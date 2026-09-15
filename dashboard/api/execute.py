"""POST /api/execute: run the partner sync pipeline live against Turso.

Vercel Python serverless function. Self-contained on purpose: the mock ERP
data generator, normalization, quality gates, and Turso writes are inlined
here (mirroring pipeline/ and mock_partner_api/ in the repo) so the function
has no local imports beyond the standard library and libsql.

Each invocation fetches all pages from the deterministic mock partner API
(including its flaky pages, handled with retries), normalizes the batch,
runs the quality gates, upserts into Turso, and records the run for the
dashboard. A 60-second cooldown between runs keeps the public demo
spam-proof.
"""
from __future__ import annotations

import json
import os
import random
import time
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler

import libsql

# ---------------------------------------------------------------------------
# Mock partner ERP (deterministic; mirrors mock_partner_api/server.py)
# ---------------------------------------------------------------------------

TOTAL_ORDERS = 137
PAGE_SIZE = 20
RUN_COOLDOWN_SECONDS = 60

_rng = random.Random(42)
_failed_once_pages: set[int] = set()

BASE_TIME = datetime(2026, 1, 5, 14, 30, 0, tzinfo=timezone.utc)


def _messy_amount(i: int):
    base = round(_rng.uniform(10, 5000), 2)
    style = i % 4
    if style == 0:
        return f"${base:,.2f}"
    if style == 1:
        return base
    if style == 2:
        return str(base)
    return None


def _messy_date(i: int):
    ts = BASE_TIME + timedelta(hours=i * 7)
    style = i % 5
    if style == 0:
        return ts.isoformat()
    if style == 1:
        return ts.strftime("%m/%d/%Y %H:%M")
    if style == 2:
        return ts.strftime("%Y-%m-%d %H:%M:%S")
    if style == 3:
        return ts.strftime("%Y-%m-%d")
    return None


def _messy_status(i: int):
    options = ["shipped", "SHIPPED", "in_transit", "in transit",
               "delivered", "DELIVERED", "cancelled", None]
    return options[i % len(options)]


def _build_order(i: int) -> dict:
    order = {
        "order_id": f"ORD-{10000 + i}",
        "amount": _messy_amount(i),
        "status": _messy_status(i),
        "ordered_at": _messy_date(i),
    }
    if i % 11 == 0:
        pass
    elif i % 2 == 0:
        order["customer_id"] = f"CUST-{5000 + (i % 37)}"
    else:
        order["custId"] = f"CUST-{5000 + (i % 37)}"
    if i % 9 == 0:
        order["currency"] = "usd" if i % 2 == 0 else "USD"
    return order


class TransientError(Exception):
    """Simulated 500 from the flaky partner API."""


def _list_orders(page: int, page_size: int) -> dict:
    # Flaky: first request for every 4th page fails, retry succeeds.
    if page % 4 == 0 and page not in _failed_once_pages:
        _failed_once_pages.add(page)
        raise TransientError("upstream hiccup")
    start = (page - 1) * page_size
    orders = [_build_order(i) for i in range(start, min(start + page_size, TOTAL_ORDERS))]
    return {
        "orders": orders,
        "page": page,
        "has_more": start + page_size < TOTAL_ORDERS,
        "total": TOTAL_ORDERS,
    }


def fetch_all_pages(page_size: int = PAGE_SIZE) -> list[dict]:
    """Paginated fetch with exponential-backoff retries on transient errors."""
    raw: list[dict] = []
    page = 1
    while True:
        for attempt in range(6):
            try:
                data = _list_orders(page, page_size)
                break
            except TransientError:
                time.sleep(min(2 ** attempt, 8))
        else:
            raise RuntimeError(f"page {page} kept failing after retries")
        raw.extend(data["orders"])
        if not data["has_more"]:
            return raw
        page += 1


# ---------------------------------------------------------------------------
# Normalization (mirrors pipeline/normalize.py)
# ---------------------------------------------------------------------------

@dataclass
class CanonicalOrder:
    order_id: str
    amount: float | None
    currency: str | None
    status: str | None
    customer_id: str | None
    ordered_at: str | None


_DATE_FORMATS = (
    "%Y-%m-%dT%H:%M:%S%z",
    "%Y-%m-%dT%H:%M:%S.%f%z",
    "%m/%d/%Y %H:%M",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d",
)


def parse_amount(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        cleaned = value.replace("$", "").replace(",", "").strip()
        try:
            return float(cleaned)
        except ValueError:
            return None
    return None


def parse_date(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    for fmt in _DATE_FORMATS:
        try:
            dt = datetime.strptime(text, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc).isoformat()
        except ValueError:
            continue
    try:
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat()
    except ValueError:
        return None


def parse_status(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip().lower()
    if not text:
        return None
    return text.replace(" ", "_").replace("-", "_")


def parse_customer_id(record: dict) -> str | None:
    for key in ("customer_id", "custId"):
        val = record.get(key)
        if val:
            return str(val)
    return None


def normalize_record(record: dict) -> CanonicalOrder:
    currency = record.get("currency")
    return CanonicalOrder(
        order_id=str(record.get("order_id")),
        amount=parse_amount(record.get("amount")),
        currency=str(currency).upper() if currency else None,
        status=parse_status(record.get("status")),
        customer_id=parse_customer_id(record),
        ordered_at=parse_date(record.get("ordered_at")),
    )


def normalize_batch(records: list[dict]) -> list[CanonicalOrder]:
    return [normalize_record(r) for r in records]


# ---------------------------------------------------------------------------
# Quality gates (mirrors pipeline/quality.py)
# ---------------------------------------------------------------------------

@dataclass
class CheckResult:
    name: str
    passed: bool
    detail: str


@dataclass
class QualityReport:
    results: list[CheckResult] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return all(r.passed for r in self.results)


MAX_NULL_AMOUNT_RATIO = 0.40
MAX_NULL_STATUS_RATIO = 0.25
MAX_NULL_DATE_RATIO = 0.35
MAX_NULL_CUSTOMER_RATIO = 0.25


def _null_ratio(orders: list[CanonicalOrder], attr: str) -> float:
    if not orders:
        return 0.0
    return sum(1 for o in orders if getattr(o, attr) is None) / len(orders)


def run_quality_checks(orders: list[CanonicalOrder]) -> QualityReport:
    report = QualityReport()
    report.results.append(CheckResult(
        name="non_empty_batch",
        passed=len(orders) > 0,
        detail=f"{len(orders)} records in batch",
    ))
    counts = Counter(o.order_id for o in orders)
    dupes = {oid: n for oid, n in counts.items() if n > 1}
    report.results.append(CheckResult(
        name="no_duplicate_order_ids",
        passed=not dupes,
        detail=f"{len(dupes)} duplicate order ids" if dupes else "all order ids unique",
    ))
    for attr, limit in (
        ("amount", MAX_NULL_AMOUNT_RATIO),
        ("status", MAX_NULL_STATUS_RATIO),
        ("ordered_at", MAX_NULL_DATE_RATIO),
        ("customer_id", MAX_NULL_CUSTOMER_RATIO),
    ):
        ratio = _null_ratio(orders, attr)
        report.results.append(CheckResult(
            name=f"{attr}_null_ratio_below_{int(limit * 100)}pct",
            passed=ratio <= limit,
            detail=f"{ratio:.1%} null (limit {limit:.0%})",
        ))
    return report


# ---------------------------------------------------------------------------
# Turso storage (same schema as pipeline/store.py; libsql is sqlite3-shaped)
# ---------------------------------------------------------------------------

_SCHEMA = """
CREATE TABLE IF NOT EXISTS orders (
    order_id    TEXT PRIMARY KEY,
    amount      REAL,
    currency    TEXT,
    status      TEXT,
    customer_id TEXT,
    ordered_at  TEXT,
    synced_at   TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);
"""

_RUNS_SCHEMA = """
CREATE TABLE IF NOT EXISTS sync_runs (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    run_at         TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    orders_fetched INTEGER NOT NULL,
    new_rows       INTEGER NOT NULL,
    total_rows     INTEGER,
    quality_passed INTEGER NOT NULL,
    dry_run        INTEGER NOT NULL DEFAULT 0,
    checks_json    TEXT NOT NULL DEFAULT '[]'
);
"""


def upsert_orders(conn, orders: list[CanonicalOrder]) -> int:
    conn.executemany(
        """
        INSERT INTO orders (order_id, amount, currency, status, customer_id, ordered_at)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(order_id) DO UPDATE SET
            amount      = excluded.amount,
            currency    = excluded.currency,
            status      = excluded.status,
            customer_id = excluded.customer_id,
            ordered_at  = excluded.ordered_at,
            synced_at   = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
        """,
        [(o.order_id, o.amount, o.currency, o.status, o.customer_id, o.ordered_at)
         for o in orders],
    )
    return len(orders)


def count_orders(conn) -> int:
    return conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0]


def record_sync_run(conn, *, orders_fetched, new_rows, total_rows,
                    quality_passed, dry_run, checks) -> int:
    payload = json.dumps(
        [{"name": c.name, "passed": bool(c.passed), "detail": c.detail} for c in checks]
    )
    cur = conn.execute(
        """
        INSERT INTO sync_runs
            (orders_fetched, new_rows, total_rows, quality_passed, dry_run, checks_json)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (orders_fetched, new_rows, total_rows, int(quality_passed), int(dry_run), payload),
    )
    return cur.lastrowid


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def run_pipeline() -> dict:
    url = os.environ.get("TURSO_DATABASE_URL")
    token = os.environ.get("TURSO_AUTH_TOKEN")
    if not url or not token:
        raise RuntimeError("Turso is not configured on this deployment")

    conn = libsql.connect(url, auth_token=token)
    try:
        conn.execute(_SCHEMA)
        conn.execute(_RUNS_SCHEMA)

        row = conn.execute(
            "SELECT run_at FROM sync_runs ORDER BY id DESC LIMIT 1"
        ).fetchone()
        if row and row[0]:
            last = datetime.fromisoformat(str(row[0]).replace("Z", "+00:00"))
            elapsed = (datetime.now(timezone.utc) - last).total_seconds()
            if elapsed < RUN_COOLDOWN_SECONDS:
                raise RuntimeError(
                    f"A sync ran {int(elapsed)}s ago; wait a minute between runs"
                )

        raw = fetch_all_pages()
        orders = normalize_batch(raw)
        report = run_quality_checks(orders)

        before = count_orders(conn)
        if report.passed:
            upsert_orders(conn, orders)
            after = count_orders(conn)
            record_sync_run(
                conn, orders_fetched=len(orders), new_rows=after - before,
                total_rows=after, quality_passed=True, dry_run=False,
                checks=report.results,
            )
            new_rows = after - before
        else:
            after = before
            record_sync_run(
                conn, orders_fetched=len(orders), new_rows=0,
                total_rows=before, quality_passed=False, dry_run=False,
                checks=report.results,
            )
            new_rows = 0
        conn.commit()

        return {
            "fetched": len(orders),
            "new_rows": new_rows,
            "total_rows": after,
            "quality_passed": report.passed,
            "checks": [
                {"name": c.name, "passed": c.passed, "detail": c.detail}
                for c in report.results
            ],
        }
    finally:
        conn.close()


class handler(BaseHTTPRequestHandler):
    def _send(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:
        try:
            result = run_pipeline()
        except RuntimeError as exc:
            # Cooldown / config problems are client-visible, not crashes.
            self._send(429, {"ok": False, "error": str(exc)})
            return
        except Exception as exc:  # noqa: BLE001 - surfaced as JSON
            self._send(500, {"ok": False, "error": f"sync failed: {exc}"})
            return
        self._send(200, {"ok": True, **result})

    def do_GET(self) -> None:
        self._send(405, {"ok": False, "error": "Use POST to run a sync"})

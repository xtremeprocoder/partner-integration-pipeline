"""Sync orchestrator: fetch -> normalize -> quality gate -> store.

Usage:
    python -m pipeline.sync --base-url http://localhost:8000 --db orders.db
    python -m pipeline.sync --base-url http://localhost:8000 --db orders.db --dry-run
"""
from __future__ import annotations

import argparse
import sys

from .client import PartnerAPIClient
from .normalize import normalize_batch
from .quality import run_quality_checks
from .store import connect, count_orders, record_sync_run, upsert_orders


def run_sync(base_url: str, db_path: str, *, page_size: int = 20, dry_run: bool = False) -> dict:
    client = PartnerAPIClient(base_url)
    try:
        raw = list(client.iter_orders(page_size=page_size))
    finally:
        client.close()

    orders = normalize_batch(raw)
    report = run_quality_checks(orders)
    print(report.summary())
    print()

    if not report.passed:
        with connect(db_path) as conn:
            record_sync_run(
                conn,
                orders_fetched=len(orders),
                new_rows=0,
                total_rows=count_orders(conn),
                quality_passed=False,
                dry_run=dry_run,
                checks=report.results,
            )
        print("Quality gate FAILED. Nothing was written.", file=sys.stderr)
        raise SystemExit(2)

    if dry_run:
        with connect(db_path) as conn:
            record_sync_run(
                conn,
                orders_fetched=len(orders),
                new_rows=0,
                total_rows=count_orders(conn),
                quality_passed=True,
                dry_run=True,
                checks=report.results,
            )
        print(f"Dry run: would write {len(orders)} orders to {db_path}.")
        return {"fetched": len(orders), "written": 0, "total": None}

    with connect(db_path) as conn:
        before = count_orders(conn)
        written = upsert_orders(conn, orders)
        after = count_orders(conn)
        record_sync_run(
            conn,
            orders_fetched=len(orders),
            new_rows=after - before,
            total_rows=after,
            quality_passed=True,
            dry_run=False,
            checks=report.results,
        )
    print(f"Synced {written} orders to {db_path} ({after} total rows).")
    return {"fetched": len(orders), "written": written, "total": after}


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Sync partner orders into SQLite.")
    parser.add_argument("--base-url", default="http://localhost:8000",
                        help="Base URL of the partner API")
    parser.add_argument("--db", default="orders.db", help="SQLite database path")
    parser.add_argument("--page-size", type=int, default=20, help="Orders per page")
    parser.add_argument("--dry-run", action="store_true",
                        help="Fetch and validate, but do not write")
    args = parser.parse_args(argv)
    run_sync(args.base_url, args.db, page_size=args.page_size, dry_run=args.dry_run)


if __name__ == "__main__":
    main()

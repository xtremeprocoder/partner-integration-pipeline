"""Normalize messy partner records into one canonical order schema.

The partner API sends amounts in four formats, dates in five, statuses in
mixed case with mixed separators, and the customer id under two different key
names (sometimes absent). Every field normalizer below is pure and total:
it accepts anything and returns a typed value or None, never raising.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

# One canonical schema, enforced at the boundary. Everything downstream
# (storage, quality checks, the future agent) sees only this shape.
@dataclass
class CanonicalOrder:
    order_id: str
    amount: float | None          # USD minor units removed; plain float
    currency: str | None         # ISO code, uppercase ("USD")
    status: str | None           # lowercase snake_case ("in_transit")
    customer_id: str | None
    ordered_at: str | None       # ISO 8601 in UTC


_DATE_FORMATS = (
    "%Y-%m-%dT%H:%M:%S%z",   # isoformat with tz (Python < 3.11 variant)
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
    # ISO strings with offsets parse cleanly via fromisoformat
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
    # Two key names in the wild; first non-empty wins.
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

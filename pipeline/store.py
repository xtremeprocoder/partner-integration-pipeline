"""Durable storage for normalized orders.

Syncs must be safe to re-run at any point: the orders table has a UNIQUE
constraint on order_id and writes use INSERT ... ON CONFLICT DO UPDATE,
so a crashed-and-restarted sync (or an accidental double run) produces the
same rows, never duplicates.
"""
from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from .normalize import CanonicalOrder

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


@contextmanager
def connect(db_path: str | Path) -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute(_SCHEMA)
        yield conn
        conn.commit()
    finally:
        conn.close()


def upsert_orders(conn: sqlite3.Connection, orders: list[CanonicalOrder]) -> int:
    """Write orders idempotently. Returns the number of rows processed."""
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
        [
            (o.order_id, o.amount, o.currency, o.status, o.customer_id, o.ordered_at)
            for o in orders
        ],
    )
    return len(orders)


def count_orders(conn: sqlite3.Connection) -> int:
    return conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0]

"""Idempotency: syncing the same batch twice must not duplicate rows,
and updated partner data must overwrite cleanly in place."""
from pipeline.normalize import CanonicalOrder
from pipeline.quality import run_quality_checks
from pipeline.store import connect, count_orders, upsert_orders


def _orders():
    return [
        CanonicalOrder("ORD-1", 100.0, "USD", "shipped", "CUST-1", "2026-01-05T00:00:00+00:00"),
        CanonicalOrder("ORD-2", 50.5, "USD", "delivered", "CUST-2", "2026-01-06T00:00:00+00:00"),
    ]


def test_double_sync_no_duplicates(tmp_path):
    db = tmp_path / "test.db"
    with connect(db) as conn:
        upsert_orders(conn, _orders())
        assert count_orders(conn) == 2
        upsert_orders(conn, _orders())
        assert count_orders(conn) == 2


def test_updated_record_overwrites(tmp_path):
    db = tmp_path / "test.db"
    with connect(db) as conn:
        upsert_orders(conn, _orders())
        updated = _orders()
        updated[0].status = "delivered"
        updated[0].amount = 120.0
        upsert_orders(conn, updated)
        row = conn.execute(
            "SELECT status, amount FROM orders WHERE order_id = 'ORD-1'"
        ).fetchone()
        assert row["status"] == "delivered"
        assert row["amount"] == 120.0
        assert count_orders(conn) == 2


def test_quality_gate_catches_null_storm():
    # Every field null: fails every ratio check.
    bad = [CanonicalOrder(f"ORD-{i}", None, None, None, None, None) for i in range(10)]
    report = run_quality_checks(bad)
    assert not report.passed


def test_quality_gate_passes_realistic_batch():
    report = run_quality_checks(_orders())
    assert report.passed

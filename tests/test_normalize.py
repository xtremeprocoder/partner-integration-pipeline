"""Tests for the normalize module: every messy format the partner API produces."""
from pipeline.normalize import (
    CanonicalOrder,
    normalize_record,
    parse_amount,
    parse_customer_id,
    parse_date,
    parse_status,
)


def test_parse_amount_all_styles():
    assert parse_amount("$1,234.56") == 1234.56
    assert parse_amount(1234.56) == 1234.56
    assert parse_amount("1234.56") == 1234.56
    assert parse_amount(None) is None
    assert parse_amount("garbage") is None


def test_parse_date_all_styles():
    assert parse_date("2026-01-05T14:30:00+00:00") == "2026-01-05T14:30:00+00:00"
    assert parse_date("01/05/2026 14:30") == "2026-01-05T14:30:00+00:00"
    assert parse_date("2026-01-05 14:30:00") == "2026-01-05T14:30:00+00:00"
    assert parse_date("2026-01-05") == "2026-01-05T00:00:00+00:00"
    assert parse_date(None) is None
    assert parse_date("not a date") is None


def test_parse_status_variants():
    assert parse_status("shipped") == "shipped"
    assert parse_status("SHIPPED") == "shipped"
    assert parse_status("in_transit") == "in_transit"
    assert parse_status("in transit") == "in_transit"
    assert parse_status(None) is None


def test_parse_customer_id_two_keys():
    assert parse_customer_id({"customer_id": "CUST-1"}) == "CUST-1"
    assert parse_customer_id({"custId": "CUST-2"}) == "CUST-2"
    assert parse_customer_id({}) is None


def test_normalize_record_full():
    record = {
        "order_id": "ORD-10001",
        "amount": "$2,500.00",
        "status": "DELIVERED",
        "custId": "CUST-5001",
        "ordered_at": "01/06/2026 09:00",
        "currency": "usd",
    }
    order = normalize_record(record)
    assert order == CanonicalOrder(
        order_id="ORD-10001",
        amount=2500.00,
        currency="USD",
        status="delivered",
        customer_id="CUST-5001",
        ordered_at="2026-01-06T09:00:00+00:00",
    )


def test_normalize_record_all_missing():
    order = normalize_record({"order_id": "ORD-10002"})
    assert order.amount is None
    assert order.currency is None
    assert order.status is None
    assert order.customer_id is None
    assert order.ordered_at is None

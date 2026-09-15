"""Mock partner ERP API.

Simulates the messy reality of a real partner integration: inconsistent field
formats, missing values, occasional 500s, and rate limiting. Output is seeded
so demos are reproducible.
"""
import random
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

app = FastAPI(title="Mock Partner ERP API")

TOTAL_ORDERS = 137
PAGE_SIZE_DEFAULT = 20
RATE_LIMIT_PER_MINUTE = 40

_rng = random.Random(42)
_request_times: list = []
_failed_once_pages: set = set()

BASE_TIME = datetime(2026, 1, 5, 14, 30, 0, tzinfo=timezone.utc)


def _messy_amount(i: int):
    base = round(_rng.uniform(10, 5000), 2)
    style = i % 4
    if style == 0:
        return f"${base:,.2f}"      # "$1,234.56"
    if style == 1:
        return base                 # 1234.56
    if style == 2:
        return str(base)            # "1234.56"
    return None                     # missing entirely


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
    # customer id missing on every 11th record, alternate key names otherwise
    if i % 11 == 0:
        pass
    elif i % 2 == 0:
        order["customer_id"] = f"CUST-{5000 + (i % 37)}"
    else:
        order["custId"] = f"CUST-{5000 + (i % 37)}"
    if i % 9 == 0:
        order["currency"] = "usd" if i % 2 == 0 else "USD"
    return order


@app.middleware("http")
async def rate_limit(request: Request, call_next):
    now = time.time()
    while _request_times and _request_times[0] < now - 60:
        _request_times.pop(0)
    if len(_request_times) >= RATE_LIMIT_PER_MINUTE:
        return JSONResponse(
            status_code=429,
            content={"error": "rate limit exceeded, slow down"},
            headers={"Retry-After": "5"},
        )
    _request_times.append(now)
    return await call_next(request)


@app.get("/orders")
def list_orders(page: int = 1, page_size: int = PAGE_SIZE_DEFAULT):
    # Flaky: first request for every 4th page fails, retry succeeds.
    if page % 4 == 0 and page not in _failed_once_pages:
        _failed_once_pages.add(page)
        return JSONResponse(status_code=500, content={"error": "upstream hiccup"})
    start = (page - 1) * page_size
    orders = [_build_order(i) for i in range(start, min(start + page_size, TOTAL_ORDERS))]
    return {
        "orders": orders,
        "page": page,
        "has_more": start + page_size < TOTAL_ORDERS,
        "total": TOTAL_ORDERS,
    }


@app.get("/health")
def health():
    return {"ok": True, "total_orders": TOTAL_ORDERS}

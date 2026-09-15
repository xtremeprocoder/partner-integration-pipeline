"""HTTP client for the partner ERP API.

Retries transient failures with exponential backoff, honors the Retry-After
header on 429s, and exposes a paginated iterator so callers never think about
page bookkeeping.
"""
from __future__ import annotations

import time
from collections.abc import Iterator

import httpx

RETRYABLE_STATUS = {429, 500, 502, 503, 504}


class PartnerAPIClient:
    def __init__(
        self,
        base_url: str,
        *,
        max_retries: int = 5,
        backoff_base: float = 1.0,
        timeout: float = 30.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.max_retries = max_retries
        self.backoff_base = backoff_base
        self._http = httpx.Client(
            base_url=self.base_url,
            timeout=timeout,
            # Ignore ambient proxy env vars: this talks to a partner endpoint
            # directly, and proxy env values can be unparsable.
            trust_env=False,
        )

    def close(self) -> None:
        self._http.close()

    def _get_json(self, path: str, params: dict) -> dict:
        """GET with retry on transient failures. Raises on permanent errors."""
        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                resp = self._http.get(path, params=params)
            except httpx.TransportError as exc:  # connection reset, timeout, ...
                last_error = exc
            else:
                if resp.status_code == 200:
                    return resp.json()
                if resp.status_code in RETRYABLE_STATUS:
                    last_error = httpx.HTTPStatusError(
                        f"retryable {resp.status_code} on {path}",
                        request=resp.request,
                        response=resp,
                    )
                else:
                    resp.raise_for_status()  # permanent: fail fast, don't retry
            if attempt < self.max_retries:
                time.sleep(self._backoff_delay(attempt, last_error))
        raise RuntimeError(f"gave up on {path} after {self.max_retries} retries") from last_error

    def _backoff_delay(self, attempt: int, error: Exception | None) -> float:
        # Server-sent Retry-After wins; otherwise exponential backoff with jitter.
        if isinstance(error, httpx.HTTPStatusError) and error.response is not None:
            retry_after = error.response.headers.get("retry-after")
            if retry_after and retry_after.isdigit():
                return float(retry_after)
        base = self.backoff_base * (2 ** attempt)
        return base + base * 0.25  # small deterministic jitter keeps tests stable

    def iter_orders(self, page_size: int = 20) -> Iterator[dict]:
        """Yield raw order dicts across all pages until the API says has_more is false."""
        page = 1
        while True:
            payload = self._get_json("/orders", {"page": page, "page_size": page_size})
            yield from payload["orders"]
            if not payload.get("has_more"):
                return
            page += 1

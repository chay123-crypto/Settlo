"""
Read-only Razorpay Test Mode client.

PLACEHOLDER / MOCK MODE
------------------------
You said you don't have a Razorpay test account set up yet. This client
handles that: if RAZORPAY_KEY_ID / RAZORPAY_KEY_SECRET are not set in
.env, every call is served by a local mock that mimics Razorpay's
Settlements API shape (including one simulated timeout on request) so
the rest of the pipeline -- and your failure-handling demo -- works
end-to-end without a real account.

The moment you add real credentials to .env, this switches to making
real HTTP calls against Razorpay Test Mode. No other code changes needed.
"""
import random
import time
from datetime import date, timedelta

import requests
from requests.auth import HTTPBasicAuth
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)

from .config import settings


class TemporaryRazorpayError(Exception):
    """Raised for retryable failures: timeouts, 429, 5xx."""


class RazorpayAuthError(Exception):
    """Raised for non-retryable failures: bad credentials, bad request."""


# ---------------------------------------------------------------------
# Mock mode
# ---------------------------------------------------------------------

_MOCK_CALL_COUNT = {"n": 0}


def _mock_fetch_settlements(params=None, force_failure=False):
    """Simulate GET /v1/settlements.

    force_failure=True (or every 5th call, deterministically) simulates
    a transient server error so failure-handling can be demonstrated
    without needing a real flaky API.
    """
    _MOCK_CALL_COUNT["n"] += 1

    if force_failure:
        raise TemporaryRazorpayError("Mock: simulated HTTP 503 from Razorpay Test Mode")

    count = int((params or {}).get("count", 10))
    items = []
    base = date(2026, 8, 1)
    for i in range(count):
        items.append({
            "id": f"setl_mock_{i:04d}",
            "entity": "settlement",
            "status": "processed",
            "amount": random.randrange(5000, 250000, 100),
            "fees": random.randrange(50, 5000),
            "tax": random.randrange(10, 900),
            "utr": f"MOCKUTR{i:06d}",
            "created_at": int(time.mktime((base + timedelta(days=i)).timetuple())),
        })
    return {"entity": "collection", "count": len(items), "items": items, "_source": "MOCK_MODE"}


# ---------------------------------------------------------------------
# Real client
# ---------------------------------------------------------------------

@retry(
    stop=stop_after_attempt(settings.max_api_attempts),
    wait=wait_exponential(multiplier=1, min=1, max=4),
    retry=retry_if_exception_type(TemporaryRazorpayError),
    reraise=True,
)
def _real_fetch_settlements(params=None):
    response = requests.get(
        f"{settings.razorpay_base_url}/settlements",
        params=params or {},
        auth=HTTPBasicAuth(settings.razorpay_key_id, settings.razorpay_key_secret),
        timeout=settings.api_timeout_seconds,
    )
    if response.status_code in (401, 403):
        raise RazorpayAuthError(f"Razorpay auth failed: HTTP {response.status_code}")
    if response.status_code in (408, 429) or response.status_code >= 500:
        raise TemporaryRazorpayError(f"Temporary HTTP {response.status_code}")
    response.raise_for_status()
    data = response.json()
    data["_source"] = "LIVE_TEST_MODE"
    return data


@retry(
    stop=stop_after_attempt(settings.max_api_attempts),
    wait=wait_exponential(multiplier=1, min=1, max=4),
    retry=retry_if_exception_type(TemporaryRazorpayError),
    reraise=True,
)
def _mock_fetch_with_retry(params=None, force_failure=False):
    # Wrapped in the same retry policy as the real client so the
    # failure-handling test exercises identical retry/backoff behaviour.
    return _mock_fetch_settlements(params=params, force_failure=force_failure)


def fetch_settlements(params=None, simulate_failure=False):
    """Public entry point. Routes to mock or live client based on
    whether real credentials are configured.

    simulate_failure: force a transient-error path, for testing/demo
    purposes only. Ignored in live mode (you can't force Razorpay's API
    to fail on demand -- use mock mode for a reliable failure demo, or
    briefly point razorpay_base_url at an invalid host to fail live).
    """
    if settings.razorpay_mock_mode:
        return _mock_fetch_with_retry(params=params, force_failure=simulate_failure)
    return _real_fetch_settlements(params=params)


def connectivity_check():
    """Small check used at startup / in the UI to show which mode is active."""
    try:
        result = fetch_settlements(params={"count": 1})
        return {
            "ok": True,
            "mode": "MOCK" if settings.razorpay_mock_mode else "LIVE_TEST_MODE",
            "sample_count": result.get("count", 0),
        }
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "mode": "MOCK" if settings.razorpay_mock_mode else "LIVE_TEST_MODE", "error": str(exc)}

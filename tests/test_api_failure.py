import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.razorpay_client import (  # noqa: E402
    TemporaryRazorpayError,
    _mock_fetch_settlements,
    fetch_settlements,
)


def test_mock_fetch_returns_settlements(monkeypatch):
    monkeypatch.setattr("backend.config.settings.razorpay_key_id", "")
    result = fetch_settlements(params={"count": 5})
    assert result["count"] == 5
    assert result["_source"] == "MOCK_MODE"


def test_forced_failure_raises_after_retries(monkeypatch):
    """Confirms the retry-wrapped mock client eventually surfaces the
    error rather than retrying forever or silently swallowing it."""
    monkeypatch.setattr("backend.config.settings.razorpay_key_id", "")
    with pytest.raises(TemporaryRazorpayError):
        fetch_settlements(params={"count": 1}, simulate_failure=True)


def test_direct_mock_failure_flag():
    with pytest.raises(TemporaryRazorpayError):
        _mock_fetch_settlements(force_failure=True)

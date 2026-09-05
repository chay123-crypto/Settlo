import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.validation import validate_order, validate_payment  # noqa: E402


def test_valid_order_passes():
    order = {
        "merchant_order_id": "ORDER-0001", "razorpay_order_id": "order_test_0001",
        "gross_amount_paise": 100000, "currency": "INR", "order_date": "2026-08-01",
    }
    result = validate_order(order)
    assert result.is_valid


def test_blank_id_fails():
    order = {"merchant_order_id": "", "razorpay_order_id": "order_test_0001",
              "gross_amount_paise": 100000, "currency": "INR", "order_date": "2026-08-01"}
    result = validate_order(order)
    assert not result.is_valid
    assert any("INVALID_ID" in e for e in result.errors)


def test_bad_currency_fails():
    order = {"merchant_order_id": "ORDER-0001", "razorpay_order_id": "order_test_0001",
              "gross_amount_paise": 100000, "currency": "USD", "order_date": "2026-08-01"}
    result = validate_order(order)
    assert not result.is_valid
    assert any("CURRENCY_MISMATCH" in e for e in result.errors)


def test_negative_amount_fails():
    order = {"merchant_order_id": "ORDER-0001", "razorpay_order_id": "order_test_0001",
              "gross_amount_paise": -100, "currency": "INR", "order_date": "2026-08-01"}
    result = validate_order(order)
    assert not result.is_valid


def test_payment_net_calculation_check():
    payment = {"payment_id": "pay_1", "payment_status": "captured",
               "gross_amount_paise": 1000, "fee_paise": 20, "tax_paise": 4, "net_amount_paise": 900}
    result = validate_payment(payment)
    assert not result.is_valid
    assert any("NET_CALCULATION_MISMATCH" in e for e in result.errors)

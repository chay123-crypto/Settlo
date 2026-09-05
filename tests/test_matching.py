import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.matcher import reconcile  # noqa: E402


def base_order():
    return {
        "merchant_order_id": "ORDER-0001", "razorpay_order_id": "order_test_0001",
        "customer_ref": "CUST-0001", "order_date": "2026-08-01",
        "gross_amount_paise": 100000, "currency": "INR", "expected_status": "paid",
    }


def base_payment():
    return {
        "payment_id": "pay_test_0001", "order_id": "order_test_0001", "settlement_id": "setl_test_0001",
        "transaction_type": "payment", "payment_date": "2026-08-01",
        "gross_amount_paise": 100000, "fee_paise": 2000, "tax_paise": 360,
        "net_amount_paise": 97640, "payment_status": "captured",
    }


def base_bank():
    return {
        "bank_reference": "UTR00000001", "settlement_id": "setl_test_0001",
        "credit_date": "2026-08-03", "credited_amount_paise": 97640,
        "currency": "INR", "bank_status": "credited",
    }


def test_exact_match():
    decision = reconcile(base_order(), [base_payment()], [base_bank()], [])
    assert decision.status == "EXACT_MATCH"
    assert decision.requires_review is False


def test_refund_adjusted_match():
    payment = base_payment()
    bank = base_bank()
    bank["credited_amount_paise"] = 97640 - 10000
    refunds = [{"refund_id": "r1", "payment_id": payment["payment_id"],
                "refund_date": "2026-08-02", "refund_amount_paise": 10000, "refund_status": "processed"}]
    decision = reconcile(base_order(), [payment], [bank], refunds)
    assert decision.status == "EXACT_MATCH_AFTER_REFUND"


def test_amount_mismatch_is_not_auto_matched():
    bank = base_bank()
    bank["credited_amount_paise"] += 100
    decision = reconcile(base_order(), [base_payment()], [bank], [])
    assert decision.status == "AMOUNT_MISMATCH"
    assert decision.requires_review is True
    assert decision.evidence["actual_credit_paise"] != decision.evidence["expected_net_paise"]


def test_missing_settlement():
    decision = reconcile(base_order(), [base_payment()], [], [])
    assert decision.status == "MISSING_SETTLEMENT"
    assert decision.requires_review is True


def test_duplicate_payment():
    p1 = base_payment()
    p2 = dict(p1)
    p2["payment_id"] = "pay_test_0001_dup"
    decision = reconcile(base_order(), [p1, p2], [base_bank()], [])
    assert decision.status == "DUPLICATE_PAYMENT"
    assert decision.requires_review is True


def test_unmatched_no_candidates():
    decision = reconcile(base_order(), [], [], [])
    assert decision.status == "UNMATCHED"


def test_ambiguous_composite_match():
    order = base_order()
    order["razorpay_order_id"] = "order_no_direct_link"
    p1 = base_payment()
    p1["order_id"] = ""
    p1["payment_id"] = "pay_a"
    p2 = dict(p1)
    p2["payment_id"] = "pay_b"
    decision = reconcile(order, [p1, p2], [], [])
    assert decision.status == "AMBIGUOUS_MATCH"
    assert decision.requires_review is True


def test_probable_match_single_composite_candidate():
    order = base_order()
    order["razorpay_order_id"] = "order_no_direct_link"
    p1 = base_payment()
    p1["order_id"] = ""
    decision = reconcile(order, [p1], [], [])
    assert decision.status == "PROBABLE_MATCH"
    assert decision.requires_review is True

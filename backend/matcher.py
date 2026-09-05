"""
Deterministic reconciliation engine.

Core design principle: code decides the money. This module contains
ZERO calls to any LLM. Every decision must be reproducible: the same
input always produces the same output, explained by a fixed rule_code.

Rules are applied in strict priority order (see `reconcile`). The first
rule that matches wins.
"""
from dataclasses import dataclass, field
from datetime import date, timedelta


@dataclass
class MatchDecision:
    status: str
    confidence: int
    rule_code: str
    requires_review: bool
    evidence: dict = field(default_factory=dict)


def _completed_refund_total(payment_id: str, refunds: list) -> int:
    return sum(
        int(r["refund_amount_paise"])
        for r in refunds
        if r.get("payment_id") == payment_id and r.get("refund_status") == "processed"
    )


def reconcile(order: dict, payments: list, settlements: list, refunds: list,
              date_window_days: int = 3, settlement_sla_days: int = 5) -> MatchDecision:
    """
    order:       one row from orders.csv (dict)
    payments:    all rows from razorpay_transactions.csv (list of dict)
    settlements: all rows from bank_settlements.csv (list of dict)
    refunds:     all rows from refunds.csv (list of dict)
    """
    order_id = order["razorpay_order_id"]

    # --- find payment candidates by exact order id ---
    candidates = [p for p in payments if p.get("order_id") == order_id]

    if len(candidates) > 1:
        return MatchDecision(
            "DUPLICATE_PAYMENT", 100, "MULTIPLE_PAYMENT_IDS", True,
            {"candidate_count": len(candidates), "payment_ids": [c["payment_id"] for c in candidates]},
        )

    if len(candidates) == 1:
        payment = candidates[0]
        bank_rows = [s for s in settlements if s.get("settlement_id") == payment.get("settlement_id")]

        if len(bank_rows) > 1:
            return MatchDecision(
                "DUPLICATE_SETTLEMENT", 100, "MULTIPLE_BANK_CREDITS", True,
                {"candidate_count": len(bank_rows), "settlement_id": payment.get("settlement_id")},
            )

        if not bank_rows:
            net_amt = int(payment.get("net_amount_paise", int(payment.get("gross_amount_paise", 0)) - int(payment.get("fee_paise", 0)) - int(payment.get("tax_paise", 0))))
            return MatchDecision(
                "MISSING_SETTLEMENT", 100, "NO_BANK_CREDIT", True,
                {"payment_id": payment["payment_id"], "settlement_id": payment.get("settlement_id"), "amount_paise": net_amt, "expected_net_paise": net_amt},
            )

        bank = bank_rows[0]
        completed_refund = _completed_refund_total(payment["payment_id"], refunds)
        gross = int(payment["gross_amount_paise"])
        fee = int(payment["fee_paise"])
        tax = int(payment["tax_paise"])
        expected_net = gross - fee - tax - completed_refund
        actual_credit = int(bank["credited_amount_paise"])

        if order.get("currency") != bank.get("currency", order.get("currency")):
            return MatchDecision(
                "CURRENCY_MISMATCH", 100, "CURRENCY_NOT_EQUAL", True,
                {"order_currency": order.get("currency"), "bank_currency": bank.get("currency")},
            )

        if expected_net != actual_credit:
            # Distinguish fee/tax mismatch (numbers internally inconsistent)
            # from a plain amount mismatch at the bank leg.
            recomputed_net = gross - fee - tax
            if recomputed_net != int(payment["net_amount_paise"]):
                rule_code = "FEE_OR_TAX_INCONSISTENT"
                status = "FEE_MISMATCH" if fee else "TAX_MISMATCH"
            else:
                rule_code = "NET_NOT_EQUAL"
                status = "AMOUNT_MISMATCH"
            return MatchDecision(
                status, 100, rule_code, True,
                {"expected_net_paise": expected_net, "actual_credit_paise": actual_credit,
                 "completed_refund_paise": completed_refund},
            )

        # --- delayed settlement check ---
        delay_days = 0
        try:
            p_date = date.fromisoformat(str(payment.get("payment_date")))
            c_date = date.fromisoformat(str(bank.get("credit_date")))
            delay_days = (c_date - p_date).days
        except (TypeError, ValueError):
            pass
        is_delayed = delay_days > settlement_sla_days

        if completed_refund > 0:
            evidence = {"payment_id": payment["payment_id"], "settlement_id": bank["settlement_id"],
                 "amount_paise": expected_net, "completed_refund_paise": completed_refund}
            if is_delayed:
                evidence["delay_days"] = delay_days
                evidence["delayed_settlement"] = True
            return MatchDecision(
                "EXACT_MATCH_AFTER_REFUND", 100, "ALL_EXACT_AFTER_REFUND", False,
                evidence,
            )

        evidence = {"payment_id": payment["payment_id"], "settlement_id": bank["settlement_id"],
             "amount_paise": expected_net}
        if is_delayed:
            evidence["delay_days"] = delay_days
            evidence["delayed_settlement"] = True
        return MatchDecision(
            "EXACT_MATCH", 100, "ALL_EXACT", False,
            evidence,
        )

    # --- no exact order-id candidate: try composite matching ---
    order_date = date.fromisoformat(str(order["order_date"]))
    window_start = order_date - timedelta(days=date_window_days)
    window_end = order_date + timedelta(days=date_window_days)

    composite_candidates = []
    for p in payments:
        try:
            p_date = date.fromisoformat(str(p.get("payment_date")))
        except (TypeError, ValueError):
            continue
        if (
            p.get("order_id") is None or p.get("order_id") == ""
        ) and window_start <= p_date <= window_end and \
                int(p.get("gross_amount_paise", -1)) == int(order["gross_amount_paise"]):
            composite_candidates.append(p)

    if len(composite_candidates) == 1:
        p = composite_candidates[0]
        return MatchDecision(
            "PROBABLE_MATCH", 75, "COMPOSITE_AMOUNT_DATE_WINDOW", True,
            {"payment_id": p["payment_id"], "date_window_days": date_window_days},
        )

    if len(composite_candidates) > 1:
        return MatchDecision(
            "AMBIGUOUS_MATCH", 50, "MULTIPLE_COMPOSITE_CANDIDATES", True,
            {"candidate_count": len(composite_candidates),
             "payment_ids": [c["payment_id"] for c in composite_candidates]},
        )

    return MatchDecision("UNMATCHED", 0, "NO_PAYMENT", True, {"order_id": order_id})

"""
Exception classifier. Assigns exactly one code from a FIXED taxonomy to
every non-auto-finalized record. Never invents a new label.
"""

EXCEPTION_TAXONOMY = {
    "MISSING_PAYMENT": "Order exists but no payment candidate found",
    "MISSING_SETTLEMENT": "Captured payment has no matching bank credit",
    "AMOUNT_MISMATCH": "Expected and credited net amounts differ",
    "FEE_MISMATCH": "Stored fee differs from expected fee calculation",
    "TAX_MISMATCH": "Stored tax differs from expected tax calculation",
    "DUPLICATE_PAYMENT": "More than one payment candidate for one order",
    "DUPLICATE_SETTLEMENT": "More than one bank credit for one settlement ID",
    "REFUND_PENDING": "Refund exists but is not completed",
    "DELAYED_SETTLEMENT": "Settlement is outside configured date expectation",
    "AMBIGUOUS_MATCH": "Multiple composite candidates exist",
    "CURRENCY_MISMATCH": "Order and bank credit currencies differ",
    "INPUT_VALIDATION_ERROR": "Source row cannot be safely processed",
}

# Statuses that never need an exception code -- they're auto-finalized.
_AUTO_FINALIZED = {"EXACT_MATCH", "EXACT_MATCH_AFTER_REFUND"}

# Direct status -> exception code map for statuses the matcher already
# names precisely.
_DIRECT_MAP = {
    "UNMATCHED": "MISSING_PAYMENT",
    "MISSING_SETTLEMENT": "MISSING_SETTLEMENT",
    "AMOUNT_MISMATCH": "AMOUNT_MISMATCH",
    "FEE_MISMATCH": "FEE_MISMATCH",
    "TAX_MISMATCH": "TAX_MISMATCH",
    "DUPLICATE_PAYMENT": "DUPLICATE_PAYMENT",
    "DUPLICATE_SETTLEMENT": "DUPLICATE_SETTLEMENT",
    "AMBIGUOUS_MATCH": "AMBIGUOUS_MATCH",
    "CURRENCY_MISMATCH": "CURRENCY_MISMATCH",
    "PROBABLE_MATCH": None,  # not an exception -- pending approval, not broken
}


def classify(decision) -> str | None:
    """decision: a MatchDecision from backend.matcher.reconcile

    Returns an exception code, or None if the record needs no exception
    (either auto-finalized, or a pending approval that isn't itself broken).
    """
    if decision.status in _AUTO_FINALIZED:
        return None
    if decision.status in _DIRECT_MAP:
        return _DIRECT_MAP[decision.status]
    # Should never happen if matcher.py and this taxonomy stay in sync --
    # fail loudly rather than inventing an uncontrolled label.
    raise ValueError(f"Unrecognized match status '{decision.status}' has no exception mapping")

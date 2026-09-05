"""
Row-level validation. Invalid rows are reported, never silently dropped.
"""
from dataclasses import dataclass, field
from datetime import datetime


ALLOWED_CURRENCY = {"INR"}
ALLOWED_PAYMENT_STATUS = {"captured", "failed", "refunded"}
ALLOWED_BANK_STATUS = {"credited", "pending", "reversed"}


@dataclass
class ValidationResult:
    is_valid: bool
    errors: list = field(default_factory=list)


def _err(code: str, msg: str) -> str:
    return f"{code}: {msg}"


def validate_order(row: dict) -> ValidationResult:
    errors = []
    if not str(row.get("merchant_order_id", "")).strip():
        errors.append(_err("INVALID_ID", "merchant_order_id is blank"))
    if not str(row.get("razorpay_order_id", "")).strip():
        errors.append(_err("INVALID_ID", "razorpay_order_id is blank"))
    try:
        amount = int(row.get("gross_amount_paise"))
        if amount < 0:
            errors.append(_err("INVALID_AMOUNT", "gross_amount_paise is negative"))
    except (TypeError, ValueError):
        errors.append(_err("INVALID_AMOUNT", "gross_amount_paise is not an integer"))
    if row.get("currency") not in ALLOWED_CURRENCY:
        errors.append(_err("CURRENCY_MISMATCH", f"unsupported currency {row.get('currency')}"))
    try:
        datetime.fromisoformat(str(row.get("order_date")))
    except ValueError:
        errors.append(_err("INVALID_DATE", "order_date is not ISO format"))
    return ValidationResult(is_valid=len(errors) == 0, errors=errors)


def validate_payment(row: dict) -> ValidationResult:
    errors = []
    if not str(row.get("payment_id", "")).strip():
        errors.append(_err("INVALID_ID", "payment_id is blank"))
    if row.get("payment_status") not in ALLOWED_PAYMENT_STATUS:
        errors.append(_err("INVALID_STATUS", f"unexpected payment_status {row.get('payment_status')}"))
    try:
        gross = int(row.get("gross_amount_paise"))
        fee = int(row.get("fee_paise"))
        tax = int(row.get("tax_paise"))
        net = int(row.get("net_amount_paise"))
        if gross - fee - tax != net:
            errors.append(_err("NET_CALCULATION_MISMATCH", f"gross-fee-tax={gross-fee-tax} != net={net}"))
    except (TypeError, ValueError):
        errors.append(_err("INVALID_AMOUNT", "one or more amount fields are not integers"))
    return ValidationResult(is_valid=len(errors) == 0, errors=errors)


def validate_bank_row(row: dict) -> ValidationResult:
    errors = []
    if not str(row.get("bank_reference", "")).strip():
        errors.append(_err("INVALID_ID", "bank_reference is blank"))
    if row.get("bank_status") not in ALLOWED_BANK_STATUS:
        errors.append(_err("INVALID_STATUS", f"unexpected bank_status {row.get('bank_status')}"))
    try:
        amount = int(row.get("credited_amount_paise"))
        if amount < 0:
            errors.append(_err("INVALID_AMOUNT", "credited_amount_paise is negative"))
    except (TypeError, ValueError):
        errors.append(_err("INVALID_AMOUNT", "credited_amount_paise is not an integer"))
    return ValidationResult(is_valid=len(errors) == 0, errors=errors)

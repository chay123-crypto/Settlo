"""
Normalization helpers. Prefer receiving integer paise directly wherever
possible; only convert at an input boundary (e.g. a rupee string from a
legacy source).
"""
from decimal import Decimal, ROUND_HALF_UP


def rupees_to_paise(value) -> int:
    amount = Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return int(amount * 100)


def normalize_id(value) -> str:
    return str(value).strip()


def normalize_currency(value) -> str:
    return str(value).strip().upper()

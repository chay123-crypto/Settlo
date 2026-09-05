"""
Generates a realistic-feeling 200-record synthetic batch.

Unlike generate_synthetic_data.py (which is clean and lab-perfect),
this dataset mimics real merchant data:
  - Indian customer names and realistic product categories
  - Varied realistic transaction amounts (not round numbers)
  - Realistic Razorpay fee structure (2% + 18% GST)
  - Settlement timing variance (T+1 to T+4 days)
  - Some rounding noise in fee/tax calculations
  - More exception variety and higher exception rate
  - Realistic-looking IDs (not sequential test_0001)

NOTE: The pipeline must NEVER read scenario_manifest_realistic.csv.
It is used only by evaluate_realistic.py after the fact.
"""
import random
import sys
import uuid
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

random.seed(99)  # different seed from the clean dataset

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "input"
OUT.mkdir(parents=True, exist_ok=True)

BASE_DATE = datetime(2026, 7, 1)

# ── Realistic Indian customer pool ──────────────────────────────────────────
FIRST_NAMES = [
    "Aarav", "Vivaan", "Aditya", "Vihaan", "Arjun", "Reyansh", "Ayaan",
    "Krishna", "Ishaan", "Shaurya", "Saanvi", "Aanya", "Pari", "Ananya",
    "Aadhya", "Riya", "Aarohi", "Priya", "Diya", "Avni", "Rahul", "Amit",
    "Sneha", "Pooja", "Neha", "Suresh", "Ramesh", "Sunita", "Geeta", "Vijay"
]
LAST_NAMES = [
    "Sharma", "Verma", "Patel", "Singh", "Kumar", "Gupta", "Joshi", "Mehta",
    "Shah", "Yadav", "Malhotra", "Kapoor", "Nair", "Menon", "Iyer", "Reddy",
    "Rao", "Pillai", "Bose", "Chatterjee", "Das", "Ghosh", "Mukherjee"
]

# ── Realistic transaction amounts by category (in paise) ────────────────────
CATEGORIES = {
    "ecommerce_grocery":  (50000,  300000),    # ₹500  - ₹3000
    "ecommerce_clothing": (80000,  800000),    # ₹800  - ₹8000
    "electronics":        (500000, 8000000),   # ₹5000 - ₹80000
    "travel_booking":     (150000, 2500000),   # ₹1500 - ₹25000
    "saas_subscription":  (99900,  999900),    # ₹999  - ₹9999
    "food_delivery":      (20000,  80000),     # ₹200  - ₹800
    "education":          (200000, 3000000),   # ₹2000 - ₹30000
}


def rand_name():
    return f"{random.choice(FIRST_NAMES)} {random.choice(LAST_NAMES)}"


def realistic_fee(gross: int) -> tuple[int, int]:
    """Simulate realistic Razorpay fee with slight rounding noise."""
    # Razorpay standard: 2% + 18% GST on fee
    # Add ±1 paise noise to simulate real rounding behavior
    fee = round(gross * 0.02) + random.choice([-1, 0, 0, 0, 1])
    tax = round(fee * 0.18) + random.choice([-1, 0, 0, 1])
    fee = max(fee, 0)
    tax = max(tax, 0)
    return fee, tax


def rand_gross():
    category = random.choice(list(CATEGORIES.keys()))
    lo, hi = CATEGORIES[category]
    # Use realistic amounts — not perfectly round
    raw = random.randint(lo // 100, hi // 100) * 100
    # Add some paise noise (e.g., ₹1,249.00 not ₹1,200.00)
    noise = random.choice([0, 0, 0, 100, 200, 500, 900, 1900, 4900, 9900])
    return raw + noise


def razorpay_id(prefix: str, n: int) -> str:
    """Realistic-looking Razorpay ID."""
    suffix = uuid.UUID(int=random.getrandbits(128)).hex[:14].upper()
    return f"{prefix}{suffix}"


orders, payments, bank, refunds, manifest = [], [], [], [], []
i = 0


def next_order_id():
    global i
    i += 1
    return f"ORD-{2026070000 + i}"


def settlement_date(payment_dt: datetime) -> datetime:
    """T+1 to T+4 settlement with weekday awareness."""
    lag = random.choices([1, 2, 3, 4], weights=[0.4, 0.35, 0.15, 0.1])[0]
    dt = payment_dt + timedelta(days=lag)
    # Skip weekends (simplistic)
    while dt.weekday() >= 5:
        dt += timedelta(days=1)
    return dt


# ════════════════════════════════════════════════════════════════════════════
# SCENARIO 1 ── Clean exact matches (120 records, 60%)
# ════════════════════════════════════════════════════════════════════════════
for _ in range(120):
    oid = next_order_id()
    gross = rand_gross()
    fee, tax = realistic_fee(gross)
    net = gross - fee - tax
    rorder = razorpay_id("order_", i)
    pay_id = razorpay_id("pay_", i)
    sett_id = razorpay_id("setl_", i)
    cust = rand_name()
    dt = BASE_DATE + timedelta(days=random.randint(0, 45),
                               hours=random.randint(8, 22),
                               minutes=random.randint(0, 59))
    sdt = settlement_date(dt)

    orders.append({
        "merchant_order_id": oid, "razorpay_order_id": rorder,
        "customer_ref": cust, "order_date": dt.date().isoformat(),
        "gross_amount_paise": gross, "currency": "INR", "expected_status": "paid",
    })
    payments.append({
        "payment_id": pay_id, "order_id": rorder, "settlement_id": sett_id,
        "transaction_type": "payment", "payment_date": dt.date().isoformat(),
        "gross_amount_paise": gross, "fee_paise": fee, "tax_paise": tax,
        "net_amount_paise": net, "payment_status": "captured",
    })
    bank.append({
        "bank_reference": f"UTR{random.randint(10**11, 10**12 - 1)}",
        "settlement_id": sett_id, "credit_date": sdt.date().isoformat(),
        "credited_amount_paise": net, "currency": "INR", "bank_status": "credited",
    })
    manifest.append({
        "record_id": oid, "injected_scenario": "exact_match",
        "expected_match_status": "EXACT_MATCH", "expected_exception_type": "",
    })

# ════════════════════════════════════════════════════════════════════════════
# SCENARIO 2 ── Refund-adjusted (12 records, 6%)
# ════════════════════════════════════════════════════════════════════════════
for _ in range(12):
    oid = next_order_id()
    gross = rand_gross()
    fee, tax = realistic_fee(gross)
    net = gross - fee - tax
    rorder = razorpay_id("order_", i)
    pay_id = razorpay_id("pay_", i)
    sett_id = razorpay_id("setl_", i)
    dt = BASE_DATE + timedelta(days=random.randint(0, 45))
    sdt = settlement_date(dt)
    refund_pct = random.choice([0.10, 0.20, 0.25, 0.50])
    refund_amt = round(gross * refund_pct / 100) * 100

    orders.append({
        "merchant_order_id": oid, "razorpay_order_id": rorder,
        "customer_ref": rand_name(), "order_date": dt.date().isoformat(),
        "gross_amount_paise": gross, "currency": "INR", "expected_status": "paid",
    })
    payments.append({
        "payment_id": pay_id, "order_id": rorder, "settlement_id": sett_id,
        "transaction_type": "payment", "payment_date": dt.date().isoformat(),
        "gross_amount_paise": gross, "fee_paise": fee, "tax_paise": tax,
        "net_amount_paise": net, "payment_status": "captured",
    })
    bank.append({
        "bank_reference": f"UTR{random.randint(10**11, 10**12 - 1)}",
        "settlement_id": sett_id, "credit_date": sdt.date().isoformat(),
        "credited_amount_paise": net - refund_amt,
        "currency": "INR", "bank_status": "credited",
    })
    refunds.append({
        "refund_id": razorpay_id("rfnd_", i),
        "payment_id": pay_id,
        "refund_date": (dt + timedelta(days=random.randint(1, 5))).date().isoformat(),
        "refund_amount_paise": refund_amt, "refund_status": "processed",
    })
    manifest.append({
        "record_id": oid, "injected_scenario": "refund_adjusted",
        "expected_match_status": "EXACT_MATCH_AFTER_REFUND", "expected_exception_type": "",
    })

# ════════════════════════════════════════════════════════════════════════════
# SCENARIO 3 ── Fee/Tax mismatch (12 records, 6%)
# ════════════════════════════════════════════════════════════════════════════
for j in range(12):
    oid = next_order_id()
    gross = rand_gross()
    fee, tax = realistic_fee(gross)
    net = gross - fee - tax
    rorder = razorpay_id("order_", i)
    pay_id = razorpay_id("pay_", i)
    sett_id = razorpay_id("setl_", i)
    dt = BASE_DATE + timedelta(days=random.randint(0, 45))
    sdt = settlement_date(dt)

    # Corrupt the fee or tax (realistic: wrong fee plan applied)
    bad_fee, bad_tax = fee, tax
    if j % 2 == 0:
        bad_fee = round(gross * 0.025)   # wrong fee tier
    else:
        bad_tax = round(bad_fee * 0.28)  # wrong GST slab

    orders.append({
        "merchant_order_id": oid, "razorpay_order_id": rorder,
        "customer_ref": rand_name(), "order_date": dt.date().isoformat(),
        "gross_amount_paise": gross, "currency": "INR", "expected_status": "paid",
    })
    payments.append({
        "payment_id": pay_id, "order_id": rorder, "settlement_id": sett_id,
        "transaction_type": "payment", "payment_date": dt.date().isoformat(),
        "gross_amount_paise": gross, "fee_paise": bad_fee, "tax_paise": bad_tax,
        "net_amount_paise": net,  # net still from original — inconsistency!
        "payment_status": "captured",
    })
    bank.append({
        "bank_reference": f"UTR{random.randint(10**11, 10**12 - 1)}",
        "settlement_id": sett_id, "credit_date": sdt.date().isoformat(),
        "credited_amount_paise": net, "currency": "INR", "bank_status": "credited",
    })
    manifest.append({
        "record_id": oid, "injected_scenario": "fee_tax_mismatch",
        "expected_match_status": "FEE_MISMATCH_OR_TAX_MISMATCH",
        "expected_exception_type": "FEE_MISMATCH_OR_TAX_MISMATCH",
    })

# ════════════════════════════════════════════════════════════════════════════
# SCENARIO 4 ── Missing bank credit (10 records, 5%)
# ════════════════════════════════════════════════════════════════════════════
for _ in range(10):
    oid = next_order_id()
    gross = rand_gross()
    fee, tax = realistic_fee(gross)
    net = gross - fee - tax
    rorder = razorpay_id("order_", i)
    pay_id = razorpay_id("pay_", i)
    sett_id = razorpay_id("setl_", i)
    # Set payment_date near today's date so cash forecast projects future inflows
    dt = datetime.now() - timedelta(days=random.randint(0, 2))
    
    orders.append({
        "merchant_order_id": oid, "razorpay_order_id": rorder,
        "customer_ref": rand_name(), "order_date": dt.date().isoformat(),
        "gross_amount_paise": gross, "currency": "INR", "expected_status": "paid",
    })
    payments.append({
        "payment_id": pay_id, "order_id": rorder, "settlement_id": sett_id,
        "transaction_type": "payment", "payment_date": dt.date().isoformat(),
        "gross_amount_paise": gross, "fee_paise": fee, "tax_paise": tax,
        "net_amount_paise": net, "payment_status": "captured",
    })
    # No bank row — settlement not received
    manifest.append({
        "record_id": oid, "injected_scenario": "missing_settlement",
        "expected_match_status": "MISSING_SETTLEMENT",
        "expected_exception_type": "MISSING_SETTLEMENT",
    })

# ════════════════════════════════════════════════════════════════════════════
# SCENARIO 5 ── Duplicate payments (6 records, 3%)
# ════════════════════════════════════════════════════════════════════════════
for _ in range(6):
    oid = next_order_id()
    gross = rand_gross()
    fee, tax = realistic_fee(gross)
    net = gross - fee - tax
    rorder = razorpay_id("order_", i)
    pay_id = razorpay_id("pay_", i)
    sett_id = razorpay_id("setl_", i)
    dt = BASE_DATE + timedelta(days=random.randint(0, 45))
    sdt = settlement_date(dt)

    orders.append({
        "merchant_order_id": oid, "razorpay_order_id": rorder,
        "customer_ref": rand_name(), "order_date": dt.date().isoformat(),
        "gross_amount_paise": gross, "currency": "INR", "expected_status": "paid",
    })
    payments.append({
        "payment_id": pay_id, "order_id": rorder, "settlement_id": sett_id,
        "transaction_type": "payment", "payment_date": dt.date().isoformat(),
        "gross_amount_paise": gross, "fee_paise": fee, "tax_paise": tax,
        "net_amount_paise": net, "payment_status": "captured",
    })
    # Duplicate payment (different pay ID, same order)
    payments.append({
        "payment_id": razorpay_id("pay_", i) + "DUP",
        "order_id": rorder, "settlement_id": sett_id,
        "transaction_type": "payment", "payment_date": dt.date().isoformat(),
        "gross_amount_paise": gross, "fee_paise": fee, "tax_paise": tax,
        "net_amount_paise": net, "payment_status": "captured",
    })
    bank.append({
        "bank_reference": f"UTR{random.randint(10**11, 10**12 - 1)}",
        "settlement_id": sett_id, "credit_date": sdt.date().isoformat(),
        "credited_amount_paise": net, "currency": "INR", "bank_status": "credited",
    })
    manifest.append({
        "record_id": oid, "injected_scenario": "duplicate_payment",
        "expected_match_status": "DUPLICATE_PAYMENT",
        "expected_exception_type": "DUPLICATE_PAYMENT",
    })

# ════════════════════════════════════════════════════════════════════════════
# SCENARIO 6 ── Amount mismatch at bank leg (8 records, 4%)
# ════════════════════════════════════════════════════════════════════════════
for _ in range(8):
    oid = next_order_id()
    gross = rand_gross()
    fee, tax = realistic_fee(gross)
    net = gross - fee - tax
    rorder = razorpay_id("order_", i)
    pay_id = razorpay_id("pay_", i)
    sett_id = razorpay_id("setl_", i)
    dt = BASE_DATE + timedelta(days=random.randint(0, 45))
    sdt = settlement_date(dt)
    # Bank credited a slightly different amount
    discrepancy = random.choice([100, 200, 500, 1000, 2000, -100, -200])

    orders.append({
        "merchant_order_id": oid, "razorpay_order_id": rorder,
        "customer_ref": rand_name(), "order_date": dt.date().isoformat(),
        "gross_amount_paise": gross, "currency": "INR", "expected_status": "paid",
    })
    payments.append({
        "payment_id": pay_id, "order_id": rorder, "settlement_id": sett_id,
        "transaction_type": "payment", "payment_date": dt.date().isoformat(),
        "gross_amount_paise": gross, "fee_paise": fee, "tax_paise": tax,
        "net_amount_paise": net, "payment_status": "captured",
    })
    bank.append({
        "bank_reference": f"UTR{random.randint(10**11, 10**12 - 1)}",
        "settlement_id": sett_id, "credit_date": sdt.date().isoformat(),
        "credited_amount_paise": net + discrepancy,
        "currency": "INR", "bank_status": "credited",
    })
    manifest.append({
        "record_id": oid, "injected_scenario": "amount_mismatch",
        "expected_match_status": "AMOUNT_MISMATCH",
        "expected_exception_type": "AMOUNT_MISMATCH",
    })

# ════════════════════════════════════════════════════════════════════════════
for _ in range(10):
    oid = next_order_id()
    gross = rand_gross()
    fee, tax = realistic_fee(gross)
    net = gross - fee - tax
    rorder = razorpay_id("order_", i)
    pay_id = razorpay_id("pay_", i)
    sett_id = razorpay_id("setl_", i)
    dt = BASE_DATE + timedelta(days=random.randint(0, 30))
    delay = random.randint(7, 15)
    sdt = dt + timedelta(days=delay)

    orders.append({
        "merchant_order_id": oid, "razorpay_order_id": rorder,
        "customer_ref": rand_name(), "order_date": dt.date().isoformat(),
        "gross_amount_paise": gross, "currency": "INR", "expected_status": "paid",
    })
    payments.append({
        "payment_id": pay_id, "order_id": rorder, "settlement_id": sett_id,
        "transaction_type": "payment", "payment_date": dt.date().isoformat(),
        "gross_amount_paise": gross, "fee_paise": fee, "tax_paise": tax,
        "net_amount_paise": net, "payment_status": "captured",
    })
    bank.append({
        "bank_reference": f"UTR{random.randint(10**11, 10**12 - 1)}",
        "settlement_id": sett_id, "credit_date": sdt.date().isoformat(),
        "credited_amount_paise": net, "currency": "INR", "bank_status": "credited",
    })
    manifest.append({
        "record_id": oid, "injected_scenario": "delayed_settlement",
        "expected_match_status": "EXACT_MATCH",
        "expected_exception_type": "DELAYED_SETTLEMENT_FLAG_OPTIONAL",
    })

# ════════════════════════════════════════════════════════════════════════════
# SCENARIO 8 ── Malformed/missing identifiers (8 records, 4%)
# ════════════════════════════════════════════════════════════════════════════
for j in range(8):
    oid = next_order_id()
    gross = rand_gross()
    fee, tax = realistic_fee(gross)
    net = gross - fee - tax
    rorder = razorpay_id("order_", i)
    pay_id = razorpay_id("pay_", i)
    sett_id = razorpay_id("setl_", i)
    dt = BASE_DATE + timedelta(days=random.randint(0, 45))

    order = {
        "merchant_order_id": oid, "razorpay_order_id": rorder,
        "customer_ref": rand_name(), "order_date": dt.date().isoformat(),
        "gross_amount_paise": gross, "currency": "INR", "expected_status": "paid",
    }
    # Inject different types of malformation
    if j % 4 == 0:
        order["razorpay_order_id"] = ""           # blank ID
    elif j % 4 == 1:
        order["gross_amount_paise"] = -gross       # negative amount
    elif j % 4 == 2:
        order["currency"] = "USD"                  # unsupported currency
    else:
        order["order_date"] = "not-a-date"         # bad date

    orders.append(order)
    payments.append({
        "payment_id": pay_id, "order_id": rorder, "settlement_id": sett_id,
        "transaction_type": "payment", "payment_date": dt.date().isoformat(),
        "gross_amount_paise": gross, "fee_paise": fee, "tax_paise": tax,
        "net_amount_paise": net, "payment_status": "captured",
    })
    manifest.append({
        "record_id": oid, "injected_scenario": "malformed_input",
        "expected_match_status": "INPUT_VALIDATION_ERROR",
        "expected_exception_type": "INPUT_VALIDATION_ERROR",
    })

# ════════════════════════════════════════════════════════════════════════════
# SCENARIO 9 ── Ambiguous composite matches (6 records, 3%)
# ════════════════════════════════════════════════════════════════════════════
for _ in range(6):
    oid = next_order_id()
    gross = rand_gross()
    fee, tax = realistic_fee(gross)
    net = gross - fee - tax
    dt = BASE_DATE + timedelta(days=random.randint(0, 45))

    order = {
        "merchant_order_id": oid,
        "razorpay_order_id": f"order_nolink_{i:04d}",  # won't match any payment
        "customer_ref": rand_name(), "order_date": dt.date().isoformat(),
        "gross_amount_paise": gross, "currency": "INR", "expected_status": "paid",
    }
    orders.append(order)

    # Two payments with same amount and nearby date, no order_id link
    for k in range(2):
        pay_id = razorpay_id("pay_", i) + f"_{k}"
        sett_id = razorpay_id("setl_", i) + f"_{k}"
        pdt = dt + timedelta(days=1)
        sdt = settlement_date(pdt)
        payments.append({
            "payment_id": pay_id, "order_id": "",
            "settlement_id": sett_id, "transaction_type": "payment",
            "payment_date": pdt.date().isoformat(),
            "gross_amount_paise": gross, "fee_paise": fee, "tax_paise": tax,
            "net_amount_paise": net, "payment_status": "captured",
        })
        bank.append({
            "bank_reference": f"UTR{random.randint(10**11, 10**12 - 1)}",
            "settlement_id": sett_id, "credit_date": sdt.date().isoformat(),
            "credited_amount_paise": net, "currency": "INR", "bank_status": "credited",
        })
    manifest.append({
        "record_id": oid, "injected_scenario": "ambiguous_composite",
        "expected_match_status": "AMBIGUOUS_MATCH",
        "expected_exception_type": "AMBIGUOUS_MATCH",
    })
    i += 1

# ════════════════════════════════════════════════════════════════════════════
# Write to CSV files
# ════════════════════════════════════════════════════════════════════════════
pd.DataFrame(orders).to_csv(OUT / "orders.csv", index=False)
pd.DataFrame(payments).to_csv(OUT / "razorpay_transactions.csv", index=False)
pd.DataFrame(bank).to_csv(OUT / "bank_settlements.csv", index=False)
pd.DataFrame(refunds if refunds else []).to_csv(OUT / "refunds.csv", index=False)

manifest_path = Path(__file__).resolve().parent / "scenario_manifest.csv"
pd.DataFrame(manifest).to_csv(manifest_path, index=False)

total = len(orders)
print(f"Generated {total} realistic orders across 9 scenario types.")
print(f"  Payments:    {len(payments)}")
print(f"  Bank rows:   {len(bank)}")
print(f"  Refunds:     {len(refunds)}")
print(f"  Manifest:    {len(manifest)} rows -> {manifest_path}")
print()
print("Scenario breakdown:")
sc = pd.DataFrame(manifest)["injected_scenario"].value_counts()
for s, c in sc.items():
    print(f"  {s:<28} {c:>4} records")

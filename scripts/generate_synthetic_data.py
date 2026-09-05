"""
Generates a 100-record synthetic reconciliation batch plus a SEPARATE
ground-truth scenario manifest. The reconciliation engine (backend/) must
NEVER read scenario_manifest.csv -- it exists only for scripts/evaluate.py
to score results against, after the fact.
"""
import random
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

random.seed(42)

ROOT = Path(__file__).resolve().parent.parent
OUT_INPUT = ROOT / "data" / "input"
OUT_INPUT.mkdir(parents=True, exist_ok=True)

BASE_DATE = datetime(2026, 8, 1)

orders, payments, bank, refunds, manifest = [], [], [], [], []

record_counter = 1


def next_id():
    global record_counter
    rid = f"ORDER-{record_counter:04d}"
    record_counter += 1
    return rid


def make_base_records(i, gross=None):
    gross = gross if gross is not None else random.randrange(5000, 250000, 100)
    fee = round(gross * 0.02)
    tax = round(fee * 0.18)
    net = gross - fee - tax
    oid = next_id()
    rorder = f"order_test_{i:04d}"
    pay = f"pay_test_{i:04d}"
    sett = f"setl_test_{i:04d}"
    dt = BASE_DATE + timedelta(days=i % 20)
    order = {
        "merchant_order_id": oid, "razorpay_order_id": rorder,
        "customer_ref": f"CUST-{i:04d}", "order_date": dt.date().isoformat(),
        "gross_amount_paise": gross, "currency": "INR", "expected_status": "paid",
    }
    payment = {
        "payment_id": pay, "order_id": rorder, "settlement_id": sett,
        "transaction_type": "payment", "payment_date": dt.date().isoformat(),
        "gross_amount_paise": gross, "fee_paise": fee, "tax_paise": tax,
        "net_amount_paise": net, "payment_status": "captured",
    }
    bank_row = {
        "bank_reference": f"UTR{i:08d}", "settlement_id": sett,
        "credit_date": (dt + timedelta(days=2)).date().isoformat(),
        "credited_amount_paise": net, "currency": "INR", "bank_status": "credited",
    }
    return order, payment, bank_row, dt, gross, fee, tax, net


i = 1

# 1. Exact complete matches (68)
for _ in range(68):
    order, payment, bank_row, *_ = make_base_records(i)
    orders.append(order); payments.append(payment); bank.append(bank_row)
    manifest.append({"record_id": order["merchant_order_id"], "injected_scenario": "exact_match",
                      "expected_match_status": "EXACT_MATCH", "expected_exception_type": ""})
    i += 1

# 2. Valid refund-adjusted matches (6)
for _ in range(6):
    order, payment, bank_row, dt, gross, fee, tax, net = make_base_records(i)
    refund_amt = round(gross * 0.1)
    payment["net_amount_paise"] = gross - fee - tax  # net before refund, as stored on the payment leg
    bank_row["credited_amount_paise"] = gross - fee - tax - refund_amt
    refunds.append({
        "refund_id": f"rfnd_{i:04d}", "payment_id": payment["payment_id"],
        "refund_date": (dt + timedelta(days=1)).date().isoformat(),
        "refund_amount_paise": refund_amt, "refund_status": "processed",
    })
    orders.append(order); payments.append(payment); bank.append(bank_row)
    manifest.append({"record_id": order["merchant_order_id"], "injected_scenario": "refund_adjusted",
                      "expected_match_status": "EXACT_MATCH_AFTER_REFUND", "expected_exception_type": ""})
    i += 1

# 3. Fee or tax mismatches (6)
for j in range(6):
    order, payment, bank_row, *_ = make_base_records(i)
    if j % 2 == 0:
        payment["fee_paise"] += 500  # fee recorded wrong -> net inconsistent with gross-fee-tax
    else:
        payment["tax_paise"] += 300
    orders.append(order); payments.append(payment); bank.append(bank_row)
    manifest.append({"record_id": order["merchant_order_id"], "injected_scenario": "fee_tax_mismatch",
                      "expected_match_status": "FEE_MISMATCH_OR_TAX_MISMATCH", "expected_exception_type": "FEE_MISMATCH_OR_TAX_MISMATCH"})
    i += 1

# 4. Missing bank credits (5)
for _ in range(5):
    order, payment, bank_row, *_ = make_base_records(i)
    orders.append(order); payments.append(payment)  # bank_row deliberately omitted
    manifest.append({"record_id": order["merchant_order_id"], "injected_scenario": "missing_settlement",
                      "expected_match_status": "MISSING_SETTLEMENT", "expected_exception_type": "MISSING_SETTLEMENT"})
    i += 1

# 5. Duplicate payment or settlement (4)
for j in range(4):
    order, payment, bank_row, *_ = make_base_records(i)
    orders.append(order); payments.append(payment); bank.append(bank_row)
    dup_payment = dict(payment)
    dup_payment["payment_id"] = payment["payment_id"] + "_dup"
    payments.append(dup_payment)
    manifest.append({"record_id": order["merchant_order_id"], "injected_scenario": "duplicate_payment",
                      "expected_match_status": "DUPLICATE_PAYMENT", "expected_exception_type": "DUPLICATE_PAYMENT"})
    i += 1

# 6. Gross/net amount mismatch (4)
for _ in range(4):
    order, payment, bank_row, *_ = make_base_records(i)
    bank_row["credited_amount_paise"] += 1500  # bank credited a different amount than expected
    orders.append(order); payments.append(payment); bank.append(bank_row)
    manifest.append({"record_id": order["merchant_order_id"], "injected_scenario": "amount_mismatch",
                      "expected_match_status": "AMOUNT_MISMATCH", "expected_exception_type": "AMOUNT_MISMATCH"})
    i += 1

# 7. Delayed settlements (3) -- still exact-value, just outside normal timing
for _ in range(3):
    order, payment, bank_row, dt, *_ = make_base_records(i)
    bank_row["credit_date"] = (dt + timedelta(days=15)).date().isoformat()
    orders.append(order); payments.append(payment); bank.append(bank_row)
    manifest.append({"record_id": order["merchant_order_id"], "injected_scenario": "delayed_settlement",
                      "expected_match_status": "EXACT_MATCH", "expected_exception_type": "DELAYED_SETTLEMENT_FLAG_OPTIONAL"})
    i += 1

# 8. Missing or malformed identifiers (2)
for _ in range(2):
    order, payment, bank_row, *_ = make_base_records(i)
    order["razorpay_order_id"] = ""  # malformed
    orders.append(order); payments.append(payment); bank.append(bank_row)
    manifest.append({"record_id": order["merchant_order_id"], "injected_scenario": "malformed_identifier",
                      "expected_match_status": "INPUT_VALIDATION_ERROR", "expected_exception_type": "INPUT_VALIDATION_ERROR"})
    i += 1

# 9. Ambiguous composite candidates (2) -- order id won't match directly;
#    two payment rows share the same amount + nearby date, no order_id link
for _ in range(2):
    gross = random.randrange(5000, 250000, 100)
    fee = round(gross * 0.02)
    tax = round(fee * 0.18)
    net = gross - fee - tax
    oid = next_id()
    dt = BASE_DATE + timedelta(days=i % 20)
    order = {
        "merchant_order_id": oid, "razorpay_order_id": f"order_test_{i:04d}_noexact",
        "customer_ref": f"CUST-{i:04d}", "order_date": dt.date().isoformat(),
        "gross_amount_paise": gross, "currency": "INR", "expected_status": "paid",
    }
    orders.append(order)
    for k in range(2):
        pay_id = f"pay_test_{i:04d}_{k}"
        sett_id = f"setl_test_{i:04d}_{k}"
        payments.append({
            "payment_id": pay_id, "order_id": "",  # no direct order_id link -> forces composite path
            "settlement_id": sett_id, "transaction_type": "payment",
            "payment_date": (dt + timedelta(days=1)).date().isoformat(),
            "gross_amount_paise": gross, "fee_paise": fee, "tax_paise": tax,
            "net_amount_paise": net, "payment_status": "captured",
        })
        bank.append({
            "bank_reference": f"UTR{i:08d}{k}", "settlement_id": sett_id,
            "credit_date": (dt + timedelta(days=3)).date().isoformat(),
            "credited_amount_paise": net, "currency": "INR", "bank_status": "credited",
        })
    manifest.append({"record_id": order["merchant_order_id"], "injected_scenario": "ambiguous_composite",
                      "expected_match_status": "AMBIGUOUS_MATCH", "expected_exception_type": "AMBIGUOUS_MATCH"})
    i += 1

pd.DataFrame(orders).to_csv(OUT_INPUT / "orders.csv", index=False)
pd.DataFrame(payments).to_csv(OUT_INPUT / "razorpay_transactions.csv", index=False)
pd.DataFrame(bank).to_csv(OUT_INPUT / "bank_settlements.csv", index=False)
pd.DataFrame(refunds).to_csv(OUT_INPUT / "refunds.csv", index=False)
# Manifest goes in scripts/, deliberately separate from data/input/, as a
# reminder that the pipeline must never read from that directory for it.
pd.DataFrame(manifest).to_csv(Path(__file__).resolve().parent / "scenario_manifest.csv", index=False)

print(f"Generated {len(orders)} orders, {len(payments)} payments, {len(bank)} bank rows, {len(refunds)} refunds.")
print(f"Ground truth manifest: {len(manifest)} rows -> scripts/scenario_manifest.csv")

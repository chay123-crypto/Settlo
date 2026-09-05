"""
Orchestrates one full batch run: load CSVs -> validate -> reconcile ->
classify -> write results + audit log. This is the module the API and
the evaluation script both call.
"""
import time
import uuid
from pathlib import Path

import pandas as pd

from .audit import AuditLogger
from .classifier import classify
from .matcher import reconcile
from .normalization import normalize_id, normalize_currency
from .validation import validate_order


def _read_csv(path: Path) -> list:
    if not path.exists():
        return []
    df = pd.read_csv(path, dtype=str)
    df = df.where(pd.notnull(df), "")  # NaN -> "" so blank/malformed checks work correctly
    return df.to_dict(orient="records")


def _coerce_int_fields(rows: list, fields: list):
    for row in rows:
        for f in fields:
            if f in row and row[f] not in (None, ""):
                try:
                    row[f] = int(float(row[f]))
                except (TypeError, ValueError):
                    pass
    return rows


def run_batch(data_dir: str = "data/input", output_dir: str = "data/output",
              batch_id: str = None) -> dict:
    data_dir = Path(data_dir)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    batch_id = batch_id or f"batch_{uuid.uuid4().hex[:8]}"
    audit = AuditLogger(str(output_dir / "audit_log.csv"))
    audit.log(batch_id, "-", "BATCH_STARTED")

    started = time.time()

    orders = _read_csv(data_dir / "orders.csv")
    payments = _read_csv(data_dir / "razorpay_transactions.csv")
    settlements = _read_csv(data_dir / "bank_settlements.csv")
    refunds = _read_csv(data_dir / "refunds.csv")

    orders = _coerce_int_fields(orders, ["gross_amount_paise"])
    payments = _coerce_int_fields(
        payments, ["gross_amount_paise", "fee_paise", "tax_paise", "net_amount_paise"]
    )
    settlements = _coerce_int_fields(settlements, ["credited_amount_paise"])
    refunds = _coerce_int_fields(refunds, ["refund_amount_paise"])

    # --- normalize identifiers and currency at the input boundary ---
    for row in orders:
        for id_field in ("merchant_order_id", "razorpay_order_id", "customer_ref"):
            if id_field in row:
                row[id_field] = normalize_id(row[id_field])
        if "currency" in row:
            row["currency"] = normalize_currency(row["currency"])
    for row in payments:
        for id_field in ("payment_id", "order_id", "settlement_id"):
            if id_field in row:
                row[id_field] = normalize_id(row[id_field])
    for row in settlements:
        for id_field in ("bank_reference", "settlement_id"):
            if id_field in row:
                row[id_field] = normalize_id(row[id_field])
        if "currency" in row:
            row["currency"] = normalize_currency(row["currency"])
    for row in refunds:
        for id_field in ("refund_id", "payment_id"):
            if id_field in row:
                row[id_field] = normalize_id(row[id_field])

    results = []
    invalid_count = 0

    for order in orders:
        record_id = order.get("merchant_order_id", "UNKNOWN")

        validation = validate_order(order)
        if not validation.is_valid:
            invalid_count += 1
            results.append({
                "record_id": record_id,
                "status": "INPUT_VALIDATION_ERROR",
                "confidence": 0,
                "rule_code": "SCHEMA_OR_FIELD_ERROR",
                "requires_review": True,
                "exception_code": "INPUT_VALIDATION_ERROR",
                "evidence": "; ".join(validation.errors),
            })
            audit.log(batch_id, record_id, "VALIDATION_FAILED", "; ".join(validation.errors))
            continue

        decision = reconcile(order, payments, settlements, refunds)
        exception_code = classify(decision)

        results.append({
            "record_id": record_id,
            "status": decision.status,
            "confidence": decision.confidence,
            "rule_code": decision.rule_code,
            "requires_review": decision.requires_review,
            "exception_code": exception_code or "",
            "delay_flag": bool(decision.evidence.get("delayed_settlement")),
            "evidence": str(decision.evidence),
        })
        audit.log(batch_id, record_id, "RECONCILED", f"{decision.status} via {decision.rule_code}")

    duration_seconds = round(time.time() - started, 3)

    results_df = pd.DataFrame(results)
    results_path = output_dir / f"{batch_id}_results.csv"
    results_df.to_csv(results_path, index=False)

    exact = sum(1 for r in results if r["status"] in ("EXACT_MATCH", "EXACT_MATCH_AFTER_REFUND"))
    probable = sum(1 for r in results if r["status"] == "PROBABLE_MATCH")
    exceptions = [r for r in results if r["exception_code"]]
    delayed = sum(1 for r in results if r.get("delay_flag"))

    manifest_path = Path(__file__).resolve().parent.parent / "scripts" / "scenario_manifest.csv"
    precision, recall, exception_accuracy = None, None, None
    if manifest_path.exists():
        try:
            manifest_df = pd.read_csv(manifest_path)
            merged = results_df.merge(manifest_df, on="record_id", how="left")
            is_match_prediction = merged["status"].isin(["EXACT_MATCH", "EXACT_MATCH_AFTER_REFUND"])
            is_true_match = merged["expected_match_status"].isin(["EXACT_MATCH", "EXACT_MATCH_AFTER_REFUND"])

            correct_match_predictions = int(((is_match_prediction) & (is_true_match)).sum())
            all_match_predictions = int(is_match_prediction.sum())
            all_true_matches = int(is_true_match.sum())

            precision = round(correct_match_predictions / all_match_predictions, 3) if all_match_predictions else 1.0
            recall = round(correct_match_predictions / all_true_matches, 3) if all_true_matches else 1.0
            
            exception_rows = merged[merged["expected_exception_type"].notna() & (merged["expected_exception_type"] != "")]
            if len(exception_rows) > 0:
                correct_exception = int(exception_rows.apply(
                    lambda r: (r["delay_flag"] == True) if r["expected_exception_type"] == "DELAYED_SETTLEMENT_FLAG_OPTIONAL"
                    else (str(r["exception_code"]) in str(r["expected_exception_type"]).split("_OR_") or str(r["expected_exception_type"]) in str(r["exception_code"])),
                    axis=1
                ).sum())
                exception_accuracy = round(correct_exception / len(exception_rows), 3)
        except Exception:
            pass

    summary = {
        "batch_id": batch_id,
        "total_orders": len(orders),
        "invalid_rows": invalid_count,
        "eligible_records": len(orders) - invalid_count,
        "exact_matches": exact,
        "probable_matches": probable,
        "exception_count": len(exceptions),
        "delayed_settlements": delayed,
        "match_rate": round(exact / max(len(orders), 1), 4),
        "manual_review_rate": round(
            sum(1 for r in results if r["requires_review"]) / max(len(orders), 1), 4
        ),
        "processing_duration_seconds": duration_seconds,
        "results_path": str(results_path),
        "precision": precision,
        "recall": recall,
        "exception_accuracy": exception_accuracy,
    }

    audit.log(batch_id, "-", "BATCH_COMPLETED", str(summary))
    return summary

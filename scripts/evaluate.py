"""
Runs the batch pipeline, then scores the output against the SEPARATE
ground-truth manifest (never read by the pipeline itself). Prints
precision, recall, exception accuracy, match rate, and manual review
rate -- each with visible numerator/denominator, not just a percentage.
"""
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend.pipeline import run_batch  # noqa: E402

MANIFEST_PATH = Path(__file__).resolve().parent / "scenario_manifest.csv"


def main():
    summary = run_batch(data_dir=str(ROOT / "data" / "input"), output_dir=str(ROOT / "data" / "output"))
    results_df = pd.read_csv(summary["results_path"])

    if not MANIFEST_PATH.exists():
        print("No scenario_manifest.csv found -- run scripts/generate_synthetic_data.py first.")
        print("Pipeline summary (no accuracy scoring available):")
        for k, v in summary.items():
            print(f"  {k}: {v}")
        return

    manifest_df = pd.read_csv(MANIFEST_PATH)
    merged = results_df.merge(manifest_df, on="record_id", how="left")

    is_match_prediction = merged["status"].isin(["EXACT_MATCH", "EXACT_MATCH_AFTER_REFUND"])
    is_true_match = merged["expected_match_status"].isin(["EXACT_MATCH", "EXACT_MATCH_AFTER_REFUND"])

    correct_match_predictions = int(((is_match_prediction) & (is_true_match)).sum())
    all_match_predictions = int(is_match_prediction.sum())
    all_true_matches = int(is_true_match.sum())

    precision = correct_match_predictions / all_match_predictions if all_match_predictions else 0
    recall = correct_match_predictions / all_true_matches if all_true_matches else 0

    exception_rows = merged[merged["expected_exception_type"].notna() & (merged["expected_exception_type"] != "")]
    if len(exception_rows) > 0:
        correct_exception = int(
            exception_rows.apply(
                lambda r: str(r["exception_code"]) in str(r["expected_exception_type"]).split("_OR_")
                or str(r["expected_exception_type"]) in str(r["exception_code"]),
                axis=1,
            ).sum()
        )
    else:
        correct_exception = 0
    exception_accuracy = correct_exception / max(len(exception_rows), 1)

    print("=" * 60)
    print(f"BATCH: {summary['batch_id']}")
    print("=" * 60)
    print(f"Total input records:        {summary['total_orders']}")
    print(f"Invalid rows:                {summary['invalid_rows']}")
    print(f"Eligible records:            {summary['eligible_records']}")
    print(f"Exact matches:               {summary['exact_matches']}")
    print(f"Probable matches:            {summary['probable_matches']}")
    print(f"Exception count:             {summary['exception_count']}")
    print("-" * 60)
    print("MATCHING CONFUSION MATRIX:")
    print(f"  True Positive (Match | Match):     {correct_match_predictions}")
    print(f"  False Positive (Match | Non-Match): {all_match_predictions - correct_match_predictions}")
    print(f"  False Negative (Non-Match | Match): {all_true_matches - correct_match_predictions}")
    print(f"  True Negative (Non-Match | Non-Match): {len(merged) - (all_match_predictions + all_true_matches - correct_match_predictions)}")
    print("-" * 60)
    print(f"Precision: {correct_match_predictions}/{all_match_predictions} = {precision:.3f}")
    print(f"Recall:    {correct_match_predictions}/{all_true_matches} = {recall:.3f}")
    print(f"Exception accuracy: {correct_exception}/{len(exception_rows)} = {exception_accuracy:.3f}")
    print(f"Match rate:          {summary['match_rate']:.3f}")
    print(f"Manual review rate:  {summary['manual_review_rate']:.3f}")
    print(f"Processing duration: {summary['processing_duration_seconds']}s")
    
    if len(exception_rows) > 0:
        print("-" * 60)
        print("EXCEPTION ACCURACY BREAKDOWN:")
        # Evaluate accuracy per expected exception type
        grouped = exception_rows.groupby("expected_exception_type")
        for expected_type, group in grouped:
            if expected_type == "DELAYED_SETTLEMENT_FLAG_OPTIONAL":
                correct = int((group["delay_flag"] == True).sum())
            else:
                correct = int(group.apply(
                    lambda r: str(r["exception_code"]) in str(r["expected_exception_type"]).split("_OR_")
                    or str(r["expected_exception_type"]) in str(r["exception_code"]), axis=1
                ).sum())
            total = len(group)
            print(f"  {expected_type}: {correct}/{total} ({correct/total:.2f})")

    print("-" * 60)
    print(f"Full results: {summary['results_path']}")
    print("NOTE: metrics are measured on a synthetic, held-out batch only.")
    print("      They are not a claim about real-world reconciliation accuracy.")


if __name__ == "__main__":
    main()

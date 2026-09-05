"""
Forward cash forecaster.

Projects expected cash inflows over a configurable horizon based on
already-computed reconciliation results and historical settlement timing.
This is pure deterministic arithmetic — no LLM, no ML model.

Design choice: forecasts are computed from batch results, not from
raw data. This means the forecast is always consistent with what the
reconciliation engine decided.
"""
import ast
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

import pandas as pd


def _parse_evidence(evidence_str: str) -> dict:
    """Safely parse the evidence dict stored as a string in results CSV."""
    try:
        return ast.literal_eval(str(evidence_str))
    except (ValueError, SyntaxError, TypeError):
        return {}


def forecast_cash(batch_id: str, output_dir: str = "data/output",
                  horizon_days: int = 14,
                  settlement_sla_days: int = 5) -> dict:
    """Project forward cash position from batch results.

    Categories:
      settled    — EXACT_MATCH / EXACT_MATCH_AFTER_REFUND: money is in the bank.
      expected   — MISSING_SETTLEMENT / PROBABLE_MATCH: likely to arrive
                   within the SLA window, weighted by confidence.
      at_risk    — AMOUNT_MISMATCH / FEE_MISMATCH / TAX_MISMATCH: partial
                   amounts may arrive but the difference is uncertain.
      excluded   — DUPLICATE_*, AMBIGUOUS_MATCH, UNMATCHED, validation
                   errors: not included in the forecast.

    Returns a dict with summary totals and a day-by-day projection table.
    """
    path = Path(output_dir) / f"{batch_id}_results.csv"
    if not path.exists():
        raise FileNotFoundError(f"No results for batch {batch_id}.")
    df = pd.read_csv(path)

    today = date.today()
    horizon_end = today + timedelta(days=horizon_days)

    settled_total = 0
    expected_total = 0
    at_risk_total = 0
    excluded_count = 0

    daily_settled = defaultdict(int)
    daily_expected = defaultdict(int)

    for _, row in df.iterrows():
        evidence = _parse_evidence(row.get("evidence", "{}"))
        status = row["status"]

        if status in ("EXACT_MATCH", "EXACT_MATCH_AFTER_REFUND"):
            amount = int(evidence.get("amount_paise", 0))
            settled_total += amount

        elif status == "MISSING_SETTLEMENT":
            # Expected to settle within SLA window from today
            amount = int(evidence.get("expected_net_paise",
                         evidence.get("amount_paise", 0)))
            if amount > 0:
                # Spread arrival uniformly across the SLA window
                per_day = amount // max(settlement_sla_days, 1)
                for d in range(1, settlement_sla_days + 1):
                    arrival = today + timedelta(days=d)
                    if arrival <= horizon_end:
                        daily_expected[arrival.isoformat()] += per_day
                expected_total += amount

        elif status == "PROBABLE_MATCH":
            amount = int(evidence.get("amount_paise",
                         evidence.get("expected_net_paise", 0)))
            weighted = int(amount * 0.75)  # 75% confidence
            if weighted > 0:
                arrival = today + timedelta(days=settlement_sla_days)
                if arrival <= horizon_end:
                    daily_expected[arrival.isoformat()] += weighted
                expected_total += weighted

        elif status in ("AMOUNT_MISMATCH", "FEE_MISMATCH", "TAX_MISMATCH"):
            expected = abs(int(evidence.get("expected_net_paise", 0)))
            actual = abs(int(evidence.get("actual_credit_paise", 0)))
            at_risk_total += abs(expected - actual)

        else:
            excluded_count += 1

    # Build day-by-day projection table
    projection = []
    cumulative = settled_total
    for d in range(horizon_days + 1):
        day = (today + timedelta(days=d)).isoformat()
        day_expected = daily_expected.get(day, 0)
        cumulative += day_expected
        projection.append({
            "date": day,
            "new_inflow_paise": day_expected,
            "cumulative_paise": cumulative,
        })

    return {
        "batch_id": batch_id,
        "forecast_horizon_days": horizon_days,
        "settlement_sla_days": settlement_sla_days,
        "settled_paise": settled_total,
        "expected_inflow_paise": expected_total,
        "at_risk_paise": at_risk_total,
        "excluded_records": excluded_count,
        "projected_total_paise": settled_total + expected_total,
        "projection": projection,
    }

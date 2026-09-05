"""
Allow-listed, READ-ONLY tools the agent may call. None of these can
modify, approve, refund, or settle anything -- they only read from
already-computed pipeline output.
"""
import ast
from pathlib import Path

import pandas as pd

from .forecaster import forecast_cash


def _load_results(output_dir: str, batch_id: str) -> pd.DataFrame:
    path = Path(output_dir) / f"{batch_id}_results.csv"
    if not path.exists():
        raise FileNotFoundError(f"No results found for batch {batch_id}. Run the batch first.")
    return pd.read_csv(path)


def get_batch_summary(batch_id: str, output_dir: str = "data/output") -> dict:
    df = _load_results(output_dir, batch_id)
    return {
        "batch_id": batch_id,
        "total_records": len(df),
        "exact_matches": int((df["status"].isin(["EXACT_MATCH", "EXACT_MATCH_AFTER_REFUND"])).sum()),
        "probable_matches": int((df["status"] == "PROBABLE_MATCH").sum()),
        "exceptions": int(df["exception_code"].notna().sum() - (df["exception_code"] == "").sum()),
    }


def get_record_details(record_id: str, batch_id: str, output_dir: str = "data/output") -> dict:
    df = _load_results(output_dir, batch_id)
    row = df[df["record_id"] == record_id]
    if row.empty:
        return {"found": False, "record_id": record_id}
    r = row.iloc[0].to_dict()
    return {"found": True, **r}


def list_exceptions(batch_id: str, exception_type: str = None, output_dir: str = "data/output") -> list:
    df = _load_results(output_dir, batch_id)
    subset = df[df["exception_code"].notna() & (df["exception_code"] != "")]
    if exception_type:
        subset = subset[subset["exception_code"] == exception_type]
    return subset.to_dict(orient="records")


def get_unresolved_value(batch_id: str, output_dir: str = "data/output") -> dict:
    df = _load_results(output_dir, batch_id)
    subset = df[df["exception_code"].notna() & (df["exception_code"] != "")]
    total = 0
    for ev in subset["evidence"]:
        try:
            d = ast.literal_eval(str(ev))
            total += abs(int(d.get("expected_net_paise", 0)) - int(d.get("actual_credit_paise", d.get("expected_net_paise", 0))))
        except (ValueError, SyntaxError, TypeError):
            continue
    return {"unresolved_records": len(subset), "unresolved_value_paise": total}


def explain_matching_rule(record_id: str, batch_id: str, output_dir: str = "data/output") -> dict:
    details = get_record_details(record_id, batch_id, output_dir)
    if not details.get("found"):
        return {"explanation": f"No record found with id {record_id} in batch {batch_id}."}
    return {
        "record_id": record_id,
        "decision": details["status"],
        "rule_applied": details["rule_code"],
        "review_required": bool(details["requires_review"]),
        "evidence": details["evidence"],
        "action_executed": "None",
    }


def get_cash_forecast(batch_id: str, horizon_days: int = 14,
                      output_dir: str = "data/output") -> dict:
    """Project forward cash position from batch results."""
    result = forecast_cash(batch_id, output_dir=output_dir,
                           horizon_days=horizon_days)
    # Return summary without the full daily projection (too verbose for agent)
    return {
        "batch_id": result["batch_id"],
        "forecast_horizon_days": result["forecast_horizon_days"],
        "settled_paise": result["settled_paise"],
        "expected_inflow_paise": result["expected_inflow_paise"],
        "at_risk_paise": result["at_risk_paise"],
        "excluded_records": result["excluded_records"],
        "projected_total_paise": result["projected_total_paise"],
        "settled_inr": f"₹{result['settled_paise']/100:,.2f}",
        "projected_total_inr": f"₹{result['projected_total_paise']/100:,.2f}",
    }


TOOL_REGISTRY = {
    "get_batch_summary": get_batch_summary,
    "get_record_details": get_record_details,
    "list_exceptions": list_exceptions,
    "get_unresolved_value": get_unresolved_value,
    "explain_matching_rule": explain_matching_rule,
    "get_cash_forecast": get_cash_forecast,
}

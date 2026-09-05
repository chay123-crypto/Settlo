"""
Append-only audit log. Kept intentionally simple: one CSV row per event.
(A hash-linked tamper-evident chain is a reasonable future upgrade, but
isn't needed to demonstrate the audit-trail concept for a submission.)
"""
import csv
import os
from datetime import datetime, timezone


class AuditLogger:
    def __init__(self, path: str):
        self.path = path
        os.makedirs(os.path.dirname(path), exist_ok=True)
        if not os.path.exists(path):
            with open(path, "w", newline="") as f:
                csv.writer(f).writerow(
                    ["timestamp", "batch_id", "record_id", "event_type", "detail"]
                )

    def log(self, batch_id: str, record_id: str, event_type: str, detail: str = ""):
        with open(self.path, "a", newline="") as f:
            csv.writer(f).writerow(
                [datetime.now(timezone.utc).isoformat(), batch_id, record_id, event_type, detail]
            )

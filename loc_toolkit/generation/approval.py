from __future__ import annotations

from typing import Dict, Tuple


def bucket_row(*, generation_status: str, validator_status: str) -> Tuple[str, bool]:
    if generation_status != "ok":
        return "manual_review_needed_rows", False
    if validator_status != "pass":
        return "rejected_rows", False
    return "accepted_rows", True


def summary_from_buckets(report: Dict[str, object]) -> Dict[str, int]:
    return {
        "total_rows": len(report["rows"]),
        "accepted_count": len(report["accepted_rows"]),
        "rejected_count": len(report["rejected_rows"]),
        "manual_review_needed_count": len(report["manual_review_needed_rows"]),
    }

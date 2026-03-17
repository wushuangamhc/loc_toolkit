from __future__ import annotations

from typing import Dict, List


def build_tm(report: Dict[str, object]) -> Dict[str, object]:
    locale_pair = None
    rows: List[Dict[str, object]] = []
    target_locale = report.get("scope", {}).get("target_locale")
    for row in report.get("accepted_rows", []):
        locale_pair = f"{row['locale']}->{target_locale}" if target_locale else None
        rows.append(
            {
                "source": row["source_text"],
                "target": row["candidate_text"],
                "file": row["file"],
                "key": row["key"],
                "locale_pair": locale_pair,
                "status": "accepted",
            }
        )
    return {"rows": rows, "locale_pair": locale_pair}

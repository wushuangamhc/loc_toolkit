from __future__ import annotations

import re
from typing import Dict, List


SEMANTIC_TAG_RE = re.compile(r"<([A-Za-z_][A-Za-z0-9_]*):([^<>]+?)/>")


def build_glossary(report: Dict[str, object]) -> Dict[str, object]:
    rows: List[Dict[str, object]] = []
    seen = set()
    target_locale = report.get("scope", {}).get("target_locale")
    for row in report.get("accepted_rows", []):
        source = row["source_text"]
        target = row["candidate_text"]
        if len(source) <= 12 and "<" not in source and "{" not in source and "%" not in source:
            marker = ("ui", source, target)
            if marker not in seen:
                seen.add(marker)
                rows.append(
                    {
                        "term": source,
                        "translation": target,
                        "file": row["file"],
                        "key": row["key"],
                        "locale_pair": f"{row['locale']}->{target_locale}",
                        "confidence": 0.7,
                        "confirmed": False,
                        "source_type": "accepted_short_ui",
                    }
                )
        for match in SEMANTIC_TAG_RE.finditer(source):
            identifier = match.group(1)
            label = match.group(2)
            marker = ("semantic", identifier, label)
            if marker not in seen:
                seen.add(marker)
                rows.append(
                    {
                        "term": identifier,
                        "translation": label,
                        "file": row["file"],
                        "key": row["key"],
                        "locale_pair": f"{row['locale']}->{target_locale}",
                        "confidence": 0.9,
                        "confirmed": False,
                        "source_type": "semantic_tag_source",
                    }
                )
    return {"rows": rows}

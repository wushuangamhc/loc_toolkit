from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from workflow_config import WorkflowConfig
from workflow_shared import (
    CandidateGenerator,
    OpenAIResponsesCandidateGenerator,
    base_report_schema,
    build_candidate_prompt,
    build_source_manifest,
    collect_source_entries,
    process_entry,
)


def run_full_translation(
    *,
    config: Optional[WorkflowConfig] = None,
    candidate_generator: Optional[CandidateGenerator] = None,
) -> Dict[str, Any]:
    config = config or WorkflowConfig()
    candidate_generator = candidate_generator or OpenAIResponsesCandidateGenerator(model=config.model)
    entries = collect_source_entries(config)

    rows: List[Dict[str, Any]] = []
    accepted_rows: List[Dict[str, Any]] = []
    rejected_rows: List[Dict[str, Any]] = []
    manual_review_needed_rows: List[Dict[str, Any]] = []

    for entry in entries:
        bucket, row = process_entry(entry, candidate_generator)
        rows.append(row)
        if bucket == "accepted":
            accepted_rows.append(row)
        elif bucket == "rejected":
            rejected_rows.append(row)
        else:
            manual_review_needed_rows.append(row)

    manifest = build_source_manifest(entries)
    return {
        "workflow": "full_initial_translation",
        "scope": {
            "locale": config.locale,
            "file_paths": [str(path) for path in config.file_paths],
            "max_rows": config.max_rows,
            "max_rows_per_file": config.max_rows_per_file,
            "english_locale_policy": config.english_locale_policy,
            "writeback_enabled": False,
            "candidate_generation_mode": "real_model_in_memory_only",
        },
        "prompt_structure": {
            "system": (
                "Translate Simplified Chinese UI/system strings into concise English while preserving "
                "all protected tokens exactly. Return structured JSON only."
            ),
            "user_fields": ["task", "scope", "constraints", "locale", "file", "key", "source"],
            "output_json": {
                "translation": "string",
                "needs_manual_review": "boolean",
                "review_reason": "string",
            },
            "example_prompt_preview": build_candidate_prompt(entry=entries[0]) if entries else None,
        },
        "report_schema": base_report_schema(),
        "summary": {
            "total_rows": len(rows),
            "accepted_count": len(accepted_rows),
            "rejected_count": len(rejected_rows),
            "manual_review_needed_count": len(manual_review_needed_rows),
        },
        "source_manifest": manifest,
        "rows": rows,
        "accepted_rows": accepted_rows,
        "rejected_rows": rejected_rows,
        "manual_review_needed_rows": manual_review_needed_rows,
    }


def main() -> None:
    print(json.dumps(run_full_translation(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

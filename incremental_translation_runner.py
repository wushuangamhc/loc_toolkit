from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Tuple

from workflow_config import WorkflowConfig
from workflow_shared import (
    CandidateGenerator,
    OpenAIResponsesCandidateGenerator,
    SourceEntry,
    base_report_schema,
    build_candidate_prompt,
    build_source_manifest,
    collect_source_entries,
    process_entry,
)


def diff_source_manifest(
    baseline_manifest: Dict[str, Dict[str, str]],
    current_manifest: Dict[str, Dict[str, str]],
) -> Dict[str, List[Dict[str, Any]]]:
    added: List[Dict[str, Any]] = []
    changed: List[Dict[str, Any]] = []
    removed: List[Dict[str, Any]] = []
    unchanged: List[Dict[str, Any]] = []

    all_files = sorted(set(baseline_manifest) | set(current_manifest))
    for file_path in all_files:
        baseline_keys = baseline_manifest.get(file_path, {})
        current_keys = current_manifest.get(file_path, {})
        all_keys = sorted(set(baseline_keys) | set(current_keys))
        for key in all_keys:
            baseline_value = baseline_keys.get(key)
            current_value = current_keys.get(key)
            if baseline_value is None and current_value is not None:
                added.append({"file": file_path, "key": key, "source_text": current_value})
            elif baseline_value is not None and current_value is None:
                removed.append({"file": file_path, "key": key, "previous_source_text": baseline_value})
            elif baseline_value != current_value:
                changed.append(
                    {
                        "file": file_path,
                        "key": key,
                        "previous_source_text": baseline_value,
                        "source_text": current_value,
                    }
                )
            else:
                unchanged.append({"file": file_path, "key": key, "source_text": current_value})

    return {
        "added": added,
        "changed": changed,
        "removed": removed,
        "unchanged": unchanged,
    }


def _build_incremental_entries(
    current_entries: List[SourceEntry],
    diff: Dict[str, List[Dict[str, Any]]],
) -> Tuple[List[SourceEntry], Dict[Tuple[str, str], Dict[str, Any]]]:
    changed_lookup: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for item in diff["added"] + diff["changed"]:
        changed_lookup[(item["file"], item["key"])] = item

    work_entries = [
        entry for entry in current_entries if (entry.file_path, entry.key) in changed_lookup
    ]
    return work_entries, changed_lookup


def run_incremental_translation(
    *,
    baseline_manifest: Dict[str, Dict[str, str]],
    config: Optional[WorkflowConfig] = None,
    candidate_generator: Optional[CandidateGenerator] = None,
) -> Dict[str, Any]:
    config = config or WorkflowConfig()
    candidate_generator = candidate_generator or OpenAIResponsesCandidateGenerator(model=config.model)
    current_entries = collect_source_entries(config)
    current_manifest = build_source_manifest(current_entries)
    diff = diff_source_manifest(baseline_manifest, current_manifest)
    work_entries, changed_lookup = _build_incremental_entries(current_entries, diff)

    rows: List[Dict[str, Any]] = []
    accepted_rows: List[Dict[str, Any]] = []
    rejected_rows: List[Dict[str, Any]] = []
    manual_review_needed_rows: List[Dict[str, Any]] = []

    for entry in work_entries:
        bucket, row = process_entry(entry, candidate_generator)
        change_meta = changed_lookup[(entry.file_path, entry.key)]
        row["change_type"] = "added" if "previous_source_text" not in change_meta else "changed"
        row["previous_source_text"] = change_meta.get("previous_source_text")
        rows.append(row)
        if bucket == "accepted":
            accepted_rows.append(row)
        elif bucket == "rejected":
            rejected_rows.append(row)
        else:
            manual_review_needed_rows.append(row)

    return {
        "workflow": "incremental_translation_maintenance",
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
                "Translate changed or newly added Simplified Chinese UI/system strings into concise English "
                "while preserving all protected tokens exactly. Return structured JSON only."
            ),
            "user_fields": ["task", "scope", "constraints", "locale", "file", "key", "source"],
            "output_json": {
                "translation": "string",
                "needs_manual_review": "boolean",
                "review_reason": "string",
            },
            "example_prompt_preview": build_candidate_prompt(entry=work_entries[0]) if work_entries else None,
        },
        "report_schema": {
            **base_report_schema(),
            "change_type": "added | changed",
            "previous_source_text": "nullable prior schinese source text for changed rows",
        },
        "diff_summary": {
            "added_count": len(diff["added"]),
            "changed_count": len(diff["changed"]),
            "removed_count": len(diff["removed"]),
            "unchanged_count": len(diff["unchanged"]),
        },
        "removed_source_rows": diff["removed"],
        "current_source_manifest": current_manifest,
        "rows": rows,
        "accepted_rows": accepted_rows,
        "rejected_rows": rejected_rows,
        "manual_review_needed_rows": manual_review_needed_rows,
    }


def main() -> None:
    print(
        json.dumps(
            run_incremental_translation(baseline_manifest={}),
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()

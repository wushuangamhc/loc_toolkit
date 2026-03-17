from __future__ import annotations

from pathlib import Path
from typing import Dict, Iterable, List, Optional

from loc_toolkit.artifacts.glossary_builder import build_glossary
from loc_toolkit.artifacts.tm_builder import build_tm
from loc_toolkit.config.models import ProjectConfig
from loc_toolkit.core.protected_tokens import extract_protected_tokens
from loc_toolkit.core.validator import compare_protected_tokens
from loc_toolkit.core.vdf_reader import collect_source_files, read_vdf_tokens
from loc_toolkit.core.vdf_writer import source_key_count, write_translated_vdf
from loc_toolkit.generation.approval import summary_from_buckets
from loc_toolkit.generation.models import CodexExecGenerator


LENGTH_THRESHOLDS = {
    "english": {"factor": 3.0, "extra": 12, "floor": 24},
    "russian": {"factor": 3.5, "extra": 16, "floor": 28},
    "schinese": {"factor": 2.0, "extra": 8, "floor": 16},
}


def make_generator(config: ProjectConfig, override=None):
    return override or CodexExecGenerator(config.codex, str(config.project_root))


def make_entry(*, config: ProjectConfig, file_path: Path, key: str, source_text: str) -> Dict[str, str]:
    return {
        "file": str(file_path),
        "locale": config.source_locale,
        "key": key,
        "source_text": source_text,
    }


def collect_entries(config: ProjectConfig, source_files: Optional[Iterable[Path]] = None) -> List[Dict[str, str]]:
    entries: List[Dict[str, str]] = []
    files = list(source_files) if source_files is not None else collect_source_files(config)
    for file_path in files:
        token_map = read_vdf_tokens(file_path)
        per_file = 0
        for key, source_text in token_map.items():
            entries.append(make_entry(config=config, file_path=file_path, key=key, source_text=source_text))
            per_file += 1
            if config.max_rows_per_file and per_file >= config.max_rows_per_file:
                break
            if config.max_rows and len(entries) >= config.max_rows:
                return entries
    return entries


def base_report(config: ProjectConfig, workflow: str) -> Dict[str, object]:
    return {
        "workflow": workflow,
        "scope": {
            "project_root": str(config.project_root),
            "source_locale": config.source_locale,
            "target_locale": config.target_locale,
            "model": config.model,
            "approval_policy": config.approval_policy,
            "english_locale_policy": "excluded_as_low_confidence_machine_translated_noise",
            "writeback_enabled": config.writeback_enabled,
        },
        "report_schema": {
            "file": "absolute path to source VDF",
            "locale": "source locale",
            "key": "token key",
            "source_text": "source string",
            "candidate_text": "in-memory candidate or null",
            "generator_status": "ok | manual_review | skipped_preflight",
            "validator_status": "pass | fail | skipped",
            "error_codes": "deterministic protected-token validation error codes",
            "manual_review_reason": "nullable explanation",
            "accepted": "true only when validator_status is pass",
            "model": "generator model name"
        },
        "rows": [],
        "accepted_rows": [],
        "rejected_rows": [],
        "manual_review_needed_rows": [],
        "writeback": {
            "written_files": [],
            "skipped_files": [],
        },
    }


def _append_row(report: Dict[str, object], bucket_name: str, row: Dict[str, object]) -> None:
    report["rows"].append(row)
    report[bucket_name].append(row)


def _visible_text_length(text: str) -> int:
    extracted = extract_protected_tokens(text)
    visible_parts: List[str] = []
    cursor = 0
    for span in extracted["spans"]:
        start = span["start"]
        if start > cursor:
            visible_parts.append(text[cursor:start])
        cursor = span["end"]
    if cursor < len(text):
        visible_parts.append(text[cursor:])
    visible_text = "".join(visible_parts)
    return len("".join(ch for ch in visible_text if not ch.isspace()))


def _length_review_reason(source_text: str, candidate_text: str, target_locale: str) -> Optional[str]:
    source_len = _visible_text_length(source_text)
    candidate_len = _visible_text_length(candidate_text)
    if candidate_len <= 0:
        return None
    rule = LENGTH_THRESHOLDS.get(target_locale, LENGTH_THRESHOLDS["english"])
    threshold = max(rule["floor"], int(source_len * rule["factor"]), source_len + rule["extra"])
    if candidate_len > threshold:
        return (
            f"candidate visible text length {candidate_len} exceeds review threshold {threshold} "
            f"for target locale {target_locale}"
        )
    return None


def _finalize_writeback(report: Dict[str, object], config: ProjectConfig) -> None:
    if not config.writeback_enabled:
        return

    rows_by_file: Dict[str, List[Dict[str, object]]] = {}
    for row in report["rows"]:
        rows_by_file.setdefault(row["file"], []).append(row)

    for file_path_str, rows in sorted(rows_by_file.items()):
        source_file = Path(file_path_str)
        accepted_rows = [row for row in rows if row["accepted"]]
        if len(accepted_rows) != len(rows):
            report["writeback"]["skipped_files"].append(
                {
                    "source_file": file_path_str,
                    "target_file": str((config.project_root / config.target_locale / source_file.relative_to(config.source_root)).resolve()),
                    "reason": "file has rejected or manual-review rows",
                }
            )
            continue
        if len(rows) != source_key_count(source_file):
            report["writeback"]["skipped_files"].append(
                {
                    "source_file": file_path_str,
                    "target_file": str((config.project_root / config.target_locale / source_file.relative_to(config.source_root)).resolve()),
                    "reason": "partial file run; not all source keys were processed",
                }
            )
            continue

        source_tokens = read_vdf_tokens(source_file)
        translated_tokens = {key: row["candidate_text"] for key, row in ((row["key"], row) for row in accepted_rows)}
        ordered_tokens = {key: translated_tokens[key] for key in source_tokens if key in translated_tokens}
        if len(ordered_tokens) != len(source_tokens):
            report["writeback"]["skipped_files"].append(
                {
                    "source_file": file_path_str,
                    "target_file": str((config.project_root / config.target_locale / source_file.relative_to(config.source_root)).resolve()),
                    "reason": "accepted rows do not cover all source keys",
                }
            )
            continue

        target_file = write_translated_vdf(config, source_file, ordered_tokens)
        report["writeback"]["written_files"].append(
            {
                "source_file": file_path_str,
                "target_file": str(target_file),
                "row_count": len(ordered_tokens),
            }
        )


def process_entries(report: Dict[str, object], entries: Iterable[Dict[str, str]], config: ProjectConfig, generator) -> Dict[str, object]:
    for entry in entries:
        warnings = extract_protected_tokens(entry["source_text"])["warnings"]
        if warnings:
            row = {
                **entry,
                "candidate_text": None,
                "generator_status": "skipped_preflight",
                "validator_status": "skipped",
                "error_codes": [],
                "manual_review_reason": "; ".join(warnings),
                "accepted": False,
                "model": config.model,
            }
            _append_row(report, "manual_review_needed_rows", row)
            continue

        generation = generator.generate(entry=entry, model=config.model, target_locale=config.target_locale)
        if generation["status"] != "ok" or not generation.get("candidate_text"):
            row = {
                **entry,
                "candidate_text": generation.get("candidate_text"),
                "generator_status": generation["status"],
                "validator_status": "skipped",
                "error_codes": [],
                "manual_review_reason": generation.get("generation_error"),
                "accepted": False,
                "model": generation.get("model", config.model),
            }
            _append_row(report, "manual_review_needed_rows", row)
            continue

        candidate_text = generation["candidate_text"]
        comparison = compare_protected_tokens(entry["source_text"], candidate_text)
        row = {
            **entry,
            "candidate_text": candidate_text,
            "generator_status": "ok",
            "validator_status": comparison["status"],
            "error_codes": [error["code"] for error in comparison["errors"]],
            "manual_review_reason": None,
            "accepted": comparison["status"] == "pass",
            "model": generation.get("model", config.model),
        }
        if comparison["status"] != "pass":
            _append_row(report, "rejected_rows", row)
            continue

        length_reason = _length_review_reason(entry["source_text"], candidate_text, config.target_locale)
        if length_reason:
            row["error_codes"] = ["LENGTH_REVIEW_REQUIRED"]
            row["manual_review_reason"] = length_reason
            row["accepted"] = False
            _append_row(report, "manual_review_needed_rows", row)
            continue

        _append_row(report, "accepted_rows", row)

    report["summary"] = summary_from_buckets(report)
    _finalize_writeback(report, config)
    if config.tm.enabled:
        report["tm_artifact"] = build_tm(report)
    if config.glossary.enabled:
        report["glossary_artifact"] = build_glossary(report)
    return report

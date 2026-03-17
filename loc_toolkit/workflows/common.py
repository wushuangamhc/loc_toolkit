from __future__ import annotations

from pathlib import Path
from typing import Dict, Iterable, List, Optional

from loc_toolkit.artifacts.glossary_builder import build_glossary
from loc_toolkit.artifacts.tm_builder import build_tm
from loc_toolkit.config.models import ProjectConfig
from loc_toolkit.core.protected_tokens import extract_protected_tokens
from loc_toolkit.core.validator import compare_protected_tokens
from loc_toolkit.core.vdf_reader import collect_source_files, read_vdf_tokens
from loc_toolkit.generation.approval import bucket_row, summary_from_buckets
from loc_toolkit.generation.models import CodexExecGenerator


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
            "writeback_enabled": False,
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
    }


def _append_row(report: Dict[str, object], bucket_name: str, row: Dict[str, object]) -> None:
    report["rows"].append(row)
    report[bucket_name].append(row)


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
        bucket_name, row["accepted"] = bucket_row(generation_status="ok", validator_status=comparison["status"])
        _append_row(report, bucket_name, row)

    report["summary"] = summary_from_buckets(report)
    if config.tm.enabled:
        report["tm_artifact"] = build_tm(report)
    if config.glossary.enabled:
        report["glossary_artifact"] = build_glossary(report)
    return report

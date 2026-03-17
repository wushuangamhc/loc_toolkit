from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Protocol, Tuple

from compare_protected_tokens import compare_protected_tokens
from protected_tokens import extract_protected_tokens
from workflow_config import WorkflowConfig


TOKENS_BLOCK_START_RE = re.compile(r'^\s*"Tokens"\s*$')
KV_RE = re.compile(r'^\s*"(?P<key>[^"]+)"\s*"(?P<value>.*)"\s*(?://.*)?$')


@dataclass(frozen=True)
class SourceEntry:
    file_path: str
    locale: str
    key: str
    source_text: str


class CandidateGenerator(Protocol):
    def generate(self, *, entry: SourceEntry) -> Dict[str, Any]:
        ...


class OpenAIResponsesCandidateGenerator:
    def __init__(
        self,
        *,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        timeout_seconds: int = 30,
    ) -> None:
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY")
        self.model = model or os.environ.get("OPENAI_MODEL") or model or "gpt-4.1-mini"
        self.timeout_seconds = timeout_seconds

    def generate(self, *, entry: SourceEntry) -> Dict[str, Any]:
        if not self.api_key:
            return {
                "status": "manual_review",
                "candidate_text": None,
                "generation_error": "OPENAI_API_KEY is not set.",
                "model": self.model,
                "raw_response": None,
            }

        prompt = build_candidate_prompt(entry=entry)
        payload = {
            "model": self.model,
            "input": [
                {
                    "role": "system",
                    "content": [
                        {
                            "type": "input_text",
                            "text": (
                                "You translate Simplified Chinese game UI or system localization strings into concise, "
                                "natural English. Preserve all protected tokens exactly. Return structured JSON only."
                            ),
                        }
                    ],
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": prompt,
                        }
                    ],
                },
            ],
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "translation_candidate",
                    "schema": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "translation": {"type": "string"},
                            "needs_manual_review": {"type": "boolean"},
                            "review_reason": {"type": "string"},
                        },
                        "required": ["translation", "needs_manual_review", "review_reason"],
                    },
                }
            },
        }

        request = urllib.request.Request(
            "https://api.openai.com/v1/responses",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                body = response.read().decode("utf-8")
        except urllib.error.URLError as exc:
            return {
                "status": "manual_review",
                "candidate_text": None,
                "generation_error": f"OpenAI request failed: {exc}",
                "model": self.model,
                "raw_response": None,
            }

        parsed_body = json.loads(body)
        output_text = extract_output_text(parsed_body)
        if output_text is None:
            return {
                "status": "manual_review",
                "candidate_text": None,
                "generation_error": "Could not extract structured output text from OpenAI response.",
                "model": self.model,
                "raw_response": parsed_body,
            }

        try:
            candidate_payload = json.loads(output_text)
        except json.JSONDecodeError as exc:
            return {
                "status": "manual_review",
                "candidate_text": None,
                "generation_error": f"Model returned non-JSON output: {exc}",
                "model": self.model,
                "raw_response": output_text,
            }

        if candidate_payload.get("needs_manual_review"):
            return {
                "status": "manual_review",
                "candidate_text": candidate_payload.get("translation"),
                "generation_error": candidate_payload.get("review_reason") or "Model requested manual review.",
                "model": self.model,
                "raw_response": parsed_body,
            }

        return {
            "status": "ok",
            "candidate_text": candidate_payload.get("translation"),
            "generation_error": None,
            "model": self.model,
            "raw_response": parsed_body,
        }


def extract_output_text(response_payload: Dict[str, Any]) -> Optional[str]:
    if isinstance(response_payload.get("output_text"), str):
        return response_payload["output_text"]
    for item in response_payload.get("output", []):
        for content in item.get("content", []):
            if content.get("type") == "output_text" and isinstance(content.get("text"), str):
                return content["text"]
    return None


def build_candidate_prompt(*, entry: SourceEntry) -> str:
    return (
        "Task: translate one Simplified Chinese localization string into concise English.\n"
        "Scope:\n"
        "- low-risk UI/system text only\n"
        "- no lore expansion\n"
        "- no style rewriting beyond natural English phrasing\n"
        "Constraints:\n"
        "- preserve all protected tokens exactly\n"
        "- keep placeholders, tags, markup, and literal-percent sequences unchanged\n"
        "- english locale files are unusable machine-translated noise and must not be used as truth\n"
        "- if the string is ambiguous or unsafe, set needs_manual_review=true\n"
        "- return JSON only\n"
        f"Locale: {entry.locale}\n"
        f"File: {entry.file_path}\n"
        f"Key: {entry.key}\n"
        f"Source: {entry.source_text}\n"
    )


def read_vdf_tokens(file_path: Path) -> Dict[str, str]:
    text = file_path.read_text(encoding="utf-8")
    tokens_started = False
    brace_depth = 0
    tokens: Dict[str, str] = {}

    for line in text.splitlines():
        if not tokens_started:
            if TOKENS_BLOCK_START_RE.match(line):
                tokens_started = True
            continue

        brace_depth += line.count("{")
        brace_depth -= line.count("}")

        match = KV_RE.match(line)
        if match:
            tokens[match.group("key")] = match.group("value")

        if tokens_started and brace_depth < 0:
            break

    return tokens


def collect_source_entries(config: WorkflowConfig) -> List[SourceEntry]:
    entries: List[SourceEntry] = []
    for file_path in config.file_paths:
        if not file_path.exists():
            continue
        token_map = read_vdf_tokens(file_path)
        per_file_count = 0
        for key, value in token_map.items():
            if per_file_count >= config.max_rows_per_file or len(entries) >= config.max_rows:
                break
            entries.append(
                SourceEntry(
                    file_path=str(file_path),
                    locale=config.locale,
                    key=key,
                    source_text=value,
                )
            )
            per_file_count += 1
        if len(entries) >= config.max_rows:
            break
    return entries


def build_source_manifest(entries: Iterable[SourceEntry]) -> Dict[str, Dict[str, str]]:
    manifest: Dict[str, Dict[str, str]] = {}
    for entry in entries:
        manifest.setdefault(entry.file_path, {})[entry.key] = entry.source_text
    return manifest


def preflight_entry(entry: SourceEntry) -> List[str]:
    extraction = extract_protected_tokens(entry.source_text)
    return list(extraction["warnings"])


def validate_candidate(entry: SourceEntry, candidate_text: str) -> Dict[str, Any]:
    return compare_protected_tokens(entry.source_text, candidate_text)


def process_entry(
    entry: SourceEntry,
    candidate_generator: CandidateGenerator,
) -> Tuple[str, Dict[str, Any]]:
    preflight_warnings = preflight_entry(entry)
    if preflight_warnings:
        return (
            "manual_review",
            {
                "file": entry.file_path,
                "locale": entry.locale,
                "key": entry.key,
                "source_text": entry.source_text,
                "candidate_text": None,
                "generator_status": "skipped_preflight",
                "validator_status": "skipped",
                "error_codes": [],
                "manual_review_reason": "; ".join(preflight_warnings),
                "accepted": False,
                "model": None,
            },
        )

    generation = candidate_generator.generate(entry=entry)
    if generation["status"] != "ok" or not generation.get("candidate_text"):
        return (
            "manual_review",
            {
                "file": entry.file_path,
                "locale": entry.locale,
                "key": entry.key,
                "source_text": entry.source_text,
                "candidate_text": generation.get("candidate_text"),
                "generator_status": generation["status"],
                "validator_status": "skipped",
                "error_codes": [],
                "manual_review_reason": generation.get("generation_error"),
                "accepted": False,
                "model": generation.get("model"),
            },
        )

    candidate_text = generation["candidate_text"]
    comparison = validate_candidate(entry, candidate_text)
    error_codes = [error["code"] for error in comparison["errors"]]
    row = {
        "file": entry.file_path,
        "locale": entry.locale,
        "key": entry.key,
        "source_text": entry.source_text,
        "candidate_text": candidate_text,
        "generator_status": generation["status"],
        "validator_status": comparison["status"],
        "error_codes": error_codes,
        "manual_review_reason": None,
        "accepted": comparison["status"] == "pass",
        "model": generation.get("model"),
    }
    return ("accepted" if row["accepted"] else "rejected", row)


def base_report_schema() -> Dict[str, str]:
    return {
        "file": "absolute path to the sampled schinese VDF",
        "locale": "source locale, always schinese for production input",
        "key": "localization token key",
        "source_text": "original schinese value",
        "candidate_text": "in-memory model-generated candidate or null",
        "generator_status": "ok | manual_review | skipped_preflight | source_missing",
        "validator_status": "pass | fail | skipped",
        "error_codes": "list of deterministic protected-token validator error codes",
        "manual_review_reason": "nullable explanation for generator or preflight escalation",
        "accepted": "true only when validator_status is pass",
        "model": "model used for generation, nullable when not invoked",
    }

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Protocol

from compare_protected_tokens import compare_protected_tokens


TOKENS_BLOCK_START_RE = re.compile(r'^\s*"Tokens"\s*$')
KV_RE = re.compile(r'^\s*"(?P<key>[^"]+)"\s*"(?P<value>.*)"\s*(?://.*)?$')

DEFAULT_FILE = Path(r"D:\_project\c1\c1\content\c1\localization\schinese\hud\ui.vdf")
DEFAULT_KEYS = [
    "Popup_Title_Common_Tips",
    "Popup_Button_Cancel",
    "Popup_Button_Confirm",
    "mail_timeout",
    "refresh_count",
    "talent_reset",
]


class CandidateGenerator(Protocol):
    def generate(self, *, key: str, source: str) -> Dict[str, Any]:
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
        self.model = model or os.environ.get("OPENAI_MODEL", "gpt-4.1-mini")
        self.timeout_seconds = timeout_seconds

    def generate(self, *, key: str, source: str) -> Dict[str, Any]:
        if not self.api_key:
            return {
                "status": "manual_review",
                "candidate_text": None,
                "generation_error": "OPENAI_API_KEY is not set.",
                "model": self.model,
                "raw_response": None,
            }

        prompt = build_candidate_prompt(key=key, source=source)
        payload = {
            "model": self.model,
            "input": [
                {
                    "role": "system",
                    "content": [
                        {
                            "type": "input_text",
                            "text": (
                                "You translate Simplified Chinese game UI strings into concise natural English. "
                                "Preserve all protected tokens exactly, including placeholders, tags, markup, "
                                "and literal trailing percent patterns. Return JSON only."
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
        output_text = _extract_output_text(parsed_body)
        if output_text is None:
            return {
                "status": "manual_review",
                "candidate_text": None,
                "generation_error": "Could not extract text output from OpenAI response.",
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


def _extract_output_text(response_payload: Dict[str, Any]) -> Optional[str]:
    if isinstance(response_payload.get("output_text"), str):
        return response_payload["output_text"]

    for item in response_payload.get("output", []):
        for content in item.get("content", []):
            if content.get("type") == "output_text" and isinstance(content.get("text"), str):
                return content["text"]
    return None


def build_candidate_prompt(*, key: str, source: str) -> str:
    return (
        "Task: translate one Simplified Chinese UI localization string into concise English.\n"
        "Constraints:\n"
        "- Protected tokens must be preserved exactly.\n"
        "- Keep placeholders, tags, markup, and punctuation-safe token sequences unchanged.\n"
        "- Do not rely on any english locale files; they are unusable machine-translated noise.\n"
        "- If the string is ambiguous or unsafe, set needs_manual_review=true.\n"
        "- Return JSON matching the requested schema only.\n"
        f"Key: {key}\n"
        f"Source: {source}\n"
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


def run_batch_translation_trial(
    *,
    file_path: Path = DEFAULT_FILE,
    keys: List[str] | None = None,
    candidate_generator: Optional[CandidateGenerator] = None,
) -> Dict[str, object]:
    keys = keys or DEFAULT_KEYS
    source_tokens = read_vdf_tokens(file_path)
    candidate_generator = candidate_generator or OpenAIResponsesCandidateGenerator()

    report_rows: List[Dict[str, object]] = []
    accepted_rows: List[Dict[str, object]] = []
    rejected_rows: List[Dict[str, object]] = []
    manual_review_needed_rows: List[Dict[str, object]] = []

    for key in keys:
        if key not in source_tokens:
            row = {
                "file": str(file_path),
                "key": key,
                "source_text": None,
                "candidate_text": None,
                "generator_status": "source_missing",
                "validator_status": "skipped",
                "error_codes": ["SOURCE_KEY_MISSING"],
                "manual_review_reason": "Source key was not found in the sampled schinese file.",
                "accepted": False,
            }
            report_rows.append(row)
            manual_review_needed_rows.append(row)
            continue

        source_text = source_tokens[key]
        generation = candidate_generator.generate(key=key, source=source_text)

        if generation["status"] != "ok" or not generation.get("candidate_text"):
            row = {
                "file": str(file_path),
                "key": key,
                "source_text": source_text,
                "candidate_text": generation.get("candidate_text"),
                "generator_status": generation["status"],
                "validator_status": "skipped",
                "error_codes": [],
                "manual_review_reason": generation.get("generation_error"),
                "accepted": False,
                "model": generation.get("model"),
            }
            report_rows.append(row)
            manual_review_needed_rows.append(row)
            continue

        candidate_text = generation["candidate_text"]
        comparison = compare_protected_tokens(source_text, candidate_text)
        error_codes = [error["code"] for error in comparison["errors"]]
        accepted = comparison["status"] == "pass"

        row = {
            "file": str(file_path),
            "key": key,
            "source_text": source_text,
            "candidate_text": candidate_text,
            "generator_status": generation["status"],
            "validator_status": comparison["status"],
            "error_codes": error_codes,
            "manual_review_reason": None,
            "accepted": accepted,
            "model": generation.get("model"),
        }
        report_rows.append(row)
        if accepted:
            accepted_rows.append(row)
        else:
            rejected_rows.append(row)

    return {
        "trial_scope": {
            "file": str(file_path),
            "locale": "schinese",
            "batch_size": len(keys),
            "key_order": keys,
            "english_locale_policy": "ignored_as_low_confidence_machine_translated_noise",
            "candidate_generation_mode": "real_model_in_memory_only",
        },
        "prompt_structure": {
            "system": (
                "Translate Simplified Chinese game UI strings into concise English while preserving "
                "all protected tokens exactly. Return JSON only."
            ),
            "user_fields": ["task", "constraints", "key", "source"],
            "output_json": {
                "translation": "string",
                "needs_manual_review": "boolean",
                "review_reason": "string",
            },
        },
        "report_schema": {
            "file": "absolute path to the sampled VDF",
            "key": "localization token key",
            "source_text": "original schinese value",
            "candidate_text": "in-memory model-generated candidate",
            "generator_status": "ok | manual_review | source_missing",
            "validator_status": "pass | fail | skipped",
            "error_codes": "list of deterministic validator error codes",
            "manual_review_reason": "nullable explanation when generation or routing needs review",
            "accepted": "true when candidate has no protected-token errors",
            "model": "model name used for candidate generation",
        },
        "rows": report_rows,
        "accepted_rows": accepted_rows,
        "rejected_rows": rejected_rows,
        "manual_review_needed_rows": manual_review_needed_rows,
    }


def main() -> None:
    report = run_batch_translation_trial()
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

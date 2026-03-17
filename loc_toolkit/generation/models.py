from __future__ import annotations

import json
import os
import shutil
import subprocess
import urllib.error
import urllib.request
from typing import Any, Dict, Optional

from loc_toolkit.config.models import CodexConfig

from .prompts import build_translation_prompt


def _extract_json_object(text: str) -> Optional[Dict[str, Any]]:
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            return None
    return None


class FakeGenerator:
    def __init__(self, mapping: Optional[Dict[str, str]] = None) -> None:
        self.mapping = mapping or {}

    def generate(self, *, entry: Dict[str, str], model: str, target_locale: str) -> Dict[str, Any]:
        candidate = self.mapping.get(entry["source_text"], self.mapping.get(entry["key"]))
        if candidate is None:
            return {
                "status": "manual_review",
                "candidate_text": None,
                "generation_error": "No fake generator mapping found.",
                "model": model,
            }
        return {"status": "ok", "candidate_text": candidate, "generation_error": None, "model": model}


class OpenAIResponsesGenerator:
    def __init__(self, api_key: Optional[str] = None, timeout_seconds: int = 120) -> None:
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY")
        self.timeout_seconds = timeout_seconds

    def generate(self, *, entry: Dict[str, str], model: str, target_locale: str) -> Dict[str, Any]:
        if not self.api_key:
            return {
                "status": "manual_review",
                "candidate_text": None,
                "generation_error": "OPENAI_API_KEY is not set.",
                "model": model,
            }
        prompt = build_translation_prompt(
            locale=entry["locale"],
            file_path=entry["file"],
            key=entry["key"],
            source_text=entry["source_text"],
            target_locale=target_locale,
        )
        payload = {
            "model": model,
            "input": prompt,
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
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
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
                "model": model,
            }
        payload = json.loads(body)
        output_text = payload.get("output_text")
        if not output_text:
            return {
                "status": "manual_review",
                "candidate_text": None,
                "generation_error": "Could not extract output_text from Responses API result.",
                "model": model,
            }
        parsed = _extract_json_object(output_text)
        if not parsed:
            return {
                "status": "manual_review",
                "candidate_text": None,
                "generation_error": "Model output was not valid JSON.",
                "model": model,
            }
        if parsed.get("needs_manual_review"):
            return {
                "status": "manual_review",
                "candidate_text": parsed.get("translation"),
                "generation_error": parsed.get("review_reason") or "Model requested manual review.",
                "model": model,
            }
        return {"status": "ok", "candidate_text": parsed.get("translation"), "generation_error": None, "model": model}


class CodexExecGenerator:
    def __init__(self, codex: CodexConfig, project_root: str) -> None:
        self.codex = codex
        self.project_root = project_root

    def _resolve_exec(self) -> Optional[str]:
        if self.codex.exec_path:
            return self.codex.exec_path
        return shutil.which("codex")

    def generate(self, *, entry: Dict[str, str], model: str, target_locale: str) -> Dict[str, Any]:
        exec_path = self._resolve_exec()
        if not exec_path:
            return {
                "status": "manual_review",
                "candidate_text": None,
                "generation_error": "codex executable was not found. Set codex.exec_path or add codex to PATH.",
                "model": model,
            }
        prompt = build_translation_prompt(
            locale=entry["locale"],
            file_path=entry["file"],
            key=entry["key"],
            source_text=entry["source_text"],
            target_locale=target_locale,
        )
        command = [exec_path, "exec", "--model", model]
        command.extend(self.codex.extra_args)
        command.append(prompt)
        try:
            completed = subprocess.run(
                command,
                cwd=self.codex.cwd or self.project_root,
                capture_output=True,
                text=True,
                timeout=self.codex.timeout_seconds,
                check=False,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            return {
                "status": "manual_review",
                "candidate_text": None,
                "generation_error": f"codex exec failed to launch: {exc}",
                "model": model,
            }
        if completed.returncode != 0:
            return {
                "status": "manual_review",
                "candidate_text": None,
                "generation_error": completed.stderr.strip() or f"codex exec exited with code {completed.returncode}",
                "model": model,
            }
        parsed = _extract_json_object(completed.stdout)
        if not parsed:
            return {
                "status": "manual_review",
                "candidate_text": None,
                "generation_error": "codex exec output was not parseable structured JSON.",
                "model": model,
            }
        if parsed.get("needs_manual_review"):
            return {
                "status": "manual_review",
                "candidate_text": parsed.get("translation"),
                "generation_error": parsed.get("review_reason") or "Model requested manual review.",
                "model": model,
            }
        return {"status": "ok", "candidate_text": parsed.get("translation"), "generation_error": None, "model": model}

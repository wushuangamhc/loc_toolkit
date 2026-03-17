from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

from .models import ArtifactConfig, CodexConfig, LanguageMapping, ProjectConfig


def _to_artifact_config(raw: Optional[Dict[str, Any]]) -> ArtifactConfig:
    raw = raw or {}
    return ArtifactConfig(
        enabled=bool(raw.get("enabled", False)),
        formats=list(raw.get("formats", ["json", "csv"])),
    )


def _to_codex_config(raw: Optional[Dict[str, Any]]) -> CodexConfig:
    raw = raw or {}
    return CodexConfig(
        exec_path=raw.get("exec_path"),
        cwd=raw.get("cwd"),
        extra_args=list(raw.get("extra_args", [])),
        timeout_seconds=int(raw.get("timeout_seconds", 120)),
    )


def _resolve_target_locale(target_lang: Optional[str], raw_target_locale: Optional[str], mapping: LanguageMapping) -> str:
    if raw_target_locale:
        return raw_target_locale
    if target_lang:
        return mapping.aliases.get(target_lang, target_lang)
    return "english"


def _normalize_root_and_source_locale(
    root: Path,
    requested_source_locale: Optional[str],
    mapping: LanguageMapping,
) -> tuple[Path, str]:
    known_locales = set(mapping.aliases.values())
    if root.name in known_locales:
        return root.parent, requested_source_locale or root.name
    return root, requested_source_locale or "schinese"


def load_project_config(
    *,
    project_root: str,
    config_path: Optional[str] = None,
    target_lang: Optional[str] = None,
    source_locale: Optional[str] = None,
    target_locale: Optional[str] = None,
    model: Optional[str] = None,
    approval_policy: Optional[str] = None,
    report_dir: Optional[str] = None,
    generate_tm: Optional[bool] = None,
    generate_glossary: Optional[bool] = None,
) -> ProjectConfig:
    root = Path(project_root).resolve()
    raw: Dict[str, Any] = {}
    cfg_path = Path(config_path).resolve() if config_path else (root / "loc-toolkit.json")
    if cfg_path.exists():
        raw = json.loads(cfg_path.read_text(encoding="utf-8"))

    mapping = LanguageMapping(aliases=dict(raw.get("language_mapping", LanguageMapping().aliases)))
    normalized_root, normalized_source_locale = _normalize_root_and_source_locale(
        root,
        source_locale or raw.get("source_locale"),
        mapping,
    )
    root = normalized_root
    resolved_source_locale = normalized_source_locale
    resolved_target_locale = _resolve_target_locale(target_lang, target_locale or raw.get("target_locale"), mapping)

    tm_config = _to_artifact_config(raw.get("tm"))
    glossary_config = _to_artifact_config(raw.get("glossary"))
    if generate_tm is not None:
        tm_config = ArtifactConfig(enabled=generate_tm, formats=tm_config.formats)
    if generate_glossary is not None:
        glossary_config = ArtifactConfig(enabled=generate_glossary, formats=glossary_config.formats)

    output_dir = Path(report_dir).resolve() if report_dir else (Path(raw["output_dir"]).resolve() if raw.get("output_dir") else None)

    return ProjectConfig(
        project_root=root,
        source_locale=resolved_source_locale,
        target_locale=resolved_target_locale,
        model=model or raw.get("model", "gpt-5.4"),
        approval_policy=approval_policy or raw.get("approval_policy", "report-only"),
        file_allowlist=list(raw.get("file_allowlist", ["**/hud/*.vdf", "**/service/*.vdf", "**/error.vdf"])),
        file_blocklist=list(raw.get("file_blocklist", ["**/heroes/*.vdf", "**/items/*.vdf", "**/abilities/*.vdf"])),
        output_dir=output_dir,
        tm=tm_config,
        glossary=glossary_config,
        codex=_to_codex_config(raw.get("codex")),
        language_mapping=mapping,
        source_of_truth_excluded_locales=list(raw.get("source_of_truth_excluded_locales", ["english"])),
        low_risk_only=bool(raw.get("low_risk_only", True)),
        max_rows=raw.get("max_rows"),
        max_rows_per_file=raw.get("max_rows_per_file"),
    )

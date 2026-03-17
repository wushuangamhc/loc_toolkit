from __future__ import annotations

from pathlib import Path
from typing import Dict, Iterable

from loc_toolkit.config.models import ProjectConfig
from loc_toolkit.core.vdf_reader import read_vdf_tokens


LANGUAGE_NAMES = {
    "schinese": "Schinese",
    "english": "English",
    "russian": "Russian",
}


def mirror_target_path(config: ProjectConfig, source_file: Path) -> Path:
    relative_path = source_file.resolve().relative_to(config.source_root.resolve())
    return (config.project_root / config.target_locale / relative_path).resolve()


def _escape_vdf_value(value: str) -> str:
    return value.replace('"', '\\"')


def build_vdf_text(*, target_locale: str, tokens: Dict[str, str]) -> str:
    language_name = LANGUAGE_NAMES.get(target_locale, target_locale.capitalize())
    lines = [
        '"lang"',
        "{",
        f'\t"Language"\t\t"{language_name}"',
        '\t"Tokens"',
        "\t{",
    ]
    for key, value in tokens.items():
        lines.append(f'\t\t"{key}"\t\t"{_escape_vdf_value(value)}"')
    lines.extend(["\t}", "}"])
    return "\r\n".join(lines) + "\r\n"


def write_translated_vdf(config: ProjectConfig, source_file: Path, translated_tokens: Dict[str, str]) -> Path:
    target_file = mirror_target_path(config, source_file)
    target_file.parent.mkdir(parents=True, exist_ok=True)
    target_file.write_text(build_vdf_text(target_locale=config.target_locale, tokens=translated_tokens), encoding="utf-8")
    return target_file


def source_key_count(source_file: Path) -> int:
    return len(read_vdf_tokens(source_file))


def is_complete_file_translation(source_file: Path, rows: Iterable[Dict[str, object]]) -> bool:
    row_count = sum(1 for _ in rows)
    return row_count == source_key_count(source_file)

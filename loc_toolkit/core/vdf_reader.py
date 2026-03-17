from __future__ import annotations

import fnmatch
import re
from pathlib import Path
from typing import Dict, Iterable, List

from loc_toolkit.config.models import ProjectConfig


TOKENS_BLOCK_START_RE = re.compile(r'^\s*"Tokens"\s*$')
KV_RE = re.compile(r'^\s*"(?P<key>[^"]+)"\s*"(?P<value>.*)"\s*(?://.*)?$')


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


def _matches_any(path: str, patterns: List[str]) -> bool:
    for pattern in patterns:
        if fnmatch.fnmatch(path, pattern):
            return True
        if pattern.startswith("**/") and fnmatch.fnmatch(path, pattern[3:]):
            return True
    return False


def collect_source_files(config: ProjectConfig) -> List[Path]:
    source_root = config.source_root
    if not source_root.exists():
        return []
    if config.source_subpath:
        selected_root = (source_root / config.source_subpath).resolve()
        if not selected_root.exists():
            return []
        if selected_root.is_file():
            return [selected_root] if selected_root.suffix.lower() == ".vdf" else []
        return sorted(selected_root.rglob("*.vdf"))
    files: List[Path] = []
    for file_path in sorted(source_root.rglob("*.vdf")):
        relative_path = file_path.relative_to(source_root).as_posix()
        if config.file_allowlist and not _matches_any(relative_path, config.file_allowlist):
            continue
        if config.file_blocklist and _matches_any(relative_path, config.file_blocklist):
            continue
        files.append(file_path)
    return files


def build_manifest(entries: Iterable[dict]) -> Dict[str, Dict[str, str]]:
    manifest: Dict[str, Dict[str, str]] = {}
    for entry in entries:
        manifest.setdefault(entry["file"], {})[entry["key"]] = entry["source_text"]
    return manifest

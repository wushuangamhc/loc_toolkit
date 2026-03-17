from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional


@dataclass(frozen=True)
class ArtifactConfig:
    enabled: bool = False
    formats: List[str] = field(default_factory=lambda: ["json", "csv"])


@dataclass(frozen=True)
class CodexConfig:
    exec_path: Optional[str] = None
    cwd: Optional[str] = None
    extra_args: List[str] = field(default_factory=list)
    timeout_seconds: int = 120


@dataclass(frozen=True)
class LanguageMapping:
    aliases: Dict[str, str] = field(
        default_factory=lambda: {
            "zh": "schinese",
            "en": "english",
            "ru": "russian",
            "schinese": "schinese",
            "english": "english",
            "russian": "russian",
        }
    )


@dataclass(frozen=True)
class ProjectConfig:
    project_root: Path
    source_locale: str = "schinese"
    target_locale: str = "english"
    model: str = "gpt-5.4"
    approval_policy: str = "report-only"
    writeback_enabled: bool = False
    file_allowlist: List[str] = field(
        default_factory=lambda: ["**/hud/*.vdf", "**/service/*.vdf", "**/error.vdf"]
    )
    file_blocklist: List[str] = field(default_factory=lambda: ["**/heroes/*.vdf", "**/items/*.vdf", "**/abilities/*.vdf"])
    output_dir: Optional[Path] = None
    tm: ArtifactConfig = field(default_factory=ArtifactConfig)
    glossary: ArtifactConfig = field(default_factory=ArtifactConfig)
    codex: CodexConfig = field(default_factory=CodexConfig)
    language_mapping: LanguageMapping = field(default_factory=LanguageMapping)
    source_of_truth_excluded_locales: List[str] = field(default_factory=lambda: ["english"])
    low_risk_only: bool = True
    max_rows: Optional[int] = None
    max_rows_per_file: Optional[int] = None

    @property
    def source_root(self) -> Path:
        return self.project_root / self.source_locale

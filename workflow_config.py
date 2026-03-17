from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import List


REPO_ROOT = Path(r"D:\_project\c1\c1\content\c1\localization")
SCHINESE_ROOT = REPO_ROOT / "schinese"
ENGLISH_ROOT = REPO_ROOT / "english"

ENGLISH_LOCALE_POLICY = (
    "excluded_as_low_confidence_machine_translated_noise_not_source_of_truth"
)

LOW_RISK_UI_SYSTEM_FILES = [
    SCHINESE_ROOT / "hud" / "ui.vdf",
    SCHINESE_ROOT / "hud" / "store.vdf",
    SCHINESE_ROOT / "hud" / "setting.vdf",
    SCHINESE_ROOT / "hud" / "menu_bar.vdf",
    SCHINESE_ROOT / "hud" / "main.vdf",
    SCHINESE_ROOT / "hud" / "login.vdf",
    SCHINESE_ROOT / "hud" / "endscreen.vdf",
    SCHINESE_ROOT / "hud" / "collection.vdf",
    SCHINESE_ROOT / "hud" / "bp.vdf",
    SCHINESE_ROOT / "hud" / "blessing.vdf",
    SCHINESE_ROOT / "hud" / "equipment.vdf",
    SCHINESE_ROOT / "hud" / "diff_selection.vdf",
    SCHINESE_ROOT / "hud" / "hero_selection.vdf",
    SCHINESE_ROOT / "error.vdf",
    SCHINESE_ROOT / "service" / "talent.vdf",
]


@dataclass(frozen=True)
class WorkflowConfig:
    file_paths: List[Path] = field(default_factory=lambda: list(LOW_RISK_UI_SYSTEM_FILES))
    max_rows: int = 25
    max_rows_per_file: int = 10
    model: str = "gpt-4.1-mini"
    locale: str = "schinese"
    english_locale_policy: str = ENGLISH_LOCALE_POLICY


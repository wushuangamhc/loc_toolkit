from __future__ import annotations

from pathlib import Path
from typing import Dict

from loc_toolkit.config.models import ProjectConfig

from .common import base_report, collect_entries, make_generator, process_entries


def run_file_translation(config: ProjectConfig, source_file: str, generator_override=None) -> Dict[str, object]:
    report = base_report(config, "file")
    report["scope"]["source_file"] = str(Path(source_file).resolve())
    entries = collect_entries(config, [Path(source_file).resolve()])
    return process_entries(report, entries, config, make_generator(config, generator_override))

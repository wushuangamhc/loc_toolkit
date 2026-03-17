from __future__ import annotations

from typing import Dict

from loc_toolkit.config.models import ProjectConfig

from .common import base_report, collect_entries, make_generator, process_entries


def run_full_translation(config: ProjectConfig, generator_override=None) -> Dict[str, object]:
    report = base_report(config, "full")
    entries = collect_entries(config)
    return process_entries(report, entries, config, make_generator(config, generator_override))

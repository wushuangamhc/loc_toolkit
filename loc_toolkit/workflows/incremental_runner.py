from __future__ import annotations

from typing import Dict, List, Tuple

from loc_toolkit.config.models import ProjectConfig
from loc_toolkit.core.vdf_reader import build_manifest

from .common import base_report, collect_entries, make_generator, process_entries


def _diff_manifests(baseline: Dict[str, Dict[str, str]], current: Dict[str, Dict[str, str]]) -> Dict[str, List[Dict[str, object]]]:
    added: List[Dict[str, object]] = []
    changed: List[Dict[str, object]] = []
    removed: List[Dict[str, object]] = []
    unchanged: List[Dict[str, object]] = []
    for file_path in sorted(set(baseline) | set(current)):
        baseline_keys = baseline.get(file_path, {})
        current_keys = current.get(file_path, {})
        for key in sorted(set(baseline_keys) | set(current_keys)):
            old = baseline_keys.get(key)
            new = current_keys.get(key)
            if old is None and new is not None:
                added.append({"file": file_path, "key": key, "source_text": new})
            elif old is not None and new is None:
                removed.append({"file": file_path, "key": key, "previous_source_text": old})
            elif old != new:
                changed.append({"file": file_path, "key": key, "source_text": new, "previous_source_text": old})
            else:
                unchanged.append({"file": file_path, "key": key, "source_text": new})
    return {"added": added, "changed": changed, "removed": removed, "unchanged": unchanged}


def run_incremental_translation(
    config: ProjectConfig,
    baseline_manifest: Dict[str, Dict[str, str]],
    generator_override=None,
) -> Dict[str, object]:
    report = base_report(config, "incremental")
    current_entries = collect_entries(config)
    current_manifest = build_manifest(current_entries)
    diff = _diff_manifests(baseline_manifest, current_manifest)

    target_lookup: Dict[Tuple[str, str], Dict[str, object]] = {}
    for item in diff["added"]:
        target_lookup[(item["file"], item["key"])] = {**item, "change_type": "added", "previous_source_text": None}
    for item in diff["changed"]:
        target_lookup[(item["file"], item["key"])] = {**item, "change_type": "changed"}

    work_entries = [entry for entry in current_entries if (entry["file"], entry["key"]) in target_lookup]
    report = process_entries(report, work_entries, config, make_generator(config, generator_override))

    for row in report["rows"]:
        meta = target_lookup[(row["file"], row["key"])]
        row["change_type"] = meta["change_type"]
        row["previous_source_text"] = meta["previous_source_text"]

    report["diff_summary"] = {
        "added_count": len(diff["added"]),
        "changed_count": len(diff["changed"]),
        "removed_count": len(diff["removed"]),
        "unchanged_count": len(diff["unchanged"]),
    }
    report["removed_source_rows"] = diff["removed"]
    report["current_source_manifest"] = current_manifest
    report["report_schema"]["change_type"] = "added | changed"
    report["report_schema"]["previous_source_text"] = "nullable previous schinese value"
    return report

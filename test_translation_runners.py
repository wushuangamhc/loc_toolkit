from __future__ import annotations

import json
import unittest
from typing import Any, Dict

from full_translation_runner import run_full_translation
from incremental_translation_runner import run_incremental_translation
from workflow_config import SCHINESE_ROOT, WorkflowConfig
from workflow_shared import SourceEntry, build_source_manifest, collect_source_entries


class FakeFullGenerator:
    MAP = {
        "提示": "Tips",
        "取消": "Cancel",
        "确认": "Confirm",
        "{day}天{hour}时{min}分后过期": "Expires in {day}d {hour}h {min}m",
        "刷新 ({d:cur})": "Refresh ({d:cur})",
        "是否重置所有天赋节点<br>返回所有升级消耗": "Reset all talent nodes?<br>Refund all upgrade costs",
    }

    def generate(self, *, entry: SourceEntry) -> Dict[str, Any]:
        candidate = self.MAP.get(entry.source_text, f"UI::{entry.key}")
        return {
            "status": "ok",
            "candidate_text": candidate,
            "generation_error": None,
            "model": "fake-full-model",
            "raw_response": None,
        }


class FakeIncrementalGenerator:
    def generate(self, *, entry: SourceEntry) -> Dict[str, Any]:
        mapping = {
            "提示": ("ok", "Tips"),
            "取消": ("ok", "Cancel"),
            "确认": ("manual_review", None),
            "{day}天{hour}时{min}分后过期": ("ok", "Expires in {day}d {hour}h {min}m"),
            "刷新 ({d:cur})": ("ok", "Refresh ({cur})"),
            "是否重置所有天赋节点<br>返回所有升级消耗": ("ok", "Reset all talent nodes?<br>Refund all upgrade costs"),
        }
        status, candidate = mapping.get(entry.source_text, ("manual_review", None))
        if status == "manual_review":
            return {
                "status": "manual_review",
                "candidate_text": None,
                "generation_error": "Fake generator requested manual review.",
                "model": "fake-incremental-model",
                "raw_response": None,
            }
        return {
            "status": "ok",
            "candidate_text": candidate,
            "generation_error": None,
            "model": "fake-incremental-model",
            "raw_response": None,
        }


TEST_CONFIG = WorkflowConfig(
    file_paths=[SCHINESE_ROOT / "hud" / "ui.vdf"],
    max_rows=6,
    max_rows_per_file=6,
)


class TranslationRunnerTests(unittest.TestCase):
    def test_full_runner_produces_bucketed_report(self) -> None:
        report = run_full_translation(config=TEST_CONFIG, candidate_generator=FakeFullGenerator())
        self.assertEqual(report["workflow"], "full_initial_translation")
        self.assertEqual(report["summary"]["accepted_count"], 6)
        self.assertEqual(report["summary"]["rejected_count"], 0)
        self.assertEqual(report["summary"]["manual_review_needed_count"], 0)

    def test_incremental_runner_uses_diff_and_buckets_results(self) -> None:
        current_entries = collect_source_entries(TEST_CONFIG)
        baseline_manifest = build_source_manifest(current_entries)

        ui_path = str(SCHINESE_ROOT / "hud" / "ui.vdf")
        baseline_manifest[ui_path]["Popup_Title_Common_Tips"] = "旧提示"
        del baseline_manifest[ui_path]["Popup_Button_Confirm"]

        report = run_incremental_translation(
            baseline_manifest=baseline_manifest,
            config=TEST_CONFIG,
            candidate_generator=FakeIncrementalGenerator(),
        )

        self.assertEqual(report["workflow"], "incremental_translation_maintenance")
        self.assertEqual(report["diff_summary"]["added_count"], 1)
        self.assertEqual(report["diff_summary"]["changed_count"], 1)
        self.assertEqual(len(report["accepted_rows"]), 1)
        self.assertEqual(len(report["rejected_rows"]), 0)
        self.assertEqual(len(report["manual_review_needed_rows"]), 1)
        self.assertEqual(report["manual_review_needed_rows"][0]["key"], "Popup_Button_Confirm")


def run_harness() -> None:
    full_report = run_full_translation(config=TEST_CONFIG, candidate_generator=FakeFullGenerator())
    incremental_entries = collect_source_entries(TEST_CONFIG)
    baseline_manifest = build_source_manifest(incremental_entries)
    ui_path = str(SCHINESE_ROOT / "hud" / "ui.vdf")
    baseline_manifest[ui_path]["Popup_Title_Common_Tips"] = "旧提示"
    del baseline_manifest[ui_path]["Popup_Button_Confirm"]
    incremental_report = run_incremental_translation(
        baseline_manifest=baseline_manifest,
        config=TEST_CONFIG,
        candidate_generator=FakeIncrementalGenerator(),
    )
    print("Full runner report:")
    print(json.dumps(full_report, ensure_ascii=False, indent=2))
    print("\nIncremental runner report:\n")
    print(json.dumps(incremental_report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    run_harness()
    print("\nRunning unittest suite...\n")
    unittest.main(argv=["test_translation_runners.py"], exit=False, verbosity=2)

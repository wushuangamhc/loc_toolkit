from __future__ import annotations

import json
import unittest
from typing import Any, Dict

from batch_translation_trial import DEFAULT_KEYS, run_batch_translation_trial


class FakePassingGenerator:
    MAP = {
        "提示": "Tips",
        "取消": "Cancel",
        "确认": "Confirm",
        "{day}天{hour}时{min}分后过期": "Expires in {day}d {hour}h {min}m",
        "刷新 ({d:cur})": "Refresh ({d:cur})",
        "是否重置所有天赋节点<br>返回所有升级消耗": "Reset all talent nodes?<br>Refund all upgrade costs",
    }

    def generate(self, *, key: str, source: str) -> Dict[str, Any]:
        return {
            "status": "ok",
            "candidate_text": self.MAP[source],
            "generation_error": None,
            "model": "fake-pass-model",
            "raw_response": None,
        }


class FakeMixedGenerator:
    MAP = {
        "Popup_Title_Common_Tips": ("ok", "Tips"),
        "Popup_Button_Cancel": ("ok", "Cancel"),
        "Popup_Button_Confirm": ("manual_review", None),
        "mail_timeout": ("ok", "Expires in {day}d {hour}h {min}m"),
        "refresh_count": ("ok", "Refresh ({cur})"),
        "talent_reset": ("ok", "Reset all talent nodes?Refund all upgrade costs"),
    }

    def generate(self, *, key: str, source: str) -> Dict[str, Any]:
        status, candidate = self.MAP[key]
        if status == "manual_review":
            return {
                "status": "manual_review",
                "candidate_text": None,
                "generation_error": "Model marked this string as ambiguous.",
                "model": "fake-mixed-model",
                "raw_response": None,
            }
        return {
            "status": "ok",
            "candidate_text": candidate,
            "generation_error": None,
            "model": "fake-mixed-model",
            "raw_response": None,
        }


class BatchTranslationTrialTests(unittest.TestCase):
    def test_passing_generator_produces_all_accepted_rows(self) -> None:
        report = run_batch_translation_trial(candidate_generator=FakePassingGenerator())
        self.assertEqual(report["trial_scope"]["batch_size"], len(DEFAULT_KEYS))
        self.assertEqual(len(report["accepted_rows"]), len(DEFAULT_KEYS))
        self.assertEqual(report["rejected_rows"], [])
        self.assertEqual(report["manual_review_needed_rows"], [])

    def test_mixed_generator_splits_rows_into_expected_buckets(self) -> None:
        report = run_batch_translation_trial(candidate_generator=FakeMixedGenerator())
        self.assertEqual(len(report["accepted_rows"]), 3)
        self.assertEqual(len(report["rejected_rows"]), 2)
        self.assertEqual(len(report["manual_review_needed_rows"]), 1)

        rejected_codes = {row["key"]: row["error_codes"] for row in report["rejected_rows"]}
        self.assertIn("PLACEHOLDER_CHANGED", rejected_codes["refresh_count"])
        self.assertIn("TOKEN_MISSING", rejected_codes["talent_reset"])


def run_harness() -> None:
    print("Read-only batch translation trial report with fake passing generator:")
    print(json.dumps(run_batch_translation_trial(candidate_generator=FakePassingGenerator()), ensure_ascii=False, indent=2))
    print("\nRead-only batch translation trial report with fake mixed generator:\n")
    print(json.dumps(run_batch_translation_trial(candidate_generator=FakeMixedGenerator()), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    run_harness()
    print("\nRunning unittest suite...\n")
    unittest.main(argv=["test_batch_translation_trial.py"], exit=False, verbosity=2)

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from loc_toolkit.artifacts.glossary_builder import build_glossary
from loc_toolkit.artifacts.tm_builder import build_tm
from loc_toolkit.config.loader import load_project_config
from loc_toolkit.core.protected_tokens import extract_protected_tokens
from loc_toolkit.core.validator import compare_protected_tokens
from loc_toolkit.workflows.full_runner import run_full_translation
from loc_toolkit.workflows.incremental_runner import run_incremental_translation
from loc_toolkit.workflows.single_file_runner import run_file_translation


UI_VDF = """"lang"
{
	"Language"		"Schinese"
	"Tokens"
	{
		"Popup_Title_Common_Tips"	"提示"
		"mail_timeout"	"{day}天{hour}时{min}分后过期"
		"talent_reset" "是否重置所有天赋节点<br>返回所有升级消耗"
	}
}
"""


class FakeGenerator:
    MAP = {
        "提示": "Tips",
        "{day}天{hour}时{min}分后过期": "Expires in {day}d {hour}h {min}m",
        "是否重置所有天赋节点<br>返回所有升级消耗": "Reset all talent nodes?<br>Refund all upgrade costs",
    }

    def generate(self, *, entry, model, target_locale):
        candidate = self.MAP.get(entry["source_text"])
        if candidate is None:
            return {"status": "manual_review", "candidate_text": None, "generation_error": "missing fake mapping", "model": model}
        return {"status": "ok", "candidate_text": candidate, "generation_error": None, "model": model}


class FakeMixedGenerator:
    def generate(self, *, entry, model, target_locale):
        if entry["key"] == "Popup_Title_Common_Tips":
            return {"status": "ok", "candidate_text": "Tips", "generation_error": None, "model": model}
        if entry["key"] == "mail_timeout":
            return {"status": "ok", "candidate_text": "Expires in {day}d {hour}h min", "generation_error": None, "model": model}
        return {"status": "manual_review", "candidate_text": None, "generation_error": "ambiguous", "model": model}


class ToolkitTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        source_dir = self.root / "schinese" / "hud"
        source_dir.mkdir(parents=True)
        (source_dir / "ui.vdf").write_text(UI_VDF, encoding="utf-8")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_extract_and_compare(self):
        result = extract_protected_tokens("Refresh ({d:cur})")
        self.assertEqual(result["inventories"]["typed_placeholders"], ["{d:cur}"])
        cmp_result = compare_protected_tokens("{day}天{hour}时{min}分", "{day}d {hour}h {min}m")
        self.assertEqual(cmp_result["status"], "pass")
        bad = compare_protected_tokens("%chance%%", "%chance%")
        self.assertIn("LITERAL_PERCENT_LOST", [error["code"] for error in bad["errors"]])

    def test_config_loader_maps_lang(self):
        cfg = load_project_config(project_root=str(self.root), target_lang="en", generate_tm=True)
        self.assertEqual(cfg.target_locale, "english")
        self.assertTrue(cfg.tm.enabled)
        self.assertIn("english", cfg.source_of_truth_excluded_locales)

    def test_full_runner(self):
        cfg = load_project_config(project_root=str(self.root), target_lang="en")
        report = run_full_translation(cfg, generator_override=FakeGenerator())
        self.assertEqual(report["summary"]["accepted_count"], 3)
        self.assertEqual(report["summary"]["rejected_count"], 0)
        self.assertEqual(report["summary"]["manual_review_needed_count"], 0)

    def test_file_runner(self):
        cfg = load_project_config(project_root=str(self.root), target_lang="en")
        report = run_file_translation(cfg, str(self.root / "schinese" / "hud" / "ui.vdf"), generator_override=FakeGenerator())
        self.assertEqual(report["workflow"], "file")
        self.assertEqual(len(report["accepted_rows"]), 3)

    def test_incremental_runner(self):
        cfg = load_project_config(project_root=str(self.root), target_lang="en")
        baseline = {
            str(self.root / "schinese" / "hud" / "ui.vdf"): {
                "Popup_Title_Common_Tips": "旧提示"
            }
        }
        report = run_incremental_translation(cfg, baseline, generator_override=FakeGenerator())
        self.assertEqual(report["diff_summary"]["changed_count"], 1)
        self.assertEqual(report["diff_summary"]["added_count"], 2)

    def test_buckets_and_artifacts(self):
        cfg = load_project_config(project_root=str(self.root), target_lang="en", generate_tm=True, generate_glossary=True)
        report = run_full_translation(cfg, generator_override=FakeMixedGenerator())
        self.assertEqual(len(report["accepted_rows"]), 1)
        self.assertEqual(len(report["rejected_rows"]), 1)
        self.assertEqual(len(report["manual_review_needed_rows"]), 1)
        tm = build_tm(report)
        glossary = build_glossary(report)
        self.assertEqual(len(tm["rows"]), 1)
        self.assertGreaterEqual(len(glossary["rows"]), 1)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import json
import unittest

from compare_protected_tokens import compare_protected_tokens


CASES = [
    {
        "name": "missing_ability_tag",
        "source_path": r"D:\_project\c1\c1\content\c1\localization\schinese\heroes\vespera.vdf#L57",
        "source": "<Ability|vespera_3/>结束后获得%shield%<Shield:护盾/>",
        "candidate": "结束后获得%shield%<Shield:护盾/>",
        "expected_codes": {"TOKEN_MISSING", "TOKEN_SEQUENCE_CHANGED"},
    },
    {
        "name": "changed_placeholder",
        "source_path": r"D:\_project\c1\c1\content\c1\localization\schinese\hud\store.vdf#L36",
        "source": "永久限购：<font color='#6B9E4C'>{d:num}/{d:max}</font>",
        "candidate": "永久限购：<font color='#6B9E4C'>{d:num}/{max}</font>",
        "expected_codes": {"TOKEN_MISSING", "TOKEN_ADDED", "PLACEHOLDER_CHANGED"},
    },
    {
        "name": "changed_tag_shape",
        "source_path": r"D:\_project\c1\c1\content\c1\localization\schinese\heroes\vexis.vdf#L43",
        "source": "<Ability|vexis_4/>会穿透目标",
        "candidate": "<Constant|vexis_4/>会穿透目标",
        "expected_codes": {"TOKEN_MISSING", "TOKEN_ADDED", "TAG_SHAPE_CHANGED"},
    },
    {
        "name": "changed_tag_attributes",
        "source_path": r"D:\_project\c1\c1\content\c1\localization\schinese\hud\store.vdf#L36",
        "source": "永久限购：<font color='#6B9E4C'>{d:num}/{d:max}</font>",
        "candidate": "永久限购：<font color='#FFFFFF'>{d:num}/{d:max}</font>",
        "expected_codes": {"TOKEN_MISSING", "TOKEN_ADDED", "TAG_ATTR_CHANGED"},
    },
    {
        "name": "lost_literal_percent",
        "source_path": r"D:\_project\c1\c1\content\c1\localization\schinese\items\artifact.vdf#L105",
        "source": "攻击有%chance%%概率对前方造成%damage%伤害",
        "candidate": "攻击有%chance%概率对前方造成%damage%伤害",
        "expected_codes": {"TOKEN_MISSING", "TOKEN_ADDED", "LITERAL_PERCENT_LOST"},
    },
]


class CompareProtectedTokensTests(unittest.TestCase):
    def test_broken_candidates_produce_expected_errors(self) -> None:
        for case in CASES:
            with self.subTest(case=case["name"]):
                result = compare_protected_tokens(case["source"], case["candidate"])
                self.assertEqual(result["status"], "fail")
                codes = {error["code"] for error in result["errors"]}
                self.assertTrue(case["expected_codes"].issubset(codes))

    def test_matching_candidate_passes(self) -> None:
        value = "<panel class='DevourIcon'/>[圣匣效果]"
        result = compare_protected_tokens(value, value)
        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["errors"], [])


def run_harness() -> None:
    print("Representative schinese comparison failures:")
    for case in CASES:
        result = compare_protected_tokens(case["source"], case["candidate"])
        payload = {
            "name": case["name"],
            "source_path": case["source_path"],
            "source": case["source"],
            "candidate": case["candidate"],
            "status": result["status"],
            "error_codes": [error["code"] for error in result["errors"]],
            "errors": result["errors"],
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    run_harness()
    print("\nRunning unittest suite...\n")
    unittest.main(argv=["test_compare_protected_tokens.py"], exit=False, verbosity=2)

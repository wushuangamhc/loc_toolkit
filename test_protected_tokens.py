from __future__ import annotations

import json
import unittest

from protected_tokens import extract_protected_tokens


SAMPLES = [
    {
        "name": "store_font_and_typed_placeholders",
        "source_path": r"D:\_project\c1\c1\content\c1\localization\schinese\hud\store.vdf#L36",
        "value": "永久限购：<font color='#6B9E4C'>{d:num}/{d:max}</font>",
        "expected_categories": ["font_open_tag", "typed_placeholder", "typed_placeholder", "font_close_tag"],
    },
    {
        "name": "ability_semantic_and_percent_special",
        "source_path": r"D:\_project\c1\c1\content\c1\localization\schinese\heroes\vespera.vdf#L29",
        "value": "<Split:散射/>：额外投掷%suriken_count%枚飞镖，额外飞镖减少%damage_reduce%%伤害",
        "expected_categories": ["semantic_tag", "percent_token", "percent_token_with_literal_percent"],
    },
    {
        "name": "ability_and_semantic_combo",
        "source_path": r"D:\_project\c1\c1\content\c1\localization\schinese\heroes\vespera.vdf#L57",
        "value": "<Ability|vespera_3/>结束后获得%shield%<Shield:护盾/>",
        "expected_categories": ["ability_tag", "percent_token", "semantic_tag"],
    },
    {
        "name": "panel_tag",
        "source_path": r"D:\_project\c1\c1\content\c1\localization\schinese\dota_ability_variable.vdf#L133",
        "value": "<panel class='DevourIcon'/>[圣匣效果]",
        "expected_categories": ["panel_tag"],
    },
    {
        "name": "variable_inside_font",
        "source_path": r"D:\_project\c1\c1\content\c1\localization\schinese\dota_ability_variable.vdf#L77",
        "value": "<font color='#ffe9a7'>$damage</font>",
        "expected_categories": ["font_open_tag", "variable", "font_close_tag"],
    },
    {
        "name": "constant_tags",
        "source_path": r"D:\_project\c1\c1\content\c1\localization\schinese\dota_ability_variable.vdf#L194",
        "value": "可以抵挡伤害，每<Constant|SHIELD_DECAY_INTERVAL/>秒会衰减<Constant|SHIELD_DECAY_RATE/>%",
        "expected_categories": ["constant_tag", "constant_tag"],
    },
    {
        "name": "ui_br_and_untyped_placeholders",
        "source_path": r"D:\_project\c1\c1\content\c1\localization\schinese\hud\ui.vdf#L38",
        "value": "是否重置所有天赋节点<br>返回所有升级消耗",
        "expected_categories": ["br_tag"],
    },
    {
        "name": "typed_and_untyped_mix",
        "source_path": r"D:\_project\c1\c1\content\c1\localization\schinese\hud\ui.vdf#L21",
        "value": "{day}天{hour}时{min}分后过期",
        "expected_categories": ["untyped_placeholder", "untyped_placeholder", "untyped_placeholder"],
    },
]


class ExtractProtectedTokensTests(unittest.TestCase):
    def test_expected_category_order(self) -> None:
        for sample in SAMPLES:
            with self.subTest(sample=sample["name"]):
                result = extract_protected_tokens(sample["value"])
                categories = [span["category"] for span in result["spans"]]
                self.assertEqual(sample["expected_categories"], categories)

    def test_special_percent_sequence_not_double_counted(self) -> None:
        sample = extract_protected_tokens(
            "<Split:散射/>：额外投掷%suriken_count%枚飞镖，额外飞镖减少%damage_reduce%%伤害"
        )
        self.assertEqual(sample["inventories"]["percent_tokens"], ["%suriken_count%"])
        self.assertEqual(
            sample["inventories"]["percent_literal_percent_sequences"],
            ["%damage_reduce%%"],
        )

    def test_variable_boundary_warning_for_invalid_following_char(self) -> None:
        result = extract_protected_tokens("$damage系数")
        self.assertEqual(result["inventories"]["variables"], ["$damage"])
        self.assertEqual(len(result["warnings"]), 1)

    def test_variable_boundary_ok_with_space_or_colon(self) -> None:
        for value in ("$damage 系数", "$damage: 系数", "$damage：系数"):
            with self.subTest(value=value):
                result = extract_protected_tokens(value)
                self.assertEqual(result["warnings"], [])


def run_harness() -> None:
    print("Representative schinese extraction samples:")
    for sample in SAMPLES:
        result = extract_protected_tokens(sample["value"])
        payload = {
            "name": sample["name"],
            "source_path": sample["source_path"],
            "value": sample["value"],
            "spans": result["spans"],
            "inventories": {
                key: value
                for key, value in result["inventories"].items()
                if value
            },
            "warnings": result["warnings"],
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    run_harness()
    print("\nRunning unittest suite...\n")
    unittest.main(argv=["test_protected_tokens.py"], exit=False, verbosity=2)

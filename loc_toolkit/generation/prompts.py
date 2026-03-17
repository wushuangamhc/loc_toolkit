from __future__ import annotations

from loc_toolkit.config.defaults import ENGLISH_NOISE_POLICY, SOURCE_OF_TRUTH_POLICY


def build_translation_prompt(*, locale: str, file_path: str, key: str, source_text: str, target_locale: str) -> str:
    return (
        "Task: translate one localization string.\n"
        f"Source locale: {locale}\n"
        f"Target locale: {target_locale}\n"
        "Scope:\n"
        "- low-risk UI/system text first\n"
        "- no lore expansion\n"
        "- no style rewriting beyond natural target-language phrasing\n"
        "Rules:\n"
        f"- {SOURCE_OF_TRUTH_POLICY}\n"
        f"- {ENGLISH_NOISE_POLICY}\n"
        "- protected tokens must be preserved exactly\n"
        "- keep placeholders, tags, markup, and literal trailing percent sequences unchanged\n"
        "- if the string is ambiguous, set needs_manual_review=true\n"
        "- return JSON only with translation, needs_manual_review, review_reason\n"
        f"File: {file_path}\n"
        f"Key: {key}\n"
        f"Source: {source_text}\n"
    )

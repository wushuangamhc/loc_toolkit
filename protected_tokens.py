from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from typing import Dict, List, Optional


VARIABLE_RE = re.compile(r"\$[A-Za-z_][A-Za-z0-9_]*")
TYPED_PLACEHOLDER_RE = re.compile(r"\{[ds]:[A-Za-z_][A-Za-z0-9_]*\}")
UNTYPED_PLACEHOLDER_RE = re.compile(r"\{[A-Za-z_][A-Za-z0-9_]*\}")
PERCENT_TOKEN_RE = re.compile(r"%[A-Za-z_][A-Za-z0-9_]*%")
PERCENT_TOKEN_WITH_LITERAL_PERCENT_RE = re.compile(r"%[A-Za-z_][A-Za-z0-9_]*%%")
ABILITY_TAG_RE = re.compile(r"<Ability\|[^/>]+/>")
CONSTANT_TAG_RE = re.compile(r"<Constant\|[^/>]+/>")
SEMANTIC_TAG_RE = re.compile(r"<[A-Za-z_][A-Za-z0-9_]*:[^<>]+/>")
FONT_OPEN_RE = re.compile(r"<font\b[^>]*>")
FONT_CLOSE_RE = re.compile(r"</font>")
BR_TAG_RE = re.compile(r"<br>")
PANEL_TAG_RE = re.compile(r"<panel\b[^>]+/>")

VARIABLE_BOUNDARY_CHARS = {" ", "\t", "\r", "\n", ":", "："}


@dataclass(frozen=True)
class TokenSpan:
    category: str
    text: str
    start: int
    end: int
    exact_match_required: bool
    notes: Optional[str] = None


def _variable_boundary_ok(value: str, end: int) -> bool:
    if end >= len(value):
        return True
    return value[end] in VARIABLE_BOUNDARY_CHARS


def _build_span(
    category: str,
    match: re.Match[str],
    *,
    exact_match_required: bool = True,
    notes: Optional[str] = None,
) -> TokenSpan:
    return TokenSpan(
        category=category,
        text=match.group(0),
        start=match.start(),
        end=match.end(),
        exact_match_required=exact_match_required,
        notes=notes,
    )


def extract_protected_tokens(value: str) -> Dict[str, object]:
    spans: List[TokenSpan] = []
    inventories: Dict[str, List[str]] = {
        "variables": [],
        "typed_placeholders": [],
        "untyped_placeholders": [],
        "percent_tokens": [],
        "percent_literal_percent_sequences": [],
        "ability_tags": [],
        "constant_tags": [],
        "semantic_tags": [],
        "font_open_tags": [],
        "font_close_tags": [],
        "br_tags": [],
        "panel_tags": [],
    }
    warnings: List[str] = []

    index = 0
    while index < len(value):
        match: Optional[re.Match[str]] = None
        span: Optional[TokenSpan] = None
        inventory_key: Optional[str] = None

        match = PERCENT_TOKEN_WITH_LITERAL_PERCENT_RE.match(value, index)
        if match:
            span = _build_span(
                "percent_token_with_literal_percent",
                match,
                notes="Represents one %token% followed by one literal percent sign.",
            )
            inventory_key = "percent_literal_percent_sequences"
        else:
            match = ABILITY_TAG_RE.match(value, index)
            if match:
                span = _build_span("ability_tag", match)
                inventory_key = "ability_tags"
            else:
                match = CONSTANT_TAG_RE.match(value, index)
                if match:
                    span = _build_span("constant_tag", match)
                    inventory_key = "constant_tags"
                else:
                    match = PANEL_TAG_RE.match(value, index)
                    if match:
                        span = _build_span("panel_tag", match)
                        inventory_key = "panel_tags"
                    else:
                        match = BR_TAG_RE.match(value, index)
                        if match:
                            span = _build_span("br_tag", match)
                            inventory_key = "br_tags"
                        else:
                            match = FONT_CLOSE_RE.match(value, index)
                            if match:
                                span = _build_span("font_close_tag", match)
                                inventory_key = "font_close_tags"
                            else:
                                match = FONT_OPEN_RE.match(value, index)
                                if match:
                                    span = _build_span("font_open_tag", match)
                                    inventory_key = "font_open_tags"
                                else:
                                    match = SEMANTIC_TAG_RE.match(value, index)
                                    if match:
                                        span = _build_span(
                                            "semantic_tag",
                                            match,
                                            notes="Safest default is exact full-tag preservation.",
                                        )
                                        inventory_key = "semantic_tags"
                                    else:
                                        match = VARIABLE_RE.match(value, index)
                                        if match:
                                            boundary_ok = _variable_boundary_ok(value, match.end())
                                            note = None if boundary_ok else "Invalid boundary after $variable."
                                            span = _build_span(
                                                "variable",
                                                match,
                                                notes=note,
                                            )
                                            inventory_key = "variables"
                                            if not boundary_ok:
                                                warnings.append(
                                                    f"Variable boundary warning at index {match.start()}: {match.group(0)}"
                                                )
                                        else:
                                            match = TYPED_PLACEHOLDER_RE.match(value, index)
                                            if match:
                                                span = _build_span("typed_placeholder", match)
                                                inventory_key = "typed_placeholders"
                                            else:
                                                match = UNTYPED_PLACEHOLDER_RE.match(value, index)
                                                if match:
                                                    span = _build_span("untyped_placeholder", match)
                                                    inventory_key = "untyped_placeholders"
                                                else:
                                                    match = PERCENT_TOKEN_RE.match(value, index)
                                                    if match:
                                                        span = _build_span("percent_token", match)
                                                        inventory_key = "percent_tokens"

        if span is not None and inventory_key is not None:
            spans.append(span)
            inventories[inventory_key].append(span.text)
            index = span.end
            continue

        index += 1

    return {
        "value": value,
        "spans": [asdict(span) for span in spans],
        "inventories": inventories,
        "warnings": warnings,
    }


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Extract protected localization tokens from a value string.")
    parser.add_argument("value", help="Raw localized value to inspect.")
    args = parser.parse_args()
    print(json.dumps(extract_protected_tokens(args.value), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

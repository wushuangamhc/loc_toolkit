from __future__ import annotations

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
        match = None
        span = None
        inventory_key = None

        for regex, category, key, notes in [
            (PERCENT_TOKEN_WITH_LITERAL_PERCENT_RE, "percent_token_with_literal_percent", "percent_literal_percent_sequences", "Represents one %token% followed by one literal percent sign."),
            (ABILITY_TAG_RE, "ability_tag", "ability_tags", None),
            (CONSTANT_TAG_RE, "constant_tag", "constant_tags", None),
            (PANEL_TAG_RE, "panel_tag", "panel_tags", None),
            (BR_TAG_RE, "br_tag", "br_tags", None),
            (FONT_CLOSE_RE, "font_close_tag", "font_close_tags", None),
            (FONT_OPEN_RE, "font_open_tag", "font_open_tags", None),
            (SEMANTIC_TAG_RE, "semantic_tag", "semantic_tags", "Safest default is exact full-tag preservation."),
            (TYPED_PLACEHOLDER_RE, "typed_placeholder", "typed_placeholders", None),
            (UNTYPED_PLACEHOLDER_RE, "untyped_placeholder", "untyped_placeholders", None),
            (PERCENT_TOKEN_RE, "percent_token", "percent_tokens", None),
        ]:
            match = regex.match(value, index)
            if match:
                span = _build_span(category, match, notes=notes)
                inventory_key = key
                break

        if span is None:
            match = VARIABLE_RE.match(value, index)
            if match:
                boundary_ok = _variable_boundary_ok(value, match.end())
                note = None if boundary_ok else "Invalid boundary after $variable."
                span = _build_span("variable", match, notes=note)
                inventory_key = "variables"
                if not boundary_ok:
                    warnings.append(f"Variable boundary warning at index {match.start()}: {match.group(0)}")

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

from __future__ import annotations

from collections import Counter
from typing import Dict, List, Optional, Tuple

from .protected_tokens import extract_protected_tokens


EXACT_INVENTORY_KEYS = {
    "variables",
    "typed_placeholders",
    "untyped_placeholders",
    "percent_tokens",
    "percent_literal_percent_sequences",
    "ability_tags",
    "constant_tags",
    "semantic_tags",
    "font_open_tags",
    "font_close_tags",
    "br_tags",
    "panel_tags",
}

TAG_CATEGORIES = {
    "ability_tag",
    "constant_tag",
    "semantic_tag",
    "font_open_tag",
    "font_close_tag",
    "br_tag",
    "panel_tag",
}

PLACEHOLDER_CATEGORIES = {"typed_placeholder", "untyped_placeholder"}


def _make_error(
    code: str,
    message: str,
    *,
    severity: str = "error",
    category: Optional[str] = None,
    source_span: Optional[str] = None,
    candidate_span: Optional[str] = None,
    details: Optional[Dict[str, object]] = None,
) -> Dict[str, object]:
    payload: Dict[str, object] = {"code": code, "severity": severity, "message": message}
    if category is not None:
        payload["category"] = category
    if source_span is not None:
        payload["source_span"] = source_span
    if candidate_span is not None:
        payload["candidate_span"] = candidate_span
    if details is not None:
        payload["details"] = details
    return payload


def _inventory_counter(items: List[str]) -> Counter:
    return Counter(items)


def _strip_tag_name(tag_text: str) -> str:
    if tag_text.startswith("</"):
        return tag_text[2:-1].strip()
    inner = tag_text[1:-1].strip()
    if inner.endswith("/"):
        inner = inner[:-1].rstrip()
    return inner.split(None, 1)[0]


def _extract_attributes(tag_text: str) -> str:
    inner = tag_text[1:-1].strip()
    if inner.endswith("/"):
        inner = inner[:-1].rstrip()
    parts = inner.split(None, 1)
    return parts[1] if len(parts) == 2 else ""


def _split_semantic_tag(tag_text: str) -> Tuple[str, str]:
    inner = tag_text[1:-2]
    return inner.split(":", 1)


def _compare_inventories(source_inventories: Dict[str, List[str]], candidate_inventories: Dict[str, List[str]]) -> List[Dict[str, object]]:
    errors: List[Dict[str, object]] = []
    for key in sorted(EXACT_INVENTORY_KEYS):
        source_counter = _inventory_counter(source_inventories.get(key, []))
        candidate_counter = _inventory_counter(candidate_inventories.get(key, []))
        for token, source_count in sorted(source_counter.items()):
            candidate_count = candidate_counter.get(token, 0)
            if candidate_count < source_count:
                errors.append(
                    _make_error(
                        "TOKEN_MISSING",
                        f"Missing protected token {token!r} from category {key}.",
                        category=key,
                        source_span=token,
                        details={"expected_count": source_count, "actual_count": candidate_count},
                    )
                )
        for token, candidate_count in sorted(candidate_counter.items()):
            source_count = source_counter.get(token, 0)
            if candidate_count > source_count:
                errors.append(
                    _make_error(
                        "TOKEN_ADDED",
                        f"Unexpected protected token {token!r} added to category {key}.",
                        category=key,
                        candidate_span=token,
                        details={"expected_count": source_count, "actual_count": candidate_count},
                    )
                )
    return errors


def _compare_ordered_spans(source_spans: List[Dict[str, object]], candidate_spans: List[Dict[str, object]]) -> List[Dict[str, object]]:
    errors: List[Dict[str, object]] = []
    paired_count = min(len(source_spans), len(candidate_spans))
    for index in range(paired_count):
        source_span = source_spans[index]
        candidate_span = candidate_spans[index]
        source_category = source_span["category"]
        candidate_category = candidate_span["category"]

        if source_category in PLACEHOLDER_CATEGORIES and candidate_category in PLACEHOLDER_CATEGORIES:
            if source_span["text"] != candidate_span["text"]:
                errors.append(
                    _make_error(
                        "PLACEHOLDER_CHANGED",
                        f"Placeholder changed at span index {index}: {source_span['text']} -> {candidate_span['text']}.",
                        category="placeholder",
                        source_span=str(source_span["text"]),
                        candidate_span=str(candidate_span["text"]),
                    )
                )
            continue

        if source_category == "percent_token_with_literal_percent" and candidate_category == "percent_token":
            errors.append(
                _make_error(
                    "LITERAL_PERCENT_LOST",
                    f"Literal trailing percent sequence changed at span index {index}: {source_span['text']} -> {candidate_span['text']}.",
                    category="percent_literal_percent_sequences",
                    source_span=str(source_span["text"]),
                    candidate_span=str(candidate_span["text"]),
                )
            )
            continue

        if source_category != candidate_category:
            errors.append(
                _make_error(
                    "TAG_SHAPE_CHANGED" if source_category in TAG_CATEGORIES else "TOKEN_SEQUENCE_CHANGED",
                    f"Protected token order/category changed at span index {index}: {source_category} -> {candidate_category}.",
                    category=str(source_category),
                    source_span=str(source_span["text"]),
                    candidate_span=str(candidate_span["text"]),
                )
            )
            continue

        if source_category == "percent_token_with_literal_percent" and source_span["text"] != candidate_span["text"]:
            errors.append(
                _make_error(
                    "LITERAL_PERCENT_LOST",
                    f"Literal trailing percent sequence changed at span index {index}: {source_span['text']} -> {candidate_span['text']}.",
                    category="percent_literal_percent_sequences",
                    source_span=str(source_span["text"]),
                    candidate_span=str(candidate_span["text"]),
                )
            )
            continue

        if source_category in {"font_open_tag", "panel_tag"}:
            if _strip_tag_name(str(source_span["text"])) != _strip_tag_name(str(candidate_span["text"])):
                errors.append(
                    _make_error(
                        "TAG_SHAPE_CHANGED",
                        f"Tag name changed at span index {index}.",
                        category=str(source_category),
                        source_span=str(source_span["text"]),
                        candidate_span=str(candidate_span["text"]),
                    )
                )
                continue
            if _extract_attributes(str(source_span["text"])) != _extract_attributes(str(candidate_span["text"])):
                errors.append(
                    _make_error(
                        "TAG_ATTR_CHANGED",
                        f"Tag attributes changed at span index {index}.",
                        category=str(source_category),
                        source_span=str(source_span["text"]),
                        candidate_span=str(candidate_span["text"]),
                    )
                )
                continue

        if source_category == "semantic_tag":
            source_identifier, source_label = _split_semantic_tag(str(source_span["text"]))
            candidate_identifier, candidate_label = _split_semantic_tag(str(candidate_span["text"]))
            if source_identifier != candidate_identifier:
                errors.append(
                    _make_error(
                        "TAG_SHAPE_CHANGED",
                        f"Semantic tag identifier changed at span index {index}: {source_identifier} -> {candidate_identifier}.",
                        category="semantic_tag",
                        source_span=str(source_span["text"]),
                        candidate_span=str(candidate_span["text"]),
                    )
                )
                continue
            if source_label != candidate_label:
                errors.append(
                    _make_error(
                        "SEMANTIC_LABEL_CHANGED",
                        f"Semantic tag label changed at span index {index}: {source_label} -> {candidate_label}.",
                        category="semantic_tag",
                        source_span=str(source_span["text"]),
                        candidate_span=str(candidate_span["text"]),
                    )
                )
                continue

    return errors


def compare_protected_tokens(source: str, candidate: str) -> Dict[str, object]:
    source_result = extract_protected_tokens(source)
    candidate_result = extract_protected_tokens(candidate)
    errors: List[Dict[str, object]] = []
    errors.extend(_compare_inventories(source_result["inventories"], candidate_result["inventories"]))
    errors.extend(_compare_ordered_spans(source_result["spans"], candidate_result["spans"]))
    return {
        "source": source,
        "candidate": candidate,
        "status": "pass" if not errors else "fail",
        "fatal": bool(errors),
        "errors": errors,
        "source_tokens": source_result,
        "candidate_tokens": candidate_result,
    }

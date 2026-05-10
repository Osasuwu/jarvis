"""Classifier helper tests — JSON parsing + enum validation, no Ollama call."""

from __future__ import annotations

from comm_patterns.classifier import VALID_LABELS, _extract_json, normalize_result


def test_extract_json_strict():
    obj = _extract_json('{"primary_label": "affirmation", "confidence": 0.9}')
    assert obj == {"primary_label": "affirmation", "confidence": 0.9}


def test_extract_json_strips_code_fences():
    raw = '```json\n{"primary_label": "affirmation"}\n```'
    obj = _extract_json(raw)
    assert obj == {"primary_label": "affirmation"}


def test_extract_json_finds_object_in_chatty_response():
    raw = 'Here is the answer: {"primary_label": null} — let me know.'
    obj = _extract_json(raw)
    assert obj == {"primary_label": None}


def test_extract_json_returns_none_on_garbage():
    assert _extract_json("hello world") is None


def test_normalize_result_accepts_valid_label():
    out = normalize_result(
        {"primary_label": "affirmation", "confidence": 0.9, "anchor_quote": "ok"},
        anchor_fallback="x",
    )
    assert out is not None
    assert out["primary_label"] == "affirmation"
    assert out["confidence"] == 0.9
    assert out["anchor_quote"] == "ok"


def test_normalize_result_rejects_invalid_label():
    out = normalize_result(
        {"primary_label": "bogus_value", "confidence": 0.9, "anchor_quote": "ok"},
        anchor_fallback="x",
    )
    assert out is None


def test_normalize_result_clamps_confidence():
    out = normalize_result(
        {"primary_label": "affirmation", "confidence": 99, "anchor_quote": "ok"},
        anchor_fallback="x",
    )
    assert out["confidence"] == 1.0


def test_normalize_result_uses_anchor_fallback_when_missing():
    out = normalize_result(
        {"primary_label": "affirmation", "confidence": 0.9},
        anchor_fallback="fallback text",
    )
    assert out["anchor_quote"] == "fallback text"


def test_normalize_result_handles_null_label():
    out = normalize_result(
        {"primary_label": None, "confidence": 0.0, "anchor_quote": "x"},
        anchor_fallback="x",
    )
    assert out is not None
    assert out["primary_label"] is None


def test_valid_labels_match_schema_check_constraint():
    """Sentinel: the enum on the Python side has to track schema.sql.
    If this fails, ADR 0004 / schema / classifier are out of sync.
    Reads schema.sql directly so the test can't drift from the table
    definition."""
    schema = (Path(__file__).resolve().parent.parent / "mcp-memory" / "schema.sql").read_text(
        encoding="utf-8"
    )
    # Walk the comm_patterns CREATE TABLE block.
    block_start = schema.index("create table if not exists comm_patterns")
    block = schema[block_start : block_start + 2000]
    # primary_label CHECK has the six allowed values quoted.
    schema_labels = set(re.findall(r"'([a-z_]+)'", block))
    assert VALID_LABELS == schema_labels


# Imports needed by the schema sentinel — keep at the bottom so the
# top-of-file remains a simple "test the public API" view.
import re  # noqa: E402
from pathlib import Path  # noqa: E402

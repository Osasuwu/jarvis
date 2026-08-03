"""Shared markdown-parsing helpers for tests/ci guard tests."""

from __future__ import annotations

import re


def strip_code_spans_and_fences(text: str) -> str:
    """Drop fenced code blocks and inline `code spans` — import-line parsing
    skips code spans, so a match only counts if it survives outside one."""
    text = re.sub(r"```.*?```", "", text, flags=re.DOTALL)
    text = re.sub(r"`[^`\n]*`", "", text)
    return text

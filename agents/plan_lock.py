"""Plan-lock helper — canonicalize/hash a ``## Plan`` section, and a strict
parser that rejects malformed plans (issue #1685).

Sibling module to :mod:`agents.scope_hash` (issue #773's consolidation
pattern: one module, many callers) — but this hashes plan *text*, not a
file list, so it is a distinct primitive rather than an extension of
``scope_hash``.

Canonicalization: CRLF -> LF, then strip trailing whitespace from every
line, so a digest is stable across line-ending and trailing-whitespace
variants of an otherwise-identical plan (golden tests in
``tests/reactive_core/test_plan_lock.py``).
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass


class MalformedPlanError(ValueError):
    """Raised by :func:`parse_plan` when a plan fails strict validation.

    ``reason`` is one of a fixed set of named codes (``missing_heading``,
    ``empty_step_list``, ``absent_lock_line``) — never a free-form message
    only — so callers can branch on the failure kind without string-parsing.
    """

    def __init__(self, reason: str, message: str) -> None:
        self.reason = reason
        super().__init__(f"{reason}: {message}")


@dataclass(frozen=True)
class ParsedPlan:
    steps: tuple[str, ...]
    lock: str


_HEADING_RE = re.compile(r"^##\s*Plan\s*$", re.MULTILINE)
_NEXT_HEADING_RE = re.compile(r"^#{1,6}(?:\s|$)", re.MULTILINE)
_STEP_RE = re.compile(r"^-\s+(.+?)\s*$", re.MULTILINE)
_LOCK_RE = re.compile(r"^lock:\s*(\S+)\s*$", re.MULTILINE)


def canonicalize_plan(text: str) -> str:
    """LF-normalize and strip trailing whitespace from every line.

    Idempotent: canonicalizing an already-canonical plan returns it
    unchanged.
    """
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    return "\n".join(line.rstrip() for line in normalized.split("\n"))


def hash_plan(text: str) -> str:
    """Sha256 hex digest of the canonicalized plan text."""
    return hashlib.sha256(canonicalize_plan(text).encode("utf-8")).hexdigest()


def parse_plan(text: str) -> ParsedPlan:
    """Strictly parse a ``## Plan`` section.

    Scoped to the content between the ``## Plan`` heading and the next
    heading line (of any level) or end of text — so a full issue body
    with other sections (e.g. "## Acceptance Criteria", "## Decisions")
    never leaks a stray ``- ...`` or ``lock: ...`` line from outside the
    plan into the parsed result.

    Raises :class:`MalformedPlanError` with a distinct named reason for
    each of: missing ``## Plan`` heading, empty step list, absent lock
    line.
    """
    canonical = canonicalize_plan(text)

    heading_match = _HEADING_RE.search(canonical)
    if not heading_match:
        raise MalformedPlanError("missing_heading", "no '## Plan' heading found")

    section_start = heading_match.end()
    next_heading_match = _NEXT_HEADING_RE.search(canonical, section_start)
    section_end = next_heading_match.start() if next_heading_match else len(canonical)
    section = canonical[section_start:section_end]

    steps = tuple(m.group(1) for m in _STEP_RE.finditer(section))
    if not steps:
        raise MalformedPlanError("empty_step_list", "no '- ' step lines found")

    lock_match = _LOCK_RE.search(section)
    if not lock_match:
        raise MalformedPlanError("absent_lock_line", "no 'lock: <value>' line found")

    return ParsedPlan(steps=steps, lock=lock_match.group(1))

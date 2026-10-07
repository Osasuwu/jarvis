"""Plan-lock helper — canonicalize/hash a ``## Plan`` section, and a strict
parser that rejects malformed plans (issue #1685).

Canonicalization: CRLF -> LF, then strip trailing whitespace from every
line, so a digest is stable across line-ending and trailing-whitespace
variants of an otherwise-identical plan (golden tests in
``tests/plan_review/test_plan_lock.py``).
"""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
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


# Public: the heading/next-heading section-scoping recipe consumed by
# `## Plan` section replacement logic (formerly agents.plan_section,
# demolished with reactive-core in #1802).
HEADING_RE = re.compile(r"^##\s*Plan\s*$", re.MULTILINE)
NEXT_HEADING_RE = re.compile(r"^#{1,6}(?:\s|$)", re.MULTILINE)
_HEADING_RE = HEADING_RE
_NEXT_HEADING_RE = NEXT_HEADING_RE
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


def _plan_steps(canonical: str) -> tuple[tuple[str, ...], str]:
    """Scope a canonical text to its ``## Plan`` section and return
    ``(steps, section)``.

    Raises :class:`MalformedPlanError` (``missing_heading`` /
    ``empty_step_list``). The lock line is not required here — that is
    :func:`parse_plan`'s check, so :func:`compute_lock` can hash a plan
    that does not carry its lock yet.
    """
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
    return steps, section


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
    steps, section = _plan_steps(canonicalize_plan(text))

    lock_match = _LOCK_RE.search(section)
    if not lock_match:
        raise MalformedPlanError("absent_lock_line", "no 'lock: <value>' line found")

    return ParsedPlan(steps=steps, lock=lock_match.group(1))


def _steps_text(steps: tuple[str, ...]) -> str:
    return "\n".join(f"- {s}" for s in steps)


def compute_lock(text: str) -> str:
    """The ``lock:`` value a ``## Plan`` section must carry (#1687, #1984).

    The sha256 (via :func:`hash_plan`) of the canonical steps-only
    reconstruction (``- <step>`` lines), never of the raw section text —
    hashing the section including its own ``lock:`` line would be
    self-referential. Any ``lock:`` line already in ``text`` is ignored, so
    this works on a plan before its lock is written.

    This is the one shared recipe: :func:`verify_lock` compares against it
    and ``python -m agents.plan_lock hash <plan-file>`` prints it. It must
    not be reimplemented per caller.

    Raises :class:`MalformedPlanError` (``missing_heading`` /
    ``empty_step_list``).
    """
    steps, _section = _plan_steps(canonicalize_plan(text))
    return hash_plan(_steps_text(steps))


def verify_lock(text: str) -> bool:
    """Verify a ``## Plan`` section's declared ``lock:`` value (#1687).

    True iff the declared lock equals :func:`compute_lock` for the same
    text. Every consumer (interactive lane, CI diff-gate) verifies through
    this function.

    Propagates :class:`MalformedPlanError` from :func:`parse_plan` — a
    malformed plan is not "unlocked", it is an error the caller must
    handle explicitly (fail closed).
    """
    parsed = parse_plan(text)
    return compute_lock(text) == parsed.lock


def main(argv: list[str] | None = None) -> int:
    """``python -m agents.plan_lock hash <plan-file>`` — print the lock.

    The plan file holds a ``## Plan`` section (a lock line in it, if any,
    is ignored). Prints the :func:`compute_lock` hex digest and exits 0;
    exits 1 with the reason on stderr when the file is unreadable or the
    plan is malformed.
    """
    parser = argparse.ArgumentParser(prog="python -m agents.plan_lock")
    sub = parser.add_subparsers(dest="command", required=True)
    hash_cmd = sub.add_parser("hash", help="print the lock hash for a ## Plan file")
    hash_cmd.add_argument("plan_file", help="file holding the ## Plan section")
    args = parser.parse_args(argv)

    try:
        with open(args.plan_file, encoding="utf-8", newline="") as fh:
            text = fh.read()
    except OSError as exc:
        print(f"cannot read plan file: {exc}", file=sys.stderr)
        return 1

    try:
        lock = compute_lock(text)
    except MalformedPlanError as exc:
        print(f"malformed plan: {exc}", file=sys.stderr)
        return 1

    print(lock)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

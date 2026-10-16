"""Plan-lock helper — canonicalize/hash a ``## Plan`` section, a strict
parser that rejects malformed plans (issue #1685), and the ``publish``
command that writes a locked plan into an issue body (#2008).

Consumers: interactive ``/implement`` and the AFK lane publish through
``python -m agents.plan_lock publish``; lane intake
(``.github/scripts/lane_intake.py``) admits an ``afk:2-plan`` issue only
when :func:`verify_lock` passes.

Canonicalization: CRLF -> LF, then strip trailing whitespace from every
line, so a digest is stable across line-ending and trailing-whitespace
variants of an otherwise-identical plan (golden tests in
``tests/plan_review/test_plan_lock.py``).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass


class MalformedPlanError(ValueError):
    """Raised by :func:`parse_plan` when a plan fails strict validation.

    ``reason`` is one of a fixed set of named codes (``missing_heading``,
    ``duplicate_heading``, ``sub_heading``, ``prose_line``,
    ``duplicate_lock_line``, ``empty_step_list``, ``absent_lock_line``) —
    never a free-form message only — so callers can branch on the failure
    kind without string-parsing.
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
# A level-1 or level-2 heading ends the section; deeper headings inside it
# are malformed (``sub_heading``), not a boundary.
NEXT_HEADING_RE = re.compile(r"^#{1,2}(?:\s|$)", re.MULTILINE)
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

    The grammar is strict (D5, #2008): the section runs to the next level-1
    or level-2 heading or end of text, and every line in it is blank, a
    ``- `` step, or the ``lock:`` line. Raises :class:`MalformedPlanError`
    (``missing_heading`` / ``duplicate_heading`` / ``sub_heading`` /
    ``prose_line`` / ``duplicate_lock_line`` / ``empty_step_list``). The lock
    line is not required here — that is :func:`parse_plan`'s check, so
    :func:`compute_lock` can hash a plan that does not carry its lock yet.
    """
    headings = list(_HEADING_RE.finditer(canonical))
    if not headings:
        raise MalformedPlanError("missing_heading", "no '## Plan' heading found")
    if len(headings) > 1:
        raise MalformedPlanError("duplicate_heading", "more than one '## Plan' heading found")

    section_start = headings[0].end()
    next_heading_match = _NEXT_HEADING_RE.search(canonical, section_start)
    section_end = next_heading_match.start() if next_heading_match else len(canonical)
    section = canonical[section_start:section_end]

    steps: list[str] = []
    lock_lines = 0
    for line in section.split("\n"):
        if not line:
            continue
        step = _STEP_RE.match(line)
        if step:
            steps.append(step.group(1))
        elif _LOCK_RE.match(line):
            lock_lines += 1
            if lock_lines > 1:
                raise MalformedPlanError("duplicate_lock_line", "more than one 'lock:' line found")
        elif line.startswith("#"):
            raise MalformedPlanError("sub_heading", f"heading inside the plan: {line!r}")
        else:
            raise MalformedPlanError("prose_line", f"line is not a step or lock: {line!r}")

    if not steps:
        raise MalformedPlanError("empty_step_list", "no '- ' step lines found")
    return tuple(steps), section


def parse_plan(text: str) -> ParsedPlan:
    """Strictly parse a ``## Plan`` section.

    Scoped to the content between the ``## Plan`` heading and the next
    level-1 or level-2 heading or end of text — so a full issue body
    with other sections (e.g. "## Acceptance Criteria", "## Decisions")
    never leaks a stray ``- ...`` or ``lock: ...`` line from outside the
    plan into the parsed result, and prose in those sections is not
    judged against the plan grammar.

    Raises :class:`MalformedPlanError` with a distinct named reason for
    each grammar violation (see :func:`_plan_steps`) and for an absent
    lock line.
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
    and :func:`publish` writes it. It must not be reimplemented per caller.

    Raises :class:`MalformedPlanError` (``missing_heading`` /
    ``empty_step_list``).
    """
    steps, _section = _plan_steps(canonicalize_plan(text))
    return hash_plan(_steps_text(steps))


def verify_lock(text: str) -> bool:
    """Verify a ``## Plan`` section's declared ``lock:`` value (#1687).

    True iff the declared lock equals :func:`compute_lock` for the same
    text. Every consumer (lane intake, :func:`publish`'s round trip) verifies
    through this function.

    Propagates :class:`MalformedPlanError` from :func:`parse_plan` — a
    malformed plan is not "unlocked", it is an error the caller must
    handle explicitly (fail closed).
    """
    parsed = parse_plan(text)
    return compute_lock(text) == parsed.lock


class PublishError(RuntimeError):
    """``publish`` could not leave a verified locked plan in the issue body."""


class GhError(RuntimeError):
    """A ``gh`` call exited non-zero; the message is gh's stderr."""


def _run_gh(args: list[str]) -> str:
    """Run ``gh <args>`` and return stdout. The one seam tests replace."""
    result = subprocess.run(
        ["gh", *args],
        capture_output=True,
        encoding="utf-8",
        check=False,
    )
    if result.returncode != 0:
        raise GhError(result.stderr.strip() or f"gh exited {result.returncode}")
    return result.stdout


def _plan_section(plan_text: str) -> tuple[str, str]:
    """The canonical locked ``## Plan`` section for ``plan_text`` and its lock.

    Raises :class:`MalformedPlanError` for a plan that breaks the grammar.
    """
    steps, _section = _plan_steps(canonicalize_plan(plan_text))
    lock = hash_plan(_steps_text(steps))
    return f"## Plan\n\n{_steps_text(steps)}\n\nlock: {lock}\n", lock


def replace_plan_section(body: str, section: str) -> str:
    """Splice ``section`` into an issue ``body`` in place of its ``## Plan``.

    Exactly one existing section is replaced, through to the next level-1 or
    level-2 heading (or the end); a body with none gets the section appended
    after a blank line; every byte outside the section is left as it was. The
    section takes the body's line-ending style. A body with two ``## Plan``
    headings keeps the second, so :func:`publish`'s verification of the result
    refuses it (``duplicate_heading``) — which one to replace is not a choice
    to make here.
    """
    newline = "\r\n" if "\r\n" in body else "\n"
    section = section.replace("\n", newline)
    headings = list(_HEADING_RE.finditer(body))
    if not headings:
        if not body.strip():
            return section
        return body.rstrip("\r\n") + newline * 2 + section

    start = headings[0].start()
    next_heading = _NEXT_HEADING_RE.search(body, headings[0].end())
    if next_heading is None:
        return body[:start] + section
    return body[:start] + section + newline + body[next_heading.start() :]


def _gh_issue_args(verb: str, issue: str, repo: str | None, *rest: str) -> list[str]:
    args = ["issue", verb, issue, *rest]
    if repo:
        args += ["--repo", repo]
    return args


def _fetch_body(issue: str, repo: str | None) -> str:
    out = _run_gh(_gh_issue_args("view", issue, repo, "--json", "body"))
    return json.loads(out)["body"]


def publish(issue: str, plan_text: str, *, repo: str | None = None) -> str:
    """Write ``plan_text`` into ``issue``'s body as a locked ``## Plan``; return the lock.

    The one publish path for interactive ``/implement`` and the AFK lane
    (D5, #2008). Replaces the body's existing ``## Plan`` or appends one,
    writes the body back, then re-fetches it and requires :func:`verify_lock`
    and the published lock to hold on what GitHub stored. Never touches
    labels or comments — ``agent:dispatch`` is applied separately and last.

    Raises :class:`MalformedPlanError` for a bad plan (before any ``gh``
    call), :class:`GhError` when ``gh`` fails and :class:`PublishError` when
    the body cannot take the section (two ``## Plan`` headings — before any
    write) or the round trip fails.
    """
    section, lock = _plan_section(plan_text)
    new_body = replace_plan_section(_fetch_body(issue, repo), section)
    try:
        spliced_ok = verify_lock(new_body)
    except MalformedPlanError as exc:
        raise PublishError(f"the issue body cannot take a valid plan section ({exc})") from exc
    if not spliced_ok:
        raise PublishError("the spliced body does not verify; nothing was written")

    fd, tmp_name = tempfile.mkstemp(suffix=".md")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as fh:
            fh.write(new_body)
        _run_gh(_gh_issue_args("edit", issue, repo, "--body-file", tmp_name))
    finally:
        os.unlink(tmp_name)

    stored = _fetch_body(issue, repo)
    try:
        stored_ok = verify_lock(stored) and parse_plan(stored).lock == lock
    except MalformedPlanError as exc:
        raise PublishError(f"round-trip failed: stored body is malformed ({exc})") from exc
    if not stored_ok:
        raise PublishError("round-trip failed: stored body does not match the published plan")
    return lock


def main(argv: list[str] | None = None) -> int:
    """``python -m agents.plan_lock publish <issue> --plan-file <path> [--repo <owner/name>]``.

    The plan file holds a ``## Plan`` section (a lock line in it, if any, is
    ignored). Publishes it into the issue body, prints the lock and exits 0;
    exits 1 with the reason on stderr when the file is unreadable, the plan
    is malformed, a ``gh`` call fails or the round trip does not verify.
    """
    parser = argparse.ArgumentParser(prog="python -m agents.plan_lock")
    sub = parser.add_subparsers(dest="command", required=True)
    publish_cmd = sub.add_parser("publish", help="write a locked ## Plan into an issue body")
    publish_cmd.add_argument("issue", help="issue number")
    publish_cmd.add_argument("--plan-file", required=True, help="file holding the ## Plan section")
    publish_cmd.add_argument("--repo", help="owner/name; defaults to the current repo")
    args = parser.parse_args(argv)

    try:
        with open(args.plan_file, encoding="utf-8", newline="") as fh:
            text = fh.read()
    except OSError as exc:
        print(f"cannot read plan file: {exc}", file=sys.stderr)
        return 1

    try:
        lock = publish(args.issue, text, repo=args.repo)
    except MalformedPlanError as exc:
        print(f"malformed plan: {exc}", file=sys.stderr)
        return 1
    except (GhError, PublishError) as exc:
        print(f"publish failed: {exc}", file=sys.stderr)
        return 1

    print(lock)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

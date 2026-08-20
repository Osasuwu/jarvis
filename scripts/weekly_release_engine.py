"""Pure decision core for the `/weekly-release` capability (#1572).

Everything here is a pure function over plain dicts/dataclasses — no
network, filesystem, or `gh` calls. The I/O adapter (window collection via
`gh`, repos.conf traversal, GitHub releases API reads) lives in
`scripts/weekly_release_gather.py`, mirroring the morning_engine.py /
morning_gather.py split (#1586).

Covers: conventional-commit parsing, release-worthiness, semver
classification, the fact-anchoring linter, goal-section format selection,
draft-aware anchor window computation, and trust-ramp state.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# -- Conventional-commit parsing --------------------------------------------

_CONVENTIONAL_RE = re.compile(
    r"^(?P<type>[a-zA-Z]+)(\((?P<scope>[^)]*)\))?(?P<breaking>!)?:\s*(?P<desc>.*)$"
)


@dataclass(frozen=True)
class ConventionalCommit:
    type: str
    scope: str | None
    breaking: bool
    desc: str


def parse_conventional_type(title: str) -> ConventionalCommit:
    """Parse a PR/commit title's conventional-commit prefix.

    Titles that don't match the convention parse as type="" (mechanical
    classification below treats an unknown type as non-mechanical, so an
    unparseable title never silently suppresses a release).
    """
    m = _CONVENTIONAL_RE.match(title.strip())
    if not m:
        return ConventionalCommit(type="", scope=None, breaking=False, desc=title.strip())
    return ConventionalCommit(
        type=m.group("type").lower(),
        scope=(m.group("scope") or None),
        breaking=bool(m.group("breaking")),
        desc=m.group("desc"),
    )


# -- Release-worthiness (AC4) -------------------------------------------------

# ceiling: fixed mechanical-type set, not learned from labels; matches the
# issue's own examples (dep-bumps, CI fixes). Extend here if a new mechanical
# category shows up in a false-positive "release" during trust-ramp review.
_MECHANICAL_TYPES = {"chore", "ci", "build", "test", "docs"}


def _is_mechanical(entry: dict) -> bool:
    if entry.get("is_dependabot"):
        return True
    c = parse_conventional_type(entry["title"])
    if c.type in _MECHANICAL_TYPES:
        return True
    # A `fix` scoped to `ci` is still a CI-fix per the issue's own framing
    # ("Неделя из dep-bump'ов и CI-фиксов -> релиза нет"), not user-facing.
    if c.type == "fix" and c.scope == "ci":
        return True
    return False


def is_release_worthy(entries: list[dict]) -> bool:
    """A window is release-worthy iff it contains at least one non-mechanical
    entry (not a dependency bump, not a CI-only fix)."""
    return any(not _is_mechanical(e) for e in entries)


# -- Semver classification (AC5) ---------------------------------------------


def classify_bump(entries: list[dict]) -> str:
    """ "patch" if the window is fixes-only, "minor" if it contains a new
    capability (any `feat` entry). Never "major" — decision 5b811a25:
    there is no breaking-change signal in any form; trust ramp is the only
    human gate, so a `!` marker or a `BREAKING CHANGE:` body never escalates
    the bump beyond minor."""
    for e in entries:
        c = parse_conventional_type(e["title"])
        if c.type == "feat":
            return "minor"
    return "patch"


# -- Fact-anchoring linter (AC6) ---------------------------------------------

_PR_REF_RE = re.compile(r"#(\d+)")
_BARE_NUMBER_RE = re.compile(r"\d")


def _has_quantitative_claim(line_without_refs: str) -> bool:
    return bool(_BARE_NUMBER_RE.search(line_without_refs))


def lint_release_notes(lines: list[str], window_refs: set[str]) -> list[str]:
    """Language-independent citation gate: every note line must cite >=1
    PR/issue number that is actually in the collected window; a line with a
    quantitative claim (any digit outside of a `#NNN` citation) but no valid
    citation is rejected with a more specific message. Replaces a
    banned-word list (per issue text) — it checks provenance, not phrasing.

    Returns a list of violation messages; empty list == the notes pass.
    """
    violations = []
    for i, line in enumerate(lines):
        refs = _PR_REF_RE.findall(line)
        valid_refs = [r for r in refs if r in window_refs]
        if valid_refs:
            continue
        stripped = _PR_REF_RE.sub("", line)
        if _has_quantitative_claim(stripped):
            violations.append(
                f"line {i}: quantitative claim without a source citation from the window: {line!r}"
            )
        else:
            violations.append(f"line {i}: missing PR/issue citation from the window: {line!r}")
    return violations


# -- Goal-section format selection (AC8) -------------------------------------


def format_goal_section(goals: list[dict]) -> str:
    """0/1 active goal (with movement) -> narrative prose; >=2 -> a
    🎯-anchored split, one bullet per goal. Goals with no movement in the
    window (`no_movement=True`) are omitted entirely from either format —
    the section is a progress note, not a goal inventory."""
    moved = [g for g in goals if not g.get("no_movement")]
    if not moved:
        return ""
    if len(moved) <= 1:
        g = moved[0]
        progress = g.get("progress_note") or g.get("title", "")
        return f"This week's focus was **{g.get('title', g.get('slug', ''))}**: {progress}"
    lines = ["## 🎯 Goals"]
    for g in moved:
        note = g.get("progress_note") or ""
        lines.append(f"- 🎯 **{g.get('title', g.get('slug', ''))}** — {note}".rstrip(" —"))
    return "\n".join(lines)


# -- Draft-aware anchor window (AC11) ----------------------------------------


@dataclass(frozen=True)
class WindowResult:
    start: str  # ISO-8601 UTC
    end: str  # ISO-8601 UTC
    truncated: bool


def compute_window(
    last_release_at: str | None,
    pending_draft_at: str | None,
    now: str,
    cap_days: int = 30,
) -> WindowResult:
    """Window anchor = last release publish time, OR an existing pending
    draft's original anchor if one exists (so re-running against a draft
    updates it in place rather than restarting the clock), whichever is
    present; capped at `cap_days` from `now`. All inputs/outputs are
    ISO-8601 UTC strings so callers don't need to thread datetime objects
    through the `gh`-calling adapter layer."""
    from datetime import datetime, timedelta

    def _parse(s: str) -> datetime:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))

    now_dt = _parse(now)
    anchor = pending_draft_at or last_release_at
    if anchor is None:
        start_dt = now_dt - timedelta(days=cap_days)
        return WindowResult(start=start_dt.isoformat(), end=now_dt.isoformat(), truncated=True)

    anchor_dt = _parse(anchor)
    cap_dt = now_dt - timedelta(days=cap_days)
    if anchor_dt < cap_dt:
        return WindowResult(start=cap_dt.isoformat(), end=now_dt.isoformat(), truncated=True)
    return WindowResult(start=anchor_dt.isoformat(), end=now_dt.isoformat(), truncated=False)


# -- Trust ramp (AC10) --------------------------------------------------------


def trust_ramp_state(prior_releases: list[dict]) -> str:
    """ "draft" or "auto". Read live from the GitHub releases API by the
    caller (no local state, per the issue text) — this function only
    applies the rule to whatever release history is handed to it.

    Rule: the first 4 releases for a repo are drafts published by the
    operator. Once the 4 most-recent releases were each published without
    a post-publish edit, the skill auto-publishes going forward.
    `prior_releases` is ordered most-recent-first; each entry needs
    `published: bool` and `edited_after_publish: bool`.
    """
    if len(prior_releases) < 4:
        return "draft"
    last_four = prior_releases[:4]
    if all(r.get("published") and not r.get("edited_after_publish") for r in last_four):
        return "auto"
    return "draft"


# -- Routine mode (#1658 AC1/AC3) ---------------------------------------------


def is_routine_host(device_config: dict) -> bool:
    """True iff this device is the sole routine host (``config/device.json``'s
    ``routine_host`` flag) — same gate /setup-tasks applies, decision
    1b7ff8d1-bbca-4207-a7e4-4c1edddef67e. A missing or falsy flag means "not
    the host", never an error — refusal is the caller's job."""
    return device_config.get("routine_host") is True


def weekly_release_notification_for(repo: str, version: str, status: str) -> tuple[str, str] | None:
    """(subject, body) for a weekly-release routine notification (AC3's fixed
    phrasing), or ``None`` when the run produced no release. ``None`` is the
    "stay silent" signal — the routine caller skips ``notify_text`` entirely
    rather than sending an empty/no-op notification, since a run with
    nothing to report must not become weekly spam."""
    if status == "draft":
        return f"Draft awaiting publication: {repo} v{version}", ""
    if status == "published":
        return f"Published release: {repo} v{version}", ""
    return None


# -- Release-body assembly (AC9) ----------------------------------------------


def assemble_release_body(
    notes_body: str,
    remaining_section: str,
    full_changelog_url: str,
    footer: str = "Опубликовано ботом",
) -> str:
    """Structural assembly only. `notes_body` and `remaining_section` are
    already agent-authored prose — facts sourced from the collected window /
    open milestone issues, drafted by the caller and passed through
    `lint_release_notes` before reaching here. This function adds no issue
    links of its own: it only appends the `**Full Changelog**` line and the
    footer, which is what "no issue-links in the body" (issue #1572 AC9)
    actually constrains — the mechanical part, not the prose."""
    parts = [notes_body.rstrip()]
    if remaining_section.strip():
        parts.append(remaining_section.rstrip())
    parts.append(f"**Full Changelog**: {full_changelog_url}")
    parts.append(f"— {footer}")
    return "\n\n".join(parts)

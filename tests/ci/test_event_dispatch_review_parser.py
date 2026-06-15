"""Meta-test for the `review-negative-claude-bot` parser in event-dispatch.yml.

Sibling of the #957 merge-gate incident (fixed in PR #960, pinned by
``test_code_review_verdict_guard.py``). Same root cause on the *event* side:

``event-dispatch.yml`` job ``review-negative-claude-bot`` selected the Claude
code-review verdict comment by the literal first line ``### Code review``
(case-sensitive) and detected findings only via a ``Found N issues:`` line.
Calibration from #960 showed the bot deviates routinely — ``## Code Review``,
``## Claude Code Review``, bare ``### MAJOR`` sections with no ``Found N`` line —
so ``review_negative`` events were silently never emitted for those reviews and
the orchestrator never fired ``/rework`` (issue #961).

Fix (issue #961, Option A): broaden the title selector and add severity-heading
findings detection, mirroring the #960-hardened merge gate, and emit
``review_negative`` on any findings signal. Unlike the merge gate this job
*cannot* fail-closed — orchestrator events have no safe default verdict — so an
unrecognized comment no-ops (the merge gate already fails-closed and blocks the
merge, so a missed event never causes a bad merge, only a missed proactive
``/rework``). A distinct ``review_unparseable`` event (Option B) is deferred
until the reactive-core orchestrator (M44) has a triage consumer.

Two halves, per the #326 guard-test convention:
  - Logic: reimplement the emit decision rule in Python and assert it
    emits/skips for the scenarios the workflow claims to handle — including the
    literal #957 / #956 / #954 deviant comment shapes.
  - Config: assert the workflow's parser step carries the hardened selector and
    findings patterns, in findings-before-clean order, and has dropped the old
    first-line-only literal selector.

Fixture *shapes* are shared with ``test_code_review_verdict_guard.py`` on
purpose, but the suites are deliberately NOT coupled (no cross-import): each
guard's contract must be free to drift independently.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
EVENT_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "event-dispatch.yml"


# -- Decision logic (mirror of the bash in review-negative-claude-bot) --------
#
# Selector: any heading line (1-6 #'s) reading "[Claude] Code Review",
# case-insensitive, anywhere in the body. grep is line-oriented so ^ is
# line-anchored — re.M mirrors that.
TITLE_RE = re.compile(r"^#{1,6}[ \t]*(?:Claude[ \t]+)?Code[ \t]+Review", re.I | re.M)
# Findings signal #1: severity-section headings. Observed deviants:
# "### MAJOR findings" (#957), bare "### MAJOR" (#956), "### 🔴 BLOCKING" (#954).
# Decoration between the #'s and the severity word is tolerated; the
# findings/issues suffix is optional. The class excludes \n so decoration can't
# span lines under re.M (grep matches per-line).
SEVERITY_RE = re.compile(
    r"^#{1,6}[^A-Za-z0-9\n]*(?:CRITICAL|MAJOR|MINOR|BLOCKING)\b", re.I | re.M
)
# Findings signal #2: the plugin's canonical findings line (unanchored, to match
# the merge gate — a deviant bot may indent it).
FOUND_RE = re.compile(r"Found [0-9]+ issues?:")
# Clean signal: line-start anchored, NO end anchor — the plugin's clean example
# carries trailing prose ("No issues found. Checked for bugs and CLAUDE.md
# compliance."); an end-anchored regex would mis-classify it.
CLEAN_RE = re.compile(r"^No issues found\.", re.M)


def classify(comment_body: str) -> str:
    """Reimplementation of the parser step's emit decision rule.

    Returns one of:
      - 'emit'         → a review_negative event is dispatched
      - 'clean'        → recognized clean review, no event
      - 'unrecognized' → title matched but no findings/clean signal, no event
      - 'skip'         → not a Code Review verdict comment at all
    """
    if not TITLE_RE.search(comment_body):
        return "skip"
    # Findings checks run BEFORE the clean check: a stray "No issues found."
    # line must never shadow a real severity section.
    if SEVERITY_RE.search(comment_body) or FOUND_RE.search(comment_body):
        return "emit"
    if CLEAN_RE.search(comment_body):
        return "clean"
    return "unrecognized"


def n_issues(comment_body: str) -> int:
    """The N reported on an emitted event. Found-N when present, else 1
    (severity-only deviant: at least one actionable finding; /rework re-parses
    the comment for the exact set)."""
    m = FOUND_RE.search(comment_body)
    if m:
        return int(re.search(r"[0-9]+", m.group()).group())
    return 1


# -- Fixture comment shapes (shapes shared with the gate test, not imported) ---

# The literal shape that false-passed the merge gate on PR #957.
PR_957_COMMENT = """\
## Claude Code Review — PR #957

Reviewed the diff against CLAUDE.md and the plugin rubric.

### MAJOR findings

1. Regex too broad in billing classifier
2. OOM lane unprobed

### MINOR findings

1. Stale comment
2. Naming drift
"""

# PR #956: APPROVE verdict line, bare "### MAJOR" section (no "findings" suffix).
PR_956_COMMENT = """\
## Code Review — PR #956 `fix(sandcastle): address round-2 review`

**Verdict: APPROVE with action items.**

### MAJOR

1. Billing regex still matches non-billing 402s (confidence 85)
2. OOM lane untested (confidence 82)
"""

# PR #954: emoji-decorated severity headings.
PR_954_COMMENT = """\
## Code Review — PR #954

### 🔴 BLOCKING

1. SessionEnd hook drops state on crash

### 🟡 IMPORTANT (non-blocking)

1. Model tiering table drifts from settings.json
"""

CANONICAL_FINDINGS = """\
### Code review

Found 3 issues:

1. Bug one
2. Bug two
3. Bug three
"""

CANONICAL_CLEAN_SPEC = """\
### Code review

No issues found. Checked for bugs and CLAUDE.md compliance.

🤖 Generated with [Claude Code](https://claude.ai/code)
"""

SIMPLIFICATION_COMMENT = """\
### Simplification opportunities

1. Inline helper X
2. Collapse branch Y
"""

REWORK_PROGRESS_COMMENT = "Reworking PR #961 — attempt 2 pushed, re-review pending.\n"


class TestEmitLogic:
    # --- the deviant shapes that silently never emitted (the bug) ---
    def test_pr_957_major_minor_sections_emit(self):
        assert classify(PR_957_COMMENT) == "emit"

    def test_pr_956_bare_severity_with_approve_line_emits(self):
        # APPROVE-with-action-items prose, but a bare "### MAJOR" section → the
        # review IS negative; the orchestrator must fire /rework.
        assert classify(PR_956_COMMENT) == "emit"

    def test_pr_954_emoji_decorated_blocking_emits(self):
        assert classify(PR_954_COMMENT) == "emit"

    def test_severity_only_no_found_line_defaults_to_one_issue(self):
        # Severity section present, no "Found N issues:" line → emit with n=1.
        assert classify(PR_956_COMMENT) == "emit"
        assert n_issues(PR_956_COMMENT) == 1

    # --- canonical plugin formats ---
    def test_canonical_found_n_emits_with_exact_count(self):
        assert classify(CANONICAL_FINDINGS) == "emit"
        assert n_issues(CANONICAL_FINDINGS) == 3

    def test_canonical_clean_with_trailing_prose_does_not_emit(self):
        assert classify(CANONICAL_CLEAN_SPEC) == "clean"

    def test_bare_no_issues_found_does_not_emit(self):
        assert classify("### Code review\n\nNo issues found.\n") == "clean"

    def test_single_issue_singular_word_emits(self):
        body = "### Code review\n\nFound 1 issue:\n\n1. x\n"
        assert classify(body) == "emit"
        assert n_issues(body) == 1

    # --- ordering: findings must not be shadowed by a stray clean line ---
    def test_found_n_not_shadowed_by_stray_clean_line(self):
        body = "### Code review\n\nFound 2 issues:\n\n1. x\n2. y\n\nNo issues found.\n"
        assert classify(body) == "emit"

    def test_severity_not_shadowed_by_stray_clean_line(self):
        body = "## Claude Code Review\n\nNo issues found.\n\n### MAJOR\n\n1. x\n"
        assert classify(body) == "emit"

    def test_severity_decoration_does_not_span_lines(self):
        # "###" alone then prose mentioning MAJOR is not a severity heading.
        body = "## Code Review\n\n###\nMAJOR refactor someday.\n\nNo issues found.\n"
        assert classify(body) == "clean"

    # --- selector behavior ---
    def test_deviant_title_variants_are_selected(self):
        assert classify("## Code Review\n\nFound 1 issue:\n\n1. x\n") == "emit"
        assert classify("## CLAUDE CODE REVIEW\n\nFound 1 issue:\n\n1. x\n") == "emit"
        assert classify("###### code review\n\nFound 1 issue:\n\n1. x\n") == "emit"

    def test_title_heading_need_not_be_first_line(self):
        body = "Review complete, summary below.\n\n## Code Review\n\nFound 1 issue:\n\n1. x\n"
        assert classify(body) == "emit"

    def test_simplification_comment_is_not_selected(self):
        # Informational-only by design — must never fire /rework.
        assert classify(SIMPLIFICATION_COMMENT) == "skip"

    def test_rework_progress_comment_is_not_selected(self):
        assert classify(REWORK_PROGRESS_COMMENT) == "skip"

    def test_unrelated_bot_comment_is_not_selected(self):
        assert classify("merge train queued for PR #961\n") == "skip"

    # --- unrecognized: title matched, no findings/clean signal → no emit ---
    def test_unrecognized_verdict_does_not_emit(self):
        # Deviant clean-ish format (e.g. APPROVE with no severity sections and
        # no "No issues found." line). The merge gate fails-closed on this; the
        # event side no-ops (no safe default verdict). Either way no /rework.
        body = "## Code Review\n\nVerdict: APPROVE. Blocking issues — None.\n"
        assert classify(body) == "unrecognized"

    def test_empty_review_body_does_not_emit(self):
        assert classify("### Code review\n") == "unrecognized"


# -- Workflow wiring ----------------------------------------------------------


@pytest.fixture(scope="module")
def workflow_text() -> str:
    return EVENT_WORKFLOW.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def parser_step(workflow_text) -> dict:
    workflow = yaml.safe_load(workflow_text)
    steps = workflow["jobs"]["review-negative-claude-bot"]["steps"]
    return next(s for s in steps if "Parse Claude verdict" in s.get("name", ""))


@pytest.fixture(scope="module")
def parser_job(workflow_text) -> dict:
    workflow = yaml.safe_load(workflow_text)
    return workflow["jobs"]["review-negative-claude-bot"]


class TestParserStepWiring:
    def test_old_first_line_literal_selector_is_gone(self, parser_step):
        run = parser_step["run"]
        assert "^###[[:space:]]+Code review$" not in run, (
            "First-line-only literal selector is the #961 miss — it skipped "
            "every deviant title (## Code Review, ## Claude Code Review)."
        )
        assert 'head -1' not in run or "FIRST_LINE" not in run, (
            "Title match must scan the whole body, not just the first line — "
            "deviant bots prepend preamble before the heading."
        )

    def test_broadened_title_selector_present(self, parser_step):
        run = parser_step["run"]
        assert "(Claude[[:blank:]]+)?Code[[:blank:]]+Review" in run, (
            "Selector must tolerate title variants (any heading level, optional "
            "'Claude' prefix), mirroring the merge gate (PR #960)."
        )
        assert "grep -qiE" in run, "Title/severity match must be case-insensitive (-i)."

    def test_severity_heading_is_a_findings_signal(self, parser_step):
        assert (
            r"^#{1,6}[^[:alnum:]]*(CRITICAL|MAJOR|MINOR|BLOCKING)\b"
            in parser_step["run"]
        ), (
            "Severity sections (### MAJOR, '### MAJOR findings' #957, bare "
            "'### MAJOR' #956, '### 🔴 BLOCKING' #954) must count as findings — "
            "their absence is the exact #961 miss."
        )

    def test_found_n_issues_still_detected(self, parser_step):
        assert "Found [0-9]+ issues?:" in parser_step["run"]

    def test_clean_pattern_is_line_anchored_not_end_anchored(self, parser_step):
        run = parser_step["run"]
        assert r"^No issues found\." in run

    def test_findings_checked_before_clean(self, parser_step):
        run = parser_step["run"]
        severity_at = run.index("(CRITICAL|MAJOR|MINOR|BLOCKING)")
        found_at = run.index("Found [0-9]+ issues?:")
        clean_at = run.index(r"^No issues found\.")
        assert severity_at < clean_at and found_at < clean_at, (
            "Pass-equivalent (clean → no emit) must not shadow a findings "
            "signal: severity and Found-N are checked before the clean line."
        )

    def test_still_emits_review_negative(self, parser_step):
        # The curl body's JSON is inside a double-quoted shell string, so its
        # quotes are backslash-escaped in the YAML scalar — match the bare token.
        assert "review_negative" in parser_step["run"]

    def test_does_not_fail_closed_on_unrecognized(self, parser_step):
        # The event surface has no safe default verdict — the unrecognized
        # branch must no-op (exit 0), not exit 1. (Merge safety is the gate's
        # job, and it fails-closed there.)
        run = parser_step["run"]
        assert "exit 1" not in run, (
            "Event dispatch must not fail-closed (exit 1) on an unrecognized "
            "comment — that would red the issue_comment workflow run; the merge "
            "gate is what blocks the merge."
        )


class TestParserJobGate:
    def test_job_gates_on_claude_bot_pr_comment(self, parser_job):
        gate = parser_job["if"]
        assert "github.event_name == 'issue_comment'" in gate
        assert "github.event.issue.pull_request != null" in gate
        assert "claude[bot]" in gate

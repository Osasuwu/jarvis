"""Meta-test for the `Verify review verdict` step in code-review.yml.

Incident (PR #957): the Claude code-review bot posted 10 findings under a
deviant comment title ("## Claude Code Review — PR #957" with
"### MAJOR findings" / "### MINOR findings" sections). The old verdict step
selected comments by the literal prefix `### Code review`, so the deviant
comment was treated as "no comment → pass" and the PR auto-merged with
unaddressed findings.

Two halves, per the #326 guard-test convention:
  - Config: the workflow's verdict step contains the hardened selector and
    verdict patterns, in fail-before-pass order, ending fail-closed.
  - Logic: reimplement the verdict decision rule in Python and assert it
    blocks/allows the scenarios the workflow claims to handle — including
    the literal #957 comment shape.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
REVIEW_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "code-review.yml"


# -- Decision logic (mirror of the bash in the verdict step) -----------------
#
# Selector: any heading line (1-6 #'s) that reads "[Claude] Code Review",
# case-insensitive, anywhere in the body (jq/Oniguruma `^` is line-anchored).
TITLE_RE = re.compile(r"^#{1,6}[ \t]*(?:Claude[ \t]+)?Code[ \t]+Review", re.I | re.M)
# Findings signal #1: severity-section headings. Deviation is routine, not a
# one-off — observed shapes: "### MAJOR findings" (#957), bare "### MAJOR"
# (#956), "### 🔴 BLOCKING" (#954). Decoration between the #'s and the
# severity word is tolerated, the findings/issues suffix is optional. The
# class excludes \n: grep matches per-line, so the Python mirror must not
# let the decoration run span lines under re.M.
SEVERITY_RE = re.compile(
    r"^#{1,6}[^A-Za-z0-9\n]*(?:CRITICAL|MAJOR|MINOR|BLOCKING)\b", re.I | re.M
)
# Findings signal #2: the plugin's canonical findings line.
FOUND_RE = re.compile(r"Found [0-9]+ issues?:")
# Clean signal: line-start anchored, NO end anchor — the plugin spec's clean
# example is "No issues found. Checked for bugs and CLAUDE.md compliance."
# (trailing prose on the same line; an end-anchored regex fails-closed on it).
CLEAN_RE = re.compile(r"^No issues found\.", re.M)


def verdict(comment_bodies: list[str]) -> str:
    """Reimplementation of the verdict step's decision rule.

    Returns 'pass' (exit 0) or 'fail' (exit 1).
    """
    selected = [b for b in comment_bodies if TITLE_RE.search(b)]
    if not selected:
        return "pass"  # plugin skipped — no review comment at all
    body = selected[-1]  # latest review comment wins
    # Findings checks run BEFORE the clean check: pass must never shadow fail.
    if SEVERITY_RE.search(body):
        return "fail"
    if FOUND_RE.search(body):
        return "fail"
    if CLEAN_RE.search(body):
        return "pass"
    return "fail"  # unrecognized review comment — fail closed


# The literal shape that false-passed the gate on PR #957.
PR_957_COMMENT = """\
## Claude Code Review — PR #957

Reviewed the diff against CLAUDE.md and the plugin rubric.

### MAJOR findings

1. Regex too broad in billing classifier
2. OOM lane unprobed
3. Silent npm failure
4. Missing test for alert path

### MINOR findings

1. Stale comment
2. Naming drift
3. Unused import
4. Doc typo
5. Log level
6. Magic number
"""

# Real deviant shape from PR #956: APPROVE verdict line, bare "### MAJOR"
# section heading (no "findings" suffix) — yet carried 8 genuine findings.
PR_956_COMMENT = """\
## Code Review — PR #956 `fix(sandcastle): address PR #956 round-2 review`

**Verdict: APPROVE with action items.**

### MAJOR

1. Billing regex still matches non-billing 402s (confidence 85)
2. OOM lane untested (confidence 82)
"""

# Real deviant shape from PR #954: emoji-decorated severity headings.
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

RETRY_EXHAUSTED_COMMENT = (
    "WARNING: Claude code-review auto-retry exhausted after 4 attempts.\n"
    "Re-run manually: gh workflow run code-review.yml -f pr_number=957\n"
)


class TestVerdictLogic:
    # --- the incident ---
    def test_pr_957_format_fails(self):
        assert verdict([PR_957_COMMENT]) == "fail"

    def test_major_findings_heading_alone_fails(self):
        assert verdict(["## Code Review\n\n### MAJOR findings\n\n1. x\n"]) == "fail"

    def test_minor_findings_heading_alone_fails(self):
        assert verdict(["## Code Review\n\n### MINOR findings\n\n1. x\n"]) == "fail"

    def test_critical_issues_heading_variant_fails(self):
        assert verdict(["## Code Review\n\n#### CRITICAL issues\n\n1. x\n"]) == "fail"

    # --- the other observed deviants (PRs #956, #954) ---
    def test_pr_956_bare_severity_heading_fails(self):
        assert verdict([PR_956_COMMENT]) == "fail"

    def test_pr_954_emoji_decorated_blocking_heading_fails(self):
        assert verdict([PR_954_COMMENT]) == "fail"

    def test_bare_severity_heading_with_stray_clean_line_fails(self):
        # The reason the severity regex covers bare headings instead of
        # leaving them to fail-closed: a stray "No issues found." line must
        # not shadow a bare "### MAJOR" section.
        body = "## Code Review\n\nNo issues found.\n\n### MAJOR\n\n1. x\n"
        assert verdict([body]) == "fail"

    def test_severity_decoration_does_not_span_lines(self):
        # "###" alone on a line followed by prose mentioning MAJOR is not a
        # severity heading (grep matches per-line; the mirror must agree).
        body = "## Code Review\n\n###\nMAJOR refactor suggested someday.\n\nNo issues found.\n"
        assert verdict([body]) == "pass"

    # --- canonical plugin formats ---
    def test_canonical_findings_fails(self):
        assert verdict([CANONICAL_FINDINGS]) == "fail"

    def test_canonical_clean_with_spec_trailing_prose_passes(self):
        # Latent bug fixed alongside #957 hardening: the old pass regex was
        # end-anchored (`^No issues found\.?\s*$`) and would have FAILED a
        # spec-compliant clean comment, whose example line carries trailing
        # prose. Pin the relaxed anchor here.
        assert verdict([CANONICAL_CLEAN_SPEC]) == "pass"

    def test_bare_no_issues_found_passes(self):
        assert verdict(["### Code review\n\nNo issues found.\n"]) == "pass"

    def test_found_n_issues_not_shadowed_by_stray_clean_line(self):
        body = "### Code review\n\nFound 2 issues:\n\n1. x\n2. y\n\nNo issues found.\n"
        assert verdict([body]) == "fail"

    def test_severity_heading_not_shadowed_by_stray_clean_line(self):
        body = "## Claude Code Review\n\nNo issues found.\n\n### MAJOR findings\n\n1. x\n"
        assert verdict([body]) == "fail"

    # --- selector behavior ---
    def test_no_comments_passes(self):
        assert verdict([]) == "pass"

    def test_unrelated_comments_only_passes(self):
        assert verdict(["LGTM!", RETRY_EXHAUSTED_COMMENT, "merge train queued"]) == "pass"

    def test_simplification_comment_is_not_selected(self):
        # Informational-only by design (see event-dispatch.yml) — must never
        # gate the merge, even though it lists numbered opportunities.
        assert verdict([SIMPLIFICATION_COMMENT]) == "pass"

    def test_deviant_title_clean_body_passes(self):
        assert verdict(["## Claude Code Review — PR #960\n\nNo issues found.\n"]) == "pass"

    def test_title_selector_is_case_insensitive(self):
        assert verdict(["### code review\n\nFound 1 issue:\n\n1. x\n"]) == "fail"
        assert verdict(["## CODE REVIEW\n\nNo issues found.\n"]) == "pass"

    def test_title_heading_mid_body_is_selected(self):
        # Deviant bots may prepend preamble — the heading need not be line 1.
        body = "Review complete, summary below.\n\n## Code Review\n\nFound 1 issue:\n\n1. x\n"
        assert verdict([body]) == "fail"

    def test_latest_review_comment_wins(self):
        assert verdict([CANONICAL_FINDINGS, CANONICAL_CLEAN_SPEC]) == "pass"
        assert verdict([CANONICAL_CLEAN_SPEC, CANONICAL_FINDINGS]) == "fail"
        # Non-review comments in between don't affect selection.
        assert verdict([CANONICAL_FINDINGS, "thanks, reworking", CANONICAL_CLEAN_SPEC]) == "pass"

    # --- fail-closed ---
    def test_unrecognized_review_comment_fails_closed(self):
        assert verdict(["## Code Review\n\nEverything looks great! Ship it.\n"]) == "fail"

    def test_empty_verdict_section_fails_closed(self):
        assert verdict(["### Code review\n"]) == "fail"


# -- Workflow wiring ----------------------------------------------------------


@pytest.fixture(scope="module")
def workflow_text() -> str:
    return REVIEW_WORKFLOW.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def verdict_step(workflow_text) -> dict:
    workflow = yaml.safe_load(workflow_text)
    steps = workflow["jobs"]["review"]["steps"]
    return next(s for s in steps if s.get("name") == "Verify review verdict")


class TestVerdictStepWiring:
    def test_step_exists_and_gates_on_pull_request(self, verdict_step):
        assert verdict_step["if"] == "github.event_name == 'pull_request'"

    def test_selector_matches_title_variants_not_literal_prefix(self, verdict_step):
        run = verdict_step["run"]
        assert 'startswith("### Code review")' not in run, (
            "Literal-prefix selector is the #957 false-pass hole — the deviant "
            "'## Claude Code Review' title was treated as 'no comment → pass'."
        )
        assert r"(^|\\n)#{1,6}[ \\t]*(Claude[ \\t]+)?Code[ \\t]+Review" in run, (
            "Selector must tolerate title variants (any heading level, "
            "optional 'Claude' prefix) and must anchor with (^|\\n), not ^ — "
            "gh's --jq is gojq (Go regexp), where ^ matches string start "
            "only, silently unselecting a heading preceded by preamble."
        )
        assert '"i"' in run, "Title selector must be case-insensitive."

    def test_selector_slurps_pagination_via_standalone_jq(self, verdict_step):
        run = verdict_step["run"]
        assert "--paginate" in run
        assert "jq -rs 'add" in run, (
            "Pages must be slurped (-s) and flattened (add) in standalone jq "
            "so .[-1] is the global-latest review comment, not per-page."
        )
        # Check command lines only — the step's comments legitimately
        # explain WHY --slurp is absent.
        code_lines = "\n".join(
            line for line in run.splitlines() if not line.lstrip().startswith("#")
        )
        assert "--slurp" not in code_lines, (
            "gh rejects --slurp combined with --jq at runtime (exit 1) — "
            "with set -euo pipefail the gate would go permanently red."
        )

    def test_severity_headings_fail_the_gate(self, verdict_step):
        assert (
            r"^#{1,6}[^[:alnum:]]*(CRITICAL|MAJOR|MINOR|BLOCKING)\b"
            in verdict_step["run"]
        ), (
            "Severity pattern must cover every observed deviant shape: "
            "'### MAJOR findings' (#957), bare '### MAJOR' (#956), "
            "'### 🔴 BLOCKING' (#954) — decoration tolerated, suffix optional."
        )

    def test_found_n_issues_fails_the_gate(self, verdict_step):
        assert "Found [0-9]+ issues?:" in verdict_step["run"]

    def test_clean_pattern_is_not_end_anchored(self, verdict_step):
        run = verdict_step["run"]
        assert r"^No issues found\." in run
        assert r"^No issues found\.?\s*$" not in run, (
            "End-anchored clean regex rejects the plugin spec's own clean "
            "example ('No issues found. Checked for bugs and CLAUDE.md "
            "compliance.') and would fail-closed every spec-compliant clean "
            "review."
        )

    def test_findings_checks_run_before_clean_check(self, verdict_step):
        run = verdict_step["run"]
        severity_at = run.index("(CRITICAL|MAJOR|MINOR|BLOCKING)")
        found_at = run.index("Found [0-9]+ issues?:")
        clean_at = run.index(r"^No issues found\.")
        assert severity_at < clean_at and found_at < clean_at, (
            "Pass must never shadow fail: findings patterns are checked "
            "before the clean pattern."
        )

    def test_step_ends_fail_closed(self, verdict_step):
        assert verdict_step["run"].strip().endswith("exit 1"), (
            "Unrecognized verdict format must fail closed (exit 1), not fall "
            "through to success — that fall-through is how #957 auto-merged."
        )

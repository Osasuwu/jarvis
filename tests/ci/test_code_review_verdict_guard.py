"""Meta-test for the `Verify review verdict` step in code-review.yml.

Two-gate model (#988, milestone #52): the MERGE gate blocks ONLY on a real
merge-blocking finding — an all-caps CRITICAL / MAJOR / BLOCKING severity
heading. MINOR / NITPICK / LOW / INFO / MEDIUM never block merge, and a bare
"Found N issues:" line (no blocking heading) no longer blocks — in practice the
plugin emits severity sections for real bugs (#963/#964/#965/#966) and the
canonical "Found N issues:" has carried only advisory MEDIUM/LOW (#956). This
unjams the #976 deadlock where clean-but-minor PRs were rejected by the gate
while the rework loop considered them done.

#976 fold: the block check is case-SENSITIVE all-caps (`grep -qE`, not `-qiE`)
so title-case prose like "Blocking issues — None" (#962) is no longer a false
block. The real plugin severity sections are always all-caps.

Incident still guarded (PR #957): the bot posted findings under a deviant title
with "### MAJOR findings" / "### MINOR findings" sections; the old literal
`### Code review` selector treated that as "no comment → pass" and the PR
auto-merged. The selector still tolerates title variants, and a `### MAJOR`
section still fails the gate.

Two halves, per the #326 guard-test convention:
  - Config: the workflow's verdict step contains the hardened selector and
    verdict patterns, block-before-pass order, ending fail-closed.
  - Logic: reimplement the verdict decision rule in Python and assert it
    blocks/allows the scenarios the workflow claims to handle.
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

# BLOCK signal: an all-caps CRITICAL / MAJOR / BLOCKING severity heading. This
# is the ONLY merge-blocking shape (two-gate model, #988). MINOR is dropped —
# minors never block merge. Case-SENSITIVE (no re.I, #976): the real plugin
# severity sections are all-caps ("### MAJOR", "### 🔴 BLOCKING"); title-case
# prose ("### Blocking issues — None", #962) must NOT match. Decoration between
# the #'s and the keyword is tolerated; the class excludes \n so the decoration
# run cannot span lines under re.M (grep matches per-line).
BLOCK_RE = re.compile(r"^#{1,6}[^A-Za-z0-9\n]*(?:CRITICAL|MAJOR|BLOCKING)\b", re.M)

# Clean signal: line-start anchored, NO end anchor — the plugin spec's clean
# example is "No issues found. Checked for bugs and CLAUDE.md compliance."
# (trailing prose on the same line; an end-anchored regex fails-closed on it).
CLEAN_RE = re.compile(r"^No issues found\.", re.M)

# "No blockers" prose: the 8-reviewer APPROVE summary "Blocking issues — None"
# (#962). Case-insensitive, matched within a single line (the class excludes
# \n). Only consulted AFTER the block check, so it can never shadow a real
# severity heading.
NO_BLOCKERS_RE = re.compile(r"blocking issues\b[^A-Za-z0-9\n]*none\b", re.I)

# Findings present but none blocking: the plugin's canonical "Found N issues:"
# line (#956 carried only MEDIUM/LOW advisories). No longer a fail signal.
FOUND_RE = re.compile(r"Found [0-9]+ issues?:")

# Non-blocking severity sections only: MINOR-only (#963), or MEDIUM/LOW/INFO/
# NITPICK advisories with no "Found N" line. All-caps, same decoration rules
# as BLOCK_RE.
NONBLOCK_SEV_RE = re.compile(
    r"^#{1,6}[^A-Za-z0-9\n]*(?:MINOR|NITPICK|LOW|INFO|MEDIUM)\b", re.M
)


def verdict(comment_bodies: list[str]) -> str:
    """Reimplementation of the verdict step's decision rule.

    Returns 'pass' (exit 0) or 'fail' (exit 1).
    """
    selected = [b for b in comment_bodies if TITLE_RE.search(b)]
    if not selected:
        return "pass"  # plugin skipped — no review comment at all
    body = selected[-1]  # latest review comment wins
    # BLOCK check runs first: a pass signal must never shadow a CRITICAL/MAJOR/
    # BLOCKING heading.
    if BLOCK_RE.search(body):
        return "fail"
    # No blocking severity heading. Any recognized non-blocking shape passes.
    if CLEAN_RE.search(body):
        return "pass"
    if NO_BLOCKERS_RE.search(body):
        return "pass"
    if FOUND_RE.search(body):
        return "pass"
    if NONBLOCK_SEV_RE.search(body):
        return "pass"
    return "fail"  # unrecognized review comment — fail closed


# The literal shape that false-passed the gate on PR #957: MAJOR + MINOR
# sections. MAJOR still blocks.
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
# section heading (no "findings" suffix) — yet carried genuine major findings.
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

# Real shape from PR #962 (#976 deadlock): an explicit APPROVE summary whose
# "### Blocking issues — None" header is title-case. The old case-insensitive
# regex matched the title-case word "Blocking" and FALSE-BLOCKED a clean PR.
PR_962_COMMENT = """\
## Code Review — PR #962

### Verdict: APPROVE ✅

### Blocking issues — None

All findings below are explicitly non-blocking.

### Notes (non-blocking)

1. Consider renaming `foo` for clarity
"""

# Canonical findings, no severity heading — under the two-gate model this is
# NON-blocking (the bot emits severity sections for real bugs; bare Found-N has
# been advisory, #956).
CANONICAL_FINDINGS = """\
### Code review

Found 3 issues:

1. Bug one
2. Bug two
3. Bug three
"""

# A findings comment whose only severity sections are MINOR (#963 shape) — must
# PASS (AC fixture (a)/(d)).
CANONICAL_MINOR_ONLY = """\
### Code review

Found 2 issues:

### MINOR

1. Naming drift
2. Stale comment
"""

# MINOR-only deviant sections with no "Found N" line — must PASS.
MINOR_ONLY_SECTIONS = """\
## Code Review — PR #963

### MINOR

1. Prefer f-string here
2. Docstring wording
"""

# A real blocking comment used to prove latest-wins / selection (MAJOR blocks).
BLOCKING_COMMENT = """\
### Code review

### MAJOR

1. Null deref on empty input
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
    # --- blocking: CRITICAL / MAJOR / BLOCKING all-caps headings fail ---
    def test_pr_957_major_section_fails(self):
        assert verdict([PR_957_COMMENT]) == "fail"

    def test_major_findings_heading_alone_fails(self):
        assert verdict(["## Code Review\n\n### MAJOR findings\n\n1. x\n"]) == "fail"

    def test_critical_issues_heading_variant_fails(self):
        assert verdict(["## Code Review\n\n#### CRITICAL issues\n\n1. x\n"]) == "fail"

    def test_pr_956_bare_major_heading_fails(self):
        assert verdict([PR_956_COMMENT]) == "fail"

    def test_pr_954_emoji_decorated_blocking_heading_fails(self):
        assert verdict([PR_954_COMMENT]) == "fail"

    def test_bare_major_heading_with_stray_clean_line_fails(self):
        # A stray "No issues found." line must not shadow a "### MAJOR" section.
        body = "## Code Review\n\nNo issues found.\n\n### MAJOR\n\n1. x\n"
        assert verdict([body]) == "fail"

    def test_major_heading_with_stray_no_blockers_line_fails(self):
        # "Blocking issues — None" prose must not shadow a real "### MAJOR".
        body = (
            "## Code Review\n\n### Blocking issues — None\n\n### MAJOR\n\n1. real bug\n"
        )
        assert verdict([body]) == "fail"

    def test_severity_decoration_does_not_span_lines(self):
        # "###" alone on a line followed by prose mentioning MAJOR is not a
        # severity heading (grep matches per-line; the mirror must agree).
        body = "## Code Review\n\n###\nMAJOR refactor suggested someday.\n\nNo issues found.\n"
        assert verdict([body]) == "pass"

    # --- minors / advisories never block (two-gate, #988) ---
    def test_minor_findings_heading_alone_passes(self):
        # WAS fail under the old gate — the core #976 unjam.
        assert verdict(["## Code Review\n\n### MINOR findings\n\n1. x\n"]) == "pass"

    def test_minor_only_sections_no_found_line_passes(self):
        assert verdict([MINOR_ONLY_SECTIONS]) == "pass"

    def test_canonical_minor_only_passes(self):
        assert verdict([CANONICAL_MINOR_ONLY]) == "pass"

    def test_low_info_nitpick_medium_headings_pass(self):
        for sev in ("LOW", "INFO", "NITPICK", "MEDIUM"):
            body = f"## Code Review\n\n### {sev}\n\n1. advisory note\n"
            assert verdict([body]) == "pass", sev

    def test_lowercase_severity_keyword_is_not_a_block(self):
        # Case-sensitive block keyword (#976): lowercase prose is not a real
        # severity section. Falls through to fail-closed (no recognized shape),
        # which is the conservative outcome — not a block masquerading as one.
        body = "## Code Review\n\n### blocking issues — none\n"
        # "blocking issues — none" matches the (case-insensitive) no-blockers
        # prose signal, so this clean APPROVE passes.
        assert verdict([body]) == "pass"

    # --- "Blocking issues — None" / APPROVE (#962, #976) ---
    def test_pr_962_approve_no_blockers_passes(self):
        assert verdict([PR_962_COMMENT]) == "pass"

    def test_titlecase_blocking_none_header_passes(self):
        assert verdict(["## Code Review\n\n### Blocking issues — None\n"]) == "pass"

    # --- canonical findings with no severity heading: non-blocking ---
    def test_canonical_findings_no_severity_passes(self):
        # Two-gate decision: a bare "Found N issues:" with no CRITICAL/MAJOR/
        # BLOCKING heading does NOT block (residual risk accepted per #988).
        assert verdict([CANONICAL_FINDINGS]) == "pass"

    # --- clean ---
    def test_canonical_clean_with_spec_trailing_prose_passes(self):
        assert verdict([CANONICAL_CLEAN_SPEC]) == "pass"

    def test_bare_no_issues_found_passes(self):
        assert verdict(["### Code review\n\nNo issues found.\n"]) == "pass"

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
        # A no-severity findings comment now PASSES (non-blocking).
        assert verdict(["### code review\n\nFound 1 issue:\n\n1. x\n"]) == "pass"
        assert verdict(["## CODE REVIEW\n\nNo issues found.\n"]) == "pass"

    def test_title_heading_mid_body_is_selected(self):
        # Deviant bots may prepend preamble — the heading need not be line 1.
        # Prove selection with a blocking comment (selection → fail).
        body = "Review complete, summary below.\n\n## Code Review\n\n### MAJOR\n\n1. x\n"
        assert verdict([body]) == "fail"

    def test_latest_review_comment_wins(self):
        # latest blocking → fail; latest clean → pass.
        assert verdict([BLOCKING_COMMENT, CANONICAL_CLEAN_SPEC]) == "pass"
        assert verdict([CANONICAL_CLEAN_SPEC, BLOCKING_COMMENT]) == "fail"
        # Non-review comments in between don't affect selection.
        assert verdict([BLOCKING_COMMENT, "thanks, reworking", CANONICAL_CLEAN_SPEC]) == "pass"

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


@pytest.fixture(scope="module")
def review_step(workflow_text) -> dict:
    workflow = yaml.safe_load(workflow_text)
    steps = workflow["jobs"]["review"]["steps"]
    return next(s for s in steps if s.get("name") == "Run /code-review")


class TestReviewStepBotGate:
    def test_allowed_bots_wildcard_is_set(self, review_step):
        # claude-code-action@v1's `allowed_bots` gate hard-fails on a Bot
        # actor. Two legitimate bot triggers feed the `review` check:
        # code-review-retry.yml (workflow_dispatch as github-actions[bot]) and
        # merge-train.yml's update-branch (synchronize as the App token). With
        # this unset, every retried / merge-train-updated PR jams the gate.
        assert review_step["with"].get("allowed_bots") == "*", (
            "Run /code-review must set allowed_bots: '*' — otherwise bot-"
            "triggered runs (retry dispatch, merge-train synchronize) fail at "
            "the action level and the `review` check goes permanently red."
        )


class TestVerdictStepWiring:
    def test_step_gates_on_pull_request_and_dispatch(self, verdict_step):
        # MUST also run on workflow_dispatch: the retry path
        # (code-review-retry.yml) dispatches with --ref <head_branch>, so its
        # check attaches to the PR head SHA and feeds the `review` gate.
        gate = verdict_step["if"]
        assert "github.event_name == 'pull_request'" in gate
        assert "github.event_name == 'workflow_dispatch'" in gate, (
            "Verdict must enforce on the retry (workflow_dispatch) path, not "
            "just pull_request — else the retry path is an auto-merge bypass."
        )

    def test_selector_matches_title_variants_not_literal_prefix(self, verdict_step):
        run = verdict_step["run"]
        assert 'startswith("### Code review")' not in run, (
            "Literal-prefix selector is the #957 false-pass hole."
        )
        assert r"(^|\\n)#{1,6}[ \\t]*(Claude[ \\t]+)?Code[ \\t]+Review" in run, (
            "Selector must tolerate title variants (any heading level, "
            "optional 'Claude' prefix) and anchor with (^|\\n), not ^."
        )
        assert '"i"' in run, "Title selector must be case-insensitive."

    def test_selector_slurps_pagination_via_standalone_jq(self, verdict_step):
        run = verdict_step["run"]
        assert "--paginate" in run
        assert "jq -rs 'add" in run, (
            "Pages must be slurped (-s) and flattened (add) in standalone jq "
            "so .[-1] is the global-latest review comment, not per-page."
        )
        code_lines = "\n".join(
            line for line in run.splitlines() if not line.lstrip().startswith("#")
        )
        assert "--slurp" not in code_lines, (
            "gh rejects --slurp combined with --jq at runtime (exit 1)."
        )

    def test_block_headings_are_critical_major_blocking_only(self, verdict_step):
        run = verdict_step["run"]
        assert r"^#{1,6}[^[:alnum:]]*(CRITICAL|MAJOR|BLOCKING)\b" in run, (
            "Block pattern must cover the real plugin severity sections: "
            "'### MAJOR' (#956), '### MAJOR findings' (#957), "
            "'### 🔴 BLOCKING' (#954) — decoration tolerated, suffix optional."
        )
        assert "(CRITICAL|MAJOR|MINOR|BLOCKING)" not in run, (
            "MINOR must be DROPPED from the block alternation (two-gate, #988) "
            "— minors never block merge."
        )

    def test_block_check_is_case_sensitive_allcaps(self, verdict_step):
        # #976: the block grep must be `-qE` (case-sensitive), NOT `-qiE` —
        # else title-case prose like "Blocking issues — None" false-blocks.
        run = verdict_step["run"]
        assert "grep -qE '^#{1,6}[^[:alnum:]]*(CRITICAL|MAJOR|BLOCKING)" in run, (
            "Block check must be case-sensitive (grep -qE, no -i) so all-caps "
            "is the discriminator between real severity sections and title-"
            "case prose (#976)."
        )
        assert "grep -qiE '^#{1,6}[^[:alnum:]]*(CRITICAL" not in run, (
            "Block check must not use -i (case-insensitive) — that is the "
            "#962 false-block bug."
        )

    def test_found_n_issues_is_a_nonblocking_pass(self, verdict_step):
        run = verdict_step["run"]
        assert "Found [0-9]+ issues?:" in run, (
            "Found-N pattern must still be recognized — as a NON-blocking "
            "pass signal now (two-gate, #988)."
        )
        block_at = run.index("(CRITICAL|MAJOR|BLOCKING)")
        found_at = run.index("Found [0-9]+ issues?:")
        assert block_at < found_at, (
            "Block check must precede the Found-N pass branch."
        )
        # The Found-N branch must lead to a pass (exit 0), not a block. The
        # branch spans the if-guard, a count-extraction line, the notice, and
        # exit 0 — widen the slice to cover it without reaching the next branch.
        found_branch = run[found_at:found_at + 380]
        assert "exit 0" in found_branch and "exit 1" not in found_branch, (
            "A 'Found N issues:' comment with no blocking heading must PASS "
            "(exit 0), not block (#956 advisory-only false-block)."
        )

    def test_no_blockers_prose_is_a_pass(self, verdict_step):
        # "Blocking issues — None" (#962) must be a positive pass, matched
        # case-insensitively (it is title-case prose).
        run = verdict_step["run"]
        assert "blocking issues" in run.lower(), (
            "A 'Blocking issues — None' APPROVE summary (#962) must be "
            "recognized as a pass."
        )

    def test_nonblocking_severity_headings_pass(self, verdict_step):
        run = verdict_step["run"]
        assert r"^#{1,6}[^[:alnum:]]*(MINOR|NITPICK|LOW|INFO|MEDIUM)\b" in run, (
            "Minor-only / advisory-only severity sections must be a positive "
            "pass signal (#963)."
        )

    def test_clean_pattern_is_not_end_anchored(self, verdict_step):
        run = verdict_step["run"]
        assert r"^No issues found\." in run
        assert r"^No issues found\.?\s*$" not in run, (
            "End-anchored clean regex rejects the plugin spec's own clean "
            "example and would fail-closed every spec-compliant clean review."
        )

    def test_block_check_runs_before_all_pass_checks(self, verdict_step):
        run = verdict_step["run"]
        block_at = run.index("(CRITICAL|MAJOR|BLOCKING)")
        clean_at = run.index(r"^No issues found\.")
        found_at = run.index("Found [0-9]+ issues?:")
        nonblock_at = run.index("(MINOR|NITPICK|LOW|INFO|MEDIUM)")
        assert block_at < clean_at, "Clean line must not shadow a block heading."
        assert block_at < found_at, "Found-N must not shadow a block heading."
        assert block_at < nonblock_at, (
            "Non-blocking severity check must run after the block check."
        )

    def test_step_ends_fail_closed(self, verdict_step):
        assert verdict_step["run"].strip().endswith("exit 1"), (
            "Unrecognized verdict format must fail closed (exit 1), not fall "
            "through to success — that fall-through is how #957 auto-merged."
        )

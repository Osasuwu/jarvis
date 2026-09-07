"""Meta-test for the `review-negative-claude-bot` parser in event-dispatch.yml.

Two-gate alignment (#992, re-grounded on the `{blocking, findings}` shape by
#1816): the event-side `review_negative` trigger must use the SAME
merge-blocking predicate as the MERGE gate in code-review.yml. The structured
`<!-- code-review-findings -->` JSON marker is authoritative in both
directions when present (fail-closed on a malformed/legacy-shaped payload);
the legacy all-caps CRITICAL/MAJOR/BLOCKING/MEDIUM severity-heading check is
kept ONLY as a fallback for comments that predate #1816 and carry no marker
at all.

This guard pins the corrected contract along the #326 two-dimension convention:
  - Config: the parser step contains the canonical block pattern (byte-identical
    to code-review.yml) for the legacy-fallback path, is case-sensitive, drops
    MINOR, and matches the structured marker/JSON extraction the same way
    scripts/review_debt_collector.py and code-review.yml's "Verify review
    verdict" step do.
  - Logic: reimplement the emit/skip decision (and findings/fingerprint
    derivation) in Python and assert it fires on the blocking shapes, stays
    silent on the non-blocking ones, and fails closed on a malformed marker.

event-dispatch.yml is event-triggered (not path-filtered), so #326 does not
strictly mandate this test — but PRD #41 calls this parser "the only fragile
string-match in the system", which earns a logic pin regardless.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
EVENT_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "event-dispatch.yml"
REVIEW_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "code-review.yml"


# -- Decision logic (mirror of the bash in the parser step) ------------------
#
# Title selector: a heading "(Claude )?Code Review" on any line, case-
# insensitive (grep -qiE). Mirrors the merge-gate selector; grep is line-
# anchored so a bare `^` is the line-start equivalent of the gate's `(^|\n)`.
TITLE_RE = re.compile(r"^#{1,6}[ \t]*(?:Claude[ \t]+)?Code[ \t]+Review", re.I | re.M)

# Structured marker: `<!-- code-review-findings ... -->` on its own lines.
# Mirrors the bash `grep -q '<!-- *code-review-findings'` detection and the
# `sed -n '/<!-- *code-review-findings/,/-->/p' | sed '1d;$d'` extraction —
# take the lines strictly between the marker-open line and the first `-->`
# line found after it.
MARKER_OPEN_RE = re.compile(r"<!-- *code-review-findings")

# Legacy BLOCK signal: an all-caps CRITICAL/MAJOR/BLOCKING/MEDIUM severity
# heading — the ONLY merge-blocking shapes under the pre-#1816 prose contract
# (two-gate, #988/#992; MEDIUM promoted from advisory, #1385 follow-up).
# Byte-identical to the legacy fallback in code-review.yml. Case-SENSITIVE
# (no re.I): real plugin severity sections are all-caps; title-case prose
# ("### Blocking issues — None", #962) must NOT match. MINOR dropped —
# minors never block.
BLOCK_RE = re.compile(r"^#{1,6}[^A-Za-z0-9\n]*(?:CRITICAL|MAJOR|BLOCKING|MEDIUM)\b", re.M)


def _extract_findings_block(comment_body: str) -> str | None:
    """Mirror of the bash marker detection + extraction.

    Returns the raw text between the `<!-- code-review-findings` line and the
    first subsequent line containing `-->`, or None if no marker is present.
    """
    lines = comment_body.splitlines()
    start = None
    end = None
    for i, line in enumerate(lines):
        if start is None and MARKER_OPEN_RE.search(line):
            start = i
            continue
        if start is not None and "-->" in line:
            end = i
            break
    if start is None or end is None:
        return None
    return "\n".join(lines[start + 1 : end])


def parse_verdict(comment_body: str) -> tuple[bool, list]:
    """Reimplementation of the parser's blocking/findings resolution (#1816).

    Three-tier resolution order, mirroring scripts/review_debt_collector.py's
    has_blocking_finding() and code-review.yml's "Verify review verdict" step
    byte-for-byte:
      1. Structured marker present + valid JSON + boolean `blocking` +
         array `findings` → authoritative, both directions.
      2. Marker present but malformed JSON, or missing/wrong-typed fields →
         fail closed (blocking=True, findings=[]).
      3. Marker absent entirely → legacy prose severity-heading fallback.

    Returns (blocking, findings).
    """
    block = _extract_findings_block(comment_body)
    if block is not None:
        try:
            data = json.loads(block)
        except json.JSONDecodeError:
            return True, []
        if not isinstance(data, dict):
            return True, []
        blocking_val = data.get("blocking")
        findings_val = data.get("findings")
        if not isinstance(blocking_val, bool) or not isinstance(findings_val, list):
            return True, []
        blocking = blocking_val
        findings = findings_val if blocking else []
        return blocking, findings
    return bool(BLOCK_RE.search(comment_body)), []


def fingerprint(findings: list) -> list[str]:
    """Mirror of `jq -c '[.[] | "\\(.class)|\\(.file)"] | unique'` (#1816 step 13)."""
    return sorted({f"{f['class']}|{f['file']}" for f in findings})


def should_emit(comment_body: str) -> bool:
    """Reimplementation of the parser's emit decision.

    Returns True iff a `review_negative` event would be dispatched.
    """
    if not TITLE_RE.search(comment_body):
        return False  # not a code-review verdict comment
    blocking, _ = parse_verdict(comment_body)
    return blocking


# -- Fixtures: real / representative comment shapes ---------------------------

PR_957_MAJOR = """\
## Claude Code Review — PR #957

### MAJOR findings

1. Regex too broad
2. OOM lane unprobed
"""

PR_956_BARE_MAJOR = """\
## Code Review — PR #956

**Verdict: APPROVE with action items.**

### MAJOR

1. Billing regex still matches non-billing 402s
"""

PR_954_BLOCKING = """\
## Code Review — PR #954

### 🔴 BLOCKING

1. SessionEnd hook drops state on crash
"""

CRITICAL_COMMENT = """\
### Code review

#### CRITICAL issues

1. Null deref on empty input
"""

# The #992 false-positive: bare "Found N issues:" with no severity heading. Old
# parser EMITTED; two-gate parser must SKIP (non-blocking).
FOUND_N_NO_SEVERITY = """\
### Code review

Found 3 issues:

1. Bug one
2. Bug two
3. Bug three
"""

MINOR_ONLY = """\
### Code review

Found 2 issues:

### MINOR

1. Naming drift
2. Stale comment
"""

CLEAN = """\
### Code review

No issues found. Checked for bugs and CLAUDE.md compliance.
"""

APPROVE_NO_BLOCKERS = """\
## Code Review — PR #962

### Verdict: APPROVE ✅

### Blocking issues — None
"""

SIMPLIFICATION = """\
### Simplification opportunities

1. Inline helper X
2. Collapse branch Y
"""

ORCHESTRATOR_DISPATCH = "Re-queued event evt_123 for the orchestrator.\n"

# -- Structured {blocking, findings} marker shapes (#1816) --------------------

STRUCTURED_BLOCKING = """\
### Code review

<!-- code-review-findings
{"blocking": true, "findings": [{"class": "regression", "file": "src/foo.py"}]}
-->
"""

STRUCTURED_PASS = """\
### Code review

<!-- code-review-findings
{"blocking": false, "findings": []}
-->
"""

# Marker present but blocking=false while the prose ALSO happens to carry a
# MAJOR heading (e.g. LLM narrative referencing a fixed issue) — the
# structured marker is authoritative, the legacy fallback must NOT be
# consulted once a marker is present.
STRUCTURED_PASS_WITH_STALE_MAJOR_PROSE = """\
### Code review

Previously flagged as MAJOR, now resolved.

<!-- code-review-findings
{"blocking": false, "findings": []}
-->
"""

STRUCTURED_MALFORMED_JSON = """\
### Code review

<!-- code-review-findings
{not valid json
-->
"""

STRUCTURED_MISSING_BLOCKING_FIELD = """\
### Code review

<!-- code-review-findings
{"findings": []}
-->
"""

STRUCTURED_NONBOOL_BLOCKING = """\
### Code review

<!-- code-review-findings
{"blocking": "true", "findings": []}
-->
"""

STRUCTURED_NONARRAY_FINDINGS = """\
### Code review

<!-- code-review-findings
{"blocking": true, "findings": "oops"}
-->
"""


class TestEmitDecision:
    # --- blocking shapes EMIT (legacy prose, no marker) ---
    def test_major_findings_section_emits(self):
        assert should_emit(PR_957_MAJOR) is True

    def test_bare_major_heading_emits(self):
        assert should_emit(PR_956_BARE_MAJOR) is True

    def test_emoji_decorated_blocking_emits(self):
        assert should_emit(PR_954_BLOCKING) is True

    def test_critical_section_emits(self):
        assert should_emit(CRITICAL_COMMENT) is True

    def test_deviant_title_with_major_emits(self):
        # Header-loosening (#992 consequence 2): a deviant title must not hide a
        # real blocker from the trigger.
        assert should_emit("## Claude Code Review — PR #960\n\n### MAJOR\n\n1. x\n") is True

    # --- non-blocking shapes SKIP (legacy prose, no marker) ---
    def test_found_n_no_severity_skips(self):
        # The core #992 false-positive fix: bare Found-N no longer triggers.
        assert should_emit(FOUND_N_NO_SEVERITY) is False

    def test_minor_only_skips(self):
        assert should_emit(MINOR_ONLY) is False

    def test_clean_skips(self):
        assert should_emit(CLEAN) is False

    def test_approve_no_blockers_skips(self):
        assert should_emit(APPROVE_NO_BLOCKERS) is False

    def test_lowercase_severity_is_not_a_block(self):
        # Case-sensitive (mirrors #976): lowercase prose is not a severity head.
        assert should_emit("### Code review\n\n### major\n\n1. x\n") is False

    # --- non-review comments SKIP at the title gate ---
    def test_simplification_comment_skips(self):
        assert should_emit(SIMPLIFICATION) is False

    def test_orchestrator_dispatch_comment_skips(self):
        assert should_emit(ORCHESTRATOR_DISPATCH) is False

    def test_minor_section_under_review_title_does_not_block(self):
        # Even with a valid review title, MINOR alone is non-blocking.
        assert should_emit("### Code review\n\n### MINOR\n\n1. nit\n") is False

    # --- structured {blocking, findings} marker (#1816) ---
    def test_structured_blocking_emits(self):
        assert should_emit(STRUCTURED_BLOCKING) is True

    def test_structured_pass_skips(self):
        assert should_emit(STRUCTURED_PASS) is False

    def test_structured_marker_overrides_stale_prose(self):
        # Marker is authoritative once present — a leftover MAJOR mention in
        # the narrative must not resurrect a blocking verdict.
        assert should_emit(STRUCTURED_PASS_WITH_STALE_MAJOR_PROSE) is False

    def test_structured_malformed_json_fails_closed_emits(self):
        assert should_emit(STRUCTURED_MALFORMED_JSON) is True

    def test_structured_missing_blocking_field_fails_closed_emits(self):
        assert should_emit(STRUCTURED_MISSING_BLOCKING_FIELD) is True

    def test_structured_nonbool_blocking_fails_closed_emits(self):
        assert should_emit(STRUCTURED_NONBOOL_BLOCKING) is True

    def test_structured_nonarray_findings_fails_closed_emits(self):
        assert should_emit(STRUCTURED_NONARRAY_FINDINGS) is True


class TestFindingsAndFingerprint:
    def test_findings_extracted_from_structured_marker(self):
        blocking, findings = parse_verdict(STRUCTURED_BLOCKING)
        assert blocking is True
        assert findings == [{"class": "regression", "file": "src/foo.py"}]

    def test_findings_empty_on_legacy_fallback(self):
        # No per-finding class/file is derivable from prose alone (#1816 step 13).
        blocking, findings = parse_verdict(PR_957_MAJOR)
        assert blocking is True
        assert findings == []

    def test_findings_empty_when_pass(self):
        blocking, findings = parse_verdict(STRUCTURED_PASS)
        assert blocking is False
        assert findings == []

    def test_findings_empty_on_fail_closed_path(self):
        blocking, findings = parse_verdict(STRUCTURED_MALFORMED_JSON)
        assert blocking is True
        assert findings == []

    def test_fingerprint_sorted_and_deduped(self):
        findings = [
            {"class": "regression", "file": "b.py"},
            {"class": "regression", "file": "b.py"},
            {"class": "performance", "file": "a.py"},
        ]
        assert fingerprint(findings) == ["performance|a.py", "regression|b.py"]

    def test_fingerprint_empty_on_no_findings(self):
        assert fingerprint([]) == []


# -- Workflow wiring ----------------------------------------------------------


@pytest.fixture(scope="module")
def parser_run() -> str:
    workflow = yaml.safe_load(EVENT_WORKFLOW.read_text(encoding="utf-8"))
    steps = workflow["jobs"]["review-negative-claude-bot"]["steps"]
    step = next(s for s in steps if s.get("name") == "Parse Claude verdict and dispatch event")
    return step["run"]


class TestParserWiring:
    def test_block_pattern_present_and_canonical(self, parser_run):
        assert r"^#{1,6}[^[:alnum:]]*(CRITICAL|MAJOR|BLOCKING|MEDIUM)\b" in parser_run, (
            "Parser's legacy fallback must key the emit decision on the all-caps "
            "CRITICAL/MAJOR/BLOCKING/MEDIUM severity heading (two-gate, #992; "
            "MEDIUM promoted #1385 follow-up)."
        )

    def test_block_pattern_byte_identical_to_merge_gate(self, parser_run):
        # The whole point of #992: event trigger and merge gate share ONE
        # legacy-fallback predicate. Pin them to the same literal so they
        # cannot drift apart.
        review_run = REVIEW_WORKFLOW.read_text(encoding="utf-8")
        pattern = r"^#{1,6}[^[:alnum:]]*(CRITICAL|MAJOR|BLOCKING|MEDIUM)\b"
        assert pattern in parser_run and pattern in review_run, (
            "Legacy block pattern must be byte-identical in event-dispatch.yml "
            "and code-review.yml — divergence reopens the two-gate alignment gap."
        )

    def test_block_check_is_case_sensitive(self, parser_run):
        assert "grep -qE '^#{1,6}[^[:alnum:]]*(CRITICAL|MAJOR|BLOCKING|MEDIUM)" in parser_run, (
            "Legacy block check must be case-sensitive (grep -qE, not -qiE) so "
            "title-case prose like 'Blocking issues — None' does not "
            "false-trigger."
        )

    def test_minor_not_in_block_alternation(self, parser_run):
        assert "(CRITICAL|MAJOR|MINOR|BLOCKING)" not in parser_run, (
            "MINOR must NOT be in the blocking alternation — minors never block "
            "(two-gate, #988)."
        )

    def test_found_n_no_longer_drives_emit(self, parser_run):
        # The old emit trigger keyed on `^Found [0-9]+ issues?:` — that line is
        # the #992 false-positive source and must no longer gate the emit.
        assert "grep -oE '^Found [0-9]+ issues?:'" not in parser_run, (
            "Parser must not derive the emit decision from a bare 'Found N "
            "issues:' line (the #992 false-positive)."
        )

    def test_title_selector_is_loosened(self, parser_run):
        assert "^###[[:space:]]+Code review$" not in parser_run, (
            "Literal '### Code review' first-line selector misses deviant "
            "titles (### #957) — must be loosened to the merge-gate selector."
        )
        assert r"^#{1,6}[ \t]*(Claude[ \t]+)?Code[ \t]+Review" in parser_run, (
            "Title selector must tolerate heading level + optional 'Claude' "
            "prefix, mirroring the merge gate."
        )

    def test_structured_marker_checked_before_legacy_fallback(self, parser_run):
        marker_at = parser_run.index("<!-- *code-review-findings")
        legacy_at = parser_run.index("(CRITICAL|MAJOR|BLOCKING|MEDIUM)")
        assert marker_at < legacy_at, (
            "The structured {blocking, findings} marker must be checked before "
            "falling back to the legacy severity-heading grep (#1816: marker "
            "is authoritative, legacy prose is fallback-only)."
        )

    def test_fails_closed_on_malformed_marker(self, parser_run):
        assert "failing closed" in parser_run, (
            "A present-but-malformed code-review-findings marker (invalid "
            "JSON, or missing/wrong-typed blocking/findings) must fail closed "
            "(BLOCKING=true), mirroring scripts/review_debt_collector.py and "
            "code-review.yml's Verify review verdict step (#1816)."
        )

    def test_n_critical_n_major_n_minor_removed(self, parser_run):
        assert "N_CRITICAL" not in parser_run
        assert "N_MAJOR" not in parser_run
        assert "N_MINOR" not in parser_run

    def test_findings_and_fingerprint_fields_present(self, parser_run):
        assert "finding_fingerprint" in parser_run
        assert "findings: $findings" in parser_run

    def test_block_check_precedes_fingerprint_derivation(self, parser_run):
        block_at = parser_run.index("(CRITICAL|MAJOR|BLOCKING|MEDIUM)")
        fp_at = parser_run.index("FINGERPRINT_JSON=$(jq")
        assert block_at < fp_at, (
            "The blocking-heading gate must run before fingerprint derivation "
            "— the fingerprint is only meaningful once a block is confirmed."
        )

    def test_severity_greps_run_under_c_locale(self, parser_run):
        # The [^[:alnum:]] decoration class only consumes a multibyte emoji
        # ("### 🔴 BLOCKING", #954) per-byte under the C locale; under the
        # runner default LANG=C.UTF-8 it reads the emoji as one non-consumed
        # rune and the block check silently misses. `export LC_ALL=C` must be
        # set, AND it must precede the legacy severity grep (after jq, so
        # JSON stays UTF-8 aware). Verified at runtime: LANG=C.UTF-8 → emoji
        # match 0, LC_ALL=C → emoji match 1.
        assert "export LC_ALL=C" in parser_run, (
            "Severity greps must run under LC_ALL=C — otherwise an emoji-"
            "decorated CRITICAL/MAJOR/BLOCKING heading (#954) escapes the "
            "block check under the runner's C.UTF-8 default."
        )
        assert parser_run.index("export LC_ALL=C") < parser_run.index(
            "(CRITICAL|MAJOR|BLOCKING|MEDIUM)"
        ), "LC_ALL=C must be exported before the legacy severity grep."


# -- Payload escaping (#1080) --------------------------------------------------
#
# #1080 replaced hand-built JSON (string-interpolated shell vars, `sed
# 's/"/\\"/g'` as the only escaping) with `jq -n --arg`/`--argjson` at 4 sites.
# The bug `sed` left open: a PR/issue title containing a backslash or an
# embedded newline (GitHub allows both via paste) produced invalid JSON and
# silently dropped the event — worse, a title crafted by an external
# contributor could corrupt the JSON structure around it. TestParserWiring
# above pins the *severity-parsing* logic in this same step; this class pins
# the *payload-construction* logic (all 4 `jq -n` sites) so a future edit
# can't quietly regress back to string interpolation.
#
# Behavioral, not just textual: each test extracts the real `jq -n ... )`
# pipeline from the workflow YAML and actually executes it via `jq` (present
# on `ubuntu-latest` runners, same as the workflow itself) against an
# adversarial title, then asserts the result is valid, correctly-escaped JSON.
# A regression to `sed`-style interpolation would make these tests fail with
# invalid JSON (json.loads raising) rather than a passing-but-meaningless
# string match.

HAS_JQ = shutil.which("jq") is not None

# Backslash + double quote + embedded newline: the exact character classes
# sed 's/"/\\"/g' left unescaped (issue #1080's finding).
ADVERSARIAL_TITLE = 'fix: "quoted" path C:\\Users\\x and\nan embedded newline'


def _load_step(job: str, step_name: str) -> dict:
    workflow = yaml.safe_load(EVENT_WORKFLOW.read_text(encoding="utf-8"))
    steps = workflow["jobs"][job]["steps"]
    return next(s for s in steps if s.get("name") == step_name)


def _extract_payload_pipeline(run_script: str) -> str:
    """Slice out just the `PAYLOAD=$(jq -n ... )` assignment from a step's
    `run:` script, so it can be executed in isolation without the rest of the
    step's GitHub-Actions-context interpolation getting in the way."""
    start = run_script.index("PAYLOAD=$(jq -n")
    end = run_script.index("}')", start) + len("}')")
    return run_script[start:end]


def _run_payload_pipeline(pipeline: str, env_vars: dict) -> dict:
    # Resolve the executable path explicitly rather than passing a bare
    # "bash" argv[0] — on Windows a bare name can resolve to the WSL launcher
    # shim (C:\Windows\System32\bash.exe) instead of a real POSIX shell,
    # depending on subprocess's PATH search order vs. shutil.which's.
    bash = shutil.which("bash")
    script = pipeline + '\necho "$PAYLOAD"'
    result = subprocess.run(
        [bash, "-c", script],
        env={**os.environ, **env_vars},
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(result.stdout)


@pytest.mark.skipif(not HAS_JQ, reason="jq not installed")
class TestPayloadEscaping:
    def test_pr_approved_payload_escapes_adversarial_title(self):
        step = _load_step("pr-approved", "Dispatch PR approved event")
        pipeline = _extract_payload_pipeline(step["run"])
        payload = _run_payload_pipeline(
            pipeline,
            {
                "REPO": "Osasuwu/jarvis",
                "PR_NUM": "1080",
                "PR_TITLE": ADVERSARIAL_TITLE,
                "REVIEWER": "petrk",
                "PR_URL": "https://github.com/Osasuwu/jarvis/pull/1080",
            },
        )
        assert payload["payload"]["pr_title"] == ADVERSARIAL_TITLE
        assert payload["payload"]["pr_number"] == 1080  # --argjson: numeric, not string

    def test_pr_merged_payload_escapes_adversarial_title(self):
        step = _load_step("pr-merged", "Dispatch PR merged event")
        pipeline = _extract_payload_pipeline(step["run"])
        payload = _run_payload_pipeline(
            pipeline,
            {
                "REPO": "Osasuwu/jarvis",
                "PR_NUM": "1080",
                "PR_TITLE": ADVERSARIAL_TITLE,
                "AUTHOR": "petrk",
                "PR_URL": "https://github.com/Osasuwu/jarvis/pull/1080",
                "MERGE_SHA": "abc123",
            },
        )
        assert payload["payload"]["pr_title"] == ADVERSARIAL_TITLE
        assert payload["payload"]["pr_number"] == 1080

    def test_review_negative_human_payload_escapes_adversarial_title(self):
        step = _load_step(
            "review-negative-human", "Dispatch review_negative event (human)"
        )
        pipeline = _extract_payload_pipeline(step["run"])
        payload = _run_payload_pipeline(
            pipeline,
            {
                "REPO": "Osasuwu/jarvis",
                "PR_NUM": "1080",
                "PR_TITLE": ADVERSARIAL_TITLE,
                "REVIEWER": "petrk",
                "REVIEW_ID": "42",
                "REVIEW_URL": "https://github.com/Osasuwu/jarvis/pull/1080#review-42",
            },
        )
        assert payload["payload"]["pr_title"] == ADVERSARIAL_TITLE
        assert payload["payload"]["pr_number"] == 1080
        assert payload["payload"]["review_id"] == 42

    def test_review_negative_claude_bot_payload_escapes_adversarial_title(
        self, parser_run
    ):
        # Same step TestParserWiring pins for severity parsing (#992/#1816) —
        # here we isolate just its payload-construction tail (#1080).
        pipeline = _extract_payload_pipeline(parser_run)
        payload = _run_payload_pipeline(
            pipeline,
            {
                "REPO": "Osasuwu/jarvis",
                "PR_NUM": "1080",
                "PR_TITLE": ADVERSARIAL_TITLE,
                "COMMENT_ID": "99",
                "COMMENT_URL": "https://github.com/Osasuwu/jarvis/pull/1080#comment-99",
                "N_ISSUES": "1",
                "ISSUE_WORD": "issue",
                "FINDINGS_JSON": '[{"class":"regression","file":"src/foo.py"}]',
                "FINGERPRINT_JSON": '["regression|src/foo.py"]',
            },
        )
        assert payload["payload"]["pr_title"] == ADVERSARIAL_TITLE
        assert payload["payload"]["pr_number"] == 1080
        assert payload["payload"]["findings"] == [
            {"class": "regression", "file": "src/foo.py"}
        ]
        assert payload["payload"]["finding_fingerprint"] == ["regression|src/foo.py"]
        assert payload["payload"]["n_issues"] == 1

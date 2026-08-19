"""Meta-test for .github/workflows/auto-merge-enable.yml.

Reimplements the auto-merge-enable's per-PR enable decision in Python and
asserts it enables/skips the PRs the workflow promises, plus a config dimension
that keeps the YAML and this test in lockstep.

Why this test exists (.claude/rules/path-filtered-ci-guards-meta-test.md, #326 + #948 Bug A): auto-merge-enable.yml is the
fix for #948 Bug A — a PR auto-merged with the default GITHUB_TOKEN is attributed
to github-actions[bot], and GitHub's recursion-prevention then SUPPRESSES native
linked-issue auto-close (the merged PR leaves its `Closes #N` issue open). The fix
is to enable auto-merge with a GitHub App installation token so the merge's
`enabledBy` actor is the App, not the bot. That correctness hinges entirely on
config the diff can silently regress:
  - reverting the App token back to GITHUB_TOKEN reintroduces the exact bug,
  - dropping the draft/fork guard hard-fails fork PRs or enrols held drafts,
  - dropping the empty-output guard silently leaves a PR un-enrolled,
  - dropping cancel-in-progress:false can kill a run mid-enable.
None of those produce a red signal on their own — this test is that signal.

Enable rule mirrored here (see the `if:` guard + bash step in the YAML):
  eligible   = non-draft AND head repo == base repo (not a fork)
  enable     = eligible AND auto-merge not already enabled (autoMergeRequest null)
  skip       = eligible AND auto-merge already enabled (idempotent re-trigger)
  fail-loud  = eligible AND `gh pr view` returned empty (auth/API degradation)
"""

from __future__ import annotations

import re
import string
from pathlib import Path

import pytest


WORKFLOW_PATH = (
    Path(__file__).resolve().parents[2] / ".github" / "workflows" / "auto-merge-enable.yml"
)


# ---- logic dimension --------------------------------------------------------
#
# The decision has three terminal states: ENABLE, SKIP, FAIL. `am` is the
# auto-merge token the workflow's jq emits: "null" when unset, "set" when
# already enabled, and "" only on degraded (whitespace-only) API output. The
# workflow reduces the raw autoMergeRequest object to this bare token via @tsv
# so `read` can't mis-split on spaces inside commitHeadline.


def decide(
    *,
    draft: bool,
    head_repo: str,
    base_repo: str,
    am: str,
    state: str = "OPEN",
    code_review_diverged: bool = False,
    pr_author: str = "user",
) -> str:
    """Mirror the workflow's enable decision.

    Returns ENABLE / SKIP / FAIL / NOOP / WITHHOLD / DISARM.

    `code_review_diverged` is the carve-out dimension (#1234): True when the PR's
    `.github/workflows/code-review.yml` blob differs from the default branch's —
    a two-dot CONTENT comparison, so it covers both "this PR edits the file" and
    "this PR's branch is merely stale on it". Both trip claude-code-action's
    workflow validation identically.
    """
    # `if:` guard — drafts, forks, and Dependabot never reach the steps.
    if draft:
        return "NOOP"
    if head_repo != base_repo:
        return "NOOP"
    # Keyed off the PR AUTHOR, not the triggering `github.actor` — the latter is
    # the pusher and changes on `synchronize` events (#944 anti-pattern; same
    # fix as code-review.yml's own Dependabot guard).
    if pr_author == "dependabot[bot]":
        return "NOOP"
    # Empty-output guard — fail loud rather than misread as "already enabled".
    if am == "" or state == "":
        return "FAIL"
    # cancel-in-progress:false lets a run queued near merge time execute after the
    # PR is already merged; on a merged PR am reads "null" but state is not OPEN.
    if state != "OPEN":
        return "NOOP"
    # Carve-out (#1234): sits after the state/empty guards (a closed PR needs no
    # carve-out) but before the arm decision. Non-failure in both branches — an
    # expected-red check on a whole PR class is the noise this issue exists to
    # remove.
    if code_review_diverged:
        return "DISARM" if am == "set" else "WITHHOLD"
    if am == "null":
        return "ENABLE"
    return "SKIP"


def test_ready_non_fork_with_no_automerge_enables():
    assert decide(draft=False, head_repo="o/r", base_repo="o/r", am="null") == "ENABLE"


def test_already_enabled_is_idempotent_skip():
    assert decide(draft=False, head_repo="o/r", base_repo="o/r", am="set") == "SKIP"


def test_draft_is_noop():
    assert decide(draft=True, head_repo="o/r", base_repo="o/r", am="null") == "NOOP"


def test_fork_pr_is_noop():
    assert decide(draft=False, head_repo="fork/r", base_repo="o/r", am="null") == "NOOP"


def test_empty_output_fails_loud():
    assert decide(draft=False, head_repo="o/r", base_repo="o/r", am="") == "FAIL"


def test_empty_state_fails_loud():
    assert decide(draft=False, head_repo="o/r", base_repo="o/r", am="null", state="") == "FAIL"


def test_already_merged_pr_is_noop():
    # Queued run executes after merge: am=="null" (auto-merge completed) but the
    # PR is no longer OPEN — must NOT call `gh pr merge` on a closed PR.
    assert (
        decide(draft=False, head_repo="o/r", base_repo="o/r", am="null", state="MERGED") == "NOOP"
    )


def test_closed_pr_is_noop():
    assert (
        decide(draft=False, head_repo="o/r", base_repo="o/r", am="null", state="CLOSED") == "NOOP"
    )


def test_code_review_divergence_withholds_automerge():
    # AC4/AC7 carve-out: when the PR's code-review.yml content differs from the
    # default branch's, claude-code-action skips on workflow validation and no
    # verdict is posted. The verdict ladder fails CLOSED on that absence
    # (#1434/#1228), but the ladder lives in the file this class edits — a
    # self-edit can weaken it to a vacuous green. Withhold here as
    # defense-in-depth from a workflow the class does not touch.
    assert (
        decide(
            draft=False,
            head_repo="o/r",
            base_repo="o/r",
            am="null",
            code_review_diverged=True,
        )
        == "WITHHOLD"
    )


def test_code_review_divergence_disarms_already_armed_pr():
    # A PR can be armed BEFORE a code-review.yml change lands on main, which makes
    # it retroactively carve-out. Leaving it armed would let it merge the moment
    # a (possibly self-edit-weakened) `review` context reads green, so the
    # carve-out disarms instead of merely declining to arm.
    assert (
        decide(
            draft=False,
            head_repo="o/r",
            base_repo="o/r",
            am="set",
            code_review_diverged=True,
        )
        == "DISARM"
    )


def test_other_workflow_paths_still_enable():
    # AC7: the carve-out is scoped to code-review.yml specifically — a PR editing
    # pytest.yml (or any other workflow) reviews normally, so it must still arm.
    # claude-code-action validates its OWN calling workflow file, not all of
    # .github/workflows/**.
    assert (
        decide(
            draft=False,
            head_repo="o/r",
            base_repo="o/r",
            am="null",
            code_review_diverged=False,
        )
        == "ENABLE"
    )


def test_carve_out_does_not_apply_to_closed_pr():
    # The state guard precedes the carve-out: a merged PR needs no withholding.
    assert (
        decide(
            draft=False,
            head_repo="o/r",
            base_repo="o/r",
            am="null",
            state="MERGED",
            code_review_diverged=True,
        )
        == "NOOP"
    )


def test_fork_precedes_empty_output_fail():
    # Fork guard is evaluated before the empty-output FAIL path: a fork PR with
    # degraded output must NOOP (the `if:` skips the steps entirely), not FAIL.
    # Replaces a draft+fork case that duplicated the draft-only path (#1006 review,
    # NIT) — this one actually reaches the fork branch with am="".
    assert decide(draft=False, head_repo="fork/r", base_repo="o/r", am="") == "NOOP"


def test_dependabot_pr_is_noop():
    # GitHub restricts repo-secret access for Dependabot-triggered pull_request
    # events (same as forks), so APP_ID/APP_PRIVATE_KEY are empty and the Assert
    # step hard-fails. The job-level `if:` guard skips Dependabot entirely.
    assert (
        decide(
            draft=False, head_repo="o/r", base_repo="o/r", am="null", pr_author="dependabot[bot]"
        )
        == "NOOP"
    )


def test_dependabot_precedes_empty_output_fail():
    # Dependabot guard is in the `if:` condition (steps never run), so degraded
    # output must yield NOOP, not FAIL — same logic as the fork analog above.
    assert (
        decide(draft=False, head_repo="o/r", base_repo="o/r", am="", pr_author="dependabot[bot]")
        == "NOOP"
    )


# ---- risk carve-out dimension (#1512) ---------------------------------------
#
# Sibling of the #1234 code-review carve-out above, but keyed off the PR body's
# own "## Risk Assessment" section (the /implement SKILL.md template) instead of
# a file diff. PR #1510 self-declared HIGH risk and still auto-merged the moment
# CI went green (#1512) because nothing ever parsed that section. Reimplements
# the workflow's awk-section-extract + grep-regex + WITHHOLD/DISARM decision so
# a regression in either the parsing or the decision produces a red here.

RISK_SECTION_RE = re.compile(r"^## Risk Assessment\n(.*?)(?=^## |\Z)", re.MULTILINE | re.DOTALL)
RISK_VALUE_RE = re.compile(r"^[ \t]*-[ \t]*\*\*(?:HIGH|CRITICAL)\*\*:[ \t]*(.*)$", re.MULTILINE)

# Negative fillers (#1655): an explicit "no risk at this level" answer is not a
# declaration. PULL_REQUEST_TEMPLATE.md ships all four severity rows pre-filled,
# so `- **HIGH**: none.` is the most literal way to answer it — and the old
# `[^<\s]` check read every one of those as a HIGH-risk declaration, parking the
# PR the carve-out was supposed to wave through (#1654 hit it). Only an EXACT
# match here passes through: anything unrecognised ("none, but the migration is
# irreversible") still counts as declared, so the failure direction stays
# conservative. Mirrors RISK_NEGATIVE_FILLERS in the workflow — kept in lockstep
# by test_workflow_negative_filler_list_matches_this_mirror below.
NEGATIVE_FILLERS = frozenset(
    {
        "none",
        "nil",
        "no",
        "nothing",
        "not applicable",
        "n/a",
        "na",
        "tbd",
        "-",
        "--",
        "—",
        "нет",
        "отсутствует",
    }
)

_HTML_TAG_RE = re.compile(r"<[^>]*>")
_EMPHASIS_RE = re.compile(r"[*_`~]")
_WHITESPACE_RE = re.compile(r"\s+")
_TRAILING_PUNCT_RE = re.compile(r"\s*[.!;,]+\s*$")
# The workflow lowercases with `tr '[:upper:]' '[:lower:]'`, which is byte-wise
# and leaves non-ASCII alone. str.lower() would fold Cyrillic too and quietly
# make this mirror MORE permissive than the thing it mirrors.
_ASCII_LOWER = str.maketrans(string.ascii_uppercase, string.ascii_lowercase)


def normalise_risk_value(raw: str) -> str:
    """Mirror the workflow's per-value sed/tr normalisation pipeline.

    Drops HTML tags (the template's `<!-- hint -->` and the SKILL.md
    `<placeholder>`), strips markdown emphasis, collapses whitespace, drops
    trailing sentence punctuation, trims, and ASCII-lowercases.
    """
    text = _HTML_TAG_RE.sub("", raw)
    text = _EMPHASIS_RE.sub("", text)
    text = _WHITESPACE_RE.sub(" ", text)
    text = _TRAILING_PUNCT_RE.sub("", text)
    return text.strip().translate(_ASCII_LOWER)


def risk_declared(body: str) -> bool:
    """Mirror the workflow's awk section-extract + per-value classification.

    Scoped to the '## Risk Assessment' section only (awk resets `f` on the next
    '## ' heading). A HIGH/CRITICAL row declares risk iff its value survives
    normalisation as something that is neither empty nor a negative filler — so
    an unfilled `<placeholder>`, an empty row, and an explicit "none" all pass
    through, while any other text parks the PR.
    """
    section_match = RISK_SECTION_RE.search(body)
    section = section_match.group(1) if section_match else ""
    for raw_value in RISK_VALUE_RE.findall(section):
        value = normalise_risk_value(raw_value)
        if not value or value in NEGATIVE_FILLERS:
            continue
        return True
    return False


def decide_risk_carveout(*, declared: bool, am: str) -> str:
    """Mirror the risk carve-out's terminal state.

    Returns PASS / WITHHOLD / DISARM. PASS means the risk carve-out does not
    intervene — control falls through to the #1234 carve-out / normal arm
    decision below it in the workflow.
    """
    if not declared:
        return "PASS"
    return "DISARM" if am == "set" else "WITHHOLD"


def test_risk_declared_withholds_unarmed_pr():
    assert decide_risk_carveout(declared=True, am="null") == "WITHHOLD"


def test_risk_declared_disarms_already_armed_pr():
    # A PR can be armed BEFORE a HIGH/CRITICAL line lands via a body-only edit
    # (the 'edited' trigger). Leaving it armed would let it merge the moment CI
    # reads green, so the carve-out disarms instead of merely declining to arm.
    assert decide_risk_carveout(declared=True, am="set") == "DISARM"


def test_no_risk_declared_passes_through():
    assert decide_risk_carveout(declared=False, am="null") == "PASS"


def test_pr_1510_body_trips_the_carveout():
    # Regression pin (#1512): PR #1510's actual Risk Assessment declared HIGH
    # and still auto-merged — this body shape must trip the carve-out now.
    body = (
        "## Risk Assessment\n"
        "- **HIGH**: drain_pending control-flow change alters event dispatch "
        "ordering under concurrent producers.\n"
    )
    assert risk_declared(body) is True


def test_risk_regex_matches_critical():
    body = "## Risk Assessment\n- **CRITICAL**: touches planning/ safety zone\n"
    assert risk_declared(body) is True


def test_risk_regex_ignores_low_medium_only():
    body = "## Risk Assessment\n- **LOW**: docs only\n- **MEDIUM**: n/a\n"
    assert risk_declared(body) is False


def test_risk_regex_ignores_unfilled_template_placeholder():
    # The raw SKILL.md template ships `- **HIGH**: <describe change if
    # applicable>` — an unfilled placeholder must not trip the carve-out on
    # every PR that never touched the section.
    body = "## Risk Assessment\n- **HIGH**: <describe change if applicable>\n"
    assert risk_declared(body) is False


def test_risk_regex_ignores_missing_section():
    body = "## Summary\nA PR with no Risk Assessment section at all.\n"
    assert risk_declared(body) is False


def test_risk_regex_scoped_to_risk_assessment_section_only():
    # A HIGH mention outside '## Risk Assessment' (e.g. prose in the Summary)
    # must not trip the carve-out — only the parsed section counts, mirroring
    # the workflow's awk /^## Risk Assessment/{f=1} ... /^## /{f=0} reset.
    body = (
        "## Summary\n"
        "- **HIGH**: mentioned here only in passing, not a real declaration\n"
        "\n"
        "## Risk Assessment\n"
        "- **LOW**: actual declared risk\n"
    )
    assert risk_declared(body) is False


def test_risk_regex_ignores_explicit_none():
    # #1655 regression pin: PULL_REQUEST_TEMPLATE.md ships all four severity
    # rows pre-filled, so answering the HIGH/CRITICAL rows honestly is the most
    # literal possible use of the template. The old `[^<\s]` check read every
    # one of those answers as a declaration and parked the PR (#1654).
    body = (
        "## Risk Assessment\n"
        "- **LOW**: version-string metadata only.\n"
        "- **MEDIUM**: none.\n"
        "- **HIGH**: none.\n"
        "- **CRITICAL**: none.\n"
    )
    assert risk_declared(body) is False


@pytest.mark.parametrize("filler", sorted(NEGATIVE_FILLERS))
def test_every_negative_filler_passes_through(filler):
    # The list is the contract — each entry must actually be recognised, not
    # just sit in the constant.
    body = f"## Risk Assessment\n- **HIGH**: {filler}\n"
    assert risk_declared(body) is False


@pytest.mark.parametrize(
    "written",
    [
        "None.",
        "NONE",
        "N/A",
        "n/a.",
        "`none`",
        "**none**",
        "none   ",
        "none <!-- logic changes, safety-adjacent -->",
        "Not applicable.",
    ],
)
def test_negative_filler_survives_formatting_noise(written):
    # Normalisation (case, markdown emphasis, template hint comment, trailing
    # punctuation, stray whitespace) happens before the filler comparison, so a
    # human writing "None." is not a different answer from "none".
    body = f"## Risk Assessment\n- **HIGH**: {written}\n"
    assert risk_declared(body) is False


def test_partial_negative_still_declares_risk():
    # Only an EXACT filler passes. A hedged answer is a declaration — the
    # failure direction stays conservative (park, don't auto-merge).
    body = "## Risk Assessment\n- **HIGH**: none, but the migration is irreversible once applied.\n"
    assert risk_declared(body) is True


def test_filler_in_high_does_not_mask_a_real_critical():
    # Every HIGH/CRITICAL row is classified independently — one honest "none"
    # must not short-circuit the scan past a real declaration below it.
    body = (
        "## Risk Assessment\n"
        "- **HIGH**: none.\n"
        "- **CRITICAL**: drops the events_canonical table in a migration.\n"
    )
    assert risk_declared(body) is True


# ---- config dimension (keep YAML and test in lockstep) ----------------------


def test_workflow_exists():
    assert WORKFLOW_PATH.is_file(), "auto-merge-enable.yml missing"


def test_workflow_mints_app_token():
    text = WORKFLOW_PATH.read_text(encoding="utf-8")
    assert "create-github-app-token" in text, (
        "auto-merge-enable must mint a GitHub App token — auto-merge enabled with "
        "GITHUB_TOKEN attributes the merge to github-actions[bot], which suppresses "
        "native linked-issue auto-close (#948 Bug A)."
    )


def test_workflow_uses_app_token_not_github_token():
    text = WORKFLOW_PATH.read_text(encoding="utf-8")
    # Minting the App token is not enough: Bug A reappears if GH_TOKEN on the
    # `gh pr merge` step reverts to secrets.GITHUB_TOKEN while the mint step stays
    # (token minted then discarded). Pin the *usage*, not just the presence.
    assert "steps.app-token.outputs.token" in text, (
        "GH_TOKEN for `gh pr merge --auto` must use the minted App token output "
        "(steps.app-token.outputs.token), not GITHUB_TOKEN — reverting is #948 Bug A."
    )
    # Match the regression VECTOR (the interpolated expression), not the bare
    # substring: a comment mentioning secrets.GITHUB_TOKEN would false-positive
    # the broad check (#1006 review, MINOR).
    assert "${{ secrets.GITHUB_TOKEN }}" not in text, (
        "auto-merge-enable must never pass ${{ secrets.GITHUB_TOKEN }} to gh — it "
        "would re-attribute the merge to github-actions[bot] and suppress auto-close."
    )


def test_workflow_app_token_is_sha_pinned():
    import re

    text = WORKFLOW_PATH.read_text(encoding="utf-8")
    # Supply-chain hardening: the action must be pinned to a full 40-hex commit
    # SHA, not a mutable tag (@v3). Match the SHANESS, not the exact commit, so a
    # Dependabot pin bump doesn't red this test (the sibling merge-train guard
    # follows the same intent-not-literal pattern).
    assert re.search(r"create-github-app-token@[0-9a-f]{40}", text), (
        "create-github-app-token must be SHA-pinned (supply-chain), not tag-pinned."
    )


def test_workflow_scopes_token_to_this_repo():
    text = WORKFLOW_PATH.read_text(encoding="utf-8")
    # Least-privilege: the App is shared across repos (jarvis + redrobot), so the
    # minted token must be scoped to this repo only. Derived from GITHUB_REPOSITORY
    # so it's populated on every trigger.
    assert "REPO_NAME=${GITHUB_REPOSITORY#*/}" in text, (
        "token must be scoped via env REPO_NAME derived from GITHUB_REPOSITORY."
    )
    assert "repositories: ${{ env.REPO_NAME }}" in text, (
        "create-github-app-token must pass repositories: env.REPO_NAME for least-privilege."
    )


def test_workflow_requests_workflows_scope_explicitly():
    text = WORKFLOW_PATH.read_text(encoding="utf-8")
    # AC2 (#1234): without the workflows scope, `enablePullRequestAutoMerge` is
    # refused by GitHub on ANY PR touching .github/workflows/ ("refusing to allow
    # a GitHub App to create or update workflow ... without `workflows`
    # permission"), so every CI-editing PR silently degrades to manual merge.
    # Input name verified against actions/create-github-app-token@bcd2ba49 (v3.2.0)
    # action.yml, NOT guessed.
    assert "permission-workflows: write" in text, (
        "the minted App token must request the workflows scope explicitly, else "
        "auto-merge can never be armed on a .github/workflows/ PR (#1234)."
    )
    # Supplying ANY permission-* input REPLACES the installation's inherited
    # permissions with exactly the listed set (per the action's README). So the
    # scopes this workflow actually needs must be listed alongside, or the token
    # silently loses the ability to merge.
    assert "permission-contents: write" in text, (
        "down-scoping via permission-* drops inherited scopes — contents:write is "
        "required for the squash merge itself."
    )
    assert "permission-pull-requests: write" in text, (
        "down-scoping via permission-* drops inherited scopes — pull-requests:write "
        "is required by enablePullRequestAutoMerge."
    )


def test_workflow_guards_drafts_and_forks():
    text = WORKFLOW_PATH.read_text(encoding="utf-8")
    assert "github.event.pull_request.draft == false" in text, (
        "draft guard dropped — held drafts would get auto-merge enabled."
    )
    assert "github.event.pull_request.head.repo.full_name == github.repository" in text, (
        "fork guard dropped — fork PRs (no secrets) would hard-fail the token step."
    )


def test_workflow_skips_dependabot_prs():
    text = WORKFLOW_PATH.read_text(encoding="utf-8")
    assert "github.event.pull_request.user.login != 'dependabot[bot]'" in text, (
        "Dependabot guard dropped, or keyed off github.actor (the triggering pusher, "
        "not the PR author — #944 anti-pattern: github.actor changes to the pusher "
        "on `synchronize` events, e.g. when dependabot-lockfile.yml pushes to a "
        "Dependabot branch). Dependabot-triggered pull_request events cannot access "
        "repo secrets (APP_ID/APP_PRIVATE_KEY), so the Assert step hard-fails on "
        "every Dependabot PR. The job-level `if:` must skip them by PR author."
    )


def test_workflow_has_empty_output_guard():
    text = WORKFLOW_PATH.read_text(encoding="utf-8")
    # The guard is compound: `[ -z "$am" ] || [ -z "$state" ]`. Assert BOTH halves
    # (#1006 review, MINOR) — dropping the `$state` half would leave the
    # state-emptiness path unguarded while this test still passed on the `$am` half.
    assert '[ -z "$am" ]' in text, (
        "empty-output guard dropped — a degraded `gh pr view` would be misread as "
        "'already enabled', silently leaving the PR un-enrolled."
    )
    assert '[ -z "$state" ]' in text, (
        "state empty-guard half dropped — a degraded `gh pr view` could leave "
        "$state empty and the merged-PR guard would misfire."
    )


def test_workflow_guards_empty_app_token():
    text = WORKFLOW_PATH.read_text(encoding="utf-8")
    # If the Mint step is skipped (REPO_NAME empty), GH_TOKEN is "" and gh could
    # fall back to the ambient GITHUB_TOKEN — re-attributing the merge to the bot
    # (#948 Bug A). The Enable step must fail loud on an empty token before any gh
    # call (#1006 review, MAJOR).
    assert '[ -z "${GH_TOKEN:-}" ]' in text, (
        "Enable step must fail loud when the App token is empty — an empty GH_TOKEN "
        "risks a GITHUB_TOKEN fallback and a bot-attributed merge (#948 Bug A)."
    )


def test_workflow_enables_only_when_unset():
    text = WORKFLOW_PATH.read_text(encoding="utf-8")
    assert '[ "$am" = "null" ]' in text, (
        "idempotency check dropped — re-triggers would re-call `gh pr merge --auto` "
        "and surface a spurious failure."
    )


def test_workflow_emits_clean_automerge_token():
    text = WORKFLOW_PATH.read_text(encoding="utf-8")
    # The raw autoMergeRequest object carries a commitHeadline that can contain
    # spaces; interpolating it into `read -r am state` mis-splits state. The jq
    # must reduce it to a bare "null"/"set" token and emit with @tsv so `read`
    # splits only on the tab. Regressing to `\(.autoMergeRequest)` re-opens the
    # whitespace bug (#948 review round 6).
    assert 'if .autoMergeRequest == null then "null" else "set" end' in text, (
        "auto-merge status must be reduced to a bare null/set token, not the raw "
        "autoMergeRequest object (whitespace in commitHeadline mis-splits `read`)."
    )
    assert "| @tsv" in text, (
        "the read inputs must be tab-separated (@tsv) so `read` can't mis-split "
        "on spaces inside a field."
    )


def test_workflow_skips_non_open_pr():
    text = WORKFLOW_PATH.read_text(encoding="utf-8")
    # cancel-in-progress:false allows a run to land after the PR merged; the state
    # guard prevents calling `gh pr merge` on a closed PR (spurious red).
    assert '[ "$state" != "OPEN" ]' in text, (
        "merged-PR guard dropped — a queued run after merge would call "
        "`gh pr merge` on a closed PR and surface a spurious failure."
    )


def test_workflow_triggers_on_ready_for_review_and_reopened():
    text = WORKFLOW_PATH.read_text(encoding="utf-8")
    # Dropping ready_for_review → draft→ready PRs never enrol; dropping reopened →
    # a reopened sandcastle never re-enrols. Both are silent failures.
    for trigger in ("opened", "ready_for_review", "reopened"):
        assert trigger in text, f"auto-merge-enable must trigger on {trigger!r}."


def test_workflow_repo_name_guard_is_load_bearing():
    text = WORKFLOW_PATH.read_text(encoding="utf-8")
    # An empty REPO_NAME makes create-github-app-token fall back to ALL installed
    # repos, leaking Issues:write to redrobot. The guard must fail loud instead.
    assert "GITHUB_REPOSITORY:?" in text, (
        "the REPO_NAME derivation must guard against an empty GITHUB_REPOSITORY "
        "(empty scope re-opens the cross-repo token leak)."
    )


def test_workflow_documents_workflows_permission_requirement():
    text = WORKFLOW_PATH.read_text(encoding="utf-8")
    # AC1 (#1234): the App-side grant is a manual UI action with no code trace of
    # its own. If the header and the setup instructions don't name it, a fresh
    # repo install reproduces the exact bug this issue fixed — auto-merge that
    # works everywhere except on CI PRs.
    assert "Workflows: Read and write" in text, (
        "the App permission list (header + Assert step setup instructions) must "
        "name Workflows: Read and write — it has no other trace in code (#1234)."
    )


def test_workflow_triggers_on_edited():
    text = WORKFLOW_PATH.read_text(encoding="utf-8")
    # #1512: a Risk Assessment escalation can land via a body-only edit with no
    # new commit — synchronize wouldn't fire for that, so the risk carve-out
    # needs its own trigger type.
    assert "edited" in text, (
        "risk carve-out needs the 'edited' trigger — a body-only Risk "
        "Assessment escalation would otherwise never re-evaluate (#1512)."
    )


def test_workflow_risk_carveout_parses_risk_assessment_section():
    text = WORKFLOW_PATH.read_text(encoding="utf-8")
    assert "## Risk Assessment" in text, (
        "risk carve-out must parse the /implement SKILL.md '## Risk "
        "Assessment' section specifically, not grep the whole PR body."
    )
    assert "HIGH|CRITICAL" in text, (
        "risk carve-out must trigger on both HIGH and CRITICAL, per /implement §7.5's merge policy."
    )


def test_workflow_negative_filler_list_matches_this_mirror():
    # #1655: the workflow's filler list and NEGATIVE_FILLERS above are one
    # contract in two languages. Drift is invisible in CI (the workflow only
    # runs on real PRs), so pin them equal here.
    text = WORKFLOW_PATH.read_text(encoding="utf-8")
    match = re.search(r"RISK_NEGATIVE_FILLERS='([^']*)'", text)
    assert match, (
        "risk carve-out must define its negative-filler set as a single "
        "RISK_NEGATIVE_FILLERS='a|b|c' assignment so this test can pin it."
    )
    workflow_fillers = set(match.group(1).split("|"))
    assert workflow_fillers == set(NEGATIVE_FILLERS), (
        "workflow negative-filler list drifted from the test mirror: "
        f"only in workflow={sorted(workflow_fillers - NEGATIVE_FILLERS)}, "
        f"only in test={sorted(NEGATIVE_FILLERS - workflow_fillers)}"
    )


def test_workflow_risk_carveout_normalises_before_matching_fillers():
    text = WORKFLOW_PATH.read_text(encoding="utf-8")
    risk_block = text.split("---- risk carve-out", 1)[1].split("---- end risk carve-out", 1)[0]
    assert "tr '[:upper:]' '[:lower:]'" in risk_block, (
        "risk carve-out must case-fold a row's value before comparing it "
        "against the negative-filler list — 'None.' is the same answer as "
        "'none' (#1655)."
    )
    assert "grep -qvxE" in risk_block, (
        "filler comparison must be a whole-line (-x) match: a substring "
        "match would let 'none of this is safe' read as the filler 'none' "
        "and silently un-park a genuinely risky PR (#1655)."
    )


def test_workflow_risk_carveout_reuses_owner_queue_guard():
    text = WORKFLOW_PATH.read_text(encoding="utf-8")
    assert 'RISK_LABEL="status:owner-queue"' in text, (
        "risk carve-out must reuse the existing status:owner-queue / "
        "owner-queue-guard required check rather than inventing a new gate."
    )


def test_workflow_risk_carveout_fetches_body_fresh():
    text = WORKFLOW_PATH.read_text(encoding="utf-8")
    assert 'gh pr view "$PR" --repo "$REPO" --json body' in text, (
        "risk carve-out must fetch the PR body fresh via gh pr view, not "
        "trust the (possibly stale) pull_request event payload body."
    )


def test_workflow_risk_carveout_guards_empty_body_fetch():
    text = WORKFLOW_PATH.read_text(encoding="utf-8")
    # #1513 review: the am/state fetch above already guards this exact
    # degraded-output hazard (gh exits 0 with empty stdout on transient
    # auth/API failure) — the BODY fetch must too, or a degraded response
    # silently reads as "no risk declared" and reopens the hole this PR
    # exists to close via a new path. `tojson` collapses the whole response
    # to one line so its OWN emptiness (not body's value) is what's checked —
    # a genuinely empty PR body still yields a non-empty JSON object string.
    risk_block = text.split("---- risk carve-out", 1)[1].split("---- end risk carve-out", 1)[0]
    assert "RAW_BODY_JSON=" in risk_block and "-q 'tojson'" in risk_block, (
        "risk carve-out must fetch the PR body via a whole-object tojson "
        "capture so degraded (empty) gh output is distinguishable from a "
        "genuinely empty PR body."
    )
    assert '[ -z "$RAW_BODY_JSON" ]' in risk_block, (
        "risk carve-out must fail loud when gh pr view returns empty output "
        "while fetching the body, mirroring the am/state empty-output guard "
        "20 lines above it in the same script step."
    )


def test_workflow_risk_carveout_disarms_already_armed_pr():
    text = WORKFLOW_PATH.read_text(encoding="utf-8")
    # Both carve-outs disarm an already-armed PR; scope the assertion to the
    # risk carve-out's own block so a future edit to the #1234 block alone
    # can't false-pass this test.
    risk_block = text.split("---- risk carve-out", 1)[1].split("---- end risk carve-out", 1)[0]
    assert "--disable-auto" in risk_block, (
        "risk carve-out must disarm auto-merge if the PR was armed BEFORE the "
        "HIGH/CRITICAL line landed via a body-only edit."
    )


def test_workflow_risk_carveout_is_idempotent():
    text = WORKFLOW_PATH.read_text(encoding="utf-8")
    risk_block = text.split("---- risk carve-out", 1)[1].split("---- end risk carve-out", 1)[0]
    assert "already_labelled" in risk_block, (
        "risk carve-out must check for an existing status:owner-queue label "
        "before re-adding it/re-commenting — else every 'edited'-triggered "
        "re-run on an already-withheld PR spams a duplicate comment."
    )


def test_workflow_risk_carveout_precedes_code_review_carveout():
    text = WORKFLOW_PATH.read_text(encoding="utf-8")
    # Ordering is not load-bearing for correctness (both carve-outs exit 0
    # independently) but pins the file's documented block order so a future
    # edit doesn't interleave the two and make the "end risk carve-out" /
    # "end carve-out" markers ambiguous.
    assert text.index("---- risk carve-out") < text.index(
        "carve-out: PRs /code-review cannot actually review"
    ), "risk carve-out block must precede the #1234 code-review carve-out block."


def test_workflow_carve_out_compares_code_review_yml_content():
    text = WORKFLOW_PATH.read_text(encoding="utf-8")
    # AC4 (#1234): claude-code-action skips with "Skipping action due to workflow
    # validation" when its OWN calling workflow's content differs from the default
    # branch's. Historically the verdict ladder read that as a legitimate skip
    # and `review` went green with ZERO comments (PR #1231, run 29992799097);
    # since #1434/#1228 it fails closed — but the ladder rides code-review.yml
    # itself, so this out-of-file carve-out stays as defense-in-depth.
    assert ".github/workflows/code-review.yml" in text, (
        "carve-out dropped — a PR whose code-review.yml diverges from the default "
        "branch would arm auto-merge, with only the PR's own (editable) copy of "
        "the verdict ladder standing between it and an unreviewed merge."
    )
    # The predicate must be a two-dot CONTENT comparison against the default
    # branch, not a merge-base diff / changed-files list: the action's validation
    # is content-based, so it also fires on a branch merely STALE on
    # code-review.yml — a strictly wider class than "this PR edits the file".
    assert "github.event.repository.default_branch" in text, (
        "carve-out must compare against the default branch's content (two-dot), "
        "not the merge base — a stale branch trips the same validation."
    )


def test_workflow_carve_out_is_non_failure_and_visible():
    text = WORKFLOW_PATH.read_text(encoding="utf-8")
    # AC4: an expected-red check on a whole class of PRs trains us to stop reading
    # it — which is exactly how a REAL auto-merge failure gets missed. The carve-out
    # must therefore exit non-failure, and it must leave a signal on the PR (the
    # owner has to know a manual merge is owed).
    assert "CARVE_OUT_LABEL" in text, (
        "the carve-out must apply a label — it is the visible signal on the PR AND "
        "the field merge-train's `gh pr list --json labels` selector reads (AC5)."
    )
    assert "automerge-withheld:review-blind" in text, (
        "carve-out label name changed — merge-train.yml's selector matches this "
        "literal; renaming one side silently strands carve-out PRs behind main."
    )


def test_workflow_surfaces_permission_specific_remediation():
    text = WORKFLOW_PATH.read_text(encoding="utf-8")
    # AC6 (#1234): the generic "Failed to enable auto-merge on still-open PR"
    # error cost a full debugging cycle to trace back to a missing App permission.
    # When the underlying gh failure IS that refusal, say so.
    # The workflow greps for the refusal substring; in YAML-embedded bash the
    # backticks are backslash-escaped, so match that literal form.
    assert r"without \`workflows\` permission" in text, (
        "the error path must detect GitHub's workflows-permission refusal string "
        "and surface a permission-specific remediation line (#1234 AC6)."
    )
    assert "Workflows: Read and write" in text


def test_workflow_documents_carve_out_retention_rationale():
    text = WORKFLOW_PATH.read_text(encoding="utf-8")
    # Supersedes the old removal-condition pin (#1234 AC11). The carve-out began
    # as a STOPGAP for the vacuous-green hole (#1236); since the comment-absence
    # gates (#1434/#1228) the `Verify review verdict` ladder fails CLOSED on
    # this class, and the block is retained deliberately for what a red check
    # cannot do: survive a self-edit of code-review.yml (the ladder rides the
    # very file this class edits; this block does not) and mark the red as
    # review-blindness (label + comment; merge-train keys branch freshness off
    # the label). If the rationale drops the #1434/#1228 citation or the
    # defense-in-depth framing, the next reader will either delete the block as
    # stale scaffolding or re-introduce #1236's "goes green" confusion.
    assert "#1434" in text and "#1228" in text, (
        "the carve-out rationale must cite the #1434/#1228 fail-closed gates as "
        "the primary defense for this class — the block is defense-in-depth on "
        "top of a red `review` check, no longer the sole gate."
    )
    assert "Defense-in-depth" in text, (
        "the carve-out rationale must state it is KEPT as defense-in-depth "
        "(self-edit of code-review.yml can weaken the in-file ladder; this "
        "block survives that) — without this framing it reads as removable "
        "stopgap scaffolding."
    )


def test_auto_merge_enable_is_sole_requester_of_workflows_scope():
    # AC8 (#1234): belt behind AC2's explicit down-scoping. The Workflows grant
    # lives on the *installation*, so every other workflow minting a token from
    # the same 'jarvis-ci' App could quietly acquire the widened scope. Pin the
    # blast radius: auto-merge-enable.yml is the only workflow that may ask for
    # it. A new consumer must land here deliberately, with a reviewer looking at
    # why a second workflow needs write access to CI definitions.
    workflows_dir = WORKFLOW_PATH.parent
    requesters = sorted(
        p.name
        for p in workflows_dir.glob("*.yml")
        if "permission-workflows" in p.read_text(encoding="utf-8")
    )
    assert requesters == [WORKFLOW_PATH.name], (
        "only auto-merge-enable.yml may request the workflows App-token scope; "
        f"found: {requesters}. If another workflow genuinely needs it, justify "
        "the widened blast radius before relaxing this invariant (#1234 AC8)."
    )


def test_auto_merge_enable_is_not_a_canon_baseline_file():
    # AC10 (#1234): scripts/repo_baseline/canon/ files are mirrored into other
    # repos, so a change there owes a parity slice. auto-merge-enable.yml is
    # jarvis-local — this test pins that, so if it is ever promoted to canon the
    # red forces the parity question instead of silently skipping it.
    canon_dir = WORKFLOW_PATH.resolve().parents[2] / "scripts" / "repo_baseline" / "canon"
    assert not (canon_dir / WORKFLOW_PATH.name).exists(), (
        "auto-merge-enable.yml became a canon baseline file — the #1234 carve-out "
        "and workflows-scope grant now owe a canon-parity slice."
    )


def test_workflow_has_concurrency_guard():
    text = WORKFLOW_PATH.read_text(encoding="utf-8")
    assert "concurrency:" in text, (
        "auto-merge-enable must declare a concurrency group to serialize per-PR runs."
    )
    assert "cancel-in-progress: false" in text, (
        "auto-merge-enable must not cancel an in-flight run mid-enable — a cancel "
        "after token mint but before `gh pr merge` leaves the PR un-enrolled."
    )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

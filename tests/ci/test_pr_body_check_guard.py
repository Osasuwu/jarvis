"""Behaviour of `require-linked-issue` in .github/workflows/pr-body-check.yml.

Each test runs the job's real github-script body under node (tests/ci/run_github_script.js)
with recording stubs for `core` and `github.rest.issues.get`, then asserts what the run
reported: the failure messages, the bypass notices and the issues it looked up. Nothing here
re-implements the rule in Python (#1967; the mirror class is #1944).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import yaml

_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_PATH = _ROOT / ".github" / "workflows" / "pr-body-check.yml"
HARNESS = Path(__file__).resolve().parent / "run_github_script.js"
REPO = {"owner": "Osasuwu", "repo": "jarvis"}

NO_LINK = (
    'PR body must include a linked issue reference (e.g. "Closes #123" to auto-close, or '
    '"Refs #123" to link a partial-work PR without closing), a [no-issue] line for trivial '
    "fix-inline drive-bys (#428), or the priority:critical label for hotfixes."
)
NOTICE_NO_ISSUE = "require-linked-issue bypassed: [no-issue] — fix-inline drive-by per #428."
PASSED_NO_LOOKUP = {"failed": [], "notices": [], "lookups": []}
BLOCKED = {"failed": [NO_LINK], "notices": [], "lookups": []}
# D14 (#2055): the lane's machine user gets no [no-issue] / refactor: bypass.
BOT_BLOCKED = {
    "failed": [
        "require-linked-issue: osasuwu-bot PRs get no [no-issue] or refactor: bypass "
        '(D14, #2055); link an issue with "Closes #N" or "Refs #N".'
    ],
    "notices": [],
    "lookups": [],
}


def _step() -> dict:
    doc = yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))
    return next(
        step
        for step in doc["jobs"]["require-linked-issue"]["steps"]
        if "script" in (step.get("with") or {})
    )


def _script() -> str:
    return _step()["with"]["script"]


def run(
    body: str = "",
    title: str = "feat: x",
    labels: tuple[str, ...] = (),
    author: str = "Osasuwu",
    issues: tuple[str, ...] = ("Osasuwu/jarvis#42",),
    step_env: dict | None = None,
    commits: tuple[str, ...] = (),
    closed: tuple[str, ...] = (),
    pulls: tuple[str, ...] = (),
    outages: tuple[str, ...] = (),
) -> dict:
    """`step_env` replaces the step's own `env:` (read from the workflow by default)."""
    node = shutil.which("node")
    assert node, "node is not on PATH; the pytest job runs on ubuntu-latest, which ships it"
    payload = {
        "pull_request": {
            "body": body,
            "title": title,
            "labels": [{"name": n} for n in labels],
            "user": {"login": author},
            "number": 7000,
        }
    }
    proc = subprocess.run(
        [node, str(HARNESS)],
        input=json.dumps(
            {
                "script": _script(),
                "repo": REPO,
                "payload": payload,
                "issues": list(issues),
                "commits": list(commits),
                "closed": list(closed),
                "pulls": list(pulls),
                "outages": list(outages),
            }
        ),
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
        check=False,
        env={
            **{k: v for k, v in os.environ.items() if k != "LANE_BOT_LOGIN"},
            **(_step().get("env") or {} if step_env is None else step_env),
        },
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


# --- linkage -------------------------------------------------------------------------------


def test_every_github_closing_keyword_and_refs_links_the_issue():
    """AC3: GitHub's nine closing keywords, in any case and with `:`, plus refs/references."""
    keywords = [
        "close", "closes", "closed", "fix", "fixes", "fixed", "resolve", "resolves", "resolved",
        "ref", "refs", "reference", "references",
    ]  # fmt: skip
    bodies = [f"{k} #42" for k in keywords]
    bodies += ["CLOSES #42", "Fixed: #42", "Resolves:#42", "Some prose.\n\nRefs #42\n"]
    expected = {"failed": [], "notices": [], "lookups": ["Osasuwu/jarvis#42"]}
    wrong = {b: r for b in bodies if (r := run(b)) != expected}
    assert wrong == {}


def test_cross_repo_and_url_references_look_up_the_named_repo():
    """AC3: `owner/repo#N` and the issue URL link, and the existence check asks that repo."""
    for body in ("Closes Other/proj#7", "Fixes https://github.com/Other/proj/issues/7"):
        result = run(body, issues=("Other/proj#7",))
        assert result == {"failed": [], "notices": [], "lookups": ["Other/proj#7"]}, body


def test_repeated_reference_is_looked_up_once():
    result = run("Closes #42\n\nRefs #42, see also fixes Osasuwu/jarvis#42")
    assert result == {"failed": [], "notices": [], "lookups": ["Osasuwu/jarvis#42"]}


def test_linked_issue_that_does_not_exist_fails():
    assert run("Closes #999") == {
        "failed": ["Linked issue Osasuwu/jarvis#999 does not exist or is not accessible."],
        "notices": [],
        "lookups": ["Osasuwu/jarvis#999"],
    }


def test_keyword_inside_a_longer_word_does_not_link():
    """AC1: `prefixes #12` / `suffixes #12` are not `fixes #12`; prose verbs are not keywords."""
    bodies = [
        "prefixes #12", "suffixes #12", "discloses #12", "unresolved #12",
        "This PR refers to #42 for background.", "This is close to done.", "",
    ]  # fmt: skip
    wrong = {b: r for b in bodies if (r := run(b, issues=("Osasuwu/jarvis#12",))) != BLOCKED}
    assert wrong == {}


# --- bypasses (AC4: each one passes and names itself in a notice) ---------------------------


def test_bot_author_bypasses_with_notice():
    assert run("bump foo", author="dependabot[bot]") == {
        "failed": [],
        "notices": [
            "require-linked-issue bypassed: bot author — dependabot[bot] cannot author linked issues."
        ],
        "lookups": [],
    }


def test_priority_critical_label_bypasses_with_notice():
    assert run("urgent prod fix", labels=("priority:critical",)) == {
        "failed": [],
        "notices": ["require-linked-issue bypassed: priority:critical — hotfix label present."],
        "lookups": [],
    }


def test_other_labels_do_not_bypass():
    assert run("trivial change", labels=("priority:medium", "documentation")) == BLOCKED


def test_no_issue_on_its_own_body_line_bypasses_with_notice():
    """AC2 accepting half: the directive on a line of its own, any case, LF or CRLF."""
    bodies = ["Drive-by docs fix.\n\n[no-issue]\n", "Drive-by.\r\n\r\n  [NO-ISSUE]  \r\n"]
    expected = {"failed": [], "notices": [NOTICE_NO_ISSUE], "lookups": []}
    wrong = {b: r for b in bodies if (r := run(b)) != expected}
    assert wrong == {}


def test_no_issue_as_last_title_token_bypasses_with_notice():
    """AC2: the squash commit title carries the marker last, as the commit-msg hook expects."""
    assert run("", title="fix(tests): isolate env [no-issue]") == {
        "failed": [],
        "notices": [NOTICE_NO_ISSUE],
        "lookups": [],
    }


def test_no_issue_inside_prose_does_not_bypass():
    """AC2 rejecting half: the marker quoted or explained is not the directive."""
    cases = [
        ("This PR explains the [no-issue] marker.", "feat: x"),
        ("Use `[no-issue]` for drive-bys.", "feat: x"),
        ("[no-issue] inline doc fix", "feat: x"),
        ("", "docs: explain the [no-issue] escape"),
        ("There is no issue with this change.", "feat: x"),
    ]
    wrong = {c: r for c in cases if (r := run(c[0], title=c[1])) != BLOCKED}
    assert wrong == {}


def test_refactor_title_prefix_bypasses_with_notice():
    expected = {
        "failed": [],
        "notices": [
            "require-linked-issue bypassed: refactor: title prefix — "
            "structural cleanup without a parent issue."
        ],
        "lookups": [],
    }
    titles = ["refactor: split foo", "Refactor(security): narrow", "REFACTOR(api): x"]
    wrong = {t: r for t in titles if (r := run("", title=t)) != expected}
    assert wrong == {}


def test_refactor_outside_the_title_prefix_does_not_bypass():
    titles = ["Refactoring the auth module", "feat: include refactor: in description"]
    wrong = {t: r for t in titles if (r := run("body", title=t)) != BLOCKED}
    assert wrong == {}


# --- D14 (#2055): the lane bot links an issue, always ----------------------------------------


def test_lane_bot_gets_no_no_issue_or_refactor_bypass():
    """AC1-3: every bypass a human may use is refused to osasuwu-bot, in any login case."""
    cases = [
        ("Drive-by.\n\n[no-issue]\n", "fix: x", "osasuwu-bot"),
        ("", "fix(tests): isolate env [no-issue]", "osasuwu-bot"),
        ("", "refactor: split foo", "osasuwu-bot"),
        ("", "refactor(api): narrow", "Osasuwu-Bot"),
        ("No link at all.", "feat: x", "osasuwu-bot"),
    ]
    wrong = {c: r for c in cases if (r := run(c[0], title=c[1], author=c[2])) != BOT_BLOCKED}
    assert wrong == {}


def test_lane_bot_linking_an_issue_passes_without_a_bypass_notice():
    """AC4: the link is what passes it — the [no-issue] line and refactor: title are ignored."""
    result = run("Closes #42\n\n[no-issue]\n", title="refactor: x", author="osasuwu-bot")
    assert result == {"failed": [], "notices": [], "lookups": ["Osasuwu/jarvis#42"]}


def test_lane_bot_keeps_the_priority_critical_bypass():
    """AC6: D14 removes only the two paperwork bypasses; the hotfix label is unchanged."""
    assert run("urgent", labels=("priority:critical",), author="osasuwu-bot") == {
        "failed": [],
        "notices": ["require-linked-issue bypassed: priority:critical — hotfix label present."],
        "lookups": [],
    }


def test_missing_lane_bot_login_fails_closed():
    """AC7: without the login the deny rule cannot apply, so no bypass is granted to anyone."""
    expected = {
        "failed": [
            "require-linked-issue: LANE_BOT_LOGIN is empty; the step must set it so the "
            "D14 deny rule (#2055) can apply."
        ],
        "notices": [],
        "lookups": [],
    }
    assert run("Drive-by.\n\n[no-issue]\n", step_env={}) == expected


# --- absorbed slices (#1178): a `(#N)` commit headline the body does not link ----------------

INCIDENT_1173 = (
    "feat(agents): executor lane (#1169)",
    "feat(deslop): diff_gate (#1159)",
    "feat(skills): Fowler-12 self-review (#1155)",
)
INCIDENT_ISSUES = ("Osasuwu/jarvis#1169", "Osasuwu/jarvis#1159", "Osasuwu/jarvis#1155")


def _orphaned(*keys: str) -> str:
    return (
        "require-linked-issue: commit headlines reference open issue(s) the PR body does not "
        f"link: {', '.join(keys)}. If the PR ships an issue's whole scope, add a closing line "
        '("Closes #N") for it; if the reference is not an absorbed slice, link it with '
        '"Refs #N" (docs/reference/pr-issue-linkage.md, #1178).'
    )


def test_incident_1173_three_slices_one_closes_line_flags_the_other_two():
    """AC1/AC2/AC6: the #1173 shape — 3 slice commits, body closes 1 → 2 named as orphaned."""
    result = run("Closes #1169", commits=INCIDENT_1173, issues=INCIDENT_ISSUES)
    assert result == {
        "failed": [_orphaned("#1159", "#1155")],
        "notices": [],
        "lookups": ["Osasuwu/jarvis#1169", "Osasuwu/jarvis#1159", "Osasuwu/jarvis#1155"],
    }


def test_every_closing_keyword_in_the_body_covers_a_headline_ref():
    """AC1: each keyword variant counts as listing the slice."""
    for kw in ("close", "closed", "fix", "fixed", "resolve", "resolved", "Resolves:"):
        body = f"Closes #1169\n{kw} #1159\n{kw} #1155"
        result = run(body, commits=INCIDENT_1173, issues=INCIDENT_ISSUES)
        assert result["failed"] == [], kw


def test_refs_line_is_the_escape_hatch_for_a_non_absorbed_ref():
    """AC3: `Refs #N` states the ref is not an absorbed slice, and the check accepts it."""
    body = "Closes #1169\nRefs #1159\nRefs #1155"
    result = run(body, commits=INCIDENT_1173, issues=INCIDENT_ISSUES)
    assert result["failed"] == []


def test_headline_ref_to_a_closed_issue_or_a_pull_request_passes():
    """AC4: back-references (closed issues, and PR numbers from squash titles) are not slices."""
    result = run(
        "Closes #1169",
        commits=INCIDENT_1173,
        issues=INCIDENT_ISSUES,
        closed=("Osasuwu/jarvis#1159",),
        pulls=("Osasuwu/jarvis#1155",),
    )
    assert result == {
        "failed": [],
        "notices": [],
        "lookups": ["Osasuwu/jarvis#1169", "Osasuwu/jarvis#1159", "Osasuwu/jarvis#1155"],
    }


def test_cross_repo_headline_ref_warns_and_does_not_fail():
    """AC5: `owner/other#N` in a headline is warned about, never failed on."""
    result = run("Closes #42", commits=("feat: port helper (Other/proj#9)",))
    assert result == {
        "failed": [],
        "notices": [],
        "lookups": ["Osasuwu/jarvis#42"],
        "warnings": [
            "require-linked-issue: commit headlines reference issue(s) in another repo: "
            "Other/proj#9. A closing keyword does not reliably close a foreign issue; close "
            "it by hand if this PR ships it (docs/reference/pr-issue-linkage.md)."
        ],
    }


def test_ref_only_in_a_commit_body_is_not_a_headline_ref():
    """AC1: only the headline (first line) is read — a body mention is not an absorbed slice."""
    commit = "feat: x (#42)\n\nfollow-up to (#1159)"
    result = run(
        "Closes #42", commits=(commit,), issues=("Osasuwu/jarvis#42", "Osasuwu/jarvis#1159")
    )
    assert result == {"failed": [], "notices": [], "lookups": ["Osasuwu/jarvis#42"]}


def test_headline_ref_to_a_missing_issue_is_skipped():
    """A `(#N)` that resolves to nothing (404) is not a slice this PR can close."""
    result = run("Closes #42", commits=("feat: x (#9999)",))
    assert result == {
        "failed": [],
        "notices": [],
        "lookups": ["Osasuwu/jarvis#42", "Osasuwu/jarvis#9999"],
    }


def test_headline_ref_lookup_outage_fails_closed():
    """A non-404 lookup error is not evidence the ref is closed: the gate fails, not passes."""
    result = run(
        "Closes #42",
        commits=("feat: x (#1159)",),
        issues=("Osasuwu/jarvis#42", "Osasuwu/jarvis#1159"),
        outages=("Osasuwu/jarvis#1159",),
    )
    assert result == {
        "failed": [
            "require-linked-issue: could not read commit-headline issue #1159 (HTTP 502); "
            "re-run the check."
        ],
        "notices": [],
        "lookups": ["Osasuwu/jarvis#42", "Osasuwu/jarvis#1159"],
    }

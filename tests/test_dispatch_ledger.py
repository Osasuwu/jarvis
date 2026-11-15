"""Tests for scripts/dispatch_ledger.py — the #2115 AC4 revisit count.

The ledger lines below are shapes copied from the real ledger comments on
Osasuwu/jarvis#2115: five-column rows, PR URLs, `repo #N` with a space, two dispatches
on one line, the PR named before its issue.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import dispatch_ledger as dl  # noqa: E402

LEDGER = dl.Ref("Osasuwu/jarvis", 2115)
AGENT_MSG = "feat(x): thing (#5)\n\nCo-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
OWNERS = {
    "jarvis": "Osasuwu/jarvis",
    "jarvis-private": "Osasuwu/jarvis-private",
    "like-current-song": "Osasuwu/like-current-song",
    "redrobot": "SergazyNarynov/redrobot",
}


def _commit(sha, login, message, parents=1):
    return {
        "sha": sha,
        "author": {"login": login} if login else None,
        "commit": {"message": message},
        "parents": [{"sha": f"p{i}"} for i in range(parents)],
    }


def _refs(line, default="Osasuwu/jarvis"):
    return [str(r) for r in dl.line_refs(line, default, OWNERS)]


# --- reading references --------------------------------------------------


def test_line_refs_reads_every_reference_form_the_ledger_uses():
    # full refs; a bare PR ref after a full ref takes that ref's repo
    assert _refs("batch-h outcome: SergazyNarynov/redrobot#3154 → PR #3270 merged") == [
        "SergazyNarynov/redrobot#3154",
        "SergazyNarynov/redrobot#3270",
    ]
    # a bare ref first on the line is the ledger's repo; a short `repo#N`
    assert _refs("| #2000 | — (subagent) | x | jarvis-private#84 | held |") == [
        "Osasuwu/jarvis#2000",
        "Osasuwu/jarvis-private#84",
    ]
    # a PR given only as a URL (comments [99]/[100])
    assert _refs(
        "| Osasuwu/jarvis#2160 | — | x | https://github.com/Osasuwu/jarvis-private/pull/96 |"
    ) == [
        "Osasuwu/jarvis#2160",
        "Osasuwu/jarvis-private#96",
    ]
    # `repo #N` with a space, then a bare ref in the same repo (comments [155]-[158])
    assert _refs("| like-current-song #281+#289 | — (subagent) | x | — |") == [
        "Osasuwu/like-current-song#281",
        "Osasuwu/like-current-song#289",
    ]
    # a short name the ledger never spells out in full tells no repo: skipped
    assert _refs("| scratch#1 | Osasuwu/jarvis#7 |") == ["Osasuwu/jarvis#7"]


def test_ledger_refs_collects_distinct_refs_with_short_names_from_the_whole_ledger():
    bodies = [
        "| redrobot#2550 | — | x | — | in progress |",  # short form before any full one
        "| SergazyNarynov/redrobot#2553 | — | x | SergazyNarynov/redrobot#2679 | held |",
        "| redrobot#2553 | — | x | — | merged |",  # the same issue again, short
    ]
    assert [str(r) for r in dl.ledger_refs(bodies, LEDGER.repo)] == [
        "SergazyNarynov/redrobot#2550",
        "SergazyNarynov/redrobot#2553",
        "SergazyNarynov/redrobot#2679",
    ]


def test_linked_refs_takes_keyword_links_only():
    text = (
        "fix(x): y (#12)\n\nCloses #12\nRefs Osasuwu/jarvis#5\n"
        "Fixes like-current-song#3\nfollow-up #9, see Osasuwu/jarvis#6"
    )
    assert dl.linked_refs(text, "Osasuwu/jarvis-private", OWNERS) == {
        dl.Ref("Osasuwu/jarvis-private", 12),
        dl.Ref("Osasuwu/jarvis", 5),
        dl.Ref("Osasuwu/like-current-song", 3),
    }


# --- edits and outcomes --------------------------------------------------


def test_human_commits_counts_only_unmarked_non_merge_non_bot_commits():
    commits = [
        _commit("aaaaaaa1", "Osasuwu", AGENT_MSG),
        _commit("bbbbbbb2", "Osasuwu", "Merge branch 'main' into feat/5", parents=2),
        _commit("ccccccc3", "dependabot[bot]", "bump x"),
        _commit("ddddddd4", "Osasuwu", "fix typo by hand"),
        _commit(
            "eeeeeee5", "Osasuwu", "docs: x\n\nCo-Authored-By: Jarvis <jarvis@personal-ai-agent>"
        ),
    ]
    assert dl.human_commits(commits) == ["ddddddd by Osasuwu: fix typo by hand"]


def test_human_commits_reads_an_unreadable_list_as_edited():
    assert dl.human_commits([]) == ["no commits readable; cannot show the PR is unedited"]


def test_issue_outcome_and_verdict():
    assert dl.issue_outcome([("closed", True, [])]) == dl.MERGED_UNEDITED
    assert dl.issue_outcome([("closed", True, []), ("closed", True, ["x"])]) == dl.EDITED
    assert dl.issue_outcome([("open", False, []), ("closed", False, [])]) == dl.OPEN
    assert dl.issue_outcome([("closed", False, [])]) == dl.CLOSED
    # the threshold the 2026-10-17 freeze decision fixed: >= 10 retires the lane
    assert dl.verdict(10) == "retire the lane"
    assert dl.verdict(9) == "reopen the freeze decision"


# --- end to end over a fake GitHub ---------------------------------------


def _fake_github():
    def issue(user):
        return {"user": {"login": user}, "state": "closed"}

    def pr(body, merged):
        return {
            "title": "t",
            "body": body,
            "state": "closed" if merged else "open",
            "merged_at": "2026-10-21" if merged else None,
        }

    is_pr = {"pull_request": {"url": "u"}}
    data = {
        "repos/Osasuwu/jarvis/issues/2115/comments": [
            {"body": "| Osasuwu/jarvis#1 | — | 2026-10-20 | #11 | merged |"},
            # two dispatches on one line (comment [296]); #13 is an unrelated PR
            {"body": "Osasuwu/jarvis#2 → #12 merged, also #13. Osasuwu/jarvis#3 → #14"},
            # the PR first, the issue named elsewhere (comment [294])
            {"body": "new PRs: Osasuwu/jarvis#15 (4)"},
            {"body": "| Osasuwu/jarvis#4 | — | 2026-10-20 | — | in progress |"},
            # a bare #N meant for another repo: not readable in the ledger's repo
            {"body": "| SergazyNarynov/redrobot (no issue; #9999 follow-up) | — | x |"},
        ],
        "repos/Osasuwu/jarvis/issues/1": issue("Osasuwu"),
        "repos/Osasuwu/jarvis/issues/2": issue("Osasuwu"),
        "repos/Osasuwu/jarvis/issues/3": issue("Osasuwu"),
        "repos/Osasuwu/jarvis/issues/4": issue("SergazyNarynov"),
        **{f"repos/Osasuwu/jarvis/issues/{n}": is_pr for n in (11, 12, 13, 14, 15)},
        "repos/Osasuwu/jarvis/pulls/11": pr("Closes #1", True),
        "repos/Osasuwu/jarvis/pulls/12": pr("Closes #2", True),
        "repos/Osasuwu/jarvis/pulls/13": pr(
            "chore: unrelated, mentions #2\n\nRefs #11", True
        ),  # links a PR
        "repos/Osasuwu/jarvis/pulls/14": pr("Closes #3", False),
        "repos/Osasuwu/jarvis/pulls/15": pr("Closes #4", True),
        "repos/Osasuwu/jarvis/pulls/11/commits": [_commit("a1", "Osasuwu", AGENT_MSG)],
        "repos/Osasuwu/jarvis/pulls/12/commits": [
            _commit("b1", "Osasuwu", AGENT_MSG),
            _commit("b2", "Osasuwu", "hand edit"),
        ],
        "repos/Osasuwu/jarvis/pulls/13/commits": [_commit("c1", "Osasuwu", "hand edit")],
        "repos/Osasuwu/jarvis/pulls/15/commits": [_commit("d1", "Osasuwu", AGENT_MSG)],
    }

    def api(path):
        if path not in data:  # what `gh api` does on a 404
            raise subprocess.CalledProcessError(1, ["gh", "api", path])
        return data[path]

    return api


def test_build_report_attributes_prs_by_their_links_and_classifies_each_issue():
    report = dl.build_report(LEDGER, _fake_github(), workers=2)
    assert [(str(r.issue), r.author, r.prs, r.outcome) for r in report.rows] == [
        ("Osasuwu/jarvis#1", "Osasuwu", ["Osasuwu/jarvis#11"], dl.MERGED_UNEDITED),
        ("Osasuwu/jarvis#2", "Osasuwu", ["Osasuwu/jarvis#12"], dl.EDITED),
        ("Osasuwu/jarvis#3", "Osasuwu", ["Osasuwu/jarvis#14"], dl.OPEN),
        ("Osasuwu/jarvis#4", "SergazyNarynov", ["Osasuwu/jarvis#15"], dl.MERGED_UNEDITED),
    ]
    assert report.rows[1].touches == ["Osasuwu/jarvis#12: b2 by Osasuwu: hand edit"]
    assert report.unattributed == [dl.Ref("Osasuwu/jarvis", 13)]
    assert report.unreadable == 1  # Osasuwu/jarvis#9999


def test_render_counts_only_the_users_merged_issues():
    text = dl.render(dl.build_report(LEDGER, _fake_github(), workers=2), "osasuwu")
    # #1 unedited + #2 edited; #3 is open, #4 is a collaborator's issue
    assert "Brought to merge (`merged-unedited` + `edited`): **2** (threshold 10)" in text
    assert "→ **reopen the freeze decision**" in text
    assert "| merged-unedited | 1 |\n| edited | 1 |\n| closed | 0 |\n| open | 1 |" in text

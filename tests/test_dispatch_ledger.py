"""Tests for scripts/dispatch_ledger.py — the #2115 AC4 revisit count.

The ledger rows below are shapes copied from the real ledger comments on
Osasuwu/jarvis#2115 (five-column rows, run tables, prose outcome lines).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import dispatch_ledger as dl  # noqa: E402

LEDGER = dl.Ref("Osasuwu/jarvis", 2115)
AGENT_MSG = "feat(x): thing (#5)\n\nCo-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"


def _commit(sha, login, message, parents=1):
    return {
        "sha": sha,
        "author": {"login": login} if login else None,
        "commit": {"message": message},
        "parents": [{"sha": f"p{i}"} for i in range(parents)],
    }


# --- parsing the rows ---------------------------------------------------


def test_parse_ledger_reads_the_row_shapes_the_ledger_holds():
    bodies = [
        # five-column row, full refs, PR in the fourth cell
        "| issue | card shown (UTC) | started (UTC) | PR | outcome |\n"
        "|---|---|---|---|---|\n"
        "| SergazyNarynov/redrobot#2184 (rc) | 2026-10-19 06:59 | 2026-10-19 07:20 "
        "| SergazyNarynov/redrobot#2643 | merged-unedited |",
        # bare issue ref (the ledger's repo) and a short `repo#N` PR ref
        "| #2000 | — (subagent) | 2026-10-20T14:42:31Z | jarvis-private#84 | held HIGH |",
        # prose outcome line with a bare PR ref in the issue's repo, then another issue
        "batch-h outcome: SergazyNarynov/redrobot#3154 → PR #3270 merged, see #2248",
        "| Osasuwu/jarvis-private#50 | — | 2026-10-19 19:05 | — | merged |",
        # a short name the ledger never spells out in full is skipped, not taken as the issue
        "| scratch#1 | Osasuwu/like-current-song#269 | subagent | #272 merged |",
    ]
    got = {
        str(d.issue): [str(r) for r in d.candidates] for d in dl.parse_ledger(bodies, LEDGER.repo)
    }
    assert got == {
        "SergazyNarynov/redrobot#2184": ["SergazyNarynov/redrobot#2643"],
        "Osasuwu/jarvis#2000": ["Osasuwu/jarvis-private#84"],
        "SergazyNarynov/redrobot#3154": [
            "SergazyNarynov/redrobot#3270",
            "SergazyNarynov/redrobot#2248",
        ],
        "Osasuwu/jarvis-private#50": [],
        "Osasuwu/like-current-song#269": ["Osasuwu/like-current-song#272"],
    }


def test_parse_ledger_merges_rows_of_one_issue_in_first_seen_order():
    bodies = [
        "| Osasuwu/jarvis#2131 | — (subagent) | 2026-10-20T15:58:45Z | #2150 | rework |",
        "| #2131 | — (subagent) | 2026-10-20T16:36:17Z | #2147, #2148, #2150 | ready |",
    ]
    dispatches = dl.parse_ledger(bodies, LEDGER.repo)
    assert [(str(d.issue), [r.number for r in d.candidates]) for d in dispatches] == [
        ("Osasuwu/jarvis#2131", [2150, 2147, 2148])
    ]


# --- attribution and edits ----------------------------------------------


def test_names_issue_accepts_the_issue_and_rejects_a_neighbour():
    issue = dl.Ref("Osasuwu/jarvis", 2129)
    assert dl.names_issue("Closes Osasuwu/jarvis#2129", issue, "Osasuwu/jarvis-private")
    assert dl.names_issue("Closes #2129", issue, "Osasuwu/jarvis")
    # a bare #N in another repo is that repo's issue, not this one
    assert not dl.names_issue("Closes #2129", issue, "Osasuwu/jarvis-private")
    # a longer number, or the same number in another repo, is not the issue
    assert not dl.names_issue(
        "Closes #21290 and Osasuwu/jarvis-private#2129", issue, "Osasuwu/jarvis"
    )


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
    assert dl.issue_outcome([]) == dl.NO_PR
    # the threshold the 2026-10-17 freeze decision fixed: >= 10 retires the lane
    assert dl.verdict(10) == "retire the lane"
    assert dl.verdict(9) == "reopen the freeze decision"


# --- end to end over a fake GitHub ---------------------------------------


def _fake_github():
    issue = lambda user: {"user": {"login": user}, "state": "closed"}  # noqa: E731
    pr = lambda body, merged: {  # noqa: E731
        "title": "t",
        "body": body,
        "state": "closed" if merged is not None else "open",
        "merged_at": merged,
        "pull_request": {},
    }
    data = {
        "repos/Osasuwu/jarvis/issues/2115/comments": [
            {"body": "| Osasuwu/jarvis#1 | — | 2026-10-20 | #11 | merged |"},
            {"body": "| Osasuwu/jarvis#2 | — | 2026-10-20 | #12, #13 | merged |"},
            {"body": "Osasuwu/jarvis#3 → #14 closed"},
            {"body": "| Osasuwu/jarvis#4 | — | 2026-10-20 | #15 | merged |"},
            {"body": "| Osasuwu/jarvis#11 | — | 2026-10-20 | — | PR named first |"},
            # a bare #N meant for another repo: not an issue of the ledger's repo
            {"body": "| SergazyNarynov/redrobot (no issue; #9999 follow-up) | — | x | — | — |"},
        ],
        "repos/Osasuwu/jarvis/issues/1": issue("Osasuwu"),
        "repos/Osasuwu/jarvis/issues/2": issue("Osasuwu"),
        "repos/Osasuwu/jarvis/issues/3": issue("Osasuwu"),
        "repos/Osasuwu/jarvis/issues/4": issue("SergazyNarynov"),
        "repos/Osasuwu/jarvis/issues/11": {"pull_request": {}},
        "repos/Osasuwu/jarvis/issues/12": {"pull_request": {}},
        "repos/Osasuwu/jarvis/issues/13": {"pull_request": {}},
        "repos/Osasuwu/jarvis/issues/14": {"pull_request": {}},
        "repos/Osasuwu/jarvis/issues/15": {"pull_request": {}},
        "repos/Osasuwu/jarvis/pulls/11": pr("Closes #1", "2026-10-21"),
        "repos/Osasuwu/jarvis/pulls/12": pr("Closes #2", "2026-10-21"),
        "repos/Osasuwu/jarvis/pulls/13": pr("unrelated, fixes #99", "2026-10-21"),
        "repos/Osasuwu/jarvis/pulls/14": pr("Closes #3", None),
        "repos/Osasuwu/jarvis/pulls/15": pr("Closes #4", "2026-10-21"),
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


def test_build_report_attributes_prs_and_classifies_each_issue():
    rows, dropped = dl.build_report(LEDGER, _fake_github())
    assert [(str(r.issue), r.author, r.prs, r.outcome) for r in rows] == [
        ("Osasuwu/jarvis#1", "Osasuwu", ["Osasuwu/jarvis#11"], dl.MERGED_UNEDITED),
        ("Osasuwu/jarvis#2", "Osasuwu", ["Osasuwu/jarvis#12"], dl.EDITED),
        ("Osasuwu/jarvis#3", "Osasuwu", ["Osasuwu/jarvis#14"], dl.OPEN),
        ("Osasuwu/jarvis#4", "SergazyNarynov", ["Osasuwu/jarvis#15"], dl.MERGED_UNEDITED),
    ]
    assert rows[1].touches == ["Osasuwu/jarvis#12: b2 by Osasuwu: hand edit"]
    assert [(str(ref), why) for ref, why in dropped] == [
        ("Osasuwu/jarvis#13", "in the row of Osasuwu/jarvis#2, but does not name it"),
        ("Osasuwu/jarvis#11", "named as the issue, but it is a pull request"),
        ("Osasuwu/jarvis#9999", "named as the issue, but not readable on GitHub"),
    ]


def test_render_counts_only_the_users_merged_issues(capsys):
    rows, dropped = dl.build_report(LEDGER, _fake_github())
    text = dl.render(rows, dropped, "osasuwu")
    # #1 unedited + #2 edited; #3 is open, #4 is a collaborator's issue
    assert "Brought to merge (`merged-unedited` + `edited`): **2** (threshold 10)" in text
    assert "→ **reopen the freeze decision**" in text
    assert "| merged-unedited | 1 |\n| edited | 1 |\n| closed | 0 |\n| open | 1 |" in text

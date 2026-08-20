"""#1572 - weekly_release_gather.py: repos.conf traversal (releases=weekly
filter), merged-PR window collection (dedup vs closed issues, Dependabot
filter, UTC window boundaries), closed-issue window (not_planned exclusion),
and remaining-issue collection (milestone-scoped, movement-in-window).

All gh/repos.conf I/O is injected via fakes - no real subprocess/network calls.
"""

from __future__ import annotations

import json

from scripts.repos_conf import RepoEntry
from scripts.weekly_release_gather import (
    WeeklyReleaseSourceKind,
    _gather_closed_issues_window,
    _gather_merged_window,
    _gather_prior_releases,
    _gather_remaining_issues,
    gather,
)

WINDOW_START = "2026-08-01T00:00:00+00:00"
WINDOW_END = "2026-08-20T00:00:00+00:00"


def _gh(stdout: str = "", returncode: int = 0):
    def fn(repo, args):
        return {"stdout": stdout, "stderr": "", "returncode": returncode}

    return fn


# -- _gather_prior_releases ----------------------------------------------------


def test_prior_releases_parses_release_rows():
    ndjson = "\n".join(
        json.dumps(r)
        for r in [
            {"tag_name": "v0.2.0", "published_at": "2026-08-01T00:00:00Z", "draft": False},
            {"tag_name": "v0.1.0", "published_at": "2026-07-01T00:00:00Z", "draft": False},
        ]
    )
    releases, prov = _gather_prior_releases("o/r", _gh(ndjson), now=0.0)
    assert [r["tag_name"] for r in releases] == ["v0.2.0", "v0.1.0"]
    assert prov.ok is True
    assert prov.input_rows == 2


def test_prior_releases_empty_on_gh_failure():
    releases, prov = _gather_prior_releases("o/r", _gh("", returncode=1), now=0.0)
    assert releases == []
    assert prov.ok is False


# -- _gather_merged_window ------------------------------------------------------


def test_merged_window_filters_by_merged_at():
    prs = [
        {
            "number": 10,
            "title": "feat: add thing",
            "mergedAt": "2026-08-10T00:00:00Z",
            "author": {"login": "alice"},
            "body": "",
        },
        {
            "number": 11,
            "title": "chore: old",
            "mergedAt": "2026-07-01T00:00:00Z",
            "author": {"login": "alice"},
            "body": "",
        },
    ]
    entries, refs, prov = _gather_merged_window(
        "o/r", _gh(json.dumps(prs)), WINDOW_START, WINDOW_END
    )
    assert [e["number"] for e in entries] == [10]
    assert refs == {"10"}


def test_merged_window_flags_dependabot():
    prs = [
        {
            "number": 12,
            "title": "chore(deps): bump x",
            "mergedAt": "2026-08-10T00:00:00Z",
            "author": {"login": "dependabot[bot]"},
            "body": "",
        },
    ]
    entries, refs, prov = _gather_merged_window(
        "o/r", _gh(json.dumps(prs)), WINDOW_START, WINDOW_END
    )
    assert entries[0]["is_dependabot"] is True


def test_merged_window_extracts_closed_issue_for_dedup():
    prs = [
        {
            "number": 13,
            "title": "fix: bug",
            "mergedAt": "2026-08-10T00:00:00Z",
            "author": {"login": "alice"},
            "body": "Closes #999",
        },
    ]
    entries, refs, prov = _gather_merged_window(
        "o/r", _gh(json.dumps(prs)), WINDOW_START, WINDOW_END
    )
    assert entries[0]["closes_issue"] == "999"
    assert refs == {"13", "999"}


# -- _gather_closed_issues_window -----------------------------------------------


def test_closed_issues_excludes_not_planned():
    issues = [
        {
            "number": 20,
            "title": "wontfix",
            "closedAt": "2026-08-10T00:00:00Z",
            "stateReason": "not_planned",
        },
        {
            "number": 21,
            "title": "real fix",
            "closedAt": "2026-08-11T00:00:00Z",
            "stateReason": "completed",
        },
    ]
    entries, refs, prov = _gather_closed_issues_window(
        "o/r", _gh(json.dumps(issues)), WINDOW_START, WINDOW_END, pr_linked_issue_refs=set()
    )
    assert [e["number"] for e in entries] == [21]


def test_closed_issues_dedups_against_pr_linked_issues():
    issues = [
        {
            "number": 22,
            "title": "already covered by its PR",
            "closedAt": "2026-08-11T00:00:00Z",
            "stateReason": "completed",
        },
    ]
    entries, refs, prov = _gather_closed_issues_window(
        "o/r", _gh(json.dumps(issues)), WINDOW_START, WINDOW_END, pr_linked_issue_refs={"22"}
    )
    assert entries == []


# -- _gather_remaining_issues ----------------------------------------------------


def test_remaining_issues_requires_milestone_and_movement_in_window():
    issues = [
        {
            "number": 30,
            "title": "in milestone, moved",
            "updatedAt": "2026-08-10T00:00:00Z",
            "milestone": {"title": "M1"},
        },
        {
            "number": 31,
            "title": "no milestone",
            "updatedAt": "2026-08-10T00:00:00Z",
            "milestone": None,
        },
        {
            "number": 32,
            "title": "stale",
            "updatedAt": "2026-01-01T00:00:00Z",
            "milestone": {"title": "M1"},
        },
    ]
    remaining, prov = _gather_remaining_issues(
        "o/r", _gh(json.dumps(issues)), WINDOW_START, WINDOW_END
    )
    assert [r["number"] for r in remaining] == [30]


# -- gather() end-to-end ---------------------------------------------------------


def test_gather_filters_repos_conf_to_weekly_releases_only():
    entries = [
        RepoEntry(name="o/weekly-repo", tokens={"releases": "weekly"}),
        RepoEntry(name="o/other-repo", tokens={}),
    ]

    def fake_run_gh(repo, args):
        if args[0] == "api":
            return {"stdout": "", "stderr": "", "returncode": 0}
        return {"stdout": "[]", "stderr": "", "returncode": 0}

    result = gather(
        jarvis_home="/fake",
        now="2026-08-20T00:00:00+00:00",
        read_repos_conf_entries_fn=lambda path: entries,
        run_gh_fn=fake_run_gh,
        now_fn=lambda: 1786000000.0,
    )
    repo_names = [r.repo for r in result.repos]
    assert repo_names == ["o/weekly-repo"]
    assert WeeklyReleaseSourceKind.REPOS_CONF in result.provenance

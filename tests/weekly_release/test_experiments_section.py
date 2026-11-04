"""#2184 - opt-in "Эксперименты недели" section: the repos.conf
`experiments=` token flags merged window PRs that touched an experiment
path, and the engine renders agent-authored lines for them under a heading,
citation-linted, placed between the disclosure and the retractions.

All gh/repos.conf I/O is injected via fakes - no real subprocess/network calls.
"""

from __future__ import annotations

import json

import pytest

from scripts.repos_conf import RepoEntry
from scripts.weekly_release_engine import (
    assemble_release_body,
    format_experiments_section,
    format_retraction_section,
    format_window_disclosure,
)
from scripts.weekly_release_gather import _gather_merged_window, gather

WINDOW_START = "2026-08-01T00:00:00+00:00"
WINDOW_END = "2026-08-20T00:00:00+00:00"


def _pr(number: int, paths: list[str]) -> dict:
    return {
        "number": number,
        "title": f"docs: pr {number}",
        "mergedAt": "2026-08-10T00:00:00Z",
        "author": {"login": "alice"},
        "body": "",
        "files": [{"path": p} for p in paths],
    }


class _RecordingGh:
    """Fake run_gh that answers `pr list` with `prs` and records each call's args."""

    def __init__(self, prs: list[dict]):
        self.prs = prs
        self.calls: list[list[str]] = []

    def __call__(self, repo, args):
        self.calls.append(args)
        if args[:2] == ["pr", "list"]:
            return {"stdout": json.dumps(self.prs), "stderr": "", "returncode": 0}
        return {"stdout": "", "stderr": "", "returncode": 0}


# -- gather: the is_experiment flag ---------------------------------------------


def test_pr_touching_a_prefix_is_flagged_and_one_outside_is_not():
    gh = _RecordingGh(
        [
            _pr(10, ["docs/plans/round-7/h0.md"]),
            _pr(11, ["redrobot/sandbox/x.py", "reports/paper/a.md"]),
            _pr(12, ["redrobot/sandbox/x.py", "docs/decisions/a.md"]),
        ]
    )
    entries, _, _ = _gather_merged_window(
        "o/r", gh, WINDOW_START, WINDOW_END, ("docs/plans/", "reports/")
    )
    flags = {e["number"]: e["is_experiment"] for e in entries}
    assert flags == {10: True, 11: True, 12: False}
    assert gh.calls[0][-1].endswith(",files")


def test_without_prefixes_query_and_entries_are_unchanged():
    gh = _RecordingGh([_pr(10, ["docs/plans/round-7/h0.md"])])
    entries, _, _ = _gather_merged_window("o/r", gh, WINDOW_START, WINDOW_END)
    assert gh.calls[0][-1] == "number,title,mergedAt,author,body"
    assert "is_experiment" not in entries[0]


def _gather_with(tokens: dict[str, str], prs: list[dict]):
    entry = RepoEntry(name="o/r", tokens={"releases": "weekly", **tokens})
    gh = _RecordingGh(prs)
    result = gather(
        jarvis_home="/fake",
        now=WINDOW_END,
        read_repos_conf_entries_fn=lambda path: [entry],
        run_gh_fn=gh,
        now_fn=lambda: 1786000000.0,
    )
    return result.repos[0], gh


def test_gather_exposes_experiment_refs_from_token():
    repo, _ = _gather_with(
        {"experiments": "docs/plans/,reports/"},
        [_pr(10, ["docs/plans/round-7/h0.md"]), _pr(11, ["redrobot/x.py"])],
    )
    assert repo.experiment_refs == {"10"}
    assert repo.to_dict()["experiment_refs"] == ["10"]


def test_gather_without_token_has_no_experiment_refs_and_no_files_query():
    repo, gh = _gather_with({}, [_pr(10, ["docs/plans/round-7/h0.md"])])
    assert repo.experiment_refs == set()
    pr_list_calls = [c for c in gh.calls if c[:2] == ["pr", "list"]]
    assert all(not c[-1].endswith(",files") for c in pr_list_calls)


# -- engine: format_experiments_section -----------------------------------------


def test_no_lines_means_no_section():
    assert format_experiments_section([], {"10"}) == ""
    assert format_experiments_section(["", "  "], {"10"}) == ""


def test_section_has_heading_and_the_lines():
    line = "- Обрезка простоя → −8.1 % часов при той же p99 → принята (#10)."
    section = format_experiments_section([line], {"10"})
    assert section.splitlines() == ["## 🧪 Эксперименты недели", line]


def test_uncited_line_is_rejected():
    with pytest.raises(ValueError, match="citation"):
        format_experiments_section(["- Часы упали на 8 %."], {"10"})


def test_line_citing_a_ref_outside_the_window_is_rejected():
    with pytest.raises(ValueError, match="citation"):
        format_experiments_section(["- Обрезка простоя принята (#99)."], {"10"})


def test_more_than_five_lines_is_rejected():
    lines = [f"- Эксперимент {i} (#10)." for i in range(6)]
    with pytest.raises(ValueError, match="at most 5"):
        format_experiments_section(lines, {"10"})


# -- engine: placement in the body ----------------------------------------------


def test_section_sits_after_notes_and_disclosure_and_before_retractions():
    disclosure = format_window_disclosure(WINDOW_START, WINDOW_END, truncated=True)
    experiments = format_experiments_section(["- Обрезка простоя принята (#10)."], {"10"})
    retractions = format_retraction_section(
        [{"original_ref": "5", "revert_ref": "11", "title": "revert x"}]
    )
    body = assemble_release_body(
        notes_body="- Notes (#12).",
        remaining_section="- Remaining (#13).",
        full_changelog_url="",
        retraction_section=retractions,
        disclosure_section=disclosure,
        experiments_section=experiments,
    )
    order = [
        body.index("- Notes (#12)."),
        body.index(disclosure),
        body.index("## 🧪 Эксперименты недели"),
        body.index("## ⏪ Отозвано"),
        body.index("- Remaining (#13)."),
    ]
    assert order == sorted(order)


def test_empty_section_leaves_body_unchanged():
    kwargs = dict(notes_body="- Notes (#12).", remaining_section="", full_changelog_url="")
    assert assemble_release_body(**kwargs, experiments_section="") == assemble_release_body(
        **kwargs
    )

"""Tests for morning_gather I/O adapter (#1586).

Thin adapter tests — the real logic (parse_repos_conf, _gather_gh_milestones,
gather_decisions) is already covered by tests/status/test_status_gather.py and
reused here unmodified. These tests only check morning_gather's own wiring.
"""

from __future__ import annotations

import json

from scripts.status_gather import parse_repos_conf
from scripts.morning_gather import gather


def _fixture_repos_conf(content: str) -> callable:
    return lambda path: parse_repos_conf(content)


def _fixture_run_gh(result: dict) -> callable:
    return lambda repo, args: result


def _fixture_query_by_table(table_rows: dict) -> callable:
    def _query(url: str, key: str, table: str, params: dict) -> list[dict] | None:
        return table_rows.get(table, [])

    return _query


def _make_gh_empty() -> dict:
    return {"stdout": "", "stderr": "", "returncode": 0}


def _make_gh_milestones_success(milestones: list) -> dict:
    """gh api --jq streams one JSON object per line, not a JSON array."""
    return {
        "stdout": "\n".join(json.dumps(m) for m in milestones),
        "stderr": "",
        "returncode": 0,
    }


def _fixture_now() -> callable:
    fixed = 1_717_000_000.0
    return lambda: fixed


def test_gather_traverses_all_repos_conf_lines_including_inactive_marked_ones(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_KEY", "test-key")

    repos_conf_content = (
        "Osasuwu/jarvis project=3\nSergazyNarynov/redrobot project=1 inactive=true\n"
    )

    result = gather(
        jarvis_home="/fake/home",
        read_repos_conf_fn=_fixture_repos_conf(repos_conf_content),
        run_gh_fn=_fixture_run_gh(_make_gh_empty()),
        query_supabase_fn=_fixture_query_by_table({}),
        now_fn=_fixture_now(),
    )

    assert result.repos == ["Osasuwu/jarvis", "SergazyNarynov/redrobot"]


def test_gather_populates_milestones_per_repo_via_injected_run_gh(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_KEY", "test-key")

    milestone = {
        "number": 64,
        "title": "Status → daily work digest",
        "open_issues": 5,
        "closed_issues": 2,
        "due_on": None,
    }

    result = gather(
        jarvis_home="/fake/home",
        read_repos_conf_fn=_fixture_repos_conf("Osasuwu/jarvis\n"),
        run_gh_fn=_fixture_run_gh(_make_gh_milestones_success([milestone])),
        query_supabase_fn=_fixture_query_by_table({}),
        now_fn=_fixture_now(),
    )

    assert result.milestones["Osasuwu/jarvis"] == [milestone]


def test_gather_populates_decisions_via_injected_query_supabase(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_KEY", "test-key")

    decision_row = {
        "id": "84581b06-c1da-4b2c-be60-9726c02fe15c",
        "actor": "session:grill",
        "kind": "decision_made",
        "payload": {"decision": "v2 schema", "rationale": "generalized sections"},
        "created_at": "2026-08-10T00:00:00+00:00",
    }

    result = gather(
        jarvis_home="/fake/home",
        read_repos_conf_fn=_fixture_repos_conf("Osasuwu/jarvis\n"),
        run_gh_fn=_fixture_run_gh(_make_gh_empty()),
        query_supabase_fn=_fixture_query_by_table({"episodes": [decision_row]}),
        now_fn=_fixture_now(),
    )

    assert len(result.decisions) == 1
    assert result.decisions[0].id == "84581b06-c1da-4b2c-be60-9726c02fe15c"


def test_gather_populates_goals_and_owner_tasks_via_injected_query_supabase(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_KEY", "test-key")

    goal_row = {"slug": "ship-morning-digest", "status": "active", "priority": 1}
    task_row = {"id": "task-1", "assignee": "owner", "status": "pending", "goal": "..."}

    result = gather(
        jarvis_home="/fake/home",
        read_repos_conf_fn=_fixture_repos_conf("Osasuwu/jarvis\n"),
        run_gh_fn=_fixture_run_gh(_make_gh_empty()),
        query_supabase_fn=_fixture_query_by_table({"goals": [goal_row], "task_queue": [task_row]}),
        now_fn=_fixture_now(),
    )

    assert result.goals == [goal_row]
    assert result.owner_tasks == [task_row]


def test_gather_missing_supabase_creds_marks_sources_not_ok_without_raising(monkeypatch):
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_KEY", raising=False)

    result = gather(
        jarvis_home="/fake/home",
        read_repos_conf_fn=_fixture_repos_conf("Osasuwu/jarvis\n"),
        run_gh_fn=_fixture_run_gh(_make_gh_empty()),
        query_supabase_fn=_fixture_query_by_table({}),
        now_fn=_fixture_now(),
    )

    assert result.decisions == []
    assert result.goals == []
    assert result.owner_tasks == []
    assert result.provenance["goals"]["ok"] is False
    assert result.provenance["owner_tasks"]["ok"] is False
    assert result.provenance["supabase_decisions"]["ok"] is False

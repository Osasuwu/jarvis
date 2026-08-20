"""PR #1662 review: outcome_list must not leak cross-project (personal)
outcomes — sibling of the goal_list leak fixed in the same PR
(test_goal_list_privacy.py). Before the fix, an unscoped ``outcome_list``
call (no ``project`` arg) applied no project filter at all, so
``project IS NULL`` rows — personal task outcomes — came back alongside
every project-scoped outcome.
"""

from __future__ import annotations

import pytest

from server import _handle_outcome_list

from supabase_stubs import FakeClient

OUTCOMES = [
    {
        "id": "o1",
        "task_type": "delegation",
        "task_description": "Ship weekly-release S1",
        "outcome_status": "success",
        "project": "jarvis",
        "created_at": "2026-08-19T10:00:00Z",
    },
    {
        "id": "o2",
        "task_type": "delegation",
        "task_description": "Calibrate arm",
        "outcome_status": "success",
        "project": "redrobot",
        "created_at": "2026-08-19T11:00:00Z",
    },
    {
        "id": "o3",
        "task_type": "delegation",
        "task_description": "Book dentist appointment",
        "outcome_status": "success",
        "project": None,
        "created_at": "2026-08-19T12:00:00Z",
    },
]


def _outcomes_handler(call):
    rows = OUTCOMES
    for f in call["filters"]:
        op, col = f[0], f[1]
        if op == "eq":
            rows = [o for o in rows if o.get(col) == f[2]]
        elif op == "is":
            rows = [o for o in rows if (o.get(col) is None) == (f[2] == "null")]
        elif op == "not_is":
            rows = [o for o in rows if (o.get(col) is None) != (f[2] == "null")]
    return rows


def _client():
    client = FakeClient()
    client.table_handlers["task_outcomes"] = _outcomes_handler
    return client


@pytest.mark.asyncio
async def test_unscoped_outcome_list_excludes_cross_project_outcomes(monkeypatch):
    monkeypatch.setattr("server._get_client", _client)

    result = await _handle_outcome_list({})

    text = result[0].text
    assert "Ship weekly-release S1" in text
    assert "Calibrate arm" in text
    assert "Book dentist appointment" not in text


@pytest.mark.asyncio
async def test_project_scoped_outcome_list_still_filters_by_project(monkeypatch):
    monkeypatch.setattr("server._get_client", _client)

    result = await _handle_outcome_list({"project": "jarvis"})

    text = result[0].text
    assert "Ship weekly-release S1" in text
    assert "Calibrate arm" not in text
    assert "Book dentist appointment" not in text

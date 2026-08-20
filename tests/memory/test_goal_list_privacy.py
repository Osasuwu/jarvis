"""#1572 AC7 — goal_list must not leak cross-project (personal) goals.

Before the fix, an unscoped ``goal_list`` call (no ``project`` arg) applied
no project filter at all, so ``project IS NULL`` rows — personal,
cross-project goals per ``_format_goal``'s own "cross-project" framing —
came back alongside every project-scoped goal. ``/weekly-release`` calls
``goal_list`` to build a release note's goal section; a leak there means
private goals ship in a public GitHub release.
"""

from __future__ import annotations

import pytest

from server import _handle_goal_list

from supabase_stubs import FakeClient

GOALS = [
    {
        "slug": "jarvis-m67",
        "title": "Weekly releases",
        "project": "jarvis",
        "status": "active",
        "priority": "high",
    },
    {
        "slug": "redrobot-calib",
        "title": "Arm calibration pass",
        "project": "redrobot",
        "status": "active",
        "priority": "medium",
    },
    {
        "slug": "personal-fitness",
        "title": "Run a 10k",
        "project": None,
        "status": "active",
        "priority": "medium",
    },
]


def _goals_handler(call):
    rows = GOALS
    for op, col, val in call["filters"]:
        if op == "eq":
            rows = [g for g in rows if g.get(col) == val]
        elif op == "is":
            rows = [g for g in rows if (g.get(col) is None) == (val == "null")]
        elif op == "not_is":
            rows = [g for g in rows if (g.get(col) is None) != (val == "null")]
    return rows


def _client():
    client = FakeClient()
    client.table_handlers["goals"] = _goals_handler
    return client


@pytest.mark.asyncio
async def test_unscoped_goal_list_excludes_cross_project_goals(monkeypatch):
    monkeypatch.setattr("server._get_client", _client)

    result = await _handle_goal_list({})

    text = result[0].text
    assert "jarvis-m67" in text
    assert "redrobot-calib" in text
    assert "personal-fitness" not in text
    assert "Run a 10k" not in text


@pytest.mark.asyncio
async def test_project_scoped_goal_list_still_filters_by_project(monkeypatch):
    monkeypatch.setattr("server._get_client", _client)

    result = await _handle_goal_list({"project": "jarvis"})

    text = result[0].text
    assert "jarvis-m67" in text
    assert "redrobot-calib" not in text
    assert "personal-fitness" not in text

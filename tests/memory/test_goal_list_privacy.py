"""#1662 review — goal_list must NOT filter project=NULL rows out of an
unscoped call.

A prior revision of this PR added an ``else`` branch that excluded
cross-project (personal) goals from any unscoped ``goal_list`` call, on the
premise that ``/weekly-release`` calls it unscoped when building a release's
goal section. That premise was wrong: ``/weekly-release`` always passes an
explicit ``project=<repo-slug>`` (see ``weekly-release/SKILL.md`` Step 3),
so it never hits the unscoped branch at all. Meanwhile ``/goals``,
``/goals review`` and ``/end`` all call ``goal_list(status="active")`` with
no ``project`` arg and expect personal (cross-project) goals to appear —
``_format_goal`` even renders ``project or 'cross-project'`` for them. The
fix belongs (if ever needed) in ``/weekly-release``'s own explicit scoping,
never in the shared handler's default for every caller.
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
async def test_unscoped_goal_list_includes_cross_project_goals(monkeypatch):
    monkeypatch.setattr("server._get_client", _client)

    result = await _handle_goal_list({})

    text = result[0].text
    assert "jarvis-m67" in text
    assert "redrobot-calib" in text
    assert "personal-fitness" in text
    assert "Run a 10k" in text


@pytest.mark.asyncio
async def test_project_scoped_goal_list_still_filters_by_project(monkeypatch):
    monkeypatch.setattr("server._get_client", _client)

    result = await _handle_goal_list({"project": "jarvis"})

    text = result[0].text
    assert "jarvis-m67" in text
    assert "redrobot-calib" not in text
    assert "personal-fitness" not in text

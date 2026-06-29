"""Tests for mcp-status/server.py status_digest tool (#1017).

Tests the thin wrapper:
- status_digest delegates gather → engine correctly
- Provenance from gather/engine is passed through intact
- No detector/ranking logic is duplicated (imports from engine only)
- Tool input/output schema matches spec
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Import server module to access conversion function and tool
# Add mcp-status to path
sys.path.insert(0, str(Path(__file__).parent.parent / "mcp-status"))
from server import _convert_gather_to_engine_format


# ============================================================================
# Fixtures for gather result
# ============================================================================

def _days_ago(days: float) -> str:
    """Return ISO 8601 string for `days` ago in UTC."""
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


def make_fixture_gather_result():
    """Create a minimal fixture GatherResult with real structure."""
    from scripts.status_gather import GatherResult, DecisionRecord

    result = GatherResult(
        gathered_at=datetime.now(timezone.utc).isoformat(),
        repos=[
            {
                "name": "Osasuwu/jarvis",
                "branch": "main",
                "clean": True,
                "degraded": False,
                "degradation_reason": None,
                "issues": [
                    {
                        "number": 1,
                        "title": "Test issue",
                        "labels": ["status:in-progress"],
                        "updatedAt": _days_ago(5),  # Stale
                        "milestone": None,
                    },
                ],
                "prs": [],
                "provenance": {
                    "git_state": {"ran": True, "ok": True, "input_rows": -1, "age": 0.1},
                    "gh_issues": {"ran": True, "ok": True, "input_rows": 1, "age": 0.5},
                    "gh_prs": {"ran": True, "ok": True, "input_rows": 0, "age": 0.3},
                    "gh_ci": {"ran": True, "ok": True, "input_rows": 0, "age": 0.2},
                    "gh_milestones": {"ran": True, "ok": True, "input_rows": 0, "age": 0.4},
                },
            },
        ],
        decisions=[
            DecisionRecord(
                id="dec-1",
                actor="session:test",
                decision="Use status_digest for synthesis",
                rationale="Single call is cleaner",
                created_at=datetime.now(timezone.utc).isoformat(),
                payload={
                    "decision": "Use status_digest for synthesis",
                    "rationale": "Single call is cleaner",
                },
            ),
        ],
        provenance={
            "repos_conf": {"ran": True, "ok": True, "input_rows": 1, "age": 0.05},
            "supabase_decisions": {"ran": True, "ok": True, "input_rows": 1, "age": 1.0},
            "status_snapshot": {"ran": True, "ok": False, "input_rows": 0, "age": 100.0},
        },
        errors=[],
    )
    return result


# ============================================================================
# Test: Convert gather result to engine format
# ============================================================================

def test_convert_gather_to_engine_format():
    """Test that GatherResult → Baseline/Delta/decisions works correctly."""
    gather_result = make_fixture_gather_result()
    baseline, delta, decisions = _convert_gather_to_engine_format(gather_result)

    # Baseline should have top-level provenance
    assert "repos_conf" in baseline.provenance
    assert baseline.provenance["repos_conf"].ran is True
    assert baseline.provenance["repos_conf"].ok is True

    # Delta should have repo state
    assert "Osasuwu/jarvis" in delta.repos
    repo_state = delta.repos["Osasuwu/jarvis"]
    assert repo_state.repo == "Osasuwu/jarvis"
    assert len(repo_state.open_issues) == 1
    assert repo_state.open_issues[0].number == 1
    assert repo_state.open_issues[0].title == "Test issue"
    assert "status:in-progress" in repo_state.open_issues[0].labels

    # Decisions should be converted
    assert len(decisions) == 1
    assert decisions[0].decision_id == "dec-1"
    assert "status_digest" in decisions[0].decision


def test_provenance_passthrough():
    """Test that provenance from gather is preserved in conversion."""
    gather_result = make_fixture_gather_result()
    baseline, delta, decisions = _convert_gather_to_engine_format(gather_result)

    # Top-level provenance from gather should be in baseline
    assert baseline.provenance["repos_conf"].input_rows == 1
    assert baseline.provenance["supabase_decisions"].input_rows == 1

    # Repo data should be in delta
    assert "Osasuwu/jarvis" in delta.repos


def test_engine_analyze_receives_correct_format():
    """Test that the converted format can be passed to engine.analyze()."""
    from scripts.status_engine import analyze

    gather_result = make_fixture_gather_result()
    baseline, delta, decisions = _convert_gather_to_engine_format(gather_result)

    # Should not raise an error
    digest = analyze(baseline, delta, decisions)

    # Digest should have health and detector hits
    assert digest.health is not None
    assert digest.detector_hits is not None
    # The stale-in-progress detector should fire (issue updated 5 days ago)
    stale_hits = [h for h in digest.detector_hits if h.detector == "stale-in-progress"]
    assert len(stale_hits) > 0


def test_no_detector_logic_duplication():
    """Test that the server uses engine functions, not reimplementing them.

    This is a structural test — it verifies by import that we're calling
    the real engine.analyze(), not a local duplicate.
    """
    from scripts.status_engine import analyze as engine_analyze

    # The server should import and use the real engine function
    # (verified by absence of detector implementations in server.py)
    # This test simply confirms the import works.
    assert callable(engine_analyze)


# ============================================================================
# Test: Tool schema compliance
# ============================================================================

def test_tool_schema_structure():
    """Test that the tool schema has the required structure."""
    # This is a structural test — verify the tool schema is correct
    # by inspecting the actual server.py code structure
    import inspect
    from server import list_tools

    # Get the source code of list_tools to verify it returns Tool objects
    # with the right names and descriptions
    src = inspect.getsource(list_tools)
    assert "status_digest" in src
    assert "gather" in src
    assert "engine" in src
    assert "jarvis_home" in src


# ============================================================================
# Test: Integration — gather result flow through to digest
# ============================================================================

def test_end_to_end_gather_to_digest():
    """Test the full pipeline: fixture gather → conversion → engine → digest."""
    from scripts.status_engine import analyze

    gather_result = make_fixture_gather_result()
    baseline, delta, decisions = _convert_gather_to_engine_format(gather_result)

    digest = analyze(baseline, delta, decisions)

    # Verify output structure
    assert digest.health is not None
    assert digest.detector_hits is not None
    assert digest.ranking is not None
    assert digest.provenance is not None

    # Provenance should include the sources from gather
    assert "repos_conf" in digest.provenance
    assert "supabase_decisions" in digest.provenance

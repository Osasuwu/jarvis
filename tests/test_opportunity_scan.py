"""Unit tests for jarvis.opportunity_scan.

Tests cover deterministic logic only — signal collection, staleness filtering,
report generation, and the LLM analysis path (mocked). No gh CLI calls are made.
"""
from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from jarvis.opportunity_scan import (
    MAX_OPPORTUNITIES,
    STALE_ISSUE_DAYS,
    STALE_PR_DAYS,
    Opportunity,
    OpportunityScanResult,
    RepoSignals,
    _analyze_with_llm,
    _days_ago,
    _impact_rank,
    _load_repos,
    _parse_json,
    _signals_to_text,
    _write_report,
)


# ── Helpers ───────────────────────────────────────────────────────────────────


def _iso(days_ago: float) -> str:
    """Return ISO timestamp for N days ago."""
    dt = datetime.now(UTC) - timedelta(days=days_ago)
    return dt.isoformat()


def _make_config(per_query: float = 0.50, per_day: float = 5.0):
    cfg = MagicMock()
    cfg.budget.per_query_usd = per_query
    cfg.budget.per_day_usd = per_day
    return cfg


# ── _days_ago ─────────────────────────────────────────────────────────────────


class TestDaysAgo:
    def test_recent_timestamp_is_near_zero(self):
        ts = _iso(0.01)
        assert _days_ago(ts) < 0.1

    def test_old_timestamp(self):
        ts = _iso(20)
        assert 19.5 < _days_ago(ts) < 20.5

    def test_invalid_returns_zero(self):
        assert _days_ago("not-a-date") == 0.0

    def test_empty_returns_zero(self):
        assert _days_ago("") == 0.0

    def test_z_suffix_parsed(self):
        ts = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        assert _days_ago(ts) < 0.01


# ── _parse_json ───────────────────────────────────────────────────────────────


class TestParseJson:
    def test_valid_array(self):
        result = _parse_json('[{"a": 1}]')
        assert result == [{"a": 1}]

    def test_empty_string(self):
        assert _parse_json("") == []

    def test_invalid_json(self):
        assert _parse_json("not json") == []

    def test_non_array_returns_empty(self):
        assert _parse_json('{"a": 1}') == []


# ── _load_repos ───────────────────────────────────────────────────────────────


class TestLoadRepos:
    def test_missing_file_returns_empty(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "jarvis.opportunity_scan.REPOS_CONF",
            tmp_path / "nonexistent.conf",
        )
        assert _load_repos() == []

    def test_parses_repos_ignoring_comments(self, tmp_path, monkeypatch):
        conf = tmp_path / "repos.conf"
        conf.write_text("# comment\nowner/repo1\n\nowner/repo2\n", encoding="utf-8")
        monkeypatch.setattr("jarvis.opportunity_scan.REPOS_CONF", conf)
        assert _load_repos() == ["owner/repo1", "owner/repo2"]

    def test_skips_lines_without_slash(self, tmp_path, monkeypatch):
        conf = tmp_path / "repos.conf"
        conf.write_text("noslash\nowner/valid\n", encoding="utf-8")
        monkeypatch.setattr("jarvis.opportunity_scan.REPOS_CONF", conf)
        assert _load_repos() == ["owner/valid"]


# ── _impact_rank ──────────────────────────────────────────────────────────────


class TestImpactRank:
    def test_high_impact_ranks_higher_than_low(self):
        high = Opportunity("t", "c", "r", "rat", "low", "high", 0.9)
        low = Opportunity("t", "c", "r", "rat", "low", "low", 0.9)
        assert _impact_rank(high) > _impact_rank(low)

    def test_confidence_affects_rank(self):
        opp_high_conf = Opportunity("t", "c", "r", "rat", "low", "high", 0.9)
        opp_low_conf = Opportunity("t", "c", "r", "rat", "low", "high", 0.3)
        assert _impact_rank(opp_high_conf) > _impact_rank(opp_low_conf)

    def test_unknown_impact_defaults_to_medium(self):
        opp = Opportunity("t", "c", "r", "rat", "low", "unknown", 1.0)
        medium = Opportunity("t", "c", "r", "rat", "low", "medium", 1.0)
        assert _impact_rank(opp) == _impact_rank(medium)


# ── _signals_to_text ──────────────────────────────────────────────────────────


class TestSignalsToText:
    def test_includes_repo_name(self):
        s = RepoSignals(repo="owner/myrepo")
        text = _signals_to_text([s])
        assert "owner/myrepo" in text

    def test_shows_stale_issue_count(self):
        s = RepoSignals(
            repo="r/r",
            stale_issues=[{"number": 1, "title": "Old issue", "days_stale": 20}],
        )
        text = _signals_to_text([s])
        assert "Stale issues" in text
        assert "1" in text

    def test_shows_ci_failure_rate_when_sampled(self):
        s = RepoSignals(repo="r/r", ci_failure_rate=0.4, ci_runs_sampled=10)
        text = _signals_to_text([s])
        assert "40%" in text

    def test_shows_fetch_errors(self):
        s = RepoSignals(repo="r/r", fetch_errors=["ci: timeout"])
        text = _signals_to_text([s])
        assert "ci: timeout" in text

    def test_multiple_repos(self):
        s1 = RepoSignals(repo="a/a")
        s2 = RepoSignals(repo="b/b")
        text = _signals_to_text([s1, s2])
        assert "a/a" in text
        assert "b/b" in text


# ── _write_report ─────────────────────────────────────────────────────────────


class TestWriteReport:
    def test_creates_file(self, tmp_path, monkeypatch):
        monkeypatch.setattr("jarvis.opportunity_scan.REPORTS_DIR", tmp_path)
        opp = Opportunity("Fix stale PRs", "stale-work", "o/r", "blocking", "low", "high", 0.9)
        text, path = _write_report([opp], [RepoSignals(repo="o/r")], "2026-03-28T12:00:00")
        assert path.exists()

    def test_report_contains_opportunity_title(self, tmp_path, monkeypatch):
        monkeypatch.setattr("jarvis.opportunity_scan.REPORTS_DIR", tmp_path)
        opp = Opportunity("Fix stale PRs", "stale-work", "o/r", "blocking", "low", "high", 0.9)
        text, _ = _write_report([opp], [RepoSignals(repo="o/r")], "2026-03-28T12:00:00")
        assert "Fix stale PRs" in text

    def test_no_opportunities_message(self, tmp_path, monkeypatch):
        monkeypatch.setattr("jarvis.opportunity_scan.REPORTS_DIR", tmp_path)
        text, _ = _write_report([], [RepoSignals(repo="o/r")], "2026-03-28T12:00:00")
        assert "No significant" in text

    def test_timestamp_in_filename(self, tmp_path, monkeypatch):
        monkeypatch.setattr("jarvis.opportunity_scan.REPORTS_DIR", tmp_path)
        _, path = _write_report([], [], "2026-03-28T12:00:00")
        assert "opportunity-scan" in path.name
        assert "2026" in path.name


# ── _analyze_with_llm ────────────────────────────────────────────────────────


class TestAnalyzeWithLlm:
    def test_returns_opportunities_on_success(self):
        mock_result = MagicMock()
        mock_result.success = True
        mock_result.text = json.dumps([{
            "title": "Address stale PRs",
            "category": "stale-work",
            "repo": "owner/repo",
            "rationale": "3 PRs stale >5 days",
            "effort": "low",
            "impact": "high",
            "confidence": 0.90,
        }])

        with patch("jarvis.executor.execute_query", new=AsyncMock(return_value=mock_result)):
            result = asyncio.run(_analyze_with_llm([RepoSignals(repo="owner/repo")], _make_config()))

        assert len(result) == 1
        assert result[0].title == "Address stale PRs"
        assert result[0].impact == "high"

    def test_strips_markdown_fences(self):
        mock_result = MagicMock()
        mock_result.success = True
        mock_result.text = "```json\n[]\n```"

        with patch("jarvis.executor.execute_query", new=AsyncMock(return_value=mock_result)):
            result = asyncio.run(_analyze_with_llm([], _make_config()))

        assert result == []

    def test_returns_empty_on_llm_failure(self):
        mock_result = MagicMock()
        mock_result.success = False
        mock_result.text = "error"

        with patch("jarvis.executor.execute_query", new=AsyncMock(return_value=mock_result)):
            result = asyncio.run(_analyze_with_llm([], _make_config()))

        assert result == []

    def test_returns_empty_on_unparseable_json(self):
        mock_result = MagicMock()
        mock_result.success = True
        mock_result.text = "not json at all"

        with patch("jarvis.executor.execute_query", new=AsyncMock(return_value=mock_result)):
            result = asyncio.run(_analyze_with_llm([], _make_config()))

        assert result == []

    def test_caps_at_max_opportunities(self):
        items = [
            {"title": f"Opp {i}", "category": "stale-work", "repo": "r/r",
             "rationale": "r", "effort": "low", "impact": "high", "confidence": 0.9}
            for i in range(MAX_OPPORTUNITIES + 3)
        ]
        mock_result = MagicMock()
        mock_result.success = True
        mock_result.text = json.dumps(items)

        with patch("jarvis.executor.execute_query", new=AsyncMock(return_value=mock_result)):
            result = asyncio.run(_analyze_with_llm([], _make_config()))

        assert len(result) <= MAX_OPPORTUNITIES

    def test_skips_malformed_items(self):
        items = [
            {"title": "Good", "category": "stale-work", "repo": "r/r",
             "rationale": "r", "effort": "low", "impact": "high", "confidence": 0.8},
            "not a dict",
            {"confidence": "not-a-float"},
        ]
        mock_result = MagicMock()
        mock_result.success = True
        mock_result.text = json.dumps(items)

        with patch("jarvis.executor.execute_query", new=AsyncMock(return_value=mock_result)):
            result = asyncio.run(_analyze_with_llm([], _make_config()))

        assert len(result) == 1
        assert result[0].title == "Good"


# ── intent routing integration ────────────────────────────────────────────────


class TestOpportunityScanIntentRouting:
    def test_keyword_routes_to_opportunity_scan(self):
        from jarvis.intent_router import route_user_input
        result = route_user_input("scan for opportunities")
        assert result.selected_route == "/opportunity-scan"
        assert result.was_routed is True

    def test_russian_keyword_routes(self):
        from jarvis.intent_router import route_user_input
        result = route_user_input("найди возможности")
        assert result.selected_route == "/opportunity-scan"

    def test_what_to_work_on_routes(self):
        from jarvis.intent_router import route_user_input
        result = route_user_input("what should we work on next")
        assert result.selected_route == "/opportunity-scan"

"""Unit tests for jarvis.intent_router — routing edge cases.

Tests cover:
- Explicit slash commands (pass-through)
- Keyword-based routing for each supported skill
- Low-confidence / greeting fallback to chat
- Argument extraction (research topic, delegate issue #)
- Async routing with LLM fallback mocked
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from jarvis.intent_router import (
    HIGH_CONFIDENCE_THRESHOLD,
    LLM_CONFIDENCE_THRESHOLD,
    RoutedInput,
    _classify_plain_text,
    _looks_like_command_intent,
    format_routing_transparency,
    route_user_input,
    route_user_input_async,
)


# ── _classify_plain_text ──────────────────────────────────────────────────────


class TestClassifyPlainText:
    def test_self_review_english(self):
        cmd, conf, _, _ = _classify_plain_text("do a self review")
        assert cmd == "/self-review"
        assert conf >= HIGH_CONFIDENCE_THRESHOLD

    def test_self_review_russian(self):
        cmd, conf, _, _ = _classify_plain_text("проверь себя")
        assert cmd == "/self-review"
        assert conf >= HIGH_CONFIDENCE_THRESHOLD

    def test_self_improve_english(self):
        cmd, conf, _, _ = _classify_plain_text("self-improve please")
        assert cmd == "/self-improve"
        assert conf >= HIGH_CONFIDENCE_THRESHOLD

    def test_self_improve_apply_fixes(self):
        cmd, conf, _, _ = _classify_plain_text("apply fixes from self review")
        assert cmd == "/self-improve"
        assert conf >= HIGH_CONFIDENCE_THRESHOLD

    def test_weekly_report(self):
        cmd, conf, _, _ = _classify_plain_text("give me the weekly report")
        assert cmd == "/weekly-report"
        assert conf >= HIGH_CONFIDENCE_THRESHOLD

    def test_weekly_report_russian(self):
        cmd, conf, _, _ = _classify_plain_text("итоги недели")
        assert cmd == "/weekly-report"
        assert conf >= HIGH_CONFIDENCE_THRESHOLD

    def test_triage(self):
        cmd, conf, _, _ = _classify_plain_text("triage the backlog")
        assert cmd == "/triage"
        assert conf >= HIGH_CONFIDENCE_THRESHOLD

    def test_issue_health(self):
        cmd, conf, _, _ = _classify_plain_text("run issue health check")
        assert cmd == "/issue-health"
        assert conf >= HIGH_CONFIDENCE_THRESHOLD

    def test_research_with_topic(self):
        cmd, conf, _, args = _classify_plain_text("research best Python ORMs")
        assert cmd == "/research"
        assert conf >= HIGH_CONFIDENCE_THRESHOLD
        assert args is not None
        assert "Python ORMs" in args or "best" in args

    def test_research_russian(self):
        cmd, conf, _, _ = _classify_plain_text("поищи документацию по FastAPI")
        assert cmd == "/research"
        assert conf >= HIGH_CONFIDENCE_THRESHOLD

    def test_delegate_with_issue_number(self):
        cmd, conf, _, args = _classify_plain_text("delegate fix issue #42")
        assert cmd == "/delegate"
        assert conf >= HIGH_CONFIDENCE_THRESHOLD
        assert args == "#42"

    def test_delegate_without_issue_number_stays_chat(self):
        # No issue number → can't delegate, fallback to chat
        cmd, conf, _, _ = _classify_plain_text("delegate something")
        assert cmd == "chat"

    def test_plain_chat_fallback(self):
        cmd, conf, _, _ = _classify_plain_text("how are you today?")
        assert cmd == "chat"
        assert conf < HIGH_CONFIDENCE_THRESHOLD

    def test_empty_like_input(self):
        cmd, _, _, _ = _classify_plain_text("  ")
        assert cmd == "chat"


# ── route_user_input (sync) ───────────────────────────────────────────────────


class TestRouteUserInputSync:
    def test_slash_command_passthrough(self):
        result = route_user_input("/triage")
        assert result.selected_route == "/triage"
        assert result.was_routed is False
        assert result.confidence == 1.0
        assert result.resolved_input == "/triage"

    def test_slash_command_with_args(self):
        result = route_user_input("/research some topic")
        assert result.selected_route == "/research"
        assert result.resolved_input == "/research some topic"
        assert result.was_routed is False

    def test_routed_to_triage(self):
        result = route_user_input("triage my issues")
        assert result.selected_route == "/triage"
        assert result.was_routed is True
        assert result.resolved_input == "/triage"

    def test_routed_to_weekly_report(self):
        result = route_user_input("show me the weekly report")
        assert result.selected_route == "/weekly-report"
        assert result.was_routed is True

    def test_routed_to_self_review(self):
        result = route_user_input("run self review on the code")
        assert result.selected_route == "/self-review"
        assert result.was_routed is True

    def test_routed_to_self_improve(self):
        result = route_user_input("улучши себя")
        assert result.selected_route == "/self-improve"
        assert result.was_routed is True

    def test_research_extracts_topic(self):
        result = route_user_input("research GraphQL vs REST")
        assert result.selected_route == "/research"
        assert result.was_routed is True
        # Resolved input should be "/research <topic>"
        assert result.resolved_input.startswith("/research")
        assert "GraphQL" in result.resolved_input or "REST" in result.resolved_input

    def test_delegate_extracts_issue(self):
        result = route_user_input("delegate implement issue #99")
        assert result.selected_route == "/delegate"
        assert result.was_routed is True
        assert "#99" in result.resolved_input

    def test_chat_fallback_greeting(self):
        result = route_user_input("привет")
        assert result.selected_route == "chat"
        assert result.was_routed is False

    def test_chat_fallback_generic_question(self):
        result = route_user_input("what time is it?")
        assert result.selected_route == "chat"
        assert result.was_routed is False

    def test_empty_input(self):
        result = route_user_input("")
        assert result.selected_route == "chat"
        assert result.was_routed is False
        assert result.confidence == 0.0


# ── _looks_like_command_intent ────────────────────────────────────────────────


class TestLooksLikeCommandIntent:
    def test_greeting_is_not_command(self):
        assert _looks_like_command_intent("привет") is False

    def test_single_word_is_not_command(self):
        assert _looks_like_command_intent("hi") is False

    def test_short_greeting_with_name_is_not_command(self):
        assert _looks_like_command_intent("hello jarvis") is False

    def test_action_sentence_is_command(self):
        assert _looks_like_command_intent("check the project status") is True

    def test_yes_no_is_not_command(self):
        assert _looks_like_command_intent("да") is False
        assert _looks_like_command_intent("ok") is False


# ── route_user_input_async ────────────────────────────────────────────────────


class TestRouteUserInputAsync:
    def test_slash_command_returns_sync_result(self):
        result = asyncio.run(route_user_input_async("/triage"))
        assert result.selected_route == "/triage"
        assert result.was_routed is False

    def test_keyword_match_skips_llm(self):
        """Keyword match should not call LLM."""
        with patch("jarvis.intent_router._classify_with_llm") as mock_llm:
            result = asyncio.run(route_user_input_async("run self review"))
        mock_llm.assert_not_called()
        assert result.selected_route == "/self-review"
        assert result.was_routed is True

    def test_greeting_skips_llm(self):
        """Short greeting should not trigger expensive LLM call."""
        with patch("jarvis.intent_router._classify_with_llm") as mock_llm:
            result = asyncio.run(route_user_input_async("hi"))
        mock_llm.assert_not_called()
        assert result.selected_route == "chat"

    def test_llm_called_for_ambiguous_text(self):
        """Ambiguous text that passes _looks_like_command_intent should try LLM."""
        llm_return = ("/triage", 0.85, "triage keywords in context", None, ())
        with patch(
            "jarvis.intent_router._classify_with_llm",
            new=AsyncMock(return_value=llm_return),
        ):
            result = asyncio.run(
                route_user_input_async("проверь статус для redrobot")
            )
        assert result.was_routed is True
        assert result.selected_route == "/triage"
        assert "llm" in result.reason

    def test_llm_low_confidence_falls_back_to_chat(self):
        """LLM result below threshold stays in chat."""
        llm_return = ("/research", 0.50, "maybe research", None, ("/triage",))
        with patch(
            "jarvis.intent_router._classify_with_llm",
            new=AsyncMock(return_value=llm_return),
        ):
            result = asyncio.run(
                route_user_input_async("проверь статус для redrobot")
            )
        assert result.selected_route == "chat"
        assert result.was_routed is False

    def test_llm_failure_falls_back_to_chat(self):
        """If LLM call fails, route stays at chat."""
        llm_return = ("chat", 0.20, "llm classification failed", None, ())
        with patch(
            "jarvis.intent_router._classify_with_llm",
            new=AsyncMock(return_value=llm_return),
        ):
            result = asyncio.run(
                route_user_input_async("something weird and ambiguous here")
            )
        assert result.selected_route == "chat"
        assert result.was_routed is False


# ── format_routing_transparency ───────────────────────────────────────────────


class TestFormatRoutingTransparency:
    def test_chat_direct_format(self):
        route = RoutedInput(
            original_input="hello",
            resolved_input="hello",
            selected_route="chat",
            confidence=0.90,
            reason="no skill keywords",
            was_routed=False,
        )
        line = format_routing_transparency(route)
        assert "chat" in line
        assert "direct" in line
        assert "0.90" in line

    def test_routed_format_shows_intent_routed(self):
        route = RoutedInput(
            original_input="run self review",
            resolved_input="/self-review",
            selected_route="/self-review",
            confidence=0.93,
            reason="matched self-review intent",
            was_routed=True,
        )
        line = format_routing_transparency(route)
        assert "intent-routed" in line
        assert "/self-review" in line
        assert "0.93" in line

    def test_suggestions_included_when_present(self):
        route = RoutedInput(
            original_input="check something",
            resolved_input="check something",
            selected_route="chat",
            confidence=0.45,
            reason="ambiguous",
            was_routed=False,
            suggestions=("/triage", "/self-review"),
        )
        line = format_routing_transparency(route)
        assert "/triage" in line
        assert "/self-review" in line

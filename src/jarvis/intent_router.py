from __future__ import annotations

import json as _json
import re
from dataclasses import dataclass, field


HIGH_CONFIDENCE_THRESHOLD = 0.78
LLM_CONFIDENCE_THRESHOLD = 0.70

AVAILABLE_COMMANDS: dict[str, str] = {
    "/self-review": "Run health checks and code review on Jarvis itself",
    "/self-improve": "Auto-apply low-risk fixes from self-review findings",
    "/triage": "Daily triage across tracked repositories",
    "/weekly-report": "Weekly delivery report",
    "/issue-health": "Deep issue metadata validation",
    "/research": "Source-backed research on a given topic (needs a topic argument)",
    "/delegate": "Delegate issue implementation to coding agent (needs #issue_number)",
}


@dataclass(frozen=True)
class RoutedInput:
    original_input: str
    resolved_input: str
    selected_route: str
    confidence: float
    reason: str
    was_routed: bool
    suggestions: tuple[str, ...] = field(default_factory=tuple)


def _clean(text: str) -> str:
    return " ".join(text.strip().split())


def _first_issue_number(text: str) -> int | None:
    match = re.search(r"#(\d+)", text)
    if not match:
        return None
    return int(match.group(1))


def _contains_any(text: str, words: tuple[str, ...]) -> bool:
    return any(word in text for word in words)


def _classify_plain_text(text: str) -> tuple[str, float, str, str | None]:
    lowered = text.lower()

    self_review_words = (
        "self review",
        "self-review",
        "самопровер",
        "сделай self review",
        "проверь себя",
    )
    if _contains_any(lowered, self_review_words):
        return "/self-review", 0.93, "matched self-review intent", None

    self_improve_words = (
        "self improve",
        "self-improve",
        "самоулучш",
        "улучши себя",
        "apply fixes",
        "fix findings",
    )
    if _contains_any(lowered, self_improve_words):
        return "/self-improve", 0.92, "matched self-improve intent", None

    weekly_words = (
        "weekly report",
        "еженедель",
        "итоги недели",
        "за неделю",
        "week summary",
    )
    if _contains_any(lowered, weekly_words):
        return "/weekly-report", 0.90, "matched weekly-report intent", None

    issue_health_words = (
        "issue health",
        "health check issues",
        "audit issues",
        "аудит issue",
        "проверь метаданные",
        "здоровье issue",
    )
    if _contains_any(lowered, issue_health_words):
        return "/issue-health", 0.90, "matched issue-health intent", None

    triage_words = (
        "triage",
        "триаж",
        "разбери issues",
        "проверь бэклог",
        "проверь доску",
        "continue work on",
        "продолжи работу над",
    )
    if _contains_any(lowered, triage_words):
        return "/triage", 0.83, "matched triage intent", None

    research_words = (
        "research",
        "исследуй",
        "поищи",
        "найди источники",
        "compare",
        "сравни",
    )
    if _contains_any(lowered, research_words):
        return "/research", 0.88, "matched research intent", text

    delegate_words = (
        "delegate",
        "делегир",
        "implement issue",
        "сделай issue",
        "возьми issue",
        "fix issue",
    )
    issue_number = _first_issue_number(lowered)
    if issue_number is not None and _contains_any(lowered, delegate_words):
        return "/delegate", 0.94, "matched delegate intent with issue reference", f"#{issue_number}"

    return "chat", 0.30, "no high-confidence tool intent", None


def route_user_input(user_input: str) -> RoutedInput:
    original = _clean(user_input)
    if not original:
        return RoutedInput(
            original_input=user_input,
            resolved_input=user_input,
            selected_route="chat",
            confidence=0.0,
            reason="empty input",
            was_routed=False,
        )

    if original.startswith("/"):
        command = original.split(maxsplit=1)[0]
        return RoutedInput(
            original_input=original,
            resolved_input=original,
            selected_route=command,
            confidence=1.0,
            reason="explicit slash command",
            was_routed=False,
        )

    route, confidence, reason, args = _classify_plain_text(original)
    if route != "chat" and confidence >= HIGH_CONFIDENCE_THRESHOLD:
        resolved = f"{route} {args}".strip() if args else route
        return RoutedInput(
            original_input=original,
            resolved_input=resolved,
            selected_route=route,
            confidence=confidence,
            reason=reason,
            was_routed=True,
        )

    return RoutedInput(
        original_input=original,
        resolved_input=original,
        selected_route="chat",
        confidence=confidence,
        reason=reason,
        was_routed=False,
    )


def _looks_like_command_intent(text: str) -> bool:
    """Heuristic: does this plain text look like it might be requesting an action?

    Short greetings and acknowledgements are not worth an LLM classification call.
    """
    words = text.split()
    if len(words) < 2:
        return False
    noise = {
        "hi", "hello", "hey", "привет", "хай", "здравствуй",
        "спасибо", "thanks", "ok", "ок", "да", "нет", "yes", "no",
    }
    if words[0].lower().rstrip("!.,") in noise and len(words) < 4:
        return False
    return True


async def _classify_with_llm(text: str) -> tuple[str, float, str, str | None, tuple[str, ...]]:
    """Use Haiku to classify intent when keyword matching fails.

    Returns (command, confidence, reason, args, suggestions).
    """
    from jarvis.executor import execute_query  # noqa: WPS433

    commands_desc = "\n".join(
        f"- {cmd}: {desc}" for cmd, desc in AVAILABLE_COMMANDS.items()
    )

    prompt = (
        "You are Jarvis's intent classifier. Given a user message, determine "
        "which command best matches the user's intent.\n\n"
        f"Available commands:\n{commands_desc}\n"
        "- chat: general conversation, not a specific command\n\n"
        f'User message: "{text}"\n\n'
        "Respond with a single JSON object (no markdown, no extra text):\n"
        '{"command": "/command-name or chat", "confidence": 0.0-1.0, '
        '"reason": "brief explanation", '
        '"args": "arguments like #123 or topic text, or null", '
        '"suggestions": ["list", "of", "possible", "commands if unsure"]}'
    )

    result = await execute_query(prompt, model="haiku", max_budget_usd=0.01)

    if not result.success:
        return "chat", 0.20, "llm classification failed", None, ()

    raw = result.text.strip()
    # Strip markdown fences if present.
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[-1]
    if raw.endswith("```"):
        raw = raw.rsplit("```", 1)[0]
    raw = raw.strip()

    try:
        parsed = _json.loads(raw)
        command = str(parsed.get("command", "chat"))
        confidence = float(parsed.get("confidence", 0.3))
        reason = str(parsed.get("reason", "llm classified"))
        args = parsed.get("args")
        if args is not None:
            args = str(args)
        suggestions = tuple(str(s) for s in parsed.get("suggestions", []))

        # Validate command is known.
        if command != "chat" and command not in AVAILABLE_COMMANDS:
            return "chat", 0.20, f"llm returned unknown command: {command}", None, (command,)

        return command, confidence, reason, args, suggestions
    except (ValueError, _json.JSONDecodeError, TypeError):
        return "chat", 0.20, "llm response unparseable", None, ()


async def route_user_input_async(user_input: str) -> RoutedInput:
    """Route with keyword matching first, LLM fallback for ambiguous plain text.

    Use this instead of route_user_input() when an async context is available.
    """
    # Fast path: keyword matching (free, instant).
    sync_result = route_user_input(user_input)

    # If keywords matched confidently or it's an explicit slash command, done.
    if sync_result.was_routed or sync_result.selected_route != "chat":
        return sync_result

    original = _clean(user_input)

    # Skip LLM for very short or greeting-like messages.
    if not _looks_like_command_intent(original):
        return sync_result

    # LLM fallback for ambiguous plain text.
    command, confidence, reason, args, suggestions = await _classify_with_llm(original)

    if command != "chat" and confidence >= LLM_CONFIDENCE_THRESHOLD:
        resolved = f"{command} {args}".strip() if args else command
        return RoutedInput(
            original_input=original,
            resolved_input=resolved,
            selected_route=command,
            confidence=confidence,
            reason=f"llm: {reason}",
            was_routed=True,
            suggestions=suggestions,
        )

    # LLM wasn't confident either — stay in chat, but pass suggestions.
    return RoutedInput(
        original_input=original,
        resolved_input=original,
        selected_route="chat",
        confidence=confidence,
        reason=f"llm: {reason}" if reason != "llm classification failed" else sync_result.reason,
        was_routed=False,
        suggestions=suggestions,
    )


def format_routing_transparency(route: RoutedInput) -> str:
    mode = "intent-routed" if route.was_routed else "direct"
    line = (
        f"[jarvis] route: {route.selected_route} | confidence: {route.confidence:.2f} "
        f"| mode: {mode} | reason: {route.reason}"
    )
    if route.suggestions:
        line += f" | suggestions: {', '.join(route.suggestions)}"
    return line

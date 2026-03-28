"""Agent registry — thin compatibility layer over jarvis.dispatcher.

All skill/agent configuration now lives in skills/*/SKILL.md frontmatter.
This module provides backwards-compatible re-exports for any code that
still imports from agents.registry.
"""
from __future__ import annotations

from jarvis.dispatcher import SkillSpec as AgentSpec  # noqa: F401
from jarvis.dispatcher import get_skill, CHAT_SPEC


def command_to_agent(user_input: str) -> AgentSpec:
    """Map user input to a SkillSpec (formerly AgentSpec)."""
    command = user_input.split(maxsplit=1)[0] if user_input.startswith("/") else ""
    skill = get_skill(command)
    return skill if skill is not None else CHAT_SPEC


def is_delegation_command(user_input: str) -> bool:
    """Check if this is a /delegate command."""
    text = user_input.strip()
    if not text.startswith("/"):
        return False
    command = text.split(maxsplit=1)[0]
    return command == "/delegate"

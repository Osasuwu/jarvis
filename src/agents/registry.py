from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AgentSpec:
    name: str
    model: str
    allowed_tools: tuple[str, ...]
    max_budget_usd: float = 0.30


# PM skills: read-only, cheap model, only gh CLI + file reading
PM_TRIAGE = AgentSpec(
    name="pm-triage",
    model="haiku",
    allowed_tools=("Bash", "Read", "Glob", "Grep"),
    max_budget_usd=0.10,
)

# Research: needs web access, stronger model
RESEARCH = AgentSpec(
    name="research",
    model="sonnet",
    allowed_tools=("WebSearch", "WebFetch", "Read", "Grep", "Glob", "Bash"),
    max_budget_usd=0.50,
)

# Delegation: brain uses Sonnet for decomposition, coding agent runs separately
DELEGATE = AgentSpec(
    name="delegate",
    model="sonnet",
    allowed_tools=("Read", "Grep", "Glob", "Bash"),
    max_budget_usd=0.20,
)

# General chat: minimal tools, cheap
CHAT = AgentSpec(
    name="chat",
    model="haiku",
    allowed_tools=(),
    max_budget_usd=0.05,
)


def command_to_agent(user_input: str) -> AgentSpec:
    """Map user input to the right agent spec. Parses command from input."""
    command = user_input.split(maxsplit=1)[0] if user_input.startswith("/") else ""
    if command in {"/triage", "/weekly-report", "/issue-health"}:
        return PM_TRIAGE
    if command == "/research":
        return RESEARCH
    if command == "/delegate":
        return DELEGATE
    return CHAT


def is_delegation_command(user_input: str) -> bool:
    """Check if this is a /delegate command (needs special handling)."""
    text = user_input.strip()
    if not text.startswith("/"):
        return False
    command = text.split(maxsplit=1)[0]
    return command == "/delegate"

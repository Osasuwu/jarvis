from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AgentSpec:
    name: str
    model: str
    permissions: tuple[str, ...]


PM_TRIAGE = AgentSpec(
    name="pm-triage",
    model="claude-haiku-4.5",
    permissions=("gh:read", "read", "glob", "grep"),
)

RESEARCH = AgentSpec(
    name="research",
    model="claude-sonnet-4.6",
    permissions=("websearch", "webfetch", "read"),
)


def command_to_agent(command: str) -> AgentSpec:
    if command in {"/triage", "/weekly-report", "/issue-health"}:
        return PM_TRIAGE
    if command.startswith("/research"):
        return RESEARCH
    return RESEARCH

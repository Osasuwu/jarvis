"""Canonical clean-label schema definition + fixture data.

The schema encodes *what labels SHOULD exist* as plain data — not
embedded in planner logic.  Categories: priority, status, area, needs,
tier, special, type.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CleanLabel:
    """A single label in the canonical clean schema."""

    name: str
    color: str
    description: str = ""
    category: str = ""


# ── Canonical clean schema ───────────────────────────────────────────

CLEAN_LABELS: list[CleanLabel] = [
    # ── Priority ──────────────────────────────────────────────────────
    CleanLabel(
        "priority:critical",
        "7B0000",
        "Blocking, must fix now",
        "priority",
    ),
    CleanLabel("priority:high", "d93f0b", "High priority", "priority"),
    CleanLabel(
        "priority:medium", "fbca04", "Medium priority", "priority"
    ),
    CleanLabel("priority:low", "0e8a16", "Low priority", "priority"),
    # ── Status ────────────────────────────────────────────────────────
    CleanLabel("status:ready", "c2e0c6", "Ready to start", "status"),
    CleanLabel(
        "status:in-progress", "fbca04", "Work in progress", "status"
    ),
    CleanLabel("status:review", "d4c5f9", "Under review", "status"),
    CleanLabel("status:blocked", "b60205", "Blocked", "status"),
    CleanLabel(
        "status:children-done",
        "0e8a16",
        "All child issues closed",
        "status",
    ),
    CleanLabel(
        "status:owner-queue",
        "F9A03C",
        "Needs owner manual touch",
        "status",
    ),
    # ── Area ──────────────────────────────────────────────────────────
    CleanLabel(
        "area:quality",
        "bfe5bf",
        "Testing and quality gates",
        "area",
    ),
    CleanLabel(
        "area:docs", "0075ca", "Documentation and planning", "area"
    ),
    CleanLabel(
        "area:skills", "0052cc", "Skill and subagent development", "area"
    ),
    CleanLabel(
        "area:config",
        "1d76db",
        "Config files (SOUL.md, device.json, .mcp.json) and setup",
        "area",
    ),
    CleanLabel(
        "area:infrastructure",
        "f9d0c4",
        "Platform, LLM, hosting, integrations",
        "area",
    ),
    CleanLabel(
        "area:core-agent",
        "ededed",
        "Core agent functionality",
        "area",
    ),
    CleanLabel(
        "area:ci-quality",
        "bfe5bf",
        "CI and quality infrastructure",
        "area",
    ),
    # ── Needs ─────────────────────────────────────────────────────────
    CleanLabel(
        "needs-research", "ededed", "Needs investigation", "needs"
    ),
    CleanLabel(
        "needs-grill",
        "FBCA04",
        "Needs /grill before implementation",
        "needs",
    ),
    CleanLabel(
        "needs-prd", "FBCA04", "Needs PRD before slicing", "needs"
    ),
    # ── Tier ──────────────────────────────────────────────────────────
    CleanLabel(
        "tier:1-auto",
        "0E8A16",
        "Tier 1: auto-dispatch",
        "tier",
    ),
    CleanLabel(
        "tier:2-review",
        "FBCA04",
        "Tier 2: owner review required",
        "tier",
    ),
    CleanLabel(
        "tier:3-human",
        "D93F0B",
        "Tier 3: owner-driven only",
        "tier",
    ),
    # ── Special ───────────────────────────────────────────────────────
    CleanLabel(
        "sandcastle",
        "1d76db",
        "AFK queue: safe for sandcastle agent",
        "special",
    ),
    CleanLabel(
        "unsafe-for-AFK",
        "B60205",
        "Not safe for sandcastle agent",
        "special",
    ),
    # ── Type ──────────────────────────────────────────────────────────
    CleanLabel("task", "0e8a16", "Task: one PR execution item", "type"),
    CleanLabel("epic", "6f42c1", "Epic: groups related tasks", "type"),
    CleanLabel(
        "draft", "C5DEF5", "Rough idea, not ready for triage", "type"
    ),
    CleanLabel("dependencies", "0366d6", "Dependency updates", "type"),
    CleanLabel("github_actions", "000000", "GitHub Actions code", "type"),
    CleanLabel("python", "2b67c6", "Python code", "type"),
]


def clean_label_by_name(name: str) -> CleanLabel | None:
    """Look up a clean label by name."""
    for label in CLEAN_LABELS:
        if label.name == name:
            return label
    return None


def clean_label_names() -> set[str]:
    """Return the set of all canonical clean label names."""
    return {lb.name for lb in CLEAN_LABELS}

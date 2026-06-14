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
        "7b0000",
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
        # Distinct light-amber so it does not collide with priority:medium
        # (fbca04) — same colour across semantic categories is ambiguous.
        "status:in-progress", "fef2c0", "Work in progress", "status"
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
        "f9a03c",
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
        # Distinct pale-green so it does not collide with area:quality
        # (bfe5bf) — the two area labels were visually identical.
        "area:ci-quality",
        "d4e9c8",
        "CI and quality infrastructure",
        "area",
    ),
    # ── Needs ─────────────────────────────────────────────────────────
    # NOTE: the needs-* family uses a dash, not the `category:value` colon
    # convention the other categories follow. This is an intentional
    # exception — these labels already exist on the live repo as
    # needs-research / needs-grill / needs-prd and are referenced throughout
    # CLAUDE.md; renaming to needs:* would break every existing issue's
    # association. The schema mirrors reality; do not "normalize" the dash.
    CleanLabel(
        "needs-research", "ededed", "Needs investigation", "needs"
    ),
    CleanLabel(
        "needs-grill",
        "fbca04",
        "Needs /grill before implementation",
        "needs",
    ),
    CleanLabel(
        "needs-prd", "fbca04", "Needs PRD before slicing", "needs"
    ),
    # ── Tier ──────────────────────────────────────────────────────────
    CleanLabel(
        "tier:1-auto",
        "0e8a16",
        "Tier 1: auto-dispatch",
        "tier",
    ),
    CleanLabel(
        "tier:2-review",
        "fbca04",
        "Tier 2: owner review required",
        "tier",
    ),
    CleanLabel(
        "tier:3-human",
        "d93f0b",
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
        "b60205",
        "Not safe for sandcastle agent",
        "special",
    ),
    # ── Type ──────────────────────────────────────────────────────────
    # NOTE: no "epic" label — CLAUDE.md decision 2a7ae10e: milestone is the
    # only grouping primitive, the term "epic" is not used. Do not re-add.
    CleanLabel("task", "0e8a16", "Task: one PR execution item", "type"),
    CleanLabel(
        "draft", "c5def5", "Rough idea, not ready for triage", "type"
    ),
    CleanLabel("dependencies", "0366d6", "Dependency updates", "type"),
    CleanLabel("github_actions", "000000", "GitHub Actions code", "type"),
    CleanLabel("python", "2b67c6", "Python code", "type"),
]


# Built once at import — O(1) name lookup instead of a linear scan per call.
_CLEAN_BY_NAME: dict[str, CleanLabel] = {lb.name: lb for lb in CLEAN_LABELS}


def clean_label_by_name(name: str) -> CleanLabel | None:
    """Look up a clean label by name (O(1))."""
    return _CLEAN_BY_NAME.get(name)


def clean_label_names() -> set[str]:
    """Return the set of all canonical clean label names."""
    return set(_CLEAN_BY_NAME)

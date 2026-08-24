"""Shared ``## Plan`` section replace helper (#1689).

Reuses :mod:`agents.plan_lock`'s heading/next-heading section-scoping regex
pair so there is exactly one recipe for "find the ``## Plan`` block inside a
full issue body" — :func:`agents.plan_lock.parse_plan` reads that scoped
slice, and :func:`replace_plan_section` here rewrites it, but both locate the
same boundaries the same way.
"""

from __future__ import annotations

from agents.plan_lock import HEADING_RE, NEXT_HEADING_RE, MalformedPlanError


def replace_plan_section(body: str, new_section: str) -> str:
    """Replace the ``## Plan`` section of ``body`` with ``new_section``.

    ``new_section`` is the full replacement content between the heading and
    the next heading (or end of body) — it does **not** include the ``##
    Plan`` heading line itself, matching what :func:`agents.plan_lock.parse_plan`
    scopes out. Text before and after the Plan section (other headings, e.g.
    ``## Acceptance Criteria``, ``## Decisions``) is preserved unchanged.

    If ``body`` has no ``## Plan`` heading, the section is appended at the
    end of ``body`` (a fresh Plan section for an issue that never had one).
    """
    heading_match = HEADING_RE.search(body)
    if not heading_match:
        separator = "" if body.endswith("\n") or not body else "\n"
        return f"{body}{separator}\n## Plan\n{new_section}"

    section_start = heading_match.end()
    next_heading_match = NEXT_HEADING_RE.search(body, section_start)
    section_end = next_heading_match.start() if next_heading_match else len(body)

    return f"{body[: heading_match.start()]}## Plan\n{new_section}{body[section_end:]}"


__all__ = ["replace_plan_section", "MalformedPlanError"]

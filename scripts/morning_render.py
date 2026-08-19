"""Renderer for the `morning` daily-digest capability (#1588).

Pure `render(digest) -> str`: no I/O, no LLM. Block order is fixed —
degradation → "Знать" (compact summary, no actions) → plan → evidence
sections. Modeled on status_render.py's shape, adapted to the Digest schema
(scripts/digest_schema.py) instead of a raw status dict; MCP surface and
skill wiring are separate slices of the same issue.
"""

from __future__ import annotations

import json
import sys

_CUT_LINE_MARKER = "--- cut-line ---"


def _degradation_line(digest: dict) -> str | None:
    """Build the lead line that opens the digest when data quality is impaired.

    Prefers the pre-computed ``digest["degradation"]`` field (set by
    morning_engine.analyze() via an explicit fold_provenance() call) so every
    per-section stamp is represented. Falls back to scanning sections directly
    when the field is absent or empty — this keeps old fixtures and hand-built
    digests working without a schema migration.

    Distinguishes two kinds of not-ok:
    - FAILED (absence_kind != "not_connected"): real degradation; raises the
      degradation level; shown under "⚠ Деградация источников".
    - NOT_CONNECTED (absence_kind == "not_connected"): stable known limitation
      (e.g. learning section blocked by #1338); does NOT raise degradation;
      shown separately under "ℹ Ограничения".
    """
    deg = digest.get("degradation") or {}
    failures = list(deg.get("failures") or [])
    known_limitations = list(deg.get("known_limitations") or [])

    if not deg:
        for section in digest.get("sections", []) or []:
            prov = section.get("provenance", {}) or {}
            if prov.get("ok", False):
                continue
            if prov.get("absence_kind") == "not_connected":
                known_limitations.append(section.get("name", "?"))
            else:
                failures.append(section.get("name", "?"))

    if not failures and not known_limitations:
        return None

    parts = []
    if failures:
        parts.append("⚠ Деградация источников: " + ", ".join(failures))
    if known_limitations:
        parts.append("ℹ Ограничения: " + ", ".join(known_limitations))
    return " | ".join(parts)


def _know_block(digest: dict) -> list[str]:
    plan = digest.get("plan", {}) or {}
    items = plan.get("items", []) or []
    cut_line_after = plan.get("cut_line_after")
    repo_hygiene = next(
        (s for s in digest.get("sections", []) or [] if s.get("name") == "repo_hygiene"), None
    )
    repo_count = len(repo_hygiene.get("items", [])) if repo_hygiene else 0
    escalations = next(
        (s for s in digest.get("sections", []) or [] if s.get("name") == "escalations"), None
    )
    escalation_count = len(escalations.get("items", [])) if escalations else 0

    return [
        "Знать:",
        f"  Эскалации: {escalation_count}",
        f"  Репозиториев: {repo_count}",
        f"  Пунктов плана: {len(items)} (в бюджет дня: {cut_line_after if cut_line_after is not None else 0})",
    ]


def _plan_block(digest: dict) -> list[str]:
    plan = digest.get("plan", {}) or {}
    items = plan.get("items", []) or []
    cut_line_after = plan.get("cut_line_after")

    if not items:
        return ["План: пусто"]

    lines = ["План:"]
    if cut_line_after == 0:
        lines.append(f"  {_CUT_LINE_MARKER}")
    for item in items:
        lines.append(f"  {item['rank']}. [{item['estimate']}] {item['text']}")
        if cut_line_after is not None and item["rank"] == cut_line_after:
            lines.append(f"  {_CUT_LINE_MARKER}")
    return lines


def _render_repo_hygiene(section: dict) -> list[str]:
    items = section.get("items", []) or []
    reason = section.get("reason")

    if not items:
        return [f"Гигиена репозиториев: {reason or 'без проблем'}"]

    problems = [it for it in items if (it.get("open_milestones") or 0) > 0]
    if not problems:
        return ["Гигиена репозиториев: без проблем"]

    lines = ["<details>", "<summary>Гигиена репозиториев</summary>", ""]
    for it in problems:
        lines.append(f"- {it.get('repo')}: {it.get('open_milestones')} открытых вех")
    lines.append("</details>")
    return lines


def _render_goals_milestones_section(section: dict) -> list[str]:
    items = section.get("items", []) or []
    reason = section.get("reason")

    if not items:
        return [f"Цели и вехи: {reason or 'нет данных'}"]

    lines = ["<details>", "<summary>Цели и вехи</summary>", ""]

    for it in items:
        kind = it.get("type")
        flags = it.get("flags") or []

        if kind == "goal":
            pct = it.get("pct")
            pct_str = f" {pct}%" if pct is not None else ""
            flag_str = " ⚠ нет вехи" if "no_milestone" in flags else ""
            lines.append(
                f"- [цель/{it.get('priority', '—')}]{pct_str} {it.get('title', it.get('slug', ''))}{flag_str}"
            )

        elif kind == "open_milestone":
            flag_str = " ⚠ нет слайсов" if "no_slices" in flags else ""
            # External text (title) is rendered as-is — not interpreted
            lines.append(
                f"- [веха] {it.get('repo')} #{it.get('number')}: {it.get('title', '')}"
                f" ({it.get('open_issues', 0)} откр / {it.get('closed_issues', 0)} закр){flag_str}"
            )

        elif kind == "arch_sweep":
            lines.append(
                f"- [арх-свип] {it.get('repo')} #{it.get('number')}: {it.get('title', '')}"
                f" — {it.get('closed_issues', 0)} слайсов, {it.get('age_days', 0)}д назад → /improve-codebase-architecture"
            )

    lines.append("</details>")
    return lines


def _render_generic_section(section: dict) -> list[str]:
    name = section.get("name", "?")
    items = section.get("items", []) or []
    reason = section.get("reason")

    if not items:
        return [f"{name}: {reason or 'нет данных'}"]

    lines = ["<details>", f"<summary>{name} ({len(items)})</summary>", ""]
    for item in items:
        lines.append(f"- {item}")
    lines.append("</details>")
    return lines


def _render_escalations_section(section: dict) -> list[str]:
    items = section.get("items", []) or []
    reason = section.get("reason")

    if not items:
        label = reason if reason else "нет"
        return [f"Эскалации: {label}"]

    lines = ["<details>", f"<summary>Эскалации ({len(items)})</summary>", ""]
    for item in items:
        goal = item.get("goal", "")
        esc_reason = item.get("reason", "")
        lines.append(f"- {goal}" + (f" ({esc_reason})" if esc_reason else ""))
    lines.append("</details>")
    return lines


def _evidence_blocks(digest: dict) -> list[list[str]]:
    blocks = []
    for section in digest.get("sections", []) or []:
        name = section.get("name")
        if name == "repo_hygiene":
            blocks.append(_render_repo_hygiene(section))
        elif name == "goals_and_milestones":
            blocks.append(_render_goals_milestones_section(section))
        elif name == "escalations":
            blocks.append(_render_escalations_section(section))
        else:
            blocks.append(_render_generic_section(section))
    return blocks


def render(digest: dict) -> str:
    """Render a Digest dict (Digest.to_dict()) to text. Pure — no I/O."""
    blocks: list[list[str]] = []

    degradation = _degradation_line(digest)
    if degradation:
        blocks.append([degradation])

    blocks.append(_know_block(digest))
    blocks.append(_plan_block(digest))
    blocks.extend(_evidence_blocks(digest))

    return "\n\n".join("\n".join(block) for block in blocks)


def main(argv: list[str] | None = None) -> int:
    """CLI: read a morning_digest JSON from stdin, print the render.

    Usage: morning_digest (MCP) | python scripts/morning_render.py
    """
    # Cyrillic labels ("Знать:", "План:", ...) are non-cp1251; force UTF-8 so
    # the CLI never crashes on a Windows console (cp1251 default). render()
    # itself returns a plain str.
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):  # pragma: no cover - non-reconfigurable stream
        pass
    raw = sys.stdin.read()
    try:
        digest = json.loads(raw)
    except json.JSONDecodeError as exc:
        sys.stderr.write(f"morning_render: invalid digest JSON on stdin: {exc}\n")
        return 2
    print(render(digest))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

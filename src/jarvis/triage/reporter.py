"""Format triage reports for console and markdown output."""

from __future__ import annotations

from jarvis.triage.models import CheckCategory, Severity, TriageReport


def to_console(report: TriageReport) -> str:
    """Return a Rich-compatible console string."""
    lines: list[str] = []
    lines.append("[bold]Daily Triage Report[/bold]")
    lines.append(f"Open issues: {report.total_open_issues}  |  " f"Blocked: {report.blocked_count}")
    lines.append(f"Errors: {report.error_count}  |  Warnings: {report.warning_count}")
    lines.append("")

    if not report.violations:
        lines.append("[green]No violations found — board is healthy.[/green]")
        return "\n".join(lines)

    # Group by category
    by_cat: dict[CheckCategory, list[object]] = {}
    for v in report.violations:
        by_cat.setdefault(v.category, []).append(v)

    for cat in CheckCategory:
        items = by_cat.get(cat, [])
        if not items:
            continue
        lines.append(f"[bold underline]{cat.value.upper()}[/bold underline]")
        for v in items:  # type: ignore[union-attr]
            icon = "[red]✗[/red]" if v.severity == Severity.ERROR else "[yellow]![/yellow]"
            lines.append(f"  {icon} #{v.issue_number} {v.issue_title}")
            lines.append(f"      {v.message}")
            lines.append(f"      → {v.suggested_action}")
        lines.append("")

    return "\n".join(lines)


def to_markdown(report: TriageReport) -> str:
    """Return a Markdown summary suitable for a GitHub issue comment or file."""
    lines: list[str] = []
    lines.append("# Daily Triage Report")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("|--------|-------|")
    lines.append(f"| Open issues | {report.total_open_issues} |")
    lines.append(f"| Blocked | {report.blocked_count} |")
    lines.append(f"| Errors | {report.error_count} |")
    lines.append(f"| Warnings | {report.warning_count} |")
    lines.append("")

    if not report.violations:
        lines.append("> No violations — board is healthy.")
        return "\n".join(lines)

    by_cat: dict[CheckCategory, list[object]] = {}
    for v in report.violations:
        by_cat.setdefault(v.category, []).append(v)

    for cat in CheckCategory:
        items = by_cat.get(cat, [])
        if not items:
            continue
        lines.append(f"## {cat.value.title()}")
        lines.append("")
        for v in items:  # type: ignore[union-attr]
            sev = "🔴" if v.severity == Severity.ERROR else "🟡"
            lines.append(f"- {sev} **#{v.issue_number}** {v.issue_title}")
            lines.append(f"  - {v.message}")
            lines.append(f"  - **Action:** {v.suggested_action}")
        lines.append("")

    return "\n".join(lines)

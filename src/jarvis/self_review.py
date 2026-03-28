from __future__ import annotations

import json as _json
import subprocess
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
import shutil

from jarvis.config import RuntimeConfig


ROOT_DIR = Path(__file__).resolve().parents[2]
SRC_DIR = ROOT_DIR / "src"
REPORTS_DIR = ROOT_DIR / "reports"
REPOS_CONF = ROOT_DIR / "skills" / "triage" / "repos.conf"


@dataclass(frozen=True)
class Finding:
    severity: str
    title: str
    details: str
    evidence: str


@dataclass(frozen=True)
class SelfReviewResult:
    report_text: str
    report_path: Path
    critical_count: int
    major_count: int
    minor_count: int
    findings: tuple[Finding, ...]


def _run(cmd: list[str], cwd: Path = ROOT_DIR) -> subprocess.CompletedProcess[str]:
    executable = cmd[0] if cmd else ""
    if executable and shutil.which(executable) is None:
        return subprocess.CompletedProcess(
            args=cmd,
            returncode=127,
            stdout="",
            stderr=f"Command not found: {executable}",
        )

    return subprocess.run(
        cmd,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
    )


def _add(finding_list: list[Finding], severity: str, title: str, details: str, evidence: str) -> None:
    finding_list.append(Finding(severity=severity, title=title, details=details, evidence=evidence))


def _check_runtime(findings: list[Finding]) -> None:
    compile_run = _run([sys.executable, "-m", "compileall", "src"])
    if compile_run.returncode != 0:
        _add(
            findings,
            "critical",
            "Runtime compile check failed",
            "Python compileall reported errors in src.",
            (compile_run.stderr.strip() or compile_run.stdout.strip() or "compileall failed")[:300],
        )

    smoke_run = _run([
        sys.executable,
        "-c",
        "import sys; sys.path.insert(0, 'src'); import main",  # noqa: E501
    ])
    if smoke_run.returncode != 0:
        _add(
            findings,
            "critical",
            "Runtime import smoke check failed",
            "Importing entrypoint module raised an error.",
            (smoke_run.stderr.strip() or smoke_run.stdout.strip() or "import failed")[:300],
        )


def _check_budget_and_config(config: RuntimeConfig, findings: list[Finding]) -> None:
    per_query = config.budget.per_query_usd
    per_day = config.budget.per_day_usd

    if per_query <= 0:
        _add(
            findings,
            "critical",
            "Invalid per-query budget",
            "JARVIS_MAX_BUDGET_PER_QUERY must be > 0.",
            f"current={per_query}",
        )

    if per_day <= 0:
        _add(
            findings,
            "critical",
            "Invalid daily budget",
            "JARVIS_MAX_BUDGET_PER_DAY must be > 0.",
            f"current={per_day}",
        )

    if per_query > per_day:
        _add(
            findings,
            "major",
            "Per-query budget exceeds daily budget",
            "Single query budget should not exceed day budget.",
            f"per_query={per_query}, per_day={per_day}",
        )

    known_model_markers = ("haiku", "sonnet", "opus")
    model_values = {
        "default": config.models.default_model,
        "planning": config.models.planning_model,
        "critical": config.models.critical_model,
    }
    for model_key, model_value in model_values.items():
        normalized = model_value.lower().strip()
        if not any(marker in normalized for marker in known_model_markers):
            _add(
                findings,
                "minor",
                "Unknown configured model",
                f"Model '{model_value}' for {model_key} is not in expected set.",
                "expected marker in model name: haiku, sonnet, opus",
            )


def _check_delegation_health(findings: list[Finding]) -> None:
    gh_version = _run(["gh", "--version"])
    if gh_version.returncode != 0:
        _add(
            findings,
            "critical",
            "GitHub CLI is unavailable",
            "Delegation and PM workflows require gh CLI.",
            (gh_version.stderr.strip() or gh_version.stdout.strip() or "gh --version failed")[:300],
        )
    else:
        gh_auth = _run(["gh", "auth", "status"])
        if gh_auth.returncode != 0:
            _add(
                findings,
                "major",
                "GitHub CLI is not authenticated",
                "Delegation cannot fetch issues or create PRs without authentication.",
                (gh_auth.stderr.strip() or gh_auth.stdout.strip() or "gh auth status failed")[:300],
            )

    claude_version = _run(["claude", "--version"])
    if claude_version.returncode != 0:
        _add(
            findings,
            "major",
            "Claude Code CLI is unavailable",
            "Delegation coding phase requires claude CLI.",
            (claude_version.stderr.strip() or claude_version.stdout.strip() or "claude --version failed")[:300],
        )

    if not REPOS_CONF.exists():
        _add(
            findings,
            "major",
            "Default repos configuration is missing",
            "Delegation default repo uses skills/triage/repos.conf.",
            str(REPOS_CONF),
        )
    else:
        repos = [
            line.strip()
            for line in REPOS_CONF.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]
        if not repos:
            _add(
                findings,
                "major",
                "No default repositories configured",
                "Delegation fallback requires at least one repo in repos.conf.",
                str(REPOS_CONF),
            )

    git_status = _run(["git", "status", "--porcelain"])
    if git_status.returncode == 0 and git_status.stdout.strip():
        _add(
            findings,
            "minor",
            "Working tree has uncommitted changes",
            "Consider committing or stashing changes before delegation. This is a development workflow note, not critical.",
            "run: git status --porcelain",
        )


def _check_changed_files_risk(findings: list[Finding]) -> None:
    changed_run = _run(["git", "status", "--porcelain"])
    if changed_run.returncode != 0:
        _add(
            findings,
            "minor",
            "Changed-files risk review skipped",
            "Unable to inspect git status for risk review.",
            (changed_run.stderr.strip() or changed_run.stdout.strip() or "git status failed")[:300],
        )
        return

    lines = [line for line in changed_run.stdout.splitlines() if line.strip()]
    if not lines:
        return

    file_paths = []
    for line in lines:
        # Format: XY <path>
        if len(line) < 4:
            continue
        file_paths.append(line[3:].strip())

    if len(file_paths) >= 20:
        _add(
            findings,
            "major",
            "Large uncommitted change set",
            "Large pending diff increases risk of accidental regressions.",
            f"changed_files={len(file_paths)}",
        )

    risky_prefixes = (
        "src/main.py",
        "src/handlers/",
        "src/jarvis/delegate.py",
        "config/",
        ".github/",
    )
    risky_files = [path for path in file_paths if path.startswith(risky_prefixes)]
    if risky_files:
        preview = ", ".join(risky_files[:5])
        if len(risky_files) > 5:
            preview += f" (+{len(risky_files) - 5} more)"
        _add(
            findings,
            "minor",
            "High-impact files are currently modified",
            "Core entrypoints/process files are changed and should be reviewed carefully.",
            preview,
        )


def _check_tests(findings: list[Finding]) -> None:
    """Run pytest and report results."""
    if shutil.which("pytest") is None:
        # Fall back to python -m pytest
        cmd = [sys.executable, "-m", "pytest", "--tb=short", "-q"]
    else:
        cmd = ["pytest", "--tb=short", "-q"]

    result = _run(cmd, cwd=ROOT_DIR)

    if result.returncode == 5:
        # pytest exit code 5 = no tests collected
        _add(
            findings,
            "major",
            "No tests found",
            "The project has no test suite. Tests are critical for safe self-improvement.",
            "pytest exit code 5: no tests collected",
        )
        return

    if result.returncode != 0:
        output = (result.stdout.strip() or result.stderr.strip() or "pytest failed")[:400]
        _add(
            findings,
            "critical",
            "Test suite has failures",
            "Failing tests must be fixed before self-improvement can run safely.",
            output,
        )
        return

    # Tests passed — no finding needed, but include as evidence in report metadata.


async def _check_code_quality(findings: list[Finding]) -> None:
    """Use LLM (Sonnet) to review source code and find real issues."""
    from jarvis.executor import execute_query  # noqa: WPS433

    source_files = sorted(SRC_DIR.rglob("*.py"))
    if not source_files:
        _add(findings, "minor", "No source files found for code review", "", str(SRC_DIR))
        return

    source_parts: list[str] = []
    total_lines = 0
    for path in source_files:
        relative = path.relative_to(ROOT_DIR)
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        lines = content.count("\n") + 1
        total_lines += lines
        source_parts.append(f"=== {relative} ({lines} lines) ===\n{content}")

    all_source = "\n\n".join(source_parts)

    prompt = (
        "You are a senior Python code reviewer. "
        "Review this codebase and find concrete issues.\n\n"
        "Focus on:\n"
        "- Code duplication (same logic in multiple places)\n"
        "- Missing error handling at system boundaries\n"
        "- Dead code or unused imports\n"
        "- Overly complex functions (>40 lines or deep nesting)\n"
        "- Security issues (command injection, path traversal, unsanitized input)\n"
        "- Architectural problems (tight coupling, circular dependencies)\n"
        "- Logic bugs or race conditions\n\n"
        "Do NOT report:\n"
        "- Style preferences (quote style, trailing commas, line length)\n"
        "- Missing docstrings or type annotations\n"
        "- Minor naming preferences\n\n"
        "For each finding, output a JSON array. Each element:\n"
        '{"severity": "critical|major|minor", "title": "short title", '
        '"details": "what is wrong and why it matters", '
        '"evidence": "file:line_range or brief code snippet"}\n\n'
        "If there are no real issues, return an empty array: []\n\n"
        f"Source code ({len(source_files)} files, ~{total_lines} lines):\n\n"
        f"{all_source}\n\n"
        "Respond with ONLY the JSON array. No markdown fencing, no commentary."
    )

    result = await execute_query(prompt, model="sonnet", max_budget_usd=0.20)

    if not result.success:
        _add(
            findings,
            "minor",
            "LLM code review skipped",
            f"Sonnet code review call failed: {result.error[:150]}",
            "Deterministic checks still ran.",
        )
        return

    # Parse the JSON array from the LLM response.
    raw = result.text.strip()
    # Strip markdown code fences if LLM added them despite instruction.
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[-1]
    if raw.endswith("```"):
        raw = raw.rsplit("```", 1)[0]
    raw = raw.strip()

    try:
        items = _json.loads(raw)
        if not isinstance(items, list):
            raise ValueError("expected JSON array")
    except (ValueError, _json.JSONDecodeError):
        _add(
            findings,
            "minor",
            "LLM code review response unparseable",
            "Could not parse structured findings from Sonnet.",
            raw[:200],
        )
        return

    valid_severities = {"critical", "major", "minor"}
    for item in items:
        if not isinstance(item, dict):
            continue
        severity = str(item.get("severity", "minor")).lower()
        if severity not in valid_severities:
            severity = "minor"
        _add(
            findings,
            severity,
            str(item.get("title", "Unnamed finding"))[:120],
            str(item.get("details", ""))[:300],
            str(item.get("evidence", ""))[:200],
        )


def _render_findings_block(findings: list[Finding], severity: str, emoji: str) -> str:
    selected = [item for item in findings if item.severity == severity]
    if not selected:
        return f"## {severity.title()}\n- {emoji} None"

    lines = [f"## {severity.title()}"]
    for item in selected:
        lines.append(f"- {emoji} **{item.title}**")
        lines.append(f"  - Details: {item.details}")
        lines.append(f"  - Evidence: {item.evidence}")
    return "\n".join(lines)


def _render_report(findings: list[Finding], generated_at: str) -> str:
    critical_count = sum(1 for item in findings if item.severity == "critical")
    major_count = sum(1 for item in findings if item.severity == "major")
    minor_count = sum(1 for item in findings if item.severity == "minor")

    summary = [
        "# Self-Review Report",
        "",
        f"- Generated at (UTC): {generated_at}",
        f"- Critical: {critical_count}",
        f"- Major: {major_count}",
        f"- Minor: {minor_count}",
        "",
        _render_findings_block(findings, "critical", "🔴"),
        "",
        _render_findings_block(findings, "major", "🟠"),
        "",
        _render_findings_block(findings, "minor", "🟡"),
        "",
        "## Next Actions",
        "1. Fix all critical findings first.",
        "2. Resolve major findings before autonomous self-improve runs.",
        "3. Re-run /self-review and compare counts to confirm progress.",
    ]
    return "\n".join(summary)


async def run_self_review(config: RuntimeConfig) -> SelfReviewResult:
    """Run all self-review checks: deterministic ops checks, tests, and LLM code review."""
    findings: list[Finding] = []

    # ── Deterministic checks (fast, free) ──
    _check_runtime(findings)
    _check_budget_and_config(config, findings)
    _check_delegation_health(findings)
    _check_changed_files_risk(findings)
    _check_tests(findings)

    # ── LLM-based code review (async, costs ~$0.05-0.15) ──
    await _check_code_quality(findings)

    now = datetime.now(UTC)
    stamp = now.strftime("%Y%m%d-%H%M%S")
    generated_at = now.strftime("%Y-%m-%d %H:%M:%S")
    report_text = _render_report(findings, generated_at)

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    report_path = REPORTS_DIR / f"self-review-{stamp}.md"
    report_path.write_text(report_text, encoding="utf-8")

    return SelfReviewResult(
        report_text=report_text,
        report_path=report_path,
        critical_count=sum(1 for item in findings if item.severity == "critical"),
        major_count=sum(1 for item in findings if item.severity == "major"),
        minor_count=sum(1 for item in findings if item.severity == "minor"),
        findings=tuple(findings),
    )


async def run_self_review_pipeline(
    config: RuntimeConfig,
    project: str | None = None,
) -> tuple[SelfReviewResult, str]:
    """Full self-review pipeline: memory context → review → memory write.

    Returns (result, memory_summary) so callers only need to format output.
    Eliminates duplication between CLI and Telegram handlers.
    """
    from jarvis.work_memory import (  # noqa: WPS433
        append_work_memory,
        build_self_review_entry,
        get_project_from_git,
        read_recent_memory,
        summarize_memory,
    )

    project_name = project or get_project_from_git()

    # ── Read and summarize prior memory ──
    recent = read_recent_memory("self-review", project=project_name, n=5)
    memory_summary = ""
    if recent:
        memory_summary = await summarize_memory(
            recent,
            question="What recurring issues appeared in past self-reviews?",
        )

    # ── Run the review ──
    result = await run_self_review(config)

    # ── Write memory ──
    blockers = [
        finding.title
        for finding in result.findings
        if finding.severity in {"critical", "major"}
    ]
    append_work_memory(
        build_self_review_entry(
            project=project_name,
            critical_count=result.critical_count,
            major_count=result.major_count,
            minor_count=result.minor_count,
            blockers=blockers,
            report_path=str(result.report_path),
        )
    )

    return result, memory_summary


async def handle(config: RuntimeConfig, args: str) -> "SkillResult":
    """Skill handler entry point — called by dispatcher auto-discovery."""
    from jarvis.dispatcher import SkillResult  # noqa: WPS433

    result, memory_summary = await run_self_review_pipeline(config)

    text = result.report_text
    if memory_summary:
        text = f"**Memory context:** {memory_summary}\n\n{text}"

    return SkillResult(text=text, success=True)

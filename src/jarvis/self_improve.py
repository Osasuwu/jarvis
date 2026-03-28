"""Self-improvement pipeline for Jarvis.

Block D: Reads self-review findings → LLM builds prioritized plan →
         auto-applies low-risk fixes → high-risk needs approval → branch + PR.
Block F: Dry-run mode, quality validation, threshold tuning.

Flow:
1. Load latest self-review result (or run fresh review)
2. Classify each finding by risk (via safety module)
3. LLM builds a prioritized improvement plan with rationale
4. Auto-apply low-risk items only (medium/high need approval)
5. Validate changes (compile check, tests)
6. Branch + commit + PR (or dry-run report)
"""
from __future__ import annotations

import json as _json
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

from jarvis.config import RuntimeConfig
from jarvis.git_utils import ROOT_DIR, run_git, run_gh
from jarvis.safety import (
    RiskAssessment,
    classify_risk,
    validate_patch,
)
from jarvis.self_review import Finding, SelfReviewResult


@dataclass
class ImprovementItem:
    finding: Finding
    risk: RiskAssessment
    plan: str = ""  # LLM-generated fix plan
    applied: bool = False
    skipped_reason: str = ""


@dataclass
class SelfImproveResult:
    success: bool
    message: str
    items: list[ImprovementItem] = field(default_factory=list)
    auto_applied: int = 0
    needs_approval: int = 0
    skipped: int = 0
    branch: str = ""
    pr_url: str = ""
    dry_run: bool = False
    validation_passed: bool = False


def _discard_changes(cwd: Path = ROOT_DIR) -> None:
    """Revert all uncommitted changes in the working tree."""
    try:
        run_git(["checkout", "--", "."], cwd=cwd)
    except RuntimeError:
        pass
    # Also remove untracked files created by the coding agent.
    try:
        run_git(["clean", "-fd", "--", "src"], cwd=cwd)
    except RuntimeError:
        pass


def _get_changed_files(cwd: Path = ROOT_DIR) -> list[str]:
    """Return list of changed file paths.

    Uses git diff/ls-files instead of parsing --porcelain, which breaks for
    renames/copies (e.g., "R  old -> new" produces synthetic paths).
    """
    changed: set[str] = set()

    # Tracked files with unstaged changes
    try:
        unstaged = run_git(["diff", "--name-only"], cwd=cwd)
        if unstaged.strip():
            changed.update(line.strip() for line in unstaged.splitlines() if line.strip())
    except RuntimeError:
        pass

    # Tracked files with staged changes
    try:
        staged = run_git(["diff", "--name-only", "--cached"], cwd=cwd)
        if staged.strip():
            changed.update(line.strip() for line in staged.splitlines() if line.strip())
    except RuntimeError:
        pass

    # Untracked files (e.g., new files not yet added)
    try:
        untracked = run_git(["ls-files", "--others", "--exclude-standard"], cwd=cwd)
        if untracked.strip():
            changed.update(line.strip() for line in untracked.splitlines() if line.strip())
    except RuntimeError:
        pass

    return sorted(changed)


def _classify_findings(findings: tuple[Finding, ...]) -> list[ImprovementItem]:
    """Classify all findings by risk level."""
    items = []
    for f in findings:
        risk = classify_risk(f.severity, f.title, f.details)
        items.append(ImprovementItem(finding=f, risk=risk))
    return items


async def _build_improvement_plan(
    items: list[ImprovementItem],
    memory_summary: str = "",
) -> list[ImprovementItem]:
    """Use LLM to build a prioritized improvement plan with concrete fix instructions."""
    from jarvis.executor import execute_query  # noqa: WPS433

    # Only plan for actionable items (low/medium risk)
    actionable = [it for it in items if it.risk.level in {"low", "medium"}]
    if not actionable:
        return items

    findings_text = "\n".join(
        f"- [{it.finding.severity}] {it.finding.title}: {it.finding.details} "
        f"(risk={it.risk.level}, evidence={it.finding.evidence})"
        for it in actionable
    )

    memory_ctx = ""
    if memory_summary:
        memory_ctx = f"\nPast review patterns: {memory_summary}\n"

    prompt = (
        "You are Jarvis, a self-improving AI agent. "
        "Given these code review findings, create a concrete improvement plan.\n\n"
        "Rules:\n"
        "- Only plan fixes you are confident about\n"
        "- Each fix must be a specific code change, not a vague suggestion\n"
        "- Prioritize: correctness > security > simplicity > performance\n"
        "- Do NOT plan changes to .env, .git/, secrets, or safety.py\n"
        f"{memory_ctx}\n"
        f"Findings:\n{findings_text}\n\n"
        "For each finding, output a JSON array of objects:\n"
        '{"title": "exact finding title", "plan": "concrete step-by-step fix", '
        '"priority": 1-10, "skip_reason": "reason to skip if not fixable"}\n\n'
        "Respond with ONLY the JSON array."
    )

    result = await execute_query(prompt, model="sonnet", max_budget_usd=0.15)
    if not result.success:
        return items

    raw = result.text.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[-1]
    if raw.endswith("```"):
        raw = raw.rsplit("```", 1)[0]
    raw = raw.strip()

    try:
        plans = _json.loads(raw)
        if not isinstance(plans, list):
            return items
    except (ValueError, _json.JSONDecodeError):
        return items

    # Match plans back to actionable items only (high-risk items excluded from planning)
    plan_map = {str(p.get("title", "")).strip(): p for p in plans if isinstance(p, dict)}
    actionable_titles = {it.finding.title for it in actionable}
    for item in items:
        if item.finding.title not in actionable_titles:
            continue
        matched = plan_map.get(item.finding.title)
        if matched:
            skip = str(matched.get("skip_reason", "")).strip()
            if skip:
                item.skipped_reason = skip
            else:
                item.plan = str(matched.get("plan", ""))

    return items


async def _apply_low_risk_fixes(
    items: list[ImprovementItem],
    dry_run: bool = False,
) -> list[ImprovementItem]:
    """Auto-apply low-risk fixes using coding agent. Medium/high are skipped."""
    from jarvis.executor import execute_query  # noqa: WPS433

    low_risk = [it for it in items if it.risk.level == "low" and it.plan and not it.skipped_reason]
    if not low_risk:
        return items

    if dry_run:
        for it in low_risk:
            it.skipped_reason = "dry-run mode — not applied"
        return items

    # Snapshot changed files before coding agent runs
    files_before = set(_get_changed_files())

    # Batch all low-risk fixes into one coding prompt
    fixes_text = "\n\n".join(
        f"### Fix {i+1}: {it.finding.title}\n{it.plan}"
        for i, it in enumerate(low_risk)
    )

    prompt = (
        "You are a coding agent applying specific fixes to a Python codebase.\n"
        "Apply ONLY the fixes described below. Do not make any other changes.\n"
        "Do not modify .env, .git/, secrets, or safety.py.\n"
        "After applying, verify the code compiles (python -m compileall src).\n\n"
        f"Fixes to apply:\n{fixes_text}\n\n"
        "Apply each fix carefully. If a fix cannot be applied safely, skip it."
    )

    result = await execute_query(
        prompt,
        model="sonnet",
        allowed_tools=("Read", "Edit", "Write", "Bash", "Glob", "Grep"),
        max_budget_usd=0.25,
    )

    if not result.success:
        for it in low_risk:
            it.skipped_reason = f"Coding agent failed: {result.error[:100]}"
        return items

    # Verify that files actually changed (fix #1: don't trust SDK success alone)
    files_after = set(_get_changed_files())
    new_changes = files_after - files_before
    if not new_changes:
        for it in low_risk:
            it.skipped_reason = "Coding agent returned success but no files were modified"
        return items

    for it in low_risk:
        it.applied = True

    return items


def _validate_changes() -> tuple[bool, str]:
    """Post-fix validation: compile check + tests.

    Both compile failure and test failure block the pipeline.
    """
    # Compile check
    compile_result = subprocess.run(
        [sys.executable, "-m", "compileall", "src"],
        capture_output=True, text=True, encoding="utf-8",
        errors="replace", cwd=str(ROOT_DIR), timeout=60,
    )
    if compile_result.returncode != 0:
        return False, f"Compile check failed: {compile_result.stderr[:200]}"

    # Run tests — failures block PR to prevent shipping broken code
    test_result = subprocess.run(
        [sys.executable, "-m", "pytest", "--tb=short", "-q"],
        capture_output=True, text=True, encoding="utf-8",
        errors="replace", cwd=str(ROOT_DIR), timeout=120,
    )
    if test_result.returncode == 5:
        return True, "No tests found (compile OK)"
    if test_result.returncode != 0:
        return False, f"Tests failed: {test_result.stdout[:300]}"

    return True, "Compile and tests passed"


async def run_self_improve(
    review_result: SelfReviewResult,
    config: RuntimeConfig,
    *,
    dry_run: bool = False,
    memory_summary: str = "",
    project: str = "",
) -> SelfImproveResult:
    """Full self-improvement pipeline.

    Args:
        review_result: Output from run_self_review.
        config: Runtime config with budget limits.
        dry_run: If True, plan but don't apply or create PR.
        memory_summary: Context from past reviews.
        project: Project name for branch naming.
    """
    if not review_result.findings:
        return SelfImproveResult(
            success=True,
            message="No findings to improve.",
            dry_run=dry_run,
            validation_passed=True,
        )

    # Remember which branch we started on for rollback
    original_branch = run_git(["rev-parse", "--abbrev-ref", "HEAD"])

    # Step 1: Classify findings by risk
    items = _classify_findings(review_result.findings)

    # Step 2: LLM builds improvement plan
    items = await _build_improvement_plan(items, memory_summary)

    # Step 3: Apply low-risk fixes (or dry-run)
    items = await _apply_low_risk_fixes(items, dry_run=dry_run)

    auto_applied = sum(1 for it in items if it.applied)
    needs_approval = sum(
        1 for it in items
        if not it.applied and not it.skipped_reason and it.risk.requires_approval
    )
    skipped = sum(1 for it in items if it.skipped_reason)

    result = SelfImproveResult(
        success=True,
        message="",
        items=items,
        auto_applied=auto_applied,
        needs_approval=needs_approval,
        skipped=skipped,
        dry_run=dry_run,
    )

    # Step 4: Validate (only if changes were applied)
    if auto_applied > 0 and not dry_run:
        valid, reason = _validate_changes()
        result.validation_passed = valid
        if not valid:
            # Fix #3: rollback changes on validation failure
            _discard_changes()
            result.message = f"Validation failed (changes reverted): {reason}"
            result.success = False
            return result

        # Step 5: Check changed files against safety gates
        changed_files = _get_changed_files()
        if changed_files:
            safe, safety_reason = validate_patch(changed_files)
            if not safe:
                # Rollback: forbidden paths were touched
                _discard_changes()
                result.message = f"Safety gate blocked (changes reverted): {safety_reason}"
                result.success = False
                return result

            # Step 6: Branch from main + commit + PR
            try:
                branch = f"self-improve/auto-{review_result.report_path.stem}"

                # Fix #8: delete stale branch if it exists from a previous failed run
                try:
                    run_git(["branch", "-D", branch])
                except RuntimeError:
                    pass  # branch didn't exist, fine

                # Check if there are changes to stash (stash push fails on clean tree)
                has_stash = False
                try:
                    status = run_git(["status", "--porcelain"], cwd=ROOT_DIR)
                    if status.strip():
                        has_stash = True
                        run_git(["stash", "push", "-u", "-m", "self-improve-temp"])
                except RuntimeError:
                    pass

                try:
                    run_git(["checkout", "main"])
                    run_git(["pull", "--ff-only"])
                except RuntimeError:
                    # If main checkout or pull fails, restore and abort
                    try:
                        run_git(["checkout", original_branch])
                    except RuntimeError:
                        pass
                    if has_stash:
                        try:
                            run_git(["stash", "pop"])
                        except RuntimeError:
                            pass
                    raise

                run_git(["checkout", "-b", branch])
                if has_stash:
                    run_git(["stash", "pop"])

                run_git(["add", "-A"])
                commit_msg = (
                    f"fix: auto-apply {auto_applied} low-risk improvements\n\n"
                    "Automated by Jarvis self-improve pipeline.\n"
                    f"Review: {review_result.report_path.name}"
                )
                run_git(["commit", "-m", commit_msg])
                run_git(["push", "-u", "origin", branch])

                applied_lines = "\n".join(
                    f"- [{it.finding.severity}] {it.finding.title}"
                    for it in items if it.applied
                )
                review_lines = "\n".join(
                    f"- [{it.finding.severity}] {it.finding.title} (risk: {it.risk.level})"
                    for it in items if not it.applied and not it.skipped_reason
                )
                pr_body = (
                    f"## Self-Improvement PR\n\n"
                    f"Auto-applied **{auto_applied}** low-risk fixes from self-review.\n\n"
                    f"### Applied fixes\n{applied_lines}"
                    f"\n\n### Needs manual review ({needs_approval})\n{review_lines}"
                    f"\n\nValidation: {'PASSED' if result.validation_passed else 'FAILED'}\n"
                    f"\nGenerated by Jarvis self-improve pipeline"
                )
                pr_url = run_gh([
                    "pr", "create",
                    "--title", f"fix: auto-apply {auto_applied} improvements",
                    "--body", pr_body,
                ])
                result.branch = branch
                result.pr_url = pr_url
            except RuntimeError as exc:
                result.message = f"Branch/PR creation failed: {exc}"
                result.success = False
                return result
            finally:
                # Always return to original branch
                try:
                    run_git(["checkout", original_branch])
                except RuntimeError:
                    pass
    else:
        result.validation_passed = True  # nothing to validate in dry-run

    if not result.message:
        if dry_run:
            result.message = f"Dry run complete: {auto_applied} would be auto-applied, {needs_approval} need approval"
        else:
            result.message = f"Applied {auto_applied} fixes, {needs_approval} need approval"

    return result


async def run_self_improve_pipeline(
    config: RuntimeConfig,
    *,
    dry_run: bool = False,
    project: str | None = None,
) -> SelfImproveResult:
    """End-to-end: self-review → self-improve → memory write.

    Shared entry point for CLI and Telegram.
    """
    from jarvis.self_review import run_self_review_pipeline  # noqa: WPS433
    from jarvis.work_memory import (  # noqa: WPS433
        append_work_memory,
        WorkMemoryEntry,
        get_project_from_git,
    )
    from datetime import UTC, datetime  # noqa: WPS433

    project_name = project or get_project_from_git()

    # Run self-review first
    review_result, memory_summary = await run_self_review_pipeline(config, project=project_name)

    # Run self-improve
    result = await run_self_improve(
        review_result,
        config,
        dry_run=dry_run,
        memory_summary=memory_summary,
        project=project_name,
    )

    # Write memory
    append_work_memory(WorkMemoryEntry(
        timestamp_utc=datetime.now(UTC).isoformat(),
        workflow="self-improve",
        project=project_name,
        objective="Auto-apply low-risk improvements from self-review findings.",
        attempted_actions=(
            "Classify findings by risk.",
            "Build LLM improvement plan.",
            "Apply low-risk fixes via coding agent.",
            "Validate changes (compile + tests).",
            "Create branch and PR.",
        ),
        status="ok" if result.success else "error",
        blockers=tuple([result.message] if not result.success else []),
        next_steps=tuple(
            [f"{result.needs_approval} items need manual approval"]
            if result.needs_approval > 0 else []
        ),
        metadata={
            "auto_applied": result.auto_applied,
            "needs_approval": result.needs_approval,
            "skipped": result.skipped,
            "dry_run": result.dry_run,
            "pr_url": result.pr_url,
        },
    ))

    return result


async def handle(config: RuntimeConfig, args: str) -> "SkillResult":
    """Skill handler entry point — called by dispatcher auto-discovery."""
    from jarvis.dispatcher import SkillResult  # noqa: WPS433

    dry_run = "--dry-run" in args

    result = await run_self_improve_pipeline(config, dry_run=dry_run)

    lines = [result.message]
    if result.pr_url:
        lines.append(f"PR: {result.pr_url}")
    if result.items:
        lines.append(f"\nApplied: {result.auto_applied} | Needs approval: {result.needs_approval} | Skipped: {result.skipped}")
        for it in result.items:
            status = "applied" if it.applied else ("skipped" if it.skipped_reason else "needs-approval")
            lines.append(f"  - [{it.finding.severity}] {it.finding.title} ({status})")

    return SkillResult(text="\n".join(lines), success=result.success)

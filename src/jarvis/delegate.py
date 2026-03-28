"""Delegation pipeline: Jarvis decomposes a task -> coding agent executes -> PR.

Flow:
1. Preflight: check working tree is clean
2. Fetch issue details from GitHub
3. Jarvis brain (cheap model) decomposes into structured coding prompt
4. Create feature branch
5. Hand off to coding agent (Claude Code CLI / Pro subscription)
6. Commit changes + create PR
7. Return PR URL to user
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from agents.coding import CodingResult, get_coding_agent
from jarvis.costs import check_daily_budget, record_execution
from jarvis.executor import execute_query
from jarvis.git_utils import run_git, run_gh


ROOT_DIR = Path(__file__).resolve().parents[2]
REPOS_CONF = ROOT_DIR / "skills" / "triage" / "repos.conf"


@dataclass
class DelegationResult:
    success: bool
    message: str
    pr_url: str = ""
    coding_summary: str = ""
    cost_usd: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0


def _get_default_repo() -> str:
    """Read the first repo from repos.conf as the default."""
    if REPOS_CONF.exists():
        for line in REPOS_CONF.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                return line
    return "Osasuwu/personal-AI-agent"




def _checkout_main_safe(cwd: str | Path = ROOT_DIR) -> None:
    """Checkout main branch, ignoring errors."""
    try:
        run_git(["checkout", "main"], cwd=cwd)
    except RuntimeError:
        pass


def preflight_check(cwd: str | Path = ROOT_DIR) -> None:
    """Ensure working tree is clean before delegation."""
    status = run_git(["status", "--porcelain"], cwd=cwd)
    if status.strip():
        raise RuntimeError(
            "Working tree is not clean. Commit or stash changes before delegating.\n"
            f"Dirty files:\n{status}"
        )


def fetch_issue(repo: str, issue_number: int) -> dict:
    """Fetch issue details from GitHub."""
    raw = run_gh([
        "issue", "view", str(issue_number),
        "--repo", repo,
        "--json", "number,title,body,labels,milestone,assignees,state",
    ])
    return json.loads(raw)


def _sanitize_branch_name(title: str) -> str:
    """Convert issue title to a valid git branch name."""
    name = title.lower()
    name = re.sub(r"[^a-z0-9\s-]", "", name)
    name = re.sub(r"[\s_]+", "-", name).strip("-")
    return name[:50]


async def decompose_issue(issue: dict, repo: str, *, max_budget_usd: float = 0.15) -> tuple[str, float, int, int]:
    """Use Jarvis brain to analyze issue and build a coding prompt.

    Returns (prompt_text, cost_usd, input_tokens, output_tokens).
    """
    issue_text = (
        f"Issue #{issue['number']}: {issue['title']}\n\n"
        f"{issue.get('body', '') or 'No description.'}\n\n"
        f"Labels: {', '.join(l['name'] for l in issue.get('labels', []))}\n"
        f"Milestone: {(issue.get('milestone') or {}).get('title', 'None')}\n"
        f"Repo: {repo}"
    )

    analysis_prompt = (
        "You are Jarvis, a task decomposition agent. Your job is to read a GitHub issue "
        "and produce a clear, actionable coding prompt that another AI agent will execute.\n\n"
        "The coding agent has access to the full repository and can read, edit, and write files, "
        "run bash commands, search code. It does NOT have access to the issue tracker.\n\n"
        f"## Issue\n{issue_text}\n\n"
        "## Your output\n"
        "Write a structured coding prompt with:\n"
        "1. **Objective** — one sentence: what needs to be done\n"
        "2. **Context** — what the coding agent needs to understand about the codebase\n"
        "3. **Steps** — numbered list of concrete coding steps\n"
        "4. **Acceptance criteria** — how to verify the work is complete\n"
        "5. **Constraints** — things to avoid, edge cases to handle\n\n"
        "Be specific. Reference file paths if you know them. "
        "The coding agent is skilled but has no context beyond what you provide.\n"
        "Output ONLY the prompt, no meta-commentary."
    )

    result = await execute_query(
        analysis_prompt,
        model="sonnet",
        allowed_tools=("Read", "Grep", "Glob", "Bash"),
        max_budget_usd=max_budget_usd,
    )

    if not result.success:
        raise RuntimeError(f"Decomposition failed: {result.error}")

    return result.text, result.cost_usd, result.input_tokens, result.output_tokens


def create_branch(issue_number: int, title: str, cwd: str | Path = ROOT_DIR) -> str:
    """Create and checkout a feature branch for the issue."""
    branch_name = f"feature/{issue_number}-{_sanitize_branch_name(title)}"

    run_git(["checkout", "main"], cwd=cwd)
    run_git(["pull", "--ff-only"], cwd=cwd)
    run_git(["checkout", "-b", branch_name], cwd=cwd)

    return branch_name


def commit_and_push(branch: str, issue_number: int, title: str, cwd: str | Path = ROOT_DIR) -> None:
    """Stage all changes, commit, and push."""
    status = run_git(["status", "--porcelain"], cwd=cwd)
    if not status.strip():
        raise RuntimeError("No changes were made by the coding agent.")

    run_git(["add", "-A"], cwd=cwd)
    commit_msg = f"feat: {title} (#{issue_number})\n\nAutomated by Jarvis delegation pipeline."
    run_git(["commit", "-m", commit_msg], cwd=cwd)
    run_git(["push", "-u", "origin", branch], cwd=cwd)


def create_pr(
    repo: str,
    branch: str,
    issue_number: int,
    title: str,
    coding_summary: str,
) -> str:
    """Create a pull request and return its URL."""
    pr_body = (
        f"## Summary\n\n"
        f"Automated implementation for #{issue_number}.\n\n"
        f"## Coding Agent Output\n\n"
        f"{coding_summary[:3000]}\n\n"
        f"## Review Checklist\n\n"
        f"- [ ] Code changes are correct and complete\n"
        f"- [ ] No unnecessary files modified\n"
        f"- [ ] Tests pass (if applicable)\n\n"
        f"Closes #{issue_number}\n\n"
        f"Generated by Jarvis delegation pipeline"
    )

    pr_url = run_gh([
        "pr", "create",
        "--repo", repo,
        "--head", branch,
        "--title", f"feat: {title}",
        "--body", pr_body,
    ])

    return pr_url


def parse_delegate_args(user_input: str) -> tuple[str, int]:
    """Parse '/delegate [repo]#<number>' into (repo, issue_number).

    Formats:
        /delegate #42                    -> (default_repo, 42)
        /delegate Osasuwu/my-repo#42     -> ("Osasuwu/my-repo", 42)
        /delegate 42                     -> (default_repo, 42)
    """
    args = user_input.removeprefix("/delegate").strip()
    if not args:
        raise ValueError("Usage: /delegate [owner/repo]#<issue_number>")

    default_repo = _get_default_repo()

    # Try repo#number format
    match = re.match(r"^([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)#(\d+)$", args)
    if match:
        return match.group(1), int(match.group(2))

    # Try #number format
    match = re.match(r"^#?(\d+)$", args)
    if match:
        return default_repo, int(match.group(1))

    raise ValueError(f"Cannot parse: '{args}'. Use: /delegate [owner/repo]#<number>")


async def delegate_issue(
    repo: str,
    issue_number: int,
    *,
    cwd: str | Path = ROOT_DIR,
    model: str = "sonnet",
    max_budget_usd: float = 0.30,
    session_id: str = "delegate",
    daily_budget_usd: float | None = None,
    per_query_usd: float | None = None,
    use_api_key: bool = False,
    timeout_sec: int = 600,
) -> DelegationResult:
    """Full delegation pipeline: preflight -> issue -> decompose -> branch -> code -> PR."""

    # Step 0: Budget gate for decomposition call
    effective_budget = max_budget_usd
    if daily_budget_usd is not None:
        allowed, remaining = check_daily_budget(daily_budget_usd)
        if not allowed:
            return DelegationResult(
                success=False,
                message=f"Daily budget exhausted (${daily_budget_usd:.2f} limit).",
            )
        effective_budget = min(effective_budget, remaining)

    if per_query_usd is not None:
        effective_budget = min(effective_budget, per_query_usd)

    if effective_budget <= 0:
        return DelegationResult(
            success=False,
            message="No budget available for delegation decomposition step.",
        )

    # Step 1: Preflight — working tree must be clean
    try:
        preflight_check(cwd=cwd)
    except RuntimeError as exc:
        return DelegationResult(success=False, message=str(exc))

    # Step 2: Fetch issue
    try:
        issue = fetch_issue(repo, issue_number)
    except RuntimeError as exc:
        return DelegationResult(success=False, message=f"Failed to fetch issue: {exc}")

    if issue.get("state") != "OPEN":
        return DelegationResult(success=False, message=f"Issue #{issue_number} is not open.")

    title = issue["title"]

    # Step 3: Decompose (Jarvis brain, API cost tracked)
    try:
        coding_prompt, cost, in_tok, out_tok = await decompose_issue(
            issue, repo, max_budget_usd=effective_budget
        )
    except RuntimeError as exc:
        return DelegationResult(success=False, message=f"Decomposition failed: {exc}")

    # Record decomposition cost
    if cost > 0 or in_tok > 0:
        record_execution(
            model="sonnet",
            input_tokens=in_tok,
            output_tokens=out_tok,
            cost_usd=cost,
            session_id=session_id,
        )

    # Step 4: Create branch
    try:
        branch = create_branch(issue_number, title, cwd=cwd)
    except RuntimeError as exc:
        return DelegationResult(
            success=False,
            message=f"Branch creation failed: {exc}",
            cost_usd=cost, input_tokens=in_tok, output_tokens=out_tok,
        )

    # Step 5: Execute coding agent (Pro subscription, no API cost)
    agent = get_coding_agent(use_api_key=use_api_key)

    full_prompt = (
        f"You are implementing a change for issue #{issue_number}: {title}\n"
        f"You are on branch '{branch}'. Make all necessary changes.\n"
        f"After making changes, verify they work (run tests if applicable).\n"
        f"Do NOT commit or push — that will be handled externally.\n\n"
        f"{coding_prompt}"
    )

    coding_result: CodingResult = agent.execute(
        full_prompt,
        cwd=cwd,
        model=model,
        timeout_sec=timeout_sec,
    )

    if not coding_result.success:
        _checkout_main_safe(cwd)
        try:
            run_git(["branch", "-D", branch], cwd=cwd)
        except RuntimeError:
            pass
        return DelegationResult(
            success=False,
            message=f"Coding agent failed: {coding_result.error}",
            cost_usd=cost, input_tokens=in_tok, output_tokens=out_tok,
        )

    # Step 6: Commit and push
    try:
        commit_and_push(branch, issue_number, title, cwd=cwd)
    except RuntimeError as exc:
        _checkout_main_safe(cwd)
        return DelegationResult(
            success=False,
            message=f"Commit/push failed: {exc}. Branch '{branch}' may still exist locally.",
            coding_summary=coding_result.summary,
            cost_usd=cost, input_tokens=in_tok, output_tokens=out_tok,
        )

    # Step 7: Create PR
    try:
        pr_url = create_pr(repo, branch, issue_number, title, coding_result.summary)
    except RuntimeError as exc:
        _checkout_main_safe(cwd)
        return DelegationResult(
            success=False,
            message=f"PR creation failed (changes pushed to branch '{branch}'): {exc}",
            coding_summary=coding_result.summary,
            cost_usd=cost, input_tokens=in_tok, output_tokens=out_tok,
        )

    _checkout_main_safe(cwd)

    return DelegationResult(
        success=True,
        message=f"PR created: {pr_url}",
        pr_url=pr_url,
        coding_summary=coding_result.summary,
        cost_usd=cost, input_tokens=in_tok, output_tokens=out_tok,
    )


async def handle(config: "RuntimeConfig", args: str) -> "SkillResult":
    """Skill handler entry point — called by dispatcher auto-discovery."""
    from uuid import uuid4  # noqa: WPS433
    from jarvis.dispatcher import SkillResult  # noqa: WPS433

    try:
        repo, issue_number = parse_delegate_args(f"/delegate {args}")
    except ValueError as exc:
        return SkillResult(text=str(exc), success=False)

    result = await delegate_issue(
        repo,
        issue_number,
        max_budget_usd=config.budget.per_query_usd,
        session_id=f"delegate-{uuid4().hex[:10]}",
        daily_budget_usd=config.budget.per_day_usd,
        per_query_usd=config.budget.per_query_usd,
    )

    text = result.message
    if result.coding_summary:
        text += f"\n\n--- Coding Agent Summary ---\n{result.coding_summary[:1000]}"

    return SkillResult(
        text=text,
        success=result.success,
        cost_usd=result.cost_usd,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
    )

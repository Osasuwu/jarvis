"""Delegation pipeline: Jarvis decomposes a task → coding agent executes → PR.

Flow:
1. Fetch issue details from GitHub
2. Jarvis brain (cheap model) analyzes issue and builds a structured coding prompt
3. Create a feature branch
4. Hand off to coding agent (Claude Code CLI / Pro subscription)
5. Commit changes + create PR
6. Return PR URL to user
"""
from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

DEFAULT_REPO = "Osasuwu/personal-AI-agent"

from agents.coding import CodingResult, get_coding_agent
from jarvis.executor import execute_query


ROOT_DIR = Path(__file__).resolve().parents[2]


@dataclass
class DelegationResult:
    success: bool
    message: str
    pr_url: str = ""
    coding_summary: str = ""


def _run_gh(args: list[str], cwd: str | Path = ROOT_DIR) -> str:
    """Run a gh CLI command and return stdout."""
    result = subprocess.run(
        ["gh", *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=str(cwd),
        timeout=30,
    )
    if result.returncode != 0:
        raise RuntimeError(f"gh {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout.strip()


def _run_git(args: list[str], cwd: str | Path = ROOT_DIR) -> str:
    """Run a git command and return stdout."""
    result = subprocess.run(
        ["git", *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=str(cwd),
        timeout=30,
    )
    if result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout.strip()


def fetch_issue(repo: str, issue_number: int) -> dict:
    """Fetch issue details from GitHub."""
    raw = _run_gh([
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


async def decompose_issue(issue: dict, repo: str) -> str:
    """Use Jarvis brain (cheap model) to analyze the issue and build a coding prompt.

    This is the 'coordinator' step — Haiku/Sonnet reads the issue and produces
    a clear, structured prompt for the coding agent.
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
        allowed_tools=["Read", "Grep", "Glob", "Bash"],
        max_budget_usd=0.15,
    )

    if not result.success:
        raise RuntimeError(f"Decomposition failed: {result.error}")

    return result.text


def create_branch(issue_number: int, title: str, cwd: str | Path = ROOT_DIR) -> str:
    """Create and checkout a feature branch for the issue."""
    branch_name = f"feature/{issue_number}-{_sanitize_branch_name(title)}"

    # Ensure we're on main and up to date
    _run_git(["checkout", "main"], cwd=cwd)
    _run_git(["pull", "--ff-only"], cwd=cwd)
    _run_git(["checkout", "-b", branch_name], cwd=cwd)

    return branch_name


def commit_and_push(branch: str, issue_number: int, title: str, cwd: str | Path = ROOT_DIR) -> None:
    """Stage all changes, commit, and push."""
    # Check if there are changes
    status = _run_git(["status", "--porcelain"], cwd=cwd)
    if not status.strip():
        raise RuntimeError("No changes were made by the coding agent.")

    _run_git(["add", "-A"], cwd=cwd)
    commit_msg = f"feat: {title} (#{issue_number})\n\nAutomated by Jarvis delegation pipeline."
    _run_git(["commit", "-m", commit_msg], cwd=cwd)
    _run_git(["push", "-u", "origin", branch], cwd=cwd)


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
        f"🤖 Generated by Jarvis delegation pipeline"
    )

    pr_url = _run_gh([
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
        /delegate #42                    → (DEFAULT_REPO, 42)
        /delegate Osasuwu/my-repo#42     → ("Osasuwu/my-repo", 42)
        /delegate 42                     → (DEFAULT_REPO, 42)
    """
    args = user_input.removeprefix("/delegate").strip()
    if not args:
        raise ValueError("Usage: /delegate [owner/repo]#<issue_number>")

    # Try repo#number format
    match = re.match(r"^([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)#(\d+)$", args)
    if match:
        return match.group(1), int(match.group(2))

    # Try #number format
    match = re.match(r"^#?(\d+)$", args)
    if match:
        return DEFAULT_REPO, int(match.group(1))

    raise ValueError(f"Cannot parse: '{args}'. Use: /delegate [owner/repo]#<number>")


async def delegate_issue(
    repo: str,
    issue_number: int,
    *,
    cwd: str | Path = ROOT_DIR,
    model: str = "sonnet",
    use_api_key: bool = False,
    timeout_sec: int = 600,
) -> DelegationResult:
    """Full delegation pipeline: issue → decompose → branch → code → PR.

    Args:
        repo: GitHub repo in owner/repo format
        issue_number: Issue number to implement
        cwd: Repository working directory
        model: Model for the coding agent
        use_api_key: If True, coding agent uses API instead of Pro subscription
        timeout_sec: Timeout for the coding agent
    """
    # Step 1: Fetch issue
    try:
        issue = fetch_issue(repo, issue_number)
    except RuntimeError as exc:
        return DelegationResult(success=False, message=f"Failed to fetch issue: {exc}")

    if issue.get("state") != "OPEN":
        return DelegationResult(success=False, message=f"Issue #{issue_number} is not open.")

    title = issue["title"]

    # Step 2: Decompose (Jarvis brain, cheap)
    try:
        coding_prompt = await decompose_issue(issue, repo)
    except RuntimeError as exc:
        return DelegationResult(success=False, message=f"Decomposition failed: {exc}")

    # Step 3: Create branch
    try:
        branch = create_branch(issue_number, title, cwd=cwd)
    except RuntimeError as exc:
        return DelegationResult(success=False, message=f"Branch creation failed: {exc}")

    # Step 4: Execute coding agent
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
        # Cleanup: go back to main
        try:
            _run_git(["checkout", "main"], cwd=cwd)
            _run_git(["branch", "-D", branch], cwd=cwd)
        except RuntimeError:
            pass
        return DelegationResult(
            success=False,
            message=f"Coding agent failed: {coding_result.error}",
        )

    # Step 5: Commit and push
    try:
        commit_and_push(branch, issue_number, title, cwd=cwd)
    except RuntimeError as exc:
        return DelegationResult(
            success=False,
            message=f"Commit/push failed: {exc}",
            coding_summary=coding_result.summary,
        )

    # Step 6: Create PR
    try:
        pr_url = create_pr(repo, branch, issue_number, title, coding_result.summary)
    except RuntimeError as exc:
        return DelegationResult(
            success=False,
            message=f"PR creation failed (changes are on branch '{branch}'): {exc}",
            coding_summary=coding_result.summary,
        )

    return DelegationResult(
        success=True,
        message=f"PR created: {pr_url}",
        pr_url=pr_url,
        coding_summary=coding_result.summary,
    )

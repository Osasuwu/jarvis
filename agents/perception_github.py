"""GitHub issue ingest for task_queue — Pillar 7 Sprint 4, issue #388.

Perception module that polls GitHub for issues with ``status:ready`` +
tier labels and produces task_queue rows. One issue → one row (idempotent).

Loop closure: when a row transitions to ``done``, this module posts a
comment on the source issue with the PR link.

Architecture:
  - ``poll_tick(client)`` — main entry point, scans allowlisted repos.
  - ``_parse_scope_files(body)`` — extract file paths from issue body.
  - ``_build_row(issue)`` — pure builder (no DB, no I/O).
  - ``_idempotency_key(repo, number, labels)`` — deterministic sha256 key.
  - ``notify_completed_issues(client)`` — done-watcher, posts PR comments.
  - CLI: ``python -m agents.perception_github [--once|--loop INTERVAL]``.

Safety: per-repo allowlist prevents ingesting from arbitrary sources.
Idempotency: upsert with ON CONFLICT (idempotency_key) DO NOTHING.

CLI usage:
    python -m agents.perception_github --once
    python -m agents.perception_github --loop 60 --notify
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import re
import subprocess
import time
from datetime import UTC, datetime
from typing import Any

from supabase import Client

from agents import supabase_client

logger = logging.getLogger(__name__)

# Source identifier for approved_by column (GitHub ingest → "github:issue:<owner>/<repo>#<N>")
SOURCE = "github"

# Per-repo allowlist. Only repos in this set will be polled.
_ALLOWED_REPOS: frozenset[str] = frozenset({"Osasuwu/jarvis"})

# Goal text cap (perception.md guidance: "well under any sensible Claude prompt budget").
# A single sane number to avoid loading huge issues into task_queue.
_GOAL_MAX_CHARS = 8000

# Tier labels and their auto_dispatch mappings.
_TIER_AUTO_DISPATCH = {
    "tier:1-auto": True,
    "tier:2-review": False,
    "tier:3-human": False,
}


def _parse_scope_files(body: str) -> list[str]:
    """Extract file paths from issue body.

    Recognizes:
    - Fenced code blocks with path-like content: ```path/to/file.py```
    - Backticked references: `path/to/file.py`

    Returns a deduplicated, sorted list of unique paths. Empty list if none found.
    """
    files: set[str] = set()

    # Fenced code blocks: ```<content>``` where content looks like a file path
    # (contains / or . and no spaces/newlines inside backticks).
    fenced = re.findall(r"```([^\n`]+(?:[/\.][^\n`]+)*)\n?```", body, re.MULTILINE)
    for match in fenced:
        # Trim whitespace; if it's a path-like string, add it.
        trimmed = match.strip()
        if "/" in trimmed or "." in trimmed:
            files.add(trimmed)

    # Backticked references: `path/to/file.ext` (no spaces, contains / or .)
    backticked = re.findall(r"`([^\s`]+(?:[/\.][^\s`]+)*)`", body)
    for match in backticked:
        if "/" in match or "." in match:
            files.add(match)

    return sorted(files)


def _hash_scope_files(scope_files: list[str]) -> str:
    """Deterministic scope-files hash.

    Matches dispatcher._hash_scope_files: sort + newline-join + sha256.
    Used for approved_scope_hash and idempotency key computation.
    """
    normalized = "\n".join(sorted(scope_files or []))
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _idempotency_key(repo: str, issue_number: int, labels: list[str]) -> str:
    """Deterministic idempotency key: sha256(repo | issue_number | sorted_label_set).

    Formula from perception.md. Freezes the tier at ingest time: changing
    labels post-ingest produces a new key and a fresh row (owner can re-tier
    by closing + reopening the issue).
    """
    sorted_labels = "|".join(sorted(labels or []))
    raw = f"{repo}|{issue_number}|{sorted_labels}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _extract_tier_label(labels: list[str]) -> str | None:
    """Extract the tier label from a list of labels.

    Returns the first tier:* label found, or None if no tier label present.
    """
    for label in labels:
        if label.startswith("tier:"):
            return label
    return None


def _build_row(issue: dict[str, Any], repo: str, now: datetime) -> dict[str, Any] | None:
    """Build a task_queue row from a GitHub issue.

    Returns None if the issue is malformed or missing required components
    (e.g., no tier label). Otherwise returns a complete row ready for upsert.

    Row shape per perception.md:
      - goal: title + "\n\n" + body (capped at _GOAL_MAX_CHARS)
      - scope_files: extracted file paths (empty list if none)
      - approved_by: "github:issue:<owner>/<repo>#<N>"
      - approved_at: ISO format timestamp (poll-tick time, best-effort)
      - approved_scope_hash: sha256 of sorted scope_files
      - auto_dispatch: true iff tier:1-auto label present
      - idempotency_key: sha256(repo | number | sorted_labels)
    """
    number = issue.get("number")
    title = issue.get("title", "")
    body = issue.get("body", "") or ""
    labels_raw = issue.get("labels") or []

    # Extract label names from GitHub's label objects.
    if isinstance(labels_raw, list) and labels_raw and isinstance(labels_raw[0], dict):
        labels = [lbl.get("name", "") for lbl in labels_raw if lbl.get("name")]
    else:
        labels = [str(label) for label in labels_raw] if labels_raw else []

    # Must have a tier label.
    tier_label = _extract_tier_label(labels)
    if not tier_label:
        logger.debug(f"Issue {repo}#{number} missing tier label, skipping")
        return None

    # Build goal from title + body, capped at max chars.
    goal_raw = f"{title}\n\n{body}".strip()
    goal = goal_raw[:_GOAL_MAX_CHARS]

    # Extract scope files from body.
    scope_files = _parse_scope_files(body)

    # Build approved_by with full owner/repo path.
    approved_by = f"github:issue:{repo}#{number}"

    # approved_scope_hash matches dispatcher hash style.
    scope_hash = _hash_scope_files(scope_files)

    # auto_dispatch from tier mapping.
    auto_dispatch = _TIER_AUTO_DISPATCH.get(tier_label, False)

    # idempotency_key from formula.
    key = _idempotency_key(repo, number, labels)

    return {
        "goal": goal,
        "scope_files": scope_files,
        "approved_by": approved_by,
        "approved_at": now.isoformat(),
        "approved_scope_hash": scope_hash,
        "auto_dispatch": auto_dispatch,
        "idempotency_key": key,
        "status": "pending",
    }


def _fetch_ready_issues(repo: str) -> list[dict[str, Any]]:
    """Fetch issues with status:ready + tier:* labels from a single repo.

    Uses ``gh issue list --label status:ready --label tier:*`` to get all
    matching issues. Returns the full JSON payload for each issue.

    Raises subprocess.CalledProcessError if gh fails.
    """
    # gh issue list --label A --label B is logical AND, not OR. Comma-separated
    # values inside a single --label flag are NOT recognised as OR — gh treats
    # them as a single literal label string and matches nothing. Probed in CI:
    # `gh issue list --label "x,y"` consistently returns []. To get OR over the
    # tier set, query each tier separately and dedup by issue number.
    seen: dict[int, dict[str, Any]] = {}
    for tier in _TIER_AUTO_DISPATCH:
        cmd = [
            "gh",
            "issue",
            "list",
            "--repo",
            repo,
            "--label",
            "status:ready",
            "--label",
            tier,
            "--json",
            "number,title,body,labels",
            "--limit",
            "100",
        ]
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True,
        )
        if not result.stdout.strip():
            continue
        for issue in json.loads(result.stdout):
            number = issue.get("number")
            if number is None or number in seen:
                continue
            seen[number] = issue

    return list(seen.values())


def poll_tick(client: Client | None = None) -> None:
    """Poll GitHub for ready issues and upsert them into task_queue.

    This is the main entry point for the perception tick. For each allowed
    repo, fetch issues and build rows, then upsert with ON CONFLICT DO NOTHING
    to ensure idempotency.

    Args:
        client: Supabase client. If None, a new one is created.
    """
    cli = client or supabase_client.get_client()
    now = datetime.now(UTC)

    for repo in _ALLOWED_REPOS:
        try:
            issues = _fetch_ready_issues(repo)
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to fetch issues for {repo}: {e.stderr}")
            continue

        inserted_count = 0
        for issue in issues:
            try:
                row = _build_row(issue, repo, now)
                if row is None:
                    continue

                # Upsert with idempotency key. ON CONFLICT DO NOTHING ensures
                # that re-running this tick produces zero new rows on duplicate keys.
                result = (
                    cli.table("task_queue")
                    .upsert(row, on_conflict="idempotency_key", ignore_duplicates=True)
                    .execute()
                )

                if result.data:
                    inserted_count += 1
                    key_prefix = row["idempotency_key"][:12]
                    logger.debug(f"Inserted {repo}#{issue['number']} (key:{key_prefix})")
                else:
                    key_prefix = row["idempotency_key"][:12]
                    logger.debug(f"Skipped duplicate {repo}#{issue['number']} (key:{key_prefix})")

            except Exception as e:
                logger.error(f"Error building/inserting row for {repo}#{issue.get('number')}: {e}")
                continue

        logger.info(f"Perception GitHub tick: {repo} inserted {inserted_count} row(s)")


def notify_completed_issues(client: Client | None = None) -> None:
    """Post PR-link comments on GitHub issues when their rows reach 'done'.

    Watches task_queue for rows where:
      - status = 'done'
      - approved_by starts with 'github:issue:'
      - not yet notified (checked via audit_log marker)

    Posts a comment on each issue with the PR link, then records the
    notification in audit_log to prevent re-posting on retry.

    Note (from perception.md): this watcher will idle until a result-collection
    path lands (future sprint) or until the owner manually flips status. Today,
    no rows naturally transition to 'done'.
    """
    cli = client or supabase_client.get_client()

    # Fetch task_queue rows that are done and github-sourced.
    done_rows = cli.table("task_queue").select("*").eq("status", "done").execute().data or []

    for row in done_rows:
        approved_by = row.get("approved_by", "")
        if not approved_by.startswith("github:issue:"):
            continue

        idempotency_key = row.get("idempotency_key", "")

        # Check if we've already notified this row (via audit marker).
        # Use the idempotency_key as the unique identifier.
        existing = (
            cli.table("audit_log")
            .select("id")
            .eq("agent_id", "perception-github")
            .eq("action", "notify-issue-completed")
            .eq("target", idempotency_key)
            .limit(1)
            .execute()
            .data
            or []
        )
        if existing:
            logger.debug(f"Row {idempotency_key} already notified, skipping")
            continue

        # Parse approved_by to extract repo and issue number.
        # Format: "github:issue:<owner>/<repo>#<N>"
        try:
            parts = approved_by.replace("github:issue:", "").split("#")
            if len(parts) != 2:
                logger.error(f"Malformed approved_by format: {approved_by}")
                continue
            repo = parts[0]
            issue_number = int(parts[1])
        except (ValueError, IndexError) as e:
            logger.error(f"Failed to parse approved_by {approved_by}: {e}")
            continue

        # Get the PR link from the row (or from related audit logs).
        # This is a stub for now — in a real implementation, we'd have
        # the PR link from the dispatcher's audit trail. For Sprint 4,
        # the owner will manually set this, so we skip posting for now.
        pr_link = (
            row.get("details", {}).get("pr_url") if isinstance(row.get("details"), dict) else None
        )
        if not pr_link:
            logger.debug(f"No PR link yet for {repo}#{issue_number}, skipping notification")
            continue

        # Post the comment.
        try:
            cmd = [
                "gh",
                "issue",
                "comment",
                str(issue_number),
                "--repo",
                repo,
                "--body",
                f"Completed via PR {pr_link}",
            ]
            subprocess.run(cmd, capture_output=True, text=True, check=True)
            logger.info(f"Posted completion comment on {repo}#{issue_number}")

            # Record that we've notified this row.
            supabase_client.audit(
                agent_id="perception-github",
                tool_name="gh",
                action="notify-issue-completed",
                target=idempotency_key,
                outcome="success",
                client=cli,
            )
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to comment on {repo}#{issue_number}: {e.stderr}")


def main() -> None:
    """CLI entry point for manual or scheduled runs."""
    parser = argparse.ArgumentParser(
        description="GitHub perception agent — poll and ingest ready issues."
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run one tick and exit (default if neither --once nor --loop specified).",
    )
    parser.add_argument(
        "--loop",
        type=int,
        metavar="INTERVAL",
        help="Run on INTERVAL seconds. 0 = continuous (no delay).",
    )
    parser.add_argument(
        "--notify",
        action="store_true",
        help="Also run the done-watcher (notify_completed_issues).",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    if args.loop is not None:
        logger.info(f"Starting loop with {args.loop}s interval")
        while True:
            poll_tick()
            if args.notify:
                notify_completed_issues()
            if args.loop > 0:
                time.sleep(args.loop)
    else:
        # Default: single tick (--once is explicit, but not required).
        logger.info("Running single tick")
        poll_tick()
        if args.notify:
            notify_completed_issues()


if __name__ == "__main__":
    main()

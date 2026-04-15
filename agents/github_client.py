"""Tiny GitHub Events API client for the monitor agent.

Scope (Sprint 1, issue #174): fetch recent repo events for classification.
Nothing else — no issue creation, no PR management. The agent observes;
it doesn't act.

Uses ``httpx`` (already pulled in transitively by ``supabase-py``) so no
new dependency is needed.
"""

from __future__ import annotations

import os
from typing import Any

import httpx

# Events we care about for classification. Everything else (WatchEvent,
# ForkEvent, CreateEvent of a branch…) is pure noise for the Sprint 1
# proof of concept. Keeping the allow-list tight avoids paying Ollama
# tokens on events we'd immediately drop anyway.
RELEVANT_EVENT_TYPES = frozenset(
    {
        "IssuesEvent",
        "PullRequestEvent",
        "PullRequestReviewEvent",
        "IssueCommentEvent",
        "PullRequestReviewCommentEvent",
        "PushEvent",
    }
)


def _headers(token: str | None) -> dict[str, str]:
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def fetch_repo_events(
    repo: str,
    *,
    after_event_id: str | None = None,
    limit: int = 10,
    token: str | None = None,
    timeout: float = 10.0,
) -> list[dict[str, Any]]:
    """Return recent public events for ``repo`` (newest first).

    * ``after_event_id`` — drop any event whose id is <= this one. GitHub
      event ids are monotonically increasing strings-of-integers, so
      string-compare by integer value is the correct semantics.
    * ``limit`` — cap Ollama classification cost; defaults to 10 per run.
    * ``token`` — optional GitHub token. Unauthenticated requests hit a
      60 req/hour rate limit per IP, which is fine for low-frequency
      monitoring but will trip on busy repos.

    Filtered to ``RELEVANT_EVENT_TYPES``. Returns raw GitHub event dicts.
    """
    auth_token = token if token is not None else os.environ.get("GITHUB_TOKEN")
    url = f"https://api.github.com/repos/{repo}/events"
    response = httpx.get(
        url,
        headers=_headers(auth_token),
        params={"per_page": 30},  # fetch a wider page, filter client-side
        timeout=timeout,
    )
    response.raise_for_status()
    events: list[dict[str, Any]] = response.json()

    # GitHub returns newest first. For cursor comparison, use integer
    # conversion — the API guarantees numeric ids.
    cursor = int(after_event_id) if after_event_id else 0
    filtered = [
        e
        for e in events
        if e.get("type") in RELEVANT_EVENT_TYPES and int(e.get("id", "0")) > cursor
    ]
    # Re-sort oldest-first before the limit slice. GitHub's response is
    # newest-first, so a naive ``filtered[:limit]`` would pick the N newest
    # and the monitor would then advance the cursor to the max id in that
    # slice — permanently skipping the older-but-still-new events that
    # didn't fit. Taking the oldest N instead makes the cursor advance
    # contiguous: next poll resumes right after the last stored event.
    filtered.sort(key=lambda e: int(e.get("id", "0")))
    return filtered[:limit]


def summarise_event(event: dict[str, Any]) -> str:
    """Return a one-line summary suitable for LLM classification.

    Pulls only the fields the model actually needs — keeps prompts small
    and removes the URL soup GitHub ships in each event payload.
    """
    event_type = event.get("type", "UnknownEvent")
    actor = event.get("actor", {}).get("login", "unknown")
    repo_name = event.get("repo", {}).get("name", "unknown")
    payload = event.get("payload", {}) or {}

    # Type-specific extraction — each branch grabs the one or two human
    # fields that make the event interpretable.
    if event_type == "IssuesEvent":
        action = payload.get("action", "?")
        issue = payload.get("issue", {}) or {}
        detail = f"{action} #{issue.get('number')}: {issue.get('title', '')}"
    elif event_type == "PullRequestEvent":
        action = payload.get("action", "?")
        pr = payload.get("pull_request", {}) or {}
        detail = f"{action} PR #{pr.get('number')}: {pr.get('title', '')}"
    elif event_type == "PullRequestReviewEvent":
        review = payload.get("review", {}) or {}
        pr = payload.get("pull_request", {}) or {}
        detail = f"review ({review.get('state', '?')}) on PR #{pr.get('number')}"
    elif event_type in ("IssueCommentEvent", "PullRequestReviewCommentEvent"):
        action = payload.get("action", "created")
        issue = payload.get("issue", payload.get("pull_request", {})) or {}
        detail = f"comment {action} on #{issue.get('number')}"
    elif event_type == "PushEvent":
        ref = payload.get("ref", "?")
        commits = len(payload.get("commits", []) or [])
        detail = f"push {commits} commits to {ref}"
    else:
        detail = "(details omitted)"

    return f"[{event_type}] {repo_name} by {actor}: {detail}"

"""Tiny GitHub Events API client for the monitor agent.

Scope (Sprint 1, issue #174): fetch recent repo events for classification.
Nothing else — no issue creation, no PR management. The agent observes;
it doesn't act.

Uses ``httpx``, declared as a direct dependency of the ``[agents]`` extra
in ``pyproject.toml``. (It was originally picked up transitively via
``supabase-py`` — see #183 for why the contract was tightened.)
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


# GitHub's /events endpoint serves at most ~300 events total across up to
# 3 pages. ``per_page=100`` is the maximum the API accepts.
_MAX_EVENTS_PAGES = 3
_PER_PAGE = 100


def fetch_repo_events(
    repo: str,
    *,
    after_event_id: str | None = None,
    limit: int = 10,
    token: str | None = None,
    timeout: float = 10.0,
) -> list[dict[str, Any]]:
    """Return recent events for ``repo`` filtered to RELEVANT_EVENT_TYPES,
    oldest first.

    GitHub returns events newest-first; this function paginates (up to 3
    pages of 100), filters to the allow-list, and re-sorts ascending before
    slicing to ``limit``. Taking the oldest N makes the monitor's cursor
    advance contiguous: the next poll resumes right after the last stored
    event rather than skipping past older-but-still-new activity that didn't
    fit in the slice.

    * ``after_event_id`` — drop any event whose id is <= this one. GitHub
      event ids are monotonically increasing integer-strings; this function
      converts them with ``int(...)`` and compares numerically.
    * ``limit`` — cap how many matching events to return per call (and
      therefore how many Ollama classifications are paid for). Default 10.
    * ``token`` — optional GitHub token. Unauthenticated requests hit a
      60 req/hour rate limit per IP, which is fine for low-frequency
      monitoring but will trip on busy repos.

    Pagination stops early when a page's oldest event id is <= the cursor
    (nothing newer can exist on later pages) or when a short page signals
    the end of available history. This prevents silent event loss on busy
    repos where more than one page of relevant activity lands between polls.
    """
    auth_token = token if token is not None else os.environ.get("GITHUB_TOKEN")
    cursor = int(after_event_id) if after_event_id else 0
    url = f"https://api.github.com/repos/{repo}/events"

    collected: list[dict[str, Any]] = []
    for page in range(1, _MAX_EVENTS_PAGES + 1):
        response = httpx.get(
            url,
            headers=_headers(auth_token),
            params={"per_page": _PER_PAGE, "page": page},
            timeout=timeout,
        )
        response.raise_for_status()
        page_events: list[dict[str, Any]] = response.json()
        if not page_events:
            break

        for event in page_events:
            if event.get("type") in RELEVANT_EVENT_TYPES and int(event.get("id", "0")) > cursor:
                collected.append(event)

        # The last element on each page is the oldest on that page (GitHub
        # returns newest-first). If it's already <= cursor, every event on
        # subsequent pages is strictly older — no further matches possible.
        oldest_on_page = int(page_events[-1].get("id", "0"))
        if oldest_on_page <= cursor:
            break
        # A partial page means GitHub has no more history to return.
        if len(page_events) < _PER_PAGE:
            break

    collected.sort(key=lambda e: int(e.get("id", "0")))
    return collected[:limit]


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

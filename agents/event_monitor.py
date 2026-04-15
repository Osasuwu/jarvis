"""Event monitor agent — first persistent LangGraph agent (issue #174).

Polls the GitHub Events API for a configured list of repos, asks a local
Ollama model to classify each event as noise / info / action, and pushes
non-noise events into Supabase so Claude Code picks them up via
``events_list``.

The agent is an observer, not an actor: it never opens issues, comments,
or triggers CI. Taking action is Pillar 7 Sprint 2+ territory.

Runs on demand:

    python -m agents.event_monitor
    python -m agents.event_monitor --repo Osasuwu/jarvis --thread event-monitor

State (including per-repo cursors) is checkpointed to local Postgres via
``PostgresSaver``. Restart-safe: repeated invocations skip events that were
already processed.
"""

from __future__ import annotations

import argparse
import json
from typing import Any, TypedDict

from dotenv import load_dotenv
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.graph import END, START, StateGraph

from agents import supabase_client
from agents.config import load_config
from agents.github_client import fetch_repo_events, summarise_event
from agents.ollama_client import chat as ollama_chat

# Agent identity stamped into every audit_log / events.source row. Matches
# the convention in docs/agents/langgraph-setup.md.
AGENT_ID = "langgraph-monitor"

# Default repo list when --repo isn't passed. Sprint 1 spec says start with
# this one only; more come online in Sprint 2.
DEFAULT_REPOS = ["Osasuwu/jarvis"]

# Three-tier classification.
#   noise  — bot chatter, fork/watch, trivial commits; dropped silently.
#   info   — new issue/PR/review/comment worth knowing about.
#   action — needs a human soon (failing check, review request, security).
# Kept tight so the small Qwen3:4b model can pick reliably with temp=0.
_CLASSIFY_SCHEMA = {
    "type": "object",
    "properties": {
        "classification": {"type": "string", "enum": ["noise", "info", "action"]},
        "reason": {"type": "string"},
    },
    "required": ["classification", "reason"],
}

_CLASSIFY_SYSTEM = (
    "You classify GitHub repository events for a personal AI agent. "
    "Reply with JSON matching the schema — no commentary.\n"
    "Labels:\n"
    "  noise  — bots, fork/watch, trivial bumps, merges of already-reviewed PRs\n"
    "  info   — new issue, new PR, new review, non-trivial comment\n"
    "  action — needs human soon: failing check, review request, urgent "
    "comment, security finding"
)

# Severity mapping into the events table. The MCP server only knows
# {critical, high, medium, low, info} — see SEVERITY_ORDER in server.py.
# "action" maps to medium; "info" stays info.
_SEVERITY = {"info": "info", "action": "medium"}


class MonitorState(TypedDict):
    """Graph state. Persists between runs via the Postgres checkpointer."""

    repos: list[str]
    # repo -> id of the newest event we've successfully stored. Only
    # advanced in the store node, so a failure mid-run doesn't cause
    # skipped events on restart.
    cursors: dict[str, str]
    fetched_events: list[dict[str, Any]]
    classified_events: list[dict[str, Any]]
    stored_count: int


def fetch_events_node(state: MonitorState) -> dict[str, Any]:
    """Pull new events per repo using the persisted cursors."""
    cursors = state.get("cursors") or {}
    fetched: list[dict[str, Any]] = []
    for repo in state["repos"]:
        after = cursors.get(repo)
        events = fetch_repo_events(repo, after_event_id=after, limit=10)
        fetched.extend(events)
    return {"fetched_events": fetched}


def classify_node(state: MonitorState) -> dict[str, Any]:
    """Ask Ollama to label each fetched event."""
    classified: list[dict[str, Any]] = []
    for event in state.get("fetched_events", []):
        summary = summarise_event(event)
        raw = ollama_chat(
            messages=[
                {"role": "system", "content": _CLASSIFY_SYSTEM},
                {"role": "user", "content": summary},
            ],
            format=_CLASSIFY_SCHEMA,
            options={"temperature": 0, "num_predict": 80},
        )
        try:
            parsed = json.loads(raw)
            label = parsed["classification"]
            reason = parsed["reason"]
        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            # Bad classifier output — prefer surfacing to silent drop.
            # The reason field records what broke so it shows up in the
            # events table payload for later inspection.
            label = "info"
            reason = f"classifier_error: {exc}"
        classified.append(
            {
                "event": event,
                "summary": summary,
                "classification": label,
                "reason": reason,
            }
        )
    return {"classified_events": classified}


def store_node(state: MonitorState) -> dict[str, Any]:
    """Persist non-noise events to Supabase and advance cursors."""
    stored = 0
    for item in state.get("classified_events", []):
        label = item["classification"]
        if label == "noise":
            continue
        event = item["event"]
        repo = event.get("repo", {}).get("name", "unknown")
        supabase_client.store_event(
            event_type=f"github.{event.get('type', 'UnknownEvent')}",
            repo=repo,
            title=item["summary"],
            severity=_SEVERITY.get(label, "info"),
            payload={
                "github_event_id": event.get("id"),
                "classification": label,
                "reason": item["reason"],
                "raw_type": event.get("type"),
                "actor": event.get("actor", {}).get("login"),
            },
            source=AGENT_ID,
        )
        stored += 1

    # Advance cursors only after storage completes — if store_event raises
    # mid-loop, the checkpoint keeps the old cursors and the next run
    # reprocesses. Duplicate info rows are cheaper than lost events.
    cursors = dict(state.get("cursors") or {})
    for event in state.get("fetched_events", []):
        repo = event.get("repo", {}).get("name")
        ev_id = event.get("id")
        if not repo or not ev_id:
            continue
        prev = cursors.get(repo)
        if prev is None or int(ev_id) > int(prev):
            cursors[repo] = str(ev_id)

    # Audit every run — empty polling cycles included. Useful to confirm
    # the agent is alive and see what it looked at.
    supabase_client.audit(
        agent_id=AGENT_ID,
        tool_name="event_monitor",
        action="poll",
        target=",".join(state["repos"]),
        details={
            "fetched": len(state.get("fetched_events", [])),
            "classified": len(state.get("classified_events", [])),
            "stored": stored,
            "cursors": cursors,
        },
    )
    return {"stored_count": stored, "cursors": cursors}


def build_graph() -> StateGraph:
    """Define the monitor graph: fetch → classify → store."""
    graph: StateGraph = StateGraph(MonitorState)
    graph.add_node("fetch_events", fetch_events_node)
    graph.add_node("classify", classify_node)
    graph.add_node("store", store_node)
    graph.add_edge(START, "fetch_events")
    graph.add_edge("fetch_events", "classify")
    graph.add_edge("classify", "store")
    graph.add_edge("store", END)
    return graph


def run(thread_id: str, repos: list[str]) -> int:
    """Invoke one monitoring pass, reusing any persisted cursors."""
    cfg = load_config()
    with PostgresSaver.from_conn_string(cfg.postgres_url) as checkpointer:
        checkpointer.setup()
        app = build_graph().compile(checkpointer=checkpointer)
        config = {"configurable": {"thread_id": thread_id}}

        # Read persisted cursors from the last run of this thread. Without
        # this, invoke() would replace cursors with `{}` and we'd start
        # over each time — defeating the whole point of checkpointing.
        snapshot = app.get_state(config)
        prior_values = snapshot.values or {}
        cursors = dict(prior_values.get("cursors") or {})

        result = app.invoke(
            {
                "repos": repos,
                "cursors": cursors,
                "fetched_events": [],
                "classified_events": [],
                "stored_count": 0,
            },
            config=config,
        )

        fetched = len(result.get("fetched_events", []))
        stored = result.get("stored_count", 0)
        print(f"[monitor] thread={thread_id}")
        print(f"[monitor] repos:   {', '.join(repos)}")
        print(f"[monitor] fetched: {fetched}")
        print(f"[monitor] stored:  {stored}")
        print(f"[monitor] cursors: {result.get('cursors')}")
    return 0


def main() -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--thread",
        default="event-monitor",
        help="LangGraph thread ID (default: event-monitor)",
    )
    parser.add_argument(
        "--repo",
        action="append",
        default=None,
        help=f"Repo to monitor (repeatable). Defaults to {DEFAULT_REPOS[0]}.",
    )
    args = parser.parse_args()
    repos = args.repo or list(DEFAULT_REPOS)
    return run(args.thread, repos)


if __name__ == "__main__":
    raise SystemExit(main())

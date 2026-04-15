"""Minimal LangGraph demo — validates Pillar 7 Sprint 1 foundation.

Acceptance checks (issue #172):
  * `python -m agents.main` runs a minimal graph end-to-end.
  * Checkpoint is persisted to PostgreSQL.
  * `python -m agents.main --resume` reads the saved state back,
    proving the graph survives a process restart.

Usage:
  # First run — creates checkpoint tables, saves state, prints result.
  python -m agents.main

  # Second run in a fresh process — loads the saved state.
  python -m agents.main --resume

  # Optional: use a custom thread ID (defaults to 'demo-thread').
  python -m agents.main --thread my-thread
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import TypedDict

from dotenv import load_dotenv
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.graph import END, START, StateGraph

from agents.config import load_config
from agents.ollama_client import chat as ollama_chat

# Schema used by the demo node — mirrors the pattern future classification
# agents will use (structured output enforced by Ollama `format`).
_STATUS_SCHEMA = {
    "type": "object",
    "properties": {
        "status": {"type": "string", "enum": ["ok", "fail"]},
    },
    "required": ["status"],
}


class DemoState(TypedDict):
    """Minimal state: user prompt, model reply, and a step counter."""

    prompt: str
    reply: str
    step: int


def respond(state: DemoState) -> dict[str, object]:
    """Single graph node — asks Ollama for a schema-enforced ack.

    The output is validated strictly: a non-JSON response or a missing
    `status` field fails the run. Silent fallback would defeat the whole
    point of the foundation check.
    """
    raw = ollama_chat(
        messages=[
            {
                "role": "system",
                "content": "Reply strictly as JSON matching the schema. No commentary.",
            },
            {"role": "user", "content": state["prompt"]},
        ],
        format=_STATUS_SCHEMA,
        options={"temperature": 0, "num_predict": 40},
    )
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Ollama returned non-JSON despite format schema: {raw!r}") from exc
    status = parsed.get("status")
    if not isinstance(status, str) or not status:
        raise RuntimeError(f"Ollama JSON missing required `status` field: {parsed!r}")
    return {"reply": status.strip(), "step": state.get("step", 0) + 1}


def build_graph() -> StateGraph:
    """Define the graph: START -> respond -> END."""
    graph: StateGraph = StateGraph(DemoState)
    graph.add_node("respond", respond)
    graph.add_edge(START, "respond")
    graph.add_edge("respond", END)
    return graph


def run(thread_id: str, resume: bool) -> int:
    cfg = load_config()
    with PostgresSaver.from_conn_string(cfg.postgres_url) as checkpointer:
        checkpointer.setup()
        app = build_graph().compile(checkpointer=checkpointer)
        config = {"configurable": {"thread_id": thread_id}}

        if resume:
            snapshot = app.get_state(config)
            if not snapshot.values:
                print(
                    f"No prior checkpoint for thread '{thread_id}'. Run without --resume first.",
                    file=sys.stderr,
                )
                return 1
            print(f"[resume] thread={thread_id}")
            print(f"[resume] prompt: {snapshot.values.get('prompt')}")
            print(f"[resume] reply:  {snapshot.values.get('reply')}")
            print(f"[resume] step:   {snapshot.values.get('step')}")
            checkpoint_id = snapshot.config.get("configurable", {}).get("checkpoint_id")
            print(f"[resume] checkpoint_id: {checkpoint_id}")
            return 0

        prompt = "Reply with a single short sentence: the word 'ok'."
        result = app.invoke({"prompt": prompt, "reply": "", "step": 0}, config=config)
        snapshot = app.get_state(config)
        checkpoint_id = snapshot.config.get("configurable", {}).get("checkpoint_id")
        print(f"[run]  thread={thread_id}")
        print(f"[run]  reply:         {result['reply']}")
        print(f"[run]  step:          {result['step']}")
        print(f"[run]  checkpoint_id: {checkpoint_id}")
    return 0


def main() -> int:
    # Load .env from the working directory — entry-point-only so that
    # library callers (and tests) keep full control over the environment.
    load_dotenv()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--thread",
        default="demo-thread",
        help="LangGraph thread ID (default: demo-thread)",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Load and print the latest checkpoint for the thread",
    )
    args = parser.parse_args()
    return run(args.thread, args.resume)


if __name__ == "__main__":
    raise SystemExit(main())

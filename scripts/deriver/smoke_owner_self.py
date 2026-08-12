"""Synthetic E2E smoke — owner-self-reflection pass (#1556).

Mirrors ``scripts/comm_patterns/smoke_synthetic.py``'s pattern: a small
synthetic transcript standing in for a real one that could not be located
(the robot-day 2026-07-26 session). The turns below are shaped after that
day's known feedback class — cherry-picking wins, a rehearsal that did not
go as planned, an owner competence assessment, and a broad "nothing went to
plan" retrospective — none of which fit ``comm_patterns``' reactive,
pair-structured 6-label rubric (correction/affirmation/preference/meta —
see ``comm_patterns/classifier.py::VALID_LABELS``), which is why the
Deriver needed a dedicated non-reactive pass instead of a 7th label there.

Run:
    .venv/Scripts/python.exe -m deriver.smoke_owner_self
"""

from __future__ import annotations

import json
import os
import socket
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlparse
from uuid import UUID, uuid4

from .pipeline import derive_owner_self_pass

SESSION_ID = "smoke-owner-self"
PROJECT_HASH = "smoke0000hash"


def _ollama_reachable() -> bool:
    """Best-effort TCP probe against the configured Ollama host.

    Mirrors ``smoke_synthetic.py``'s exit-3 convention: a live-model smoke
    that can't reach its backend is an environment gap, not a code failure,
    and should be distinguishable from a genuine extraction failure.
    """
    host = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
    parsed = urlparse(host)
    hostname = parsed.hostname or "localhost"
    port = parsed.port or 11434
    try:
        with socket.create_connection((hostname, port), timeout=2):
            return True
    except OSError:
        return False


def _build_buffer(buffer_dir: Path) -> None:
    proj_dir = buffer_dir / PROJECT_HASH
    proj_dir.mkdir(parents=True, exist_ok=True)
    path = proj_dir / f"{SESSION_ID}.jsonl"
    rows = [
        {
            "role": "user",
            "content": (
                "Looking back at today, I keep cherry-picking the wins for the "
                "status update and glossing over the parts that failed."
            ),
        },
        {"role": "assistant", "content": "Noted — want that reflected in the report?"},
        {
            "role": "user",
            "content": (
                "No, just flagging it for myself. Also the rehearsal run this "
                "morning did not go anywhere near as planned — I skipped half "
                "the checklist because I was rushing."
            ),
        },
        {"role": "assistant", "content": "Understood."},
        {
            "role": "user",
            "content": (
                "Honestly I don't think I'm that good at estimating how long "
                "this kind of setup takes — I should have known better than to "
                "block only an hour for it."
            ),
        },
        {"role": "assistant", "content": "Ack."},
        {"role": "user", "content": "Basically nothing went to plan today."},
    ]
    with path.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")


def _make_fake_insert() -> tuple[callable, list[dict]]:
    captured: list[dict] = []

    def insert_fn(row: dict) -> UUID:
        uid = uuid4()
        captured.append(row)
        return uid

    return insert_fn, captured


def main() -> int:
    if not _ollama_reachable():
        print(
            "Ollama unavailable — owner-self pass could not run live. "
            "Start Ollama (`ollama serve`) and re-run this smoke.",
            file=sys.stderr,
        )
        return 3

    with tempfile.TemporaryDirectory() as td:
        buffer_dir = Path(td)
        _build_buffer(buffer_dir)
        insert_fn, captured = _make_fake_insert()

        result = derive_owner_self_pass(
            SESSION_ID,
            project_hash=PROJECT_HASH,
            insert_fn=insert_fn,
            buffer_root=buffer_dir,
        )

        print(f"inserted: {len(result)}")
        for row in captured:
            print(
                f"  type={row['type']} tags={row['tags']} "
                f"name={row['name']!r} content={row['content'][:80]!r}"
            )

        if not captured:
            print(
                "FAIL: owner-self pass surfaced nothing for a transcript "
                "built around cherry-picking / rehearsal-failure / "
                'competence / "nothing went to plan" content.',
                file=sys.stderr,
            )
            return 1

        if not all(
            row["type"] == "feedback" and "scope:owner-self" in row["tags"] for row in captured
        ):
            print(
                "FAIL: not every inserted row carries type=feedback + scope:owner-self",
                file=sys.stderr,
            )
            return 1

    print("OK: owner-self pass surfaces the robot-day-2026-07-26-shaped feedback class.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

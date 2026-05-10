"""Extractor — wires transcript → classifier → scrubber → store.

Pure orchestrator, no I/O of its own beyond the injected dependencies.
The CLI entry (``scripts/comm-patterns-extract.py``) wires real
implementations. Tests inject fakes.

The classifier function signature:
    classify_fn(user_text: str, prev_assistant_text: str) -> dict | None
        returns {primary_label, subtype, confidence, anchor_quote} or None.

A None return (or a result with primary_label=None) means "no pattern" —
the turn is *processed* (watermark moves past it) but no row is written.
This is the right answer: if we re-ran later we'd want the watermark to
already cover it.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .scrubber import scrub
from .store import Store
from .transcript import Turn, is_headless_cwd, is_interactive, parse_turns

CONFIDENCE_THRESHOLD = 0.5

ClassifyFn = Callable[[str, str], dict[str, Any] | None]


def _to_row(
    turn: Turn,
    classified: dict[str, Any],
    *,
    device: str,
    session_id: str,
    source_provenance: str,
) -> dict[str, Any]:
    anchor_raw = classified.get("anchor_quote") or turn.user_text[:600]
    anchor_scrubbed, redacted = scrub(anchor_raw)
    captured_at = turn.timestamp or datetime.now(timezone.utc).isoformat()
    return {
        "device": device,
        "session_id": session_id,
        "message_idx": turn.message_idx,
        "captured_at": captured_at,
        "primary_label": classified["primary_label"],
        "subtype": classified.get("subtype"),
        "confidence": classified["confidence"],
        "anchor_quote": anchor_scrubbed,
        "redacted": redacted,
        "embedding": None,  # Day-1 column nullable; backfilled by /learn comms.
        "source_provenance": source_provenance,
    }


def extract_session(
    *,
    device: str,
    session_id: str,
    transcript_path: Path,
    cwd: str | None,
    store: Store,
    classify_fn: ClassifyFn,
    source_provenance: str,
) -> dict[str, Any]:
    """Run the extractor for one session. Returns a stats dict.

    Idempotent: the watermark in the store is consulted *before* each turn
    is classified. The unique index on (device, session_id, message_idx)
    is the second line of defence against double-writes.

    Headless / sandcastle sessions are skipped — see
    :func:`transcript.is_headless_cwd` for the heuristic.
    """
    stats: dict[str, Any] = {
        "session_id": session_id,
        "device": device,
        "skipped": None,
        "turns_seen": 0,
        "turns_classified": 0,
        "rows_written": 0,
        "low_confidence_skipped": 0,
        "no_pattern_skipped": 0,
        "watermark_before": -1,
        "watermark_after": -1,
    }

    if is_headless_cwd(cwd):
        stats["skipped"] = "headless_cwd"
        return stats

    turns = parse_turns(transcript_path)
    stats["turns_seen"] = len(turns)
    if not is_interactive(turns):
        stats["skipped"] = "no_user_messages"
        return stats

    watermark_before = store.get_watermark(device, session_id)
    stats["watermark_before"] = watermark_before
    new_watermark = watermark_before

    for turn in turns:
        if turn.message_idx <= watermark_before:
            continue
        result = classify_fn(turn.user_text, turn.prev_assistant_text)
        stats["turns_classified"] += 1
        # Distinguish two None-shaped outcomes:
        #   * result is None              — classifier failure (network, parse).
        #     Don't advance the watermark; transient failures retry next run.
        #   * result["primary_label"] is None — definitive "no pattern".
        #     Advance the watermark; the model gave its answer.
        if result is None:
            stats["no_pattern_skipped"] += 1
            continue
        if turn.message_idx > new_watermark:
            new_watermark = turn.message_idx
        if result.get("primary_label") is None:
            stats["no_pattern_skipped"] += 1
            continue
        if float(result.get("confidence", 0.0)) < CONFIDENCE_THRESHOLD:
            stats["low_confidence_skipped"] += 1
            continue
        row = _to_row(
            turn,
            result,
            device=device,
            session_id=session_id,
            source_provenance=source_provenance,
        )
        store.insert_row(row)
        stats["rows_written"] += 1

    if new_watermark > watermark_before:
        store.set_watermark(device, session_id, new_watermark)
    stats["watermark_after"] = new_watermark
    return stats

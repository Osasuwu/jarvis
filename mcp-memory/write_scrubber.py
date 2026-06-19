"""MCP write-path Tier-2 secret-scrubber gate (#555).

The slice-3 scrubber (``scripts/lib/secret_scrubber.py``) is applied at the
MCP write boundary. This is the Tier-2 backstop in the two-layer privacy
model (decision ``eb62980e``, ADR-0003): even if the SessionEnd hook scrubber
(slice 6) leaks, MCP writes still cannot land secrets.

When any pattern fires on user-supplied text, the write is **rejected** — not
silently scrubbed. The write is intent-bearing, so the sender must know the
payload was blocked rather than silently rewritten.

Privacy invariant: no value from a blocked payload ever leaves this module.
Only pattern names + fire counts appear in the rejection error, the
``mcp_write_scrubber_block`` counter event, or any log line.

Scope (#555 AC): this gate covers the two free-text write paths named in the
acceptance criteria — ``memory_store`` and ``record_decision``. Three other
handlers also persist user free-text (``goal_set``/``goal_update``,
``outcome_record``/``outcome_update``, ``credential_add``); extending the gate
to ``goal``/``outcome`` is tracked as a follow-up slice. ``credential_add`` is
deliberately NOT a candidate — its entire purpose is to store secrets, so a
reject-gate there would be a contradiction (that store relies on RLS + the
``credential_registry`` access model, not scrubbing).
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from collections.abc import Iterator
from pathlib import Path

# The scrubber lib lives under scripts/lib. The live server runtime launches
# server.py from mcp-memory/ (via run-memory-server.py), so scripts/ is NOT on
# sys.path by default — add it here so jarvis always loads the real gate
# instead of silently degrading to a no-op. Tests already put scripts/ on the
# path (conftest), so the insert is idempotent there.
_SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
if _SCRIPTS.is_dir() and str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

try:
    from lib.secret_scrubber import scrub, API_KEY_PATTERNS  # type: ignore
except Exception:  # noqa: BLE001 — cross-repo (redrobot) may lack scripts/lib
    scrub = None  # type: ignore
    API_KEY_PATTERNS = []  # type: ignore
    # Fail-open is intentional (availability > over-blocking) but MUST be loud:
    # a silent no-op would erase the Tier-2 layer with zero operator signal.
    print(
        "[write_scrubber] WARNING: secret_scrubber unavailable — the Tier-2 "
        "MCP write-path gate is DISABLED; writes will NOT be scanned for secrets.",
        file=sys.stderr,
    )


# Patterns the scrubber detects but that must NOT hard-block an MCP write.
# `path_username` is a privacy *normalization* (scrub-and-keep), not a secret
# leak: ~26% of the live memory corpus (214/832) legitimately contains absolute
# user paths (`C:\Users\<name>\…`, `/Users/<name>/…`). Hard-rejecting those
# would violate AC#4 ("no false-positive blocks on real-world content") and
# break a quarter of all memory writes that reference a file path. Path
# normalization is the SessionEnd/Deriver lane's job (slice 6), not this
# Tier-2 secret-reject backstop. The genuine-secret patterns (API keys, env
# blocks) — 0 false positives in the corpus — remain blocking.
SCRUB_ONLY_PATTERNS = frozenset({"path_username"})

# Guard against silent string-coupling drift: SCRUB_ONLY_PATTERNS names must be
# real pattern names emitted by secret_scrubber.py. If a pattern is renamed
# there, this raises at import (loud) instead of letting the frozenset become a
# no-op that starts hard-blocking every path-containing write.
_KNOWN_PATTERN_NAMES = {name for name, _ in API_KEY_PATTERNS} | {"env_block", "path_username"}
if scrub is not None and not SCRUB_ONLY_PATTERNS <= _KNOWN_PATTERN_NAMES:
    raise RuntimeError(
        "write_scrubber.SCRUB_ONLY_PATTERNS references pattern name(s) not "
        f"produced by secret_scrubber: {SCRUB_ONLY_PATTERNS - _KNOWN_PATTERN_NAMES}. "
        "A rename in secret_scrubber.py silently disables path exclusion — "
        "update SCRUB_ONLY_PATTERNS in lockstep."
    )


def _iter_strings(value: object) -> Iterator[str]:
    """Yield the str values worth scanning out of a field value.

    str → itself; list/tuple → each str element; everything else (ints,
    None, dicts, floats) is skipped so non-text fields never raise.
    """
    if isinstance(value, str):
        yield value
    elif isinstance(value, (list, tuple)):
        for item in value:
            if isinstance(item, str):
                yield item


def scan_fields(fields: dict[str, object]) -> dict[str, int]:
    """Run the scrubber over each text field, return aggregate fire counts.

    *fields* maps a logical field name → value. Returns a dict of pattern
    name → total fire count across all fields. Empty when nothing fires (or
    when the scrubber lib is unavailable — see module docstring).

    A ``scrub()`` crash is contained per-field (logged + skipped) so a bug in
    the scrubber cannot take down every MCP write; this is fail-open, matching
    the unavailable-scrubber stance above.
    """
    if scrub is None:
        return {}
    totals: dict[str, int] = {}
    for value in fields.values():
        for text in _iter_strings(value):
            try:
                _, fires = scrub(text)
            except Exception as exc:  # noqa: BLE001 — scrubber bug must not crash writes
                print(
                    f"[write_scrubber] scrub() raised, field skipped (fail-open): {exc}",
                    file=sys.stderr,
                )
                continue
            for name, count in fires.items():
                totals[name] = totals.get(name, 0) + count
    return totals


def rejection_error(patterns: dict[str, int]) -> str:
    """Build the structured rejection payload as a JSON string.

    Carries ONLY pattern names + counts — never any payload value.
    """
    return json.dumps({"error": "secret_pattern_detected", "patterns": patterns})


def log_block_event(client, patterns: dict[str, int], *, write_path: str) -> None:
    """Best-effort: write an ``mcp_write_scrubber_block`` counter event.

    Records pattern names + counts only (privacy invariant). *write_path*
    identifies which handler blocked (``memory_store`` / ``record_decision``)
    so ``/learn`` can surface eager-pattern false positives. Repo slug is
    env-overridable so cross-repo (redrobot) blocks are attributed correctly.
    """
    try:
        client.table("events").insert(
            {
                "event_type": "mcp_write_scrubber_block",
                "severity": "low",
                "repo": os.environ.get("JARVIS_REPO_SLUG", "Osasuwu/jarvis"),
                "source": "mcp_memory",
                "title": f"Write blocked by secret scrubber ({write_path})",
                "payload": {"write_path": write_path, "patterns": patterns},
            }
        ).execute()
    except Exception as exc:  # noqa: BLE001 — logging must never block the rejection
        # Loud-but-non-fatal: a silent pass hides "why are there no block
        # events in the table?" during debugging.
        print(f"[write_scrubber] block-event log failed: {exc}", file=sys.stderr)


async def _log_block_event_async(client, patterns: dict[str, int], *, write_path: str) -> None:
    """Coroutine wrapper so the blocking insert can run as a detached task
    (mirrors ``_emit_recall_event``) instead of stalling the handler response."""
    log_block_event(client, patterns, write_path=write_path)


def _dispatch_block_log(client, patterns: dict[str, int], *, write_path: str) -> None:
    """Emit the block event off the hot path.

    Inside an async handler (a loop is running) the insert is scheduled as a
    detached task so the rejection returns immediately — the MCP event loop is
    never stalled on a 50–200 ms Supabase round-trip. Called synchronously with
    no running loop (direct unit-test calls) it falls back to an inline insert.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        log_block_event(client, patterns, write_path=write_path)
    else:
        asyncio.create_task(_log_block_event_async(client, patterns, write_path=write_path))


def check_write(client, fields: dict[str, object], *, write_path: str) -> str | None:
    """Tier-2 gate. Scan *fields*; on any **blocking** secret fire, emit the
    block event (off the event loop when one is running) and return the JSON
    rejection string. Return ``None`` to allow the write. Scrub-only patterns
    (see ``SCRUB_ONLY_PATTERNS``) are ignored — they are normalization
    concerns, not write-blocking leaks.
    """
    fires = scan_fields(fields)
    blocking = {k: v for k, v in fires.items() if k not in SCRUB_ONLY_PATTERNS}
    if not blocking:
        return None
    _dispatch_block_log(client, blocking, write_path=write_path)
    return rejection_error(blocking)

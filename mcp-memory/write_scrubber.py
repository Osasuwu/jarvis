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
"""

from __future__ import annotations

import json
import sys
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
    from lib.secret_scrubber import scrub  # type: ignore
except Exception:  # noqa: BLE001 — cross-repo (redrobot) may lack scripts/lib
    scrub = None  # type: ignore


# Patterns the scrubber detects but that must NOT hard-block an MCP write.
# `path_username` is a privacy *normalization* (scrub-and-keep), not a secret
# leak: ~26% of the live memory corpus (214/832) legitimately contains absolute
# user paths (`C:\Users\<name>\…`, `/Users/<name>/…`). Hard-rejecting those
# would violate AC#4 ("no false-positive blocks on real-world content") and
# break a quarter of all memory writes that reference a file path. Path
# normalization is the SessionEnd/Deriver lane's job (slice 6), not this
# Tier-2 secret-reject backstop. The genuine-secret patterns (API keys, env
# blocks) — 0 false positives in the corpus — remain blocking.
NON_BLOCKING_PATTERNS = frozenset({"path_username"})


def _iter_strings(value: object):
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
    """
    if scrub is None:
        return {}
    totals: dict[str, int] = {}
    for value in fields.values():
        for text in _iter_strings(value):
            _, fires = scrub(text)
            for name, count in fires.items():
                totals[name] = totals.get(name, 0) + count
    return totals


def rejection_error(patterns: dict[str, int]) -> str:
    """Build the structured rejection payload as a JSON string.

    Carries ONLY pattern names + counts — never any payload value.
    """
    return json.dumps({"error": "secret_pattern_detected", "patterns": patterns})


def log_block_event(client, patterns: dict[str, int], *, write_path: str) -> None:
    """Fire-and-forget: write an ``mcp_write_scrubber_block`` counter event.

    Records pattern names + counts only (privacy invariant). *write_path*
    identifies which handler blocked (``memory_store`` / ``record_decision``)
    so ``/learn`` can surface eager-pattern false positives.
    """
    try:
        client.table("events").insert(
            {
                "event_type": "mcp_write_scrubber_block",
                "severity": "low",
                "repo": "Osasuwu/jarvis",
                "source": "mcp_memory",
                "title": f"Write blocked by secret scrubber ({write_path})",
                "payload": {"write_path": write_path, "patterns": patterns},
            }
        ).execute()
    except Exception:
        # Logging is best-effort — never let it block the rejection itself.
        pass


def check_write(client, fields: dict[str, object], *, write_path: str) -> str | None:
    """Tier-2 gate. Scan *fields*; on any **blocking** secret fire, log the
    block event and return the JSON rejection string. Return ``None`` to allow
    the write. Non-blocking patterns (see ``NON_BLOCKING_PATTERNS``) are
    ignored — they are normalization concerns, not write-blocking leaks.
    """
    fires = scan_fields(fields)
    blocking = {k: v for k, v in fires.items() if k not in NON_BLOCKING_PATTERNS}
    if not blocking:
        return None
    log_block_event(client, blocking, write_path=write_path)
    return rejection_error(blocking)

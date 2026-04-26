"""Principal detection — who is running the current Claude session?

Hooks (PreToolUse and friends) read this to apply principal-aware policy.
See ``docs/security/agent-boundaries.md`` for the full permission matrix.

Detection chain (belt + suspenders, default-safe):

1. Explicit env ``JARVIS_PRINCIPAL`` — primary signal.
   Accepted values: ``live``, ``autonomous``, ``subagent``, ``supervised``.
2. Claude Code headless / non-interactive env vars → ``autonomous``.
3. ``not sys.stdin.isatty()`` → ``autonomous``.
4. Default → ``live``.

Default-safe property: forgetting to set ``JARVIS_PRINCIPAL`` in a future
autonomous launch path falls to ``autonomous`` (no human attached, narrow
permissions), never to ``live``. The dispatcher (Pillar 7 Sprint 2) and any
other future entry point inherit this safety net for free.

Tier model is shared with ``agents.safety`` (T0=AUTO, T1=OWNER_QUEUE,
T2=BLOCKED). This module covers the orthogonal "principal" axis; concrete
permission decisions are ``(action_tier, principal)`` lookups documented
in the agent-boundaries doc.
"""

from __future__ import annotations

import os
import sys
from typing import Literal

Principal = Literal["live", "autonomous", "subagent", "supervised"]

VALID_PRINCIPALS: frozenset[str] = frozenset(
    {"live", "autonomous", "subagent", "supervised"}
)

# Claude Code env vars that signal headless / non-interactive execution. The
# exact name has shifted across releases; treat any of them being set (to a
# truthy value) as a "no human attached" signal. This is the suspenders that
# back up an explicit ``JARVIS_PRINCIPAL`` going missing.
_HEADLESS_ENV_VARS: tuple[str, ...] = (
    "CLAUDE_CODE_NON_INTERACTIVE",
    "CLAUDE_CODE_HEADLESS",
    "CLAUDE_HEADLESS",
)


def _explicit_env() -> str | None:
    """Return the explicit principal from ``JARVIS_PRINCIPAL`` if valid, else None."""
    raw = os.environ.get("JARVIS_PRINCIPAL")
    if not raw:
        return None
    val = raw.strip().lower()
    return val if val in VALID_PRINCIPALS else None


def _is_headless_env() -> bool:
    """True if any Claude Code headless / non-interactive env var is truthy."""
    for name in _HEADLESS_ENV_VARS:
        v = os.environ.get(name)
        if v and v.strip() and v.strip().lower() not in {"0", "false", "no"}:
            return True
    return False


def _is_tty() -> bool:
    """Best-effort isatty() — returns False on detached stdin or errors."""
    try:
        return sys.stdin.isatty()
    except (ValueError, AttributeError, OSError):
        return False


def detect() -> Principal:
    """Return the active principal for the current process.

    Resolution order:
    1. ``JARVIS_PRINCIPAL`` env (explicit, primary)
    2. Headless env var → ``autonomous``
    3. Not a TTY → ``autonomous``
    4. Default → ``live``
    """
    explicit = _explicit_env()
    if explicit is not None:
        return explicit  # type: ignore[return-value]
    if _is_headless_env():
        return "autonomous"
    if not _is_tty():
        return "autonomous"
    return "live"


if __name__ == "__main__":
    # Ad-hoc inspection: ``python scripts/principal.py``
    print(detect())

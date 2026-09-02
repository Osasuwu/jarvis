"""Harness seam — one neutral core, N thin adapters (design: S7).

Jarvis runs on a *harness* (today Claude Code; OpenCode is the second adapter
planned in ``docs/design/harness-agnostic.md``). Anything that differs between
harnesses is owned here and nowhere else, so the rest of the codebase never
grows an ``if harness == "claude"`` branch.

Slice 1 (issue #1741) implements exactly one adapter method — :meth:`Harness.home`,
the agent home directory (``~/.claude``) that was previously recomputed inline,
by copy-paste, in five modules. Later slices add ``binary()``, ``spawn_argv()``,
``transcripts()`` and ``capabilities()``; they are intentionally absent from the
base contract until they are implemented and tested — a method on this class is
a method that works.

Resolution order (the single place harness identity is decided):

  1. explicit ``$JARVIS_HARNESS`` — selected by adapter name; an unknown value
     falls through rather than erroring;
  2. autodetect — the first registered adapter whose ``detect()`` is true;
  3. default — ``claude-code``.

An unset or unknown ``$JARVIS_HARNESS`` therefore always yields ``claude-code``
while it is the only adapter.
"""

from __future__ import annotations

import os
from pathlib import Path

from lib.harness.base import Harness
from lib.harness.claude_code import ClaudeCodeHarness

HARNESS_ENV = "JARVIS_HARNESS"
DEFAULT_HARNESS = "claude-code"

# Ordered adapter registry. Autodetect walks this in order and takes the first
# adapter whose ``detect()`` is true; ``$JARVIS_HARNESS`` selects by name.
# ceiling: single-entry tuple today; add adapters here (S6 opencode) as they land.
_ADAPTERS: tuple[type[Harness], ...] = (ClaudeCodeHarness,)
_BY_NAME: dict[str, type[Harness]] = {a.name: a for a in _ADAPTERS}


def resolve() -> Harness:
    """Return the active harness adapter per the documented resolution order."""
    explicit = os.environ.get(HARNESS_ENV)
    if explicit and explicit in _BY_NAME:
        return _BY_NAME[explicit]()
    for adapter in _ADAPTERS:
        if adapter.detect():
            return adapter()
    return _BY_NAME[DEFAULT_HARNESS]()


def current() -> Harness:
    """Alias for :func:`resolve` — the active harness adapter instance."""
    return resolve()


def home() -> Path:
    """Agent home directory for the active harness (e.g. ``~/.claude``).

    Honours the harness's own home override (for ``claude-code``,
    ``$JARVIS_CLAUDE_HOME``). Read at call time, so tests toggling the override
    env var see the change without reimporting.
    """
    return resolve().home()


__all__ = [
    "DEFAULT_HARNESS",
    "HARNESS_ENV",
    "ClaudeCodeHarness",
    "Harness",
    "current",
    "home",
    "resolve",
]

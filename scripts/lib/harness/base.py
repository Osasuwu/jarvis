"""Base harness contract — the neutral interface every adapter implements.

See ``docs/design/harness-agnostic.md`` §"The five adapter methods". Only
``home()`` is part of the contract in slice 1 (#1741); the other four methods
land in later slices and are deliberately not declared here yet, so the class
never advertises a capability that has no working implementation.
"""

from __future__ import annotations

from pathlib import Path


class Harness:
    """Identity + runtime capabilities of the harness Jarvis is running under.

    Subclasses are thin adapters: they map neutral Jarvis concepts onto one
    concrete harness. They carry no Jarvis logic of their own.
    """

    #: Stable adapter identifier, matched against ``$JARVIS_HARNESS`` and used
    #: as the registry key. Subclasses must override.
    name: str = ""

    def home(self) -> Path:
        """Agent home directory (e.g. ``~/.claude``, ``~/.config/opencode``)."""
        raise NotImplementedError

    @classmethod
    def detect(cls) -> bool:
        """True when this adapter's harness is the one currently running.

        Used only for autodetect (step 2 of resolution); an explicit
        ``$JARVIS_HARNESS`` bypasses it. Base default is ``False`` so a new
        adapter is never autodetected until it opts in.
        """
        return False

"""Claude Code harness adapter.

Implements :meth:`home` for the ``claude-code`` harness — the agent home is
``~/.claude`` unless ``$JARVIS_CLAUDE_HOME`` overrides it. This is the exact
resolution the five inline copies used before #1741; the override is preserved
verbatim (back-compat, not a rename).
"""

from __future__ import annotations

import os
from pathlib import Path

from lib.harness.base import Harness

#: Home override honoured by the claude-code adapter (unchanged from the inline
#: copies this seam replaces).
CLAUDE_HOME_OVERRIDE_ENV = "JARVIS_CLAUDE_HOME"


class ClaudeCodeHarness(Harness):
    name = "claude-code"

    def home(self) -> Path:
        override = os.environ.get(CLAUDE_HOME_OVERRIDE_ENV)
        if override:
            return Path(override).expanduser()
        return Path.home() / ".claude"

    @classmethod
    def detect(cls) -> bool:
        # Sole runtime today, so autodetect always resolves here. A competing
        # signal arrives with the second adapter (S6); until then this is the
        # default in practice as well as by declaration.
        return True

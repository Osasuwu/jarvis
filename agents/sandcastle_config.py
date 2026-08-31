"""Loader for the sandcastle slot ladder (#1119).

Attempt ceiling used to be a hardcoded ``MAX_ATTEMPTS`` constant in
``agents/orchestrator.py``. #1119 replaces it with a ladder-derived value:
the number of slots configured in ``config/sandcastle.yaml``, loaded here.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_REQUIRED_KEYS = ("slots",)


@dataclass(frozen=True)
class SandcastleConfig:
    slots: tuple[str, ...]


def load_sandcastle_config(path: Path) -> SandcastleConfig:
    """Load and validate the sandcastle slot-ladder config.

    Raises ``FileNotFoundError`` if ``path`` does not exist, ``ValueError``
    if the file is missing a required key.
    """
    if not path.exists():
        raise FileNotFoundError(f"sandcastle config not found: {path}")

    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}

    missing = [k for k in _REQUIRED_KEYS if k not in raw]
    if missing:
        raise ValueError(f"sandcastle config {path}: missing keys {missing}")

    return SandcastleConfig(slots=tuple(raw["slots"]))


def attempt_ceiling(config: SandcastleConfig) -> int:
    """Attempt ceiling derived from the ladder — one attempt per slot."""
    return len(config.slots)


@lru_cache(maxsize=1)
def default_attempt_ceiling() -> int:
    """Attempt ceiling from the repo's own ``config/sandcastle.yaml``."""
    config = load_sandcastle_config(Path(_REPO_ROOT) / "config" / "sandcastle.yaml")
    return attempt_ceiling(config)

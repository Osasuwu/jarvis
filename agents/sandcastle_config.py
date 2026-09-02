"""Loader for the sandcastle slot ladder (#1119).

Attempt ceiling used to be a hardcoded ``MAX_ATTEMPTS`` constant in
``agents/orchestrator.py``. #1119 replaces it with a ladder-derived value:
the number of slots configured in ``config/sandcastle.yaml``, loaded here.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_CONFIG_PATH = Path(_REPO_ROOT) / "config" / "sandcastle.yaml"

_REQUIRED_KEYS = ("slots",)

_DEFAULT_OPERATOR_SUBSTRATE = "worktree"

_DEFAULT_SWEEPER_RUNTIME_ROOT = ".sandcastle/runtime"


@dataclass(frozen=True)
class SweeperConfig:
    """Task sweeper tunables (#1122 AC11) — no sweeper literal on a code path."""

    run_timeout_hours: float = 4
    destructive_min_age_minutes: float = 10
    daemon_failure_threshold: int = 3
    docker_call_timeout_seconds: float = 30
    runtime_root: str = _DEFAULT_SWEEPER_RUNTIME_ROOT


@dataclass(frozen=True)
class SandcastleConfig:
    slots: tuple[str, ...]
    # Billing-key denylist (#1121) — single shared config source consumed by
    # BOTH .sandcastle/main.mts's subscription-mode guard and this repo's
    # Python spawn-env builder, not two independently-maintained checks
    # (decision 70f25333-b4f4-454e-903b-ab2d32b125c8).
    billing_key_denylist: tuple[str, ...] = ()
    # Per-row tier-aware quota gate (#1121, decision cc5f9c2c) — a throttled
    # row is skipped at drain time, never halts the drain.
    quota_gate: dict[str, Any] = field(default_factory=dict)
    # Default substrate for a row with no explicit substrate value (#1121,
    # decision c5e2e14a). Only "worktree" is routable this slice.
    operator_default_substrate: str = _DEFAULT_OPERATOR_SUBSTRATE
    # Task sweeper config (#1122 AC11).
    sweeper: SweeperConfig = field(default_factory=SweeperConfig)


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

    raw_sweeper = dict(raw.get("sweeper") or {})
    default_sweeper = SweeperConfig()
    sweeper = SweeperConfig(
        run_timeout_hours=raw_sweeper.get("run_timeout_hours", default_sweeper.run_timeout_hours),
        destructive_min_age_minutes=raw_sweeper.get(
            "destructive_min_age_minutes", default_sweeper.destructive_min_age_minutes
        ),
        daemon_failure_threshold=raw_sweeper.get(
            "daemon_failure_threshold", default_sweeper.daemon_failure_threshold
        ),
        docker_call_timeout_seconds=raw_sweeper.get(
            "docker_call_timeout_seconds", default_sweeper.docker_call_timeout_seconds
        ),
        runtime_root=raw_sweeper.get("runtime_root") or default_sweeper.runtime_root,
    )

    return SandcastleConfig(
        slots=tuple(raw["slots"]),
        billing_key_denylist=tuple(raw.get("billing_key_denylist") or ()),
        quota_gate=dict(raw.get("quota_gate") or {}),
        operator_default_substrate=raw.get("operator_default_substrate") or _DEFAULT_OPERATOR_SUBSTRATE,
        sweeper=sweeper,
    )


def attempt_ceiling(config: SandcastleConfig) -> int:
    """Attempt ceiling derived from the ladder — one attempt per slot."""
    return len(config.slots)


@lru_cache(maxsize=1)
def default_sandcastle_config() -> SandcastleConfig:
    """The repo's own ``config/sandcastle.yaml``, loaded once and cached."""
    return load_sandcastle_config(_CONFIG_PATH)


def default_attempt_ceiling() -> int:
    """Attempt ceiling from the repo's own ``config/sandcastle.yaml``."""
    return attempt_ceiling(default_sandcastle_config())


def default_billing_key_denylist() -> tuple[str, ...]:
    """Billing-key denylist from the repo's own ``config/sandcastle.yaml``."""
    return default_sandcastle_config().billing_key_denylist


def default_quota_gate() -> dict[str, Any]:
    """Quota-gate binding from the repo's own ``config/sandcastle.yaml``."""
    return default_sandcastle_config().quota_gate


def default_operator_default_substrate() -> str:
    """Operator default substrate from the repo's own ``config/sandcastle.yaml``."""
    return default_sandcastle_config().operator_default_substrate


def default_sweeper_config() -> SweeperConfig:
    """Sweeper config from the repo's own ``config/sandcastle.yaml``."""
    return default_sandcastle_config().sweeper

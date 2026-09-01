"""Supervisor launch adapter (#1121, plan step 6).

Builds the subprocess env for ``.sandcastle/main.mts`` (the sandcastle
supervisor, run via ``npm run sandcastle``) from a task_queue row, and
launches it. This replaces ``executor.spawn``'s bare ``claude -p`` for rows
routed onto the supervisor path — the routing decision itself is a separate
call site (plan step 8), not this module's job.

Two safety properties enforced while building the env:

- ``SUPABASE_KEY`` is validated by role (decision 94c55c7b,
  :mod:`agents.supabase_key_role``) before being forwarded — a service-role
  key never reaches a spawned container.
- Billing-override keys (decision 70f25333, ``config/sandcastle.yaml``'s
  ``billing_key_denylist``) are stripped from the env. ``main.mts`` itself
  refuses to start in subscription auth-mode if any denylisted key is
  present in its environment; stripping here keeps that guarantee even
  outside subscription mode instead of relying solely on the TS-side check.
"""

from __future__ import annotations

import logging
import os
import subprocess
from dataclasses import dataclass
from typing import Any, Callable

from agents.sandcastle_config import default_billing_key_denylist
from agents.supabase_key_role import SupabaseKeyRoleError, assert_supabase_key_is_anon
from agents.usage_probe import UsageProbe, read_usage

logger = logging.getLogger(__name__)

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

Launcher = Callable[..., "subprocess.Popen[Any]"]


@dataclass(frozen=True)
class SupervisorSpawnResult:
    """Duck-compatible with ``executor.SpawnResult`` — ``drain_tasks`` reads
    ``.proc`` and ``.throttled`` off whatever ``spawn`` returns."""

    proc: Any = None
    throttled: bool = False
    reason: str | None = None


def build_supervisor_env(
    row: dict[str, Any],
    *,
    task_id: str,
    lineage_key: str,
    attempt: int,
    base_env: dict[str, str] | None = None,
) -> dict[str, str]:
    """Build the env dict for a supervisor-path launch.

    Raises :class:`SupabaseKeyRoleError` if ``SUPABASE_KEY`` (read from
    ``base_env`` or the real process env) is not an anon-equivalent key.
    """
    source = base_env if base_env is not None else os.environ
    denylist = set(default_billing_key_denylist())
    env: dict[str, str] = {k: v for k, v in source.items() if k not in denylist}

    supabase_key = env.get("SUPABASE_KEY")
    if supabase_key:
        assert_supabase_key_is_anon(supabase_key)

    env["SANDCASTLE_TASK_ID"] = task_id
    env["SANDCASTLE_LINEAGE_KEY"] = lineage_key
    env["SANDCASTLE_ATTEMPT"] = str(attempt)
    env["SANDCASTLE_GOAL"] = str(row.get("goal") or "")
    target_repo = row.get("target_repo")
    if target_repo:
        env["SANDCASTLE_REPO"] = str(target_repo)
    return env


def launch_supervisor(
    row: dict[str, Any],
    *,
    task_id: str,
    lineage_key: str,
    attempt: int,
    popen: Launcher | None = None,
    probe: UsageProbe | None = None,
) -> SupervisorSpawnResult:
    """Build the env and launch the supervisor (``npm run sandcastle``).

    Refuses (returns a non-throttled result with no ``proc``) rather than
    raising when ``SUPABASE_KEY`` fails role validation — the caller
    (``default_supervisor_spawn``) treats a ``None`` proc as "did not spawn"
    the same way ``executor.spawn`` treats a throttled result.

    Re-probes quota per spawn, mirroring ``executor.spawn``'s AC4 backstop
    (decision behind commit 91db40f5): a throttled reading refuses the
    launch with ``throttled=True`` so the caller requeues the row instead of
    counting a phantom spawn. Without this, ``drain_tasks``'s once-per-drain
    preflight (``task_dispatch.py`` around the ``AC4 (#921)`` comment) is the
    only quota gate on this path, and a quota flip mid-drain would strand
    the row as ``running`` with no process.
    """
    reading = read_usage(probe=probe)
    if reading.near_exhaustion:
        logger.warning(
            "[sandcastle_supervisor] launch refused for task %s — quota near-exhaustion "
            "(used=%d/%d)",
            task_id,
            reading.used,
            reading.total,
        )
        return SupervisorSpawnResult(
            proc=None,
            throttled=True,
            reason=f"quota near-exhaustion: used {reading.used}/{reading.total}",
        )

    try:
        env = build_supervisor_env(row, task_id=task_id, lineage_key=lineage_key, attempt=attempt)
    except SupabaseKeyRoleError as exc:
        logger.error("[sandcastle_supervisor] refusing launch for task %s: %s", task_id, exc)
        return SupervisorSpawnResult(proc=None, reason=str(exc))

    spawn_fn = popen or subprocess.Popen
    proc = spawn_fn(
        ["npm", "run", "sandcastle"],
        env=env,
        cwd=_REPO_ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    logger.info(
        "[sandcastle_supervisor] launched (pid=%s) task_id=%s lineage_key=%s attempt=%d",
        getattr(proc, "pid", None),
        task_id,
        lineage_key,
        attempt,
    )
    return SupervisorSpawnResult(proc=proc)

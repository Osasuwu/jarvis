"""Fire-and-forget executor — spawns ``claude -p`` for a coding task.

Salvaged from ``agents/dispatcher.py`` (LangGraph dispatcher retired per
reactive-core resolution 2026-05-20). Plain functions, no graph framework.

End-to-end behavior:

- ``spawn(task_text)`` runs ``claude -p`` through the salvaged env guard
  (strips ``ANTHROPIC_API_KEY`` / ``ANTHROPIC_AUTH_TOKEN`` / ``CLAUDE_API_KEY``
  so the run bills the Claude Max subscription, never the API account) and
  ``_resolve_claude_binary`` (Windows path resolution).  After spawn the
  executor does nothing further — the loop is closed externally by GitHub
  workflows.

- ``safety.py`` (``classify`` / ``gate`` / ``idempotency_key`` / ``audit``)
  is preserved as-is.

The billing-trap is the load-bearing safety property: an autonomous spawn
must never inherit API-billing keys.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
from datetime import UTC, datetime
from typing import Any

from agents.scope_hash import _hash_scope_files  # re-export — see issue #773

logger = logging.getLogger(__name__)

# Env vars that must not reach the Claude subprocess. Keeping them here
# (not on a config surface) means a future Anthropic env name — likely
# shipped as a breaking rename — turns into a one-line edit rather than a
# billing incident.
_SENSITIVE_ENV_KEYS: frozenset[str] = frozenset(
    {
        "ANTHROPIC_API_KEY",
        "ANTHROPIC_AUTH_TOKEN",
        "CLAUDE_API_KEY",
    }
)

# Permission spec for the spawned ``claude -p`` session (#372, #378). Without
# these flags, headless Claude hangs waiting for approval that no operator
# can give. Design: ``acceptEdits`` auto-approves Write/Edit (matches
# executor's primary shape — "make the change"), plus a narrow allowlist
# of read-only and safely-namespaced tools that ``acceptEdits`` does not
# cover. Widen this list only with a design note; do NOT switch to
# ``bypassPermissions`` — that defeats the safety layering.
#
# Security rationale (#378):
# - Dropped: Bash(python:*) — arbitrary code escape hatch. If a task needs
#   to run a script, agent can invoke Edit + commit; CI tests for us.
# - Replaced: Bash(gh:*) with scoped read/create verbs only. Removed:
#   destructive verbs (merge --admin, repo delete, api DELETE).
_SPAWN_PERMISSION_MODE = "acceptEdits"
_SPAWN_ALLOWED_TOOLS = (
    "Read",
    "Glob",
    "Grep",
    "TodoWrite",
    "Bash(git:*)",
    "Bash(gh pr view:*)",
    "Bash(gh pr create:*)",
    "Bash(gh pr list:*)",
    "Bash(gh issue view:*)",
    "Bash(gh issue create:*)",
    "Bash(gh issue list:*)",
    "Bash(gh issue comment:*)",
    "Bash(gh api repos/*/issues:*)",
    "Bash(gh api repos/*/pulls:*)",
    "Bash(pytest:*)",
    "Bash(npm:*)",
)

# Documented Windows install locations to probe when neither override, env
# var, nor PATH lookup yields a binary. Templates expand against ``os.environ``
# so absent vars (e.g. running under a service account) are skipped silently.
# Order matters: official installer first, then common alt locations seen in
# the wild (``.local/bin/claude.exe``, npm shim, pipx).
_CLAUDE_DEFAULT_WINDOWS_PATHS: tuple[str, ...] = (
    r"{LOCALAPPDATA}\Programs\claude\claude.exe",
    r"{USERPROFILE}\.local\bin\claude.exe",
    r"{APPDATA}\npm\claude.exe",
)

# Default stderr log directory for spawned subprocesses. Per
# ``fire_and_forget_subprocess_capture_stderr``: fire-and-forget subprocesses
# MUST capture stderr to a file — DEVNULL hides production failures.
_STDERR_LOG_DIR = "logs/executor"


def _resolve_claude_binary(override: str | None = None) -> str:
    """Resolve the absolute path to the ``claude`` executable.

    Resolution chain — earlier sources win and are validated against the
    filesystem before being returned:

    1. ``override`` argument — for tests and programmatic callers that need
       to inject a known path.
    2. ``JARVIS_CLAUDE_BIN`` env var — operator override for unattended
       contexts (NSSM service, cron, CI) where PATH is sparse.
    3. :func:`shutil.which` — works in interactive shells where ``claude``
       is on the user PATH but breaks under ``LocalSystem`` (issue #385).
    4. Documented Windows install paths — covers official and common alt
       installs without forcing the operator to set an env var on every box.

    Raises :class:`FileNotFoundError` when nothing resolves to an existing
    file, with a message that lists each step that was tried.
    """
    if override:
        if os.path.exists(override):
            return override
        raise FileNotFoundError(
            f"claude binary override does not exist: {override!r}"
        )

    env_path = os.environ.get("JARVIS_CLAUDE_BIN")
    if env_path:
        if os.path.exists(env_path):
            return env_path
        raise FileNotFoundError(
            f"JARVIS_CLAUDE_BIN points to a missing file: {env_path!r}"
        )

    found = shutil.which("claude")
    if found:
        return found

    if os.name == "nt":
        for tmpl in _CLAUDE_DEFAULT_WINDOWS_PATHS:
            try:
                candidate = tmpl.format(**os.environ)
            except KeyError:
                continue
            if os.path.exists(candidate):
                return candidate

    tried = ["override arg", "JARVIS_CLAUDE_BIN", "shutil.which('claude')"]
    if os.name == "nt":
        tried.append(f"Windows defaults {_CLAUDE_DEFAULT_WINDOWS_PATHS}")
    raise FileNotFoundError(
        "claude binary not found. Tried: "
        + ", ".join(tried)
        + ". Set JARVIS_CLAUDE_BIN to the absolute path; under NSSM, "
        "'nssm set jarvis-scheduler AppEnvironmentExtra JARVIS_CLAUDE_BIN=...'."
    )


def _sanitize_env(env: dict[str, str] | None = None) -> dict[str, str]:
    """Return ``env`` (defaults to ``os.environ``) minus API-billing keys.

    Claude Max auth lives in the CLI's on-disk session (``~/.claude/``),
    not in an env var; the subprocess inherits it automatically when we
    don't poison the env with an API key.
    """
    source = env if env is not None else os.environ
    return {k: v for k, v in source.items() if k not in _SENSITIVE_ENV_KEYS}


def _now_iso() -> str:
    """ISO-8601 timestamp at UTC."""
    return datetime.now(UTC).isoformat()


def spawn(
    task_text: str,
    *,
    stderr_log_dir: str | None = None,
    popen: Any = None,  # noqa: ANN401 — injectable for tests
) -> subprocess.Popen[str]:
    """Fire-and-forget spawn of ``claude -p <task_text>``.

    Returns the :class:`subprocess.Popen` handle. The caller does not wait;
    the child session writes its own outcomes. Stderr is captured to a log
    file (never ``DEVNULL``) so silent failures are observable.

    ``popen`` is injectable so tests can capture the env dict without
    shelling out to a real ``claude`` binary; production wiring goes through
    :func:`subprocess.Popen` directly.
    """
    env = _sanitize_env()
    argv = [
        _resolve_claude_binary(),
        "-p",
        task_text,
        "--permission-mode",
        _SPAWN_PERMISSION_MODE,
        "--allowedTools",
        *_SPAWN_ALLOWED_TOOLS,
    ]

    # Capture stderr to file — fire-and-forget subprocesses must never use
    # DEVNULL (see ``fire_and_forget_subprocess_capture_stderr`` memory).
    log_dir = stderr_log_dir or _STDERR_LOG_DIR
    os.makedirs(log_dir, exist_ok=True)
    stderr_path = os.path.join(
        log_dir,
        f"spawn-{_now_iso().replace(':', '-')}.stderr.log",
    )
    stderr_file = open(stderr_path, "w", encoding="utf-8")  # noqa: SIM115 — closed below after Popen dup2

    spawn_fn = popen or subprocess.Popen
    proc = spawn_fn(
        argv,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=stderr_file,
        close_fds=True,
    )
    # Popen dup2'd the fd into the child; the parent handle is no longer
    # needed. Without this, a long-running scheduler leaks one fd per spawn.
    stderr_file.close()

    logger.info(
        "spawned claude -p (pid=%d) stderr=%s argv=%r",
        proc.pid,
        stderr_path,
        argv,
    )
    return proc

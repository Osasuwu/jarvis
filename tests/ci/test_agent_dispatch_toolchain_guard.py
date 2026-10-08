"""Guard for the dispatch worker's test toolchain (#1951).

The worker job used to run only checkout and ``claude-code-action``. Its allowlist
granted ``pytest`` and ``python -m pytest`` on a runner image with neither, so the
worker pushed code it had never run and could not do the mutation probe that
``docs/reference/test-quality.md`` asks for. The fix installs the ``pytest`` CI job's
environment before the agent starts and puts that environment on ``PATH``.

Three claims stay true after this PR, so each has a check:

* the worker installs what ``pytest.yml`` installs (parity between two artifacts that
  must agree -- the membership is read from ``pytest.yml``, not listed here);
* the environment is on ``PATH`` before the agent starts, so the existing
  ``pytest`` / ``python -m pytest`` grants resolve to it;
* the allowlist never gains a package installer: AC3 of #1951 says the install must not
  let the worker install packages of its own choosing, and ``uv run`` / ``uv sync``
  would install from a ``pyproject.toml`` / ``uv.lock`` the worker can edit.

What the CI cannot show is the live half: whether a ``$GITHUB_PATH`` entry reaches the
Bash tool of the process ``claude-code-action`` starts. That is checked on the first
dispatch run after merge (the ``Check the test toolchain`` step fails the job if the
environment is missing).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = REPO_ROOT / ".github" / "workflows"

AGENT_STEP = "Run unattended worker"
PATH_STEP = "Put the test environment on PATH"

# Closed set from #1951 AC3: a Bash grant whose command is, starts with, or is a prefix of
# one of these can install packages the worker chose.
INSTALLER_COMMANDS = (
    "pip",
    "pip3",
    "python -m pip",
    "python3 -m pip",
    "python -m ensurepip",
    "uv",
    "uvx",
    "pipx",
    "poetry",
    "conda",
    "npm",
    "npx",
    "apt",
    "apt-get",
)


def _load(name: str) -> dict:
    return yaml.safe_load((WORKFLOWS / name).read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def worker_steps() -> list[dict]:
    return _load("agent-dispatch.yml")["jobs"]["worker"]["steps"]


def _index(steps: list[dict], name: str) -> int:
    for i, step in enumerate(steps):
        if step.get("name") == name:
            return i
    pytest.fail(f"agent-dispatch.yml worker job has no {name!r} step")


def _allowed_tools(steps: list[dict]) -> list[str]:
    claude_args = steps[_index(steps, AGENT_STEP)]["with"]["claude_args"]
    match = re.search(r'^--allowed-tools\s+"([^"]*)"', claude_args, flags=re.MULTILINE)
    assert match, "worker step has no --allowed-tools line"
    return match.group(1).split(",")


def _signature(step: dict) -> tuple:
    return (step.get("name"), step.get("uses"), step.get("with"), step.get("run"))


def test_worker_installs_the_pytest_jobs_environment_before_the_agent(worker_steps):
    pytest_steps = _load("pytest.yml")["jobs"]["pytest"]["steps"]
    run_pytest = next(i for i, s in enumerate(pytest_steps) if s.get("name") == "Run pytest")
    install = [
        _signature(s)
        for s in pytest_steps[:run_pytest]
        if not str(s.get("uses", "")).startswith("actions/checkout@")
    ]
    # Guard before the comparison: an empty slice would make the loop below vacuous.
    assert install, "pytest.yml's pytest job has no install steps before `Run pytest`"
    assert any("uv sync" in (sig[3] or "") for sig in install)

    worker = [_signature(s) for s in worker_steps]
    agent = _index(worker_steps, AGENT_STEP)
    positions = [worker.index(sig) if sig in worker else -1 for sig in install]
    assert -1 not in positions, f"worker job lacks pytest.yml install step(s): {install}"
    assert positions == sorted(positions), "worker runs pytest.yml's install steps out of order"
    assert positions[-1] < agent, "the environment must be installed before the agent starts"


def test_worker_venv_is_on_path_before_the_agent(worker_steps):
    syncs = [i for i, s in enumerate(worker_steps) if "uv sync" in s.get("run", "")]
    assert syncs, "worker job never runs `uv sync`"
    sync = max(syncs)
    on_path = _index(worker_steps, PATH_STEP)
    agent = _index(worker_steps, AGENT_STEP)
    assert sync < on_path < agent
    assert '$GITHUB_WORKSPACE/.venv/bin" >> "$GITHUB_PATH"' in worker_steps[on_path]["run"]
    allowed = _allowed_tools(worker_steps)
    assert "Bash(python -m pytest:*)" in allowed
    assert "Bash(pytest:*)" in allowed


def test_allowlist_grants_no_package_installer(worker_steps):
    allowed = _allowed_tools(worker_steps)
    assert allowed, "worker allowlist parsed empty"
    offenders = []
    for entry in allowed:
        if entry in ("Bash", "Bash(*)"):
            offenders.append(entry)
            continue
        grant = re.fullmatch(r"Bash\((.*?)(?::\*)?\)", entry)
        if not grant:
            continue
        command = grant.group(1)
        for installer in INSTALLER_COMMANDS:
            a, b = f"{command} ", f"{installer} "
            if a.startswith(b) or b.startswith(a):
                offenders.append(entry)
    assert offenders == [], f"worker allowlist can install packages (#1951 AC3): {offenders}"

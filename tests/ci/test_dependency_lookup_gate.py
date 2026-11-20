"""The required check that goes red on a dependency missing from the index (#2143 AC1).

`docs/reference/failure-class-coverage.md` row 18 rests on one flag: the required `ruff` check
installs with `uv sync --locked`, which resolves `pyproject.toml` against the index and fails when
a named package is not there, or (with `exclude-newer` set) when only versions younger than the
minimum age satisfy it. Without `--locked`, or with `ruff` dropped from the required list, such a
PR goes green and the row claims a gate that no longer exists.
"""

from __future__ import annotations

import importlib.util
import shlex
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
RUFF_YML = REPO_ROOT / ".github" / "workflows" / "ruff.yml"
REPO_SETUP = REPO_ROOT / "docs" / "reference" / "github-repo-setup.md"

_spec = importlib.util.spec_from_file_location(
    "branch_protection_drift", REPO_ROOT / ".github" / "scripts" / "branch_protection_drift.py"
)
drift = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(drift)


def _uv_sync_argv(job):
    """argv of every `uv sync` command in the job's run steps."""
    found = []
    for step in job.get("steps", []):
        for line in str(step.get("run", "")).splitlines():
            argv = shlex.split(line)
            if argv[:2] == ["uv", "sync"]:
                found.append(argv)
    return found


def test_ruff_job_installs_with_uv_sync_locked():
    jobs = yaml.safe_load(RUFF_YML.read_text(encoding="utf-8"))["jobs"]
    syncs = _uv_sync_argv(jobs["ruff"])
    assert syncs, "the ruff job no longer runs `uv sync`"
    assert all("--locked" in argv for argv in syncs), syncs


def test_ruff_is_a_required_check():
    binding = drift.parse_documented_binding(REPO_SETUP.read_text(encoding="utf-8"))
    assert "ruff" in binding

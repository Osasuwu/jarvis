"""Every `run:` step in every workflow and composite action is fail-fast (#2142, row 6).

GitHub runs a `run:` step with no `shell:` as `bash -e {0}`: a failing command stops the step,
but a failure on the left of a pipe does not (`pytest | tee log` passes when pytest fails). An
explicit `shell: bash` runs as `bash --noprofile --norc -eo pipefail {0}`, which closes that
gap (GitHub docs, "jobs.<job_id>.steps[*].shell"). So a step is fail-fast when its effective
shell is `bash` (the step's `shell:`, else the job's `defaults.run.shell`, else the workflow's),
or when its script opens with `set -eo pipefail` / `set -euo pipefail` itself.

One test over the whole set, so a new workflow or step is covered the moment it is added.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS_DIR = REPO_ROOT / ".github" / "workflows"
ACTIONS_DIR = REPO_ROOT / ".github" / "actions"

# `set -eo pipefail`, `set -euo pipefail`, `set -o pipefail -e` style variants are not
# accepted: one spelling keeps the check readable, and both accepted forms are the ones in use.
_SET_LINE = re.compile(r"^set -eu?o pipefail\b")
FAIL_FAST_SHELLS = frozenset({"bash"})


def _opens_with_set(script: str) -> bool:
    for line in script.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        return bool(_SET_LINE.match(stripped))
    return False


def _shell(*scopes: object) -> str | None:
    """The first `defaults.run.shell` found, innermost scope first."""
    for scope in scopes:
        if isinstance(scope, dict):
            shell = ((scope.get("defaults") or {}).get("run") or {}).get("shell")
            if shell:
                return shell
    return None


def violations(doc: dict, name: str) -> tuple[int, list[str]]:
    """`(run steps seen, steps that are not fail-fast)` for one parsed workflow or action."""
    seen, bad = 0, []
    if "runs" in doc:  # a composite action: no defaults, every run step names its shell
        jobs = {"(action)": {"steps": (doc.get("runs") or {}).get("steps") or []}}
    else:
        jobs = doc.get("jobs") or {}
    for job_id, job in jobs.items():
        for i, step in enumerate(job.get("steps") or []):
            if "run" not in step:
                continue
            seen += 1
            shell = step.get("shell") or _shell(job, doc)
            if shell in FAIL_FAST_SHELLS or _opens_with_set(str(step["run"])):
                continue
            label = step.get("name") or step.get("id") or f"step {i}"
            bad.append(f"{name}: job {job_id}: {label} (shell: {shell or 'default bash -e'})")
    return seen, bad


def _files() -> list[Path]:
    workflows = [*WORKFLOWS_DIR.glob("*.yml"), *WORKFLOWS_DIR.glob("*.yaml")]
    actions = [*ACTIONS_DIR.glob("*/action.yml"), *ACTIONS_DIR.glob("*/action.yaml")]
    return sorted(workflows + actions)


def test_every_run_step_is_fail_fast():
    files = _files()
    assert files, "no workflow or action files found"
    seen, bad = 0, []
    for path in files:
        doc = yaml.load(path.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)
        n, found = violations(doc, str(path.relative_to(REPO_ROOT)).replace("\\", "/"))
        seen += n
        bad += found
    assert seen, "no `run:` steps found in any workflow — the walker is broken"
    assert bad == [], (
        "run steps without pipefail (add `defaults: run: shell: bash` to the workflow, "
        "`shell: bash` to the step, or open the script with `set -euo pipefail`):\n"
        + "\n".join(bad)
    )

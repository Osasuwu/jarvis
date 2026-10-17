"""Advisory: report when jarvis's lane pin is behind main (#2087).

jarvis's lane callers and the `risk-tier` job run the shared lane code at one pinned jarvis
commit. A fix to that code merges green (the tests load the in-tree files) but does not run
until someone bumps the pin. This lists the commits between the pin and HEAD that touch the
pinned code and emits one `::warning::` naming the pin and those commits. It never fails:
the signal is advisory, not a check anything waits on.

Run from a full-history checkout of the default branch:
    python3 .github/scripts/lane_pin_drift.py
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

# The workflow whose `risk-tier` job carries the pin; the lane callers name the same SHA
# (tests/ci/test_lane_distribution_guard.py holds them equal).
PIN_SOURCE = ".github/workflows/pr-body-check.yml"

# The code the pin runs: the shared lane workflows, the risk-tier action, the scripts they run,
# and what those import or read. Kept equal to lane-pin-drift.yml's `paths:` by a test.
PINNED_PATHS = (
    ".github/workflows/lane.yml",
    ".github/workflows/lane-watch.yml",
    ".github/workflows/lane-close.yml",
    ".github/actions/risk-tier/**",
    ".github/scripts/lane_*.py",
    ".github/scripts/risk_tier.py",
    ".github/scripts/github_client.py",
    "agents/plan_lock.py",
    "agents/plan_classifier.py",
    "agents/plan_review_config.py",
    "agents/path_policy.py",
    "config/plan_review.yaml",
)

_PIN = re.compile(r"Osasuwu/jarvis/\.github/actions/risk-tier@([0-9a-f]{40})")


def pin_from(text: str) -> str:
    """The pinned SHA in the `risk-tier` job of `text`."""
    found = set(_PIN.findall(text))
    if len(found) != 1:
        raise ValueError(f"expected one risk-tier pin, found {sorted(found)}")
    return found.pop()


def missing_commits(repo: Path, pin: str, head: str = "HEAD") -> list[str]:
    """`<short sha> <subject>` for each commit in pin..head touching PINNED_PATHS, newest first."""
    pathspecs = [f":(glob){p}" for p in PINNED_PATHS]
    out = subprocess.run(
        ["git", "-C", str(repo), "log", "--format=%h %s", f"{pin}..{head}", "--", *pathspecs],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return [line for line in out.splitlines() if line]


def report(pin: str, commits: list[str]) -> str:
    if not commits:
        return f"lane pin {pin[:12]} is current: no later main commit touches the pinned code."
    listed = "; ".join(commits)
    return (
        f"::warning title=Lane pin is stale::lane pin {pin[:12]} is {len(commits)} commit(s) behind "
        f"main on the pinned code: {listed}. Bump it (docs/reference/lane-host-setup.md -> "
        f"Bumping the pin)."
    )


def main() -> int:
    pin = pin_from((REPO_ROOT / PIN_SOURCE).read_text(encoding="utf-8"))
    commits = missing_commits(REPO_ROOT, pin)
    print(report(pin, commits))
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary and commits:
        with open(summary, "a", encoding="utf-8") as fh:
            fh.write(f"### Lane pin `{pin[:12]}` is stale\n\n")
            fh.writelines(f"- {c}\n" for c in commits)
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Advisory: report when jarvis's lane pin is behind main (#2087).

jarvis's lane callers and the `risk-tier` job run the shared lane code at one pinned jarvis
commit. A fix to that code merges green (the tests load the in-tree files) but does not run
until someone bumps the pin. This lists the commits between the pin and HEAD that touch the
pinned code and emits one `::warning::` naming the pin and those commits, plus a step summary
that says "stale" or "current". It never fails: a pin it cannot resolve is a warning too, since
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
# and what those import or read. Named file by file, so this script and its workflow (which the
# lane never runs) are not in it. lane-pin-drift.yml's `paths:` trigger holds these plus the
# pin-carrying caller files; tests/ci/test_lane_pin_drift.py holds both lists.
PINNED_PATHS = (
    ".github/workflows/lane.yml",
    ".github/workflows/lane-watch.yml",
    ".github/workflows/lane-close.yml",
    ".github/actions/risk-tier/**",
    ".github/scripts/lane_intake.py",
    ".github/scripts/lane_publish.py",
    ".github/scripts/lane_escalation.py",
    ".github/scripts/lane_ledger.py",
    ".github/scripts/risk_tier.py",
    ".github/scripts/github_client.py",
    "agents/__init__.py",
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


def _escape(data: str) -> str:
    """Workflow-command data encoding: the runner decodes %25, %0D and %0A."""
    return data.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def report(pin: str, commits: list[str]) -> str:
    if not commits:
        return f"lane pin {pin[:12]} is current: no later main commit touches the pinned code."
    listed = "; ".join(commits)
    return "::warning title=Lane pin is stale::" + _escape(
        f"lane pin {pin[:12]} is {len(commits)} commit(s) behind main on the pinned code: "
        f"{listed}. Bump it (docs/reference/lane-host-setup.md -> Bumping the pin)."
    )


def _summary(text: str) -> None:
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(text)


def main(repo: Path = REPO_ROOT) -> int:
    try:
        pin = pin_from((repo / PIN_SOURCE).read_text(encoding="utf-8"))
        commits = missing_commits(repo, pin)
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        detail = getattr(exc, "stderr", None) or str(exc)
        print(
            "::warning title=Lane pin drift check could not run::"
            + _escape(f"{type(exc).__name__}: {detail.strip()}")
        )
        _summary(f"### Lane pin drift check could not run\n\n{type(exc).__name__}: {detail}\n")
        return 0
    print(report(pin, commits))
    if commits:
        _summary(f"### Lane pin `{pin[:12]}` is stale\n\n" + "".join(f"- {c}\n" for c in commits))
    else:
        _summary(
            f"### Lane pin `{pin[:12]}` is current\n\nNo later main commit touches the pinned code.\n"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())

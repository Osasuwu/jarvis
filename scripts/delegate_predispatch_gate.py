"""Pre-dispatch gate for /dispatch and drain_tasks (issues #642, #931, #1099, #1085).

`check_issue` refuses to admit an issue unless it satisfies four readiness
conditions:

  1. has the `sandcastle` label
  2. has no `needs-*` label
  3. body contains a `## Acceptance criteria` heading (case-insensitive)
  4. body cites at least one decision UUID, OR carries the explicit
     `[no-decision]` marker for slices that legitimately have none (#1099 —
     pure-mechanical slices should not be forced to cite a synthetic UUID)

`check_issue` has two call sites, both still live:

  - `/dispatch`'s advisory gate, run once per issue before enqueue — a
    courtesy filter, not the enforcement authority (see dispatch/SKILL.md
    §Contract: advisory readiness gate).
  - `drain_tasks`'s mechanical re-check on a fresh issue fetch immediately
    before spawn (#1085 S2-3) — this is the actual enforcement authority,
    since the queue row may be stale relative to the issue by the time it's
    claimed.

`check_in_flight` additionally SKIPs an issue that already has in-flight work
(dispatch-dedup, #931): an open PR referencing it via a closing keyword or a
`<prefix>/<N>-` head branch, or a `feat/<N>-` branch with no open PR (stale —
owner attention). As of Slice 2 (#1085) this is a **legacy second-line check,
not the dedup mechanism**: the real per-issue dedup is now
`task_queue`'s partial unique index on `issue_number`
(`idx_task_queue_issue_number_active`, Slice 1, PR #1529) — a database-level
CAS enforced on every `enqueue()` call, not by an LLM correctly following
prose. `check_in_flight` still runs (at both call sites above) as a second-line
catch for pre-Slice-2 branch/PR-based in-flight work that has no queue row to
collide against; it is not expected to fire once Slice 2 is the only active
dispatch path. The branch-push claim `check_in_flight` used to gate against is
retired — nothing pushes a claim branch as an atomic dispatch step anymore.

The gate is invoked with a strict envelope on stdin (no bare-issue fallback —
a missing or malformed `issue` / `open_prs` / `open_branches` fails closed as
SKIP). Callers that only want the readiness check (e.g. /dispatch's advisory
gate) pass empty `open_prs`/`open_branches` lists, which makes
`check_in_flight` a structural no-op rather than omitting the envelope shape:

  {"issue": {...}, "open_prs": [{number, body, headRefName}, ...],
   "open_branches": ["feat/123-x", ...]}
    | python scripts/delegate_predispatch_gate.py

Exit codes: 0 ⇒ OK (dispatch), 1 ⇒ REFUSE (readiness failure),
2 ⇒ SKIP (in-flight or unverifiable evidence). Decision text is on stdout.

Notes:
  - This module does no network I/O — callers fetch PR/branch lists (with
    explicit pagination) and pass them in.
  - The closing-keyword body regex is convention-backed, not speculative: the
    `require-linked-issue` merge gate forces closing keywords into PR bodies,
    so a live PR for an issue is reliably detectable this way.
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass, field

_UUID_RE = re.compile(
    r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b",
    re.IGNORECASE,
)
_AC_HEADING_RE = re.compile(r"(?m)^##\s+acceptance\s+criteria\b", re.IGNORECASE)
_NO_DECISION_MARKER_RE = re.compile(r"\[no-decision\]", re.IGNORECASE)
_NEEDS_PREFIX = "needs-"
_REQUIRED_LABEL = "sandcastle"

_CLOSING_KEYWORD = r"(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)"


def _closing_ref_re(issue_number: int) -> re.Pattern[str]:
    return re.compile(rf"(?i)\b{_CLOSING_KEYWORD}\s+#{issue_number}(?!\d)")


def _pr_head_re(issue_number: int) -> re.Pattern[str]:
    return re.compile(rf"^[a-z]+/{issue_number}-")


def _claim_branch_re(issue_number: int) -> re.Pattern[str]:
    # ceiling: detects only the legacy pre-Slice-2 `feat/<N>-` branch-push claim
    # (retired as the dedup mechanism — see module docstring); kept as a
    # second-line stale-branch catch, not a live claim detector. No upgrade
    # path needed unless a new non-queue claim convention is introduced.
    return re.compile(rf"^feat/{issue_number}-")


@dataclass(frozen=True)
class InFlightResult:
    verdict: str  # "clear" | "live_pr" | "stale_branch"
    pointer: str = ""

    @property
    def clear(self) -> bool:
        return self.verdict == "clear"


def check_in_flight(
    issue_number: int,
    open_prs: list[dict],
    open_branches: list[str],
) -> InFlightResult:
    """Detect in-flight work for an issue from pre-fetched GitHub data.

    Pure function — callers fetch `open_prs` (dicts with `number`, `body`,
    `headRefName`) and `open_branches` (names) themselves; no network I/O here.
    A live PR beats a stale branch.
    """
    closing_ref = _closing_ref_re(issue_number)
    pr_head = _pr_head_re(issue_number)
    for pr in open_prs:
        if closing_ref.search(pr.get("body") or ""):
            return InFlightResult(
                "live_pr",
                f"open PR #{pr.get('number')} closes #{issue_number}",
            )
        if pr_head.match(pr.get("headRefName") or ""):
            return InFlightResult(
                "live_pr",
                f"open PR #{pr.get('number')} from branch {pr.get('headRefName')}",
            )

    claim_branch = _claim_branch_re(issue_number)
    for branch in open_branches:
        if claim_branch.match(branch):
            return InFlightResult(
                "stale_branch",
                f"branch {branch} exists with no open PR — owner attention",
            )

    return InFlightResult("clear")


@dataclass(frozen=True)
class GateResult:
    failures: tuple[str, ...] = field(default_factory=tuple)

    @property
    def allow(self) -> bool:
        return not self.failures

    @property
    def message(self) -> str:
        if self.allow:
            return "OK"
        return "REFUSE: " + "; ".join(self.failures)


def check_issue(issue: dict) -> GateResult:
    failures: list[str] = []

    label_names = {label.get("name", "") for label in (issue.get("labels") or [])}
    body = issue.get("body") or ""

    if _REQUIRED_LABEL not in label_names:
        failures.append(f"missing required label `{_REQUIRED_LABEL}`")

    needs = sorted(n for n in label_names if n.startswith(_NEEDS_PREFIX))
    if needs:
        failures.append(f"blocked by needs-* label(s): {', '.join(needs)}")

    if not _AC_HEADING_RE.search(body):
        failures.append("missing `## Acceptance criteria` section in body")

    if not _UUID_RE.search(body) and not _NO_DECISION_MARKER_RE.search(body):
        failures.append(
            "missing decision UUID reference in body (or `[no-decision]` marker)"
        )

    return GateResult(failures=tuple(failures))


def _validate_envelope(payload: object) -> tuple[dict, list[dict], list[str]] | str:
    """Return (issue, open_prs, open_branches) or a SKIP reason string."""
    if not isinstance(payload, dict):
        return "payload is not a JSON object"
    issue = payload.get("issue")
    if not isinstance(issue, dict):
        return "missing or malformed `issue` key"
    if not isinstance(issue.get("number"), int):
        return "missing or malformed `issue.number`"
    open_prs = payload.get("open_prs")
    if not isinstance(open_prs, list) or any(not isinstance(pr, dict) for pr in open_prs):
        return "missing or malformed `open_prs` (must be a list of objects)"
    open_branches = payload.get("open_branches")
    if not isinstance(open_branches, list) or any(
        not isinstance(b, str) for b in open_branches
    ):
        return "missing or malformed `open_branches` (must be a list of strings)"
    return issue, open_prs, open_branches


def main(argv: list[str] | None = None) -> int:
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(f"SKIP: unverifiable — stdin is not valid JSON ({exc.msg})")
        return 2

    validated = _validate_envelope(payload)
    if isinstance(validated, str):
        print(f"SKIP: unverifiable — {validated}")
        return 2
    issue, open_prs, open_branches = validated

    readiness = check_issue(issue)
    if not readiness.allow:
        print(readiness.message)
        return 1

    in_flight = check_in_flight(issue["number"], open_prs, open_branches)
    if not in_flight.clear:
        print(f"SKIP: {in_flight.pointer}")
        return 2

    print(readiness.message)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

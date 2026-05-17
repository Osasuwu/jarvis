"""Pre-dispatch gate for /delegate (issue #642).

Refuses to dispatch a sandcastle subagent unless the target GitHub issue
satisfies four readiness conditions:

  1. has the `sandcastle` label
  2. has no `needs-*` label
  3. body contains a `## Acceptance criteria` heading (case-insensitive)
  4. body cites at least one decision UUID

The gate is invoked from the /delegate skill prose. Usage:

  gh issue view <N> --repo <R> --json number,body,labels \\
    | python scripts/delegate_predispatch_gate.py

Exit code 0 ⇒ allow; exit code 1 ⇒ refuse. Decision text is on stdout.
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
_NEEDS_PREFIX = "needs-"
_REQUIRED_LABEL = "sandcastle"


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

    if not _UUID_RE.search(body):
        failures.append("missing decision UUID reference in body")

    return GateResult(failures=tuple(failures))


def main(argv: list[str] | None = None) -> int:
    payload = sys.stdin.read()
    issue = json.loads(payload)
    result = check_issue(issue)
    print(result.message)
    return 0 if result.allow else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

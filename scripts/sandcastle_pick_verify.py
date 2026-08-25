"""Pick-time verification wrapper for the sandcastle container (#1691 AC7).

Exit-code contract mirroring ``scripts/delegate_predispatch_gate.py``: the
container branches on the exit code, never on free-text interpretation of
stdout. No model judgement lives in this path — the script is a thin
stdin-JSON-in, exit-code-out shell around the pure
``agents.sandcastle_admission.verify_pick_time`` digest+age re-check.

Stdin envelope (strict — malformed input fails closed with SKIP/2):

    {"body": "<issue body>", "locked_at": "<ISO 8601 or null>",
     "max_age_days": <int, optional — defaults from config/plan_review.yaml>,
     "now": "<ISO 8601, optional — defaults to the current UTC time>"}

Exit codes: 0 = OK (pick honored), 1 = REFUSE (digest mismatch, malformed
plan, or lock age past the ceiling), 2 = SKIP (unverifiable — malformed
stdin). Message text is on stdout for operator/log visibility only; the
exit code is the contract.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agents.plan_review_config import load_plan_review_config
from agents.sandcastle_admission import verify_pick_time

_DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "plan_review.yaml"


def _parse_iso(value: str | None) -> datetime | None:
    if value is None:
        return None
    return datetime.fromisoformat(value)


def _default_max_age_days() -> int:
    return load_plan_review_config(_DEFAULT_CONFIG_PATH).lock_max_age_days


def main_from_payload(payload: dict) -> tuple[int, str]:
    body = payload.get("body", "")
    locked_at = _parse_iso(payload.get("locked_at"))
    now = _parse_iso(payload.get("now")) or datetime.now(timezone.utc)
    max_age_days = payload.get("max_age_days")
    if max_age_days is None:
        max_age_days = _default_max_age_days()

    ok, reason = verify_pick_time(body, locked_at, int(max_age_days), now)
    if ok:
        return 0, reason
    return 1, f"REFUSE: {reason}"


def main(argv: list[str] | None = None) -> int:
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(f"SKIP: unverifiable — stdin is not valid JSON ({exc.msg})")
        return 2

    if not isinstance(payload, dict):
        print("SKIP: unverifiable — payload is not a JSON object")
        return 2

    try:
        exit_code, message = main_from_payload(payload)
    except (ValueError, TypeError) as exc:
        print(f"SKIP: unverifiable — malformed payload ({exc})")
        return 2

    print(message)
    return exit_code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

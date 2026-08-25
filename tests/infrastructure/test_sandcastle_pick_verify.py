"""Tests for scripts/sandcastle_pick_verify.py (#1691 AC7).

Container-facing exit-code wrapper around
``agents.sandcastle_admission.verify_pick_time`` — the pick-time re-check
the sandcastle container runs before honoring a ``plan:locked`` label. No
model judgement in this path: the script parses stdin JSON, calls the pure
verification function, and exits 0 (OK) or 1 (REFUSE) — the caller branches
on the exit code, not on any free-text interpretation.
"""

from __future__ import annotations

import importlib
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
verify = importlib.import_module("sandcastle_pick_verify")

_LOCK = "3f5e1c2a9b7d4680e1f2a3b4c5d6e7f8"


def _plan_body(steps: tuple[str, ...]) -> str:
    from agents.plan_lock import hash_plan

    steps_text = "\n".join(f"- {step}" for step in steps)
    digest = hash_plan(steps_text)
    return f"## Plan\n{steps_text}\nlock: {digest}\n"


def _run(payload: dict) -> tuple[int, str]:
    exit_code = verify.main_from_payload(payload)
    return exit_code


def test_valid_fresh_lock_exits_ok():
    now = datetime(2026, 8, 25, tzinfo=timezone.utc)
    payload = {
        "body": _plan_body(("Step one",)),
        "locked_at": (now - timedelta(days=1)).isoformat(),
        "max_age_days": 14,
        "now": now.isoformat(),
    }
    code, message = _run(payload)
    assert code == 0
    assert "ok" in message.lower()


def test_stale_lock_exits_refuse():
    now = datetime(2026, 8, 25, tzinfo=timezone.utc)
    payload = {
        "body": _plan_body(("Step one",)),
        "locked_at": (now - timedelta(days=20)).isoformat(),
        "max_age_days": 14,
        "now": now.isoformat(),
    }
    code, message = _run(payload)
    assert code == 1
    assert "age" in message.lower()


def test_edited_body_exits_refuse():
    now = datetime(2026, 8, 25, tzinfo=timezone.utc)
    payload = {
        "body": "## Plan\n- Step one\nlock: deadbeef\n",
        "locked_at": None,
        "now": now.isoformat(),
    }
    code, message = _run(payload)
    assert code == 1
    assert "digest" in message.lower()


def test_malformed_plan_exits_refuse():
    now = datetime(2026, 8, 25, tzinfo=timezone.utc)
    payload = {"body": "no plan section here", "locked_at": None, "now": now.isoformat()}
    code, message = _run(payload)
    assert code == 1
    assert "malformed" in message.lower()


def test_missing_locked_at_is_digest_only_verdict():
    now = datetime(2026, 8, 25, tzinfo=timezone.utc)
    payload = {"body": _plan_body(("Step one",)), "locked_at": None, "now": now.isoformat()}
    code, message = _run(payload)
    assert code == 0


def test_missing_max_age_days_defaults_from_config():
    now = datetime(2026, 8, 25, tzinfo=timezone.utc)
    payload = {
        "body": _plan_body(("Step one",)),
        "locked_at": (now - timedelta(days=13)).isoformat(),
        "now": now.isoformat(),
    }
    code, _ = _run(payload)
    assert code == 0


def test_malformed_stdin_json_fails_closed():
    exit_code, stdout = _invoke_main_with_stdin("not json")
    assert exit_code == 2
    assert "REFUSE" in stdout or "SKIP" in stdout or "malformed" in stdout.lower()


def _invoke_main_with_stdin(raw: str) -> tuple[int, str]:
    import io

    old_stdin = sys.stdin
    old_stdout = sys.stdout
    sys.stdin = io.StringIO(raw)
    sys.stdout = io.StringIO()
    try:
        exit_code = verify.main([])
        return exit_code, sys.stdout.getvalue()
    finally:
        sys.stdin = old_stdin
        sys.stdout = old_stdout

"""Unit tests for scripts/deriver-sessionend.py — the Stop-hook Deriver entry.

Regression coverage for #1558's code-review finding: ``derive_owner_self_pass``
(#1556) was defined in ``deriver/pipeline.py`` but never called from this
script, the actual SessionEnd/Stop hook registered in
``.claude-userlevel/settings.json`` — so the feature never fired outside
tests/smoke. These tests pin that ``main()`` invokes *both* passes so the
gap can't silently reopen.

Hyphen in filename → import via spec_from_file_location (repo convention,
see tests/memory/test_deriver_accumulator.py). Loading under a name other
than ``__main__`` means the module's venv re-exec bootstrap guard never
fires on import.
"""

from __future__ import annotations

import importlib.util
import io
import json
from pathlib import Path
from uuid import uuid4

import pytest

SCRIPT_PATH = Path(__file__).resolve().parent.parent.parent / "scripts" / "deriver-sessionend.py"

spec = importlib.util.spec_from_file_location("deriver_sessionend", SCRIPT_PATH)
assert spec and spec.loader
sessionend = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sessionend)


@pytest.fixture()
def hook_input(monkeypatch):
    payload = json.dumps({"session_id": "sess-1234", "cwd": "/home/user/GitHub/jarvis"})
    monkeypatch.setattr("sys.stdin", io.StringIO(payload))
    monkeypatch.setattr("sys.stdin.isatty", lambda: False, raising=False)
    return payload


def test_main_calls_both_default_and_owner_self_passes(monkeypatch, hook_input):
    calls = []

    def fake_default(session_id, *, project_hash):
        calls.append(("default", session_id, project_hash))
        return [uuid4()]

    def fake_owner_self(session_id, *, project_hash):
        calls.append(("owner-self", session_id, project_hash))
        return [uuid4()]

    monkeypatch.setattr(sessionend, "derive_from_session", fake_default)
    monkeypatch.setattr(sessionend, "derive_owner_self_pass", fake_owner_self)

    assert sessionend.main() == 0
    assert [c[0] for c in calls] == ["default", "owner-self"]
    assert all(c[1] == "sess-1234" for c in calls)


def test_owner_self_pass_failure_does_not_block_default_pass_or_exit(monkeypatch, hook_input):
    calls = []

    def fake_default(session_id, *, project_hash):
        calls.append("default")
        return []

    def fake_owner_self(session_id, *, project_hash):
        raise RuntimeError("boom")

    monkeypatch.setattr(sessionend, "derive_from_session", fake_default)
    monkeypatch.setattr(sessionend, "derive_owner_self_pass", fake_owner_self)

    assert sessionend.main() == 0
    assert calls == ["default"]


def test_default_pass_failure_does_not_block_owner_self_pass(monkeypatch, hook_input):
    calls = []

    def fake_default(session_id, *, project_hash):
        raise RuntimeError("boom")

    def fake_owner_self(session_id, *, project_hash):
        calls.append("owner-self")
        return []

    monkeypatch.setattr(sessionend, "derive_from_session", fake_default)
    monkeypatch.setattr(sessionend, "derive_owner_self_pass", fake_owner_self)

    assert sessionend.main() == 0
    assert calls == ["owner-self"]

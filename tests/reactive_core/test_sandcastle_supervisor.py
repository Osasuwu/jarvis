"""Tests for agents/sandcastle_supervisor.py (#1121 plan step 6)."""

from __future__ import annotations

import base64
import json

import pytest

from agents.sandcastle_supervisor import (
    SupervisorSpawnResult,
    build_supervisor_env,
    launch_supervisor,
)
from agents.supabase_key_role import SupabaseKeyRoleError


def _fake_jwt(role: str) -> str:
    def b64url(obj: dict) -> str:
        return base64.urlsafe_b64encode(json.dumps(obj).encode()).rstrip(b"=").decode()

    return f"{b64url({'alg': 'HS256'})}.{b64url({'role': role})}.sig"


ANON_JWT = _fake_jwt("anon")
SERVICE_ROLE_JWT = _fake_jwt("service_role")


class TestBuildSupervisorEnv:
    def test_injects_task_lineage_attempt_goal(self):
        env = build_supervisor_env(
            {"goal": "do the thing", "target_repo": "Osasuwu/jarvis"},
            task_id="t1",
            lineage_key="lineage-abc",
            attempt=2,
            base_env={},
        )
        assert env["SANDCASTLE_TASK_ID"] == "t1"
        assert env["SANDCASTLE_LINEAGE_KEY"] == "lineage-abc"
        assert env["SANDCASTLE_ATTEMPT"] == "2"
        assert env["SANDCASTLE_GOAL"] == "do the thing"
        assert env["SANDCASTLE_REPO"] == "Osasuwu/jarvis"

    def test_omits_repo_when_row_has_none(self):
        env = build_supervisor_env(
            {"goal": "g"}, task_id="t1", lineage_key="l", attempt=1, base_env={}
        )
        assert "SANDCASTLE_REPO" not in env

    def test_strips_billing_denylist_keys(self):
        base_env = {"ANTHROPIC_API_KEY": "sk-live-x", "SOME_OTHER_VAR": "keep-me"}
        env = build_supervisor_env(
            {"goal": "g"}, task_id="t1", lineage_key="l", attempt=1, base_env=base_env
        )
        assert "ANTHROPIC_API_KEY" not in env
        assert env["SOME_OTHER_VAR"] == "keep-me"

    def test_accepts_anon_supabase_key(self):
        env = build_supervisor_env(
            {"goal": "g"},
            task_id="t1",
            lineage_key="l",
            attempt=1,
            base_env={"SUPABASE_KEY": ANON_JWT},
        )
        assert env["SUPABASE_KEY"] == ANON_JWT

    def test_rejects_service_role_supabase_key(self):
        with pytest.raises(SupabaseKeyRoleError):
            build_supervisor_env(
                {"goal": "g"},
                task_id="t1",
                lineage_key="l",
                attempt=1,
                base_env={"SUPABASE_KEY": SERVICE_ROLE_JWT},
            )


class TestLaunchSupervisor:
    def test_launches_npm_run_sandcastle_with_built_env(self, monkeypatch):
        # SUPABASE_KEY read from the real process env (build_supervisor_env's
        # os.environ fallback) must not leak from whatever the runner has set —
        # pin it to a known-good anon key so this test is deterministic
        # regardless of ambient environment (was flaky/CI-only-failing before).
        monkeypatch.setenv("SUPABASE_KEY", ANON_JWT)
        captured = {}

        class FakeProc:
            pid = 4242

        def fake_popen(argv, **kwargs):
            captured["argv"] = argv
            captured["kwargs"] = kwargs
            return FakeProc()

        result = launch_supervisor(
            {"goal": "do it", "target_repo": "Osasuwu/jarvis"},
            task_id="t1",
            lineage_key="l1",
            attempt=1,
            popen=fake_popen,
        )

        assert isinstance(result, SupervisorSpawnResult)
        assert result.proc is not None
        assert result.proc.pid == 4242
        assert result.throttled is False
        assert captured["argv"] == ["npm", "run", "sandcastle"]
        env = captured["kwargs"]["env"]
        assert env["SANDCASTLE_TASK_ID"] == "t1"
        assert env["SANDCASTLE_GOAL"] == "do it"

    def test_refuses_without_raising_on_bad_supabase_key(self, monkeypatch):
        monkeypatch.setenv("SUPABASE_KEY", SERVICE_ROLE_JWT)

        def fake_popen(argv, **kwargs):
            raise AssertionError("must not launch when SUPABASE_KEY fails role validation")

        result = launch_supervisor(
            {"goal": "g"},
            task_id="t1",
            lineage_key="l",
            attempt=1,
            popen=fake_popen,
        )

        assert result.proc is None
        assert result.throttled is False
        assert result.reason is not None

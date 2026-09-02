"""Tests for agents/sandcastle_supervisor.py (#1121 plan step 6)."""

from __future__ import annotations

import base64
import json
import re
from datetime import UTC, datetime, timedelta

import pytest

from agents.sandcastle_supervisor import (
    SupervisorSpawnResult,
    build_supervisor_env,
    launch_supervisor,
)
from agents.supabase_key_role import SupabaseKeyRoleError
from agents.usage_probe import UsageReading


def _fake_jwt(role: str) -> str:
    def b64url(obj: dict) -> str:
        return base64.urlsafe_b64encode(json.dumps(obj).encode()).rstrip(b"=").decode()

    return f"{b64url({'alg': 'HS256'})}.{b64url({'role': role})}.sig"


ANON_JWT = _fake_jwt("anon")
SERVICE_ROLE_JWT = _fake_jwt("service_role")


class _FixedProbe:
    """Probe stub returning a fixed ``UsageReading`` (mirrors
    ``test_agents_executor.py``'s ``_FixedProbe``)."""

    def __init__(self, reading: UsageReading) -> None:
        self._reading = reading

    def read(self) -> UsageReading:
        return self._reading


def _exhausted_reading() -> UsageReading:
    return UsageReading(
        limit_window=timedelta(hours=5),
        used=95,
        total=100,
        reset_at=datetime.now(UTC),
        near_exhaustion=True,
    )


def _healthy_reading() -> UsageReading:
    return UsageReading(
        limit_window=timedelta(hours=5),
        used=10,
        total=100,
        reset_at=datetime.now(UTC),
        near_exhaustion=False,
    )


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

    # -- #1122 AC2 -----------------------------------------------------

    def test_run_id_defaults_to_bare_task_id(self):
        env = build_supervisor_env(
            {"goal": "do the thing"}, task_id="t1", lineage_key="l", attempt=1, base_env={}
        )
        assert env["SANDCASTLE_RUN_ID"] == "t1"

    def test_run_id_extracted_from_branch_directive(self):
        env = build_supervisor_env(
            {"goal": "Re-drive (attempt 2): do it\n\n(branch=task/root-42)"},
            task_id="t99",
            lineage_key="l",
            attempt=2,
            base_env={},
        )
        assert env["SANDCASTLE_RUN_ID"] == "root-42"

    def test_run_id_ignores_non_task_prefixed_branch_directive(self):
        # Only a literal `task/`-prefixed directive is a run-id source; any
        # other (branch=...) form falls back to the bare task_id.
        env = build_supervisor_env(
            {"goal": "g\n\n(branch=feature/x)"}, task_id="t1", lineage_key="l", attempt=1, base_env={}
        )
        assert env["SANDCASTLE_RUN_ID"] == "t1"

    def test_result_file_keyed_by_task_id_and_attempt(self):
        env = build_supervisor_env(
            {"goal": "g"},
            task_id="t7",
            lineage_key="l",
            attempt=3,
            base_env={},
            runtime_root="/tmp/runtime",
        )
        assert env["SANDCASTLE_RESULT_FILE"] == "/tmp/runtime/t7-a3/result.json"

    def test_result_file_defaults_runtime_root_from_config(self):
        env = build_supervisor_env(
            {"goal": "g"}, task_id="t7", lineage_key="l", attempt=1, base_env={}
        )
        assert env["SANDCASTLE_RESULT_FILE"] == ".sandcastle/runtime/t7-a1/result.json"

    def test_pinned_branch_matches_pr_evidence_head_fresh_shape(self):
        # main.mts pins task/<runId> verbatim (main.mts:319); pr_evidence's
        # ensure_pr_closing_ref derives the evidence head via its own regex
        # (agents/pr_evidence.py:276-277) — for a fresh-shape goal (no
        # existing directive) both must land on task/<task_id>.
        env = build_supervisor_env(
            {"goal": "implement the thing"}, task_id="t5", lineage_key="l", attempt=1, base_env={}
        )
        pinned_branch = f"task/{env['SANDCASTLE_RUN_ID']}"

        goal = "implement the thing"
        evidence_match = re.search(r"\(branch=([^)]+)\)", goal)
        evidence_head = evidence_match.group(1).strip() if evidence_match else f"task/t5"
        assert pinned_branch == evidence_head

    def test_pinned_branch_matches_pr_evidence_head_redrive_shape(self):
        goal = "Re-drive (attempt 2): implement the thing\n\n(branch=task/t5)"
        env = build_supervisor_env(
            {"goal": goal}, task_id="t5-redrive", lineage_key="l", attempt=2, base_env={}
        )
        pinned_branch = f"task/{env['SANDCASTLE_RUN_ID']}"

        evidence_match = re.search(r"\(branch=([^)]+)\)", goal)
        evidence_head = evidence_match.group(1).strip() if evidence_match else "task/t5-redrive"
        assert pinned_branch == evidence_head


class TestLaunchSupervisor:
    def test_launches_npm_run_sandcastle_with_built_env(self, monkeypatch):
        # SUPABASE_KEY read from the real process env (build_supervisor_env's
        # os.environ fallback) must not leak from whatever the runner has set —
        # pin it to a known-good anon key so this test is deterministic
        # regardless of ambient environment (was flaky/CI-only-failing before).
        monkeypatch.setenv("SUPABASE_KEY", ANON_JWT)
        monkeypatch.setattr("agents.sandcastle_supervisor.shutil.which", lambda cmd: "npm.cmd")
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
            probe=_FixedProbe(_healthy_reading()),
        )

        assert isinstance(result, SupervisorSpawnResult)
        assert result.proc is not None
        assert result.proc.pid == 4242
        assert result.throttled is False
        # npm resolved via shutil.which (not a bare "npm") -- avoids WinError 2
        # on Windows, where npm is npm.cmd and Popen(shell=False) doesn't
        # search PATHEXT for extensionless names.
        assert captured["argv"] == ["npm.cmd", "run", "sandcastle"]
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
            probe=_FixedProbe(_healthy_reading()),
        )

        assert result.proc is None
        assert result.throttled is False
        assert result.reason is not None

    def test_refuses_without_launching_when_quota_near_exhaustion(self, monkeypatch):
        monkeypatch.setenv("SUPABASE_KEY", ANON_JWT)

        def fake_popen(argv, **kwargs):
            raise AssertionError("must not launch when quota is near-exhaustion")

        result = launch_supervisor(
            {"goal": "g"},
            task_id="t1",
            lineage_key="l",
            attempt=1,
            popen=fake_popen,
            probe=_FixedProbe(_exhausted_reading()),
        )

        assert result.proc is None
        assert result.throttled is True
        assert result.reason is not None

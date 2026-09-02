"""Tests for agents/sandcastle_config.py's slot-ladder loader (#1119).

attempt_ceiling() is derived from the ladder length (config/sandcastle.yaml's
slots: list) rather than a hardcoded MAX_ATTEMPTS constant, per decision
9f357110-8a9a-4992-b9ec-780c07d96ecc.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from agents.sandcastle_config import (
    SandcastleConfig,
    SweeperConfig,
    attempt_ceiling,
    default_attempt_ceiling,
    default_billing_key_denylist,
    default_operator_default_substrate,
    default_quota_gate,
    default_sweeper_config,
    load_sandcastle_config,
)


class TestLoadSandcastleConfig:
    def test_loads_slots_list(self, tmp_path: Path) -> None:
        config_path = tmp_path / "sandcastle.yaml"
        config_path.write_text("slots: [\"slot-1\", \"slot-2\", \"slot-3\"]\n", encoding="utf-8")

        config = load_sandcastle_config(config_path)

        assert config == SandcastleConfig(slots=("slot-1", "slot-2", "slot-3"))

    def test_missing_slots_key_raises_value_error_naming_key(self, tmp_path: Path) -> None:
        config_path = tmp_path / "sandcastle.yaml"
        config_path.write_text("other_key: 1\n", encoding="utf-8")

        with pytest.raises(ValueError, match="slots"):
            load_sandcastle_config(config_path)

    def test_missing_sweeper_block_uses_defaults(self, tmp_path: Path) -> None:
        config_path = tmp_path / "sandcastle.yaml"
        config_path.write_text('slots: ["slot-1"]\n', encoding="utf-8")

        config = load_sandcastle_config(config_path)

        assert config.sweeper == SweeperConfig()

    def test_loads_sweeper_block(self, tmp_path: Path) -> None:
        config_path = tmp_path / "sandcastle.yaml"
        config_path.write_text(
            "slots: [\"slot-1\"]\n"
            "sweeper:\n"
            "  run_timeout_hours: 2\n"
            "  destructive_min_age_minutes: 5\n"
            "  daemon_failure_threshold: 7\n"
            "  docker_call_timeout_seconds: 15\n"
            "  runtime_root: /var/run/sandcastle\n",
            encoding="utf-8",
        )

        config = load_sandcastle_config(config_path)

        assert config.sweeper == SweeperConfig(
            run_timeout_hours=2,
            destructive_min_age_minutes=5,
            daemon_failure_threshold=7,
            docker_call_timeout_seconds=15,
            runtime_root="/var/run/sandcastle",
        )


class TestDefaultSweeperConfig:
    def test_default_sweeper_config_matches_repo_yaml(self) -> None:
        config = default_sweeper_config()
        assert config.run_timeout_hours == 4
        assert config.destructive_min_age_minutes == 10
        assert config.daemon_failure_threshold == 3
        assert config.docker_call_timeout_seconds == 30
        assert config.runtime_root == ".sandcastle/runtime"

    def test_missing_file_raises_file_not_found_error(self, tmp_path: Path) -> None:
        missing_path = tmp_path / "does-not-exist.yaml"

        with pytest.raises(FileNotFoundError):
            load_sandcastle_config(missing_path)


class TestAttemptCeiling:
    def test_equals_slot_count(self) -> None:
        config = SandcastleConfig(slots=("slot-1", "slot-2"))

        assert attempt_ceiling(config) == 2

    def test_single_slot_ceiling_is_one(self) -> None:
        config = SandcastleConfig(slots=("slot-1",))

        assert attempt_ceiling(config) == 1


class TestDefaultAttemptCeiling:
    def test_reads_repo_config_and_matches_slot_count(self) -> None:
        config = load_sandcastle_config(
            Path(__file__).resolve().parent.parent.parent / "config" / "sandcastle.yaml"
        )

        assert default_attempt_ceiling() == len(config.slots)


class TestBillingKeyDenylist:
    """Single shared config source consumed by both TS and Python spawn paths
    (decision 70f25333, #1121) — asserted against the repo's own config here so
    a drift between the yaml and the loader's defaults is caught immediately.
    """

    def test_loads_denylist_list(self, tmp_path: Path) -> None:
        config_path = tmp_path / "sandcastle.yaml"
        config_path.write_text(
            'slots: ["slot-1"]\nbilling_key_denylist: ["ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN"]\n',
            encoding="utf-8",
        )

        config = load_sandcastle_config(config_path)

        assert config.billing_key_denylist == ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN")

    def test_absent_denylist_defaults_to_empty_tuple(self, tmp_path: Path) -> None:
        config_path = tmp_path / "sandcastle.yaml"
        config_path.write_text('slots: ["slot-1"]\n', encoding="utf-8")

        config = load_sandcastle_config(config_path)

        assert config.billing_key_denylist == ()

    def test_default_billing_key_denylist_reads_repo_config(self) -> None:
        config = load_sandcastle_config(
            Path(__file__).resolve().parent.parent.parent / "config" / "sandcastle.yaml"
        )

        assert default_billing_key_denylist() == config.billing_key_denylist
        # The repo's own config must actually carry a non-empty denylist —
        # an empty list here would silently disable the billing guard.
        assert "ANTHROPIC_API_KEY" in default_billing_key_denylist()


class TestQuotaGate:
    def test_loads_quota_gate_mapping(self, tmp_path: Path) -> None:
        config_path = tmp_path / "sandcastle.yaml"
        config_path.write_text('slots: ["slot-1"]\nquota_gate:\n  enabled: true\n', encoding="utf-8")

        config = load_sandcastle_config(config_path)

        assert config.quota_gate == {"enabled": True}

    def test_absent_quota_gate_defaults_to_empty_dict(self, tmp_path: Path) -> None:
        config_path = tmp_path / "sandcastle.yaml"
        config_path.write_text('slots: ["slot-1"]\n', encoding="utf-8")

        config = load_sandcastle_config(config_path)

        assert config.quota_gate == {}

    def test_default_quota_gate_reads_repo_config(self) -> None:
        assert default_quota_gate() == {"enabled": True}


class TestOperatorDefaultSubstrate:
    def test_loads_operator_default_substrate(self, tmp_path: Path) -> None:
        config_path = tmp_path / "sandcastle.yaml"
        config_path.write_text('slots: ["slot-1"]\noperator_default_substrate: worktree\n', encoding="utf-8")

        config = load_sandcastle_config(config_path)

        assert config.operator_default_substrate == "worktree"

    def test_absent_operator_default_substrate_defaults_to_worktree(self, tmp_path: Path) -> None:
        config_path = tmp_path / "sandcastle.yaml"
        config_path.write_text('slots: ["slot-1"]\n', encoding="utf-8")

        config = load_sandcastle_config(config_path)

        assert config.operator_default_substrate == "worktree"

    def test_default_operator_default_substrate_reads_repo_config(self) -> None:
        assert default_operator_default_substrate() == "worktree"

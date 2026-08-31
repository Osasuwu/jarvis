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
    attempt_ceiling,
    default_attempt_ceiling,
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

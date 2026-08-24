"""Tests for agents.plan_review_config — the single classification artifact
loader for issue #1685 (class-2 thresholds + class-3 criteria, one config).
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

import fnmatch

from agents.plan_review_config import load_plan_review_config

_REPO_CONFIG = Path(__file__).resolve().parents[2] / "config" / "plan_review.yaml"


def test_loads_repo_config() -> None:
    """The committed config/plan_review.yaml loads without error."""
    cfg = load_plan_review_config(_REPO_CONFIG)
    assert cfg.class_2.churn_threshold > 0
    assert cfg.class_2.min_prod_areas > 0
    assert cfg.class_2.shared_surface_globs
    assert cfg.class_3.mechanical_criteria
    assert cfg.models.planner
    assert cfg.models.critic


def test_repo_config_covers_supabase_as_a_shared_surface() -> None:
    """docs/context/invariants.md: 'Supabase schema are shared surfaces —
    consumers sit outside this repo ... breakage is invisible from inside
    it.' A Supabase migration path must trip a shared_surface_globs match,
    same as mcp-memory/** (#1685 review finding: the glob list omitted
    supabase/** entirely, so a real supabase/migrations/*.sql change fell
    through class-2 classification unnoticed)."""
    cfg = load_plan_review_config(_REPO_CONFIG)
    sample_path = "supabase/migrations/20260415082814_create_credential_registry.sql"
    assert any(fnmatch.fnmatch(sample_path, glob) for glob in cfg.class_2.shared_surface_globs)


def test_thresholds_are_read_from_config_not_hardcoded(tmp_path: Path) -> None:
    """Changing a threshold in config changes the loaded verdict — no code edit.

    This is AC2's assertion: the loader must reflect whatever value is on
    disk, proving thresholds are not hardcoded on the loading path.
    """
    custom = tmp_path / "plan_review.yaml"
    custom.write_text(
        yaml.safe_dump(
            {
                "schema_version": "v1",
                "class_2": {
                    "shared_surface_globs": ["only/this/**"],
                    "churn_threshold": 12345,
                    "min_prod_areas": 7,
                },
                "class_3": {"mechanical_criteria": ["only-criterion"]},
                "models": {"planner": "custom-planner-model", "critic": "custom-critic-model"},
            }
        ),
        encoding="utf-8",
    )

    cfg = load_plan_review_config(custom)

    assert cfg.class_2.churn_threshold == 12345
    assert cfg.class_2.min_prod_areas == 7
    assert cfg.class_2.shared_surface_globs == ("only/this/**",)
    assert cfg.class_3.mechanical_criteria == ("only-criterion",)
    assert cfg.models.planner == "custom-planner-model"
    assert cfg.models.critic == "custom-critic-model"


def test_missing_models_key_raises(tmp_path: Path) -> None:
    """Issue #1686 AC9: planner/critic model floors must come from config —
    a config file without them is invalid, not silently defaulted."""
    bad = tmp_path / "plan_review.yaml"
    bad.write_text(
        yaml.safe_dump(
            {
                "schema_version": "v1",
                "class_2": {
                    "shared_surface_globs": ["x/**"],
                    "churn_threshold": 1,
                    "min_prod_areas": 1,
                },
                "class_3": {"mechanical_criteria": ["x"]},
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError):
        load_plan_review_config(bad)


def test_missing_file_raises() -> None:
    with pytest.raises(FileNotFoundError):
        load_plan_review_config(Path("does/not/exist.yaml"))


def test_missing_required_key_raises(tmp_path: Path) -> None:
    bad = tmp_path / "plan_review.yaml"
    bad.write_text(yaml.safe_dump({"schema_version": "v1", "class_2": {}}), encoding="utf-8")
    with pytest.raises(ValueError):
        load_plan_review_config(bad)

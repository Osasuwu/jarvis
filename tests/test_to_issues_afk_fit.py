"""Tests for scripts/to_issues_afk_fit.py — AFK-fit static check (issue #642).

The full AFK-fit checklist has four questions (1 static, 3 LLM-judgement).
This module covers question 1 only: does any declared-changed file match a
protected-path glob from the per-repo list in config/protected-paths.json?

Tests use synthetic config dicts to avoid coupling to the live JSON shape.
"""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
afk_fit = importlib.import_module("to_issues_afk_fit")

intersects_protected = afk_fit.intersects_protected
load_protected_paths = afk_fit.load_protected_paths


# ── Synthetic config used across tests ──────────────────────────────────────


SYNTHETIC_CONFIG = {
    "Osasuwu/jarvis": [
        ".mcp.json",
        "config/SOUL.md",
        "mcp-memory/handlers/**",
        ".pre-commit-config.yaml",
    ],
    "SergazyNarynov/redrobot": [
        "driver/**",
        "planning/**",
    ],
}


# ── Allow path (no intersection) ────────────────────────────────────────────


def test_no_intersection_when_files_outside_protected_zone():
    matched = intersects_protected(
        ["docs/foo.md", "src/bar.py"],
        repo="Osasuwu/jarvis",
        config=SYNTHETIC_CONFIG,
    )
    assert matched == []


def test_no_intersection_for_empty_declared_list():
    matched = intersects_protected([], repo="Osasuwu/jarvis", config=SYNTHETIC_CONFIG)
    assert matched == []


# ── Refusal path (intersection) ─────────────────────────────────────────────


def test_intersection_on_literal_file_match():
    matched = intersects_protected([".mcp.json"], repo="Osasuwu/jarvis", config=SYNTHETIC_CONFIG)
    assert matched == [".mcp.json"]


def test_intersection_on_glob_match():
    matched = intersects_protected(
        ["mcp-memory/handlers/foo.py"],
        repo="Osasuwu/jarvis",
        config=SYNTHETIC_CONFIG,
    )
    assert "mcp-memory/handlers/foo.py" in matched


def test_intersection_on_nested_glob_match():
    matched = intersects_protected(
        ["mcp-memory/handlers/sub/bar.py"],
        repo="Osasuwu/jarvis",
        config=SYNTHETIC_CONFIG,
    )
    assert "mcp-memory/handlers/sub/bar.py" in matched


def test_intersection_returns_all_matching_files():
    matched = intersects_protected(
        [".mcp.json", "docs/safe.md", "config/SOUL.md", "other/file.py"],
        repo="Osasuwu/jarvis",
        config=SYNTHETIC_CONFIG,
    )
    assert set(matched) == {".mcp.json", "config/SOUL.md"}


def test_intersection_for_redrobot_safety_zones():
    matched = intersects_protected(
        ["driver/main.py", "ui/page.tsx"],
        repo="SergazyNarynov/redrobot",
        config=SYNTHETIC_CONFIG,
    )
    assert matched == ["driver/main.py"]


# ── Repo lookup semantics ───────────────────────────────────────────────────


def test_unknown_repo_returns_no_intersection_by_default():
    """An unlisted repo has no protected-paths entry — AFK-yes by default.

    Failing closed (treating unknown as protected) would block any new repo
    until edited; AC explicitly says adding a new repo MUST NOT require
    editing the SKILL.md, so failing open with a clear marker is right.
    The skill prose must surface 'unknown repo' as an LLM-judgement prompt.
    """
    matched = intersects_protected([".mcp.json"], repo="Unknown/repo", config=SYNTHETIC_CONFIG)
    assert matched == []


def test_repo_with_empty_glob_list_returns_no_intersection():
    config = {"Some/repo": []}
    matched = intersects_protected([".mcp.json"], repo="Some/repo", config=config)
    assert matched == []


# ── Load from JSON file ─────────────────────────────────────────────────────


def test_load_protected_paths_skips_underscore_keys(tmp_path):
    """The `_comment` key in the canonical JSON is metadata, not a repo entry."""
    path = tmp_path / "paths.json"
    path.write_text(
        json.dumps(
            {
                "_comment": "explanatory metadata",
                "Owner/repo": [".mcp.json"],
            }
        )
    )
    config = load_protected_paths(path)
    assert "_comment" not in config
    assert config == {"Owner/repo": [".mcp.json"]}


def test_load_protected_paths_real_config_has_both_repos():
    """Smoke against the actual config/protected-paths.json shipped with this PR."""
    repo_root = Path(__file__).resolve().parents[1]
    config = load_protected_paths(repo_root / "config" / "protected-paths.json")
    assert "Osasuwu/jarvis" in config
    assert "SergazyNarynov/redrobot" in config
    # Jarvis list must cover the canonical Tier-2 surface (sample check)
    assert ".mcp.json" in config["Osasuwu/jarvis"]
    assert "CLAUDE.md" in config["Osasuwu/jarvis"]
    # Redrobot list must cover the documented safety-critical zones
    assert any(p.startswith("driver/") for p in config["SergazyNarynov/redrobot"])


def test_real_config_redrobot_blocks_driver_path():
    repo_root = Path(__file__).resolve().parents[1]
    config = load_protected_paths(repo_root / "config" / "protected-paths.json")
    matched = intersects_protected(
        ["driver/joint_controller.py"],
        repo="SergazyNarynov/redrobot",
        config=config,
    )
    assert matched == ["driver/joint_controller.py"]


def test_real_config_jarvis_blocks_protected_file():
    repo_root = Path(__file__).resolve().parents[1]
    config = load_protected_paths(repo_root / "config" / "protected-paths.json")
    matched = intersects_protected(
        [".mcp.json", "docs/foo.md"],
        repo="Osasuwu/jarvis",
        config=config,
    )
    assert matched == [".mcp.json"]

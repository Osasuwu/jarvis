"""Tests for scripts/to_tickets_afk_fit.py — AFK-fit static classification (#642, #1708).

The full AFK-fit checklist has four questions. Question 1 is static and lives
here: does any declared-changed file match a protected-path glob from the
per-repo {hitl, guarded} buckets in config/protected-paths.json? A hitl hit is
a categorical security boundary (class 3, afk:3-human, hard refusal); a
guarded hit is a shared surface recoverable via a locked plan (class 2,
afk:2-plan); no hit falls through to Q2-Q4 LLM judgement (prose in SKILL.md).

Tests use synthetic config dicts to avoid coupling to the live JSON shape,
plus a handful of smoke tests against the real config/protected-paths.json.
"""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
afk_fit = importlib.import_module("to_tickets_afk_fit")

classify_static_paths = afk_fit.classify_static_paths
ClassVerdict = afk_fit.ClassVerdict
load_protected_paths = afk_fit.load_protected_paths


# ── Synthetic config used across tests ──────────────────────────────────────


SYNTHETIC_CONFIG = {
    "Osasuwu/jarvis": {
        "hitl": [
            ".mcp.json",
            "config/SOUL.md",
            ".pre-commit-config.yaml",
        ],
        "guarded": [
            "mcp-memory/handlers/**",
        ],
    },
    "SergazyNarynov/redrobot": {
        "hitl": [],
        "guarded": [
            "driver/**",
            "planning/**",
        ],
    },
}


# ── No match — fall through ──────────────────────────────────────────────────


def test_no_match_falls_through_for_known_repo():
    verdict = classify_static_paths(
        ["docs/foo.md", "src/bar.py"],
        repo="Osasuwu/jarvis",
        config=SYNTHETIC_CONFIG,
    )
    assert verdict.cls is None
    assert verdict.bucket is None
    assert verdict.label is None
    assert verdict.matched_files == ()
    assert "fall through" in verdict.reason


def test_no_match_for_empty_declared_list():
    verdict = classify_static_paths([], repo="Osasuwu/jarvis", config=SYNTHETIC_CONFIG)
    assert verdict.cls is None
    assert "fall through" in verdict.reason


# ── hitl hit -> class 3 ──────────────────────────────────────────────────────


def test_hitl_literal_match_is_class_3():
    verdict = classify_static_paths([".mcp.json"], repo="Osasuwu/jarvis", config=SYNTHETIC_CONFIG)
    assert verdict.cls == 3
    assert verdict.bucket == "hitl"
    assert verdict.label == "afk:3-human"
    assert verdict.matched_files == (".mcp.json",)


def test_hitl_glob_prefix_match_is_class_3():
    config = {
        "Osasuwu/jarvis": {"hitl": ["config/**"], "guarded": []},
    }
    verdict = classify_static_paths(["config/SOUL.md"], repo="Osasuwu/jarvis", config=config)
    assert verdict.cls == 3
    assert verdict.bucket == "hitl"


# ── guarded hit -> class 2 ───────────────────────────────────────────────────


def test_guarded_glob_match_is_class_2():
    verdict = classify_static_paths(
        ["mcp-memory/handlers/foo.py"],
        repo="Osasuwu/jarvis",
        config=SYNTHETIC_CONFIG,
    )
    assert verdict.cls == 2
    assert verdict.bucket == "guarded"
    assert verdict.label == "afk:2-plan"
    assert verdict.matched_files == ("mcp-memory/handlers/foo.py",)


def test_guarded_nested_glob_match_is_class_2():
    verdict = classify_static_paths(
        ["mcp-memory/handlers/sub/bar.py"],
        repo="Osasuwu/jarvis",
        config=SYNTHETIC_CONFIG,
    )
    assert verdict.cls == 2
    assert verdict.bucket == "guarded"


def test_redrobot_empty_hitl_guarded_hit_is_class_2():
    """Redrobot has no hitl entries — a guarded-zone file must still be class 2."""
    verdict = classify_static_paths(
        ["driver/main.py", "ui/page.tsx"],
        repo="SergazyNarynov/redrobot",
        config=SYNTHETIC_CONFIG,
    )
    assert verdict.cls == 2
    assert verdict.bucket == "guarded"
    assert verdict.label == "afk:2-plan"
    assert verdict.matched_files == ("driver/main.py",)


# ── hitl wins over guarded when both buckets match ──────────────────────────


def test_hitl_wins_when_both_buckets_match():
    config = {
        "Owner/repo": {
            "hitl": ["secrets/**"],
            "guarded": ["secrets/**"],
        }
    }
    verdict = classify_static_paths(["secrets/token.json"], repo="Owner/repo", config=config)
    assert verdict.cls == 3
    assert verdict.bucket == "hitl"


# ── Repo lookup semantics ───────────────────────────────────────────────────


def test_unknown_repo_reason_names_it_for_manual_judgement():
    """An unlisted repo has no bucket entries — flag for manual judgement.

    Failing closed (treating unknown as protected) would block any new repo
    until edited; the AFK-fit AC explicitly says adding a new repo MUST NOT
    require editing the SKILL.md, so failing open with a clear marker is
    right. The skill prose must surface 'unknown repo' as an LLM-judgement
    prompt.
    """
    verdict = classify_static_paths([".mcp.json"], repo="Unknown/repo", config=SYNTHETIC_CONFIG)
    assert verdict.cls is None
    assert verdict.bucket is None
    assert verdict.label is None
    assert verdict.reason == "unknown repo, judge manually"


def test_known_repo_with_empty_buckets_falls_through():
    config = {"Some/repo": {"hitl": [], "guarded": []}}
    verdict = classify_static_paths([".mcp.json"], repo="Some/repo", config=config)
    assert verdict.cls is None
    assert "fall through" in verdict.reason


# ── Load from JSON file ─────────────────────────────────────────────────────


def test_load_protected_paths_skips_underscore_keys(tmp_path):
    """The `_comment` key in the canonical JSON is metadata, not a repo entry."""
    path = tmp_path / "paths.json"
    path.write_text(
        json.dumps(
            {
                "_comment": "explanatory metadata",
                "Owner/repo": {"hitl": [".mcp.json"], "guarded": []},
            }
        )
    )
    config = load_protected_paths(path)
    assert "_comment" not in config
    assert config == {"Owner/repo": {"hitl": [".mcp.json"], "guarded": []}}


def test_load_protected_paths_rejects_legacy_flat_list_shape(tmp_path):
    """A pre-#1708 flat list-per-repo document is a stale schema, not a repo
    with empty buckets — must raise, not silently misread as no protections."""
    path = tmp_path / "paths.json"
    path.write_text(json.dumps({"Owner/repo": [".mcp.json", "config/SOUL.md"]}))
    try:
        load_protected_paths(path)
    except ValueError as exc:
        assert "Owner/repo" in str(exc)
    else:
        raise AssertionError("expected ValueError on legacy flat-list schema")


def test_intersects_protected_removed():
    """classify_static_paths is the sole entry point (#1708) — the old
    boolean-style helper must no longer exist as a module attribute."""
    assert not hasattr(afk_fit, "intersects_protected")


# ── Smoke against the real config/protected-paths.json ──────────────────────


def test_load_protected_paths_real_config_has_both_repos():
    repo_root = Path(__file__).resolve().parents[2]
    config = load_protected_paths(repo_root / "config" / "protected-paths.json")
    assert "Osasuwu/jarvis" in config
    assert "SergazyNarynov/redrobot" in config
    assert ".mcp.json" in config["Osasuwu/jarvis"]["guarded"]
    assert "CLAUDE.md" in config["Osasuwu/jarvis"]["hitl"]
    assert any(
        p.startswith("redrobot/driver/") for p in config["SergazyNarynov/redrobot"]["guarded"]
    )
    assert config["SergazyNarynov/redrobot"]["hitl"] == []


def test_real_config_redrobot_driver_path_is_class_2():
    repo_root = Path(__file__).resolve().parents[2]
    config = load_protected_paths(repo_root / "config" / "protected-paths.json")
    verdict = classify_static_paths(
        ["redrobot/driver/joint_controller.py"],
        repo="SergazyNarynov/redrobot",
        config=config,
    )
    assert verdict.cls == 2
    assert verdict.label == "afk:2-plan"
    assert verdict.matched_files == ("redrobot/driver/joint_controller.py",)


def test_real_config_redrobot_planning_path_is_class_2():
    """#1684 fail-open repro: a real redrobot safety path (`redrobot/planning/…`)
    must match the guarded bucket. Before the fix the glob was the bare
    `planning/**`, which matched no real repo-relative path and silently
    returned no-match (class None → LLM fall-through)."""
    repo_root = Path(__file__).resolve().parents[2]
    config = load_protected_paths(repo_root / "config" / "protected-paths.json")
    verdict = classify_static_paths(
        ["redrobot/planning/strategist.py"],
        repo="SergazyNarynov/redrobot",
        config=config,
    )
    assert verdict.cls == 2
    assert verdict.bucket == "guarded"
    assert verdict.matched_files == ("redrobot/planning/strategist.py",)


def test_real_config_redrobot_tier1_files_are_class_2():
    """Full tier-1 safety core (decision a7111a44) — each declared path must be
    class 2, guarding against a partial fix that only prefixes some zones."""
    repo_root = Path(__file__).resolve().parents[2]
    config = load_protected_paths(repo_root / "config" / "protected-paths.json")
    for path in (
        "redrobot/driver/motor.py",
        "redrobot/planning/policy.py",
        "redrobot/experiments.py",
        "tests/safety/test_limits.py",
        "tests/experiments/test_rehearsal_guard.py",
    ):
        verdict = classify_static_paths(
            [path], repo="SergazyNarynov/redrobot", config=config
        )
        assert verdict.cls == 2, f"{path} should be class 2, got {verdict.cls}"
        assert verdict.bucket == "guarded", path


def test_real_config_redrobot_mujoco_removed_and_no_bare_prefixes():
    """`mujoco/**` retired (tier 2, guarded by golden/replay tests not the plan
    gate); no guarded glob is a bare zone prefix that would fail open against
    real `redrobot/…` paths (#1684)."""
    repo_root = Path(__file__).resolve().parents[2]
    config = load_protected_paths(repo_root / "config" / "protected-paths.json")
    guarded = config["SergazyNarynov/redrobot"]["guarded"]
    assert not any("mujoco" in g for g in guarded)
    # Every package-dir zone glob must carry the redrobot/ prefix; a bare
    # `driver/**` or `planning/**` is the exact fail-open shape from #1684.
    for bare in ("driver/**", "planning/**"):
        assert bare not in guarded, f"bare {bare} reintroduces the #1684 fail-open"


def test_real_config_jarvis_hitl_file_is_class_3():
    repo_root = Path(__file__).resolve().parents[2]
    config = load_protected_paths(repo_root / "config" / "protected-paths.json")
    verdict = classify_static_paths(
        ["CLAUDE.md", "docs/foo.md"],
        repo="Osasuwu/jarvis",
        config=config,
    )
    assert verdict.cls == 3
    assert verdict.label == "afk:3-human"
    assert verdict.matched_files == ("CLAUDE.md",)


def test_real_config_jarvis_mcp_memory_is_class_2():
    """Proof for #1708 AC: mcp-memory/server.py, previously a blanket AFK-no
    (class-3-equivalent) hitl entry, now yields class 2 under the guarded
    bucket — it's a shared surface recoverable via a locked plan, not a
    categorical security boundary."""
    repo_root = Path(__file__).resolve().parents[2]
    config = load_protected_paths(repo_root / "config" / "protected-paths.json")
    verdict = classify_static_paths(
        ["mcp-memory/server.py"],
        repo="Osasuwu/jarvis",
        config=config,
    )
    assert verdict.cls == 2
    assert verdict.bucket == "guarded"
    assert verdict.label == "afk:2-plan"

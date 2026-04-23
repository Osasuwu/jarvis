"""Tests for scripts/install/installer.py — Epic #335 M1."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
import yaml


# Add scripts/install/ to sys.path so `import installer` resolves; dataclasses
# need the module registered in sys.modules (__module__ lookup).
import sys as _sys

_install_dir = Path(__file__).resolve().parents[1] / "scripts" / "install"
if str(_install_dir) not in _sys.path:
    _sys.path.insert(0, str(_install_dir))

import installer  # noqa: E402  — path hack is intentional


# ---------- fixtures ----------


@pytest.fixture
def fake_repo(tmp_path: Path) -> Path:
    """A minimal fake repo with a small .claude/, config/, .mcp.json and git init."""
    repo = tmp_path / "jarvis"
    (repo / ".claude" / "skills" / "implement").mkdir(parents=True)
    (repo / ".claude" / "skills" / "implement" / "SKILL.md").write_text(
        "# implement skill\n", encoding="utf-8"
    )
    (repo / ".claude" / "skills" / "niche").mkdir(parents=True)
    (repo / ".claude" / "skills" / "niche" / "SKILL.md").write_text(
        "# niche skill (should NOT be whitelisted)\n", encoding="utf-8"
    )
    (repo / ".claude" / "settings.json").write_text(
        json.dumps(
            {
                "hooks": {
                    "SessionStart": [
                        {
                            "matcher": "startup",
                            "hooks": [
                                {
                                    "type": "command",
                                    "command": "python scripts/session-context.py",
                                }
                            ],
                        }
                    ]
                }
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    (repo / "config").mkdir()
    (repo / "config" / "SOUL.md").write_text("# SOUL stub\n", encoding="utf-8")
    (repo / ".mcp.json").write_text(
        json.dumps(
            {
                "mcpServers": {
                    "memory": {
                        "command": "python",
                        "args": ["scripts/run-memory-server.py"],
                    }
                }
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    # git init so current_git_sha() works
    subprocess.run(["git", "init", "-q", "--initial-branch=main"], cwd=repo, check=True)
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "init"],
        cwd=repo,
        check=True,
    )
    return repo


@pytest.fixture
def manifest(tmp_path: Path, fake_repo: Path) -> Path:
    target = tmp_path / "claude_home"
    data = {
        "version": 1,
        "target_root": str(target),
        "version_marker": ".jarvis-version",
        "groups": [
            {
                "id": "soul",
                "enabled": True,
                "files": [{"source": "config/SOUL.md", "dest": "SOUL.md", "template": False}],
            },
            {
                "id": "hooks_settings",
                "enabled": True,
                "files": [
                    {
                        "source": ".claude/settings.json",
                        "dest": "settings.json",
                        "template": True,
                    }
                ],
            },
            {
                "id": "mcp_config",
                "enabled": True,
                "files": [
                    {"source": ".mcp.json", "dest": ".mcp.json", "template": True}
                ],
            },
            {
                "id": "skills",
                "enabled": True,
                "directories": [
                    {
                        "source": ".claude/skills",
                        "dest": "skills",
                        "template": False,
                        "include": ["implement"],
                    }
                ],
            },
        ],
        "env_vars": [{"name": "JARVIS_HOME", "value": "{repo_root}", "platforms": ["windows", "posix"]}],
        "health_check": {"enabled": False},
        "backup": {"prefix": ".claude.backup-", "retain": 3},
    }
    path = fake_repo / "install-manifest.yaml"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    return path


# ---------- unit tests ----------


def test_load_manifest_rejects_unknown_version(tmp_path: Path) -> None:
    bad = tmp_path / "m.yaml"
    bad.write_text(yaml.safe_dump({"version": 999}), encoding="utf-8")
    with pytest.raises(ValueError, match="unsupported manifest version"):
        installer.load_manifest(bad)


def test_detect_state_fresh_when_target_missing(tmp_path: Path) -> None:
    state, prev = installer.detect_state(tmp_path / "missing", "abc123")
    assert state == "fresh"
    assert prev is None


def test_detect_state_current_when_sha_matches(tmp_path: Path) -> None:
    target = tmp_path / "t"
    target.mkdir()
    (target / ".jarvis-version").write_text("abc123\n", encoding="utf-8")
    state, prev = installer.detect_state(target, "abc123")
    assert state == "current"
    assert prev == "abc123"


def test_detect_state_outdated_when_sha_differs(tmp_path: Path) -> None:
    target = tmp_path / "t"
    target.mkdir()
    (target / ".jarvis-version").write_text("old\n", encoding="utf-8")
    state, prev = installer.detect_state(target, "new")
    assert state == "outdated"
    assert prev == "old"


def test_template_content_json_rewrites_relative_paths(fake_repo: Path) -> None:
    target = fake_repo / ".claude" / "settings.json"
    claude_home = Path("/tmp/not-used")
    rendered = installer.template_content(target, fake_repo, claude_home).decode("utf-8")
    data = json.loads(rendered)
    command = data["hooks"]["SessionStart"][0]["hooks"][0]["command"]
    expected_prefix = fake_repo.as_posix() + "/scripts/"
    assert expected_prefix in command, f"got: {command}"
    assert not command.startswith("python scripts/"), "relative path not rewritten"


def test_template_content_mcp_json_rewrites_args(fake_repo: Path) -> None:
    target = fake_repo / ".mcp.json"
    rendered = installer.template_content(target, fake_repo, Path("/")).decode("utf-8")
    data = json.loads(rendered)
    args = data["mcpServers"]["memory"]["args"]
    assert args[0].startswith(fake_repo.as_posix() + "/scripts/")


def test_build_plan_state_fresh_has_writes_no_backup(manifest: Path, fake_repo: Path) -> None:
    m = installer.load_manifest(manifest)
    plan = installer.build_plan(m, fake_repo)
    assert plan.state == "fresh"
    assert plan.backup_path is None  # target doesn't exist yet
    kinds = [a.kind for a in plan.actions]
    assert kinds.count("copy_file") >= 3  # SOUL, settings, mcp
    assert kinds.count("copy_dir") == 1
    assert kinds.count("write_version") == 1
    assert kinds.count("set_env") == 1


def test_apply_plan_creates_files_and_version_marker(
    manifest: Path, fake_repo: Path
) -> None:
    m = installer.load_manifest(manifest)
    plan = installer.build_plan(m, fake_repo)
    installer.apply_plan(plan, m, run_env=None)

    target = plan.target_root
    assert (target / "SOUL.md").exists()
    assert (target / "settings.json").exists()
    assert (target / ".mcp.json").exists()
    assert (target / "skills" / "implement" / "SKILL.md").exists()
    # whitelist excluded
    assert not (target / "skills" / "niche").exists()

    marker = (target / ".jarvis-version").read_text(encoding="utf-8").strip()
    assert marker == plan.current_sha


def test_apply_is_idempotent(manifest: Path, fake_repo: Path) -> None:
    m = installer.load_manifest(manifest)
    plan1 = installer.build_plan(m, fake_repo)
    installer.apply_plan(plan1, m, run_env=None)

    plan2 = installer.build_plan(m, fake_repo)
    assert plan2.state == "current"
    assert plan2.actions == []


def test_outdated_triggers_backup(manifest: Path, fake_repo: Path, tmp_path: Path) -> None:
    m = installer.load_manifest(manifest)
    plan1 = installer.build_plan(m, fake_repo)
    installer.apply_plan(plan1, m, run_env=None)

    # Pretend the repo moved to a new SHA by overwriting the marker.
    (plan1.target_root / ".jarvis-version").write_text("old-sha-not-real\n", encoding="utf-8")

    plan2 = installer.build_plan(m, fake_repo)
    assert plan2.state == "outdated"
    assert plan2.backup_path is not None
    installer.apply_plan(plan2, m, run_env=None)
    assert plan2.backup_path.exists()
    assert (plan2.backup_path / "SOUL.md").exists()


def test_rollback_restores_target(manifest: Path, fake_repo: Path) -> None:
    m = installer.load_manifest(manifest)
    plan = installer.build_plan(m, fake_repo)
    installer.apply_plan(plan, m, run_env=None)

    backup = plan.target_root.parent / ".claude.backup-manual"
    import shutil
    shutil.copytree(plan.target_root, backup)

    # Corrupt the target.
    (plan.target_root / "SOUL.md").write_text("corrupted\n", encoding="utf-8")
    installer.rollback(plan.target_root, backup)
    assert (plan.target_root / "SOUL.md").read_text(encoding="utf-8") == "# SOUL stub\n"


def test_prune_backups_keeps_latest_n(fake_repo: Path, tmp_path: Path) -> None:
    target_root = tmp_path / "claude_home"
    parent = target_root.parent
    for name in [".claude.backup-20260401-000000", ".claude.backup-20260402-000000",
                 ".claude.backup-20260403-000000", ".claude.backup-20260404-000000"]:
        (parent / name).mkdir()
    dropped = installer.prune_backups(target_root, ".claude.backup-", retain=2)
    assert len(dropped) == 2
    remaining = sorted(p.name for p in parent.iterdir() if p.name.startswith(".claude.backup-"))
    assert remaining == [".claude.backup-20260403-000000", ".claude.backup-20260404-000000"]


def test_health_check_disabled_by_default_returns_ok() -> None:
    ok, logs = installer.run_health_check({"health_check": {"enabled": False}}, Path("."))
    assert ok is True
    assert logs == []


def test_health_check_failed_command_reports_failure(fake_repo: Path) -> None:
    m = {"health_check": {"enabled": True, "commands": ["python -c exit(1)"]}}
    ok, logs = installer.run_health_check(m, fake_repo)
    assert ok is False
    assert any("FAIL" in line for line in logs)


def test_disabled_group_is_skipped(manifest: Path, fake_repo: Path) -> None:
    data = yaml.safe_load(manifest.read_text(encoding="utf-8"))
    for g in data["groups"]:
        if g["id"] == "soul":
            g["enabled"] = False
    manifest.write_text(yaml.safe_dump(data), encoding="utf-8")

    m = installer.load_manifest(manifest)
    plan = installer.build_plan(m, fake_repo)
    installer.apply_plan(plan, m, run_env=None)
    assert not (plan.target_root / "SOUL.md").exists()
    # Others still land.
    assert (plan.target_root / "settings.json").exists()


def test_real_manifest_all_groups_disabled_yields_minimal_plan(fake_repo: Path) -> None:
    """The real repo manifest ships with all groups disabled for M1.
    Plan must still produce a version marker + env var so the installer
    is meaningful even before M2-M4 enable the groups.
    """
    real = Path(__file__).resolve().parents[1] / "install-manifest.yaml"
    if not real.exists():
        pytest.skip("no real manifest")
    m = installer.load_manifest(real)
    # Re-point target to a tmp dir to avoid touching user home.
    target = fake_repo.parent / "sandbox-claude"
    plan = installer.build_plan(m, fake_repo, target_root_override=str(target))
    kinds = [a.kind for a in plan.actions]
    assert "write_version" in kinds
    assert "set_env" in kinds
    # No copies while all groups disabled.
    assert "copy_file" not in kinds
    assert "copy_dir" not in kinds

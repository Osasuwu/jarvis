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


def test_health_check_handles_utf8_output(fake_repo: Path) -> None:
    """Regression for #352: on non-UTF-8 Windows locales (e.g. cp1251),
    text=True without explicit encoding crashes the reader thread when a
    health-check script emits em-dashes / Cyrillic. The parent call now
    forces encoding='utf-8', errors='replace' — asserting the guarantee
    here locks that in regardless of the host's locale."""
    payload = 'import sys; sys.stdout.buffer.write("before \u2014 после\n".encode("utf-8"))'
    m = {
        "health_check": {
            "enabled": True,
            "commands": [f'python -c "{payload}"'],
        }
    }
    ok, logs = installer.run_health_check(m, fake_repo)
    assert ok is True, logs
    assert any("OK" in line for line in logs)


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


def test_real_manifest_m4_all_groups_enabled() -> None:
    """Real manifest shape after M4 (#339): all 4 groups enabled.
    soul joins skills + hooks_settings + mcp_config.
    """
    real = Path(__file__).resolve().parents[1] / "install-manifest.yaml"
    assert real.exists(), "install-manifest.yaml must ship in-tree"
    m = installer.load_manifest(real)

    by_id = {g["id"]: g for g in m["groups"]}
    assert by_id["skills"]["enabled"] is True
    assert by_id["skills"]["directories"][0]["source"] == ".claude-userlevel/skills"
    include = by_id["skills"]["directories"][0]["include"]
    assert "sprint-report" not in include
    assert "implement" in include and "delegate" in include

    assert by_id["hooks_settings"]["enabled"] is True
    settings_entry = by_id["hooks_settings"]["files"][0]
    assert settings_entry["source"] == ".claude-userlevel/settings.json"
    assert settings_entry["merge"] is True
    assert settings_entry["template"] is True

    assert by_id["mcp_config"]["enabled"] is True
    mcp_entry = by_id["mcp_config"]["files"][0]
    assert mcp_entry["source"] == ".claude-userlevel/.mcp.json"
    assert mcp_entry["install_as"] == "user_mcp_registrations"
    assert mcp_entry["template"] is True

    # M4: soul flipped on. Source stays at config/SOUL.md (canonical git-tracked).
    # Dest SOUL.md lands at ~/.claude/SOUL.md via plain copy (no template, no merge).
    assert by_id["soul"]["enabled"] is True
    soul_entry = by_id["soul"]["files"][0]
    assert soul_entry["source"] == "config/SOUL.md"
    assert soul_entry["dest"] == "SOUL.md"
    assert soul_entry.get("template", False) is False
    assert soul_entry.get("merge", False) is False


def test_userlevel_settings_points_soul_at_user_level(fake_repo: Path) -> None:
    """M4 (#339) acceptance: rendered SessionStart command reads SOUL from
    {{CLAUDE_USER_HOME}}/SOUL.md (so it works in any CWD, not tied to
    JARVIS_HOME — user-level install becomes the source of SOUL at runtime)."""
    repo_root = Path(__file__).resolve().parents[1]
    settings_src = repo_root / ".claude-userlevel" / "settings.json"
    claude_home = Path("/opt/fakehome/.claude")
    rendered = installer.template_content(
        settings_src, repo_root, claude_home
    ).decode("utf-8")
    data = json.loads(rendered)
    # Every SessionStart cat must reference the user-level SOUL, not
    # <JARVIS_HOME>/config/SOUL.md.
    for entry in data["hooks"]["SessionStart"]:
        for hook in entry["hooks"]:
            cmd = hook["command"]
            if "SOUL.md" in cmd:
                assert f"{claude_home.as_posix()}/SOUL.md" in cmd, (
                    f"SessionStart SOUL path not rewritten to user level: {cmd}"
                )
                assert "config/SOUL.md" not in cmd, (
                    f"leftover relative config/SOUL.md reference: {cmd}"
                )


def test_userlevel_source_files_exist() -> None:
    """Source-of-truth files for M3 must ship in-tree."""
    repo_root = Path(__file__).resolve().parents[1]
    assert (repo_root / ".claude-userlevel" / "settings.json").exists()
    assert (repo_root / ".claude-userlevel" / ".mcp.json").exists()


# ---------- #344: tightening before M3 ----------


def test_path_rewrite_preserves_urls() -> None:
    """Regex must NOT rewrite `scripts/` / `config/` tokens that are part of
    a URL or a compound identifier. Was `\\b(scripts|config)/` — too greedy.
    """
    data = {
        "docs": "https://example.com/scripts/foo",
        "nested": {"ref": "https://cdn.example.com/config/v2/x.yaml"},
        "compound": "my-scripts/foo",
        "list": ["https://gh.io/scripts/a", "scripts/keep"],
    }
    out = installer._transform_json_paths(data, "/abs/repo")
    assert out["docs"] == "https://example.com/scripts/foo"
    assert out["nested"]["ref"] == "https://cdn.example.com/config/v2/x.yaml"
    assert out["compound"] == "my-scripts/foo"
    # The one real path still gets rewritten.
    assert out["list"][0] == "https://gh.io/scripts/a"
    assert out["list"][1] == "/abs/repo/scripts/keep"


def test_path_rewrite_handles_embedded_command_paths() -> None:
    """Command strings with multiple relative paths (whitespace-separated)
    must have all path tokens rewritten."""
    cmd = "python scripts/a.py && cat config/SOUL.md && python scripts/b.py"
    out = installer._transform_json_paths(cmd, "/abs/repo")
    assert "/abs/repo/scripts/a.py" in out
    assert "/abs/repo/config/SOUL.md" in out
    assert "/abs/repo/scripts/b.py" in out
    assert " scripts/" not in out
    assert " config/" not in out


def test_fresh_install_rollback_on_apply_failure(
    manifest: Path, fake_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Fresh-state apply failure must leave target_root removed, not half-written.

    Without the fix, a failure mid-apply leaves a stub directory that
    detect_state reads as outdated next time, masking the original error.
    """
    m = installer.load_manifest(manifest)
    plan = installer.build_plan(m, fake_repo)
    assert plan.state == "fresh"
    assert plan.backup_path is None

    # Make apply create the target dir (simulating partial write) then fail.
    real_copy_file = installer._copy_file
    call_count = {"n": 0}

    def flaky_copy_file(*args, **kwargs):
        call_count["n"] += 1
        if call_count["n"] == 1:
            real_copy_file(*args, **kwargs)
            return
        raise RuntimeError("simulated apply failure")

    monkeypatch.setattr(installer, "_copy_file", flaky_copy_file)

    with pytest.raises(RuntimeError, match="simulated apply failure"):
        installer.apply_plan(plan, m, run_env=None)

    # Sanity: target_root exists and has partial content.
    assert plan.target_root.exists()
    assert any(plan.target_root.iterdir())

    # Now invoke the rollback helper directly (what main() does in the except).
    installer._rollback_failed_apply(plan)
    assert not plan.target_root.exists(), (
        "fresh install failure must remove target_root entirely"
    )


def test_health_check_uses_shlex_for_argv_parsing(
    fake_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """cmd.split() broke on paths with spaces; shlex handles quoted args."""
    seen: list[list[str]] = []

    class FakeResult:
        returncode = 0
        stderr = ""
        stdout = ""

    def fake_run(argv, **kwargs):
        seen.append(list(argv))
        return FakeResult()

    monkeypatch.setattr(installer.subprocess, "run", fake_run)

    m = {
        "health_check": {
            "enabled": True,
            "commands": [
                'python "/tmp/path with spaces/script.py" --flag value',
            ],
        }
    }
    ok, _logs = installer.run_health_check(m, fake_repo)
    assert ok is True
    assert len(seen) == 1
    argv = seen[0]
    # Whether posix or windows flavor of shlex, the quoted path must stay
    # as ONE argv element (not split on spaces).
    assert any("path with spaces" in tok for tok in argv), (
        f"quoted path split by whitespace: argv={argv}"
    )
    assert argv[0] == "python"


# ---------- #338 (M3): settings.json + .mcp.json deep-merge ----------


def test_deep_merge_preserves_user_hook_events(tmp_path: Path) -> None:
    """User events jarvis doesn't own (e.g. Stop) must survive merge."""
    existing = {
        "hooks": {
            "SessionStart": [{"matcher": "startup", "hooks": [
                {"type": "command", "command": "user-custom-session.sh"}
            ]}],
            "Stop": [{"hooks": [{"type": "command", "command": "user-cleanup.sh"}]}],
        },
        "theme": "dark",  # top-level user key
    }
    source = {
        "hooks": {
            "SessionStart": [{"matcher": "startup", "hooks": [
                {"type": "command", "command": "python /abs/jarvis/scripts/session-context.py"}
            ]}],
            "PreCompact": [{"hooks": [{"type": "command", "command": "python /abs/jarvis/scripts/pre-compact-backup.py"}]}],
        }
    }
    merged = installer._deep_merge_jarvis_json(existing, source)

    # Jarvis replaces SessionStart wholesale — user's custom SessionStart entry is gone.
    ss = merged["hooks"]["SessionStart"][0]["hooks"][0]["command"]
    assert "session-context.py" in ss
    assert "user-custom-session.sh" not in ss

    # Jarvis adds PreCompact (it didn't exist before).
    assert "PreCompact" in merged["hooks"]
    assert "pre-compact-backup.py" in merged["hooks"]["PreCompact"][0]["hooks"][0]["command"]

    # Stop (user-owned event jarvis doesn't touch) is preserved.
    assert merged["hooks"]["Stop"][0]["hooks"][0]["command"] == "user-cleanup.sh"

    # Top-level non-hooks user key preserved.
    assert merged["theme"] == "dark"


def test_deep_merge_preserves_user_mcp_servers(tmp_path: Path) -> None:
    """User-added mcpServers entries must survive; jarvis-owned ones replaced."""
    existing = {
        "mcpServers": {
            "memory": {"command": "old-memory", "args": ["obsolete"]},
            "user-custom": {"command": "npx", "args": ["user-server"]},
        }
    }
    source = {
        "mcpServers": {
            "memory": {"command": "python", "args": ["/abs/jarvis/scripts/run-memory-server.py"]},
            "context7": {"command": "npx", "args": ["-y", "@upstash/context7-mcp@latest"]},
        }
    }
    merged = installer._deep_merge_jarvis_json(existing, source)

    assert merged["mcpServers"]["memory"]["command"] == "python"
    assert "run-memory-server.py" in merged["mcpServers"]["memory"]["args"][0]
    assert merged["mcpServers"]["context7"]["args"][0] == "-y"
    # User-added server preserved.
    assert merged["mcpServers"]["user-custom"]["command"] == "npx"
    assert merged["mcpServers"]["user-custom"]["args"] == ["user-server"]


def test_merge_json_file_fresh_write_when_dest_missing(tmp_path: Path) -> None:
    """No existing target → write source as-is (still templated)."""
    src = tmp_path / "src.json"
    src.write_text(json.dumps({"hooks": {"SessionStart": [{"command": "x"}]}}),
                   encoding="utf-8")
    dest = tmp_path / "out" / "settings.json"
    installer._merge_json_file(src, dest, template=False, repo_root=tmp_path,
                               claude_home=tmp_path)
    assert dest.exists()
    loaded = json.loads(dest.read_text(encoding="utf-8"))
    assert loaded["hooks"]["SessionStart"][0]["command"] == "x"


def test_merge_json_file_merges_onto_existing(tmp_path: Path) -> None:
    """Existing dest → deep-merge (user keys preserved)."""
    dest = tmp_path / "settings.json"
    dest.write_text(json.dumps({"hooks": {"Stop": [{"c": "user"}]}, "theme": "dark"}),
                    encoding="utf-8")
    src = tmp_path / "src.json"
    src.write_text(json.dumps({"hooks": {"SessionStart": [{"c": "jarvis"}]}}),
                   encoding="utf-8")

    installer._merge_json_file(src, dest, template=False, repo_root=tmp_path,
                               claude_home=tmp_path)
    merged = json.loads(dest.read_text(encoding="utf-8"))
    assert merged["hooks"]["Stop"][0]["c"] == "user"  # survived
    assert merged["hooks"]["SessionStart"][0]["c"] == "jarvis"  # added
    assert merged["theme"] == "dark"  # survived


def test_merge_json_file_corrupt_existing_falls_back_to_source(tmp_path: Path) -> None:
    """Unparseable existing dest → treat as absent and write source fresh."""
    dest = tmp_path / "settings.json"
    dest.write_text("{not valid json", encoding="utf-8")
    src = tmp_path / "src.json"
    src.write_text(json.dumps({"hooks": {"SessionStart": [{"c": "new"}]}}),
                   encoding="utf-8")

    installer._merge_json_file(src, dest, template=False, repo_root=tmp_path,
                               claude_home=tmp_path)
    merged = json.loads(dest.read_text(encoding="utf-8"))
    assert merged["hooks"]["SessionStart"][0]["c"] == "new"


def test_merge_json_preserves_user_mcp_on_reapply(
    manifest: Path, fake_repo: Path
) -> None:
    """Full flow: apply once, user adds a custom mcpServer, re-apply,
    jarvis-owned server updates while custom server survives.
    Idempotency for jarvis keys: re-apply doesn't duplicate."""
    # Manifest mcp_config uses copy_file by default in fixture; switch to merge.
    data = yaml.safe_load(manifest.read_text(encoding="utf-8"))
    for g in data["groups"]:
        if g["id"] == "mcp_config":
            g["files"][0]["merge"] = True
    manifest.write_text(yaml.safe_dump(data), encoding="utf-8")

    m = installer.load_manifest(manifest)
    plan1 = installer.build_plan(m, fake_repo)
    installer.apply_plan(plan1, m, run_env=None)

    # User manually adds a custom server.
    mcp_path = plan1.target_root / ".mcp.json"
    existing = json.loads(mcp_path.read_text(encoding="utf-8"))
    existing["mcpServers"]["user-obsidian"] = {"command": "npx", "args": ["user-mcp"]}
    mcp_path.write_text(json.dumps(existing), encoding="utf-8")

    # Bump SHA so build_plan considers us outdated.
    (plan1.target_root / ".jarvis-version").write_text("old-sha\n", encoding="utf-8")
    plan2 = installer.build_plan(m, fake_repo)
    installer.apply_plan(plan2, m, run_env=None)

    final = json.loads(mcp_path.read_text(encoding="utf-8"))
    # User-added server preserved across re-apply.
    assert final["mcpServers"]["user-obsidian"]["command"] == "npx"
    # Jarvis-owned server present.
    assert "memory" in final["mcpServers"]
    assert "run-memory-server.py" in final["mcpServers"]["memory"]["args"][0]
    # No duplicates — idempotency check.
    assert len(final["mcpServers"]) == 2


def test_merge_action_kind_in_plan(manifest: Path, fake_repo: Path) -> None:
    """Entries flagged `merge: true` produce merge_json actions, not copy_file."""
    data = yaml.safe_load(manifest.read_text(encoding="utf-8"))
    for g in data["groups"]:
        if g["id"] == "hooks_settings":
            g["files"][0]["merge"] = True
    manifest.write_text(yaml.safe_dump(data), encoding="utf-8")
    m = installer.load_manifest(manifest)
    plan = installer.build_plan(m, fake_repo)
    kinds = {a.group: a.kind for a in plan.actions if a.group}
    assert kinds.get("hooks_settings") == "merge_json"
    assert kinds.get("mcp_config") == "copy_file"  # not flagged, stays copy


def test_real_userlevel_templates_rewrite_scripts_paths(fake_repo: Path) -> None:
    """The real .claude-userlevel/ templates must get scripts/ -> abs rewritten.

    Post-M4 (#339): settings.json no longer has a `config/SOUL.md`
    reference — SOUL is read from `{{CLAUDE_USER_HOME}}/SOUL.md`.
    """
    repo_root = Path(__file__).resolve().parents[1]
    settings_src = repo_root / ".claude-userlevel" / "settings.json"
    mcp_src = repo_root / ".claude-userlevel" / ".mcp.json"

    settings_rendered = installer.template_content(
        settings_src, repo_root, Path("/opt/fake/.claude")
    ).decode("utf-8")
    mcp_rendered = installer.template_content(
        mcp_src, repo_root, Path("/opt/fake/.claude")
    ).decode("utf-8")

    repo_posix = repo_root.as_posix()
    # Every `scripts/` reference in the rendered output is absolute-rooted.
    assert "python scripts/" not in settings_rendered
    assert f"{repo_posix}/scripts/" in settings_rendered
    # mcp: args use relative paths that should rewrite too.
    assert f"{repo_posix}/scripts/run-memory-server.py" in mcp_rendered


def test_userlevel_skills_dir_exists_and_has_whitelisted_skills() -> None:
    """Source-of-truth directory must exist with every whitelisted skill."""
    repo_root = Path(__file__).resolve().parents[1]
    src = repo_root / ".claude-userlevel" / "skills"
    assert src.is_dir(), f"{src} must exist — M2 source of truth"

    m = installer.load_manifest(repo_root / "install-manifest.yaml")
    include = next(
        d["include"]
        for g in m["groups"] if g["id"] == "skills"
        for d in g["directories"]
    )
    for name in include:
        skill_md = src / name / "SKILL.md"
        assert skill_md.exists(), f"whitelisted skill missing: {skill_md}"


# ── #350: backup tolerates files that vanish mid-copy ────────────────


def test_backup_tolerates_vanished_file(
    manifest: Path, fake_repo: Path, monkeypatch, capsys
) -> None:
    """Claude Code rotates files in ~/.claude/debug/ while the installer runs.
    shutil.copytree would abend the whole install with shutil.Error; we patch
    _copy_tolerant onto shutil.copy2 so the backup completes and the install
    proceeds, logging the skipped entry to stderr."""
    m = installer.load_manifest(manifest)
    plan1 = installer.build_plan(m, fake_repo)
    installer.apply_plan(plan1, m, run_env=None)

    # Create an extra debug entry that will "vanish" during the next backup.
    debug_dir = plan1.target_root / "debug"
    debug_dir.mkdir(exist_ok=True)
    vanishing = debug_dir / "latest"
    vanishing.write_text("ephemeral\n", encoding="utf-8")

    real_copy2 = installer.shutil.copy2

    def flaky_copy2(src, dst, *, follow_symlinks=True):
        if str(src).endswith("latest"):
            raise FileNotFoundError(2, "simulated mid-copy vanish", str(src))
        return real_copy2(src, dst, follow_symlinks=follow_symlinks)

    monkeypatch.setattr(installer.shutil, "copy2", flaky_copy2)

    # Trigger outdated re-apply → exercises the backup path.
    (plan1.target_root / ".jarvis-version").write_text("old-sha\n", encoding="utf-8")
    plan2 = installer.build_plan(m, fake_repo)
    assert plan2.state == "outdated"

    # Must NOT raise. Backup completes; skipped entry is logged to stderr.
    installer.apply_plan(plan2, m, run_env=None)

    assert plan2.backup_path.exists()
    assert (plan2.backup_path / "SOUL.md").exists()
    assert not (plan2.backup_path / "debug" / "latest").exists()  # the vanishing one
    stderr = capsys.readouterr().err
    assert "unreadable" in stderr and "latest" in stderr


def test_backup_tolerates_locked_file(
    manifest: Path, fake_repo: Path, monkeypatch, capsys
) -> None:
    """Windows log rotation can hold a PermissionError on the file being appended to.
    Same tolerance applies (#350 review nit)."""
    m = installer.load_manifest(manifest)
    plan1 = installer.build_plan(m, fake_repo)
    installer.apply_plan(plan1, m, run_env=None)

    (plan1.target_root / "debug").mkdir(exist_ok=True)
    (plan1.target_root / "debug" / "locked.log").write_text("x\n", encoding="utf-8")

    real_copy2 = installer.shutil.copy2

    def locked_copy2(src, dst, *, follow_symlinks=True):
        if str(src).endswith("locked.log"):
            raise PermissionError(13, "file is locked by another process", str(src))
        return real_copy2(src, dst, follow_symlinks=follow_symlinks)

    monkeypatch.setattr(installer.shutil, "copy2", locked_copy2)

    (plan1.target_root / ".jarvis-version").write_text("old-sha\n", encoding="utf-8")
    plan2 = installer.build_plan(m, fake_repo)
    installer.apply_plan(plan2, m, run_env=None)

    assert plan2.backup_path.exists()
    assert not (plan2.backup_path / "debug" / "locked.log").exists()
    assert "locked.log" in capsys.readouterr().err


# ---------- legacy parent-dir .mcp.json quarantine ----------


def _legacy_mcp_payload(rel_path: str = "jarvis/scripts/run-memory-server.py") -> str:
    return json.dumps(
        {"mcpServers": {"memory": {"command": "python", "args": [rel_path]}}},
        indent=2,
    )


def test_find_legacy_parent_mcp_detects_relative_jarvis_refs(tmp_path: Path) -> None:
    repo = tmp_path / "Github" / "jarvis"
    repo.mkdir(parents=True)
    legacy = tmp_path / "Github" / ".mcp.json"
    legacy.write_text(_legacy_mcp_payload(), encoding="utf-8")

    found = installer.find_legacy_parent_mcp(repo)
    assert legacy.resolve() in [p.resolve() for p in found]


def test_find_legacy_parent_mcp_ignores_absolute_paths(tmp_path: Path) -> None:
    repo = tmp_path / "Github" / "jarvis"
    repo.mkdir(parents=True)
    correct = tmp_path / "Github" / ".mcp.json"
    correct.write_text(
        _legacy_mcp_payload(rel_path=str(repo / "scripts" / "run-memory-server.py")),
        encoding="utf-8",
    )

    assert installer.find_legacy_parent_mcp(repo) == []


def test_find_legacy_parent_mcp_ignores_unrelated_mcp_configs(tmp_path: Path) -> None:
    repo = tmp_path / "Github" / "jarvis"
    repo.mkdir(parents=True)
    unrelated = tmp_path / "Github" / ".mcp.json"
    unrelated.write_text(
        json.dumps({"mcpServers": {"foo": {"command": "npx", "args": ["foo-mcp"]}}}),
        encoding="utf-8",
    )

    assert installer.find_legacy_parent_mcp(repo) == []


def test_apply_plan_quarantines_legacy_parent_mcp(
    manifest: Path, fake_repo: Path
) -> None:
    legacy = fake_repo.parent / ".mcp.json"
    legacy.write_text(_legacy_mcp_payload(), encoding="utf-8")

    m = installer.load_manifest(manifest)
    plan = installer.build_plan(m, fake_repo)

    quarantine = [a for a in plan.actions if a.kind == "quarantine_file"]
    assert any(Path(a.source).resolve() == legacy.resolve() for a in quarantine)

    installer.apply_plan(plan, m, run_env=None)

    assert not legacy.exists()
    assert (legacy.parent / ".mcp.json.bak.pre-jarvis-migration").exists()


def test_quarantine_dest_avoids_clobbering_existing_bak(tmp_path: Path) -> None:
    legacy = tmp_path / ".mcp.json"
    legacy.write_text("{}", encoding="utf-8")
    existing_bak = tmp_path / ".mcp.json.bak.pre-jarvis-migration"
    existing_bak.write_text("{}", encoding="utf-8")

    dest = installer._quarantine_dest(legacy)
    assert dest != existing_bak
    assert dest.name.startswith(".mcp.json.bak.pre-jarvis-migration-")


# ---------- user-scope MCP registration ----------


def _user_mcp_manifest(fake_repo: Path, target_root: Path) -> Path:
    """Manifest variant that registers MCPs via `claude mcp add` instead of copying."""
    data = {
        "version": 1,
        "target_root": str(target_root),
        "version_marker": ".jarvis-version",
        "groups": [
            {
                "id": "mcp_config",
                "enabled": True,
                "files": [
                    {
                        "source": ".mcp.json",
                        "install_as": "user_mcp_registrations",
                        "template": True,
                    }
                ],
            },
        ],
        "env_vars": [],
        "health_check": {"enabled": False},
        "backup": {"prefix": ".claude.backup-", "retain": 3},
    }
    path = fake_repo / "install-manifest-user-mcp.yaml"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    return path


def test_plan_user_mcp_registrations_emits_action_per_server(
    fake_repo: Path, tmp_path: Path
) -> None:
    target = tmp_path / "claude_home"
    manifest_path = _user_mcp_manifest(fake_repo, target)
    m = installer.load_manifest(manifest_path)
    plan = installer.build_plan(m, fake_repo)

    regs = [a for a in plan.actions if a.kind == "register_mcp_user"]
    assert len(regs) == 1
    payload = json.loads(regs[0].note)
    assert payload["name"] == "memory"
    assert payload["spec"]["command"] == "python"
    # Path templating applied — relative `scripts/...` rewritten to absolute.
    assert payload["spec"]["args"][0].startswith(fake_repo.as_posix() + "/scripts/")


def test_plan_user_mcp_registrations_quarantines_stale_target_file(
    fake_repo: Path, tmp_path: Path
) -> None:
    target = tmp_path / "claude_home"
    target.mkdir()
    stale = target / ".mcp.json"
    stale.write_text("{}", encoding="utf-8")

    manifest_path = _user_mcp_manifest(fake_repo, target)
    m = installer.load_manifest(manifest_path)
    plan = installer.build_plan(m, fake_repo)

    quarantine = [a for a in plan.actions if a.kind == "quarantine_file"]
    assert any(Path(a.source).resolve() == stale.resolve() for a in quarantine)


def test_apply_register_mcp_user_calls_injected_runner(
    fake_repo: Path, tmp_path: Path
) -> None:
    target = tmp_path / "claude_home"
    manifest_path = _user_mcp_manifest(fake_repo, target)
    m = installer.load_manifest(manifest_path)
    plan = installer.build_plan(m, fake_repo)

    calls: list[tuple[str, dict]] = []

    def fake_register(name: str, spec: dict) -> None:
        calls.append((name, spec))

    installer.apply_plan(plan, m, run_env=None, register_mcp=fake_register)

    assert calls and calls[0][0] == "memory"
    assert calls[0][1]["command"] == "python"


def test_register_mcp_user_stdio_command_shape(monkeypatch) -> None:
    captured: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        captured.append(list(cmd))
        class R:
            returncode = 0
            stdout = ""
            stderr = ""
        return R()

    monkeypatch.setattr(installer.subprocess, "run", fake_run)
    installer._register_mcp_user(
        "memory",
        {"command": "python", "args": ["/abs/run.py"], "env": {"K": "V"}},
    )

    # First call: idempotent remove. Second: add — name BEFORE -e to avoid
    # the variadic -e swallowing the positional (#432).
    assert captured[0][:5] == ["claude", "mcp", "remove", "-s", "user"]
    add = captured[1]
    assert add[:5] == ["claude", "mcp", "add", "-s", "user"]
    # Layout: ... -s user <name> -e K=V -- <command> <args...>
    name_idx = add.index("memory")
    assert "-e" in add and "K=V" in add
    e_idx = add.index("-e")
    assert name_idx < e_idx, "name must come BEFORE -e (variadic eats positional)"
    assert "--" in add
    dd = add.index("--")
    assert e_idx < dd, "-e must come BEFORE -- separator"
    assert add[dd + 1 :] == ["python", "/abs/run.py"]


def test_register_mcp_user_stdio_command_shape_no_env(monkeypatch) -> None:
    """Stdio without env vars — name still goes before `--` boundary."""
    captured: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        captured.append(list(cmd))
        class R:
            returncode = 0
            stdout = ""
            stderr = ""
        return R()

    monkeypatch.setattr(installer.subprocess, "run", fake_run)
    installer._register_mcp_user("simple", {"command": "uvx", "args": ["foo-mcp"]})

    add = captured[1]
    dd = add.index("--")
    # No -e flag should appear when env is absent.
    assert "-e" not in add
    # Layout: ... -s user simple -- uvx foo-mcp
    assert add[dd - 1] == "simple"
    assert add[dd + 1 :] == ["uvx", "foo-mcp"]


def test_register_mcp_user_http_command_shape(monkeypatch) -> None:
    captured: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        captured.append(list(cmd))
        class R:
            returncode = 0
            stdout = ""
            stderr = ""
        return R()

    monkeypatch.setattr(installer.subprocess, "run", fake_run)
    installer._register_mcp_user(
        "remote",
        {
            "type": "http",
            "url": "https://example.com/mcp",
            "headers": {"Authorization": "Bearer xxx"},
        },
    )

    add = captured[1]
    assert "--transport" in add and "http" in add
    assert "-H" in add and "Authorization: Bearer xxx" in add
    # Layout: ... --transport http <name> <url> -H "..." (#432)
    # Headers AFTER positionals so variadic -H doesn't eat <name>.
    name_idx = add.index("remote")
    url_idx = add.index("https://example.com/mcp")
    h_idx = add.index("-H")
    assert name_idx < url_idx < h_idx, "positionals must come BEFORE -H (variadic)"


def test_register_mcp_user_http_no_headers(monkeypatch) -> None:
    """HTTP server without auth headers — clean positional layout."""
    captured: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        captured.append(list(cmd))
        class R:
            returncode = 0
            stdout = ""
            stderr = ""
        return R()

    monkeypatch.setattr(installer.subprocess, "run", fake_run)
    installer._register_mcp_user(
        "open-mcp",
        {"type": "http", "url": "https://example.com/mcp"},
    )

    add = captured[1]
    assert "-H" not in add
    assert add[-2:] == ["open-mcp", "https://example.com/mcp"]


def test_register_mcp_user_raises_on_add_failure(monkeypatch) -> None:
    seq = iter([0, 1])  # remove succeeds, add fails

    def fake_run(cmd, **kwargs):
        class R:
            returncode = next(seq)
            stdout = ""
            stderr = "boom"
        return R()

    monkeypatch.setattr(installer.subprocess, "run", fake_run)
    with pytest.raises(RuntimeError, match="claude mcp add failed"):
        installer._register_mcp_user("x", {"command": "y", "args": []})


def test_unknown_install_as_raises(fake_repo: Path, tmp_path: Path) -> None:
    target = tmp_path / "claude_home"
    bad = {
        "version": 1,
        "target_root": str(target),
        "version_marker": ".jarvis-version",
        "groups": [
            {
                "id": "mcp_config",
                "enabled": True,
                "files": [
                    {"source": ".mcp.json", "install_as": "bogus", "template": True}
                ],
            }
        ],
    }
    path = fake_repo / "bad-manifest.yaml"
    path.write_text(yaml.safe_dump(bad), encoding="utf-8")
    m = installer.load_manifest(path)
    with pytest.raises(ValueError, match="unknown install_as"):
        installer.build_plan(m, fake_repo)

"""Tests for scripts/protected-files.py — protected file detection."""

import sys
import os
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import importlib
protected_files = importlib.import_module("protected-files")

is_protected = protected_files.is_protected
normalize_path = protected_files.normalize_path


@pytest.fixture
def fake_claude_home(tmp_path, monkeypatch):
    """Pin ``JARVIS_CLAUDE_HOME`` to a tmp dir so user-level assertions don't
    depend on the developer's real home."""
    home = tmp_path / ".claude"
    monkeypatch.setenv("JARVIS_CLAUDE_HOME", str(home))
    return home.as_posix().rstrip("/")


# ── Protected files: blocked ─────────────────────────────────────────

def test_blocks_mcp_json():
    assert is_protected(".mcp.json")

def test_blocks_soul_md():
    assert is_protected("config/SOUL.md")

def test_blocks_claude_md():
    assert is_protected("CLAUDE.md")

def test_blocks_server_py():
    assert is_protected("mcp-memory/server.py")

def test_blocks_settings_json():
    assert is_protected(".claude/settings.json")

def test_blocks_gitleaks():
    assert is_protected(".gitleaks.toml")

def test_blocks_pre_commit():
    assert is_protected(".pre-commit-config.yaml")


# ── Absolute paths (Windows-style) ──────────────────────────────────

def test_blocks_absolute_windows():
    assert is_protected("C:\\Users\\petrk\\GitHub\\jarvis\\CLAUDE.md")

def test_blocks_absolute_forward_slash():
    assert is_protected("C:/Users/petrk/GitHub/jarvis/config/SOUL.md")


# ── Non-protected files: allowed ─────────────────────────────────────

def test_allows_regular_python():
    assert not is_protected("scripts/secret-scanner.py")

def test_allows_docs():
    assert not is_protected("docs/PROJECT_PLAN.md")

def test_allows_tests():
    assert not is_protected("tests/test_secret_scanner.py")

def test_allows_skill():
    assert not is_protected(".claude/skills/delegate/SKILL.md")

def test_allows_other_json():
    assert not is_protected("config/device.json")


# ── Normalize path ──────────────────────────────────────────────────

def test_normalize_backslashes():
    assert normalize_path("config\\SOUL.md") == "config/SOUL.md"

def test_normalize_leading_dot_slash():
    assert normalize_path("./CLAUDE.md") == "CLAUDE.md"

def test_normalize_absolute():
    assert normalize_path("C:/Users/petrk/GitHub/jarvis/CLAUDE.md") == "CLAUDE.md"


# ── User-level (~/.claude/) paths: blocked ───────────────────────────

def test_blocks_user_level_settings(fake_claude_home):
    assert is_protected(f"{fake_claude_home}/settings.json")


def test_blocks_user_level_soul(fake_claude_home):
    assert is_protected(f"{fake_claude_home}/SOUL.md")


def test_blocks_user_level_mcp(fake_claude_home):
    assert is_protected(f"{fake_claude_home}/.mcp.json")


def test_blocks_user_level_skill(fake_claude_home):
    assert is_protected(f"{fake_claude_home}/skills/implement/SKILL.md")


def test_blocks_user_level_skill_backslashes(fake_claude_home):
    # Normalize must handle native Windows separators on the user-level surface too.
    winpath = fake_claude_home.replace("/", "\\") + "\\skills\\delegate\\SKILL.md"
    assert is_protected(winpath)


# ── User-level: look-alike paths allowed ────────────────────────────

def test_allows_other_project_claude_settings(fake_claude_home, tmp_path):
    """`.claude/settings.json` inside some unrelated repo is NOT user-level —
    and since normalize_path doesn't strip its prefix, it must not match
    the repo-level `.claude/settings.json` entry either."""
    other = (tmp_path / "other-project" / ".claude" / "settings.json").as_posix()
    assert not is_protected(other)


def test_allows_user_level_non_protected(fake_claude_home):
    # Files under ~/.claude/ that aren't on the list (e.g. projects/, history) stay allowed.
    assert not is_protected(f"{fake_claude_home}/projects/some-project/history.jsonl")


def test_allows_user_level_skill_subresource(fake_claude_home):
    # Only SKILL.md itself is protected — co-located scripts or resources aren't.
    assert not is_protected(f"{fake_claude_home}/skills/implement/helper.py")

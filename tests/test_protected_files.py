"""Tests for scripts/protected-files.py — protected file detection."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import importlib
protected_files = importlib.import_module("protected-files")

is_protected = protected_files.is_protected
normalize_path = protected_files.normalize_path


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

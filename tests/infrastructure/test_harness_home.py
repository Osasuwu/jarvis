"""Tests for the harness seam — ``scripts/lib/harness`` (#1741, design S7).

Covers the seam's own contract (home resolution, detection order, default) and
call-site parity: each of the five modules that previously recomputed the agent
home inline now resolves through the seam and yields the identical path with and
without the ``JARVIS_CLAUDE_HOME`` override.
"""

from __future__ import annotations

import importlib
import importlib.util
from pathlib import Path

import pytest
from lib import harness
from lib.harness.base import Harness
from lib.harness.claude_code import ClaudeCodeHarness

_REPO_ROOT = Path(__file__).resolve().parents[2]


def _expected_home(monkeypatch, override: str | None) -> Path:
    """Resolve the home the seam should produce for a given override state."""
    if override is None:
        monkeypatch.delenv("JARVIS_CLAUDE_HOME", raising=False)
        return Path.home() / ".claude"
    monkeypatch.setenv("JARVIS_CLAUDE_HOME", override)
    return Path(override).expanduser()


# ── Seam contract: home() ────────────────────────────────────────────────────

def test_home_honours_override(monkeypatch, tmp_path):
    override = str(tmp_path / "custom-home")
    expected = _expected_home(monkeypatch, override)
    assert harness.home() == expected


def test_home_defaults_to_dot_claude(monkeypatch):
    expected = _expected_home(monkeypatch, None)
    assert harness.home() == expected


def test_home_read_at_call_time(monkeypatch, tmp_path):
    """The override is re-read on every call — no import-time caching in the seam."""
    monkeypatch.delenv("JARVIS_CLAUDE_HOME", raising=False)
    assert harness.home() == Path.home() / ".claude"
    monkeypatch.setenv("JARVIS_CLAUDE_HOME", str(tmp_path))
    assert harness.home() == tmp_path


# ── Seam contract: resolution order ($JARVIS_HARNESS → autodetect → default) ──

def test_unset_harness_yields_claude_code(monkeypatch):
    monkeypatch.delenv("JARVIS_HARNESS", raising=False)
    assert harness.resolve().name == "claude-code"


def test_unknown_harness_yields_claude_code(monkeypatch):
    monkeypatch.setenv("JARVIS_HARNESS", "does-not-exist")
    assert harness.resolve().name == "claude-code"


def test_explicit_harness_selects_by_name(monkeypatch):
    monkeypatch.setenv("JARVIS_HARNESS", "claude-code")
    assert harness.resolve().name == "claude-code"


def test_explicit_wins_over_autodetect(monkeypatch):
    """Explicit valid name is honoured even when it differs from autodetect.

    With one adapter the observable result is still claude-code, but this pins
    the *order*: the explicit branch runs before any detect() call. A stub
    adapter whose detect() is always true must not override an explicit match.
    """

    class _NeverDefault(Harness):
        name = "stub-explicit"

        def home(self) -> Path:  # pragma: no cover - not exercised here
            return Path("/stub")

        @classmethod
        def detect(cls) -> bool:
            return True

    monkeypatch.setattr(harness, "_BY_NAME", {"stub-explicit": _NeverDefault})
    monkeypatch.setattr(harness, "_ADAPTERS", (ClaudeCodeHarness,))
    monkeypatch.setenv("JARVIS_HARNESS", "stub-explicit")
    assert harness.resolve().name == "stub-explicit"


def test_base_detect_defaults_false():
    """A new adapter is never autodetected until it opts in."""
    assert Harness.detect() is False


# ── Call-site parity: each former inline copy routes through the seam ─────────

def _load_hyphenated(name: str, rel: str):
    """Load a dash-named script fresh so its import-time home is recomputed."""
    spec = importlib.util.spec_from_file_location(name, _REPO_ROOT / rel)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# module attribute holding the import-time resolved home, per call site
_MODULE_CALL_SITES = [
    ("scripts/memory-recall-hook.py", "memory_recall_hook_home"),
    ("scripts/pretooluse-recall-hook.py", "pretooluse_recall_hook_home"),
    ("scripts/record-decision-gate.py", "record_decision_gate_home"),
]


@pytest.mark.parametrize("override", [None, "override"])
@pytest.mark.parametrize("rel,modname", _MODULE_CALL_SITES)
def test_hyphenated_call_sites_match_seam(monkeypatch, tmp_path, rel, modname, override):
    ovr = None if override is None else str(tmp_path / override)
    expected = _expected_home(monkeypatch, ovr)
    module = _load_hyphenated(modname, rel)
    assert module._CLAUDE_HOME == expected


@pytest.mark.parametrize("override", [None, "override"])
def test_recall_dedup_matches_seam(monkeypatch, tmp_path, override):
    ovr = None if override is None else str(tmp_path / override)
    expected = _expected_home(monkeypatch, ovr)
    from lib import recall_dedup

    reloaded = importlib.reload(recall_dedup)
    assert reloaded._CLAUDE_HOME == expected


@pytest.mark.parametrize("override", [None, "override"])
def test_protected_files_matches_seam(monkeypatch, tmp_path, override):
    ovr = None if override is None else str(tmp_path / override)
    expected = _expected_home(monkeypatch, ovr)
    protected_files = importlib.import_module("protected-files")
    # Call-time resolver: no reload needed, override is re-read on each call.
    assert protected_files._user_claude_home() == expected.as_posix().rstrip("/")

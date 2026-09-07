"""Tests for scripts/setup-device.py::setup_venv() (#1312 AC#7).

setup_venv() must delegate dependency installation to scripts/lib/env_sync.py
(check + heal) instead of running its own inline pip block, while preserving
its existing int-return contract (main() does `errors += setup_venv()`).
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

_PATH = Path(__file__).resolve().parent.parent.parent / "scripts" / "setup-device.py"
_REPO_ROOT = _PATH.resolve().parent.parent
_spec = importlib.util.spec_from_file_location("setup_device", _PATH)
sd = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sd)

_FAKE_ENV = SimpleNamespace(name="main")


def _fake_check(in_sync, reason=None):
    return SimpleNamespace(in_sync=in_sync, reason=reason, old_hash=None, new_hash=None)


def _fake_heal(success, reason=None):
    return SimpleNamespace(
        success=success, reason=reason, old_hash=None, new_hash=None, log_path=None
    )


@pytest.fixture(autouse=True)
def _existing_venv(tmp_path, monkeypatch):
    """Point ROOT at a scratch dir with .venv already present, so tests don't
    exercise the real repo venv or the `python -m venv` creation subprocess."""
    (tmp_path / ".venv").mkdir()
    monkeypatch.setattr(sd, "ROOT", tmp_path)
    return tmp_path


def test_setup_venv_skips_heal_when_in_sync(monkeypatch):
    monkeypatch.setattr(sd.env_sync, "get_env", lambda name: _FAKE_ENV)
    monkeypatch.setattr(sd.env_sync, "check", lambda env: _fake_check(in_sync=True))

    def _boom(env, *a, **k):
        raise AssertionError("heal() must not be called when already in sync")

    monkeypatch.setattr(sd.env_sync, "heal", _boom)

    assert sd.setup_venv() == 0


def test_setup_venv_heals_on_drift_and_succeeds(monkeypatch):
    calls = []
    monkeypatch.setattr(sd.env_sync, "get_env", lambda name: _FAKE_ENV)
    monkeypatch.setattr(sd.env_sync, "check", lambda env: _fake_check(in_sync=False))
    monkeypatch.setattr(
        sd.env_sync,
        "heal",
        lambda env, **k: (calls.append(env), _fake_heal(success=True))[1],
    )

    assert sd.setup_venv() == 0
    assert len(calls) == 1


def test_setup_venv_returns_1_on_heal_failure(monkeypatch, capsys):
    monkeypatch.setattr(sd.env_sync, "get_env", lambda name: _FAKE_ENV)
    monkeypatch.setattr(sd.env_sync, "check", lambda env: _fake_check(in_sync=False))
    monkeypatch.setattr(
        sd.env_sync, "heal", lambda env, **k: _fake_heal(success=False, reason="disk full")
    )

    assert sd.setup_venv() == 1
    assert "disk full" in capsys.readouterr().out


def test_setup_venv_returns_1_when_registry_missing_main_env(monkeypatch, capsys):
    monkeypatch.setattr(sd.env_sync, "get_env", lambda name: None)

    assert sd.setup_venv() == 1
    assert "main" in capsys.readouterr().out.lower() or "registry" in capsys.readouterr().out.lower()


def test_setup_venv_creates_venv_dir_when_missing(tmp_path, monkeypatch):
    empty_root = tmp_path / "no-venv-yet"
    empty_root.mkdir()
    monkeypatch.setattr(sd, "ROOT", empty_root)  # no .venv/ created this time
    calls = []
    monkeypatch.setattr(sd.subprocess, "run", lambda cmd, **k: calls.append(cmd))
    monkeypatch.setattr(sd.env_sync, "get_env", lambda name: _FAKE_ENV)
    monkeypatch.setattr(sd.env_sync, "check", lambda env: _fake_check(in_sync=True))

    sd.setup_venv()

    assert len(calls) == 1
    assert "venv" in calls[0]


def test_setup_venv_source_never_invokes_pip_directly():
    source = _PATH.read_text(encoding="utf-8")
    assert "pip.exe" not in source
    assert "pip install" not in source.split("def setup_venv")[1].split("\ndef ")[0]


def test_setup_venv_heal_uses_longer_timeout_than_env_sync_default(monkeypatch):
    """A from-scratch device setup installs ~90 packages (numpy, cryptography,
    pillow, tokenizers) -- verified in real smoke test to take ~80s even with
    cached wheels, well past env_sync's DEFAULT_HEAL_TIMEOUT=40 (#1312).
    setup_venv() must pass a longer timeout so first-time installs don't
    spuriously fail as 'pip_failed'."""
    calls = []
    monkeypatch.setattr(sd.env_sync, "get_env", lambda name: _FAKE_ENV)
    monkeypatch.setattr(sd.env_sync, "check", lambda env: _fake_check(in_sync=False))
    monkeypatch.setattr(
        sd.env_sync,
        "heal",
        lambda env, **k: (calls.append(k), _fake_heal(success=True))[1],
    )

    sd.setup_venv()

    assert len(calls) == 1
    assert calls[0].get("timeout", sd.env_sync.DEFAULT_HEAL_TIMEOUT) > sd.env_sync.DEFAULT_HEAL_TIMEOUT


def test_claude_plugins_local_entries_match_vendored_marketplace():
    """Every CLAUDE_PLUGINS entry that points at the vendored
    .claude/marketplace/ local marketplace must actually exist in that
    marketplace.json's plugin list (#1797). The manifest was pruned to hold
    only the fork-pinned `code-review` plugin (the rest are unmodified
    upstream Anthropic plugins, installed straight from the official
    claude-plugins-official marketplace instead) -- if CLAUDE_PLUGINS still
    lists a pruned id against marketplace_path=.claude/marketplace,
    install_claude_plugins() would try to install a ghost entry that no
    longer exists in the local manifest."""
    manifest_path = _REPO_ROOT / ".claude" / "marketplace" / ".claude-plugin" / "marketplace.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    vendored_names = {p["name"] for p in manifest["plugins"]}

    local_entries = [e for e in sd.CLAUDE_PLUGINS if e.get("marketplace_path")]
    assert local_entries, "expected at least one locally-vendored plugin entry"
    for entry in local_entries:
        assert entry["plugin"] in vendored_names, (
            f"{entry['plugin']} references .claude/marketplace but is not in its "
            f"marketplace.json plugin list {sorted(vendored_names)} -- "
            "CLAUDE_PLUGINS is out of sync with the vendored manifest"
        )


def test_install_claude_plugins_installs_every_entry(monkeypatch, tmp_path):
    """install_claude_plugins() must install every CLAUDE_PLUGINS entry, not
    just ones vendored via a local marketplace_path (#1797). A plugin
    classified OFFICIAL has no marketplace_path -- it installs straight from
    the already-registered claude-plugins-official marketplace name, with no
    local `marketplace add`/`update` step. The pre-fix implementation
    indexed entry["marketplace_path"] unconditionally and KeyErrors on such
    an entry."""
    monkeypatch.setattr(sd, "ROOT", tmp_path)
    local_mp = tmp_path / ".claude" / "marketplace"
    local_mp.mkdir(parents=True)

    monkeypatch.setattr(
        sd,
        "CLAUDE_PLUGINS",
        [
            {
                "plugin": "code-review",
                "marketplace": "jarvis-fork-plugins",
                "marketplace_path": ".claude/marketplace",
                "purpose": "vendored fork",
            },
            {
                "plugin": "pr-review-toolkit",
                "marketplace": "claude-plugins-official",
                "purpose": "official marketplace, no local vendoring",
            },
        ],
    )
    monkeypatch.setattr(sd.shutil, "which", lambda name: "/usr/bin/claude")

    calls = []

    def _fake_run(cmd, **kwargs):
        calls.append(cmd)
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(sd.subprocess, "run", _fake_run)

    sd.install_claude_plugins()

    install_calls = [c for c in calls if "install" in c]
    installed_specs = {c[c.index("install") + 1] for c in install_calls}
    assert installed_specs == {
        "code-review@jarvis-fork-plugins",
        "pr-review-toolkit@claude-plugins-official",
    }

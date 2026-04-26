"""Tests for scripts/principal.py — principal detection (#426)."""

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import principal  # noqa: E402


# ── Fixtures ─────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    """Strip JARVIS_PRINCIPAL and headless markers before each test so the
    detection chain starts from a clean slate.
    """
    monkeypatch.delenv("JARVIS_PRINCIPAL", raising=False)
    for name in principal._HEADLESS_ENV_VARS:
        monkeypatch.delenv(name, raising=False)


class _FakeStdin:
    """Stand-in for sys.stdin with a configurable isatty()."""

    def __init__(self, tty: bool):
        self._tty = tty

    def isatty(self) -> bool:
        return self._tty


@pytest.fixture
def fake_tty(monkeypatch):
    """Force isatty()=True so default falls through to ``live``."""
    monkeypatch.setattr(sys, "stdin", _FakeStdin(tty=True))


@pytest.fixture
def fake_no_tty(monkeypatch):
    """Force isatty()=False so default falls through to ``autonomous``."""
    monkeypatch.setattr(sys, "stdin", _FakeStdin(tty=False))


# ── Explicit env var (primary signal) ────────────────────────────────


@pytest.mark.parametrize(
    "value",
    ["live", "autonomous", "subagent", "supervised"],
)
def test_explicit_env_each_valid_value(monkeypatch, fake_no_tty, value):
    """Explicit JARVIS_PRINCIPAL wins over fallback detection."""
    monkeypatch.setenv("JARVIS_PRINCIPAL", value)
    assert principal.detect() == value


def test_explicit_env_uppercase_normalized(monkeypatch, fake_no_tty):
    monkeypatch.setenv("JARVIS_PRINCIPAL", "LIVE")
    assert principal.detect() == "live"


def test_explicit_env_whitespace_stripped(monkeypatch, fake_no_tty):
    monkeypatch.setenv("JARVIS_PRINCIPAL", "  autonomous  ")
    assert principal.detect() == "autonomous"


def test_explicit_env_invalid_falls_through_to_autonomous(monkeypatch, fake_no_tty):
    """An invalid value is ignored; chain continues — no TTY → autonomous.

    Default-safe property: a typo doesn't escalate to ``live``.
    """
    monkeypatch.setenv("JARVIS_PRINCIPAL", "garbage")
    assert principal.detect() == "autonomous"


def test_explicit_env_invalid_falls_through_to_live(monkeypatch, fake_tty):
    """Same chain with TTY available: invalid env → TTY check → live."""
    monkeypatch.setenv("JARVIS_PRINCIPAL", "root")
    assert principal.detect() == "live"


def test_explicit_env_empty_treated_as_unset(monkeypatch, fake_tty):
    monkeypatch.setenv("JARVIS_PRINCIPAL", "")
    assert principal.detect() == "live"


# ── Headless env (suspenders) ────────────────────────────────────────


@pytest.mark.parametrize("var_name", principal._HEADLESS_ENV_VARS)
def test_headless_env_forces_autonomous_even_with_tty(monkeypatch, fake_tty, var_name):
    """Headless env wins over a misleading TTY signal."""
    monkeypatch.setenv(var_name, "1")
    assert principal.detect() == "autonomous"


@pytest.mark.parametrize("falsy", ["0", "false", "no", "FALSE", " "])
def test_headless_env_falsy_values_ignored(monkeypatch, fake_tty, falsy):
    """A headless env set to a falsy value isn't a real signal."""
    monkeypatch.setenv("CLAUDE_CODE_NON_INTERACTIVE", falsy)
    assert principal.detect() == "live"


def test_explicit_env_overrides_headless(monkeypatch, fake_tty):
    """Explicit JARVIS_PRINCIPAL still wins over headless env."""
    monkeypatch.setenv("CLAUDE_CODE_NON_INTERACTIVE", "1")
    monkeypatch.setenv("JARVIS_PRINCIPAL", "subagent")
    assert principal.detect() == "subagent"


# ── isatty fallback ──────────────────────────────────────────────────


def test_no_tty_falls_back_to_autonomous(fake_no_tty):
    assert principal.detect() == "autonomous"


def test_tty_falls_back_to_live(fake_tty):
    assert principal.detect() == "live"


# ── Default-safe property check ──────────────────────────────────────


def test_default_safe_no_signals_with_no_tty(fake_no_tty):
    """No env, no TTY — must be ``autonomous``, never ``live``.

    This is THE safety property of detect(): if a future entry-point launches
    Claude headless and forgets to set JARVIS_PRINCIPAL, the principal must
    fall to a constrained mode, not the wide-permissions live mode.
    """
    # No env vars set (clean_env fixture), no TTY.
    assert principal.detect() == "autonomous"

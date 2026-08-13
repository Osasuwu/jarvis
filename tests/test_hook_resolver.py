"""Tests for hook-resolver.py — worktree-aware hook path resolution."""

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest


# Root of the repo
REPO_ROOT = Path(__file__).resolve().parent.parent
HOOK_RESOLVER = REPO_ROOT / "scripts" / "hook-resolver.py"


def _load_hook_resolver():
    """Import hook-resolver.py as a module (works despite the hyphen in the filename)."""
    spec = importlib.util.spec_from_file_location("hook_resolver", HOOK_RESOLVER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestDetectProjectRoot:
    """Unit-test detect_project_root() in isolation."""

    def test_main_checkout_returns_repo_root(self):
        """A path inside the main checkout resolves to the repo root."""
        mod = _load_hook_resolver()
        base = Path("/projects/jarvis")
        result = mod.detect_project_root(str(base / "scripts" / "hook-resolver.py"))
        assert result == base

    def test_reactive_worktree_returns_worktree_root(self):
        """A path inside .reactive/worktrees/<uuid> resolves to the worktree, not main repo."""
        mod = _load_hook_resolver()
        worktree = Path("/projects/jarvis/.reactive/worktrees/abc123-uuid")
        result = mod.detect_project_root(str(worktree / "scripts" / "something.py"))
        assert result == worktree, (
            f"Expected worktree root {worktree}, got {result}. "
            "detect_project_root() must not collapse the path back to the main checkout."
        )

    def test_claude_worktree_returns_worktree_root(self):
        """A path inside .claude/worktrees/<name> resolves to the worktree root."""
        mod = _load_hook_resolver()
        worktree = Path("/projects/jarvis/.claude/worktrees/my-feature")
        result = mod.detect_project_root(str(worktree / "scripts" / "hook-resolver.py"))
        assert result == worktree

    def test_sandcastle_worktree_returns_worktree_root(self):
        """A path inside .sandcastle/worktrees/<name> resolves to the worktree root."""
        mod = _load_hook_resolver()
        worktree = Path("/projects/jarvis/.sandcastle/worktrees/task-20260101")
        result = mod.detect_project_root(str(worktree))
        assert result == worktree

    def test_none_input_returns_none(self):
        """None input must return None without raising."""
        mod = _load_hook_resolver()
        assert mod.detect_project_root(None) is None

    def test_unrelated_path_returns_none(self):
        """A path with no known project component returns None."""
        mod = _load_hook_resolver()
        assert mod.detect_project_root("/tmp/unrelated/path") is None


class TestHookResolverEndToEnd:
    """Subprocess-level tests for the hook-resolver entry point."""

    def test_hook_resolver_exists(self):
        assert HOOK_RESOLVER.exists(), f"hook-resolver.py not found at {HOOK_RESOLVER}"

    def test_detect_project_from_repo_root(self):
        """Running from the repo root detects the project (no 'Could not detect' error)."""
        result = subprocess.run(
            [sys.executable, str(HOOK_RESOLVER), "nonexistent.py"],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
        )
        assert "Could not detect project root" not in result.stderr

    def test_hook_resolver_finds_real_script(self):
        """hook-resolver successfully locates a script that exists."""
        result = subprocess.run(
            [sys.executable, str(HOOK_RESOLVER), "secret-scanner.py", "--help"],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
        )
        assert "Script not found" not in result.stderr or result.returncode == 0

    def test_missing_arg_exits_blocking(self):
        """Invoking without a script name exits with code 2 (blocking), not 1."""
        result = subprocess.run(
            [sys.executable, str(HOOK_RESOLVER)],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
        )
        assert result.returncode == 2, (
            f"Expected exit code 2 (blocking), got {result.returncode}. "
            "Error paths must be fail-closed to prevent silent hook bypass."
        )

    def test_missing_script_exits_blocking(self):
        """A missing target script exits with code 2 (blocking), not 1."""
        result = subprocess.run(
            [sys.executable, str(HOOK_RESOLVER), "definitely-does-not-exist.py"],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
        )
        assert result.returncode == 2, (
            f"Expected exit code 2 (blocking), got {result.returncode}."
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

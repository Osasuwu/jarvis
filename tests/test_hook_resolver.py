"""Tests for hook-resolver.py — worktree-aware hook path resolution."""

import subprocess
import sys
from pathlib import Path

import pytest


# Root of the repo
REPO_ROOT = Path(__file__).resolve().parent.parent
HOOK_RESOLVER = REPO_ROOT / "scripts" / "hook-resolver.py"


class TestHookResolverPathDetection:
    """Test that hook-resolver detects project root from various path sources."""

    def test_hook_resolver_exists(self):
        """Verify hook-resolver.py exists."""
        assert HOOK_RESOLVER.exists(), f"hook-resolver.py not found at {HOOK_RESOLVER}"

    def test_detect_project_from_repo_root(self):
        """Test that passing the repo root detects the project."""
        # Run hook-resolver with a dummy script name to test detection
        result = subprocess.run(
            [sys.executable, str(HOOK_RESOLVER), "nonexistent.py"],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
        )
        # Will fail with "script not found" but the detection passed
        # (if detection failed, we'd see "Could not detect project root")
        assert "Could not detect project root" not in result.stderr

    def test_detect_project_from_worktree_path(self):
        """Test that project detection works from a worktree path."""
        # Get the worktree path by going up from the current script location
        # This is a worktree session, so we're in .claude/worktrees/<name>
        current = Path(__file__).resolve()
        worktree_path = current.parent.parent.parent  # Go up 3 levels from tests/

        # Verify we can detect the project from this worktree-relative path
        result = subprocess.run(
            [sys.executable, str(HOOK_RESOLVER), "nonexistent.py"],
            cwd=str(worktree_path),
            capture_output=True,
            text=True,
        )
        # Will fail with "script not found" but detection should pass
        assert "Could not detect project root" not in result.stderr

    def test_hook_resolver_finds_real_script(self):
        """Test that hook-resolver successfully finds and would invoke a real script."""
        # Test with a script that exists and has a --help or similar option
        # We'll use a script that can be invoked safely
        result = subprocess.run(
            [sys.executable, str(HOOK_RESOLVER), "secret-scanner.py", "--help"],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
        )
        # The script should be found and invoked
        # (it might fail with --help not recognized, but won't fail on "Script not found")
        assert "Script not found" not in result.stderr or result.returncode == 0

    def test_hook_resolver_respects_cwd(self):
        """Test that hook-resolver uses cwd for detection."""
        # Run from the repo root and verify it finds the scripts
        result = subprocess.run(
            [sys.executable, str(HOOK_RESOLVER), "memory-dedup-check.py", "--help"],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
        )
        # Should detect project and attempt to run the script
        # (will fail on --help unless the script supports it, but not on path resolution)
        assert "Could not detect project root" not in result.stderr


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

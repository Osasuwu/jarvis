"""Tests for scripts/hook-resolver.py — #1565.

One test per session-type matrix row (jarvis main / jarvis worktree /
non-jarvis project / non-jarvis project's own worktree), plus exit-code
fail-open vs fail-closed coverage.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import importlib.util

_SPEC = importlib.util.spec_from_file_location(
    "hook_resolver", Path(__file__).resolve().parents[2] / "scripts" / "hook-resolver.py"
)
hook_resolver = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(hook_resolver)


def _make_jarvis_checkout(root: Path, hook_name: str = "session-context.py") -> Path:
    scripts = root / "scripts"
    scripts.mkdir(parents=True)
    (scripts / hook_name).write_text("print('ok')\n", encoding="utf-8")
    return root


# ---------- matrix row 1: jarvis main checkout ----------


def test_row1_jarvis_main_checkout_resolves_directly(tmp_path: Path) -> None:
    main_checkout = tmp_path / "jarvis"
    _make_jarvis_checkout(main_checkout)

    root = hook_resolver.detect_project_root(str(main_checkout))

    assert root == main_checkout


# ---------- matrix row 2: jarvis worktree (must NOT collapse to main checkout) ----------


@pytest.mark.parametrize("worktree_parent", [".claude", ".reactive", ".sandcastle"])
def test_row2_jarvis_worktree_extends_into_own_root(tmp_path: Path, worktree_parent: str) -> None:
    main_checkout = tmp_path / "jarvis"
    _make_jarvis_checkout(main_checkout)
    worktree_root = main_checkout / worktree_parent / "worktrees" / "issue-1565-a70727"
    _make_jarvis_checkout(worktree_root, hook_name="only-in-worktree.py")

    root = hook_resolver.detect_project_root(str(worktree_root))

    assert root == worktree_root
    assert root != main_checkout, "worktree session must not collapse to the main checkout"


# ---------- matrix row 3: non-jarvis project falls back to canonical jarvis install ----------


def test_row3_non_jarvis_project_falls_back_to_canonical_jarvis(tmp_path: Path, monkeypatch) -> None:
    other_project = tmp_path / "like_spotify_mobile_app"
    other_project.mkdir()
    canonical_jarvis = tmp_path / "canonical" / "jarvis"
    _make_jarvis_checkout(canonical_jarvis)

    # CLAUDE_PROJECT_DIR / cwd point at the non-jarvis project (no jarvis/redrobot
    # path component anywhere) — resolver must fall through to its own on-disk
    # location instead of resolving inside the unrelated project.
    assert hook_resolver.detect_project_root(str(other_project)) is None

    # Simulate hook-resolver.py physically living inside the canonical install
    # (its own settings.json invocation is always an install-time-baked
    # absolute path, never $CLAUDE_PROJECT_DIR-templated) by pointing the
    # module's own __file__ at it — resolve_script() derives its third
    # fallback candidate from Path(__file__).
    monkeypatch.setattr(hook_resolver, "__file__", str(canonical_jarvis / "scripts" / "hook-resolver.py"))
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(other_project))
    monkeypatch.chdir(other_project)

    resolved = hook_resolver.resolve_script("session-context.py")

    assert resolved == canonical_jarvis / "scripts" / "session-context.py"


# ---------- matrix row 4: non-jarvis project's own worktree is not mistaken for a jarvis worktree ----------


def test_row4_non_jarvis_worktree_not_mistaken_for_jarvis(tmp_path: Path, monkeypatch) -> None:
    redrobot_worktree = tmp_path / "redrobot" / ".claude" / "worktrees" / "feature-x"
    redrobot_worktree.mkdir(parents=True)
    canonical_jarvis = tmp_path / "canonical" / "jarvis"
    _make_jarvis_checkout(canonical_jarvis)

    # "we're technically inside *some* worktree" must not resolve as jarvis —
    # detect_project_root should key off the "redrobot" component and return
    # the redrobot worktree root (correct for a redrobot session), never a
    # jarvis path just because ".claude/worktrees/<name>" is present.
    root = hook_resolver.detect_project_root(str(redrobot_worktree))
    assert root == redrobot_worktree
    assert "jarvis" not in root.parts

    monkeypatch.setattr(hook_resolver, "__file__", str(canonical_jarvis / "scripts" / "hook-resolver.py"))
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(redrobot_worktree))
    monkeypatch.chdir(redrobot_worktree)

    resolved = hook_resolver.resolve_script("session-context.py")

    assert resolved == canonical_jarvis / "scripts" / "session-context.py"


# ---------- exit-code behavior: fail closed vs fail open ----------


def test_resolution_failure_exits_2_by_default_fail_closed(tmp_path: Path, monkeypatch) -> None:
    # A script name that exists under no candidate root (including this
    # checkout's own scripts/) forces genuine resolution failure.
    monkeypatch.delenv("CLAUDE_PROJECT_DIR", raising=False)
    monkeypatch.chdir(tmp_path)
    result = subprocess.run(
        [sys.executable, str(Path(__file__).resolve().parents[2] / "scripts" / "hook-resolver.py"), "does-not-exist.py"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        env={"SystemRoot": __import__("os").environ.get("SystemRoot", "")},
    )
    assert result.returncode == 2


def test_resolution_failure_exits_1_with_soft_flag_fail_open(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("CLAUDE_PROJECT_DIR", raising=False)
    monkeypatch.chdir(tmp_path)
    result = subprocess.run(
        [
            sys.executable,
            str(Path(__file__).resolve().parents[2] / "scripts" / "hook-resolver.py"),
            "--soft",
            "does-not-exist.py",
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        env={"SystemRoot": __import__("os").environ.get("SystemRoot", "")},
    )
    assert result.returncode == 1

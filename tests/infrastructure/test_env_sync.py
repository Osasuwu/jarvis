"""Tests for scripts/lib/env_sync.py (#1312).

Covers AC#1 (check/heal core), AC#2 (lock reclaim), and the registry slice
of AC#8's meta-test (probe_modules coverage of third-party imports across
the three MCP server files).
"""

import ast
import json
import os
import subprocess
import sys
import time
from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT / "scripts" / "lib"))

import env_sync  # noqa: E402


def _make_env(tmp_path, probe_modules=("modA", "modB")):
    manifest = tmp_path / "requirements.txt"
    manifest.write_text("modA>=1,<2\nmodB>=1,<2\n", encoding="utf-8")
    return env_sync.ManagedEnv(
        name="test-env",
        venv_python=tmp_path / "venv-python",
        manifest=manifest,
        stamp_path=tmp_path / ".deps-stamp",
        probe_modules=probe_modules,
    )


class FakeCompleted:
    def __init__(self, returncode=0):
        self.returncode = returncode


def _probes_all_ok(*args, **kwargs):
    return FakeCompleted(0)


def _probes_all_fail(*args, **kwargs):
    return FakeCompleted(1)


def _probes_fail_for(bad_modules):
    def _run(cmd, *args, **kwargs):
        # cmd = [python_exe, "-c", "import <module>"]
        src = cmd[2]
        module = src.split("import ", 1)[1]
        return FakeCompleted(1 if module in bad_modules else 0)

    return _run


# ---------------------------------------------------------------------------
# check()
# ---------------------------------------------------------------------------


def test_check_no_stamp_reports_drift(tmp_path, monkeypatch):
    env = _make_env(tmp_path)
    monkeypatch.setattr(env_sync.subprocess, "run", _probes_all_ok)
    result = env_sync.check(env)
    assert result.in_sync is False
    assert result.reason == "hash_mismatch"


def test_check_matching_stamp_and_healthy_probes_is_in_sync(tmp_path, monkeypatch):
    env = _make_env(tmp_path)
    env.stamp_path.write_text(env_sync._manifest_hash(env.manifest), encoding="utf-8")
    monkeypatch.setattr(env_sync.subprocess, "run", _probes_all_ok)
    result = env_sync.check(env)
    assert result.in_sync is True
    assert result.reason is None


def test_check_manifest_changed_after_stamp_reports_drift(tmp_path, monkeypatch):
    env = _make_env(tmp_path)
    env.stamp_path.write_text(env_sync._manifest_hash(env.manifest), encoding="utf-8")
    env.manifest.write_text("modA>=2,<3\nmodB>=1,<2\n", encoding="utf-8")
    monkeypatch.setattr(env_sync.subprocess, "run", _probes_all_ok)
    result = env_sync.check(env)
    assert result.in_sync is False
    assert result.reason == "hash_mismatch"


def test_check_hash_matches_but_probe_fails_reports_drift(tmp_path, monkeypatch):
    env = _make_env(tmp_path)
    env.stamp_path.write_text(env_sync._manifest_hash(env.manifest), encoding="utf-8")
    monkeypatch.setattr(env_sync.subprocess, "run", _probes_fail_for({"modB"}))
    result = env_sync.check(env)
    assert result.in_sync is False
    assert result.reason == "probe_failed:modB"


# ---------------------------------------------------------------------------
# heal()
# ---------------------------------------------------------------------------


class FakePopen:
    """Fake subprocess.Popen standing in for the pip install child."""

    def __init__(self, returncode=0, hang=False):
        self._returncode = returncode
        self._hang = hang
        self.pid = 4242
        self.calls = []

    def __call__(self, cmd, *args, **kwargs):
        self.calls.append((cmd, args, kwargs))
        return self

    def wait(self, timeout=None):
        if self._hang:
            raise subprocess.TimeoutExpired(cmd="pip", timeout=timeout)
        return self._returncode

    def kill(self):
        pass


def test_heal_writes_stamp_on_pip_success_and_probe_pass(tmp_path, monkeypatch):
    env = _make_env(tmp_path)
    monkeypatch.setattr(env_sync.subprocess, "Popen", FakePopen(returncode=0))
    monkeypatch.setattr(env_sync.subprocess, "run", _probes_all_ok)
    monkeypatch.setattr(env_sync, "_LOG_DIR", tmp_path / "logs")

    result = env_sync.heal(env)

    assert result.success is True
    assert env.stamp_path.exists()
    assert env.stamp_path.read_text(encoding="utf-8").strip() == env_sync._manifest_hash(
        env.manifest
    )


def test_heal_does_not_write_stamp_when_pip_fails(tmp_path, monkeypatch):
    env = _make_env(tmp_path)
    monkeypatch.setattr(env_sync.subprocess, "Popen", FakePopen(returncode=1))
    monkeypatch.setattr(env_sync.subprocess, "run", _probes_all_ok)
    monkeypatch.setattr(env_sync, "_LOG_DIR", tmp_path / "logs")

    result = env_sync.heal(env)

    assert result.success is False
    assert result.reason == "pip_install_failed"  # Updated for #1313
    assert not env.stamp_path.exists()


def test_heal_does_not_write_stamp_when_post_install_probe_fails(tmp_path, monkeypatch):
    env = _make_env(tmp_path)
    monkeypatch.setattr(env_sync.subprocess, "Popen", FakePopen(returncode=0))
    monkeypatch.setattr(env_sync.subprocess, "run", _probes_fail_for({"modA"}))
    monkeypatch.setattr(env_sync, "_LOG_DIR", tmp_path / "logs")

    result = env_sync.heal(env)

    assert result.success is False
    assert result.reason == "probe_failed:modA"
    assert not env.stamp_path.exists()


def test_heal_never_raises_on_internal_error(tmp_path, monkeypatch):
    env = _make_env(tmp_path)

    def _boom(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(env_sync.subprocess, "Popen", _boom)
    monkeypatch.setattr(env_sync, "_LOG_DIR", tmp_path / "logs")

    result = env_sync.heal(env)

    assert result.success is False
    assert result.reason.startswith("exception:")


# ---------------------------------------------------------------------------
# Lock reclaim (AC#2)
# ---------------------------------------------------------------------------


def test_acquire_lock_succeeds_when_no_lock_present(tmp_path):
    lock_path = tmp_path / "x.lock"
    assert env_sync._acquire_lock(lock_path) is True
    assert lock_path.exists()


def test_acquire_lock_blocked_by_live_lock(tmp_path, monkeypatch):
    lock_path = tmp_path / "x.lock"
    lock_path.write_text(json.dumps({"pid": 99999, "ts": time.time()}), encoding="utf-8")
    monkeypatch.setattr(env_sync, "_pid_alive", lambda pid: True)
    assert env_sync._acquire_lock(lock_path) is False


def test_acquire_lock_reclaims_dead_pid(tmp_path, monkeypatch):
    lock_path = tmp_path / "x.lock"
    lock_path.write_text(json.dumps({"pid": 99999, "ts": time.time()}), encoding="utf-8")
    monkeypatch.setattr(env_sync, "_pid_alive", lambda pid: False)
    assert env_sync._acquire_lock(lock_path) is True


def test_acquire_lock_reclaims_expired_ttl(tmp_path, monkeypatch):
    lock_path = tmp_path / "x.lock"
    stale_ts = time.time() - (env_sync.LOCK_TTL_SECONDS + 10)
    lock_path.write_text(json.dumps({"pid": os.getpid(), "ts": stale_ts}), encoding="utf-8")
    monkeypatch.setattr(env_sync, "_pid_alive", lambda pid: True)
    assert env_sync._acquire_lock(lock_path) is True


def test_heal_returns_locked_when_second_caller_blocked(tmp_path, monkeypatch):
    env = _make_env(tmp_path)
    monkeypatch.setattr(env_sync, "_LOG_DIR", tmp_path / "logs")
    monkeypatch.setattr(env_sync, "_acquire_lock", lambda lock_path, ttl=None: False)

    result = env_sync.heal(env)

    assert result.success is False
    assert result.reason == "locked"


# ---------------------------------------------------------------------------
# Registry meta-test (AC#8): probe_modules must cover every third-party
# top-level import across the three MCP server files. This is the standing
# guard against the nest_asyncio/telethon class of silent drift recurring.
# ---------------------------------------------------------------------------

_STDLIB_ALLOWLIST = set(sys.stdlib_module_names) if hasattr(sys, "stdlib_module_names") else set()

_SERVER_FILES = [
    _REPO_ROOT / "mcp-memory" / "server.py",
    _REPO_ROOT / "mcp-status" / "server.py",
    _REPO_ROOT / "scripts" / "telegram-mcp-server.py",
]

# Local first-party packages that show up as top-level imports but are not
# pip-installed third-party dependencies (repo-local modules).
_FIRST_PARTY_ALLOWLIST = {"scripts", "mcp_memory", "mcp_status", "client", "embeddings", "handlers"}


def _is_sibling_module(name: str, source_dir: Path) -> bool:
    return (source_dir / f"{name}.py").exists() or (source_dir / name / "__init__.py").exists()


def _top_level_third_party_imports(path: Path) -> set:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                found.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.level and node.level > 0:
                continue  # relative import, always first-party
            if node.module:
                found.add(node.module.split(".")[0])
    return {
        m
        for m in found
        if m not in _STDLIB_ALLOWLIST
        and m not in _FIRST_PARTY_ALLOWLIST
        and not _is_sibling_module(m, path.parent)
    }


def test_registry_probe_modules_cover_all_server_third_party_imports():
    main_env = env_sync.get_env("main")
    assert main_env is not None

    required = set()
    for server_file in _SERVER_FILES:
        required |= _top_level_third_party_imports(server_file)

    missing = required - set(main_env.probe_modules)
    assert not missing, f"probe_modules missing third-party imports: {missing}"


# ---------------------------------------------------------------------------
# Lockfile parity (#1313): uv.lock ensures CI resolution matches local
# ---------------------------------------------------------------------------


def _make_env_with_lockfile(tmp_path, probe_modules=("modA", "modB")):
    """Create a ManagedEnv with both manifest and lockfile (#1313)."""
    manifest = tmp_path / "requirements.txt"
    manifest.write_text("modA>=1,<2\nmodB>=1,<2\n", encoding="utf-8")
    lockfile = tmp_path / "uv.lock"
    lockfile.write_text("[metadata]\nversion = 1\n", encoding="utf-8")
    return env_sync.ManagedEnv(
        name="test-env",
        venv_python=tmp_path / "venv-python",
        manifest=manifest,
        stamp_path=tmp_path / ".deps-stamp",
        lockfile=lockfile,
        probe_modules=probe_modules,
    )


def test_check_prefers_lockfile_hash_over_manifest_when_lockfile_exists(tmp_path, monkeypatch):
    """Lockfile parity AC#2: check() uses combined hash when lockfile present (#1313)."""
    env = _make_env_with_lockfile(tmp_path)
    # When both manifest and lockfile exist, use combined hash
    combined_hash = env_sync._combined_hash(env.manifest, env.lockfile)
    env.stamp_path.write_text(combined_hash, encoding="utf-8")
    monkeypatch.setattr(env_sync.subprocess, "run", _probes_all_ok)

    result = env_sync.check(env)

    # Should be in sync because combined hash matches stamp
    assert result.in_sync is True


def test_check_detects_lockfile_drift(tmp_path, monkeypatch):
    """Lockfile parity AC#2: check() detects when manifest drifts from lockfile (#1313)."""
    env = _make_env_with_lockfile(tmp_path)
    # Save combined hash of initial state
    combined_hash = env_sync._combined_hash(env.manifest, env.lockfile)
    env.stamp_path.write_text(combined_hash, encoding="utf-8")
    # Simulate Dependabot widening manifest range
    env.manifest.write_text("modA>=1,<3\nmodB>=1,<2\n", encoding="utf-8")
    # Lockfile not yet regenerated — drift detected (combined hash changed)
    monkeypatch.setattr(env_sync.subprocess, "run", _probes_all_ok)

    result = env_sync.check(env)

    # Manifest changed but lockfile didn't, so combined hash changed → drift detected
    assert result.in_sync is False


def test_check_detects_new_lockfile_as_drift(tmp_path, monkeypatch):
    """Lockfile parity AC#2: adding lockfile to manifest-only setup triggers drift (#1313)."""
    # Start with manifest-only setup
    manifest = tmp_path / "requirements.txt"
    manifest.write_text("modA>=1,<2\nmodB>=1,<2\n", encoding="utf-8")
    env = env_sync.ManagedEnv(
        name="test-env",
        venv_python=tmp_path / "venv-python",
        manifest=manifest,
        stamp_path=tmp_path / ".deps-stamp",
        lockfile=None,
        probe_modules=("modA", "modB"),
    )
    manifest_hash = env_sync._manifest_hash(manifest)
    env.stamp_path.write_text(manifest_hash, encoding="utf-8")
    monkeypatch.setattr(env_sync.subprocess, "run", _probes_all_ok)

    # At this point, should be in sync (manifest matches stamp)
    result = env_sync.check(env)
    assert result.in_sync is True

    # Now add lockfile (simulating #1313 landing)
    lockfile = tmp_path / "uv.lock"
    lockfile.write_text("[metadata]\nversion = 1\n", encoding="utf-8")
    env = env_sync.ManagedEnv(
        name="test-env",
        venv_python=tmp_path / "venv-python",
        manifest=manifest,
        stamp_path=tmp_path / ".deps-stamp",
        lockfile=lockfile,
        probe_modules=("modA", "modB"),
    )

    # Now check should detect drift because lockfile hash != manifest hash
    result = env_sync.check(env)
    assert result.in_sync is False
    assert result.reason == "hash_mismatch"


def test_heal_uses_uv_sync_when_lockfile_exists(tmp_path, monkeypatch):
    """Lockfile parity AC#3: heal() uses uv sync if lockfile present (#1313)."""
    env = _make_env_with_lockfile(tmp_path)

    # Track which commands were run
    calls = []

    def fake_popen(cmd, *args, **kwargs):
        calls.append(("popen", cmd))
        return FakePopen(returncode=0)

    monkeypatch.setattr(env_sync.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(env_sync.subprocess, "run", _probes_all_ok)
    monkeypatch.setattr(env_sync, "_LOG_DIR", tmp_path / "logs")

    result = env_sync.heal(env)

    assert result.success is True
    # Should have called uv sync (via Popen), not pip
    assert any("uv" in str(cmd) and "sync" in str(cmd) for _, cmd in calls)


def test_mcp_memory_uv_sync_succeeds_against_real_pyproject(tmp_path):
    """Regression test (#1312 env-sync heal-fails-forever bug).

    heal() shells out to real `uv sync`, but every mocked test above stubs
    subprocess and so never exercises the actual pyproject.toml. setuptools'
    flat-layout auto-discovery saw `handlers/` and `migrations/` as two
    top-level packages with no explicit selection and refused to build
    jarvis-mcp-memory, which made `uv sync` (and therefore heal()) fail
    unconditionally — any session whose venv had genuinely drifted could
    never be healed, only ever re-report "Heal Failed". Fixed via
    `tool.uv.package = false`: mcp-memory is an application launched through
    scripts/run-memory-server.py, never installed/imported as a library, so
    it should never need building at all.
    """
    project_dir = _REPO_ROOT / "mcp-memory"
    sync_env = dict(os.environ)
    sync_env["UV_PROJECT_ENVIRONMENT"] = str(tmp_path / "venv")
    result = subprocess.run(
        ["uv", "sync", "--project", str(project_dir)],
        cwd=str(project_dir),
        env=sync_env,
        capture_output=True,
        text=True,
        timeout=180,
    )
    output = result.stdout + result.stderr
    assert result.returncode == 0, output
    assert "Multiple top-level packages" not in output


def test_heal_falls_back_to_pip_when_lockfile_missing(tmp_path, monkeypatch):
    """Lockfile parity backward compat: heal() uses pip if lockfile absent (#1313)."""
    # Create env without lockfile
    manifest = tmp_path / "requirements.txt"
    manifest.write_text("modA>=1,<2\nmodB>=1,<2\n", encoding="utf-8")
    env = env_sync.ManagedEnv(
        name="test-env",
        venv_python=tmp_path / "venv-python",
        manifest=manifest,
        stamp_path=tmp_path / ".deps-stamp",
        lockfile=None,
        probe_modules=("modA", "modB"),
    )

    calls = []

    def fake_popen(cmd, *args, **kwargs):
        calls.append(("popen", cmd))
        return FakePopen(returncode=0)

    monkeypatch.setattr(env_sync.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(env_sync.subprocess, "run", _probes_all_ok)
    monkeypatch.setattr(env_sync, "_LOG_DIR", tmp_path / "logs")

    result = env_sync.heal(env)

    assert result.success is True
    # Should have called pip install (via Popen), not uv
    assert any("pip" in str(cmd) and "install" in str(cmd) for _, cmd in calls)

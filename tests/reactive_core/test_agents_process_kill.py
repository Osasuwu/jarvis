"""Unit tests for agents/process_kill.py (#1609 — task_dispatch decomposition 5/7).

Extracted from agents/task_dispatch.py and de-duplicated against the
equivalent kill logic that used to live in agents/pid_sidecar.py. Both call
sites now converge on the single implementation here (AC1-AC3); the
``TestSingleSourceOfTruth`` class below is the AC4 test proving no sibling
implementation remains.
"""

from __future__ import annotations

import subprocess
from typing import Any


class _FakeProc:
    """Minimal ``Popen``-shaped handle: ``poll()`` returns the scripted rc."""

    def __init__(self, rc: int | None = None, pid: int = 4242) -> None:
        self._rc = rc
        self.pid = pid
        self.killed = False
        self.waited = False

    def poll(self) -> int | None:
        return self._rc

    def kill(self) -> None:
        self.killed = True
        self._rc = -9

    def wait(self, timeout: float | None = None) -> int | None:
        self.waited = True
        return self._rc


class TestKillProcessTree:
    def test_windows_uses_taskkill_tree_force(self, monkeypatch: Any) -> None:
        # Bare Popen.kill() is terminate() on Windows — children survive. The
        # tree-kill must go through taskkill /T /F.
        import agents.process_kill as pk

        runs: list[list[str]] = []
        monkeypatch.setattr(pk.subprocess, "run", lambda argv, **kw: runs.append(list(argv)))
        proc = _FakeProc(rc=None, pid=1234)
        pk.kill_process_tree(proc, platform="win32")
        assert runs == [["taskkill", "/PID", "1234", "/T", "/F"]]
        assert proc.killed is False  # win32 path never calls Popen.kill()

    def test_posix_uses_proc_kill(self) -> None:
        import agents.process_kill as pk

        proc = _FakeProc(rc=None, pid=1234)
        pk.kill_process_tree(proc, platform="linux")
        assert proc.killed is True

    def test_reaps_handle_with_wait(self, monkeypatch: Any) -> None:
        # review #957-3: the post-kill wait must actually run (it reaps the
        # handle so poll() reflects the death immediately), win32 and POSIX
        # alike — a fake without wait() was silently masking this call.
        import agents.process_kill as pk

        monkeypatch.setattr(pk.subprocess, "run", lambda argv, **kw: None)
        win = _FakeProc(rc=None, pid=1234)
        pk.kill_process_tree(win, platform="win32")
        posix = _FakeProc(rc=None, pid=1234)
        pk.kill_process_tree(posix, platform="linux")
        assert win.waited is True
        assert posix.waited is True

    def test_hung_wait_is_swallowed(self) -> None:
        # A child that won't reap within the timeout must not hang the driver
        # tick: TimeoutExpired is swallowed, the next tick's poll re-checks.
        import agents.process_kill as pk

        class _HangingProc(_FakeProc):
            def wait(self, timeout: float | None = None) -> int | None:
                raise subprocess.TimeoutExpired(cmd="claude", timeout=timeout or 10)

        proc = _HangingProc(rc=None, pid=1234)
        pk.kill_process_tree(proc, platform="linux")
        assert proc.killed is True  # the kill happened despite the hung wait

    def test_missing_taskkill_falls_back_to_proc_kill(self, monkeypatch: Any) -> None:
        # review #957-7 (MINOR): taskkill absent from PATH (stripped env,
        # minimal container) must not leave the runaway alive — fall back to
        # plain Popen.kill(), which at least takes down the direct child.
        import agents.process_kill as pk

        def raising_run(argv: list[str], **kw: Any) -> None:
            raise FileNotFoundError("taskkill not found")

        monkeypatch.setattr(pk.subprocess, "run", raising_run)
        proc = _FakeProc(rc=None, pid=1234)
        pk.kill_process_tree(proc, platform="win32")
        assert proc.killed is True

    def test_wait_timeout_is_configurable(self) -> None:
        # pid_sidecar's orphan-kill path needs a faster reap than the 10s
        # runaway-kill default (AC3 de-dup depends on this being tunable).
        import agents.process_kill as pk

        seen_timeouts: list[float | None] = []

        class _RecordingProc(_FakeProc):
            def wait(self, timeout: float | None = None) -> int | None:
                seen_timeouts.append(timeout)
                return super().wait(timeout=timeout)

        proc = _RecordingProc(rc=None, pid=1234)
        pk.kill_process_tree(proc, platform="linux", wait_timeout=1.0)
        assert seen_timeouts == [1.0]


class TestSingleSourceOfTruth:
    """AC4 — task_dispatch.py and pid_sidecar.py both call the one implementation."""

    def test_task_dispatch_imports_the_shared_implementation(self) -> None:
        import agents.process_kill as pk
        import agents.task_dispatch as td

        assert td.kill_process_tree is pk.kill_process_tree

    def test_pid_sidecar_imports_the_shared_implementation(self) -> None:
        import agents.pid_sidecar as ps
        import agents.process_kill as pk

        assert ps.kill_process_tree is pk.kill_process_tree

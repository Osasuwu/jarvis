"""Reactive-core test fixtures.

Companion to the live-Supabase guard in ``tests/conftest.py``: that one turns an
accidental production write into a failure, this one removes the reason the
drain tests attempted one at all.
"""

from __future__ import annotations

import shutil

import pytest

# ---------------------------------------------------------------------------
# Host-independent infra pre-flight (#1121 step 16 fallout)
# ---------------------------------------------------------------------------
# `drain_tasks` binds `check_infra_available=default_check_infra_available` as a
# def-time default, so a module-level monkeypatch of that name cannot reach the
# 44 call sites that don't pass the argument — the seam has to be one level
# down, at the `shutil.which` the default consults. Without this, whether a
# drain test exercises the happy path or the pre-flight-failure path depends on
# the PATH of whatever process pytest happens to run in.
#
# Only `docker` / `node` are synthesised, and only when genuinely absent; every
# other lookup (`resolve_binary`'s included) still hits the real filesystem. A
# test that wants a broken host passes `check_infra_available=` explicitly.


@pytest.fixture(autouse=True)
def _infra_preflight_sees_a_healthy_host(monkeypatch):
    real_which = shutil.which

    def which(cmd, *args, **kwargs):
        found = real_which(cmd, *args, **kwargs)
        if found is None and cmd in ("docker", "node"):
            return f"/stub/bin/{cmd}"
        return found

    monkeypatch.setattr(shutil, "which", which)

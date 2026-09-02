"""The autouse guard in tests/conftest.py must actually block live clients.

Incident 2026-09-02: a `pytest tests/reactive_core` run wrote 392 real
`drain_infra_preflight_failure` rows into the production events table in six
minutes, and wake_driver started fanning them into owner escalations. The
suite had always *looked* isolated — tests/conftest.py sets SUPABASE_URL /
SUPABASE_KEY to test values — but it sets them with `setdefault`, which loses
to a real `.env`, so every unstubbed `get_client()` in the suite was pointed at
production the whole time.

The guard is only load-bearing if it fails when removed, hence these tests.
"""

from __future__ import annotations

import pytest


def test_create_client_is_blocked() -> None:
    """A test constructing a Supabase client fails instead of reaching prod."""
    import supabase

    with pytest.raises(AssertionError, match="LIVE Supabase client"):
        supabase.create_client("https://real.supabase.co", "real-key")


def test_agents_get_client_is_blocked_after_config_validation() -> None:
    """`agents.supabase_client.get_client` cannot return a live client either.

    The block sits at `create_client`, one level below `get_client`, so this is
    the end-to-end check that the lower seam still covers the outer call.
    """
    from agents.supabase_client import get_client

    with pytest.raises(AssertionError, match="LIVE Supabase client"):
        get_client()


def test_missing_credentials_still_raise_runtime_error(monkeypatch) -> None:
    """The guard must not shadow get_client's own config-validation contract.

    Blocking `get_client` itself (the first attempt at this guard) swallowed the
    RuntimeError that `test_supabase_client_errors_without_credentials` asserts.
    """
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_KEY", raising=False)

    from agents.supabase_client import get_client

    with pytest.raises(RuntimeError, match="SUPABASE_URL and SUPABASE_KEY"):
        get_client()

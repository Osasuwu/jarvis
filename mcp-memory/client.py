"""Supabase client factory + audit log (#360 split).

Lazy-init singleton pattern preserved from server.py. Audit log is
fire-and-forget — never raises into the caller.
"""

from __future__ import annotations

import os

_supabase = None


def _get_client():
    global _supabase
    if _supabase is not None:
        return _supabase

    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")
    if not url or not key:
        raise RuntimeError(
            "SUPABASE_URL and SUPABASE_KEY must be set. "
            "Get them from your Supabase project settings."
        )

    from supabase import create_client

    _supabase = create_client(url, key)

    # One-time migration: normalize legacy project='global' string rows to NULL.
    # Before the 2026-03-31 fix, 'global' was stored as a literal string instead
    # of NULL. This UPDATE is idempotent and safe to run on every startup.
    try:
        _supabase.table("memories").update({"project": None}).eq("project", "global").execute()
    except Exception:
        pass  # non-fatal — server still works without the migration

    return _supabase


# ---------------------------------------------------------------------------
# Audit logging — lightweight, fire-and-forget
# ---------------------------------------------------------------------------


def _audit_log(
    client, tool_name: str, action: str, target: str | None = None, details: dict | None = None
):
    """Fire-and-forget audit log entry. Never fails the caller."""
    try:
        client.table("audit_log").insert(
            {
                "tool_name": tool_name,
                "action": action,
                "target": target,
                "details": details or {},
            }
        ).execute()
    except Exception:
        pass  # audit is best-effort — never block operations

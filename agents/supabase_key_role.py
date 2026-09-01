"""SUPABASE_KEY role validation (#1121, decision 94c55c7b).

Non-emptiness alone doesn't stop a service-role key from being forwarded
into a spawned container — this validates by role instead:

- new Supabase API key formats: ``sb_publishable_*`` is accepted
  (anon-equivalent), ``sb_secret_*`` is rejected (service-role-equivalent).
- legacy JWT keys: decode the unverified payload's ``role`` claim;
  ``"anon"`` is accepted, ``"service_role"`` (or anything else) is rejected.

This only classifies the key's role — it does not verify the JWT
signature. Signature verification happens Supabase-side on every request;
this check exists purely to stop the wrong *class* of key from being
forwarded into a spawned container in the first place.

Mirror of .sandcastle/supabase-key-role.mts — keep both in sync.
"""

from __future__ import annotations

import base64
import json


class SupabaseKeyRoleError(ValueError):
    pass


def _decode_jwt_role(key: str) -> str | None:
    parts = key.split(".")
    if len(parts) != 3:
        return None
    try:
        payload_b64 = parts[1]
        padded = payload_b64 + "=" * (-len(payload_b64) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded))
        role = payload.get("role")
        return role if isinstance(role, str) else None
    except Exception:
        return None


def assert_supabase_key_is_anon(key: str) -> None:
    """Raise SupabaseKeyRoleError if ``key`` is not an anon-equivalent key."""
    if key.startswith("sb_secret_"):
        raise SupabaseKeyRoleError(
            "SUPABASE_KEY is a service-role secret key (sb_secret_ prefix) — "
            "anon key only, never service-role."
        )
    if key.startswith("sb_publishable_"):
        return

    role = _decode_jwt_role(key)
    if role == "anon":
        return
    if role == "service_role":
        raise SupabaseKeyRoleError(
            "SUPABASE_KEY is a service-role JWT (role=service_role) — anon "
            "key only, never service-role."
        )
    raise SupabaseKeyRoleError(
        "SUPABASE_KEY is not a recognized anon-role key (expected "
        "sb_publishable_* or a JWT with role=anon)."
    )

"""Tests for agents/supabase_key_role.py (#1121, decision 94c55c7b).

Mirror of .sandcastle/check-supabase-key-role.mts.
"""

from __future__ import annotations

import base64
import json

import pytest

from agents.supabase_key_role import SupabaseKeyRoleError, assert_supabase_key_is_anon


def _fake_jwt(role: str) -> str:
    def b64url(obj: dict) -> str:
        return base64.urlsafe_b64encode(json.dumps(obj).encode()).rstrip(b"=").decode()

    return f"{b64url({'alg': 'HS256', 'typ': 'JWT'})}.{b64url({'role': role})}.fakesig"


ANON_JWT = _fake_jwt("anon")
SERVICE_ROLE_JWT = _fake_jwt("service_role")


class TestAssertSupabaseKeyIsAnon:
    def test_publishable_key_accepted(self):
        assert_supabase_key_is_anon("sb_publishable_abc123")  # no raise

    def test_secret_key_rejected(self):
        with pytest.raises(SupabaseKeyRoleError):
            assert_supabase_key_is_anon("sb_secret_abc123")

    def test_anon_jwt_accepted(self):
        assert_supabase_key_is_anon(ANON_JWT)  # no raise

    def test_service_role_jwt_rejected(self):
        with pytest.raises(SupabaseKeyRoleError):
            assert_supabase_key_is_anon(SERVICE_ROLE_JWT)

    def test_malformed_key_rejected(self):
        with pytest.raises(SupabaseKeyRoleError):
            assert_supabase_key_is_anon("not-a-real-key")

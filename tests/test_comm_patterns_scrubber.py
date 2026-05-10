"""Scrubber unit tests — secrets + PII regression coverage.

#581 acceptance criterion: planted email, planted path with username, and
planted API-key-shape all trigger ``redacted=True`` and replace the quote
with a placeholder.
"""

from __future__ import annotations

from comm_patterns.scrubber import scrub


def test_clean_text_passes_through_unchanged():
    text = "правильно, спасибо — теперь всё работает."
    out, redacted = scrub(text)
    assert out == text
    assert redacted is False


def test_planted_email_is_redacted():
    text = "user said: john.doe@example.com is my contact"
    out, redacted = scrub(text)
    assert redacted is True
    assert "john.doe@example.com" not in out
    assert "[REDACTED:email]" in out


def test_planted_path_with_username_is_redacted_windows():
    text = r"check C:\Users\petrk\GitHub\jarvis\config.json"
    out, redacted = scrub(text)
    assert redacted is True
    assert "petrk" not in out
    assert "[REDACTED:user]" in out
    # Path structure preserved.
    assert "GitHub" in out


def test_planted_path_with_username_is_redacted_posix_home():
    text = "ls /home/petrk/.cache/jarvis-comms-analysis"
    out, redacted = scrub(text)
    assert redacted is True
    assert "/home/petrk" not in out
    assert "[REDACTED:user]" in out


def test_planted_path_with_username_is_redacted_macos_users():
    text = "open /Users/petrk/Documents/secret.txt"
    out, redacted = scrub(text)
    assert redacted is True
    assert "/Users/petrk" not in out
    assert "[REDACTED:user]" in out


def test_planted_api_key_shape_is_redacted_anthropic():
    fake_key = "sk-ant-" + "a" * 40
    text = f"my key is {fake_key} please remove"
    out, redacted = scrub(text)
    assert redacted is True
    assert fake_key not in out
    assert "[REDACTED:secret:anthropic-key]" in out


def test_planted_api_key_shape_is_redacted_github_token():
    fake_token = "ghp_" + "x" * 40
    text = f"GITHUB_TOKEN={fake_token}"
    out, redacted = scrub(text)
    assert redacted is True
    assert fake_token not in out


def test_planted_jwt_is_redacted():
    fake_jwt = "eyJ" + "A" * 40 + "." + "B" * 20
    text = f"Authorization: Bearer {fake_jwt}"
    out, redacted = scrub(text)
    assert redacted is True
    assert fake_jwt not in out


def test_dotenv_shaped_value_is_redacted():
    # Non-credential-named var so the credential-assignment regex doesn't
    # win first — exercises the dotenv fallback specifically.
    text = "DEPLOY_HASH=abcdef1234567890abcdef"
    out, redacted = scrub(text)
    assert redacted is True
    assert "abcdef1234567890abcdef" not in out
    assert "DEPLOY_HASH=[REDACTED:env]" in out


def test_credential_assignment_is_redacted():
    text = "SOME_TOKEN=abcdef1234567890abcdef"
    out, redacted = scrub(text)
    assert redacted is True
    assert "abcdef1234567890abcdef" not in out
    assert "[REDACTED:secret:credential-assignment]" in out


def test_multiple_substitutions_each_count():
    fake_key = "sk-" + "z" * 40
    text = f"contact me at me@example.com with {fake_key}"
    out, redacted = scrub(text)
    assert redacted is True
    assert "me@example.com" not in out
    assert fake_key not in out


def test_empty_text_returns_false():
    out, redacted = scrub("")
    assert out == ""
    assert redacted is False


def test_quote_truncation_is_caller_responsibility():
    """Scrubber doesn't truncate — the row builder does. This guards against
    the scrubber growing surprise side-effects on length."""
    text = "a" * 5000
    out, redacted = scrub(text)
    assert out == text
    assert redacted is False

"""Tests for Groq provider."""

import pytest

from jarvis.llm.groq import GroqProvider


def test_groq_provider_initialization_error() -> None:
    """Test GroqProvider raises error without API key."""
    with pytest.raises(ValueError, match="API key not provided"):
        GroqProvider(api_key="")


def test_groq_provider_properties() -> None:
    """Test GroqProvider properties."""
    provider = GroqProvider(api_key="test-key", model="test-model")
    assert provider.provider_name == "groq"
    assert provider.model_name == "test-model"


@pytest.mark.asyncio
async def test_groq_provider_validate_connection() -> None:
    """Test connection validation (will fail with fake key, but tests the method)."""
    provider = GroqProvider(api_key="fake-key-for-test")
    # This should fail with invalid API key, but tests the method exists
    result = await provider.validate_connection()
    assert result is False  # Expected to fail with fake key


def test_parse_json() -> None:
    """Test JSON parsing utility."""
    # Valid JSON
    result = GroqProvider._parse_json('{"key": "value"}')
    assert result == {"key": "value"}

    # Invalid JSON
    result = GroqProvider._parse_json("invalid json")
    assert result == {}

    # None
    result = GroqProvider._parse_json(None)
    assert result == {}

"""Tests for configuration management."""

from jarvis.config import (
    AgentSettings,
    JarvisConfig,
    LLMSettings,
    LoggingSettings,
    MemorySettings,
    ToolSettings,
    get_config,
    reload_config,
)


def test_llm_settings_defaults() -> None:
    """Test LLM settings have correct defaults."""
    settings = LLMSettings()
    assert settings.provider == "groq"
    assert settings.model == "llama-3.3-70b-versatile"
    assert settings.temperature == 0.7
    assert settings.max_tokens == 4096


def test_llm_settings_custom_values() -> None:
    """Test LLM settings with custom values."""
    settings = LLMSettings(
        provider="ollama",
        model="llama3.2",
        temperature=0.5,
    )
    assert settings.provider == "ollama"
    assert settings.model == "llama3.2"
    assert settings.temperature == 0.5


def test_tool_settings_defaults() -> None:
    """Test tool settings have correct defaults."""
    settings = ToolSettings()
    assert settings.enabled is True
    assert settings.auto_discover is True
    assert "HIGH" in settings.require_confirmation_for_risk_levels
    assert settings.max_parallel_executions == 3


def test_memory_settings_defaults() -> None:
    """Test memory settings have correct defaults."""
    settings = MemorySettings()
    assert settings.max_conversation_length == 50
    assert settings.persist_to_disk is True
    assert settings.storage_path == "./.jarvis/memory"


def test_logging_settings_defaults() -> None:
    """Test logging settings have correct defaults."""
    settings = LoggingSettings()
    assert settings.level == "INFO"
    assert settings.format == "json"
    assert settings.output == "console"


def test_agent_settings_defaults() -> None:
    """Test agent settings have correct defaults."""
    settings = AgentSettings()
    assert settings.name == "Jarvis"
    assert settings.max_iterations == 10
    assert settings.timeout_seconds == 300


def test_jarvis_config_integration() -> None:
    """Test JarvisConfig integrates all settings."""
    config = JarvisConfig()
    assert config.llm.provider == "groq"
    assert config.tools.enabled is True
    assert config.memory.persist_to_disk is True
    assert config.logging.level == "INFO"
    assert config.agent.name == "Jarvis"


def test_get_config_singleton() -> None:
    """Test get_config returns singleton."""
    config1 = get_config()
    config2 = get_config()
    assert config1 is config2


def test_reload_config() -> None:
    """Test reload_config creates new instance."""
    config1 = get_config()
    config2 = reload_config()
    # Different instances but same values
    assert config1 is not config2
    assert config1.llm.model == config2.llm.model

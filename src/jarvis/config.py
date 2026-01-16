"""Jarvis configuration management using Pydantic Settings."""

from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class LLMSettings(BaseSettings):
    """LLM provider settings."""

    provider: Literal["groq", "ollama", "gemini", "openai"] = "groq"
    model: str = "llama-3.3-70b-versatile"
    temperature: float = 0.7
    max_tokens: int = 4096
    top_p: float = 1.0

    # Groq specific
    groq_api_key: str = ""
    groq_timeout: int = 30

    # Ollama specific
    ollama_base_url: str = "http://localhost:11434"
    ollama_timeout: int = 60

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


class ToolSettings(BaseSettings):
    """Tool system settings."""

    enabled: bool = True
    auto_discover: bool = True
    require_confirmation_for_risk_levels: list[str] = ["HIGH"]
    max_parallel_executions: int = 3

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


class MemorySettings(BaseSettings):
    """Memory management settings."""

    max_conversation_length: int = 50
    persist_to_disk: bool = True
    storage_path: str = "./.jarvis/memory"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


class LoggingSettings(BaseSettings):
    """Logging settings."""

    level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    format: Literal["json", "text"] = "json"
    output: Literal["console", "file", "both"] = "console"
    file_path: str = "./logs/jarvis.log"
    rotation: str = "1 day"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


class AgentSettings(BaseSettings):
    """Jarvis agent settings."""

    name: str = "Jarvis"
    max_iterations: int = 10
    timeout_seconds: int = 300

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


class JarvisConfig(BaseSettings):
    """Main Jarvis configuration."""

    llm: LLMSettings = LLMSettings()
    tools: ToolSettings = ToolSettings()
    memory: MemorySettings = MemorySettings()
    logging: LoggingSettings = LoggingSettings()
    agent: AgentSettings = AgentSettings()

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


# Singleton instance
_config: JarvisConfig | None = None


def get_config() -> JarvisConfig:
    """Get or create the global Jarvis configuration."""
    global _config
    if _config is None:
        _config = JarvisConfig()
    return _config


def reload_config() -> JarvisConfig:
    """Reload configuration from environment/files."""
    global _config
    _config = JarvisConfig()
    return _config

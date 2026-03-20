"""Jarvis configuration management using Pydantic Settings."""

import logging
from pathlib import Path
from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)


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

    @field_validator("storage_path")
    @classmethod
    def validate_storage_path(cls, v: str) -> str:
        """Validate that storage path parent directory can be created."""
        path = Path(v)
        try:
            # Ensure parent directory can be created
            path.parent.mkdir(parents=True, exist_ok=True)
            # Test write permission
            test_file = path.parent / ".write_test"
            test_file.touch()
            test_file.unlink()
        except (PermissionError, OSError) as e:
            raise ValueError(
                f"Storage path '{v}' is not writable or parent directory cannot be created: {e}"
            ) from e
        return v


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
    """
    Main Jarvis configuration with validation.

    Configuration contracts:
    - If persist_to_disk=True, storage_path must be writable
    - If using Groq provider, groq_api_key must be set
    - All numeric settings must be positive
    """

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

    def validate(self) -> None:
        """
        Validate configuration contracts at startup.

        Raises:
            ValueError: If configuration violates contract
        """
        errors: list[str] = []

        # Validate memory settings
        if self.memory.persist_to_disk:
            try:
                path = Path(self.memory.storage_path)
                path.parent.mkdir(parents=True, exist_ok=True)
                # Test write permission
                test_file = path.parent / ".config_test"
                test_file.touch()
                test_file.unlink()
            except (PermissionError, OSError) as e:
                errors.append(
                    f"Memory persistence enabled but storage path '{self.memory.storage_path}' "
                    f"is not writable: {e}"
                )

        # Validate memory limits
        if self.memory.max_conversation_length <= 0:
            errors.append(
                f"max_conversation_length must be positive, got {self.memory.max_conversation_length}"
            )

        # Validate LLM settings
        if self.llm.provider == "groq" and not self.llm.groq_api_key:
            errors.append(
                "LLM provider is 'groq' but GROQ_API_KEY is not set. "
                "Set GROQ_API_KEY environment variable or use USE_LOCAL_LLM=1"
            )

        if self.llm.temperature < 0 or self.llm.temperature > 2.0:
            errors.append(f"LLM temperature must be between 0 and 2.0, got {self.llm.temperature}")

        if self.llm.max_tokens <= 0:
            errors.append(f"LLM max_tokens must be positive, got {self.llm.max_tokens}")

        # Validate agent settings
        if self.agent.max_iterations <= 0:
            errors.append(f"agent.max_iterations must be positive, got {self.agent.max_iterations}")

        if self.agent.timeout_seconds <= 0:
            errors.append(
                f"agent.timeout_seconds must be positive, got {self.agent.timeout_seconds}"
            )

        # Raise all errors at once for clarity
        if errors:
            error_msg = "Configuration validation failed:\n  " + "\n  ".join(errors)
            logger.error(error_msg)
            raise ValueError(error_msg)


# Singleton instance
_config: JarvisConfig | None = None


def get_config() -> JarvisConfig:
    """
    Get or create the global Jarvis configuration.

    Validates configuration on first creation.

    Raises:
        ValueError: If configuration is invalid
    """
    global _config
    if _config is None:
        _config = JarvisConfig()
        _config.validate()
    return _config


def reload_config() -> JarvisConfig:
    """
    Reload configuration from environment/files.

    Validates configuration after reload.

    Raises:
        ValueError: If configuration is invalid
    """
    global _config
    _config = JarvisConfig()
    _config.validate()
    return _config

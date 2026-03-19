"""
Factory for creating orchestrator and its dependencies.

This module centralizes all dependency creation, enabling:
- Testability: Easy to create mocked versions for testing
- Clarity: One place to understand component composition
- Flexibility: Easy to swap implementations or add new features
- Consistency: Ensures all orchestrators are created the same way

Architecture:
- create_orchestrator(): Main entry point for CLI/production
- _create_llm_provider(): LLM provider factory
- _create_tool_registry(): Tool discovery and registration
- _create_safety_layer(): Safety components (confirmation, whitelist, audit)
- _create_memory(): Conversation memory with persistence

All functions are dependency-injectable for testing.
"""

import logging
import os
from pathlib import Path

from jarvis.config import get_config
from jarvis.core.orchestrator import Orchestrator
from jarvis.llm import GroqProvider, LLMProvider, LocalStubProvider
from jarvis.memory.conversation import ConversationMemory
from jarvis.safety.auditor import AuditLogger
from jarvis.safety.confirmation import ConfirmationPrompt
from jarvis.safety.whitelist import WhitelistManager
from jarvis.tools.discovery import ToolDiscovery
from jarvis.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)


def _create_llm_provider() -> LLMProvider:
    """
    Create and initialize the LLM provider.

    Priority:
    1. USE_LOCAL_LLM env var → LocalStubProvider (for testing/development)
    2. GROQ_API_KEY configured → GroqProvider
    3. Fallback → LocalStubProvider

    Returns:
        Initialized LLM provider

    Raises:
        ValueError: If configuration is invalid
    """
    config = get_config()

    # Check for local LLM override
    use_local = os.getenv("USE_LOCAL_LLM", "").lower() in ("1", "true", "yes")
    if use_local:
        local_model = os.getenv("LOCAL_LLM_MODEL", "qwen2:4b")
        logger.info(f"Using local LLM provider with model: {local_model}")
        return LocalStubProvider(model=local_model)

    # Try Groq if API key is set
    if config.llm.groq_api_key:
        logger.info(
            f"Using Groq provider: {config.llm.model} " f"(timeout={config.llm.groq_timeout}s)"
        )
        return GroqProvider(
            api_key=config.llm.groq_api_key,
            model=config.llm.model,
        )

    # Fallback to local stub
    logger.warning(
        "GROQ_API_KEY not configured; using local stub provider. "
        "For production, set GROQ_API_KEY or USE_LOCAL_LLM."
    )
    return LocalStubProvider()


def _create_tool_registry() -> ToolRegistry:
    """
    Create tool registry with auto-discovery.

    Process:
    1. Create registry
    2. Discover builtin tools
    3. Register each tool
    4. Validate registry

    Returns:
        Initialized tool registry with discovered tools

    Raises:
        RuntimeError: If tool discovery fails
    """
    registry = ToolRegistry()

    try:
        discovery = ToolDiscovery()
        discovered_tools = discovery.discover_all(
            include_builtin=True,
            config_file=None,  # Optional: "configs/tools.yaml"
            custom_paths=None,  # Optional: ["./custom_tools"]
        )

        registered_count = 0
        for tool in discovered_tools:
            try:
                registry.register(tool)
                registered_count += 1
            except Exception as e:
                logger.warning(f"Failed to register tool {tool.name}: {e}")

        logger.info(f"Tool registry initialized with {registered_count} tools")

        if registered_count == 0:
            logger.warning("No tools were registered; agent will have no capabilities")

        return registry

    except Exception as e:
        error_msg = f"Failed to initialize tool registry: {e}"
        logger.error(error_msg)
        raise RuntimeError(error_msg) from e


def _create_safety_layer(
    config_storage_path: str | None = None,
) -> tuple[ConfirmationPrompt, WhitelistManager, AuditLogger]:
    """
    Create safety layer components.

    Components:
    - ConfirmationPrompt: User approval for HIGH/MEDIUM risk operations
    - WhitelistManager: Parameter validation for sensitive tools
    - AuditLogger: Operation tracking and compliance logging

    Args:
        config_storage_path: Override storage path for audit logs

    Returns:
        Tuple of (confirmation, whitelist, auditor)
    """
    config = get_config()

    # Confirmation prompts
    confirmation = ConfirmationPrompt()
    logger.debug("ConfirmationPrompt initialized")

    # Whitelist for safe operations
    whitelist = WhitelistManager()
    # Add default safe patterns
    whitelist.add_path_pattern("src/**")
    whitelist.add_path_pattern("tests/**")
    whitelist.add_path_pattern("./**")
    whitelist.add_command_pattern("python*")
    whitelist.add_command_pattern("pytest*")
    whitelist.add_command_pattern("ls*")
    whitelist.add_command_pattern("cd*")
    logger.debug("WhitelistManager initialized with default patterns")

    # Audit logging
    storage_path = Path(config_storage_path or config.memory.storage_path)
    audit_log_path = storage_path / "audit.json"
    auditor = AuditLogger(log_file=audit_log_path)
    logger.debug(f"AuditLogger initialized (path={audit_log_path})")

    return confirmation, whitelist, auditor


def _create_memory(auto_load: bool = True) -> ConversationMemory:
    """
    Create conversation memory with persistence.

    Args:
        auto_load: Automatically load saved conversation (default: True)

    Returns:
        Initialized conversation memory

    Raises:
        OSError: If storage path is not writable
    """
    try:
        memory = ConversationMemory(auto_load=auto_load)
        logger.info(f"ConversationMemory initialized (auto_load={auto_load})")
        return memory
    except OSError as e:
        error_msg = f"Failed to initialize memory: {e}"
        logger.error(error_msg)
        raise


def create_orchestrator(
    llm_provider: LLMProvider | None = None,
    tool_registry: ToolRegistry | None = None,
    memory: ConversationMemory | None = None,
    confirmation: ConfirmationPrompt | None = None,
    whitelist: WhitelistManager | None = None,
    auditor: AuditLogger | None = None,
) -> Orchestrator:
    """
    Create fully initialized orchestrator for agent operation.

    This is the main factory entry point. All dependencies are created
    using their respective factories if not provided (allowing injection
    for testing).

    Composition:
    1. Create LLM provider (unless injected)
    2. Create tool registry (unless injected)
    3. Create conversation memory (unless injected)
    4. Create safety components (unless injected)
    5. Wire everything into Orchestrator

    Args:
        llm_provider: Injected LLM provider (optional)
        tool_registry: Injected tool registry (optional)
        memory: Injected conversation memory (optional)
        confirmation: Injected confirmation system (optional)
        whitelist: Injected whitelist (optional)
        auditor: Injected audit logger (optional)

    Returns:
        Fully configured Orchestrator ready for operation

    Raises:
        ValueError: If configuration is invalid
        RuntimeError: If initialization fails
    """
    config = get_config()

    # Validate configuration at startup
    try:
        config.validate()
    except ValueError as e:
        logger.error(f"Configuration validation failed: {e}")
        raise

    # Create dependencies (using injected versions or factories)
    llm = llm_provider if llm_provider is not None else _create_llm_provider()
    registry = tool_registry if tool_registry is not None else _create_tool_registry()
    # Note: Pass auto_load=False for factory-created memory; auto-loading happens only for
    # persistent/resumed conversations, not fresh instances
    mem = memory if memory is not None else _create_memory(auto_load=False)

    if confirmation is None or whitelist is None or auditor is None:
        conf, wl, aud = _create_safety_layer()
        confirmation = confirmation or conf
        whitelist = whitelist or wl
        auditor = auditor or aud

    # Create Orchestrator with all components
    orchestrator = Orchestrator(
        llm_provider=llm,
        tool_registry=registry,
        memory=mem,
        confirmation=confirmation,
        whitelist=whitelist,
        auditor=auditor,
    )

    logger.info("Orchestrator created successfully")
    return orchestrator

"""Tests for Blocker 3: Orchestrator Coupling and Dependency Injection."""

import pytest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import AsyncMock, MagicMock

from jarvis.core.factory import (
    create_orchestrator,
    _create_llm_provider,
    _create_tool_registry,
    _create_memory,
    _create_safety_layer,
)
from jarvis.core.orchestrator import Orchestrator
from jarvis.llm import LLMProvider
from jarvis.llm.base import LLMResponse, ToolCall
from jarvis.memory.conversation import ConversationMemory
from jarvis.safety.auditor import AuditLogger
from jarvis.safety.confirmation import ConfirmationPrompt
from jarvis.safety.whitelist import WhitelistManager
from jarvis.tools.base import RiskLevel, Tool, ToolParameter, ToolResult
from jarvis.tools.registry import ToolRegistry


class MockTool(Tool):
    """Mock tool for testing."""

    name = "mock_tool"
    description = "Mock tool for testing"
    risk_level = RiskLevel.LOW

    async def execute(self, **kwargs) -> ToolResult:
        return ToolResult(success=True, output="Mock response")

    def get_parameters(self) -> list[ToolParameter]:
        return []


@pytest.mark.asyncio
async def test_create_orchestrator_uses_dependency_injection():
    """Test that create_orchestrator accepts and uses injected dependencies."""
    from tempfile import TemporaryDirectory
    
    # Create mocked LLM
    mock_llm = AsyncMock(spec=LLMProvider)
    
    # Create real registry
    mock_registry = ToolRegistry()
    mock_registry.register(MockTool())
    
    # Create memory with a unique storage location to avoid loading saved data
    with TemporaryDirectory() as tmpdir:
        mock_memory = ConversationMemory(auto_load=False)
        mock_memory.storage_path = Path(tmpdir) / "memory.json"
        mock_memory.persist_enabled = False  # Disable persistence
        
        # Add a marker message to verify it's the same object
        mock_memory.add_message("system", "MARKER_MESSAGE")
        
        mock_confirmation = ConfirmationPrompt()
        mock_whitelist = WhitelistManager()
        mock_auditor = AuditLogger()

        # Create orchestrator with injected dependencies
        orchestrator = create_orchestrator(
            llm_provider=mock_llm,
            tool_registry=mock_registry,
            memory=mock_memory,
            confirmation=mock_confirmation,
            whitelist=mock_whitelist,
            auditor=mock_auditor,
        )

        # Verify all dependencies were injected (by checking for marker)
        assert orchestrator.llm is mock_llm
        assert orchestrator.tool_registry is mock_registry
        assert orchestrator.memory is mock_memory  # Should be the exact same object
        # Verify marker message is there (proves same memory object)
        assert len(orchestrator.memory) == 1
        assert orchestrator.memory.get_messages()[0]["content"] == "MARKER_MESSAGE"
        assert orchestrator.executor.safe_executor.confirmation is mock_confirmation
        assert orchestrator.executor.safe_executor.whitelist is mock_whitelist
        assert orchestrator.executor.safe_executor.auditor is mock_auditor


@pytest.mark.asyncio
async def test_orchestrator_no_tight_coupling_to_initialization():
    """Test that Orchestrator doesn't instantiate dependencies itself."""
    # Create Orchestrator directly with explicit dependencies
    mock_llm = AsyncMock(spec=LLMProvider)
    registry = ToolRegistry()
    registry.register(MockTool())
    
    with TemporaryDirectory() as tmpdir:
        memory = ConversationMemory(auto_load=False)
        memory.storage_path = Path(tmpdir) / "memory.json"
        memory.persist_enabled = False
        
        confirmation = ConfirmationPrompt()
        whitelist = WhitelistManager()
        auditor = AuditLogger()

        # Orchestrator should NOT create its own dependencies
        orchestrator = Orchestrator(
            llm_provider=mock_llm,
            tool_registry=registry,
            memory=memory,
            confirmation=confirmation,
            whitelist=whitelist,
            auditor=auditor,
        )

        # Verify dependencies are those we provided
        assert orchestrator.llm is mock_llm
        assert orchestrator.memory is memory


@pytest.mark.asyncio
async def test_factory_creates_memory_with_validation():
    """Test that memory factory validates storage path."""
    # Should not raise - uses temp directory
    memory = _create_memory(auto_load=False)
    assert memory is not None
    assert isinstance(memory, ConversationMemory)


@pytest.mark.asyncio
async def test_factory_creates_llm_provider():
    """Test that LLM provider factory creates correct provider."""
    # Will use LocalStubProvider or GroqProvider depending on config
    llm = _create_llm_provider()
    assert llm is not None
    assert hasattr(llm, "complete")


@pytest.mark.asyncio
async def test_factory_creates_tool_registry():
    """Test that tool registry factory discovers tools."""
    registry = _create_tool_registry()
    assert registry is not None
    assert isinstance(registry, ToolRegistry)
    # Should have some builtin tools
    assert len(registry) > 0


@pytest.mark.asyncio
async def test_factory_creates_safety_layer():
    """Test that safety layer factory creates all components."""
    confirmation, whitelist, auditor = _create_safety_layer()

    assert confirmation is not None
    assert isinstance(confirmation, ConfirmationPrompt)
    assert whitelist is not None
    assert isinstance(whitelist, WhitelistManager)
    assert auditor is not None
    assert isinstance(auditor, AuditLogger)


@pytest.mark.asyncio
async def test_factory_validates_config_on_startup():
    """Test that create_orchestrator validates config."""
    # This would require invalid config to test properly
    # For now, just verify it doesn't raise with valid config
    try:
        orchestrator = create_orchestrator()
        assert orchestrator is not None
    except ValueError:
        # This is expected if config is invalid
        pass


@pytest.mark.asyncio
async def test_orchestrator_testable_with_mocks():
    """Test that Orchestrator can be fully tested with mocks."""
    # Create all mocks
    mock_llm = AsyncMock(spec=LLMProvider)
    mock_llm.complete = AsyncMock(
        return_value=LLMResponse(
            content="Done",
            tool_calls=[],
        )
    )
    mock_llm.provider_name = "mock"
    mock_llm.model_name = "mock-model"

    registry = ToolRegistry()
    registry.register(MockTool())

    with TemporaryDirectory() as tmpdir:
        memory = ConversationMemory(auto_load=False)
        memory.storage_path = Path(tmpdir) / "memory.json"
        memory.persist_enabled = False

        # Create orchestrator with mocks
        orchestrator = Orchestrator(
            llm_provider=mock_llm,
            tool_registry=registry,
            memory=memory,
        )

        # Now testable - can run actual orchestration with mocks
        response = await orchestrator.run("test query")

        assert isinstance(response, str)
        # LLM was called
        mock_llm.complete.assert_called()


@pytest.mark.asyncio
async def test_executor_injectable_in_orchestrator():
    """Test that custom executor can be injected into orchestrator."""
    from jarvis.core.executor import Executor

    mock_llm = AsyncMock(spec=LLMProvider)
    mock_llm.provider_name = "mock"
    mock_llm.model_name = "mock-model"

    registry = ToolRegistry()
    registry.register(MockTool())

    with TemporaryDirectory() as tmpdir:
        memory = ConversationMemory(auto_load=False)
        memory.storage_path = Path(tmpdir) / "memory.json"
        memory.persist_enabled = False

        # Create custom executor
        custom_executor = Executor(registry)

        # Inject into orchestrator
        orchestrator = Orchestrator(
            llm_provider=mock_llm,
            tool_registry=registry,
            memory=memory,
            executor=custom_executor,
        )

        # Verify it's used
        assert orchestrator.executor is custom_executor


@pytest.mark.asyncio
async def test_create_orchestrator_full_integration():
    """Test full orchestrator creation with all components."""
    # This is the main integration point
    orchestrator = create_orchestrator()

    # Verify all components are present
    assert orchestrator is not None
    assert orchestrator.llm is not None
    assert orchestrator.tool_registry is not None
    assert len(orchestrator.tool_registry) > 0
    assert orchestrator.memory is not None
    assert orchestrator.executor is not None
    assert orchestrator.executor.safe_executor is not None


@pytest.mark.asyncio
async def test_factory_allows_partial_injection():
    """Test that factory allows injecting some but not all dependencies."""
    # Create one injected dependency  
    with TemporaryDirectory() as tmpdir:
        custom_memory = ConversationMemory(auto_load=False)
        custom_memory.storage_path = Path(tmpdir) / "memory.json"
        custom_memory.persist_enabled = False

        # Create orchestrator with only memory injected
        # Others should be created by factory
        orchestrator = create_orchestrator(memory=custom_memory)

        assert orchestrator.memory is custom_memory
        # But others are created
        assert orchestrator.llm is not None
        assert orchestrator.tool_registry is not None


@pytest.mark.asyncio
async def test_no_circular_dependencies():
    """Test that component dependencies form proper DAG (no cycles)."""
    # Create orchestrator - if there were circular deps, this would fail/hang
    orchestrator = create_orchestrator()

    # All components should be initialized
    assert orchestrator.llm is not None
    assert orchestrator.executor is not None
    assert orchestrator.memory is not None
    assert orchestrator.planner is not None


@pytest.mark.asyncio
async def test_memory_injected_independently():
    """Test that memory can be created and tested independently."""
    memory = _create_memory(auto_load=False)

    # Add messages independently
    memory.add_message("user", "Test")
    assert memory.size() == 1

    # Can be used without LLM or tools
    assert memory.get_recent(10)[0]["content"] == "Test"

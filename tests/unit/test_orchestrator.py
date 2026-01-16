"""Tests for Orchestrator."""

import pytest
from unittest.mock import AsyncMock

from jarvis.core.orchestrator import Orchestrator
from jarvis.llm.base import LLMResponse, ToolCall
from jarvis.memory import ConversationMemory
from jarvis.tools.base import RiskLevel, Tool, ToolParameter, ToolResult
from jarvis.tools.registry import ToolRegistry


class SampleTool(Tool):
    """Sample tool for orchestrator tests."""

    name = "sample_tool"
    description = "A sample tool"
    risk_level = RiskLevel.LOW

    async def execute(self, **kwargs) -> ToolResult:
        """Execute."""
        return ToolResult(success=True, output="Sample output")

    def get_parameters(self) -> list[ToolParameter]:
        """Get parameters."""
        return [
            ToolParameter(
                name="param",
                type="string",
                description="Sample parameter",
                required=True,
            )
        ]


@pytest.mark.asyncio
async def test_orchestrator_initialization() -> None:
    """Test orchestrator initializes correctly."""
    mock_llm = AsyncMock()
    registry = ToolRegistry()
    memory = ConversationMemory()

    orchestrator = Orchestrator(mock_llm, registry, memory, max_iterations=5)

    assert orchestrator.max_iterations == 5
    assert orchestrator.llm == mock_llm
    assert orchestrator.tool_registry == registry


@pytest.mark.asyncio
async def test_orchestrator_with_tool_call() -> None:
    """Test orchestrator with tool call."""
    registry = ToolRegistry()
    registry.register(SampleTool())

    mock_llm = AsyncMock()
    mock_llm.complete.side_effect = [
        LLMResponse(
            content="I'll use the sample tool",
            tool_calls=[
                ToolCall(
                    id="call_1",
                    name="sample_tool",
                    arguments={"param": "value"},
                )
            ],
        ),
        LLMResponse(content="Task completed successfully"),
    ]

    memory = ConversationMemory()
    orchestrator = Orchestrator(mock_llm, registry, memory)

    response = await orchestrator.run("Use the sample tool")

    assert "completed" in response.lower()
    assert mock_llm.complete.call_count == 2


@pytest.mark.asyncio
async def test_orchestrator_max_iterations() -> None:
    """Test orchestrator respects max iterations."""
    registry = ToolRegistry()
    registry.register(SampleTool())

    mock_llm = AsyncMock()
    mock_llm.complete.return_value = LLMResponse(
        content="Calling tool again",
        tool_calls=[ToolCall(id="call_1", name="sample_tool", arguments={"param": "value"})],
    )

    memory = ConversationMemory()
    orchestrator = Orchestrator(mock_llm, registry, memory, max_iterations=3)

    response = await orchestrator.run("Test")

    assert "maximum" in response.lower() or "iterations" in response.lower()
    assert mock_llm.complete.call_count <= 3


@pytest.mark.asyncio
async def test_orchestrator_tool_execution_error() -> None:
    """Test orchestrator handles tool execution errors."""

    class FailingTool(Tool):
        name = "failing_tool"
        description = "A tool that fails"
        risk_level = RiskLevel.LOW

        async def execute(self, **kwargs) -> ToolResult:
            return ToolResult(success=False, output=None, error="Execution failed")

        def get_parameters(self) -> list[ToolParameter]:
            return []

    registry = ToolRegistry()
    registry.register(FailingTool())

    mock_llm = AsyncMock()
    mock_llm.complete.side_effect = [
        LLMResponse(
            content="Using failing tool",
            tool_calls=[ToolCall(id="call_1", name="failing_tool", arguments={})],
        ),
        LLMResponse(content="Tool failed, but handled gracefully"),
    ]

    memory = ConversationMemory()
    orchestrator = Orchestrator(mock_llm, registry, memory)

    response = await orchestrator.run("Test")

    assert "gracefully" in response.lower() or "failed" in response.lower()


def test_orchestrator_reset() -> None:
    """Test orchestrator reset."""
    mock_llm = AsyncMock()
    registry = ToolRegistry()
    memory = ConversationMemory()
    memory.add_message("user", "test")

    orchestrator = Orchestrator(mock_llm, registry, memory)
    assert memory.size() == 1

    orchestrator.reset()
    assert memory.size() == 0


def test_orchestrator_get_stats() -> None:
    """Test getting orchestrator statistics."""
    mock_llm = AsyncMock()
    mock_llm.provider_name = "test_provider"
    mock_llm.model_name = "test_model"

    registry = ToolRegistry()
    registry.register(SampleTool())

    memory = ConversationMemory()
    orchestrator = Orchestrator(mock_llm, registry, memory, max_iterations=10)

    stats = orchestrator.get_stats()
    assert stats["max_iterations"] == 10
    assert stats["tools_available"] == 1
    assert stats["llm_provider"] == "test_provider"

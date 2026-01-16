"""Tests for Executor."""

import pytest

from jarvis.core.executor import Executor
from jarvis.tools.base import RiskLevel, Tool, ToolParameter, ToolResult
from jarvis.tools.registry import ToolRegistry


class MockTool(Tool):
    """Mock tool for testing."""

    name = "mock_tool"
    description = "A mock tool"
    risk_level = RiskLevel.LOW

    async def execute(self, **kwargs) -> ToolResult:
        """Execute mock tool."""
        value = kwargs.get("value", "default")
        return ToolResult(success=True, output=f"Processed: {value}")

    def get_parameters(self) -> list[ToolParameter]:
        """Get parameters."""
        return [
            ToolParameter(
                name="value",
                type="string",
                description="Test value",
                required=True,
            )
        ]


class FailingTool(Tool):
    """Tool that always fails."""

    name = "failing_tool"
    description = "A tool that fails"
    risk_level = RiskLevel.LOW

    async def execute(self, **kwargs) -> ToolResult:
        """Execute and fail."""
        return ToolResult(success=False, output=None, error="Tool failed")

    def get_parameters(self) -> list[ToolParameter]:
        """Get parameters."""
        return []


def test_executor_initialization() -> None:
    """Test executor initializes correctly."""
    registry = ToolRegistry()
    executor = Executor(registry)

    assert executor.execution_count == 0
    stats = executor.get_stats()
    assert stats["total_executions"] == 0


@pytest.mark.asyncio
async def test_execute_tool_success() -> None:
    """Test successful tool execution."""
    registry = ToolRegistry()
    registry.register(MockTool())
    executor = Executor(registry)

    result = await executor.execute_tool("mock_tool", {"value": "test"})

    assert result.success is True
    assert result.output == "Processed: test"
    assert result.error is None
    assert executor.execution_count == 1


@pytest.mark.asyncio
async def test_execute_tool_not_found() -> None:
    """Test executing non-existent tool."""
    registry = ToolRegistry()
    executor = Executor(registry)

    result = await executor.execute_tool("nonexistent", {})

    assert result.success is False
    assert "not found" in result.error


@pytest.mark.asyncio
async def test_execute_tool_invalid_params() -> None:
    """Test executing tool with invalid parameters."""
    registry = ToolRegistry()
    registry.register(MockTool())
    executor = Executor(registry)

    # Missing required 'value' parameter
    result = await executor.execute_tool("mock_tool", {})

    assert result.success is False
    assert "Missing required parameters" in result.error


@pytest.mark.asyncio
async def test_execute_tool_failure() -> None:
    """Test tool that returns failure."""
    registry = ToolRegistry()
    registry.register(FailingTool())
    executor = Executor(registry)

    result = await executor.execute_tool("failing_tool", {})

    assert result.success is False
    assert result.error == "Tool failed"


@pytest.mark.asyncio
async def test_execution_count() -> None:
    """Test execution count increments."""
    registry = ToolRegistry()
    registry.register(MockTool())
    executor = Executor(registry)

    assert executor.execution_count == 0

    await executor.execute_tool("mock_tool", {"value": "1"})
    assert executor.execution_count == 1

    await executor.execute_tool("mock_tool", {"value": "2"})
    assert executor.execution_count == 2


def test_reset_stats() -> None:
    """Test resetting execution statistics."""
    registry = ToolRegistry()
    executor = Executor(registry)
    executor.execution_count = 5

    executor.reset_stats()
    assert executor.execution_count == 0


def test_get_stats() -> None:
    """Test getting executor statistics."""
    registry = ToolRegistry()
    registry.register(MockTool())
    executor = Executor(registry)
    executor.execution_count = 3

    stats = executor.get_stats()
    assert stats["total_executions"] == 3
    assert stats["tools_available"] == 1

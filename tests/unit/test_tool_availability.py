"""
Tests for tool availability logic and state management in orchestrator.

These tests verify tools are consistently available to the LLM
across all ReAct iterations and separate requests.
"""

from unittest.mock import AsyncMock

import pytest
from jarvis.core.orchestrator import Orchestrator
from jarvis.llm.base import LLMResponse, ToolCall
from jarvis.memory.conversation import ConversationMemory
from jarvis.tools.base import RiskLevel, Tool, ToolParameter, ToolResult
from jarvis.tools.registry import ToolRegistry


class DummyTool(Tool):
    """Test tool for orchestrator tests."""

    name = "dummy_tool"
    description = "A test tool"
    risk_level = RiskLevel.LOW

    def get_parameters(self) -> list[ToolParameter]:
        """Return tool parameters."""
        return [ToolParameter(name="value", type="string", description="Test value")]

    async def execute(self, value: str) -> ToolResult:
        """Execute the test tool."""
        return ToolResult(success=True, output=f"Executed with {value}")


@pytest.mark.asyncio
async def test_tool_availability_provided_each_iteration():
    """
    Tools should be provided on every iteration, including after tool calls.
    """
    # Setup
    registry = ToolRegistry()
    registry.register(DummyTool())

    memory = ConversationMemory(auto_load=False)

    # Mock LLM that returns tool call first, then final response
    mock_llm = AsyncMock()
    mock_llm.provider_name = "test"
    mock_llm.model_name = "test-model"

    # First call: LLM returns a tool call
    first_response = LLMResponse(
        content="I'll use the tool",
        tool_calls=[ToolCall(name="dummy_tool", arguments={"value": "test"})],
    )

    # Second call: LLM returns final response
    second_response = LLMResponse(
        content="Done!",
        tool_calls=None,
    )

    mock_llm.complete.side_effect = [first_response, second_response]

    orchestrator = Orchestrator(
        llm_provider=mock_llm,
        tool_registry=registry,
        memory=memory,
        max_iterations=3,
    )

    # Execute
    result = await orchestrator.run("Test query")

    # Verify
    assert result == "Done!"
    assert mock_llm.complete.call_count == 2

    # First call should have tools
    first_call = mock_llm.complete.call_args_list[0]
    assert first_call[1]["tools"] is not None
    assert len(first_call[1]["tools"]) > 0

    # Second call should also have tools
    second_call = mock_llm.complete.call_args_list[1]
    assert second_call[1]["tools"] is not None
    assert len(second_call[1]["tools"]) > 0


@pytest.mark.asyncio
async def test_tool_availability_allows_multi_step_usage():
    """
    If LLM requests tools across multiple iterations, schemas should remain available.
    """
    # Setup
    registry = ToolRegistry()
    registry.register(DummyTool())

    memory = ConversationMemory(auto_load=False)

    mock_llm = AsyncMock()
    mock_llm.provider_name = "test"
    mock_llm.model_name = "test-model"

    # LLM calls tool on first AND second iteration
    response_with_tool = LLMResponse(
        content="Using tool",
        tool_calls=[ToolCall(name="dummy_tool", arguments={"value": "test"})],
    )

    final_response = LLMResponse(content="Done", tool_calls=None)

    # Simulate: first call with tool, second call with tool, third call finalizes
    mock_llm.complete.side_effect = [
        response_with_tool,
        response_with_tool,
        final_response,
    ]

    orchestrator = Orchestrator(
        llm_provider=mock_llm,
        tool_registry=registry,
        memory=memory,
        max_iterations=5,
    )

    # Execute
    await orchestrator.run("Test query")

    # Verify tools are still provided in later iterations
    second_call = mock_llm.complete.call_args_list[1]
    assert second_call[1]["tools"] is not None
    assert len(second_call[1]["tools"]) > 0


@pytest.mark.asyncio
async def test_tool_availability_flag_resets_per_request():
    """
    Verify tools are provided on first iteration of each separate request.
    """
    # Setup
    registry = ToolRegistry()
    registry.register(DummyTool())

    memory = ConversationMemory(auto_load=False)

    mock_llm = AsyncMock()
    mock_llm.provider_name = "test"
    mock_llm.model_name = "test-model"

    # Each request: tool call then response
    mock_llm.complete.side_effect = [
        LLMResponse(
            content="Tool", tool_calls=[ToolCall(name="dummy_tool", arguments={"value": "1"})]
        ),
        LLMResponse(content="Done 1", tool_calls=None),
        LLMResponse(
            content="Tool", tool_calls=[ToolCall(name="dummy_tool", arguments={"value": "2"})]
        ),
        LLMResponse(content="Done 2", tool_calls=None),
    ]

    orchestrator = Orchestrator(
        llm_provider=mock_llm,
        tool_registry=registry,
        memory=memory,
        max_iterations=3,
    )

    # First request
    result1 = await orchestrator.run("Request 1")
    assert result1 == "Done 1"

    # Second request should also get tools on first iteration
    result2 = await orchestrator.run("Request 2")
    assert result2 == "Done 2"

    # Verify tools were provided on iteration 1 of both requests
    call_1_first = mock_llm.complete.call_args_list[0]
    call_2_first = mock_llm.complete.call_args_list[2]

    assert call_1_first[1]["tools"] is not None  # Request 1, iteration 1
    assert call_2_first[1]["tools"] is not None  # Request 2, iteration 1

"""Tests for LLM provider base class."""

from jarvis.llm.base import LLMResponse, ToolCall


def test_tool_call_creation() -> None:
    """Test ToolCall dataclass."""
    call = ToolCall(name="test_tool", arguments={"arg1": "value1"})
    assert call.name == "test_tool"
    assert call.arguments == {"arg1": "value1"}
    assert call.id is None


def test_tool_call_with_id() -> None:
    """Test ToolCall with ID."""
    call = ToolCall(name="test_tool", arguments={"arg1": "value1"}, id="call_123")
    assert call.id == "call_123"


def test_llm_response_content_only() -> None:
    """Test LLMResponse with only content."""
    response = LLMResponse(content="Hello world")
    assert response.content == "Hello world"
    assert response.tool_calls is None
    assert response.stop_reason is None


def test_llm_response_with_tool_calls() -> None:
    """Test LLMResponse with tool calls."""
    tool_calls = [
        ToolCall(name="tool1", arguments={"param": "value"}),
        ToolCall(name="tool2", arguments={"param2": "value2"}),
    ]
    response = LLMResponse(
        content="",
        tool_calls=tool_calls,
        stop_reason="tool_calls",
    )
    assert len(response.tool_calls) == 2
    assert response.tool_calls[0].name == "tool1"
    assert response.stop_reason == "tool_calls"


def test_llm_response_with_tokens() -> None:
    """Test LLMResponse with token count."""
    response = LLMResponse(
        content="Response",
        tokens_used=150,
    )
    assert response.tokens_used == 150

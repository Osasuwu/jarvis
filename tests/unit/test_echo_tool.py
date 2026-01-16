"""Tests for EchoTool."""

import pytest

from jarvis.tools.builtin import EchoTool
from jarvis.tools.base import RiskLevel


def test_echo_tool_properties() -> None:
    """Test EchoTool properties."""
    tool = EchoTool()
    
    assert tool.name == "echo"
    assert tool.risk_level == RiskLevel.LOW
    assert tool.requires_confirmation is False
    assert "utility" in tool.capabilities
    assert "test" in tool.capabilities


@pytest.mark.asyncio
async def test_echo_tool_basic() -> None:
    """Test basic echo functionality."""
    tool = EchoTool()
    
    result = await tool.execute(text="Hello World")
    
    assert result.success is True
    assert result.output == "Echo: Hello World"
    assert result.error is None


@pytest.mark.asyncio
async def test_echo_tool_with_prefix() -> None:
    """Test echo with custom prefix."""
    tool = EchoTool()
    
    result = await tool.execute(text="Test", prefix="Reply:")
    
    assert result.success is True
    assert result.output == "Reply: Test"


@pytest.mark.asyncio
async def test_echo_tool_empty_text() -> None:
    """Test echo with empty text."""
    tool = EchoTool()
    
    result = await tool.execute(text="")
    
    assert result.success is True
    assert result.output == "Echo: "


def test_echo_tool_parameters() -> None:
    """Test echo tool parameters."""
    tool = EchoTool()
    params = tool.get_parameters()
    
    assert len(params) == 2
    
    # Check text parameter
    text_param = params[0]
    assert text_param.name == "text"
    assert text_param.type == "string"
    assert text_param.required is True
    
    # Check prefix parameter
    prefix_param = params[1]
    assert prefix_param.name == "prefix"
    assert prefix_param.type == "string"
    assert prefix_param.required is False
    assert prefix_param.default == "Echo:"


def test_echo_tool_llm_schema() -> None:
    """Test LLM schema generation."""
    tool = EchoTool()
    schema = tool.to_llm_schema()
    
    assert schema["function"]["name"] == "echo"
    assert "text" in schema["function"]["parameters"]["properties"]
    assert "prefix" in schema["function"]["parameters"]["properties"]
    assert "text" in schema["function"]["parameters"]["required"]
    assert "prefix" not in schema["function"]["parameters"]["required"]

"""Tests for Tool base class."""

import pytest

from jarvis.tools.base import RiskLevel, Tool, ToolParameter, ToolResult


def test_risk_level_enum() -> None:
    """Test RiskLevel enum values."""
    assert RiskLevel.LOW.value == "LOW"
    assert RiskLevel.MEDIUM.value == "MEDIUM"
    assert RiskLevel.HIGH.value == "HIGH"


def test_tool_result_success() -> None:
    """Test ToolResult for successful execution."""
    result = ToolResult(success=True, output="Result data")
    assert result.success is True
    assert result.output == "Result data"
    assert result.error is None


def test_tool_result_failure() -> None:
    """Test ToolResult for failed execution."""
    result = ToolResult(
        success=False,
        output=None,
        error="Something went wrong",
    )
    assert result.success is False
    assert result.error == "Something went wrong"


def test_tool_result_with_tokens() -> None:
    """Test ToolResult with token usage."""
    result = ToolResult(
        success=True,
        output="data",
        tokens_used=100,
    )
    assert result.tokens_used == 100


def test_tool_parameter_creation() -> None:
    """Test ToolParameter creation."""
    param = ToolParameter(
        name="input_text",
        type="string",
        description="Input text",
        required=True,
    )
    assert param.name == "input_text"
    assert param.type == "string"
    assert param.required is True


def test_tool_parameter_with_default() -> None:
    """Test ToolParameter with default value."""
    param = ToolParameter(
        name="count",
        type="integer",
        description="Number of items",
        required=False,
        default=10,
    )
    assert param.required is False
    assert param.default == 10


def test_tool_parameter_with_enum() -> None:
    """Test ToolParameter with enum values."""
    param = ToolParameter(
        name="color",
        type="string",
        description="Color choice",
        enum=["red", "green", "blue"],
    )
    assert param.enum == ["red", "green", "blue"]


class SimpleTool(Tool):
    """Simple tool for testing."""

    name = "simple_tool"
    description = "A simple test tool"
    risk_level = RiskLevel.LOW

    async def execute(self, **kwargs) -> ToolResult:
        """Execute the tool."""
        return ToolResult(success=True, output="executed")

    def get_parameters(self) -> list[ToolParameter]:
        """Get parameters."""
        return [
            ToolParameter(
                name="param1",
                type="string",
                description="Parameter 1",
            ),
        ]


def test_tool_instantiation() -> None:
    """Test Tool subclass instantiation."""
    tool = SimpleTool()
    assert tool.name == "simple_tool"
    assert tool.description == "A simple test tool"
    assert tool.risk_level == RiskLevel.LOW


def test_tool_to_llm_schema() -> None:
    """Test Tool conversion to LLM schema."""
    tool = SimpleTool()
    schema = tool.to_llm_schema()

    assert schema["type"] == "function"
    assert schema["function"]["name"] == "simple_tool"
    assert schema["function"]["description"] == "A simple test tool"
    assert "param1" in schema["function"]["parameters"]["properties"]


def test_tool_to_manifest() -> None:
    """Test Tool conversion to manifest."""
    tool = SimpleTool()
    manifest = tool.to_manifest()

    assert manifest["name"] == "simple_tool"
    assert manifest["description"] == "A simple test tool"
    assert manifest["risk_level"] == "LOW"
    assert len(manifest["parameters"]) == 1


@pytest.mark.asyncio
async def test_tool_execute() -> None:
    """Test Tool execution."""
    tool = SimpleTool()
    result = await tool.execute()
    assert result.success is True
    assert result.output == "executed"

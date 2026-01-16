"""Tests for Tool Registry."""

import pytest

from jarvis.tools.base import RiskLevel, Tool, ToolParameter, ToolResult
from jarvis.tools.registry import ToolRegistry


class SampleTool(Tool):
    """Test tool for registry testing."""

    name = "test_tool"
    description = "Test tool"
    risk_level = RiskLevel.LOW
    capabilities = ["file", "read"]

    async def execute(self, **kwargs) -> ToolResult:
        """Execute tool."""
        return ToolResult(success=True, output="test")

    def get_parameters(self) -> list[ToolParameter]:
        """Get parameters."""
        return [
            ToolParameter(
                name="path",
                type="string",
                description="File path",
            ),
        ]


class HighRiskTool(Tool):
    """High risk test tool."""

    name = "dangerous_tool"
    description = "Dangerous tool"
    risk_level = RiskLevel.HIGH
    requires_confirmation = True
    capabilities = ["shell", "execute"]

    async def execute(self, **kwargs) -> ToolResult:
        """Execute tool."""
        return ToolResult(success=True, output="dangerous")

    def get_parameters(self) -> list[ToolParameter]:
        """Get parameters."""
        return []


def test_registry_register_tool() -> None:
    """Test registering a tool."""
    registry = ToolRegistry()
    tool = SampleTool()

    registry.register(tool)
    assert len(registry) == 1
    assert registry.get("test_tool") is tool


def test_registry_duplicate_registration() -> None:
    """Test registering duplicate tool name raises error."""
    registry = ToolRegistry()
    tool1 = SampleTool()
    tool2 = SampleTool()

    registry.register(tool1)
    with pytest.raises(ValueError, match="already registered"):
        registry.register(tool2)


def test_registry_unregister() -> None:
    """Test unregistering a tool."""
    registry = ToolRegistry()
    tool = SampleTool()

    registry.register(tool)
    assert len(registry) == 1

    removed = registry.unregister("test_tool")
    assert removed is True
    assert len(registry) == 0


def test_registry_unregister_nonexistent() -> None:
    """Test unregistering nonexistent tool."""
    registry = ToolRegistry()
    removed = registry.unregister("nonexistent")
    assert removed is False


def test_registry_get() -> None:
    """Test getting a tool by name."""
    registry = ToolRegistry()
    tool = SampleTool()
    registry.register(tool)

    retrieved = registry.get("test_tool")
    assert retrieved is tool

    nonexistent = registry.get("nonexistent")
    assert nonexistent is None


def test_registry_get_all() -> None:
    """Test getting all tools."""
    registry = ToolRegistry()
    tool1 = SampleTool()
    tool2 = HighRiskTool()

    registry.register(tool1)
    registry.register(tool2)

    all_tools = registry.get_all()
    assert len(all_tools) == 2
    assert tool1 in all_tools
    assert tool2 in all_tools


def test_registry_find_by_capability() -> None:
    """Test finding tools by capability."""
    registry = ToolRegistry()
    file_tool = SampleTool()
    shell_tool = HighRiskTool()

    registry.register(file_tool)
    registry.register(shell_tool)

    file_tools = registry.find_by_capability("file")
    assert len(file_tools) == 1
    assert file_tools[0].name == "test_tool"

    shell_tools = registry.find_by_capability("shell")
    assert len(shell_tools) == 1
    assert shell_tools[0].name == "dangerous_tool"


def test_registry_find_by_risk_level() -> None:
    """Test finding tools by risk level."""
    registry = ToolRegistry()
    low_tool = SampleTool()
    high_tool = HighRiskTool()

    registry.register(low_tool)
    registry.register(high_tool)

    low_tools = registry.find_by_risk_level(RiskLevel.LOW)
    assert len(low_tools) == 1

    high_tools = registry.find_by_risk_level(RiskLevel.HIGH)
    assert len(high_tools) == 1


def test_registry_get_llm_schemas() -> None:
    """Test getting LLM schemas for all tools."""
    registry = ToolRegistry()
    registry.register(SampleTool())

    schemas = registry.get_llm_schemas()
    assert len(schemas) == 1
    assert schemas[0]["function"]["name"] == "test_tool"


def test_registry_get_manifests() -> None:
    """Test getting manifests for all tools."""
    registry = ToolRegistry()
    registry.register(SampleTool())

    manifests = registry.get_manifests()
    assert len(manifests) == 1
    assert manifests[0]["name"] == "test_tool"


def test_registry_validate_parameters_success() -> None:
    """Test parameter validation success."""
    registry = ToolRegistry()
    registry.register(SampleTool())

    is_valid, error = registry.validate_parameters("test_tool", path="/some/path")
    assert is_valid is True
    assert error == ""


def test_registry_validate_parameters_missing_required() -> None:
    """Test parameter validation with missing required parameter."""
    registry = ToolRegistry()
    registry.register(SampleTool())

    is_valid, error = registry.validate_parameters("test_tool")
    assert is_valid is False
    assert "Missing required parameters" in error


def test_registry_validate_parameters_unexpected() -> None:
    """Test parameter validation with unexpected parameters."""
    registry = ToolRegistry()
    registry.register(SampleTool())

    is_valid, error = registry.validate_parameters(
        "test_tool",
        path="/some/path",
        unknown_param="value",
    )
    assert is_valid is False
    assert "Unexpected parameters" in error


def test_registry_validate_parameters_nonexistent_tool() -> None:
    """Test parameter validation for nonexistent tool."""
    registry = ToolRegistry()

    is_valid, error = registry.validate_parameters("nonexistent")
    assert is_valid is False
    assert "not found" in error


def test_registry_contains() -> None:
    """Test __contains__ operator."""
    registry = ToolRegistry()
    tool = SampleTool()

    assert "test_tool" not in registry
    registry.register(tool)
    assert "test_tool" in registry


def test_registry_repr() -> None:
    """Test string representation."""
    registry = ToolRegistry()
    assert "0 tools" in repr(registry)

    registry.register(SampleTool())
    assert "1 tools" in repr(registry)

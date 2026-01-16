"""Tests for tool discovery system."""

import pytest
from jarvis.tools.base import Tool, ToolParameter, ToolResult, RiskLevel
from jarvis.tools.discovery import ToolDiscovery
from jarvis.tools.loader import ToolLoader


class MockTool(Tool):
    """Mock tool for testing."""

    name = "mock_tool"
    description = "A mock tool for testing"
    risk_level = RiskLevel.LOW
    
    async def execute(self, **kwargs):
        return ToolResult(success=True, output="mock output")
    
    def get_parameters(self):
        return []


class DuplicateTool(Tool):
    """Another tool with same name for testing duplicates."""

    name = "mock_tool"  # Same name as MockTool
    description = "Duplicate tool"
    risk_level = RiskLevel.LOW
    
    async def execute(self, **kwargs):
        return ToolResult(success=True, output="duplicate output")
    
    def get_parameters(self):
        return []


def test_tool_loader_from_class():
    """Test loading a tool from a class."""
    loader = ToolLoader()
    tool = loader.load_from_class(MockTool)
    
    assert tool is not None
    assert tool.name == "mock_tool"
    assert tool.description == "A mock tool for testing"


def test_tool_loader_validate_class():
    """Test tool class validation."""
    loader = ToolLoader()
    
    # Valid tool class
    assert loader.validate_tool_class(MockTool) is True
    
    # Invalid - base Tool class
    assert loader.validate_tool_class(Tool) is False
    
    # Invalid - not a class
    assert loader.validate_tool_class("not a class") is False
    
    # Invalid - not a Tool subclass
    class NotATool:
        pass
    assert loader.validate_tool_class(NotATool) is False


def test_discovery_builtin_tools():
    """Test discovery of builtin tools."""
    discovery = ToolDiscovery()
    tools = discovery.discover_all(include_builtin=True)
    
    # Should discover all builtin tools
    assert len(tools) > 0
    
    # Check for known builtin tools
    tool_names = [t.name for t in tools]
    assert "echo" in tool_names
    assert "file_read" in tool_names
    assert "list_directory" in tool_names


def test_discovery_deduplication(monkeypatch):
    """Test that duplicate tool names are handled correctly."""
    # Create a custom loader that returns our mock tools
    loader = ToolLoader()
    
    # Manually test deduplication logic
    discovery = ToolDiscovery(loader=loader)
    
    # Add first tool
    tool1 = loader.load_from_class(MockTool)
    assert discovery._check_duplicate(tool1) is True
    
    # Try to add duplicate
    tool2 = loader.load_from_class(DuplicateTool)
    assert discovery._check_duplicate(tool2) is False
    
    # Verify only first was tracked
    assert "mock_tool" in discovery._seen_names
    assert len(discovery._seen_names) == 1


def test_discovery_empty_config():
    """Test discovery with non-existent config file."""
    discovery = ToolDiscovery()
    tools = discovery.discover_all(
        include_builtin=False,
        config_file="nonexistent.yaml"
    )
    
    # Should return empty list, not crash
    assert tools == []


def test_discovery_invalid_directory():
    """Test discovery with non-existent directory."""
    discovery = ToolDiscovery()
    tools = discovery.discover_all(
        include_builtin=False,
        custom_paths=["nonexistent_dir"]
    )
    
    # Should return empty list, not crash
    assert tools == []


@pytest.mark.asyncio
async def test_discovered_tool_execution():
    """Test that discovered tools can be executed."""
    discovery = ToolDiscovery()
    tools = discovery.discover_all(include_builtin=True)
    
    # Find echo tool
    echo_tool = next((t for t in tools if t.name == "echo"), None)
    assert echo_tool is not None
    
    # Execute it (echo tool expects 'text' parameter)
    result = await echo_tool.execute(text="test")
    assert result.success is True
    assert "test" in str(result.output)

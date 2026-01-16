"""Tests for Planner."""

import pytest

from jarvis.core.planner import Planner
from jarvis.llm.base import LLMProvider
from jarvis.tools.base import RiskLevel, Tool, ToolParameter, ToolResult
from jarvis.tools.registry import ToolRegistry


class SimpleTool(Tool):
    """Simple mock tool for testing."""

    name = "simple_tool"
    description = "A simple tool"
    risk_level = RiskLevel.LOW

    async def execute(self, **kwargs) -> ToolResult:
        """Execute."""
        return ToolResult(success=True, output="Done")

    def get_parameters(self) -> list[ToolParameter]:
        """Get parameters."""
        return []


@pytest.mark.asyncio
async def test_planner_initialization() -> None:
    """Test planner initializes correctly."""
    registry = ToolRegistry()
    llm = None  # Not needed for basic functionality
    planner = Planner(llm, registry)
    
    assert planner.tool_registry == registry


@pytest.mark.asyncio
async def test_planner_creates_plan() -> None:
    """Test planner creates a plan."""
    registry = ToolRegistry()
    registry.register(SimpleTool())
    llm = None
    planner = Planner(llm, registry)
    
    plan = await planner.plan("Do a simple task")
    
    assert "task" in plan
    assert "available_tools" in plan
    assert "tool_count" in plan
    assert plan["task"] == "Do a simple task"
    assert plan["tool_count"] == 1


@pytest.mark.asyncio
async def test_planner_estimates_complexity() -> None:
    """Test planner estimates task complexity."""
    registry = ToolRegistry()
    llm = None
    planner = Planner(llm, registry)
    
    simple_plan = await planner.plan("Do it")
    assert simple_plan["complexity"] == "simple"
    
    medium_plan = await planner.plan("Do this task with some detailed requirements and specifications here")
    assert medium_plan["complexity"] == "medium"


def test_planner_validates_tool_selection() -> None:
    """Test tool validation."""
    registry = ToolRegistry()
    registry.register(SimpleTool())
    llm = None
    planner = Planner(llm, registry)
    
    # Valid tool
    is_valid, error = planner.validate_tool_selection("simple_tool")
    assert is_valid
    assert error == ""
    
    # Invalid tool
    is_valid, error = planner.validate_tool_selection("nonexistent")
    assert not is_valid
    assert "not found" in error

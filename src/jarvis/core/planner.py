"""Planner for task decomposition and tool selection."""

import logging
from typing import Any

from jarvis.llm import LLMProvider
from jarvis.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)


class Planner:
    """
    Planner analyzes tasks and selects appropriate tools.

    In MVP: Simple tool selection based on LLM function calling.
    Future: Complex task decomposition and multi-step planning.
    """

    def __init__(self, llm_provider: LLMProvider, tool_registry: ToolRegistry):
        """
        Initialize planner.

        Args:
            llm_provider: LLM for reasoning
            tool_registry: Available tools
        """
        self.llm = llm_provider
        self.tool_registry = tool_registry
        logger.info("Planner initialized")

    async def plan(self, task: str, context: list[dict] | None = None) -> dict[str, Any]:
        """
        Create a plan for executing a task.

        Args:
            task: Task description
            context: Optional conversation context

        Returns:
            Plan with selected tools and steps
        """
        logger.debug(f"Planning for task: {task[:100]}...")

        # For MVP: Let LLM choose tools via function calling
        # Future Phase: Break down into steps

        available_tools = self.tool_registry.get_manifests()

        plan = {
            "task": task,
            "available_tools": [t["name"] for t in available_tools],
            "tool_count": len(available_tools),
            "complexity": self._estimate_complexity(task),
        }

        logger.debug(f"Plan created: {plan['tool_count']} tools available")
        return plan

    def _estimate_complexity(self, task: str) -> str:
        """
        Estimate task complexity (simple heuristic for MVP).

        Args:
            task: Task description

        Returns:
            Complexity level: 'simple', 'medium', 'complex'
        """
        words = task.split()
        if len(words) < 10:
            return "simple"
        elif len(words) < 30:
            return "medium"
        else:
            return "complex"

    def validate_tool_selection(self, tool_name: str) -> tuple[bool, str]:
        """
        Validate if tool can be used.

        Args:
            tool_name: Name of the tool

        Returns:
            Tuple of (is_valid, error_message)
        """
        if tool_name not in self.tool_registry:
            return False, f"Tool '{tool_name}' not found in registry"

        tool = self.tool_registry.get(tool_name)
        if tool.requires_confirmation:
            # TODO: Phase 4 - Human-in-the-loop confirmation
            logger.warning(
                f"Tool '{tool_name}' requires confirmation (not implemented yet)"
            )

        return True, ""

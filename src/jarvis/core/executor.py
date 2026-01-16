"""Executor for running tools and handling results."""

import logging
from typing import Any

from jarvis.tools.base import ToolResult
from jarvis.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)


class Executor:
    """
    Executor runs tools and handles their results.

    Responsibilities:
    - Execute tools with validation
    - Handle errors gracefully
    - Log execution details
    """

    def __init__(self, tool_registry: ToolRegistry):
        """
        Initialize executor.

        Args:
            tool_registry: Registry of available tools
        """
        self.tool_registry = tool_registry
        self.execution_count = 0
        logger.info("Executor initialized")

    async def execute_tool(
        self, tool_name: str, arguments: dict[str, Any]
    ) -> ToolResult:
        """
        Execute a tool with given arguments.

        Args:
            tool_name: Name of tool to execute
            arguments: Tool arguments

        Returns:
            ToolResult with execution outcome
        """
        self.execution_count += 1
        logger.info(
            f"Executing tool '{tool_name}' (execution #{self.execution_count})"
        )

        # Validate tool exists
        tool = self.tool_registry.get(tool_name)
        if not tool:
            error_msg = f"Tool '{tool_name}' not found in registry"
            logger.error(error_msg)
            return ToolResult(success=False, output=None, error=error_msg)

        # Validate parameters
        is_valid, error = self.tool_registry.validate_parameters(tool_name, **arguments)
        if not is_valid:
            logger.error(f"Parameter validation failed: {error}")
            return ToolResult(success=False, output=None, error=error)

        # Execute tool
        try:
            logger.debug(f"Tool '{tool_name}' parameters: {arguments}")
            result = await tool.execute(**arguments)

            if result.success:
                logger.info(f"Tool '{tool_name}' executed successfully")
            else:
                logger.warning(f"Tool '{tool_name}' failed: {result.error}")

            return result

        except Exception as e:
            error_msg = f"Tool execution error: {str(e)}"
            logger.exception(error_msg)
            return ToolResult(success=False, output=None, error=error_msg)

    def get_stats(self) -> dict[str, Any]:
        """
        Get executor statistics.

        Returns:
            Dict with execution stats
        """
        return {
            "total_executions": self.execution_count,
            "tools_available": len(self.tool_registry),
        }

    def reset_stats(self) -> None:
        """Reset execution statistics."""
        self.execution_count = 0
        logger.info("Executor stats reset")

"""Tool registry for discovery and management."""

import logging
from typing import Any

from jarvis.tools.base import RiskLevel, Tool

logger = logging.getLogger(__name__)


class ToolRegistry:
    """Registry for tool discovery, validation, and execution."""

    def __init__(self):
        """Initialize empty tool registry."""
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        """
        Register a tool in the registry.

        Args:
            tool: Tool instance to register

        Raises:
            ValueError: If tool name already exists
        """
        if tool.name in self._tools:
            raise ValueError(f"Tool '{tool.name}' is already registered")

        self._tools[tool.name] = tool
        logger.info(f"Registered tool: {tool.name}")

    def unregister(self, name: str) -> bool:
        """
        Unregister a tool from the registry.

        Returns:
            True if tool was removed, False if it didn't exist
        """
        if name in self._tools:
            del self._tools[name]
            logger.info(f"Unregistered tool: {name}")
            return True
        return False

    def get(self, name: str) -> Tool | None:
        """
        Get a tool by name.

        Args:
            name: Tool name

        Returns:
            Tool instance or None if not found
        """
        return self._tools.get(name)

    def get_all(self) -> list[Tool]:
        """Get all registered tools."""
        return list(self._tools.values())

    def find_by_capability(self, capability: str) -> list[Tool]:
        """
        Find tools by capability tag.

        Args:
            capability: Capability to search for

        Returns:
            List of tools with matching capability
        """
        return [tool for tool in self._tools.values() if capability in tool.capabilities]

    def find_by_risk_level(self, risk_level: RiskLevel) -> list[Tool]:
        """
        Find tools by risk level.

        Args:
            risk_level: Risk level to search for

        Returns:
            List of tools with matching risk level
        """
        return [tool for tool in self._tools.values() if tool.risk_level == risk_level]

    def get_llm_schemas(self) -> list[dict[str, Any]]:
        """
        Get all tool schemas for LLM function calling.

        Returns:
            List of tool schemas in OpenAI format
        """
        return [tool.to_llm_schema() for tool in self._tools.values()]

    def get_manifests(self) -> list[dict[str, Any]]:
        """
        Get all tool manifests for discovery/storage.

        Returns:
            List of tool manifests
        """
        return [tool.to_manifest() for tool in self._tools.values()]

    def validate_parameters(self, tool_name: str, **kwargs: Any) -> tuple[bool, str]:
        """
        Validate parameters for a tool.

        Args:
            tool_name: Name of the tool
            **kwargs: Parameters to validate

        Returns:
            Tuple of (is_valid, error_message)
        """
        tool = self.get(tool_name)
        if not tool:
            return False, f"Tool '{tool_name}' not found"

        params = tool.get_parameters()
        required_params = {p.name for p in params if p.required}
        provided_params = set(kwargs.keys())

        # Check required parameters
        missing = required_params - provided_params
        if missing:
            return False, f"Missing required parameters: {missing}"

        # Check unexpected parameters
        allowed_params = {p.name for p in params}
        unexpected = provided_params - allowed_params
        if unexpected:
            return False, f"Unexpected parameters: {unexpected}"

        return True, ""

    def __len__(self) -> int:
        """Get number of registered tools."""
        return len(self._tools)

    def __contains__(self, name: str) -> bool:
        """Check if tool is registered."""
        return name in self._tools

    def __repr__(self) -> str:
        """String representation."""
        return f"ToolRegistry({len(self._tools)} tools)"

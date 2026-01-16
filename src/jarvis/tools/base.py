"""Base Tool interface and utilities."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class RiskLevel(str, Enum):
    """Risk level for tool execution."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


@dataclass
class ToolResult:
    """Result of tool execution."""

    success: bool
    output: Any
    error: str | None = None
    tokens_used: int | None = None


@dataclass
class ToolParameter:
    """Tool parameter definition."""

    name: str
    type: str
    description: str
    required: bool = True
    default: Any = None
    enum: list[Any] | None = None


class Tool(ABC):
    """Abstract base class for all tools."""

    name: str
    description: str
    risk_level: RiskLevel = RiskLevel.LOW
    requires_confirmation: bool = False
    capabilities: list[str] = field(default_factory=list)

    def __init__(self):
        """Initialize tool."""
        if not self.name:
            raise ValueError("Tool must have a name")
        if not self.description:
            raise ValueError("Tool must have a description")

    @abstractmethod
    async def execute(self, **kwargs: Any) -> ToolResult:
        """
        Execute the tool with given parameters.

        Returns:
            ToolResult with success status and output
        """
        pass

    @abstractmethod
    def get_parameters(self) -> list[ToolParameter]:
        """
        Get list of parameters this tool accepts.

        Returns:
            List of ToolParameter objects
        """
        pass

    def to_llm_schema(self) -> dict[str, Any]:
        """
        Convert tool to OpenAI function calling schema format.

        Returns:
            Dict with function schema for LLM
        """
        params = self.get_parameters()

        properties = {}
        required = []

        for param in params:
            prop_def: dict[str, Any] = {
                "type": param.type,
                "description": param.description,
            }

            if param.enum:
                prop_def["enum"] = param.enum

            if param.default is not None:
                prop_def["default"] = param.default

            properties[param.name] = prop_def

            if param.required:
                required.append(param.name)

        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                },
            },
        }

    def to_manifest(self) -> dict[str, Any]:
        """
        Convert tool to manifest format for storage/discovery.

        Returns:
            Dict with complete tool metadata
        """
        return {
            "name": self.name,
            "description": self.description,
            "risk_level": self.risk_level.value,
            "requires_confirmation": self.requires_confirmation,
            "capabilities": self.capabilities,
            "parameters": [
                {
                    "name": p.name,
                    "type": p.type,
                    "description": p.description,
                    "required": p.required,
                    "default": p.default,
                    "enum": p.enum,
                }
                for p in self.get_parameters()
            ],
        }

"""Tool discovery orchestration.

This module coordinates multiple discovery sources (builtin, config, directories)
and produces validated tool instances for registration.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from pathlib import Path

from jarvis.tools.base import Tool
from jarvis.tools.loader import ToolLoader

logger = logging.getLogger(__name__)


class ToolDiscovery:
    """Combine multiple discovery strategies to yield tool instances.

    Discovery order: builtin → config → directories.
    Deduplication by tool name; first occurrence wins with warning for conflicts.
    """

    def __init__(self, loader: ToolLoader | None = None):
        """Initialize discovery with optional custom loader."""
        self.loader = loader or ToolLoader()
        self._seen_names: set[str] = set()

    def discover_all(
        self,
        include_builtin: bool = True,
        config_file: str | None = None,
        custom_paths: Iterable[str] | None = None,
    ) -> list[Tool]:
        """Discover tools from all configured sources.

        Args:
            include_builtin: Load builtin tools from jarvis.tools.builtin.
            config_file: Path to YAML config with tool specs.
            custom_paths: Directories to scan for custom tool modules.

        Returns:
            List of validated Tool instances; duplicates removed.
        """
        tools: list[Tool] = []
        self._seen_names.clear()

        # 1. Builtin tools
        if include_builtin:
            builtin_tools = self._discover_builtin()
            tools.extend(builtin_tools)
            logger.info(f"Discovered {len(builtin_tools)} builtin tools")

        # 2. Config-driven tools
        if config_file:
            config_tools = self._discover_from_config(config_file)
            tools.extend(config_tools)
            logger.info(f"Discovered {len(config_tools)} tools from config")

        # 3. Custom directories
        if custom_paths:
            for path in custom_paths:
                dir_tools = self._discover_from_directory(path)
                tools.extend(dir_tools)
                logger.info(f"Discovered {len(dir_tools)} tools from {path}")

        logger.info(f"Total tools discovered: {len(tools)}")
        return tools

    def _discover_builtin(self) -> list[Tool]:
        """Discover builtin tools from jarvis.tools.builtin."""
        tools: list[Tool] = []

        try:
            # Import builtin module to get all registered tools
            from jarvis.tools.builtin import (
                EchoTool,
                FileReadTool,
                FileWriteTool,
                ListDirectoryTool,
                ShellExecuteTool,
                WebFetchTool,
                WebSearchTool,
            )

            builtin_classes = [
                EchoTool,
                FileReadTool,
                FileWriteTool,
                ListDirectoryTool,
                ShellExecuteTool,
                WebFetchTool,
                WebSearchTool,
            ]

            for tool_class in builtin_classes:
                tool = self.loader.load_from_class(tool_class)
                if tool and self._check_duplicate(tool):
                    tools.append(tool)

        except Exception as e:
            logger.error(f"Failed to discover builtin tools: {e}")

        return tools

    def _discover_from_config(self, config_file: str) -> list[Tool]:
        """Discover tools from YAML config file.

        Expected format:
        tools:
          - name: custom_tool
            module: my_tools.custom
            class: CustomTool
            enabled: true
        """
        tools: list[Tool] = []

        try:
            import yaml

            config_path = Path(config_file)
            if not config_path.exists():
                logger.warning(f"Config file not found: {config_file}")
                return tools

            with open(config_path) as f:
                config = yaml.safe_load(f)

            if not config or "tools" not in config:
                logger.warning(f"No tools section in config: {config_file}")
                return tools

            for spec in config["tools"]:
                if not spec.get("enabled", True):
                    logger.debug(f"Skipping disabled tool: {spec.get('name')}")
                    continue

                tool = self.loader.load_from_spec(spec)
                if tool and self._check_duplicate(tool):
                    tools.append(tool)

        except ImportError:
            logger.warning("PyYAML not installed; config discovery disabled")
        except Exception as e:
            logger.error(f"Failed to load config {config_file}: {e}")

        return tools

    def _discover_from_directory(self, directory: str) -> list[Tool]:
        """Discover tools by scanning Python modules in directory.

        Looks for Tool subclasses in .py files.
        """
        tools: list[Tool] = []

        try:
            dir_path = Path(directory)
            if not dir_path.exists() or not dir_path.is_dir():
                logger.warning(f"Directory not found or not a dir: {directory}")
                return tools

            # Scan for .py files
            for py_file in dir_path.glob("*.py"):
                if py_file.name.startswith("_"):
                    continue

                module_tools = self.loader.load_from_module_file(str(py_file))
                for tool in module_tools:
                    if self._check_duplicate(tool):
                        tools.append(tool)

        except Exception as e:
            logger.error(f"Failed to scan directory {directory}: {e}")

        return tools

    def _check_duplicate(self, tool: Tool) -> bool:
        """Check for duplicate tool names; log warning if found.

        Returns:
            True if tool is unique and should be added, False if duplicate.
        """
        if tool.name in self._seen_names:
            logger.warning(
                f"Duplicate tool name '{tool.name}' found; skipping. " "First registration wins."
            )
            return False

        self._seen_names.add(tool.name)
        return True

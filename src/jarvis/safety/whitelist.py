"""Whitelist management for allowed commands and paths."""

from __future__ import annotations

import fnmatch
import json
from pathlib import Path
from typing import Any


class WhitelistManager:
    """Manage whitelists for commands and file paths."""

    def __init__(self):
        """Initialize whitelist manager."""
        self.command_patterns: list[str] = []
        self.path_patterns: list[str] = []
        self.forbidden_patterns: list[str] = [
            "*rm -rf*",
            "*rm -r/*",
            "*etc/shadow*",
            "*../..* ",
        ]

    def add_command_pattern(self, pattern: str) -> None:
        """
        Add a command pattern to whitelist.

        Supports glob patterns: echo, pytest, python *.py, etc.

        Args:
            pattern: Command pattern (can use wildcards)
        """
        if pattern and pattern not in self.command_patterns:
            self.command_patterns.append(pattern)

    def add_path_pattern(self, pattern: str) -> None:
        """
        Add a file path pattern to whitelist.

        Supports glob patterns: src/**, tests/**, ./temp/*, etc.

        Args:
            pattern: Path pattern (can use wildcards)
        """
        if pattern and pattern not in self.path_patterns:
            self.path_patterns.append(pattern)

    def add_forbidden_pattern(self, pattern: str) -> None:
        """
        Add a pattern to forbidden list.

        Args:
            pattern: Pattern to block
        """
        if pattern and pattern not in self.forbidden_patterns:
            self.forbidden_patterns.append(pattern)

    def is_command_allowed(self, command: str) -> bool:
        """
        Check if a command is allowed.

        Args:
            command: Command string

        Returns:
            True if allowed, False otherwise
        """
        # Check if it matches any forbidden pattern first
        for forbidden in self.forbidden_patterns:
            if fnmatch.fnmatch(command.lower(), forbidden.lower()):
                return False

        # If no whitelist patterns, allow everything (except forbidden)
        if not self.command_patterns:
            return True

        # Check if matches any allowed pattern
        for pattern in self.command_patterns:
            if fnmatch.fnmatch(command.lower(), pattern.lower()):
                return True

        return False

    def is_path_allowed(self, path: str | Path) -> bool:
        """
        Check if a file path is allowed.

        Args:
            path: File path (string or Path)

        Returns:
            True if allowed, False otherwise
        """
        path_str = str(path).lower()

        # Check forbidden patterns first (highest priority)
        for forbidden in self.forbidden_patterns:
            if fnmatch.fnmatch(path_str, forbidden.lower()):
                return False

        # If no whitelist patterns, allow everything (except forbidden, which we checked)
        if not self.path_patterns:
            return True

        # Check if matches any allowed pattern
        return any(fnmatch.fnmatch(path_str, pattern.lower()) for pattern in self.path_patterns)

    def save_config(self, filepath: str | Path) -> None:
        """
        Save whitelist configuration to JSON file.

        Args:
            filepath: Path to save configuration
        """
        config = {
            "command_patterns": self.command_patterns,
            "path_patterns": self.path_patterns,
            "forbidden_patterns": self.forbidden_patterns,
        }
        Path(filepath).write_text(json.dumps(config, indent=2))

    def load_config(self, filepath: str | Path) -> None:
        """
        Load whitelist configuration from JSON file.

        Args:
            filepath: Path to load configuration from
        """
        config = json.loads(Path(filepath).read_text())
        self.command_patterns = config.get("command_patterns", [])
        self.path_patterns = config.get("path_patterns", [])
        self.forbidden_patterns = config.get("forbidden_patterns", [])

    def get_summary(self) -> dict[str, Any]:
        """Get summary of whitelist configuration."""
        return {
            "command_patterns": len(self.command_patterns),
            "path_patterns": len(self.path_patterns),
            "forbidden_patterns": len(self.forbidden_patterns),
            "commands": self.command_patterns,
            "paths": self.path_patterns,
            "forbidden": self.forbidden_patterns,
        }

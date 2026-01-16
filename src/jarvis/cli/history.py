"""Command history management."""

import json
from datetime import datetime
from pathlib import Path
from typing import Any


class CommandHistory:
    """Manages command history storage and retrieval."""

    def __init__(self, history_file: str | None = None):
        """Initialize history manager.

        Args:
            history_file: Path to history file (defaults to ~/.jarvis/history.json)
        """
        if history_file is None:
            home = Path.home()
            history_file = str(home / ".jarvis" / "history.json")

        self.history_file = Path(history_file)
        self.history_file.parent.mkdir(parents=True, exist_ok=True)
        self.commands: list[dict[str, Any]] = self._load_history()

    def _load_history(self) -> list[dict[str, Any]]:
        """Load history from file."""
        if not self.history_file.exists():
            return []

        try:
            with open(self.history_file, encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return []

    def _save_history(self) -> None:
        """Save history to file."""
        with open(self.history_file, "w", encoding="utf-8") as f:
            json.dump(self.commands, f, indent=2, ensure_ascii=False)

    def add_command(
        self,
        command: str,
        status: str = "success",
        result: str = "",
        error: str = "",
    ) -> None:
        """Add command to history.

        Args:
            command: The command text
            status: "success", "error", or "cancelled"
            result: Command result
            error: Error message if any
        """
        entry = {
            "timestamp": datetime.now().isoformat(),
            "command": command,
            "status": status,
            "result": result,
            "error": error,
        }
        self.commands.append(entry)
        self._save_history()

    def get_recent(self, limit: int = 10) -> list[dict[str, Any]]:
        """Get recent commands."""
        return self.commands[-limit:]

    def get_by_status(self, status: str) -> list[dict[str, Any]]:
        """Get commands by status."""
        return [c for c in self.commands if c["status"] == status]

    def get_successful_commands(self) -> list[dict[str, Any]]:
        """Get all successful commands."""
        return self.get_by_status("success")

    def get_failed_commands(self) -> list[dict[str, Any]]:
        """Get all failed commands."""
        return self.get_by_status("error")

    def search(self, query: str) -> list[dict[str, Any]]:
        """Search history by command text."""
        query_lower = query.lower()
        return [c for c in self.commands if query_lower in c["command"].lower()]

    def get_summary(self) -> dict[str, Any]:
        """Get history summary statistics."""
        total = len(self.commands)
        successful = len(self.get_successful_commands())
        failed = len(self.get_failed_commands())

        return {
            "total_commands": total,
            "successful": successful,
            "failed": failed,
            "success_rate": ((successful / total * 100) if total > 0 else 0),
        }

    def clear_history(self) -> None:
        """Clear all history."""
        self.commands.clear()
        self._save_history()

    def export_to_json(self, filepath: str) -> None:
        """Export history to JSON file."""
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(self.commands, f, indent=2, ensure_ascii=False)

    def get_all(self) -> list[dict[str, Any]]:
        """Get all commands."""
        return self.commands.copy()

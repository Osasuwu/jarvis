"""Interactive CLI interface for Jarvis."""

import asyncio
from typing import Any, Callable

from .formatter import OutputFormatter
from .history import CommandHistory


class CLIInterface:
    """Interactive command-line interface for Jarvis agent."""

    def __init__(self, formatter: OutputFormatter | None = None):
        """Initialize CLI interface.

        Args:
            formatter: OutputFormatter instance (creates new if None)
        """
        self.formatter = formatter or OutputFormatter()
        self.history = CommandHistory()
        self.running = False
        self.commands: dict[str, Callable] = {}
        self._setup_default_commands()

    def _setup_default_commands(self) -> None:
        """Setup built-in commands."""
        self.register_command("help", self._cmd_help, "Show help message")
        self.register_command("history", self._cmd_history, "Show command history")
        self.register_command("clear", self._cmd_clear, "Clear screen")
        self.register_command("exit", self._cmd_exit, "Exit the application")
        self.register_command("stats", self._cmd_stats, "Show statistics")

    def register_command(
        self, name: str, handler: Callable, help_text: str = ""
    ) -> None:
        """Register a command handler.

        Args:
            name: Command name
            handler: Callable to execute
            help_text: Help description
        """
        self.commands[name] = {"handler": handler, "help": help_text}

    async def run_command(self, command: str) -> Any:
        """Execute a command.

        Args:
            command: Command string

        Returns:
            Command result
        """
        parts = command.strip().split(maxsplit=1)
        if not parts:
            return None

        cmd_name = parts[0].lower()
        cmd_args = parts[1] if len(parts) > 1 else ""

        if cmd_name not in self.commands:
            self.formatter.print_error(f"Unknown command: {cmd_name}")
            return None

        try:
            handler = self.commands[cmd_name]["handler"]

            # Check if handler is async
            if asyncio.iscoroutinefunction(handler):
                result = await handler(cmd_args)
            else:
                result = handler(cmd_args)

            # Log successful command
            self.history.add_command(
                command=command, status="success", result=str(result or "")
            )
            return result

        except KeyboardInterrupt:
            self.formatter.print_warning("Command cancelled")
            self.history.add_command(command=command, status="cancelled")
            return None
        except Exception as e:
            self.formatter.print_error(f"Command failed: {e}")
            self.history.add_command(
                command=command, status="error", error=str(e)
            )
            return None

    def _cmd_help(self, args: str) -> None:
        """Show help message."""
        self.formatter.print_section("Available Commands")

        help_items = []
        for name, info in self.commands.items():
            help_text = info.get("help", "No description")
            help_items.append(f"{name:15} - {help_text}")

        for item in sorted(help_items):
            self.formatter.console.print(f"  {item}")

    def _cmd_history(self, args: str) -> None:
        """Show command history."""
        if args == "clear":
            if self.formatter.confirm("Clear all history?", default=False):
                self.history.clear_history()
                self.formatter.print_success("History cleared")
            return

        if args == "export":
            filepath = self.formatter.input_prompt(
                "Export to file", "history.json"
            )
            self.history.export_to_json(filepath)
            self.formatter.print_success(f"History exported to {filepath}")
            return

        recent = self.history.get_recent(limit=10)
        if not recent:
            self.formatter.print_info("No history")
            return

        self.formatter.print_section("Recent Commands")
        for i, cmd in enumerate(recent, 1):
            status_symbol = (
                "✓" if cmd["status"] == "success" else "✗"
            )
            self.formatter.console.print(
                f"  [{i}] {status_symbol} {cmd['command']}"
            )

    def _cmd_clear(self, args: str) -> None:
        """Clear screen."""
        self.formatter.clear_screen()

    def _cmd_exit(self, args: str) -> None:
        """Exit application."""
        self.formatter.print_info("Goodbye!")
        self.running = False

    def _cmd_stats(self, args: str) -> None:
        """Show statistics."""
        summary = self.history.get_summary()

        self.formatter.print_section("Statistics")
        self.formatter.print_dict(
            {
                "Total Commands": summary["total_commands"],
                "Successful": summary["successful"],
                "Failed": summary["failed"],
                "Success Rate": f"{summary['success_rate']:.1f}%",
            }
        )

    async def start_interactive_mode(self) -> None:
        """Start interactive command loop."""
        self.running = True
        self.formatter.print_header(
            "Jarvis - Personal AI Agent",
            "Type 'help' for available commands",
        )

        while self.running:
            try:
                command = self.formatter.input_prompt("jarvis")
                if command:
                    await self.run_command(command)
            except KeyboardInterrupt:
                self.formatter.print_warning("Interrupted")
                self.running = False
            except EOFError:
                self.formatter.print_info("EOF received")
                self.running = False

    def get_commands(self) -> dict[str, str]:
        """Get all registered commands with help text."""
        return {
            name: info["help"] for name, info in self.commands.items()
        }

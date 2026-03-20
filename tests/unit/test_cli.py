"""Unit tests for CLI module."""

import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from jarvis.cli import CLIInterface, CommandHistory, OutputFormatter


class TestOutputFormatter(unittest.TestCase):
    """Tests for OutputFormatter."""

    def setUp(self):
        """Set up test fixtures."""
        self.formatter = OutputFormatter()

    def test_initialization(self):
        """Test formatter initialization."""
        self.assertIsNotNone(self.formatter.console)

    def test_print_success(self):
        """Test success message formatting."""
        # Just test it doesn't raise
        self.formatter.print_success("Test message")

    def test_print_error(self):
        """Test error message formatting."""
        self.formatter.print_error("Error message")

    def test_print_warning(self):
        """Test warning message formatting."""
        self.formatter.print_warning("Warning message")

    def test_print_info(self):
        """Test info message formatting."""
        self.formatter.print_info("Info message")

    def test_print_code(self):
        """Test code formatting."""
        code = 'print("hello")'
        self.formatter.print_code(code, language="python")

    def test_print_json(self):
        """Test JSON formatting."""
        data = {"key": "value", "number": 42}
        self.formatter.print_json(data)

    def test_print_table(self):
        """Test table formatting."""
        data = [
            {"name": "Alice", "age": 30},
            {"name": "Bob", "age": 25},
        ]
        self.formatter.print_table(data, title="Users")

    def test_print_list(self):
        """Test list formatting."""
        items = ["Item 1", "Item 2", "Item 3"]
        self.formatter.print_list(items, title="Items")

    def test_print_dict(self):
        """Test dictionary formatting."""
        data = {"key1": "value1", "key2": 42}
        self.formatter.print_dict(data, title="Dict")

    def test_input_prompt(self):
        """Test input prompt."""
        with patch("builtins.input", return_value="test input"):
            # Mock console input
            self.formatter.console.input = MagicMock(return_value="test input")
            result = self.formatter.input_prompt("Enter value")
            self.assertIsNotNone(result)

    def test_confirm_default_yes(self):
        """Test confirmation with default yes."""
        self.formatter.console.input = MagicMock(return_value="")
        result = self.formatter.confirm("Confirm?", default=True)
        self.assertTrue(result)

    def test_confirm_default_no(self):
        """Test confirmation with default no."""
        self.formatter.console.input = MagicMock(return_value="")
        result = self.formatter.confirm("Confirm?", default=False)
        self.assertFalse(result)

    def test_confirm_yes_response(self):
        """Test confirmation with yes response."""
        self.formatter.console.input = MagicMock(return_value="y")
        result = self.formatter.confirm("Confirm?")
        self.assertTrue(result)

    def test_confirm_no_response(self):
        """Test confirmation with no response."""
        self.formatter.console.input = MagicMock(return_value="n")
        result = self.formatter.confirm("Confirm?", default=True)
        self.assertFalse(result)


class TestCommandHistory(unittest.TestCase):
    """Tests for CommandHistory."""

    def setUp(self):
        """Set up test fixtures."""
        self.tmpdir = tempfile.TemporaryDirectory()
        self.history_file = Path(self.tmpdir.name) / "history.json"
        self.history = CommandHistory(str(self.history_file))

    def tearDown(self):
        """Clean up test fixtures."""
        self.tmpdir.cleanup()

    def test_initialization(self):
        """Test history initialization."""
        with tempfile.TemporaryDirectory() as tmpdir:
            history_file = Path(tmpdir) / "history.json"
            history = CommandHistory(str(history_file))
            self.assertEqual(len(history.commands), 0)

    def test_add_command(self):
        """Test adding command to history."""
        self.history.add_command("test command", status="success")
        self.assertEqual(len(self.history.commands), 1)
        self.assertEqual(self.history.commands[0]["command"], "test command")

    def test_add_multiple_commands(self):
        """Test adding multiple commands."""
        self.history.add_command("cmd1", status="success")
        self.history.add_command("cmd2", status="error", error="Failed")
        self.assertEqual(len(self.history.commands), 2)

    def test_get_recent(self):
        """Test getting recent commands."""
        for i in range(5):
            self.history.add_command(f"cmd {i}", status="success")

        recent = self.history.get_recent(limit=3)
        self.assertEqual(len(recent), 3)

    def test_get_by_status(self):
        """Test filtering by status."""
        self.history.add_command("success1", status="success")
        self.history.add_command("success2", status="success")
        self.history.add_command("error1", status="error")

        success_cmds = self.history.get_by_status("success")
        error_cmds = self.history.get_by_status("error")

        self.assertEqual(len(success_cmds), 2)
        self.assertEqual(len(error_cmds), 1)

    def test_get_successful_commands(self):
        """Test getting successful commands."""
        self.history.add_command("ok", status="success")
        self.history.add_command("fail", status="error")

        successful = self.history.get_successful_commands()
        self.assertEqual(len(successful), 1)

    def test_get_failed_commands(self):
        """Test getting failed commands."""
        self.history.add_command("ok", status="success")
        self.history.add_command("fail", status="error")

        failed = self.history.get_failed_commands()
        self.assertEqual(len(failed), 1)

    def test_search(self):
        """Test searching history."""
        self.history.add_command("list files", status="success")
        self.history.add_command("read config", status="success")
        self.history.add_command("delete item", status="error")

        results = self.history.search("config")
        self.assertEqual(len(results), 1)
        self.assertIn("config", results[0]["command"])

    def test_get_summary(self):
        """Test getting summary statistics."""
        for i in range(8):
            self.history.add_command(f"cmd {i}", status="success")
        for i in range(2):
            self.history.add_command(f"fail {i}", status="error")

        summary = self.history.get_summary()
        self.assertEqual(summary["total_commands"], 10)
        self.assertEqual(summary["successful"], 8)
        self.assertEqual(summary["failed"], 2)
        self.assertEqual(summary["success_rate"], 80.0)

    def test_export_to_json(self):
        """Test exporting history to JSON."""
        self.history.add_command("cmd1", status="success")
        self.history.add_command("cmd2", status="error", error="Failed")

        with tempfile.TemporaryDirectory() as tmpdir:
            export_file = Path(tmpdir) / "export.json"
            self.history.export_to_json(str(export_file))

            with open(export_file) as f:
                data = json.load(f)

            self.assertEqual(len(data), 2)


class TestCLIInterface(unittest.TestCase):
    """Tests for CLIInterface."""

    def setUp(self):
        """Set up test fixtures."""
        self.cli = CLIInterface()

    def test_initialization(self):
        """Test CLI initialization."""
        self.assertIsNotNone(self.cli.formatter)
        self.assertIsNotNone(self.cli.history)
        self.assertFalse(self.cli.running)

    def test_default_commands_registered(self):
        """Test default commands are registered."""
        commands = self.cli.get_commands()
        self.assertIn("help", commands)
        self.assertIn("history", commands)
        self.assertIn("clear", commands)
        self.assertIn("exit", commands)
        self.assertIn("stats", commands)

    def test_register_custom_command(self):
        """Test registering custom command."""

        def custom_handler(args):
            return f"Custom: {args}"

        self.cli.register_command("custom", custom_handler, "Custom command")
        commands = self.cli.get_commands()
        self.assertIn("custom", commands)

    async def test_run_custom_command(self):
        """Test running custom command."""

        def handler(args):
            return f"Result: {args}"

        self.cli.register_command("test", handler, "Test command")
        result = await self.cli.run_command("test arg1")

        self.assertIsNotNone(result)
        self.assertIn("Result", str(result))

    def test_run_unknown_command(self):
        """Test running unknown command."""

        async def run():
            return await self.cli.run_command("unknown_cmd")

        result = asyncio.run(run())
        self.assertIsNone(result)

    async def test_run_help_command(self):
        """Test help command."""
        await self.cli.run_command("help")
        # Help command returns None

    async def test_run_exit_command(self):
        """Test exit command."""
        self.cli.running = True
        await self.cli.run_command("exit")
        self.assertFalse(self.cli.running)

    def test_get_commands(self):
        """Test getting all commands."""
        commands = self.cli.get_commands()
        self.assertIsInstance(commands, dict)
        self.assertGreater(len(commands), 0)


class TestIntegration(unittest.TestCase):
    """Integration tests for CLI."""

    def test_full_cli_workflow(self):
        """Test complete CLI workflow."""
        with tempfile.TemporaryDirectory() as tmpdir:
            history_file = Path(tmpdir) / "history.json"

            # Create CLI
            formatter = OutputFormatter()
            cli = CLIInterface(formatter)
            cli.history.history_file = history_file

            # Register custom command
            def echo_handler(args):
                return f"Echo: {args}"

            cli.register_command("echo", echo_handler, "Echo text")

            # Run commands
            async def run_workflow():
                await cli.run_command("echo hello")
                await cli.run_command("stats")
                await cli.run_command("exit")

            asyncio.run(run_workflow())

            # Verify history
            self.assertGreater(len(cli.history.commands), 0)


if __name__ == "__main__":
    unittest.main()

"""Tests for safety and human-in-the-loop system."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import pytest
from jarvis.safety.auditor import AuditEntry, AuditLogger
from jarvis.safety.confirmation import ConfirmationPrompt
from jarvis.safety.executor import SafeExecutor
from jarvis.safety.whitelist import WhitelistManager
from jarvis.tools.base import RiskLevel, Tool, ToolParameter, ToolResult


# Mock tool for testing
class MockHighRiskTool(Tool):
    """Mock tool with HIGH risk."""

    name = "mock_high_risk"
    description = "Mock high risk tool"
    risk_level = RiskLevel.HIGH
    capabilities = ["test"]

    async def execute(self, **kwargs) -> ToolResult:
        return ToolResult(success=True, output="Executed")

    def get_parameters(self):
        return [ToolParameter(name="action", type="string", required=True)]


class MockLowRiskTool(Tool):
    """Mock tool with LOW risk."""

    name = "mock_low_risk"
    description = "Mock low risk tool"
    risk_level = RiskLevel.LOW
    capabilities = ["test"]

    async def execute(self, **kwargs) -> ToolResult:
        return ToolResult(success=True, output="Executed")

    def get_parameters(self):
        return [ToolParameter(name="query", type="string", required=True)]


# ===== Confirmation Tests =====


@pytest.mark.asyncio
async def test_confirmation_request_denied() -> None:
    """Test confirmation request denied."""
    confirmation = ConfirmationPrompt()

    # Mock input to return 'no'
    import unittest.mock as mock

    with mock.patch("builtins.input", return_value="no"):
        result = await confirmation.request_confirmation(
            operation="Test",
            tool_name="test_tool",
            parameters={"action": "test"},
        )
        assert result is False


@pytest.mark.asyncio
async def test_confirmation_request_approved() -> None:
    """Test confirmation request approved."""
    confirmation = ConfirmationPrompt()

    with patch("builtins.input", return_value="yes"):
        result = await confirmation.request_confirmation(
            operation="Test",
            tool_name="test_tool",
            parameters={"action": "test"},
        )
        assert result is True


@pytest.mark.asyncio
async def test_confirmation_keyboard_interrupt() -> None:
    """Test confirmation handles keyboard interrupt."""
    confirmation = ConfirmationPrompt()

    with patch("builtins.input", side_effect=KeyboardInterrupt):
        result = await confirmation.request_confirmation_with_retry(
            operation="Test",
            tool_name="test_tool",
            parameters={"action": "test"},
        )
        assert result is False


# ===== Whitelist Tests =====


def test_whitelist_allow_command() -> None:
    """Test command whitelist allow."""
    wl = WhitelistManager()
    wl.add_command_pattern("echo *")
    wl.add_command_pattern("pytest *")

    assert wl.is_command_allowed("echo hello")
    assert wl.is_command_allowed("pytest tests/")
    assert not wl.is_command_allowed("rm -rf /")


def test_whitelist_no_patterns_allow_all() -> None:
    """Test that no patterns allow all (except forbidden)."""
    wl = WhitelistManager()

    assert wl.is_command_allowed("echo hello")
    assert wl.is_command_allowed("python script.py")


def test_whitelist_forbidden_patterns() -> None:
    """Test forbidden pattern blocking."""
    wl = WhitelistManager()

    assert not wl.is_command_allowed("rm -rf *")
    assert not wl.is_command_allowed("rm -r/test")


def test_whitelist_path_allowed() -> None:
    """Test path whitelist."""
    wl = WhitelistManager()
    wl.add_path_pattern("src/**")
    wl.add_path_pattern("tests/**")

    assert wl.is_path_allowed("src/main.py")
    assert wl.is_path_allowed("tests/test_main.py")
    assert not wl.is_path_allowed("etc/passwd")


def test_whitelist_forbidden_paths() -> None:
    """Test forbidden path blocking."""
    wl = WhitelistManager()
    # Add some allowed patterns to test forbidden override
    wl.add_path_pattern("**/*")

    assert not wl.is_path_allowed("etc/shadow")
    assert not wl.is_path_allowed("/etc/shadow")


def test_whitelist_save_load() -> None:
    """Test whitelist save/load."""
    with TemporaryDirectory() as tmpdir:
        filepath = Path(tmpdir) / "whitelist.json"

        # Save
        wl1 = WhitelistManager()
        wl1.add_command_pattern("echo *")
        wl1.add_path_pattern("src/**")
        wl1.save_config(filepath)

        # Load
        wl2 = WhitelistManager()
        wl2.load_config(filepath)

        assert wl2.is_command_allowed("echo hello")
        assert wl2.is_path_allowed("src/main.py")


# ===== Audit Logger Tests =====


def test_audit_entry_to_dict() -> None:
    """Test audit entry serialization."""
    entry = AuditEntry(
        timestamp="2026-01-16T00:00:00",
        tool_name="test_tool",
        operation="Test operation",
        parameters={"action": "test"},
        risk_level="HIGH",
        user_approved=True,
        result_status="success",
    )

    data = entry.to_dict()
    assert data["tool_name"] == "test_tool"
    assert data["risk_level"] == "HIGH"
    assert data["user_approved"] is True


def test_audit_logger_log_operation() -> None:
    """Test audit logger logging."""
    auditor = AuditLogger()

    entry = auditor.log_operation(
        tool_name="shell_execute",
        operation="Execute command",
        parameters={"command": "echo hello"},
        risk_level="HIGH",
        user_approved=True,
        result_status="success",
    )

    assert entry.tool_name == "shell_execute"
    assert len(auditor.entries) == 1
    assert auditor.entries[0].tool_name == "shell_execute"


def test_audit_logger_filter_by_risk() -> None:
    """Test filtering audit entries by risk level."""
    auditor = AuditLogger()

    auditor.log_operation(
        tool_name="file_read",
        operation="Read",
        parameters={},
        risk_level="LOW",
        result_status="success",
    )
    auditor.log_operation(
        tool_name="shell_execute",
        operation="Execute",
        parameters={},
        risk_level="HIGH",
        result_status="success",
    )

    low = auditor.get_entries_by_risk("LOW")
    high = auditor.get_entries_by_risk("HIGH")

    assert len(low) == 1
    assert len(high) == 1


def test_audit_logger_summary() -> None:
    """Test audit logger summary."""
    auditor = AuditLogger()

    auditor.log_operation(
        tool_name="file_read",
        operation="Read",
        parameters={},
        risk_level="LOW",
        result_status="success",
    )
    auditor.log_operation(
        tool_name="shell_execute",
        operation="Execute",
        parameters={},
        risk_level="HIGH",
        result_status="denied",
    )

    summary = auditor.get_summary()
    assert summary["total_operations"] == 2
    assert summary["denied_count"] == 1
    assert summary["by_risk_level"]["LOW"] == 1


def test_audit_logger_export_json() -> None:
    """Test audit logger JSON export."""
    with TemporaryDirectory() as tmpdir:
        filepath = Path(tmpdir) / "audit.json"
        auditor = AuditLogger()

        auditor.log_operation(
            tool_name="test",
            operation="Test",
            parameters={},
            risk_level="LOW",
            result_status="success",
        )

        auditor.export_to_json(filepath)

        data = json.loads(filepath.read_text())
        assert len(data) == 1
        assert data[0]["tool_name"] == "test"


# ===== Safe Executor Tests =====


@pytest.mark.asyncio
async def test_safe_executor_low_risk_no_confirmation() -> None:
    """Test that LOW risk tools don't need confirmation."""
    executor = SafeExecutor()
    tool = MockLowRiskTool()

    result = await executor.execute(tool, query="test")

    assert result.success
    assert result.output == "Executed"


@pytest.mark.asyncio
async def test_safe_executor_high_risk_with_auditing() -> None:
    """Test that HIGH risk tools are audited."""
    auditor = AuditLogger()
    executor = SafeExecutor(auditor=auditor)
    tool = MockHighRiskTool()

    with patch("builtins.input", return_value="yes"):
        await executor.execute(tool, action="test")

    assert len(auditor.entries) == 1
    assert auditor.entries[0].risk_level == "HIGH"
    assert auditor.entries[0].user_approved is True


@pytest.mark.asyncio
async def test_safe_executor_whitelist_rejection() -> None:
    """Test executor rejects non-whitelisted operations."""
    whitelist = WhitelistManager()
    whitelist.add_command_pattern("echo *")

    executor = SafeExecutor(whitelist=whitelist)

    # Create mock tool for shell_execute
    class MockShellTool(Tool):
        name = "shell_execute"
        description = "Shell execute"
        risk_level = RiskLevel.HIGH

        async def execute(self, **kwargs):
            return ToolResult(success=True, output="")

        def get_parameters(self):
            return []

    tool = MockShellTool()

    with pytest.raises(ValueError, match="not whitelisted"):
        await executor.execute(tool, command="rm -rf /")


@pytest.mark.asyncio
async def test_safe_executor_with_confirmation() -> None:
    """Test executor with confirmation."""
    confirmation = ConfirmationPrompt()
    auditor = AuditLogger()
    executor = SafeExecutor(confirmation=confirmation, auditor=auditor)
    tool = MockHighRiskTool()

    with patch("builtins.input", return_value="yes"):
        result = await executor.execute(tool, action="test")

    assert result.success
    assert auditor.entries[0].result_status == "success"
    assert auditor.entries[0].user_approved is True

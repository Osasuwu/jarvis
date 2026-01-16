"""Tests for Blocker 2: Safety Layer Integration."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from jarvis.core.executor import Executor
from jarvis.safety.auditor import AuditLogger
from jarvis.safety.confirmation import ConfirmationPrompt
from jarvis.safety.whitelist import WhitelistManager
from jarvis.tools.base import RiskLevel, Tool, ToolParameter, ToolResult
from jarvis.tools.registry import ToolRegistry


class HighRiskTool(Tool):
    """Mock high-risk tool for testing."""

    name = "dangerous_operation"
    description = "A dangerous operation requiring approval"
    risk_level = RiskLevel.HIGH
    capabilities = ["admin"]

    async def execute(self, action: str = "default") -> ToolResult:
        """Execute the dangerous operation."""
        return ToolResult(success=True, output=f"Executed: {action}")

    def get_parameters(self) -> list[ToolParameter]:
        """Get parameters."""
        return [
            ToolParameter(
                name="action",
                type="string",
                description="Action to perform",
                required=True,
            )
        ]


class LowRiskTool(Tool):
    """Mock low-risk tool for testing."""

    name = "safe_operation"
    description = "A safe operation"
    risk_level = RiskLevel.LOW
    capabilities = ["read"]

    async def execute(self, query: str = "") -> ToolResult:
        """Execute the safe operation."""
        return ToolResult(success=True, output=f"Result: {query}")

    def get_parameters(self) -> list[ToolParameter]:
        """Get parameters."""
        return [
            ToolParameter(
                name="query",
                type="string",
                description="Query",
                required=False,
            )
        ]


@pytest.mark.asyncio
async def test_executor_with_safety_layer():
    """Test that executor initializes with safety layer."""
    registry = ToolRegistry()
    registry.register(LowRiskTool())
    registry.register(HighRiskTool())

    confirmation = ConfirmationPrompt()
    whitelist = WhitelistManager()
    auditor = AuditLogger()

    executor = Executor(
        registry,
        confirmation=confirmation,
        whitelist=whitelist,
        auditor=auditor,
        require_confirmation_for=["HIGH"],
    )

    assert executor.safe_executor is not None
    assert executor.safe_executor.confirmation == confirmation
    assert executor.safe_executor.auditor == auditor


@pytest.mark.asyncio
async def test_low_risk_tool_executes_without_confirmation():
    """Test that low-risk tools execute without requiring confirmation."""
    registry = ToolRegistry()
    registry.register(LowRiskTool())

    confirmation = AsyncMock()
    whitelist = WhitelistManager()
    auditor = AuditLogger()

    executor = Executor(
        registry,
        confirmation=confirmation,
        whitelist=whitelist,
        auditor=auditor,
        require_confirmation_for=["HIGH"],
    )

    result = await executor.execute_tool("safe_operation", {"query": "test"})

    assert result.success
    # Confirmation should NOT be requested for LOW risk
    confirmation.request_confirmation_with_retry.assert_not_called()


@pytest.mark.asyncio
async def test_high_risk_tool_requires_confirmation():
    """Test that high-risk tools require user confirmation."""
    registry = ToolRegistry()
    registry.register(HighRiskTool())

    confirmation = AsyncMock()
    confirmation.request_confirmation_with_retry = AsyncMock(return_value=True)
    whitelist = WhitelistManager()
    auditor = AuditLogger()

    executor = Executor(
        registry,
        confirmation=confirmation,
        whitelist=whitelist,
        auditor=auditor,
        require_confirmation_for=["HIGH"],
    )

    result = await executor.execute_tool("dangerous_operation", {"action": "delete"})

    assert result.success
    # Confirmation MUST be requested for HIGH risk
    confirmation.request_confirmation_with_retry.assert_called_once()


@pytest.mark.asyncio
async def test_high_risk_tool_denied_by_user():
    """Test that denied high-risk tool returns error without executing."""
    registry = ToolRegistry()
    registry.register(HighRiskTool())

    confirmation = AsyncMock()
    confirmation.request_confirmation_with_retry = AsyncMock(return_value=False)
    whitelist = WhitelistManager()
    auditor = AuditLogger()

    executor = Executor(
        registry,
        confirmation=confirmation,
        whitelist=whitelist,
        auditor=auditor,
        require_confirmation_for=["HIGH"],
    )

    result = await executor.execute_tool("dangerous_operation", {"action": "delete"})

    # Should fail because user denied
    assert not result.success
    assert "denied" in result.error.lower() or "denied" in str(result.error).lower()


@pytest.mark.asyncio
async def test_audit_logging_tracks_all_operations():
    """Test that all operations are audited."""
    registry = ToolRegistry()
    registry.register(LowRiskTool())

    auditor = AuditLogger()
    confirmation = ConfirmationPrompt()
    whitelist = WhitelistManager()

    executor = Executor(
        registry,
        confirmation=confirmation,
        whitelist=whitelist,
        auditor=auditor,
        require_confirmation_for=["HIGH"],
    )

    await executor.execute_tool("safe_operation", {"query": "test query"})

    # Verify audit entry was created
    assert len(auditor.entries) > 0
    entry = auditor.entries[0]
    assert entry.tool_name == "safe_operation"
    assert entry.result_status == "success"


@pytest.mark.asyncio
async def test_executor_validates_tool_exists():
    """Test that executor validates tool exists before execution."""
    registry = ToolRegistry()
    registry.register(LowRiskTool())

    executor = Executor(registry)

    result = await executor.execute_tool(
        "nonexistent_tool",
        {"param": "value"},
    )

    assert not result.success
    assert "not found" in result.error.lower()


@pytest.mark.asyncio
async def test_executor_validates_parameters():
    """Test that executor validates parameters before execution."""
    registry = ToolRegistry()
    registry.register(HighRiskTool())

    executor = Executor(registry)

    # Missing required "action" parameter
    result = await executor.execute_tool("dangerous_operation", {})

    assert not result.success
    assert "parameter" in result.error.lower() or "valid" in result.error.lower()


@pytest.mark.asyncio
async def test_executor_handles_tool_execution_errors():
    """Test that executor handles tool execution errors gracefully."""

    class FailingTool(Tool):
        name = "failing_tool"
        description = "Tool that fails"
        risk_level = RiskLevel.LOW

        async def execute(self, **kwargs) -> ToolResult:
            raise RuntimeError("Intentional failure")

        def get_parameters(self) -> list[ToolParameter]:
            return []

    registry = ToolRegistry()
    registry.register(FailingTool())

    executor = Executor(registry)

    result = await executor.execute_tool("failing_tool", {})

    assert not result.success
    assert "error" in result.error.lower()


@pytest.mark.asyncio
async def test_whitelist_blocks_dangerous_commands():
    """Test that whitelist blocks dangerous commands."""
    registry = ToolRegistry()

    class ShellTool(Tool):
        name = "shell_execute"
        description = "Execute shell command"
        risk_level = RiskLevel.HIGH

        async def execute(self, command: str = "") -> ToolResult:
            return ToolResult(success=True, output="Executed")

        def get_parameters(self) -> list[ToolParameter]:
            return [
                ToolParameter(
                    name="command",
                    type="string",
                    description="Command to execute",
                    required=True,
                )
            ]

    registry.register(ShellTool())

    whitelist = WhitelistManager()
    whitelist.add_command_pattern("safe_command")
    whitelist.add_forbidden_pattern("*rm*")

    confirmation = AsyncMock()
    confirmation.request_confirmation_with_retry = AsyncMock(return_value=True)

    executor = Executor(
        registry,
        confirmation=confirmation,
        whitelist=whitelist,
        require_confirmation_for=["HIGH"],
    )

    # Try dangerous command
    result = await executor.execute_tool("shell_execute", {"command": "rm -rf /"})

    # Should be blocked by whitelist
    assert not result.success
    assert "whitelist" in result.error.lower() or "not whitelisted" in result.error.lower()


@pytest.mark.asyncio
async def test_executor_tracks_execution_count():
    """Test that executor tracks total executions."""
    registry = ToolRegistry()
    registry.register(LowRiskTool())

    executor = Executor(registry)

    await executor.execute_tool("safe_operation", {})
    await executor.execute_tool("safe_operation", {})
    await executor.execute_tool("safe_operation", {})

    stats = executor.get_stats()
    assert stats["total_executions"] == 3

"""Executor for running tools with safety checks and auditing."""

import logging
from typing import Any

from jarvis.safety.auditor import AuditLogger
from jarvis.safety.confirmation import ConfirmationPrompt
from jarvis.safety.executor import SafeExecutor
from jarvis.safety.whitelist import WhitelistManager
from jarvis.tools.base import RiskLevel, ToolResult
from jarvis.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)


class Executor:
    """
    Main executor that runs tools with safety enforcement.

    Responsibilities:
    - Validate tool parameters
    - Enforce safety policy (confirmations, whitelist, audit logging)
    - Handle errors gracefully
    - Track execution statistics

    Safety integration:
    - All tool executions go through SafeExecutor
    - HIGH/MEDIUM risk tools require user confirmation
    - All operations logged to audit trail
    - Tool parameters validated against whitelist
    """

    def __init__(
        self,
        tool_registry: ToolRegistry,
        confirmation: ConfirmationPrompt | None = None,
        whitelist: WhitelistManager | None = None,
        auditor: AuditLogger | None = None,
        require_confirmation_for: list[str] | None = None,
    ):
        """
        Initialize executor with safety layer.

        Args:
            tool_registry: Registry of available tools
            confirmation: Confirmation system for user approval
            whitelist: Whitelist manager for parameter validation
            auditor: Audit logger for operation tracking
            require_confirmation_for: Risk levels requiring confirmation
                (defaults to ["HIGH"] - configure via ToolSettings)
        """
        self.tool_registry = tool_registry
        self.execution_count = 0
        
        # Initialize safety layer
        require_confirmation_for = require_confirmation_for or ["HIGH"]
        self.safe_executor = SafeExecutor(
            confirmation=confirmation,
            whitelist=whitelist,
            auditor=auditor,
            require_confirmation_for=require_confirmation_for,
        )
        
        logger.info(
            f"Executor initialized with safety layer "
            f"(require_confirmation_for={require_confirmation_for})"
        )

    async def execute_tool(self, tool_name: str, arguments: dict[str, Any]) -> ToolResult:
        """
        Execute a tool with safety checks.

        Safety enforcement pipeline:
        1. Validate tool exists in registry
        2. Validate parameters against schema
        3. Check whitelist (if enabled)
        4. Request user confirmation (if HIGH/MEDIUM risk)
        5. Execute tool
        6. Log execution to audit trail

        Args:
            tool_name: Name of tool to execute
            arguments: Tool arguments

        Returns:
            ToolResult with execution outcome
        """
        self.execution_count += 1
        logger.info(f"Executing tool '{tool_name}' (execution #{self.execution_count})")

        # 1. Validate tool exists
        tool = self.tool_registry.get(tool_name)
        if not tool:
            error_msg = f"Tool '{tool_name}' not found in registry"
            logger.error(error_msg)
            return ToolResult(success=False, output=None, error=error_msg)

        # 2. Validate parameters
        is_valid, error = self.tool_registry.validate_parameters(tool_name, **arguments)
        if not is_valid:
            error_msg = f"Parameter validation failed: {error}"
            logger.error(error_msg)
            return ToolResult(success=False, output=None, error=error_msg)

        # 3-6. Execute through safety layer (includes confirmation, whitelist, audit)
        try:
            logger.debug(f"Tool '{tool_name}' parameters: {arguments}")
            
            # SafeExecutor handles:
            # - Whitelist checks
            # - User confirmation (if needed)
            # - Execution
            # - Audit logging
            result = await self.safe_executor.execute(tool, **arguments)

            if result.success:
                logger.info(f"Tool '{tool_name}' executed successfully")
            else:
                logger.warning(f"Tool '{tool_name}' failed: {result.error}")

            return result

        except ValueError as e:
            # Whitelist violation
            error_msg = f"Tool execution blocked: {str(e)}"
            logger.error(error_msg)
            return ToolResult(success=False, output=None, error=error_msg)
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

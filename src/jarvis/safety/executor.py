"""Safe executor wrapper that enforces confirmations and logging."""

from __future__ import annotations

import time
from typing import Any

from jarvis.safety.auditor import AuditLogger
from jarvis.safety.confirmation import ConfirmationPrompt
from jarvis.safety.whitelist import WhitelistManager
from jarvis.tools.base import RiskLevel, Tool, ToolResult


class SafeExecutor:
    """Execute tools safely with confirmations, whitelisting, and logging."""

    def __init__(
        self,
        confirmation: ConfirmationPrompt | None = None,
        whitelist: WhitelistManager | None = None,
        auditor: AuditLogger | None = None,
        require_confirmation_for: list[str] | None = None,
    ):
        """
        Initialize safe executor.

        Args:
            confirmation: Confirmation system (optional)
            whitelist: Whitelist manager (optional)
            auditor: Audit logger (optional)
            require_confirmation_for: Risk levels requiring confirmation
                Default: ["MEDIUM", "HIGH"]
        """
        self.confirmation = confirmation
        self.whitelist = whitelist
        self.auditor = auditor
        self.require_confirmation_for = require_confirmation_for or ["MEDIUM", "HIGH"]

    async def execute(
        self,
        tool: Tool,
        **kwargs: Any,
    ) -> ToolResult:
        """
        Execute a tool with safety checks.

        Args:
            tool: Tool to execute
            **kwargs: Parameters for tool

        Returns:
            Tool result with audit logging
        """
        start_time = time.time()
        risk_level = getattr(tool, "risk_level", RiskLevel.LOW).name

        # Determine if confirmation is needed
        needs_confirmation = risk_level in self.require_confirmation_for

        # Pre-execution checks
        if self.whitelist:
            self._check_whitelist(tool.name, kwargs)

        user_approved = None
        denied = False

        # Request confirmation if needed
        if needs_confirmation and self.confirmation:
            user_approved = await self.confirmation.request_confirmation_with_retry(
                operation=f"Execute {tool.name}",
                tool_name=tool.name,
                parameters=kwargs,
                reason=f"This is a {risk_level} risk operation",
            )

            if not user_approved:
                denied = True
                result_status = "denied"
                error_msg = "Operation denied by user"
        else:
            user_approved = True

        # Execute tool if approved
        if not denied:
            try:
                result = await tool.execute(**kwargs)
                result_status = "success" if result.success else "failed"
                error_msg = result.error if not result.success else None
            except Exception as exc:  # noqa: BLE001
                result = ToolResult(
                    success=False,
                    output="",
                    error=f"Execution error: {exc}",
                )
                result_status = "failed"
                error_msg = str(exc)
        else:
            result = ToolResult(
                success=False,
                output="",
                error=error_msg,
            )

        # Log to audit trail
        if self.auditor:
            duration = time.time() - start_time
            self.auditor.log_operation(
                tool_name=tool.name,
                operation=f"Execute {tool.name}",
                parameters=kwargs,
                risk_level=risk_level,
                user_approved=user_approved,
                result_status=result_status,
                error_message=error_msg,
                duration_seconds=duration,
                metadata={
                    "tool_description": tool.description,
                    "capabilities": tool.capabilities,
                },
            )

        return result

    def _check_whitelist(self, tool_name: str, parameters: dict[str, Any]) -> None:
        """
        Check if parameters are whitelisted.

        Args:
            tool_name: Name of tool
            parameters: Parameters to check

        Raises:
            ValueError: If parameters not whitelisted
        """
        if not self.whitelist:
            return

        # Check specific parameters based on tool
        if tool_name == "shell_execute":
            command = parameters.get("command", "")
            if not self.whitelist.is_command_allowed(command):
                raise ValueError(f"Command not whitelisted: {command}")

        elif tool_name in ("file_read", "file_write"):
            path = parameters.get("path", "")
            if not self.whitelist.is_path_allowed(path):
                raise ValueError(f"Path not whitelisted: {path}")

        elif tool_name == "list_directory":
            path = parameters.get("path", ".")
            if not self.whitelist.is_path_allowed(path):
                raise ValueError(f"Path not whitelisted: {path}")

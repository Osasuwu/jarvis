"""User confirmation prompts for high-risk operations."""

from __future__ import annotations

import asyncio
from typing import Any


class ConfirmationPrompt:
    """Interactive confirmation system for risky operations."""

    def __init__(self, auto_approve_whitelist: bool = False):
        """
        Initialize confirmation system.

        Args:
            auto_approve_whitelist: Auto-approve whitelisted operations
        """
        self.auto_approve_whitelist = auto_approve_whitelist

    async def request_confirmation(
        self,
        operation: str,
        tool_name: str,
        parameters: dict[str, Any],
        reason: str | None = None,
    ) -> bool:
        """
        Request user confirmation for an operation.

        Args:
            operation: Description of operation (e.g., "Execute shell command")
            tool_name: Name of the tool (e.g., "shell_execute")
            parameters: Parameters being passed to tool
            reason: Optional reason why confirmation is needed

        Returns:
            True if approved, False if denied
        """
        # Format the prompt
        prompt_lines = [
            "",
            "⚠️  HIGH-RISK OPERATION REQUIRES CONFIRMATION",
            "=" * 50,
            f"Tool: {tool_name}",
            f"Operation: {operation}",
            "",
            "Parameters:",
        ]

        # Add parameter details
        for key, value in parameters.items():
            # Truncate long values
            val_str = str(value)
            if len(val_str) > 60:
                val_str = val_str[:57] + "..."
            prompt_lines.append(f"  {key}: {val_str}")

        if reason:
            prompt_lines.append("")
            prompt_lines.append(f"Reason: {reason}")

        prompt_lines.extend(
            [
                "",
                "Do you approve this operation?",
                "Type 'yes' to confirm, 'no' to deny, 'details' for more info:",
                "> ",
            ]
        )

        prompt_text = "\n".join(prompt_lines)

        # Get user input (run in thread to avoid blocking event loop)
        response = await asyncio.to_thread(input, prompt_text)

        return response.strip().lower() in ("yes", "y")

    async def request_confirmation_with_retry(
        self,
        operation: str,
        tool_name: str,
        parameters: dict[str, Any],
        reason: str | None = None,
        max_retries: int = 3,
    ) -> bool:
        """
        Request confirmation with retry logic.

        Args:
            operation: Description of operation
            tool_name: Name of the tool
            parameters: Parameters being passed
            reason: Optional reason
            max_retries: Maximum retry attempts

        Returns:
            True if approved, False after max retries or denial
        """
        for attempt in range(max_retries):
            try:
                result = await self.request_confirmation(
                    operation=operation,
                    tool_name=tool_name,
                    parameters=parameters,
                    reason=reason,
                )
                return result
            except EOFError:
                # Handle non-interactive environments
                print("No input available (non-interactive mode) — operation denied")
                return False
            except KeyboardInterrupt:
                print("\nOperation cancelled by user")
                return False
            except Exception as exc:  # noqa: BLE001
                print(f"Error getting confirmation: {exc}")
                if attempt == max_retries - 1:
                    return False
                continue

        return False

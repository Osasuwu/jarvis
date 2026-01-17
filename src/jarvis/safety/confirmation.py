"""User confirmation prompts for high-risk operations."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from jarvis.self_improvement.models import CopilotPrompt, DecisionType, ImprovementOpportunity


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


class ImprovementApprovalPrompt(ConfirmationPrompt):
    """Extended confirmation for self-improvement operations.

    Per design decision Q2: Extends existing safety module with structured
    approval for self-improvement, maintaining consistency with other
    human approval gates.
    """

    async def request_improvement_approval(
        self,
        opportunity: ImprovementOpportunity,
        proposed_prompt: CopilotPrompt,
        rationale: str,
    ) -> tuple[DecisionType, str | None]:
        """Request approval for a self-improvement opportunity.

        Args:
            opportunity: The detected improvement opportunity
            proposed_prompt: The generated Copilot prompt
            rationale: Why the detector proposed this

        Returns:
            Tuple of (decision, metadata):
            - (APPROVE, None): User approved as-is
            - (REJECT, reason): User rejected with optional reason
            - (EDIT, edited_text): User wants to edit the prompt
            - (REJECT, "category_disabled:<reason>"): User disabled this detector category
        """
        from jarvis.self_improvement.models import DecisionType

        prompt_lines = [
            "",
            "🔍 SELF-IMPROVEMENT OPPORTUNITY",
            "=" * 60,
            f"File: {opportunity.file_path}:{opportunity.line_number}",
            f"Category: {opportunity.category.value}",
            f"Severity: {opportunity.severity.value}",
            f"Detector: {opportunity.detector_name}",
            "",
            f"Issue: {opportunity.description}",
            "",
            "Rationale:",
            f"  {rationale}",
            "",
            "Proposed Copilot Prompt:",
            "-" * 60,
            proposed_prompt.prompt_text,
            "-" * 60,
            "",
            "Options:",
            "  [a] Approve - Send prompt to Copilot",
            "  [r] Reject - Skip this improvement",
            "  [e] Edit - Modify the prompt before sending",
            "  [s] Skip category - Disable this detector type",
            "",
            "Your decision (a/r/e/s): ",
        ]

        prompt_text = "\n".join(prompt_lines)
        response = await asyncio.to_thread(input, prompt_text)
        decision = response.strip().lower()

        if decision in ("a", "approve"):
            return (DecisionType.APPROVE, None)

        if decision in ("e", "edit"):
            edit_prompt = "\nEnter your edited prompt (or press Ctrl+C to cancel):\n> "
            try:
                edited_text = await asyncio.to_thread(input, edit_prompt)
                if edited_text.strip():
                    return (DecisionType.EDIT, edited_text.strip())
                print("No changes provided, treating as rejection")
                return (DecisionType.REJECT, "No edits provided")
            except (KeyboardInterrupt, EOFError):
                return (DecisionType.REJECT, "Edit cancelled")

        if decision in ("s", "skip", "skip_category"):
            reason_prompt = "\nReason for disabling this category (optional): "
            try:
                reason = await asyncio.to_thread(input, reason_prompt)
                reason_text = reason.strip() if reason.strip() else "User disabled"
                # Return REJECT with special metadata prefix to indicate category disable
                return (DecisionType.REJECT, f"category_disabled:{reason_text}")
            except (KeyboardInterrupt, EOFError):
                return (DecisionType.REJECT, "category_disabled:User disabled")

        # Default to reject for any other input
        if decision in ("r", "reject"):
            reason_prompt = "\nReason for rejection (optional): "
            try:
                reason = await asyncio.to_thread(input, reason_prompt)
                return (DecisionType.REJECT, reason.strip() if reason.strip() else None)
            except (KeyboardInterrupt, EOFError):
                return (DecisionType.REJECT, None)

        return (DecisionType.REJECT, f"Invalid response: {decision}")

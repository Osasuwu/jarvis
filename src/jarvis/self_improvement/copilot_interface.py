"""Copilot Interface - bridge between agent and VS Code Copilot Chat.

This module handles the interaction with VS Code Copilot Chat,
either through programmatic API or file-based handoff.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path

from jarvis.self_improvement.models import (
    CopilotPrompt,
    ExecutionReport,
    ExecutionStatus,
)


class IntegrationMethod(str, Enum):
    """Method for integrating with VS Code Copilot.

    Per spec section 2 - Integration Options.
    See design_questions.md Q1 for prioritization discussion.
    """

    FILE_BASED = "file_based"
    VSCODE_API = "vscode_api"  # Future: Requires VS Code extension development
    CHAT_PARTICIPANTS = "chat_participants"  # Future: Investigate availability


@dataclass
class InterfaceConfig:
    """Configuration for the Copilot interface."""

    method: IntegrationMethod = IntegrationMethod.FILE_BASED
    queue_path: Path | None = None  # For file-based method
    timeout_seconds: int = 300  # 5 minute default timeout

    def __post_init__(self) -> None:
        if self.method == IntegrationMethod.FILE_BASED and self.queue_path is None:
            self.queue_path = Path(".copilot_queue")


class CopilotInterface:
    """Interface for executing prompts via VS Code Copilot.

    Per spec section 2: Bridge between agent and VS Code Copilot Chat.
    """

    def __init__(self, config: InterfaceConfig | None = None):
        """Initialize the interface.

        Args:
            config: Interface configuration
        """
        self.config = config or InterfaceConfig()
        self._ensure_queue_directory()

    def _ensure_queue_directory(self) -> None:
        """Ensure the queue directory exists for file-based method."""
        if self.config.method == IntegrationMethod.FILE_BASED and self.config.queue_path:
            self.config.queue_path.mkdir(parents=True, exist_ok=True)

    def enqueue_prompt(self, prompt: CopilotPrompt) -> Path:
        """Enqueue a prompt for execution.

        Per spec: If human approves, enqueue to CopilotInterface with the packaged context.

        Args:
            prompt: The approved prompt to execute

        Returns:
            Path to the queued prompt file
        """
        if self.config.method != IntegrationMethod.FILE_BASED:
            raise NotImplementedError(
                f"Integration method {self.config.method} is not yet implemented. "
                "See spec Open Questions R-1: VS Code Copilot Chat API investigation required."
            )

        return self._enqueue_file_based(prompt)

    def _enqueue_file_based(self, prompt: CopilotPrompt) -> Path:
        """Enqueue prompt using file-based handoff.

        Creates a markdown file that the user can copy to Copilot Chat.
        """
        if not self.config.queue_path:
            raise ValueError("Queue path not configured")

        # Create filename with timestamp and ID
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{timestamp}_{prompt.id}.md"
        file_path = self.config.queue_path / filename

        # Build the prompt file content
        content = self._format_prompt_for_file(prompt)

        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)

        # Also create a metadata file for tracking
        meta_path = self.config.queue_path / f"{timestamp}_{prompt.id}.meta.json"
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "prompt_id": prompt.id,
                    "queued_at": datetime.now().isoformat(),
                    "status": "pending",
                    "expected_changes": [c.to_dict() for c in prompt.expected_changes],
                    "validation_plan": prompt.validation_plan,
                },
                f,
                indent=2,
            )

        return file_path

    def _format_prompt_for_file(self, prompt: CopilotPrompt) -> str:
        """Format the prompt for the file-based handoff."""
        lines = [
            f"# Copilot Prompt: {prompt.id}",
            "",
            f"**Generated:** {prompt.generated_at}",
            f"**Priority:** {prompt.priority}/10",
            f"**Risk Level:** {prompt.risk_level.value}",
            "",
            "## Context Files",
            "",
        ]

        for ctx_file in prompt.context_files:
            lines.append(f"- `{ctx_file}`")

        lines.extend(
            [
                "",
                "## Prompt",
                "",
                "Copy the following prompt to VS Code Copilot Chat:",
                "",
                "---",
                "",
                prompt.prompt_text,
                "",
                "---",
                "",
                "## Expected Changes",
                "",
            ]
        )

        for change in prompt.expected_changes:
            lines.append(f"- **{change.file}**: {change.change_type.value} - {change.description}")

        lines.extend(
            [
                "",
                "## Validation Plan",
                "",
                "After Copilot makes changes, run these validations:",
                "",
            ]
        )

        for validation in prompt.validation_plan:
            lines.append(f"```bash\n{validation}\n```")
            lines.append("")

        lines.extend(
            [
                "## Instructions",
                "",
                "1. Open the context files listed above in VS Code",
                "2. Open Copilot Chat (Ctrl+Shift+I or Cmd+Shift+I)",
                "3. Copy and paste the prompt above",
                "4. Review Copilot's suggested changes before accepting",
                "5. Run the validation commands",
                "6. Mark this prompt as complete by renaming the file to `.done.md`",
                "",
            ]
        )

        return "\n".join(lines)

    def check_execution_status(self, prompt: CopilotPrompt) -> ExecutionReport | None:
        """Check the execution status of a prompt.

        For file-based method, checks if the user has marked the prompt as done.

        Args:
            prompt: The prompt to check

        Returns:
            ExecutionReport if execution is complete, None if still pending
        """
        if self.config.method != IntegrationMethod.FILE_BASED:
            raise NotImplementedError(
                f"Integration method {self.config.method} is not yet implemented."
            )

        return self._check_file_based_status(prompt)

    def _check_file_based_status(self, prompt: CopilotPrompt) -> ExecutionReport | None:
        """Check status using file-based method."""
        if not self.config.queue_path:
            return None

        # Look for completed file (*.done.md)
        for done_file in self.config.queue_path.glob(f"*_{prompt.id}.done.md"):
            # Found completed prompt
            meta_path = self.config.queue_path / f"{done_file.stem.replace('.done', '')}.meta.json"

            meta = {}
            if meta_path.exists():
                with open(meta_path, encoding="utf-8") as f:
                    meta = json.load(f)

            return ExecutionReport(
                prompt_id=prompt.id,
                status=ExecutionStatus.SUCCESS,
                files_modified=meta.get("files_modified", []),
                files_expected=[c.file for c in prompt.expected_changes],
                scope_match=True,  # User verified by marking done
                validations={},
                duration_seconds=0,
                error_details=None,
                copilot_response_length=0,
                user_notes=meta.get("user_notes", ""),
            )

        # Check for failed file
        for failed_file in self.config.queue_path.glob(f"*_{prompt.id}.failed.md"):
            meta_path = (
                self.config.queue_path / f"{failed_file.stem.replace('.failed', '')}.meta.json"
            )

            meta = {}
            if meta_path.exists():
                with open(meta_path, encoding="utf-8") as f:
                    meta = json.load(f)

            return ExecutionReport(
                prompt_id=prompt.id,
                status=ExecutionStatus.FAILED,
                files_modified=[],
                files_expected=[c.file for c in prompt.expected_changes],
                scope_match=False,
                validations={},
                duration_seconds=0,
                error_details=meta.get("error_details", "User marked as failed"),
                copilot_response_length=0,
                user_notes=meta.get("user_notes", ""),
            )

        return None

    def get_pending_prompts(self) -> list[str]:
        """Get list of pending prompt IDs.

        Returns:
            List of prompt IDs that are still pending
        """
        if self.config.method != IntegrationMethod.FILE_BASED:
            return []

        if not self.config.queue_path:
            return []

        pending: list[str] = []
        for md_file in self.config.queue_path.glob("*.md"):
            if ".done." in md_file.name or ".failed." in md_file.name:
                continue
            # Extract prompt ID from filename
            parts = md_file.stem.split("_", 1)
            if len(parts) > 1:
                pending.append(parts[1])

        return pending

    def mark_complete(
        self,
        prompt: CopilotPrompt,
        files_modified: list[str],
        user_notes: str = "",
    ) -> ExecutionReport:
        """Mark a prompt as successfully completed.

        Args:
            prompt: The prompt that was executed
            files_modified: List of files that were modified
            user_notes: Optional notes from the user

        Returns:
            Execution report
        """
        if self.config.method != IntegrationMethod.FILE_BASED:
            raise NotImplementedError(
                f"Integration method {self.config.method} is not yet implemented."
            )

        return self._mark_file_based_complete(prompt, files_modified, user_notes)

    def _mark_file_based_complete(
        self,
        prompt: CopilotPrompt,
        files_modified: list[str],
        user_notes: str,
    ) -> ExecutionReport:
        """Mark prompt as complete using file-based method."""
        if not self.config.queue_path:
            raise ValueError("Queue path not configured")

        # Find the original prompt file
        for md_file in self.config.queue_path.glob(f"*_{prompt.id}.md"):
            if ".done." in md_file.name or ".failed." in md_file.name:
                continue

            # Rename to done
            done_path = md_file.with_suffix(".done.md")
            md_file.rename(done_path)

            # Update metadata
            meta_path = self.config.queue_path / f"{md_file.stem}.meta.json"
            if meta_path.exists():
                with open(meta_path, encoding="utf-8") as f:
                    meta = json.load(f)

                meta["status"] = "completed"
                meta["completed_at"] = datetime.now().isoformat()
                meta["files_modified"] = files_modified
                meta["user_notes"] = user_notes

                with open(meta_path, "w", encoding="utf-8") as f:
                    json.dump(meta, f, indent=2)

            break

        # Determine if scope matched
        expected_files = {c.file for c in prompt.expected_changes}
        modified_set = set(files_modified)
        scope_match = expected_files == modified_set or expected_files.issubset(modified_set)

        return ExecutionReport(
            prompt_id=prompt.id,
            status=ExecutionStatus.SUCCESS,
            files_modified=files_modified,
            files_expected=[c.file for c in prompt.expected_changes],
            scope_match=scope_match,
            validations={},
            duration_seconds=0,
            error_details=None,
            copilot_response_length=0,
            user_notes=user_notes,
        )

    def mark_failed(
        self,
        prompt: CopilotPrompt,
        error_details: str,
        user_notes: str = "",
    ) -> ExecutionReport:
        """Mark a prompt as failed.

        Args:
            prompt: The prompt that failed
            error_details: Description of what went wrong
            user_notes: Optional notes from the user

        Returns:
            Execution report
        """
        if self.config.method != IntegrationMethod.FILE_BASED:
            raise NotImplementedError(
                f"Integration method {self.config.method} is not yet implemented."
            )

        if not self.config.queue_path:
            raise ValueError("Queue path not configured")

        # Find and rename the prompt file
        for md_file in self.config.queue_path.glob(f"*_{prompt.id}.md"):
            if ".done." in md_file.name or ".failed." in md_file.name:
                continue

            failed_path = md_file.with_suffix(".failed.md")
            md_file.rename(failed_path)

            # Update metadata
            meta_path = self.config.queue_path / f"{md_file.stem}.meta.json"
            if meta_path.exists():
                with open(meta_path, encoding="utf-8") as f:
                    meta = json.load(f)

                meta["status"] = "failed"
                meta["failed_at"] = datetime.now().isoformat()
                meta["error_details"] = error_details
                meta["user_notes"] = user_notes

                with open(meta_path, "w", encoding="utf-8") as f:
                    json.dump(meta, f, indent=2)

            break

        return ExecutionReport(
            prompt_id=prompt.id,
            status=ExecutionStatus.FAILED,
            files_modified=[],
            files_expected=[c.file for c in prompt.expected_changes],
            scope_match=False,
            validations={},
            duration_seconds=0,
            error_details=error_details,
            copilot_response_length=0,
            user_notes=user_notes,
        )

    def cleanup_old_prompts(self, days: int = 30) -> int:
        """Clean up old completed/failed prompt files.

        Args:
            days: Remove files older than this many days

        Returns:
            Number of files removed
        """
        if self.config.method != IntegrationMethod.FILE_BASED:
            return 0

        if not self.config.queue_path:
            return 0

        from datetime import timedelta

        removed = 0
        cutoff = datetime.now() - timedelta(days=days)

        for file_path in self.config.queue_path.iterdir():
            if not file_path.is_file():
                continue

            # Only clean up completed/failed files
            if ".done." not in file_path.name and ".failed." not in file_path.name:
                continue

            # Check file age
            mtime = datetime.fromtimestamp(file_path.stat().st_mtime)
            if mtime < cutoff:
                file_path.unlink()
                removed += 1

        return removed

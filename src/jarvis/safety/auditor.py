"""Audit logging system for tracking all operations."""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass
class AuditEntry:
    """Single audit log entry."""

    timestamp: str
    tool_name: str
    operation: str
    parameters: dict[str, Any]
    risk_level: str
    user_approved: bool | None = None
    result_status: str | None = None  # "success", "failed", "denied"
    error_message: str | None = None
    duration_seconds: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert entry to dictionary."""
        return asdict(self)

    def to_json(self) -> str:
        """Convert entry to JSON string."""
        return json.dumps(self.to_dict())


class AuditLogger:
    """Audit logging system for operations."""

    def __init__(self, log_file: str | Path | None = None):
        """
        Initialize audit logger.

        Args:
            log_file: Path to audit log file (optional)
        """
        self.log_file = Path(log_file) if log_file else None
        self.entries: list[AuditEntry] = []
        self.logger = logging.getLogger(__name__)

        if self.log_file:
            self.log_file.parent.mkdir(parents=True, exist_ok=True)

    def log_operation(
        self,
        tool_name: str,
        operation: str,
        parameters: dict[str, Any],
        risk_level: str,
        user_approved: bool | None = None,
        result_status: str | None = None,
        error_message: str | None = None,
        duration_seconds: float | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AuditEntry:
        """
        Log an operation.

        Args:
            tool_name: Name of tool
            operation: Operation description
            parameters: Parameters used
            risk_level: Risk level (LOW/MEDIUM/HIGH)
            user_approved: Whether user approved (None for LOW risk)
            result_status: Operation result (success/failed/denied)
            error_message: Error message if failed
            duration_seconds: How long operation took
            metadata: Additional metadata

        Returns:
            Created audit entry
        """
        entry = AuditEntry(
            timestamp=datetime.now().isoformat(),
            tool_name=tool_name,
            operation=operation,
            parameters=parameters,
            risk_level=risk_level,
            user_approved=user_approved,
            result_status=result_status,
            error_message=error_message,
            duration_seconds=duration_seconds,
            metadata=metadata or {},
        )

        self.entries.append(entry)

        # Log to file if configured
        if self.log_file:
            self._write_to_file(entry)

        # Also log to Python logger
        log_msg = (
            f"[{risk_level}] {tool_name}: {operation} "
            f"(approved={user_approved}, status={result_status})"
        )
        self.logger.info(log_msg)

        return entry

    def _write_to_file(self, entry: AuditEntry) -> None:
        """Write entry to audit log file."""
        try:
            with self.log_file.open("a") as f:
                f.write(entry.to_json() + "\n")
        except Exception as exc:  # noqa: BLE001
            self.logger.error(f"Failed to write audit log: {exc}")

    def get_entries(self, limit: int | None = None) -> list[AuditEntry]:
        """
        Get audit entries.

        Args:
            limit: Maximum number of entries to return

        Returns:
            List of audit entries
        """
        if limit:
            return self.entries[-limit:]
        return self.entries

    def get_entries_by_risk(self, risk_level: str) -> list[AuditEntry]:
        """
        Get entries filtered by risk level.

        Args:
            risk_level: Risk level to filter by

        Returns:
            Filtered entries
        """
        return [e for e in self.entries if e.risk_level == risk_level]

    def get_entries_by_tool(self, tool_name: str) -> list[AuditEntry]:
        """
        Get entries filtered by tool name.

        Args:
            tool_name: Tool name to filter by

        Returns:
            Filtered entries
        """
        return [e for e in self.entries if e.tool_name == tool_name]

    def get_denied_operations(self) -> list[AuditEntry]:
        """Get all denied operations."""
        return [e for e in self.entries if e.result_status == "denied"]

    def get_failed_operations(self) -> list[AuditEntry]:
        """Get all failed operations."""
        return [e for e in self.entries if e.result_status == "failed"]

    def get_summary(self) -> dict[str, Any]:
        """Get summary statistics."""
        return {
            "total_operations": len(self.entries),
            "by_risk_level": {
                "LOW": len(self.get_entries_by_risk("LOW")),
                "MEDIUM": len(self.get_entries_by_risk("MEDIUM")),
                "HIGH": len(self.get_entries_by_risk("HIGH")),
            },
            "denied_count": len(self.get_denied_operations()),
            "failed_count": len(self.get_failed_operations()),
        }

    def clear(self) -> None:
        """Clear all entries from memory."""
        self.entries.clear()

    def export_to_json(self, filepath: str | Path) -> None:
        """
        Export all entries to JSON file.

        Args:
            filepath: Path to export to
        """
        Path(filepath).write_text(
            json.dumps([e.to_dict() for e in self.entries], indent=2)
        )

    def load_from_file(self, filepath: str | Path) -> None:
        """
        Load entries from audit log file.

        Args:
            filepath: Path to log file
        """
        self.entries.clear()
        try:
            with Path(filepath).open() as f:
                for line in f:
                    if line.strip():
                        data = json.loads(line)
                        entry = AuditEntry(**data)
                        self.entries.append(entry)
        except Exception as exc:  # noqa: BLE001
            self.logger.error(f"Failed to load audit log: {exc}")

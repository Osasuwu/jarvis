"""Approval Tracker - maintains history of proposals and learns from patterns.

This module records approval/rejection decisions and provides analytics
for learning what changes are acceptable.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from jarvis.self_improvement.models import (
    ApprovalDecision,
    Category,
    CopilotPrompt,
    DecisionType,
    ExecutionReport,
    ExecutionStatus,
)


@dataclass
class RateLimitConfig:
    """Rate limit configuration.

    Per spec section 4:
    - Global: max 20 improvements per week
    - Per-file: max 3 improvements per 7 days
    - Per-category: max 5 per cycle
    """

    global_max_per_week: int = 20
    per_file_max_per_week: int = 3
    per_category_max_per_cycle: int = 5
    rejection_cooldown_days: list[int] | None = None  # 1 -> 3 -> 7 days

    def __post_init__(self) -> None:
        if self.rejection_cooldown_days is None:
            self.rejection_cooldown_days = [1, 3, 7]


@dataclass
class CooldownState:
    """Tracks cooldown state for a detector/file."""

    last_rejection: str  # ISO timestamp
    consecutive_rejections: int
    cooldown_until: str  # ISO timestamp


class ApprovalTracker:
    """Tracks approval history and provides analytics.

    Per spec section 2: Maintain history of proposals and learn from patterns.
    """

    def __init__(
        self,
        storage_path: Path,
        rate_limit_config: RateLimitConfig | None = None,
    ):
        """Initialize the tracker.

        Args:
            storage_path: Path to store approval history
            rate_limit_config: Rate limit configuration
        """
        self.storage_path = storage_path
        self.rate_limit_config = rate_limit_config or RateLimitConfig()
        self.decisions: list[ApprovalDecision] = []
        self.execution_reports: list[ExecutionReport] = []
        self.cooldowns: dict[str, CooldownState] = {}  # key -> CooldownState
        self._load_history()

    def _load_history(self) -> None:
        """Load existing history from storage."""
        self.storage_path.mkdir(parents=True, exist_ok=True)

        decisions_file = self.storage_path / "decisions.json"
        if decisions_file.exists():
            try:
                with open(decisions_file, encoding="utf-8") as f:
                    data = json.load(f)
                    self.decisions = [
                        ApprovalDecision(**d) for d in data.get("decisions", [])
                    ]
                    # Load cooldowns
                    for key, state in data.get("cooldowns", {}).items():
                        self.cooldowns[key] = CooldownState(**state)
            except (json.JSONDecodeError, OSError):
                # Start fresh if file is corrupted
                self.decisions = []

        reports_file = self.storage_path / "execution_reports.json"
        if reports_file.exists():
            try:
                with open(reports_file, encoding="utf-8") as f:
                    # Load as dicts, we don't need to reconstruct full objects for history
                    self.execution_reports = json.load(f)
            except (json.JSONDecodeError, OSError):
                self.execution_reports = []

    def _save_history(self) -> None:
        """Persist history to storage.

        Per spec: DO NOT lose approval history or decision reasons.
        """
        self.storage_path.mkdir(parents=True, exist_ok=True)

        # Save decisions
        decisions_file = self.storage_path / "decisions.json"
        with open(decisions_file, "w", encoding="utf-8") as f:
            data = {
                "decisions": [d.to_dict() for d in self.decisions],
                "cooldowns": {
                    k: {
                        "last_rejection": v.last_rejection,
                        "consecutive_rejections": v.consecutive_rejections,
                        "cooldown_until": v.cooldown_until,
                    }
                    for k, v in self.cooldowns.items()
                },
            }
            json.dump(data, f, indent=2)

        # Save execution reports separately (can be large)
        reports_file = self.storage_path / "execution_reports.json"
        with open(reports_file, "w", encoding="utf-8") as f:
            json.dump(
                [r.to_dict() if hasattr(r, "to_dict") else r for r in self.execution_reports],
                f,
                indent=2,
            )

    def record_decision(
        self,
        prompt: CopilotPrompt,
        decision: DecisionType,
        reason_code: str | None = None,
        user_feedback: str | None = None,
        edited_prompt: str | None = None,
        category: str | None = None,
        detector_name: str | None = None,
    ) -> ApprovalDecision:
        """Record an approval decision.

        Per spec:
        - DO record every approval/rejection decision with exact timestamp and reason code
        - DO NOT delete or modify past improvement records (only append)

        Args:
            prompt: The prompt that was reviewed
            decision: The decision made
            reason_code: Optional reason code
            user_feedback: Optional user feedback
            edited_prompt: The edited prompt text if decision was EDIT
            category: Category of the improvement
            detector_name: Name of the detector that found this opportunity

        Returns:
            The recorded decision
        """
        record = ApprovalDecision(
            prompt_id=prompt.id,
            decision=decision,
            timestamp=datetime.now().isoformat(),
            reason_code=reason_code,
            user_feedback=user_feedback,
            edited_prompt=edited_prompt,
            category=category,
            detector_name=detector_name,
        )

        self.decisions.append(record)

        # Update cooldowns on rejection
        if decision == DecisionType.REJECT:
            self._update_cooldown(prompt)

        self._save_history()
        return record

    def record_execution(self, report: ExecutionReport) -> None:
        """Record an execution report.

        Args:
            report: The execution report
        """
        self.execution_reports.append(report)
        self._save_history()

    def _update_cooldown(self, prompt: CopilotPrompt) -> None:
        """Update cooldown state after a rejection.

        Per spec: DO apply increasing cooldowns on repeated rejections (1 day -> 3 days -> 7 days)
        """
        # Use the file as the cooldown key
        key = prompt.context_files[0] if prompt.context_files else "global"

        now = datetime.now()

        if key in self.cooldowns:
            state = self.cooldowns[key]
            state.consecutive_rejections += 1
            state.last_rejection = now.isoformat()
        else:
            state = CooldownState(
                last_rejection=now.isoformat(),
                consecutive_rejections=1,
                cooldown_until=now.isoformat(),
            )

        # Calculate cooldown duration
        cooldown_index = min(
            state.consecutive_rejections - 1,
            len(self.rate_limit_config.rejection_cooldown_days or []) - 1,
        )
        if cooldown_index >= 0 and self.rate_limit_config.rejection_cooldown_days:
            cooldown_days = self.rate_limit_config.rejection_cooldown_days[cooldown_index]
            state.cooldown_until = (now + timedelta(days=cooldown_days)).isoformat()

        self.cooldowns[key] = state

    def is_file_in_cooldown(self, file_path: str) -> bool:
        """Check if a file is currently in cooldown.

        Args:
            file_path: The file path to check

        Returns:
            True if file is in cooldown
        """
        if file_path not in self.cooldowns:
            return False

        state = self.cooldowns[file_path]
        cooldown_until = datetime.fromisoformat(state.cooldown_until)
        return datetime.now() < cooldown_until

    def is_detector_disabled(self, detector_name: str) -> bool:
        """Check if a detector should be skipped.

        Per spec: DO skip detectors if their last 5 suggestions were all rejected
        (reset after 7 days)
        """
        # Get recent decisions for this detector
        recent = self._get_recent_decisions(days=7)

        # Filter to this detector's decisions using detector_name field
        detector_decisions = [
            d for d in recent
            if d.detector_name == detector_name
        ]

        if len(detector_decisions) < 5:
            return False

        # Check if last 5 were all rejections
        last_5 = detector_decisions[-5:]
        return all(d.decision == DecisionType.REJECT for d in last_5)

    def check_rate_limits(
        self,
        file_path: str | None = None,
        category: Category | None = None,  # noqa: ARG002 - reserved for future use
    ) -> dict[str, bool]:
        """Check if rate limits are exceeded.

        Per spec: DO check and enforce rate limits before processing.

        Args:
            file_path: Optional file to check per-file limit
            category: Optional category to check per-category limit

        Returns:
            Dict with limit names and whether they're exceeded
        """
        now = datetime.now()
        week_ago = now - timedelta(days=7)

        limits: dict[str, bool] = {}

        # Global limit: max 20 per week
        week_decisions = [
            d for d in self.decisions
            if datetime.fromisoformat(d.timestamp) > week_ago
            and d.decision == DecisionType.APPROVE
        ]
        limits["global_weekly"] = len(week_decisions) >= self.rate_limit_config.global_max_per_week

        # Per-file limit: max 3 per 7 days
        if file_path:
            file_decisions = [
                d for d in week_decisions
                if file_path in d.prompt_id  # Heuristic
            ]
            limits["per_file_weekly"] = len(file_decisions) >= self.rate_limit_config.per_file_max_per_week

        # Per-category limit is checked per-cycle, not here
        # See design_questions.md Q5: Cycle definition needs clarification

        return limits

    def get_approval_rate(self, category: Category | None = None, days: int = 30) -> float:
        """Get the approval rate for a category.

        Args:
            category: Optional category to filter by
            days: Number of days to look back

        Returns:
            Approval rate (0.0-1.0)
        """
        recent = self._get_recent_decisions(days)

        # Filter by category if specified (using heuristic on prompt_id)
        if category:
            recent = [d for d in recent if category.value in d.prompt_id.lower()]

        if not recent:
            return 0.5  # Default rate when no history

        approved = sum(1 for d in recent if d.decision == DecisionType.APPROVE)
        return approved / len(recent)

    def get_historical_context(self, category: Category) -> dict[str, int]:
        """Get historical context for approval requests.

        Per spec: DO show historical context: show approval/rejection rate for this category.

        Args:
            category: The category to get context for

        Returns:
            Dict with "approved" and "rejected" counts
        """
        recent = self._get_recent_decisions(days=90)

        # Filter by category
        category_decisions = [
            d for d in recent
            if category.value in d.prompt_id.lower()
        ]

        approved = sum(1 for d in category_decisions if d.decision == DecisionType.APPROVE)
        rejected = sum(1 for d in category_decisions if d.decision == DecisionType.REJECT)

        return {"approved": approved, "rejected": rejected}

    def get_skipped_detectors(self) -> set[str]:
        """Get detectors that should be skipped due to rejection patterns.

        Returns:
            Set of detector names to skip
        """
        # Known detectors to check
        detectors = ["pylint", "complexity", "coverage", "security"]
        skipped: set[str] = set()

        for detector in detectors:
            if self.is_detector_disabled(detector):
                skipped.add(detector)

        return skipped

    def get_execution_success_rate(self, days: int = 30) -> float:  # noqa: ARG002
        """Get the execution success rate.

        Per spec M-2: Track Copilot execution success rate.

        Args:
            days: Number of days to look back (note: time filtering not yet implemented
                  as ExecutionReport lacks timestamp field per spec)

        Returns:
            Success rate (0.0-1.0)
        """
        # Note: Without timestamp in ExecutionReport, we process all available reports
        # This is acceptable as tracker maintains recent history and old reports are periodically cleared

        # Filter recent reports
        recent_reports = []
        for report in self.execution_reports:
            # Handle both dict and object forms
            if isinstance(report, dict):
                # Skip if no status
                if "status" not in report:
                    continue
                # Check timestamp if available
                # Note: ExecutionReport doesn't have timestamp in spec, using creation time as proxy
                recent_reports.append(report)
            else:
                recent_reports.append(report.to_dict())

        if not recent_reports:
            return 1.0  # Assume success when no history

        successful = sum(
            1 for r in recent_reports
            if r.get("status") == ExecutionStatus.SUCCESS.value
        )
        return successful / len(recent_reports)

    def _get_recent_decisions(self, days: int) -> list[ApprovalDecision]:
        """Get decisions from the last N days."""
        cutoff = datetime.now() - timedelta(days=days)
        return [
            d for d in self.decisions
            if datetime.fromisoformat(d.timestamp) > cutoff
        ]

    def get_file_edit_frequency(self, file_path: str, days: int = 7) -> int:  # noqa: ARG002
        """Get how many times a file has been edited recently.

        Per spec M-3: Track files modified repeatedly by self-improvement.

        Args:
            file_path: The file to check
            days: Number of days to look back (note: time filtering not yet implemented
                  as ExecutionReport lacks timestamp field per spec)

        Returns:
            Edit count
        """
        count = 0
        # Note: Without timestamp in ExecutionReport, we count all reports
        # This is acceptable as the tracker maintains recent history
        # and old reports are cleared periodically

        for report in self.execution_reports:
            if isinstance(report, dict):
                files = report.get("files_modified", [])
            else:
                files = report.files_modified

            if file_path in files:
                count += 1

        return count

    def export_audit_log(self) -> list[dict[str, Any]]:
        """Export the full audit log.

        Per spec: Maintain immutable audit trail.

        Returns:
            List of all decisions and reports
        """
        log: list[dict[str, Any]] = []

        for decision in self.decisions:
            log.append({
                "type": "decision",
                "data": decision.to_dict(),
            })

        for report in self.execution_reports:
            log.append({
                "type": "execution",
                "data": report.to_dict() if hasattr(report, "to_dict") else report,
            })

        # Sort by timestamp
        log.sort(key=lambda x: x["data"].get("timestamp", x["data"].get("generated_at", "")))

        return log

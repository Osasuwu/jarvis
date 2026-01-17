"""Data models for the self-improvement module.

This module contains all the data structures defined in the spec's output contracts.
"""

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class Severity(str, Enum):
    """Severity levels for improvement opportunities."""

    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class Category(str, Enum):
    """Categories of improvement opportunities."""

    BUG = "bug"
    REFACTOR = "refactor"
    TEST = "test"
    DOCS = "docs"
    SECURITY = "security"
    PERFORMANCE = "performance"


class RiskLevel(str, Enum):
    """Risk levels for Copilot prompts."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class ChangeType(str, Enum):
    """Types of expected file changes."""

    ADD = "ADD"
    MODIFY = "MODIFY"
    REMOVE = "REMOVE"


class EstimatedEffort(str, Enum):
    """Estimated effort levels."""

    TRIVIAL = "trivial"
    SMALL = "small"
    MEDIUM = "medium"
    LARGE = "large"


class ExecutionStatus(str, Enum):
    """Status of prompt execution."""

    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    PARTIAL = "PARTIAL"
    ROLLBACK = "ROLLBACK"


class ValidationStatus(str, Enum):
    """Status of validation checks."""

    PASS = "PASS"
    FAIL = "FAIL"
    SKIPPED = "SKIPPED"


class DecisionType(str, Enum):
    """Types of approval decisions."""

    APPROVE = "APPROVE"
    REJECT = "REJECT"
    EDIT = "EDIT"
    DEFER = "DEFER"


@dataclass
class LineRange:
    """Represents a range of lines in a file."""

    start: int  # 1-indexed
    end: int  # 1-indexed

    def __post_init__(self) -> None:
        if self.start < 1:
            raise ValueError("Line numbers must be 1-indexed (start >= 1)")
        if self.end < self.start:
            raise ValueError("End line must be >= start line")

    def overlaps(self, other: LineRange, threshold: float = 0.8) -> bool:
        """Check if this range overlaps with another by at least threshold."""
        if self.start > other.end or other.start > self.end:
            return False

        overlap_start = max(self.start, other.start)
        overlap_end = min(self.end, other.end)
        overlap_size = overlap_end - overlap_start + 1

        self_size = self.end - self.start + 1
        other_size = other.end - other.start + 1
        min_size = min(self_size, other_size)

        return overlap_size / min_size >= threshold


@dataclass
class OpportunityContext:
    """Context information for an improvement opportunity."""

    code_snippet: str  # 20-50 lines max
    affected_files: list[str] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ImprovementOpportunity:
    """Represents a detected improvement opportunity.

    Contract per spec section 4 - ImprovementOpportunity (Input Contract).
    """

    id: str
    detector: str  # e.g., 'pylint', 'test_coverage', 'complexity'
    category: Category
    severity: Severity
    confidence: float  # 0.0-1.0
    file: str  # absolute path from workspace root
    line_range: LineRange
    description: str  # imperative, <200 chars
    context: OpportunityContext
    atomic: bool  # true if change is self-contained
    estimated_effort: EstimatedEffort

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("Confidence must be between 0.0 and 1.0")
        if len(self.description) > 200:
            raise ValueError("Description must be <200 characters")
        # Description must start with imperative verb (basic check)
        if not self.description[0].isupper():
            raise ValueError("Description must start with imperative verb (capitalized)")

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "detector": self.detector,
            "category": self.category.value,
            "severity": self.severity.value,
            "confidence": self.confidence,
            "file": self.file,
            "line_range": {"start": self.line_range.start, "end": self.line_range.end},
            "description": self.description,
            "context": self.context.to_dict(),
            "atomic": self.atomic,
            "estimated_effort": self.estimated_effort.value,
        }


@dataclass
class ExpectedChange:
    """Expected change to a file from a Copilot prompt."""

    file: str
    change_type: ChangeType
    description: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "file": self.file,
            "change_type": self.change_type.value,
            "description": self.description,
        }


@dataclass
class CopilotPrompt:
    """A prompt ready for VS Code Copilot Chat.

    Contract per spec section 4 - CopilotPrompt (Output Contract).
    """

    id: str  # SI_<category>_<timestamp>_<hash>
    opportunity_id: str
    prompt_text: str  # max 2000 tokens
    context_files: list[str]  # 1-10 files
    expected_changes: list[ExpectedChange]
    validation_plan: list[str]  # e.g., 'pytest src/module/tests'
    risk_level: RiskLevel
    requires_high_risk_approval: bool
    priority: int  # 1-10, higher = more urgent
    generated_at: str  # ISO 8601 timestamp

    def __post_init__(self) -> None:
        if not 1 <= len(self.context_files) <= 10:
            raise ValueError("context_files must have 1-10 files")
        if not 1 <= self.priority <= 10:
            raise ValueError("priority must be between 1 and 10")

    @staticmethod
    def generate_id(category: Category, opportunity_id: str) -> str:
        """Generate a unique ID for the prompt."""
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        hash_input = f"{category.value}_{timestamp}_{opportunity_id}"
        hash_suffix = hashlib.sha256(hash_input.encode()).hexdigest()[:8]
        return f"SI_{category.value}_{timestamp}_{hash_suffix}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "opportunity_id": self.opportunity_id,
            "prompt_text": self.prompt_text,
            "context_files": self.context_files,
            "expected_changes": [c.to_dict() for c in self.expected_changes],
            "validation_plan": self.validation_plan,
            "risk_level": self.risk_level.value,
            "requires_high_risk_approval": self.requires_high_risk_approval,
            "priority": self.priority,
            "generated_at": self.generated_at,
        }


@dataclass
class ValidationResult:
    """Result of a validation check."""

    status: ValidationStatus
    output: str  # first 500 chars

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "output": self.output[:500],
        }


@dataclass
class ExecutionReport:
    """Report of prompt execution.

    Contract per spec section 4 - ExecutionReport (Output).

    Per Q7 design decision: duration_seconds tracks wall-clock time from
    prompt creation to approval decision (enqueue-to-decision time).
    """

    prompt_id: str
    status: ExecutionStatus
    files_modified: list[str]
    files_expected: list[str]
    scope_match: bool
    validations: dict[str, ValidationResult]
    duration_seconds: float  # Wall-clock time from creation to decision
    error_details: str | None
    copilot_response_length: int
    user_notes: str
    created_at: datetime = field(default_factory=datetime.now)  # Enqueue time
    approved_at: datetime | None = None  # Approval time

    @property
    def approval_latency(self) -> float | None:
        """Time user took to approve (indicates prompt clarity).

        Returns:
            Latency in seconds if approved, None otherwise
        """
        if self.approved_at:
            return (self.approved_at - self.created_at).total_seconds()
        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "prompt_id": self.prompt_id,
            "status": self.status.value,
            "files_modified": self.files_modified,
            "files_expected": self.files_expected,
            "scope_match": self.scope_match,
            "validations": {k: v.to_dict() for k, v in self.validations.items()},
            "duration_seconds": self.duration_seconds,
            "error_details": self.error_details,
            "copilot_response_length": self.copilot_response_length,
            "user_notes": self.user_notes,
            "created_at": self.created_at.isoformat(),
            "approved_at": self.approved_at.isoformat() if self.approved_at else None,
            "approval_latency": self.approval_latency,
        }


@dataclass
class ApprovalDecision:
    """Record of an approval decision."""

    prompt_id: str
    decision: DecisionType
    timestamp: str  # ISO 8601
    reason_code: str | None = None
    user_feedback: str | None = None
    edited_prompt: str | None = None  # if decision was EDIT
    category: str | None = None  # Category for analytics
    detector_name: str | None = None  # Detector that created the opportunity

    def to_dict(self) -> dict[str, Any]:
        return {
            "prompt_id": self.prompt_id,
            "decision": self.decision.value,
            "timestamp": self.timestamp,
            "reason_code": self.reason_code,
            "user_feedback": self.user_feedback,
            "edited_prompt": self.edited_prompt,
            "category": self.category,
            "detector_name": self.detector_name,
        }


@dataclass
class ApprovalRequest:
    """User-facing approval request packet.

    Contract per spec section 4 - ApprovalRequest (User-Facing).
    """

    prompt: CopilotPrompt
    opportunity: ImprovementOpportunity
    historical_context: dict[str, int]  # e.g., {"approved": 3, "rejected": 1}

    def format_for_display(self) -> str:
        """Format the approval request for CLI display."""
        approval_rate = 0.0
        total = self.historical_context.get("approved", 0) + self.historical_context.get(
            "rejected", 0
        )
        if total > 0:
            approval_rate = self.historical_context.get("approved", 0) / total * 100

        risk_indicator = "⚠️ " if self.prompt.requires_high_risk_approval else ""

        lines = [
            "┌" + "─" * 53 + "┐",
            f"│ IMPROVEMENT PROMPT #{self.prompt.id:<30} │",
            "├" + "─" * 53 + "┤",
            f"│ Category: {self.opportunity.category.value:<15} Severity: {self.opportunity.severity.value:<10} │",
            f"│ Risk Level: {risk_indicator}{self.prompt.risk_level.value:<38} │",
            f"│ File: {self.opportunity.file}:{self.opportunity.line_range.start}-{self.opportunity.line_range.end}",
            "├" + "─" * 53 + "┤",
            "│ Opportunity:",
            f"│ {self.opportunity.description}",
            "│",
            "│ Context Snippet:",
        ]

        # Add code snippet (truncated)
        for snippet_line in self.opportunity.context.code_snippet.split("\n")[:10]:
            lines.append(f"│ {snippet_line[:50]}")

        lines.extend(
            [
                "├" + "─" * 53 + "┤",
                "│ Copilot Prompt:",
                f"│ {self.prompt.prompt_text[:100]}...",
                "│",
                "│ Expected Changes:",
            ]
        )

        for change in self.prompt.expected_changes:
            lines.append(f"│ - {change.file}: {change.change_type.value} ({change.description})")

        lines.extend(
            [
                "│",
                "│ Validation Plan:",
            ]
        )

        for validation in self.prompt.validation_plan:
            lines.append(f"│ - {validation}")

        lines.extend(
            [
                "│",
                "│ Historical Context:",
                f"│ Similar improvements: {self.historical_context.get('approved', 0)} approved, {self.historical_context.get('rejected', 0)} rejected",
                f"│ (Approval rate: {approval_rate:.0f}%)",
                "├" + "─" * 53 + "┤",
                "│ [APPROVE] [EDIT] [REJECT] [DEFER]                  │",
                "└" + "─" * 53 + "┘",
            ]
        )

        return "\n".join(lines)

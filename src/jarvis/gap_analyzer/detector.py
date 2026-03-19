"""Gap Detector - identifies missing capabilities."""

import json
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any


@dataclass
class CapabilityGap:
    """Represents a detected capability gap."""

    timestamp: str
    capability_name: str
    capability_description: str
    context: str  # User's request or operation
    attempted_tool: str | None = None  # Tool that failed
    error_message: str | None = None
    severity: str = "MEDIUM"  # LOW, MEDIUM, HIGH
    confidence: float = 0.8  # 0.0-1.0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)

    @staticmethod
    def from_error(
        capability_name: str,
        description: str,
        context: str,
        tool_name: str,
        error: str,
        severity: str = "HIGH",
    ) -> "CapabilityGap":
        """Create from tool error."""
        return CapabilityGap(
            timestamp=datetime.now().isoformat(),
            capability_name=capability_name,
            capability_description=description,
            context=context,
            attempted_tool=tool_name,
            error_message=error,
            severity=severity,
            confidence=0.95,  # High confidence when tool actually fails
        )


class GapDetector:
    """Detects capability gaps during execution."""

    def __init__(self):
        """Initialize the gap detector."""
        self.gaps: list[CapabilityGap] = []

    def detect_from_error(
        self,
        capability_name: str,
        description: str,
        context: str,
        tool_name: str,
        error: str,
        severity: str = "HIGH",
    ) -> CapabilityGap:
        """Detect a gap from a tool error.

        Args:
            capability_name: Name of the required capability
            description: Human-readable description
            context: What user was trying to do
            tool_name: Which tool failed
            error: Error message
            severity: Gap severity (LOW/MEDIUM/HIGH)

        Returns:
            Detected capability gap
        """
        gap = CapabilityGap.from_error(
            capability_name=capability_name,
            description=description,
            context=context,
            tool_name=tool_name,
            error=error,
            severity=severity,
        )
        self.gaps.append(gap)
        return gap

    def detect_missing_capability(
        self,
        capability_name: str,
        description: str,
        context: str,
        severity: str = "MEDIUM",
        confidence: float = 0.7,
    ) -> CapabilityGap:
        """Detect a missing capability without an error.

        Args:
            capability_name: Name of the capability
            description: What it should do
            context: Why it's needed
            severity: Gap severity
            confidence: Confidence level 0.0-1.0

        Returns:
            Detected capability gap
        """
        gap = CapabilityGap(
            timestamp=datetime.now().isoformat(),
            capability_name=capability_name,
            capability_description=description,
            context=context,
            attempted_tool=None,
            error_message=None,
            severity=severity,
            confidence=confidence,
        )
        self.gaps.append(gap)
        return gap

    def get_gaps_by_severity(self, severity: str) -> list[CapabilityGap]:
        """Get gaps of specific severity."""
        return [g for g in self.gaps if g.severity == severity]

    def get_critical_gaps(self) -> list[CapabilityGap]:
        """Get HIGH severity gaps (most critical)."""
        return self.get_gaps_by_severity("HIGH")

    def get_recent_gaps(self, limit: int = 10) -> list[CapabilityGap]:
        """Get most recent gaps."""
        return sorted(self.gaps, key=lambda g: g.timestamp, reverse=True)[:limit]

    def has_unresolved_gaps(self) -> bool:
        """Check if there are any unresolved gaps."""
        return len(self.gaps) > 0

    def export_to_json(self, filepath: str) -> None:
        """Export gaps to JSON file."""
        data = {
            "export_timestamp": datetime.now().isoformat(),
            "total_gaps": len(self.gaps),
            "gaps": [gap.to_dict() for gap in self.gaps],
        }
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def clear_gaps(self) -> None:
        """Clear all detected gaps."""
        self.gaps.clear()

    def get_summary(self) -> dict[str, Any]:
        """Get summary statistics."""
        return {
            "total_gaps": len(self.gaps),
            "critical_gaps": len(self.get_critical_gaps()),
            "high_confidence_gaps": len([g for g in self.gaps if g.confidence >= 0.9]),
            "by_severity": {
                "HIGH": len(self.get_gaps_by_severity("HIGH")),
                "MEDIUM": len(self.get_gaps_by_severity("MEDIUM")),
                "LOW": len(self.get_gaps_by_severity("LOW")),
            },
        }

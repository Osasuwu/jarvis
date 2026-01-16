"""Tool Proposer - generates tool proposals for gaps."""

import json
from dataclasses import dataclass, asdict
from typing import Any

from .detector import CapabilityGap
from .researcher import ResearchResult


@dataclass
class ToolProposal:
    """Proposed tool specification."""

    tool_name: str
    description: str
    purpose: str
    parameters: dict[str, str]  # name -> type
    return_type: str
    risk_level: str  # LOW, MEDIUM, HIGH
    example_usage: str
    implementation_hint: str
    estimated_effort: float  # days
    estimated_complexity: str  # SIMPLE, MODERATE, COMPLEX, VERY_COMPLEX

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)

    def to_markdown(self) -> str:
        """Convert to markdown format."""
        lines = [
            f"# Tool: {self.tool_name}",
            "",
            f"**Description:** {self.description}",
            f"**Purpose:** {self.purpose}",
            "",
            "## Parameters",
            "",
        ]

        for param_name, param_type in self.parameters.items():
            lines.append(f"- `{param_name}` ({param_type})")

        lines.extend(
            [
                "",
                f"## Returns",
                f"`{self.return_type}`",
                "",
                f"## Risk Level",
                f"{self.risk_level}",
                "",
                f"## Implementation Complexity",
                f"{self.estimated_complexity} (~{self.estimated_effort} days)",
                "",
                f"## Example",
                "```python",
                self.example_usage,
                "```",
                "",
                f"## Implementation Hint",
                self.implementation_hint,
            ]
        )

        return "\n".join(lines)


class ToolProposer:
    """Generates tool proposals for capability gaps."""

    def __init__(self):
        """Initialize the tool proposer."""
        self.proposals: list[ToolProposal] = []

    def propose_tool(
        self, gap: CapabilityGap, research: ResearchResult
    ) -> ToolProposal:
        """Generate a tool proposal based on gap and research.

        Args:
            gap: The capability gap
            research: Research results with possible solutions

        Returns:
            Generated tool proposal
        """
        # Map gaps to tool proposals
        proposal = self._generate_proposal(gap, research)
        self.proposals.append(proposal)
        return proposal

    def _generate_proposal(
        self, gap: CapabilityGap, research: ResearchResult
    ) -> ToolProposal:
        """Generate proposal based on gap type."""
        gap_name_lower = gap.capability_name.lower()

        if "database" in gap_name_lower:
            return ToolProposal(
                tool_name="database_query",
                description="Execute SQL queries against databases",
                purpose="Query and manipulate data in SQL databases",
                parameters={
                    "connection_string": "str",
                    "query": "str",
                    "parameters": "dict",
                },
                return_type="list[dict]",
                risk_level="HIGH",
                example_usage='tool("postgresql://user:pass@localhost/db", '
                '"SELECT * FROM users WHERE id=?", {"id": 1})',
                implementation_hint=f"Use {research.possible_solutions[0]} library. "
                "Query results as list of dictionaries.",
                estimated_effort=research.estimated_effort_days,
                estimated_complexity=research.implementation_difficulty,
            )

        elif "image" in gap_name_lower:
            return ToolProposal(
                tool_name="image_process",
                description="Process and manipulate images",
                purpose="Resize, convert, or edit image files",
                parameters={
                    "input_path": "str",
                    "operation": "str",
                    "output_path": "str",
                },
                return_type="dict",
                risk_level="MEDIUM",
                example_usage='tool("photo.jpg", "resize:640x480", "photo_small.jpg")',
                implementation_hint=f"Use {research.possible_solutions[0]} library. "
                "Support common operations: resize, rotate, convert.",
                estimated_effort=research.estimated_effort_days,
                estimated_complexity=research.implementation_difficulty,
            )

        elif "pdf" in gap_name_lower:
            return ToolProposal(
                tool_name="pdf_generate",
                description="Generate PDF documents",
                purpose="Create PDF files from templates or data",
                parameters={
                    "template_path": "str",
                    "data": "dict",
                    "output_path": "str",
                },
                return_type="str",
                risk_level="LOW",
                example_usage='tool("template.html", {"name": "John"}, "output.pdf")',
                implementation_hint=f"Use {research.possible_solutions[0]} library. "
                "Support HTML-to-PDF conversion.",
                estimated_effort=research.estimated_effort_days,
                estimated_complexity=research.implementation_difficulty,
            )

        elif "api" in gap_name_lower or "integration" in gap_name_lower:
            return ToolProposal(
                tool_name="api_call",
                description="Make HTTP API calls with authentication",
                purpose="Integrate with external APIs",
                parameters={
                    "endpoint": "str",
                    "method": "str",
                    "headers": "dict",
                    "body": "dict",
                },
                return_type="dict",
                risk_level="MEDIUM",
                example_usage='tool("https://api.example.com/data", "GET", '
                '{"Authorization": "Bearer token"})',
                implementation_hint=f"Use {research.possible_solutions[0]} library. "
                "Support JSON, form data, auth tokens.",
                estimated_effort=research.estimated_effort_days,
                estimated_complexity=research.implementation_difficulty,
            )

        else:
            # Generic tool proposal
            primary_solution = (
                research.possible_solutions[0]
                if research.possible_solutions
                else "custom implementation"
            )
            return ToolProposal(
                tool_name=gap.capability_name.lower().replace(" ", "_"),
                description=gap.capability_description,
                purpose=gap.context,
                parameters={},
                return_type="Any",
                risk_level="MEDIUM",
                example_usage="tool()",
                implementation_hint=f"Use {primary_solution}. "
                + "Implement according to gap requirements.",
                estimated_effort=research.estimated_effort_days,
                estimated_complexity=research.implementation_difficulty,
            )

    def get_proposals_by_complexity(self, complexity: str) -> list[ToolProposal]:
        """Get proposals by complexity."""
        return [p for p in self.proposals if p.estimated_complexity == complexity]

    def get_quick_wins(self) -> list[ToolProposal]:
        """Get proposals with minimal effort."""
        return [p for p in self.proposals if p.estimated_effort <= 0.5]

    def get_high_priority_proposals(self) -> list[ToolProposal]:
        """Get high-priority proposals (HIGH risk or complex gaps)."""
        return [
            p
            for p in self.proposals
            if p.risk_level == "HIGH" or "VERY_COMPLEX" in p.estimated_complexity
        ]

    def export_proposals(self, filepath: str) -> None:
        """Export proposals to JSON."""
        data = {
            "total_proposals": len(self.proposals),
            "proposals": [p.to_dict() for p in self.proposals],
        }
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def export_proposals_as_markdown(self, directory: str) -> None:
        """Export each proposal as markdown file."""
        import os

        os.makedirs(directory, exist_ok=True)

        for i, proposal in enumerate(self.proposals, 1):
            filename = f"{directory}/proposal_{i:02d}_{proposal.tool_name}.md"
            with open(filename, "w", encoding="utf-8") as f:
                f.write(proposal.to_markdown())

    def clear_proposals(self) -> None:
        """Clear all proposals."""
        self.proposals.clear()

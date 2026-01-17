"""Prompt Proposer - generates Copilot prompts for improvement opportunities.

This module transforms ImprovementOpportunity objects into CopilotPrompt
objects that are ready for human review and execution.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from jarvis.self_improvement.models import (
    Category,
    ChangeType,
    CopilotPrompt,
    EstimatedEffort,
    ExpectedChange,
    ImprovementOpportunity,
    RiskLevel,
    Severity,
)

# Maximum prompt text length in tokens (approximated as chars/4)
MAX_PROMPT_TOKENS = 2000
MAX_PROMPT_CHARS = MAX_PROMPT_TOKENS * 4

# Maximum context files per prompt
MAX_CONTEXT_FILES = 10

# Core modules that require HIGH_RISK_APPROVAL per spec
CORE_MODULES = frozenset(
    {
        "core/",
        "safety/",
        "llm/",
    }
)


class PromptProposer:
    """Generates Copilot prompts for improvement opportunities.

    Per spec section 2: Generate CopilotPrompt ready for human review.
    """

    def __init__(self, workspace_path: Path):
        """Initialize the proposer.

        Args:
            workspace_path: Root path of the workspace
        """
        self.workspace_path = workspace_path
        self.prompts: list[CopilotPrompt] = []

    def propose(
        self,
        opportunity: ImprovementOpportunity,
        related_files: list[str] | None = None,
        best_practices: list[str] | None = None,
    ) -> CopilotPrompt | None:
        """Generate a Copilot prompt for an opportunity.

        Per spec section 4:
        - DO generate one CopilotPrompt per approved ImprovementOpportunity
        - DO validate prompt length <2000 tokens; split opportunities exceeding this limit
        - DO NOT generate prompts >2000 tokens; defer oversized opportunities

        Args:
            opportunity: The improvement opportunity
            related_files: Additional files for context
            best_practices: Best practices from research to include in prompt

        Returns:
            Generated CopilotPrompt or None if opportunity cannot be handled
        """
        # Validate atomicity per spec
        if not opportunity.atomic:
            # Per spec: DO NOT create opportunities spanning unrelated concerns
            return None

        # Build context files list
        context_files = self._gather_context_files(opportunity, related_files)

        # Generate the prompt text (M4 fix: include best practices)
        prompt_text = self._generate_prompt_text(opportunity, best_practices)

        # Check prompt length
        if len(prompt_text) > MAX_PROMPT_CHARS:
            # Per spec: DO NOT generate prompts >2000 tokens; defer
            return None

        # Determine risk level
        risk_level = self._assess_risk_level(opportunity)

        # Build expected changes
        expected_changes = self._determine_expected_changes(opportunity)

        # Build validation plan
        validation_plan = self._create_validation_plan(opportunity)

        # Calculate priority
        priority = self._calculate_priority(opportunity)

        # Generate the prompt
        prompt = CopilotPrompt(
            id=CopilotPrompt.generate_id(opportunity.category, opportunity.id),
            opportunity_id=opportunity.id,
            prompt_text=prompt_text,
            context_files=context_files,
            expected_changes=expected_changes,
            validation_plan=validation_plan,
            risk_level=risk_level,
            requires_high_risk_approval=risk_level in (RiskLevel.HIGH, RiskLevel.CRITICAL),
            priority=priority,
            generated_at=datetime.now().isoformat(),
        )

        self.prompts.append(prompt)
        return prompt

    def _gather_context_files(
        self,
        opportunity: ImprovementOpportunity,
        related_files: list[str] | None,
    ) -> list[str]:
        """Gather context files for the prompt.

        Per spec: DO mark required context files: list all files Copilot must consider (max 10 files)
        """
        files: set[str] = {opportunity.file}

        # Add affected files from opportunity context
        files.update(opportunity.context.affected_files)

        # Add related files if provided
        if related_files:
            files.update(related_files)

        # Limit to MAX_CONTEXT_FILES
        file_list = list(files)[:MAX_CONTEXT_FILES]

        # Per spec: context_files must have 1-10 files
        if not file_list:
            file_list = [opportunity.file]

        return file_list

    def _generate_prompt_text(
        self,
        opportunity: ImprovementOpportunity,
        best_practices: list[str] | None = None,
    ) -> str:
        """Generate the actual prompt text for Copilot.

        Per spec:
        - DO include immediate context: show affected code snippet in prompt preamble
        - DO state expected changes explicitly
        - DO reference file paths and line numbers consistently
        - DO NOT assume Copilot has domain context; always include "why"

        Args:
            opportunity: The improvement opportunity
            best_practices: Optional best practices from research (M4 integration)
        """
        parts: list[str] = []

        # Preamble with context
        parts.append("## Context\n")
        parts.append(f"File: `{opportunity.file}` (lines {opportunity.line_range.start}-{opportunity.line_range.end})\n")
        parts.append(f"Category: {opportunity.category.value}\n")
        parts.append(f"Detected by: {opportunity.detector}\n")
        parts.append("\n")

        # Code snippet
        parts.append("## Current Code\n")
        parts.append("```python\n")
        # Limit snippet to 50 lines per spec
        snippet_lines = opportunity.context.code_snippet.split("\n")[:50]
        parts.append("\n".join(snippet_lines))
        parts.append("\n```\n\n")

        # Task description
        parts.append("## Task\n")
        parts.append(f"{opportunity.description}\n\n")

        # Why (rationale)
        parts.append("## Why This Change Is Needed\n")
        parts.append(self._generate_rationale(opportunity))
        parts.append("\n\n")

        # Best Practices (M4 fix: inject research findings)
        if best_practices:
            parts.append("## Best Practices & Patterns\n")
            for practice in best_practices[:3]:  # Limit to 3 to avoid prompt bloat
                parts.append(f"- {practice}\n")
            parts.append("\n")

        # Expected outcome
        parts.append("## Expected Outcome\n")
        parts.append(self._generate_expected_outcome(opportunity))
        parts.append("\n\n")

        # Constraints
        parts.append("## Constraints\n")
        parts.append("- Preserve existing functionality and public interfaces\n")
        parts.append("- Follow existing code style and patterns in this project\n")
        parts.append("- Keep changes minimal and focused on the specific issue\n")
        parts.append("- Ensure all existing tests continue to pass\n")

        return "".join(parts)

    def _generate_rationale(self, opportunity: ImprovementOpportunity) -> str:
        """Generate the rationale section based on category."""
        rationales = {
            Category.BUG: "This code contains a potential bug that could cause incorrect behavior or crashes at runtime.",
            Category.REFACTOR: "This code has maintainability issues that make it harder to understand, modify, or extend.",
            Category.TEST: "The test coverage for this code is insufficient, increasing the risk of undetected regressions.",
            Category.DOCS: "This code lacks proper documentation, making it difficult for developers to understand its purpose and usage.",
            Category.SECURITY: "This code has potential security vulnerabilities that could be exploited.",
            Category.PERFORMANCE: "This code has performance issues that could impact application responsiveness or resource usage.",
        }

        base_rationale = rationales.get(opportunity.category, "This code needs improvement.")

        # Add detector-specific context
        metrics = opportunity.context.metrics
        if metrics:
            if "cyclomatic_complexity" in metrics:
                base_rationale += f" The cyclomatic complexity is {metrics['cyclomatic_complexity']}, which exceeds the recommended maximum of 10."
            if "pylint_symbol" in metrics:
                base_rationale += f" Pylint reported: {metrics['pylint_symbol']}."

        return base_rationale

    def _generate_expected_outcome(self, opportunity: ImprovementOpportunity) -> str:
        """Generate the expected outcome description."""
        outcomes = {
            Category.BUG: "The bug will be fixed and the code will behave correctly in all cases.",
            Category.REFACTOR: "The code will be cleaner, more readable, and easier to maintain.",
            Category.TEST: "Test coverage will be improved with meaningful test cases.",
            Category.DOCS: "The code will have clear documentation explaining its purpose and usage.",
            Category.SECURITY: "The security vulnerability will be eliminated.",
            Category.PERFORMANCE: "The code will execute more efficiently.",
        }

        return outcomes.get(opportunity.category, "The code quality will be improved.")

    def _assess_risk_level(self, opportunity: ImprovementOpportunity) -> RiskLevel:
        """Assess the risk level of the change.

        Per spec:
        - DO include risk assessment: mark opportunities requiring HIGH_RISK_APPROVAL
          if they modify core modules, remove functionality, or affect 5+ files
        """
        # Check if file is in core modules
        for core_path in CORE_MODULES:
            if opportunity.file.startswith(core_path):
                return RiskLevel.HIGH

        # Check number of affected files
        if len(opportunity.context.affected_files) >= 5:
            return RiskLevel.HIGH

        # Map severity to risk
        severity_risk_map = {
            Severity.CRITICAL: RiskLevel.HIGH,
            Severity.HIGH: RiskLevel.MEDIUM,
            Severity.MEDIUM: RiskLevel.LOW,
            Severity.LOW: RiskLevel.LOW,
        }

        return severity_risk_map.get(opportunity.severity, RiskLevel.LOW)

    def _determine_expected_changes(
        self, opportunity: ImprovementOpportunity
    ) -> list[ExpectedChange]:
        """Determine expected file changes.

        Per spec: DO state expected changes explicitly.
        """
        changes: list[ExpectedChange] = []

        # Primary file change
        change_type = ChangeType.MODIFY
        description = self._describe_change(opportunity)

        changes.append(
            ExpectedChange(
                file=opportunity.file,
                change_type=change_type,
                description=description,
            )
        )

        # Add test file if this is a test-related opportunity
        if opportunity.category == Category.TEST:
            test_file = self._infer_test_file(opportunity.file)
            if test_file:
                changes.append(
                    ExpectedChange(
                        file=test_file,
                        change_type=ChangeType.MODIFY,
                        description="Add or update test cases",
                    )
                )

        return changes

    def _describe_change(self, opportunity: ImprovementOpportunity) -> str:
        """Generate a description of the expected change."""
        descriptions = {
            Category.BUG: "Fix the identified bug",
            Category.REFACTOR: "Refactor for improved maintainability",
            Category.TEST: "Add test coverage",
            Category.DOCS: "Add or update documentation",
            Category.SECURITY: "Fix security vulnerability",
            Category.PERFORMANCE: "Optimize for better performance",
        }
        return descriptions.get(opportunity.category, "Improve code quality")

    def _infer_test_file(self, source_file: str) -> str | None:
        """Infer the test file path for a source file."""
        # Simple heuristic: src/module/file.py -> tests/module/test_file.py
        if source_file.startswith("src/"):
            test_path = source_file.replace("src/", "tests/")
            parts = test_path.rsplit("/", 1)
            if len(parts) == 2:
                return f"{parts[0]}/test_{parts[1]}"
        return None

    def _create_validation_plan(self, opportunity: ImprovementOpportunity) -> list[str]:
        """Create the validation plan for after Copilot changes.

        Per spec: DO include validation plan: specify which tests/linters must pass post-execution.
        """
        plan: list[str] = []

        # Always run pytest for the affected module
        plan.append("pytest tests/ -v --tb=short")

        # Run pylint on changed file
        plan.append(f"pylint {opportunity.file} --disable=C0114,C0115,C0116")

        # Category-specific validations
        if opportunity.category == Category.SECURITY:
            plan.append(f"bandit -r {opportunity.file}")

        if opportunity.category == Category.REFACTOR:
            plan.append(f"radon cc {opportunity.file} -a")

        return plan

    def _calculate_priority(self, opportunity: ImprovementOpportunity) -> int:
        """Calculate priority (1-10, higher = more urgent).

        Per spec: DO preserve order: prioritize by severity.
        """
        severity_priority = {
            Severity.CRITICAL: 10,
            Severity.HIGH: 8,
            Severity.MEDIUM: 5,
            Severity.LOW: 2,
        }

        effort_adjustment = {
            EstimatedEffort.TRIVIAL: 1,
            EstimatedEffort.SMALL: 0,
            EstimatedEffort.MEDIUM: -1,
            EstimatedEffort.LARGE: -2,
        }

        base = severity_priority.get(opportunity.severity, 5)
        adjustment = effort_adjustment.get(opportunity.estimated_effort, 0)

        return max(1, min(10, base + adjustment))

    def batch_prompts(
        self,
        prompts: list[CopilotPrompt],
        max_batch_size: int = 5,
    ) -> list[list[CopilotPrompt]]:
        """Batch prompts for approval.

        Per spec:
        - DO group related opportunities by category or file when atomicity is preserved
        - DO enforce per-cycle batch limit: max 5 independent prompts per approval cycle
        - DO NOT execute partial batches (all-or-nothing within a batch)

        Args:
            prompts: List of prompts to batch
            max_batch_size: Maximum prompts per batch

        Returns:
            List of prompt batches
        """
        if not prompts:
            return []

        # Sort by priority (highest first)
        sorted_prompts = sorted(prompts, key=lambda p: p.priority, reverse=True)

        # Group by file for related batching
        by_file: dict[str, list[CopilotPrompt]] = {}
        for prompt in sorted_prompts:
            # Use first context file as grouping key
            key = prompt.context_files[0] if prompt.context_files else "other"
            by_file.setdefault(key, []).append(prompt)

        batches: list[list[CopilotPrompt]] = []
        current_batch: list[CopilotPrompt] = []

        for file_prompts in by_file.values():
            for prompt in file_prompts:
                if len(current_batch) >= max_batch_size:
                    batches.append(current_batch)
                    current_batch = []
                current_batch.append(prompt)

        if current_batch:
            batches.append(current_batch)

        return batches

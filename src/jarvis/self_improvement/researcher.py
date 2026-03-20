"""Researcher - researches best practices and patterns for improvements.

This module provides research capabilities for improvement opportunities,
finding best practices and implementation patterns.
"""

from __future__ import annotations

import asyncio
from dataclasses import asdict, dataclass
from typing import Any

from jarvis.self_improvement.models import Category, ImprovementOpportunity


@dataclass
class ResearchResult:
    """Result of researching an improvement opportunity."""

    opportunity_id: str
    best_practices: list[str]
    code_patterns: list[str]
    external_references: list[dict[str, str]]  # {"url": ..., "description": ...}
    implementation_notes: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ImprovementResearcher:
    """Researches best practices for improvement opportunities.

    Per spec section 2: Researches best practices, patterns (optional).
    """

    def __init__(self):
        """Initialize the researcher."""
        self.cache: dict[str, ResearchResult] = {}

    async def research(self, opportunity: ImprovementOpportunity) -> ResearchResult:
        """Research best practices for an improvement opportunity.

        Args:
            opportunity: The opportunity to research

        Returns:
            Research results with best practices and patterns
        """
        # Check cache first
        cache_key = f"{opportunity.category.value}_{opportunity.detector}"
        if cache_key in self.cache:
            result = self.cache[cache_key]
            # Update the opportunity_id for this specific request
            return ResearchResult(
                opportunity_id=opportunity.id,
                best_practices=result.best_practices,
                code_patterns=result.code_patterns,
                external_references=result.external_references,
                implementation_notes=result.implementation_notes,
            )

        # Perform research based on category
        result = await self._research_category(opportunity)
        self.cache[cache_key] = result
        return result

    async def _research_category(self, opportunity: ImprovementOpportunity) -> ResearchResult:
        """Research based on opportunity category."""
        # Simulate async research
        await asyncio.sleep(0.01)

        research_data = self._get_category_research(opportunity.category)

        return ResearchResult(
            opportunity_id=opportunity.id,
            best_practices=research_data["best_practices"],
            code_patterns=research_data["code_patterns"],
            external_references=research_data["external_references"],
            implementation_notes=research_data["implementation_notes"],
        )

    def _get_category_research(self, category: Category) -> dict[str, Any]:
        """Get pre-built research data for a category.

        Note: Future enhancement could use web_fetch tool for real-time research.
        See design_questions.md - Future Enhancements section.
        """
        research_db: dict[Category, dict[str, Any]] = {
            Category.BUG: {
                "best_practices": [
                    "Add defensive null/boundary checks",
                    "Handle edge cases explicitly",
                    "Add logging for debugging",
                    "Write regression tests for the fix",
                ],
                "code_patterns": [
                    "Early return pattern for validation",
                    "Guard clauses at function entry",
                    "Try-except with specific exceptions",
                ],
                "external_references": [
                    {
                        "url": "https://docs.python.org/3/tutorial/errors.html",
                        "description": "Python error handling tutorial",
                    },
                ],
                "implementation_notes": "Focus on fixing the root cause, not just the symptom. Add tests to prevent regression.",
            },
            Category.REFACTOR: {
                "best_practices": [
                    "Extract methods for repeated code",
                    "Use meaningful variable names",
                    "Keep functions small and focused",
                    "Apply Single Responsibility Principle",
                ],
                "code_patterns": [
                    "Extract Method refactoring",
                    "Replace Magic Numbers with Constants",
                    "Introduce Parameter Object",
                    "Replace Conditional with Polymorphism",
                ],
                "external_references": [
                    {
                        "url": "https://refactoring.guru/refactoring",
                        "description": "Refactoring techniques catalog",
                    },
                ],
                "implementation_notes": "Refactor in small steps, running tests after each change. Preserve existing behavior.",
            },
            Category.TEST: {
                "best_practices": [
                    "Test one thing per test",
                    "Use descriptive test names",
                    "Follow Arrange-Act-Assert pattern",
                    "Test edge cases and error conditions",
                ],
                "code_patterns": [
                    "pytest fixtures for setup",
                    "parametrized tests for multiple inputs",
                    "Mock external dependencies",
                ],
                "external_references": [
                    {
                        "url": "https://docs.pytest.org/en/latest/",
                        "description": "pytest documentation",
                    },
                ],
                "implementation_notes": "Focus on testing behavior, not implementation. Aim for meaningful coverage, not 100%.",
            },
            Category.DOCS: {
                "best_practices": [
                    "Use Google-style or NumPy-style docstrings",
                    "Document parameters and return values",
                    "Include usage examples",
                    "Keep docs close to code",
                ],
                "code_patterns": [
                    "Module-level docstrings",
                    "Class docstrings with attributes",
                    "Function docstrings with Args/Returns",
                ],
                "external_references": [
                    {
                        "url": "https://google.github.io/styleguide/pyguide.html#38-comments-and-docstrings",
                        "description": "Google Python Style Guide - Docstrings",
                    },
                ],
                "implementation_notes": "Document the 'why', not just the 'what'. Keep documentation up to date with code changes.",
            },
            Category.SECURITY: {
                "best_practices": [
                    "Validate and sanitize all inputs",
                    "Use parameterized queries",
                    "Avoid hardcoded credentials",
                    "Follow principle of least privilege",
                ],
                "code_patterns": [
                    "Input validation at boundaries",
                    "Secrets management with environment variables",
                    "Safe deserialization patterns",
                ],
                "external_references": [
                    {
                        "url": "https://owasp.org/www-project-top-ten/",
                        "description": "OWASP Top 10 security risks",
                    },
                ],
                "implementation_notes": "Security fixes should be thorough. Consider all attack vectors, not just the reported one.",
            },
            Category.PERFORMANCE: {
                "best_practices": [
                    "Profile before optimizing",
                    "Use appropriate data structures",
                    "Cache expensive computations",
                    "Avoid premature optimization",
                ],
                "code_patterns": [
                    "Generator expressions for memory efficiency",
                    "functools.lru_cache for memoization",
                    "Lazy loading patterns",
                ],
                "external_references": [
                    {
                        "url": "https://docs.python.org/3/library/profile.html",
                        "description": "Python profiling documentation",
                    },
                ],
                "implementation_notes": "Measure performance before and after. Ensure correctness is not sacrificed for speed.",
            },
        }

        return research_db.get(
            category,
            {
                "best_practices": ["Follow project conventions"],
                "code_patterns": [],
                "external_references": [],
                "implementation_notes": "Apply standard best practices for this type of change.",
            },
        )

    async def research_batch(
        self, opportunities: list[ImprovementOpportunity]
    ) -> dict[str, ResearchResult]:
        """Research multiple opportunities in parallel.

        Args:
            opportunities: List of opportunities to research

        Returns:
            Dict mapping opportunity IDs to research results
        """
        tasks = [self.research(opp) for opp in opportunities]
        results = await asyncio.gather(*tasks)
        return {opp.id: result for opp, result in zip(opportunities, results)}

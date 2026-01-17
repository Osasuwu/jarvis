"""Improvement Detector - analyzes workspace for improvement opportunities.

This module identifies improvement opportunities in the codebase through
static analysis, test coverage checks, and other analysis methods.
"""

from __future__ import annotations

import hashlib
import logging
import subprocess
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from jarvis.self_improvement.models import (
    Category,
    EstimatedEffort,
    ImprovementOpportunity,
    LineRange,
    OpportunityContext,
    Severity,
)

logger = logging.getLogger(__name__)

# Protected paths that must never be analyzed per spec section 4 (DO NOT)
PROTECTED_PATHS = frozenset(
    {
        "self_improvement/",
        "safety/",
        "core/orchestrator.py",
    }
)


@dataclass
class DetectorConfig:
    """Configuration for the improvement detector."""

    workspace_path: Path
    excluded_paths: set[str] | None = None
    min_confidence: float = 0.5
    enabled_categories: set[Category] | None = None

    def __post_init__(self) -> None:
        if self.excluded_paths is None:
            self.excluded_paths = set()
        # Always add protected paths
        self.excluded_paths = self.excluded_paths.union(PROTECTED_PATHS)

        if self.enabled_categories is None:
            self.enabled_categories = set(Category)


class BaseAnalyzer(ABC):
    """Abstract base class for code analyzers."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Return the analyzer name (e.g., 'pylint', 'test_coverage')."""
        pass

    @property
    @abstractmethod
    def supported_categories(self) -> set[Category]:
        """Return the categories this analyzer can detect."""
        pass

    @abstractmethod
    async def analyze(
        self, workspace_path: Path, excluded_paths: set[str]
    ) -> list[ImprovementOpportunity]:
        """Run analysis and return opportunities.

        Args:
            workspace_path: Root path of the workspace
            excluded_paths: Paths to exclude from analysis

        Returns:
            List of detected improvement opportunities
        """
        pass

    def _is_path_excluded(self, file_path: Path, workspace_path: Path, excluded: set[str]) -> bool:
        """Check if a path should be excluded from analysis."""
        try:
            rel_path = file_path.relative_to(workspace_path)
            rel_str = str(rel_path).replace("\\", "/")
            return any(rel_str.startswith(excl) or excl in rel_str for excl in excluded)
        except ValueError:
            # Path is not relative to workspace
            return True

    def _generate_opportunity_id(self, detector: str, file: str, line_start: int) -> str:
        """Generate a unique, immutable ID for an opportunity."""
        hash_input = f"{detector}_{file}_{line_start}_{datetime.now().isoformat()}"
        return hashlib.sha256(hash_input.encode()).hexdigest()[:16]


class PylintAnalyzer(BaseAnalyzer):
    """Analyzer using pylint for code quality checks."""

    @property
    def name(self) -> str:
        return "pylint"

    @property
    def supported_categories(self) -> set[Category]:
        return {Category.BUG, Category.REFACTOR}

    async def analyze(
        self, workspace_path: Path, excluded_paths: set[str]
    ) -> list[ImprovementOpportunity]:
        """Run pylint analysis on the workspace."""
        opportunities: list[ImprovementOpportunity] = []

        # Find Python files
        python_files = list(workspace_path.rglob("*.py"))

        for py_file in python_files:
            if self._is_path_excluded(py_file, workspace_path, excluded_paths):
                continue

            try:
                result = subprocess.run(
                    [
                        "pylint",
                        str(py_file),
                        "--output-format=json",
                        "--disable=C0114,C0115,C0116",  # Disable docstring warnings for now
                    ],
                    capture_output=True,
                    text=True,
                    timeout=30,
                )

                if result.stdout:
                    import json

                    issues = json.loads(result.stdout)
                    for issue in issues:
                        opp = self._issue_to_opportunity(issue, py_file, workspace_path)
                        if opp:
                            opportunities.append(opp)

            except subprocess.TimeoutExpired:
                logger.warning(f"Pylint analysis timed out for {py_file}")
            except FileNotFoundError:
                logger.debug("Pylint not installed, skipping pylint analysis")
            except json.JSONDecodeError as e:
                logger.warning(f"Failed to parse pylint output for {py_file}: {e}")
            except Exception as e:  # noqa: BLE001
                logger.error(f"Unexpected error in pylint analysis for {py_file}: {e}")

        return opportunities

    def _issue_to_opportunity(
        self, issue: dict[str, Any], file_path: Path, workspace_path: Path
    ) -> ImprovementOpportunity | None:
        """Convert a pylint issue to an ImprovementOpportunity."""
        message_type = issue.get("type", "")
        line = issue.get("line", 1)
        message = issue.get("message", "")
        symbol = issue.get("symbol", "")

        # Map pylint types to our categories and severity
        category_map = {
            "error": (Category.BUG, Severity.HIGH),
            "warning": (Category.REFACTOR, Severity.MEDIUM),
            "convention": (Category.REFACTOR, Severity.LOW),
            "refactor": (Category.REFACTOR, Severity.MEDIUM),
        }

        if message_type not in category_map:
            return None

        category, severity = category_map[message_type]

        # Read context snippet
        try:
            with open(file_path, encoding="utf-8") as f:
                lines = f.readlines()
                start_line = max(1, line - 10)
                end_line = min(len(lines), line + 10)
                snippet = "".join(lines[start_line - 1 : end_line])
        except OSError:
            snippet = ""

        rel_path = str(file_path.relative_to(workspace_path)).replace("\\", "/")

        # Create description starting with imperative verb
        description = f"Fix {symbol}: {message}"
        if len(description) > 200:
            description = description[:197] + "..."

        return ImprovementOpportunity(
            id=self._generate_opportunity_id(self.name, rel_path, line),
            detector=self.name,
            category=category,
            severity=severity,
            confidence=0.85,  # Pylint has high confidence
            file=rel_path,
            line_range=LineRange(start=line, end=line),
            description=description,
            context=OpportunityContext(
                code_snippet=snippet,
                affected_files=[rel_path],
                metrics={"pylint_symbol": symbol, "pylint_type": message_type},
            ),
            atomic=True,
            estimated_effort=EstimatedEffort.TRIVIAL,
        )


class ComplexityAnalyzer(BaseAnalyzer):
    """Analyzer for code complexity metrics using radon."""

    @property
    def name(self) -> str:
        return "complexity"

    @property
    def supported_categories(self) -> set[Category]:
        return {Category.REFACTOR}

    async def analyze(
        self, workspace_path: Path, excluded_paths: set[str]
    ) -> list[ImprovementOpportunity]:
        """Run complexity analysis on the workspace."""
        opportunities: list[ImprovementOpportunity] = []

        python_files = list(workspace_path.rglob("*.py"))

        for py_file in python_files:
            if self._is_path_excluded(py_file, workspace_path, excluded_paths):
                continue

            try:
                result = subprocess.run(
                    ["radon", "cc", str(py_file), "-j"],  # JSON output
                    capture_output=True,
                    text=True,
                    timeout=30,
                )

                if result.stdout:
                    import json

                    data = json.loads(result.stdout)
                    for _file_path, functions in data.items():
                        for func in functions:
                            if func.get("complexity", 0) > 10:  # High complexity threshold
                                opp = self._complexity_to_opportunity(
                                    func, py_file, workspace_path
                                )
                                if opp:
                                    opportunities.append(opp)

            except subprocess.TimeoutExpired:
                logger.warning(f"Radon analysis timed out for {py_file}")
            except FileNotFoundError:
                logger.debug("Radon not installed, skipping complexity analysis")
            except Exception as e:  # noqa: BLE001
                logger.error(f"Unexpected error in complexity analysis for {py_file}: {e}")

        return opportunities

    def _complexity_to_opportunity(
        self, func: dict[str, Any], file_path: Path, workspace_path: Path
    ) -> ImprovementOpportunity | None:
        """Convert complexity data to an ImprovementOpportunity."""
        complexity = func.get("complexity", 0)
        name = func.get("name", "unknown")
        lineno = func.get("lineno", 1)
        endline = func.get("endline", lineno)

        # Map complexity to severity
        if complexity > 20:
            severity = Severity.HIGH
        elif complexity > 15:
            severity = Severity.MEDIUM
        else:
            severity = Severity.LOW

        # Read context snippet
        try:
            with open(file_path, encoding="utf-8") as f:
                lines = f.readlines()
                start = max(0, lineno - 1)
                end = min(len(lines), endline + 5)
                snippet = "".join(lines[start:end])
        except OSError:
            snippet = ""

        rel_path = str(file_path.relative_to(workspace_path)).replace("\\", "/")

        return ImprovementOpportunity(
            id=self._generate_opportunity_id(self.name, rel_path, lineno),
            detector=self.name,
            category=Category.REFACTOR,
            severity=severity,
            confidence=0.9,
            file=rel_path,
            line_range=LineRange(start=lineno, end=endline),
            description=f"Refactor {name} to reduce cyclomatic complexity from {complexity}",
            context=OpportunityContext(
                code_snippet=snippet,
                affected_files=[rel_path],
                metrics={"cyclomatic_complexity": complexity},
            ),
            atomic=endline - lineno < 50,
            estimated_effort=(
                EstimatedEffort.SMALL if complexity < 15 else EstimatedEffort.MEDIUM
            ),
        )


class ImprovementDetector:
    """Main detector that orchestrates multiple analyzers.

    Per spec Phase 1: Choose detectors based on configured categories,
    recent rejection patterns, and risk level.
    """

    def __init__(self, config: DetectorConfig):
        """Initialize the improvement detector.

        Args:
            config: Detector configuration
        """
        self.config = config
        self.analyzers: list[BaseAnalyzer] = []
        self._register_default_analyzers()

    def _register_default_analyzers(self) -> None:
        """Register default analyzers.

        Note: See design_questions.md Q6 for future configuration strategy.
        """
        self.analyzers.append(PylintAnalyzer())
        self.analyzers.append(ComplexityAnalyzer())

    def register_analyzer(self, analyzer: BaseAnalyzer) -> None:
        """Register a custom analyzer.

        Args:
            analyzer: Analyzer instance to register
        """
        self.analyzers.append(analyzer)

    async def detect(
        self, skip_detectors: set[str] | None = None
    ) -> list[ImprovementOpportunity]:
        """Run all eligible analyzers and collect opportunities.

        Per spec Phase 1: Skip detectors whose last run produced only
        rejected items unless cooldown expired.

        Args:
            skip_detectors: Set of detector names to skip

        Returns:
            List of detected improvement opportunities
        """
        skip_detectors = skip_detectors or set()
        all_opportunities: list[ImprovementOpportunity] = []

        for analyzer in self.analyzers:
            # Check if analyzer should be skipped
            if analyzer.name in skip_detectors:
                continue

            # Check if analyzer supports enabled categories
            if not analyzer.supported_categories.intersection(self.config.enabled_categories or set()):
                continue

            # Run analyzer
            opportunities = await analyzer.analyze(
                self.config.workspace_path, self.config.excluded_paths or set()
            )

            # Filter by minimum confidence (per spec: DO NOT include opportunities with confidence <0.5)
            opportunities = [
                opp
                for opp in opportunities
                if opp.confidence >= self.config.min_confidence
                or opp.severity == Severity.CRITICAL
            ]

            all_opportunities.extend(opportunities)

        # Deduplicate and vet opportunities (per spec Phase 2)
        vetted = self._vet_opportunities(all_opportunities)

        return vetted

    def _vet_opportunities(
        self, opportunities: list[ImprovementOpportunity]
    ) -> list[ImprovementOpportunity]:
        """Vet and deduplicate opportunities.

        Per spec Phase 2:
        - Deduplicate and merge overlapping findings
        - Discard items lacking precise file+line ranges or actionable descriptions
        """
        if not opportunities:
            return []

        # Group by file for overlap detection
        by_file: dict[str, list[ImprovementOpportunity]] = {}
        for opp in opportunities:
            by_file.setdefault(opp.file, []).append(opp)

        vetted: list[ImprovementOpportunity] = []

        for file_opps in by_file.values():
            # Sort by start line
            file_opps.sort(key=lambda o: o.line_range.start)

            # Deduplicate overlapping opportunities (keep higher severity)
            seen_ranges: list[ImprovementOpportunity] = []

            for opp in file_opps:
                is_duplicate = False
                for existing in seen_ranges:
                    # Per spec: merge only if line ranges overlap >80%
                    if opp.line_range.overlaps(existing.line_range, threshold=0.8):
                        is_duplicate = True
                        # Keep higher severity one
                        severity_order = [Severity.LOW, Severity.MEDIUM, Severity.HIGH, Severity.CRITICAL]
                        if severity_order.index(opp.severity) > severity_order.index(existing.severity):
                            seen_ranges.remove(existing)
                            seen_ranges.append(opp)
                        break

                if not is_duplicate:
                    seen_ranges.append(opp)

            vetted.extend(seen_ranges)

        return vetted

    def score_opportunity(self, opportunity: ImprovementOpportunity, approval_rate: float) -> float:
        """Score an opportunity for prioritization.

        Per spec Phase 2: Score using severity, confidence, impact surface,
        and historical approval rate.

        Args:
            opportunity: The opportunity to score
            approval_rate: Historical approval rate for this category (0.0-1.0)

        Returns:
            Score value (higher = more important)
        """
        severity_scores = {
            Severity.CRITICAL: 100,
            Severity.HIGH: 75,
            Severity.MEDIUM: 50,
            Severity.LOW: 25,
        }

        base_score = severity_scores.get(opportunity.severity, 25)
        confidence_factor = opportunity.confidence
        approval_factor = 0.5 + (approval_rate * 0.5)  # Range 0.5 to 1.0

        # Impact surface factor
        affected_files = len(opportunity.context.affected_files)
        impact_factor = 1.0 + (0.1 * min(affected_files, 3))  # Cap at 3 files

        return base_score * confidence_factor * approval_factor * impact_factor

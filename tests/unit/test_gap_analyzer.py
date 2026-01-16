"""Unit tests for Gap Analyzer module."""

import asyncio
import json
import tempfile
import unittest
from pathlib import Path

from jarvis.gap_analyzer import GapDetector, GapResearcher, ToolProposer
from jarvis.gap_analyzer.detector import CapabilityGap


class TestGapDetector(unittest.TestCase):
    """Tests for GapDetector."""

    def setUp(self):
        """Set up test fixtures."""
        self.detector = GapDetector()

    def test_detect_from_error(self):
        """Test detecting gap from error."""
        gap = self.detector.detect_from_error(
            capability_name="database_query",
            description="Execute SQL queries",
            context="User tried to query PostgreSQL",
            tool_name="shell_execute",
            error="psycopg2 not found",
            severity="HIGH",
        )

        self.assertEqual(gap.capability_name, "database_query")
        self.assertEqual(gap.attempted_tool, "shell_execute")
        self.assertEqual(gap.severity, "HIGH")
        self.assertEqual(gap.confidence, 0.95)
        self.assertIn("psycopg2", gap.error_message)

    def test_detect_missing_capability(self):
        """Test detecting missing capability."""
        gap = self.detector.detect_missing_capability(
            capability_name="image_processing",
            description="Process and resize images",
            context="User requested image transformation",
            severity="MEDIUM",
            confidence=0.8,
        )

        self.assertEqual(gap.capability_name, "image_processing")
        self.assertIsNone(gap.attempted_tool)
        self.assertIsNone(gap.error_message)
        self.assertEqual(gap.confidence, 0.8)

    def test_get_gaps_by_severity(self):
        """Test filtering gaps by severity."""
        self.detector.detect_from_error(
            "db_query",
            "Query database",
            "User query",
            "shell",
            "Error",
            severity="HIGH",
        )
        self.detector.detect_missing_capability(
            "image_proc", "Image processing", "User request", severity="MEDIUM"
        )
        self.detector.detect_missing_capability(
            "pdf_gen", "PDF generation", "User request", severity="LOW"
        )

        high = self.detector.get_gaps_by_severity("HIGH")
        medium = self.detector.get_gaps_by_severity("MEDIUM")
        low = self.detector.get_gaps_by_severity("LOW")

        self.assertEqual(len(high), 1)
        self.assertEqual(len(medium), 1)
        self.assertEqual(len(low), 1)

    def test_get_critical_gaps(self):
        """Test getting critical gaps."""
        self.detector.detect_from_error(
            "gap1", "Desc1", "Context1", "tool1", "Error1", severity="HIGH"
        )
        self.detector.detect_from_error(
            "gap2", "Desc2", "Context2", "tool2", "Error2", severity="HIGH"
        )
        self.detector.detect_missing_capability(
            "gap3", "Desc3", "Context3", severity="LOW"
        )

        critical = self.detector.get_critical_gaps()
        self.assertEqual(len(critical), 2)
        self.assertTrue(all(g.severity == "HIGH" for g in critical))

    def test_get_recent_gaps(self):
        """Test getting recent gaps with limit."""
        for i in range(5):
            self.detector.detect_missing_capability(
                f"gap_{i}", f"Desc {i}", f"Context {i}"
            )

        recent = self.detector.get_recent_gaps(limit=3)
        self.assertEqual(len(recent), 3)

    def test_has_unresolved_gaps(self):
        """Test checking for unresolved gaps."""
        self.assertFalse(self.detector.has_unresolved_gaps())

        self.detector.detect_missing_capability(
            "gap1", "Desc1", "Context1"
        )
        self.assertTrue(self.detector.has_unresolved_gaps())

    def test_export_to_json(self):
        """Test exporting gaps to JSON."""
        self.detector.detect_from_error(
            "db_query", "Query DB", "User request", "shell", "Error", "HIGH"
        )
        self.detector.detect_missing_capability(
            "image_proc", "Process images", "User request", "MEDIUM"
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = Path(tmpdir) / "gaps.json"
            self.detector.export_to_json(str(filepath))

            with open(filepath) as f:
                data = json.load(f)

            self.assertEqual(data["total_gaps"], 2)
            self.assertEqual(len(data["gaps"]), 2)

    def test_clear_gaps(self):
        """Test clearing gaps."""
        self.detector.detect_missing_capability(
            "gap1", "Desc1", "Context1"
        )
        self.assertEqual(len(self.detector.gaps), 1)

        self.detector.clear_gaps()
        self.assertEqual(len(self.detector.gaps), 0)

    def test_get_summary(self):
        """Test getting summary statistics."""
        self.detector.detect_from_error(
            "gap1", "Desc1", "Context1", "tool1", "Error1", "HIGH"
        )
        self.detector.detect_from_error(
            "gap2", "Desc2", "Context2", "tool2", "Error2", "HIGH"
        )
        self.detector.detect_missing_capability(
            "gap3", "Desc3", "Context3", "MEDIUM", 0.95
        )

        summary = self.detector.get_summary()
        self.assertEqual(summary["total_gaps"], 3)
        self.assertEqual(summary["critical_gaps"], 2)
        self.assertEqual(summary["by_severity"]["HIGH"], 2)
        self.assertEqual(summary["by_severity"]["MEDIUM"], 1)

    def test_capability_gap_from_error(self):
        """Test CapabilityGap.from_error factory."""
        gap = CapabilityGap.from_error(
            capability_name="test_cap",
            description="Test description",
            context="Test context",
            tool_name="test_tool",
            error="Test error",
        )

        self.assertEqual(gap.capability_name, "test_cap")
        self.assertEqual(gap.severity, "HIGH")
        self.assertEqual(gap.confidence, 0.95)


class TestGapResearcher(unittest.TestCase):
    """Tests for GapResearcher."""

    def setUp(self):
        """Set up test fixtures."""
        self.researcher = GapResearcher()

    def test_research_gap(self):
        """Test researching a gap."""
        gap = CapabilityGap(
            timestamp="2026-01-16T10:00:00",
            capability_name="database_query",
            capability_description="Query SQL databases",
            context="User needs to query PostgreSQL",
        )

        result = asyncio.run(self.researcher.research_gap(gap))

        self.assertIsNotNone(result)
        self.assertGreater(len(result.possible_solutions), 0)
        self.assertGreater(len(result.external_resources), 0)
        self.assertGreater(result.estimated_effort_days, 0)

    def test_research_image_gap(self):
        """Test researching image processing gap."""
        gap = CapabilityGap(
            timestamp="2026-01-16T10:00:00",
            capability_name="image_processing",
            capability_description="Process images",
            context="User needs to resize images",
        )

        result = asyncio.run(self.researcher.research_gap(gap))

        self.assertIn("image_processing", result.gap_name.lower())
        self.assertIn("Pillow", result.possible_solutions)

    def test_research_caching(self):
        """Test research result caching."""
        gap = CapabilityGap(
            timestamp="2026-01-16T10:00:00",
            capability_name="database_query",
            capability_description="Query databases",
            context="Test context",
        )

        # First research
        result1 = asyncio.run(self.researcher.research_gap(gap))
        # Second research should be cached
        result2 = asyncio.run(self.researcher.research_gap(gap))

        self.assertEqual(result1.gap_name, result2.gap_name)
        self.assertEqual(result1.possible_solutions, result2.possible_solutions)

    def test_get_cached_research(self):
        """Test retrieving cached research."""
        gap = CapabilityGap(
            timestamp="2026-01-16T10:00:00",
            capability_name="pdf_generation",
            capability_description="Generate PDFs",
            context="Test context",
        )

        asyncio.run(self.researcher.research_gap(gap))
        cached = self.researcher.get_cached_research("pdf_generation")

        self.assertIsNotNone(cached)
        self.assertEqual(cached.gap_name, "pdf_generation")

    def test_clear_cache(self):
        """Test clearing research cache."""
        gap = CapabilityGap(
            timestamp="2026-01-16T10:00:00",
            capability_name="database_query",
            capability_description="Query databases",
            context="Test context",
        )

        asyncio.run(self.researcher.research_gap(gap))
        self.assertGreater(len(self.researcher.research_cache), 0)

        self.researcher.clear_cache()
        self.assertEqual(len(self.researcher.research_cache), 0)

    def test_export_research(self):
        """Test exporting research to JSON."""
        gap = CapabilityGap(
            timestamp="2026-01-16T10:00:00",
            capability_name="database_query",
            capability_description="Query databases",
            context="Test context",
        )

        asyncio.run(self.researcher.research_gap(gap))

        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = Path(tmpdir) / "research.json"
            self.researcher.export_research(str(filepath))

            with open(filepath) as f:
                data = json.load(f)

            self.assertGreater(data["total_researches"], 0)
            self.assertIn("research_results", data)


class TestToolProposer(unittest.TestCase):
    """Tests for ToolProposer."""

    def setUp(self):
        """Set up test fixtures."""
        self.proposer = ToolProposer()
        self.researcher = GapResearcher()

    def test_propose_database_tool(self):
        """Test proposing database query tool."""
        gap = CapabilityGap(
            timestamp="2026-01-16T10:00:00",
            capability_name="database_query",
            capability_description="Query SQL databases",
            context="User needs database access",
        )

        research = asyncio.run(self.researcher.research_gap(gap))
        proposal = self.proposer.propose_tool(gap, research)

        self.assertEqual(proposal.tool_name, "database_query")
        self.assertIn("database", proposal.description.lower())
        self.assertEqual(proposal.risk_level, "HIGH")

    def test_propose_image_tool(self):
        """Test proposing image processing tool."""
        gap = CapabilityGap(
            timestamp="2026-01-16T10:00:00",
            capability_name="image_processing",
            capability_description="Process images",
            context="User needs image manipulation",
        )

        research = asyncio.run(self.researcher.research_gap(gap))
        proposal = self.proposer.propose_tool(gap, research)

        self.assertEqual(proposal.tool_name, "image_process")
        self.assertIn("image", proposal.description.lower())

    def test_proposal_to_markdown(self):
        """Test converting proposal to markdown."""
        gap = CapabilityGap(
            timestamp="2026-01-16T10:00:00",
            capability_name="pdf_generation",
            capability_description="Generate PDF documents",
            context="User needs to create PDFs",
        )

        research = asyncio.run(self.researcher.research_gap(gap))
        proposal = self.proposer.propose_tool(gap, research)
        markdown = proposal.to_markdown()

        self.assertIn("pdf_generate", markdown)
        self.assertIn("Parameters", markdown)
        self.assertIn("Risk Level", markdown)
        self.assertIn("Example", markdown)

    def test_get_quick_wins(self):
        """Test getting quick-win proposals."""
        gap1 = CapabilityGap(
            timestamp="2026-01-16T10:00:00",
            capability_name="api_integration",
            capability_description="Call APIs",
            context="User needs API access",
        )
        gap2 = CapabilityGap(
            timestamp="2026-01-16T10:00:00",
            capability_name="image_processing",
            capability_description="Process images",
            context="User needs image processing",
        )

        research1 = asyncio.run(self.researcher.research_gap(gap1))
        research2 = asyncio.run(self.researcher.research_gap(gap2))

        self.proposer.propose_tool(gap1, research1)
        self.proposer.propose_tool(gap2, research2)

        quick_wins = self.proposer.get_quick_wins()
        self.assertTrue(all(p.estimated_effort <= 0.5 for p in quick_wins))

    def test_get_high_priority_proposals(self):
        """Test getting high-priority proposals."""
        gap = CapabilityGap(
            timestamp="2026-01-16T10:00:00",
            capability_name="database_query",
            capability_description="Query databases",
            context="User needs database access",
        )

        research = asyncio.run(self.researcher.research_gap(gap))
        self.proposer.propose_tool(gap, research)

        high_priority = self.proposer.get_high_priority_proposals()
        self.assertTrue(
            any(p.risk_level == "HIGH" for p in high_priority)
        )

    def test_export_proposals_json(self):
        """Test exporting proposals to JSON."""
        gap = CapabilityGap(
            timestamp="2026-01-16T10:00:00",
            capability_name="database_query",
            capability_description="Query databases",
            context="Test context",
        )

        research = asyncio.run(self.researcher.research_gap(gap))
        self.proposer.propose_tool(gap, research)

        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = Path(tmpdir) / "proposals.json"
            self.proposer.export_proposals(str(filepath))

            with open(filepath) as f:
                data = json.load(f)

            self.assertEqual(data["total_proposals"], 1)
            self.assertIn("proposals", data)

    def test_export_proposals_markdown(self):
        """Test exporting proposals as markdown files."""
        gap = CapabilityGap(
            timestamp="2026-01-16T10:00:00",
            capability_name="database_query",
            capability_description="Query databases",
            context="Test context",
        )

        research = asyncio.run(self.researcher.research_gap(gap))
        self.proposer.propose_tool(gap, research)

        with tempfile.TemporaryDirectory() as tmpdir:
            self.proposer.export_proposals_as_markdown(tmpdir)

            # Check that markdown file was created
            md_files = list(Path(tmpdir).glob("*.md"))
            self.assertGreater(len(md_files), 0)

    def test_clear_proposals(self):
        """Test clearing proposals."""
        gap = CapabilityGap(
            timestamp="2026-01-16T10:00:00",
            capability_name="test_gap",
            capability_description="Test description",
            context="Test context",
        )

        research = asyncio.run(self.researcher.research_gap(gap))
        self.proposer.propose_tool(gap, research)
        self.assertEqual(len(self.proposer.proposals), 1)

        self.proposer.clear_proposals()
        self.assertEqual(len(self.proposer.proposals), 0)


class TestIntegration(unittest.TestCase):
    """Integration tests for Gap Analyzer."""

    def test_full_gap_analysis_workflow(self):
        """Test complete workflow: detect → research → propose."""
        detector = GapDetector()
        researcher = GapResearcher()
        proposer = ToolProposer()

        # Step 1: Detect gaps
        gap = detector.detect_from_error(
            capability_name="database_query",
            description="Execute SQL queries against databases",
            context="User tried to query PostgreSQL database",
            tool_name="shell_execute",
            error="psycopg2 library not found",
            severity="HIGH",
        )

        self.assertEqual(len(detector.gaps), 1)

        # Step 2: Research the gap
        research = asyncio.run(researcher.research_gap(gap))
        self.assertIsNotNone(research)

        # Step 3: Propose a tool
        proposal = proposer.propose_tool(gap, research)
        self.assertIsNotNone(proposal)
        self.assertEqual(proposal.tool_name, "database_query")

        # Verify integration
        self.assertIn(
            research.possible_solutions[0], proposal.implementation_hint
        )


if __name__ == "__main__":
    unittest.main()

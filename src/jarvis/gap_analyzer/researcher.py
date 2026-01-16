"""Gap Researcher - searches for solutions to gaps."""

import asyncio
import json
from dataclasses import dataclass, asdict
from typing import Any

from .detector import CapabilityGap


@dataclass
class ResearchResult:
    """Result of researching a capability gap."""

    gap_name: str
    possible_solutions: list[str]  # Library names, APIs, etc.
    system_capabilities: list[str]  # What system can already do
    implementation_difficulty: str  # EASY, MEDIUM, HARD, VERY_HARD
    estimated_effort_days: float
    external_resources: list[dict[str, str]]  # URLs and descriptions

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)


class GapResearcher:
    """Researches solutions for detected capability gaps."""

    def __init__(self):
        """Initialize the gap researcher."""
        self.research_cache: dict[str, ResearchResult] = {}

    async def research_gap(self, gap: CapabilityGap) -> ResearchResult:
        """Research solutions for a capability gap.

        Args:
            gap: The capability gap to research

        Returns:
            Research results with possible solutions
        """
        # Check cache first
        cache_key = gap.capability_name.lower()
        if cache_key in self.research_cache:
            return self.research_cache[cache_key]

        # Simulate research (in real implementation, would use web_fetch tool)
        result = await self._simulate_research(gap)
        self.research_cache[cache_key] = result
        return result

    async def _simulate_research(self, gap: CapabilityGap) -> ResearchResult:
        """Simulate research process."""
        await asyncio.sleep(0.1)  # Simulate research time

        # Map common gaps to solutions
        gap_solutions = {
            "database_query": {
                "possible_solutions": ["SQLAlchemy", "psycopg2", "pymongo", "pymysql"],
                "system_capabilities": ["Can execute SQL via shell_execute"],
                "difficulty": "EASY",
                "effort": 0.5,
                "resources": [
                    {
                        "url": "https://www.sqlalchemy.org",
                        "description": "Python SQL toolkit",
                    },
                    {
                        "url": "https://www.psycopg.org",
                        "description": "PostgreSQL adapter",
                    },
                ],
            },
            "image_processing": {
                "possible_solutions": ["Pillow", "OpenCV", "scikit-image"],
                "system_capabilities": ["Can execute ffmpeg via shell_execute"],
                "difficulty": "MEDIUM",
                "effort": 1.5,
                "resources": [
                    {
                        "url": "https://python-pillow.org",
                        "description": "Image processing library",
                    },
                    {
                        "url": "https://opencv.org",
                        "description": "Computer vision library",
                    },
                ],
            },
            "pdf_generation": {
                "possible_solutions": ["reportlab", "fpdf2", "python-docx"],
                "system_capabilities": ["Can write files"],
                "difficulty": "EASY",
                "effort": 0.5,
                "resources": [
                    {
                        "url": "https://www.reportlab.com",
                        "description": "PDF toolkit",
                    },
                ],
            },
            "api_integration": {
                "possible_solutions": ["requests", "httpx", "aiohttp"],
                "system_capabilities": ["Can make web requests via web_fetch"],
                "difficulty": "EASY",
                "effort": 0.25,
                "resources": [
                    {
                        "url": "https://requests.readthedocs.io",
                        "description": "HTTP library",
                    },
                ],
            },
            "data_parsing": {
                "possible_solutions": ["BeautifulSoup", "lxml", "html.parser"],
                "system_capabilities": ["Can fetch web content via web_fetch"],
                "difficulty": "EASY",
                "effort": 0.5,
                "resources": [
                    {
                        "url": "https://www.crummy.com/software/BeautifulSoup",
                        "description": "Web scraping library",
                    },
                ],
            },
        }

        # Find best match
        gap_lower = gap.capability_name.lower()
        for key, solution in gap_solutions.items():
            if key in gap_lower or gap_lower in key:
                return ResearchResult(
                    gap_name=gap.capability_name,
                    possible_solutions=solution["possible_solutions"],
                    system_capabilities=solution["system_capabilities"],
                    implementation_difficulty=solution["difficulty"],
                    estimated_effort_days=solution["effort"],
                    external_resources=solution["resources"],
                )

        # Generic fallback
        return ResearchResult(
            gap_name=gap.capability_name,
            possible_solutions=["PyPI package search recommended"],
            system_capabilities=["Can use shell_execute for system commands"],
            implementation_difficulty="UNKNOWN",
            estimated_effort_days=1.0,
            external_resources=[
                {
                    "url": "https://pypi.org",
                    "description": "Python Package Index",
                }
            ],
        )

    def get_cached_research(self, gap_name: str) -> ResearchResult | None:
        """Get cached research result."""
        return self.research_cache.get(gap_name.lower())

    def clear_cache(self) -> None:
        """Clear research cache."""
        self.research_cache.clear()

    def export_research(self, filepath: str) -> None:
        """Export all research results to JSON."""
        data = {
            "total_researches": len(self.research_cache),
            "research_results": {
                name: result.to_dict()
                for name, result in self.research_cache.items()
            },
        }
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

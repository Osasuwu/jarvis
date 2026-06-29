"""Jarvis Status MCP Server — status_digest tool.

Thin wrapper around status_gather (I/O adapter) and status_engine (pure function).

Public interface:
    status_digest: Single tool that calls gather() → analyze() and returns digest.

Usage in .mcp.json:
{
  "status": {
    "type": "stdio",
    "command": "python",
    "args": ["mcp-status/server.py"],
    "env": {
      "SUPABASE_URL": "https://xxx.supabase.co",
      "SUPABASE_KEY": "eyJ...",
    }
  }
}
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# Alias __main__ -> 'server' for consistency with mcp-memory pattern
sys.modules.setdefault("server", sys.modules[__name__])

# noqa: E402 — .env loaded before MCP/script imports (required, follows mcp-memory pattern)
from dotenv import load_dotenv  # noqa: E402

# Load .env from repo root (two levels up from mcp-status/server.py).
_env_candidates = [
    Path(__file__).resolve().parent.parent / ".env",
    Path(__file__).resolve().parent.parent.parent / ".env",
]
for _env_path in _env_candidates:
    if _env_path.exists():
        load_dotenv(_env_path, override=True)
        break

from mcp.server import Server  # noqa: E402
from mcp.server.stdio import stdio_server  # noqa: E402
from mcp.types import CallToolResult, TextContent, Tool  # noqa: E402

# Import gather and engine modules
from scripts.status_gather import gather  # noqa: E402
from scripts.status_engine import analyze  # noqa: E402

# ============================================================================
# MCP Server
# ============================================================================

server = Server("jarvis-status")


# ============================================================================
# Tool registration
# ============================================================================

@server.list_tools()
def list_tools() -> list[Tool]:
    """Return the single status_digest tool."""
    return [
        Tool(
            name="status_digest",
            description=(
                "Synthesize a status digest by gathering current repo state "
                "and analyzing it for anomalies. Wraps gather() → engine "
                "in a single call. Returns {health, detector_hits, ranking, "
                "provenance}."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "jarvis_home": {
                        "type": "string",
                        "description": (
                            "Root path of the jarvis repo. If empty, auto-detects "
                            "from CWD via git rev-parse."
                        ),
                    },
                },
                "required": [],
            },
        ),
    ]


# ============================================================================
# Tool dispatch
# ============================================================================

def _convert_gather_to_engine_format(gather_result):
    """Convert GatherResult to Baseline/Delta/decisions for engine.analyze()."""
    from scripts.status_engine import (
        Baseline, Delta, Provenance, RepoState, IssueInfo, DecisionInfo
    )

    baseline = Baseline(gathered_at="", repos={}, provenance={})
    delta = Delta(gathered_at=gather_result.gathered_at, repos={})

    # Convert repo data to engine format
    for repo_entry in gather_result.repos:
        repo_name = repo_entry.get("name", "")
        issues_data = repo_entry.get("issues", [])
        prs_data = repo_entry.get("prs", [])

        # Convert issues to IssueInfo
        issues: list[IssueInfo] = []
        for issue in issues_data:
            issues.append(IssueInfo(
                number=issue.get("number", 0),
                title=issue.get("title", ""),
                state="open",  # gather filters to open issues
                labels=issue.get("labels", []),
                milestone=issue.get("milestone"),
                updated_at=issue.get("updatedAt", ""),
            ))

        # Create RepoState for delta (most recent data)
        repo_state = RepoState(
            repo=repo_name,
            open_issues=issues,
            open_prs=prs_data or [],
            provenance=None,
        )

        # Mark provenance from gather
        repo_provenance: dict[str, any] = {}
        if "provenance" in repo_entry:
            for source_key, prov_dict in repo_entry["provenance"].items():
                repo_provenance[source_key] = Provenance(
                    ran=prov_dict.get("ran", False),
                    ok=prov_dict.get("ok", False),
                    input_rows=prov_dict.get("input_rows", 0),
                    age=prov_dict.get("age", 0.0),
                )

        delta.repos[repo_name] = repo_state

    # Convert top-level provenance from gather
    for source_key, prov_dict in gather_result.provenance.items():
        baseline.provenance[source_key] = Provenance(
            ran=prov_dict.get("ran", False),
            ok=prov_dict.get("ok", False),
            input_rows=prov_dict.get("input_rows", 0),
            age=prov_dict.get("age", 0.0),
        )

    # Convert decisions
    decisions: list[DecisionInfo] = []
    for decision_rec in gather_result.decisions:
        payload = decision_rec.payload or {}
        decisions.append(DecisionInfo(
            decision_id=decision_rec.id,
            decision=payload.get("decision", ""),
            created_at=decision_rec.created_at,
            project=payload.get("project"),
        ))

    return baseline, delta, decisions


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent] | CallToolResult:
    """Dispatch to the status_digest tool."""
    try:
        if name == "status_digest":
            jarvis_home = arguments.get("jarvis_home", "")

            # Call gather to collect state
            gather_result = gather(jarvis_home)

            # Convert gather result to engine format
            baseline, delta, decisions = _convert_gather_to_engine_format(gather_result)

            # Analyze with engine
            digest = analyze(baseline, delta, decisions)

            # Build response: {health, detector_hits, ranking, provenance}
            response_data = {
                "health": {
                    "ok": digest.health.ok,
                    "reason": digest.health.reason,
                },
                "detector_hits": [
                    {
                        "detector": hit.detector,
                        "severity": hit.severity,
                        "repo": hit.repo,
                        "issue_number": hit.issue_number,
                        "title": hit.title,
                        "description": hit.description,
                    }
                    for hit in digest.detector_hits
                ],
                "ranking": [
                    {
                        "rank": item.rank,
                        "detector_hit": {
                            "detector": item.detector_hit.detector,
                            "severity": item.detector_hit.severity,
                            "repo": item.detector_hit.repo,
                            "issue_number": item.detector_hit.issue_number,
                            "title": item.detector_hit.title,
                            "description": item.detector_hit.description,
                        },
                        "reason": item.reason,
                    }
                    for item in digest.ranking
                ],
                "provenance": {
                    key: {
                        "ran": prov.ran,
                        "ok": prov.ok,
                        "input_rows": prov.input_rows,
                        "age": prov.age,
                    }
                    for key, prov in digest.provenance.items()
                },
            }

            import json
            result_text = json.dumps(response_data, indent=2, default=str)
            return [TextContent(type="text", text=result_text)]

        else:
            return [TextContent(type="text", text=f"Unknown tool: {name}")]

    except Exception as exc:
        import traceback
        return [TextContent(
            type="text",
            text=f"Error in {name}: {exc}\n{traceback.format_exc()}"
        )]


# ============================================================================
# Main
# ============================================================================

async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())

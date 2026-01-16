"""Local tools for filesystem and shell operations."""

from __future__ import annotations

import os
import subprocess
import textwrap
from pathlib import Path
from typing import Any
from urllib import request, error as urlerror
import json

from jarvis.tools.base import RiskLevel, Tool, ToolParameter, ToolResult


def _resolve_safe_path(path_str: str) -> Path:
    """Resolve a path and ensure it stays within the working directory."""
    base = Path.cwd().resolve()
    target = (base / path_str).resolve()
    if not str(target).startswith(str(base)):
        raise ValueError("Path escapes working directory")
    return target


class FileReadTool(Tool):
    """Safely read a file within the working directory."""

    name = "file_read"
    description = "Read a text file from the working directory."
    risk_level = RiskLevel.LOW
    capabilities = ["fs", "read"]

    async def execute(self, **kwargs: Any) -> ToolResult:
        try:
            path = _resolve_safe_path(kwargs.get("path", ""))
            encoding = kwargs.get("encoding", "utf-8")
            max_bytes = int(kwargs.get("max_bytes", 1_000_000))

            if not path.exists() or not path.is_file():
                return ToolResult(success=False, output="", error="File not found")

            if path.stat().st_size > max_bytes:
                return ToolResult(success=False, output="", error="File too large to read safely")

            content = path.read_text(encoding=encoding)
            return ToolResult(success=True, output=content)
        except Exception as exc:  # noqa: BLE001
            return ToolResult(success=False, output="", error=str(exc))

    def get_parameters(self) -> list[ToolParameter]:
        return [
            ToolParameter(
                name="path",
                type="string",
                description="Relative path to the file to read",
                required=True,
            ),
            ToolParameter(
                name="encoding",
                type="string",
                description="Text encoding (default utf-8)",
                required=False,
                default="utf-8",
            ),
            ToolParameter(
                name="max_bytes",
                type="integer",
                description="Maximum file size to read in bytes (default 1,000,000)",
                required=False,
                default=1_000_000,
            ),
        ]


class FileWriteTool(Tool):
    """Safely write or append to a file within the working directory."""

    name = "file_write"
    description = "Write text to a file (creates parent dirs)."
    risk_level = RiskLevel.MEDIUM
    requires_confirmation = False
    capabilities = ["fs", "write"]

    async def execute(self, **kwargs: Any) -> ToolResult:
        try:
            path = _resolve_safe_path(kwargs.get("path", ""))
            content = kwargs.get("content", "")
            append = bool(kwargs.get("append", False))
            encoding = kwargs.get("encoding", "utf-8")

            path.parent.mkdir(parents=True, exist_ok=True)
            mode = "a" if append else "w"
            with path.open(mode, encoding=encoding) as f:
                f.write(content)

            return ToolResult(success=True, output=f"Wrote to {path}")
        except Exception as exc:  # noqa: BLE001
            return ToolResult(success=False, output="", error=str(exc))

    def get_parameters(self) -> list[ToolParameter]:
        return [
            ToolParameter(
                name="path",
                type="string",
                description="Relative path to the file to write",
                required=True,
            ),
            ToolParameter(
                name="content",
                type="string",
                description="Content to write",
                required=True,
            ),
            ToolParameter(
                name="append",
                type="boolean",
                description="Append instead of overwrite",
                required=False,
                default=False,
            ),
            ToolParameter(
                name="encoding",
                type="string",
                description="Text encoding (default utf-8)",
                required=False,
                default="utf-8",
            ),
        ]


class ListDirectoryTool(Tool):
    """List files in a directory (safe, bounded)."""

    name = "list_directory"
    description = "List directory contents within working directory."
    risk_level = RiskLevel.LOW
    capabilities = ["fs", "list"]

    async def execute(self, **kwargs: Any) -> ToolResult:
        try:
            path = _resolve_safe_path(kwargs.get("path", "."))
            show_hidden = bool(kwargs.get("show_hidden", False))
            max_items = int(kwargs.get("max_items", 200))

            if not path.exists() or not path.is_dir():
                return ToolResult(success=False, output="", error="Directory not found")

            entries = []
            for entry in os.scandir(path):
                if not show_hidden and entry.name.startswith('.'):
                    continue
                kind = "dir" if entry.is_dir() else "file"
                size = entry.stat().st_size if entry.is_file() else 0
                entries.append({"name": entry.name, "type": kind, "size": size})
                if len(entries) >= max_items:
                    break

            return ToolResult(success=True, output=entries)
        except Exception as exc:  # noqa: BLE001
            return ToolResult(success=False, output="", error=str(exc))

    def get_parameters(self) -> list[ToolParameter]:
        return [
            ToolParameter(
                name="path",
                type="string",
                description="Directory path (relative)",
                required=False,
                default=".",
            ),
            ToolParameter(
                name="show_hidden",
                type="boolean",
                description="Include hidden files",
                required=False,
                default=False,
            ),
            ToolParameter(
                name="max_items",
                type="integer",
                description="Maximum items to list",
                required=False,
                default=200,
            ),
        ]


class ShellExecuteTool(Tool):
    """Execute a shell command (high risk)."""

    name = "shell_execute"
    description = "Execute a shell command in the working directory."
    risk_level = RiskLevel.HIGH
    requires_confirmation = True
    capabilities = ["shell", "exec"]

    async def execute(self, **kwargs: Any) -> ToolResult:
        cmd = kwargs.get("command", "")
        timeout = int(kwargs.get("timeout", 15))
        stdout = ""

        if not cmd:
            return ToolResult(success=False, output="", error="No command provided")

        try:
            completed = subprocess.run(  # noqa: S603, S607
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                cwd=Path.cwd(),
                timeout=timeout,
            )
            stdout = completed.stdout.strip()
            stderr = completed.stderr.strip()
            output = stdout if stdout else stderr
            success = completed.returncode == 0
            summary = textwrap.shorten(output, width=4000) if output else ""
            return ToolResult(success=success, output=summary, error=None if success else output)
        except Exception as exc:  # noqa: BLE001
            return ToolResult(success=False, output=stdout, error=str(exc))

    def get_parameters(self) -> list[ToolParameter]:
        return [
            ToolParameter(
                name="command",
                type="string",
                description="Shell command to execute",
                required=True,
            ),
            ToolParameter(
                name="timeout",
                type="integer",
                description="Timeout in seconds (default 15)",
                required=False,
                default=15,
            ),
        ]


class WebFetchTool(Tool):
    """Fetch a URL (simple GET)."""

    name = "web_fetch"
    description = "Fetch a URL via HTTP GET (no auth)."
    risk_level = RiskLevel.LOW
    capabilities = ["web", "fetch"]

    async def execute(self, **kwargs: Any) -> ToolResult:
        url = kwargs.get("url", "")
        timeout = int(kwargs.get("timeout", 10))
        if not url:
            return ToolResult(success=False, output="", error="No URL provided")
        try:
            with request.urlopen(url, timeout=timeout) as resp:
                content_type = resp.headers.get("Content-Type", "")
                body = resp.read()
                # Try decode if text
                if "text" in content_type or "json" in content_type:
                    try:
                        body_text = body.decode(resp.headers.get_content_charset() or "utf-8")
                    except Exception:  # noqa: BLE001
                        body_text = body.decode(errors="replace")
                    return ToolResult(success=True, output=body_text)
                return ToolResult(success=True, output=f"Fetched {len(body)} bytes")
        except Exception as exc:  # noqa: BLE001
            return ToolResult(success=False, output="", error=str(exc))

    def get_parameters(self) -> list[ToolParameter]:
        return [
            ToolParameter(
                name="url",
                type="string",
                description="URL to fetch",
                required=True,
            ),
            ToolParameter(
                name="timeout",
                type="integer",
                description="Timeout seconds",
                required=False,
                default=10,
            ),
        ]


class WebSearchTool(Tool):
    """Perform a simple web search using DuckDuckGo instant answer API."""

    name = "web_search"
    description = "Search the web (DuckDuckGo Instant Answer)."
    risk_level = RiskLevel.LOW
    capabilities = ["web", "search"]

    async def execute(self, **kwargs: Any) -> ToolResult:
        query = kwargs.get("query", "")
        max_results = int(kwargs.get("max_results", 5))
        if not query:
            return ToolResult(success=False, output="", error="No query provided")
        try:
            url = f"https://api.duckduckgo.com/?q={request.quote(query)}&format=json&no_redirect=1&no_html=1"
            with request.urlopen(url, timeout=10) as resp:
                data = json.loads(resp.read())
            topics = data.get("RelatedTopics", [])
            results = []
            for t in topics:
                if isinstance(t, dict) and t.get("Text"):
                    results.append({"title": t.get("Text"), "url": t.get("FirstURL")})
                if len(results) >= max_results:
                    break
            if not results and data.get("AbstractText"):
                results.append({"title": data.get("AbstractText"), "url": data.get("AbstractURL")})
            if not results:
                return ToolResult(success=False, output="", error="No results")
            return ToolResult(success=True, output=results)
        except Exception as exc:  # noqa: BLE001
            return ToolResult(success=False, output="", error=str(exc))

    def get_parameters(self) -> list[ToolParameter]:
        return [
            ToolParameter(
                name="query",
                type="string",
                description="Search query",
                required=True,
            ),
            ToolParameter(
                name="max_results",
                type="integer",
                description="Maximum results to return",
                required=False,
                default=5,
            ),
        ]

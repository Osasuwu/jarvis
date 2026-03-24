"""Abstract coding agent interface + Claude Code CLI implementation.

The coding agent receives a structured prompt and works autonomously in a repo
to implement changes. Jarvis brain (cheap model) handles decomposition and
orchestration; the coding agent (expensive model or Pro subscription) does the work.

Architecture: pluggable — swap implementations without changing the pipeline.
"""
from __future__ import annotations

import os
import subprocess
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CodingResult:
    success: bool
    summary: str
    error: str = ""
    files_changed: int = 0


class CodingAgent(ABC):
    """Abstract interface for a coding agent that writes code."""

    @abstractmethod
    def execute(
        self,
        prompt: str,
        *,
        cwd: str | Path,
        model: str = "sonnet",
        timeout_sec: int = 600,
    ) -> CodingResult:
        """Execute a coding task. Returns result with summary."""
        ...


class ClaudeCodeAgent(CodingAgent):
    """Coding agent using Claude Code CLI.

    Uses Pro/Max subscription by default (excludes ANTHROPIC_API_KEY from env).
    Set use_api_key=True to use API billing instead.
    """

    def __init__(self, *, use_api_key: bool = False, cli_path: str = "claude"):
        self.use_api_key = use_api_key
        self.cli_path = cli_path

    def execute(
        self,
        prompt: str,
        *,
        cwd: str | Path,
        model: str = "sonnet",
        timeout_sec: int = 600,
    ) -> CodingResult:
        env = os.environ.copy()
        if not self.use_api_key:
            env.pop("ANTHROPIC_API_KEY", None)

        command = [
            self.cli_path,
            "--model", model,
            "-p", prompt,
            "--output-format", "text",
            "--allowedTools", "Edit,Write,Read,Bash,Glob,Grep",
        ]

        try:
            completed = subprocess.run(
                command,
                check=False,
                text=True,
                encoding="utf-8",
                errors="replace",
                capture_output=True,
                timeout=timeout_sec,
                cwd=str(cwd),
                env=env,
            )
        except FileNotFoundError:
            return CodingResult(
                success=False,
                summary="",
                error=f"Claude Code CLI not found at '{self.cli_path}'. Install: npm install -g @anthropic-ai/claude-code",
            )
        except subprocess.TimeoutExpired:
            return CodingResult(
                success=False,
                summary="",
                error=f"Coding agent timed out after {timeout_sec}s.",
            )

        if completed.returncode != 0:
            error_text = completed.stderr.strip() or completed.stdout.strip() or "Unknown error"
            return CodingResult(
                success=False,
                summary="",
                error=f"Claude Code exited with code {completed.returncode}: {error_text[:500]}",
            )

        output = completed.stdout.strip()
        if not output:
            return CodingResult(
                success=False,
                summary="",
                error="Claude Code returned empty output.",
            )

        return CodingResult(
            success=True,
            summary=output,
        )


def get_coding_agent(*, use_api_key: bool = False) -> CodingAgent:
    """Factory — returns the configured coding agent.

    Currently only ClaudeCodeAgent. In the future, can return
    other implementations based on config.
    """
    cli_path = os.getenv("CLAUDE_CLI_PATH", "claude")
    return ClaudeCodeAgent(use_api_key=use_api_key, cli_path=cli_path)

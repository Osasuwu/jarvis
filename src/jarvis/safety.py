"""Safety gates for Jarvis self-modification.

Block E: Prevents dangerous operations during autonomous self-improvement.
- Forbidden paths: files that must never be auto-modified
- Forbidden commands: shell commands that must never be auto-executed
- Risk classification: categorize findings by modification risk
- Patch validation: check that proposed changes don't touch forbidden areas
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import PurePosixPath


# ── Forbidden paths ──────────────────────────────────────────────────────
# Files/dirs that must NEVER be modified by autonomous self-improve.
FORBIDDEN_PATHS: frozenset[str] = frozenset({
    ".env",
    ".env.local",
    ".env.production",
    ".git",
    ".github/workflows",
    "secrets",
    "credentials",
    "config/secrets",
    # Safety module itself — no self-modification of safety gates
    "src/jarvis/safety.py",
})

# Patterns for additional forbidden paths.
# Prefix patterns start with "." and use trailing "*" as wildcard.
# Suffix patterns start with "*" and match by extension.
FORBIDDEN_PATH_PATTERNS: tuple[str, ...] = (
    "*.pem",
    "*.key",
    "*.secret",
    ".env*",  # matches .env, .env.local, .env.anything
)

# ── Forbidden commands ───────────────────────────────────────────────────
# Shell commands/fragments that must never be auto-executed.
FORBIDDEN_COMMANDS: frozenset[str] = frozenset({
    "rm -rf /",
    "rm -rf ~",
    "rm -rf .",
    "git push --force",
    "git push -f",
    "git reset --hard",
    "git clean -fd",
    "git checkout -- .",
    "drop table",
    "drop database",
    "truncate table",
    "curl | sh",
    "curl | bash",
    "wget | sh",
    "wget | bash",
    "> /dev/null 2>&1 &",  # silent background — hides errors
    "chmod 777",
    "sudo rm",
})

# Regex patterns for command denylist.
FORBIDDEN_COMMAND_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"rm\s+-[a-z]*r[a-z]*f", re.IGNORECASE),  # rm -rf variants
    re.compile(r"git\s+push\s+.*--force", re.IGNORECASE),
    re.compile(r"git\s+push\s+-f\b", re.IGNORECASE),
    re.compile(r"curl\s+.*\|\s*(ba)?sh", re.IGNORECASE),
    re.compile(r"eval\s*\(", re.IGNORECASE),  # eval() injection
)


# ── Risk levels ──────────────────────────────────────────────────────────
@dataclass(frozen=True)
class RiskAssessment:
    level: str  # "low", "medium", "high"
    reason: str
    requires_approval: bool


# Keywords in finding titles/details that signal higher risk.
_HIGH_RISK_KEYWORDS = frozenset({
    "security", "injection", "traversal", "authentication", "authorization",
    "credential", "secret", "token", "password", "api key", "race condition",
    "data loss", "corruption",
})

_MEDIUM_RISK_KEYWORDS = frozenset({
    "architecture", "refactor", "coupling", "circular dependency",
    "entrypoint", "handler", "config migration",
})

# High-impact file paths — changes here are at least medium risk.
_HIGH_IMPACT_PATHS: tuple[str, ...] = (
    "src/main.py",
    "src/handlers/",
    "src/jarvis/delegate.py",
    "src/jarvis/executor.py",
    "src/jarvis/config.py",
    "src/jarvis/safety.py",
    "src/agents/",
    ".github/",
)


def classify_risk(
    severity: str,
    title: str,
    details: str,
    files_involved: list[str] | None = None,
) -> RiskAssessment:
    """Classify the risk of auto-fixing a finding.

    Returns a RiskAssessment with level, reason, and whether approval is needed.
    """
    combined = f"{title} {details}".lower()

    # Critical severity → always high risk
    if severity == "critical":
        return RiskAssessment("high", "Critical severity findings require human review", True)

    # Security-related keywords → high risk
    for kw in _HIGH_RISK_KEYWORDS:
        if kw in combined:
            return RiskAssessment("high", f"Security-sensitive keyword: {kw}", True)

    # High-impact file paths
    if files_involved:
        for fpath in files_involved:
            for pattern in _HIGH_IMPACT_PATHS:
                if fpath.startswith(pattern):
                    return RiskAssessment(
                        "medium",
                        f"Touches high-impact path: {pattern}",
                        True,
                    )

    # Architecture/refactoring keywords → medium
    for kw in _MEDIUM_RISK_KEYWORDS:
        if kw in combined:
            return RiskAssessment("medium", f"Structural change keyword: {kw}", True)

    # Major severity → medium risk
    if severity == "major":
        return RiskAssessment("medium", "Major severity — review recommended", True)

    # Minor severity with no risk signals → low risk, auto-apply OK
    return RiskAssessment("low", "Minor finding with no risk signals", False)


def is_path_forbidden(path: str) -> bool:
    """Check if a file path is in the forbidden set."""
    normalized = path.replace("\\", "/").strip("/")

    for forbidden in FORBIDDEN_PATHS:
        if normalized == forbidden or normalized.startswith(forbidden + "/"):
            return True

    # Check patterns
    name = PurePosixPath(normalized).name
    for pattern in FORBIDDEN_PATH_PATTERNS:
        if pattern.startswith("*"):
            # Suffix pattern: "*.pem" → match files ending with ".pem"
            if name.endswith(pattern[1:]):
                return True
        elif pattern.endswith("*"):
            # Prefix pattern: ".env*" → match files starting with ".env"
            if name.startswith(pattern[:-1]):
                return True
        elif name == pattern:
            return True

    return False


def validate_patch(files_changed: list[str]) -> tuple[bool, str]:
    """Validate that a set of changed files doesn't touch forbidden paths.

    Returns (is_safe, reason).
    """
    blocked = [f for f in files_changed if is_path_forbidden(f)]
    if blocked:
        return False, f"Forbidden paths would be modified: {', '.join(blocked)}"
    return True, "All changed files are within allowed paths"


def is_command_forbidden(command: str) -> bool:
    """Check if a shell command matches the denylist.

    NOTE: This function is currently NOT integrated into the subprocess execution layer.
    It is defined here as part of the safety module design, but no execution paths
    currently call it before running shell commands. To activate command-level safety
    blocking, wire this function into any subprocess wrappers used by autonomous
    workflows (e.g., the coding agent or LLM tool layer).

    Until then, this denylist provides documentation of which commands are considered
    dangerous, but does not actually prevent their execution.
    """
    lower = command.lower().strip()

    for forbidden in FORBIDDEN_COMMANDS:
        if forbidden in lower:
            return True

    for pattern in FORBIDDEN_COMMAND_PATTERNS:
        if pattern.search(lower):
            return True

    return False


def require_approval(risk_level: str) -> bool:
    """Whether a given risk level requires human approval."""
    return risk_level in {"medium", "high"}

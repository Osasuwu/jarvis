from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[2]
MEMORY_FILE = ROOT_DIR / ".jarvis" / "work_memory.jsonl"


@dataclass(frozen=True)
class WorkMemoryEntry:
    timestamp_utc: str
    workflow: str
    project: str
    objective: str
    attempted_actions: tuple[str, ...]
    blockers: tuple[str, ...]
    next_steps: tuple[str, ...]
    status: str
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp_utc": self.timestamp_utc,
            "workflow": self.workflow,
            "project": self.project,
            "objective": self.objective,
            "attempted_actions": list(self.attempted_actions),
            "blockers": list(self.blockers),
            "next_steps": list(self.next_steps),
            "status": self.status,
            "metadata": self.metadata,
        }


def _parse_entry(raw: dict[str, Any]) -> WorkMemoryEntry | None:
    try:
        return WorkMemoryEntry(
            timestamp_utc=str(raw.get("timestamp_utc", "")),
            workflow=str(raw.get("workflow", "")),
            project=str(raw.get("project", "")),
            objective=str(raw.get("objective", "")),
            attempted_actions=tuple(str(item) for item in raw.get("attempted_actions", [])),
            blockers=tuple(str(item) for item in raw.get("blockers", [])),
            next_steps=tuple(str(item) for item in raw.get("next_steps", [])),
            status=str(raw.get("status", "")),
            metadata=dict(raw.get("metadata", {})),
        )
    except Exception:
        return None


def append_work_memory(entry: WorkMemoryEntry) -> None:
    """Append an entry to the work memory log.

    Note: File grows indefinitely. To clean up old entries, call cleanup_old_entries().
    """
    MEMORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    # Use ensure_ascii=False for better readability of multi-language entries
    with MEMORY_FILE.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry.to_dict(), ensure_ascii=False) + "\n")


def read_latest_work_memory(workflow: str, project: str | None = None) -> WorkMemoryEntry | None:
    entries = read_recent_memory(workflow, project=project, n=1)
    return entries[0] if entries else None


def read_recent_memory(
    workflow: str,
    project: str | None = None,
    n: int = 5,
) -> list[WorkMemoryEntry]:
    """Return the last *n* entries for a workflow, in chronological order."""
    if not MEMORY_FILE.exists():
        return []

    lines = MEMORY_FILE.read_text(encoding="utf-8").splitlines()
    results: list[WorkMemoryEntry] = []
    for line in reversed(lines):
        if len(results) >= n:
            break
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        entry = _parse_entry(payload)
        if entry is None:
            continue
        if entry.workflow != workflow:
            continue
        if project is not None and entry.project != project:
            continue
        results.append(entry)
    return list(reversed(results))


async def summarize_memory(
    entries: list[WorkMemoryEntry],
    question: str | None = None,
) -> str:
    """Use Haiku to summarize patterns across memory entries.

    Falls back to a simple formatted context string when the LLM call
    fails or there is nothing to summarize.
    """
    if not entries:
        return "No prior memory entries."

    # Avoid circular import — executor lives in the same package.
    from jarvis.executor import execute_query  # noqa: WPS433

    entries_text = "\n".join(
        f"- [{e.timestamp_utc}] {e.workflow} status={e.status} "
        f"blockers=[{'; '.join(e.blockers[:3])}] "
        f"next=[{'; '.join(e.next_steps[:3])}]"
        for e in entries
    )

    focus = f"\nSpecific question: {question}" if question else ""

    prompt = (
        "You are Jarvis's memory analyst. "
        "Analyze these workflow memory entries and provide a brief summary.\n"
        "Focus on: recurring blockers, patterns of success/failure, "
        "what changed over time.\n"
        f"{focus}\n\n"
        f"Entries (oldest first):\n{entries_text}\n\n"
        "Respond with 2-3 sentences. Be specific and actionable."
    )

    result = await execute_query(prompt, model="haiku", max_budget_usd=0.01)

    if not result.success:
        # Graceful degradation: return simple last-entry context.
        return format_memory_context(entries[-1])

    return result.text.strip()


def build_self_review_entry(
    *,
    project: str,
    critical_count: int,
    major_count: int,
    minor_count: int,
    blockers: list[str],
    report_path: str,
) -> WorkMemoryEntry:
    next_steps = []
    if blockers:
        next_steps.append("Resolve critical/major blockers and rerun /self-review.")
    else:
        next_steps.append("No blockers found. Proceed to /self-improve planning.")

    return WorkMemoryEntry(
        timestamp_utc=datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S"),
        workflow="self-review",
        project=project,
        objective="Evaluate runtime and operational readiness of Jarvis.",
        attempted_actions=(
            "Compile source files.",
            "Run entrypoint import smoke test.",
            "Validate budget and model config.",
            "Check delegation prerequisites.",
            "Run changed-files risk review.",
        ),
        blockers=tuple(blockers),
        next_steps=tuple(next_steps),
        status="ok" if not blockers else "needs-attention",
        metadata={
            "critical_count": critical_count,
            "major_count": major_count,
            "minor_count": minor_count,
            "report_path": report_path,
        },
    )


def build_delegate_entry(
    *,
    project: str,
    issue_number: int,
    success: bool,
    message: str,
    pr_url: str,
) -> WorkMemoryEntry:
    compact_message = " ".join(message.split())
    if len(compact_message) > 240:
        compact_message = compact_message[:237] + "..."

    blockers = []
    next_steps = []

    if success:
        next_steps.append("Review PR and merge when checks pass.")
    else:
        blockers.append(compact_message)
        next_steps.append("Fix reported delegation failure and retry /delegate.")

    return WorkMemoryEntry(
        timestamp_utc=datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S"),
        workflow="delegate",
        project=project,
        objective=f"Delegate implementation for issue #{issue_number}.",
        attempted_actions=(
            "Parse delegation target.",
            "Apply budget gate.",
            "Run issue decomposition.",
            "Execute coding pipeline and PR flow.",
        ),
        blockers=tuple(blockers),
        next_steps=tuple(next_steps),
        status="ok" if success else "failed",
        metadata={
            "issue_number": issue_number,
            "success": success,
            "pr_url": pr_url,
            "raw_message": message,
        },
    )


def format_memory_context(entry: WorkMemoryEntry) -> str:
    blockers = "; ".join(entry.blockers[:2]) if entry.blockers else "none"
    next_steps = "; ".join(entry.next_steps[:2]) if entry.next_steps else "n/a"
    return (
        f"[jarvis] memory: last {entry.workflow} status={entry.status} "
        f"| blockers={blockers} | next={next_steps}"
    )


def get_project_from_git() -> str:
    """Derive project name from git remote origin, with fallback."""
    import subprocess

    try:
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            url = result.stdout.strip()
            # Handle https://github.com/owner/repo.git and git@github.com:owner/repo.git
            for prefix in ("https://github.com/", "git@github.com:"):
                if url.startswith(prefix):
                    return url[len(prefix) :].removesuffix(".git")
    except Exception:
        pass
    return "unknown/project"


def cleanup_old_entries(days: int = 30) -> int:
    """Remove entries older than N days. Returns count of cleaned entries.

    This prevents MEMORY_FILE from growing unboundedly.
    Call periodically (e.g., weekly) or when size exceeds threshold.
    """
    if not MEMORY_FILE.exists():
        return 0

    from datetime import timedelta  # noqa: WPS433
    cutoff = datetime.now(UTC) - timedelta(days=days)

    lines = MEMORY_FILE.read_text(encoding="utf-8").splitlines()
    retained = []
    removed = 0

    for line in lines:
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
            entry = _parse_entry(payload)
            if entry is None:
                # Preserve lines that parse as JSON but don't match our schema
                retained.append(line)
                continue
            # Keep entries newer than cutoff
            entry_time = datetime.fromisoformat(entry.timestamp_utc.replace("Z", "+00:00"))
            # Handle naive timestamps (no timezone info)
            if entry_time.tzinfo is None:
                entry_time = entry_time.replace(tzinfo=UTC)
            if entry_time >= cutoff:
                retained.append(line)
            else:
                removed += 1
        except (json.JSONDecodeError, ValueError):
            # Preserve unparseable lines
            retained.append(line)

    MEMORY_FILE.write_text("\n".join(retained) + "\n" if retained else "", encoding="utf-8")
    return removed

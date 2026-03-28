"""Opportunity Scanner — repo health signals → top-N improvement proposals.

Collects deterministic signals from configured repos via gh CLI, then uses
a single Haiku LLM call to surface the most impactful opportunities.

Signal types:
- Stale issues   : open issues not updated in > STALE_ISSUE_DAYS
- Stale PRs      : open PRs not updated in > STALE_PR_DAYS
- CI instability : recent workflow run failure rate
- Milestone drift: open milestones with low completion percentage
- Critical backlog: priority:high issues not updated in > CRITICAL_DAYS
"""
from __future__ import annotations

import json as _json
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

from jarvis.config import RuntimeConfig


ROOT_DIR = Path(__file__).resolve().parents[2]
REPORTS_DIR = ROOT_DIR / "reports"
REPOS_CONF = ROOT_DIR / "skills" / "triage" / "repos.conf"

STALE_ISSUE_DAYS = 14
STALE_PR_DAYS = 5
CRITICAL_DAYS = 30
CI_RUNS_SAMPLE = 20
MAX_OPPORTUNITIES = 5


# ── Data classes ─────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Opportunity:
    title: str
    category: str   # stale-work | ci-instability | milestone-drift | critical-backlog
    repo: str
    rationale: str
    effort: str     # low | medium | high
    impact: str     # low | medium | high
    confidence: float


@dataclass
class RepoSignals:
    repo: str
    stale_issues: list[dict] = field(default_factory=list)
    stale_prs: list[dict] = field(default_factory=list)
    ci_failure_rate: float = 0.0
    ci_runs_sampled: int = 0
    milestone_drift: list[dict] = field(default_factory=list)
    critical_backlog: int = 0
    fetch_errors: list[str] = field(default_factory=list)


@dataclass
class OpportunityScanResult:
    opportunities: tuple[Opportunity, ...]
    report_text: str
    report_path: Path
    scan_timestamp: str
    repos_scanned: int
    success: bool
    error: str = ""


# ── Helpers ───────────────────────────────────────────────────────────────────


def _load_repos() -> list[str]:
    """Load repo list from repos.conf. Returns empty list if missing."""
    if not REPOS_CONF.exists():
        return []
    repos = []
    for line in REPOS_CONF.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "/" in line:
            repos.append(line)
    return repos


def _run_gh(args: list[str], timeout: int = 30) -> tuple[bool, str]:
    """Run a gh CLI command. Returns (success, stdout)."""
    if shutil.which("gh") is None:
        return False, "gh CLI not found"
    try:
        result = subprocess.run(
            ["gh"] + args,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
        if result.returncode != 0:
            return False, result.stderr.strip() or "gh command failed"
        return True, result.stdout.strip()
    except subprocess.TimeoutExpired:
        return False, "gh command timed out"
    except Exception as exc:
        return False, str(exc)


def _days_ago(iso_str: str) -> float:
    """Return how many days ago an ISO timestamp was. Returns 0 on parse error."""
    try:
        ts = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        return (datetime.now(UTC) - ts).total_seconds() / 86400
    except (ValueError, TypeError):
        return 0.0


def _parse_json(raw: str) -> list[dict]:
    """Parse JSON array; return empty list on error."""
    if not raw:
        return []
    try:
        data = _json.loads(raw)
        return data if isinstance(data, list) else []
    except _json.JSONDecodeError:
        return []


# ── Signal collectors ────────────────────────────────────────────────────────


def _fetch_stale_issues(repo: str) -> tuple[list[dict], str]:
    """Return issues not updated in > STALE_ISSUE_DAYS days."""
    ok, out = _run_gh([
        "issue", "list", "--repo", repo, "--state", "open",
        "--json", "number,title,updatedAt,labels",
        "--limit", "200",
    ])
    if not ok:
        return [], out

    cutoff = STALE_ISSUE_DAYS
    stale = []
    for issue in _parse_json(out):
        age = _days_ago(issue.get("updatedAt", ""))
        if age >= cutoff:
            stale.append({
                "number": issue.get("number"),
                "title": issue.get("title", "")[:80],
                "days_stale": round(age, 1),
            })
    return stale, ""


def _fetch_stale_prs(repo: str) -> tuple[list[dict], str]:
    """Return open PRs not updated in > STALE_PR_DAYS days."""
    ok, out = _run_gh([
        "pr", "list", "--repo", repo, "--state", "open",
        "--json", "number,title,updatedAt,isDraft,reviewDecision",
        "--limit", "100",
    ])
    if not ok:
        return [], out

    cutoff = STALE_PR_DAYS
    stale = []
    for pr in _parse_json(out):
        age = _days_ago(pr.get("updatedAt", ""))
        if age >= cutoff and not pr.get("isDraft"):
            stale.append({
                "number": pr.get("number"),
                "title": pr.get("title", "")[:80],
                "days_stale": round(age, 1),
                "review": pr.get("reviewDecision", ""),
            })
    return stale, ""


def _fetch_ci_stats(repo: str) -> tuple[float, int, str]:
    """Return (failure_rate, runs_sampled, error) from recent CI runs."""
    ok, out = _run_gh([
        "run", "list", "--repo", repo,
        "--json", "conclusion",
        "--limit", str(CI_RUNS_SAMPLE),
    ])
    if not ok:
        return 0.0, 0, out

    runs = _parse_json(out)
    if not runs:
        return 0.0, 0, ""

    failures = sum(1 for r in runs if r.get("conclusion") in {"failure", "timed_out"})
    return round(failures / len(runs), 2), len(runs), ""


def _fetch_milestone_drift(repo: str) -> tuple[list[dict], str]:
    """Return open milestones with their completion percentage."""
    ok, out = _run_gh([
        "api", f"repos/{repo}/milestones",
        "--jq", "[.[] | {title:.title, open:.open_issues, closed:.closed_issues}]",
    ])
    if not ok:
        return [], out

    drift = []
    for ms in _parse_json(out):
        total = ms.get("open", 0) + ms.get("closed", 0)
        if total == 0:
            continue
        pct = round(ms["closed"] / total * 100, 1)
        if ms["open"] > 0:  # only milestones with open work
            drift.append({
                "name": ms.get("title", ""),
                "open": ms["open"],
                "closed": ms["closed"],
                "pct_done": pct,
            })
    return drift, ""


def _fetch_critical_backlog(repo: str) -> tuple[int, str]:
    """Count priority:high issues open for > CRITICAL_DAYS days."""
    ok, out = _run_gh([
        "issue", "list", "--repo", repo, "--state", "open",
        "--label", "priority:high",
        "--json", "number,updatedAt,createdAt",
        "--limit", "100",
    ])
    if not ok:
        return 0, out

    count = sum(
        1 for issue in _parse_json(out)
        if _days_ago(issue.get("createdAt", "")) >= CRITICAL_DAYS
    )
    return count, ""


# ── Signal aggregation ───────────────────────────────────────────────────────


def _gather_signals(repo: str) -> RepoSignals:
    """Collect all signals for one repo. Errors are stored, not raised."""
    signals = RepoSignals(repo=repo)

    stale_issues, err = _fetch_stale_issues(repo)
    signals.stale_issues = stale_issues
    if err:
        signals.fetch_errors.append(f"issues: {err}")

    stale_prs, err = _fetch_stale_prs(repo)
    signals.stale_prs = stale_prs
    if err:
        signals.fetch_errors.append(f"prs: {err}")

    ci_rate, ci_count, err = _fetch_ci_stats(repo)
    signals.ci_failure_rate = ci_rate
    signals.ci_runs_sampled = ci_count
    if err:
        signals.fetch_errors.append(f"ci: {err}")

    drift, err = _fetch_milestone_drift(repo)
    signals.milestone_drift = drift
    if err:
        signals.fetch_errors.append(f"milestones: {err}")

    critical, err = _fetch_critical_backlog(repo)
    signals.critical_backlog = critical
    if err:
        signals.fetch_errors.append(f"critical: {err}")

    return signals


def _signals_to_text(all_signals: list[RepoSignals]) -> str:
    """Render collected signals as a compact text block for LLM input."""
    lines = []
    for s in all_signals:
        lines.append(f"=== {s.repo} ===")
        lines.append(f"Stale issues (>{STALE_ISSUE_DAYS}d): {len(s.stale_issues)}")
        for i in s.stale_issues[:3]:
            lines.append(f"  #{i['number']}: {i['title']} ({i['days_stale']}d)")
        lines.append(f"Stale PRs (>{STALE_PR_DAYS}d, non-draft): {len(s.stale_prs)}")
        for p in s.stale_prs[:3]:
            lines.append(f"  #{p['number']}: {p['title']} ({p['days_stale']}d, review={p.get('review','?')})")
        if s.ci_runs_sampled > 0:
            lines.append(f"CI failure rate (last {s.ci_runs_sampled} runs): {s.ci_failure_rate:.0%}")
        lines.append(f"Critical backlog (priority:high, >{CRITICAL_DAYS}d): {s.critical_backlog}")
        if s.milestone_drift:
            lines.append("Open milestones:")
            for ms in s.milestone_drift[:3]:
                lines.append(f"  {ms['name']}: {ms['pct_done']}% done ({ms['open']} open)")
        if s.fetch_errors:
            lines.append(f"[fetch errors: {'; '.join(s.fetch_errors)}]")
        lines.append("")
    return "\n".join(lines)


# ── LLM analysis ─────────────────────────────────────────────────────────────


_ANALYSIS_PROMPT = """\
You are Jarvis's opportunity scanner. Given project health signals from GitHub repos,
identify the top {max_n} most impactful improvement opportunities.

Signals:
{signals}

Respond ONLY with a JSON array (no markdown fences, no extra text):
[
  {{
    "title": "concise opportunity title",
    "category": "stale-work|ci-instability|milestone-drift|critical-backlog",
    "repo": "owner/repo",
    "rationale": "1-2 sentence explanation of why this matters now",
    "effort": "low|medium|high",
    "impact": "low|medium|high",
    "confidence": 0.0-1.0
  }}
]

Rules:
- Each opportunity must map to a concrete signal above (no hallucination).
- Rank by impact × confidence descending.
- Skip repos with no significant signals.
- Max {max_n} items total.
"""


async def _analyze_with_llm(
    all_signals: list[RepoSignals],
    config: RuntimeConfig,
) -> list[Opportunity]:
    """Run LLM analysis on collected signals. Returns [] on failure."""
    from jarvis.executor import execute_query  # noqa: WPS433

    signals_text = _signals_to_text(all_signals)
    prompt = _ANALYSIS_PROMPT.format(signals=signals_text, max_n=MAX_OPPORTUNITIES)

    result = await execute_query(
        prompt,
        model="haiku",
        allowed_tools=[],
        max_budget_usd=min(0.10, config.budget.per_query_usd),
    )

    if not result.success:
        return []

    raw = result.text.strip()
    # Strip markdown fences if present.
    raw = re.sub(r"^```[a-z]*\n?", "", raw)
    raw = re.sub(r"\n?```$", "", raw)
    raw = raw.strip()

    try:
        items = _json.loads(raw)
        if not isinstance(items, list):
            return []
        opportunities = []
        for item in items[:MAX_OPPORTUNITIES]:
            if not isinstance(item, dict):
                continue
            try:
                opp = Opportunity(
                    title=str(item.get("title", ""))[:120],
                    category=str(item.get("category", ""))[:40],
                    repo=str(item.get("repo", ""))[:60],
                    rationale=str(item.get("rationale", ""))[:300],
                    effort=str(item.get("effort", "medium"))[:10],
                    impact=str(item.get("impact", "medium"))[:10],
                    confidence=float(item.get("confidence", 0.5)),
                )
                opportunities.append(opp)
            except (ValueError, TypeError):
                continue
        return opportunities
    except (_json.JSONDecodeError, ValueError):
        return []


# ── Report writer ─────────────────────────────────────────────────────────────


def _impact_rank(opp: Opportunity) -> float:
    """Numeric rank for sorting: impact × confidence."""
    impact_map = {"high": 3, "medium": 2, "low": 1}
    return impact_map.get(opp.impact, 2) * opp.confidence


def _write_report(
    opportunities: list[Opportunity],
    all_signals: list[RepoSignals],
    timestamp: str,
) -> tuple[str, Path]:
    """Render markdown report and save to reports/."""
    lines = [
        f"# Opportunity Scan — {timestamp}",
        "",
        f"**Repos scanned:** {len(all_signals)}  ",
        f"**Opportunities found:** {len(opportunities)}",
        "",
    ]

    if opportunities:
        lines.append("## Top Opportunities\n")
        for i, opp in enumerate(opportunities, 1):
            impact_badge = {"high": "HIGH", "medium": "MED", "low": "LOW"}.get(opp.impact, opp.impact.upper())
            lines.append(f"### {i}. [{impact_badge} IMPACT] {opp.title}")
            lines.append(f"- **Repo**: `{opp.repo}`")
            lines.append(f"- **Category**: {opp.category}")
            lines.append(f"- **Rationale**: {opp.rationale}")
            lines.append(f"- **Effort**: {opp.effort} | **Impact**: {opp.impact} | **Confidence**: {opp.confidence:.2f}")
            lines.append("")
    else:
        lines.append("No significant opportunities detected.\n")

    lines.append("## Signal Summary\n")
    for s in all_signals:
        lines.append(f"### {s.repo}")
        lines.append(f"- Stale issues: {len(s.stale_issues)}")
        lines.append(f"- Stale PRs: {len(s.stale_prs)}")
        if s.ci_runs_sampled > 0:
            lines.append(f"- CI failure rate: {s.ci_failure_rate:.0%} (last {s.ci_runs_sampled} runs)")
        lines.append(f"- Critical backlog: {s.critical_backlog}")
        if s.milestone_drift:
            for ms in s.milestone_drift:
                lines.append(f"- Milestone '{ms['name']}': {ms['pct_done']}% done ({ms['open']} open)")
        if s.fetch_errors:
            lines.append(f"- ⚠ Fetch errors: {'; '.join(s.fetch_errors)}")
        lines.append("")

    report_text = "\n".join(lines)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    slug = timestamp.replace(":", "").replace(" ", "-").replace("T", "-")[:19]
    report_path = REPORTS_DIR / f"opportunity-scan-{slug}.md"
    report_path.write_text(report_text, encoding="utf-8")
    return report_text, report_path


# ── Main pipeline ─────────────────────────────────────────────────────────────


async def run_opportunity_scan(config: RuntimeConfig) -> OpportunityScanResult:
    """Collect signals, analyze with LLM, write report."""
    timestamp = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S")

    repos = _load_repos()
    if not repos:
        msg = "No repos configured. Add entries to skills/triage/repos.conf."
        return OpportunityScanResult(
            opportunities=(),
            report_text=msg,
            report_path=Path("/dev/null"),
            scan_timestamp=timestamp,
            repos_scanned=0,
            success=False,
            error=msg,
        )

    all_signals: list[RepoSignals] = []
    for repo in repos:
        signals = _gather_signals(repo)
        all_signals.append(signals)

    opportunities = await _analyze_with_llm(all_signals, config)
    opportunities.sort(key=_impact_rank, reverse=True)

    report_text, report_path = _write_report(opportunities, all_signals, timestamp)

    # Record in work memory for false-positive tracking.
    try:
        from jarvis.work_memory import WorkMemoryEntry, append_work_memory  # noqa: WPS433
        append_work_memory(WorkMemoryEntry(
            timestamp_utc=timestamp,
            workflow="opportunity-scan",
            project=",".join(repos),
            objective="surface top improvement opportunities",
            attempted_actions=tuple(f"{o.title} ({o.repo})" for o in opportunities),
            blockers=tuple(
                f"{s.repo}: {'; '.join(s.fetch_errors)}"
                for s in all_signals if s.fetch_errors
            ),
            next_steps=(),
            status="completed",
            metadata={
                "repos_scanned": len(repos),
                "opportunities_found": len(opportunities),
                "report_path": str(report_path),
            },
        ))
    except Exception:
        pass  # non-critical

    return OpportunityScanResult(
        opportunities=tuple(opportunities),
        report_text=report_text,
        report_path=report_path,
        scan_timestamp=timestamp,
        repos_scanned=len(repos),
        success=True,
    )


async def handle(config: RuntimeConfig, args: str) -> "SkillResult":
    """Skill handler entry point — called by dispatcher auto-discovery."""
    from jarvis.dispatcher import SkillResult  # noqa: WPS433

    result = await run_opportunity_scan(config)

    if not result.success:
        return SkillResult(text=result.error, success=False)

    summary = (
        f"Scan complete: {result.repos_scanned} repos, "
        f"{len(result.opportunities)} opportunities found.\n"
        f"Report: {result.report_path}\n\n"
    )
    # Prepend short summary, then full report (trimmed for Telegram).
    preview = result.report_text[:3000]
    if len(result.report_text) > 3000:
        preview += "\n\n[... truncated — see report file for full details]"

    return SkillResult(text=summary + preview, success=True)

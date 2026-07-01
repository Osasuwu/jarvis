"""I/O adapter for status synthesis (#1015).

Reads repos.conf, gathers per-repo state via gh/git, queries Supabase decisions.
Produces structured output for status_engine (#1013) to consume.

Every source is stamped with provenance {ran, ok, input_rows, age} so the
renderer can distinguish "all clear" from "the gather silently failed".

Design pattern — pure functions over injectable I/O callbacks. The public
gather() function accepts optional callbacks for every side-effect boundary;
callers that omit them get real subprocess/HTTP implementations. Tests pass
fixture-returning lambdas — no mocking framework required.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import yaml

# ============================================================================
# Public constants
# ============================================================================

SUPABASE_URL_ENV = "SUPABASE_URL"
SUPABASE_KEY_ENV = "SUPABASE_KEY"
REPOS_CONF_RELPATH = "config/repos.conf"
DEVICE_CONF_RELPATH = "config/device.json"

# ============================================================================
# Provenance
# ============================================================================


@dataclass
class Provenance:
    """Provenance stamp for one gathered source.

    Fields:
        ran: True if the gather attempted this source.
        ok: True if the source returned data without error.
        input_rows: Number of result rows (-1 for non-row sources like git).
        age: Seconds since data was gathered (None if !ran).
    """

    ran: bool = False
    ok: bool = False
    input_rows: int = -1
    age: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "ran": self.ran,
            "ok": self.ok,
            "input_rows": self.input_rows,
            "age": self.age,
        }


# ============================================================================
# Canonical source identifiers
# ============================================================================


class SourceKind:
    """Canonical source identifiers for provenance tracking."""

    REPOS_CONF = "repos_conf"
    GIT_STATE = "git_state"
    GH_PRS = "gh_prs"
    GH_ISSUES = "gh_issues"
    GH_CI = "gh_ci"
    GH_MILESTONES = "gh_milestones"
    GH_PROJECTS = "gh_projects"
    SUPABASE_DECISIONS = "supabase_decisions"
    STATUS_SNAPSHOT = "status_snapshot"


# ============================================================================
# Data structures — contract for status_engine (#1013)
# ============================================================================


@dataclass
class DecisionRecord:
    """One decision_made episode from Supabase."""

    id: str
    actor: str
    decision: str
    rationale: str
    created_at: str
    payload: dict

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "actor": self.actor,
            "decision": self.decision,
            "rationale": self.rationale,
            "created_at": self.created_at,
            "payload": self.payload,
        }


@dataclass
class GatherResult:
    """Complete gather output — the contract for status_engine.analyze().

    Fields:
        repos: Per-repo gathered state dicts (name, git, prs, issues, etc.).
        decisions: Decision_made episodes from Supabase.
        baselines: Status-record snapshots (may be None/empty on first run
                   or non-cron device).
        provenance: Top-level provenance for sources not scoped to a repo
                    (repos.conf parsing, Supabase query).
        gathered_at: ISO 8601 UTC timestamp.
        errors: Non-fatal error messages from individual sources.
    """

    repos: list[dict] = field(default_factory=list)
    decisions: list[DecisionRecord] = field(default_factory=list)
    baselines: list[dict] | None = None
    provenance: dict[str, dict] = field(default_factory=dict)
    gathered_at: str = ""
    errors: list[str] = field(default_factory=list)
    contradiction_cache: dict | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "repos": self.repos,
            "decisions": [d.to_dict() for d in self.decisions],
            "baselines": self.baselines,
            "provenance": self.provenance,
            "gathered_at": self.gathered_at,
            "errors": self.errors,
            "contradiction_cache": self.contradiction_cache,
        }


# ============================================================================
# I/O adapter types — injectable callbacks
# ============================================================================

# read_repos_conf(path) -> list[str] (owner/repo lines)
ReadReposConfFn = Callable[[str], list[str]]

# read_repos_conf_projects(path) -> dict[str, int] (owner/repo -> project number)
ReadReposConfProjectsFn = Callable[[str], dict]

# read_device_json(path) -> dict | None (parsed device.json or None)
ReadDeviceJsonFn = Callable[[str], dict | None]

# run_git(repo_path, args) -> dict with {stdout, returncode}
RunGitFn = Callable[[str, list[str]], dict]

# run_gh(repo, args) -> dict with {stdout, stderr, returncode}
RunGhFn = Callable[[str, list[str]], dict]

# query_supabase(url, key, table, params) -> list[dict] | None
QuerySupabaseFn = Callable[[str, str, str, dict], list[dict] | None]

# now_fn() -> float (epoch seconds)
NowFn = Callable[[], float]


# ============================================================================
# Default I/O implementations
# ============================================================================


def _default_read_file(path: str) -> str | None:
    try:
        return Path(path).read_text(encoding="utf-8")
    except (OSError, FileNotFoundError):
        return None


def _default_read_repos_conf(path: str) -> list[str]:
    """Read owner/repo lines from repos.conf, skipping comments and blanks."""
    raw = _default_read_file(path)
    if raw is None:
        return []
    return parse_repos_conf(raw)


def _default_read_repos_conf_projects(path: str) -> dict:
    """Read owner/repo → project-number map from repos.conf (#1059).

    Only lines carrying a ``project=<N>`` token contribute an entry; a repo
    without one simply has no ProjectV2 board configured and is skipped by the
    project-status fetch. Empty/unreadable file → empty map.
    """
    raw = _default_read_file(path)
    if raw is None:
        return {}
    return parse_repos_conf_projects(raw)


def _default_read_device_json(path: str) -> dict | None:
    raw = _default_read_file(path)
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def _default_run_git(repo_path: str, args: list[str]) -> dict:
    try:
        result = subprocess.run(
            ["git", "-C", repo_path, *args],
            capture_output=True, text=True, stdin=subprocess.DEVNULL,
            encoding="utf-8", errors="replace", timeout=15,
        )
        return {"stdout": result.stdout.strip(), "stderr": result.stderr.strip(),
                "returncode": result.returncode}
    except (OSError, subprocess.SubprocessError) as exc:
        return {"stdout": "", "stderr": str(exc), "returncode": -1}


def _default_run_gh(repo: str, args: list[str]) -> dict:
    # `gh api` addresses the repo through the URL path (repos/<owner>/<name>/...)
    # and rejects a trailing `--repo` flag ("unknown flag: --repo") — appending
    # it unconditionally made every milestone gather fail. Every other gh
    # subcommand needs `--repo` to target the right repo.
    cmd = ["gh", *args] if args and args[0] == "api" else ["gh", *args, "--repo", repo]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True, text=True, stdin=subprocess.DEVNULL,
            encoding="utf-8", errors="replace", timeout=30,
        )
        return {"stdout": result.stdout.strip(), "stderr": result.stderr.strip(),
                "returncode": result.returncode}
    except (OSError, subprocess.SubprocessError) as exc:
        return {"stdout": "", "stderr": str(exc), "returncode": -1}


def _default_query_supabase(
    url: str, key: str, table: str, params: dict,
) -> list[dict] | None:
    """Query Supabase table via REST API (direct execute_sql equivalent).

    Uses the Supabase REST API directly (not memory-MCP) to query the episodes
    table. The anon key has SELECT on episodes per the RLS policy.
    """
    import httpx

    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Accept": "application/json",
    }

    # Build query params for Supabase REST API
    query_parts: list[str] = []
    for k, v in params.items():
        if v is not None:
            query_parts.append(f"{k}={v}")

    url_str = f"{url.rstrip('/')}/rest/v1/{table}"
    if query_parts:
        url_str += "?" + "&".join(query_parts)

    try:
        resp = httpx.get(url_str, headers=headers, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, list):
            return data
        return [data] if data else []
    except Exception:
        return None


# ============================================================================
# Repo parsing
# ============================================================================


def parse_repos_conf(raw: str) -> list[str]:
    """Parse repos.conf content into owner/repo list (pure, tested directly).

    A line may carry trailing key=value tokens (e.g. ``project=3``, #1059);
    only the first whitespace-delimited token — the ``owner/repo`` — is the
    repo identifier. Bare lines (no tokens) are returned unchanged.
    """
    repos: list[str] = []
    for line in raw.splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            repos.append(line.split()[0])
    return repos


def parse_repos_conf_projects(raw: str) -> dict:
    """Parse repos.conf ``project=<N>`` tokens into owner/repo → int map (#1059).

    Only lines with a parseable ``project=<int>`` token yield an entry; lines
    without one (or with a non-integer value) are omitted, so a repo with no
    ProjectV2 board is simply absent from the map. Pure, tested directly.
    """
    projects: dict[str, int] = {}
    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        tokens = line.split()
        repo = tokens[0]
        for tok in tokens[1:]:
            if tok.startswith("project="):
                try:
                    projects[repo] = int(tok.split("=", 1)[1])
                except ValueError:
                    pass
    return projects


# ============================================================================
# Per-repo gather helpers
# ============================================================================


def _gather_git_state(
    repo_path: str,
    run_git: RunGitFn,
    now: float,
) -> tuple[dict, Provenance]:
    """Gather git state for one repo locally."""
    start = time.time()
    branch_result = run_git(repo_path, ["branch", "--show-current"])
    status_result = run_git(repo_path, ["status", "--short"])

    ok = branch_result["returncode"] == 0
    elapsed = time.time() - start

    prov = Provenance(ran=True, ok=ok, input_rows=-1, age=elapsed)
    if not ok:
        return {"branch": None, "clean": None}, prov

    return {
        "branch": branch_result["stdout"],
        "clean": len(status_result["stdout"]) == 0,
    }, prov


def _gather_gh_prs(repo: str, run_gh: RunGhFn, now: float) -> tuple[dict, Provenance]:
    """Gather open PRs for one repo."""
    start = time.time()
    result = run_gh(repo, [
        "pr", "list", "--state", "open",
        "--json", "number,title,createdAt,updatedAt,reviewDecision,isDraft,labels,headRefName",
        "--limit", "100",
    ])

    elapsed = time.time() - start
    ok = result["returncode"] == 0
    data: list[dict] = []
    truncated = False

    if ok and result["stdout"]:
        try:
            data = json.loads(result["stdout"])
        except json.JSONDecodeError:
            ok = False
    if len(data) >= 100:
        truncated = True

    prov = Provenance(ran=True, ok=ok, input_rows=len(data), age=elapsed)
    return {"prs": data, "prs_truncated": truncated}, prov


def _gather_gh_issues(
    repo: str, run_gh: RunGhFn, now: float,
) -> tuple[dict, Provenance]:
    """Gather open issues for one repo."""
    start = time.time()
    result = run_gh(repo, [
        "issue", "list", "--state", "open",
        "--json", "number,title,labels,updatedAt,milestone",
        "--limit", "100",
    ])

    elapsed = time.time() - start
    ok = result["returncode"] == 0
    data: list[dict] = []
    truncated = False

    if ok and result["stdout"]:
        try:
            data = json.loads(result["stdout"])
        except json.JSONDecodeError:
            ok = False
    if len(data) >= 100:
        truncated = True

    prov = Provenance(ran=True, ok=ok, input_rows=len(data), age=elapsed)
    return {"issues": data, "issues_truncated": truncated}, prov


def _gather_gh_ci(repo: str, run_gh: RunGhFn, now: float) -> tuple[dict, Provenance]:
    """Gather recent CI runs for one repo."""
    start = time.time()
    result = run_gh(repo, [
        "run", "list", "--json", "conclusion,name,createdAt,headBranch",
        "--limit", "10",
    ])

    elapsed = time.time() - start
    ok = result["returncode"] == 0
    data: list[dict] = []

    if ok and result["stdout"]:
        try:
            data = json.loads(result["stdout"])
        except json.JSONDecodeError:
            ok = False

    prov = Provenance(ran=True, ok=ok, input_rows=len(data), age=elapsed)
    return {"ci_runs": data}, prov


def _gather_gh_milestones(
    repo: str, run_gh: RunGhFn, now: float,
) -> tuple[dict, Provenance]:
    """Gather open milestones for one repo (redrobot-asymmetric source)."""
    start = time.time()
    # Use gh api directly since gh milestone list has different shapes
    result = run_gh(repo, [
        "api", f"repos/{repo}/milestones?state=open&per_page=50",
        "--jq", ".[] | {number, title, open_issues, closed_issues, due_on}",
    ])

    elapsed = time.time() - start
    ok = result["returncode"] == 0
    data: list[dict] = []
    truncated = False

    if ok and result["stdout"]:
        try:
            # May be multiple lines of JSON (one per milestone)
            lines = result["stdout"].splitlines()
            for line in lines:
                if line.strip():
                    data.append(json.loads(line))
        except json.JSONDecodeError:
            ok = False
    if len(data) >= 50:
        truncated = True

    prov = Provenance(ran=True, ok=ok, input_rows=len(data), age=elapsed)
    return {"milestones": data, "milestones_truncated": truncated}, prov


# ============================================================================
# ProjectV2 status gather (#1059)
# ============================================================================

# GraphQL for a *user*-owned Project (owner from repo.split("/")[0]); the
# board tracked repos live under is a user project, not an org project.
_PROJECT_STATUS_QUERY = (
    "query($owner: String!, $number: Int!) {"
    "  user(login: $owner) {"
    "    projectV2(number: $number) {"
    "      items(first: 100) {"
    "        nodes {"
    "          content { ... on Issue { number } }"
    "          fieldValueByName(name: \"Status\") {"
    "            ... on ProjectV2ItemFieldSingleSelectValue { name }"
    "          }"
    "        }"
    "      }"
    "    }"
    "  }"
    "}"
)

_PROJECT_STATUS_JQ = (
    ".data.user.projectV2.items.nodes[] "
    "| select(.content.number != null) "
    "| {number: .content.number, status: (.fieldValueByName.name // null)}"
)


def _gather_project_status(
    repo: str, project_number: int, run_gh: RunGhFn, now: float,
) -> tuple[dict, Provenance]:
    """Fetch GitHub Projects v2 ``Status`` per issue number for one repo (#1059).

    Returns ({issue_number: status_string}, Provenance). A fetch failure (or
    malformed payload) yields an empty map with ok=False so the caller leaves
    ``project_status=None`` on every issue and surfaces a provenance gap rather
    than a false-green (AC5). Issues without a Status value are simply absent
    from the map (join leaves them None → detector treats as "not on board").
    """
    start = time.time()
    owner = repo.split("/")[0]
    result = run_gh(repo, [
        "api", "graphql",
        "-f", f"query={_PROJECT_STATUS_QUERY}",
        "-F", f"owner={owner}",
        "-F", f"number={project_number}",
        "--jq", _PROJECT_STATUS_JQ,
    ])

    elapsed = time.time() - start
    ok = result["returncode"] == 0
    status_by_number: dict[int, str] = {}

    if ok and result["stdout"]:
        try:
            for line in result["stdout"].splitlines():
                line = line.strip()
                if not line:
                    continue
                row = json.loads(line)
                num = row.get("number")
                status = row.get("status")
                if num is not None and status:
                    status_by_number[int(num)] = str(status)
        except (json.JSONDecodeError, ValueError, TypeError):
            ok = False
            status_by_number = {}

    prov = Provenance(ran=True, ok=ok, input_rows=len(status_by_number), age=elapsed)
    return status_by_number, prov


# ============================================================================
# Supabase decisions gather
# ============================================================================


def _make_decision_record(row: dict) -> DecisionRecord:
    """Convert a Supabase episodes row to a DecisionRecord (pure)."""
    payload = row.get("payload") or {}
    return DecisionRecord(
        id=str(row.get("id", "")),
        actor=str(row.get("actor", "")),
        decision=str(payload.get("decision", "")),
        rationale=str(payload.get("rationale", "")),
        created_at=str(row.get("created_at", "")),
        payload=payload,
    )


def gather_decisions(
    url: str,
    key: str,
    query_fn: QuerySupabaseFn,
    now: float,
) -> tuple[list[DecisionRecord], Provenance]:
    """Query Supabase episodes for decision_made records.

    Uses direct REST API (execute_sql equivalent) — NOT memory-MCP.
    """
    start = time.time()

    params = {
        "kind": "eq.decision_made",
        "select": "id,actor,kind,payload,created_at",
        "order": "created_at.desc",
        "limit": "100",
    }
    rows = query_fn(url, key, "episodes", params)

    elapsed = time.time() - start

    if rows is None:
        # Query failed entirely
        prov = Provenance(ran=True, ok=False, input_rows=0, age=elapsed)
        return [], prov

    if not rows:
        # Query succeeded but empty
        prov = Provenance(ran=True, ok=True, input_rows=0, age=elapsed)
        return [], prov

    records = [_make_decision_record(r) for r in rows]
    prov = Provenance(ran=True, ok=True, input_rows=len(records), age=elapsed)
    return records, prov


# ============================================================================
# Contradiction-cache gather (#1016 AC3/AC4)
#
# The L1 status-record audit runs the memory↔git contradiction LLM ONCE and
# writes its verdicts into the `status-snapshot`-tagged memory as a fenced
# yaml block (schema contradiction-cache/v1). gather() reads that block back
# so the engine can FOLD the cached verdicts without re-running the LLM
# (AC4). Reading is pure deserialization — no LLM, no network beyond the
# single REST read that already fetches the snapshot row.
# ============================================================================

# Tolerant of a fence info-string (```yaml title=...) and of a trailing blank
# line before the closing fence — both are common Markdown emits (M1).
_YAML_FENCE_RE = re.compile(r"```ya?ml[^\n]*\n(.*?)\n?```", re.DOTALL)


def _extract_contradiction_cache(content: str) -> dict | None:
    """Pull the `contradiction_cache` dict out of a memory body.

    Fully tolerant: any parse failure, a missing fence, or a fence whose yaml
    has no `contradiction_cache` key returns None. Never raises.
    """
    if not content:
        return None

    for match in _YAML_FENCE_RE.finditer(content):
        block = match.group(1).strip()
        try:
            data = yaml.safe_load(block)
        except yaml.YAMLError:
            continue
        if isinstance(data, dict):
            cache = data.get("contradiction_cache")
            if isinstance(cache, dict):
                return cache
    return None


def _parse_iso_epoch(iso_str: str) -> float | None:
    """Parse an ISO 8601 timestamp to epoch seconds, or None on failure."""
    if not iso_str:
        return None
    try:
        s = iso_str.strip()
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        return datetime.fromisoformat(s).timestamp()
    except (ValueError, TypeError):
        return None


def gather_contradiction_cache(
    url: str,
    key: str,
    query_fn: QuerySupabaseFn,
    now: float,
) -> tuple[dict | None, Provenance]:
    """Read the cached L1 contradiction verdicts from the latest status snapshot.

    Queries the `memories` table for the most recent `status-snapshot`-tagged
    jarvis memory, extracts its fenced contradiction-cache yaml block, and
    returns it for the engine to fold. The cache's own `generated_at` drives
    the provenance age (data age, not query latency) so the renderer's
    freshness gate reflects when the LLM actually ran.

    Returns (cache_dict, provenance). cache is None and ok=False when the
    query fails, no snapshot exists, or the snapshot carries no cache block.
    """
    params = {
        "tags": "cs.{status-snapshot}",
        "project": "eq.jarvis",
        "select": "name,content,created_at",
        "order": "created_at.desc",
        "limit": "1",
        # Live-row filter (mirrors memory recall): never fold a snapshot that
        # was soft-deleted or expired/superseded out of belief.
        "deleted_at": "is.null",
        "expired_at": "is.null",
        # Trust boundary (#542/#565 RLS): a sandcastle agent can only write
        # rows whose source_provenance starts `sandcastle:`. An L1 baseline
        # written by the principal never carries that prefix, so reject it to
        # stop a sandcastle-poisoned snapshot from injecting forged verdicts.
        # NULL provenance (legacy/principal writes) still passes.
        "or": "(source_provenance.is.null,source_provenance.not.like.sandcastle:*)",
    }
    rows = query_fn(url, key, "memories", params)

    # A transport failure (None) and an empty result ([]) must NOT collapse
    # into the same provenance — a Supabase outage has to stay distinguishable
    # from a first-run device that simply has no snapshot yet. Mirrors the
    # gather_decisions None-vs-empty split.
    _failed = Provenance(ran=True, ok=False, input_rows=0, age=None)

    if rows is None:
        # Query failed entirely — transport/network error.
        return None, _failed

    if not rows:
        # Query succeeded, no snapshot row yet (first run / intraday pre-L1).
        # Empty is a legitimate non-error state, like gather_decisions.
        return None, Provenance(ran=True, ok=True, input_rows=0, age=None)

    content = rows[0].get("content") or ""
    cache = _extract_contradiction_cache(content)
    if cache is None:
        # Snapshot exists but carries no parseable cache block — treat as a
        # failed read of the cache, not an empty success.
        return None, _failed

    verdicts = cache.get("verdicts") or []
    gen_epoch = _parse_iso_epoch(str(cache.get("generated_at", "")))
    age = (now - gen_epoch) if gen_epoch is not None else None
    prov = Provenance(ran=True, ok=True, input_rows=len(verdicts), age=age)
    return cache, prov


# ============================================================================
# Main gather orchestrator
# ============================================================================


def gather(
    jarvis_home: str = "",
    *,
    # Injectable I/O callbacks (defaults = real implementations)
    read_repos_conf_fn: ReadReposConfFn | None = None,
    read_repos_conf_projects_fn: ReadReposConfProjectsFn | None = None,
    read_device_json_fn: ReadDeviceJsonFn | None = None,
    run_git_fn: RunGitFn | None = None,
    run_gh_fn: RunGhFn | None = None,
    query_supabase_fn: QuerySupabaseFn | None = None,
    now_fn: NowFn | None = None,
) -> GatherResult:
    """Gather state from all sources for status synthesis.

    Args:
        jarvis_home: Root path of the jarvis repo. If empty, auto-detect
                     from CWD via git rev-parse.
        read_repos_conf_fn: Callable to read repos.conf (default: file I/O).
        read_device_json_fn: Callable to read device.json (default: file I/O).
        run_git_fn: Callable to run git commands (default: subprocess).
        run_gh_fn: Callable to run repo-scoped gh commands (default: subprocess).
        query_supabase_fn: Callable for Supabase REST queries (default: httpx).
        now_fn: Callable returning epoch seconds (default: time.time).

    Returns:
        GatherResult with per-repo state, decisions, and provenance.
    """
    # Resolve defaults
    _read_conf = read_repos_conf_fn or _default_read_repos_conf
    _read_conf_projects = (
        read_repos_conf_projects_fn or _default_read_repos_conf_projects
    )
    _read_dev = read_device_json_fn or _default_read_device_json
    _run_git = run_git_fn or _default_run_git
    _run_gh = run_gh_fn or _default_run_gh
    _query_supabase = query_supabase_fn or _default_query_supabase
    _now = now_fn or time.time

    gather_start = _now()
    gathered_at = datetime.fromtimestamp(gather_start, tz=timezone.utc).isoformat()
    result = GatherResult(gathered_at=gathered_at)

    # --- Resolve jarvis_home via git rev-parse ---
    if not jarvis_home:
        try:
            git_result = subprocess.run(
                ["git", "rev-parse", "--show-toplevel"],
                capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=5,
            )
            if git_result.returncode == 0:
                jarvis_home = git_result.stdout.strip()
        except (OSError, subprocess.SubprocessError):
            pass

    if not jarvis_home:
        jarvis_home = os.getcwd()

    jarvis_path = Path(jarvis_home)

    # --- Step 1: Read repos.conf ---
    conf_path = str(jarvis_path / REPOS_CONF_RELPATH)
    repos = _read_conf(conf_path)

    if not repos:
        # Empty or unreadable repos.conf — provenance stamped but no repos to gather
        result.provenance[SourceKind.REPOS_CONF] = Provenance(
            ran=True, ok=False, input_rows=0,
            age=_now() - gather_start,
        ).to_dict()
        result.errors.append("repos.conf is empty, unreadable, or not found")
        return result

    result.provenance[SourceKind.REPOS_CONF] = Provenance(
        ran=True, ok=True, input_rows=len(repos),
        age=_now() - gather_start,
    ).to_dict()

    # Project-number map (owner/repo -> ProjectV2 number) from the same conf.
    # A repo absent from the map has no board configured; its issues keep
    # project_status=None and no gh_projects provenance is stamped (#1059 AC1).
    repos_projects = _read_conf_projects(conf_path) or {}

    # --- Step 2: Read device.json for repos_path ---
    dev_path = str(jarvis_path / DEVICE_CONF_RELPATH)
    device_conf = _read_dev(dev_path)
    repos_base = None
    if device_conf and isinstance(device_conf, dict):
        repos_base = device_conf.get("repos_path")

    # --- Step 3: Gather per-repo state ---
    for repo_name in repos:
        repo_name_stripped = repo_name.strip()
        repo_entry: dict[str, Any] = {
            "name": repo_name_stripped,
            "degraded": False,
            "degradation_reason": None,
            "provenance": {},
        }

        # Resolve local repo path
        local_repo_path: str | None = None
        if repos_base and isinstance(repos_base, str):
            _path = Path(repos_base) / repo_name_stripped.split("/")[-1]
            if _path.is_dir():
                local_repo_path = str(_path)

        # Git state (local)
        if local_repo_path:
            git_state, git_prov = _gather_git_state(local_repo_path, _run_git, _now())
            repo_entry.update(git_state)
            repo_entry["provenance"][SourceKind.GIT_STATE] = git_prov.to_dict()
        else:
            repo_entry["branch"] = None
            repo_entry["clean"] = None
            repo_entry["provenance"][SourceKind.GIT_STATE] = Provenance(
                ran=True, ok=False, input_rows=-1,
                age=_now() - gather_start,
            ).to_dict()

        # === Per-repo GitHub state ===
        # Each gh call is independently provenanced — a failure in one source
        # degrades that source only, never the whole repo or other repos.

        # PRs
        prs_state, prs_prov = _gather_gh_prs(repo_name_stripped, _run_gh, _now())
        repo_entry.update(prs_state)
        repo_entry["provenance"][SourceKind.GH_PRS] = prs_prov.to_dict()

        # Issues
        issues_state, issues_prov = _gather_gh_issues(repo_name_stripped, _run_gh, _now())
        repo_entry.update(issues_state)
        repo_entry["provenance"][SourceKind.GH_ISSUES] = issues_prov.to_dict()

        # ProjectV2 Status — join onto issues by number (#1059 AC1). Only for
        # repos with a configured project number. The provenance is stamped at
        # TOP level (`gh_projects:<repo>`) so a fetch failure gates health via
        # compute_health_verdict rather than false-greening (AC5).
        project_number = repos_projects.get(repo_name_stripped)
        if project_number is not None:
            status_map, project_prov = _gather_project_status(
                repo_name_stripped, project_number, _run_gh, _now(),
            )
            for issue in repo_entry.get("issues") or []:
                issue["project_status"] = status_map.get(issue.get("number"))
            result.provenance[
                f"{SourceKind.GH_PROJECTS}:{repo_name_stripped}"
            ] = project_prov.to_dict()
            if not project_prov.ok:
                result.errors.append(
                    f"{SourceKind.GH_PROJECTS}:{repo_name_stripped}: "
                    f"ProjectV2 status fetch failed"
                )

        # CI
        ci_state, ci_prov = _gather_gh_ci(repo_name_stripped, _run_gh, _now())
        repo_entry.update(ci_state)
        repo_entry["provenance"][SourceKind.GH_CI] = ci_prov.to_dict()

        # Milestones — asymmetric source: redrobot may not have this
        milestones_state, milestones_prov = _gather_gh_milestones(
            repo_name_stripped, _run_gh, _now(),
        )
        if not milestones_prov.ok:
            # Degrade this repo's milestone source but keep other sources
            repo_entry["degraded"] = True
            repo_entry["degradation_reason"] = (
                f"{SourceKind.GH_MILESTONES}: "
                f"failed (expected for repos without milestone access)"
            )
            repo_entry["milestones"] = None
            repo_entry["milestones_truncated"] = False
        else:
            repo_entry.update(milestones_state)
        repo_entry["provenance"][SourceKind.GH_MILESTONES] = milestones_prov.to_dict()

        result.repos.append(repo_entry)

    # --- Step 4: Query Supabase decisions ---
    supabase_url = os.environ.get(SUPABASE_URL_ENV, "")
    supabase_key = os.environ.get(SUPABASE_KEY_ENV, "")

    if supabase_url and supabase_key:
        decisions, decisions_prov = gather_decisions(
            supabase_url, supabase_key, _query_supabase, _now(),
        )
        result.decisions = decisions
        result.provenance[SourceKind.SUPABASE_DECISIONS] = decisions_prov.to_dict()
        if not decisions_prov.ok:
            result.errors.append(
                f"{SourceKind.SUPABASE_DECISIONS}: query returned no data or failed"
            )
    else:
        # Supabase not configured — non-fatal, provenance marks it unavailable
        result.provenance[SourceKind.SUPABASE_DECISIONS] = Provenance(
            ran=True, ok=False, input_rows=0,
            age=_now() - gather_start,
        ).to_dict()
        result.errors.append(
            f"{SourceKind.SUPABASE_DECISIONS}: {SUPABASE_URL_ENV}/{SUPABASE_KEY_ENV} unset"
        )

    # --- Step 5: Status-snapshot contradiction cache (optional — tolerate gap) ---
    # The L1 status-record audit writes the cached memory↔git contradiction
    # verdicts into the `status-snapshot`-tagged memory. We read them back here
    # (pure deserialization, no LLM — #1016 AC4) so the engine can fold them.
    # On first run, a non-cron device, or a missing snapshot, the read is !ok
    # and the engine/renderer treats it as stale/no-baseline.
    if supabase_url and supabase_key:
        cache, snap_prov = gather_contradiction_cache(
            supabase_url, supabase_key, _query_supabase, _now(),
        )
        result.contradiction_cache = cache
        result.provenance[SourceKind.STATUS_SNAPSHOT] = snap_prov.to_dict()
        if not snap_prov.ok:
            result.errors.append(
                f"{SourceKind.STATUS_SNAPSHOT}: no fresh status snapshot available"
            )
    else:
        # No creds ⇒ nothing was gathered, so data age is undefined (None), not
        # time-since-gather-start (m3). ok=False already signals the gap.
        result.provenance[SourceKind.STATUS_SNAPSHOT] = Provenance(
            ran=True, ok=False, input_rows=0, age=None,
        ).to_dict()
        result.errors.append(
            f"{SourceKind.STATUS_SNAPSHOT}: {SUPABASE_URL_ENV}/{SUPABASE_KEY_ENV} unset"
        )

    return result


# ============================================================================
# CLI
# ============================================================================


def main(argv: list[str] | None = None) -> int:
    """Run gather and print result as JSON to stdout."""
    result = gather()
    json.dump(result.to_dict(), sys.stdout, indent=2, default=str)
    return 0 if not result.errors else 1


if __name__ == "__main__":
    sys.exit(main())

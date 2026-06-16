"""Auditor — thin gh/REST shell that dumps a repo's real GitHub setup.

Slice 1 of repo-baseline (milestone #48), the dependency root. The Auditor
reads each repo's labels / workflows / settings / branch-protection /
dependabot ecosystems and emits a structured :class:`RepoSnapshot`. The
committed JSON snapshots become the canonical fixtures every downstream
pure-core test runs against, and :func:`seed_manifest` derives a per-repo
:class:`~scripts.repo_baseline.manifest.Manifest` skeleton from a snapshot.

The gh/REST boundary is a single injected *runner* callable so the parsing
logic is fully unit-testable against canned ``gh api`` JSON — no live calls,
no network. The live runner (:func:`gh_runner`) shells out to ``gh api``.
"""

from __future__ import annotations

import base64
import json
import re
import subprocess
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

import yaml


class GhNotFound(Exception):
    """Raised by a runner when a ``gh api`` path 404s.

    Used for *expected* absences — a repo with no branch protection or no
    ``.github/dependabot.yml`` — which the Auditor treats as "feature off",
    not an error.
    """


# A runner takes a gh api path (e.g. ``repos/Osasuwu/jarvis/labels``) and
# returns parsed JSON. ``paginate=True`` requests ``gh api --paginate``.
GhRunner = Callable[..., Any]


# The baseline audit scope — the five Osasuwu repos named in the milestone #48
# PRD problem statement. NOT ``config/repos.conf`` (which is the narrower
# daily-triage list of jarvis + redrobot). ``SergazyNarynov/redrobot`` is
# out of scope here: a different owner, credential-blocked under the
# Osasuwu-only token, and deferred to issue #940.
OSASUWU_REPOS: List[str] = [
    "Osasuwu/jarvis",
    "Osasuwu/music-intel-mcp",
    "Osasuwu/like_spotify_mobile_app",
    "Osasuwu/dnd-calendar",
    "Osasuwu/farming-evolution",
]


# ── Snapshot value objects ───────────────────────────────────────────


@dataclass(frozen=True)
class LabelSnapshot:
    """A label as found on a repo — name + color + description."""

    name: str
    color: str = ""
    description: str = ""


@dataclass
class RepoSettings:
    """Repo-level merge/visibility settings (from ``GET /repos/{repo}``)."""

    allow_auto_merge: bool = False
    allow_squash_merge: bool = False
    allow_merge_commit: bool = False
    allow_rebase_merge: bool = False
    delete_branch_on_merge: bool = False
    visibility: str = "public"
    default_branch: str = "main"


@dataclass
class BranchProtection:
    """Required-status-check config on the default branch."""

    strict: bool = False
    contexts: List[str] = field(default_factory=list)


@dataclass
class RepoSnapshot:
    """Structured snapshot of a repo's real GitHub setup."""

    repo: str
    settings: RepoSettings
    labels: List[LabelSnapshot] = field(default_factory=list)
    workflows: List[str] = field(default_factory=list)
    branch_protection: Optional[BranchProtection] = None
    dependabot_ecosystems: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Structural dict for JSON serialization (no scrub — see
        :func:`scrub_topology`, applied at fixture-write time)."""
        return {
            "repo": self.repo,
            "settings": vars(self.settings).copy(),
            "labels": [vars(lb).copy() for lb in self.labels],
            "workflows": list(self.workflows),
            "branch_protection": (
                vars(self.branch_protection).copy() if self.branch_protection is not None else None
            ),
            "dependabot_ecosystems": list(self.dependabot_ecosystems),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RepoSnapshot":
        bp = data.get("branch_protection")
        return cls(
            repo=data["repo"],
            settings=RepoSettings(**data["settings"]),
            labels=[LabelSnapshot(**lb) for lb in data.get("labels", [])],
            workflows=list(data.get("workflows", [])),
            branch_protection=(BranchProtection(**bp) if bp is not None else None),
            dependabot_ecosystems=list(data.get("dependabot_ecosystems", [])),
        )


# ── Auditor ──────────────────────────────────────────────────────────


class Auditor:
    """Reads live repo state into a :class:`RepoSnapshot` via an injected runner."""

    def __init__(self, runner: GhRunner):
        self.runner = runner

    def audit(self, repo: str) -> RepoSnapshot:
        """Build a full snapshot for *repo* (``owner/name``)."""
        settings = self._read_settings(repo)
        return RepoSnapshot(
            repo=repo,
            settings=settings,
            labels=self._read_labels(repo),
            workflows=self._read_workflows(repo),
            branch_protection=self._read_branch_protection(repo, settings.default_branch),
            dependabot_ecosystems=self._read_dependabot_ecosystems(repo),
        )

    def audit_all(self, repos: List[str]) -> Dict[str, RepoSnapshot]:
        """Audit each repo in *repos*, returning a ``repo -> RepoSnapshot`` map.

        Iteration order follows *repos*; the dict preserves insertion order so
        the committed fixture set is deterministic.
        """
        return {repo: self.audit(repo) for repo in repos}

    # ── per-aspect readers ────────────────────────────────────────────

    def _read_settings(self, repo: str) -> RepoSettings:
        data = self.runner(f"repos/{repo}")
        return RepoSettings(
            allow_auto_merge=bool(data.get("allow_auto_merge", False)),
            allow_squash_merge=bool(data.get("allow_squash_merge", False)),
            allow_merge_commit=bool(data.get("allow_merge_commit", False)),
            allow_rebase_merge=bool(data.get("allow_rebase_merge", False)),
            delete_branch_on_merge=bool(data.get("delete_branch_on_merge", False)),
            visibility=data.get("visibility", "public"),
            default_branch=data.get("default_branch", "main"),
        )

    def _read_labels(self, repo: str) -> List[LabelSnapshot]:
        data = self.runner(f"repos/{repo}/labels", paginate=True)
        return [
            LabelSnapshot(
                name=lb["name"],
                color=lb.get("color", ""),
                description=lb.get("description") or "",
            )
            for lb in data
        ]

    def _read_workflows(self, repo: str) -> List[str]:
        data = self.runner(f"repos/{repo}/actions/workflows")
        return [wf["path"] for wf in data.get("workflows", [])]

    def _read_branch_protection(self, repo: str, default_branch: str) -> Optional[BranchProtection]:
        try:
            data = self.runner(f"repos/{repo}/branches/{default_branch}/protection")
        except GhNotFound:
            return None
        rsc = data.get("required_status_checks") or {}
        return BranchProtection(
            strict=bool(rsc.get("strict", False)),
            contexts=list(rsc.get("contexts", [])),
        )

    def _read_dependabot_ecosystems(self, repo: str) -> List[str]:
        try:
            data = self.runner(f"repos/{repo}/contents/.github/dependabot.yml")
        except GhNotFound:
            return []
        raw = base64.b64decode(data["content"]).decode("utf-8")
        parsed = yaml.safe_load(raw) or {}
        updates = parsed.get("updates", []) or []
        return [u["package-ecosystem"] for u in updates if "package-ecosystem" in u]


# ── Manifest seeding ─────────────────────────────────────────────────


def seed_manifest(snapshot: RepoSnapshot) -> Dict[str, Any]:
    """Derive a per-repo manifest dict from an observed snapshot.

    The seed captures *observed reality* as explicit axis values so the owner
    edits a populated skeleton rather than writing a manifest from scratch.

    Only the axes the snapshot actually observes are emitted — and they are
    emitted **explicitly**, including their absences (``auto_merge=False``,
    ``dependabot_ecosystems=[]``). Relying on the ``full`` profile's defaults
    for these would misreport a bare repo as fully baselined. Axes the snapshot
    does not capture (``runs_on``, ``ci_language``, ``code_review_marketplace``,
    ``test_extras`` — all buried inside workflow YAML bodies the auditor only
    records paths for) are left out so they resolve to the profile default; a
    downstream slice can deepen the audit to populate them.

    The result is a plain dict accepted unchanged by
    :meth:`~scripts.repo_baseline.manifest.Manifest.from_dict`.
    """
    bp = snapshot.branch_protection
    return {
        "repo": snapshot.repo,
        "profile": "full",
        "visibility": snapshot.settings.visibility,
        "auto_merge": snapshot.settings.allow_auto_merge,
        "branch_protection": bp is not None,
        "required_check_contexts": list(bp.contexts) if bp is not None else [],
        # The snapshot lists one ecosystem per dependabot update block, so a repo
        # with pip blocks for two directories yields a duplicated entry. The
        # manifest axis is a *set* of ecosystem types (directory granularity
        # lives in the managed file body, not the axis) — dedupe, first-seen order.
        "dependabot_ecosystems": _dedupe(snapshot.dependabot_ecosystems),
    }


def _dedupe(items: List[str]) -> List[str]:
    """Deduplicate preserving first-seen order (``dict.fromkeys`` idiom)."""
    return list(dict.fromkeys(items))


# ── Topology scrubbing (fixture-write hygiene) ───────────────────────

# jarvis is a PUBLIC repo: committed snapshot fixtures must not leak device or
# infra topology. The username segment is matched *positionally* (any user, not
# a hardcoded login) so the scrub survives a different operator on another
# device. Over-redaction is the safe direction here.
_TAILNET_IP_RE = re.compile(r"\b100\.\d{1,3}\.\d{1,3}\.\d{1,3}\b")
_WIN_USER_RE = re.compile(r"([A-Za-z]:\\Users\\)([^\\]+)")
_NIX_USER_RE = re.compile(r"(/(?:home|Users)/)([^/]+)")


def _scrub_str(value: str) -> str:
    value = _TAILNET_IP_RE.sub("<REDACTED-IP>", value)
    value = _WIN_USER_RE.sub(r"\1<user>", value)
    value = _NIX_USER_RE.sub(r"\1<user>", value)
    return value


def scrub_topology(data: Any) -> Any:
    """Recursively redact device/infra topology from a snapshot dict.

    Redacts tailnet IPs (``100.x.x.x``) and the username segment of Windows
    (``C:\\Users\\<user>``) and POSIX (``/home/<user>``, ``/Users/<user>``)
    home paths, in every string reachable through nested dicts/lists. Returns a
    new structure — the input is left untouched. A snapshot with no topology
    round-trips byte-identical.

    Applied at fixture-write time, never inside :meth:`RepoSnapshot.to_dict`
    (serialization and redaction are separate concerns — a live audit run may
    want the unscrubbed dict in memory).
    """
    if isinstance(data, str):
        return _scrub_str(data)
    if isinstance(data, dict):
        return {k: scrub_topology(v) for k, v in data.items()}
    if isinstance(data, list):
        return [scrub_topology(v) for v in data]
    return data


# ── Live gh/REST runner ──────────────────────────────────────────────


def _parse_concatenated_json(text: str) -> List[Any]:
    """Parse a stream of whitespace-separated JSON values into a list.

    ``gh api --paginate`` emits one JSON document per page with no separator,
    so a multi-page array response is ``[...][...]`` — not a single valid JSON
    document. A streaming ``raw_decode`` loop handles both the single-page and
    multi-page cases without depending on a particular ``gh`` version's
    ``--slurp`` behavior.
    """
    decoder = json.JSONDecoder()
    values: List[Any] = []
    idx, n = 0, len(text)
    while idx < n:
        while idx < n and text[idx].isspace():
            idx += 1
        if idx >= n:
            break
        value, end = decoder.raw_decode(text, idx)
        values.append(value)
        idx = end
    return values


def gh_runner(path: str, *, paginate: bool = False) -> Any:
    """Live runner — shells out to ``gh api`` and returns parsed JSON.

    A 404 is mapped to :class:`GhNotFound` so the Auditor can treat an absent
    branch protection / dependabot.yml as "feature off". Any other non-zero
    exit raises :class:`RuntimeError` with the captured stderr (never the
    response body, to avoid leaking anything sensitive into logs).

    With ``paginate=True`` the per-page JSON arrays are merged into one flat
    list (see :func:`_parse_concatenated_json`).
    """
    args = ["gh", "api", path]
    if paginate:
        args.append("--paginate")
    proc = subprocess.run(args, capture_output=True, text=True)
    if proc.returncode != 0:
        stderr = (proc.stderr or "").strip()
        if "404" in stderr or "Not Found" in stderr:
            raise GhNotFound(path)
        raise RuntimeError(f"gh api {path!r} failed (exit {proc.returncode}): {stderr}")

    if not paginate:
        return json.loads(proc.stdout)

    values = _parse_concatenated_json(proc.stdout)
    if values and all(isinstance(v, list) for v in values):
        flat: List[Any] = []
        for page in values:
            flat.extend(page)
        return flat
    if len(values) == 1:
        return values[0]
    return values

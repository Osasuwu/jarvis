"""Applier — the Executor side of repo-baseline (#939, milestone #48 slice 5).

Symmetric to the :class:`~scripts.repo_baseline.auditor.Auditor`: where the
Auditor is a pure-parse *reader* behind an injected ``gh`` runner, the Applier
is a pure *translator* that turns a Planner action plan into an ordered,
idempotency-filtered sequence of semantic mutations (:class:`GhCall`),
rendering MANAGED / LANGUAGE-TEST file content through the
:class:`~scripts.repo_baseline.renderer.Renderer` + canon templates on the way.

The ``Action.content`` field the Planner leaves ``None`` (its docstring names
this slice as the populating step) is filled here.

Altitude boundary (deliberate, mirrors the package's "pure core + thin shell"
idiom):

* This module emits the ordered *semantic mutation sequence* and performs
  **no network writes**. Materialising each :class:`GhCall` into the concrete
  live sync-PR ``gh``/REST calls — branch creation, Contents-API ``sha``
  lookups, ``gh pr create``, and the per-repo admin-merge serialisation for a
  self-modifying ``code-review.yml`` (PRD story 22) — is the live-executor
  layer, deferred to a supervised HITL step so the dangerous tail stays gated.
* :func:`plan_account_pass` is the per-account-pass orchestrator (PRD: "run
  once per GitHub account"). It composes loader + Planner + Applier into a
  per-repo dry-run report; it does not mutate anything either.

Idempotency (PRD story 23): a :class:`GhCall` is emitted only when desired
differs from actual.

* ``SET_CHECK_CONTEXTS`` is dropped when the actual required contexts already
  match the manifest (order-insensitive set comparison).
* A managed-file write is dropped when :class:`ActualState` records a content
  hash equal to the rendered content's hash. The auditor records workflow
  *paths*, not bodies, today, so the actual hash is usually unknown — the write
  is then emitted and the git layer dedupes (a synced repo's sync-PR is empty).
  The hash comparison is forward-compatible for when the auditor learns to read
  bodies (#979).
"""

from __future__ import annotations

import enum
import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml

from .auditor import OSASUWU_REPOS, RepoSnapshot
from .manifest import Manifest
from .planner import Action, ActionKind, ActualState, Planner
from .renderer import Renderer

# The Osasuwu account pass (PRD story 7): redrobot is a different owner and
# credential-blocked under the Osasuwu token — its SergazyNarynov pass is #940,
# so it is excluded from this account pass. Re-exported from the auditor's
# canonical list (rather than redefined) so the two never drift; named in
# ``__all__`` so it is a deliberate public re-export, not an unused import.
__all__ = [
    "OSASUWU_REPOS",
    "ApplyError",
    "Applier",
    "GhCall",
    "GhCallKind",
    "RepoPlan",
    "actual_state_from_snapshot",
    "load_canon",
    "load_manifest",
    "load_snapshot",
    "plan_account_pass",
]

_MODULE_DIR = Path(__file__).resolve().parent
CANON_DIR = _MODULE_DIR / "canon"
MANIFESTS_DIR = _MODULE_DIR / "manifests"
SNAPSHOTS_DIR = _MODULE_DIR / "snapshots"


class ApplyError(ValueError):
    """Raised when a plan cannot be translated — e.g. a managed-file write
    references a path with no canon template, or an unknown action kind."""


class GhCallKind(enum.Enum):
    """The semantic mutation kinds the Applier emits."""

    PUT_FILE = "put_file"
    """Create or overwrite a managed file with rendered content."""

    DELETE_FILE = "delete_file"
    """Remove a file no longer in the managed set."""

    SET_CHECK_CONTEXTS = "set_check_contexts"
    """Reconcile the required status-check contexts on the default branch."""


@dataclass(frozen=True)
class GhCall:
    """One semantic mutation in the ordered apply sequence.

    Frozen + tuple-valued so calls are hashable, comparable value objects —
    tests assert an exact expected sequence by equality.
    """

    kind: GhCallKind
    path: str
    content: Optional[str] = None
    """Rendered file body (PUT_FILE only)."""

    file_class: Optional[str] = None
    """Traceability — managed / language_test (PUT_FILE only)."""

    contexts: tuple[str, ...] = ()
    """Desired required-check contexts (SET_CHECK_CONTEXTS only)."""


def _content_hash(text: str) -> str:
    """Stable content hash used for write-idempotency comparison."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _canon_name(repo_path: str) -> str:
    """Canon template key for a repo-path — its basename.

    Managed-set basenames are unique (``code-review.yml``, ``bug.yml``,
    ``PULL_REQUEST_TEMPLATE.md`` …), so a basename key cleanly maps a repo-path
    like ``.github/ISSUE_TEMPLATE/bug.yml`` to ``canon/bug.yml``.
    """
    return repo_path.rsplit("/", 1)[-1]


class Applier:
    """Pure translator: action plan + actual state -> ordered ``GhCall`` list."""

    def __init__(
        self,
        manifest: Manifest,
        canon: dict[str, str],
        renderer: Optional[Renderer] = None,
    ):
        self.manifest = manifest
        self.canon = canon
        """Canon templates keyed by basename (see :func:`load_canon`)."""
        self.renderer = renderer or Renderer()

    def render_content(self, repo_path: str) -> str:
        """Render the canon template for *repo_path* through the manifest axes.

        Raises :class:`ApplyError` if no canon template covers the path — a
        loud, attributable failure rather than a silently skipped write.
        """
        name = _canon_name(repo_path)
        template = self.canon.get(name)
        if template is None:
            raise ApplyError(
                f"No canon template for managed path {repo_path!r} "
                f"(expected canon entry {name!r}; repo={self.manifest.repo!r})"
            )
        return self.renderer.render(template, self.manifest)

    def missing_canon(self, plan: list[Action]) -> list[str]:
        """Repo-paths in *plan* that WRITE but have no canon template.

        A pre-flight gap check the orchestrator uses to surface an incomplete
        canon set without aborting the whole account pass.
        """
        return [
            a.path
            for a in plan
            if a.kind == ActionKind.WRITE_FILE and _canon_name(a.path) not in self.canon
        ]

    def translate(self, plan: list[Action], actual: ActualState) -> list[GhCall]:
        """Translate a rendered plan into the idempotency-filtered call sequence.

        Order is preserved from the plan (the Planner already encodes the
        files-before-protection ordering invariant, PRD story 10).
        """
        calls: list[GhCall] = []
        for action in plan:
            if action.kind == ActionKind.WRITE_FILE:
                content = self.render_content(action.path)
                actual_hash = actual.files.get(action.path)
                if actual_hash and actual_hash == _content_hash(content):
                    continue  # idempotent: already byte-identical on the repo
                calls.append(
                    GhCall(
                        kind=GhCallKind.PUT_FILE,
                        path=action.path,
                        content=content,
                        file_class=action.file_class,
                    )
                )
            elif action.kind == ActionKind.DELETE_FILE:
                # Only delete what actually exists (the Planner derives deletes
                # from actual state, so this is defensive — a stale plan replayed
                # against a repo where the file is already gone is a no-op).
                if action.path in actual.files:
                    calls.append(GhCall(kind=GhCallKind.DELETE_FILE, path=action.path))
            elif action.kind == ActionKind.SET_CHECK_CONTEXTS:
                desired = list(action.context_names)
                if set(desired) == set(actual.required_check_contexts):
                    continue  # idempotent: required gates already match
                calls.append(
                    GhCall(
                        kind=GhCallKind.SET_CHECK_CONTEXTS,
                        path=action.path,
                        contexts=tuple(desired),
                    )
                )
            else:  # pragma: no cover — defensive against a new ActionKind
                raise ApplyError(f"Unknown action kind {action.kind!r}")
        return calls


# ── Loaders ──────────────────────────────────────────────────────────


def load_canon(canon_dir: Path = CANON_DIR) -> dict[str, str]:
    """Load canon templates as a ``{basename: text}`` map.

    Skips ``__init__.py`` (package marker, not a template). Sorted for
    deterministic iteration in error messages.
    """
    return {
        p.name: p.read_text(encoding="utf-8")
        for p in sorted(canon_dir.iterdir())
        if p.is_file() and p.name != "__init__.py"
    }


def _slug(repo: str) -> str:
    """``Osasuwu/jarvis`` -> ``Osasuwu__jarvis`` (mirrors generate_snapshots)."""
    return repo.replace("/", "__")


def load_manifest(repo: str, manifests_dir: Path = MANIFESTS_DIR) -> Manifest:
    """Load the committed seeded manifest for *repo*."""
    path = manifests_dir / f"{_slug(repo)}.manifest.yml"
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return Manifest.from_dict(data)


def load_snapshot(repo: str, snapshots_dir: Path = SNAPSHOTS_DIR) -> RepoSnapshot:
    """Load the committed audit snapshot for *repo*."""
    import json

    path = snapshots_dir / f"{_slug(repo)}.snapshot.json"
    return RepoSnapshot.from_dict(json.loads(path.read_text(encoding="utf-8")))


def actual_state_from_snapshot(snapshot: RepoSnapshot) -> ActualState:
    """Bridge an audit :class:`RepoSnapshot` to the Planner's :class:`ActualState`.

    Only the axes the snapshot observes are populated: present workflow paths
    (with unknown content hash — the auditor records paths, not bodies, so the
    empty-string hash signals "present but content unknown") and the required
    check contexts. Template/community-health file presence and file bodies are
    not yet captured by the auditor (#979 deepens this), so write-idempotency on
    those falls through to the git layer.
    """
    files = {path: "" for path in snapshot.workflows}
    contexts = list(snapshot.branch_protection.contexts) if snapshot.branch_protection else []
    return ActualState(files=files, required_check_contexts=contexts)


# ── Per-account-pass orchestrator (dry-run) ──────────────────────────


@dataclass
class RepoPlan:
    """The translated apply sequence for one repo, plus pre-flight gaps."""

    repo: str
    calls: list[GhCall] = field(default_factory=list)
    missing_canon: list[str] = field(default_factory=list)
    """Managed-write paths with no canon template — a gap to fill before any
    live run; when non-empty the repo's calls are left empty (not translated)."""


def plan_account_pass(
    repos: list[str],
    *,
    canon: Optional[dict[str, str]] = None,
    manifests_dir: Path = MANIFESTS_DIR,
    snapshots_dir: Path = SNAPSHOTS_DIR,
) -> list[RepoPlan]:
    """Build the dry-run apply plan for an account's repos (PRD: per-account pass).

    For each repo: load its seeded manifest + committed snapshot, run the
    Planner to get the action plan, then the Applier to translate it into the
    idempotency-filtered ``GhCall`` sequence. A repo with a canon gap is
    reported (``missing_canon`` populated, ``calls`` empty) rather than aborting
    the whole pass — staged blast-radius (PRD story 9) starts with knowing which
    repos are even applyable.

    This performs **no live writes**: it is the planning half of slice 5. The
    live sync-PR executor that consumes these ``RepoPlan``\\ s is the supervised
    follow-up.
    """
    canon = canon if canon is not None else load_canon()
    plans: list[RepoPlan] = []
    for repo in repos:
        manifest = load_manifest(repo, manifests_dir)
        snapshot = load_snapshot(repo, snapshots_dir)
        actual = actual_state_from_snapshot(snapshot)
        plan = Planner(manifest).plan(actual)
        applier = Applier(manifest, canon)
        gaps = applier.missing_canon(plan)
        if gaps:
            plans.append(RepoPlan(repo=repo, calls=[], missing_canon=gaps))
            continue
        plans.append(RepoPlan(repo=repo, calls=applier.translate(plan, actual)))
    return plans

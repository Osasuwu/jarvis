"""Generate committed audit snapshots + seeded manifests for the baseline repos.

Runs the live :class:`~scripts.repo_baseline.auditor.Auditor` over every repo in
``OSASUWU_REPOS`` and writes, per repo:

* ``snapshots/<owner>__<name>.snapshot.json`` — the full :class:`RepoSnapshot`,
  scrubbed of device/infra topology (jarvis is PUBLIC). These are the canonical
  fixtures the downstream pure-core (#939 applier) tests run against.
* ``manifests/<owner>__<name>.manifest.yml`` — the :func:`seed_manifest` skeleton,
  a populated starting point the owner edits rather than authoring from scratch.

Re-runnable: re-auditing is the whole point of a *re-syncable* baseline. Output is
deterministic (sorted-key JSON *and* sorted-key YAML) so a no-op re-audit produces
no diff regardless of the order keys are emitted in the source. ``SergazyNarynov/
redrobot`` is intentionally out of scope — different owner, credential-blocked
under the Osasuwu token; deferred to issue #940.

Usage::

    python -m scripts.repo_baseline.generate_snapshots
"""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from .auditor import (
    OSASUWU_REPOS,
    Auditor,
    GhRunner,
    gh_runner,
    scrub_topology,
    seed_manifest,
)

_MODULE_DIR = Path(__file__).resolve().parent
SNAPSHOTS_DIR = _MODULE_DIR / "snapshots"
MANIFESTS_DIR = _MODULE_DIR / "manifests"


def _slug(repo: str) -> str:
    """``Osasuwu/jarvis`` -> ``Osasuwu__jarvis`` (filesystem-safe, owner-keyed)."""
    return repo.replace("/", "__")


def generate(
    repos: list[str],
    runner: GhRunner = gh_runner,
    *,
    snapshots_dir: Path | None = None,
    manifests_dir: Path | None = None,
) -> list[str]:
    """Audit each repo and write its snapshot + seeded manifest. Returns paths.

    ``snapshots_dir`` / ``manifests_dir`` default to the package's committed
    fixture dirs; tests pass a ``tmp_path`` so a generation run never touches
    the real fixtures.

    Like :meth:`Auditor.audit_all`, this does **not** fail fast: a single repo's
    audit failure must not discard the files already written for its siblings.
    Every repo is attempted; if any failed, a single :class:`RuntimeError` naming
    all failures is raised at the end. Files for the repos that succeeded remain
    on disk — a partial regen is recoverable, a lost batch is not.
    """
    snapshots_dir = snapshots_dir if snapshots_dir is not None else SNAPSHOTS_DIR
    manifests_dir = manifests_dir if manifests_dir is not None else MANIFESTS_DIR
    snapshots_dir.mkdir(parents=True, exist_ok=True)
    manifests_dir.mkdir(parents=True, exist_ok=True)

    auditor = Auditor(runner)
    written: list[str] = []
    errors: dict[str, Exception] = {}
    # NOTE: this loop deliberately does NOT delegate to ``Auditor.audit_all``.
    # ``audit_all`` collects every snapshot in memory and only raises at the end —
    # it never writes anything. Here the write *is* the per-repo work, and the
    # isolation property we need is write-as-you-go: a sibling's mid-run failure
    # must leave the already-written files on disk. Calling ``audit_all`` and
    # writing afterwards would discard the whole batch if any single repo failed,
    # regressing that property. The ``generate:`` error prefix is intentionally
    # distinct from ``audit_all:`` so a failure is traceable to this writer path.
    for repo in repos:
        try:
            snapshot = auditor.audit(repo)
            slug = _slug(repo)

            snap_path = snapshots_dir / f"{slug}.snapshot.json"
            scrubbed = scrub_topology(snapshot.to_dict())
            snap_path.write_text(
                json.dumps(scrubbed, sort_keys=True, indent=2) + "\n", encoding="utf-8"
            )
            written.append(str(snap_path))

            manifest_path = manifests_dir / f"{slug}.manifest.yml"
            seed = scrub_topology(seed_manifest(snapshot))
            manifest_path.write_text(
                yaml.safe_dump(seed, sort_keys=True, default_flow_style=False),
                encoding="utf-8",
            )
            written.append(str(manifest_path))
        except Exception as e:  # noqa: BLE001 — collect, don't fail-fast
            errors[repo] = e

    if errors:
        detail = "; ".join(f"{r} ({type(e).__name__}: {e})" for r, e in errors.items())
        raise RuntimeError(f"generate: {len(errors)} of {len(repos)} repo(s) failed — {detail}")
    return written


def main() -> None:
    written = generate(OSASUWU_REPOS)
    print(f"Wrote {len(written)} files for {len(OSASUWU_REPOS)} repos:")
    for path in written:
        print(f"  {path}")


if __name__ == "__main__":
    main()

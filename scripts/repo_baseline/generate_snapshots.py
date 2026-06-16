"""Generate committed audit snapshots + seeded manifests for the baseline repos.

Runs the live :class:`~scripts.repo_baseline.auditor.Auditor` over every repo in
``OSASUWU_REPOS`` and writes, per repo:

* ``snapshots/<owner>__<name>.snapshot.json`` — the full :class:`RepoSnapshot`,
  scrubbed of device/infra topology (jarvis is PUBLIC). These are the canonical
  fixtures the downstream pure-core (#939 applier) tests run against.
* ``manifests/<owner>__<name>.manifest.yml`` — the :func:`seed_manifest` skeleton,
  a populated starting point the owner edits rather than authoring from scratch.

Re-runnable: re-auditing is the whole point of a *re-syncable* baseline. Output is
deterministic (sorted-key JSON, fixed-order YAML) so a no-op re-audit produces no
diff. ``SergazyNarynov/redrobot`` is intentionally out of scope — different owner,
credential-blocked under the Osasuwu token; deferred to issue #940.

Usage::

    python -m scripts.repo_baseline.generate_snapshots
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import List

import yaml

from .auditor import OSASUWU_REPOS, Auditor, gh_runner, scrub_topology, seed_manifest

_MODULE_DIR = Path(__file__).resolve().parent
SNAPSHOTS_DIR = _MODULE_DIR / "snapshots"
MANIFESTS_DIR = _MODULE_DIR / "manifests"


def _slug(repo: str) -> str:
    """``Osasuwu/jarvis`` -> ``Osasuwu__jarvis`` (filesystem-safe, owner-keyed)."""
    return repo.replace("/", "__")


def generate(repos: List[str], runner=gh_runner) -> List[str]:
    """Audit each repo and write its snapshot + seeded manifest. Returns paths."""
    SNAPSHOTS_DIR.mkdir(exist_ok=True)
    MANIFESTS_DIR.mkdir(exist_ok=True)

    auditor = Auditor(runner)
    written: List[str] = []
    for repo in repos:
        snapshot = auditor.audit(repo)
        slug = _slug(repo)

        snap_path = SNAPSHOTS_DIR / f"{slug}.snapshot.json"
        scrubbed = scrub_topology(snapshot.to_dict())
        snap_path.write_text(
            json.dumps(scrubbed, sort_keys=True, indent=2) + "\n", encoding="utf-8"
        )
        written.append(str(snap_path))

        manifest_path = MANIFESTS_DIR / f"{slug}.manifest.yml"
        seed = scrub_topology(seed_manifest(snapshot))
        manifest_path.write_text(
            yaml.safe_dump(seed, sort_keys=False, default_flow_style=False),
            encoding="utf-8",
        )
        written.append(str(manifest_path))

    return written


def main() -> None:
    written = generate(OSASUWU_REPOS)
    print(f"Wrote {len(written)} files for {len(OSASUWU_REPOS)} repos:")
    for path in written:
        print(f"  {path}")


if __name__ == "__main__":
    main()

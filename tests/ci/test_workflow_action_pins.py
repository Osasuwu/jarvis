"""Every third-party action in every workflow is pinned to a full commit SHA.

A tag (`@v7`) or branch (`@main`) ref is movable: whoever controls the action's
repository can point it at different code, and that code runs with this
repository's token and secrets on the next workflow run, with no PR here.
A 40-hex commit SHA is the only immutable ref. The human-readable tag stays
as a trailing comment (`uses: actions/checkout@<sha> # v7`), which is also the
form Dependabot's `github-actions` updater (.github/dependabot.yml) maintains.

One test over the whole workflow directory, so a new workflow is covered the
moment it is added — no per-workflow copy to forget.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS_DIR = REPO_ROOT / ".github" / "workflows"

_SHA_PINNED = re.compile(r"@[0-9a-f]{40}$")


def _uses_refs(node: object) -> list[str]:
    """Every `uses:` value in a parsed workflow — step-level and job-level."""
    if isinstance(node, dict):
        found = [v for k, v in node.items() if k == "uses" and isinstance(v, str)]
        for value in node.values():
            found.extend(_uses_refs(value))
        return found
    if isinstance(node, list):
        return [ref for item in node for ref in _uses_refs(item)]
    return []


def _is_pinned(ref: str) -> bool:
    if ref.startswith("./"):
        return True  # local action / reusable workflow: versioned with this repo
    if ref.startswith("docker://"):
        return "@sha256:" in ref
    return _SHA_PINNED.search(ref) is not None


def test_every_action_ref_is_pinned_to_a_commit_sha():
    workflows = sorted([*WORKFLOWS_DIR.glob("*.yml"), *WORKFLOWS_DIR.glob("*.yaml")])
    assert workflows, f"no workflow files found under {WORKFLOWS_DIR}"

    seen = 0
    unpinned: list[str] = []
    for path in workflows:
        refs = _uses_refs(yaml.safe_load(path.read_text(encoding="utf-8")))
        seen += len(refs)
        unpinned.extend(f"{path.name}: {ref}" for ref in refs if not _is_pinned(ref))

    assert seen, "no `uses:` refs found in any workflow — the walker is broken"
    assert not unpinned, (
        "Action refs on a movable tag/branch (pin to the 40-hex commit SHA, "
        "keep the tag as a trailing comment):\n  " + "\n  ".join(unpinned)
    )

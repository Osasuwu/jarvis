"""Lint: `.github/dependabot.yml` names no file that is missing from the tree (#2000 S2).

The file's comments pointed at `dependabot-lockfile.yml` for months after #1835 deleted it, so a
reader (or an agent) went looking for automation that does not exist. A reference to a file that
is gone stays a lie until someone trips on it; this walks every `*.yml` / `*.yaml` / `*.md` token
in the file and fails on the ones that resolve to nothing.

A bare `name.yml` is a workflow file under `.github/workflows/`; a token with a `/` is a path
from the repo root.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DEPENDABOT_YML = REPO_ROOT / ".github" / "dependabot.yml"
WORKFLOWS = REPO_ROOT / ".github" / "workflows"

_FILE_TOKEN = re.compile(r"[\w./-]+\.(?:ya?ml|md)\b")


def _resolve(token: str) -> Path:
    return REPO_ROOT / token if "/" in token else WORKFLOWS / token


def test_dependabot_yml_references_no_file_absent_from_the_tree():
    tokens = _FILE_TOKEN.findall(DEPENDABOT_YML.read_text(encoding="utf-8"))
    # Guard for the loop below: a config that mentions no file would pass vacuously.
    assert tokens, "dependabot.yml names no file; the lint has nothing to check"

    missing = sorted({t for t in tokens if not _resolve(t).is_file()})

    assert missing == [], (
        f".github/dependabot.yml names files that do not exist on this tree: {missing}. "
        "Fix the comment, or restore the file it points at."
    )

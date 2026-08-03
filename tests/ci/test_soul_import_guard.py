"""Guard for #1328 — SOUL.md must be delivered by @import, not a SessionStart cat.

Mirrors `test_doctrine_pointers_guard.py`'s pattern for `@DOCTRINE.md` (#1315):
a bare `@SOUL.md` import line in `.claude-userlevel/CLAUDE.md` is how identity
content reaches every session (fresh, `--resume`d, post-compaction) — a
SessionStart hook only fires on `startup`/`compact` matchers and silently
skips `--resume`, which was the gap #1328 closes.

Two checks pinned here:
  - the `@SOUL.md` import line exists in CLAUDE.md outside any code span
  - the `soul` manifest group (config/SOUL.md -> SOUL.md) is present and enabled

The "no SessionStart hook cats a static file" assertion lives in
tests/infrastructure/test_installer.py::test_userlevel_settings_no_longer_cats_soul
— not duplicated here to avoid two tests asserting the same fact.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
USERLEVEL_DIR = REPO_ROOT / ".claude-userlevel"
CLAUDE_MD_PATH = USERLEVEL_DIR / "CLAUDE.md"
SOUL_MD_PATH = REPO_ROOT / "config" / "SOUL.md"
MANIFEST_PATH = REPO_ROOT / "install-manifest.yaml"


def strip_code_spans_and_fences(text: str) -> str:
    """Drop fenced code blocks and inline `code spans` — import-line parsing
    skips code spans, so a match only counts if it survives outside one."""
    text = re.sub(r"```.*?```", "", text, flags=re.DOTALL)
    text = re.sub(r"`[^`\n]*`", "", text)
    return text


class TestSoulImport:
    def test_claude_md_exists(self):
        assert CLAUDE_MD_PATH.exists(), f"missing {CLAUDE_MD_PATH}"

    def test_soul_md_exists(self):
        assert SOUL_MD_PATH.exists(), f"missing {SOUL_MD_PATH}"

    def test_bare_import_line_outside_code_span(self):
        text = CLAUDE_MD_PATH.read_text(encoding="utf-8")
        stripped = strip_code_spans_and_fences(text)
        assert "@SOUL.md" in stripped, (
            "expected a bare `@SOUL.md` import in .claude-userlevel/CLAUDE.md, "
            "outside any backtick code span or fenced code block — Claude Code's "
            "@import parser skips code spans, so a fenced/backticked mention would "
            "not actually load SOUL.md (#1328)"
        )


class TestManifestCoverage:
    @pytest.fixture(scope="class")
    def manifest(self):
        assert MANIFEST_PATH.exists(), f"missing {MANIFEST_PATH}"
        return yaml.safe_load(MANIFEST_PATH.read_text(encoding="utf-8"))

    def test_soul_covered_by_install_manifest(self, manifest):
        groups = manifest.get("groups", [])
        soul_groups = [
            g for g in groups if any(f.get("source") == "config/SOUL.md" for f in g.get("files", []))
        ]
        assert soul_groups, (
            "install-manifest.yaml has no group installing config/SOUL.md — "
            "SOUL.md would never reach ~/.claude/ on `install.ps1 -Apply`"
        )

    def test_soul_group_enabled(self, manifest):
        groups = manifest.get("groups", [])
        soul_groups = [g for g in groups if g.get("id") == "soul"]
        assert soul_groups, "no manifest group with id 'soul'"
        assert soul_groups[0].get("enabled") is True, "soul manifest group is not enabled"

"""Guard for #1417 — Invariants + Glossary index must be delivered by @import.

Mirrors `test_soul_import_guard.py` / `test_doctrine_pointers_guard.py`'s
pattern for `@SOUL.md` (#1328) / `@DOCTRINE.md` (#1315): a bare `@import`
line in the project's root `CLAUDE.md` is how this content reaches every
session, bypassing the SessionStart hook's budget-constrained assembler
entirely (the assembler used to drop `project_context` in 47% of sessions —
see CONTEXT.md → *Context delivery*).

Unlike SOUL.md/DOCTRINE.md, these two files are project-repo content (not
user-level), so there is no install-manifest coverage to check — the whole
jarvis repo ships as-is via `git clone`/`git pull`, and CLAUDE.md is already
read by the harness in every jarvis session.

Three checks pinned here:
  - both files exist and each carries its own unique import-marker string
  - both bare `@import` lines exist in root CLAUDE.md, outside any code span
  - `scripts/session-context.py` no longer defines the retired assembler path
    (`_load_project_context`) — the whole point of #1417 is that this content
    no longer rides the budget-constrained push
"""

from __future__ import annotations

from pathlib import Path

from ._md_helpers import strip_code_spans_and_fences

REPO_ROOT = Path(__file__).resolve().parents[2]
CLAUDE_MD_PATH = REPO_ROOT / "CLAUDE.md"
INVARIANTS_MD_PATH = REPO_ROOT / "docs" / "context" / "invariants.md"
GLOSSARY_INDEX_MD_PATH = REPO_ROOT / "docs" / "context" / "glossary-index.md"
SESSION_CONTEXT_PATH = REPO_ROOT / "scripts" / "session-context.py"


class TestExtractedFilesExist:
    def test_invariants_md_exists(self):
        assert INVARIANTS_MD_PATH.exists(), f"missing {INVARIANTS_MD_PATH}"

    def test_glossary_index_md_exists(self):
        assert GLOSSARY_INDEX_MD_PATH.exists(), f"missing {GLOSSARY_INDEX_MD_PATH}"

    def test_invariants_md_has_unique_marker(self):
        text = INVARIANTS_MD_PATH.read_text(encoding="utf-8")
        assert "<!-- jarvis-context-import-marker: invariants-md -->" in text

    def test_glossary_index_md_has_unique_marker(self):
        text = GLOSSARY_INDEX_MD_PATH.read_text(encoding="utf-8")
        assert "<!-- jarvis-context-import-marker: glossary-index-md -->" in text

    def test_markers_are_distinct(self):
        invariants_text = INVARIANTS_MD_PATH.read_text(encoding="utf-8")
        glossary_text = GLOSSARY_INDEX_MD_PATH.read_text(encoding="utf-8")
        assert "glossary-index-md" not in invariants_text
        assert "invariants-md" not in glossary_text


class TestImportLines:
    def test_claude_md_exists(self):
        assert CLAUDE_MD_PATH.exists(), f"missing {CLAUDE_MD_PATH}"

    def test_bare_invariants_import_line_outside_code_span(self):
        text = CLAUDE_MD_PATH.read_text(encoding="utf-8")
        stripped = strip_code_spans_and_fences(text)
        assert "@docs/context/invariants.md" in stripped, (
            "expected a bare `@docs/context/invariants.md` import in root CLAUDE.md, "
            "outside any backtick code span or fenced code block — Claude Code's "
            "@import parser skips code spans, so a fenced/backticked mention would "
            "not actually load the file (#1417)"
        )

    def test_bare_glossary_index_import_line_outside_code_span(self):
        text = CLAUDE_MD_PATH.read_text(encoding="utf-8")
        stripped = strip_code_spans_and_fences(text)
        assert "@docs/context/glossary-index.md" in stripped, (
            "expected a bare `@docs/context/glossary-index.md` import in root CLAUDE.md, "
            "outside any backtick code span or fenced code block — Claude Code's "
            "@import parser skips code spans, so a fenced/backticked mention would "
            "not actually load the file (#1417)"
        )


class TestRetiredAssemblerPath:
    def test_load_project_context_removed(self):
        text = SESSION_CONTEXT_PATH.read_text(encoding="utf-8")
        assert "_load_project_context" not in text, (
            "scripts/session-context.py must not define/reference "
            "_load_project_context — #1417 retired the budget-constrained "
            "CONTEXT.md push in favor of @import delivery"
        )

    def test_priority_context_push_removed(self):
        text = SESSION_CONTEXT_PATH.read_text(encoding="utf-8")
        assert "_PRIORITY_CONTEXT_PUSH" not in text, (
            "scripts/session-context.py must not define/reference "
            "_PRIORITY_CONTEXT_PUSH — its priority slot was removed by #1417"
        )

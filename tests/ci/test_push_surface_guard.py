"""Anti-regrowth ratchet on the always-pushed context layer (#1273).

CI ceilings on push surfaces only — the six canonical source files: the four
original identity/rules files plus the two @import-delivered context files
(``docs/context/invariants.md``, ``docs/context/glossary-index.md``) that
replaced the SessionStart hook's assembly-derived CONTEXT.md push (#1417).
Ceilings live in checked-in JSON
(``tests/ci/fixtures/push_surface_ceilings.json``); the guard fails red when a
surface exceeds its ceiling, and raising a ceiling requires editing the fixture
in the same PR (the JSON IS the fixture — ``same_pr_raise`` in the fixture).

Key design rules, per #1273 (as amended by #1417):

- **Every canonical surface is a plain file.** All six surfaces are measured
  by reading their file directly — there is no assembly-derived surface left
  since #1417 retired ``_load_project_context`` and its budget-constrained
  push. ``docs/context/invariants.md`` / ``docs/context/glossary-index.md``
  ride a bare ``@import`` in CLAUDE.md, which bypasses the SessionStart
  assembler and its ``ASSEMBLY_BUDGET_CHARS`` cap entirely.
- **Item definition is pinned and load-bearing.** bullet at any nesting depth +
  numbered line; only block-level HTML comments are excluded. Fenced code, YAML
  frontmatter, and ``.claude/rules/*`` without a ``paths:`` key are all counted
  (they load at session start). A synthetic fixture test asserts this.
- **A new always-pushed surface fails red.** ``.claude/rules/*.md`` without a
  ``paths:`` key and ``CLAUDE.local.md`` load at launch; if one appears and the
  fixture does not list it, the guard fails.
- **CONTEXT.md as a whole file has NO ceiling** — the Invariants/Glossary
  content that used to be measured through it now lives in its own ratcheted
  files (see above); CONTEXT.md itself carries only pointers.

Runs via ci-meta.yml (``pytest tests/ci/``, deliberately not path-filtered) on
every PR, per the #326 guard-test pattern.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_PATH = Path(__file__).resolve().parent / "fixtures" / "push_surface_ceilings.json"

# ---------------------------------------------------------------------------
# Pinned item definition (#1273): bullet at any nesting depth or a numbered
# line. Only block-level HTML comments are excluded; fenced code and YAML
# frontmatter are counted (the metric measures what is actually pushed).
# ---------------------------------------------------------------------------

_HTML_COMMENT_RE = re.compile(r"<!--.*?-->", flags=re.DOTALL)
_BULLET_RE = re.compile(r"^[-*+] ")
_NUMBERED_RE = re.compile(r"^\d+[.)]\s")


def strip_html_comments(text: str) -> str:
    return _HTML_COMMENT_RE.sub("", text)


def count_items(text: str) -> int:
    """Count 'items' per the pinned definition. See the fixture's
    ``item_definition`` — this implementation must stay in lockstep with it."""
    n = 0
    for line in strip_html_comments(text).splitlines():
        s = line.strip()
        if not s:
            continue
        if _BULLET_RE.match(s) or _NUMBERED_RE.match(s):
            n += 1
    return n


def count_bytes(text: str) -> int:
    return len(text.encode("utf-8"))


# ---------------------------------------------------------------------------
# Surface discovery + measurement
# ---------------------------------------------------------------------------

# The six canonical file surfaces — all plain files, none assembly-derived.
CANONICAL_SURFACES = {
    "soul_md": "config/SOUL.md",
    "project_claude_md": "CLAUDE.md",
    "userlevel_claude_md": ".claude-userlevel/CLAUDE.md",
    "userlevel_doctrine_md": ".claude-userlevel/DOCTRINE.md",
    "invariants_md": "docs/context/invariants.md",
    "glossary_index_md": "docs/context/glossary-index.md",
}


def _has_paths_key(path: Path) -> bool:
    """True when a .claude/rules/* file carries a ``paths:`` key in frontmatter.

    A rule WITHOUT ``paths:`` loads at launch with the same priority as
    ``.claude/CLAUDE.md`` — an always-pushed surface. One WITH ``paths:`` only
    loads when the glob matches, so it is conditional and excluded. We exclude
    by the key, never by directory — excluding the directory wholesale would
    make ``mv`` from CLAUDE.md into ``.claude/rules/`` a zero-cost laundering
    path (#1273).
    """
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return False
    end = text.find("\n---", 3)
    if end == -1:
        return False
    frontmatter = text[3:end]
    return any(line.strip() == "paths:" or line.strip().startswith("paths:")
               for line in frontmatter.splitlines())


def _discover_extra_file_surfaces() -> dict[str, str]:
    """Always-pushed file surfaces beyond the canonical four: .claude/rules/*
    without a paths: key, and CLAUDE.local.md if present. Returns
    {surface_id: repo-relative path}."""
    surfaces: dict[str, str] = {}
    rules_dir = REPO_ROOT / ".claude" / "rules"
    if rules_dir.exists():
        for md in sorted(rules_dir.glob("*.md")):
            if not _has_paths_key(md):
                surfaces[f"claude_rules:{md.name}"] = str(md.relative_to(REPO_ROOT))
    local = REPO_ROOT / "CLAUDE.local.md"
    if local.exists():
        surfaces["claude_local_md"] = "CLAUDE.local.md"
    return surfaces


def _measure_surface(surface_id: str, spec: dict) -> tuple[int, int]:
    """Return (items, bytes) for a fixture surface — always a plain file read."""
    text = (REPO_ROOT / spec["path"]).read_text(encoding="utf-8")
    return count_items(text), count_bytes(text)


def _format_violation(surface_id: str, items: int, items_ceil: int,
                      bytes_: int, bytes_ceil: int) -> str:
    fixture = _load_fixture()
    spec = fixture["surfaces"][surface_id]
    source = spec["path"]
    parts = [f"Push surface '{surface_id}' ({source}) exceeds its ceiling:"]
    if items > items_ceil:
        parts.append(f"  items: {items} > {items_ceil} (over by {items - items_ceil})")
    if bytes_ > bytes_ceil:
        parts.append(f"  bytes: {bytes_} > {bytes_ceil} (over by {bytes_ - bytes_ceil})")
    parts.append(
        "Every session pays this cost. Move content to a cheaper carrier per "
        ".claude-userlevel/DOCTRINE.md → Baseline carrier selection "
        "(code/CI gate, PreToolUse deny hook, .claude/rules/ + paths:, retrieval) "
        "instead of raising the ceiling. Raising a ceiling requires editing "
        "tests/ci/fixtures/push_surface_ceilings.json in the same PR "
        f"(decision {spec['decision_uuid']})."
    )
    return "\n".join(parts)


def _load_fixture() -> dict:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Synthetic fixture for the pinned item definition (#1273 AC3)
# ---------------------------------------------------------------------------

SYNTHETIC_CONTENT = """\
<!-- a block-level HTML comment
   that spans lines and contains - not a bullet
   and 1. not a numbered item -->
---
- frontmatter bullet
---

# Heading

- a bullet
- another bullet
    - nested bullet
* star bullet
    * nested star
+ plus bullet
1. numbered one
2) numbered paren
   3. nested numbered

| col | col |
| - | 2. x |

```fenced
- inside fenced code (counted)
1. also counted
```

- after the fence
"""


class TestItemDefinition:
    """The pinned definition must be asserted, not implied (#1273 AC3)."""

    def test_synthetic_content_counts_as_pinned(self):
        assert count_items(SYNTHETIC_CONTENT) == 13

    def test_block_html_comments_excluded(self):
        assert count_items("<!-- - hidden\n   1. also hidden\n-->\n- real") == 1

    def test_nested_bullets_counted(self):
        assert count_items("- top\n    - mid\n        - deep\n") == 3

    def test_numbered_lines_counted(self):
        assert count_items("1. one\n2) two\n   3. three\n10. ten\n") == 4

    def test_fenced_code_is_counted(self):
        # Fenced code is NOT stripped — it is pushed at session start, so it
        # counts toward the byte metric just like any other text (#1273 AC4).
        assert count_items("```\n- in fence\n1. also\n```\n") == 2

    def test_yaml_frontmatter_is_counted(self):
        assert count_items("---\n- fm bullet\n1. fm num\n---\nbody\n") == 2

    def test_table_rows_are_not_items(self):
        assert count_items("| - | 2. x |\n| * | 3) y |\n") == 0

    def test_plain_lines_are_not_items(self):
        assert count_items("not a bullet\n= heading =\njust text\n") == 0


class TestFixtureIntegrity:
    def test_fixture_exists_and_is_valid_json(self):
        assert FIXTURE_PATH.is_file()
        fixture = _load_fixture()
        assert "surfaces" in fixture

    def test_item_definition_pinned_in_fixture(self):
        fixture = _load_fixture()
        definition = fixture["_meta"]["item_definition"]
        assert "bullet" in definition and "numbered" in definition
        assert "HTML comment" in definition

    def test_margin_stated(self):
        fixture = _load_fixture()
        margin = fixture["_meta"]["margin"]
        assert margin["pct"] >= 0
        assert "statement" in margin

    def test_every_surface_has_record_decision_uuid(self):
        fixture = _load_fixture()
        uuid_re = re.compile(
            r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
        )
        for surface_id, spec in fixture["surfaces"].items():
            assert uuid_re.match(spec["decision_uuid"]), (
                f"{surface_id}: decision_uuid must be a record_decision UUID"
            )

    def test_context_md_whole_file_has_no_ceiling(self):
        fixture = _load_fixture()
        assert fixture["_meta"]["context_md_whole_file"]["has_ceiling"] is False
        # The whole-file CONTEXT.md must not be ratcheted; the extracted
        # content lives in its own ratcheted files instead (#1417).
        assert "invariants_md" in fixture["surfaces"]
        assert "glossary_index_md" in fixture["surfaces"]
        assert "context_md_pushed" not in fixture["surfaces"]
        assert "context_md" not in fixture["surfaces"]

    def test_fixture_surfaces_exist_on_disk(self):
        fixture = _load_fixture()
        for surface_id, spec in fixture["surfaces"].items():
            assert (REPO_ROOT / spec["path"]).is_file(), (
                f"{surface_id}: {spec['path']} missing"
            )

    def test_fixture_covers_discovered_surfaces(self):
        """A new always-pushed file surface must be added to the fixture before
        the guard passes — adding one without updating the fixture fails red."""
        fixture = _load_fixture()
        fixture_paths = {spec["path"] for spec in fixture["surfaces"].values()}
        for surface_id, relpath in _discover_extra_file_surfaces().items():
            assert relpath in fixture_paths, (
                f"new always-pushed surface {relpath} (discovered as "
                f"{surface_id}) is not in tests/ci/fixtures/push_surface_ceilings.json "
                "— add a ceiling for it in the same PR, else the ratchet silently "
                "misses it"
            )

    def test_same_pr_raise_documented(self):
        """The JSON-is-the-fixture property must be documented so a reviewer
        knows a ceiling bump is a fixture edit in the same PR."""
        fixture = _load_fixture()
        assert "same_pr_raise" in fixture["_meta"]


class TestRatchet:
    def test_all_surfaces_within_ceilings(self):
        fixture = _load_fixture()
        violations = []
        for surface_id, spec in fixture["surfaces"].items():
            items, bytes_ = _measure_surface(surface_id, spec)
            if items > spec["items"] or bytes_ > spec["bytes"]:
                violations.append(
                    (surface_id, items, spec["items"], bytes_, spec["bytes"])
                )
        assert not violations, "\n" + "\n".join(
            _format_violation(sid, it, ic, by, bc)
            for sid, it, ic, by, bc in violations
        )

    def test_failure_message_names_carriers(self):
        """AC10: the failure message names the surface, both overage units, and
        carrier alternatives from the #1252 AC2 table (DOCTRINE.md)."""
        msg = _format_violation("soul_md", 50, 46, 12000, 11415)
        assert "soul_md" in msg
        assert "items: 50 > 46 (over by 4)" in msg
        assert "bytes: 12000 > 11415 (over by 585)" in msg
        assert "Baseline carrier selection" in msg
        assert ".claude/rules/ + paths:" in msg
        assert "retrieval" in msg

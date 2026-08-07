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
    return any(
        line.strip() == "paths:" or line.strip().startswith("paths:")
        for line in frontmatter.splitlines()
    )


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


def _format_violation(
    surface_id: str, items: int, items_ceil: int, bytes_: int, bytes_ceil: int
) -> str:
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
# Fan-out budget (#1324)
#
# Measured in #1270 (docs/research/context-management.md A.7): both CLAUDE.md
# levels and every *bare* ``@import`` under them are inherited verbatim by each
# Agent-tool subagent, while SessionStart hook output is not. So an inherited
# byte is paid N+1 times on a fan-out of N, and a hook-injected byte is paid
# once regardless. The per-surface ratchet cannot see this: adding a new bare
# import is a fan-out-multiplied cost that no single surface ceiling measures.
#
# There is no per-agent CLAUDE.md profile to opt out of (see A.7 note on #1324
# AC3) — Explore and Plan are the only subagents that omit CLAUDE.md, and that
# is not configurable. Budgeting is therefore the only available lever.
# ---------------------------------------------------------------------------

_BARE_IMPORT_RE = re.compile(r"^@(\S+)[ \t]*$")
_FENCE_RE = re.compile(r"^\s*(```|~~~)")

# The two CLAUDE.md levels are the inheritance roots.
_INHERITANCE_ROOTS = ("CLAUDE.md", ".claude-userlevel/CLAUDE.md")

# ``.claude-userlevel/`` is installed to ``~/.claude/``; one file is templated
# from elsewhere in the repo, so a bare import written against the installed
# layout resolves to a different repo path.
_INSTALL_ALIASES = {".claude-userlevel/SOUL.md": "config/SOUL.md"}


def _parse_bare_imports(text: str) -> list[str]:
    """Import targets that Claude Code actually expands: bare, line-start, own
    line, outside fenced code. A mid-prose ``@path`` mention does not resolve
    (#1426) and therefore costs nothing — counting it would overstate the
    budget and, worse, hide the fact that it is not delivered."""
    out: list[str] = []
    in_fence = False
    for line in text.splitlines():
        if _FENCE_RE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        m = _BARE_IMPORT_RE.match(line)
        if m:
            out.append(m.group(1))
    return out


def _resolve_import(target: str, containing: str) -> str | None:
    """Repo-relative path for an import target, or None when it does not exist
    in this checkout (a bare import to a missing file is silently empty)."""
    base = Path(containing).parent
    rel = str((base / target).as_posix()).lstrip("./")
    rel = _INSTALL_ALIASES.get(rel, rel)
    return rel if (REPO_ROOT / rel).is_file() else None


def inherited_surfaces() -> dict[str, int]:
    """{repo-relative path: bytes} for every surface a subagent inherits.

    Derived by walking bare imports transitively from the two CLAUDE.md roots —
    never hardcoded, so a newly added import is picked up (and charged) by the
    ratchet automatically instead of needing anyone to remember."""
    seen: dict[str, int] = {}
    queue = list(_INHERITANCE_ROOTS)
    while queue:
        rel = queue.pop(0)
        if rel in seen:
            continue
        path = REPO_ROOT / rel
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        seen[rel] = count_bytes(text)
        for target in _parse_bare_imports(text):
            resolved = _resolve_import(target, rel)
            if resolved is not None:
                queue.append(resolved)
    return seen


def inherited_bytes() -> int:
    return sum(inherited_surfaces().values())


def max_safe_fanout() -> int:
    """Largest N for which (N+1) copies of the inherited layer stay inside the
    declared per-agent ceiling. This is the number ``/delegate`` cites when
    sizing a fan-out."""
    per_agent = inherited_bytes()
    ceiling = _load_fixture()["_meta"]["fanout_budget"]["per_agent_ceiling_bytes"]
    if per_agent > ceiling:
        return 0
    # Within the ceiling, every additional agent costs the same fixed amount,
    # so the budget is expressed per agent and the reference fan-out is the
    # multiplier used when reporting total cost.
    return _load_fixture()["_meta"]["fanout_budget"]["reference_fanout"]


def _format_fanout_violation(per_agent: int, n: int, ceiling: int) -> str:
    total = per_agent * (n + 1)
    return "\n".join(
        [
            "Inherited-context layer exceeds the fan-out budget:",
            f"  per agent: {per_agent} > {ceiling} (over by {per_agent - ceiling})",
            f"  at the reference fan-out of {n}: {total} bytes of prompt "
            f"({n} subagents + the parent session)",
            "Inherited surfaces (both CLAUDE.md levels + every bare @import under "
            "them): " + ", ".join(sorted(inherited_surfaces())),
            "There is no per-agent CLAUDE.md profile to opt out of. Move content to "
            "a cheaper carrier per .claude-userlevel/DOCTRINE.md → Baseline carrier "
            "selection (code/CI gate, PreToolUse deny hook, .claude/rules/ + paths:, "
            "retrieval) — those are inherited zero times. Raising the ceiling "
            "requires editing tests/ci/fixtures/push_surface_ceilings.json in the "
            "same PR, which is the point: the raise makes the N+1 cost visible at "
            "review time.",
        ]
    )


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
        uuid_re = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
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
            assert (REPO_ROOT / spec["path"]).is_file(), f"{surface_id}: {spec['path']} missing"

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


class TestBareImportParsing:
    """The inherited set is derived by parsing imports — so the parser must
    distinguish the form that actually resolves (#1426's lesson)."""

    def test_bare_line_start_import_is_parsed(self):
        assert _parse_bare_imports("@docs/context/invariants.md\n") == [
            "docs/context/invariants.md"
        ]

    def test_mid_prose_mention_is_not_an_import(self):
        # This is exactly the #1426 defect: a mention inside a sentence never
        # expands, so it must not be counted as inherited weight either.
        text = "Identity lives in @SOUL.md, installed alongside this file.\n"
        assert _parse_bare_imports(text) == []

    def test_trailing_whitespace_tolerated(self):
        assert _parse_bare_imports("@a/b.md   \n") == ["a/b.md"]

    def test_fenced_import_is_not_parsed(self):
        assert _parse_bare_imports("```\n@a/b.md\n```\n") == []

    def test_indented_import_is_not_parsed(self):
        assert _parse_bare_imports("  @a/b.md\n") == []


class TestFanoutBudget:
    """#1324: every inherited byte is paid N+1 times on a fan-out of N.

    The per-surface ratchet does not capture this — adding a *new* bare
    ``@import`` to CLAUDE.md is a fan-out-multiplied cost that no single
    surface ceiling sees.
    """

    def test_fanout_budget_declared_in_fixture(self):
        budget = _load_fixture()["_meta"]["fanout_budget"]
        assert budget["reference_fanout"] >= 1
        assert budget["per_agent_ceiling_bytes"] > 0
        assert "statement" in budget
        assert re.match(
            r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
            budget["decision_uuid"],
        )

    def test_inherited_set_is_derived_and_nonempty(self):
        inherited = inherited_surfaces()
        # Both CLAUDE.md levels are inherited verbatim by every Agent-tool
        # subagent (measured, #1270 → docs/research/context-management.md A.7).
        assert "CLAUDE.md" in inherited
        assert ".claude-userlevel/CLAUDE.md" in inherited
        # ...as is every bare @import reachable from them.
        assert "docs/context/invariants.md" in inherited

    def test_hook_injected_context_is_not_inherited(self):
        """A one-time session cost must never be counted per agent (#1270)."""
        assert "CONTEXT.md" not in inherited_surfaces()

    def test_fanout_cost_within_budget(self):
        budget = _load_fixture()["_meta"]["fanout_budget"]
        per_agent = inherited_bytes()
        n = budget["reference_fanout"]
        ceiling = budget["per_agent_ceiling_bytes"]
        assert per_agent <= ceiling, _format_fanout_violation(per_agent, n, ceiling)
        assert per_agent * (n + 1) <= ceiling * (n + 1)

    def test_reference_fanout_is_affordable(self):
        budget = _load_fixture()["_meta"]["fanout_budget"]
        assert max_safe_fanout() >= budget["reference_fanout"]

    def test_violation_message_states_the_multiplier(self):
        msg = _format_fanout_violation(60000, 6, 52131)
        assert "60000" in msg
        assert "52131" in msg
        assert "420000" in msg  # 60000 * (6 + 1)
        assert "Baseline carrier selection" in msg
        assert "push_surface_ceilings.json" in msg


class TestRatchet:
    def test_all_surfaces_within_ceilings(self):
        fixture = _load_fixture()
        violations = []
        for surface_id, spec in fixture["surfaces"].items():
            items, bytes_ = _measure_surface(surface_id, spec)
            if items > spec["items"] or bytes_ > spec["bytes"]:
                violations.append((surface_id, items, spec["items"], bytes_, spec["bytes"]))
        assert not violations, "\n" + "\n".join(
            _format_violation(sid, it, ic, by, bc) for sid, it, ic, by, bc in violations
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

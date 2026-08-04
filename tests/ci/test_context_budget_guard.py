"""Budget-aware session-context assembly guard (#1271).

Runs via ci-meta.yml (``pytest tests/ci/``) on every PR. Asserts the #1271
assembly contract by importing the REAL assembler from
``scripts/session-context.py`` — never a reimplementation (that is the
anti-pattern the old byte-cap tests used to commit, #1271 AC5 / research E.1).

What it locks in:

- Clean-path and compact-path assembly each emit < 9,500 chars with every
  surviving section present (AC1), using the real CONTEXT.md push.
- Compact path delivers the durable layer (always-load, user profile, working
  state, goals) even when the CONTEXT push and one-line reminders drop (AC2).
- Drop-priority order under induced overflow; dropped sections named on the
  ``dropped:`` line (AC3).
- Every run self-logs its emitted size (AC4); the log lives at
  ``.claude/logs/session-context-size.jsonl`` (gitignored — device-local).
- CONTEXT push carries compressed Invariants + Glossary category index; the
  per-term ``### Index`` and category bodies are pull-only (AC6).
- Byte-slice truncation removal (AC7) is asserted in
  tests/ci/test_push_surface_guard.py::test_assembly_cap_pinned and
  tests/infrastructure/test_session_context_recovery.py.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import types
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _stub_module(name: str, attrs: dict) -> None:
    mod = sys.modules.get(name)
    if mod is not None and all(hasattr(mod, a) for a in attrs):
        return
    new = types.ModuleType(name)
    for attr, value in attrs.items():
        setattr(new, attr, value)
    sys.modules[name] = new


_stub_module("supabase", {"create_client": lambda *a, **k: None})
_stub_module("dotenv", {"load_dotenv": lambda *a, **k: None})


def _load_assembly_module():
    path = REPO_ROOT / "scripts" / "session-context.py"
    spec = importlib.util.spec_from_file_location("session_context_budget", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["session_context_budget"] = mod
    spec.loader.exec_module(mod)
    return mod


sc = _load_assembly_module()


def _ctx_push() -> str:
    """The REAL section-aware CONTEXT push (Invariants + Glossary index)."""
    section = sc._load_project_context(REPO_ROOT)
    assert section is not None, "CONTEXT.md must exist and be non-empty"
    return section


class TestCleanPath:
    """AC1 clean path: no compact resume → every section present, < 9,500."""

    def test_clean_path_fits_budget_with_all_sections(self):
        ctx = _ctx_push()
        sections = [
            (sc._PRIORITY_ALWAYS_LOAD, "always_load", "## Always-Load Rules\n" + "a" * 1200, []),
            (sc._PRIORITY_USER_PROFILE, "user_profile", "## User Profile\n" + "u" * 500, []),
            (sc._PRIORITY_CONTEXT_PUSH, "project_context", ctx, []),
            (sc._PRIORITY_WORKING_STATE, "working_state", "## Working State (jarvis)\n" + "w" * 700, []),
            (sc._PRIORITY_GOALS, "goals", "## Active Goals (2)\n" + "g" * 250, []),
            (sc._PRIORITY_REMINDER, "pending_review", "**Pending memory candidates:** 3", []),
            (sc._PRIORITY_REMINDER, "milestone_sweep", "## Architecture Sweep\n- Milestone #1", []),
        ]
        output, dropped, emitted_ids, chars = sc.assemble_sections(sections)
        assert chars < sc.ASSEMBLY_BUDGET_CHARS
        assert dropped == []
        for name in (
            "always_load", "user_profile", "project_context",
            "working_state", "goals", "pending_review", "milestone_sweep",
        ):
            assert name not in dropped
        # Delivery: every section's content is actually emitted.
        assert output.count("## Always-Load Rules") == 1
        assert output.count("## User Profile") == 1
        assert output.count("## Working State (jarvis)") == 1
        assert output.count("## Active Goals (2)") == 1
        assert "### Invariants" in output
        assert "### Glossary categories" in output


class TestCompactPath:
    """AC1 + AC2: compact resume delivers the durable layer under 9,500."""

    def test_compact_path_delivers_durable_layer(self):
        ctx = _ctx_push()
        sections = [
            (sc._PRIORITY_RECOVERY, "recovery", "## Pre-Compact Recovery\n" + "s" * 2000, []),
            (sc._PRIORITY_ALWAYS_LOAD, "always_load", "## Always-Load Rules\n" + "a" * 1200, []),
            (sc._PRIORITY_USER_PROFILE, "user_profile", "## User Profile\n" + "u" * 500, []),
            (sc._PRIORITY_WORKING_STATE, "working_state", "## Working State (jarvis)\n" + "w" * 700, []),
            (sc._PRIORITY_GOALS, "goals", "## Active Goals (2)\n" + "g" * 250, []),
            (sc._PRIORITY_CONTEXT_PUSH, "project_context", ctx, []),
            (sc._PRIORITY_REMINDER, "pending_review", "**Pending memory candidates:** 3", []),
            (sc._PRIORITY_REMINDER, "milestone_sweep", "## Architecture Sweep\n- Milestone #1", []),
        ]
        output, dropped, emitted_ids, chars = sc.assemble_sections(sections)
        assert chars < sc.ASSEMBLY_BUDGET_CHARS
        # The durable layer + recovery survive; the push and reminders cut first.
        for name in ("recovery", "always_load", "user_profile", "working_state", "goals"):
            assert name not in dropped
        assert "project_context" in dropped
        for name in ("pending_review", "milestone_sweep"):
            assert name in dropped
        assert "Pre-Compact Recovery" in output
        assert "Always-Load Rules" in output
        assert "User Profile" in output
        assert "Working State (jarvis)" in output
        assert "Active Goals (2)" in output


class TestDropPriority:
    """AC3: the ranked drop order under induced overflow."""

    def test_drop_priority_order_under_overflow(self):
        sections = [
            (sc._PRIORITY_RECOVERY, "recovery", "## Pre-Compact Recovery\n" + "r" * 1000, []),
            (sc._PRIORITY_ALWAYS_LOAD, "always_load", "## Always-Load Rules\n" + "a" * 1000, []),
            (sc._PRIORITY_USER_PROFILE, "user_profile", "## User Profile\n" + "u" * 1000, []),
            (sc._PRIORITY_WORKING_STATE, "working_state", "## Working State\n" + "w" * 1000, []),
            (sc._PRIORITY_GOALS, "goals", "## Active Goals\n" + "g" * 1000, []),
            (sc._PRIORITY_CONTEXT_PUSH, "project_context", "## Project Context\n" + "c" * 1000, []),
            (sc._PRIORITY_REMINDER, "pending", "**pending**", []),
            (sc._PRIORITY_REMINDER, "sweep", "**sweep**", []),
            (sc._PRIORITY_REMINDER, "drift", "**drift**", []),
        ]
        output, dropped, emitted_ids, chars = sc.assemble_sections(sections, budget_chars=2000)
        assert dropped == [
            "drift", "sweep", "pending",   # reminders — lowest priority, later first
            "project_context",             # CONTEXT push
            "goals",
            "working_state",
            "user_profile",
            "always_load",
        ]
        # Recovery is priority 0 — the last survivor.
        assert "recovery" not in dropped
        assert "Pre-Compact Recovery" in output
        # Dropped sections are named on the dropped: line.
        dropped_line = next(
            line for line in output.splitlines() if line.startswith("dropped: ")
        )
        for name in dropped:
            assert name in dropped_line

    def test_emitted_ids_exclude_dropped_sections(self):
        """Only KEPT sections' memory ids are returned — a dropped section is
        never fed to _touch_accessed (#1271 C.1 row 6)."""
        sections = [
            (0, "keep", "## K\n" + "k" * 500, ["id-keep"]),
            (6, "drop", "## D\n" + "d" * 500, ["id-drop"]),
        ]
        output, dropped, emitted_ids, chars = sc.assemble_sections(sections, budget_chars=800)
        assert "drop" in dropped
        assert emitted_ids == ["id-keep"]
        assert "id-drop" not in emitted_ids


class TestContextPushStructure:
    """AC6: the push carries Invariants + Glossary category index only."""

    def test_push_has_invariants_and_glossary_categories(self):
        section = _ctx_push()
        assert section.startswith("## Project Context\n")
        assert "### Invariants" in section
        assert "### Glossary categories" in section
        # Per-term index and category bodies are pull-only.
        assert "### Index" not in section
        assert "### Core entities" not in section
        assert "Multi-milestone capability area" not in section

    def test_push_delivered_in_clean_assembly(self):
        """The real CONTEXT push is delivered in the assembled output — not
        just extractable, actually present (E.1 row 3 delivery check)."""
        sections = [
            (sc._PRIORITY_CONTEXT_PUSH, "project_context", _ctx_push(), []),
            (sc._PRIORITY_GOALS, "goals", "## Active Goals\n- g", []),
        ]
        output, dropped, emitted_ids, chars = sc.assemble_sections(sections)
        assert dropped == []
        assert "### Invariants" in output
        assert "### Glossary categories" in output

    def test_glossary_categories_carries_unconditional_pull_notice(self):
        """#1327 AC: the injected Glossary categories block carries an
        explicit, unconditional one-line notice that category bodies are
        omitted and how to read them — fires whenever CONTEXT.md has a
        Glossary section, not only when the push is dropped/size-constrained."""
        section = _ctx_push()
        idx = section.index("### Glossary categories")
        block = section[idx:]
        assert "pull-only" in block
        assert "CONTEXT.md" in block


class TestSelfLog:
    """AC4: every run appends its emitted size to the self-log."""

    def test_self_log_appends_json_line(self, tmp_path, monkeypatch):
        log_path = tmp_path / "session-context-size.jsonl"
        monkeypatch.setattr(sc, "_SELF_LOG_PATH", log_path)
        sc._self_log(1234, ["reminder"], True)
        lines = log_path.read_text(encoding="utf-8").splitlines()
        assert len(lines) == 1
        entry = json.loads(lines[0])
        assert entry["emitted_chars"] == 1234
        assert entry["budget_chars"] == sc.ASSEMBLY_BUDGET_CHARS
        assert entry["dropped"] == ["reminder"]
        assert entry["compact_resume"] is True

    def test_self_log_never_raises(self, tmp_path, monkeypatch):
        """A log write failure must not break session start."""
        blocked = tmp_path / "blocked"
        blocked.write_text("i am a file", encoding="utf-8")
        monkeypatch.setattr(sc, "_SELF_LOG_PATH", blocked / "x.jsonl")
        sc._self_log(0, [], False)  # must not raise

    def test_log_location_documented(self):
        """The self-log is under .claude/logs/ — gitignored, device-local."""
        assert ".claude" in str(sc._SELF_LOG_PATH)
        assert "logs" in str(sc._SELF_LOG_PATH)
        assert sc._SELF_LOG_PATH.name == "session-context-size.jsonl"

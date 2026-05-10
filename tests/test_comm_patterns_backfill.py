"""Backfill helper tests.

The backfill script is loaded via importlib (filename has a dash, can't be
imported as a module). We exercise the deterministic helpers — synthetic
session-id stability, captured-at validation, example iteration — without
calling Ollama or Supabase.

Per review #584 finding 13: ``_synth_session_id`` stability is the
idempotency contract; a refactor that silently changes its hash would
double-write every cache file on the next backfill run.
"""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

# Ensure heavy optional deps don't fail at module import time.
for _stub in ("supabase", "dotenv"):
    if _stub not in sys.modules:
        try:
            __import__(_stub)
        except ImportError:
            mod = types.ModuleType(_stub)
            if _stub == "dotenv":
                mod.load_dotenv = lambda *a, **k: None
            if _stub == "supabase":
                mod.create_client = lambda *a, **k: None
            sys.modules[_stub] = mod

_PATH = Path(__file__).resolve().parent.parent / "scripts" / "comm-patterns-backfill.py"
_spec = importlib.util.spec_from_file_location("comm_patterns_backfill", _PATH)
_mod = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(_mod)


# ---------------------------------------------------------------------------
# _synth_session_id determinism
# ---------------------------------------------------------------------------


def test_synth_session_id_is_deterministic(tmp_path: Path):
    fp = tmp_path / "x.json"
    a = _mod._synth_session_id(fp, "permission_seeking", 0)
    b = _mod._synth_session_id(fp, "permission_seeking", 0)
    assert a == b
    assert a.startswith("backfill:")


def test_synth_session_id_differs_per_input(tmp_path: Path):
    fp = tmp_path / "x.json"
    others = {
        _mod._synth_session_id(fp, "permission_seeking", 0),
        _mod._synth_session_id(fp, "tunnel_vision", 0),
        _mod._synth_session_id(fp, "permission_seeking", 1),
        _mod._synth_session_id(tmp_path / "y.json", "permission_seeking", 0),
    }
    assert len(others) == 4


# ---------------------------------------------------------------------------
# _captured_at_from_file: validation tightened (#6)
# ---------------------------------------------------------------------------


def test_captured_at_from_valid_iso_date():
    out = _mod._captured_at_from_file({"date_range": ["2026-04-01", "2026-04-30"]})
    assert out == "2026-04-01T00:00:00+00:00"


def test_captured_at_from_garbage_falls_back_to_now():
    """Free-form strings or None used to produce 'NoneT00:00:00+00:00' —
    now they fall back to a real UTC ISO string (#584 review finding 6)."""
    out_garbage = _mod._captured_at_from_file({"date_range": ["Q1 2025", "Q2 2025"]})
    out_none = _mod._captured_at_from_file({"date_range": [None, None]})
    out_missing = _mod._captured_at_from_file({})
    for out in (out_garbage, out_none, out_missing):
        assert "None" not in out
        # ISO-shaped fallback parses cleanly.
        from datetime import datetime
        datetime.fromisoformat(out)


# ---------------------------------------------------------------------------
# _iter_examples: structural robustness
# ---------------------------------------------------------------------------


def test_iter_examples_handles_missing_keys():
    """Old cache files may have only correctives or only affirmatives."""
    only_corr = {"correctives": {"x": {"examples": [{"trigger": "t", "correction": "c"}]}}}
    only_aff = {"affirmatives": {"examples": [{"trigger": "t", "snippet": "s"}]}}
    empty = {}
    assert len(_mod._iter_examples(only_corr)) == 1
    assert len(_mod._iter_examples(only_aff)) == 1
    assert _mod._iter_examples(empty) == []


def test_iter_examples_yields_categories_with_examples():
    payload = {
        "correctives": {
            "permission_seeking": {"examples": [{"trigger": "t1", "correction": "c1"}]},
            "tunnel_vision": {"examples": [{"trigger": "t2", "correction": "c2"}]},
        },
        "affirmatives": {"examples": [{"trigger": "t3", "snippet": "s3"}]},
    }
    out = _mod._iter_examples(payload)
    cats = [cat for cat, _ in out]
    assert "permission_seeking" in cats
    assert "tunnel_vision" in cats
    assert "affirmative" in cats


def test_example_to_user_text_prefers_correction_over_snippet():
    """correction wins over snippet (correction is corrective; snippet is affirmative).
    Both populated → correction wins."""
    user, prev = _mod._example_to_user_text({"trigger": "t", "correction": "c", "snippet": "s"})
    assert user == "c"
    assert prev == "t"


def test_example_to_user_text_falls_back_to_snippet():
    user, prev = _mod._example_to_user_text({"trigger": "t", "snippet": "s"})
    assert user == "s"
    assert prev == "t"


def test_example_to_user_text_empty_when_neither_present():
    user, prev = _mod._example_to_user_text({"trigger": "t"})
    assert user == ""

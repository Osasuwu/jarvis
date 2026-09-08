"""Unit tests for issue #1252 AC3: always_load admission cap.

Cap: 4 entries / 6000 bytes combined, enforced at read time in
scripts/eval-recall.py (_load_session_context), per decision
3e6594f6-27da-45d9-96d8-516a46716425.

scripts/session-context.py was deleted (#1800); its half of this cap's
coverage went with it. eval-recall.py's own cap enforcement survives here.

Tests that:
1. The loader truncates to ALWAYS_LOAD_MAX_ENTRIES when more rows are tagged.
2. The loader truncates on ALWAYS_LOAD_MAX_BYTES even under the entry cap.
3. Truncation prints a warning to stderr rather than raising.
"""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock


for _stub in ("dotenv", "supabase"):
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


def _load_module(filename, modname):
    path = Path(__file__).resolve().parent.parent.parent / "scripts" / filename
    spec = importlib.util.spec_from_file_location(modname, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[modname] = mod  # dataclass() needs cls.__module__ in sys.modules
    spec.loader.exec_module(mod)
    return mod


erc = _load_module("eval-recall.py", "eval_recall_1252")


def _mock_client(rows):
    client = MagicMock()
    query = MagicMock()
    query.select.return_value = query
    query.contains.return_value = query
    query.is_.return_value = query
    query.order.return_value = query
    query.execute.return_value = MagicMock(data=rows)
    client.table.return_value = query
    return client


def _row(i, content=""):
    return {
        "id": f"mem_{i}",
        "name": f"rule_{i}",
        "type": "reference",
        "project": "global",
        "description": "d",
        "tags": ["always_load"],
        "content": content,
    }


def test_eval_recall_caps_entries(capsys):
    rows = [_row(i) for i in range(7)]
    client = _mock_client(rows)

    text, counts = erc._load_session_context(client)

    assert counts["always_load"] == erc.ALWAYS_LOAD_MAX_ENTRIES
    assert "cap is" in capsys.readouterr().err


def test_eval_recall_caps_bytes(capsys):
    big = "x" * (erc.ALWAYS_LOAD_MAX_BYTES // 2 + 1)
    rows = [_row(0, big), _row(1, big), _row(2, big)]
    client = _mock_client(rows)

    text, counts = erc._load_session_context(client)

    assert counts["always_load"] == 1
    assert "byte budget" in capsys.readouterr().err


if __name__ == "__main__":
    import pytest

    pytest.main([__file__, "-v"])

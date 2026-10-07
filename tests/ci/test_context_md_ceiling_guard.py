"""Guard for #1985 — CONTEXT.md stays navigable.

Two properties that have to keep holding after this PR:

- **Byte ceiling.** `CONTEXT.md` is pull-only, so it was never under the push-surface
  ratchet (#1273), yet readers pulled it whole and burned their context. The ceiling lives in
  `tests/ci/fixtures/context_md_ceiling.json`; raising it means editing that file in the same
  PR, which makes regrowth a reviewable act (the push-surface ratchet's mechanism).
- **Section index.** One line per `##` section inside the first 60 lines, so a reader can
  open the one section they need instead of the whole file.

The size is measured the way CI sees it — `read_text(encoding="utf-8")` normalizes CRLF to LF
— not with `wc -c`, which on a Windows autocrlf checkout reads higher than the runner.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_PATH = Path(__file__).resolve().parent / "fixtures" / "context_md_ceiling.json"
INDEX_WINDOW_LINES = 60

_H2_RE = re.compile(r"^## (.+?)\s*$")
_INDEX_ENTRY_RE = re.compile(r"^- \*\*(.+?)\*\* — \S")


def _load_ceiling() -> tuple[Path, int]:
    entry = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))["context_md"]
    return REPO_ROOT / entry["path"], entry["bytes"]


def _section_name(heading: str) -> str:
    """`Invariants (must always hold ...)` -> `Invariants`: the index names a section by what
    precedes the first parenthetical."""
    return heading.split(" (", 1)[0].strip()


def index_problems(text: str) -> list[str]:
    """Every `##` section needs exactly one `- **Name** — read when ...` line above the first
    `##` heading and inside the first `INDEX_WINDOW_LINES` lines, and the index must not name a section that does not exist."""
    lines = text.splitlines()
    sections = [m.group(1) for line in lines if (m := _H2_RE.match(line))]
    # The index sits above the first `##` heading: the Glossary's own `- **Term** — ...`
    # lines further down are terms, not section entries.
    first_h2 = next((i for i, line in enumerate(lines) if _H2_RE.match(line)), len(lines))
    window = lines[: min(INDEX_WINDOW_LINES, first_h2)]
    indexed = [m.group(1) for line in window if (m := _INDEX_ENTRY_RE.match(line))]
    wanted = [_section_name(s) for s in sections]
    problems = []
    for name in wanted:
        count = indexed.count(name)
        if count != 1:
            problems.append(
                f"section '{name}' has {count} index lines in the first "
                f"{INDEX_WINDOW_LINES} lines (need exactly 1)"
            )
    for name in indexed:
        if name not in wanted:
            problems.append(f"index names '{name}' but no such `##` section exists")
    return problems


class TestByteCeiling:
    def test_context_md_within_ceiling(self):
        path, ceiling = _load_ceiling()
        size = len(path.read_text(encoding="utf-8").encode("utf-8"))
        assert size <= ceiling, (
            f"{path.name} is {size} bytes, ceiling is {ceiling} (over by {size - ceiling}). "
            "Trim it or move a section to docs/reference/*.md instead of raising the ceiling. "
            "If the content must stay, raise `context_md.bytes` in "
            "tests/ci/fixtures/context_md_ceiling.json in the same PR and say why in the PR body."
        )


class TestSectionIndex:
    def test_live_context_md_has_complete_index(self):
        path, _ = _load_ceiling()
        problems = index_problems(path.read_text(encoding="utf-8"))
        assert not problems, "CONTEXT.md section index is out of sync:\n  " + "\n  ".join(problems)

    def test_detector_flags_missing_stale_and_late_entries(self):
        base = "# T\n\n- **Alpha** — read when a\n- **Gone** — read when b\n\n## Alpha\n\n## Beta (x)\n"
        assert index_problems(base) == [
            "section 'Beta' has 0 index lines in the first 60 lines (need exactly 1)",
            "index names 'Gone' but no such `##` section exists",
        ]
        late = "\n" * INDEX_WINDOW_LINES + "- **Alpha** — read when a\n## Alpha\n"
        assert index_problems(late) == [
            "section 'Alpha' has 0 index lines in the first 60 lines (need exactly 1)",
        ]
        ok = "- **Alpha** — read when a\n- **Beta** — read when b\n## Alpha\n## Beta (x)\n"
        assert index_problems(ok) == []

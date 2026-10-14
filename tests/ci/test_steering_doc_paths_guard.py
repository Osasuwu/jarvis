"""Steering docs must not point at `.github/` or `docs/` paths that no longer exist (#2045).

`AGENTS.md`, `CONTEXT.md` and `docs/reference/*.md` name workflows and docs in backticks.
When the file goes, the mention stays, and nothing fails: an agent following the pointer
wastes a turn, or concludes the mechanism does not exist. `github-repo-setup.md` kept naming
the deleted `issue-checks.yml`, and `ci-guard-meta-tests.md` kept sending readers to the
deleted `ci-meta.yml` as the place meta-tests run.

A checked span is an inline code span whose whole content is one path token:
- starting with `.github/` or `docs/` — resolved from the repo root (globs must match);
- a bare `<name>.yml` / `<name>.yaml` — resolved against any file of that name under
  `.github/`. Workflows are mostly named this way in prose, and `issue-checks.yml` was.

A `#anchor` or `:line` suffix is dropped; a span holding `<` is a template and skipped.
Fenced code blocks are skipped. A historical mention stays legal by appearing in
`DEAD_PATH_ALLOWLIST` with its reason; the allowlist is itself checked, so an entry whose
file came back or whose mention went away has to be removed.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

_FENCE_LINE_RE = re.compile(r"^\s*(```|~~~)")
_SPAN_RE = re.compile(r"`([^`\n]+)`")
_BARE_YAML_RE = re.compile(r"^[A-Za-z0-9_.-]+\.ya?ml$")
_SUFFIX_RE = re.compile(r"(#.*|:\d+(-\d+)?)$")

# Span text → why it may name a path that does not exist.
DEAD_PATH_ALLOWLIST: dict[str, str] = {
    ".github/workflows/X-guard.yml": "placeholder in the naming-convention rule",
    "docs/SIGNOFF.md": "lives in jarvis-oss, not this repo",
    "docs/context/": "historical: folded into AGENTS.md by #1791",
    "docs/context/glossary-index.md": "historical: deleted by #1418",
    "docs/reference/mcp-slim-profile.md": "historical: named as deleted",
    "ci-meta.yml": "historical: deleted in #1835",
    "issue-checks.yml": "historical: deleted in #1835",
    "pr-merged.yml": "historical: deleted in #1796",
    "project-sync.yml": "historical: deleted in #1835",
    "event-dispatch.yml": "historical: retired with the severity ladder (#70)",
    "schema-drift-check.yml": "historical: the original WORKFLOW_TEST_OVERRIDES case",
    "auto-merge-enable.yml": (
        "stale: ci-guard-meta-tests.md's review-blind section still describes it as live; "
        "rewrite tracked separately"
    ),
}


def steering_docs(root: Path) -> list[Path]:
    return [
        root / "AGENTS.md",
        root / "CONTEXT.md",
        *sorted((root / "docs/reference").glob("*.md")),
    ]


def find_path_refs(text: str) -> list[tuple[int, str]]:
    """`(lineno, span)` for every checked path span outside fenced code blocks."""
    refs = []
    in_fence = False
    for lineno, line in enumerate(text.splitlines(), start=1):
        if _FENCE_LINE_RE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        for m in _SPAN_RE.finditer(line):
            span = m.group(1)
            if span != span.strip() or " " in span or "<" in span:
                continue
            if span.startswith((".github/", "docs/")) or _BARE_YAML_RE.match(span):
                refs.append((lineno, span))
    return refs


def resolves(span: str, root: Path) -> bool:
    path = _SUFFIX_RE.sub("", span)
    if _BARE_YAML_RE.match(path):
        return any((root / ".github").rglob(path))
    if any(c in path for c in "*?["):
        return any(root.glob(path))
    return (root / path).exists()


def _dead_refs(root: Path) -> list[tuple[str, int, str]]:
    dead = []
    for doc in steering_docs(root):
        for lineno, span in find_path_refs(doc.read_text(encoding="utf-8")):
            if not resolves(span, root):
                dead.append((doc.relative_to(root).as_posix(), lineno, span))
    return dead


def test_steering_docs_name_only_existing_paths():
    docs = steering_docs(REPO_ROOT)
    assert len(docs) > 2, "docs/reference/*.md matched nothing"
    unlisted = [
        f"{doc}:{lineno}: `{span}`"
        for doc, lineno, span in _dead_refs(REPO_ROOT)
        if span not in DEAD_PATH_ALLOWLIST
    ]
    assert unlisted == [], "dead path in a steering doc — fix it or allowlist it:\n" + "\n".join(
        unlisted
    )


def test_allowlist_holds_only_dead_mentioned_paths():
    still_dead = {span for _, _, span in _dead_refs(REPO_ROOT)}
    stale = sorted(set(DEAD_PATH_ALLOWLIST) - still_dead)
    assert stale == [], "allowlisted path now exists or is no longer mentioned — drop it"


def test_find_path_refs_picks_only_single_path_spans_outside_fences():
    text = "\n".join(
        [
            "See `docs/a.md#sec` and `.github/workflows/b.yml:12`, run `lane.yml`.",
            "Not `docs/a.md --flag`, not `uses: x/.github/w.yml@<sha>`, not `config/x.yaml`.",
            "```",
            "`docs/in-fence.md`",
            "```",
            "Glob `docs/reference/*.md`, template `docs/<x>.md`, prose docs/plain.md.",
        ]
    )
    assert find_path_refs(text) == [
        (1, "docs/a.md#sec"),
        (1, ".github/workflows/b.yml:12"),
        (1, "lane.yml"),
        (6, "docs/reference/*.md"),
    ]


def test_resolves_paths_globs_and_bare_workflow_names(tmp_path):
    (tmp_path / ".github/workflows").mkdir(parents=True)
    (tmp_path / ".github/workflows/live.yml").write_text("", encoding="utf-8")
    (tmp_path / "docs/reference").mkdir(parents=True)
    (tmp_path / "docs/reference/a.md").write_text("", encoding="utf-8")

    cases = {
        "docs/reference/a.md": True,
        "docs/reference/a.md#anchor": True,
        ".github/workflows/live.yml:3-9": True,
        "live.yml": True,
        "docs/reference/*.md": True,
        "docs/reference/gone.md": False,
        ".github/workflows/gone.yml": False,
        "gone.yml": False,
        "docs/other/*.md": False,
    }
    assert {span: resolves(span, tmp_path) for span in cases} == cases

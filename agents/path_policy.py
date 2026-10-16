"""Which changed paths are dangerous: the one reader of `config/protected-paths.json` (#2067).

Every reader of the protected-path list goes through this module, so the list has one glob
dialect and one bucket verdict:

- `scripts/to_tickets_afk_fit.py` (/to-tickets and /triage Q1) reads the AFK class;
- `.github/scripts/risk_tier.py` (the `risk-tier` check) reads the risk floor;
- `agents/plan_review_config.py` reads a repo's `guarded` bucket as the plan classifier's
  shared-surface globs, which `agents/plan_classifier.py` matches here;
- `.github/scripts/code_gate_verdict.py` reads the `gate` flag, loading this file by path.

The dialect. A path is normalised first: `\\` becomes `/` and a leading `./` is dropped.
Matching is case-insensitive on every OS. Then, per glob:

- `x/**` matches `x` itself and anything under `x/`;
- `a/**/b` matches the pattern `b` at any depth under `a/`;
- any other glob is `fnmatch.fnmatchcase` on the lowercased path and glob, where `*` also
  crosses `/`.

This is a superset of what each reader matched before #2067 on any OS, so no reader matches
fewer paths than it did.

Buckets, per repo entry (keys starting with `_` are comments, never buckets):

- `hitl`    — any match is AFK class 3 (checked first);
- `guarded` — any match is AFK class 2;
- `machinery`, `gate` and any bucket name this module does not know — no AFK class, but any
  match in any bucket floors the risk tier at HIGH; `gate` also sets the `gate` flag.

Stdlib only, importing nothing from `agents`: `code_gate_verdict.py` loads this file by path
under `python -I`, where neither the package nor PyYAML is importable.
"""

from __future__ import annotations

import fnmatch
import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path

AFK_BUCKETS = (("hitl", 3), ("guarded", 2))
GATE_BUCKET = "gate"


class PolicyError(ValueError):
    """A repo entry that cannot be read as buckets of globs."""


class UnknownRepoError(PolicyError):
    def __init__(self, repo: str) -> None:
        super().__init__(f"config/protected-paths.json has no entry for {repo!r}")
        self.repo = repo


class LegacySchemaError(PolicyError):
    def __init__(self, repo: str) -> None:
        super().__init__(
            f"config/protected-paths.json: {repo!r} uses the legacy flat-list "
            "schema (pre-#1708) — expected a {'hitl': [...], 'guarded': [...]} object"
        )
        self.repo = repo


class MalformedBucketError(PolicyError):
    def __init__(self, repo: str, bucket: str) -> None:
        super().__init__(
            f"config/protected-paths.json: {repo!r} bucket {bucket!r} is not a list of globs"
        )
        self.repo = repo
        self.bucket = bucket


def _normalise(path: str) -> str:
    norm = path.replace("\\", "/")
    if norm.startswith("./"):
        norm = norm[2:]
    return norm.lower()


def _matches(path: str, glob: str) -> bool:
    """`path` is already normalised; see the module docstring for the dialect."""
    glob = glob.lower()
    if glob.endswith("/**"):
        prefix = glob[:-3].rstrip("/")
        return path == prefix or path.startswith(prefix + "/")
    if "/**/" in glob:
        head, tail = glob.split("/**/", 1)
        if not path.startswith(head + "/"):
            return False
        rest = path[len(head) + 1 :]
        return fnmatch.fnmatchcase(rest, tail) or fnmatch.fnmatchcase(rest, "*/" + tail)
    return fnmatch.fnmatchcase(path, glob)


def matched_paths(paths: Iterable[str], globs: Iterable[str]) -> tuple[str, ...]:
    """The caller's own strings, in input order, of the paths that match any glob."""
    globs = tuple(globs)
    if not globs:
        return ()
    return tuple(p for p in paths if any(_matches(_normalise(p), g) for g in globs))


@dataclass(frozen=True)
class PathVerdict:
    afk_class: int | None
    afk_bucket: str | None
    afk_matched: tuple[str, ...]
    risk_floor: str
    risk_matched: tuple[str, ...]
    machinery: bool
    hitl: bool
    gate: bool


def classify_buckets(paths: Iterable[str], buckets: Mapping[str, Iterable[str]]) -> PathVerdict:
    """One repo's verdict for a set of changed paths (bucket rules: module docstring)."""
    paths = tuple(paths)
    hits = {
        name: matched_paths(paths, globs)
        for name, globs in buckets.items()
        if not name.startswith("_")
    }
    afk_class, afk_bucket, afk_matched = None, None, ()
    for name, cls in AFK_BUCKETS:
        if hits.get(name):
            afk_class, afk_bucket, afk_matched = cls, name, hits[name]
            break
    matched = {p for found in hits.values() for p in found}
    risk_matched = tuple(p for p in paths if p in matched)
    return PathVerdict(
        afk_class=afk_class,
        afk_bucket=afk_bucket,
        afk_matched=afk_matched,
        risk_floor="HIGH" if risk_matched else "LOW",
        risk_matched=risk_matched,
        machinery=bool(hits.get("machinery")),
        hitl=bool(hits.get("hitl")),
        gate=bool(hits.get(GATE_BUCKET)),
    )


class Policy:
    """A parsed `protected-paths.json`. Entries are validated per repo, on lookup, so a
    malformed entry for one repo cannot change another repo's answer."""

    def __init__(self, data: Mapping[str, object]) -> None:
        self._data = data

    def repos(self) -> tuple[str, ...]:
        return tuple(key for key in self._data if not key.startswith("_"))

    def buckets(self, repo: str) -> dict[str, tuple[str, ...]]:
        if repo.startswith("_") or repo not in self._data:
            raise UnknownRepoError(repo)
        entry = self._data[repo]
        if not isinstance(entry, dict):
            raise LegacySchemaError(repo)
        buckets = {}
        for name, globs in entry.items():
            if name.startswith("_"):
                continue
            if not isinstance(globs, list) or not all(isinstance(g, str) for g in globs):
                raise MalformedBucketError(repo, name)
            buckets[name] = tuple(globs)
        return buckets

    def classify(self, repo: str, paths: Iterable[str]) -> PathVerdict:
        return classify_buckets(paths, self.buckets(repo))


def load_policy(path: str | Path) -> Policy:
    """Read the file; a JSON decode error propagates unchanged."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise TypeError(f"{path} must hold a JSON object, not {type(data).__name__}")
    return Policy(data)

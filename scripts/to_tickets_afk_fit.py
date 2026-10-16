"""AFK-fit static path-grep helper for /to-tickets and /triage (#642, split per #1708).

Question 1 of the four-question AFK-fit checklist is static: does any
declared-changed file match a protected-path glob for the target repo?
config/protected-paths.json holds two AFK buckets per repo:

- ``hitl``    — identity/security config, a categorical security boundary.
                Any match -> class 3 (afk:3-human), hard refusal.
- ``guarded`` — shared surfaces with off-repo consumers, recoverable via a
                locked plan. Any match -> class 2 (afk:2-plan).

No match in either bucket falls through to Q2-Q4 LLM judgement (documented
in each skill's own SKILL.md, not reimplemented here).

Reading the file and matching globs are `agents/path_policy.py`'s (#2067), so
Q1 answers in the same dialect as every other reader of the list.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from agents import path_policy  # noqa: E402
from agents.plan_classifier import label_for  # noqa: E402


def load_protected_paths(path: str | Path) -> dict[str, dict[str, list[str]]]:
    """Each repo's ``hitl`` and ``guarded`` buckets; ``ValueError`` on a legacy
    flat-list entry or a bucket that is not a list of globs."""
    policy = path_policy.load_policy(path)
    config: dict[str, dict[str, list[str]]] = {}
    for repo in policy.repos():
        buckets = policy.buckets(repo)
        config[repo] = {
            "hitl": list(buckets.get("hitl", ())),
            "guarded": list(buckets.get("guarded", ())),
        }
    return config


@dataclass(frozen=True)
class ClassVerdict:
    cls: int | None
    bucket: str | None
    label: str | None
    matched_files: tuple[str, ...]
    reason: str


def classify_static_paths(
    declared_files: list[str],
    repo: str,
    config: dict[str, dict[str, list[str]]],
) -> ClassVerdict:
    if repo not in config:
        return ClassVerdict(
            cls=None,
            bucket=None,
            label=None,
            matched_files=(),
            reason="unknown repo, judge manually",
        )

    verdict = path_policy.classify_buckets(declared_files, config[repo])
    if verdict.afk_class is not None:
        return ClassVerdict(
            cls=verdict.afk_class,
            bucket=verdict.afk_bucket,
            label=label_for(verdict.afk_class),
            matched_files=verdict.afk_matched,
            reason=f"matched {verdict.afk_bucket} path(s): {', '.join(verdict.afk_matched)}",
        )

    return ClassVerdict(
        cls=None,
        bucket=None,
        label=None,
        matched_files=(),
        reason="no protected-path match; fall through to Q2-Q4",
    )

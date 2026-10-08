"""The `risk-tier` required check: the PR body's `Risk:` line becomes a merge hold (#2004).

Runs from the `risk-tier` job of `.github/workflows/pr-body-check.yml` on `pull_request`
and `pull_request_review` events (decisions D7, D10, D11 and "Risk-tier check — the hold
is the check itself" in docs/decisions/2026-Q4.md). The job checks out the PR's *base*
branch and runs this file from it, so the protected-path list and the classifier a PR is
judged by are the base's: a PR cannot shorten its own list. Nothing of the PR head is
checked out, imported or executed here; the PR is read through the API as data.

Verdict, in order:

1. the body must carry exactly one well-formed `Risk:` line (grammar: risk_tier.md);
2. the computed tier is the highest of: a changed path in any bucket of the base's
   `config/protected-paths.json` entry (HIGH), test weakening (HIGH), and the plan
   classifier's ordinal (3 -> HIGH, 2 -> MEDIUM, 1 -> LOW). Anything unreadable is HIGH;
3. final tier = max(computed, declared). LOW and MEDIUM pass;
4. HIGH and CRITICAL pass only with an APPROVED review on the current head SHA from an
   admin human who is not the lane's bot.

Stdlib plus `agents.plan_classifier` / `agents.plan_review_config` (PyYAML) and the glob
matcher of `scripts/to_tickets_afk_fit.py`, all read from the base checkout.
"""

import collections
import fnmatch
import json
import os
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from agents.plan_classifier import ChangeSet, classify, prod_areas_from_paths  # noqa: E402
from agents.plan_review_config import load_plan_review_config  # noqa: E402
from scripts.to_tickets_afk_fit import _matched_files  # noqa: E402

SEVERITY = ("LOW", "MEDIUM", "HIGH", "CRITICAL")
HOLD_TIERS = ("HIGH", "CRITICAL")
GRAMMAR = "Risk: LOW|MEDIUM|HIGH|CRITICAL — <reason>"
DOC = ".github/scripts/risk_tier.md"
DEFAULT_BOT_LOGIN = "osasuwu-bot"

_COMMENT = re.compile(r"<!--.*?(?:-->|\Z)", re.DOTALL)
_FENCE = re.compile(r"^[ \t]{0,3}(`{3,}|~{3,})")
_FENCE_CLOSE = re.compile(r"^[ \t]{0,3}(`{3,}|~{3,})[ \t]*$")
# A line that announces itself as the Risk line: the label, its colon, nothing else asked.
_LABEL = re.compile(r"^[ \t]*(?:[-*][ \t]+)?(?:\*\*)?Risk(?:\*\*)?[ \t]*:", re.IGNORECASE)
_TIER = r"(?:LOW|MEDIUM|HIGH|CRITICAL)"
_RISK_LINE = re.compile(
    rf"^[ \t]*(?:[-*][ \t]+)?Risk[ \t]*:[ \t]*"
    rf"(?:\*\*(?P<b>{_TIER})\*\*|(?P<p>{_TIER}))"
    r"[ \t]+(?:—|–|--|-)[ \t]+\S.*$",
    re.IGNORECASE,
)

_TEST_NAME = re.compile(r"^[+-][ \t]*(?:async[ \t]+)?def[ \t]+(test\w*)[ \t]*\(")
_SKIP_MARKERS = (
    "pytest.mark.skip",
    "skipif",
    "xfail",
    "pytest.skip(",
    "pytest.importorskip(",
    "unittest.skip",
    "collect_ignore",
)
_TEST_BASENAMES = ("test_*.py", "*_test.py", "conftest.py")


def _visible_lines(body):
    """The body's lines minus HTML comments and fenced code (a `>` quote never matches _LABEL)."""
    text = _COMMENT.sub("", (body or "").replace("\r\n", "\n").replace("\r", "\n"))
    fence = None
    lines = []
    for line in text.split("\n"):
        opener = _FENCE.match(line)
        if fence is None and opener:
            fence = opener.group(1)
            continue
        if fence is not None:
            closer = _FENCE_CLOSE.match(line)
            if closer and closer.group(1)[0] == fence[0] and len(closer.group(1)) >= len(fence):
                fence = None
            continue
        lines.append(line)
    return lines


def parse_declared(body):
    """`(tier, None)` for exactly one well-formed Risk line, else `(None, problem)`.

    problem is `missing`, `malformed` or `duplicate`; the grammar is risk_tier.md.
    """
    candidates = [line for line in _visible_lines(body) if _LABEL.match(line)]
    if not candidates:
        return None, "missing"
    if len(candidates) > 1:
        return None, "duplicate"
    match = _RISK_LINE.match(candidates[0].rstrip())
    if not match:
        return None, "malformed"
    return (match.group("b") or match.group("p")).upper(), None


def _is_test_file(path):
    base = path.rsplit("/", 1)[-1]
    return path.startswith("tests/") or any(fnmatch.fnmatchcase(base, p) for p in _TEST_BASENAMES)


def path_tier(paths, repo, root):
    """HIGH when a changed path sits in any bucket of the base's protected list."""
    try:
        data = json.loads((Path(root) / "config" / "protected-paths.json").read_text("utf-8"))
        entry = data[repo]
        globs = [g for key, value in entry.items() if not key.startswith("_") for g in value]
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        return "HIGH", [f"protected-path list unreadable at base ({type(exc).__name__}): fail closed"]
    hits = _matched_files(list(paths), globs)
    if hits:
        return "HIGH", [f"protected path(s): {', '.join(hits)}"]
    return "LOW", []


def test_weakening(files):
    """HIGH reasons for removed test functions, removed/undiffable test files, skip markers."""
    reasons = []
    removed, added = collections.Counter(), collections.Counter()
    for f in files:
        name = f["filename"]
        if not _is_test_file(name):
            continue
        if f.get("status") == "removed":
            reasons.append(f"test file removed: {name}")
            continue
        patch = f.get("patch")
        if patch is None:
            reasons.append(f"test file with no readable diff: {name}")
            continue
        for line in patch.split("\n"):
            m = _TEST_NAME.match(line)
            if m:
                (removed if line[0] == "-" else added)[m.group(1)] += 1
            elif line.startswith("+") and any(s in line for s in _SKIP_MARKERS):
                reasons.append(f"skip/xfail added in {name}: {line[1:].strip()}")
    for test, count in sorted(removed.items()):
        if count > added[test]:
            reasons.append(f"test function removed: {test}")
    return reasons


def _changed_paths(files):
    """Every path the diff touches: the new name and, for a rename, the old one."""
    return tuple(p for f in files for p in (f["filename"], f.get("previous_filename")) if p)


def classifier_tier(files, root):
    paths = _changed_paths(files)
    churn = sum(f.get("additions", 0) + f.get("deletions", 0) for f in files)
    try:
        config = load_plan_review_config(Path(root) / "config" / "plan_review.yaml")
    except Exception as exc:  # unreadable config must not read as a clean diff
        return "HIGH", [f"plan_review.yaml unreadable at base ({type(exc).__name__}): fail closed"]
    ordinal = classify(config, ChangeSet(paths, churn, prod_areas_from_paths(paths)))
    return {1: "LOW", 2: "MEDIUM", 3: "HIGH"}[ordinal], (
        [f"classifier ordinal {ordinal}"] if ordinal > 1 else []
    )


def computed_tier(files, changed_files, repo, root):
    """`(tier, reasons)` from the diff alone; the declared line cannot lower it."""
    tiers, reasons = [], []
    if len(files) < changed_files:
        tiers.append("HIGH")
        reasons.append(f"only {len(files)} of {changed_files} changed files listable: fail closed")
    paths = _changed_paths(files)
    for tier, why in (
        path_tier(paths, repo, root),
        ("HIGH", test_weakening(files)),
        classifier_tier(files, root),
    ):
        if why:
            tiers.append(tier)
            reasons.extend(why)
    return max(tiers or ["LOW"], key=SEVERITY.index), reasons


def _paged(api, path):
    items, page = [], 1
    while True:
        batch = api(f"{path}?per_page=100&page={page}")
        items.extend(batch)
        if len(batch) < 100:
            return items
        page += 1


def releasing_reviewer(api, repo, number, head_sha, bot):
    """The login of an admin human whose latest review is APPROVED at `head_sha`, or None."""
    latest = {}
    for review in _paged(api, f"repos/{repo}/pulls/{number}/reviews"):
        user = review.get("user") or {}
        if review.get("state") == "COMMENTED" or not user.get("login"):
            continue
        latest[user["login"]] = review
    for login, review in latest.items():
        if review["state"] != "APPROVED" or review.get("commit_id") != head_sha:
            continue
        if (review["user"].get("type") == "Bot") or login.lower() == bot.lower():
            continue
        try:
            permission = api(f"repos/{repo}/collaborators/{urllib.parse.quote(login)}/permission")
        except Exception as exc:  # an unreadable permission is not an admin
            print(f"::warning::permission lookup for {login} failed: {exc}")
            continue
        if permission.get("permission") == "admin":
            return login
    return None


def evaluate(api, repo, number, event_head_sha, root, bot=DEFAULT_BOT_LOGIN):
    """`(ok, messages)` for one PR. `api(path)` GETs a JSON document from the GitHub API."""
    pr = api(f"repos/{repo}/pulls/{number}")
    head = pr["head"]["sha"]
    if head != event_head_sha:
        return False, [f"head moved to {head[:7]} (event was {event_head_sha[:7]}): superseded by a newer push"]
    declared, problem = parse_declared(pr.get("body"))
    if problem:
        return False, [
            f"The PR body has a {problem} Risk line. Expected exactly one line `{GRAMMAR}` "
            f"(grammar and examples: {DOC})."
        ]
    files = _paged(api, f"repos/{repo}/pulls/{number}/files")
    computed, reasons = computed_tier(files, pr.get("changed_files", len(files)), repo, root)
    final = max(declared, computed, key=SEVERITY.index)
    summary = f"declared {declared}, computed {computed}, final {final}" + "".join(
        f"\n  - {r}" for r in reasons
    )
    if final not in HOLD_TIERS:
        return True, [summary]
    releaser = releasing_reviewer(api, repo, number, head, bot)
    if releaser:
        return True, [summary, f"released by an APPROVED review from admin {releaser} at {head[:7]}"]
    return False, [
        summary,
        f"{final} holds until an admin human (not {bot}) leaves an APPROVED review on the "
        f"current head {head[:7]}; a new push needs a new approval. See {DOC} (residual risks).",
    ]


def _github_get(path):
    req = urllib.request.Request(
        f"https://api.github.com/{path}",
        headers={
            "Authorization": f"Bearer {os.environ['GITHUB_TOKEN']}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())


def main():
    ok, messages = evaluate(
        _github_get,
        os.environ["GITHUB_REPOSITORY"],
        os.environ["PR_NUMBER"],
        os.environ["HEAD_SHA"],
        Path(__file__).resolve().parents[2],
        os.environ.get("LANE_BOT_LOGIN", DEFAULT_BOT_LOGIN),
    )
    for line in messages:
        print(line)
    if not ok:
        print(f"::error::{messages[-1]}")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()

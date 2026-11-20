"""The `risk-tier` required check: the PR body's `Risk:` line becomes a merge hold (#2004).

Runs from the `risk-tier` composite action (`.github/actions/risk-tier/action.yml`), called by
the `risk-tier` job of a host's `pr-body-check.yml` on `pull_request` and
`pull_request_review` events (decisions D7, D10, D11 and "Risk-tier check — the hold is the
check itself" in docs/decisions/2026-Q4.md). Two checkouts, neither of the PR head: this
file and the classifier come from a jarvis checkout pinned to a SHA (the code root), and the
protected-path list comes from the host's own `config/protected-paths.json` at the PR's
*base* commit (`RISK_TIER_HOST_ROOT`, D7). A PR cannot shorten its own list, and a host
without that file gets HIGH on every diff. The PR is read through the API as data.

Verdict, in order:

1. the body must carry exactly one well-formed `Risk:` line (grammar: risk_tier.md), except a
   Dependabot PR (author `dependabot[bot]`, type `Bot`), whose body is not read and whose
   declared tier is fixed at HIGH (#2059);
2. the computed tier is the highest of: a changed path in any bucket of the host base's
   `config/protected-paths.json` entry (HIGH), test weakening (HIGH), and the plan
   classifier's ordinal (3 -> HIGH, 2 -> MEDIUM, 1 -> LOW). Anything unreadable is HIGH.
   A diff of modified `.py` files whose two sides (merge base, head; read through the
   contents API) differ in plain comments alone loses the path floor and the classifier's
   shared-surface input (the comment-only exemption, #2201);
3. final tier = max(computed, declared, the CI reviewer's raise from its review evidence,
   #2202); red while the head's code review has not completed. LOW and MEDIUM pass;
4. HIGH and CRITICAL pass when the live PR's author holds the releasing role: `admin`
   permission, not a `Bot` account, not the lane's bot (#2088). Every other author's HIGH or
   CRITICAL PR passes only with an APPROVED review on the current head SHA from a holder of
   the releasing role (`admin` permission) who is not a `Bot` account and not the lane's bot.

Stdlib plus `agents.plan_classifier` / `agents.plan_review_config` (PyYAML) and
`agents.path_policy` (the protected-list reader and its glob dialect, #2067), all read from
the pinned code root, and the shared GitHub client `github_client.py` beside this script
(#2068), loaded by file path at import.
"""

import ast
import base64
import collections
import dataclasses
import fnmatch
import importlib.util
import io
import os
import re
import sys
import tokenize
import urllib.error
import urllib.parse
from pathlib import Path

CODE_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(CODE_ROOT))

from agents.plan_classifier import ChangeSet, classify, prod_areas_from_paths  # noqa: E402
from agents.plan_review_config import load_plan_review_config  # noqa: E402
from agents import path_policy  # noqa: E402


def _load_client():
    """`github_client.py` beside this script, shared through `sys.modules` so that
    `ListingTruncated` is one class within the process."""
    name = "_jarvis_github_client"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(
        name, Path(__file__).resolve().with_name("github_client.py")
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        sys.modules.pop(name, None)  # a half-built module must not be handed out next time
        raise
    return module


github_client = _load_client()

SEVERITY = ("LOW", "MEDIUM", "HIGH", "CRITICAL")
HOLD_TIERS = ("HIGH", "CRITICAL")
GRAMMAR = "Risk: LOW|MEDIUM|HIGH|CRITICAL — <reason>"
DOC = ".github/scripts/risk_tier.md"
HOST_SETUP_DOC = "docs/reference/lane-host-setup.md"
EXEMPTION = "comment-only exemption"
# A Dependabot PR carries upstream release notes, not a Risk line, so its body is not read and
# its declared tier is fixed (#2059). HIGH: only a releasing-role holder's head-SHA approval
# releases it.
DEPENDABOT = "dependabot[bot]"
DEPENDABOT_TIER = "HIGH"
# Listing caps (#2068). Files: GitHub serves at most 3000 per PR. A listing that
# reaches its cap fails closed, never reads as whole.
MAX_FILE_PAGES = 30
MAX_REVIEW_PAGES = 10
# The comment-only exemption reads two blobs per file; past this many files it reads none
# and the floor stands (#2201).
MAX_SOURCE_FILES = 30

_COMMENT = re.compile(r"<!--.*?(?:-->|\Z)", re.DOTALL)
_FENCE = re.compile(r"^[ \t]{0,3}(`{3,}|~{3,})")
_FENCE_CLOSE = re.compile(r"^[ \t]{0,3}(`{3,}|~{3,})[ \t]*$")
# A line that announces itself as the Risk line: the label, its colon, nothing else asked.
_LABEL = re.compile(r"^[ ]{0,3}(?:[-*][ \t]+)?(?:\*\*)?Risk(?:\*\*)?[ \t]*:", re.IGNORECASE)
_TIER = r"(?:LOW|MEDIUM|HIGH|CRITICAL)"
_RISK_LINE = re.compile(
    rf"^[ ]{{0,3}}(?:[-*][ \t]+)?Risk[ \t]*:[ \t]*"
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

# The comment-only exemption (#2201). A comment some tool or the interpreter reads: decision
# "Three risk tiers" names noqa, type: ignore, pragma and fmt:; the rest change a linter's, a
# type checker's or a scanner's verdict just the same (the set redrobot#3368 chose). Matched
# anywhere in the comment, case-insensitively: a prose comment that only looks like one costs
# the exemption, nothing more.
_DIRECTIVE = re.compile(
    r"^#!|noqa|type\s*:|pragma|fmt\s*:|yapf\s*:|isort\s*:|pylint\s*:|mypy\s*:|pyright\s*:"
    r"|pyre-|ruff\s*:|flake8|nosec|gitleaks\s*:|coding[:=]",
    re.IGNORECASE,
)
# A CR not followed by LF. Python versions and tools disagree on whether it ends a line
# (tokenize on 3.12+ says no, 3.11 and ruff say yes), so the line a directive sits on is
# not well defined: no exemption.
_LONE_CR = re.compile(rb"\r(?!\n)")
# A shebang or a coding cookie: read by position, on the first line or two.
_HEADER = re.compile(r"^#!|coding[:=]", re.IGNORECASE)


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


def is_dependabot(pr):
    """The live PR's author is the Dependabot app (#2059): the login and the `Bot` type.

    Read from the API's PR object, never from PR text. The `[bot]` suffix is reserved for
    GitHub Apps, so no human account carries this login.
    """
    user = pr.get("user") or {}
    return user.get("login") == DEPENDABOT and user.get("type") == "Bot"


def _clean(text):
    """PR-controlled text for a log line: no newline can start a `::` workflow command."""
    return text.replace("\r", "\\r").replace("\n", "\\n")


def _is_test_file(path):
    base = path.rsplit("/", 1)[-1]
    return path.startswith("tests/") or any(fnmatch.fnmatchcase(base, p) for p in _TEST_BASENAMES)


def path_tier(paths, repo, host_root):
    """HIGH when a changed path sits in any bucket of the host base's protected list.

    A host with no list, or none for this repo, is HIGH on every diff: the reason names the
    fix (D2, D7), so a host that has not finished enabling the lane reads it in the check.
    """
    tier, reasons, _ = _path_floor(paths, repo, host_root)
    return tier, reasons


def _path_floor(paths, repo, host_root):
    """`(tier, reasons, matched)`: :func:`path_tier`'s verdict plus the protected paths that
    matched. `matched` is empty unless the floor comes from a match, so a list that cannot be
    read never offers the comment-only exemption anything to drop."""
    if host_root is None:
        return (
            "HIGH",
            [
                "RISK_TIER_HOST_ROOT is not set: no host checkout to read "
                "config/protected-paths.json from"
            ],
            (),
        )
    adopt = f"every diff is HIGH until the host adds it (D2, {HOST_SETUP_DOC})"
    try:
        policy = path_policy.load_policy(Path(host_root) / "config" / "protected-paths.json")
        buckets = policy.buckets(repo)
    except path_policy.UnknownRepoError:
        why = f"config/protected-paths.json has no entry for {repo} at the base commit: {adopt}"
        return "HIGH", [why], ()
    except path_policy.MalformedBucketError:
        why = (
            f"protected-path list for {repo} has a bucket that is not a list of globs: fail closed"
        )
        return "HIGH", [why], ()
    except FileNotFoundError:
        return "HIGH", [f"config/protected-paths.json not found at the base commit: {adopt}"], ()
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        why = f"protected-path list unreadable at base ({type(exc).__name__}): fail closed"
        return "HIGH", [why], ()
    if not any(buckets.values()):
        why = f"protected-path list for {repo} has no globs at the base commit: {adopt}"
        return "HIGH", [why], ()
    verdict = path_policy.classify_buckets(paths, buckets)
    if verdict.risk_floor == "HIGH":
        matched = tuple(verdict.risk_matched)
        return "HIGH", [f"protected path(s): {', '.join(map(_clean, matched))}"], matched
    return "LOW", [], ()


def _directives(source):
    """Each directive comment of `source` (bytes) with its anchor: the number of code tokens
    before it, and whether it trails code on its line. Comments and blank lines do not move
    the anchor, so a plain comment added next to a directive leaves it in place; a directive
    moved to another line of code, or from its own line onto a line of code, does not. A
    shebang or coding cookie works only on the first lines, so its line number counts too."""
    anchor, last, found = 0, None, []
    for tok in tokenize.tokenize(io.BytesIO(source).readline):
        if tok.type == tokenize.COMMENT:
            if _DIRECTIVE.search(tok.string):
                trailing = last is not None and last.end[0] == tok.start[0]
                row = tok.start[0] if _HEADER.search(tok.string) else None
                found.append((anchor, trailing, row, tok.string))
        elif tok.type != tokenize.NL:
            anchor += 1
            if tok.type not in (tokenize.NEWLINE, tokenize.INDENT, tokenize.DEDENT):
                last = tok
    return found


def is_comment_only_edit(before, after):
    """True when `before` -> `after` (bytes) changes plain comments alone (#2201).

    The AST is equal, and a docstring is a node of it, so a docstring edit fails here; every
    directive comment is unchanged and at the same anchor. A missing side, a lone CR, or a
    side that does not decode, parse or tokenize is False: the rule fails closed.
    """
    try:
        if _LONE_CR.search(before) or _LONE_CR.search(after):
            return False
        if ast.dump(ast.parse(before)) != ast.dump(ast.parse(after)):
            return False
        return _directives(before) == _directives(after)
    except Exception:  # anything the rule cannot read is no exemption
        return False


def is_comment_only(files, sources):
    """True when every listed file is a `.py` file whose `(before, after)` in `sources` is a
    comment-only edit. A file with no entry, or any other language, means no exemption: a
    new language gets none until it has a rule of its own (risk_tier.md)."""
    if not files or not sources:
        return False
    for f in files:
        pair = sources.get(f["filename"])
        if not _covered(f) or pair is None or not is_comment_only_edit(*pair):
            return False
    return True


def _covered(f):
    """A modified `.py` file: added, removed or renamed has no two sides of one path."""
    return f.get("status") == "modified" and f["filename"].endswith(".py")


def read_sources(api, repo, pr, files):
    """`(sources, note)` for :func:`computed_tier`: each file at the PR's merge base and at
    its head, the two commits its file list is a diff of. Nothing is read when a file is not
    covered or there are more than MAX_SOURCE_FILES; any failure reads as no sources."""
    if not files or not all(_covered(f) for f in files):
        return None, ""
    if len(files) > MAX_SOURCE_FILES:
        return None, f"{EXEMPTION} not checked: {len(files)} files, more than {MAX_SOURCE_FILES}"
    head = pr["head"]["sha"]
    try:
        compare = api("GET", f"repos/{repo}/compare/{pr['base']['sha']}...{head}")
        merge_base = compare["merge_base_commit"]["sha"]
        return {
            f["filename"]: (
                _blob(api, repo, f["filename"], merge_base),
                _blob(api, repo, f["filename"], head),
            )
            for f in files
        }, ""
    except Exception as exc:  # what cannot be read keeps the floor
        return None, f"{EXEMPTION} not checked: {_clean(str(exc))}"


def _blob(api, repo, path, ref):
    entry = api("GET", f"repos/{repo}/contents/{urllib.parse.quote(path)}?ref={ref}")
    if not (
        isinstance(entry, dict)
        and entry.get("type") == "file"
        and entry.get("encoding") == "base64"
    ):  # a directory, a submodule, or a file over the contents API's 1 MB inline limit
        raise ValueError(f"{path}@{ref[:7]} is not an inline file")
    return base64.b64decode(entry["content"])


def test_weakening(files):
    """HIGH reasons for removed test functions, removed/undiffable test files, skip markers."""
    reasons = []
    removed, added = collections.Counter(), collections.Counter()
    for f in files:
        name = f["filename"]
        old_name = f.get("previous_filename")
        if old_name and _is_test_file(old_name) and not _is_test_file(name):
            reasons.append(f"test file renamed out of the test set: {_clean(old_name)}")
            continue
        if not _is_test_file(name):
            continue
        if f.get("status") == "removed":
            reasons.append(f"test file removed: {_clean(name)}")
            continue
        patch = f.get("patch")
        if patch is None:
            if f.get("status") == "renamed" and not f.get("changes"):
                continue  # a pure rename carries no patch and changes no line
            reasons.append(f"test file with no readable diff: {_clean(name)}")
            continue
        for line in patch.split("\n"):
            m = _TEST_NAME.match(line)
            if m:
                (removed if line[0] == "-" else added)[m.group(1)] += 1
            elif line.startswith("+") and any(s in line for s in _SKIP_MARKERS):
                reasons.append(f"skip/xfail added in {_clean(name)}: {_clean(line[1:].strip())}")
    for test, count in sorted(removed.items()):
        if count > added[test]:
            reasons.append(f"test function removed: {test}")
    return reasons


def _changed_paths(files):
    """Every path the diff touches: the new name and, for a rename, the old one."""
    return tuple(p for f in files for p in (f["filename"], f.get("previous_filename")) if p)


def classifier_tier(files, code_root, shared_surface=True):
    """The plan classifier's ordinal as a tier. `shared_surface=False` drops its shared-surface
    input (the `guarded` bucket again), for a diff the comment-only exemption covers."""
    paths = _changed_paths(files)
    churn = sum(f.get("additions", 0) + f.get("deletions", 0) for f in files)
    try:
        config = load_plan_review_config(Path(code_root) / "config" / "plan_review.yaml")
    except Exception as exc:  # unreadable config must not read as a clean diff
        return "HIGH", [f"plan_review.yaml unreadable ({type(exc).__name__}): fail closed"]
    if not shared_surface:
        config = dataclasses.replace(
            config, class_2=dataclasses.replace(config.class_2, shared_surface_globs=())
        )
    ordinal = classify(config, ChangeSet(paths, churn, prod_areas_from_paths(paths)))
    return {1: "LOW", 2: "MEDIUM", 3: "HIGH"}[ordinal], (
        [f"classifier ordinal {ordinal}"] if ordinal > 1 else []
    )


def computed_tier(files, changed_files, repo, host_root, code_root=CODE_ROOT, read_sources=None):
    """`(tier, reasons)` from the diff alone; the declared line cannot lower it.

    `read_sources()` returns `(sources, note)`: each listed file's `(before, after)` bytes, or
    None, and a line for the log. It is called only when a protected path matched, and a diff
    it shows to change comments alone (:func:`is_comment_only`) loses the path floor and the
    classifier's shared-surface input, nothing else (#2201).
    """
    tiers, reasons = [], []
    if len(files) < changed_files:
        tiers.append("HIGH")
        reasons.append(f"only {len(files)} of {changed_files} changed files listable: fail closed")
    paths = _changed_paths(files)
    floor = _path_floor(paths, repo, host_root)
    exempt = False
    if floor[2] and read_sources is not None:
        sources, note = read_sources()
        if note:
            reasons.append(note)
        exempt = is_comment_only(files, sources)
    if exempt:
        reasons.append(
            f"{EXEMPTION}: protected path(s) {', '.join(map(_clean, floor[2]))} changed in comments only"
        )
        floor = ("LOW", [], ())
    for tier, why in (
        floor[:2],
        ("HIGH", test_weakening(files)),
        classifier_tier(files, code_root, shared_surface=not exempt),
    ):
        if why:
            tiers.append(tier)
            reasons.extend(why)
    return max(tiers or ["LOW"], key=SEVERITY.index), reasons


def releasing_reviewer(api, repo, number, head_sha, bot):
    """The login of a releasing-role holder (`admin`, not a bot) whose latest review is
    APPROVED at `head_sha`, or None.

    A reviews listing past its cap raises `ListingTruncated` to the caller."""
    latest = {}
    reviews = github_client.paged(
        api, f"repos/{repo}/pulls/{number}/reviews", max_pages=MAX_REVIEW_PAGES
    )
    for review in reviews:
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
            permission = api(
                "GET", f"repos/{repo}/collaborators/{urllib.parse.quote(login)}/permission"
            )
        except Exception as exc:  # an unreadable permission is not an admin
            print(f"::warning::permission lookup for {login} failed: {exc}")
            continue
        if permission.get("permission") == "admin":
            return login
    return None


def admin_author(api, repo, pr, bot):
    """The login of the PR's author when it holds the releasing role (`admin`), is not a
    `Bot` account and is not `bot`, or None.

    An unreadable permission is not an admin."""
    user = pr.get("user") or {}
    login = user.get("login")
    if not login or user.get("type") == "Bot" or login.lower() == bot.lower():
        return None
    try:
        permission = api(
            "GET", f"repos/{repo}/collaborators/{urllib.parse.quote(login)}/permission"
        )
    except Exception as exc:  # an unreadable permission is not an admin
        print(f"::warning::author permission lookup for {login} failed: {exc}")
        return None
    return login if permission.get("permission") == "admin" else None


# --- the reviewer's raise (#2202) ---------------------------------------------------------


def _gate():
    """`code_gate_verdict.py` beside this script, by file path on first use: the review
    evidence is read with the code-gate's own provenance and artifact rules."""
    name = "_jarvis_code_gate_verdict"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(
        name, Path(__file__).resolve().with_name("code_gate_verdict.py")
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        sys.modules.pop(name, None)  # a half-built module must not be handed out next time
        raise
    return module


def review_raise(entries, number, head_sha, base_ref, default_branch):
    """`(pending, raises)` from the code review's evidence entries for this head (#2202).

    `entries` are `code_gate_verdict.gather_entries`'s. `pending` is why the review is not
    done yet, or None: a bound review run is unfinished, or no successful bound run has
    left evidence. `raises` lists `(tier, reason)`: each raise any attempt's evidence
    carries, and HIGH for each attempt whose evidence cannot be read (deleted, expired,
    undownloadable, malformed, for another commit), since it may hide a raise.
    """
    gate = _gate()
    raises, reviewed = [], False
    for entry in entries:
        run = entry["run"]
        provenance = gate.run_provenance(run, number, head_sha, default_branch)
        if not provenance:
            continue
        if run.get("status") != "completed" or run.get("conclusion") == "action_required":
            return f"review run {run.get('id')} is not finished", raises
        if "key" not in entry:
            continue  # a run none of whose attempts left evidence: no reviewer verdict
        if entry.get("state") != "ok":
            judged = entry.get("state")
        else:
            judged = gate._judge_artifact(entry["artifact"], head_sha, base_ref)
        if judged not in ("skipped", "clean", "evidence-blocking"):
            raises.append(
                (
                    "HIGH",
                    f"review evidence {entry['key']} is {judged}: its raise is unknown, fail closed",
                )
            )
            continue
        raised = entry["artifact"].get("raise") if judged != "skipped" else None
        if raised:  # validated by _judge_artifact: {"tier": LOW|MEDIUM|HIGH, "reason": str}
            raises.append((raised["tier"], _clean(raised["reason"])))
        if provenance == "bound" and run.get("conclusion") == "success":
            reviewed = True
    if not reviewed:
        return "no successful review run has left evidence for this commit yet", raises
    return None, raises


def read_review(api, repo, pr, number, head_sha):
    """`(pending, raises, notes)` for this head, read through the API (#2202).

    No raise is read for a PR into another base (code-gate decides none) or on a host
    without the review workflow. Any other failure to read is a raise to HIGH."""
    base = pr.get("base") or {}
    default_branch = (base.get("repo") or {}).get("default_branch")
    if base.get("ref") != default_branch:
        return (
            None,
            [],
            [
                f"base {_clean(str(base.get('ref')))} is not the default branch "
                f"{default_branch}: no reviewer raise to read"
            ],
        )
    workflow = _gate().REVIEW_WORKFLOW
    try:
        api("GET", f"repos/{repo}/actions/workflows/{workflow.rsplit('/', 1)[1]}")
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None, [], [f"no {workflow} on this repo: no reviewer raise to read"]
        return None, [("HIGH", f"review evidence unreadable (HTTP {exc.code}): fail closed")], []
    except Exception as exc:  # unreadable must not read as "no reviewer"
        return (
            None,
            [("HIGH", f"review evidence unreadable ({type(exc).__name__}): fail closed")],
            [],
        )
    try:
        entries = _gate().gather_entries(
            api, repo, int(number), head_sha, default_branch, pr["created_at"]
        )
    except Exception as exc:  # a truncated or failed listing may hide a raise
        return (
            None,
            [("HIGH", f"review evidence unreadable ({type(exc).__name__}): fail closed")],
            [],
        )
    pending, raises = review_raise(entries, int(number), head_sha, base["ref"], default_branch)
    return pending, raises, []


def evaluate(api, repo, number, event_head_sha, host_root, bot, code_root=CODE_ROOT):
    """`(ok, messages)` for one PR. `api` is a `github_client.Client`: `api("GET", path)`
    returns a JSON document from the GitHub API."""
    pr = api("GET", f"repos/{repo}/pulls/{number}")
    head = pr["head"]["sha"]
    if head != event_head_sha:
        return False, [
            f"head moved to {head[:7]} (event was {event_head_sha[:7]}): superseded by a newer push"
        ]
    note = ""
    if is_dependabot(pr):
        declared, problem = DEPENDABOT_TIER, None
        note = f" (fixed: {DEPENDABOT} PR, body not read)"
    else:
        declared, problem = parse_declared(pr.get("body"))
    if problem:
        return False, [
            f"The PR body has a {problem} Risk line. Expected exactly one line `{GRAMMAR}` "
            f"(grammar and examples: {DOC})."
        ]
    truncated = None
    try:
        files = github_client.paged(
            api, f"repos/{repo}/pulls/{number}/files", max_pages=MAX_FILE_PAGES
        )
    except github_client.ListingTruncated as exc:
        files, truncated = exc.items, f"files listing truncated at {MAX_FILE_PAGES} pages"
    computed, reasons = computed_tier(
        files,
        pr.get("changed_files", len(files)),
        repo,
        host_root,
        code_root,
        read_sources=lambda: read_sources(api, repo, pr, files),
    )
    if truncated:  # what went unread could be any path: a hold tier, CRITICAL still reachable
        computed = max(computed, "HIGH", key=SEVERITY.index)
        reasons.append(truncated)
    final = max(declared, computed, key=SEVERITY.index)
    pending, raises, notes = read_review(api, repo, pr, number, head)
    reasons.extend(notes)
    # The reviewer may raise the tier, never lower it (#2202): highest first, so each
    # raise is logged as applied or as at or below the tier it met.
    for tier, why in sorted(raises, key=lambda r: SEVERITY.index(r[0]), reverse=True):
        if SEVERITY.index(tier) > SEVERITY.index(final):
            reasons.append(f"reviewer raise to {tier} applied (was {final}): {why}")
            final = tier
        else:
            reasons.append(f"reviewer raise to {tier} not applied: at or below {final}: {why}")
    summary = f"declared {declared}{note}, computed {computed}, final {final}" + "".join(
        f"\n  - {r}" for r in reasons
    )
    if pending:
        return False, [
            summary,
            f"waiting for the code review of {head[:7]}: {pending}; the tier is re-decided "
            "when it completes, since the reviewer may raise it (#2202)",
        ]
    if final not in HOLD_TIERS:
        return True, [summary]
    author = admin_author(api, repo, pr, bot)
    if author:
        return True, [summary, f"{final} hold skipped: author {author} has admin permission"]
    unread = []
    try:
        releaser = releasing_reviewer(api, repo, number, head, bot)
    except github_client.ListingTruncated:  # an unread review cannot release
        releaser = None
        unread = [f"reviews listing truncated at {MAX_REVIEW_PAGES} pages"]
    if releaser:
        return True, [
            summary,
            f"released by an APPROVED review from admin {releaser} at {head[:7]}",
        ]
    return False, [
        summary,
        *unread,
        f"{final} holds until a holder of the releasing role (admin, not a Bot account, not "
        f"{bot}) leaves an APPROVED review on the current head {head[:7]}; a new push needs a "
        f"new approval. See {DOC} (residual risks).",
    ]


def _make_client(token):
    return github_client.Client(token, user_agent="risk-tier")


def main(make_client=None):
    bot = os.environ.get("LANE_BOT_LOGIN", "")
    if not bot:
        print(
            "::error::risk-tier: LANE_BOT_LOGIN is empty; the calling workflow must pass the "
            "lane's bot login"
        )
        sys.exit(1)
    host_root = os.environ.get("RISK_TIER_HOST_ROOT")
    client = (make_client or _make_client)(os.environ["GITHUB_TOKEN"])
    ok, messages = evaluate(
        client,
        os.environ["GITHUB_REPOSITORY"],
        os.environ["PR_NUMBER"],
        os.environ["HEAD_SHA"],
        Path(host_root) if host_root else None,
        bot,
    )
    for line in messages:
        print(line)
    for reason in messages[0].split("\n  - ")[1:]:
        if reason.startswith(f"{EXEMPTION}:"):  # where the review retro counts it (#2201)
            print(f"::notice title=risk-tier::{reason}")
    if not ok:
        print(f"::error::{messages[-1]}")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()

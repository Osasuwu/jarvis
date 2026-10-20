"""Fail when live branch protection and the documented required-check binding disagree.

Runs from `.github/workflows/branch-protection-drift.yml`. docs/reference/github-repo-setup.md
carries the binding branch protection is meant to have, as a JSON block after the
`<!-- required-checks-binding -->` marker: required check name -> the GitHub App id allowed
to post it. An `app_id` of null in live protection accepts a same-named check run or commit
status from any source, so a documented binding that was never applied (#1998) is a fail-open
merge gate; this probe is what notices.

The branch object (`GET /repos/{owner}/{repo}/branches/{branch}`) carries the protection
settings for any token that can read the repo, so the probe needs no admin credential.

Stdlib only: the job needs no dependency install. The branch is read through the shared
client `github_client.py` beside this script (#2068), loaded by file path at import.
"""

import importlib.util
import json
import os
import re
import sys
from pathlib import Path


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

MARKER = "<!-- required-checks-binding -->"
_BLOCK = re.compile(re.escape(MARKER) + r"\s*```json\s*\n(.*?)\n```", re.DOTALL)
DEFAULT_DOC = "docs/reference/github-repo-setup.md"


class BindingError(Exception):
    """The documented binding could not be read."""


def parse_documented_binding(markdown):
    """Return {check name: app id} from the marked JSON block of the doc."""
    match = _BLOCK.search(markdown)
    if not match:
        raise BindingError(f"no ```json block follows {MARKER}")
    try:
        binding = json.loads(match.group(1))
    except json.JSONDecodeError as exc:
        raise BindingError(f"binding block is not valid JSON: {exc}") from exc
    if not isinstance(binding, dict) or not binding:
        raise BindingError("binding block must be a non-empty JSON object")
    bad = [k for k, v in binding.items() if type(v) is not int]
    if bad:
        raise BindingError(f"app id must be an integer for: {', '.join(bad)}")
    return binding


def live_binding(branch):
    """Return {check name: app id or None} for the required checks of a branch object."""
    required = (branch.get("protection") or {}).get("required_status_checks") or {}
    live = {c["context"]: c.get("app_id") for c in required.get("checks") or []}
    for context in required.get("contexts") or []:
        live.setdefault(context, None)
    return live


def find_drift(documented, branch):
    """List the ways live protection differs from the documented binding."""
    live = live_binding(branch)
    problems = []
    for name, app_id in documented.items():
        if name not in live:
            problems.append(f"{name}: documented app_id {app_id}, not required live")
        elif live[name] != app_id:
            problems.append(f"{name}: documented app_id {app_id}, live {live[name]}")
    for name, app_id in live.items():
        if name not in documented:
            problems.append(f"{name}: required live (app_id {app_id}), not documented")
    return problems


# --- Doc claims (#1894) ------------------------------------------------------------------------
# Prose that calls a backticked name a required check is a claim about live protection. A name
# that is not required live is a gate a reader trusts and the branch does not have. The grammar
# is deliberately narrow (the forms below); a claim in any other phrasing — "the required `X`
# check", "being a required check, `X` …", workflow YAML comments — goes uncaught.

# Files whose prose describes current state. Dated records (docs/decisions, docs/research,
# docs/incidents) describe the past and are not scanned.
SCANNED_FILES = ("AGENTS.md", "README.md", "CONTEXT.md", "SECURITY.md")
SCANNED_DIRS = ("docs/reference", "docs/security", ".github")
SCANNED_ROOTS = SCANNED_FILES + SCANNED_DIRS

# (path, name, follow-up issue): claims known to be stale, tracked by the issue. Reported as a
# warning. An entry that matches no current claim fails tests/ci (unmatched_known_stale), so
# the entry has to leave in the PR that fixes its line.
KNOWN_STALE = (("docs/reference/ci-guard-meta-tests.md", "Detect secrets with gitleaks", 2123),)

_TOKEN = r"\**`(?P<name>[^`\n]+)`\**"
_REQ = r"\**required\**"
# Case-insensitive: "Required checks: …" at a sentence start is the same claim. Names keep
# their case — only the surrounding words are folded.
_FORMS = [
    re.compile(
        _TOKEN + r"\s+(?:is|are)\s+an?\s+" + _REQ + r"\s+checks?\b", re.I
    ),  # `X` is a required check
    re.compile(_TOKEN + r"\s+an?\s+" + _REQ + r"\s+checks?\b", re.I),  # make `X` a required check
    re.compile(_TOKEN + r"\s+" + _REQ + r"\s+checks?\b", re.I),  # the `X` required check
    re.compile(_REQ + r"\s+checks?\s+" + _TOKEN, re.I),  # the required check `X`
    re.compile(r"\badd\s+" + _TOKEN + r"\s+to\s+the\s+" + _REQ + r"\s+status\s+checks\b", re.I),
]
# "required [CI|status] checks" + plain words, then the list opens with ":", "(" or "are".
_ENUM = re.compile(_REQ + r"(?:\s+[\w-]+)?\s+checks\b[^`.:()]{0,60}?(?:[:(]|\bare\b)", re.I)
_ITEM = re.compile(r"\s*" + _TOKEN)
_SEP = re.compile(r"\s*(?:,\s*and\b|,|and\b)")
_NEGATED = re.compile(r"\b(?:not|no longer|never)\s+(?:an?\s+|the\s+)?\**required\b", re.I)
_SENTENCE_END = re.compile(r"[.;!?](?=\s|$)")
_PATHLIKE = re.compile(r"/|\.[A-Za-z0-9]{1,5}$")
_BRANCHES = {"main", "master"}


def _skip_gloss(text, pos):
    """Index past a balanced "(…)" gloss starting after whitespace at pos, or pos itself."""
    i = pos
    while i < len(text) and text[i].isspace():
        i += 1
    if i >= len(text) or text[i] != "(":
        return pos
    depth = 0
    for j in range(i, len(text)):
        if text[j] == "(":
            depth += 1
        elif text[j] == ")":
            depth -= 1
            if depth == 0:
                return j + 1
    return pos


def _enumeration(text, start):
    """(offset, name) of each list-position token from start; stops at the first non-item."""
    items, pos = [], start
    while True:
        m = _ITEM.match(text, pos)
        if not m:
            return items
        items.append((m.start("name"), m.group("name")))
        pos = _skip_gloss(text, m.end())
        sep = _SEP.match(text, pos)
        if not sep:
            return items
        pos = sep.end()


def _sentence(text, offset):
    starts = [m.end() for m in _SENTENCE_END.finditer(text, 0, offset)]
    begin = starts[-1] if starts else 0
    end = _SENTENCE_END.search(text, offset)
    return text[begin : end.start() if end else len(text)]


def claimed_required_checks(path, text):
    """[(path, line, name)] for each backticked name the prose calls a required check."""
    found = {}
    lines = text.split("\n")
    in_fence, block_lines = False, []

    def flush():
        flat, owner = "", []
        for number, line in block_lines:
            owner.extend([number] * (len(line) + 1))
            flat += line + " "
        hits = []
        for form in _FORMS:
            hits += [(m.start("name"), m.group("name")) for m in form.finditer(flat)]
        for m in _ENUM.finditer(flat):
            hits += _enumeration(flat, m.end())
        for offset, name in hits:
            if _PATHLIKE.search(name) or name in _BRANCHES:
                continue
            if _NEGATED.search(_sentence(flat, offset)):
                continue
            found.setdefault((path, owner[offset], name), (owner[offset], offset))

    for number, line in enumerate(lines, 1):
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            flush()
            block_lines = []
            continue
        if in_fence:
            continue
        if not line.strip():
            flush()
            block_lines = []
        else:
            block_lines.append((number, line))
    flush()
    return sorted(found, key=found.get)


class DocScanError(Exception):
    """The doc scan could not see what it is configured to scan."""


def _scanned_files(root):
    """The files to scan under root; raises DocScanError when a root is missing or none exist.

    A scan that sees nothing must not read as "no claims": a narrowed sparse checkout, a wrong
    DOC_ROOT or cwd would otherwise turn the probe green while checking no doc at all.
    """
    root = Path(root)
    missing = [name for name in SCANNED_FILES if not (root / name).is_file()]
    missing += [name for name in SCANNED_DIRS if not (root / name).is_dir()]
    if missing:
        raise DocScanError(f"scan roots missing under {root}: {', '.join(missing)}")
    paths = [root / name for name in SCANNED_FILES]
    for directory in SCANNED_DIRS:
        paths += sorted((root / directory).rglob("*.md"))
    if not paths:
        raise DocScanError(f"no docs to scan under {root}")
    return paths


def scan_docs(root):
    """Every claim in the scanned docs under root, paths relative to root.

    Raises DocScanError when a configured root is missing or no file was scanned.
    """
    root = Path(root)
    claims = []
    for path in _scanned_files(root):
        rel = path.relative_to(root).as_posix()
        claims += claimed_required_checks(rel, path.read_text(encoding="utf-8"))
    return claims


def unmatched_known_stale(claims, known=KNOWN_STALE):
    """The entries of known that match no claim: the stale line was fixed, the entry stayed."""
    present = {(path, name) for path, _, name in claims}
    return [entry for entry in known if (entry[0], entry[1]) not in present]


def run(doc_text, fetch_branch, claims=(), scan_error=None):
    """Compare; print the verdict; return the process exit code.

    scan_error is the DocScanError of a doc scan that could not run: the binding comparison
    still runs and reports, but the verdict is a failure, never "No drift".
    """
    documented = parse_documented_binding(doc_text)
    branch = fetch_branch()
    problems = find_drift(documented, branch)
    live = live_binding(branch)
    tracked = {(path, name): issue for path, name, issue in KNOWN_STALE}
    stale, warnings = [], []
    for path, line, name in claims:
        if name in live:
            continue
        message = f"{path}:{line}: `{name}` is named as a required check, not required live"
        if (path, name) in tracked:
            warnings.append(f"{message} (tracked #{tracked[(path, name)]})")
        else:
            stale.append(message)
    for warning in warnings:
        print(f"warning: {warning}")
    if problems:
        print("Branch protection drifts from the binding documented in " + DEFAULT_DOC + ":")
        for problem in problems:
            print(f"  - {problem}")
        print(
            "Apply the documented binding (PATCH .../protection/required_status_checks) or fix the doc."
        )
    if stale:
        print("Docs name required checks that live protection does not require:")
        for message in stale:
            print(f"  - {message}")
    if scan_error:
        print(f"Doc scan failed: {scan_error}")
    if problems or stale or scan_error:
        return 1
    print(f"No drift: {len(documented)} required checks match the documented binding.")
    return 0


def _make_client(token):
    return github_client.Client(token, user_agent="branch-protection-drift")


def main(make_client=None):
    repo = os.environ["GITHUB_REPOSITORY"]
    branch = os.environ["DEFAULT_BRANCH"]
    client = (make_client or _make_client)(os.environ["GH_TOKEN"])
    try:
        claims, scan_error = scan_docs(os.environ.get("DOC_ROOT", ".")), None
    except DocScanError as error:
        claims, scan_error = [], error
    with open(os.environ.get("BINDING_DOC", DEFAULT_DOC), encoding="utf-8") as doc:
        return run(
            doc.read(),
            lambda: client("GET", f"repos/{repo}/branches/{branch}"),
            claims,
            scan_error,
        )


if __name__ == "__main__":
    sys.exit(main())

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
# is deliberately narrow (the forms below). Goes uncaught: a claim in any other phrasing ("being
# a required check, `X` …"), workflow YAML comments, and by design (#2123) fenced code, closed
# HTML comments and indented code blocks (see _prose_blocks). Claims in HOST_SCOPED_FILES are
# printed as info and never fail the job.

# Files whose prose describes current state. Dated records (docs/decisions, docs/research,
# docs/incidents) describe the past and are not scanned.
SCANNED_FILES = ("AGENTS.md", "README.md", "CONTEXT.md", "SECURITY.md")
SCANNED_DIRS = ("docs/reference", "docs/security", ".github")
SCANNED_ROOTS = SCANNED_FILES + SCANNED_DIRS

# (path, line, name, follow-up issue): claims known to be stale, tracked by the issue. Reported
# as a warning. Keyed on the line, so a new claim of the same name elsewhere in the same file is
# not covered by an old entry (#2123). An entry that matches no current claim fails tests/ci
# (unmatched_known_stale), so the entry has to leave in the PR that fixes or moves its line.
KNOWN_STALE = ()

# Scanned files whose claims describe what a host repo of the AFK lane should require, not what
# jarvis requires (#2123). Their claims are listed as info and never compared to jarvis's live set
# or the documented binding.
HOST_SCOPED_FILES = ("docs/reference/lane-host-setup.md",)

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
    re.compile(_REQ + r"\s+" + _TOKEN + r"\s+checks?\b", re.I),  # the required `X` check (#2123)
    re.compile(r"\badd\s+" + _TOKEN + r"\s+to\s+the\s+" + _REQ + r"\s+status\s+checks\b", re.I),
]
# "required [CI|status] checks" + plain words, then the list opens with ":", "(" or "are".
_ENUM = re.compile(_REQ + r"(?:\s+[\w-]+)?\s+checks\b[^`.:()]{0,60}?(?:[:(]|\bare\b)", re.I)
_ITEM = re.compile(r"\s*" + _TOKEN)
_SEP = re.compile(r"\s*(?:,\s*and\b|,|and\b)")
_NEGATED = re.compile(r"\b(?:not|no longer|never)\s+(?:an?\s+|the\s+)?\**required\b", re.I)
_SENTENCE_END = re.compile(r"[.;!?](?=\s|$)")
_JOINER = re.compile(r",\s*but\b|\b(?:while|whereas|although|though|yet)\b|[—–]", re.I)
# A file or directory path, not a check: a known file extension, a trailing "/", or a leading
# "." (a dot-directory such as .github/…). `code-review/verdict`, `ci / pytest` and
# `pytest-3.12` are check names and stay claims (#2123).
_PATHLIKE = re.compile(r"\.(?:ya?ml|py|md|json|toml|sh|txt|js|ts|cfg|ini)$|/$|^\.", re.I)
_BRANCHES = {"main", "master"}
_FENCE = re.compile(r"\s*(`{3,}|~{3,})")
_INDENTED = re.compile(r" {0,3}\t| {4}")
_LIST_ITEM = re.compile(r"\s*(?:[-*+]|\d+[.)])(?:\s|$)")
_COMMENT_OPEN, _COMMENT_CLOSE = "<!--", "-->"


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


def _clause(text, offset):
    """The part of the sentence at offset between contrastive joiners (", but", "while", em
    dash …), so a negation of one name does not drop a claim on another (#2123)."""
    sentence_start = ([m.end() for m in _SENTENCE_END.finditer(text, 0, offset)] or [0])[-1]
    end = _SENTENCE_END.search(text, offset)
    sentence_end = end.start() if end else len(text)
    begin = sentence_start
    for m in _JOINER.finditer(text, sentence_start, sentence_end):
        if m.end() <= offset:
            begin = m.end()
        else:
            return text[begin : m.start()]
    return text[begin:sentence_end]


def _strip_comments(line, in_comment, last_close):
    """(line with HTML comment text blanked to spaces, still inside a comment at its end).

    Blanking keeps every offset and line number. Inline code spans are skipped, so a
    backticked `<!--` opens no comment. last_close is the offset of the text's last `-->`,
    relative to this line: a `<!--` with no `-->` after it is text and hides nothing (#2123).
    """
    chars, i = list(line), 0
    while i < len(line):
        if in_comment:
            end = line.find(_COMMENT_CLOSE, i)
            stop = len(line) if end < 0 else end + len(_COMMENT_CLOSE)
            chars[i:stop] = " " * (stop - i)
            i, in_comment = stop, end < 0
        elif line[i] == "`":
            j = i
            while j < len(line) and line[j] == "`":
                j += 1
            close = re.compile(r"(?<!`)" + "`" * (j - i) + r"(?!`)").search(line, j)
            i = close.end() if close else j
        elif line.startswith(_COMMENT_OPEN, i) and i + len(_COMMENT_OPEN) <= last_close:
            chars[i : i + len(_COMMENT_OPEN)] = " " * len(_COMMENT_OPEN)
            i, in_comment = i + len(_COMMENT_OPEN), True
        else:
            i += 1
    return "".join(chars), in_comment


def _prose_blocks(text):
    """[[(line number, line)]]: the prose of a Markdown text in blank-line separated blocks.

    Left out (#2123): fenced code (``` or ~~~, closed only by a fence of the same character
    at least as long), closed HTML comments, and indented code — a block whose every line is
    indented 4 spaces or a tab and holds no comment, unless it continues a list or an indented
    paragraph. Indentation is read on the raw line, not the comment-blanked one.
    """
    blocks, block, fence, in_comment = [], [], None, False
    before = None  # kind of the last prose block: None, list, indented, text
    indented, commented = set(), set()  # line numbers: raw line indented; held a comment
    last_close, line_start = text.rfind(_COMMENT_CLOSE), 0

    def close_block():
        nonlocal block, before
        if block:
            code = all(n in indented and n not in commented for n, _ in block)
            code = code and before in (None, "text")
            if not code:  # after a code block `before` stands, so its next block is code too
                blocks.append(block)
                if any(_LIST_ITEM.match(line) for _, line in block):
                    before = "list"  # a wrapped item's tail is no list marker (#2123 review)
                else:
                    before = "indented" if block[-1][0] in indented else "text"
        block = []

    for number, raw in enumerate(text.split("\n"), 1):
        start, line_start = line_start, line_start + len(raw) + 1
        if fence:
            m = _FENCE.match(raw)
            if m and m.group(1)[0] == fence[0] and len(m.group(1)) >= fence[1]:
                if not raw[m.end() :].strip():
                    fence = None
            continue
        if not in_comment:
            m = _FENCE.match(raw)
            if m:
                close_block()
                fence = (m.group(1)[0], len(m.group(1)))
                before = "indented" if raw[:1].isspace() else None
                continue
        line, in_comment = _strip_comments(raw, in_comment, last_close - start)
        if line.strip():
            if _INDENTED.match(raw):
                indented.add(number)
            if line != raw:
                commented.add(number)
            block.append((number, line))
        else:
            close_block()
    close_block()
    return blocks


def claimed_required_checks(path, text):
    """[(path, line, name)] for each backticked name the prose calls a required check."""
    found = {}

    def flush(block_lines):
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
            if _NEGATED.search(_clause(flat, offset)):
                continue
            found.setdefault((path, owner[offset], name), (owner[offset], offset))

    for block in _prose_blocks(text):
        flush(block)
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
    present = set(claims)
    return [entry for entry in known if tuple(entry[:3]) not in present]


def run(doc_text, fetch_branch, claims=(), scan_error=None, known=KNOWN_STALE):
    """Compare; print the verdict; return the process exit code.

    scan_error is the DocScanError of a doc scan that could not run: the binding comparison
    still runs and reports, but the verdict is a failure, never "No drift". known is the
    tracked-stale list (KNOWN_STALE by default).
    """
    documented = parse_documented_binding(doc_text)
    branch = fetch_branch()
    problems = find_drift(documented, branch)
    live = live_binding(branch)
    tracked = {(path, line, name): issue for path, line, name, issue in known}
    stale, warnings = [], []
    for path, line, name in claims:
        if path in HOST_SCOPED_FILES:
            print(
                f"info: {path}:{line}: `{name}` host-scoped, not checked against jarvis's live set"
            )
            continue
        if name in live:
            continue
        message = f"{path}:{line}: `{name}` is named as a required check, not required live"
        if (path, line, name) in tracked:
            warnings.append(f"{message} (tracked #{tracked[(path, line, name)]})")
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

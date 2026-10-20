"""Seeded-defect harness for the code-gate review (#2131).

Opens one draft PR per fixture in ``tests/fixtures/seeded_defects/<class>/`` and later
reads the Code Review evidence for each, so the question "does code-gate flag a defect
of jarvis-oss class X?" has a re-runnable answer. The fixtures are whole new files
(``files/<target>.seed``), never patches, so edits on main do not stale them.

    python scripts/seeded_defects.py open --tag 20261020 [--dry-run]
    python scripts/seeded_defects.py collect --tag 20261020

``open`` builds each PR's commit with git plumbing on a temporary index (no checkout,
no worktree, the caller's tree and branch are untouched), pushes it to
``seeded-defect/<class>-<tag>`` and opens a **draft** PR labelled
``waiting-human-review``. A draft gets no review: ``review_skip_reason`` in
``.github/scripts/code_gate_verdict.py`` returns ``draft`` for it, so ``collect``
reports ``no-verdict`` until a person marks the PR ready. The harness never does that,
never merges, closes, re-runs or dispatches anything: every command it runs passes
``check_command``, an allowlist, first.

``collect`` classifies from the review evidence artifact only, never from the
``code-gate`` check colour, which is also red for a draft or a pending review. Evidence
must pass code-gate's own ``validate_findings`` and be for the head SHA against main;
then ``flagged`` = blocking with a finding whose class is one the fixture planted *and*
whose file is a fixture target, ``flagged-other`` = blocking on anything else (not a
detection), ``missed`` = reviewed, not blocking. Every run needs a new ``--tag``: a
class whose branch already exists is skipped, with or without an open PR.
"""

from __future__ import annotations

import argparse
import functools
import importlib.util
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import NamedTuple

REPO = "Osasuwu/jarvis"
BASE = "main"
ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIR = ROOT / "tests" / "fixtures" / "seeded_defects"
SEED_SUFFIX = ".seed"
TITLE_PREFIX = "[seeded-defect] "
BRANCH_PREFIX = "seeded-defect/"
HOLD_LABEL = "waiting-human-review"
EXPERIMENT_ISSUE = "2131"  # the reviewer reads a linked issue for intent; the body never names it
REVIEW_WORKFLOW = "code-review.yml"
EVIDENCE_FILE = "review-evidence.json"
EVIDENCE_ARTIFACT = re.compile(r"^review-evidence-([1-9][0-9]*)$")
_TAG = re.compile(r"^[0-9A-Za-z][0-9A-Za-z._-]{0,31}$")
_SHA = re.compile(r"^[0-9a-f]{40}$")
_META_KEYS = frozenset({"class", "summary", "body", "targets", "expected_finding_classes"})


class FixtureError(ValueError):
    """A fixture directory that cannot produce the PR it describes."""


class UnsafeCommand(ValueError):
    """A command outside the harness's allowlist."""


class Fixture(NamedTuple):
    cls: str
    summary: str
    body: str
    files: dict  # target path in the repo -> the .seed file holding its content
    expected_finding_classes: tuple


class Classification(NamedTuple):
    kind: str  # flagged | flagged-other | missed | no-verdict
    reason: str
    findings: tuple  # ((finding class, file), ...)
    gate: str | None  # the code-gate check conclusion, recorded, never decisive


# --- fixtures -----------------------------------------------------------------


def _seed_files(directory):
    files_dir = directory / "files"
    out = {}
    for path in sorted(files_dir.rglob("*")):
        if path.is_file():
            if not path.name.endswith(SEED_SUFFIX):
                raise FixtureError(f"{path}: fixture files end in {SEED_SUFFIX}")
            rel = path.relative_to(files_dir).as_posix()
            out[rel[: -len(SEED_SUFFIX)]] = path
    return out


def load_fixtures(root=FIXTURE_DIR):
    """Every fixture under ``root``, sorted by class; any invalid one raises."""
    fixtures = []
    for directory in sorted(p for p in Path(root).iterdir() if p.is_dir()):
        meta_path = directory / "meta.json"
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise FixtureError(f"{meta_path}: {exc}") from exc
        missing = _META_KEYS - set(meta)
        if missing:
            raise FixtureError(f"{meta_path}: missing {sorted(missing)}")
        if meta["class"] != directory.name:
            raise FixtureError(f"{meta_path}: class {meta['class']!r} != {directory.name!r}")
        files = _seed_files(directory)
        if sorted(meta["targets"]) != sorted(files):
            raise FixtureError(
                f"{meta_path}: targets {sorted(meta['targets'])} != files {sorted(files)}"
            )
        if EXPERIMENT_ISSUE in meta["body"] or EXPERIMENT_ISSUE in meta["summary"]:
            raise FixtureError(f"{meta_path}: the PR must not name #{EXPERIMENT_ISSUE}")
        fixtures.append(
            Fixture(
                cls=meta["class"],
                summary=meta["summary"],
                body=meta["body"],
                files=files,
                expected_finding_classes=tuple(meta["expected_finding_classes"]),
            )
        )
    return fixtures


def render_title(fx):
    return TITLE_PREFIX + fx.summary


def render_body(fx):
    """The fixture's body plus a ``[no-issue]`` line, which require-linked-issue accepts."""
    return f"{fx.body}\n\n[no-issue]\n"


def branch_name(cls, tag):
    if not _TAG.match(tag):
        raise ValueError(f"tag {tag!r} must match {_TAG.pattern}")
    return f"{BRANCH_PREFIX}{cls}-{tag}"


# --- evidence -------------------------------------------------------------------


def _no_verdict(reason, gate):
    return Classification("no-verdict", reason, (), gate)


@functools.cache
def _code_gate():
    """code-gate's own module, loaded by path: the evidence rules are read, not copied."""
    path = Path(__file__).resolve().parents[1] / ".github" / "scripts" / "code_gate_verdict.py"
    spec = importlib.util.spec_from_file_location("_seeded_code_gate_verdict", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def classify(evidence, head_sha, gate, fx):
    """Classify one PR from its review evidence against fixture ``fx``.

    ``gate`` is only recorded. A blocking verdict counts as ``flagged`` only when a
    finding has a class the fixture planted and names one of its target files.
    """
    if evidence is None:
        return _no_verdict("no review evidence", gate)
    if not isinstance(evidence, dict) or evidence.get("schema") != 1:
        return _no_verdict("evidence unreadable: schema", gate)
    if evidence.get("sha") != head_sha:
        return _no_verdict(
            f"evidence is for {str(evidence.get('sha'))[:7]}, head is {head_sha[:7]}", gate
        )
    if evidence.get("status") == "skipped":
        return _no_verdict(f"review skipped: {evidence.get('reason')}", gate)
    if evidence.get("status") != "reviewed":
        return _no_verdict(f"evidence unreadable: status {evidence.get('status')!r}", gate)
    if evidence.get("base_ref") != BASE:
        return _no_verdict(
            f"evidence is against base {evidence.get('base_ref')!r}, not {BASE}", gate
        )
    errors = _code_gate().validate_findings(evidence)
    if errors:
        return _no_verdict("evidence invalid: " + "; ".join(errors), gate)
    pairs = tuple((f["class"], f["file"]) for f in evidence["findings"])
    if not evidence["blocking"]:
        return Classification("missed", "reviewed, not blocking", pairs, gate)
    if any(c in fx.expected_finding_classes and f in fx.files for c, f in pairs):
        return Classification(
            "flagged", "reviewed, blocking on a planted class in a target file", pairs, gate
        )
    return Classification(
        "flagged-other",
        "reviewed, blocking, but no finding names a planted class in a target file",
        pairs,
        gate,
    )


# A run that ended like this produced no review: the `edited` trigger's skipped job, a
# cancelled or never-started run. A failed run stays a candidate: blocking can fail it.
_NO_REVIEW_CONCLUSIONS = frozenset(
    {"skipped", "cancelled", "timed_out", "startup_failure", "stale", "neutral"}
)


def matching_runs(runs, pr_number, head_sha):
    """Code Review runs whose title names this PR at this head, newest first."""
    title = f"Code review PR #{pr_number} @ {head_sha}"
    matching = [
        r for r in runs if r.get("display_title") == title and r.get("head_sha") == head_sha
    ]
    return sorted(matching, key=lambda r: r.get("created_at") or "", reverse=True)


def candidate_runs(runs, pr_number, head_sha):
    """The matching runs that completed and may hold a review, newest first."""
    return [
        r
        for r in matching_runs(runs, pr_number, head_sha)
        if r.get("status") == "completed" and r.get("conclusion") not in _NO_REVIEW_CONCLUSIONS
    ]


def select_artifact(artifacts):
    """The live ``review-evidence-<attempt>`` artifact with the highest attempt."""
    best, best_attempt = None, 0
    for art in artifacts:
        m = EVIDENCE_ARTIFACT.match(art.get("name") or "")
        if m and not art.get("expired") and int(m.group(1)) > best_attempt:
            best, best_attempt = art, int(m.group(1))
    return best


def read_evidence_zip(blob):
    try:
        with zipfile.ZipFile(io.BytesIO(blob)) as zf:
            return json.loads(zf.read(EVIDENCE_FILE).decode("utf-8"))
    except (zipfile.BadZipFile, KeyError, UnicodeDecodeError, json.JSONDecodeError):
        return None


ROW_HEADER = (
    "| Class | PR | Head | Result | Findings | Evidence | code-gate |\n"
    "|---|---|---|---|---|---|---|"
)


def render_row(fx, number, sha, result, run_url):
    kind = result.kind if result.kind != "no-verdict" else f"no-verdict ({result.reason})"
    findings = "; ".join(f"{c} `{f}`" for c, f in result.findings) or "none"
    evidence = f"[run]({run_url})" if run_url else "none"
    pr = f"[#{number}](https://github.com/{REPO}/pull/{number})"
    return (
        f"| {fx.cls} | {pr} | `{sha[:7]}` | {kind} | {findings} | {evidence} "
        f"| {result.gate or 'none'} |"
    )


# --- commands -------------------------------------------------------------------

_GIT_LOCAL = frozenset({"rev-parse", "hash-object", "commit-tree", "ls-tree"})
# These read or write the index, so they run only on a temporary one (GIT_INDEX_FILE):
# on the default index they would rewrite the caller's staging area.
_GIT_INDEX = frozenset({"read-tree", "update-index", "write-tree"})
_BRANCH = re.compile(rf"^{re.escape(BRANCH_PREFIX)}[a-z0-9-]+-{_TAG.pattern[1:-1]}$")
_SHA_ = r"[0-9a-f]{40}"
# Every path the harness reads with `gh api`; each is a GET, since no field flag is allowed.
_API_PATH = re.compile(
    rf"^repos/{re.escape(REPO)}/("
    rf"actions/workflows/{re.escape(REVIEW_WORKFLOW)}/runs\?head_sha={_SHA_}&per_page=100"
    rf"|actions/runs/[0-9]+/artifacts"
    rf"|actions/artifacts/[0-9]+/zip"
    rf"|commits/{_SHA_}/check-runs\?check_name=code-gate"
    rf")$"
)


def _is_branch(value):
    return bool(_BRANCH.match(value))


def check_command(cmd, env=None):
    """Raise ``UnsafeCommand`` unless ``cmd`` is exactly one of the shapes the harness builds.

    Each shape is matched token for token, so an extra, repeated or attached flag
    (``-B dev``, ``-XPOST``, ``--method=PUT``) never passes: local git plumbing (the
    index-touching part only with a temporary ``GIT_INDEX_FILE`` in ``env``), ``git fetch
    origin main``, ``git ls-remote`` of one seeded-defect ref, a push of one commit to a
    ``refs/heads/seeded-defect/*`` ref, the harness's ``gh pr list`` and draft ``gh pr
    create``, and ``gh api <path>`` (a GET) for the four paths ``collect`` reads.
    """
    cmd = list(cmd)
    if cmd == fetch_cmd():
        return
    if cmd[:1] == ["git"] and len(cmd) > 1 and cmd[1] in _GIT_LOCAL:
        return
    if cmd[:1] == ["git"] and len(cmd) > 1 and cmd[1] in _GIT_INDEX:
        if env and env.get("GIT_INDEX_FILE"):
            return
        raise UnsafeCommand(f"index plumbing needs a temporary GIT_INDEX_FILE: {cmd}")
    if cmd[:4] == ["git", "ls-remote", "--heads", "origin"] and len(cmd) == 5:
        if cmd[4].startswith("refs/heads/") and _is_branch(cmd[4][len("refs/heads/") :]):
            return
    if cmd[:3] == ["git", "push", "origin"] and len(cmd) == 4:
        src, _, dst = cmd[3].partition(":")
        if _SHA.match(src) and dst.startswith("refs/heads/") and _is_branch(dst[11:]):
            return
    if len(cmd) > 6 and _is_branch(cmd[6]) and cmd == pr_list_cmd(cmd[6]):
        return
    if (
        len(cmd) == 16
        and cmd[:9] == ["gh", "pr", "create", "--repo", REPO, "--draft", "--base", BASE, "--head"]
        and _is_branch(cmd[9])
        and cmd[10] == "--title"
        and cmd[11].startswith(TITLE_PREFIX)
        and cmd[12] == "--body-file"
        and cmd[14:] == ["--label", HOLD_LABEL]
    ):
        return
    if len(cmd) == 3 and cmd[:2] == ["gh", "api"] and _API_PATH.match(cmd[2]):
        return
    raise UnsafeCommand(f"not in the harness allowlist: {cmd}")


def run(cmd, *, env=None, capture=True, binary=False):
    """Run an allowlisted command; stdout is returned, a non-zero exit raises."""
    check_command(cmd, env)
    proc = subprocess.run(
        cmd, cwd=ROOT, env=env, check=True, capture_output=capture, text=not binary
    )
    return proc.stdout


def fetch_cmd():
    return ["git", "fetch", "origin", BASE]


def ls_remote_cmd(branch):
    return ["git", "ls-remote", "--heads", "origin", f"refs/heads/{branch}"]


def push_cmd(commit, branch):
    return ["git", "push", "origin", f"{commit}:refs/heads/{branch}"]


def pr_list_cmd(branch):
    return ["gh", "pr", "list", "--repo", REPO, "--head", branch, "--state", "open",
            "--json", "number,url,headRefOid,isDraft"]  # fmt: skip


def pr_create_cmd(fx, branch, body_file):
    return ["gh", "pr", "create", "--repo", REPO, "--draft", "--base", BASE, "--head", branch,
            "--title", render_title(fx), "--body-file", str(body_file), "--label", HOLD_LABEL]  # fmt: skip


def api_get_cmd(path):
    return ["gh", "api", path]


def runs_path(sha):
    return f"repos/{REPO}/actions/workflows/{REVIEW_WORKFLOW}/runs?head_sha={sha}&per_page=100"


def checks_path(sha):
    return f"repos/{REPO}/commits/{sha}/check-runs?check_name=code-gate"


# --- subcommands ----------------------------------------------------------------


def _open_pr(branch):
    prs = json.loads(run(pr_list_cmd(branch)) or "[]")
    return prs[0] if prs else None


def build_commit(fx, base):
    """A commit on ``base`` adding the fixture's files, built on a temporary index."""
    with tempfile.TemporaryDirectory() as tmp:
        env = {**os.environ, "GIT_INDEX_FILE": str(Path(tmp) / "index")}
        run(["git", "read-tree", base], env=env)
        for target, seed in fx.files.items():
            if run(["git", "ls-tree", base, "--", target]).strip():
                raise FixtureError(f"{fx.cls}: {target} already exists on {BASE}")
            blob = run(["git", "hash-object", "-w", "--path", target, str(seed)]).strip()
            run(["git", "update-index", "--add", "--cacheinfo", f"100644,{blob},{target}"], env=env)
        tree = run(["git", "write-tree"], env=env).strip()
    message = f"feat(scripts): {fx.summary}"
    return run(["git", "commit-tree", tree, "-p", base, "-m", message]).strip()


def cmd_open(args):
    fixtures = load_fixtures()
    if not args.dry_run:
        run(fetch_cmd())
    for fx in fixtures:
        branch = branch_name(fx.cls, args.tag)
        if args.dry_run:
            print(f"{fx.cls}: would open a draft from {branch}: {render_title(fx)}")
            print("  " + " ".join(pr_create_cmd(fx, branch, "<body file>")))
            continue
        existing = _open_pr(branch)
        if existing:
            print(f"{fx.cls}: open PR #{existing['number']} already has head {branch}; skipped")
            continue
        if run(ls_remote_cmd(branch)).strip():
            # A push whose PR create failed: re-pushing would fail non-fast-forward.
            print(f"{fx.cls}: {branch} exists on origin with no open PR; use a new --tag")
            continue
        base = run(["git", "rev-parse", f"origin/{BASE}"]).strip()
        commit = build_commit(fx, base)
        run(push_cmd(commit, branch))
        with tempfile.TemporaryDirectory() as tmp:
            body = Path(tmp) / "body.md"
            body.write_text(render_body(fx), encoding="utf-8")
            url = run(pr_create_cmd(fx, branch, body)).strip()
        print(f"{fx.cls}: {url}")
    return 0


def collect_one(number, sha, fx):
    """``(Classification, run url)`` for one seeded PR at head ``sha``.

    A review still running is ``review pending``. Otherwise the evidence comes from the
    newest completed run that holds a live evidence artifact, so a later run that ended
    without a review (the ``edited`` trigger's skipped job, a cancel) does not hide it.
    """
    runs = json.loads(run(api_get_cmd(runs_path(sha)))).get("workflow_runs", [])
    gate = _gate_conclusion(sha)
    matching = matching_runs(runs, number, sha)
    if any(r.get("status") != "completed" for r in matching):
        return _no_verdict("review pending", gate), None
    for review in candidate_runs(runs, number, sha):
        arts = json.loads(run(api_get_cmd(f"repos/{REPO}/actions/runs/{review['id']}/artifacts")))
        art = select_artifact(arts.get("artifacts", []))
        if art is not None:
            blob = run(api_get_cmd(f"repos/{REPO}/actions/artifacts/{art['id']}/zip"), binary=True)
            return classify(read_evidence_zip(blob), sha, gate, fx), review.get("html_url")
    return classify(None, sha, gate, fx), (matching[0].get("html_url") if matching else None)


def _gate_conclusion(sha):
    checks = json.loads(run(api_get_cmd(checks_path(sha))))
    runs = checks.get("check_runs", [])
    if not runs:
        return None
    latest = max(runs, key=lambda c: c.get("started_at") or "")
    return latest.get("conclusion") or latest.get("status")


def cmd_collect(args):
    print(ROW_HEADER)
    for fx in load_fixtures():
        branch = branch_name(fx.cls, args.tag)
        pr = _open_pr(branch)
        if pr is None:
            print(f"| {fx.cls} | none (no open PR from `{branch}`) | | | | | |")
            continue
        sha = pr["headRefOid"]
        result, run_url = collect_one(pr["number"], sha, fx)
        print(render_row(fx, pr["number"], sha, result, run_url))
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    p_open = sub.add_parser("open", help="open one draft PR per fixture")
    p_open.add_argument("--tag", required=True)
    p_open.add_argument("--dry-run", action="store_true")
    p_open.set_defaults(func=cmd_open)
    p_collect = sub.add_parser("collect", help="classify each seeded PR's review evidence")
    p_collect.add_argument("--tag", required=True)
    p_collect.set_defaults(func=cmd_collect)
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())

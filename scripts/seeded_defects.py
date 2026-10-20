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

``collect`` classifies from the review evidence artifact only (``flagged`` = a reviewed,
blocking verdict on the head SHA; ``missed`` = reviewed, not blocking), never from the
``code-gate`` check colour, which is also red for a draft or a pending review.
"""

from __future__ import annotations

import argparse
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
    kind: str  # flagged | missed | no-verdict
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


def classify(evidence, head_sha, gate):
    """Classify one PR from its review evidence. ``gate`` is only recorded."""
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
    blocking, findings = evidence.get("blocking"), evidence.get("findings")
    if not isinstance(blocking, bool) or not isinstance(findings, list):
        return _no_verdict("evidence unreadable: blocking/findings", gate)
    pairs = tuple(
        (str(f.get("class")), str(f.get("file"))) for f in findings if isinstance(f, dict)
    )
    if blocking:
        return Classification("flagged", "reviewed, blocking", pairs, gate)
    return Classification("missed", "reviewed, not blocking", pairs, gate)


def select_run(runs, pr_number, head_sha):
    """The latest Code Review run whose title names this PR at this head."""
    title = f"Code review PR #{pr_number} @ {head_sha}"
    matching = [
        r for r in runs if r.get("display_title") == title and r.get("head_sha") == head_sha
    ]
    return max(matching, key=lambda r: r.get("created_at") or "", default=None)


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

_GIT_LOCAL = frozenset({"rev-parse", "read-tree", "hash-object", "update-index", "write-tree",
                        "commit-tree", "ls-tree"})  # fmt: skip
_GH_API_WRITE_FLAGS = frozenset({"-X", "--method", "-f", "-F", "--field", "--raw-field", "--input"})


def _value(cmd, flag):
    return cmd[cmd.index(flag) + 1] if flag in cmd[:-1] else None


def check_command(cmd):
    """Raise ``UnsafeCommand`` unless ``cmd`` is one of the shapes the harness needs.

    An allowlist: local git plumbing, ``git fetch origin main``, a push of one commit
    to a new ``refs/heads/seeded-defect/*`` ref, ``gh pr list``, a draft ``gh pr
    create`` into main from a seeded-defect branch, and read-only ``gh api``.
    """
    cmd = list(cmd)
    head = cmd[:2]
    if head == ["git", "fetch"] and cmd[2:] == ["origin", BASE]:
        return
    if head[:1] == ["git"] and len(cmd) > 1 and cmd[1] in _GIT_LOCAL:
        return
    if head == ["git", "push"] and len(cmd) == 4 and cmd[2] == "origin":
        src, _, dst = cmd[3].partition(":")
        if _SHA.match(src) and dst.startswith("refs/heads/" + BRANCH_PREFIX):
            return
    if cmd[:3] == ["gh", "pr", "list"]:
        return
    if cmd[:3] == ["gh", "pr", "create"]:
        if (
            "--draft" in cmd
            and _value(cmd, "--base") == BASE
            and (_value(cmd, "--head") or "").startswith(BRANCH_PREFIX)
        ):
            return
    if head == ["gh", "api"] and not _GH_API_WRITE_FLAGS & set(cmd):
        return
    raise UnsafeCommand(f"not in the harness allowlist: {cmd}")


def run(cmd, *, env=None, capture=True, binary=False):
    """Run an allowlisted command; stdout is returned, a non-zero exit raises."""
    check_command(cmd)
    proc = subprocess.run(
        cmd, cwd=ROOT, env=env, check=True, capture_output=capture, text=not binary
    )
    return proc.stdout


def fetch_cmd():
    return ["git", "fetch", "origin", BASE]


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
        base = run(["git", "rev-parse", f"origin/{BASE}"]).strip()
        commit = build_commit(fx, base)
        run(push_cmd(commit, branch))
        with tempfile.TemporaryDirectory() as tmp:
            body = Path(tmp) / "body.md"
            body.write_text(render_body(fx), encoding="utf-8")
            url = run(pr_create_cmd(fx, branch, body)).strip()
        print(f"{fx.cls}: {url}")
    return 0


def _evidence_for(number, sha):
    runs = json.loads(
        run(
            api_get_cmd(
                f"repos/{REPO}/actions/workflows/{REVIEW_WORKFLOW}/runs?head_sha={sha}&per_page=100"
            )
        )
    ).get("workflow_runs", [])
    review = select_run(runs, number, sha)
    if review is None or review.get("status") != "completed":
        return None, review
    arts = json.loads(run(api_get_cmd(f"repos/{REPO}/actions/runs/{review['id']}/artifacts")))
    art = select_artifact(arts.get("artifacts", []))
    if art is None:
        return None, review
    blob = run(api_get_cmd(f"repos/{REPO}/actions/artifacts/{art['id']}/zip"), binary=True)
    return read_evidence_zip(blob), review


def _gate_conclusion(sha):
    checks = json.loads(
        run(api_get_cmd(f"repos/{REPO}/commits/{sha}/check-runs?check_name=code-gate"))
    )
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
        evidence, review = _evidence_for(pr["number"], sha)
        result = classify(evidence, sha, _gate_conclusion(sha))
        print(render_row(fx, pr["number"], sha, result, (review or {}).get("html_url")))
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

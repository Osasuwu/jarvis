"""Executor — the live-write shell for repo-baseline (#1346, milestone #48 slice 5).

Where :mod:`applier` is a pure translator (action plan -> ordered ``GhCall``
list, no network), this module is the thin ``gh``/REST shell that actually
performs those calls: Contents-API writes on a fixed sync branch, a lifecycle
check against any existing sync PR, and a reportability-gated branch-protection
update. Mirrors the Auditor/gh_runner split: parsing/decision logic is unit
-testable against injected runners, only :func:`gh_write_runner` and
:func:`main` touch a live process.

Per-run pipeline (one repo): audit -> plan -> translate -> diff (live GET,
read-only) -> write (branch + Contents-API calls + PR) -> protection guard.
Two-field summary status model per repo (AC8) — see :class:`RepoOutcome`.
"""

from __future__ import annotations

import argparse
import base64
import json
from dataclasses import dataclass
from typing import Any, Callable, Optional, Protocol

import subprocess

import yaml

from .applier import (
    Applier,
    ApplyError,
    GhCall,
    GhCallKind,
    actual_state_from_snapshot,
    load_canon,
    load_manifest,
)
from .auditor import (
    OSASUWU_REPOS,
    REDROBOT_REPOS,
    Auditor,
    GhNotFound,
    GhRunner,
    RepoSnapshot,
    gh_runner,
)
from .manifest import Manifest
from .planner import Planner
from .renderer import RenderError

__all__ = [
    "SYNC_BRANCH",
    "ACCOUNT_REPOS",
    "IdentityError",
    "GhWriteRunner",
    "WriteOp",
    "RepoOutcome",
    "gh_write_runner",
    "resolve_repos",
    "preflight_identity",
    "find_sync_pr",
    "diff_phase",
    "evaluate_protection_guard",
    "render_pr_body",
    "execute_repo",
    "execute_account_pass",
    "main",
]

SYNC_BRANCH = "repo-baseline/sync"

# The two account passes (PRD story 7). Keyed by CLI-facing lowercase name;
# the login each pass's `gh` identity must present before any write — see
# `preflight_identity`. This is the safety gate that currently blocks a
# redrobot `--execute` run under the Osasuwu token (push, not admin — see
# auditor.REDROBOT_REPOS's own comment on the credential split).
ACCOUNT_REPOS: dict[str, list[str]] = {
    "osasuwu": OSASUWU_REPOS,
    "redrobot": REDROBOT_REPOS,
}
ACCOUNT_LOGIN: dict[str, str] = {
    "osasuwu": "Osasuwu",
    "redrobot": "SergazyNarynov",
}

# ceiling: hand-maintained check-context -> canon-workflow-path map. Covers
# only the contexts canon's own workflows currently produce (their job-level
# `name:`/id, which is what GitHub actually uses as the check-run context —
# NOT the workflow's top-level `name:`). A new canon workflow's context must
# be added here manually; an unmapped context always falls through to
# "unreportable" (safe default — never silently claims a check exists).
_CONTEXT_WORKFLOW_MAP: dict[str, str] = {
    "review": ".github/workflows/code-review.yml",
    "owner-queue-guard": ".github/workflows/owner-queue-guard.yml",
    "require-linked-issue": ".github/workflows/pr-body-check.yml",
    "meta-tests": ".github/workflows/ci-meta.yml",
    "pytest": ".github/workflows/pytest.yml",
}


class IdentityError(RuntimeError):
    """Raised when the authenticated ``gh`` identity does not match the
    account a pass is scoped to — refuses to write under the wrong credential."""


class GhWriteRunner(Protocol):
    """A write runner performs a mutating ``gh api`` call: method + path +
    optional JSON body, returns parsed JSON. Symmetric to
    :class:`~scripts.repo_baseline.auditor.GhRunner`, which is read-only."""

    def __call__(self, method: str, path: str, *, body: Optional[dict] = None) -> Any: ...


@dataclass(frozen=True)
class WriteOp:
    """A :class:`GhCall` paired with the live blob ``sha`` captured during the
    diff phase (``None`` for a brand-new file). Kept executor-local rather than
    added to the frozen, already-tested ``GhCall`` — the planning half has no
    use for a live blob sha."""

    call: GhCall
    blob_sha: Optional[str] = None


@dataclass
class RepoOutcome:
    """Two-field per-repo summary (AC8).

    ``file_status`` in {"applied", "pending", "declined", "failed", "skipped",
    "gapped", "errored"}; ``protection_status`` in {"applied",
    "deferred: <reason>", "failed", "skipped"}.
    """

    repo: str
    file_status: str
    protection_status: str
    pr_url: Optional[str] = None
    error: Optional[str] = None


def gh_write_runner(method: str, path: str, *, body: Optional[dict] = None) -> Any:
    """Live write runner — shells out to ``gh api -X <method>``.

    Mirrors :func:`~scripts.repo_baseline.auditor.gh_runner`'s conventions
    exactly (explicit UTF-8 decoding, 60s timeout, ``GhNotFound`` on 404,
    stderr-only ``RuntimeError`` on other failures — see that function's
    docstring for the incident history behind those choices), extended with a
    JSON body piped over ``--input -`` for the mutating call.
    """
    args = ["gh", "api", path, "-X", method]
    stdin_input = None
    if body is not None:
        args += ["--input", "-"]
        stdin_input = json.dumps(body)
    try:
        proc = subprocess.run(
            args,
            input=stdin_input,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=60,
        )
    except subprocess.TimeoutExpired as e:
        raise RuntimeError(f"gh api {method} {path!r} timed out after 60s") from e
    if proc.returncode != 0:
        stderr = (proc.stderr or "").strip()
        if "HTTP 404" in stderr or "Not Found" in stderr:
            raise GhNotFound(path)
        raise RuntimeError(f"gh api {method} {path!r} failed (exit {proc.returncode}): {stderr}")
    if not proc.stdout.strip():
        return {}
    return json.loads(proc.stdout)


def resolve_repos(account: str, repo: Optional[str] = None) -> list[str]:
    """Resolve the repo list for an account pass, optionally narrowed to one repo."""
    try:
        repos = ACCOUNT_REPOS[account]
    except KeyError:
        raise ValueError(f"unknown account {account!r}; choose one of {sorted(ACCOUNT_REPOS)}")
    if repo is None:
        return list(repos)
    if repo not in repos:
        raise ValueError(f"{repo!r} is not in the {account!r} account's repo list: {repos}")
    return [repo]


def preflight_identity(runner: GhRunner, *, account: str) -> None:
    """Abort before any mutating call if the authenticated identity doesn't
    match the account this pass is scoped to (AC1)."""
    me = runner("user")
    login = me.get("login")
    expected = ACCOUNT_LOGIN.get(account)
    if login != expected:
        raise IdentityError(
            f"gh identity {login!r} does not match {account!r} pass owner "
            f"{expected!r} — refusing to write"
        )


def find_sync_pr(runner: GhRunner, repo: str, *, branch: str = SYNC_BRANCH) -> Optional[dict]:
    """Find the sync PR from ``branch`` on *repo*, if any (open or closed)."""
    owner = repo.split("/", 1)[0]
    prs = runner(f"repos/{repo}/pulls?head={owner}:{branch}&state=all")
    for pr in prs:
        if pr.get("head", {}).get("ref") == branch:
            return pr
    return None


def sync_pr_status(pr: Optional[dict]) -> str:
    """Classify a sync PR lookup result (AC4): "pending" (open), "declined"
    (closed, unmerged), or "none" (no PR, or a merged one — a merge typically
    deletes the branch, so a fresh cycle is the right next state)."""
    if pr is None:
        return "none"
    if pr.get("state") == "open":
        return "pending"
    if pr.get("state") == "closed" and pr.get("merged_at") is None:
        return "declined"
    return "none"


def split_calls(calls: list[GhCall]) -> tuple[list[GhCall], Optional[GhCall]]:
    """Split a translated call sequence into file calls and the (at most one)
    SET_CHECK_CONTEXTS call — files and protection are executed independently."""
    file_calls = [c for c in calls if c.kind in (GhCallKind.PUT_FILE, GhCallKind.DELETE_FILE)]
    context_calls = [c for c in calls if c.kind == GhCallKind.SET_CHECK_CONTEXTS]
    return file_calls, (context_calls[0] if context_calls else None)


def diff_phase(
    runner: GhRunner, repo: str, default_branch: str, calls: list[GhCall]
) -> tuple[list[WriteOp], list[GhCall]]:
    """Read-only pre-write check: GET each planned file on the default branch,
    capture its blob ``sha``, compare live content against the desired one.

    The Applier's own idempotency check runs against snapshot-derived
    ``ActualState`` (workflow paths only, content unknown — see
    ``actual_state_from_snapshot``'s docstring), so it over-emits PUT_FILE
    calls whenever body content isn't tracked. This is the live, authoritative
    check right before a write actually happens. Returns
    ``(write_ops, skipped)`` — ``skipped`` covers both an already-identical
    file and a DELETE whose target is already absent.
    """
    write_ops: list[WriteOp] = []
    skipped: list[GhCall] = []
    for call in calls:
        try:
            data = runner(f"repos/{repo}/contents/{call.path}?ref={default_branch}")
            sha = data.get("sha")
            if data.get("encoding") == "base64":
                live_content: Optional[str] = base64.b64decode(data.get("content", "")).decode(
                    "utf-8"
                )
            else:
                live_content = data.get("content")
        except GhNotFound:
            sha = None
            live_content = None

        if call.kind == GhCallKind.DELETE_FILE:
            if sha is None:
                skipped.append(call)
                continue
            write_ops.append(WriteOp(call=call, blob_sha=sha))
            continue

        # PUT_FILE
        if sha is not None and live_content == call.content:
            skipped.append(call)
            continue
        write_ops.append(WriteOp(call=call, blob_sha=sha))
    return write_ops, skipped


def _get_ref_sha(runner: GhRunner, repo: str, branch: str) -> str:
    data = runner(f"repos/{repo}/git/refs/heads/{branch}")
    return data["object"]["sha"]


def ensure_sync_branch(
    runner: GhRunner, write_runner: GhWriteRunner, repo: str, default_branch: str
) -> None:
    """Reset (orphan branch, no open PR) or create the fixed sync branch from
    the current default-branch HEAD. Only called from the write phase, and
    only when at least one real write remains (AC3)."""
    base_sha = _get_ref_sha(runner, repo, default_branch)
    try:
        runner(f"repos/{repo}/git/refs/heads/{SYNC_BRANCH}")
        exists = True
    except GhNotFound:
        exists = False
    if exists:
        write_runner(
            "PATCH",
            f"repos/{repo}/git/refs/heads/{SYNC_BRANCH}",
            body={"sha": base_sha, "force": True},
        )
    else:
        write_runner(
            "POST",
            f"repos/{repo}/git/refs",
            body={"ref": f"refs/heads/{SYNC_BRANCH}", "sha": base_sha},
        )


def _execute_write_op(write_runner: GhWriteRunner, repo: str, op: WriteOp) -> None:
    call = op.call
    if call.kind == GhCallKind.PUT_FILE:
        body: dict[str, Any] = {
            "message": f"repo-baseline: sync {call.path}",
            "content": base64.b64encode((call.content or "").encode("utf-8")).decode("ascii"),
            "branch": SYNC_BRANCH,
        }
        if op.blob_sha is not None:
            body["sha"] = op.blob_sha
        write_runner("PUT", f"repos/{repo}/contents/{call.path}", body=body)
    elif call.kind == GhCallKind.DELETE_FILE:
        write_runner(
            "DELETE",
            f"repos/{repo}/contents/{call.path}",
            body={
                "message": f"repo-baseline: remove {call.path}",
                "sha": op.blob_sha,
                "branch": SYNC_BRANCH,
            },
        )
    else:  # pragma: no cover — defensive; split_calls never routes this kind here
        raise ValueError(f"_execute_write_op: unsupported call kind {call.kind!r}")


def render_pr_body(manifest: Manifest, calls: list[GhCall]) -> str:
    """Pure render of the sync PR body from the translated call sequence (AC9)."""
    file_calls = [c for c in calls if c.kind in (GhCallKind.PUT_FILE, GhCallKind.DELETE_FILE)]
    context_calls = [c for c in calls if c.kind == GhCallKind.SET_CHECK_CONTEXTS]

    lines = [
        "Automated repo-baseline sync — brings this repo's canon files and "
        "settings in line with the declarative manifest. See milestone #48 "
        "for the PRD.",
        "",
        "[no-issue]",
        "",
        f"**Profile:** `{manifest.profile}`",
        "",
        "## Files",
    ]
    for c in sorted(file_calls, key=lambda c: c.path):
        verb = "update" if c.kind == GhCallKind.PUT_FILE else "delete"
        lines.append(f"- `{c.path}` — {verb} ({c.file_class or 'repo_custom'})")

    if context_calls:
        lines += ["", "## Required check contexts", f"- {', '.join(context_calls[0].contexts)}"]

    if any(c.path == ".github/workflows/code-review.yml" for c in file_calls):
        lines += [
            "",
            "**Self-modifying gate warning:** this PR changes `code-review.yml` "
            "itself — the review-blind carve-out applies (per DOCTRINE.md). "
            "Do not auto-merge; use an admin merge after manual review.",
        ]
    return "\n".join(lines)


def evaluate_protection_guard(
    context_names: list[str],
    snapshot: RepoSnapshot,
    *,
    file_exists: Callable[[str], bool],
) -> tuple[bool, Optional[str]]:
    """A required-check context is reportable (safe to write into branch
    protection) iff it is EITHER already observed live on the default branch's
    protection, OR maps to a canon workflow that is confirmed present on the
    default branch (AC5). Any other context defers — never claim a check
    exists on a guess."""
    live_contexts = (
        set(snapshot.branch_protection.contexts) if snapshot.branch_protection else set()
    )
    for ctx in context_names:
        if ctx in live_contexts:
            continue
        path = _CONTEXT_WORKFLOW_MAP.get(ctx)
        if path is None or not file_exists(path):
            return False, (
                f"context {ctx!r} not yet observed on live protection and its "
                "workflow is not present on the default branch"
            )
    return True, None


def _file_exists_on_branch(runner: GhRunner, repo: str, branch: str, path: str) -> bool:
    try:
        runner(f"repos/{repo}/contents/{path}?ref={branch}")
        return True
    except GhNotFound:
        return False


def apply_protection(
    runner: GhRunner,
    write_runner: GhWriteRunner,
    repo: str,
    default_branch: str,
    context_names: list[str],
    snapshot: RepoSnapshot,
) -> str:
    """Apply the protection-guard verdict (AC6): PATCH the check-contexts slice
    when protection already exists (live ``strict`` preserved), else PUT the
    full doctrine-pinned payload on a bare branch."""
    reportable, reason = evaluate_protection_guard(
        context_names,
        snapshot,
        file_exists=lambda path: _file_exists_on_branch(runner, repo, default_branch, path),
    )
    if not reportable:
        return f"deferred: {reason}"

    if snapshot.branch_protection is not None:
        write_runner(
            "PATCH",
            f"repos/{repo}/branches/{default_branch}/protection/required_status_checks",
            body={"strict": snapshot.branch_protection.strict, "contexts": list(context_names)},
        )
    else:
        write_runner(
            "PUT",
            f"repos/{repo}/branches/{default_branch}/protection",
            body={
                "required_status_checks": {"strict": False, "contexts": list(context_names)},
                "enforce_admins": False,
                "required_pull_request_reviews": None,
                "restrictions": None,
            },
        )
    return "applied"


def execute_repo(
    repo: str,
    manifest: Manifest,
    *,
    runner: GhRunner,
    write_runner: GhWriteRunner,
    execute: bool,
    canon: Optional[dict[str, str]] = None,
) -> RepoOutcome:
    """Run the full live pipeline for one repo (AC2): audit -> plan ->
    translate -> sync-PR lifecycle check -> diff -> write -> protection guard.

    Planning-phase failures (audit/manifest/render/translate) are left to
    propagate — the caller (:func:`execute_account_pass`) is the isolation
    boundary (AC2's "errored" status). Write-phase failures are caught here
    and reported as ``failed: <call> -> <error>`` without aborting the
    protection phase evaluation for this same repo (AC7).
    """
    canon = canon if canon is not None else load_canon()
    snapshot = Auditor(runner).audit(repo)
    actual = actual_state_from_snapshot(snapshot)
    plan = Planner(manifest).plan(actual)
    applier = Applier(manifest, canon)
    gaps = applier.missing_canon(plan)
    if gaps:
        return RepoOutcome(repo=repo, file_status="gapped", protection_status="skipped")
    calls = applier.translate(plan, actual)

    file_calls, context_call = split_calls(calls)
    default_branch = snapshot.settings.default_branch

    def _protection_outcome() -> str:
        if context_call is None or not execute:
            return "skipped"
        try:
            return apply_protection(
                runner, write_runner, repo, default_branch, context_call.contexts, snapshot
            )
        except (GhNotFound, RuntimeError) as e:
            return f"failed: {e}"

    pr = find_sync_pr(runner, repo)
    status = sync_pr_status(pr)
    if status == "declined":
        return RepoOutcome(
            repo=repo,
            file_status="declined",
            protection_status="skipped",
            pr_url=pr.get("html_url"),
        )
    if status == "pending":
        return RepoOutcome(
            repo=repo,
            file_status="pending",
            protection_status=_protection_outcome(),
            pr_url=pr.get("html_url"),
        )

    if not file_calls:
        return RepoOutcome(
            repo=repo, file_status="skipped", protection_status=_protection_outcome()
        )

    write_ops, _skipped = diff_phase(runner, repo, default_branch, file_calls)
    if not write_ops:
        return RepoOutcome(
            repo=repo, file_status="skipped", protection_status=_protection_outcome()
        )

    if not execute:
        return RepoOutcome(repo=repo, file_status="pending", protection_status="skipped")

    try:
        ensure_sync_branch(runner, write_runner, repo, default_branch)
        for op in write_ops:
            _execute_write_op(write_runner, repo, op)
        pr_body = render_pr_body(manifest, calls)
        pr_resp = write_runner(
            "POST",
            f"repos/{repo}/pulls",
            body={
                "title": f"repo-baseline: sync {repo}",
                "head": SYNC_BRANCH,
                "base": default_branch,
                "body": pr_body,
            },
        )
    except (GhNotFound, RuntimeError) as e:
        failed_call = write_ops[0].call if write_ops else None
        return RepoOutcome(
            repo=repo,
            file_status=f"failed: {failed_call.kind.value if failed_call else '?'} "
            f"{failed_call.path if failed_call else '?'} -> {e}",
            protection_status="skipped",
        )

    return RepoOutcome(
        repo=repo,
        file_status="applied",
        protection_status=_protection_outcome(),
        pr_url=pr_resp.get("html_url"),
    )


_ISOLATION_EXCEPTIONS = (
    ApplyError,
    RenderError,
    OSError,
    ValueError,
    json.JSONDecodeError,
    RuntimeError,
    yaml.YAMLError,
)
"""Broader than the Applier's own tuple (mirrors it plus the two failure modes
that only exist on the live path): RuntimeError from Auditor.audit, and
yaml.YAMLError from a malformed on-disk manifest."""


def execute_account_pass(
    account: str,
    *,
    runner: GhRunner,
    write_runner: GhWriteRunner,
    repo: Optional[str] = None,
    execute: bool = False,
    canon: Optional[dict[str, str]] = None,
) -> list[RepoOutcome]:
    """Executor-level per-repo isolation (AC2): any exception in a repo's
    audit/plan/translate cycle is caught here and reported as ``errored`` —
    the pass continues to the next repo. Runs the identity preflight (AC1)
    once, before the first repo, only when ``execute`` is set."""
    repos = resolve_repos(account, repo)
    if execute:
        preflight_identity(runner, account=account)
    canon = canon if canon is not None else load_canon()

    outcomes: list[RepoOutcome] = []
    for r in repos:
        try:
            manifest = load_manifest(r)
            outcome = execute_repo(
                r, manifest, runner=runner, write_runner=write_runner, execute=execute, canon=canon
            )
        except _ISOLATION_EXCEPTIONS as e:
            outcome = RepoOutcome(
                repo=r,
                file_status="errored",
                protection_status="skipped",
                error=f"{type(e).__name__}: {e}",
            )
        outcomes.append(outcome)
    return outcomes


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Live sync-PR executor for repo-baseline.")
    parser.add_argument("--account", choices=sorted(ACCOUNT_REPOS), help="Account pass to run.")
    parser.add_argument("--repo", help="Restrict the pass to one repo (must belong to --account).")
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Perform live writes. Default is dry-run: plan and report, no PRs opened.",
    )
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    args = _build_arg_parser().parse_args(argv)
    if not args.account:
        raise SystemExit("--account is required")
    if args.execute and not args.account:
        raise SystemExit(
            "--execute requires --account"
        )  # pragma: no cover — unreachable, kept explicit per AC1

    outcomes = execute_account_pass(
        args.account,
        runner=gh_runner,
        write_runner=gh_write_runner,
        repo=args.repo,
        execute=args.execute,
    )
    for o in outcomes:
        pr = f" {o.pr_url}" if o.pr_url else ""
        err = f" ({o.error})" if o.error else ""
        print(f"{o.repo}: files={o.file_status} protection={o.protection_status}{pr}{err}")
    return 1 if any(o.file_status.startswith(("failed", "errored")) for o in outcomes) else 0


if __name__ == "__main__":
    raise SystemExit(main())

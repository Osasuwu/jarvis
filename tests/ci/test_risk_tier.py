"""The `risk-tier` required check (.github/scripts/risk_tier.py, #2004).

The PR body's `Risk:` line is a merge hold: the check goes red on a bad line, floors the tier by
the diff, and holds a non-admin author's HIGH/CRITICAL until a holder of the releasing role
(admin, not a Bot account, not the lane's bot) approves the current head (#2088). These tests run the real script against a fake GitHub API and the real workflow
file; expected values are literals.
"""

import base64
import importlib.util
import io
import json
import re
import shutil
import zipfile
from pathlib import Path

import pytest
import yaml

from ._github_fake import FakeApi, http_error, load_client

_root = next(p for p in Path(__file__).resolve().parents if (p / ".github" / "scripts").is_dir())


def _load(name):
    spec = importlib.util.spec_from_file_location(
        name, _root / ".github" / "scripts" / f"{name}.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


risk_tier = _load("risk_tier")
lane_publish = _load("lane_publish")
gate = _load("code_gate_verdict")

REPO = "Osasuwu/jarvis"
HEAD = "a" * 40
OLD = "b" * 40
BASE_TIP = "c" * 40
MERGE_BASE = "d" * 40
GRAMMAR_LINE = "Risk: LOW|MEDIUM|HIGH|CRITICAL — <reason>"
BASE_LIST = {
    REPO: {
        "hitl": ["AGENTS.md"],
        "guarded": ["supabase/**"],
        "machinery": [".github/**", "docs/security/**"],
    }
}
GOOD_BODY = "Refs #1\n\nRisk: LOW — small"

# The code review of PR #7 at HEAD (#2202): one `pull_request` run of code-review.yml whose
# attempt 1 uploaded its evidence. By default the review is clean and raises nothing.
REVIEW_RUN = 900
REVIEW_WORKFLOW = f"repos/{REPO}/actions/workflows/code-review.yml"


def _review_run(**over):
    run = {
        "id": REVIEW_RUN,
        "name": "Code Review",
        "path": ".github/workflows/code-review.yml",
        "event": "pull_request",
        "status": "completed",
        "conclusion": "success",
        "run_attempt": 1,
        "head_sha": HEAD,
        "display_title": f"Code review PR #7 @ {HEAD}",
        "pull_requests": [
            {"number": 7, "base": {"ref": "main", "sha": OLD}, "head": {"ref": "x", "sha": HEAD}}
        ],
    }
    run.update(over)
    return run


def _evidence_zip(findings=None, sha=HEAD, **over):
    """The evidence artifact as code-review.yml uploads it, built by the producer's own
    `build_evidence`."""
    evidence = gate.build_evidence(
        findings or {"blocking": False, "findings": []}, sha, "main", "0" * 40
    )
    evidence.update(over)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("review-evidence.json", json.dumps(evidence))
    return buf.getvalue()


def _raising(tier, reason="rewrites the token refresh"):
    findings = {"blocking": False, "findings": [], "raise": {"tier": tier, "reason": reason}}
    assert gate.validate_findings(findings) == []  # what the review's `validate` step accepts
    return {901: _evidence_zip(findings)}


@pytest.fixture
def base(tmp_path):
    """A base-branch checkout: a literal protected list and the real plan_review.yaml."""
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "protected-paths.json").write_text(json.dumps(BASE_LIST), "utf-8")
    shutil.copy(_root / "config" / "plan_review.yaml", tmp_path / "config" / "plan_review.yaml")
    return tmp_path


class FakeGitHub(FakeApi):
    """The shared fake, routed as PR #7 of REPO: the PR, its files and reviews paged by
    `per_page`/`page`, and the collaborators' permissions (an unknown login is a 404).
    Any other GET fails the test instead of answering."""

    def __init__(
        self,
        body=GOOD_BODY,
        files=(),
        reviews=(),
        permissions=None,
        head=HEAD,
        changed_files=None,
        author=("carol", "User"),
        base_ref="main",
        review_runs=None,
        artifacts=None,
        evidence=None,
        review_workflow=True,
        contents=None,
        merge_base=MERGE_BASE,
    ):
        self.pr = {
            "number": 7,
            "body": body,
            "user": {"login": author[0], "type": author[1]},
            "head": {"sha": head},
            "base": {"ref": base_ref, "sha": BASE_TIP, "repo": {"default_branch": "main"}},
            "created_at": "2026-11-01T00:00:00Z",
            "changed_files": len(files) if changed_files is None else changed_files,
        }
        self.files = list(files)
        self.reviews = list(reviews)
        self.permissions = permissions or {}
        # The code review (#2202): runs of code-review.yml, each run's artifacts, their blobs.
        self.review_runs = [_review_run()] if review_runs is None else review_runs
        self.artifacts = (
            {REVIEW_RUN: [{"id": 901, "name": "review-evidence-1", "expired": False}]}
            if artifacts is None
            else artifacts
        )
        self.review_workflow = review_workflow
        self.contents = contents or {}
        self.merge_base = merge_base
        prefix = f"repos/{REPO}/pulls/7"
        super().__init__(
            {
                prefix: self._pr,
                f"{prefix}/files?": self._page(self.files),
                f"{prefix}/reviews?": self._page(self.reviews),
                f"repos/{REPO}/collaborators/": self._permission,
                REVIEW_WORKFLOW: self._workflow,
                f"{REVIEW_WORKFLOW}/runs?": self._runs,
                f"repos/{REPO}/actions/runs/": self._run_detail,
                f"repos/{REPO}/compare/": self._compare,
                f"repos/{REPO}/contents/": self._content,
            },
            blobs={901: _evidence_zip()} if evidence is None else evidence,
        )

    def _workflow(self, method, path, body):
        if path != REVIEW_WORKFLOW:
            return AssertionError(f"unexpected API call: {path}")
        if self.review_workflow is not True:
            return self.review_workflow
        return {"id": 1, "path": ".github/workflows/code-review.yml"}

    def _runs(self, method, path, body):
        query = path.partition("?")[2].split("&")
        if "page=1" not in query:
            return {"workflow_runs": []}
        event = "workflow_dispatch" if "event=workflow_dispatch" in query else "pull_request"
        runs = self.review_runs
        if isinstance(runs, BaseException):
            return runs
        return {"workflow_runs": [r for r in runs if r["event"] == event]}

    def _run_detail(self, method, path, body):
        m = re.fullmatch(rf"repos/{REPO}/actions/runs/(\d+)/artifacts\?.*page=(\d+)", path)
        if m:
            return {"artifacts": self.artifacts.get(int(m.group(1)), []) if m[2] == "1" else []}
        if re.fullmatch(rf"repos/{REPO}/actions/runs/\d+/attempts/\d+", path):
            return {"conclusion": "success"}
        return AssertionError(f"unexpected API call: {path}")

    def _compare(self, method, path, body):
        if path.partition("?")[0] != f"repos/{REPO}/compare/{BASE_TIP}...{self.pr['head']['sha']}":
            return AssertionError(f"unexpected API call: {path}")
        if isinstance(self.merge_base, BaseException):
            return self.merge_base
        return {"merge_base_commit": {"sha": self.merge_base}}

    def _content(self, method, path, body):
        """`contents[(path, ref)]`: bytes become a base64 file entry, anything else is the
        answer as given; an unknown path or ref is a 404."""
        m = re.fullmatch(rf"repos/{REPO}/contents/(.+)\?ref=(\w+)", path)
        entry = self.contents.get((m.group(1), m.group(2))) if m else None
        if entry is None:
            return http_error(404, url=f"https://api.github.com/{path}")
        if isinstance(entry, bytes):
            return {
                "type": "file",
                "encoding": "base64",
                "content": base64.b64encode(entry).decode(),
            }
        return entry

    def _pr(self, method, path, body):
        if path != f"repos/{REPO}/pulls/7":
            return AssertionError(f"unexpected API call: {path}")
        return self.pr

    @staticmethod
    def _page(items):
        def answer(method, path, body):
            params = dict(q.split("=") for q in path.partition("?")[2].split("&"))
            per_page, page = int(params["per_page"]), int(params["page"])
            return items[(page - 1) * per_page : page * per_page]

        return answer

    def _permission(self, method, path, body):
        m = re.fullmatch(rf"repos/{REPO}/collaborators/([^/]+)/permission", path)
        if not m:
            return AssertionError(f"unexpected API call: {path}")
        if m.group(1) not in self.permissions:
            return http_error(404, url=f"https://api.github.com/{path}")
        permission = self.permissions[m.group(1)]
        if isinstance(permission, BaseException):
            return permission
        return {"permission": permission}


def _file(name, patch="@@ -0,0 +1 @@\n+x", status="modified", additions=1, deletions=0, **extra):
    f = {"filename": name, "status": status, "additions": additions, "deletions": deletions}
    if patch is not None:
        f["patch"] = patch
    return {**f, **extra}


def _review(login, state, commit=HEAD, user_type="User"):
    return {"user": {"login": login, "type": user_type}, "state": state, "commit_id": commit}


def _run(base, api, head=HEAD):
    return risk_tier.evaluate(api, REPO, 7, head, base, "osasuwu-bot")


def _computed(base, files, changed_files=None):
    return risk_tier.computed_tier(
        files, len(files) if changed_files is None else changed_files, REPO, base
    )


# --- AC1: the Risk line grammar ----------------------------------------------------------

_ROW = re.compile(r"^\| `(?P<example>[^`]+)` \| (?P<verdict>\w+) \|$")


def _doc_rows():
    text = (_root / ".github" / "scripts" / "risk_tier.md").read_text(encoding="utf-8")
    rows = [m for m in map(_ROW.match, text.splitlines()) if m]
    return [(m["example"].replace("<br>", "\n"), m["verdict"]) for m in rows]


def test_every_documented_grammar_row_is_parsed_as_documented():
    rows = _doc_rows()
    assert len(rows) >= 20  # the table was found, not an empty walk
    wrong = []
    for example, verdict in rows:
        tier, problem = risk_tier.parse_declared(example)
        got = tier if tier else problem
        if got != (verdict if verdict in risk_tier.SEVERITY else verdict):
            wrong.append(f"{example!r}: documented {verdict}, parsed {got}")
    assert wrong == []


def test_documented_tier_rows_parse_to_the_same_tier_in_the_lenient_lane_parser():
    one_liners = [(ex, v) for ex, v in _doc_rows() if v in risk_tier.SEVERITY and "\n" not in ex]
    assert len(one_liners) >= 7
    wrong = [ex for ex, v in one_liners if lane_publish.parse_risk(ex) != v]
    assert wrong == []


def test_the_unfilled_pr_template_line_is_malformed_not_missing():
    template = (_root / ".github" / "PULL_REQUEST_TEMPLATE.md").read_text(encoding="utf-8")
    assert risk_tier.parse_declared(template) == (None, "malformed")


def test_a_valid_low_line_on_a_clean_diff_is_green(base):
    api = FakeGitHub(files=[_file("scripts/x.py")])
    ok, messages = _run(base, api)
    assert (ok, messages) == (True, ["declared LOW, computed LOW, final LOW"])


def test_a_valid_medium_line_on_a_clean_diff_is_green_without_any_review(base):
    api = FakeGitHub(body="Risk: MEDIUM — new helper", files=[_file("scripts/x.py")])
    ok, messages = _run(base, api)
    assert (ok, messages) == (True, ["declared MEDIUM, computed LOW, final MEDIUM"])


@pytest.mark.parametrize(
    ("body", "problem"),
    [
        ("Refs #1", "missing"),
        ("Risk: LOW", "malformed"),
        ("Risk: LOW — a\nRisk: HIGH — b", "duplicate"),
    ],
)
def test_a_bad_risk_line_is_red_and_names_the_expected_grammar(base, body, problem):
    ok, messages = _run(base, FakeGitHub(body=body, files=[_file("scripts/x.py")]))
    assert (ok, messages) == (
        False,
        [
            f"The PR body has a {problem} Risk line. Expected exactly one line "
            f"`{GRAMMAR_LINE}` (grammar and examples: .github/scripts/risk_tier.md)."
        ],
    )


# --- AC2: the computed tier floors the declared one --------------------------------------


@pytest.mark.parametrize(
    "path",
    ["AGENTS.md", ".github/workflows/x.yml", "supabase/x.sql"],
    ids=["hitl", "machinery", "guarded"],
)
def test_a_path_in_any_bucket_of_the_base_list_reads_high_whatever_the_declared_line(base, path):
    ok, messages = _run(base, FakeGitHub(body="Risk: LOW — x", files=[_file(path)]))
    assert ok is False
    assert messages[0].startswith(
        f"declared LOW, computed HIGH, final HIGH\n  - protected path(s): {path}"
    )


@pytest.mark.parametrize(
    "path",
    [
        ".gitleaksignore",
        "SECURITY.md",
        ".github/workflows/x.yml",
        "config/plan_review.yaml",
        "pyproject.toml",
        "agents/plan_lock.py",
        "config/repos.conf",
    ],
)
def test_the_real_protected_list_floors_the_gate_machinery_at_high(path):
    tier, reasons = risk_tier.path_tier([path], REPO, _root)
    assert (tier, reasons) == ("HIGH", [f"protected path(s): {path}"])


def test_repos_conf_is_a_shared_surface_to_the_classifier_and_to_afk_fit():
    """#2067 AC3: the plan classifier and /to-tickets Q1 read the same `guarded` bucket, so
    `config/repos.conf` is class 2 to both — it used to be class 2 to the classifier only."""
    from scripts.to_tickets_afk_fit import classify_static_paths, load_protected_paths

    assert risk_tier.classifier_tier([_file("config/repos.conf")], _root) == (
        "MEDIUM",
        ["classifier ordinal 2"],
    )
    protected = load_protected_paths(_root / "config" / "protected-paths.json")
    assert classify_static_paths(["config/repos.conf"], REPO, protected).cls == 2


def test_risk_tier_imports_no_private_name_from_the_afk_fit_script():
    """#2067 AC2: risk_tier reads the protected list through `agents.path_policy`, not a
    `_`-prefixed helper reached into from another script."""
    import ast

    tree = ast.parse((_root / ".github" / "scripts" / "risk_tier.py").read_text("utf-8"))
    private = [
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module == "scripts.to_tickets_afk_fit"
        for alias in node.names
        if alias.name.startswith("_")
    ]
    assert private == []


def test_a_rename_out_of_a_protected_path_reads_high(base):
    files = [_file("scripts/moved.py", status="renamed", previous_filename="AGENTS.md")]
    tier, reasons = _computed(base, files)
    assert (tier, reasons[0]) == ("HIGH", "protected path(s): AGENTS.md")


def test_a_corrupt_protected_list_reads_high(base):
    (base / "config" / "protected-paths.json").write_text("{", "utf-8")
    tier, reasons = _computed(base, [_file("scripts/x.py")])
    assert tier == "HIGH"
    assert len(reasons) == 1
    assert reasons[0].startswith("protected-path list unreadable at base (")


@pytest.mark.parametrize(
    ("entry", "reason"),
    [
        ({}, "has no globs at the base commit"),
        ({"hitl": [], "guarded": [], "machinery": []}, "has no globs at the base commit"),
        ({"machinery": ".github/**"}, "has a bucket that is not a list of globs"),
        ({"machinery": [[".github/**"]]}, "has a bucket that is not a list of globs"),
    ],
)
def test_an_empty_or_malformed_host_entry_reads_high_not_low(base, entry, reason):
    (base / "config" / "protected-paths.json").write_text(json.dumps({REPO: entry}), "utf-8")
    tier, reasons = _computed(base, [_file("scripts/x.py")])
    assert tier == "HIGH"
    assert len(reasons) == 1
    assert reason in reasons[0]


# A host that has not adopted the lane has no protected list: every diff is HIGH and the check
# output says why and where the fix is (D2, D7; docs/reference/lane-host-setup.md).
def test_a_host_without_a_protected_list_reads_high_with_the_reason(base):
    (base / "config" / "protected-paths.json").unlink()
    assert _computed(base, [_file("scripts/x.py")]) == (
        "HIGH",
        [
            "config/protected-paths.json not found at the base commit: every diff is HIGH "
            "until the host adds it (D2, docs/reference/lane-host-setup.md)"
        ],
    )


def test_a_host_list_without_an_entry_for_the_repo_reads_high_naming_the_repo(base):
    (base / "config" / "protected-paths.json").write_text(
        json.dumps({"Other/repo": {"hitl": []}}), "utf-8"
    )
    assert _computed(base, [_file("scripts/x.py")]) == (
        "HIGH",
        [
            "config/protected-paths.json has no entry for Osasuwu/jarvis at the base commit: "
            "every diff is HIGH until the host adds it (D2, docs/reference/lane-host-setup.md)"
        ],
    )


def test_an_unset_host_root_reads_high_with_its_own_reason():
    assert risk_tier.path_tier(["scripts/x.py"], REPO, None) == (
        "HIGH",
        [
            "RISK_TIER_HOST_ROOT is not set: no host checkout to read config/protected-paths.json from"
        ],
    )


def test_a_path_only_the_hosts_own_list_names_reads_high(tmp_path):
    host = tmp_path / "host"
    (host / "config").mkdir(parents=True)
    (host / "config" / "protected-paths.json").write_text(
        json.dumps({REPO: {"guarded": ["host_only/**"]}}), "utf-8"
    )
    assert risk_tier.path_tier(["host_only/a.py"], REPO, host) == (
        "HIGH",
        ["protected path(s): host_only/a.py"],
    )
    assert risk_tier.path_tier(["AGENTS.md"], REPO, host) == ("LOW", [])


def test_the_classifier_config_comes_from_the_code_not_the_host(base):
    (base / "config" / "plan_review.yaml").unlink()  # a host carries none; the code checkout does
    assert _computed(base, [_file("scripts/a.py"), _file("agents/b.py")]) == (
        "MEDIUM",
        ["classifier ordinal 2"],
    )


def test_a_files_listing_shorter_than_changed_files_reads_high(base):
    tier, reasons = _computed(base, [_file("scripts/x.py")], changed_files=3000)
    assert (tier, reasons) == ("HIGH", ["only 1 of 3000 changed files listable: fail closed"])


def test_a_files_listing_is_read_past_the_first_page(base):
    files = [_file(f"scripts/f{i}.py") for i in range(150)]
    listed = load_client().paged(
        FakeGitHub(files=files), f"repos/{REPO}/pulls/7/files", max_pages=risk_tier.MAX_FILE_PAGES
    )
    assert _computed(base, listed, changed_files=150) == ("LOW", [])


def test_a_files_listing_past_its_page_cap_holds_at_high_naming_the_cut(base):
    """#2068: 30 full pages (GitHub's 3000-file cap) may go on unread. The listed files are
    all LOW, churn-free and match changed_files, so only the cap can raise the tier."""
    files = [_file(f"scripts/f{i}.py", additions=0) for i in range(3000)]  # no churn
    ok, messages = _run(base, FakeGitHub(body="Risk: LOW — x", files=files))
    assert ok is False
    assert messages[0] == (
        "declared LOW, computed HIGH, final HIGH\n  - files listing truncated at 30 pages"
    )


def test_two_production_areas_read_medium_through_the_classifier(base):
    files = [_file("scripts/a.py"), _file("agents/b.py")]
    assert _computed(base, files) == ("MEDIUM", ["classifier ordinal 2"])


def test_the_docs_only_exemption_does_not_lower_a_protected_path(base):
    tier, reasons = _computed(base, [_file("docs/security/agent-boundaries.md")])
    assert (tier, reasons) == ("HIGH", ["protected path(s): docs/security/agent-boundaries.md"])


def test_an_unreadable_plan_review_config_reads_high(base, tmp_path):
    code = tmp_path / "code"
    (code / "config").mkdir(parents=True)
    (code / "config" / "plan_review.yaml").write_text("not: [valid", "utf-8")
    tier, reasons = risk_tier.computed_tier([_file("scripts/x.py")], 1, REPO, base, code_root=code)
    assert tier == "HIGH"
    assert reasons[0].startswith("plan_review.yaml unreadable (")


# --- #2201: the comment-only exemption on protected paths --------------------------------
# A protected-path diff loses its path floor only when every changed file is `.py`, both sides
# parse to the same AST, and every directive comment is unchanged and in place. Anything the
# rule cannot read keeps the floor.

SCRIPT = ".github/scripts/x.py"  # machinery bucket, one production area, no shared surface
SCRIPT_FLOOR = ("HIGH", [f"protected path(s): {SCRIPT}"])
CODE = b'"""Doc."""\nimport os  # noqa: F401\n\n\ndef f():  # why f\n    return 1\n'


def _with_sources(base, sources, files=None, note=""):
    """`computed_tier` on modified files, with `read_sources` answering `sources`."""
    files = files or [_file(path) for path in sources]
    return risk_tier.computed_tier(
        files, len(files), REPO, base, read_sources=lambda: (sources, note)
    )


def test_a_comment_only_edit_on_a_protected_path_drops_to_low_and_says_so(base):
    # an own-line comment above a directive, a reworded trailing one, one at the end
    after = (
        CODE.replace(b"import os", b"# about os\nimport os").replace(
            b"# why f", b"# why f, reworded"
        )
        + b"# the end\n"
    )
    assert _with_sources(base, {SCRIPT: (CODE, after)}) == (
        "LOW",
        [f"comment-only exemption: protected path(s) {SCRIPT} changed in comments only"],
    )
    # `supabase/**` is the guarded bucket here and the classifier's shared surface too.
    guarded = "supabase/functions/f.py"
    assert _with_sources(base, {guarded: (CODE, after)}) == (
        "LOW",
        [f"comment-only exemption: protected path(s) {guarded} changed in comments only"],
    )


@pytest.mark.parametrize(
    "after",
    [
        CODE.replace(b'"""Doc."""', b'"""Doc, reworded."""'),
        CODE.replace(b"return 1", b"return 2"),
        CODE.replace(b"# noqa: F401", b"# noqa: E501"),
        CODE.replace(b"  # noqa: F401", b""),
        CODE.replace(b"  # noqa: F401", b"").replace(b"# why f", b"# noqa: F401"),
        CODE.replace(b"# why f", b"# why f  # type: ignore"),
        CODE.replace(b"# why f", b"# pragma: no cover"),
        CODE.replace(b"# why f", b"# fmt: skip"),
        CODE.replace(b"# why f", b"# Pylint: disable=invalid-name"),
        b"#!/usr/bin/env python\n" + CODE,
        b"# -*- coding: latin-1 -*-\n" + CODE,
    ],
    ids=[
        "docstring",
        "code",
        "noqa code changed",
        "noqa dropped",
        "noqa moved",
        "type: ignore added",
        "pragma",
        "fmt:",
        "a directive in another case",
        "shebang",
        "coding cookie",
    ],
)
def test_a_docstring_code_or_directive_change_keeps_the_floor(base, after):
    assert _with_sources(base, {SCRIPT: (CODE, after)}) == SCRIPT_FLOOR


@pytest.mark.parametrize(
    ("sources", "files"),
    [
        ({SCRIPT: (b"def f(:\n", b"def f(:  # x\n")}, None),
        # sides that would pass as Python, so only the extension can refuse it
        ({SCRIPT: (CODE, CODE + b"# x\n"), "docs/a.md": (b"a\n", b"a  # x\n")}, None),
        ({SCRIPT: (CODE, CODE + b"# x\n")}, [_file(SCRIPT), _file("docs/a.md")]),
        ({".github/x.pyi": (b"x: int\n", b"x: int  # x\n")}, None),
        ({SCRIPT: (None, CODE)}, None),
        ({SCRIPT: (CODE, None)}, None),
        (None, [_file(SCRIPT)]),
        ({SCRIPT: (b"x = '\xff'\n", b"x = '\xff'  # x\n")}, None),
        ({SCRIPT: (CODE, CODE + b"# note\r# ruff: noqa\n")}, None),
        ({SCRIPT: (CODE, CODE.replace(b"F401", b"F401\r# ruff: noqa"))}, None),
        (
            {SCRIPT: (CODE, CODE + b"# x\n")},
            [_file(SCRIPT, status="renamed", previous_filename="scripts/old.py")],
        ),
    ],
    ids=[
        "does not parse",
        "a non-.py file beside it",
        "a non-.py file with no source",
        ".pyi",
        "added",
        "removed",
        "no sources",
        "invalid UTF-8",
        "a lone CR at the end of the file",
        "a lone CR after a trailing comment",
        "renamed",
    ],
)
def test_what_the_rule_cannot_read_keeps_the_floor(base, sources, files):
    tier, reasons = _with_sources(base, sources, files)
    floor = [
        f["filename"] for f in files or [_file(p) for p in sources] if f["filename"] != "docs/a.md"
    ]
    assert tier == "HIGH"
    assert [r for r in reasons if r.startswith(("protected", "comment-only"))] == [
        f"protected path(s): {floor[0]}"
    ]


@pytest.mark.parametrize(
    ("before", "after"),
    [
        (b"x = f(\n    1,\n    # nosec\n    2,\n)\n", b"x = f(\n    1,  # nosec\n    2,\n)\n"),
        (b"#!/usr/bin/env python\nx = 1\n", b"# note\n#!/usr/bin/env python\nx = 1\n"),
        (b"# coding: utf-8\nx = 1\n", b"# note\n\n# coding: utf-8\nx = 1\n"),
    ],
    ids=[
        "onto a line of code",
        "shebang pushed down",
        "coding cookie pushed down",
    ],
)
def test_a_directive_moved_to_another_line_keeps_the_floor(base, before, after):
    assert _with_sources(base, {SCRIPT: (before, after)}) == SCRIPT_FLOOR


def test_a_path_in_the_reason_cannot_start_a_workflow_command(base):
    path = "supabase/a\n::error::x.py"
    shown = "supabase/a\\n::error::x.py"
    comments = (CODE, CODE + b"# x\n")
    assert _with_sources(base, {path: comments}) == (
        "LOW",
        [f"comment-only exemption: protected path(s) {shown} changed in comments only"],
    )
    code = (CODE, CODE.replace(b"return 1", b"return 2"))
    assert _with_sources(base, {path: code}) == (  # supabase/** is the shared surface too
        "HIGH",
        [f"protected path(s): {shown}", "classifier ordinal 2"],
    )


def test_the_exemption_lowers_only_the_path_floor(base):
    after = CODE + b"# x\n"
    churned = [_file(SCRIPT, additions=500)]
    assert _with_sources(base, {SCRIPT: (CODE, after)}, churned) == (
        "MEDIUM",
        [
            f"comment-only exemption: protected path(s) {SCRIPT} changed in comments only",
            "classifier ordinal 2",
        ],
    )
    test_file = ".github/tests/test_x.py"
    weakened = [_file(test_file, patch="@@ -1 +1,2 @@\n x = 1\n+# pytest.mark.skip")]
    assert _with_sources(
        base, {test_file: (b"x = 1\n", b"x = 1\n# pytest.mark.skip\n")}, weakened
    ) == (
        "HIGH",
        [
            f"comment-only exemption: protected path(s) {test_file} changed in comments only",
            f"skip/xfail added in {test_file}: # pytest.mark.skip",
        ],
    )


def _exempt_line(*paths):
    return f"comment-only exemption: protected path(s) {', '.join(paths)} changed in comments only"


def _sides(paths, before=CODE, after=CODE + b"# x\n"):
    """`contents` for FakeGitHub: each path at the merge base and at the head."""
    return {k: v for p in paths for k, v in (((p, MERGE_BASE), before), ((p, HEAD), after))}


def _source_reads(api):
    return [p for _, p, _ in api.calls if "/compare/" in p or "/contents/" in p]


def test_evaluate_reads_the_two_sides_at_the_merge_base_and_the_head(base):
    # the base tip moved on since the branch point: its version is not the PR's "before"
    contents = {**_sides([SCRIPT]), (SCRIPT, BASE_TIP): CODE.replace(b"return 1", b"return 3")}
    api = FakeGitHub(body="Risk: LOW — x", files=[_file(SCRIPT)], contents=contents)
    assert _run(base, api) == (
        True,
        [f"declared LOW, computed LOW, final LOW\n  - {_exempt_line(SCRIPT)}"],
    )


_NOT_A_FILE = {"type": "dir", "encoding": "base64", "content": ""}
_TOO_LARGE = {"type": "file", "encoding": "none", "content": ""}
_NOT_INLINE = f"{SCRIPT}@{HEAD[:7]} is not an inline file"


@pytest.mark.parametrize(
    ("contents", "merge_base", "why"),
    [
        ({(SCRIPT, MERGE_BASE): CODE}, MERGE_BASE, "HTTP Error 404: error"),
        ({**_sides([SCRIPT]), (SCRIPT, HEAD): _TOO_LARGE}, MERGE_BASE, _NOT_INLINE),
        ({**_sides([SCRIPT]), (SCRIPT, HEAD): _NOT_A_FILE}, MERGE_BASE, _NOT_INLINE),
        ({**_sides([SCRIPT]), (SCRIPT, HEAD): []}, MERGE_BASE, _NOT_INLINE),
        (_sides([SCRIPT]), http_error(500), "HTTP Error 500: error"),
    ],
    ids=[
        "missing at the head",
        "too large to inline",
        "not a file",
        "a directory",
        "compare fails",
    ],
)
def test_an_unreadable_source_keeps_the_floor_and_says_why(base, contents, merge_base, why):
    api = FakeGitHub(
        body="Risk: LOW — x", files=[_file(SCRIPT)], contents=contents, merge_base=merge_base
    )
    ok, messages = _run(base, api)
    assert ok is False
    assert messages[0].split("\n  - ") == [
        "declared LOW, computed HIGH, final HIGH",
        f"comment-only exemption not checked: {why}",
        f"protected path(s): {SCRIPT}",
    ]


@pytest.mark.parametrize(
    "files",
    [
        [_file(SCRIPT, status="added")],
        [_file(SCRIPT, status="renamed", previous_filename=".github/scripts/old.py")],
        [_file(SCRIPT), _file(".github/workflows/w.yml")],
        [_file("scripts/x.py")],
    ],
    ids=["added", "renamed", "a .yml beside it", "no protected path"],
)
def test_a_diff_the_rule_does_not_cover_reads_no_source(base, files):
    api = FakeGitHub(body="Risk: HIGH — x", files=files, contents=_sides([SCRIPT, "scripts/x.py"]))
    _, messages = _run(base, api)
    assert _source_reads(api) == []
    assert "comment-only exemption" not in messages[0]


def test_the_rule_reads_at_most_30_files(base):
    paths = [f".github/scripts/x{i:02}.py" for i in range(31)]
    api = FakeGitHub(
        body="Risk: LOW — x", files=[_file(p) for p in paths[:30]], contents=_sides(paths)
    )
    assert _run(base, api) == (
        True,
        [f"declared LOW, computed LOW, final LOW\n  - {_exempt_line(*paths[:30])}"],
    )
    api = FakeGitHub(body="Risk: LOW — x", files=[_file(p) for p in paths], contents=_sides(paths))
    _, messages = _run(base, api)
    assert _source_reads(api) == []
    assert messages[0].split("\n  - ")[:2] == [
        "declared LOW, computed HIGH, final HIGH",
        "comment-only exemption not checked: 31 files, more than 30",
    ]


# --- AC3: test weakening -----------------------------------------------------------------


def test_a_removed_test_function_reads_high(base):
    files = [_file("tests/test_a.py", patch="@@ -1,2 +0,0 @@\n-def test_old():\n-    pass")]
    assert _computed(base, files) == ("HIGH", ["test function removed: test_old"])


def test_a_test_function_moved_to_another_file_does_not(base):
    files = [
        _file("tests/test_a.py", patch="@@ -1 +0,0 @@\n-def test_moved():"),
        _file("tests/test_b.py", patch="@@ -0,0 +1 @@\n+def test_moved():"),
    ]
    assert _computed(base, files) == ("LOW", [])


def test_a_removed_test_function_in_a_non_test_named_file_under_tests_reads_high(base):
    files = [_file("tests/helpers.py", patch="@@ -1,2 +0,0 @@\n-def test_old():\n-    pass")]
    assert _computed(base, files) == ("HIGH", ["test function removed: test_old"])


def test_a_test_file_renamed_out_of_the_test_set_reads_high(base):
    files = [_file("docs/a.txt", patch=None, status="renamed", previous_filename="tests/test_a.py")]
    assert _computed(base, files) == (
        "HIGH",
        ["test file renamed out of the test set: tests/test_a.py"],
    )


def test_a_pure_rename_between_test_files_is_not_an_unreadable_diff(base):
    files = [
        _file(
            "tests/test_b.py",
            patch=None,
            status="renamed",
            previous_filename="tests/test_a.py",
            additions=0,
            changes=0,
        )
    ]
    assert _computed(base, files) == ("LOW", [])


def test_a_renamed_test_file_with_edits_but_no_patch_still_reads_high(base):
    files = [
        _file(
            "tests/test_b.py",
            patch=None,
            status="renamed",
            previous_filename="tests/test_a.py",
            changes=3,
        )
    ]
    assert _computed(base, files) == ("HIGH", ["test file with no readable diff: tests/test_b.py"])


def test_a_newline_in_a_file_name_cannot_start_a_workflow_command_line(base):
    files = [_file("tests/a\n::stop-commands::x.py", patch=None, status="removed")]
    tier, reasons = _computed(base, files)
    assert (tier, reasons) == ("HIGH", ["test file removed: tests/a\\n::stop-commands::x.py"])
    assert not any(line.startswith("::") for r in reasons for line in r.split("\n"))


def test_adding_a_test_function_does_not(base):
    files = [_file("tests/test_a.py", patch="@@ -0,0 +1 @@\n+def test_new():")]
    assert _computed(base, files) == ("LOW", [])


def test_every_listed_skip_marker_added_to_a_test_file_reads_high(base):
    markers = [
        "@pytest.mark.skip(reason='x')",
        "@pytest.mark.skipif(True, reason='x')",
        "@mark.skipif(True, reason='x')",
        "@pytest.mark.xfail",
        "    pytest.skip('x')",
        "pytest.importorskip('yaml')",
        "@unittest.skipIf(True, 'x')",
        "collect_ignore = ['a.py']",
    ]
    not_high = []
    for marker in markers:
        files = [_file("tests/test_a.py", patch=f"@@ -0,0 +1 @@\n+{marker}")]
        tier, _ = _computed(base, files)
        if tier != "HIGH":
            not_high.append(marker)
    assert not_high == []


def test_a_skip_marker_in_a_non_test_file_does_not(base):
    files = [_file("scripts/x.py", patch="@@ -1 +1 @@\n-def test_helper():\n+# pytest.mark.skip")]
    assert _computed(base, files) == ("LOW", [])


def test_a_removed_test_file_reads_high(base):
    files = [_file("tests/test_a.py", status="removed", patch="@@ -1 +0,0 @@\n-x", deletions=1)]
    assert _computed(base, files) == ("HIGH", ["test file removed: tests/test_a.py"])


def test_a_test_file_without_a_readable_diff_reads_high(base):
    files = [_file("tests/test_big.py", patch=None)]
    assert _computed(base, files) == (
        "HIGH",
        ["test file with no readable diff: tests/test_big.py"],
    )


# --- AC4: the release is an approval at the current head from a releasing-role holder -----

HIGH_FILES = [_file("AGENTS.md")]


@pytest.fixture
def high(base):
    """Evaluate a PR that touches AGENTS.md (HIGH by path) with the given reviews."""

    def run(reviews, permissions, body="Risk: HIGH — rules file", head=HEAD, files=HIGH_FILES):
        api = FakeGitHub(body=body, files=files, reviews=reviews, permissions=permissions)
        return risk_tier.evaluate(api, REPO, 7, head, base, "osasuwu-bot")

    return run


def test_an_admin_approval_on_the_current_head_releases_a_high_pr(high):
    ok, messages = high([_review("alice", "APPROVED")], {"alice": "admin"})
    assert ok is True
    assert messages[-1] == "released by an APPROVED review from admin alice at aaaaaaa"


@pytest.mark.parametrize(
    ("reviews", "permissions"),
    [
        ([_review("alice", "APPROVED", commit=OLD)], {"alice": "admin"}),
        ([_review("osasuwu-bot", "APPROVED")], {"osasuwu-bot": "admin"}),
        ([_review("ci-app", "APPROVED", user_type="Bot")], {"ci-app": "admin"}),
        ([_review("bob", "APPROVED")], {"bob": "write"}),
        ([_review("alice", "APPROVED"), _review("alice", "CHANGES_REQUESTED")], {"alice": "admin"}),
        ([_review("alice", "APPROVED"), _review("alice", "DISMISSED")], {"alice": "admin"}),
        ([_review("alice", "COMMENTED")], {"alice": "admin"}),
        ([_review("alice", "APPROVED")], {}),
        ([], {}),
    ],
    ids=[
        "old head",
        "the lane's bot",
        "a Bot account",
        "not admin",
        "changes requested later",
        "dismissed",
        "comment only",
        "permission lookup fails",
        "no reviews",
    ],
)
def test_nothing_but_a_releasing_role_holders_approval_at_head_releases_a_high_pr(
    high, reviews, permissions
):
    ok, messages = high(reviews, permissions)
    assert ok is False
    assert messages[-1] == (
        "HIGH holds until a holder of the releasing role (admin, not a Bot account, not "
        "osasuwu-bot) leaves an APPROVED review on the current head aaaaaaa; a new push "
        "needs a new approval. See .github/scripts/risk_tier.md (residual risks)."
    )


def test_a_reviews_listing_past_its_page_cap_does_not_release(high):
    """#2068: an admin's head approval on the first page does not release a listing that
    may go on unread past its 10th full page; the hold names the cut."""
    reviews = [_review("alice", "APPROVED")]
    reviews += [_review(f"user{i}", "COMMENTED") for i in range(999)]
    ok, messages = high(reviews, {"alice": "admin"})
    assert ok is False
    assert messages[1:] == [
        "reviews listing truncated at 10 pages",
        "HIGH holds until a holder of the releasing role (admin, not a Bot account, not "
        "osasuwu-bot) leaves an APPROVED review on the current head aaaaaaa; a new push "
        "needs a new approval. See .github/scripts/risk_tier.md (residual risks).",
    ]


def test_a_later_approval_and_an_unrelated_comment_still_release(high):
    reviews = [
        _review("alice", "CHANGES_REQUESTED", commit=OLD),
        _review("alice", "APPROVED"),
        _review("alice", "COMMENTED"),
    ]
    ok, _ = high(reviews, {"alice": "admin"})
    assert ok is True


def test_a_declared_critical_line_holds_a_clean_diff(high):
    ok, messages = high([], {}, body="Risk: CRITICAL — data loss", files=[_file("scripts/x.py")])
    assert ok is False
    assert messages[0] == "declared CRITICAL, computed LOW, final CRITICAL"
    assert messages[-1].startswith("CRITICAL holds until a holder of the releasing role (admin,")


def test_an_event_for_a_head_that_has_since_moved_is_red_as_superseded(high):
    ok, messages = high([_review("alice", "APPROVED")], {"alice": "admin"}, head=OLD)
    assert (ok, messages) == (
        False,
        ["head moved to aaaaaaa (event was bbbbbbb): superseded by a newer push"],
    )


# --- #2088: an admin author's own HIGH/CRITICAL PR skips the hold ------------------------

HIGH_SUMMARY = "declared HIGH, computed HIGH, final HIGH\n  - protected path(s): AGENTS.md"
HIGH_HOLD = (
    "HIGH holds until a holder of the releasing role (admin, not a Bot account, not "
    "osasuwu-bot) leaves an APPROVED review on the current head aaaaaaa; a new push "
    "needs a new approval. See .github/scripts/risk_tier.md (residual risks)."
)


def _authored(base, author, permissions, body="Risk: HIGH — rules file", files=HIGH_FILES, **kw):
    api = FakeGitHub(body=body, files=files, author=author, permissions=permissions, **kw)
    return _run(base, api), api


def test_an_admin_authors_high_pr_is_green_without_reading_reviews_or_counting_admins(base):
    verdict, api = _authored(base, ("alice", "User"), {"alice": "admin"})
    assert verdict == (True, [HIGH_SUMMARY, "HIGH hold skipped: author alice has admin permission"])
    assert [p for _, p, _ in api.calls if "/reviews" in p] == []
    assert [p for _, p, _ in api.calls if "/collaborators" in p] == [
        f"repos/{REPO}/collaborators/alice/permission"
    ]


def test_an_admin_authors_declared_critical_pr_is_green_naming_the_tier(base):
    verdict, _ = _authored(
        base,
        ("alice", "User"),
        {"alice": "admin"},
        body="Risk: CRITICAL — data loss",
        files=[_file("scripts/x.py")],
    )
    assert verdict == (
        True,
        [
            "declared CRITICAL, computed LOW, final CRITICAL",
            "CRITICAL hold skipped: author alice has admin permission",
        ],
    )


def test_a_write_authors_high_pr_still_holds_until_an_admin_approves_at_head(base):
    held, _ = _authored(base, ("bob", "User"), {"bob": "write"})
    assert held == (False, [HIGH_SUMMARY, HIGH_HOLD])
    released, _ = _authored(
        base,
        ("bob", "User"),
        {"bob": "write", "dave": "admin"},
        reviews=[_review("dave", "APPROVED")],
    )
    assert released == (
        True,
        [HIGH_SUMMARY, "released by an APPROVED review from admin dave at aaaaaaa"],
    )


@pytest.mark.parametrize(
    "permissions",
    [{}, {"alice": http_error(500, url="https://api.github.com/x")}],
    ids=["lookup 404", "lookup 500"],
)
def test_an_unreadable_author_permission_counts_as_not_admin(base, permissions):
    verdict, _ = _authored(base, ("alice", "User"), permissions)
    assert verdict == (False, [HIGH_SUMMARY, HIGH_HOLD])


@pytest.mark.parametrize(
    "author",
    [("ci-app", "Bot"), ("osasuwu-bot", "User"), ("Osasuwu-Bot", "User")],
    ids=["a Bot account", "the lane's bot", "the lane's bot, other case"],
)
def test_an_admin_bot_author_does_not_skip_the_hold(base, author):
    verdict, _ = _authored(base, author, {author[0]: "admin"})
    assert verdict == (False, [HIGH_SUMMARY, HIGH_HOLD])


@pytest.mark.parametrize(
    ("body", "problem"),
    [
        ("Refs #1", "missing"),
        ("Risk: LOW", "malformed"),
        ("Risk: LOW — a\nRisk: HIGH — b", "duplicate"),
    ],
)
def test_an_admin_authors_bad_risk_line_is_still_red(base, body, problem):
    verdict, _ = _authored(base, ("alice", "User"), {"alice": "admin"}, body=body)
    assert verdict == (
        False,
        [
            f"The PR body has a {problem} Risk line. Expected exactly one line "
            f"`{GRAMMAR_LINE}` (grammar and examples: .github/scripts/risk_tier.md)."
        ],
    )


# --- main(): the exit code and the annotation --------------------------------------------


def _main_env(monkeypatch, host):
    env = {
        "GITHUB_REPOSITORY": REPO,
        "PR_NUMBER": "7",
        "HEAD_SHA": HEAD,
        "LANE_BOT_LOGIN": "osasuwu-bot",
        "RISK_TIER_HOST_ROOT": str(host),
        "GITHUB_TOKEN": "t0ken",
    }
    for key, value in env.items():
        monkeypatch.setenv(key, value)


@pytest.mark.parametrize(("body", "code"), [("Risk: LOW — x", 0), ("Refs #1", 1)])
def test_main_exits_with_the_verdict_and_annotates_a_failure(monkeypatch, capsys, base, body, code):
    api = FakeGitHub(body=body, files=[_file("scripts/x.py")])
    _main_env(monkeypatch, base)
    tokens = []
    with pytest.raises(SystemExit) as exit_info:
        risk_tier.main(make_client=lambda token: tokens.append(token) or api)
    assert exit_info.value.code == code
    assert tokens == ["t0ken"]
    out = capsys.readouterr().out
    assert ("::error::The PR body has a missing Risk line." in out) == (code == 1)


def test_main_reads_the_protected_list_from_the_host_root(monkeypatch, capsys, tmp_path):
    host = tmp_path / "host"
    (host / "config").mkdir(parents=True)
    (host / "config" / "protected-paths.json").write_text(
        json.dumps({REPO: {"guarded": ["scripts/**"]}}), "utf-8"
    )
    _main_env(monkeypatch, host)
    api = FakeGitHub(body="Risk: LOW — x", files=[_file("scripts/x.py")])
    tokens = []
    with pytest.raises(SystemExit) as exit_info:
        risk_tier.main(make_client=lambda token: tokens.append(token) or api)
    assert exit_info.value.code == 1
    assert tokens == ["t0ken"]
    assert "computed HIGH" in capsys.readouterr().out


def test_main_without_a_bot_login_fails_naming_the_variable(monkeypatch, capsys, base):
    _main_env(monkeypatch, base)
    monkeypatch.setenv("LANE_BOT_LOGIN", "")
    api = FakeGitHub(files=[_file("scripts/x.py")])
    with pytest.raises(SystemExit) as exit_info:
        risk_tier.main(make_client=lambda token: api)
    assert exit_info.value.code == 1
    assert capsys.readouterr().out.strip() == (
        "::error::risk-tier: LANE_BOT_LOGIN is empty; the calling workflow must pass the lane's "
        "bot login"
    )


@pytest.mark.parametrize(
    ("after", "exempt"),
    [(CODE + b"# x\n", True), (CODE.replace(b"return 1", b"return 2"), False), (None, False)],
    ids=["comments only", "code", "unreadable"],
)
def test_main_annotates_an_applied_exemption(monkeypatch, capsys, base, after, exempt):
    contents = {(SCRIPT, MERGE_BASE): CODE, (SCRIPT, HEAD): after}
    api = FakeGitHub(body="Risk: LOW — x", files=[_file(SCRIPT)], contents=contents)
    _main_env(monkeypatch, base)
    with pytest.raises(SystemExit):
        risk_tier.main(make_client=lambda token: api)
    notices = [line for line in capsys.readouterr().out.splitlines() if line.startswith("::notice")]
    assert notices == (
        [
            f"::notice title=risk-tier::comment-only exemption: protected path(s) {SCRIPT} "
            "changed in comments only"
        ]
        if exempt
        else []
    )


# --- AC5: the workflow ------------------------------------------------------------------

WORKFLOW = yaml.safe_load(
    (_root / ".github" / "workflows" / "pr-body-check.yml").read_text(encoding="utf-8")
)
TRIGGERS = WORKFLOW.get("on", WORKFLOW.get(True))  # PyYAML reads the bare key `on` as True


def _job():
    return WORKFLOW["jobs"]["risk-tier"]


def test_the_check_context_is_the_job_id_and_it_re_runs_on_reviews():
    assert "name" not in _job()  # a `name:` would change the check context from `risk-tier`
    assert TRIGGERS["pull_request_review"]["types"] == ["submitted", "dismissed"]
    assert TRIGGERS["pull_request"]["types"] == ["opened", "edited", "reopened", "synchronize"]
    assert "pull_request_target" not in TRIGGERS


def test_the_job_is_one_pinned_action_step_time_boxed_with_unchanged_scope():
    # #2013 PR2: the classifier comes from jarvis at a pinned commit, not the base checkout, so
    # the job is the action alone; scope and grouping stay what the required check ran under.
    job = _job()
    assert job["timeout-minutes"] == 10
    # actions: read lets the check read the code review's evidence, for its raise (#2202).
    assert job["permissions"] == {"actions": "read", "contents": "read", "pull-requests": "read"}
    assert job["concurrency"] == {
        "group": "risk-tier-${{ github.event.pull_request.number }}",
        "cancel-in-progress": True,
    }
    (step,) = job["steps"]
    assert re.fullmatch(r"Osasuwu/jarvis/\.github/actions/risk-tier@[0-9a-f]{40}", step["uses"])
    assert step["with"] == {"bot-login": "osasuwu-bot"}


# --- the composite action a host repo calls (#2013, D7) ----------------------------------

ACTION = yaml.safe_load(
    (_root / ".github" / "actions" / "risk-tier" / "action.yml").read_text(encoding="utf-8")
)


def test_the_action_reads_protected_paths_only_from_the_hosts_base_commit():
    checkouts = [
        s for s in ACTION["runs"]["steps"] if s.get("uses", "").startswith("actions/checkout@")
    ]
    assert len(checkouts) == 1
    assert checkouts[0]["with"] == {
        "ref": "${{ github.event.pull_request.base.ref }}",
        "path": ".risk-tier-host",
        "sparse-checkout": "config",
        "persist-credentials": False,
    }


def test_the_action_runs_the_classifier_from_its_own_pinned_checkout():
    (step,) = [s for s in ACTION["runs"]["steps"] if "risk_tier.py" in s.get("run", "")]
    # `$GITHUB_ACTION_PATH` is the action's repo at the pinned SHA: the host's tree is never run.
    assert step["run"] == 'python "$GITHUB_ACTION_PATH/../../scripts/risk_tier.py"'
    assert step["env"]["RISK_TIER_HOST_ROOT"] == "${{ github.workspace }}/.risk-tier-host"
    assert step["env"]["LANE_BOT_LOGIN"] == "${{ inputs.bot-login }}"
    assert step["env"]["HEAD_SHA"] == "${{ github.event.pull_request.head.sha }}"
    assert step["shell"] == "bash"


def test_the_actions_script_path_resolves_from_the_action_directory():
    action_dir = _root / ".github" / "actions" / "risk-tier"
    assert (action_dir / ".." / ".." / "scripts" / "risk_tier.py").is_file()


def test_no_context_value_is_interpolated_into_an_action_shell_step():
    runs = [s["run"] for s in ACTION["runs"]["steps"] if "run" in s]
    assert len(runs) == 2
    assert [r for r in runs if "${{" in r] == []


def test_a_review_event_does_not_skip_the_linked_issue_job():
    assert "if" not in WORKFLOW["jobs"]["require-linked-issue"]  # a skipped job reads as passing


# --- #2059: a Dependabot PR's body is not read; its declared tier is fixed at HIGH --------

DEPENDABOT = ("dependabot[bot]", "Bot")
# uv.lock is outside BASE_LIST and the classifier exempts a dependency bump, so the
# computed tier is LOW: only the fixed declared tier holds the PR.
LOCK_BUMP = [_file("uv.lock")]
DEPENDABOT_HOLD = (
    "HIGH holds until a holder of the releasing role (admin, not a Bot account, not "
    "osasuwu-bot) leaves an APPROVED review on the current head aaaaaaa; a new push "
    "needs a new approval. See .github/scripts/risk_tier.md (residual risks)."
)
DEPENDABOT_SUMMARY = (
    "declared HIGH (fixed: dependabot[bot] PR, body not read), computed LOW, final HIGH"
)


def test_a_dependabot_pr_without_a_risk_line_holds_as_high_until_an_admin_approves_at_head(
    base,
):
    notes = "Bumps the python-dependencies group with 1 update: pyyaml."
    held = _run(base, FakeGitHub(body=notes, files=LOCK_BUMP, author=DEPENDABOT))
    assert held == (False, [DEPENDABOT_SUMMARY, DEPENDABOT_HOLD])
    released = _run(
        base,
        FakeGitHub(
            body=notes,
            files=LOCK_BUMP,
            author=DEPENDABOT,
            reviews=[_review("alice", "APPROVED")],
            permissions={"alice": "admin"},
        ),
    )
    assert released == (
        True,
        [DEPENDABOT_SUMMARY, "released by an APPROVED review from admin alice at aaaaaaa"],
    )


@pytest.mark.parametrize(
    "body",
    [
        "Risk: LOW — upstream release notes",
        "Risk: CRITICAL — upstream release notes",
        "Risk: oops",
        "Risk: LOW — a\nRisk: HIGH — b",
        None,
    ],
    ids=["low", "critical", "malformed", "duplicate", "no body"],
)
def test_a_risk_line_in_a_dependabot_body_changes_nothing(base, body):
    api = FakeGitHub(body=body, files=LOCK_BUMP, author=DEPENDABOT)
    assert _run(base, api) == (False, [DEPENDABOT_SUMMARY, DEPENDABOT_HOLD])


@pytest.mark.parametrize(
    "author",
    [("dependabot[bot]", "User"), ("renovate[bot]", "Bot"), ("dependabot", "User")],
    ids=["dependabot login, not a Bot", "another bot", "look-alike human login"],
)
def test_only_the_dependabot_bot_account_skips_the_risk_line(base, author):
    api = FakeGitHub(body="Bumps pyyaml.", files=LOCK_BUMP, author=author)
    assert _run(base, api) == (
        False,
        [
            "The PR body has a missing Risk line. Expected exactly one line "
            f"`{GRAMMAR_LINE}` (grammar and examples: .github/scripts/risk_tier.md)."
        ],
    )


# --- #2202: the CI reviewer may raise the tier, never lower it ---------------------------

RAISED_HOLD = (
    "HIGH holds until a holder of the releasing role (admin, not a Bot account, not "
    "osasuwu-bot) leaves an APPROVED review on the current head aaaaaaa; a new push "
    "needs a new approval. See .github/scripts/risk_tier.md (residual risks)."
)
CLEAN = [_file("scripts/x.py")]  # computed LOW


def test_a_low_pr_the_reviewer_raises_to_high_holds_naming_the_raise(base):
    """AC2: findings with a raise go through the producer's validate and build_evidence,
    into the artifact the check reads; the final tier is the raise."""
    api = FakeGitHub(body="Risk: LOW — x", files=CLEAN, evidence=_raising("HIGH"))
    assert _run(base, api) == (
        False,
        [
            "declared LOW, computed LOW, final HIGH\n"
            "  - reviewer raise to HIGH applied (was LOW): rewrites the token refresh",
            RAISED_HOLD,
        ],
    )


def test_the_same_low_pr_without_a_raise_is_green(base):
    api = FakeGitHub(body="Risk: LOW — x", files=CLEAN)
    assert _run(base, api) == (True, ["declared LOW, computed LOW, final LOW"])


def test_a_raise_below_the_declared_tier_changes_nothing_and_is_logged(base):
    api = FakeGitHub(body="Risk: MEDIUM — x", files=CLEAN, evidence=_raising("LOW"))
    assert _run(base, api) == (
        True,
        [
            "declared MEDIUM, computed LOW, final MEDIUM\n"
            "  - reviewer raise to LOW not applied: at or below MEDIUM: rewrites the token refresh"
        ],
    )


def test_a_raise_below_the_computed_tier_changes_nothing_and_is_logged(base):
    files = [_file("scripts/a.py"), _file("agents/b.py")]  # two areas: computed MEDIUM
    api = FakeGitHub(body="Risk: LOW — x", files=files, evidence=_raising("LOW"))
    assert _run(base, api) == (
        True,
        [
            "declared LOW, computed MEDIUM, final MEDIUM\n"
            "  - classifier ordinal 2\n"
            "  - reviewer raise to LOW not applied: at or below MEDIUM: rewrites the token refresh"
        ],
    )


def test_a_raise_equal_to_the_final_tier_changes_nothing_and_is_logged(base):
    api = FakeGitHub(body="Risk: MEDIUM — x", files=CLEAN, evidence=_raising("MEDIUM"))
    ok, messages = _run(base, api)
    assert ok is True
    assert messages[0] == (
        "declared MEDIUM, computed LOW, final MEDIUM\n"
        "  - reviewer raise to MEDIUM not applied: at or below MEDIUM: rewrites the token refresh"
    )


def test_a_raise_to_medium_is_green_at_medium(base):
    api = FakeGitHub(body="Risk: LOW — x", files=CLEAN, evidence=_raising("MEDIUM"))
    assert _run(base, api) == (
        True,
        [
            "declared LOW, computed LOW, final MEDIUM\n"
            "  - reviewer raise to MEDIUM applied (was LOW): rewrites the token refresh"
        ],
    )


def test_a_newline_in_the_raise_reason_cannot_start_a_workflow_command_line(base):
    api = FakeGitHub(
        body="Risk: LOW — x", files=CLEAN, evidence=_raising("MEDIUM", "a\n::error::forged")
    )
    _, messages = _run(base, api)
    assert "\n::" not in messages[0]
    assert messages[0].endswith("(was LOW): a\\n::error::forged")


def test_the_highest_raise_across_attempts_applies(base):
    """A re-run's raise and an earlier attempt's both stand; the higher one wins."""
    api = FakeGitHub(
        body="Risk: LOW — x",
        files=CLEAN,
        review_runs=[_review_run(run_attempt=2)],
        artifacts={
            REVIEW_RUN: [
                {"id": 901, "name": "review-evidence-1", "expired": False},
                {"id": 902, "name": "review-evidence-2", "expired": False},
            ]
        },
        evidence={901: _raising("MEDIUM")[901], 902: _raising("HIGH")[901]},
    )
    ok, messages = _run(base, api)
    assert ok is False
    assert messages[0] == (
        "declared LOW, computed LOW, final HIGH\n"
        "  - reviewer raise to HIGH applied (was LOW): rewrites the token refresh\n"
        "  - reviewer raise to MEDIUM not applied: at or below HIGH: rewrites the token refresh"
    )


@pytest.mark.parametrize(
    ("evidence", "artifacts", "why"),
    [
        (
            {901: _evidence_zip(**{"raise": {"tier": "CRITICAL", "reason": "x"}})},
            None,
            "review evidence 900:1 is evidence-invalid",
        ),
        (
            {901: _evidence_zip(**{"raise": None})},
            None,
            "review evidence 900:1 is evidence-invalid",
        ),
        ({901: _evidence_zip(sha=OLD)}, None, "review evidence 900:1 is evidence-sha-mismatch"),
        ({901: b"not a zip"}, None, "review evidence 900:1 is unreadable"),
        (
            None,
            {REVIEW_RUN: [{"id": 901, "name": "review-evidence-1", "expired": True}]},
            "review evidence 900:1 is expired",
        ),
        (None, {REVIEW_RUN: []}, "review evidence 900:1 is missing"),
    ],
    ids=["critical-raise", "null-raise", "other-commit", "undownloadable", "expired", "deleted"],
)
def test_evidence_whose_raise_cannot_be_read_holds_at_high(base, evidence, artifacts, why):
    """Fail closed: a raise that is malformed, or evidence that is gone or unreadable,
    may hide a raise, so it reads as a raise to HIGH."""
    api = FakeGitHub(body="Risk: LOW — x", files=CLEAN, evidence=evidence, artifacts=artifacts)
    ok, messages = _run(base, api)
    assert ok is False
    assert messages[0] == (
        "declared LOW, computed LOW, final HIGH\n"
        f"  - reviewer raise to HIGH applied (was LOW): {why}: its raise is unknown, fail closed"
    )


@pytest.mark.parametrize(
    "error",
    [http_error(500), ValueError("page is not a list")],
    ids=["http-500", "bad-page"],
)
def test_an_unreadable_review_listing_holds_at_high(base, error):
    api = FakeGitHub(body="Risk: LOW — x", files=CLEAN, review_runs=error)
    ok, messages = _run(base, api)
    assert ok is False
    assert messages[0].startswith(
        "declared LOW, computed LOW, final HIGH\n"
        "  - reviewer raise to HIGH applied (was LOW): review evidence unreadable ("
    )


PENDING = (
    "waiting for the code review of aaaaaaa: {why}; the tier is re-decided when it "
    "completes, since the reviewer may raise it (#2202)"
)


@pytest.mark.parametrize(
    ("runs", "artifacts", "why"),
    [
        (
            [_review_run(status="in_progress", conclusion=None)],
            None,
            "review run 900 is not finished",
        ),
        ([_review_run(conclusion="action_required")], None, "review run 900 is not finished"),
        ([], None, "no successful review run has left evidence for this commit yet"),
        (
            [_review_run(conclusion="failure")],
            {},
            "no successful review run has left evidence for this commit yet",
        ),
    ],
    ids=["in-progress", "awaiting-approval", "no-run", "failed-run"],
)
def test_the_check_is_red_while_the_review_is_pending(base, runs, artifacts, why):
    """No review yet means no raise read yet: green now could merge before the raise lands."""
    api = FakeGitHub(body="Risk: LOW — x", files=CLEAN, review_runs=runs, artifacts=artifacts)
    assert _run(base, api) == (
        False,
        ["declared LOW, computed LOW, final LOW", PENDING.format(why=why)],
    )


def test_a_skipped_review_counts_as_done_with_no_raise(base):
    """A cosmetic, draft or untrusted PR's review uploads `status: skipped`: no reviewer ran."""
    skipped = gate.build_skipped_evidence(HEAD, "main", "cosmetic")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("review-evidence.json", json.dumps(skipped))
    api = FakeGitHub(body="Risk: LOW — x", files=CLEAN, evidence={901: buf.getvalue()})
    assert _run(base, api) == (True, ["declared LOW, computed LOW, final LOW"])


def test_a_host_without_a_review_workflow_reads_no_raise_and_does_not_wait(base):
    api = FakeGitHub(
        body="Risk: LOW — x",
        files=CLEAN,
        review_workflow=http_error(404, url=f"https://api.github.com/{REVIEW_WORKFLOW}"),
    )
    assert _run(base, api) == (
        True,
        [
            "declared LOW, computed LOW, final LOW\n"
            "  - no .github/workflows/code-review.yml on this repo: no reviewer raise to read"
        ],
    )
    assert not [p for _, p, _ in api.calls if "/runs" in p]


def test_an_unreadable_review_workflow_lookup_holds_at_high(base):
    api = FakeGitHub(body="Risk: LOW — x", files=CLEAN, review_workflow=http_error(500))
    ok, messages = _run(base, api)
    assert ok is False
    assert messages[0].startswith("declared LOW, computed LOW, final HIGH\n")


def test_a_pr_into_another_base_reads_no_raise(base):
    """code-gate decides only PRs into the default branch, so no review evidence binds."""
    api = FakeGitHub(
        body="Risk: LOW — x", files=CLEAN, base_ref="release", evidence=_raising("HIGH")
    )
    assert _run(base, api) == (
        True,
        [
            "declared LOW, computed LOW, final LOW\n"
            "  - base release is not the default branch main: no reviewer raise to read"
        ],
    )


def test_a_raise_on_an_admin_authors_pr_meets_the_unchanged_admin_pass(base):
    """The raise moves the tier; who may release it is unchanged."""
    api = FakeGitHub(
        body="Risk: LOW — x",
        files=CLEAN,
        evidence=_raising("HIGH"),
        author=("alice", "User"),
        permissions={"alice": "admin"},
    )
    ok, messages = _run(base, api)
    assert ok is True
    assert messages[-1] == "HIGH hold skipped: author alice has admin permission"


def test_main_binds_the_review_although_the_pr_number_arrives_as_a_string(
    monkeypatch, capsys, base
):
    """main reads PR_NUMBER from the environment; the review binds the integer, so a
    string compared raw would never bind and the check would wait for ever."""
    api = FakeGitHub(body="Risk: LOW — x", files=CLEAN, evidence=_raising("HIGH"))
    _main_env(monkeypatch, base)
    with pytest.raises(SystemExit) as exit_info:
        risk_tier.main(make_client=lambda token: api)
    assert exit_info.value.code == 1
    assert "reviewer raise to HIGH applied (was LOW)" in capsys.readouterr().out

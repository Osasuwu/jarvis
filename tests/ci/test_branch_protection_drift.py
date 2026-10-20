"""Drift probe between live branch protection and the binding documented in
docs/reference/github-repo-setup.md (#1998).

#1982 documented that `code-gate` is bound to the `osasuwu-ci` App and `gitleaks` to
github-actions, while the live protection kept `app_id: null` for both. Nothing noticed.
.github/scripts/branch_protection_drift.py compares the two on a schedule; these tests pin
what it calls drift, against the real documented block and the real workflow.
"""

import importlib.util
from pathlib import Path

import pytest
import yaml

from ._github_fake import FakeApi

_root = next(p for p in Path(__file__).resolve().parents if (p / ".github" / "scripts").is_dir())
_spec = importlib.util.spec_from_file_location(
    "branch_protection_drift", _root / ".github" / "scripts" / "branch_protection_drift.py"
)
drift = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(drift)

DOC = (_root / "docs" / "reference" / "github-repo-setup.md").read_text(encoding="utf-8")
WORKFLOW = yaml.safe_load(
    (_root / ".github" / "workflows" / "branch-protection-drift.yml").read_text(encoding="utf-8")
)

DOCUMENTED = {"code-gate": 3969106, "gitleaks": 15368, "pytest": 15368}


def _branch(checks, enabled=True):
    """The `protection` object of `GET /repos/{o}/{r}/branches/{b}`."""
    if not enabled:
        return {"protected": False, "protection": {"enabled": False}}
    return {
        "protected": True,
        "protection": {
            "enabled": True,
            "required_status_checks": {
                "contexts": [c["context"] for c in checks],
                "checks": checks,
            },
        },
    }


def _live(**ids):
    return _branch([{"context": name, "app_id": app} for name, app in ids.items()])


def test_matching_protection_has_no_drift():
    assert (
        drift.find_drift(
            DOCUMENTED, _live(**{"code-gate": 3969106, "gitleaks": 15368, "pytest": 15368})
        )
        == []
    )


def test_unbound_check_is_drift():
    # The #1998 state: app_id null accepts a same-named status from any source.
    live = _live(**{"code-gate": None, "gitleaks": 15368, "pytest": 15368})
    assert drift.find_drift(DOCUMENTED, live) == ["code-gate: documented app_id 3969106, live None"]


def test_check_bound_to_another_app_is_drift():
    live = _live(**{"code-gate": 3969106, "gitleaks": 99, "pytest": 15368})
    assert drift.find_drift(DOCUMENTED, live) == ["gitleaks: documented app_id 15368, live 99"]


def test_missing_and_undocumented_checks_are_both_drift():
    live = _live(**{"code-gate": 3969106, "gitleaks": 15368, "extra": 15368})
    assert drift.find_drift(DOCUMENTED, live) == [
        "pytest: documented app_id 15368, not required live",
        "extra: required live (app_id 15368), not documented",
    ]


def test_context_listed_without_a_check_entry_counts_as_unbound():
    # Legacy `contexts` with no `checks` entry is how an unbound requirement reads.
    live = _branch(
        [{"context": "code-gate", "app_id": 3969106}, {"context": "gitleaks", "app_id": 15368}]
    )
    live["protection"]["required_status_checks"]["contexts"].append("pytest")
    assert drift.find_drift(DOCUMENTED, live) == ["pytest: documented app_id 15368, live None"]


@pytest.mark.parametrize(
    "branch",
    [
        _branch([], enabled=False),
        {"protected": False},
        {"protected": True, "protection": {"enabled": True}},
    ],
)
def test_no_protection_or_no_required_checks_is_drift_on_every_documented_check(branch):
    assert drift.find_drift(DOCUMENTED, branch) == [
        "code-gate: documented app_id 3969106, not required live",
        "gitleaks: documented app_id 15368, not required live",
        "pytest: documented app_id 15368, not required live",
    ]


def test_documented_binding_is_read_from_the_marked_json_block():
    doc = (
        'prose { "x": 1 }\n\n'
        "<!-- required-checks-binding -->\n"
        "```json\n"
        '{"code-gate": 3969106, "gitleaks": 15368}\n'
        "```\n"
    )
    assert drift.parse_documented_binding(doc) == {"code-gate": 3969106, "gitleaks": 15368}


@pytest.mark.parametrize(
    "doc",
    [
        'no marker here\n```json\n{"a": 1}\n```\n',
        "<!-- required-checks-binding -->\nno fence follows\n",
        '<!-- required-checks-binding -->\n```json\n{"a": "1"}\n```\n',
        "<!-- required-checks-binding -->\n```json\n{}\n```\n",
    ],
)
def test_unreadable_documented_binding_is_an_error_not_an_empty_pass(doc):
    with pytest.raises(drift.BindingError):
        drift.parse_documented_binding(doc)


def test_the_real_doc_binds_code_gate_to_the_ci_app_and_gitleaks_to_github_actions():
    binding = drift.parse_documented_binding(DOC)
    assert binding["code-gate"] == 3969106
    assert binding["gitleaks"] == 15368


def test_run_reports_drift_with_a_nonzero_exit(capsys):
    live = _live(**{"code-gate": None, "gitleaks": 15368})
    doc = '<!-- required-checks-binding -->\n```json\n{"code-gate": 3969106, "gitleaks": 15368}\n```\n'
    assert drift.run(doc, lambda: live) == 1
    assert "code-gate: documented app_id 3969106, live None" in capsys.readouterr().out


def test_run_exits_zero_when_in_step(capsys):
    live = _live(**{"code-gate": 3969106})
    doc = '<!-- required-checks-binding -->\n```json\n{"code-gate": 3969106}\n```\n'
    assert drift.run(doc, lambda: live) == 0
    assert capsys.readouterr().out == "No drift: 1 required checks match the documented binding.\n"


def test_main_reads_the_default_branch_with_the_job_token_and_exits_on_drift(
    monkeypatch, tmp_path, capsys
):
    doc = tmp_path / "binding.md"
    doc.write_text(
        '<!-- required-checks-binding -->\n```json\n{"code-gate": 3969106}\n```\n',
        encoding="utf-8",
    )
    api = FakeApi({"repos/owner/repo/branches/main": _live(**{"code-gate": None})})
    tokens = []
    for key, value in {
        "GITHUB_REPOSITORY": "owner/repo",
        "DEFAULT_BRANCH": "main",
        "GH_TOKEN": "t0ken",
        "BINDING_DOC": str(doc),
        "DOC_ROOT": str(tmp_path / "no-docs"),
    }.items():
        monkeypatch.setenv(key, value)
    assert drift.main(make_client=lambda token: tokens.append(token) or api) == 1
    assert tokens == ["t0ken"]
    assert api.calls == [("GET", "repos/owner/repo/branches/main", None)]
    assert "code-gate: documented app_id 3969106, live None" in capsys.readouterr().out


def test_the_probe_runs_unattended_on_a_schedule_and_on_demand():
    on = WORKFLOW[True]  # PyYAML parses the bare key `on` as True
    (entry,) = on["schedule"]
    assert entry["cron"] == "23 5 * * *"
    assert "workflow_dispatch" in on
    # It judges the default branch's doc, so a PR run would compare against stale state.
    assert "pull_request" not in on
    assert "pull_request_target" not in on


def test_the_probe_job_runs_the_script_with_a_read_only_token():
    job = WORKFLOW["jobs"]["drift"]
    assert WORKFLOW["permissions"] == {"contents": "read"}
    (step,) = [s for s in job["steps"] if "run" in s]
    assert step["run"] == "python3 .github/scripts/branch_protection_drift.py"
    assert step["env"]["GH_TOKEN"] == "${{ secrets.GITHUB_TOKEN }}"


# --- Doc claims: prose that names a required check (#1894) -----------------------------------
# A doc that calls `X` a required check is a claim about live protection. When `X` is not
# required live, a reader trusts a gate that is not there; the probe reports it.


def _names(text, path="doc.md"):
    return [name for _, _, name in drift.claimed_required_checks(path, text)]


@pytest.mark.parametrize(
    "text",
    [
        "Here `alpha` is a required check.",
        "Here `alpha` is a **required** check.",
        "It gates the `alpha` required check.",
        "The required check `alpha` turns red.",
        "The host must make `alpha` a required check first.",
        "Add `alpha` to the required status checks of the default branch.",
    ],
)
def test_each_sentence_form_extracts_the_claimed_name(text):
    assert _names(text) == ["alpha"]


def test_a_sentence_wrapped_across_lines_extracts_on_the_line_of_the_name():
    text = "intro line\nbecause\n`alpha` is a **required**\ncheck, and more.\n"
    assert drift.claimed_required_checks("d.md", text) == [("d.md", 3, "alpha")]


def test_an_enumeration_after_required_checks_extracts_each_listed_name():
    text = "Gated by three required checks: `alpha`, `beta`, and `gamma`.\n"
    assert _names(text) == ["alpha", "beta", "gamma"]


@pytest.mark.parametrize(
    "text",
    [
        "Required checks: `alpha`, `beta`.",
        "The six required checks are `alpha`, `beta`.",
        "REQUIRED CHECKS: `alpha` and `beta`.",
    ],
)
def test_an_enumeration_opened_by_are_or_in_any_case_extracts_each_listed_name(text):
    assert _names(text) == ["alpha", "beta"]


def test_a_sentence_form_matches_in_any_case_and_keeps_the_name_as_written():
    assert _names("The Required Check `Alpha` turns red.") == ["Alpha"]


@pytest.mark.parametrize(
    "text",
    [
        "The `alpha` run is not a required check and never fails.",
        "These are not required checks: `alpha`, `beta`.",
        "The required check `alpha` is no longer required.",
        "It runs as the `alpha/beta.yml` required check.",
        "It runs as the `alpha.yml` required check.",
        "These required checks on `main` are listed below.",
        "Here `alpha` is a check that is required somewhere.",
    ],
)
def test_negated_path_branch_and_loose_sentences_extract_nothing(text):
    assert _names(text) == []


def test_the_agents_md_merge_rule_sentence_extracts_exactly_the_six_checks():
    # Verbatim from AGENTS.md "Merge rules" (the glosses carry `Risk:`, which is no check).
    text = (
        "Merging is gated by six required CI checks on the default branch: `code-gate` (the code-review\n"
        "verdict), `require-linked-issue`, `pytest`, `gitleaks`, `waiting-human-review`, and `risk-tier`\n"
        "(the PR's `Risk:` line and diff; a non-admin author's HIGH+ stays red until an admin human approves the head SHA) —\n"
        "branch-protection enforced, no cooperation needed from you.\n"
    )
    assert _names(text) == [
        "code-gate",
        "require-linked-issue",
        "pytest",
        "gitleaks",
        "waiting-human-review",
        "risk-tier",
    ]


def test_a_token_in_running_prose_after_the_list_is_not_an_item():
    text = "Two required checks (`alpha`, `beta`) are the target set; see `gamma` for more.\n"
    assert _names(text) == ["alpha", "beta"]


def test_fenced_code_is_not_scanned():
    text = "```\n`alpha` is a required check.\n```\n"
    assert _names(text) == []


REAL_CLAIMS = drift.scan_docs(_root)


def test_the_real_docs_claim_exactly_these_required_checks():
    assert sorted({(path, name) for path, _, name in REAL_CLAIMS}) == [
        (".github/scripts/risk_tier.md", "risk-tier"),
        ("AGENTS.md", "code-gate"),
        ("AGENTS.md", "gitleaks"),
        ("AGENTS.md", "pytest"),
        ("AGENTS.md", "require-linked-issue"),
        ("AGENTS.md", "risk-tier"),
        ("AGENTS.md", "waiting-human-review"),
        ("docs/reference/ci-guard-meta-tests.md", "Detect secrets with gitleaks"),
        ("docs/reference/ci-guard-meta-tests.md", "pytest"),
        ("docs/reference/github-repo-setup.md", "code-gate"),
        ("docs/reference/github-repo-setup.md", "gitleaks"),
        ("docs/reference/github-repo-setup.md", "pytest"),
        ("docs/reference/github-repo-setup.md", "require-linked-issue"),
        ("docs/reference/github-repo-setup.md", "risk-tier"),
        ("docs/reference/github-repo-setup.md", "waiting-human-review"),
        ("docs/reference/lane-host-setup.md", "risk-tier"),
        ("docs/reference/vendored-plugin-pins.md", "code-gate"),
    ]


def test_every_claimed_name_not_tracked_as_stale_is_in_the_documented_binding():
    # So a PR that drops a check from the binding while prose still names it fails `pytest`.
    binding = drift.parse_documented_binding(DOC)
    known = {(path, name) for path, name, _ in drift.KNOWN_STALE}
    untracked = [c for c in REAL_CLAIMS if (c[0], c[2]) not in known and c[2] not in binding]
    assert untracked == []


def test_every_known_stale_entry_still_matches_a_claim_in_the_real_docs():
    assert drift.unmatched_known_stale(REAL_CLAIMS) == []


def test_a_known_stale_entry_whose_claim_is_gone_is_reported():
    entry = ("docs/x.md", "alpha", 1)
    assert drift.unmatched_known_stale([("docs/x.md", 4, "beta")], known=(entry,)) == [entry]


def test_run_fails_on_a_claimed_check_that_is_not_required_live(capsys):
    live = _live(**{"code-gate": 3969106})
    doc = '<!-- required-checks-binding -->\n```json\n{"code-gate": 3969106}\n```\n'
    claims = [("docs/a.md", 7, "code-gate"), ("docs/b.md", 12, "ghost")]
    assert drift.run(doc, lambda: live, claims) == 1
    out = capsys.readouterr().out
    assert "docs/b.md:12: `ghost` is named as a required check, not required live" in out
    assert "docs/a.md" not in out


def test_run_warns_on_a_tracked_stale_claim_and_exits_zero(capsys):
    live = _live(**{"code-gate": 3969106})
    doc = '<!-- required-checks-binding -->\n```json\n{"code-gate": 3969106}\n```\n'
    (path, name, issue) = drift.KNOWN_STALE[0]
    assert drift.run(doc, lambda: live, [(path, 3, name)]) == 0
    assert (
        f"{path}:3: `{name}` is named as a required check, not required live (tracked #{issue})"
        in (capsys.readouterr().out)
    )


def test_main_fails_on_a_doc_claim_under_doc_root_that_is_not_required_live(
    monkeypatch, tmp_path, capsys
):
    doc = tmp_path / "binding.md"
    doc.write_text(
        '<!-- required-checks-binding -->\n```json\n{"code-gate": 3969106}\n```\n',
        encoding="utf-8",
    )
    root = _doc_root(tmp_path / "root")
    (root / "AGENTS.md").write_text("Here `ghost` is a required check.\n", encoding="utf-8")
    api = FakeApi({"repos/owner/repo/branches/main": _live(**{"code-gate": 3969106})})
    for key, value in {
        "GITHUB_REPOSITORY": "owner/repo",
        "DEFAULT_BRANCH": "main",
        "GH_TOKEN": "t0ken",
        "BINDING_DOC": str(doc),
        "DOC_ROOT": str(root),
    }.items():
        monkeypatch.setenv(key, value)
    assert drift.main(make_client=lambda token: api) == 1
    assert "AGENTS.md:1: `ghost` is named as a required check" in capsys.readouterr().out


def _doc_root(root):
    """A doc root holding every scanned file and directory, all empty of claims."""
    for name in drift.SCANNED_FILES:
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text("No claims here.\n", encoding="utf-8")
    for name in drift.SCANNED_DIRS:
        (root / name).mkdir(parents=True, exist_ok=True)
    return root


# A scan that sees nothing must not read as "no claims" (#2138 review): a sparse checkout that
# drops a root, or a wrong DOC_ROOT / cwd, would otherwise print "No drift" having checked no doc.


@pytest.mark.parametrize("gone", ["AGENTS.md", "docs/reference"])
def test_a_missing_scan_root_is_an_error_naming_it(tmp_path, gone):
    root = _doc_root(tmp_path / "root")
    target = root / gone
    if target.is_dir():
        target.rmdir()
    else:
        target.unlink()
    with pytest.raises(drift.DocScanError, match=gone):
        drift.scan_docs(root)


def test_a_scan_that_finds_no_file_is_an_error(monkeypatch, tmp_path):
    monkeypatch.setattr(drift, "SCANNED_FILES", ())
    monkeypatch.setattr(drift, "SCANNED_DIRS", ("docs",))
    (tmp_path / "docs").mkdir()
    with pytest.raises(drift.DocScanError, match="no docs to scan"):
        drift.scan_docs(tmp_path)


def test_main_fails_closed_when_doc_root_is_missing_even_with_protection_in_step(
    monkeypatch, tmp_path, capsys
):
    doc = tmp_path / "binding.md"
    doc.write_text(
        '<!-- required-checks-binding -->\n```json\n{"code-gate": 3969106}\n```\n',
        encoding="utf-8",
    )
    api = FakeApi({"repos/owner/repo/branches/main": _live(**{"code-gate": 3969106})})
    for key, value in {
        "GITHUB_REPOSITORY": "owner/repo",
        "DEFAULT_BRANCH": "main",
        "GH_TOKEN": "t0ken",
        "BINDING_DOC": str(doc),
        "DOC_ROOT": str(tmp_path / "no-docs"),
    }.items():
        monkeypatch.setenv(key, value)
    assert drift.main(make_client=lambda token: api) == 1
    out = capsys.readouterr().out
    assert "Doc scan failed: scan roots missing" in out
    assert "AGENTS.md" in out
    assert "No drift" not in out
    assert api.calls == [("GET", "repos/owner/repo/branches/main", None)]


def test_the_workflow_sparse_checkout_covers_every_scanned_root():
    (checkout,) = [s for s in WORKFLOW["jobs"]["drift"]["steps"] if "uses" in s]
    entries = checkout["with"]["sparse-checkout"].split()
    for root in drift.SCANNED_ROOTS:
        assert any(root == e or root.startswith(e + "/") for e in entries), root
    assert len(drift.SCANNED_ROOTS) >= 7

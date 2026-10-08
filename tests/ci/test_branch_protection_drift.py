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

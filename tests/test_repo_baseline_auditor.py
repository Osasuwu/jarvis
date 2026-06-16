"""Tests for the Auditor shell — empirical 6-repo audit + manifest seed (slice 1).

The Auditor is a thin gh/REST shell with an *injectable runner* so the parsing
logic is exercised against canned ``gh api`` JSON with zero live calls. Each
test class maps to one acceptance-criterion bullet of issue #934.
"""

from __future__ import annotations

import base64
import json

import pytest

from scripts.repo_baseline import Manifest
from scripts.repo_baseline import auditor as auditor_mod
from scripts.repo_baseline.auditor import (
    OSASUWU_REPOS,
    Auditor,
    BranchProtection,
    GhNotFound,
    RepoSettings,
    RepoSnapshot,
    gh_runner,
    scrub_topology,
    seed_manifest,
)


# ── Test double: dict-backed gh runner ───────────────────────────────


class FakeRunner:
    """Stand-in for the live ``gh api`` runner.

    ``responses`` maps an api path → parsed JSON. Paths listed in
    ``not_found`` raise ``GhNotFound`` (simulating a 404, e.g. a repo with
    no branch protection or no dependabot.yml).
    """

    def __init__(self, responses: dict, not_found: set[str] | None = None):
        self.responses = responses
        self.not_found = set(not_found or ())
        self.calls: list[str] = []

    def __call__(self, path: str, *, paginate: bool = False):
        self.calls.append(path)
        if path in self.not_found:
            raise GhNotFound(path)
        return self.responses[path]


def _dependabot_b64(*ecosystems: str) -> dict:
    updates = "\n".join(
        f'  - package-ecosystem: "{e}"\n    directory: "/"\n    schedule:\n      interval: "weekly"'
        for e in ecosystems
    )
    text = f"version: 2\nupdates:\n{updates}\n"
    return {
        "content": base64.b64encode(text.encode()).decode(),
        "encoding": "base64",
    }


def _jarvis_responses() -> dict:
    return {
        "repos/Osasuwu/jarvis": {
            "allow_auto_merge": True,
            "allow_squash_merge": True,
            "allow_merge_commit": False,
            "allow_rebase_merge": False,
            "delete_branch_on_merge": True,
            "visibility": "public",
            "default_branch": "main",
        },
        "repos/Osasuwu/jarvis/labels": [
            {"name": "priority:critical", "color": "b60205", "description": "Hotfix"},
            {"name": "status:in-progress", "color": "fbca04", "description": ""},
        ],
        "repos/Osasuwu/jarvis/actions/workflows": {
            "workflows": [
                {"name": "Code Review", "path": ".github/workflows/code-review.yml"},
                {"name": "pytest", "path": ".github/workflows/pytest.yml"},
            ]
        },
        "repos/Osasuwu/jarvis/branches/main/protection": {
            "required_status_checks": {
                "strict": True,
                "contexts": ["review", "pytest"],
            }
        },
        "repos/Osasuwu/jarvis/contents/.github/dependabot.yml": _dependabot_b64(
            "pip", "github-actions"
        ),
    }


class TestRepoSnapshotParsing:
    """AC1 — Auditor reads labels/workflows/settings/protection/dependabot."""

    def test_audit_builds_full_snapshot(self):
        auditor = Auditor(FakeRunner(_jarvis_responses()))
        snap = auditor.audit("Osasuwu/jarvis")

        assert isinstance(snap, RepoSnapshot)
        assert snap.repo == "Osasuwu/jarvis"

        # repo settings
        assert snap.settings.allow_auto_merge is True
        assert snap.settings.allow_squash_merge is True
        assert snap.settings.allow_merge_commit is False
        assert snap.settings.delete_branch_on_merge is True
        assert snap.settings.visibility == "public"
        assert snap.settings.default_branch == "main"

        # labels — name + color + description
        assert [lb.name for lb in snap.labels] == [
            "priority:critical",
            "status:in-progress",
        ]
        assert snap.labels[0].color == "b60205"
        assert snap.labels[0].description == "Hotfix"

        # workflow filenames
        assert snap.workflows == [
            ".github/workflows/code-review.yml",
            ".github/workflows/pytest.yml",
        ]

        # branch protection
        assert isinstance(snap.branch_protection, BranchProtection)
        assert snap.branch_protection.strict is True
        assert snap.branch_protection.contexts == ["review", "pytest"]

        # dependabot ecosystems
        assert snap.dependabot_ecosystems == ["pip", "github-actions"]

    def test_bare_repo_absent_protection_and_dependabot(self):
        """A repo with no branch protection / no dependabot.yml audits cleanly:
        404 on those paths is 'feature off', not an error."""
        responses = {
            "repos/Osasuwu/dnd-calendar": {
                "allow_auto_merge": False,
                "allow_squash_merge": True,
                "allow_merge_commit": True,
                "allow_rebase_merge": True,
                "delete_branch_on_merge": False,
                "visibility": "public",
                "default_branch": "main",
            },
            "repos/Osasuwu/dnd-calendar/labels": [],
            "repos/Osasuwu/dnd-calendar/actions/workflows": {"workflows": []},
        }
        not_found = {
            "repos/Osasuwu/dnd-calendar/branches/main/protection",
            "repos/Osasuwu/dnd-calendar/contents/.github/dependabot.yml",
        }
        auditor = Auditor(FakeRunner(responses, not_found))
        snap = auditor.audit("Osasuwu/dnd-calendar")

        assert snap.branch_protection is None
        assert snap.dependabot_ecosystems == []
        assert snap.labels == []
        assert snap.workflows == []
        assert snap.settings.allow_auto_merge is False

    def test_branch_protection_reads_modern_checks_field(self):
        """GitHub deprecated required_status_checks.contexts in favour of
        .checks ([{context, app_id}]). A repo configured after that migration
        can have contexts=[] while checks holds the real names — reading only
        contexts would report an apparently-protected repo with zero required
        checks. Fall back to .checks when contexts is empty. (#978 MAJOR 1.)"""
        responses = dict(_jarvis_responses())
        responses["repos/Osasuwu/jarvis/branches/main/protection"] = {
            "required_status_checks": {
                "strict": True,
                "contexts": [],
                "checks": [
                    {"context": "review", "app_id": 1},
                    {"context": "pytest", "app_id": 2},
                ],
            }
        }
        snap = Auditor(FakeRunner(responses)).audit("Osasuwu/jarvis")
        assert snap.branch_protection.strict is True
        assert snap.branch_protection.contexts == ["review", "pytest"]

    def test_dependabot_unexpected_encoding_raises(self):
        """The Contents API sets encoding='none' with empty content for files
        over ~1 MB. Silently base64-decoding '' yields [] — misreporting a repo
        that HAS dependabot as having none. A present-but-unreadable file is an
        audit failure, not 'feature off' — fail loud. (#978 MINOR 6.)"""
        responses = dict(_jarvis_responses())
        responses["repos/Osasuwu/jarvis/contents/.github/dependabot.yml"] = {
            "content": "",
            "encoding": "none",
        }
        with pytest.raises(RuntimeError, match="encoding"):
            Auditor(FakeRunner(responses)).audit("Osasuwu/jarvis")

    def test_repo_settings_merge_method_defaults_match_github(self):
        """GitHub's real defaults for squash/merge-commit/rebase are all True;
        auto-merge and delete-branch default False. A test double (or any caller)
        that omits these fields must inherit GitHub's actual defaults, not a
        blanket False that misreports the repo. (#978 MINOR 7.)"""
        s = RepoSettings()
        assert s.allow_squash_merge is True
        assert s.allow_merge_commit is True
        assert s.allow_rebase_merge is True
        assert s.allow_auto_merge is False
        assert s.delete_branch_on_merge is False

        # _read_settings inherits the same defaults when the API omits a field.
        responses = {
            "repos/Osasuwu/x": {"visibility": "public", "default_branch": "main"},
            "repos/Osasuwu/x/labels": [],
            "repos/Osasuwu/x/actions/workflows": {"workflows": []},
        }
        not_found = {
            "repos/Osasuwu/x/branches/main/protection",
            "repos/Osasuwu/x/contents/.github/dependabot.yml",
        }
        snap = Auditor(FakeRunner(responses, not_found)).audit("Osasuwu/x")
        assert snap.settings.allow_squash_merge is True
        assert snap.settings.allow_merge_commit is True
        assert snap.settings.allow_rebase_merge is True


class TestSnapshotSerialization:
    """AC3 — structured JSON snapshot artifact, round-trippable + deterministic."""

    def test_to_dict_from_dict_round_trip(self):
        auditor = Auditor(FakeRunner(_jarvis_responses()))
        snap = auditor.audit("Osasuwu/jarvis")

        restored = RepoSnapshot.from_dict(snap.to_dict())
        assert restored == snap

    def test_to_dict_is_json_serialisable_and_deterministic(self):
        import json

        auditor = Auditor(FakeRunner(_jarvis_responses()))
        snap = auditor.audit("Osasuwu/jarvis")

        d = snap.to_dict()
        # Stable, sorted JSON — committed fixture must not churn on re-audit.
        s1 = json.dumps(d, sort_keys=True, indent=2)
        s2 = json.dumps(snap.to_dict(), sort_keys=True, indent=2)
        assert s1 == s2
        # Round-trips through a JSON string too.
        assert RepoSnapshot.from_dict(json.loads(s1)) == snap

    def test_bare_repo_round_trip(self):
        """branch_protection=None must survive serialization."""
        responses = {
            "repos/Osasuwu/dnd-calendar": {
                "visibility": "public",
                "default_branch": "main",
            },
            "repos/Osasuwu/dnd-calendar/labels": [],
            "repos/Osasuwu/dnd-calendar/actions/workflows": {"workflows": []},
        }
        not_found = {
            "repos/Osasuwu/dnd-calendar/branches/main/protection",
            "repos/Osasuwu/dnd-calendar/contents/.github/dependabot.yml",
        }
        snap = Auditor(FakeRunner(responses, not_found)).audit("Osasuwu/dnd-calendar")
        assert RepoSnapshot.from_dict(snap.to_dict()) == snap
        assert snap.to_dict()["branch_protection"] is None

    def test_to_dict_nested_lists_are_independent_copies(self):
        """to_dict must deep-copy: mutating a nested list in the returned dict
        (e.g. branch_protection.contexts) must NOT corrupt the live snapshot.
        A shallow vars().copy() shares the list object. (#978 MINOR 5.)"""
        snap = Auditor(FakeRunner(_jarvis_responses())).audit("Osasuwu/jarvis")
        d = snap.to_dict()
        d["branch_protection"]["contexts"].append("INJECTED")
        d["dependabot_ecosystems"].append("INJECTED")
        d["workflows"].append("INJECTED")
        assert "INJECTED" not in snap.branch_protection.contexts
        assert "INJECTED" not in snap.dependabot_ecosystems
        assert "INJECTED" not in snap.workflows


class TestSeedManifest:
    """AC4 — derive a per-repo Manifest skeleton from a snapshot, populating
    the axis values from observed reality. Output must round-trip through
    Manifest.from_dict (no unknown keys)."""

    def test_seed_captures_observed_axes(self):
        snap = Auditor(FakeRunner(_jarvis_responses())).audit("Osasuwu/jarvis")
        seed = seed_manifest(snap)

        # The seed is a plain manifest dict that from_dict accepts unchanged.
        m = Manifest.from_dict(seed)
        assert m.repo == "Osasuwu/jarvis"
        assert m.resolve_axis("auto_merge") is True
        assert m.resolve_axis("branch_protection") is True
        assert m.resolve_axis("required_check_contexts") == ["review", "pytest"]
        assert m.resolve_axis("dependabot_ecosystems") == ["pip", "github-actions"]
        assert m.resolve_axis("visibility") == "public"

    def test_seed_bare_repo_captures_absences_explicitly(self):
        """A bare repo's absences (no protection, no dependabot, auto_merge off)
        must be captured as explicit values, NOT left to resolve to the full
        profile's defaults — otherwise the seed would misreport reality."""
        responses = {
            "repos/Osasuwu/dnd-calendar": {
                "allow_auto_merge": False,
                "visibility": "public",
                "default_branch": "main",
            },
            "repos/Osasuwu/dnd-calendar/labels": [],
            "repos/Osasuwu/dnd-calendar/actions/workflows": {"workflows": []},
        }
        not_found = {
            "repos/Osasuwu/dnd-calendar/branches/main/protection",
            "repos/Osasuwu/dnd-calendar/contents/.github/dependabot.yml",
        }
        snap = Auditor(FakeRunner(responses, not_found)).audit("Osasuwu/dnd-calendar")
        m = Manifest.from_dict(seed_manifest(snap))

        assert m.resolve_axis("auto_merge") is False
        assert m.resolve_axis("branch_protection") is False
        assert m.resolve_axis("required_check_contexts") == []
        # Crucially [] not the ["pip","github-actions"] profile default.
        assert m.resolve_axis("dependabot_ecosystems") == []

    def test_seed_private_repo_visibility(self):
        responses = dict(_jarvis_responses())
        responses["repos/Osasuwu/jarvis"] = {
            **responses["repos/Osasuwu/jarvis"],
            "visibility": "private",
        }
        snap = Auditor(FakeRunner(responses)).audit("Osasuwu/jarvis")
        m = Manifest.from_dict(seed_manifest(snap))
        assert m.resolve_axis("visibility") == "private"

    def test_seed_dedupes_dependabot_ecosystems(self):
        """A repo with multiple dependabot update blocks for the same ecosystem
        (e.g. pip for two directories) yields a duplicated ecosystem list on the
        snapshot. The manifest axis is a *set* of ecosystem types, so the seed
        must dedupe — preserving first-seen order — or the renderer would emit
        duplicate dependabot blocks. (Surfaced by the live audit of Osasuwu/jarvis,
        which has two pip blocks; unit fixtures used distinct ecosystems.)"""
        responses = dict(_jarvis_responses())
        responses["repos/Osasuwu/jarvis/contents/.github/dependabot.yml"] = _dependabot_b64(
            "pip", "pip", "github-actions"
        )
        snap = Auditor(FakeRunner(responses)).audit("Osasuwu/jarvis")
        assert snap.dependabot_ecosystems == ["pip", "pip", "github-actions"]

        seed = seed_manifest(snap)
        assert seed["dependabot_ecosystems"] == ["pip", "github-actions"]
        m = Manifest.from_dict(seed)
        assert m.resolve_axis("dependabot_ecosystems") == ["pip", "github-actions"]

    def test_seed_profile_full_for_baselined_repo(self):
        """A repo with auto-merge AND branch protection is observably baselined
        → profile 'full'. (#978 MAJOR 2.)"""
        snap = Auditor(FakeRunner(_jarvis_responses())).audit("Osasuwu/jarvis")
        assert seed_manifest(snap)["profile"] == "full"

    def test_seed_profile_minimal_for_bare_repo(self):
        """A bare repo (no auto-merge AND no branch protection) is observably
        un-baselined → profile 'minimal', not 'full'. Hardcoding 'full' would
        make it silently inherit the full profile's Python-shaped axes
        (ci_language, test_extras) that seed_manifest omits — the seed must
        reflect observed posture, not prescribe a target. (#978 MAJOR 2.)"""
        responses = {
            "repos/Osasuwu/dnd-calendar": {
                "allow_auto_merge": False,
                "visibility": "public",
                "default_branch": "main",
            },
            "repos/Osasuwu/dnd-calendar/labels": [],
            "repos/Osasuwu/dnd-calendar/actions/workflows": {"workflows": []},
        }
        not_found = {
            "repos/Osasuwu/dnd-calendar/branches/main/protection",
            "repos/Osasuwu/dnd-calendar/contents/.github/dependabot.yml",
        }
        snap = Auditor(FakeRunner(responses, not_found)).audit("Osasuwu/dnd-calendar")
        seed = seed_manifest(snap)
        assert seed["profile"] == "minimal"
        # Explicit observed axes still win over the minimal profile defaults.
        m = Manifest.from_dict(seed)
        assert m.resolve_axis("auto_merge") is False
        assert m.resolve_axis("branch_protection") is False


class TestScrubTopology:
    """AC5 — redact device/infra topology before a snapshot is committed to a
    PUBLIC repo. Applied at fixture-write time. Must catch ANY username, not a
    hardcoded one, and leave a clean structure byte-identical."""

    def test_redacts_tailnet_ip(self):
        out = scrub_topology({"x": "runner reachable at 100.83.12.7 ok"})
        assert "100.83.12.7" not in json.dumps(out)
        assert out["x"] == "runner reachable at <REDACTED-IP> ok"

    def test_redacts_windows_user_path_any_username(self):
        out = scrub_topology({"x": r"see C:\Users\someguy\GitHub\jarvis\foo"})
        assert "someguy" not in json.dumps(out)
        assert out["x"] == r"see C:\Users\<user>\GitHub\jarvis\foo"

    def test_redacts_unix_home_paths(self):
        out = scrub_topology({"a": "/home/alice/code", "b": "/Users/bob/x"})
        assert out["a"] == "/home/<user>/code"
        assert out["b"] == "/Users/<user>/x"

    def test_redacts_nested_dicts_and_lists(self):
        data = {
            "labels": [{"description": "self-hosted runner 100.1.2.3"}],
            "nested": {"path": r"C:\Users\joe\x"},
        }
        out = scrub_topology(data)
        assert out["labels"][0]["description"] == "self-hosted runner <REDACTED-IP>"
        assert out["nested"]["path"] == r"C:\Users\<user>\x"

    def test_does_not_mutate_input(self):
        data = {"x": "100.5.6.7"}
        scrub_topology(data)
        assert data["x"] == "100.5.6.7"  # original untouched

    def test_clean_snapshot_unchanged(self):
        snap = Auditor(FakeRunner(_jarvis_responses())).audit("Osasuwu/jarvis")
        d = snap.to_dict()
        assert scrub_topology(d) == d


class TestAuditAll:
    """AC2 — audit a set of repos, returning one snapshot per repo."""

    def test_audit_all_returns_snapshot_per_repo(self):
        responses = {
            **_jarvis_responses(),
            "repos/Osasuwu/dnd-calendar": {
                "allow_auto_merge": False,
                "visibility": "public",
                "default_branch": "main",
            },
            "repos/Osasuwu/dnd-calendar/labels": [],
            "repos/Osasuwu/dnd-calendar/actions/workflows": {"workflows": []},
        }
        not_found = {
            "repos/Osasuwu/dnd-calendar/branches/main/protection",
            "repos/Osasuwu/dnd-calendar/contents/.github/dependabot.yml",
        }
        auditor = Auditor(FakeRunner(responses, not_found))
        result = auditor.audit_all(["Osasuwu/jarvis", "Osasuwu/dnd-calendar"])

        assert set(result) == {"Osasuwu/jarvis", "Osasuwu/dnd-calendar"}
        assert isinstance(result["Osasuwu/jarvis"], RepoSnapshot)
        assert result["Osasuwu/jarvis"].settings.allow_auto_merge is True
        assert result["Osasuwu/dnd-calendar"].branch_protection is None

    def test_osasuwu_repos_constant_is_the_five_baseline_repos(self):
        # Baseline scope = the milestone #48 PRD's 5 Osasuwu repos, NOT
        # config/repos.conf (which is the daily-triage list).
        assert OSASUWU_REPOS == [
            "Osasuwu/jarvis",
            "Osasuwu/music-intel-mcp",
            "Osasuwu/like_spotify_mobile_app",
            "Osasuwu/dnd-calendar",
            "Osasuwu/farming-evolution",
        ]
        # redrobot is NOT in the Osasuwu baseline scope — credential-blocked,
        # different owner, deferred to #940.
        assert not any("redrobot" in r for r in OSASUWU_REPOS)


class _FakeProc:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


class TestGhRunner:
    """The live gh/REST shell — exercised with a monkeypatched ``subprocess``
    so the 404 mapping + pagination parsing are tested with zero live calls."""

    def test_object_endpoint_returns_parsed_json(self, monkeypatch):
        captured = {}

        def fake_run(args, **kwargs):
            captured["args"] = args
            return _FakeProc(stdout='{"visibility": "public"}')

        monkeypatch.setattr(auditor_mod.subprocess, "run", fake_run)
        out = gh_runner("repos/Osasuwu/jarvis")
        assert out == {"visibility": "public"}
        assert captured["args"][:2] == ["gh", "api"]
        assert "repos/Osasuwu/jarvis" in captured["args"]
        assert "--paginate" not in captured["args"]

    def test_404_maps_to_gh_not_found(self, monkeypatch):
        def fake_run(args, **kwargs):
            return _FakeProc(returncode=1, stderr="gh: Not Found (HTTP 404)")

        monkeypatch.setattr(auditor_mod.subprocess, "run", fake_run)
        with pytest.raises(GhNotFound):
            gh_runner("repos/Osasuwu/jarvis/branches/main/protection")

    def test_non_404_error_raises_runtime_error(self, monkeypatch):
        def fake_run(args, **kwargs):
            return _FakeProc(returncode=1, stderr="gh: Bad credentials (HTTP 401)")

        monkeypatch.setattr(auditor_mod.subprocess, "run", fake_run)
        with pytest.raises(RuntimeError, match="401"):
            gh_runner("repos/Osasuwu/jarvis")

    def test_paginate_flattens_concatenated_array_pages(self, monkeypatch):
        # gh api --paginate emits one JSON array per page, concatenated with no
        # separator. The runner must merge them into a single flat list.
        page1 = '[{"name": "a"}, {"name": "b"}]'
        page2 = '[{"name": "c"}]'

        def fake_run(args, **kwargs):
            assert "--paginate" in args
            return _FakeProc(stdout=page1 + page2)

        monkeypatch.setattr(auditor_mod.subprocess, "run", fake_run)
        out = gh_runner("repos/Osasuwu/jarvis/labels", paginate=True)
        assert [d["name"] for d in out] == ["a", "b", "c"]

    def test_paginate_single_page(self, monkeypatch):
        def fake_run(args, **kwargs):
            return _FakeProc(stdout='[{"name": "only"}]')

        monkeypatch.setattr(auditor_mod.subprocess, "run", fake_run)
        out = gh_runner("repos/Osasuwu/jarvis/labels", paginate=True)
        assert [d["name"] for d in out] == ["only"]

    def test_paginate_raises_on_mixed_type_stream(self, monkeypatch):
        """A page stream of mixed types (array + trailing object) is corrupt.
        Returning the raw [list, dict] would fail deep in the caller with no
        useful error — raise explicitly instead. (#978 MINOR 3.)"""

        def fake_run(args, **kwargs):
            return _FakeProc(stdout='[{"name": "a"}]{"cursor": "x"}')

        monkeypatch.setattr(auditor_mod.subprocess, "run", fake_run)
        with pytest.raises(RuntimeError, match="page structure"):
            gh_runner("repos/Osasuwu/jarvis/labels", paginate=True)

    def test_digit_404_in_non_notfound_error_does_not_map_to_gh_not_found(self, monkeypatch):
        """A '404' digit run inside a non-NotFound error (e.g. a path or message
        referencing 404) must NOT false-positive into GhNotFound — match gh's
        actual 'HTTP 404' marker, not a bare digit run. (#978 MINOR 4.)"""

        def fake_run(args, **kwargs):
            return _FakeProc(returncode=1, stderr="gh: rate limited, see 404 widgets (HTTP 403)")

        monkeypatch.setattr(auditor_mod.subprocess, "run", fake_run)
        with pytest.raises(RuntimeError, match="403"):
            gh_runner("repos/Osasuwu/error-404-demo")

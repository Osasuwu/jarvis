"""Tests for the Manifest model — validation, profile resolution, from_dict."""

import pytest

from scripts.repo_baseline import FileClass, Manifest


class TestManifestFromDict:
    def test_basic_manifest(self):
        m = Manifest.from_dict({
            "repo": "Osasuwu/jarvis",
            "profile": "full",
            "required_check_contexts": ["review", "pytest"],
        })
        assert m.repo == "Osasuwu/jarvis"
        assert m.profile == "full"

    def test_unknown_keys_rejected(self):
        with pytest.raises(ValueError, match="Unknown manifest keys"):
            Manifest.from_dict({"repo": "x", "nonsense_key": 42})

    def test_minimal_profile_defaults(self):
        m = Manifest.from_dict({
            "repo": "test/minimal",
            "profile": "minimal",
        })
        # minimal profile: auto_merge=False, branch_protection=False
        assert m.resolve_axis("auto_merge") is False
        assert m.resolve_axis("branch_protection") is False
        # Fewer managed files
        managed = m.resolve_axis("managed_files")
        assert ".github/workflows/code-review.yml" not in (managed or [])


class TestFileClassRouting:
    def test_managed_class(self):
        m = Manifest.from_dict({"repo": "x"})
        assert m.class_for_file(".github/workflows/code-review.yml") == FileClass.MANAGED

    def test_language_test_class(self):
        m = Manifest.from_dict({"repo": "x"})
        assert m.class_for_file(".github/workflows/pytest.yml") == FileClass.LANGUAGE_TEST

    def test_custom_file_class(self):
        m = Manifest.from_dict({
            "repo": "x",
            "custom_files": ["scripts/deploy.sh"],
        })
        assert m.class_for_file("scripts/deploy.sh") == FileClass.REPO_CUSTOM

    def test_default_deny_for_unknown(self):
        m = Manifest.from_dict({"repo": "x"})
        assert m.class_for_file("some/random/file.txt") == FileClass.REPO_CUSTOM


class TestAxisResolution:
    def test_required_check_contexts_explicit(self):
        """required_check_contexts has no profile fallback — must be explicit."""
        m = Manifest.from_dict({
            "repo": "x",
            "required_check_contexts": ["a", "b"],
        })
        assert m.resolve_axis("required_check_contexts") == ["a", "b"]

    def test_empty_required_check_contexts_returns_empty_list(self):
        m = Manifest.from_dict({"repo": "x"})
        assert m.resolve_axis("required_check_contexts") == []

    def test_runs_on_profile_default(self):
        m = Manifest.from_dict({"repo": "x"})
        assert m.resolve_axis("runs_on") == ["ubuntu-latest"]

    def test_runs_on_explicit_override(self):
        m = Manifest.from_dict({
            "repo": "x",
            "runs_on": ["self-hosted"],
        })
        assert m.resolve_axis("runs_on") == ["self-hosted"]

    def test_ci_language_default(self):
        m = Manifest.from_dict({"repo": "x"})
        assert m.resolve_axis("ci_language") == "python"

    def test_ci_language_override(self):
        m = Manifest.from_dict({
            "repo": "x",
            "ci_language": "javascript",
        })
        assert m.resolve_axis("ci_language") == "javascript"

    def test_code_review_marketplace_default(self):
        m = Manifest.from_dict({"repo": "x"})
        assert m.resolve_axis("code_review_marketplace") == "anthropics/claude-code-action@v1"

    def test_visibility_from_profile(self):
        m = Manifest.from_dict({"repo": "x", "profile": "full"})
        assert m.resolve_axis("visibility") == "public"

    def test_visibility_uses_profile_default_when_unset(self):
        """visibility=None (unset) → falls back to profile default, not a hardcoded value."""
        m = Manifest.from_dict({"repo": "x"})
        # No explicit visibility → should resolve from profile (which is "public")
        assert m.visibility is None
        assert m.resolve_axis("visibility") == "public"

    def test_visibility_explicit_override(self):
        """Explicit visibility in manifest overrides profile default."""
        m = Manifest.from_dict({"repo": "x", "visibility": "private"})
        assert m.resolve_axis("visibility") == "private"

    def test_explicit_empty_managed_files_not_replaced_by_default(self):
        """Manifest with managed_files=[] must yield empty, not the default set."""
        m = Manifest.from_dict({"repo": "x", "managed_files": []})
        assert m.resolved_managed_files == []


class TestJarvisSplitPreserved:
    """jarvis's existing split: pytest=LANGUAGE-TEST, ci-meta=MANAGED,
    schema-drift-check/issue-checks=REPO-CUSTOM."""

    def test_pytest_is_language_test(self):
        m = Manifest.from_dict({"repo": "Osasuwu/jarvis"})
        assert m.class_for_file(".github/workflows/pytest.yml") == FileClass.LANGUAGE_TEST

    def test_ci_meta_is_managed(self):
        m = Manifest.from_dict({"repo": "Osasuwu/jarvis"})
        assert m.class_for_file(".github/workflows/ci-meta.yml") == FileClass.MANAGED

    def test_schema_drift_check_is_repo_custom(self):
        m = Manifest.from_dict({
            "repo": "Osasuwu/jarvis",
            "custom_files": [
                ".github/workflows/schema-drift-check.yml",
                ".github/workflows/issue-checks.yml",
            ],
        })
        assert m.class_for_file(
            ".github/workflows/schema-drift-check.yml"
        ) == FileClass.REPO_CUSTOM

    def test_issue_checks_is_repo_custom(self):
        m = Manifest.from_dict({
            "repo": "Osasuwu/jarvis",
            "custom_files": [
                ".github/workflows/schema-drift-check.yml",
                ".github/workflows/issue-checks.yml",
            ],
        })
        assert m.class_for_file(
            ".github/workflows/issue-checks.yml"
        ) == FileClass.REPO_CUSTOM

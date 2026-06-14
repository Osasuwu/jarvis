"""Manifest model — per-repo declarative config for the baseline sync.

Every axis has a default so per-repo manifests are sparse (declare only
deviations from the default profile).
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Dict, List, Optional


class FileClass(enum.Enum):
    """Three-class file model for the baseline sync."""

    MANAGED = "managed"
    """Overwrite byte-for-byte modulo axis substitution."""

    LANGUAGE_TEST = "language_test"
    """Managed + ``ci_language`` axis + escape-hatch (``test_extras`` / override)."""

    REPO_CUSTOM = "repo_custom"
    """Default-deny: untouched unless listed in ``manifest.custom_files``."""


@dataclass
class AxisProfile:
    """Named set of axis defaults (e.g. ``full``, ``minimal``)."""

    runs_on: List[str] = field(default_factory=lambda: ["ubuntu-latest"])
    ci_language: str = "python"
    code_review_marketplace: str = "anthropics/claude-code-action@v1"
    dependabot_ecosystems: List[str] = field(default_factory=lambda: ["pip", "github-actions"])
    auto_merge: bool = True
    branch_protection: bool = True
    visibility: str = "public"
    test_extras: str = "[full,dev]"
    managed_files: List[str] = field(default_factory=lambda: list(_MANAGED_FILES_DEFAULT))
    custom_files: List[str] = field(default_factory=list)


# ── Canonical set  ────────────────────────────────────────────────────
_MANAGED_FILES_DEFAULT = [
    ".github/workflows/code-review.yml",
    ".github/workflows/owner-queue-guard.yml",
    ".github/workflows/pr-body-check.yml",
    ".github/workflows/ci-meta.yml",
    ".github/dependabot.yml",
    ".github/ISSUE_TEMPLATE/bug.yml",
    ".github/ISSUE_TEMPLATE/task.yml",
    ".github/ISSUE_TEMPLATE/config.yml",
    ".github/PULL_REQUEST_TEMPLATE.md",
]

# Axes that every manifest MUST declare (no-profile default applicable).
REQUIRED_AXES = frozenset({
    "ci_language",
    "code_review_marketplace",
    "required_check_contexts",
    "test_extras",
})


def _resolve_managed_files(override: list | None, profile: str,
                           profiles: dict[str, AxisProfile] | None = None) -> list[str]:
    """Resolve managed_files: explicit override → profile default → hardcoded default."""
    if override is not None:
        return override
    profiles = profiles or {}
    profile_val = profiles.get(profile, AxisProfile()).managed_files if profile else None
    return profile_val or list(_MANAGED_FILES_DEFAULT)


@dataclass
class Manifest:
    """Per-repo declarative configuration for the baseline sync.

    Use ``from_dict`` for deserialization from a YAML/JSON manifest file.
    """

    repo: str = ""
    profile: str = "full"
    visibility: str = "public"

    # ── Axis overrides (None = use profile default) ───────────────────
    runs_on: Optional[List[str]] = None
    ci_language: str = ""
    code_review_marketplace: str = ""
    dependabot_ecosystems: Optional[List[str]] = None
    auto_merge: Optional[bool] = None
    branch_protection: Optional[bool] = None
    test_extras: str = ""

    # ── Explicit check-contexts (required axis — no fallback) ──────────
    required_check_contexts: List[str] = field(default_factory=list)

    # ── File inventory (Optional = resolve via profile) ─────────────────
    managed_files: Optional[List[str]] = None
    custom_files: List[str] = field(default_factory=list)

    # ── LANGUAGE-TEST class files ───────────────────────────────────────
    language_test_files: List[str] = field(default_factory=lambda: [
        ".github/workflows/pytest.yml",
    ])

    # ── Profiles (class constant — not a field) ────────────────────────
    _PROFILES: Dict[str, AxisProfile] = field(default_factory=lambda: {
        "full": AxisProfile(),
        "minimal": AxisProfile(
            auto_merge=False,
            branch_protection=False,
            managed_files=[
                ".github/workflows/owner-queue-guard.yml",
                ".github/workflows/pr-body-check.yml",
                ".github/workflows/ci-meta.yml",
                ".github/dependabot.yml",
            ],
        ),
    })

    @classmethod
    def from_dict(cls, data: dict) -> Manifest:
        valid = {"repo", "profile", "visibility", "runs_on", "ci_language",
                 "code_review_marketplace", "dependabot_ecosystems",
                 "auto_merge", "branch_protection", "test_extras",
                 "required_check_contexts", "managed_files", "custom_files",
                 "language_test_files"}
        extra = set(data) - valid
        if extra:
            raise ValueError(f"Unknown manifest keys: {sorted(extra)}")

        return cls(
            repo=data.get("repo", ""),
            profile=data.get("profile", "full"),
            visibility=data.get("visibility", "public"),
            runs_on=data.get("runs_on"),
            ci_language=data.get("ci_language", ""),
            code_review_marketplace=data.get("code_review_marketplace", ""),
            dependabot_ecosystems=data.get("dependabot_ecosystems"),
            auto_merge=data.get("auto_merge"),
            branch_protection=data.get("branch_protection"),
            test_extras=data.get("test_extras", ""),
            required_check_contexts=data.get("required_check_contexts", []),
            managed_files=data.get("managed_files"),
            custom_files=data.get("custom_files", []),
            language_test_files=data.get("language_test_files", [
                ".github/workflows/pytest.yml",
            ]),
        )

    def resolve_axis(self, key: str) -> str | int | bool | list | None:
        """Resolve an axis value: per-manifest override → profile default."""
        axis_defaults = self._PROFILES.get(self.profile, AxisProfile())
        override = getattr(self, key, None)
        profile_val = getattr(axis_defaults, key, None)

        if key == "required_check_contexts":
            return self.required_check_contexts  # always explicit, no fallback

        if key == "managed_files":
            return _resolve_managed_files(override, self.profile, self._PROFILES)

        # Explicit None or empty → use profile default
        if override is None or (isinstance(override, (str, list)) and not override):
            return profile_val
        return override

    @property
    def resolved_managed_files(self) -> List[str]:
        """Managed files resolved through current profile."""
        return self.resolve_axis("managed_files") or list(_MANAGED_FILES_DEFAULT)

    def class_for_file(self, path: str) -> FileClass:
        """Determine the file class for a given repo-path."""
        if path in self.custom_files:
            return FileClass.REPO_CUSTOM
        if path in self.language_test_files:
            return FileClass.LANGUAGE_TEST
        if path in self.resolved_managed_files:
            return FileClass.MANAGED
        return FileClass.REPO_CUSTOM  # default-deny

    def file_class_label(self, path: str) -> str:
        return self.class_for_file(path).value

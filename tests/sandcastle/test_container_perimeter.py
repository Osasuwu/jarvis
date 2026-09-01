"""Tests for the container permission perimeter (#1121 step 12).

The perimeter moves INTO the image in this slice: a PreToolUse denylist and
``permissions.deny`` are COPYed alongside the vendored skills, and the
container gets ``JARVIS_PRINCIPAL=subagent`` baked in as an ``ENV`` — closing
the drift where docs/design/sandcastle-integration.md described these as
active controls while the actual spawn env never set them.
"""

from __future__ import annotations

import json
from pathlib import Path

DOCKERFILE = Path(__file__).resolve().parent.parent.parent / ".sandcastle" / "Dockerfile"
CONTAINER_SETTINGS = Path(__file__).resolve().parent.parent.parent / ".sandcastle" / "container-settings.json"


def _dockerfile_text() -> str:
    return DOCKERFILE.read_text(encoding="utf-8")


def test_dockerfile_copies_container_settings_after_skills():
    text = _dockerfile_text()
    skills_idx = text.index("COPY --chown=agent:agent .claude-userlevel/skills/")
    settings_idx = text.index("COPY --chown=agent:agent .sandcastle/container-settings.json")
    assert settings_idx > skills_idx
    assert "/home/agent/.claude/settings.json" in text


def test_dockerfile_sets_jarvis_principal_subagent():
    text = _dockerfile_text()
    assert "ENV JARVIS_PRINCIPAL=subagent" in text


def test_container_settings_is_valid_json():
    data = json.loads(CONTAINER_SETTINGS.read_text(encoding="utf-8"))
    assert isinstance(data, dict)


def test_container_settings_denies_credential_paths():
    data = json.loads(CONTAINER_SETTINGS.read_text(encoding="utf-8"))
    deny = data["permissions"]["deny"]
    assert "Read(~/.ssh/**)" in deny
    assert "Read(**/.env)" in deny
    assert "Edit(~/.aws/**)" in deny


def test_container_settings_wires_protected_files_hook():
    data = json.loads(CONTAINER_SETTINGS.read_text(encoding="utf-8"))
    pretooluse = data["hooks"]["PreToolUse"]
    matchers = [entry["matcher"] for entry in pretooluse]
    assert "Edit|Write|NotebookEdit" in matchers
    commands = [
        h["command"]
        for entry in pretooluse
        for h in entry["hooks"]
    ]
    assert any("protected-files.py" in cmd for cmd in commands)

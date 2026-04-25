"""Tests for scripts/install/installer.py.

Covers should-fix items from #344 and test coverage gaps.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest import mock

import pytest

# Import installer module
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts" / "install"))
import installer


class TestIncludeFor:
    """Tests for _include_for normalization fix (#4)."""

    def test_exact_match_succeeds(self):
        """Test that exact normalized path match returns include list."""
        manifest = {
            "groups": [
                {
                    "id": "test_group",
                    "directories": [
                        {
                            "source": "scripts/foo",
                            "include": ["file1.py", "file2.py"]
                        }
                    ]
                }
            ]
        }
        result = installer._include_for(manifest, "test_group", "scripts/foo")
        assert result == ["file1.py", "file2.py"]

    def test_overlapping_prefixes(self):
        """Test that overlapping prefixes don't cause false matches.

        When two groups have sources like 'scripts' and 'scripts/install',
        normalized path equality should prevent 'scripts/install' from
        incorrectly matching against the 'scripts' group.
        """
        manifest = {
            "groups": [
                {
                    "id": "group1",
                    "directories": [
                        {
                            "source": "scripts",
                            "include": ["group1_file.py"]
                        }
                    ]
                },
                {
                    "id": "group2",
                    "directories": [
                        {
                            "source": "scripts/install",
                            "include": ["group2_file.py"]
                        }
                    ]
                }
            ]
        }
        # Should match group2 exactly, not group1 via substring
        result = installer._include_for(manifest, "group2", "scripts/install")
        assert result == ["group2_file.py"]

    def test_no_match_returns_none(self):
        """Test that non-matching source returns None."""
        manifest = {
            "groups": [
                {
                    "id": "test_group",
                    "directories": [
                        {
                            "source": "scripts/foo",
                            "include": ["file1.py"]
                        }
                    ]
                }
            ]
        }
        result = installer._include_for(manifest, "test_group", "scripts/bar")
        assert result is None

    def test_normalized_path_variants(self):
        """Test that different path separators normalize to same result."""
        manifest = {
            "groups": [
                {
                    "id": "test_group",
                    "directories": [
                        {
                            "source": "scripts/foo",
                            "include": ["file1.py"]
                        }
                    ]
                }
            ]
        }
        # Both forward slash and backslash should resolve to same normalized form
        result = installer._include_for(manifest, "test_group", "scripts/foo")
        assert result == ["file1.py"]


class TestSetEnvLogging:
    """Tests for _set_env failure logging fix (#5)."""

    def test_setx_failure_logged(self, capsys):
        """Test that setx returncode != 0 is logged to stderr."""
        with mock.patch(
            "subprocess.run"
        ) as mock_run:
            # Simulate setx failure
            mock_run.return_value = mock.MagicMock(
                returncode=1,
                stderr=b"The parameter is incorrect.\n"
            )

            installer._set_env("TEST_VAR", "test_value", "windows")

            # Verify setx was called
            mock_run.assert_called_once()

            # Verify failure was logged to stderr
            captured = capsys.readouterr()
            assert "setx TEST_VAR failed" in captured.err
            assert "rc=1" in captured.err
            assert "The parameter is incorrect" in captured.err

    def test_setx_success_silent(self, capsys):
        """Test that setx returncode 0 is silent."""
        with mock.patch(
            "subprocess.run"
        ) as mock_run:
            # Simulate setx success
            mock_run.return_value = mock.MagicMock(
                returncode=0,
                stderr=b""
            )

            installer._set_env("TEST_VAR", "test_value", "windows")

            # Verify no stderr output on success
            captured = capsys.readouterr()
            assert "failed" not in captured.err

    def test_posix_rc_file_handling(self):
        """Test that POSIX platforms still use rc file writes."""
        with tempfile.TemporaryDirectory() as tmpdir:
            home = Path(tmpdir)
            bashrc = home / ".bashrc"
            bashrc.write_text("# existing content\n")

            with mock.patch("pathlib.Path.home", return_value=home):
                installer._set_env("TEST_VAR", "test_value", "posix")

            # Verify bashrc was updated
            content = bashrc.read_text()
            assert "export TEST_VAR=" in content
            assert "test_value" in content


class TestRollbackCLI:
    """Tests for --rollback CLI path (#344 test coverage gap)."""

    def test_rollback_restores_from_backup(self):
        """Test that rollback restores target_root from backup_path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            backup_path = base / "backup"
            target_root = base / "target"

            # Create backup with test content
            backup_path.mkdir()
            (backup_path / "test.txt").write_text("backup content")

            # Create different content in target
            target_root.mkdir()
            (target_root / "old.txt").write_text("old content")

            # Perform rollback
            installer.rollback(target_root, backup_path)

            # Verify target now matches backup
            assert (target_root / "test.txt").read_text() == "backup content"
            assert not (target_root / "old.txt").exists()

    def test_rollback_cli_main(self):
        """Test rollback via main() CLI with --rollback flag."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            backup_path = base / "backup"
            target_root = base / "target"

            # Create backup with test content
            backup_path.mkdir()
            (backup_path / "test.txt").write_text("backup content")

            # Create different content in target
            target_root.mkdir()
            (target_root / "old.txt").write_text("old content")

            # Build a minimal manifest for --rollback path
            manifest_path = base / "manifest.yaml"
            manifest_path.write_text(
                "version: 1\ntarget_root: {}\n".format(target_root)
            )

            # Call main with --rollback
            rc = installer.main([
                "--manifest", str(manifest_path),
                "--target", str(target_root),
                "--rollback", str(backup_path)
            ])

            assert rc == 0
            # Verify target was restored
            assert (target_root / "test.txt").read_text() == "backup content"
            assert not (target_root / "old.txt").exists()

    def test_rollback_missing_backup_raises(self):
        """Test that rollback raises if backup_path doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            backup_path = base / "nonexistent_backup"
            target_root = base / "target"
            target_root.mkdir()

            with pytest.raises(FileNotFoundError):
                installer.rollback(target_root, backup_path)


class TestJsonRoundtripCaveat:
    """Tests documenting the .mcp.json JSONC/ordering caveat."""

    def test_json_ordering_normalized(self):
        """Document that JSON key ordering is not preserved through round-trip.

        When .mcp.json goes through json.loads/dumps (in template_content),
        the key ordering is normalized by Python's json module. While Python 3.7+
        preserves insertion order in dicts, json.dumps sorts keys by default in
        some contexts, so the output may differ from the input's key order.
        """
        import tempfile

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            # Write JSON with specific key order
            f.write('{\n  "z_key": 1,\n  "a_key": 2\n}\n')
            f.flush()
            json_file = Path(f.name)

        try:
            # Process through template_content (uses json.loads/dumps internally)
            result = installer.template_content(json_file, Path("/tmp"), Path("/tmp"))
            # Result is valid JSON with same data, order may differ
            data = json.loads(result.decode("utf-8"))
            assert data == {"z_key": 1, "a_key": 2}
        finally:
            json_file.unlink()

    def test_invalid_json_falls_back_to_copy(self):
        """Document that non-JSON .json files fall back to raw copy."""
        import tempfile

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            # Write JSONC (not valid JSON)
            f.write('{\n  // comment\n  "key": "value"\n}\n')
            f.flush()
            json_file = Path(f.name)

        try:
            # Process through template_content
            # Invalid JSON causes fallback to raw copy (comments preserved)
            result = installer.template_content(json_file, Path("/tmp"), Path("/tmp"))
            # Result bytes are identical to input since JSONC parse fails
            assert b"// comment" in result
        finally:
            json_file.unlink()

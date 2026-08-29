"""
Tests for InstallService (Task 14).
"""
from __future__ import annotations

import shutil
import tempfile
import re
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from tools.workflow_cli.install import InstallService, SCHEMA_VERSION
from tools.workflow_cli.version import R2P_VERSION

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).parent.parent


def make_service(tmp_path: Path) -> tuple[InstallService, Path, Path]:
    """Return (service, manifest_root, fake_platform_homes_root)."""
    manifest_root = tmp_path / "manifest"
    ph_root = tmp_path / "platforms"
    platform_homes = {
        "claude": ph_root / "claude",
        "codex": ph_root / "codex",
        "gemini": ph_root / "gemini",
        "opencode": ph_root / "opencode",
    }
    svc = InstallService(
        repo_root=REPO_ROOT,
        manifest_root=manifest_root,
        platform_homes=platform_homes,
    )
    return svc, manifest_root, ph_root


# ---------------------------------------------------------------------------
# Test class
# ---------------------------------------------------------------------------


class TestInstallService:

    # -----------------------------------------------------------------------
    # install — basic
    # -----------------------------------------------------------------------

    def test_install_creates_manifest(self, tmp_path):
        svc, manifest_root, _ = make_service(tmp_path)
        svc.install("claude")
        manifest_path = manifest_root / "install" / "claude.yaml"
        assert manifest_path.exists(), "manifest YAML should be created"

    def test_install_copies_skill_md(self, tmp_path):
        svc, manifest_root, ph_root = make_service(tmp_path)
        svc.install("claude")
        skill = ph_root / "claude" / "skills" / "r2p" / "SKILL.md"
        assert skill.exists(), "SKILL.md should be copied to platform home"

    def test_install_copies_command_files(self, tmp_path):
        svc, manifest_root, ph_root = make_service(tmp_path)
        svc.install("claude")
        cmds_dir = ph_root / "claude" / "commands"
        md_files = list(cmds_dir.glob("r2p-*.md"))
        assert len(md_files) > 0, "command *.md files should be copied"

    def test_install_renders_r2p_version_placeholder(self, tmp_path):
        svc, manifest_root, ph_root = make_service(tmp_path)
        svc.install("claude")
        skill = ph_root / "claude" / "skills" / "r2p" / "SKILL.md"
        content = skill.read_text()
        assert "{{R2P_VERSION}}" not in content, "placeholder should be replaced"
        assert R2P_VERSION in content, "version should appear in rendered file"

    def test_install_renders_r2p_bin_dir_placeholder(self, tmp_path):
        svc, manifest_root, ph_root = make_service(tmp_path)
        svc.install("claude")
        skill = ph_root / "claude" / "skills" / "r2p" / "SKILL.md"
        content = skill.read_text()
        assert "{{R2P_BIN_DIR}}" not in content, "bin dir placeholder should be replaced"
        bin_dir = str(manifest_root / "bin")
        assert bin_dir in content, "rendered bin dir path should appear in file"

    def test_install_claude_skill_qualifies_content_file_stops(self, tmp_path):
        svc, manifest_root, ph_root = make_service(tmp_path)
        svc.install("claude")
        skill = ph_root / "claude" / "skills" / "r2p" / "SKILL.md"
        content = skill.read_text()
        assert "content_file" in content
        assert "needs_content" in content
        assert "needs_repair" in content

    def test_install_renders_bin_script_with_source_repo_root(self, tmp_path):
        svc, manifest_root, _ = make_service(tmp_path)
        svc.install("claude")

        script = manifest_root / "bin" / "r2p-start"
        content = script.read_text()

        assert str(REPO_ROOT) in content
        assert 'REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"' not in content

    def test_install_backs_up_existing_file(self, tmp_path):
        svc, manifest_root, ph_root = make_service(tmp_path)
        # pre-create a file at the skill destination
        skill_dest = ph_root / "claude" / "skills" / "r2p" / "SKILL.md"
        skill_dest.parent.mkdir(parents=True, exist_ok=True)
        skill_dest.write_text("old content")

        svc.install("claude")

        manifest = yaml.safe_load(
            (manifest_root / "install" / "claude.yaml").read_text()
        )
        backup_entries = [b for b in manifest["backups"] if "SKILL.md" in b["target"]]
        assert len(backup_entries) == 1, "should record one backup for SKILL.md"
        backup_path = Path(backup_entries[0]["backup"])
        assert backup_path.exists(), "backup file should exist on disk"
        assert backup_path.read_text() == "old content"

    def test_install_rejects_symlinked_managed_target(self, tmp_path):
        svc, manifest_root, ph_root = make_service(tmp_path)
        skill_dest = ph_root / "claude" / "skills" / "r2p" / "SKILL.md"
        skill_dest.parent.mkdir(parents=True, exist_ok=True)
        victim = tmp_path / "victim.txt"
        victim.write_text("do not overwrite", encoding="utf-8")
        skill_dest.symlink_to(victim)

        with pytest.raises(ValueError, match="unsafe_install"):
            svc.install("claude")

        assert victim.read_text(encoding="utf-8") == "do not overwrite"
        assert not (manifest_root / "install" / "claude.yaml").exists()

    def test_install_rejects_symlink_below_platform_home(self, tmp_path):
        svc, manifest_root, ph_root = make_service(tmp_path)
        platform_home = ph_root / "claude"
        platform_home.mkdir(parents=True)
        escaped = tmp_path / "escaped-skills"
        escaped.mkdir()
        (platform_home / "skills").symlink_to(escaped, target_is_directory=True)

        with pytest.raises(ValueError, match="unsafe_install"):
            svc.install("claude")

        assert not (escaped / "r2p" / "SKILL.md").exists()
        assert not (manifest_root / "install" / "claude.yaml").exists()

    def test_install_rejects_symlinked_manifest_root_before_mkdir(self, tmp_path):
        manifest_link = tmp_path / "manifest"
        escaped_manifest = tmp_path / "escaped-manifest"
        escaped_manifest.mkdir()
        manifest_link.symlink_to(escaped_manifest, target_is_directory=True)
        ph_root = tmp_path / "platforms"
        svc = InstallService(
            repo_root=REPO_ROOT,
            manifest_root=manifest_link,
            platform_homes={
                "claude": ph_root / "claude",
                "codex": ph_root / "codex",
                "gemini": ph_root / "gemini",
            },
        )

        with pytest.raises(ValueError, match="unsafe_install"):
            svc.install("claude")

        assert not (escaped_manifest / "bin").exists()
        assert not (escaped_manifest / "install").exists()
        assert not (ph_root / "claude" / "skills" / "r2p" / "SKILL.md").exists()

    def test_install_rejects_symlinked_manifest_tmp(self, tmp_path):
        # Regression: the atomic manifest write goes through a unique-named temp
        # sibling. A planted symlink there must be rejected, or the atomic write
        # would follow it and redirect the manifest write outside the manifest dir.
        # Monkeypatch secrets.token_hex to a fixed value so we can plant a symlink
        # at the predictable temp path (.claude.yaml.<pid>.<token>.tmp).
        import os as _os
        import secrets as _secrets_mod
        svc, manifest_root, ph_root = make_service(tmp_path)
        install_dir = manifest_root / "install"
        install_dir.mkdir(parents=True)
        victim = tmp_path / "victim.txt"
        victim.write_text("do not overwrite", encoding="utf-8")
        fixed_token = "deadbeef12345678"
        manifest_path = install_dir / "claude.yaml"
        tmp_name = f".claude.yaml.{_os.getpid()}.{fixed_token}.tmp"
        (install_dir / tmp_name).symlink_to(victim)

        with patch.object(_secrets_mod, "token_hex", return_value=fixed_token):
            with pytest.raises(ValueError, match="unsafe_install"):
                svc.install("claude")

        assert victim.read_text(encoding="utf-8") == "do not overwrite"
        assert not manifest_path.exists()

    def test_write_manifest_atomic_writes_and_replaces(self, tmp_path):
        # Verify the new unique-temp helper: a normal install still writes the
        # manifest file with valid content (file exists, YAML parses, has expected
        # keys). This is the positive-path contract for _write_manifest_atomic.
        svc, manifest_root, _ = make_service(tmp_path)
        svc.install("claude")
        manifest_path = manifest_root / "install" / "claude.yaml"
        assert manifest_path.exists(), "_write_manifest_atomic must create the manifest"
        assert not manifest_path.is_symlink(), "manifest must be a regular file"
        data = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
        assert data["platform"] == "claude"
        assert isinstance(data["installed_paths"], list)
        assert len(data["installed_paths"]) > 0

    def test_strip_path_from_manifest_rejects_symlinked_manifest(self, tmp_path):
        # _strip_path_from_manifest now writes via _write_manifest_atomic, which
        # rejects a symlinked manifest instead of following it. A planted symlink
        # whose target references the stripped path must not be written through.
        from tools.workflow_cli.install import _load_manifest

        svc, manifest_root, _ = make_service(tmp_path)
        svc.install("claude")
        real_manifest = manifest_root / "install" / "claude.yaml"
        manifest_text = real_manifest.read_text(encoding="utf-8")
        target = _load_manifest(real_manifest)["installed_paths"][0]

        victim = tmp_path / "victim.yaml"
        victim.write_text(manifest_text, encoding="utf-8")
        link = manifest_root / "install" / "codex.yaml"
        link.symlink_to(victim)

        with pytest.raises(ValueError, match="unsafe_install"):
            svc._strip_path_from_manifest(link, target)

        assert link.is_symlink(), "planted manifest must remain a symlink"
        assert victim.read_text(encoding="utf-8") == manifest_text, (
            "symlink target must not be written through"
        )

    def test_strip_path_from_manifest_tolerates_non_dict_backup_entry(self, tmp_path):
        # A malformed (non-dict) backups entry — e.g. from a hand-edited or legacy
        # manifest — must not crash _strip_path_from_manifest with AttributeError.
        # The matching dict backup is still stripped; the malformed scalar survives.
        from tools.workflow_cli.install import _dump_manifest, _load_manifest

        svc, manifest_root, _ = make_service(tmp_path)
        svc.install("claude")
        manifest_path = manifest_root / "install" / "claude.yaml"
        manifest = _load_manifest(manifest_path)
        target = manifest["installed_paths"][0]
        manifest["backups"] = [{"target": target}, "not-a-dict-scalar"]
        manifest_path.write_text(_dump_manifest(manifest), encoding="utf-8")

        # Must not raise; previously raised AttributeError on the scalar entry.
        svc._strip_path_from_manifest(manifest_path, target)

        result = _load_manifest(manifest_path)
        assert target not in result["installed_paths"], "target must be stripped"
        assert result["backups"] == ["not-a-dict-scalar"], (
            "matching dict backup removed, malformed scalar preserved"
        )

    def test_obsolete_wrapper_cleanup_tolerates_symlinked_manifest(self, tmp_path):
        # A symlinked (unsafe) manifest sitting in install/ must neither be written
        # through nor abort cleanup of the remaining valid manifests. The valid
        # codex manifest's obsolete reference is still stripped; the symlinked
        # claude manifest (sorted first) raises ValueError that the loop tolerates.
        from tools.workflow_cli.install import _dump_manifest, _load_manifest

        svc, manifest_root, _ = make_service(tmp_path)
        svc.install("codex")
        bin_dir = manifest_root / "bin"
        bin_dir.mkdir(parents=True, exist_ok=True)
        stale = bin_dir / "r2p-adapt"
        stale.write_text("MANAGED WRAPPER\n", encoding="utf-8")

        valid_mpath = manifest_root / "install" / "codex.yaml"
        valid_manifest = _load_manifest(valid_mpath)
        valid_manifest.setdefault("installed_paths", []).append(str(stale))
        valid_mpath.write_text(_dump_manifest(valid_manifest), encoding="utf-8")

        victim = tmp_path / "victim-claude.yaml"
        victim.write_text(
            _dump_manifest(
                {
                    "backups": [],
                    "installed_at": "x",
                    "installed_paths": [str(stale)],
                    "platform": "claude",
                    "r2p_version": "x",
                    "schema_version": SCHEMA_VERSION,
                }
            ),
            encoding="utf-8",
        )
        victim_text = victim.read_text(encoding="utf-8")
        link = manifest_root / "install" / "claude.yaml"
        link.symlink_to(victim)

        # Must complete without raising despite the symlinked manifest.
        svc._cleanup_obsolete_managed_wrappers()

        assert str(stale) not in _load_manifest(valid_mpath).get(
            "installed_paths", []
        ), "valid manifest's obsolete reference must still be stripped"
        assert link.is_symlink(), "planted manifest must remain a symlink"
        assert victim.read_text(encoding="utf-8") == victim_text, (
            "symlinked manifest target must not be written through"
        )

    def test_install_removes_manifest_when_post_manifest_cleanup_fails(self, tmp_path):
        svc, manifest_root, ph_root = make_service(tmp_path)
        manifest_path = manifest_root / "install" / "claude.yaml"

        with patch.object(
            svc,
            "_cleanup_obsolete_managed_wrappers",
            side_effect=RuntimeError("cleanup failed"),
        ):
            with pytest.raises(RuntimeError, match="cleanup failed"):
                svc.install("claude")

        assert not manifest_path.exists()
        assert not (manifest_root / "bin" / "r2p-start").exists()
        assert not (ph_root / "claude" / "skills" / "r2p" / "SKILL.md").exists()

    def test_install_restores_prior_install_when_reinstall_cleanup_fails(
        self, tmp_path
    ):
        svc, manifest_root, ph_root = make_service(tmp_path)
        from tools.workflow_cli import install as install_mod

        manifest_path = manifest_root / "install" / "claude.yaml"
        skill_dest = ph_root / "claude" / "skills" / "r2p" / "SKILL.md"
        skill_dest.parent.mkdir(parents=True, exist_ok=True)
        skill_dest.write_text("original user skill", encoding="utf-8")
        svc.install("claude")
        manifest_before = manifest_path.read_text(encoding="utf-8")
        skill_before = skill_dest.read_text(encoding="utf-8")
        cleanup_calls = [0]

        def fail_after_reinstall_uninstall(*args, **kwargs):
            cleanup_calls[0] += 1
            if cleanup_calls[0] > 1:
                raise RuntimeError("cleanup failed")

        with patch.object(
            svc,
            "_cleanup_obsolete_managed_wrappers",
            side_effect=fail_after_reinstall_uninstall,
        ), patch.object(install_mod, "R2P_VERSION", "v-reinstall"):
            with pytest.raises(RuntimeError, match="cleanup failed"):
                svc.install("claude")

        assert cleanup_calls[0] == 2
        assert manifest_path.read_text(encoding="utf-8") == manifest_before
        assert skill_dest.read_text(encoding="utf-8") == skill_before

        svc.uninstall("claude")

        assert skill_dest.read_text(encoding="utf-8") == "original user skill"

    def test_failed_reinstall_removes_new_backups_before_restoring_manifest(
        self, tmp_path
    ):
        svc, manifest_root, ph_root = make_service(tmp_path)
        from tools.workflow_cli import install as install_mod

        manifest_path = manifest_root / "install" / "claude.yaml"
        backup_dir = manifest_root / "install" / "backups" / "claude"
        skill_dest = ph_root / "claude" / "skills" / "r2p" / "SKILL.md"
        skill_dest.parent.mkdir(parents=True, exist_ok=True)
        skill_dest.write_text("original user skill", encoding="utf-8")
        cleanup_calls = [0]

        def fail_after_reinstall_uninstall(*args, **kwargs):
            cleanup_calls[0] += 1
            if cleanup_calls[0] > 1:
                raise RuntimeError("cleanup failed")

        with patch.object(
            install_mod,
            "_now_ts",
            side_effect=["20260601T000000", "20260602T000000"],
        ):
            svc.install("claude")
            prior_manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
            prior_backups = {Path(bk["backup"]) for bk in prior_manifest["backups"]}

            with patch.object(
                svc,
                "_cleanup_obsolete_managed_wrappers",
                side_effect=fail_after_reinstall_uninstall,
            ), patch.object(install_mod, "R2P_VERSION", "v-reinstall"):
                with pytest.raises(RuntimeError, match="cleanup failed"):
                    svc.install("claude")

        assert cleanup_calls[0] == 2
        assert {
            path for path in backup_dir.iterdir() if path.is_file()
        } == prior_backups
        assert all("20260602T000000" not in path.name for path in backup_dir.iterdir())
        assert (
            yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
            == prior_manifest
        )

        svc.uninstall("claude")

        assert skill_dest.read_text(encoding="utf-8") == "original user skill"
        assert not backup_dir.exists()

    def test_reinstall_rejects_symlinked_backup_dir_before_uninstall(
        self, tmp_path
    ):
        svc, manifest_root, ph_root = make_service(tmp_path)
        svc.install("claude")
        manifest_path = manifest_root / "install" / "claude.yaml"
        manifest_before = manifest_path.read_text(encoding="utf-8")
        skill_dest = ph_root / "claude" / "skills" / "r2p" / "SKILL.md"
        skill_before = skill_dest.read_text(encoding="utf-8")
        backup_dir = manifest_root / "install" / "backups" / "claude"
        outside_backups = tmp_path / "outside-backups"
        outside_backups.mkdir()
        backup_dir.parent.mkdir(parents=True, exist_ok=True)
        backup_dir.symlink_to(outside_backups, target_is_directory=True)

        with pytest.raises(ValueError, match="unsafe_install"):
            svc.install("claude")

        assert manifest_path.read_text(encoding="utf-8") == manifest_before
        assert skill_dest.read_text(encoding="utf-8") == skill_before

    def test_install_keeps_backups_unique_for_same_named_targets(self, tmp_path):
        svc, manifest_root, ph_root = make_service(tmp_path)
        first = ph_root / "codex" / "skills" / "r2p-start" / "SKILL.md"
        second = ph_root / "codex" / "skills" / "r2p-continue" / "SKILL.md"
        first.parent.mkdir(parents=True, exist_ok=True)
        second.parent.mkdir(parents=True, exist_ok=True)
        first.write_text("original start", encoding="utf-8")
        second.write_text("original continue", encoding="utf-8")

        with patch("tools.workflow_cli.install._now_ts", return_value="20260602T000000"):
            svc.install("codex")

        manifest = yaml.safe_load(
            (manifest_root / "install" / "codex.yaml").read_text()
        )
        target_backups = [
            b for b in manifest["backups"] if b["target"] in {str(first), str(second)}
        ]
        backup_paths = [b["backup"] for b in target_backups]

        assert len(target_backups) == 2
        assert len(set(backup_paths)) == 2

        svc.uninstall("codex")

        assert first.read_text(encoding="utf-8") == "original start"
        assert second.read_text(encoding="utf-8") == "original continue"

    def test_install_rollback_on_failure(self, tmp_path):
        svc, manifest_root, ph_root = make_service(tmp_path)

        # Patch _safe_write so it fails after the first successful write
        from tools.workflow_cli import install as install_mod

        real_safe_write = install_mod._safe_write
        call_count = [0]

        def failing_safe_write(dest, content, backups, installed_paths, written, backup_dir):
            call_count[0] += 1
            if call_count[0] > 1:
                raise OSError("simulated write failure")
            real_safe_write(dest, content, backups, installed_paths, written, backup_dir)

        with patch.object(install_mod, "_safe_write", side_effect=failing_safe_write):
            with pytest.raises(OSError):
                svc.install("claude")

        # After rollback, nothing should remain in the platform home except the
        # directory structure (dirs may be created but no files from install)
        # The first written file should have been removed
        for f in (ph_root / "claude").rglob("*"):
            if f.is_file():
                pytest.fail(f"Rollback should have removed {f}")

    def test_install_unknown_platform_raises(self, tmp_path):
        svc, _, _ = make_service(tmp_path)
        with pytest.raises(ValueError, match="Unknown platform"):
            svc.install("nonexistent-platform")

    def test_reinstall_overwrites_without_confirm(self, tmp_path):
        svc, manifest_root, _ = make_service(tmp_path)
        svc.install("claude")
        # Reinstall must just succeed (overwrite); no confirm flag needed.
        svc.install("claude")
        manifest_path = manifest_root / "install" / "claude.yaml"
        assert manifest_path.exists()

    def test_reinstall_preserves_original_backup_state(self, tmp_path):
        svc, manifest_root, ph_root = make_service(tmp_path)
        skill_dest = ph_root / "claude" / "skills" / "r2p" / "SKILL.md"
        skill_dest.parent.mkdir(parents=True, exist_ok=True)
        skill_dest.write_text("original content")

        svc.install("claude")
        svc.install("claude")
        svc.uninstall("claude")

        assert skill_dest.exists()
        assert skill_dest.read_text() == "original content"

    def test_reinstall_uninstall_does_not_leave_managed_files(self, tmp_path):
        svc, manifest_root, ph_root = make_service(tmp_path)
        svc.install("claude")
        skill_dest = ph_root / "claude" / "skills" / "r2p" / "SKILL.md"
        assert skill_dest.exists()

        svc.install("claude")
        svc.uninstall("claude")

        assert not skill_dest.exists()

    def test_reinstall_preserves_unmanaged_bin_files(self, tmp_path):
        svc, manifest_root, _ = make_service(tmp_path)
        svc.install("claude")
        unmanaged = manifest_root / "bin" / "r2p-local-helper"
        unmanaged.write_text("user helper\n", encoding="utf-8")

        svc.install("claude")

        assert unmanaged.exists()
        assert unmanaged.read_text(encoding="utf-8") == "user helper\n"

    def test_install_copies_bin_scripts(self, tmp_path):
        svc, manifest_root, _ = make_service(tmp_path)
        svc.install("claude")
        bin_dir = manifest_root / "bin"
        r2p_scripts = list(bin_dir.glob("r2p-*"))
        assert len(r2p_scripts) > 0, "bin scripts should be copied"

    def test_manifest_contains_schema_version(self, tmp_path):
        svc, manifest_root, _ = make_service(tmp_path)
        svc.install("claude")
        manifest = yaml.safe_load(
            (manifest_root / "install" / "claude.yaml").read_text()
        )
        assert manifest["schema_version"] == SCHEMA_VERSION

    def test_manifest_contains_platform(self, tmp_path):
        svc, manifest_root, _ = make_service(tmp_path)
        svc.install("codex")
        manifest = yaml.safe_load(
            (manifest_root / "install" / "codex.yaml").read_text()
        )
        assert manifest["platform"] == "codex"

    def test_manifest_contains_r2p_version(self, tmp_path):
        svc, manifest_root, _ = make_service(tmp_path)
        svc.install("claude")
        manifest = yaml.safe_load(
            (manifest_root / "install" / "claude.yaml").read_text()
        )
        assert manifest["r2p_version"] == R2P_VERSION

    def test_manifest_contains_installed_paths(self, tmp_path):
        svc, manifest_root, _ = make_service(tmp_path)
        svc.install("claude")
        manifest = yaml.safe_load(
            (manifest_root / "install" / "claude.yaml").read_text()
        )
        assert isinstance(manifest["installed_paths"], list)
        assert len(manifest["installed_paths"]) > 0

    # -----------------------------------------------------------------------
    # uninstall
    # -----------------------------------------------------------------------

    def test_uninstall_removes_installed_paths(self, tmp_path):
        svc, manifest_root, ph_root = make_service(tmp_path)
        svc.install("claude")
        skill = ph_root / "claude" / "skills" / "r2p" / "SKILL.md"
        assert skill.exists()

        svc.uninstall("claude")
        assert not skill.exists(), "SKILL.md should be removed after uninstall"

    def test_uninstall_restores_backup(self, tmp_path):
        svc, manifest_root, ph_root = make_service(tmp_path)
        # pre-create a file that will be backed up
        skill_dest = ph_root / "claude" / "skills" / "r2p" / "SKILL.md"
        skill_dest.parent.mkdir(parents=True, exist_ok=True)
        skill_dest.write_text("original content")

        svc.install("claude")
        assert skill_dest.read_text() != "original content"

        svc.uninstall("claude")
        assert skill_dest.exists(), "restored file should exist"
        assert skill_dest.read_text() == "original content", "content should be restored"

    def test_uninstall_rejects_manifest_installed_path_outside_managed_roots(self, tmp_path):
        svc, manifest_root, _ = make_service(tmp_path)
        svc.install("claude")
        victim = tmp_path / "victim.txt"
        victim.write_text("do not delete", encoding="utf-8")

        from tools.workflow_cli.install import _dump_manifest, _load_manifest

        manifest_path = manifest_root / "install" / "claude.yaml"
        manifest = _load_manifest(manifest_path)
        manifest["installed_paths"].append(str(victim))
        manifest_path.write_text(_dump_manifest(manifest), encoding="utf-8")

        with pytest.raises(ValueError, match="unsafe_manifest"):
            svc.uninstall("claude")

        assert victim.exists()
        assert victim.read_text(encoding="utf-8") == "do not delete"

    def test_uninstall_rejects_manifest_target_matching_symlinked_managed_path(self, tmp_path):
        svc, manifest_root, _ = make_service(tmp_path)
        svc.install("claude")
        managed_target = manifest_root / "bin" / "r2p-start"
        managed_target.unlink()
        victim = tmp_path / "victim.txt"
        victim.write_text("do not delete", encoding="utf-8")
        managed_target.symlink_to(victim)

        from tools.workflow_cli.install import _dump_manifest, _load_manifest

        manifest_path = manifest_root / "install" / "claude.yaml"
        manifest = _load_manifest(manifest_path)
        manifest["installed_paths"] = [
            path for path in manifest["installed_paths"] if path != str(managed_target)
        ]
        manifest["installed_paths"].append(str(victim))
        manifest_path.write_text(_dump_manifest(manifest), encoding="utf-8")

        with pytest.raises(ValueError, match="unsafe_manifest"):
            svc.uninstall("claude")

        assert victim.exists()
        assert victim.read_text(encoding="utf-8") == "do not delete"

    def test_uninstall_rejects_manifest_backup_source_outside_backup_dir(self, tmp_path):
        svc, manifest_root, _ = make_service(tmp_path)
        svc.install("claude")
        malicious_backup = tmp_path / "outside.bak"
        malicious_backup.write_text("malicious restore", encoding="utf-8")

        from tools.workflow_cli.install import _dump_manifest, _load_manifest

        manifest_path = manifest_root / "install" / "claude.yaml"
        manifest = _load_manifest(manifest_path)
        target = manifest["installed_paths"][0]
        manifest.setdefault("backups", []).append(
            {"target": target, "backup": str(malicious_backup)}
        )
        manifest_path.write_text(_dump_manifest(manifest), encoding="utf-8")

        with pytest.raises(ValueError, match="unsafe_manifest"):
            svc.uninstall("claude")

        assert malicious_backup.exists()

    def test_uninstall_rejects_symlinked_backup_directory(self, tmp_path):
        svc, manifest_root, _ = make_service(tmp_path)
        svc.install("claude")
        backup_root = manifest_root / "install" / "backups"
        backup_root.mkdir(parents=True, exist_ok=True)
        backup_dir = backup_root / "claude"
        if backup_dir.exists():
            backup_dir.rmdir()
        outside_backups = tmp_path / "outside-backups"
        outside_backups.mkdir()
        backup_dir.symlink_to(outside_backups, target_is_directory=True)
        malicious_backup = backup_dir / "outside.bak"
        malicious_backup.write_text("malicious restore", encoding="utf-8")

        from tools.workflow_cli.install import _dump_manifest, _load_manifest

        manifest_path = manifest_root / "install" / "claude.yaml"
        manifest = _load_manifest(manifest_path)
        target = manifest["installed_paths"][0]
        manifest.setdefault("backups", []).append(
            {"target": target, "backup": str(malicious_backup)}
        )
        manifest_path.write_text(_dump_manifest(manifest), encoding="utf-8")

        with pytest.raises(ValueError, match="unsafe_manifest"):
            svc.uninstall("claude")

        assert (outside_backups / "outside.bak").exists()

    def test_uninstall_rejects_backup_path_with_symlink_then_parent_ref(self, tmp_path):
        svc, manifest_root, _ = make_service(tmp_path)
        svc.install("claude")
        backup_dir = manifest_root / "install" / "backups" / "claude"
        backup_dir.mkdir(parents=True, exist_ok=True)
        outside_parent = tmp_path / "outside-parent"
        outside_child = outside_parent / "child"
        outside_child.mkdir(parents=True)
        symlink = backup_dir / "link"
        symlink.symlink_to(outside_child, target_is_directory=True)
        victim = outside_parent / "victim.bak"
        victim.write_text("malicious restore", encoding="utf-8")
        malicious_backup = backup_dir / "link" / ".." / "victim.bak"

        from tools.workflow_cli.install import _dump_manifest, _load_manifest

        manifest_path = manifest_root / "install" / "claude.yaml"
        manifest = _load_manifest(manifest_path)
        target = manifest["installed_paths"][0]
        manifest.setdefault("backups", []).append(
            {"target": target, "backup": str(malicious_backup)}
        )
        manifest_path.write_text(_dump_manifest(manifest), encoding="utf-8")

        with pytest.raises(ValueError, match="unsafe_manifest"):
            svc.uninstall("claude")

        assert victim.exists()
        assert victim.read_text(encoding="utf-8") == "malicious restore"

    def test_validate_backup_path_rejects_symlinked_manifest_root(self, tmp_path):
        actual_manifest_root = tmp_path / "actual-manifest"
        actual_manifest_root.mkdir()
        manifest_root = tmp_path / "manifest-link"
        manifest_root.symlink_to(actual_manifest_root, target_is_directory=True)
        ph_root = tmp_path / "platforms"
        svc = InstallService(
            repo_root=REPO_ROOT,
            manifest_root=manifest_root,
            platform_homes={
                "claude": ph_root / "claude",
                "codex": ph_root / "codex",
                "gemini": ph_root / "gemini",
            },
        )
        backup_dir = manifest_root / "install" / "backups" / "claude"
        backup_dir.mkdir(parents=True, exist_ok=True)
        backup = backup_dir / "r2p-start.bak"
        backup.write_text("malicious restore", encoding="utf-8")

        with pytest.raises(ValueError, match="unsafe_manifest"):
            svc._validate_backup_path("claude", str(backup), field="backups[0].backup")

        assert backup.exists()

    def test_uninstall_tolerates_symlinked_platform_home(self, tmp_path):
        # A user may symlink ~/.claude via a dotfile manager (stow/chezmoi).
        # The managed install/uninstall must still work through that symlink —
        # the platform home is an operator-trusted root, not an injected symlink.
        real_home = tmp_path / "real-claude"
        real_home.mkdir()
        link_home = tmp_path / "link-claude"
        link_home.symlink_to(real_home, target_is_directory=True)
        ph_root = tmp_path / "platforms"
        svc = InstallService(
            repo_root=REPO_ROOT,
            manifest_root=tmp_path / "manifest",
            platform_homes={
                "claude": link_home,
                "codex": ph_root / "codex",
                "gemini": ph_root / "gemini",
            },
        )
        svc.install("claude")
        skill = real_home / "skills" / "r2p" / "SKILL.md"
        assert skill.exists()

        result = svc.uninstall("claude")

        assert not skill.exists()
        assert any("SKILL.md" in p for p in result["removed"])

    def test_uninstall_still_rejects_symlink_below_platform_home(self, tmp_path):
        # Trusting the platform home itself must not extend to symlinks the
        # attacker injects *inside* it: an intermediate managed dir swapped for
        # a symlink would let a managed target escape, so it stays rejected.
        svc, manifest_root, ph_root = make_service(tmp_path)
        svc.install("claude")
        real_skills = ph_root / "claude" / "skills"
        escaped = tmp_path / "escaped-skills"
        shutil.move(str(real_skills), str(escaped))
        real_skills.symlink_to(escaped, target_is_directory=True)

        with pytest.raises(ValueError, match="unsafe_manifest"):
            svc.uninstall("claude")

    def test_uninstall_rejects_manifest_backup_target_outside_managed_roots(self, tmp_path):
        svc, manifest_root, _ = make_service(tmp_path)
        svc.install("claude")
        victim = tmp_path / "victim.txt"
        victim.write_text("do not overwrite", encoding="utf-8")
        backup_dir = manifest_root / "install" / "backups" / "claude"
        backup_dir.mkdir(parents=True, exist_ok=True)
        backup = backup_dir / "victim.bak"
        backup.write_text("malicious restore", encoding="utf-8")

        from tools.workflow_cli.install import _dump_manifest, _load_manifest

        manifest_path = manifest_root / "install" / "claude.yaml"
        manifest = _load_manifest(manifest_path)
        manifest.setdefault("backups", []).append(
            {"target": str(victim), "backup": str(backup)}
        )
        manifest_path.write_text(_dump_manifest(manifest), encoding="utf-8")

        with pytest.raises(ValueError, match="unsafe_manifest"):
            svc.uninstall("claude")

        assert victim.read_text(encoding="utf-8") == "do not overwrite"

    @pytest.mark.parametrize(
        ("platform", "obsolete_parts"),
        [
            ("claude", ("commands", "r2p-adapt.md")),
            ("codex", ("skills", "r2p-adapt", "SKILL.md")),
            ("gemini", ("commands", "r2p-adapt.toml")),
        ],
    )
    def test_uninstall_removes_known_obsolete_platform_adapt_targets(
        self, tmp_path, platform, obsolete_parts
    ):
        svc, manifest_root, ph_root = make_service(tmp_path)
        svc.install(platform)
        obsolete_target = (ph_root / platform).joinpath(*obsolete_parts)
        obsolete_target.parent.mkdir(parents=True, exist_ok=True)
        obsolete_target.write_text("old adapt command", encoding="utf-8")

        from tools.workflow_cli.install import _dump_manifest, _load_manifest

        manifest_path = manifest_root / "install" / f"{platform}.yaml"
        manifest = _load_manifest(manifest_path)
        manifest["installed_paths"].append(str(obsolete_target))
        manifest_path.write_text(_dump_manifest(manifest), encoding="utf-8")

        result = svc.uninstall(platform)

        assert str(obsolete_target) in result["removed"]
        assert not obsolete_target.exists()

    def test_install_preserves_other_manifest_referenced_unmanaged_bin_r2p_file(self, tmp_path):
        svc, manifest_root, _ = make_service(tmp_path)
        svc.install("claude")
        unmanaged = manifest_root / "bin" / "r2p-local"
        unmanaged.write_text("user helper\n", encoding="utf-8")

        from tools.workflow_cli.install import _dump_manifest

        manifest_path = manifest_root / "install" / "codex.yaml"
        manifest = {
            "backups": [],
            "installed_at": "2026-06-04T00:00:00+00:00",
            "installed_paths": [str(unmanaged)],
            "platform": "codex",
            "r2p_version": R2P_VERSION,
            "schema_version": SCHEMA_VERSION,
        }
        manifest_path.write_text(_dump_manifest(manifest), encoding="utf-8")

        svc.install("gemini")

        assert unmanaged.exists()
        assert unmanaged.read_text(encoding="utf-8") == "user helper\n"

    def test_uninstall_fails_when_no_manifest(self, tmp_path):
        svc, _, _ = make_service(tmp_path)
        with pytest.raises(FileNotFoundError):
            svc.uninstall("claude")

    def test_uninstall_removes_bin_dir_when_last_platform(self, tmp_path):
        svc, manifest_root, _ = make_service(tmp_path)
        svc.install("claude")
        bin_dir = manifest_root / "bin"
        assert bin_dir.exists()

        svc.uninstall("claude")
        assert not bin_dir.exists(), "bin dir should be removed when last platform uninstalls"

    def test_uninstall_preserves_bin_dir_when_other_platforms_installed(self, tmp_path):
        svc, manifest_root, _ = make_service(tmp_path)
        svc.install("claude")
        svc.install("codex")

        bin_dir = manifest_root / "bin"
        assert bin_dir.exists()

        svc.uninstall("claude")
        assert bin_dir.exists(), "bin dir should remain because codex is still installed"

        # cleanup
        svc.uninstall("codex")
        assert not bin_dir.exists(), "bin dir removed after last platform gone"

    def test_uninstall_removes_context_view_wrapper_after_final_shared_platform(self, tmp_path):
        svc, manifest_root, _ = make_service(tmp_path)
        svc.install("codex")
        svc.install("claude")
        wrapper = manifest_root / "bin" / "r2p-context-view"
        assert wrapper.exists()

        svc.uninstall("claude")
        assert wrapper.exists(), "shared wrapper must remain for codex"

        svc.uninstall("codex")
        assert not wrapper.exists(), "managed context-view wrapper must not be restored"
        assert not (manifest_root / "bin").exists()

    def test_uninstall_restores_user_context_view_comment_script_byte_identically(self, tmp_path):
        svc, manifest_root, _ = make_service(tmp_path)
        wrapper = manifest_root / "bin" / "r2p-context-view"
        wrapper.parent.mkdir(parents=True)
        user_script = (
            b'#!/usr/bin/env bash\n'
            b'set -euo pipefail\n'
            b'SCRIPT_DIR="$(cd "$(dirname "$' b'{BASH_SOURCE[0]}")" && pwd)"\n'
            b'REPO_ROOT=/user/owned/script\n'
            b'# exec python3 -E "$REPO_ROOT/tools/workflow_cli/__main__.py" '
            b'tools.workflow_cli context-view "$@"\n'
            b"printf 'user-owned wrapper\\n'\n"
        )
        wrapper.write_bytes(user_script)

        svc.install("claude")
        svc.install("codex")
        svc.uninstall("claude")
        svc.uninstall("codex")

        assert wrapper.read_bytes() == user_script

    def test_uninstall_preserves_shared_bin_scripts_when_other_platforms_installed(self, tmp_path):
        svc, manifest_root, _ = make_service(tmp_path)
        svc.install("claude")
        svc.install("codex")

        script = manifest_root / "bin" / "r2p-start"
        assert script.exists()

        svc.uninstall("claude")

        assert script.exists(), "shared bin scripts should remain for codex install"

    def test_uninstall_defers_shared_bin_user_backup_until_final_platform(self, tmp_path):
        svc, manifest_root, _ = make_service(tmp_path)
        script = manifest_root / "bin" / "r2p-start"
        script.parent.mkdir(parents=True, exist_ok=True)
        script.write_text("USER ORIGINAL\n", encoding="utf-8")

        svc.install("claude")
        assert script.read_text(encoding="utf-8") != "USER ORIGINAL\n"

        svc.install("codex")
        svc.uninstall("claude")

        assert script.exists(), "shared wrapper must remain managed while codex is installed"
        assert script.read_text(encoding="utf-8") != "USER ORIGINAL\n"

        from tools.workflow_cli.install import _load_manifest
        codex_manifest = _load_manifest(manifest_root / "install" / "codex.yaml")
        transferred = [
            bk for bk in codex_manifest.get("backups", [])
            if isinstance(bk, dict) and bk.get("target") == str(script)
        ]
        assert any(
            Path(bk["backup"]).read_text(encoding="utf-8") == "USER ORIGINAL\n"
            for bk in transferred
        ), "user backup should be transferred to the remaining platform manifest"

        result = svc.uninstall("codex")

        assert str(script) in result["restored"]
        assert script.exists(), "final uninstall must restore the user's original wrapper"
        assert script.read_text(encoding="utf-8") == "USER ORIGINAL\n"

    # -----------------------------------------------------------------------
    # status
    # -----------------------------------------------------------------------

    def test_status_returns_empty_when_none(self, tmp_path):
        svc, _, _ = make_service(tmp_path)
        assert svc.status() == []

    def test_status_returns_platform_info(self, tmp_path):
        svc, _, _ = make_service(tmp_path)
        svc.install("claude")
        result = svc.status()
        assert len(result) == 1
        assert result[0]["platform"] == "claude"
        assert result[0]["r2p_version"] == R2P_VERSION
        assert result[0]["schema_version"] == SCHEMA_VERSION
        assert result[0]["status"] == "ok"
        assert result[0]["issues"] == []

    def test_status_returns_multiple_platforms(self, tmp_path):
        svc, _, _ = make_service(tmp_path)
        svc.install("claude")
        svc.install("codex")
        platforms = {r["platform"] for r in svc.status()}
        assert "claude" in platforms
        assert "codex" in platforms

    def test_status_reports_missing_file_as_drift(self, tmp_path):
        svc, manifest_root, ph_root = make_service(tmp_path)
        svc.install("claude")
        skill = ph_root / "claude" / "skills" / "r2p" / "SKILL.md"
        skill.unlink()

        result = svc.status()
        assert len(result) == 1
        assert result[0]["status"] == "drift"
        assert any("missing_file" in issue for issue in result[0]["issues"])

    def test_status_reports_version_mismatch_as_drift(self, tmp_path):
        svc, manifest_root, _ = make_service(tmp_path)
        svc.install("claude")

        manifest_path = manifest_root / "install" / "claude.yaml"
        data = yaml.safe_load(manifest_path.read_text())
        data["r2p_version"] = "v0-old"
        manifest_path.write_text(yaml.dump(data, default_flow_style=False, sort_keys=True))

        result = svc.status()
        assert len(result) == 1
        assert result[0]["status"] == "drift"
        assert any("version_mismatch" in issue for issue in result[0]["issues"])

    def test_status_reports_invalid_on_malformed_manifest(self, tmp_path):
        svc, manifest_root, _ = make_service(tmp_path)
        svc.install("claude")

        # A partial/truncated write can still parse but be wrong-shaped.
        manifest_path = manifest_root / "install" / "claude.yaml"
        manifest_path.write_text('{"platform": "claude"}')

        result = svc.status()
        assert len(result) == 1
        assert result[0]["status"] == "invalid"
        assert result[0]["issues"]

    @pytest.mark.parametrize(
        ("field", "value", "expected_issue"),
        [
            ("backups", "corrupt", "backups_not_a_list"),
            ("installed_paths", [123], "installed_paths[0]_not_a_string"),
            ("backups", ["corrupt"], "backups[0]_not_a_mapping"),
            (
                "backups",
                [{"target": 123, "backup": []}],
                "backups[0].target_not_a_string",
            ),
        ],
    )
    def test_status_reports_invalid_on_nested_manifest_shape(
        self, tmp_path, field, value, expected_issue
    ):
        svc, manifest_root, _ = make_service(tmp_path)
        svc.install("claude")
        manifest_path = manifest_root / "install" / "claude.yaml"
        data = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
        data[field] = value
        manifest_path.write_text(
            yaml.safe_dump(data, default_flow_style=False, sort_keys=True),
            encoding="utf-8",
        )

        result = svc.status()

        assert result[0]["status"] == "invalid"
        assert any(expected_issue in issue for issue in result[0]["issues"])

    @pytest.mark.parametrize(
        ("updates", "removed_field", "expected_issue"),
        [
            ({}, "installed_at", "missing_installed_at"),
            ({"installed_at": ""}, None, "installed_at_empty"),
            ({"schema_version": "1"}, None, "schema_version_not_an_integer"),
            ({"r2p_version": 123}, None, "r2p_version_not_a_string"),
        ],
    )
    def test_status_reports_invalid_on_manifest_scalar_shape(
        self, tmp_path, updates, removed_field, expected_issue
    ):
        svc, manifest_root, _ = make_service(tmp_path)
        svc.install("claude")
        manifest_path = manifest_root / "install" / "claude.yaml"
        data = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
        data.update(updates)
        if removed_field is not None:
            data.pop(removed_field)
        from tools.workflow_cli.install import _dump_manifest

        manifest_path.write_text(
            _dump_manifest(data),
            encoding="utf-8",
        )

        result = svc.status()

        assert result[0]["status"] == "invalid"
        assert any(expected_issue in issue for issue in result[0]["issues"])

    def _rewrite_schema_version(self, manifest_path: Path, new_version: int) -> None:
        from tools.workflow_cli.install import _dump_manifest

        data = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
        data["schema_version"] = new_version
        manifest_path.write_text(_dump_manifest(data), encoding="utf-8")

    def test_status_reports_schema_mismatch_as_drift_not_invalid(self, tmp_path):
        svc, manifest_root, _ = make_service(tmp_path)
        svc.install("claude")
        manifest_path = manifest_root / "install" / "claude.yaml"
        self._rewrite_schema_version(manifest_path, SCHEMA_VERSION + 1)

        result = svc.status()

        # A structurally valid manifest whose schema_version differs is drift,
        # not invalid — otherwise it would be un-uninstallable.
        assert result[0]["status"] == "drift"
        assert any("unsupported_schema_version" in issue for issue in result[0]["issues"])

    def test_uninstall_succeeds_on_schema_version_mismatch(self, tmp_path):
        svc, manifest_root, ph_root = make_service(tmp_path)
        svc.install("claude")
        skill_dest = ph_root / "claude" / "skills" / "r2p" / "SKILL.md"
        assert skill_dest.exists()
        manifest_path = manifest_root / "install" / "claude.yaml"
        self._rewrite_schema_version(manifest_path, SCHEMA_VERSION + 1)

        # A future schema bump must not strand a prior install: uninstall must
        # still validate the manifest and remove managed files.
        svc.uninstall("claude")

        assert not skill_dest.exists()
        assert not manifest_path.exists()

    def test_status_reports_invalid_on_unparseable_manifest(self, tmp_path):
        svc, manifest_root, _ = make_service(tmp_path)
        svc.install("claude")

        manifest_path = manifest_root / "install" / "claude.yaml"
        manifest_path.write_text(": : not valid : :\n\tbad")

        result = svc.status()
        assert len(result) == 1
        assert result[0]["status"] == "invalid"

    def test_status_returns_empty_when_nothing_installed(self, tmp_path):
        svc, _, _ = make_service(tmp_path)
        assert svc.status() == []

    # -----------------------------------------------------------------------
    # codex and gemini platforms
    # -----------------------------------------------------------------------

    def test_install_codex_copies_shortcut_skills(self, tmp_path):
        svc, manifest_root, ph_root = make_service(tmp_path)
        svc.install("codex")
        for command in [
            "r2p-continue",
            "r2p-reopen",
            "r2p-start",
            "r2p-status",
            "r2p-switch",
            "r2p-tier-lock",
        ]:
            skill = ph_root / "codex" / "skills" / command / "SKILL.md"
            assert skill.exists(), f"{command} SKILL.md should be installed for codex"

    def test_install_gemini_copies_toml_commands(self, tmp_path):
        svc, manifest_root, ph_root = make_service(tmp_path)
        svc.install("gemini")
        toml_files = list((ph_root / "gemini" / "commands").glob("r2p-*.toml"))
        assert len(toml_files) > 0, "*.toml command files should be installed for gemini"

    def test_gemini_commands_use_prompt_schema_and_forward_args(self, tmp_path):
        svc, _manifest_root, ph_root = make_service(tmp_path)
        svc.install("gemini")

        commands = sorted((ph_root / "gemini" / "commands").glob("r2p-*.toml"))
        assert commands
        for command in commands:
            content = command.read_text(encoding="utf-8")
            keys = {
                match.group(1)
                for line in content.splitlines()
                if (match := re.match(r"^([A-Za-z][A-Za-z0-9_-]*)\s*=", line))
            }
            assert keys == {"description", "prompt"}, (command, keys)
            assert "{{args}}" in content, command
            assert "!{" in content, command

    @pytest.mark.parametrize(
        ("flag", "target"),
        [
            ("-E", "tools.workflow_cli.agent_shortcuts start"),
            ("-I", "tools.workflow_cli.agent_shortcuts start"),
        ],
    )
    def test_trusted_and_legacy_isolated_wrappers_are_recognized_as_managed(
        self, flag, target
    ):
        from tools.workflow_cli.install import _looks_like_managed_bin_script

        wrapper = f"""#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${{BASH_SOURCE[0]}}")" && pwd)"
REPO_ROOT=/trusted/req-to-plan
if command -v python3 >/dev/null 2>&1; then
    exec python3 {flag} "$REPO_ROOT/tools/workflow_cli/__main__.py" {target} "$@"
else
    exec python {flag} "$REPO_ROOT/tools/workflow_cli/__main__.py" {target} "$@"
fi
"""

        assert _looks_like_managed_bin_script(wrapper)

    def test_context_view_prefix_is_not_recognized_as_a_managed_wrapper(self):
        from tools.workflow_cli.install import _looks_like_managed_bin_script

        wrapper = """#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT=/trusted/req-to-plan
exec python3 -E "$REPO_ROOT/tools/workflow_cli/__main__.py" tools.workflow_cli context-view-evil "$@"
"""

        assert not _looks_like_managed_bin_script(wrapper)

    # -----------------------------------------------------------------------
    # Return value shape
    # -----------------------------------------------------------------------

    def test_install_returns_manifest_dict(self, tmp_path):
        svc, _, _ = make_service(tmp_path)
        result = svc.install("claude")
        assert isinstance(result, dict)
        assert "installed_paths" in result
        assert "schema_version" in result

    def test_uninstall_returns_removed_dict(self, tmp_path):
        svc, _, _ = make_service(tmp_path)
        svc.install("claude")
        result = svc.uninstall("claude")
        assert isinstance(result, dict)
        assert "removed" in result
        assert len(result["removed"]) > 0

    def test_uninstall_cleans_backup_directory(self, tmp_path):
        """Backup directory for the platform is removed after uninstall."""
        svc, manifest_root, ph_root = make_service(tmp_path)
        platform_homes = {"claude": ph_root / "claude"}
        svc2 = InstallService(repo_root=REPO_ROOT, manifest_root=manifest_root, platform_homes={
            "claude": ph_root / "claude",
            "codex": ph_root / "codex",
            "gemini": ph_root / "gemini",
        })
        # Create an existing file so a backup is made
        cmd_dir = ph_root / "claude" / "commands"
        cmd_dir.mkdir(parents=True)
        (cmd_dir / "r2p-start.md").write_text("old content", encoding="utf-8")
        svc2.install("claude")
        svc2.uninstall("claude")
        backup_dir = manifest_root / "install" / "backups" / "claude"
        assert not backup_dir.exists()

    def test_install_ships_r2p_execute_for_all_platforms(self, tmp_path):
        service, _manifest_root, ph_root = make_service(tmp_path)
        for platform, rel in (
            ("claude", "commands/r2p-execute.md"),
            ("codex", "skills/r2p-execute/SKILL.md"),
            ("gemini", "commands/r2p-execute.toml"),
        ):
            service.install(platform)
            assert (ph_root / platform / rel).exists(), f"{platform}:{rel} not installed"

    def test_install_ships_r2p_archive_for_all_platforms(self, tmp_path):
        service, _manifest_root, ph_root = make_service(tmp_path)
        for platform, rel in (
            ("claude", "commands/r2p-archive.md"),
            ("codex", "skills/r2p-archive/SKILL.md"),
            ("gemini", "commands/r2p-archive.toml"),
        ):
            service.install(platform)
            assert (ph_root / platform / rel).exists(), f"{platform}:{rel} not installed"


# ---------------------------------------------------------------------------
# Stale shared-wrapper cleanup (Part 2, Task 6)
# ---------------------------------------------------------------------------


def seed_stale_wrapper_in_manifests(manifest_root: Path, stale: Path, platforms) -> None:
    """Record `stale` in each platform manifest's installed_paths, mimicking an
    old install that managed the now-obsolete shared wrapper."""
    from tools.workflow_cli.install import _load_manifest, _dump_manifest
    for platform in platforms:
        mpath = manifest_root / "install" / f"{platform}.yaml"
        manifest = _load_manifest(mpath)
        paths = manifest.setdefault("installed_paths", [])
        if str(stale) not in paths:
            paths.append(str(stale))
        mpath.write_text(_dump_manifest(manifest), encoding="utf-8")


def assert_no_manifest_references(manifest_root: Path, stale: Path) -> None:
    """No installed platform manifest may list `stale` in installed_paths, and no
    backups entry may target it."""
    from tools.workflow_cli.install import _load_manifest
    install_dir = manifest_root / "install"
    for mpath in sorted(install_dir.glob("*.yaml")):
        manifest = _load_manifest(mpath)
        assert str(stale) not in manifest.get("installed_paths", []), (
            f"{mpath.name} still lists stale wrapper in installed_paths"
        )
        for bk in manifest.get("backups", []):
            assert str(bk.get("target")) != str(stale), (
                f"{mpath.name} still has a backups entry targeting the stale wrapper"
            )


def old_managed_adapt_wrapper() -> str:
    return """#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT=/old/req-to-plan
export PYTHONPATH="$REPO_ROOT${PYTHONPATH:+:$PYTHONPATH}"
if command -v python3 >/dev/null 2>&1; then
    exec python3 -m tools.workflow_cli.agent_shortcuts adapt "$@"
else
    exec python -m tools.workflow_cli.agent_shortcuts adapt "$@"
fi
"""


@pytest.mark.parametrize(
    ("platform", "template_suffixes"),
    [
        ("claude", ("commands/r2p-gap-open.md", "commands/r2p-gap-resolve.md")),
        ("codex", ("skills/r2p-gap-open/SKILL.md", "skills/r2p-gap-resolve/SKILL.md")),
        ("gemini", ("commands/r2p-gap-open.toml", "commands/r2p-gap-resolve.toml")),
    ],
)
def test_install_writes_gap_shortcut_templates(tmp_path, platform, template_suffixes):
    svc, manifest_root, ph_root = make_service(tmp_path)
    result = svc.install(platform)
    installed_paths = [Path(p) for p in result.get("installed_paths", [])]
    installed_names = {p.name for p in installed_paths}
    assert {"r2p-gap-open", "r2p-gap-resolve"} <= installed_names
    normalized = {p.as_posix() for p in installed_paths}
    for suffix in template_suffixes:
        assert any(path.endswith(suffix) for path in normalized)


class TestStaleWrapperCleanup:
    def test_upgrade_removes_stale_shared_wrapper_from_all_manifests(self, tmp_path):
        svc, manifest_root, ph_root = make_service(tmp_path)
        svc.install("claude")
        svc.install("codex")
        bin_dir = manifest_root / "bin"
        stale = bin_dir / "r2p-adapt"
        stale.write_text("#!/usr/bin/env bash\n", encoding="utf-8")
        seed_stale_wrapper_in_manifests(manifest_root, stale, platforms=("claude", "codex"))

        # Reinstall should deterministically remove the stale wrapper and manifest refs.
        svc.install("claude")
        assert not stale.exists(), "stale r2p-adapt wrapper must be removed on upgrade"
        assert_no_manifest_references(manifest_root, stale)

    def test_uninstall_removes_stale_shared_wrapper_from_all_manifests(self, tmp_path):
        svc, manifest_root, ph_root = make_service(tmp_path)
        svc.install("claude")
        svc.install("codex")
        bin_dir = manifest_root / "bin"
        stale = bin_dir / "r2p-adapt"
        stale.write_text("#!/usr/bin/env bash\n", encoding="utf-8")
        seed_stale_wrapper_in_manifests(manifest_root, stale, platforms=("claude", "codex"))

        # Uninstall must also clean obsolete managed shared wrappers even when another
        # platform remains installed and normal uninstall would skip shared bin paths.
        svc.uninstall("claude")
        assert not stale.exists(), "stale r2p-adapt wrapper must be removed on uninstall"
        assert_no_manifest_references(manifest_root, stale)

    def test_uninstall_removes_stale_wrapper_referenced_only_by_removed_manifest(self, tmp_path):
        svc, manifest_root, ph_root = make_service(tmp_path)
        svc.install("claude")
        svc.install("codex")
        bin_dir = manifest_root / "bin"
        stale = bin_dir / "r2p-adapt"
        stale.write_text("#!/usr/bin/env bash\n", encoding="utf-8")
        seed_stale_wrapper_in_manifests(manifest_root, stale, platforms=("claude",))

        svc.uninstall("claude")

        assert not stale.exists(), "stale wrapper must be removed before its only manifest ref is dropped"
        assert_no_manifest_references(manifest_root, stale)

    def test_uninstall_preserves_restored_user_backup_for_obsolete_shared_wrapper(self, tmp_path):
        svc, manifest_root, ph_root = make_service(tmp_path)
        svc.install("claude")
        svc.install("codex")
        bin_dir = manifest_root / "bin"
        stale = bin_dir / "r2p-adapt"
        stale.write_text(old_managed_adapt_wrapper(), encoding="utf-8")
        seed_stale_wrapper_in_manifests(manifest_root, stale, platforms=("claude", "codex"))

        backup_dir = manifest_root / "install" / "backups" / "claude"
        backup_dir.mkdir(parents=True, exist_ok=True)
        backup_file = backup_dir / "r2p-adapt.user.bak"
        backup_file.write_text("USER ORIGINAL\n", encoding="utf-8")

        from tools.workflow_cli.install import _load_manifest, _dump_manifest
        claude_manifest_path = manifest_root / "install" / "claude.yaml"
        claude_manifest = _load_manifest(claude_manifest_path)
        claude_manifest.setdefault("backups", []).append(
            {"target": str(stale), "backup": str(backup_file)}
        )
        claude_manifest_path.write_text(_dump_manifest(claude_manifest), encoding="utf-8")

        svc.uninstall("claude")

        assert stale.exists(), "user's restored original must not be removed by cleanup"
        assert stale.read_text() == "USER ORIGINAL\n"
        assert_no_manifest_references(manifest_root, stale)
        assert not backup_file.exists(), "restored backup file should be consumed"

    def test_final_uninstall_preserves_restored_user_backup_for_obsolete_shared_wrapper(self, tmp_path):
        svc, manifest_root, ph_root = make_service(tmp_path)
        svc.install("claude")
        bin_dir = manifest_root / "bin"
        stale = bin_dir / "r2p-adapt"
        stale.write_text(old_managed_adapt_wrapper(), encoding="utf-8")
        seed_stale_wrapper_in_manifests(manifest_root, stale, platforms=("claude",))

        backup_dir = manifest_root / "install" / "backups" / "claude"
        backup_dir.mkdir(parents=True, exist_ok=True)
        backup_file = backup_dir / "r2p-adapt.user.bak"
        backup_file.write_text("USER ORIGINAL\n", encoding="utf-8")

        from tools.workflow_cli.install import _load_manifest, _dump_manifest
        claude_manifest_path = manifest_root / "install" / "claude.yaml"
        claude_manifest = _load_manifest(claude_manifest_path)
        claude_manifest.setdefault("backups", []).append(
            {"target": str(stale), "backup": str(backup_file)}
        )
        claude_manifest_path.write_text(_dump_manifest(claude_manifest), encoding="utf-8")

        result = svc.uninstall("claude")

        assert str(stale) in result["restored"], "uninstall should report restored user backup"
        assert stale.exists(), "final uninstall must not delete the restored user file"
        assert stale.read_text() == "USER ORIGINAL\n"
        assert not backup_file.exists(), "restored backup file should be consumed"

    def test_uninstall_discards_restored_managed_backup_for_obsolete_shared_wrapper(self, tmp_path):
        svc, manifest_root, ph_root = make_service(tmp_path)
        svc.install("claude")
        svc.install("codex")
        bin_dir = manifest_root / "bin"
        stale = bin_dir / "r2p-adapt"
        stale.write_text(old_managed_adapt_wrapper(), encoding="utf-8")
        seed_stale_wrapper_in_manifests(manifest_root, stale, platforms=("claude", "codex"))

        backup_dir = manifest_root / "install" / "backups" / "codex"
        backup_dir.mkdir(parents=True, exist_ok=True)
        backup_file = backup_dir / "r2p-adapt.managed.bak"
        backup_file.write_text(old_managed_adapt_wrapper(), encoding="utf-8")

        from tools.workflow_cli.install import _load_manifest, _dump_manifest
        codex_manifest_path = manifest_root / "install" / "codex.yaml"
        codex_manifest = _load_manifest(codex_manifest_path)
        codex_manifest.setdefault("backups", []).append(
            {"target": str(stale), "backup": str(backup_file)}
        )
        codex_manifest_path.write_text(_dump_manifest(codex_manifest), encoding="utf-8")

        svc.uninstall("codex")

        assert not stale.exists(), "restored managed obsolete wrapper must not survive cleanup"
        assert_no_manifest_references(manifest_root, stale)
        assert not backup_file.exists(), "discarded managed backup file should be consumed"

    def test_stale_shared_wrapper_cleanup_preserves_unmanaged_r2p_wrapper(self, tmp_path):
        svc, manifest_root, ph_root = make_service(tmp_path)
        svc.install("claude")
        svc.install("codex")
        bin_dir = manifest_root / "bin"
        stale = bin_dir / "r2p-adapt"
        unmanaged = bin_dir / "r2p-local"
        stale.write_text("#!/usr/bin/env bash\n", encoding="utf-8")
        unmanaged.write_text("#!/usr/bin/env bash\n", encoding="utf-8")
        seed_stale_wrapper_in_manifests(manifest_root, stale, platforms=("claude", "codex"))

        svc.install("claude")
        assert not stale.exists(), "managed stale wrapper should be removed"
        assert unmanaged.exists(), "unmanaged r2p-* files in bin must be preserved"
        assert_no_manifest_references(manifest_root, stale)

    def test_cleanup_restores_user_backup_before_dropping_obsolete_wrapper(self, tmp_path):
        svc, manifest_root, ph_root = make_service(tmp_path)
        svc.install("codex")  # keep one platform installed so manifests exist
        bin_dir = manifest_root / "bin"
        bin_dir.mkdir(parents=True, exist_ok=True)
        stale = bin_dir / "r2p-adapt"
        # The obsolete managed wrapper currently sits at the target...
        stale.write_text("MANAGED WRAPPER\n", encoding="utf-8")
        # ...and the user's ORIGINAL file was saved as a backup by an old install.
        backups_dir = manifest_root / "install" / "backups" / "codex"
        backups_dir.mkdir(parents=True, exist_ok=True)
        backup_file = backups_dir / "r2p-adapt.bak"
        backup_file.write_text("USER ORIGINAL\n", encoding="utf-8")
        # Seed the manifest: r2p-adapt is both installed and backed up.
        from tools.workflow_cli.install import _load_manifest, _dump_manifest
        mpath = manifest_root / "install" / "codex.yaml"
        manifest = _load_manifest(mpath)
        manifest.setdefault("installed_paths", []).append(str(stale))
        manifest.setdefault("backups", []).append(
            {"target": str(stale), "backup": str(backup_file)}
        )
        mpath.write_text(_dump_manifest(manifest), encoding="utf-8")

        svc._cleanup_obsolete_managed_wrappers()

        # The user's original must be restored at the target, not lost.
        assert stale.exists(), "user's original file must survive cleanup"
        assert stale.read_text() == "USER ORIGINAL\n", (
            "user's backed-up original must be restored before metadata is dropped"
        )
        # Obsolete-wrapper metadata is cleaned and the consumed backup is gone.
        assert_no_manifest_references(manifest_root, stale)
        assert not backup_file.exists(), "restored backup file should be consumed"

    def test_cleanup_ignores_managed_wrapper_backup_when_no_user_backup_exists(self, tmp_path):
        svc, manifest_root, ph_root = make_service(tmp_path)
        svc.install("codex")
        bin_dir = manifest_root / "bin"
        stale = bin_dir / "r2p-adapt"
        stale.write_text(old_managed_adapt_wrapper(), encoding="utf-8")

        backups_dir = manifest_root / "install" / "backups" / "codex"
        backups_dir.mkdir(parents=True, exist_ok=True)
        managed_backup = backups_dir / "r2p-adapt.managed.bak"
        managed_backup.write_text(old_managed_adapt_wrapper(), encoding="utf-8")

        from tools.workflow_cli.install import _load_manifest, _dump_manifest
        mpath = manifest_root / "install" / "codex.yaml"
        manifest = _load_manifest(mpath)
        manifest.setdefault("installed_paths", []).append(str(stale))
        manifest.setdefault("backups", []).append(
            {"target": str(stale), "backup": str(managed_backup)}
        )
        mpath.write_text(_dump_manifest(manifest), encoding="utf-8")

        svc._cleanup_obsolete_managed_wrappers()

        assert not stale.exists(), "managed-only obsolete wrapper backup must not be restored"
        assert_no_manifest_references(manifest_root, stale)
        assert not managed_backup.exists(), "discarded managed wrapper backup should be consumed"

    def test_cleanup_prefers_user_backup_over_later_managed_wrapper_backup(self, tmp_path):
        svc, manifest_root, ph_root = make_service(tmp_path)
        svc.install("codex")
        svc.install("gemini")
        bin_dir = manifest_root / "bin"
        stale = bin_dir / "r2p-adapt"
        stale.write_text(old_managed_adapt_wrapper(), encoding="utf-8")

        from tools.workflow_cli.install import _load_manifest, _dump_manifest

        codex_backup_dir = manifest_root / "install" / "backups" / "codex"
        codex_backup_dir.mkdir(parents=True, exist_ok=True)
        user_backup = codex_backup_dir / "r2p-adapt.user.bak"
        user_backup.write_text("USER ORIGINAL\n", encoding="utf-8")
        codex_manifest_path = manifest_root / "install" / "codex.yaml"
        codex_manifest = _load_manifest(codex_manifest_path)
        codex_manifest.setdefault("installed_paths", []).append(str(stale))
        codex_manifest.setdefault("backups", []).append(
            {"target": str(stale), "backup": str(user_backup)}
        )
        codex_manifest_path.write_text(_dump_manifest(codex_manifest), encoding="utf-8")

        gemini_backup_dir = manifest_root / "install" / "backups" / "gemini"
        gemini_backup_dir.mkdir(parents=True, exist_ok=True)
        managed_backup = gemini_backup_dir / "r2p-adapt.managed.bak"
        managed_backup.write_text(old_managed_adapt_wrapper(), encoding="utf-8")
        gemini_manifest_path = manifest_root / "install" / "gemini.yaml"
        gemini_manifest = _load_manifest(gemini_manifest_path)
        gemini_manifest.setdefault("installed_paths", []).append(str(stale))
        gemini_manifest.setdefault("backups", []).append(
            {"target": str(stale), "backup": str(managed_backup)}
        )
        gemini_manifest_path.write_text(_dump_manifest(gemini_manifest), encoding="utf-8")

        svc._cleanup_obsolete_managed_wrappers()

        assert stale.exists(), "user's original file must survive cleanup"
        assert stale.read_text() == "USER ORIGINAL\n"
        assert_no_manifest_references(manifest_root, stale)
        assert not user_backup.exists(), "restored user backup file should be consumed"
        assert not managed_backup.exists(), "discarded managed wrapper backup should be consumed"

    def test_cleanup_ignores_bad_manifest_while_cleaning_valid_manifests(self, tmp_path):
        svc, manifest_root, ph_root = make_service(tmp_path)
        svc.install("codex")
        bin_dir = manifest_root / "bin"
        stale = bin_dir / "r2p-adapt"
        stale.write_text(old_managed_adapt_wrapper(), encoding="utf-8")
        seed_stale_wrapper_in_manifests(manifest_root, stale, platforms=("codex",))

        bad_manifest = manifest_root / "install" / "broken.yaml"
        bad_manifest.write_text("[]\n", encoding="utf-8")

        svc._cleanup_obsolete_managed_wrappers()

        assert bad_manifest.exists(), "cleanup should leave unreadable manifests for operator repair"
        assert not stale.exists(), "valid manifests should still be cleaned"
        from tools.workflow_cli.install import _load_manifest
        codex_manifest = _load_manifest(manifest_root / "install" / "codex.yaml")
        assert str(stale) not in codex_manifest.get("installed_paths", [])
        assert all(
            str(bk.get("target")) != str(stale)
            for bk in codex_manifest.get("backups", [])
        )


# ---------------------------------------------------------------------------
# opencode platform — reuses claude's command templates, installed under
# ~/.config/opencode/commands/ (no SKILL.md; opencode has no skills concept)
# ---------------------------------------------------------------------------


def _claude_command_names() -> set[str]:
    cmd_dir = REPO_ROOT / "tools" / "workflow_cli" / "agent_templates" / "claude" / "commands"
    return {p.name for p in cmd_dir.glob("r2p-*.md")}


OPENCODE_COMMANDS_WITH_ARGS = {
    "r2p-archive.md",
    "r2p-gap-open.md",
    "r2p-gap-resolve.md",
    "r2p-reopen.md",
    "r2p-start.md",
    "r2p-status.md",
    "r2p-switch.md",
    "r2p-tier-lock.md",
}


class TestInstallOpencode:
    def test_install_copies_command_files(self, tmp_path):
        svc, _, ph_root = make_service(tmp_path)
        svc.install("opencode")
        cmds = list((ph_root / "opencode" / "commands").glob("r2p-*.md"))
        assert {p.name for p in cmds} == _claude_command_names()
        assert len(cmds) > 0

    def test_install_does_not_create_skill_md(self, tmp_path):
        svc, _, ph_root = make_service(tmp_path)
        svc.install("opencode")
        assert not (ph_root / "opencode" / "skills").exists()

    def test_install_command_names_match_claude(self, tmp_path):
        svc, _, ph_root = make_service(tmp_path)
        svc.install("opencode")
        opencode_names = {p.name for p in (ph_root / "opencode" / "commands").glob("r2p-*.md")}
        assert opencode_names == _claude_command_names()

    def test_execute_command_derives_phase_one_protocol_from_claude(self, tmp_path):
        svc, _, ph_root = make_service(tmp_path)
        svc.install("opencode")
        content = (ph_root / "opencode" / "commands" / "r2p-execute.md").read_text(encoding="utf-8")
        for token in (
            "brand-new zero-history subagent invocation",
            "built-in `Task` tool without `task_id`",
            "`task_id` resumes an existing subagent session",
            "targeted or directly affected tests",
            "execution/metrics.md",
            "verification_records",
            "r2p-context-view --work-id <id>",
            "semantic_view",
            "semantic_payload_bytes",
            "⚠️ DEFER",
        ):
            assert token in content

    def test_continue_command_derives_phase_two_plan_author_protocol_from_claude(self, tmp_path):
        svc, _, ph_root = make_service(tmp_path)
        svc.install("opencode")
        content = (ph_root / "opencode" / "commands" / "r2p-continue.md").read_text(encoding="utf-8")
        for token in (
            "phase-level cohesive slice",
            "operation-homogeneous task group",
            "intermediate contract",
            "Prerequisite: none",
            "Prerequisite: PLAN-TASK-NNN",
            "execution-prerequisite-check --work-id <id> --task <N> --require-version 1",
            "strict-compatible",
            "Dependencies:",
        ):
            assert token in content

    def test_install_renders_placeholders(self, tmp_path):
        svc, manifest_root, ph_root = make_service(tmp_path)
        svc.install("opencode")
        content = (ph_root / "opencode" / "commands" / "r2p-start.md").read_text()
        assert "{{R2P_BIN_DIR}}" not in content
        assert "{{R2P_VERSION}}" not in content
        assert str(manifest_root / "bin") in content

    def test_argument_taking_commands_preserve_invocation_arguments(self, tmp_path):
        svc, _, ph_root = make_service(tmp_path)
        svc.install("opencode")
        command_dir = ph_root / "opencode" / "commands"

        for name in OPENCODE_COMMANDS_WITH_ARGS:
            content = (command_dir / name).read_text(encoding="utf-8")
            assert "$ARGUMENTS" in content, f"{name} must receive opencode invocation args"

    def test_manifest_lists_command_paths(self, tmp_path):
        svc, manifest_root, ph_root = make_service(tmp_path)
        svc.install("opencode")
        manifest = yaml.safe_load(
            (manifest_root / "install" / "opencode.yaml").read_text()
        )
        assert manifest["platform"] == "opencode"
        cmd_dir = ph_root / "opencode" / "commands"
        for name in _claude_command_names():
            assert str(cmd_dir / name) in manifest["installed_paths"]

    def test_uninstall_removes_command_files(self, tmp_path):
        svc, _, ph_root = make_service(tmp_path)
        svc.install("opencode")
        svc.uninstall("opencode")
        assert not list((ph_root / "opencode" / "commands").glob("r2p-*.md"))

    def test_uninstall_restores_backup(self, tmp_path):
        svc, _, ph_root = make_service(tmp_path)
        dest = ph_root / "opencode" / "commands" / "r2p-start.md"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text("old content", encoding="utf-8")
        svc.install("opencode")
        svc.uninstall("opencode")
        assert dest.read_text(encoding="utf-8") == "old content"

    def test_status_reports_ok(self, tmp_path):
        svc, _, _ = make_service(tmp_path)
        svc.install("opencode")
        row = next(r for r in svc.status() if r["platform"] == "opencode")
        assert row["status"] == "ok"
        assert row["issues"] == []

    def test_uninstall_preserves_shared_bin_when_claude_installed(self, tmp_path):
        svc, manifest_root, _ = make_service(tmp_path)
        svc.install("claude")
        svc.install("opencode")
        script = manifest_root / "bin" / "r2p-start"
        assert script.exists()
        svc.uninstall("opencode")
        assert script.exists(), "shared bin scripts should remain for the claude install"

    def test_install_rejects_symlinked_managed_target(self, tmp_path):
        svc, manifest_root, ph_root = make_service(tmp_path)
        dest = ph_root / "opencode" / "commands" / "r2p-start.md"
        dest.parent.mkdir(parents=True, exist_ok=True)
        victim = tmp_path / "victim.txt"
        victim.write_text("do not overwrite", encoding="utf-8")
        dest.symlink_to(victim)

        with pytest.raises(ValueError, match="unsafe_install"):
            svc.install("opencode")

        assert victim.read_text(encoding="utf-8") == "do not overwrite"
        assert not (manifest_root / "install" / "opencode.yaml").exists()

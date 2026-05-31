"""
Tests for InstallService (Task 14).
"""
from __future__ import annotations

import shutil
import tempfile
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

    def test_install_already_installed_raises_without_confirm(self, tmp_path):
        svc, _, _ = make_service(tmp_path)
        svc.install("claude")
        with pytest.raises(FileExistsError):
            svc.install("claude")

    def test_install_already_installed_succeeds_with_confirm(self, tmp_path):
        svc, manifest_root, _ = make_service(tmp_path)
        svc.install("claude")
        # Should not raise
        svc.install("claude", confirm=True)
        manifest_path = manifest_root / "install" / "claude.yaml"
        assert manifest_path.exists()

    def test_confirm_reinstall_preserves_original_backup_state(self, tmp_path):
        svc, manifest_root, ph_root = make_service(tmp_path)
        skill_dest = ph_root / "claude" / "skills" / "r2p" / "SKILL.md"
        skill_dest.parent.mkdir(parents=True, exist_ok=True)
        skill_dest.write_text("original content")

        svc.install("claude")
        svc.install("claude", confirm=True)
        svc.uninstall("claude")

        assert skill_dest.exists()
        assert skill_dest.read_text() == "original content"

    def test_confirm_reinstall_uninstall_does_not_leave_managed_files(self, tmp_path):
        svc, manifest_root, ph_root = make_service(tmp_path)
        svc.install("claude")
        skill_dest = ph_root / "claude" / "skills" / "r2p" / "SKILL.md"
        assert skill_dest.exists()

        svc.install("claude", confirm=True)
        svc.uninstall("claude")

        assert not skill_dest.exists()

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

    def test_uninstall_preserves_shared_bin_scripts_when_other_platforms_installed(self, tmp_path):
        svc, manifest_root, _ = make_service(tmp_path)
        svc.install("claude")
        svc.install("codex")

        script = manifest_root / "bin" / "r2p-start"
        assert script.exists()

        svc.uninstall("claude")

        assert script.exists(), "shared bin scripts should remain for codex install"

    # -----------------------------------------------------------------------
    # installed
    # -----------------------------------------------------------------------

    def test_installed_returns_empty_when_none(self, tmp_path):
        svc, _, _ = make_service(tmp_path)
        result = svc.installed()
        assert result == []

    def test_installed_returns_platform_info(self, tmp_path):
        svc, _, _ = make_service(tmp_path)
        svc.install("claude")
        result = svc.installed()
        assert len(result) == 1
        assert result[0]["platform"] == "claude"
        assert result[0]["r2p_version"] == R2P_VERSION
        assert result[0]["schema_version"] == SCHEMA_VERSION

    def test_installed_returns_multiple_platforms(self, tmp_path):
        svc, _, _ = make_service(tmp_path)
        svc.install("claude")
        svc.install("codex")
        result = svc.installed()
        platforms = {r["platform"] for r in result}
        assert "claude" in platforms
        assert "codex" in platforms

    # -----------------------------------------------------------------------
    # doctor
    # -----------------------------------------------------------------------

    def test_doctor_returns_ok_when_clean(self, tmp_path):
        svc, _, _ = make_service(tmp_path)
        svc.install("claude")
        reports = svc.doctor()
        assert len(reports) == 1
        assert reports[0]["platform"] == "claude"
        assert reports[0]["status"] == "ok"
        assert reports[0]["issues"] == []

    def test_doctor_reports_missing_file(self, tmp_path):
        svc, manifest_root, ph_root = make_service(tmp_path)
        svc.install("claude")
        # Manually remove a file to simulate drift
        skill = ph_root / "claude" / "skills" / "r2p" / "SKILL.md"
        skill.unlink()

        reports = svc.doctor()
        assert len(reports) == 1
        assert reports[0]["status"] == "drift"
        issues = reports[0]["issues"]
        assert any("missing_file" in issue for issue in issues)

    def test_doctor_reports_version_mismatch(self, tmp_path):
        svc, manifest_root, _ = make_service(tmp_path)
        svc.install("claude")

        # Tamper with manifest to simulate version drift
        manifest_path = manifest_root / "install" / "claude.yaml"
        data = yaml.safe_load(manifest_path.read_text())
        data["r2p_version"] = "v0-old"
        manifest_path.write_text(yaml.dump(data, default_flow_style=False, sort_keys=True))

        reports = svc.doctor()
        assert len(reports) == 1
        assert reports[0]["status"] == "drift"
        issues = reports[0]["issues"]
        assert any("version_mismatch" in issue for issue in issues)

    def test_doctor_returns_empty_when_nothing_installed(self, tmp_path):
        svc, _, _ = make_service(tmp_path)
        reports = svc.doctor()
        assert reports == []

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
        svc.install("claude", confirm=True)
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

        svc.install("claude", confirm=True)
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

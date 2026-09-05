"""
InstallService — multi-platform install/uninstall for the r2p skill.

Supports: claude, codex, gemini, opencode
"""
from __future__ import annotations

import os
import secrets
import json
import hashlib
import re
import shutil
import shlex
import stat
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from tools.workflow_cli.version import R2P_VERSION
from tools.workflow_cli.atomic import atomic_write_text


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SCHEMA_VERSION = 1

SUPPORTED_PLATFORMS = ("claude", "codex", "gemini", "opencode")

DEFAULT_PLATFORM_HOMES = {
    "claude": Path.home() / ".claude",
    "codex": Path.home() / ".codex",
    "gemini": Path.home() / ".gemini",
    "opencode": Path.home() / ".config" / "opencode",
}

KNOWN_OBSOLETE_SHARED_WRAPPERS = frozenset({"r2p-adapt"})

KNOWN_OBSOLETE_PLATFORM_TARGETS = {
    "claude": (("commands", "r2p-adapt.md"),),
    "codex": (("skills", "r2p-adapt", "SKILL.md"),),
    "gemini": (("commands", "r2p-adapt.toml"),),
}

@dataclass
class _FileSnapshot:
    path: Path
    content: bytes
    mode: int


@dataclass
class _InstallSnapshot:
    manifest_path: Path
    manifest_text: str
    files: list[_FileSnapshot]
    backup_files: list[_FileSnapshot]


def _now_ts() -> str:
    """Return UTC timestamp for backup filenames."""
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")


def _iso_now() -> str:
    """Return ISO 8601 datetime string for manifest."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")


# ---------------------------------------------------------------------------
# InstallService
# ---------------------------------------------------------------------------


class InstallService:
    def __init__(
        self,
        repo_root: Path,
        manifest_root: Path,
        platform_homes: dict[str, Path] | None = None,
    ):
        self.repo_root = repo_root
        self.manifest_root = manifest_root
        self.platform_homes: dict[str, Path] = dict(
            platform_homes if platform_homes is not None else DEFAULT_PLATFORM_HOMES
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def install(self, platform: str) -> dict:
        """Install platform, overwriting any existing install. Returns manifest dict.

        Raises ValueError on unknown platform. An existing install is removed first
        (clean reinstall); per-file backups still guard pre-existing user files.
        """
        if platform not in SUPPORTED_PLATFORMS:
            raise ValueError(
                f"Unknown platform: {platform!r}. Supported: {SUPPORTED_PLATFORMS}"
            )

        manifest_path = self._manifest_path(platform)
        backup_dir = self.manifest_root / "install" / "backups" / platform
        self._validate_install_plan(platform, manifest_path, backup_dir)
        prior_install = (
            self._capture_install_snapshot(platform, manifest_path)
            if manifest_path.exists()
            else None
        )

        installed_paths: list[str] = []
        backups: list[dict[str, str]] = []
        written: list[Path] = []
        manifest_written = False

        try:
            if prior_install is not None:
                self.uninstall(platform)

            bin_dir = self.manifest_root / "bin"

            # Copy bin scripts
            for src in sorted(self.repo_root.glob("tools/r2p-*")):
                if src.is_file():
                    dest = bin_dir / src.name
                    content = _render_bin_script(
                        src.read_text(encoding="utf-8"),
                        self.repo_root,
                    )
                    self._write_managed_file(
                        dest, content, backups, installed_paths, written, backup_dir
                    )
                    shutil.copymode(str(src), str(dest))

            # Copy platform templates
            template_dir = (
                self.repo_root / "tools" / "workflow_cli" / "agent_templates" / platform
            )
            platform_home = self.platform_homes[platform]

            if platform == "claude":
                # SKILL.md → <claude_home>/skills/r2p/SKILL.md
                skill_src = template_dir / "SKILL.md"
                skill_dest = platform_home / "skills" / "r2p" / "SKILL.md"
                content = _render(skill_src.read_text(), R2P_VERSION, str(bin_dir))
                self._write_managed_file(
                    skill_dest, content, backups, installed_paths, written, backup_dir
                )

                # commands/r2p-*.md → <claude_home>/commands/r2p-*.md
                cmd_dir = template_dir / "commands"
                for src in sorted(cmd_dir.glob("r2p-*.md")):
                    dest = platform_home / "commands" / src.name
                    content = _render(src.read_text(), R2P_VERSION, str(bin_dir))
                    self._write_managed_file(
                        dest, content, backups, installed_paths, written, backup_dir
                    )

            elif platform == "codex":
                # skills/r2p-*/SKILL.md → <codex_home>/skills/r2p-*/SKILL.md
                skills_dir = template_dir / "skills"
                for src in sorted(skills_dir.glob("r2p-*/SKILL.md")):
                    dest = platform_home / "skills" / src.parent.name / "SKILL.md"
                    content = _render(src.read_text(), R2P_VERSION, str(bin_dir))
                    self._write_managed_file(
                        dest, content, backups, installed_paths, written, backup_dir
                    )

            elif platform == "gemini":
                # commands/r2p-*.toml → <gemini_home>/commands/r2p-*.toml
                cmd_dir = template_dir / "commands"
                for src in sorted(cmd_dir.glob("r2p-*.toml")):
                    dest = platform_home / "commands" / src.name
                    content = _render(src.read_text(), R2P_VERSION, str(bin_dir))
                    self._write_managed_file(
                        dest, content, backups, installed_paths, written, backup_dir
                    )

            elif platform == "opencode":
                # opencode custom commands use Markdown files with `description:`
                # frontmatter and the filename as the command name. Reuse claude's
                # command bodies. Most commands preserve slash-command invocation
                # args; r2p-execute is specialized below with a fixed preflight.
                cmd_dir = self._opencode_command_source()
                for src in sorted(cmd_dir.glob("r2p-*.md")):
                    dest = platform_home / "commands" / src.name
                    content = _render_opencode_command(
                        src.read_text(),
                        R2P_VERSION,
                        str(bin_dir),
                        src.name,
                    )
                    self._write_managed_file(
                        dest, content, backups, installed_paths, written, backup_dir
                    )

            # Write manifest
            manifest: dict[str, Any] = {
                "backups": backups,
                "installed_at": _iso_now(),
                "installed_paths": installed_paths,
                "platform": platform,
                "r2p_version": R2P_VERSION,
                "schema_version": SCHEMA_VERSION,
            }
            self._write_manifest_atomic(manifest_path, _dump_manifest(manifest))
            manifest_written = True

            # Remove obsolete managed shared wrappers (e.g. a 0.1.2 r2p-adapt) that
            # are no longer part of the current template set, across all manifests.
            self._cleanup_obsolete_managed_wrappers()
            return manifest

        except Exception:
            # Rollback: remove written files, restore backups
            if manifest_written:
                # A pre-existing manifest is impossible here: a fresh install
                # never had one, and a reinstall's uninstall already removed
                # it — prior-manifest restoration is owned by
                # _restore_install_snapshot below.
                manifest_path.unlink(missing_ok=True)
            for path in reversed(written):
                try:
                    path.unlink(missing_ok=True)
                except OSError:
                    pass
            for bk in backups:
                backup_path = Path(bk["backup"])
                target_path = Path(bk["target"])
                if backup_path.exists():
                    target_path.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(str(backup_path), str(target_path))
                    backup_path.unlink(missing_ok=True)
            if prior_install is not None:
                self._restore_install_snapshot(prior_install)
            raise

    def uninstall(self, platform: str) -> dict:
        """Uninstall platform. Returns removed paths. Raises FileNotFoundError if no manifest."""
        manifest_path = self._manifest_path(platform)
        if not manifest_path.exists():
            raise FileNotFoundError(
                f"No manifest for platform {platform!r}. Not installed?"
            )

        manifest = _load_manifest(manifest_path)
        self._validate_manifest_for_uninstall(platform, manifest)
        removed: list[str] = []
        restored: list[str] = []
        restored_targets: set[str] = set()

        # Collect paths that have backups (these should be restored, not deleted)
        backed_up_targets: set[str] = set()
        for bk in manifest.get("backups", []):
            backed_up_targets.add(str(bk["target"]))

        other_platforms_installed = self._other_platforms_have_manifests(platform)
        bin_dir = self.manifest_root / "bin"

        # Remove installed paths (skip paths that will be restored from backup)
        for path_str in manifest.get("installed_paths", []):
            if path_str in backed_up_targets:
                # Will be overwritten by backup restore below — skip deletion
                continue
            p = Path(path_str)
            if other_platforms_installed and p.is_relative_to(bin_dir):
                # r2p-* wrappers are shared by every platform manifest.
                continue
            if p.exists():
                p.unlink()
                removed.append(path_str)

        # Restore user backups (reverse order). Managed wrapper backups are
        # generated r2p files from another platform install, not user originals.
        discarded_managed_backup_targets: set[str] = set()
        for bk in reversed(manifest.get("backups", [])):
            backup_path = Path(bk["backup"])
            target_path = Path(bk["target"])
            if backup_path.exists():
                target_str = str(target_path)
                is_managed_wrapper_backup = self._is_managed_wrapper_backup(
                    target_str, backup_path
                )
                if (
                    other_platforms_installed
                    and self._is_current_shared_wrapper_target(target_path)
                    and not is_managed_wrapper_backup
                ):
                    self._defer_shared_wrapper_backup(platform, target_path, backup_path)
                elif not is_managed_wrapper_backup:
                    target_path.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(str(backup_path), str(target_path))
                    restored.append(str(target_path))
                    restored_targets.add(str(target_path))
                else:
                    discarded_managed_backup_targets.add(str(target_path))
                backup_path.unlink(missing_ok=True)

        if not other_platforms_installed:
            for path_str in discarded_managed_backup_targets - restored_targets:
                p = Path(path_str)
                if p.is_relative_to(bin_dir) and p.exists():
                    p.unlink()
                    removed.append(path_str)

        # Clean obsolete managed shared wrappers while this manifest can still
        # prove ownership of stale shared bin paths.
        self._cleanup_obsolete_managed_wrappers(preserve_paths=restored_targets)

        # Reference-count bin dir: on final platform uninstall, remove the
        # directory only when managed path cleanup left it empty. Files not
        # recorded in the manifest are user-owned and must survive uninstall.
        if not other_platforms_installed and bin_dir.exists():
            try:
                bin_dir.rmdir()
            except OSError:
                pass

        # Clean up empty backup directory for this platform
        backup_dir = self.manifest_root / "install" / "backups" / platform
        if backup_dir.exists():
            try:
                backup_dir.rmdir()  # only removes if empty
            except OSError:
                pass  # non-empty is OK (unexpected files left by user)

        # Remove the manifest itself
        manifest_path.unlink(missing_ok=True)

        return {"removed": removed, "restored": restored, "platform": platform}

    def status(self) -> list[dict]:
        """Read-only install status per platform.

        Each item: {platform, schema_version, r2p_version, installed_at,
        status: 'ok' | 'drift' | 'invalid', issues: [str]}.

        A manifest that is unreadable or has the wrong shape reports `invalid`
        rather than crashing or being mistaken for a healthy install.
        """
        result = []
        install_dir = self.manifest_root / "install"
        if not install_dir.exists():
            return result
        for platform in SUPPORTED_PLATFORMS:
            mp = self._manifest_path(platform)
            if not mp.exists():
                continue

            try:
                data = _load_manifest(mp)
            except Exception as exc:  # truncated / unparseable manifest
                result.append(
                    {
                        "platform": platform,
                        "schema_version": None,
                        "r2p_version": None,
                        "installed_at": None,
                        "status": "invalid",
                        "issues": [f"unreadable_manifest: {exc}"],
                    }
                )
                continue

            shape_issues = _manifest_shape_issues(data, platform)
            if shape_issues:
                meta = data if isinstance(data, dict) else {}
                result.append(
                    {
                        "platform": meta.get("platform", platform),
                        "schema_version": meta.get("schema_version"),
                        "r2p_version": meta.get("r2p_version"),
                        "installed_at": meta.get("installed_at"),
                        "status": "invalid",
                        "issues": shape_issues,
                    }
                )
                continue

            issues: list[str] = []
            for path_str in data.get("installed_paths", []):
                if not Path(path_str).exists():
                    issues.append(f"missing_file: {path_str}")
            schema_version = data.get("schema_version")
            if (
                isinstance(schema_version, int)
                and not isinstance(schema_version, bool)
                and schema_version != SCHEMA_VERSION
            ):
                issues.append(
                    f"unsupported_schema_version: manifest={schema_version!r} "
                    f"expected={SCHEMA_VERSION!r}"
                )
            if data.get("r2p_version") != R2P_VERSION:
                issues.append(
                    f"version_mismatch: manifest={data.get('r2p_version')!r} "
                    f"current={R2P_VERSION!r}"
                )

            result.append(
                {
                    "platform": data.get("platform"),
                    "schema_version": data.get("schema_version"),
                    "r2p_version": data.get("r2p_version"),
                    "installed_at": data.get("installed_at"),
                    "status": "ok" if not issues else "drift",
                    "issues": issues,
                }
            )
        return result

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _manifest_path(self, platform: str) -> Path:
        return self.manifest_root / "install" / f"{platform}.yaml"

    def _other_platforms_have_manifests(self, excluding: str) -> bool:
        """Return True if any other platform has an installed manifest."""
        for platform in SUPPORTED_PLATFORMS:
            if platform == excluding:
                continue
            if self._manifest_path(platform).exists():
                return True
        return False

    def _is_current_shared_wrapper_target(self, target: Path) -> bool:
        bin_dir = self.manifest_root / "bin"
        if target.parent != bin_dir:
            return False
        return target.name in {
            src.name for src in sorted(self.repo_root.glob("tools/r2p-*")) if src.is_file()
        }

    def _defer_shared_wrapper_backup(
        self,
        uninstalling_platform: str,
        target_path: Path,
        backup_path: Path,
    ) -> None:
        recipient = self._shared_backup_recipient(uninstalling_platform)
        if recipient is None:
            raise ValueError("unsafe_manifest: no_valid_shared_backup_recipient")
        recipient_platform, recipient_manifest_path, recipient_manifest = recipient

        backup_dir = self.manifest_root / "install" / "backups" / recipient_platform
        self._validate_install_backup_dir(backup_dir)
        backup_dir.mkdir(parents=True, exist_ok=True)
        deferred_backup_path = _backup_path(backup_dir, target_path)
        shutil.copy2(str(backup_path), str(deferred_backup_path))
        try:
            recipient_manifest.setdefault("backups", []).append(
                {"target": str(target_path), "backup": str(deferred_backup_path)}
            )
            self._write_manifest_atomic(
                recipient_manifest_path,
                _dump_manifest(recipient_manifest),
            )
        except BaseException:
            deferred_backup_path.unlink(missing_ok=True)
            raise
        backup_path.unlink(missing_ok=True)

    def _shared_backup_recipient(
        self, excluding: str
    ) -> tuple[str, Path, dict[str, Any]] | None:
        for platform in SUPPORTED_PLATFORMS:
            if platform == excluding:
                continue
            manifest_path = self._manifest_path(platform)
            if not manifest_path.exists():
                continue
            manifest = _load_manifest(manifest_path)
            self._validate_manifest_for_uninstall(platform, manifest)
            return platform, manifest_path, manifest
        return None

    def _validate_manifest_for_uninstall(self, platform: str, manifest: dict) -> None:
        shape_issues = _manifest_shape_issues(manifest, platform)
        if shape_issues:
            raise ValueError(f"unsafe_manifest: {', '.join(shape_issues)}")

        backups = manifest.get("backups", [])
        if not isinstance(backups, list):
            raise ValueError("unsafe_manifest: backups_not_a_list")

        expected_targets = {
            self._normalize_without_resolving_symlinks(path)
            for path in self._expected_managed_targets(platform)
        }

        for path_str in manifest.get("installed_paths", []):
            self._validate_manifest_target(
                path_str,
                expected_targets,
                field="installed_paths",
            )

        for index, backup in enumerate(backups):
            if not isinstance(backup, dict):
                raise ValueError(f"unsafe_manifest: backups[{index}]_not_a_mapping")
            target = backup.get("target")
            backup_path = backup.get("backup")
            self._validate_manifest_target(
                target,
                expected_targets,
                field=f"backups[{index}].target",
            )
            self._validate_backup_path(
                platform,
                backup_path,
                field=f"backups[{index}].backup",
            )

    def _validate_manifest_target(
        self,
        raw_path: Any,
        expected_targets: set[Path],
        *,
        field: str,
    ) -> Path:
        if not isinstance(raw_path, str):
            raise ValueError(f"unsafe_manifest: {field}_not_a_string")

        path = Path(raw_path)
        if not path.is_absolute():
            raise ValueError(f"unsafe_manifest: {field}_not_absolute")
        if ".." in path.parts:
            raise ValueError(f"unsafe_manifest: {field}_parent_ref")
        if path.is_symlink():
            raise ValueError(f"unsafe_manifest: {field}_is_symlink")

        normalized = self._normalize_without_resolving_symlinks(path)
        if normalized not in expected_targets:
            raise ValueError(f"unsafe_manifest: {field}_outside_managed_targets")
        self._reject_symlinked_ancestors(normalized, field=field)
        return path

    def _validate_backup_path(
        self,
        platform: str,
        raw_path: Any,
        *,
        field: str,
    ) -> Path:
        if not isinstance(raw_path, str):
            raise ValueError(f"unsafe_manifest: {field}_not_a_string")

        path = Path(raw_path)
        if not path.is_absolute():
            raise ValueError(f"unsafe_manifest: {field}_not_absolute")
        if ".." in path.parts:
            raise ValueError(f"unsafe_manifest: {field}_parent_ref")
        if path.is_symlink():
            raise ValueError(f"unsafe_manifest: {field}_is_symlink")

        backup_dir = self._normalize_without_resolving_symlinks(
            self.manifest_root / "install" / "backups" / platform
        )
        normalized = self._normalize_without_resolving_symlinks(path)
        if normalized == backup_dir or not normalized.is_relative_to(backup_dir):
            raise ValueError(f"unsafe_manifest: {field}_outside_backup_dir")
        self._reject_symlinked_ancestors(normalized, field=field)
        return path

    def _normalize_without_resolving_symlinks(self, path: Path) -> Path:
        return Path(os.path.abspath(path))

    def _managed_scan_boundary(self, normalized_path: Path) -> Path:
        """Return the trusted ancestor *below* which a symlink is rejected.

        Platform homes (``~/.claude`` …) and the manifest root are operator-
        configured trusted roots. A user may legitimately symlink a platform
        home (stow/chezmoi), so symlinks are only rejected *inside* it — the
        home itself is trusted. The manifest root keeps the stricter boundary
        (its own parent) so a symlinked manifest root is still rejected,
        matching the install/backup ownership model.
        """
        best_home: Path | None = None
        for home in self.platform_homes.values():
            home_norm = self._normalize_without_resolving_symlinks(home)
            if normalized_path == home_norm or normalized_path.is_relative_to(home_norm):
                if best_home is None or len(home_norm.parts) > len(best_home.parts):
                    best_home = home_norm
        if best_home is not None:
            return best_home
        return self._normalize_without_resolving_symlinks(self.manifest_root).parent

    def _reject_symlinked_ancestors(self, normalized_path: Path, *, field: str) -> None:
        """Reject any symlink among the path's ancestors below its trusted root.

        Only ancestors strictly under the trusted boundary are checked, so a
        user-symlinked platform home is tolerated while an attacker-injected
        symlink swapped in for a managed intermediate directory is not.
        """
        boundary = self._managed_scan_boundary(normalized_path)
        try:
            rel = normalized_path.parent.relative_to(boundary)
        except ValueError:
            raise ValueError(f"unsafe_manifest: {field}_outside_managed_root")
        current = boundary
        for part in rel.parts:
            current = current / part
            if current.is_symlink():
                raise ValueError(f"unsafe_manifest: {field}_symlinked_ancestor")

    def _expected_managed_targets(self, platform: str) -> set[Path]:
        if platform not in SUPPORTED_PLATFORMS:
            raise ValueError(f"unsafe_manifest: unsupported_platform {platform!r}")

        targets = set(self._install_targets(platform))
        bin_dir = self.manifest_root / "bin"
        targets.update(bin_dir / name for name in KNOWN_OBSOLETE_SHARED_WRAPPERS)

        platform_home = self.platform_homes[platform]
        for parts in KNOWN_OBSOLETE_PLATFORM_TARGETS.get(platform, ()):
            targets.add(platform_home.joinpath(*parts))

        return targets

    def _install_targets(self, platform: str) -> list[Path]:
        bin_dir = self.manifest_root / "bin"
        targets = [
            bin_dir / src.name
            for src in sorted(self.repo_root.glob("tools/r2p-*"))
            if src.is_file()
        ]

        template_dir = (
            self.repo_root / "tools" / "workflow_cli" / "agent_templates" / platform
        )
        platform_home = self.platform_homes[platform]

        if platform == "claude":
            targets.append(platform_home / "skills" / "r2p" / "SKILL.md")
            for src in sorted((template_dir / "commands").glob("r2p-*.md")):
                targets.append(platform_home / "commands" / src.name)
        elif platform == "codex":
            for src in sorted((template_dir / "skills").glob("r2p-*/SKILL.md")):
                targets.append(platform_home / "skills" / src.parent.name / "SKILL.md")
        elif platform == "gemini":
            for src in sorted((template_dir / "commands").glob("r2p-*.toml")):
                targets.append(platform_home / "commands" / src.name)
        elif platform == "opencode":
            # opencode reuses claude's command templates (see install()).
            for src in sorted(self._opencode_command_source().glob("r2p-*.md")):
                targets.append(platform_home / "commands" / src.name)

        return targets

    def _opencode_command_source(self) -> Path:
        """Source dir for opencode commands, shared with claude to avoid drift."""
        return (
            self.repo_root
            / "tools"
            / "workflow_cli"
            / "agent_templates"
            / "claude"
            / "commands"
        )

    def _cleanup_obsolete_managed_wrappers(
        self, preserve_paths: set[str] | None = None
    ) -> None:
        """Remove managed shared bin/r2p-* wrappers that are no longer part of the
        current template set, across every installed platform manifest.

        Obsolete candidates are discovered only from valid manifest references
        to known obsolete shared wrappers. A manifest entry for an arbitrary
        ``bin/r2p-*`` path is not proof that this installer owns that file.
        """
        preserve_paths = preserve_paths or set()
        current_wrappers = {
            p.name for p in sorted(self.repo_root.glob("tools/r2p-*")) if p.is_file()
        }
        bin_dir = self.manifest_root / "bin"
        install_dir = self.manifest_root / "install"
        if not install_dir.exists():
            return

        # Discover obsolete managed wrapper paths from manifest references only.
        obsolete: set[str] = set()
        for mpath in sorted(install_dir.glob("*.yaml")):
            manifest = self._load_manifest_for_cleanup(mpath)
            if manifest is None:
                continue
            platform = mpath.stem
            if platform not in SUPPORTED_PLATFORMS:
                continue
            if _manifest_shape_issues(manifest, platform):
                continue
            expected_targets = {
                self._normalize_without_resolving_symlinks(path)
                for path in self._expected_managed_targets(platform)
            }
            installed_refs = manifest.get("installed_paths", [])
            refs = list(installed_refs) if isinstance(installed_refs, list) else []
            backups = manifest.get("backups", [])
            if isinstance(backups, list):
                refs += [
                    bk.get("target")
                    for bk in backups
                    if isinstance(bk, dict)
                ]
            for ref in refs:
                if not isinstance(ref, str):
                    continue
                p = Path(ref)
                if (
                    p.parent == bin_dir
                    and p.name in KNOWN_OBSOLETE_SHARED_WRAPPERS
                    and p.name not in current_wrappers
                ):
                    try:
                        self._validate_manifest_target(
                            ref,
                            expected_targets,
                            field="obsolete_wrapper",
                        )
                    except ValueError:
                        continue
                    obsolete.add(str(p))

        if not obsolete:
            return

        for path_str in obsolete:
            # If an older manifest backed up the user's pre-existing file at this
            # path, restore it before dropping the metadata — otherwise the user's
            # only copy is orphaned and can never be restored by uninstall.
            restored = self._restore_managed_wrapper_backup(path_str)
            for mpath in sorted(install_dir.glob("*.yaml")):
                if self._load_manifest_for_cleanup(mpath) is None:
                    continue
                try:
                    self._strip_path_from_manifest(mpath, path_str)
                except ValueError:
                    # Best-effort cleanup: _write_manifest_atomic rejects writes
                    # that would follow an untrusted symlink. A symlinked or
                    # otherwise unsafe manifest is left in place for operator
                    # repair rather than aborting the in-progress install.
                    continue
            # Delete the obsolete managed wrapper only when there was no user
            # original to restore in its place.
            if not restored and path_str not in preserve_paths:
                Path(path_str).unlink(missing_ok=True)

    def _restore_managed_wrapper_backup(self, path_str: str) -> bool:
        """Restore a user's pre-existing file from any manifest backup whose target
        is ``path_str``, consuming the backup. Returns True if a backup was restored.

        Mirrors the uninstall restore step so cleaning up an obsolete managed
        wrapper never destroys the user's original file. Backups that contain an
        r2p-managed wrapper are discarded instead of restored; those are backups
        of a shared wrapper already written by another platform install."""
        target = Path(path_str)
        user_backups: list[tuple[str, str, int, Path]] = []
        managed_backups: list[Path] = []

        for mpath in sorted((self.manifest_root / "install").glob("*.yaml")):
            manifest = self._load_manifest_for_cleanup(mpath)
            if manifest is None:
                continue
            platform = mpath.stem
            if platform not in SUPPORTED_PLATFORMS:
                continue
            expected_targets = {
                self._normalize_without_resolving_symlinks(path)
                for path in self._expected_managed_targets(platform)
            }
            installed_at = str(manifest.get("installed_at", ""))
            for index, bk in enumerate(manifest.get("backups", [])):
                if not isinstance(bk, dict):
                    continue
                if str(bk.get("target")) != path_str:
                    continue
                backup = bk.get("backup")
                if not backup:
                    continue
                try:
                    self._validate_manifest_target(
                        bk.get("target"),
                        expected_targets,
                        field="backups.target",
                    )
                    self._validate_backup_path(
                        platform,
                        backup,
                        field="backups.backup",
                    )
                except ValueError:
                    continue
                backup_path = Path(backup)
                if not backup_path.is_file():
                    continue
                if self._is_managed_wrapper_backup(path_str, backup_path):
                    managed_backups.append(backup_path)
                else:
                    user_backups.append((installed_at, mpath.name, index, backup_path))

        restored = False
        if user_backups:
            _, _, _, backup_path = sorted(user_backups, key=lambda item: item[:3])[0]
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(backup_path), str(target))
            backup_path.unlink(missing_ok=True)
            restored = True

        for backup_path in managed_backups:
            backup_path.unlink(missing_ok=True)

        return restored

    def _is_managed_wrapper_backup(self, path_str: str, backup_path: Path) -> bool:
        target = Path(path_str)
        bin_dir = self.manifest_root / "bin"
        if target.parent != bin_dir or not target.name.startswith("r2p-"):
            return False
        try:
            content = backup_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            return False
        source = self.repo_root / "tools" / target.name
        try:
            if source.is_file():
                expected = _render_bin_script(
                    source.read_text(encoding="utf-8"), self.repo_root
                )
                if content == expected:
                    return True
        except (OSError, UnicodeDecodeError):
            return False
        return _looks_like_managed_bin_script(content)

    def _strip_path_from_manifest(self, manifest_path: Path, path_str: str) -> None:
        """Remove ``path_str`` from a manifest's installed_paths and any matching
        backups entry, rewriting the file only when it changed."""
        manifest = _load_manifest(manifest_path)
        changed = False

        paths = manifest.get("installed_paths", [])
        if path_str in paths:
            manifest["installed_paths"] = [p for p in paths if p != path_str]
            changed = True

        backups = manifest.get("backups", [])
        if isinstance(backups, list):
            kept = [
                bk
                for bk in backups
                if not isinstance(bk, dict) or str(bk.get("target")) != path_str
            ]
            if len(kept) != len(backups):
                manifest["backups"] = kept
                changed = True

        if changed:
            self._write_manifest_atomic(manifest_path, _dump_manifest(manifest))

    def _load_manifest_for_cleanup(self, manifest_path: Path) -> dict[str, Any] | None:
        """Load a manifest during best-effort shared-wrapper cleanup.

        A malformed unrelated manifest should not leave the current install or
        uninstall half-cleaned; the bad file remains in place for operator repair.
        """
        try:
            return _load_manifest(manifest_path)
        except (OSError, UnicodeDecodeError, ValueError):
            return None

    def _capture_install_snapshot(
        self,
        platform: str,
        manifest_path: Path,
    ) -> _InstallSnapshot:
        manifest = _load_manifest(manifest_path)
        self._validate_manifest_for_uninstall(platform, manifest)
        files: list[_FileSnapshot] = []
        backup_files: list[_FileSnapshot] = []

        for path_str in manifest.get("installed_paths", []):
            snapshot = self._snapshot_file(Path(path_str))
            if snapshot is not None:
                files.append(snapshot)

        for backup in manifest.get("backups", []):
            snapshot = self._snapshot_file(Path(backup["backup"]))
            if snapshot is not None:
                backup_files.append(snapshot)

        return _InstallSnapshot(
            manifest_path=manifest_path,
            manifest_text=manifest_path.read_text(encoding="utf-8"),
            files=files,
            backup_files=backup_files,
        )

    def _snapshot_file(self, path: Path) -> _FileSnapshot | None:
        if not path.is_file():
            return None
        return _FileSnapshot(
            path=path,
            content=path.read_bytes(),
            mode=stat.S_IMODE(path.stat().st_mode),
        )

    def _restore_install_snapshot(self, snapshot: _InstallSnapshot) -> None:
        for file_snapshot in snapshot.files + snapshot.backup_files:
            file_snapshot.path.parent.mkdir(parents=True, exist_ok=True)
            file_snapshot.path.write_bytes(file_snapshot.content)
            try:
                file_snapshot.path.chmod(file_snapshot.mode)
            except OSError:
                pass
        self._write_manifest_atomic(snapshot.manifest_path, snapshot.manifest_text)

    def _write_manifest_atomic(self, manifest_path: Path, data: str) -> None:
        """Write manifest data via a unique temp sibling, then atomically replace.

        Closes the fixed-name temp collision + check-then-write TOCTOU window.
        _validate_install_path is called on both the manifest path and each
        candidate temp path (preserving the existing symlink-rejection rules).
        """
        self._validate_install_path(manifest_path, field="manifest")
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        flags |= getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
        last_err: Exception | None = None
        for _ in range(100):
            tmp = manifest_path.with_name(
                f".{manifest_path.name}.{os.getpid()}.{secrets.token_hex(8)}.tmp"
            )
            self._validate_install_path(tmp, field="manifest")
            try:
                fd = os.open(tmp, flags, 0o666)
            except FileExistsError as exc:
                last_err = exc
                continue
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as fh:
                    fh.write(data)
                os.replace(tmp, manifest_path)
                return
            except BaseException:
                try:
                    tmp.unlink()
                except FileNotFoundError:
                    pass
                raise
        raise FileExistsError(
            f"could not create unique manifest temp for {manifest_path}"
        ) from last_err

    def _validate_install_path(self, path: Path, *, field: str) -> None:
        """Reject install writes that would follow untrusted symlinks."""
        if path.is_symlink():
            raise ValueError(f"unsafe_install: {field}_is_symlink")
        normalized = self._normalize_without_resolving_symlinks(path)
        try:
            self._reject_symlinked_ancestors(normalized, field=field)
        except ValueError as exc:
            raise ValueError(
                str(exc).replace("unsafe_manifest:", "unsafe_install:", 1)
            ) from exc

    def _validate_install_backup_dir(self, backup_dir: Path) -> None:
        probe = backup_dir / "__r2p_probe__"
        normalized = self._normalize_without_resolving_symlinks(probe)
        try:
            self._reject_symlinked_ancestors(normalized, field="backup_dir")
        except ValueError as exc:
            raise ValueError(
                str(exc).replace("unsafe_manifest:", "unsafe_install:", 1)
            ) from exc

    def _validate_install_plan(
        self,
        platform: str,
        manifest_path: Path,
        backup_dir: Path,
    ) -> None:
        for target in self._install_targets(platform):
            self._validate_install_path(target, field="install_destination")
        self._validate_install_path(manifest_path, field="manifest")
        self._validate_install_backup_dir(backup_dir)

    def _write_managed_file(
        self,
        dest: Path,
        content: str,
        backups: list[dict[str, str]],
        installed_paths: list[str],
        written: list[Path],
        backup_dir: Path,
    ) -> None:
        self._validate_install_path(dest, field="install_destination")
        self._validate_install_backup_dir(backup_dir)
        _safe_write(dest, content, backups, installed_paths, written, backup_dir)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _render(content: str, version: str, bin_dir: str) -> str:
    """Substitute template placeholders."""
    content = content.replace("{{R2P_VERSION}}", version)
    content = content.replace("{{R2P_BIN_DIR}}", bin_dir)
    return content


def _render_opencode_command(content: str, version: str, bin_dir: str, command_name: str) -> str:
    """Render a Markdown command for opencode."""
    rendered = _render(content, version, bin_dir)
    if command_name == "r2p-execute.md":
        wrapper = shlex.quote(str(Path(bin_dir) / "r2p-execute"))
        preflight = (
            "\n## Deterministic OpenCode preflight\n\n"
            f"!`{wrapper} $ARGUMENTS 2>&1; r2p_status=$?; "
            'printf \'\\nR2P_PREFLIGHT_EXIT=%s\\n\' "$r2p_status"`\n\n'
            "Treat `R2P_PREFLIGHT_EXIT != 0`, `blocked:`, `no_selected_run`, "
            "or `plan_not_ready` in the preflight output as a hard stop before "
            "any execution work. To execute a specific run, first run "
            "`r2p-switch --work-id <id>` and invoke `/r2p-execute` again.\n"
        )
        if rendered.startswith("---\n"):
            end = rendered.find("\n---\n", 4)
            if end != -1:
                insert_at = end + len("\n---\n")
                return rendered[:insert_at] + preflight + rendered[insert_at:]
        return preflight.lstrip() + "\n" + rendered
    if "$ARGUMENTS" in rendered:
        return rendered
    return (
        rendered.rstrip()
        + "\n\n## opencode invocation arguments\n\n"
        + "Use these arguments when running the wrapper above:\n\n"
        + "```text\n$ARGUMENTS\n```\n\n"
        + "If no arguments were supplied, follow the default usage.\n"
    )


def _render_bin_script(content: str, repo_root: Path) -> str:
    """Render an installed wrapper so it imports modules from the source repo."""
    return content.replace(
        'REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"',
        f"REPO_ROOT={shlex.quote(str(repo_root))}",
    )


def _looks_like_managed_bin_script(content: str) -> bool:
    common = (
        content.startswith("#!/usr/bin/env bash")
        and 'SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"' in content
    )
    legacy = (
        'export PYTHONPATH="$REPO_ROOT${PYTHONPATH:+:$PYTHONPATH}"' in content
        and "-m tools.workflow_cli.agent_shortcuts" in content
    )
    trusted_entrypoint = re.compile(
        r'^[ \t]*exec python(?:3)? -(?:E|I) '
        r'"\$REPO_ROOT/tools/workflow_cli/__main__\.py" '
        r'(?:'
        r'tools\.workflow_cli\.agent_shortcuts [a-z][a-z0-9-]*'
        r'|tools\.workflow_cli\.install_cli(?: [a-z][a-z0-9-]*)?'
        r'|tools\.workflow_cli (?:context-view|execution-prerequisite-check|execution-metrics-(?:status|append|ack|finalize))'
        r') "\$@"$',
        re.MULTILINE,
    )
    return common and (legacy or bool(trusted_entrypoint.search(content)))


def _dump_manifest(manifest: dict[str, Any]) -> str:
    """Return a manifest string readable as YAML without requiring PyYAML."""
    return json.dumps(manifest, indent=2, sort_keys=True) + "\n"


def _load_manifest(path: Path) -> dict[str, Any]:
    """Load current JSON-formatted manifests and legacy simple YAML manifests."""
    text = path.read_text(encoding="utf-8")
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        data = _load_legacy_manifest_yaml(text)
    if not isinstance(data, dict):
        raise ValueError(f"Invalid manifest at {path}: expected object")
    return data


def _manifest_shape_issues(data: Any, platform: str) -> list[str]:
    """Return shape problems that make a parseable manifest still invalid.

    A truncated or partial write can parse yet be missing required fields or
    name the wrong platform; such a manifest must report `invalid`, not `ok`.
    """
    if not isinstance(data, dict):
        return ["manifest_not_a_mapping"]
    issues: list[str] = []
    schema_version = data.get("schema_version")
    if schema_version is None:
        issues.append("missing_schema_version")
    elif isinstance(schema_version, bool) or not isinstance(schema_version, int):
        issues.append("schema_version_not_an_integer")
    # A structurally valid manifest whose schema_version simply differs from the
    # current one is *drift*, not a shape defect: it must not block uninstall or
    # obsolete-wrapper cleanup (which would strand managed files). status()
    # surfaces the mismatch separately as a non-fatal issue.
    if data.get("platform") != platform:
        issues.append(
            f"platform_mismatch: manifest={data.get('platform')!r} expected={platform!r}"
        )
    installed_at = data.get("installed_at")
    if installed_at is None:
        issues.append("missing_installed_at")
    elif not isinstance(installed_at, str):
        issues.append("installed_at_not_a_string")
    elif not installed_at.strip():
        issues.append("installed_at_empty")
    installed_paths = data.get("installed_paths")
    if not isinstance(installed_paths, list):
        issues.append("installed_paths_not_a_list")
    else:
        for index, path in enumerate(installed_paths):
            if not isinstance(path, str):
                issues.append(f"installed_paths[{index}]_not_a_string")
    backups = data.get("backups")
    if not isinstance(backups, list):
        issues.append("backups_not_a_list")
    else:
        for index, backup in enumerate(backups):
            if not isinstance(backup, dict):
                issues.append(f"backups[{index}]_not_a_mapping")
                continue
            for field in ("target", "backup"):
                if not isinstance(backup.get(field), str):
                    issues.append(f"backups[{index}].{field}_not_a_string")
    r2p_version = data.get("r2p_version")
    if r2p_version is None:
        issues.append("missing_r2p_version")
    elif not isinstance(r2p_version, str):
        issues.append("r2p_version_not_a_string")
    return issues


def _load_legacy_manifest_yaml(text: str) -> dict[str, Any]:
    """Parse the limited manifest YAML shape written by older r2p versions."""
    result: dict[str, Any] = {}
    lines = text.splitlines()
    i = 0

    while i < len(lines):
        line = lines[i]
        if not line.strip() or line.startswith(" "):
            i += 1
            continue
        if ":" not in line:
            i += 1
            continue

        key, raw_value = line.split(":", 1)
        value = raw_value.strip()
        if value:
            result[key] = _parse_manifest_scalar(value)
            i += 1
            continue

        i += 1
        items: list[Any] = []
        while i < len(lines):
            child = lines[i]
            if not child.strip():
                i += 1
                continue
            if not child.startswith("- ") and not child.startswith("  "):
                break

            if child.startswith("- "):
                rest = child[2:].strip()
                if ":" in rest:
                    item: dict[str, Any] = {}
                    child_key, child_value = rest.split(":", 1)
                    item[child_key.strip()] = _parse_manifest_scalar(child_value.strip())
                    i += 1
                    while i < len(lines) and lines[i].startswith("  "):
                        nested = lines[i].strip()
                        if nested and ":" in nested:
                            nested_key, nested_value = nested.split(":", 1)
                            item[nested_key.strip()] = _parse_manifest_scalar(
                                nested_value.strip()
                            )
                        i += 1
                    items.append(item)
                else:
                    items.append(_parse_manifest_scalar(rest))
                    i += 1
            else:
                i += 1

        result[key] = items

    return result


def _parse_manifest_scalar(value: str) -> Any:
    value = value.strip()
    if value == "[]":
        return []
    if value == "{}":
        return {}
    if value in {"''", '""'}:
        return ""
    if (
        len(value) >= 2
        and ((value[0] == "'" and value[-1] == "'") or (value[0] == '"' and value[-1] == '"'))
    ):
        value = value[1:-1]
    if value.isdigit():
        return int(value)
    return value


def _backup_path(backup_dir: Path, dest: Path) -> Path:
    path_hash = hashlib.sha256(str(dest).encode("utf-8")).hexdigest()[:12]
    base = backup_dir / f"{dest.name}.{path_hash}.{_now_ts()}"
    candidate = base
    suffix = 1
    while candidate.exists():
        candidate = backup_dir / f"{base.name}.{suffix}"
        suffix += 1
    return candidate


def _safe_write(
    dest: Path,
    content: str,
    backups: list[dict[str, str]],
    installed_paths: list[str],
    written: list[Path],
    backup_dir: Path,
) -> None:
    """Write content to dest, backing up dest to backup_dir if it already exists."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        backup_dir.mkdir(parents=True, exist_ok=True)
        backup = _backup_path(backup_dir, dest)
        shutil.copy2(str(dest), str(backup))
        backups.append({"target": str(dest), "backup": str(backup)})
    atomic_write_text(dest, content)
    installed_paths.append(str(dest))
    written.append(dest)

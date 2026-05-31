"""
InstallService — multi-platform install/uninstall for the r2p skill.

Supports: claude, codex, gemini
"""
from __future__ import annotations

import json
import shutil
import shlex
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from tools.workflow_cli.version import R2P_VERSION


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SCHEMA_VERSION = 1

SUPPORTED_PLATFORMS = ("claude", "codex", "gemini")

DEFAULT_PLATFORM_HOMES = {
    "claude": Path.home() / ".claude",
    "codex": Path.home() / ".codex",
    "gemini": Path.home() / ".gemini",
}


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

    def install(self, platform: str, confirm: bool = False) -> dict:
        """Install platform. Returns manifest dict. Raises ValueError on unknown platform."""
        if platform not in SUPPORTED_PLATFORMS:
            raise ValueError(
                f"Unknown platform: {platform!r}. Supported: {SUPPORTED_PLATFORMS}"
            )

        manifest_path = self._manifest_path(platform)
        if manifest_path.exists() and not confirm:
            raise FileExistsError(
                f"Platform {platform!r} is already installed. "
                "Pass confirm=True to reinstall."
            )
        if manifest_path.exists() and confirm:
            self.uninstall(platform)

        installed_paths: list[str] = []
        backups: list[dict[str, str]] = []
        written: list[Path] = []
        backup_dir = self.manifest_root / "install" / "backups" / platform

        try:
            bin_dir = self.manifest_root / "bin"
            bin_dir.mkdir(parents=True, exist_ok=True)

            # Copy bin scripts
            for src in sorted(self.repo_root.glob("tools/r2p-*")):
                if src.is_file():
                    dest = bin_dir / src.name
                    content = _render_bin_script(
                        src.read_text(encoding="utf-8"),
                        self.repo_root,
                    )
                    _safe_write(
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
                _safe_write(
                    skill_dest, content, backups, installed_paths, written, backup_dir
                )

                # commands/r2p-*.md → <claude_home>/commands/r2p-*.md
                cmd_dir = template_dir / "commands"
                for src in sorted(cmd_dir.glob("r2p-*.md")):
                    dest = platform_home / "commands" / src.name
                    content = _render(src.read_text(), R2P_VERSION, str(bin_dir))
                    _safe_write(
                        dest, content, backups, installed_paths, written, backup_dir
                    )

            elif platform == "codex":
                # skills/r2p-*/SKILL.md → <codex_home>/skills/r2p-*/SKILL.md
                skills_dir = template_dir / "skills"
                for src in sorted(skills_dir.glob("r2p-*/SKILL.md")):
                    dest = platform_home / "skills" / src.parent.name / "SKILL.md"
                    content = _render(src.read_text(), R2P_VERSION, str(bin_dir))
                    _safe_write(
                        dest, content, backups, installed_paths, written, backup_dir
                    )

            elif platform == "gemini":
                # commands/r2p-*.toml → <gemini_home>/commands/r2p-*.toml
                cmd_dir = template_dir / "commands"
                for src in sorted(cmd_dir.glob("r2p-*.toml")):
                    dest = platform_home / "commands" / src.name
                    content = _render(src.read_text(), R2P_VERSION, str(bin_dir))
                    _safe_write(
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
            manifest_path.parent.mkdir(parents=True, exist_ok=True)
            manifest_path.write_text(_dump_manifest(manifest), encoding="utf-8")

            # Remove obsolete managed shared wrappers (e.g. a 0.1.2 r2p-adapt) that
            # are no longer part of the current template set, across all manifests.
            self._cleanup_obsolete_managed_wrappers()
            return manifest

        except Exception:
            # Rollback: remove written files, restore backups
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
            raise

    def uninstall(self, platform: str) -> dict:
        """Uninstall platform. Returns removed paths. Raises FileNotFoundError if no manifest."""
        manifest_path = self._manifest_path(platform)
        if not manifest_path.exists():
            raise FileNotFoundError(
                f"No manifest for platform {platform!r}. Not installed?"
            )

        manifest = _load_manifest(manifest_path)
        removed: list[str] = []
        restored: list[str] = []

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

        # Restore backups (reverse order)
        for bk in reversed(manifest.get("backups", [])):
            backup_path = Path(bk["backup"])
            target_path = Path(bk["target"])
            if backup_path.exists():
                target_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(str(backup_path), str(target_path))
                restored.append(str(target_path))
                backup_path.unlink(missing_ok=True)

        # Reference-count bin dir: only remove when no other platform manifests exist
        if not other_platforms_installed:
            if bin_dir.exists():
                shutil.rmtree(str(bin_dir))

        # Clean up empty backup directory for this platform
        backup_dir = self.manifest_root / "install" / "backups" / platform
        if backup_dir.exists():
            try:
                backup_dir.rmdir()  # only removes if empty
            except OSError:
                pass  # non-empty is OK (unexpected files left by user)

        # Remove the manifest itself
        manifest_path.unlink(missing_ok=True)

        # Clean obsolete managed shared wrappers even when another platform remains
        # installed (normal uninstall skips shared bin/ paths in that case).
        self._cleanup_obsolete_managed_wrappers()

        return {"removed": removed, "restored": restored, "platform": platform}

    def installed(self) -> list[dict]:
        """Return list of installed manifest dicts."""
        result = []
        install_dir = self.manifest_root / "install"
        if not install_dir.exists():
            return result
        for platform in SUPPORTED_PLATFORMS:
            mp = self._manifest_path(platform)
            if mp.exists():
                data = _load_manifest(mp)
                result.append(
                    {
                        "schema_version": data.get("schema_version"),
                        "platform": data.get("platform"),
                        "r2p_version": data.get("r2p_version"),
                        "installed_at": data.get("installed_at"),
                    }
                )
        return result

    def doctor(self) -> list[dict]:
        """Return list of drift reports. Each item: {platform, status, issues: [str]}."""
        reports = []
        for platform in SUPPORTED_PLATFORMS:
            mp = self._manifest_path(platform)
            if not mp.exists():
                continue
            manifest = _load_manifest(mp)
            issues: list[str] = []

            for path_str in manifest.get("installed_paths", []):
                if not Path(path_str).exists():
                    issues.append(f"missing_file: {path_str}")

            if manifest.get("r2p_version") != R2P_VERSION:
                issues.append(
                    f"version_mismatch: manifest={manifest.get('r2p_version')!r} "
                    f"current={R2P_VERSION!r}"
                )

            reports.append(
                {
                    "platform": platform,
                    "status": "ok" if not issues else "drift",
                    "issues": issues,
                }
            )
        return reports

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

    def _cleanup_obsolete_managed_wrappers(self) -> None:
        """Remove managed shared bin/r2p-* wrappers that are no longer part of the
        current template set, across every installed platform manifest.

        Obsolete candidates are discovered only from manifest references (so
        unmanaged files in bin/ are never touched): every ``installed_paths``
        entry and every ``backups[*].target`` under ``install/``. A reference is
        obsolete when it points inside ``bin/``, its filename starts with ``r2p-``,
        and that filename is not in the current ``tools/r2p-*`` wrapper set.
        """
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
            manifest = _load_manifest(mpath)
            refs = list(manifest.get("installed_paths", []))
            refs += [str(bk.get("target")) for bk in manifest.get("backups", [])]
            for ref in refs:
                p = Path(ref)
                if (
                    p.parent == bin_dir
                    and p.name.startswith("r2p-")
                    and p.name not in current_wrappers
                ):
                    obsolete.add(str(p))

        if not obsolete:
            return

        for path_str in obsolete:
            # If an older manifest backed up the user's pre-existing file at this
            # path, restore it before dropping the metadata — otherwise the user's
            # only copy is orphaned and can never be restored by uninstall.
            restored = self._restore_managed_wrapper_backup(path_str)
            for mpath in sorted(install_dir.glob("*.yaml")):
                self._strip_path_from_manifest(mpath, path_str)
            # Delete the obsolete managed wrapper only when there was no user
            # original to restore in its place.
            if not restored:
                Path(path_str).unlink(missing_ok=True)

    def _restore_managed_wrapper_backup(self, path_str: str) -> bool:
        """Restore a user's pre-existing file from any manifest backup whose target
        is ``path_str``, consuming the backup. Returns True if a backup was restored.

        Mirrors the uninstall restore step so cleaning up an obsolete managed
        wrapper never destroys the user's original file."""
        target = Path(path_str)
        restored = False
        for mpath in sorted((self.manifest_root / "install").glob("*.yaml")):
            manifest = _load_manifest(mpath)
            for bk in manifest.get("backups", []):
                if str(bk.get("target")) != path_str:
                    continue
                backup_path = Path(bk.get("backup", ""))
                if backup_path.exists():
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(str(backup_path), str(target))
                    backup_path.unlink(missing_ok=True)
                    restored = True
        return restored

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
        kept = [bk for bk in backups if str(bk.get("target")) != path_str]
        if len(kept) != len(backups):
            manifest["backups"] = kept
            changed = True

        if changed:
            manifest_path.write_text(_dump_manifest(manifest), encoding="utf-8")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _render(content: str, version: str, bin_dir: str) -> str:
    """Substitute template placeholders."""
    content = content.replace("{{R2P_VERSION}}", version)
    content = content.replace("{{R2P_BIN_DIR}}", bin_dir)
    return content


def _render_bin_script(content: str, repo_root: Path) -> str:
    """Render an installed wrapper so it imports modules from the source repo."""
    return content.replace(
        'REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"',
        f"REPO_ROOT={shlex.quote(str(repo_root))}",
    )


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


def _safe_copy(
    src: Path,
    dest: Path,
    backups: list[dict[str, str]],
    installed_paths: list[str],
    written: list[Path],
    backup_dir: Path,
) -> None:
    """Copy src to dest, backing up dest to backup_dir if it already exists."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        ts = _now_ts()
        backup_dir.mkdir(parents=True, exist_ok=True)
        backup = backup_dir / f"{dest.name}.{ts}"
        shutil.copy2(str(dest), str(backup))
        backups.append({"target": str(dest), "backup": str(backup)})
    shutil.copy2(str(src), str(dest))
    installed_paths.append(str(dest))
    written.append(dest)


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
        ts = _now_ts()
        backup_dir.mkdir(parents=True, exist_ok=True)
        backup = backup_dir / f"{dest.name}.{ts}"
        shutil.copy2(str(dest), str(backup))
        backups.append({"target": str(dest), "backup": str(backup)})
    dest.write_text(content, encoding="utf-8")
    installed_paths.append(str(dest))
    written.append(dest)

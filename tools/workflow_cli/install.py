"""
InstallService — multi-platform install/uninstall for the r2p skill.

Supports: claude, codex, gemini
"""
from __future__ import annotations

import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

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
                    _safe_copy(src, dest, backups, installed_paths, written, backup_dir)

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
                # AGENTS.md → <codex_home>/skills/r2p/AGENTS.md
                agents_src = template_dir / "AGENTS.md"
                agents_dest = platform_home / "skills" / "r2p" / "AGENTS.md"
                content = _render(agents_src.read_text(), R2P_VERSION, str(bin_dir))
                _safe_write(
                    agents_dest, content, backups, installed_paths, written, backup_dir
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
            manifest_path.write_text(
                yaml.dump(manifest, default_flow_style=False, sort_keys=True)
            )
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

        manifest = yaml.safe_load(manifest_path.read_text())
        removed: list[str] = []
        restored: list[str] = []

        # Collect paths that have backups (these should be restored, not deleted)
        backed_up_targets: set[str] = set()
        for bk in manifest.get("backups", []):
            backed_up_targets.add(str(bk["target"]))

        # Remove installed paths (skip paths that will be restored from backup)
        for path_str in manifest.get("installed_paths", []):
            if path_str in backed_up_targets:
                # Will be overwritten by backup restore below — skip deletion
                continue
            p = Path(path_str)
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

        # Reference-count bin dir: only remove when no other platform manifests exist
        if not self._other_platforms_have_manifests(platform):
            bin_dir = self.manifest_root / "bin"
            if bin_dir.exists():
                shutil.rmtree(str(bin_dir))

        # Remove the manifest itself
        manifest_path.unlink(missing_ok=True)

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
                data = yaml.safe_load(mp.read_text())
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
            manifest = yaml.safe_load(mp.read_text())
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


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _render(content: str, version: str, bin_dir: str) -> str:
    """Substitute template placeholders."""
    content = content.replace("{{R2P_VERSION}}", version)
    content = content.replace("{{R2P_BIN_DIR}}", bin_dir)
    return content


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
    dest.write_text(content)
    installed_paths.append(str(dest))
    written.append(dest)

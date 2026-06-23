"""Workspace-level helpers for the `.req-to-plan/` directory.

Neutral module imported by both cli.py and agent_shortcuts.py (it imports
neither, so there is no cycle). Owns the workspace `.gitignore` and the
path-limited git-commit primitive used by run-close (add) and run-archive
(remove).
"""
from __future__ import annotations

from pathlib import Path

from tools.workflow_cli.atomic import atomic_write_text

_ARCHIVE_IGNORE_LINE = "/archive"


def ensure_workspace_gitignore(base_path: Path) -> None:
    """Ensure `<base>/.req-to-plan/.gitignore` ignores the archive dir.

    Creates the file with `/archive` if absent; appends the line if the file
    exists without it; no-op if already present. Deliberately does no merging
    or sorting.
    """
    r2p_dir = base_path / ".req-to-plan"
    r2p_dir.mkdir(parents=True, exist_ok=True)
    gitignore = r2p_dir / ".gitignore"
    if not gitignore.exists():
        atomic_write_text(gitignore, _ARCHIVE_IGNORE_LINE + "\n")
        return
    existing = gitignore.read_text(encoding="utf-8")
    if _ARCHIVE_IGNORE_LINE in [ln.strip() for ln in existing.splitlines()]:
        return
    prefix = existing if existing.endswith("\n") or existing == "" else existing + "\n"
    atomic_write_text(gitignore, prefix + _ARCHIVE_IGNORE_LINE + "\n")

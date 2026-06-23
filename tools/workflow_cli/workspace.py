"""Workspace-level helpers for the `.req-to-plan/` directory.

Neutral module imported by both cli.py and agent_shortcuts.py (it imports
neither, so there is no cycle). Owns the workspace `.gitignore` and the
path-limited git-commit primitive used by run-close (add) and run-archive
(remove).
"""
from __future__ import annotations

import subprocess
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


def _git(base_path: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(base_path), *args],
        capture_output=True,
        text=True,
    )


def commit_requirement_dir(base_path: Path, work_id: str, message: str) -> None:
    """Path-limited, best-effort commit of one requirement directory.

    Stages and commits only `.req-to-plan/.gitignore` and `.req-to-plan/<id>`.
    The same primitive both adds (path present) and removes (path moved/deleted).
    Best-effort with observable skips; it never raises and never touches paths
    outside `.req-to-plan/<id>` (no `add -A`, no `-f`, no push).
    """
    gitignore_rel = ".req-to-plan/.gitignore"
    run_rel = f".req-to-plan/{work_id}"

    # Guard 1: must be inside a git work tree.
    inside = _git(base_path, "rev-parse", "--is-inside-work-tree")
    if inside.returncode != 0 or inside.stdout.strip() != "true":
        print(f"warning: skipped commit for {run_rel}: not a git work tree")
        return

    # Stage (path-limited). `git add -- <path>` stages an addition/modification
    # when the path exists, and stages a deletion when it was tracked and is now
    # gone. A wholesale-gitignored path stages nothing (we never pass -f).
    _git(base_path, "add", "--", gitignore_rel, run_rel)

    # Guards 2 & 3 (merged): if nothing is staged for these paths, there is
    # nothing to commit — covers wholesale-ignored, untracked-then-moved, and
    # no-change. `git diff --cached --quiet` returns 0 when there is no diff.
    staged = _git(base_path, "diff", "--cached", "--quiet", "--", gitignore_rel, run_rel)
    if staged.returncode == 0:
        print(f"warning: skipped commit for {run_rel}: nothing staged (ignored or unchanged)")
        return

    committed = _git(base_path, "commit", "-m", message, "--", gitignore_rel, run_rel)
    if committed.returncode != 0:
        print(f"warning: git commit failed for {run_rel}: {committed.stderr.strip()}")

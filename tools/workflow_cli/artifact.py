"""
Artifact lifecycle manager for req-to-plan workflow runs.

Each stage produces an artifact file in .req-to-plan/<work-id>/.
Files use YAML frontmatter to track version, status, and timestamps.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from tools.workflow_cli.models import Stage, STAGE_ARTIFACT_MAP


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------


def artifact_path(run_dir: Path, stage: Stage) -> Path:
    """Return the expected filesystem path for a stage artifact."""
    return run_dir / STAGE_ARTIFACT_MAP[stage]


def artifact_exists(run_dir: Path, stage: Stage) -> bool:
    """Return True if the artifact file for this stage exists."""
    return artifact_path(run_dir, stage).exists()


# ---------------------------------------------------------------------------
# Frontmatter helpers
# ---------------------------------------------------------------------------


def _frontmatter(
    stage: Stage,
    version: int,
    status: str,
    created_at: str,
    updated_at: str,
) -> str:
    return (
        f"---\n"
        f"r2p_stage: {stage.value}\n"
        f"r2p_version: {version}\n"
        f"r2p_status: {status}\n"
        f"r2p_created_at: {created_at}\n"
        f"r2p_updated_at: {updated_at}\n"
        f"---\n\n"
    )


def _parse_frontmatter(text: str) -> tuple[dict, str]:
    """Return (frontmatter_dict, body_content).

    Expects YAML frontmatter delimited by ``---`` lines.
    Returns empty dict and original text when no frontmatter is present.
    """
    if not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---\n", 4)
    if end == -1:
        return {}, text
    fm_text = text[4:end]
    body = text[end + 5:].lstrip("\n")
    fm: dict[str, str] = {}
    for line in fm_text.splitlines():
        if ": " in line:
            key, val = line.split(": ", 1)
            fm[key.strip()] = val.strip()
    return fm, body


# ---------------------------------------------------------------------------
# Core read / write functions
# ---------------------------------------------------------------------------


def write_artifact(
    run_dir: Path,
    stage: Stage,
    content: str,
    version: int = 1,
    status: str = "draft",
) -> Path:
    """Write (or overwrite) a stage artifact with YAML frontmatter.

    Preserves the original ``r2p_created_at`` timestamp when the file
    already exists.

    Returns the path of the written file.
    """
    path = artifact_path(run_dir, stage)
    run_dir.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).isoformat()
    created_at = now
    if path.exists():
        fm, _ = _parse_frontmatter(path.read_text(encoding="utf-8"))
        created_at = fm.get("r2p_created_at", now)
    full_text = _frontmatter(stage, version, status, created_at, now) + content
    # Atomic write: a crash mid-write must not leave a truncated artifact that
    # fails to parse on the next load. Write a sibling temp file then replace.
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(full_text, encoding="utf-8")
    tmp.replace(path)
    return path


def read_artifact(run_dir: Path, stage: Stage) -> str:
    """Return artifact body content (without frontmatter).

    Raises FileNotFoundError when the artifact does not exist.
    """
    path = artifact_path(run_dir, stage)
    if not path.exists():
        raise FileNotFoundError(f"Artifact not found: {path}")
    _, body = _parse_frontmatter(path.read_text(encoding="utf-8"))
    return body


def get_artifact_version(run_dir: Path, stage: Stage) -> int:
    """Return the current version number from frontmatter, or 0 if absent."""
    path = artifact_path(run_dir, stage)
    if not path.exists():
        return 0
    fm, _ = _parse_frontmatter(path.read_text(encoding="utf-8"))
    try:
        return int(fm.get("r2p_version", 0))
    except (ValueError, TypeError):
        return 0


def get_artifact_status(run_dir: Path, stage: Stage) -> str:
    """Return the current status string from frontmatter, or 'missing' if absent."""
    path = artifact_path(run_dir, stage)
    if not path.exists():
        return "missing"
    fm, _ = _parse_frontmatter(path.read_text(encoding="utf-8"))
    return fm.get("r2p_status", "unknown")


def update_artifact_status(run_dir: Path, stage: Stage, new_status: str) -> None:
    """Rewrite the artifact preserving content and version but updating status.

    Raises FileNotFoundError when the artifact does not exist.
    """
    path = artifact_path(run_dir, stage)
    if not path.exists():
        raise FileNotFoundError(f"Artifact not found: {path}")
    fm, body = _parse_frontmatter(path.read_text(encoding="utf-8"))
    write_artifact(
        run_dir,
        stage,
        body,
        version=int(fm.get("r2p_version", 1)),
        status=new_status,
    )


# ---------------------------------------------------------------------------
# ArtifactManager class
# ---------------------------------------------------------------------------


class ArtifactManager:
    """High-level interface for managing stage artifacts in a run directory."""

    def __init__(self, run_dir: Path) -> None:
        self.run_dir = run_dir

    def stage_produce(self, stage: Stage, content: str) -> Path:
        """Write the initial version (v1, draft) of a stage artifact.

        Raises FileExistsError if the artifact already exists at version > 1
        or with a non-draft status. Use stage_update to create a new version.
        """
        version = get_artifact_version(self.run_dir, stage)
        status = get_artifact_status(self.run_dir, stage)
        if version > 1:
            raise FileExistsError(
                f"Artifact for stage {stage.value!r} is already at version {version}. "
                "Use stage_update to create a new version."
            )
        if status not in ("draft", "missing"):
            raise FileExistsError(
                f"Artifact for stage {stage.value!r} has status {status!r}. "
                "Cannot re-produce a non-draft artifact; use stage_update instead."
            )
        return write_artifact(self.run_dir, stage, content, version=1, status="draft")

    def stage_update(self, stage: Stage, content: str) -> Path:
        """Increment the version and overwrite content, keeping status as draft."""
        current_version = get_artifact_version(self.run_dir, stage)
        return write_artifact(
            self.run_dir,
            stage,
            content,
            version=current_version + 1,
            status="draft",
        )

    def stage_ready(self, stage: Stage) -> None:
        """Mark a stage artifact as ready (content unchanged)."""
        status = get_artifact_status(self.run_dir, stage)
        if status == "stale":
            raise ValueError(
                f"Artifact for stage {stage.value!r} is stale. "
                "Use stage_update to create a new version before marking it ready."
            )
        update_artifact_status(self.run_dir, stage, "ready")

    def mark_stale(self, stage: Stage, reason: str, replaced_by: str) -> None:
        """Mark a stage artifact as stale, recording reason and replaced_by in frontmatter."""
        path = artifact_path(self.run_dir, stage)
        if not path.exists():
            raise FileNotFoundError(f"Artifact not found: {path}")
        fm, body = _parse_frontmatter(path.read_text(encoding="utf-8"))
        now = datetime.now(timezone.utc).isoformat()
        created_at = fm.get("r2p_created_at", now)
        version = int(fm.get("r2p_version", 1))
        content = (
            f"---\n"
            f"r2p_stage: {stage.value}\n"
            f"r2p_version: {version}\n"
            f"r2p_status: stale\n"
            f"r2p_created_at: {created_at}\n"
            f"r2p_updated_at: {now}\n"
            f"r2p_stale_reason: {reason}\n"
            f"r2p_replaced_by: {replaced_by}\n"
            f"---\n\n"
        ) + body
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(content, encoding="utf-8")
        tmp.replace(path)

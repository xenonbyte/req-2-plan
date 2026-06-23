from __future__ import annotations

from pathlib import Path

import pytest

from tools.workflow_cli.agent_shortcuts import read_active_pointer, write_active_pointer
from tools.workflow_cli.artifact import ArtifactManager, write_artifact
from tools.workflow_cli.models import Stage, WorkId
from tools.workflow_cli.state import RunStateManager, create_run_record


def _symlink_or_skip(link: Path, target: Path) -> None:
    try:
        link.symlink_to(target)
    except (NotImplementedError, OSError) as exc:
        pytest.skip(f"symlink unavailable: {exc}")


def test_active_pointer_write_does_not_follow_planted_tmp_symlink(tmp_path: Path) -> None:
    outside = tmp_path / "outside.txt"
    outside.write_text("keep me", encoding="utf-8")
    r2p_dir = tmp_path / ".req-to-plan"
    r2p_dir.mkdir()
    _symlink_or_skip(r2p_dir / ".workflow-active.tmp", outside)

    write_active_pointer(tmp_path, "WF-20260623-safe-pointer")

    assert outside.read_text(encoding="utf-8") == "keep me"
    pointer = r2p_dir / ".workflow-active"
    assert not pointer.is_symlink()
    assert read_active_pointer(tmp_path)["selected_work_id"] == "WF-20260623-safe-pointer"


def test_run_state_save_does_not_follow_planted_tmp_symlink(tmp_path: Path) -> None:
    work_id = "WF-20260623-safe-run"
    run_dir = tmp_path / ".req-to-plan" / work_id
    run_dir.mkdir(parents=True)
    outside = tmp_path / "outside-run.txt"
    outside.write_text("keep me", encoding="utf-8")
    _symlink_or_skip(run_dir / "run.md.tmp", outside)

    manager = RunStateManager(run_dir)
    manager.save(create_run_record(WorkId(work_id)))

    assert outside.read_text(encoding="utf-8") == "keep me"
    assert not (run_dir / "run.md").is_symlink()
    assert manager.load().work_id == WorkId(work_id)


def test_artifact_write_does_not_follow_planted_tmp_symlink(tmp_path: Path) -> None:
    run_dir = tmp_path / ".req-to-plan" / "WF-20260623-safe-artifact"
    run_dir.mkdir(parents=True)
    outside = tmp_path / "outside-artifact.txt"
    outside.write_text("keep me", encoding="utf-8")
    _symlink_or_skip(run_dir / "00-raw-requirement.md.tmp", outside)

    artifact = write_artifact(run_dir, Stage.RAW_REQUIREMENT, "# raw body\n")

    assert outside.read_text(encoding="utf-8") == "keep me"
    assert not artifact.is_symlink()
    assert "# raw body" in artifact.read_text(encoding="utf-8")


def test_mark_stale_does_not_follow_planted_tmp_symlink(tmp_path: Path) -> None:
    run_dir = tmp_path / ".req-to-plan" / "WF-20260623-safe-stale"
    artifact = write_artifact(run_dir, Stage.RAW_REQUIREMENT, "# raw body\n")
    outside = tmp_path / "outside-stale.txt"
    outside.write_text("keep me", encoding="utf-8")
    _symlink_or_skip(run_dir / "00-raw-requirement.md.tmp", outside)

    ArtifactManager(run_dir).mark_stale(
        Stage.RAW_REQUIREMENT,
        reason="upstream changed",
        replaced_by="03-requirement-brief.md",
    )

    assert outside.read_text(encoding="utf-8") == "keep me"
    assert not artifact.is_symlink()
    assert "r2p_status: stale" in artifact.read_text(encoding="utf-8")

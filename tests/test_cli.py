"""
Tests for tools/workflow_cli/cli.py — CLI command router.
"""
from __future__ import annotations

import contextlib
import io
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

from tools.workflow_cli.cli import main
from tools.workflow_cli.models import (
    CheckpointRecord,
    OpenRoute,
    RunStatus,
    STAGE_ARTIFACT_MAP,
    Stage,
    TierBase,
    TierEstimate,
    WorkId,
)
from tools.workflow_cli.state import RunStateManager


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def invoke(args: list[str], base_path: str | Path | None = None, expect_exit: int = 0):
    """Call main() with optional --base-path injection; capture SystemExit."""
    full_args = list(args)
    if base_path is not None:
        full_args = ["--base-path", str(base_path)] + full_args
    with pytest.raises(SystemExit) as exc:
        main(full_args)
    assert exc.value.code == expect_exit, (
        f"Expected exit {expect_exit}, got {exc.value.code}"
    )


def load_record(base_path: str | Path, work_id: str):
    run_dir = Path(base_path) / ".req-to-plan" / work_id
    return RunStateManager(run_dir).load()


def save_record(base_path: str | Path, record):
    run_dir = Path(base_path) / ".req-to-plan" / str(record.work_id)
    RunStateManager(run_dir).save(record)


def plan_checkpoint() -> CheckpointRecord:
    return CheckpointRecord(
        stage=Stage.PLAN,
        artifact="07-plan.md",
        version=1,
        approved_at="2026-05-27T00:00:00+00:00",
        downstream_authorization="executor",
    )


def requirement_checkpoint() -> CheckpointRecord:
    return CheckpointRecord(
        stage=Stage.REQUIREMENT_BRIEF,
        artifact="03-requirement-brief.md",
        version=1,
        approved_at="2026-05-27T00:00:00+00:00",
        downstream_authorization="next_stage",
    )


def _seed_plan_approved_run(base_path, work_id="WF-20260604-gap"):
    """A run at PLAN with the full upstream chain active+approved on disk."""
    from tools.workflow_cli.state import create_run_record, upsert_active_artifact
    from tools.workflow_cli.artifact import write_artifact

    record = create_run_record(WorkId(work_id))
    record.current_stage = Stage.PLAN
    record.status = RunStatus.CHECKPOINT_APPROVED
    record.tier_locked = TierEstimate(base=TierBase.LIGHT)
    run_dir = Path(base_path) / ".req-to-plan" / work_id
    run_dir.mkdir(parents=True, exist_ok=True)
    for stage in (
        Stage.REQUIREMENT_BRIEF,
        Stage.RISK_DISCOVERY,
        Stage.DESIGN,
        Stage.SPEC,
        Stage.PLAN,
    ):
        artifact_file = STAGE_ARTIFACT_MAP[stage]
        write_artifact(run_dir, stage, f"# {stage.value} body\n", version=1, status="approved")
        upsert_active_artifact(record, stage, artifact_file, 1, "approved")
        record.approved_checkpoints.append(
            CheckpointRecord(
                stage=stage,
                artifact=artifact_file,
                version=1,
                approved_at="2026-06-04T00:00:00+00:00",
                downstream_authorization="next_stage",
            )
        )
    RunStateManager(run_dir).save(record)
    return work_id, run_dir


def test_seed_plan_approved_run_roundtrips():
    with tempfile.TemporaryDirectory() as tmp:
        work_id, _ = _seed_plan_approved_run(tmp)
        rec = load_record(tmp, work_id)
        assert rec.current_stage == Stage.PLAN
        assert rec.tier_locked.base == TierBase.LIGHT
        assert {cp.stage for cp in rec.approved_checkpoints} == {
            Stage.REQUIREMENT_BRIEF,
            Stage.RISK_DISCOVERY,
            Stage.DESIGN,
            Stage.SPEC,
            Stage.PLAN,
        }
        assert all(aa.status == "approved" for aa in rec.active_artifacts)


# ---------------------------------------------------------------------------
# run-start
# ---------------------------------------------------------------------------


class TestRunStart:
    def test_creates_run_md(self):
        with tempfile.TemporaryDirectory() as tmp:
            invoke(
                ["run-start", "--work-id", "WF-20260527-test", "--requirement", "Add rate limiting"],
                base_path=tmp,
            )
            run_md = Path(tmp) / ".req-to-plan" / "WF-20260527-test" / "run.md"
            assert run_md.exists(), "run.md should be created"

    def test_creates_raw_requirement_artifact(self):
        with tempfile.TemporaryDirectory() as tmp:
            invoke(
                ["run-start", "--work-id", "WF-20260527-test", "--requirement", "Add rate limiting"],
                base_path=tmp,
            )
            raw = Path(tmp) / ".req-to-plan" / "WF-20260527-test" / "00-raw-requirement.md"
            assert raw.exists(), "00-raw-requirement.md should be created"

    def test_creates_intake_brief(self):
        with tempfile.TemporaryDirectory() as tmp:
            invoke(
                ["run-start", "--work-id", "WF-20260527-test", "--requirement", "Add rate limiting"],
                base_path=tmp,
            )
            brief = Path(tmp) / ".req-to-plan" / "WF-20260527-test" / "01-intake-brief.md"
            assert brief.exists(), "01-intake-brief.md should be created"

    def test_run_md_contains_work_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            invoke(
                ["run-start", "--work-id", "WF-20260527-test", "--requirement", "Add rate limiting"],
                base_path=tmp,
            )
            run_md = Path(tmp) / ".req-to-plan" / "WF-20260527-test" / "run.md"
            content = run_md.read_text()
            assert "WF-20260527-test" in content

    def test_invalid_work_id_exits_nonzero(self, capsys):
        with tempfile.TemporaryDirectory() as tmp:
            with pytest.raises(SystemExit) as exc:
                main(["--base-path", str(tmp), "run-start", "--work-id", "INVALID", "--requirement", "foo"])
            assert exc.value.code != 0

    def test_blank_requirement_exits_cli_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            invoke(
                ["run-start", "--work-id", "WF-20260527-test", "--requirement", "   "],
                base_path=tmp,
                expect_exit=2,
            )

    def test_second_run_start_same_work_id_exits_conflict(self):
        with tempfile.TemporaryDirectory() as tmp:
            invoke(["run-start", "--work-id", "WF-20260527-test", "--requirement", "foo"], base_path=tmp)
            with pytest.raises(SystemExit) as exc:
                main(["--base-path", str(tmp), "run-start", "--work-id", "WF-20260527-test", "--requirement", "bar"])
            assert exc.value.code == 6  # EXIT_CONFLICT

    def test_run_start_with_overwrite_succeeds(self):
        with tempfile.TemporaryDirectory() as tmp:
            invoke(["run-start", "--work-id", "WF-20260527-test", "--requirement", "foo"], base_path=tmp)
            invoke(["run-start", "--work-id", "WF-20260527-test", "--requirement", "bar", "--overwrite"], base_path=tmp)
            run_md = Path(tmp) / ".req-to-plan" / "WF-20260527-test" / "run.md"
            assert run_md.exists()

    def test_run_start_with_overwrite_clears_stale_run_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            work_id = "WF-20260527-test"
            run_dir = Path(tmp) / ".req-to-plan" / work_id
            invoke(["run-start", "--work-id", work_id, "--requirement", "foo"], base_path=tmp)
            stale_artifact = run_dir / "03-requirement-brief.md"
            stale_marker = run_dir / "reviews" / "raw_requirement-checkpoint-review-v1.md"
            stale_marker.parent.mkdir(parents=True, exist_ok=True)
            stale_artifact.write_text("old requirement brief", encoding="utf-8")
            stale_marker.write_text("old review marker", encoding="utf-8")

            invoke(["run-start", "--work-id", work_id, "--requirement", "bar", "--overwrite"], base_path=tmp)

            assert not stale_artifact.exists()
            assert not stale_marker.exists()

    def test_run_start_refuses_partial_run_dir_without_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            work_id = "WF-20260527-test"
            run_dir = Path(tmp) / ".req-to-plan" / work_id
            stale_marker = run_dir / "reviews" / "raw_requirement-checkpoint-review-v1.md"
            stale_marker.parent.mkdir(parents=True, exist_ok=True)
            stale_marker.write_text("old review marker", encoding="utf-8")

            invoke(
                ["run-start", "--work-id", work_id, "--requirement", "bar"],
                base_path=tmp,
                expect_exit=6,
            )
            invoke(
                ["run-start", "--work-id", work_id, "--requirement", "bar", "--overwrite"],
                base_path=tmp,
            )

            assert not stale_marker.exists()

    def test_run_start_rejects_symlinked_workspace_dir_without_writing_target(self, capsys):
        # run-start bootstraps the trusted state root, so it must refuse a
        # symlinked .req-to-plan exactly like _load_run does for every other
        # command — otherwise the requirement text is written out-of-workspace.
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            outside = base / "outside-r2p"
            outside.mkdir()
            (base / ".req-to-plan").symlink_to(outside, target_is_directory=True)

            with pytest.raises(SystemExit) as exc:
                main([
                    "--base-path", str(base),
                    "run-start",
                    "--work-id", "WF-20260527-link",
                    "--requirement", "secret requirement text",
                ])

            assert exc.value.code == 6  # EXIT_CONFLICT
            assert "symlink" in capsys.readouterr().out.lower()
            assert not (outside / "WF-20260527-link" / "00-raw-requirement.md").exists()
            assert not (outside / "WF-20260527-link" / "run.md").exists()

    def test_run_start_rejects_symlinked_run_dir_without_writing_target(self, capsys):
        # A symlinked .req-to-plan/<id> must also be refused before any write,
        # mirroring the second guard in _load_run.
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            work_id = "WF-20260527-link"
            outside = base / "outside-run"
            outside.mkdir()
            run_link = base / ".req-to-plan" / work_id
            run_link.parent.mkdir(parents=True)
            run_link.symlink_to(outside, target_is_directory=True)

            with pytest.raises(SystemExit) as exc:
                main([
                    "--base-path", str(base),
                    "run-start",
                    "--work-id", work_id,
                    "--requirement", "secret requirement text",
                ])

            assert exc.value.code == 6  # EXIT_CONFLICT
            assert "symlink" in capsys.readouterr().out.lower()
            assert run_link.is_symlink()
            assert not (outside / "00-raw-requirement.md").exists()
            assert not (outside / "run.md").exists()


# ---------------------------------------------------------------------------
# run-start --requirement-file
# ---------------------------------------------------------------------------


class TestRunStartRequirementFile:
    def test_reads_requirement_from_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            req_file = Path(tmp) / "req.md"
            req_file.write_text("Add OAuth login support with Google", encoding="utf-8")
            invoke(
                ["run-start", "--work-id", "WF-20260527-test",
                 "--requirement-file", str(req_file)],
                base_path=tmp,
            )
            raw = Path(tmp) / ".req-to-plan" / "WF-20260527-test" / "00-raw-requirement.md"
            assert "Add OAuth login support with Google" in raw.read_text(encoding="utf-8")

    def test_brief_stores_file_content_not_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            req_file = Path(tmp) / "req.md"
            req_file.write_text("Migrate from MySQL to PostgreSQL", encoding="utf-8")
            invoke(
                ["run-start", "--work-id", "WF-20260527-test",
                 "--requirement-file", str(req_file)],
                base_path=tmp,
            )
            brief = (
                Path(tmp) / ".req-to-plan" / "WF-20260527-test" / "01-intake-brief.md"
            ).read_text(encoding="utf-8")
            assert "Migrate from MySQL to PostgreSQL" in brief
            # The literal file path must NOT be stored as the requirement.
            assert f"requirement: {req_file}" not in brief

    def test_missing_file_exits_cli_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            invoke(
                ["run-start", "--work-id", "WF-20260527-test",
                 "--requirement-file", str(Path(tmp) / "nope.md")],
                base_path=tmp,
                expect_exit=2,
            )

    def test_empty_file_exits_cli_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            req_file = Path(tmp) / "empty.md"
            req_file.write_text("   \n", encoding="utf-8")
            invoke(
                ["run-start", "--work-id", "WF-20260527-test",
                 "--requirement-file", str(req_file)],
                base_path=tmp,
                expect_exit=2,
            )

    def test_requirement_and_file_are_mutually_exclusive(self):
        with tempfile.TemporaryDirectory() as tmp:
            req_file = Path(tmp) / "req.md"
            req_file.write_text("content", encoding="utf-8")
            with pytest.raises(SystemExit) as exc:
                main(["--base-path", str(tmp), "run-start", "--work-id", "WF-20260527-test",
                      "--requirement", "inline", "--requirement-file", str(req_file)])
            assert exc.value.code != 0

    def test_neither_requirement_nor_file_errors(self):
        with tempfile.TemporaryDirectory() as tmp:
            with pytest.raises(SystemExit) as exc:
                main(["--base-path", str(tmp), "run-start", "--work-id", "WF-20260527-test"])
            assert exc.value.code != 0


# ---------------------------------------------------------------------------
# tier-status
# ---------------------------------------------------------------------------


class TestTierStatus:
    def test_prints_tier_info_after_run_start(self, capsys):
        with tempfile.TemporaryDirectory() as tmp:
            invoke(
                ["run-start", "--work-id", "WF-20260527-test", "--requirement", "Add rate limiting"],
                base_path=tmp,
            )
            invoke(
                ["tier-status", "--work-id", "WF-20260527-test"],
                base_path=tmp,
            )
            out = capsys.readouterr().out
            assert "tier" in out.lower() or "light" in out.lower() or "standard" in out.lower()

    def test_not_found_exits_nonzero(self):
        with tempfile.TemporaryDirectory() as tmp:
            with pytest.raises(SystemExit) as exc:
                main(["--base-path", str(tmp), "tier-status", "--work-id", "WF-20260527-nothere"])
            assert exc.value.code != 0


# ---------------------------------------------------------------------------
# gate-entry
# ---------------------------------------------------------------------------


class TestGateEntry:
    def test_raw_requirement_passes_no_upstream(self, capsys):
        with tempfile.TemporaryDirectory() as tmp:
            invoke(
                ["run-start", "--work-id", "WF-20260527-test", "--requirement", "Add rate limiting"],
                base_path=tmp,
            )
            invoke(
                ["gate-entry", "--work-id", "WF-20260527-test", "--stage", "raw_requirement"],
                base_path=tmp,
            )
            out = capsys.readouterr().out
            assert "pass" in out.lower() or "ok" in out.lower() or "passed" in out.lower()

    def test_missing_run_exits_nonzero(self):
        with tempfile.TemporaryDirectory() as tmp:
            with pytest.raises(SystemExit) as exc:
                main(["--base-path", str(tmp), "gate-entry", "--work-id", "WF-20260527-nothere", "--stage", "raw_requirement"])
            assert exc.value.code != 0


# ---------------------------------------------------------------------------
# stage-produce
# ---------------------------------------------------------------------------


class TestStageProduce:
    def test_writes_artifact(self):
        with tempfile.TemporaryDirectory() as tmp:
            invoke(
                ["run-start", "--work-id", "WF-20260527-test", "--requirement", "Add rate limiting"],
                base_path=tmp,
            )
            invoke(
                ["stage-produce", "--work-id", "WF-20260527-test", "--stage", "raw_requirement", "--content", "My raw content"],
                base_path=tmp,
            )
            artifact = Path(tmp) / ".req-to-plan" / "WF-20260527-test" / "00-raw-requirement.md"
            assert artifact.exists()
            text = artifact.read_text()
            assert "My raw content" in text

    def test_missing_run_exits_nonzero(self):
        with tempfile.TemporaryDirectory() as tmp:
            with pytest.raises(SystemExit) as exc:
                main([
                    "--base-path", str(tmp),
                    "stage-produce", "--work-id", "WF-20260527-nothere",
                    "--stage", "raw_requirement", "--content", "foo",
                ])
            assert exc.value.code != 0

    def test_content_file_option(self):
        with tempfile.TemporaryDirectory() as tmp:
            content_file = Path(tmp) / "my_content.md"
            content_file.write_text("Content from file")
            invoke(
                ["run-start", "--work-id", "WF-20260527-test", "--requirement", "Add rate limiting"],
                base_path=tmp,
            )
            invoke(
                ["stage-produce", "--work-id", "WF-20260527-test", "--stage", "raw_requirement", "--content-file", str(content_file)],
                base_path=tmp,
            )
            artifact = Path(tmp) / ".req-to-plan" / "WF-20260527-test" / "00-raw-requirement.md"
            text = artifact.read_text()
            assert "Content from file" in text

    def test_refuses_non_current_stage(self):
        with tempfile.TemporaryDirectory() as tmp:
            work_id = "WF-20260527-test"
            invoke(
                ["run-start", "--work-id", work_id, "--requirement", "Add rate limiting"],
                base_path=tmp,
            )

            invoke(
                ["stage-produce", "--work-id", work_id, "--stage", "design", "--content", "Design"],
                base_path=tmp,
                expect_exit=6,
            )

            artifact = Path(tmp) / ".req-to-plan" / work_id / "05-design.md"
            assert not artifact.exists()

    def test_requires_entry_gate_for_current_stage(self):
        with tempfile.TemporaryDirectory() as tmp:
            work_id = "WF-20260527-test"
            invoke(
                ["run-start", "--work-id", work_id, "--requirement", "Add rate limiting"],
                base_path=tmp,
            )
            record = load_record(tmp, work_id)
            record.current_stage = Stage.DESIGN
            save_record(tmp, record)

            invoke(
                ["stage-produce", "--work-id", work_id, "--stage", "design", "--content", "Design"],
                base_path=tmp,
                expect_exit=3,
            )

            artifact = Path(tmp) / ".req-to-plan" / work_id / "05-design.md"
            assert not artifact.exists()
            record = load_record(tmp, work_id)
            assert record.status == RunStatus.ENTRY_GATE_FAILED


# ---------------------------------------------------------------------------
# status-run
# ---------------------------------------------------------------------------


class TestStatusRun:
    def test_prints_run_info(self, capsys):
        with tempfile.TemporaryDirectory() as tmp:
            invoke(
                ["run-start", "--work-id", "WF-20260527-test", "--requirement", "Add rate limiting"],
                base_path=tmp,
            )
            invoke(
                ["status-run", "--work-id", "WF-20260527-test"],
                base_path=tmp,
            )
            out = capsys.readouterr().out
            assert "WF-20260527-test" in out

    def test_missing_run_exits_nonzero(self):
        with tempfile.TemporaryDirectory() as tmp:
            with pytest.raises(SystemExit) as exc:
                main(["--base-path", str(tmp), "status-run", "--work-id", "WF-20260527-nothere"])
            assert exc.value.code != 0

    def test_rejects_path_traversal_work_id_before_loading(self, capsys):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            outside = base / "outside"
            outside.mkdir()
            (outside / "run.md").write_text(
                "# Workflow Run: WF-20260527-outside\n\n"
                "## Status\nactive_stage_draft\n\n"
                "## Current Stage\nraw_requirement\n\n"
                "## r2p Version\nv1\n",
                encoding="utf-8",
            )

            with pytest.raises(SystemExit) as exc:
                main([
                    "--base-path", str(base),
                    "status-run", "--work-id", "../outside",
                ])

            assert exc.value.code == 2
            assert "WF-20260527-outside" not in capsys.readouterr().out

    def test_rejects_symlinked_run_dir(self, capsys):
        # Even a read-only command refuses a symlinked .req-to-plan/<id>: the
        # guard is centralized in _load_run, not per-command.
        from tools.workflow_cli.state import RunStateManager, create_run_record
        from tools.workflow_cli.models import WorkId

        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            work_id = "WF-20260527-link"
            outside = base / "outside-run"
            outside.mkdir()
            RunStateManager(outside).save(create_run_record(WorkId(work_id)))
            run_link = base / ".req-to-plan" / work_id
            run_link.parent.mkdir(parents=True)
            run_link.symlink_to(outside, target_is_directory=True)

            with pytest.raises(SystemExit) as exc:
                main(["--base-path", str(base), "status-run", "--work-id", work_id])

            assert exc.value.code == 6
            assert "symlink" in capsys.readouterr().out.lower()
            assert run_link.is_symlink()

    def test_human_caps_approved_checkpoints_with_recovery_file(self, tmp_path, capsys):
        work_id = "WF-20260625-compact-test"
        invoke(["run-start", "--work-id", work_id, "--requirement", "Compact status output"], base_path=tmp_path)
        record = load_record(tmp_path, work_id)
        stages = list(Stage)
        record.approved_checkpoints = [
            CheckpointRecord(
                stage=stages[i % len(stages)],
                artifact=f"{i:02d}-artifact.md",
                version=i,
                approved_at=f"2026-06-25T00:{i:02d}:00+00:00",
                downstream_authorization="next_stage",
            )
            for i in range(12)
        ]
        save_record(tmp_path, record)
        capsys.readouterr()

        invoke(["status-run", "--work-id", work_id], base_path=tmp_path)

        out = capsys.readouterr().out
        recovery = tmp_path / ".req-to-plan" / work_id / "logs" / "status-run-approved-checkpoints.txt"
        assert "approved_checkpoints" in out
        assert "10 shown" in out
        assert "12 total" in out
        assert f".req-to-plan/{work_id}/logs/status-run-approved-checkpoints.txt" in out
        assert recovery.exists()
        assert "00-artifact.md" in recovery.read_text(encoding="utf-8")

    def test_human_keeps_short_approved_checkpoints_without_recovery_file(self, tmp_path, capsys):
        work_id = "WF-20260625-compact-test"
        invoke(["run-start", "--work-id", work_id, "--requirement", "Compact status output"], base_path=tmp_path)
        record = load_record(tmp_path, work_id)
        record.approved_checkpoints = [
            CheckpointRecord(
                stage=Stage.RAW_REQUIREMENT,
                artifact=f"{i:02d}-artifact.md",
                version=i,
                approved_at=f"2026-06-25T00:{i:02d}:00+00:00",
                downstream_authorization="next_stage",
            )
            for i in range(3)
        ]
        save_record(tmp_path, record)
        capsys.readouterr()

        invoke(["status-run", "--work-id", work_id], base_path=tmp_path)

        out = capsys.readouterr().out
        assert "approved_checkpoints" in out
        assert "shown" not in out
        assert "total" not in out
        assert f".req-to-plan/{work_id}/logs/status-run-approved-checkpoints.txt" not in out
        assert not (tmp_path / ".req-to-plan" / work_id / "logs" / "status-run-approved-checkpoints.txt").exists()

    def test_human_falls_back_to_full_approved_checkpoints_when_recovery_write_fails(self, tmp_path, capsys):
        work_id = "WF-20260625-compact-test"
        invoke(["run-start", "--work-id", work_id, "--requirement", "Compact status output"], base_path=tmp_path)
        record = load_record(tmp_path, work_id)
        record.approved_checkpoints = [
            CheckpointRecord(
                stage=Stage.RAW_REQUIREMENT,
                artifact=f"{i:02d}-artifact.md",
                version=i,
                approved_at=f"2026-06-25T00:{i:02d}:00+00:00",
                downstream_authorization="next_stage",
            )
            for i in range(12)
        ]
        save_record(tmp_path, record)
        logs_path = tmp_path / ".req-to-plan" / work_id / "logs"
        logs_path.write_text("not a directory", encoding="utf-8")
        capsys.readouterr()

        invoke(["status-run", "--work-id", work_id], base_path=tmp_path)

        out = capsys.readouterr().out
        assert "10 shown" not in out
        assert "12 total" not in out
        assert f".req-to-plan/{work_id}/logs/status-run-approved-checkpoints.txt" not in out
        assert out.count("    - raw_requirement") == 12

    def test_json_keeps_full_approved_checkpoints_without_recovery_file(self, tmp_path, capsys, monkeypatch):
        work_id = "WF-20260625-compact-test"
        invoke(["run-start", "--work-id", work_id, "--requirement", "Compact status output"], base_path=tmp_path)
        record = load_record(tmp_path, work_id)
        record.approved_checkpoints = [
            CheckpointRecord(
                stage=Stage.RAW_REQUIREMENT,
                artifact=f"{i:02d}-artifact.md",
                version=i,
                approved_at=f"2026-06-25T00:{i:02d}:00+00:00",
                downstream_authorization="next_stage",
            )
            for i in range(12)
        ]
        save_record(tmp_path, record)
        monkeypatch.setenv("R2P_JSON", "1")
        capsys.readouterr()

        invoke(["status-run", "--work-id", work_id], base_path=tmp_path)

        payload = json.loads(capsys.readouterr().out)
        assert payload["approved_checkpoints"] == ["raw_requirement"] * 12
        assert "approved_checkpoints_full_list" not in payload
        assert not (tmp_path / ".req-to-plan" / work_id / "logs" / "status-run-approved-checkpoints.txt").exists()

    def test_human_keeps_status_decision_fields_uncapped(self, tmp_path, capsys):
        from tools.workflow_cli.models import ActiveArtifact, StaleArtifact

        work_id = "WF-20260625-compact-test"
        invoke(["run-start", "--work-id", work_id, "--requirement", "Compact status output"], base_path=tmp_path)
        record = load_record(tmp_path, work_id)
        record.open_routes = [
            OpenRoute(
                route_id=f"GAP-{i:03d}",
                from_stage=Stage.PLAN,
                owner_stage=Stage.SPEC,
                required_action=f"repair-{i}",
                status="open",
            )
            for i in range(12)
        ]
        record.stale_artifacts = [
            StaleArtifact(
                artifact=f"artifact-{i}.md",
                reason=f"reason-{i}",
                replaced_by=f"replacement-{i}.md",
                required_action=f"refresh-{i}",
            )
            for i in range(12)
        ]
        record.active_artifacts = [
            ActiveArtifact(
                stage=Stage.PLAN,
                artifact=f"active-{i}.md",
                version=i,
                status="stale",
            )
            for i in range(12)
        ]
        save_record(tmp_path, record)
        capsys.readouterr()

        invoke(["status-run", "--work-id", work_id], base_path=tmp_path)

        out = capsys.readouterr().out
        assert "GAP-011" in out
        assert "artifact-11.md" in out
        assert out.count("plan") >= 12


# ---------------------------------------------------------------------------
# status-next
# ---------------------------------------------------------------------------


class TestStatusNext:
    def test_prints_next_operation(self, capsys):
        with tempfile.TemporaryDirectory() as tmp:
            invoke(
                ["run-start", "--work-id", "WF-20260527-test", "--requirement", "Add rate limiting"],
                base_path=tmp,
            )
            invoke(
                ["status-next", "--work-id", "WF-20260527-test"],
                base_path=tmp,
            )
            out = capsys.readouterr().out
            assert len(out.strip()) > 0

    def test_decision_fields_remain_uncapped(self, tmp_path, capsys):
        from tools.workflow_cli.state import update_resume_context

        work_id = "WF-20260625-compact-test"
        invoke(["run-start", "--work-id", work_id, "--requirement", "Compact status output"], base_path=tmp_path)
        record = load_record(tmp_path, work_id)
        long_targets = ", ".join(f"file-{i}.py" for i in range(20))
        update_resume_context(
            record,
            next_operation=f"next operation requires {long_targets}",
            active_item=f"active item includes {long_targets}",
            reason=f"resume because {long_targets}",
        )
        save_record(tmp_path, record)
        capsys.readouterr()

        invoke(["status-next", "--work-id", work_id], base_path=tmp_path)

        out = capsys.readouterr().out
        assert "file-19.py" in out
        assert "shown" not in out
        assert "total" not in out
        assert "full_list" not in out


# ---------------------------------------------------------------------------
# tier-estimate
# ---------------------------------------------------------------------------


class TestTierEstimate:
    def test_prints_tier(self, capsys):
        invoke(["tier-estimate", "--text", "Add a simple logout button"])
        out = capsys.readouterr().out
        assert "light" in out.lower() or "standard" in out.lower()

    def test_migration_text_detects_modifier(self, capsys):
        invoke(["tier-estimate", "--text", "Migrate database from MySQL to PostgreSQL"])
        out = capsys.readouterr().out
        assert "migration" in out.lower() or "standard" in out.lower()


# ---------------------------------------------------------------------------
# run-resume
# ---------------------------------------------------------------------------


class TestRunResume:
    def test_prints_state_after_run_start(self, capsys):
        with tempfile.TemporaryDirectory() as tmp:
            invoke(
                ["run-start", "--work-id", "WF-20260527-test", "--requirement", "Add rate limiting"],
                base_path=tmp,
            )
            invoke(
                ["run-resume", "--work-id", "WF-20260527-test"],
                base_path=tmp,
            )
            out = capsys.readouterr().out
            assert len(out.strip()) > 0

    def test_missing_run_exits_nonzero(self):
        with tempfile.TemporaryDirectory() as tmp:
            with pytest.raises(SystemExit) as exc:
                main(["--base-path", str(tmp), "run-resume", "--work-id", "WF-20260527-nothere"])
            assert exc.value.code != 0

    def test_human_caps_reread_targets_with_recovery_file(self, tmp_path, capsys):
        from tools.workflow_cli.state import update_resume_context

        work_id = "WF-20260625-compact-test"
        invoke(["run-start", "--work-id", work_id, "--requirement", "Compact status output"], base_path=tmp_path)
        record = load_record(tmp_path, work_id)
        update_resume_context(record, reread_targets=[f"file-{i}.py" for i in range(20)])
        save_record(tmp_path, record)
        capsys.readouterr()

        invoke(["run-resume", "--work-id", work_id], base_path=tmp_path)

        out = capsys.readouterr().out
        recovery = tmp_path / ".req-to-plan" / work_id / "logs" / "run-resume-reread-targets.txt"
        assert "required_reread_targets" in out
        assert "15 shown" in out
        assert "20 total" in out
        assert f".req-to-plan/{work_id}/logs/run-resume-reread-targets.txt" in out
        assert recovery.exists()
        assert "file-19.py" in recovery.read_text(encoding="utf-8")

    def test_human_keeps_short_reread_targets_without_recovery_file(self, tmp_path, capsys):
        from tools.workflow_cli.state import update_resume_context

        work_id = "WF-20260625-compact-test"
        invoke(["run-start", "--work-id", work_id, "--requirement", "Compact status output"], base_path=tmp_path)
        record = load_record(tmp_path, work_id)
        update_resume_context(record, reread_targets=[f"file-{i}.py" for i in range(3)])
        save_record(tmp_path, record)
        capsys.readouterr()

        invoke(["run-resume", "--work-id", work_id], base_path=tmp_path)

        out = capsys.readouterr().out
        assert "required_reread_targets" in out
        assert "file-2.py" in out
        assert "shown" not in out
        assert "total" not in out
        assert f".req-to-plan/{work_id}/logs/run-resume-reread-targets.txt" not in out
        assert not (tmp_path / ".req-to-plan" / work_id / "logs" / "run-resume-reread-targets.txt").exists()

    def test_human_falls_back_to_full_reread_targets_when_recovery_write_fails(self, tmp_path, capsys):
        from tools.workflow_cli.state import update_resume_context

        work_id = "WF-20260625-compact-test"
        invoke(["run-start", "--work-id", work_id, "--requirement", "Compact status output"], base_path=tmp_path)
        record = load_record(tmp_path, work_id)
        update_resume_context(record, reread_targets=[f"file-{i}.py" for i in range(20)])
        save_record(tmp_path, record)
        logs_path = tmp_path / ".req-to-plan" / work_id / "logs"
        logs_path.write_text("not a directory", encoding="utf-8")
        capsys.readouterr()

        invoke(["run-resume", "--work-id", work_id], base_path=tmp_path)

        out = capsys.readouterr().out
        assert "15 shown" not in out
        assert "20 total" not in out
        assert f".req-to-plan/{work_id}/logs/run-resume-reread-targets.txt" not in out
        assert "file-19.py" in out

    def test_json_keeps_full_reread_targets_without_recovery_file(self, tmp_path, capsys, monkeypatch):
        from tools.workflow_cli.state import update_resume_context

        work_id = "WF-20260625-compact-test"
        invoke(["run-start", "--work-id", work_id, "--requirement", "Compact status output"], base_path=tmp_path)
        record = load_record(tmp_path, work_id)
        update_resume_context(record, reread_targets=[f"file-{i}.py" for i in range(20)])
        save_record(tmp_path, record)
        monkeypatch.setenv("R2P_JSON", "1")
        capsys.readouterr()

        invoke(["run-resume", "--work-id", work_id], base_path=tmp_path)

        payload = json.loads(capsys.readouterr().out)
        assert payload["required_reread_targets"] == [f"file-{i}.py" for i in range(20)]
        assert "required_reread_targets_full_list" not in payload
        assert not (tmp_path / ".req-to-plan" / work_id / "logs" / "run-resume-reread-targets.txt").exists()

    def test_human_keeps_resume_decision_fields_uncapped(self, tmp_path, capsys):
        from tools.workflow_cli.state import update_resume_context

        work_id = "WF-20260625-compact-test"
        invoke(["run-start", "--work-id", work_id, "--requirement", "Compact status output"], base_path=tmp_path)
        record = load_record(tmp_path, work_id)
        long_targets = ", ".join(f"file-{i}.py" for i in range(20))
        update_resume_context(
            record,
            next_operation=f"next operation requires {long_targets}",
            active_item=f"active item includes {long_targets}",
            reason=f"resume because {long_targets}",
            reread_targets=[f"short-{i}.py" for i in range(3)],
        )
        save_record(tmp_path, record)
        capsys.readouterr()

        invoke(["run-resume", "--work-id", work_id], base_path=tmp_path)

        out = capsys.readouterr().out
        assert "file-19.py" in out
        assert "shown" not in out
        assert "total" not in out


# ---------------------------------------------------------------------------
# run-close
# ---------------------------------------------------------------------------


class TestRunClose:
    def test_refuses_checkpoint_approved_non_plan_stage(self):
        with tempfile.TemporaryDirectory() as tmp:
            work_id = "WF-20260527-test"
            invoke(["run-start", "--work-id", work_id, "--requirement", "foo"], base_path=tmp)
            record = load_record(tmp, work_id)
            record.status = RunStatus.CHECKPOINT_APPROVED
            record.current_stage = Stage.REQUIREMENT_BRIEF
            record.approved_checkpoints = [requirement_checkpoint()]
            save_record(tmp, record)

            invoke(["run-close", "--work-id", work_id], base_path=tmp, expect_exit=6)

            record = load_record(tmp, work_id)
            assert record.status == RunStatus.CHECKPOINT_APPROVED
            assert record.current_stage == Stage.REQUIREMENT_BRIEF

    def test_refuses_close_with_open_routes(self):
        with tempfile.TemporaryDirectory() as tmp:
            work_id = "WF-20260527-test"
            invoke(["run-start", "--work-id", work_id, "--requirement", "foo"], base_path=tmp)
            record = load_record(tmp, work_id)
            record.status = RunStatus.CHECKPOINT_APPROVED
            record.current_stage = Stage.PLAN
            record.approved_checkpoints = [plan_checkpoint()]
            from tools.workflow_cli.models import ActiveArtifact
            record.active_artifacts = [ActiveArtifact(
                stage=Stage.PLAN, artifact="07-plan.md", version=1, status="approved")]
            record.open_routes = [
                OpenRoute(
                    route_id="GAP-001",
                    from_stage=Stage.PLAN,
                    owner_stage=Stage.SPEC,
                    required_action="repair traceability",
                    status="open",
                )
            ]
            save_record(tmp, record)
            run_dir = Path(tmp) / ".req-to-plan" / work_id
            (run_dir / "07-plan.md").write_text("---\nr2p_version: 1\n---\nplan content", encoding="utf-8")

            invoke(["run-close", "--work-id", work_id], base_path=tmp, expect_exit=6)

            record = load_record(tmp, work_id)
            assert record.status == RunStatus.CHECKPOINT_APPROVED
            assert record.current_stage == Stage.PLAN

    def test_closes_only_after_approved_plan_checkpoint(self):
        with tempfile.TemporaryDirectory() as tmp:
            work_id = "WF-20260527-test"
            invoke(["run-start", "--work-id", work_id, "--requirement", "foo"], base_path=tmp)
            record = load_record(tmp, work_id)
            record.status = RunStatus.CHECKPOINT_APPROVED
            record.current_stage = Stage.PLAN
            record.approved_checkpoints = [plan_checkpoint()]
            from tools.workflow_cli.models import ActiveArtifact
            record.active_artifacts = [ActiveArtifact(
                stage=Stage.PLAN, artifact="07-plan.md", version=1, status="approved")]
            save_record(tmp, record)
            run_dir = Path(tmp) / ".req-to-plan" / work_id
            (run_dir / "07-plan.md").write_text("---\nr2p_version: 1\n---\nplan content", encoding="utf-8")

            invoke(["run-close", "--work-id", work_id], base_path=tmp)

            record = load_record(tmp, work_id)
            assert record.status == RunStatus.CLOSED_AT_PLAN_CHECKPOINT
            assert record.current_stage == Stage.CLOSED


# ---------------------------------------------------------------------------
# run-reopen
# ---------------------------------------------------------------------------


class TestRunReopen:
    def test_reopen_copies_context_pack_files(self, tmp_path):
        source = "WF-20260605-reopen-context"
        repo = tmp_path / "repo"
        repo.mkdir()
        (repo / "requirements.txt").write_text("pyyaml>=6.0\n", encoding="utf-8")
        invoke(
            [
                "run-start", "--work-id", source,
                "--requirement", "add rate limiting",
                "--repo-path", str(repo),
            ],
            base_path=tmp_path,
        )
        record = load_record(tmp_path, source)
        record.status = RunStatus.CLOSED_AT_PLAN_CHECKPOINT
        record.current_stage = Stage.CLOSED
        record.approved_checkpoints = [plan_checkpoint()]
        save_record(tmp_path, record)

        source_dir = tmp_path / ".req-to-plan" / source
        invoke(
            ["run-reopen", "--from", source, "--stage", "plan", "--reason", "repair plan"],
            base_path=tmp_path,
        )

        reopened_dir = tmp_path / ".req-to-plan" / f"{source}-r1"
        for context_file in ("02-project-context.json", "02-project-context.md"):
            assert (reopened_dir / context_file).read_text(encoding="utf-8") == (
                source_dir / context_file
            ).read_text(encoding="utf-8")

    def test_repeated_reopen_uses_next_free_suffix(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = "WF-20260527-test"
            invoke(["run-start", "--work-id", source, "--requirement", "foo"], base_path=tmp)
            record = load_record(tmp, source)
            record.status = RunStatus.CLOSED_AT_PLAN_CHECKPOINT
            record.current_stage = Stage.CLOSED
            record.approved_checkpoints = [plan_checkpoint()]
            save_record(tmp, record)

            invoke(
                ["run-reopen", "--from", source, "--stage", "spec", "--reason", "fix gap"],
                base_path=tmp,
            )
            invoke(
                ["run-reopen", "--from", source, "--stage", "spec", "--reason", "fix another gap"],
                base_path=tmp,
            )

            assert (Path(tmp) / ".req-to-plan" / f"{source}-r1").exists()
            assert (Path(tmp) / ".req-to-plan" / f"{source}-r2").exists()

    def test_reopen_skips_suffix_reserved_by_archived_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            source = "WF-20260527-test"
            invoke(["run-start", "--work-id", source, "--requirement", "foo"], base_path=base)
            record = load_record(base, source)
            record.status = RunStatus.CLOSED_AT_PLAN_CHECKPOINT
            record.current_stage = Stage.CLOSED
            record.approved_checkpoints = [plan_checkpoint()]
            save_record(base, record)
            (base / ".req-to-plan" / "archive" / f"{source}-r1").mkdir(parents=True)

            invoke(
                ["run-reopen", "--from", source, "--stage", "spec", "--reason", "fix gap"],
                base_path=base,
            )

            assert not (base / ".req-to-plan" / f"{source}-r1").exists()
            assert (base / ".req-to-plan" / f"{source}-r2").exists()

    def test_reopen_does_not_delete_candidate_created_by_concurrent_reopen(
        self, monkeypatch
    ):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            source = "WF-20260527-race"
            invoke(["run-start", "--work-id", source, "--requirement", "foo"], base_path=base)
            record = load_record(base, source)
            record.status = RunStatus.CLOSED_AT_PLAN_CHECKPOINT
            record.current_stage = Stage.CLOSED
            record.approved_checkpoints = [plan_checkpoint()]
            save_record(base, record)

            raced_dir = base / ".req-to-plan" / f"{source}-r1"
            original_mkdir = Path.mkdir

            def create_then_race(self_path, *args, **kwargs):
                if self_path == raced_dir:
                    original_mkdir(self_path, parents=True, exist_ok=False)
                    (self_path / "run.md").write_text(
                        "created by concurrent reopen\n", encoding="utf-8"
                    )
                    raise FileExistsError("simulated concurrent reopen")
                return original_mkdir(self_path, *args, **kwargs)

            monkeypatch.setattr(Path, "mkdir", create_then_race)

            with pytest.raises(FileExistsError):
                main(
                    [
                        "--base-path",
                        str(base),
                        "run-reopen",
                        "--from",
                        source,
                        "--stage",
                        "spec",
                        "--reason",
                        "fix gap",
                    ]
                )

            assert raced_dir.exists()
            assert (raced_dir / "run.md").read_text(encoding="utf-8") == (
                "created by concurrent reopen\n"
            )

    def test_rejects_closed_as_target_stage(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = "WF-20260527-test"
            invoke(["run-start", "--work-id", source, "--requirement", "foo"], base_path=tmp)
            record = load_record(tmp, source)
            record.status = RunStatus.CLOSED_AT_PLAN_CHECKPOINT
            record.current_stage = Stage.CLOSED
            record.approved_checkpoints = [plan_checkpoint()]
            save_record(tmp, record)

            invoke(
                ["run-reopen", "--from", source, "--stage", "closed", "--reason", "fix gap"],
                base_path=tmp,
                expect_exit=2,
            )

            assert not (Path(tmp) / ".req-to-plan" / f"{source}-r1").exists()

    def test_reopen_executing_rejects_symlinked_source_without_writing_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp) / "workspace"
            base.mkdir()
            outside = Path(tmp) / "outside-run"
            source = "WF-20260527-executing"
            invoke(["run-start", "--work-id", source, "--requirement", "foo"], base_path=base)
            record = load_record(base, source)
            record.status = RunStatus.EXECUTING
            save_record(base, record)

            source_dir = base / ".req-to-plan" / source
            source_dir.rename(outside)
            source_dir.symlink_to(outside, target_is_directory=True)
            target_run_md_before = (outside / "run.md").read_text(encoding="utf-8")

            invoke(
                ["run-reopen", "--from", source, "--stage", "spec", "--reason", "repair spec"],
                base_path=base,
                expect_exit=6,
            )

            assert source_dir.is_symlink()
            assert (outside / "run.md").read_text(encoding="utf-8") == target_run_md_before
            assert not (base / ".req-to-plan" / f"{source}-r1").exists()

    def test_reopen_from_executing_rolls_back_new_run_on_source_save_failure(
        self, monkeypatch
    ):
        """SPEC-STATE-001: if source_mgr.save raises after new_run_dir is created,
        the new run dir must be removed (no orphan) and source must stay EXECUTING."""
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            source = "WF-20260527-exec-rb"
            invoke(
                ["run-start", "--work-id", source, "--requirement", "foo"],
                base_path=base,
            )
            record = load_record(base, source)
            record.status = RunStatus.EXECUTING
            record.current_stage = Stage.CLOSED
            save_record(base, record)

            # Patch RunStateManager.save to succeed the first call (new record)
            # and raise on the second call (source record).
            from tools.workflow_cli.state import RunStateManager as _RSM

            original_save = _RSM.save
            call_count = {"n": 0}

            def patched_save(self_mgr, rec):
                call_count["n"] += 1
                if call_count["n"] == 2:
                    raise OSError("simulated disk failure on source save")
                return original_save(self_mgr, rec)

            monkeypatch.setattr(_RSM, "save", patched_save)

            with pytest.raises((OSError, SystemExit)):
                main(
                    [
                        "--base-path",
                        str(base),
                        "run-reopen",
                        "--from",
                        source,
                        "--stage",
                        "plan",
                        "--reason",
                        "repair plan",
                    ]
                )

            # No orphan new run dir
            new_run_dir = base / ".req-to-plan" / f"{source}-r1"
            assert not new_run_dir.exists(), "Orphan new_run_dir must not exist after rollback"

            # Source stays EXECUTING (un-patched load)
            monkeypatch.undo()
            source_rec = load_record(base, source)
            assert source_rec.status == RunStatus.EXECUTING, (
                f"Source must stay EXECUTING after failed save, got {source_rec.status}"
            )

    def test_reopen_from_executing_rolls_back_new_run_on_new_record_save_failure(
        self, monkeypatch
    ):
        """SPEC-STATE-001: if the NEW record save raises after new_run_dir is
        populated, the new run dir must be removed (no orphan)."""
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            source = "WF-20260527-exec-rb2"
            invoke(
                ["run-start", "--work-id", source, "--requirement", "foo"],
                base_path=base,
            )
            record = load_record(base, source)
            record.status = RunStatus.EXECUTING
            record.current_stage = Stage.CLOSED
            save_record(base, record)

            from tools.workflow_cli.state import RunStateManager as _RSM

            def patched_save(self_mgr, rec):
                raise OSError("simulated disk failure on new record save")

            monkeypatch.setattr(_RSM, "save", patched_save)

            with pytest.raises((OSError, SystemExit)):
                main(
                    [
                        "--base-path",
                        str(base),
                        "run-reopen",
                        "--from",
                        source,
                        "--stage",
                        "plan",
                        "--reason",
                        "repair plan",
                    ]
                )

            new_run_dir = base / ".req-to-plan" / f"{source}-r1"
            assert not new_run_dir.exists(), (
                "Orphan new_run_dir must not exist after new-record save rollback"
            )

            monkeypatch.undo()
            source_rec = load_record(base, source)
            assert source_rec.status == RunStatus.EXECUTING

    def test_reopen_from_executing_normal_path_unchanged(self):
        """SPEC-STATE-001: normal reopen from EXECUTING still creates new run and
        transitions source to CLOSED_AT_PLAN_CHECKPOINT (existing behaviour)."""
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            source = "WF-20260527-exec-normal"
            invoke(
                ["run-start", "--work-id", source, "--requirement", "foo"],
                base_path=base,
            )
            record = load_record(base, source)
            record.status = RunStatus.EXECUTING
            record.current_stage = Stage.CLOSED
            save_record(base, record)

            invoke(
                [
                    "run-reopen",
                    "--from",
                    source,
                    "--stage",
                    "plan",
                    "--reason",
                    "repair plan",
                ],
                base_path=base,
            )

            new_run_dir = base / ".req-to-plan" / f"{source}-r1"
            assert new_run_dir.exists(), "New run dir must exist after normal reopen"
            assert (new_run_dir / "run.md").exists(), "New run.md must exist"

            source_rec = load_record(base, source)
            assert source_rec.status == RunStatus.CLOSED_AT_PLAN_CHECKPOINT, (
                f"Source must be CLOSED_AT_PLAN_CHECKPOINT, got {source_rec.status}"
            )


# ---------------------------------------------------------------------------
# tier-lock
# ---------------------------------------------------------------------------


class TestTierLock:
    def test_lock_requires_confirm(self):
        with tempfile.TemporaryDirectory() as tmp:
            work_id = "WF-20260527-test"
            invoke(
                ["run-start", "--work-id", work_id, "--requirement", "Add rate limiting"],
                base_path=tmp,
            )

            invoke(
                ["tier-lock", "--work-id", work_id, "--base", "standard"],
                base_path=tmp,
                expect_exit=2,
            )

            record = load_record(tmp, work_id)
            assert record.tier_locked is None

    def test_lock_at_floor_succeeds(self, capsys):
        with tempfile.TemporaryDirectory() as tmp:
            invoke(
                ["run-start", "--work-id", "WF-20260527-test", "--requirement", "Add rate limiting"],
                base_path=tmp,
            )
            # lock at standard (safe, always >= floor)
            invoke(
                ["tier-lock", "--work-id", "WF-20260527-test", "--base", "standard", "--confirm"],
                base_path=tmp,
            )
            out = capsys.readouterr().out
            assert "lock" in out.lower() or "tier" in out.lower() or "standard" in out.lower()

    def test_lock_rejects_non_active_stage_draft(self, capsys):
        with tempfile.TemporaryDirectory() as tmp:
            work_id = "WF-20260527-test"
            invoke(
                ["run-start", "--work-id", work_id, "--requirement", "Add rate limiting"],
                base_path=tmp,
            )
            record = load_record(tmp, work_id)
            record.status = RunStatus.CHECKPOINT_APPROVED
            save_record(tmp, record)

            invoke(
                ["tier-lock", "--work-id", work_id, "--base", "standard", "--confirm"],
                base_path=tmp,
                expect_exit=6,
            )

            out = capsys.readouterr().out
            assert "must be active_stage_draft" in out
            assert load_record(tmp, work_id).tier_locked is None


# ---------------------------------------------------------------------------
# gate-quality
# ---------------------------------------------------------------------------


class TestGateQuality:
    def test_runs_quality_check_after_tier_lock(self, capsys):
        with tempfile.TemporaryDirectory() as tmp:
            invoke(
                ["run-start", "--work-id", "WF-20260527-test", "--requirement", "Add rate limiting"],
                base_path=tmp,
            )
            invoke(
                ["tier-lock", "--work-id", "WF-20260527-test", "--base", "standard", "--confirm"],
                base_path=tmp,
            )
            invoke(
                ["stage-produce", "--work-id", "WF-20260527-test", "--stage", "raw_requirement", "--content", "Some content"],
                base_path=tmp,
            )
            invoke(
                ["stage-ready", "--work-id", "WF-20260527-test", "--stage", "raw_requirement"],
                base_path=tmp,
            )
            # quality gate may pass or fail (structural), just check it runs cleanly
            with pytest.raises(SystemExit) as exc:
                main(["--base-path", str(tmp), "gate-quality", "--work-id", "WF-20260527-test", "--stage", "raw_requirement"])
            # exit_code 0 (pass) or 3 (gate fail) are both acceptable
            assert exc.value.code in (0, 3)
            out = capsys.readouterr().out
            assert len(out.strip()) > 0

    def test_pass_persists_ready_for_checkpoint_review(self):
        with tempfile.TemporaryDirectory() as tmp:
            work_id = "WF-20260527-test"
            invoke(
                ["run-start", "--work-id", work_id, "--requirement", "Add rate limiting"],
                base_path=tmp,
            )
            invoke(
                ["tier-lock", "--work-id", work_id, "--base", "standard", "--confirm"],
                base_path=tmp,
            )
            invoke(
                ["stage-produce", "--work-id", work_id, "--stage", "raw_requirement", "--content", "Some content"],
                base_path=tmp,
            )
            invoke(
                ["stage-ready", "--work-id", work_id, "--stage", "raw_requirement"],
                base_path=tmp,
            )

            invoke(["gate-quality", "--work-id", work_id, "--stage", "raw_requirement"], base_path=tmp)

            record = load_record(tmp, work_id)
            assert record.status == RunStatus.READY_FOR_CHECKPOINT_REVIEW

    def test_failure_persists_quality_gate_failed(self):
        with tempfile.TemporaryDirectory() as tmp:
            work_id = "WF-20260527-test"
            invoke(
                ["run-start", "--work-id", work_id, "--requirement", "Add rate limiting"],
                base_path=tmp,
            )
            invoke(
                ["tier-lock", "--work-id", work_id, "--base", "standard", "--confirm"],
                base_path=tmp,
            )
            # Produce artifact with content that will fail the quality gate (unclosed upstream ID)
            invoke(
                ["stage-produce", "--work-id", work_id, "--stage", "raw_requirement",
                 "--content", "REQ-API-100 some requirement without closure tag"],
                base_path=tmp,
            )
            invoke(
                ["stage-ready", "--work-id", work_id, "--stage", "raw_requirement"],
                base_path=tmp,
            )

            invoke(
                ["gate-quality", "--work-id", work_id, "--stage", "raw_requirement"],
                base_path=tmp,
                expect_exit=3,
            )

            record = load_record(tmp, work_id)
            assert record.status == RunStatus.QUALITY_GATE_FAILED


class TestGateQualityReadiness:
    def test_gate_quality_refuses_unready_artifact(self):
        with tempfile.TemporaryDirectory() as tmp:
            work_id = "WF-20260527-nrdy"
            invoke(["run-start", "--work-id", work_id, "--requirement", "foo"], base_path=tmp)
            invoke(["tier-lock", "--work-id", work_id, "--base", "light", "--confirm"], base_path=tmp)
            invoke(["stage-produce", "--work-id", work_id, "--stage", "raw_requirement",
                    "--content", "draft only, never marked ready"], base_path=tmp)
            invoke(["gate-quality", "--work-id", work_id, "--stage", "raw_requirement"],
                   base_path=tmp, expect_exit=6)

    def test_gate_quality_accepts_ready_artifact(self):
        with tempfile.TemporaryDirectory() as tmp:
            work_id = "WF-20260527-rady"
            invoke(["run-start", "--work-id", work_id, "--requirement", "foo"], base_path=tmp)
            invoke(["tier-lock", "--work-id", work_id, "--base", "light", "--confirm"], base_path=tmp)
            invoke(["stage-produce", "--work-id", work_id, "--stage", "raw_requirement",
                    "--content", "real content"], base_path=tmp)
            invoke(["stage-ready", "--work-id", work_id, "--stage", "raw_requirement"], base_path=tmp)
            invoke(["gate-quality", "--work-id", work_id, "--stage", "raw_requirement"], base_path=tmp)

    def test_gate_quality_without_tier_lock_keeps_tier_lock_reachable(self):
        with tempfile.TemporaryDirectory() as tmp:
            work_id = "WF-20260527-gqtl"
            invoke(["run-start", "--work-id", work_id, "--requirement", "foo"], base_path=tmp)
            invoke(["stage-produce", "--work-id", work_id, "--stage", "raw_requirement",
                    "--content", "real content"], base_path=tmp)
            invoke(["stage-ready", "--work-id", work_id, "--stage", "raw_requirement"], base_path=tmp)

            invoke(["gate-quality", "--work-id", work_id, "--stage", "raw_requirement"],
                   base_path=tmp, expect_exit=3)

            record = load_record(tmp, work_id)
            assert record.status == RunStatus.ACTIVE_STAGE_DRAFT
            invoke(["tier-lock", "--work-id", work_id, "--base", "standard", "--confirm"],
                   base_path=tmp)

    def test_gate_quality_refuses_wrong_stage_or_stale_version(self):
        with tempfile.TemporaryDirectory() as tmp:
            work_id = "WF-20260527-gqst"
            invoke(["run-start", "--work-id", work_id, "--requirement", "foo"], base_path=tmp)
            invoke(["tier-lock", "--work-id", work_id, "--base", "light", "--confirm"], base_path=tmp)
            invoke(["stage-produce", "--work-id", work_id, "--stage", "raw_requirement",
                    "--content", "real content"], base_path=tmp)
            invoke(["stage-ready", "--work-id", work_id, "--stage", "raw_requirement"], base_path=tmp)
            invoke(["gate-quality", "--work-id", work_id, "--stage", "requirement_brief"],
                   base_path=tmp, expect_exit=6)
            run_dir = Path(tmp) / ".req-to-plan" / work_id
            (run_dir / "00-raw-requirement.md").write_text(
                "---\nr2p_version: 2\n---\nfoo", encoding="utf-8")
            invoke(["gate-quality", "--work-id", work_id, "--stage", "raw_requirement"],
                   base_path=tmp, expect_exit=6)


class TestGateQualityRepeatGuard:
    def _to_ready(self, tmp, work_id):
        invoke(["run-start", "--work-id", work_id, "--requirement", "foo"], base_path=tmp)
        invoke(["tier-lock", "--work-id", work_id, "--base", "light", "--confirm"], base_path=tmp)
        invoke(["stage-produce", "--work-id", work_id, "--stage", "raw_requirement",
                "--content", "real content"], base_path=tmp)
        invoke(["stage-ready", "--work-id", work_id, "--stage", "raw_requirement"], base_path=tmp)

    def test_gate_quality_refused_when_already_quality_failed(self):
        with tempfile.TemporaryDirectory() as tmp:
            work_id = "WF-20260527-gqr"
            self._to_ready(tmp, work_id)
            record = load_record(tmp, work_id)
            record.status = RunStatus.QUALITY_GATE_FAILED
            save_record(tmp, record)
            # Re-running gate-quality from a non-draft state must be a clean conflict, not a traceback.
            invoke(["gate-quality", "--work-id", work_id, "--stage", "raw_requirement"],
                   base_path=tmp, expect_exit=6)

    def test_gate_quality_refused_when_already_ready_for_review(self):
        with tempfile.TemporaryDirectory() as tmp:
            work_id = "WF-20260527-gqr2"
            self._to_ready(tmp, work_id)
            invoke(["gate-quality", "--work-id", work_id, "--stage", "raw_requirement"], base_path=tmp)
            # Now READY_FOR_CHECKPOINT_REVIEW; a duplicate run must not raise an illegal self-transition.
            invoke(["gate-quality", "--work-id", work_id, "--stage", "raw_requirement"],
                   base_path=tmp, expect_exit=6)


# ---------------------------------------------------------------------------
# stage-update
# ---------------------------------------------------------------------------


class TestStageUpdate:
    def test_increments_version(self):
        with tempfile.TemporaryDirectory() as tmp:
            invoke(
                ["run-start", "--work-id", "WF-20260527-test", "--requirement", "Add rate limiting"],
                base_path=tmp,
            )
            invoke(
                ["stage-produce", "--work-id", "WF-20260527-test", "--stage", "raw_requirement", "--content", "v1 content"],
                base_path=tmp,
            )
            invoke(
                ["stage-update", "--work-id", "WF-20260527-test", "--stage", "raw_requirement", "--content", "v2 content"],
                base_path=tmp,
            )
            artifact = Path(tmp) / ".req-to-plan" / "WF-20260527-test" / "00-raw-requirement.md"
            text = artifact.read_text()
            assert "v2 content" in text
            assert "r2p_version: 2" in text


# ---------------------------------------------------------------------------
# stage-ready
# ---------------------------------------------------------------------------


class TestStageReady:
    def test_marks_artifact_ready(self):
        with tempfile.TemporaryDirectory() as tmp:
            invoke(
                ["run-start", "--work-id", "WF-20260527-test", "--requirement", "Add rate limiting"],
                base_path=tmp,
            )
            invoke(
                ["stage-produce", "--work-id", "WF-20260527-test", "--stage", "raw_requirement", "--content", "Some content"],
                base_path=tmp,
            )
            invoke(
                ["stage-ready", "--work-id", "WF-20260527-test", "--stage", "raw_requirement"],
                base_path=tmp,
            )
            artifact = Path(tmp) / ".req-to-plan" / "WF-20260527-test" / "00-raw-requirement.md"
            text = artifact.read_text()
            assert "r2p_status: ready" in text

    def test_stage_ready_from_quality_gate_failed_returns_to_draft(self):
        with tempfile.TemporaryDirectory() as tmp:
            work_id = "WF-20260527-ready-repair"
            invoke(["run-start", "--work-id", work_id, "--requirement", "foo"], base_path=tmp)
            invoke(["stage-produce", "--work-id", work_id, "--stage", "raw_requirement",
                    "--content", "real"], base_path=tmp)
            record = load_record(tmp, work_id)
            record.status = RunStatus.QUALITY_GATE_FAILED
            save_record(tmp, record)

            invoke(["stage-ready", "--work-id", work_id, "--stage", "raw_requirement"],
                   base_path=tmp)

            record = load_record(tmp, work_id)
            assert record.status == RunStatus.ACTIVE_STAGE_DRAFT
            assert record.active_artifacts[0].status == "ready"

    def test_stage_ready_refuses_changes_requested_without_repair(self):
        with tempfile.TemporaryDirectory() as tmp:
            work_id = "WF-20260527-ready-cr"
            invoke(["run-start", "--work-id", work_id, "--requirement", "foo"], base_path=tmp)
            invoke(["tier-lock", "--work-id", work_id, "--base", "light", "--confirm"], base_path=tmp)
            invoke(["stage-produce", "--work-id", work_id, "--stage", "raw_requirement",
                    "--content", "real"], base_path=tmp)
            invoke(["stage-ready", "--work-id", work_id, "--stage", "raw_requirement"], base_path=tmp)
            invoke(["gate-quality", "--work-id", work_id, "--stage", "raw_requirement"], base_path=tmp)
            invoke(["review-checkpoint", "--work-id", work_id, "--stage", "raw_requirement"],
                   base_path=tmp)
            invoke(["checkpoint-decide", "--work-id", work_id, "--stage", "raw_requirement",
                    "--decision", "changes_requested"], base_path=tmp)

            invoke(["stage-ready", "--work-id", work_id, "--stage", "raw_requirement"],
                   base_path=tmp, expect_exit=6)

            record = load_record(tmp, work_id)
            assert record.status == RunStatus.CHECKPOINT_CHANGES_REQUESTED
            assert record.active_artifacts[0].version == 1
            assert record.active_artifacts[0].status == "ready"

    def test_refuses_after_checkpoint_approval_without_resetting_artifact(self):
        with tempfile.TemporaryDirectory() as tmp:
            work_id = "WF-20260527-ready-approved"
            invoke(["run-start", "--work-id", work_id, "--requirement", "foo"], base_path=tmp)
            invoke(["tier-lock", "--work-id", work_id, "--base", "light", "--confirm"], base_path=tmp)
            invoke(["stage-produce", "--work-id", work_id, "--stage", "raw_requirement",
                    "--content", "real"], base_path=tmp)
            invoke(["stage-ready", "--work-id", work_id, "--stage", "raw_requirement"], base_path=tmp)
            invoke(["gate-quality", "--work-id", work_id, "--stage", "raw_requirement"], base_path=tmp)
            invoke(["review-checkpoint", "--work-id", work_id, "--stage", "raw_requirement"],
                   base_path=tmp)
            invoke(["checkpoint-decide", "--work-id", work_id, "--stage", "raw_requirement",
                    "--decision", "approved", "--confirm"], base_path=tmp)

            invoke(["stage-ready", "--work-id", work_id, "--stage", "raw_requirement"],
                   base_path=tmp, expect_exit=6)

            record = load_record(tmp, work_id)
            assert record.status == RunStatus.CHECKPOINT_APPROVED
            assert record.active_artifacts[0].status == "approved"
            invoke(["stage-advance", "--work-id", work_id], base_path=tmp)

    def test_refuses_after_stage_advance_without_downgrading_approved_artifact(self):
        with tempfile.TemporaryDirectory() as tmp:
            work_id = "WF-20260527-ready-advanced"
            invoke(["run-start", "--work-id", work_id, "--requirement", "foo"], base_path=tmp)
            invoke(["tier-lock", "--work-id", work_id, "--base", "light", "--confirm"], base_path=tmp)
            invoke(["stage-produce", "--work-id", work_id, "--stage", "raw_requirement",
                    "--content", "real"], base_path=tmp)
            invoke(["stage-ready", "--work-id", work_id, "--stage", "raw_requirement"], base_path=tmp)
            invoke(["gate-quality", "--work-id", work_id, "--stage", "raw_requirement"], base_path=tmp)
            invoke(["review-checkpoint", "--work-id", work_id, "--stage", "raw_requirement"],
                   base_path=tmp)
            invoke(["checkpoint-decide", "--work-id", work_id, "--stage", "raw_requirement",
                    "--decision", "approved", "--confirm"], base_path=tmp)
            invoke(["stage-advance", "--work-id", work_id], base_path=tmp)

            invoke(["stage-ready", "--work-id", work_id, "--stage", "raw_requirement"],
                   base_path=tmp, expect_exit=6)

            record = load_record(tmp, work_id)
            assert record.status == RunStatus.NEXT_STAGE
            assert record.current_stage == Stage.REQUIREMENT_BRIEF
            from tools.workflow_cli.state import get_active_artifact
            aa = get_active_artifact(record, Stage.RAW_REQUIREMENT)
            assert aa.status == "approved"

    def test_refuses_non_current_stage_ready(self):
        with tempfile.TemporaryDirectory() as tmp:
            work_id = "WF-20260527-ready-stage"
            invoke(["run-start", "--work-id", work_id, "--requirement", "foo"], base_path=tmp)
            record = load_record(tmp, work_id)
            record.current_stage = Stage.REQUIREMENT_BRIEF
            save_record(tmp, record)

            invoke(["stage-ready", "--work-id", work_id, "--stage", "raw_requirement"],
                   base_path=tmp, expect_exit=6)

            record = load_record(tmp, work_id)
            assert record.status == RunStatus.ACTIVE_STAGE_DRAFT
            assert record.active_artifacts[0].status == "draft"


# ---------------------------------------------------------------------------
# install_cli
# ---------------------------------------------------------------------------


class TestInstallCli:
    def test_install_stub(self, capsys, tmp_path):
        from tools.workflow_cli.install_cli import main as install_main
        from tools.workflow_cli.install import InstallService

        repo_root = Path(__file__).parent.parent
        svc = InstallService(
            repo_root=repo_root,
            manifest_root=tmp_path / "manifest",
            platform_homes={
                "claude": tmp_path / "claude",
                "codex": tmp_path / "codex",
                "gemini": tmp_path / "gemini",
            },
        )
        with __import__("unittest.mock", fromlist=["patch"]).patch(
            "tools.workflow_cli.install_cli._make_service", return_value=svc
        ):
            install_main(["install", "--platform", "claude"])
        out = capsys.readouterr().out
        assert "install" in out.lower()

    def test_install_accepts_comma_platform_list(self, capsys, tmp_path):
        from tools.workflow_cli.install_cli import main as install_main
        from tools.workflow_cli.install import InstallService

        repo_root = Path(__file__).parent.parent
        svc = InstallService(
            repo_root=repo_root,
            manifest_root=tmp_path / "manifest",
            platform_homes={
                "claude": tmp_path / "claude",
                "codex": tmp_path / "codex",
                "gemini": tmp_path / "gemini",
            },
        )

        with __import__("unittest.mock", fromlist=["patch"]).patch(
            "tools.workflow_cli.install_cli._make_service", return_value=svc
        ):
            install_main(["install", "--platform", "claude,codex,gemini"])

        out = capsys.readouterr().out
        assert "platform='claude'" in out
        assert "platform='codex'" in out
        assert "platform='gemini'" in out
        assert (tmp_path / "manifest" / "install" / "claude.yaml").exists()
        assert (tmp_path / "manifest" / "install" / "codex.yaml").exists()
        assert (tmp_path / "manifest" / "install" / "gemini.yaml").exists()

    def test_uninstall_accepts_comma_platform_list(self, capsys, tmp_path):
        from tools.workflow_cli.install_cli import main as install_main
        from tools.workflow_cli.install import InstallService

        repo_root = Path(__file__).parent.parent
        svc = InstallService(
            repo_root=repo_root,
            manifest_root=tmp_path / "manifest",
            platform_homes={
                "claude": tmp_path / "claude",
                "codex": tmp_path / "codex",
                "gemini": tmp_path / "gemini",
            },
        )
        svc.install("claude")
        svc.install("codex")
        svc.install("gemini")

        with __import__("unittest.mock", fromlist=["patch"]).patch(
            "tools.workflow_cli.install_cli._make_service", return_value=svc
        ):
            install_main(["uninstall", "--platform", "claude,codex,gemini"])

        out = capsys.readouterr().out
        assert "platform='claude'" in out
        assert "platform='codex'" in out
        assert "platform='gemini'" in out
        assert not (tmp_path / "manifest" / "install" / "claude.yaml").exists()
        assert not (tmp_path / "manifest" / "install" / "codex.yaml").exists()
        assert not (tmp_path / "manifest" / "install" / "gemini.yaml").exists()

    def test_uninstall_without_platform_removes_only_installed_platforms(self, capsys, tmp_path):
        from tools.workflow_cli.install_cli import main as install_main
        from tools.workflow_cli.install import InstallService

        repo_root = Path(__file__).parent.parent
        svc = InstallService(
            repo_root=repo_root,
            manifest_root=tmp_path / "manifest",
            platform_homes={
                "claude": tmp_path / "claude",
                "codex": tmp_path / "codex",
                "gemini": tmp_path / "gemini",
            },
        )
        svc.install("codex")

        from unittest.mock import patch
        with patch(
            "tools.workflow_cli.install_cli._make_service", return_value=svc
        ):
            install_main(["uninstall"])

        out = capsys.readouterr().out
        assert "platform='codex'" in out
        assert not (tmp_path / "manifest" / "install" / "codex.yaml").exists()

    def test_version(self, capsys):
        from tools.workflow_cli.install_cli import main as install_main
        from tools.workflow_cli.version import R2P_VERSION
        install_main(["version"])
        out = capsys.readouterr().out
        assert R2P_VERSION in out

    def test_status_stub(self, capsys):
        from tools.workflow_cli.install_cli import main as install_main
        install_main(["status"])
        out = capsys.readouterr().out
        assert len(out.strip()) > 0

    def test_no_args_prints_help(self, capsys):
        from tools.workflow_cli.install_cli import main as install_main
        install_main([])
        out = capsys.readouterr().out
        assert "install" in out and "uninstall" in out and "status" in out

    def test_version_flag(self, capsys):
        from tools.workflow_cli.install_cli import main as install_main
        from tools.workflow_cli.version import R2P_VERSION
        install_main(["--version"])
        assert R2P_VERSION in capsys.readouterr().out
        install_main(["-v"])
        assert R2P_VERSION in capsys.readouterr().out

    def test_status_json_is_parseable(self, capsys):
        import json
        from tools.workflow_cli.install_cli import main as install_main
        install_main(["status", "--json"])
        data = json.loads(capsys.readouterr().out)
        assert isinstance(data, list)

    def test_parse_platforms_defaults_to_all(self):
        from tools.workflow_cli.install_cli import _parse_platforms
        assert _parse_platforms(None, ("claude", "codex", "gemini")) == [
            "claude",
            "codex",
            "gemini",
        ]

    def test_install_unknown_platform_exits_before_writing(self):
        # _parse_platforms rejects an unknown platform before any service.install,
        # so this never touches the real ~/.req-to-plan.
        from tools.workflow_cli.install_cli import main as install_main
        with pytest.raises(SystemExit) as exc:
            install_main(["install", "--platform", "bogus-platform"])
        assert exc.value.code != 0


# ---------------------------------------------------------------------------
# Repair Loop Tests
# ---------------------------------------------------------------------------


class TestRepairLoops:
    def _to_quality_failed(self, tmp, work_id):
        invoke(["run-start", "--work-id", work_id, "--requirement", "foo"], base_path=tmp)
        invoke(["tier-lock", "--work-id", work_id, "--base", "light", "--confirm"], base_path=tmp)
        invoke(["stage-produce", "--work-id", work_id, "--stage", "raw_requirement",
                "--content", "x"], base_path=tmp)
        invoke(["stage-ready", "--work-id", work_id, "--stage", "raw_requirement"], base_path=tmp)
        record = load_record(tmp, work_id)
        record.status = RunStatus.QUALITY_GATE_FAILED
        save_record(tmp, record)

    def test_stage_update_flips_quality_failed_to_draft(self):
        with tempfile.TemporaryDirectory() as tmp:
            work_id = "WF-20260527-r-qf"
            self._to_quality_failed(tmp, work_id)
            invoke(["stage-update", "--work-id", work_id, "--stage", "raw_requirement",
                    "--content", "repaired content"], base_path=tmp)
            record = load_record(tmp, work_id)
            assert record.status == RunStatus.ACTIVE_STAGE_DRAFT

    def test_stage_update_flips_changes_requested_to_draft(self):
        with tempfile.TemporaryDirectory() as tmp:
            work_id = "WF-20260527-cr-1"
            invoke(["run-start", "--work-id", work_id, "--requirement", "foo"], base_path=tmp)
            invoke(["stage-produce", "--work-id", work_id, "--stage", "raw_requirement",
                    "--content", "x"], base_path=tmp)
            record = load_record(tmp, work_id)
            record.status = RunStatus.CHECKPOINT_CHANGES_REQUESTED
            save_record(tmp, record)
            invoke(["stage-update", "--work-id", work_id, "--stage", "raw_requirement",
                    "--content", "addressed changes"], base_path=tmp)
            record = load_record(tmp, work_id)
            assert record.status == RunStatus.ACTIVE_STAGE_DRAFT

    def test_stage_update_after_quality_pass_reenters_draft(self):
        with tempfile.TemporaryDirectory() as tmp:
            work_id = "WF-20260527-rqg"
            invoke(["run-start", "--work-id", work_id, "--requirement", "foo"], base_path=tmp)
            invoke(["tier-lock", "--work-id", work_id, "--base", "light", "--confirm"], base_path=tmp)
            invoke(["stage-produce", "--work-id", work_id, "--stage", "raw_requirement",
                    "--content", "real content"], base_path=tmp)
            invoke(["stage-ready", "--work-id", work_id, "--stage", "raw_requirement"], base_path=tmp)
            invoke(["gate-quality", "--work-id", work_id, "--stage", "raw_requirement"], base_path=tmp)
            record = load_record(tmp, work_id)
            assert record.status == RunStatus.READY_FOR_CHECKPOINT_REVIEW

            invoke(["stage-update", "--work-id", work_id, "--stage", "raw_requirement",
                    "--content", "edited after gate"], base_path=tmp)
            record = load_record(tmp, work_id)
            assert record.status == RunStatus.ACTIVE_STAGE_DRAFT
            from tools.workflow_cli.state import get_active_artifact
            aa = get_active_artifact(record, Stage.RAW_REQUIREMENT)
            assert aa.version == 2
            assert aa.status == "draft"

            invoke(["stage-ready", "--work-id", work_id, "--stage", "raw_requirement"], base_path=tmp)
            invoke(["review-checkpoint", "--work-id", work_id, "--stage", "raw_requirement"],
                   base_path=tmp, expect_exit=6)

    def test_stage_update_rejects_open_checkpoint_review(self):
        with tempfile.TemporaryDirectory() as tmp:
            work_id = "WF-20260527-rcr"
            invoke(["run-start", "--work-id", work_id, "--requirement", "foo"], base_path=tmp)
            invoke(["tier-lock", "--work-id", work_id, "--base", "light", "--confirm"], base_path=tmp)
            invoke(["stage-produce", "--work-id", work_id, "--stage", "raw_requirement",
                    "--content", "real content"], base_path=tmp)
            invoke(["stage-ready", "--work-id", work_id, "--stage", "raw_requirement"], base_path=tmp)
            invoke(["gate-quality", "--work-id", work_id, "--stage", "raw_requirement"], base_path=tmp)
            invoke(["review-checkpoint", "--work-id", work_id, "--stage", "raw_requirement"],
                   base_path=tmp)
            record = load_record(tmp, work_id)
            assert record.status == RunStatus.CHECKPOINT_REVIEW

            invoke(["stage-update", "--work-id", work_id, "--stage", "raw_requirement",
                    "--content", "edited while review is open"],
                   base_path=tmp, expect_exit=6)
            record = load_record(tmp, work_id)
            assert record.status == RunStatus.CHECKPOINT_REVIEW
            from tools.workflow_cli.state import get_active_artifact
            aa = get_active_artifact(record, Stage.RAW_REQUIREMENT)
            assert aa.version == 1
            assert aa.status == "ready"

    def test_stage_update_rejects_approved_checkpoint(self):
        with tempfile.TemporaryDirectory() as tmp:
            work_id = "WF-20260527-rca"
            invoke(["run-start", "--work-id", work_id, "--requirement", "foo"], base_path=tmp)
            invoke(["tier-lock", "--work-id", work_id, "--base", "light", "--confirm"], base_path=tmp)
            invoke(["stage-produce", "--work-id", work_id, "--stage", "raw_requirement",
                    "--content", "real content"], base_path=tmp)
            invoke(["stage-ready", "--work-id", work_id, "--stage", "raw_requirement"], base_path=tmp)
            invoke(["gate-quality", "--work-id", work_id, "--stage", "raw_requirement"], base_path=tmp)
            invoke(["review-checkpoint", "--work-id", work_id, "--stage", "raw_requirement"],
                   base_path=tmp)
            invoke(["checkpoint-decide", "--work-id", work_id, "--stage", "raw_requirement",
                    "--decision", "approved", "--confirm"], base_path=tmp)
            record = load_record(tmp, work_id)
            assert record.status == RunStatus.CHECKPOINT_APPROVED

            invoke(["stage-update", "--work-id", work_id, "--stage", "raw_requirement",
                    "--content", "edited after approval"],
                   base_path=tmp, expect_exit=6)
            record = load_record(tmp, work_id)
            assert record.status == RunStatus.CHECKPOINT_APPROVED
            from tools.workflow_cli.state import get_active_artifact
            aa = get_active_artifact(record, Stage.RAW_REQUIREMENT)
            assert aa.version == 1
            assert aa.status == "approved"

    def test_stage_update_rejects_wrong_stage_in_repair_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            work_id = "WF-20260527-rws"
            # run-start writes a raw_requirement artifact on disk.
            invoke(["run-start", "--work-id", work_id, "--requirement", "foo"], base_path=tmp)
            record = load_record(tmp, work_id)
            # Repair is requested on requirement_brief (the current stage), not raw_requirement.
            record.current_stage = Stage.REQUIREMENT_BRIEF
            record.status = RunStatus.CHECKPOINT_CHANGES_REQUESTED
            save_record(tmp, record)
            # Updating a non-current stage must be refused and must NOT clear the repair state.
            invoke(["stage-update", "--work-id", work_id, "--stage", "raw_requirement",
                    "--content", "tampering with a different stage"],
                   base_path=tmp, expect_exit=6)
            record = load_record(tmp, work_id)
            assert record.status == RunStatus.CHECKPOINT_CHANGES_REQUESTED

    def test_stage_produce_updates_ready_quality_failed_artifact_to_new_draft(self):
        with tempfile.TemporaryDirectory() as tmp:
            work_id = "WF-20260527-rpq-1"
            self._to_quality_failed(tmp, work_id)
            invoke(["stage-produce", "--work-id", work_id, "--stage", "raw_requirement",
                    "--content", "replacement content"], base_path=tmp)
            record = load_record(tmp, work_id)
            assert record.status == RunStatus.ACTIVE_STAGE_DRAFT
            from tools.workflow_cli.state import get_active_artifact
            aa = get_active_artifact(record, Stage.RAW_REQUIREMENT)
            assert aa.version == 2
            assert aa.status == "draft"

    def test_stage_produce_updates_ready_changes_requested_artifact_to_new_draft(self):
        with tempfile.TemporaryDirectory() as tmp:
            work_id = "WF-20260527-rpc-1"
            invoke(["run-start", "--work-id", work_id, "--requirement", "foo"], base_path=tmp)
            invoke(["stage-produce", "--work-id", work_id, "--stage", "raw_requirement",
                    "--content", "x"], base_path=tmp)
            invoke(["stage-ready", "--work-id", work_id, "--stage", "raw_requirement"], base_path=tmp)
            record = load_record(tmp, work_id)
            record.status = RunStatus.CHECKPOINT_CHANGES_REQUESTED
            save_record(tmp, record)
            invoke(["stage-produce", "--work-id", work_id, "--stage", "raw_requirement",
                    "--content", "addressed changes"], base_path=tmp)
            record = load_record(tmp, work_id)
            assert record.status == RunStatus.ACTIVE_STAGE_DRAFT
            from tools.workflow_cli.state import get_active_artifact
            aa = get_active_artifact(record, Stage.RAW_REQUIREMENT)
            assert aa.version == 2
            assert aa.status == "draft"

    def test_stage_produce_returns_entry_gate_failure_from_quality_failed(self):
        with tempfile.TemporaryDirectory() as tmp:
            work_id = "WF-20260527-rpegq"
            invoke(["run-start", "--work-id", work_id, "--requirement", "foo"], base_path=tmp)
            record = load_record(tmp, work_id)
            record.current_stage = Stage.RISK_DISCOVERY
            record.status = RunStatus.QUALITY_GATE_FAILED
            save_record(tmp, record)

            invoke(["stage-produce", "--work-id", work_id, "--stage", "risk_discovery",
                    "--content", "repaired risk discovery"],
                   base_path=tmp, expect_exit=3)

            record = load_record(tmp, work_id)
            assert record.status == RunStatus.QUALITY_GATE_FAILED

    def test_stage_produce_returns_entry_gate_failure_from_changes_requested(self):
        with tempfile.TemporaryDirectory() as tmp:
            work_id = "WF-20260527-rpegc"
            invoke(["run-start", "--work-id", work_id, "--requirement", "foo"], base_path=tmp)
            record = load_record(tmp, work_id)
            record.current_stage = Stage.RISK_DISCOVERY
            record.status = RunStatus.CHECKPOINT_CHANGES_REQUESTED
            save_record(tmp, record)

            invoke(["stage-produce", "--work-id", work_id, "--stage", "risk_discovery",
                    "--content", "repaired risk discovery"],
                   base_path=tmp, expect_exit=3)

            record = load_record(tmp, work_id)
            assert record.status == RunStatus.CHECKPOINT_CHANGES_REQUESTED


# ---------------------------------------------------------------------------
# State Authority Tests
# ---------------------------------------------------------------------------


class TestStateAuthority:
    def test_gate_quality_uses_validated_transition(self):
        """gate-quality must reach READY via update_run_status, not a raw write."""
        with tempfile.TemporaryDirectory() as tmp:
            work_id = "WF-20260527-auth"
            invoke(["run-start", "--work-id", work_id, "--requirement", "foo"], base_path=tmp)
            invoke(["tier-lock", "--work-id", work_id, "--base", "light", "--confirm"], base_path=tmp)
            invoke(["stage-produce", "--work-id", work_id, "--stage", "raw_requirement",
                    "--content", "Some real content here."], base_path=tmp)
            invoke(["stage-ready", "--work-id", work_id, "--stage", "raw_requirement"], base_path=tmp)
            invoke(["gate-quality", "--work-id", work_id, "--stage", "raw_requirement"], base_path=tmp)
            record = load_record(tmp, work_id)
            assert record.status == RunStatus.READY_FOR_CHECKPOINT_REVIEW


# ---------------------------------------------------------------------------
# gate-entry Persistence Tests
# ---------------------------------------------------------------------------


class TestGateEntryPersistence:
    def test_gate_entry_persists_from_next_stage(self):
        with tempfile.TemporaryDirectory() as tmp:
            work_id = "WF-20260527-nsp"
            invoke(["run-start", "--work-id", work_id, "--requirement", "foo"], base_path=tmp)
            record = load_record(tmp, work_id)
            # raw_requirement has no required upstream checkpoints, so entry gate passes.
            record.status = RunStatus.NEXT_STAGE
            save_record(tmp, record)
            invoke(["gate-entry", "--work-id", work_id, "--stage", "raw_requirement"], base_path=tmp)
            record = load_record(tmp, work_id)
            assert record.status == RunStatus.ACTIVE_STAGE_DRAFT

    def test_gate_entry_readonly_outside_those_states(self):
        with tempfile.TemporaryDirectory() as tmp:
            work_id = "WF-20260527-rop"
            invoke(["run-start", "--work-id", work_id, "--requirement", "foo"], base_path=tmp)
            invoke(["gate-entry", "--work-id", work_id, "--stage", "raw_requirement"], base_path=tmp)
            record = load_record(tmp, work_id)
            assert record.status == RunStatus.ACTIVE_STAGE_DRAFT  # unchanged from run-start

    def test_gate_entry_refuses_wrong_stage_in_stateful_modes(self):
        with tempfile.TemporaryDirectory() as tmp:
            work_id = "WF-20260527-wsm"
            invoke(["run-start", "--work-id", work_id, "--requirement", "foo"], base_path=tmp)
            record = load_record(tmp, work_id)
            record.current_stage = Stage.REQUIREMENT_BRIEF
            record.status = RunStatus.NEXT_STAGE
            save_record(tmp, record)
            invoke(["gate-entry", "--work-id", work_id, "--stage", "raw_requirement"],
                   base_path=tmp, expect_exit=6)
            record = load_record(tmp, work_id)
            assert record.status == RunStatus.NEXT_STAGE


class TestNextStageProduceGuard:
    def test_stage_produce_refused_in_next_stage(self):
        with tempfile.TemporaryDirectory() as tmp:
            work_id = "WF-20260527-npg"
            invoke(["run-start", "--work-id", work_id, "--requirement", "foo"], base_path=tmp)
            record = load_record(tmp, work_id)
            record.status = RunStatus.NEXT_STAGE
            save_record(tmp, record)
            invoke(["stage-produce", "--work-id", work_id, "--stage", "raw_requirement",
                    "--content", "should be refused"], base_path=tmp, expect_exit=6)

    def test_stage_produce_refused_in_entry_gate_failed(self):
        with tempfile.TemporaryDirectory() as tmp:
            work_id = "WF-20260527-egp"
            invoke(["run-start", "--work-id", work_id, "--requirement", "foo"], base_path=tmp)
            record = load_record(tmp, work_id)
            record.status = RunStatus.ENTRY_GATE_FAILED
            save_record(tmp, record)
            invoke(["stage-produce", "--work-id", work_id, "--stage", "raw_requirement",
                    "--content", "should run gate-entry first"], base_path=tmp, expect_exit=6)


# ---------------------------------------------------------------------------
# Forced Review Relocation Tests
# ---------------------------------------------------------------------------


class TestForcedReviewRelocation:
    def test_gate_quality_allows_forced_modifier_to_reach_checkpoint_review(self):
        with tempfile.TemporaryDirectory() as tmp:
            work_id = "WF-20260527-frg"
            invoke(["run-start", "--work-id", work_id, "--requirement", "foo"], base_path=tmp)
            invoke(["tier-lock", "--work-id", work_id, "--base", "standard",
                    "--modifiers", "safety", "--confirm"], base_path=tmp)
            record = load_record(tmp, work_id)
            record.current_stage = Stage.DESIGN
            record.status = RunStatus.ACTIVE_STAGE_DRAFT
            from tools.workflow_cli.models import ActiveArtifact
            record.active_artifacts = [ActiveArtifact(
                stage=Stage.DESIGN, artifact="05-design.md", version=1, status="ready")]
            save_record(tmp, record)
            run_dir = Path(tmp) / ".req-to-plan" / work_id
            (run_dir / "05-design.md").write_text(
                "---\nr2p_version: 1\n---\n"
                "## Design Summary\ncontent\n## Current Code Evidence\ncontent\n"
                "## Requirements Coverage\ncontent\n## Options Considered\ncontent\n"
                "## Chosen Design\ncontent\n### DES-ARCH-001 Selected architecture\ncontent\n"
                "## Decision Requests\nnone\n"
                "## Rollback\ncontent\n"
                "## Observability\ncontent\n## SPEC Handoff\ncontent\n",
                encoding="utf-8",
            )
            invoke(["gate-quality", "--work-id", work_id, "--stage", "design"], base_path=tmp)
            record = load_record(tmp, work_id)
            assert record.status == RunStatus.READY_FOR_CHECKPOINT_REVIEW


class TestTierEscalationInvalidatesPlanGate:
    def _ready_plan_under_light_tier(self, tmp: str, work_id: str) -> None:
        from tools.workflow_cli.models import ActiveArtifact

        invoke(["run-start", "--work-id", work_id, "--requirement", "foo"], base_path=tmp)
        invoke(["tier-lock", "--work-id", work_id, "--base", "light", "--confirm"], base_path=tmp)
        record = load_record(tmp, work_id)
        record.current_stage = Stage.PLAN
        record.status = RunStatus.ACTIVE_STAGE_DRAFT
        record.active_artifacts = [
            ActiveArtifact(
                stage=Stage.PLAN,
                artifact="07-plan.md",
                version=1,
                status="ready",
            )
        ]
        save_record(tmp, record)
        run_dir = Path(tmp) / ".req-to-plan" / work_id
        (run_dir / "07-plan.md").write_text(
            "---\nr2p_version: 1\n---\n# PLAN\n\n## Tasks\n\nProse-only plan.\n",
            encoding="utf-8",
        )
        invoke(["gate-quality", "--work-id", work_id, "--stage", "plan"], base_path=tmp)

    def test_scope_expanding_escalation_invalidates_ready_plan_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            work_id = "WF-20260527-pgready"
            self._ready_plan_under_light_tier(tmp, work_id)

            invoke(["tier-escalate", "--work-id", work_id, "--modifier", "scope_expanding"], base_path=tmp)

            record = load_record(tmp, work_id)
            assert record.status == RunStatus.ACTIVE_STAGE_DRAFT
            assert record.tier_locked.base.value == "standard"
            invoke(["review-checkpoint", "--work-id", work_id, "--stage", "plan"], base_path=tmp, expect_exit=6)
            invoke(["gate-quality", "--work-id", work_id, "--stage", "plan"], base_path=tmp, expect_exit=3)

    def test_scope_expanding_escalation_invalidates_open_plan_review(self):
        with tempfile.TemporaryDirectory() as tmp:
            work_id = "WF-20260527-pgreview"
            self._ready_plan_under_light_tier(tmp, work_id)
            invoke(["review-checkpoint", "--work-id", work_id, "--stage", "plan"], base_path=tmp)

            invoke(["tier-escalate", "--work-id", work_id, "--modifier", "scope_expanding"], base_path=tmp)

            record = load_record(tmp, work_id)
            assert record.status == RunStatus.ACTIVE_STAGE_DRAFT
            invoke(
                ["checkpoint-decide", "--work-id", work_id, "--stage", "plan", "--decision", "approved", "--confirm"],
                base_path=tmp,
                expect_exit=6,
            )
            invoke(["gate-quality", "--work-id", work_id, "--stage", "plan"], base_path=tmp, expect_exit=3)

    def test_scope_expanding_escalation_refuses_approved_plan(self):
        with tempfile.TemporaryDirectory() as tmp:
            work_id = "WF-20260527-pgapproved"
            self._ready_plan_under_light_tier(tmp, work_id)
            invoke(["review-checkpoint", "--work-id", work_id, "--stage", "plan"], base_path=tmp)
            invoke(
                ["checkpoint-decide", "--work-id", work_id, "--stage", "plan", "--decision", "approved", "--confirm"],
                base_path=tmp,
            )

            invoke(
                ["tier-escalate", "--work-id", work_id, "--modifier", "scope_expanding"],
                base_path=tmp,
                expect_exit=6,
            )

            record = load_record(tmp, work_id)
            assert record.status == RunStatus.CHECKPOINT_APPROVED
            assert record.tier_locked.base.value == "light"

    def test_scope_expanding_escalation_refuses_closed_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            work_id = "WF-20260527-pgclosed"
            self._ready_plan_under_light_tier(tmp, work_id)
            invoke(["review-checkpoint", "--work-id", work_id, "--stage", "plan"], base_path=tmp)
            invoke(
                ["checkpoint-decide", "--work-id", work_id, "--stage", "plan", "--decision", "approved", "--confirm"],
                base_path=tmp,
            )
            invoke(["run-close", "--work-id", work_id], base_path=tmp)

            invoke(
                ["tier-escalate", "--work-id", work_id, "--modifier", "scope_expanding"],
                base_path=tmp,
                expect_exit=6,
            )

            record = load_record(tmp, work_id)
            assert record.status == RunStatus.CLOSED_AT_PLAN_CHECKPOINT
            assert record.tier_locked.base.value == "light"


class TestTierEscalationInvalidatesEarlierStageGates:
    """R15a: the light->standard revert must cover DESIGN/SPEC, not only PLAN."""

    _DESIGN_BODY = (
        "---\nr2p_version: 1\n---\n# DESIGN\n\n"
        "## Design Summary\nsummary text\n\n"
        "## Chosen Design\n### DES-ARCH-001 chosen approach\ndetails\n\n"
        "## SPEC Handoff\nhandoff notes\n"
    )
    _SPEC_BODY = (
        "---\nr2p_version: 1\n---\n# SPEC\n\n"
        "## Behavior Contracts\n### SPEC-AUTH-001 login behavior\ncontract text\n\n"
        "## External Documentation Checked\nN/A — no external dependencies\n\n"
        "## PLAN Handoff\nhandoff notes\n"
    )
    _PLAN_BODY = (
        "---\nr2p_version: 1\n---\n# PLAN\n\n"
        "## Tasks\n\nProse-only plan.\n"
    )

    def _ready_stage_under_light_tier(self, tmp, work_id, stage, artifact, body):
        from tools.workflow_cli.models import ActiveArtifact

        invoke(["run-start", "--work-id", work_id, "--requirement", "foo"], base_path=tmp)
        invoke(["tier-lock", "--work-id", work_id, "--base", "light", "--confirm"], base_path=tmp)
        record = load_record(tmp, work_id)
        record.current_stage = stage
        record.status = RunStatus.ACTIVE_STAGE_DRAFT
        record.active_artifacts = [
            ActiveArtifact(stage=stage, artifact=artifact, version=1, status="ready")
        ]
        save_record(tmp, record)
        run_dir = Path(tmp) / ".req-to-plan" / work_id
        (run_dir / artifact).write_text(body, encoding="utf-8")
        invoke(["gate-quality", "--work-id", work_id, "--stage", stage.value], base_path=tmp)
        record = load_record(tmp, work_id)
        assert record.status == RunStatus.READY_FOR_CHECKPOINT_REVIEW, (
            f"fixture must pass the light {stage.value} quality gate first"
        )

    def test_escalation_to_standard_past_design_prints_gap_open_note(self, capsys):
        with tempfile.TemporaryDirectory() as tmp:
            work_id = "WF-20260606-note1"
            self._ready_stage_under_light_tier(
                tmp, work_id, Stage.SPEC, "06-spec.md", self._SPEC_BODY)
            capsys.readouterr()

            invoke(["tier-escalate", "--work-id", work_id, "--modifier", "scope_expanding"], base_path=tmp)

            out = capsys.readouterr().out
            assert f"r2p-gap-open --work-id {work_id} --owner-stage design" in out
            assert "--required-action" in out

    def test_escalation_to_standard_at_plan_prints_gap_open_note(self, capsys):
        with tempfile.TemporaryDirectory() as tmp:
            work_id = "WF-20260606-note3"
            self._ready_stage_under_light_tier(
                tmp, work_id, Stage.PLAN, "07-plan.md", self._PLAN_BODY)
            capsys.readouterr()

            invoke(["tier-escalate", "--work-id", work_id, "--modifier", "scope_expanding"], base_path=tmp)

            out = capsys.readouterr().out
            assert f"r2p-gap-open --work-id {work_id} --owner-stage design" in out
            assert "--required-action" in out

    def test_escalation_to_standard_at_design_prints_no_note(self, capsys):
        with tempfile.TemporaryDirectory() as tmp:
            work_id = "WF-20260606-note2"
            self._ready_stage_under_light_tier(
                tmp, work_id, Stage.DESIGN, "05-design.md", self._DESIGN_BODY)
            capsys.readouterr()

            invoke(["tier-escalate", "--work-id", work_id, "--modifier", "scope_expanding"], base_path=tmp)

            out = capsys.readouterr().out
            assert "r2p-gap-open" not in out

    def test_scope_expanding_escalation_invalidates_ready_design_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            work_id = "WF-20260606-dgready"
            self._ready_stage_under_light_tier(
                tmp, work_id, Stage.DESIGN, "05-design.md", self._DESIGN_BODY)

            invoke(["tier-escalate", "--work-id", work_id, "--modifier", "scope_expanding"], base_path=tmp)

            record = load_record(tmp, work_id)
            assert record.status == RunStatus.ACTIVE_STAGE_DRAFT
            assert record.tier_locked.base.value == "standard"
            assert record.resume_context.active_item == "design"
            invoke(["gate-quality", "--work-id", work_id, "--stage", "design"], base_path=tmp, expect_exit=3)

    def test_scope_expanding_escalation_invalidates_open_design_review(self):
        with tempfile.TemporaryDirectory() as tmp:
            work_id = "WF-20260606-dgreview"
            self._ready_stage_under_light_tier(
                tmp, work_id, Stage.DESIGN, "05-design.md", self._DESIGN_BODY)
            invoke(["review-checkpoint", "--work-id", work_id, "--stage", "design"], base_path=tmp)

            invoke(["tier-escalate", "--work-id", work_id, "--modifier", "scope_expanding"], base_path=tmp)

            record = load_record(tmp, work_id)
            assert record.status == RunStatus.ACTIVE_STAGE_DRAFT
            invoke(["gate-quality", "--work-id", work_id, "--stage", "design"], base_path=tmp, expect_exit=3)

    def test_scope_expanding_escalation_invalidates_ready_spec_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            work_id = "WF-20260606-sgready"
            self._ready_stage_under_light_tier(
                tmp, work_id, Stage.SPEC, "06-spec.md", self._SPEC_BODY)

            invoke(["tier-escalate", "--work-id", work_id, "--modifier", "scope_expanding"], base_path=tmp)

            record = load_record(tmp, work_id)
            assert record.status == RunStatus.ACTIVE_STAGE_DRAFT
            assert record.tier_locked.base.value == "standard"
            assert record.resume_context.active_item == "spec"
            invoke(["gate-quality", "--work-id", work_id, "--stage", "spec"], base_path=tmp, expect_exit=3)

    def test_non_base_changing_escalation_keeps_ready_design_gate(self):
        """Modifier-only escalation (base does not flip to standard) must NOT revert."""
        with tempfile.TemporaryDirectory() as tmp:
            work_id = "WF-20260606-dgdep"
            self._ready_stage_under_light_tier(
                tmp, work_id, Stage.DESIGN, "05-design.md", self._DESIGN_BODY)

            invoke(["tier-escalate", "--work-id", work_id, "--modifier", "dependency"], base_path=tmp)

            record = load_record(tmp, work_id)
            assert record.status == RunStatus.READY_FOR_CHECKPOINT_REVIEW
            assert record.tier_locked.base.value == "light"


# ---------------------------------------------------------------------------
# review-checkpoint
# ---------------------------------------------------------------------------


class TestReviewCheckpoint:
    def _to_ready(self, tmp, work_id, stage="raw_requirement"):
        invoke(["run-start", "--work-id", work_id, "--requirement", "foo"], base_path=tmp)
        invoke(["tier-lock", "--work-id", work_id, "--base", "light", "--confirm"], base_path=tmp)
        invoke(["stage-produce", "--work-id", work_id, "--stage", stage, "--content", "real"], base_path=tmp)
        invoke(["stage-ready", "--work-id", work_id, "--stage", stage], base_path=tmp)
        invoke(["gate-quality", "--work-id", work_id, "--stage", stage], base_path=tmp)

    def test_review_checkpoint_writes_marker_and_transitions(self):
        with tempfile.TemporaryDirectory() as tmp:
            work_id = "WF-20260527-rcp"
            self._to_ready(tmp, work_id)
            invoke(["review-checkpoint", "--work-id", work_id, "--stage", "raw_requirement"], base_path=tmp)
            record = load_record(tmp, work_id)
            assert record.status == RunStatus.CHECKPOINT_REVIEW
            marker = Path(tmp) / ".req-to-plan" / work_id / "reviews" / "raw_requirement-checkpoint-review-v1.md"
            assert marker.exists()

    def test_review_checkpoint_recreates_missing_marker_in_open_review(self):
        with tempfile.TemporaryDirectory() as tmp:
            work_id = "WF-20260527-rcrb"
            self._to_ready(tmp, work_id)
            invoke(["review-checkpoint", "--work-id", work_id, "--stage", "raw_requirement"], base_path=tmp)
            marker = Path(tmp) / ".req-to-plan" / work_id / "reviews" / "raw_requirement-checkpoint-review-v1.md"
            marker.unlink()

            invoke(["review-checkpoint", "--work-id", work_id, "--stage", "raw_requirement"], base_path=tmp)

            record = load_record(tmp, work_id)
            assert record.status == RunStatus.CHECKPOINT_REVIEW
            assert marker.exists()

    def test_review_checkpoint_wrong_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            work_id = "WF-20260527-rcw"
            invoke(["run-start", "--work-id", work_id, "--requirement", "foo"], base_path=tmp)
            invoke(["review-checkpoint", "--work-id", work_id, "--stage", "raw_requirement"],
                   base_path=tmp, expect_exit=6)

    def test_review_checkpoint_refuses_unready_or_stale_artifact(self):
        with tempfile.TemporaryDirectory() as tmp:
            work_id = "WF-20260527-rcs"
            invoke(["run-start", "--work-id", work_id, "--requirement", "foo"], base_path=tmp)
            record = load_record(tmp, work_id)
            record.status = RunStatus.READY_FOR_CHECKPOINT_REVIEW
            save_record(tmp, record)
            invoke(["review-checkpoint", "--work-id", work_id, "--stage", "raw_requirement"],
                   base_path=tmp, expect_exit=6)
            record = load_record(tmp, work_id)
            record.active_artifacts[0].status = "ready"
            save_record(tmp, record)
            run_dir = Path(tmp) / ".req-to-plan" / work_id
            (run_dir / "00-raw-requirement.md").write_text(
                "---\nr2p_version: 2\n---\nfoo", encoding="utf-8")
            invoke(["review-checkpoint", "--work-id", work_id, "--stage", "raw_requirement"],
                   base_path=tmp, expect_exit=6)

    def test_review_checkpoint_rejects_symlinked_reviews_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            work_id = "WF-20260527-rcsym"
            self._to_ready(tmp, work_id)
            run_dir = Path(tmp) / ".req-to-plan" / work_id
            outside = Path(tmp) / "outside-reviews"
            outside.mkdir()
            reviews_link = run_dir / "reviews"
            reviews_link.symlink_to(outside, target_is_directory=True)

            invoke(["review-checkpoint", "--work-id", work_id, "--stage", "raw_requirement"],
                   base_path=tmp, expect_exit=6)

            # Symlink must not be followed; the outside dir stays empty.
            assert reviews_link.is_symlink()
            assert list(outside.iterdir()) == []

    def test_review_checkpoint_rejects_symlinked_marker_without_writing_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            work_id = "WF-20260527-rcmsym"
            self._to_ready(tmp, work_id)
            run_dir = Path(tmp) / ".req-to-plan" / work_id
            reviews = run_dir / "reviews"
            reviews.mkdir()
            outside = Path(tmp) / "outside-marker.md"
            outside.write_text("original", encoding="utf-8")
            marker = reviews / "raw_requirement-checkpoint-review-v1.md"
            marker.symlink_to(outside)

            invoke(["review-checkpoint", "--work-id", work_id, "--stage", "raw_requirement"],
                   base_path=tmp, expect_exit=6)

            assert marker.is_symlink()
            assert outside.read_text(encoding="utf-8") == "original"
            record = load_record(tmp, work_id)
            assert record.status == RunStatus.READY_FOR_CHECKPOINT_REVIEW


# ---------------------------------------------------------------------------
# checkpoint-decide
# ---------------------------------------------------------------------------


class TestCheckpointDecide:
    def _to_review(self, tmp, work_id, base="light", modifiers=None, stage="raw_requirement"):
        invoke(["run-start", "--work-id", work_id, "--requirement", "foo"], base_path=tmp)
        lock = ["tier-lock", "--work-id", work_id, "--base", base, "--confirm"]
        if modifiers:
            lock += ["--modifiers", modifiers]
        invoke(lock, base_path=tmp)
        invoke(["stage-produce", "--work-id", work_id, "--stage", stage, "--content", "real"], base_path=tmp)
        invoke(["stage-ready", "--work-id", work_id, "--stage", stage], base_path=tmp)
        invoke(["gate-quality", "--work-id", work_id, "--stage", stage], base_path=tmp)
        invoke(["review-checkpoint", "--work-id", work_id, "--stage", stage], base_path=tmp)

    def test_approve_requires_confirm(self):
        with tempfile.TemporaryDirectory() as tmp:
            work_id = "WF-20260527-cd1"
            self._to_review(tmp, work_id)
            invoke(["checkpoint-decide", "--work-id", work_id, "--stage", "raw_requirement",
                    "--decision", "approved"], base_path=tmp, expect_exit=5)

    def test_approve_non_forced_passes_with_marker(self):
        with tempfile.TemporaryDirectory() as tmp:
            work_id = "WF-20260527-cd2"
            self._to_review(tmp, work_id)
            invoke(["checkpoint-decide", "--work-id", work_id, "--stage", "raw_requirement",
                    "--decision", "approved", "--confirm"], base_path=tmp)
            record = load_record(tmp, work_id)
            assert record.status == RunStatus.CHECKPOINT_APPROVED
            assert any(cp.stage == Stage.RAW_REQUIREMENT for cp in record.approved_checkpoints)
            artifact = Path(tmp) / ".req-to-plan" / work_id / "00-raw-requirement.md"
            assert "r2p_status: approved" in artifact.read_text(encoding="utf-8")

    def test_approve_preserves_downstream_authorization(self):
        with tempfile.TemporaryDirectory() as tmp:
            work_id = "WF-20260527-cd2a"
            self._to_review(tmp, work_id)
            invoke(["checkpoint-decide", "--work-id", work_id, "--stage", "raw_requirement",
                    "--decision", "approved", "--confirm",
                    "--downstream-authorization", "custom_next"], base_path=tmp)
            record = load_record(tmp, work_id)
            checkpoint = next(cp for cp in record.approved_checkpoints if cp.stage == Stage.RAW_REQUIREMENT)
            assert checkpoint.downstream_authorization == "custom_next"

    def test_approve_rejects_multiline_downstream_authorization_without_mutation(self):
        with tempfile.TemporaryDirectory() as tmp:
            work_id = "WF-20260527-cd2m"
            self._to_review(tmp, work_id)
            run_md_path = Path(tmp) / ".req-to-plan" / work_id / "run.md"
            artifact_path = Path(tmp) / ".req-to-plan" / work_id / "00-raw-requirement.md"
            run_md_before = run_md_path.read_text(encoding="utf-8")
            artifact_before = artifact_path.read_text(encoding="utf-8")

            invoke(
                [
                    "checkpoint-decide", "--work-id", work_id, "--stage", "raw_requirement",
                    "--decision", "approved", "--confirm",
                    "--downstream-authorization", "custom_next\n## Status\narchived",
                ],
                base_path=tmp,
                expect_exit=2,
            )

            assert run_md_path.read_text(encoding="utf-8") == run_md_before
            assert artifact_path.read_text(encoding="utf-8") == artifact_before
            record = load_record(tmp, work_id)
            assert record.status == RunStatus.CHECKPOINT_REVIEW
            assert record.approved_checkpoints == []

    def test_approve_rejects_trailing_newline_downstream_authorization_without_mutation(self):
        with tempfile.TemporaryDirectory() as tmp:
            work_id = "WF-20260527-cd2t"
            self._to_review(tmp, work_id)
            run_md_path = Path(tmp) / ".req-to-plan" / work_id / "run.md"
            artifact_path = Path(tmp) / ".req-to-plan" / work_id / "00-raw-requirement.md"
            run_md_before = run_md_path.read_text(encoding="utf-8")
            artifact_before = artifact_path.read_text(encoding="utf-8")

            invoke(
                [
                    "checkpoint-decide", "--work-id", work_id, "--stage", "raw_requirement",
                    "--decision", "approved", "--confirm",
                    "--downstream-authorization", "custom_next\n",
                ],
                base_path=tmp,
                expect_exit=2,
            )

            assert run_md_path.read_text(encoding="utf-8") == run_md_before
            assert artifact_path.read_text(encoding="utf-8") == artifact_before
            record = load_record(tmp, work_id)
            assert record.status == RunStatus.CHECKPOINT_REVIEW
            assert record.approved_checkpoints == []

    def test_approve_refuses_open_routes(self):
        with tempfile.TemporaryDirectory() as tmp:
            work_id = "WF-20260527-cd2b"
            self._to_review(tmp, work_id)
            record = load_record(tmp, work_id)
            record.open_routes = [
                OpenRoute(
                    route_id="GAP-001",
                    from_stage=Stage.RAW_REQUIREMENT,
                    owner_stage=Stage.RAW_REQUIREMENT,
                    required_action="repair traceability",
                    status="open",
                )
            ]
            save_record(tmp, record)

            invoke(["checkpoint-decide", "--work-id", work_id, "--stage", "raw_requirement",
                    "--decision", "approved", "--confirm"], base_path=tmp, expect_exit=6)

            record = load_record(tmp, work_id)
            assert record.status == RunStatus.CHECKPOINT_REVIEW
            assert record.approved_checkpoints == []
            assert record.active_artifacts[0].status == "ready"

    def test_approve_rejects_symlinked_checkpoint_marker_without_mutation(self):
        with tempfile.TemporaryDirectory() as tmp:
            work_id = "WF-20260527-cd2s"
            self._to_review(tmp, work_id)
            run_dir = Path(tmp) / ".req-to-plan" / work_id
            marker = run_dir / "reviews" / "raw_requirement-checkpoint-review-v1.md"
            marker.unlink()
            outside = Path(tmp) / "outside-marker.md"
            outside.write_text("marker", encoding="utf-8")
            marker.symlink_to(outside)

            invoke(["checkpoint-decide", "--work-id", work_id, "--stage", "raw_requirement",
                    "--decision", "approved", "--confirm"], base_path=tmp, expect_exit=6)

            assert marker.is_symlink()
            record = load_record(tmp, work_id)
            assert record.status == RunStatus.CHECKPOINT_REVIEW
            assert record.approved_checkpoints == []
            assert record.active_artifacts[0].status == "ready"

    def test_changes_requested_rejects_symlinked_checkpoint_marker_without_mutation(self):
        with tempfile.TemporaryDirectory() as tmp:
            work_id = "WF-20260527-cd2cs"
            self._to_review(tmp, work_id)
            run_dir = Path(tmp) / ".req-to-plan" / work_id
            marker = run_dir / "reviews" / "raw_requirement-checkpoint-review-v1.md"
            marker.unlink()
            outside = Path(tmp) / "outside-marker.md"
            outside.write_text("marker", encoding="utf-8")
            marker.symlink_to(outside)

            invoke(["checkpoint-decide", "--work-id", work_id, "--stage", "raw_requirement",
                    "--decision", "changes_requested"], base_path=tmp, expect_exit=6)

            assert marker.is_symlink()
            record = load_record(tmp, work_id)
            assert record.status == RunStatus.CHECKPOINT_REVIEW
            assert record.approved_checkpoints == []
            assert record.active_artifacts[0].status == "ready"

    def test_changes_requested_rejects_non_regular_checkpoint_marker_without_mutation(self):
        with tempfile.TemporaryDirectory() as tmp:
            work_id = "WF-20260527-cd2cd"
            self._to_review(tmp, work_id)
            run_dir = Path(tmp) / ".req-to-plan" / work_id
            marker = run_dir / "reviews" / "raw_requirement-checkpoint-review-v1.md"
            marker.unlink()
            marker.mkdir()

            invoke(["checkpoint-decide", "--work-id", work_id, "--stage", "raw_requirement",
                    "--decision", "changes_requested"], base_path=tmp, expect_exit=6)

            assert marker.is_dir()
            record = load_record(tmp, work_id)
            assert record.status == RunStatus.CHECKPOINT_REVIEW
            assert record.approved_checkpoints == []
            assert record.active_artifacts[0].status == "ready"

    def test_changes_requested_transitions_and_sets_resume(self):
        with tempfile.TemporaryDirectory() as tmp:
            work_id = "WF-20260527-cd3"
            self._to_review(tmp, work_id)
            invoke(["checkpoint-decide", "--work-id", work_id, "--stage", "raw_requirement",
                    "--decision", "changes_requested"], base_path=tmp)
            record = load_record(tmp, work_id)
            assert record.status == RunStatus.CHECKPOINT_CHANGES_REQUESTED

    def test_forced_modifier_needs_subagent_review(self):
        with tempfile.TemporaryDirectory() as tmp:
            work_id = "WF-20260527-cd4"
            invoke(["run-start", "--work-id", work_id, "--requirement", "foo"], base_path=tmp)
            invoke(["tier-lock", "--work-id", work_id, "--base", "standard",
                    "--modifiers", "safety", "--confirm"], base_path=tmp)
            record = load_record(tmp, work_id)
            record.current_stage = Stage.DESIGN
            record.status = RunStatus.CHECKPOINT_REVIEW
            from tools.workflow_cli.models import ActiveArtifact
            record.active_artifacts = [ActiveArtifact(
                stage=Stage.DESIGN, artifact="05-design.md", version=1, status="ready")]
            save_record(tmp, record)
            run_dir = Path(tmp) / ".req-to-plan" / work_id
            (run_dir / "05-design.md").write_text("---\nr2p_version: 1\n---\nbody", encoding="utf-8")
            reviews = run_dir / "reviews"; reviews.mkdir(parents=True, exist_ok=True)
            (reviews / "design-checkpoint-review-v1.md").write_text("marker", encoding="utf-8")
            # marker alone -> exit 5 (forced needs subagent review)
            invoke(["checkpoint-decide", "--work-id", work_id, "--stage", "design",
                    "--decision", "approved", "--confirm"], base_path=tmp, expect_exit=5)
            (reviews / "design-subagent-review-v1.md").write_text("findings", encoding="utf-8")
            invoke(["checkpoint-decide", "--work-id", work_id, "--stage", "design",
                    "--decision", "approved", "--confirm"], base_path=tmp)
            record = load_record(tmp, work_id)
            assert record.status == RunStatus.CHECKPOINT_APPROVED

    def test_forced_modifier_unsafe_review_exit_code_is_propagated(self):
        with tempfile.TemporaryDirectory() as tmp:
            work_id = "WF-20260527-cd4s"
            invoke(["run-start", "--work-id", work_id, "--requirement", "foo"], base_path=tmp)
            invoke(["tier-lock", "--work-id", work_id, "--base", "standard",
                    "--modifiers", "safety", "--confirm"], base_path=tmp)
            record = load_record(tmp, work_id)
            record.current_stage = Stage.DESIGN
            record.status = RunStatus.CHECKPOINT_REVIEW
            from tools.workflow_cli.models import ActiveArtifact
            record.active_artifacts = [ActiveArtifact(
                stage=Stage.DESIGN, artifact="05-design.md", version=1, status="ready")]
            save_record(tmp, record)
            run_dir = Path(tmp) / ".req-to-plan" / work_id
            (run_dir / "05-design.md").write_text("---\nr2p_version: 1\n---\nbody", encoding="utf-8")
            reviews = run_dir / "reviews"
            reviews.mkdir(parents=True, exist_ok=True)
            (reviews / "design-checkpoint-review-v1.md").write_text("marker", encoding="utf-8")
            outside = Path(tmp) / "outside-review.md"
            outside.write_text("planted review", encoding="utf-8")
            (reviews / "design-subagent-review-v1.md").symlink_to(outside)

            invoke(["checkpoint-decide", "--work-id", work_id, "--stage", "design",
                    "--decision", "approved", "--confirm"], base_path=tmp, expect_exit=6)

            record = load_record(tmp, work_id)
            assert record.status == RunStatus.CHECKPOINT_REVIEW
            assert record.approved_checkpoints == []

    def test_forced_modifier_gate_quality_passes_but_approve_requires_review(self):
        with tempfile.TemporaryDirectory() as tmp:
            work_id = "WF-20260527-cd5"
            invoke(["run-start", "--work-id", work_id, "--requirement", "foo"], base_path=tmp)
            invoke(["tier-lock", "--work-id", work_id, "--base", "standard",
                    "--modifiers", "safety", "--confirm"], base_path=tmp)
            record = load_record(tmp, work_id)
            record.current_stage = Stage.DESIGN
            record.status = RunStatus.ACTIVE_STAGE_DRAFT
            from tools.workflow_cli.models import ActiveArtifact
            record.active_artifacts = [ActiveArtifact(
                stage=Stage.DESIGN, artifact="05-design.md", version=1, status="ready")]
            save_record(tmp, record)
            run_dir = Path(tmp) / ".req-to-plan" / work_id
            (run_dir / "05-design.md").write_text(
                "---\nr2p_version: 1\n---\n"
                "## Design Summary\ncontent\n## Current Code Evidence\ncontent\n"
                "## Requirements Coverage\ncontent\n## Options Considered\ncontent\n"
                "## Chosen Design\ncontent\n### DES-ARCH-001 Selected architecture\ncontent\n"
                "## Decision Requests\nnone\n"
                "## Rollback\ncontent\n"
                "## Observability\ncontent\n## SPEC Handoff\ncontent\n",
                encoding="utf-8",
            )
            invoke(["gate-quality", "--work-id", work_id, "--stage", "design"], base_path=tmp)
            invoke(["review-checkpoint", "--work-id", work_id, "--stage", "design"], base_path=tmp)
            invoke(["checkpoint-decide", "--work-id", work_id, "--stage", "design",
                    "--decision", "approved", "--confirm"], base_path=tmp, expect_exit=5)
            reviews = run_dir / "reviews"
            (reviews / "design-subagent-review-v1.md").write_text("findings", encoding="utf-8")
            invoke(["checkpoint-decide", "--work-id", work_id, "--stage", "design",
                    "--decision", "approved", "--confirm"], base_path=tmp)

    def test_checkpoint_decide_refuses_unready_or_stale_artifact(self):
        with tempfile.TemporaryDirectory() as tmp:
            work_id = "WF-20260527-cds"
            self._to_review(tmp, work_id)
            record = load_record(tmp, work_id)
            record.active_artifacts[0].status = "draft"
            save_record(tmp, record)
            invoke(["checkpoint-decide", "--work-id", work_id, "--stage", "raw_requirement",
                    "--decision", "changes_requested"], base_path=tmp, expect_exit=6)
            record = load_record(tmp, work_id)
            record.active_artifacts[0].status = "ready"
            save_record(tmp, record)
            run_dir = Path(tmp) / ".req-to-plan" / work_id
            (run_dir / "00-raw-requirement.md").write_text(
                "---\nr2p_version: 2\n---\nfoo", encoding="utf-8")
            invoke(["checkpoint-decide", "--work-id", work_id, "--stage", "raw_requirement",
                    "--decision", "changes_requested"], base_path=tmp, expect_exit=6)


# ---------------------------------------------------------------------------
# stage-advance
# ---------------------------------------------------------------------------


class TestStageAdvance:
    def _to_approved(self, tmp, work_id, stage="raw_requirement"):
        invoke(["run-start", "--work-id", work_id, "--requirement", "foo"], base_path=tmp)
        invoke(["tier-lock", "--work-id", work_id, "--base", "light", "--confirm"], base_path=tmp)
        invoke(["stage-produce", "--work-id", work_id, "--stage", stage, "--content", "real"], base_path=tmp)
        invoke(["stage-ready", "--work-id", work_id, "--stage", stage], base_path=tmp)
        invoke(["gate-quality", "--work-id", work_id, "--stage", stage], base_path=tmp)
        invoke(["review-checkpoint", "--work-id", work_id, "--stage", stage], base_path=tmp)
        invoke(["checkpoint-decide", "--work-id", work_id, "--stage", stage,
                "--decision", "approved", "--confirm"], base_path=tmp)

    def test_advance_moves_to_next_stage(self):
        with tempfile.TemporaryDirectory() as tmp:
            work_id = "WF-20260527-adv"
            self._to_approved(tmp, work_id)
            invoke(["stage-advance", "--work-id", work_id], base_path=tmp)
            record = load_record(tmp, work_id)
            assert record.status == RunStatus.NEXT_STAGE
            assert record.current_stage == Stage.REQUIREMENT_BRIEF

    def test_stage_update_refused_after_stage_advance_before_entry(self):
        with tempfile.TemporaryDirectory() as tmp:
            work_id = "WF-20260527-sun"
            self._to_approved(tmp, work_id)
            invoke(["stage-advance", "--work-id", work_id], base_path=tmp)
            invoke(["stage-update", "--work-id", work_id, "--stage", "raw_requirement",
                    "--content", "mutating approved upstream after advance"],
                   base_path=tmp, expect_exit=6)
            record = load_record(tmp, work_id)
            assert record.status == RunStatus.NEXT_STAGE
            assert record.current_stage == Stage.REQUIREMENT_BRIEF

    def test_stage_update_refused_for_non_current_stage_after_entry(self):
        with tempfile.TemporaryDirectory() as tmp:
            work_id = "WF-20260527-suc"
            self._to_approved(tmp, work_id)
            invoke(["stage-advance", "--work-id", work_id], base_path=tmp)
            invoke(["gate-entry", "--work-id", work_id, "--stage", "requirement_brief"], base_path=tmp)
            invoke(["stage-update", "--work-id", work_id, "--stage", "raw_requirement",
                    "--content", "mutating approved upstream from next-stage draft"],
                   base_path=tmp, expect_exit=6)
            record = load_record(tmp, work_id)
            assert record.status == RunStatus.ACTIVE_STAGE_DRAFT
            assert record.current_stage == Stage.REQUIREMENT_BRIEF

    def test_advance_refused_without_matching_checkpoint(self):
        with tempfile.TemporaryDirectory() as tmp:
            work_id = "WF-20260527-sa2"
            invoke(["run-start", "--work-id", work_id, "--requirement", "foo"], base_path=tmp)
            record = load_record(tmp, work_id)
            record.status = RunStatus.CHECKPOINT_APPROVED  # hand-edited, no checkpoint row
            record.active_artifacts[0].status = "approved"
            save_record(tmp, record)
            invoke(["stage-advance", "--work-id", work_id], base_path=tmp, expect_exit=6)

    def test_advance_refused_at_plan(self):
        with tempfile.TemporaryDirectory() as tmp:
            work_id = "WF-20260527-sa3"
            invoke(["run-start", "--work-id", work_id, "--requirement", "foo"], base_path=tmp)
            record = load_record(tmp, work_id)
            record.status = RunStatus.CHECKPOINT_APPROVED
            record.current_stage = Stage.PLAN
            record.approved_checkpoints = [plan_checkpoint()]
            from tools.workflow_cli.models import ActiveArtifact
            record.active_artifacts = [ActiveArtifact(
                stage=Stage.PLAN, artifact="07-plan.md", version=1, status="approved")]
            save_record(tmp, record)
            invoke(["stage-advance", "--work-id", work_id], base_path=tmp, expect_exit=6)

    def test_advance_refuses_non_approved_active_artifact(self):
        with tempfile.TemporaryDirectory() as tmp:
            work_id = "WF-20260527-sa4"
            self._to_approved(tmp, work_id)
            record = load_record(tmp, work_id)
            record.active_artifacts[0].status = "ready"
            save_record(tmp, record)
            invoke(["stage-advance", "--work-id", work_id], base_path=tmp, expect_exit=6)
            record = load_record(tmp, work_id)
            record.active_artifacts[0].status = "approved"
            save_record(tmp, record)
            run_dir = Path(tmp) / ".req-to-plan" / work_id
            (run_dir / "00-raw-requirement.md").write_text(
                "---\nr2p_version: 2\n---\nfoo", encoding="utf-8")
            invoke(["stage-advance", "--work-id", work_id], base_path=tmp, expect_exit=6)

    def test_advance_refused_with_open_route(self):
        with tempfile.TemporaryDirectory() as tmp:
            work_id = "WF-20260527-sa5"
            self._to_approved(tmp, work_id)
            record = load_record(tmp, work_id)
            record.open_routes = [
                OpenRoute(
                    route_id="GAP-001",
                    from_stage=Stage.RAW_REQUIREMENT,
                    owner_stage=Stage.RAW_REQUIREMENT,
                    required_action="repair traceability",
                    status="open",
                )
            ]
            save_record(tmp, record)
            invoke(["stage-advance", "--work-id", work_id], base_path=tmp, expect_exit=6)
            record = load_record(tmp, work_id)
            assert record.status == RunStatus.CHECKPOINT_APPROVED  # unchanged; not advanced


# ---------------------------------------------------------------------------
# run-close checkpoint matching
# ---------------------------------------------------------------------------


class TestRunCloseCheckpointMatch:
    def test_run_close_refuses_mismatched_plan_checkpoint(self):
        with tempfile.TemporaryDirectory() as tmp:
            work_id = "WF-20260527-rcm"
            invoke(["run-start", "--work-id", work_id, "--requirement", "foo"], base_path=tmp)
            record = load_record(tmp, work_id)
            record.status = RunStatus.CHECKPOINT_APPROVED
            record.current_stage = Stage.PLAN
            from tools.workflow_cli.models import ActiveArtifact, CheckpointRecord
            record.active_artifacts = [ActiveArtifact(
                stage=Stage.PLAN, artifact="07-plan.md", version=2, status="approved")]
            record.approved_checkpoints = [CheckpointRecord(
                stage=Stage.PLAN, artifact="07-plan.md", version=1,
                approved_at="2026-05-27T00:00:00+00:00",
                downstream_authorization="close_workflow_run")]
            save_record(tmp, record)
            invoke(["run-close", "--work-id", work_id], base_path=tmp, expect_exit=6)

    def test_run_close_refuses_stale_plan_artifact_on_disk(self):
        with tempfile.TemporaryDirectory() as tmp:
            work_id = "WF-20260527-rcmd"
            invoke(["run-start", "--work-id", work_id, "--requirement", "foo"], base_path=tmp)
            record = load_record(tmp, work_id)
            record.status = RunStatus.CHECKPOINT_APPROVED
            record.current_stage = Stage.PLAN
            from tools.workflow_cli.models import ActiveArtifact, CheckpointRecord
            record.active_artifacts = [ActiveArtifact(
                stage=Stage.PLAN, artifact="07-plan.md", version=1, status="approved")]
            record.approved_checkpoints = [CheckpointRecord(
                stage=Stage.PLAN, artifact="07-plan.md", version=1,
                approved_at="2026-05-27T00:00:00+00:00",
                downstream_authorization="close_workflow_run")]
            save_record(tmp, record)
            run_dir = Path(tmp) / ".req-to-plan" / work_id
            (run_dir / "07-plan.md").write_text(
                "---\nr2p_version: 2\n---\nfoo", encoding="utf-8")
            invoke(["run-close", "--work-id", work_id], base_path=tmp, expect_exit=6)


# ---------------------------------------------------------------------------
# gap-open tests
# ---------------------------------------------------------------------------


def test_gap_open_routes_back_and_invalidates_downstream(capsys):
    with tempfile.TemporaryDirectory() as tmp:
        work_id, _ = _seed_plan_approved_run(tmp)
        invoke(
            ["gap-open", "--work-id", work_id, "--owner-stage", "design",
             "--required-action", "fixed-window burst flaw"],
            base_path=tmp, expect_exit=0,
        )
        rec = load_record(tmp, work_id)
        assert rec.current_stage == Stage.DESIGN
        assert rec.status == RunStatus.ACTIVE_STAGE_DRAFT
        assert len(rec.open_routes) == 1
        r = rec.open_routes[0]
        assert (r.from_stage, r.owner_stage, r.status) == (Stage.PLAN, Stage.DESIGN, "open")
        downstream = {aa.stage: aa.status for aa in rec.active_artifacts}
        assert downstream[Stage.SPEC] == "stale"
        assert downstream[Stage.PLAN] == "stale"
        assert downstream[Stage.DESIGN] == "stale"
        assert {cp.stage for cp in rec.approved_checkpoints} == {
            Stage.REQUIREMENT_BRIEF,
            Stage.RISK_DISCOVERY,
        }
        assert len(rec.stale_artifacts) == 3
        design_path = Path(tmp) / ".req-to-plan" / work_id / STAGE_ARTIFACT_MAP[Stage.DESIGN]
        assert "r2p_status: stale" in design_path.read_text(encoding="utf-8")
        assert "r2p_status: stale" in (Path(tmp) / ".req-to-plan" / work_id / STAGE_ARTIFACT_MAP[Stage.SPEC]).read_text(encoding="utf-8")
        assert "r2p_status: stale" in (Path(tmp) / ".req-to-plan" / work_id / STAGE_ARTIFACT_MAP[Stage.PLAN]).read_text(encoding="utf-8")


def test_gap_open_invalidates_reopened_copied_artifacts():
    with tempfile.TemporaryDirectory() as tmp:
        source_work_id, _ = _seed_plan_approved_run(tmp)
        source = load_record(tmp, source_work_id)
        source.status = RunStatus.CLOSED_AT_PLAN_CHECKPOINT
        save_record(tmp, source)

        invoke(
            ["run-reopen", "--from", source_work_id, "--stage", "plan", "--reason", "repair plan"],
            base_path=tmp,
            expect_exit=0,
        )
        work_id = f"{source_work_id}-r1"
        reopened = load_record(tmp, work_id)
        assert {aa.stage: aa.status for aa in reopened.active_artifacts} == {
            Stage.REQUIREMENT_BRIEF: "approved",
            Stage.RISK_DISCOVERY: "approved",
            Stage.DESIGN: "approved",
            Stage.SPEC: "approved",
        }
        assert {cp.stage for cp in reopened.approved_checkpoints} == {
            Stage.REQUIREMENT_BRIEF,
            Stage.RISK_DISCOVERY,
            Stage.DESIGN,
            Stage.SPEC,
        }

        invoke(
            ["gap-open", "--work-id", work_id, "--owner-stage", "design",
             "--required-action", "copied design was wrong"],
            base_path=tmp,
            expect_exit=0,
        )

        rec = load_record(tmp, work_id)
        assert {aa.stage: aa.status for aa in rec.active_artifacts} == {
            Stage.REQUIREMENT_BRIEF: "approved",
            Stage.RISK_DISCOVERY: "approved",
            Stage.DESIGN: "stale",
            Stage.SPEC: "stale",
        }
        assert {cp.stage for cp in rec.approved_checkpoints} == {
            Stage.REQUIREMENT_BRIEF,
            Stage.RISK_DISCOVERY,
        }
        run_dir = Path(tmp) / ".req-to-plan" / work_id
        assert "r2p_status: stale" in (
            run_dir / STAGE_ARTIFACT_MAP[Stage.DESIGN]
        ).read_text(encoding="utf-8")
        assert "r2p_status: stale" in (
            run_dir / STAGE_ARTIFACT_MAP[Stage.SPEC]
        ).read_text(encoding="utf-8")


def test_gap_open_missing_downstream_artifact_is_atomic():
    with tempfile.TemporaryDirectory() as tmp:
        work_id, run_dir = _seed_plan_approved_run(tmp)
        spec_path = run_dir / STAGE_ARTIFACT_MAP[Stage.SPEC]
        plan_path = run_dir / STAGE_ARTIFACT_MAP[Stage.PLAN]
        spec_before = spec_path.read_text(encoding="utf-8")
        plan_path.unlink()

        invoke(["gap-open", "--work-id", work_id, "--owner-stage", "design",
                "--required-action", "x"], base_path=tmp, expect_exit=7)

        rec = load_record(tmp, work_id)
        assert rec.current_stage == Stage.PLAN
        assert rec.open_routes == []
        assert {cp.stage for cp in rec.approved_checkpoints} == {
            Stage.REQUIREMENT_BRIEF,
            Stage.RISK_DISCOVERY,
            Stage.DESIGN,
            Stage.SPEC,
            Stage.PLAN,
        }
        assert {aa.stage: aa.status for aa in rec.active_artifacts}[Stage.SPEC] == "approved"
        assert {aa.stage: aa.status for aa in rec.active_artifacts}[Stage.PLAN] == "approved"
        assert spec_path.read_text(encoding="utf-8") == spec_before


def test_gap_open_rolls_back_mid_stale_write_failure(monkeypatch):
    from tools.workflow_cli.artifact import ArtifactManager

    with tempfile.TemporaryDirectory() as tmp:
        work_id, run_dir = _seed_plan_approved_run(tmp)
        run_md_path = run_dir / "run.md"
        spec_path = run_dir / STAGE_ARTIFACT_MAP[Stage.SPEC]
        plan_path = run_dir / STAGE_ARTIFACT_MAP[Stage.PLAN]
        run_md_before = run_md_path.read_text(encoding="utf-8")
        spec_before = spec_path.read_text(encoding="utf-8")
        plan_before = plan_path.read_text(encoding="utf-8")

        original_mark_stale = ArtifactManager.mark_stale

        def fail_on_plan(self, stage, reason, replaced_by):
            if stage == Stage.PLAN:
                raise RuntimeError("forced mark_stale failure")
            return original_mark_stale(self, stage, reason, replaced_by)

        monkeypatch.setattr(ArtifactManager, "mark_stale", fail_on_plan)

        invoke(["gap-open", "--work-id", work_id, "--owner-stage", "design",
                "--required-action", "x"], base_path=tmp, expect_exit=6)

        rec = load_record(tmp, work_id)
        assert rec.current_stage == Stage.PLAN
        assert rec.open_routes == []
        assert rec.stale_artifacts == []
        assert {cp.stage for cp in rec.approved_checkpoints} == {
            Stage.REQUIREMENT_BRIEF,
            Stage.RISK_DISCOVERY,
            Stage.DESIGN,
            Stage.SPEC,
            Stage.PLAN,
        }
        assert run_md_path.read_text(encoding="utf-8") == run_md_before
        assert spec_path.read_text(encoding="utf-8") == spec_before
        assert plan_path.read_text(encoding="utf-8") == plan_before


def test_gap_open_rejects_owner_not_upstream():
    with tempfile.TemporaryDirectory() as tmp:
        work_id, _ = _seed_plan_approved_run(tmp)
        # plan is current; routing to plan (==current) is not strictly upstream
        invoke(["gap-open", "--work-id", work_id, "--owner-stage", "plan",
                "--required-action", "x"], base_path=tmp, expect_exit=6)


def test_gap_open_rejects_empty_required_action():
    with tempfile.TemporaryDirectory() as tmp:
        work_id, _ = _seed_plan_approved_run(tmp)
        invoke(["gap-open", "--work-id", work_id, "--owner-stage", "design",
                "--required-action", "   "], base_path=tmp, expect_exit=2)


def test_gap_open_rejects_multiline_required_action_without_mutation():
    with tempfile.TemporaryDirectory() as tmp:
        work_id, _ = _seed_plan_approved_run(tmp)
        run_md_path = Path(tmp) / ".req-to-plan" / work_id / "run.md"
        run_md_before = run_md_path.read_text(encoding="utf-8")

        invoke(["gap-open", "--work-id", work_id, "--owner-stage", "design",
                "--required-action", "line one\nline two"], base_path=tmp, expect_exit=2)

        assert run_md_path.read_text(encoding="utf-8") == run_md_before
        rec = load_record(tmp, work_id)
        assert rec.open_routes == []


def test_gap_open_rejects_trailing_newline_required_action_without_mutation():
    # A single *trailing* newline has only one splitlines() element, so a
    # `len(splitlines()) > 1` guard would pass it through — yet it still splits
    # the open_routes table cell from its status column on reload, corrupting
    # run.md. The single-line guard must reject trailing breaks too.
    with tempfile.TemporaryDirectory() as tmp:
        work_id, _ = _seed_plan_approved_run(tmp)
        run_md_path = Path(tmp) / ".req-to-plan" / work_id / "run.md"
        run_md_before = run_md_path.read_text(encoding="utf-8")

        invoke(["gap-open", "--work-id", work_id, "--owner-stage", "design",
                "--required-action", "repair traceability\n"], base_path=tmp, expect_exit=2)

        assert run_md_path.read_text(encoding="utf-8") == run_md_before
        rec = load_record(tmp, work_id)
        assert rec.open_routes == []


def test_run_reopen_rejects_multiline_reason_without_mutation():
    with tempfile.TemporaryDirectory() as tmp:
        source = "WF-20260605-reopen-multiline"
        invoke(["run-start", "--work-id", source, "--requirement", "foo"], base_path=tmp)
        record = load_record(tmp, source)
        record.status = RunStatus.CLOSED_AT_PLAN_CHECKPOINT
        record.current_stage = Stage.CLOSED
        record.approved_checkpoints = [plan_checkpoint()]
        save_record(tmp, record)

        run_md_path = Path(tmp) / ".req-to-plan" / source / "run.md"
        run_md_before = run_md_path.read_text(encoding="utf-8")

        invoke(
            ["run-reopen", "--from", source, "--stage", "plan",
             "--reason", "line one\n## Status\narchived"],
            base_path=tmp,
            expect_exit=2,
        )

        assert run_md_path.read_text(encoding="utf-8") == run_md_before
        assert not (Path(tmp) / ".req-to-plan" / f"{source}-r1").exists()


def test_run_reopen_rejects_trailing_newline_reason_without_mutation():
    # Trailing breaks are benign for reopen_lineage (a raw last-section line),
    # but the shared single-line guard rejects them defensively — pin that.
    with tempfile.TemporaryDirectory() as tmp:
        source = "WF-20260605-reopen-trailing"
        invoke(["run-start", "--work-id", source, "--requirement", "foo"], base_path=tmp)
        record = load_record(tmp, source)
        record.status = RunStatus.CLOSED_AT_PLAN_CHECKPOINT
        record.current_stage = Stage.CLOSED
        record.approved_checkpoints = [plan_checkpoint()]
        save_record(tmp, record)

        run_md_path = Path(tmp) / ".req-to-plan" / source / "run.md"
        run_md_before = run_md_path.read_text(encoding="utf-8")

        invoke(
            ["run-reopen", "--from", source, "--stage", "plan",
             "--reason", "reopened to fix design\n"],
            base_path=tmp,
            expect_exit=2,
        )

        assert run_md_path.read_text(encoding="utf-8") == run_md_before
        assert not (Path(tmp) / ".req-to-plan" / f"{source}-r1").exists()


def test_gap_open_rejects_duplicate_open_route():
    with tempfile.TemporaryDirectory() as tmp:
        work_id, _ = _seed_plan_approved_run(tmp)
        rec = load_record(tmp, work_id)
        rec.open_routes.append(
            OpenRoute(
                route_id="R-existing",
                from_stage=Stage.PLAN,
                owner_stage=Stage.DESIGN,
                required_action="already open",
                status="open",
            )
        )
        save_record(tmp, rec)

        invoke(["gap-open", "--work-id", work_id, "--owner-stage", "design",
                "--required-action", "y"], base_path=tmp, expect_exit=6)


def test_gap_open_rejects_nested_open_route_to_different_owner():
    with tempfile.TemporaryDirectory() as tmp:
        work_id, _ = _seed_plan_approved_run(tmp)
        invoke(["gap-open", "--work-id", work_id, "--owner-stage", "design",
                "--required-action", "fix design"], base_path=tmp, expect_exit=0)

        invoke(["gap-open", "--work-id", work_id, "--owner-stage", "risk_discovery",
                "--required-action", "fix risk"], base_path=tmp, expect_exit=6)

        rec = load_record(tmp, work_id)
        open_routes = [r for r in rec.open_routes if r.status == "open"]
        assert len(open_routes) == 1
        assert open_routes[0].route_id == "R-1"
        assert open_routes[0].owner_stage == Stage.DESIGN
        assert rec.current_stage == Stage.DESIGN


def test_gap_open_rejects_closed_run():
    with tempfile.TemporaryDirectory() as tmp:
        work_id, _ = _seed_plan_approved_run(tmp)
        rec = load_record(tmp, work_id)
        rec.status = RunStatus.CLOSED_AT_PLAN_CHECKPOINT
        save_record(tmp, rec)

        invoke(["gap-open", "--work-id", work_id, "--owner-stage", "design",
                "--required-action", "x"], base_path=tmp, expect_exit=6)


def test_gap_open_rejects_unrouteable_current_status():
    with tempfile.TemporaryDirectory() as tmp:
        work_id, _ = _seed_plan_approved_run(tmp)
        rec = load_record(tmp, work_id)
        rec.status = RunStatus.NEXT_STAGE
        save_record(tmp, rec)

        invoke(["gap-open", "--work-id", work_id, "--owner-stage", "design",
                "--required-action", "x"], base_path=tmp, expect_exit=6)


def test_gap_open_rejects_invalid_owner_stage():
    with tempfile.TemporaryDirectory() as tmp:
        work_id, _ = _seed_plan_approved_run(tmp)
        invoke(["gap-open", "--work-id", work_id, "--owner-stage", "not-a-stage",
                "--required-action", "x"], base_path=tmp, expect_exit=2)


def test_gap_open_rejects_missing_run():
    with tempfile.TemporaryDirectory() as tmp:
        invoke(["gap-open", "--work-id", "WF-20260604-none", "--owner-stage", "design",
                "--required-action", "x"], base_path=tmp, expect_exit=7)


# ---------------------------------------------------------------------------
# gap-resolve tests
# ---------------------------------------------------------------------------


def _open_gap_to_design(tmp):
    work_id, run_dir = _seed_plan_approved_run(tmp)
    invoke(["gap-open", "--work-id", work_id, "--owner-stage", "design",
            "--required-action", "fix"], base_path=tmp, expect_exit=0)
    return work_id, run_dir


def test_gap_resolve_rejects_when_owner_not_ready():
    with tempfile.TemporaryDirectory() as tmp:
        work_id, _ = _open_gap_to_design(tmp)
        invoke(["gap-resolve", "--work-id", work_id, "--route-id", "R-1"],
               base_path=tmp, expect_exit=6)


def test_gap_resolve_rejects_before_owner_quality_gate():
    with tempfile.TemporaryDirectory() as tmp:
        work_id, _ = _open_gap_to_design(tmp)
        invoke(["stage-update", "--work-id", work_id, "--stage", "design",
                "--content", "# design v2\n"], base_path=tmp, expect_exit=0)
        invoke(["stage-ready", "--work-id", work_id, "--stage", "design"],
               base_path=tmp, expect_exit=0)
        # artifact is ready, but the run is still active_stage_draft until gate-quality passes
        invoke(["gap-resolve", "--work-id", work_id, "--route-id", "R-1"],
               base_path=tmp, expect_exit=6)


def test_gap_resolve_rejects_unknown_route():
    with tempfile.TemporaryDirectory() as tmp:
        work_id, _ = _open_gap_to_design(tmp)
        invoke(["gap-resolve", "--work-id", work_id, "--route-id", "R-9"],
               base_path=tmp, expect_exit=7)


def test_gap_resolve_rejects_missing_run():
    with tempfile.TemporaryDirectory() as tmp:
        invoke(["gap-resolve", "--work-id", "WF-20260604-none", "--route-id", "R-1"],
               base_path=tmp, expect_exit=7)


_DESIGN_LIGHT_CONTENT = (
    "# design v2\n\n## Design Summary\ncontent\n"
    "## Chosen Design\ncontent\n### DES-ARCH-001 Selected design\ncontent\n"
    "## SPEC Handoff\ncontent\n"
)


def test_gap_resolve_closes_route_when_owner_checkpoint_ready():
    with tempfile.TemporaryDirectory() as tmp:
        work_id, _ = _open_gap_to_design(tmp)
        # Re-work the owner: update design (-> v2 draft), mark ready, then pass quality gate
        invoke(["stage-update", "--work-id", work_id, "--stage", "design",
                "--content", _DESIGN_LIGHT_CONTENT], base_path=tmp, expect_exit=0)
        invoke(["stage-ready", "--work-id", work_id, "--stage", "design"],
               base_path=tmp, expect_exit=0)
        invoke(["gate-quality", "--work-id", work_id, "--stage", "design"],
               base_path=tmp, expect_exit=0)
        invoke(["gap-resolve", "--work-id", work_id, "--route-id", "R-1"],
               base_path=tmp, expect_exit=0)
        rec = load_record(tmp, work_id)
        assert rec.open_routes[0].status == "repaired"
        assert not [r for r in rec.open_routes if r.status == "open"]


def test_checkpoint_decide_blocked_while_route_open_then_allowed_after_resolve():
    with tempfile.TemporaryDirectory() as tmp:
        work_id, _ = _open_gap_to_design(tmp)
        invoke(["stage-update", "--work-id", work_id, "--stage", "design",
                "--content", _DESIGN_LIGHT_CONTENT], base_path=tmp, expect_exit=0)
        invoke(["stage-ready", "--work-id", work_id, "--stage", "design"],
               base_path=tmp, expect_exit=0)
        invoke(["gate-quality", "--work-id", work_id, "--stage", "design"],
               base_path=tmp, expect_exit=0)
        invoke(["review-checkpoint", "--work-id", work_id, "--stage", "design"],
               base_path=tmp, expect_exit=0)
        # route still open -> approval blocked (exit 6)
        invoke(["checkpoint-decide", "--work-id", work_id, "--stage", "design",
                "--decision", "approved", "--confirm"], base_path=tmp, expect_exit=6)
        # resolve, then approval works
        invoke(["gap-resolve", "--work-id", work_id, "--route-id", "R-1"],
               base_path=tmp, expect_exit=0)
        invoke(["checkpoint-decide", "--work-id", work_id, "--stage", "design",
                "--decision", "approved", "--confirm"], base_path=tmp, expect_exit=0)


def test_stage_advance_blocked_while_route_open():
    with tempfile.TemporaryDirectory() as tmp:
        work_id, _ = _open_gap_to_design(tmp)
        # Force the other stage-advance preconditions true so this test reaches
        # the open-route guard instead of a status/artifact/checkpoint guard.
        rec = load_record(tmp, work_id)
        rec.status = RunStatus.CHECKPOINT_APPROVED
        save_record(tmp, rec)
        invoke(["stage-advance", "--work-id", work_id], base_path=tmp, expect_exit=6)


def test_stage_advance_rejects_stale_downstream_after_route_resolved():
    with tempfile.TemporaryDirectory() as tmp:
        work_id, _ = _open_gap_to_design(tmp)

        invoke(["stage-update", "--work-id", work_id, "--stage", "design",
                "--content", _DESIGN_LIGHT_CONTENT], base_path=tmp, expect_exit=0)
        invoke(["stage-ready", "--work-id", work_id, "--stage", "design"],
               base_path=tmp, expect_exit=0)
        invoke(["gate-quality", "--work-id", work_id, "--stage", "design"],
               base_path=tmp, expect_exit=0)
        invoke(["gap-resolve", "--work-id", work_id, "--route-id", "R-1"],
               base_path=tmp, expect_exit=0)
        invoke(["review-checkpoint", "--work-id", work_id, "--stage", "design"],
               base_path=tmp, expect_exit=0)
        invoke(["checkpoint-decide", "--work-id", work_id, "--stage", "design",
                "--decision", "approved", "--confirm"], base_path=tmp, expect_exit=0)
        invoke(["stage-advance", "--work-id", work_id], base_path=tmp, expect_exit=0)
        invoke(["gate-entry", "--work-id", work_id, "--stage", "spec"],
               base_path=tmp, expect_exit=0)

        rec = load_record(tmp, work_id)
        assert rec.current_stage == Stage.SPEC
        assert {aa.stage: aa.status for aa in rec.active_artifacts}[Stage.SPEC] == "stale"
        assert not any(cp.stage == Stage.SPEC for cp in rec.approved_checkpoints)

        # Force only the status precondition true; stage-advance must still reject
        # the stale spec active artifact instead of skipping re-derivation.
        rec.status = RunStatus.CHECKPOINT_APPROVED
        save_record(tmp, rec)
        invoke(["stage-advance", "--work-id", work_id], base_path=tmp, expect_exit=6)


def test_stage_ready_rejects_stale_downstream_until_stage_update():
    with tempfile.TemporaryDirectory() as tmp:
        work_id, _ = _open_gap_to_design(tmp)

        invoke(["stage-update", "--work-id", work_id, "--stage", "design",
                "--content", _DESIGN_LIGHT_CONTENT], base_path=tmp, expect_exit=0)
        invoke(["stage-ready", "--work-id", work_id, "--stage", "design"],
               base_path=tmp, expect_exit=0)
        invoke(["gate-quality", "--work-id", work_id, "--stage", "design"],
               base_path=tmp, expect_exit=0)
        invoke(["gap-resolve", "--work-id", work_id, "--route-id", "R-1"],
               base_path=tmp, expect_exit=0)
        invoke(["review-checkpoint", "--work-id", work_id, "--stage", "design"],
               base_path=tmp, expect_exit=0)
        invoke(["checkpoint-decide", "--work-id", work_id, "--stage", "design",
                "--decision", "approved", "--confirm"], base_path=tmp, expect_exit=0)
        invoke(["stage-advance", "--work-id", work_id], base_path=tmp, expect_exit=0)
        invoke(["gate-entry", "--work-id", work_id, "--stage", "spec"],
               base_path=tmp, expect_exit=0)

        invoke(["stage-ready", "--work-id", work_id, "--stage", "spec"],
               base_path=tmp, expect_exit=6)
        rec = load_record(tmp, work_id)
        aa_by_stage = {aa.stage: aa for aa in rec.active_artifacts}
        assert aa_by_stage[Stage.SPEC].status == "stale"
        assert aa_by_stage[Stage.SPEC].version == 1

        invoke(["stage-update", "--work-id", work_id, "--stage", "spec",
                "--content", "# spec v2\n"], base_path=tmp, expect_exit=0)
        invoke(["stage-ready", "--work-id", work_id, "--stage", "spec"],
               base_path=tmp, expect_exit=0)
        rec = load_record(tmp, work_id)
        aa_by_stage = {aa.stage: aa for aa in rec.active_artifacts}
        assert aa_by_stage[Stage.SPEC].status == "ready"
        assert aa_by_stage[Stage.SPEC].version == 2


def test_gap_routing_full_cascade_back_to_plan():
    with tempfile.TemporaryDirectory() as tmp:
        work_id, _ = _seed_plan_approved_run(tmp)

        def rework_content(stage_value):
            if stage_value == "spec":
                return (
                    "# spec v2\n\n## Behavior Contracts\ncontent\n"
                    "### SPEC-CORE-001 Core behavior\ncontent\n\n"
                    "## External Documentation Checked\n\nN/A — no external dependencies\n\n"
                    "## PLAN Handoff\ncontent\n"
                )
            if stage_value == "design":
                return _DESIGN_LIGHT_CONTENT
            if stage_value == "plan":
                return (
                    "# plan v2\n\n## Tasks\n\n"
                    "### PLAN-TASK-001 do thing\n"
                    "Spec References: SPEC-CORE-001\n"
                    "Change Type: non_code\n"
                    "TDD Applicable: no\n"
                    "Files: n/a\n"
                    "Skeleton: update implementation\n"
                    "Steps:\n- [ ] apply change\n"
                    "Verification: pytest\n"
                )
            return f"# {stage_value} v2\n"

        def rework_and_approve(stage_value):
            invoke(["stage-update", "--work-id", work_id, "--stage", stage_value,
                    "--content", rework_content(stage_value)], base_path=tmp, expect_exit=0)
            invoke(["stage-ready", "--work-id", work_id, "--stage", stage_value],
                   base_path=tmp, expect_exit=0)
            invoke(["gate-quality", "--work-id", work_id, "--stage", stage_value],
                   base_path=tmp, expect_exit=0)
            invoke(["review-checkpoint", "--work-id", work_id, "--stage", stage_value],
                   base_path=tmp, expect_exit=0)
            invoke(["checkpoint-decide", "--work-id", work_id, "--stage", stage_value,
                    "--decision", "approved", "--confirm"], base_path=tmp, expect_exit=0)

        # 1. open gap to design, 2. re-work design, 3. resolve, 4. approve design
        invoke(["gap-open", "--work-id", work_id, "--owner-stage", "design",
                "--required-action", "fix"], base_path=tmp, expect_exit=0)
        invoke(["stage-update", "--work-id", work_id, "--stage", "design",
                "--content", _DESIGN_LIGHT_CONTENT], base_path=tmp, expect_exit=0)
        invoke(["stage-ready", "--work-id", work_id, "--stage", "design"],
               base_path=tmp, expect_exit=0)
        invoke(["gate-quality", "--work-id", work_id, "--stage", "design"],
               base_path=tmp, expect_exit=0)
        # gap-resolve must come before review-checkpoint (route must be closed before approval)
        invoke(["gap-resolve", "--work-id", work_id, "--route-id", "R-1"],
               base_path=tmp, expect_exit=0)
        invoke(["review-checkpoint", "--work-id", work_id, "--stage", "design"],
               base_path=tmp, expect_exit=0)
        invoke(["checkpoint-decide", "--work-id", work_id, "--stage", "design",
                "--decision", "approved", "--confirm"], base_path=tmp, expect_exit=0)

        # 5. advance to spec and re-derive; 6. advance to plan and re-derive
        invoke(["stage-advance", "--work-id", work_id], base_path=tmp, expect_exit=0)
        invoke(["gate-entry", "--work-id", work_id, "--stage", "spec"], base_path=tmp, expect_exit=0)
        rework_and_approve("spec")
        invoke(["stage-advance", "--work-id", work_id], base_path=tmp, expect_exit=0)
        invoke(["gate-entry", "--work-id", work_id, "--stage", "plan"], base_path=tmp, expect_exit=0)
        rework_and_approve("plan")

        rec = load_record(tmp, work_id)
        assert rec.current_stage == Stage.PLAN
        outstanding = [aa.stage.value for aa in rec.active_artifacts if aa.status == "stale"]
        assert outstanding == []


# ---------------------------------------------------------------------------
# status-run / status-next gap-route enrichment tests
# ---------------------------------------------------------------------------


def test_status_run_surfaces_routes_and_outstanding_stale(capsys, monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        work_id, _ = _open_gap_to_design(tmp)
        monkeypatch.setenv("R2P_JSON", "1")
        capsys.readouterr()  # flush output from setup commands
        invoke(["status-run", "--work-id", work_id], base_path=tmp, expect_exit=0)
        out = capsys.readouterr().out
        payload = json.loads(out)
        ids = [r["route_id"] for r in payload["open_routes_detail"]]
        assert ids == ["R-1"]
        assert set(payload["outstanding_stale"]) == {"design", "spec", "plan"}
        assert len(payload["stale_artifacts"]) == 3


def test_status_next_surfaces_gap_route_progress(capsys, monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        work_id, _ = _open_gap_to_design(tmp)
        monkeypatch.setenv("R2P_JSON", "1")

        capsys.readouterr()
        invoke(["status-next", "--work-id", work_id], base_path=tmp, expect_exit=0)
        payload = json.loads(capsys.readouterr().out)
        assert payload["next_allowed_operation"] == "stage_update"
        assert payload["active_item"] == "design"
        assert "R-1" in payload["resume_reason"]

        invoke(["stage-update", "--work-id", work_id, "--stage", "design",
                "--content", _DESIGN_LIGHT_CONTENT], base_path=tmp, expect_exit=0)
        invoke(["stage-ready", "--work-id", work_id, "--stage", "design"],
               base_path=tmp, expect_exit=0)
        invoke(["gate-quality", "--work-id", work_id, "--stage", "design"],
               base_path=tmp, expect_exit=0)
        invoke(["gap-resolve", "--work-id", work_id, "--route-id", "R-1"],
               base_path=tmp, expect_exit=0)

        capsys.readouterr()
        invoke(["status-next", "--work-id", work_id], base_path=tmp, expect_exit=0)
        payload = json.loads(capsys.readouterr().out)
        assert payload["next_allowed_operation"] == "checkpoint_review"
        assert payload["active_item"] == "design"
        assert "R-1" in payload["resume_reason"]
        assert "repaired" in payload["resume_reason"]


# ---------------------------------------------------------------------------
# context-build command
# ---------------------------------------------------------------------------


class TestContextBuildCommand:
    def test_context_build_writes_pack_into_run_dir(self, tmp_path):
        repo = tmp_path / "repo"
        repo.mkdir()
        (repo / "requirements.txt").write_text("pyyaml>=6.0\n", encoding="utf-8")
        run_dir = tmp_path / ".req-to-plan" / "WF-20260605-ctx"
        run_dir.mkdir(parents=True)
        with pytest.raises(SystemExit) as exc_info:
            main([
                "context-build",
                "--work-id", "WF-20260605-ctx",
                "--repo-path", str(repo),
                "--base-path", str(tmp_path),
            ])
        assert exc_info.value.code == 0
        data = json.loads((run_dir / "02-project-context.json").read_text(encoding="utf-8"))
        assert "pip" in data["package_managers"]

    def test_context_build_honors_global_base_path(self, tmp_path):
        repo = tmp_path / "repo"
        repo.mkdir()
        (repo / "requirements.txt").write_text("pyyaml>=6.0\n", encoding="utf-8")
        run_dir = tmp_path / ".req-to-plan" / "WF-20260605-global-base"
        run_dir.mkdir(parents=True)

        with pytest.raises(SystemExit) as exc_info:
            main([
                "--base-path", str(tmp_path),
                "context-build",
                "--work-id", "WF-20260605-global-base",
                "--repo-path", str(repo),
            ])

        assert exc_info.value.code == 0
        assert (run_dir / "02-project-context.json").exists()

    def test_context_build_rejects_invalid_work_id_before_writing(self, tmp_path):
        from tools.workflow_cli.output import EXIT_CLI_ERR
        repo = tmp_path / "repo"
        repo.mkdir()
        base = tmp_path / "base"
        (base / ".req-to-plan").mkdir(parents=True)
        outside = tmp_path / "existing-dir"
        outside.mkdir()

        with pytest.raises(SystemExit) as exc_info:
            main([
                "context-build",
                "--work-id", "../../existing-dir",
                "--repo-path", str(repo),
                "--base-path", str(base),
            ])

        assert exc_info.value.code == EXIT_CLI_ERR
        assert not (outside / "02-project-context.json").exists()

    def test_context_build_rejects_missing_repo_path_without_traceback(self, tmp_path, capsys):
        from tools.workflow_cli.output import EXIT_CLI_ERR
        run_dir = tmp_path / ".req-to-plan" / "WF-20260605-missing-repo"
        run_dir.mkdir(parents=True)

        with pytest.raises(SystemExit) as exc_info:
            main([
                "--base-path", str(tmp_path),
                "context-build",
                "--work-id", "WF-20260605-missing-repo",
                "--repo-path", str(tmp_path / "no-such-repo"),
            ])

        assert exc_info.value.code == EXIT_CLI_ERR
        assert "repo path not found or not a directory" in capsys.readouterr().out
        assert not (run_dir / "02-project-context.json").exists()

    def test_context_build_rejects_file_repo_path_without_traceback(self, tmp_path, capsys):
        from tools.workflow_cli.output import EXIT_CLI_ERR
        run_dir = tmp_path / ".req-to-plan" / "WF-20260605-file-repo"
        run_dir.mkdir(parents=True)
        repo_file = tmp_path / "repo.txt"
        repo_file.write_text("not a directory", encoding="utf-8")

        with pytest.raises(SystemExit) as exc_info:
            main([
                "--base-path", str(tmp_path),
                "context-build",
                "--work-id", "WF-20260605-file-repo",
                "--repo-path", str(repo_file),
            ])

        assert exc_info.value.code == EXIT_CLI_ERR
        assert "repo path not found or not a directory" in capsys.readouterr().out
        assert not (run_dir / "02-project-context.json").exists()

    def test_context_build_rejects_symlinked_workspace_dir_without_writing_target(self, tmp_path, capsys):
        repo = tmp_path / "repo"
        repo.mkdir()
        (repo / "requirements.txt").write_text("pyyaml>=6.0\n", encoding="utf-8")
        outside = tmp_path / "outside-r2p"
        outside.mkdir()
        (tmp_path / ".req-to-plan").symlink_to(outside, target_is_directory=True)

        with pytest.raises(SystemExit) as exc_info:
            main([
                "context-build",
                "--work-id", "WF-20260605-link",
                "--repo-path", str(repo),
                "--base-path", str(tmp_path),
            ])

        assert exc_info.value.code == 6  # EXIT_CONFLICT
        assert "symlink" in capsys.readouterr().out.lower()
        assert not (outside / "WF-20260605-link" / "02-project-context.json").exists()
        assert not (outside / "WF-20260605-link" / "02-project-context.md").exists()

    def test_context_build_rejects_symlinked_run_dir_without_writing_target(self, tmp_path, capsys):
        repo = tmp_path / "repo"
        repo.mkdir()
        (repo / "requirements.txt").write_text("pyyaml>=6.0\n", encoding="utf-8")
        work_id = "WF-20260605-link"
        outside = tmp_path / "outside-run"
        outside.mkdir()
        run_link = tmp_path / ".req-to-plan" / work_id
        run_link.parent.mkdir(parents=True)
        run_link.symlink_to(outside, target_is_directory=True)

        with pytest.raises(SystemExit) as exc_info:
            main([
                "context-build",
                "--work-id", work_id,
                "--repo-path", str(repo),
                "--base-path", str(tmp_path),
            ])

        assert exc_info.value.code == 6  # EXIT_CONFLICT
        assert "symlink" in capsys.readouterr().out.lower()
        assert run_link.is_symlink()
        assert not (outside / "02-project-context.json").exists()
        assert not (outside / "02-project-context.md").exists()


# ---------------------------------------------------------------------------
# run-start: Context Pack + link expansion
# ---------------------------------------------------------------------------


class TestRunStartBuildsContextPack:
    def test_run_start_with_repo_path_writes_context_pack(self, tmp_path):
        import json
        from tools.workflow_cli.cli import main
        repo = tmp_path / "repo"
        repo.mkdir()
        (repo / "requirements.txt").write_text("pyyaml>=6.0\n", encoding="utf-8")
        with pytest.raises(SystemExit) as exc:
            main([
                "--base-path", str(tmp_path),
                "run-start", "--work-id", "WF-20260605-rate-limit",
                "--requirement", "add rate limiting",
                "--repo-path", str(repo),
            ])
        assert exc.value.code == 0
        assert (tmp_path / ".req-to-plan" / "WF-20260605-rate-limit" / "02-project-context.json").exists()

    def test_run_start_without_repo_path_defaults_to_base_path(self, tmp_path):
        # --repo-path is optional: when omitted, tier estimation and the Context
        # Pack default to the workspace root (--base-path, the current directory in
        # real usage), so a standard-tier run is grounded without an explicit flag.
        from tools.workflow_cli.cli import main
        (tmp_path / "requirements.txt").write_text("pyyaml>=6.0\n", encoding="utf-8")
        with pytest.raises(SystemExit) as exc:
            main([
                "--base-path", str(tmp_path),
                "run-start", "--work-id", "WF-20260605-default-repo",
                "--requirement", "add rate limiting",
            ])
        assert exc.value.code == 0
        run_dir = tmp_path / ".req-to-plan" / "WF-20260605-default-repo"
        assert (run_dir / "02-project-context.json").exists()
        assert (run_dir / "02-project-context.md").exists()

    def test_run_start_rejects_missing_repo_path_before_writing_run(self, tmp_path, capsys):
        from tools.workflow_cli.cli import main
        from tools.workflow_cli.output import EXIT_CLI_ERR
        work_id = "WF-20260605-missing-repo"

        with pytest.raises(SystemExit) as exc:
            main([
                "--base-path", str(tmp_path),
                "run-start", "--work-id", work_id,
                "--requirement", "add rate limiting",
                "--repo-path", str(tmp_path / "no-such-repo"),
            ])

        assert exc.value.code == EXIT_CLI_ERR
        assert "repo path not found or not a directory" in capsys.readouterr().out
        assert not (tmp_path / ".req-to-plan" / work_id).exists()

    def test_run_start_rejects_file_repo_path_before_writing_run(self, tmp_path, capsys):
        from tools.workflow_cli.cli import main
        from tools.workflow_cli.output import EXIT_CLI_ERR
        work_id = "WF-20260605-file-repo"
        repo_file = tmp_path / "package.json"
        repo_file.write_text("{}", encoding="utf-8")

        with pytest.raises(SystemExit) as exc:
            main([
                "--base-path", str(tmp_path),
                "run-start", "--work-id", work_id,
                "--requirement", "add rate limiting",
                "--repo-path", str(repo_file),
            ])

        assert exc.value.code == EXIT_CLI_ERR
        assert "repo path not found or not a directory" in capsys.readouterr().out
        assert not (tmp_path / ".req-to-plan" / work_id).exists()

    def test_run_start_with_repo_path_persists_local_and_http_link_context(self, tmp_path):
        from tools.workflow_cli.cli import main
        repo = tmp_path / "repo"
        (repo / "docs").mkdir(parents=True)
        (repo / "requirements.txt").write_text("pyyaml>=6.0\n", encoding="utf-8")
        (repo / "docs" / "context.md").write_text("local architecture note", encoding="utf-8")
        requirement = "Use docs/context.md and https://example.com/spec"
        with pytest.raises(SystemExit) as exc:
            main([
                "--base-path", str(tmp_path),
                "run-start", "--work-id", "WF-20260605-links",
                "--requirement", requirement,
                "--repo-path", str(repo),
            ])
        assert exc.value.code == 0
        intake = (tmp_path / ".req-to-plan" / "WF-20260605-links" / "01-intake-brief.md").read_text(encoding="utf-8")
        assert "docs/context.md" in intake
        assert "local architecture note" in intake
        assert "https://example.com/spec" in intake
        assert "external" in intake

    def test_run_start_with_http_link_uses_link_results_for_tier(self, tmp_path):
        from tools.workflow_cli.cli import main
        repo = tmp_path / "repo"
        repo.mkdir()
        requirement = "Use https://example.com/spec"

        with pytest.raises(SystemExit) as exc:
            main([
                "--base-path", str(tmp_path),
                "run-start", "--work-id", "WF-20260605-http-link-tier",
                "--requirement", requirement,
                "--repo-path", str(repo),
            ])

        assert exc.value.code == 0
        record = load_record(tmp_path, "WF-20260605-http-link-tier")
        assert record.tier_estimate.base == TierBase.STANDARD
        intake = (tmp_path / ".req-to-plan" / "WF-20260605-http-link-tier" / "01-intake-brief.md").read_text(encoding="utf-8")
        assert "base: standard" in intake


class TestRunCloseCommitsRequirementDir:
    def test_close_rejects_symlinked_workspace_gitignore_without_copying_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            work_id, _ = _seed_plan_approved_run(base, "WF-20260101-gitignore-link")
            secret = base / "secret.txt"
            secret.write_text("PRIVATE\n", encoding="utf-8")
            gitignore = base / ".req-to-plan" / ".gitignore"
            gitignore.symlink_to(secret)

            with pytest.raises(SystemExit) as exc:
                main(["--base-path", str(base), "run-close", "--work-id", work_id])

            assert exc.value.code == 6
            assert gitignore.is_symlink()
            assert secret.read_text(encoding="utf-8") == "PRIVATE\n"
            rec = load_record(base, work_id)
            assert rec.status == RunStatus.CHECKPOINT_APPROVED
            assert rec.current_stage == Stage.PLAN

    def test_close_json_stdout_remains_parseable_when_auto_commit_skips(self, monkeypatch, capsys):
        with tempfile.TemporaryDirectory() as tmp:
            work_id, _ = _seed_plan_approved_run(tmp, "WF-20260101-json")
            monkeypatch.setenv("R2P_JSON", "1")

            with pytest.raises(SystemExit) as exc:
                main(["--base-path", str(tmp), "run-close", "--work-id", work_id])

            assert exc.value.code == 0
            captured = capsys.readouterr()
            payload = json.loads(captured.out)
            assert payload["status"] == "closed_at_plan_checkpoint"
            assert payload["message"] == "Run closed"
            assert payload["work_id"] == work_id
            assert "warning: skipped commit" in captured.err

    def test_close_treats_missing_git_as_best_effort_warning(self, monkeypatch, capsys):
        def raise_missing_git(*args, **kwargs):
            raise FileNotFoundError("git")

        with tempfile.TemporaryDirectory() as tmp:
            work_id, _ = _seed_plan_approved_run(tmp, "WF-20260101-no-git")
            monkeypatch.setattr("tools.workflow_cli.workspace.subprocess.run", raise_missing_git)

            with pytest.raises(SystemExit) as exc:
                main(["--base-path", str(tmp), "run-close", "--work-id", work_id])

            assert exc.value.code == 0
            rec = load_record(tmp, work_id)
            assert rec.status == RunStatus.CLOSED_AT_PLAN_CHECKPOINT
            assert "warning: skipped commit" in capsys.readouterr().err

    def test_failed_auto_commit_unstages_r2p_paths(self):
        import subprocess

        def git(base, *a):
            return subprocess.run(["git", "-C", str(base), *a], capture_output=True, text=True)

        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            git(base, "init", "-q")
            git(base, "config", "user.email", "t@e.com")
            git(base, "config", "user.name", "t")
            (base / "README.md").write_text("# repo\n", encoding="utf-8")
            git(base, "add", "README.md")
            git(base, "commit", "-m", "initial")
            hook = base / ".git" / "hooks" / "pre-commit"
            hook.write_text("#!/bin/sh\necho reject >&2\nexit 1\n", encoding="utf-8")
            hook.chmod(0o755)

            work_id, _ = _seed_plan_approved_run(base, "WF-20260101-hook")
            with pytest.raises(SystemExit) as exc:
                main(["--base-path", str(base), "run-close", "--work-id", work_id])

            assert exc.value.code == 0
            staged = git(base, "diff", "--cached", "--name-only", "--", ".req-to-plan").stdout.splitlines()
            assert staged == []

    def test_close_commits_requirement_dir_in_a_git_repo(self):
        import subprocess
        from tools.workflow_cli.state import (
            RunStateManager, create_run_record, upsert_active_artifact, add_checkpoint,
        )
        from tools.workflow_cli.models import (
            RunStatus, Stage, WorkId, STAGE_ARTIFACT_MAP, TierBase, TierEstimate,
        )
        from tools.workflow_cli.artifact import write_artifact

        def git(base, *a):
            return subprocess.run(["git", "-C", str(base), *a], capture_output=True, text=True)

        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            git(base, "init", "-q"); git(base, "config", "user.email", "t@e.com"); git(base, "config", "user.name", "t")
            wid = WorkId("WF-20260101-close")
            run_dir = base / ".req-to-plan" / str(wid)
            run_dir.mkdir(parents=True)
            rec = create_run_record(wid)
            rec.tier_locked = TierEstimate(base=TierBase.LIGHT, modifiers=frozenset())
            rec.current_stage = Stage.PLAN
            rec.status = RunStatus.CHECKPOINT_APPROVED
            write_artifact(run_dir, Stage.PLAN, "# Plan\n\n## Tasks\n", version=1, status="approved")
            upsert_active_artifact(rec, Stage.PLAN, STAGE_ARTIFACT_MAP[Stage.PLAN], 1, "approved")
            add_checkpoint(rec, Stage.PLAN, STAGE_ARTIFACT_MAP[Stage.PLAN], 1, "close_workflow_run")
            RunStateManager(run_dir).save(rec)

            with pytest.raises(SystemExit):
                main(["--base-path", str(base), "run-close", "--work-id", str(wid)])

            tracked = git(base, "ls-files", f".req-to-plan/{wid}").stdout
            assert f"{wid}/run.md" in tracked


class TestRunArchive:
    def _closed_run(self, base, wid_str):
        from tools.workflow_cli.state import RunStateManager, create_run_record
        from tools.workflow_cli.models import RunStatus, Stage, WorkId
        wid = WorkId(wid_str)
        run_dir = base / ".req-to-plan" / wid_str
        run_dir.mkdir(parents=True)
        rec = create_run_record(wid)
        rec.status = RunStatus.CLOSED_AT_PLAN_CHECKPOINT
        rec.current_stage = Stage.CLOSED
        RunStateManager(run_dir).save(rec)
        return run_dir

    def test_archive_moves_run_dir_under_archive(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            self._closed_run(base, "WF-20260101-arch")
            with pytest.raises(SystemExit) as exc:
                main(["--base-path", str(base), "run-archive", "--work-id", "WF-20260101-arch"])
            assert exc.value.code == 0
            assert not (base / ".req-to-plan" / "WF-20260101-arch").exists()
            assert (base / ".req-to-plan" / "archive" / "WF-20260101-arch" / "run.md").exists()

    def test_archive_sets_status_archived(self):
        from tools.workflow_cli.state import RunStateManager
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            self._closed_run(base, "WF-20260101-arch")
            with pytest.raises(SystemExit):
                main(["--base-path", str(base), "run-archive", "--work-id", "WF-20260101-arch"])
            rec = RunStateManager(base / ".req-to-plan" / "archive" / "WF-20260101-arch").load()
            assert rec.status.value == "archived"

    def test_archive_refuses_when_not_closed(self):
        from tools.workflow_cli.state import RunStateManager, create_run_record
        from tools.workflow_cli.models import WorkId
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            wid = WorkId("WF-20260101-open")
            run_dir = base / ".req-to-plan" / "WF-20260101-open"
            run_dir.mkdir(parents=True)
            RunStateManager(run_dir).save(create_run_record(wid))  # ACTIVE_STAGE_DRAFT
            with pytest.raises(SystemExit) as exc:
                main(["--base-path", str(base), "run-archive", "--work-id", "WF-20260101-open"])
            assert exc.value.code == 6  # EXIT_CONFLICT

    def test_archive_refuses_to_overwrite_existing_archive(self):
        from tools.workflow_cli.state import RunStateManager
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            self._closed_run(base, "WF-20260101-arch")
            (base / ".req-to-plan" / "archive" / "WF-20260101-arch").mkdir(parents=True)
            with pytest.raises(SystemExit) as exc:
                main(["--base-path", str(base), "run-archive", "--work-id", "WF-20260101-arch"])
            assert exc.value.code == 6  # EXIT_CONFLICT
            assert (base / ".req-to-plan" / "WF-20260101-arch").exists()  # not moved
            rec = RunStateManager(base / ".req-to-plan" / "WF-20260101-arch").load()
            assert rec.status.value == "closed_at_plan_checkpoint"  # no partial archive state

    def test_archive_rejects_symlinked_archive_parent_without_moving(self):
        from tools.workflow_cli.state import RunStateManager
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            work_id = "WF-20260101-arch"
            run_dir = self._closed_run(base, work_id)
            outside = base / "outside"
            outside.mkdir()
            (base / ".req-to-plan" / "archive").symlink_to(outside, target_is_directory=True)

            with pytest.raises(SystemExit) as exc:
                main(["--base-path", str(base), "run-archive", "--work-id", work_id])

            assert exc.value.code == 6  # EXIT_CONFLICT
            assert run_dir.exists()
            assert not (outside / work_id).exists()
            rec = RunStateManager(run_dir).load()
            assert rec.status.value == "closed_at_plan_checkpoint"

    def test_archive_rejects_symlinked_run_dir_without_writing_target(self):
        from tools.workflow_cli.state import RunStateManager, create_run_record
        from tools.workflow_cli.models import RunStatus, Stage, WorkId

        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            work_id = "WF-20260101-arch"
            outside = base / "outside-run"
            outside.mkdir()
            rec = create_run_record(WorkId(work_id))
            rec.status = RunStatus.CLOSED_AT_PLAN_CHECKPOINT
            rec.current_stage = Stage.CLOSED
            RunStateManager(outside).save(rec)
            run_link = base / ".req-to-plan" / work_id
            run_link.parent.mkdir(parents=True)
            run_link.symlink_to(outside, target_is_directory=True)

            with pytest.raises(SystemExit) as exc:
                main(["--base-path", str(base), "run-archive", "--work-id", work_id])

            assert exc.value.code == 6
            assert run_link.is_symlink()
            assert not (base / ".req-to-plan" / "archive" / work_id).exists()
            rec = RunStateManager(outside).load()
            assert rec.status.value == "closed_at_plan_checkpoint"

    def test_archive_move_failure_leaves_original_status_closed(self):
        from unittest.mock import patch
        from tools.workflow_cli.state import RunStateManager
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            run_dir = self._closed_run(base, "WF-20260101-arch")

            with patch("tools.workflow_cli.cli.shutil.move", side_effect=OSError("disk full")):
                with pytest.raises(OSError):
                    main(["--base-path", str(base), "run-archive", "--work-id", "WF-20260101-arch"])

            rec = RunStateManager(run_dir).load()
            assert rec.status.value == "closed_at_plan_checkpoint"
            assert not (base / ".req-to-plan" / "archive" / "WF-20260101-arch").exists()

    def test_archive_save_failure_moves_run_back_with_original_status(self):
        from unittest.mock import patch
        from tools.workflow_cli.state import RunStateManager
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            run_dir = self._closed_run(base, "WF-20260101-arch")
            archive_dir = base / ".req-to-plan" / "archive" / "WF-20260101-arch"

            with patch("tools.workflow_cli.cli.RunStateManager.save", side_effect=OSError("disk full")):
                with pytest.raises(OSError):
                    main(["--base-path", str(base), "run-archive", "--work-id", "WF-20260101-arch"])

            assert run_dir.exists()
            assert not archive_dir.exists()
            rec = RunStateManager(run_dir).load()
            assert rec.status.value == "closed_at_plan_checkpoint"


class TestRunExecuteStart:
    _PLAN_WITH_READONLY_PHANTOM_TASK = (
        "# Plan\n\n## Tasks\n"
        "### PLAN-TASK-001: real task\nFiles:\n- a.py\n"
        "\n## Project Context (read-only)\n"
        "copied context that mentions an old task\n"
        "### PLAN-TASK-999: phantom task\nFiles:\n- ghost.py\n"
        "<!-- /r2p-read-only -->\n"
    )

    def _closed_run_with_plan(self, base, wid_str, plan_body):
        from tools.workflow_cli.state import RunStateManager, create_run_record
        from tools.workflow_cli.models import RunStatus, Stage, WorkId
        from tools.workflow_cli.artifact import write_artifact
        wid = WorkId(wid_str)
        run_dir = base / ".req-to-plan" / wid_str
        run_dir.mkdir(parents=True)
        rec = create_run_record(wid)
        rec.status = RunStatus.CLOSED_AT_PLAN_CHECKPOINT
        rec.current_stage = Stage.CLOSED
        write_artifact(run_dir, Stage.PLAN, plan_body, version=1, status="approved")
        RunStateManager(run_dir).save(rec)
        return run_dir

    def test_execute_start_sets_executing_and_seeds_ledger(self):
        from tools.workflow_cli.state import RunStateManager
        plan = (
            "# Plan\n\n## Tasks\n"
            "### PLAN-TASK-001: first task\nFiles:\n- a.py\n"
            "### PLAN-TASK-002: second task\nFiles:\n- b.py\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            run_dir = self._closed_run_with_plan(base, "WF-20260101-exec", plan)
            with pytest.raises(SystemExit) as exc:
                main(["--base-path", str(base), "run-execute-start", "--work-id", "WF-20260101-exec"])
            assert exc.value.code == 0
            rec = RunStateManager(run_dir).load()
            assert rec.status.value == "executing"
            ledger = (run_dir / "execution" / "progress.md").read_text(encoding="utf-8")
            assert "- [ ] PLAN-TASK-001 first task" in ledger
            assert "- [ ] PLAN-TASK-002 second task" in ledger

    def test_execute_start_ignores_readonly_plan_task_headings(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            run_dir = self._closed_run_with_plan(
                base,
                "WF-20260101-exec",
                self._PLAN_WITH_READONLY_PHANTOM_TASK,
            )
            with pytest.raises(SystemExit) as exc:
                main(["--base-path", str(base), "run-execute-start", "--work-id", "WF-20260101-exec"])

            assert exc.value.code == 0
            ledger = (run_dir / "execution" / "progress.md").read_text(encoding="utf-8")
            assert "- [ ] PLAN-TASK-001 real task" in ledger
            assert "PLAN-TASK-999" not in ledger

    def test_execute_start_ledger_failure_leaves_status_closed(self):
        from tools.workflow_cli.state import RunStateManager
        plan = "# Plan\n\n## Tasks\n### PLAN-TASK-001: first task\nFiles:\n- a.py\n"
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            run_dir = self._closed_run_with_plan(base, "WF-20260101-exec", plan)
            (run_dir / "execution").write_text("not a directory", encoding="utf-8")

            with pytest.raises(FileExistsError):
                main(["--base-path", str(base), "run-execute-start", "--work-id", "WF-20260101-exec"])

            rec = RunStateManager(run_dir).load()
            assert rec.status.value == "closed_at_plan_checkpoint"
            assert rec.resume_context.last_completed_operation != "execute_start"
            assert rec.resume_context.next_allowed_operation != "implement_tasks"

    def test_execute_start_rejects_symlinked_execution_dir_without_writing_ledger(self):
        from tools.workflow_cli.state import RunStateManager
        plan = "# Plan\n\n## Tasks\n### PLAN-TASK-001: first task\nFiles:\n- a.py\n"
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            run_dir = self._closed_run_with_plan(base, "WF-20260101-exec", plan)
            outside = base / "outside"
            outside.mkdir()
            (run_dir / "execution").symlink_to(outside, target_is_directory=True)

            with pytest.raises(SystemExit) as exc:
                main(["--base-path", str(base), "run-execute-start", "--work-id", "WF-20260101-exec"])

            assert exc.value.code == 6
            assert not (outside / "progress.md").exists()
            rec = RunStateManager(run_dir).load()
            assert rec.status.value == "closed_at_plan_checkpoint"
            assert rec.resume_context.last_completed_operation != "execute_start"
            assert rec.resume_context.next_allowed_operation != "implement_tasks"

    def test_execute_start_rejects_symlinked_run_dir_without_writing_ledger(self):
        from tools.workflow_cli.artifact import write_artifact
        from tools.workflow_cli.state import RunStateManager, create_run_record
        from tools.workflow_cli.models import RunStatus, Stage, WorkId

        plan = "# Plan\n\n## Tasks\n### PLAN-TASK-001: first task\nFiles:\n- a.py\n"
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            work_id = "WF-20260101-exec"
            outside = base / "outside-run"
            outside.mkdir()
            rec = create_run_record(WorkId(work_id))
            rec.status = RunStatus.CLOSED_AT_PLAN_CHECKPOINT
            rec.current_stage = Stage.CLOSED
            write_artifact(outside, Stage.PLAN, plan, version=1, status="approved")
            RunStateManager(outside).save(rec)
            run_link = base / ".req-to-plan" / work_id
            run_link.parent.mkdir(parents=True)
            run_link.symlink_to(outside, target_is_directory=True)

            with pytest.raises(SystemExit) as exc:
                main(["--base-path", str(base), "run-execute-start", "--work-id", work_id])

            assert exc.value.code == 6
            assert run_link.is_symlink()
            assert not (outside / "execution" / "progress.md").exists()
            rec = RunStateManager(outside).load()
            assert rec.status.value == "closed_at_plan_checkpoint"
            assert rec.resume_context.last_completed_operation != "execute_start"
            assert rec.resume_context.next_allowed_operation != "implement_tasks"

    def test_execute_start_rejects_symlinked_workspace_dir_without_writing_ledger(self):
        from tools.workflow_cli.state import RunStateManager

        plan = "# Plan\n\n## Tasks\n### PLAN-TASK-001: first task\nFiles:\n- a.py\n"
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            outside = base / "outside-r2p"
            outside.mkdir()
            (base / ".req-to-plan").symlink_to(outside, target_is_directory=True)
            work_id = "WF-20260101-exec"
            self._closed_run_with_plan(base, work_id, plan)

            with pytest.raises(SystemExit) as exc:
                main(["--base-path", str(base), "run-execute-start", "--work-id", work_id])

            assert exc.value.code == 6
            assert not (outside / work_id / "execution" / "progress.md").exists()
            rec = RunStateManager(outside / work_id).load()
            assert rec.status.value == "closed_at_plan_checkpoint"
            assert rec.resume_context.last_completed_operation != "execute_start"
            assert rec.resume_context.next_allowed_operation != "implement_tasks"

    def test_execute_start_rejects_plan_without_task_anchors(self):
        from tools.workflow_cli.state import RunStateManager
        plan = "# Plan\n\n## Tasks\n- first task\n- second task\n"
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            run_dir = self._closed_run_with_plan(base, "WF-20260101-exec", plan)

            with pytest.raises(SystemExit) as exc:
                main([
                    "--base-path",
                    str(base),
                    "run-execute-start",
                    "--work-id",
                    "WF-20260101-exec",
                ])

            assert exc.value.code == 6  # EXIT_CONFLICT
            rec = RunStateManager(run_dir).load()
            assert rec.status.value == "closed_at_plan_checkpoint"
            assert not (run_dir / "execution").exists()

    def test_executing_run_can_be_reopened_for_upstream_repair(self):
        plan = (
            "# Plan\n\n## Tasks\n"
            "### PLAN-TASK-001: first task\nFiles:\n- a.py\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            self._closed_run_with_plan(base, "WF-20260101-exec", plan)
            with pytest.raises(SystemExit) as exc:
                main([
                    "--base-path",
                    str(base),
                    "run-execute-start",
                    "--work-id",
                    "WF-20260101-exec",
                ])
            assert exc.value.code == 0

            with pytest.raises(SystemExit) as exc:
                main([
                    "--base-path",
                    str(base),
                    "run-reopen",
                    "--from",
                    "WF-20260101-exec",
                    "--stage",
                    "plan",
                    "--reason",
                    "pre-flight found PLAN defect",
                ])

            assert exc.value.code == 0
            assert (base / ".req-to-plan" / "WF-20260101-exec-r1" / "run.md").exists()
            assert load_record(base, "WF-20260101-exec").status == RunStatus.CLOSED_AT_PLAN_CHECKPOINT
            from tools.workflow_cli.agent_shortcuts import scan_open_runs
            assert scan_open_runs(base) == ["WF-20260101-exec-r1"]

    def test_execute_start_refuses_when_not_closed(self):
        from tools.workflow_cli.state import RunStateManager, create_run_record
        from tools.workflow_cli.models import WorkId
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            wid = WorkId("WF-20260101-open")
            run_dir = base / ".req-to-plan" / "WF-20260101-open"
            run_dir.mkdir(parents=True)
            RunStateManager(run_dir).save(create_run_record(wid))  # ACTIVE_STAGE_DRAFT
            with pytest.raises(SystemExit) as exc:
                main(["--base-path", str(base), "run-execute-start", "--work-id", "WF-20260101-open"])
            assert exc.value.code == 6  # EXIT_CONFLICT


class TestRunArchiveFromExecuting:
    _COMPLETE_LEDGER = (
        "# Execution Progress\n\nwork_id: WF-20260101-exec\n\n"
        "- [x] PLAN-TASK-001 first task\n- [x] PLAN-TASK-002 second task\n"
    )

    def _executing_run(self, base, wid_str, ledger, plan=None):
        """An EXECUTING run; ledger=None seeds no execution/progress.md.
        plan=<text> writes an approved 07-plan.md artifact for anchor cross-check."""
        from tools.workflow_cli.state import RunStateManager, create_run_record
        from tools.workflow_cli.models import RunStatus, Stage, WorkId
        wid = WorkId(wid_str)
        run_dir = base / ".req-to-plan" / wid_str
        run_dir.mkdir(parents=True)
        rec = create_run_record(wid)
        rec.status = RunStatus.EXECUTING
        rec.current_stage = Stage.CLOSED
        RunStateManager(run_dir).save(rec)
        if plan is not None:
            from tools.workflow_cli.artifact import write_artifact
            write_artifact(run_dir, Stage.PLAN, plan, version=1, status="approved")
        if ledger is not None:
            exec_dir = run_dir / "execution"
            exec_dir.mkdir(parents=True, exist_ok=True)
            (exec_dir / "progress.md").write_text(ledger, encoding="utf-8")
        return run_dir

    def test_archive_executing_run_with_complete_ledger(self):
        from tools.workflow_cli.state import RunStateManager
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            run_dir = self._executing_run(
                base,
                "WF-20260101-exec",
                self._COMPLETE_LEDGER,
                plan=self._TWO_TASK_PLAN,
            )
            _seed_approved_final_review(run_dir)
            with pytest.raises(SystemExit) as exc:
                main(["--base-path", str(base), "run-archive", "--work-id", "WF-20260101-exec"])
            assert exc.value.code == 0
            assert (base / ".req-to-plan" / "archive" / "WF-20260101-exec" / "run.md").exists()
            rec = RunStateManager(base / ".req-to-plan" / "archive" / "WF-20260101-exec").load()
            assert rec.status.value == "archived"

    def test_archive_executing_run_rejected_when_plan_missing(self):
        from tools.workflow_cli.state import RunStateManager
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            run_dir = self._executing_run(base, "WF-20260101-exec", self._COMPLETE_LEDGER)
            with pytest.raises(SystemExit) as exc:
                main(["--base-path", str(base), "run-archive", "--work-id", "WF-20260101-exec"])
            assert exc.value.code == 3  # EXIT_GATE_FAIL
            assert run_dir.exists()  # not moved
            assert not (base / ".req-to-plan" / "archive" / "WF-20260101-exec").exists()
            assert RunStateManager(run_dir).load().status.value == "executing"

    def test_archive_executing_run_rejected_when_ledger_missing(self):
        from tools.workflow_cli.state import RunStateManager
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            run_dir = self._executing_run(base, "WF-20260101-exec", None)
            with pytest.raises(SystemExit) as exc:
                main(["--base-path", str(base), "run-archive", "--work-id", "WF-20260101-exec"])
            assert exc.value.code == 3  # EXIT_GATE_FAIL
            assert run_dir.exists()  # not moved
            assert not (base / ".req-to-plan" / "archive" / "WF-20260101-exec").exists()
            assert RunStateManager(run_dir).load().status.value == "executing"

    def test_archive_executing_run_rejects_symlinked_ledger(self, capsys):
        from tools.workflow_cli.state import RunStateManager
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            run_dir = self._executing_run(
                base,
                "WF-20260101-exec",
                None,
                plan=self._TWO_TASK_PLAN,
            )
            outside = base / "outside-progress.md"
            outside.write_text(self._COMPLETE_LEDGER, encoding="utf-8")
            exec_dir = run_dir / "execution"
            exec_dir.mkdir()
            (exec_dir / "progress.md").symlink_to(outside)

            with pytest.raises(SystemExit) as exc:
                main(["--base-path", str(base), "run-archive", "--work-id", "WF-20260101-exec"])

            assert exc.value.code == 3  # EXIT_GATE_FAIL
            assert "symlink" in capsys.readouterr().out.lower()
            assert run_dir.exists()  # not moved
            assert not (base / ".req-to-plan" / "archive" / "WF-20260101-exec").exists()
            assert RunStateManager(run_dir).load().status.value == "executing"

    def test_archive_executing_run_rejects_symlinked_execution_dir(self, capsys):
        from tools.workflow_cli.state import RunStateManager
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            run_dir = self._executing_run(
                base,
                "WF-20260101-exec",
                None,
                plan=self._TWO_TASK_PLAN,
            )
            outside = base / "outside-execution"
            outside.mkdir()
            (outside / "progress.md").write_text(self._COMPLETE_LEDGER, encoding="utf-8")
            (run_dir / "execution").symlink_to(outside, target_is_directory=True)

            with pytest.raises(SystemExit) as exc:
                main(["--base-path", str(base), "run-archive", "--work-id", "WF-20260101-exec"])

            assert exc.value.code == 3  # EXIT_GATE_FAIL
            assert "symlink" in capsys.readouterr().out.lower()
            assert run_dir.exists()  # not moved
            assert not (base / ".req-to-plan" / "archive" / "WF-20260101-exec").exists()
            assert RunStateManager(run_dir).load().status.value == "executing"

    @pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="mkfifo unavailable on this platform")
    def test_archive_executing_run_rejects_fifo_ledger_without_blocking(self, capsys):
        from tools.workflow_cli.state import RunStateManager
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            run_dir = self._executing_run(base, "WF-20260101-exec", None, plan=self._TWO_TASK_PLAN)
            exec_dir = run_dir / "execution"
            exec_dir.mkdir()
            os.mkfifo(exec_dir / "progress.md")  # a FIFO with no writer must not hang the gate

            with pytest.raises(SystemExit) as exc:
                main(["--base-path", str(base), "run-archive", "--work-id", "WF-20260101-exec"])

            assert exc.value.code == 3  # EXIT_GATE_FAIL
            assert "regular file" in capsys.readouterr().out.lower()
            assert run_dir.exists()  # not moved
            assert RunStateManager(run_dir).load().status.value == "executing"

    def test_archive_executing_run_rejected_with_unchecked_task(self):
        from tools.workflow_cli.state import RunStateManager
        ledger = (
            "# Execution Progress\n\nwork_id: WF-20260101-exec\n\n"
            "- [x] PLAN-TASK-001 first task\n- [ ] PLAN-TASK-002 second task\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            run_dir = self._executing_run(base, "WF-20260101-exec", ledger)
            with pytest.raises(SystemExit) as exc:
                main(["--base-path", str(base), "run-archive", "--work-id", "WF-20260101-exec"])
            assert exc.value.code == 3  # EXIT_GATE_FAIL
            assert run_dir.exists()  # not moved
            assert RunStateManager(run_dir).load().status.value == "executing"

    def test_archive_executing_run_rejected_when_ledger_has_no_tasks(self):
        ledger = "# Execution Progress\n\nwork_id: WF-20260101-exec\n\n"
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            run_dir = self._executing_run(base, "WF-20260101-exec", ledger)
            with pytest.raises(SystemExit) as exc:
                main(["--base-path", str(base), "run-archive", "--work-id", "WF-20260101-exec"])
            assert exc.value.code == 3  # EXIT_GATE_FAIL
            assert run_dir.exists()  # not moved

    def test_archive_executing_run_force_overrides_incomplete_ledger(self):
        ledger = (
            "# Execution Progress\n\nwork_id: WF-20260101-exec\n\n"
            "- [ ] PLAN-TASK-001 first task\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            self._executing_run(base, "WF-20260101-exec", ledger)
            with pytest.raises(SystemExit) as exc:
                main(["--base-path", str(base), "run-archive", "--work-id", "WF-20260101-exec", "--force"])
            assert exc.value.code == 0
            assert (base / ".req-to-plan" / "archive" / "WF-20260101-exec" / "run.md").exists()

    def test_archive_force_overrides_missing_ledger(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            self._executing_run(base, "WF-20260101-exec", None)
            with pytest.raises(SystemExit) as exc:
                main(["--base-path", str(base), "run-archive", "--work-id", "WF-20260101-exec", "--force"])
            assert exc.value.code == 0
            assert (base / ".req-to-plan" / "archive" / "WF-20260101-exec" / "run.md").exists()

    _TWO_TASK_PLAN = (
        "# Plan\n\n## Tasks\n"
        "### PLAN-TASK-001: first task\nFiles:\n- a.py\n"
        "### PLAN-TASK-002: second task\nFiles:\n- b.py\n"
    )
    _PLAN_WITH_READONLY_PHANTOM_TASK = (
        "# Plan\n\n## Tasks\n"
        "### PLAN-TASK-001: real task\nFiles:\n- a.py\n"
        "\n## Upstream Summary (read-only)\n"
        "copied upstream plan fragment\n"
        "### PLAN-TASK-999: phantom task\nFiles:\n- ghost.py\n"
        "<!-- /r2p-read-only -->\n"
    )

    def test_archive_rejected_when_ledger_drops_a_plan_task(self):
        from tools.workflow_cli.state import RunStateManager
        # PLAN has 001 and 002; ledger dropped the 002 line entirely (no unchecked box).
        ledger = "# Execution Progress\n\nwork_id: WF-20260101-exec\n\n- [x] PLAN-TASK-001 first task\n"
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            run_dir = self._executing_run(base, "WF-20260101-exec", ledger, plan=self._TWO_TASK_PLAN)
            with pytest.raises(SystemExit) as exc:
                main(["--base-path", str(base), "run-archive", "--work-id", "WF-20260101-exec"])
            assert exc.value.code == 3  # EXIT_GATE_FAIL
            assert run_dir.exists()  # not moved
            assert RunStateManager(run_dir).load().status.value == "executing"

    def test_archive_ignores_readonly_plan_task_headings(self):
        ledger = "# Execution Progress\n\nwork_id: WF-20260101-exec\n\n- [x] PLAN-TASK-001 real task\n"
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            run_dir = self._executing_run(
                base,
                "WF-20260101-exec",
                ledger,
                plan=self._PLAN_WITH_READONLY_PHANTOM_TASK,
            )
            _seed_approved_final_review(run_dir)
            with pytest.raises(SystemExit) as exc:
                main(["--base-path", str(base), "run-archive", "--work-id", "WF-20260101-exec"])
            assert exc.value.code == 0
            assert (base / ".req-to-plan" / "archive" / "WF-20260101-exec" / "run.md").exists()

    def test_archive_passes_when_ledger_covers_all_plan_tasks(self):
        ledger = (
            "# Execution Progress\n\nwork_id: WF-20260101-exec\n\n"
            "- [x] PLAN-TASK-001 first task\n- [x] PLAN-TASK-002 second task\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            run_dir = self._executing_run(base, "WF-20260101-exec", ledger, plan=self._TWO_TASK_PLAN)
            _seed_approved_final_review(run_dir)
            with pytest.raises(SystemExit) as exc:
                main(["--base-path", str(base), "run-archive", "--work-id", "WF-20260101-exec"])
            assert exc.value.code == 0
            assert (base / ".req-to-plan" / "archive" / "WF-20260101-exec" / "run.md").exists()


# ---------------------------------------------------------------------------
# Honesty-guard helper (SPEC-HONEST-001) — phrase/pattern-based, NOT substring.
# ---------------------------------------------------------------------------

_HONESTY_DENY = [
    re.compile(r"\bverified\b", re.I),
    re.compile(r"\bvalidated\b", re.I),
    re.compile(r"\bguaranteed\s+correct\b", re.I),
    re.compile(r"\bcorrect(?:ness)?\s+is\s+guaranteed\b", re.I),
    re.compile(r"\bproven\s+correct\b", re.I),
    re.compile(r"\breview\s+approved\b", re.I),  # ADJACENT words: \s+ whitespace-only
    # "review not approved" (canonical msg) does NOT match — the \s+ gap is
    # whitespace only, so "not " in between breaks the match.
]


def _is_honest(message: str) -> bool:
    """Return True iff message contains none of the affirmative-claim patterns."""
    return not any(p.search(message) for p in _HONESTY_DENY)


def _seed_approved_final_review(run_dir):
    """Seed execution/final-review.md with 'Verdict: Approved' in run_dir."""
    exec_dir = run_dir / "execution"
    exec_dir.mkdir(parents=True, exist_ok=True)
    (exec_dir / "final-review.md").write_text(
        "# Final Review\n\nVerdict: Approved\n", encoding="utf-8"
    )


# ---------------------------------------------------------------------------
# New tests: SPEC-ARCHIVE-001, SPEC-SEED-001, SPEC-HONEST-001
# ---------------------------------------------------------------------------

class TestFinalReviewGateInArchive:
    """SPEC-ARCHIVE-001: archive wires check_final_review_recorded after completion gate."""

    _COMPLETE_LEDGER = (
        "# Execution Progress\n\nwork_id: WF-20260101-exec\n\n"
        "- [x] PLAN-TASK-001 first task\n- [x] PLAN-TASK-002 second task\n"
    )
    _TWO_TASK_PLAN = (
        "# Plan\n\n## Tasks\n"
        "### PLAN-TASK-001: first task\nFiles:\n- a.py\n"
        "### PLAN-TASK-002: second task\nFiles:\n- b.py\n"
    )

    def _executing_run(self, base, wid_str, ledger, plan=None):
        from tools.workflow_cli.state import RunStateManager, create_run_record
        from tools.workflow_cli.models import RunStatus, Stage, WorkId
        wid = WorkId(wid_str)
        run_dir = base / ".req-to-plan" / wid_str
        run_dir.mkdir(parents=True)
        rec = create_run_record(wid)
        rec.status = RunStatus.EXECUTING
        rec.current_stage = Stage.CLOSED
        RunStateManager(run_dir).save(rec)
        if plan is not None:
            from tools.workflow_cli.artifact import write_artifact
            write_artifact(run_dir, Stage.PLAN, plan, version=1, status="approved")
        if ledger is not None:
            exec_dir = run_dir / "execution"
            exec_dir.mkdir(parents=True, exist_ok=True)
            (exec_dir / "progress.md").write_text(ledger, encoding="utf-8")
        return run_dir

    def test_executing_with_complete_ledger_no_marker_is_rejected(self, capsys):
        """EXECUTING + complete ledger + NO final-review.md → exit 3, run stays EXECUTING."""
        from tools.workflow_cli.state import RunStateManager
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            run_dir = self._executing_run(
                base, "WF-20260101-exec", self._COMPLETE_LEDGER, plan=self._TWO_TASK_PLAN
            )
            # No final-review.md seeded
            with pytest.raises(SystemExit) as exc:
                main(["--base-path", str(base), "run-archive", "--work-id", "WF-20260101-exec"])
            assert exc.value.code == 3  # EXIT_GATE_FAIL
            assert run_dir.exists()  # run dir was NOT moved
            assert not (base / ".req-to-plan" / "archive" / "WF-20260101-exec").exists()
            assert RunStateManager(run_dir).load().status.value == "executing"

    def test_executing_with_complete_ledger_and_approved_marker_succeeds(self):
        """EXECUTING + complete ledger + approved marker → archive succeeds."""
        from tools.workflow_cli.state import RunStateManager
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            run_dir = self._executing_run(
                base, "WF-20260101-exec", self._COMPLETE_LEDGER, plan=self._TWO_TASK_PLAN
            )
            _seed_approved_final_review(run_dir)
            with pytest.raises(SystemExit) as exc:
                main(["--base-path", str(base), "run-archive", "--work-id", "WF-20260101-exec"])
            assert exc.value.code == 0
            archive_run = base / ".req-to-plan" / "archive" / "WF-20260101-exec"
            assert archive_run.exists()
            assert RunStateManager(archive_run).load().status.value == "archived"

    def test_executing_force_bypasses_both_gates(self):
        """EXECUTING + --force → bypasses completion AND final-review gate."""
        # Incomplete ledger + no marker — force must still archive.
        incomplete_ledger = (
            "# Execution Progress\n\nwork_id: WF-20260101-exec\n\n"
            "- [ ] PLAN-TASK-001 first task\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            self._executing_run(
                base, "WF-20260101-exec", incomplete_ledger, plan=self._TWO_TASK_PLAN
            )
            # No final-review.md seeded
            with pytest.raises(SystemExit) as exc:
                main([
                    "--base-path", str(base), "run-archive",
                    "--work-id", "WF-20260101-exec", "--force",
                ])
            assert exc.value.code == 0
            assert (base / ".req-to-plan" / "archive" / "WF-20260101-exec" / "run.md").exists()

    def test_closed_at_plan_checkpoint_archive_no_marker_required(self):
        """CLOSED_AT_PLAN_CHECKPOINT archive never reaches the gate; no marker needed."""
        from tools.workflow_cli.state import RunStateManager, create_run_record
        from tools.workflow_cli.models import RunStatus, Stage, WorkId
        from tools.workflow_cli.artifact import write_artifact
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            wid = WorkId("WF-20260101-exec")
            run_dir = base / ".req-to-plan" / "WF-20260101-exec"
            run_dir.mkdir(parents=True)
            rec = create_run_record(wid)
            rec.status = RunStatus.CLOSED_AT_PLAN_CHECKPOINT
            rec.current_stage = Stage.CLOSED
            RunStateManager(run_dir).save(rec)
            # No execution/ subdir at all
            with pytest.raises(SystemExit) as exc:
                main(["--base-path", str(base), "run-archive", "--work-id", "WF-20260101-exec"])
            assert exc.value.code == 0
            archive_run = base / ".req-to-plan" / "archive" / "WF-20260101-exec"
            assert archive_run.exists()
            assert RunStateManager(archive_run).load().status.value == "archived"


class TestExecuteStartDoesNotSeedFinalReview:
    """SPEC-SEED-001: run-execute-start must NOT create execution/final-review.md."""

    def _closed_run_with_plan(self, base, wid_str, plan_body):
        from tools.workflow_cli.state import RunStateManager, create_run_record
        from tools.workflow_cli.models import RunStatus, Stage, WorkId
        from tools.workflow_cli.artifact import write_artifact
        wid = WorkId(wid_str)
        run_dir = base / ".req-to-plan" / wid_str
        run_dir.mkdir(parents=True)
        rec = create_run_record(wid)
        rec.status = RunStatus.CLOSED_AT_PLAN_CHECKPOINT
        rec.current_stage = Stage.CLOSED
        write_artifact(run_dir, Stage.PLAN, plan_body, version=1, status="approved")
        RunStateManager(run_dir).save(rec)
        return run_dir

    def test_execute_start_does_not_create_final_review_marker(self):
        """After run-execute-start, execution/final-review.md must NOT exist."""
        plan = (
            "# Plan\n\n## Tasks\n"
            "### PLAN-TASK-001: first task\nFiles:\n- a.py\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            run_dir = self._closed_run_with_plan(base, "WF-20260101-exec", plan)
            with pytest.raises(SystemExit) as exc:
                main(["--base-path", str(base), "run-execute-start", "--work-id", "WF-20260101-exec"])
            assert exc.value.code == 0
            # progress.md must be created (sanity check the command ran)
            assert (run_dir / "execution" / "progress.md").exists()
            # final-review.md must NOT be seeded
            assert not (run_dir / "execution" / "final-review.md").exists()


class TestHonestyGuard:
    """SPEC-HONEST-001: phrase/pattern honesty guard — not a substring match."""

    # ------------------------------------------------------------------
    # DENY: affirmative-claim patterns must be flagged as dishonest
    # ------------------------------------------------------------------
    def test_deny_verified(self):
        assert not _is_honest("the result was verified"), "should be dishonest"

    def test_deny_validated(self):
        assert not _is_honest("output validated by tests"), "should be dishonest"

    def test_deny_guaranteed_correct(self):
        assert not _is_honest("guaranteed correct"), "should be dishonest"

    def test_deny_review_approved_adjacent(self):
        assert not _is_honest("review approved"), "should be dishonest"

    def test_deny_proven_correct(self):
        assert not _is_honest("proven correct"), "should be dishonest"

    def test_deny_correctness_is_guaranteed(self):
        assert not _is_honest("correctness is guaranteed"), "should be dishonest"

    # ------------------------------------------------------------------
    # ALLOW literals: canonical disclaimer + protocol literal must NOT trip guard
    # ------------------------------------------------------------------
    def test_allow_not_a_correctness_guarantee(self):
        assert _is_honest("not a correctness guarantee"), "must be honest"

    def test_allow_verdict_approved(self):
        assert _is_honest("Verdict: Approved"), "must be honest"

    def test_allow_canonical_not_approved_msg(self):
        # The verbatim canonical message from gates.py must pass
        msg = (
            "Final whole-branch review not approved: execution/final-review.md is "
            "missing, or its current (last unfenced) 'Verdict:' line is not "
            "'Approved'. Presence check on the review audit trail — not a correctness "
            "guarantee. Record 'Verdict: Approved', or re-run with --force to archive "
            "an abandoned run."
        )
        assert _is_honest(msg), "canonical not-approved msg must be honest"

    def test_allow_not_a_correctness_guarantee_phrase(self):
        assert _is_honest("not a correctness guarantee"), "must be honest"

    def test_allow_review_not_approved(self):
        # "review not approved" must NOT trip the \breview\s+approved\b guard
        assert _is_honest("Final whole-branch review not approved"), "must be honest"

    def test_allow_arbitrary_honest_string(self):
        assert _is_honest("Presence check on the review audit trail"), "must be honest"

    # ------------------------------------------------------------------
    # ALLOW coverage: every mode-specific gate failure message must be honest
    # ------------------------------------------------------------------
    def test_gate_messages_are_honest(self):
        """Every failure message from check_final_review_recorded must pass _is_honest."""
        from tools.workflow_cli.gates import check_final_review_recorded
        import stat

        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run"
            run_dir.mkdir()
            exec_dir = run_dir / "execution"
            exec_dir.mkdir()

            # Case a: missing file
            gate = check_final_review_recorded(run_dir)
            assert not gate.passed
            for msg in gate.issues:
                assert _is_honest(msg), f"missing-file msg not honest: {msg!r}"

            # Case d: file exists but no Verdict: line
            marker = exec_dir / "final-review.md"
            marker.write_text("# Review\n\nsome content\n", encoding="utf-8")
            gate = check_final_review_recorded(run_dir)
            assert not gate.passed
            for msg in gate.issues:
                assert _is_honest(msg), f"no-verdict msg not honest: {msg!r}"

            # Case e: unsupported verdict value
            marker.write_text("Verdict: Maybe\n", encoding="utf-8")
            gate = check_final_review_recorded(run_dir)
            assert not gate.passed
            for msg in gate.issues:
                assert _is_honest(msg), f"unsupported-verdict msg not honest: {msg!r}"

            # Case f: changes requested
            marker.write_text("Verdict: Changes Requested\n", encoding="utf-8")
            gate = check_final_review_recorded(run_dir)
            assert not gate.passed
            for msg in gate.issues:
                assert _is_honest(msg), f"changes-requested msg not honest: {msg!r}"

            # Case b: symlink
            marker.unlink()
            outside = Path(tmp) / "outside.md"
            outside.write_text("Verdict: Approved\n", encoding="utf-8")
            marker.symlink_to(outside)
            gate = check_final_review_recorded(run_dir)
            assert not gate.passed
            for msg in gate.issues:
                assert _is_honest(msg), f"symlink msg not honest: {msg!r}"

    @pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="mkfifo unavailable")
    def test_non_regular_file_gate_message_is_honest(self):
        """Case c: not-a-regular-file message must pass _is_honest."""
        from tools.workflow_cli.gates import check_final_review_recorded
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run"
            exec_dir = run_dir / "execution"
            exec_dir.mkdir(parents=True)
            os.mkfifo(exec_dir / "final-review.md")
            gate = check_final_review_recorded(run_dir)
            assert not gate.passed
            for msg in gate.issues:
                assert _is_honest(msg), f"non-regular msg not honest: {msg!r}"

    def test_archive_success_output_is_honest(self, capsys):
        """Archive success payload must be honest (no affirmative correctness wording)."""
        from tools.workflow_cli.state import RunStateManager, create_run_record
        from tools.workflow_cli.models import RunStatus, Stage, WorkId
        from tools.workflow_cli.artifact import write_artifact
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            wid = WorkId("WF-20260101-exec")
            run_dir = base / ".req-to-plan" / "WF-20260101-exec"
            run_dir.mkdir(parents=True)
            rec = create_run_record(wid)
            rec.status = RunStatus.EXECUTING
            rec.current_stage = Stage.CLOSED
            RunStateManager(run_dir).save(rec)
            plan = (
                "# Plan\n\n## Tasks\n"
                "### PLAN-TASK-001: first task\nFiles:\n- a.py\n"
            )
            write_artifact(run_dir, Stage.PLAN, plan, version=1, status="approved")
            exec_dir = run_dir / "execution"
            exec_dir.mkdir(parents=True, exist_ok=True)
            (exec_dir / "progress.md").write_text(
                "# Execution Progress\n\nwork_id: WF-20260101-exec\n\n"
                "- [x] PLAN-TASK-001 first task\n",
                encoding="utf-8",
            )
            _seed_approved_final_review(run_dir)
            with pytest.raises(SystemExit):
                main(["--base-path", str(base), "run-archive", "--work-id", "WF-20260101-exec"])
            out = capsys.readouterr().out
            assert _is_honest(out), f"archive success output not honest: {out!r}"


# ---------------------------------------------------------------------------
# TestPlanTaskBrief — SPEC-CLI-001
# ---------------------------------------------------------------------------


class TestPlanTaskBrief:
    """SPEC-CLI-001: plan-task-brief writes a task-scoped brief to logs/."""

    _MULTI_TASK_PLAN = (
        "# Plan\n\n"
        "## Overview\nSome overview text.\n\n"
        "### PLAN-TASK-001: first task\n"
        "Do thing A.\n"
        "Files:\n- a.py\n\n"
        "### PLAN-TASK-002: second task\n"
        "Do thing B.\n"
        "Files:\n- b.py\n\n"
        "### PLAN-TASK-003: third task\n"
        "Do thing C.\n"
    )

    def _executing_run_with_plan(self, base, wid_str, plan_body):
        from tools.workflow_cli.state import RunStateManager, create_run_record
        from tools.workflow_cli.artifact import write_artifact
        from tools.workflow_cli.models import RunStatus, Stage, WorkId
        wid = WorkId(wid_str)
        run_dir = base / ".req-to-plan" / wid_str
        run_dir.mkdir(parents=True)
        rec = create_run_record(wid)
        rec.status = RunStatus.EXECUTING
        rec.current_stage = Stage.CLOSED
        write_artifact(run_dir, Stage.PLAN, plan_body, version=1, status="approved")
        RunStateManager(run_dir).save(rec)
        return run_dir

    def test_plan_task_brief_writes_task_body_and_returns_success(self, capsys):
        """Happy path: task 2 brief written; payload carries work_id, task_id, brief_path."""
        from tools.workflow_cli.markdown import (
            heading_bounded_bodies,
            PLAN_TASK_ANCHOR_RE,
            plan_task_anchors,
            strip_readonly_sections,
        )
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            wid = "WF-20260626-brief"
            run_dir = self._executing_run_with_plan(base, wid, self._MULTI_TASK_PLAN)
            with pytest.raises(SystemExit) as exc:
                main(["--base-path", str(base), "plan-task-brief", "--work-id", wid, "--task", "2"])
            assert exc.value.code == 0
            brief_path = run_dir / "logs" / "task-2-brief.md"
            assert brief_path.exists(), "brief file must be written"
            actual_body = brief_path.read_text(encoding="utf-8")
            # Byte-identical to heading_bounded_bodies gate for task 2
            stripped = strip_readonly_sections(self._MULTI_TASK_PLAN)
            bodies = list(heading_bounded_bodies(stripped, PLAN_TASK_ANCHOR_RE.match))
            assert actual_body == bodies[1], "body must be byte-identical to heading_bounded_bodies slice"
            # Verify success payload
            out = capsys.readouterr().out
            assert wid in out
            assert "PLAN-TASK-002" in out
            assert ".req-to-plan" in out
            assert "task-2-brief.md" in out

    def test_plan_task_brief_non_executing_run_exits_conflict(self):
        """Non-EXECUTING run → EXIT_CONFLICT and no file written."""
        from tools.workflow_cli.state import RunStateManager, create_run_record
        from tools.workflow_cli.artifact import write_artifact
        from tools.workflow_cli.models import RunStatus, Stage, WorkId
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            wid = "WF-20260626-closed"
            run_dir = base / ".req-to-plan" / wid
            run_dir.mkdir(parents=True)
            rec = create_run_record(WorkId(wid))
            rec.status = RunStatus.CLOSED_AT_PLAN_CHECKPOINT
            rec.current_stage = Stage.CLOSED
            write_artifact(run_dir, Stage.PLAN, self._MULTI_TASK_PLAN, version=1, status="approved")
            RunStateManager(run_dir).save(rec)
            with pytest.raises(SystemExit) as exc:
                main(["--base-path", str(base), "plan-task-brief", "--work-id", wid, "--task", "1"])
            assert exc.value.code == 6  # EXIT_CONFLICT
            assert not (run_dir / "logs" / "task-1-brief.md").exists()

    def test_plan_task_brief_symlinked_logs_dir_exits_conflict(self):
        """Symlinked logs/ → EXIT_CONFLICT; no write-through the link."""
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            wid = "WF-20260626-symlog"
            run_dir = self._executing_run_with_plan(base, wid, self._MULTI_TASK_PLAN)
            outside = base / "outside-logs"
            outside.mkdir()
            (run_dir / "logs").symlink_to(outside, target_is_directory=True)
            with pytest.raises(SystemExit) as exc:
                main(["--base-path", str(base), "plan-task-brief", "--work-id", wid, "--task", "1"])
            assert exc.value.code == 6  # EXIT_CONFLICT
            # Must not write through the symlink
            assert not (outside / "task-1-brief.md").exists()

    def test_plan_task_brief_symlinked_brief_target_exits_conflict(self):
        """Pre-existing symlinked logs/task-N-brief.md → EXIT_CONFLICT; no write-through."""
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            wid = "WF-20260626-symbrief"
            run_dir = self._executing_run_with_plan(base, wid, self._MULTI_TASK_PLAN)
            logs_dir = run_dir / "logs"
            logs_dir.mkdir(parents=True)
            outside = base / "outside-brief.md"
            outside.write_text("old content", encoding="utf-8")
            (logs_dir / "task-1-brief.md").symlink_to(outside)
            with pytest.raises(SystemExit) as exc:
                main(["--base-path", str(base), "plan-task-brief", "--work-id", wid, "--task", "1"])
            assert exc.value.code == 6  # EXIT_CONFLICT
            assert outside.read_text(encoding="utf-8") == "old content"  # not overwritten

    def test_plan_task_brief_out_of_range_task_exits_not_found(self):
        """--task beyond PLAN task count → EXIT_NOT_FOUND."""
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            wid = "WF-20260626-oob"
            self._executing_run_with_plan(base, wid, self._MULTI_TASK_PLAN)
            with pytest.raises(SystemExit) as exc:
                main(["--base-path", str(base), "plan-task-brief", "--work-id", wid, "--task", "99"])
            assert exc.value.code == 7  # EXIT_NOT_FOUND

    def test_plan_task_brief_non_positive_task_exits_cli_err(self):
        """--task 0 → EXIT_CLI_ERR (argparse type rejection)."""
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            wid = "WF-20260626-zero"
            self._executing_run_with_plan(base, wid, self._MULTI_TASK_PLAN)
            with pytest.raises(SystemExit) as exc:
                main(["--base-path", str(base), "plan-task-brief", "--work-id", wid, "--task", "0"])
            assert exc.value.code == 2  # EXIT_CLI_ERR

    def test_plan_task_brief_non_integer_task_exits_cli_err(self):
        """--task abc → EXIT_CLI_ERR (argparse ValueError branch)."""
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            wid = "WF-20260626-abc"
            self._executing_run_with_plan(base, wid, self._MULTI_TASK_PLAN)
            with pytest.raises(SystemExit) as exc:
                main(["--base-path", str(base), "plan-task-brief", "--work-id", wid, "--task", "abc"])
            assert exc.value.code == 2  # EXIT_CLI_ERR

    def test_plan_task_brief_zero_padded_anchor_resolved_by_task_number(self):
        """### PLAN-TASK-002 (zero-padded) resolved by --task 2; payload task_id = 'PLAN-TASK-002'."""
        plan = (
            "# Plan\n\n"
            "### PLAN-TASK-001: first\nBody 1.\n\n"
            "### PLAN-TASK-002: padded second\nBody 2.\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            wid = "WF-20260626-padded"
            run_dir = self._executing_run_with_plan(base, wid, plan)
            with pytest.raises(SystemExit) as exc:
                main(["--base-path", str(base), "plan-task-brief", "--work-id", wid, "--task", "2"])
            assert exc.value.code == 0
            brief_path = run_dir / "logs" / "task-2-brief.md"
            assert brief_path.exists()
            body = brief_path.read_text(encoding="utf-8")
            assert "PLAN-TASK-002" in body

    def test_plan_task_brief_missing_plan_exits_not_found(self):
        """EXECUTING run without a PLAN artifact → EXIT_NOT_FOUND, no brief written."""
        from tools.workflow_cli.state import RunStateManager, create_run_record
        from tools.workflow_cli.models import RunStatus, Stage, WorkId
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            wid = "WF-20260626-noplan"
            run_dir = base / ".req-to-plan" / wid
            run_dir.mkdir(parents=True)
            rec = create_run_record(WorkId(wid))
            rec.status = RunStatus.EXECUTING
            rec.current_stage = Stage.CLOSED
            RunStateManager(run_dir).save(rec)  # deliberately no PLAN artifact
            with pytest.raises(SystemExit) as exc:
                main(["--base-path", str(base), "plan-task-brief", "--work-id", wid, "--task", "1"])
            assert exc.value.code == 7  # EXIT_NOT_FOUND
            assert not (run_dir / "logs" / "task-1-brief.md").exists()

    def test_plan_task_brief_unknown_work_id_exits_not_found(self):
        """Unknown work-id (no run dir) → EXIT_NOT_FOUND."""
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            with pytest.raises(SystemExit) as exc:
                main([
                    "--base-path", str(base),
                    "plan-task-brief", "--work-id", "WF-20260626-nope", "--task", "1",
                ])
            assert exc.value.code == 7  # EXIT_NOT_FOUND

    def test_plan_task_brief_excludes_read_only_section_task(self):
        """A PLAN-TASK nested in a read-only section is stripped: not selectable,
        and a real task's brief carries no read-only content."""
        plan = (
            "# Plan\n\n"
            "## Project Context (read-only)\n"
            "### PLAN-TASK-099: phantom inside read-only\n"
            "Should be stripped.\n"
            "<!-- /r2p-read-only -->\n\n"
            "### PLAN-TASK-001: real first\nBody 1.\n\n"
            "### PLAN-TASK-002: real second\nBody 2.\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            wid = "WF-20260626-readonly"
            run_dir = self._executing_run_with_plan(base, wid, plan)
            # Phantom task inside the read-only section is excluded.
            with pytest.raises(SystemExit) as exc:
                main(["--base-path", str(base), "plan-task-brief", "--work-id", wid, "--task", "99"])
            assert exc.value.code == 7  # EXIT_NOT_FOUND
            assert not (run_dir / "logs" / "task-99-brief.md").exists()
            # The real task still extracts; its brief carries no read-only content.
            with pytest.raises(SystemExit) as exc2:
                main(["--base-path", str(base), "plan-task-brief", "--work-id", wid, "--task", "1"])
            assert exc2.value.code == 0
            body = (run_dir / "logs" / "task-1-brief.md").read_text(encoding="utf-8")
            assert "PLAN-TASK-001" in body
            assert "read-only" not in body
            assert "PLAN-TASK-099" not in body


# ---------------------------------------------------------------------------
# TestTaskBriefShortcut — SPEC-SURFACE-001 (PLAN-TASK-003)
# ---------------------------------------------------------------------------


class TestTaskBriefShortcut:
    """SPEC-SURFACE-001: task-brief shortcut is surface-equivalent to plan-task-brief CLI."""

    _MULTI_TASK_PLAN = (
        "# Plan\n\n"
        "## Overview\nSome overview text.\n\n"
        "### PLAN-TASK-001: first task\n"
        "Do thing A.\n"
        "Files:\n- a.py\n\n"
        "### PLAN-TASK-002: second task\n"
        "Do thing B.\n"
        "Files:\n- b.py\n\n"
        "### PLAN-TASK-003: third task\n"
        "Do thing C.\n"
    )

    def _executing_run_with_plan(self, base, wid_str, plan_body):
        """Seed an EXECUTING run with an approved PLAN artifact (mirrors TestPlanTaskBrief)."""
        from tools.workflow_cli.state import RunStateManager, create_run_record
        from tools.workflow_cli.artifact import write_artifact
        from tools.workflow_cli.models import RunStatus, Stage, WorkId
        wid = WorkId(wid_str)
        run_dir = base / ".req-to-plan" / wid_str
        run_dir.mkdir(parents=True)
        rec = create_run_record(wid)
        rec.status = RunStatus.EXECUTING
        rec.current_stage = Stage.CLOSED
        write_artifact(run_dir, Stage.PLAN, plan_body, version=1, status="approved")
        RunStateManager(run_dir).save(rec)
        return run_dir

    # ------------------------------------------------------------------
    # Shortcut equivalence tests
    # ------------------------------------------------------------------

    def test_task_brief_shortcut_happy_path_matches_cli_json_and_file(self, monkeypatch):
        """EXECUTING run: shortcut JSON, file bytes, exit code == direct CLI (exit 0)."""
        from tools.workflow_cli.agent_shortcuts import main as shortcuts_main

        monkeypatch.setenv("R2P_JSON", "1")
        with tempfile.TemporaryDirectory() as tmp1, tempfile.TemporaryDirectory() as tmp2:
            base_cli = Path(tmp1)
            base_sc = Path(tmp2)
            wid = "WF-20260626-sc-ok"
            run_dir_cli = self._executing_run_with_plan(base_cli, wid, self._MULTI_TASK_PLAN)
            run_dir_sc = self._executing_run_with_plan(base_sc, wid, self._MULTI_TASK_PLAN)

            # Direct CLI
            out_cli = io.StringIO()
            cli_exit = None
            with contextlib.redirect_stdout(out_cli):
                try:
                    main(["--base-path", str(base_cli), "plan-task-brief",
                          "--work-id", wid, "--task", "2"])
                except SystemExit as exc:
                    cli_exit = exc.code

            # Shortcut
            out_sc = io.StringIO()
            sc_exit = None
            with contextlib.redirect_stdout(out_sc):
                try:
                    shortcuts_main(["task-brief", "--work-id", wid, "--task", "2"],
                                   base_path=base_sc)
                except SystemExit as exc:
                    sc_exit = exc.code

            assert cli_exit == 0, f"CLI exit: {cli_exit}"
            assert sc_exit == 0, f"shortcut exit: {sc_exit}"

            cli_payload = json.loads(out_cli.getvalue().strip())
            sc_payload = json.loads(out_sc.getvalue().strip())

            # work_id and task_id must be identical; brief_path differs only in base dir
            assert cli_payload["work_id"] == sc_payload["work_id"]
            assert cli_payload["task_id"] == sc_payload["task_id"]
            assert "task-2-brief.md" in cli_payload["brief_path"]
            assert "task-2-brief.md" in sc_payload["brief_path"]

            # The brief file bytes must be identical (same PLAN extraction)
            brief_cli = (run_dir_cli / "logs" / "task-2-brief.md").read_bytes()
            brief_sc = (run_dir_sc / "logs" / "task-2-brief.md").read_bytes()
            assert brief_cli == brief_sc

    def test_task_brief_shortcut_uses_active_run_when_work_id_omitted(self, monkeypatch):
        """Selected EXECUTING run: shortcut accepts --task without --work-id."""
        from tools.workflow_cli.agent_shortcuts import main as shortcuts_main, write_active_pointer

        monkeypatch.setenv("R2P_JSON", "1")
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            wid = "WF-20260626-sc-active"
            run_dir = self._executing_run_with_plan(base, wid, self._MULTI_TASK_PLAN)
            write_active_pointer(base, wid, reason="execute_resume")

            out = io.StringIO()
            shortcut_exit = None
            with contextlib.redirect_stdout(out):
                try:
                    shortcuts_main(["task-brief", "--task", "2"], base_path=base)
                except SystemExit as exc:
                    shortcut_exit = exc.code

            assert shortcut_exit == 0, f"shortcut exit: {shortcut_exit}"
            payload = json.loads(out.getvalue().strip())
            assert payload["work_id"] == wid
            assert payload["task_id"] == "PLAN-TASK-002"
            assert (run_dir / "logs" / "task-2-brief.md").exists()

    def test_task_brief_shortcut_conflict_exit_code_propagates(self, monkeypatch):
        """Non-EXECUTING run: shortcut exit code == CLI exit code (EXIT_CONFLICT=6)."""
        from tools.workflow_cli.agent_shortcuts import main as shortcuts_main
        from tools.workflow_cli.state import RunStateManager, create_run_record
        from tools.workflow_cli.artifact import write_artifact

        monkeypatch.setenv("R2P_JSON", "1")

        def _seed_closed(base):
            run_dir = base / ".req-to-plan" / wid
            run_dir.mkdir(parents=True)
            rec = create_run_record(WorkId(wid))
            rec.status = RunStatus.CLOSED_AT_PLAN_CHECKPOINT
            rec.current_stage = Stage.CLOSED
            write_artifact(run_dir, Stage.PLAN, self._MULTI_TASK_PLAN, version=1, status="approved")
            RunStateManager(run_dir).save(rec)

        wid = "WF-20260626-sc-cf"
        with tempfile.TemporaryDirectory() as tmp1, tempfile.TemporaryDirectory() as tmp2:
            base_cli = Path(tmp1)
            base_sc = Path(tmp2)
            _seed_closed(base_cli)
            _seed_closed(base_sc)

            # Direct CLI
            cli_exit = None
            with contextlib.redirect_stdout(io.StringIO()):
                try:
                    main(["--base-path", str(base_cli), "plan-task-brief",
                          "--work-id", wid, "--task", "1"])
                except SystemExit as exc:
                    cli_exit = exc.code

            # Shortcut
            sc_exit = None
            with contextlib.redirect_stdout(io.StringIO()):
                try:
                    shortcuts_main(["task-brief", "--work-id", wid, "--task", "1"],
                                   base_path=base_sc)
                except SystemExit as exc:
                    sc_exit = exc.code

            assert cli_exit == 6, f"CLI exit: {cli_exit}"
            assert sc_exit == cli_exit, f"shortcut exit {sc_exit} != CLI exit {cli_exit}"

    # ------------------------------------------------------------------
    # Wrapper structural test
    # ------------------------------------------------------------------

    def test_r2p_task_brief_wrapper_structural(self):
        """tools/r2p-task-brief exists, is executable, and body delegates to agent_shortcuts task-brief."""
        wrapper = Path(__file__).resolve().parents[1] / "tools" / "r2p-task-brief"
        assert wrapper.exists(), "tools/r2p-task-brief must exist"
        assert os.access(wrapper, os.X_OK), "tools/r2p-task-brief must be executable"
        body = wrapper.read_text(encoding="utf-8")
        assert "agent_shortcuts" in body, "wrapper body must invoke agent_shortcuts"
        assert "task-brief" in body, "wrapper body must delegate to task-brief subcommand"

    # ------------------------------------------------------------------
    # Wrapper end-to-end test
    # ------------------------------------------------------------------

    def test_r2p_task_brief_wrapper_end_to_end(self, monkeypatch, tmp_path):
        """Subprocess wrapper produces identical JSON, file bytes, and exit code as direct CLI."""
        wrapper = Path(__file__).resolve().parents[1] / "tools" / "r2p-task-brief"
        assert wrapper.exists() and os.access(wrapper, os.X_OK)

        wid = "WF-20260626-wpe2e"
        base_sc = tmp_path / "sc_base"
        base_sc.mkdir()
        base_cli = tmp_path / "cli_base"
        base_cli.mkdir()
        run_dir_sc = self._executing_run_with_plan(base_sc, wid, self._MULTI_TASK_PLAN)
        run_dir_cli = self._executing_run_with_plan(base_cli, wid, self._MULTI_TASK_PLAN)

        # Symlink sys.executable as "python3" in a tmp bin dir so the wrapper
        # always finds a dependency-complete interpreter regardless of CI PATH.
        # Also propagate site-packages via PYTHONPATH so yaml is available even
        # when sys.executable is itself a symlink to the base cpython binary
        # (as in a uv-managed venv on local dev) and Python can't locate pyvenv.cfg
        # through the extra symlink indirection.
        import sysconfig
        py_bin = tmp_path / "pybin"
        py_bin.mkdir()
        py3_link = py_bin / "python3"
        py3_link.symlink_to(sys.executable)
        # The symlink resolves to the already-executable interpreter. Do not
        # chmod it: chmod follows symlinks and can mutate/fail on the host Python.
        assert os.access(py3_link, os.X_OK)

        site_pkgs = sysconfig.get_path("purelib")
        base_pp = os.environ.get("PYTHONPATH", "")
        extra_pp = site_pkgs if site_pkgs else ""
        child_pythonpath = (extra_pp + os.pathsep + base_pp).strip(os.pathsep) if extra_pp or base_pp else ""

        child_env: dict[str, str] = {
            **os.environ,
            "PATH": str(py_bin) + os.pathsep + os.environ["PATH"],
            "R2P_JSON": "1",
        }
        if child_pythonpath:
            child_env["PYTHONPATH"] = child_pythonpath

        # Run wrapper; cwd=base_sc so agent_shortcuts uses it as base_path
        result = subprocess.run(
            [str(wrapper), "--work-id", wid, "--task", "2"],
            cwd=str(base_sc),
            env=child_env,
            text=True,
            capture_output=True,
        )

        # Direct CLI for comparison
        monkeypatch.setenv("R2P_JSON", "1")
        out_cli = io.StringIO()
        cli_exit = None
        with contextlib.redirect_stdout(out_cli):
            try:
                main(["--base-path", str(base_cli), "plan-task-brief",
                      "--work-id", wid, "--task", "2"])
            except SystemExit as exc:
                cli_exit = exc.code

        assert cli_exit == 0, f"CLI exit: {cli_exit}"
        assert result.returncode == 0, (
            f"wrapper returncode={result.returncode}\n"
            f"stdout: {result.stdout!r}\nstderr: {result.stderr!r}"
        )

        cli_payload = json.loads(out_cli.getvalue().strip())
        wrapper_payload = json.loads(result.stdout.strip())

        assert cli_payload["work_id"] == wrapper_payload["work_id"]
        assert cli_payload["task_id"] == wrapper_payload["task_id"]
        assert "task-2-brief.md" in cli_payload["brief_path"]
        assert "task-2-brief.md" in wrapper_payload["brief_path"]

        brief_cli = (run_dir_cli / "logs" / "task-2-brief.md").read_bytes()
        brief_sc = (run_dir_sc / "logs" / "task-2-brief.md").read_bytes()
        assert brief_cli == brief_sc

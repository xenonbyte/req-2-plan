"""
Tests for tools/workflow_cli/cli.py — CLI command router.
"""
from __future__ import annotations

import json
import tempfile
import os
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


def test_gap_open_invalidates_reopened_copied_artifacts_without_active_records():
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
        assert reopened.active_artifacts == []
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
                return "# plan v2\n\n## Tasks\n\nProse-only plan.\n"
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

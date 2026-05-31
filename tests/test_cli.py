"""
Tests for tools/workflow_cli/cli.py — CLI command router.
"""
from __future__ import annotations

import tempfile
import os
from pathlib import Path

import pytest

from tools.workflow_cli.cli import main
from tools.workflow_cli.models import (
    CheckpointRecord,
    OpenRoute,
    RunStatus,
    Stage,
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
            save_record(tmp, record)

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

    def test_version(self, capsys):
        from tools.workflow_cli.install_cli import main as install_main
        from tools.workflow_cli.version import R2P_VERSION
        install_main(["version"])
        out = capsys.readouterr().out
        assert R2P_VERSION in out

    def test_installed_stub(self, capsys):
        from tools.workflow_cli.install_cli import main as install_main
        install_main(["installed"])
        out = capsys.readouterr().out
        assert len(out.strip()) > 0

    def test_doctor_stub(self, capsys):
        from tools.workflow_cli.install_cli import main as install_main
        install_main(["doctor"])
        out = capsys.readouterr().out
        assert len(out.strip()) > 0


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
            (run_dir / "05-design.md").write_text("---\nr2p_version: 1\n---\nbody", encoding="utf-8")
            invoke(["gate-quality", "--work-id", work_id, "--stage", "design"], base_path=tmp)
            record = load_record(tmp, work_id)
            assert record.status == RunStatus.READY_FOR_CHECKPOINT_REVIEW


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
            (run_dir / "05-design.md").write_text("---\nr2p_version: 1\n---\nbody", encoding="utf-8")
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

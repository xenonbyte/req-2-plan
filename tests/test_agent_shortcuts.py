"""
Tests for tools/workflow_cli/agent_shortcuts.py
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from tools.workflow_cli.models import RunStatus
from tools.workflow_cli.agent_shortcuts import (
    generate_work_id,
    is_terminal,
    read_active_pointer,
    scan_open_runs,
    write_active_pointer,
    main,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_run(tmp: Path, work_id: str, status: RunStatus = RunStatus.ACTIVE_STAGE_DRAFT) -> Path:
    """Create a minimal run.md for the given work_id and status."""
    run_dir = tmp / ".req-to-plan" / work_id
    run_dir.mkdir(parents=True, exist_ok=True)
    run_md = run_dir / "run.md"
    run_md.write_text(
        f"# Workflow Run: {work_id}\n\n## Status\n{status.value}\n\n## Current Stage\nraw_requirement\n\n## r2p Version\nv1\n",
        encoding="utf-8",
    )
    return run_md


def _invoke(args: list[str], base_path: Path, expect_exit: int = 0, capsys=None):
    with pytest.raises(SystemExit) as exc:
        main(args, base_path=base_path)
    code = exc.value.code
    assert code == expect_exit, f"Expected exit {expect_exit}, got {code}"
    if capsys:
        return capsys.readouterr()
    return None


# ---------------------------------------------------------------------------
# TestReadWriteActivePointer
# ---------------------------------------------------------------------------


class TestReadWriteActivePointer:
    def test_read_returns_none_when_file_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = read_active_pointer(Path(tmp))
            assert result is None

    def test_read_parses_selected_work_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            write_active_pointer(base, "WF-20260527-login-rate-limit")
            data = read_active_pointer(base)
            assert data is not None
            assert data["selected_work_id"] == "WF-20260527-login-rate-limit"

    def test_read_parses_selected_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            write_active_pointer(base, "WF-20260527-login-rate-limit")
            data = read_active_pointer(base)
            assert "selected_run" in data
            assert "WF-20260527-login-rate-limit" in data["selected_run"]

    def test_write_creates_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            write_active_pointer(base, "WF-20260527-test-work")
            pointer_path = base / ".req-to-plan" / ".workflow-active"
            assert pointer_path.exists()

    def test_write_sets_selected_work_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            write_active_pointer(base, "WF-20260527-my-feature")
            data = read_active_pointer(base)
            assert data["selected_work_id"] == "WF-20260527-my-feature"

    def test_write_default_reason_is_workflow_start(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            write_active_pointer(base, "WF-20260527-default-reason")
            data = read_active_pointer(base)
            assert data["reason"] == "workflow_start"

    def test_write_updated_at_is_present(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            write_active_pointer(base, "WF-20260527-timestamp-check")
            data = read_active_pointer(base)
            assert "updated_at" in data
            assert data["updated_at"]


# ---------------------------------------------------------------------------
# TestScanOpenRuns
# ---------------------------------------------------------------------------


class TestScanOpenRuns:
    def test_returns_empty_list_when_no_r2p_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = scan_open_runs(Path(tmp))
            assert result == []

    def test_returns_empty_list_when_no_runs(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            (base / ".req-to-plan").mkdir()
            result = scan_open_runs(base)
            assert result == []

    def test_returns_work_id_for_open_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            _make_run(base, "WF-20260527-open-run", RunStatus.ACTIVE_STAGE_DRAFT)
            result = scan_open_runs(base)
            assert "WF-20260527-open-run" in result

    def test_excludes_terminal_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            _make_run(base, "WF-20260527-closed-run", RunStatus.CLOSED_AT_PLAN_CHECKPOINT)
            result = scan_open_runs(base)
            assert "WF-20260527-closed-run" not in result


# ---------------------------------------------------------------------------
# TestGenerateWorkId
# ---------------------------------------------------------------------------


class TestGenerateWorkId:
    def test_uses_wf_yyyymmdd_prefix(self):
        wid = generate_work_id("add rate limiting", today="20260527")
        assert wid.startswith("WF-20260527-")

    def test_injects_today_parameter(self):
        wid = generate_work_id("some requirement", today="20991231")
        assert wid.startswith("WF-20991231-")

    def test_strips_non_alphanumeric(self):
        wid = generate_work_id("add rate-limiting (now!)", today="20260527")
        assert "(" not in wid
        assert "!" not in wid

    def test_result_length_lte_48(self):
        req = "implement a very long requirement that exceeds the maximum allowed length for slugs"
        wid = generate_work_id(req, today="20260527")
        assert len(wid) <= 48

    def test_handles_empty_requirement(self):
        wid = generate_work_id("", today="20260527")
        assert wid.startswith("WF-20260527-")
        assert len(wid) <= 48

    def test_deduplicates_if_path_exists(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            req = "add login feature"
            wid1 = generate_work_id(req, base_path=base, today="20260527")
            _make_run(base, wid1)
            wid2 = generate_work_id(req, base_path=base, today="20260527")
            assert wid2 != wid1
            assert wid2.endswith("-2")


# ---------------------------------------------------------------------------
# TestIsTerminal
# ---------------------------------------------------------------------------


class TestIsTerminal:
    def test_returns_true_for_closed_at_plan_checkpoint(self):
        assert is_terminal(RunStatus.CLOSED_AT_PLAN_CHECKPOINT) is True

    def test_returns_false_for_active_stage_draft(self):
        assert is_terminal(RunStatus.ACTIVE_STAGE_DRAFT) is False

    def test_returns_false_for_not_started(self):
        assert is_terminal(RunStatus.NOT_STARTED) is False


# ---------------------------------------------------------------------------
# TestCmdSwitch
# ---------------------------------------------------------------------------


class TestCmdSwitch:
    def test_writes_active_pointer_when_run_exists(self, capsys):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            _make_run(base, "WF-20260527-switch-target")
            _invoke(["switch", "--work-id", "WF-20260527-switch-target"], base)
            data = read_active_pointer(base)
            assert data["selected_work_id"] == "WF-20260527-switch-target"

    def test_exits_nonzero_when_run_not_found(self, capsys):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            _invoke(["switch", "--work-id", "WF-20260527-nonexistent"], base, expect_exit=7)


# ---------------------------------------------------------------------------
# TestCmdStart
# ---------------------------------------------------------------------------


class TestCmdStart:
    def test_creates_run_and_writes_pointer(self, capsys):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            with patch("tools.workflow_cli.agent_shortcuts._run_cli", return_value=0):
                with patch(
                    "tools.workflow_cli.agent_shortcuts.generate_work_id",
                    return_value="WF-20260527-add-rate-limiting",
                ):
                    _invoke(["start", "add rate limiting"], base)
            data = read_active_pointer(base)
            assert data["selected_work_id"] == "WF-20260527-add-rate-limiting"

    def test_blocks_when_active_run_exists_no_separate(self, capsys):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            _make_run(base, "WF-20260527-active-run")
            write_active_pointer(base, "WF-20260527-active-run")
            _invoke(["start", "another requirement"], base, expect_exit=1)
            out = capsys.readouterr().out
            assert "blocked" in out

    def test_allows_start_with_separate_when_active_run_exists(self, capsys):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            _make_run(base, "WF-20260527-existing-run")
            write_active_pointer(base, "WF-20260527-existing-run")
            with patch("tools.workflow_cli.agent_shortcuts._run_cli", return_value=0):
                with patch(
                    "tools.workflow_cli.agent_shortcuts.generate_work_id",
                    return_value="WF-20260527-new-separate",
                ):
                    _invoke(["start", "--separate", "new requirement"], base)

    def test_blocks_when_single_unselected_open_run_exists(self, capsys):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            _make_run(base, "WF-20260527-unselected-run")
            _invoke(["start", "another req"], base, expect_exit=1)
            out = capsys.readouterr().out
            assert "blocked" in out

    def test_blocks_when_multiple_open_runs_exist(self, capsys):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            _make_run(base, "WF-20260527-run-one")
            _make_run(base, "WF-20260527-run-two")
            _invoke(["start", "yet another"], base, expect_exit=1)
            out = capsys.readouterr().out
            assert "blocked" in out


# ---------------------------------------------------------------------------
# TestCmdContinue
# ---------------------------------------------------------------------------


class TestCmdContinue:
    def test_exits_with_error_when_no_pointer(self, capsys):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            _invoke(["continue"], base, expect_exit=1)
            out = capsys.readouterr().out
            assert "no_selected_run" in out

    def test_stops_at_tier_not_locked_for_open_run(self, capsys):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            _make_run(base, "WF-20260527-continue-target")
            write_active_pointer(base, "WF-20260527-continue-target")
            _invoke(["continue"], base, expect_exit=0)
            out = capsys.readouterr().out
            assert "tier_not_locked" in out


# ---------------------------------------------------------------------------
# TestCmdStatus
# ---------------------------------------------------------------------------


class TestCmdStatus:
    def test_prints_no_selected_run_when_no_pointer(self, capsys):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            _invoke(["status"], base, expect_exit=0)
            out = capsys.readouterr().out
            assert "no_selected_run" in out

    def test_calls_status_run_when_pointer_exists(self, capsys):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            _make_run(base, "WF-20260527-status-target")
            write_active_pointer(base, "WF-20260527-status-target")
            with patch("tools.workflow_cli.agent_shortcuts._run_cli", return_value=0) as mock_cli:
                _invoke(["status"], base)
            called_args = mock_cli.call_args[0][0]
            assert "status-run" in called_args


# ---------------------------------------------------------------------------
# TestCmdReopen
# ---------------------------------------------------------------------------


class TestCmdReopen:
    def test_delegates_to_run_reopen(self, capsys):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            with patch("tools.workflow_cli.agent_shortcuts._run_cli", return_value=0) as mock_cli:
                _invoke(
                    [
                        "reopen",
                        "--from", "WF-20260527-source",
                        "--stage", "plan",
                        "--reason", "fix spec gap",
                    ],
                    base,
                )
            called_args = mock_cli.call_args[0][0]
            assert "run-reopen" in called_args
            assert "--from" in called_args
            assert "WF-20260527-source" in called_args


# ---------------------------------------------------------------------------
# TestContinueDriver
# ---------------------------------------------------------------------------


class TestContinueDriver:
    def test_continue_stops_at_unready_artifact(self, capsys):
        import tempfile
        from pathlib import Path
        from tools.workflow_cli import agent_shortcuts as A
        from tools.workflow_cli.models import TierBase, TierEstimate
        from tools.workflow_cli.state import RunStateManager
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            with pytest.raises(SystemExit):
                A.main(["start", "Add rate limiting"], base_path=base)
            pointer = A.read_active_pointer(base)
            manager = RunStateManager(base / ".req-to-plan" / pointer["selected_work_id"])
            record = manager.load()
            record.tier_locked = TierEstimate(TierBase.LIGHT)
            manager.save(record)
            # after start: ACTIVE_STAGE_DRAFT, raw_requirement artifact is draft (not ready)
            with pytest.raises(SystemExit):
                A.main(["continue"], base_path=base)
            out = capsys.readouterr().out
            assert "stage-ready" in out
            assert f"stage-ready --work-id {pointer['selected_work_id']} --stage raw_requirement" in out

    def test_continue_new_stage_without_artifact_asks_for_production(self, capsys):
        import tempfile
        from pathlib import Path
        from tools.workflow_cli import agent_shortcuts as A
        from tools.workflow_cli.models import RunStatus, Stage, TierBase, TierEstimate
        from tools.workflow_cli.state import RunStateManager
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            with pytest.raises(SystemExit):
                A.main(["start", "Add rate limiting"], base_path=base)
            pointer = A.read_active_pointer(base)
            manager = RunStateManager(base / ".req-to-plan" / pointer["selected_work_id"])
            record = manager.load()
            record.tier_locked = TierEstimate(TierBase.LIGHT)
            record.current_stage = Stage.REQUIREMENT_BRIEF
            record.status = RunStatus.ACTIVE_STAGE_DRAFT
            record.active_artifacts = []
            manager.save(record)
            with pytest.raises(SystemExit):
                A.main(["continue"], base_path=base)
            out = capsys.readouterr().out
            assert "needs_content" in out
            assert "produce requirement_brief content" in out

    def test_continue_surfaces_repair_after_failed_quality_gate(self, capsys):
        import tempfile
        from pathlib import Path
        from tools.workflow_cli import agent_shortcuts as A
        from tools.workflow_cli.cli import main as cli_main
        from tools.workflow_cli.models import RunStatus
        from tools.workflow_cli.state import RunStateManager
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            with pytest.raises(SystemExit):
                A.main(["start", "Add rate limiting"], base_path=base)
            work_id = A.read_active_pointer(base)["selected_work_id"]
            # Lock tier, then make the artifact ready with content that fails the
            # quality gate (an unclosed upstream reference).
            with pytest.raises(SystemExit):
                cli_main(["--base-path", str(base), "tier-lock", "--work-id", work_id,
                          "--base", "light", "--confirm"])
            with pytest.raises(SystemExit):
                cli_main(["--base-path", str(base), "stage-update", "--work-id", work_id,
                          "--stage", "raw_requirement",
                          "--content", "Depends on REQ-AUTH-1 with no closure tag"])
            with pytest.raises(SystemExit):
                cli_main(["--base-path", str(base), "stage-ready", "--work-id", work_id,
                          "--stage", "raw_requirement"])
            # A single continue must auto-run gate-quality (which fails) AND surface the
            # repair stop in the same call — not exit at the raw gate output.
            with pytest.raises(SystemExit) as exc:
                A.main(["continue"], base_path=base)
            out = capsys.readouterr().out
            assert "needs_repair" in out
            assert f"stage-update --work-id {work_id} --stage raw_requirement" in out
            assert exc.value.code == 0
            record = RunStateManager(base / ".req-to-plan" / work_id).load()
            assert record.status == RunStatus.QUALITY_GATE_FAILED

    def test_continue_tier_not_locked_prints_executable_next(self, capsys):
        import tempfile
        from pathlib import Path
        from tools.workflow_cli import agent_shortcuts as A
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            with pytest.raises(SystemExit):
                A.main(["start", "Add rate limiting"], base_path=base)
            with pytest.raises(SystemExit):
                A.main(["continue"], base_path=base)
            out = capsys.readouterr().out
            assert "tier_not_locked" in out
            # The suggested next step must be the real workflow command, not the
            # lifecycle `r2p` binary (which has no tier-lock subcommand).
            assert "r2p tier-lock" not in out
            assert "tier-lock --work-id" in out

    def test_continue_checkpoint_review_prints_executable_next(self, capsys):
        import tempfile
        from pathlib import Path
        from tools.workflow_cli import agent_shortcuts as A
        from tools.workflow_cli.models import RunStatus
        from tools.workflow_cli.state import RunStateManager
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            with pytest.raises(SystemExit):
                A.main(["start", "Add rate limiting"], base_path=base)
            work_id = A.read_active_pointer(base)["selected_work_id"]
            manager = RunStateManager(base / ".req-to-plan" / work_id)
            record = manager.load()
            record.status = RunStatus.CHECKPOINT_REVIEW
            manager.save(record)

            with pytest.raises(SystemExit):
                A.main(["continue"], base_path=base)

            out = capsys.readouterr().out
            assert "needs_human_approval" in out
            assert (
                f"checkpoint-decide --work-id {work_id} --stage raw_requirement "
                "--decision approved --confirm"
            ) in out

    def test_continue_next_stage_entry_failure_prints_executable_retry(self, capsys):
        import tempfile
        from pathlib import Path
        from tools.workflow_cli import agent_shortcuts as A
        from tools.workflow_cli.models import RunStatus, Stage
        from tools.workflow_cli.state import RunStateManager
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            with pytest.raises(SystemExit):
                A.main(["start", "Add rate limiting"], base_path=base)
            work_id = A.read_active_pointer(base)["selected_work_id"]
            manager = RunStateManager(base / ".req-to-plan" / work_id)
            record = manager.load()
            record.status = RunStatus.NEXT_STAGE
            record.current_stage = Stage.REQUIREMENT_BRIEF
            manager.save(record)

            with patch("tools.workflow_cli.agent_shortcuts._run_cli", return_value=2):
                with pytest.raises(SystemExit) as exc:
                    A.main(["continue"], base_path=base)

            out = capsys.readouterr().out
            assert exc.value.code == 2
            assert "entry_gate_failed" in out
            assert f"gate-entry --work-id {work_id} --stage requirement_brief" in out

    def test_continue_entry_gate_failed_prints_executable_retry(self, capsys):
        import tempfile
        from pathlib import Path
        from tools.workflow_cli import agent_shortcuts as A
        from tools.workflow_cli.models import RunStatus, Stage
        from tools.workflow_cli.state import RunStateManager
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            with pytest.raises(SystemExit):
                A.main(["start", "Add rate limiting"], base_path=base)
            work_id = A.read_active_pointer(base)["selected_work_id"]
            manager = RunStateManager(base / ".req-to-plan" / work_id)
            record = manager.load()
            record.status = RunStatus.ENTRY_GATE_FAILED
            record.current_stage = Stage.REQUIREMENT_BRIEF
            manager.save(record)

            with pytest.raises(SystemExit):
                A.main(["continue"], base_path=base)

            out = capsys.readouterr().out
            assert "entry_gate_failed" in out
            assert f"gate-entry --work-id {work_id} --stage requirement_brief" in out

"""
Tests for tools/workflow_cli/agent_shortcuts.py
"""
from __future__ import annotations

import os
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from tools.workflow_cli.models import RunStatus
from tools.workflow_cli.version import R2P_VERSION
from tools.workflow_cli.agent_shortcuts import (
    generate_work_id,
    is_terminal,
    read_active_pointer,
    scan_open_runs,
    write_active_pointer,
    main,
)
from tools.workflow_cli.cli import main as cli_main
from tools.workflow_cli.state import RunStateManager

# Schema-valid DESIGN LIGHT content (required for gate-quality to pass at LIGHT tier).
_DESIGN_LIGHT_CONTENT = (
    "# design v2\n\n## Design Summary\ncontent\n"
    "## Chosen Design\ncontent\n### DES-ARCH-001 Selected design\ncontent\n"
    "## SPEC Handoff\ncontent\n"
)


def _expected_workflow_cli_prefix(base: Path) -> str:
    from tools.workflow_cli import agent_shortcuts as A

    return (
        f"env PYTHONPATH={shlex.quote(str(A._repo_root()))} "
        f"{shlex.quote(sys.executable)} -m tools.workflow_cli --base-path {shlex.quote(str(base))}"
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
        f"# Workflow Run: {work_id}\n\n## Status\n{status.value}\n\n## Current Stage\nraw_requirement\n\n## r2p Version\n{R2P_VERSION}\n",
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

    def test_rejects_path_traversal_work_id_before_writing_pointer(self, capsys):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            outside = base / "outside"
            _make_run(outside, "WF-20260527-outside")
            (base / ".req-to-plan").mkdir()

            _invoke(["switch", "--work-id", "../outside/.req-to-plan/WF-20260527-outside"], base, expect_exit=2)

            assert read_active_pointer(base) is None
            assert "invalid_work_id" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# TestCmdStart
# ---------------------------------------------------------------------------


class TestCmdStart:
    def test_requires_requirement_argument(self, capsys):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            _invoke(["start"], base, expect_exit=2)

    def test_rejects_blank_requirement_argument(self, capsys):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            _invoke(["start", "   "], base, expect_exit=2)

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
# TestCmdStartFile — `r2p-start --file <path>`
# ---------------------------------------------------------------------------


class TestCmdStartFile:
    def test_start_with_file_reads_content(self, capsys):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            req_file = base / "req.md"
            req_file.write_text("Add OAuth login with Google and GitHub", encoding="utf-8")
            with pytest.raises(SystemExit):
                main(["start", "--file", str(req_file)], base_path=base)
            work_id = read_active_pointer(base)["selected_work_id"]
            raw = base / ".req-to-plan" / work_id / "00-raw-requirement.md"
            assert "Add OAuth login with Google and GitHub" in raw.read_text(encoding="utf-8")

    def test_start_with_file_work_id_from_content_not_path(self, capsys):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            req_file = base / "req.md"
            req_file.write_text("Add OAuth login support", encoding="utf-8")
            with pytest.raises(SystemExit):
                main(["start", "--file", str(req_file)], base_path=base)
            work_id = read_active_pointer(base)["selected_work_id"]
            # Slug must derive from file CONTENT (oauth/login), not the filename (req).
            assert "oauth" in work_id.lower()

    def test_start_with_missing_file_blocks(self, capsys):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            _invoke(["start", "--file", str(base / "nope.md")], base, expect_exit=2)
            out = capsys.readouterr().out
            assert "requirement_file_not_found" in out

    def test_start_with_empty_file_blocks(self, capsys):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            f = base / "empty.md"
            f.write_text("  \n", encoding="utf-8")
            _invoke(["start", "--file", str(f)], base, expect_exit=2)
            out = capsys.readouterr().out
            assert "empty_requirement_file" in out

    def test_start_rejects_both_positional_and_file(self, capsys):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            f = base / "req.md"
            f.write_text("content", encoding="utf-8")
            _invoke(["start", "inline req", "--file", str(f)], base, expect_exit=2)
            out = capsys.readouterr().out
            assert "ambiguous_requirement" in out


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

    def test_rejects_invalid_pointer_work_id_before_loading_run(self, capsys):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            outside = base / "outside"
            _make_run(outside, "WF-20260527-outside")
            pointer_path = base / ".req-to-plan" / ".workflow-active"
            pointer_path.parent.mkdir(parents=True)
            pointer_path.write_text(
                "selected_work_id: ../outside/.req-to-plan/WF-20260527-outside\n",
                encoding="utf-8",
            )

            _invoke(["continue"], base, expect_exit=2)

            out = capsys.readouterr().out
            assert "invalid_work_id" in out
            assert "tier_not_locked" not in out


# ---------------------------------------------------------------------------
# TestCmdTierLock
# ---------------------------------------------------------------------------


class TestCmdTierLock:
    def test_tier_lock_delegates_to_workflow_cli(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            _make_run(base, "WF-20260531-tier-lock")
            with patch(
                "tools.workflow_cli.agent_shortcuts._run_cli",
                return_value=0,
            ) as run_cli:
                _invoke(
                    [
                        "tier-lock",
                        "--work-id", "WF-20260531-tier-lock",
                        "--base", "standard",
                        "--confirm",
                    ],
                    base,
                )

            run_cli.assert_called_once_with(
                [
                    "tier-lock",
                    "--work-id", "WF-20260531-tier-lock",
                    "--base", "standard",
                    "--confirm",
                ],
                base,
            )

    def test_tier_lock_rejects_non_active_stage_before_delegating(self, capsys):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            work_id = "WF-20260531-tier-lock"
            _make_run(base, work_id, RunStatus.CHECKPOINT_APPROVED)

            with patch(
                "tools.workflow_cli.agent_shortcuts._run_cli",
                return_value=0,
            ) as run_cli:
                _invoke(
                    [
                        "tier-lock",
                        "--work-id", work_id,
                        "--base", "standard",
                        "--confirm",
                    ],
                    base,
                    expect_exit=6,
                )

            run_cli.assert_not_called()
            out = capsys.readouterr().out
            assert "blocked: tier_lock_not_allowed" in out
            assert "status: checkpoint_approved" in out
            assert "must_be: active_stage_draft" in out


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
    def test_workflow_cli_command_uses_active_python_executable(self):
        from tools.workflow_cli import agent_shortcuts as A

        command = A._workflow_cli_command(
            Path("/tmp/r2p-root"),
            ["stage-ready", "--work-id", "WF-20260527-test", "--stage", "raw_requirement"],
        )

        assert f"{shlex.quote(sys.executable)} -m tools.workflow_cli" in command
        assert "python3 -m tools.workflow_cli" not in command

    def test_workflow_cli_command_uses_patched_active_python_executable(self):
        from tools.workflow_cli import agent_shortcuts as A

        with patch.object(A.sys, "executable", "python"):
            command = A._workflow_cli_command(
                Path("/tmp/r2p-root"),
                ["stage-ready", "--work-id", "WF-20260527-test", "--stage", "raw_requirement"],
            )

        assert "python -m tools.workflow_cli" in command
        assert "python3 -m tools.workflow_cli" not in command

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
            assert _expected_workflow_cli_prefix(base) in out
            assert (
                f"stage-ready --work-id {pointer['selected_work_id']} "
                "--stage raw_requirement"
            ) in out

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
            content_file = base / ".req-to-plan" / pointer["selected_work_id"] / "inputs" / "requirement_brief-content.md"
            assert "needs_content" in out
            assert _expected_workflow_cli_prefix(base) in out
            assert content_file.exists()
            assert str(content_file) in out
            assert (
                f"stage-produce --work-id {pointer['selected_work_id']} "
                "--stage requirement_brief --content-file"
            ) in out

    def test_continue_existing_empty_artifact_asks_for_update(self, capsys):
        import tempfile
        from pathlib import Path
        from tools.workflow_cli import agent_shortcuts as A
        from tools.workflow_cli.cli import main as cli_main
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            with pytest.raises(SystemExit):
                A.main(["start", "Add rate limiting"], base_path=base)
            work_id = A.read_active_pointer(base)["selected_work_id"]
            with pytest.raises(SystemExit):
                cli_main(["--base-path", str(base), "tier-lock", "--work-id", work_id,
                          "--base", "light", "--confirm"])
            empty_content = base / "empty.md"
            empty_content.write_text("", encoding="utf-8")
            with pytest.raises(SystemExit):
                cli_main(["--base-path", str(base), "stage-update", "--work-id", work_id,
                          "--stage", "raw_requirement",
                          "--content-file", str(empty_content)])

            with pytest.raises(SystemExit):
                A.main(["continue"], base_path=base)

            out = capsys.readouterr().out
            content_file = base / ".req-to-plan" / work_id / "inputs" / "raw_requirement-content.md"
            assert "needs_content" in out
            assert str(content_file) in out
            assert (
                f"stage-update --work-id {work_id} --stage raw_requirement "
                "--content-file"
            ) in out
            assert "stage-produce" not in out

    def test_continue_open_owner_route_asks_for_stage_update(self, capsys):
        import tempfile
        from pathlib import Path
        from tests.test_cli import _seed_plan_approved_run
        from tools.workflow_cli import agent_shortcuts as A
        from tools.workflow_cli.cli import main as cli_main

        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            work_id, _ = _seed_plan_approved_run(base)
            A.write_active_pointer(base, work_id)

            with pytest.raises(SystemExit):
                cli_main([
                    "--base-path", str(base),
                    "gap-open",
                    "--work-id", work_id,
                    "--owner-stage", "design",
                    "--required-action", "fixed-window burst flaw",
                ])

            with pytest.raises(SystemExit):
                A.main(["continue"], base_path=base)

            out = capsys.readouterr().out
            content_file = base / ".req-to-plan" / work_id / "inputs" / "design-repair.md"
            assert "needs_repair" in out
            assert str(content_file) in out
            assert (
                f"stage-update --work-id {work_id} --stage design "
                "--content-file"
            ) in out
            assert "stage-ready" not in out

    def test_continue_repaired_owner_draft_asks_for_stage_ready(self, capsys):
        import tempfile
        from pathlib import Path
        from tests.test_cli import _seed_plan_approved_run
        from tools.workflow_cli import agent_shortcuts as A
        from tools.workflow_cli.cli import main as cli_main

        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            work_id, _ = _seed_plan_approved_run(base)
            A.write_active_pointer(base, work_id)

            for cmd in (
                [
                    "--base-path", str(base), "gap-open",
                    "--work-id", work_id,
                    "--owner-stage", "design",
                    "--required-action", "fixed-window burst flaw",
                ],
                [
                    "--base-path", str(base), "stage-update",
                    "--work-id", work_id,
                    "--stage", "design",
                    "--content", _DESIGN_LIGHT_CONTENT,
                ],
            ):
                with pytest.raises(SystemExit) as exc:
                    cli_main(cmd)
                assert exc.value.code == 0

            with pytest.raises(SystemExit):
                A.main(["continue"], base_path=base)

            out = capsys.readouterr().out
            assert "needs_ready" in out
            assert f"stage-ready --work-id {work_id} --stage design" in out
            assert "stage-update" not in out

    def test_continue_owner_gate_passed_asks_for_gap_resolve(self, capsys):
        import tempfile
        from pathlib import Path
        from tests.test_cli import _seed_plan_approved_run
        from tools.workflow_cli import agent_shortcuts as A
        from tools.workflow_cli.cli import main as cli_main

        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            work_id, _ = _seed_plan_approved_run(base)
            A.write_active_pointer(base, work_id)

            for cmd in (
                [
                    "--base-path", str(base), "gap-open",
                    "--work-id", work_id,
                    "--owner-stage", "design",
                    "--required-action", "fixed-window burst flaw",
                ],
                [
                    "--base-path", str(base), "stage-update",
                    "--work-id", work_id,
                    "--stage", "design",
                    "--content", _DESIGN_LIGHT_CONTENT,
                ],
                ["--base-path", str(base), "stage-ready", "--work-id", work_id, "--stage", "design"],
                ["--base-path", str(base), "gate-quality", "--work-id", work_id, "--stage", "design"],
            ):
                with pytest.raises(SystemExit) as exc:
                    cli_main(cmd)
                assert exc.value.code == 0

            with pytest.raises(SystemExit):
                A.main(["continue"], base_path=base)

            out = capsys.readouterr().out
            assert "needs_gap_resolve" in out
            assert f"gap-resolve --work-id {work_id} --route-id R-1" in out
            assert "checkpoint-decide" not in out

    def test_continue_owner_checkpoint_review_asks_for_gap_resolve(self, capsys):
        import tempfile
        from pathlib import Path
        from tests.test_cli import _seed_plan_approved_run
        from tools.workflow_cli import agent_shortcuts as A
        from tools.workflow_cli.cli import main as cli_main

        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            work_id, _ = _seed_plan_approved_run(base)
            A.write_active_pointer(base, work_id)

            for cmd in (
                [
                    "--base-path", str(base), "gap-open",
                    "--work-id", work_id,
                    "--owner-stage", "design",
                    "--required-action", "fixed-window burst flaw",
                ],
                [
                    "--base-path", str(base), "stage-update",
                    "--work-id", work_id,
                    "--stage", "design",
                    "--content", _DESIGN_LIGHT_CONTENT,
                ],
                ["--base-path", str(base), "stage-ready", "--work-id", work_id, "--stage", "design"],
                ["--base-path", str(base), "gate-quality", "--work-id", work_id, "--stage", "design"],
                ["--base-path", str(base), "review-checkpoint", "--work-id", work_id, "--stage", "design"],
            ):
                with pytest.raises(SystemExit) as exc:
                    cli_main(cmd)
                assert exc.value.code == 0

            with pytest.raises(SystemExit):
                A.main(["continue"], base_path=base)

            out = capsys.readouterr().out
            assert "needs_gap_resolve" in out
            assert f"gap-resolve --work-id {work_id} --route-id R-1" in out
            assert "checkpoint-decide" not in out

    def test_continue_downstream_stale_stage_asks_for_stage_update(self, capsys):
        import tempfile
        from pathlib import Path
        from tests.test_cli import _seed_plan_approved_run
        from tools.workflow_cli import agent_shortcuts as A
        from tools.workflow_cli.cli import main as cli_main

        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            work_id, _ = _seed_plan_approved_run(base)
            A.write_active_pointer(base, work_id)

            for cmd in (
                [
                    "--base-path", str(base), "gap-open",
                    "--work-id", work_id,
                    "--owner-stage", "design",
                    "--required-action", "fixed-window burst flaw",
                ],
                [
                    "--base-path", str(base), "stage-update",
                    "--work-id", work_id,
                    "--stage", "design",
                    "--content", _DESIGN_LIGHT_CONTENT,
                ],
                ["--base-path", str(base), "stage-ready", "--work-id", work_id, "--stage", "design"],
                ["--base-path", str(base), "gate-quality", "--work-id", work_id, "--stage", "design"],
                ["--base-path", str(base), "gap-resolve", "--work-id", work_id, "--route-id", "R-1"],
                ["--base-path", str(base), "review-checkpoint", "--work-id", work_id, "--stage", "design"],
                [
                    "--base-path", str(base), "checkpoint-decide",
                    "--work-id", work_id,
                    "--stage", "design",
                    "--decision", "approved",
                    "--confirm",
                ],
            ):
                with pytest.raises(SystemExit) as exc:
                    cli_main(cmd)
                assert exc.value.code == 0

            with pytest.raises(SystemExit):
                A.main(["continue"], base_path=base)

            out = capsys.readouterr().out
            content_file = base / ".req-to-plan" / work_id / "inputs" / "spec-repair.md"
            assert "needs_repair" in out
            assert str(content_file) in out
            assert (
                f"stage-update --work-id {work_id} --stage spec "
                "--content-file"
            ) in out
            assert "stage-produce" not in out

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
            content_file = base / ".req-to-plan" / work_id / "inputs" / "raw_requirement-repair.md"
            assert "needs_repair" in out
            assert _expected_workflow_cli_prefix(base) in out
            assert content_file.exists()
            assert "Depends on REQ-AUTH-1 with no closure tag" in content_file.read_text(encoding="utf-8")
            assert str(content_file) in out
            assert (
                f"stage-update --work-id {work_id} --stage raw_requirement "
                "--content-file"
            ) in out
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
            work_id = A.read_active_pointer(base)["selected_work_id"]
            with pytest.raises(SystemExit):
                A.main(["continue"], base_path=base)
            out = capsys.readouterr().out
            assert "tier_not_locked" in out
            # The suggested next step must be invocable without relying on the
            # wrapper directory being present on PATH.
            assert _expected_workflow_cli_prefix(base) in out
            assert "r2p tier-lock" not in out
            assert "r2p-tier-lock" not in out
            assert f"tier-lock --work-id {work_id}" in out
            assert "<light|standard>" not in out

    def test_continue_tier_not_locked_includes_required_modifiers(self, capsys):
        import tempfile
        from pathlib import Path
        from tools.workflow_cli import agent_shortcuts as A
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            with pytest.raises(SystemExit):
                A.main(["start", "Migrate database and delete production data"], base_path=base)
            work_id = A.read_active_pointer(base)["selected_work_id"]

            with pytest.raises(SystemExit):
                A.main(["continue"], base_path=base)

            out = capsys.readouterr().out
            assert "tier_not_locked" in out
            assert _expected_workflow_cli_prefix(base) in out
            assert (
                f"tier-lock --work-id {work_id} --base standard "
                "--modifiers migration,safety --confirm"
            ) in out
            assert "r2p-tier-lock" not in out

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
            assert _expected_workflow_cli_prefix(base) in out
            assert (
                f"checkpoint-decide --work-id {work_id} --stage raw_requirement "
                "--decision approved --confirm"
            ) in out
            assert (
                f"checkpoint-decide --work-id {work_id} --stage raw_requirement "
                "--decision changes_requested"
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
            assert _expected_workflow_cli_prefix(base) in out
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
            assert _expected_workflow_cli_prefix(base) in out
            assert f"gate-entry --work-id {work_id} --stage requirement_brief" in out

    def _make_forced_review_run(self, base):
        """Build a CHECKPOINT_REVIEW run at DESIGN with a migration-locked tier."""
        from tools.workflow_cli import agent_shortcuts as A
        from tools.workflow_cli.models import RunStatus, Stage, TierBase, TierEstimate, TierModifier
        from tools.workflow_cli.state import RunStateManager, upsert_active_artifact
        with pytest.raises(SystemExit):
            A.main(["start", "Migrate the data store"], base_path=base)
        work_id = A.read_active_pointer(base)["selected_work_id"]
        manager = RunStateManager(base / ".req-to-plan" / work_id)
        record = manager.load()
        record.tier_locked = TierEstimate(TierBase.STANDARD, frozenset({TierModifier.MIGRATION}))
        record.current_stage = Stage.DESIGN
        record.status = RunStatus.CHECKPOINT_REVIEW
        upsert_active_artifact(record, Stage.DESIGN, "04-design.md", 1, "ready")
        manager.save(record)
        return work_id

    def test_continue_forced_review_stops_with_review_file(self, capsys):
        import tempfile
        from pathlib import Path
        from tools.workflow_cli import agent_shortcuts as A
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            work_id = self._make_forced_review_run(base)

            with pytest.raises(SystemExit):
                A.main(["continue"], base_path=base)

            out = capsys.readouterr().out
            review_file = (
                base / ".req-to-plan" / work_id / "reviews" / "design-subagent-review-v1.md"
            )
            assert "needs_subagent_review" in out
            assert str(review_file) in out
            # Forced review must precede human approval, not skip it.
            assert "needs_human_approval" not in out

    def test_continue_forced_review_satisfied_then_human_approval(self, capsys):
        import tempfile
        from pathlib import Path
        from tools.workflow_cli import agent_shortcuts as A
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            work_id = self._make_forced_review_run(base)
            reviews = base / ".req-to-plan" / work_id / "reviews"
            reviews.mkdir(parents=True, exist_ok=True)
            (reviews / "design-subagent-review-v1.md").write_text("findings", encoding="utf-8")

            with pytest.raises(SystemExit):
                A.main(["continue"], base_path=base)

            out = capsys.readouterr().out
            assert "needs_human_approval" in out
            assert "needs_subagent_review" not in out
            assert (
                f"checkpoint-decide --work-id {work_id} --stage design "
                "--decision approved --confirm"
            ) in out

    def test_continue_light_tier_checkpoint_skips_subagent_review(self, capsys):
        import tempfile
        from pathlib import Path
        from tools.workflow_cli import agent_shortcuts as A
        from tools.workflow_cli.models import RunStatus, Stage, TierBase, TierEstimate
        from tools.workflow_cli.state import RunStateManager, upsert_active_artifact
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            with pytest.raises(SystemExit):
                A.main(["start", "Add a tooltip"], base_path=base)
            work_id = A.read_active_pointer(base)["selected_work_id"]
            manager = RunStateManager(base / ".req-to-plan" / work_id)
            record = manager.load()
            record.tier_locked = TierEstimate(TierBase.LIGHT)
            record.current_stage = Stage.DESIGN
            record.status = RunStatus.CHECKPOINT_REVIEW
            upsert_active_artifact(record, Stage.DESIGN, "04-design.md", 1, "ready")
            manager.save(record)

            with pytest.raises(SystemExit):
                A.main(["continue"], base_path=base)

            out = capsys.readouterr().out
            assert "needs_subagent_review" not in out
            assert "needs_human_approval" in out


# ---------------------------------------------------------------------------
# TestGapShortcuts
# ---------------------------------------------------------------------------


def _seed_via_cli(tmp):
    from tests.test_cli import _seed_plan_approved_run
    return _seed_plan_approved_run(tmp)


def test_r2p_gap_open_delegates():
    with tempfile.TemporaryDirectory() as tmp:
        work_id, _ = _seed_via_cli(tmp)
        with pytest.raises(SystemExit) as exc:
            main(
                ["gap-open", "--work-id", work_id, "--owner-stage", "design",
                 "--required-action", "fix"],
                base_path=Path(tmp),
            )
        assert exc.value.code == 0
        rec = RunStateManager(Path(tmp) / ".req-to-plan" / work_id).load()
        assert any(r.status == "open" and r.owner_stage.value == "design" for r in rec.open_routes)


def test_r2p_gap_resolve_delegates():
    with tempfile.TemporaryDirectory() as tmp:
        work_id, _ = _seed_via_cli(tmp)
        with pytest.raises(SystemExit) as exc:
            main(
                ["gap-open", "--work-id", work_id, "--owner-stage", "design",
                 "--required-action", "fix"],
                base_path=Path(tmp),
            )
        assert exc.value.code == 0
        for cmd in (
            ["--base-path", tmp, "stage-update", "--work-id", work_id, "--stage", "design", "--content", _DESIGN_LIGHT_CONTENT],
            ["--base-path", tmp, "stage-ready", "--work-id", work_id, "--stage", "design"],
            ["--base-path", tmp, "gate-quality", "--work-id", work_id, "--stage", "design"],
        ):
            with pytest.raises(SystemExit) as exc:
                cli_main(cmd)
            assert exc.value.code == 0
        with pytest.raises(SystemExit) as exc:
            main(["gap-resolve", "--work-id", work_id, "--route-id", "R-1"], base_path=Path(tmp))
        assert exc.value.code == 0
        rec = RunStateManager(Path(tmp) / ".req-to-plan" / work_id).load()
        assert rec.open_routes[0].status == "repaired"


def test_r2p_gap_open_wrapper_executes():
    wrapper = Path(__file__).resolve().parents[1] / "tools" / "r2p-gap-open"
    assert wrapper.exists() and os.access(wrapper, os.X_OK)
    with tempfile.TemporaryDirectory() as tmp:
        work_id, _ = _seed_via_cli(tmp)
        result = subprocess.run(
            [str(wrapper), "--work-id", work_id, "--owner-stage", "design", "--required-action", "fix"],
            cwd=tmp, text=True, capture_output=True,
        )
        assert result.returncode == 0, result.stderr or result.stdout
        rec = RunStateManager(Path(tmp) / ".req-to-plan" / work_id).load()
        assert any(r.status == "open" and r.owner_stage.value == "design" for r in rec.open_routes)


def test_r2p_gap_resolve_wrapper_executes():
    gap_open = Path(__file__).resolve().parents[1] / "tools" / "r2p-gap-open"
    gap_resolve = Path(__file__).resolve().parents[1] / "tools" / "r2p-gap-resolve"
    assert gap_open.exists() and os.access(gap_open, os.X_OK)
    assert gap_resolve.exists() and os.access(gap_resolve, os.X_OK)
    with tempfile.TemporaryDirectory() as tmp:
        work_id, _ = _seed_via_cli(tmp)
        r = subprocess.run(
            [str(gap_open), "--work-id", work_id, "--owner-stage", "design", "--required-action", "fix"],
            cwd=tmp, text=True, capture_output=True,
        )
        assert r.returncode == 0, r.stderr or r.stdout
        for cmd in (
            ["--base-path", tmp, "stage-update", "--work-id", work_id, "--stage", "design", "--content", _DESIGN_LIGHT_CONTENT],
            ["--base-path", tmp, "stage-ready", "--work-id", work_id, "--stage", "design"],
            ["--base-path", tmp, "gate-quality", "--work-id", work_id, "--stage", "design"],
        ):
            with pytest.raises(SystemExit) as exc:
                cli_main(cmd)
            assert exc.value.code == 0
        r = subprocess.run(
            [str(gap_resolve), "--work-id", work_id, "--route-id", "R-1"],
            cwd=tmp, text=True, capture_output=True,
        )
        assert r.returncode == 0, r.stderr or r.stdout
        rec = RunStateManager(Path(tmp) / ".req-to-plan" / work_id).load()
        assert rec.open_routes[0].status == "repaired"


class TestSeedForStage:
    def test_seed_includes_scope_headings_for_brief(self):
        from tools.workflow_cli.agent_shortcuts import _seed_for_stage
        from tools.workflow_cli.models import Stage, TierBase, TierEstimate
        tier = TierEstimate(base=TierBase.STANDARD, modifiers=frozenset())
        seed = _seed_for_stage(Stage.REQUIREMENT_BRIEF, tier, upstream_summary="")
        assert "## In-Scope" in seed
        assert "## Out-of-Scope" in seed

    def test_seed_appends_upstream_summary_when_present(self):
        from tools.workflow_cli.agent_shortcuts import _seed_for_stage
        from tools.workflow_cli.models import Stage, TierBase, TierEstimate
        tier = TierEstimate(base=TierBase.LIGHT, modifiers=frozenset())
        seed = _seed_for_stage(Stage.DESIGN, tier, upstream_summary="REQ-AUTH-001: do X")
        assert "REQ-AUTH-001: do X" in seed
        assert "## Upstream Summary (read-only)" in seed

    def test_seed_includes_context_summary_when_present(self):
        from tools.workflow_cli.agent_shortcuts import _seed_for_stage
        from tools.workflow_cli.models import Stage, TierBase, TierEstimate
        tier = TierEstimate(base=TierBase.LIGHT, modifiers=frozenset())
        seed = _seed_for_stage(Stage.DESIGN, tier, context_summary="languages: {'Python': 100}")
        assert "Project Context" in seed
        assert "'Python'" in seed


class TestRunStartArgs:
    def test_repo_path_is_forwarded_to_run_start(self):
        from tools.workflow_cli.agent_shortcuts import _build_run_start_args
        args = _build_run_start_args("WF-x", "do thing", None, repo_path=".")
        assert "--repo-path" in args
        assert args[args.index("--repo-path") + 1] == "."

    def test_repo_path_absent_when_not_given(self):
        from tools.workflow_cli.agent_shortcuts import _build_run_start_args
        args = _build_run_start_args("WF-x", "do thing", None, repo_path=None)
        assert "--repo-path" not in args

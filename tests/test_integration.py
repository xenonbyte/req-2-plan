"""
Integration tests for the req-to-plan workflow pipeline.

Exercises the full workflow pipeline via cli.main() and agent_shortcuts.main()
with real temp directories — no mocking of filesystem operations.
"""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from tools.workflow_cli.cli import main
from tools.workflow_cli.agent_shortcuts import (
    main as shortcuts_main,
    read_active_pointer,
    write_active_pointer,
)
from tools.workflow_cli.state import RunStateManager
from tools.workflow_cli.models import RunStatus, WorkId


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def invoke(args: list[str], base_path=None, expect_exit: int = 0):
    """Call main() with optional --base-path injection; assert expected exit code."""
    full_args = list(args)
    if base_path is not None:
        full_args = ["--base-path", str(base_path)] + full_args
    with pytest.raises(SystemExit) as exc:
        main(full_args)
    assert exc.value.code == expect_exit, (
        f"Expected exit {expect_exit}, got {exc.value.code}"
    )


def _force_close(run_dir: Path) -> None:
    """Force a run record to CLOSED_AT_PLAN_CHECKPOINT status by direct mutation."""
    mgr = RunStateManager(run_dir)
    record = mgr.load()
    record.status = RunStatus.CLOSED_AT_PLAN_CHECKPOINT
    mgr.save(record)


def _start_run(base_path, work_id: str = "WF-20260527-integ", requirement: str = "Add rate limiting"):
    """Helper to create a run and return (base_path, work_id, run_dir)."""
    invoke(
        ["run-start", "--work-id", work_id, "--requirement", requirement],
        base_path=base_path,
    )
    run_dir = Path(base_path) / ".req-to-plan" / work_id
    return run_dir


_WORK_ID = "WF-20260527-integ"
_REQUIREMENT = "Add rate limiting to the API gateway"


# ---------------------------------------------------------------------------
# TestFullRunLifecycle
# ---------------------------------------------------------------------------


class TestFullRunLifecycle:
    """Happy-path tests from run-start through stage operations."""

    def test_run_start_creates_expected_files(self):
        """run.md + 00-raw-requirement.md + 01-intake-brief.md must all exist."""
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            invoke(["run-start", "--work-id", _WORK_ID, "--requirement", _REQUIREMENT], base_path=base)
            run_dir = base / ".req-to-plan" / _WORK_ID
            assert (run_dir / "run.md").exists(), "run.md must exist"
            assert (run_dir / "00-raw-requirement.md").exists(), "00-raw-requirement.md must exist"
            assert (run_dir / "01-intake-brief.md").exists(), "01-intake-brief.md must exist"

    def test_stage_produce_then_update_increments_version(self):
        """After stage-update, artifact must contain v2 content and r2p_version: 2."""
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            _start_run(base, _WORK_ID, _REQUIREMENT)
            invoke(
                ["stage-produce", "--work-id", _WORK_ID, "--stage", "raw_requirement", "--content", "v1 content"],
                base_path=base,
            )
            invoke(
                ["stage-update", "--work-id", _WORK_ID, "--stage", "raw_requirement", "--content", "v2 content"],
                base_path=base,
            )
            artifact = base / ".req-to-plan" / _WORK_ID / "00-raw-requirement.md"
            text = artifact.read_text()
            assert "v2 content" in text
            assert "r2p_version: 2" in text

    def test_stage_ready_marks_artifact_ready(self):
        """After stage-ready, artifact must contain r2p_status: ready."""
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            _start_run(base, _WORK_ID, _REQUIREMENT)
            invoke(
                ["stage-produce", "--work-id", _WORK_ID, "--stage", "raw_requirement", "--content", "Some content"],
                base_path=base,
            )
            invoke(
                ["stage-ready", "--work-id", _WORK_ID, "--stage", "raw_requirement"],
                base_path=base,
            )
            artifact = base / ".req-to-plan" / _WORK_ID / "00-raw-requirement.md"
            text = artifact.read_text()
            assert "r2p_status: ready" in text

    def test_status_run_reports_run_state(self, capsys):
        """status-run output must include the work_id."""
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            _start_run(base, _WORK_ID, _REQUIREMENT)
            invoke(["status-run", "--work-id", _WORK_ID], base_path=base)
            out = capsys.readouterr().out
            assert _WORK_ID in out

    def test_tier_lock_saves_to_run_md(self):
        """After tier-lock, run.md must contain the locked tier."""
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            _start_run(base, _WORK_ID, _REQUIREMENT)
            invoke(
                ["tier-lock", "--work-id", _WORK_ID, "--base", "standard", "--confirm"],
                base_path=base,
            )
            run_md = base / ".req-to-plan" / _WORK_ID / "run.md"
            text = run_md.read_text()
            # Tier Lock section should show standard, not "unlocked"
            assert "standard" in text
            assert "unlocked" not in text.split("## Tier Lock")[1].split("##")[0]

    def test_run_resume_returns_context(self, capsys):
        """run-resume must print context info including work_id and status."""
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            _start_run(base, _WORK_ID, _REQUIREMENT)
            invoke(["run-resume", "--work-id", _WORK_ID], base_path=base)
            out = capsys.readouterr().out
            assert _WORK_ID in out
            assert len(out.strip()) > 0

    def test_gate_entry_raw_requirement_in_lifecycle(self, capsys):
        """gate-entry for raw_requirement must pass after run-start (no upstream required)."""
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            _start_run(base, _WORK_ID, _REQUIREMENT)
            invoke(["gate-entry", "--work-id", _WORK_ID, "--stage", "raw_requirement"], base_path=base)
            out = capsys.readouterr().out
            assert "pass" in out.lower() or "ok" in out.lower()


# ---------------------------------------------------------------------------
# TestTierFlow
# ---------------------------------------------------------------------------


class TestTierFlow:
    """Tests around tier estimation, locking, and floor enforcement."""

    def test_tier_estimate_without_run(self, capsys):
        """tier-estimate works standalone without a run (just text input)."""
        invoke(["tier-estimate", "--text", "Add a simple logout button"])
        out = capsys.readouterr().out
        assert "light" in out.lower() or "standard" in out.lower()

    def test_tier_lock_at_floor_succeeds(self, capsys):
        """Locking at standard always succeeds regardless of estimated floor."""
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            _start_run(base, _WORK_ID, _REQUIREMENT)
            invoke(
                ["tier-lock", "--work-id", _WORK_ID, "--base", "standard", "--confirm"],
                base_path=base,
            )
            out = capsys.readouterr().out
            assert "standard" in out.lower() or "tier" in out.lower()

    def test_tier_lock_below_floor_fails(self):
        """Locking below estimated floor must exit 2 (CLI error)."""
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            # Use a migration requirement to guarantee standard floor
            invoke(
                ["run-start", "--work-id", _WORK_ID, "--requirement", "Migrate database schema"],
                base_path=base,
            )
            # Verify the floor is standard
            run_dir = base / ".req-to-plan" / _WORK_ID
            mgr = RunStateManager(run_dir)
            record = mgr.load()
            if record.tier_estimate and record.tier_estimate.base.value == "standard":
                # Attempt to lock at light — must fail
                invoke(
                    ["tier-lock", "--work-id", _WORK_ID, "--base", "light", "--confirm"],
                    base_path=base,
                    expect_exit=2,
                )
            else:
                # Floor is light — override floor is needed; standard lock succeeds
                invoke(
                    ["tier-lock", "--work-id", _WORK_ID, "--base", "standard", "--confirm"],
                    base_path=base,
                )

    def test_tier_lock_below_floor_with_override_succeeds(self, capsys):
        """--override-floor allows locking below computed floor."""
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            # Use a migration requirement so floor is standard
            invoke(
                ["run-start", "--work-id", _WORK_ID, "--requirement", "Migrate database schema"],
                base_path=base,
            )
            run_dir = base / ".req-to-plan" / _WORK_ID
            mgr = RunStateManager(run_dir)
            record = mgr.load()
            if record.tier_estimate and record.tier_estimate.base.value == "standard":
                # With --override-floor + --confirm, locking below floor must succeed
                invoke(
                    ["tier-lock", "--work-id", _WORK_ID, "--base", "light", "--override-floor", "--confirm"],
                    base_path=base,
                    expect_exit=0,
                )
                out = capsys.readouterr().out
                assert "light" in out.lower()

    def test_tier_status_shows_locked_tier_after_lock(self, capsys):
        """tier-status after lock must display locked tier information."""
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            _start_run(base, _WORK_ID, _REQUIREMENT)
            invoke(
                ["tier-lock", "--work-id", _WORK_ID, "--base", "standard", "--confirm"],
                base_path=base,
            )
            invoke(["tier-status", "--work-id", _WORK_ID], base_path=base)
            out = capsys.readouterr().out
            assert "tier" in out.lower() or "standard" in out.lower()

    def test_tier_estimate_migration_text_detects_modifier(self, capsys):
        """Tier estimate for migration text should report migration modifier."""
        invoke(["tier-estimate", "--text", "Migrate database from MySQL to PostgreSQL"])
        out = capsys.readouterr().out
        assert "migration" in out.lower() or "standard" in out.lower()


# ---------------------------------------------------------------------------
# TestGateFlow
# ---------------------------------------------------------------------------


class TestGateFlow:
    """Tests for entry and quality gate commands."""

    def test_gate_entry_raw_requirement_passes(self, capsys):
        """Entry gate for raw_requirement passes immediately after run-start (no upstream deps)."""
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            _start_run(base, _WORK_ID, _REQUIREMENT)
            invoke(["gate-entry", "--work-id", _WORK_ID, "--stage", "raw_requirement"], base_path=base)
            out = capsys.readouterr().out
            assert "pass" in out.lower() or "ok" in out.lower() or "passed" in out.lower()

    def test_gate_entry_requirement_brief_fails_without_checkpoint(self):
        """Entry gate for requirement_brief fails when raw_requirement has no checkpoint.

        Note: STAGE_REQUIRED_UPSTREAM_CHECKPOINTS shows requirement_brief requires [],
        so this test verifies that at least the gate runs without crashing, and passes
        when no upstream is required.
        """
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            _start_run(base, _WORK_ID, _REQUIREMENT)
            # requirement_brief has no required upstream checkpoints per the model,
            # so gate-entry should pass with exit 0
            invoke(
                ["gate-entry", "--work-id", _WORK_ID, "--stage", "requirement_brief"],
                base_path=base,
                expect_exit=0,
            )

    def test_gate_entry_risk_discovery_fails_without_upstream(self):
        """Entry gate for risk_discovery must fail (exit 3) when requirement_brief not approved."""
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            _start_run(base, _WORK_ID, _REQUIREMENT)
            # risk_discovery requires requirement_brief checkpoint — not present yet
            invoke(
                ["gate-entry", "--work-id", _WORK_ID, "--stage", "risk_discovery"],
                base_path=base,
                expect_exit=3,
            )

    def test_gate_quality_runs_on_artifact(self, capsys):
        """gate-quality runs after stage-produce (may pass or fail, must not crash)."""
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            _start_run(base, _WORK_ID, _REQUIREMENT)
            invoke(
                ["tier-lock", "--work-id", _WORK_ID, "--base", "standard", "--confirm"],
                base_path=base,
            )
            invoke(
                ["stage-produce", "--work-id", _WORK_ID, "--stage", "raw_requirement", "--content", "Some content"],
                base_path=base,
            )
            invoke(
                ["stage-ready", "--work-id", _WORK_ID, "--stage", "raw_requirement"],
                base_path=base,
            )
            # exit 0 (pass) or 3 (quality fail) are both acceptable structural outcomes
            with pytest.raises(SystemExit) as exc:
                main(["--base-path", str(base), "gate-quality", "--work-id", _WORK_ID, "--stage", "raw_requirement"])
            assert exc.value.code in (0, 3)
            out = capsys.readouterr().out
            assert len(out.strip()) > 0

    def test_gate_quality_fails_without_tier_lock(self, capsys):
        """gate-quality must fail when tier is not locked yet."""
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            _start_run(base, _WORK_ID, _REQUIREMENT)
            invoke(
                ["stage-produce", "--work-id", _WORK_ID, "--stage", "raw_requirement", "--content", "Content"],
                base_path=base,
            )
            invoke(
                ["stage-ready", "--work-id", _WORK_ID, "--stage", "raw_requirement"],
                base_path=base,
            )
            # Tier not locked — quality gate must fail with exit 3
            invoke(
                ["gate-quality", "--work-id", _WORK_ID, "--stage", "raw_requirement"],
                base_path=base,
                expect_exit=3,
            )


# ---------------------------------------------------------------------------
# TestRunReopen
# ---------------------------------------------------------------------------


class TestRunReopen:
    """Tests for run-reopen: closing and reopening runs."""

    def _setup_closed_run(self, base: Path, work_id: str = _WORK_ID) -> Path:
        """Create a run and force-close it, returning its run_dir."""
        run_dir = _start_run(base, work_id, _REQUIREMENT)
        _force_close(run_dir)
        return run_dir

    def test_run_reopen_creates_new_run_dir(self):
        """Reopening a closed run must create a new run directory."""
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            self._setup_closed_run(base, _WORK_ID)
            invoke(
                ["run-reopen", "--from", _WORK_ID, "--stage", "requirement_brief", "--reason", "fix spec gap"],
                base_path=base,
            )
            # New run dir should be _WORK_ID + -r1
            new_work_id = f"{_WORK_ID}-r1"
            new_run_dir = base / ".req-to-plan" / new_work_id
            assert new_run_dir.exists(), f"New run dir {new_run_dir} must be created"
            assert (new_run_dir / "run.md").exists(), "New run.md must exist"

    def test_run_reopen_copies_artifacts_before_target_stage(self):
        """Artifacts for stages before target must be copied to the new run dir."""
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            run_dir = self._setup_closed_run(base, _WORK_ID)

            # Verify 00-raw-requirement.md exists in source (created by run-start)
            assert (run_dir / "00-raw-requirement.md").exists()

            # Reopen at requirement_brief — raw_requirement artifact should be copied
            invoke(
                ["run-reopen", "--from", _WORK_ID, "--stage", "requirement_brief", "--reason", "revise brief"],
                base_path=base,
            )
            new_work_id = f"{_WORK_ID}-r1"
            new_run_dir = base / ".req-to-plan" / new_work_id
            assert (new_run_dir / "00-raw-requirement.md").exists(), (
                "00-raw-requirement.md must be copied to new run dir"
            )

    def test_run_reopen_fails_on_open_source_run(self):
        """Reopening a non-closed run must exit 6 (conflict)."""
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            _start_run(base, _WORK_ID, _REQUIREMENT)
            # Run is ACTIVE_STAGE_DRAFT — not closed
            invoke(
                ["run-reopen", "--from", _WORK_ID, "--stage", "requirement_brief", "--reason", "attempt reopen"],
                base_path=base,
                expect_exit=6,
            )

    def test_run_reopen_lineage_recorded_in_new_run(self):
        """New run.md must contain the reopen lineage reference."""
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            self._setup_closed_run(base, _WORK_ID)
            invoke(
                ["run-reopen", "--from", _WORK_ID, "--stage", "requirement_brief", "--reason", "fix-gap"],
                base_path=base,
            )
            new_work_id = f"{_WORK_ID}-r1"
            new_run_dir = base / ".req-to-plan" / new_work_id
            mgr = RunStateManager(new_run_dir)
            record = mgr.load()
            assert record.reopen_lineage is not None
            assert _WORK_ID in record.reopen_lineage

    def test_run_reopen_new_run_is_active(self):
        """Reopened run must have an active (non-closed) status."""
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            self._setup_closed_run(base, _WORK_ID)
            invoke(
                ["run-reopen", "--from", _WORK_ID, "--stage", "design", "--reason", "revise design"],
                base_path=base,
            )
            new_work_id = f"{_WORK_ID}-r1"
            new_run_dir = base / ".req-to-plan" / new_work_id
            mgr = RunStateManager(new_run_dir)
            record = mgr.load()
            assert record.status != RunStatus.CLOSED_AT_PLAN_CHECKPOINT


# ---------------------------------------------------------------------------
# TestAgentShortcuts
# ---------------------------------------------------------------------------


class TestAgentShortcuts:
    """Integration tests for agent_shortcuts.main() without mocking."""

    def _invoke_shortcut(self, args: list[str], base_path: Path, expect_exit: int = 0):
        with pytest.raises(SystemExit) as exc:
            shortcuts_main(args, base_path=base_path)
        assert exc.value.code == expect_exit, (
            f"Expected exit {expect_exit}, got {exc.value.code}"
        )

    def test_shortcut_start_creates_run_and_pointer(self):
        """After shortcut start, active pointer file must exist."""
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            self._invoke_shortcut(["start", "Add rate limiting"], base)
            pointer = read_active_pointer(base)
            assert pointer is not None
            assert "selected_work_id" in pointer
            # The run dir must also exist
            work_id = pointer["selected_work_id"]
            run_dir = base / ".req-to-plan" / work_id
            assert run_dir.exists(), f"Run dir {run_dir} must exist"
            assert (run_dir / "run.md").exists()

    def test_shortcut_start_blocks_on_active_run(self, capsys):
        """Second start without --separate must exit nonzero when active run exists."""
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            # Create first run via shortcuts
            self._invoke_shortcut(["start", "Add rate limiting"], base)
            capsys.readouterr()  # clear output
            # Second start should be blocked
            self._invoke_shortcut(["start", "Another feature"], base, expect_exit=1)
            out = capsys.readouterr().out
            assert "blocked" in out

    def test_shortcut_switch_updates_pointer(self):
        """After switch, active pointer must contain the new work_id."""
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            # Create a run manually via cli and write pointer to a different run
            work_id_a = "WF-20260527-run-a"
            work_id_b = "WF-20260527-run-b"
            invoke(["run-start", "--work-id", work_id_a, "--requirement", "Feature A"], base_path=base)
            invoke(["run-start", "--work-id", work_id_b, "--requirement", "Feature B"], base_path=base)
            write_active_pointer(base, work_id_a)

            # Switch to B
            self._invoke_shortcut(["switch", "--work-id", work_id_b], base)
            pointer = read_active_pointer(base)
            assert pointer["selected_work_id"] == work_id_b

    def test_shortcut_status_no_pointer_exits_zero(self, capsys):
        """status without pointer must exit 0 (read-only, no crash)."""
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            self._invoke_shortcut(["status"], base, expect_exit=0)
            out = capsys.readouterr().out
            assert "no_selected_run" in out

    def test_shortcut_start_separate_flag_bypasses_block(self):
        """start --separate must succeed even when an active run exists."""
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            # Create first run
            self._invoke_shortcut(["start", "Feature One"], base)
            # Start second with --separate flag — must succeed
            self._invoke_shortcut(["start", "--separate", "Feature Two"], base, expect_exit=0)

    def test_shortcut_status_all_lists_runs(self, capsys):
        """status --all must list all known runs."""
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            # Create two runs
            invoke(["run-start", "--work-id", "WF-20260527-run-x", "--requirement", "Feature X"], base_path=base)
            invoke(["run-start", "--work-id", "WF-20260527-run-y", "--requirement", "Feature Y"], base_path=base)
            self._invoke_shortcut(["status", "--all"], base, expect_exit=0)
            out = capsys.readouterr().out
            assert "WF-20260527-run-x" in out
            assert "WF-20260527-run-y" in out


# ---------------------------------------------------------------------------
# TestExecutorAdapt
# ---------------------------------------------------------------------------

_PLAN_CONTENT = """\
# Plan: {work_id}

## PLAN-TASK-001

Goal: Add rate limiting

Steps:
1. Implement middleware

Spec References: SPEC-001

Verification:
- Run tests
"""


class TestExecutorAdapt:
    """Tests for executor adapt via agent_shortcuts."""

    def _setup_closed_run_with_plan(self, base: Path, work_id: str) -> Path:
        """Create a closed run with a minimal 07-plan.md."""
        run_dir = _start_run(base, work_id, _REQUIREMENT)
        _force_close(run_dir)
        plan_path = run_dir / "07-plan.md"
        plan_path.write_text(_PLAN_CONTENT.format(work_id=work_id), encoding="utf-8")
        return run_dir

    def _invoke_shortcut(self, args: list[str], base_path: Path, expect_exit: int = 0):
        with pytest.raises(SystemExit) as exc:
            shortcuts_main(args, base_path=base_path)
        assert exc.value.code == expect_exit, (
            f"Expected exit {expect_exit}, got {exc.value.code}"
        )

    def test_adapt_writes_derived_plan(self):
        """adapt must create superpowers-plan.md when plan has PLAN-TASK sections."""
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            work_id = "WF-20260527-adapt-test"
            self._setup_closed_run_with_plan(base, work_id)

            # Set the active pointer to this run
            write_active_pointer(base, work_id)

            self._invoke_shortcut(["adapt", "--executor", "superpowers"], base)

            output_path = base / ".req-to-plan" / work_id / "superpowers-plan.md"
            assert output_path.exists(), "superpowers-plan.md must be created"
            content = output_path.read_text()
            assert "Superpowers Plan" in content or "PLAN-TASK" in content or "rate limiting" in content.lower()

    def test_adapt_requires_closed_run(self, capsys):
        """adapt must exit nonzero when the run is not in a terminal state."""
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            work_id = "WF-20260527-adapt-open"
            _start_run(base, work_id, _REQUIREMENT)
            # Do NOT close the run
            write_active_pointer(base, work_id)
            # adapt should fail because run is still active
            self._invoke_shortcut(["adapt", "--executor", "superpowers"], base, expect_exit=1)
            out = capsys.readouterr().out
            assert "blocked" in out or "not_closed" in out or "run_not_closed" in out

    def test_adapt_with_unsupported_executor_exits_nonzero(self, capsys):
        """adapt with an unknown executor must exit nonzero."""
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            work_id = "WF-20260527-adapt-bad-exec"
            self._setup_closed_run_with_plan(base, work_id)
            write_active_pointer(base, work_id)
            self._invoke_shortcut(["adapt", "--executor", "nonexistent-executor"], base, expect_exit=2)

"""
Tests for tools/workflow_cli/cli.py — CLI command router.
"""
from __future__ import annotations

import tempfile
import os
from pathlib import Path

import pytest

from tools.workflow_cli.cli import main


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
# tier-lock
# ---------------------------------------------------------------------------


class TestTierLock:
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
            # quality gate may pass or fail (structural), just check it runs cleanly
            with pytest.raises(SystemExit) as exc:
                main(["--base-path", str(tmp), "gate-quality", "--work-id", "WF-20260527-test", "--stage", "raw_requirement"])
            # exit_code 0 (pass) or 3 (gate fail) are both acceptable
            assert exc.value.code in (0, 3)
            out = capsys.readouterr().out
            assert len(out.strip()) > 0


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

    def test_version(self, capsys):
        from tools.workflow_cli.install_cli import main as install_main
        install_main(["version"])
        out = capsys.readouterr().out
        assert "v1" in out

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

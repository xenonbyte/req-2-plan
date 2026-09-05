"""
Tests for tools/workflow_cli/agent_shortcuts.py
"""
from __future__ import annotations

import contextlib
import argparse
import io
import itertools
import json
import os
import shlex
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from tools.workflow_cli.models import RunStatus, Stage, TierBase, TierEstimate, WorkId
from tools.workflow_cli.version import R2P_VERSION
from tools.workflow_cli.agent_shortcuts import (
    generate_work_id,
    is_terminal,
    read_active_pointer,
    scan_open_runs,
    write_active_pointer,
    main,
    _pointer_path,
)
from tools.workflow_cli.cli import main as cli_main
from tools.workflow_cli.state import RunStateManager

REPO_ROOT = Path(__file__).parent.parent

# Schema-valid DESIGN LIGHT content (required for gate-quality to pass at LIGHT tier).
_DESIGN_LIGHT_CONTENT = (
    "# design v2\n\n## Design Summary\ncontent\n"
    "## Chosen Design\ncontent\n### DES-ARCH-001 Selected design\ncontent\n"
    "## SPEC Handoff\ncontent\n"
)


def test_all_wrappers_use_trusted_bootstrap_without_disabling_user_site():
    wrappers = [REPO_ROOT / "tools" / "r2p"] + sorted(
        (REPO_ROOT / "tools").glob("r2p-*")
    )
    assert wrappers
    for wrapper in wrappers:
        content = wrapper.read_text(encoding="utf-8")
        assert '-E "$REPO_ROOT/tools/workflow_cli/__main__.py"' in content, wrapper
        assert " -I " not in content, wrapper
        assert " -s " not in content, wrapper
        assert "export PYTHONPATH=" not in content, wrapper
        assert " -m tools.workflow_cli" not in content, wrapper


def test_r2p_start_wrapper_does_not_import_workspace_module(tmp_path):
    malicious = tmp_path / "tools" / "workflow_cli"
    malicious.mkdir(parents=True)
    (tmp_path / "tools" / "__init__.py").write_text("", encoding="utf-8")
    (malicious / "__init__.py").write_text("", encoding="utf-8")
    (malicious / "agent_shortcuts.py").write_text(
        "from pathlib import Path\n"
        "Path(__file__).parents[2].joinpath('workspace-module-ran').write_text('yes')\n",
        encoding="utf-8",
    )
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)

    completed = subprocess.run(
        [str(REPO_ROOT / "tools" / "r2p-start"), "--help"],
        cwd=tmp_path,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert not (tmp_path / "workspace-module-ran").exists()


def test_r2p_start_wrapper_can_import_dependency_from_user_site():
    base_python = (
        Path(sys.base_prefix)
        / "bin"
        / f"python{sys.version_info.major}.{sys.version_info.minor}"
    )
    if not base_python.exists():
        base_python = Path(getattr(sys, "_base_executable", sys.executable))
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        home = root / "home"
        workspace = root / "workspace"
        bin_dir = root / "bin"
        home.mkdir()
        workspace.mkdir()
        bin_dir.mkdir()
        env = os.environ.copy()
        env["HOME"] = str(home)
        env.pop("PYTHONPATH", None)
        env.pop("PYTHONNOUSERSITE", None)
        probe = subprocess.run(
            [
                str(base_python),
                "-E",
                "-c",
                "import site; print(site.ENABLE_USER_SITE); print(site.USER_SITE)",
            ],
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )
        assert probe.returncode == 0, probe.stderr
        enabled, user_site_raw = probe.stdout.strip().splitlines()
        if enabled != "True":
            pytest.skip("base interpreter disables user site-packages")
        user_site = Path(user_site_raw)
        try:
            user_site.relative_to(root)
        except ValueError:
            pytest.skip("base interpreter does not derive user site from isolated HOME")
        user_site.mkdir(parents=True)
        marker = root / "user-yaml-imported"
        (user_site / "yaml.py").write_text(
            "from pathlib import Path\n"
            f"Path({str(marker)!r}).write_text('loaded', encoding='utf-8')\n"
            "def safe_load(stream):\n"
            "    return {}\n",
            encoding="utf-8",
        )
        (bin_dir / "python3").symlink_to(base_python)
        env["PATH"] = f"{bin_dir}{os.pathsep}{env.get('PATH', '')}"

        completed = subprocess.run(
            [
                str(REPO_ROOT / "tools" / "r2p-start"),
                "--repo-path",
                str(workspace),
                "User-site dependency smoke test",
            ],
            cwd=workspace,
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )

        assert completed.returncode == 0, completed.stderr
        assert marker.read_text(encoding="utf-8") == "loaded"


def _expected_workflow_cli_prefix(base: Path) -> str:
    from tools.workflow_cli import agent_shortcuts as A

    return (
        f"{shlex.quote(sys.executable)} -E "
        f"{shlex.quote(str(A._repo_root() / 'tools' / 'workflow_cli' / '__main__.py'))} "
        f"tools.workflow_cli --base-path {shlex.quote(str(base))}"
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

    def test_write_rejects_symlinked_gitignore_with_clean_blocked(self):
        from tools.workflow_cli.output import EXIT_CONFLICT
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            (base / ".req-to-plan").mkdir()
            secret = base / "secret.txt"
            secret.write_text("PRIVATE\n", encoding="utf-8")
            gitignore = base / ".req-to-plan" / ".gitignore"
            gitignore.symlink_to(secret)

            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                with pytest.raises(SystemExit) as exc:
                    write_active_pointer(base, "WF-20260527-link")

            assert exc.value.code == EXIT_CONFLICT
            assert "blocked:" in buf.getvalue()
            assert gitignore.is_symlink()
            assert secret.read_text(encoding="utf-8") == "PRIVATE\n"
            assert not (base / ".req-to-plan" / ".workflow-active").exists()


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

    def test_two_character_slug_falls_back_to_hash_id(self):
        wid = generate_work_id("UI", today="20260527")

        assert wid.startswith("WF-20260527-run-")
        WorkId(wid)  # raises ValueError if invalid

    def test_deduplicates_if_path_exists(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            req = "add login feature"
            wid1 = generate_work_id(req, base_path=base, today="20260527")
            _make_run(base, wid1)
            wid2 = generate_work_id(req, base_path=base, today="20260527")
            assert wid2 != wid1
            assert wid2.endswith("-2")

    def test_deduplicates_if_archive_path_exists(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            req = "add login feature"
            wid1 = generate_work_id(req, base_path=base, today="20260527")
            (base / ".req-to-plan" / "archive" / wid1).mkdir(parents=True)

            wid2 = generate_work_id(req, base_path=base, today="20260527")

            assert wid2 != wid1
            assert wid2.endswith("-2")

    def test_truncation_never_leaves_trailing_dash(self):
        # Regression: truncating after strip("-") could leave a trailing "-",
        # producing an invalid WorkId. The 36-char slug window means a word
        # whose boundary aligns a hyphen at the slice edge must still validate.
        req = "a" * 35 + " bb"
        wid = generate_work_id(req, today="20260527")
        assert not wid.endswith("-")
        WorkId(wid)  # raises ValueError if invalid

    def test_generated_ids_always_valid_workid(self):
        for req in [
            "authentication internationalization localization",
            "a" * 60,
            "x" * 36 + " yyy",
            "implement a very long requirement that exceeds the maximum allowed length for slugs",
            "short req here",
        ]:
            wid = generate_work_id(req, today="20260527")
            assert len(wid) <= 48
            WorkId(wid)  # must not raise


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

    def test_rejects_run_md_with_mismatched_work_id(self, capsys):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            requested = "WF-20260527-directory-id"
            run_md = _make_run(base, requested)
            run_md.write_text(
                run_md.read_text(encoding="utf-8").replace(
                    requested, "WF-20260527-embedded-id", 1
                ),
                encoding="utf-8",
            )

            _invoke(["switch", "--work-id", requested], base, expect_exit=6)

            assert read_active_pointer(base) is None
            assert "run_identity_mismatch" in capsys.readouterr().out


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

    def test_json_mode_emits_one_parseable_payload(self, capsys, monkeypatch):
        monkeypatch.setenv("R2P_JSON", "1")
        work_id = "WF-20260527-json-start"

        def fake_run_cli(_args, _base):
            print(json.dumps({"status": "ok", "work_id": work_id}))
            return 0

        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            with patch(
                "tools.workflow_cli.agent_shortcuts.generate_work_id",
                return_value=work_id,
            ), patch(
                "tools.workflow_cli.agent_shortcuts._run_cli",
                side_effect=fake_run_cli,
            ):
                _invoke(["start", "json output"], base)

            payload = json.loads(capsys.readouterr().out)
            assert payload["work_id"] == work_id
            assert payload["created"] == f".req-to-plan/{work_id}/run.md"
            assert payload["selected_run"] == f".req-to-plan/{work_id}/run.md"
            assert payload["next"] == "r2p-continue"

    def test_start_preflights_workspace_gitignore_before_creating_run(self, capsys):
        from tools.workflow_cli.output import EXIT_CONFLICT
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            (base / ".req-to-plan").mkdir()
            secret = base / "secret.txt"
            secret.write_text("PRIVATE\n", encoding="utf-8")
            gitignore = base / ".req-to-plan" / ".gitignore"
            gitignore.symlink_to(secret)
            work_id = "WF-20260527-add-rate-limiting"

            with patch(
                "tools.workflow_cli.agent_shortcuts.generate_work_id",
                return_value=work_id,
            ):
                _invoke(["start", "add rate limiting"], base, expect_exit=EXIT_CONFLICT)

            out = capsys.readouterr().out
            assert "unsafe_workspace_gitignore" in out
            assert not (base / ".req-to-plan" / work_id).exists()
            assert not (base / ".req-to-plan" / ".workflow-active").exists()
            assert secret.read_text(encoding="utf-8") == "PRIVATE\n"

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

    def test_rejects_symlinked_workspace_dir_before_missing_pointer(self, capsys):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            outside = base / "outside"
            outside.mkdir()
            (base / ".req-to-plan").symlink_to(outside, target_is_directory=True)

            _invoke(["continue"], base, expect_exit=6)

            out = capsys.readouterr().out
            assert "unsafe_workspace_dir_symlink" in out
            assert "no_selected_run" not in out

    def test_rejects_symlinked_workspace_dir_before_reading_pointer(self, capsys):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            outside = base / "outside"
            outside.mkdir()
            (outside / ".workflow-active").write_text(
                "selected_work_id: ../outside\n",
                encoding="utf-8",
            )
            (base / ".req-to-plan").symlink_to(outside, target_is_directory=True)

            _invoke(["continue"], base, expect_exit=6)

            out = capsys.readouterr().out
            assert "unsafe_workspace_dir_symlink" in out
            assert "invalid_work_id" not in out

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

    def test_rejects_pointer_to_run_with_mismatched_embedded_id(self, capsys):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            requested = "WF-20260527-continue-id"
            run_md = _make_run(base, requested)
            run_md.write_text(
                run_md.read_text(encoding="utf-8").replace(
                    requested, "WF-20260527-different-id", 1
                ),
                encoding="utf-8",
            )
            write_active_pointer(base, requested)

            _invoke(["continue"], base, expect_exit=6)

            out = capsys.readouterr().out
            assert "run_identity_mismatch" in out
            assert not (run_md.parent / "inputs").exists()

    def test_rejects_symlinked_run_dir_before_writing_inputs(self, capsys):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            work_id = "WF-20260527-continue-symlink"
            outside = base / "outside"
            run_md = _make_run(outside, work_id)
            record = RunStateManager(run_md.parent).load()
            record.current_stage = Stage.REQUIREMENT_BRIEF
            record.tier_locked = TierEstimate(base=TierBase.LIGHT)
            RunStateManager(run_md.parent).save(record)

            r2p_dir = base / ".req-to-plan"
            r2p_dir.mkdir()
            (r2p_dir / work_id).symlink_to(run_md.parent, target_is_directory=True)
            _pointer_path(base).write_text(
                f"selected_work_id: {work_id}\n",
                encoding="utf-8",
            )

            _invoke(["continue"], base, expect_exit=6)

            out = capsys.readouterr().out
            assert "unsafe_run_dir_symlink" in out
            assert not (run_md.parent / "inputs").exists()


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
    def test_all_json_aggregates_multiple_runs_into_one_value(self, capsys, monkeypatch):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            _make_run(base, "WF-20260527-status-one")
            _make_run(base, "WF-20260527-status-two")
            monkeypatch.setenv("R2P_JSON", "1")

            _invoke(["status", "--all"], base, expect_exit=0)

            payload = json.loads(capsys.readouterr().out)
            assert [run["work_id"] for run in payload["runs"]] == [
                "WF-20260527-status-one",
                "WF-20260527-status-two",
            ]

    def test_all_json_represents_no_runs_as_an_empty_collection(self, capsys, monkeypatch):
        with tempfile.TemporaryDirectory() as tmp:
            monkeypatch.setenv("R2P_JSON", "1")

            _invoke(["status", "--all"], Path(tmp), expect_exit=0)

            assert json.loads(capsys.readouterr().out) == {"runs": []}

    def test_all_json_reports_malformed_run_without_breaking_aggregate(
        self, capsys, monkeypatch
    ):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            healthy_id = "WF-20260527-status-healthy"
            malformed_id = "WF-20260527-status-malformed"
            _make_run(base, healthy_id)
            malformed_dir = base / ".req-to-plan" / malformed_id
            malformed_dir.mkdir(parents=True)
            (malformed_dir / "run.md").write_text(
                "not a workflow run\n",
                encoding="utf-8",
            )
            monkeypatch.setenv("R2P_JSON", "1")

            _invoke(["status", "--all"], base, expect_exit=6)

            payload = json.loads(capsys.readouterr().out)
            runs = {run["work_id"]: run for run in payload["runs"]}
            assert healthy_id in runs
            assert runs[malformed_id] == {
                "work_id": malformed_id,
                "status": "invalid",
                "error": "invalid_run_state",
                "exit_code": 6,
            }

    def test_all_text_reports_malformed_run_without_breaking_aggregate(self, capsys):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            healthy_id = "WF-20260527-status-healthy"
            malformed_id = "WF-20260527-status-malformed"
            _make_run(base, healthy_id)
            malformed_dir = base / ".req-to-plan" / malformed_id
            malformed_dir.mkdir(parents=True)
            (malformed_dir / "run.md").write_text(
                "not a workflow run\n",
                encoding="utf-8",
            )

            _invoke(["status", "--all"], base, expect_exit=6)

            out = capsys.readouterr().out
            assert healthy_id in out
            assert (
                f"work_id: {malformed_id}\nstatus: invalid\nerror: invalid_run_state"
                in out
            )

    def test_prints_no_selected_run_when_no_pointer(self, capsys):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            _invoke(["status"], base, expect_exit=0)
            out = capsys.readouterr().out
            assert "no_selected_run" in out

    def test_prints_no_selected_run_when_pointer_missing_key(self, capsys):
        # A non-empty pointer file lacking selected_work_id (hand-edited or
        # externally corrupted) must behave like a missing pointer, not KeyError.
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            (base / ".req-to-plan").mkdir()
            _pointer_path(base).write_text(
                "updated_at: 2026-01-01T00:00:00Z\nreason: corrupted\n",
                encoding="utf-8",
            )
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
# TestCmdTaskBrief
# ---------------------------------------------------------------------------


class TestCmdTaskBrief:
    def test_prints_no_selected_run_when_no_pointer(self, capsys):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            _invoke(["task-brief", "--task", "2"], base, expect_exit=1)
            out = capsys.readouterr().out
            assert "no_selected_run" in out

    def test_prints_no_selected_run_when_pointer_missing_key(self, capsys):
        # Shape-B fallback (ns.work_id empty): a corrupted pointer missing the
        # selected_work_id key must fall through to no_selected_run, not KeyError.
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            (base / ".req-to-plan").mkdir()
            _pointer_path(base).write_text(
                "updated_at: 2026-01-01T00:00:00Z\nreason: corrupted\n",
                encoding="utf-8",
            )
            _invoke(["task-brief", "--task", "2"], base, expect_exit=1)
            out = capsys.readouterr().out
            assert "no_selected_run" in out


# ---------------------------------------------------------------------------
# TestCmdReopen
# ---------------------------------------------------------------------------


class TestCmdReopen:
    def test_delegates_to_run_reopen_and_selects_reopened_run(self, capsys):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)

            def fake_run_cli(args_list, base_path):
                print("  new_work_id: WF-20260527-source-r1")
                return 0

            with patch("tools.workflow_cli.agent_shortcuts._run_cli", side_effect=fake_run_cli) as mock_cli:
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
            pointer = read_active_pointer(base)
            assert pointer is not None
            assert pointer["selected_work_id"] == "WF-20260527-source-r1"

    def test_reopen_preflights_workspace_gitignore_before_creating_reopened_run(self, capsys):
        from tests.test_cli import _seed_plan_approved_run
        from tools.workflow_cli.cli import main as cli_main
        from tools.workflow_cli.output import EXIT_CONFLICT

        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            work_id, _ = _seed_plan_approved_run(base, "WF-20260527-source")
            with pytest.raises(SystemExit) as exc:
                cli_main(["--base-path", str(base), "run-close", "--work-id", work_id])
            assert exc.value.code == 0

            secret = base / "secret.txt"
            secret.write_text("PRIVATE\n", encoding="utf-8")
            gitignore = base / ".req-to-plan" / ".gitignore"
            gitignore.unlink()
            gitignore.symlink_to(secret)

            _invoke(
                [
                    "reopen",
                    "--from", work_id,
                    "--stage", "plan",
                    "--reason", "fix spec gap",
                ],
                base,
                expect_exit=EXIT_CONFLICT,
            )

            out = capsys.readouterr().out
            assert "unsafe_workspace_gitignore" in out
            assert not (base / ".req-to-plan" / "WF-20260527-source-r1").exists()
            assert read_active_pointer(base) is None
            assert secret.read_text(encoding="utf-8") == "PRIVATE\n"

    def test_reopen_preserves_json_mode_output(self, capsys, monkeypatch):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            monkeypatch.setenv("R2P_JSON", "1")

            def fake_run_cli(args_list, base_path):
                print(json.dumps({"status": "ok", "new_work_id": "WF-20260527-source-r1"}))
                return 0

            with patch("tools.workflow_cli.agent_shortcuts._run_cli", side_effect=fake_run_cli):
                _invoke(
                    [
                        "reopen",
                        "--from", "WF-20260527-source",
                        "--stage", "plan",
                        "--reason", "fix spec gap",
                    ],
                    base,
                )

            out = capsys.readouterr().out
            payload = json.loads(out)
            assert payload["new_work_id"] == "WF-20260527-source-r1"
            assert payload["selected_run"] == ".req-to-plan/WF-20260527-source-r1/run.md"
            assert payload["next"] == "r2p-continue"
            pointer = read_active_pointer(base)
            assert pointer is not None
            assert pointer["selected_work_id"] == "WF-20260527-source-r1"


class TestCmdAbandon:
    def test_delegates_to_run_abandon_and_clears_matching_pointer(self, capsys):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            work_id = "WF-20260527-abandoned-draft"
            write_active_pointer(base, work_id, reason="test")

            def fake_run_cli(args_list, base_path):
                print(
                    "  work_id: WF-20260527-abandoned-draft\n"
                    "  status: archived\n"
                )
                return 0

            with patch(
                "tools.workflow_cli.agent_shortcuts._run_cli",
                side_effect=fake_run_cli,
            ) as mock_cli:
                _invoke(
                    [
                        "abandon",
                        "--work-id", work_id,
                        "--reason", "superseded draft",
                    ],
                    base,
                )

            called_args = mock_cli.call_args[0][0]
            assert called_args == [
                "run-abandon",
                "--work-id", work_id,
                "--reason", "superseded draft",
            ]
            assert read_active_pointer(base) is None
            assert "abandoned_and_archived" in capsys.readouterr().out

    def test_json_mode_emits_single_payload_and_clears_pointer(
        self, capsys, monkeypatch
    ):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            work_id = "WF-20260527-abandoned-json"
            write_active_pointer(base, work_id, reason="test")
            monkeypatch.setenv("R2P_JSON", "1")

            def fake_run_cli(args_list, base_path):
                print(json.dumps({
                    "status": "ok",
                    "work_id": work_id,
                    "archived_to": f"{base}/.req-to-plan/archive/{work_id}",
                }))
                return 0

            with patch(
                "tools.workflow_cli.agent_shortcuts._run_cli",
                side_effect=fake_run_cli,
            ):
                _invoke(
                    [
                        "abandon",
                        "--work-id", work_id,
                        "--reason", "superseded draft",
                    ],
                    base,
                )

            payload = json.loads(capsys.readouterr().out)
            assert payload["work_id"] == work_id
            assert payload["next"] == "r2p-status --all"
            assert read_active_pointer(base) is None


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

        launcher = A._repo_root() / "tools" / "workflow_cli" / "__main__.py"
        assert f"{shlex.quote(sys.executable)} -E {shlex.quote(str(launcher))}" in command
        assert "tools.workflow_cli --base-path" in command
        assert "PYTHONPATH=" not in command

    def test_workflow_cli_command_uses_patched_active_python_executable(self):
        from tools.workflow_cli import agent_shortcuts as A

        with patch.object(A.sys, "executable", "python"):
            command = A._workflow_cli_command(
                Path("/tmp/r2p-root"),
                ["stage-ready", "--work-id", "WF-20260527-test", "--stage", "raw_requirement"],
            )

        launcher = A._repo_root() / "tools" / "workflow_cli" / "__main__.py"
        assert f"python -E {shlex.quote(str(launcher))}" in command
        assert "tools.workflow_cli --base-path" in command
        assert "PYTHONPATH=" not in command

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

    def test_continue_next_stage_seeds_content_file_after_entry_gate_passes(self, capsys):
        import tempfile
        from pathlib import Path
        from tools.workflow_cli import agent_shortcuts as A
        from tools.workflow_cli.models import RunStatus, Stage, TierBase, TierEstimate
        from tools.workflow_cli.state import RunStateManager

        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            with pytest.raises(SystemExit):
                A.main(["start", "Add rate limiting"], base_path=base)
            capsys.readouterr()
            work_id = A.read_active_pointer(base)["selected_work_id"]
            run_dir = base / ".req-to-plan" / work_id
            manager = RunStateManager(run_dir)
            record = manager.load()
            record.status = RunStatus.NEXT_STAGE
            record.current_stage = Stage.REQUIREMENT_BRIEF
            record.tier_locked = TierEstimate(base=TierBase.STANDARD, modifiers=frozenset())
            manager.save(record)
            (run_dir / "02-project-context.md").write_text("repo summary", encoding="utf-8")

            def fake_gate_entry(args, gate_base_path):
                assert gate_base_path == base
                assert args == ["gate-entry", "--work-id", work_id, "--stage", "requirement_brief"]
                updated = manager.load()
                updated.status = RunStatus.ACTIVE_STAGE_DRAFT
                manager.save(updated)
                return 0

            with patch("tools.workflow_cli.agent_shortcuts._run_cli", side_effect=fake_gate_entry):
                with pytest.raises(SystemExit) as exc:
                    A.main(["continue"], base_path=base)

            out = capsys.readouterr().out
            content = (run_dir / "inputs" / "requirement_brief-content.md").read_text(encoding="utf-8")
            assert exc.value.code == 0
            assert "entered_stage" in out
            assert "## In-Scope" in content
            assert "## Upstream Summary (read-only)" in content
            assert "## Project Context (read-only)\nrepo summary" in content

    @pytest.mark.parametrize("seed_source", ["02-project-context.md", "00-raw-requirement.md"])
    def test_continue_rejects_symlinked_seed_source_without_copying_target(
        self, capsys, seed_source
    ):
        from tools.workflow_cli import agent_shortcuts as A

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            base = root / "workspace"
            base.mkdir()
            secret = root / "outside-secret.txt"
            secret.write_text("PRIVATE-CONTENT\n", encoding="utf-8")
            with pytest.raises(SystemExit):
                A.main(["start", "Add rate limiting"], base_path=base)
            capsys.readouterr()
            work_id = A.read_active_pointer(base)["selected_work_id"]
            run_dir = base / ".req-to-plan" / work_id
            manager = RunStateManager(run_dir)
            record = manager.load()
            record.status = RunStatus.ACTIVE_STAGE_DRAFT
            record.current_stage = Stage.REQUIREMENT_BRIEF
            record.tier_locked = TierEstimate(TierBase.LIGHT)
            manager.save(record)
            source = run_dir / seed_source
            source.unlink()
            source.symlink_to(secret)

            with pytest.raises(SystemExit) as exc:
                A.main(["continue"], base_path=base)

            out = capsys.readouterr().out
            assert exc.value.code == 6
            assert "unsafe_seed_source" in out
            assert not (run_dir / "inputs" / "requirement_brief-content.md").exists()
            assert secret.read_text(encoding="utf-8") == "PRIVATE-CONTENT\n"

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

    def test_seed_strips_readonly_blocks_carried_by_upstream(self):
        # An upstream artifact persists the read-only blocks it was seeded with
        # (nothing strips them at store time). When that artifact becomes the
        # next stage's upstream summary, those blocks must be stripped so the
        # freshly injected ones are not duplicated/accumulated.
        from tools.workflow_cli.agent_shortcuts import _seed_for_stage
        from tools.workflow_cli.models import Stage, TierBase, TierEstimate
        tier = TierEstimate(base=TierBase.LIGHT, modifiers=frozenset())
        upstream = (
            "# spec v1\n\n## Spec Summary\nreal spec content\n"
            "\n## Upstream Summary (read-only)\nstale design echo\n"
            "<!-- /r2p-read-only -->\n"
            "\n## Project Context (read-only)\nstale pack echo\n"
            "<!-- /r2p-read-only -->\n"
        )
        seed = _seed_for_stage(
            Stage.PLAN, tier, upstream_summary=upstream, context_summary="fresh pack"
        )
        # Exactly one of each read-only heading: the freshly injected wrappers.
        assert seed.count("## Project Context (read-only)") == 1
        assert seed.count("## Upstream Summary (read-only)") == 1
        # The upstream's real content survives; its carried read-only echoes don't.
        assert "real spec content" in seed
        assert "fresh pack" in seed
        assert "stale design echo" not in seed
        assert "stale pack echo" not in seed


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


class TestPrepareInputFileSymlink(unittest.TestCase):
    def test_rejects_preplanted_symlink_target(self):
        from tools.workflow_cli.agent_shortcuts import _prepare_input_file
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            (run_dir / "inputs").mkdir()
            outside = run_dir / "outside.md"
            outside.write_text("secret", encoding="utf-8")
            link = run_dir / "inputs" / "spec-content.md"
            os.symlink(outside, link)
            with self.assertRaises(ValueError):
                _prepare_input_file(run_dir, "spec", "content", "seed")
            # The symlink target must NOT have been written through.
            self.assertEqual(outside.read_text(encoding="utf-8"), "secret")

    def test_rejects_symlinked_inputs_directory(self):
        from tools.workflow_cli.agent_shortcuts import _prepare_input_file
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            run_dir = base / "run"
            run_dir.mkdir()
            outside_inputs = base / "outside-inputs"
            outside_inputs.mkdir()
            os.symlink(outside_inputs, run_dir / "inputs")
            with self.assertRaises(ValueError):
                _prepare_input_file(run_dir, "spec", "content", "seed")
            # The symlinked directory must NOT receive the seeded file.
            self.assertFalse((outside_inputs / "spec-content.md").exists())

    def test_writes_seed_when_absent_and_not_a_symlink(self):
        from tools.workflow_cli.agent_shortcuts import _prepare_input_file
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            p = _prepare_input_file(run_dir, "spec", "content", "seed text")
            self.assertEqual(p.read_text(encoding="utf-8"), "seed text")
            self.assertFalse(p.is_symlink())


class TestCheckpointAmbiguityGuidance(unittest.TestCase):
    def _emit_subagent_review_output(self) -> str:
        from pathlib import Path
        from tools.workflow_cli import agent_shortcuts as ash
        from tools.workflow_cli.models import (
            Stage, TierBase, TierModifier, TierEstimate, WorkId, STAGE_ARTIFACT_MAP,
        )
        from tools.workflow_cli.state import create_run_record, upsert_active_artifact
        # Force a subagent review at DESIGN: a safety modifier with no
        # version-matched review file on disk → _emit_checkpoint_stop prints
        # `needs_subagent_review`.
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            (run_dir / "reviews").mkdir()
            rec = create_run_record(WorkId("WF-20260101-amb"))
            rec.current_stage = Stage.DESIGN
            rec.tier_locked = TierEstimate(
                base=TierBase.STANDARD,
                modifiers=frozenset({TierModifier.SAFETY}),
            )
            upsert_active_artifact(
                rec,
                stage=Stage.DESIGN,
                artifact=STAGE_ARTIFACT_MAP[Stage.DESIGN],
                version=1,
                status="ready",
            )
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                ash._emit_checkpoint_stop(run_dir, "WF-20260101-amb", "design", rec, run_dir)
            return buf.getvalue()

    def test_subagent_review_note_mentions_ambiguity(self):
        out = self._emit_subagent_review_output()
        self.assertIn("needs_subagent_review", out)
        self.assertIn("ambiguity", out.lower())

    def test_continue_blocks_symlinked_forced_review_in_checkpoint_review(self):
        from tools.workflow_cli import agent_shortcuts as A
        from tools.workflow_cli.models import (
            RunStatus,
            STAGE_ARTIFACT_MAP,
            Stage,
            TierBase,
            TierEstimate,
            TierModifier,
            WorkId,
        )
        from tools.workflow_cli.output import EXIT_CONFLICT
        from tools.workflow_cli.state import (
            RunStateManager,
            create_run_record,
            upsert_active_artifact,
        )

        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            work_id = "WF-20260101-symlink-review"
            run_dir = base / ".req-to-plan" / work_id
            run_dir.mkdir(parents=True)
            outside = base / "outside-reviews"
            outside.mkdir()
            (outside / "design-subagent-review-v1.md").write_text(
                "planted review\n", encoding="utf-8"
            )
            (run_dir / "reviews").symlink_to(outside, target_is_directory=True)

            rec = create_run_record(WorkId(work_id))
            rec.status = RunStatus.CHECKPOINT_REVIEW
            rec.current_stage = Stage.DESIGN
            rec.tier_locked = TierEstimate(
                base=TierBase.STANDARD,
                modifiers=frozenset({TierModifier.SAFETY}),
            )
            upsert_active_artifact(
                rec,
                stage=Stage.DESIGN,
                artifact=STAGE_ARTIFACT_MAP[Stage.DESIGN],
                version=1,
                status="ready",
            )
            RunStateManager(run_dir).save(rec)
            A.write_active_pointer(base, work_id)

            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                with pytest.raises(SystemExit) as exc:
                    A.main(["continue"], base_path=base)

            out = buf.getvalue()
            assert exc.value.code == EXIT_CONFLICT
            assert "blocked: unsafe_forced_review" in out
            assert "needs_subagent_review" not in out
            assert "review_file:" not in out
            assert (run_dir / "reviews").is_symlink()
            assert sorted(p.name for p in outside.iterdir()) == [
                "design-subagent-review-v1.md"
            ]


class TestIsTerminalArchived(unittest.TestCase):
    def test_archived_is_terminal(self):
        from tools.workflow_cli.agent_shortcuts import is_terminal
        from tools.workflow_cli.models import RunStatus
        self.assertTrue(is_terminal(RunStatus.ARCHIVED))

    def test_closed_is_terminal(self):
        from tools.workflow_cli.agent_shortcuts import is_terminal
        from tools.workflow_cli.models import RunStatus
        self.assertTrue(is_terminal(RunStatus.CLOSED_AT_PLAN_CHECKPOINT))


class TestArchiveShortcut(unittest.TestCase):
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

    def test_archive_clears_pointer_when_pointing_at_archived_run(self):
        import argparse
        import tempfile
        from pathlib import Path
        from tools.workflow_cli import agent_shortcuts as ash
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            self._closed_run(base, "WF-20260101-arch")
            ash.write_active_pointer(base, "WF-20260101-arch", reason="test")
            ns = argparse.Namespace(work_id="WF-20260101-arch")
            with self.assertRaises(SystemExit) as cm:
                ash._cmd_archive(ns, base)
            self.assertEqual(cm.exception.code, 0)
            self.assertFalse(ash._pointer_path(base).exists())
            self.assertTrue((base / ".req-to-plan" / "archive" / "WF-20260101-arch" / "run.md").exists())

    def _executing_run_incomplete(self, base, wid_str):
        from tools.workflow_cli.state import RunStateManager, create_run_record
        from tools.workflow_cli.models import RunStatus, Stage, WorkId
        wid = WorkId(wid_str)
        run_dir = base / ".req-to-plan" / wid_str
        run_dir.mkdir(parents=True)
        rec = create_run_record(wid)
        rec.status = RunStatus.EXECUTING
        rec.current_stage = Stage.CLOSED
        RunStateManager(run_dir).save(rec)
        exec_dir = run_dir / "execution"
        exec_dir.mkdir(parents=True)
        (exec_dir / "progress.md").write_text(
            "# Execution Progress\n\n- [ ] PLAN-TASK-001 t\n", encoding="utf-8"
        )
        return run_dir

    def test_archive_shortcut_blocks_incomplete_executing_run(self):
        import argparse, tempfile
        from pathlib import Path
        from tools.workflow_cli import agent_shortcuts as ash
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            run_dir = self._executing_run_incomplete(base, "WF-20260101-exec")
            ns = argparse.Namespace(work_id="WF-20260101-exec", force=False)
            with self.assertRaises(SystemExit) as cm:
                ash._cmd_archive(ns, base)
            self.assertEqual(cm.exception.code, 3)  # EXIT_GATE_FAIL
            self.assertTrue(run_dir.exists())  # not moved

    def test_archive_shortcut_force_passes_through(self):
        import argparse, tempfile
        from pathlib import Path
        from tools.workflow_cli import agent_shortcuts as ash
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            self._executing_run_incomplete(base, "WF-20260101-exec")
            ns = argparse.Namespace(work_id="WF-20260101-exec", force=True)
            with self.assertRaises(SystemExit) as cm:
                ash._cmd_archive(ns, base)
            self.assertEqual(cm.exception.code, 0)
            self.assertTrue((base / ".req-to-plan" / "archive" / "WF-20260101-exec" / "run.md").exists())

    def test_archive_json_mode_emits_single_payload(self):
        import argparse, tempfile
        from pathlib import Path
        from tools.workflow_cli import agent_shortcuts as ash
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            self._closed_run(base, "WF-20260101-arch")
            ash.write_active_pointer(base, "WF-20260101-arch", reason="test")
            ns = argparse.Namespace(work_id="WF-20260101-arch", force=False)
            buf = io.StringIO()
            with patch.dict(os.environ, {"R2P_JSON": "1"}):
                with contextlib.redirect_stdout(buf):
                    with self.assertRaises(SystemExit) as cm:
                        ash._cmd_archive(ns, base)

            self.assertEqual(cm.exception.code, 0)
            payload = json.loads(buf.getvalue())
            self.assertEqual(payload["work_id"], "WF-20260101-arch")
            self.assertEqual(payload["status"], "archived")
            self.assertEqual(payload["next"], "r2p-status --all")


class TestIsTerminalExecuting(unittest.TestCase):
    def test_executing_is_not_terminal(self):
        from tools.workflow_cli.agent_shortcuts import is_terminal
        from tools.workflow_cli.models import RunStatus
        self.assertFalse(is_terminal(RunStatus.EXECUTING))


class TestExecuteShortcutAndRouting(unittest.TestCase):
    def _run(self, base, wid_str, status):
        from tools.workflow_cli.state import RunStateManager, create_run_record
        from tools.workflow_cli.models import RunStatus, Stage, WorkId
        from tools.workflow_cli.artifact import write_artifact
        if not (base / ".git").exists():
            subprocess.run(["git", "init", "-q"], cwd=base, check=True)
            subprocess.run(["git", "config", "user.email", "tests@example.invalid"], cwd=base, check=True)
            subprocess.run(["git", "config", "user.name", "Tests"], cwd=base, check=True)
            subprocess.run(["git", "commit", "--allow-empty", "-qm", "test base"], cwd=base, check=True)
        wid = WorkId(wid_str)
        run_dir = base / ".req-to-plan" / wid_str
        run_dir.mkdir(parents=True)
        rec = create_run_record(wid)
        rec.status = status
        rec.current_stage = Stage.CLOSED if status != RunStatus.ACTIVE_STAGE_DRAFT else Stage.RAW_REQUIREMENT
        write_artifact(run_dir, Stage.PLAN, "# Plan\n\n## Tasks\n### PLAN-TASK-001: t\nSteps:\nPrerequisite: none\n", version=1, status="approved")
        RunStateManager(run_dir).save(rec)
        if status == RunStatus.EXECUTING:
            from tools.workflow_cli.execution_metrics import _initial_metrics_text

            execution = run_dir / "execution"
            execution.mkdir()
            execution_base = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=base,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            (execution / "progress.md").write_text(
                "\n".join((
                    "# Execution Progress",
                    "",
                    f"work_id: {wid_str}",
                    "",
                    f"Execution BASE: {execution_base}",
                    "",
                    "- [ ] PLAN-TASK-001 t",
                    "",
                )),
                encoding="utf-8",
            )
            (execution / "metrics.md").write_text(
                _initial_metrics_text(wid, "strict", 1),
                encoding="utf-8",
            )
        from tools.workflow_cli import agent_shortcuts as ash
        ash.write_active_pointer(base, wid_str, reason="test")
        return run_dir

    def _capture(self, fn, *a):
        import io, contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            with self.assertRaises(SystemExit) as cm:
                fn(*a)
        return buf.getvalue(), cm.exception.code

    @staticmethod
    def _execute_args(
        work_id,
        *,
        profile=None,
        confirm=False,
        reject=False,
        reason=None,
    ):
        return argparse.Namespace(
            work_id=work_id,
            profile=profile,
            confirm_fast_eligible=confirm,
            reject_fast_ineligible=reject,
            reason=reason,
        )

    @staticmethod
    def _lock_light_tier(run_dir):
        from tools.workflow_cli.models import TierBase, TierEstimate
        from tools.workflow_cli.state import RunStateManager

        manager = RunStateManager(run_dir)
        record = manager.load()
        record.tier_locked = TierEstimate(base=TierBase.LIGHT, modifiers=frozenset())
        manager.save(record)

    def test_execute_fast_closed_handshake_reviews_then_confirms_without_implicit_mutation(self):
        import tempfile
        from pathlib import Path
        from tools.workflow_cli import agent_shortcuts as ash
        from tools.workflow_cli.models import RunStatus
        from tools.workflow_cli.state import RunStateManager

        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            run_dir = self._run(
                base, "WF-20260101-fast", RunStatus.CLOSED_AT_PLAN_CHECKPOINT
            )
            self._lock_light_tier(run_dir)

            out, code = self._capture(
                ash._cmd_execute,
                self._execute_args("WF-20260101-fast", profile="fast"),
                base,
            )
            self.assertEqual(code, 0)
            self.assertIn("stop: fast_profile_review", out)
            self.assertIn("tier: light", out)
            self.assertIn("modifiers: none", out)
            self.assertEqual(
                RunStateManager(run_dir).load().status,
                RunStatus.CLOSED_AT_PLAN_CHECKPOINT,
            )
            self.assertFalse((run_dir / "execution").exists())

            out, code = self._capture(
                ash._cmd_execute,
                self._execute_args(
                    "WF-20260101-fast", profile="fast", confirm=True
                ),
                base,
            )
            self.assertEqual(code, 0)
            self.assertIn("stop: execute_plan", out)
            self.assertIn(
                "Execution Profile: fast",
                (run_dir / "execution" / "progress.md").read_text(encoding="utf-8"),
            )

    def test_execute_fast_rejects_invalid_prerequisites_before_any_mutation(self):
        from tools.workflow_cli.artifact import write_artifact
        from tools.workflow_cli.models import RunStatus, Stage
        from tools.workflow_cli import agent_shortcuts as ash

        first = "### PLAN-TASK-001: first\nSteps:\nPrerequisite: none\n"
        second = "### PLAN-TASK-002: second\nSteps:\nPrerequisite: PLAN-TASK-001\n"
        plans = (
            "### PLAN-TASK-001: legacy\n",
            first + "### PLAN-TASK-002: legacy\nSteps:\n- implement\n",
            first + second.replace("PLAN-TASK-001\n", "PLAN-TASK-999\n"),
            first + second.replace("Prerequisite:", "Prerequisite :"),
            first + second + "Prerequisite: none\n",
        )
        for plan, confirm, json_mode in itertools.product(plans, (False, True), (False, True)):
            with self.subTest(plan=plan, confirm=confirm, json_mode=json_mode), tempfile.TemporaryDirectory() as tmp:
                base = Path(tmp)
                work_id = "WF-20260101-prerequisite-preflight"
                run_dir = self._run(base, work_id, RunStatus.CLOSED_AT_PLAN_CHECKPOINT)
                self._lock_light_tier(run_dir)
                write_artifact(run_dir, Stage.PLAN, plan, version=1, status="approved")
                before = {p.relative_to(base): p.read_bytes() for p in (base / ".req-to-plan").rglob("*") if p.is_file()}
                with patch.dict(os.environ, {"R2P_JSON": "1" if json_mode else "0"}):
                    out, code = self._capture(
                        ash._cmd_execute,
                        self._execute_args(work_id, profile="fast", confirm=confirm),
                        base,
                    )
                self.assertEqual(code, 6, out)
                self.assertIn("prerequisite", out.lower())
                after = {p.relative_to(base): p.read_bytes() for p in (base / ".req-to-plan").rglob("*") if p.is_file()}
                self.assertEqual(before, after)
                self.assertFalse((run_dir / "execution").exists())

    def test_execute_fast_reject_and_structure_ineligible_are_zero_mutation(self):
        import tempfile
        from pathlib import Path
        from tools.workflow_cli import agent_shortcuts as ash
        from tools.workflow_cli.models import RunStatus
        from tools.workflow_cli.output import EXIT_CONFLICT
        from tools.workflow_cli.state import RunStateManager

        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            run_dir = self._run(
                base, "WF-20260101-fast", RunStatus.CLOSED_AT_PLAN_CHECKPOINT
            )
            out, code = self._capture(
                ash._cmd_execute,
                self._execute_args("WF-20260101-fast", profile="fast"),
                base,
            )
            self.assertEqual(code, EXIT_CONFLICT)
            self.assertIn("fast_profile_ineligible", out)
            self.assertEqual(
                RunStateManager(run_dir).load().status,
                RunStatus.CLOSED_AT_PLAN_CHECKPOINT,
            )
            self.assertFalse((run_dir / "execution").exists())

        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            run_dir = self._run(
                base, "WF-20260101-fast", RunStatus.CLOSED_AT_PLAN_CHECKPOINT
            )
            self._lock_light_tier(run_dir)
            out, code = self._capture(
                ash._cmd_execute,
                self._execute_args(
                    "WF-20260101-fast",
                    profile="fast",
                    reject=True,
                    reason="shared core change",
                ),
                base,
            )
            self.assertEqual(code, EXIT_CONFLICT)
            self.assertIn("fast_profile_ineligible", out)
            self.assertIn("shared core change", out)
            self.assertEqual(
                RunStateManager(run_dir).load().status,
                RunStatus.CLOSED_AT_PLAN_CHECKPOINT,
            )
            self.assertFalse((run_dir / "execution").exists())

    def test_execute_profile_resume_reuses_effective_profile_and_rejects_conflicts(self):
        import tempfile
        from pathlib import Path
        from tools.workflow_cli import agent_shortcuts as ash
        from tools.workflow_cli.models import RunStatus
        from tools.workflow_cli.output import EXIT_CONFLICT

        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            run_dir = self._run(
                base, "WF-20260101-fast", RunStatus.CLOSED_AT_PLAN_CHECKPOINT
            )
            self._lock_light_tier(run_dir)
            self._capture(
                ash._cmd_execute,
                self._execute_args(
                    "WF-20260101-fast", profile="fast", confirm=True
                ),
                base,
            )
            for profile in (None, "fast"):
                out, code = self._capture(
                    ash._cmd_execute,
                    self._execute_args("WF-20260101-fast", profile=profile),
                    base,
                )
                self.assertEqual(code, 0)
                self.assertIn("stop: resume_execution", out)
                self.assertIn("effective_profile: fast", out)

            out, code = self._capture(
                ash._cmd_execute,
                self._execute_args("WF-20260101-fast", profile="strict"),
                base,
            )
            self.assertEqual(code, EXIT_CONFLICT)
            self.assertIn("execution_profile_conflict", out)

            out, code = self._capture(
                ash._cmd_execute,
                self._execute_args(
                    "WF-20260101-fast", profile="fast", confirm=True
                ),
                base,
            )
            self.assertEqual(code, EXIT_CONFLICT)
            self.assertIn("profile_decision_on_executing_run", out)

    def test_execute_escalated_fast_resume_recovers_transaction_with_initial_profile(self):
        import tempfile
        from pathlib import Path
        from tools.workflow_cli import agent_shortcuts as ash
        from tools.workflow_cli.models import RunStatus

        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            work_id = "WF-20260101-escalated-fast"
            run_dir = self._run(
                base, work_id, RunStatus.CLOSED_AT_PLAN_CHECKPOINT
            )
            self._lock_light_tier(run_dir)
            self._capture(
                ash._cmd_execute,
                self._execute_args(work_id, profile="fast", confirm=True),
                base,
            )
            progress_path = run_dir / "execution" / "progress.md"
            progress_path.write_text(
                progress_path.read_text(encoding="utf-8")
                + "\nProfile Escalation: fast -> strict (reason: concern found)\n",
                encoding="utf-8",
            )

            out, code = self._capture(
                ash._cmd_execute,
                self._execute_args(work_id, profile="strict"),
                base,
            )

            self.assertEqual(code, 0)
            self.assertIn("stop: resume_execution", out)
            self.assertIn("effective_profile: strict", out)
            self.assertIn("first_actionable_task: 1", out)

    def test_execute_fast_resume_reports_first_actionable_task_not_first_unchecked(self):
        import re
        import tempfile
        from pathlib import Path
        from tools.workflow_cli import agent_shortcuts as ash
        from tools.workflow_cli.artifact import write_artifact
        from tools.workflow_cli.models import RunStatus, Stage

        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            work_id = "WF-20260101-fast-actionable"
            run_dir = self._run(
                base, work_id, RunStatus.CLOSED_AT_PLAN_CHECKPOINT
            )
            write_artifact(
                run_dir,
                Stage.PLAN,
                "# Plan\n\n## Tasks\n"
                "### PLAN-TASK-001: first\nSteps:\nPrerequisite: none\n"
                "### PLAN-TASK-002: second\nSteps:\nPrerequisite: PLAN-TASK-001\n",
                version=1,
                status="approved",
            )
            self._lock_light_tier(run_dir)
            self._capture(
                ash._cmd_execute,
                self._execute_args(work_id, profile="fast", confirm=True),
                base,
            )
            progress_path = run_dir / "execution" / "progress.md"
            execution_base = re.search(
                r"^Execution BASE: ([0-9a-f]{40})$",
                progress_path.read_text(encoding="utf-8"),
                re.MULTILINE,
            ).group(1)
            (base / "task-one.py").write_text("done = True\n", encoding="utf-8")
            subprocess.run(["git", "add", "task-one.py"], cwd=base, check=True)
            subprocess.run(["git", "commit", "-qm", "task one"], cwd=base, check=True)
            task_head = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=base,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            progress_path.write_text(
                progress_path.read_text(encoding="utf-8")
                + f"Task 1: implemented (commits {execution_base[:7]}..{task_head[:7]}, verification recorded)\n",
                encoding="utf-8",
            )

            out, code = self._capture(
                ash._cmd_execute, self._execute_args(work_id), base
            )

            self.assertEqual(code, 0)
            self.assertIn("first_actionable_task: 2", out)
            self.assertNotIn("first unchecked task", out)

            with patch.dict(os.environ, {"R2P_JSON": "1"}):
                out, code = self._capture(
                    ash._cmd_execute, self._execute_args(work_id), base
                )
            self.assertEqual(code, 0)
            self.assertEqual(json.loads(out)["first_actionable_task"], 2)

    def test_execute_resume_recovers_start_transaction_marker_and_rejects_mismatch(self):
        import re
        import tempfile
        from pathlib import Path
        from tools.workflow_cli import agent_shortcuts as ash
        from tools.workflow_cli.models import RunStatus
        from tools.workflow_cli.output import EXIT_CONFLICT

        def seed_marker(base, work_id, *, profile="strict"):
            run_dir = self._run(
                base, work_id, RunStatus.CLOSED_AT_PLAN_CHECKPOINT
            )
            self._capture(
                ash._cmd_execute, self._execute_args(work_id), base
            )
            progress = (run_dir / "execution" / "progress.md").read_text(
                encoding="utf-8"
            )
            execution_base = re.search(
                r"^Execution BASE: ([0-9a-f]{40})$", progress, re.MULTILINE
            ).group(1)
            marker = {
                "schema": 1,
                "work_id": work_id,
                "profile": profile,
                "task_count": 1,
                "execution_base": execution_base,
            }
            marker_path = run_dir / "execution" / ".start-transaction.json"
            marker_path.write_text(
                json.dumps(marker, sort_keys=True, separators=(",", ":")) + "\n",
                encoding="utf-8",
            )
            return marker_path

        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            marker = seed_marker(base, "WF-20260101-resume-recovery")

            out, code = self._capture(
                ash._cmd_execute,
                self._execute_args("WF-20260101-resume-recovery"),
                base,
            )

            self.assertEqual(code, 0)
            self.assertIn("stop: resume_execution", out)
            self.assertFalse(marker.exists())

        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            marker = seed_marker(
                base, "WF-20260101-resume-conflict", profile="fast"
            )

            out, code = self._capture(
                ash._cmd_execute,
                self._execute_args("WF-20260101-resume-conflict"),
                base,
            )

            self.assertEqual(code, EXIT_CONFLICT)
            self.assertNotIn("stop: resume_execution", out)
            self.assertTrue(marker.exists())

    def test_execute_profile_resume_errors_remain_json(self):
        import tempfile
        from pathlib import Path
        from tools.workflow_cli import agent_shortcuts as ash
        from tools.workflow_cli.models import RunStatus
        from tools.workflow_cli.output import EXIT_CONFLICT

        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            with patch.dict(os.environ, {"R2P_JSON": "1"}):
                out, code = self._capture(
                    ash._cmd_execute,
                    self._execute_args(
                        "WF-20260101-invalid", profile="strict", confirm=True
                    ),
                    base,
                )
            self.assertEqual(code, 2)
            payload = json.loads(out)
            self.assertEqual(payload["status"], "error")
            self.assertEqual(payload["reason"], "invalid_execute_profile_arguments")
            self.assertEqual(payload["exit_code"], 2)

        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            run_dir = self._run(base, "WF-20260101-malformed", RunStatus.EXECUTING)
            progress = run_dir / "execution" / "progress.md"
            progress.write_text(
                progress.read_text(encoding="utf-8").replace(
                    "Execution BASE:", "Execution BASE: invalid\nExecution BASE:", 1
                ),
                encoding="utf-8",
            )
            with patch.dict(os.environ, {"R2P_JSON": "1"}):
                out, code = self._capture(
                    ash._cmd_execute,
                    self._execute_args("WF-20260101-malformed"),
                    base,
                )
            self.assertEqual(code, EXIT_CONFLICT)
            payload = json.loads(out)
            self.assertEqual(payload["status"], "error")
            self.assertEqual(payload["reason"], "invalid_execution_profile_ledger")
            self.assertEqual(payload["exit_code"], EXIT_CONFLICT)
            self.assertEqual(payload["work_id"], "WF-20260101-malformed")

        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            run_dir = self._run(base, "WF-20260101-conflict", RunStatus.EXECUTING)
            progress = run_dir / "execution" / "progress.md"
            progress.write_text(
                progress.read_text(encoding="utf-8").replace(
                    "- [ ] PLAN-TASK-001",
                    "Execution Profile: fast\n\n- [ ] PLAN-TASK-001",
                ),
                encoding="utf-8",
            )
            with patch.dict(os.environ, {"R2P_JSON": "1"}):
                out, code = self._capture(
                    ash._cmd_execute,
                    self._execute_args("WF-20260101-conflict", profile="strict"),
                    base,
                )
            self.assertEqual(code, EXIT_CONFLICT)
            payload = json.loads(out)
            self.assertEqual(payload["status"], "error")
            self.assertEqual(payload["reason"], "execution_profile_conflict")
            self.assertEqual(payload["effective_profile"], "fast")
            self.assertEqual(payload["requested_profile"], "strict")

        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            self._run(base, "WF-20260101-decision", RunStatus.EXECUTING)
            with patch.dict(os.environ, {"R2P_JSON": "1"}):
                out, code = self._capture(
                    ash._cmd_execute,
                    self._execute_args(
                        "WF-20260101-decision", profile="fast", confirm=True
                    ),
                    base,
                )
            self.assertEqual(code, EXIT_CONFLICT)
            payload = json.loads(out)
            self.assertEqual(payload["status"], "error")
            self.assertEqual(payload["reason"], "profile_decision_on_executing_run")
            self.assertEqual(payload["exit_code"], EXIT_CONFLICT)

    def test_execute_profile_invalid_argument_combinations_fail_before_mutation(self):
        import tempfile
        from pathlib import Path
        from tools.workflow_cli import agent_shortcuts as ash
        from tools.workflow_cli.models import RunStatus

        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            run_dir = self._run(
                base, "WF-20260101-fast", RunStatus.CLOSED_AT_PLAN_CHECKPOINT
            )
            self._lock_light_tier(run_dir)
            invalid = (
                self._execute_args(
                    "WF-20260101-fast", profile="fast", confirm=True, reject=True
                ),
                self._execute_args(
                    "WF-20260101-fast", profile="fast", reject=True
                ),
                self._execute_args(
                    "WF-20260101-fast", profile="strict", confirm=True
                ),
                self._execute_args(
                    "WF-20260101-fast",
                    profile="fast",
                    reject=True,
                    reason="line one\nline two",
                ),
            )
            for args in invalid:
                out, code = self._capture(ash._cmd_execute, args, base)
                self.assertEqual(code, 2)
                self.assertIn("invalid_execute_profile_arguments", out)
                self.assertFalse((run_dir / "execution").exists())

    def test_execute_on_closed_starts_and_prints_execute_plan(self):
        import tempfile, argparse
        from pathlib import Path
        from tools.workflow_cli import agent_shortcuts as ash
        from tools.workflow_cli.models import RunStatus
        from tools.workflow_cli.state import RunStateManager
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            run_dir = self._run(base, "WF-20260101-exec", RunStatus.CLOSED_AT_PLAN_CHECKPOINT)
            out, code = self._capture(ash._cmd_execute, argparse.Namespace(work_id="WF-20260101-exec"), base)
            self.assertEqual(code, 0)
            self.assertIn("stop: execute_plan", out)
            self.assertIn(f"plan: {run_dir / '07-plan.md'}\n", out)
            self.assertIn(f"ledger: {run_dir / 'execution' / 'progress.md'}\n", out)
            self.assertIn("r2p-archive --work-id WF-20260101-exec", out)
            self.assertEqual(RunStateManager(run_dir).load().status, RunStatus.EXECUTING)
            pointer = ash.read_active_pointer(base)
            self.assertEqual(pointer["selected_work_id"], "WF-20260101-exec")

    def test_execute_preflights_workspace_gitignore_before_transitioning_closed_run(self):
        import tempfile, argparse
        from pathlib import Path
        from tools.workflow_cli import agent_shortcuts as ash
        from tools.workflow_cli.models import RunStatus
        from tools.workflow_cli.output import EXIT_CONFLICT
        from tools.workflow_cli.state import RunStateManager
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            run_dir = self._run(base, "WF-20260101-exec", RunStatus.CLOSED_AT_PLAN_CHECKPOINT)
            secret = base / "secret.txt"
            secret.write_text("PRIVATE\n", encoding="utf-8")
            gitignore = base / ".req-to-plan" / ".gitignore"
            gitignore.unlink()
            gitignore.symlink_to(secret)

            out, code = self._capture(ash._cmd_execute, argparse.Namespace(work_id="WF-20260101-exec"), base)

            self.assertEqual(code, EXIT_CONFLICT)
            self.assertIn("unsafe_workspace_gitignore", out)
            self.assertEqual(RunStateManager(run_dir).load().status, RunStatus.CLOSED_AT_PLAN_CHECKPOINT)
            self.assertFalse((run_dir / "execution" / "progress.md").exists())
            self.assertEqual(secret.read_text(encoding="utf-8"), "PRIVATE\n")

    def test_execute_json_mode_start_emits_single_payload(self):
        import tempfile, argparse
        from pathlib import Path
        from tools.workflow_cli import agent_shortcuts as ash
        from tools.workflow_cli.models import RunStatus
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            run_dir = self._run(base, "WF-20260101-exec", RunStatus.CLOSED_AT_PLAN_CHECKPOINT)
            with patch.dict(os.environ, {"R2P_JSON": "1"}):
                out, code = self._capture(
                    ash._cmd_execute,
                    argparse.Namespace(work_id="WF-20260101-exec"),
                    base,
                )

            self.assertEqual(code, 0)
            payload = json.loads(out)
            self.assertEqual(payload["status"], "stop")
            self.assertEqual(payload["reason"], "execute_plan")
            self.assertEqual(payload["work_id"], "WF-20260101-exec")
            self.assertEqual(payload["plan"], str(run_dir / "07-plan.md"))
            self.assertEqual(payload["ledger"], str(run_dir / "execution" / "progress.md"))
            self.assertIn("r2p-archive --work-id WF-20260101-exec", payload["next"])

    def test_execute_explicit_work_id_overrides_different_active_pointer(self):
        import tempfile, argparse
        from pathlib import Path
        from tools.workflow_cli import agent_shortcuts as ash
        from tools.workflow_cli.models import RunStatus
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            self._run(base, "WF-20260101-target", RunStatus.CLOSED_AT_PLAN_CHECKPOINT)
            self._run(base, "WF-20260101-other", RunStatus.CLOSED_AT_PLAN_CHECKPOINT)
            ash.write_active_pointer(base, "WF-20260101-other", reason="test")

            out, code = self._capture(ash._cmd_execute, argparse.Namespace(work_id="WF-20260101-target"), base)

            self.assertEqual(code, 0)
            self.assertIn("r2p-archive --work-id WF-20260101-target", out)
            pointer = ash.read_active_pointer(base)
            self.assertEqual(pointer["selected_work_id"], "WF-20260101-target")

    def test_execute_on_executing_prints_resume(self):
        import tempfile, argparse
        from pathlib import Path
        from tools.workflow_cli import agent_shortcuts as ash
        from tools.workflow_cli.models import RunStatus
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            run_dir = self._run(base, "WF-20260101-exec", RunStatus.EXECUTING)
            out, code = self._capture(ash._cmd_execute, argparse.Namespace(work_id="WF-20260101-exec"), base)
            self.assertIn("stop: resume_execution", out)
            self.assertIn(f"plan: {run_dir / '07-plan.md'}\n", out)
            self.assertIn(f"ledger: {run_dir / 'execution' / 'progress.md'}\n", out)
            self.assertIn("r2p-archive --work-id WF-20260101-exec", out)

    def test_execute_resume_bootstraps_missing_metrics_for_legacy_ledger(self):
        import tempfile
        from pathlib import Path
        from tools.workflow_cli import agent_shortcuts as ash
        from tools.workflow_cli.models import RunStatus
        from tools.workflow_cli.execution_metrics import parse_metrics

        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            work_id = "WF-20260101-missing-metrics"
            run_dir = self._run(base, work_id, RunStatus.EXECUTING)
            (run_dir / "execution" / "metrics.md").unlink()

            out, code = self._capture(
                ash._cmd_execute,
                argparse.Namespace(work_id=work_id),
                base,
            )

            self.assertEqual(code, 0)
            self.assertIn("stop: resume_execution", out)
            parsed = parse_metrics(
                (run_dir / "execution" / "metrics.md").read_text(
                    encoding="utf-8"
                )
            )
            self.assertFalse(parsed.header["instrumentation_complete"])
            self.assertEqual(
                parsed.header["bootstrap_gap"],
                "legacy_metrics_start_task_001",
            )

    def test_execute_resume_rejects_symlinked_run_dir(self):
        import tempfile, argparse
        from pathlib import Path
        from tools.workflow_cli import agent_shortcuts as ash
        from tools.workflow_cli.artifact import write_artifact
        from tools.workflow_cli.models import RunStatus, Stage, WorkId
        from tools.workflow_cli.output import EXIT_CONFLICT
        from tools.workflow_cli.state import RunStateManager, create_run_record

        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            work_id = "WF-20260101-exec"
            outside = base / "outside-run"
            outside.mkdir()
            rec = create_run_record(WorkId(work_id))
            rec.status = RunStatus.EXECUTING
            rec.current_stage = Stage.CLOSED
            write_artifact(
                outside,
                Stage.PLAN,
                "# Plan\n\n## Tasks\n### PLAN-TASK-001: t\n",
                version=1,
                status="approved",
            )
            RunStateManager(outside).save(rec)
            run_link = base / ".req-to-plan" / work_id
            run_link.parent.mkdir(parents=True)
            run_link.symlink_to(outside, target_is_directory=True)

            out, code = self._capture(
                ash._cmd_execute,
                argparse.Namespace(work_id=work_id),
                base,
            )

            self.assertEqual(code, EXIT_CONFLICT)
            self.assertIn("symlink", out.lower())
            self.assertNotIn("resume_execution", out)
            self.assertIsNone(ash.read_active_pointer(base))
            self.assertTrue(run_link.is_symlink())

    def test_execute_blocks_symlinked_run_record(self):
        import tempfile, argparse
        from pathlib import Path
        from tools.workflow_cli import agent_shortcuts as ash
        from tools.workflow_cli.models import RunStatus
        from tools.workflow_cli.output import EXIT_CONFLICT

        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            work_id = "WF-20260101-exec"
            run_dir = self._run(base, work_id, RunStatus.CLOSED_AT_PLAN_CHECKPOINT)
            run_md = run_dir / "run.md"
            content = run_md.read_text(encoding="utf-8")
            run_md.unlink()
            outside = base / "outside-run.md"
            outside.write_text(content, encoding="utf-8")
            run_md.symlink_to(outside)

            out, code = self._capture(
                ash._cmd_execute,
                argparse.Namespace(work_id=work_id),
                base,
            )

            self.assertEqual(code, EXIT_CONFLICT)
            self.assertIn("blocked: unsafe_run_record", out)
            self.assertIn(f"work_id: {work_id}", out)
            self.assertTrue(run_md.is_symlink())

    def test_execute_json_mode_resume_emits_single_payload(self):
        import tempfile, argparse
        from pathlib import Path
        from tools.workflow_cli import agent_shortcuts as ash
        from tools.workflow_cli.models import RunStatus
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            run_dir = self._run(base, "WF-20260101-exec", RunStatus.EXECUTING)
            with patch.dict(os.environ, {"R2P_JSON": "1"}):
                out, code = self._capture(
                    ash._cmd_execute,
                    argparse.Namespace(work_id="WF-20260101-exec"),
                    base,
                )

            self.assertEqual(code, 0)
            payload = json.loads(out)
            self.assertEqual(payload["status"], "stop")
            self.assertEqual(payload["reason"], "resume_execution")
            self.assertEqual(payload["work_id"], "WF-20260101-exec")
            self.assertEqual(payload["plan"], str(run_dir / "07-plan.md"))
            self.assertEqual(payload["ledger"], str(run_dir / "execution" / "progress.md"))
            self.assertIn("r2p-archive --work-id WF-20260101-exec", payload["next"])

    def test_continue_routes_executing_to_resume(self):
        import tempfile, argparse
        from pathlib import Path
        from tools.workflow_cli import agent_shortcuts as ash
        from tools.workflow_cli.models import RunStatus
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            self._run(base, "WF-20260101-exec", RunStatus.EXECUTING)
            out, _ = self._capture(ash._cmd_continue, argparse.Namespace(), base)
            self.assertIn("resume_execution", out)

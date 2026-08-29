"""Black-box checks for the public ``r2p-context-view`` wrapper."""
from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
from pathlib import Path

from tools.workflow_cli.install import InstallService, _render_bin_script
from tools.workflow_cli.models import RunStatus, Stage, WorkId
from tools.workflow_cli.state import RunStateManager, create_run_record


REPO_ROOT = Path(__file__).parent.parent
WRAPPER = REPO_ROOT / "tools" / "r2p-context-view"
WORK_ID = WorkId("WF-20260830-context-wrapper")
SOURCES = (
    "02-project-context.md",
    "03-requirement-brief.md",
    "04-risk-discovery.md",
    "05-design.md",
    "06-spec.md",
    "execution/progress.md",
)


def _make_workspace(base: Path) -> None:
    run_dir = base / ".req-to-plan" / str(WORK_ID)
    (run_dir / "execution").mkdir(parents=True)
    record = create_run_record(WORK_ID)
    record.status = RunStatus.EXECUTING
    record.current_stage = Stage.CLOSED
    RunStateManager(run_dir).save(record)
    for source in SOURCES:
        target = run_dir / source
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(f"content for {source}\n", encoding="utf-8")


def _run_wrapper(base: Path, *, json_mode: bool = False) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    if json_mode:
        environment["R2P_JSON"] = "1"
    else:
        environment.pop("R2P_JSON", None)
    return subprocess.run(
        [str(WRAPPER), "--base-path", str(base), "--work-id", str(WORK_ID)],
        text=True,
        capture_output=True,
        check=False,
        env=environment,
    )


def test_wrapper_forwards_to_context_view_with_human_and_json_output(tmp_path):
    _make_workspace(tmp_path)

    human = _run_wrapper(tmp_path)
    payload = _run_wrapper(tmp_path, json_mode=True)

    assert human.returncode == 0, human.stderr
    assert human.stdout.startswith("===== 02-project-context.md =====\n")
    assert "===== execution/progress.md =====" in human.stdout
    assert payload.returncode == 0, payload.stderr
    assert json.loads(payload.stdout)["status"] == "ok"
    assert json.loads(payload.stdout)["work_id"] == str(WORK_ID)


def _write_fake_python(directory: Path, name: str, exit_code: int) -> Path:
    executable = directory / name
    executable.write_text(
        "#!/bin/sh\n"
        'printf "%s\\n" "$@" > "$R2P_WRAPPER_CAPTURE"\n'
        f"exit {exit_code}\n",
        encoding="utf-8",
    )
    executable.chmod(executable.stat().st_mode | stat.S_IXUSR)
    return executable


def _provide_wrapper_path_dependencies(directory: Path) -> None:
    dirname = shutil.which("dirname")
    assert dirname is not None
    (directory / "dirname").symlink_to(dirname)


def test_wrapper_prefers_python3_forwards_args_and_propagates_exit(tmp_path):
    capture = tmp_path / "captured.txt"
    _write_fake_python(tmp_path, "python3", 41)
    _provide_wrapper_path_dependencies(tmp_path)
    environment = os.environ.copy()
    environment["PATH"] = str(tmp_path)
    environment["R2P_WRAPPER_CAPTURE"] = str(capture)

    completed = subprocess.run(
        ["/bin/bash", str(WRAPPER), "--work-id", "WF-20260830-context-wrapper", "--extra"],
        text=True,
        capture_output=True,
        check=False,
        env=environment,
    )

    assert completed.returncode == 41
    assert capture.read_text(encoding="utf-8").splitlines() == [
        "-E",
        str(REPO_ROOT / "tools" / "workflow_cli" / "__main__.py"),
        "tools.workflow_cli",
        "context-view",
        "--work-id",
        "WF-20260830-context-wrapper",
        "--extra",
    ]


def test_wrapper_falls_back_to_python_when_python3_is_unavailable(tmp_path):
    capture = tmp_path / "captured.txt"
    _write_fake_python(tmp_path, "python", 37)
    _provide_wrapper_path_dependencies(tmp_path)
    environment = os.environ.copy()
    environment["PATH"] = str(tmp_path)
    environment["R2P_WRAPPER_CAPTURE"] = str(capture)

    completed = subprocess.run(
        ["/bin/bash", str(WRAPPER), "--work-id", "WF-20260830-context-wrapper"],
        text=True,
        capture_output=True,
        check=False,
        env=environment,
    )

    assert completed.returncode == 37
    assert capture.read_text(encoding="utf-8").splitlines()[:4] == [
        "-E",
        str(REPO_ROOT / "tools" / "workflow_cli" / "__main__.py"),
        "tools.workflow_cli",
        "context-view",
    ]


def test_installed_script_rendering_quotes_a_repo_path_with_spaces():
    source = (
        '#!/usr/bin/env bash\n'
        'SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"\n'
        'REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"\n'
        'exec python3 -E "$REPO_ROOT/tools/workflow_cli/__main__.py" '
        'tools.workflow_cli context-view "$@"\n'
    )

    rendered = _render_bin_script(source, Path("/tmp/a repo with spaces"))

    assert "REPO_ROOT='/tmp/a repo with spaces'" in rendered
    assert 'tools.workflow_cli context-view "$@"' in rendered


def test_install_discovers_and_renders_the_context_view_wrapper(tmp_path):
    manifest_root = tmp_path / "manifest"
    platform_root = tmp_path / "platforms"
    service = InstallService(
        repo_root=REPO_ROOT,
        manifest_root=manifest_root,
        platform_homes={name: platform_root / name for name in ("claude", "codex", "gemini", "opencode")},
    )

    service.install("codex")

    installed = manifest_root / "bin" / "r2p-context-view"
    assert installed.is_file()
    assert os.access(installed, os.X_OK)
    content = installed.read_text(encoding="utf-8")
    assert f"REPO_ROOT={REPO_ROOT}" in content
    assert 'tools.workflow_cli context-view "$@"' in content

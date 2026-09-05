from __future__ import annotations

import os
from pathlib import Path
import stat

import pytest

from tools.workflow_cli.execution_context import (
    CONTEXT_SOURCE_PATHS,
    ContextSourceNotFoundError,
    ContextViewError,
    UnsafeContextSourceError,
    build_context_view,
)
from tools.workflow_cli.models import RunStatus, Stage, WorkId
from tools.workflow_cli.state import RunStateManager, create_run_record


WORK_ID = WorkId("WF-20260830-context-view")


def _make_workspace(
    base: Path,
    *,
    source_text: dict[str, str] | None = None,
    status: RunStatus = RunStatus.EXECUTING,
    embedded_work_id: WorkId = WORK_ID,
) -> Path:
    run_dir = base / ".req-to-plan" / str(WORK_ID)
    execution_dir = run_dir / "execution"
    execution_dir.mkdir(parents=True)

    record = create_run_record(embedded_work_id)
    record.status = status
    record.current_stage = Stage.CLOSED
    RunStateManager(run_dir).save(record)

    values = {
        path: f"content for {path}\n"
        for path in CONTEXT_SOURCE_PATHS
    }
    if source_text:
        values.update(source_text)
    for relative_path, text in values.items():
        destination = run_dir / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(text, encoding="utf-8")
    return run_dir


def test_build_context_view_has_exact_order_filtering_separators_and_bytes(tmp_path):
    raw_by_path = {
        "02-project-context.md": "# Project\n你好 <!-- hidden -->\n\n",
        "03-requirement-brief.md": (
            "## Keep\nvisible\n"
            "## Upstream Summary (read-only)\nsecret\n<!-- /r2p-read-only -->\n"
        ),
        "04-risk-discovery.md": "```md\n<!-- fenced -->\n```\n",
        "05-design.md": " \n\t\n",
        "06-spec.md": "spec\n\n",
        "execution/progress.md": "progress\n",
    }
    _make_workspace(tmp_path, source_text=raw_by_path)

    view = build_context_view(tmp_path, WORK_ID)

    semantic_by_path = {
        "02-project-context.md": "# Project\n你好",
        "03-requirement-brief.md": "## Keep\nvisible",
        "04-risk-discovery.md": "```md\n<!-- fenced -->\n```",
        "05-design.md": "",
        "06-spec.md": "spec",
        "execution/progress.md": "progress",
    }
    expected_content = "\n\n".join(
        f"===== {path} =====\n{semantic_by_path[path]}"
        for path in CONTEXT_SOURCE_PATHS
    ) + "\n"

    assert view.work_id == str(WORK_ID)
    assert tuple(source.path for source in view.sources) == CONTEXT_SOURCE_PATHS
    assert view.content == expected_content
    assert view.raw_bytes == sum(
        len(raw_by_path[path].encode("utf-8")) for path in CONTEXT_SOURCE_PATHS
    )
    assert view.semantic_bytes == len(expected_content.encode("utf-8"))
    assert tuple(source.raw_bytes for source in view.sources) == tuple(
        len(raw_by_path[path].encode("utf-8")) for path in CONTEXT_SOURCE_PATHS
    )
    assert tuple(source.semantic_bytes for source in view.sources) == tuple(
        len(semantic_by_path[path].encode("utf-8")) for path in CONTEXT_SOURCE_PATHS
    )
    assert view.content.endswith("\n") and not view.content.endswith("\n\n")


def test_whitespace_only_source_is_retained_as_an_empty_semantic_chunk(tmp_path):
    _make_workspace(tmp_path, source_text={"05-design.md": " \t\r\n\n"})

    view = build_context_view(tmp_path, WORK_ID)

    source = next(item for item in view.sources if item.path == "05-design.md")
    assert source.raw_bytes == len(" \t\r\n\n".encode("utf-8"))
    assert source.semantic_bytes == 0
    assert "===== 05-design.md =====\n\n\n===== 06-spec.md =====" in view.content


def test_directory_and_file_opens_use_required_no_follow_nonblocking_flags(tmp_path, monkeypatch):
    _make_workspace(tmp_path)
    real_open = os.open
    calls: list[tuple[str, int, int | None]] = []

    def recording_open(path, flags, mode=0o777, *, dir_fd=None):
        calls.append((os.fspath(path), flags, dir_fd))
        return real_open(path, flags, mode, dir_fd=dir_fd)

    monkeypatch.setattr("tools.workflow_cli.execution_context.os.open", recording_open)
    build_context_view(tmp_path, WORK_ID)

    directory_names = {tmp_path.anchor, *tmp_path.parts[1:], ".req-to-plan", str(WORK_ID), "execution"}
    directory_calls = [call for call in calls if call[0] in directory_names]
    file_calls = [call for call in calls if call[0] in {"run.md", *(Path(p).name for p in CONTEXT_SOURCE_PATHS)}]
    assert directory_calls
    assert file_calls
    for _, flags, _ in directory_calls:
        assert flags & os.O_DIRECTORY
        assert flags & os.O_NOFOLLOW
        assert flags & os.O_NONBLOCK
    for _, flags, _ in file_calls:
        assert not flags & os.O_DIRECTORY
        assert flags & os.O_NOFOLLOW
        assert flags & os.O_NONBLOCK


@pytest.mark.parametrize("kind", ["symlink", "directory", "fifo", "device"])
def test_rejects_non_regular_source_without_blocking(tmp_path, monkeypatch, kind):
    run_dir = _make_workspace(tmp_path)
    source = run_dir / "04-risk-discovery.md"
    source.unlink()

    if kind == "symlink":
        source.symlink_to(run_dir / "03-requirement-brief.md")
    elif kind == "directory":
        source.mkdir()
    elif kind == "fifo":
        os.mkfifo(source)
    else:
        source.write_text("regular", encoding="utf-8")
        real_stat = os.stat

        def device_stat(path, *args, **kwargs):
            result = real_stat(path, *args, **kwargs)
            if path == "04-risk-discovery.md" and kwargs.get("dir_fd") is not None:
                values = list(result)
                values[0] = stat.S_IFCHR | 0o600
                return os.stat_result(values)
            return result

        monkeypatch.setattr("tools.workflow_cli.execution_context.os.stat", device_stat)

    with pytest.raises(UnsafeContextSourceError):
        build_context_view(tmp_path, WORK_ID)


def test_rejects_execution_directory_symlink(tmp_path):
    run_dir = _make_workspace(tmp_path)
    real_execution = run_dir / "real-execution"
    (run_dir / "execution").rename(real_execution)
    (run_dir / "execution").symlink_to(real_execution, target_is_directory=True)

    with pytest.raises(UnsafeContextSourceError):
        build_context_view(tmp_path, WORK_ID)


def test_rejects_regular_file_replaced_between_pre_stat_and_open(tmp_path, monkeypatch):
    run_dir = _make_workspace(tmp_path)
    target = run_dir / "04-risk-discovery.md"
    replacement = run_dir / "replacement.md"
    replacement.write_text("replacement\n", encoding="utf-8")
    # Keep both files alive so the filesystem cannot recycle the target inode.
    assert replacement.stat().st_ino != target.stat().st_ino
    real_open = os.open
    swapped = False

    def racing_open(path, flags, mode=0o777, *, dir_fd=None):
        nonlocal swapped
        if path == "04-risk-discovery.md" and dir_fd is not None and not swapped:
            swapped = True
            replacement.replace(target)
        return real_open(path, flags, mode, dir_fd=dir_fd)

    monkeypatch.setattr("tools.workflow_cli.execution_context.os.open", racing_open)
    with pytest.raises(UnsafeContextSourceError, match="identity changed"):
        build_context_view(tmp_path, WORK_ID)


def test_raced_in_fifo_is_rejected_without_blocking(tmp_path, monkeypatch):
    run_dir = _make_workspace(tmp_path)
    target = run_dir / "04-risk-discovery.md"
    real_open = os.open
    swapped = False

    def racing_open(path, flags, mode=0o777, *, dir_fd=None):
        nonlocal swapped
        if path == "04-risk-discovery.md" and dir_fd is not None and not swapped:
            swapped = True
            target.unlink()
            os.mkfifo(target)
        return real_open(path, flags, mode, dir_fd=dir_fd)

    monkeypatch.setattr("tools.workflow_cli.execution_context.os.open", racing_open)
    with pytest.raises(UnsafeContextSourceError):
        build_context_view(tmp_path, WORK_ID)


@pytest.mark.parametrize("replacement_level", ["workspace", "run"])
def test_pinned_run_tree_survives_parent_replacement_without_switching(
    tmp_path, monkeypatch, replacement_level
):
    original_run = _make_workspace(
        tmp_path,
        source_text={path: f"original {path}\n" for path in CONTEXT_SOURCE_PATHS},
    )
    workspace = tmp_path / ".req-to-plan"
    replacement_root = tmp_path / "replacement"
    replacement_run = _make_workspace(
        replacement_root,
        source_text={path: f"replacement {path}\n" for path in CONTEXT_SOURCE_PATHS},
    )
    real_read = __import__("tools.workflow_cli.execution_context", fromlist=["_read_text_at"])._read_text_at
    replaced = False

    def replacing_read(parent_fd, name):
        nonlocal replaced
        text = real_read(parent_fd, name)
        if name == "run.md" and not replaced:
            replaced = True
            if replacement_level == "workspace":
                workspace.rename(tmp_path / ".req-to-plan-original")
                (replacement_root / ".req-to-plan").rename(workspace)
            else:
                original_run.rename(tmp_path / "original-run")
                replacement_run.rename(workspace / str(WORK_ID))
        return text

    monkeypatch.setattr("tools.workflow_cli.execution_context._read_text_at", replacing_read)
    view = build_context_view(tmp_path, WORK_ID)

    if replacement_level == "workspace":
        assert (tmp_path / ".req-to-plan-original" / str(WORK_ID)).exists()
    else:
        assert (tmp_path / "original-run").exists()
    assert replacement_run.exists() is False
    assert "original 02-project-context.md" in view.content
    assert "replacement 02-project-context.md" not in view.content


def test_run_record_is_validated_from_same_pinned_handle(tmp_path):
    other = WorkId("WF-20260830-other-context")
    _make_workspace(tmp_path, embedded_work_id=other)

    with pytest.raises(UnsafeContextSourceError, match="work_id"):
        build_context_view(tmp_path, WORK_ID)


def test_only_executing_run_is_accepted(tmp_path):
    run_dir = _make_workspace(tmp_path, status=RunStatus.CLOSED_AT_PLAN_CHECKPOINT)
    (run_dir / "execution" / "progress.md").unlink()
    (run_dir / "execution").rmdir()

    with pytest.raises(ContextViewError, match="not executing"):
        build_context_view(tmp_path, WORK_ID)


def test_missing_source_is_distinct_from_unsafe_source(tmp_path):
    run_dir = _make_workspace(tmp_path)
    (run_dir / "06-spec.md").unlink()

    with pytest.raises(ContextSourceNotFoundError, match="06-spec.md"):
        build_context_view(tmp_path, WORK_ID)


def test_invalid_utf8_is_rejected(tmp_path):
    run_dir = _make_workspace(tmp_path)
    (run_dir / "06-spec.md").write_bytes(b"\xff")

    with pytest.raises(UnsafeContextSourceError, match="UTF-8"):
        build_context_view(tmp_path, WORK_ID)


def test_missing_directory_fd_capability_fails_closed(tmp_path, monkeypatch):
    _make_workspace(tmp_path)
    monkeypatch.setattr("tools.workflow_cli.execution_context._HAS_REQUIRED_CAPABILITIES", False)

    with pytest.raises(UnsafeContextSourceError, match="capability unavailable"):
        build_context_view(tmp_path, WORK_ID)


@pytest.mark.parametrize("failure_name", ["run.md", "03-requirement-brief.md", "execution"])
def test_all_opened_file_descriptors_close_on_errors(tmp_path, monkeypatch, failure_name):
    _make_workspace(tmp_path)
    module = __import__("tools.workflow_cli.execution_context", fromlist=["os"])
    real_open = os.open
    real_close = os.close
    opened: set[int] = set()
    closed: set[int] = set()

    def tracking_open(path, flags, mode=0o777, *, dir_fd=None):
        if path == failure_name:
            raise OSError("injected open failure")
        fd = real_open(path, flags, mode, dir_fd=dir_fd)
        opened.add(fd)
        return fd

    def tracking_close(fd):
        closed.add(fd)
        return real_close(fd)

    monkeypatch.setattr(module.os, "open", tracking_open)
    monkeypatch.setattr(module.os, "close", tracking_close)

    with pytest.raises((ContextViewError, OSError)):
        build_context_view(tmp_path, WORK_ID)
    assert opened <= closed

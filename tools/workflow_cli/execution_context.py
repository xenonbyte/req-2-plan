"""Pinned, deterministic construction of the execution semantic context view.

This module deliberately exposes no CLI surface.  Its private directory-fd
helpers own the fixed execution-context traversal without widening the public
single-file API in :mod:`tools.workflow_cli.atomic`.
"""
from __future__ import annotations

from dataclasses import dataclass
import errno
import os
from pathlib import Path
import re
import stat

from tools.workflow_cli.markdown import strip_nonsemantic_markdown
from tools.workflow_cli.models import RunStatus, WorkId
from tools.workflow_cli.state import parse_run_record


CONTEXT_SOURCE_PATHS = (
    "02-project-context.md",
    "03-requirement-brief.md",
    "04-risk-discovery.md",
    "05-design.md",
    "06-spec.md",
    "execution/progress.md",
)


class ContextViewError(ValueError):
    """The requested semantic context view cannot be constructed."""


class ContextSourceNotFoundError(ContextViewError):
    """A required run directory or context source is missing."""


class UnsafeContextSourceError(ContextViewError):
    """A required path or platform capability is unsafe for trusted input."""


@dataclass(frozen=True)
class ContextSource:
    path: str
    raw_bytes: int
    semantic_bytes: int


@dataclass(frozen=True)
class ContextView:
    work_id: str
    sources: tuple[ContextSource, ...]
    raw_bytes: int
    semantic_bytes: int
    content: str


_HAS_REQUIRED_CAPABILITIES = (
    all(hasattr(os, name) for name in ("O_DIRECTORY", "O_NOFOLLOW", "O_NONBLOCK"))
    and os.open in os.supports_dir_fd
    and os.stat in os.supports_dir_fd
    and os.stat in os.supports_follow_symlinks
)

_DIR_FLAGS = (
    os.O_RDONLY
    | getattr(os, "O_DIRECTORY", 0)
    | getattr(os, "O_NOFOLLOW", 0)
    | getattr(os, "O_NONBLOCK", 0)
    | getattr(os, "O_CLOEXEC", 0)
)
_FILE_READ_FLAGS = (
    os.O_RDONLY
    | getattr(os, "O_NOFOLLOW", 0)
    | getattr(os, "O_NONBLOCK", 0)
    | getattr(os, "O_CLOEXEC", 0)
)


def _require_fd_capabilities() -> None:
    if not _HAS_REQUIRED_CAPABILITIES:
        raise UnsafeContextSourceError("stable directory-fd capability unavailable")


def _validate_component(name: str, *, kind: str) -> None:
    if not isinstance(name, str) or "/" in name or name in {"", ".", ".."}:
        raise UnsafeContextSourceError(f"unsafe {kind} component")


def _translate_open_error(exc: OSError, name: str, *, kind: str) -> ContextViewError:
    if exc.errno == errno.ENOENT:
        return ContextSourceNotFoundError(f"missing {kind}: {name}")
    return UnsafeContextSourceError(f"unsafe {kind}: {name}")


def _open_absolute_dir(path: Path) -> int:
    """Pin an absolute directory by no-follow walking from its filesystem root."""
    _require_fd_capabilities()
    absolute = Path(os.path.abspath(os.fspath(path)))
    if not absolute.is_absolute():
        raise UnsafeContextSourceError("repository path must be absolute")

    fd: int | None = None
    try:
        try:
            fd = os.open(absolute.anchor, _DIR_FLAGS)
        except OSError as exc:
            raise _translate_open_error(exc, absolute.anchor, kind="directory") from exc
        for component in absolute.parts[1:]:
            _validate_component(component, kind="directory")
            try:
                next_fd = os.open(component, _DIR_FLAGS, dir_fd=fd)
            except OSError as exc:
                raise _translate_open_error(exc, component, kind="directory") from exc
            os.close(fd)
            fd = next_fd
        if not stat.S_ISDIR(os.fstat(fd).st_mode):
            raise UnsafeContextSourceError("repository path is not a directory")
        result = fd
        fd = None
        return result
    finally:
        if fd is not None:
            os.close(fd)


def _open_dir_at(parent_fd: int, name: str) -> int:
    _validate_component(name, kind="directory")
    try:
        fd = os.open(name, _DIR_FLAGS, dir_fd=parent_fd)
    except OSError as exc:
        raise _translate_open_error(exc, name, kind="directory") from exc
    try:
        if not stat.S_ISDIR(os.fstat(fd).st_mode):
            raise UnsafeContextSourceError(f"not a directory: {name}")
        result = fd
        fd = -1
        return result
    finally:
        if fd >= 0:
            os.close(fd)


def _read_text_at(parent_fd: int, name: str) -> str:
    """Read one UTF-8 regular file after a no-follow identity handshake."""
    _validate_component(name, kind="file")
    try:
        before = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    except OSError as exc:
        raise _translate_open_error(exc, name, kind="source") from exc
    if not stat.S_ISREG(before.st_mode):
        raise UnsafeContextSourceError(f"unsafe non-regular source: {name}")

    fd: int | None = None
    try:
        try:
            fd = os.open(name, _FILE_READ_FLAGS, dir_fd=parent_fd)
        except OSError as exc:
            raise _translate_open_error(exc, name, kind="source") from exc
        opened = os.fstat(fd)
        if (
            not stat.S_ISREG(opened.st_mode)
            or (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino)
        ):
            raise UnsafeContextSourceError(f"source identity changed during read: {name}")

        chunks: list[bytes] = []
        while True:
            chunk = os.read(fd, 1024 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
        try:
            return b"".join(chunks).decode("utf-8")
        except UnicodeDecodeError as exc:
            raise UnsafeContextSourceError(f"trusted source is not UTF-8: {name}") from exc
    except ContextViewError:
        raise
    except OSError as exc:
        raise UnsafeContextSourceError(f"unsafe source read: {name}") from exc
    finally:
        if fd is not None:
            os.close(fd)


def _open_run_tree(base_path: Path, work_id: WorkId) -> tuple[int, int, int]:
    repo_fd = workspace_fd = run_fd = None
    try:
        repo_fd = _open_absolute_dir(base_path)
        workspace_fd = _open_dir_at(repo_fd, ".req-to-plan")
        run_fd = _open_dir_at(workspace_fd, str(work_id))
        result = (repo_fd, workspace_fd, run_fd)
        repo_fd = workspace_fd = run_fd = None
        return result
    finally:
        for fd in (run_fd, workspace_fd, repo_fd):
            if fd is not None:
                os.close(fd)


def _record_from_pinned_run(run_fd: int, requested_work_id: WorkId):
    text = _read_text_at(run_fd, "run.md")
    match = re.search(r"^# Workflow Run: (WF-\S+)$", text, re.MULTILINE)
    if match is None:
        raise UnsafeContextSourceError("cannot parse work_id from pinned run record")
    try:
        embedded_work_id = WorkId(match.group(1))
    except ValueError as exc:
        raise UnsafeContextSourceError("pinned run record contains an invalid work_id") from exc
    if embedded_work_id != requested_work_id:
        raise UnsafeContextSourceError("pinned run record work_id does not match request")
    try:
        return parse_run_record(text, embedded_work_id)
    except (TypeError, ValueError) as exc:
        raise UnsafeContextSourceError("pinned run record is malformed") from exc


def build_context_view(base_path: Path, work_id: WorkId) -> ContextView:
    """Build the fixed six-source semantic view from one pinned run tree."""
    try:
        requested_work_id = WorkId(str(work_id))
    except ValueError as exc:
        raise ContextViewError("invalid work_id") from exc

    repo_fd = workspace_fd = run_fd = execution_fd = None
    try:
        repo_fd, workspace_fd, run_fd = _open_run_tree(
            Path(base_path), requested_work_id
        )
        record = _record_from_pinned_run(run_fd, requested_work_id)
        if record.status != RunStatus.EXECUTING:
            raise ContextViewError("run is not executing")
        execution_fd = _open_dir_at(run_fd, "execution")

        sources: list[ContextSource] = []
        chunks: list[str] = []
        for relative_path in CONTEXT_SOURCE_PATHS:
            if relative_path.startswith("execution/"):
                parent_fd = execution_fd
                name = relative_path.removeprefix("execution/")
            else:
                parent_fd = run_fd
                name = relative_path
            raw = _read_text_at(parent_fd, name)
            semantic = strip_nonsemantic_markdown(raw).rstrip()
            sources.append(
                ContextSource(
                    path=relative_path,
                    raw_bytes=len(raw.encode("utf-8")),
                    semantic_bytes=len(semantic.encode("utf-8")),
                )
            )
            chunks.append(f"===== {relative_path} =====\n{semantic}")

        content = "\n\n".join(chunks) + "\n"
        return ContextView(
            work_id=str(requested_work_id),
            sources=tuple(sources),
            raw_bytes=sum(source.raw_bytes for source in sources),
            semantic_bytes=len(content.encode("utf-8")),
            content=content,
        )
    finally:
        for fd in (execution_fd, run_fd, workspace_fd, repo_fd):
            if fd is not None:
                os.close(fd)

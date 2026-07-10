"""Safe filesystem read/write helpers."""
from __future__ import annotations

import errno
import os
import secrets
import stat
from pathlib import Path


class UnsafeRegularFileError(ValueError):
    """Raised when a trusted text input is not a stable regular file."""


def read_regular_text(
    path: Path,
    *,
    encoding: str = "utf-8",
    missing_ok: bool = False,
) -> str | None:
    """Read one regular file without following a final-component symlink.

    The lstat/fstat identity check preserves no-follow behavior on platforms
    without ``O_NOFOLLOW``. ``O_NONBLOCK`` prevents a raced-in FIFO from
    blocking before the regular-file check.
    """
    try:
        before = path.lstat()
    except FileNotFoundError:
        if missing_ok:
            return None
        raise
    if not stat.S_ISREG(before.st_mode):
        raise UnsafeRegularFileError(f"not a regular file: {path}")

    flags = os.O_RDONLY
    flags |= getattr(os, "O_NOFOLLOW", 0)
    flags |= getattr(os, "O_NONBLOCK", 0)
    flags |= getattr(os, "O_CLOEXEC", 0)
    fd: int | None = None
    try:
        fd = os.open(path, flags)
        opened = os.fstat(fd)
        if (
            not stat.S_ISREG(opened.st_mode)
            or opened.st_dev != before.st_dev
            or opened.st_ino != before.st_ino
        ):
            raise UnsafeRegularFileError(f"file changed during validation: {path}")
        with os.fdopen(fd, "r", encoding=encoding) as stream:
            fd = None
            return stream.read()
    except FileNotFoundError:
        if missing_ok:
            return None
        raise
    except OSError as exc:
        if exc.errno in (errno.ELOOP, errno.ENOTDIR):
            raise UnsafeRegularFileError(f"not a regular file: {path}") from exc
        raise
    finally:
        if fd is not None:
            os.close(fd)


def atomic_write_text(path: Path, content: str, *, encoding: str = "utf-8") -> None:
    """Write text via a unique sibling temp file, then atomically replace path.

    Guarantees atomic-replace semantics (a reader sees either the old or the new
    file, never a truncated one). It does NOT fsync — durability across power
    loss / crash is a deliberate non-goal for this CLI.
    """
    tmp_path, fd = _open_unique_sibling_tmp(path)
    try:
        with os.fdopen(fd, "w", encoding=encoding) as tmp:
            fd = -1
            tmp.write(content)
        os.replace(tmp_path, path)
        tmp_path = None
    finally:
        if fd != -1:
            os.close(fd)
        if tmp_path is not None:
            try:
                tmp_path.unlink()
            except FileNotFoundError:
                pass


def _open_unique_sibling_tmp(path: Path) -> tuple[Path, int]:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW

    last_error: FileExistsError | None = None
    for _ in range(100):
        candidate = path.with_name(
            f".{path.name}.{os.getpid()}.{secrets.token_hex(8)}.tmp"
        )
        try:
            return candidate, os.open(candidate, flags, 0o666)
        except FileExistsError as exc:
            last_error = exc

    raise FileExistsError(f"Could not create unique temp file for {path}") from last_error

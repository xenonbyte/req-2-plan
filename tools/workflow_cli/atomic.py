"""Atomic filesystem write helpers."""
from __future__ import annotations

import os
import secrets
from pathlib import Path


def atomic_write_text(path: Path, content: str, *, encoding: str = "utf-8") -> None:
    """Write text via a unique sibling temp file, then atomically replace path."""
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

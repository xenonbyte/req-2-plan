"""Tests for the isolated-launcher sys.path surgery in ``__main__``.

Under ``-E`` (used by the shell wrappers) Python still prepends the launcher
script's own directory to ``sys.path``, so ``tools/workflow_cli/`` modules such
as ``trace`` would shadow their stdlib namesakes unless the bootstrap drops it.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from tools.workflow_cli.__main__ import _sanitized_sys_path


def _sanitize(entries, repo_root, script_dir, cwd):
    return _sanitized_sys_path(
        entries,
        Path(repo_root),
        Path(script_dir).resolve(),
        Path(cwd).resolve() if cwd is not None else None,
    )


def test_repo_root_is_prepended(tmp_path):
    repo_root = tmp_path / "repo"
    stdlib = tmp_path / "stdlib"
    result = _sanitize([str(stdlib)], repo_root, tmp_path / "script", tmp_path / "cwd")
    assert result[0] == str(repo_root)


def test_script_dir_is_dropped(tmp_path):
    repo_root = tmp_path / "repo"
    script_dir = repo_root / "tools" / "workflow_cli"
    script_dir.mkdir(parents=True)
    stdlib = tmp_path / "stdlib"
    entries = [str(script_dir), str(stdlib)]

    result = _sanitize(entries, repo_root, script_dir, cwd=None)

    assert str(script_dir) not in result
    assert result == [str(repo_root), str(stdlib)]


def test_cwd_is_dropped(tmp_path):
    repo_root = tmp_path / "repo"
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    stdlib = tmp_path / "stdlib"
    entries = [str(cwd), str(stdlib)]

    result = _sanitize(entries, repo_root, tmp_path / "script", cwd)

    assert str(cwd) not in result
    assert result == [str(repo_root), str(stdlib)]


def test_empty_entries_and_repo_root_duplicate_are_removed(tmp_path):
    repo_root = tmp_path / "repo"
    stdlib = tmp_path / "stdlib"
    # An empty entry (cwd sentinel) and a pre-existing repo_root must not appear
    # twice in the result.
    entries = ["", str(repo_root), str(stdlib)]

    result = _sanitize(entries, repo_root, tmp_path / "script", cwd=None)

    assert result == [str(repo_root), str(stdlib)]


def test_retained_order_is_preserved(tmp_path):
    repo_root = tmp_path / "repo"
    a = tmp_path / "a"
    b = tmp_path / "b"
    c = tmp_path / "c"
    result = _sanitize([str(a), str(b), str(c)], repo_root, tmp_path / "s", cwd=None)
    assert result == [str(repo_root), str(a), str(b), str(c)]


def test_unresolvable_entry_is_retained(tmp_path):
    # A bogus entry whose resolve() might fail must not crash the surgery and,
    # not matching an excluded path, should be retained.
    repo_root = tmp_path / "repo"
    result = _sanitize(["\x00bad", str(tmp_path / "keep")], repo_root, tmp_path / "s", cwd=None)
    assert result[0] == str(repo_root)
    assert str(tmp_path / "keep") in result

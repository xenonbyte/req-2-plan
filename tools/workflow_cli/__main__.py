from __future__ import annotations

import importlib
import sys
from pathlib import Path


_BOOTSTRAP_TARGETS = {
    "tools.workflow_cli": ("tools.workflow_cli.cli", "main"),
    "tools.workflow_cli.agent_shortcuts": (
        "tools.workflow_cli.agent_shortcuts",
        "main",
    ),
    "tools.workflow_cli.install_cli": ("tools.workflow_cli.install_cli", "main"),
}


def _sanitized_sys_path(
    entries: list[str],
    repo_root: Path,
    script_dir: Path,
    cwd: Path | None,
) -> list[str]:
    """Put the source checkout first and drop cwd + the bootstrap script's dir.

    Under ``-E`` (unlike ``-I``/``-P``) Python still prepends the script's own
    directory to ``sys.path``. Left in place, modules under
    ``tools/workflow_cli/`` (e.g. ``trace``) would shadow stdlib. Absolute
    package imports only need ``repo_root``, so dropping both the script
    directory and the current directory is safe and keeps the isolation ``-I``
    used to provide via ``-P``.
    """
    excluded: set[Path] = {script_dir}
    if cwd is not None:
        excluded.add(cwd)
    retained: list[str] = []
    for entry in entries:
        if not entry:
            continue
        try:
            if Path(entry).resolve() in excluded:
                continue
        except (OSError, ValueError):
            pass
        if entry != str(repo_root):
            retained.append(entry)
    return [str(repo_root), *retained]


def _run_isolated_bootstrap() -> None:
    """Dispatch a trusted entrypoint when this file is executed with ``-E``.

    The shell wrappers execute this file by absolute path, so Python does not
    need to resolve the ``tools`` package before we can put the source checkout
    first on ``sys.path``.  Dropping the current directory and the script's own
    directory as a belt-and-braces measure also keeps this safe if a caller
    accidentally omits ``-E``.
    """
    if len(sys.argv) < 2 or sys.argv[1] not in _BOOTSTRAP_TARGETS:
        allowed = ", ".join(sorted(_BOOTSTRAP_TARGETS))
        raise SystemExit(f"bootstrap target required; allowed: {allowed}")

    target = sys.argv[1]
    here = Path(__file__).resolve()
    repo_root = here.parents[2]
    try:
        cwd = Path.cwd().resolve()
    except OSError:
        cwd = None

    sys.path[:] = _sanitized_sys_path(sys.path, repo_root, here.parent, cwd)

    module_name, function_name = _BOOTSTRAP_TARGETS[target]
    sys.argv = [target, *sys.argv[2:]]
    entrypoint = getattr(importlib.import_module(module_name), function_name)
    entrypoint()


if __name__ == "__main__":
    if __package__:
        # Preserve the documented ``python -m tools.workflow_cli`` entrypoint.
        from tools.workflow_cli.cli import main

        main()
    else:
        _run_isolated_bootstrap()

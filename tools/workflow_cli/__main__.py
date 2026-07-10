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


def _run_isolated_bootstrap() -> None:
    """Dispatch a trusted entrypoint when this file is executed with ``-I``.

    The shell wrappers execute this file by absolute path, so Python does not
    need to resolve the ``tools`` package before we can put the source checkout
    first on ``sys.path``.  Removing the current directory as a belt-and-braces
    measure also keeps this safe if a caller accidentally omits ``-I``.
    """
    if len(sys.argv) < 2 or sys.argv[1] not in _BOOTSTRAP_TARGETS:
        allowed = ", ".join(sorted(_BOOTSTRAP_TARGETS))
        raise SystemExit(f"bootstrap target required; allowed: {allowed}")

    target = sys.argv[1]
    repo_root = Path(__file__).resolve().parents[2]
    try:
        cwd = Path.cwd().resolve()
    except OSError:
        cwd = None

    retained: list[str] = []
    for entry in sys.path:
        if not entry:
            continue
        try:
            if cwd is not None and Path(entry).resolve() == cwd:
                continue
        except OSError:
            pass
        if entry != str(repo_root):
            retained.append(entry)
    sys.path[:] = [str(repo_root), *retained]

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

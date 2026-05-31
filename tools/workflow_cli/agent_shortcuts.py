"""
Agent shortcut dispatcher for r2p-* commands.

Usage:
    python3 -m tools.workflow_cli.agent_shortcuts <subcommand> [flags]
"""
from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from tools.workflow_cli.models import RunStatus

ACTIVE_POINTER_FILE = ".workflow-active"


# ---------------------------------------------------------------------------
# Active pointer helpers
# ---------------------------------------------------------------------------


def _pointer_path(base_path: Path) -> Path:
    return base_path / ".req-to-plan" / ACTIVE_POINTER_FILE


def read_active_pointer(base_path: Path) -> dict | None:
    path = _pointer_path(base_path)
    if not path.exists():
        return None
    data: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if ": " in line:
            k, _, v = line.partition(": ")
            data[k.strip()] = v.strip()
    return data if data else None


def write_active_pointer(base_path: Path, work_id: str, reason: str = "workflow_start") -> None:
    path = _pointer_path(base_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    run_rel = f".req-to-plan/{work_id}/run.md"
    updated_at = datetime.now(timezone.utc).astimezone().isoformat()
    content = (
        f"selected_work_id: {work_id}\n"
        f"selected_run: {run_rel}\n"
        f"updated_at: {updated_at}\n"
        f"reason: {reason}\n"
    )
    path.write_text(content, encoding="utf-8")


# ---------------------------------------------------------------------------
# Open run scanner
# ---------------------------------------------------------------------------


def scan_open_runs(base_path: Path) -> list[str]:
    r2p_dir = base_path / ".req-to-plan"
    if not r2p_dir.exists():
        return []
    open_ids: list[str] = []
    for run_md in sorted(r2p_dir.glob("*/run.md")):
        try:
            from tools.workflow_cli.state import RunStateManager
            mgr = RunStateManager(run_md.parent)
            record = mgr.load()
            if not is_terminal(record.status):
                open_ids.append(run_md.parent.name)
        except Exception as e:
            print(f"warning: could not load run {run_md.parent.name!r}: {e}", file=sys.stderr)
    return open_ids


# ---------------------------------------------------------------------------
# Work ID generation
# ---------------------------------------------------------------------------

_STOP_WORDS = frozenset(
    {
        "a", "an", "the", "and", "or", "but", "for", "of", "in", "on", "to",
        "at", "by", "with", "from", "as", "is", "it", "be", "are", "was",
        "were", "that", "this", "we", "our", "should", "will", "can", "do",
    }
)


def generate_work_id(
    requirement: str,
    base_path: Path | None = None,
    today: str | None = None,
) -> str:
    date_str = today or datetime.now().strftime("%Y%m%d")
    prefix = f"WF-{date_str}-"
    max_slug_len = 48 - len(prefix)

    slug = re.sub(r"[^a-zA-Z0-9\s]", " ", requirement).lower().strip()
    words = [w for w in slug.split() if w not in _STOP_WORDS and len(w) > 1]
    if not words:
        words = [w for w in slug.split() if w]
    if not words:
        import hashlib
        h = hashlib.md5(requirement.encode()).hexdigest()[:8]
        words = [f"run-{h}"]

    candidate = "-".join(words[:5])
    candidate = re.sub(r"-+", "-", candidate).strip("-")[:max_slug_len]
    if len(candidate) < 2:
        import hashlib
        h = hashlib.md5(requirement.encode()).hexdigest()[:8]
        candidate = f"run-{h}"

    base_id = f"{prefix}{candidate}"

    if base_path is None:
        return base_id

    if not (base_path / ".req-to-plan" / base_id).exists():
        return base_id

    for n in range(2, 100):
        suffix = f"-{n}"
        alt = f"{prefix}{candidate[:max_slug_len - len(suffix)]}{suffix}"
        if not (base_path / ".req-to-plan" / alt).exists():
            return alt

    raise RuntimeError(
        f"Could not generate a unique work ID for {base_id!r} after 98 attempts. "
        "Clean up old runs in .req-to-plan/ before starting a new one."
    )


# ---------------------------------------------------------------------------
# Terminal check
# ---------------------------------------------------------------------------


def is_terminal(status: RunStatus) -> bool:
    return status == RunStatus.CLOSED_AT_PLAN_CHECKPOINT


# ---------------------------------------------------------------------------
# Internal CLI runner
# ---------------------------------------------------------------------------


def _run_cli(args_list: list[str], base_path: Path) -> int:
    from tools.workflow_cli.cli import main as cli_main
    try:
        cli_main(["--base-path", str(base_path)] + args_list)
        return 0
    except SystemExit as exc:
        code = exc.code
        return int(code) if isinstance(code, int) else (1 if code else 0)


# ---------------------------------------------------------------------------
# Subcommand handlers
# ---------------------------------------------------------------------------


def _cmd_start(ns: argparse.Namespace, base_path: Path) -> None:
    pointer = read_active_pointer(base_path)
    open_runs = scan_open_runs(base_path)

    if not ns.separate:
        if pointer and pointer.get("selected_work_id") in open_runs:
            active_id = pointer["selected_work_id"]
            print(f"blocked: active_run_exists\nactive_run: {active_id}\nnext: r2p-continue\n")
            sys.exit(1)
        if len(open_runs) == 1:
            print(f"blocked: open_run_exists\nopen_run: {open_runs[0]}\nnext: r2p-switch --work-id {open_runs[0]}\n")
            sys.exit(1)
        if len(open_runs) > 1:
            ids = ", ".join(open_runs)
            print(f"blocked: open_runs_exist\nopen_runs: {ids}\nnext: r2p-switch --work-id <id>\n")
            sys.exit(1)

    work_id = generate_work_id(ns.requirement, base_path)
    exit_code = _run_cli(
        ["run-start", "--work-id", work_id, "--requirement", ns.requirement],
        base_path,
    )
    if exit_code != 0:
        sys.exit(exit_code)

    write_active_pointer(base_path, work_id, reason="workflow_start")
    print(
        f"created: .req-to-plan/{work_id}/run.md\n"
        f"selected_run: .req-to-plan/{work_id}/run.md\n"
        f"next: r2p-continue\n"
    )


def _cmd_continue(ns: argparse.Namespace, base_path: Path) -> None:
    pointer = read_active_pointer(base_path)
    if not pointer:
        print("no_selected_run: true\nnext: r2p-status --all\n")
        sys.exit(1)
    work_id = pointer["selected_work_id"]
    run_path = base_path / ".req-to-plan" / work_id / "run.md"
    if not run_path.exists():
        print(f"blocked: source_run_not_found\nwork_id: {work_id}\n")
        sys.exit(7)

    from tools.workflow_cli.artifact import read_artifact
    from tools.workflow_cli.state import RunStateManager, get_active_artifact
    from tools.workflow_cli.models import RunStatus, Stage
    manager = RunStateManager(run_path.parent)

    while True:
        record = manager.load()
        s = record.status
        stage = record.current_stage.value

        if s == RunStatus.CLOSED_AT_PLAN_CHECKPOINT:
            print(f"done: run_closed\nwork_id: {work_id}\nplan: 07-plan.md\n"
                  "next: hand the PLAN to your executor\n")
            sys.exit(0)

        if s == RunStatus.ACTIVE_STAGE_DRAFT:
            if record.tier_locked is None:
                print(f"stop: tier_not_locked\nnext: r2p tier-lock\n")
                sys.exit(0)
            aa = get_active_artifact(record, record.current_stage)
            try:
                body = read_artifact(run_path.parent, record.current_stage).strip()
            except FileNotFoundError:
                body = ""
            if aa is None or not body:
                print(f"stop: needs_content\nstage: {stage}\n"
                      f"next: produce {stage} content\n")
                sys.exit(0)
            if aa.status != "ready":
                print(f"stop: needs_ready\nstage: {stage}\n"
                      f"next: review the artifact, then stage-ready --stage {stage}\n")
                sys.exit(0)
            code = _run_cli(["gate-quality", "--work-id", work_id, "--stage", stage], base_path)
            if code != 0:
                sys.exit(code)
            continue  # reload and run review-checkpoint before stopping for human approval

        if s == RunStatus.READY_FOR_CHECKPOINT_REVIEW:
            code = _run_cli(["review-checkpoint", "--work-id", work_id, "--stage", stage], base_path)
            if code != 0:
                sys.exit(code)
            print(f"stop: needs_human_approval\nstage: {stage}\n"
                  f"next: checkpoint-decide --stage {stage} --decision approved --confirm "
                  "(or --decision changes_requested)\n")
            sys.exit(0)

        if s == RunStatus.CHECKPOINT_REVIEW:
            print(f"stop: needs_human_approval\nstage: {stage}\n"
                  f"next: checkpoint-decide --stage {stage} --decision approved --confirm\n")
            sys.exit(0)

        if s == RunStatus.CHECKPOINT_APPROVED:
            if record.current_stage == Stage.PLAN:
                code = _run_cli(["run-close", "--work-id", work_id], base_path)
                if code == 0:
                    print("done: closing\nplan: 07-plan.md\nnext: hand the PLAN to your executor\n")
                sys.exit(code)
            code = _run_cli(["stage-advance", "--work-id", work_id], base_path)
            if code != 0:
                sys.exit(code)
            continue  # reload and run the NEXT_STAGE entry gate in the same continue call

        if s == RunStatus.NEXT_STAGE:
            code = _run_cli(["gate-entry", "--work-id", work_id, "--stage", stage], base_path)
            if code != 0:
                print(f"stop: entry_gate_failed\nstage: {stage}\nnext: repair upstream and rerun gate-entry\n")
                sys.exit(code)
            print(f"stop: entered_stage\nstage: {stage}\nnext: produce {stage} content\n")
            sys.exit(0)

        if s == RunStatus.ENTRY_GATE_FAILED:
            print(f"stop: entry_gate_failed\nstage: {stage}\n"
                  f"next: repair upstream checkpoints, then gate-entry --stage {stage}\n")
            sys.exit(0)

        if s in (RunStatus.QUALITY_GATE_FAILED, RunStatus.CHECKPOINT_CHANGES_REQUESTED):
            print(f"stop: needs_repair\nstatus: {s.value}\nstage: {stage}\n"
                  f"next: address the issue, then stage-update --stage {stage}\n")
            sys.exit(0)

        # Fallback: read-only resume context.
        code = _run_cli(["run-resume", "--work-id", work_id], base_path)
        sys.exit(code)


def _cmd_status(ns: argparse.Namespace, base_path: Path) -> None:
    if ns.all:
        r2p_dir = base_path / ".req-to-plan"
        if not r2p_dir.exists():
            print("no_runs: true\n")
            sys.exit(0)
        for run_md in sorted(r2p_dir.glob("*/run.md")):
            work_id = run_md.parent.name
            _run_cli(["status-run", "--work-id", work_id], base_path)
        sys.exit(0)

    pointer = read_active_pointer(base_path)
    if not pointer:
        print("no_selected_run: true\nnext: r2p-status --all\n")
        sys.exit(0)

    work_id = pointer["selected_work_id"]
    exit_code = _run_cli(["status-run", "--work-id", work_id], base_path)
    sys.exit(exit_code)


def _cmd_switch(ns: argparse.Namespace, base_path: Path) -> None:
    work_id = ns.work_id
    run_path = base_path / ".req-to-plan" / work_id / "run.md"
    if not run_path.exists():
        print(f"blocked: source_run_not_found\nwork_id: {work_id}\n")
        sys.exit(7)

    write_active_pointer(base_path, work_id, reason="manual_switch")
    print(f"selected_run: .req-to-plan/{work_id}/run.md\nnext: r2p-continue\n")


def _cmd_adapt(ns: argparse.Namespace, base_path: Path) -> None:
    pointer = read_active_pointer(base_path)
    if not pointer:
        print("no_selected_run: true\nnext: r2p-status --all\n")
        sys.exit(1)

    work_id = pointer["selected_work_id"]
    run_path = base_path / ".req-to-plan" / work_id / "run.md"
    if not run_path.exists():
        print(f"blocked: source_run_not_found\nwork_id: {work_id}\n")
        sys.exit(7)

    from tools.workflow_cli.state import RunStateManager
    try:
        mgr = RunStateManager(run_path.parent)
        record = mgr.load()
    except Exception as e:
        print(f"blocked: run_not_terminal\nwork_id: {work_id}\nreason: {e}\n")
        sys.exit(1)

    if not is_terminal(record.status):
        print(f"blocked: run_not_closed\nwork_id: {work_id}\nnext: r2p-continue\n")
        sys.exit(1)

    plan_path = base_path / ".req-to-plan" / work_id / "07-plan.md"
    output_path = base_path / ".req-to-plan" / work_id / f"{ns.executor}-plan.md"

    from tools.workflow_cli.adapters import get_adapter
    try:
        adapter = get_adapter(ns.executor)
    except ValueError:
        print(f"unsupported_executor: {ns.executor}\n")
        sys.exit(2)

    result = adapter.adapt_plan(plan_path, output_path)
    print(result)
    print(f"output: {output_path}\n")


def _cmd_reopen(ns: argparse.Namespace, base_path: Path) -> None:
    exit_code = _run_cli(
        [
            "run-reopen",
            "--from", ns.from_id,
            "--stage", ns.stage,
            "--reason", ns.reason,
        ],
        base_path,
    )
    sys.exit(exit_code)


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="r2p", description="req-to-plan agent shortcuts")
    sub = parser.add_subparsers(dest="subcommand", required=True)

    p_start = sub.add_parser("start")
    p_start.add_argument("requirement", nargs="?", default="")
    p_start.add_argument("--separate", action="store_true")

    sub.add_parser("continue")

    p_status = sub.add_parser("status")
    p_status.add_argument("--all", action="store_true")

    p_switch = sub.add_parser("switch")
    p_switch.add_argument("--work-id", dest="work_id", required=True)

    p_adapt = sub.add_parser("adapt")
    p_adapt.add_argument("--executor", required=True)

    p_reopen = sub.add_parser("reopen")
    p_reopen.add_argument("--from", dest="from_id", required=True)
    p_reopen.add_argument("--stage", required=True)
    p_reopen.add_argument("--reason", required=True)

    return parser


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main(args: list[str] | None = None, base_path: Path | None = None) -> None:
    parser = _build_parser()
    ns = parser.parse_args(args)

    bp = base_path or Path.cwd()

    handlers = {
        "start": _cmd_start,
        "continue": _cmd_continue,
        "status": _cmd_status,
        "switch": _cmd_switch,
        "adapt": _cmd_adapt,
        "reopen": _cmd_reopen,
    }
    handlers[ns.subcommand](ns, bp)
    sys.exit(0)


if __name__ == "__main__":
    main()

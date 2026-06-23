"""
Agent shortcut dispatcher for r2p-* commands.

Usage:
    python3 -m tools.workflow_cli.agent_shortcuts <subcommand> [flags]
"""
from __future__ import annotations

import argparse
import re
import shutil
import shlex
import sys
from datetime import datetime, timezone
from pathlib import Path

from tools.workflow_cli.atomic import atomic_write_text
from tools.workflow_cli.models import RunStatus, WorkId
from tools.workflow_cli.output import EXIT_CONFLICT

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
    work_id = _validate_work_id(work_id)
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
    atomic_write_text(path, content)


def _validate_work_id(raw: str) -> str:
    try:
        return str(WorkId(raw))
    except ValueError as exc:
        print(
            "blocked: invalid_work_id\n"
            f"work_id: {raw}\n"
            f"reason: {exc}\n"
        )
        sys.exit(2)


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
    # Truncate first, then strip dashes: stripping before truncation can leave a
    # trailing "-" at the slice boundary, producing an invalid WorkId.
    candidate = re.sub(r"-+", "-", candidate)[:max_slug_len].strip("-")
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
        alt_candidate = candidate[:max_slug_len - len(suffix)].rstrip("-")
        alt = f"{prefix}{alt_candidate}{suffix}"
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


def _shell_join(parts: list[str | Path]) -> str:
    return " ".join(shlex.quote(str(part)) for part in parts)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _python_executable() -> str:
    if sys.executable:
        return sys.executable
    return "python3" if shutil.which("python3") else "python"


def _workflow_cli_command(base_path: Path, args_list: list[str]) -> str:
    return _shell_join(
        [
            "env",
            f"PYTHONPATH={_repo_root()}",
            _python_executable(),
            "-m",
            "tools.workflow_cli",
            "--base-path",
            base_path,
            *args_list,
        ]
    )


def _tier_lock_command(base_path: Path, work_id: str, record) -> str:
    estimate = getattr(record, "tier_estimate", None)
    base = estimate.base.value if estimate is not None else "light"
    modifiers = (
        sorted(m.value for m in estimate.modifiers)
        if estimate is not None
        else []
    )
    args = ["tier-lock", "--work-id", work_id, "--base", base]
    if modifiers:
        args.extend(["--modifiers", ",".join(modifiers)])
    args.append("--confirm")
    return _workflow_cli_command(base_path, args)


def _prepare_input_file(run_dir: Path, stage: str, suffix: str, seed: str = "") -> Path:
    path = run_dir / "inputs" / f"{stage}-{suffix}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text(seed, encoding="utf-8")
    return path


def _prev_stage(stage):
    """Return the Stage enum member immediately before *stage*, or None if first."""
    from tools.workflow_cli.models import STAGE_ORDER
    i = STAGE_ORDER.index(stage)
    return STAGE_ORDER[i - 1] if i > 0 else None


def _seed_for_stage(stage, tier, upstream_summary: str = "", context_summary: str = "") -> str:
    """Build the seed text for a stage content file: template + upstream summary + context pack."""
    from tools.workflow_cli.stage_templates import template_for
    from tools.workflow_cli.markdown import strip_readonly_sections
    base = tier.base if tier is not None else None
    text = template_for(stage, base) if base is not None else ""
    # Upstream artifacts persist the read-only blocks they were seeded with
    # (nothing strips them at store time). Strip them here, like every other
    # consumer (gates/trace), so the freshly injected Upstream Summary / Project
    # Context wrappers below are not duplicated or accumulated across stages.
    upstream_summary = strip_readonly_sections(upstream_summary).strip()
    if upstream_summary:
        text += (
            "\n## Upstream Summary (read-only)\n"
            + upstream_summary
            + "\n<!-- /r2p-read-only -->\n"
        )
    if context_summary.strip():
        text += (
            "\n## Project Context (read-only)\n"
            + context_summary.strip()
            + "\n<!-- /r2p-read-only -->\n"
        )
    return text


def _stage_content_command(
    base_path: Path,
    work_id: str,
    stage: str,
    command: str,
    content_file: Path,
) -> str:
    return _workflow_cli_command(
        base_path,
        [
            command,
            "--work-id", work_id,
            "--stage", stage,
            "--content-file", content_file,
        ],
    )


def _emit_checkpoint_stop(
    base_path: Path,
    work_id: str,
    stage: str,
    record,
    run_dir: Path,
) -> None:
    """Print the correct checkpoint stop for the current run.

    Forced-review runs (a migration/safety/cross_project modifier at
    DESIGN/SPEC/PLAN) that lack a version-matched subagent review file stop with
    ``needs_subagent_review``: the agent is authorized to run a read-only review
    subagent autonomously and write its findings to the printed ``review_file``,
    with no separate human authorization. Every other checkpoint stops with
    ``needs_human_approval`` for an explicit ``checkpoint-decide``.
    """
    from tools.workflow_cli.gates import check_forced_subagent_review
    from tools.workflow_cli.state import get_active_artifact

    aa = get_active_artifact(record, record.current_stage)
    version = aa.version if aa is not None else 1
    reviews_dir = run_dir / "reviews"
    review_result = check_forced_subagent_review(
        record.current_stage, record.tier_locked, reviews_dir, version
    )
    if not review_result.passed:
        review_file = reviews_dir / f"{stage}-subagent-review-v{version}.md"
        modifiers = (
            ", ".join(sorted(m.value for m in record.tier_locked.modifiers))
            if record.tier_locked is not None
            else ""
        )
        print(
            "stop: needs_subagent_review\n"
            f"stage: {stage}\n"
            f"review_file: {review_file}\n"
            f"reason: forced subagent review required (tier modifier: {modifiers})\n"
            "note: you are authorized to spawn a read-only review subagent now; "
            "separate human approval is NOT required for this step\n"
            "next: have the review subagent audit the stage artifact, write its "
            "findings to review_file, then r2p-continue\n"
        )
        return

    approve_cmd = _workflow_cli_command(
        base_path,
        ["checkpoint-decide", "--work-id", work_id, "--stage", stage,
         "--decision", "approved", "--confirm"],
    )
    changes_cmd = _workflow_cli_command(
        base_path,
        ["checkpoint-decide", "--work-id", work_id, "--stage", stage,
         "--decision", "changes_requested"],
    )
    print(
        f"stop: needs_human_approval\nstage: {stage}\n"
        "next: "
        f"{approve_cmd}\n"
        "alt: "
        f"{changes_cmd}\n"
    )


def _open_owner_route(record):
    return next(
        (
            route
            for route in record.open_routes
            if route.status == "open" and route.owner_stage == record.current_stage
        ),
        None,
    )


def _emit_gap_resolve_stop(base_path: Path, work_id: str, stage: str, route_id: str) -> None:
    resolve_cmd = _workflow_cli_command(
        base_path,
        ["gap-resolve", "--work-id", work_id, "--route-id", route_id],
    )
    print(
        "stop: needs_gap_resolve\n"
        f"stage: {stage}\n"
        f"route_id: {route_id}\n"
        f"next: {resolve_cmd}\n"
    )


# ---------------------------------------------------------------------------
# Subcommand handlers
# ---------------------------------------------------------------------------


def _resolve_start_requirement(ns: argparse.Namespace) -> tuple[str, Path | None]:
    """Resolve the start requirement from either --file or the positional arg.

    Returns (requirement_text, file_path); file_path is None for inline text.
    Exits with a structured ``blocked:`` message (exit 2) on bad input.
    """
    file_arg = getattr(ns, "file", None)
    raw = ns.requirement

    if file_arg and raw:
        print(
            "blocked: ambiguous_requirement\n"
            "next: pass either a positional requirement or --file, not both\n"
        )
        sys.exit(2)

    if file_arg:
        file_path = Path(file_arg)
        if not file_path.is_file():
            print(f"blocked: requirement_file_not_found\nfile: {file_arg}\n")
            sys.exit(2)
        text = file_path.read_text(encoding="utf-8")
        if not text.strip():
            print(f"blocked: empty_requirement_file\nfile: {file_arg}\n")
            sys.exit(2)
        return text, file_path.resolve()

    if not raw or not raw.strip():
        print("blocked: missing_requirement\nnext: r2p-start \"<raw requirement>\"\n")
        sys.exit(2)
    return raw, None


def _build_run_start_args(work_id, requirement, file_path, repo_path=None):
    if file_path is not None:
        args = ["run-start", "--work-id", work_id, "--requirement-file", str(file_path)]
    else:
        args = ["run-start", "--work-id", work_id, "--requirement", requirement]
    if repo_path:
        args += ["--repo-path", str(repo_path)]
    return args


def _cmd_start(ns: argparse.Namespace, base_path: Path) -> None:
    requirement, file_path = _resolve_start_requirement(ns)

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

    work_id = generate_work_id(requirement, base_path)
    run_args = _build_run_start_args(work_id, requirement, file_path, getattr(ns, "repo_path", None))
    exit_code = _run_cli(run_args, base_path)
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
    work_id = _validate_work_id(pointer["selected_work_id"])
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
                print(f"stop: tier_not_locked\nstage: {stage}\n"
                      f"next: {_tier_lock_command(base_path, work_id, record)}\n")
                sys.exit(0)
            aa = get_active_artifact(record, record.current_stage)
            try:
                body = read_artifact(run_path.parent, record.current_stage).strip()
            except FileNotFoundError:
                body = ""
            open_owner_route = _open_owner_route(record)
            if aa is None or not body:
                prev = _prev_stage(record.current_stage)
                try:
                    upstream = read_artifact(run_path.parent, prev) if prev else ""
                except FileNotFoundError:
                    upstream = ""
                pack_md = run_path.parent / "02-project-context.md"
                context_summary = pack_md.read_text(encoding="utf-8") if pack_md.exists() else ""
                seed = _seed_for_stage(record.current_stage, record.tier_locked, upstream, context_summary)
                content_file = _prepare_input_file(run_path.parent, stage, "content", seed)
                content_cmd = _stage_content_command(
                    base_path,
                    work_id,
                    stage,
                    "stage-produce" if aa is None else "stage-update",
                    content_file,
                )
                print(f"stop: needs_content\nstage: {stage}\n"
                      f"content_file: {content_file}\n"
                      f"next: {content_cmd}\n")
                sys.exit(0)
            if aa.status == "stale":
                content_file = _prepare_input_file(run_path.parent, stage, "repair", body)
                update_cmd = _stage_content_command(
                    base_path,
                    work_id,
                    stage,
                    "stage-update",
                    content_file,
                )
                repair_status = "upstream_gap_open" if open_owner_route is not None else "stale_artifact"
                print(f"stop: needs_repair\nstatus: {repair_status}\nstage: {stage}\n"
                      f"content_file: {content_file}\n"
                      f"next: {update_cmd}\n")
                sys.exit(0)
            if aa.status != "ready":
                ready_cmd = _workflow_cli_command(
                    base_path,
                    ["stage-ready", "--work-id", work_id, "--stage", stage],
                )
                print(f"stop: needs_ready\nstage: {stage}\n"
                      "next: review the artifact, then "
                      f"{ready_cmd}\n")
                sys.exit(0)
            code = _run_cli(["gate-quality", "--work-id", work_id, "--stage", stage], base_path)
            if code != 0 and manager.load().status == RunStatus.ACTIVE_STAGE_DRAFT:
                # The gate did not change state (e.g. a precondition conflict); surface
                # its output directly instead of looping on the same unchanged status.
                sys.exit(code)
            # On pass -> ready_for_checkpoint_review (opens review-checkpoint below);
            # on structural failure -> quality_gate_failed (surfaced as stop: needs_repair).
            continue

        if s == RunStatus.READY_FOR_CHECKPOINT_REVIEW:
            route = _open_owner_route(record)
            if route is not None:
                _emit_gap_resolve_stop(base_path, work_id, stage, route.route_id)
                sys.exit(0)
            code = _run_cli(["review-checkpoint", "--work-id", work_id, "--stage", stage], base_path)
            if code != 0:
                sys.exit(code)
            record = manager.load()
            route = _open_owner_route(record)
            if route is not None:
                _emit_gap_resolve_stop(base_path, work_id, stage, route.route_id)
                sys.exit(0)
            _emit_checkpoint_stop(base_path, work_id, stage, record, run_path.parent)
            sys.exit(0)

        if s == RunStatus.CHECKPOINT_REVIEW:
            route = _open_owner_route(record)
            if route is not None:
                _emit_gap_resolve_stop(base_path, work_id, stage, route.route_id)
                sys.exit(0)
            _emit_checkpoint_stop(base_path, work_id, stage, record, run_path.parent)
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
                retry_cmd = _workflow_cli_command(
                    base_path,
                    ["gate-entry", "--work-id", work_id, "--stage", stage],
                )
                print(f"stop: entry_gate_failed\nstage: {stage}\n"
                      "next: repair upstream and rerun "
                      f"{retry_cmd}\n")
                sys.exit(code)
            record = manager.load()
            stage = record.current_stage.value
            aa = get_active_artifact(record, record.current_stage)
            if aa is not None and aa.status == "stale":
                try:
                    body = read_artifact(run_path.parent, record.current_stage).strip()
                except FileNotFoundError:
                    body = ""
                content_file = _prepare_input_file(run_path.parent, stage, "repair", body)
                update_cmd = _stage_content_command(
                    base_path,
                    work_id,
                    stage,
                    "stage-update",
                    content_file,
                )
                print(f"stop: needs_repair\nstatus: stale_artifact\nstage: {stage}\n"
                      f"content_file: {content_file}\n"
                      f"next: {update_cmd}\n")
                sys.exit(0)
            prev = _prev_stage(record.current_stage)
            try:
                upstream = read_artifact(run_path.parent, prev) if prev else ""
            except FileNotFoundError:
                upstream = ""
            pack_md = run_path.parent / "02-project-context.md"
            context_summary = pack_md.read_text(encoding="utf-8") if pack_md.exists() else ""
            seed = _seed_for_stage(record.current_stage, record.tier_locked, upstream, context_summary)
            content_file = _prepare_input_file(run_path.parent, stage, "content", seed)
            produce_cmd = _stage_content_command(
                base_path,
                work_id,
                stage,
                "stage-produce",
                content_file,
            )
            print(f"stop: entered_stage\nstage: {stage}\n"
                  f"content_file: {content_file}\n"
                  f"next: {produce_cmd}\n")
            sys.exit(0)

        if s == RunStatus.ENTRY_GATE_FAILED:
            retry_cmd = _workflow_cli_command(
                base_path,
                ["gate-entry", "--work-id", work_id, "--stage", stage],
            )
            print(f"stop: entry_gate_failed\nstage: {stage}\n"
                  "next: repair upstream checkpoints, then "
                  f"{retry_cmd}\n")
            sys.exit(0)

        if s in (RunStatus.QUALITY_GATE_FAILED, RunStatus.CHECKPOINT_CHANGES_REQUESTED):
            try:
                seed = read_artifact(run_path.parent, record.current_stage)
            except FileNotFoundError:
                seed = ""
            content_file = _prepare_input_file(run_path.parent, stage, "repair", seed)
            update_cmd = _stage_content_command(
                base_path,
                work_id,
                stage,
                "stage-update",
                content_file,
            )
            print(f"stop: needs_repair\nstatus: {s.value}\nstage: {stage}\n"
                  f"content_file: {content_file}\n"
                  f"next: {update_cmd}\n")
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

    work_id = _validate_work_id(pointer["selected_work_id"])
    exit_code = _run_cli(["status-run", "--work-id", work_id], base_path)
    sys.exit(exit_code)


def _cmd_switch(ns: argparse.Namespace, base_path: Path) -> None:
    work_id = _validate_work_id(ns.work_id)
    run_path = base_path / ".req-to-plan" / work_id / "run.md"
    if not run_path.exists():
        print(f"blocked: source_run_not_found\nwork_id: {work_id}\n")
        sys.exit(7)

    write_active_pointer(base_path, work_id, reason="manual_switch")
    print(f"selected_run: .req-to-plan/{work_id}/run.md\nnext: r2p-continue\n")


def _cmd_reopen(ns: argparse.Namespace, base_path: Path) -> None:
    from_id = _validate_work_id(ns.from_id)
    exit_code = _run_cli(
        [
            "run-reopen",
            "--from", from_id,
            "--stage", ns.stage,
            "--reason", ns.reason,
        ],
        base_path,
    )
    sys.exit(exit_code)


def _cmd_gap_open(ns: argparse.Namespace, base_path: Path) -> None:
    work_id = _validate_work_id(ns.work_id)
    args = [
        "gap-open",
        "--work-id", work_id,
        "--owner-stage", ns.owner_stage,
        "--required-action", ns.required_action,
    ]
    if ns.confirm:
        args.append("--confirm")
    sys.exit(_run_cli(args, base_path))


def _cmd_gap_resolve(ns: argparse.Namespace, base_path: Path) -> None:
    work_id = _validate_work_id(ns.work_id)
    args = ["gap-resolve", "--work-id", work_id, "--route-id", ns.route_id]
    if ns.confirm:
        args.append("--confirm")
    sys.exit(_run_cli(args, base_path))


def _cmd_tier_lock(ns: argparse.Namespace, base_path: Path) -> None:
    work_id = _validate_work_id(ns.work_id)
    run_path = base_path / ".req-to-plan" / work_id / "run.md"
    if not run_path.exists():
        print(f"blocked: source_run_not_found\nwork_id: {work_id}\n")
        sys.exit(7)

    from tools.workflow_cli.state import RunStateManager
    record = RunStateManager(run_path.parent).load()
    if record.status != RunStatus.ACTIVE_STAGE_DRAFT:
        print(
            "blocked: tier_lock_not_allowed\n"
            f"work_id: {work_id}\n"
            f"status: {record.status.value}\n"
            "must_be: active_stage_draft\n"
        )
        sys.exit(EXIT_CONFLICT)

    args = [
        "tier-lock",
        "--work-id", work_id,
        "--base", ns.base,
    ]
    if ns.modifiers:
        args.extend(["--modifiers", ns.modifiers])
    if ns.override_floor:
        args.append("--override-floor")
    if ns.confirm:
        args.append("--confirm")
    sys.exit(_run_cli(args, base_path))


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="r2p", description="req-to-plan agent shortcuts")
    sub = parser.add_subparsers(dest="subcommand", required=True)

    p_start = sub.add_parser("start")
    p_start.add_argument("requirement", nargs="?", default=None)
    p_start.add_argument("--separate", action="store_true")
    p_start.add_argument(
        "--file",
        dest="file",
        default=None,
        help="Read the requirement from a file instead of a positional argument",
    )
    p_start.add_argument("--repo-path", dest="repo_path", default=None)

    sub.add_parser("continue")

    p_status = sub.add_parser("status")
    p_status.add_argument("--all", action="store_true")

    p_switch = sub.add_parser("switch")
    p_switch.add_argument("--work-id", dest="work_id", required=True)

    p_reopen = sub.add_parser("reopen")
    p_reopen.add_argument("--from", dest="from_id", required=True)
    p_reopen.add_argument("--stage", required=True)
    p_reopen.add_argument("--reason", required=True)

    p_tier_lock = sub.add_parser("tier-lock")
    p_tier_lock.add_argument("--work-id", dest="work_id", required=True)
    p_tier_lock.add_argument("--base", required=True, choices=["light", "standard"])
    p_tier_lock.add_argument("--modifiers", default=None)
    p_tier_lock.add_argument("--override-floor", action="store_true")
    p_tier_lock.add_argument("--confirm", action="store_true")

    p_gap_open = sub.add_parser("gap-open")
    p_gap_open.add_argument("--work-id", dest="work_id", required=True)
    p_gap_open.add_argument("--owner-stage", dest="owner_stage", required=True)
    p_gap_open.add_argument("--required-action", dest="required_action", required=True)
    p_gap_open.add_argument("--confirm", action="store_true")

    p_gap_resolve = sub.add_parser("gap-resolve")
    p_gap_resolve.add_argument("--work-id", dest="work_id", required=True)
    p_gap_resolve.add_argument("--route-id", dest="route_id", required=True)
    p_gap_resolve.add_argument("--confirm", action="store_true")

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
        "reopen": _cmd_reopen,
        "tier-lock": _cmd_tier_lock,
        "gap-open": _cmd_gap_open,
        "gap-resolve": _cmd_gap_resolve,
    }
    handlers[ns.subcommand](ns, bp)
    sys.exit(0)


if __name__ == "__main__":
    main()

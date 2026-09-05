"""
Agent shortcut dispatcher for r2p-* commands.

Usage:
    python3 -m tools.workflow_cli.agent_shortcuts <subcommand> [flags]
"""
from __future__ import annotations

import argparse
import contextlib
import io
import json
import re
import shutil
import shlex
import sys
from datetime import datetime, timezone
from pathlib import Path

from tools.workflow_cli.atomic import (
    UnsafeRegularFileError,
    atomic_write_text,
    read_regular_text,
)
from tools.workflow_cli.models import RunStatus, WorkId
from tools.workflow_cli.output import (
    EXIT_CLI_ERR,
    EXIT_CONFLICT,
    EXIT_REVIEW_REQ,
    is_json_mode,
)
from tools.workflow_cli.execution_profile import (
    ExecutionProfileError,
    fast_structure_eligible,
    parse_execution_ledger,
    prerequisite_semantics_version,
)
from tools.workflow_cli.execution_metrics import (
    MetricsFormatError,
    PrerequisiteError,
    start_execution_transaction,
)
from tools.workflow_cli.markdown import plan_task_anchors, strip_nonsemantic_markdown
from tools.workflow_cli.workspace import ensure_workspace_gitignore

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


def _ensure_workspace_gitignore_or_exit(base_path: Path, work_id: str) -> None:
    try:
        ensure_workspace_gitignore(base_path)
    except ValueError as exc:
        print(
            "blocked: unsafe_workspace_gitignore\n"
            f"work_id: {work_id}\n"
            f"reason: {exc}\n"
        )
        sys.exit(EXIT_CONFLICT)


def write_active_pointer(base_path: Path, work_id: str, reason: str = "workflow_start") -> None:
    work_id = _validate_work_id(work_id)
    _ensure_workspace_gitignore_or_exit(base_path, work_id)
    path = _pointer_path(base_path)
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


def _reject_symlinked_workspace_dir_or_exit(base_path: Path, work_id: str | None = None) -> Path:
    r2p_dir = base_path / ".req-to-plan"
    if r2p_dir.is_symlink():
        work_id_line = f"work_id: {work_id}\n" if work_id else ""
        print(
            "blocked: unsafe_workspace_dir_symlink\n"
            f"{work_id_line}"
            f"path: {r2p_dir}\n"
        )
        sys.exit(EXIT_CONFLICT)
    return r2p_dir


def _reject_symlinked_run_paths_or_exit(base_path: Path, work_id: str) -> Path:
    r2p_dir = _reject_symlinked_workspace_dir_or_exit(base_path, work_id)
    run_dir = r2p_dir / work_id
    if run_dir.is_symlink():
        print(
            "blocked: unsafe_run_dir_symlink\n"
            f"work_id: {work_id}\n"
            f"path: {run_dir}\n"
        )
        sys.exit(EXIT_CONFLICT)
    return run_dir


def _load_matching_record_or_exit(manager, run_dir: Path, work_id: str):
    """Load a run only when its path and embedded WorkId agree."""
    try:
        record = manager.load()
    except FileNotFoundError:
        print(f"blocked: source_run_not_found\nwork_id: {work_id}\n")
        sys.exit(7)
    except UnsafeRegularFileError as exc:
        print(f"blocked: unsafe_run_record\nwork_id: {work_id}\nreason: {exc}\n")
        sys.exit(EXIT_CONFLICT)
    embedded = str(record.work_id)
    if run_dir.name != work_id or embedded != work_id:
        print(
            "blocked: run_identity_mismatch\n"
            f"requested_work_id: {work_id}\n"
            f"directory_work_id: {run_dir.name}\n"
            f"record_work_id: {embedded}\n"
        )
        sys.exit(EXIT_CONFLICT)
    return record


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
            if str(record.work_id) != run_md.parent.name:
                raise ValueError(
                    "run identity mismatch: "
                    f"directory={run_md.parent.name!r}, record={record.work_id!r}"
                )
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
    if len(candidate) < 3:
        import hashlib
        h = hashlib.md5(requirement.encode()).hexdigest()[:8]
        candidate = f"run-{h}"

    base_id = f"{prefix}{candidate}"

    if base_path is None:
        return base_id

    r2p_dir = base_path / ".req-to-plan"

    def is_reserved(work_id: str) -> bool:
        return (r2p_dir / work_id).exists() or (r2p_dir / "archive" / work_id).exists()

    if not is_reserved(base_id):
        return base_id

    for n in range(2, 100):
        suffix = f"-{n}"
        alt_candidate = candidate[:max_slug_len - len(suffix)].rstrip("-")
        alt = f"{prefix}{alt_candidate}{suffix}"
        if not is_reserved(alt):
            return alt

    raise RuntimeError(
        f"Could not generate a unique work ID for {base_id!r} after 98 attempts. "
        "Clean up old runs in .req-to-plan/ or .req-to-plan/archive/ before starting a new one."
    )


# ---------------------------------------------------------------------------
# Terminal check
# ---------------------------------------------------------------------------


def is_terminal(status: RunStatus) -> bool:
    return status in (RunStatus.CLOSED_AT_PLAN_CHECKPOINT, RunStatus.ARCHIVED)


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


def _extract_cli_output_value(output: str, key: str) -> str | None:
    stripped = output.strip()
    if stripped.startswith("{"):
        try:
            payload = json.loads(stripped)
        except json.JSONDecodeError:
            payload = {}
        value = payload.get(key)
        if isinstance(value, str):
            return value

    prefix = f"{key}:"
    for line in output.splitlines():
        line = line.strip()
        if line.startswith(prefix):
            return line.partition(":")[2].strip()
    return None


def _json_payload_from_cli_output(output: str) -> dict[str, object]:
    stripped = output.strip()
    if not stripped:
        return {}
    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _isolated_launcher_path() -> Path:
    return _repo_root() / "tools" / "workflow_cli" / "__main__.py"


def _python_executable() -> str:
    if sys.executable:
        return sys.executable
    return "python3" if shutil.which("python3") else "python"


def _workflow_cli_command(base_path: Path, args_list: list[str]) -> str:
    return _shell_join(
        [
            _python_executable(),
            "-E",
            _isolated_launcher_path(),
            "tools.workflow_cli",
            "--base-path",
            base_path,
            *args_list,
        ]
    )


def _unsafe_seed_source_or_exit(path: Path, work_id: str, reason: Exception) -> None:
    print(
        "blocked: unsafe_seed_source\n"
        f"work_id: {work_id}\n"
        f"path: {path}\n"
        f"reason: {reason}\n"
    )
    sys.exit(EXIT_CONFLICT)


def _read_seed_file_or_exit(path: Path, work_id: str) -> str:
    try:
        text = read_regular_text(path, missing_ok=True)
    except (UnsafeRegularFileError, OSError, UnicodeError) as exc:
        _unsafe_seed_source_or_exit(path, work_id, exc)
    return text or ""


def _read_seed_artifact_or_exit(run_dir: Path, stage, work_id: str) -> str:
    from tools.workflow_cli.artifact import artifact_path, read_artifact

    try:
        return read_artifact(run_dir, stage)
    except FileNotFoundError:
        return ""
    except (UnsafeRegularFileError, OSError, UnicodeError) as exc:
        _unsafe_seed_source_or_exit(artifact_path(run_dir, stage), work_id, exc)


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
    inputs_dir = run_dir / "inputs"
    if inputs_dir.is_symlink():
        raise ValueError("unsafe_input_file_symlink")
    inputs_dir.mkdir(parents=True, exist_ok=True)
    path = inputs_dir / f"{stage}-{suffix}.md"
    if path.is_symlink():
        raise ValueError("unsafe_input_file_symlink")
    if not path.exists():
        atomic_write_text(path, seed)
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
        if review_result.exit_code != EXIT_REVIEW_REQ:
            reason = "; ".join(review_result.issues) or "forced review gate failed"
            print(
                "blocked: unsafe_forced_review\n"
                f"stage: {stage}\n"
                f"reason: {reason}\n"
                "next: remove the unsafe reviews/ path or subagent review file, "
                "then r2p-continue\n"
            )
            sys.exit(EXIT_CONFLICT)
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
            "next: have the review subagent audit the stage artifact for spec "
            "compliance, code/design quality, AND any unresolved ambiguity / "
            "undecided point (flag hedging that lacks a decision), write its "
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
    _ensure_workspace_gitignore_or_exit(base_path, work_id)
    json_mode = is_json_mode()
    cli_output = ""
    if json_mode:
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            exit_code = _run_cli(run_args, base_path)
        cli_output = output.getvalue()
    else:
        exit_code = _run_cli(run_args, base_path)
    if exit_code != 0:
        if json_mode and cli_output:
            print(cli_output, end="" if cli_output.endswith("\n") else "\n")
        sys.exit(exit_code)

    write_active_pointer(base_path, work_id, reason="workflow_start")
    run_path = f".req-to-plan/{work_id}/run.md"
    if json_mode:
        payload = _json_payload_from_cli_output(cli_output)
        payload.setdefault("work_id", work_id)
        payload.update(
            {
                "created": run_path,
                "selected_work_id": work_id,
                "selected_run": run_path,
                "next": "r2p-continue",
            }
        )
        print(json.dumps(payload, indent=2))
        return
    print(
        f"created: {run_path}\n"
        f"selected_run: {run_path}\n"
        f"next: r2p-continue\n"
    )


def _cmd_continue(ns: argparse.Namespace, base_path: Path) -> None:
    _reject_symlinked_workspace_dir_or_exit(base_path)
    pointer = read_active_pointer(base_path)
    work_id = pointer.get("selected_work_id") if pointer else None
    if not work_id:
        print("no_selected_run: true\nnext: r2p-status --all\n")
        sys.exit(1)
    work_id = _validate_work_id(work_id)
    run_dir = _reject_symlinked_run_paths_or_exit(base_path, work_id)
    run_path = run_dir / "run.md"
    if not run_path.exists():
        print(f"blocked: source_run_not_found\nwork_id: {work_id}\n")
        sys.exit(7)

    from tools.workflow_cli.state import RunStateManager, get_active_artifact
    from tools.workflow_cli.models import RunStatus, Stage
    manager = RunStateManager(run_path.parent)

    while True:
        record = _load_matching_record_or_exit(manager, run_dir, work_id)
        s = record.status
        stage = record.current_stage.value

        if s == RunStatus.EXECUTING:
            ledger = run_path.parent / "execution" / "progress.md"
            print(
                "stop: resume_execution\n"
                f"work_id: {work_id}\n"
                f"ledger: {ledger}\n"
                f"next: r2p-execute --work-id {work_id} to validate and report "
                "first_actionable_task\n"
            )
            sys.exit(0)

        if s == RunStatus.ARCHIVED:
            print(f"done: archived\nwork_id: {work_id}\n")
            sys.exit(0)

        if s == RunStatus.CLOSED_AT_PLAN_CHECKPOINT:
            print(f"done: run_closed\nwork_id: {work_id}\nplan: 07-plan.md\n"
                  "next: hand the PLAN to your executor\n"
                  f"to implement: r2p-execute --work-id {work_id}\n"
                  f"to archive: r2p-archive --work-id {work_id}\n")
            sys.exit(0)

        if s == RunStatus.ACTIVE_STAGE_DRAFT:
            if record.tier_locked is None:
                print(f"stop: tier_not_locked\nstage: {stage}\n"
                      f"next: {_tier_lock_command(base_path, work_id, record)}\n")
                sys.exit(0)
            aa = get_active_artifact(record, record.current_stage)
            body = _read_seed_artifact_or_exit(
                run_path.parent, record.current_stage, work_id
            ).strip()
            open_owner_route = _open_owner_route(record)
            if aa is None or not body:
                prev = _prev_stage(record.current_stage)
                upstream = (
                    _read_seed_artifact_or_exit(run_path.parent, prev, work_id)
                    if prev
                    else ""
                )
                pack_md = run_path.parent / "02-project-context.md"
                context_summary = _read_seed_file_or_exit(pack_md, work_id)
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
            if (
                code != 0
                and _load_matching_record_or_exit(
                    manager, run_dir, work_id
                ).status
                == RunStatus.ACTIVE_STAGE_DRAFT
            ):
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
            record = _load_matching_record_or_exit(manager, run_dir, work_id)
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
            record = _load_matching_record_or_exit(manager, run_dir, work_id)
            stage = record.current_stage.value
            aa = get_active_artifact(record, record.current_stage)
            if aa is not None and aa.status == "stale":
                body = _read_seed_artifact_or_exit(
                    run_path.parent, record.current_stage, work_id
                ).strip()
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
            upstream = (
                _read_seed_artifact_or_exit(run_path.parent, prev, work_id)
                if prev
                else ""
            )
            pack_md = run_path.parent / "02-project-context.md"
            context_summary = _read_seed_file_or_exit(pack_md, work_id)
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
            seed = _read_seed_artifact_or_exit(
                run_path.parent, record.current_stage, work_id
            )
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
        run_paths = sorted(r2p_dir.glob("*/run.md")) if r2p_dir.exists() else []
        if is_json_mode():
            runs: list[dict[str, object]] = []
            exit_code = 0
            for run_md in run_paths:
                work_id = run_md.parent.name
                output = io.StringIO()
                try:
                    with contextlib.redirect_stdout(output):
                        run_exit_code = _run_cli(
                            ["status-run", "--work-id", work_id], base_path
                        )
                except (OSError, UnicodeError, ValueError):
                    runs.append(
                        {
                            "work_id": work_id,
                            "status": "invalid",
                            "error": "invalid_run_state",
                            "exit_code": EXIT_CONFLICT,
                        }
                    )
                    if exit_code == 0:
                        exit_code = EXIT_CONFLICT
                    continue
                payload = _json_payload_from_cli_output(output.getvalue())
                if not payload:
                    payload = {"work_id": work_id, "exit_code": run_exit_code}
                elif run_exit_code != 0:
                    payload.setdefault("exit_code", run_exit_code)
                runs.append(payload)
                if exit_code == 0 and run_exit_code != 0:
                    exit_code = run_exit_code
            print(json.dumps({"runs": runs}, indent=2))
            sys.exit(exit_code)
        if not run_paths:
            print("no_runs: true\n")
            sys.exit(0)
        exit_code = 0
        for run_md in run_paths:
            work_id = run_md.parent.name
            try:
                _run_cli(["status-run", "--work-id", work_id], base_path)
            except (OSError, UnicodeError, ValueError):
                # Mirror the JSON aggregate: one malformed run.md must not
                # abort the listing of the remaining runs.
                print(
                    f"work_id: {work_id}\n"
                    "status: invalid\n"
                    "error: invalid_run_state\n"
                )
                if exit_code == 0:
                    exit_code = EXIT_CONFLICT
        sys.exit(exit_code)

    pointer = read_active_pointer(base_path)
    work_id = pointer.get("selected_work_id") if pointer else None
    if not work_id:
        print("no_selected_run: true\nnext: r2p-status --all\n")
        sys.exit(0)

    work_id = _validate_work_id(work_id)
    exit_code = _run_cli(["status-run", "--work-id", work_id], base_path)
    sys.exit(exit_code)


def _cmd_switch(ns: argparse.Namespace, base_path: Path) -> None:
    work_id = _validate_work_id(ns.work_id)
    run_dir = _reject_symlinked_run_paths_or_exit(base_path, work_id)
    run_path = run_dir / "run.md"
    if not run_path.exists():
        print(f"blocked: source_run_not_found\nwork_id: {work_id}\n")
        sys.exit(7)

    from tools.workflow_cli.state import RunStateManager
    _load_matching_record_or_exit(RunStateManager(run_dir), run_dir, work_id)

    write_active_pointer(base_path, work_id, reason="manual_switch")
    print(f"selected_run: .req-to-plan/{work_id}/run.md\nnext: r2p-continue\n")


def _cmd_reopen(ns: argparse.Namespace, base_path: Path) -> None:
    from_id = _validate_work_id(ns.from_id)
    _ensure_workspace_gitignore_or_exit(base_path, from_id)
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        exit_code = _run_cli(
            [
                "run-reopen",
                "--from", from_id,
                "--stage", ns.stage,
                "--reason", ns.reason,
            ],
            base_path,
        )
    cli_output = output.getvalue()
    json_mode = is_json_mode()
    if cli_output and (exit_code != 0 or not json_mode):
        print(cli_output, end="" if cli_output.endswith("\n") else "\n")
    if exit_code != 0:
        sys.exit(exit_code)

    new_work_id = _extract_cli_output_value(cli_output, "new_work_id")
    if not new_work_id:
        print("blocked: reopen_output_missing_new_work_id\n")
        sys.exit(EXIT_CONFLICT)

    write_active_pointer(base_path, new_work_id, reason="workflow_reopen")
    selected_run = f".req-to-plan/{new_work_id}/run.md"
    if json_mode:
        payload: dict[str, object] = {}
        stripped = cli_output.strip()
        if stripped:
            try:
                parsed = json.loads(stripped)
            except json.JSONDecodeError:
                parsed = {}
            if isinstance(parsed, dict):
                payload.update(parsed)
        payload["selected_work_id"] = new_work_id
        payload["selected_run"] = selected_run
        payload["next"] = "r2p-continue"
        print(json.dumps(payload, indent=2))
        sys.exit(0)

    print(f"selected_run: {selected_run}\nnext: r2p-continue\n")
    sys.exit(0)


def _cmd_archive(ns: argparse.Namespace, base_path: Path) -> None:
    work_id = ns.work_id
    if not work_id:
        pointer = read_active_pointer(base_path)
        work_id = pointer.get("selected_work_id") if pointer else None
        if not work_id:
            print("no_selected_run: true\nnext: r2p-archive --work-id <id>\n")
            sys.exit(1)
    work_id = _validate_work_id(work_id)
    archive_args = ["run-archive", "--work-id", work_id]
    if getattr(ns, "force", False):
        archive_args.append("--force")
    json_mode = is_json_mode()
    cli_output = ""
    if json_mode:
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            exit_code = _run_cli(archive_args, base_path)
        cli_output = output.getvalue()
    else:
        exit_code = _run_cli(archive_args, base_path)
    if exit_code != 0:
        if json_mode and cli_output:
            print(cli_output, end="" if cli_output.endswith("\n") else "\n")
        sys.exit(exit_code)
    pointer = read_active_pointer(base_path)
    if pointer and pointer.get("selected_work_id") == work_id:
        _pointer_path(base_path).unlink(missing_ok=True)
    if json_mode:
        payload = _json_payload_from_cli_output(cli_output)
        payload.setdefault("work_id", work_id)
        payload["next"] = "r2p-status --all"
        print(json.dumps(payload, indent=2))
        sys.exit(0)
    print(f"archived: {work_id}\nnext: r2p-status --all\n")
    sys.exit(0)


def _cmd_abandon(ns: argparse.Namespace, base_path: Path) -> None:
    work_id = _validate_work_id(ns.work_id)
    abandon_args = [
        "run-abandon",
        "--work-id", work_id,
        "--reason", ns.reason,
    ]
    json_mode = is_json_mode()
    cli_output = ""
    if json_mode:
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            exit_code = _run_cli(abandon_args, base_path)
        cli_output = output.getvalue()
    else:
        exit_code = _run_cli(abandon_args, base_path)
    if exit_code != 0:
        if json_mode and cli_output:
            print(cli_output, end="" if cli_output.endswith("\n") else "\n")
        sys.exit(exit_code)
    pointer = read_active_pointer(base_path)
    if pointer and pointer.get("selected_work_id") == work_id:
        _pointer_path(base_path).unlink(missing_ok=True)
    if json_mode:
        payload = _json_payload_from_cli_output(cli_output)
        payload.setdefault("work_id", work_id)
        payload["next"] = "r2p-status --all"
        print(json.dumps(payload, indent=2))
        sys.exit(0)
    print(f"abandoned_and_archived: {work_id}\nnext: r2p-status --all\n")
    sys.exit(0)


def _cmd_execute(ns: argparse.Namespace, base_path: Path) -> None:
    requested_profile = getattr(ns, "profile", None)
    confirm_fast = bool(getattr(ns, "confirm_fast_eligible", False))
    reject_fast = bool(getattr(ns, "reject_fast_ineligible", False))
    reason = getattr(ns, "reason", None)
    invalid_args = (
        requested_profile not in {None, "strict", "fast"}
        or (confirm_fast and reject_fast)
        or ((confirm_fast or reject_fast) and requested_profile != "fast")
        or (reason is not None and not reject_fast)
        or (reject_fast and (
            not isinstance(reason, str)
            or not reason.strip()
            or "\n" in reason
            or "\r" in reason
        ))
    )
    if invalid_args:
        if is_json_mode():
            print(json.dumps({
                "status": "error",
                "reason": "invalid_execute_profile_arguments",
                "exit_code": EXIT_CLI_ERR,
                "message": "execute profile arguments are invalid",
            }, indent=2))
        else:
            print("blocked: invalid_execute_profile_arguments\n")
        sys.exit(EXIT_CLI_ERR)

    work_id = ns.work_id
    if not work_id:
        pointer = read_active_pointer(base_path)
        work_id = pointer.get("selected_work_id") if pointer else None
        if not work_id:
            print("no_selected_run: true\nnext: r2p-execute --work-id <id>\n")
            sys.exit(1)
    work_id = _validate_work_id(work_id)
    run_dir = _reject_symlinked_run_paths_or_exit(base_path, work_id)
    run_path = run_dir / "run.md"
    if not run_path.exists():
        print(f"blocked: source_run_not_found\nwork_id: {work_id}\n")
        sys.exit(7)

    from tools.workflow_cli.state import RunStateManager
    record = _load_matching_record_or_exit(
        RunStateManager(run_dir), run_dir, work_id
    )
    plan = run_dir / "07-plan.md"
    ledger = run_dir / "execution" / "progress.md"

    if record.status == RunStatus.CLOSED_AT_PLAN_CHECKPOINT:
        profile = requested_profile or "strict"
        if profile == "fast":
            if reject_fast:
                if is_json_mode():
                    print(json.dumps({
                        "status": "error",
                        "reason": "fast_profile_ineligible",
                        "exit_code": EXIT_CONFLICT,
                        "work_id": work_id,
                        "message": reason.strip(),
                    }, indent=2))
                else:
                    print(
                        "blocked: fast_profile_ineligible\n"
                        f"work_id: {work_id}\n"
                        f"reason: {reason.strip()}\n"
                    )
                sys.exit(EXIT_CONFLICT)
            if not fast_structure_eligible(record.tier_locked):
                if is_json_mode():
                    print(json.dumps({
                        "status": "error",
                        "reason": "fast_profile_ineligible",
                        "exit_code": EXIT_CONFLICT,
                        "work_id": work_id,
                        "message": "fast requires locked LIGHT tier with no modifiers",
                    }, indent=2))
                else:
                    print(
                        "blocked: fast_profile_ineligible\n"
                        f"work_id: {work_id}\n"
                        "reason: fast requires locked LIGHT tier with no modifiers\n"
                    )
                sys.exit(EXIT_CONFLICT)
            try:
                plan_text = read_regular_text(plan)
                assert plan_text is not None
                if prerequisite_semantics_version(plan_text) != 2:
                    raise ExecutionProfileError("fast requires prerequisite semantics version 2")
            except (ExecutionProfileError, UnsafeRegularFileError, FileNotFoundError) as exc:
                code = 7 if isinstance(exc, FileNotFoundError) else EXIT_CONFLICT
                if is_json_mode():
                    print(json.dumps({
                        "status": "error",
                        "reason": "fast_profile_ineligible",
                        "exit_code": code,
                        "work_id": work_id,
                        "message": str(exc),
                    }, indent=2))
                else:
                    print(f"blocked: fast_profile_ineligible\nwork_id: {work_id}\nreason: {exc}\n")
                sys.exit(code)
            if not confirm_fast:
                assert record.tier_locked is not None
                tier = record.tier_locked.base.value
                modifiers = sorted(item.value for item in record.tier_locked.modifiers)
                next_step = (
                    "review every PLAN task for local mechanical behavior, explicit safe Files, "
                    "no ambiguity or shared/core/security/migration/dependency/config risk, and "
                    "deterministic Verification; then confirm or reject fast eligibility"
                )
                if is_json_mode():
                    print(json.dumps({
                        "status": "stop",
                        "reason": "fast_profile_review",
                        "work_id": work_id,
                        "run_status": record.status.value,
                        "plan": str(plan),
                        "tier": tier,
                        "modifiers": modifiers,
                        "next": next_step,
                    }, indent=2))
                else:
                    print(
                        "stop: fast_profile_review\n"
                        f"work_id: {work_id}\n"
                        f"plan: {plan}\n"
                        f"tier: {tier}\n"
                        f"modifiers: {','.join(modifiers) if modifiers else 'none'}\n"
                        f"next: {next_step}\n"
                    )
                sys.exit(0)
        _ensure_workspace_gitignore_or_exit(base_path, work_id)
        json_mode = is_json_mode()
        cli_output = ""
        if json_mode:
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                code = _run_cli(
                    ["run-execute-start", "--work-id", work_id, "--profile", profile],
                    base_path,
                )
            cli_output = output.getvalue()
        else:
            code = _run_cli(
                ["run-execute-start", "--work-id", work_id, "--profile", profile],
                base_path,
            )
        if code != 0:
            if json_mode and cli_output:
                print(cli_output, end="" if cli_output.endswith("\n") else "\n")
            sys.exit(code)
        write_active_pointer(base_path, work_id, reason="execute_start")
        next_step = (
            "drive the r2p-execute skill (subagent-driven SDD loop) to "
            "implement each PLAN-TASK in place on the current branch, then "
            f"r2p-archive --work-id {work_id} when done"
        )
        if json_mode:
            payload = _json_payload_from_cli_output(cli_output)
            run_status = payload.get("status")
            payload.update(
                {
                    "status": "stop",
                    "reason": "execute_plan",
                    "work_id": work_id,
                    "plan": str(plan),
                    "ledger": str(ledger),
                    "effective_profile": profile,
                    "next": next_step,
                }
            )
            if isinstance(run_status, str):
                payload["run_status"] = run_status
            print(json.dumps(payload, indent=2))
            sys.exit(0)
        print(
            "stop: execute_plan\n"
            f"work_id: {work_id}\n"
            f"plan: {plan}\n"
            f"ledger: {ledger}\n"
            f"effective_profile: {profile}\n"
            f"next: {next_step}\n"
        )
        sys.exit(0)

    if record.status == RunStatus.EXECUTING:
        if confirm_fast or reject_fast:
            if is_json_mode():
                print(json.dumps({
                    "status": "error",
                    "reason": "profile_decision_on_executing_run",
                    "exit_code": EXIT_CONFLICT,
                    "work_id": work_id,
                    "message": "profile decisions are not allowed on an executing run",
                }, indent=2))
            else:
                print(
                    "blocked: profile_decision_on_executing_run\n"
                    f"work_id: {work_id}\n"
                )
            sys.exit(EXIT_CONFLICT)
        try:
            progress = read_regular_text(ledger)
            plan_text = read_regular_text(plan)
            if progress is None or plan_text is None:
                raise ExecutionProfileError("execution profile inputs are missing")
            task_ids = tuple(
                task_id
                for task_id, _ in plan_task_anchors(
                    strip_nonsemantic_markdown(plan_text)
                )
            )
            parsed_profile = parse_execution_ledger(progress, task_ids)
        except (OSError, UnsafeRegularFileError, ExecutionProfileError) as exc:
            if is_json_mode():
                print(json.dumps({
                    "status": "error",
                    "reason": "invalid_execution_profile_ledger",
                    "exit_code": EXIT_CONFLICT,
                    "work_id": work_id,
                    "message": str(exc),
                }, indent=2))
            else:
                print(
                    "blocked: invalid_execution_profile_ledger\n"
                    f"work_id: {work_id}\n"
                    f"reason: {exc}\n"
                )
            sys.exit(EXIT_CONFLICT)
        effective_profile = parsed_profile.effective_profile.value
        if requested_profile is not None and requested_profile != effective_profile:
            if is_json_mode():
                print(json.dumps({
                    "status": "error",
                    "reason": "execution_profile_conflict",
                    "exit_code": EXIT_CONFLICT,
                    "work_id": work_id,
                    "message": "requested profile does not match the effective profile",
                    "effective_profile": effective_profile,
                    "requested_profile": requested_profile,
                }, indent=2))
            else:
                print(
                    "blocked: execution_profile_conflict\n"
                    f"work_id: {work_id}\n"
                    f"effective_profile: {effective_profile}\n"
                    f"requested_profile: {requested_profile}\n"
                )
            sys.exit(EXIT_CONFLICT)
        try:
            record = start_execution_transaction(
                base_path.resolve(),
                WorkId(work_id),
                parsed_profile.initial_profile.value,
            )
        except (MetricsFormatError, PrerequisiteError, OSError) as exc:
            if is_json_mode():
                print(json.dumps({
                    "status": "error",
                    "reason": "invalid_execution_start_transaction",
                    "exit_code": EXIT_CONFLICT,
                    "work_id": work_id,
                    "message": str(exc),
                }, indent=2))
            else:
                print(
                    "blocked: invalid_execution_start_transaction\n"
                    f"work_id: {work_id}\n"
                    f"reason: {exc}\n"
                )
            sys.exit(EXIT_CONFLICT)
        _ensure_workspace_gitignore_or_exit(base_path, work_id)
        write_active_pointer(base_path, work_id, reason="execute_resume")
        first_actionable_task = parsed_profile.first_actionable_task()
        if first_actionable_task is None:
            resume_point = "continue at final review; no PLAN task remains actionable"
        else:
            resume_point = (
                f"resume the r2p-execute loop from PLAN-TASK-{first_actionable_task:03d}, "
                "the first actionable task"
            )
        next_step = (
            f"{resume_point}, then r2p-archive --work-id {work_id} when done"
        )
        if is_json_mode():
            print(
                json.dumps(
                    {
                        "status": "stop",
                        "reason": "resume_execution",
                        "work_id": work_id,
                        "run_status": record.status.value,
                        "plan": str(plan),
                        "ledger": str(ledger),
                        "effective_profile": effective_profile,
                        "first_actionable_task": first_actionable_task,
                        "next": next_step,
                    },
                    indent=2,
                )
            )
            sys.exit(0)
        print(
            "stop: resume_execution\n"
            f"work_id: {work_id}\n"
            f"plan: {plan}\n"
            f"ledger: {ledger}\n"
            f"effective_profile: {effective_profile}\n"
            f"first_actionable_task: {first_actionable_task if first_actionable_task is not None else 'none'}\n"
            f"next: {next_step}\n"
        )
        sys.exit(0)

    print(f"blocked: plan_not_ready\nwork_id: {work_id}\nstatus: {record.status.value}\nnext: r2p-continue\n")
    sys.exit(EXIT_CONFLICT)


def _cmd_task_brief(ns: argparse.Namespace, base_path: Path) -> None:
    work_id = ns.work_id
    if not work_id:
        pointer = read_active_pointer(base_path)
        work_id = pointer.get("selected_work_id") if pointer else None
        if not work_id:
            print("no_selected_run: true\nnext: r2p-task-brief --work-id <id> --task <N>\n")
            sys.exit(1)
    work_id = _validate_work_id(work_id)
    sys.exit(_run_cli(
        ["plan-task-brief", "--work-id", work_id, "--task", str(ns.task)],
        base_path,
    ))


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
    run_dir = _reject_symlinked_run_paths_or_exit(base_path, work_id)
    run_path = run_dir / "run.md"
    if not run_path.exists():
        print(f"blocked: source_run_not_found\nwork_id: {work_id}\n")
        sys.exit(7)

    from tools.workflow_cli.state import RunStateManager
    record = _load_matching_record_or_exit(
        RunStateManager(run_dir), run_dir, work_id
    )
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

    p_archive = sub.add_parser("archive")
    p_archive.add_argument("--work-id", dest="work_id", default=None)
    p_archive.add_argument("--force", action="store_true")

    p_abandon = sub.add_parser("abandon")
    p_abandon.add_argument("--work-id", dest="work_id", required=True)
    p_abandon.add_argument("--reason", required=True)

    p_tier_lock = sub.add_parser("tier-lock")
    p_tier_lock.add_argument("--work-id", dest="work_id", required=True)
    p_tier_lock.add_argument("--base", required=True, choices=["light", "standard"])
    p_tier_lock.add_argument("--modifiers", default=None)
    p_tier_lock.add_argument("--override-floor", action="store_true")
    p_tier_lock.add_argument("--confirm", action="store_true")

    p_task_brief = sub.add_parser("task-brief")
    p_task_brief.add_argument("--work-id", dest="work_id", default=None)
    p_task_brief.add_argument("--task", type=int, required=True)

    p_gap_open = sub.add_parser("gap-open")
    p_gap_open.add_argument("--work-id", dest="work_id", required=True)
    p_gap_open.add_argument("--owner-stage", dest="owner_stage", required=True)
    p_gap_open.add_argument("--required-action", dest="required_action", required=True)
    p_gap_open.add_argument("--confirm", action="store_true")

    p_gap_resolve = sub.add_parser("gap-resolve")
    p_gap_resolve.add_argument("--work-id", dest="work_id", required=True)
    p_gap_resolve.add_argument("--route-id", dest="route_id", required=True)
    p_gap_resolve.add_argument("--confirm", action="store_true")

    p_execute = sub.add_parser("execute")
    p_execute.add_argument("--work-id", dest="work_id", default=None)
    p_execute.add_argument("--profile", choices=["strict", "fast"], default=None)
    decision = p_execute.add_mutually_exclusive_group()
    decision.add_argument("--confirm-fast-eligible", action="store_true")
    decision.add_argument("--reject-fast-ineligible", action="store_true")
    p_execute.add_argument("--reason", default=None)

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
        "archive": _cmd_archive,
        "abandon": _cmd_abandon,
        "tier-lock": _cmd_tier_lock,
        "gap-open": _cmd_gap_open,
        "gap-resolve": _cmd_gap_resolve,
        "execute": _cmd_execute,
        "task-brief": _cmd_task_brief,
    }
    handlers[ns.subcommand](ns, bp)
    sys.exit(0)


if __name__ == "__main__":
    main()

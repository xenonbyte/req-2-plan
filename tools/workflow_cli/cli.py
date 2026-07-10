"""
req-to-plan workflow CLI — internal Agent command router.

Usage:
    python3 -m tools.workflow_cli [--base-path <dir>] <command> [options]
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import stat
import sys
from pathlib import Path

from tools.workflow_cli.models import (
    RunStatus,
    Stage,
    TierBase,
    TierModifier,
    WorkId,
    STAGE_ARTIFACT_MAP,
    STAGE_ORDER,
    is_command_allowed,
    is_transition_allowed,
)
from tools.workflow_cli.state import (
    RunStateManager,
    create_run_record,
    update_run_status,
    upsert_active_artifact,
    update_resume_context,
    get_active_artifact,
    add_checkpoint,
    add_open_route,
    close_route,
    record_stale_artifact,
)
from tools.workflow_cli.artifact import (
    ArtifactManager,
    write_artifact,
    read_artifact,
    get_artifact_version,
    update_artifact_status,
)
from tools.workflow_cli.gates import (
    check_entry_gate,
    check_quality_gate,
    check_forced_subagent_review,
    check_execution_complete,
    check_final_review_recorded,
)
from tools.workflow_cli.output import (
    COMPACT_DETAIL_LIMIT,
    COMPACT_FILE_LIST_LIMIT,
    compact_human_list,
    format_success,
    format_error,
    format_gate_result,
    is_json_mode,
    print_and_exit,
    EXIT_OK,
    EXIT_CLI_ERR,
    EXIT_GATE_FAIL,
    EXIT_REVIEW_REQ,
    EXIT_CONFLICT,
    EXIT_NOT_FOUND,
)
from tools.workflow_cli.tier import estimate_tier, scan_keywords
from tools.workflow_cli.workspace import ensure_workspace_gitignore, commit_requirement_dir
from tools.workflow_cli.atomic import atomic_write_text
from tools.workflow_cli.markdown import (
    PLAN_TASK_ANCHOR_RE,
    heading_bounded_bodies,
    plan_task_anchors,
    strip_readonly_sections,
)


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------


def _get_run_dir(work_id: str, base_path: Path | None = None) -> Path:
    root = base_path or Path.cwd()
    valid_work_id = _validate_work_id(str(work_id))
    return root / ".req-to-plan" / str(valid_work_id)


def _load_run(work_id: str, base_path: Path | None = None):
    """Load RunRecord; exit with EXIT_NOT_FOUND if not found.

    Rejects a symlinked workspace or run directory up front (EXIT_CONFLICT) so
    no command — read-only or mutating — ever follows `.req-to-plan` or
    `.req-to-plan/<id>` out of the workspace.
    """
    run_dir = _reject_symlinked_run_paths(work_id, base_path)
    mgr = RunStateManager(run_dir)
    try:
        record = mgr.load()
    except FileNotFoundError:
        print_and_exit(
            format_error(f"Run not found: {work_id}", exit_code=EXIT_NOT_FOUND),
            EXIT_NOT_FOUND,
        )
    requested = str(work_id)
    embedded = str(record.work_id)
    if run_dir.name != requested or embedded != requested:
        print_and_exit(
            format_error(
                "Run identity mismatch: "
                f"requested={requested!r}, directory={run_dir.name!r}, "
                f"record={embedded!r}",
                exit_code=EXIT_CONFLICT,
            ),
            EXIT_CONFLICT,
        )
    return record, mgr, run_dir


def _write_recovery_list(run_dir: Path, work_id: str, filename: str, items: list[str]) -> str | None:
    logs_dir = run_dir / "logs"
    if logs_dir.is_symlink():
        return None
    try:
        logs_dir.mkdir(parents=True, exist_ok=True)
        recovery_path = logs_dir / filename
        atomic_write_text(recovery_path, "\n".join(items) + "\n")
    except OSError:
        return None
    return f".req-to-plan/{work_id}/logs/{filename}"


def _human_list_payload(
    *,
    run_dir: Path,
    work_id: str,
    label: str,
    items: list,
    limit: int,
    recovery_filename: str,
    recovery_items: list[str] | None = None,
) -> dict:
    if is_json_mode() or len(items) <= limit:
        return {label: items}

    recovery_path = _write_recovery_list(
        run_dir,
        work_id,
        recovery_filename,
        recovery_items if recovery_items is not None else [str(item) for item in items],
    )
    if recovery_path is None:
        return {label: items}

    payload = compact_human_list(
        label=label,
        items=items,
        limit=limit,
        recovery_path=recovery_path,
    )
    payload[f"{label}_summary"] = (
        f"{payload[f'{label}_shown']} shown, {payload[f'{label}_total']} total"
    )
    return payload


def _validate_work_id(raw: str) -> WorkId:
    """Parse WorkId or exit with CLI error."""
    try:
        return WorkId(raw)
    except ValueError as e:
        print_and_exit(format_error(str(e), exit_code=EXIT_CLI_ERR), EXIT_CLI_ERR)


def _has_line_break(value: str) -> bool:
    """True if value carries a line boundary — embedded OR trailing.

    Uses str.splitlines(), the same splitter the run.md reload parser relies on
    (state._split_sections and state._parse_md_table), so this covers every
    boundary it does: \\n \\r \\r\\n \\v \\f \\x1c-\\x1e \\x85 \\u2028 \\u2029.
    Any such character lets a crafted CLI free-text value corrupt run.md on
    reload — a "## "-prefixed heading injected into a raw section line, or a
    table row split across the boundary — so callers that interpolate the value
    into run.md must reject it. Comparing against ``[value]`` (not just
    ``len(...) > 1``) also catches a single *trailing* boundary, which splits a
    table cell from the column after it. An empty value has no boundary.
    """
    return bool(value) and value.splitlines() != [value]


def _ensure_workspace_gitignore_or_exit(base_path: Path) -> None:
    try:
        ensure_workspace_gitignore(base_path)
    except ValueError as e:
        print_and_exit(format_error(str(e), exit_code=EXIT_CONFLICT), EXIT_CONFLICT)


def _reject_symlink_or_exit(path: Path, message: str) -> None:
    if path.is_symlink():
        print_and_exit(format_error(message, exit_code=EXIT_CONFLICT), EXIT_CONFLICT)


def _reject_unsafe_checkpoint_marker_or_exit(marker: Path) -> None:
    if marker.is_symlink():
        print_and_exit(
            format_error("unsafe_checkpoint_review_marker_symlink", exit_code=EXIT_CONFLICT),
            EXIT_CONFLICT,
        )
    if marker.exists() and not marker.is_file():
        print_and_exit(
            format_error("unsafe_checkpoint_review_marker_not_regular", exit_code=EXIT_CONFLICT),
            EXIT_CONFLICT,
        )


def _reject_symlinked_run_paths(work_id, base_path: Path | None) -> Path:
    """Reject a symlinked workspace or run directory, then return the run dir.

    Guards `.req-to-plan` and `.req-to-plan/<id>` up front (EXIT_CONFLICT) so no
    command — read-only or mutating — ever follows either out of the workspace.
    Call before any filesystem mutation that targets the run dir.
    """
    root = base_path or Path.cwd()
    _reject_symlink_or_exit(root / ".req-to-plan", "unsafe_workspace_dir_symlink")
    run_dir = _get_run_dir(work_id, base_path)
    _reject_symlink_or_exit(run_dir, f"Run directory is a symlink: {run_dir}")
    return run_dir


def _validate_repo_path(raw: str) -> Path:
    """Return a repo path only when it is an existing directory."""
    repo_path = Path(raw)
    if not repo_path.is_dir():
        print_and_exit(
            format_error(
                f"repo path not found or not a directory: {raw}",
                exit_code=EXIT_CLI_ERR,
            ),
            EXIT_CLI_ERR,
        )
    return repo_path


def _parse_stage(raw: str) -> Stage:
    """Parse Stage enum or exit with CLI error."""
    try:
        return Stage(raw)
    except ValueError:
        valid = [s.value for s in Stage]
        print_and_exit(
            format_error(f"Unknown stage {raw!r}. Valid: {valid}", exit_code=EXIT_CLI_ERR),
            EXIT_CLI_ERR,
        )


def _parse_reopen_stage(raw: str) -> Stage:
    """Parse a stage that can be used as the active target of a reopened run."""
    stage = _parse_stage(raw)
    if stage not in STAGE_ORDER:
        valid = [s.value for s in STAGE_ORDER]
        print_and_exit(
            format_error(
                f"Stage {raw!r} cannot be reopened into. Valid: {valid}",
                exit_code=EXIT_CLI_ERR,
            ),
            EXIT_CLI_ERR,
        )
    return stage


def _parse_tier_base(raw: str) -> TierBase:
    """Parse TierBase enum or exit with CLI error."""
    try:
        return TierBase(raw)
    except ValueError:
        valid = [b.value for b in TierBase]
        print_and_exit(
            format_error(f"Unknown tier base {raw!r}. Valid: {valid}", exit_code=EXIT_CLI_ERR),
            EXIT_CLI_ERR,
        )


def _parse_modifiers(raw: str | None) -> frozenset[TierModifier]:
    """Parse comma-separated modifier list or return empty set."""
    if not raw:
        return frozenset()
    mods: list[TierModifier] = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            mods.append(TierModifier(part))
        except ValueError:
            valid = [m.value for m in TierModifier]
            print_and_exit(
                format_error(f"Unknown modifier {part!r}. Valid: {valid}", exit_code=EXIT_CLI_ERR),
                EXIT_CLI_ERR,
            )
    return frozenset(mods)


# ---------------------------------------------------------------------------
# Run lifecycle commands
# ---------------------------------------------------------------------------


def _read_requirement_arg(args) -> str:
    """Return the raw requirement text from --requirement or --requirement-file.

    --requirement-file reads the file's contents (deterministic input ingestion).
    A missing file fails loudly with EXIT_CLI_ERR rather than silently falling back.
    """
    req_file = getattr(args, "requirement_file", None)
    if req_file:
        path = Path(req_file)
        if not path.is_file():
            print_and_exit(
                format_error(f"Requirement file not found: {req_file}", exit_code=EXIT_CLI_ERR),
                EXIT_CLI_ERR,
            )
        return path.read_text(encoding="utf-8")
    return args.requirement or ""


def _cmd_run_start(args):
    work_id = _validate_work_id(args.work_id)
    requirement = _read_requirement_arg(args)
    if not requirement.strip():
        print_and_exit(
            format_error("Requirement must not be blank", exit_code=EXIT_CLI_ERR),
            EXIT_CLI_ERR,
        )
    if args.repo_path:
        repo_path = _validate_repo_path(args.repo_path)
    else:
        # --repo-path is optional: default to the workspace root (--base-path,
        # which itself defaults to the current directory) so tier estimation and
        # the Project Context Pack are grounded in real repo facts without an
        # explicit flag. A standard-tier PLAN later requires a usable Context Pack
        # (R11), so grounding by default avoids a silent gate failure. Using
        # base_path (not literal Path.cwd()) preserves --base-path test isolation.
        repo_path = args.base_path or Path.cwd()
    run_dir = _reject_symlinked_run_paths(work_id, args.base_path)
    mgr = RunStateManager(run_dir)

    run_dir_occupied = False
    if run_dir.exists():
        run_dir_occupied = (
            True
            if run_dir.is_symlink() or not run_dir.is_dir()
            else any(run_dir.iterdir())
        )

    if run_dir_occupied and not getattr(args, "overwrite", False):
        print_and_exit(
            format_error(
                f"Run {work_id!r} already exists. Use --overwrite to reset or choose a different --work-id.",
                exit_code=EXIT_CONFLICT,
            ),
            EXIT_CONFLICT,
        )
    if run_dir_occupied and getattr(args, "overwrite", False):
        if run_dir.is_symlink() or run_dir.is_file():
            run_dir.unlink()
        else:
            shutil.rmtree(run_dir)

    # Create run record
    record = create_run_record(work_id)

    # Write raw requirement artifact
    run_dir.mkdir(parents=True, exist_ok=True)
    write_artifact(run_dir, Stage.RAW_REQUIREMENT, requirement, version=1, status="draft")

    # Tier estimation inputs
    link_results = []
    if repo_path is not None:
        from tools.workflow_cli.link_expander import expand_links
        # Local relative links expand; HTTP URLs are recorded as external references only.
        link_results = expand_links(requirement, base_path=repo_path)

    # Tier estimation
    tier_estimate, evidence = estimate_tier(requirement, repo_path=repo_path, link_results=link_results)
    record.tier_estimate = tier_estimate

    # Context Pack + link expansion (when repo_path is provided)
    if repo_path is not None:
        from tools.workflow_cli.context_pack import build_context_pack, write_context_pack
        write_context_pack(build_context_pack(repo_path), run_dir)
        if link_results:
            evidence.linked_context = "\n".join(
                f"- {r.url}: {r.status.value}"
                + (f"\n  preview: {r.content_preview}" if r.content_preview else "")
                + (f"\n  error: {r.error}" if r.error else "")
                for r in link_results
            )

    # Update active artifacts in record
    artifact_file = STAGE_ARTIFACT_MAP[Stage.RAW_REQUIREMENT]
    upsert_active_artifact(record, Stage.RAW_REQUIREMENT, artifact_file, 1, "draft")

    # Write intake brief (01-intake-brief.md) with evidence block
    brief_lines = [
        "# Intake Brief",
        "",
        f"work_id: {work_id}",
        f"requirement: {requirement}",
        "",
        "## Tier Estimate",
        f"base: {tier_estimate.base.value}",
        f"modifiers: {', '.join(sorted(m.value for m in tier_estimate.modifiers))}",
        "",
        "## Evidence Block",
        f"keywords_hit: {evidence.keywords_hit or []}",
        f"repo_baseline_summary: {evidence.repo_baseline_summary}",
        f"linked_context: {evidence.linked_context}",
        f"scope_signals: {evidence.scope_signals or []}",
        f"escalation_candidates: {evidence.escalation_candidates or []}",
        f"confirm_status: {evidence.confirm_status}",
    ]
    (run_dir / "01-intake-brief.md").write_text("\n".join(brief_lines), encoding="utf-8")

    # Save run record
    mgr.save(record)

    print_and_exit(
        format_success(
            {
                "work_id": str(work_id),
                "tier_floor": tier_estimate.base.value,
                "modifiers": sorted(m.value for m in tier_estimate.modifiers),
                "run_dir": str(run_dir),
            },
            message=f"Run started: {work_id}",
        ),
        EXIT_OK,
    )


def _cmd_run_resume(args):
    record, mgr, run_dir = _load_run(args.work_id, args.base_path)
    rc = record.resume_context
    reread_targets = list(rc.required_reread_targets)
    reread_payload = _human_list_payload(
        run_dir=run_dir,
        work_id=str(record.work_id),
        label="required_reread_targets",
        items=reread_targets,
        limit=COMPACT_FILE_LIST_LIMIT,
        recovery_filename="run-resume-reread-targets.txt",
    )
    print_and_exit(
        format_success(
            {
                "work_id": record.work_id,
                "status": record.status.value,
                "current_stage": record.current_stage.value,
                "last_operation": rc.last_completed_operation,
                "next_operation": rc.next_allowed_operation,
                "active_item": rc.active_item,
                "resume_reason": rc.resume_reason,
                **reread_payload,
            },
            message="Resume context",
        ),
        EXIT_OK,
    )


def _cmd_run_close(args):
    record, mgr, run_dir = _load_run(args.work_id, args.base_path)
    if record.status != RunStatus.CHECKPOINT_APPROVED:
        print_and_exit(
            format_error(
                f"Cannot close run in status {record.status.value!r}; "
                "must be in checkpoint_approved",
                exit_code=EXIT_CONFLICT,
            ),
            EXIT_CONFLICT,
        )
    if record.current_stage != Stage.PLAN:
        print_and_exit(
            format_error(
                f"Cannot close run at stage {record.current_stage.value!r}; "
                "current stage must be plan",
                exit_code=EXIT_CONFLICT,
            ),
            EXIT_CONFLICT,
        )
    aa = get_active_artifact(record, Stage.PLAN)
    if aa is None or aa.status != "approved":
        print_and_exit(
            format_error("PLAN active artifact must be approved before run-close", exit_code=EXIT_CONFLICT),
            EXIT_CONFLICT,
        )
    disk_version = get_artifact_version(run_dir, Stage.PLAN)
    if disk_version != aa.version:
        print_and_exit(
            format_error(
                f"Active artifact version v{aa.version} does not match on-disk v{disk_version}",
                exit_code=EXIT_CONFLICT,
            ),
            EXIT_CONFLICT,
        )
    has_matching_plan_checkpoint = any(
        cp.stage == Stage.PLAN
        and cp.artifact == aa.artifact
        and cp.version == aa.version
        for cp in record.approved_checkpoints
    )
    if not has_matching_plan_checkpoint:
        print_and_exit(
            format_error(
                f"No approved PLAN checkpoint matching {aa.artifact} v{aa.version}",
                exit_code=EXIT_CONFLICT,
            ),
            EXIT_CONFLICT,
        )
    open_routes = [r.route_id for r in record.open_routes if r.status == "open"]
    if open_routes:
        print_and_exit(
            format_error(
                "Cannot close run while routes remain open",
                details=open_routes,
                exit_code=EXIT_CONFLICT,
            ),
            EXIT_CONFLICT,
        )
    base = args.base_path or Path.cwd()
    _ensure_workspace_gitignore_or_exit(base)
    try:
        record = update_run_status(record, RunStatus.CLOSED_AT_PLAN_CHECKPOINT)
    except ValueError as e:
        print_and_exit(format_error(str(e), exit_code=EXIT_CONFLICT), EXIT_CONFLICT)
    record.current_stage = Stage.CLOSED
    update_resume_context(record, last_operation="close_at_plan_checkpoint")
    mgr.save(record)
    # PLAN complete → land the requirement directory in version control
    # (best-effort, path-limited; never touches unrelated changes). spec §4.5
    commit_requirement_dir(
        base,
        str(record.work_id),
        f"chore(r2p): plan {record.work_id}",
    )
    print_and_exit(
        format_success({"work_id": str(record.work_id), "status": record.status.value}, message="Run closed"),
        EXIT_OK,
    )


class _UnsafeReopenSourceError(ValueError):
    pass


def _reopen_candidate_work_id(base_work_id: str, suffix: int) -> WorkId:
    """Append ``-rN`` while shortening only the slug when length requires it."""
    match = re.fullmatch(r"(WF-\d{8}-)(.+)", base_work_id)
    if match is None:
        raise ValueError(f"Invalid base WorkId for reopen: {base_work_id!r}")
    prefix, slug = match.groups()
    suffix_text = f"-r{suffix}"
    while slug:
        candidate = f"{prefix}{slug}{suffix_text}"
        try:
            return WorkId(candidate)
        except ValueError:
            slug = slug[:-1].rstrip("-")
    raise ValueError(f"Could not construct a reopen WorkId for {base_work_id!r}")


def _copy_reopen_regular_file(source: Path, destination: Path) -> bool:
    """Copy one existing regular file without following a source symlink.

    ``lstat`` plus an inode/device comparison closes the fallback race on
    platforms where ``O_NOFOLLOW`` is unavailable.  The function returns
    ``False`` only when the source does not exist at all; every non-regular
    source is an explicit conflict.
    """
    try:
        before = source.lstat()
    except FileNotFoundError:
        return False
    if not stat.S_ISREG(before.st_mode):
        raise _UnsafeReopenSourceError(
            f"reopen source is not a regular file: {source}"
        )

    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        source_fd = os.open(source, flags)
    except OSError as exc:
        raise _UnsafeReopenSourceError(
            f"could not safely open reopen source {source}: {exc}"
        ) from exc

    destination_created = False
    try:
        opened = os.fstat(source_fd)
        if (
            not stat.S_ISREG(opened.st_mode)
            or opened.st_dev != before.st_dev
            or opened.st_ino != before.st_ino
        ):
            raise _UnsafeReopenSourceError(
                f"reopen source changed during validation: {source}"
            )

        destination_fd = os.open(
            destination,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            stat.S_IMODE(opened.st_mode),
        )
        destination_created = True
        with os.fdopen(source_fd, "rb") as source_stream:
            source_fd = -1
            with os.fdopen(destination_fd, "wb") as destination_stream:
                shutil.copyfileobj(source_stream, destination_stream)
        os.chmod(destination, stat.S_IMODE(opened.st_mode))
        os.utime(
            destination,
            ns=(opened.st_atime_ns, opened.st_mtime_ns),
            follow_symlinks=False,
        )
    except Exception:
        if destination_created:
            destination.unlink(missing_ok=True)
        raise
    finally:
        if source_fd >= 0:
            os.close(source_fd)
    return True


def _cmd_run_reopen(args):
    source_id = str(_validate_work_id(args.from_id))
    target_stage = _parse_reopen_stage(args.stage)

    # Load source run through the shared guard so reopen cannot follow a
    # symlinked .req-to-plan/<work-id> outside the workspace.
    source_record, source_mgr, source_dir = _load_run(source_id, args.base_path)

    # --reason is interpolated verbatim into reopen_lineage, a raw line under the
    # last run.md section; a line boundary there could inject a "## "-prefixed
    # heading that overwrites a real section on reload. Reject any line break.
    if _has_line_break(args.reason):
        print_and_exit(
            format_error("--reason must be a single line", exit_code=EXIT_CLI_ERR),
            EXIT_CLI_ERR,
        )

    reopenable_statuses = {RunStatus.CLOSED_AT_PLAN_CHECKPOINT, RunStatus.EXECUTING}
    if source_record.status not in reopenable_statuses:
        print_and_exit(
            format_error(
                f"Source run {source_id!r} is not reopenable "
                f"(status={source_record.status.value!r}); must be "
                "closed_at_plan_checkpoint or executing",
                exit_code=EXIT_CONFLICT,
            ),
            EXIT_CONFLICT,
        )

    # Determine new work_id suffix: -r1, -r2, etc.
    base = source_id
    suffix = 1
    # Remove existing -rN suffix from base if present
    m = re.match(r"^(WF-\d{8}-.+?)-r(\d+)$", source_id)
    if m:
        base = m.group(1)
        suffix = int(m.group(2)) + 1

    new_work_id = None
    new_run_dir = None
    for candidate_suffix in range(suffix, 100):
        try:
            candidate_work_id = _reopen_candidate_work_id(base, candidate_suffix)
        except ValueError:
            continue
        candidate = str(candidate_work_id)
        candidate_dir = _get_run_dir(candidate, args.base_path)
        candidate_archive_dir = (
            (args.base_path or Path.cwd())
            / ".req-to-plan"
            / "archive"
            / candidate
        )
        if not candidate_dir.exists() and not candidate_archive_dir.exists():
            new_work_id = candidate_work_id
            new_run_dir = candidate_dir
            break
    if new_work_id is None or new_run_dir is None:
        print_and_exit(
            format_error(
                f"Could not find an unused reopen work ID for {source_id!r}",
                exit_code=EXIT_CONFLICT,
            ),
            EXIT_CONFLICT,
        )

    new_run_dir_created = False
    try:
        new_run_dir.mkdir(parents=True, exist_ok=False)
        new_run_dir_created = True

        # Copy artifacts up to (not including) target_stage
        for stage in STAGE_ORDER:
            if stage == target_stage:
                break
            artifact_file = STAGE_ARTIFACT_MAP.get(stage)
            if artifact_file:
                src_path = source_dir / artifact_file
                _copy_reopen_regular_file(
                    src_path, new_run_dir / artifact_file
                )
        for context_file in ("02-project-context.json", "02-project-context.md"):
            src_path = source_dir / context_file
            _copy_reopen_regular_file(src_path, new_run_dir / context_file)

        # Create new run record
        new_record = create_run_record(new_work_id)
        new_record.tier_estimate = source_record.tier_estimate
        new_record.tier_locked = source_record.tier_locked
        source_phase = (
            "execution"
            if source_record.status == RunStatus.EXECUTING
            else "plan_checkpoint"
        )
        new_record.reopen_lineage = f"reopened_from: {source_id}@{source_phase} reason: {args.reason}"
        new_record.current_stage = target_stage

        # Copy approved checkpoints before target stage
        for cp in source_record.approved_checkpoints:
            cp_stage_idx = STAGE_ORDER.index(cp.stage) if cp.stage in STAGE_ORDER else -1
            target_idx = STAGE_ORDER.index(target_stage) if target_stage in STAGE_ORDER else 999
            if cp_stage_idx < target_idx:
                new_record.approved_checkpoints.append(cp)

        # Repopulate active_artifacts for copied stages so the reopened record
        # matches the on-disk artifacts and approved checkpoints.
        for cp in new_record.approved_checkpoints:
            # Invariant: cp.artifact == STAGE_ARTIFACT_MAP[cp.stage] (artifacts are
            # only ever created via the map, artifact.py:23). The existence check and
            # the recorded name are therefore interchangeable; no drift path exists.
            artifact_name = STAGE_ARTIFACT_MAP.get(cp.stage)
            if artifact_name and (new_run_dir / artifact_name).exists():
                upsert_active_artifact(
                    new_record,
                    stage=cp.stage,
                    artifact=cp.artifact,
                    version=cp.version,
                    status="approved",
                )

        new_mgr = RunStateManager(new_run_dir)
        new_mgr.save(new_record)
    except _UnsafeReopenSourceError as exc:
        if new_run_dir_created:
            shutil.rmtree(new_run_dir, ignore_errors=True)
        print_and_exit(
            format_error(str(exc), exit_code=EXIT_CONFLICT),
            EXIT_CONFLICT,
        )
    except Exception:
        # Roll back the partially-created new run dir so no orphan is left
        # when populate/save fails (mirrors the source-save rollback below).
        if new_run_dir_created:
            shutil.rmtree(new_run_dir, ignore_errors=True)
        raise

    if source_record.status == RunStatus.EXECUTING:
        try:
            source_record = update_run_status(source_record, RunStatus.CLOSED_AT_PLAN_CHECKPOINT)
        except ValueError as e:
            print_and_exit(format_error(str(e), exit_code=EXIT_CONFLICT), EXIT_CONFLICT)
        source_record.current_stage = Stage.CLOSED
        update_resume_context(
            source_record,
            last_operation="reopen_from_execution",
            next_operation=f"continue_reopened_run:{new_work_id}",
        )
        try:
            source_mgr.save(source_record)
        except Exception:
            # Roll back the just-created new run so no orphan is left and the
            # source stays consistently EXECUTING.
            shutil.rmtree(new_run_dir, ignore_errors=True)
            raise

    print_and_exit(
        format_success(
            {
                "new_work_id": str(new_work_id),
                "source_work_id": source_id,
                "target_stage": target_stage.value,
                "run_dir": str(new_run_dir),
            },
            message=f"Run reopened as {new_work_id}",
        ),
        EXIT_OK,
    )


def _cmd_run_archive(args):
    record, mgr, run_dir = _load_run(args.work_id, args.base_path)
    base = args.base_path or Path.cwd()
    archivable = {RunStatus.CLOSED_AT_PLAN_CHECKPOINT, RunStatus.EXECUTING}
    if record.status not in archivable:
        print_and_exit(
            format_error(
                f"Cannot archive run in status {record.status.value!r}; "
                "must be closed_at_plan_checkpoint or executing",
                exit_code=EXIT_CONFLICT,
            ),
            EXIT_CONFLICT,
        )
    # 0. Completion gate: an executing run must show every PLAN-TASK done in its
    # ledger before it can be archived. --force overrides (abandoned/superseded run).
    if record.status == RunStatus.EXECUTING and not args.force:
        gate = check_execution_complete(run_dir)
        if not gate.passed:
            detail = " ".join(gate.issues)
            print_and_exit(
                format_error(
                    f"Execution incomplete: {detail} "
                    "Re-run with --force to archive an unfinished run.",
                    exit_code=gate.exit_code,
                ),
                gate.exit_code,
            )
        # 0b. Final-review gate: the whole-branch review verdict must be recorded.
        # --force bypasses (abandoned/superseded run already skips this block).
        review_gate = check_final_review_recorded(run_dir)
        if not review_gate.passed:
            print_and_exit(
                format_error(
                    " ".join(review_gate.issues),
                    exit_code=review_gate.exit_code,
                ),
                review_gate.exit_code,
            )
    # 1. Refuse to clobber an existing archived copy before mutating state.
    archive_dir = base / ".req-to-plan" / "archive" / str(record.work_id)
    if archive_dir.exists():
        print_and_exit(
            format_error(
                f"Archive target already exists: {archive_dir}",
                exit_code=EXIT_CONFLICT,
            ),
            EXIT_CONFLICT,
        )
    # 2. Ensure /archive is ignored before anything lands under it.
    _ensure_workspace_gitignore_or_exit(base)
    # 3. Build the archived record, but do not persist it until the move succeeds.
    try:
        archived_record = update_run_status(record, RunStatus.ARCHIVED)
    except ValueError as e:
        print_and_exit(format_error(str(e), exit_code=EXIT_CONFLICT), EXIT_CONFLICT)
    _reject_symlink_or_exit(archive_dir.parent, f"Archive parent is a symlink: {archive_dir.parent}")
    archive_dir.parent.mkdir(parents=True, exist_ok=True)
    # 4. Move the run dir into the (ignored) archive, then persist ARCHIVED there.
    shutil.move(str(run_dir), str(archive_dir))
    try:
        RunStateManager(archive_dir).save(archived_record)
    except Exception:
        if archive_dir.exists() and not run_dir.exists():
            shutil.move(str(archive_dir), str(run_dir))
        raise
    # 5. Commit the removal of the original path (untracks the dir). spec §4.6
    commit_requirement_dir(
        base, str(archived_record.work_id), f"chore(r2p): archive {archived_record.work_id}"
    )
    print_and_exit(
        format_success(
            {"work_id": str(archived_record.work_id), "status": "archived", "archived_to": str(archive_dir)},
            message=f"Run archived: {archived_record.work_id}",
        ),
        EXIT_OK,
    )


def _cmd_run_execute_start(args):
    record, mgr, run_dir = _load_run(args.work_id, args.base_path)
    if record.status != RunStatus.CLOSED_AT_PLAN_CHECKPOINT:
        print_and_exit(
            format_error(
                f"Cannot start execution in status {record.status.value!r}; "
                "must be closed_at_plan_checkpoint (plan_not_ready)",
                exit_code=EXIT_CONFLICT,
            ),
            EXIT_CONFLICT,
        )
    try:
        plan_text = read_artifact(run_dir, Stage.PLAN)
    except FileNotFoundError:
        print_and_exit(
            format_error("PLAN artifact not found; cannot start execution", exit_code=EXIT_NOT_FOUND),
            EXIT_NOT_FOUND,
        )
    # Seed the structural progress ledger (IDs + checkboxes = structure, not
    # semantics; the agent appends progress). CLI never generates artifact text.
    anchors = plan_task_anchors(strip_readonly_sections(plan_text))
    if not anchors:
        print_and_exit(
            format_error(
                "PLAN contains no PLAN-TASK anchors; repair PLAN with "
                "### PLAN-TASK-NNN headings before execution",
                exit_code=EXIT_CONFLICT,
            ),
            EXIT_CONFLICT,
        )
    lines = ["# Execution Progress", "", f"work_id: {record.work_id}", ""]
    lines += [f"- [ ] {tid} {title}".rstrip() for tid, title in anchors]
    exec_dir = run_dir / "execution"
    _reject_symlink_or_exit(exec_dir, "unsafe_execution_dir_symlink")
    exec_dir.mkdir(parents=True, exist_ok=True)
    atomic_write_text(exec_dir / "progress.md", "\n".join(lines) + "\n")
    record = update_run_status(record, RunStatus.EXECUTING)
    update_resume_context(record, last_operation="execute_start", next_operation="implement_tasks")
    mgr.save(record)
    print_and_exit(
        format_success(
            {
                "work_id": str(record.work_id),
                "status": record.status.value,
                "ledger": str(exec_dir / "progress.md"),
                "task_count": len(anchors),
            },
            message=f"Execution started: {record.work_id}",
        ),
        EXIT_OK,
    )


def _cmd_gap_resolve(args):
    record, mgr, run_dir = _load_run(args.work_id, args.base_path)
    route = next(
        (r for r in record.open_routes if r.route_id == args.route_id and r.status == "open"),
        None,
    )
    if route is None:
        print_and_exit(
            format_error(f"No open route with id {args.route_id!r}", exit_code=EXIT_NOT_FOUND),
            EXIT_NOT_FOUND,
        )
    owner = route.owner_stage
    aa = get_active_artifact(record, owner)
    checkpoint_ready_statuses = {
        RunStatus.READY_FOR_CHECKPOINT_REVIEW,
        RunStatus.CHECKPOINT_REVIEW,
    }
    if aa is None or aa.status != "ready" or record.status not in checkpoint_ready_statuses:
        print_and_exit(
            format_error(
                f"Owner stage {owner.value!r} must pass gate-quality before resolving the route",
                exit_code=EXIT_CONFLICT,
            ),
            EXIT_CONFLICT,
        )
    close_route(record, args.route_id)
    next_operation = (
        "checkpoint_decide"
        if record.status == RunStatus.CHECKPOINT_REVIEW
        else "checkpoint_review"
    )
    update_resume_context(
        record, last_operation=f"gap_resolve_{args.route_id}",
        next_operation=next_operation, active_item=owner.value,
        reason=f"owner repaired for {args.route_id}; resume checkpoint approval",
    )
    mgr.save(record)
    print_and_exit(
        format_success(
            {"route_id": args.route_id, "status": "repaired", "owner_stage": owner.value,
             "resume_from": owner.value},
            message=f"Route {args.route_id} resolved; continue owner checkpoint approval",
        ),
        EXIT_OK,
    )


def _cmd_gap_open(args):
    record, mgr, run_dir = _load_run(args.work_id, args.base_path)
    owner = _parse_stage(args.owner_stage)

    if record.status == RunStatus.CLOSED_AT_PLAN_CHECKPOINT:
        print_and_exit(
            format_error("Cannot gap-open a closed run; use run-reopen", exit_code=EXIT_CONFLICT),
            EXIT_CONFLICT,
        )
    if not args.required_action or not args.required_action.strip():
        print_and_exit(
            format_error("--required-action must be non-empty", exit_code=EXIT_CLI_ERR),
            EXIT_CLI_ERR,
        )
    # required_action is interpolated into an open_routes table cell with a
    # status column after it; an embedded OR trailing line boundary splits the
    # row on reload (state._parse_md_table), corrupting run.md. Reject any break.
    if _has_line_break(args.required_action):
        print_and_exit(
            format_error("--required-action must be a single line", exit_code=EXIT_CLI_ERR),
            EXIT_CLI_ERR,
        )

    cur = record.current_stage
    if owner not in STAGE_ORDER or cur not in STAGE_ORDER:
        print_and_exit(
            format_error(f"Stage {owner.value!r} not in stage order", exit_code=EXIT_CONFLICT),
            EXIT_CONFLICT,
        )
    if STAGE_ORDER.index(owner) >= STAGE_ORDER.index(cur):
        print_and_exit(
            format_error(
                f"owner-stage {owner.value!r} must be strictly upstream of current stage {cur.value!r}",
                exit_code=EXIT_CONFLICT,
            ),
            EXIT_CONFLICT,
        )
    if not is_transition_allowed(record.status, RunStatus.UPSTREAM_GAP_ROUTING):
        print_and_exit(
            format_error(
                f"Cannot route a gap from status {record.status.value!r}; resolve the current step first",
                exit_code=EXIT_CONFLICT,
            ),
            EXIT_CONFLICT,
        )
    open_route_ids = [r.route_id for r in record.open_routes if r.status == "open"]
    if open_route_ids:
        print_and_exit(
            format_error(
                "Cannot gap-open while another route is open; resolve it before opening a new route",
                details=open_route_ids,
                exit_code=EXIT_CONFLICT,
            ),
            EXIT_CONFLICT,
        )

    run_md_path = run_dir / "run.md"
    run_md_before = run_md_path.read_text(encoding="utf-8")
    affected = []
    for d in STAGE_ORDER[STAGE_ORDER.index(owner): STAGE_ORDER.index(cur) + 1]:
        aa = get_active_artifact(record, d)
        cp = next(
            (checkpoint for checkpoint in record.approved_checkpoints if checkpoint.stage == d),
            None,
        )
        artifact_file = STAGE_ARTIFACT_MAP[d]
        artifact_path = run_dir / artifact_file
        if aa is None and cp is None and not artifact_path.exists():
            continue
        version = aa.version if aa is not None else (
            cp.version if cp is not None else get_artifact_version(run_dir, d)
        )
        if not artifact_path.exists():
            print_and_exit(
                format_error(
                    f"Cannot gap-open: downstream artifact file missing for {d.value!r}: {artifact_file}",
                    exit_code=EXIT_NOT_FOUND,
                ),
                EXIT_NOT_FOUND,
            )
        affected.append(
            (
                d,
                version,
                artifact_file,
                artifact_path,
                artifact_path.read_text(encoding="utf-8"),
            )
        )

    route_id = f"R-{len(record.open_routes) + 1}"
    am = ArtifactManager(run_dir)
    reason = f"upstream gap at {owner.value}"
    staled = []
    try:
        add_open_route(record, route_id, from_stage=cur, owner_stage=owner, required_action=args.required_action)
        for d, version, artifact_file, _artifact_path, _artifact_before in affected:
            record_stale_artifact(
                record, artifact=artifact_file, reason=reason,
                replaced_by="(pending re-derivation)", required_action=route_id,
            )
            am.mark_stale(d, reason, "(pending re-derivation)")
            upsert_active_artifact(record, d, artifact_file, version, "stale")
            record.approved_checkpoints = [cp for cp in record.approved_checkpoints if cp.stage != d]
            staled.append(d.value)

        record.current_stage = owner
        record = update_run_status(record, RunStatus.UPSTREAM_GAP_ROUTING)
        record = update_run_status(record, RunStatus.ACTIVE_STAGE_DRAFT)
        update_resume_context(
            record, last_operation=f"gap_open_{route_id}",
            next_operation="stage_update", active_item=owner.value,
            reason=f"repair owner for {route_id}",
        )
        mgr.save(record)
    except Exception as e:
        atomic_write_text(run_md_path, run_md_before)
        for _d, _aa, _artifact_file, artifact_path, artifact_before in reversed(affected):
            atomic_write_text(artifact_path, artifact_before)
        print_and_exit(
            format_error(
                f"Cannot gap-open: failed to mark downstream stale atomically ({e})",
                exit_code=EXIT_CONFLICT,
            ),
            EXIT_CONFLICT,
        )
    print_and_exit(
        format_success(
            {"route_id": route_id, "owner_stage": owner.value, "from_stage": cur.value, "staled_stages": staled},
            message=f"Gap routed to {owner.value}; repair it, then gap-resolve --route-id {route_id}",
        ),
        EXIT_OK,
    )


# ---------------------------------------------------------------------------
# Tier commands
# ---------------------------------------------------------------------------


def _cmd_tier_estimate(args):
    repo_path = Path(args.repo_path) if args.repo_path else None
    tier, evidence = estimate_tier(args.text, repo_path=repo_path)
    print_and_exit(
        format_success(
            {
                "tier_base": tier.base.value,
                "modifiers": sorted(m.value for m in tier.modifiers),
                "keywords_hit": evidence.keywords_hit or [],
                "repo_summary": evidence.repo_baseline_summary,
                "confirm_status": evidence.confirm_status,
            },
            message=f"Tier estimate: {tier.base.value}",
        ),
        EXIT_OK,
    )


def _cmd_tier_lock(args):
    record, mgr, run_dir = _load_run(args.work_id, args.base_path)

    if not is_command_allowed(record.status, "CMD-TIER-LOCK"):
        print_and_exit(
            format_error(
                f"Cannot tier-lock in status {record.status.value!r}; "
                "must be active_stage_draft",
                exit_code=EXIT_CONFLICT,
            ),
            EXIT_CONFLICT,
        )

    if not args.confirm:
        print_and_exit(
            format_error(
                "Locking tier requires --confirm",
                exit_code=EXIT_CLI_ERR,
            ),
            EXIT_CLI_ERR,
        )

    base = _parse_tier_base(args.base)
    modifiers = _parse_modifiers(args.modifiers)

    from tools.workflow_cli.models import _TIER_BASE_ORDER, TierEstimate

    if record.tier_estimate is None:
        # If no estimate, create a minimal one.
        record.tier_estimate = TierEstimate(
            base=TierBase.LIGHT, modifiers=frozenset()
        )

    if args.override_floor:
        record.tier_locked = TierEstimate(base=base, modifiers=modifiers)
    else:
        effective_floor = record.tier_estimate
        if record.tier_locked is not None:
            effective_floor = TierEstimate(
                base=max(
                    record.tier_estimate.base,
                    record.tier_locked.base,
                    key=_TIER_BASE_ORDER.index,
                ),
                modifiers=(
                    record.tier_estimate.modifiers
                    | record.tier_locked.modifiers
                ),
            )
        try:
            record.tier_locked = effective_floor.lock(base, modifiers)
        except ValueError as e:
            print_and_exit(format_error(str(e), exit_code=EXIT_CLI_ERR), EXIT_CLI_ERR)

    mgr.save(record)
    print_and_exit(
        format_success(
            {
                "work_id": str(record.work_id),
                "tier_base": record.tier_locked.base.value,
                "modifiers": sorted(m.value for m in record.tier_locked.modifiers),
            },
            message="Tier locked",
        ),
        EXIT_OK,
    )


def _cmd_tier_escalate(args):
    record, mgr, run_dir = _load_run(args.work_id, args.base_path)

    try:
        modifier = TierModifier(args.modifier)
    except ValueError:
        valid = [m.value for m in TierModifier]
        print_and_exit(
            format_error(f"Unknown modifier {args.modifier!r}. Valid: {valid}", exit_code=EXIT_CLI_ERR),
            EXIT_CLI_ERR,
        )

    if record.tier_locked is None:
        print_and_exit(
            format_error("Tier is not locked; run tier-lock first", exit_code=EXIT_CLI_ERR),
            EXIT_CLI_ERR,
        )
    if record.status == RunStatus.CHECKPOINT_APPROVED:
        print_and_exit(
            format_error(
                "Cannot escalate tier after checkpoint approval; advance or reopen the run first",
                exit_code=EXIT_CONFLICT,
            ),
            EXIT_CONFLICT,
        )
    if not is_command_allowed(record.status, "CMD-TIER-ESCALATE"):
        print_and_exit(
            format_error(
                f"Cannot tier-escalate in status {record.status.value!r}",
                exit_code=EXIT_CONFLICT,
            ),
            EXIT_CONFLICT,
        )

    previous_tier = record.tier_locked
    record.tier_locked = record.tier_locked.escalate(modifier)

    gate_passed_statuses = {
        RunStatus.READY_FOR_CHECKPOINT_REVIEW,
        RunStatus.CHECKPOINT_REVIEW,
    }
    standard_gate_became_applicable = (
        previous_tier.base != TierBase.STANDARD
        and record.tier_locked.base == TierBase.STANDARD
        and record.status in gate_passed_statuses
    )
    if standard_gate_became_applicable:
        record = update_run_status(record, RunStatus.ACTIVE_STAGE_DRAFT)
        update_resume_context(
            record,
            last_operation=f"tier_escalated_{modifier.value}",
            next_operation="gate_quality",
            active_item=record.current_stage.value,
        )

    # Revoke affected bundle authorizations that cover high-tier stages.
    # Reuse the gates definition so bundle revocation stays in lockstep with
    # forced-review behavior if the high-risk modifier set ever changes.
    from tools.workflow_cli.gates import _FORCED_REVIEW_MODIFIERS
    from datetime import datetime, timezone
    if modifier in _FORCED_REVIEW_MODIFIERS:
        revoke_ts = datetime.now(timezone.utc).isoformat()
        from tools.workflow_cli.models import STAGE_REQUIRED_UPSTREAM_CHECKPOINTS
        affected_stages = {Stage.DESIGN, Stage.SPEC, Stage.PLAN}
        for ba in record.bundle_authorizations:
            if ba.stages & affected_stages and ba.revoked_at is None:
                ba.revoked_at = revoke_ts

    mgr.save(record)
    data = {
        "work_id": str(record.work_id),
        "tier_base": record.tier_locked.base.value,
        "modifiers": sorted(m.value for m in record.tier_locked.modifiers),
        "added_modifier": modifier.value,
    }
    if (
        previous_tier.base != TierBase.STANDARD
        and record.tier_locked.base == TierBase.STANDARD
        and STAGE_ORDER.index(record.current_stage) > STAGE_ORDER.index(Stage.DESIGN)
    ):
        data["note"] = (
            "DESIGN was approved under light tier; if this escalation "
            "changes design decisions, run r2p-gap-open --work-id "
            f"{record.work_id} --owner-stage design "
            '--required-action "<describe the design impact>"'
        )
    print_and_exit(
        format_success(
            data,
            message=f"Tier escalated with modifier: {modifier.value}",
        ),
        EXIT_OK,
    )


def _cmd_tier_status(args):
    record, mgr, run_dir = _load_run(args.work_id, args.base_path)

    est = record.tier_estimate
    locked = record.tier_locked

    data = {
        "work_id": str(record.work_id),
        "tier_estimate": (
            {"base": est.base.value, "modifiers": sorted(m.value for m in est.modifiers)}
            if est else "none"
        ),
        "tier_locked": (
            {"base": locked.base.value, "modifiers": sorted(m.value for m in locked.modifiers)}
            if locked else "unlocked"
        ),
    }
    print_and_exit(format_success(data, message="Tier status"), EXIT_OK)


# ---------------------------------------------------------------------------
# Gate commands
# ---------------------------------------------------------------------------


def _cmd_gate_entry(args):
    record, mgr, run_dir = _load_run(args.work_id, args.base_path)
    stage = _parse_stage(args.stage)

    # Precondition: if in NEXT_STAGE or ENTRY_GATE_FAILED, stage must match current_stage
    if record.status in (RunStatus.NEXT_STAGE, RunStatus.ENTRY_GATE_FAILED) and stage != record.current_stage:
        print_and_exit(
            format_error(
                f"Cannot run entry gate for {stage.value!r}; current stage is {record.current_stage.value!r}",
                exit_code=EXIT_CONFLICT,
            ),
            EXIT_CONFLICT,
        )

    result = check_entry_gate(
        run_dir,
        stage,
        record.approved_checkpoints,
        record.bundle_authorizations,
    )

    # Persist state if in NEXT_STAGE or ENTRY_GATE_FAILED
    if record.status in (RunStatus.NEXT_STAGE, RunStatus.ENTRY_GATE_FAILED):
        target = RunStatus.ACTIVE_STAGE_DRAFT if result.passed else RunStatus.ENTRY_GATE_FAILED
        if target != record.status:
            record = update_run_status(record, target)
        update_resume_context(
            record,
            last_operation=f"entry_gate_{'passed' if result.passed else 'failed'}_{stage.value}",
            next_operation="produce_stage_artifact" if result.passed else "repair_upstream_checkpoint",
            active_item=stage.value,
        )
        mgr.save(record)

    output = format_gate_result(result, gate_type="entry-gate")
    exit_code = EXIT_OK if result.passed else result.exit_code
    print_and_exit(output, exit_code)


def _cmd_gate_quality(args):
    record, mgr, run_dir = _load_run(args.work_id, args.base_path)
    stage = _parse_stage(args.stage)

    # Precondition: only an active draft can be quality-gated. Re-running after a
    # pass (ready_for_checkpoint_review) or failure (quality_gate_failed) would
    # otherwise attempt an illegal self-transition; return a clean conflict instead.
    if record.status != RunStatus.ACTIVE_STAGE_DRAFT:
        print_and_exit(
            format_error(
                f"Cannot run quality gate in status {record.status.value!r}; "
                "must be active_stage_draft",
                exit_code=EXIT_CONFLICT,
            ),
            EXIT_CONFLICT,
        )

    # Precondition: stage must be current and artifact must be ready
    if stage != record.current_stage:
        print_and_exit(
            format_error(
                f"Stage {stage.value!r} is not the current stage {record.current_stage.value!r}",
                exit_code=EXIT_CONFLICT,
            ),
            EXIT_CONFLICT,
        )
    aa = get_active_artifact(record, stage)
    if aa is None or aa.status != "ready":
        print_and_exit(
            format_error(
                f"Stage {stage.value!r} artifact is not ready; run stage-ready first",
                exit_code=EXIT_CONFLICT,
            ),
            EXIT_CONFLICT,
        )
    version = get_artifact_version(run_dir, stage)
    if version != aa.version:
        print_and_exit(
            format_error(
                f"Active artifact version v{aa.version} does not match on-disk v{version}",
                exit_code=EXIT_CONFLICT,
            ),
            EXIT_CONFLICT,
        )

    # Read artifact content
    try:
        content = read_artifact(run_dir, stage)
    except FileNotFoundError:
        print_and_exit(
            format_error(
                f"Artifact not found for stage {stage.value!r}",
                exit_code=EXIT_NOT_FOUND,
            ),
            EXIT_NOT_FOUND,
        )

    # Check quality gate
    result = check_quality_gate(
        run_dir,
        stage,
        record.tier_locked,
        record.approved_checkpoints,
        content,
    )

    if not result.passed:
        if record.tier_locked is None:
            print_and_exit(format_gate_result(result, gate_type="quality-gate"), result.exit_code)

        record = update_run_status(record, RunStatus.QUALITY_GATE_FAILED)
        update_resume_context(
            record,
            last_operation=f"quality_gate_failed_{stage.value}",
            next_operation="repair_stage_artifact",
            active_item=stage.value,
        )
        mgr.save(record)
        print_and_exit(format_gate_result(result, gate_type="quality-gate"), result.exit_code)

    record = update_run_status(record, RunStatus.READY_FOR_CHECKPOINT_REVIEW)
    update_resume_context(
        record,
        last_operation=f"quality_gate_passed_{stage.value}",
        next_operation="checkpoint_review",
        active_item=stage.value,
    )
    mgr.save(record)
    print_and_exit(format_gate_result(result, gate_type="quality-gate"), EXIT_OK)


# ---------------------------------------------------------------------------
# Status commands
# ---------------------------------------------------------------------------


def _cmd_status_run(args):
    record, mgr, run_dir = _load_run(args.work_id, args.base_path)

    open_route_ids = [r.route_id for r in record.open_routes if r.status == "open"]
    open_routes_detail = [
        {
            "route_id": r.route_id,
            "from_stage": r.from_stage.value,
            "owner_stage": r.owner_stage.value,
            "required_action": r.required_action,
            "status": r.status,
        }
        for r in record.open_routes
        if r.status == "open"
    ]
    stale_artifacts = [
        {
            "artifact": s.artifact,
            "reason": s.reason,
            "replaced_by": s.replaced_by,
            "required_action": s.required_action,
        }
        for s in record.stale_artifacts
    ]
    outstanding_stale = [aa.stage.value for aa in record.active_artifacts if aa.status == "stale"]
    approved_checkpoints = [cp.stage.value for cp in record.approved_checkpoints]
    approved_payload = _human_list_payload(
        run_dir=run_dir,
        work_id=str(record.work_id),
        label="approved_checkpoints",
        items=approved_checkpoints,
        limit=COMPACT_DETAIL_LIMIT,
        recovery_filename="status-run-approved-checkpoints.txt",
        recovery_items=[
            (
                f"{cp.stage.value}\t{cp.artifact}\tv{cp.version}\t"
                f"{cp.approved_at}\t{cp.downstream_authorization}\t{cp.bundle_id or ''}"
            )
            for cp in record.approved_checkpoints
        ],
    )

    print_and_exit(
        format_success(
            {
                "work_id": str(record.work_id),
                "status": record.status.value,
                "current_stage": record.current_stage.value,
                "tier_locked": (
                    record.tier_locked.base.value if record.tier_locked else "unlocked"
                ),
                "open_routes": open_route_ids,
                "open_routes_detail": open_routes_detail,
                "stale_artifacts": stale_artifacts,
                "outstanding_stale": outstanding_stale,
                **approved_payload,
            },
            message="Run status",
        ),
        EXIT_OK,
    )


def _cmd_status_next(args):
    record, mgr, run_dir = _load_run(args.work_id, args.base_path)
    rc = record.resume_context
    print_and_exit(
        format_success(
            {
                "work_id": str(record.work_id),
                "next_allowed_operation": rc.next_allowed_operation,
                "active_item": rc.active_item,
                "last_completed_operation": rc.last_completed_operation,
                "resume_reason": rc.resume_reason,
            },
            message="Next operation",
        ),
        EXIT_OK,
    )


# ---------------------------------------------------------------------------
# Stage commands
# ---------------------------------------------------------------------------


def _resolve_content(args) -> str:
    """Resolve content from --content or --content-file option."""
    if args.content:
        return args.content
    if args.content_file:
        path = Path(args.content_file)
        if not path.exists():
            print_and_exit(
                format_error(f"Content file not found: {path}", exit_code=EXIT_NOT_FOUND),
                EXIT_NOT_FOUND,
            )
        return path.read_text(encoding="utf-8")
    print_and_exit(
        format_error("Either --content or --content-file is required", exit_code=EXIT_CLI_ERR),
        EXIT_CLI_ERR,
    )


def _cmd_stage_produce(args):
    record, mgr, run_dir = _load_run(args.work_id, args.base_path)
    stage = _parse_stage(args.stage)
    repair_state = record.status in (
        RunStatus.CHECKPOINT_CHANGES_REQUESTED,
        RunStatus.QUALITY_GATE_FAILED,
    )

    if record.status in (RunStatus.NEXT_STAGE, RunStatus.ENTRY_GATE_FAILED):
        next_step = "gate-entry first to enter the stage draft"
        if record.status == RunStatus.ENTRY_GATE_FAILED:
            next_step = "gate-entry after repairing upstream checkpoints"
        print_and_exit(
            format_error(
                f"Cannot produce in {record.status.value}; run {next_step}",
                exit_code=EXIT_CONFLICT,
            ),
            EXIT_CONFLICT,
        )

    if stage != record.current_stage:
        print_and_exit(
            format_error(
                f"Cannot produce stage {stage.value!r}; current stage is "
                f"{record.current_stage.value!r}",
                exit_code=EXIT_CONFLICT,
            ),
            EXIT_CONFLICT,
        )

    entry_result = check_entry_gate(
        run_dir,
        stage,
        record.approved_checkpoints,
        record.bundle_authorizations,
    )
    if not entry_result.passed:
        if not repair_state:
            record = update_run_status(record, RunStatus.ENTRY_GATE_FAILED)
        update_resume_context(
            record,
            last_operation=f"entry_gate_failed_{stage.value}",
            next_operation="repair_upstream_checkpoint",
            active_item=stage.value,
        )
        mgr.save(record)
        print_and_exit(
            format_gate_result(entry_result, gate_type="entry-gate"),
            entry_result.exit_code,
        )

    content = _resolve_content(args)

    am = ArtifactManager(run_dir)
    artifact_file = STAGE_ARTIFACT_MAP[stage]
    try:
        if repair_state:
            path = am.stage_update(stage, content)
            from tools.workflow_cli.artifact import get_artifact_version
            new_version = get_artifact_version(run_dir, stage)
        else:
            path = am.stage_produce(stage, content)
            new_version = 1
    except FileExistsError as e:
        print_and_exit(format_error(str(e), exit_code=EXIT_CONFLICT), EXIT_CONFLICT)

    # Update run record active artifacts
    record = update_run_status(record, RunStatus.ACTIVE_STAGE_DRAFT)
    upsert_active_artifact(record, stage, artifact_file, new_version, "draft")
    update_resume_context(record, last_operation=f"produce_{stage.value}")
    mgr.save(record)

    print_and_exit(
        format_success(
            {"work_id": str(record.work_id), "stage": stage.value, "artifact": str(path)},
            message=f"Artifact produced for stage: {stage.value}",
        ),
        EXIT_OK,
    )


def _cmd_stage_update(args):
    record, mgr, run_dir = _load_run(args.work_id, args.base_path)
    stage = _parse_stage(args.stage)

    if record.status in (RunStatus.NEXT_STAGE, RunStatus.ENTRY_GATE_FAILED):
        next_step = "gate-entry first to enter the stage draft"
        if record.status == RunStatus.ENTRY_GATE_FAILED:
            next_step = "gate-entry after repairing upstream checkpoints"
        print_and_exit(
            format_error(
                f"Cannot update in {record.status.value}; run {next_step}",
                exit_code=EXIT_CONFLICT,
            ),
            EXIT_CONFLICT,
        )

    if record.status == RunStatus.CHECKPOINT_REVIEW:
        print_and_exit(
            format_error(
                "Cannot update artifacts while checkpoint review is open; "
                "use checkpoint-decide to approve or request changes first",
                exit_code=EXIT_CONFLICT,
            ),
            EXIT_CONFLICT,
        )
    if record.status == RunStatus.CHECKPOINT_APPROVED:
        print_and_exit(
            format_error(
                "Cannot update artifacts after checkpoint approval; "
                "use stage-advance or run-close",
                exit_code=EXIT_CONFLICT,
            ),
            EXIT_CONFLICT,
        )

    if stage != record.current_stage:
        print_and_exit(
            format_error(
                f"Cannot update stage {stage.value!r}; current stage is "
                f"{record.current_stage.value!r}",
                exit_code=EXIT_CONFLICT,
            ),
            EXIT_CONFLICT,
        )

    # Repair and post-gate edits invalidate the current artifact's gate/review readiness.
    repair_state = record.status in (
        RunStatus.CHECKPOINT_CHANGES_REQUESTED,
        RunStatus.QUALITY_GATE_FAILED,
    )
    review_ready_state = record.status == RunStatus.READY_FOR_CHECKPOINT_REVIEW
    needs_draft_reset = repair_state or review_ready_state

    content = _resolve_content(args)

    am = ArtifactManager(run_dir)
    path = am.stage_update(stage, content)

    # Update run record
    from tools.workflow_cli.artifact import get_artifact_version
    new_version = get_artifact_version(run_dir, stage)
    artifact_file = STAGE_ARTIFACT_MAP[stage]
    upsert_active_artifact(record, stage, artifact_file, new_version, "draft")

    # Any post-gate edit invalidates the previous gate/review readiness.
    # The stage must be marked ready and pass gate-quality again.
    if needs_draft_reset:
        record = update_run_status(record, RunStatus.ACTIVE_STAGE_DRAFT)

    update_resume_context(record, last_operation=f"update_{stage.value}")
    mgr.save(record)

    print_and_exit(
        format_success(
            {
                "work_id": str(record.work_id),
                "stage": stage.value,
                "artifact": str(path),
                "version": new_version,
            },
            message=f"Artifact updated for stage: {stage.value}",
        ),
        EXIT_OK,
    )


def _cmd_stage_ready(args):
    record, mgr, run_dir = _load_run(args.work_id, args.base_path)
    stage = _parse_stage(args.stage)

    stage_ready_statuses = {
        RunStatus.ACTIVE_STAGE_DRAFT,
        RunStatus.QUALITY_GATE_FAILED,
    }
    if record.status not in stage_ready_statuses:
        print_and_exit(
            format_error(
                f"Cannot mark artifacts ready in status {record.status.value!r}; "
                "stage-ready is only allowed while drafting or after quality-gate failure; "
                "checkpoint changes_requested requires stage-update or stage-produce first",
                exit_code=EXIT_CONFLICT,
            ),
            EXIT_CONFLICT,
        )

    repair_state = record.status == RunStatus.QUALITY_GATE_FAILED

    if stage != record.current_stage:
        print_and_exit(
            format_error(
                f"Cannot mark stage {stage.value!r} ready while current stage is "
                f"{record.current_stage.value!r}",
                exit_code=EXIT_CONFLICT,
            ),
            EXIT_CONFLICT,
        )

    am = ArtifactManager(run_dir)
    try:
        am.stage_ready(stage)
    except FileNotFoundError:
        print_and_exit(
            format_error(
                f"Artifact not found for stage {stage.value!r}; produce it first",
                exit_code=EXIT_NOT_FOUND,
            ),
            EXIT_NOT_FOUND,
        )
    except ValueError as e:
        print_and_exit(
            format_error(str(e), exit_code=EXIT_CONFLICT),
            EXIT_CONFLICT,
        )

    # Update run record
    from tools.workflow_cli.artifact import get_artifact_version
    version = get_artifact_version(run_dir, stage)
    artifact_file = STAGE_ARTIFACT_MAP[stage]
    upsert_active_artifact(record, stage, artifact_file, version, "ready")
    if repair_state:
        record = update_run_status(record, RunStatus.ACTIVE_STAGE_DRAFT)
    update_resume_context(record, last_operation=f"ready_{stage.value}")
    mgr.save(record)

    print_and_exit(
        format_success(
            {"work_id": str(record.work_id), "stage": stage.value},
            message=f"Stage marked ready: {stage.value}",
        ),
        EXIT_OK,
    )


# ---------------------------------------------------------------------------
# plan-task-brief
# ---------------------------------------------------------------------------


def _positive_int(raw: str) -> int:
    """argparse type: positive integer (>= 1); raises ArgumentTypeError → exit 2."""
    try:
        n = int(raw)
    except ValueError:
        raise argparse.ArgumentTypeError(f"expected a positive integer, got {raw!r}")
    if n < 1:
        raise argparse.ArgumentTypeError(f"task number must be >= 1, got {n}")
    return n


def _cmd_plan_task_brief(args):
    """Write a read-only task brief for one PLAN-TASK-NNN to logs/task-N-brief.md."""
    record, mgr, run_dir = _load_run(args.work_id, args.base_path)
    if record.status != RunStatus.EXECUTING:
        print_and_exit(
            format_error(
                "plan-task-brief requires an EXECUTING run",
                exit_code=EXIT_CONFLICT,
            ),
            EXIT_CONFLICT,
        )
    try:
        plan_text = read_artifact(run_dir, Stage.PLAN)
    except FileNotFoundError:
        print_and_exit(
            format_error("PLAN artifact not found", exit_code=EXIT_NOT_FOUND),
            EXIT_NOT_FOUND,
        )
    stripped = strip_readonly_sections(plan_text)
    anchors = plan_task_anchors(stripped)
    bodies = list(heading_bounded_bodies(stripped, PLAN_TASK_ANCHOR_RE.match))
    target_idx = None
    for i, (tid, _title) in enumerate(anchors):
        m = re.match(r"PLAN-TASK-(\d+)", tid)
        if m and int(m.group(1)) == args.task:
            target_idx = i
            break
    if target_idx is None:
        print_and_exit(
            format_error(f"task {args.task} not found in PLAN", exit_code=EXIT_NOT_FOUND),
            EXIT_NOT_FOUND,
        )
    task_id = anchors[target_idx][0]
    body = bodies[target_idx]
    logs_dir = run_dir / "logs"
    _reject_symlink_or_exit(logs_dir, "logs dir is a symlink")
    brief_path = logs_dir / f"task-{args.task}-brief.md"
    _reject_symlink_or_exit(brief_path, "brief target is a symlink")
    logs_dir.mkdir(parents=True, exist_ok=True)
    atomic_write_text(brief_path, body)
    rel = brief_path.relative_to(run_dir.parent.parent)
    print_and_exit(
        format_success(
            {
                "work_id": args.work_id,
                "task_id": task_id,
                "brief_path": rel.as_posix(),
            },
            message="task brief written",
        ),
        EXIT_OK,
    )


# ---------------------------------------------------------------------------
# Subparser registration
# ---------------------------------------------------------------------------


def _register_run_commands(subparsers):
    # run-start
    p = subparsers.add_parser("run-start", help="Start a new workflow run")
    p.add_argument("--work-id", required=True, help="Workflow ID (WF-YYYYMMDD-slug)")
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("--requirement", default=None, help="Raw requirement text")
    src.add_argument(
        "--requirement-file",
        dest="requirement_file",
        default=None,
        help="Path to a file whose contents are the raw requirement",
    )
    p.add_argument(
        "--repo-path",
        default=None,
        help="Path to repository for baseline scan (default: current directory / --base-path)",
    )
    p.add_argument("--overwrite", action="store_true", help="Overwrite an existing run")
    p.set_defaults(func=_cmd_run_start)

    # run-resume
    p = subparsers.add_parser("run-resume", help="Resume a workflow run")
    p.add_argument("--work-id", required=True)
    p.set_defaults(func=_cmd_run_resume)

    # run-close
    p = subparsers.add_parser("run-close", help="Close a workflow run")
    p.add_argument("--work-id", required=True)
    p.set_defaults(func=_cmd_run_close)

    # run-reopen
    p = subparsers.add_parser(
        "run-reopen",
        help="Reopen a closed or executing workflow run",
    )
    p.add_argument("--from", dest="from_id", required=True, help="Source work-id to reopen from")
    p.add_argument("--stage", required=True, help="Target stage to reopen at")
    p.add_argument("--reason", required=True, help="Reason for reopening")
    p.set_defaults(func=_cmd_run_reopen)

    # run-archive
    p = subparsers.add_parser("run-archive", help="Archive a closed run out of the active workspace")
    p.add_argument("--work-id", required=True)
    p.add_argument(
        "--force",
        action="store_true",
        help="Archive an executing run even if its execution ledger is missing or has unfinished tasks",
    )
    p.set_defaults(func=_cmd_run_archive)

    # run-execute-start
    p = subparsers.add_parser("run-execute-start", help="Begin executing a closed run's PLAN in place")
    p.add_argument("--work-id", required=True)
    p.set_defaults(func=_cmd_run_execute_start)

    # plan-task-brief
    p = subparsers.add_parser(
        "plan-task-brief",
        help="Write a read-only brief for one PLAN task to logs/task-N-brief.md",
    )
    p.add_argument("--work-id", required=True, help="Workflow run ID")
    p.add_argument(
        "--task",
        required=True,
        type=_positive_int,
        help="Task number to extract (positive integer, e.g. 2 for PLAN-TASK-002)",
    )
    p.set_defaults(func=_cmd_plan_task_brief)


def _register_tier_commands(subparsers):
    # tier-estimate
    p = subparsers.add_parser("tier-estimate", help="Estimate tier for requirement text")
    p.add_argument("--text", required=True, help="Requirement text to estimate")
    p.add_argument("--repo-path", default=None, help="Path to repository for baseline scan")
    p.set_defaults(func=_cmd_tier_estimate)

    # tier-lock
    p = subparsers.add_parser("tier-lock", help="Lock tier for a run")
    p.add_argument("--work-id", required=True)
    p.add_argument("--base", required=True, choices=["light", "standard"])
    p.add_argument("--modifiers", default=None, help="Comma-separated modifiers")
    p.add_argument("--override-floor", action="store_true", help="Allow locking below floor")
    p.add_argument("--confirm", action="store_true", help="Required confirmation before locking tier")
    p.set_defaults(func=_cmd_tier_lock)

    # tier-escalate
    p = subparsers.add_parser("tier-escalate", help="Add a modifier to locked tier")
    p.add_argument("--work-id", required=True)
    p.add_argument(
        "--modifier",
        required=True,
        choices=[m.value for m in TierModifier],
        help="Modifier to add",
    )
    p.set_defaults(func=_cmd_tier_escalate)

    # tier-status
    p = subparsers.add_parser("tier-status", help="Print tier estimate and lock status")
    p.add_argument("--work-id", required=True)
    p.set_defaults(func=_cmd_tier_status)


def _register_gate_commands(subparsers):
    # gate-entry
    p = subparsers.add_parser("gate-entry", help="Check entry gate for a stage")
    p.add_argument("--work-id", required=True)
    p.add_argument("--stage", required=True)
    p.set_defaults(func=_cmd_gate_entry)

    # gate-quality
    p = subparsers.add_parser("gate-quality", help="Check quality gate for a stage")
    p.add_argument("--work-id", required=True)
    p.add_argument("--stage", required=True)
    p.set_defaults(func=_cmd_gate_quality)


def _register_status_commands(subparsers):
    # status-run
    p = subparsers.add_parser("status-run", help="Print run state, stage, tier, open routes")
    p.add_argument("--work-id", required=True)
    p.set_defaults(func=_cmd_status_run)

    # status-next
    p = subparsers.add_parser("status-next", help="Print next allowed operation from resume context")
    p.add_argument("--work-id", required=True)
    p.set_defaults(func=_cmd_status_next)


def _cmd_review_checkpoint(args):
    record, mgr, run_dir = _load_run(args.work_id, args.base_path)
    stage = _parse_stage(args.stage)

    if record.status not in {
        RunStatus.READY_FOR_CHECKPOINT_REVIEW,
        RunStatus.CHECKPOINT_REVIEW,
    }:
        print_and_exit(
            format_error(
                f"Cannot review-checkpoint in status {record.status.value!r}; "
                "must be ready_for_checkpoint_review or checkpoint_review",
                exit_code=EXIT_CONFLICT,
            ),
            EXIT_CONFLICT,
        )
    if stage != record.current_stage:
        print_and_exit(
            format_error(
                f"Stage {stage.value!r} is not the current stage {record.current_stage.value!r}",
                exit_code=EXIT_CONFLICT,
            ),
            EXIT_CONFLICT,
        )

    aa = get_active_artifact(record, stage)
    if aa is None:
        print_and_exit(
            format_error(f"No active artifact for stage {stage.value!r}", exit_code=EXIT_CONFLICT),
            EXIT_CONFLICT,
        )
    if aa.status != "ready":
        print_and_exit(
            format_error(
                f"Stage {stage.value!r} artifact must be ready before checkpoint review",
                exit_code=EXIT_CONFLICT,
            ),
            EXIT_CONFLICT,
        )
    version = get_artifact_version(run_dir, stage)
    if version != aa.version:
        print_and_exit(
            format_error(
                f"Active artifact version v{aa.version} does not match on-disk v{version}",
                exit_code=EXIT_CONFLICT,
            ),
            EXIT_CONFLICT,
        )
    reviews_dir = run_dir / "reviews"
    _reject_symlink_or_exit(reviews_dir, "unsafe_reviews_dir_symlink")
    reviews_dir.mkdir(parents=True, exist_ok=True)
    marker = reviews_dir / f"{stage.value}-checkpoint-review-v{aa.version}.md"
    _reject_unsafe_checkpoint_marker_or_exit(marker)
    atomic_write_text(
        marker,
        f"# Checkpoint review marker\n\nstage: {stage.value}\nversion: {aa.version}\n"
        "status: ready for human decision\n",
    )

    if record.status == RunStatus.READY_FOR_CHECKPOINT_REVIEW:
        record = update_run_status(record, RunStatus.CHECKPOINT_REVIEW)
    update_resume_context(
        record,
        last_operation=f"review_checkpoint_{stage.value}",
        next_operation="checkpoint_decide",
        active_item=stage.value,
    )
    mgr.save(record)
    print_and_exit(
        format_success(
            {"work_id": str(record.work_id), "stage": stage.value, "marker": str(marker)},
            message=f"Checkpoint review opened: {stage.value}",
        ),
        EXIT_OK,
    )


def _register_stage_commands(subparsers):
    def _add_content_args(p):
        grp = p.add_mutually_exclusive_group()
        grp.add_argument("--content", default=None, help="Artifact content (inline)")
        grp.add_argument("--content-file", default=None, help="Path to file containing content")

    # stage-produce
    p = subparsers.add_parser("stage-produce", help="Write initial draft of a stage artifact")
    p.add_argument("--work-id", required=True)
    p.add_argument("--stage", required=True)
    _add_content_args(p)
    p.set_defaults(func=_cmd_stage_produce)

    # stage-update
    p = subparsers.add_parser("stage-update", help="Increment version and update stage artifact")
    p.add_argument("--work-id", required=True)
    p.add_argument("--stage", required=True)
    _add_content_args(p)
    p.set_defaults(func=_cmd_stage_update)

    # stage-ready
    p = subparsers.add_parser("stage-ready", help="Mark a stage artifact as ready")
    p.add_argument("--work-id", required=True)
    p.add_argument("--stage", required=True)
    p.set_defaults(func=_cmd_stage_ready)


def _cmd_checkpoint_decide(args):
    record, mgr, run_dir = _load_run(args.work_id, args.base_path)
    stage = _parse_stage(args.stage)

    if record.status != RunStatus.CHECKPOINT_REVIEW:
        print_and_exit(
            format_error(
                f"Cannot decide in status {record.status.value!r}; must be checkpoint_review",
                exit_code=EXIT_CONFLICT,
            ),
            EXIT_CONFLICT,
        )
    if stage != record.current_stage:
        print_and_exit(
            format_error(
                f"Stage {stage.value!r} is not the current stage {record.current_stage.value!r}",
                exit_code=EXIT_CONFLICT,
            ),
            EXIT_CONFLICT,
        )

    aa = get_active_artifact(record, stage)
    if aa is None:
        print_and_exit(
            format_error(f"No active artifact for stage {stage.value!r}", exit_code=EXIT_CONFLICT),
            EXIT_CONFLICT,
        )
    if aa.status != "ready":
        print_and_exit(
            format_error(
                f"Stage {stage.value!r} artifact must be ready before checkpoint decision",
                exit_code=EXIT_CONFLICT,
            ),
            EXIT_CONFLICT,
        )
    version = get_artifact_version(run_dir, stage)
    if version != aa.version:
        print_and_exit(
            format_error(
                f"Active artifact version v{aa.version} does not match on-disk v{version}",
                exit_code=EXIT_CONFLICT,
            ),
            EXIT_CONFLICT,
        )

    reviews_dir = run_dir / "reviews"
    _reject_symlink_or_exit(reviews_dir, "unsafe_reviews_dir_symlink")
    # Precondition: checkpoint-review marker for this version must exist (GR5).
    marker = reviews_dir / f"{stage.value}-checkpoint-review-v{aa.version}.md"
    _reject_unsafe_checkpoint_marker_or_exit(marker)
    if not marker.exists():
        print_and_exit(
            format_error(
                f"Missing checkpoint-review marker for {stage.value} v{aa.version}; "
                "run review-checkpoint first",
                exit_code=EXIT_REVIEW_REQ,
            ),
            EXIT_REVIEW_REQ,
        )

    if args.decision == "changes_requested":
        record = update_run_status(record, RunStatus.CHECKPOINT_CHANGES_REQUESTED)
        update_resume_context(
            record,
            last_operation=f"changes_requested_{stage.value}",
            next_operation="repair_stage_artifact",
            active_item=stage.value,
        )
        mgr.save(record)
        print_and_exit(
            format_success(
                {"work_id": str(record.work_id), "stage": stage.value, "decision": "changes_requested"},
                message=f"Changes requested: {stage.value}",
            ),
            EXIT_OK,
        )

    # decision == "approved"
    if not args.confirm:
        print_and_exit(
            format_error(
                "Approval requires --confirm",
                exit_code=EXIT_REVIEW_REQ,
            ),
            EXIT_REVIEW_REQ,
        )

    # --downstream-authorization is stored in the Approved Checkpoints table.
    # A line boundary there splits the row on reload, so reject embedded or
    # trailing breaks before any approve-path mutation.
    if args.downstream_authorization and _has_line_break(args.downstream_authorization):
        print_and_exit(
            format_error(
                "--downstream-authorization must be a single line",
                exit_code=EXIT_CLI_ERR,
            ),
            EXIT_CLI_ERR,
        )

    open_routes = [r.route_id for r in record.open_routes if r.status == "open"]
    if open_routes:
        print_and_exit(
            format_error(
                "Cannot approve checkpoint while routes remain open",
                details=open_routes,
                exit_code=EXIT_CONFLICT,
            ),
            EXIT_CONFLICT,
        )

    # Duplicate-approval guard.
    if any(cp.stage == stage and cp.version == aa.version for cp in record.approved_checkpoints):
        print_and_exit(
            format_error(
                f"Stage {stage.value!r} v{aa.version} already has an approved checkpoint",
                exit_code=EXIT_CONFLICT,
            ),
            EXIT_CONFLICT,
        )

    # Forced-review guard (version-aware; subagent file required).
    review_result = check_forced_subagent_review(stage, record.tier_locked, reviews_dir, aa.version)
    if not review_result.passed:
        print_and_exit(
            format_gate_result(review_result, gate_type="subagent-review"),
            review_result.exit_code,
        )

    from tools.workflow_cli.models import NEXT_STAGE_MAP
    next_stage = NEXT_STAGE_MAP.get(stage)
    downstream = args.downstream_authorization or (next_stage.value if next_stage else "close_workflow_run")
    artifact_file = STAGE_ARTIFACT_MAP[stage]
    add_checkpoint(record, stage, artifact_file, aa.version, downstream)
    upsert_active_artifact(record, stage, artifact_file, aa.version, "approved")
    update_artifact_status(run_dir, stage, "approved")
    record = update_run_status(record, RunStatus.CHECKPOINT_APPROVED)
    update_resume_context(
        record,
        last_operation=f"approved_{stage.value}",
        next_operation="stage_advance" if next_stage else "run_close",
        active_item=stage.value,
    )
    mgr.save(record)
    print_and_exit(
        format_success(
            {"work_id": str(record.work_id), "stage": stage.value, "decision": "approved"},
            message=f"Checkpoint approved: {stage.value}",
        ),
        EXIT_OK,
    )


def _cmd_stage_advance(args):
    record, mgr, run_dir = _load_run(args.work_id, args.base_path)

    if record.status != RunStatus.CHECKPOINT_APPROVED:
        print_and_exit(
            format_error(
                f"Cannot advance in status {record.status.value!r}; must be checkpoint_approved",
                exit_code=EXIT_CONFLICT,
            ),
            EXIT_CONFLICT,
        )

    stage = record.current_stage
    if stage == Stage.PLAN:
        print_and_exit(
            format_error(
                "Cannot advance past plan; use run-close",
                exit_code=EXIT_CONFLICT,
            ),
            EXIT_CONFLICT,
        )

    aa = get_active_artifact(record, stage)
    if aa is None:
        print_and_exit(
            format_error(
                f"No active artifact for stage {stage.value!r}",
                exit_code=EXIT_CONFLICT,
            ),
            EXIT_CONFLICT,
        )
    if aa.status != "approved":
        print_and_exit(
            format_error(
                f"Stage {stage.value!r} artifact must be approved before stage-advance",
                exit_code=EXIT_CONFLICT,
            ),
            EXIT_CONFLICT,
        )
    version = get_artifact_version(run_dir, stage)
    if version != aa.version:
        print_and_exit(
            format_error(
                f"Active artifact version v{aa.version} does not match on-disk v{version}",
                exit_code=EXIT_CONFLICT,
            ),
            EXIT_CONFLICT,
        )
    if not any(
        cp.stage == stage and cp.artifact == aa.artifact and cp.version == aa.version
        for cp in record.approved_checkpoints
    ):
        print_and_exit(
            format_error(
                f"No approved checkpoint matching {stage.value} v{aa.version}",
                exit_code=EXIT_CONFLICT,
            ),
            EXIT_CONFLICT,
        )
    open_routes = [r.route_id for r in record.open_routes if r.status == "open"]
    if open_routes:
        print_and_exit(
            format_error(
                "Cannot advance stage while routes remain open",
                details=open_routes,
                exit_code=EXIT_CONFLICT,
            ),
            EXIT_CONFLICT,
        )

    from tools.workflow_cli.models import NEXT_STAGE_MAP
    next_stage = NEXT_STAGE_MAP[stage]
    record = update_run_status(record, RunStatus.NEXT_STAGE)
    record.current_stage = next_stage
    update_resume_context(
        record,
        last_operation=f"advance_to_{next_stage.value}",
        next_operation="gate_entry",
        active_item=next_stage.value,
    )
    mgr.save(record)
    print_and_exit(
        format_success(
            {"work_id": str(record.work_id), "current_stage": next_stage.value},
            message=f"Advanced to {next_stage.value}",
        ),
        EXIT_OK,
    )


def _register_checkpoint_commands(subparsers):
    p = subparsers.add_parser("review-checkpoint", help="Open checkpoint review for a stage")
    p.add_argument("--work-id", required=True)
    p.add_argument("--stage", required=True)
    p.set_defaults(func=_cmd_review_checkpoint)

    p = subparsers.add_parser("checkpoint-decide", help="Approve or request changes on a checkpoint")
    p.add_argument("--work-id", required=True)
    p.add_argument("--stage", required=True)
    p.add_argument("--decision", required=True, choices=["approved", "changes_requested"])
    p.add_argument("--confirm", action="store_true")
    p.add_argument("--downstream-authorization", default=None)
    p.set_defaults(func=_cmd_checkpoint_decide)

    p = subparsers.add_parser("stage-advance", help="Advance an approved stage to the next stage")
    p.add_argument("--work-id", required=True)
    p.set_defaults(func=_cmd_stage_advance)


def _register_route_commands(subparsers):
    # gap-open
    p = subparsers.add_parser("gap-open", help="Route an upstream gap back to an owner stage")
    p.add_argument("--work-id", required=True)
    p.add_argument("--owner-stage", required=True)
    p.add_argument("--required-action", required=True)
    p.add_argument("--confirm", action="store_true")
    p.set_defaults(func=_cmd_gap_open)

    # gap-resolve
    p = subparsers.add_parser("gap-resolve", help="Resolve an open upstream-gap route")
    p.add_argument("--work-id", required=True)
    p.add_argument("--route-id", required=True)
    p.add_argument("--confirm", action="store_true")
    p.set_defaults(func=_cmd_gap_resolve)


# ---------------------------------------------------------------------------
# context-build command
# ---------------------------------------------------------------------------


def _cmd_context_build(args):
    from tools.workflow_cli.context_pack import build_context_pack, write_context_pack

    work_id = str(_validate_work_id(args.work_id))
    run_dir = _reject_symlinked_run_paths(work_id, args.base_path)
    if not run_dir.exists():
        print_and_exit(
            format_error(f"run not found: {work_id}", exit_code=EXIT_NOT_FOUND),
            EXIT_NOT_FOUND,
        )
    # Some low-level callers intentionally pre-create only the run directory.
    # Once run.md exists, however, it is authoritative and its embedded WorkId
    # must match the requested path before this write command changes the run.
    run_path = run_dir / "run.md"
    if run_path.exists() or run_path.is_symlink():
        _record, _manager, run_dir = _load_run(work_id, args.base_path)
    repo_path = _validate_repo_path(args.repo_path)
    pack = build_context_pack(repo_path)
    md_path, json_path = write_context_pack(pack, run_dir)
    print_and_exit(
        format_success(
            {"work_id": work_id, "context_md": str(md_path), "context_json": str(json_path)},
            message="Context Pack built",
        ),
        EXIT_OK,
    )


def _register_context_commands(subparsers):
    p = subparsers.add_parser("context-build", help="Build Project Context Pack for a run")
    p.add_argument("--work-id", required=True)
    p.add_argument("--repo-path", required=True)
    p.add_argument("--base-path", type=Path, default=argparse.SUPPRESS)
    p.set_defaults(func=_cmd_context_build)


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------


def main(args=None):
    parser = argparse.ArgumentParser(
        prog="workflow",
        description="req-to-plan CLI — internal Agent commands",
    )
    parser.add_argument(
        "--base-path",
        type=Path,
        default=None,
        help="Override base path for .req-to-plan/ directory (for testing)",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)
    _register_run_commands(subparsers)
    _register_route_commands(subparsers)
    _register_tier_commands(subparsers)
    _register_gate_commands(subparsers)
    _register_status_commands(subparsers)
    _register_stage_commands(subparsers)
    _register_checkpoint_commands(subparsers)
    _register_context_commands(subparsers)

    parsed = parser.parse_args(args)
    parsed.func(parsed)


if __name__ == "__main__":
    main()

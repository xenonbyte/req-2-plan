"""Non-authoritative execution metrics primitives.

This module deliberately has no command registration.  It owns the Phase 0
on-disk metrics grammar and the recoverable execution-start transaction; later
integration work supplies the CLI and agent-facing orchestration.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
import errno
import fcntl
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
from typing import Any

from tools.workflow_cli.artifact import read_artifact
from tools.workflow_cli.atomic import UnsafeRegularFileError, atomic_write_text, read_regular_text
from tools.workflow_cli.markdown import plan_task_anchors, strip_nonsemantic_markdown
from tools.workflow_cli.models import RunRecord, RunStatus, Stage, WorkId
from tools.workflow_cli.state import RunStateManager, update_resume_context, update_run_status
from tools.workflow_cli.version import R2P_VERSION


INSTRUMENTATION_SCHEMA = 1
PREREQUISITE_IMPLEMENTATION_VERSION = 1
SELF_HOSTED_WORK_ID = "WF-20260829-r2p-execute-token-phase-r2p"
SELF_HOSTED_BOOTSTRAP_GAP = "execution_start_through_task_002_reviewed_complete"
_HEADER_FIELDS = (
    "work_id", "r2p_version", "instrumentation_schema", "profile", "task_count",
    "instrumentation_complete", "bootstrap_gap", "change_shape", "metrics_finalized",
)
_INVOCATION_FIELDS = (
    "role", "task", "model", "started_at", "ended_at", "elapsed_seconds",
    "context_mode", "context_bytes_kind", "context_bytes", "verification_records_json",
    "verification_total_seconds", "report_bytes", "status", "concerns_json", "fix_wave",
    "input_tokens", "output_tokens", "total_tokens",
)
_ROLES = {
    "implementer", "task_reviewer", "fixer", "task_rereviewer", "final_reviewer",
    "final_fixer", "final_rereviewer",
}
_SHAPES = {
    "migration", "single_module_code", "cross_module_code", "docs_only", "config_only",
    "test_only", "mixed",
}
_DECIMAL_6 = re.compile(r"^[0-9]+\.[0-9]{6}$")
_SHA7 = re.compile(r"^[0-9a-f]{7}$")


class MetricsFormatError(ValueError):
    """The metrics document is absent, malformed, or internally inconsistent."""


class PrerequisiteError(MetricsFormatError):
    """The legacy prerequisite is not met; callers must not dispatch a role."""


@dataclass(frozen=True)
class ParsedMetrics:
    header: dict[str, Any]
    invocations: tuple[dict[str, Any], ...]


def quantize_elapsed_seconds(start_ns: int, end_ns: int) -> str:
    """Serialize a monotonic duration with the prescribed six-place rounding."""
    if end_ns < start_ns:
        raise ValueError("monotonic end precedes start")
    value = Decimal(end_ns - start_ns) / Decimal(1_000_000_000)
    return format(value.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP), "f")


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":"))


def _parse_bool(value: str, name: str) -> bool:
    if value == "true":
        return True
    if value == "false":
        return False
    raise MetricsFormatError(f"{name} must be true or false")


def _parse_nonnegative(value: str, name: str) -> int:
    if not re.fullmatch(r"0|[1-9][0-9]*", value):
        raise MetricsFormatError(f"{name} must be a non-negative integer")
    return int(value)


def _parse_decimal(value: str, name: str) -> Decimal:
    if not _DECIMAL_6.fullmatch(value):
        raise MetricsFormatError(f"{name} must have exactly six fractional digits")
    return Decimal(value)


def _parse_timestamp(value: str, name: str) -> str:
    try:
        datetime.strptime(value, "%Y-%m-%dT%H:%M:%S.%fZ")
    except ValueError as exc:
        raise MetricsFormatError(f"{name} is not a UTC timestamp") from exc
    return value


def _parse_canonical_array(value: str, name: str) -> list[Any]:
    if "\n" in value or "\r" in value:
        raise MetricsFormatError(f"{name} must be single-line canonical JSON")
    try:
        parsed = json.loads(value, parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
    except (ValueError, json.JSONDecodeError) as exc:
        raise MetricsFormatError(f"{name} is invalid JSON") from exc
    if not isinstance(parsed, list) or _canonical_json(parsed) != value:
        raise MetricsFormatError(f"{name} must be a canonical JSON array")
    return parsed


def _parse_header(lines: list[str]) -> dict[str, Any]:
    if not lines or lines[0] != "# Execution Metrics":
        raise MetricsFormatError("missing canonical metrics header")
    if len(lines) < len(_HEADER_FIELDS) + 1:
        raise MetricsFormatError("truncated canonical metrics header")
    raw: dict[str, str] = {}
    for index, field in enumerate(_HEADER_FIELDS, start=1):
        prefix = f"{field}: "
        line = lines[index]
        if not line.startswith(prefix) or field in raw:
            raise MetricsFormatError("metrics header is not canonical")
        raw[field] = line[len(prefix):]
    if len(lines) > len(_HEADER_FIELDS) + 1 and lines[len(_HEADER_FIELDS) + 1] not in ("", "## Invocation 1"):
        raise MetricsFormatError("metrics header must be followed by one blank line")
    try:
        work_id = str(WorkId(raw["work_id"]))
    except ValueError as exc:
        raise MetricsFormatError("work_id is invalid") from exc
    if not raw["r2p_version"]:
        raise MetricsFormatError("r2p_version must be non-empty")
    schema = _parse_nonnegative(raw["instrumentation_schema"], "instrumentation_schema")
    if schema <= 0:
        raise MetricsFormatError("instrumentation_schema must be positive")
    if raw["profile"] not in {"strict", "fast"}:
        raise MetricsFormatError("profile must be strict or fast")
    task_count = _parse_nonnegative(raw["task_count"], "task_count")
    if task_count <= 0:
        raise MetricsFormatError("task_count must be positive")
    complete = _parse_bool(raw["instrumentation_complete"], "instrumentation_complete")
    finalized = _parse_bool(raw["metrics_finalized"], "metrics_finalized")
    gap = raw["bootstrap_gap"]
    expected_gap = SELF_HOSTED_BOOTSTRAP_GAP if not complete else "none"
    if gap != expected_gap or (not complete and work_id != SELF_HOSTED_WORK_ID):
        raise MetricsFormatError("closed instrumentation header combination is invalid")
    shape = raw["change_shape"]
    if shape != "unavailable" and shape not in _SHAPES:
        raise MetricsFormatError("change_shape is invalid")
    if finalized and shape == "unavailable":
        raise MetricsFormatError("finalized metrics require a change_shape")
    if not finalized and shape != "unavailable":
        raise MetricsFormatError("unfinalized metrics must have unavailable change_shape")
    return {
        "work_id": work_id, "r2p_version": raw["r2p_version"], "instrumentation_schema": schema,
        "profile": raw["profile"], "task_count": task_count, "instrumentation_complete": complete,
        "bootstrap_gap": gap, "change_shape": shape, "metrics_finalized": finalized,
    }


def _parse_invocation(raw: dict[str, str], number: int, header: dict[str, Any]) -> dict[str, Any]:
    if tuple(raw) != _INVOCATION_FIELDS:
        raise MetricsFormatError("invocation fields are not canonical")
    role = raw["role"]
    if role not in _ROLES:
        raise MetricsFormatError("role is invalid")
    task_raw = raw["task"]
    final_role = role.startswith("final_")
    if final_role != (task_raw == "final"):
        raise MetricsFormatError("role/task matrix is invalid")
    if not final_role:
        task = _parse_nonnegative(task_raw, "task")
        if task <= 0 or task > header["task_count"]:
            raise MetricsFormatError("task is outside PLAN bounds")
    else:
        task = "final"
    if raw["model"] != "unavailable" and not raw["model"].strip():
        raise MetricsFormatError("model must be non-empty or unavailable")
    started_at = _parse_timestamp(raw["started_at"], "started_at")
    ended_at = _parse_timestamp(raw["ended_at"], "ended_at")
    elapsed = _parse_decimal(raw["elapsed_seconds"], "elapsed_seconds")
    if raw["context_mode"] == "direct_acs":
        expected_kind = "declared_payload_bytes"
    elif raw["context_mode"] == "semantic_view":
        expected_kind = "semantic_payload_bytes"
    else:
        raise MetricsFormatError("context_mode is invalid")
    if raw["context_bytes_kind"] != expected_kind:
        raise MetricsFormatError("context mode/bytes kind matrix is invalid")
    context_bytes = _parse_nonnegative(raw["context_bytes"], "context_bytes")
    records_raw = raw["verification_records_json"]
    total_raw = raw["verification_total_seconds"]
    status = raw["status"]
    wave = _parse_nonnegative(raw["fix_wave"], "fix_wave")
    mutation = role in {"implementer", "fixer", "final_fixer"}
    review = role in {"task_reviewer", "task_rereviewer", "final_reviewer", "final_rereviewer"}
    allowed = {"complete", "blocked"} if mutation else {"approved", "changes_requested", "blocked"}
    if status not in allowed:
        raise MetricsFormatError("role/status matrix is invalid")
    if role in {"implementer", "task_reviewer", "final_reviewer"} and wave != 0:
        raise MetricsFormatError("initial role must use fix_wave 0")
    if role in {"fixer", "task_rereviewer", "final_fixer", "final_rereviewer"} and wave == 0:
        raise MetricsFormatError("fix role must use a positive fix_wave")
    if records_raw == "unavailable":
        if status != "blocked" or total_raw != "unavailable":
            raise MetricsFormatError("only blocked invocation may have unavailable verification")
        records: list[dict[str, str]] | str = "unavailable"
    else:
        records = _parse_canonical_array(records_raw, "verification_records_json")
        if not records:
            raise MetricsFormatError("successful invocation requires verification records")
        if total_raw == "unavailable":
            raise MetricsFormatError("verification total is required")
        total = _parse_decimal(total_raw, "verification_total_seconds")
        parsed_records: list[dict[str, str]] = []
        for record in records:
            if not isinstance(record, dict) or set(record) != {"command", "scope", "reason", "elapsed_seconds", "status"}:
                raise MetricsFormatError("verification record schema is invalid")
            if not all(isinstance(record[key], str) and record[key] for key in ("command", "reason", "elapsed_seconds")):
                raise MetricsFormatError("verification record scalar is invalid")
            if record["scope"] not in {"targeted", "directly_affected", "full_suite"} or record["status"] not in {"passed", "failed"}:
                raise MetricsFormatError("verification record enum is invalid")
            _parse_decimal(record["elapsed_seconds"], "verification record elapsed_seconds")
            parsed_records.append(record)
        if sum((_parse_decimal(record["elapsed_seconds"], "verification record elapsed_seconds") for record in parsed_records), Decimal()) != total:
            raise MetricsFormatError("verification_total_seconds does not match records")
        records = parsed_records
    concerns = _parse_canonical_array(raw["concerns_json"], "concerns_json")
    if not all(isinstance(item, str) for item in concerns):
        raise MetricsFormatError("concerns_json entries must be strings")
    tokens = [raw["input_tokens"], raw["output_tokens"], raw["total_tokens"]]
    if any(token == "unavailable" for token in tokens):
        if tokens != ["unavailable", "unavailable", "unavailable"]:
            raise MetricsFormatError("total_tokens and token fields must all be unavailable or measured")
    else:
        parsed_tokens = [_parse_nonnegative(token, "token") for token in tokens]
        if parsed_tokens[2] != parsed_tokens[0] + parsed_tokens[1]:
            raise MetricsFormatError("total_tokens must equal input_tokens + output_tokens")
    return {
        "sequence": number, "role": role, "task": task, "model": raw["model"],
        "started_at": started_at, "ended_at": ended_at, "elapsed_seconds": format(elapsed, "f"),
        "context_mode": raw["context_mode"], "context_bytes_kind": raw["context_bytes_kind"],
        "context_bytes": context_bytes, "verification_records": records,
        "verification_total_seconds": total_raw, "report_bytes": _parse_nonnegative(raw["report_bytes"], "report_bytes"),
        "status": status, "concerns": concerns, "fix_wave": wave,
        "input_tokens": raw["input_tokens"], "output_tokens": raw["output_tokens"], "total_tokens": raw["total_tokens"],
    }


def parse_metrics(text: str) -> ParsedMetrics:
    """Parse the closed metrics grammar without accepting near-miss documents."""
    if not isinstance(text, str) or not text.endswith("\n"):
        raise MetricsFormatError("metrics text must end in one newline")
    lines = text.splitlines()
    header = _parse_header(lines)
    cursor = len(_HEADER_FIELDS) + 1
    if cursor < len(lines) and lines[cursor] == "":
        cursor += 1
    invocations: list[dict[str, Any]] = []
    while cursor < len(lines):
        expected = f"## Invocation {len(invocations) + 1}"
        if lines[cursor] != expected:
            raise MetricsFormatError("invocation sequence is not contiguous")
        cursor += 1
        raw: dict[str, str] = {}
        for field in _INVOCATION_FIELDS:
            if cursor >= len(lines) or not lines[cursor].startswith(f"{field}: "):
                raise MetricsFormatError("invocation fields are not canonical")
            raw[field] = lines[cursor][len(field) + 2:]
            cursor += 1
        invocations.append(_parse_invocation(raw, len(invocations) + 1, header))
        if cursor < len(lines):
            if lines[cursor] != "":
                raise MetricsFormatError("invocations must be separated by one blank line")
            cursor += 1
    return ParsedMetrics(header=header, invocations=tuple(invocations))


def _validate_relative_path(value: str) -> PurePosixPath:
    path = PurePosixPath(value)
    if value == "" or path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError("invalid repository-relative path")
    return path


def _is_test_path(path: PurePosixPath) -> bool:
    name = path.name
    return (
        any(part in {"test", "tests"} for part in path.parts)
        or re.fullmatch(r"test_.+", name) is not None
        or re.fullmatch(r".+_test(?:\..+)?", name) is not None
        or re.fullmatch(r".+\.test\..+", name) is not None
        or re.fullmatch(r".+\.spec\..+", name) is not None
    )


def classify_change_shape(name_status_z: bytes) -> str:
    """Classify exactly one NUL-delimited ``git diff --name-status`` result."""
    if not isinstance(name_status_z, bytes) or not name_status_z or not name_status_z.endswith(b"\0"):
        raise ValueError("invalid git name-status output")
    try:
        tokens = name_status_z[:-1].split(b"\0")
        tokens = [token.decode("utf-8") for token in tokens]
    except UnicodeDecodeError as exc:
        raise ValueError("git path is not UTF-8") from exc
    paths: list[PurePosixPath] = []
    index = 0
    while index < len(tokens):
        status = tokens[index]
        index += 1
        if status in {"A", "M", "D", "T"}:
            count = 1
        elif re.fullmatch(r"[RC](?:0\d\d|100)", status):
            count = 2
        else:
            raise ValueError("invalid git name-status token")
        if index + count > len(tokens):
            raise ValueError("truncated git name-status record")
        for value in tokens[index:index + count]:
            paths.append(_validate_relative_path(value))
        index += count
    if not paths:
        raise ValueError("git diff has no changed paths")
    if any(part in {"migration", "migrations"} for path in paths for part in path.parts):
        return "migration"
    tests = [path for path in paths if _is_test_path(path)]
    if len(tests) == len(paths):
        return "test_only"
    non_tests = [path for path in paths if path not in tests]
    docs = [path for path in non_tests if path.parts[0] == "docs" or path.suffix in {".md", ".rst", ".adoc", ".txt"}]
    configs = [path for path in non_tests if path.suffix in {".json", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".properties"}]
    sources = [path for path in non_tests if path not in docs and path not in configs]
    if sources:
        modules = {"_root" if len(path.parts) == 1 else path.parts[0] for path in sources}
        return "single_module_code" if len(modules) == 1 else "cross_module_code"
    if non_tests and len(docs) == len(non_tests):
        return "docs_only"
    if non_tests and len(configs) == len(non_tests):
        return "config_only"
    return "mixed"


def _execution_base(base_path: Path) -> str:
    result = subprocess.run(
        ["git", "-C", str(base_path), "rev-parse", "HEAD"],
        capture_output=True, text=True, check=False,
    )
    value = result.stdout.strip()
    if result.returncode != 0 or not re.fullmatch(r"[0-9a-f]{40}", value):
        raise MetricsFormatError("cannot determine full Execution BASE")
    return value


def _initial_metrics_text(work_id: WorkId, profile: str, task_count: int) -> str:
    return "\n".join((
        "# Execution Metrics", f"work_id: {work_id}", f"r2p_version: {R2P_VERSION}",
        f"instrumentation_schema: {INSTRUMENTATION_SCHEMA}", f"profile: {profile}",
        f"task_count: {task_count}", "instrumentation_complete: true", "bootstrap_gap: none",
        "change_shape: unavailable", "metrics_finalized: false", "",
    ))


def _initial_progress_text(work_id: WorkId, execution_base: str, anchors: list[tuple[str, str]]) -> str:
    lines = ["# Execution Progress", "", f"work_id: {work_id}", "", f"Execution BASE: {execution_base}", ""]
    lines.extend(f"- [ ] {task_id} {title}".rstrip() for task_id, title in anchors)
    return "\n".join(lines) + "\n"


def _lock_file(path: Path) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        raise MetricsFormatError("unsafe lock path")
    flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    fd = os.open(path, flags, 0o600)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise MetricsFormatError("lock is not a regular file")
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return fd
    except Exception:
        os.close(fd)
        raise


def start_execution_transaction(base_path: Path, work_id: WorkId, profile: str) -> RunRecord:
    """Create the two initial ledgers and transition a closed run atomically enough to recover.

    The marker makes partial creation explicit.  Existing residue is never
    overwritten: a later integrator can surface recovery through the CLI.
    """
    if profile not in {"strict", "fast"}:
        raise MetricsFormatError("profile must be strict or fast")
    base_path = Path(base_path)
    run_dir = base_path / ".req-to-plan" / str(work_id)
    manager = RunStateManager(run_dir)
    record = manager.load()
    if record.work_id != work_id:
        raise MetricsFormatError("run record work_id does not match request")
    if record.status == RunStatus.EXECUTING:
        execution_dir = run_dir / "execution"
        marker = execution_dir / ".start-transaction.json"
        try:
            metrics = parse_metrics(read_regular_text(execution_dir / "metrics.md") or "")
            progress = read_regular_text(execution_dir / "progress.md") or ""
        except (FileNotFoundError, UnsafeRegularFileError) as exc:
            raise MetricsFormatError("executing run has incomplete start ledgers") from exc
        if metrics.header["profile"] != profile:
            raise MetricsFormatError("executing run profile conflicts with requested profile")
        if not marker.exists():
            return record
        try:
            marker_text = read_regular_text(marker)
            marker_data = json.loads(marker_text or "")
        except (FileNotFoundError, UnsafeRegularFileError, json.JSONDecodeError) as exc:
            raise MetricsFormatError("unsafe or malformed execution start marker") from exc
        base_match = re.search(r"^Execution BASE: ([0-9a-f]{40})$", progress, re.MULTILINE)
        expected_marker = {
            "schema": 1, "work_id": str(work_id), "profile": profile,
            "task_count": metrics.header["task_count"],
            "execution_base": base_match.group(1) if base_match else None,
        }
        if marker_data != expected_marker:
            raise MetricsFormatError("execution start marker does not match complete ledgers")
        marker.unlink()
        return record
    if record.status != RunStatus.CLOSED_AT_PLAN_CHECKPOINT:
        raise MetricsFormatError("run is not closed at the PLAN checkpoint")
    plan_text = read_artifact(run_dir, Stage.PLAN)
    anchors = plan_task_anchors(strip_nonsemantic_markdown(plan_text))
    if not anchors:
        raise MetricsFormatError("PLAN contains no PLAN-TASK anchors")
    execution_base = _execution_base(base_path)
    lock_fd = _lock_file(run_dir / "logs" / "execute-start.lock")
    try:
        execution_dir = run_dir / "execution"
        if execution_dir.exists() or execution_dir.is_symlink():
            raise MetricsFormatError("execution start residue exists; refusing to clobber")
        execution_dir.mkdir()
        marker = execution_dir / ".start-transaction.json"
        marker_payload = {
            "schema": 1, "work_id": str(work_id), "profile": profile,
            "task_count": len(anchors), "execution_base": execution_base,
        }
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
        marker_fd = os.open(marker, flags, 0o600)
        with os.fdopen(marker_fd, "w", encoding="utf-8") as stream:
            stream.write(_canonical_json(marker_payload) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        atomic_write_text(execution_dir / "progress.md", _initial_progress_text(work_id, execution_base, anchors))
        atomic_write_text(execution_dir / "metrics.md", _initial_metrics_text(work_id, profile, len(anchors)))
        parse_metrics(read_regular_text(execution_dir / "metrics.md") or "")
        record = update_run_status(record, RunStatus.EXECUTING)
        update_resume_context(record, last_operation="execute_start", next_operation="implement_tasks")
        manager.save(record)
        marker.unlink()
        return record
    except Exception:
        raise
    finally:
        fcntl.flock(lock_fd, fcntl.LOCK_UN)
        os.close(lock_fd)


def _read_progress(run_dir: Path) -> str:
    try:
        value = read_regular_text(run_dir / "execution" / "progress.md")
    except (FileNotFoundError, UnsafeRegularFileError) as exc:
        raise PrerequisiteError("unsafe or missing execution progress") from exc
    assert value is not None
    return value


def _marker_for(progress: str, task: int) -> tuple[str, str] | None:
    pattern = re.compile(rf"^Task {task}: complete \(commits ([0-9a-f]{{7}})\.\.([0-9a-f]{{7}}), (?:review|final review) clean\)$", re.MULTILINE)
    found = pattern.findall(progress)
    if len(found) > 1:
        raise PrerequisiteError(f"Task {task} has duplicate completion markers")
    return found[0] if found else None


def check_prerequisite_v1(base_path: Path, work_id: WorkId, task: int) -> dict[str, Any]:
    """Validate the legacy task-001/task-002 execution boundary without mutation."""
    if task not in {1, 2}:
        raise PrerequisiteError("prerequisite v1 only supports Task 001 or 002")
    run_dir = Path(base_path) / ".req-to-plan" / str(work_id)
    record = RunStateManager(run_dir).load()
    if record.status != RunStatus.EXECUTING:
        raise PrerequisiteError("run must be EXECUTING")
    plan_text = read_artifact(run_dir, Stage.PLAN)
    anchors = plan_task_anchors(strip_nonsemantic_markdown(plan_text))
    expected = [f"PLAN-TASK-{number:03d}" for number in range(1, 10)]
    if [anchor[0] for anchor in anchors] != expected:
        raise PrerequisiteError("PLAN must have exactly nine contiguous task anchors")
    progress = _read_progress(run_dir)
    rows = re.findall(r"^- \[([ x])\] (PLAN-TASK-\d{3})\b", progress, re.MULTILINE)
    if [item[1] for item in rows] != expected:
        raise PrerequisiteError("progress must have the corresponding nine task rows")
    if re.search(r"^(?:Execution Profile|Profile Escalation|Task \d+: (?:implemented|complete)):", progress, re.MULTILINE):
        if task == 1:
            raise PrerequisiteError("Task 001 legacy preflight forbids profile and task markers")
    base_match = re.search(r"^Execution BASE: ([0-9a-f]{40})$", progress, re.MULTILINE)
    if not base_match:
        raise PrerequisiteError("progress must record a full Execution BASE")
    unchecked = [number for number, (checked, _) in enumerate(rows, start=1) if checked == " "]
    if not unchecked or unchecked[0] != task:
        raise PrerequisiteError("task is not the lowest unchecked task")
    head = _execution_base(Path(base_path))
    if task == 1:
        if base_match.group(1) != head:
            raise PrerequisiteError("Task 001 requires full Execution BASE to equal HEAD")
    else:
        prior = _marker_for(progress, 1)
        if prior is None or not head.startswith(prior[1]):
            raise PrerequisiteError("Task 002 requires HEAD at Task 001 reviewed-complete head")
    return {"version": PREREQUISITE_IMPLEMENTATION_VERSION, "task": task, "task_count": len(anchors), "execution_base": base_match.group(1)}


def _bootstrap_metrics_text(work_id: WorkId, profile: str, task_count: int) -> str:
    return "\n".join((
        "# Execution Metrics", f"work_id: {work_id}", f"r2p_version: {R2P_VERSION}",
        f"instrumentation_schema: {INSTRUMENTATION_SCHEMA}", f"profile: {profile}",
        f"task_count: {task_count}", "instrumentation_complete: false",
        f"bootstrap_gap: {SELF_HOSTED_BOOTSTRAP_GAP}", "change_shape: unavailable",
        "metrics_finalized: false", "",
    ))


def bootstrap_self_hosted_metrics(base_path: Path, work_id: WorkId, through_task: int) -> ParsedMetrics:
    """Publish the one self-hosted metrics header with no replacement fallback."""
    if str(work_id) != SELF_HOSTED_WORK_ID or through_task != 2:
        raise PrerequisiteError("self-hosted bootstrap arguments are not canonical")
    run_dir = Path(base_path) / ".req-to-plan" / str(work_id)
    progress = _read_progress(run_dir)
    record = RunStateManager(run_dir).load()
    if record.status != RunStatus.EXECUTING:
        raise PrerequisiteError("self-hosted bootstrap requires an EXECUTING run")
    complete_one = _marker_for(progress, 1)
    complete_two = _marker_for(progress, 2)
    if complete_one is None or complete_two is None:
        raise PrerequisiteError("self-hosted bootstrap requires Tasks 001 and 002 reviewed-complete")
    if not _execution_base(Path(base_path)).startswith(complete_two[1]):
        raise PrerequisiteError("self-hosted bootstrap requires HEAD at Task 002 reviewed-complete head")
    if re.search(r"^Task [3-9]:", progress, re.MULTILINE):
        raise PrerequisiteError("Task 003 must not have started before first bootstrap")
    execution_dir = run_dir / "execution"
    lock_fd = _lock_file(run_dir / "logs" / "metrics-bootstrap.lock")
    try:
        target = execution_dir / "metrics.md"
        expected = _bootstrap_metrics_text(work_id, "strict", 9)
        if target.exists() or target.is_symlink():
            parsed = parse_metrics(read_regular_text(target) or "")
            if parsed.header != parse_metrics(expected).header:
                raise MetricsFormatError("existing metrics header does not match bootstrap")
            return parsed
        nonce = os.urandom(16).hex()
        temp = execution_dir / f".metrics-bootstrap.{os.getpid()}.{nonce}.tmp"
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(temp, flags, 0o600)
        try:
            os.write(fd, expected.encode("utf-8"))
            os.fsync(fd)
            source = os.fstat(fd)
            before = os.lstat(temp)
            if not stat.S_ISREG(source.st_mode) or (source.st_dev, source.st_ino) != (before.st_dev, before.st_ino):
                raise MetricsFormatError("bootstrap temp identity changed")
            try:
                os.link(temp, target, follow_symlinks=False)
            except FileExistsError:
                parsed = parse_metrics(read_regular_text(target) or "")
                if parsed.header != parse_metrics(expected).header:
                    raise MetricsFormatError("concurrent bootstrap target mismatches")
                return parsed
            final = os.lstat(target)
            current = os.lstat(temp)
            if (final.st_dev, final.st_ino) != (source.st_dev, source.st_ino) or (current.st_dev, current.st_ino) != (source.st_dev, source.st_ino):
                raise MetricsFormatError("bootstrap publish identity changed")
            os.fsync(fd)
            temp.unlink()
            return parse_metrics(read_regular_text(target) or "")
        finally:
            os.close(fd)
    finally:
        fcntl.flock(lock_fd, fcntl.LOCK_UN)
        os.close(lock_fd)


def _sample_error(message: str) -> MetricsFormatError:
    return MetricsFormatError(f"representative_metrics_missing: {message}")


def _sample_summary(sample_dir: Path) -> dict[str, Any]:
    if not sample_dir.is_absolute() or sample_dir.is_symlink() or not sample_dir.is_dir():
        raise _sample_error("sample directory must be an absolute regular directory")
    canonical = sample_dir.resolve(strict=True)
    try:
        work_id = WorkId(canonical.name)
    except ValueError as exc:
        raise _sample_error("sample basename is not a WorkId") from exc
    try:
        record = RunStateManager(canonical).load()
        metrics_text = read_regular_text(canonical / "execution" / "metrics.md")
        progress = read_regular_text(canonical / "execution" / "progress.md")
        plan_text = read_artifact(canonical, Stage.PLAN)
        final_review = read_regular_text(canonical / "execution" / "final-review.md")
    except (FileNotFoundError, UnsafeRegularFileError, ValueError) as exc:
        raise _sample_error("sample has unsafe or missing authoritative input") from exc
    if record.work_id != work_id or record.status != RunStatus.ARCHIVED:
        raise _sample_error("sample is not archived")
    if str(work_id) == SELF_HOSTED_WORK_ID:
        raise _sample_error("self-hosted run cannot be a sample")
    parsed = parse_metrics(metrics_text or "")
    header = parsed.header
    if header["profile"] != "strict" or not header["instrumentation_complete"] or header["bootstrap_gap"] != "none" or not header["metrics_finalized"]:
        raise _sample_error("sample metrics header is not finalized strict instrumentation")
    if header["instrumentation_schema"] != INSTRUMENTATION_SCHEMA or header["change_shape"] == "unavailable":
        raise _sample_error("sample schema or shape is unsupported")
    anchors = plan_task_anchors(strip_nonsemantic_markdown(plan_text))
    if len(anchors) != header["task_count"]:
        raise _sample_error("sample PLAN task count differs from metrics")
    task_ids = [item[0] for item in anchors]
    if any(not re.search(rf"^- \[x\] {re.escape(task_id)}\b", progress or "", re.MULTILINE) for task_id in task_ids):
        raise _sample_error("sample progress is incomplete")
    verdicts = re.findall(r"^Verdict:\s*(.+?)\s*$", final_review or "", re.MULTILINE)
    if not verdicts or verdicts[-1] != "Approved":
        raise _sample_error("sample final verdict is not Approved")
    roles = {role: 0 for role in sorted(_ROLES)}
    for invocation in parsed.invocations:
        roles[invocation["role"]] += 1
    if roles["final_reviewer"] < 1 or any(roles["implementer"] < len(anchors) for _ in [0]) or roles["task_reviewer"] < len(anchors):
        raise _sample_error("sample role coverage is incomplete")
    duration = sum((Decimal(item["elapsed_seconds"]) for item in parsed.invocations), Decimal())
    reports = sum(item["report_bytes"] for item in parsed.invocations)
    contexts = sum(item["context_bytes"] for item in parsed.invocations)
    tokens_available = all(item["total_tokens"] != "unavailable" for item in parsed.invocations)
    return {
        "path": str(canonical), "work_id": str(work_id), "r2p_version": header["r2p_version"],
        "instrumentation_schema": header["instrumentation_schema"], "task_count": header["task_count"],
        "change_shape": header["change_shape"], "role_counts": roles, "final_verdict": "Approved",
        "duration_seconds": format(duration, "f"), "report_bytes": reports, "context_bytes": contexts,
        "total_tokens": sum(int(item["total_tokens"]) for item in parsed.invocations) if tokens_available else "unavailable",
    }


def validate_representative_samples(sample_dirs: tuple[Path, Path, Path]) -> dict[str, Any]:
    """Validate exactly three pinned archived strict samples without discovery or writes."""
    if not isinstance(sample_dirs, tuple) or len(sample_dirs) != 3:
        raise _sample_error("exactly three sample directories are required")
    summaries = [_sample_summary(Path(path)) for path in sample_dirs]
    if len({item["path"] for item in summaries}) != 3 or len({item["work_id"] for item in summaries}) != 3:
        raise _sample_error("sample paths and work IDs must be unique")
    if len({item["task_count"] for item in summaries}) < 2 and len({item["change_shape"] for item in summaries}) < 2:
        raise _sample_error("samples are not representative")
    return {
        "status": "ok", "samples": summaries,
        "aggregate": {
            "duration_seconds": format(sum((Decimal(item["duration_seconds"]) for item in summaries), Decimal()), "f"),
            "report_bytes": sum(item["report_bytes"] for item in summaries),
            "context_bytes": sum(item["context_bytes"] for item in summaries),
            "total_tokens": "unavailable" if any(item["total_tokens"] == "unavailable" for item in summaries) else sum(int(item["total_tokens"]) for item in summaries),
        },
    }

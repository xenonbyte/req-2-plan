"""Non-authoritative execution metrics primitives.

This module deliberately has no command registration. It owns the Phase 0
on-disk metrics grammar, recoverable execution-start transaction, structured
role append/status operations, and deterministic finalization. CLI registration
and agent-facing orchestration remain separate.
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
import secrets
import stat
import subprocess
from typing import Any

from tools.workflow_cli.artifact import _parse_frontmatter
from tools.workflow_cli.execution_profile import (
    ExecutionProfile,
    ExecutionProfileError,
    ParsedExecutionLedger,
    check_prerequisite_v2,
    parse_execution_ledger,
    prerequisite_semantics_version,
    validate_ledger_commit_chain,
)
from tools.workflow_cli.markdown import (
    PLAN_TASK_CHECKBOX_RE,
    plan_task_anchors,
    strip_html_comments_outside_fences,
    strip_nonsemantic_markdown,
    unfenced_markdown_lines,
)
from tools.workflow_cli.models import RunRecord, RunStatus, STAGE_ARTIFACT_MAP, Stage, WorkId
from tools.workflow_cli.state import (
    parse_run_record,
    run_record_to_markdown,
    update_resume_context,
    update_run_status,
)
from tools.workflow_cli.version import R2P_VERSION


INSTRUMENTATION_SCHEMA = 1
PREREQUISITE_IMPLEMENTATION_VERSION = 2
SELF_HOSTED_WORK_ID = "WF-20260829-r2p-execute-token-phase-r2p"
SELF_HOSTED_BOOTSTRAP_GAP = "execution_start_through_task_002_reviewed_complete"
_LEGACY_BOOTSTRAP_GAP_RE = re.compile(
    r"^legacy_metrics_start_(?:task_([0-9]{3})|final)$"
)
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


class MetricsInputError(MetricsFormatError):
    """A structured metrics request is syntactically valid JSON but invalid input."""


class PrerequisiteError(MetricsFormatError):
    """The legacy prerequisite is not met; callers must not dispatch a role."""


class PlanNotFoundError(FileNotFoundError):
    """Only the PLAN read boundary may report a missing PLAN."""


class RepresentativeSamplesError(MetricsFormatError):
    """Representative sample validation failed with a stable error payload."""

    def __init__(self, result: dict[str, Any]):
        super().__init__(result["message"])
        self.result = result


class _CommittedWriteError(OSError):
    """An atomic replacement landed, but a post-commit durability step failed."""


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
    if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{6}Z", value):
        raise MetricsFormatError(f"{name} is not a canonical UTC timestamp")
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
    legacy_gap = _LEGACY_BOOTSTRAP_GAP_RE.fullmatch(gap)
    legacy_task = int(legacy_gap.group(1)) if legacy_gap and legacy_gap.group(1) else None
    valid_gap = (
        (complete and gap == "none")
        or (
            not complete
            and work_id == SELF_HOSTED_WORK_ID
            and gap == SELF_HOSTED_BOOTSTRAP_GAP
        )
        or (
            not complete
            and raw["profile"] == "strict"
            and legacy_gap is not None
            and (legacy_task is None or 1 <= legacy_task <= task_count)
        )
    )
    if not valid_gap:
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
    timing = [raw["started_at"], raw["ended_at"], raw["elapsed_seconds"]]
    if any(value == "unavailable" for value in timing):
        if timing != ["unavailable", "unavailable", "unavailable"]:
            raise MetricsFormatError(
                "timing fields must all be unavailable or all be measured"
            )
        started_at: datetime | str = "unavailable"
        ended_at: datetime | str = "unavailable"
        elapsed_text = "unavailable"
    else:
        started_at = _parse_timestamp(raw["started_at"], "started_at")
        ended_at = _parse_timestamp(raw["ended_at"], "ended_at")
        if ended_at < started_at:
            raise MetricsFormatError("ended_at precedes started_at")
        elapsed_text = format(
            _parse_decimal(raw["elapsed_seconds"], "elapsed_seconds"), "f"
        )
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
        if not records and status != "blocked":
            raise MetricsFormatError("successful invocation requires verification records")
        if total_raw == "unavailable":
            raise MetricsFormatError("verification total is required")
        total = _parse_decimal(total_raw, "verification_total_seconds")
        parsed_records: list[dict[str, str]] = []
        for record in records:
            if not isinstance(record, dict) or set(record) != {"command", "scope", "reason", "elapsed_seconds", "status"}:
                raise MetricsFormatError("verification record schema is invalid")
            if not all(
                isinstance(record[key], str) and record[key]
                for key in (
                    "command", "scope", "reason", "elapsed_seconds", "status"
                )
            ):
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
        "started_at": started_at, "ended_at": ended_at, "elapsed_seconds": elapsed_text,
        "context_mode": raw["context_mode"], "context_bytes_kind": raw["context_bytes_kind"],
        "context_bytes": context_bytes, "verification_records": records,
        "verification_total_seconds": total_raw, "report_bytes": _parse_nonnegative(raw["report_bytes"], "report_bytes"),
        "status": status, "concerns": concerns, "fix_wave": wave,
        "input_tokens": raw["input_tokens"], "output_tokens": raw["output_tokens"], "total_tokens": raw["total_tokens"],
    }


def parse_metrics(text: str) -> ParsedMetrics:
    """Parse the closed metrics grammar without accepting near-miss documents."""
    if not isinstance(text, str) or not text.endswith("\n") or text.endswith("\n\n"):
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


_DIR_FLAGS = (
    os.O_RDONLY
    | getattr(os, "O_DIRECTORY", 0)
    | getattr(os, "O_NOFOLLOW", 0)
    | getattr(os, "O_NONBLOCK", 0)
    | getattr(os, "O_CLOEXEC", 0)
)
_FILE_READ_FLAGS = (
    os.O_RDONLY
    | getattr(os, "O_NOFOLLOW", 0)
    | getattr(os, "O_NONBLOCK", 0)
    | getattr(os, "O_CLOEXEC", 0)
)
_FILE_WRITE_FLAGS = (
    os.O_WRONLY
    | os.O_CREAT
    | os.O_EXCL
    | getattr(os, "O_NOFOLLOW", 0)
    | getattr(os, "O_CLOEXEC", 0)
)
START_TRANSACTION_OWNER = ".execution-start-transaction.json"


def _require_fd_capabilities() -> None:
    required = ("O_DIRECTORY", "O_NOFOLLOW", "O_NONBLOCK")
    if any(not hasattr(os, name) for name in required):
        raise MetricsFormatError("stable directory-fd capability unavailable")
    if os.open not in os.supports_dir_fd or os.stat not in os.supports_dir_fd:
        raise MetricsFormatError("stable directory-fd capability unavailable")


def _open_absolute_dir(path: Path) -> int:
    """Pin an absolute directory by walking from the filesystem root."""
    _require_fd_capabilities()
    path = Path(os.path.abspath(os.fspath(path)))
    if not path.is_absolute():
        raise MetricsFormatError("directory path must be absolute")
    fd = os.open(path.anchor, _DIR_FLAGS)
    try:
        for component in path.parts[1:]:
            if component in {"", ".", ".."}:
                raise MetricsFormatError("unsafe directory component")
            next_fd = os.open(component, _DIR_FLAGS, dir_fd=fd)
            os.close(fd)
            fd = next_fd
        opened = os.fstat(fd)
        if not stat.S_ISDIR(opened.st_mode):
            raise MetricsFormatError("path is not a directory")
        return fd
    except OSError as exc:
        os.close(fd)
        if exc.errno in {errno.ELOOP, errno.ENOTDIR, errno.ENOENT}:
            raise MetricsFormatError("unsafe or missing directory path") from exc
        raise
    except Exception:
        os.close(fd)
        raise


def _open_dir_at(parent_fd: int, name: str) -> int:
    if "/" in name or name in {"", ".", ".."}:
        raise MetricsFormatError("unsafe directory component")
    try:
        fd = os.open(name, _DIR_FLAGS, dir_fd=parent_fd)
    except OSError as exc:
        if exc.errno in {errno.ELOOP, errno.ENOTDIR, errno.ENOENT}:
            raise MetricsFormatError(f"unsafe or missing directory: {name}") from exc
        raise
    if not stat.S_ISDIR(os.fstat(fd).st_mode):
        os.close(fd)
        raise MetricsFormatError(f"not a directory: {name}")
    return fd


def _read_text_at(parent_fd: int, name: str, *, missing_ok: bool = False) -> str | None:
    if "/" in name or name in {"", ".", ".."}:
        raise MetricsFormatError("unsafe file component")
    try:
        before = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    except FileNotFoundError:
        if missing_ok:
            return None
        raise
    if not stat.S_ISREG(before.st_mode):
        raise MetricsFormatError(f"unsafe non-regular file: {name}")
    fd: int | None = None
    try:
        fd = os.open(name, _FILE_READ_FLAGS, dir_fd=parent_fd)
        opened = os.fstat(fd)
        if (
            not stat.S_ISREG(opened.st_mode)
            or (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino)
        ):
            raise MetricsFormatError(f"file identity changed during read: {name}")
        chunks: list[bytes] = []
        while True:
            chunk = os.read(fd, 1024 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
        try:
            return b"".join(chunks).decode("utf-8")
        except UnicodeDecodeError as exc:
            raise MetricsFormatError(f"trusted input is not UTF-8: {name}") from exc
    except FileNotFoundError:
        if missing_ok:
            return None
        raise
    except OSError as exc:
        if exc.errno in {errno.ELOOP, errno.ENOTDIR, errno.ENXIO}:
            raise MetricsFormatError(f"unsafe regular file: {name}") from exc
        raise
    finally:
        if fd is not None:
            os.close(fd)


def _write_all(fd: int, payload: bytes) -> None:
    offset = 0
    while offset < len(payload):
        written = os.write(fd, payload[offset:])
        if written <= 0:
            raise OSError("short write")
        offset += written


def _write_new_text_at(parent_fd: int, name: str, content: str) -> os.stat_result:
    fd = os.open(name, _FILE_WRITE_FLAGS, 0o600, dir_fd=parent_fd)
    try:
        _write_all(fd, content.encode("utf-8"))
        os.fsync(fd)
        opened = os.fstat(fd)
        if not stat.S_ISREG(opened.st_mode):
            raise MetricsFormatError(f"created path is not regular: {name}")
        current = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        if (opened.st_dev, opened.st_ino) != (current.st_dev, current.st_ino):
            raise MetricsFormatError(f"created file identity changed: {name}")
        return opened
    finally:
        os.close(fd)


def _publish_new_text_at(parent_fd: int, name: str, content: str) -> None:
    """Atomically create a durable file without ever exposing partial content."""
    temp = f".{name}.{os.getpid()}.{secrets.token_hex(16)}.tmp"
    fd = os.open(temp, _FILE_WRITE_FLAGS, 0o600, dir_fd=parent_fd)
    linked = False
    try:
        _write_all(fd, content.encode("utf-8"))
        os.fsync(fd)
        opened = os.fstat(fd)
        current = os.stat(temp, dir_fd=parent_fd, follow_symlinks=False)
        identity = (opened.st_dev, opened.st_ino)
        if (
            not stat.S_ISREG(opened.st_mode)
            or identity != (current.st_dev, current.st_ino)
        ):
            raise MetricsFormatError("atomic create temp identity changed")
        os.link(
            temp,
            name,
            src_dir_fd=parent_fd,
            dst_dir_fd=parent_fd,
            follow_symlinks=False,
        )
        linked = True
        published = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        if (
            not stat.S_ISREG(published.st_mode)
            or identity != (published.st_dev, published.st_ino)
        ):
            raise MetricsFormatError("atomic create publish identity changed")
        os.fsync(parent_fd)
    finally:
        os.close(fd)
        try:
            os.unlink(temp, dir_fd=parent_fd)
        except FileNotFoundError:
            pass
        if linked:
            os.fsync(parent_fd)


def _clear_owned_execution_dir(execution_fd: int) -> None:
    """Remove only the closed start transaction's closed set of regular files."""
    children = set(os.listdir(execution_fd))
    allowed = {".start-transaction.json", "progress.md", "metrics.md"}
    if not children <= allowed:
        raise MetricsFormatError("foreign execution-start residue")
    for name in sorted(children):
        before = os.stat(name, dir_fd=execution_fd, follow_symlinks=False)
        if not stat.S_ISREG(before.st_mode):
            raise MetricsFormatError("unsafe execution-start residue")
        os.unlink(name, dir_fd=execution_fd)
    os.fsync(execution_fd)


def _replace_text_at(parent_fd: int, name: str, content: str) -> None:
    temp = f".{name}.{os.getpid()}.{secrets.token_hex(16)}.tmp"
    fd = os.open(temp, _FILE_WRITE_FLAGS, 0o600, dir_fd=parent_fd)
    try:
        _write_all(fd, content.encode("utf-8"))
        os.fsync(fd)
        opened = os.fstat(fd)
        current = os.stat(temp, dir_fd=parent_fd, follow_symlinks=False)
        if not stat.S_ISREG(opened.st_mode) or (opened.st_dev, opened.st_ino) != (current.st_dev, current.st_ino):
            raise MetricsFormatError("atomic temp identity changed")
        os.replace(temp, name, src_dir_fd=parent_fd, dst_dir_fd=parent_fd)
        temp = ""
        try:
            os.fsync(parent_fd)
        except OSError as exc:
            raise _CommittedWriteError(str(exc)) from exc
    finally:
        os.close(fd)
        if temp:
            try:
                os.unlink(temp, dir_fd=parent_fd)
            except FileNotFoundError:
                pass


def _parse_record_at(run_fd: int, expected_work_id: WorkId) -> RunRecord:
    text = _read_text_at(run_fd, "run.md")
    assert text is not None
    match = re.search(r"# Workflow Run: (WF-\S+)", text)
    if not match:
        raise MetricsFormatError("cannot parse work_id from run.md")
    embedded = WorkId(match.group(1))
    if embedded != expected_work_id:
        raise MetricsFormatError("run record work_id does not match request")
    return parse_run_record(text, embedded)


def _plan_at(run_fd: int) -> str:
    try:
        text = _read_text_at(run_fd, STAGE_ARTIFACT_MAP[Stage.PLAN])
    except FileNotFoundError as exc:
        raise PlanNotFoundError("PLAN not found") from exc
    assert text is not None
    _, body = _parse_frontmatter(text)
    return body


def _open_run(base_path: Path, work_id: WorkId) -> tuple[int, int, int]:
    repo_fd = _open_absolute_dir(Path(base_path))
    workspace_fd: int | None = None
    run_fd: int | None = None
    try:
        workspace_fd = _open_dir_at(repo_fd, ".req-to-plan")
        run_fd = _open_dir_at(workspace_fd, str(work_id))
        return repo_fd, workspace_fd, run_fd
    except Exception:
        if run_fd is not None:
            os.close(run_fd)
        if workspace_fd is not None:
            os.close(workspace_fd)
        os.close(repo_fd)
        raise


def _close_fds(*fds: int | None) -> None:
    for fd in reversed(fds):
        if fd is not None:
            os.close(fd)


def _open_lock_at(run_fd: int, filename: str) -> tuple[int, int]:
    try:
        os.mkdir("logs", 0o700, dir_fd=run_fd)
    except FileExistsError:
        pass
    logs_fd = _open_dir_at(run_fd, "logs")
    fd: int | None = None
    try:
        fd = os.open(
            filename,
            os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0),
            0o600,
            dir_fd=logs_fd,
        )
        opened = os.fstat(fd)
        current = os.stat(filename, dir_fd=logs_fd, follow_symlinks=False)
        if not stat.S_ISREG(opened.st_mode) or (opened.st_dev, opened.st_ino) != (current.st_dev, current.st_ino):
            raise MetricsFormatError("unsafe lock file")
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return logs_fd, fd
    except BlockingIOError as exc:
        if fd is not None:
            os.close(fd)
        os.close(logs_fd)
        raise MetricsFormatError("execution lock is busy") from exc
    except Exception:
        if fd is not None:
            os.close(fd)
        os.close(logs_fd)
        raise


def _release_lock(logs_fd: int, lock_fd: int) -> None:
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_UN)
    finally:
        os.close(lock_fd)
        os.close(logs_fd)


def _execution_base(base_path: Path) -> str:
    result = subprocess.run(
        ["git", "-C", str(base_path), "rev-parse", "HEAD"],
        capture_output=True, text=True, check=False,
    )
    value = result.stdout.strip()
    if result.returncode != 0 or not re.fullmatch(r"[0-9a-f]{40}", value):
        raise MetricsFormatError("cannot determine full Execution BASE")
    return value


def _require_clean_code_worktree(base_path: Path) -> None:
    dirty = subprocess.run(
        [
            "git", "-C", str(base_path), "status", "--porcelain=v1",
            "--untracked-files=all", "--", ".", ":(exclude).req-to-plan",
        ],
        capture_output=True,
        check=False,
    )
    if dirty.returncode != 0 or dirty.stdout:
        raise MetricsFormatError("code worktree outside .req-to-plan must be clean")


def _resolve_commit(base_path: Path, abbreviation: str) -> str:
    if not _SHA7.fullmatch(abbreviation):
        raise PrerequisiteError("commit abbreviation is not canonical")
    result = subprocess.run(
        ["git", "-C", str(base_path), "rev-parse", "--verify", f"{abbreviation}^{{commit}}"],
        capture_output=True,
        text=True,
        check=False,
    )
    value = result.stdout.strip()
    if result.returncode != 0 or not re.fullmatch(r"[0-9a-f]{40}", value):
        raise PrerequisiteError("commit abbreviation is missing or ambiguous")
    return value


def _resolve_commit_or_full(base_path: Path, value: str) -> str:
    if not (_SHA7.fullmatch(value) or re.fullmatch(r"[0-9a-f]{40}", value)):
        raise PrerequisiteError("commit identifier is not canonical")
    result = subprocess.run(
        ["git", "-C", str(base_path), "rev-parse", "--verify", f"{value}^{{commit}}"],
        capture_output=True,
        text=True,
        check=False,
    )
    resolved = result.stdout.strip()
    if result.returncode != 0 or not re.fullmatch(r"[0-9a-f]{40}", resolved):
        raise PrerequisiteError("commit identifier is missing or ambiguous")
    return resolved


def _is_ancestor(base_path: Path, ancestor: str, descendant: str) -> bool:
    result = subprocess.run(
        ["git", "-C", str(base_path), "merge-base", "--is-ancestor", ancestor, descendant],
        capture_output=True,
        check=False,
    )
    if result.returncode == 0:
        return True
    if result.returncode == 1:
        return False
    raise PrerequisiteError("cannot verify ledger commit ancestry")


def _initial_metrics_text(work_id: WorkId, profile: str, task_count: int) -> str:
    return "\n".join((
        "# Execution Metrics", f"work_id: {work_id}", f"r2p_version: {R2P_VERSION}",
        f"instrumentation_schema: {INSTRUMENTATION_SCHEMA}", f"profile: {profile}",
        f"task_count: {task_count}", "instrumentation_complete: true", "bootstrap_gap: none",
        "change_shape: unavailable", "metrics_finalized: false", "",
    ))


def _legacy_metrics_text(
    work_id: WorkId,
    task_count: int,
    start_task: int | None,
) -> str:
    gap = (
        "legacy_metrics_start_final"
        if start_task is None
        else f"legacy_metrics_start_task_{start_task:03d}"
    )
    return "\n".join((
        "# Execution Metrics", f"work_id: {work_id}", f"r2p_version: {R2P_VERSION}",
        f"instrumentation_schema: {INSTRUMENTATION_SCHEMA}", "profile: strict",
        f"task_count: {task_count}", "instrumentation_complete: false",
        f"bootstrap_gap: {gap}", "change_shape: unavailable",
        "metrics_finalized: false", "",
    ))


def _initial_progress_text(
    work_id: WorkId,
    execution_base: str,
    anchors: list[tuple[str, str]],
    profile: str,
) -> str:
    lines = [
        "# Execution Progress", "", f"work_id: {work_id}", "",
        f"Execution BASE: {execution_base}", "", f"Execution Profile: {profile}", "",
    ]
    lines.extend(f"- [ ] {task_id} {title}".rstrip() for task_id, title in anchors)
    return "\n".join(lines) + "\n"


def start_execution_transaction(base_path: Path, work_id: WorkId, profile: str) -> RunRecord:
    """Own the pinned, no-clobber execution-start transaction and recovery."""
    if profile not in {"strict", "fast"}:
        raise MetricsFormatError("profile must be strict or fast")
    base_path = Path(base_path)
    repo_fd = workspace_fd = run_fd = None
    logs_fd = lock_fd = None
    try:
        repo_fd, workspace_fd, run_fd = _open_run(base_path, work_id)
        logs_fd, lock_fd = _open_lock_at(run_fd, "execute-start.lock")
        record = _parse_record_at(run_fd, work_id)
        plan = _plan_at(run_fd)
        anchors = plan_task_anchors(strip_nonsemantic_markdown(plan))
        if not anchors:
            raise MetricsFormatError("PLAN contains no PLAN-TASK anchors")
        try:
            version = prerequisite_semantics_version(plan)
        except ExecutionProfileError as exc:
            raise PrerequisiteError(str(exc)) from exc
        if profile == "fast" and version != 2:
            raise PrerequisiteError("fast requires prerequisite semantics version 2")

        if record.status == RunStatus.EXECUTING:
            execution_fd = _open_dir_at(run_fd, "execution")
            try:
                progress = _read_text_at(execution_fd, "progress.md")
                owner_marker = _read_text_at(
                    run_fd, START_TRANSACTION_OWNER, missing_ok=True
                )
                existing_marker = _read_text_at(
                    execution_fd, ".start-transaction.json", missing_ok=True
                )
                assert progress is not None
                semantic_progress = "\n".join(
                    line
                    for line, _, _ in unfenced_markdown_lines(
                        strip_nonsemantic_markdown(progress)
                    )
                )
                base_match = re.search(
                    r"^Execution BASE: ([0-9a-f]{40})$",
                    semantic_progress,
                    re.MULTILINE,
                )
                profile_lines = re.findall(
                    r"^Execution Profile: (strict|fast)$",
                    semantic_progress,
                    re.MULTILINE,
                )
                rows = [
                    match.group(2)
                    for line in semantic_progress.splitlines()
                    if (match := PLAN_TASK_CHECKBOX_RE.match(line))
                ]
                profile_like = re.findall(
                    r"^\s*Execution\s+Profile[A-Za-z0-9_-]*\s*:.*$",
                    semantic_progress,
                    re.MULTILINE,
                )
                legacy_profileless_strict = (
                    existing_marker is None
                    and profile == "strict"
                    and not profile_lines
                    and not profile_like
                )
                if (
                    base_match is None
                    or not (
                        profile_lines == [profile] or legacy_profileless_strict
                    )
                    or rows != [task_id for task_id, _ in anchors]
                ):
                    raise MetricsFormatError("executing progress does not match start contract")
                # Once start is durable, observations are never a resume gate.
                # An old profileless run may receive its observable bootstrap,
                # but status/append own reporting any metrics defect thereafter.
                if owner_marker is None and existing_marker is None:
                    if legacy_profileless_strict:
                        legacy_ledger = parse_execution_ledger(
                            progress, tuple(task_id for task_id, _ in anchors)
                        )
                        try:
                            if _read_text_at(execution_fd, "metrics.md", missing_ok=True) is None:
                                _publish_new_text_at(execution_fd, "metrics.md", _legacy_metrics_text(
                                    work_id, len(anchors), legacy_ledger.first_actionable_task(),
                                ))
                        except (MetricsFormatError, OSError):
                            import warnings
                            warnings.warn("metrics_incomplete: legacy observation bootstrap failed", RuntimeWarning)
                    return record
                metrics_text = _read_text_at(execution_fd, "metrics.md", missing_ok=True)
                if metrics_text is None:
                    if not legacy_profileless_strict:
                        raise MetricsFormatError("executing run metrics.md is missing")
                    task_ids = tuple(task_id for task_id, _ in anchors)
                    try:
                        legacy_ledger = parse_execution_ledger(progress, task_ids)
                    except ExecutionProfileError as exc:
                        raise MetricsFormatError(
                            f"legacy execution progress is invalid: {exc}"
                        ) from exc
                    metrics_text = _legacy_metrics_text(
                        work_id,
                        len(anchors),
                        legacy_ledger.first_actionable_task(),
                    )
                    _publish_new_text_at(execution_fd, "metrics.md", metrics_text)
                metrics = parse_metrics(metrics_text)
                if (
                    metrics.header["work_id"] != str(work_id)
                    or metrics.header["profile"] != profile
                    or metrics.header["task_count"] != len(anchors)
                ):
                    raise MetricsFormatError("executing run metrics work_id/profile/task count conflicts")
                expected = {
                    "schema": 1,
                    "work_id": str(work_id),
                    "profile": profile,
                    "task_count": len(anchors),
                    "execution_base": base_match.group(1),
                }
                expected_marker_text = _canonical_json(expected) + "\n"
                if owner_marker is not None and owner_marker != expected_marker_text:
                    raise MetricsFormatError(
                        "execution start owner does not match complete ledgers"
                    )
                if existing_marker is not None:
                    if owner_marker is None and existing_marker != expected_marker_text:
                        raise MetricsFormatError("execution start marker does not match complete ledgers")
                    os.unlink(".start-transaction.json", dir_fd=execution_fd)
                    os.fsync(execution_fd)
                if owner_marker is not None:
                    os.unlink(START_TRANSACTION_OWNER, dir_fd=run_fd)
                    os.fsync(run_fd)
                return record
            finally:
                os.close(execution_fd)

        if record.status != RunStatus.CLOSED_AT_PLAN_CHECKPOINT:
            raise MetricsFormatError("run is not closed at the PLAN checkpoint")

        _require_clean_code_worktree(base_path)
        execution_base = _execution_base(base_path)
        marker_payload = {
            "schema": 1, "work_id": str(work_id), "profile": profile,
            "task_count": len(anchors), "execution_base": execution_base,
        }
        marker_text = _canonical_json(marker_payload) + "\n"
        expected_progress = _initial_progress_text(work_id, execution_base, anchors, profile)
        expected_metrics = _initial_metrics_text(work_id, profile, len(anchors))

        # Closed-run recovery. The run-level owner is atomically published
        # before execution/ exists, so even an empty directory or truncated
        # inner marker remains safely attributable after power loss.
        owner_marker = _read_text_at(
            run_fd, START_TRANSACTION_OWNER, missing_ok=True
        )
        if owner_marker is not None and owner_marker != marker_text:
            raise MetricsFormatError("foreign execution-start owner residue")
        try:
            execution_fd = _open_dir_at(run_fd, "execution")
        except MetricsFormatError as exc:
            try:
                os.stat("execution", dir_fd=run_fd, follow_symlinks=False)
            except FileNotFoundError:
                execution_fd = None
            else:
                raise exc
        if execution_fd is not None:
            try:
                existing_marker = _read_text_at(execution_fd, ".start-transaction.json", missing_ok=True)
                children = set(os.listdir(execution_fd))
                allowed = {".start-transaction.json", "progress.md", "metrics.md"}
                if owner_marker is not None:
                    _clear_owned_execution_dir(execution_fd)
                    os.close(execution_fd)
                    execution_fd = None
                    os.rmdir("execution", dir_fd=run_fd)
                    os.fsync(run_fd)
                    os.unlink(START_TRANSACTION_OWNER, dir_fd=run_fd)
                    owner_marker = None
                    os.fsync(run_fd)
                elif existing_marker is not None:
                    if existing_marker != marker_text or not children <= allowed:
                        raise MetricsFormatError("foreign execution-start residue")
                    # Promote old inner-marker ownership before destructive
                    # cleanup, closing the prior unlink/rmdir crash window.
                    _publish_new_text_at(
                        run_fd, START_TRANSACTION_OWNER, marker_text
                    )
                    _clear_owned_execution_dir(execution_fd)
                    os.close(execution_fd)
                    execution_fd = None
                    os.rmdir("execution", dir_fd=run_fd)
                    os.fsync(run_fd)
                    os.unlink(START_TRANSACTION_OWNER, dir_fd=run_fd)
                    os.fsync(run_fd)
                elif children == {"progress.md", "metrics.md"}:
                    progress = _read_text_at(execution_fd, "progress.md")
                    metrics_text = _read_text_at(execution_fd, "metrics.md")
                    if progress != expected_progress or metrics_text != expected_metrics:
                        raise MetricsFormatError("closed run has foreign complete ledgers")
                    record = update_run_status(record, RunStatus.EXECUTING)
                    update_resume_context(record, last_operation="execute_start", next_operation="implement_tasks")
                    _replace_text_at(run_fd, "run.md", run_record_to_markdown(record))
                    return record
                else:
                    raise MetricsFormatError("closed run has incomplete unowned execution residue")
            finally:
                if execution_fd is not None:
                    os.close(execution_fd)
        elif owner_marker is not None:
            os.unlink(START_TRANSACTION_OWNER, dir_fd=run_fd)
            os.fsync(run_fd)

        _publish_new_text_at(run_fd, START_TRANSACTION_OWNER, marker_text)
        os.mkdir("execution", 0o700, dir_fd=run_fd)
        execution_fd = _open_dir_at(run_fd, "execution")
        owned_identity = os.fstat(execution_fd)
        state_saved = False
        try:
            _write_new_text_at(execution_fd, ".start-transaction.json", marker_text)
            _write_new_text_at(execution_fd, "progress.md", expected_progress)
            _write_new_text_at(execution_fd, "metrics.md", expected_metrics)
            if parse_metrics(_read_text_at(execution_fd, "metrics.md") or "").header["profile"] != profile:
                raise MetricsFormatError("written metrics failed validation")
            if _read_text_at(execution_fd, "progress.md") != expected_progress:
                raise MetricsFormatError("written progress failed validation")
            record = update_run_status(record, RunStatus.EXECUTING)
            update_resume_context(record, last_operation="execute_start", next_operation="implement_tasks")
            try:
                _replace_text_at(run_fd, "run.md", run_record_to_markdown(record))
            except _CommittedWriteError:
                state_saved = True
                raise
            else:
                state_saved = True
            os.unlink(".start-transaction.json", dir_fd=execution_fd)
            os.fsync(execution_fd)
            os.unlink(START_TRANSACTION_OWNER, dir_fd=run_fd)
            os.fsync(run_fd)
            return record
        except Exception:
            if not state_saved:
                try:
                    current_dir = os.stat("execution", dir_fd=run_fd, follow_symlinks=False)
                    children = set(os.listdir(execution_fd))
                    if (
                        stat.S_ISDIR(current_dir.st_mode)
                        and (current_dir.st_dev, current_dir.st_ino) == (owned_identity.st_dev, owned_identity.st_ino)
                    ):
                        _clear_owned_execution_dir(execution_fd)
                        os.close(execution_fd)
                        execution_fd = None
                        os.rmdir("execution", dir_fd=run_fd)
                        os.fsync(run_fd)
                        os.unlink(START_TRANSACTION_OWNER, dir_fd=run_fd)
                        os.fsync(run_fd)
                except Exception:
                    pass
            raise
        finally:
            if execution_fd is not None:
                os.close(execution_fd)
    finally:
        if lock_fd is not None and logs_fd is not None:
            _release_lock(logs_fd, lock_fd)
        _close_fds(run_fd, workspace_fd, repo_fd)


def _read_prerequisite_inputs(
    base_path: Path, work_id: WorkId
) -> tuple[RunRecord, str, str]:
    """Read one identity-checked run through pinned directory descriptors."""
    repo_fd = workspace_fd = run_fd = execution_fd = None
    try:
        repo_fd, workspace_fd, run_fd = _open_run(Path(base_path), work_id)
        record = _parse_record_at(run_fd, work_id)
        if record.status != RunStatus.EXECUTING:
            raise PrerequisiteError("run must be EXECUTING")
        plan = _plan_at(run_fd)
        execution_fd = _open_dir_at(run_fd, "execution")
        progress = _read_text_at(execution_fd, "progress.md")
        assert progress is not None
        return record, plan, progress
    except (MetricsFormatError, OSError) as exc:
        raise PrerequisiteError(str(exc)) from exc
    finally:
        _close_fds(execution_fd, run_fd, workspace_fd, repo_fd)


def _semantic_progress(progress: str) -> str:
    return "".join(
        line for line, _, _ in unfenced_markdown_lines(
            strip_nonsemantic_markdown(progress)
        )
    )


def _marker_for(progress: str, task: int) -> tuple[str, str] | None:
    pattern = re.compile(rf"^Task {task}: complete \(commits ([0-9a-f]{{7}})\.\.([0-9a-f]{{7}}), (?:review|final review) clean\)$", re.MULTILINE)
    found = pattern.findall(_semantic_progress(progress))
    if len(found) > 1:
        raise PrerequisiteError(f"Task {task} has duplicate completion markers")
    return found[0] if found else None


def check_prerequisite_v1(base_path: Path, work_id: WorkId, task: int) -> dict[str, Any]:
    """Validate strict prerequisite semantics v1 without mutating the run."""
    _, plan_text, progress = _read_prerequisite_inputs(base_path, work_id)
    anchors = plan_task_anchors(strip_nonsemantic_markdown(plan_text))
    expected = [f"PLAN-TASK-{number:03d}" for number in range(1, len(anchors) + 1)]
    if not anchors or [anchor[0] for anchor in anchors] != expected:
        raise PrerequisiteError("PLAN must have contiguous task anchors")
    if task < 1 or task > len(anchors):
        raise PrerequisiteError("task is outside PLAN bounds")
    if task in {1, 2} and str(work_id) == SELF_HOSTED_WORK_ID and len(anchors) != 9:
        raise PrerequisiteError("self-hosted PLAN must have exactly nine task anchors")
    progress = _semantic_progress(progress)
    profile_lines = re.findall(r"^Execution Profile: (\S+)$", progress, re.MULTILINE)
    escalation_lines = re.findall(r"^Profile Escalation:.*$", progress, re.MULTILINE)
    implemented_lines = re.findall(r"^Task \d+: implemented.*$", progress, re.MULTILINE)
    if escalation_lines or implemented_lines:
        raise PrerequisiteError("prerequisite v1 rejects fast-only ledger state")
    if profile_lines not in ([], ["strict"]):
        raise PrerequisiteError("prerequisite v1 requires legacy or explicit strict profile")
    try:
        ledger = parse_execution_ledger(progress, tuple(expected))
    except ExecutionProfileError as exc:
        raise PrerequisiteError(str(exc)) from exc
    complete_markers = {
        marker.number: (marker.base, marker.head) for marker in ledger.markers
    }
    if ledger.first_actionable_task() != task:
        raise PrerequisiteError("task is not the lowest unchecked task")
    head = _execution_base(Path(base_path))
    if ledger.journal is not None:
        try:
            validate_ledger_commit_chain(
                ledger, current_head=head,
                resolve_commit=lambda value: _resolve_commit_or_full(Path(base_path), value),
                is_ancestor=lambda older, newer: _is_ancestor(Path(base_path), older, newer),
            )
        except ExecutionProfileError as exc:
            raise PrerequisiteError(str(exc)) from exc
    elif task == 1:
        historical_self_host_profile = (
            str(work_id) == SELF_HOSTED_WORK_ID and bool(profile_lines)
        )
        if (
            ledger.reviewed_complete
            or complete_markers
            or historical_self_host_profile
        ):
            raise PrerequisiteError("Task 001 legacy preflight requires untouched ledger state")
        if ledger.execution_base != head:
            raise PrerequisiteError("Task 001 requires full Execution BASE to equal HEAD")
    else:
        for number in range(1, task):
            if number not in ledger.reviewed_complete:
                raise PrerequisiteError("all predecessor tasks must be reviewed-complete")
        if any(number >= task for number in complete_markers):
            raise PrerequisiteError("later task marker precedes current dispatch")
        prior = complete_markers[task - 1]
        if _resolve_commit(Path(base_path), prior[1]) != head:
            raise PrerequisiteError("HEAD must equal predecessor reviewed-complete head")
        expected_base = ledger.execution_base[:7] if task == 2 else complete_markers[task - 2][1]
        if prior[0] != expected_base:
            raise PrerequisiteError("completion marker BASE chain is discontinuous")
    prerequisite = "none" if task == 1 else f"PLAN-TASK-{task - 1:03d}"
    return {
        "work_id": str(work_id),
        "task": task,
        "implementation_version": PREREQUISITE_IMPLEMENTATION_VERSION,
        "semantics_version": 1,
        "effective_profile": "strict",
        "prerequisite": prerequisite,
        "satisfied": True,
        "task_count": len(anchors),
        "execution_base": ledger.execution_base,
    }


def check_prerequisite(
    base_path: Path,
    work_id: WorkId,
    task: int,
    *,
    require_version: int,
) -> dict[str, Any]:
    """Dispatch the requested compatible prerequisite semantics version."""
    if require_version < 1 or require_version > PREREQUISITE_IMPLEMENTATION_VERSION:
        raise PrerequisiteError("requested prerequisite semantics version is unsupported")
    if require_version == 1:
        return check_prerequisite_v1(base_path, work_id, task)

    _, plan, progress = _read_prerequisite_inputs(base_path, work_id)
    try:
        result = check_prerequisite_v2(progress, plan, task)
        task_ids = tuple(
            task_id
            for task_id, _ in plan_task_anchors(strip_nonsemantic_markdown(plan))
        )
        parsed = parse_execution_ledger(progress, task_ids)
        current_head = _execution_base(Path(base_path))
        validate_ledger_commit_chain(
            parsed,
            current_head=current_head,
            resolve_commit=lambda value: _resolve_commit_or_full(Path(base_path), value),
            is_ancestor=lambda ancestor, descendant: _is_ancestor(
                Path(base_path), ancestor, descendant
            ),
        )
    except (ExecutionProfileError, OSError) as exc:
        raise PrerequisiteError(str(exc)) from exc
    return {
        "work_id": str(work_id),
        "implementation_version": PREREQUISITE_IMPLEMENTATION_VERSION,
        **result,
    }


def _bootstrap_metrics_text(work_id: WorkId, profile: str, task_count: int) -> str:
    return "\n".join((
        "# Execution Metrics", f"work_id: {work_id}", f"r2p_version: {R2P_VERSION}",
        f"instrumentation_schema: {INSTRUMENTATION_SCHEMA}", f"profile: {profile}",
        f"task_count: {task_count}", "instrumentation_complete: false",
        f"bootstrap_gap: {SELF_HOSTED_BOOTSTRAP_GAP}", "change_shape: unavailable",
        "metrics_finalized: false", "",
    ))


def _validate_bootstrap_retry_state(
    progress: str,
    rows: list[tuple[str, str]],
    invocations: tuple[dict[str, Any], ...],
) -> None:
    """Bind Task 003+ metrics groups to the strict progress frontier."""
    progress = _semantic_progress(progress)
    completed: set[int] = set()
    untouched_seen = False
    marker_like = re.findall(r"^Task (\d+): (?:implemented|complete).*$", progress, re.MULTILINE)
    valid_markers = 0
    for number, (checked, _) in enumerate(rows, start=1):
        marker = _marker_for(progress, number)
        if marker is not None:
            valid_markers += 1
        if (checked == "x") != (marker is not None):
            raise MetricsFormatError("bootstrap progress checkbox/task marker state is inconsistent")
        if checked == "x":
            if untouched_seen:
                raise MetricsFormatError("bootstrap progress reviewed-complete tasks are not a prefix")
            completed.add(number)
        else:
            untouched_seen = True
    if len(marker_like) != valid_markers or not {1, 2} <= completed:
        raise MetricsFormatError("bootstrap progress task markers are malformed or incomplete")

    groups: dict[int, list[dict[str, Any]]] = {}
    last_task = 2
    seen_final = False
    for invocation in invocations:
        task = invocation["task"]
        if task == "final":
            if len(completed) != len(rows):
                raise MetricsFormatError("bootstrap final invocation precedes completed progress")
            seen_final = True
            continue
        if seen_final or task < 3:
            raise MetricsFormatError("bootstrap invocation blocks are not Task 003+ ordered state")
        if task != last_task:
            if task != last_task + 1 or last_task not in completed:
                raise MetricsFormatError("bootstrap invocation task skips the legal progress frontier")
            last_task = task
        groups.setdefault(task, []).append(invocation)

    completed_after_bootstrap = sorted(number for number in completed if number >= 3)
    if completed_after_bootstrap != list(range(3, 3 + len(completed_after_bootstrap))):
        raise MetricsFormatError("bootstrap completed task state is not contiguous from Task 003")
    if any(number not in groups for number in completed_after_bootstrap):
        raise MetricsFormatError("bootstrap completed progress task lacks invocation evidence")
    for number, group in groups.items():
        roles = [item["role"] for item in group]
        if roles[0] != "implementer":
            raise MetricsFormatError("bootstrap task invocation group must start with implementer")
        if number in completed and not any(
            item["role"] in {"task_reviewer", "task_rereviewer"} and item["status"] == "approved"
            for item in group
        ):
            raise MetricsFormatError("bootstrap completed task lacks approved review evidence")


def bootstrap_self_hosted_metrics(base_path: Path, work_id: WorkId, through_task: int) -> ParsedMetrics:
    """Crash-idempotently publish or validate the self-hosted metrics ledger."""
    if str(work_id) != SELF_HOSTED_WORK_ID or through_task != 2:
        raise PrerequisiteError("self-hosted bootstrap arguments are not canonical")
    repo_fd = workspace_fd = run_fd = execution_fd = None
    logs_fd = lock_fd = None
    temp_name = ""
    temp_fd: int | None = None
    temp_identity: tuple[int, int] | None = None
    linked = False
    try:
        repo_fd, workspace_fd, run_fd = _open_run(Path(base_path), work_id)
        logs_fd, lock_fd = _open_lock_at(run_fd, "metrics-bootstrap.lock")
        record = _parse_record_at(run_fd, work_id)
        if record.status != RunStatus.EXECUTING:
            raise PrerequisiteError("self-hosted bootstrap requires an EXECUTING run")
        anchors = plan_task_anchors(strip_nonsemantic_markdown(_plan_at(run_fd)))
        if [item[0] for item in anchors] != [f"PLAN-TASK-{n:03d}" for n in range(1, 10)]:
            raise PrerequisiteError("self-hosted bootstrap requires the canonical nine-task PLAN")
        execution_fd = _open_dir_at(run_fd, "execution")
        progress = _read_text_at(execution_fd, "progress.md")
        assert progress is not None
        try:
            parse_execution_ledger(progress, tuple(item[0] for item in anchors))
        except ExecutionProfileError as exc:
            raise PrerequisiteError(f"self-hosted bootstrap progress is invalid: {exc}") from exc
        progress = _semantic_progress(progress)
        complete_one = _marker_for(progress, 1)
        complete_two = _marker_for(progress, 2)
        if complete_one is None or complete_two is None:
            raise PrerequisiteError("self-hosted bootstrap requires Tasks 001 and 002 reviewed-complete")
        base_match = re.search(r"^Execution BASE: ([0-9a-f]{40})$", progress, re.MULTILINE)
        profile_lines = re.findall(r"^Execution Profile: (\S+)$", progress, re.MULTILINE)
        rows = [
            (match.group(1).lower(), match.group(2))
            for line, _, _ in unfenced_markdown_lines(
                strip_nonsemantic_markdown(progress)
            )
            if (match := PLAN_TASK_CHECKBOX_RE.match(line))
        ]
        if (
            base_match is None
            or profile_lines not in ([], ["strict"])
            or [item[1] for item in rows] != [f"PLAN-TASK-{n:03d}" for n in range(1, 10)]
            or complete_one[0] != base_match.group(1)[:7]
            or complete_two[0] != complete_one[1]
        ):
            raise PrerequisiteError("self-hosted bootstrap progress/BASE chain is invalid")
        expected = _bootstrap_metrics_text(work_id, "strict", 9)
        expected_header = parse_metrics(expected).header
        existing = _read_text_at(execution_fd, "metrics.md", missing_ok=True)
        if existing is not None:
            parsed = parse_metrics(existing)
            if parsed.header != expected_header:
                raise MetricsFormatError("existing metrics header does not match bootstrap")
            _validate_bootstrap_retry_state(progress, rows, parsed.invocations)
            return parsed

        if re.search(r"^Task [3-9]:", progress, re.MULTILINE):
            raise PrerequisiteError("Task 003 must not have started before first bootstrap")
        if _resolve_commit(Path(base_path), complete_two[1]) != _execution_base(Path(base_path)):
            raise PrerequisiteError("self-hosted bootstrap requires HEAD at Task 002 reviewed-complete head")

        temp_name = f".metrics-bootstrap.{os.getpid()}.{secrets.token_hex(16)}.tmp"
        temp_fd = os.open(temp_name, _FILE_WRITE_FLAGS, 0o600, dir_fd=execution_fd)
        try:
            _write_all(temp_fd, expected.encode("utf-8"))
            os.fsync(temp_fd)
            source = os.fstat(temp_fd)
            temp_identity = (source.st_dev, source.st_ino)
            before = os.stat(temp_name, dir_fd=execution_fd, follow_symlinks=False)
            if not stat.S_ISREG(source.st_mode) or (source.st_dev, source.st_ino) != (before.st_dev, before.st_ino):
                raise MetricsFormatError("bootstrap temp identity changed")
            try:
                os.link(
                    temp_name,
                    "metrics.md",
                    src_dir_fd=execution_fd,
                    dst_dir_fd=execution_fd,
                    follow_symlinks=False,
                )
                linked = True
            except FileExistsError:
                concurrent = _read_text_at(execution_fd, "metrics.md")
                parsed = parse_metrics(concurrent or "")
                if parsed.header != expected_header or parsed.invocations:
                    raise MetricsFormatError("concurrent bootstrap target mismatches")
                return parsed
            final = os.stat("metrics.md", dir_fd=execution_fd, follow_symlinks=False)
            current = os.stat(temp_name, dir_fd=execution_fd, follow_symlinks=False)
            identity = (source.st_dev, source.st_ino)
            if (
                not stat.S_ISREG(final.st_mode)
                or (final.st_dev, final.st_ino) != identity
                or (current.st_dev, current.st_ino) != identity
            ):
                raise MetricsFormatError("bootstrap publish identity changed")
            os.fsync(execution_fd)
            os.unlink(temp_name, dir_fd=execution_fd)
            temp_name = ""
            os.fsync(execution_fd)
            return parse_metrics(_read_text_at(execution_fd, "metrics.md") or "")
        finally:
            if temp_fd is not None:
                os.close(temp_fd)
                temp_fd = None
    except Exception:
        if temp_name and not linked and execution_fd is not None:
            try:
                current = os.stat(temp_name, dir_fd=execution_fd, follow_symlinks=False)
                identity_matches = temp_identity is not None and (current.st_dev, current.st_ino) == temp_identity
                if identity_matches and _read_text_at(execution_fd, "metrics.md", missing_ok=True) is None:
                    os.unlink(temp_name, dir_fd=execution_fd)
            except Exception:
                pass
        raise
    finally:
        if temp_fd is not None:
            os.close(temp_fd)
        if lock_fd is not None and logs_fd is not None:
            _release_lock(logs_fd, lock_fd)
        _close_fds(execution_fd, run_fd, workspace_fd, repo_fd)


_APPEND_REQUIRED_KEYS = {
    "expected_sequence", "role", "task", "model", "started_at", "ended_at",
    "elapsed_seconds", "context_mode", "context_bytes", "verification_records",
    "report_path", "status", "concerns", "fix_wave",
}
_TOKEN_KEYS = {"input_tokens", "output_tokens", "total_tokens"}
_PENDING_COMPLETIONS_NAME = ".pending-completions.json"


def _read_pending_completions(execution_fd: int) -> list[dict[str, Any]]:
    text = _read_text_at(
        execution_fd, _PENDING_COMPLETIONS_NAME, missing_ok=True
    )
    if text is None:
        return []
    try:
        payload = json.loads(text)
    except (json.JSONDecodeError, ValueError) as exc:
        raise MetricsFormatError("pending completion journal is invalid") from exc
    if (
        not isinstance(payload, dict)
        or set(payload) != {"schema", "entries"}
        or payload["schema"] != 1
        or not isinstance(payload["entries"], list)
        or _canonical_json(payload) + "\n" != text
    ):
        raise MetricsFormatError("pending completion journal is not canonical")
    entries: list[dict[str, Any]] = []
    sequences: list[int] = []
    for entry in payload["entries"]:
        if (
            not isinstance(entry, dict)
            or set(entry) != {"sequence", "record", "invocation"}
            or isinstance(entry["sequence"], bool)
            or not isinstance(entry["sequence"], int)
            or entry["sequence"] <= 0
            or not isinstance(entry["record"], dict)
            or not isinstance(entry["invocation"], dict)
            or entry["record"].get("expected_sequence") != entry["sequence"]
            or entry["invocation"].get("sequence") != entry["sequence"]
        ):
            raise MetricsFormatError("pending completion entry is invalid")
        sequences.append(entry["sequence"])
        entries.append(entry)
    if sequences != sorted(set(sequences)):
        raise MetricsFormatError("pending completion sequences are not canonical")
    return entries


def _write_pending_completions(
    execution_fd: int, entries: list[dict[str, Any]]
) -> None:
    if entries:
        _replace_text_at(
            execution_fd,
            _PENDING_COMPLETIONS_NAME,
            _canonical_json({"schema": 1, "entries": entries}) + "\n",
        )
        return
    try:
        before = os.stat(
            _PENDING_COMPLETIONS_NAME,
            dir_fd=execution_fd,
            follow_symlinks=False,
        )
    except FileNotFoundError:
        return
    if not stat.S_ISREG(before.st_mode):
        raise MetricsFormatError("pending completion journal is unsafe")
    os.unlink(_PENDING_COMPLETIONS_NAME, dir_fd=execution_fd)
    os.fsync(execution_fd)


def _validate_pending_completions(
    parsed: ParsedMetrics, entries: list[dict[str, Any]]
) -> None:
    prepared = 0
    for entry in entries:
        sequence = entry["sequence"]
        if sequence <= len(parsed.invocations):
            if parsed.invocations[sequence - 1] != entry["invocation"]:
                raise MetricsFormatError(
                    "pending completion does not match metrics.md"
                )
        elif sequence == len(parsed.invocations) + 1:
            prepared += 1
        else:
            raise MetricsFormatError(
                "pending completion skips the metrics sequence"
            )
    if prepared > 1:
        raise MetricsFormatError(
            "pending completion journal has multiple prepared records"
        )


def _status_result(
    parsed: ParsedMetrics,
    result: str,
    pending: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    pending = pending or []
    public_pending = [
        {
            "sequence": entry["sequence"],
            "phase": (
                "appended"
                if entry["sequence"] <= len(parsed.invocations)
                else "prepared"
            ),
            "record_json": _canonical_json(entry["record"]),
        }
        for entry in pending
    ]
    return {
        "work_id": parsed.header["work_id"],
        "profile": parsed.header["profile"],
        "instrumentation_schema": parsed.header["instrumentation_schema"],
        "instrumentation_complete": parsed.header["instrumentation_complete"],
        "bootstrap_gap": parsed.header["bootstrap_gap"],
        "result": result,
        "invocation_count": len(parsed.invocations),
        "next_sequence": len(parsed.invocations) + 1,
        "metrics_finalized": parsed.header["metrics_finalized"],
        "change_shape": parsed.header["change_shape"],
        "pending_completion": public_pending[0] if public_pending else None,
        "pending_completions": public_pending,
    }


def _open_metrics_run(
    base_path: Path,
    work_id: WorkId,
) -> tuple[int, int, int, int, RunRecord, ParsedMetrics, str]:
    repo_fd = workspace_fd = run_fd = execution_fd = None
    try:
        repo_fd, workspace_fd, run_fd = _open_run(base_path, work_id)
        record = _parse_record_at(run_fd, work_id)
        if record.status != RunStatus.EXECUTING:
            raise MetricsFormatError("metrics operations require an EXECUTING run")
        anchors = plan_task_anchors(strip_nonsemantic_markdown(_plan_at(run_fd)))
        if not anchors:
            raise MetricsFormatError("PLAN contains no PLAN-TASK anchors")
        execution_fd = _open_dir_at(run_fd, "execution")
        metrics_text = _read_text_at(execution_fd, "metrics.md")
        progress = _read_text_at(execution_fd, "progress.md")
        assert metrics_text is not None and progress is not None
        parsed = parse_metrics(metrics_text)
        _validate_current_metrics(run_fd, work_id, parsed, progress)
        return repo_fd, workspace_fd, run_fd, execution_fd, record, parsed, progress
    except Exception:
        _close_fds(execution_fd, run_fd, workspace_fd, repo_fd)
        raise


def _validate_current_metrics(
    run_fd: int,
    work_id: WorkId,
    parsed: ParsedMetrics,
    progress: str,
) -> ParsedExecutionLedger | None:
    anchors = plan_task_anchors(strip_nonsemantic_markdown(_plan_at(run_fd)))
    semantic_progress = "\n".join(
        line
        for line, _, _ in unfenced_markdown_lines(
            strip_nonsemantic_markdown(progress)
        )
    )
    profiles = re.findall(
        r"^Execution Profile: (strict|fast)$", semantic_progress, re.MULTILINE
    )
    if not profiles:
        profiles = ["strict"]
    profile_like = re.findall(
        r"^\s*Execution\s+Profile[A-Za-z0-9_-]*\s*:.*$",
        semantic_progress,
        re.MULTILINE,
    )
    if (
        not anchors
        or parsed.header["work_id"] != str(work_id)
        or parsed.header["instrumentation_schema"] != INSTRUMENTATION_SCHEMA
        or parsed.header["task_count"] != len(anchors)
        or profiles != [parsed.header["profile"]]
        or (profile_like and len(profile_like) != len(profiles))
    ):
        raise MetricsFormatError("metrics header identity does not match the run")
    task_ids = tuple(task_id for task_id, _ in anchors)
    try:
        ledger = parse_execution_ledger(progress, task_ids)
    except ExecutionProfileError as exc:
        raise MetricsFormatError(f"execution progress is invalid: {exc}") from exc
    if ledger.initial_profile.value != parsed.header["profile"]:
        raise MetricsFormatError("metrics header profile does not match execution ledger")
    return ledger


def _is_self_host_partial(parsed: ParsedMetrics) -> bool:
    """Return whether this is the one non-representative self-host observation."""
    return (
        parsed.header["work_id"] == SELF_HOSTED_WORK_ID
        and not parsed.header["instrumentation_complete"]
        and parsed.header["bootstrap_gap"] == SELF_HOSTED_BOOTSTRAP_GAP
    )


def _legacy_metrics_start_task(parsed: ParsedMetrics) -> int | None:
    match = _LEGACY_BOOTSTRAP_GAP_RE.fullmatch(parsed.header["bootstrap_gap"])
    if match is None:
        raise MetricsFormatError("legacy metrics bootstrap gap is invalid")
    return int(match.group(1)) if match.group(1) is not None else None


def _is_legacy_partial(parsed: ParsedMetrics) -> bool:
    return (
        not parsed.header["instrumentation_complete"]
        and _LEGACY_BOOTSTRAP_GAP_RE.fullmatch(
            parsed.header["bootstrap_gap"]
        )
        is not None
    )


def _report_name(base_path: Path, work_id: WorkId, value: str) -> str:
    if not isinstance(value, str) or not value:
        raise MetricsFormatError("report_path must be a non-empty string")
    candidate = Path(value)
    if candidate.is_absolute():
        expected_parent = (
            Path(os.path.abspath(os.fspath(base_path)))
            / ".req-to-plan" / str(work_id) / "execution"
        )
        if candidate.parent != expected_parent:
            raise MetricsFormatError("report_path must be inside this run's execution directory")
        name = candidate.name
    else:
        parts = candidate.parts
        if len(parts) == 1:
            name = parts[0]
        elif len(parts) == 2 and parts[0] == "execution":
            name = parts[1]
        else:
            raise MetricsFormatError("report_path must name one execution artifact")
    if name in {"", ".", ".."} or "/" in name:
        raise MetricsFormatError("report_path is unsafe")
    return name


def _canonical_append_fields(
    base_path: Path,
    work_id: WorkId,
    execution_fd: int,
    record: dict[str, Any],
) -> tuple[int, tuple[str, ...]]:
    if not isinstance(record, dict):
        raise MetricsInputError("record must be a JSON object")
    keys = set(record)
    token_keys = keys & _TOKEN_KEYS
    if keys - _APPEND_REQUIRED_KEYS - _TOKEN_KEYS:
        raise MetricsInputError("record contains unknown keys")
    if not _APPEND_REQUIRED_KEYS <= keys:
        raise MetricsInputError("record is missing required keys")
    if token_keys and token_keys != _TOKEN_KEYS:
        raise MetricsInputError("token keys must be supplied as one complete group")

    sequence = record["expected_sequence"]
    if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence <= 0:
        raise MetricsInputError("expected_sequence must be a positive integer")
    string_fields = (
        "role", "model", "started_at", "ended_at", "elapsed_seconds",
        "context_mode", "status", "report_path",
    )
    if any(not isinstance(record[field], str) for field in string_fields):
        raise MetricsInputError("record scalar types are invalid")
    task = record["task"]
    if not ((isinstance(task, int) and not isinstance(task, bool)) or task == "final"):
        raise MetricsInputError("task must be a positive integer or final")
    context_bytes = record["context_bytes"]
    wave = record["fix_wave"]
    if (
        isinstance(context_bytes, bool) or not isinstance(context_bytes, int) or context_bytes < 0
        or isinstance(wave, bool) or not isinstance(wave, int) or wave < 0
    ):
        raise MetricsInputError("numeric record scalar is invalid")
    records = record["verification_records"]
    if records != "unavailable" and not isinstance(records, list):
        raise MetricsInputError("verification_records must be an array or unavailable")
    concerns = record["concerns"]
    if not isinstance(concerns, list) or not all(isinstance(item, str) for item in concerns):
        raise MetricsInputError("concerns must be an array of strings")
    if records == "unavailable":
        records_json = "unavailable"
        total_text = "unavailable"
    else:
        total = Decimal()
        for verification in records:
            if not isinstance(verification, dict) or set(verification) != {
                "command", "scope", "reason", "elapsed_seconds", "status"
            }:
                raise MetricsInputError("verification record schema is invalid")
            if not all(
                isinstance(verification.get(field), str)
                and bool(verification.get(field))
                for field in (
                    "command", "scope", "reason", "elapsed_seconds", "status"
                )
            ):
                raise MetricsInputError("verification record scalar is invalid")
            if verification["scope"] not in {
                "targeted", "directly_affected", "full_suite"
            } or verification["status"] not in {"passed", "failed"}:
                raise MetricsInputError("verification record enum is invalid")
            elapsed = verification.get("elapsed_seconds")
            assert isinstance(elapsed, str)
            try:
                total += _parse_decimal(elapsed, "verification record elapsed_seconds")
            except MetricsFormatError as exc:
                raise MetricsInputError(str(exc)) from exc
        records_json = _canonical_json(records)
        total_text = format(total, ".6f")
    context_kind = {
        "direct_acs": "declared_payload_bytes",
        "semantic_view": "semantic_payload_bytes",
    }.get(record["context_mode"])
    if context_kind is None:
        raise MetricsInputError("context_mode is invalid")
    role = record["role"]
    if role in {"implementer", "fixer", "task_reviewer", "task_rereviewer"} and isinstance(task, int) and task > 0:
        suffix = "review" if role in {"task_reviewer", "task_rereviewer"} else "report"
        expected_report = f"task-{task}-{suffix}.md"
    elif role in {"final_reviewer", "final_fixer", "final_rereviewer"} and task == "final":
        expected_report = "final-review-report.md"
    else:
        raise MetricsInputError("report_path requires a valid role and task")
    report_name = _report_name(base_path, work_id, record["report_path"])
    if report_name != expected_report:
        raise MetricsInputError(f"report_path for {role}/{task} must name {expected_report}")
    report_text = _read_text_at(execution_fd, report_name)
    assert report_text is not None
    tokens: list[str]
    if token_keys:
        values = [record[name] for name in ("input_tokens", "output_tokens", "total_tokens")]
        if any(isinstance(value, bool) or not isinstance(value, int) or value < 0 for value in values):
            raise MetricsInputError("token values must be non-negative integers")
        tokens = [str(value) for value in values]
    else:
        tokens = ["unavailable"] * 3
    fields = (
        str(record["role"]), str(task), str(record["model"]),
        str(record["started_at"]), str(record["ended_at"]), str(record["elapsed_seconds"]),
        str(record["context_mode"]), context_kind, str(context_bytes),
        records_json, total_text,
        str(len(report_text.encode("utf-8"))), str(record["status"]),
        _canonical_json(concerns), str(wave), *tokens,
    )
    return sequence, fields


def _invocation_block(sequence: int, fields: tuple[str, ...]) -> str:
    lines = [f"## Invocation {sequence}"]
    lines.extend(f"{name}: {value}" for name, value in zip(_INVOCATION_FIELDS, fields))
    return "\n".join(lines) + "\n"


def _validate_strict_role_sequence(
    invocations: tuple[dict[str, Any], ...],
    task_count: int,
    *,
    start_task: int = 1,
    start_at_final: bool = False,
    require_complete: bool = False,
    implemented_through: int = 0,
) -> None:
    if start_task < 1 or start_task > task_count:
        raise MetricsFormatError("role sequence start task is outside PLAN bounds")
    task = start_task
    expected_role = "final_reviewer" if start_at_final else "task_reviewer" if start_task <= implemented_through else "implementer"
    expected_wave = 0
    complete = False
    for invocation in invocations:
        if complete:
            raise MetricsFormatError("illegal role transition after terminal role status")
        if (
            invocation["role"] != expected_role
            or invocation["task"] != ("final" if expected_role.startswith("final_") else task)
            or invocation["fix_wave"] != expected_wave
        ):
            raise MetricsFormatError("illegal role transition")
        status = invocation["status"]
        if status == "blocked":
            continue
        if expected_role == "implementer":
            expected_role = "task_reviewer"
        elif expected_role == "task_reviewer":
            if status == "approved":
                if task == task_count:
                    expected_role = "final_reviewer"
                else:
                    task += 1
                    expected_role = "task_reviewer" if task <= implemented_through else "implementer"
                expected_wave = 0
            else:
                expected_role = "fixer"
                expected_wave = 1
        elif expected_role == "fixer":
            expected_role = "task_rereviewer"
        elif expected_role == "task_rereviewer":
            if status == "approved":
                if task == task_count:
                    expected_role = "final_reviewer"
                else:
                    task += 1
                    expected_role = "task_reviewer" if task <= implemented_through else "implementer"
                expected_wave = 0
            else:
                expected_role = "fixer"
                expected_wave += 1
        elif expected_role == "final_reviewer":
            if status == "approved":
                complete = True
            else:
                expected_role = "final_fixer"
                expected_wave = 1
        elif expected_role == "final_fixer":
            expected_role = "final_rereviewer"
        elif expected_role == "final_rereviewer":
            if status == "approved":
                complete = True
            else:
                expected_role = "final_fixer"
                expected_wave += 1
    if require_complete and not complete:
        raise MetricsFormatError("role sequence is incomplete")


def _validate_fast_role_sequence(
    invocations: tuple[dict[str, Any], ...],
    task_count: int,
    *,
    require_complete: bool = False,
) -> None:
    task = 1
    expected_role = "implementer"
    expected_wave = 0
    complete = False
    for invocation in invocations:
        if complete:
            raise MetricsFormatError("illegal role transition after terminal role status")
        expected_task: int | str = (
            "final" if expected_role.startswith("final_") else task
        )
        if (
            invocation["role"] != expected_role
            or invocation["task"] != expected_task
            or invocation["fix_wave"] != expected_wave
        ):
            raise MetricsFormatError("illegal role transition")
        status = invocation["status"]
        if status == "blocked":
            continue
        if expected_role == "implementer":
            if task == task_count:
                expected_role = "final_reviewer"
            else:
                task += 1
        elif expected_role == "final_reviewer":
            if status == "approved":
                complete = True
            else:
                expected_role = "final_fixer"
                expected_wave = 1
        elif expected_role == "final_fixer":
            expected_role = "final_rereviewer"
        elif expected_role == "final_rereviewer":
            if status == "approved":
                complete = True
            else:
                expected_role = "final_fixer"
                expected_wave += 1
    if require_complete and not complete:
        raise MetricsFormatError("role sequence is incomplete")


def _validate_escalated_fast_role_sequence(
    invocations: tuple[dict[str, Any], ...],
    task_count: int,
    *,
    require_complete: bool = False,
) -> None:
    # Preserve every real fast dispatch, including a primary final review and
    # its repair attempts, before the first strict task review. A retry of a
    # blocked role remains at that role rather than ending the entire run.
    boundary = next((
        index for index, invocation in enumerate(invocations)
        if invocation["role"] == "task_reviewer" and invocation["task"] == 1
    ), len(invocations))
    prefix = invocations[:boundary]
    _validate_fast_role_sequence(prefix, task_count)
    implemented = {
        invocation["task"] for invocation in prefix
        if invocation["role"] == "implementer" and invocation["status"] == "complete"
    }
    if boundary == len(invocations):
        if require_complete:
            raise MetricsFormatError("escalated role sequence is incomplete")
        return
    _validate_strict_role_sequence(
        invocations[boundary:], task_count,
        implemented_through=len(implemented), require_complete=require_complete,
    )


def validate_role_sequence(
    invocations: tuple[dict[str, Any], ...],
    *,
    profile: str,
    task_count: int,
    require_complete: bool = False,
) -> None:
    """Validate the truthful role topology for an initial execution profile."""
    if profile == "strict":
        _validate_strict_role_sequence(
            invocations, task_count, require_complete=require_complete
        )
        return
    if profile == "fast":
        _validate_fast_role_sequence(
            invocations, task_count, require_complete=require_complete
        )
        return
    raise MetricsFormatError("profile must be strict or fast")


def _metrics_identity(execution_fd: int) -> tuple[int, int]:
    before = os.stat("metrics.md", dir_fd=execution_fd, follow_symlinks=False)
    if not stat.S_ISREG(before.st_mode):
        raise MetricsFormatError("unsafe non-regular file: metrics.md")
    return before.st_dev, before.st_ino


def _publish_metrics(
    execution_fd: int,
    previous_identity: tuple[int, int],
    text: str,
) -> ParsedMetrics:
    current = os.stat("metrics.md", dir_fd=execution_fd, follow_symlinks=False)
    if not stat.S_ISREG(current.st_mode) or (current.st_dev, current.st_ino) != previous_identity:
        raise MetricsFormatError("metrics.md identity changed before publish")
    _replace_text_at(execution_fd, "metrics.md", text)
    committed = _read_text_at(execution_fd, "metrics.md")
    assert committed is not None
    if committed != text:
        raise MetricsFormatError("committed metrics text does not match request")
    return parse_metrics(committed)


def read_metrics_status(base_path: Path, work_id: WorkId) -> dict[str, Any]:
    """Return the canonical next metrics sequence without mutating metrics.md."""
    repo_fd = workspace_fd = run_fd = execution_fd = None
    logs_fd = lock_fd = None
    try:
        repo_fd, workspace_fd, run_fd, execution_fd, _, parsed, _ = _open_metrics_run(
            Path(base_path), work_id
        )
        logs_fd, lock_fd = _open_lock_at(run_fd, "metrics.lock")
        current = parse_metrics(_read_text_at(execution_fd, "metrics.md") or "")
        progress = _read_text_at(execution_fd, "progress.md")
        assert progress is not None
        _validate_current_metrics(run_fd, work_id, current, progress)
        pending = _read_pending_completions(execution_fd)
        _validate_pending_completions(current, pending)
        return _status_result(
            current,
            "status",
            pending,
        )
    finally:
        if lock_fd is not None and logs_fd is not None:
            _release_lock(logs_fd, lock_fd)
        _close_fds(execution_fd, run_fd, workspace_fd, repo_fd)


def append_metrics_invocation(
    base_path: Path,
    work_id: WorkId,
    record: dict[str, Any],
) -> dict[str, Any]:
    """Validate, sequence, and atomically append one controller role record."""
    repo_fd = workspace_fd = run_fd = execution_fd = None
    logs_fd = lock_fd = None
    try:
        repo_fd, workspace_fd, run_fd, execution_fd, _, _, _ = _open_metrics_run(
            Path(base_path), work_id
        )
        logs_fd, lock_fd = _open_lock_at(run_fd, "metrics.lock")
        identity = _metrics_identity(execution_fd)
        text = _read_text_at(execution_fd, "metrics.md")
        assert text is not None
        parsed = parse_metrics(text)
        pending = _read_pending_completions(execution_fd)
        _validate_pending_completions(parsed, pending)
        progress = _read_text_at(execution_fd, "progress.md")
        assert progress is not None
        execution_ledger = _validate_current_metrics(
            run_fd, work_id, parsed, progress
        )
        sequence, fields = _canonical_append_fields(
            Path(base_path), work_id, execution_fd, record
        )
        block = _invocation_block(sequence, fields)
        if sequence <= len(parsed.invocations):
            header = _initial_metrics_text(
                work_id, parsed.header["profile"], parsed.header["task_count"]
            )
            try:
                normalized = dict(
                    parse_metrics(
                        header + _invocation_block(1, fields)
                    ).invocations[0]
                )
            except MetricsFormatError as exc:
                raise MetricsInputError(str(exc)) from exc
            normalized["sequence"] = sequence
            if parsed.invocations[sequence - 1] != normalized:
                raise MetricsFormatError("conflicting retry for existing sequence")
            result = _status_result(parsed, "already_applied", pending)
        else:
            if sequence != len(parsed.invocations) + 1:
                raise MetricsFormatError("expected sequence skips the canonical next sequence")
            if parsed.header["metrics_finalized"]:
                raise MetricsFormatError("cannot append after metrics finalization")
            candidate = text.rstrip("\n") + "\n\n" + block
            try:
                updated = parse_metrics(candidate)
            except MetricsFormatError as exc:
                raise MetricsInputError(str(exc)) from exc
            if _is_self_host_partial(updated):
                if any(
                    invocation["task"] != "final" and invocation["task"] < 3
                    for invocation in updated.invocations
                ):
                    raise MetricsFormatError(
                        "self-host partial metrics cannot append pre-bootstrap Task 003 evidence"
                    )
            elif _is_legacy_partial(updated):
                start_task = _legacy_metrics_start_task(updated)
                _validate_strict_role_sequence(
                    updated.invocations,
                    updated.header["task_count"],
                    start_task=(
                        updated.header["task_count"]
                        if start_task is None
                        else start_task
                    ),
                    start_at_final=start_task is None,
                )
            else:
                if (
                    execution_ledger is not None
                    and execution_ledger.initial_profile is ExecutionProfile.FAST
                    and execution_ledger.effective_profile is ExecutionProfile.STRICT
                ):
                    _validate_escalated_fast_role_sequence(
                        updated.invocations,
                        updated.header["task_count"],
                    )
                else:
                    validate_role_sequence(
                        updated.invocations,
                        profile=updated.header["profile"],
                        task_count=updated.header["task_count"],
                    )
            invocation = dict(updated.invocations[-1])
            entry = {
                "sequence": sequence,
                "record": json.loads(_canonical_json(record)),
                "invocation": invocation,
            }
            prior = next(
                (item for item in pending if item["sequence"] == sequence),
                None,
            )
            if prior is not None and prior != entry:
                raise MetricsFormatError(
                    "conflicting retry for pending completion sequence"
                )
            if prior is None:
                pending = sorted(
                    [*pending, entry], key=lambda item: item["sequence"]
                )
                _write_pending_completions(execution_fd, pending)
            parsed = _publish_metrics(execution_fd, identity, candidate)
            result = _status_result(parsed, "appended", pending)
        invocation = parsed.invocations[sequence - 1]
        result.update({
            "sequence": sequence,
            "role": invocation["role"],
            "task": invocation["task"],
            "fix_wave": invocation["fix_wave"],
        })
        return result
    finally:
        if lock_fd is not None and logs_fd is not None:
            _release_lock(logs_fd, lock_fd)
        _close_fds(execution_fd, run_fd, workspace_fd, repo_fd)


def acknowledge_metrics_completion(
    base_path: Path,
    work_id: WorkId,
    expected_sequence: int,
) -> dict[str, Any]:
    """Clear one durable append handoff after authoritative state catches up."""
    if (
        isinstance(expected_sequence, bool)
        or not isinstance(expected_sequence, int)
        or expected_sequence <= 0
    ):
        raise MetricsInputError("expected_sequence must be a positive integer")
    repo_fd = workspace_fd = run_fd = execution_fd = None
    logs_fd = lock_fd = None
    try:
        repo_fd, workspace_fd, run_fd, execution_fd, _, _, _ = _open_metrics_run(
            Path(base_path), work_id
        )
        logs_fd, lock_fd = _open_lock_at(run_fd, "metrics.lock")
        parsed = parse_metrics(_read_text_at(execution_fd, "metrics.md") or "")
        progress = _read_text_at(execution_fd, "progress.md")
        assert progress is not None
        ledger = _validate_current_metrics(run_fd, work_id, parsed, progress)
        pending = _read_pending_completions(execution_fd)
        _validate_pending_completions(parsed, pending)
        entry = next(
            (item for item in pending if item["sequence"] == expected_sequence),
            None,
        )
        if entry is None:
            if expected_sequence <= len(parsed.invocations):
                return _status_result(parsed, "already_acknowledged", pending)
            raise MetricsFormatError("pending completion sequence is unknown")
        if expected_sequence > len(parsed.invocations):
            raise MetricsFormatError(
                "pending completion has not reached metrics.md; retry its exact record"
            )
        invocation = parsed.invocations[expected_sequence - 1]
        if invocation != entry["invocation"]:
            raise MetricsFormatError("pending completion does not match metrics.md")
        assert isinstance(ledger, ParsedExecutionLedger)
        role = invocation["role"]
        status = invocation["status"]
        task = invocation["task"]
        if (
            role in {"task_reviewer", "task_rereviewer"}
            and status == "approved"
            and task not in ledger.reviewed_complete
        ):
            raise MetricsFormatError(
                "approved task review progress transition is not durable"
            )
        if (
            role == "implementer"
            and ledger.effective_profile is ExecutionProfile.FAST
            and status == "complete"
        ):
            marker = ledger.marker_for(task)
            if marker is None or marker.kind not in {"implemented", "complete"}:
                raise MetricsFormatError(
                    "fast implementer progress transition is not durable"
                )
        if role in {"final_reviewer", "final_rereviewer"} and status == "approved":
            final_review = _read_text_at(
                execution_fd, "final-review.md", missing_ok=True
            )
            if (
                ledger.implemented
                or ledger.reviewed_complete != tuple(range(1, parsed.header["task_count"] + 1))
                or final_review is None
                or _current_verdict(final_review) != "approved"
            ):
                raise MetricsFormatError(
                    "approved final review progress transition is not durable"
                )
        remaining = [
            item for item in pending if item["sequence"] != expected_sequence
        ]
        _write_pending_completions(execution_fd, remaining)
        result = _status_result(parsed, "acknowledged", remaining)
        result.update({
            "sequence": expected_sequence,
            "role": role,
            "task": task,
            "fix_wave": invocation["fix_wave"],
        })
        return result
    finally:
        if lock_fd is not None and logs_fd is not None:
            _release_lock(logs_fd, lock_fd)
        _close_fds(execution_fd, run_fd, workspace_fd, repo_fd)


def _current_verdict(text: str) -> str | None:
    value = None
    semantic = strip_html_comments_outside_fences(text)
    for line, _, _ in unfenced_markdown_lines(semantic):
        stripped = line.strip()
        if stripped[:8].lower() == "verdict:":
            value = stripped[8:].strip().lower()
    return value


def _passing_final_verification(invocation: dict[str, Any]) -> bool:
    """Historical red runs are observations; the final command outcomes must pass."""
    records = invocation["verification_records"]
    if records == "unavailable" or not records or invocation["status"] != "approved":
        return False
    latest = {record["command"]: record for record in records}
    return (
        all(record["status"] == "passed" for record in latest.values())
        and any(record["scope"] == "full_suite" for record in latest.values())
    )


def _parse_finalization_ledger(
    progress: str, task_count: int
) -> ParsedExecutionLedger:
    """Parse the authoritative ledger after normalizing accepted checkbox style."""
    normalized: list[str] = []
    for line, _, _ in unfenced_markdown_lines(
        strip_nonsemantic_markdown(progress)
    ):
        plain = line.rstrip("\r\n")
        match = PLAN_TASK_CHECKBOX_RE.match(plain)
        if match:
            mark = "x" if match.group(1).lower() == "x" else " "
            normalized.append(f"- [{mark}] {match.group(2)}")
        else:
            normalized.append(plain)
    task_ids = tuple(
        f"PLAN-TASK-{number:03d}" for number in range(1, task_count + 1)
    )
    try:
        return parse_execution_ledger("\n".join(normalized) + "\n", task_ids)
    except ExecutionProfileError as exc:
        raise MetricsFormatError(f"execution progress ledger is invalid: {exc}") from exc


def _require_finalization_truth(
    base_path: Path,
    execution_fd: int,
    parsed: ParsedMetrics,
    progress: str,
    execution_ledger: Any,
) -> bytes:
    self_host_partial = _is_self_host_partial(parsed)
    legacy_partial = _is_legacy_partial(parsed)
    if not (self_host_partial or legacy_partial) and (
        not parsed.header["instrumentation_complete"]
        or parsed.header["bootstrap_gap"] != "none"
    ):
        raise MetricsFormatError("metrics instrumentation is incomplete")
    task_count = parsed.header["task_count"]
    if not self_host_partial:
        execution_ledger = _parse_finalization_ledger(progress, task_count)
        journal = execution_ledger.journal
        if journal and journal.base == execution_ledger.execution_base and not legacy_partial:
            fields = ("role", "task", "status", "fix_wave")
            expected_roles = [tuple(event[field] for field in fields) for event in journal.events]
            observed_roles = [tuple(invocation[field] for field in fields) for invocation in parsed.invocations]
            if journal.inflight or expected_roles != observed_roles:
                raise MetricsFormatError("metrics_incomplete: observations do not cover the authoritative role journal")
    semantic_progress = strip_html_comments_outside_fences(progress)
    progress_lines = [
        line for line, _, _ in unfenced_markdown_lines(semantic_progress)
    ]
    progress_rows = [
        (match.group(1).lower(), match.group(2))
        for line in progress_lines
        if (match := PLAN_TASK_CHECKBOX_RE.match(line))
    ]
    if any(not mark for mark, _task_id in progress_rows):
        raise MetricsFormatError("execution progress is incomplete")
    checked_ids = {
        task_id for mark, task_id in progress_rows if mark == "x"
    }
    expected_ids = {f"PLAN-TASK-{number:03d}" for number in range(1, task_count + 1)}
    if not expected_ids.issubset(checked_ids):
        raise MetricsFormatError("execution progress is incomplete")
    semantic_progress_text = "\n".join(progress_lines)
    for number in range(1, task_count + 1):
        if _marker_for(semantic_progress_text, number) is None:
            raise MetricsFormatError("execution progress lacks reviewed-complete task markers")
    final_review = _read_text_at(execution_fd, "final-review.md")
    assert final_review is not None
    if _current_verdict(final_review) != "approved":
        raise MetricsFormatError("final review is not Approved")
    if not self_host_partial:
        if legacy_partial:
            start_task = _legacy_metrics_start_task(parsed)
            _validate_strict_role_sequence(
                parsed.invocations,
                parsed.header["task_count"],
                start_task=(
                    parsed.header["task_count"]
                    if start_task is None
                    else start_task
                ),
                start_at_final=start_task is None,
                require_complete=True,
            )
        elif (
            execution_ledger is not None
            and execution_ledger.initial_profile is ExecutionProfile.FAST
            and execution_ledger.effective_profile is ExecutionProfile.STRICT
        ):
            _validate_escalated_fast_role_sequence(
                parsed.invocations,
                parsed.header["task_count"],
                require_complete=True,
            )
        else:
            validate_role_sequence(
                parsed.invocations,
                profile=parsed.header["profile"],
                task_count=parsed.header["task_count"],
                require_complete=True,
            )
        final_role = parsed.invocations[-1]
        if (
            final_role["role"] not in {"final_reviewer", "final_rereviewer"}
            or not _passing_final_verification(final_role)
        ):
            raise MetricsFormatError(
                "approved final role requires passed full-suite verification evidence"
            )
    for invocation in parsed.invocations:
        if self_host_partial and invocation["status"] == "blocked":
            raise MetricsFormatError("blocked role evidence cannot be finalized")
    _require_clean_code_worktree(base_path)
    if not self_host_partial:
        assert isinstance(execution_ledger, ParsedExecutionLedger)
        current_head = _execution_base(base_path)
        try:
            validate_ledger_commit_chain(
                execution_ledger,
                current_head=current_head,
                resolve_commit=lambda value: _resolve_commit_or_full(
                    base_path, value
                ),
                is_ancestor=lambda ancestor, descendant: _is_ancestor(
                    base_path, ancestor, descendant
                ),
            )
        except (ExecutionProfileError, PrerequisiteError) as exc:
            raise MetricsFormatError(
                f"execution ledger commit chain is invalid: {exc}"
            ) from exc
    base_match = re.search(
        r"^Execution BASE: ([0-9a-f]{40})$", semantic_progress_text, re.MULTILINE
    )
    if base_match is None:
        raise MetricsFormatError("progress must record a full Execution BASE")
    execution_base = base_match.group(1)
    resolved = subprocess.run(
        ["git", "-C", str(base_path), "rev-parse", "--verify", f"{execution_base}^{{commit}}"],
        capture_output=True,
        text=True,
        check=False,
    )
    if resolved.returncode != 0 or resolved.stdout.strip() != execution_base:
        raise MetricsFormatError("Execution BASE does not resolve exactly")
    diff = subprocess.run(
        [
            "git", "-C", str(base_path), "diff", "--name-status", "-z",
            execution_base, "HEAD", "--", ".", ":(exclude).req-to-plan",
        ],
        capture_output=True,
        check=False,
    )
    if diff.returncode != 0:
        raise MetricsFormatError("git diff --name-status failed")
    return diff.stdout


def _finalized_metrics_text(text: str, change_shape: str) -> str:
    lines = text.splitlines()
    shape_index = 1 + _HEADER_FIELDS.index("change_shape")
    finalized_index = 1 + _HEADER_FIELDS.index("metrics_finalized")
    lines[shape_index] = f"change_shape: {change_shape}"
    lines[finalized_index] = "metrics_finalized: true"
    return "\n".join(lines) + "\n"


def finalize_metrics(
    base_path: Path,
    work_id: WorkId,
    expected_invocation_count: int,
) -> dict[str, Any]:
    """Atomically derive change shape and close a complete metrics ledger."""
    if (
        isinstance(expected_invocation_count, bool)
        or not isinstance(expected_invocation_count, int)
        or expected_invocation_count < 0
    ):
        raise MetricsFormatError("expected_invocation_count must be non-negative")
    repo_fd = workspace_fd = run_fd = execution_fd = None
    logs_fd = lock_fd = None
    try:
        repo_fd, workspace_fd, run_fd, execution_fd, _, _, progress = _open_metrics_run(
            Path(base_path), work_id
        )
        logs_fd, lock_fd = _open_lock_at(run_fd, "metrics.lock")
        identity = _metrics_identity(execution_fd)
        text = _read_text_at(execution_fd, "metrics.md")
        assert text is not None
        parsed = parse_metrics(text)
        progress = _read_text_at(execution_fd, "progress.md")
        assert progress is not None
        execution_ledger = _validate_current_metrics(
            run_fd, work_id, parsed, progress
        )
        if expected_invocation_count != len(parsed.invocations):
            raise MetricsFormatError("expected invocation count is stale")
        pending = _read_pending_completions(execution_fd)
        _validate_pending_completions(parsed, pending)
        if parsed.header["metrics_finalized"]:
            if pending:
                raise MetricsFormatError("finalized metrics cannot retain pending completions")
            return _status_result(parsed, "already_finalized")
        name_status = _require_finalization_truth(
            Path(base_path), execution_fd, parsed, progress, execution_ledger
        )
        if pending:
            raise MetricsFormatError("pending completions must be acknowledged before metrics finalization")
        try:
            shape = classify_change_shape(name_status)
        except ValueError as exc:
            raise MetricsFormatError(str(exc)) from exc
        finalized_text = _finalized_metrics_text(text, shape)
        parsed = _publish_metrics(execution_fd, identity, finalized_text)
        return _status_result(parsed, "finalized")
    finally:
        if lock_fd is not None and logs_fd is not None:
            _release_lock(logs_fd, lock_fd)
        _close_fds(execution_fd, run_fd, workspace_fd, repo_fd)


_SAMPLE_RULES = (
    "path_safety",
    "identity_unique",
    "archived_strict",
    "instrumentation_complete",
    "plan_complete",
    "final_review_approved",
    "role_coverage",
    "measured_fields_complete",
    "metrics_totals_consistent",
)
_ROLE_ORDER = (
    "implementer",
    "task_reviewer",
    "fixer",
    "task_rereviewer",
    "final_reviewer",
    "final_fixer",
    "final_rereviewer",
)


def _sample_failure(
    sample_dir: str,
    work_id: str,
    rule: str,
    message: str,
) -> dict[str, str]:
    return {"sample_dir": sample_dir, "work_id": work_id, "rule": rule, "message": message}


def _sample_error_result(details: list[dict[str, str]]) -> dict[str, Any]:
    return {
        "status": "error",
        "message": "BLOCKED: representative_metrics_missing",
        "exit_code": 3,
        "details": details,
    }


def _six(value: Decimal) -> str:
    return format(value.quantize(Decimal("0.000001")), "f")


def _fix_waves(text: str) -> set[int]:
    semantic = strip_nonsemantic_markdown(text)
    marker = re.compile(r"Fix Wave ([1-9][0-9]*)")
    return {
        int(match.group(1))
        for line, _, _ in unfenced_markdown_lines(semantic)
        if (match := marker.fullmatch(line.rstrip("\r\n")))
    }


def _final_fix_waves(text: str) -> set[int]:
    semantic = strip_nonsemantic_markdown(text)
    marker = re.compile(r"^[ \t]*Final Fix Wave:[ \t]*([1-9][0-9]*)[ \t]*$")
    return {
        int(match.group(1))
        for line, _, _ in unfenced_markdown_lines(semantic)
        if (match := marker.fullmatch(line.rstrip("\r\n")))
    }


def _sample_role_evidence(
    execution_fd: int,
    task_count: int,
    final_review: str,
) -> dict[str, set[tuple[int, int]] | set[int]]:
    task_fixers: set[tuple[int, int]] = set()
    task_rereviewers: set[tuple[int, int]] = set()
    for task in range(1, task_count + 1):
        report = _read_text_at(execution_fd, f"task-{task}-report.md", missing_ok=True)
        review = _read_text_at(execution_fd, f"task-{task}-review.md", missing_ok=True)
        if report is not None:
            task_fixers.update((task, wave) for wave in _fix_waves(report))
        if review is not None:
            task_rereviewers.update((task, wave) for wave in _fix_waves(review))
    final_waves = _final_fix_waves(final_review)
    return {
        "fixer": task_fixers,
        "task_rereviewer": task_rereviewers,
        "final_fixer": set(final_waves),
        "final_rereviewer": set(final_waves),
    }


def _safe_sample_inputs(
    sample_dir: Path,
) -> tuple[
    str,
    WorkId,
    int,
    int,
    RunRecord,
    str,
    ParsedMetrics,
    str,
    str,
    dict[str, set[tuple[int, int]] | set[int]],
]:
    raw = os.fspath(sample_dir)
    if not sample_dir.is_absolute() or any(part in {"..", "."} for part in sample_dir.parts):
        raise MetricsFormatError("sample directory must be an absolute canonical path")
    canonical = Path(os.path.abspath(raw))
    try:
        before = os.lstat(canonical)
    except OSError as exc:
        raise MetricsFormatError("sample directory is missing or unreadable") from exc
    if not stat.S_ISDIR(before.st_mode):
        raise MetricsFormatError("sample directory is not a regular directory")
    try:
        work_id = WorkId(canonical.name)
    except ValueError as exc:
        raise MetricsFormatError("sample basename is not a WorkId") from exc
    sample_fd = _open_absolute_dir(canonical)
    execution_fd: int | None = None
    try:
        opened = os.fstat(sample_fd)
        if (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino):
            raise MetricsFormatError("sample directory identity changed")
        record = _parse_record_at(sample_fd, work_id)
        plan = _plan_at(sample_fd)
        execution_fd = _open_dir_at(sample_fd, "execution")
        progress = _read_text_at(execution_fd, "progress.md")
        metrics_text = _read_text_at(execution_fd, "metrics.md")
        final_review = _read_text_at(execution_fd, "final-review.md")
        assert progress is not None and metrics_text is not None and final_review is not None
        metrics = parse_metrics(metrics_text)
        evidence = _sample_role_evidence(execution_fd, metrics.header["task_count"], final_review)
        return (
            str(canonical), work_id, sample_fd, execution_fd, record, plan, metrics,
            progress, final_review, evidence,
        )
    except Exception:
        if execution_fd is not None:
            os.close(execution_fd)
        os.close(sample_fd)
        raise


def _summarize_sample(
    canonical: str,
    work_id: WorkId,
    record: RunRecord,
    plan: str,
    parsed: ParsedMetrics,
    progress: str,
    final_review: str,
    role_evidence: dict[str, set[tuple[int, int]] | set[int]],
) -> tuple[dict[str, Any] | None, list[dict[str, str]]]:
    failures: list[dict[str, str]] = []
    header = parsed.header

    if header["work_id"] != str(work_id):
        failures.append(_sample_failure(
            canonical,
            str(work_id),
            "identity_unique",
            "metrics work_id does not match the pinned sample identity",
        ))
    if record.status != RunStatus.ARCHIVED or header["profile"] != "strict" or str(work_id) == SELF_HOSTED_WORK_ID:
        failures.append(_sample_failure(canonical, str(work_id), "archived_strict", "sample must be an archived strict non-self-hosted run"))
    if (
        header["instrumentation_schema"] != INSTRUMENTATION_SCHEMA
        or not header["instrumentation_complete"]
        or header["bootstrap_gap"] != "none"
        or not header["metrics_finalized"]
        or header["change_shape"] == "unavailable"
        or not header["r2p_version"]
    ):
        failures.append(_sample_failure(canonical, str(work_id), "instrumentation_complete", "metrics instrumentation is incomplete, unsupported, or unfinalized"))

    anchors = plan_task_anchors(strip_nonsemantic_markdown(plan))
    task_ids = [item[0] for item in anchors]
    rows = [
        (match.group(1).lower(), match.group(2))
        for line, _, _ in unfenced_markdown_lines(
            strip_nonsemantic_markdown(progress)
        )
        if (match := PLAN_TASK_CHECKBOX_RE.match(line))
    ]
    plan_ok = (
        task_ids == [f"PLAN-TASK-{n:03d}" for n in range(1, len(anchors) + 1)]
        and len(anchors) == header["task_count"]
        and [task_id for _, task_id in rows] == task_ids
        and all(mark == "x" for mark, _ in rows)
    )
    if not plan_ok:
        failures.append(_sample_failure(canonical, str(work_id), "plan_complete", "PLAN task count or progress completion is inconsistent"))

    if _current_verdict(final_review) != "approved":
        failures.append(_sample_failure(canonical, str(work_id), "final_review_approved", "last final-review verdict is not Approved"))

    role_sequence_error: str | None = None
    try:
        validate_role_sequence(
            parsed.invocations,
            profile="strict",
            task_count=header["task_count"],
            require_complete=True,
        )
    except MetricsFormatError as exc:
        role_sequence_error = str(exc)

    role_counts = {role: 0 for role in _ROLE_ORDER}
    task_roles: dict[tuple[str, int], int] = {}
    fixer_waves: set[tuple[int, int]] = set()
    rereviewer_waves: set[tuple[int, int]] = set()
    final_fixer_waves: set[int] = set()
    final_rereviewer_waves: set[int] = set()
    task_review_statuses: dict[int, list[str]] = {}
    final_review_statuses: list[str] = []
    final_role_full_suite: list[bool] = []
    completed_statuses_ok = True
    measured_ok = True
    totals_ok = True
    role_elapsed = Decimal()
    verification_elapsed = Decimal()
    report_bytes = 0
    full_suite_count = 0
    full_suite_duration = Decimal()
    contexts = {
        "direct_acs": {"invocation_count": 0, "context_bytes_kind": "declared_payload_bytes", "context_bytes": 0},
        "semantic_view": {"invocation_count": 0, "context_bytes_kind": "semantic_payload_bytes", "context_bytes": 0},
    }
    tokens_available = True
    input_tokens = output_tokens = total_tokens = 0
    for invocation in parsed.invocations:
        role = invocation["role"]
        role_counts[role] += 1
        if isinstance(invocation["task"], int):
            if invocation["status"] != "blocked":
                task_roles[(role, invocation["task"])] = task_roles.get((role, invocation["task"]), 0) + 1
            if role in {"task_reviewer", "task_rereviewer"}:
                task_review_statuses.setdefault(invocation["task"], []).append(invocation["status"])
        elif role in {"final_reviewer", "final_rereviewer"}:
            final_review_statuses.append(invocation["status"])
        if role == "fixer":
            fixer_waves.add((invocation["task"], invocation["fix_wave"]))
        elif role == "task_rereviewer":
            rereviewer_waves.add((invocation["task"], invocation["fix_wave"]))
        elif role == "final_fixer":
            final_fixer_waves.add(invocation["fix_wave"])
        elif role == "final_rereviewer":
            final_rereviewer_waves.add(invocation["fix_wave"])
        if invocation["elapsed_seconds"] == "unavailable":
            measured_ok = False
        else:
            role_elapsed += Decimal(invocation["elapsed_seconds"])
        report_bytes += invocation["report_bytes"]
        records = invocation["verification_records"]
        if records == "unavailable" or invocation["verification_total_seconds"] == "unavailable":
            measured_ok = False
            if role in {"final_reviewer", "final_rereviewer"}:
                final_role_full_suite.append(False)
            continue
        record_total = sum((Decimal(item["elapsed_seconds"]) for item in records), Decimal())
        verification_elapsed += record_total
        if record_total != Decimal(invocation["verification_total_seconds"]):
            totals_ok = False
        for item in records:
            if item["scope"] == "full_suite":
                full_suite_count += 1
                full_suite_duration += Decimal(item["elapsed_seconds"])
        if role in {"final_reviewer", "final_rereviewer"}:
            final_role_full_suite.append(_passing_final_verification(invocation))
        context = contexts[invocation["context_mode"]]
        context["invocation_count"] += 1
        context["context_bytes"] += invocation["context_bytes"]
        if invocation["total_tokens"] == "unavailable":
            tokens_available = False
        elif tokens_available:
            input_tokens += int(invocation["input_tokens"])
            output_tokens += int(invocation["output_tokens"])
            total_tokens += int(invocation["total_tokens"])

    coverage_ok = (
        role_counts["implementer"] >= header["task_count"]
        and role_counts["task_reviewer"] >= header["task_count"]
        and role_counts["final_reviewer"] >= 1
        and all(task_roles.get(("implementer", task)) == 1 for task in range(1, header["task_count"] + 1))
        and all(task_roles.get(("task_reviewer", task)) == 1 for task in range(1, header["task_count"] + 1))
        and fixer_waves == rereviewer_waves
        and final_fixer_waves == final_rereviewer_waves
    )
    completed_statuses_ok = (
        completed_statuses_ok
        and all(
            task_review_statuses.get(task)
            and task_review_statuses[task][-1] == "approved"
            for task in range(1, header["task_count"] + 1)
        )
        and bool(final_review_statuses)
        and final_review_statuses[-1] == "approved"
    )
    evidence_ok = (
        role_evidence["fixer"] == fixer_waves
        and role_evidence["task_rereviewer"] == rereviewer_waves
        and role_evidence["final_fixer"] == final_fixer_waves
        and role_evidence["final_rereviewer"] == final_rereviewer_waves
    )
    if not completed_statuses_ok:
        failures.append(_sample_failure(
            canonical,
            str(work_id),
            "role_coverage",
            "required role invocation did not complete successfully",
        ))
    elif role_sequence_error is not None:
        failures.append(_sample_failure(
            canonical,
            str(work_id),
            "role_coverage",
            f"role sequence is invalid: {role_sequence_error}",
        ))
    elif not coverage_ok:
        failures.append(_sample_failure(canonical, str(work_id), "role_coverage", "required role coverage or fix-wave pairing is incomplete"))
    elif not evidence_ok:
        failures.append(_sample_failure(
            canonical,
            str(work_id),
            "role_coverage",
            "persistent role/fix-wave evidence is missing matching metrics blocks",
        ))
    if not final_role_full_suite or not final_role_full_suite[-1]:
        failures.append(_sample_failure(
            canonical,
            str(work_id),
            "role_coverage",
            "approved terminal final reviewer requires passed full-suite evidence",
        ))
    if not measured_ok:
        failures.append(_sample_failure(canonical, str(work_id), "measured_fields_complete", "required measured timing or verification fields are unavailable"))
    if not totals_ok:
        failures.append(_sample_failure(canonical, str(work_id), "metrics_totals_consistent", "verification totals are inconsistent"))
    if failures:
        return None, failures

    token_totals: dict[str, Any]
    if tokens_available:
        token_totals = {
            "status": "available",
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": total_tokens,
        }
    else:
        token_totals = {
            "status": "unavailable",
            "input_tokens": "unavailable",
            "output_tokens": "unavailable",
            "total_tokens": "unavailable",
        }
    rules = [{"rule": rule, "status": "passed", "details": []} for rule in _SAMPLE_RULES]
    return {
        "path": canonical,
        "work_id": str(work_id),
        "r2p_version": header["r2p_version"],
        "instrumentation_schema": header["instrumentation_schema"],
        "profile": "strict",
        "task_count": header["task_count"],
        "change_shape": header["change_shape"],
        "instrumentation_complete": True,
        "bootstrap_gap": "none",
        "metrics_finalized": True,
        "plan_complete": True,
        "final_verdict": "Approved",
        "invocation_count": len(parsed.invocations),
        "role_counts": role_counts,
        "role_elapsed_total_seconds": _six(role_elapsed),
        "verification_total_seconds": _six(verification_elapsed),
        "report_bytes_total": report_bytes,
        "full_suite": {"count": full_suite_count, "duration_seconds": _six(full_suite_duration)},
        "context_totals": contexts,
        "token_totals": token_totals,
        "rules": rules,
    }, []


def validate_representative_samples(sample_dirs: tuple[Path, Path, Path]) -> dict[str, Any]:
    """Validate exactly three pinned archived strict samples without writes."""
    observed = len(sample_dirs) if isinstance(sample_dirs, tuple) else -1
    if not isinstance(sample_dirs, tuple) or observed != 3:
        raise RepresentativeSamplesError(_sample_error_result([
            _sample_failure("invocation", "unavailable", "argument_count", f"expected 3 sample dirs, observed {observed}")
        ]))

    summaries: list[dict[str, Any]] = []
    failures: list[dict[str, str]] = []
    canonical_paths: set[str] = set()
    work_ids: set[str] = set()
    for raw_path in sample_dirs:
        source = os.fspath(raw_path)
        sample_fd = execution_fd = None
        try:
            (
                canonical, work_id, sample_fd, execution_fd, record, plan, parsed,
                progress, final_review, role_evidence,
            ) = _safe_sample_inputs(Path(raw_path))
        except Exception as exc:
            failures.append(_sample_failure(source, "unavailable", "path_safety", str(exc)))
            continue
        try:
            if canonical in canonical_paths:
                failures.append(_sample_failure(
                    source,
                    str(work_id),
                    "identity_unique",
                    "canonical sample path is duplicated",
                ))
                continue
            canonical_paths.add(canonical)
            if str(work_id) in work_ids:
                failures.append(_sample_failure(
                    source,
                    str(work_id),
                    "identity_unique",
                    "sample work ID is duplicated",
                ))
                continue
            work_ids.add(str(work_id))
            summary, sample_failures = _summarize_sample(
                canonical, work_id, record, plan, parsed, progress, final_review, role_evidence
            )
            failures.extend(sample_failures)
            if summary is not None:
                summaries.append(summary)
        finally:
            _close_fds(execution_fd, sample_fd)

    if failures:
        raise RepresentativeSamplesError(_sample_error_result(failures))
    task_counts = sorted({item["task_count"] for item in summaries})
    change_shapes = sorted({item["change_shape"] for item in summaries})
    task_count_diverse = len(task_counts) >= 2
    change_shape_diverse = len(change_shapes) >= 2
    if not (task_count_diverse or change_shape_diverse):
        raise RepresentativeSamplesError(_sample_error_result([
            _sample_failure("aggregate", "unavailable", "aggregate_representative", "samples lack task-count and change-shape diversity")
        ]))
    return {
        "status": "ok",
        "message": "representative_metrics_accepted",
        "samples": summaries,
        "aggregate": {
            "sample_count": 3,
            "work_ids": [item["work_id"] for item in summaries],
            "task_counts": task_counts,
            "change_shapes": change_shapes,
            "task_count_diverse": task_count_diverse,
            "change_shape_diverse": change_shape_diverse,
            "representative": True,
        },
    }

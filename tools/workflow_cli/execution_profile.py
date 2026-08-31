"""Pure strict/fast execution-profile and ledger semantics.

This module deliberately has no CLI, filesystem mutation, or agent-surface
dependencies.  Callers obtain a parsed ledger here, validate Git ancestry at
their boundary, and atomically persist a complete migrated ledger when a fast
run receives final approval.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from enum import Enum
import json
import os
from pathlib import Path
import re
from collections.abc import Callable
from typing import Any

from tools.workflow_cli.atomic import UnsafeRegularFileError, read_regular_text
from tools.workflow_cli.markdown import (
    plan_task_anchors,
    strip_html_comments_outside_fences,
    strip_nonsemantic_markdown,
    unfenced_markdown_lines,
)
from tools.workflow_cli.models import TierBase, TierEstimate, WorkId


class ExecutionProfile(Enum):
    STRICT = "strict"
    FAST = "fast"


class ExecutionProfileError(ValueError):
    """Raised when a profile ledger or accepted evidence is not canonical."""


@dataclass(frozen=True)
class TaskMarker:
    number: int
    kind: str
    base: str
    head: str
    review_kind: str | None = None


@dataclass(frozen=True)
class ParsedExecutionLedger:
    initial_profile: ExecutionProfile
    effective_profile: ExecutionProfile
    execution_base: str
    escalation_reason: str | None
    markers: tuple[TaskMarker, ...]
    reviewed_complete: tuple[int, ...]
    implemented: tuple[int, ...]
    untouched: tuple[int, ...]

    def marker_for(self, task: int) -> TaskMarker | None:
        return next((marker for marker in self.markers if marker.number == task), None)

    def first_actionable_task(self) -> int | None:
        """Return the next controller action without inferring Git history."""
        if self.effective_profile is ExecutionProfile.STRICT and self.implemented:
            return self.implemented[0]
        if self.untouched:
            return self.untouched[0]
        return None


_FULL_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_SHORT_SHA_RE = r"[0-9a-f]{7}"
_PROFILE_RE = re.compile(r"^Execution Profile: (strict|fast)$")
_ESCALATION_RE = re.compile(r"^Profile Escalation: fast -> strict \(reason: ([^\r\n]+)\)$")
_PROFILE_LIKE_RE = re.compile(r"^\s*Execution\s+Profile[A-Za-z0-9_-]*\s*:")
_ESCALATION_LIKE_RE = re.compile(r"^\s*Profile\s+Escalation[A-Za-z0-9_-]*\s*:")
_IMPLEMENTED_RE = re.compile(
    rf"^Task ([1-9][0-9]*): implemented \(commits ({_SHORT_SHA_RE})\.\.({_SHORT_SHA_RE}), verification recorded\)$"
)
_COMPLETE_RE = re.compile(
    rf"^Task ([1-9][0-9]*): complete \(commits ({_SHORT_SHA_RE})\.\.({_SHORT_SHA_RE}), (review|final review) clean\)$"
)
_MARKER_LIKE_RE = re.compile(
    r"^\s*Task\s*[0-9]+\s*:?\s*(?:implemented|complete).*$"
)
_CHECKBOX_RE = re.compile(r"^- \[([ x])\] (PLAN-TASK-[0-9]{3})\b")
_BASE_RE = re.compile(r"^Execution BASE: ([0-9a-f]{40})$")
_SAMPLE_ROLES = (
    "implementer",
    "task_reviewer",
    "fixer",
    "task_rereviewer",
    "final_reviewer",
    "final_fixer",
    "final_rereviewer",
)
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
_SAMPLE_FIELDS = (
    "path", "work_id", "r2p_version", "instrumentation_schema", "profile",
    "task_count", "change_shape", "instrumentation_complete", "bootstrap_gap",
    "metrics_finalized", "plan_complete", "final_verdict", "invocation_count",
    "role_counts", "role_elapsed_total_seconds", "verification_total_seconds",
    "report_bytes_total", "full_suite", "context_totals", "token_totals", "rules",
)
_AGGREGATE_FIELDS = (
    "sample_count", "work_ids", "task_counts", "change_shapes",
    "task_count_diverse", "change_shape_diverse", "representative",
)
_EVIDENCE_FIELDS = ("status", "message", "samples", "aggregate")
_FULL_SUITE_FIELDS = ("count", "duration_seconds")
_CONTEXT_FIELDS = ("invocation_count", "context_bytes_kind", "context_bytes")
_TOKEN_FIELDS = ("status", "input_tokens", "output_tokens", "total_tokens")
_RULE_FIELDS = ("rule", "status", "details")
_CHANGE_SHAPES = frozenset((
    "migration", "single_module_code", "cross_module_code", "docs_only",
    "config_only", "test_only", "mixed",
))
_DECIMAL_6_RE = re.compile(r"^(?:0|[1-9][0-9]*)\.[0-9]{6}$")


def _expected_numbers(plan_task_ids: tuple[str, ...]) -> tuple[int, ...]:
    expected = tuple(range(1, len(plan_task_ids) + 1))
    canonical = tuple(f"PLAN-TASK-{number:03d}" for number in expected)
    if not expected or plan_task_ids != canonical:
        raise ExecutionProfileError("PLAN task IDs must be contiguous canonical anchors")
    return expected


def _semantic_lines(text: str) -> list[str]:
    if not isinstance(text, str):
        raise ExecutionProfileError("execution ledger must be text")
    semantic = strip_nonsemantic_markdown(text)
    return [line.rstrip("\r\n") for line, _, _ in unfenced_markdown_lines(semantic)]


def parse_execution_ledger(
    text: str, plan_task_ids: tuple[str, ...]
) -> ParsedExecutionLedger:
    """Fail closed while parsing immutable profile and task-marker grammar."""
    expected_numbers = _expected_numbers(plan_task_ids)
    lines = _semantic_lines(text)

    profiles = [match.group(1) for line in lines if (match := _PROFILE_RE.match(line))]
    profile_like = [line for line in lines if _PROFILE_LIKE_RE.match(line)]
    if len(profiles) != len(profile_like) or len(profiles) > 1:
        raise ExecutionProfileError("initial execution profile is malformed or duplicated")
    initial = ExecutionProfile(profiles[0]) if profiles else ExecutionProfile.STRICT

    escalations = [match.group(1) for line in lines if (match := _ESCALATION_RE.match(line))]
    escalation_like = [line for line in lines if _ESCALATION_LIKE_RE.match(line)]
    if len(escalations) != len(escalation_like) or len(escalations) > 1:
        raise ExecutionProfileError("profile escalation is malformed or duplicated")
    if escalations and (initial is not ExecutionProfile.FAST or not escalations[0].strip()):
        raise ExecutionProfileError("only fast may escalate once to strict")
    effective = ExecutionProfile.STRICT if escalations else initial

    bases = [match.group(1) for line in lines if (match := _BASE_RE.match(line))]
    base_like = [line for line in lines if line.startswith("Execution BASE:")]
    if len(bases) != 1 or len(base_like) != 1 or not _FULL_SHA_RE.fullmatch(bases[0]):
        raise ExecutionProfileError("execution ledger must contain one full Execution BASE")

    checkbox_rows = [match.groups() for line in lines if (match := _CHECKBOX_RE.match(line))]
    if tuple(task_id for _, task_id in checkbox_rows) != plan_task_ids:
        raise ExecutionProfileError("execution ledger task rows do not match PLAN")

    markers: list[TaskMarker] = []
    marker_like_count = 0
    for line in lines:
        if _MARKER_LIKE_RE.match(line):
            marker_like_count += 1
            implemented = _IMPLEMENTED_RE.match(line)
            complete = _COMPLETE_RE.match(line)
            if implemented:
                number, base, head = implemented.groups()
                markers.append(TaskMarker(int(number), "implemented", base, head))
            elif complete:
                number, base, head, review_kind = complete.groups()
                markers.append(
                    TaskMarker(int(number), "complete", base, head, review_kind)
                )
            else:
                raise ExecutionProfileError("task marker is malformed")
    if marker_like_count != len(markers):
        raise ExecutionProfileError("task marker is malformed")
    if len({marker.number for marker in markers}) != len(markers):
        raise ExecutionProfileError("task has duplicate markers")
    if any(marker.number not in expected_numbers for marker in markers):
        raise ExecutionProfileError("task marker is outside PLAN bounds")
    if initial is ExecutionProfile.STRICT and any(marker.kind == "implemented" for marker in markers):
        raise ExecutionProfileError("strict ledger cannot contain implemented marker")
    if not profiles and (escalations or any(marker.kind == "implemented" for marker in markers)):
        raise ExecutionProfileError("legacy ledger cannot contain fast-only state")

    by_task = {marker.number: marker for marker in markers}
    states: list[str] = []
    for number, (checked, _task_id) in zip(expected_numbers, checkbox_rows):
        marker = by_task.get(number)
        if checked == "x":
            if marker is None or marker.kind != "complete":
                raise ExecutionProfileError("checked task must have one complete marker")
            states.append("complete")
        elif marker is None:
            states.append("untouched")
        elif marker.kind == "implemented":
            states.append("implemented")
        else:
            raise ExecutionProfileError("unchecked task cannot have complete marker")

    expected_states = sorted(states, key={"complete": 0, "implemented": 1, "untouched": 2}.get)
    if states != expected_states:
        raise ExecutionProfileError("task states must be complete, implemented, then untouched")
    if effective is ExecutionProfile.STRICT and initial is ExecutionProfile.STRICT and "implemented" in states:
        raise ExecutionProfileError("strict ledger cannot retain implemented state")
    if (
        initial is ExecutionProfile.FAST
        and effective is ExecutionProfile.FAST
        and "complete" in states
        and any(state != "complete" for state in states)
    ):
        raise ExecutionProfileError(
            "unelevated fast ledger cannot retain a reviewed-complete prefix"
        )
    if (
        initial is ExecutionProfile.FAST
        and effective is ExecutionProfile.FAST
        and states
        and all(state == "complete" for state in states)
        and any(marker.review_kind != "final review" for marker in markers)
    ):
        raise ExecutionProfileError(
            "unelevated fast complete markers must use final review clean"
        )

    return ParsedExecutionLedger(
        initial_profile=initial,
        effective_profile=effective,
        execution_base=bases[0],
        escalation_reason=escalations[0] if escalations else None,
        markers=tuple(sorted(markers, key=lambda marker: marker.number)),
        reviewed_complete=tuple(number for number, state in zip(expected_numbers, states) if state == "complete"),
        implemented=tuple(number for number, state in zip(expected_numbers, states) if state == "implemented"),
        untouched=tuple(number for number, state in zip(expected_numbers, states) if state == "untouched"),
    )


def check_prerequisite_v2(progress: str, plan: str, task: int) -> dict[str, Any]:
    """Validate profile-aware pre-dispatch ordering without mutating a run."""
    ids = tuple(task_id for task_id, _ in plan_task_anchors(strip_nonsemantic_markdown(plan)))
    parsed = parse_execution_ledger(progress, ids)
    if task not in range(1, len(ids) + 1):
        raise ExecutionProfileError("task is outside PLAN bounds")
    actionable = parsed.first_actionable_task()
    if actionable != task:
        raise ExecutionProfileError("task is not the first actionable task")
    prerequisite = "none" if task == 1 else f"PLAN-TASK-{task - 1:03d}"
    return {
        "task": task,
        "semantics_version": 2,
        "effective_profile": parsed.effective_profile.value,
        "prerequisite": prerequisite,
        "satisfied": True,
        "task_count": len(ids),
        "execution_base": parsed.execution_base,
    }


def fast_structure_eligible(tier_locked: TierEstimate | None) -> bool:
    """Fast may only be considered for a locked LIGHT tier without modifiers."""
    return (
        isinstance(tier_locked, TierEstimate)
        and tier_locked.base is TierBase.LIGHT
        and not tier_locked.modifiers
    )


def validate_ledger_commit_chain(
    parsed: ParsedExecutionLedger,
    *,
    current_head: str,
    resolve_commit: Callable[[str], str],
    is_ancestor: Callable[[str, str], bool],
) -> None:
    """Check the BASE-to-HEAD chain with caller-supplied Git primitives.

    Keeping Git calls outside this helper preserves a deterministic profile core
    while ensuring callers never substitute ``HEAD~1`` for a marker boundary.
    """
    if not _FULL_SHA_RE.fullmatch(current_head):
        raise ExecutionProfileError("current HEAD must be a full SHA")
    try:
        previous_head = resolve_commit(parsed.execution_base)
        if not _FULL_SHA_RE.fullmatch(previous_head):
            raise ExecutionProfileError("Execution BASE did not resolve to a full SHA")
        for marker in parsed.markers:
            marker_base = resolve_commit(marker.base)
            marker_head = resolve_commit(marker.head)
            if marker_base != previous_head:
                raise ExecutionProfileError("task marker BASE chain is discontinuous")
            if not _FULL_SHA_RE.fullmatch(marker_head) or not is_ancestor(previous_head, marker_head):
                raise ExecutionProfileError("task marker head is not an ordered descendant")
            previous_head = marker_head
    except ExecutionProfileError:
        raise
    except Exception as exc:  # Git adapter errors must fail closed at the pure boundary.
        raise ExecutionProfileError("ledger commit abbreviation is unresolved") from exc
    if not is_ancestor(previous_head, current_head):
        raise ExecutionProfileError("current HEAD diverges from the ledger chain")


def _is_nonnegative_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _has_fields(value: Any, fields: tuple[str, ...]) -> bool:
    return isinstance(value, dict) and all(field in value for field in fields)


def _has_exact_fields(value: Any, fields: tuple[str, ...]) -> bool:
    return isinstance(value, dict) and set(value) == set(fields)


def _canonical_decimal(value: Any) -> Decimal | None:
    if not isinstance(value, str) or _DECIMAL_6_RE.fullmatch(value) is None:
        return None
    try:
        return Decimal(value)
    except InvalidOperation:
        return None


def _canonical_sample_identity(path: Any, work_id: Any) -> bool:
    if not isinstance(path, str) or not isinstance(work_id, str):
        return False
    try:
        WorkId(work_id)
    except ValueError:
        return False
    return (
        os.path.isabs(path)
        and str(Path(os.path.abspath(path))) == path
        and Path(path).name == work_id
    )


def _canonical_sample(sample: Any) -> bool:
    if not _has_exact_fields(sample, _SAMPLE_FIELDS):
        return False
    assert isinstance(sample, dict)
    if not all(isinstance(sample[field], str) and sample[field] for field in (
        "path", "work_id", "r2p_version", "change_shape",
        "role_elapsed_total_seconds", "verification_total_seconds",
    )):
        return False
    if not _canonical_sample_identity(sample["path"], sample["work_id"]):
        return False
    instrumentation_schema = sample["instrumentation_schema"]
    if (
        not isinstance(instrumentation_schema, int)
        or isinstance(instrumentation_schema, bool)
        or instrumentation_schema != 1
        or not all(_is_nonnegative_int(sample[field]) for field in (
            "task_count", "invocation_count", "report_bytes_total",
        ))
        or sample["task_count"] < 1
        or sample["invocation_count"] < 1
        or sample["change_shape"] not in _CHANGE_SHAPES
    ):
        return False
    if (
        sample["profile"] != "strict"
        or sample["instrumentation_complete"] is not True
        or sample["bootstrap_gap"] != "none"
        or sample["metrics_finalized"] is not True
        or sample["plan_complete"] is not True
        or sample["final_verdict"] != "Approved"
    ):
        return False

    role_counts = sample["role_counts"]
    if not _has_exact_fields(role_counts, _SAMPLE_ROLES) or not all(
        _is_nonnegative_int(role_counts[role]) for role in _SAMPLE_ROLES
    ):
        return False
    if (
        role_counts["implementer"] != sample["task_count"]
        or role_counts["task_reviewer"] != sample["task_count"]
        or role_counts["final_reviewer"] < 1
        or role_counts["fixer"] != role_counts["task_rereviewer"]
        or role_counts["final_fixer"] != role_counts["final_rereviewer"]
        or sum(role_counts.values()) != sample["invocation_count"]
    ):
        return False
    full_suite = sample["full_suite"]
    full_suite_duration = _canonical_decimal(
        full_suite.get("duration_seconds") if isinstance(full_suite, dict) else None
    )
    verification_total = _canonical_decimal(sample["verification_total_seconds"])
    if not (
        _has_exact_fields(full_suite, _FULL_SUITE_FIELDS)
        and isinstance(full_suite["count"], int)
        and not isinstance(full_suite["count"], bool)
        and full_suite["count"] > 0
        and full_suite_duration is not None
        and verification_total is not None
        and full_suite_duration <= verification_total
        and _canonical_decimal(sample["role_elapsed_total_seconds"]) is not None
    ):
        return False
    contexts = sample["context_totals"]
    if not _has_exact_fields(contexts, ("direct_acs", "semantic_view")):
        return False
    context_invocations = 0
    for mode, bytes_kind in (
        ("direct_acs", "declared_payload_bytes"),
        ("semantic_view", "semantic_payload_bytes"),
    ):
        context = contexts[mode]
        if not _has_exact_fields(context, _CONTEXT_FIELDS):
            return False
        if (
            not _is_nonnegative_int(context["invocation_count"])
            or context["context_bytes_kind"] != bytes_kind
            or not _is_nonnegative_int(context["context_bytes"])
            or (context["invocation_count"] == 0 and context["context_bytes"] != 0)
        ):
            return False
        context_invocations += context["invocation_count"]
    if context_invocations != sample["invocation_count"]:
        return False
    tokens = sample["token_totals"]
    if not _has_exact_fields(tokens, _TOKEN_FIELDS):
        return False
    if tokens["status"] == "available":
        if not all(_is_nonnegative_int(tokens[field]) for field in (
            "input_tokens", "output_tokens", "total_tokens",
        )) or tokens["total_tokens"] != tokens["input_tokens"] + tokens["output_tokens"]:
            return False
    elif tokens["status"] == "unavailable":
        if any(tokens[field] != "unavailable" for field in (
            "input_tokens", "output_tokens", "total_tokens",
        )):
            return False
    else:
        return False
    rules = sample["rules"]
    return (
        isinstance(rules, list)
        and len(rules) == len(_SAMPLE_RULES)
        and [item.get("rule") for item in rules if isinstance(item, dict)] == list(_SAMPLE_RULES)
        and all(
            _has_exact_fields(item, _RULE_FIELDS)
            and item.get("status") == "passed"
            and item.get("details") == []
            for item in rules
        )
    )


def _canonical_aggregate(aggregate: Any, samples: list[dict[str, Any]]) -> bool:
    if not _has_exact_fields(aggregate, _AGGREGATE_FIELDS):
        return False
    assert isinstance(aggregate, dict)
    task_counts = sorted({sample["task_count"] for sample in samples})
    change_shapes = sorted({sample["change_shape"] for sample in samples})
    task_count_diverse = len(task_counts) >= 2
    change_shape_diverse = len(change_shapes) >= 2
    return (
        _is_nonnegative_int(aggregate["sample_count"])
        and aggregate["sample_count"] == 3
        and isinstance(aggregate["task_counts"], list)
        and all(_is_nonnegative_int(value) for value in aggregate["task_counts"])
        and aggregate["work_ids"] == [sample["work_id"] for sample in samples]
        and aggregate["task_counts"] == task_counts
        and aggregate["change_shapes"] == change_shapes
        and aggregate["task_count_diverse"] is task_count_diverse
        and aggregate["change_shape_diverse"] is change_shape_diverse
        and aggregate["representative"] is True
        and (task_count_diverse or change_shape_diverse)
    )


def consume_accepted_sample_evidence(path: str | Path) -> dict[str, Any]:
    """Read only a complete saved validator result; never discover sample directories."""
    try:
        text = read_regular_text(Path(path))
        if text is None:
            raise UnsafeRegularFileError("evidence is missing")
        payload = json.loads(text)
    except (OSError, UnsafeRegularFileError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ExecutionProfileError("representative metrics evidence is unreadable") from exc
    if (
        not _has_exact_fields(payload, _EVIDENCE_FIELDS)
        or payload["status"] != "ok"
        or payload["message"] != "representative_metrics_accepted"
    ):
        raise ExecutionProfileError("representative metrics evidence was not accepted")
    samples = payload.get("samples")
    aggregate = payload.get("aggregate")
    if not isinstance(samples, list) or len(samples) != 3 or not isinstance(aggregate, dict):
        raise ExecutionProfileError("representative metrics evidence is incomplete")
    if not all(_canonical_sample(sample) for sample in samples):
        raise ExecutionProfileError("representative metrics evidence is incomplete")
    paths = [sample["path"] for sample in samples]
    work_ids = [sample["work_id"] for sample in samples]
    if len(set(paths)) != len(paths) or len(set(work_ids)) != len(work_ids):
        raise ExecutionProfileError("representative metrics evidence is incomplete")
    if not _canonical_aggregate(aggregate, samples):
        raise ExecutionProfileError("representative metrics evidence is incomplete")
    return payload


def finalize_fast_ledger(text: str, plan_task_ids: tuple[str, ...]) -> str:
    """Build the one-shot strict-compatible ledger written after fast approval."""
    parsed = parse_execution_ledger(text, plan_task_ids)
    if parsed.initial_profile is not ExecutionProfile.FAST or parsed.effective_profile is not ExecutionProfile.FAST:
        raise ExecutionProfileError("only an unelevated fast ledger may be finalized")
    if parsed.untouched:
        raise ExecutionProfileError("fast final approval requires every task implemented")
    semantic = strip_html_comments_outside_fences(text)
    replacements: list[tuple[int, int, str]] = []
    for line, start, end in unfenced_markdown_lines(semantic):
        plain = line.rstrip("\r\n")
        checkbox = _CHECKBOX_RE.match(plain)
        implemented = _IMPLEMENTED_RE.match(plain)
        original_line = text[start:end]
        if checkbox:
            if checkbox.group(1) == " ":
                replacements.append(
                    (start, end, original_line.replace("- [ ]", "- [x]", 1))
                )
        elif implemented:
            number, base, head = implemented.groups()
            replacements.append((
                start,
                end,
                f"Task {number}: complete (commits {base}..{head}, final review clean)"
                + original_line[len(original_line.rstrip("\r\n")):],
            ))
    result: list[str] = []
    cursor = 0
    for start, end, replacement in replacements:
        result.append(text[cursor:start])
        result.append(replacement)
        cursor = end
    result.append(text[cursor:])
    migrated = "".join(result)
    parse_execution_ledger(migrated, plan_task_ids)
    return migrated

"""Pure strict/fast execution-profile and ledger semantics.

This module deliberately has no CLI, filesystem mutation, or agent-surface
dependencies.  Callers obtain a parsed ledger here, validate Git ancestry at
their boundary, and atomically persist a complete migrated ledger when a fast
run receives final approval.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import json
from pathlib import Path
import re
from collections.abc import Callable
from typing import Any

from tools.workflow_cli.markdown import (
    plan_task_anchors,
    strip_nonsemantic_markdown,
    unfenced_markdown_lines,
)
from tools.workflow_cli.models import TierBase, TierEstimate


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
_IMPLEMENTED_RE = re.compile(
    rf"^Task ([1-9][0-9]*): implemented \(commits ({_SHORT_SHA_RE})\.\.({_SHORT_SHA_RE}), verification recorded\)$"
)
_COMPLETE_RE = re.compile(
    rf"^Task ([1-9][0-9]*): complete \(commits ({_SHORT_SHA_RE})\.\.({_SHORT_SHA_RE}), (review|final review) clean\)$"
)
_MARKER_LIKE_RE = re.compile(r"^Task [0-9]+: (?:implemented|complete).*$")
_CHECKBOX_RE = re.compile(r"^- \[([ x])\] (PLAN-TASK-[0-9]{3})\b")
_BASE_RE = re.compile(r"^Execution BASE: ([0-9a-f]{40})$")


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
    profile_like = [line for line in lines if line.startswith("Execution Profile:")]
    if len(profiles) != len(profile_like) or len(profiles) > 1:
        raise ExecutionProfileError("initial execution profile is malformed or duplicated")
    initial = ExecutionProfile(profiles[0]) if profiles else ExecutionProfile.STRICT

    escalations = [match.group(1) for line in lines if (match := _ESCALATION_RE.match(line))]
    escalation_like = [line for line in lines if line.startswith("Profile Escalation:")]
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
                number, base, head, _review_kind = complete.groups()
                markers.append(TaskMarker(int(number), "complete", base, head))
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


def fast_structure_eligible(tier: TierEstimate) -> bool:
    """Fast may only be considered for a locked LIGHT tier without modifiers."""
    return (
        isinstance(tier, TierEstimate)
        and tier.base is TierBase.LIGHT
        and not tier.modifiers
        and tier._floor_base is not None
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


def consume_accepted_sample_evidence(path: str | Path) -> dict[str, Any]:
    """Read only the saved validator evidence; never discover sample directories."""
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ExecutionProfileError("representative metrics evidence is unreadable") from exc
    if not isinstance(payload, dict) or payload.get("status") != "ok" or payload.get("message") != "representative_metrics_accepted":
        raise ExecutionProfileError("representative metrics evidence was not accepted")
    samples = payload.get("samples")
    aggregate = payload.get("aggregate")
    if not isinstance(samples, list) or len(samples) != 3 or not isinstance(aggregate, dict):
        raise ExecutionProfileError("representative metrics evidence is incomplete")
    if aggregate.get("representative") is not True or aggregate.get("sample_count") != 3:
        raise ExecutionProfileError("representative metrics evidence is not diverse")
    if any(not isinstance(sample, dict) or not isinstance(sample.get("work_id"), str) for sample in samples):
        raise ExecutionProfileError("representative metrics evidence has invalid sample identity")
    return payload


def finalize_fast_ledger(text: str, plan_task_ids: tuple[str, ...]) -> str:
    """Build the one-shot strict-compatible ledger written after fast approval."""
    parsed = parse_execution_ledger(text, plan_task_ids)
    if parsed.initial_profile is not ExecutionProfile.FAST or parsed.effective_profile is not ExecutionProfile.FAST:
        raise ExecutionProfileError("only an unelevated fast ledger may be finalized")
    if parsed.untouched:
        raise ExecutionProfileError("fast final approval requires every task implemented")
    result: list[str] = []
    for line in text.splitlines(keepends=True):
        plain = line.rstrip("\r\n")
        checkbox = _CHECKBOX_RE.match(plain)
        implemented = _IMPLEMENTED_RE.match(plain)
        if checkbox:
            result.append(line.replace("- [ ]", "- [x]", 1) if checkbox.group(1) == " " else line)
        elif implemented:
            number, base, head = implemented.groups()
            result.append(f"Task {number}: complete (commits {base}..{head}, final review clean)" + line[len(plain):])
        else:
            result.append(line)
    migrated = "".join(result)
    parse_execution_ledger(migrated, plan_task_ids)
    return migrated

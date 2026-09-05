"""Pure structural role checkpoints stored in the authoritative progress ledger."""
from __future__ import annotations

from dataclasses import dataclass
import json
import re

from tools.workflow_cli.markdown import strip_nonsemantic_markdown, unfenced_markdown_lines


MUTATING_ROLES = {"implementer", "fixer", "final_fixer"}
INITIAL_ROLES = {"implementer", "task_reviewer", "final_reviewer"}
ROLES = INITIAL_ROLES | {"fixer", "task_rereviewer", "final_fixer", "final_rereviewer"}
_SHA = re.compile(r"[0-9a-f]{40}")
_DISPATCH_FIELDS = {"sequence", "role", "task", "fix_wave", "base", "profile"}
_RESULT_FIELDS = _DISPATCH_FIELDS | {"status", "head", "reason"}


@dataclass(frozen=True)
class ExecutionJournal:
    base: str
    events: tuple[dict, ...] = ()
    inflight: dict | None = None


def canonical_json(value) -> str:
    return json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":"))


def _positive(value, *, zero=False) -> bool:
    return type(value) is int and value >= (0 if zero else 1)


def _payload(raw: str) -> dict:
    try:
        value = json.loads(raw)
        if not isinstance(value, dict) or canonical_json(value) != raw:
            raise ValueError("noncanonical payload")
        return value
    except (TypeError, ValueError) as exc:
        raise ValueError("execution journal payload is not canonical") from exc


def _validate_role(value: dict, task_count: int, *, completed: bool) -> None:
    fields = _RESULT_FIELDS if completed else _DISPATCH_FIELDS
    role, task = value.get("role"), value.get("task")
    if (
        set(value) != fields or not isinstance(role, str) or role not in ROLES
        or not _positive(value["sequence"]) or not _positive(value["fix_wave"], zero=True)
        or value["profile"] not in ("strict", "fast")
        or not isinstance(value["base"], str) or not _SHA.fullmatch(value["base"])
        or (role.startswith("final_") and task != "final")
        or (not role.startswith("final_") and (not _positive(task) or task > task_count))
        or ((role in INITIAL_ROLES) != (value["fix_wave"] == 0))
    ):
        raise ValueError("execution journal role is invalid")
    if completed:
        allowed = {"complete", "blocked"} if role in MUTATING_ROLES else {"approved", "changes_requested", "blocked"}
        if (
            not isinstance(value["status"], str) or value["status"] not in allowed or not isinstance(value["head"], str)
            or not _SHA.fullmatch(value["head"])
            or not isinstance(value["reason"], str) or "\n" in value["reason"] or "\r" in value["reason"]
            or (role not in MUTATING_ROLES and value["base"] != value["head"])
        ):
            raise ValueError("execution journal completion is invalid")


def parse_execution_journal(text: str, task_count: int) -> ExecutionJournal | None:
    header = None
    events = []
    inflight = None
    for line, _, _ in unfenced_markdown_lines(strip_nonsemantic_markdown(text)):
        plain = line.rstrip("\r\n")
        if not re.match(r"^\s*Execution (?:Journal|Role|Inflight)\b", plain):
            continue
        prefix, separator, raw = plain.partition(": ")
        if not separator or prefix not in {"Execution Journal", "Execution Role", "Execution Inflight"}:
            raise ValueError("execution journal line is malformed")
        value = _payload(raw)
        if prefix == "Execution Journal":
            if header is not None or events or inflight is not None:
                raise ValueError("execution journal header is duplicated or out of order")
            if set(value) != {"schema", "base"} or type(value["schema"]) is not int or value["schema"] != 1 or not isinstance(value["base"], str) or not _SHA.fullmatch(value["base"]):
                raise ValueError("execution journal header is invalid")
            header = value
        else:
            if header is None or inflight is not None:
                raise ValueError("execution journal roles are out of order")
            _validate_role(value, task_count, completed=prefix == "Execution Role")
            if value["sequence"] != len(events) + 1:
                raise ValueError("execution journal sequence is discontinuous")
            if prefix == "Execution Inflight":
                inflight = value
            else:
                events.append(value)
    if header is None:
        return None
    return ExecutionJournal(header["base"], tuple(events), inflight)


def next_role(ledger) -> dict:
    """Select a role from progress, never from observation metrics or Git history."""
    journal = ledger.journal
    if journal and journal.inflight:
        return dict(journal.inflight)
    events = journal.events if journal else ()
    last = events[-1] if events else None
    task = ledger.first_actionable_task()
    role = "implementer" if task is not None else "final_reviewer"
    wave = 0
    if task is not None and task in ledger.implemented:
        role = "task_reviewer"
    target = "final" if task is None else task
    if last and last["task"] == target:
        if last["status"] == "blocked":
            role, wave = last["role"], last["fix_wave"]
        elif last["role"] == "implementer":
            role = "task_reviewer"
        elif last["role"] in {"fixer", "final_fixer"}:
            role = "final_rereviewer" if target == "final" else "task_rereviewer"
            wave = last["fix_wave"]
        elif last["status"] == "changes_requested":
            role = "final_fixer" if target == "final" else "fixer"
            wave = last["fix_wave"] + 1
        elif target == "final" and last["status"] == "approved":
            role = None
    return {
        "sequence": len(events) + 1, "role": role,
        "task": target if role else None, "fix_wave": wave,
        "profile": ledger.effective_profile.value,
    }


def task_review_ranges(ledger, task: int, resolve_commit) -> list[dict[str, str]]:
    marker = ledger.marker_for(task)
    events = ledger.journal.events if ledger.journal else ()
    implementations = [event for event in events if event["role"] == "implementer" and event["task"] == task]
    ranges = []
    if marker:
        ranges.append({"base": resolve_commit(marker.base), "head": resolve_commit(marker.head)})
    elif implementations:
        ranges.append({"base": implementations[0]["base"], "head": implementations[-1]["head"]})
    ranges.extend(
        {"base": event["base"], "head": event["head"]}
        for event in events if event["role"] == "fixer" and event["task"] == task and event["base"] != event["head"]
    )
    return ranges

"""Pinned atomic structural progress updates; agents still own reports and review."""
from __future__ import annotations

import re
from pathlib import Path

from tools.workflow_cli.execution_journal import (
    MUTATING_ROLES, canonical_json, next_role, task_review_ranges,
)
from tools.workflow_cli.execution_metrics import (
    _close_fds, _current_verdict, _execution_base,
    _is_ancestor, _open_dir_at, _open_lock_at, _open_run, _parse_record_at,
    _plan_at, _read_text_at, _release_lock, _replace_text_at,
    _require_clean_code_worktree, _resolve_commit_or_full,
)
from tools.workflow_cli.execution_profile import (
    ExecutionProfileError, _semantic_source_lines, check_prerequisite_v2,
    finalize_fast_ledger, parse_execution_ledger, prerequisite_semantics_version,
    validate_ledger_commit_chain,
)
from tools.workflow_cli.markdown import PLAN_TASK_CHECKBOX_RE, plan_task_anchors, strip_nonsemantic_markdown
from tools.workflow_cli.models import RunStatus, WorkId


def _parse(progress, plan):
    ids = tuple(task_id for task_id, _ in plan_task_anchors(strip_nonsemantic_markdown(plan)))
    return parse_execution_ledger(progress, ids), ids


def _validate_chain(root, ledger, *, allow_inflight=False):
    validate_ledger_commit_chain(
        ledger, current_head=_execution_base(root),
        resolve_commit=lambda sha: _resolve_commit_or_full(root, sha),
        is_ancestor=lambda base, head: _is_ancestor(root, base, head),
        allow_inflight=allow_inflight,
    )


def _replace_line(text, predicate, replacement):
    matches = [(start, end) for line, start, end in _semantic_source_lines(text) if predicate(line.rstrip("\r\n"))]
    if len(matches) > 1:
        raise ExecutionProfileError("progress transition matches duplicate structural lines")
    if not matches:
        return text.rstrip("\n") + "\n" + replacement if replacement else text
    start, end = matches[0]
    return text[:start] + replacement + text[end:]


def _task_marker(text, task, base, head, *, complete):
    task_id = f"PLAN-TASK-{task:03d}"
    for line, start, end in _semantic_source_lines(text):
        row = PLAN_TASK_CHECKBOX_RE.match(line)
        if row and row.group(2) == task_id:
            mark = "x" if complete else " "
            # Preserve the title while normalizing only the structural checkbox.
            text = text[:start] + f"- [{mark}] {task_id}" + line[row.end():] + text[end:]
            break
    else:
        raise ExecutionProfileError("task checkbox is missing")
    kind = "complete" if complete else "implemented"
    evidence = "review clean" if complete else "verification recorded"
    marker = f"Task {task}: {kind} (commits {base[:7]}..{head[:7]}, {evidence})\n"
    return _replace_line(text, lambda line: line.startswith((f"Task {task}: complete (", f"Task {task}: implemented (")), marker)


def _report_name(role, task):
    if task == "final":
        return "final-review-report.md"
    suffix = "review" if role in {"task_reviewer", "task_rereviewer"} else "report"
    return f"task-{task}-{suffix}.md"


def _result(root, work_id, ledger, result=None):
    action = next_role(ledger)
    inflight = bool(ledger.journal and ledger.journal.inflight)
    role, task = action["role"], action["task"]
    ranges = []
    if isinstance(task, int):
        ranges = task_review_ranges(ledger, task, lambda sha: _resolve_commit_or_full(root, sha))
    elif task == "final":
        ranges = [{"base": ledger.execution_base, "head": _execution_base(root)}]
    return {
        "work_id": str(work_id), "result": result or ("recover_role_result" if inflight else "ready" if role else "complete"),
        "effective_profile": ledger.effective_profile.value,
        "next_role": role, "task": task, "fix_wave": action["fix_wave"],
        "role_sequence": action["sequence"], "inflight": inflight,
        "role_base": action.get("base"), "review_ranges": ranges,
        "report_path": str(root / ".req-to-plan" / str(work_id) / "execution" / _report_name(role, task)) if role else None,
    }


def _transition(root, execution_fd, progress, plan, action, sequence, status, head, reason):
    ledger, ids = _parse(progress, plan)
    expected = next_role(ledger)
    journal = ledger.journal
    if action == "complete" and journal and sequence <= len(journal.events):
        recorded = journal.events[sequence - 1]
        if (recorded["status"], recorded["head"], recorded["reason"]) != (status, head, reason or ""):
            raise ExecutionProfileError("conflicting retry for completed role")
        return progress, "already_applied"
    if sequence != expected["sequence"] or expected["role"] is None:
        raise ExecutionProfileError("stale role sequence or execution already complete")
    if reason is not None and (not isinstance(reason, str) or not reason.strip() or "\n" in reason or "\r" in reason):
        raise ExecutionProfileError("escalation reason must be one non-blank line")
    if action == "recover":
        if journal is not None or expected["role"] != "implementer" or status != "complete" or head != _execution_base(root):
            raise ExecutionProfileError("legacy recovery requires an unjournaled implementer result at current HEAD")
        marker = ledger.marker_for(expected["task"] - 1)
        base = _resolve_commit_or_full(root, marker.head) if marker else ledger.execution_base
        validate_ledger_commit_chain(
            ledger, current_head=base,
            resolve_commit=lambda sha: _resolve_commit_or_full(root, sha),
            is_ancestor=lambda older, newer: _is_ancestor(root, older, newer),
        )
        report = _read_text_at(execution_fd, _report_name("implementer", expected["task"])) or ""
        report_lines = [line.strip() for line, _, _ in _semantic_source_lines(report)]
        ranges = re.findall(r"(?<![0-9a-f])([0-9a-f]{7}|[0-9a-f]{40})\.\.([0-9a-f]{7}|[0-9a-f]{40})(?![0-9a-f])", "\n".join(report_lines))
        if (
            not any(re.fullmatch(r"(?:Status: )?DONE(?:_WITH_CONCERNS)?", line) for line in report_lines)
            or not ranges or any(_resolve_commit_or_full(root, left) != base or _resolve_commit_or_full(root, right) != head for left, right in ranges)
        ):
            raise ExecutionProfileError("legacy report must record DONE and the exact original BASE..HEAD range; do not infer history")
        progress += "\nExecution Journal: " + canonical_json({"schema": 1, "base": base}) + "\n"
        progress += "Execution Inflight: " + canonical_json({**expected, "base": base}) + "\n"
        return _transition(root, execution_fd, progress, plan, "complete", sequence, status, head, reason)
    if action == "begin":
        if status is not None or head is not None or reason is not None:
            raise ExecutionProfileError("begin does not accept completion fields")
        if journal and journal.inflight:
            _validate_chain(root, ledger, allow_inflight=True)
            return progress, "recover_role_result"
        _require_clean_code_worktree(root)
        _validate_chain(root, ledger)
        if expected["role"] == "implementer" and prerequisite_semantics_version(plan) == 2:
            check_prerequisite_v2(progress, plan, expected["task"])
        if journal is None:
            progress += "\nExecution Journal: " + canonical_json({"schema": 1, "base": _execution_base(root)}) + "\n"
        dispatch = {**expected, "base": _execution_base(root)}
        return progress.rstrip("\n") + "\nExecution Inflight: " + canonical_json(dispatch) + "\n", "started"
    if action == "escalate":
        if status is not None or head is not None or reason is None or (journal and journal.inflight):
            raise ExecutionProfileError("escalate requires a reason and an idle role boundary")
        _validate_chain(root, ledger)
        if ledger.escalation_reason == reason:
            return progress, "already_applied"
    elif action == "complete":
        if not journal or not journal.inflight:
            raise ExecutionProfileError("role completion requires a durable begin checkpoint")
        dispatch = journal.inflight
        allowed = {"complete", "blocked"} if dispatch["role"] in MUTATING_ROLES else {"approved", "changes_requested", "blocked"}
        if status not in allowed or head != _execution_base(root):
            raise ExecutionProfileError("role result status or HEAD does not match the dispatch")
        _require_clean_code_worktree(root)
        _validate_chain(root, ledger, allow_inflight=True)
        if dispatch["role"] not in MUTATING_ROLES and head != dispatch["base"]:
            raise ExecutionProfileError("read-only reviewer changed the commit boundary")
        _read_text_at(execution_fd, _report_name(dispatch["role"], dispatch["task"]))
        event = {**dispatch, "head": head, "status": status, "reason": reason or ""}
        progress = _replace_line(progress, lambda line: line.startswith("Execution Inflight: "), "Execution Role: " + canonical_json(event) + "\n")
        updated, _ = _parse(progress, plan)
        role, task = dispatch["role"], dispatch["task"]
        if role == "implementer" and status == "complete":
            ranges = task_review_ranges(updated, task, lambda sha: _resolve_commit_or_full(root, sha))
            if not ranges or ranges[0]["base"] == ranges[0]["head"]:
                raise ExecutionProfileError("implemented task must contain a commit")
            if dispatch["profile"] == "fast":
                progress = _task_marker(progress, task, **ranges[0], complete=False)
        if role in {"task_reviewer", "task_rereviewer"} and status == "approved":
            unresolved = set()
            for line, _, _ in _semantic_source_lines(progress):
                label, _, finding = line.strip().partition(":")
                if label in {"Gap", "Unresolved"}:
                    unresolved.add(finding.strip())
                elif label == "Resolved":
                    unresolved.discard(finding.strip())
            if unresolved:
                raise ExecutionProfileError("unresolved task review concerns block completion")
            ranges = task_review_ranges(updated, task, lambda sha: _resolve_commit_or_full(root, sha))
            if not ranges:
                raise ExecutionProfileError("reviewed task implementation range is missing")
            progress = _task_marker(progress, task, **ranges[0], complete=True)
        if role in {"final_reviewer", "final_rereviewer"} and status == "approved" and reason is None:
            final = _read_text_at(execution_fd, "final-review.md")
            if _current_verdict(final or "") != "approved":
                raise ExecutionProfileError("approved final review verdict must be durable")
            if updated.effective_profile.value == "fast":
                progress = finalize_fast_ledger(progress, ids)
            elif updated.untouched or updated.implemented:
                raise ExecutionProfileError("final approval requires all tasks reviewed-complete")
    else:
        raise ExecutionProfileError("unknown progress action")
    if reason is not None:
        if ledger.effective_profile.value != "fast":
            raise ExecutionProfileError("only an effective fast run may escalate")
        progress += f"\nProfile Escalation: fast -> strict (reason: {reason})\n"
    return progress, "recorded"


def _operate(root, work_id, *, action=None, sequence=None, status=None, head=None, reason=None):
    root = Path(root).resolve()
    repo_fd = workspace_fd = run_fd = execution_fd = logs_fd = lock_fd = None
    try:
        repo_fd, workspace_fd, run_fd = _open_run(root, work_id)
        logs_fd, lock_fd = _open_lock_at(run_fd, "progress.lock")
        if _parse_record_at(run_fd, work_id).status != RunStatus.EXECUTING:
            raise ExecutionProfileError("progress requires an EXECUTING run")
        plan = _plan_at(run_fd)
        execution_fd = _open_dir_at(run_fd, "execution")
        progress = _read_text_at(execution_fd, "progress.md")
        assert progress is not None
        identities = [
            line.strip() for line, _, _ in _semantic_source_lines(progress)
            if re.match(r"^\s*work_id\s*:", line)
        ]
        if identities != [f"work_id: {work_id}"]:
            raise ExecutionProfileError("progress work_id must match the selected run exactly once")
        result = None
        if action:
            if type(sequence) is not int or sequence < 1:
                raise ExecutionProfileError("expected role sequence must be a positive integer")
            updated, result = _transition(root, execution_fd, progress, plan, action, sequence, status, head, reason)
            ledger, _ = _parse(updated, plan)
            _validate_chain(root, ledger, allow_inflight=bool(ledger.journal and ledger.journal.inflight))
            if updated != progress:
                _replace_text_at(execution_fd, "progress.md", updated)
            progress = updated
        ledger, _ = _parse(progress, plan)
        _validate_chain(root, ledger, allow_inflight=bool(ledger.journal and ledger.journal.inflight))
        return _result(root, work_id, ledger, result)
    finally:
        if lock_fd is not None:
            _release_lock(logs_fd, lock_fd)
        _close_fds(execution_fd, run_fd, workspace_fd, repo_fd)


def resume_execution_progress(base_path: Path, work_id: WorkId) -> dict:
    return _operate(base_path, work_id)


def record_execution_progress(base_path: Path, work_id: WorkId, action: str, expected_sequence: int, *, status=None, head=None, reason=None) -> dict:
    return _operate(base_path, work_id, action=action, sequence=expected_sequence, status=status, head=head, reason=reason)

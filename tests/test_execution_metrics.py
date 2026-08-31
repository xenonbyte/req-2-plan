"""Direct contracts for the Phase 0 metrics core."""
from __future__ import annotations

import errno
import fcntl
import json
import os
from pathlib import Path
import re
import stat
import subprocess

import pytest

from tools.workflow_cli.execution_metrics import (
    INSTRUMENTATION_SCHEMA,
    MetricsFormatError,
    MetricsInputError,
    PrerequisiteError,
    RepresentativeSamplesError,
    append_metrics_invocation,
    bootstrap_self_hosted_metrics,
    check_prerequisite_v1,
    classify_change_shape,
    parse_metrics,
    quantize_elapsed_seconds,
    read_metrics_status,
    finalize_metrics,
    start_execution_transaction,
    validate_representative_samples,
)
from tools.workflow_cli.gates import check_execution_complete, check_final_review_recorded
from tools.workflow_cli.artifact import write_artifact
from tools.workflow_cli.models import RunStatus, Stage, WorkId
from tools.workflow_cli.state import RunStateManager, create_run_record


def _git_init(path: Path) -> str:
    import subprocess

    subprocess.run(["git", "init", "-q", str(path)], check=True)
    subprocess.run(["git", "-C", str(path), "config", "user.email", "test@example.invalid"], check=True)
    subprocess.run(["git", "-C", str(path), "config", "user.name", "test"], check=True)
    (path / "seed").write_text("seed\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(path), "add", "seed"], check=True)
    subprocess.run(["git", "-C", str(path), "commit", "-qm", "seed"], check=True)
    return subprocess.run(
        ["git", "-C", str(path), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _commit(path: Path, name: str) -> str:
    import subprocess

    (path / name).write_text(name + "\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(path), "add", name], check=True)
    subprocess.run(["git", "-C", str(path), "commit", "-qm", name], check=True)
    return subprocess.run(
        ["git", "-C", str(path), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _plan(count: int) -> str:
    return "\n".join(f"### PLAN-TASK-{number:03d}: task {number}" for number in range(1, count + 1)) + "\n"


def _invocation(
    role: str,
    task: int | str,
    sequence: int,
    *,
    context_mode: str = "direct_acs",
    fix_wave: int = 0,
) -> str:
    status = "approved" if "reviewer" in role else "complete"
    kind = "declared_payload_bytes" if context_mode == "direct_acs" else "semantic_payload_bytes"
    return f"""## Invocation {sequence}
role: {role}
task: {task}
model: unavailable
started_at: 2026-08-30T00:00:00.000000Z
ended_at: 2026-08-30T00:00:01.000000Z
elapsed_seconds: 1.000000
context_mode: {context_mode}
context_bytes_kind: {kind}
context_bytes: 100
verification_records_json: [{{"command":"pytest","elapsed_seconds":"0.100000","reason":"required","scope":"full_suite","status":"passed"}}]
verification_total_seconds: 0.100000
report_bytes: 42
status: {status}
concerns_json: []
fix_wave: {fix_wave}
input_tokens: unavailable
output_tokens: unavailable
total_tokens: unavailable
"""


def _structured_record(
    execution: Path,
    *,
    expected_sequence: int,
    role: str,
    task: int | str,
    status: str,
    fix_wave: int = 0,
) -> dict[str, object]:
    if task == "final":
        report = execution / "final-review-report.md"
    elif "reviewer" in role:
        report = execution / f"task-{task}-review.md"
    else:
        report = execution / f"task-{task}-report.md"
    report.write_text("report\n", encoding="utf-8")
    return {
        "expected_sequence": expected_sequence,
        "role": role,
        "task": task,
        "model": "unavailable",
        "started_at": "2026-08-31T00:00:00.000000Z",
        "ended_at": "2026-08-31T00:00:01.000000Z",
        "elapsed_seconds": "1.000000",
        "context_mode": "semantic_view",
        "context_bytes": 123,
        "verification_records": [{
            "command": "pytest -q",
            "scope": "targeted",
            "reason": "direct contract",
            "elapsed_seconds": "0.125000",
            "status": "passed",
        }],
        "report_path": str(report),
        "status": status,
        "concerns": [],
        "fix_wave": fix_wave,
    }


def _started_metrics_run(tmp_path: Path, *, task_count: int = 1) -> tuple[WorkId, Path, Path, str]:
    work_id = WorkId("WF-20260831-structured-metrics")
    run_dir = tmp_path / ".req-to-plan" / str(work_id)
    record = create_run_record(work_id)
    record.status = RunStatus.CLOSED_AT_PLAN_CHECKPOINT
    record.current_stage = Stage.CLOSED
    RunStateManager(run_dir).save(record)
    write_artifact(run_dir, Stage.PLAN, _plan(task_count), version=1, status="approved")
    base = _git_init(tmp_path)
    start_execution_transaction(tmp_path, work_id, "strict")
    return work_id, run_dir, run_dir / "execution", base


def _append_complete_metrics_sequence(
    base_path: Path,
    work_id: WorkId,
    execution: Path,
    *,
    failed_verification: bool = False,
) -> None:
    for sequence, role, task, status in (
        (1, "implementer", 1, "complete"),
        (2, "task_reviewer", 1, "approved"),
        (3, "final_reviewer", "final", "approved"),
    ):
        record = _structured_record(
            execution,
            expected_sequence=sequence,
            role=role,
            task=task,
            status=status,
        )
        if failed_verification and sequence == 3:
            record["verification_records"][0]["status"] = "failed"
        append_metrics_invocation(base_path, work_id, record)


def _commit_paths(base_path: Path, paths: tuple[str, ...]) -> str:
    for relative in paths:
        target = base_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(f"content for {relative}\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(base_path), "add", "--", *paths], check=True)
    subprocess.run(["git", "-C", str(base_path), "commit", "-qm", "change"], check=True)
    return subprocess.run(
        ["git", "-C", str(base_path), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _record_authoritative_completion(
    execution: Path,
    base: str,
    head: str,
    *,
    checked_row: str = "- [x] PLAN-TASK-001 — task 1",
    verdict: str = "Approved",
) -> None:
    progress_path = execution / "progress.md"
    progress = progress_path.read_text(encoding="utf-8")
    progress = re.sub(r"^- \[ \] PLAN-TASK-001.*$", checked_row, progress, flags=re.MULTILINE)
    progress += f"\nTask 1: complete (commits {base[:7]}..{head[:7]}, review clean)\n"
    progress_path.write_text(progress, encoding="utf-8")
    (execution / "final-review.md").write_text(
        f"Verdict: {verdict}\n", encoding="utf-8"
    )


def test_structured_metrics_status_append_and_exact_retry(tmp_path):
    work_id, _, execution, _ = _started_metrics_run(tmp_path)

    initial = read_metrics_status(tmp_path, work_id)
    assert initial["result"] == "status"
    assert initial["invocation_count"] == 0
    assert initial["next_sequence"] == 1

    request = _structured_record(
        execution,
        expected_sequence=1,
        role="implementer",
        task=1,
        status="complete",
    )
    appended = append_metrics_invocation(tmp_path, work_id, request)
    retried = append_metrics_invocation(tmp_path, work_id, request)

    assert appended["result"] == "appended"
    assert retried["result"] == "already_applied"
    parsed = parse_metrics((execution / "metrics.md").read_text(encoding="utf-8"))
    invocation = parsed.invocations[0]
    assert invocation["context_bytes_kind"] == "semantic_payload_bytes"
    assert invocation["verification_total_seconds"] == "0.125000"
    assert invocation["report_bytes"] == len("report\n".encode())


def test_structured_metrics_rejects_record_schema_errors_as_input_errors(tmp_path):
    work_id, _, execution, _ = _started_metrics_run(tmp_path)
    record = _structured_record(
        execution,
        expected_sequence=1,
        role="implementer",
        task=1,
        status="complete",
    )
    with pytest.raises(MetricsInputError, match="unknown"):
        append_metrics_invocation(tmp_path, work_id, dict(record, surprise=True))
    with pytest.raises(MetricsInputError, match="fractional"):
        append_metrics_invocation(tmp_path, work_id, dict(record, elapsed_seconds="1.0"))


def test_structured_metrics_rejects_skips_conflicts_and_illegal_role_transitions(tmp_path):
    work_id, _, execution, _ = _started_metrics_run(tmp_path)
    first = _structured_record(
        execution,
        expected_sequence=1,
        role="implementer",
        task=1,
        status="complete",
    )
    append_metrics_invocation(tmp_path, work_id, first)

    with pytest.raises(MetricsFormatError, match="conflict"):
        append_metrics_invocation(tmp_path, work_id, dict(first, context_bytes=999))
    with pytest.raises(MetricsFormatError, match="sequence"):
        append_metrics_invocation(
            tmp_path,
            work_id,
            _structured_record(
                execution,
                expected_sequence=3,
                role="task_reviewer",
                task=1,
                status="approved",
            ),
        )
    with pytest.raises(MetricsFormatError, match="role transition"):
        append_metrics_invocation(
            tmp_path,
            work_id,
            _structured_record(
                execution,
                expected_sequence=2,
                role="implementer",
                task=1,
                status="complete",
            ),
        )


def test_structured_metrics_fix_waves_are_contiguous_paired_and_close_before_final(tmp_path):
    work_id, _, execution, _ = _started_metrics_run(tmp_path)
    sequence = (
        ("implementer", 1, "complete", 0),
        ("task_reviewer", 1, "changes_requested", 0),
        ("fixer", 1, "complete", 1),
        ("task_rereviewer", 1, "changes_requested", 1),
        ("fixer", 1, "complete", 2),
        ("task_rereviewer", 1, "approved", 2),
        ("final_reviewer", "final", "changes_requested", 0),
        ("final_fixer", "final", "complete", 1),
        ("final_rereviewer", "final", "approved", 1),
    )
    for number, (role, task, status, wave) in enumerate(sequence, start=1):
        result = append_metrics_invocation(
            tmp_path,
            work_id,
            _structured_record(
                execution,
                expected_sequence=number,
                role=role,
                task=task,
                status=status,
                fix_wave=wave,
            ),
        )
        assert result["sequence"] == number
    assert read_metrics_status(tmp_path, work_id)["next_sequence"] == 10


def test_structured_metrics_records_blocked_role_with_unavailable_verification(tmp_path):
    work_id, _, execution, _ = _started_metrics_run(tmp_path)
    record = _structured_record(
        execution,
        expected_sequence=1,
        role="implementer",
        task=1,
        status="blocked",
    )
    record["verification_records"] = "unavailable"

    result = append_metrics_invocation(tmp_path, work_id, record)

    assert result["result"] == "appended"
    parsed = parse_metrics((execution / "metrics.md").read_text(encoding="utf-8"))
    assert parsed.invocations[0]["verification_records"] == "unavailable"
    assert parsed.invocations[0]["verification_total_seconds"] == "unavailable"


def test_structured_metrics_self_host_bootstrap_sequence_starts_at_task_three(tmp_path):
    work_id, _, execution, _, _, _ = _bootstrap_ready_run(tmp_path)
    bootstrap_self_hosted_metrics(tmp_path, work_id, 2)

    first = append_metrics_invocation(
        tmp_path,
        work_id,
        _structured_record(
            execution,
            expected_sequence=1,
            role="implementer",
            task=3,
            status="complete",
        ),
    )
    second = append_metrics_invocation(
        tmp_path,
        work_id,
        _structured_record(
            execution,
            expected_sequence=2,
            role="task_reviewer",
            task=3,
            status="approved",
        ),
    )

    assert first["result"] == "appended"
    assert second["result"] == "appended"


def test_self_host_partial_append_allows_retroactive_task_six_and_keeps_retry_guards(tmp_path):
    work_id, _, execution, _, _, _ = _bootstrap_ready_run(tmp_path)
    bootstrap_self_hosted_metrics(tmp_path, work_id, 2)

    sequence = (
        ("implementer", 3, "complete", 0),
        ("task_reviewer", 3, "approved", 0),
        ("implementer", 4, "complete", 0),
        ("task_reviewer", 4, "approved", 0),
        ("implementer", 5, "complete", 0),
        ("task_reviewer", 5, "approved", 0),
        ("implementer", 6, "complete", 0),
        ("task_reviewer", 6, "approved", 0),
    )
    for expected_sequence, (role, task, status, fix_wave) in enumerate(sequence, start=1):
        append_metrics_invocation(
            tmp_path,
            work_id,
            _structured_record(
                execution,
                expected_sequence=expected_sequence,
                role=role,
                task=task,
                status=status,
                fix_wave=fix_wave,
            ),
        )

    retroactive = _structured_record(
        execution,
        expected_sequence=9,
        role="task_rereviewer",
        task=6,
        status="approved",
        fix_wave=1,
    )
    assert append_metrics_invocation(tmp_path, work_id, retroactive)["result"] == "appended"
    assert append_metrics_invocation(tmp_path, work_id, retroactive)["result"] == "already_applied"
    with pytest.raises(MetricsFormatError, match="conflicting retry"):
        append_metrics_invocation(tmp_path, work_id, dict(retroactive, context_bytes=999))
    with pytest.raises(MetricsFormatError, match="expected sequence"):
        append_metrics_invocation(
            tmp_path,
            work_id,
            _structured_record(
                execution,
                expected_sequence=11,
                role="fixer",
                task=6,
                status="complete",
                fix_wave=2,
            ),
        )


def test_self_host_partial_append_rejects_prebootstrap_task_history(tmp_path):
    work_id, _, execution, _, _, _ = _bootstrap_ready_run(tmp_path)
    bootstrap_self_hosted_metrics(tmp_path, work_id, 2)

    with pytest.raises(MetricsFormatError, match="Task 003"):
        append_metrics_invocation(
            tmp_path,
            work_id,
            _structured_record(
                execution,
                expected_sequence=1,
                role="implementer",
                task=2,
                status="complete",
            ),
        )


def _prepare_self_host_partial_finalization(tmp_path: Path) -> tuple[WorkId, Path]:
    work_id, _, execution, base, _, _ = _bootstrap_ready_run(tmp_path)
    bootstrap_self_hosted_metrics(tmp_path, work_id, 2)
    head = _commit_paths(tmp_path, ("src/self_host_partial.py",))
    progress_path = execution / "progress.md"
    progress = progress_path.read_text(encoding="utf-8")
    progress = re.sub(
        r"^- \[ \] (PLAN-TASK-\d{3} task \d+)$",
        r"- [x] \1",
        progress,
        flags=re.MULTILINE,
    )
    progress += "\n".join(
        f"Task {number}: complete (commits {base[:7]}..{head[:7]}, review clean)"
        for number in range(3, 10)
    ) + "\n"
    progress_path.write_text(progress, encoding="utf-8")
    (execution / "final-review.md").write_text("Verdict: Approved\n", encoding="utf-8")
    return work_id, execution


def test_self_host_partial_finalization_closes_observation_without_rewriting_header(tmp_path):
    work_id, execution = _prepare_self_host_partial_finalization(tmp_path)
    record = _structured_record(
        execution,
        expected_sequence=1,
        role="task_rereviewer",
        task=6,
        status="approved",
        fix_wave=1,
    )
    record["verification_records"][0]["status"] = "failed"
    append_metrics_invocation(tmp_path, work_id, record)

    finalized = finalize_metrics(tmp_path, work_id, 1)
    retried = finalize_metrics(tmp_path, work_id, 1)
    parsed = parse_metrics((execution / "metrics.md").read_text(encoding="utf-8"))

    assert finalized["result"] == "finalized"
    assert finalized["change_shape"] != "unavailable"
    assert retried["result"] == "already_finalized"
    assert parsed.header["instrumentation_complete"] is False
    assert parsed.header["bootstrap_gap"] == "execution_start_through_task_002_reviewed_complete"
    assert parsed.header["metrics_finalized"] is True


def test_self_host_partial_finalization_still_rejects_blocked_evidence_without_rewriting(tmp_path):
    work_id, execution = _prepare_self_host_partial_finalization(tmp_path)
    record = _structured_record(
        execution,
        expected_sequence=1,
        role="implementer",
        task=3,
        status="blocked",
    )
    record["verification_records"] = "unavailable"
    append_metrics_invocation(tmp_path, work_id, record)
    before = (execution / "metrics.md").read_bytes()

    with pytest.raises(MetricsFormatError, match="blocked"):
        finalize_metrics(tmp_path, work_id, 1)

    assert (execution / "metrics.md").read_bytes() == before


def test_finalized_self_host_partial_remains_nonrepresentative(tmp_path):
    work_id, execution = _prepare_self_host_partial_finalization(tmp_path)
    append_metrics_invocation(
        tmp_path,
        work_id,
        _structured_record(
            execution,
            expected_sequence=1,
            role="task_rereviewer",
            task=6,
            status="approved",
            fix_wave=1,
        ),
    )
    finalize_metrics(tmp_path, work_id, 1)
    run_dir = execution.parent
    record = RunStateManager(run_dir).load()
    record.status = RunStatus.ARCHIVED
    RunStateManager(run_dir).save(record)
    first = _archived_sample(tmp_path / "samples", "WF-20260831-partial-first", 1, "docs_only")
    second = _archived_sample(tmp_path / "samples", "WF-20260831-partial-second", 2, "single_module_code")

    with pytest.raises(RepresentativeSamplesError) as error:
        validate_representative_samples((run_dir, first, second))

    assert any(
        item["rule"] == "instrumentation_complete"
        for item in error.value.result["details"]
    )


def test_structured_metrics_lock_contention_and_unsafe_report_are_fail_closed(tmp_path):
    work_id, run_dir, execution, _ = _started_metrics_run(tmp_path)
    lock_path = run_dir / "logs" / "metrics.lock"
    lock_path.parent.mkdir(exist_ok=True)
    with lock_path.open("a+") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(MetricsFormatError, match="busy"):
            read_metrics_status(tmp_path, work_id)
        fcntl.flock(lock.fileno(), fcntl.LOCK_UN)

    outside = tmp_path / "outside-report.md"
    outside.write_text("outside\n", encoding="utf-8")
    report = execution / "task-1-report.md"
    report.symlink_to(outside)
    record = _structured_record(
        execution,
        expected_sequence=1,
        role="implementer",
        task=1,
        status="complete",
    )
    report.unlink()
    report.symlink_to(outside)
    with pytest.raises(MetricsFormatError, match="non-regular|unsafe"):
        append_metrics_invocation(tmp_path, work_id, record)


def test_structured_metrics_post_commit_retry_recovers_without_duplicate(tmp_path, monkeypatch):
    import tools.workflow_cli.execution_metrics as metrics_module

    work_id, _, execution, _ = _started_metrics_run(tmp_path)
    record = _structured_record(
        execution,
        expected_sequence=1,
        role="implementer",
        task=1,
        status="complete",
    )
    original = metrics_module._replace_text_at
    injected = False

    def landed_then_uncertain(parent_fd, name, content):
        nonlocal injected
        original(parent_fd, name, content)
        if name == "metrics.md" and not injected:
            injected = True
            raise OSError("injected committed-state unknown")

    monkeypatch.setattr(metrics_module, "_replace_text_at", landed_then_uncertain)
    with pytest.raises(OSError, match="committed-state unknown"):
        append_metrics_invocation(tmp_path, work_id, record)
    monkeypatch.setattr(metrics_module, "_replace_text_at", original)

    recovered = append_metrics_invocation(tmp_path, work_id, record)
    assert recovered["result"] == "already_applied"
    assert len(parse_metrics((execution / "metrics.md").read_text()).invocations) == 1


def test_structured_metrics_precommit_write_failure_preserves_document(tmp_path, monkeypatch):
    import tools.workflow_cli.execution_metrics as metrics_module

    work_id, _, execution, _ = _started_metrics_run(tmp_path)
    before = (execution / "metrics.md").read_bytes()
    monkeypatch.setattr(
        metrics_module,
        "_write_all",
        lambda *args: (_ for _ in ()).throw(OSError("injected short write")),
    )
    with pytest.raises(OSError, match="short write"):
        append_metrics_invocation(
            tmp_path,
            work_id,
            _structured_record(
                execution,
                expected_sequence=1,
                role="implementer",
                task=1,
                status="complete",
            ),
        )
    assert (execution / "metrics.md").read_bytes() == before
    assert not list(execution.glob(".metrics.md.*.tmp"))


def test_finalize_metrics_derives_change_shape_closes_header_and_is_idempotent(tmp_path):
    work_id, _, execution, base = _started_metrics_run(tmp_path)
    append_metrics_invocation(
        tmp_path,
        work_id,
        _structured_record(
            execution, expected_sequence=1, role="implementer", task=1, status="complete"
        ),
    )
    append_metrics_invocation(
        tmp_path,
        work_id,
        _structured_record(
            execution, expected_sequence=2, role="task_reviewer", task=1, status="approved"
        ),
    )
    append_metrics_invocation(
        tmp_path,
        work_id,
        _structured_record(
            execution, expected_sequence=3, role="final_reviewer", task="final", status="approved"
        ),
    )
    source = tmp_path / "src" / "feature.py"
    source.parent.mkdir()
    source.write_text("enabled = True\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(tmp_path), "add", "src/feature.py"], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "commit", "-qm", "feature"], check=True)
    head = subprocess.run(
        ["git", "-C", str(tmp_path), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    progress = (execution / "progress.md").read_text(encoding="utf-8")
    progress = progress.replace("- [ ] PLAN-TASK-001", "- [x] PLAN-TASK-001")
    progress += f"\nTask 1: complete (commits {base[:7]}..{head[:7]}, review clean)\n"
    (execution / "progress.md").write_text(progress, encoding="utf-8")
    (execution / "final-review.md").write_text(
        "```text\nVerdict: Changes Requested\n```\nVerdict: Approved\n",
        encoding="utf-8",
    )

    finalized = finalize_metrics(tmp_path, work_id, 3)
    retried = finalize_metrics(tmp_path, work_id, 3)

    assert finalized["result"] == "finalized"
    assert finalized["change_shape"] == "single_module_code"
    assert finalized["metrics_finalized"] is True
    assert retried["result"] == "already_finalized"
    parsed = parse_metrics((execution / "metrics.md").read_text(encoding="utf-8"))
    assert parsed.header["change_shape"] == "single_module_code"
    assert parsed.header["metrics_finalized"] is True


def test_finalize_metrics_rejects_incomplete_authoritative_state_without_rewriting(tmp_path):
    work_id, _, execution, _ = _started_metrics_run(tmp_path)
    before = (execution / "metrics.md").read_bytes()
    with pytest.raises(MetricsFormatError, match="progress|role sequence"):
        finalize_metrics(tmp_path, work_id, 0)
    assert (execution / "metrics.md").read_bytes() == before


@pytest.mark.parametrize("container", ("fence", "comment"))
@pytest.mark.parametrize("evidence_kind", ("checkbox", "marker"))
def test_finalize_rejects_nonsemantic_progress_evidence_without_rewriting(
    tmp_path, container, evidence_kind
):
    work_id, run_dir, execution, base = _started_metrics_run(tmp_path)
    _append_complete_metrics_sequence(tmp_path, work_id, execution)
    head = _commit_paths(tmp_path, ("src/semantic.py",))
    marker = f"Task 1: complete (commits {base[:7]}..{head[:7]}, review clean)"
    evidence = "- [x] PLAN-TASK-001 — task 1" if evidence_kind == "checkbox" else marker
    wrapped = f"```text\n{evidence}\n```" if container == "fence" else f"<!--\n{evidence}\n-->"
    progress_path = execution / "progress.md"
    replacement = wrapped if evidence_kind == "checkbox" else "- [x] PLAN-TASK-001 — task 1"
    progress = re.sub(
        r"^- \[ \] PLAN-TASK-001.*$", replacement,
        progress_path.read_text(encoding="utf-8"),
        flags=re.MULTILINE,
    )
    progress += f"\n{marker if evidence_kind == 'checkbox' else wrapped}\n"
    progress_path.write_text(progress, encoding="utf-8")
    (execution / "final-review.md").write_text("Verdict: Approved\n", encoding="utf-8")
    before = (execution / "metrics.md").read_bytes()

    assert check_execution_complete(run_dir).passed is (evidence_kind == "marker")
    with pytest.raises(MetricsFormatError, match="progress"):
        finalize_metrics(tmp_path, work_id, 3)

    assert (execution / "metrics.md").read_bytes() == before


def test_finalize_accepts_the_same_checked_row_shape_as_authoritative_gate(tmp_path):
    work_id, run_dir, execution, base = _started_metrics_run(tmp_path)
    _append_complete_metrics_sequence(tmp_path, work_id, execution)
    head = _commit_paths(tmp_path, ("src/semantic.py",))
    _record_authoritative_completion(
        execution,
        base,
        head,
        checked_row="  -  [X] PLAN-TASK-001 — task 1",
    )

    assert check_execution_complete(run_dir).passed is True
    assert finalize_metrics(tmp_path, work_id, 3)["result"] == "finalized"


@pytest.mark.parametrize("unchecked_inner_whitespace", ("", " ", "   "))
def test_finalize_rejects_authoritative_unchecked_duplicate_whitespace_without_rewriting(
    tmp_path, unchecked_inner_whitespace
):
    work_id, run_dir, execution, base = _started_metrics_run(tmp_path)
    _append_complete_metrics_sequence(tmp_path, work_id, execution)
    head = _commit_paths(tmp_path, ("src/stale-checkbox.py",))
    _record_authoritative_completion(execution, base, head)

    progress_path = execution / "progress.md"
    progress = progress_path.read_text(encoding="utf-8")
    progress += (
        f"- [{unchecked_inner_whitespace}] PLAN-TASK-001 — stale duplicate\n"
    )
    progress_path.write_text(progress, encoding="utf-8")
    (execution / "final-review.md").write_text("Verdict: Approved\n", encoding="utf-8")
    before = (execution / "metrics.md").read_bytes()

    assert check_execution_complete(run_dir).passed is False
    with pytest.raises(MetricsFormatError, match="progress"):
        finalize_metrics(tmp_path, work_id, 3)
    assert (execution / "metrics.md").read_bytes() == before


@pytest.mark.parametrize("verdict", ("Changes Requested", ""))
def test_finalize_rejects_nonapproved_or_missing_final_verdict_without_rewriting(
    tmp_path, verdict
):
    work_id, _, execution, base = _started_metrics_run(tmp_path)
    _append_complete_metrics_sequence(tmp_path, work_id, execution)
    head = _commit_paths(tmp_path, ("src/verdict.py",))
    _record_authoritative_completion(execution, base, head, verdict=verdict)
    before = (execution / "metrics.md").read_bytes()

    with pytest.raises(MetricsFormatError, match="final review"):
        finalize_metrics(tmp_path, work_id, 3)

    assert (execution / "metrics.md").read_bytes() == before


@pytest.mark.parametrize("evidence", ("missing", "blocked", "failed"))
def test_finalize_rejects_missing_blocked_or_failed_role_evidence_without_rewriting(
    tmp_path, evidence
):
    work_id, _, execution, base = _started_metrics_run(tmp_path)
    if evidence == "missing":
        for sequence, role, task, status in (
            (1, "implementer", 1, "complete"),
            (2, "task_reviewer", 1, "approved"),
        ):
            append_metrics_invocation(
                tmp_path,
                work_id,
                _structured_record(
                    execution,
                    expected_sequence=sequence,
                    role=role,
                    task=task,
                    status=status,
                ),
            )
        expected = 2
    elif evidence == "blocked":
        append_metrics_invocation(
            tmp_path,
            work_id,
            _structured_record(
                execution,
                expected_sequence=1,
                role="implementer",
                task=1,
                status="blocked",
            ),
        )
        expected = 1
    else:
        _append_complete_metrics_sequence(
            tmp_path, work_id, execution, failed_verification=True
        )
        expected = 3
    head = _commit_paths(tmp_path, (f"src/{evidence}.py",))
    _record_authoritative_completion(execution, base, head)
    before = (execution / "metrics.md").read_bytes()

    with pytest.raises(MetricsFormatError, match="role sequence|blocked|verification"):
        finalize_metrics(tmp_path, work_id, expected)

    assert (execution / "metrics.md").read_bytes() == before


def test_finalize_rejects_dirty_code_tree_without_rewriting(tmp_path):
    work_id, _, execution, base = _started_metrics_run(tmp_path)
    _append_complete_metrics_sequence(tmp_path, work_id, execution)
    head = _commit_paths(tmp_path, ("src/clean.py",))
    _record_authoritative_completion(execution, base, head)
    (tmp_path / "src" / "dirty.py").write_text("dirty = True\n", encoding="utf-8")
    before = (execution / "metrics.md").read_bytes()

    with pytest.raises(MetricsFormatError, match="worktree"):
        finalize_metrics(tmp_path, work_id, 3)

    assert (execution / "metrics.md").read_bytes() == before


@pytest.mark.parametrize("case", ("empty", "invalid"))
def test_finalize_rejects_empty_or_invalid_git_diff_without_rewriting(
    tmp_path, monkeypatch, case
):
    work_id, _, execution, base = _started_metrics_run(tmp_path)
    _append_complete_metrics_sequence(tmp_path, work_id, execution)
    if case == "empty":
        head = base
    else:
        head = _commit_paths(tmp_path, ("src/invalid.py",))
        original_run = subprocess.run

        def invalid_name_status(arguments, *args, **kwargs):
            if "diff" in arguments and "--name-status" in arguments:
                return subprocess.CompletedProcess(arguments, 0, stdout=b"Z\0src/invalid.py\0")
            return original_run(arguments, *args, **kwargs)

        monkeypatch.setattr(subprocess, "run", invalid_name_status)
    _record_authoritative_completion(execution, base, head)
    before = (execution / "metrics.md").read_bytes()

    with pytest.raises(MetricsFormatError, match="invalid git name-status"):
        finalize_metrics(tmp_path, work_id, 3)

    assert (execution / "metrics.md").read_bytes() == before


def test_finalize_rejects_stale_count_and_self_host_gap_without_rewriting(tmp_path):
    work_id, _, execution, base = _started_metrics_run(tmp_path)
    _append_complete_metrics_sequence(tmp_path, work_id, execution)
    head = _commit_paths(tmp_path, ("src/stale.py",))
    _record_authoritative_completion(execution, base, head)
    before = (execution / "metrics.md").read_bytes()
    with pytest.raises(MetricsFormatError, match="stale"):
        finalize_metrics(tmp_path, work_id, 2)
    assert (execution / "metrics.md").read_bytes() == before

    self_host_id, _, self_host_execution, _, _, _ = _bootstrap_ready_run(tmp_path / "self-host")
    bootstrap_self_hosted_metrics(tmp_path / "self-host", self_host_id, 2)
    self_host_before = (self_host_execution / "metrics.md").read_bytes()
    with pytest.raises(MetricsFormatError, match="progress"):
        finalize_metrics(tmp_path / "self-host", self_host_id, 0)
    assert (self_host_execution / "metrics.md").read_bytes() == self_host_before


def test_append_after_finalized_rejects_new_sequence_but_exact_retry_is_readable(tmp_path):
    work_id, _, execution, base = _started_metrics_run(tmp_path)
    _append_complete_metrics_sequence(tmp_path, work_id, execution)
    head = _commit_paths(tmp_path, ("src/finalized.py",))
    _record_authoritative_completion(execution, base, head)
    finalize_metrics(tmp_path, work_id, 3)
    before = (execution / "metrics.md").read_bytes()

    exact = _structured_record(
        execution,
        expected_sequence=3,
        role="final_reviewer",
        task="final",
        status="approved",
    )
    assert append_metrics_invocation(tmp_path, work_id, exact)["result"] == "already_applied"
    with pytest.raises(MetricsFormatError, match="after metrics finalization"):
        append_metrics_invocation(
            tmp_path,
            work_id,
            _structured_record(
                execution,
                expected_sequence=4,
                role="final_fixer",
                task="final",
                status="complete",
                fix_wave=1,
            ),
        )

    assert (execution / "metrics.md").read_bytes() == before


def test_append_and_finalize_share_one_nonblocking_lock(tmp_path):
    work_id, run_dir, execution, base = _started_metrics_run(tmp_path)
    append_request = _structured_record(
        execution,
        expected_sequence=1,
        role="implementer",
        task=1,
        status="complete",
    )
    lock_path = run_dir / "logs" / "metrics.lock"
    lock_path.parent.mkdir(exist_ok=True)
    before = (execution / "metrics.md").read_bytes()
    with lock_path.open("a+") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(MetricsFormatError, match="busy"):
            append_metrics_invocation(tmp_path, work_id, append_request)
        with pytest.raises(MetricsFormatError, match="busy"):
            finalize_metrics(tmp_path, work_id, 0)
        fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
    assert (execution / "metrics.md").read_bytes() == before


@pytest.mark.parametrize(
    ("shape", "paths"),
    (
        ("migration", ("migrations/001.sql",)),
        ("single_module_code", ("src/feature.py",)),
        ("cross_module_code", ("src/feature.py", "lib/helper.py")),
        ("docs_only", ("docs/guide.md",)),
        ("config_only", ("settings.yaml",)),
        ("test_only", ("tests/test_feature.py",)),
        ("mixed", ("docs/guide.md", "settings.yaml")),
    ),
)
def test_finalize_computes_every_supported_change_shape(tmp_path, shape, paths):
    work_id, _, execution, base = _started_metrics_run(tmp_path)
    _append_complete_metrics_sequence(tmp_path, work_id, execution)
    head = _commit_paths(tmp_path, paths)
    _record_authoritative_completion(execution, base, head)

    result = finalize_metrics(tmp_path, work_id, 3)

    assert result["change_shape"] == shape
    assert result["metrics_finalized"] is True


def test_isolated_opencode_install_executes_all_metrics_wrappers_to_finalized_state(tmp_path):
    from tools.workflow_cli.install import InstallService

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    work_id, _, execution, base = _started_metrics_run(workspace)
    manifest_root = tmp_path / "isolated-home"
    platform_root = tmp_path / "platforms"
    service = InstallService(
        repo_root=Path(__file__).resolve().parents[1],
        manifest_root=manifest_root,
        platform_homes={
            name: platform_root / name
            for name in ("claude", "codex", "gemini", "opencode")
        },
    )
    service.install("opencode")
    derived = (
        platform_root / "opencode" / "commands" / "r2p-execute.md"
    ).read_text(encoding="utf-8")
    assert "r2p-metrics-status" in derived
    assert "r2p-metrics-append" in derived
    assert "r2p-metrics-finalize" in derived
    assert "never emits ad-hoc" in derived
    assert "`## Role` prose" in derived

    environment = os.environ.copy()
    environment["R2P_JSON"] = "1"
    environment["PATH"] = (
        f"{Path(__file__).resolve().parents[1] / '.venv' / 'bin'}:"
        f"{environment.get('PATH', '')}"
    )

    def installed(name: str, *arguments: str) -> dict[str, object]:
        completed = subprocess.run(
            [str(manifest_root / "bin" / name), *arguments],
            cwd=workspace,
            env=environment,
            check=True,
            capture_output=True,
            text=True,
        )
        return json.loads(completed.stdout)

    assert installed("r2p-metrics-status", "--work-id", str(work_id))["next_sequence"] == 1
    for sequence, role, task, status in (
        (1, "implementer", 1, "complete"),
        (2, "task_reviewer", 1, "approved"),
        (3, "final_reviewer", "final", "approved"),
    ):
        result = installed(
            "r2p-metrics-append",
            "--work-id",
            str(work_id),
            "--record-json",
            json.dumps(
                _structured_record(
                    execution,
                    expected_sequence=sequence,
                    role=role,
                    task=task,
                    status=status,
                ),
                separators=(",", ":"),
            ),
        )
        assert result["result"] == "appended"
    head = _commit_paths(workspace, ("src/installed.py",))
    _record_authoritative_completion(execution, base, head)

    result = installed(
        "r2p-metrics-finalize",
        "--work-id",
        str(work_id),
        "--expected-invocation-count",
        "3",
    )

    assert result["result"] == "finalized"
    parsed = parse_metrics((execution / "metrics.md").read_text(encoding="utf-8"))
    assert parsed.header["metrics_finalized"] is True
    assert len(parsed.invocations) == 3


def test_metrics_wrappers_produce_archive_accepted_by_unchanged_sample_validator(tmp_path):
    from tools.workflow_cli.cli import main

    work_id, _, execution, base = _started_metrics_run(tmp_path)
    repo_root = Path(__file__).resolve().parents[1]
    environment = os.environ.copy()
    environment["PATH"] = f"{repo_root / '.venv' / 'bin'}:{environment.get('PATH', '')}"
    environment["R2P_JSON"] = "1"

    def wrapper(name: str, *arguments: str) -> dict[str, object]:
        completed = subprocess.run(
            [str(repo_root / "tools" / name), *arguments],
            cwd=tmp_path,
            env=environment,
            check=True,
            capture_output=True,
            text=True,
        )
        return json.loads(completed.stdout)

    status = wrapper("r2p-metrics-status", "--work-id", str(work_id))
    assert status["result"] == "status"
    assert status["next_sequence"] == 1
    for sequence, role, task, status in (
        (1, "implementer", 1, "complete"),
        (2, "task_reviewer", 1, "approved"),
        (3, "final_reviewer", "final", "approved"),
    ):
        appended = wrapper(
            "r2p-metrics-append",
            "--work-id",
            str(work_id),
            "--record-json",
            json.dumps(
                _structured_record(
                    execution,
                    expected_sequence=sequence,
                    role=role,
                    task=task,
                    status=status,
                ),
                ensure_ascii=False,
                separators=(",", ":"),
            ),
        )
        assert appended["result"] == "appended"
    source = tmp_path / "src" / "accepted.py"
    source.parent.mkdir()
    source.write_text("accepted = True\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(tmp_path), "add", "src/accepted.py"], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "commit", "-qm", "accepted"], check=True)
    head = subprocess.run(
        ["git", "-C", str(tmp_path), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    progress_path = execution / "progress.md"
    progress = progress_path.read_text(encoding="utf-8").replace(
        "- [ ] PLAN-TASK-001", "- [x] PLAN-TASK-001"
    )
    progress += f"\nTask 1: complete (commits {base[:7]}..{head[:7]}, review clean)\n"
    progress_path.write_text(progress, encoding="utf-8")
    (execution / "final-review.md").write_text("Verdict: Approved\n", encoding="utf-8")
    finalized = wrapper(
        "r2p-metrics-finalize",
        "--work-id",
        str(work_id),
        "--expected-invocation-count",
        "3",
    )
    assert finalized["result"] == "finalized"

    with pytest.raises(SystemExit) as archived:
        main(["--base-path", str(tmp_path), "run-archive", "--work-id", str(work_id)])
    assert archived.value.code == 0
    produced = tmp_path / ".req-to-plan" / "archive" / str(work_id)
    fixture_root = tmp_path / "independent-samples"
    two = _archived_sample(fixture_root, "WF-20260831-independent-two", 2, "single_module_code")
    three = _archived_sample(fixture_root, "WF-20260831-independent-three", 1, "docs_only")

    accepted = validate_representative_samples((produced, two, three))
    assert accepted["message"] == "representative_metrics_accepted"
    assert accepted["samples"][0]["metrics_finalized"] is True


def _bootstrap_ready_run(tmp_path: Path) -> tuple[WorkId, Path, Path, str, str, str]:
    work_id = WorkId("WF-20260829-r2p-execute-token-phase-r2p")
    run_dir = tmp_path / ".req-to-plan" / str(work_id)
    record = create_run_record(work_id)
    record.status = RunStatus.EXECUTING
    record.current_stage = Stage.CLOSED
    RunStateManager(run_dir).save(record)
    write_artifact(run_dir, Stage.PLAN, _plan(9), version=1, status="approved")
    base = _git_init(tmp_path)
    task_one = _commit(tmp_path, "task-one")
    task_two = _commit(tmp_path, "task-two")
    execution = run_dir / "execution"
    execution.mkdir()
    rows = [
        f"- [x] PLAN-TASK-{number:03d} task {number}"
        if number < 3 else f"- [ ] PLAN-TASK-{number:03d} task {number}"
        for number in range(1, 10)
    ]
    (execution / "progress.md").write_text("\n".join([
        "# Execution Progress", "", f"work_id: {work_id}", "", f"Execution BASE: {base}", "",
        *rows,
        f"Task 1: complete (commits {base[:7]}..{task_one[:7]}, review clean)",
        f"Task 2: complete (commits {task_one[:7]}..{task_two[:7]}, review clean)",
        "",
    ]), encoding="utf-8")
    return work_id, run_dir, execution, base, task_one, task_two


def test_quantize_elapsed_seconds_uses_monotonic_nanoseconds_and_half_up():
    assert quantize_elapsed_seconds(0, 499) == "0.000000"
    assert quantize_elapsed_seconds(0, 500) == "0.000001"
    assert quantize_elapsed_seconds(1_000_000_000, 1_000_001_500) == "0.000002"
    with pytest.raises(ValueError, match="monotonic"):
        quantize_elapsed_seconds(2, 1)


def test_parse_metrics_requires_the_canonical_header_and_block_grammar():
    text = """# Execution Metrics
work_id: WF-20260830-metrics-core
r2p_version: 0.7.11
instrumentation_schema: 1
profile: strict
task_count: 1
instrumentation_complete: true
bootstrap_gap: none
change_shape: unavailable
metrics_finalized: false

## Invocation 1
role: implementer
task: 1
model: unavailable
started_at: 2026-08-30T00:00:00.000000Z
ended_at: 2026-08-30T00:00:01.000000Z
elapsed_seconds: 1.000000
context_mode: direct_acs
context_bytes_kind: declared_payload_bytes
context_bytes: 0
verification_records_json: [{"command":"pytest","elapsed_seconds":"0.100000","reason":"targeted","scope":"targeted","status":"passed"}]
verification_total_seconds: 0.100000
report_bytes: 42
status: complete
concerns_json: []
fix_wave: 0
input_tokens: unavailable
output_tokens: unavailable
total_tokens: unavailable
"""
    metrics = parse_metrics(text)
    assert metrics.header["instrumentation_schema"] == INSTRUMENTATION_SCHEMA
    assert metrics.invocations[0]["verification_total_seconds"] == "0.100000"

    with pytest.raises(MetricsFormatError, match="canonical"):
        parse_metrics(text.replace("profile: strict", "profile: strict\nunknown: value"))
    with pytest.raises(MetricsFormatError, match="total_tokens"):
        parse_metrics(text.replace("total_tokens: unavailable", "total_tokens: 3"))


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        (b"M\0src/a.py\0", "single_module_code"),
        (b"M\0src/a.py\0M\0lib/b.py\0", "cross_module_code"),
        (b"A\0tests/test_a.py\0", "test_only"),
        (b"M\0docs/readme.md\0M\0tests/test_a.py\0", "docs_only"),
        (b"M\0settings.toml\0", "config_only"),
        (b"R100\0old.py\0new.py\0", "single_module_code"),
        (b"C099\0old.py\0migrations/new.py\0", "migration"),
        (b"M\0docs/a.md\0M\0settings.toml\0", "mixed"),
    ],
)
def test_classify_change_shape_uses_exact_nul_name_status_grammar(payload, expected):
    assert classify_change_shape(payload) == expected


@pytest.mark.parametrize("payload", [b"", b"R101\0a\0b\0", b"U\0a\0", b"M\0../a\0"])
def test_classify_change_shape_rejects_invalid_git_output(payload):
    with pytest.raises(ValueError):
        classify_change_shape(payload)


def test_start_execution_transaction_seeds_both_ledgers_once(tmp_path):
    work_id = WorkId("WF-20260830-start-metrics")
    run_dir = tmp_path / ".req-to-plan" / str(work_id)
    record = create_run_record(work_id)
    record.status = RunStatus.CLOSED_AT_PLAN_CHECKPOINT
    record.current_stage = Stage.CLOSED
    RunStateManager(run_dir).save(record)
    write_artifact(
        run_dir,
        Stage.PLAN,
        "### PLAN-TASK-001: metrics core\n\nFiles:\n- `new.py`\n",
        version=1,
        status="approved",
    )
    subprocess = pytest.importorskip("subprocess")
    completed = subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "config", "user.email", "test@example.invalid"], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "config", "user.name", "test"], check=True)
    (tmp_path / "seed").write_text("seed\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(tmp_path), "add", "seed"], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "commit", "-qm", "seed"], check=True)

    started = start_execution_transaction(tmp_path, work_id, "strict")

    assert started.status == RunStatus.EXECUTING
    metrics = parse_metrics((run_dir / "execution" / "metrics.md").read_text(encoding="utf-8"))
    assert metrics.header["task_count"] == 1
    assert "Execution BASE: " in (run_dir / "execution" / "progress.md").read_text(encoding="utf-8")
    assert start_execution_transaction(tmp_path, work_id, "strict").status == RunStatus.EXECUTING


def test_start_execution_transaction_recovers_an_executing_marker_without_rewriting_ledgers(tmp_path):
    work_id = WorkId("WF-20260830-marker-recovery")
    run_dir = tmp_path / ".req-to-plan" / str(work_id)
    record = create_run_record(work_id)
    record.status = RunStatus.CLOSED_AT_PLAN_CHECKPOINT
    record.current_stage = Stage.CLOSED
    RunStateManager(run_dir).save(record)
    write_artifact(run_dir, Stage.PLAN, "### PLAN-TASK-001: core\n", version=1, status="approved")
    subprocess = pytest.importorskip("subprocess")
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "config", "user.email", "test@example.invalid"], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "config", "user.name", "test"], check=True)
    (tmp_path / "seed").write_text("seed\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(tmp_path), "add", "seed"], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "commit", "-qm", "seed"], check=True)
    start_execution_transaction(tmp_path, work_id, "strict")
    progress_before = (run_dir / "execution" / "progress.md").read_text(encoding="utf-8")
    (run_dir / "execution" / ".start-transaction.json").write_text(
        json.dumps({"schema": 1, "work_id": str(work_id), "profile": "strict", "task_count": 1,
                    "execution_base": progress_before.split("Execution BASE: ")[1].splitlines()[0]},
        sort_keys=True, separators=(",", ":"),
    ) + "\n",
        encoding="utf-8",
    )

    recovered = start_execution_transaction(tmp_path, work_id, "strict")

    assert recovered.status == RunStatus.EXECUTING
    assert not (run_dir / "execution" / ".start-transaction.json").exists()
    assert (run_dir / "execution" / "progress.md").read_text(encoding="utf-8") == progress_before


def test_start_execution_transaction_rolls_back_owned_partial_and_retries(tmp_path, monkeypatch):
    work_id = WorkId("WF-20260830-start-rollback")
    run_dir = tmp_path / ".req-to-plan" / str(work_id)
    record = create_run_record(work_id)
    record.status = RunStatus.CLOSED_AT_PLAN_CHECKPOINT
    record.current_stage = Stage.CLOSED
    RunStateManager(run_dir).save(record)
    write_artifact(run_dir, Stage.PLAN, _plan(1), version=1, status="approved")
    _git_init(tmp_path)

    import tools.workflow_cli.execution_metrics as metrics_module

    original = metrics_module._write_new_text_at

    def fail_metrics(parent_fd, name, content):
        if name == "metrics.md":
            raise OSError("injected metrics write failure")
        return original(parent_fd, name, content)

    monkeypatch.setattr(metrics_module, "_write_new_text_at", fail_metrics)
    with pytest.raises(OSError, match="injected"):
        start_execution_transaction(tmp_path, work_id, "strict")

    assert not (run_dir / "execution").exists()
    assert RunStateManager(run_dir).load().status == RunStatus.CLOSED_AT_PLAN_CHECKPOINT

    monkeypatch.setattr(metrics_module, "_write_new_text_at", original)
    assert start_execution_transaction(tmp_path, work_id, "strict").status == RunStatus.EXECUTING


def test_prerequisite_v1_supports_later_strict_tasks(tmp_path):
    work_id = WorkId("WF-20260830-prerequisite-v1")
    run_dir = tmp_path / ".req-to-plan" / str(work_id)
    record = create_run_record(work_id)
    record.status = RunStatus.EXECUTING
    record.current_stage = Stage.CLOSED
    RunStateManager(run_dir).save(record)
    write_artifact(run_dir, Stage.PLAN, _plan(9), version=1, status="approved")
    base = _git_init(tmp_path)
    task_one = _commit(tmp_path, "task-one")
    task_two = _commit(tmp_path, "task-two")
    execution = run_dir / "execution"
    execution.mkdir()
    rows = [f"- [x] PLAN-TASK-{n:03d} task {n}" if n < 3 else f"- [ ] PLAN-TASK-{n:03d} task {n}" for n in range(1, 10)]
    progress = "\n".join([
        "# Execution Progress", "", f"work_id: {work_id}", "", f"Execution BASE: {base}", "",
        *rows,
        f"Task 1: complete (commits {base[:7]}..{task_one[:7]}, review clean)",
        f"Task 2: complete (commits {task_one[:7]}..{task_two[:7]}, review clean)",
        "",
    ])
    (execution / "progress.md").write_text(progress, encoding="utf-8")

    result = check_prerequisite_v1(tmp_path, work_id, 3)

    assert result["implementation_version"] == 1
    assert result["semantics_version"] == 1
    assert result["effective_profile"] == "strict"
    assert result["prerequisite"] == "PLAN-TASK-002"
    assert result["satisfied"] is True


def test_bootstrap_retry_accepts_complete_task_three_blocks(tmp_path):
    work_id = WorkId("WF-20260829-r2p-execute-token-phase-r2p")
    run_dir = tmp_path / ".req-to-plan" / str(work_id)
    record = create_run_record(work_id)
    record.status = RunStatus.EXECUTING
    record.current_stage = Stage.CLOSED
    RunStateManager(run_dir).save(record)
    write_artifact(run_dir, Stage.PLAN, _plan(9), version=1, status="approved")
    base = _git_init(tmp_path)
    task_one = _commit(tmp_path, "task-one")
    task_two = _commit(tmp_path, "task-two")
    execution = run_dir / "execution"
    execution.mkdir()
    rows = [f"- [x] PLAN-TASK-{n:03d} task {n}" if n < 3 else f"- [ ] PLAN-TASK-{n:03d} task {n}" for n in range(1, 10)]
    (execution / "progress.md").write_text("\n".join([
        "# Execution Progress", "", f"work_id: {work_id}", "", f"Execution BASE: {base}", "", *rows,
        f"Task 1: complete (commits {base[:7]}..{task_one[:7]}, review clean)",
        f"Task 2: complete (commits {task_one[:7]}..{task_two[:7]}, review clean)", "",
    ]), encoding="utf-8")

    first = bootstrap_self_hosted_metrics(tmp_path, work_id, 2)
    metrics_path = execution / "metrics.md"
    metrics_path.write_text(
        metrics_path.read_text(encoding="utf-8")
        + _invocation("implementer", 3, 1)
        + "\n"
        + _invocation("task_reviewer", 3, 2),
        encoding="utf-8",
    )
    progress_path = execution / "progress.md"
    progress = progress_path.read_text(encoding="utf-8").replace(
        "- [ ] PLAN-TASK-003 task 3",
        "- [x] PLAN-TASK-003 task 3",
    )
    progress += f"Task 3: complete (commits {task_two[:7]}..{task_two[:7]}, review clean)\n"
    progress_path.write_text(progress, encoding="utf-8")

    retried = bootstrap_self_hosted_metrics(tmp_path, work_id, 2)

    assert first.header == retried.header
    assert len(retried.invocations) == 2
    assert retried.invocations[0]["task"] == 3


def _archived_sample(root: Path, name: str, task_count: int, shape: str) -> Path:
    work_id = WorkId(name)
    run_dir = root / name
    record = create_run_record(work_id)
    record.status = RunStatus.ARCHIVED
    record.current_stage = Stage.CLOSED
    RunStateManager(run_dir).save(record)
    write_artifact(run_dir, Stage.PLAN, _plan(task_count), version=1, status="approved")
    execution = run_dir / "execution"
    execution.mkdir()
    progress = ["# Execution Progress", "", f"work_id: {work_id}", "", "Execution BASE: " + "a" * 40, ""]
    progress.extend(f"- [x] PLAN-TASK-{n:03d} task {n}" for n in range(1, task_count + 1))
    (execution / "progress.md").write_text("\n".join(progress) + "\n", encoding="utf-8")
    (execution / "final-review.md").write_text("Verdict: Approved\n", encoding="utf-8")
    header = "\n".join([
        "# Execution Metrics", f"work_id: {work_id}", "r2p_version: 0.7.11",
        "instrumentation_schema: 1", "profile: strict", f"task_count: {task_count}",
        "instrumentation_complete: true", "bootstrap_gap: none", f"change_shape: {shape}",
        "metrics_finalized: true", "",
    ])
    blocks = []
    sequence = 1
    for task in range(1, task_count + 1):
        blocks.append(_invocation("implementer", task, sequence))
        sequence += 1
        blocks.append(_invocation("task_reviewer", task, sequence))
        sequence += 1
    blocks.append(_invocation("final_reviewer", "final", sequence, context_mode="semantic_view"))
    (execution / "metrics.md").write_text(header + "\n".join(blocks), encoding="utf-8")
    return run_dir


def test_representative_samples_returns_exact_auditable_shape(tmp_path):
    one = _archived_sample(tmp_path, "WF-20260830-sample-one", 1, "single_module_code")
    two = _archived_sample(tmp_path, "WF-20260830-sample-two", 2, "single_module_code")
    three = _archived_sample(tmp_path, "WF-20260830-sample-three", 1, "docs_only")

    result = validate_representative_samples((one, two, three))

    assert set(result) == {"status", "message", "samples", "aggregate"}
    assert result["message"] == "representative_metrics_accepted"
    assert result["aggregate"] == {
        "sample_count": 3,
        "work_ids": ["WF-20260830-sample-one", "WF-20260830-sample-two", "WF-20260830-sample-three"],
        "task_counts": [1, 2],
        "change_shapes": ["docs_only", "single_module_code"],
        "task_count_diverse": True,
        "change_shape_diverse": True,
        "representative": True,
    }
    sample = result["samples"][0]
    assert set(sample) == {
        "path", "work_id", "r2p_version", "instrumentation_schema", "profile", "task_count",
        "change_shape", "instrumentation_complete", "bootstrap_gap", "metrics_finalized",
        "plan_complete", "final_verdict", "invocation_count", "role_counts",
        "role_elapsed_total_seconds", "verification_total_seconds", "report_bytes_total",
        "full_suite", "context_totals", "token_totals", "rules",
    }
    assert [item["rule"] for item in sample["rules"]] == [
        "path_safety", "identity_unique", "archived_strict", "instrumentation_complete",
        "plan_complete", "final_review_approved", "role_coverage", "measured_fields_complete",
        "metrics_totals_consistent",
    ]
    assert all(item == {"rule": item["rule"], "status": "passed", "details": []} for item in sample["rules"])
    assert sample["role_counts"] == {
        "implementer": 1, "task_reviewer": 1, "fixer": 0, "task_rereviewer": 0,
        "final_reviewer": 1, "final_fixer": 0, "final_rereviewer": 0,
    }
    assert sample["token_totals"] == {
        "status": "unavailable", "input_tokens": "unavailable",
        "output_tokens": "unavailable", "total_tokens": "unavailable",
    }


def test_parse_metrics_rejects_reversed_wall_clock_and_noncanonical_record_keys():
    text = """# Execution Metrics
work_id: WF-20260830-metrics-time
r2p_version: 0.7.11
instrumentation_schema: 1
profile: strict
task_count: 1
instrumentation_complete: true
bootstrap_gap: none
change_shape: unavailable
metrics_finalized: false

""" + _invocation("implementer", 1, 1)
    with pytest.raises(MetricsFormatError, match="ended_at"):
        parse_metrics(text.replace(
            "ended_at: 2026-08-30T00:00:01.000000Z",
            "ended_at: 2026-08-29T23:59:59.000000Z",
        ))
    with pytest.raises(MetricsFormatError, match="canonical|schema"):
        parse_metrics(text.replace(
            '"status":"passed"',
            '"extra":"x","status":"passed"',
        ))


def _closed_run(tmp_path: Path, work_name: str, tasks: int = 1) -> tuple[WorkId, Path]:
    work_id = WorkId(work_name)
    run_dir = tmp_path / ".req-to-plan" / str(work_id)
    record = create_run_record(work_id)
    record.status = RunStatus.CLOSED_AT_PLAN_CHECKPOINT
    record.current_stage = Stage.CLOSED
    RunStateManager(run_dir).save(record)
    write_artifact(run_dir, Stage.PLAN, _plan(tasks), version=1, status="approved")
    _git_init(tmp_path)
    return work_id, run_dir


def test_start_transaction_lock_contention_is_zero_mutation(tmp_path):
    work_id, run_dir = _closed_run(tmp_path, "WF-20260830-lock-contention")
    logs = run_dir / "logs"
    logs.mkdir()
    lock_fd = os.open(logs / "execute-start.lock", os.O_RDWR | os.O_CREAT, 0o600)
    fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    try:
        with pytest.raises(MetricsFormatError, match="busy"):
            start_execution_transaction(tmp_path, work_id, "strict")
        assert not (run_dir / "execution").exists()
        assert RunStateManager(run_dir).load().status == RunStatus.CLOSED_AT_PLAN_CHECKPOINT
    finally:
        os.close(lock_fd)


def test_start_transaction_preserves_foreign_residue_and_symlink(tmp_path):
    work_id, run_dir = _closed_run(tmp_path, "WF-20260830-foreign-residue")
    execution = run_dir / "execution"
    execution.mkdir()
    (execution / "foreign").write_text("do not delete\n", encoding="utf-8")
    with pytest.raises(MetricsFormatError, match="residue"):
        start_execution_transaction(tmp_path, work_id, "strict")
    assert (execution / "foreign").read_text(encoding="utf-8") == "do not delete\n"

    execution.rename(run_dir / "saved-execution")
    external = tmp_path / "external"
    external.mkdir()
    (run_dir / "execution").symlink_to(external, target_is_directory=True)
    with pytest.raises(MetricsFormatError, match="unsafe|missing"):
        start_execution_transaction(tmp_path, work_id, "strict")
    assert list(external.iterdir()) == []


def test_start_transaction_post_state_replace_failure_recovers_as_executing(tmp_path, monkeypatch):
    work_id, run_dir = _closed_run(tmp_path, "WF-20260830-post-state-save")
    import tools.workflow_cli.execution_metrics as metrics_module

    original = metrics_module._replace_text_at
    raised = False

    def replace_then_fail(parent_fd, name, content):
        nonlocal raised
        original(parent_fd, name, content)
        if name == "run.md" and not raised:
            raised = True
            raise metrics_module._CommittedWriteError("injected post-replace failure")

    monkeypatch.setattr(metrics_module, "_replace_text_at", replace_then_fail)
    with pytest.raises(OSError, match="injected"):
        start_execution_transaction(tmp_path, work_id, "strict")

    assert RunStateManager(run_dir).load().status == RunStatus.EXECUTING
    assert (run_dir / "execution" / ".start-transaction.json").is_file()
    assert (run_dir / "execution" / "progress.md").is_file()
    assert (run_dir / "execution" / "metrics.md").is_file()

    monkeypatch.setattr(metrics_module, "_replace_text_at", original)
    recovered = start_execution_transaction(tmp_path, work_id, "strict")
    assert recovered.status == RunStatus.EXECUTING
    assert not (run_dir / "execution" / ".start-transaction.json").exists()


def test_bootstrap_rejects_unsafe_existing_metrics_without_overwrite(tmp_path):
    work_id = WorkId("WF-20260829-r2p-execute-token-phase-r2p")
    run_dir = tmp_path / ".req-to-plan" / str(work_id)
    record = create_run_record(work_id)
    record.status = RunStatus.EXECUTING
    record.current_stage = Stage.CLOSED
    RunStateManager(run_dir).save(record)
    write_artifact(run_dir, Stage.PLAN, _plan(9), version=1, status="approved")
    base = _git_init(tmp_path)
    task_one = _commit(tmp_path, "task-one")
    task_two = _commit(tmp_path, "task-two")
    execution = run_dir / "execution"
    execution.mkdir()
    rows = [f"- [x] PLAN-TASK-{n:03d} task {n}" if n < 3 else f"- [ ] PLAN-TASK-{n:03d} task {n}" for n in range(1, 10)]
    (execution / "progress.md").write_text("\n".join([
        "# Execution Progress", "", f"work_id: {work_id}", "", f"Execution BASE: {base}", "", *rows,
        f"Task 1: complete (commits {base[:7]}..{task_one[:7]}, review clean)",
        f"Task 2: complete (commits {task_one[:7]}..{task_two[:7]}, review clean)", "",
    ]), encoding="utf-8")
    external = tmp_path / "external-metrics"
    external.write_text("foreign\n", encoding="utf-8")
    (execution / "metrics.md").symlink_to(external)

    with pytest.raises(MetricsFormatError, match="non-regular|unsafe"):
        bootstrap_self_hosted_metrics(tmp_path, work_id, 2)

    assert external.read_text(encoding="utf-8") == "foreign\n"
    assert (execution / "metrics.md").is_symlink()


def test_sample_validator_argument_duplicate_and_symlink_failures_are_stable(tmp_path):
    with pytest.raises(RepresentativeSamplesError) as count_error:
        validate_representative_samples(tuple())
    assert count_error.value.result == {
        "status": "error",
        "message": "BLOCKED: representative_metrics_missing",
        "exit_code": 3,
        "details": [{
            "sample_dir": "invocation", "work_id": "unavailable", "rule": "argument_count",
            "message": "expected 3 sample dirs, observed 0",
        }],
    }

    one = _archived_sample(tmp_path, "WF-20260830-duplicate-one", 1, "docs_only")
    two = _archived_sample(tmp_path, "WF-20260830-duplicate-two", 2, "single_module_code")
    with pytest.raises(RepresentativeSamplesError) as duplicate_error:
        validate_representative_samples((one, one, two))
    duplicate = duplicate_error.value.result["details"]
    assert duplicate == [{
        "sample_dir": str(one), "work_id": "WF-20260830-duplicate-one",
        "rule": "identity_unique", "message": "canonical sample path/work ID is duplicated",
    }]

    link = tmp_path / "WF-20260830-symlink-sample"
    link.symlink_to(one, target_is_directory=True)
    with pytest.raises(RepresentativeSamplesError) as symlink_error:
        validate_representative_samples((link, one, two))
    detail = symlink_error.value.result["details"][0]
    assert detail["sample_dir"] == str(link)
    assert detail["rule"] == "path_safety"
    assert "# Execution Metrics" not in detail["message"]


def test_prerequisite_v1_rejects_fast_only_state(tmp_path):
    work_id = WorkId("WF-20260830-prerequisite-fast")
    run_dir = tmp_path / ".req-to-plan" / str(work_id)
    record = create_run_record(work_id)
    record.status = RunStatus.EXECUTING
    record.current_stage = Stage.CLOSED
    RunStateManager(run_dir).save(record)
    write_artifact(run_dir, Stage.PLAN, _plan(2), version=1, status="approved")
    base = _git_init(tmp_path)
    execution = run_dir / "execution"
    execution.mkdir()
    (execution / "progress.md").write_text("\n".join([
        "# Execution Progress", "", f"work_id: {work_id}", "", f"Execution BASE: {base}", "",
        "Execution Profile: fast", "", "- [ ] PLAN-TASK-001 task 1", "- [ ] PLAN-TASK-002 task 2", "",
    ]), encoding="utf-8")
    with pytest.raises(PrerequisiteError, match="strict"):
        check_prerequisite_v1(tmp_path, work_id, 1)


def test_representative_samples_reject_metrics_header_for_another_work_id(tmp_path):
    one = _archived_sample(tmp_path, "WF-20260830-identity-one", 1, "single_module_code")
    two = _archived_sample(tmp_path, "WF-20260830-identity-two", 2, "single_module_code")
    three = _archived_sample(tmp_path, "WF-20260830-identity-three", 1, "docs_only")
    metrics_path = one / "execution" / "metrics.md"
    metrics_path.write_text(
        metrics_path.read_text(encoding="utf-8").replace(
            "work_id: WF-20260830-identity-one",
            "work_id: WF-20260830-identity-two",
            1,
        ),
        encoding="utf-8",
    )

    with pytest.raises(RepresentativeSamplesError) as error:
        validate_representative_samples((one, two, three))

    assert error.value.result["details"] == [{
        "sample_dir": str(one),
        "work_id": "WF-20260830-identity-one",
        "rule": "identity_unique",
        "message": "metrics work_id does not match the pinned sample identity",
    }]
    assert "# Execution Metrics" not in error.value.result["details"][0]["message"]


def test_bootstrap_retry_rejects_skipped_task_invocation(tmp_path):
    work_id, _, execution, _, _, _ = _bootstrap_ready_run(tmp_path)
    bootstrap_self_hosted_metrics(tmp_path, work_id, 2)
    metrics_path = execution / "metrics.md"
    metrics_path.write_text(
        metrics_path.read_text(encoding="utf-8") + _invocation("implementer", 4, 1),
        encoding="utf-8",
    )

    with pytest.raises(MetricsFormatError, match="progress|Task 003|state"):
        bootstrap_self_hosted_metrics(tmp_path, work_id, 2)


def test_bootstrap_retry_accepts_contiguous_complete_then_active_task(tmp_path):
    work_id, _, execution, _, _, task_two = _bootstrap_ready_run(tmp_path)
    bootstrap_self_hosted_metrics(tmp_path, work_id, 2)
    metrics_path = execution / "metrics.md"
    metrics_path.write_text(
        metrics_path.read_text(encoding="utf-8")
        + _invocation("implementer", 3, 1)
        + "\n"
        + _invocation("task_reviewer", 3, 2)
        + "\n"
        + _invocation("implementer", 4, 3),
        encoding="utf-8",
    )
    progress_path = execution / "progress.md"
    progress = progress_path.read_text(encoding="utf-8").replace(
        "- [ ] PLAN-TASK-003 task 3",
        "- [x] PLAN-TASK-003 task 3",
    )
    progress += f"Task 3: complete (commits {task_two[:7]}..{task_two[:7]}, review clean)\n"
    progress_path.write_text(progress, encoding="utf-8")

    parsed = bootstrap_self_hosted_metrics(tmp_path, work_id, 2)

    assert [item["task"] for item in parsed.invocations] == [3, 3, 4]


def test_bootstrap_retry_rejects_out_of_order_task_groups(tmp_path):
    work_id, _, execution, _, _, task_two = _bootstrap_ready_run(tmp_path)
    bootstrap_self_hosted_metrics(tmp_path, work_id, 2)
    metrics_path = execution / "metrics.md"
    metrics_path.write_text(
        metrics_path.read_text(encoding="utf-8")
        + _invocation("implementer", 3, 1)
        + "\n"
        + _invocation("task_reviewer", 3, 2)
        + "\n"
        + _invocation("implementer", 4, 3)
        + "\n"
        + _invocation("implementer", 3, 4),
        encoding="utf-8",
    )
    progress_path = execution / "progress.md"
    progress = progress_path.read_text(encoding="utf-8").replace(
        "- [ ] PLAN-TASK-003 task 3",
        "- [x] PLAN-TASK-003 task 3",
    )
    progress += f"Task 3: complete (commits {task_two[:7]}..{task_two[:7]}, review clean)\n"
    progress_path.write_text(progress, encoding="utf-8")

    with pytest.raises(MetricsFormatError, match="ordered|frontier"):
        bootstrap_self_hosted_metrics(tmp_path, work_id, 2)


@pytest.mark.parametrize("replacement", ["regular", "symlink"])
def test_bootstrap_rejects_pre_link_temp_replacement(tmp_path, monkeypatch, replacement):
    work_id, _, execution, _, _, _ = _bootstrap_ready_run(tmp_path)
    import tools.workflow_cli.execution_metrics as metrics_module

    original_link = metrics_module.os.link

    def replace_source_then_link(src, dst, *, src_dir_fd, dst_dir_fd, follow_symlinks):
        metrics_module.os.unlink(src, dir_fd=src_dir_fd)
        if replacement == "regular":
            fd = metrics_module.os.open(
                src,
                metrics_module.os.O_WRONLY | metrics_module.os.O_CREAT | metrics_module.os.O_EXCL,
                0o600,
                dir_fd=src_dir_fd,
            )
            try:
                metrics_module.os.write(fd, b"foreign\n")
            finally:
                metrics_module.os.close(fd)
        else:
            metrics_module.os.symlink("foreign-target", src, dir_fd=src_dir_fd)
        return original_link(
            src,
            dst,
            src_dir_fd=src_dir_fd,
            dst_dir_fd=dst_dir_fd,
            follow_symlinks=follow_symlinks,
        )

    monkeypatch.setattr(metrics_module.os, "link", replace_source_then_link)

    with pytest.raises(MetricsFormatError, match="identity"):
        bootstrap_self_hosted_metrics(tmp_path, work_id, 2)

    assert (execution / "metrics.md").exists() or (execution / "metrics.md").is_symlink()


def test_bootstrap_rejects_post_link_final_name_replacement(tmp_path, monkeypatch):
    work_id, _, execution, _, _, _ = _bootstrap_ready_run(tmp_path)
    import tools.workflow_cli.execution_metrics as metrics_module

    original_link = metrics_module.os.link

    def replace_final_after_link(src, dst, *, src_dir_fd, dst_dir_fd, follow_symlinks):
        original_link(
            src,
            dst,
            src_dir_fd=src_dir_fd,
            dst_dir_fd=dst_dir_fd,
            follow_symlinks=follow_symlinks,
        )
        metrics_module.os.unlink(dst, dir_fd=dst_dir_fd)
        fd = metrics_module.os.open(
            dst,
            metrics_module.os.O_WRONLY | metrics_module.os.O_CREAT | metrics_module.os.O_EXCL,
            0o600,
            dir_fd=dst_dir_fd,
        )
        try:
            metrics_module.os.write(fd, b"foreign\n")
        finally:
            metrics_module.os.close(fd)

    monkeypatch.setattr(metrics_module.os, "link", replace_final_after_link)

    with pytest.raises(MetricsFormatError, match="identity"):
        bootstrap_self_hosted_metrics(tmp_path, work_id, 2)

    assert (execution / "metrics.md").read_text(encoding="utf-8") == "foreign\n"


def test_bootstrap_eexist_exact_publish_is_idempotent_and_retains_abandoned_temp(tmp_path, monkeypatch):
    work_id, _, execution, _, _, _ = _bootstrap_ready_run(tmp_path)
    import tools.workflow_cli.execution_metrics as metrics_module

    original_link = metrics_module.os.link

    def publish_then_report_eexist(src, dst, *, src_dir_fd, dst_dir_fd, follow_symlinks):
        original_link(
            src,
            dst,
            src_dir_fd=src_dir_fd,
            dst_dir_fd=dst_dir_fd,
            follow_symlinks=follow_symlinks,
        )
        raise FileExistsError(errno.EEXIST, "injected concurrent exact publish")

    monkeypatch.setattr(metrics_module.os, "link", publish_then_report_eexist)

    parsed = bootstrap_self_hosted_metrics(tmp_path, work_id, 2)

    assert parsed.header["work_id"] == str(work_id)
    assert (execution / "metrics.md").is_file()
    assert len(list(execution.glob(".metrics-bootstrap.*.tmp"))) == 1


@pytest.mark.parametrize("directory_fsync_call", [1, 2])
def test_bootstrap_directory_fsync_crash_retries_from_exact_final(
    tmp_path,
    monkeypatch,
    directory_fsync_call,
):
    work_id, _, execution, _, _, _ = _bootstrap_ready_run(tmp_path)
    import tools.workflow_cli.execution_metrics as metrics_module

    original_fsync = metrics_module.os.fsync
    observed = 0

    def fail_selected_directory_fsync(fd):
        nonlocal observed
        if stat.S_ISDIR(metrics_module.os.fstat(fd).st_mode) and (execution / "metrics.md").exists():
            observed += 1
            if observed == directory_fsync_call:
                raise OSError("injected directory fsync failure")
        return original_fsync(fd)

    monkeypatch.setattr(metrics_module.os, "fsync", fail_selected_directory_fsync)
    with pytest.raises(OSError, match="directory fsync"):
        bootstrap_self_hosted_metrics(tmp_path, work_id, 2)

    monkeypatch.setattr(metrics_module.os, "fsync", original_fsync)
    parsed = bootstrap_self_hosted_metrics(tmp_path, work_id, 2)
    assert parsed.header["work_id"] == str(work_id)


def test_bootstrap_temp_cleanup_crash_retries_without_deleting_final(tmp_path, monkeypatch):
    work_id, _, execution, _, _, _ = _bootstrap_ready_run(tmp_path)
    import tools.workflow_cli.execution_metrics as metrics_module

    original_unlink = metrics_module.os.unlink
    injected = False

    def fail_published_temp_cleanup(path, *, dir_fd=None):
        nonlocal injected
        if (
            not injected
            and isinstance(path, str)
            and path.startswith(".metrics-bootstrap.")
            and (execution / "metrics.md").exists()
        ):
            injected = True
            raise OSError("injected temp cleanup failure")
        return original_unlink(path, dir_fd=dir_fd)

    monkeypatch.setattr(metrics_module.os, "unlink", fail_published_temp_cleanup)
    with pytest.raises(OSError, match="temp cleanup"):
        bootstrap_self_hosted_metrics(tmp_path, work_id, 2)

    monkeypatch.setattr(metrics_module.os, "unlink", original_unlink)
    parsed = bootstrap_self_hosted_metrics(tmp_path, work_id, 2)
    assert parsed.header["work_id"] == str(work_id)
    assert len(list(execution.glob(".metrics-bootstrap.*.tmp"))) == 1


def test_executing_start_rejects_metrics_for_another_work_id_without_mutation(tmp_path):
    work_id, run_dir = _closed_run(tmp_path, "WF-20260830-start-identity")
    start_execution_transaction(tmp_path, work_id, "strict")
    execution = run_dir / "execution"
    metrics_path = execution / "metrics.md"
    progress_path = execution / "progress.md"
    metrics_path.write_text(
        metrics_path.read_text(encoding="utf-8").replace(
            f"work_id: {work_id}",
            "work_id: WF-20260830-foreign-identity",
            1,
        ),
        encoding="utf-8",
    )
    metrics_before = metrics_path.read_bytes()
    progress_before = progress_path.read_bytes()
    run_before = (run_dir / "run.md").read_bytes()

    with pytest.raises(MetricsFormatError, match="work_id|identity"):
        start_execution_transaction(tmp_path, work_id, "strict")

    assert metrics_path.read_bytes() == metrics_before
    assert progress_path.read_bytes() == progress_before
    assert (run_dir / "run.md").read_bytes() == run_before
    assert RunStateManager(run_dir).load().status == RunStatus.EXECUTING


@pytest.mark.parametrize("artifact_name", ["task-1-report.md", "task-1-review.md"])
def test_sample_validator_rejects_fix_wave_evidence_without_role_blocks(tmp_path, artifact_name):
    one = _archived_sample(tmp_path, "WF-20260830-wave-one", 1, "single_module_code")
    two = _archived_sample(tmp_path, "WF-20260830-wave-two", 2, "single_module_code")
    three = _archived_sample(tmp_path, "WF-20260830-wave-three", 1, "docs_only")
    (one / "execution" / artifact_name).write_text(
        "# Task 1 Report\n\n## Fix Wave 1\n\nsecret diagnostic body\n",
        encoding="utf-8",
    )

    with pytest.raises(RepresentativeSamplesError) as error:
        validate_representative_samples((one, two, three))

    assert error.value.result["details"] == [{
        "sample_dir": str(one),
        "work_id": "WF-20260830-wave-one",
        "rule": "role_coverage",
        "message": "persistent role/fix-wave evidence is missing matching metrics blocks",
    }]
    assert "secret diagnostic body" not in json.dumps(error.value.result)


def test_sample_validator_accepts_matching_report_review_fix_wave_blocks(tmp_path):
    one = _archived_sample(tmp_path, "WF-20260830-wave-match-one", 1, "single_module_code")
    two = _archived_sample(tmp_path, "WF-20260830-wave-match-two", 2, "single_module_code")
    three = _archived_sample(tmp_path, "WF-20260830-wave-match-three", 1, "docs_only")
    execution = one / "execution"
    (execution / "task-1-report.md").write_text(
        "# Task 1 Report\n\n## Fix Wave 1\n",
        encoding="utf-8",
    )
    (execution / "task-1-review.md").write_text(
        "# Task 1 Review\n\n## Fix Wave 1\n",
        encoding="utf-8",
    )
    metrics_path = execution / "metrics.md"
    metrics = metrics_path.read_text(encoding="utf-8")
    metrics_path.write_text(
        metrics.replace(
            _invocation("final_reviewer", "final", 3, context_mode="semantic_view"),
            _invocation("fixer", 1, 3, fix_wave=1)
            + "\n"
            + _invocation("task_rereviewer", 1, 4, fix_wave=1)
            + "\n"
            + _invocation("final_reviewer", "final", 5, context_mode="semantic_view"),
        ),
        encoding="utf-8",
    )

    result = validate_representative_samples((one, two, three))

    assert result["samples"][0]["role_counts"]["fixer"] == 1
    assert result["samples"][0]["role_counts"]["task_rereviewer"] == 1


@pytest.mark.parametrize(
    ("final_review", "approved"),
    [
        ("Verdict: Approved\n", True),
        ("Verdict: approved\n", True),
        ("Verdict: APPROVED\n", True),
        ("Verdict: aPpRoVeD\n", True),
        ("```text\nVerdict: Approved\n```\n", False),
        ("<!-- Verdict: Approved -->\n", False),
        ("Verdict: Approved\nVerdict: Changes Requested\n", False),
        ("Verdict: Changes Requested\nVerdict: approved\n", True),
    ],
    ids=(
        "title-case",
        "lower-case",
        "upper-case",
        "mixed-case",
        "fenced-only",
        "commented-only",
        "last-unfenced-rejects",
        "last-unfenced-approves",
    ),
)
def test_sample_verdict_matches_finalization_and_archive_semantics(
    tmp_path,
    final_review,
    approved,
):
    one = _archived_sample(tmp_path, "WF-20260831-verdict-one", 1, "single_module_code")
    two = _archived_sample(tmp_path, "WF-20260831-verdict-two", 2, "single_module_code")
    three = _archived_sample(tmp_path, "WF-20260831-verdict-three", 1, "docs_only")
    (one / "execution" / "final-review.md").write_text(final_review, encoding="utf-8")

    assert check_final_review_recorded(one).passed is approved
    if approved:
        result = validate_representative_samples((one, two, three))
        assert result["samples"][0]["final_verdict"] == "Approved"
    else:
        with pytest.raises(RepresentativeSamplesError) as sample_error:
            validate_representative_samples((one, two, three))
        assert sample_error.value.result["details"] == [{
            "sample_dir": str(one),
            "work_id": "WF-20260831-verdict-one",
            "rule": "final_review_approved",
            "message": "last final-review verdict is not Approved",
        }]

    live = tmp_path / "live"
    live.mkdir()
    work_id, _, execution, base = _started_metrics_run(live)
    _append_complete_metrics_sequence(live, work_id, execution)
    head = _commit_paths(live, ("src/verdict-parity.py",))
    _record_authoritative_completion(execution, base, head)
    (execution / "final-review.md").write_text(final_review, encoding="utf-8")
    if approved:
        assert finalize_metrics(live, work_id, 3)["result"] == "finalized"
    else:
        with pytest.raises(MetricsFormatError, match="final review"):
            finalize_metrics(live, work_id, 3)


def _replace_one_task_final_role_chain(
    execution: Path,
    role_specs: tuple[tuple[str, int, str], ...],
) -> None:
    metrics_path = execution / "metrics.md"
    prefix = metrics_path.read_text(encoding="utf-8").split("## Invocation 3", 1)[0]
    blocks = []
    for sequence, (role, wave, status_value) in enumerate(role_specs, start=3):
        block = _invocation(
            role,
            "final",
            sequence,
            context_mode="semantic_view",
            fix_wave=wave,
        )
        automatic_status = "approved" if "reviewer" in role else "complete"
        blocks.append(
            block.replace(f"status: {automatic_status}", f"status: {status_value}")
        )
    metrics_path.write_text(prefix + "\n".join(blocks), encoding="utf-8")


def test_sample_final_summary_task_fix_wave_does_not_require_final_roles(tmp_path):
    one = _archived_sample(tmp_path, "WF-20260831-final-summary-one", 1, "single_module_code")
    two = _archived_sample(tmp_path, "WF-20260831-final-summary-two", 2, "single_module_code")
    three = _archived_sample(tmp_path, "WF-20260831-final-summary-three", 1, "docs_only")
    (one / "execution" / "final-review.md").write_text(
        "Reviewed PLAN-TASK-001..005 + fix wave 1.\nVerdict: Approved\n",
        encoding="utf-8",
    )

    result = validate_representative_samples((one, two, three))

    assert result["samples"][0]["role_counts"]["final_fixer"] == 0
    assert result["samples"][0]["role_counts"]["final_rereviewer"] == 0


def test_sample_explicit_final_fix_wave_requires_matching_final_roles(tmp_path):
    one = _archived_sample(tmp_path, "WF-20260831-final-wave-one", 1, "single_module_code")
    two = _archived_sample(tmp_path, "WF-20260831-final-wave-two", 2, "single_module_code")
    three = _archived_sample(tmp_path, "WF-20260831-final-wave-three", 1, "docs_only")
    (one / "execution" / "final-review.md").write_text(
        "Final Fix Wave: 1\nVerdict: Approved\n",
        encoding="utf-8",
    )

    with pytest.raises(RepresentativeSamplesError) as error:
        validate_representative_samples((one, two, three))

    assert error.value.result["details"] == [{
        "sample_dir": str(one),
        "work_id": "WF-20260831-final-wave-one",
        "rule": "role_coverage",
        "message": "persistent role/fix-wave evidence is missing matching metrics blocks",
    }]


def test_sample_explicit_final_fix_wave_accepts_matching_final_roles(tmp_path):
    one = _archived_sample(tmp_path, "WF-20260831-final-pair-one", 1, "single_module_code")
    two = _archived_sample(tmp_path, "WF-20260831-final-pair-two", 2, "single_module_code")
    three = _archived_sample(tmp_path, "WF-20260831-final-pair-three", 1, "docs_only")
    execution = one / "execution"
    (execution / "final-review.md").write_text(
        "Final Fix Wave: 1\nVerdict: Approved\n",
        encoding="utf-8",
    )
    _replace_one_task_final_role_chain(execution, (
        ("final_reviewer", 0, "changes_requested"),
        ("final_fixer", 1, "complete"),
        ("final_rereviewer", 1, "approved"),
    ))

    result = validate_representative_samples((one, two, three))

    assert result["samples"][0]["role_counts"]["final_fixer"] == 1
    assert result["samples"][0]["role_counts"]["final_rereviewer"] == 1


@pytest.mark.parametrize(
    "non_evidence",
    (
        "Final Fix Waves: none\n",
        "Summary: task fix wave 1 completed.\n",
        "Summary: final fix wave 1 completed.\n",
        "```text\nFinal Fix Wave: 1\n```\n",
        "<!-- Final Fix Wave: 1 -->\n",
    ),
)
def test_sample_ignores_noncanonical_final_fix_wave_evidence(tmp_path, non_evidence):
    one = _archived_sample(tmp_path, "WF-20260831-final-none-one", 1, "single_module_code")
    two = _archived_sample(tmp_path, "WF-20260831-final-none-two", 2, "single_module_code")
    three = _archived_sample(tmp_path, "WF-20260831-final-none-three", 1, "docs_only")
    (one / "execution" / "final-review.md").write_text(
        non_evidence + "Verdict: Approved\n",
        encoding="utf-8",
    )

    assert validate_representative_samples((one, two, three))["status"] == "ok"


@pytest.mark.parametrize("covered_waves", ((1,), (1, 2)))
def test_sample_multiple_explicit_final_fix_waves_require_exact_coverage(
    tmp_path,
    covered_waves,
):
    one = _archived_sample(tmp_path, "WF-20260831-final-multi-one", 1, "single_module_code")
    two = _archived_sample(tmp_path, "WF-20260831-final-multi-two", 2, "single_module_code")
    three = _archived_sample(tmp_path, "WF-20260831-final-multi-three", 1, "docs_only")
    execution = one / "execution"
    (execution / "final-review.md").write_text(
        "Final Fix Wave: 1\nFinal Fix Wave: 2\nVerdict: Approved\n",
        encoding="utf-8",
    )
    role_specs = [("final_reviewer", 0, "changes_requested")]
    for index, wave in enumerate(covered_waves):
        role_specs.extend((
            ("final_fixer", wave, "complete"),
            (
                "final_rereviewer",
                wave,
                "approved" if index == len(covered_waves) - 1 else "changes_requested",
            ),
        ))
    _replace_one_task_final_role_chain(execution, tuple(role_specs))

    if covered_waves == (1, 2):
        assert validate_representative_samples((one, two, three))["status"] == "ok"
    else:
        with pytest.raises(RepresentativeSamplesError) as error:
            validate_representative_samples((one, two, three))
        assert error.value.result["details"][0]["rule"] == "role_coverage"


@pytest.mark.parametrize(
    "wrapped_evidence",
    (
        "```text\nFix Wave 1\n```\n",
        "<!-- Fix Wave 1 -->\n",
    ),
)
@pytest.mark.parametrize("artifact_name", ("task-1-report.md", "task-1-review.md"))
def test_sample_ignores_fenced_or_commented_task_fix_wave_evidence(
    tmp_path,
    artifact_name,
    wrapped_evidence,
):
    one = _archived_sample(tmp_path, "WF-20260831-task-wrap-one", 1, "single_module_code")
    two = _archived_sample(tmp_path, "WF-20260831-task-wrap-two", 2, "single_module_code")
    three = _archived_sample(tmp_path, "WF-20260831-task-wrap-three", 1, "docs_only")
    (one / "execution" / artifact_name).write_text(wrapped_evidence, encoding="utf-8")

    assert validate_representative_samples((one, two, three))["status"] == "ok"


@pytest.mark.parametrize("unsafe_kind", ["symlink", "fifo"])
def test_sample_validator_rejects_unsafe_report_without_leaking_body(tmp_path, unsafe_kind):
    one = _archived_sample(tmp_path, "WF-20260830-report-link-one", 1, "single_module_code")
    two = _archived_sample(tmp_path, "WF-20260830-report-link-two", 2, "single_module_code")
    three = _archived_sample(tmp_path, "WF-20260830-report-link-three", 1, "docs_only")
    report = one / "execution" / "task-1-report.md"
    if unsafe_kind == "symlink":
        external = tmp_path / "secret-report"
        external.write_text("do-not-leak-this-report-body\n", encoding="utf-8")
        report.symlink_to(external)
    else:
        os.mkfifo(report)

    with pytest.raises(RepresentativeSamplesError) as error:
        validate_representative_samples((one, two, three))

    detail = error.value.result["details"][0]
    assert detail["rule"] == "path_safety"
    assert "do-not-leak-this-report-body" not in json.dumps(error.value.result)


@pytest.mark.parametrize(
    ("failed_name", "slug"),
    [(".start-transaction.json", "marker"), ("progress.md", "progress")],
)
def test_start_transaction_write_failure_removes_owned_partial(tmp_path, monkeypatch, failed_name, slug):
    work_id, run_dir = _closed_run(tmp_path, f"WF-20260830-write-failure-{slug}")
    import tools.workflow_cli.execution_metrics as metrics_module

    original = metrics_module._write_new_text_at

    def fail_selected_write(parent_fd, name, content):
        if name == failed_name:
            raise OSError(f"injected {failed_name} write failure")
        return original(parent_fd, name, content)

    monkeypatch.setattr(metrics_module, "_write_new_text_at", fail_selected_write)
    with pytest.raises(OSError, match="injected"):
        start_execution_transaction(tmp_path, work_id, "strict")

    assert not (run_dir / "execution").exists()
    assert RunStateManager(run_dir).load().status == RunStatus.CLOSED_AT_PLAN_CHECKPOINT


def test_start_transaction_preserves_preexisting_empty_execution_directory(tmp_path):
    work_id, run_dir = _closed_run(tmp_path, "WF-20260830-empty-execution")
    execution = run_dir / "execution"
    execution.mkdir()

    with pytest.raises(MetricsFormatError, match="residue"):
        start_execution_transaction(tmp_path, work_id, "strict")

    assert execution.is_dir()
    assert list(execution.iterdir()) == []
    assert RunStateManager(run_dir).load().status == RunStatus.CLOSED_AT_PLAN_CHECKPOINT


def test_start_transaction_marker_cleanup_failure_recovers_without_rewriting_ledgers(tmp_path, monkeypatch):
    work_id, run_dir = _closed_run(tmp_path, "WF-20260830-marker-cleanup")
    import tools.workflow_cli.execution_metrics as metrics_module

    original_unlink = metrics_module.os.unlink
    injected = False

    def fail_marker_cleanup(path, *, dir_fd=None):
        nonlocal injected
        if path == ".start-transaction.json" and not injected:
            injected = True
            raise OSError("injected marker cleanup failure")
        return original_unlink(path, dir_fd=dir_fd)

    monkeypatch.setattr(metrics_module.os, "unlink", fail_marker_cleanup)
    with pytest.raises(OSError, match="marker cleanup"):
        start_execution_transaction(tmp_path, work_id, "strict")

    execution = run_dir / "execution"
    progress_before = (execution / "progress.md").read_bytes()
    metrics_before = (execution / "metrics.md").read_bytes()
    assert RunStateManager(run_dir).load().status == RunStatus.EXECUTING
    assert (execution / ".start-transaction.json").is_file()

    monkeypatch.setattr(metrics_module.os, "unlink", original_unlink)
    assert start_execution_transaction(tmp_path, work_id, "strict").status == RunStatus.EXECUTING
    assert (execution / "progress.md").read_bytes() == progress_before
    assert (execution / "metrics.md").read_bytes() == metrics_before
    assert not (execution / ".start-transaction.json").exists()


def test_start_transaction_rebuilds_closed_owned_marker_partial(tmp_path):
    work_id, run_dir = _closed_run(tmp_path, "WF-20260830-owned-rebuild")
    execution = run_dir / "execution"
    execution.mkdir()
    head = subprocess.run(
        ["git", "-C", str(tmp_path), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    marker = {
        "schema": 1,
        "work_id": str(work_id),
        "profile": "strict",
        "task_count": 1,
        "execution_base": head,
    }
    (execution / ".start-transaction.json").write_text(
        json.dumps(marker, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    (execution / "progress.md").write_text("owned partial\n", encoding="utf-8")

    result = start_execution_transaction(tmp_path, work_id, "strict")

    assert result.status == RunStatus.EXECUTING
    assert not (execution / ".start-transaction.json").exists()
    assert "Execution Profile: strict" in (execution / "progress.md").read_text(encoding="utf-8")
    assert parse_metrics((execution / "metrics.md").read_text(encoding="utf-8")).header["work_id"] == str(work_id)


@pytest.mark.parametrize(
    ("blocked_role", "task", "fix_wave", "completed_status"),
    [
        ("implementer", 1, 0, "complete"),
        ("task_reviewer", 1, 0, "changes_requested"),
        ("fixer", 1, 1, "complete"),
        ("task_rereviewer", 1, 1, "approved"),
        ("final_reviewer", "final", 0, "changes_requested"),
        ("final_fixer", "final", 1, "complete"),
        ("final_rereviewer", "final", 1, "approved"),
    ],
)
def test_sample_validator_rejects_blocked_role_in_completed_fix_chain(
    tmp_path,
    blocked_role,
    task,
    fix_wave,
    completed_status,
):
    one = _archived_sample(tmp_path, "WF-20260830-blocked-one", 1, "single_module_code")
    two = _archived_sample(tmp_path, "WF-20260830-blocked-two", 2, "single_module_code")
    three = _archived_sample(tmp_path, "WF-20260830-blocked-three", 1, "docs_only")
    metrics_path = one / "execution" / "metrics.md"
    header = metrics_path.read_text(encoding="utf-8").split("## Invocation 1", 1)[0]
    role_specs = [
        ("implementer", 1, 0, "complete"),
        ("task_reviewer", 1, 0, "changes_requested"),
        ("fixer", 1, 1, "complete"),
        ("task_rereviewer", 1, 1, "approved"),
        ("final_reviewer", "final", 0, "changes_requested"),
        ("final_fixer", "final", 1, "complete"),
        ("final_rereviewer", "final", 1, "approved"),
    ]
    blocks = []
    for sequence, (role, role_task, wave, status_value) in enumerate(role_specs, start=1):
        block = _invocation(
            role,
            role_task,
            sequence,
            context_mode="semantic_view" if role.startswith("final_") else "direct_acs",
            fix_wave=wave,
        )
        automatic_status = "approved" if "reviewer" in role else "complete"
        block = block.replace(f"status: {automatic_status}", f"status: {status_value}")
        if (role, role_task, wave, status_value) == (
            blocked_role,
            task,
            fix_wave,
            completed_status,
        ):
            block = block.replace(f"status: {status_value}", "status: blocked")
        blocks.append(block)
    metrics_path.write_text(header + "\n".join(blocks), encoding="utf-8")

    with pytest.raises(RepresentativeSamplesError) as error:
        validate_representative_samples((one, two, three))

    assert error.value.result["details"] == [{
        "sample_dir": str(one),
        "work_id": "WF-20260830-blocked-one",
        "rule": "role_coverage",
        "message": "required role invocation did not complete successfully",
    }]


def test_start_transaction_missing_directory_fd_capability_is_zero_mutation(tmp_path, monkeypatch):
    work_id, run_dir = _closed_run(tmp_path, "WF-20260830-missing-dir-fd")
    run_before = (run_dir / "run.md").read_bytes()
    import tools.workflow_cli.execution_metrics as metrics_module

    monkeypatch.setattr(metrics_module.os, "supports_dir_fd", set())

    with pytest.raises(MetricsFormatError, match="capability unavailable"):
        start_execution_transaction(tmp_path, work_id, "strict")

    assert (run_dir / "run.md").read_bytes() == run_before
    assert not (run_dir / "execution").exists()
    assert RunStateManager(run_dir).load().status == RunStatus.CLOSED_AT_PLAN_CHECKPOINT


def test_start_transaction_concurrent_execution_mkdir_collision_preserves_residue(
    tmp_path,
    monkeypatch,
):
    work_id, run_dir = _closed_run(tmp_path, "WF-20260830-concurrent-execution-dir")
    run_before = (run_dir / "run.md").read_bytes()
    import tools.workflow_cli.execution_metrics as metrics_module

    original_mkdir = metrics_module.os.mkdir

    def create_execution_then_collide(path, mode=0o777, *, dir_fd=None):
        if path == "execution":
            original_mkdir(path, mode, dir_fd=dir_fd)
            raise FileExistsError(errno.EEXIST, "injected concurrent execution directory")
        return original_mkdir(path, mode, dir_fd=dir_fd)

    monkeypatch.setattr(metrics_module.os, "mkdir", create_execution_then_collide)

    with pytest.raises(FileExistsError, match="concurrent execution directory"):
        start_execution_transaction(tmp_path, work_id, "strict")

    execution = run_dir / "execution"
    assert execution.is_dir()
    assert list(execution.iterdir()) == []
    assert (run_dir / "run.md").read_bytes() == run_before
    assert RunStateManager(run_dir).load().status == RunStatus.CLOSED_AT_PLAN_CHECKPOINT

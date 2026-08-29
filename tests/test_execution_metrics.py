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
    PrerequisiteError,
    RepresentativeSamplesError,
    bootstrap_self_hosted_metrics,
    check_prerequisite_v1,
    classify_change_shape,
    parse_metrics,
    quantize_elapsed_seconds,
    start_execution_transaction,
    validate_representative_samples,
)
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

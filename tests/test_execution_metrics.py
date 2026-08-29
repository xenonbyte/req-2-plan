"""Direct contracts for the Phase 0 metrics core."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.workflow_cli.execution_metrics import (
    INSTRUMENTATION_SCHEMA,
    MetricsFormatError,
    classify_change_shape,
    parse_metrics,
    quantize_elapsed_seconds,
    start_execution_transaction,
)
from tools.workflow_cli.artifact import write_artifact
from tools.workflow_cli.models import RunStatus, Stage, WorkId
from tools.workflow_cli.state import RunStateManager, create_run_record


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
        separators=(",", ":"),
    ) + "\n",
        encoding="utf-8",
    )

    recovered = start_execution_transaction(tmp_path, work_id, "strict")

    assert recovered.status == RunStatus.EXECUTING
    assert not (run_dir / "execution" / ".start-transaction.json").exists()
    assert (run_dir / "execution" / "progress.md").read_text(encoding="utf-8") == progress_before

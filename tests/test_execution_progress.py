"""Real commit / role / acknowledgment recovery journeys."""
from pathlib import Path
import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile

import pytest

from tests.test_execution_metrics import (
    _commit_paths, _started_metrics_run, _structured_record,
)
from tools.workflow_cli.execution_metrics import (
    MetricsFormatError, acknowledge_metrics_completion, append_metrics_invocation, check_prerequisite,
    finalize_metrics, parse_metrics, read_metrics_status,
)
from tools.workflow_cli.execution_profile import parse_execution_ledger
from tools.workflow_cli.execution_profile import ExecutionProfileError
from tools.workflow_cli.execution_progress import (
    record_execution_progress, resume_execution_progress,
)


@pytest.fixture
def workspace():
    with tempfile.TemporaryDirectory() as temporary:
        yield Path(temporary).resolve()


def begin(root, work_id):
    state = resume_execution_progress(root, work_id)
    return record_execution_progress(
        root, work_id, "begin", state["role_sequence"],
    )


def finish(root, work_id, execution, dispatch, status, head, *, reason=None, red=False):
    sequence = read_metrics_status(root, work_id)["next_sequence"]
    observation = _structured_record(
        execution, expected_sequence=sequence, role=dispatch["next_role"],
        task=dispatch["task"], status=status, fix_wave=dispatch["fix_wave"],
    )
    if dispatch["fix_wave"]:
        report = Path(observation["report_path"])
        report.write_text(report.read_text() + f"\nFix Wave {dispatch['fix_wave']}\n")
    if red:
        observation["verification_records"].insert(0, dict(
            observation["verification_records"][0], status="failed", reason="TDD red",
        ))
    if dispatch["task"] == "final":
        verdict = "Approved" if status == "approved" else "Changes Requested"
        (execution / "final-review.md").write_text(f"Verdict: {verdict}\n")
    result = record_execution_progress(
        root, work_id, "complete", dispatch["role_sequence"],
        status=status, head=head, reason=reason,
    )
    append_metrics_invocation(root, work_id, observation)
    acknowledge_metrics_completion(root, work_id, sequence)
    return result


def test_strict_resume_after_implementer_ack_dispatches_review(workspace):
    work_id, _, execution, base = _started_metrics_run(workspace)
    dispatch = begin(workspace, work_id)
    head = _commit_paths(workspace, ("src/task.py",))
    finish(workspace, work_id, execution, dispatch, "complete", head)
    assert read_metrics_status(workspace, work_id)["pending_completion"] is None
    resumed = resume_execution_progress(workspace, work_id)
    assert resumed["next_role"] == "task_reviewer"
    assert resumed["review_ranges"] == [{"base": base, "head": head}]
    assert begin(workspace, work_id)["next_role"] == "task_reviewer"


def test_fast_upgrade_then_next_strict_implementer_can_ack(workspace):
    work_id, _, execution, base = _started_metrics_run(workspace, task_count=2, profile="fast")
    dispatch = begin(workspace, work_id)
    first = _commit_paths(workspace, ("src/one.py",))
    state = finish(workspace, work_id, execution, dispatch, "complete", first, reason="concern")
    assert state["effective_profile"] == "strict"
    finish(workspace, work_id, execution, begin(workspace, work_id), "approved", first)
    assert check_prerequisite(workspace, work_id, 2, require_version=2)["satisfied"]
    dispatch = begin(workspace, work_id)
    second = _commit_paths(workspace, ("src/two.py",))
    finish(workspace, work_id, execution, dispatch, "complete", second)
    assert resume_execution_progress(workspace, work_id)["next_role"] == "task_reviewer"


def test_fast_recovery_keeps_task_ranges_and_separate_repair_commits(workspace):
    work_id, _, execution, base = _started_metrics_run(workspace, task_count=3, profile="fast")
    dispatch = begin(workspace, work_id)
    first = _commit_paths(workspace, ("src/one.py",))
    finish(workspace, work_id, execution, dispatch, "complete", first)
    dispatch = begin(workspace, work_id)
    second = _commit_paths(workspace, ("src/two.py",))
    finish(workspace, work_id, execution, dispatch, "complete", second, reason="review concern")
    review = begin(workspace, work_id)
    assert review["task"] == 1
    assert review["review_ranges"] == [{"base": base, "head": first}]
    finish(workspace, work_id, execution, review, "changes_requested", second)
    fixer = begin(workspace, work_id)
    repaired = _commit_paths(workspace, ("src/one-fix.py",))
    finish(workspace, work_id, execution, fixer, "complete", repaired)
    rereview = begin(workspace, work_id)
    assert rereview["review_ranges"] == [
        {"base": base, "head": first}, {"base": second, "head": repaired},
    ]
    finish(workspace, work_id, execution, rereview, "approved", repaired)
    review_two = begin(workspace, work_id)
    assert review_two["task"] == 2
    assert review_two["review_ranges"] == [{"base": first, "head": second}]
    finish(workspace, work_id, execution, review_two, "approved", repaired)
    assert check_prerequisite(workspace, work_id, 3, require_version=2)["satisfied"]
    assert begin(workspace, work_id)["next_role"] == "implementer"


def test_fast_final_findings_can_upgrade_and_finish_strict(workspace):
    work_id, _, execution, _ = _started_metrics_run(workspace, profile="fast")
    dispatch = begin(workspace, work_id)
    head = _commit_paths(workspace, ("src/task.py",))
    finish(workspace, work_id, execution, dispatch, "complete", head)
    final = begin(workspace, work_id)
    assert final["next_role"] == "final_reviewer"
    finish(workspace, work_id, execution, final, "changes_requested", head, reason="final concern")
    assert begin(workspace, work_id)["next_role"] == "task_reviewer"
    dispatch = resume_execution_progress(workspace, work_id)
    finish(workspace, work_id, execution, dispatch, "approved", head)
    finish(workspace, work_id, execution, begin(workspace, work_id), "approved", head)
    assert finalize_metrics(workspace, work_id, 4)["metrics_finalized"]


def test_blocked_retry_and_tdd_red_remain_in_finalized_observations(workspace):
    work_id, _, execution, base = _started_metrics_run(workspace)
    finish(workspace, work_id, execution, begin(workspace, work_id), "blocked", base)
    dispatch = begin(workspace, work_id)
    assert dispatch["next_role"] == "implementer"
    head = _commit_paths(workspace, ("src/task.py",))
    finish(workspace, work_id, execution, dispatch, "complete", head, red=True)
    finish(workspace, work_id, execution, begin(workspace, work_id), "approved", head)
    finish(workspace, work_id, execution, begin(workspace, work_id), "approved", head)
    assert finalize_metrics(workspace, work_id, 4)["metrics_finalized"]
    invocations = parse_metrics((execution / "metrics.md").read_text()).invocations
    assert invocations[0]["status"] == "blocked"
    assert invocations[1]["verification_records"][0]["status"] == "failed"


def test_inflight_commit_recovers_result_without_redispatch(workspace):
    work_id, _, execution, _ = _started_metrics_run(workspace)
    dispatch = begin(workspace, work_id)
    head = _commit_paths(workspace, ("src/task.py",))
    resumed = resume_execution_progress(workspace, work_id)
    assert resumed["result"] == "recover_role_result"
    assert resumed["role_sequence"] == dispatch["role_sequence"]
    finish(workspace, work_id, execution, resumed, "complete", head)
    progress = (execution / "progress.md").read_bytes()
    record_execution_progress(workspace, work_id, "complete", dispatch["role_sequence"], status="complete", head=head)
    assert (execution / "progress.md").read_bytes() == progress


def test_legacy_committed_report_adopts_review_without_metrics_dependency(workspace):
    work_id, _, execution, base = _started_metrics_run(workspace)
    head = _commit_paths(workspace, ("src/legacy.py",))
    (execution / "task-1-report.md").write_text(f"## Status\nDONE\n\n## Commit Range\n{base[:7]}..{head[:7]}\n")
    state = record_execution_progress(workspace, work_id, "recover", 1, status="complete", head=head)
    assert state["next_role"] == "task_reviewer"
    assert state["review_ranges"] == [{"base": base, "head": head}]


def test_final_fix_preserves_original_task_range_and_finishes(workspace):
    work_id, _, execution, base = _started_metrics_run(workspace)
    dispatch = begin(workspace, work_id)
    head = _commit_paths(workspace, ("src/task.py",))
    finish(workspace, work_id, execution, dispatch, "complete", head)
    finish(workspace, work_id, execution, begin(workspace, work_id), "approved", head)
    finish(workspace, work_id, execution, begin(workspace, work_id), "changes_requested", head)
    fixer = begin(workspace, work_id)
    fixed = _commit_paths(workspace, ("src/final-fix.py",))
    finish(workspace, work_id, execution, fixer, "complete", fixed)
    finish(workspace, work_id, execution, begin(workspace, work_id), "approved", fixed)
    parsed = parse_execution_ledger((execution / "progress.md").read_text(), ("PLAN-TASK-001",))
    assert parsed.marker_for(1).head == head[:7]
    assert resume_execution_progress(workspace, work_id)["next_role"] is None
    assert finalize_metrics(workspace, work_id, 5)["metrics_finalized"]


def test_strict_v1_next_task_uses_journal_tail_after_task_fix(workspace):
    work_id, _, execution, _ = _started_metrics_run(workspace, task_count=2)
    dispatch = begin(workspace, work_id)
    head = _commit_paths(workspace, ("src/task.py",))
    finish(workspace, work_id, execution, dispatch, "complete", head)
    finish(workspace, work_id, execution, begin(workspace, work_id), "changes_requested", head)
    fixer = begin(workspace, work_id)
    fixed = _commit_paths(workspace, ("src/fix.py",))
    finish(workspace, work_id, execution, fixer, "complete", fixed)
    finish(workspace, work_id, execution, begin(workspace, work_id), "approved", fixed)
    assert check_prerequisite(workspace, work_id, 2, require_version=1)["satisfied"]
    assert begin(workspace, work_id)["task"] == 2


@pytest.mark.parametrize("mutation", ["missing_report", "conflicting_head", "stale_sequence", "symlink_report", "reviewer_commit"])
def test_progress_rejects_unsafe_completion_without_mutation(workspace, mutation):
    work_id, _, execution, base = _started_metrics_run(workspace)
    dispatch = begin(workspace, work_id)
    head = _commit_paths(workspace, ("src/task.py",))
    if mutation == "reviewer_commit":
        finish(workspace, work_id, execution, dispatch, "complete", head)
        dispatch = begin(workspace, work_id)
        head = _commit_paths(workspace, ("src/reviewer-change.py",))
    report = Path(dispatch["report_path"])
    if mutation == "symlink_report":
        report.symlink_to(workspace / "seed")
    elif mutation != "missing_report":
        report.write_text("report\n")
    before = (execution / "progress.md").read_bytes()
    with pytest.raises((ExecutionProfileError, ValueError, OSError)):
        record_execution_progress(
            workspace, work_id, "complete", dispatch["role_sequence"] + (mutation == "stale_sequence"),
            status="approved" if mutation == "reviewer_commit" else "complete",
            head=base if mutation == "conflicting_head" else head,
        )
    assert (execution / "progress.md").read_bytes() == before


@pytest.mark.parametrize("label", ["Gap", "Unresolved"])
def test_later_task_reraised_concern_blocks_until_a_new_semantic_resolution(workspace, label):
    work_id, _, execution, _ = _started_metrics_run(workspace, task_count=2)
    path = execution / "progress.md"
    for task in (1, 2):
        dispatch = begin(workspace, work_id)
        head = _commit_paths(workspace, (f"src/task{task}.py",))
        finish(workspace, work_id, execution, dispatch, "complete", head)
        review = begin(workspace, work_id)
        if task == 1:
            path.write_text(path.read_text() + "\nGap: repeated concern\nResolved: repeated concern\n")
            finish(workspace, work_id, execution, review, "approved", head)
    path.write_text(
        path.read_text() + f"\n{label}: repeated concern\n"
        "```text\nResolved: repeated concern\n```\n"
        "<!--\nResolved: repeated concern\n-->\n"
        "## Project Context (read-only)\n# Copied heading\n"
        "Resolved: repeated concern\n<!-- /r2p-read-only -->\n"
    )
    Path(review["report_path"]).write_text("Approved\n")
    before = path.read_bytes()
    with pytest.raises(ExecutionProfileError, match="unresolved task review concerns"):
        record_execution_progress(workspace, work_id, "complete", review["role_sequence"], status="approved", head=head)
    assert path.read_bytes() == before
    path.write_text(path.read_text() + "\nResolved: repeated concern\n")
    result = record_execution_progress(workspace, work_id, "complete", review["role_sequence"], status="approved", head=head)
    assert result["next_role"] == "final_reviewer"


def test_resume_and_exact_retry_revalidate_after_head_changes(workspace):
    work_id, _, execution, _ = _started_metrics_run(workspace)
    dispatch = begin(workspace, work_id)
    head = _commit_paths(workspace, ("src/task.py",))
    finish(workspace, work_id, execution, dispatch, "complete", head)
    before = (execution / "progress.md").read_bytes()
    _commit_paths(workspace, ("src/unrecorded.py",))
    with pytest.raises(ExecutionProfileError, match="recorded ledger boundary"):
        resume_execution_progress(workspace, work_id)
    with pytest.raises(ExecutionProfileError, match="recorded ledger boundary"):
        record_execution_progress(workspace, work_id, "complete", dispatch["role_sequence"], status="complete", head=head)
    assert (execution / "progress.md").read_bytes() == before


@pytest.mark.parametrize("ending", ["\r\n", *"\n\r\v\f\x1c\x1d\x1e\x85\u2028\u2029"])
def test_strict_completion_preserves_readonly_splitlines_boundaries(workspace, ending):
    work_id, _, execution, _ = _started_metrics_run(workspace)
    progress = execution / "progress.md"
    readonly = (
        f"## Project Context (read-only){ending}Copied context α{ending}"
        f"<!-- /r2p-read-only -->{ending}"
    )
    before = progress.read_bytes().decode("utf-8")
    position = before.index("- [ ] PLAN-TASK-001")
    progress.write_bytes((before[:position] + readonly + before[position:]).encode("utf-8"))
    dispatch = begin(workspace, work_id)
    head = _commit_paths(workspace, ("src/task.py",))
    finish(workspace, work_id, execution, dispatch, "complete", head)
    result = finish(workspace, work_id, execution, begin(workspace, work_id), "approved", head)
    after = progress.read_bytes()
    assert readonly.encode("utf-8") in after
    assert b"- [x] PLAN-TASK-001" in after
    assert result["next_role"] == "final_reviewer"


def test_completion_atomic_failure_and_exact_retry(workspace, monkeypatch):
    import tools.workflow_cli.execution_progress as progress_module
    work_id, _, execution, _ = _started_metrics_run(workspace)
    dispatch = begin(workspace, work_id)
    head = _commit_paths(workspace, ("src/task.py",))
    (execution / "task-1-report.md").write_text("report\n")
    before = (execution / "progress.md").read_bytes()
    real_replace = progress_module._replace_text_at
    def fail_before_replace(*args):
        raise OSError("injected progress write failure")
    with monkeypatch.context() as scoped:
        scoped.setattr(progress_module, "_replace_text_at", fail_before_replace)
        with pytest.raises(OSError):
            record_execution_progress(workspace, work_id, "complete", 1, status="complete", head=head)
    assert (execution / "progress.md").read_bytes() == before
    def replace_then_fail(*args):
        real_replace(*args)
        raise OSError("injected crash after replace")
    with monkeypatch.context() as scoped:
        scoped.setattr(progress_module, "_replace_text_at", replace_then_fail)
        with pytest.raises(OSError):
            record_execution_progress(workspace, work_id, "complete", 1, status="complete", head=head)
    after = (execution / "progress.md").read_bytes()
    record_execution_progress(workspace, work_id, "complete", 1, status="complete", head=head)
    assert (execution / "progress.md").read_bytes() == after


@pytest.mark.parametrize(
    ("operation", "expected_checks"),
    [("resume", 1), ("begin", 2), ("complete", 2), ("retry", 1)],
)
def test_progress_validates_each_required_boundary_once(
    workspace, monkeypatch, operation, expected_checks
):
    import tools.workflow_cli.execution_progress as progress_module
    work_id, _, execution, _ = _started_metrics_run(workspace)
    if operation in {"complete", "retry"}:
        begin(workspace, work_id)
        head = _commit_paths(workspace, ("src/task.py",))
        (execution / "task-1-report.md").write_text("report\n")
        if operation == "retry":
            record_execution_progress(workspace, work_id, "complete", 1, status="complete", head=head)
    real_validate = progress_module.validate_ledger_commit_chain
    checks = []

    def counted_validate(*args, **kwargs):
        checks.append(kwargs["current_head"])
        return real_validate(*args, **kwargs)

    monkeypatch.setattr(progress_module, "validate_ledger_commit_chain", counted_validate)
    if operation == "resume":
        result = resume_execution_progress(workspace, work_id)
    elif operation == "begin":
        result = record_execution_progress(workspace, work_id, "begin", 1)
    else:
        result = record_execution_progress(workspace, work_id, "complete", 1, status="complete", head=head)
    assert len(checks) == expected_checks
    assert result["next_role"] == ("task_reviewer" if operation in {"complete", "retry"} else "implementer")


def test_late_strict_begin_bounds_git_subprocess_cost(workspace, monkeypatch):
    work_id, _, execution, _ = _started_metrics_run(workspace, task_count=9)
    for task in range(1, 10):
        dispatch = begin(workspace, work_id)
        head = _commit_paths(workspace, (f"src/task{task}.py",))
        Path(dispatch["report_path"]).write_text("report\n")
        record_execution_progress(workspace, work_id, "complete", dispatch["role_sequence"], status="complete", head=head)
        review = begin(workspace, work_id)
        Path(review["report_path"]).write_text("Approved\n")
        record_execution_progress(workspace, work_id, "complete", review["role_sequence"], status="approved", head=head)
    real_run = subprocess.run
    git_commands = []

    def counted_run(command, *args, **kwargs):
        if command[0] == "git":
            git_commands.append(command)
        return real_run(command, *args, **kwargs)

    monkeypatch.setattr(subprocess, "run", counted_run)
    dispatch = record_execution_progress(workspace, work_id, "begin", 19)
    assert dispatch["next_role"] == "final_reviewer"
    assert dispatch["inflight"]
    assert len(git_commands) <= 81


def test_resume_shortcut_survives_missing_observation_file(workspace, monkeypatch):
    from tools.workflow_cli import agent_shortcuts
    work_id, _, execution, _ = _started_metrics_run(workspace)
    dispatch = begin(workspace, work_id)
    head = _commit_paths(workspace, ("src/task.py",))
    finish(workspace, work_id, execution, dispatch, "complete", head)
    (execution / "metrics.md").unlink()
    monkeypatch.setenv("R2P_JSON", "1")
    output = io.StringIO()
    with contextlib.redirect_stdout(output), pytest.raises(SystemExit) as done:
        agent_shortcuts.main(["execute", "--work-id", str(work_id)], base_path=workspace)
    assert done.value.code == 0
    payload = json.loads(output.getvalue())
    assert payload["next_role"] == "task_reviewer"
    assert payload["role_sequence"] == 2


def test_installed_progress_wrapper_and_execute_resume_contract(workspace):
    from tools.workflow_cli.install import InstallService
    root = workspace / "project"
    root.mkdir()
    work_id, _, execution, _ = _started_metrics_run(root)
    home = workspace / "isolated-home"
    service = InstallService(
        repo_root=Path(__file__).resolve().parents[1], manifest_root=home,
        platform_homes={name: workspace / "platforms" / name for name in ("claude", "codex", "gemini", "opencode")},
    )
    service.install("opencode")
    environment = dict(os.environ, R2P_JSON="1", PATH=str(Path(sys.executable).parent) + os.pathsep + os.environ.get("PATH", ""))
    wrapper = home / "bin" / "r2p-progress"
    def invoke(*args):
        result = subprocess.run([str(wrapper), *args], cwd=root, env=environment, text=True, capture_output=True)
        assert result.returncode == 0, result.stdout + result.stderr
        return json.loads(result.stdout)
    started = invoke("begin", "--work-id", str(work_id), "--expected-sequence", "1")
    assert started["next_role"] == "implementer"
    head = _commit_paths(root, ("src/task.py",))
    (execution / "task-1-report.md").write_text("report\n")
    completed = invoke("complete", "--work-id", str(work_id), "--expected-sequence", "1", "--status", "complete", "--head", head)
    assert completed["next_role"] == "task_reviewer"
    assert "r2p-progress" in (workspace / "platforms/opencode/commands/r2p-execute.md").read_text()


@pytest.mark.parametrize("profile", ["strict", "fast"])
def test_clean_completion_and_final_red_retry(workspace, profile):
    work_id, _, execution, _ = _started_metrics_run(workspace, profile=profile)
    dispatch = begin(workspace, work_id)
    head = _commit_paths(workspace, ("src/task.py",))
    finish(workspace, work_id, execution, dispatch, "complete", head)
    if profile == "strict":
        finish(workspace, work_id, execution, begin(workspace, work_id), "approved", head)
    finish(workspace, work_id, execution, begin(workspace, work_id), "approved", head, red=True)
    assert resume_execution_progress(workspace, work_id)["next_role"] is None
    assert finalize_metrics(workspace, work_id, 3 if profile == "strict" else 2)["metrics_finalized"]


def test_missing_observation_blocks_finalization_but_not_completion_or_archive(workspace):
    from tools.workflow_cli import agent_shortcuts
    work_id, _, execution, base = _started_metrics_run(workspace)
    dispatch = begin(workspace, work_id)
    (execution / "task-1-report.md").write_text("BLOCKED: missing context\n")
    record_execution_progress(workspace, work_id, "complete", dispatch["role_sequence"], status="blocked", head=base)
    # Simulate losing this blocked invocation's observation after durable progress.
    dispatch = begin(workspace, work_id)
    head = _commit_paths(workspace, ("src/task.py",))
    finish(workspace, work_id, execution, dispatch, "complete", head)
    finish(workspace, work_id, execution, begin(workspace, work_id), "approved", head)
    finish(workspace, work_id, execution, begin(workspace, work_id), "approved", head)
    before = (execution / "metrics.md").read_bytes()
    with pytest.raises(MetricsFormatError, match="metrics_incomplete"):
        finalize_metrics(workspace, work_id, 3)
    assert (execution / "metrics.md").read_bytes() == before
    assert resume_execution_progress(workspace, work_id)["next_role"] is None
    with pytest.raises(SystemExit) as done:
        agent_shortcuts.main(["archive", "--work-id", str(work_id)], base_path=workspace)
    assert done.value.code == 0
    assert (workspace / ".req-to-plan/archive" / str(work_id) / "execution/metrics.md").read_bytes() == before


@pytest.mark.parametrize("mutation", ["foreign", "duplicate", "missing"])
def test_progress_rejects_invalid_embedded_work_id(workspace, mutation):
    work_id, _, execution, _ = _started_metrics_run(workspace)
    path = execution / "progress.md"
    content = path.read_text()
    if mutation == "foreign":
        content = content.replace(str(work_id), "WF-20260905-unrelated")
    elif mutation == "duplicate":
        content += f"\nwork_id: {work_id}\n"
    else:
        content = content.replace(f"work_id: {work_id}", "")
    path.write_text(content)
    with pytest.raises(ExecutionProfileError, match="work_id"):
        record_execution_progress(workspace, work_id, "begin", 1)
    assert path.read_text() == content


def test_progress_lock_contention_and_release(workspace):
    import fcntl
    work_id, run_dir, execution, _ = _started_metrics_run(workspace)
    lock = run_dir / "logs/progress.lock"
    lock.parent.mkdir(exist_ok=True)
    before = (execution / "progress.md").read_bytes()
    with lock.open("w") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(MetricsFormatError, match="busy"):
            record_execution_progress(workspace, work_id, "begin", 1)
        assert (execution / "progress.md").read_bytes() == before
    assert begin(workspace, work_id)["next_role"] == "implementer"


def test_idle_fast_escalation_exact_retry_is_idempotent(workspace):
    work_id, _, execution, _ = _started_metrics_run(workspace, task_count=2, profile="fast")
    dispatch = begin(workspace, work_id)
    head = _commit_paths(workspace, ("src/task.py",))
    finish(workspace, work_id, execution, dispatch, "complete", head)
    first = record_execution_progress(workspace, work_id, "escalate", 2, reason="shared module")
    before = (execution / "progress.md").read_bytes()
    retry = record_execution_progress(workspace, work_id, "escalate", 2, reason="shared module")
    assert first["next_role"] == retry["next_role"] == "task_reviewer"
    assert retry["result"] == "already_applied"
    with pytest.raises(ExecutionProfileError):
        record_execution_progress(workspace, work_id, "escalate", 2, reason="different request")
    assert (execution / "progress.md").read_bytes() == before


@pytest.mark.parametrize("failure_command", ["pytest -q", "other check"])
def test_latest_failed_final_check_still_prevents_metrics_finalization(workspace, failure_command):
    work_id, _, execution, _ = _started_metrics_run(workspace)
    dispatch = begin(workspace, work_id)
    head = _commit_paths(workspace, ("src/task.py",))
    finish(workspace, work_id, execution, dispatch, "complete", head)
    finish(workspace, work_id, execution, begin(workspace, work_id), "approved", head)
    dispatch = begin(workspace, work_id)
    observation = _structured_record(execution, expected_sequence=3, role="final_reviewer", task="final", status="approved")
    observation["verification_records"].append(dict(observation["verification_records"][0], command=failure_command, status="failed"))
    (execution / "final-review.md").write_text("Verdict: Approved\n")
    record_execution_progress(workspace, work_id, "complete", dispatch["role_sequence"], status="approved", head=head)
    append_metrics_invocation(workspace, work_id, observation)
    acknowledge_metrics_completion(workspace, work_id, 3)
    before = (execution / "metrics.md").read_bytes()
    with pytest.raises(MetricsFormatError, match="passed full-suite"):
        finalize_metrics(workspace, work_id, 3)
    assert (execution / "metrics.md").read_bytes() == before

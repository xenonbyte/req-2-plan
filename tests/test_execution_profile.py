import json

import pytest

from tools.workflow_cli.execution_profile import (
    ExecutionProfile,
    ExecutionProfileError,
    check_prerequisite_v2,
    consume_accepted_sample_evidence,
    fast_structure_eligible,
    finalize_fast_ledger,
    parse_execution_ledger,
    validate_ledger_commit_chain,
)
from tools.workflow_cli.models import TierBase, TierEstimate, TierModifier


TASK_IDS = ("PLAN-TASK-001", "PLAN-TASK-002", "PLAN-TASK-003")
BASE = "abcdef0123456789abcdef0123456789abcdef01"


def ledger(*rows: str, extras: str = "") -> str:
    return "\n".join((
        "# Execution Progress",
        "",
        f"Execution BASE: {BASE}",
        "",
        *rows,
        "",
        extras.rstrip(),
        "",
    ))


def plan() -> str:
    return "\n".join(f"### {task_id} — task" for task_id in TASK_IDS)


def test_legacy_strict_ledger_parses_reviewed_complete_prefix():
    ledger = """# Execution Progress

Execution BASE: abcdef0123456789abcdef0123456789abcdef01

- [x] PLAN-TASK-001 — first
- [ ] PLAN-TASK-002 — second

Task 1: complete (commits abcdef0..1234567, review clean)
"""

    parsed = parse_execution_ledger(
        ledger, ("PLAN-TASK-001", "PLAN-TASK-002")
    )

    assert parsed.initial_profile is ExecutionProfile.STRICT
    assert parsed.effective_profile is ExecutionProfile.STRICT
    assert parsed.reviewed_complete == (1,)
    assert parsed.implemented == ()
    assert parsed.untouched == (2,)


def test_comments_and_fenced_examples_do_not_create_profile_or_markers():
    parsed = parse_execution_ledger(
        ledger(
            "- [ ] PLAN-TASK-001 — first",
            "- [ ] PLAN-TASK-002 — second",
            "- [ ] PLAN-TASK-003 — third",
            extras="""<!-- Execution Profile: fast -->
```text
Task 1: implemented (commits abcdef0..1234567, verification recorded)
```""",
        ),
        TASK_IDS,
    )

    assert parsed.initial_profile is ExecutionProfile.STRICT
    assert parsed.untouched == (1, 2, 3)


@pytest.mark.parametrize(
    "extra",
    (
        "Execution Profile: fast\nExecution Profile: fast",
        "Execution Profile: standard",
        "Profile Escalation: strict -> fast (reason: no)",
        "Task 1: implemented (commits ABCDEF0..1234567, verification recorded)",
        "Task 1: completebogus",
    ),
)
def test_profile_grammar_fails_closed(extra):
    with pytest.raises(ExecutionProfileError):
        parse_execution_ledger(
            ledger(
                "- [ ] PLAN-TASK-001 — first",
                "- [ ] PLAN-TASK-002 — second",
                "- [ ] PLAN-TASK-003 — third",
                extras=extra,
            ),
            TASK_IDS,
        )


def test_fast_state_segments_and_resume_selector():
    parsed = parse_execution_ledger(
        ledger(
            "- [x] PLAN-TASK-001 — first",
            "- [ ] PLAN-TASK-002 — second",
            "- [ ] PLAN-TASK-003 — third",
            extras="""Execution Profile: fast
Task 1: complete (commits abcdef0..1234567, review clean)
Task 2: implemented (commits 1234567..7654321, verification recorded)""",
        ),
        TASK_IDS,
    )

    assert parsed.reviewed_complete == (1,)
    assert parsed.implemented == (2,)
    assert parsed.untouched == (3,)
    assert parsed.first_actionable_task() == 3


def test_escalated_fast_must_review_implemented_segment_before_untouched():
    parsed = parse_execution_ledger(
        ledger(
            "- [ ] PLAN-TASK-001 — first",
            "- [ ] PLAN-TASK-002 — second",
            "- [ ] PLAN-TASK-003 — third",
            extras="""Execution Profile: fast
Profile Escalation: fast -> strict (reason: concern found)
Task 1: implemented (commits abcdef0..1234567, verification recorded)
Task 2: implemented (commits 1234567..7654321, verification recorded)""",
        ),
        TASK_IDS,
    )

    assert parsed.effective_profile is ExecutionProfile.STRICT
    assert parsed.first_actionable_task() == 1


@pytest.mark.parametrize(
    "rows, extra",
    (
        (
            ("- [ ] PLAN-TASK-001 — first", "- [x] PLAN-TASK-002 — second", "- [ ] PLAN-TASK-003 — third"),
            "Task 2: complete (commits abcdef0..1234567, review clean)",
        ),
        (
            ("- [x] PLAN-TASK-001 — first", "- [ ] PLAN-TASK-002 — second", "- [ ] PLAN-TASK-003 — third"),
            "Task 1: implemented (commits abcdef0..1234567, verification recorded)",
        ),
    ),
)
def test_invalid_task_state_segments_fail_closed(rows, extra):
    with pytest.raises(ExecutionProfileError):
        parse_execution_ledger(ledger(*rows, extras=extra), TASK_IDS)


def test_v2_prerequisite_uses_fast_resume_and_strict_recovery_selector():
    progress = ledger(
        "- [ ] PLAN-TASK-001 — first",
        "- [ ] PLAN-TASK-002 — second",
        "- [ ] PLAN-TASK-003 — third",
        extras="""Execution Profile: fast
Task 1: implemented (commits abcdef0..1234567, verification recorded)""",
    )

    result = check_prerequisite_v2(progress, plan(), 2)

    assert result["effective_profile"] == "fast"
    assert result["prerequisite"] == "PLAN-TASK-001"
    with pytest.raises(ExecutionProfileError, match="first actionable"):
        check_prerequisite_v2(progress, plan(), 1)


def test_fast_structure_requires_locked_light_without_modifiers():
    assert fast_structure_eligible(TierEstimate(TierBase.LIGHT).lock(TierBase.LIGHT, frozenset()))
    assert not fast_structure_eligible(TierEstimate(TierBase.LIGHT))
    assert not fast_structure_eligible(TierEstimate(TierBase.STANDARD).lock(TierBase.STANDARD, frozenset()))
    with_modifier = TierEstimate(TierBase.LIGHT, frozenset({TierModifier.MIGRATION}))
    assert not fast_structure_eligible(with_modifier.lock(TierBase.LIGHT, with_modifier.modifiers))


def test_commit_chain_requires_each_marker_base_and_head_to_be_ordered_ancestors():
    progress = ledger(
        "- [x] PLAN-TASK-001 — first",
        "- [x] PLAN-TASK-002 — second",
        "- [ ] PLAN-TASK-003 — third",
        extras="""Task 1: complete (commits abcdef0..1234567, review clean)
Task 2: complete (commits 1234567..7654321, review clean)""",
    )
    parsed = parse_execution_ledger(progress, TASK_IDS)
    commits = {
        BASE: BASE,
        "abcdef0": BASE,
        "1234567": "1" * 40,
        "7654321": "2" * 40,
    }
    ancestors = {(BASE, "1" * 40), ("1" * 40, "2" * 40), ("2" * 40, "2" * 40)}

    validate_ledger_commit_chain(
        parsed,
        current_head="2" * 40,
        resolve_commit=commits.__getitem__,
        is_ancestor=lambda older, newer: older == newer or (older, newer) in ancestors,
    )
    with pytest.raises(ExecutionProfileError, match="discontinuous"):
        validate_ledger_commit_chain(
            parsed,
            current_head="2" * 40,
            resolve_commit={**commits, "abcdef0": "f" * 40}.__getitem__,
            is_ancestor=lambda _older, _newer: True,
        )


def test_final_fast_migration_replaces_all_markers_in_one_constructed_ledger():
    progress = ledger(
        "- [ ] PLAN-TASK-001 — first",
        "- [ ] PLAN-TASK-002 — second",
        "- [ ] PLAN-TASK-003 — third",
        extras="""Execution Profile: fast
Task 1: implemented (commits abcdef0..1234567, verification recorded)
Task 2: implemented (commits 1234567..7654321, verification recorded)
Task 3: implemented (commits 7654321..0123456, verification recorded)""",
    )

    migrated = finalize_fast_ledger(progress, TASK_IDS)

    assert "- [ ]" not in migrated
    assert "implemented" not in migrated
    assert migrated.count("final review clean") == 3
    assert parse_execution_ledger(migrated, TASK_IDS).reviewed_complete == (1, 2, 3)


def test_evidence_consumption_reads_only_saved_validator_result(tmp_path):
    evidence = {
        "status": "ok",
        "message": "representative_metrics_accepted",
        "samples": [{"work_id": f"WF-20260831-sample-{number}"} for number in range(1, 4)],
        "aggregate": {"sample_count": 3, "representative": True},
    }
    path = tmp_path / "phase-3-sample-evidence.json"
    path.write_text(json.dumps(evidence), encoding="utf-8")

    assert consume_accepted_sample_evidence(path) == evidence


@pytest.mark.parametrize(
    "evidence",
    (
        {"status": "error", "message": "BLOCKED: representative_metrics_missing"},
        {"status": "ok", "message": "representative_metrics_accepted", "samples": [], "aggregate": {}},
    ),
)
def test_evidence_consumption_rejects_incomplete_or_unsuccessful_result(tmp_path, evidence):
    path = tmp_path / "phase-3-sample-evidence.json"
    path.write_text(json.dumps(evidence), encoding="utf-8")

    with pytest.raises(ExecutionProfileError):
        consume_accepted_sample_evidence(path)

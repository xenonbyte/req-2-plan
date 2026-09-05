import pytest

import tools.workflow_cli.execution_profile as execution_profile
from tools.workflow_cli.execution_profile import (
    ExecutionProfile,
    ExecutionProfileError,
    check_prerequisite_v2,
    fast_structure_eligible,
    finalize_fast_ledger,
    parse_execution_ledger,
    validate_ledger_commit_chain,
)
from tools.workflow_cli.models import TierBase, TierEstimate, TierModifier, WorkId
from tools.workflow_cli.state import RunStateManager, create_run_record


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


def plan(*steps: str) -> str:
    if not steps:
        steps = (
            "Prerequisite: none\n- [ ] first step",
            "Prerequisite: PLAN-TASK-001\n- [ ] second step",
            "Prerequisite: PLAN-TASK-002\n- [ ] third step",
        )
    assert len(steps) == len(TASK_IDS)
    return "\n\n".join(
        f"""### {task_id} — task
Steps:
{task_steps}
Verification:
1. Verify the task.
"""
        for task_id, task_steps in zip(TASK_IDS, steps)
    )


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


def test_execution_ledger_accepts_authoritative_checkbox_spacing_and_case():
    parsed = parse_execution_ledger(
        ledger(
            "  -  [X]   PLAN-TASK-001 — first",
            "\t- [   ] PLAN-TASK-002 — second",
            "- [ ] PLAN-TASK-003 — third",
            extras="Task 1: complete (commits abcdef0..1234567, review clean)",
        ),
        TASK_IDS,
    )

    assert parsed.reviewed_complete == (1,)
    assert parsed.untouched == (2, 3)


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
        " Execution Profile: fast",
        "Execution Profile : fast",
        "Execution Profilex: fast",
        "Profile Escalation: strict -> fast (reason: no)",
        " Profile Escalation: fast -> strict (reason: concern)",
        "Profile Escalation : fast -> strict (reason: concern)",
        "Profile Escalationx: fast -> strict (reason: concern)",
        "Task 1: implemented (commits ABCDEF0..1234567, verification recorded)",
        " Task 1: implemented (commits abcdef0..1234567, verification recorded)",
        "Task1: implemented (commits abcdef0..1234567, verification recorded)",
        "Task 1 : implemented (commits abcdef0..1234567, verification recorded)",
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


def test_profile_escalation_must_follow_explicit_initial_profile():
    with pytest.raises(ExecutionProfileError, match="precede"):
        parse_execution_ledger(
            ledger(
                "- [ ] PLAN-TASK-001 — first",
                "- [ ] PLAN-TASK-002 — second",
                "- [ ] PLAN-TASK-003 — third",
                extras="""Profile Escalation: fast -> strict (reason: concern)
Execution Profile: fast""",
            ),
            TASK_IDS,
        )


@pytest.mark.parametrize(
    "extra",
    (
        "Execution Profile documentation remains unchanged.",
        "Profile Escalation is discussed in the operator guide.",
        "Task execution completed after verification.",
    ),
)
def test_ordinary_unrelated_prose_is_not_a_ledger_lookalike(extra):
    parsed = parse_execution_ledger(
        ledger(
            "- [ ] PLAN-TASK-001 — first",
            "- [ ] PLAN-TASK-002 — second",
            "- [ ] PLAN-TASK-003 — third",
            extras=extra,
        ),
        TASK_IDS,
    )

    assert parsed.untouched == (1, 2, 3)


def test_fast_state_segments_and_resume_selector():
    parsed = parse_execution_ledger(
        ledger(
            "- [ ] PLAN-TASK-001 — first",
            "- [ ] PLAN-TASK-002 — second",
            "- [ ] PLAN-TASK-003 — third",
            extras="""Execution Profile: fast
Task 1: implemented (commits abcdef0..1234567, verification recorded)""",
        ),
        TASK_IDS,
    )

    assert parsed.reviewed_complete == ()
    assert parsed.implemented == (1,)
    assert parsed.untouched == (2, 3)
    assert parsed.first_actionable_task() == 2


def test_unelevated_fast_rejects_reviewed_complete_prefix():
    with pytest.raises(ExecutionProfileError, match="unelevated fast"):
        parse_execution_ledger(
            ledger(
                "- [x] PLAN-TASK-001 — first",
                "- [ ] PLAN-TASK-002 — second",
                "- [ ] PLAN-TASK-003 — third",
                extras="""Execution Profile: fast
Task 1: complete (commits abcdef0..1234567, final review clean)""",
            ),
            TASK_IDS,
        )


def test_unelevated_fast_all_complete_requires_final_review_clean():
    progress = ledger(
        "- [x] PLAN-TASK-001 — first",
        "- [x] PLAN-TASK-002 — second",
        "- [x] PLAN-TASK-003 — third",
        extras="""Execution Profile: fast
Task 1: complete (commits abcdef0..1234567, review clean)
Task 2: complete (commits 1234567..7654321, review clean)
Task 3: complete (commits 7654321..0123456, review clean)""",
    )

    with pytest.raises(ExecutionProfileError, match="final review clean"):
        parse_execution_ledger(progress, TASK_IDS)
    with pytest.raises(ExecutionProfileError, match="final review clean"):
        finalize_fast_ledger(progress, TASK_IDS)


def test_unelevated_fast_all_complete_accepts_final_review_clean():
    progress = ledger(
        "- [x] PLAN-TASK-001 — first",
        "- [x] PLAN-TASK-002 — second",
        "- [x] PLAN-TASK-003 — third",
        extras="""Execution Profile: fast
Task 1: complete (commits abcdef0..1234567, final review clean)
Task 2: complete (commits 1234567..7654321, final review clean)
Task 3: complete (commits 7654321..0123456, final review clean)""",
    )

    parsed = parse_execution_ledger(progress, TASK_IDS)

    assert parsed.reviewed_complete == (1, 2, 3)
    assert finalize_fast_ledger(progress, TASK_IDS) == progress


def test_escalated_fast_retains_reviewed_prefix_for_strict_recovery():
    parsed = parse_execution_ledger(
        ledger(
            "- [x] PLAN-TASK-001 — first",
            "- [ ] PLAN-TASK-002 — second",
            "- [ ] PLAN-TASK-003 — third",
            extras="""Execution Profile: fast
Profile Escalation: fast -> strict (reason: concern found)
Task 1: complete (commits abcdef0..1234567, review clean)
Task 2: implemented (commits 1234567..7654321, verification recorded)""",
        ),
        TASK_IDS,
    )

    assert parsed.reviewed_complete == (1,)
    assert parsed.implemented == (2,)
    assert parsed.first_actionable_task() == 2


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


def test_v2_prerequisite_accepts_declared_group_root_none():
    progress = ledger(
        "- [x] PLAN-TASK-001 — first",
        "- [x] PLAN-TASK-002 — second",
        "- [ ] PLAN-TASK-003 — third",
        extras="""Task 1: complete (commits abcdef0..1234567, review clean)
Task 2: complete (commits 1234567..7654321, review clean)""",
    )

    result = check_prerequisite_v2(
        progress,
        plan(
            "Prerequisite: none\n- [ ] first step",
            "Prerequisite: PLAN-TASK-001\n- [ ] second step",
            "Prerequisite: none\n- [ ] third step",
        ),
        3,
    )

    assert result["prerequisite"] == "none"
    assert result["satisfied"] is True


def test_v2_prerequisite_uses_declared_reviewed_predecessor_marker():
    progress = ledger(
        "- [x] PLAN-TASK-001 — first",
        "- [ ] PLAN-TASK-002 — second",
        "- [ ] PLAN-TASK-003 — third",
        extras="Task 1: complete (commits abcdef0..1234567, review clean)",
    )

    result = check_prerequisite_v2(progress, plan(), 2)

    assert result["prerequisite"] == "PLAN-TASK-001"
    assert result["satisfied"] is True


@pytest.mark.parametrize(
    ("task_steps", "message"),
    (
        ("- [ ] no declaration", "missing"),
        (
            "Prerequisite: none\nPrerequisite: PLAN-TASK-001\n- [ ] duplicate",
            "duplicated",
        ),
        ("Prerequisite: PLAN-TASK-1\n- [ ] malformed", "malformed"),
        ("- [ ] not first\nPrerequisite: none", "first Steps line"),
    ),
)
def test_v2_prerequisite_rejects_missing_duplicate_or_malformed_declarations(
    task_steps, message
):
    progress = ledger(
        "- [ ] PLAN-TASK-001 — first",
        "- [ ] PLAN-TASK-002 — second",
        "- [ ] PLAN-TASK-003 — third",
    )

    with pytest.raises(ExecutionProfileError, match=message):
        check_prerequisite_v2(
            progress,
            plan(
                task_steps,
                "Prerequisite: PLAN-TASK-001\n- [ ] second step",
                "Prerequisite: PLAN-TASK-002\n- [ ] third step",
            ),
            1,
        )


@pytest.mark.parametrize(
    ("declared", "message"),
    (
        ("PLAN-TASK-002", "itself"),
        ("PLAN-TASK-003", "forward"),
        ("PLAN-TASK-999", "outside PLAN"),
    ),
)
def test_v2_prerequisite_rejects_self_forward_and_foreign_references(
    declared, message
):
    progress = ledger(
        "- [x] PLAN-TASK-001 — first",
        "- [ ] PLAN-TASK-002 — second",
        "- [ ] PLAN-TASK-003 — third",
        extras="Task 1: complete (commits abcdef0..1234567, review clean)",
    )

    with pytest.raises(ExecutionProfileError, match=message):
        check_prerequisite_v2(
            progress,
            plan(
                "Prerequisite: none\n- [ ] first step",
                f"Prerequisite: {declared}\n- [ ] second step",
                "Prerequisite: PLAN-TASK-002\n- [ ] third step",
            ),
            2,
        )


def test_fast_structure_uses_authoritative_locked_tier_boundary(tmp_path):
    record = create_run_record(WorkId("WF-20260831-profile-test"))
    record.tier_locked = TierEstimate(TierBase.LIGHT)
    manager = RunStateManager(tmp_path / ".req-to-plan" / str(record.work_id))
    manager.save(record)

    loaded = manager.load()

    assert loaded.tier_locked == TierEstimate(TierBase.LIGHT)
    assert fast_structure_eligible(loaded.tier_locked)
    assert not fast_structure_eligible(None)
    assert not fast_structure_eligible(TierEstimate(TierBase.STANDARD))
    assert not fast_structure_eligible(
        TierEstimate(TierBase.LIGHT, frozenset({TierModifier.MIGRATION}))
    )


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


def test_commit_chain_rejects_zero_length_task_marker_range():
    parsed = parse_execution_ledger(
        ledger(
            "- [x] PLAN-TASK-001 — first",
            "- [ ] PLAN-TASK-002 — second",
            "- [ ] PLAN-TASK-003 — third",
            extras="Task 1: complete (commits abcdef0..abcdef0, review clean)",
        ),
        TASK_IDS,
    )

    with pytest.raises(ExecutionProfileError, match="empty|zero-length|contain a commit"):
        validate_ledger_commit_chain(
            parsed,
            current_head=BASE,
            resolve_commit={BASE: BASE, "abcdef0": BASE}.__getitem__,
            is_ancestor=lambda older, newer: older == newer,
        )


def test_commit_chain_rejects_unrecorded_descendant_without_task_marker():
    parsed = parse_execution_ledger(
        ledger(
            "- [ ] PLAN-TASK-001 — first",
            "- [ ] PLAN-TASK-002 — second",
            "- [ ] PLAN-TASK-003 — third",
        ),
        TASK_IDS,
    )
    descendant = "1" * 40

    validate_ledger_commit_chain(
        parsed,
        current_head=BASE,
        resolve_commit={BASE: BASE}.__getitem__,
        is_ancestor=lambda older, newer: older == newer,
    )
    with pytest.raises(ExecutionProfileError, match="recorded ledger boundary"):
        validate_ledger_commit_chain(
            parsed,
            current_head=descendant,
            resolve_commit={BASE: BASE}.__getitem__,
            is_ancestor=lambda older, newer: (older, newer) == (BASE, descendant),
        )


@pytest.mark.parametrize("adapter", ["resolve", "ancestry"])
@pytest.mark.parametrize("error_type", [ValueError, OSError, TypeError, AttributeError])
def test_commit_chain_preserves_adapter_failure_classification(adapter, error_type):
    parsed = parse_execution_ledger(
        ledger(*(f"- [ ] {task_id}" for task_id in TASK_IDS)), TASK_IDS,
    )
    error = error_type("injected adapter failure")

    def fail(*args):
        raise error

    expected = ExecutionProfileError if error_type in {ValueError, OSError} else error_type
    with pytest.raises(expected) as failure:
        validate_ledger_commit_chain(
            parsed, current_head=BASE,
            resolve_commit=fail if adapter == "resolve" else lambda sha: sha,
            is_ancestor=fail if adapter == "ancestry" else lambda older, newer: True,
        )
    if expected is ExecutionProfileError:
        message = "commit resolution failed" if adapter == "resolve" else "commit ancestry check failed"
        assert message in str(failure.value)
        assert failure.value.__cause__ is error
    else:
        assert failure.value is error


def test_commit_chain_does_not_reclassify_malformed_ledger_as_git_failure():
    from dataclasses import replace
    parsed = parse_execution_ledger(
        ledger(*(f"- [ ] {task_id}" for task_id in TASK_IDS)), TASK_IDS,
    )
    with pytest.raises(AttributeError):
        validate_ledger_commit_chain(
            replace(parsed, markers=(None,)), current_head=BASE,
            resolve_commit=lambda sha: sha, is_ancestor=lambda older, newer: True,
        )


def test_commit_chain_rejects_unrecorded_descendant_after_task_marker():
    parsed = parse_execution_ledger(
        ledger(
            "- [x] PLAN-TASK-001 — first",
            "- [ ] PLAN-TASK-002 — second",
            "- [ ] PLAN-TASK-003 — third",
            extras="Task 1: complete (commits abcdef0..1234567, review clean)",
        ),
        TASK_IDS,
    )
    marker_head = "1" * 40
    descendant = "2" * 40
    commits = {BASE: BASE, "abcdef0": BASE, "1234567": marker_head}
    ancestors = {(BASE, marker_head), (marker_head, descendant)}

    with pytest.raises(ExecutionProfileError, match="recorded ledger boundary"):
        validate_ledger_commit_chain(
            parsed,
            current_head=descendant,
            resolve_commit=commits.__getitem__,
            is_ancestor=lambda older, newer: (
                older == newer or (older, newer) in ancestors
            ),
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


def test_final_fast_migration_preserves_fenced_and_commented_examples_byte_for_byte():
    nonsemantic = """```text
- [ ] PLAN-TASK-001 — fenced example
Task 1: implemented (commits abcdef0..1234567, verification recorded)
```
<!--
- [ ] PLAN-TASK-002 — commented example
Task 2: implemented (commits 1234567..7654321, verification recorded)
-->"""
    progress = ledger(
        "- [ ] PLAN-TASK-001 — first",
        "- [ ] PLAN-TASK-002 — second",
        "- [ ] PLAN-TASK-003 — third",
        extras=f"""Execution Profile: fast
Task 1: implemented (commits abcdef0..1234567, verification recorded)
Task 2: implemented (commits 1234567..7654321, verification recorded)
Task 3: implemented (commits 7654321..0123456, verification recorded)
{nonsemantic}""",
    )

    migrated = finalize_fast_ledger(progress, TASK_IDS)

    assert nonsemantic in migrated
    assert migrated.count("- [x] PLAN-TASK-") == 3
    assert migrated.count("final review clean") == 3


def test_final_fast_migration_preserves_seeded_readonly_block_byte_for_byte():
    nonsemantic = """## Project Context (read-only)
- [ ] PLAN-TASK-001 — seeded example
Task 1: implemented (commits abcdef0..1234567, verification recorded)
<!-- /r2p-read-only -->"""
    progress = ledger(
        "- [ ] PLAN-TASK-001 — first",
        "- [ ] PLAN-TASK-002 — second",
        "- [ ] PLAN-TASK-003 — third",
        extras=f"""{nonsemantic}
Execution Profile: fast
Task 1: implemented (commits abcdef0..1234567, verification recorded)
Task 2: implemented (commits 1234567..7654321, verification recorded)
Task 3: implemented (commits 7654321..0123456, verification recorded)""",
    )

    migrated = finalize_fast_ledger(progress, TASK_IDS)

    assert nonsemantic in migrated
    assert migrated.count("- [x] PLAN-TASK-") == 3
    assert migrated.count("final review clean") == 3


@pytest.mark.parametrize("ending", ["\n", "\r\n"])
def test_fast_migration_preserves_original_offsets_with_copied_headings_and_comments(ending):
    nonsemantic = (
        "## Project Context (read-only)\n# Copied artifact\n"
        "- [ ] PLAN-TASK-001 — copied\n<!-- /r2p-read-only -->\n"
        "<!--\n```\n- [ ] PLAN-TASK-001 — comment\n-->\n"
        "~~~markdown\n- [ ] PLAN-TASK-001 — fenced\n~~~\n"
    )
    task = "- [ ] PLAN-TASK-001 — 真实任务\n"
    marker = "Task 1: implemented (commits abcdef0..1234567, verification recorded)"
    prefix = f"# Progress\nExecution BASE: {BASE}\nExecution Profile: fast\n"
    progress = (prefix + nonsemantic + task + marker).replace("\n", ending)
    expected = (
        prefix + nonsemantic + task.replace("- [ ]", "- [x]")
        + "Task 1: complete (commits abcdef0..1234567, final review clean)"
    ).replace("\n", ending)
    assert finalize_fast_ledger(progress, (TASK_IDS[0],)) == expected


@pytest.mark.parametrize("ending", ["\r\n", *"\n\r\v\f\x1c\x1d\x1e\x85\u2028\u2029"])
def test_fast_migration_preserves_readonly_splitlines_boundaries(ending):
    prefix = f"# Progress\nExecution BASE: {BASE}\nExecution Profile: fast\n"
    readonly = (
        f"## Project Context (read-only){ending}Copied context α{ending}"
        f"<!-- /r2p-read-only -->{ending}"
    )
    example = "```text\n- [ ] PLAN-TASK-001 example\n<!-- literal comment -->\n```\n"
    checkbox = "- [ ] PLAN-TASK-001 real task\n"
    marker = "Task 1: implemented (commits abcdef0..1234567, verification recorded)\n"
    content = prefix + readonly + example + checkbox + marker
    expected = (
        prefix + readonly + example + checkbox.replace("- [ ]", "- [x]")
        + "Task 1: complete (commits abcdef0..1234567, final review clean)\n"
    )
    assert finalize_fast_ledger(content, (TASK_IDS[0],)).encode("utf-8") == expected.encode("utf-8")


@pytest.mark.parametrize("size", [100, 200, 400])
def test_semantic_source_scan_bounds_total_markdown_input(monkeypatch, size):
    import tools.workflow_cli.markdown as markdown
    content = "visible α\n" * size
    scanned = []
    real_mask = markdown._mask_html_comments_outside_fences

    def counted_mask(text, **kwargs):
        scanned.append(len(text))
        return real_mask(text, **kwargs)

    monkeypatch.setattr(markdown, "_mask_html_comments_outside_fences", counted_mask)
    lines = list(execution_profile._semantic_source_lines(content))
    assert len(lines) == size
    assert all(content[start:end] == line for line, start, end in lines)
    assert sum(scanned) <= 3 * len(content)


@pytest.mark.parametrize("second", [
    "Steps:\n- implement\n",
    "Steps:\nPrerequisite : PLAN-TASK-001\n",
    "Steps:\nPrerequisite: PLAN-TASK-002\n",
    "Steps:\nPrerequisite: PLAN-TASK-003\n",
    "Steps:\nPrerequisite: PLAN-TASK-999\n",
    "Steps:\nPrerequisite: PLAN-TASK-001\nPrerequisite: none\n",
    "Steps:\nPrerequisite: PLAN-TASK-001\nVerification:\nPrerequisite: none\n",
    "Steps:\n- Prerequisite: PLAN-TASK-001\n",
    "Steps:\nprerequisite: PLAN-TASK-001\n",
])
def test_plan_prerequisite_classification_validates_every_task(second):
    from tools.workflow_cli.execution_profile import prerequisite_semantics_version

    text = (
        "### PLAN-TASK-001: first\nSteps:\nPrerequisite: none\n"
        "### PLAN-TASK-002: second\n" + second
    )
    with pytest.raises(ExecutionProfileError):
        prerequisite_semantics_version(text)


def test_plan_prerequisite_classification_preserves_legacy_and_group_roots():
    from tools.workflow_cli.execution_profile import prerequisite_semantics_version

    legacy = "### PLAN-TASK-001: first\nSteps:\n- implement\n"
    examples = "```text\nPrerequisite: none\n```\n<!-- Prerequisite: bad -->\n"
    assert prerequisite_semantics_version(legacy + examples) == 1
    assert prerequisite_semantics_version(
        "### PLAN-TASK-001: first\nSteps:\nPrerequisite: none\n"
        "### PLAN-TASK-002: root\nSteps:\nPrerequisite: none\n" + examples
    ) == 2

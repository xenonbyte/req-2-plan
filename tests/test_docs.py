from __future__ import annotations

from pathlib import Path


def unfenced_lines(content: str):
    in_fence = False
    for line in content.splitlines():
        if line.startswith("```") or line.startswith("~~~"):
            in_fence = not in_fence
            continue
        if not in_fence:
            yield line


def fenced_lines(content: str):
    in_fence = False
    for line in content.splitlines():
        if line.startswith("```") or line.startswith("~~~"):
            in_fence = not in_fence
            continue
        if in_fence:
            yield line


def test_plan_workflow_task_examples_use_plan_task_anchors():
    content = Path("docs/plan-workflow.md").read_text(encoding="utf-8")

    assert "### Task N:" not in content
    assert "### Task 3:" not in content
    assert "### PLAN-TASK-001:" in content


def test_spec_workflow_no_dependency_na_row_is_unfenced():
    content = Path("docs/spec-workflow.md").read_text(encoding="utf-8")
    template = content.split("## SPEC Template\n\n```markdown\n", 1)[1].split("\n```", 1)[0]
    line = "N/A — no external dependencies"

    assert line in list(unfenced_lines(template))
    assert line not in list(fenced_lines(template))


def test_workflow_cli_adapter_documents_review_checkpoint_marker_only():
    content = Path("docs/workflow-cli-adapter.md").read_text(encoding="utf-8")
    row = next(
        line for line in content.splitlines()
        if line.startswith("| `workflow review-checkpoint` |")
    )

    assert "marker-only" in row.lower()
    assert "findings" not in row.lower()


def test_tier_command_docs_match_cli_flags_and_checkpoint_boundary():
    cli_adapter = Path("docs/workflow-cli-adapter.md").read_text(encoding="utf-8")
    assert "| `workflow tier-estimate` |" in cli_adapter
    assert "| `workflow tier-estimate` | `CMD-TIER-ESTIMATE` | `--text`" in cli_adapter
    assert "| `workflow tier-lock` | `CMD-TIER-LOCK` | `--work-id`, `--base`" in cli_adapter
    assert "--decision" not in next(
        line for line in cli_adapter.splitlines()
        if line.startswith("| `workflow tier-lock` |")
    )
    assert "--modifier" in next(
        line for line in cli_adapter.splitlines()
        if line.startswith("| `workflow tier-escalate` |")
    )

    command_surface = Path("docs/workflow-command-surface.md").read_text(encoding="utf-8")
    escalation_policy = next(
        sentence for sentence in command_surface.split(". ")
        if "`CMD-TIER-ESCALATE` is allowed" in sentence
    )
    assert "`checkpoint_approved`" not in escalation_policy
    assert "It is refused in `not_started`, `checkpoint_approved`, `closed_at_plan_checkpoint`" in command_surface


def test_cli_adapter_implemented_rows_match_current_parser_surface():
    content = Path("docs/workflow-cli-adapter.md").read_text(encoding="utf-8")

    forbidden = [
        "`--json` |",
        "workflow status-next --work-id WF-001 --json",
        "python -m tools.workflow_cli status-next --work-id WF-001 --json",
        "workflow gap-reimport --work-id WF-001",
        "workflow artifact-mark-stale --work-id WF-001",
        "`workflow run-start` | `CMD-RUN-START` | `--work-id`, plus `--source`",
    ]
    for needle in forbidden:
        assert needle not in content

    required = [
        "| `R2P_JSON=1` |",
        "| `workflow run-start` | `CMD-RUN-START` | `--work-id`, `--requirement`",
        "| `workflow stage-produce` | `CMD-STAGE-PRODUCE` | `--work-id`, `--stage`, `--content` or `--content-file`",
        "| `workflow checkpoint-decide` | `CMD-CHECKPOINT-DECIDE` | `--work-id`, `--stage`, `--decision`, `--confirm` for approval",
        "workflow checkpoint-decide --work-id WF-001 --stage spec --decision changes_requested",
    ]
    for needle in required:
        assert needle in content


def test_command_surface_documents_marker_only_review_and_next_stage_advance():
    content = Path("docs/workflow-command-surface.md").read_text(encoding="utf-8")

    advance_row = next(
        line for line in content.splitlines()
        if line.startswith("| `CMD-STAGE-ADVANCE` |")
    )
    assert "`next_stage`" in advance_row
    assert "active_stage_draft` transition" in advance_row

    review_row = next(
        line for line in content.splitlines()
        if line.startswith("| `CMD-REVIEW-CHECKPOINT` |")
    )
    assert "marker-only" in review_row.lower()
    assert "checkpoint-review-vN.md" in review_row

    decide_row = next(
        line for line in content.splitlines()
        if line.startswith("| `CMD-CHECKPOINT-DECIDE` |")
    )
    assert "checkpoint-review marker for approvals" in decide_row
    assert "result `approved` or `changes_requested`" in decide_row


def test_invariants_describe_marker_scope_for_approval_only():
    content = Path("docs/workflow-invariants.md").read_text(encoding="utf-8")
    section = content.split("### Forced Subagent Review Rule", 1)[1].split("\n### ", 1)[0]

    assert "always-required precondition for approved decisions" in section
    assert "Non-approval decisions such as `changes_requested`" in section
    assert "findings must be merged before any checkpoint decision" not in section


def test_operator_runbook_uses_current_cli_surface():
    content = Path("docs/workflow-operator-runbook.md").read_text(encoding="utf-8")

    forbidden = [
        "--source <requirement.md>",
        "review-merge",
        "confirm-record",
        "checkpoint-bundle",
        "status-routes",
        "status-artifacts",
        "--decision \"<base+modifiers>\"",
        "--decision migration",
        "--reason \"discovery surfaced migration-visible behavior\"",
        "< <stage-artifact-body.md>",
    ]
    for needle in forbidden:
        assert needle not in content

    required = [
        "--requirement \"<raw requirement>\"",
        "--base <light|standard>",
        "--modifier migration",
        "--content-file <stage-artifact-body.md>",
        "review-checkpoint",
        "checkpoint-decide",
        "stage-advance",
        "R2P_JSON=1",
        "does not accept a `--json` flag",
    ]
    for needle in required:
        assert needle in content

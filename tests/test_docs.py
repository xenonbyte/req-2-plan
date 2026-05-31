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

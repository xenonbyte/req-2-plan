"""Tests for the Superpowers adapter and adapter registry."""
from __future__ import annotations

import pytest
from pathlib import Path


# ---------------------------------------------------------------------------
# Adapter constants
# ---------------------------------------------------------------------------

def test_adapter_name():
    from tools.workflow_cli.adapters.superpowers import ADAPTER_NAME
    assert ADAPTER_NAME == "superpowers"


def test_adapter_rule_version():
    from tools.workflow_cli.adapters.superpowers import ADAPTER_RULE_VERSION
    assert ADAPTER_RULE_VERSION == "v1"


def test_supported_plan_sections_nonempty():
    from tools.workflow_cli.adapters.superpowers import SUPPORTED_PLAN_SECTIONS
    assert isinstance(SUPPORTED_PLAN_SECTIONS, set)
    assert len(SUPPORTED_PLAN_SECTIONS) > 0


# ---------------------------------------------------------------------------
# Happy path: single task
# ---------------------------------------------------------------------------

MINIMAL_PLAN = """\
# Plan: WF-20260527-feature

## PLAN-TASK-001
Goal: Implement rate limiting middleware
Steps:
1. Add rate limit check in middleware
2. Return 429 on limit exceeded
Spec References: SPEC-FUNC-001, SPEC-ERR-001
Change Type: additive
TDD:
- Red: write failing test for rate limit
- Green: implement
- Refactor: extract config
Verification:
- Unit test passes
- Integration test passes
"""


def test_happy_path_returns_derived_plan_written(tmp_path: Path):
    from tools.workflow_cli.adapters.superpowers import adapt_plan
    plan = tmp_path / "07-plan.md"
    plan.write_text(MINIMAL_PLAN, encoding="utf-8")
    out = tmp_path / "superpowers-plan.md"
    result = adapt_plan(plan, out)
    assert result == "derived_plan_written"


def test_happy_path_output_file_exists(tmp_path: Path):
    from tools.workflow_cli.adapters.superpowers import adapt_plan
    plan = tmp_path / "07-plan.md"
    plan.write_text(MINIMAL_PLAN, encoding="utf-8")
    out = tmp_path / "superpowers-plan.md"
    adapt_plan(plan, out)
    assert out.exists()


def test_happy_path_output_contains_task_goal(tmp_path: Path):
    from tools.workflow_cli.adapters.superpowers import adapt_plan
    plan = tmp_path / "07-plan.md"
    plan.write_text(MINIMAL_PLAN, encoding="utf-8")
    out = tmp_path / "superpowers-plan.md"
    adapt_plan(plan, out)
    content = out.read_text(encoding="utf-8")
    assert "Implement rate limiting middleware" in content


def test_happy_path_output_contains_adapter_rule_version(tmp_path: Path):
    from tools.workflow_cli.adapters.superpowers import adapt_plan, ADAPTER_RULE_VERSION
    plan = tmp_path / "07-plan.md"
    plan.write_text(MINIMAL_PLAN, encoding="utf-8")
    out = tmp_path / "superpowers-plan.md"
    adapt_plan(plan, out)
    content = out.read_text(encoding="utf-8")
    assert ADAPTER_RULE_VERSION in content


# ---------------------------------------------------------------------------
# Missing task: no PLAN-TASK sections
# ---------------------------------------------------------------------------

NO_TASK_PLAN = """\
# Plan: WF-20260527-feature

Some prose content but no task sections here.
"""


def test_missing_task_returns_adapter_gap_detected(tmp_path: Path):
    from tools.workflow_cli.adapters.superpowers import adapt_plan
    plan = tmp_path / "07-plan.md"
    plan.write_text(NO_TASK_PLAN, encoding="utf-8")
    out = tmp_path / "superpowers-plan.md"
    result = adapt_plan(plan, out)
    assert result == "adapter_gap_detected"


def test_missing_task_repair_file_written(tmp_path: Path):
    from tools.workflow_cli.adapters.superpowers import adapt_plan
    plan = tmp_path / "07-plan.md"
    plan.write_text(NO_TASK_PLAN, encoding="utf-8")
    out = tmp_path / "superpowers-plan.md"
    adapt_plan(plan, out)
    repair = tmp_path / "superpowers-plan.md.repair.md"
    assert repair.exists()


# ---------------------------------------------------------------------------
# Stale source: file does not exist
# ---------------------------------------------------------------------------

def test_stale_source_returns_stale_source_detected(tmp_path: Path):
    from tools.workflow_cli.adapters.superpowers import adapt_plan
    plan = tmp_path / "nonexistent-plan.md"
    out = tmp_path / "superpowers-plan.md"
    result = adapt_plan(plan, out)
    assert result == "stale_source_detected"


# ---------------------------------------------------------------------------
# Empty plan: file exists but content is empty
# ---------------------------------------------------------------------------

def test_empty_plan_returns_stale_source_detected(tmp_path: Path):
    from tools.workflow_cli.adapters.superpowers import adapt_plan
    plan = tmp_path / "07-plan.md"
    plan.write_text("", encoding="utf-8")
    out = tmp_path / "superpowers-plan.md"
    result = adapt_plan(plan, out)
    assert result == "stale_source_detected"


# ---------------------------------------------------------------------------
# Source not mutated
# ---------------------------------------------------------------------------

def test_adapt_plan_does_not_mutate_source(tmp_path: Path):
    from tools.workflow_cli.adapters.superpowers import adapt_plan
    plan = tmp_path / "07-plan.md"
    plan.write_text(MINIMAL_PLAN, encoding="utf-8")
    original = plan.read_text(encoding="utf-8")
    out = tmp_path / "superpowers-plan.md"
    adapt_plan(plan, out)
    assert plan.read_text(encoding="utf-8") == original


# ---------------------------------------------------------------------------
# Multiple tasks
# ---------------------------------------------------------------------------

MULTI_TASK_PLAN = """\
# Plan: WF-20260527-feature

## PLAN-TASK-001
Goal: Implement rate limiting middleware
Steps:
1. Add rate limit check in middleware
Spec References: SPEC-FUNC-001
TDD:
- Red: write failing test
- Green: implement
Verification:
- Unit test passes

## PLAN-TASK-002
Goal: Add logging for rate limit events
Steps:
1. Log rate limit trigger
Spec References: SPEC-OBS-001
TDD:
- Red: write failing test for logging
- Green: implement logging
Verification:
- Log output verified
"""


def test_multiple_tasks_both_appear_in_output(tmp_path: Path):
    from tools.workflow_cli.adapters.superpowers import adapt_plan
    plan = tmp_path / "07-plan.md"
    plan.write_text(MULTI_TASK_PLAN, encoding="utf-8")
    out = tmp_path / "superpowers-plan.md"
    result = adapt_plan(plan, out)
    assert result == "derived_plan_written"
    content = out.read_text(encoding="utf-8")
    assert "Implement rate limiting middleware" in content
    assert "Add logging for rate limit events" in content


# ---------------------------------------------------------------------------
# Adapter registry
# ---------------------------------------------------------------------------

def test_get_adapter_returns_module_with_adapt_plan():
    from tools.workflow_cli.adapters import get_adapter
    module = get_adapter("superpowers")
    assert hasattr(module, "adapt_plan")
    assert callable(module.adapt_plan)


def test_list_adapters_contains_superpowers():
    from tools.workflow_cli.adapters import list_adapters
    assert "superpowers" in list_adapters()


def test_get_adapter_nonexistent_raises_value_error():
    from tools.workflow_cli.adapters import get_adapter
    with pytest.raises(ValueError, match="nonexistent"):
        get_adapter("nonexistent")

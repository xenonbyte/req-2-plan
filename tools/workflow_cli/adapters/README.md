# Adding a New Executor Adapter

Each adapter module must be placed in `tools/workflow_cli/adapters/` and registered in `ADAPTER_REGISTRY` in `__init__.py`.

## Required Exports

Each adapter module must export:

```python
ADAPTER_NAME: str          # unique name, matches registry key (e.g., "superpowers")
ADAPTER_RULE_VERSION: str  # version stamp written to derived plan header (e.g., "v1")
SUPPORTED_PLAN_SECTIONS: set[str]  # set of 07-plan.md section names this adapter consumes

def adapt_plan(plan_path: Path, output_path: Path) -> str:
    """
    Read the neutral 07-plan.md at plan_path.
    Write the executor-specific plan to output_path.
    Write a repair request to output_path.repair.md on failure.

    Returns one of:
    - "derived_plan_written"    — success, output_path written
    - "adapter_gap_detected"    — plan has gaps that need repair; repair file written
    - "stale_source_detected"   — plan_path content is stale (missing required sections)
    - "unsupported_executor"    — this adapter cannot handle the plan
    """
```

## Rules

1. `adapt_plan` MUST NOT mutate `plan_path` or any file outside `output_path` / `output_path.with_suffix('.repair.md')`.
2. `adapt_plan` MUST NOT change the source run's `run.md` status.
3. If the PLAN is not adaptable (empty Task Breakdown, missing SPEC refs, ambiguous TDD applicability), write a repair request file rather than guessing.
4. The derived plan header MUST include `ADAPTER_RULE_VERSION` for audit traceability.

## Tests

Create `tests/test_adapters_<name>.py` covering: happy path, missing-task, unsupported-sections, repair-request paths.

## Registration

Add your adapter to `ADAPTER_REGISTRY` in `adapters/__init__.py`:

```python
ADAPTER_REGISTRY = {
    "superpowers": "tools.workflow_cli.adapters.superpowers",
    "your_executor": "tools.workflow_cli.adapters.your_executor",  # ← add here
}
```

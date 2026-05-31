---
name: req-to-plan
description: Developer guide for extending and maintaining the req-to-plan CLI and Agent workflow
---

# req-to-plan Developer Skill

This skill is for contributors working on the req-to-plan implementation itself — adding commands, adapters, tests, or tier keywords. For the user-facing skill that drives workflow runs, see `tools/workflow_cli/agent_templates/claude/SKILL.md`.

## Module Responsibilities

```
tools/workflow_cli/
├── models.py          # Core types: RunStatus, Stage, TierBase, TierModifier, TierEstimate,
│                      # EvidenceBlock, WorkId, STAGE_ORDER, ALLOWED_TRANSITIONS
├── state.py           # RunStateManager (run.md read/write), state transition validation
├── artifact.py        # ArtifactManager (produce/update/ready/mark_stale), YAML frontmatter
├── tier.py            # scan_keywords (L1), compute_floor, estimate_tier (L1-L4)
├── tier_keywords.yaml # Keyword bank: 5 modifiers × zh+en entries
├── gates.py           # check_entry_gate, check_quality_gate, check_forced_subagent_review
├── output.py          # Exit codes, format_success/error/gate_result, is_json_mode
├── cli.py             # argparse router: run/tier/gate/status/stage command groups
├── agent_shortcuts.py # r2p-* shortcut surface: start/continue/status/switch/adapt/reopen
├── install_cli.py     # r2p lifecycle binary stub (full impl: Task 14)
├── version.py         # R2P_VERSION = "v1"
├── adapters/
│   ├── __init__.py    # ADAPTER_REGISTRY, get_adapter(), list_adapters()
│   └── superpowers.py # PLAN → Superpowers format adapter
└── agent_templates/   # Install templates (rendered by r2p install)
    ├── claude/        # SKILL.md + commands/r2p-*.md
    ├── codex/         # AGENTS.md
    └── gemini/        # commands/r2p-*.toml
```

Layer rule: Agent handles semantics and content generation; CLI handles state, structured validation, and file I/O.

## Running Tests

Use the project `.venv` (system Python lacks PyYAML due to PEP 668):

```bash
# All tests
.venv/bin/python -m pytest tests/ -v

# Single module
.venv/bin/python -m pytest tests/test_agent_shortcuts.py -v

# With coverage (if pytest-cov installed)
.venv/bin/python -m pytest tests/ --cov=tools/workflow_cli
```

Test count baseline: 530 passing. All tests must stay green after any change.

## Adding a New CLI Command

1. **Define the handler** in `cli.py`:

```python
def _cmd_mygroup_myaction(args):
    record, mgr, run_dir = _load_run(args.work_id, args.base_path)
    # ... logic ...
    print_and_exit(format_success({...}, message="..."), EXIT_OK)
```

2. **Register in a `_register_*_commands` function**:

```python
def _register_mygroup_commands(subparsers):
    p = subparsers.add_parser("mygroup-myaction", help="...")
    p.add_argument("--work-id", required=True)
    p.set_defaults(func=_cmd_mygroup_myaction)
```

3. **Call the register function** in `main()`:

```python
_register_mygroup_commands(subparsers)
```

4. **Exit codes** — use constants from `output.py`:
   - `EXIT_OK = 0` — success
   - `EXIT_CLI_ERR = 2` — invalid input
   - `EXIT_GATE_FAIL = 3` — gate/precondition fail
   - `EXIT_DRY_RUN = 4` — dry-run preview
   - `EXIT_REVIEW_REQ = 5` — subagent review required
   - `EXIT_CONFLICT = 6` — conflicting state
   - `EXIT_NOT_FOUND = 7` — run or artifact missing

5. **Add tests** in `tests/test_cli.py` following the `invoke()` helper pattern.

## Adding a New Adapter

1. **Create the module** at `tools/workflow_cli/adapters/<name>.py`:

```python
from __future__ import annotations
from pathlib import Path

ADAPTER_NAME = "<name>"
ADAPTER_RULE_VERSION = "v1"
SUPPORTED_PLAN_SECTIONS: set[str] = {"PLAN-TASK"}  # sections you handle

def adapt_plan(plan_path: Path, output_path: Path) -> str:
    """Convert approved PLAN to executor-specific format.
    
    Returns one of:
    - "derived_plan_written" — success
    - "adapter_gap_detected" — gap found; writes output_path.with_suffix('.repair.md')
    - "stale_source_detected" — source plan is stale
    """
    content = plan_path.read_text(encoding="utf-8")
    # ... transform content ...
    output_path.write_text(derived, encoding="utf-8")
    return "derived_plan_written"
```

2. **Register** in `tools/workflow_cli/adapters/__init__.py`:

```python
ADAPTER_REGISTRY: dict[str, str] = {
    "superpowers": "tools.workflow_cli.adapters.superpowers",
    "<name>": "tools.workflow_cli.adapters.<name>",
}
```

3. **Add tests** in `tests/test_adapters_<name>.py`. See `tests/test_adapters_superpowers.py` for the pattern.

Adapter contract rules (from `tools/workflow_cli/adapters/README.md`):
- Never mutate the source PLAN artifact.
- Write a `.repair.md` file (not raise) when content is unadaptable.
- Return exactly one of the four result strings.

## Extending the Tier Keyword Bank

Keywords live in `tools/workflow_cli/tier_keywords.yaml`. Structure:

```yaml
migration:
  - migrate
  - 迁移
cross_project:
  - cross-service
  - 跨项目
safety:
  - auth
  - 鉴权
dependency:
  - upgrade
  - 升级
scope_expanding:
  - rewrite
  - 重写
```

Rules:
- Each modifier (`migration`, `cross_project`, `safety`, `dependency`, `scope_expanding`) maps to a list of keyword strings.
- Matching is case-insensitive substring match on the requirement text.
- Add both English and Chinese variants when applicable.
- After editing, run `tests/test_tier.py` to verify existing tests still pass.

## State Machine Reference

Valid run status transitions (from `models.py` `ALLOWED_TRANSITIONS`):

```
not_started → active_stage_draft
active_stage_draft → entry_gate_failed | quality_gate_failed | ready_for_checkpoint_review
entry_gate_failed → active_stage_draft
quality_gate_failed → active_stage_draft
ready_for_checkpoint_review → checkpoint_review
checkpoint_review → checkpoint_changes_requested | checkpoint_approved | upstream_gap_routing
checkpoint_changes_requested → active_stage_draft
upstream_gap_routing → active_stage_draft
checkpoint_approved → next_stage | closed_at_plan_checkpoint
next_stage → active_stage_draft
```

## Artifact Filename Map

| Stage | File |
|---|---|
| `raw_requirement` | `00-raw-requirement.md` |
| `requirement_brief` | `03-requirement-brief.md` |
| `risk_discovery` | `04-risk-discovery.md` |
| `design` | `05-design.md` |
| `spec` | `06-spec.md` |
| `plan` | `07-plan.md` |

## Active Pointer

The active pointer at `.req-to-plan/.workflow-active` tracks the selected run for `r2p-*` shortcuts:

```
selected_work_id: WF-20260527-login-rate-limit
selected_run: .req-to-plan/WF-20260527-login-rate-limit/run.md
updated_at: 2026-05-27T12:00:00+00:00
reason: workflow_start
```

Functions in `agent_shortcuts.py`: `read_active_pointer(base_path)`, `write_active_pointer(base_path, work_id, reason)`.

## Common Pitfalls

- **Import PyYAML only where used** — system Python may lack it (PEP 668). Always test with `.venv/bin/python`.
- **`print_and_exit` calls `sys.exit`** — catch `SystemExit` when calling `cli.main()` from within `agent_shortcuts._run_cli()`.
- **`base_path` in tests** — always pass a `tempfile.TemporaryDirectory` path to isolate filesystem state.
- **Tier floor enforcement** — `TierEstimate.lock()` raises `ValueError` if the requested base is below the computed floor. Use `--override-floor --confirm` flags to bypass.
- **Terminal status check** — only `RunStatus.CLOSED_AT_PLAN_CHECKPOINT` is terminal. All other statuses are open.

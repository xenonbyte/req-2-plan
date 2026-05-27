# Design: Requirement-to-PLAN Agent Workflow

## Status
approved

## Date
2026-05-27

## Summary

Build a requirement-to-PLAN Agent workflow with a Python CLI state machine and a Claude Code Agent skill. The Agent drives the 5-stage pipeline (Requirement Brief → Risk Discovery → DESIGN → SPEC → PLAN), calling the CLI for state management and structured validation. Post-PLAN, the CLI adapts the neutral PLAN into a Superpowers-executable plan.

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Agent (Claude Code Skill)              │
│  - 理解 workflow 文档语义                                  │
│  - 生成 Requirement Brief / DESIGN / SPEC / PLAN 内容     │
│  - 执行 Quality Gate 语义检查                              │
│  - 执行 Checkpoint Review                                │
│  - 处理 upstream gap 路由决策                              │
│  - 用户交互（确认 acceptance、设计选择、checkpoint 审批）    │
└──────────────────────┬──────────────────────────────────┘
                       │ JSON stdin/stdout
┌──────────────────────┴──────────────────────────────────┐
│                  CLI 状态机 (Python)                       │
│  - run.md 读写、状态转换验证                                │
│  - artifact 生命周期管理（版本、stale、superseded）          │
│  - 结构化 gate 检查（引用完整性、ID 唯一性、closure 覆盖）    │
│  - 路径解析、dry-run、确认门禁                              │
│  - PLAN → Superpowers 适配                                │
└──────────────────────┬──────────────────────────────────┘
                       │ 文件读写
┌──────────────────────┴──────────────────────────────────┐
│              .req-to-plan/<work-id>/                      │
│  run.md | 00-raw-requirement.md | ... | 07-plan.md       │
└─────────────────────────────────────────────────────────┘
```

### Layer Responsibilities

| Layer | Owns | Does NOT own |
|-------|------|-------------|
| Agent | Semantic content, gate judgment, checkpoint decisions, user interaction | File-level state management, artifact versioning |
| CLI | State machine, structured validation, file I/O, PLAN adaptation | Semantic quality judgments, content generation |

## Artifact Storage

```
.req-to-plan/
├── .workflow-active                          # workspace active pointer
└── <work-id>/                                # e.g. WF-20260527-login-rate-limit
    ├── run.md                                # run state record
    ├── 00-raw-requirement.md
    ├── 01-intake-brief.md
    ├── 02-requirement-discovery-notes.md
    ├── 03-requirement-brief.md
    ├── 04-risk-discovery.md
    ├── 05-design.md
    ├── 06-spec.md
    ├── 07-plan.md
    ├── superpowers-plan.md                   # post-PLAN adapter output
    └── reviews/
        └── <stage>-checkpoint-review-<n>.md
```

## CLI Module Structure

```
tools/workflow_cli/
├── __init__.py
├── __main__.py               # entry: python -m tools.workflow_cli
├── cli.py                    # argparse command routing
├── state.py                  # run.md read/write, state machine validation
├── artifact.py               # artifact lifecycle, version management
├── gates.py                  # structured gate checks
├── adapters/
│   ├── __init__.py
│   └── superpowers.py        # PLAN → Superpowers conversion
└── agent_shortcuts.py        # coyeme-workflow-* entry points
```

## CLI State Machine

### Run States

```
not_started → active_stage_draft → entry_gate_failed → quality_gate_failed
→ ready_for_checkpoint_review → checkpoint_review → checkpoint_changes_requested
→ upstream_gap_routing → checkpoint_approved → next_stage → closed_at_plan_checkpoint
```

### CLI validates state transitions; Agent decides when to transition.

## Agent Command Surface (User-Facing)

| Command | Purpose |
|---------|---------|
| `coyeme-workflow-start [--separate] "<requirement>"` | Start new workflow run |
| `coyeme-workflow-continue` | Continue active run to next stage/step |
| `coyeme-workflow-status [--all]` | Inspect run state, read-only |
| `coyeme-workflow-switch --work-id <id>` | Switch active pointer |
| `coyeme-workflow-adapt --executor superpowers` | Generate Superpowers plan |

### Continue Flow

`coyeme-workflow-continue` is the main command. The Agent:
1. Reads `run.md` and determines current stage and next allowed operation
2. Loads the relevant stage workflow document from `docs/`
3. Executes the appropriate step: entry gate, artifact production, quality gate, checkpoint review, or checkpoint decision
4. Calls CLI for state persistence and structured validation at each step
5. Stops and asks the user when confirmation is required

## Internal CLI Commands (Agent-Internal)

The Agent calls these via Bash. The user never invokes them directly.

Complete command matrix per `workflow-cli-adapter.md`: run (start/resume/close), stage (load/produce/update/ready), gate (entry/quality), review (checkpoint/merge), checkpoint decide, confirm (record/reject/link), subagent (dispatch/merge/review), gap (record/route/reimport), artifact mark-stale, status (run/stage/next/routes/artifacts), executor adapt.

## PLAN → Superpowers Adaptation

### Conversion Rules

| Neutral PLAN | Superpowers Plan |
|--------------|-----------------|
| `PLAN-TASK-*` Goal + Steps | Task description (preserve executor-neutral semantics) |
| `Spec References` | Attached as task context for traceability |
| `Change Type: preserve/no-op` | Verification-only task, no implementation change |
| `Verification` field | Per-task verification steps |
| `Execution Sequencing` | Task dependencies and execution order |
| `Rollback / Safety Plan` | Standalone safety check steps |
| `Stop / Escalation Conditions` | Plan-level stop rules |
| TDD steps (red/green/refactor) | Preserved as-is (Superpowers natively supports TDD) |

### Output

- Success: `.req-to-plan/<work-id>/superpowers-plan.md`
- Failure: `.req-to-plan/<work-id>/superpowers-plan.repair.md` with gap record

### Adapter Rules

- The adapter must not mutate the approved source PLAN
- If PLAN content is unadaptable (missing SPEC refs, ambiguous TDD applicability), the adapter records a repair request rather than guessing
- Target format references `superpowers:subagent-driven-development` skill conventions

## Key Design Decisions

1. **Agent + CLI layered architecture**: Agent handles semantics, CLI handles state
2. **`.req-to-plan/` as artifact root**: Hidden directory, not mixed with project docs
3. **Agent skill drives the workflow**: `coyeme-workflow-continue` as the primary interaction
4. **CLI is Agent-internal**: User never operates CLI commands directly
5. **Superpowers adapter is post-PLAN**: Occurs after `closed_at_plan_checkpoint`, does not mutate the neutral PLAN
6. **Workflow docs remain the source of truth**: Agent reads `docs/*.md` for stage-specific rules

## Scope

### In Scope
- Full CLI state machine with all command groups
- Agent skill (`req-to-plan`) implementing the 5-stage workflow
- PLAN → Superpowers adapter
- Structured gate validation (CLI) + semantic gate validation (Agent)
- Upstream gap detection and routing
- Subagent dispatch for parallel discovery (risk scan, checkpoint review)

### Out of Scope
- Executors other than Superpowers
- Concrete implementation execution after PLAN adaptation
- MCP/API/UI carriers (CLI only for now)
- Background agents or persistent services

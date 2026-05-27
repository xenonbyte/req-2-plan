# Requirement-to-PLAN Workflow

This folder defines a staged workflow for turning a raw requirement into an approved, executor-neutral implementation PLAN.

Use it when a request needs durable clarification, risk discovery, design decisions, behavior contracts, or a task plan that another agent or engineer can execute without re-deciding scope.

For very small low-risk work, use the same order with lightweight artifacts. Do not skip DESIGN; use a short DESIGN instead.

## Start Here

Run `r2p install --platform <your-platform>` once per platform to register the agent integration. See `workflow-install-surface.md` for the lifecycle binary.

1. Capture the raw requirement and produce a stable Requirement Brief.
2. Run Risk & Question Discovery to find blockers, assumptions, risks, discussion points, and downstream inputs.
3. Run DESIGN to choose one technical approach and resolve design blockers.
4. Run SPEC to convert approved DESIGN into testable behavior contracts.
5. Run PLAN to convert approved SPEC into executor-neutral tasks, sequencing, verification, rollback, and stop conditions.

Each artifact-producing stage must pass its Quality Gate before checkpoint review. Each downstream handoff requires Main/User Checkpoint approval.

Use `workflow-execution-guide.md` when operating a workflow run, resuming from a checkpoint, or routing an upstream gap.
Use `workflow-operation-surface.md` when designing or reviewing operation entry semantics for commands, tools, skills, APIs, or UI actions.
Use `workflow-command-surface.md` when mapping operation semantics into carrier-neutral command intents before designing concrete command syntax.
Use `workflow-cli-adapter.md` when designing a concrete CLI carrier for those command intents.
Use `workflow-agent-command-adapter.md` when exposing the workflow to agents as the compact project shortcuts `r2p-start`, `r2p-continue`, `r2p-status`, `r2p-switch`, and `r2p-adapt`.
Use `workflow-post-plan-adapter-surface.md` when designing post-PLAN executor adaptation entry points (`CMD-EXEC-*`).
Use `workflow-operator-runbook.md` when operating the local CLI end to end from raw requirement through PLAN closure.

## Document Map

| Need | Read |
|---|---|
| Operate the local CLI end to end from raw requirement to approved PLAN | `workflow-operator-runbook.md` |
| Run or resume the workflow, operate gates/checkpoints, route upstream gaps, and close a workflow run | `workflow-execution-guide.md` |
| Design operation entry semantics before choosing CLI, slash command, MCP, API, skill, or UI carriers | `workflow-operation-surface.md` |
| Map operation semantics into carrier-neutral command intents before designing concrete CLI, slash command, MCP, API, skill, or UI syntax | `workflow-command-surface.md` |
| Design concrete CLI command names, flags, output, dry-run, confirmation, and exit semantics | `workflow-cli-adapter.md` |
| Expose the workflow to agents as `r2p-*` project shortcuts | `workflow-agent-command-adapter.md` |
| Design post-PLAN executor adaptation command intents (`CMD-EXEC-*`) | `workflow-post-plan-adapter-surface.md` |
| Install, uninstall, verify, or audit the `r2p` lifecycle binary on a host | `workflow-install-surface.md` |
| Cross-stage rules, artifact lifecycle, upstream routing, shared definitions, and concept index | `workflow-invariants.md` |
| Requirement capture, discovery, assumptions, source provenance, acceptance, and scope inventory | `requirement-brief-workflow.md` |
| Blocking questions, assumptions, risk priority, design triggers, spec inputs, and plan inputs | `risk-question-discovery-workflow.md` |
| Approach selection, boundaries, migration, rollback, compatibility, verification architecture, and handoff schemas | `design-workflow.md` |
| Behavior contracts, design coverage import, boundary contracts, acceptance scenarios, and PLAN inputs | `spec-workflow.md` |
| Executor-neutral task breakdown, TDD decomposition, sequencing, verification, rollback, and stop conditions | `plan-workflow.md` |

## Default Artifact Layout

Store workflow artifacts under:

```text
.req-to-plan/<work-id>/
```

Default files:

```text
run.md
00-raw-requirement.md
01-intake-brief.md
02-requirement-discovery-notes.md
03-requirement-brief.md
04-risk-discovery.md
05-design.md
06-spec.md
07-plan.md
reviews/<stage>-checkpoint-review-<n>.md
```

Approved artifacts should not be overwritten. Create a new version when upstream approved input changes.

## Common Statuses

| Status | Meaning |
|---|---|
| `ready` | The stage artifact can enter checkpoint review. |
| `approved` | Main/User Checkpoint froze this artifact for downstream use. |
| `changes_requested` | The artifact must be revised before handoff. |
| `blocked` | The owning zero-blocker stage must resolve a requirement or design blocker. |
| `upstream_gap_detected` | A downstream stage found missing upstream input it cannot decide. |
| `route_upstream` | Checkpoint authorization sends work back to the responsible upstream stage. |

## Non-Negotiables

- Requirement Brief does not choose design.
- DESIGN does not redefine requirements.
- SPEC does not invent missing design decisions.
- PLAN does not invent missing contracts or choose executor-specific format.
- Subagents produce evidence and recommendations, not checkpoint approval.
- Cross-project work must use explicit source provenance and integration boundaries.
- Upstream repairs require the repaired stage to pass Quality Gate and Checkpoint again before downstream artifacts can be approved.

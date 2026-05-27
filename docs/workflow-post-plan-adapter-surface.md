# Workflow Post-PLAN Adapter Surface

## Purpose

This document defines the carrier-neutral command intent layer for post-PLAN executor adaptation.

The requirement-to-PLAN workflow stops at an executor-neutral PLAN. Post-PLAN adaptation converts an approved PLAN into an executor-specific derived plan (e.g. Superpowers). It is intentionally outside the requirement-to-PLAN `CMD-*` state machine, but it must still expose a stable, auditable surface so the carrier layers (CLI, agent shortcut, MCP, API, UI) can map to it without inventing new authority.

Use this document when designing or reviewing any post-PLAN executor adaptation entry point.

## Scope

This document covers:

- The post-PLAN command intent catalog (`CMD-EXEC-*`).
- Required inputs, preconditions, allowed writes, stop conditions, and result classes for each intent.
- The authority boundary that separates post-PLAN adaptation from the requirement-to-PLAN state machine.
- The relationship to the CLI adapter, agent command adapter, and approved PLAN artifact.

This document does not cover:

- Concrete CLI, slash command, MCP, API, skill, or UI syntax.
- Executor runtime implementation (Superpowers, GSD, or other executors).
- Actual implementation execution after adaptation.

## Authority Boundary

Post-PLAN adaptation:

- Reads the approved PLAN artifact and (when relevant) the source run's `run.md`.
- Writes a derived executor plan file plus an optional repair-request file under the source run's artifact root.
- Does not mutate the approved source PLAN, any other source-run artifact, or `run.md` status.
- Does not change requirement-to-PLAN run state or approved checkpoint records.
- Does not execute the derived plan.

A post-PLAN command surface entry must never:

- Approve or re-approve a requirement-to-PLAN checkpoint.
- Open, route, or close a requirement-to-PLAN upstream gap.
- Promote a `closed_at_plan_checkpoint` run back into an open run.
- Inject executor-specific runtime, command, or prompt format into the approved PLAN.

## Post-PLAN Command Intent Catalog

### `CMD-EXEC-ADAPT`

**Purpose**
Convert the approved PLAN of a terminal run into an executor-specific derived plan.

**Required Inputs**
- Terminal run identifier (work ID or run record path).
- Target executor name (e.g. `superpowers`).
- Approved PLAN artifact reference. Defaults to the approved PLAN recorded in the run's Approved Checkpoints table when not supplied.
- Output path for the derived plan. Defaults to `.req-to-plan/<work-id>/<executor>-plan.md`.

**Preconditions**
- The source run's `run.md` status is `closed_at_plan_checkpoint`.
- The Main/User PLAN Checkpoint is `approved`.
- No open route remains on the source run.
- The approved PLAN artifact is reachable and not marked `stale` or `superseded`.
- A registered adapter exists for the target executor.

**Allowed Artifact Writes**
- `<output>` on success.
- `<output>.repair.md` when the adapter detects an unadaptable PLAN.

**run.md Updates**
None. The source run is not mutated.

**User Confirmation Required**
Conditional. Required when the operator chooses to overwrite an existing derived plan or repair-request file.

**Stop Conditions**
- Run is not terminal.
- PLAN Checkpoint is not approved.
- Open route remains.
- Approved PLAN artifact is missing, unreachable, stale, or superseded.
- Target executor adapter is not registered.
- PLAN content is unadaptable (missing SPEC references, empty Task Breakdown, ambiguous TDD applicability, missing verification, or missing rollback/safety where required by adapter rules).

**Forbidden Behavior**
- Do not mutate the approved source PLAN.
- Do not change `run.md` status or Approved Checkpoints.
- Do not execute the derived plan.
- Do not infer missing SPEC references or rollback handling — emit a repair request instead.
- Do not switch the workspace active pointer.

**Result / Output**
`derived_plan_written`, `adapter_gap_detected`, `stale_source_detected`, `unsupported_executor`, or `run_not_terminal`.

### `CMD-EXEC-LIST-ADAPTERS`

**Purpose**
List registered executor adapters and their adapter rule versions.

**Required Inputs**
None.

**Preconditions**
None.

**Allowed Artifact Writes**
None.

**run.md Updates**
None.

**User Confirmation Required**
No.

**Stop Conditions**
None for read; report registry errors instead of writing.

**Forbidden Behavior**
- Do not mutate artifacts or `run.md`.

**Result / Output**
List of registered executor names, adapter rule versions, and registry status.

## Repair Request Shape

When `CMD-EXEC-ADAPT` returns `adapter_gap_detected` or `stale_source_detected`, the adapter must write a Post-PLAN Gap Repair Request to `<output>.repair.md` with at least:

```markdown
# Post-PLAN Gap Repair Request

## Source Run
<work-id> / <run.md path>

## Source PLAN
<approved PLAN artifact and version>

## Target Executor
<executor name>

## Gap
What is missing, ambiguous, or stale.

## Required Action
What must change in the source run (PLAN repair, route, or supersession) before adaptation can succeed.

## Owner
requirement_brief | risk_discovery | design | spec | plan | post_plan
```

A repair request does not authorize PLAN repair. If the repair owner is a requirement-to-PLAN stage, the operator must follow `workflow-invariants.md#upstream-gap-routing-rule` to open a new working version of the source run (or a derived run) instead of editing approved artifacts.

## Operation Coverage Matrix

Every post-PLAN command intent must be covered by an operator-facing carrier or explicitly marked internal-only.

| Post-PLAN Command Intent | Carrier (default) | Coverage |
|---|---|---|
| `CMD-EXEC-ADAPT` | CLI `workflow executor-adapt`; agent shortcut `r2p-adapt` | Covered |
| `CMD-EXEC-LIST-ADAPTERS` | CLI `workflow executor-list-adapters` | Covered |

## Adapter Design Rules

Concrete adapter implementations (e.g. `adapters/superpowers.py`) must:

- Map exactly to one `CMD-EXEC-*` intent.
- Preserve approved PLAN traceability: SPEC references, Change Type, Verification, and Rollback/Safety must remain attached to each derived task.
- Preserve executor-neutral PLAN content in the source artifact; transformations apply only to the derived output.
- Record adapter rule version in the derived plan header so re-runs are auditable.
- Fail loudly on ambiguity by writing a repair request rather than guessing.

## Adding A New Executor Adapter

To add a new executor adapter, follow the per-adapter README at `tools/workflow_cli/adapters/README.md`. The README documents the adapter module shape, the registration entry, the adapter rule version string, the derived-plan header schema, and the repair-request emission contract. Adapter authors must keep the executor-neutral PLAN content untouched and emit a Post-PLAN Gap Repair Request rather than guess missing source content.

## Non-Goals

This document intentionally does not define:

- Concrete CLI flag syntax, slash command grammar, MCP schema, or UI labels.
- Executor runtime implementation.
- Conversion rules for any specific executor (those belong to the adapter's own design notes under `adapters/<executor>/`).
- New requirement-to-PLAN authority.

Carrier-specific designs that expose these intents must preserve the authority boundary defined above.

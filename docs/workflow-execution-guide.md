# Workflow Execution Guide

## Purpose

This document defines how an agent runs the requirement-to-PLAN workflow from start to finish.

It is a workflow run protocol. It does not replace the stage workflow documents and does not define executor-specific commands, prompt formats, orchestration frameworks, or implementation execution.

Use this guide when starting, resuming, routing, reviewing, or closing a workflow run.

## Scope

This guide covers:

- Creating and resuming a workflow run.
- Loading upstream approved artifacts.
- Running entry gates, Quality Gates, and checkpoint reviews.
- Producing and updating stage artifacts.
- Routing `upstream_gap_detected` and `route_upstream`.
- Recovering from context compaction, interruption, or agent handoff.
- Handling subagents and user confirmations.
- Keeping artifacts, statuses, and downstream authorization consistent.

This guide does not cover:

- Concrete command names.
- Executor-specific prompt or task format.
- GSD, Superpowers, or any runtime adapter.
- Actual code implementation after PLAN approval.
- Automation scripts for enforcing the workflow.

## Workflow Run Model

A workflow run is one durable attempt to convert a raw requirement into an approved executor-neutral PLAN.

Recommended run record:

```text
.req-to-plan/<work-id>/run.md
```

Run record fields:

```markdown
# Workflow Run: <work-id>

## Status
not_started | active_stage_draft | entry_gate_failed | quality_gate_failed | ready_for_checkpoint_review | checkpoint_review | checkpoint_changes_requested | upstream_gap_routing | checkpoint_approved | next_stage | closed_at_plan_checkpoint

## Current Stage
raw_requirement | requirement_brief | risk_discovery | design | spec | plan | closed

## Approved Checkpoints
| Stage | Artifact | Version | Approved At | Downstream Authorization |
|---|---|---|---|---|

## Active Artifacts
| Stage | Artifact | Version | Status |
|---|---|---|---|

## Stale / Superseded Artifacts
| Artifact | Reason | Replaced By | Required Action |
|---|---|---|---|

## Open Routes
| Route ID | From Stage | Owner Stage | Required Action | Status |
|---|---|---|---|---|

## User Confirmations
| Confirmation | Stage | Source | Recorded In |
|---|---|---|---|

## Resume Context
| Field | Value |
|---|---|
| Last Completed Operation | <canonical operation, gate, or checkpoint> |
| Next Allowed Operation | <canonical operation or operation intent> |
| Active Item | <stage item ID, PLAN task ID, or artifact section> |
| Required Reread Targets | <artifact>@<version>#<section-or-id> entries to reload before continuing |
| Resume Reason | context_compaction, interruption, agent_handoff, manual_resume, active_run_refresh |
```

The run record is an execution aid. The stage artifacts remain the source of truth for stage content and checkpoint approval.

## Executable Stage Sequence

The executable run state sequence is:

```text
raw_requirement -> requirement_brief -> risk_discovery -> design -> spec -> plan
```

`Intake Brief v0` and `Requirement Discovery Notes` are Requirement Brief content records. They are not independent run `Current Stage` values and do not receive their own checkpoint approvals.

`Design Entry Gate` and `Design Scope Gate` are DESIGN-owned gates. They may appear as sections or gate evidence inside the DESIGN artifact, but the run `Current Stage` remains `design`.

## Run States

```text
not_started
  -> active_stage_draft
  -> entry_gate_failed
  -> quality_gate_failed
  -> ready_for_checkpoint_review
  -> checkpoint_review
  -> checkpoint_changes_requested
  -> upstream_gap_routing
  -> checkpoint_approved
  -> next_stage
  -> closed_at_plan_checkpoint
```

State meanings:

| State | Meaning | Allowed next action |
|---|---|---|
| `not_started` | No run record or stage artifact exists yet. | `start_workflow_run` |
| `active_stage_draft` | A stage artifact is being produced or revised. | Continue drafting or run gate. |
| `entry_gate_failed` | The stage cannot start from current upstream inputs. | Route to required upstream stage. |
| `quality_gate_failed` | Current stage artifact is incomplete. | Return to the owning stage step. |
| `ready_for_checkpoint_review` | Quality Gate is ready, but checkpoint review has not started. | Run checkpoint review. |
| `checkpoint_review` | Quality Gate is ready and checkpoint review is running, or merged findings are waiting for Main/User checkpoint decision. | Merge review findings, or decide the checkpoint after findings are merged and required confirmations are ready. |
| `checkpoint_changes_requested` | Checkpoint review found required changes. | Revise artifact and rerun Quality Gate. |
| `upstream_gap_routing` | Current stage found a missing upstream input it cannot decide. | Record route, repair upstream, re-import downstream. |
| `checkpoint_approved` | Main/User approval froze the artifact for downstream use. | Authorize next stage. |
| `next_stage` | The next stage is ready to start from approved inputs. | Run next stage entry gate. |
| `closed_at_plan_checkpoint` | PLAN Checkpoint is approved and this workflow is complete. | Hand off to a later execution workflow if needed. |

Only `checkpoint_approved` authorizes formal downstream handoff. `ready` and `ready_for_checkpoint_review` mean the current artifact can be reviewed; they do not authorize the next stage by themselves.

## Tier Lifecycle

Tier is governed by `workflow-invariants.md#workflow-complexity-tier-rule`. This section defines when each tier event happens during a run.

- Tier is estimated at `run-start`, immediately after repo baseline scan and link expansion. The Evidence Block produced by `estimate_tier` is written to `run.md` before the operator interacts with the Intake Brief.
- Tier is locked between `run-start` and the Requirement Brief stage entry gate. The Agent surfaces the Evidence Block to the user; the user confirms via `tier-lock` (or `lock_tier` semantically) before any `stage-produce` runs for `requirement_brief`. A `stage-produce` call against `requirement_brief` without a recorded Tier Lock is refused.
- Tier is escalated as needed during any subsequent stage via `tier-escalate`. Each escalation appends a modifier, revokes affected bundled checkpoints, and is audit-logged in `run.md`.
- Tier is frozen at run close. `close_workflow_run` records the final tier as immutable run metadata; downstream reopen runs receive a new tier estimation and lock.
- Tier lock is required before `gate-quality` runs with full tier-aware section checks. Without a Tier Lock, `gate-quality` runs only an Upstream-References minimal check and emits a stop suggesting `tier-lock`. The minimal check never substitutes for the full Quality Gate; downstream checkpoint review and approval remain blocked until the full gate has been satisfied against a locked tier.

## Context Resume Contract

`Resume Context` is a lightweight resume index. It is not a memory system and is not a source of truth.

The workflow does not assume an agent can reliably detect context compaction. Apply this contract when the runtime explicitly reports `context_compaction`, `interruption`, `agent_handoff`, or `manual_resume`, or when the agent cannot prove the active run context is already loaded.

Apply this contract before continuing when:

- The runtime reports that conversation or model context was compacted.
- The workflow was interrupted and later resumed.
- A different agent or session resumes the run.
- `run.md` and the current dialogue disagree.
- The active artifact is stale, superseded, or not loaded.
- The active item is unclear from current context.

Active run context is proven loaded only when the agent has loaded `run.md`, the active artifact and active item, required reread targets, open routes, and stale/superseded markers. Conversation-only memory is not proof.

If `Resume Context` is missing, `Resume Workflow Run` may rebuild it from `run.md`, active artifact metadata, and open routes only when those sources identify the active item and required reread targets unambiguously. If they do not, stop and record a missing resume target.

Minimum reread set:

1. `run.md`.
2. The active artifact header, status, and active item section.
3. Upstream stable IDs referenced by the active item.
4. Open routes plus stale or superseded markers.
5. The stage workflow section needed for the next allowed operation.

Write each `Required Reread Targets` entry as `<artifact>@<version>#<section-or-id>` when the artifact version is known. If the version is unknown, `Resume Workflow Run` must resolve it from the artifact header before continuing.

PLAN task resume rule:

- If the active item is a PLAN task, reread the full task section before continuing it.
- Also reread referenced SPEC IDs, verification steps, rollback notes, and stop/escalation conditions for that task.
- Do not reread the full PLAN unless the active task is missing, references are incomplete, or artifact versions conflict.

Resume rules:

- Treat approved stage artifacts as authoritative when `Resume Context` conflicts with artifact content.
- Record the inconsistency in `run.md` and stop or route instead of guessing.
- Do not use conversation-only memory as approval, source provenance, or downstream authorization.
- Keep `Required Reread Targets` narrow enough to restore the active item, not the whole workflow history.

## Canonical Operations

These operations are semantic. They are not command names.

| Operation | Purpose | Required input | Output |
|---|---|---|---|
| `start_workflow_run` | Create the run record and initial artifact root. | Raw requirement or source reference. | Run record with `active_stage_draft`. |
| `load_or_create_artifact` | Open the current stage artifact or create its draft. | Work ID, stage, upstream references. | Draft artifact with header and upstream references. |
| `run_stage_entry_gate` | Confirm the stage may start from approved upstream input. | Required upstream checkpoints and references. | `pass`, `blocked`, `return_to_*`, or `upstream_gap_detected`. |
| `produce_stage_artifact` | Draft or update the current stage artifact. | Stage workflow document and approved upstream artifacts. | Draft artifact content. This does not by itself mark the artifact ready. |
| `mark_stage_artifact_ready` | Record an explicit author readiness assertion on the current active draft artifact so Quality Gate evaluation can run. | Current active draft artifact and stage readiness assertion. | Updated artifact frontmatter or status block plus `run.md` Resume Context refresh. Does not pass Quality Gate or approve any checkpoint. |
| `run_quality_gate` | Check whether the stage artifact is internally complete. | Current artifact. | `ready`, `blocked`, `return_to_*`, or `upstream_gap_detected`. |
| `run_checkpoint_review` | Review a ready artifact before downstream authorization. | Ready artifact and optional subagent reviews. | Review findings and recommendation. |
| `merge_checkpoint_review_findings` | Merge checkpoint review findings without granting checkpoint approval. | Review findings, optional checkpoint-review subagent findings, ready artifact, and conflict rules. | Merged review summary, preserved conflicts, required confirmations, required changes, or routing actions. |
| `approve_checkpoint` | Freeze the artifact for downstream use. | Ready artifact, merged review findings, user confirmations where needed. | `approved` checkpoint and downstream authorization. |
| `route_upstream` | Send missing or conflicting input to the owner stage. | Upstream Gap Record or checkpoint route. | Run state `upstream_gap_routing`. |
| `resume_from_checkpoint` | Continue from the latest approved checkpoint or active draft after pause, repair, context compaction, interruption, or agent handoff. | Run record, approved artifact versions, and required reread targets. | Active stage draft, next stage, or upstream gap routing. |
| `record_user_confirmation` | Record a user-owned confirmation, rejection, or clarification that affects downstream authorization. | Confirmation source, owning stage, affected artifact section. | Stage artifact and run record confirmation entry. |
| `dispatch_subagent_work` | Start allowed discovery or checkpoint-review subagent work. | Stage rules, scope, sources, and allowed subagent task type. | Subagent finding or review artifact. |
| `merge_subagent_findings` | Merge subagent findings without granting checkpoint approval. | Subagent outputs and current stage artifact. | Merged findings, preserved conflicts, and routing actions. |
| `inspect_workflow_run` | Read run state, artifact versions, open routes, and next allowed operation without writing artifacts. | Run record and artifact root. | Read-only status report. |
| `close_workflow_run` | End the workflow after PLAN approval. | Approved PLAN Checkpoint. | Run state `closed_at_plan_checkpoint`. |
| `estimate_tier` | Run tier estimation (L1-L5 layers) before tier lock. | Raw requirement, link expansion result, repo baseline scan, and keyword scan output. | TierEstimate including the Evidence Block; fails if the Evidence Block is incomplete. |
| `lock_tier` | Lock tier after user confirms the Evidence Block. | TierEstimate, user confirmation, and optional `--override-floor` reason. | Writes Tier Lock to `run.md`; required before `gate-quality` runs with full tier-aware section checks. |
| `escalate_tier` | Add a modifier to a locked tier. | Locked tier, new modifier signal or operator request, and reason. | Appends the modifier, revokes affected bundled checkpoints, and logs the escalation in `run.md`. |
| `authorize_bundled_checkpoints` | Bundle-approve multiple eligible checkpoint stages at once. | Tier with no modifier (or `light` + no modifier through DESIGN), Quality Gate `ready` on each bundled stage, and required user confirmation. | Writes BundleAuthorization in `run.md`; only allowed for eligible tier+modifier combos. |
| `reopen_workflow_run` | Copy a closed run to a new `<id>-rN` run from a specified stage. | Source `closed_at_plan_checkpoint` run, target start stage, and reopen reason. | Source run stays frozen; new run inherits a lineage reference and starts at the requested stage. |

## Stage Execution Loop

Use this loop for every artifact-producing stage:

```text
1. Load the latest approved upstream artifacts.
2. Load or create the current stage artifact.
3. Run the stage entry gate when the stage defines one.
4. Produce or update the stage artifact using the stage workflow document.
5. Run the stage Quality Gate.
6. If Quality Gate fails because current-stage work is incomplete, return to the owning stage step.
7. If Quality Gate finds upstream missing input, record `upstream_gap_detected` and route upstream.
8. When Quality Gate is ready, set run state to `ready_for_checkpoint_review`.
9. Run checkpoint review.
10. Merge checkpoint review findings.
11. Record required user confirmations.
12. Approve or reject the Main/User Checkpoint.
13. If approved, update the run record and authorize the next stage.
```

Stage-specific workflow documents own the content of each artifact. This guide owns the order of operations.

In concrete CLI operation, `produce_stage_artifact` records or appends artifact content and leaves readiness to the artifact author plus Quality Gate. The author or reviewing agent must set an explicit artifact status only when the stage workflow's ready criteria are actually satisfied.

## Artifact Handling

Use `workflow-invariants.md#artifact-lifecycle-rule` for artifact storage and versioning.

Execution rules:

- Create or update `run.md` when the run starts, pauses, routes upstream, resumes, approves a checkpoint, or closes.
- Refresh `Resume Context` when the active item changes, a run pauses, a route opens, a checkpoint is approved, or a different agent/session resumes the run.
- Keep stage artifacts under `.req-to-plan/<work-id>/` unless a repository-local convention overrides it.
- Draft artifacts may be edited in place before checkpoint approval.
- A stage artifact can express gate status with frontmatter `status: ready`, a `## Status` section whose first line is `ready`, or a bullet `- Status: ready`. Placeholder choices such as `ready | blocked` are not a status.
- Approved artifacts must not be overwritten.
- When approved upstream input changes, mark downstream artifacts that imported the old version as `stale` or `superseded`.
- A downstream artifact may be updated incrementally only when all imported upstream IDs can be remapped and no downstream decision conflicts with the repaired upstream input.
- If remapping is incomplete, unclear, or conflict-bearing, rebuild the downstream artifact from the repaired upstream checkpoint.

## Gate And Checkpoint Procedure

Entry Gate:

- Confirms the stage is allowed to start.
- Uses approved upstream artifacts only.
- Fails fast when required upstream checkpoint approval, source provenance, or required input is missing.

Quality Gate:

- Checks internal completeness of the current stage artifact.
- Returns to the current-stage step when the current artifact is incomplete.
- Marks `upstream_gap_detected` when the current stage lacks authority to decide the missing input.
- Must be `ready` before checkpoint review starts.

Checkpoint Review:

- May be performed by subagents when the stage allows or requires it.
- Produces findings and recommendations only.
- Does not approve downstream handoff.

Main/User Checkpoint:

- Verifies review findings are merged.
- Records required user confirmations.
- Freezes the current artifact when approved.
- Is the only operation that authorizes the next stage.
- Records `checkpoint_approved`; closing the workflow is a separate `close_workflow_run` operation after PLAN approval.

## Upstream Gap Procedure

Use `workflow-invariants.md#upstream-gap-routing-rule`.

When a stage detects an upstream gap:

```text
1. Stop downstream authorization.
2. Record an Upstream Gap Record in the current artifact.
3. Set the current artifact status to `upstream_gap_detected` or checkpoint status to `route_upstream`.
4. Identify the owner stage and exact artifact sections that must change.
5. Update `run.md` with state `upstream_gap_routing`.
6. Return to the owner stage.
7. Repair the owner artifact.
8. Rerun the owner stage Quality Gate.
9. Rerun the owner stage Main/User Checkpoint.
10. Re-import repaired upstream input into downstream artifacts.
11. Mark old imported versions as stale or superseded.
12. Rerun downstream Quality Gate and Checkpoint before handoff.
```

Do not fill an upstream gap with an assumption unless the owner stage explicitly classifies that assumption as non-blocking and records its carry target.

## Subagent Procedure

There are two subagent modes:

```text
discovery subagent: gathers evidence before a stage artifact is finalized.
checkpoint review subagent: reviews a ready artifact before Main/User Checkpoint.
```

Rules:

- Subagents produce evidence, findings, and recommendations.
- Subagents do not approve checkpoints.
- The main agent merges subagent findings.
- Conflicts must be preserved until resolved by evidence, routed to the owning stage, or sent to User Decision Gate when human judgment is required.
- If subagent output changes scope, design decisions, SPEC contracts, or PLAN tasks outside that stage's authority, treat it as a routing issue instead of silently accepting it.

## User Confirmation Procedure

Record user confirmations in the stage artifact and in `run.md` when they affect downstream authorization.

User confirmation is required for:

- Confirming, rejecting, or supplementing acceptance candidates in Requirement Brief.
- Requirement scope, non-scope, source provenance, or constraints that cannot be inferred safely.
- High-cost, compatibility-changing, irreversible, destructive, dependency-critical, or preference-sensitive DESIGN choices.
- Explicit acceptance of P0 risks.
- Main/User Checkpoint approval for downstream authorization.
- PLAN sequencing, rollback, safety, or verification choices when they materially affect execution risk.

Do not treat a user preference as an approved design decision unless the owning stage records it as such.

## Parallel Work Boundaries

Use `workflow-invariants.md#parallel-work-rule`.

Allowed:

- Subagent discovery inside a stage after the stage entry gate passes.
- Independent checkpoint reviews after the stage Quality Gate is `ready`.
- Evidence gathering for a later stage when it does not create an authoritative downstream artifact.
- Scratch downstream drafting when clearly marked `unapproved` and re-imported from approved upstream artifacts before Quality Gate.

Forbidden:

- Approving a checkpoint before required upstream checkpoint approval exists.
- Treating speculative downstream drafts as approved artifacts.
- Starting execution from a PLAN before PLAN Checkpoint approval.
- Letting parallel work bypass upstream repair after an upstream input changes.

## Command Mapping Boundary

This guide intentionally defines operations, not commands.

Operation surface design may map user-facing or agent-facing intent to canonical operations, for example:

```text
operation intent -> canonical operation -> stage workflow document -> artifact update
```

Use `workflow-operation-surface.md` for operation-entry semantics before choosing any carrier-specific command, tool, skill, API, or UI shape.

Carrier design must preserve these constraints:

- Commands must not skip required Quality Gates or Checkpoints.
- Commands must not approve downstream handoff without Main/User Checkpoint approval.
- Commands must not hide `upstream_gap_detected`.
- Commands must remain executor-neutral until a separate executor adapter workflow is defined.

Do not add concrete command names to this guide. Concrete carrier syntax belongs to a later adapter design.

## Run Completion

The requirement-to-PLAN workflow is complete when:

- PLAN Quality Gate is `ready`.
- Main/User PLAN Checkpoint is `approved`.
- `run.md` records `closed_at_plan_checkpoint`.
- All approved artifacts referenced by PLAN are available and not stale.
- No open upstream route remains.

This workflow stops at an executor-neutral PLAN. Actual implementation, orchestration, or runtime command formatting belongs to a later execution workflow.

## Operator Checklist

Before moving to the next stage:

- Required upstream checkpoint is approved.
- Current artifact has upstream references and artifact status.
- Quality Gate result is recorded.
- Checkpoint review findings are merged or routed.
- User confirmations are recorded where required.
- Downstream authorization is explicit.
- `run.md` reflects the current stage, artifact versions, stale artifacts, and open routes.

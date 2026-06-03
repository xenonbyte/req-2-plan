# Workflow Operation Surface

## Purpose

This document defines the operation-entry semantics for the requirement-to-PLAN workflow.

It maps user or agent intent to the canonical operations in `workflow-execution-guide.md#canonical-operations`. It does not define concrete CLI commands, slash commands, MCP tools, API endpoints, UI controls, prompt formats, or executor adapters.

Use this document when designing or reviewing any user-facing, agent-facing, or tool-facing entry point that operates the workflow.

## Scope

This document covers:

- Operation groups and operation intents.
- Required inputs and preconditions for each operation.
- Which artifacts an operation may write.
- How an operation may update `run.md`.
- When user confirmation is required.
- When an operation must stop.
- Safety rules for operation carriers.

This document does not cover:

- Concrete command names or flags.
- Carrier-specific syntax.
- Runtime adapter implementation.
- Executor-specific task formats.
- Actual implementation after PLAN approval.

Post-PLAN executor-specific adaptation is out of scope for the requirement-to-PLAN workflow.

## Operation Carrier Boundary

An operation semantic can be carried by many surfaces:

```text
CLI
slash-style command
agent skill
MCP tool
API endpoint
UI action
natural-language instruction pattern
```

This document does not choose a carrier. Carrier-specific designs must map back to the operation semantics in this document and to the canonical operations in `workflow-execution-guide.md`.

Carrier designs must not:

- Skip required Quality Gates or Checkpoints.
- Hide `upstream_gap_detected`.
- Rewrite approved artifacts.
- Start downstream work from stale or superseded artifacts.
- Convert executor-neutral PLAN content into executor-specific instructions.

## Operation Groups

| Group | Purpose |
|---|---|
| Run Lifecycle Operations | Start, resume, reopen, and close a workflow run. |
| Tier Operations | Estimate, lock, escalate the workflow complexity tier; bundle eligible checkpoints. |
| Stage Operations | Load, create, produce, or update stage artifacts. |
| Gate / Checkpoint Operations | Run entry gates, Quality Gates, checkpoint reviews, and Main/User checkpoint approval. |
| User Confirmation Operations | Record user-owned confirmations, rejections, and clarification requests. |
| Subagent Operations | Dispatch allowed subagent work and merge subagent outputs without granting approval. |
| Routing / Resume Operations | Record upstream gaps, route to owner stages, re-import repaired upstream artifacts, and mark downstream artifacts stale or superseded. |
| Inspection / Status Operations | Inspect run state, artifact versions, open routes, stale/superseded artifacts, and next allowed operation. |

## Operation Contract Schema

Every operation semantic must be specified with this schema:

```markdown
### <Operation Intent>

**Canonical Operations**
Canonical operation names from `workflow-execution-guide.md#canonical-operations`.

**Required Inputs**
Inputs required before the operation can run.

**Preconditions**
State, checkpoint, artifact, or authorization conditions required before running.

**Allowed Artifact Writes**
Artifacts or sections the operation may create or update.

**run.md Updates**
Run record fields this operation may update.

**User Confirmation Required**
Whether the operation needs explicit main/user confirmation.

**Stop Conditions**
Conditions that make the operation stop instead of guessing or continuing.

**Forbidden Behavior**
Actions the operation must never perform.

**Result / Output**
Allowed operation result, output, or resulting run/artifact status. Only `run.md Updates` defines run-state writes.
```

Carrier-specific command specs may add syntax fields later, but they must preserve this semantic contract.

## Resume Context Maintenance Rule

Before any write-capable operation continues an active workflow run, the operator must be able to prove the active run context is loaded: `run.md`, active artifact, active item, required reread targets, open routes, and stale/superseded markers. If this cannot be proven, run `Resume Workflow Run` first. `Resume Workflow Run` and read-only inspection operations are allowed to run without this proof because they establish it.

Any operation that writes `run.md` and changes current stage, active artifact, active item, next allowed operation, open route, stale/superseded marker, checkpoint status, or route closure must refresh `Resume Context`.

Refresh means recording last completed operation, next allowed operation, active item, versioned required reread targets, and resume reason when applicable. Read-only operations must not update `Resume Context`.

When no narrower item exists, use the smallest stable container as `Active Item`: raw requirement or intake section for run start, current stage artifact for stage-level drafting, checkpoint section for gate/checkpoint operations, open route ID for routing, downstream artifact section for re-import, and approved PLAN checkpoint for close.

If a write operation cannot determine the active item or required reread targets, it must stop instead of advancing the run state. When the operation is allowed to write `run.md`, record the missing resume target as part of the stop or route context.

## Run Lifecycle Operations

### Start Workflow Run

**Canonical Operations**
`start_workflow_run`, `load_or_create_artifact`

**Required Inputs**
Raw requirement text or a durable source reference, plus a `work_id` or enough context to create one.

**Preconditions**
No active run exists for the same work ID, or the user explicitly chooses to create a new run instead of resuming.

**Allowed Artifact Writes**
Create `.req-to-plan/<work-id>/run.md` and initial raw requirement or intake artifact.

**run.md Updates**
Set status to `active_stage_draft`, current stage to `raw_requirement` or `requirement_brief`, and record active artifacts.

**User Confirmation Required**
Required when the operation would create a duplicate work ID or supersede an existing run.

**Stop Conditions**
Missing raw requirement, ambiguous work ID collision, or inaccessible referenced source.

**Forbidden Behavior**
Do not infer source provenance for referenced files, repositories, designs, or documents.

**Result / Output**
`active_stage_draft`

### Resume Workflow Run

**Canonical Operations**
`resume_from_checkpoint`, `load_or_create_artifact`

**Required Inputs**
Work ID or run record path, plus existing `Resume Context` when present.

**Preconditions**
`run.md` exists and approved checkpoint or active draft state can be read.

**Allowed Artifact Writes**
Update `run.md`, including `Resume Context`; update current draft artifact only when resume target is clear and no open route remains. After `checkpoint_approved`, create or load the next-stage draft artifact when required, but do not run or bypass that stage's entry gate.

**run.md Updates**
Apply the `Context Resume Contract` in `workflow-execution-guide.md#context-resume-contract`: load `run.md`, load required reread targets, verify the active item, and stop on conflict before continuing. If `Resume Context` is missing but `run.md`, active artifact metadata, and open routes are enough to identify the active item and required reread targets, rebuild `Resume Context`; otherwise stop and record the missing resume target. Record current stage, active artifacts, stale artifacts, open routes, and next allowed operation. Refresh `Resume Context` with last completed operation, next allowed operation, active item, versioned required reread targets, and resume reason. If any open route remains, do not set `next_stage`; when the route owner has an approved repaired checkpoint, keep the current run target on re-import and set next allowed operation to `Re-import Repaired Upstream`. When resuming from `checkpoint_approved` into the next stage with no open route, set run status to `next_stage`, set current stage to the target next stage, and keep the next allowed operation as that stage's entry gate.

**User Confirmation Required**
Required when multiple resume targets are plausible or an artifact appears stale or superseded.

**Stop Conditions**
Missing run record, conflicting artifact versions, active item cannot be loaded, required reread target is missing, any open route remains, stale/superseded approved input, or `Resume Context` conflicts with approved artifact content. If the open route has an approved repaired owner checkpoint, normal resume stops and routes to `Re-import Repaired Upstream`.

**Forbidden Behavior**
Do not resume from a downstream draft when its imported upstream artifact is stale or superseded. Do not continue from conversation-only memory. Do not treat `Resume Context` as the source of truth when it conflicts with stage artifacts.

**Result / Output**
`active_stage_draft`, `next_stage`, or `upstream_gap_routing`

### Close Workflow Run

**Canonical Operations**
`close_workflow_run`

**Required Inputs**
Approved PLAN Checkpoint and run record.

**Preconditions**
PLAN Quality Gate is `ready`, Main/User PLAN Checkpoint is `approved`, and no open upstream route remains.

**Allowed Artifact Writes**
Update `run.md` only.

**run.md Updates**
Set status to `closed_at_plan_checkpoint`, current stage to `closed`, and record final approved artifact versions.

**User Confirmation Required**
No. PLAN Checkpoint approval is a precondition; this operation only closes an already approved run.

**Stop Conditions**
PLAN not approved, stale/superseded upstream artifact referenced by PLAN, or open route remains.

**Forbidden Behavior**
Do not start implementation or executor-specific adaptation.

**Result / Output**
`closed_at_plan_checkpoint`

### Reopen Workflow Run

**Canonical Operations**
`reopen_workflow_run`

**Required Inputs**
Source `closed_at_plan_checkpoint` work ID or run record path, target start stage (`requirement_brief`, `risk_discovery`, `design`, `spec`, or `plan`), and reopen reason.

**Preconditions**
Source run is `closed_at_plan_checkpoint`, source PLAN Checkpoint remains approved, target start stage is reachable in the canonical chain, and no in-progress reopen for the same source exists.

**Allowed Artifact Writes**
Create `.req-to-plan/<source-work-id>-rN/run.md` and copy source-run artifacts up to (but not including) the target start stage into the new run path. The source run's `run.md` and approved artifacts must not be modified.

**run.md Updates**
Write a new `run.md` for the reopened run with status `active_stage_draft`, current stage set to the target start stage, and a lineage reference (`reopened_from: <source-work-id>@<source-checkpoint>`). The source `run.md` is read-only during this operation. The new run requires a fresh tier estimation and lock before any `stage-produce` runs (same as a `run-start` flow).

**User Confirmation Required**
Required. Reopen is a deliberate fork; the operator must confirm the source work ID, target stage, and reason.

**Stop Conditions**
Source run not found, source run not `closed_at_plan_checkpoint`, invalid target stage name, target stage falls outside the canonical chain, or an existing `<source-work-id>-rN` run is unresolved.

**Forbidden Behavior**
Do not modify the source run's `run.md`. Do not delete source artifacts. Do not auto-approve the new run's first-stage checkpoint. Do not switch the workspace active pointer without explicit instruction.

**Result / Output**
`active_stage_draft` for the new `<source-work-id>-rN` run.

## Tier Operations

### Estimate Tier

**Canonical Operations**
`estimate_tier`

**Required Inputs**
Raw requirement text or durable source reference, repo baseline scan result, link expansion result, and keyword scan output.

**Preconditions**
Run record exists, raw requirement is loaded, and baseline scan plus link expansion have completed. Tier has not yet been locked, or operator explicitly requests re-estimation before lock.

**Allowed Artifact Writes**
Write or refresh the Tier Estimation Evidence Block in the active Intake Brief or Requirement Brief draft and in `run.md`.

**run.md Updates**
Record `tier_estimate` with base, modifiers, floor, keyword hits, repo baseline summary, linked context, scope signals, escalation candidates, and confirm status `pending`.

**User Confirmation Required**
No. Estimation is mechanical; lock requires confirmation.

**Stop Conditions**
Missing raw requirement, baseline scan incomplete, link expansion unresolved (`requires_auth` or `unreachable`), or Evidence Block fields cannot be populated.

**Forbidden Behavior**
Do not lock the tier. Do not enable full tier-aware Quality Gate checks. Do not silently downgrade modifier signals.

**Result / Output**
`tier_estimate_recorded` with Evidence Block; run state unchanged.

### Lock Tier

**Canonical Operations**
`lock_tier`

**Required Inputs**
Current TierEstimate with complete Evidence Block, user confirmation, and optional `--override-floor` reason.

**Preconditions**
A TierEstimate exists, no Tier Lock exists yet, and Requirement Brief stage has not yet run `stage-produce`. If the requested lock is below the Floor, `override_floor` reason is required.

**Allowed Artifact Writes**
Write Tier Lock block to `run.md` and append a Tier Lock entry to the Requirement Brief draft.

**run.md Updates**
Set `tier_lock` with base, modifiers, locked_at timestamp, override_floor reason when applicable, and confirm source. Mark `tier_estimate.confirm_status = confirmed`.

**User Confirmation Required**
Required. Lock is a user-owned decision and must record the confirmation source.

**Stop Conditions**
No TierEstimate, Evidence Block incomplete, requested base/modifiers below Floor without `--override-floor` plus `--confirm`, or Requirement Brief `stage-produce` already executed.

**Forbidden Behavior**
Do not silently override the Floor. Do not drop modifiers. Do not lock with a stale Evidence Block.

**Result / Output**
`tier_locked`; run state unchanged. Subsequent `gate-quality` runs apply full tier-aware section checks.

### Escalate Tier

**Canonical Operations**
`escalate_tier`

**Required Inputs**
Existing Tier Lock, new modifier from the canonical set, triggering signal or operator reason, and current stage.

**Preconditions**
Tier Lock exists, requested modifier is not already in the lock, run state is non-terminal, and the new modifier is supported by an observed signal or operator-recorded reason.

**Allowed Artifact Writes**
Append the new modifier to the Tier Lock block in `run.md` and add an escalation log entry. Mark affected Bundled Checkpoints as revoked when applicable.

**run.md Updates**
Update `tier_lock.modifiers`, append `tier_escalations[]` with modifier, triggered_in stage, reason, recorded_at. If a Bundled Checkpoint covers a stage whose section requirements change, mark that bundled checkpoint `revoked` and revert affected stage states to `checkpoint_review`.

**User Confirmation Required**
Required when escalation revokes an approved Bundled Checkpoint or changes a previously confirmed tier-derived decision.

**Stop Conditions**
No Tier Lock exists, modifier already present, terminal run state, or revocation target cannot be resolved unambiguously.

**Forbidden Behavior**
Do not remove an existing modifier. Do not silently re-approve a revoked bundled checkpoint. Do not bypass downstream re-import after revocation.

**Result / Output**
`tier_escalated`; run state may change to `checkpoint_review` for revoked bundled stages.

### Authorize Bundled Checkpoints

**Canonical Operations**
`authorize_bundled_checkpoints`

**Required Inputs**
List of bundled stage names (`requirement_brief`, `risk_discovery`, optionally `design` for light + no modifier), each stage's ready artifact and merged review findings, and required user confirmation.

**Preconditions**
Tier Lock has no modifier and stage set matches `workflow-invariants.md#workflow-complexity-tier-rule` bundle eligibility (`light + no modifier`: requirement_brief + risk_discovery + design; `standard + no modifier`: requirement_brief + risk_discovery). Every bundled stage has Quality Gate `ready` and merged checkpoint review findings, with required confirmations recorded for the highest-authority stage in the bundle.

**Allowed Artifact Writes**
Write BundleAuthorization to `run.md`, append an Approved Checkpoints row for each bundled stage, and mark each bundled stage's artifact as `approved`.

**run.md Updates**
Record `bundle_authorization` with bundled_stages, approved_at, confirm source, and revocable flag. Set run status to `checkpoint_approved` for the last bundled stage and update downstream authorization records.

**User Confirmation Required**
Required. Bundle approval is a single user-owned decision spanning multiple stages.

**Stop Conditions**
Tier has any modifier, requested bundle does not match eligibility, any bundled stage lacks Quality Gate `ready` or merged findings, or any forced subagent review condition applies (see `workflow-invariants.md#forced-subagent-review-rule`).

**Forbidden Behavior**
Do not bundle when any modifier is present. Do not skip individual stage Quality Gates. Do not approve a bundle that contains a stage with an unresolved upstream gap.

**Result / Output**
`bundle_authorized`; multiple stages become `approved` in a single audit record. Tier escalation may later revoke the bundle.

## Stage Operations

### Load Or Create Stage Artifact

**Canonical Operations**
`load_or_create_artifact`

**Required Inputs**
Work ID, target stage, required upstream artifact references, and artifact lifecycle rules.

**Preconditions**
Required upstream checkpoint approvals exist unless the target stage is the initial requirement capture.

**Allowed Artifact Writes**
Create or update only the target stage draft artifact and `run.md`.

**run.md Updates**
Record active artifact path, version, status, and derived-from references.

**User Confirmation Required**
Required when creating a new version from an approved artifact.

**Stop Conditions**
Missing upstream approval, stale/superseded upstream input, missing artifact root, or unresolved route.

**Forbidden Behavior**
Do not overwrite an approved artifact.

**Result / Output**
`active_stage_draft`

### Produce Stage Artifact

**Canonical Operations**
`produce_stage_artifact`

**Required Inputs**
Stage workflow document, approved upstream artifacts, and current stage draft.

**Preconditions**
Stage entry gate has passed when the stage defines one.

**Allowed Artifact Writes**
Update only sections owned by the current stage artifact.

**run.md Updates**
Update active artifact status and updated version metadata.

**User Confirmation Required**
Required only for stage-specific user-owned decisions, such as acceptance confirmation or User Decision Gate items.

**Stop Conditions**
The stage needs an upstream decision it is not allowed to make, or user confirmation is required.

**Forbidden Behavior**
Do not change upstream artifact content from a downstream stage.

**Result / Output**
`active_stage_draft`, `blocked`, or `upstream_gap_detected`

### Mark Stage Artifact Ready

**Canonical Operations**
`mark_stage_artifact_ready`

**Required Inputs**
Current active draft artifact, stage workflow ready criteria, and the author's readiness assertion.

**Preconditions**
The current active draft artifact exists for the current stage, has no blocking explicit artifact status, has no non-owner open route, and the stage workflow's ready criteria are reasonably satisfied per author assertion.

**Allowed Artifact Writes**
Update the current active draft artifact's frontmatter or `## Status` section to `ready`. Refresh `run.md` Resume Context.

**run.md Updates**
Refresh `Resume Context` with last completed operation, next allowed operation, and active item. Do not change run status to `ready_for_checkpoint_review`; that transition belongs to `run_quality_gate`.

**User Confirmation Required**
Required only when marking ready would override or supersede a previously approved row or change a user-confirmed decision.

**Stop Conditions**
Wrong stage, missing active artifact, non-draft active artifact row, blocking explicit artifact status, stale imported upstream input, or non-owner open route.

**Forbidden Behavior**
Do not pass Quality Gate, run checkpoint review, or approve a checkpoint. Do not mark an approved or superseded artifact ready.

**Result / Output**
`stage_ready_recorded`; the run state remains the same and is changed by a subsequent `run_quality_gate` call.

### Update Stage Artifact

**Canonical Operations**
`produce_stage_artifact`

**Required Inputs**
Current draft artifact, requested change, and reason for update.

**Preconditions**
Artifact is not approved, or the update creates a new version.

**Allowed Artifact Writes**
Update current draft artifact, or create a new version when the prior artifact is approved.

**run.md Updates**
Record new active artifact version and supersedes relationship when applicable.

**User Confirmation Required**
Required when updating an approved artifact or changing a user-confirmed decision.

**Stop Conditions**
Requested update conflicts with approved upstream input or changes stage responsibility boundaries.

**Forbidden Behavior**
Do not silently revise checkpoint-approved content in place.

**Result / Output**
`active_stage_draft`, `changes_requested`, or `superseded`

## Gate / Checkpoint Operations

### Run Entry Gate

**Canonical Operations**
`run_stage_entry_gate`

**Required Inputs**
Current stage, required upstream checkpoint approvals, and entry gate rules from the stage workflow.

**Preconditions**
Target stage is selected and upstream references are available.

**Allowed Artifact Writes**
Record entry gate result in the current artifact or `run.md`.

**run.md Updates**
Set status to `active_stage_draft` on pass, `entry_gate_failed` when entry cannot start from current inputs, or `upstream_gap_routing` when entry detects a missing upstream input. Add an open route when status is `upstream_gap_routing`.

**User Confirmation Required**
Required when entry depends on user-owned approval or source provenance.

**Stop Conditions**
Required checkpoint missing, required source inaccessible, or requirement/design blocker routed to owner stage.

**Forbidden Behavior**
Do not start a stage from unapproved upstream input.

**Result / Output**
`pass`, `blocked`, `return_to_*`, or `upstream_gap_detected`

### Run Quality Gate

**Canonical Operations**
`run_quality_gate`

**Required Inputs**
Current stage artifact and stage Quality Gate rules.

**Preconditions**
Current artifact exists and has required upstream references.

**Allowed Artifact Writes**
Record Quality Gate result and failure routing in the current artifact.

**run.md Updates**
Set status to `ready_for_checkpoint_review` when ready, `quality_gate_failed` when current-stage work is incomplete, or `upstream_gap_routing` when upstream gap is detected.

**User Confirmation Required**
Required when a failed check needs user-owned confirmation.

**Stop Conditions**
Any required check fails.

**Forbidden Behavior**
Do not treat Quality Gate `ready` as downstream authorization.

**Result / Output**
`ready`, `blocked`, `return_to_*`, or `upstream_gap_detected`

### Run Checkpoint Review

**Canonical Operations**
`run_checkpoint_review`

**Required Inputs**
Current stage artifact with Quality Gate `ready`.

**Preconditions**
Quality Gate is `ready` and run state is `ready_for_checkpoint_review`; optional subagent checkpoint reviews are allowed by stage rules.

**Allowed Artifact Writes**
Write checkpoint review findings under the stage artifact or `reviews/`.

**run.md Updates**
Set status to `checkpoint_review` while review is active. After review, record review finding references and keep status `checkpoint_review`. Do not set `checkpoint_changes_requested` or `upstream_gap_routing`; `Merge Checkpoint Review Findings` owns review-result routing.

**User Confirmation Required**
Not for review findings; required later for checkpoint approval.

**Stop Conditions**
Quality Gate is not ready, required review source is unavailable, or review findings cannot be written.

**Forbidden Behavior**
Do not approve handoff, merge findings, set checkpoint decision status, or route review findings from a checkpoint review.

**Result / Output**
`review_findings_written`, `issues_found`, `blocked`, or `upstream_gap_finding`

### Merge Checkpoint Review Findings

**Canonical Operations**
`merge_checkpoint_review_findings`, `merge_subagent_findings` when checkpoint-review subagent findings exist

**Required Inputs**
Checkpoint review findings, optional checkpoint-review subagent findings, current stage artifact with Quality Gate `ready`, evidence references, and conflict handling rules.

**Preconditions**
Run state is `checkpoint_review`, review findings exist, and review sources are complete enough to merge or explicitly marked partial.

**Allowed Artifact Writes**
Write merged checkpoint review summary, preserved conflicts, required current-stage changes, required confirmations, and upstream routing records under the stage artifact or `reviews/`.

**run.md Updates**
Record merged review sources. Keep status `checkpoint_review` when findings are merged and no required change or upstream route remains. Set `checkpoint_changes_requested` for required current-stage changes, or `upstream_gap_routing` when merge detects or routes an upstream gap.

**User Confirmation Required**
Required when merge exposes a user-owned decision, confirmation, rejection, or risk acceptance.

**Stop Conditions**
Review findings are missing, findings conflict without resolution path, required user confirmation is missing, required current-stage change remains, or upstream gap owner cannot be identified.

**Forbidden Behavior**
Do not approve downstream handoff, silently drop review findings, or resolve direct conflicts without evidence or required user confirmation.

**Result / Output**
`review_findings_merged`, `checkpoint_changes_requested`, `upstream_gap_detected`, or `route_upstream`

### Approve Checkpoint

**Canonical Operations**
`approve_checkpoint`

**Required Inputs**
Ready artifact, merged checkpoint findings, and required user confirmations.

**Preconditions**
Quality Gate is `ready` and checkpoint findings are merged. Every approval requires the version-matched checkpoint marker `reviews/<stage>-checkpoint-review-v<artifact-version>.md`. The Forced Subagent Review Rule in `workflow-invariants.md#workflow-complexity-tier-rule` also applies: when the locked tier carries any modifier in `{ migration, safety, cross_project }` and the current stage is in `{ design, spec, plan }`, an `approved` decision is refused unless `reviews/<stage>-subagent-review-v<artifact-version>.md` exists for the current stage and active artifact version. Non-approval decisions remain allowed.

**Allowed Artifact Writes**
Update checkpoint section in the stage artifact and update `run.md`.

**run.md Updates**
On approval, add the approved checkpoint, set downstream authorization, and set run status to `checkpoint_approved`. On `changes_requested` or `blocked`, set run status to `checkpoint_changes_requested`. On `upstream_gap_detected` or `route_upstream`, set run status to `upstream_gap_routing` and add an open route. A later resume/next-stage operation may set `next_stage`; only `Close Workflow Run` may set `closed_at_plan_checkpoint`.

**User Confirmation Required**
Always required for Main/User Checkpoint approval.

**Stop Conditions**
Checkpoint findings are unmerged, required user confirmation is missing, upstream gap owner cannot be identified, or stale/superseded upstream artifact is detected without a route or stale/superseded record.

**Forbidden Behavior**
Do not approve downstream handoff on subagent recommendation alone.

**Result / Output**
`approved`, `changes_requested`, `blocked`, `upstream_gap_detected`, or `route_upstream`

## User Confirmation Operations

### Record User Confirmation

**Canonical Operations**
`record_user_confirmation`

**Required Inputs**
Confirmation statement, user source, owning stage, affected artifact section, and whether downstream authorization depends on it.

**Preconditions**
The confirmation belongs to the current stage or to an upstream owner stage being repaired.

**Allowed Artifact Writes**
Add or update confirmation records in the owning stage artifact and `run.md`.

**run.md Updates**
Add a User Confirmations row with stage, source, and recorded location.

**User Confirmation Required**
Yes. The confirmation must come from the user or main agent authority defined by the checkpoint rules.

**Stop Conditions**
Confirmation is ambiguous, conflicts with approved upstream input, or belongs to a different owner stage.

**Forbidden Behavior**
Do not treat a preference, inference, or subagent recommendation as a user confirmation.

**Result / Output**
`confirmation_recorded`; run state remains unchanged unless another operation explicitly updates it.

### Reject Or Request Clarification

**Canonical Operations**
`record_user_confirmation`, `route_upstream`

**Required Inputs**
Rejected item or clarification request, owner stage, affected section, and blocking impact.

**Preconditions**
The current operation requires user confirmation and the user rejects, changes, or cannot confirm the item.

**Allowed Artifact Writes**
Record rejection or clarification need in the current artifact, owner artifact when applicable, and `run.md`.

**run.md Updates**
Set status to `active_stage_draft`, `quality_gate_failed`, or `upstream_gap_routing` depending on owner stage.

**User Confirmation Required**
Yes.

**Stop Conditions**
Owner stage cannot be identified or the rejection invalidates already approved downstream artifacts.

**Forbidden Behavior**
Do not continue as if the original confirmation was granted.

**Result / Output**
`quality_gate_failed`, `upstream_gap_detected`, or `route_upstream`

### Link Confirmation To Artifact Section

**Canonical Operations**
`record_user_confirmation`

**Required Inputs**
Existing confirmation, artifact section, stable item ID when available, and downstream effect.

**Preconditions**
Confirmation exists and affects a traceable artifact item.

**Allowed Artifact Writes**
Update confirmation reference in the owning artifact and `run.md`.

**run.md Updates**
Update confirmation location or trace row.

**User Confirmation Required**
No, unless linking changes the confirmed meaning.

**Stop Conditions**
No stable artifact section exists or linking changes the content of the confirmation.

**Forbidden Behavior**
Do not use a confirmation link as a substitute for missing artifact content.

**Result / Output**
`confirmation_linked`; run state remains unchanged unless another operation explicitly updates it.

## Subagent Operations

### Dispatch Discovery Subagents

**Canonical Operations**
`dispatch_subagent_work`

**Required Inputs**
Stage, allowed subagent task type, scope, sources, and expected finding template.

**Preconditions**
The stage entry gate has passed and the stage allows discovery subagents.

**Allowed Artifact Writes**
Write subagent finding artifacts or referenced finding sections.

**run.md Updates**
Record active subagent finding references when they affect stage completion.

**User Confirmation Required**
No, unless the dispatch needs access to a user-controlled source.

**Stop Conditions**
Subagent task would change scope, choose design, write SPEC/PLAN content outside authority, or require unavailable source access.

**Forbidden Behavior**
Do not let discovery subagents approve checkpoints or make final decisions.

**Result / Output**
`subagent_work_dispatched`; run state remains unchanged unless another operation explicitly updates it.

### Merge Subagent Findings

**Canonical Operations**
`merge_subagent_findings`

**Required Inputs**
Subagent outputs, current stage artifact, evidence references, and conflict handling rules.

**Preconditions**
Subagent outputs are complete enough to merge or explicitly marked partial.

**Allowed Artifact Writes**
Update current stage artifact with merged findings, preserved conflicts, and routing actions.

**run.md Updates**
Record merged review sources when they affect checkpoint review or user confirmation.

**User Confirmation Required**
Required when conflicts require product, cost, compatibility, risk, or scope judgment.

**Stop Conditions**
Findings conflict with approved upstream input, require user-owned decision, or reveal upstream gap.

**Forbidden Behavior**
Do not silently resolve direct conflicts, treat subagent conclusions as approval, or mark the artifact ready for checkpoint review without a Quality Gate.

**Result / Output**
`merged`, `conflict_preserved`, `upstream_gap_detected`, or `route_upstream`

### Run Checkpoint Review Subagents

**Canonical Operations**
`dispatch_subagent_work`, `run_checkpoint_review`

**Required Inputs**
Current artifact with Quality Gate `ready`, checkpoint review template, and review scope.

**Preconditions**
Run state is `ready_for_checkpoint_review` and the stage allows or requires subagent checkpoint review.

**Allowed Artifact Writes**
Write checkpoint review artifacts under `reviews/`.

**run.md Updates**
Record checkpoint review sources and set status to `checkpoint_review` while review is active. Do not merge findings or set checkpoint decision status; `Merge Checkpoint Review Findings` owns the merged review summary and review-result routing.

**User Confirmation Required**
No for review execution; yes for Main/User Checkpoint approval.

**Stop Conditions**
Quality Gate is not ready, review finds upstream gap, or review finds unresolved blocker.

**Forbidden Behavior**
Do not merge findings, approve downstream handoff, or route review conclusions as final from subagent checkpoint review.

**Result / Output**
`review_findings_written`, `issues_found`, `blocked`, or `upstream_gap_finding`

## Routing / Resume Operations

### Record Upstream Gap

**Canonical Operations**
`route_upstream`

**Required Inputs**
Detected missing or conflicting upstream input, current stage, owner stage, affected sections, and required action.

**Preconditions**
Current stage lacks authority to decide the missing input.

**Allowed Artifact Writes**
Add Upstream Gap Record to the current artifact and update `run.md`.

**run.md Updates**
Set status to `upstream_gap_routing` and add an open route.

**User Confirmation Required**
Required when owner stage or routing action is ambiguous.

**Stop Conditions**
Owner stage cannot be identified or affected artifact sections are unclear.

**Forbidden Behavior**
Do not convert the gap into a downstream assumption.

**Result / Output**
`upstream_gap_detected` or `route_upstream`

### Route Upstream

**Canonical Operations**
`route_upstream`, `load_or_create_artifact`

**Required Inputs**
Open route record, owner stage, and current upstream artifact version.

**Preconditions**
Upstream Gap Record exists and downstream authorization is `no`.

**Allowed Artifact Writes**
Open or create the owner stage draft and record route context. Actual upstream repair must run through the owner stage's produce/update, Quality Gate, and Main/User Checkpoint flow.

**run.md Updates**
Move current stage to owner stage and record downstream artifacts with stale markers or superseded entries when they imported the old upstream input.

**User Confirmation Required**
Required when choosing the owner stage, opening the owner draft, or recording route context would affect user-confirmed scope, acceptance, design choice, or risk acceptance.

**Stop Conditions**
Owner stage cannot be identified, owner draft cannot be opened or created safely, or required user confirmation is missing.

**Forbidden Behavior**
Do not keep downstream artifacts approved against stale or superseded input.

**Result / Output**
`active_stage_draft` or `upstream_gap_routing`

### Re-import Repaired Upstream

**Canonical Operations**
`resume_from_checkpoint`, `produce_stage_artifact`, `run_quality_gate`

**Required Inputs**
Run record, open route record, repaired upstream artifact with approved checkpoint, downstream artifact that imported the old version, and required reread targets for the repaired upstream references and affected downstream sections.

**Preconditions**
Owner stage has rerun Quality Gate and Main/User Checkpoint after repair. The open route exists, belongs to the repaired owner stage, and has not already been closed. Apply the `Context Resume Contract` scoped to the open route, repaired upstream references, and affected downstream sections before remapping.

**Allowed Artifact Writes**
Update downstream draft artifact or create a new downstream version.

**run.md Updates**
Close the repaired route when remapping is complete and update stale/superseded artifact records. If any open route remains, keep run status `upstream_gap_routing`, set next allowed operation to the remaining route's repair or re-import step, and do not unlock the affected downstream stage. If no open route remains, set current stage to the affected downstream stage, record the downstream artifact as the active artifact, refresh `Resume Context` with the downstream artifact section as `Active Item`, and set run status to `active_stage_draft`, `quality_gate_failed`, or `ready_for_checkpoint_review` according to the re-imported downstream artifact and rerun Quality Gate result.

**User Confirmation Required**
Required when remapping changes user-confirmed downstream choices.

**Stop Conditions**
Missing run record, missing open route, missing required reread target, imported IDs cannot be remapped, conflicts remain, or downstream decisions contradict repaired upstream input.

**Forbidden Behavior**
Do not approve downstream handoff until downstream Quality Gate and Checkpoint rerun.

**Result / Output**
`active_stage_draft`, `quality_gate_failed`, `ready_for_checkpoint_review`, or `upstream_gap_routing`

### Mark Downstream Artifact Stale

**Canonical Operations**
`route_upstream`

**Required Inputs**
Changed upstream artifact version and downstream artifact references.

**Preconditions**
Downstream artifact imported a now-repaired or superseded upstream version.

**Allowed Artifact Writes**
Update downstream artifact metadata only when marking it `superseded`; record `stale` only in `run.md`.

**run.md Updates**
Add a stale marker or superseded artifact entry.

**User Confirmation Required**
Not required unless stale or superseded artifact was previously approved for downstream use.

**Stop Conditions**
Unable to determine which downstream artifacts imported the old version.

**Forbidden Behavior**
Do not silently continue from an artifact known to be stale or superseded.

**Result / Output**
`stale_recorded`, `superseded`, or `upstream_gap_routing`; `stale` is a `run.md` marker, not an artifact status.

## Inspection / Status Operations

### Show Run Status

**Canonical Operations**
`inspect_workflow_run`

**Required Inputs**
Work ID or run record path.

**Preconditions**
Run record exists.

**Allowed Artifact Writes**
None.

**run.md Updates**
None.

**User Confirmation Required**
No.

**Stop Conditions**
Run record missing or unreadable.

**Forbidden Behavior**
Do not modify artifacts.

**Result / Output**
Current run status.

### Show Current Stage

**Canonical Operations**
`inspect_workflow_run`

**Required Inputs**
Work ID or run record path.

**Preconditions**
Run record exists.

**Allowed Artifact Writes**
None.

**run.md Updates**
None.

**User Confirmation Required**
No.

**Stop Conditions**
Current stage cannot be determined from `run.md` and artifact statuses.

**Forbidden Behavior**
Do not infer approval from artifact existence alone.

**Result / Output**
Current stage and required next gate or artifact action.

### Show Next Allowed Operation

**Canonical Operations**
`inspect_workflow_run`

**Required Inputs**
Run record, active artifact status, approved checkpoint list, and open routes.

**Preconditions**
Run record exists.

**Allowed Artifact Writes**
None.

**run.md Updates**
None.

**User Confirmation Required**
No.

**Stop Conditions**
Conflicting statuses or unresolved stale/superseded artifact references.

**Forbidden Behavior**
Do not choose a next operation that bypasses open route, Quality Gate, or Checkpoint requirements.

**Result / Output**
Recommended next semantic operation and reason.

### Show Open Routes

**Canonical Operations**
`inspect_workflow_run`

**Required Inputs**
Run record.

**Preconditions**
Run record exists.

**Allowed Artifact Writes**
None.

**run.md Updates**
None.

**User Confirmation Required**
No.

**Stop Conditions**
Open route records are incomplete or inconsistent.

**Forbidden Behavior**
Do not close routes during inspection.

**Result / Output**
List of open routes, owner stages, and required actions.

### Show Tier Status

**Canonical Operations**
`inspect_workflow_run`

**Required Inputs**
Work ID or run record path.

**Preconditions**
Run record exists.

**Allowed Artifact Writes**
None.

**run.md Updates**
None.

**User Confirmation Required**
No.

**Stop Conditions**
Run record missing or tier records (TierEstimate, Tier Lock, escalations, bundle authorizations) are inconsistent.

**Forbidden Behavior**
Do not modify artifacts. Do not lock or escalate the tier as a side effect.

**Result / Output**
Current TierEstimate, Tier Lock, escalations, and bundle authorization status.

### Show Artifact Versions

**Canonical Operations**
`inspect_workflow_run`

**Required Inputs**
Run record and artifact root.

**Preconditions**
Artifact root exists.

**Allowed Artifact Writes**
None.

**run.md Updates**
None.

**User Confirmation Required**
No.

**Stop Conditions**
Artifact metadata is missing or contradictory.

**Forbidden Behavior**
Do not mark artifacts approved, stale, or superseded during inspection.

**Result / Output**
Artifact version list with active, approved, stale, and superseded markers.

## Safety Rules

All operation carriers must preserve these rules:

- No operation may approve downstream handoff except `Approve Checkpoint`.
- No operation may treat Quality Gate `ready` as checkpoint approval.
- No operation may continue from an artifact marked `stale` or `superseded`.
- No operation may overwrite an approved artifact.
- No operation may hide or downgrade `upstream_gap_detected`.
- No operation may let SPEC or PLAN decide missing upstream requirement, risk, design, or contract input.
- No operation may skip Coverage Closure for SPEC or PLAN imports.
- No operation may start actual implementation from PLAN before PLAN Checkpoint approval.
- No operation may inject executor-specific runtime, command, or prompt format into PLAN.

## Semantic Examples

### Start From Raw Requirement

Intent:

```text
Create a workflow run from a raw user request.
```

Semantic mapping:

```text
Start Workflow Run -> start_workflow_run -> run.md + raw requirement artifact -> active_stage_draft
```

Required stop:

```text
Stop if the request references a file, repository, design, document, or external source whose provenance is unknown.
```

### Continue After Approved Checkpoint

Intent:

```text
Proceed from the latest approved checkpoint to the next stage.
```

Semantic mapping:

```text
Resume Workflow Run -> resume_from_checkpoint -> load next stage artifact -> run entry gate
```

Required stop:

```text
Stop if any downstream artifact imported a stale upstream version. If any open route remains, including a route whose owner checkpoint is already repaired and approved, run re-import before ordinary resume can select a next stage.
```

### Route Missing Design Input

Intent:

```text
SPEC found a missing compatibility decision that DESIGN owns.
```

Semantic mapping:

```text
Record Upstream Gap -> route_upstream -> repair DESIGN -> rerun DESIGN Quality Gate and Checkpoint -> re-import SPEC coverage
```

Required stop:

```text
Stop PLAN authorization until SPEC reruns Quality Gate and Checkpoint from the repaired DESIGN.
```

## Future Adapter Boundary

Future carrier-specific designs may define concrete syntax or APIs, but they must map to this operation surface.

Adapter designs must specify:

- Which operation semantic they invoke.
- Which canonical operation they call.
- Which required inputs they collect.
- Which preconditions they enforce before running.
- Which artifacts they may write.
- Which `run.md` fields they may update.
- Which stop conditions they enforce.
- Which forbidden behaviors they prevent.
- Which result or output values they can return.
- Which user confirmations they require.

Adapter designs must not introduce new workflow authority that is absent from this document or `workflow-execution-guide.md`.

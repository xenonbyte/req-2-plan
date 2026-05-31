# Workflow Command Surface

## Purpose

This document defines the carrier-neutral command intent layer for the requirement-to-PLAN workflow.

It maps operation semantics from `workflow-operation-surface.md` into stable command intents that a later carrier can expose as CLI commands, slash commands, MCP tools, API endpoints, skills, UI actions, or natural-language command patterns.

This document does not define concrete command names, flags, paths, prompts, schemas, transport protocols, runtime adapters, or executor-specific behavior.

Use this document when deciding which workflow actions should be available to an operator before designing any concrete command syntax.

## Scope

This document covers:

- Stable command intent IDs.
- Command intent groups.
- The operation intents and canonical operations each command intent may invoke.
- The authority boundary for each command intent.
- Required input class, confirmation need, stop condition class, allowed write class, and result class.
- Coverage from operation intents to command intents.
- Adapter rules for future concrete command surfaces.

This document does not cover:

- Concrete CLI or slash-command text.
- Concrete MCP, API, skill, or UI schemas.
- Runtime implementation.
- Executor-specific PLAN adaptation.
- Actual implementation after PLAN approval.

## Command Surface Boundary

A command intent is a stable workflow action that an operator or agent may request. It is not a concrete command syntax.

The following are carriers, not command intents:

- CLI command
- slash command
- MCP tool name
- API endpoint
- UI control label
- prompt template
- executor adapter instruction

Concrete carriers may choose their own syntax later, but each exposed command must map back to one command intent in this document, or to an explicitly documented composition of command intents.

Carrier-specific designs must not:

- Add authority beyond the mapped command intent.
- Collapse Quality Gate readiness into checkpoint approval.
- Hide `upstream_gap_detected` or `route_upstream`.
- Start downstream work from stale or superseded artifacts.
- Rewrite approved artifacts in place.
- Convert executor-neutral PLAN content into executor-specific runtime instructions.

## Command Contract Schema

Future concrete command specs must use this schema for every exposed command:

```markdown
### <Concrete Command>

**Command Intent**
Stable command intent ID from this document.

**Operation Intents**
Operation intent names from `workflow-operation-surface.md`.

**Canonical Operations**
Canonical operation names from `workflow-execution-guide.md#canonical-operations`.

**Required Inputs**
Concrete parameters or user inputs and how they satisfy the command intent.

**Preconditions**
Run, stage, artifact, gate, checkpoint, route, or confirmation conditions required before invocation.

**Allowed Artifact Writes**
Artifacts or review files the command may create or update.

**run.md Updates**
Run record fields the command may update.

**User Confirmation Required**
Whether explicit Main/User confirmation is required.

**Stop Conditions**
Conditions that make the command stop instead of guessing or continuing.

**Forbidden Behavior**
Actions the command must never perform.

**Result / Output**
Allowed command result, output, or resulting artifact/run status.
```

The command intent catalog below is the semantic index. The full operation-level write, `run.md`, stop, and forbidden-behavior details remain owned by `workflow-operation-surface.md`.

## Command Intent Groups

| Group | Purpose |
|---|---|
| Run Lifecycle | Start, resume, reopen, and close a workflow run. |
| Tier | Estimate, lock, escalate, and inspect the workflow complexity tier; bundle eligible checkpoints. |
| Stage Artifact | Load, create, produce, or update stage artifacts. |
| Gate / Checkpoint | Run entry gates, Quality Gates, checkpoint reviews, and checkpoint decisions. |
| User Confirmation | Record, reject, clarify, and link user-owned confirmations. |
| Subagent | Dispatch allowed subagent work and merge findings without granting approval. |
| Routing / Repair | Record upstream gaps, route to owner stages, re-import repairs, and mark stale downstream artifacts. |
| Inspection | Read run state, stage, next allowed operation, routes, and artifact versions. |

## Command Intent Catalog

Column meanings:

- `Inputs`: required input class. Concrete adapters must define exact parameters later.
- `Confirmation`: whether user confirmation is `Required`, `Conditional`, or `No`.
- `Authority / stops`: what the command may decide and where it must stop.
- `Writes / result`: allowed write class and expected output class. Full `run.md` details come from the mapped operation intents.

### Run Lifecycle

| Command Intent | Operation Intents | Canonical Operations | Inputs | Confirmation | Authority / stops | Writes / result |
|---|---|---|---|---|---|---|
| `CMD-RUN-START` | Start Workflow Run | `start_workflow_run`, `load_or_create_artifact` | Raw requirement or durable source reference; work ID context. | Conditional | May create a new run; stop on duplicate active run, missing requirement, or unknown source provenance. | Create artifact root, `run.md`, and initial requirement/intake artifact; result `active_stage_draft`. |
| `CMD-RUN-RESUME` | Resume Workflow Run | `resume_from_checkpoint`, `load_or_create_artifact` | Work ID or run record path; `Resume Context` when present. | Conditional | `context_refresh` may load required reread targets, refresh `Resume Context`, and report missing/ambiguous targets, open routes, or stale/superseded inputs without advancing stage. `ordinary_resume` may resume a clear run target only when the matrix allows ordinary `CMD-RUN-RESUME` and no open route remains. Stop on ambiguous target, missing reread target, active item conflict, any open route including a repaired route that still requires `CMD-GAP-REIMPORT`, stale/superseded input, or conflicting versions. | `context_refresh` may update `run.md` only for `Resume Context` or missing-target status. `ordinary_resume` may update `run.md` and load/create next-stage draft after approval and no open route. Result `active_stage_draft`, `next_stage`, or `upstream_gap_routing`. |
| `CMD-RUN-CLOSE` | Close Workflow Run | `close_workflow_run` | Approved PLAN Checkpoint and run record. | No | May close only after approved PLAN and no open route; stop on stale/superseded final references. | Update `run.md` only; result `closed_at_plan_checkpoint`. |
| `CMD-RUN-REOPEN` | Reopen Workflow Run | `reopen_workflow_run` | Source `closed_at_plan_checkpoint` work ID or run path, target start stage, reopen reason. | Required | May copy source artifacts up to target start stage into a new `<source-work-id>-rN` run; stop on missing source, source not closed, invalid stage name, or unresolved prior reopen. | Create new `run.md` with lineage reference and copied prior-stage artifacts; result `active_stage_draft` for the reopened run. |

### Tier

| Command Intent | Operation Intents | Canonical Operations | Inputs | Confirmation | Authority / stops | Writes / result |
|---|---|---|---|---|---|---|
| `CMD-TIER-ESTIMATE` | Estimate Tier | `estimate_tier` | Raw requirement, baseline scan, link expansion, keyword scan output. | No | May record Evidence Block; stop on missing baseline scan, unresolved link expansion, or incomplete Evidence Block fields. | Write Tier Estimation Evidence Block to active draft and `run.md`; result `tier_estimate_recorded`. |
| `CMD-TIER-LOCK` | Lock Tier | `lock_tier` | TierEstimate with complete Evidence Block, user confirmation, optional `override_floor` reason. | Required | May lock the tier and enable full tier-aware Quality Gate checks; stop on missing estimate, incomplete Evidence Block, below-Floor request without `override_floor`, or Requirement Brief `stage-produce` already executed. | Write Tier Lock to `run.md` and Requirement Brief draft; result `tier_locked`. |
| `CMD-TIER-ESCALATE` | Escalate Tier | `escalate_tier` | Existing Tier Lock, new modifier, triggering signal or reason, current stage. | Conditional | May append a modifier and revoke affected bundled checkpoints; stop on missing lock, duplicate modifier, terminal run, or unresolved revocation target. | Update Tier Lock and append escalation log; revoked bundle stages return to `checkpoint_review`; result `tier_escalated`. |
| `CMD-TIER-STATUS` | Show Tier Status | `inspect_workflow_run` | Work ID or run record path. | No | Read only; stop if `run.md` is missing or tier records are inconsistent. | No writes; result current tier estimate, lock, modifiers, escalations, and bundle authorization status. |
| `CMD-CHECKPOINT-BUNDLE` | Authorize Bundled Checkpoints | `authorize_bundled_checkpoints` | Bundled stage list, each stage's ready artifact and merged findings, required user confirmation. | Required | May approve eligible bundled stages in one decision; stop on any modifier, ineligible stage set, missing Quality Gate `ready`, unmerged findings, or applicable Forced Subagent Review condition. | Update Approved Checkpoints rows, write BundleAuthorization to `run.md`, mark bundled artifacts approved; result `bundle_authorized`. |

### Stage Artifact

| Command Intent | Operation Intents | Canonical Operations | Inputs | Confirmation | Authority / stops | Writes / result |
|---|---|---|---|---|---|---|
| `CMD-STAGE-LOAD` | Load Or Create Stage Artifact | `load_or_create_artifact` | Work ID, target stage, upstream references, artifact lifecycle rules. | Conditional | May load/create target draft; stop on missing upstream approval, stale/superseded input, or unresolved route. | Create/update target draft and `run.md`; result `active_stage_draft`. |
| `CMD-STAGE-PRODUCE` | Produce Stage Artifact | `produce_stage_artifact` | Stage workflow, approved upstream artifacts, current stage draft. | Conditional | May write current-stage owned sections; stop on upstream decision need or user confirmation need. | Update current draft; result `active_stage_draft`, `blocked`, or `upstream_gap_detected`. |
| `CMD-STAGE-UPDATE` | Update Stage Artifact | `produce_stage_artifact` | Current draft, requested change, reason. | Conditional | May update unapproved draft or create new version; stop on approved-input conflict or ownership boundary change. | Update draft or create version; result `active_stage_draft`, `changes_requested`, or `superseded`. |
| `CMD-STAGE-READY` | Mark Stage Artifact Ready | `mark_stage_artifact_ready` | Current active draft artifact and stage readiness assertion. | Conditional | May mark only the current active draft artifact explicitly ready for Quality Gate evaluation; stop on wrong stage, missing active artifact, non-draft row status, blocking explicit artifact status, stale input, or non-owner open route. | Update artifact frontmatter and `run.md` Resume Context; result `stage_ready_recorded`. |
| `CMD-STAGE-ADVANCE` | Advance To Next Stage | `load_or_create_artifact` | Approved checkpoint and run record for non-PLAN stages only. | No | May load the next-stage draft after checkpoint approval; stop on unapproved current stage, PLAN stage, active/pending confirmation need, or open route. | Create or load next-stage draft and update `run.md`; result `active_stage_draft` for next stage. |

### Gate / Checkpoint

| Command Intent | Operation Intents | Canonical Operations | Inputs | Confirmation | Authority / stops | Writes / result |
|---|---|---|---|---|---|---|
| `CMD-GATE-ENTRY` | Run Entry Gate | `run_stage_entry_gate` | Current stage, upstream checkpoints, entry-gate rules. | Conditional | May determine stage entry readiness; stop on missing checkpoint, inaccessible source, or owner-stage blocker. | Record entry result; result `pass`, `blocked`, `return_to_*`, or `upstream_gap_detected`. |
| `CMD-GATE-QUALITY` | Run Quality Gate | `run_quality_gate` | Current artifact and stage Quality Gate rules. | Conditional | May determine internal readiness; stop on any failed required check. | Record gate result and route; result `ready`, `blocked`, `return_to_*`, or `upstream_gap_detected`. |
| `CMD-REVIEW-CHECKPOINT` | Run Checkpoint Review | `run_checkpoint_review` | Artifact with Quality Gate `ready`. | No | May produce review findings; stop if Quality Gate is not ready, required review source is unavailable, or findings cannot be written. | Write review findings under artifact or `reviews/`; result `review_findings_written`, `issues_found`, `blocked`, or `upstream_gap_finding`. |
| `CMD-REVIEW-MERGE` | Merge Checkpoint Review Findings; Merge Subagent Findings when checkpoint-review subagent findings exist | `merge_checkpoint_review_findings`, `merge_subagent_findings` when checkpoint-review subagent findings exist | Checkpoint review findings, optional subagent review findings, ready artifact, conflict rules. | Conditional | May merge review findings into a checkpoint review summary; stop on unmerged conflict, user-owned decision, upstream gap, or required current-stage change. | Write merged review summary and route/failure markers; result `review_findings_merged`, `checkpoint_changes_requested`, `upstream_gap_detected`, or `route_upstream`. |
| `CMD-CHECKPOINT-DECIDE` | Approve Checkpoint | `approve_checkpoint` | Ready artifact, merged checkpoint findings, required user confirmations. | Required | May approve only when no unresolved required change or route remains; may request changes, block, or route after findings are merged. Stop if findings are unmerged or required confirmation for the requested decision is missing. | Update checkpoint section and `run.md`; result `approved`, `changes_requested`, `blocked`, `upstream_gap_detected`, or `route_upstream`. |

### User Confirmation

| Command Intent | Operation Intents | Canonical Operations | Inputs | Confirmation | Authority / stops | Writes / result |
|---|---|---|---|---|---|---|
| `CMD-CONFIRM-RECORD` | Record User Confirmation | `record_user_confirmation` | Confirmation statement, user source, owner stage, affected section, downstream dependency. | Required | May record explicit user-owned confirmation; stop on ambiguity, conflict, or wrong owner stage. | Record confirmation in artifact and `run.md`; result `confirmation_recorded`. |
| `CMD-CONFIRM-REJECT` | Reject Or Request Clarification | `record_user_confirmation`, `route_upstream` | Rejected item or clarification request, owner stage, affected section, blocking impact. | Required | May record rejection or clarification need; stop when owner cannot be identified or downstream approvals become invalid. | Record rejection/clarification and route when needed; result `quality_gate_failed`, `upstream_gap_detected`, or `route_upstream`. |
| `CMD-CONFIRM-LINK` | Link Confirmation To Artifact Section | `record_user_confirmation` | Existing confirmation, artifact section, stable item ID, downstream effect. | Conditional | May link existing confirmation; stop if no stable section exists or link changes meaning. | Update confirmation references; result `confirmation_linked`. |

### Subagent

| Command Intent | Operation Intents | Canonical Operations | Inputs | Confirmation | Authority / stops | Writes / result |
|---|---|---|---|---|---|---|
| `CMD-SUBAGENT-DISPATCH` | Dispatch Discovery Subagents | `dispatch_subagent_work` | Stage, allowed subagent task type, scope, sources, finding template. | Conditional | May dispatch evidence-gathering work; stop if task would decide scope/design, write outside authority, or need unavailable access. | Write subagent findings or references; result `subagent_work_dispatched`. |
| `CMD-SUBAGENT-MERGE` | Merge Subagent Findings | `merge_subagent_findings` | Subagent outputs, current artifact, evidence references, conflict rules. | Conditional | May merge evidence and preserve conflicts; stop on approved-input conflict, user-owned decision, or upstream gap. | Update current artifact with merged findings, conflicts, and routes; result `merged`, `conflict_preserved`, `upstream_gap_detected`, or `route_upstream`. |
| `CMD-SUBAGENT-REVIEW` | Run Checkpoint Review Subagents | `dispatch_subagent_work`, `run_checkpoint_review` | Ready artifact, checkpoint review template, review scope. | No | May run subagent review and collect findings; stop if Quality Gate is not ready, required review source is unavailable, or findings cannot be written. | Write `reviews/` artifacts and review findings; result `review_findings_written`, `issues_found`, `blocked`, or `upstream_gap_finding`. |

### Routing / Repair

| Command Intent | Operation Intents | Canonical Operations | Inputs | Confirmation | Authority / stops | Writes / result |
|---|---|---|---|---|---|---|
| `CMD-GAP-RECORD` | Record Upstream Gap | `route_upstream` | Missing/conflicting upstream input, current stage, owner stage, affected sections, required action. | Conditional | May record missing upstream input; stop when owner or affected sections are unclear. | Add Upstream Gap Record and open route; result `upstream_gap_detected` or `route_upstream`. |
| `CMD-GAP-ROUTE` | Route Upstream | `route_upstream`, `load_or_create_artifact` | Open route, owner stage, current upstream artifact version. | Conditional | May open owner-stage draft and route context; stop when owner draft cannot be opened safely or confirmation is missing. | Open/create owner draft, mark affected downstream artifacts stale/superseded in allowed locations; result `active_stage_draft` or `upstream_gap_routing`. |
| `CMD-GAP-REIMPORT` | Re-import Repaired Upstream | `resume_from_checkpoint`, `produce_stage_artifact`, `run_quality_gate` | Run record, open route, approved repaired upstream artifact, affected downstream artifact, and required reread targets. | Conditional | May remap downstream draft after upstream repair; stop on missing route, missing reread target, unmappable IDs, remaining conflicts, or contradicted downstream decisions. | Update downstream draft/version and close route when remapped; refresh `Resume Context`; result `active_stage_draft`, `quality_gate_failed`, `ready_for_checkpoint_review`, or `upstream_gap_routing`. |
| `CMD-ARTIFACT-MARK-STALE` | Mark Downstream Artifact Stale | `route_upstream` | Changed upstream artifact version and downstream artifact references. | Conditional | May record freshness impact; stop if affected downstream artifacts cannot be identified. | Record `stale` only in `run.md`, or `superseded` in allowed metadata; result `stale_recorded`, `superseded`, or `upstream_gap_routing`. |

### Inspection

| Command Intent | Operation Intents | Canonical Operations | Inputs | Confirmation | Authority / stops | Writes / result |
|---|---|---|---|---|---|---|
| `CMD-STATUS-RUN` | Show Run Status | `inspect_workflow_run` | Work ID or run record path. | No | Read only; stop when run record is missing or unreadable. | No writes; result current run status. |
| `CMD-STATUS-STAGE` | Show Current Stage | `inspect_workflow_run` | Work ID or run record path. | No | Read only; stop when current stage cannot be determined. | No writes; result current stage and required next gate or artifact action. |
| `CMD-STATUS-NEXT` | Show Next Allowed Operation | `inspect_workflow_run` | Run record, active artifact status, approved checkpoints, open routes. | No | Read only; stop on conflicting statuses or freshness conflicts. | No writes; result recommended next semantic operation and reason. |
| `CMD-STATUS-ROUTES` | Show Open Routes | `inspect_workflow_run` | Run record. | No | Read only; stop on incomplete or inconsistent route records. | No writes; result open routes, owner stages, and required actions. |
| `CMD-STATUS-ARTIFACTS` | Show Artifact Versions | `inspect_workflow_run` | Run record and artifact root. | No | Read only; stop on missing or contradictory artifact metadata. | No writes; result artifact versions with active, approved, stale, and superseded markers. |

## Run State Command Eligibility Matrix

Inspection command intents (`CMD-STATUS-*`) and `CMD-TIER-STATUS` are allowed in any state when their required inputs exist. They must remain read-only and must return an inconsistency instead of choosing or running a write command.

`CMD-TIER-ESTIMATE`, `CMD-TIER-LOCK`, and `CMD-TIER-ESCALATE` are allowed in any non-terminal run state (`active_stage_draft`, `entry_gate_failed`, `quality_gate_failed`, `ready_for_checkpoint_review`, `checkpoint_review`, `checkpoint_changes_requested`, `upstream_gap_routing`, `checkpoint_approved`, `next_stage`). They are refused in `not_started`, `closed_at_plan_checkpoint`, and inconsistent or unknown states. `CMD-TIER-LOCK` is additionally refused once `requirement_brief` has executed `stage-produce`; the operator must reopen the run if a lock change is required after that point.

`CMD-CHECKPOINT-BUNDLE` is allowed only in `checkpoint_review`. It is refused in any other state.

`CMD-RUN-REOPEN` is allowed only in `closed_at_plan_checkpoint`. It does not change the source run's state and creates a new run record for the reopened lineage.

Context-refresh exception: `CMD-RUN-RESUME` may run before ordinary matrix refusal when an existing readable, nonterminal run cannot prove loaded active context because of compaction, interruption, handoff, manual resume, or missing `Resume Context`. In this mode it may only load required reread targets, refresh `Resume Context`, report missing/ambiguous targets, and surface open routes or stale/superseded inputs. It must not advance to a next stage, create a next-stage draft, close a route, approve a checkpoint, or write stage artifact content unless the current run state also allows ordinary `CMD-RUN-RESUME` in the matrix. If the run is `not_started`, `closed_at_plan_checkpoint`, inconsistent, or unknown after reading `run.md`, this exception must stop or return read-only status instead of writing.

The matrix below lists ordinary write-capable command intents allowed by run state. If a command intent is not listed for the current state and the context-refresh exception does not apply, a concrete carrier must refuse it and suggest `CMD-STATUS-NEXT`.

| Run State | Allowed write-capable command intents | Required stops |
|---|---|---|
| `not_started` | `CMD-RUN-START` | Stop all stage, gate, review, checkpoint, route, and close commands. |
| `active_stage_draft` | `CMD-STAGE-LOAD`, `CMD-STAGE-PRODUCE`, `CMD-STAGE-UPDATE`, `CMD-STAGE-READY`, `CMD-GATE-ENTRY`, `CMD-GATE-QUALITY`, `CMD-CONFIRM-RECORD`, `CMD-CONFIRM-REJECT`, `CMD-CONFIRM-LINK`, `CMD-SUBAGENT-DISPATCH`, `CMD-SUBAGENT-MERGE`, `CMD-GAP-RECORD` | Stop checkpoint decision until Quality Gate is `ready` and checkpoint review findings are merged. |
| `entry_gate_failed` | `CMD-GATE-ENTRY`, `CMD-CONFIRM-RECORD`, `CMD-CONFIRM-REJECT`, `CMD-GAP-RECORD`, `CMD-GAP-ROUTE` | Stop artifact production unless the entry failure is repaired or routed to the owner stage. |
| `quality_gate_failed` | `CMD-STAGE-PRODUCE`, `CMD-STAGE-UPDATE`, `CMD-STAGE-READY`, `CMD-GATE-QUALITY`, `CMD-CONFIRM-RECORD`, `CMD-CONFIRM-REJECT`, `CMD-SUBAGENT-DISPATCH`, `CMD-SUBAGENT-MERGE`, `CMD-GAP-RECORD`, `CMD-GAP-ROUTE` | Stop checkpoint review and checkpoint decision until Quality Gate returns `ready`. |
| `ready_for_checkpoint_review` | `CMD-REVIEW-CHECKPOINT`, `CMD-SUBAGENT-REVIEW`, `CMD-GAP-RECORD` | Stop checkpoint decision until review findings are written and merged. |
| `checkpoint_review` | `CMD-REVIEW-CHECKPOINT` or `CMD-SUBAGENT-REVIEW` only for required review sources registered before review began, `CMD-REVIEW-MERGE`, `CMD-CONFIRM-RECORD`, `CMD-CONFIRM-REJECT`, `CMD-CONFIRM-LINK`, `CMD-CHECKPOINT-DECIDE` only after all review findings are merged and required confirmations for the requested decision are recorded, `CMD-CHECKPOINT-BUNDLE` only for eligible no-modifier tiers with each bundled stage's Quality Gate `ready` and findings merged, `CMD-GAP-RECORD`, `CMD-GAP-ROUTE`, `CMD-TIER-ESTIMATE`, `CMD-TIER-LOCK`, `CMD-TIER-ESCALATE` | Stop new unregistered review dispatch; allow confirmation evidence to be recorded while waiting for checkpoint decision; stop checkpoint decision until all review findings are written and merged. Stop `approved` decisions when any unresolved route or required change remains; allow `changes_requested`, `blocked`, `upstream_gap_detected`, or `route_upstream` decisions to record the corresponding non-approval result. Stop `CMD-CHECKPOINT-BUNDLE` when any modifier is present or the requested stage set is not bundle-eligible. |
| `checkpoint_changes_requested` | `CMD-STAGE-PRODUCE`, `CMD-STAGE-UPDATE`, `CMD-STAGE-READY`, `CMD-GATE-QUALITY`, `CMD-CONFIRM-RECORD`, `CMD-CONFIRM-REJECT`, `CMD-GAP-RECORD`, `CMD-GAP-ROUTE` | Stop checkpoint decision until requested changes are made and Quality Gate reruns. |
| `upstream_gap_routing` | `CMD-GAP-ROUTE`, `CMD-GAP-REIMPORT` when an open route already has an approved repaired owner checkpoint, `CMD-STAGE-LOAD`, `CMD-STAGE-PRODUCE`, `CMD-STAGE-UPDATE`, `CMD-STAGE-READY`, `CMD-GATE-QUALITY`, `CMD-CHECKPOINT-DECIDE` only for the open route's owner-stage repair checkpoint, `CMD-ARTIFACT-MARK-STALE` | Stop affected downstream Quality Gate, review, and checkpoint approval until the owner-stage repair passes Quality Gate and Main/User Checkpoint, then re-import is complete. Do not use this state's `CMD-CHECKPOINT-DECIDE` allowance to approve the affected downstream stage before `CMD-GAP-REIMPORT` completes and downstream gate/review/checkpoint rerun. |
| `checkpoint_approved` | `CMD-STAGE-ADVANCE` for non-PLAN stages when no open route remains and no pending confirmation, `CMD-RUN-RESUME` only when no open route remains, `CMD-GAP-REIMPORT` when an open route was repaired by the just-approved owner stage, `CMD-RUN-CLOSE` for approved PLAN only | Stop `CMD-STAGE-ADVANCE` for PLAN stages (use `CMD-RUN-CLOSE` instead). Stop ordinary resume and stage-advance when any open route remains; if the route owner checkpoint is approved, run re-import before selecting a next stage; stop close unless PLAN Checkpoint is approved and no route remains. |
| `next_stage` | `CMD-STAGE-LOAD`, `CMD-GATE-ENTRY`, `CMD-RUN-RESUME` | Stop production until the target stage entry gate passes. |
| `closed_at_plan_checkpoint` | `CMD-RUN-REOPEN` | Stop all other write-capable workflow commands; inspection and `CMD-RUN-REOPEN` (which creates a new run without modifying the closed source) are allowed. |
| inconsistent or unknown | None | Stop all write-capable commands and require operator repair or explicit route clarification. |

State eligibility is necessary but not sufficient. A command intent must also satisfy its catalog row and the mapped operation contract in `workflow-operation-surface.md`.

## User Confirmation Rule

Command intents that require user confirmation must preserve the difference between:

- user-confirmed decisions,
- main-agent checkpoint approval,
- inferred agent recommendations,
- subagent findings,
- unconfirmed assumptions.

Only `CMD-CHECKPOINT-DECIDE` can approve downstream handoff. `CMD-CONFIRM-RECORD` records confirmation evidence, but it does not approve a checkpoint by itself.

`Conditional` means the command intent must use the mapped operation contract to decide whether confirmation is required. If confirmation is required but missing, the command intent must stop or route; it must not downgrade the item to an assumption.

## Command Composition Rules

A carrier may compose multiple command intents only when the composition preserves every intermediate stop condition.

Allowed compositions:

- Start a run and load the initial stage artifact through `CMD-RUN-START`.
- Resume a run and load the next-stage draft through `CMD-RUN-RESUME` only when no open route remains.
- Run checkpoint review subagents through `CMD-SUBAGENT-REVIEW`.
- Record an upstream gap and route to the owner stage only when the owner stage, affected artifacts, and required confirmations are explicit.

Required breaks:

- Stop between Quality Gate `ready` and checkpoint decision.
- Stop between checkpoint review findings and Main/User approval until `CMD-REVIEW-MERGE` has produced merged findings.
- Stop between upstream gap routing and upstream repair. `CMD-GAP-RECORD` and `CMD-GAP-ROUTE` may be composed only to open the route and owner draft; repair must use the owner stage's `CMD-STAGE-PRODUCE` or `CMD-STAGE-UPDATE`, then `CMD-GATE-QUALITY`, then `CMD-CHECKPOINT-DECIDE`.
- Stop after repaired upstream re-import until downstream Quality Gate is rerun or confirmed by the re-import operation. If Quality Gate is not ready, continue downstream Quality Gate work; if it is ready, proceed to checkpoint review and Main/User Checkpoint. Do not hand off downstream before that checkpoint is approved.

## Operation Coverage Matrix

Every operation intent in `workflow-operation-surface.md` must be covered by a command intent or explicitly marked internal-only.

| Operation Intent | Command Intent | Coverage |
|---|---|---|
| Start Workflow Run | `CMD-RUN-START` | Covered |
| Resume Workflow Run | `CMD-RUN-RESUME` | Covered |
| Close Workflow Run | `CMD-RUN-CLOSE` | Covered |
| Reopen Workflow Run | `CMD-RUN-REOPEN` | Covered |
| Estimate Tier | `CMD-TIER-ESTIMATE` | Covered |
| Lock Tier | `CMD-TIER-LOCK` | Covered |
| Escalate Tier | `CMD-TIER-ESCALATE` | Covered |
| Authorize Bundled Checkpoints | `CMD-CHECKPOINT-BUNDLE` | Covered |
| Show Tier Status | `CMD-TIER-STATUS` | Covered |
| Load Or Create Stage Artifact | `CMD-STAGE-LOAD`, `CMD-STAGE-ADVANCE` (after checkpoint_approved, non-PLAN only) | Covered |
| Produce Stage Artifact | `CMD-STAGE-PRODUCE` | Covered |
| Update Stage Artifact | `CMD-STAGE-UPDATE` | Covered |
| Mark Stage Artifact Ready | `CMD-STAGE-READY` | Covered |
| Run Entry Gate | `CMD-GATE-ENTRY` | Covered |
| Run Quality Gate | `CMD-GATE-QUALITY` | Covered |
| Run Checkpoint Review | `CMD-REVIEW-CHECKPOINT` | Covered |
| Merge Checkpoint Review Findings | `CMD-REVIEW-MERGE` | Covered |
| Approve Checkpoint | `CMD-CHECKPOINT-DECIDE` | Covered |
| Record User Confirmation | `CMD-CONFIRM-RECORD` | Covered |
| Reject Or Request Clarification | `CMD-CONFIRM-REJECT` | Covered |
| Link Confirmation To Artifact Section | `CMD-CONFIRM-LINK` | Covered |
| Dispatch Discovery Subagents | `CMD-SUBAGENT-DISPATCH` | Covered |
| Merge Subagent Findings | `CMD-SUBAGENT-MERGE`; `CMD-REVIEW-MERGE` when checkpoint-review subagent findings exist | Covered |
| Run Checkpoint Review Subagents | `CMD-SUBAGENT-REVIEW` | Covered |
| Record Upstream Gap | `CMD-GAP-RECORD` | Covered |
| Route Upstream | `CMD-GAP-ROUTE` | Covered |
| Re-import Repaired Upstream | `CMD-GAP-REIMPORT` | Covered |
| Mark Downstream Artifact Stale | `CMD-ARTIFACT-MARK-STALE` | Covered |
| Show Run Status | `CMD-STATUS-RUN` | Covered |
| Show Current Stage | `CMD-STATUS-STAGE` | Covered |
| Show Next Allowed Operation | `CMD-STATUS-NEXT` | Covered |
| Show Open Routes | `CMD-STATUS-ROUTES` | Covered |
| Show Artifact Versions | `CMD-STATUS-ARTIFACTS` | Covered |

## Internal-Only Operation Coverage

No current operation intent is internal-only.

Future internal-only operation intents must be listed here with:

- operation intent,
- reason it is not operator-facing,
- owning command intent or runtime component,
- allowed writes,
- stop conditions,
- audit evidence required in `run.md` or the owning artifact.

An operation that writes artifacts, changes `run.md`, closes routes, approves checkpoints, or changes artifact freshness must not be hidden as internal-only unless another command intent exposes its audit trail and stop conditions.

## Adapter Design Rules

Future concrete command surfaces must follow these rules:

- Each concrete command maps to exactly one command intent, or to a documented composition from `Command Composition Rules`.
- Each concrete command lists how its parameters satisfy `Required Inputs`.
- Each concrete command preserves preconditions, allowed writes, `run.md` updates, user confirmation rules, stop conditions, forbidden behavior, and result outputs from the mapped operation intents.
- Read-only commands must map only to inspection command intents and must not write artifacts or `run.md`.
- Write commands must make artifact writes and `run.md` writes explicit.
- Confirmation-bearing commands must distinguish user-confirmed decisions from inferred agent recommendations.
- Concrete command syntax must not become part of PLAN content.
- Concrete command syntax must not become a substitute for checkpoint approval.
- Executor adapters may consume an approved PLAN later, but they must not change PLAN authority, traceability, or neutrality.

## Semantic Examples

### Start A New Workflow

Intent:

```text
Begin a workflow run from a raw user requirement.
```

Command intent mapping:

```text
CMD-RUN-START -> Start Workflow Run -> start_workflow_run + load_or_create_artifact
```

Required stop:

```text
Stop if the requirement references a file, repository, design, document, or source whose provenance is unknown.
```

### Continue After Checkpoint Approval

Intent:

```text
Continue from the latest approved checkpoint to the next stage draft.
```

Command intent mapping:

```text
CMD-RUN-RESUME -> Resume Workflow Run -> resume_from_checkpoint + load_or_create_artifact
```

Required stop:

```text
Stop before the next stage's entry gate if upstream references are stale, superseded, or incomplete.
```

### SPEC Finds Missing DESIGN Input

Intent:

```text
SPEC detects a required design decision that DESIGN did not record.
```

Command intent mapping:

```text
CMD-GAP-RECORD -> CMD-GAP-ROUTE -> owner DESIGN draft -> DESIGN Quality Gate -> DESIGN Checkpoint -> CMD-GAP-REIMPORT
```

Required stop:

```text
Stop until repaired DESIGN passes Quality Gate and Main/User Checkpoint, then rerun affected SPEC Quality Gate and Checkpoint.
```

### Inspect Without Mutating

Intent:

```text
Show what can run next without changing artifacts.
```

Command intent mapping:

```text
CMD-STATUS-NEXT -> Show Next Allowed Operation -> inspect_workflow_run
```

Required stop:

```text
Return an inconsistency instead of choosing a next operation when open routes or artifact freshness conflict.
```

## Non-Goals

This document intentionally does not define:

- final user-facing command names,
- short aliases,
- flags or options,
- JSON schemas or HTTP paths,
- MCP tool definitions,
- slash command grammar,
- UI layout,
- skill installation or runtime packaging,
- executor-specific PLAN consumption.

Other carrier details belong to later adapter documents or implementations. Any such later work must preserve the command intent semantics defined here.

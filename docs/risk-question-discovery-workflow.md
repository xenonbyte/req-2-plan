# Risk & Question Discovery Workflow

## Purpose

This document records the agreed workflow for the `Risk & Question Discovery` node. This node runs after `Requirement Brief Checkpoint` is approved and before DESIGN entry.

It systematically finds questions, assumptions, risks, and discussion points that could cause missed scope, wrong design choices, unsafe execution, rework, or incomplete PLAN handoff.

It does not choose the design, write the SPEC, or split implementation tasks.

## Position

Canonical node order is defined in `workflow-invariants.md#canonical-chain`. This document covers the risk-discovery segment:

```text
Requirement Brief Checkpoint
  -> Risk & Question Discovery
  -> Risk Discovery Quality Gate
  -> Risk Discovery Checkpoint
  -> Design Entry Gate
  -> Design Scope Gate
```

## Flow

```text
Risk Entry Gate
  -> Optional Subagent Discovery
  -> Finding Merge
  -> Classification
  -> Assumption Conflict Check
  -> Risk Prioritization
  -> Risk Discovery Canonical Output
  -> Risk Discovery Quality Gate
  -> Risk Discovery Checkpoint
```

Risk Discovery Checkpoint authorizes DESIGN entry. It does not execute Design Entry Gate or Design Scope Gate; both gates are DESIGN-owned. DESIGN runs Design Entry Gate first to validate upstream authorization, then Design Scope Gate to choose DESIGN depth.

## Zero-Blocker Routing Rule

`Requirement Brief` and DESIGN are both zero-blocker stages.

Requirement-definition blockers must be eliminated in `Requirement Brief`. They must not flow into DESIGN.

Design/approach blockers must be eliminated in DESIGN. They must not flow into SPEC or PLAN.

If `Risk & Question Discovery` discovers a missed requirement-definition blocker, the safe next node is `Requirement Brief`, not DESIGN.

If any design/approach blocker remains after DESIGN, the workflow must not produce an execution-ready SPEC or PLAN. It may only produce a draft or blocked handoff that states what is missing, why it blocks execution, and who or what can resolve it.

Use this distinction:

```text
Requirement Brief can eliminate blockers about goal, scope, acceptance, users, operators, constraints, and explicit non-scope.
DESIGN must eliminate blockers about approach, architecture, migration, rollback, compatibility, external dependencies, and execution safety.
```

## Inputs

```text
Requirement Brief v1
Requirement Brief Checkpoint = approved
Requirement Discovery Notes, if available
Requirement Brief Downstream Attention, if present
Context facts, if available
```

If no project or repository context was inspected, this node can still run from the requirement alone, but it must mark context coverage as `requirement-only`.

## Risk Entry Gate

Purpose: confirm Risk Discovery can start from an authorized requirement input.

Pass conditions:

- Requirement Brief Checkpoint is `approved`.
- Raw Requirement and Requirement Brief references are available.
- Context coverage is known, even if it is only `requirement-only`.
- Requirement-definition blockers are not intentionally being carried forward from Requirement Brief.

Fail result:

```text
return_to_requirement_brief
```

## Outputs

Risk Discovery produces one canonical artifact with these sections:

- Upstream References.
- Context Coverage.
- Blocking Questions.
- Assumptions.
- Subagent Discovery Findings, when used.
- Risks.
- Discussion Points.
- Design Triggers.
- Spec Inputs.
- Plan Inputs.
- Quality Gate.
- Risk Discovery Checkpoint.

The canonical output template is defined in `Risk Discovery Canonical Output`.

Requirement Brief `Downstream Attention` items must be classified in this node. They may become risks, design triggers, spec inputs, plan inputs, discussion points, or non-blocking assumptions, but they must not disappear.

## Classification Boundaries

### Blocking Questions

A question is blocking when not answering it would leave goal, scope, acceptance, safety boundary, migration boundary, compatibility, or execution permission undefined.

Examples:

- Is this a full migration or only a core-module migration?
- Is modifying persistent data allowed?
- Must existing API behavior remain compatible?
- When integrating two projects, which project's behavior takes precedence?

### Assumptions

An assumption is non-blocking when the workflow can continue safely if the assumption is explicit and carried forward.

Every assumption must include:

- Source
- Impact if wrong
- Conflict status or handling result
- Which later node must inherit, confirm, or eliminate it

Examples:

- `[ASSUMPTION]` Initial workflow only generates documents and does not execute code changes.
- `[ASSUMPTION]` Executor-specific format, adaptation, orchestration, and management are deferred to a later execution workflow, not the requirement-to-PLAN workflow.

### Assumption Conflict Handling

Assumptions must not silently override confirmed upstream facts.

Rules:

- If a Risk Discovery assumption conflicts with confirmed Requirement Brief scope, non-scope, acceptance, constraints, or source provenance, treat it as a requirement-definition issue and route back to Requirement Brief.
- If two assumptions conflict and the conflict affects goal, scope, acceptance, safety boundary, or source provenance, classify it as a Blocking Question and route to Requirement Brief.
- If two assumptions conflict and the conflict affects approach, architecture, migration, rollback, compatibility, dependency, or execution safety, classify it as a Design Trigger and carry it to DESIGN.
- If the conflict is non-blocking, keep both assumptions, mark source and impact for each, and state which later node must confirm or eliminate them.
- Do not convert a conflicting assumption into a downstream fact.

### Risks

A risk is a possible failure mode or cost even if all questions have answers.

Examples:

- Data migration may be irreversible.
- Two projects may have dependency conflicts.
- A rewrite may make behavior-equivalence testing expensive.
- Agent execution may modify unrelated files if the PLAN is underspecified.

Every risk must include impact, likelihood, priority, mitigation direction, and carry target. Use `workflow-invariants.md#shared-concept-definitions` for the P0-P3 priority framework.

Risk prioritization rules:

- P0 risks must be resolved, explicitly accepted by the user, or routed before downstream handoff.
- P1 risks must have DESIGN mitigation and SPEC/PLAN coverage where relevant.
- P2 risks may be carried downstream with an owner and mitigation direction.
- P3 risks may remain informational if traceability and verification are not affected.
- Irreversible data loss, destructive operation, privacy/security exposure, or unapproved production-state change cannot be lower than P0 unless the reason is explicit and user-approved.

### Discussion Points

A discussion point is a tradeoff requiring human judgment but not necessarily blocking the next node.

Examples:

- Whether DESIGN depth should be light, standard, migration, architecture, or safety focused.
- Whether migration should be big-bang or incremental.
- Whether PLAN should be split by module or by user workflow.

## Scan Dimensions

Always scan the requirement against these dimensions:

```text
Scope
Acceptance
Context
Data
Interfaces
Permissions
Dependencies
Compatibility
Execution
Rollback
Observability
Scale
```

The initial scan over all 12 dimensions is mandatory at every tier; tier only changes the required depth. See [Workflow Complexity Tier Rule](workflow-invariants.md#workflow-complexity-tier-rule) for the per-modifier depth table.

### Tier Escalation

When the scan surfaces modifier-trigger keywords or signals that are not already in the locked tier, call `tier-escalate` before requesting checkpoint approval. The escalation revokes affected bundled checkpoints and is audit-logged in `run.md`. Skipping escalation will trigger forced-subagent-review or bundle-revocation later in DESIGN/SPEC/PLAN and force rework.

## Subagent Use

This section follows the shared Subagent Use structure in `workflow-invariants.md#shared-subagent-use-structure`. The rules below define Risk Discovery-specific discovery behavior.

### Subagent Discovery

Risk Discovery may use subagents to scan independent dimensions in parallel before the canonical output is finalized. This is separate from Subagent Checkpoint Review: discovery subagents help find issues; checkpoint subagents review the completed artifact.

Use subagent discovery when:

- The requirement spans multiple projects, modules, repositories, data stores, APIs, commands, or workflows.
- Migration, replacement, rewrite, integration, destructive operations, compatibility, or rollback risk is present.
- Several scan dimensions require independent evidence collection.
- A broad requirement could miss risks if scanned sequentially.

Allowed subagent discovery tasks:

- Scan one or more Risk Discovery dimensions.
- Find blocking questions, assumptions, risks, discussion points, design triggers, spec inputs, and plan inputs.
- Collect evidence from upstream artifacts or inspected context.
- Identify conflicts between assumptions or between assumptions and upstream facts.

Forbidden subagent discovery tasks:

- Approving Risk Discovery Checkpoint.
- Executing Design Entry Gate or Design Scope Gate.
- Choosing the design approach.
- Writing SPEC contracts.
- Splitting PLAN tasks.
- Treating assumptions as confirmed facts.

Subagent discovery output extends the shared subagent finding template in `workflow-invariants.md#shared-templates`:

```markdown
# Risk Discovery Subagent Finding: <dimension or topic>

## Scope
Risk dimensions, artifacts, and context inspected.

## Findings
Evidence-backed blocking questions, assumptions, risks, discussion points, design triggers, spec inputs, or plan inputs.

## Assumption Conflicts
Conflicts with upstream facts or other assumptions.

## Evidence
Upstream references, paths, commands, or source facts.
```

The main agent must merge subagent discovery findings before Risk Discovery Quality Gate.

Merge subagent findings using `workflow-invariants.md#shared-subagent-merge-rule`.

## Classification Rules

Use these rules to classify each finding:

```text
Changes Goal, Scope, Acceptance, or safety boundary -> Blocking Question
Can proceed only if transparent -> Assumption
Has failure probability or meaningful cost -> Risk
Requires strategy or preference choice -> Discussion Point
Affects architecture or tradeoff choice -> Design Trigger
Affects final behavior -> Spec Input
Affects execution, verification, or rollback -> Plan Input
```

The same finding may belong to multiple categories.

Example:

```text
Question: Is production data modification allowed?
Categories: Blocking Question, Risk, Spec Input, Plan Input
```

## Blocker Placement

Some blockers should be resolved in `Requirement Brief`; others should be resolved in `DESIGN`.

Resolve in `Requirement Brief`:

- Goal ambiguity
- Scope ambiguity
- Non-scope ambiguity
- Missing acceptance criteria
- Unclear user, operator, or affected party
- Whether a user-mentioned technology is a hard constraint, preference, proposed solution, or unknown

Resolve in `DESIGN`:

- Choice between valid implementation approaches
- Architecture boundary
- Migration strategy
- Rollback strategy
- Compatibility strategy
- External dependency strategy
- Safety strategy for destructive or high-risk operations
- Execution strategy when agents or automation will apply changes

If a `Requirement Brief` blocker is found at this node, route back to `Requirement Brief`. Do not carry it forward into DESIGN.

## Risk Discovery Canonical Output

Use the shared upstream-reference template from `workflow-invariants.md#shared-templates`, then include the stage-specific sections below.

Before Risk Discovery Checkpoint can authorize DESIGN entry, check:

- Every requirement-definition blocker is resolved; otherwise safe next node is `Requirement Brief`.
- Every remaining blocker is a design/approach blocker to be resolved in DESIGN.
- No blocker has a latest-resolution node later than DESIGN.
- Every assumption has source, impact, conflict status or handling result, and carry target.
- Every Requirement Brief Downstream Attention item is classified or explicitly rejected with reason.
- Every risk has consequence, likelihood, priority, mitigation direction, and carry target.
- Every discussion point has a decision owner or decision point.
- Every design trigger has a stable `RISK-DES-*` ID and explains required DESIGN coverage or depth.
- Every spec input can become a behavior contract.
- Every plan input can become an execution, verification, or rollback requirement.

Template:

```markdown
# Risk & Question Discovery: <title>

## Upstream References
| Artifact | Reference | Status |
|---|---|---|
| Raw Requirement |  | available |
| Requirement Brief |  | approved |

## Context Coverage
- Level:
- Sources:
- Not inspected:

## Subagent Discovery Findings
| Dimension / Topic | Source | Finding IDs | Evidence |
|---|---|---|---|

## Blocking Questions
| ID | Question | Why it blocks | Resolve in | Owner | Needed before |
|---|---|---|---|---|---|

## Assumptions
| ID | Assumption | Source | Impact if wrong | Conflict status / handling | Carry to |
|---|---|---|---|---|---|

## Risks
| ID | Risk | Impact | Likelihood | Priority | Mitigation direction | Carry to |
|---|---|---|---|---|---|---|

## Discussion Points
| ID | Topic | Options | Decision owner | Needed before |
|---|---|---|---|---|

## Design Triggers
| Design Trigger ID | Source Artifact | Source Item ID | Trigger | Required design topic | Status |
|---|---|---|---|---|---|

## Spec Inputs
| Spec Input ID | Source Artifact | Source Item ID | Item | Required SPEC Contract | Reason | Status |
|---|---|---|---|---|---|---|

## Plan Inputs
| Plan Input ID | Source Artifact | Source Item ID | Item | Required PLAN Constraint | Covers | Status |
|---|---|---|---|---|---|---|

## Quality Gate
- Status: ready | needs_clarification (draft only) | blocked
- Reason:
- Safe next node:
- All 12 scan dimensions appear in the artifact, with `N/A: <reason>` allowed only when the tier permits per [Workflow Complexity Tier Rule](workflow-invariants.md#workflow-complexity-tier-rule).

## Risk Discovery Checkpoint
- Status: approved | changes_requested | route_upstream
- Review Sources:
- Required Changes:
- User Confirmations:
  - DESIGN Entry Authorization: yes | no
```

## Status Meanings

```text
ready: Safe to continue to Risk Discovery Checkpoint.
needs_clarification: Non-blocking clarifications remain. Convert them into explicit assumptions or discussion points, then set Quality Gate to ready before checkpoint. This status cannot enter Risk Discovery Checkpoint.
blocked: Do not move forward until the blocker is resolved or routed to the correct zero-blocker stage.
```

Blocked status does not mean no document should be produced. It means the document must clearly state what blocks progress, why it blocks progress, and how to resolve it.

Quality Gate failure routing:

| Failed check | Return to | Required action |
|---|---|---|
| Requirement-definition blocker remains | Requirement Brief | Resolve goal, scope, acceptance, user/operator, constraint, source provenance, or module coverage issue. |
| Design/approach blocker is unresolved or misrouted | Risk Discovery Classification / DESIGN handoff fields | Classify it as a Design Trigger and route it to DESIGN. |
| Assumption lacks source, impact, or carry target | Assumption Conflict Check / Assumptions | Add source, impact, carry target, and conflict status. |
| Assumption conflicts with confirmed Requirement Brief fact | Requirement Brief | Resolve or revise the confirmed requirement input. |
| Requirement Brief Downstream Attention item is unclassified | Classification | Classify it as risk, design trigger, spec input, plan input, discussion point, assumption, or rejected with reason. |
| Risk lacks consequence, likelihood, priority, mitigation direction, or carry target | Risks / Risk Prioritization | Add impact, likelihood, P0-P3 priority, mitigation direction, and carry target. |
| Discussion point lacks owner or decision point | Discussion Points | Assign owner or specify where the decision is made. |
| Design Trigger lacks stable ID or required coverage/depth | Design Triggers | Add a `RISK-DES-*` ID and state required DESIGN topic or depth input. |
| Spec Input cannot become a behavior contract | Spec Inputs / Requirement Brief or DESIGN | Refine input, or route upstream if missing requirement or design information. |
| Plan Input cannot become execution, verification, or rollback constraint | Plan Inputs / DESIGN | Refine into a PLAN constraint or route to DESIGN as a missing design input. |

## Risk Discovery Checkpoint

Purpose: freeze Risk & Question Discovery output as the authorized input for Design Entry Gate, Design Scope Gate, and DESIGN.

The checkpoint has two layers:

```text
Subagent Checkpoint Review
Main/User Risk Discovery Checkpoint
```

Subagent review may be skipped only for small, low-risk requirements where the main agent can reasonably verify risk discovery directly. It is required for migration, rewrite, replacement, integration, cross-project, safety-sensitive, dependency-heavy, or broad boundary work.

Subagent review checks:

- Requirement-definition blockers are routed back to Requirement Brief.
- Design/approach blockers are routed to DESIGN.
- Assumptions have source, impact, conflict status or handling result, and carry target.
- Requirement Brief Downstream Attention items are classified.
- Risks have consequence, likelihood, priority, mitigation direction, and carry target.
- Discussion points have owner or decision point.
- Design Triggers have stable `RISK-DES-*` IDs and are complete enough for Design Scope Gate.
- Spec Inputs can become behavior contracts.
- Plan Inputs can become execution, verification, or rollback constraints.
- No unconfirmed assumption is silently treated as fact.

Subagent review output extends the shared checkpoint-review template in `workflow-invariants.md#shared-templates`:

```markdown
# Risk Discovery Checkpoint Review

## Status
pass | issues_found | route_upstream

## Routing Findings
Incorrectly routed blockers, assumptions, risks, or discussion points.

## Coverage Findings
Missing risk dimensions, design triggers, spec inputs, or plan inputs.

## Assumption Findings
Unclear assumptions, missing impact, or unconfirmed assumptions treated as facts.

## Recommendation
approve | request_changes | route_upstream
```

Main/User checkpoint output extends the shared checkpoint template in `workflow-invariants.md#shared-templates`:

```markdown
# Risk Discovery Checkpoint

## Status
approved | changes_requested | route_upstream

## Review Sources
Subagent checkpoint reviews and other review sources used.

## Required Changes
Risk Discovery items that must be changed before DESIGN entry.

## User Confirmations
User-confirmed assumptions, discussion decisions, or risk routing.

## DESIGN Entry Authorization
yes | no
```

Risk Discovery Checkpoint must be `approved` before Design Entry Gate can proceed.

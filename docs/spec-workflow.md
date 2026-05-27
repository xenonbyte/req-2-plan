# SPEC Workflow

## Purpose

This document records the agreed workflow for the SPEC stage. SPEC converts ready DESIGN output into precise, testable, implementation-ready behavior contracts.

SPEC does not redefine the requirement, choose technical approaches, change DESIGN decisions, split implementation tasks, or decide executor-specific PLAN format.

## Position

Canonical node order is defined in `workflow-invariants.md#canonical-chain`. This document covers the SPEC segment:

```text
DESIGN Checkpoint
  -> SPEC
  -> SPEC Quality Gate
  -> SPEC Checkpoint
  -> PLAN
```

## Responsibilities

SPEC answers:

- What the system must do after implementation.
- What interfaces, commands, files, events, configuration, or payloads must look like.
- How data and state behave.
- How errors, retries, interruptions, and edge cases behave.
- What permissions, safety, compatibility, and observability rules apply.
- How every confirmed acceptance criterion is covered by behavior contracts.
- Which BDD-style acceptance scenarios express the expected behavior.
- How every DESIGN change point and boundary is covered by behavior contracts.

SPEC must not:

- Redefine goal, scope, non-scope, users, operators, or acceptance.
- Select a technical approach.
- Change DESIGN decisions.
- Introduce new design choices.
- Split implementation work into tasks.
- Choose GSD, Superpowers, or executor-specific PLAN format.
- Write implementation steps.

## Inputs

Required upstream references:

```text
Raw Requirement
Requirement Brief
Risk & Question Discovery
DESIGN
```

Required DESIGN inputs:

```text
Spec Inputs
Change Point Inventory
Requirement Trace Check
Boundary Coverage / Integration Boundary Check
Integration Boundaries, when present
Risk / Attack Gate results
Resolved Blockers
Remaining Assumptions
```

If DESIGN is not ready, SPEC must not start.

## Flow

```text
Spec Entry Gate
  -> Design Coverage Import
  -> Contract Derivation
  -> Boundary Contract Check
  -> Acceptance Trace Check
  -> Testability Gate
  -> PLAN Handoff
  -> Spec Quality Gate
  -> Subagent Checkpoint Review
  -> Main/User SPEC Checkpoint
```

## Gate 1: Spec Entry Gate

Purpose: confirm SPEC can start.

Pass conditions:

- DESIGN Checkpoint is `approved`.
- No design blocker remains.
- Upstream references are present and accessible.
- Spec Inputs are explicit.
- Change Point Inventory is present.
- Boundary Coverage / Integration Boundary Check is complete where required.
- Integration Boundaries are present for integration, replacement, or cross-project work.

Fail result:

```text
return_to_design
```

SPEC must not guess missing design decisions.

## Design Coverage Import

Purpose: import all DESIGN outputs that must become behavior contracts.

Every item in these DESIGN sections must be mapped:

- Spec Inputs.
- Change Point Inventory.
- Requirement Trace Check.
- Boundary Coverage / Integration Boundary Check.
- Integration Boundaries, when present.
- Risk / Attack Gate results.
- Remaining non-blocking assumptions.

DESIGN Spec Inputs must use the shared schema in `workflow-invariants.md#downstream-input-schema-rule`. SPEC must preserve the upstream `Spec Input ID` while deriving contracts.

Use `workflow-invariants.md#coverage-closure-rule` to close every imported upstream ID. Short tables are allowed for light or standard work, but each imported ID must have a closure status.

Suggested template:

```markdown
## Design Coverage Import

| Design Source | Source ID | Item | Required SPEC Contract | Closure Status | Resolution / Route |
|---|---|---|---|---|---|
```

## Contract Derivation

Purpose: convert design inputs into precise behavior contracts.

Contract categories:

```text
Functional Requirements
Interfaces
Data / State
Error Behavior
Permissions / Safety
Compatibility
Observability
Acceptance Scenarios
Edge Cases
```

Every contract must be:

- Specific.
- Testable.
- Traceable to Requirement Brief or DESIGN.
- Free of implementation-task language.
- Free of unresolved design choice.

## Boundary Contract Check

Purpose: ensure every design boundary has a matching SPEC contract.

For each boundary, SPEC must define:

- Inputs and outputs.
- Data and state semantics.
- Error behavior.
- Permission or safety rules.
- Compatibility rules.
- Observable outcomes.
- Testable conditions.

For integration boundaries, SPEC must additionally define:

- Current operation.
- Target capability.
- Responsibility split visible to callers or users.
- Data/state mapping semantics.
- Backward compatibility or intentional incompatibility.
- Migration-visible behavior, if any.

Use `workflow-invariants.md#shared-concept-definitions` for `migration-visible behavior`.

Suggested template:

```markdown
## Boundary Contract Check

| Boundary | Contract Area | Input / Output | Data / State | Error Behavior | Compatibility | Migration-visible Behavior | Rollback / Recovery | Required Behavior | Trace | Testability |
|---|---|---|---|---|---|---|---|---|---|---|
```

## Acceptance Trace Check

Purpose: ensure every confirmed acceptance criterion is covered by SPEC.

Suggested template:

```markdown
## Acceptance Trace Check

| Acceptance | SPEC Coverage | Verification Idea | Status |
|---|---|---|---|
```

## Testability Gate

Purpose: prevent vague or untestable requirements from entering PLAN.

Pass conditions:

- Every functional requirement has an observable outcome.
- Every interface contract has inputs, outputs, and error behavior where applicable.
- Every data/state contract has state transitions or persistence semantics where applicable.
- Every compatibility contract states what remains compatible or what intentionally changes.
- Every acceptance scenario has a verification idea.
- No contract depends on hidden implementation assumptions.

Fail result:

```text
return_to_spec_derivation
```

Failure routing:

| Failed check | Return to | Required action |
|---|---|---|
| Functional requirement lacks observable outcome | Contract Derivation | Rewrite the contract as externally observable behavior. |
| Interface contract lacks input, output, or error behavior | Contract Derivation / Boundary Contract Check | Add interface shape, valid inputs, outputs, and error behavior. |
| Data/state contract lacks state transition or persistence semantics | Contract Derivation / Boundary Contract Check | Define state transition, persistence, mutation, migration-visible behavior, or explicit no-op/preserve semantics. |
| Compatibility contract does not state what remains compatible or intentionally changes | Boundary Contract Check / Compatibility | Add backward compatibility, intentional incompatibility, or migration-visible compatibility behavior. |
| Acceptance scenario has no verification idea | Acceptance Trace Check | Add a verification idea or route upstream if acceptance is not verifiable. |
| Contract depends on hidden implementation assumptions | Contract Derivation / DESIGN | Remove hidden assumptions, make behavior observable, or mark `upstream_gap_detected` if a DESIGN decision is missing. |
| Contract cannot be tested without unsafe external or production state | Testability Gate / DESIGN | Add safe test boundary, mock/fixture strategy, manual acceptance check, or route to DESIGN for verification architecture. |

## Subagent Use

SPEC may use subagents for contract extraction, coverage checking, boundary checking, and test scenario discovery.

This section follows the shared Subagent Use structure in `workflow-invariants.md#shared-subagent-use-structure`. The rules below define SPEC-specific contract and coverage review behavior.

Subagents follow `workflow-invariants.md#subagent-model-rule`.

Allowed subagent tasks:

- Extract contracts from DESIGN inputs.
- Check coverage between DESIGN and SPEC.
- Check boundary contract completeness.
- Identify missing edge cases.
- Suggest verification ideas.
- Identify ambiguity in contract wording.

Forbidden subagent tasks:

- Changing requirement scope.
- Changing DESIGN decisions.
- Choosing technical approaches.
- Splitting PLAN tasks.
- Choosing executor-specific PLAN format.
- Treating unconfirmed assumptions as confirmed contracts.

Subagent output extends the shared subagent finding template in `workflow-invariants.md#shared-templates`:

```markdown
# SPEC Subagent Finding: <topic>

## Scope
What this subagent checked.

## Sources
Upstream artifacts and sections inspected.

## Findings
Evidence-backed findings.

## Missing Contracts
Contracts that appear missing or underspecified.

## Ambiguities
SPEC wording or upstream inputs that remain unclear.

## Verification Ideas
Possible verification paths for contracts.

## Evidence
References to upstream sections, paths, or identifiers.
```

The main agent must merge subagent findings before finalizing SPEC.

## PLAN Handoff

SPEC must produce PLAN inputs before Spec Quality Gate and SPEC Checkpoint approval:

Use the shared Plan Input schema from `workflow-invariants.md#downstream-input-schema-rule`:

```markdown
| Plan Input ID | Source Artifact | Source Item ID | Item | Required PLAN Constraint | Covers | Status |
|---|---|---|---|---|---|---|
```

Plan Inputs cover contracts to implement, verification expectations, edge cases, compatibility checks, safety checks, migration-visible behavior, and known risky areas.

Risk Discovery Plan Inputs carried through DESIGN must become traceable `SPEC-PLAN-*` items, so PLAN can verify this chain:

```text
Risk Discovery Plan Input -> DESIGN Plan Input -> SPEC-PLAN-* -> PLAN coverage
```

SPEC must not write the final PLAN.

## Spec Quality Gate

Purpose: decide whether SPEC is internally complete enough to enter checkpoint review.

Pass conditions:

- Upstream references are present and accessible.
- DESIGN Checkpoint is approved.
- Every Spec Input is represented.
- Every Design Coverage Import row preserves the upstream Design `Spec Input ID` when present.
- Every imported DESIGN source ID has closure status under `workflow-invariants.md#coverage-closure-rule`.
- Every Change Point has a contract or an explicit no-op/preserve contract using the shared `preserve` and `no-op` definitions.
- Every required Boundary or Integration Boundary has contracts.
- Every confirmed Acceptance criterion has SPEC coverage.
- Every contract is testable.
- No design decision is missing.
- No requirement scope is changed.
- No implementation task or executor format is specified.
- Remaining assumptions are explicit and non-blocking.
- Risk Discovery Plan Inputs carried through DESIGN are represented as traceable `SPEC-PLAN-*` items where relevant.

Fail result:

```text
return_to_spec_step | upstream_gap_detected
```

`return_to_spec_step` means the SPEC artifact itself is incomplete and must return to the SPEC step that owns the missing contract or trace. `upstream_gap_detected` means SPEC found missing upstream information it cannot decide. SPEC must not invent the missing answer. Route back to the responsible upstream stage from `workflow-invariants.md#upstream-gap-routing-rule`.

Quality Gate failure routing:

| Failed check | Return to | Required action |
|---|---|---|
| Upstream reference or DESIGN Checkpoint missing | Spec Entry Gate | Restore required upstream references or wait for DESIGN approval. |
| Spec Input not represented or Design `Spec Input ID` lost | Design Coverage Import / Contract Derivation | Add a contract and preserve the source ID, or mark `upstream_gap_detected` if DESIGN lacks the needed input. |
| Imported DESIGN source ID has no closure status | Design Coverage Import | Add `covered`, `preserve`, `no-op`, `return_to_spec_step`, or `upstream_gap_detected` and route unresolved items before checkpoint review. |
| Change Point lacks contract or no-op/preserve contract | Contract Derivation | Add the behavior contract or explicit preserve/no-op contract using the shared definitions. |
| Boundary or Integration Boundary lacks contract | Boundary Contract Check | Define I/O, data/state, errors, permissions, compatibility, observability, and testability. |
| Acceptance criterion lacks SPEC coverage | Acceptance Trace Check | Add SPEC coverage and verification idea. |
| Contract is vague or untestable | Testability Gate / Contract Derivation | Rewrite as observable, testable behavior. |
| Missing design decision | DESIGN | Mark `upstream_gap_detected` and route to DESIGN. |
| Risk Discovery Plan Input carried by DESIGN lacks `SPEC-PLAN-*` representation | PLAN Handoff / Contract Derivation | Add a traceable `SPEC-PLAN-*` item, or route to DESIGN if the DESIGN Plan Input is missing. |
| Missing Risk Discovery classification, Spec Input, or Plan Input | Risk & Question Discovery | Mark `upstream_gap_detected` and route to Risk Discovery Quality Gate / Checkpoint repair. |
| Requirement scope changed | Requirement Brief | Mark `upstream_gap_detected` and route to Requirement Brief. |
| Implementation task or executor format appears | Contract Derivation | Remove task/executor content and keep only behavior contracts. |
| Remaining assumption is blocking or unconfirmed | Requirement Brief / DESIGN | Route to the upstream stage that owns the missing confirmation. |

## Subagent Checkpoint Review

Purpose: run an independent checkpoint review before the main agent or user authorizes PLAN handoff.

Subagent Checkpoint Review can run only after Spec Quality Gate is `ready`. If checkpoint review finds an upstream gap, using the PLAN Handoff to start PLAN is not allowed; route back to the responsible upstream stage and rerun Spec Quality Gate before another checkpoint.

This review may be skipped only for small, low-risk SPECs where the main agent can reasonably verify coverage directly. It is required for migration, replacement, rewrite, integration, cross-project, safety-sensitive, or broad boundary work.

Subagents perform checkpoint checks and report findings. They do not approve PLAN handoff.

Review checks:

- SPEC covers Requirement Brief and DESIGN.
- SPEC covers Change Point Inventory.
- SPEC covers Boundary Coverage / Integration Boundary Check.
- SPEC covers Integration Boundaries when present.
- SPEC contracts are testable.
- SPEC has no ambiguous behavior.
- SPEC does not contain design choices or PLAN steps.
- SPEC has no blocking or hidden assumptions. Explicit non-blocking assumptions may remain if they are traceable and carried forward.

Subagent review output extends the shared checkpoint-review template in `workflow-invariants.md#shared-templates`:

```markdown
# SPEC Checkpoint Review

## Status
pass | issues_found | upstream_gap_detected

## Coverage Findings
Coverage gaps against Requirement Brief, DESIGN, Change Point Inventory, and boundaries.

## Ambiguity Findings
Ambiguous or untestable contracts.

## Traceability Findings
Missing trace links to upstream artifacts.

## Boundary Findings
Boundary or integration contract gaps.

## Testability Findings
Contracts without clear verification paths.

## Recommendation
approve | request_changes | route_upstream
```

## Main/User SPEC Checkpoint

Purpose: freeze SPEC as the authorized input for PLAN.

The main agent merges subagent checkpoint reviews, applies required SPEC updates, asks the user for confirmation when behavior or compatibility choices need explicit approval, and decides whether the PLAN Handoff can be used to start PLAN.

Only the main agent and user can approve SPEC and its PLAN Handoff for PLAN start.

Pass conditions:

- Subagent checkpoint reviews are merged when used.
- Required changes are resolved.
- User-owned behavior, compatibility, boundary, or error-handling confirmations are recorded.
- SPEC is approved as the sole behavior-contract input for PLAN.

Fail result:

```text
changes_requested | upstream_gap_detected
```

Checkpoint output extends the shared checkpoint template in `workflow-invariants.md#shared-templates`:

```markdown
# SPEC Checkpoint

## Status
approved | changes_requested | upstream_gap_detected

## Review Sources
Subagent checkpoint reviews and other review sources used.

## Required Changes
SPEC items that must be changed before PLAN handoff.

## User Confirmations
User-confirmed behavior, compatibility, boundary, or error-handling choices.

## PLAN Authorization
yes | no
```

## Example: Integration Boundary to Contracts

For `forma` replacing `pencil` design capability with `opendesign`, SPEC turns the approved DESIGN boundary into behavior contracts.

Positive SPEC handling:

```markdown
## Functional Requirements
- SPEC-FR-001: Opening an existing supported design document from forma must produce the same user-visible canvas state after opendesign integration.

## Compatibility
- SPEC-COMPAT-001: Existing supported pencil-backed design documents must remain openable or produce a documented unsupported-feature error that preserves the original file without mutation.

## Error Behavior
- SPEC-ERR-001: If opendesign cannot parse a design feature, forma must show a recoverable error and must not overwrite the source document.

## Acceptance Scenarios
- SPEC-ACC-001: Given a supported existing design document, when the user opens it after integration, then the rendered document state matches the approved compatibility expectation.
```

Anti-example:

```text
Do not write "implement an opendesign adapter" as a SPEC contract. That is an implementation task, not observable behavior.
```

## SPEC Template

```markdown
# SPEC: <title>

## Upstream References
| Artifact | Reference | Status |
|---|---|---|
| Raw Requirement |  | available |
| Requirement Brief |  | approved |
| Risk & Question Discovery |  | approved |
| DESIGN |  | approved |

## Summary
Behavioral summary of what must be true after implementation.

## Design Coverage Import
Mapping from DESIGN inputs to SPEC contracts. Preserve upstream Design `Spec Input ID` values and assign closure status for every imported upstream ID.

## Functional Requirements
Required user-visible or operator-visible behavior.

## Interfaces
API, CLI, file, event, configuration, command, or payload contracts.

## Data / State
Data semantics, state transitions, persistence, and migration-visible behavior as defined in `workflow-invariants.md`.

## Error Behavior
Errors, interruptions, retries, partial failures, and recovery-visible behavior.

## Permissions / Safety
Permission, privacy, data safety, destructive-operation, and execution-safety contracts.

## Compatibility
Old behavior, old data, old API, old file, old workflow, or intentional incompatibility contracts.

## Observability
Logs, metrics, traces, status outputs, diagnostics, or failure visibility requirements.

## Boundary Contract Check
Contracts for module, interface, data, state, permission, compatibility, migration, rollback, dependency, execution, and integration boundaries.

## Acceptance Scenarios
Confirmed acceptance criteria mapped to SPEC behavior.

BDD-style scenarios may be used here as formal behavior contracts, provided they are confirmed, testable, and traceable to Requirement Brief and DESIGN.

## Edge Cases
Boundary inputs, missing data, repeated operations, concurrency, interruption, partial failure, and rollback-visible cases.

## Traceability
Mapping from Requirement Brief, DESIGN, Change Point Inventory, and Integration Boundaries to SPEC sections.

## Plan Inputs
Contracts, checks, edge cases, and constraints that PLAN must implement and verify. Use the shared Plan Input schema and `SPEC-PLAN-*` IDs for plan inputs that must be traceable in PLAN, especially Risk Discovery Plan Inputs carried through DESIGN.

## Spec Quality Gate
ready | return_to_spec_step | upstream_gap_detected

## SPEC Checkpoint
approved | changes_requested | upstream_gap_detected
```

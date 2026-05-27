# DESIGN Workflow

## Purpose

This document records the agreed workflow for the DESIGN stage. DESIGN converts a ready `Requirement Brief` and risk discovery output into one selected technical approach with no remaining design blockers.

DESIGN is mandatory for every requirement. Low-risk work uses lightweight DESIGN; high-risk work uses deeper DESIGN coverage.

DESIGN does not redefine the requirement, write detailed SPEC contracts, split implementation tasks, or decide executor-specific PLAN format.

## Position

Canonical node order is defined in `workflow-invariants.md#canonical-chain`. This document covers the DESIGN segment:

```text
Risk Discovery Checkpoint
  -> Design Entry Gate
  -> Design Scope Gate
  -> DESIGN
  -> DESIGN Quality Gate
  -> DESIGN Checkpoint
  -> SPEC
```

## Responsibilities

DESIGN answers:

- How the requirement should be solved.
- Which technical approach is selected.
- Why this approach is selected.
- Which alternatives were rejected and why.
- How module boundaries, interfaces, data, state, compatibility, migration, rollback, dependencies, and execution safety are handled.
- Which design points, change points, integration boundaries, migration boundaries, compatibility boundaries, and execution-safety boundaries exist.
- What verification strategy or test architecture the design requires.
- Which design decisions must become SPEC behavior contracts.
- Which design decisions must become PLAN execution, verification, or rollback constraints.

DESIGN must not:

- Redefine the requirement.
- Expand or shrink confirmed scope.
- Treat candidate acceptance as confirmed acceptance.
- Write complete API, state, or error contracts; those belong in SPEC.
- Split concrete implementation tasks; those belong in PLAN.
- Write TDD execution steps; those belong in PLAN.
- Decide GSD, Superpowers, or executor-specific PLAN format.

## Inputs

Required inputs:

```text
Requirement Brief v1
Requirement Brief Checkpoint = approved
Risk & Question Discovery
Risk Discovery Checkpoint = approved
Confirmed Source Provenance
Scope Inventory
Confirmed Acceptance
Design Triggers
Spec Input candidates
Plan Input candidates
```

If `Requirement Brief` has unresolved blockers, DESIGN must not start.

## Flow

```text
Design Entry Gate
  -> Design Scope Gate
  -> Design Discovery
  -> Subagent Conflict Gate
  -> Requirement Trace Check
  -> Option Analysis
  -> Decision Gate
  -> User Decision Gate
  -> Change Point Inventory
  -> Boundary Coverage / Integration Boundary Check
  -> Risk / Attack Gate
  -> Verification Strategy / Test Architecture
  -> Spec & Plan Handoff
  -> Design Quality Gate
  -> Subagent Checkpoint Review
  -> Main/User DESIGN Checkpoint
```

## Gate 1: Design Entry Gate

Purpose: confirm the workflow is allowed to enter DESIGN.

Pass conditions:

- Requirement Brief Checkpoint is `approved`.
- Risk Discovery Checkpoint is `approved`.
- Requirement Brief has no requirement-definition blockers.
- Acceptance criteria are confirmed.
- Source provenance is confirmed.
- Scope Inventory is classified.
- Risk & Question Discovery is complete.
- No requirement-definition issue is being carried into DESIGN.

Failure routing:

| Failed condition | Return to | Required action |
|---|---|---|
| Requirement Brief Checkpoint is not `approved` | Requirement Brief Checkpoint | Approve or revise the Requirement Brief before DESIGN. |
| Risk Discovery Checkpoint is not `approved` | Risk & Question Discovery | Complete Risk Discovery Quality Gate and checkpoint approval. |
| Requirement Brief still has requirement-definition blockers | Requirement Brief | Resolve blockers in the zero-blocker Requirement Brief stage. |
| Acceptance criteria, source provenance, or Scope Inventory is incomplete | Requirement Brief | Confirm acceptance, source provenance, or scope inventory. |
| Risk & Question Discovery is incomplete | Risk & Question Discovery | Complete blocker, assumption, risk, discussion, design trigger, spec input, and plan input discovery. |
| Requirement-definition issue is being carried into DESIGN | Requirement Brief | Route back; DESIGN must not absorb requirement-definition blockers. |

Design Entry Gate output:

```markdown
## Design Entry Gate
- Status: pass | blocked | route_upstream
- Requirement Brief Checkpoint:
- Risk Discovery Checkpoint:
- Missing / Invalid Inputs:
- Failure Routing:
- Safe next step:
```

## Gate 2: Design Scope Gate

Purpose: choose DESIGN depth and required topics. It does not decide whether DESIGN exists.

Design Scope Gate is a DESIGN-owned entry gate that runs after Design Entry Gate. It is shown before `DESIGN` in the canonical chain because it must run before Design Discovery, but it belongs to the DESIGN workflow and produces DESIGN entry decisions.

Possible design levels:

```text
light_design: Low risk, approach is nearly obvious, no migration.
standard_design: Normal feature or module-level change.
architecture_design: Architecture boundaries, module relationships, or interface relationships change.
migration_design: Migration, rewrite, replacement, or project integration.
safety_design: Data, permissions, production, privacy, or destructive operations.
dependency_design: External API, MCP, CLI, third-party service, or critical dependency behavior.
```

Levels may be combined, such as:

```text
migration_design + safety_design
```

Design Scope Gate derives design levels from Risk Discovery `RISK-DES-*` Design Triggers, Requirement Brief scope, and known source/context facts.

Decision framework:

| Trigger or condition | Required design level |
|---|---|
| Low-risk local change with obvious approach, no migration, no public boundary change | `light_design` |
| Normal feature or module-level change with limited blast radius | `standard_design` |
| Module ownership, architecture boundary, public interface, event/file/API boundary, or cross-module relationship changes | `architecture_design` |
| Migration, rewrite, replacement, integration, cross-project work, or behavior-equivalence requirement | `migration_design` |
| Data mutation, destructive operation, permission/privacy concern, production state, safety boundary, or irreversible operation | `safety_design` |
| External API, MCP, CLI, third-party service, package/runtime dependency, or critical dependency behavior | `dependency_design` |

Selection rules:

- If multiple triggers apply, combine all required levels.
- If Risk Discovery has any `RISK-DES-*` Design Trigger, the Design Scope Gate must map it to at least one required design level or explicitly reject it with reason.
- `light_design` is allowed only when no migration, architecture, safety, dependency, or compatibility trigger is present.
- `standard_design` is the default when the change is not light but no specialized level is required.

Design Scope Gate output:

```markdown
## Design Scope Gate
- Design Levels:
- Required Design Topics:
- Source Triggers:
- Trigger-to-Level Mapping:
- Safe next step:
```

## Design Discovery

Purpose: gather enough technical evidence to compare options and select one approach.

DESIGN may use subagents for scheme research, impact analysis, and blast-radius discovery.

This section follows the shared Subagent Use structure in `workflow-invariants.md#shared-subagent-use-structure`. The rules below define DESIGN-specific research and impact-analysis behavior.

Subagents follow `workflow-invariants.md#subagent-model-rule`.

Use subagents when:

- Multiple implementation approaches are plausible.
- The change affects multiple modules, repositories, services, or agent capabilities.
- Migration, rewrite, replacement, or integration impact is broad.
- Compatibility, rollback, safety, or dependency behavior needs independent analysis.
- Impact analysis requires tracing callers, callees, ownership boundaries, tests, or configuration across the codebase.

Allowed subagent tasks:

- Option research.
- Impact analysis.
- Dependency and integration analysis.
- Compatibility analysis.
- Migration and rollback feasibility analysis.
- Safety and permission impact analysis.
- Existing pattern discovery.
- Test and verification surface discovery.

Forbidden subagent tasks:

- Making the final design decision.
- Expanding or changing requirement scope.
- Treating assumptions as confirmed facts.
- Producing final SPEC or PLAN.
- Choosing executor-specific PLAN format.
- Ignoring unresolved conflicts between findings.

Subagent output extends the shared subagent finding template in `workflow-invariants.md#shared-templates`:

```markdown
# Design Subagent Finding: <topic>

## Scope
What this subagent analyzed.

## Sources
Paths, repositories, docs, tests, configs, symbols, commands, or tools inspected.

## Facts
Evidence-backed technical facts.

## Options Observed
Viable options discovered, with evidence.

## Impact
Affected modules, interfaces, data, dependencies, tests, configs, or workflows.

## Risks
Design risks found.

## Compatibility / Migration / Rollback Notes
Only if relevant.

## Unknowns
Information still missing.

## Evidence
Key files, paths, commands, symbols, or references supporting the findings.
```

The main agent must merge subagent findings before selecting a decision.

Merge responsibilities:

- Deduplicate findings.
- Preserve conflicts instead of guessing.
- Classify evidence strength.
- Map findings to design options.
- Convert unresolved conflicts into design blockers or explicit tradeoffs.
- Confirm that requirement scope was not changed by subagent output.

Use `workflow-invariants.md#shared-subagent-merge-rule` for the merge decision tree.

## Subagent Conflict Gate

Purpose: prevent conflicting subagent findings from being silently resolved by the main agent.

This gate is required when DESIGN uses subagents.

Conflict examples:

- Subagents disagree about module ownership or responsibility.
- Subagents report different impact scopes.
- One finding says migration is feasible while another identifies compatibility risk.
- Option feasibility conclusions conflict.
- Test or verification surface differs in a way that affects design confidence.

Resolution rules:

- Evidence-level duplicates may be merged.
- Direct conflicts must be preserved.
- A conflict that affects selected approach becomes a design blocker or explicit tradeoff.
- A conflict that requires product, cost, compatibility, or risk preference goes to User Decision Gate.
- DESIGN must not hide conflicts inside assumptions.

Suggested template:

```markdown
## Subagent Conflict Gate

| Conflict | Sources | Impact | Resolution | Carry To |
|---|---|---|---|---|
```

## Requirement Trace Check

Purpose: ensure DESIGN covers every confirmed requirement chain before selecting or finalizing the approach.

This check maps upstream inputs to design handling:

- Every `In Scope` item from Scope Inventory has a design response.
- Every relevant capability has an owner, target module, or explicit handling strategy.
- Every `Out of Scope` item is not accidentally included.
- Every `Candidate` item that affects design has been confirmed or excluded before DESIGN exits.
- Every confirmed acceptance criterion can be traced to design capabilities.
- Every Risk & Question Discovery design input is handled.

For migration, replacement, rewrite, and integration work, this check must be explicit and table-driven.

Suggested template:

```markdown
## Requirement Trace Check

| Requirement / Scope Item | Source | Design Handling | Status | Spec Input | Plan Input |
|---|---|---|---|---|---|
```

## Option Analysis

Purpose: compare viable approaches before selecting one.

Every DESIGN must include:

```text
Recommended Option
Minimal Option
Rejected Option(s)
```

If only one option is viable, DESIGN must explain why other apparent options are not valid or not worth considering.

Each option should include:

- Approach summary.
- What existing code, modules, tools, or patterns it builds on.
- Benefits.
- Costs.
- Risks.
- Migration, compatibility, rollback, dependency, and safety implications when relevant.

## Decision Gate

Purpose: select exactly one design direction.

Pass conditions:

- One option is selected.
- Rationale is explicit.
- Rejected options have rejection reasons.
- Design assumptions are explicit.
- Close tradeoffs are surfaced to the user when human judgment is needed.

Fail result:

```text
blocked_in_design
```

DESIGN must not enter SPEC with unresolved "choose A or B" ambiguity.

## User Decision Gate

Purpose: require explicit user confirmation for high-cost or preference-sensitive design choices.

This gate is required when:

- Multiple options have close tradeoffs.
- The decision affects data migration or irreversible state.
- The decision changes compatibility strategy.
- The decision introduces a critical dependency.
- The decision removes, replaces, or deprecates existing capability.
- The decision materially expands maintenance cost.
- Subagent conflicts require product, cost, compatibility, or risk preference.

Pass conditions:

- Required user decisions are listed.
- User-confirmed choices are recorded.
- Rejected choices and reasons are recorded.
- No user-owned decision remains unresolved.

Fail result:

```text
blocked_in_design
```

Suggested template:

```markdown
## User Decision Gate

| Decision | Options | Recommendation | User Choice | Reason | Impact |
|---|---|---|---|---|---|
```

## Change Point Inventory

Purpose: list every required design-level change point before SPEC and PLAN.

This inventory does not describe implementation steps. It records what must change, be preserved, or remain untouched.

Use `workflow-invariants.md#shared-concept-definitions` for the difference between `preserve` and `no-op`.

Change types:

```text
add
modify
replace
remove
preserve
no-op
```

Each change point should identify:

- Module, capability, interface, data, state, config, dependency, workflow, or test surface.
- Change type.
- Reason.
- Design decision that requires it.
- Spec input.
- Plan input.

Suggested template:

```markdown
## Change Point Inventory

| Area | Current State | Change Type | Target State | Reason | Spec Input | Plan Input |
|---|---|---|---|---|---|---|
```

## Boundary Coverage / Integration Boundary Check

Purpose: identify all design and change boundaries, then verify each one has enough detail for SPEC and PLAN.

This check is mandatory for:

- Migration.
- Replacement.
- Rewrite.
- Integration.
- Cross-project or cross-repository work.
- Cross-module architecture change.
- Public interface or data compatibility change.
- Safety-sensitive or destructive operation.

Boundary categories:

```text
Module boundary
API / CLI / event / file-format boundary
Data / state boundary
Storage / persistence boundary
Permission / safety boundary
Compatibility boundary
Migration boundary
Rollback boundary
Dependency boundary
Execution boundary
```

Each boundary must answer:

- What is the boundary?
- Which current-side module, workflow, or capability is involved?
- Which target-side module, workflow, or capability receives or implements it?
- What is the responsibility split?
- What inputs and outputs cross the boundary?
- What data or state transformation is needed?
- How are errors handled?
- How is compatibility preserved or intentionally changed?
- Is migration required?
- Is rollback required?
- What must SPEC define?
- What must PLAN verify or sequence?

Suggested template:

```markdown
## Boundary Coverage Check

| Boundary ID | Boundary | Current Side | Target Side | Responsibility | Input / Output | Data / State | Errors | Compatibility | Migration | Rollback | Spec Inputs | Plan Inputs |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
```

For integration, replacement, or cross-project work, include an explicit Integration Boundaries table:

```markdown
## Integration Boundaries

| Integration Boundary ID | Integration Boundary | Current Project / Module | Target Project / Module | Current Operation | Target Capability | Responsibility Split | Input / Output | Data / State Mapping | Error Handling | Compatibility | Migration | Rollback | Spec Inputs | Plan Inputs |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
```

For cross-project work, apply `workflow-invariants.md#cross-project-checklist` before the Design Quality Gate.

Example for `forma` replacing `pencil` design capability with `opendesign`:

```text
First identify which forma modules receive or integrate opendesign capabilities.
Then list every integration point between forma design operations and opendesign capabilities.
Then confirm responsibility, data/state, compatibility, migration, rollback, SPEC input, and PLAN input for each integration point.
```

Positive DESIGN handling:

```markdown
## Integration Boundaries
| Integration Boundary ID | Integration Boundary | Current Project / Module | Target Project / Module | Current Operation | Target Capability | Responsibility Split | Input / Output | Data / State Mapping | Error Handling | Compatibility | Migration | Rollback | Spec Inputs | Plan Inputs |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| DES-INT-001 | Design document open/render | forma design-document module | opendesign document/render module | Open existing pencil-backed design document and render it in forma | Parse and render equivalent opendesign document state | forma owns product workflow and UI invocation; opendesign owns document model/render semantics | Existing design document input -> rendered canvas state or recoverable parse result | Map pencil-backed document state to opendesign render semantics without mutating the source document | Unsupported feature produces a recoverable non-mutating error | Supported existing documents remain openable; unsupported features fail with a documented non-mutating error | No data migration for the open path unless a separate DESIGN decision approves conversion | Disable the opendesign open path and retain the source document unchanged | Define visible open/render behavior, compatibility behavior for old documents, and error behavior for unsupported features | Sequence adapter boundary before migration checks; add compatibility and golden/equivalence verification |
```

Anti-example:

```text
Do not write "replace pencil with opendesign" as a single design decision without listing each integration boundary ID, responsibility split, data/state mapping, compatibility rule, migration handling, rollback handling, SPEC input, and PLAN input.
```

## Risk / Attack Gate

Purpose: challenge the selected design before handoff.

Check at least:

```text
Dependency failure: What happens if an external dependency, API, MCP, CLI, or service is unavailable?
Scale explosion: What breaks first at 10x data volume, task count, or usage?
Rollback cost: Can the direction be reversed, and what state must be restored?
Data safety: Can the design corrupt, delete, or silently change data?
Compatibility: How are old behavior, old data, old APIs, and old users handled?
Execution safety: How will later agent execution avoid unrelated changes or unsafe operations?
```

If an attack invalidates the selected design, return to Option Analysis and revise or choose another option.

P0 and P1 risks from Risk Discovery must be addressed first. P0 risks require a selected mitigation, explicit user acceptance, or upstream routing before DESIGN handoff.

Depth by design level:

| Design level | Required depth |
|---|---|
| `light_design` | Brief check of applicable dimensions. State why omitted dimensions are not relevant. |
| `standard_design` | Cover all six dimensions with concise risk, mitigation, and verification notes. |
| `architecture_design` | Emphasize dependency failure, compatibility, execution safety, and scale impact across module boundaries. |
| `migration_design` | Deep coverage for rollback cost, data safety, compatibility, migration-visible behavior, partial migration states, and golden/equivalence verification. |
| `safety_design` | Deep coverage for data safety, permissions, destructive operations, privacy/security exposure, operator approval, backup, rollback, and stop conditions. |
| `dependency_design` | Deep coverage for dependency failure, version/API drift, fallback or explicit failure behavior, observability, and verification without live production dependency mutation. |

When multiple design levels apply, use the deepest required treatment for each attack dimension.

Suggested template:

```markdown
## Risk / Attack Gate

| Attack Dimension | Depth | Risk / Failure Mode | Mitigation / Design Response | Verification or SPEC/PLAN Input | Status |
|---|---|---|---|---|---|
```

## Verification Strategy / Test Architecture

Purpose: define the test and verification architecture required by the selected design.

This section is required for every DESIGN. For low-risk work it may be short, but it must still state why targeted verification is sufficient.

DESIGN may require test types such as:

```text
unit tests
integration tests
contract tests
migration tests
golden/equivalence tests
regression tests
compatibility tests
safety tests
manual acceptance checks
```

DESIGN must not write TDD execution steps. It should state what verification layers are required and why; PLAN later turns SPEC contracts into concrete red -> green -> refactor steps.

## Spec & Plan Handoff

DESIGN must produce downstream inputs:

Spec Inputs use the shared schema from `workflow-invariants.md#downstream-input-schema-rule`:

```markdown
| Spec Input ID | Source Artifact | Source Item ID | Item | Required SPEC Contract | Reason | Status |
|---|---|---|---|---|---|---|
```

Plan Inputs use the shared schema from `workflow-invariants.md#downstream-input-schema-rule`:

```markdown
| Plan Input ID | Source Artifact | Source Item ID | Item | Required PLAN Constraint | Covers | Status |
|---|---|---|---|---|---|---|
```

DESIGN must not write the final SPEC or PLAN.

## Design Quality Gate

Purpose: decide whether DESIGN can hand off to SPEC.

Pass conditions:

- No design/approach blocker remains.
- All Risk Discovery design blockers are resolved.
- Subagent Conflict Gate is complete when subagents were used.
- One design direction is selected.
- User Decision Gate is complete when user-owned decisions exist.
- Change Point Inventory is complete.
- Requirement Trace Check is complete.
- Boundary Coverage / Integration Boundary Check is complete where required.
- Boundary Coverage rows have stable `DES-BND-*` IDs and Integration Boundary rows have stable `DES-INT-*` IDs where required.
- Verification Strategy / Test Architecture is explicit.
- Migration, compatibility, rollback, dependency, safety, and execution boundaries are clear where relevant.
- Risks have mitigation directions.
- P0/P1 risks have selected mitigation, explicit user acceptance, or upstream routing.
- Spec Inputs use the shared downstream input schema and have stable IDs.
- Plan Inputs use the shared downstream input schema and have stable IDs.
- Requirement scope was not changed.
- No unconfirmed requirement was converted into a design fact.

Fail result:

```text
blocked_in_design
```

Quality Gate failure routing:

| Failed check | Return to | Required action |
|---|---|---|
| Risk Discovery design blocker unresolved | Option Analysis / Decision / User Decision Gate | Resolve the design blocker or record the user-owned decision. |
| Subagent conflicts unresolved | Subagent Conflict Gate | Preserve conflict, resolve with evidence, or route to User Decision Gate. |
| No single design direction selected | Option Analysis / Decision | Compare viable options and select one approach. |
| User-owned decision unresolved | User Decision Gate | Capture user choice, rejected options, reason, and impact. |
| Change Point Inventory incomplete | Change Point Inventory | Add missing add/modify/replace/remove/preserve/no-op entries. |
| Requirement Trace Check incomplete | Requirement Trace Check | Map every scope, acceptance, and Risk Discovery input to design handling. |
| Boundary or Integration Boundary incomplete | Boundary Coverage / Integration Boundary Check | Complete responsibility, I/O, data/state, errors, compatibility, migration, rollback, Spec Inputs, and Plan Inputs. |
| Boundary or Integration Boundary lacks stable ID | Boundary Coverage / Integration Boundary Check | Add `DES-BND-*` or `DES-INT-*` IDs before SPEC/PLAN handoff. |
| Risk / Attack Gate invalidates the design | Option Analysis | Revise or replace the selected approach. |
| P0/P1 risks lack mitigation, acceptance, or routing | Risk / Attack Gate / User Decision Gate | Resolve, explicitly accept, or route before DESIGN handoff. |
| Verification Strategy / Test Architecture missing | Verification Strategy / Test Architecture | Define required verification layers and rationale. |
| Spec Inputs or Plan Inputs missing or lack stable IDs | Spec & Plan Handoff | Produce downstream handoff inputs with the shared schema without writing SPEC or PLAN. |
| Requirement scope changed during DESIGN | Requirement Brief | Return to Requirement Brief because DESIGN must not redefine requirements. |
| Unconfirmed requirement treated as design fact | Requirement Brief / Requirement Trace Check | Confirm the requirement or remove the unsupported design fact. |

## DESIGN Checkpoint

Purpose: freeze DESIGN as the authorized design input for SPEC.

DESIGN Checkpoint can run only after Design Quality Gate is `ready`. If checkpoint review finds a design/approach blocker, return to the relevant DESIGN step, update DESIGN, and pass Design Quality Gate again before another checkpoint.

The checkpoint has two layers:

```text
Subagent Checkpoint Review
Main/User DESIGN Checkpoint
```

Subagent review may be skipped only for small, low-risk DESIGNs where the main agent can reasonably verify coverage directly. It is required for migration, rewrite, replacement, integration, cross-project, safety-sensitive, dependency-heavy, or broad boundary work.

Subagent review checks:

- DESIGN has one selected approach.
- No design blocker remains.
- User Decision Gate is complete where needed.
- Subagent Conflict Gate is complete where needed.
- Change Point Inventory is complete.
- Requirement Trace Check is complete.
- Boundary Coverage / Integration Boundary Check is complete where required.
- Integration Boundaries are complete where required.
- Boundary and Integration Boundary rows have stable IDs where required.
- Risk / Attack Gate issues are resolved or explicitly handled.
- P0/P1 risks are mitigated, explicitly accepted, or routed.
- Spec Inputs and Plan Inputs use the shared schema and stable IDs.

Subagent review output extends the shared checkpoint-review template in `workflow-invariants.md#shared-templates`:

```markdown
# DESIGN Checkpoint Review

## Status
pass | issues_found | blocked

## Decision Findings
Approach selection, rejected options, or rationale issues.

## Coverage Findings
Missing change points, trace mappings, boundaries, or integration points.

## Risk Findings
Unresolved risk, rollback, compatibility, dependency, or safety issues.

## Handoff Findings
Missing or unclear Spec Inputs / Plan Inputs.

## Recommendation
approve | request_changes | block
```

Main/User checkpoint output extends the shared checkpoint template in `workflow-invariants.md#shared-templates`:

```markdown
# DESIGN Checkpoint

## Status
approved | changes_requested | blocked

## Review Sources
Subagent checkpoint reviews and other review sources used.

## Required Changes
DESIGN items that must be changed before SPEC handoff.

## User Confirmations
User-confirmed design choices, tradeoffs, compatibility, rollback, dependency, or safety decisions.

## SPEC Authorization
yes | no
```

DESIGN Checkpoint must be `approved` before SPEC can proceed.

## DESIGN Template

```markdown
# DESIGN: <title>

## Upstream References
| Artifact | Reference | Status |
|---|---|---|
| Raw Requirement |  | available |
| Requirement Brief |  | approved |
| Risk & Question Discovery |  | approved |

## Design Level
light_design | standard_design | architecture_design | migration_design | safety_design | dependency_design

## Inputs
Requirement Brief and Risk Discovery inputs summarized here.

## Problem
The technical problem this design solves.

## Goals
Design goals derived from confirmed requirements.

## Non-goals
What this design will not solve.

## Context
Current system facts and constraints.

## Options
Viable options, including recommended, minimal, and rejected options.

## Decision
The selected approach.

## User Decision Gate
User-owned design decisions and confirmations, if any.

## Rationale
Why this option was selected.

## Rejected Options
Options not selected and why.

## Impact
Affected modules, interfaces, data, configuration, dependencies, tests, and workflows.

## Change Point Inventory
All design-level change points and their change type.

## Requirement Trace Check
Mapping from requirement scope and acceptance to design handling.

## Boundary Coverage / Integration Boundary Check
All design/change/integration boundaries and their handling.

## Integration Boundaries
Required for integration, replacement, or cross-project work.

## Migration / Compatibility
Migration and compatibility strategy, or `None` with reason.

## Failure / Rollback
Failure modes and rollback or recovery strategy.

## Dependency / Safety
External dependency, permission, data safety, privacy, and execution safety considerations.

## Risk / Attack Gate
Challenge results for dependency failure, scale, rollback cost, data safety, compatibility, and execution safety.

## Verification Strategy / Test Architecture
Test and verification architecture required by this design.

## Resolved Blockers
Design blockers eliminated in this stage.

## Remaining Assumptions
Only explicit non-blocking assumptions.

## Spec Inputs
Behavior contracts and semantics that SPEC must cover, using the shared Spec Input schema.

## Plan Inputs
Execution, sequencing, verification, rollback, or safety constraints that PLAN must cover, using the shared Plan Input schema.

## Design Quality Gate
ready | blocked

## DESIGN Checkpoint
approved | changes_requested | blocked
```

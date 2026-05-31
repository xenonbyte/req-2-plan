# PLAN Workflow

## Purpose

This document records the agreed workflow for the PLAN stage. PLAN converts an approved SPEC into executor-neutral, verification-driven implementation steps.

The PLAN artifact is a step-by-step checkable plan: each per-task step is expressed as a `- [ ]` checkbox so executors can tick off progress top-to-bottom during execution.

PLAN is clean and executor-neutral in this workflow. It does not discuss, choose, or format for GSD, Superpowers, or any other executor.

Executor-specific adaptation, orchestration, and management are out of scope for this requirement-to-PLAN workflow. They belong to a later, larger execution workflow.

PLAN does not redefine requirements, change DESIGN, change SPEC contracts, or guess missing upstream decisions.

## Position

Canonical node order is defined in `workflow-invariants.md#canonical-chain`. This document covers the PLAN segment:

```text
SPEC Checkpoint
  -> PLAN
  -> PLAN Quality Gate
  -> PLAN Checkpoint
```

## Responsibilities

PLAN answers:

- How approved SPEC contracts are implemented as tasks.
- How each task is verified.
- How DESIGN Verification Strategy / Test Architecture becomes concrete verification work.
- How SPEC contracts become TDD-oriented execution steps where appropriate.
- In what order tasks should run.
- Which dependencies exist between tasks.
- How risky changes are sequenced.
- How rollback and safety requirements are handled during execution.

PLAN must not:

- Redefine the requirement.
- Change DESIGN decisions.
- Change SPEC contracts.
- Add behavior not present in SPEC.
- Guess missing scope, missing design, or missing contract details.
- Choose or format for a specific executor.

If PLAN detects a blocker-like issue, it must mark `upstream_gap_detected` and route back to the responsible upstream stage.

No orphan PLAN tasks are allowed. Every PLAN task must reference at least one SPEC item.

## Inputs

Required upstream references:

```text
Raw Requirement
Requirement Brief
Risk & Question Discovery
DESIGN
SPEC
```

Required entry status:

```text
SPEC Checkpoint = approved
```

Required SPEC inputs:

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
Plan Inputs
Traceability
```

Required DESIGN inputs:

```text
Change Point Inventory
Boundary Coverage / Integration Boundary Check
Integration Boundaries, when present
Verification Strategy / Test Architecture
Plan Inputs
Rollback / Safety constraints
```

## Flow

```text
Plan Entry Gate
  -> Contract-to-Task Mapping
  -> Risk Discovery Plan Input Traceability
  -> TDD Decomposition
  -> Execution Sequencing
  -> Verification Plan
  -> Rollback / Safety Plan
  -> Stop / Escalation Conditions
  -> PLAN Quality Gate
  -> Subagent Checkpoint Review
  -> Main/User PLAN Checkpoint
```

## Gate 1: Plan Entry Gate

Purpose: confirm PLAN can start.

Pass conditions:

- SPEC Checkpoint is `approved`.
- Upstream references are present and accessible.
- SPEC contracts are traceable.
- PLAN Inputs are explicit.
- DESIGN Verification Strategy / Test Architecture is available.

Fail result:

```text
upstream_gap_detected
```

PLAN must not guess missing SPEC or DESIGN information.

## Contract-to-Task Mapping

Purpose: ensure every approved SPEC contract has implementation coverage.

Every SPEC contract must map to at least one of:

```text
implementation task
verification task
rollback/safety task
explicit no-op/preserve task
```

Use `workflow-invariants.md#shared-concept-definitions` for the difference between `preserve` and `no-op`.

The reverse must also hold: every PLAN task must map back to at least one SPEC contract, acceptance scenario, edge case, verification requirement, or Plan Input.

Use `workflow-invariants.md#coverage-closure-rule` to close every imported SPEC contract and `SPEC-PLAN-*` item. Short tables are allowed for light or standard work, but each imported ID must have a closure status.

Suggested template:

```markdown
## Contract-to-Task Mapping

| SPEC Contract | Source | Task / Check | Coverage Type | Closure Status | Resolution / Route |
|---|---|---|---|---|---|
```

Use stable SPEC IDs so task-level references are easy to follow:

```text
SPEC-FR-*       Functional requirement
SPEC-IF-*       Interface contract
SPEC-DATA-*     Data / State contract
SPEC-ERR-*      Error behavior
SPEC-SAFE-*     Permission / Safety contract
SPEC-COMPAT-*   Compatibility contract
SPEC-OBS-*      Observability requirement
SPEC-ACC-*      Acceptance Scenario
SPEC-EDGE-*     Edge Case
SPEC-PLAN-*     Plan Input
```

Every task must include:

```markdown
**Spec References:**
- SPEC-FR-002: <title>
- SPEC-EDGE-001: <title>
```

## Risk Discovery Plan Input Traceability

Purpose: ensure Risk Discovery Plan Inputs were not lost while passing through DESIGN and SPEC.

PLAN uses SPEC as the primary task reference, but it must also verify this chain:

```text
Risk Discovery Plan Input -> DESIGN Plan Input -> SPEC-PLAN-* -> PLAN task/check/rollback/safety item
```

Suggested template:

```markdown
## Risk Discovery Plan Input Traceability

| Risk Discovery Plan Input | DESIGN Plan Input | SPEC-PLAN ID | PLAN Coverage | Closure Status | Resolution / Route |
|---|---|---|---|---|---|
```

## PLAN Task Schema

Purpose: define machine-parseable structure for PLAN tasks to enable automated validation, traceability, and executor adaptation.

Each PLAN task must follow this schema structure:

````markdown
### PLAN-TASK-001: <title>

Spec References: SPEC-...

Change Type: add | modify | remove

TDD Applicable: yes | no

Files: <Create/Modify + path list>

Skeleton:
  ```<lang>
  <interface signature or failing-test skeleton>
  ```

Steps:
- [ ] red: ...
- [ ] green: ...

Verification: ...
````

Machine-parsing rules:

- Task headings match regex `^### PLAN-TASK-\d+` (followed by colon, space, and title text).
- `Change Type` is one of: `add`, `modify`, `remove`, `preserve`, or `no-op`.
- `TDD Applicable` is `yes` or `no` (case-insensitive).
- When `TDD Applicable: yes`, the task MUST include at least one fenced code block under `Skeleton` section.
- Steps use checkbox format `- [ ]` (unchecked) or `- [x]` (checked).
- `Skeleton` fenced code blocks begin with triple backticks and a language specifier (e.g., `python`, `typescript`, `bash`).
- The outer fence (shown above) uses four backticks to allow inner triple-backtick code blocks to render correctly in markdown.

Human readers see the schema as part of the document structure. Automation scans for PLAN-TASK-NN headings, extracts metadata and code skeletons, and validates coverage against SPEC contracts and traceability tables.

## TDD Decomposition

Purpose: turn testable SPEC contracts into test-first execution steps where appropriate.

TDD is required for tasks where the referenced SPEC behavior can be verified before implementation. If TDD is not used, PLAN must state why TDD does not fit and what alternative verification replaces it.

Default TDD shape (expressed as checkboxes — tick each step during execution):

```text
- [ ] red: Write failing test and confirm it fails.
- [ ] green: Implement minimal change and confirm test passes.
- [ ] refactor: Refactor if needed; confirm tests still pass.
```

Not every task fits TDD. Documentation-only work, mechanical configuration, generated artifacts, or one-time migration operations may use alternative verification, but PLAN must state the reason and the verification method.

Suggested template:

```markdown
## TDD Decomposition

| Task | SPEC Contract | TDD Applicable | Steps | Alternative Verification |
|---|---|---|---|---|
```

## Execution Sequencing

Purpose: order tasks so implementation can proceed safely.

Sequencing should account for:

- Dependencies between tasks.
- Risky change isolation.
- Migration or compatibility order.
- Test availability.
- Rollback checkpoints.
- Keeping the system runnable between steps when possible.

Suggested template:

```markdown
## Execution Sequencing

| Order | Task | Depends On | Why This Order | Safe Checkpoint |
|---|---|---|---|---|
```

## Task Format

Each PLAN task must be traceable, testable, and executor-neutral.

Executor-neutral means the task describes the required implementation increment, SPEC references, verification, rollback/safety handling, and stop conditions without selecting a specific agent runtime, prompt format, orchestration framework, or executor-specific command language.

Task granularity rule:

- Each task should be an independently executable and independently verifiable increment.
- Each task should fit within one working context.
- Each task should avoid spanning unrelated modules or unrelated SPEC areas.
- Each task should have clear stop conditions.
- Large tasks must be split until their verification and rollback/safety handling are clear.

Task template:

Each task is self-contained: it carries its own spec references, behavior goal, checkable steps, verification commands, and rollback/safety anchor so an executor can read one task top-to-bottom without cross-referencing other sections.

```markdown
### Task N: <task title>

**Spec References:**
- SPEC-<TYPE>-<ID>: <title>

**Goal**
What this task accomplishes.

**Change Type**
add | modify | replace | remove | preserve | no-op

**Steps**
- [ ] <executor-neutral step>
- [ ] <executor-neutral step>

**Verification**
Checks, commands, or methods that verify the task. Reference the SPEC contract or acceptance scenario confirmed by each check.

**Rollback / Safety**
Task-specific rollback, safety notes, or stop conditions.
```

Positive executor-neutral handling:

```markdown
### Task N: Preserve legacy import compatibility

**Spec References:**
- SPEC-COMPAT-003: Legacy import files remain accepted.

**Goal**
Keep the existing import behavior compatible while adding the new parser boundary.

**Change Type**
preserve

**Steps**
- [ ] Add or update compatibility coverage for the legacy import case.
- [ ] Make the minimal implementation change needed for the new boundary.
- [ ] Run the compatibility and regression checks named in the Verification Plan.

**Verification**
The compatibility check proves SPEC-COMPAT-003 still passes. Run the named regression suite and confirm no regressions against SPEC-COMPAT-003.

**Rollback / Safety**
Stop if the implementation requires changing the legacy file format without a new SPEC compatibility decision.
```

Anti-examples:

```text
Do not write "Have Superpowers implement the migration plan."
Do not write "Use GSD to inspect the codebase and decide the task split."
Do not write "Let the executor choose whether compatibility tests are needed."
```

These anti-examples are not executor-neutral because they depend on a specific executor or delegate upstream decisions and verification choices to execution time.

Example task mapping for `forma` replacing `pencil` design capability with `opendesign`:

```markdown
### Task 3: Add compatibility-preserving document open path

**Spec References:**
- SPEC-FR-001: Existing supported design documents open with the expected visible canvas state.
- SPEC-COMPAT-001: Supported pencil-backed documents remain openable or fail with documented non-mutating errors.
- SPEC-ERR-001: Unsupported opendesign parse cases do not overwrite the source document.

**Goal**
Introduce the document-open boundary needed by the approved DESIGN while preserving existing document safety behavior.

**Change Type**
modify

**Steps**
- [ ] red: Add failing compatibility/golden test for opening a supported existing design document (covers SPEC-FR-001, SPEC-COMPAT-001).
- [ ] red: Add failing error-path test for unsupported parse behavior (covers SPEC-ERR-001).
- [ ] green: Implement the minimal document-open integration path until both tests pass.
- [ ] verify: Run targeted compatibility, error-path, and regression checks.

**Verification**
Targeted tests prove SPEC-FR-001, SPEC-COMPAT-001, and SPEC-ERR-001. All three tests must pass; no existing regression may fail.

**Rollback / Safety**
Stop if the implementation requires mutating existing documents before read-only compatibility tests pass.
```

Anti-example:

```text
Do not create a PLAN task named "integrate opendesign" with no SPEC references, no independently verifiable result, and no stop condition.
```

## Verification Plan

Purpose: turn DESIGN Verification Strategy and SPEC contracts into concrete verification commands or checks.

Verification may include:

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
format/lint/typecheck/build
```

Suggested template:

```markdown
## Verification Plan

| Check | Purpose | Command / Method | Expected Result | Covers |
|---|---|---|---|---|
```

## Rollback / Safety Plan

Purpose: make execution reversible or failure-aware.

PLAN must state:

- What can be reverted by code rollback.
- What requires data/config rollback.
- What must be backed up before execution.
- What must be verified before and after risky steps.
- What operations are destructive or safety-sensitive.
- What stop conditions apply.

Suggested template:

```markdown
## Rollback / Safety Plan

| Risky Area | Safety Constraint | Rollback Method | Stop Condition | Verification |
|---|---|---|---|---|
```

## Stop / Escalation Conditions

Purpose: define when execution must stop instead of guessing or continuing unsafely.

PLAN must state stop or escalation conditions for the overall plan and for risky tasks.

Stop conditions include:

- Verification fails unexpectedly.
- A task discovers `upstream_gap_detected`.
- A task requires a destructive operation not already approved.
- A task touches an out-of-scope module, capability, data source, or workflow.
- A task cannot satisfy its referenced SPEC item.
- A task needs a new behavior, compatibility rule, or design decision not present in SPEC/DESIGN.
- A task would require skipping or weakening required verification.

Suggested template:

```markdown
## Stop / Escalation Conditions

| Condition | Stop / Escalate | Responsible Stage | Required Action |
|---|---|---|---|
```

### Tier-Aware Sub-steps

PLAN sub-steps (Contract-to-Task Mapping, Risk Discovery Plan Input Traceability, TDD Decomposition, Execution Sequencing, Verification Plan, Rollback / Safety Plan, Stop / Escalation Conditions) are required or optional per tier. Optional sub-steps must either be present or marked `N/A: <reason>` consistent with the locked tier. See [Workflow Complexity Tier Rule](workflow-invariants.md#workflow-complexity-tier-rule) for the full per-tier table.

## PLAN Quality Gate

Purpose: decide whether PLAN is internally complete enough to enter checkpoint review.

Pass conditions:

- Upstream references are present and accessible.
- SPEC Checkpoint is approved.
- Every SPEC contract maps to a task, check, rollback/safety item, or explicit no-op/preserve item.
- Every imported SPEC contract and `SPEC-PLAN-*` item has closure status under `workflow-invariants.md#coverage-closure-rule`.
- Every PLAN task has at least one SPEC reference.
- No orphan PLAN tasks exist.
- TDD decomposition is present for every task where TDD applies.
- Alternative verification is justified where TDD is not applicable.
- Task granularity is independently executable and verifiable.
- Execution sequencing is explicit.
- Verification Plan covers SPEC contracts and DESIGN Verification Strategy / Test Architecture.
- Rollback / Safety Plan covers risky changes.
- Stop / Escalation Conditions are explicit.
- Risk Discovery Plan Inputs are traceable through DESIGN, SPEC, and PLAN coverage.
- No upstream gap is being guessed into PLAN.
- Optional sub-steps are either present or marked `N/A: <reason>` consistent with the locked tier per [Workflow Complexity Tier Rule](workflow-invariants.md#workflow-complexity-tier-rule).

Fail result:

```text
return_to_plan_step | upstream_gap_detected
```

`return_to_plan_step` means the PLAN artifact itself is incomplete and must return to the PLAN step that owns the missing task, sequence, verification, rollback, safety, stop, or traceability work. `upstream_gap_detected` means PLAN found missing requirement, design, or SPEC information and must route upstream instead of guessing.

Quality Gate failure routing:

| Failed check | Return to | Required action |
|---|---|---|
| Upstream reference or SPEC Checkpoint missing | Plan Entry Gate | Restore required upstream references or wait for SPEC approval. |
| SPEC contract lacks task/check/rollback/no-op coverage | Contract-to-Task Mapping | Add coverage or mark explicit no-op/preserve. |
| Imported SPEC ID or `SPEC-PLAN-*` item has no closure status | Contract-to-Task Mapping / Risk Discovery Plan Input Traceability | Add `covered`, `preserve`, `no-op`, `return_to_plan_step`, or `upstream_gap_detected` and route unresolved items before checkpoint review. |
| PLAN task lacks SPEC reference | Task Breakdown / Contract-to-Task Mapping | Add SPEC reference or remove orphan task. |
| TDD applicability missing or unjustified | TDD Decomposition | Add red/green/refactor steps or justified alternative verification. |
| Task granularity too broad | Task Breakdown / Task Granularity | Split into independently executable and verifiable increments. |
| Execution order unclear | Execution Sequencing | Add dependencies, order rationale, and safe checkpoints. |
| Verification Plan incomplete | Verification Plan | Add checks covering SPEC contracts and DESIGN verification strategy. |
| Rollback or safety handling incomplete | Rollback / Safety Plan | Add rollback method, safety constraint, stop condition, and verification. |
| Stop / Escalation Conditions missing | Stop / Escalation Conditions | Add stop/escalation condition, responsible stage, and required action. |
| Risk Discovery Plan Input trace is missing | Risk Discovery Plan Input Traceability | Link Risk Discovery Plan Input to DESIGN Plan Input, SPEC-PLAN ID, and PLAN coverage. |
| Missing SPEC/DESIGN/Requirement input | Responsible upstream stage | Mark `upstream_gap_detected` and route to the owner stage. |

## Subagent Use

PLAN may use subagents for decomposition and review. Subagents do not change Requirement Brief, DESIGN, or SPEC.

This section follows the shared Subagent Use structure in `workflow-invariants.md#shared-subagent-use-structure`. The rules below define PLAN-specific decomposition and review behavior.

Subagents follow `workflow-invariants.md#subagent-model-rule`.

Use subagents when:

- PLAN spans five or more tasks.
- PLAN covers multiple modules, repositories, services, commands, workflows, or data stores.
- Migration, rollback, destructive operation, safety, compatibility, or execution ordering risk is present.
- Risk Discovery Plan Inputs require independent traceability review through DESIGN and SPEC.
- TDD applicability or alternative verification is non-obvious for several tasks.
- Verification coverage must be checked across multiple test layers or manual acceptance paths.
- Task sequencing has dependencies, safe checkpoints, or stop conditions that could be missed by a single-pass review.

Allowed subagent tasks:

- Task decomposition review.
- Contract-to-task coverage review.
- TDD applicability review.
- Execution order review.
- Verification coverage review.
- Rollback and safety review.

Forbidden subagent tasks:

- Changing requirement scope.
- Changing DESIGN decisions.
- Changing SPEC contracts.
- Choosing executor-specific format.
- Skipping required verification.
- Treating upstream gaps as PLAN decisions.

## Subagent Checkpoint Review

Purpose: independently review PLAN before main/user approval.

Subagent Checkpoint Review can run only after PLAN Quality Gate is `ready`. If checkpoint review finds an upstream gap, PLAN approval is not allowed; route back to the responsible upstream stage and rerun PLAN Quality Gate before another checkpoint.

Subagent review checks:

- Every SPEC contract maps to task, check, rollback/safety item, or explicit no-op/preserve.
- Every PLAN task has Spec References.
- No orphan PLAN tasks exist.
- Risk Discovery Plan Inputs are traceable through DESIGN Plan Inputs, SPEC-PLAN IDs, and PLAN coverage.
- TDD decomposition is present for every task where TDD applies.
- Alternative verification is justified where TDD is not applicable.
- Task granularity is small enough for independent execution and verification.
- Stop / Escalation Conditions are explicit.
- Execution order respects dependencies and risk.
- Verification Plan covers SPEC and DESIGN Verification Strategy / Test Architecture.
- Rollback / Safety Plan covers risky changes.
- No upstream gap is being guessed into a PLAN task.

Subagent review output extends the shared checkpoint-review template in `workflow-invariants.md#shared-templates`:

```markdown
# PLAN Checkpoint Review

## Status
pass | issues_found | upstream_gap_detected

## Coverage Findings
SPEC contracts or DESIGN plan inputs missing from PLAN.

## Sequencing Findings
Task dependency or ordering issues.

## Verification Findings
Missing or weak verification.

## Rollback / Safety Findings
Missing rollback, safety, stop condition, or risky-step handling.

## Recommendation
approve | request_changes | route_upstream
```

## Main/User PLAN Checkpoint

Purpose: approve PLAN as the canonical implementation plan.

This workflow stops at an executor-neutral PLAN. Executor-specific adaptation, orchestration, and management are intentionally out of scope here.

Pass conditions:

- PLAN Quality Gate is `ready`.
- Subagent checkpoint reviews are merged when used.
- Required changes are resolved.
- Every SPEC contract has execution and verification coverage.
- Every PLAN task has at least one SPEC reference.
- No orphan PLAN tasks exist.
- TDD is used for every task where it applies.
- Alternative verification is justified where TDD is not applicable.
- Task granularity is independently executable and verifiable.
- Stop / Escalation Conditions are explicit.
- Rollback and safety constraints are explicit.
- No upstream gap remains.
- PLAN is approved as the canonical implementation plan.

Checkpoint output extends the shared checkpoint template in `workflow-invariants.md#shared-templates`:

```markdown
# PLAN Checkpoint

## Status
approved | changes_requested | upstream_gap_detected

## Review Sources
Subagent checkpoint reviews and other review sources used.

## Required Changes
PLAN items that must be changed before the canonical PLAN can be approved.

## User Confirmations
User-confirmed sequencing, risk, rollback, or verification choices.

## Executor-Neutral Authorization
yes | no
```

## Post-Checkpoint Handoff

After Main/User PLAN Checkpoint is `approved`, the requirement-to-PLAN workflow is complete. The approved PLAN is executor-neutral — it does not choose or format for any specific execution tool or runtime.

Handoff rules:

1. Keep the approved PLAN executor-neutral. Do not add executor-specific commands, model choices, subagent prompts, commit behavior, or tool-specific orchestration to the PLAN artifact.
2. If execution discovers missing or contradictory requirement, risk, DESIGN, SPEC, or PLAN input while the source run is still write-capable, stop execution and route through `upstream_gap_detected` / `route_upstream`.
3. Executor behavior must obey repository-local instructions and user approvals, including git, commit, branch, test, destructive-action, and external-state rules.

This handoff is a boundary. It does not change PLAN approval, downstream authorization, artifact traceability, or upstream gap routing.

## PLAN Template

```markdown
# PLAN: <title>

## Upstream References
| Artifact | Reference | Status |
|---|---|---|
| Raw Requirement |  | available |
| Requirement Brief |  | approved |
| Risk & Question Discovery |  | approved |
| DESIGN |  | approved |
| SPEC |  | approved |

## Goal
Implementation goal derived from SPEC.

## Preconditions
Required local state, dependencies, data backups, config, or safety checks before execution.

## Contract-to-Task Mapping
Mapping from SPEC contracts to tasks, checks, rollback/safety items, or no-op/preserve items. Every imported SPEC ID must have closure status.

## Risk Discovery Plan Input Traceability
Mapping from Risk Discovery Plan Inputs through DESIGN Plan Inputs and SPEC-PLAN IDs to PLAN coverage. Every carried plan input must have closure status.

## Task Breakdown
Executor-neutral implementation tasks. Every task must include `Spec References`.

## Task Granularity
Rules and notes for task size, independence, and verification boundaries.

## TDD Decomposition
Test-first steps or justified alternative verification.

## Execution Sequencing
Task order, dependencies, and safe checkpoints.

## Verification Plan
Commands, checks, methods, and expected outcomes.

## Rollback / Safety Plan
Rollback method, safety constraints, stop conditions, and risky areas.

## Stop / Escalation Conditions
Conditions that require stopping, escalation, or upstream routing.

## Traceability
Mapping from Requirement Brief, DESIGN, SPEC, and PLAN tasks.

## PLAN Quality Gate
ready | return_to_plan_step | upstream_gap_detected

## PLAN Checkpoint
approved | changes_requested | upstream_gap_detected
```

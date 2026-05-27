# Requirement to Plan Workflow Invariants

## Purpose

This document records cross-node rules for the requirement-to-plan workflow. Node-specific details live in their own workflow documents.

## Quick Start

For a first pass, read `README.md` first, then use this document as the shared rulebook. Use the stage workflow documents only when you are producing or reviewing that stage's artifact.

## Canonical Chain

```text
Raw Requirement
  -> Intake Brief v0
  -> Requirement Discovery Loop
  -> Requirement Brief v1
  -> Requirement Brief Quality Gate
  -> Requirement Brief Checkpoint
  -> Risk & Question Discovery
  -> Risk Discovery Quality Gate
  -> Risk Discovery Checkpoint
  -> Design Entry Gate [DESIGN-owned input-validation gate]
  -> Design Scope Gate [DESIGN-owned depth-selection gate]
  -> DESIGN
  -> DESIGN Quality Gate
  -> DESIGN Checkpoint
  -> SPEC
  -> SPEC Quality Gate
  -> SPEC Checkpoint
  -> PLAN
  -> PLAN Quality Gate
  -> PLAN Checkpoint
```

Stage-specific workflow documents should reference this canonical chain and mark their focused node. They should not maintain a different shortened chain unless the difference is explicitly explained.

`Design Entry Gate` and `Design Scope Gate` are shown before `DESIGN` because both must run before design discovery. They are DESIGN-owned gates maintained in `design-workflow.md`.

## Stage Responsibility Boundary

`Requirement Brief` and `DESIGN` have separate responsibilities.

```text
Requirement Brief: define what is needed, why, for whom, with what scope, non-scope, constraints, acceptance, source provenance, and module/capability coverage.
DESIGN: decide how the requirement should be solved, including approach, architecture, migration, rollback, compatibility, dependencies, and execution safety.
```

Do not let `Requirement Brief` become DESIGN.

Do not let DESIGN redefine the requirement.

Requirement Brief may identify relevant modules, capabilities, workflows, repositories, and integration surfaces. It must not decide how to change them.

Requirement Brief may use subagents for parallel fact gathering and scope inventory. Subagents produce evidence, not decisions.

Risk & Question Discovery may use subagents for parallel risk, assumption, blocker, discussion, and downstream-input discovery across scan dimensions. Subagents produce findings and evidence, not routing approval, design decisions, SPEC contracts, or PLAN tasks.

DESIGN may use subagents for scheme research, impact analysis, and blast-radius discovery. Subagents produce evidence and analysis, not the final design decision.

SPEC may use subagents for contract extraction, coverage checking, boundary checking, and test scenario discovery. Subagents produce findings and verification ideas, not new requirements, new design decisions, or PLAN tasks.

SPEC checkpoint review may be performed by subagents, but checkpoint approval and PLAN authorization belong to the main agent and user.

PLAN may use subagents for task decomposition review, contract-to-task coverage review, TDD applicability review, execution order review, verification coverage review, and rollback/safety review. Subagents do not change Requirement Brief, DESIGN, or SPEC.

All subagents follow the shared Subagent Model Rule in this document.

## Subagent Model Rule

Subagents inherit the main agent's model class or capability level. Workflow documents must not hard-code a specific model name, because available models and agent runtimes vary by environment.

Operational rules:

- Request the same model/capability tier as the main agent when the runtime allows explicit selection.
- If the runtime only supports implicit inheritance or default model selection, use that runtime behavior and record the limitation in the subagent output when it affects confidence.
- Do not silently downgrade judgment-heavy work such as design tradeoff analysis, impact analysis, checkpoint review, or safety review.
- If a lower-capability model is forced by runtime availability, the subagent may still gather evidence, but the main agent must treat its conclusions as review inputs rather than decisions.
- Mechanical scans may use the inherited/default runtime model when they only produce evidence and traceable findings.

## Shared Subagent Use Structure

Stage-specific workflow documents should not redefine the common subagent framework. They should reference this structure and list only stage-specific triggers, allowed tasks, forbidden tasks, outputs, and merge rules.

Every stage-specific subagent section should cover:

- Purpose: what the subagent helps discover or review.
- When to use: risk, scope, size, or parallelism triggers.
- Allowed tasks: evidence-producing work inside the stage boundary.
- Forbidden tasks: decisions, approvals, or downstream artifacts the subagent must not create.
- Output shape: use or extend the shared subagent finding/checkpoint templates.
- Merge rule: the main agent merges findings, preserves conflicts, and owns downstream decisions.
- Approval boundary: subagents can recommend, but main/user checkpoints approve.

## Shared Subagent Merge Rule

The main agent must merge subagent output before using it in a stage artifact or checkpoint.

Use this merge order:

```text
1. Normalize finding IDs, source references, inspected scope, and confidence.
2. Deduplicate exact or evidence-equivalent findings.
3. Separate complementary findings from direct conflicts.
4. Resolve evidence-level conflicts only when one side is stale, out of scope, unsupported, or contradicted by stronger direct evidence.
5. Preserve unresolved direct conflicts in the stage artifact.
6. Route conflicts to the owning gate when they affect scope, acceptance, design choice, contracts, sequencing, safety, rollback, compatibility, or cost.
```

Decision tree:

```text
Same evidence and same conclusion -> merge as duplicate.
Different evidence but compatible conclusions -> merge as complementary coverage.
One conclusion lacks evidence -> keep the evidenced finding and record the unsupported claim as rejected or unknown.
Both conclusions have evidence and affect a decision -> preserve conflict and route to the stage conflict gate or checkpoint.
Conflict requires product, cost, compatibility, risk, or preference judgment -> route to User Decision Gate or Main/User Checkpoint.
Conflict exposes missing upstream input -> mark `upstream_gap_detected` or `route_upstream` according to the current stage.
```

The main agent may resolve mechanical evidence conflicts, but must not silently resolve decision-bearing conflicts by preference.

## Shared Templates

Stage documents may add fields, but they should extend these shared templates instead of redefining incompatible structures.

Upstream references:

```markdown
## Upstream References
| Artifact | Reference | Status |
|---|---|---|
```

Subagent finding:

```markdown
# <Stage> Subagent Finding: <topic>

## Scope
What this subagent inspected or analyzed.

## Sources
Paths, repositories, documents, upstream sections, commands, tools, or evidence sources used.

## Findings
Evidence-backed facts, observations, or review findings.

## Unknowns
Information still unconfirmed.

## Evidence
Traceable references supporting the findings.
```

Subagent checkpoint review:

```markdown
# <Stage> Checkpoint Review

## Status
pass | issues_found | blocked | upstream_gap_detected | route_upstream

## Findings
Coverage, ambiguity, routing, risk, verification, or handoff issues found by the review.

## Recommendation
approve | request_changes | block | route_upstream
```

Main/User checkpoint:

```markdown
# <Stage> Checkpoint

## Status
approved | changes_requested | blocked | upstream_gap_detected | route_upstream

## Review Sources
Subagent checkpoint reviews and other review sources used.

## Required Changes
Items that must be changed before downstream authorization.

## User Confirmations
User-owned confirmations recorded at this checkpoint.

## Downstream Authorization
yes | no
```

## Artifact Lifecycle Rule

Artifacts are stored under a workflow artifact root unless a repository-local convention overrides it.

Default root:

```text
docs/artifacts/<work-id>/
```

Default file shape:

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

Rules:

- Use Markdown for workflow artifacts unless the project explicitly requires another durable format.
- Keep Quality Gate and Main/User Checkpoint sections in the stage artifact by default.
- Store large independent subagent findings or checkpoint reviews under `reviews/` and reference them from the main artifact.
- Do not overwrite an approved artifact. Create a new version or revision when approved upstream input changes.
- Draft artifacts may be edited in place before checkpoint approval.
- Approved artifacts must include status, upstream references, derived-from artifact versions, and supersedes/superseded-by references when applicable.
- Use `stale` as a `run.md` marker for downstream artifacts that imported old upstream input. Do not use `stale` as an artifact header status; use `superseded` when a replacement artifact version exists.
- Use stable IDs inside artifacts. File names may change during drafting, but IDs referenced by downstream artifacts must remain stable after checkpoint approval.

Recommended artifact header:

```markdown
---
artifact_id:
artifact_type:
work_id:
status: draft | ready | approved | changes_requested | blocked | upstream_gap_detected | route_upstream | superseded
version:
derived_from:
supersedes:
updated_at:
---
```

## Context Resume Rule

Context resume prevents context compaction, interruption, or agent handoff from continuing a workflow from partial memory.

Rules:

- `Resume Context` is a run-record index, not a source of truth.
- Apply the `Context Resume Contract` before continuing after context compaction, interruption, agent handoff, manual resume, or unclear active item state. Use `active_run_refresh` when refreshing resume context during an uninterrupted active run.
- Do not assume the agent can detect context compaction. If active run context cannot be proven loaded, resume first. `Resume Workflow Run` and read-only inspection operations may run before this proof because they establish it; other write-capable operations must stop and resume first when proof is missing.
- Minimal reread is `run.md`, the active artifact header/status, the active item section, referenced upstream stable IDs, open routes, stale/superseded markers, and the stage workflow section for the next allowed operation.
- Required reread targets should be versioned as `<artifact>@<version>#<section-or-id>` whenever the artifact version is known.
- If `Resume Context` conflicts with approved artifact content, the artifact wins. Record the inconsistency and stop or route instead of guessing.
- Do not turn resume recovery into whole-history rereading unless the active item, references, or artifact versions are incomplete or conflicting.

## Zero-Blocker Rule

`Requirement Brief` and DESIGN are both zero-blocker stages.

```text
Requirement Brief must not hand off requirement-definition blockers.
DESIGN must not hand off design/approach blockers.
```

If `Requirement Brief` still has blockers, the workflow must not continue to DESIGN.

If `Requirement Brief` contains candidate acceptance criteria, candidate scope items that affect requirement definition, or unclear source provenance, it is still blocked.

If `Risk & Question Discovery` discovers a missed requirement-definition blocker, the workflow returns to `Requirement Brief` instead of moving forward.

If DESIGN still has blockers, the workflow must not produce an execution-ready SPEC or PLAN.

## Mandatory DESIGN Rule

Every requirement passes through DESIGN.

There is no `skip DESIGN` path. Low-risk work uses a lightweight DESIGN; high-risk work uses deeper DESIGN coverage.

```text
low risk -> light DESIGN
normal risk -> standard DESIGN
migration/rewrite/integration -> migration or architecture DESIGN
security/data/destructive operations -> safety DESIGN
```

The Design Entry Gate confirms DESIGN is allowed to start. The Design Scope Gate then decides DESIGN depth and required topics; it does not decide whether DESIGN exists.

Design Entry Gate and Design Scope Gate are DESIGN-owned entry gates. They are shown before `DESIGN` in the canonical chain because they must run before design discovery, but ownership and maintenance belong to the DESIGN workflow.

Risk Discovery Checkpoint authorizes Design Entry Gate, but it does not execute Design Entry Gate or Design Scope Gate. DESIGN executes Design Entry Gate first, then Design Scope Gate.

## Handoff Rule

Each node must hand off only the decisions and constraints that belong to downstream nodes.

```text
Requirement Brief -> stable requirement input
Risk & Question Discovery -> risks, assumptions, questions, and downstream inputs
Design Entry Gate -> approved upstream input validation
Design Scope Gate -> DESIGN depth and required design topics
DESIGN -> resolved approach and inputs for SPEC/PLAN
SPEC -> behavior contracts
PLAN -> execution path
```

## Upstream Reference Rule

Every stage document must include explicit references to all upstream associated artifacts.

```text
Requirement Brief references the raw requirement or requirement source.
Risk & Question Discovery references the raw requirement and Requirement Brief.
DESIGN references the raw requirement, Requirement Brief, and Risk & Question Discovery.
SPEC references the raw requirement, Requirement Brief, Risk & Question Discovery, and DESIGN.
PLAN references the raw requirement, Requirement Brief, Risk & Question Discovery, DESIGN, and SPEC.
```

References should include paths, URLs, document IDs, commit/branch when relevant, and status. Missing or inaccessible upstream references are blockers for that stage.

## Checkpoint Rule

Every artifact-producing stage must pass its internal Quality Gate before checkpoint review. Any stage that hands off to a downstream stage must end with checkpoint approval before handoff.

```text
Requirement Brief Quality Gate -> Requirement Brief Checkpoint -> Risk & Question Discovery
Risk Discovery Quality Gate -> Risk Discovery Checkpoint -> Design Entry Gate -> Design Scope Gate
DESIGN Quality Gate -> DESIGN Checkpoint -> SPEC
SPEC Quality Gate -> SPEC Checkpoint -> PLAN
PLAN Quality Gate -> PLAN Checkpoint
```

Checkpoint review may be performed by subagents. Checkpoint approval and downstream authorization belong to the main agent and user.

Subagent checkpoint reviews produce findings and recommendations. They do not approve handoff.

Main/User checkpoints freeze the current artifact as the authorized input for the next stage.

Quality Gate and Checkpoint have different meanings:

```text
Quality Gate = internal stage readiness check: the stage output is complete enough to be reviewed.
Checkpoint = external or higher-level authorization: the artifact is frozen as approved input for the next stage.
```

Checkpoint Entry Rule:

```text
Quality Gate must be ready before checkpoint review can run.
If checkpoint review finds a blocker or upstream gap, downstream handoff is not allowed.
The stage returns to the appropriate earlier work step, then must pass Quality Gate again before another checkpoint.
```

Quality Gate Failure Routing Rule:

```text
Each stage must define how failed Quality Gate checks map to the specific earlier workflow step that can fix them.
If the failure is caused by a current-stage drafting or coverage omission, return to the current-stage step that owns the missing work.
If SPEC or PLAN discovers missing upstream requirement, risk-discovery, design, or SPEC input that the current stage cannot own, mark `upstream_gap_detected` and route to the responsible upstream stage instead of guessing.
```

Only Requirement Brief and DESIGN are allowed to resolve and clear blockers directly:

```text
Requirement Brief resolves requirement-definition blockers.
DESIGN resolves design/approach blockers.
Risk & Question Discovery may discover missed requirement-definition blockers or design/approach blockers, but it must record and route them to the owning zero-blocker stage instead of resolving them.
SPEC and PLAN cannot produce their own upstream blockers. If SPEC or PLAN detects a blocker-like issue owned by an earlier stage, they must mark `upstream_gap_detected` and route back to the responsible upstream stage instead of guessing.
```

## Upstream Gap Routing Rule

`upstream_gap_detected` means the current stage found a missing, contradictory, or unauthorized upstream input that the current stage is not allowed to decide.

`route_upstream` means checkpoint authorization sends the work back to the stage that owns the missing decision or correction.

When an upstream gap is detected:

- Record the gap in the current artifact before routing.
- Set downstream authorization to `no`.
- Identify the responsible upstream stage and the exact artifact sections that must change.
- Do not continue downstream from the stale artifact.
- Do not fill the gap with an assumption unless the owning upstream stage explicitly classifies it as non-blocking.

Gap record:

```markdown
## Upstream Gap Record

| Gap ID | Detected In | Missing / Conflicting Input | Owner Stage | Affected Sections | Required Upstream Action | Downstream Authorization |
|---|---|---|---|---|---|---|
```

Owner routing:

| Gap type | Owner stage |
|---|---|
| Goal, scope, non-scope, acceptance, user/operator, source provenance, requirement constraint, or requirement-level assumption | Requirement Brief |
| Missing risk classification, assumption conflict, discussion point, design trigger, spec input, or plan input discovered before DESIGN starts | Risk & Question Discovery |
| Approach, architecture, boundary, migration, rollback, compatibility, dependency, safety, verification architecture, Spec Input, or Plan Input | DESIGN |
| Behavior contract, edge case, compatibility contract, error behavior, data/state behavior, or `SPEC-PLAN-*` item needed by PLAN | SPEC |
| Task decomposition, sequencing, verification mapping, rollback/safety plan, or stop condition derived from approved SPEC | PLAN |

After upstream repair:

- The repaired upstream artifact must pass its own Quality Gate again.
- The repaired upstream artifact must receive a new Main/User Checkpoint approval before downstream work resumes.
- Every downstream artifact that imported the old version must mark that version as superseded or stale.
- Downstream stages may update incrementally only when all imported input IDs can be remapped and no previous downstream decision conflicts with the repair.
- If remapping is incomplete, unclear, or conflict-bearing, rebuild the downstream artifact from the repaired upstream checkpoint.
- Each updated downstream artifact must pass its own Quality Gate and Checkpoint again before handoff.

Example:

```text
SPEC finds DESIGN missing a compatibility decision -> SPEC records Upstream Gap -> route to DESIGN -> DESIGN updates and passes Design Quality Gate + DESIGN Checkpoint -> SPEC re-imports DESIGN coverage -> SPEC passes Spec Quality Gate + SPEC Checkpoint again -> PLAN may start.
```

## Execution Readiness Rule

Execution-ready SPEC and PLAN artifacts are allowed only when:

- Requirement Brief has no requirement-definition blockers.
- DESIGN has no design/approach blockers.
- Acceptance criteria are confirmed, not guessed.
- Source provenance is confirmed for every project or external source the requirement depends on.
- Any remaining assumptions are explicit and non-blocking.
- Risks have been converted into SPEC contracts, PLAN constraints, verification, or rollback requirements.

## Coverage Completeness Rule

Requirement Brief and DESIGN carry the main responsibility for preventing downstream ambiguity.

```text
Requirement Brief must find all requirement-scope modules, capabilities, workflows, source boundaries, and acceptance needs.
DESIGN must find all design points, change points, integration boundaries, migration boundaries, compatibility boundaries, and execution-safety boundaries.
SPEC and PLAN must not rely on guessing missing scope or missing design decisions.
```

For migration, replacement, rewrite, and integration work, DESIGN must include requirement trace checking and boundary-by-boundary design coverage before handoff to SPEC. For integration, replacement, or cross-project work, DESIGN must include explicit Integration Boundaries.

When DESIGN uses subagents, conflicting findings must pass through a Subagent Conflict Gate instead of being guessed away.

When DESIGN contains high-cost or preference-sensitive tradeoffs, user-owned decisions must pass through a User Decision Gate before handoff to SPEC.

DESIGN must include a Change Point Inventory so SPEC and PLAN can derive contracts and execution steps without guessing what changes.

SPEC must map every DESIGN Spec Input, Change Point, Requirement Trace item, Boundary, and Integration Boundary into precise, testable contracts before PLAN can start.

SPEC must pass Main/User SPEC Checkpoint before PLAN can start. Subagent checkpoint findings must be merged and resolved or marked as `upstream_gap_detected` before approval.

Risk Discovery Plan Inputs must remain traceable through the pipeline:

```text
Risk Discovery Plan Input -> DESIGN Plan Input -> SPEC-PLAN-* -> PLAN task/check/rollback/safety item
```

PLAN does not need every task to directly reference Risk Discovery, but PLAN traceability must prove that Risk Discovery Plan Inputs were not lost.

## Coverage Closure Rule

SPEC and PLAN must close every imported upstream item before checkpoint approval.

Closure means each imported upstream ID has one explicit downstream status:

```text
covered: represented by a downstream contract, task, check, rollback/safety item, or trace row.
preserve: intentionally unchanged and backed by a preserve reason plus verification path when observable.
no-op: inspected and not affected; no special downstream behavior or task is required.
return_to_spec_step: SPEC coverage is incomplete and must return to the SPEC step that owns the missing contract.
return_to_plan_step: PLAN coverage is incomplete and must return to the PLAN step that owns the missing task, check, sequence, verification, rollback, or safety item.
upstream_gap_detected: the missing or conflicting input belongs to an upstream stage and must be routed by the Upstream Gap Routing Rule.
```

Rules:

- SPEC Design Coverage Import must assign closure status to every imported DESIGN Spec Input, Change Point, Requirement Trace item, Boundary, Integration Boundary, Risk / Attack Gate item, and remaining assumption.
- PLAN Contract-to-Task Mapping must assign closure status to every imported SPEC contract and `SPEC-PLAN-*` item.
- PLAN Risk Discovery Plan Input Traceability must assign closure status to every Risk Discovery Plan Input carried through DESIGN and SPEC.
- Light or standard work may use concise tables, but no imported upstream ID may be omitted or left without closure status.
- A stage cannot enter checkpoint review while any imported upstream ID has no closure status.

## Downstream Input Schema Rule

DESIGN, SPEC, and PLAN handoffs must use stable IDs so downstream imports do not depend on free-text conversion.

Spec Input schema:

```markdown
| Spec Input ID | Source Artifact | Source Item ID | Item | Required SPEC Contract | Reason | Status |
|---|---|---|---|---|---|---|
```

Plan Input schema:

```markdown
| Plan Input ID | Source Artifact | Source Item ID | Item | Required PLAN Constraint | Covers | Status |
|---|---|---|---|---|---|---|
```

Rules:

- DESIGN must emit Spec Inputs and Plan Inputs using these schemas.
- SPEC Design Coverage Import must preserve DESIGN Spec Input IDs.
- SPEC Plan Inputs must use `SPEC-PLAN-*` IDs when PLAN needs traceable execution, verification, rollback, or safety coverage.
- PLAN must map `SPEC-PLAN-*` items to tasks, checks, rollback/safety items, or explicit no-op/preserve coverage.

## Shared ID Scheme Rule

Stable IDs are required for any artifact item referenced by another stage.

Recommended prefixes:

| Artifact item | Prefix |
|---|---|
| Raw requirement note | `RAW-*` |
| Intake Brief item | `INTAKE-*` |
| Requirement Brief scope item | `REQ-SCOPE-*` |
| Requirement Brief acceptance item | `REQ-ACC-*` |
| Requirement Brief assumption | `REQ-ASM-*` |
| Requirement Brief downstream attention item | `REQ-DA-*` |
| Risk Discovery blocking question | `RISK-Q-*` |
| Risk Discovery assumption | `RISK-ASM-*` |
| Risk Discovery risk | `RISK-R-*` |
| Risk Discovery discussion point | `RISK-DISC-*` |
| Risk Discovery design trigger | `RISK-DES-*` |
| Risk Discovery Spec Input | `RISK-SPEC-*` |
| Risk Discovery Plan Input | `RISK-PLAN-*` |
| DESIGN option | `DES-OPT-*` |
| DESIGN decision | `DES-DEC-*` |
| DESIGN change point | `DES-CP-*` |
| DESIGN boundary | `DES-BND-*` |
| DESIGN integration boundary | `DES-INT-*` |
| DESIGN Spec Input | `DES-SPEC-*` |
| DESIGN Plan Input | `DES-PLAN-*` |
| SPEC contract | `SPEC-FR-*`, `SPEC-IF-*`, `SPEC-DATA-*`, `SPEC-ERR-*`, `SPEC-SAFE-*`, `SPEC-COMPAT-*`, `SPEC-OBS-*`, `SPEC-ACC-*`, `SPEC-EDGE-*` |
| SPEC Plan Input | `SPEC-PLAN-*` |
| PLAN task | `PLAN-TASK-*` |
| PLAN verification check | `PLAN-VERIFY-*` |
| PLAN rollback or safety item | `PLAN-SAFE-*` |

ID rules:

- Use three-digit numeric suffixes by default, such as `REQ-ACC-001`.
- Do not reuse an ID after checkpoint approval.
- If an approved item is replaced, keep the old ID as superseded and create a new ID.
- Downstream artifacts must preserve upstream IDs in trace columns instead of renumbering them.
- Mapping from Risk Discovery to PLAN should follow this chain:

```text
RISK-PLAN-* -> DES-PLAN-* -> SPEC-PLAN-* -> PLAN-TASK-* / PLAN-VERIFY-* / PLAN-SAFE-*
```

## Link Convention

Workflow documents in `docs/` use same-directory relative links, such as `workflow-invariants.md#canonical-chain`. Do not rewrite these as `docs/workflow-invariants.md#canonical-chain` from inside another `docs/*.md` file, because many Markdown renderers would resolve that as `docs/docs/...`.

Use a path-qualified link only when linking from outside `docs/`, such as `docs/workflow-invariants.md#canonical-chain`.

## Shared Concept Definitions

`preserve` means an existing behavior, interface, data shape, workflow, dependency, or safety property must intentionally remain unchanged. It requires a reason, a SPEC contract or preserve assertion, and a verification path when observable.

`no-op` means an inspected item is in the workflow's coverage surface but requires no change and no special preservation guarantee beyond normal regression coverage. It requires a reason, but not a new behavior contract unless downstream traceability would otherwise be ambiguous.

Use `preserve` when change would be a regression. Use `no-op` when the item is explicitly considered and found unaffected.

`migration-visible behavior` means behavior visible to users, operators, callers, tests, data stores, files, logs, status outputs, or rollback/recovery paths during or after migration. It includes old-data handling, compatibility behavior, error behavior, partial migration states, fallback visibility, and post-migration observable state. It does not include purely internal implementation steps unless those steps affect observable behavior or recoverability.

Risk priority is the order in which risks must be addressed by DESIGN, SPEC, and PLAN. Priority is derived from impact, likelihood, reversibility, safety, and traceability risk.

Recommended risk priority levels:

| Priority | Meaning | Required handling |
|---|---|---|
| P0 | High impact and hard to reverse, safety-sensitive, data-destructive, security/privacy-sensitive, or blocks workflow authorization. | Must be resolved, explicitly accepted by user, or routed before downstream handoff. |
| P1 | Material product, compatibility, migration, dependency, or execution risk. | Must have DESIGN mitigation and SPEC/PLAN coverage where relevant. |
| P2 | Moderate risk with clear mitigation or rollback. | Carry to the owning downstream stage with mitigation direction. |
| P3 | Low risk, local, reversible, or informational. | Record only when it affects traceability or verification. |

Do not sort risks by likelihood alone. A low-likelihood irreversible data loss risk outranks a likely but cheap local rework risk.

## Parallel Work Rule

Checkpoint dependencies are sequential. Artifact approval cannot be parallelized across required upstream checkpoints.

Allowed parallel work:

- Subagent discovery within a stage after that stage's entry gate passes.
- Multiple independent subagent checkpoint reviews after the stage Quality Gate is `ready`.
- Evidence gathering for a later stage, if it does not produce an authoritative downstream artifact.
- Scratch drafting of a downstream artifact while waiting for an upstream user decision, if the draft is clearly marked `unapproved` and is re-imported from the approved upstream artifact before Quality Gate.

Forbidden parallel work:

- Approving Risk Discovery before Requirement Brief Checkpoint approval.
- Approving DESIGN before Risk Discovery Checkpoint approval.
- Approving SPEC before DESIGN Checkpoint approval.
- Approving PLAN before SPEC Checkpoint approval.
- Treating speculative downstream drafts as execution-ready artifacts.

If upstream input changes while a downstream draft exists, the downstream draft must re-run import, traceability, Quality Gate, and Checkpoint before handoff.

## Cross-Project Checklist

For cross-project, cross-repository, integration, replacement, or migration work, the workflow must explicitly cover:

- Source provenance for every project: path or URL, branch, commit, access, trust status, and owner when known.
- Scope ownership: which project owns each capability, workflow, API, data store, command, file format, and user/operator surface.
- Boundary direction: current side, target side, responsibility split, input/output, error behavior, and data/state mapping.
- Precedence rules when projects disagree on behavior, compatibility, validation, permissions, or errors.
- Dependency and runtime compatibility: package versions, build systems, language/runtime constraints, CLIs, external services, and generated artifacts.
- Data and migration safety: source-of-truth, backup, rollback, idempotency, partial migration behavior, and migration-visible behavior.
- Verification coverage across repositories: unit, integration, contract, compatibility, golden/equivalence, migration, and manual checks.
- Operational concerns: release order, deployment order, config changes, credentials, permissions, observability, and rollback authority.

## Workflow Document Change Rule

Changes to workflow documents must be treated as changes to the process contract.

Minimum change process:

- State the problem or gap being fixed.
- Identify affected workflow documents and downstream templates.
- Update shared rules in this document before duplicating stage-specific wording.
- Keep stage documents aligned with shared terminology and schemas.
- Update `Document Map`, `Key Concept Index`, and `README.md` when navigation or concepts change.
- Run a consistency check for renamed statuses, concepts, table fields, and cross-document references.
- Get Main/User approval before treating the revised workflow as the new standard.

Workflow edits do not need the full requirement-to-PLAN chain unless the change itself is large, risky, or changes how downstream execution is authorized.

## BDD / TDD Placement Rule

BDD and TDD are useful in this workflow, but they belong to different stages.

```text
Requirement Brief: may use BDD-style scenarios to generate and confirm Acceptance Candidates.
DESIGN: defines verification strategy and test architecture, not TDD execution steps.
SPEC: defines testable behavior contracts and BDD-style Acceptance Scenarios.
PLAN: turns SPEC contracts into TDD execution steps, such as red -> green -> refactor.
```

Verification Strategy / Test Architecture belongs in DESIGN and is required. DESIGN decides required verification layers such as unit, integration, contract, migration, golden/equivalence, regression, compatibility, or safety tests. PLAN decides the concrete test-writing sequence.

In PLAN, TDD is required for tasks where the referenced SPEC behavior can be verified before implementation. If TDD does not fit, PLAN must explain why and provide alternative verification.

## PLAN Neutrality Rule

The PLAN stage is executor-neutral. It produces a canonical implementation plan and does not choose or format for GSD, Superpowers, or any other executor.

Executor-specific adaptation, orchestration, and management are out of scope for the requirement-to-PLAN workflow.

If a write-capable workflow run discovers missing or contradictory requirement, risk, DESIGN, SPEC, or PLAN input before closure, it must stop and route through `upstream_gap_detected` / `route_upstream` instead of silently patching the approved PLAN.

No orphan PLAN tasks are allowed. Every PLAN task must include explicit SPEC references so execution can trace why the task exists.

PLAN tasks must be independently executable and independently verifiable increments. PLAN must define stop/escalation conditions so execution does not continue by guessing when verification fails, scope drifts, destructive work appears, or upstream gaps are discovered.

Positive handling:

```text
Task: Add compatibility coverage for SPEC-COMPAT-001.
Steps: add failing compatibility test, implement minimal behavior, run targeted regression checks.
Verification: command or method, expected result, SPEC references.
```

Anti-example:

```text
Task: Ask the GSD executor to use its migration playbook and fix anything it finds.
```

The positive example is executor-neutral because any capable executor can run it. The anti-example is executor-specific, delegates decisions to an executor, and lacks SPEC-traceable verification.

## Document Map

Use this map to choose the right workflow document before editing or generating artifacts.

| Need | Read |
|---|---|
| Start using the workflow quickly | `README.md` |
| Operate the local CLI end to end from raw requirement to approved PLAN | `workflow-operator-runbook.md` |
| Run or resume the workflow, operate gates/checkpoints, route upstream gaps, and close a workflow run | `workflow-execution-guide.md` |
| Design operation entry semantics before choosing CLI, slash command, MCP, API, skill, or UI carriers | `workflow-operation-surface.md` |
| Map operation semantics into carrier-neutral command intents before designing concrete CLI, slash command, MCP, API, skill, or UI syntax | `workflow-command-surface.md` |
| Design concrete CLI command names, flags, output, dry-run, confirmation, and exit semantics | `workflow-cli-adapter.md` |
| Expose the workflow to agents as `coyeme-workflow-*` project shortcuts | `workflow-agent-command-adapter.md` |
| Understand cross-stage order, invariants, checkpoints, subagent shared rules, and traceability rules | `workflow-invariants.md` |
| Capture raw requirement, clarify scope, source provenance, acceptance, and module/capability coverage | `requirement-brief-workflow.md` |
| Scan blockers, assumptions, risks, discussion points, design triggers, spec inputs, and plan inputs | `risk-question-discovery-workflow.md` |
| Choose approach, architecture, migration/rollback/compatibility strategy, boundaries, and verification architecture | `design-workflow.md` |
| Convert approved DESIGN into precise, testable behavior contracts | `spec-workflow.md` |
| Convert approved SPEC into executor-neutral tasks, sequencing, verification, rollback, safety, and stop conditions | `plan-workflow.md` |

## Key Concept Index

| Concept | Meaning | Owner document | Section |
|---|---|---|---|
| Canonical Chain | Authoritative requirement-to-PLAN node order. | `workflow-invariants.md` | `Canonical Chain` |
| Workflow Run | One durable attempt to convert a raw requirement into an approved executor-neutral PLAN. | `workflow-execution-guide.md` | `Workflow Run Model` |
| Operator Runbook | Concrete local CLI operating guide from raw requirement through PLAN closure. | `workflow-operator-runbook.md` | `Purpose` |
| Run State | Execution status for the current workflow run, including draft, review, routing, approval, and closed states. | `workflow-execution-guide.md` | `Run States` |
| Resume Context | Run-record section that records last completed operation, next allowed operation, active item, versioned required reread targets, and resume reason. | `workflow-execution-guide.md` | `Workflow Run Model` |
| Context Resume Contract | Lightweight recovery protocol for context compaction, interruption, agent handoff, or manual resume. | `workflow-execution-guide.md` | `Context Resume Contract` |
| Canonical Operation | Executor-neutral operation used by the run protocol before any user-facing command mapping. | `workflow-execution-guide.md` | `Canonical Operations` |
| Operation Surface | Semantic entry layer that maps user or agent intent to canonical operations without choosing a carrier. | `workflow-operation-surface.md` | `Purpose` |
| Operation Carrier Boundary | Boundary separating operation semantics from CLI, slash command, MCP, API, skill, or UI carrier syntax. | `workflow-operation-surface.md` | `Operation Carrier Boundary` |
| Operation Contract | Required semantic contract for each operation intent, including inputs, writes, confirmations, stops, and result statuses. | `workflow-operation-surface.md` | `Operation Contract Schema` |
| Merge Checkpoint Review Findings | Operation that merges checkpoint review findings before Main/User Checkpoint approval without granting approval itself. | `workflow-operation-surface.md` | `Merge Checkpoint Review Findings` |
| Command Surface | Carrier-neutral command intent layer that maps operation semantics to operator-facing workflow actions. | `workflow-command-surface.md` | `Purpose` |
| Command Intent | Stable workflow action ID, such as `CMD-RUN-START`, that a later concrete command carrier may expose. | `workflow-command-surface.md` | `Command Intent Catalog` |
| Command Contract | Required semantic contract for each command intent, including operation intents, canonical operations, inputs, writes, confirmations, stops, and results. | `workflow-command-surface.md` | `Command Contract Schema` |
| Agent Command Adapter | Compact project shortcut carrier with `coyeme-workflow-start`, `coyeme-workflow-continue`, `coyeme-workflow-status`, `coyeme-workflow-switch`, and `coyeme-workflow-adapt`. | `workflow-agent-command-adapter.md` | `Purpose` |
| Active Run | Selected nonterminal workflow run used by `coyeme-workflow-continue`. | `workflow-agent-command-adapter.md` | `Run Selection Model` |
| Workspace Active Pointer | Workspace-level pointer at `docs/artifacts/.workflow-active` that selects the default run for project shortcuts. | `workflow-agent-command-adapter.md` | `Workspace Active Pointer` |
| Work ID | Stable generated workflow run ID used in artifact paths and `coyeme-workflow-switch`. | `workflow-agent-command-adapter.md` | `Work ID Rule` |
| Run State Command Eligibility | Matrix defining which command intents may run from each `run.md` state. | `workflow-command-surface.md` | `Run State Command Eligibility Matrix` |
| Operation Coverage Matrix | Mapping that proves every operation intent is covered by a command intent or explicitly marked internal-only. | `workflow-command-surface.md` | `Operation Coverage Matrix` |
| CLI Adapter | Concrete CLI carrier that maps command intents to command names, flags, output, dry-run, confirmation, and exit semantics without adding workflow authority. | `workflow-cli-adapter.md` | `Purpose` |
| Command Mapping Boundary | Boundary that prevents the run protocol from hard-coding command names, runtime adapters, or executor-specific prompt formats. | `workflow-execution-guide.md` | `Command Mapping Boundary` |
| Requirement Brief | Stable detailed requirement with scope, non-scope, acceptance, source provenance, and module/capability coverage. | `requirement-brief-workflow.md` | `Step 4: Requirement Brief v1` |
| Raw Requirement Capture | Recommended structure for preserving original user input and source references before interpretation. | `requirement-brief-workflow.md` | `Step 1: Raw Requirement` |
| Requirement Discovery Exit Conditions | Conditions for stopping discovery and drafting Requirement Brief v1. | `requirement-brief-workflow.md` | `Step 3: Requirement Discovery Loop` |
| Risk & Question Discovery | Systematic scan for blockers, assumptions, risks, discussion points, and downstream inputs before DESIGN. | `risk-question-discovery-workflow.md` | `Risk Discovery Canonical Output` |
| Risk Discovery Subagent Discovery | Optional parallel risk/assumption/input discovery across scan dimensions. | `risk-question-discovery-workflow.md` | `Subagent Use` |
| Assumption Conflict Handling | Rules for conflicts between assumptions, upstream facts, raw intent, or other assumptions. | `requirement-brief-workflow.md`, `risk-question-discovery-workflow.md` | `Assumption Conflict Handling` |
| Design Scope Gate | DESIGN-owned depth-selection gate that runs after Design Entry Gate and chooses DESIGN depth and required topics. | `design-workflow.md` | `Gate 2: Design Scope Gate` |
| DESIGN | Mandatory solution-design stage that resolves approach, architecture, migration, rollback, compatibility, dependencies, boundaries, and verification strategy. | `design-workflow.md` | `Responsibilities` |
| SPEC | Precise behavior-contract stage derived from approved DESIGN. | `spec-workflow.md` | `Responsibilities` |
| PLAN | Executor-neutral implementation plan derived from approved SPEC. | `plan-workflow.md` | `Responsibilities` |
| Quality Gate | Internal readiness check before checkpoint review. | `workflow-invariants.md` | `Checkpoint Rule` |
| Quality Gate Failure Routing | Mapping from failed quality checks to the workflow step that owns the fix. | `workflow-invariants.md` | `Checkpoint Rule` |
| Checkpoint | Main/User authorization that freezes an artifact for downstream use. | `workflow-invariants.md` | `Checkpoint Rule` |
| zero-blocker stage | Stage that cannot pass unresolved blockers downstream. | `workflow-invariants.md` | `Zero-Blocker Rule` |
| upstream_gap_detected | Current stage found missing upstream input it cannot decide and must route upstream instead of guessing. | `workflow-invariants.md` | `Upstream Gap Routing Rule` |
| No orphan PLAN tasks | Every PLAN task must trace to at least one SPEC item. | `plan-workflow.md` | `Contract-to-Task Mapping` |
| Risk Discovery Plan Input Trace | Chain proving Risk Discovery Plan Inputs reach DESIGN, SPEC, and PLAN coverage. | `workflow-invariants.md` | `Coverage Completeness Rule` |
| Coverage Closure | Rule requiring SPEC and PLAN to assign closure status to every imported upstream ID before checkpoint review. | `workflow-invariants.md` | `Coverage Closure Rule` |
| Verification Strategy / Test Architecture | DESIGN-defined verification layers that PLAN later converts into concrete checks and TDD steps. | `design-workflow.md` | `Verification Strategy / Test Architecture` |
| Intake Brief v0 | First structured interpretation of the raw requirement, allowed to be incomplete. | `requirement-brief-workflow.md` | `Step 2: Intake Brief v0` |
| Requirement Discovery Notes | Traceability record for context facts, scope inventory, assumptions, blockers, and downstream attention before Requirement Brief v1. | `requirement-brief-workflow.md` | `Step 3: Requirement Discovery Loop` |
| Design Entry Gate | DESIGN entry check that confirms approved requirement and risk inputs are available before depth selection. | `design-workflow.md` | `Gate 1: Design Entry Gate` |
| Testability Gate | SPEC gate that prevents vague or untestable contracts from entering PLAN. | `spec-workflow.md` | `Testability Gate` |
| Subagent Conflict Gate | DESIGN gate for preserving and routing conflicting subagent findings. | `design-workflow.md` | `Subagent Conflict Gate` |
| User Decision Gate | DESIGN gate for high-cost or preference-sensitive user-owned decisions. | `design-workflow.md` | `User Decision Gate` |
| Subagent Model Rule | Subagents inherit main-agent capability and do not hard-code model names. | `workflow-invariants.md` | `Subagent Model Rule` |
| Shared Subagent Use Structure | Common subagent section structure and approval boundary for all stages. | `workflow-invariants.md` | `Shared Subagent Use Structure` |
| Shared Subagent Merge Rule | Common merge order and conflict routing for subagent findings. | `workflow-invariants.md` | `Shared Subagent Merge Rule` |
| Artifact Lifecycle | Default artifact storage, versioning, and approved-artifact handling. | `workflow-invariants.md` | `Artifact Lifecycle Rule` |
| Upstream Gap Routing | Closed loop for recording, routing, repairing, and revalidating upstream gaps. | `workflow-invariants.md` | `Upstream Gap Routing Rule` |
| Downstream Input Schema | Stable Spec Input and Plan Input schemas used across DESIGN, SPEC, and PLAN. | `workflow-invariants.md` | `Downstream Input Schema Rule` |
| preserve | Intentional unchanged behavior or surface that needs reason and verification when observable. | `workflow-invariants.md` | `Shared Concept Definitions` |
| no-op | Inspected item that is unaffected and needs no special preservation guarantee. | `workflow-invariants.md` | `Shared Concept Definitions` |
| Change Type | DESIGN/PLAN classification for add, modify, replace, remove, preserve, and no-op handling. | `workflow-invariants.md` | `Shared Concept Definitions` |
| migration-visible behavior | Observable behavior during or after migration. | `workflow-invariants.md` | `Shared Concept Definitions` |
| Risk Priority | Priority framework for ordering risk handling across downstream stages. | `workflow-invariants.md` | `Shared Concept Definitions` |
| Shared ID Scheme | Stable ID prefixes and traceability mapping across Requirement, Risk, DESIGN, SPEC, and PLAN. | `workflow-invariants.md` | `Shared ID Scheme Rule` |
| Link Convention | Relative link convention for workflow documents under `docs/`. | `workflow-invariants.md` | `Link Convention` |
| Parallel Work Rule | What can and cannot run in parallel across stages and checkpoints. | `workflow-invariants.md` | `Parallel Work Rule` |
| Cross-Project Checklist | Common checklist for multi-repository, integration, replacement, and migration work. | `workflow-invariants.md` | `Cross-Project Checklist` |
| Workflow Document Change Rule | Minimum governance for changing workflow documents themselves. | `workflow-invariants.md` | `Workflow Document Change Rule` |

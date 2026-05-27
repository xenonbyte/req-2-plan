# Requirement to Requirement Brief Workflow

## Purpose

This document records the agreed workflow for converting a raw user requirement into a stable `Requirement Brief`. This stage clarifies and standardizes the requirement into a detailed requirement with scope inventory; it does not choose the technical design, produce a SPEC, or create an implementation PLAN.

## Position

Canonical node order is defined in `workflow-invariants.md#canonical-chain`. This document covers the requirement-definition segment:

```text
Raw Requirement
  -> Intake Brief v0
  -> Requirement Discovery Loop
  -> Requirement Brief v1
  -> Requirement Brief Quality Gate
  -> Requirement Brief Checkpoint
```

This document only covers conversion through the Requirement Brief quality gate and checkpoint.

## Core Principle

`Requirement Brief` may include investigation and discussion when the raw requirement is too ambiguous to define detailed scope, affected capabilities, or relevant modules, but it must not become a design document.

Use this boundary:

```text
Requirement-stage discovery: clarify what problem, scope, constraints, acceptance, capabilities, and module coverage mean.
Design-stage discovery: decide which technical solution should be used and why.
```

`Requirement Brief` is a zero-blocker stage. If any requirement-definition blocker remains, the workflow must not continue to DESIGN. Requirement-definition blockers include unresolved goal, scope, non-scope, acceptance, user/operator, constraint, source provenance, or module coverage questions.

If candidate acceptance criteria are generated during this stage, they must be confirmed, rejected, or supplemented by the user before the stage can pass. Requirement Brief must not hand off guessed acceptance to DESIGN or SPEC.

Any requirement that depends on a local path, remote repository, external project, design file, or document source must have confirmed source provenance. Unknown source, version, access, branch, or commit is a blocker.

Requirement Brief can answer:

```text
Which capabilities are in scope?
Which modules, packages, services, commands, workflows, or repositories are relevant to the requirement?
Which modules are candidates for migration, replacement, integration, or preservation?
Which capabilities are explicitly out of scope?
```

Requirement Brief must not answer:

```text
How should those modules be changed?
Which architecture or implementation approach should be selected?
How should migration, rollback, compatibility, or adapter design work?
Which exact files should be edited in what order?
```

## Step 1: Raw Requirement

The raw requirement is the user's original input. It may be vague, conversational, incomplete, or mixed with suggested technical solutions.

Actions:

- Preserve the user's original intent and important wording.
- Identify explicit goals, constraints, preferences, and exclusions.
- Do not convert the request into an architecture or task breakdown.
- Do not treat a mentioned technical solution as a design decision yet.

Output fragment:

```markdown
## Raw Notes
- Key original requirement sentence or phrase.
- Key stated constraint, preference, or exclusion.
```

Recommended capture format:

```markdown
## Raw Requirement Capture
- Original Text:
- Source / Requester:
- Received At:
- Linked Paths / Repositories / Documents:
- Attachments / References:
- Explicit Goal Signals:
- Explicit Scope Signals:
- Explicit Non-scope Signals:
- Explicit Constraints / Preferences:
- Sensitive or Redacted Information:
```

Raw Requirement has no minimum quality gate. Very rough input can still enter `Intake Brief v0`; low-quality or incomplete input should trigger the Requirement Discovery Loop instead of being rejected.

## Step 2: Intake Brief v0

`Intake Brief v0` is the first structured interpretation of the raw requirement. It is allowed to be incomplete.

Actions:

- Extract the initial goal.
- Separate stated scope from stated non-scope.
- Capture stated technical directions.
- Capture known constraints.
- Identify obvious missing information.
- Decide whether a requirement discovery loop is needed.

The workflow may skip Requirement Discovery Loop only when Intake Brief v0 already has enough confirmed information to produce a stable Requirement Brief:

- Goal is understandable as an outcome.
- Scope and non-scope are clear enough for this requirement size.
- Acceptance signals can become confirmed acceptance without guessing.
- Source provenance is known for referenced local paths, repositories, documents, or external projects.
- No project/context inspection is needed to define requirement scope.
- User-mentioned technical directions can be classified without design analysis.

Template:

```markdown
# Intake Brief v0: <title>

## Initial Goal
Initial understanding of the desired outcome.

## Stated Scope
What the user explicitly asked to include.

## Stated Non-scope
What the user explicitly excluded or deferred.

## Stated Technical Direction
Technologies, tools, platforms, executors, or approaches mentioned by the user.

## Known Constraints
Constraints explicitly stated by the user.

## Initial Acceptance Signals
Signals in the raw requirement that suggest how completion will be judged.

## Obvious Gaps
Missing information that may affect requirement definition.

## Raw Notes
Important original phrases from the user's request.

## Tier Estimation
The Evidence Block produced by `CMD-TIER-ESTIMATE` at `run-start`. Subfields:

- `keywords_hit`: modifier-triggering keywords matched against the request and links.
- `repo_baseline_summary`: loc, module_count, is_monorepo, language set, and detected entry points.
- `linked_context`: link expansion result with `reachable`, `requires_auth`, or `unreachable` per URL.
- `scope_signals`: counts of repos, modules, and surfaces named in the request.
- `escalation_candidates`: modifier candidates surfaced by the scan but not yet locked.
- `floor`: computed Tier Floor (base plus modifiers).
- `confirm_status`: `pending` until the user confirms via `tier-lock`, then `confirmed`.
```

> See [Workflow Complexity Tier Rule](workflow-invariants.md#workflow-complexity-tier-rule) for the section-requirements-by-tier table.

## Step 3: Requirement Discovery Loop

Run this loop only when the requirement is not stable enough to become a `Requirement Brief`.

Typical triggers:

- The goal is unclear.
- Scope cannot be determined.
- The user describes a technical solution instead of the underlying problem.
- The request involves migration, rewrite, project integration, or multiple existing systems.
- Reading project context is necessary to understand what the work actually means.
- Acceptance criteria are not verifiable.

Actions:

- Read relevant project files, docs, configuration, tests, and entrypoints when needed.
- For migration, rewrite, or integration requirements, inspect enough of the involved project sources to list relevant structure, capabilities, and module coverage.
- Record confirmed context facts separately from assumptions.
- Classify any technical direction mentioned by the user.
- Ask only questions that truly block stable requirement definition.
- Keep non-blocking assumptions explicit.
- Check assumption conflicts before drafting Requirement Brief v1.
- Preserve execution, verification, rollback, or safety concerns as downstream attention items for Risk & Question Discovery.
- Preserve topics that the user explicitly deferred to later workflow nodes.

### Exit Conditions

Requirement Discovery Loop can exit only when all of these are true:

- There is enough confirmed evidence to draft `Requirement Brief v1`.
- Remaining unknowns are either non-blocking `Open Inputs` or explicit blockers.
- Source provenance is confirmed for every requirement-dependent source.
- Scope Inventory can classify relevant items as `In Scope`, `Out of Scope`, `Candidate`, or `Referenced Only`.
- Candidate scope items that affect requirement definition are ready for user confirmation, exclusion, or blocker handling.
- Acceptance candidates are ready for user confirmation, rejection, or supplementation.
- Further context reading would only inform DESIGN, SPEC, or PLAN rather than requirement definition.

The loop must not continue just to choose an architecture, migration strategy, adapter strategy, rollback strategy, or task order.

### Assumption Conflict Handling

Requirement-stage assumptions must not silently override raw user intent, confirmed context facts, source provenance, or confirmed acceptance.

Rules:

- If an assumption conflicts with raw requirement intent, confirmed scope, non-scope, acceptance, constraints, or source provenance, treat it as a requirement-definition blocker.
- If two requirement-stage assumptions conflict and the conflict affects goal, scope, acceptance, user/operator, source provenance, or constraints, convert the conflict into a blocking question.
- If an assumption conflict only affects approach, architecture, migration, rollback, compatibility, dependency, execution safety, or task sequencing, keep it out of Requirement Brief decisions and record it as a downstream attention item for Risk & Question Discovery.
- If the conflict is non-blocking, keep both assumptions, mark source and impact for each, and state which later node must confirm or eliminate them.
- Do not convert a conflicting assumption into a confirmed requirement fact.

Use `workflow-invariants.md#shared-subagent-merge-rule` when assumption conflicts come from subagent findings.

### Subagent Use

Requirement Discovery Loop may use subagents when parallel fact gathering reduces omission risk. Subagents are optional; small or clear requirements can be handled directly by the main agent.

This section follows the shared Subagent Use structure in `workflow-invariants.md#shared-subagent-use-structure`. The rules below define Requirement Brief-specific discovery behavior.

Subagents follow `workflow-invariants.md#subagent-model-rule`.

Use subagents when:

- The requirement involves two or more projects or repositories.
- The project is large enough that module or capability inventory is likely to be incomplete if done sequentially.
- The request involves migration, rewrite, integration, or replacement.
- Source provenance must be checked across local paths, remote repositories, branches, commits, design files, or document sources.
- A specific capability must be found across many directories, modules, commands, APIs, or tests.

Subagents may produce evidence, not decisions.

Allowed subagent tasks:

- Source provenance check.
- Project structure scan.
- Module and capability inventory.
- Integration surface scan.
- Existing behavior summary.
- Acceptance candidate extraction.
- Requirement-definition blocker discovery.

Forbidden subagent tasks:

- Selecting a technical solution.
- Choosing architecture.
- Choosing migration, compatibility, rollback, or adapter strategy.
- Deciding how modules should be changed.
- Producing SPEC or PLAN.
- Treating candidate acceptance criteria as confirmed acceptance.
- Resolving blockers that require user confirmation.

Subagent output extends the shared subagent finding template in `workflow-invariants.md#shared-templates`:

```markdown
# Subagent Finding: <topic>

## Scope
What this subagent inspected.

## Sources
Paths, repositories, documents, configuration, tests, or commands inspected.

## Facts
Evidence-backed facts only.

## Scope Inventory
- In Scope:
- Out of Scope:
- Candidate:
- Referenced Only:

## Acceptance Candidates
Candidate acceptance criteria only. These are not confirmed acceptance.

## Blockers
Requirement-definition blockers found by this subagent.

## Unknowns
Information still unconfirmed.

## Evidence
Key files, paths, commands, or references supporting the findings.
```

The main agent must merge subagent findings before producing `Requirement Brief v1`.

Merge responsibilities:

- Deduplicate findings.
- Resolve obvious evidence-level duplicates.
- Preserve conflicts instead of guessing.
- Classify scope items as `In Scope`, `Out of Scope`, `Candidate`, or `Referenced Only`.
- Convert unresolved conflicts into blockers or candidates.
- Present acceptance candidates to the user for confirmation, rejection, or supplementation.
- Ensure no requirement-definition blocker remains before passing the quality gate.

Technical direction classification:

```text
Hard Constraint: Must be followed.
Preference: User preference, but still open to discussion.
Proposed Solution: A possible implementation direction, not yet validated.
Unknown: Meaning or priority is unclear.
```

Template:

```markdown
# Requirement Discovery Notes

## Context Facts
Facts confirmed from project files, docs, configuration, tests, or other reliable context.

## Source Provenance
Confirmed local paths, remote repositories, branches, commits, access status, and any unresolved source identity issues.

## Requirement Clarifications
Requirement points clarified through investigation or discussion.

## Acceptance Candidates
Candidate acceptance criteria generated from the requirement or project context. These must be confirmed, rejected, or supplemented by the user before Requirement Brief can pass the quality gate.

BDD-style scenarios may be used here to make acceptance candidates concrete, but they remain candidates until the user confirms, rejects, or supplements them.

## Scope Inventory
Relevant projects, modules, packages, services, commands, workflows, capabilities, and integration surfaces classified by scope status.

Use these categories:

```text
In Scope: Confirmed part of the requirement.
Out of Scope: Confirmed excluded from the requirement.
Candidate: Possibly relevant, requires clarification or later analysis.
Referenced Only: Needed for context or dependency understanding, but not part of the requirement coverage.
```

## Technical Direction Classification
Classify each user-mentioned technology or approach as hard constraint, preference, proposed solution, or unknown.

## Scope Candidates
Alternative interpretations of scope, if more than one remains plausible.

## Blocking Questions
Questions that must be answered before a stable Requirement Brief can be produced.

## Assumptions
Non-blocking assumptions that can be carried forward, with source marked.

## Assumption Conflict Check
Conflicts between assumptions, raw intent, confirmed facts, source provenance, or acceptance. Requirement-definition conflicts must become blockers before Requirement Brief v1.

## Downstream Attention
Execution, verification, rollback, safety, migration, compatibility, or plan-shaping concerns discovered during requirement work. These are not design or PLAN decisions; Risk & Question Discovery must classify them into risks, design triggers, spec inputs, or plan inputs.

## Deferred Topics
Topics explicitly deferred to later nodes such as DESIGN, SPEC, or PLAN.
```

## Step 4: Requirement Brief v1

`Requirement Brief v1` is the stable requirement input for later workflow nodes.

Actions:

- Fix the goal as an outcome, not an unvalidated implementation.
- Fix scope and non-scope.
- Record the project, repository, module, capability, workflow, and integration surfaces that the requirement covers.
- Identify users, operators, maintainers, and affected parties.
- Define verifiable acceptance criteria.
- Record confirmed constraints and explicit assumptions.
- Record downstream attention items that Risk & Question Discovery must classify.
- Preserve deferred topics and open inputs.
- State whether mentioned technical directions are constraints, preferences, proposed solutions, or unknowns.

Template:

```markdown
# Requirement Brief: <title>

## Upstream References
| Artifact | Reference | Status |
|---|---|---|
| Raw Requirement |  | available |

## Goal
The final outcome to achieve.

## Background
Why this is needed now and what pain it addresses.

## Scope
What this requirement includes.

## Non-scope
What this requirement does not include.

## Scope Inventory
Projects, repositories, modules, packages, services, commands, workflows, capabilities, or integration surfaces classified as `In Scope`, `Out of Scope`, `Candidate`, or `Referenced Only`.

## Users / Operators
Who provides input, who uses the output, who maintains it, and who is affected.

## Acceptance
Verifiable conditions that define completion.

This section must contain only confirmed acceptance criteria. Candidate acceptance criteria must not remain here without user confirmation.

## Constraints
Confirmed limits, preferences, environment constraints, dependencies, or assumptions.

## Assumptions
Non-blocking assumptions with source, impact if wrong, conflict status, and carry target.

## Downstream Attention
Requirement-stage concerns that may affect Risk Discovery, DESIGN, SPEC, or PLAN. Examples: backup needs, destructive-operation permissions, migration safety, verification expectations, cross-project release ordering, or execution constraints. These are inputs to Risk & Question Discovery, not decisions.

## Stated Technical Direction
User-mentioned technologies or approaches and their classification.

## Source Provenance
Confirmed source locations, versions, branches, commits, and access status for any local or remote projects involved.

## Deferred
Topics intentionally left for later workflow nodes.

## Open Inputs
Information still missing but not blocking this brief.

## Raw Notes
Traceable key phrases from the original requirement.
```

## Example Boundaries

### Example: Refactor Project A with Rust

Requirement Brief should:

- Confirm Project A source provenance: local path, remote repository, branch, commit, access, and whether the source can be trusted.
- Treat unknown or inaccessible Project A provenance as a blocker.
- Inspect Project A structure, entrypoints, modules, commands, configuration, tests, and release shape.
- List Project A capabilities and module coverage as `In Scope`, `Out of Scope`, `Candidate`, or `Referenced Only`.
- Identify which modules are in migration or rewrite scope.
- Classify "Rust refactor" as a hard constraint, preference, proposed solution, or unknown.
- Generate behavior-equivalence and acceptance candidates, then confirm, reject, or supplement them with the user before passing the quality gate.

Requirement Brief must not decide:

- Rust crate structure.
- Full rewrite versus incremental migration.
- FFI, CLI, service boundary, or library boundary.
- Migration order.
- Dual-run or behavior-equivalence verification design.

### Example: Integrate forma and opendesign

Requirement Brief should:

- Confirm source provenance, versions, branches, commits, and access for both projects.
- Inspect both projects enough to understand structure and relevant capabilities.
- List all forma modules related to pencil or design capabilities.
- List the design-related operations currently present in forma.
- List opendesign capabilities relevant to the integration request.
- Identify opendesign modules and capabilities that are in scope.
- Identify opendesign modules and capabilities that are out of scope.
- Classify ambiguous opendesign modules and capabilities as `Candidate` instead of silently treating them as in scope.
- Clarify what "replace pencil design capability with opendesign" means at the requirement level: capability replacement, API replacement, storage model replacement, workflow replacement, or execution replacement.
- Generate candidates for which forma design flows must remain usable after replacement, then confirm, reject, or supplement them with the user before passing the quality gate.

Requirement Brief must not decide:

- Adapter architecture.
- Data model conversion strategy.
- Compatibility strategy for old pencil documents.
- Migration path.
- Rollback strategy.
- Module boundary or implementation design.

## Step 5: Requirement Brief Quality Gate

The quality gate decides whether `Requirement Brief v1` is ready for the next stage. It must not pass requirement-definition blockers downstream.

Checks:

- Goal describes an outcome, not an unvalidated implementation.
- Scope and non-scope are separated.
- Scope inventory lists relevant projects, modules, capabilities, workflows, and integration surfaces with `In Scope`, `Out of Scope`, `Candidate`, or `Referenced Only` status when project context is needed.
- No `Candidate` scope item remains unresolved if it affects requirement definition.
- Acceptance is verifiable and confirmed.
- Acceptance candidates have been confirmed, rejected, or supplemented by the user.
- Constraints contain confirmed facts or explicitly marked assumptions.
- Assumptions include source, impact if wrong, conflict status, and carry target.
- Assumption conflicts that affect requirement definition are resolved or converted into blockers.
- Downstream attention items are recorded when requirement-stage discovery finds execution, verification, rollback, safety, migration, compatibility, or plan-shaping concerns.
- Source provenance is confirmed for any local path, remote repository, external project, design file, or document source that the requirement depends on.
- User-mentioned technical directions are classified, not silently accepted as design decisions.
- Deferred topics are not expanded prematurely.
- Open inputs do not include questions that block requirement definition.
- Any requirement-definition blocker sets status to `blocked`.
- Raw notes preserve traceability to the original intent.
- Tier Estimation Evidence Block is present and complete; user confirmation is recorded via `tier-lock` before `stage-produce` runs for `requirement_brief`. See [Workflow Complexity Tier Rule](workflow-invariants.md#workflow-complexity-tier-rule) for the section-requirements-by-tier table.

Template:

```markdown
# Requirement Brief Quality Gate

## Status
ready | needs_clarification | blocked

## Issues
Quality checks that failed.

## Required Clarifications
Questions that must be answered before proceeding.

## User Acceptance Confirmation
Acceptance candidates that were confirmed, rejected, or supplemented by the user.

## Assumption Conflict Result
Conflicts resolved, routed, or converted into blockers.

## Downstream Attention Handoff
Items Risk & Question Discovery must classify.

## Safe To Proceed
Whether the workflow can continue to Requirement Brief Checkpoint and Risk & Question Discovery.
```

Quality Gate failure routing:

| Failed check | Return to | Required action |
|---|---|---|
| Raw intent or goal is unclear | Raw Requirement / Intake Brief v0 | Preserve original wording, restate goal candidates, and ask only blocking clarification. |
| Scope, non-scope, users, or operators are unclear | Requirement Discovery Loop | Gather or ask for requirement-definition facts. |
| Source provenance is missing | Requirement Discovery Loop | Confirm path, repository, branch, commit, access, document source, or trust boundary. |
| Scope Inventory is incomplete or has unresolved requirement-affecting candidates | Requirement Discovery Loop | Inspect context or ask user to classify candidates. |
| Acceptance is missing, untestable, or unconfirmed | Requirement Discovery Loop | Generate candidates and get user confirmation, rejection, or supplementation. |
| Assumption conflicts with raw intent, confirmed facts, source provenance, or acceptance | Requirement Discovery Loop | Resolve the conflict, ask a blocking question, or record it as downstream attention if it belongs later. |
| Execution, verification, rollback, safety, migration, compatibility, or plan-shaping concern is hidden inside assumptions or deferred topics | Requirement Discovery Loop / Requirement Brief v1 | Move it to `Downstream Attention` for Risk Discovery classification. |
| Technical direction is unclassified | Intake Brief v0 / Requirement Discovery Loop | Classify as hard constraint, preference, proposed solution, or unknown. |
| Deferred topics contain design/spec/plan work | Requirement Brief v1 | Move those topics to `Deferred` without deciding them. |
| Tier estimate is missing or below Floor | Intake Brief v0 | Re-run the tier estimator and surface the Evidence Block; lock at or above Floor or supply `--override-floor` with reason. |

## Step 6: Requirement Brief Checkpoint

Purpose: freeze `Requirement Brief v1` as the authorized requirement input for downstream stages.

Requirement Brief Checkpoint can run only after Requirement Brief Quality Gate is `ready`. If checkpoint review finds a requirement-definition blocker, return to Requirement Discovery Loop, update the Requirement Brief, and pass Requirement Brief Quality Gate again before another checkpoint.

The checkpoint has two layers:

```text
Subagent Checkpoint Review
Main/User Requirement Brief Checkpoint
```

Subagent review may be skipped only for small, low-risk requirements where the main agent can reasonably verify the brief directly. It is required for migration, rewrite, integration, replacement, multi-project, source-provenance-sensitive, or broad-scope work.

Subagent review checks:

- Requirement goal is stable.
- Source provenance is confirmed.
- Scope Inventory is complete and categorized.
- Candidate scope items that affect requirement definition are resolved.
- Acceptance candidates are confirmed, rejected, or supplemented by the user.
- Users, operators, constraints, non-scope, and deferred topics are clear.
- Assumptions have source, impact, conflict status, and carry target.
- Downstream attention items are visible for Risk & Question Discovery.
- No requirement-definition blocker remains.

Subagent review output extends the shared checkpoint-review template in `workflow-invariants.md#shared-templates`:

```markdown
# Requirement Brief Checkpoint Review

## Status
pass | issues_found | blocked

## Scope Findings
Missing, ambiguous, or misclassified scope items.

## Source Provenance Findings
Missing or unclear source references.

## Acceptance Findings
Unconfirmed, untestable, or incomplete acceptance criteria.

## Blocker Findings
Remaining requirement-definition blockers.

## Recommendation
approve | request_changes | block
```

Main/User checkpoint output extends the shared checkpoint template in `workflow-invariants.md#shared-templates`:

```markdown
# Requirement Brief Checkpoint

## Status
approved | changes_requested | blocked

## Review Sources
Subagent checkpoint reviews and other review sources used.

## Required Changes
Requirement Brief items that must be changed before downstream handoff.

## User Confirmations
User-confirmed scope, non-scope, acceptance, constraints, and source provenance.

## Downstream Authorization
yes | no
```

Requirement Brief Checkpoint must be `approved` before Risk & Question Discovery can proceed.

## Required Outputs

The conversion process may produce these artifacts:

```text
1. Intake Brief v0
2. Requirement Discovery Notes
3. Requirement Brief v1
4. Requirement Brief Quality Gate
5. Requirement Brief Checkpoint
```

Only these artifacts are passed downstream by default:

```text
Requirement Brief v1
Requirement Brief Quality Gate
Requirement Brief Checkpoint
```

`Intake Brief v0` and `Requirement Discovery Notes` are process records used for traceability.

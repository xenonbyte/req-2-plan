# Requirement Brief

## Goal

Lower the avoidable drift between an approved PLAN and the code that executes it,
and make a fresh session resume a mid-task interruption without losing per-task
review integrity — using template-level protocol text and seed scaffolding only.
There is no new state machine, no new gate, no CLI semantic judgment, and no new
derived or persisted state; r2p continues to make no claim of formal correctness
and only minimizes avoidable drift through complete context, structured PLANs,
task boundaries, subagent review, fix loops, final review, and the archive gate.
The work is two independently shippable batches with disjoint touchpoints: Batch 1
reinforces the `r2p-execute` protocol on the claude command and the codex SKILL
surfaces (kept in lockstep and guarded by `tests/test_docs_consistency.py`
tokens); Batch 2 enriches the single PLAN seed-template source
(`stage_templates.py`) without modifying `PLAN_TASK_FIELDS` or adding
gate-required headings. Recommended order is Batch 2 first (single source, lowest
gate-interaction risk), then Batch 1.

## In-Scope

- SCOPE-IN-001 — EXE-1: the Final Whole-Branch Review section on both r2p-execute surfaces instructs the reviewer to read the full Authoritative Context Set (`02-project-context.md`, `03-requirement-brief.md`, `04-risk-discovery.md`, `05-design.md`, `06-spec.md`, `execution/progress.md`) plus `07-plan.md`, every `execution/task-N-report.md`, every `execution/task-N-review.md`, and every `Minor:` ledger entry. The final reviewer is the one role that reads `07-plan.md`; the per-task ACS exclusion of `07-plan.md` is not copied here.
- SCOPE-IN-002 — EXE-2: before dispatching each task's implementer (not only Task 1), the controller runs `git status --short -- ':!.req-to-plan'`; a non-clean code tree at a task boundary is a boundary invariant violation that stops execution until resolved, framed distinctly from the Task 1 check that additionally negotiates pre-existing user dirty work.
- SCOPE-IN-003 — EXE-3: the brief-contents description on both surfaces is corrected to list `Files`, and the task-reviewer section instructs the reviewer to compare files actually changed in the task diff against the brief's `Files` list; files outside that list need an explicit recorded justification or the review returns `CHANGES_REQUESTED`. Reviewer-protocol only — the CLI does not parse the diff or enforce a hard gate.
- SCOPE-IN-004 — EXE-4: mid-task interruption recovery by derive-on-resume, persisting nothing new. The in-progress task is the lowest-numbered unchecked (`- [ ]`) task; its BASE is reconstructed from on-disk markers (Task 1 from the ledger `Execution BASE:` line; Task N>1 from the `head7` of the immediately preceding `Task N-1: complete (commits <base7>..<head7>, review clean)` line), then `logs/task-N-diff.md` is regenerated and the task-reviewer re-dispatched idempotently. No fresh BASE is captured from HEAD and no range is inferred from `HEAD~1`; if neither marker resolves, the controller stops and asks the human for the BASE.
- SCOPE-IN-005 — EXE-5: the implementer's `execution/task-N-report.md` carries a `Verification Evidence` section (the command run and its fresh result) and a `Changed Files` section (the files the task actually changed), and does not carry a self-attested "Context Read" checklist. These are review aids, not a correctness proof; the Changed Files section feeds the EXE-3 comparison.
- SCOPE-IN-006 — Batch 1 two-surface lockstep: each EXE-1..EXE-5 addition lands identically on `r2p-execute.md` (claude) and `r2p-execute/SKILL.md` (codex), with a guard token in `tests/test_docs_consistency.py` asserting its presence on both surfaces so they cannot drift. opencode derives from the claude surface at install time; the gemini TOML keeps its lighter check.
- SCOPE-IN-007 — PLN-1: seed an optional `## Execution Readiness` pre-execution self-check section into the PLAN template (author scaffolding, not a hard gate) — e.g. requirement brief reviewed, design decisions resolved, decision requests pending none, high-risk mitigations represented in tasks, non-goals protected, verification commands executable, expected changed files listed, future-task ownership clear, no unresolved ambiguity.
- SCOPE-IN-008 — PLN-2: seed optional `Out-of-Task` and `Future Task Ownership` field lines into the PLAN-TASK body (the latter referencing `PLAN-TASK-NNN`) so an author can state what a task must not do and which sibling owns adjacent work. Optional fields only — they are not added to `PLAN_TASK_FIELDS`.
- SCOPE-IN-009 — PLN-3: enrich the PLAN-TASK `Verification` seed example into a three-part executable contract — a targeted command, the full relevant suite command, and the expected evidence. Seed text only.
- SCOPE-IN-010 — PLN-4: seed an optional `## Risk Handling` table mapping risks to the tasks that handle them; every row naming a `RISK-*` ID carries a same-line closure tag (`[ADDRESSED]`, `[DEFERRED]`, `[N/A]`, `[OUT-OF-SCOPE]`, or `[CLOSED]`) because the PLAN quality gate's Check 3 requires it, and the `RISK-*` IDs appear only in table cells, never in a `#`/`##`/`###` heading.
- SCOPE-IN-011 — PLN-5: seed PLAN-TASK granularity guidance stating one task should be completable by one implementer subagent and independently reviewable by one task-reviewer — split a task that spans too many files or behaviors; merge two only when they change one indivisible behavior.
- SCOPE-IN-012 — Batch 2 gate round-trip coverage: a test proving a PLAN seeded from the updated template and filled minimally passes the PLAN quality gate (the seeded `## Risk Handling` example row triggers neither Check 3 nor the malformed-trace-ID check), and a test proving a PLAN that omits the new optional sections and fields still passes — confirming the additive optional-section seed path does not register new required headings and leaves `PLAN_TASK_FIELDS` unchanged.

## Out-of-Scope

- SCOPE-OUT-001 — Explicit per-task BASE persistence (the rejected "Option A": a `Task N BASE:` ledger line per task). EXE-4 derives the BASE from existing markers instead and persists nothing new.
- SCOPE-OUT-002 — A new `r2p-execute-doctor` read-only health command.
- SCOPE-OUT-003 — Any `task-N-context.md` bundle, `context-manifest.json`, content hash, or drift gate.
- SCOPE-OUT-004 — CLI-side semantic correctness judgment (whether tests truly cover the requirement, whether the implementation matches the design, whether a review verdict is true).
- SCOPE-OUT-005 — Whole-repository AST, call-graph, or LSP indexing.
- SCOPE-OUT-006 — Any new multi-step approval flow or new run status.
- SCOPE-OUT-007 — A new skill or command for execution resume; resume stays inside the existing `/r2p-execute` Durable Progress section, changed only by the EXE-4 protocol text.
- SCOPE-OUT-008 — The firm code boundary (AC-6): no change to any CLI handler, `state.py`, or gate code in Batch 1, and no change to `STAGE_SCHEMA` or `PLAN_TASK_FIELDS` in Batch 2.

## Non-Goals

- Not changing the CLI/Agent boundary: the CLI keeps owning state, structure, paths, gates, ledger, and archive; the Agent keeps owning semantic understanding, implementation, tests, review, and repair. Every addition here is template prose or seed scaffolding.
- Not making any new marker machine-read: EXE-5 evidence sections, the `## Execution Readiness` self-check, and the `## Risk Handling` table are review aids and author scaffolding, never receipt-based verification that a marker is true.
- Not changing the subagent topology or the in-place single-branch execution model; EXE-2's clean-tree check observes an existing invariant rather than adding isolation.
- Not reversing the documented per-task-BASE deferral beyond what EXE-4 specifies (read-only marker reconstruction on resume).

## Assumptions

- The R2 schema gate is presence-only: `check_quality_gate` fails on a missing required heading but performs no exclusivity check, so extra PLAN headings (`## Execution Readiness`, `## Risk Handling`) are accepted (`gates.py`); the additive-heading question is resolved by code, so PLN-1 and PLN-4 sections are gate-safe.
- The task brief is the full PLAN-TASK body, so it already carries `Files`, `Skeleton`, `Steps`, `Spec References`, and `Verification`; EXE-3 needs only a wording correction and a reviewer-protocol instruction, no CLI change.
- The two `r2p-execute` orchestration targets are the claude Markdown command and the codex SKILL; opencode derives its command from the claude template at install time and the gemini TOML keeps its lighter pointer-only check.
- The ledger markers EXE-4 reads (`Execution BASE:` and `Task N: complete (commits <base7>..<head7>, review clean)`) are already produced by the existing execution loop, so derive-on-resume reads existing on-disk conventions and introduces none.
- The PLAN quality gate's Check 3 closure rule applies to the PLAN artifact: any referenced `REQ/RISK/DES/SPEC` ID, except a SPEC consumed via `Spec References`, needs a same-line closure tag; `PLAN-TASK-*` references are exempt — which is why PLN-4 requires closure tags and PLN-2's `PLAN-TASK-NNN` references are safe.

## Acceptance Criteria

- AC-1 (Batch 1 parity and content): for each of EXE-1..EXE-5, both `r2p-execute.md` and `r2p-execute/SKILL.md` carry the new instruction text and `tests/test_docs_consistency.py` has a guard token asserting its presence on both surfaces; the full pytest suite stays green.
- AC-2 (EXE-3 description fix): the brief-contents description on both surfaces lists `Files` alongside `Skeleton`, `Steps`, `Spec References`, and `Verification`.
- AC-3 (EXE-4 fail-closed): the resume text specifies BASE reconstruction from `Execution BASE:` (Task 1) and the preceding completion line's `head7` (Task N), plus an explicit stop-and-ask path with no `HEAD~1` inference and no fresh-from-HEAD BASE capture.
- AC-4 (Batch 2 gate-clean seed): a PLAN seeded from the updated template and filled minimally passes the PLAN quality gate; the seeded `## Risk Handling` example row carries a same-line closure tag and well-formed IDs, so it triggers neither Check 3 nor the malformed-trace-ID check.
- AC-5 (Batch 2 non-gating): a PLAN that omits `## Execution Readiness`, `## Risk Handling`, `Out-of-Task`, and `Future Task Ownership` still passes the quality gate as long as `## Tasks` is present, confirming the new sections and fields are optional and `PLAN_TASK_FIELDS` is unchanged.
- AC-6 (no scope leakage): no CLI, `state.py`, or gate code changes in Batch 1; no `STAGE_SCHEMA` or `PLAN_TASK_FIELDS` change in Batch 2; none of the out-of-scope items appear in the diff.

## Open Questions

- None blocking. All scoping and approach decisions were resolved during analysis: Option B (derive-on-resume) over Option A (per-task BASE persistence) for EXE-4; the reduced EXE-5 without a Context-Read checklist; the closure-tag form for PLN-4; and the additive-heading safety, confirmed by inspecting the presence-only schema gate.

## Sources

- `requirements/execution-and-plan-template-hardening.md` — the approved requirement (Batch 1 EXE-1..EXE-5, Batch 2 PLN-1..PLN-5, cross-cutting constraints, grounding facts, AC-1..AC-6).
- Touchpoint files: `tools/workflow_cli/agent_templates/claude/commands/r2p-execute.md`, `tools/workflow_cli/agent_templates/codex/skills/r2p-execute/SKILL.md`, `tools/workflow_cli/stage_templates.py`, and `tests/test_docs_consistency.py`.
- Gate anchors verified during analysis: `tools/workflow_cli/gates.py` (`check_quality_gate` presence-only schema, Check 3 closure rule, malformed-trace-ID check) and `tools/workflow_cli/stage_schema.py` (`STAGE_SCHEMA`, `PLAN_TASK_FIELDS`).
- Local archive precedent: the shipped `r2p-execute` SDD-enhancement and context-management work (FR-A* and FR-CM* runs) whose templates these batches extend.

## Trace

| This ID | Upstream | Status |
|---|---|---|
| SCOPE-IN-001 | EXE-1 (final reviewer full context) | open — carried to design, spec, plan |
| SCOPE-IN-002 | EXE-2 (per-task clean-tree check) | open — carried to design, spec, plan |
| SCOPE-IN-003 | EXE-3 (reviewer files-vs-brief) | open — carried to design, spec, plan |
| SCOPE-IN-004 | EXE-4 (derive-on-resume BASE) | open — carried to design, spec, plan |
| SCOPE-IN-005 | EXE-5 (report evidence sections) | open — carried to design, spec, plan |
| SCOPE-IN-006 | Batch 1 lockstep guard tokens | open — carried to design, spec, plan |
| SCOPE-IN-007 | PLN-1 (Execution Readiness seed) | open — carried to design, spec, plan |
| SCOPE-IN-008 | PLN-2 (optional PLAN-TASK fields) | open — carried to design, spec, plan |
| SCOPE-IN-009 | PLN-3 (Verification contract seed) | open — carried to design, spec, plan |
| SCOPE-IN-010 | PLN-4 (Risk Handling table seed) | open — carried to design, spec, plan |
| SCOPE-IN-011 | PLN-5 (granularity guidance seed) | open — carried to design, spec, plan |
| SCOPE-IN-012 | Batch 2 gate round-trip tests | open — carried to design, spec, plan |
| SCOPE-OUT-001 | per-task BASE persistence (Option A) | excluded |
| SCOPE-OUT-002 | r2p-execute-doctor command | excluded |
| SCOPE-OUT-003 | context bundle / manifest / drift gate | excluded |
| SCOPE-OUT-004 | CLI semantic correctness judgment | excluded |
| SCOPE-OUT-005 | repo AST / call-graph / LSP indexing | excluded |
| SCOPE-OUT-006 | new approval flow / run status | excluded |
| SCOPE-OUT-007 | new resume skill/command | excluded |
| SCOPE-OUT-008 | firm code boundary (no gate/schema/fields change) | excluded |

## Upstream Summary (read-only)
---
status: active
slug: execution-and-plan-template-hardening
created_at: 2026-06-29
---

# Execution-protocol and PLAN-template hardening

## Background

r2p already ships a strong requirement-to-PLAN-to-execution chain. The execution
loop (`r2p-execute`) has per-task briefs, an Authoritative Context Set, a
task-reviewer after each task, a fix loop, a final whole-branch review, and a
gated archive. The CLI/Agent boundary is healthy: the CLI owns state, structure,
paths, gates, ledger, and archive; the Agent owns semantic understanding,
implementation, tests, review, and repair.

This iteration does not change that boundary. It adds a set of small protocol and
template reinforcements that reduce avoidable execution drift and make mid-task
interruption recovery correct. There is no new state machine, no new gate, no CLI
semantic judgment, and no new derived state.

The work splits into two independent batches with different touchpoints:

- Batch 1 reinforces the execution protocol. Touchpoint:
  `tools/workflow_cli/agent_templates/claude/commands/r2p-execute.md` and
  `tools/workflow_cli/agent_templates/codex/skills/r2p-execute/SKILL.md` (the two
  surfaces must stay in lockstep), plus guard tokens in
  `tests/test_docs_consistency.py`. No CLI, state, or gate code changes.
- Batch 2 reinforces PLAN generation. Touchpoint:
  `tools/workflow_cli/stage_templates.py` (the single seed-template source). It
  does not modify `PLAN_TASK_FIELDS` and does not add gate-required headings.

The two batches are independently shippable. Recommended order is Batch 2 first
(single source, lowest gate-interaction risk), then Batch 1.

## Goal

Lower the avoidable drift between an approved PLAN and the code that executes it,
and make a fresh session resume a mid-task interruption without losing per-task
review integrity, using template-level protocol text and seed scaffolding only.
r2p continues to make no claim of formal correctness; it minimizes avoidable
drift through complete context, structured PLANs, task boundaries, subagent
review, fix loops, final review, and the archive gate.

## In-Scope

### Batch 1: execution-protocol reinforcement (`r2p-execute` surfaces)

- EXE-1: Final whole-branch reviewer reads the full upstream context.
  The Final Whole-Branch Review section must instruct the reviewer to read the
  Authoritative Context Set (`02-project-context.md`, `03-requirement-brief.md`,
  `04-risk-discovery.md`, `05-design.md`, `06-spec.md`, `execution/progress.md`)
  plus `07-plan.md`, plus every `execution/task-N-report.md`, every
  `execution/task-N-review.md`, and every `Minor:` entry in the ledger. The
  final reviewer is the one role that reads `07-plan.md`; the per-task ACS
  exclusion of `07-plan.md` must not be copied into this section.

- EXE-2: Per-task clean working-tree check.
  Before dispatching each task's implementer (not only Task 1), the controller
  runs `git status --short -- ':!.req-to-plan'`. A non-clean code tree at a task
  boundary is treated as an invariant violation (the previous task or fix wave
  left uncommitted work): stop and resolve before continuing. This is framed as
  a boundary invariant, distinct from the Task 1 check, which additionally
  negotiates pre-existing user dirty work.

- EXE-3: Reviewer checks changed files against the task brief's `Files`.
  The task brief already carries the `Files` field (the brief is the full
  PLAN-TASK body). The template's description of brief contents must be corrected
  to list `Files`. The task-reviewer section must instruct the reviewer to
  compare the files actually changed in the task diff against the brief's `Files`
  list; files outside that list require an explicit, recorded justification, or
  the review returns `CHANGES_REQUESTED`. This stays a reviewer-protocol check;
  the CLI does not parse the diff or enforce a hard gate.

- EXE-4: Correct mid-task interruption recovery (derive-on-resume, no new
  persisted state).
  On resume, the in-progress task is the lowest-numbered unchecked
  (`- [ ]`) task. For that task the controller must NOT capture a fresh BASE from
  current HEAD. It reconstructs the task's BASE from markers already on disk:
  Task 1 from the ledger's `Execution BASE:` line; Task N (N > 1) from the
  `head7` of the immediately preceding completed task's
  `Task N-1: complete (commits <base7>..<head7>, review clean)` line. It then
  regenerates `logs/task-N-diff.md` from that BASE to HEAD and re-dispatches the
  task-reviewer (idempotent: already-committed, correct work is approved as-is;
  the implementer is re-dispatched only if the review finds a gap). If neither
  marker can be resolved, the controller stops and asks the human for the BASE;
  it never infers a range from `HEAD~1`. This adds no new ledger field and no new
  persisted convention.

- EXE-5: Implementer task report carries evidence sections.
  The implementer's `execution/task-N-report.md` must contain a
  `Verification Evidence` section (the command run and its fresh result) and a
  `Changed Files` section (the files the task actually changed). It must NOT
  contain a self-attested "Context Read" checklist. These sections are review
  aids, not a correctness proof; the Changed Files section also feeds the EXE-3
  reviewer comparison.

### Batch 2: PLAN-generation reinforcement (`stage_templates.py`)

- PLN-1: `## Execution Readiness` self-check section.
  Seed an optional pre-execution self-check section into the PLAN template
  (for example: requirement brief reviewed, design decisions resolved, decision
  requests pending none, high-risk mitigations represented in tasks, non-goals
  protected, verification commands executable, expected changed files listed,
  future-task ownership clear, no unresolved ambiguity). It is scaffolding for
  the author, not a hard gate.

- PLN-2: `Out-of-Task` / `Future Task Ownership` optional fields in PLAN-TASK.
  Seed optional field lines into the PLAN-TASK body that let an author state what
  the task must not do and which sibling task owns adjacent work (referencing
  `PLAN-TASK-NNN`). These are optional fields only; they must not be added to
  `PLAN_TASK_FIELDS` (which would make them gate-required).

- PLN-3: Verification written as an executable contract.
  Enrich the PLAN-TASK `Verification` seed example into a three-part shape:
  a targeted command, the full relevant suite command, and the expected evidence.
  This sharpens the existing single-line example; it is seed-text only.

- PLN-4: `## Risk Handling` mapping table.
  Seed an optional table that maps risks to the tasks that handle them. Each row
  that names a `RISK-*` ID must carry a closure tag on the same line
  (`[ADDRESSED]`, `[DEFERRED]`, `[N/A]`, `[OUT-OF-SCOPE]`, or `[CLOSED]`),
  because the PLAN quality gate's Check 3 requires a same-line closure tag for any
  referenced upstream `REQ/RISK/DES/SPEC` ID that is not a consumed SPEC. The
  `RISK-*` IDs must appear in table cells, never in a `#`/`##`/`###` heading.

- PLN-5: PLAN-TASK granularity guidance.
  Seed authoring guidance stating that one PLAN-TASK should be completable by one
  implementer subagent and independently reviewable by one task-reviewer: split a
  task that spans too many files or behaviors; merge two tasks only when they
  change one indivisible behavior.

## Out-of-Scope (explicitly not done this iteration)

- Explicit per-task BASE persistence (the rejected "Option A": writing a
  `Task N BASE:` ledger line per task). EXE-4 derives the BASE from existing
  markers instead.
- A new `r2p-execute-doctor` read-only health command.
- Any `task-N-context.md` bundle, `context-manifest.json`, content hash, or drift
  gate.
- CLI-side semantic correctness judgment (whether tests truly cover the
  requirement, whether the implementation matches the design, whether a review
  verdict is true).
- Whole-repository AST, call-graph, or LSP indexing.
- Any new multi-step approval flow or new run status.
- A new skill or command for execution resume. Resume already works through
  `/r2p-execute`; the only resume change is the EXE-4 protocol text inside the
  existing `r2p-execute` Durable Progress section.

## Cross-cutting constraints

- Two-surface lockstep. Every Batch 1 protocol addition must land identically in
  both `r2p-execute.md` (claude) and `r2p-execute/SKILL.md` (codex), with a guard
  token in `tests/test_docs_consistency.py` so the two surfaces cannot drift.
  opencode derives from the claude surface at install time; the gemini TOML keeps
  its lighter check.
- The PLAN quality gate Check 3 closure rule applies to the PLAN artifact: any
  referenced `REQ/RISK/DES/SPEC` ID, except a SPEC consumed via `Spec References`,
  needs a same-line closure tag. `PLAN-TASK-*` references are exempt. This is why
  PLN-4 requires closure tags and why PLN-2's `PLAN-TASK-NNN` references are safe.
- Batch 2 sections are additive. `## Execution Readiness` and `## Risk Handling`
  are extra headings, not members of `STAGE_SCHEMA[Stage.PLAN]`. They must be
  seeded by a mechanism that does not register them as required headings (the seed
  renderer currently emits only required headings plus the trace skeleton, so this
  needs an optional-section path, decided at design time).
- No reversal of the documented per-task-BASE deferral beyond what EXE-4
  specifies. EXE-4 persists nothing new; it only reads existing markers on resume.

## Grounding facts verified during analysis

- The R2 schema gate is presence-only: `check_quality_gate` fails on a missing
  required heading but performs no exclusivity check, so extra PLAN headings are
  accepted (`gates.py:894-900`). The earlier "confirm extra headings are
  additive" open item is therefore resolved: PLN-1 and PLN-4 sections are safe.
- The task brief is the full PLAN-TASK body, so it already carries `Files`,
  `Skeleton`, `Steps`, `Spec References`, and `Verification`
  (`cli.py:_cmd_plan_task_brief`, body taken from the task anchor). EXE-3 needs no
  CLI change.
- `Files` is one of `PLAN_TASK_FIELDS` and is seeded by the PLAN template
  (`stage_schema.py`, `stage_templates.py`).
- Execution resume entry point is `/r2p-execute`: on an `EXECUTING` run its
  precondition gate returns `resume_execution` and the loop skips checked tasks
  (`agent_shortcuts.py:_cmd_execute`). `/r2p-execute` resolves the run from the
  on-disk active pointer, so no `--work-id` is needed unless no run is selected or
  a different run is targeted. `r2p-continue` is not the executor; on an
  `EXECUTING` run it only redirects to the execute loop
  (`agent_shortcuts.py:530-538`).

## Open Questions

None blocking. All scoping and approach decisions (Option B over Option A for
EXE-4; the reduced EXE-5 without a Context-Read checklist; closure-tag form for
PLN-4) were resolved during discussion, and the additive-heading question was
resolved by code inspection above.

## Checkpoints and acceptance

- AC-1 (Batch 1 parity and content): for each of EXE-1, EXE-2, EXE-3, EXE-4,
  EXE-5, both `r2p-execute.md` and `r2p-execute/SKILL.md` carry the new
  instruction text, and `tests/test_docs_consistency.py` has a guard token
  asserting its presence on both surfaces. The full pytest suite stays green.
- AC-2 (EXE-3 description fix): the brief-contents description in both surfaces
  lists `Files` alongside `Skeleton`, `Steps`, `Spec References`, and
  `Verification`.
- AC-3 (EXE-4 fail-closed): the resume text specifies BASE reconstruction from
  `Execution BASE:` (Task 1) and the preceding completion line's `head7`
  (Task N), and an explicit stop-and-ask path with no `HEAD~1` inference.
- AC-4 (Batch 2 gate-clean seed): a PLAN seeded from the updated template,
  filled minimally, passes the PLAN quality gate. The seeded `## Risk Handling`
  example row carries a same-line closure tag and well-formed IDs, so it triggers
  neither Check 3 nor the malformed-trace-ID check.
- AC-5 (Batch 2 non-gating): a PLAN that omits `## Execution Readiness`,
  `## Risk Handling`, `Out-of-Task`, and `Future Task Ownership` still passes the
  quality gate as long as `## Tasks` is present, confirming the new sections and
  fields are optional and `PLAN_TASK_FIELDS` is unchanged.
- AC-6 (no scope leakage): no CLI, `state.py`, or gate code changes in Batch 1;
  no `STAGE_SCHEMA` or `PLAN_TASK_FIELDS` change in Batch 2; none of the
  out-of-scope items appear in the diff.
<!-- /r2p-read-only -->

## Project Context (read-only)
# Project Context Pack

- repo_root: `/Users/xubo/x-skills/req-to-plan`
- languages: {'Python': 22201, 'JavaScript': 31}
- package_managers: npm, pip
- test_commands: ['npm test']
- entrypoints: ['tools/workflow_cli/__main__.py']
- config_files: ['requirements.txt']
- dependencies (1):
  - pyyaml>=6.0 (pip)
- source_dirs: ['bin', 'docs', 'requirements', 'tests', 'tools']
<!-- /r2p-read-only -->

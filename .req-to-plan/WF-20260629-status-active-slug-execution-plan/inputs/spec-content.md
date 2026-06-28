# Spec

## Behavior Contracts

### SPEC-EXE-001 — Final whole-branch reviewer reads the full upstream context
Implements DES-EXEC-001 [ADDRESSED]; closes SCOPE-IN-001. Applies identically to both r2p-execute surfaces.
- The `## Final Whole-Branch Review` section instructs the reviewer to read the full Authoritative Context Set — `02-project-context.md`, `03-requirement-brief.md`, `04-risk-discovery.md`, `05-design.md`, `06-spec.md`, `execution/progress.md` — plus `07-plan.md`, every `execution/task-N-report.md`, every `execution/task-N-review.md`, and every `Minor:` ledger entry.
- The final reviewer is the one role that reads `07-plan.md`; the per-task Authoritative Context Set exclusion of `07-plan.md` is not copied into this section, and the per-task ACS block keeps that exclusion unchanged.

### SPEC-EXE-002 — Per-task clean working-tree boundary invariant
Implements DES-EXEC-001 [ADDRESSED]; closes SCOPE-IN-002. Applies identically to both surfaces.
- Before dispatching each task's implementer (not only Task 1), the controller runs `git status --short -- ':!.req-to-plan'`.
- A non-clean code tree at a task boundary is treated as a boundary-invariant violation (the previous task or fix wave left uncommitted work): the controller stops and resolves it before continuing.
- This per-task boundary invariant is stated distinctly from the existing Task 1 check, which additionally negotiates pre-existing user dirty work; the Task 1 negotiation is not duplicated into the per-task boundary text.

### SPEC-EXE-003 — Reviewer checks changed files against the brief's `Files`
Implements DES-EXEC-001 [ADDRESSED]; closes SCOPE-IN-003. Applies identically to both surfaces.
- The §1 brief-contents description lists `Files` alongside `Skeleton`, `Steps`, `Spec References`, and `Verification` (AC-2).
- The task-reviewer section instructs the reviewer to compare the files actually changed in the task diff against the brief's `Files` list; a file changed outside that list requires an explicit, recorded justification, or the review returns `CHANGES_REQUESTED`.
- This is a reviewer-protocol check only; the CLI does not parse the diff and no hard gate is added.

### SPEC-EXE-004 — Mid-task interruption recovery by derive-on-resume
Implements DES-EXEC-001 [ADDRESSED]; closes SCOPE-IN-004. Applies identically to both surfaces. Lives in the existing `## Durable Progress` section; persists no new state.
- On resume, the in-progress task is the lowest-numbered unchecked (`- [ ]`) task.
- For that task the controller does NOT capture a fresh BASE from current HEAD. It reconstructs the task's BASE from markers already on disk: Task 1 from the ledger `Execution BASE:` line; Task N (N > 1) from the `head7` of the immediately preceding `Task N-1: complete (commits <base7>..<head7>, review clean)` line.
- It then regenerates `logs/task-N-diff.md` from that BASE to HEAD and re-dispatches the task-reviewer idempotently: an already-committed, correct task is approved as-is; the implementer is re-dispatched only if the review finds a gap.
- If neither marker can be resolved, the controller stops and asks the human for the BASE. It never infers a range from `HEAD~1` and never captures a fresh BASE from HEAD on resume.

### SPEC-EXE-005 — Implementer task report carries evidence sections
Implements DES-EXEC-001 [ADDRESSED]; closes SCOPE-IN-005. Applies identically to both surfaces.
- The implementer's `execution/task-N-report.md` contains a `Verification Evidence` section (the command run and its fresh result) and a `Changed Files` section (the files the task actually changed).
- The report does NOT contain a self-attested "Context Read" checklist.
- These sections are review aids, not a correctness proof; the `Changed Files` section also feeds the SPEC-EXE-003 reviewer comparison.

### SPEC-GUARD-001 — Batch 1 two-surface lockstep token guard
Implements DES-GUARD-001 [ADDRESSED]; closes SCOPE-IN-006.
- `tests/test_docs_consistency.py` asserts that each of EXE-1..EXE-5 has a distinctive load-bearing token present on BOTH r2p-execute surfaces (`claude/commands/r2p-execute.md` and `codex/skills/r2p-execute/SKILL.md`); deleting any required token from either surface fails the test.
- Each guard token is distinctive — absent from both templates before this edit — so it proves the new prose landed rather than matching incidental pre-existing text.
- The existing SDD / FR-A / FR-CM token sets and the no-`r2p-gap-open` assertions are preserved.
- Suggested token set (exact literals finalized in the PLAN against the authored prose): EXE-1 a final-review whole-context literal naming `07-plan.md` plus per-task reports/reviews and `Minor:`; EXE-2 a per-task-boundary clean-tree literal (e.g. distinct from the Task-1 wording); EXE-3 the brief-contents `Files` correction literal and a files-vs-`Files` reviewer literal; EXE-4 a derive-on-resume literal (lowest-numbered unchecked task / preceding completion `head7`); EXE-5 the `Verification Evidence` and `Changed Files` section names.

### SPEC-SEED-001 — Optional-section seed path and the five PLN seeds in stage_templates.py
Implements DES-SEED-001 [ADDRESSED]; closes SCOPE-IN-007, SCOPE-IN-008, SCOPE-IN-009, SCOPE-IN-010, SCOPE-IN-011.
- A per-stage optional-section source (e.g. `_OPTIONAL_SECTIONS: dict[Stage, str]`) is emitted by `template_for` after the required-heading bodies and before `_TRACE_SKELETON`. `required_headings`, `STAGE_SCHEMA`, and `PLAN_TASK_FIELDS` are unchanged, so no new heading is gate-required and no new field is gate-required.
- PLN-1: the PLAN optional sections include `## Execution Readiness`, a concrete optional self-check checklist (requirement brief reviewed; design decisions resolved; decision requests pending none; high-risk mitigations represented in tasks; non-goals protected; verification commands executable; expected changed files listed; future-task ownership clear; no unresolved ambiguity). Author scaffolding, not a hard gate.
- PLN-4: the PLAN optional sections include `## Risk Handling`, a risk-to-task table with a header row and exactly one example data row `| RISK-EXAMPLE-001 | PLAN-TASK-001 | [ADDRESSED] |`. Every row naming a `RISK-*` ID carries a same-line closure tag (`[ADDRESSED]`, `[DEFERRED]`, `[N/A]`, `[OUT-OF-SCOPE]`, or `[CLOSED]`); `RISK-*` IDs appear only in table cells, never in a `#`/`##`/`###` heading.
- PLN-2: the PLAN-TASK seed body gains optional `Out-of-Task:` and `Future Task Ownership:` field lines with gate-clean illustrative values; `Future Task Ownership` references the `PLAN-TASK-NNN` form. These optional fields are NOT added to `PLAN_TASK_FIELDS`.
- PLN-3: the required `Verification` seed example is enriched into a three-part executable contract — a targeted command, the full relevant suite command, and the expected evidence. `Verification` stays the author-supplied required field; only its example is enriched.
- PLN-5: a concise PLAN-TASK granularity-guidance HTML comment is seeded under `## Tasks` — one PLAN-TASK should be completable by one implementer subagent and independently reviewable by one task-reviewer; split a task spanning too many files or behaviors; merge two only when they change one indivisible behavior.
- Gate-clean invariants: every seeded optional element is free of placeholder tokens (no fill-in / TBD / `???` / `to be decided`), uses only well-formed trace IDs, and lives outside the `### PLAN-TASK` bodies (so the last task body terminates at `## Execution Readiness`). A PLAN seeded from the updated template and filled minimally passes the PLAN quality gate (AC-4), and omitting the optional sections and fields leaves a PLAN that still passes with `## Tasks` present (AC-5).

### SPEC-SEEDTEST-001 — Batch 2 gate round-trip coverage
Implements DES-SEEDTEST-001 [ADDRESSED]; closes SCOPE-IN-012.
- An AC-4 test renders the updated PLAN template, fills the required `## Tasks` minimally (with a consistent minimal upstream fixture: a SPEC that defines and is consumed by the task, a carried SCOPE-IN, closed risks, and a usable Context Pack for standard tier), and asserts the PLAN quality gate passes — confirming the seeded `## Risk Handling` row triggers neither the Check 3 closure failure nor the malformed-trace-ID check.
- An AC-5 test strips `## Execution Readiness`, `## Risk Handling`, `Out-of-Task`, and `Future Task Ownership` and asserts the gate still passes with `## Tasks` present, proving the new sections and fields are optional and `PLAN_TASK_FIELDS` is unchanged.

## API / Data / Config Contracts

No CLI argument, JSON payload, exit code, run status, state transition, gate, artifact schema, or `PLAN_TASK_FIELDS` change. The only programmatic surface touched is the internal `stage_templates.template_for` rendering (SPEC-SEED-001): its output for the PLAN stage gains trailing optional sections, while its output for every other stage is byte-identical to today (the optional-section source is empty for non-PLAN stages). The seeded PLAN's structural contract (`## Tasks`, the seven `PLAN_TASK_FIELDS`, the trace skeleton) is preserved; the additions are appended, optional, and removable.

## External Documentation Checked

N/A — no external dependencies

The change is entirely internal: template prose on the r2p-execute surfaces, an additive seed-rendering path in `stage_templates.py` (Python stdlib only), and pytest assertions. No new runtime dependency is introduced and no third-party library, API, SDK, or CLI is consulted by the implementation. The PLAN granularity, derive-on-resume, and clean-tree disciplines are r2p's own conventions, verified against the in-repo code, not an external source.

## Test Matrix

| Test | SPEC | Expectation |
|---|---|---|
| EXE-1 final-review full-context tokens on both surfaces | SPEC-EXE-001, SPEC-GUARD-001 | the final-review section names `07-plan.md`, the ACS read set, per-task reports/reviews, and `Minor:`; deleting the token on either surface fails |
| EXE-2 per-task boundary clean-tree token on both surfaces | SPEC-EXE-002, SPEC-GUARD-001 | a per-task-boundary clean-tree literal distinct from the Task-1 check is present on both surfaces |
| EXE-3 `Files` description + reviewer files-vs-`Files` tokens | SPEC-EXE-003, SPEC-GUARD-001 | §1 brief description lists `Files`; reviewer compares changed files vs `Files`; both surfaces |
| EXE-4 derive-on-resume tokens on both surfaces | SPEC-EXE-004, SPEC-GUARD-001 | lowest-numbered unchecked task + preceding-completion `head7` reconstruction + no-`HEAD~1`/stop-and-ask present on both surfaces |
| EXE-5 report evidence-section tokens on both surfaces | SPEC-EXE-005, SPEC-GUARD-001 | `Verification Evidence` and `Changed Files` present, no Context-Read checklist, both surfaces |
| existing SDD / FR-A / FR-CM token sets still pass | SPEC-GUARD-001 | unchanged guards stay green; no `r2p-gap-open` on either surface |
| seeded PLAN, filled minimally, passes the quality gate | SPEC-SEED-001, SPEC-SEEDTEST-001 | gate passes; Risk Handling row clears Check 3 and the malformed-ID check (AC-4) |
| seeded PLAN with optional sections/fields omitted passes | SPEC-SEED-001, SPEC-SEEDTEST-001 | gate passes with `## Tasks` present (AC-5) |
| non-PLAN stage templates byte-identical | SPEC-SEED-001 | `template_for` output unchanged for non-PLAN stages |
| full pytest suite stays green | all | no pre-existing test regresses |

## Non-goals

- SCOPE-OUT-001: no per-task BASE persistence; SPEC-EXE-004 reconstructs the BASE from existing markers and persists nothing new.
- SCOPE-OUT-002 / SCOPE-OUT-003: no `r2p-execute-doctor` command and no `task-N-context.md` bundle, `context-manifest.json`, content hash, or drift gate.
- SCOPE-OUT-004: no CLI-side semantic correctness judgment; the EXE-5 evidence, `## Execution Readiness`, and `## Risk Handling` markers are never machine-asserted as true.
- SCOPE-OUT-005 / SCOPE-OUT-006: no whole-repo AST / call-graph / LSP indexing, and no new approval flow or run status.
- SCOPE-OUT-007: no new resume skill or command; SPEC-EXE-004 lives in the existing `/r2p-execute` Durable Progress section.
- SCOPE-OUT-008: no CLI, `state.py`, or gate change in Batch 1; no `STAGE_SCHEMA` or `PLAN_TASK_FIELDS` change in Batch 2.

## PLAN Handoff

Three PLAN tasks, numbered contiguously from 1, consuming every SPEC ID above. Batch 2 ships first (single source, lowest gate-interaction risk), then Batch 1; each task is independently mergeable.
- PLAN-TASK-1 (Batch 2) — add the optional-section seed path and the five PLN seeds to `tools/workflow_cli/stage_templates.py` (Change Type: modify). Spec References: SPEC-SEED-001. Carries SCOPE-IN-007, SCOPE-IN-008, SCOPE-IN-009, SCOPE-IN-010, SCOPE-IN-011.
- PLAN-TASK-2 (Batch 2) — add the gate round-trip tests (AC-4 gate-clean seed, AC-5 non-gating omission) in `tests/` (Change Type: modify). Spec References: SPEC-SEEDTEST-001. Carries SCOPE-IN-012.
- PLAN-TASK-3 (Batch 1) — add the EXE-1..EXE-5 prose identically to both r2p-execute surfaces and extend `tests/test_docs_consistency.py` with the matching per-EXE guard tokens, written red-first against the new prose (Change Type: modify). Spec References: SPEC-EXE-001, SPEC-EXE-002, SPEC-EXE-003, SPEC-EXE-004, SPEC-EXE-005, SPEC-GUARD-001. Carries SCOPE-IN-001, SCOPE-IN-002, SCOPE-IN-003, SCOPE-IN-004, SCOPE-IN-005, SCOPE-IN-006.

## Trace

| This ID | Upstream | Status |
|---|---|---|
| SPEC-EXE-001 | DES-EXEC-001, SCOPE-IN-001 | open — consumed by PLAN-TASK-3 |
| SPEC-EXE-002 | DES-EXEC-001, SCOPE-IN-002 | open — consumed by PLAN-TASK-3 |
| SPEC-EXE-003 | DES-EXEC-001, SCOPE-IN-003 | open — consumed by PLAN-TASK-3 |
| SPEC-EXE-004 | DES-EXEC-001, SCOPE-IN-004 | open — consumed by PLAN-TASK-3 |
| SPEC-EXE-005 | DES-EXEC-001, SCOPE-IN-005 | open — consumed by PLAN-TASK-3 |
| SPEC-GUARD-001 | DES-GUARD-001, SCOPE-IN-006 | open — consumed by PLAN-TASK-3 |
| SPEC-SEED-001 | DES-SEED-001, SCOPE-IN-007, SCOPE-IN-008, SCOPE-IN-009, SCOPE-IN-010, SCOPE-IN-011 | open — consumed by PLAN-TASK-1 |
| SPEC-SEEDTEST-001 | DES-SEEDTEST-001, SCOPE-IN-012 | open — consumed by PLAN-TASK-2 |

## Upstream Summary (read-only)
# Design

## Design Summary

Deliver the two batches as template prose plus seed scaffolding, touching no gate,
state, schema, or CLI handler. Batch 1 reinforces the `r2p-execute` orchestration
body identically on the claude command and the codex SKILL: the final
whole-branch reviewer is told to read the full upstream context including
`07-plan.md` (EXE-1), a per-task boundary clean-tree invariant is added distinct
from the Task 1 check (EXE-2), the task-reviewer compares changed files against
the brief's `Files` and the §1 brief-contents description is corrected to list
`Files` (EXE-3), mid-task interruption resume reconstructs the in-progress task's
BASE from existing on-disk markers instead of capturing fresh HEAD (EXE-4), and
the implementer report carries `Verification Evidence` and `Changed Files`
sections with no self-attested Context-Read checklist (EXE-5). A docs-consistency
token guard pins each addition on both surfaces. Batch 2 adds an optional-section
seed path to the single seed source `stage_templates.py` so the PLAN template can
emit `## Execution Readiness` and `## Risk Handling` plus optional PLAN-TASK
fields and richer Verification/granularity guidance, without registering any new
required heading in `STAGE_SCHEMA` or extending `PLAN_TASK_FIELDS`; a round-trip
gate test proves the seed is both gate-clean when filled minimally and still
gate-clean when the optional sections are omitted. The batches are independently
shippable; Batch 2 ships first (single source, lowest gate-interaction risk).

## Current Code Evidence

- `tools/workflow_cli/stage_templates.py` — `template_for` iterates only `required_headings(stage, tier_base)` (from `STAGE_SCHEMA`), appends each heading's `_HEADING_BODY` entry, then appends `_TRACE_SKELETON`. There is **no path to emit a non-required (optional) section**, which is exactly the gap Batch 2 must fill without touching `required_headings`. The PLAN `## Tasks` body in `_HEADING_BODY` already seeds the seven `PLAN_TASK_FIELDS` and a single-line guided `Verification:` placeholder example — the line PLN-3 enriches.
- `tools/workflow_cli/stage_schema.py` — `STAGE_SCHEMA[Stage.PLAN]` is `["## Tasks"]` for both tiers and `PLAN_TASK_FIELDS` is the fixed seven-field tuple. Both must stay unchanged (SCOPE-OUT-008); the new sections and fields are additive and optional.
- `tools/workflow_cli/gates.py` — `check_quality_gate` Check 3 (`_find_ids_without_closure`, closure tags `[ADDRESSED] [DEFERRED] [N/A] [OUT-OF-SCOPE] [CLOSED]`) requires any referenced `REQ/RISK/DES/SPEC` ID that is not a consumed SPEC to carry a same-line closure tag; `_check_stage_schema` runs the malformed-trace-ID scan (`_TRACE_ID_CANDIDATE_RE` vs `_VALID_TRACE_ID_RE`) and is **presence-only with no exclusivity check**, so extra PLAN headings are accepted. This is why the seeded `## Risk Handling` row must carry a same-line closure tag and well-formed IDs, and why PLN-1/PLN-4 sections are gate-safe.
- `tools/workflow_cli/agent_templates/claude/commands/r2p-execute.md` (and its codex twin `tools/workflow_cli/agent_templates/codex/skills/r2p-execute/SKILL.md`): the §1 brief-contents sentence lists `Skeleton`, `Steps`, `Spec References`, and `Verification` but **omits `Files`** (the EXE-3 description fix); the clean-tree `git status --short -- ':!.req-to-plan'` check exists **only before Task 1** in `## In-Place Execution` (EXE-2 adds the per-task boundary invariant); the `## Authoritative Context Set` block deliberately **excludes `07-plan.md`** for per-task roles (EXE-1 must add the full-context read to the final-review section without copying that exclusion); the §2 implementer dispatch names a `execution/task-N-report.md` path but does not specify the report's internal sections (EXE-5); and `## Durable Progress` resumes only the final-review `Execution BASE:` line, with no mid-task in-progress-task BASE reconstruction (EXE-4), while §2 says "Record BASE (`git rev-parse HEAD`)" which on resume would capture a fresh HEAD.
- `tests/test_docs_consistency.py` — `test_execute_surfaces_carry_sdd_orchestration_tokens` and sibling guards (`test_execute_surfaces_block_dirty_code_tree_before_task_loop`, `test_execute_surfaces_persist_execution_base_for_resume`, `test_execute_surfaces_hand_authoritative_context_set`) are the token-gate pattern DES-GUARD-001 extends; the ACS guard's forbidden-token set is only `Scene-setting context` and `` `r2p-gap-open` ``, so adding a `07-plan.md` read to the final review does not trip it.

## Requirements Coverage

| Scope item | Design component |
|---|---|
| SCOPE-IN-001 | DES-EXEC-001 |
| SCOPE-IN-002 | DES-EXEC-001 |
| SCOPE-IN-003 | DES-EXEC-001 |
| SCOPE-IN-004 | DES-EXEC-001 |
| SCOPE-IN-005 | DES-EXEC-001 |
| SCOPE-IN-006 | DES-GUARD-001 |
| SCOPE-IN-007 | DES-SEED-001 |
| SCOPE-IN-008 | DES-SEED-001 |
| SCOPE-IN-009 | DES-SEED-001 |
| SCOPE-IN-010 | DES-SEED-001 |
| SCOPE-IN-011 | DES-SEED-001 |
| SCOPE-IN-012 | DES-SEEDTEST-001 |

## Options Considered

- Batch 2 seed mechanism — Option A (chosen): a per-stage `_OPTIONAL_SECTIONS` mapping in `stage_templates.py`, appended by `template_for` after the required-heading bodies and before `_TRACE_SKELETON`. It leaves `STAGE_SCHEMA` / `required_headings` untouched (so the gate never treats the new headings as required), keeps the single seed source, and lets the seeded content be gate-clean as authored. Option B — add the headings to `STAGE_SCHEMA[Stage.PLAN]`: rejected, it makes them required (R2.1 would fail any PLAN that omits them, breaking AC-5 and SCOPE-OUT-008). Option C — inline the sections into the `## Tasks` `_HEADING_BODY` value: rejected, it buries top-level `##` sections inside the Tasks body region and entangles them with PLAN-TASK body parsing.
- Optional-section placement — chosen: emit them after `## Tasks` and before `## Trace`, so they terminate the task list cleanly (`_iter_plan_task_bodies` bounds the last task at the next heading) and the trace table stays the final structural element, consistent with every other stage.
- PLN-2 / PLN-3 / PLN-5 shape — chosen: seed `Out-of-Task` and `Future Task Ownership` as optional field lines inside the PLAN-TASK body with gate-clean illustrative values (referencing the `PLAN-TASK-NNN` guidance form, never added to `PLAN_TASK_FIELDS`); keep the required `Verification` field a guided author-supplied placeholder but enrich its example into the three-part contract; seed PLN-5 granularity guidance as a concise HTML comment under `## Tasks`.
- EXE-4 resume mechanism — already settled upstream: Option B (derive-on-resume from existing markers) over the rejected Option A (a persisted per-task `Task N BASE:` ledger line, SCOPE-OUT-001). The design only encodes the derive-on-resume protocol text; it persists nothing new.

## Chosen Design

### DES-EXEC-001 — Batch 1 execution-protocol reinforcement on both r2p-execute surfaces
The five EXE edits land identically in `r2p-execute.md` and `r2p-execute/SKILL.md`. EXE-1: the `## Final Whole-Branch Review` section instructs the reviewer to read the full Authoritative Context Set (`02-project-context.md`, `03-requirement-brief.md`, `04-risk-discovery.md`, `05-design.md`, `06-spec.md`, `execution/progress.md`) plus `07-plan.md`, every `execution/task-N-report.md`, every `execution/task-N-review.md`, and every `Minor:` ledger entry; the final reviewer is the one role that reads `07-plan.md`, and the per-task ACS exclusion of `07-plan.md` is not copied here. EXE-2: before each task's implementer dispatch (not only Task 1), the controller runs `git status --short -- ':!.req-to-plan'`; a non-clean code tree at a task boundary is a boundary-invariant violation that stops execution until resolved, framed distinctly from the existing Task 1 check that additionally negotiates pre-existing user dirty work. EXE-3: the §1 brief-contents description is corrected to list `Files` alongside `Skeleton`, `Steps`, `Spec References`, and `Verification`, and the task-reviewer section instructs the reviewer to compare files actually changed in the task diff against the brief's `Files` list — files outside that list need an explicit recorded justification or the review returns `CHANGES_REQUESTED` (reviewer-protocol only; no CLI diff parsing). EXE-4: on resume the in-progress task is the lowest-numbered unchecked `- [ ]` task; its BASE is reconstructed from existing markers — Task 1 from the ledger `Execution BASE:` line, Task N>1 from the `head7` of the preceding `Task N-1: complete (commits <base7>..<head7>, review clean)` line — then `logs/task-N-diff.md` is regenerated and the task-reviewer re-dispatched idempotently; the controller never captures a fresh BASE from HEAD, never infers from `HEAD~1`, and stops to ask the human when neither marker resolves. EXE-5: the implementer `execution/task-N-report.md` carries a `Verification Evidence` section (the command run and its fresh result) and a `Changed Files` section (the files the task actually changed), and must not carry a self-attested Context-Read checklist; these are review aids and the Changed Files section feeds the EXE-3 comparison. Addresses RISK-RESUME-001 [ADDRESSED], RISK-TREE-001 [ADDRESSED], RISK-TRUST-001 [ADDRESSED], RISK-SCOPE-001 [ADDRESSED], RISK-DRIFT-001 [ADDRESSED].

### DES-GUARD-001 — Batch 1 two-surface lockstep token guard
Extend `tests/test_docs_consistency.py` with a guard token per EXE-1..EXE-5 (each a distinctive literal absent from both templates before the edit) asserted on both r2p-execute surfaces, while preserving the existing SDD / FR-A / FR-CM token sets and the no-`r2p-gap-open` assertion. Dropping any EXE addition from either surface fails the suite; opencode re-derives from the claude surface at install time and the gemini TOML keeps its lighter pointer-only check. Addresses RISK-DRIFT-001 [ADDRESSED].

### DES-SEED-001 — Batch 2 optional-section seed path in stage_templates.py
Add a per-stage `_OPTIONAL_SECTIONS` mapping and emit it from `template_for` after the required-heading bodies and before `_TRACE_SKELETON`, leaving `STAGE_SCHEMA` and `PLAN_TASK_FIELDS` untouched. For the PLAN stage, seed: PLN-1 `## Execution Readiness` as a concrete optional self-check checklist (requirement brief reviewed, design decisions resolved, decision requests pending none, high-risk mitigations represented in tasks, non-goals protected, verification commands executable, expected changed files listed, future-task ownership clear, no unresolved ambiguity); PLN-4 `## Risk Handling` as an optional risk-to-task table whose single example row carries a same-line closure tag and well-formed IDs in cells only — `| RISK-EXAMPLE-001 | PLAN-TASK-001 | [ADDRESSED] |` — never in a heading; PLN-2 optional `Out-of-Task` and `Future Task Ownership` field lines inside the PLAN-TASK body (the latter referencing the `PLAN-TASK-NNN` form), gate-clean and not added to `PLAN_TASK_FIELDS`; PLN-3 the required `Verification` example enriched into a three-part contract (a targeted command, the full relevant suite command, and the expected evidence); PLN-5 a concise granularity-guidance HTML comment under `## Tasks`. All seeded optional content is free of fill-in/placeholder tokens so a minimally-filled PLAN passes the gate. Addresses RISK-SEED-001 [ADDRESSED], RISK-TRUST-001 [ADDRESSED], RISK-SCOPE-001 [ADDRESSED].

### DES-SEEDTEST-001 — Batch 2 gate round-trip coverage
Add a test that renders the updated PLAN template, fills the required `## Tasks` minimally, and asserts the PLAN quality gate passes — confirming the seeded `## Risk Handling` row triggers neither Check 3 nor the malformed-trace-ID check (AC-4) — plus a test that strips `## Execution Readiness`, `## Risk Handling`, `Out-of-Task`, and `Future Task Ownership` and asserts the gate still passes with `## Tasks` present (AC-5), proving the new sections and fields are optional and `PLAN_TASK_FIELDS` is unchanged. Addresses RISK-SEED-001 [ADDRESSED].

## Decision Requests

none

## Rollback

Pure additive template prose, seed scaffolding, and tests; there is no state, schema, or data migration, so there is nothing to roll back beyond the code. Batch 1 (DES-EXEC-001, DES-GUARD-001) and Batch 2 (DES-SEED-001, DES-SEEDTEST-001) each revert independently with a single `git revert`. An execution run already in flight keeps working after a Batch 1 revert because the prior orchestration prose still functions, and a PLAN freshly seeded after a Batch 2 revert simply lacks the optional sections — both gate-clean either way.

## Observability

`pytest` is the only regression signal: the DES-GUARD-001 token assertions on both surfaces and the DES-SEEDTEST-001 round-trip gate test in `tests/`. The EXE-5 `Verification Evidence` / `Changed Files` sections, the `## Execution Readiness` self-check, and the `## Risk Handling` table are human-observable in the run's `execution/` reports and the PLAN artifact respectively; none is machine-read. No runtime metrics or logging are added — this is a CLI tool with no server.

## SPEC Handoff

The SPEC must pin one `SPEC-*` ID per behavior so PLAN tasks can consume them:
- EXE-1..EXE-5 each as a behavior contract for the prose that must appear on both surfaces: the final-reviewer full-context read set (incl. `07-plan.md`, task reports/reviews, `Minor:` entries); the per-task boundary clean-tree invariant distinct from the Task 1 check; the reviewer files-vs-`Files` comparison plus the §1 `Files` description correction; the derive-on-resume BASE reconstruction with its fail-closed stop-and-ask and no-`HEAD~1`/no-fresh-HEAD rule; and the report `Verification Evidence` + `Changed Files` sections with the Context-Read-checklist prohibition.
- The Batch 1 docs-consistency token-guard contract (a distinctive per-EXE token on both surfaces; exact literals finalized in the PLAN against the authored prose).
- The Batch 2 seed-template behavior: the optional-section emission path that does not register required headings, and the gate-clean shape of each PLN seed (closure-tagged `## Risk Handling` row, well-formed IDs in cells, no fill-in tokens in optional content, optional PLAN-TASK fields outside `PLAN_TASK_FIELDS`, the three-part Verification example, the PLN-5 guidance comment).
- The Batch 2 round-trip test matrix: AC-4 (minimally-filled seeded PLAN passes; Risk Handling row clears Check 3 and the malformed-ID check) and AC-5 (PLAN omitting the optional sections/fields still passes with `## Tasks` present).

## Trace

| This ID | Upstream | Status |
|---|---|---|
| DES-EXEC-001 | SCOPE-IN-001, SCOPE-IN-002, SCOPE-IN-003, SCOPE-IN-004, SCOPE-IN-005 | open — carried to spec, plan |
| DES-GUARD-001 | SCOPE-IN-006 | open — carried to spec, plan |
| DES-SEED-001 | SCOPE-IN-007, SCOPE-IN-008, SCOPE-IN-009, SCOPE-IN-010, SCOPE-IN-011 | open — carried to spec, plan |
| DES-SEEDTEST-001 | SCOPE-IN-012 | open — carried to spec, plan |
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

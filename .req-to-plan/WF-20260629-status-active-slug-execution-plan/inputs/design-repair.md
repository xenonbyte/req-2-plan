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

## Upstream Summary (read-only)
# Risk Discovery

## Risks

### RISK-DRIFT-001 — Batch 1 prose lands on one r2p-execute surface but not the other
The five EXE additions must land identically on the claude command (`r2p-execute.md`) and the codex SKILL (`r2p-execute/SKILL.md`). A surface edited in isolation, or a guard token chosen so loosely that it matches incidental pre-existing text, lets the two surfaces silently diverge — the exact failure the two-surface lockstep constraint exists to prevent.
Status: mitigated

### RISK-SEED-001 — A PLAN seed-template change breaks the PLAN quality gate it seeds
Batch 2 adds the `## Execution Readiness` and `## Risk Handling` headings, optional PLAN-TASK fields, and an enriched Verification example to the single seed source. A seeded `## Risk Handling` row carrying a bare `RISK-*` ID with no same-line closure tag, a malformed example ID, or an accidental registration of the new headings as required would make every freshly seeded PLAN fail its own quality gate (Check 3 closure, the malformed-trace-ID check, or required-heading presence).
Status: mitigated

### RISK-RESUME-001 — Derive-on-resume reconstructs the wrong BASE
EXE-4 reconstructs the in-progress task's BASE from on-disk markers rather than capturing current HEAD. If the resume text lets the controller fall back to `HEAD~1`, capture a fresh BASE from HEAD, or mis-read the preceding completion line's `head7`, the regenerated `logs/task-N-diff.md` covers the wrong range and the task-reviewer reviews the wrong change — worse than no resume protocol at all.
Status: mitigated

### RISK-TRUST-001 — A new marker is misread as machine-enforced verification
The EXE-5 report evidence sections, the `## Execution Readiness` self-check, and the `## Risk Handling` table are author and review aids. If a later change wired a gate to assert these markers are true, it would cross the deliberate trust/audit boundary the project holds — the agent adjudicates and the machine only audits the presence and structure of the markers the agent produces.
Status: mitigated

### RISK-SCOPE-001 — The change leaks into out-of-scope code
Editing template prose and the seed source sits next to gate, state, and schema code. A careless edit could touch a CLI handler, `state.py`, a gate function, `STAGE_SCHEMA`, or `PLAN_TASK_FIELDS` — exactly the firm boundary SCOPE-OUT-008 forbids — or drift toward an explicitly excluded item such as per-task BASE persistence, a doctor command, or a context manifest.
Status: mitigated

### RISK-TREE-001 — The EXE-2 clean-tree check produces false invariant violations
EXE-2 runs `git status --short -- ':!.req-to-plan'` before each task. If the pathspec or framing is wrong, the run's own `.req-to-plan` ledger writes, or legitimately negotiated pre-existing user dirty work at Task 1, could be misread as an uncommitted-code invariant violation and wrongly halt execution.
Status: mitigated

## Boundaries

- Files touched: the two `r2p-execute` surfaces (`tools/workflow_cli/agent_templates/claude/commands/r2p-execute.md` and `tools/workflow_cli/agent_templates/codex/skills/r2p-execute/SKILL.md`), the single PLAN seed source `tools/workflow_cli/stage_templates.py`, and the tests `tests/test_docs_consistency.py` plus a Batch 2 gate round-trip test.
- Firm boundary (SCOPE-OUT-008): no edit to any CLI handler, `state.py`, or gate function in Batch 1; no edit to `STAGE_SCHEMA` or `PLAN_TASK_FIELDS` in Batch 2.
- Every addition is template prose or seed scaffolding read by humans and the existing presence gates; no new machine gate, run status, transition, or persisted state is introduced.
- opencode derives from the claude surface at install time and gemini keeps its lighter pointer-only check; neither is authored independently here.

## Scope Overflow Risks

- Temptation to persist the resume BASE as a new `Task N BASE:` ledger line while implementing EXE-4 — excluded by SCOPE-OUT-001; EXE-4 reads existing markers only.
- Temptation to add a machine gate that reads the EXE-5 evidence or the `## Execution Readiness` self-check as truth — excluded by SCOPE-OUT-004 and the trust/audit boundary.
- Temptation to register `## Execution Readiness` / `## Risk Handling` as required `STAGE_SCHEMA` headings, or to add the optional PLAN-TASK fields to `PLAN_TASK_FIELDS` — excluded by SCOPE-OUT-008; they must stay optional.
- Temptation to broadly refactor the r2p-execute templates while editing the dispatch and review sections — bounded by the docs-consistency token gate and the Batch 1 no-code-change boundary.

## Mitigations

- RISK-DRIFT-001: every EXE addition is mirrored on both surfaces in the same pass and pinned by a distinctive guard token in `tests/test_docs_consistency.py` (a literal absent from both templates before the edit), so dropping it on either surface fails the suite; opencode re-derives from the claude surface at install time.
- RISK-SEED-001: the seeded `## Risk Handling` example row carries a same-line closure tag and well-formed `RISK-*` / `PLAN-TASK-*` IDs in table cells only (never in a heading); the new sections are emitted through an optional-section seed path that does not touch `STAGE_SCHEMA`; and a round-trip test (SCOPE-IN-012) asserts both a minimally-filled seeded PLAN and a PLAN omitting the optional sections pass the quality gate.
- RISK-RESUME-001: the EXE-4 text fixes the BASE source explicitly (Task 1 from the ledger `Execution BASE:` line, Task N from the preceding completion line's `head7`), forbids `HEAD~1` inference and fresh-from-HEAD capture, and stops to ask the human when neither marker resolves; the re-dispatch is idempotent so a correct already-committed task is approved as-is.
- RISK-TRUST-001: the new markers stay inert to every gate and no gate is wired to them; the requirement's Non-Goals and SCOPE-OUT-004 record the boundary, so the final-review and completion gates remain presence / audit checks.
- RISK-SCOPE-001 and RISK-TREE-001: the diff is held to the listed prose, seed, and test files with no gate, state, schema, or field edit; EXE-2 uses the `:!.req-to-plan` pathspec so the run's own ledger writes are excluded, and the Task 1 check (which negotiates pre-existing user dirty work) is kept distinct from the per-task boundary invariant; the full pytest suite staying green is the regression signal.

## Trace

| This ID | Upstream | Status |
|---|---|---|
| RISK-DRIFT-001 | SCOPE-IN-006 | mitigated |
| RISK-SEED-001 | SCOPE-IN-007, SCOPE-IN-008, SCOPE-IN-009, SCOPE-IN-010, SCOPE-IN-012 | mitigated |
| RISK-RESUME-001 | SCOPE-IN-004 | mitigated |
| RISK-TRUST-001 | SCOPE-IN-005, SCOPE-IN-007, SCOPE-IN-010, SCOPE-OUT-004 | mitigated |
| RISK-SCOPE-001 | SCOPE-OUT-008 | mitigated |
| RISK-TREE-001 | SCOPE-IN-002 | mitigated |
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

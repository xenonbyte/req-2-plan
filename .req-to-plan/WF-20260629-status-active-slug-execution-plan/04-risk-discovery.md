---
r2p_stage: risk_discovery
r2p_version: 1
r2p_status: approved
r2p_created_at: 2026-06-28T20:12:23.367941+00:00
r2p_updated_at: 2026-06-28T20:12:30.139065+00:00
---

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

## Upstream Summary (read-only)
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

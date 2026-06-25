# Risk Discovery

## Risks

### RISK-GATE-001 — Prose or brief-handoff accidentally alters existing gate or checkbox-flip behavior
The FR-CM changes are template prose plus one read-only command, but they sit next to the checkbox-flip rule and the completion / final-review gates. A careless edit could change a gate's behavior or the literal IDs the ledger gate audits.
Status: mitigated

### RISK-CTX-001 — Bounded-read brief returns the wrong or truncated task body
FR-CM1 and FR-CM5 bet that the implementer and reviewer can read one task's brief on demand. If `plan-task-brief` extracts the wrong PLAN-TASK body or truncates it, the subagent works from bad context — worse than today's one-shot whole-plan read.
Status: mitigated

### RISK-TRUST-001 — FR-CM3 markers misread as a machine gate (receipt-based verification)
The Resolved/Gap/Unresolved adjudication records evidence the controller judged. If a later gate were wired to read those markers as truth, it would cross the trust/audit boundary the project deliberately holds.
Status: mitigated

### RISK-DOCS-001 — Reworking the dispatch prose drops a required FR-A or FR-CM token
Routing the implementer and reviewer dispatches through the brief file rewrites the same template regions FR-A2 and FR-A4 already constrain. A rewrite could silently drop a load-bearing token the docs-consistency gate or the SDD set depends on.
Status: mitigated

### RISK-EXEC-001 — `plan-task-brief` writes outside EXECUTING or follows a symlink
A command that writes a file under `logs/` could, if mis-guarded, write on a non-EXECUTING run or follow a symlinked path, mutating unintended state.
Status: mitigated

## Boundaries

- Files touched: `tools/workflow_cli/cli.py`, `tools/workflow_cli/agent_shortcuts.py`, a new `tools/r2p-task-brief` wrapper, the two `agent_templates/{claude,codex}` r2p-execute surfaces, and `tests/test_cli.py` plus `tests/test_docs_consistency.py`.
- Firm boundary: no edit to any gate function, to `ALLOWED_TRANSITIONS`, to an artifact schema or its required headings, or to an existing command's stdout / JSON contract.
- `plan-task-brief` is read-only with respect to run state: it reads the frozen PLAN and writes only a gitignored `logs/task-N-brief.md` scratch file; it never advances state or flips a checkbox.
- opencode and gemini stay outside the authored surface: opencode derives from the claude Markdown command, and gemini gets no r2p-execute orchestration surface here.

## Scope Overflow Risks

- Temptation to add a machine gate that reads the FR-CM3 warning / Resolved / Gap / Unresolved markers — excluded by SCOPE-OUT-002; it would convert audited judgment into asserted truth.
- Temptation to broadly refactor the r2p-execute templates while editing the dispatch sections — bounded by SCOPE-OUT-001 (no output-contract change) and the docs-consistency token gate.
- Temptation to introduce worktree or branch isolation, or gap-route handling, while touching execution prose — excluded by SCOPE-OUT-004.

## Mitigations

- RISK-GATE-001 and RISK-EXEC-001: keep the diff to the listed files; `plan-task-brief` reuses the existing `plan_task_anchors` and `heading_bounded_bodies` primitives and the established EXECUTING-status and symlink-rejection guards (mirroring `_reject_symlink_or_exit`); verified by the full pytest suite staying green plus targeted non-EXECUTING and symlink tests that expect EXIT_CONFLICT.
- RISK-CTX-001: `plan-task-brief` extracts the task body with the same anchor and boundary logic the PLAN gate uses, so the brief equals exactly what the gate counts as the task; a red-to-green test asserts single-task extraction.
- RISK-TRUST-001: the markers stay inert to the ledger regexes and no gate is wired to them; the requirement's Non-Goals and SCOPE-OUT-002 record the boundary, and the final-review and completion gates remain presence / audit checks.
- RISK-DOCS-001: extend `tests/test_docs_consistency.py` to require the new tokens on both surfaces while preserving the existing FR-A and SDD token set; the gate fails if either surface drops a token.

## Trace

| This ID | Upstream | Status |
|---|---|---|
| RISK-GATE-001 | SCOPE-OUT-001 | mitigated |
| RISK-CTX-001 | SCOPE-IN-001, SCOPE-IN-002 | mitigated |
| RISK-TRUST-001 | SCOPE-OUT-002 | mitigated |
| RISK-DOCS-001 | SCOPE-IN-006 | mitigated |
| RISK-EXEC-001 | SCOPE-IN-001 | mitigated |

## Upstream Summary (read-only)
# Requirement Brief

## Goal

Borrow the five remaining context-management disciplines of the
`superpowers:subagent-driven-development` skill (upstream `obra/superpowers`
v6.0.3) into the `r2p-execute` SDD execution loop, so the controller's resident
context stops growing with pasted task text and subagent return text. The change
is additive template prose plus one read-only CLI extraction command; it touches
no gate, no state transition, no artifact schema, and no existing command's
output contract, and it stays inside r2p's existing trust/audit boundary — the
agent adjudicates, the machine only audits the presence and structure of the
markers the agent produces.

## In-Scope

- SCOPE-IN-001 — FR-CM5: a read-only `plan-task-brief` CLI command, with its `task-brief` shortcut and `tools/r2p-task-brief` wrapper, that extracts one frozen PLAN-TASK body to `.req-to-plan/<id>/logs/task-N-brief.md`; valid only while the run is EXECUTING (else EXIT_CONFLICT, no write), symlink-rejecting, and emitting JSON `{work_id, task_id, brief_path}` where `task_id` is the literal matched anchor and `brief_path` is repo-root-relative. Phase 1, independently shippable.
- SCOPE-IN-002 — FR-CM1: route the implementer dispatch and the reviewer dispatch through the per-task brief file produced at the start of the loop instead of pasting task text, and define a minimal implementer return contract, on both r2p-execute orchestration surfaces (the claude command and the codex SKILL).
- SCOPE-IN-003 — FR-CM2: add a controller narration ceiling to both r2p-execute surfaces, capping what the controller restates from subagent returns into its own resident context.
- SCOPE-IN-004 — FR-CM3: require the controller to adjudicate each reviewer warning of the "cannot verify from diff" kind and record the outcome in `execution/progress.md` as a Resolved, Gap, or Unresolved line before the checkbox flip, where only Resolved — with implementation and test evidence for any unchanged-code claim — clears the warning.
- SCOPE-IN-005 — FR-CM4: carry Minor reviewer findings forward to the final whole-branch review on both surfaces rather than dropping them per task.
- SCOPE-IN-006 — Guard the new prose with token coverage in `tests/test_docs_consistency.py`, so dropping a load-bearing FR-CM token on either r2p-execute surface fails the suite.

## Out-of-Scope

- SCOPE-OUT-001 — Any change to a gate, a state transition, an artifact schema, or an existing command's output contract.
- SCOPE-OUT-002 — Any machine assertion or verification that a marker is true; there is no receipt-based verification, the trust/audit boundary is unchanged, and the warning/Resolved/Gap/Unresolved markers stay in the agent-judgment layer.
- SCOPE-OUT-003 — A separately authored gemini r2p-execute orchestration surface; opencode inherits from the claude Markdown command and is not authored independently here.
- SCOPE-OUT-004 — Any change to the in-place single-branch SDD execution model (no worktree or branch isolation) and no gap-route opening from inside an executing run.

## Non-Goals

- Not changing the subagent topology: the per-task implementer plus task-reviewer and the final whole-branch reviewer dispatch counts stay as they are.
- Not optimizing the token cost of the implementer's or reviewer's one-shot whole-plan read; the target is controller-resident, compounding context only.
- Not adding automated enforcement that the controller obeys the narration ceiling or the brief handoff — FR-CM1 and FR-CM2 are disciplines audited by humans and the existing presence gates, not new machine gates.

## Assumptions

- PLAN-TASK anchors are unique and contiguous from 1 (gate-guaranteed by `_check_plan_task_fields` at the PLAN quality gate), so an integer `--task N` resolves deterministically to a single `### PLAN-TASK` anchor.
- FR-A2 (diff and history handed off to files) and FR-A4 (reviewer-prompt discipline) are already shipped on both r2p-execute surfaces; this work composes with them.
- The claude command and the codex SKILL are the two r2p-execute orchestration targets; opencode derives its command from the claude Markdown template.
- `.req-to-plan/<id>/logs/` is gitignored scratch and is the correct home for per-task brief files.

## Acceptance Criteria

- `plan-task-brief --task N` on an EXECUTING run writes `.req-to-plan/<id>/logs/task-N-brief.md` containing exactly the one PLAN-TASK body and prints JSON `{work_id, task_id, brief_path}`; on any non-EXECUTING status it exits EXIT_CONFLICT and writes nothing; a symlinked output path exits EXIT_CONFLICT; and the command is reachable through both the `task-brief` shortcut and the `r2p-task-brief` wrapper — all covered by new red-to-green tests in `tests/test_cli.py`.
- Both r2p-execute surfaces carry the FR-CM1 through FR-CM4 prose: the loop produces the brief, the implementer and reviewer dispatches hand over the brief path rather than pasted task text, the implementer return contract is minimal, the narration ceiling is stated, the warning adjudication records a Resolved/Gap/Unresolved line before the flip, and Minor findings are carried to the final review.
- `tests/test_docs_consistency.py` fails if either surface drops a new required token, and the full pytest suite is green with no pre-existing test regressed.
- No gate, transition, artifact schema, or existing command output contract changes; the diff touches only `cli.py`, `agent_shortcuts.py`, the new wrapper, the two templates, and the two test files.

## Open Questions

- None blocking. The upstream requirement already resolved its prior micro-decisions: the implementer reads a bounded brief on demand (R2, not fully plan-blind), the command is EXECUTING-only, and the JSON payload is pinned. Naming follows the three-layer convention — CLI subcommand `plan-task-brief`, shortcut `task-brief`, wrapper `r2p-task-brief`.

## Sources

- `docs/r2p-execute-context-management-requirement.md` — the approved requirement (FR-CM1 through FR-CM5, design intent, test plan, risks, non-goals).
- `superpowers:subagent-driven-development` (upstream `obra/superpowers` v6.0.3) — the context-economy disciplines being borrowed.
- Shipped baseline: the r2p-execute SDD enhancement and final-review marker-gate work (FR-A1 through FR-A6, in local archive), specifically FR-A2 and FR-A4.
- Code anchors: `tools/workflow_cli/cli.py` (`_cmd_run_execute_start`), `gates.py` (`_check_plan_task_fields`, `check_execution_complete`), `markdown.py` (`plan_task_anchors`, `heading_bounded_bodies`), and the two `agent_templates/{claude,codex}` r2p-execute surfaces.

## Trace

| This ID | Upstream | Status |
|---|---|---|
| SCOPE-IN-001 | FR-CM5 | open — carried to design, spec, plan |
| SCOPE-IN-002 | FR-CM1 | open — carried to design, spec, plan |
| SCOPE-IN-003 | FR-CM2 | open — carried to design, spec, plan |
| SCOPE-IN-004 | FR-CM3 | open — carried to design, spec, plan |
| SCOPE-IN-005 | FR-CM4 | open — carried to design, spec, plan |
| SCOPE-IN-006 | docs-consistency token gate | open — carried to design, spec, plan |
| SCOPE-OUT-001 | trust/audit boundary | excluded |
| SCOPE-OUT-002 | trust/audit boundary | excluded |
| SCOPE-OUT-003 | surface coverage | excluded |
| SCOPE-OUT-004 | execution model | excluded |
<!-- /r2p-read-only -->

## Project Context (read-only)
# Project Context Pack

- repo_root: `/Users/xubo/x-skills/req-to-plan`
- languages: {'Python': 21274, 'JavaScript': 31}
- package_managers: npm, pip
- test_commands: ['npm test']
- entrypoints: ['tools/workflow_cli/__main__.py']
- config_files: ['requirements.txt']
- dependencies (1):
  - pyyaml>=6.0 (pip)
- source_dirs: ['bin', 'docs', 'tests', 'tools']
<!-- /r2p-read-only -->

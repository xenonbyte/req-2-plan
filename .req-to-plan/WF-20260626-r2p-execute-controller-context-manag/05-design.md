---
r2p_stage: design
r2p_version: 2
r2p_status: approved
r2p_created_at: 2026-06-25T17:45:18.449426+00:00
r2p_updated_at: 2026-06-25T17:55:17.704580+00:00
---

# Design

## Design Summary

Deliver the five disciplines as two mechanisms: one read-only CLI extraction
command (`plan-task-brief`) plus additive template prose on both r2p-execute
surfaces. The command reuses the exact PLAN-TASK anchor and body-boundary
primitives the PLAN gate already uses, and mirrors the EXECUTING-status and
symlink-rejection guards of the existing `run-execute-start` handler, so it adds
no new gate, transition, schema, or output contract. The prose moves the task
handoff from pasted text to a brief-file path and records the FR-CM3 warning
adjudication as agent-judgment markers the machine never reads. Phase 1
(`plan-task-brief` plus its tests) ships independently of Phase 2 (the prose plus
token guard).

## Current Code Evidence

- `tools/workflow_cli/cli.py` `_cmd_run_execute_start` — its `CLOSED_AT_PLAN_CHECKPOINT`-status precondition (`cli.py:728`, EXIT_CONFLICT otherwise), the `_reject_symlink_or_exit` guard on the exec dir, and `atomic_write_text` for run-dir writes; `plan-task-brief` mirrors this guard shape but checks EXECUTING status.
- `tools/workflow_cli/markdown.py` — `plan_task_anchors` and `heading_bounded_bodies` with `PLAN_TASK_ANCHOR_RE` (`^### PLAN-TASK-\d+`); these define the single-task body boundary the command must reuse verbatim.
- `tools/workflow_cli/gates.py` `_check_plan_task_fields` — enforces unique, contiguous-from-1 PLAN-TASK numbering at the PLAN gate, so an integer `--task N` resolves deterministically to one `### PLAN-TASK` anchor.
- `tools/workflow_cli/gates.py` `_LEDGER_UNCHECKED_RE` / `_LEDGER_CHECKED_RE` and `check_execution_complete` — the completion gate; the FR-CM3 Resolved/Gap/Unresolved markers must stay inert to these regexes.
- `tools/workflow_cli/agent_shortcuts.py` and the auto-discovered `tools/r2p-*` wrappers (via `install.py`) — the three-layer surface where the `task-brief` shortcut and `r2p-task-brief` wrapper plug in.
- `tools/workflow_cli/agent_templates/claude/commands/r2p-execute.md` and `agent_templates/codex/skills/r2p-execute/SKILL.md` — the §1 task extraction, §2 implementer dispatch, §5 reviewer dispatch, and §6 flip rule edited by FR-CM1 through FR-CM4.
- `tests/test_docs_consistency.py` — the token gate extended by DES-GUARD-001.

## Requirements Coverage

| Scope item | Design component |
|---|---|
| SCOPE-IN-001 | DES-CLI-001 |
| SCOPE-IN-002 | DES-PROSE-001 |
| SCOPE-IN-003 | DES-PROSE-001 |
| SCOPE-IN-004 | DES-PROSE-001 |
| SCOPE-IN-005 | DES-PROSE-001 |
| SCOPE-IN-006 | DES-GUARD-001 |

## Options Considered

- Option A (chosen) — a new read-only `plan-task-brief` CLI subcommand that extracts one task to a brief file, with §1 producing it and §2/§5 handing over the path. Durable on disk, survives controller context compaction, reuses gate primitives, and Phase 1 is independently shippable.
- Option B — a fully plan-blind controller that never reads the PLAN. Rejected: it bets on a Pre-flight whole-plan read surviving compaction on long runs, and it breaks Model Selection and the FR-CM3 adjudication, both of which need the controller to see the cited SPEC and sibling context.
- Option C — keep pasting task text inline (status quo). Rejected: the pasted text is exactly the controller-resident leak this work removes.
- Command home — a new subcommand versus extending `run-execute-start`. Chose the new subcommand: it is read-only and single-responsibility, independently testable, and keeps the state-transition command focused.

## Chosen Design

### DES-CLI-001 — read-only `plan-task-brief` command, shortcut, and wrapper
An argparse subcommand in `cli.py` that resolves integer `--task N` to `### PLAN-TASK-<N>` via `plan_task_anchors(strip_readonly_sections(plan_text))`, extracts that single task body with `heading_bounded_bodies`, requires run status EXECUTING (else EXIT_CONFLICT with no write), rejects a symlinked logs or exec path via the `_reject_symlink_or_exit` pattern, writes the body with `atomic_write_text` to `.req-to-plan/<id>/logs/task-N-brief.md`, and prints JSON `{work_id, task_id, brief_path}` where `task_id` is the literal matched anchor and `brief_path` is repo-root-relative. Exposed via the `agent_shortcuts.py` `task-brief` subcommand and the `tools/r2p-task-brief` wrapper. This addresses RISK-CTX-001 [ADDRESSED] by reusing the gate's own body boundary, and RISK-EXEC-001 [ADDRESSED] via the EXECUTING and symlink guards.

### DES-PROSE-001 — FR-CM1 through FR-CM4 prose on both surfaces
§1 calls `plan-task-brief` and hands the brief-file path; §2 (implementer dispatch) and §5 (reviewer dispatch) reference that path instead of pasted task text; the implementer return contract is reduced to status plus a report-file path, not a restated task; FR-CM2 adds a narration ceiling on what the controller restates; FR-CM3 records each "cannot verify from diff" warning as a Resolved, Gap, or Unresolved line in `execution/progress.md` before the flip, where only Resolved clears it; FR-CM4 carries Minor findings to the final whole-branch review. This addresses RISK-GATE-001 [ADDRESSED] (prose only, no gate touched) and RISK-TRUST-001 [ADDRESSED] (markers inert, no gate reads them).

### DES-GUARD-001 — docs-consistency token coverage
Extend `tests/test_docs_consistency.py` to require the new FR-CM tokens on both r2p-execute surfaces while preserving the existing FR-A and SDD token set, and to keep asserting the r2p-execute surfaces do not mention the gap-open route. This addresses RISK-DOCS-001 [ADDRESSED].

## Decision Requests

none

## Rollback

Prose plus an additive read-only command; there is no state or schema migration, so there is no data rollback. Phase 1 (DES-CLI-001 and its tests) and Phase 2 (DES-PROSE-001, DES-GUARD-001) each revert independently with a single `git revert`. An execution run already in flight keeps working after a revert because the brief file is regenerable and the prior inline-paste prose still functions.

## Observability

The command's JSON payload and exit codes (0 ok, 2 cli error, 6 conflict, 7 not found) are the machine-observable signal; `pytest` over `tests/test_cli.py` and `tests/test_docs_consistency.py` is the regression signal. No runtime metrics or logging are added — this is a CLI tool with no server. The FR-CM3 outcomes are human-observable as Resolved/Gap/Unresolved lines in `execution/progress.md`.

## SPEC Handoff

The SPEC must pin, with one SPEC-* ID per behavior so PLAN tasks can consume them:
- The `plan-task-brief` CLI contract: arguments, the EXECUTING-only precondition, symlink rejection, the exact JSON keys and value shapes, the exit codes, and the output file path and format (the one task body, verbatim).
- The behavior contracts for the §1, §2, and §5 prose changes on each surface, plus the FR-CM2 narration ceiling, the FR-CM3 Resolved/Gap/Unresolved recording rule, and the FR-CM4 carry-forward.
- The exact token list `tests/test_docs_consistency.py` must enforce on both surfaces.
- The test matrix: EXECUTING happy path, non-EXECUTING giving EXIT_CONFLICT, symlink giving EXIT_CONFLICT, shortcut and wrapper end-to-end, and token presence.

## Trace

| This ID | Upstream | Status |
|---|---|---|
| DES-CLI-001 | SCOPE-IN-001 | open — carried to spec, plan |
| DES-PROSE-001 | SCOPE-IN-002, SCOPE-IN-003, SCOPE-IN-004, SCOPE-IN-005 | open — carried to spec, plan |
| DES-GUARD-001 | SCOPE-IN-006 | open — carried to spec, plan |

## Upstream Summary (read-only)
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

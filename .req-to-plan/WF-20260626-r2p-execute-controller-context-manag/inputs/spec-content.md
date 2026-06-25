# Spec

## Behavior Contracts

### SPEC-CLI-001 — `plan-task-brief` read-only extraction command
Implements DES-CLI-001 [ADDRESSED]; closes SCOPE-IN-001.
- Precondition: the run status must be EXECUTING. On any other status the command prints an error and exits EXIT_CONFLICT (6) **without writing any file**.
- Not found: an unknown `--work-id`, a missing PLAN artifact, or a `--task N` whose anchor does not exist exits EXIT_NOT_FOUND (7).
- Argument error: a missing or non-positive / non-integer `--task` exits EXIT_CLI_ERR (2).
- Task resolution: `--task N` maps to the literal anchor `### PLAN-TASK-<N>` resolved from `plan_task_anchors(strip_readonly_sections(plan_text))`; because the PLAN gate guarantees unique, contiguous-from-1 numbering, an in-range integer resolves to exactly one anchor.
- Extraction: the written body is exactly the `heading_bounded_bodies` slice for that anchor — byte-identical to what the PLAN gate counts as the task body — with no truncation or reflow.
- Symlink rejection: if the run's logs or exec path is a symlink, the command exits EXIT_CONFLICT (6) without writing (mirrors `_reject_symlink_or_exit`).
- Write: the body is written with `atomic_write_text` to `.req-to-plan/<id>/logs/task-<N>-brief.md`; re-running overwrites idempotently.
- No state mutation: `run.md`, the run status, and all artifacts are untouched.

### SPEC-SURFACE-001 — `task-brief` shortcut and `r2p-task-brief` wrapper
Implements DES-CLI-001 [ADDRESSED]; closes SCOPE-IN-001.
- `agent_shortcuts.py` gains a `task-brief` subcommand that delegates to the CLI `plan-task-brief` via `_run_cli`, preserving its exit code and stdout verbatim.
- A `tools/r2p-task-brief` wrapper (auto-discovered by the `install.py` `tools/r2p-*` glob, installed like the other wrappers) invokes the shortcut.
- Equivalence: invoking via the wrapper or the shortcut yields the identical JSON payload, the identical written file, and the identical exit code as the direct CLI call.

### SPEC-PROSE-001 — FR-CM1 task handoff as a brief file
Implements DES-PROSE-001 [ADDRESSED]; closes SCOPE-IN-002. Applies to both r2p-execute surfaces.
- The per-task loop's first step runs `plan-task-brief` for the current task and uses the returned `brief_path`.
- The implementer dispatch hands the `brief_path` (not pasted task text) plus scene-setting context and a report-file path.
- The reviewer dispatch hands the `brief_path` plus the task's Spec References and the diff-file path (not pasted task text).
- The implementer return contract is minimal: a status (DONE / DONE_WITH_CONCERNS / NEEDS_CONTEXT / BLOCKED) plus the report-file path; the controller does not ask the implementer to restate the task.
- The controller uses the returned `brief_path` without eager-reading the full task body into its own context; the implementer and reviewer read the brief on demand.

### SPEC-PROSE-002 — FR-CM2 controller narration ceiling
Implements DES-PROSE-001 [ADDRESSED]; closes SCOPE-IN-003. Applies to both surfaces.
- Between tool calls the controller narrates at most one short line (the FR-CM2 `Narration:` discipline — that label is the load-bearing token pinned in the PLAN), and never pastes a subagent's returned text into a later dispatch; what it restates into its own context is bounded to a status plus a pointer to the report or diff file.

### SPEC-PROSE-003 — FR-CM3 reviewer warning adjudication before the flip
Implements DES-PROSE-001 [ADDRESSED]; closes SCOPE-IN-004. Applies to both surfaces.
- For each reviewer "cannot verify from diff" warning, before flipping the task's checkbox the controller records one line per finding in `execution/progress.md`: `Resolved: ...`, `Gap: ...`, or `Unresolved: ...`.
- Only `Resolved:` clears the warning; a `Resolved:` claim about unchanged code must cite implementation and test evidence.
- `Gap:` and `Unresolved:` block the flip and cannot be overridden on the controller's own judgment.
- These markers are agent-judgment records; no machine gate reads them (they are inert to the ledger regexes), so the trust/audit boundary is unchanged.

### SPEC-PROSE-004 — FR-CM4 Minor findings carried to the final review
Implements DES-PROSE-001 [ADDRESSED]; closes SCOPE-IN-005. Applies to both surfaces.
- Minor reviewer findings not fixed within a task are recorded and carried into the final whole-branch review's input rather than dropped per task.

### SPEC-GUARD-001 — docs-consistency token coverage
Implements DES-GUARD-001 [ADDRESSED]; closes SCOPE-IN-006.
- `tests/test_docs_consistency.py` asserts both r2p-execute surfaces carry the new FR-CM load-bearing tokens, preserves the existing FR-A / SDD token set, and keeps asserting neither surface mentions the gap-open route.
- Required token set (semantic; exact literals pinned in the PLAN against the authored prose): `plan-task-brief`; the brief-file handoff (`task-` brief path / `brief_path`); the FR-CM3 markers `Resolved:` / `Gap:` / `Unresolved:`; the FR-CM2 narration-ceiling phrasing; the FR-CM4 carry-to-final-review phrasing.

## API / Data / Config Contracts

`plan-task-brief` command interface:
- Arguments: `--work-id <work-id>` (required), `--task <N>` (required, positive integer).
- Exit codes: `0` success; `2` cli error (missing or non-positive `--task`); `6` conflict (status not EXECUTING, or a symlinked logs/exec path); `7` not found (unknown work-id, missing PLAN, or task N out of range).
- stdout on success: the command uses the shared `format_success` helper, so the success payload carries at least the three data keys `{work_id, task_id, brief_path}` alongside the standard `status` and `message` fields. Under `R2P_JSON=1` the output is the JSON object `{"status": "ok", "message": "...", "work_id": "<id>", "task_id": "PLAN-TASK-<NNN>", "brief_path": ".req-to-plan/<id>/logs/task-<N>-brief.md"}`; in plain mode the same three values appear as labeled lines. `task_id` is the literal matched anchor text (zero-padding as the PLAN authored it, taken from the `plan_task_anchors` group); `brief_path` is repo-root-relative POSIX.
- File output: `.req-to-plan/<id>/logs/task-<N>-brief.md`, content = the verbatim single PLAN-TASK body.
- The three data fields are part of the success payload in both modes — JSON object keys under `R2P_JSON=1`, labeled lines otherwise — never replacing the standard envelope; no other config or environment input beyond the `--base-path` / `R2P_JSON` envelope shared by all subcommands.

## External Documentation Checked

N/A — no external dependencies

The change adds no new runtime dependency: `plan-task-brief` uses Python stdlib `argparse` and `json` plus existing internal modules (`markdown.py`, `cli.py` helpers, `atomic.py`). The borrowed disciplines come from `superpowers:subagent-driven-development` (upstream `obra/superpowers` v6.0.3), consulted 2026-06-26 as design provenance, not a code dependency the implementation calls.

## Test Matrix

| Test | SPEC | Expectation |
|---|---|---|
| EXECUTING happy path | SPEC-CLI-001 | writes `logs/task-N-brief.md`, success payload carries work_id/task_id/brief_path (inside the standard `status`/`message` envelope under `R2P_JSON`), exit 0 |
| status not EXECUTING (e.g. closed_at_plan_checkpoint) | SPEC-CLI-001 | exit 6 (EXIT_CONFLICT), no file written |
| symlinked logs/exec path | SPEC-CLI-001 | exit 6, no write |
| `--task` out of range | SPEC-CLI-001 | exit 7 (EXIT_NOT_FOUND) |
| `--task` non-positive / non-integer | SPEC-CLI-001 | exit 2 (EXIT_CLI_ERR) |
| extracted body equals the gate's task body | SPEC-CLI-001 | brief file == `heading_bounded_bodies` slice, byte-identical |
| zero-padded anchor resolved by integer `--task` | SPEC-CLI-001 | PLAN authored `### PLAN-TASK-002`; `--task 2` writes `task-2-brief.md` and reports `task_id` = `PLAN-TASK-002` (integer match, not string equality) |
| shortcut `task-brief` end-to-end | SPEC-SURFACE-001 | identical JSON, file, and exit code as the CLI |
| wrapper `r2p-task-brief` end-to-end | SPEC-SURFACE-001 | identical JSON, file, and exit code as the CLI |
| FR-CM token presence on both surfaces | SPEC-GUARD-001 | passes; deleting any required token from either surface fails the test |
| no gap-open mention on either surface | SPEC-GUARD-001 | assertion holds |
| FR-CM1–CM4 prose present | SPEC-PROSE-001..004 | enforced via the SPEC-GUARD-001 token coverage |

## Non-goals

- SCOPE-OUT-001: no change to any gate, state transition, artifact schema, or existing command output contract.
- SCOPE-OUT-002: no machine assertion that a marker is true; the warning / Resolved / Gap / Unresolved markers stay in the agent-judgment layer.
- SCOPE-OUT-003: no separately authored gemini surface; opencode derives from the claude command.
- SCOPE-OUT-004: no change to the in-place single-branch execution model and no gap-route opening inside an executing run.

## PLAN Handoff

Three PLAN tasks, numbered contiguously, consuming every SPEC ID above:
- PLAN-TASK-1 (Phase 1, independently shippable) — implement the `plan-task-brief` CLI command, the `task-brief` shortcut, the `tools/r2p-task-brief` wrapper, and their `tests/test_cli.py` cases. Spec References: SPEC-CLI-001, SPEC-SURFACE-001. Carries SCOPE-IN-001.
- PLAN-TASK-2 (Phase 2) — add the FR-CM1 through FR-CM4 prose to both r2p-execute surfaces (the claude command and the codex SKILL). Spec References: SPEC-PROSE-001, SPEC-PROSE-002, SPEC-PROSE-003, SPEC-PROSE-004. Carries SCOPE-IN-002, SCOPE-IN-003, SCOPE-IN-004, SCOPE-IN-005.
- PLAN-TASK-3 (Phase 2) — extend `tests/test_docs_consistency.py` token coverage. Spec References: SPEC-GUARD-001. Carries SCOPE-IN-006.

## Trace

| This ID | Upstream | Status |
|---|---|---|
| SPEC-CLI-001 | DES-CLI-001, SCOPE-IN-001 | open — consumed by PLAN-TASK-1 |
| SPEC-SURFACE-001 | DES-CLI-001, SCOPE-IN-001 | open — consumed by PLAN-TASK-1 |
| SPEC-PROSE-001 | DES-PROSE-001, SCOPE-IN-002 | open — consumed by PLAN-TASK-2 |
| SPEC-PROSE-002 | DES-PROSE-001, SCOPE-IN-003 | open — consumed by PLAN-TASK-2 |
| SPEC-PROSE-003 | DES-PROSE-001, SCOPE-IN-004 | open — consumed by PLAN-TASK-2 |
| SPEC-PROSE-004 | DES-PROSE-001, SCOPE-IN-005 | open — consumed by PLAN-TASK-2 |
| SPEC-GUARD-001 | DES-GUARD-001, SCOPE-IN-006 | open — consumed by PLAN-TASK-3 |

## Upstream Summary (read-only)
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

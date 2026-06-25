# Requirement Brief

## Goal

Strengthen the `r2p-execute` execution workflow along two complementary layers and
document the existing cross-stage closure model, without changing any workflow
state transition, artifact schema, tier semantics, or other gate:

- **Quality layer (agent-side, template-only):** fold durable controller-discipline
  lessons from `superpowers:subagent-driven-development` and
  `superpowers:verification-before-completion` into both `r2p-execute` surfaces —
  explicit model selection, file-handoff context hygiene, a BASE-commit rule,
  continuous execution, evidence-before-claims, and a stronger final whole-branch
  review that re-runs the suite and records its verdict.
- **Structural layer (CLI-side):** add a lightweight presence gate so an
  `EXECUTING` run cannot be archived (without `--force`) unless the final
  whole-branch review verdict is recorded on disk
  (`execution/final-review.md` with a current `Verdict: Approved`). This is an
  archive-time **audit precondition** at the same trust level as the existing
  PLAN-TASK checkbox cross-check — it never runs code, tests, or asserts the
  verdict is true.

Plus document (docs-only) that cross-stage trace closure is intentionally
concentrated at the PLAN quality gate. A separable P2 batch of three write-safety /
transactional-consistency fixes is captured but is not part of the SDD theme and
not a blocker.

## In-Scope

- SCOPE-IN-001 — **Part A: `r2p-execute` template enhancements** applied
  identically and kept in sync across both full-prose surfaces
  (`agent_templates/claude/commands/r2p-execute.md` and
  `agent_templates/codex/skills/r2p-execute/SKILL.md`): a `## Model Selection`
  subsection (FR-A1); diff/history handed as a file under `<work-id>/logs/`
  instead of inline (FR-A2); explicit BASE-commit rule that forbids `HEAD~1`
  (FR-A3); reviewer-prompt discipline (FR-A4); continuous execution and
  evidence-before-claims hardening (FR-A5); a stronger final whole-branch review
  that re-runs the suite, walks the PLAN task-by-task, dispatches one consolidated
  fix subagent, runs on the most capable model, and writes the
  `execution/final-review.md` verdict marker (FR-A6). Prose-only, terse, all
  existing required SDD tokens preserved, `r2p-gap-open` absent.
- SCOPE-IN-002 — **Part B: final-review marker gate (CLI-side)**: new
  `gates.py::check_final_review_recorded(run_dir)` reusing the existing
  symlink/regular-file and unfenced-line helpers (FR-B1); `run-execute-start` does
  **not** seed the marker file (FR-B2); wire the gate into
  `cli.py::_cmd_run_archive` after `check_execution_complete`, only for
  `EXECUTING` runs, bypassable by `--force` (FR-B3); honest, presence-check-only
  labeling enforced by an executable phrase/pattern guard (FR-B4).
- SCOPE-IN-003 — **Part C: closure-model documentation (docs-only)**: two
  `CLAUDE.md` Invariants lines (marker gate is presence/audit; closure enforced at
  the PLAN quality gate, 04–06 have no forward full-coverage gate) and an updated
  `r2p-execute` SDD-token description in the Test rules section; no hardcoded test
  count introduced (FR-C1).
- SCOPE-IN-004 — **Part D (P2, separable, non-blocking): three write-safety /
  transactional fixes**: atomic, symlink-checked Context Pack write (FR-D1);
  unique-temp `O_EXCL`/`O_NOFOLLOW` install-manifest write preserving existing
  install path validation (FR-D2); transactional run-reopen from `EXECUTING` with
  rollback matching archive's level (FR-D3).
- SCOPE-IN-005 — **Tests and doc-consistency guards** covering all of the above:
  unit tests for the new gate (`tests/test_gates.py`), archive
  blocked/passes/force-bypass plus the honesty-word guard and updated
  executing-archive success tests (`tests/test_cli.py`), new guarded tokens
  (`tests/test_docs_consistency.py`), and Part-D focused tests
  (`tests/test_context_pack.py`, `tests/test_install.py`, `tests/test_cli.py`).

## Out-of-Scope

- SCOPE-OUT-001 — The CLI running code, running tests, or parsing "did the test
  actually pass" from evidence. Correctness stays in the agent protocol and
  subagent reviews.
- SCOPE-OUT-002 — A per-task verification-output presence check (the ledger line
  already records commits and the review verdict; this would be redundant theater).
- SCOPE-OUT-003 — A forward full-coverage gate at stages 04–06 (REQ→DES→SPEC is a
  legitimately many-to-many, lossy mapping; closure deliberately funnels at PLAN).
- SCOPE-OUT-004 — Worktrees, branch isolation, the upstream
  `scripts/review-package` / `task-brief` external scripts, or any new service,
  database, telemetry, or network dependency.
- SCOPE-OUT-005 — Routing execution-time upstream defects through `r2p-gap-open`
  (execution runs are `closed`; defects go through reopen/human repair).
- SCOPE-OUT-006 — Any change to workflow state transitions, artifact schemas, tier
  semantics, or any other gate's rules.
- SCOPE-OUT-007 — Editing the gemini `r2p-execute.toml` four-line launcher shim
  (it carries no SDD prose) or hand-editing the opencode surface (it derives from
  the claude command via `install.py`).
- SCOPE-OUT-008 — Presenting the marker gate as a hard correctness barrier;
  `--force` is the intended operator bypass and fabrication is out of scope (same
  trust level as the checkbox gate).

## Non-Goals

- No durability or forensic claim for the marker: it is a working-tree precondition
  read at archive time, not a shared, committed record. The marker behaves like
  `execution/progress.md` — created during execution, never staged by per-task
  commits, moved into the gitignored archive at archive time.
- No new abstraction, runtime, or worktree model. The transferable mechanism is
  controller hygiene plus a recorded verdict.
- Keep every change Python-only and dependency-light (stdlib + `pyyaml`); keep the
  CLI/agent boundary intact (CLI validates structure/recorded state; the agent
  produces all semantic content).

## Assumptions

- The current `r2p-execute` skeleton already matches the subagent-driven model
  (fresh implementer per task, two-verdict task-reviewer, final whole-branch
  review, `NEEDS_CONTEXT` ladder, dirty-tree block, durable ledger); Part A adds
  controller discipline, not a rewrite.
- The background "Honesty surfaces" audit holds: no existing archive-path surface
  (`cli.py`, `agent_shortcuts.py`, `output.py`, `r2p-archive`/`r2p-status`
  templates) claims correctness today; only the new Part B message and Part A prose
  could leak a correctness claim, and both are constrained by FR-B4.
- `.req-to-plan/.gitignore` ignores `/*/logs/`, so the FR-A2 diff scratch under
  `<work-id>/logs/` is gitignored and immune to an accidental `git add`; the run's
  `execution/` directory is tracked.
- Part B overrides the previously recorded "wait for a real false-green archive"
  decision deliberately; it is accepted because the gate is strictly additive and
  revertible (one function + one wiring line).
- Parts A–C ship together; Part D may land in a separate change.

## Acceptance Criteria

- AC-001 — Both `r2p-execute` surfaces carry the Part A additions and stay in sync;
  all pre-existing required SDD tokens remain present and `r2p-gap-open` is absent.
- AC-002 — `check_final_review_recorded` passes only on a regular
  `execution/final-review.md` whose final unfenced `Verdict:` line is
  `Verdict: Approved`; it fails on a missing file, a symlink/non-regular file, a
  missing verdict line, an unsupported current verdict value, and a final
  `Verdict: Changes Requested`; a `Verdict:` inside a fenced code block does not
  count; multiple unfenced verdict lines use the last one.
- AC-003 — Archiving an `EXECUTING` run with a complete ledger but no approved
  marker is rejected with `EXIT_GATE_FAIL` (3); adding the approved marker lets it
  pass; `--force` bypasses both the completion and final-review gates.
- AC-004 — Archiving a `CLOSED_AT_PLAN_CHECKPOINT` run does not require a
  final-review marker.
- AC-005 — `run-execute-start` does not create `execution/final-review.md`.
- AC-006 — No archive-path output and no gate message makes an affirmative
  correctness claim; the executable guard allows required protocol literals
  (`Verdict: Approved`) and the negated disclaimer (`not a correctness guarantee`)
  in any gate failure message, while rejecting affirmative wording (`verified`,
  `validated`, `guaranteed correct`, `review approved`). The guard is
  phrase/pattern-based, not a bare-token substring match.
- AC-007 — Existing exit codes and JSON-mode payloads are unchanged.
- AC-008 — `tests/test_docs_consistency.py` guards the new tokens
  (`Model Selection`, `HEAD~1`, `execution/final-review.md`, `Verdict: Approved`,
  `re-run the full verification suite`) and stays green; the full suite stays green.
- AC-009 — (Part D) a symlink planted at either Context Pack target is rejected and
  a normal build still produces both files; the install manifest is still
  written/replaced and a symlink planted at its temp path is rejected; a simulated
  reopen source-save failure leaves no orphan new run and a consistent source
  status, and a normal reopen is unchanged.

## Open Questions

- None blocking. The requirement is decision-complete: the marker contract, gate
  modes, failure-message text, honesty-guard shape, and Part-D fixes are all
  specified. Part D's sequencing (same change vs. separate) is a delivery choice
  resolved at PLAN, not a design open question.

## Sources

- `00-raw-requirement.md` — the verbatim requirement (Summary, Motivation, Goals,
  Non-Goals, Background, FR-A1..A6, FR-B1..B4, FR-C1, FR-D1..D3, Marker File
  Contract, Target Surfaces, Acceptance Criteria, Test Plan, Migration,
  auto-commit-and-archive interaction, Risks, Implementation Boundaries,
  Verification Commands).
- `02-project-context.md` / `02-project-context.json` — Python-only repo (stdlib +
  `pyyaml`), `npm test`, entrypoint `tools/workflow_cli/__main__.py`.
- Code referenced in the requirement's verified Background:
  `gates.py::check_execution_complete`, `gates.py::check_quality_gate`,
  `trace.py::check_trace_closure`, `cli.py::_cmd_run_archive`,
  `cli.py::_cmd_run_execute_start`, `cli.py::_cmd_run_reopen`,
  `context_pack.py::write_context_pack`, `install.py`, `atomic.py`.

## Trace

| This ID | Upstream | Status |
|---|---|---|
| SCOPE-IN-001 | 00 Part A (FR-A1..A6) | open |
| SCOPE-IN-002 | 00 Part B (FR-B1..B4) | open |
| SCOPE-IN-003 | 00 Part C (FR-C1) | open |
| SCOPE-IN-004 | 00 Part D (FR-D1..D3) | open |
| SCOPE-IN-005 | 00 Test Plan / Acceptance Criteria | open |
| SCOPE-OUT-001 | 00 Non-Goals | closed |
| SCOPE-OUT-002 | 00 Non-Goals | closed |
| SCOPE-OUT-003 | 00 Non-Goals | closed |
| SCOPE-OUT-004 | 00 Non-Goals | closed |
| SCOPE-OUT-005 | 00 Non-Goals | closed |
| SCOPE-OUT-006 | 00 Non-Goals | closed |
| SCOPE-OUT-007 | 00 Target Surfaces / Files | closed |
| SCOPE-OUT-008 | 00 Non-Goals / Risks | closed |

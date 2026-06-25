# Risk Discovery

## Risks

### RISK-HONESTY-001 — False confidence (presence gate reads as "correctness verified")
Status: mitigated
A presence gate that read as "correctness verified" would regress into the
theater this project previously rejected. The marker only records that a verdict
line exists; it never runs code or tests and never asserts the verdict is true.
Mitigated by FR-B4 and its executable phrase/pattern guard: every gate message is
a presence/audit statement at the same trust level as the existing checkbox gate.

### RISK-TRUST-001 — Bypass and fabrication (by design, not a defect)
Status: out_of_scope
`--force` is the intended operator bypass for abandoned/superseded runs, and an
agent could write a fake `Verdict: Approved` — the same trust level as fabricated
checkboxes. Defeating a deliberately-lying agent is explicitly out of scope; the
gate is an archive-time audit precondition, not a hard barrier. It closes the
realistic forgetful/lazy skip of the final review, which is its whole stated
purpose.

### RISK-EVIDENCE-001 — Enforcement ahead of observed evidence
Status: mitigated
The gate guards a failure mode (false-green archive) not yet observed in this
project, overriding the recorded "wait for a real false-green" decision. Bounded
and mitigated by design: the gate is strictly additive and revertible (remove one
function plus one wiring line), makes no correctness or durability claim, and adds
exactly one archive-time precondition — so the override is low-cost and easy to
undo if it proves noisy.

### RISK-TEST-001 — Existing executing-archive tests turn red
Status: mitigated
Adding the gate makes previously-passing executing-archive success tests fail
(they archive with a complete ledger but no marker). Mitigated in the same change:
the test plan seeds an approved `execution/final-review.md` in those success cases
(FR-B3 / Test Plan) so the suite stays green.

### RISK-DRIFT-001 — The two `r2p-execute` surfaces fall out of sync
Status: mitigated
Part A edits two surfaces (claude command + codex skill) that can diverge.
Mitigated by `tests/test_docs_consistency.py`: the guarded-token set (extended in
FR-C1 with the new tokens) fails the suite on divergence of any guarded token, and
opencode/gemini are derived/inert so they need no hand-edit.

### RISK-GUARD-001 — Honesty-guard brittleness (over-asserting our own prose)
Status: mitigated
The FR-B4 guard asserts on our own output prose, and the project elsewhere warns
that pinning exact message text is brittle. Mitigated by keeping it
phrase/pattern-based and minimal — match affirmative claim phrases only, exempt
the exact disclaimer (`not a correctness guarantee`) and protocol literals
(`Verdict: Approved`) — so it guards intent without pinning full message text.

### RISK-WRITE-001 — (Part D) symlink / TOCTOU write-safety gaps
Status: mitigated
`context_pack.py::write_context_pack` writes both targets with plain `write_text`
and no symlink check, and `install.py` writes the manifest through a fixed-name
sibling temp with a check-then-write window. A planted symlink or a fixed-name
collision could be written through. Mitigated by FR-D1 (reject symlink target +
`atomic_write_text`) and FR-D2 (unique-temp `O_EXCL`/`O_NOFOLLOW` write preserving
install path validation). Low risk, separable, non-blocking.

### RISK-STATE-001 — (Part D) partial state on run-reopen failure
Status: mitigated
`cli.py::_cmd_run_reopen` saves the new run first, then transitions/saves an
`EXECUTING` source; a source-save failure leaves the new run created while the
source stays `EXECUTING`, with no rollback (unlike archive). Mitigated by FR-D3:
make reopen transactional (remove the orphan new run on source-save failure, or
persist the source transition first and roll it back if the new-run save fails) —
matching archive's transactional level.

## Boundaries

- **No correctness verification in the CLI.** The marker gate must never run code,
  run tests, or parse "did the test actually pass" from evidence
  (SCOPE-OUT-001). Correctness stays in the agent protocol and subagent reviews.
- **No new gate semantics elsewhere.** The change adds exactly one archive-time
  precondition wired after `check_execution_complete`; it does not change workflow
  state transitions, artifact schemas, tier semantics, or any other gate
  (SCOPE-OUT-006).
- **Scope of the marker gate.** Enforced only when archiving an `EXECUTING` run
  without `--force`; a `CLOSED_AT_PLAN_CHECKPOINT` run never executed is archivable
  without a marker (FR-B3 / AC-004).
- **Surface boundary.** Part A edits only the two full-prose surfaces (claude
  command, codex skill); opencode derives from the claude command via `install.py`
  and the gemini four-line launcher shim carries no SDD prose — both intentionally
  unedited (SCOPE-OUT-007).
- **Dependency boundary.** Python-only, stdlib + `pyyaml`; no worktrees, branch
  isolation, external scripts, service, database, telemetry, or network dependency
  (SCOPE-OUT-004). CLI/agent boundary preserved.
- **Marker durability boundary.** The marker is a working-tree precondition read at
  archive time, not a shared, committed record; it is moved into the gitignored
  archive at archive time and is never staged by per-task commits.

## Scope Overflow Risks

### RISK-OVERFLOW-001 — Part A prose ballooning
Status: mitigated
The upstream skill is 400+ lines; copying it wholesale would dilute adherence and
cost context on every load. Mitigated by FR's "terse, prefer one-line additions"
constraint and the requirement that the upstream skill is a source of principles,
not a length target.

### RISK-OVERFLOW-002 — Drifting into rejected adjacent checks
Status: out_of_scope
Tempting adjacent additions are explicitly excluded: a per-task
verification-output presence check (SCOPE-OUT-002) and a forward full-coverage gate
at stages 04–06 (SCOPE-OUT-003). Both are out of scope; pulling them in would be
scope overflow and (for 04–06) would fight the deliberate "closure funnels at
PLAN" design.

### RISK-OVERFLOW-003 — Part D bleeding into the SDD theme
Status: deferred
Part D is a separable P2 batch (write-safety/transactional fixes) unrelated to the
SDD theme. Deferred boundary: it may land in a change separate from Parts A–C and
must not block them; PLAN sequences it explicitly.

## Mitigations

- **Honesty (RISK-HONESTY-001, RISK-GUARD-001):** FR-B4's executable
  phrase/pattern guard — allow protocol literals (`Verdict: Approved`) and the
  negated disclaimer (`not a correctness guarantee`) in any gate failure message;
  reject affirmative claims (`verified`, `validated`, `guaranteed correct`,
  `review approved`); never a bare-token substring match. Archive success path
  stays state-only (`archived`).
- **Trust boundary (RISK-TRUST-001):** documented as by-design; `--force` is the
  named operator bypass; the gate is labeled an audit precondition, not a barrier.
- **Reversibility (RISK-EVIDENCE-001):** one gate function + one wiring line; trivially
  revertible if noisy.
- **Test integrity (RISK-TEST-001):** seed an approved marker in updated
  executing-archive success tests in the same change; add focused gate unit tests.
- **Surface sync (RISK-DRIFT-001):** extend `tests/test_docs_consistency.py`
  guarded tokens; rely on opencode-derivation and gemini-inertness.
- **Write-safety (RISK-WRITE-001, RISK-STATE-001):** FR-D1/D2 symlink-checked
  atomic/unique-temp writes; FR-D3 transactional reopen with rollback; each with
  focused tests.
- **Prose terseness (RISK-OVERFLOW-001..003):** one-line additions, principle-not-length,
  hard exclusion of SCOPE-OUT-002/003, Part D kept separable.

## Trace

| This ID | Upstream | Status |
|---|---|---|
| RISK-HONESTY-001 | SCOPE-IN-002 / 00 Risks (False confidence) | mitigated |
| RISK-TRUST-001 | SCOPE-IN-002 / 00 Risks (Bypass) | out_of_scope |
| RISK-EVIDENCE-001 | SCOPE-IN-002 / 00 Risks (Enforcement ahead of evidence) | mitigated |
| RISK-TEST-001 | SCOPE-IN-005 / 00 Risks (Existing-test breakage) | mitigated |
| RISK-DRIFT-001 | SCOPE-IN-001 / 00 Risks (Surface drift) | mitigated |
| RISK-GUARD-001 | SCOPE-IN-002 / 00 Risks (Honesty-guard brittleness) | mitigated |
| RISK-WRITE-001 | SCOPE-IN-004 / 00 FR-D1, FR-D2 | mitigated |
| RISK-STATE-001 | SCOPE-IN-004 / 00 FR-D3 | mitigated |
| RISK-OVERFLOW-001 | SCOPE-IN-001 / 00 Part A terseness | mitigated |
| RISK-OVERFLOW-002 | SCOPE-OUT-002, SCOPE-OUT-003 | out_of_scope |
| RISK-OVERFLOW-003 | SCOPE-IN-004 / 00 Part D | deferred |

## Upstream Summary (read-only)
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
<!-- /r2p-read-only -->

## Project Context (read-only)
# Project Context Pack

- repo_root: `/Users/xubo/x-skills/req-to-plan`
- languages: {'Python': 20333, 'JavaScript': 31}
- package_managers: npm, pip
- test_commands: ['npm test']
- entrypoints: ['tools/workflow_cli/__main__.py']
- config_files: ['requirements.txt']
- dependencies (1):
  - pyyaml>=6.0 (pip)
- source_dirs: ['bin', 'docs', 'tests', 'tools']
<!-- /r2p-read-only -->

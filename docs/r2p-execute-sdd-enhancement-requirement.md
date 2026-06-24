# r2p-execute SDD Enhancement & Final-Review Marker Gate Requirement

## Summary

Strengthen the `r2p-execute` execution workflow in two complementary layers,
plus document the existing cross-stage closure model.

- **Part A (agent-side, template-only):** fold the durable controller-discipline
  lessons from the `superpowers:subagent-driven-development` and
  `superpowers:verification-before-completion` skills into the `r2p-execute`
  surfaces — model selection, file-handoff context hygiene, an explicit BASE
  commit rule, continuous execution, evidence-before-claims, and a stronger
  final whole-branch review. These improve the **quality** of execution
  evidence.
- **Part B (CLI-side, structural):** add a lightweight `check_final_review_recorded`
  presence gate so a run cannot be archived unless the final whole-branch review
  verdict is persisted on disk (`execution/final-review.md` carrying
  `Verdict: Approved`). This enforces the **persistence** of that evidence and
  closes a real structural hole: today an agent can flip every PLAN-TASK checkbox
  and archive while silently skipping the final review.
- **Part C (docs-only):** document that cross-stage trace closure is intentionally
  concentrated at the PLAN quality gate, and that stages 04–06 deliberately have
  no forward full-coverage gate.

Part B is an **audit-trail completeness** check at the same trust level as the
existing checkbox cross-check — it is a presence/audit gate, **not** a
correctness gate. It never runs code, never runs tests, and never asserts the
recorded verdict is true.

## Motivation

The current `r2p-execute` skeleton already matches the subagent-driven model
(fresh implementer per task, a two-verdict task-reviewer, a final whole-branch
review, the `NEEDS_CONTEXT` ambiguity ladder, a dirty-tree block, and a durable
ledger) and is in several respects stronger than the upstream skill: a
CLI-enforced precondition gate, a CLI-enforced completion gate
(`check_execution_complete` cross-checks the ledger against the frozen PLAN),
in-place execution on the current branch, and an upstream-defect → reopen/repair
route. Those divergences are deliberate and are preserved.

What the upstream skills carry and our surfaces lack is **controller
discipline** and **evidence persistence**:

1. **No model-selection guidance.** Every subagent silently inherits the session
   model (often the most capable and most expensive). The upstream skill scales
   the model to the role and dispatches the final review on the most capable
   model.
2. **The diff is handed inline.** Step 5 currently records the diff with
   `git diff -U10 <base-commit> HEAD` and passes the diff text into the reviewer
   dispatch. Pasted text stays resident in the controller's context and is
   re-read every turn; a long plan bloats the controller. The upstream skill
   hands the diff as a file path.
3. **`<base-commit>` carries no warning.** Using `HEAD~1` as the base silently
   drops all but the last commit of a multi-commit task.
4. **Per-task completion claims are not hardened.** "should pass" / "looks
   correct" can stand in for fresh verification output.
5. **The final whole-branch review does not re-run the suite.** Per-task greens
   do not catch cross-task regressions (task 5 breaks task 2's test), and the
   review verdict is never required on disk before archive.
6. **Cross-stage coverage is asked about repeatedly.** The closure model is real
   but undocumented, so it reads as a possible gap.

The transferable mechanism is controller hygiene and persisted audit evidence —
not a new runtime, not a worktree model, and not CLI-side correctness
verification.

## Goals

- Reduce controller context bloat and subagent cost during execution
  (file handoffs, explicit model selection).
- Raise the quality and honesty of per-task and whole-branch completion evidence.
- Guarantee that an archived executing run leaves the final whole-branch review
  verdict on disk, so a later false-green can be inspected.
- Keep every change Python-only and dependency-light (stdlib + `pyyaml`).
- Preserve the CLI/agent boundary: the CLI validates structure and persistence,
  the agent produces all semantic content. The CLI never generates artifact prose
  and never verifies correctness.
- Keep both `r2p-execute` surfaces (claude command + codex skill) byte-for-byte
  in sync on the guarded tokens, and keep the full test suite green.

## Non-Goals

- Do **not** make the CLI run code, run tests, or parse "did the test actually
  pass" from the evidence. Correctness is not structurally checkable and stays in
  the agent protocol and subagent reviews.
- Do **not** add a per-task verification-output presence check. The ledger line
  `(commits <base7>..<head7>, review clean)` already records commits and the
  review verdict; a per-task evidence-presence field is largely redundant and is
  prone to becoming theater.
- Do **not** add a forward full-coverage gate at stages 04–06 (e.g. forcing every
  brief item into a DES heading or every `DES-*` into a SPEC). REQ→DES→SPEC is a
  legitimately many-to-many, lossy mapping; a hard symmetric-coverage gate would
  produce false positives and fight the deliberate "closure funnels at PLAN"
  design.
- Do **not** introduce worktrees, branch isolation, the upstream
  `scripts/review-package` / `task-brief` external scripts, or any new service,
  database, telemetry, or network dependency.
- Do **not** route execution-time upstream defects through `r2p-gap-open`
  (execution runs are `closed`; defects go through reopen/human repair).
- Do **not** change workflow state transitions, artifact schemas, tier semantics,
  or any other gate's rules.

## Background: Current State (verified against code)

- `gates.py::check_execution_complete(run_dir)` is the only archive completion
  gate. It reads `execution/progress.md`, requires every frozen PLAN-TASK to have
  a `- [x]` line, rejects any remaining `- [ ]`, rejects a truncated ledger, and
  rejects an empty ledger. Its own docstring states it is "structural validation
  only … an audit gate, not a correctness gate."
- `gates.py::check_quality_gate` runs cross-stage closure **only at the PLAN
  stage** via `trace.py::check_trace_closure` (every `SPEC-*` consumed by a
  PLAN-TASK, every `SCOPE-IN-*` carried into PLAN, every `RISK-*` closed), plus a
  per-stage rule (`_find_ids_without_closure`) that any *cited* upstream ID must
  carry a closure tag. There is no forward full-coverage gate at 04–06.
- `cli.py::_cmd_run_archive` calls `check_execution_complete` only for an
  `EXECUTING` run when `--force` is not set. There is **no** check that the final
  whole-branch review happened — an agent that flips all task checkboxes can
  archive without it.
- `cli.py::_cmd_run_execute_start` seeds `execution/progress.md` with one
  unchecked line per PLAN-TASK. It does **not** seed any final-review artifact.

### Honesty surfaces (verified — no correctness leak today)

Every surface that reports a successful archive was checked and none claims
correctness:

- `cli.py` archive success → `✓ Run archived: {work_id}` / JSON `status: archived`.
- `agent_shortcuts.py` archive shortcut → `done: archived`.
- `output.py` success → `✓ {message}` only; its generic `"{gate} passed"` helper
  is not on the archive path.
- `r2p-archive` / `r2p-status` templates contain none of
  `verif|correct|approved|passed`.

The only new surfaces that could imply correctness are the Part B gate failure
message and the Part A template prose — both are owned by this change and are
constrained by FR-B4.

## Functional Requirements

### Part A — r2p-execute template enhancements (agent-side)

Applies identically to both surfaces, kept in sync:

- `tools/workflow_cli/agent_templates/claude/commands/r2p-execute.md`
- `tools/workflow_cli/agent_templates/codex/skills/r2p-execute/SKILL.md`

All existing required SDD tokens must be preserved and `r2p-gap-open` must not
appear (guarded by `tests/test_docs_consistency.py`).

#### FR-A1: Model Selection

Add a `## Model Selection` subsection: dispatch the cheapest capable model for
mechanical tasks (1–2 files with a complete Skeleton), a standard model for
integration/judgment tasks, and the most capable available model for the final
whole-branch review. Always specify the model explicitly when dispatching; an
omitted model inherits the session default. State the principle "turn count beats
token price."

#### FR-A2: Diff and history as files, not inline

Replace the inline-diff instruction in Step 5. The controller records the task's
BASE commit before dispatching the implementer, and after `DONE` writes the diff
to `execution/task-N-diff.md` (`git diff -U10 <base-commit> HEAD >
execution/task-N-diff.md`) and hands the reviewer the **file path**, not the diff
text. The reviewer-input list changes "The diff" to the diff file path.

#### FR-A3: BASE commit rule

State explicitly: record BASE (`git rev-parse HEAD`) before dispatching the
implementer, and **never use `HEAD~1`** as BASE — it silently drops all but the
last commit of a multi-commit task.

#### FR-A4: Reviewer-prompt discipline

Add a short rule block: copy the plan's Global Constraints verbatim into the
reviewer prompt; never pre-judge a finding's severity ("at most Minor") or tell
the reviewer what not to flag; never paste accumulated prior-task summaries into a
later dispatch (a fresh subagent gets its task, the interfaces it touches, and the
global constraints — nothing else).

#### FR-A5: Continuous execution and evidence-before-claims

Execute all PLAN-TASKs without pausing to ask "should I continue?" between tasks;
the only stop conditions are an unresolvable `BLOCKED`, an upstream defect
requiring repair, the dirty-tree block, or all tasks complete. Harden the
implementer contract: `Verification` requires fresh command output; "should pass"
/ "looks correct" is not evidence, and the implementer may not report `DONE`
without it.

#### FR-A6: Stronger final whole-branch review

The final whole-branch review must:

1. re-run the full verification suite on the final HEAD and attach the fresh
   output (per-task greens do not catch cross-task regressions);
2. walk the PLAN task-by-task as a line-by-line requirements checklist and report
   any gap;
3. dispatch **one** fix subagent carrying the complete findings list, not one
   fixer per finding;
4. run on the most capable available model (cross-reference FR-A1);
5. once the review is clean, write `execution/final-review.md` recording the
   reviewed range, a `Verdict: Approved` line (or `Verdict: Changes Requested`
   while findings remain), and a one-line summary; and note that `r2p-archive`
   refuses to archive an executing run without this file carrying
   `Verdict: Approved` (Part B).

### Part B — Final-review marker gate (CLI-side)

#### FR-B1: New gate function

Add `gates.py::check_final_review_recorded(run_dir) -> GateResult`, placed beside
`check_execution_complete`, reusing `_read_regular_text_no_symlink` (symlink and
non-regular-file rejection) and `unfenced_markdown_lines` (fenced code is
ignored). It validates `execution/final-review.md`:

- file missing → fail.
- file is a symlink or not a regular file → fail (refuse to read outside the run
  directory).
- no unfenced line matching `^\s*Verdict:\s*(Approved|Changes Requested)\s*$`
  (case-insensitive) → fail (verdict not recorded).
- `Verdict: Changes Requested` (or any non-approved value) → fail (resolve
  findings and record `Verdict: Approved`).
- `Verdict: Approved` → pass.

The gate uses exit code `EXIT_GATE_FAIL` (3), consistent with
`check_execution_complete`.

#### FR-B2: Not seeded

`run-execute-start` must **not** create `execution/final-review.md`. The file is
absent by default so the gate has teeth; only the agent's final-review step
writes it.

#### FR-B3: Archive wiring

In `cli.py::_cmd_run_archive`, inside the existing
`record.status == RunStatus.EXECUTING and not args.force` block, after
`check_execution_complete` passes, run `check_final_review_recorded` and
`print_and_exit` on failure with its issues and exit code. The gate applies only
to `EXECUTING` runs (a `CLOSED_AT_PLAN_CHECKPOINT` run that was never executed is
archivable without a final review). `--force` bypasses both completion and
final-review gates (abandoned/superseded runs).

#### FR-B4: Honest labeling (the linchpin)

No archive-path output and no `check_final_review_recorded` message may imply that
correctness was verified. The gate's failure message states it is a presence
check on the review audit trail, not a correctness guarantee. The archive success
path stays state-only (`archived`); no "review approved" / "verified" wording is
added anywhere. This requirement is enforced by an executable test (the
honesty-word guard in the Test Plan), not by prose intention alone.

The canonical failure message is:

```text
Final whole-branch review verdict not recorded: execution/final-review.md is
missing or has no 'Verdict: Approved' line. Presence check on the review audit
trail — not a correctness guarantee. Record the verdict, or re-run with --force
to archive an abandoned run.
```

### Part C — Closure-model documentation (docs-only)

#### FR-C1: Document the closure model

Add two `CLAUDE.md` Invariants lines: (a) the final-review marker gate is
presence/audit at the same trust level as the checkbox gate and does not verify
correctness; (b) cross-stage trace closure is enforced at the PLAN quality gate
(every SPEC consumed, SCOPE-IN carried, RISK closed), intermediate stages enforce
only "cited upstream ID ⇒ closure tag", and 04–06 intentionally have no forward
full-coverage gate. Update the `r2p-execute` SDD token description in the Test
rules section to match the new guarded tokens. No hardcoded test count may be
introduced.

## Marker File Contract

```text
Path:     <run-dir>/execution/final-review.md
Seeded:   no (absent by default; written by the agent's final-review step)
Required: a regular, non-symlink file containing an unfenced line
          matching  ^\s*Verdict:\s*(Approved|Changes Requested)\s*$  (case-insensitive)
Pass:     Verdict: Approved
Fail:     missing file | symlink / non-regular | no Verdict line | Verdict: Changes Requested
Exit:     EXIT_GATE_FAIL (3) on failure
Scope:    enforced only when archiving an EXECUTING run without --force
```

## Target Surfaces / Files

1. `tools/workflow_cli/agent_templates/claude/commands/r2p-execute.md` — Part A + FR-A6 marker write.
2. `tools/workflow_cli/agent_templates/codex/skills/r2p-execute/SKILL.md` — same, synced.
3. `tools/workflow_cli/gates.py` — new `check_final_review_recorded`.
4. `tools/workflow_cli/cli.py` — wire the gate into `_cmd_run_archive`.
5. `tests/test_gates.py` — unit tests for the new gate.
6. `tests/test_cli.py` — archive blocked/passes/force-bypass; the honesty-word guard; update existing executing-archive success tests.
7. `tests/test_docs_consistency.py` — new guarded tokens.
8. `CLAUDE.md` — Invariants (Parts B and C) + Test rules token description.

No new file is created for tests; no new module, service, or dependency.

## Acceptance Criteria

- Both `r2p-execute` surfaces contain the Part A additions and stay in sync; all
  pre-existing required SDD tokens remain present and `r2p-gap-open` is absent.
- `check_final_review_recorded` passes only on a regular `execution/final-review.md`
  carrying `Verdict: Approved`; it fails on a missing file, a symlink/non-regular
  file, a missing verdict line, and `Verdict: Changes Requested`; a `Verdict:`
  inside a fenced code block does not count.
- Archiving an `EXECUTING` run with a complete ledger but no approved
  final-review marker is rejected with `EXIT_GATE_FAIL`; adding the approved
  marker lets it pass; `--force` bypasses both gates.
- Archiving a `CLOSED_AT_PLAN_CHECKPOINT` run does not require a final-review
  marker.
- `run-execute-start` does not create `execution/final-review.md`.
- No archive-path output and no gate message contains correctness-implying wording
  (`verified`, `correct`, `validated`, `guaranteed`, …); an executable test
  asserts this.
- Existing exit codes and JSON-mode payloads are unchanged.
- `tests/test_docs_consistency.py` guards the new tokens and stays green; the full
  suite stays green.

## Test Plan

- `tests/test_gates.py`: missing file → fail; `Verdict: Approved` → pass;
  `Verdict: Changes Requested` → fail; symlink → fail; non-regular (FIFO) →
  fail without blocking; `Verdict:` inside a code fence → not counted.
- `tests/test_cli.py`: executing-run archive blocked when the marker is missing
  even with a complete ledger; passes with an approved marker; `--force`
  overrides; closed-at-plan archive unaffected. Update the existing success cases
  (`test_archive_executing_run_with_complete_ledger`,
  `test_archive_passes_when_ledger_covers_all_plan_tasks`, and any other
  executing-run archive-success test) to seed an approved
  `execution/final-review.md`. Add the FR-B4 honesty-word guard over the archive
  output and the gate message.
- `tests/test_docs_consistency.py`: add a stable subset of new tokens
  (`Model Selection`, `HEAD~1`, `execution/final-review.md`, `Verdict: Approved`,
  `re-run the full verification suite`) to the execute-surface required set.

## Migration

A run already in `EXECUTING` before this change has no `execution/final-review.md`.
After upgrade, archiving it requires the agent's final-review step to write the
marker (the normal path) or `--force` (abandoned/superseded run). No run state is
mutated by the upgrade itself.

## Risks

- **False confidence.** A presence gate that read as "correctness verified" would
  regress into the theater this project previously rejected. Mitigated by FR-B4
  and its executable guard; the gate trust level equals the existing checkbox
  gate.
- **Adversarial fabrication.** An agent could write a fake `Verdict: Approved`
  without doing the review. This is the same trust boundary as fabricated
  checkboxes and is explicitly out of scope; the gate closes the realistic
  forgetful/lazy-skip hole, not fabrication.
- **Existing-test breakage.** Adding the gate turns previously-passing
  executing-archive tests red; the test plan updates them in the same change.
- **Surface drift.** The two `r2p-execute` surfaces can fall out of sync; the
  docs-consistency token guard catches divergence on the guarded tokens.
- **Honesty word-list coverage.** The FR-B4 guard checks a finite word list; a
  future message could imply correctness with an unlisted word. Accepted as low
  residual risk, mitigated by covering the common words and stating intent in
  `CLAUDE.md`.

## Implementation Boundaries

Keep the change narrow. Part A is template/docs prose only. Part B adds one gate
function and one archive wiring point; it does not change state transitions,
artifact schemas, tier semantics, or any other gate. The marker gate is
structural and honestly labeled — it must never run code, run tests, or assert
that a recorded verdict is true. Do not add a new service, database, telemetry, or
external dependency.

## Verification Commands

```bash
.venv/bin/python -m pytest tests/test_gates.py -v
.venv/bin/python -m pytest tests/test_cli.py -v
.venv/bin/python -m pytest tests/test_docs_consistency.py -v
.venv/bin/python -m pytest tests/ -v
```

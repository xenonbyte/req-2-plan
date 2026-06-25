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
  verdict is recorded (`execution/final-review.md` carrying `Verdict: Approved`).
  This makes the recorded verdict an **archive-time precondition** and closes a
  real structural hole: today an agent can flip every PLAN-TASK checkbox and
  archive while silently skipping the final review.
- **Part C (docs-only):** document that cross-stage trace closure is intentionally
  concentrated at the PLAN quality gate, and that stages 04–06 deliberately have
  no forward full-coverage gate.
- **Part D (adjacent, P2):** three independently-shippable write-safety /
  transactional-consistency fixes (Context Pack write, install manifest temp,
  run-reopen rollback), captured at the maintainer's request. Not part of the SDD
  theme and not a blocker for A–C.

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
discipline** and a **recorded final-review verdict**:

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

The transferable mechanism is controller hygiene and a recorded review verdict —
not a new runtime, not a worktree model, and not CLI-side correctness
verification.

## Goals

- Reduce controller context bloat and subagent cost during execution
  (file handoffs, explicit model selection).
- Raise the quality and honesty of per-task and whole-branch completion evidence.
- Make an approved final whole-branch review verdict an archive-time precondition
  for executing runs, at the same trust level as the existing PLAN-TASK checkbox
  cross-check. (No durability or forensic claim: the marker is a working-tree
  precondition read at archive time, not a shared, committed record.)
- Keep every change Python-only and dependency-light (stdlib + `pyyaml`).
- Preserve the CLI/agent boundary: the CLI validates structure and recorded state,
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
- Do **not** present the marker gate as a hard correctness barrier. `--force` is
  its intended operator bypass for abandoned/superseded runs, and fabrication is
  out of scope (same trust level as the checkbox gate); the gate is an
  archive-time audit precondition, not a guarantee that the review happened or was
  correct.

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

Part A is prose-only and must stay terse. Prefer one-line additions over new
subsections wherever a line suffices, and keep the combined `r2p-execute` surface
from ballooning — a long rule list dilutes adherence and costs context on every
load. Treat the upstream 400+ line skill as a source of principles, not a length
target.

#### FR-A1: Model Selection

Add a `## Model Selection` subsection that follows the validated wording of the
`superpowers:subagent-driven-development` "Model Selection" section, adapted only
to r2p terms. Use the least powerful model that can handle each role:

- **Mechanical implementation** (isolated functions, clear specs, 1–2 files): a
  fast, cheap model. Most tasks are mechanical when the PLAN is well-specified.
- **Integration / judgment** (multi-file coordination, pattern matching,
  debugging): a standard model.
- **Architecture / design**: the most capable available model. The final
  whole-branch review is one of these — dispatch it on the most capable model,
  not the session default.
- **Review tasks**: the same judgment, scaled to the diff's size, complexity, and
  risk — a small mechanical diff does not need the most capable model; a subtle
  concurrency change does.

Always specify the model explicitly when dispatching; an omitted model inherits
the session model — often the most capable and most expensive — which silently
defeats this section. **Turn count beats token price:** the cheapest models
routinely take 2–3× the turns on multi-step work, costing more overall, so use a
mid-tier model as the floor for reviewers and for implementers working from prose
descriptions; drop to the cheapest tier only when the task carries the complete
code to write (transcription plus testing — in r2p, a PLAN-TASK whose `Skeleton`
is complete code) or for single-file mechanical fixes.

The `## Model Selection` prose is authored in the two full-prose surfaces (the
claude command and the codex skill) and is inherited by opencode, whose commands
`install.py` derives from the claude command. The gemini surface is a four-line
launcher shim (`command = {{R2P_BIN_DIR}}/r2p-execute`) that carries no SDD prose,
so it is intentionally left unedited. The guidance is actionable wherever a
runtime's subagent dispatch accepts an explicit model; where it does not, it is
inert there and is not force-fit — a runtime-capability question, orthogonal to
which surface carries the prose.

#### FR-A2: Diff and history as files, not inline

Replace the inline-diff instruction in Step 5. The controller records the task's
BASE commit before dispatching the implementer, and after `DONE` ensures the run's
gitignored scratch dir exists (`mkdir -p .req-to-plan/<work-id>/logs`), writes the
diff to `<work-id>/logs/task-N-diff.md`
(`git diff -U10 <base-commit> HEAD > .req-to-plan/<work-id>/logs/task-N-diff.md`),
and hands the reviewer the **file path**, not the diff text. The reviewer-input
list changes "The diff" to the diff file path. The diff is transient, possibly
large review scratch, so it goes under `logs/` (ignored by `.req-to-plan/.gitignore`
via `/*/logs/`), never under the tracked `execution/` path — keeping it out of
`git status` and immune to an accidental broad `git add` during execution.

#### FR-A3: BASE commit rule

State explicitly: record BASE (`git rev-parse HEAD`) before dispatching the
implementer, and **never use `HEAD~1`** as BASE — it silently drops all but the
last commit of a multi-commit task.

For Task 1, this BASE is also the run's `<execution-base-commit>` — the range
anchor for the final whole-branch review (FR-A6). Persist it immediately in
tracked execution state by adding an `Execution BASE: <execution-base-commit>`
line to `execution/progress.md`. On resume, the final review reads that line back
as `<execution-base-commit>` rather than recomputing the range from `HEAD` or the
latest task range — a recomputed range would silently drop earlier task commits,
the same multi-commit-loss failure `HEAD~1` causes. If the line is missing, stop
and ask the human for the original Task 1 BASE instead of inferring a range.

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
5. after the final review settles, write `execution/final-review.md` recording the
   reviewed range, a one-line summary, and the verdict — `Verdict: Approved` when
   the review is clean, `Verdict: Changes Requested` while findings remain;
6. after any final-review fix wave, regenerate
   `.req-to-plan/<work-id>/logs/final-diff.md` from the same
   `<execution-base-commit>` to current `HEAD`, re-run the full verification suite,
   re-dispatch the final whole-branch reviewer with the refreshed diff and output,
   and repeat until the post-fix reviewer is clean; only then append
   `Verdict: Approved` as the final unfenced verdict (the gate reads the last one,
   FR-B1). Note that `r2p-archive` refuses to archive an executing run unless this
   file's current verdict is `Verdict: Approved` (Part B).

### Part B — Final-review marker gate (CLI-side)

#### FR-B1: New gate function

Add `gates.py::check_final_review_recorded(run_dir) -> GateResult`, placed beside
`check_execution_complete`, reusing `_read_regular_text_no_symlink` (symlink and
non-regular-file rejection) and `unfenced_markdown_lines` (fenced code is
ignored). It validates the current verdict in `execution/final-review.md`:

- file missing → fail.
- file is a symlink or not a regular file → fail (refuse to read outside the run
  directory).
- no unfenced line beginning `Verdict:` → fail (verdict not recorded).
- unsupported unfenced `Verdict:` value → fail (allowed values are `Approved`
  and `Changes Requested`, case-insensitive).
- when multiple unfenced `Verdict:` lines exist, the **last** one is the current
  verdict; earlier verdict lines are historical audit text.
- current verdict `Changes Requested` → fail (resolve findings and record
  `Verdict: Approved` as the final unfenced verdict).
- current verdict `Approved` → pass.

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

No archive-path output and no `check_final_review_recorded` message may make an
affirmative correctness claim. Every gate failure message states it is a
presence check on the review audit trail, not a correctness guarantee. The
archive success path stays state-only (`archived`); no affirmative "review
approved" / "verified" wording is added anywhere. The executable honesty guard
must allow required protocol literals such as `Verdict: Approved` and the
negated disclaimer `not a correctness guarantee` in **any** gate failure
message, while rejecting affirmative correctness claims such as "verified",
"validated", "guaranteed correct", or "review approved".

The guard cannot be a naive substring match: `correct` and `guarantee` appear in
both the allowed disclaimer (`not a correctness guarantee`) and rejected claims
(`guaranteed correct`), and `Approved` is both a protocol literal (allowed) and
part of `review approved` (rejected). It must match affirmative claim
phrases/patterns and exempt the exact disclaimer plus protocol literals — never
match bare tokens. This requirement is enforced by an executable test (the
honesty guard in the Test Plan), not by prose intention alone.

Failure messages are mode-specific (missing file; symlink / non-regular; no
unfenced `Verdict:` line; unsupported current verdict; current verdict
`Changes Requested`). Each carries the presence-check disclaimer, and the
honesty allowlist must cover every message that embeds `Verdict: Approved` or
`not a correctness guarantee`. The missing / not-approved variant reads:

```text
Final whole-branch review not approved: execution/final-review.md is missing,
or its current (last unfenced) 'Verdict:' line is not 'Approved'. Presence check
on the review audit trail — not a correctness guarantee. Record
'Verdict: Approved', or re-run with --force to archive an abandoned run.
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

### Part D — Adjacent write-safety & transactional hardening (P2)

These three items are **separate from the SDD theme** and are captured here at the
maintainer's request. Each is a low-risk consistency fix, independently shippable,
and **not a blocker** for Parts A–C. All three are verified against current code.

#### FR-D1: Atomic, symlink-checked Context Pack write

`context_pack.py::write_context_pack` writes `02-project-context.json` and
`02-project-context.md` with plain `Path.write_text` and no symlink check on the
two targets. `run-start` and `context-build` guard the run directory, but a symlink
planted at either file inside an existing run dir would be written through
(`write_text` follows symlinks). Fix: reject when either target `is_symlink()`,
then write each via `atomic_write_text` (unique temp + `O_EXCL` + `O_NOFOLLOW` +
`os.replace`), matching the write-safety style used elsewhere. Tests
(`tests/test_context_pack.py`): a symlink planted at the json or md path is
rejected (target not written through); a normal build still produces both files.

#### FR-D2: Unique-temp manifest write in install

`install.py` writes the manifest through a fixed sibling temp `manifest.yaml.tmp`,
validates it is not a symlink (`_validate_install_path`), then `write_text` +
`replace`. It does not use the unique-temp + `O_EXCL` + `O_NOFOLLOW` pattern, so a
fixed-name collision (rare — install is not normally concurrent) and a
check-then-write TOCTOU window remain. Fix: add an install-specific unique-temp
write helper that preserves the existing install path validation (manifest path and
parent) but writes through an `O_EXCL` unique temp like `atomic_write_text`; it
cannot reuse `atomic_write_text` verbatim because install carries its own
path-validation rules. Low risk, not a blocker. Tests (`tests/test_install.py`):
the manifest is still written and replaced; a symlink planted at the temp path is
rejected.

#### FR-D3: Transactional run-reopen from EXECUTING

`cli.py::_cmd_run_reopen` saves the new run (`new_mgr.save`) first, then — for an
`EXECUTING` source — transitions the source to `CLOSED_AT_PLAN_CHECKPOINT` and saves
it. If the source save fails, the new run already exists while the source stays
`EXECUTING` — a partial state. Unlike `_cmd_run_archive`, which rolls back on save
failure, reopen has no rollback. Fix (either): on source-save failure, remove the
newly created run; or persist the source transition first and roll the source back
if the new-run save fails — matching archive's transactional level. Low
probability, no file-safety breakage. Tests (`tests/test_cli.py`): a simulated
source-save failure leaves no orphan new run and a consistent source status; a
normal reopen is unchanged.

## Marker File Contract

```text
Path:     <run-dir>/execution/final-review.md
Seeded:   no (absent by default; written by the agent's final-review step)
Required: a regular, non-symlink file containing at least one unfenced
          Verdict: line. The final unfenced Verdict: line is the current verdict.
Pass:     current verdict is Approved
Fail:     missing file | symlink / non-regular | no Verdict line |
          unsupported current verdict | current verdict is Changes Requested
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

No new file is created for tests; no new module, service, or dependency. The
opencode surface needs no edit — `install.py` derives its commands from the claude
command (1), so it inherits Part A automatically. The gemini `r2p-execute.toml` is
a four-line launcher shim that carries no SDD prose and is intentionally left
unedited.

Part D (adjacent, P2) additionally touches `tools/workflow_cli/context_pack.py`,
`tools/workflow_cli/install.py`, and `tools/workflow_cli/cli.py` (reopen), with
focused tests in `tests/test_context_pack.py`, `tests/test_install.py`, and
`tests/test_cli.py`. These can land in a change separate from Parts A–C.

## Acceptance Criteria

- Both `r2p-execute` surfaces contain the Part A additions and stay in sync; all
  pre-existing required SDD tokens remain present and `r2p-gap-open` is absent.
- `check_final_review_recorded` passes only on a regular `execution/final-review.md`
  whose final unfenced `Verdict:` line is `Verdict: Approved`; it fails on a
  missing file, a symlink/non-regular file, a missing verdict line, an
  unsupported current verdict value, and a final `Verdict: Changes Requested`; a
  `Verdict:` inside a fenced code block does not count.
- Archiving an `EXECUTING` run with a complete ledger but no approved
  final-review marker is rejected with `EXIT_GATE_FAIL`; adding the approved
  marker lets it pass; `--force` bypasses both gates.
- Archiving a `CLOSED_AT_PLAN_CHECKPOINT` run does not require a final-review
  marker.
- `run-execute-start` does not create `execution/final-review.md`.
- No archive-path output and no gate message may make an affirmative correctness
  claim; the executable guard allows required protocol literals and the negated
  disclaimer in any gate failure message, while rejecting affirmative wording
  such as `verified`, `validated`, `guaranteed correct`, and `review approved`.
  The guard is phrase/pattern-based, not a bare-token substring match.
- Existing exit codes and JSON-mode payloads are unchanged.
- `tests/test_docs_consistency.py` guards the new tokens and stays green; the full
  suite stays green.

## Test Plan

- `tests/test_gates.py`: missing file → fail; final `Verdict: Approved` → pass;
  final `Verdict: Changes Requested` → fail; unsupported current verdict value →
  fail; symlink → fail; non-regular (FIFO) → fail without blocking; `Verdict:`
  inside a code fence → not counted; multiple unfenced verdict lines use the
  last verdict (`Changes Requested` then `Approved` passes, `Approved` then
  `Changes Requested` fails).
- `tests/test_cli.py`: executing-run archive blocked when the marker is missing
  even with a complete ledger; passes with an approved marker; `--force`
  overrides; closed-at-plan archive unaffected. Update the existing success cases
  (`test_archive_executing_run_with_complete_ledger`,
  `test_archive_passes_when_ledger_covers_all_plan_tasks`, and any other
  executing-run archive-success test) to seed an approved
  `execution/final-review.md`. Add the FR-B4 honesty guard over the archive
  output and every gate failure message: allowlist coverage so each mode-specific
  message passes, plus negative tests that affirmative claims ("verified",
  "guaranteed correct", "review approved") are rejected while the disclaimer
  `not a correctness guarantee` is not (the guard must be phrase/pattern-based,
  not a bare-token substring match).
- `tests/test_docs_consistency.py`: add a stable subset of new tokens
  (`Model Selection`, `HEAD~1`, `execution/final-review.md`, `Verdict: Approved`,
  `re-run the full verification suite`) to the execute-surface required set.

## Migration

A run already in `EXECUTING` before this change has no `execution/final-review.md`.
After upgrade, archiving it requires the agent's final-review step to write the
marker (the normal path) or `--force` (abandoned/superseded run). No run state is
mutated by the upgrade itself.

## Interaction with auto-commit-and-archive

The `r2p-execute` skill auto-archives on completion, and `r2p-archive` performs a
path-scoped git commit. This change is compatible with that flow; the relevant
facts, verified against code:

- **gitignore boundary** (`.req-to-plan/.gitignore`): `/archive`,
  `/.workflow-active`, and `/*/logs/` are ignored. The run's `execution/` directory
  is **tracked**; `<work-id>/logs/` is **ignored**.
- **The archive commit is path-scoped and post-move.** `commit_requirement_dir`
  runs `git add -- <.req-to-plan/.gitignore> <run-dir>` (no `-A`, no `-f`) *after*
  `shutil.move` has already moved the run dir into the gitignored `/archive`. It
  records the **removal** of the previously-tracked run files; the moved-away
  `execution/` artifacts are never staged by it.
- **The marker gate is read-only and pre-commit.** `check_final_review_recorded`
  only reads `execution/final-review.md` from the working tree, before the move and
  commit. It adds an archive precondition with zero git interaction.
- **New `execution/` artifacts are not committed by r2p.** `execution/final-review.md`
  behaves like the existing `execution/progress.md` and `task-N-report.md`: created
  during execution, never staged by the per-task code commits (which stage only
  task files), and moved into the gitignored archive at archive time. No r2p flow
  runs a path-scoped commit over the run dir between marker-write and the post-move
  archive commit, so the marker is never committed.
- **Transient diff scratch lives under `logs/` (FR-A2),** not `execution/`, so it is
  gitignored and cannot be picked up by any `git add`.
- **Behavioral note (by design, not a conflict):** a `Verdict: Changes Requested`
  marker blocks auto-archive until the verdict becomes `Approved` (or `--force`) —
  the same "stuck if incomplete" property the existing completion gate already has,
  not a new failure class.

## Risks

- **False confidence.** A presence gate that read as "correctness verified" would
  regress into the theater this project previously rejected. Eliminated by FR-B4
  and its executable guard: every gate message is a presence/audit statement at
  the same trust level as the existing checkbox gate.
- **Bypass and trust boundary (by design, not a defect).** `--force` is the
  intended operator bypass for abandoned/superseded runs, and an agent could write
  a fake `Verdict: Approved` — the same trust level as fabricated checkboxes. The
  gate is an archive-time audit precondition, not a hard barrier; it closes the
  realistic forgetful/lazy skip of the final review, which is its whole and stated
  purpose.
- **Enforcement ahead of evidence.** The gate guards a failure mode not yet
  observed in this project, overriding the recorded "wait for a real false-green"
  decision. Bounded: the gate is strictly additive and revertible (remove one
  function plus one wiring line), makes no correctness or durability claim, and
  adds exactly one archive-time precondition — so the override is low-cost and
  easy to undo if it proves noisy.
- **Existing-test breakage.** Adding the gate turns previously-passing
  executing-archive tests red; the test plan updates them in the same change.
- **Surface drift.** The two `r2p-execute` surfaces can fall out of sync; the
  docs-consistency token guard catches divergence on the guarded tokens.
- **Honesty-guard brittleness.** The FR-B4 guard asserts on our own output prose,
  and the project elsewhere warns that over-asserting exact prose is brittle. Keep
  it pattern-based and minimal — match affirmative claim phrases only, exempt the
  exact disclaimer and protocol literals — so it guards intent without pinning
  full message text.

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

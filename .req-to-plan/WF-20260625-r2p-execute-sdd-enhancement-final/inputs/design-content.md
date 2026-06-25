# Design

## Design Summary

The change has four independent slices that share one principle — **the CLI
validates structure and recorded state; the agent produces all semantic content**:

1. **Part A (template prose, two synced surfaces):** fold controller-discipline
   into both `r2p-execute` surfaces — model selection, diff-as-file handoff, a
   BASE-commit rule, reviewer-prompt discipline, continuous execution +
   evidence-before-claims, and a stronger final whole-branch review that re-runs
   the suite and writes a `execution/final-review.md` verdict marker.
2. **Part B (one CLI gate + one wiring point):** a new
   `gates.py::check_final_review_recorded(run_dir)` that reads the marker's current
   verdict, wired into `_cmd_run_archive` right after `check_execution_complete`,
   for `EXECUTING` runs only, bypassable by `--force`. The marker is **not seeded**.
3. **Part C (docs):** two `CLAUDE.md` Invariants lines + an updated Test-rules
   token description; no hardcoded test count.
4. **Part D (separable P2):** symlink-checked atomic Context Pack write,
   unique-temp install-manifest write, transactional run-reopen — each landable in
   a change separate from A–C.

No state transition, artifact schema, tier semantic, or other gate changes. New
mechanism is exactly one gate function reusing existing helpers; the marker is a
working-tree precondition, not a committed record. Closes RISK-HONESTY-001 via the
FR-B4 guard, RISK-DRIFT-001 via extended docs-consistency tokens.

## Current Code Evidence

Verified against the current tree:

- `gates.py::check_execution_complete(run_dir)` — the only archive completion gate.
  Reads `execution/progress.md` via `_read_regular_text_no_symlink` (rejects
  symlink/non-regular), scans `unfenced_markdown_lines` for unchecked
  `- [ ] PLAN-TASK-*`, cross-checks checked IDs against frozen PLAN task IDs,
  rejects an empty ledger. Returns `GateResult(passed, issues, exit_code)` with
  `EXIT_GATE_FAIL` on failure. **The new gate mirrors this shape exactly** and
  reuses the same two helpers.
- `gates.py::_read_regular_text_no_symlink(path)` returns
  `(text|None, error|None)` where error ∈ {`missing`,`symlink`,`not_regular`}
  using `O_NOFOLLOW|O_NONBLOCK` + `S_ISREG`. Reused verbatim by the new gate.
- `gates.py::unfenced_markdown_lines(content)` yields `(line, start, end)` for
  lines outside fenced code — so a `Verdict:` inside ``` ``` is ignored (AC-002).
- `cli.py::_cmd_run_archive` — the `EXECUTING and not args.force` block runs
  `check_execution_complete` and `print_and_exit`s on failure. The new gate is
  inserted **after** that passes, inside the same block (FR-B3). Success payload is
  state-only: `{"work_id", "status": "archived", "archived_to"}` — no correctness
  word (FR-B4 / AC-007 preserved). `--force` already bypasses the block.
- `cli.py::_cmd_run_execute_start` seeds `execution/progress.md` only; it does not
  create any final-review file — so FR-B2 is "leave as-is" plus a regression test.
- `cli.py::_cmd_run_reopen` saves the new run (`new_mgr.save(new_record)`) first,
  then for an `EXECUTING` source transitions it to `CLOSED_AT_PLAN_CHECKPOINT` and
  `source_mgr.save(source_record)`. A source-save failure leaves the orphan new run
  with no rollback (contrast `_cmd_run_archive`, which moves-back on save failure).
- `context_pack.py::write_context_pack(pack, run_dir)` writes both
  `02-project-context.{json,md}` with plain `Path.write_text` (follows symlinks),
  no per-target symlink check.
- `install.py` (lines ~207–215) writes the manifest through a fixed-name sibling
  temp `manifest.yaml.tmp`, validates both `manifest_path` and `tmp` via
  `_validate_install_path` (rejects symlink), then `tmp.write_text` + `tmp.replace`.
  Fixed-name → no `O_EXCL` uniqueness; a check-then-write TOCTOU window exists.
- `atomic.py::atomic_write_text` / `_open_unique_sibling_tmp` — the unique-temp
  `O_WRONLY|O_CREAT|O_EXCL(|O_NOFOLLOW|O_CLOEXEC)` pattern FR-D1 reuses directly and
  FR-D2 mirrors (it cannot reuse `atomic_write_text` verbatim because install
  carries its own `_validate_install_path` rules).
- `tools/workflow_cli/agent_templates/{claude/commands/r2p-execute.md,codex/skills/r2p-execute/SKILL.md}`
  — ~122/123 lines. Step 5 currently records the diff **inline**
  (`git diff -U10 <base-commit> HEAD`) and hands "The diff" to the reviewer; the
  Final Whole-Branch Review includes an inline `git diff -U10 <merge-base> HEAD`,
  does not re-run the suite, and writes no marker. No `## Model Selection` exists.
- `tests/test_docs_consistency.py` already guards a required SDD token set and
  `r2p-gap-open` absence on both surfaces; FR-C1 extends the token tuple.

## Requirements Coverage

| Requirement | DES |
|---|---|
| FR-A1 Model Selection | DES-TMPL-001 |
| FR-A2 diff/history as files under logs/ | DES-TMPL-001 |
| FR-A3 BASE commit rule (no HEAD~1) | DES-TMPL-001 |
| FR-A4 reviewer-prompt discipline | DES-TMPL-001 |
| FR-A5 continuous execution + evidence-before-claims | DES-TMPL-001 |
| FR-A6 stronger final review + write final-review.md | DES-TMPL-001 |
| FR-B1 check_final_review_recorded | DES-GATE-001 |
| FR-B2 not seeded | DES-GATE-002 |
| FR-B3 archive wiring (EXECUTING-only, --force bypass) | DES-GATE-002 |
| FR-B4 honest labeling + executable guard | DES-HONEST-001 |
| FR-C1 CLAUDE.md invariants + token description | DES-DOCS-001 |
| FR-D1 atomic symlink-checked Context Pack write | DES-WRITE-001 |
| FR-D2 unique-temp manifest write | DES-WRITE-002 |
| FR-D3 transactional run-reopen | DES-STATE-001 |

## Options Considered

- **Marker location — `execution/final-review.md` (chosen) vs a committed record.**
  Chosen: `execution/` sibling of `progress.md`, working-tree only, gitignored-into-archive
  at archive time, never staged by per-task commits. Rejected a committed/forensic
  record — out of scope, and would couple the gate to git side effects
  (RISK-HONESTY-001 framing: presence, not durability).
- **Verdict encoding — last unfenced `Verdict:` line (chosen) vs first / single.**
  Chosen: multiple unfenced verdict lines allowed, the **last** is current — lets
  the agent append `Changes Requested` then `Approved` after a fix wave without
  rewriting history (FR-A6/FR-B1). Fenced verdict lines ignored via
  `unfenced_markdown_lines`.
- **Gate placement — after `check_execution_complete`, EXECUTING-only (chosen) vs
  a standalone command / all archive paths.** Chosen: same block, after completion
  passes, so `--force` bypasses both and a `CLOSED_AT_PLAN_CHECKPOINT` run never
  executed is unaffected (AC-003/AC-004). Rejected a separate gate command — extra
  surface for no benefit.
- **Honesty guard — phrase/pattern allow+deny (chosen) vs bare-token substring.**
  Rejected substring: `correct`/`guarantee` appear in both the allowed disclaimer
  (`not a correctness guarantee`) and rejected claims (`guaranteed correct`), and
  `Approved` is both a protocol literal and part of `review approved`. Chosen:
  match affirmative claim phrases/patterns, exempt the exact disclaimer + protocol
  literals (RISK-GUARD-001: minimal, pattern-based).
- **Diff handoff — file path under `logs/` (chosen) vs inline vs under `execution/`.**
  Rejected inline (controller bloat). Rejected `execution/` (tracked → risk of an
  accidental `git add`). Chosen `<work-id>/logs/` (gitignored via `/*/logs/`).
- **FR-D3 rollback — remove orphan new run on source-save failure (chosen) vs
  persist source transition first then roll back.** Chosen the first: the new run
  was just `mkdir`-ed and saved, so removing it is a clean, local undo with no
  source mutation ordering change; matches archive's transactional level with the
  smaller diff.
- **FR-D2 — new install-local unique-temp helper (chosen) vs reuse
  `atomic_write_text`.** Chosen a helper that keeps `_validate_install_path` on
  both manifest and temp paths but opens an `O_EXCL`/`O_NOFOLLOW` unique temp;
  `atomic_write_text` cannot be reused verbatim because it lacks install's path
  validation.

## Chosen Design

### DES-ARCH-001 — Four independent slices, CLI/agent boundary preserved
The change is additive and revertible. Part A is prose-only across two synced
surfaces (opencode derives from claude via `install.py`; gemini shim untouched).
Part B adds one gate function + one wiring line. Part C is docs. Part D is three
separable write-safety fixes. No transition/schema/tier/other-gate change; no new
module, service, dependency, or worktree. Closes SCOPE-IN-001..005; honors
SCOPE-OUT-001..008.

### DES-TMPL-001 — Part A r2p-execute prose (both surfaces, byte-synced on tokens)
Terse, one-line-preferred additions; the upstream 400+ line skill is a principle
source, not a length target (RISK-OVERFLOW-001). Edits:
- **`## Model Selection`** subsection (FR-A1): least-powerful-model-that-fits per
  role (mechanical→cheap/fast; integration/judgment→standard; architecture &
  **final whole-branch review**→most capable); always specify the model explicitly
  (omitted ⇒ inherits session model); "turn count beats token price" floor note.
  Inert on runtimes whose dispatch takes no explicit model (gemini shim excluded).
- **Step 5 diff-as-file** (FR-A2): record BASE before dispatch; after `DONE`,
  `mkdir -p .req-to-plan/<work-id>/logs` then
  `git diff -U10 <base-commit> HEAD > .req-to-plan/<work-id>/logs/task-N-diff.md`;
  hand the reviewer the **file path**, not the diff text. Reviewer-input list
  changes "The diff" → the diff file path.
- **BASE commit rule** (FR-A3): record BASE = `git rev-parse HEAD` before
  dispatching; **never use `HEAD~1`** (drops all but the last commit of a
  multi-commit task).
- **Reviewer-prompt discipline** (FR-A4): copy the plan's Global Constraints
  verbatim into the reviewer prompt; never pre-judge severity or tell the reviewer
  what not to flag; never paste accumulated prior-task summaries into a later
  dispatch.
- **Continuous execution + evidence** (FR-A5): execute all PLAN-TASKs without
  pausing to ask "should I continue?"; stop conditions are unresolvable `BLOCKED`,
  an upstream defect needing repair, the dirty-tree block, or all tasks done.
  `Verification` requires fresh command output; "should pass"/"looks correct" is
  not evidence and the implementer may not report `DONE` without it.
- **Stronger final whole-branch review** (FR-A6): (1) re-run the full verification
  suite on final HEAD and attach fresh output; (2) walk the PLAN task-by-task as a
  line-by-line checklist; (3) dispatch **one** fix subagent carrying the complete
  findings list; (4) run on the most capable model (xref FR-A1); (5) write
  `execution/final-review.md` with the reviewed range, a one-line summary, and the
  verdict — `Verdict: Approved` when clean, `Verdict: Changes Requested` while
  findings remain, appending `Verdict: Approved` as the final unfenced verdict
  after a fix wave clears them. Note that `r2p-archive` refuses an executing run
  unless the current verdict is `Verdict: Approved`.
All pre-existing required SDD tokens preserved; `r2p-gap-open` stays absent
(SCOPE-OUT-005). Both surfaces kept in sync on guarded tokens (RISK-DRIFT-001).

### DES-GATE-001 — `gates.py::check_final_review_recorded(run_dir) -> GateResult`
Placed beside `check_execution_complete`. Reads `execution/final-review.md` via
`_read_regular_text_no_symlink`; scans `unfenced_markdown_lines` for lines
beginning `Verdict:` (case-insensitive on the value). Decision table:
- missing → fail; symlink → fail; not_regular → fail.
- no unfenced `Verdict:` line → fail.
- collect unfenced `Verdict:` values in order; the **last** is current.
- current value not in {`approved`,`changes requested`} → fail (unsupported).
- current `changes requested` → fail.
- current `approved` → pass.
Failure → `GateResult(passed=False, issues=[...], exit_code=EXIT_GATE_FAIL)`;
pass → `exit_code=0`. Every failure message is a presence-check statement (FR-B4).

### DES-GATE-002 — Archive wiring (FR-B3) + not-seeded (FR-B2)
In `_cmd_run_archive`, inside `EXECUTING and not args.force`, after
`check_execution_complete` passes, call `check_final_review_recorded(run_dir)` and
`print_and_exit(format_error(<issue text>, exit_code=gate.exit_code), gate.exit_code)`
on failure. Applies only to `EXECUTING` runs; `--force` bypasses both gates
(AC-003/AC-004). `_cmd_run_execute_start` is unchanged — the marker stays absent so
the gate has teeth (regression test asserts non-creation, AC-005).

### DES-HONEST-001 — Honest labeling + executable guard (FR-B4)
Every gate failure message embeds the presence-check disclaimer
`Presence check on the review audit trail — not a correctness guarantee.` and may
embed the protocol literal `Verdict: Approved`. The missing/not-approved variant is
the exact text in the requirement. The executable guard (a test helper) is
phrase/pattern-based: it **rejects** affirmative claim patterns (`verified`,
`validated`, `guaranteed correct`, `review approved`) and **exempts** the exact
disclaimer phrase and protocol literals — never a bare-token match (RISK-GUARD-001).
The archive success payload stays `status: archived` only (no correctness word).

### DES-DOCS-001 — Closure-model docs + token description (FR-C1, Part C)
Add two `CLAUDE.md` Invariants lines: (a) the final-review marker gate is
presence/audit at the same trust level as the checkbox gate and does not verify
correctness; (b) cross-stage trace closure is enforced at the PLAN quality gate
(every SPEC consumed, SCOPE-IN carried, RISK closed); intermediate stages enforce
only "cited upstream ID ⇒ closure tag"; 04–06 have no forward full-coverage gate.
Update the Test-rules `r2p-execute` token description to list the new guarded
tokens. No hardcoded test count introduced.

### DES-WRITE-001 — Atomic, symlink-checked Context Pack write (FR-D1)
In `write_context_pack`, reject when either `02-project-context.json` or
`02-project-context.md` `is_symlink()`, then write each via `atomic_write_text`
(unique temp + `O_EXCL` + `O_NOFOLLOW` + `os.replace`). Behavior otherwise
unchanged (returns `(md_path, json_path)`).

### DES-WRITE-002 — Unique-temp manifest write in install (FR-D2)
Add an install-local helper that keeps `_validate_install_path` on both the
manifest path and the temp path but writes through an `O_EXCL`/`O_NOFOLLOW` unique
temp (like `_open_unique_sibling_tmp`), then `os.replace`. Replaces the fixed-name
`manifest.yaml.tmp` write at install.py ~209–215. Closes the fixed-name collision +
TOCTOU window without weakening install path validation.

### DES-STATE-001 — Transactional run-reopen from EXECUTING (FR-D3)
In `_cmd_run_reopen`, after `new_mgr.save(new_record)`, wrap the EXECUTING-source
transition+save so that if `source_mgr.save` fails, the freshly created
`new_run_dir` is removed (and the in-memory new record discarded) before
re-raising — leaving no orphan new run and the source still consistently
`EXECUTING`. A normal reopen is unchanged.

## Decision Requests

none

## Rollback

Each slice reverts independently. Part B: delete `check_final_review_recorded` and
its one wiring line in `_cmd_run_archive` (gate is strictly additive,
RISK-EVIDENCE-001). Part A: revert the two template files (token guard would catch
a partial revert). Part C: revert the `CLAUDE.md` lines. Part D items revert one
function each. No data migration, no state mutation, no schema change — a run
already `EXECUTING` simply needs the agent's final-review step (or `--force`) after
upgrade (Migration section of the requirement).

## Observability

- Gate failures surface through the existing `print_and_exit` path with
  `EXIT_GATE_FAIL` (3) and mode-specific issue text (missing / symlink /
  non-regular / no verdict line / unsupported / changes-requested), consistent
  with `check_execution_complete`. JSON mode (`R2P_JSON=1`) unchanged.
- The marker file itself (`execution/final-review.md`) is the human-readable audit
  record of the final review (range, summary, verdict history).
- No new logs, metrics, or telemetry (SCOPE-OUT-004). Test suite + docs-consistency
  guard are the regression observability surface.

## SPEC Handoff

SPEC must pin, as behavior contracts:
- DES-GATE-001 → the full decision table as discrete contracts (missing, symlink,
  non-regular/FIFO, no verdict line, unsupported value, last-of-many verdict,
  fenced-verdict-ignored, approved-pass), each with exit code.
- DES-GATE-002 → archive-blocked / archive-passes-with-marker / `--force`-bypass /
  closed-at-plan-unaffected / not-seeded contracts and exit codes.
- DES-HONEST-001 → the exact disclaimer + protocol literals the guard must exempt
  and the affirmative patterns it must reject; the precise missing/not-approved
  message text.
- DES-TMPL-001 → the concrete guarded-token set to add to docs-consistency
  (`Model Selection`, `HEAD~1`, `execution/final-review.md`, `Verdict: Approved`,
  `re-run the full verification suite`) and the byte-sync requirement.
- DES-WRITE-001/002, DES-STATE-001 → the symlink-reject / unique-temp / rollback
  contracts and their focused tests.
Config/data contracts: the Marker File Contract (path, seeded=no, regular
non-symlink, last unfenced `Verdict:` is current, pass on `Approved`).

## Trace
<!-- Map this stage's IDs to upstream/downstream. R3 derives & checks closure. -->
| This ID | Upstream | Status |
|---|---|---|
| DES-ARCH-001 | SCOPE-IN-001..005 | open |
| DES-TMPL-001 | SCOPE-IN-001 (FR-A1..A6), RISK-OVERFLOW-001, RISK-DRIFT-001 | open |
| DES-GATE-001 | SCOPE-IN-002 (FR-B1) | open |
| DES-GATE-002 | SCOPE-IN-002 (FR-B2, FR-B3) | open |
| DES-HONEST-001 | SCOPE-IN-002 (FR-B4), RISK-HONESTY-001, RISK-GUARD-001 | open |
| DES-DOCS-001 | SCOPE-IN-003 (FR-C1) | open |
| DES-WRITE-001 | SCOPE-IN-004 (FR-D1), RISK-WRITE-001 | open |
| DES-WRITE-002 | SCOPE-IN-004 (FR-D2), RISK-WRITE-001 | open |
| DES-STATE-001 | SCOPE-IN-004 (FR-D3), RISK-STATE-001 | open |
| SCOPE-IN-001 | carried to SPEC | closed |
| SCOPE-IN-002 | carried to SPEC | closed |
| SCOPE-IN-003 | carried to SPEC | closed |
| SCOPE-IN-004 | carried to SPEC | closed |
| SCOPE-IN-005 | carried to SPEC | closed |
| RISK-HONESTY-001 | DES-HONEST-001 | mitigated |
| RISK-GUARD-001 | DES-HONEST-001 | mitigated |
| RISK-DRIFT-001 | DES-TMPL-001, DES-DOCS-001 | mitigated |
| RISK-EVIDENCE-001 | DES-GATE-002, Rollback | mitigated |
| RISK-OVERFLOW-001 | DES-TMPL-001 | mitigated |
| RISK-WRITE-001 | DES-WRITE-001, DES-WRITE-002 | mitigated |
| RISK-STATE-001 | DES-STATE-001 | mitigated |

## Upstream Summary (read-only)
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

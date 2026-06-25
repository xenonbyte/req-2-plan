# Spec

## Behavior Contracts

### SPEC-GATE-001 — `check_final_review_recorded(run_dir)` decision table
New function in `tools/workflow_cli/gates.py`, placed beside
`check_execution_complete`, signature `check_final_review_recorded(run_dir: Path) -> GateResult`.
Reads `run_dir / "execution" / "final-review.md"` via `_read_regular_text_no_symlink`
(gates.py) and scans for unfenced lines via `unfenced_markdown_lines` (defined in
`markdown.py`, imported by gates.py). A "verdict line" is an unfenced line whose
stripped text starts with `Verdict:` (case-insensitive on the `Verdict:` key); its
value is the remainder, stripped, compared case-insensitively. Contracts (implements
DES-GATE-001):

| # | Input condition | Result | exit_code |
|---|---|---|---|
| a | file missing (`_read..` → `missing`) | fail | EXIT_GATE_FAIL (3) |
| b | path is a symlink (`→ symlink`, incl. ELOOP) | fail | 3 |
| c | not a regular file (`→ not_regular`, e.g. FIFO) | fail (no block) | 3 |
| d | regular file, zero unfenced `Verdict:` lines | fail | 3 |
| e | current (last) verdict value ∉ {`approved`,`changes requested`} | fail (unsupported) | 3 |
| f | current (last) verdict value == `changes requested` | fail | 3 |
| g | current (last) verdict value == `approved` | **pass** | 0 |
| h | ≥2 unfenced verdict lines | only the **last** decides (a–g applied to it) | — |
| i | a `Verdict:` line inside a ``` fenced block | ignored (not a verdict line) | — |

Pass → `GateResult(passed=True, issues=[], exit_code=0)`. Fail → `passed=False`,
`issues` = the mode-specific message(s) (SPEC-HONEST-001), `exit_code=EXIT_GATE_FAIL`.

### SPEC-ARCHIVE-001 — Archive wiring (`_cmd_run_archive`)
Implements DES-GATE-002. Inside the existing
`record.status == RunStatus.EXECUTING and not args.force` block, **after**
`check_execution_complete` passes, call `check_final_review_recorded(run_dir)`; on
`not gate.passed`, `print_and_exit(format_error(<joined issues>, exit_code=gate.exit_code), gate.exit_code)`.

- EXECUTING + complete ledger + no/!approved marker → exits EXIT_GATE_FAIL (3); run stays EXECUTING, nothing moved.
- EXECUTING + complete ledger + approved marker → archive proceeds as today (payload `{work_id, status:"archived", archived_to}`, EXIT_OK).
- EXECUTING + `--force` → both completion and final-review gates skipped (abandoned/superseded).
- `CLOSED_AT_PLAN_CHECKPOINT` archive → never reaches the block; no marker required.
- Ordering: completion gate first, then final-review gate, then the existing
  archive-target/clobber/gitignore/move/commit steps — unchanged.

### SPEC-SEED-001 — Marker not seeded (`_cmd_run_execute_start`)
Implements DES-GATE-002/FR-B2. `run-execute-start` continues to seed only
`execution/progress.md`; it must NOT create `execution/final-review.md`. Regression
contract: after `run-execute-start`, `execution/final-review.md` does not exist.

### SPEC-HONEST-001 — Honest labeling + executable guard (FR-B4)
Implements DES-HONEST-001. Every `check_final_review_recorded` failure message is a
presence/audit statement and carries the disclaimer literal
`not a correctness guarantee`. No archive-path output adds any affirmative
correctness wording; the archive success payload stays state-only (`status: archived`).

Mode-specific messages (each carries the disclaimer):
- missing / not-approved variant (verbatim, the requirement's canonical text):
  `Final whole-branch review not approved: execution/final-review.md is missing, or its current (last unfenced) 'Verdict:' line is not 'Approved'. Presence check on the review audit trail — not a correctness guarantee. Record 'Verdict: Approved', or re-run with --force to archive an abandoned run.`
- symlink / non-regular: states the file is a symlink / not a regular file and is refused; carries the disclaimer.
- no-verdict-line / unsupported-value / changes-requested: states the specific
  recorded-state problem; carries the disclaimer.

Executable honesty guard (a **test helper**, phrase/pattern-based — NOT a bare-token
substring match). Given any archive-path output string or gate failure message:
- It REJECTS (asserts dishonest) strings matching affirmative-claim patterns,
  case-insensitive, word-boundary anchored: `verified`, `validated`,
  `guaranteed correct` (also `correct(ness)? (is )?guaranteed`), `review approved`,
  `proven correct`.
- It EXEMPTS (never trips on) the exact disclaimer phrase `not a correctness guarantee`
  and the protocol literal `Verdict: Approved`. Because matching is phrase/pattern
  anchored, `not a correctness guarantee` (contains "correct"/"guarantee") and
  `Verdict: Approved` (contains "Approved") do NOT trip the guard — proving it is
  not a substring match.

### SPEC-TMPL-001 — Part A r2p-execute prose, both surfaces in sync
Implements DES-TMPL-001 (FR-A1..A6). Each surface
(`agent_templates/claude/commands/r2p-execute.md`,
`agent_templates/codex/skills/r2p-execute/SKILL.md`) gains, terse:
1. a `## Model Selection` section (role→model scaling; final review on most capable; always specify model explicitly; turn-count-beats-token-price floor);
2. Step 5 records BASE before dispatch, after `DONE` runs `mkdir -p .req-to-plan/<work-id>/logs` then writes `git diff -U10 <base-commit> HEAD > .req-to-plan/<work-id>/logs/task-N-diff.md`, and hands the reviewer the **diff file path** (reviewer-input list says the diff file path, not "The diff");
3. an explicit BASE rule: record `git rev-parse HEAD` before dispatch, **never use `HEAD~1`**;
4. reviewer-prompt discipline (copy Global Constraints verbatim; no pre-judged severity; no pasted prior-task summaries);
5. continuous execution (no "should I continue?" between tasks; stop only on unresolvable BLOCKED / upstream-defect / dirty-tree / all-done) and evidence-before-claims (`Verification` requires fresh command output; no `DONE` without it);
6. stronger final review: re-run the full verification suite on final HEAD + attach output; task-by-task PLAN checklist; one consolidated fix subagent; most-capable model; then write `execution/final-review.md` (range, one-line summary, `Verdict:` — `Approved` clean / `Changes Requested` while findings remain / append `Approved` after a fix wave), noting `r2p-archive` refuses unless current verdict is `Verdict: Approved`.

Invariants: all pre-existing required SDD tokens remain; `r2p-gap-open` stays
absent; the two surfaces stay byte-synced on every guarded token. gemini shim and
opencode (derived) are not hand-edited.

### SPEC-WRITE-001 — Atomic, symlink-checked Context Pack write (FR-D1)
Implements DES-WRITE-001. `context_pack.py::write_context_pack(pack, run_dir)`: before
writing, if `(run_dir/"02-project-context.json").is_symlink()` or
`(run_dir/"02-project-context.md").is_symlink()` → raise (reject; do not write
through). Otherwise write each target via `atomic_write_text` (unique temp + `O_EXCL`
+ `O_NOFOLLOW` + `os.replace`). Return value unchanged (`(md_path, json_path)`); a
normal build still produces both files.

### SPEC-WRITE-002 — Unique-temp manifest write in install (FR-D2)
Implements DES-WRITE-002. Note (per design review): `install.py` already validates
**both** the manifest path and the fixed temp path via `_validate_install_path`
(symlink already rejected today). The residual this fixes is the **fixed-name temp
collision + check-then-write TOCTOU window**, not a missing symlink check. Add an
install-local helper that (a) keeps `_validate_install_path` on the manifest path and
on the chosen temp path, and (b) opens a **unique** temp via
`O_WRONLY|O_CREAT|O_EXCL(|O_NOFOLLOW|O_CLOEXEC)` (mirroring
`atomic._open_unique_sibling_tmp`, which cannot be reused verbatim because install
carries its own path-validation rules), writes the manifest bytes, then `os.replace`
onto the validated manifest path. Behavior contract: the manifest is still written
and replaced; a symlink planted at the temp path is rejected.

### SPEC-STATE-001 — Transactional run-reopen from EXECUTING (FR-D3)
Implements DES-STATE-001. In `cli.py::_cmd_run_reopen`, after `new_mgr.save(new_record)`,
guard the EXECUTING-source transition+save: if `source_mgr.save(source_record)` raises,
remove the freshly created `new_run_dir` (and do not leave a persisted new run) before
re-raising — so a source-save failure leaves no orphan new run and the source stays
consistently `EXECUTING`. A normal reopen (source save succeeds) is byte-for-byte
unchanged.

### SPEC-DOCS-001 — Closure-model documentation (FR-C1, Part C)
Implements DES-DOCS-001. `CLAUDE.md` gains two Invariants bullets: (a) the
final-review marker gate is a presence/audit check at the same trust level as the
PLAN-TASK checkbox gate and verifies no correctness; (b) cross-stage trace closure is
enforced at the PLAN quality gate (every `SPEC-*` consumed, every `SCOPE-IN-*`
carried, every `RISK-*` closed); intermediate stages enforce only "cited upstream ID
⇒ closure tag"; stages 04–06 have no forward full-coverage gate. The Test-rules
`r2p-execute` token description is updated to name the new guarded tokens. No
hardcoded test count is introduced anywhere in `CLAUDE.md`.

## API / Data / Config Contracts

- **Marker file** `execution/final-review.md`: not seeded (absent by default);
  written only by the agent's final-review step. Must be a regular, non-symlink file
  with ≥1 unfenced `Verdict:` line; the **last** unfenced `Verdict:` line is the
  current verdict; pass iff current value (case-insensitive) is `approved`.
- **Function**: `check_final_review_recorded(run_dir: Path) -> GateResult` where
  `GateResult(passed: bool, issues: list[str], exit_code: int)` (existing type);
  `EXIT_GATE_FAIL == 3` (from `output.py`).
- **Supported verdict values** (case-insensitive): `Approved`, `Changes Requested`.
  Any other non-empty value is "unsupported" → fail.
- **Honesty allow-set (must never trip the guard)**: `Verdict: Approved`,
  `not a correctness guarantee`. **Deny-set (must trip the guard)**: `verified`,
  `validated`, `guaranteed correct`, `review approved`.
- **New docs-consistency tokens** (added to the execute-surface required tuple in
  `tests/test_docs_consistency.py`): `Model Selection`, `HEAD~1`,
  `execution/final-review.md`, `Verdict: Approved`, `re-run the full verification suite`.
- **Diff scratch path**: `.req-to-plan/<work-id>/logs/task-N-diff.md` (gitignored via
  `/*/logs/`), never under tracked `execution/`.
- Exit codes and JSON-mode (`R2P_JSON=1`) payload shapes are otherwise unchanged.

## External Documentation Checked

N/A — no external dependencies

## Test Matrix

| Test | Surface | Asserts | SPEC |
|---|---|---|---|
| missing-file fail (case a) | `tests/test_gates.py` | no marker → fail, exit 3 | SPEC-GATE-001 |
| symlink fail (case b) | `tests/test_gates.py` | symlink target → fail | SPEC-GATE-001 |
| non-regular FIFO fail (case c) | `tests/test_gates.py` | FIFO → fail, no block | SPEC-GATE-001 |
| no-verdict-line fail (case d) | `tests/test_gates.py` | regular file, no `Verdict:` → fail | SPEC-GATE-001 |
| unsupported value fail (case e) | `tests/test_gates.py` | `Verdict: Maybe` → fail | SPEC-GATE-001 |
| changes-requested fail (case f) | `tests/test_gates.py` | final `Verdict: Changes Requested` → fail | SPEC-GATE-001 |
| approved pass (case g) | `tests/test_gates.py` | final `Verdict: Approved` → pass, exit 0 | SPEC-GATE-001 |
| last-of-many CR then Approved (case h) | `tests/test_gates.py` | passes | SPEC-GATE-001 |
| last-of-many Approved then CR (case h) | `tests/test_gates.py` | fails | SPEC-GATE-001 |
| fenced verdict ignored (case i) | `tests/test_gates.py` | `Verdict:` only inside a code fence → not counted, falls to case d | SPEC-GATE-001 |
| archive blocked no marker | `tests/test_cli.py` | EXECUTING + complete ledger + no marker → exit 3 | SPEC-ARCHIVE-001 |
| archive passes with marker | `tests/test_cli.py` | approved marker → archived | SPEC-ARCHIVE-001 |
| `--force` bypass | `tests/test_cli.py` | force archives without marker | SPEC-ARCHIVE-001 |
| closed-at-plan archive | `tests/test_cli.py` | no marker required | SPEC-ARCHIVE-001 |
| update existing executing-archive successes | `tests/test_cli.py` | seed approved marker so they stay green | SPEC-ARCHIVE-001 |
| not-seeded | `tests/test_cli.py` | `run-execute-start` leaves no final-review.md | SPEC-SEED-001 |
| honesty allow coverage | `tests/test_cli.py` | every mode message + archive output passes the guard | SPEC-HONEST-001 |
| honesty deny | `tests/test_cli.py` | `verified`/`guaranteed correct`/`review approved` trip the guard; `not a correctness guarantee` and `Verdict: Approved` do not | SPEC-HONEST-001 |
| new guarded tokens present + synced | `tests/test_docs_consistency.py` | both surfaces carry the 5 new tokens; `r2p-gap-open` still absent | SPEC-TMPL-001, SPEC-DOCS-001 |
| context-pack symlink reject + normal build | `tests/test_context_pack.py` | symlink at json/md → rejected; normal build writes both | SPEC-WRITE-001 |
| manifest unique-temp write + temp-symlink reject | `tests/test_install.py` | manifest written/replaced; symlink at temp rejected | SPEC-WRITE-002 |
| reopen rollback + normal reopen | `tests/test_cli.py` | simulated source-save failure → no orphan, source consistent; normal reopen unchanged | SPEC-STATE-001 |

No new test module is created; no new dependency, module, or service.

## Non-goals

- The CLI never runs code, runs tests, or parses correctness from evidence
  (SCOPE-OUT-001). The gate is presence/audit only.
- No per-task verification-output presence check (SCOPE-OUT-002); no forward
  full-coverage gate at 04–06 (SCOPE-OUT-003).
- No worktrees, branch isolation, external scripts, new service/db/telemetry/network
  dependency (SCOPE-OUT-004).
- No `r2p-gap-open` routing in execution surfaces (SCOPE-OUT-005); no change to
  transitions/schemas/tier/other gates (SCOPE-OUT-006); gemini shim untouched,
  opencode derived (SCOPE-OUT-007); marker not presented as a hard correctness
  barrier (SCOPE-OUT-008).

## PLAN Handoff

PLAN must produce ordered PLAN-TASKs that each consume one or more SPEC IDs, with
`Skeleton`/`Steps`/`Spec References`/`Verification`. Suggested grouping (sequence A→C
first, D separable):
- T1 → SPEC-GATE-001 (new gate function + `tests/test_gates.py`), TDD red→green.
- T2 → SPEC-ARCHIVE-001 + SPEC-SEED-001 + SPEC-HONEST-001 (archive wiring, messages,
  honesty guard; update existing executing-archive tests) in `tests/test_cli.py`.
- T3 → SPEC-TMPL-001 (both r2p-execute surfaces, synced) + SPEC-DOCS-001 (`CLAUDE.md`)
  + the new `tests/test_docs_consistency.py` tokens.
- T4 → SPEC-WRITE-001 (`tests/test_context_pack.py`).
- T5 → SPEC-WRITE-002 (`tests/test_install.py`).
- T6 → SPEC-STATE-001 (`tests/test_cli.py`).
Global constraints PLAN must restate: Python-only stdlib + `pyyaml`; CLI/agent
boundary; no affirmative correctness wording; full suite + docs-consistency stay
green; verification command `.venv/bin/python -m pytest tests/ -v` (and the targeted
module runs).

## Trace
<!-- Map this stage's IDs to upstream/downstream. R3 derives & checks closure. -->
| This ID | Upstream | Status |
|---|---|---|
| SPEC-GATE-001 | DES-GATE-001 [ADDRESSED] | open |
| SPEC-ARCHIVE-001 | DES-GATE-002 [ADDRESSED] | open |
| SPEC-SEED-001 | DES-GATE-002 [ADDRESSED] | open |
| SPEC-HONEST-001 | DES-HONEST-001 [ADDRESSED] | open |
| SPEC-TMPL-001 | DES-TMPL-001 [ADDRESSED] | open |
| SPEC-WRITE-001 | DES-WRITE-001 [ADDRESSED] | open |
| SPEC-WRITE-002 | DES-WRITE-002 [ADDRESSED] | open |
| SPEC-STATE-001 | DES-STATE-001 [ADDRESSED] | open |
| SPEC-DOCS-001 | DES-DOCS-001 [ADDRESSED] | open |

## Upstream Summary (read-only)
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
| RISK-HONESTY-001 | DES-HONEST-001 | mitigated [ADDRESSED] |
| RISK-GUARD-001 | DES-HONEST-001 | mitigated [ADDRESSED] |
| RISK-DRIFT-001 | DES-TMPL-001, DES-DOCS-001 | mitigated [ADDRESSED] |
| RISK-EVIDENCE-001 | DES-GATE-002, Rollback | mitigated [ADDRESSED] |
| RISK-OVERFLOW-001 | DES-TMPL-001 | mitigated [ADDRESSED] |
| RISK-WRITE-001 | DES-WRITE-001, DES-WRITE-002 | mitigated [ADDRESSED] |
| RISK-STATE-001 | DES-STATE-001 | mitigated [ADDRESSED] |
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

# Design Subagent Review (v2)

## Verdict

**Approved** — no blocking issues.

Every functional requirement (FR-A1..A6, FR-B1..B4, FR-C1, FR-D1..D3) is covered
by a faithful DES item. Every "Current Code Evidence" claim was independently
confirmed against the current tree. The new gate's decision table, the honesty
guard, the archive wiring, and the three Part-D fixes are all implementable with
the cited helpers, internally consistent, and scope-clean. `Decision Requests:
none` is justified — the requirement is decision-complete.

## Blocking findings

None.

## Non-blocking observations

1. **Helper-attribution imprecision in Current Code Evidence (cosmetic).** The
   design writes `gates.py::unfenced_markdown_lines(content)` (05-design.md:51).
   The function is *defined* in `markdown.py:24`; `gates.py` only *imports* it
   (`gates.py:32`) and uses it (`gates.py:1202`). The behavioral claim ("yields
   `(line, start, end)`; a `Verdict:` inside a fence is ignored") is correct
   (verified `markdown.py:24-55`). Same module slightly off, not the behavior.
   The Trace/SPEC-handoff sections correctly treat it as a reused helper, so this
   does not affect implementability. Worth tightening the `gates.py::` prefix to
   `markdown.py::` in the evidence bullet for accuracy.

2. **Line-count hedge "~122/123 lines" (05-design.md:75).** Actual on-disk: the
   claude surface is 123 lines, the codex surface 124. The "~" qualifier covers
   it; no action needed, but the numbers are approximate, not exact.

3. **FR-D2 — the design correctly notes the *real* residual is the fixed name,
   not a missing symlink check.** `install.py` already validates *both* the
   manifest path and the `.tmp` sibling via `_validate_install_path` (install.py:
   207, 213), which rejects a planted symlink (install.py:837). The genuine gap
   the fix closes is the fixed-name collision + the check-then-write (TOCTOU)
   window between `_validate_install_path(tmp)` and `tmp.write_text`. The design
   states this precisely (05-design.md:66-69, DES-WRITE-002). One caveat for SPEC:
   the FR-D2 acceptance test "a symlink planted at the temp path is rejected" is
   already satisfied by today's code, so the *new* test value is the unique-name /
   `O_EXCL` behavior, not symlink rejection (which is a regression-guard, not a
   new capability). The design does not overclaim here, but SPEC should phrase the
   FR-D2 contract around `O_EXCL` uniqueness + TOCTOU closure, not "now rejects
   symlinks."

4. **DES-HONEST-001 guard spec is directionally correct but leaves the exact
   pattern set to SPEC (by design).** The design names the affirmative patterns to
   reject (`verified`, `validated`, `guaranteed correct`, `review approved`) and
   the exact exemptions (`not a correctness guarantee`, `Verdict: Approved`), and
   explicitly rejects bare-token substring matching with the right rationale
   (`correct`/`guarantee`/`Approved` appear on both sides). That is enough to be
   non-naive. The one thing SPEC must pin and the design defers: whether the guard
   matches case-insensitively and on word boundaries (so `review approved` is
   caught but `Verdict: Approved` is exempt even though both contain "Approved").
   The design hands this to SPEC (05-design.md:278-280) rather than fully
   specifying it — acceptable for a DESIGN-stage artifact, flagged so SPEC closes
   it.

## Evidence checked

Confirmed by reading the current tree (codegraph verbatim source + direct Read):

- **`gates.py::check_execution_complete` (gates.py:1156)** — reads
  `execution/progress.md` via `_read_regular_text_no_symlink`, scans
  `unfenced_markdown_lines` for unchecked `- [ ] PLAN-TASK-*`
  (`_LEDGER_UNCHECKED_RE`, gates.py:1117), cross-checks checked IDs
  (`_LEDGER_CHECKED_RE`, gates.py:1118) against `_plan_task_ids(run_dir)`, rejects
  an empty ledger (gates.py:1226-1230), returns
  `GateResult(passed, issues, exit_code=EXIT_GATE_FAIL|0)`. The design's "new gate
  mirrors this shape exactly + reuses the same two helpers" is faithful.

- **`gates.py::_read_regular_text_no_symlink` (gates.py:1121)** — returns
  `(text|None, error|None)`, `error ∈ {missing, symlink, not_regular}`, uses
  `O_RDONLY|O_NOFOLLOW|O_NONBLOCK` + `stat.S_ISREG`, and also rejects a symlinked
  parent (gates.py:1123) and maps `ELOOP → symlink`. Matches the design claim
  (05-design.md:48-49).

- **`markdown.py::unfenced_markdown_lines` (markdown.py:24)** — yields
  `(line, start, end)` for lines outside fenced code; fenced lines are skipped
  (markdown.py:35-51). Confirms AC-002 "a `Verdict:` inside ``` ``` is ignored"
  is achievable directly. (Defined in markdown.py, imported by gates.py — see
  observation 1.)

- **`gates.py::_find_ids_without_closure` (gates.py:151)** — the per-stage closure
  rule: any *cited* upstream ID (not defined-here) must carry a closure tag.
  Matches FR-C1's documented "cited upstream ID ⇒ closure tag" (DES-DOCS-001).

- **`gates.py::GateResult` (gates.py:43)** — dataclass `(passed: bool,
  issues: list[str], exit_code: int = 0)`. The design's
  `GateResult(passed=False, issues=[...], exit_code=EXIT_GATE_FAIL)` for failure /
  `exit_code=0` for pass (DES-GATE-001) is exactly this shape.

- **`output.py::EXIT_GATE_FAIL` (output.py:8)** — `= 3`. Matches the requirement's
  Marker File Contract exit code and the design's claim.

- **`cli.py::_cmd_run_archive` (cli.py:632)** — the
  `record.status == RunStatus.EXECUTING and not args.force` block (cli.py:647)
  runs `check_execution_complete` and `print_and_exit`s on failure (cli.py:648-
  658); `--force` skips the whole block. Success payload is state-only
  `{"work_id", "status": "archived", "archived_to"}` (cli.py:692) — no correctness
  word, so FR-B4/AC-007 are preserved as the design claims. The proposed insertion
  point ("after `check_execution_complete` passes, inside the same block") is the
  correct, only place that makes `--force` bypass both gates and leaves
  `CLOSED_AT_PLAN_CHECKPOINT` archives untouched (AC-003/AC-004). DES-GATE-002 is
  consistent with the real control flow.

- **`cli.py::_cmd_run_execute_start` (cli.py:699)** — seeds only
  `execution/progress.md` via `atomic_write_text(exec_dir / "progress.md", ...)`
  (cli.py:734); it creates no final-review file. FR-B2 "leave as-is + regression
  test" (DES-GATE-002) is accurate, so the gate has teeth (AC-005).

- **`cli.py::_cmd_run_reopen` (cli.py:496)** — `new_mgr.save(new_record)`
  (cli.py:603) runs first; then for an `EXECUTING` source it transitions to
  `CLOSED_AT_PLAN_CHECKPOINT` and calls `source_mgr.save(source_record)`
  (cli.py:605-616). A failure of the source save leaves the orphan new run with no
  rollback — exactly the defect DES-STATE-001/FR-D3 targets. The contrast with
  archive's move-back-on-save-failure (cli.py:680-685) is real and correctly
  cited.

- **`context_pack.py::write_context_pack` (context_pack.py:167)** — writes both
  `02-project-context.json` and `02-project-context.md` with plain
  `Path.write_text` (context_pack.py:170-171), no `is_symlink()` check; returns
  `(md_path, json_path)`. Confirms the FR-D1 defect and that DES-WRITE-001
  preserves the return contract.

- **`install.py` manifest write (install.py:207-216)** — fixed-name sibling temp
  `manifest_path.with_name(manifest_path.name + ".tmp")` (install.py:209),
  `_validate_install_path` on *both* `manifest_path` (207) and `tmp` (213), then
  `tmp.write_text(...)` + `tmp.replace(manifest_path)`. So the fix's job is the
  fixed-name collision + check-then-write window, not a missing symlink check
  (see observation 3). `_validate_install_path` (install.py:835) rejects a symlink
  target and symlinked ancestors. DES-WRITE-002 "keep `_validate_install_path` on
  both paths but use an `O_EXCL` unique temp" does not weaken validation.

- **`atomic.py::atomic_write_text` / `_open_unique_sibling_tmp` (atomic.py:9, 33)**
  — unique sibling temp (`secrets.token_hex(8)` name) opened with
  `O_WRONLY|O_CREAT|O_EXCL` plus `O_CLOEXEC`/`O_NOFOLLOW` when available, then
  `os.replace`. This is the exact pattern FR-D1 reuses directly (DES-WRITE-001) and
  FR-D2 mirrors (DES-WRITE-002). The design's claim that FR-D2 "cannot reuse
  `atomic_write_text` verbatim because install carries its own
  `_validate_install_path` rules" is correct — `atomic_write_text` performs no
  install path validation.

- **Both `r2p-execute` surfaces** (claude commands/r2p-execute.md;
  codex skills/r2p-execute/SKILL.md) — Step 5 currently records the diff **inline**
  (`git diff -U10 <base-commit> HEAD`, claude:71 / codex:72) and hands "The diff"
  to the reviewer (claude:75 / codex:76). The Final Whole-Branch Review includes an
  inline `git diff -U10 <merge-base> HEAD` (claude:93 / codex:94), does **not**
  re-run the suite, and writes **no** marker. Neither surface contains a
  `## Model Selection` heading. All baseline facts behind FR-A1..A6 are confirmed.
  The surfaces are byte-aligned on the guarded tokens today, so the sync premise
  (RISK-DRIFT-001) holds.

- **`tests/test_docs_consistency.py`** — `TestExecuteTemplateContent` already
  guards the SDD token set (`closed_at_plan_checkpoint`, `current branch`,
  `Pre-flight`, `Verification`, `fresh implementer subagent`, `task-reviewer`,
  `whole-branch review`, `r2p-archive`, `--work-id`, `- [x] PLAN-TASK-NNN`,
  `hard prerequisite`, `NEEDS_CONTEXT`) and `r2p-gap-open` absence on both
  surfaces (test_docs_consistency.py:60-103). The new FR-C1 tokens
  (`Model Selection`, `HEAD~1`, `execution/final-review.md`, `Verdict: Approved`,
  `re-run the full verification suite`) are **not yet** in the guarded tuple —
  correct, since adding them is FR-C1's job. The `CLAUDE.md` no-hardcoded-count
  guard (`_MAGIC_COUNT`, test_docs_consistency.py:12) also confirms DES-DOCS-001's
  "no hardcoded test count" constraint is enforced.

- **`.req-to-plan/.gitignore`** — contains `/archive`, `/.workflow-active`, and
  `/*/logs/`. Confirms FR-A2's premise that `<work-id>/logs/` is gitignored (so the
  diff scratch is immune to an accidental `git add`) while `execution/` is tracked
  — the rationale behind rejecting `execution/` as the diff location.

### Assessment against the eight check items

1. **FR coverage (faithful, nothing dropped).** All 13 FRs map to a DES item in
   the Requirements-Coverage table (05-design.md:84-99) and each is elaborated in
   Chosen Design. FR-A1..A6 → DES-TMPL-001; FR-B1 → DES-GATE-001; FR-B2/B3 →
   DES-GATE-002; FR-B4 → DES-HONEST-001; FR-C1 → DES-DOCS-001; FR-D1/D2/D3 →
   DES-WRITE-001/002 / DES-STATE-001. No requirement is silently dropped or
   distorted. ✓

2. **Code-evidence claims true.** All confirmed (see above). Only cosmetic
   imprecision (observations 1-2). ✓

3. **DES-GATE-001 implementable + internally consistent.** The decision table
   (missing/symlink/not_regular → fail; no unfenced `Verdict:` → fail; last-of-many
   wins; value ∉ {approved, changes requested} → fail; `changes requested` → fail;
   `approved` → pass; case-insensitive on value) is buildable with
   `_read_regular_text_no_symlink` + `unfenced_markdown_lines`, and matches the
   requirement's Marker File Contract and AC-002 exactly. The "last unfenced wins /
   fenced ignored" logic is consistent with the FR-A6 append-`Approved`-after-a-fix-
   wave workflow. ✓

4. **DES-HONEST-001 genuinely phrase/pattern-based.** It rejects affirmative
   *phrases* and exempts the *exact* disclaimer and protocol literals, explicitly
   ruling out a bare-token match with the correct FR-B4 trap analysis
   (`correct`/`guarantee`/`Approved` straddle allowed and rejected strings). Not
   satisfiable by a naive substring guard. Underspecified only on
   case/word-boundary mechanics, which the design defers to SPEC (observation 4). ✓

5. **DES-GATE-002 archive wiring.** EXECUTING-only, after the completion gate,
   `--force` bypasses both, `CLOSED_AT_PLAN_CHECKPOINT` unaffected, marker not
   seeded — all consistent with the real `_cmd_run_archive` / `_cmd_run_execute_
   start` control flow (verified above). ✓

6. **Part D fixes correct + non-weakening.** DES-WRITE-001 adds a symlink reject +
   `atomic_write_text` (closing the real `write_text`-follows-symlink gap).
   DES-WRITE-002 keeps both `_validate_install_path` calls and only swaps the
   fixed-name temp for an `O_EXCL` unique temp (does not weaken path validation;
   see observation 3 for the precise residual). DES-STATE-001 makes reopen
   transactional (remove orphan new run on source-save failure) matching archive's
   level. All three target the verified defects. ✓

7. **Decision Requests: none — justified.** The requirement and brief are
   decision-complete: marker contract, gate modes, exact failure-message text,
   honesty-guard shape, and Part-D fixes are all specified; Part D sequencing is a
   PLAN delivery choice, not a design open question (brief Open Questions:159-164).
   No hedge in the design lacks a decision — the Options-Considered section records
   each choice with its rejected alternative and rationale. ✓

8. **Scope discipline.** No CLI correctness verification (Boundaries:387-394), no
   new dependency (Python stdlib + `pyyaml` only), no transition/schema/tier/other-
   gate change, gemini shim left untouched, opencode derived — all honor
   SCOPE-OUT-001..008. The marker is a working-tree precondition, not a committed
   record (durability boundary, Boundaries:405-407). ✓

# Plan Subagent Review (v2)

## Verdict

**Approved** — no blocking issues.

All 9 SPEC IDs are consumed by a PLAN-TASK `Spec References`; no SPEC is dropped and
no PLAN-TASK cites a non-existent SPEC. Every task is TDD with a fenced Skeleton and
an objective `.venv/bin/python -m pytest` Verification command. The Global
Constraints restate the Python-only / CLI-boundary / no-correctness-wording /
surface-sync / sequencing rules. Files lists reference real repo paths only; no new
module, dependency, or service. I empirically executed the two subtle skeletons
(PLAN-TASK-001 verdict logic + message build, PLAN-TASK-002 honesty regex) against
the canonical messages and they behave correctly. The `.replace("Presence",
"Presence")` is a confirmed harmless no-op (see observation 1). Three non-blocking
implementation notes follow; none blocks the PLAN.

## Blocking findings

None.

## Non-blocking observations

1. **PLAN-TASK-001 — `.replace("Presence", "Presence")` is a harmless no-op the
   implementer should drop (cosmetic, not a logic defect).** I verified
   `disclaimer.replace("Presence","Presence") == disclaimer` is `True`, and that the
   skeleton's branch builds the canonical not-approved message **byte-for-byte**
   identical to SPEC-HONEST-001's verbatim text. So it does not mislead the output —
   it is pure dead text that should simply be deleted (write `_FINAL_REVIEW_
   DISCLAIMER` directly). Confirmed not a logic bug. Flagging only so the
   implementer removes it rather than copying it forward.

2. **PLAN-TASK-001 — the skeleton collapses "missing file" and
   "present-but-no-verdict" into one message, making row d's dedicated message dead
   code (deviation from SPEC-GATE-001 row a vs d and SPEC-HONEST-001's per-mode
   list).** The first branch is
   `if err == "missing" or (err is None and text is not None and not _has_verdict(text)):`
   which returns the canonical *missing/not-approved* message for BOTH the missing
   file (row a) and the regular-file-with-no-`Verdict:`-line case (row d). The later
   branch (skeleton lines 82-84) `if current is None: return _fail("...records no
   'Verdict:' line...")` is therefore **unreachable** — `_has_verdict` already
   caught it. SPEC-GATE-001 lists rows a and d as distinct fail rows and
   SPEC-HONEST-001 lists "no-verdict-line" as a distinct mode message that "states
   the specific recorded-state problem." This collapse is behaviorally safe — both
   paths fail with `EXIT_GATE_FAIL` (3) and carry the disclaimer, so AC-002 and FR-B4
   still hold — but it (a) leaves dead code the implementer should not ship, and
   (b) drops the distinct "no-verdict-line" message the SPEC envisioned (the
   honesty-allow test then has one fewer distinct mode message to cover). The
   skeleton's own comment ("present-but-no-verdict both report the canonical ...
   message") shows this is intentional, and the requirement's canonical text
   explicitly covers "is missing, or its current ... 'Verdict:' line is not
   'Approved'" — so merging them is defensible. Recommend the implementer either
   (i) keep the merge and delete the unreachable lines 82-84, or (ii) split row d
   into its own message to honor the SPEC's per-mode contract. Either is acceptable;
   flag so the choice is deliberate, not accidental dead code. **Not blocking** — no
   AC fails under either reading.

3. **PLAN-TASK-006 — the rollback skeleton widens the `try` to also wrap
   `update_run_status`, changing the existing `ValueError` path.** The real
   `_cmd_run_reopen` (cli.py:605-616) wraps only `update_run_status` in its own
   `try/except ValueError: print_and_exit(..., EXIT_CONFLICT)`, then calls
   `source_mgr.save` **outside** any try. The skeleton puts `update_run_status`,
   `current_stage`, `update_resume_context`, AND `source_mgr.save` inside one
   `try: ... except Exception: shutil.rmtree(new_run_dir); raise`. Two effects to
   call out for the implementer: (a) a `ValueError` from `update_run_status` — today
   a clean `print_and_exit(EXIT_CONFLICT)` — would under the skeleton instead
   `rmtree` the new run and re-raise an uncaught exception (a behavior change on a
   path SPEC-STATE-001 does not ask to change; SPEC-STATE-001 only requires guarding
   the `source_mgr.save` failure). (b) It is still functionally correct for the
   required contract (source-save failure → no orphan + source stays EXECUTING).
   Recommend the implementer scope the rollback `try` to the `source_mgr.save` call
   (and the immediately-preceding in-memory mutations) and preserve the existing
   `except ValueError → print_and_exit(EXIT_CONFLICT)` around `update_run_status`, so
   the only new behavior is the rollback on save failure. **Not blocking** — the
   skeleton is illustrative and the Steps/Verification target the right contract; a
   careful implementer following SPEC-STATE-001 will scope it correctly.

4. **PLAN-TASK-005 — `secrets` is not currently imported in `install.py` (only
   `os`).** The skeleton uses `secrets.token_hex(8)` but `install.py` imports `os`
   (line 8) and not `secrets`. The implementer must add `import secrets`. Trivial,
   but the skeleton does not note it. (`atomic.py` already imports `secrets`, which
   is where the pattern is mirrored from.) **Not blocking.**

## Evidence checked

- **Coverage (check 1).** All 9 SPEC IDs are consumed exactly once across the
  PLAN Trace (07-plan.md:315-320): SPEC-GATE-001 → PLAN-TASK-001; SPEC-ARCHIVE-001 +
  SPEC-SEED-001 + SPEC-HONEST-001 → PLAN-TASK-002; SPEC-TMPL-001 + SPEC-DOCS-001 →
  PLAN-TASK-003; SPEC-WRITE-001 → PLAN-TASK-004; SPEC-WRITE-002 → PLAN-TASK-005;
  SPEC-STATE-001 → PLAN-TASK-006. Each task's `Spec References` line matches the
  Trace. No SPEC dropped; no PLAN-TASK references a non-existent SPEC. The grouping
  matches the SPEC's PLAN-Handoff suggestion (T1→T6) exactly.

- **PLAN-TASK-001 gate skeleton (check 2) — executed.** I reconstructed
  `_current_verdict` and the branch logic and ran them:
  `Verdict: Approved` → `approved`; `Verdict: Changes Requested` → `changes
  requested`; CR-then-Approved → `approved` (last-wins); Approved-then-CR → `changes
  requested` (last-wins); `Verdict:` with empty value → `''` (falls to the
  unsupported branch → fail, correct); no verdict line → `None`. Fenced-ignored and
  last-wins are delegated to `unfenced_markdown_lines` (markdown.py:24, verified
  earlier to skip fenced blocks and yield lines in order). The exit code is
  `EXIT_GATE_FAIL` on every fail path via `_fail`. The `Verdict:`-key match uses
  `s[:8].lower() == "verdict:"` (case-insensitive key) and `.lower()` on the value
  (case-insensitive value) — matches SPEC-GATE-001. Logic is correct; see
  observations 1-2 for the no-op and the missing/no-verdict collapse.

- **PLAN-TASK-002 honesty guard (check 2) — executed.** Ran the skeleton's
  `_HONESTY_DENY` regex list against every canonical message:
  - canonical missing/not-approved message → **no trip** (passes) ✓
  - changes-requested message → no trip ✓
  - symlink message → no trip ✓
  - `Verdict: Approved` (exempt literal) → no trip ✓
  - `not a correctness guarantee` (exempt literal) → no trip ✓
  - `the review approved this` → trips `\breview\s+approved\b` ✓
  - `verified correct output` → trips `\bverified\b` ✓
  - `output is guaranteed correct` → trips `\bguaranteed\s+correct\b` ✓
  - `whole-branch review not approved` → **no trip** ✓ (critical: `\s+` is whitespace
    only, so the intervening "not" prevents a false-positive on the canonical
    message). The skeleton's inline comment explicitly warns against `review.*approved`
    for this reason. The deny list is genuinely adjacency/word-boundary based, not a
    bare-substring match. Matches SPEC-HONEST-001.

- **PLAN-TASK-002 archive wiring (check 2).** The skeleton inserts
  `review_gate = check_final_review_recorded(run_dir)` + `print_and_exit` **inside**
  the `EXECUTING and not args.force` block, **after** `check_execution_complete`.
  This matches the real `_cmd_run_archive` (cli.py:647-658): the completion gate runs
  in that block, and the new gate is placed right after it, so `--force` bypasses
  both and `CLOSED_AT_PLAN_CHECKPOINT` never enters the block. The not-seeded note
  ("`_cmd_run_execute_start` UNCHANGED") matches cli.py:699-734 (seeds only
  `execution/progress.md`). Consistent with SPEC-ARCHIVE-001 and SPEC-SEED-001.

- **PLAN-TASK-005 install skeleton (check 2).** Confirmed against the real write site
  (install.py:207-216): the skeleton replaces the fixed-name
  `manifest_path.with_name(manifest_path.name + ".tmp")` + `tmp.write_text` +
  `tmp.replace` with a loop opening a **unique** temp
  (`.{name}.{pid}.{token_hex(8)}.tmp`) via `O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW|
  O_CLOEXEC`, then `os.replace`. It keeps `_validate_install_path(manifest_path)` AND
  `_validate_install_path(tmp)` — preserving the existing symlink rejection
  (install.py:835-845) on both paths, so validation is not weakened. The residual it
  closes (fixed-name collision + TOCTOU window) matches SPEC-WRITE-002's corrected
  framing. One gap: `import secrets` is needed (observation 4).

- **PLAN-TASK-006 reopen skeleton (check 2).** The rollback (`shutil.rmtree(new_run_
  dir, ignore_errors=True)` on source-save failure → no orphan, source stays
  EXECUTING) matches the SPEC-STATE-001 contract and the real `_cmd_run_reopen`
  ordering (cli.py:602-616: `new_mgr.save` first, then the EXECUTING-source
  transition+save). `shutil` is importable (module top, cli.py:11). The one
  divergence — the skeleton widens the `try` over `update_run_status`, altering the
  existing `ValueError → print_and_exit(EXIT_CONFLICT)` path — is observation 3
  (non-blocking; the implementer should scope the try to `source_mgr.save`).

- **PLAN-TASK-004 context_pack skeleton (check 2).** Rejects when either
  `02-project-context.json` / `.md` `is_symlink()`, else `atomic_write_text` each,
  returns `(md_path, json_path)` unchanged. Matches SPEC-WRITE-001 and the real
  `write_context_pack` (context_pack.py:167, plain `write_text` today, returns
  `(md_path, json_path)`); `atomic_write_text` (atomic.py:9) provides the unique-temp
  + `O_EXCL` + `O_NOFOLLOW` + `os.replace` semantics the SPEC names. The import
  `from tools.workflow_cli.atomic import atomic_write_text` is correct. Return tuple
  preserved.

- **TDD + Verification (check 3).** Every task has a fenced ```` ``` ```` Skeleton, a
  Steps list that writes the failing test first (each Step 1 is "Red: ..."), and an
  objective `.venv/bin/python -m pytest tests/<module>.py -v` Verification command
  (PLAN-TASK-006 additionally uses `-k reopen` plus a full-module green check). The
  Global Constraints (07-plan.md:11-36) restate: Python-only stdlib+`pyyaml`,
  `.venv/bin/python -m pytest` (system python3 lacks pyyaml), CLI/agent boundary, no
  affirmative correctness wording + disclaimer requirement, no transition/schema/
  tier/other-gate change, surface byte-sync + `r2p-gap-open` absent + gemini/opencode
  not hand-edited, sequencing (T1-T3 land together; T4-T6 separable), TDD-first, and
  full-suite-green definition of done. All present and faithful to the SPEC.

- **Files lists (check 4).** Every path referenced exists in the repo:
  `tools/workflow_cli/{gates,cli,context_pack,install}.py`, the two `r2p-execute`
  surfaces, `CLAUDE.md`, and `tests/{test_gates,test_cli,test_docs_consistency,
  test_context_pack,test_install}.py`. No new module, dependency, or service is
  introduced (consistent with "No new test module is created" and the Global
  Constraints). All Part-D fixes reuse existing modules.

- **Unresolved ambiguity (check 5).** None lacking a decision. The PLAN has no open
  questions / decision-requests section and introduces no undecided hedge. The
  `.replace("Presence","Presence")` is a confirmed harmless no-op (observation 1,
  empirically `True`), not a logic defect and not misleading — the implementer should
  simply drop it. The only implementation-precision notes are observations 2-4, all
  caught by the SPEC's own tests (the honesty-allow test covers the message set; the
  module Verifications cover the behavior). Sequencing (A-C first, D separable) is
  explicit and respected.

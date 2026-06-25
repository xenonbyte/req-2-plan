# Spec Subagent Review (v2)

## Verdict

**Approved** — no blocking issues.

Every DES item is consumed by exactly one SPEC behavior contract and closed in the
trace with `[ADDRESSED]`. SPEC-GATE-001's decision table is complete and consistent
with the Marker File Contract and AC-002. The honesty guard is specified as
genuinely phrase/pattern-based and its allow/deny mechanics work as stated. The
canonical missing/not-approved message matches the requirement's FR-B4 block
verbatim. SPEC-ARCHIVE-001 control flow matches the real `_cmd_run_archive`.
SPEC-WRITE-002 now correctly states the residual is the fixed-name collision +
TOCTOU window, not a missing symlink check. The Test Matrix covers every Test-Plan
item. One non-blocking precision note on the `review approved` pattern (below) the
implementer should heed, but it is already pointed in the right direction by the
SPEC's own "phrase / word-boundary anchored" wording, so it is not blocking.

## Blocking findings

None.

## Non-blocking observations

1. **SPEC-HONEST-001 — `review approved` must be matched as an *adjacent* phrase,
   not a flexible gap, or the guard false-positives on its own canonical message.**
   The canonical missing/not-approved message contains the substring
   "...whole-branch **review not approved**:..." and later "...the **review** audit
   trail...". I tested both readings of the deny pattern against the exact canonical
   string (06-spec.md:64):
   - `\breview approved\b` (adjacent, the correct reading) → **does not match** the
     message → message passes the guard. ✓
   - `\breview\b.*\bapproved\b` (flexible gap) → **matches** "review not approved"
     → the canonical message would be wrongly flagged dishonest. ✗

   The SPEC says the deny patterns are "phrase/pattern, case-insensitive,
   word-boundary anchored" (06-spec.md:69-74), which points at the adjacent reading,
   and the honesty-allow test (06-spec.md:180, matrix row "honesty allow coverage":
   "every mode message ... passes the guard") would catch a flexible-gap
   implementation. So the spec is self-correcting via its own test. Still, the
   contract should explicitly state that `review approved` matches only when the two
   words are adjacent (no intervening token such as "not"), so the implementer does
   not reach for a `.*`/`\s+`-with-gap regex. Recommend PLAN restate this as an
   explicit Global Constraint or Skeleton note on T2.

2. **`proven correct` added beyond the requirement's deny-set (additive, fine).**
   SPEC-HONEST-001 (06-spec.md:74) adds `proven correct` to the deny patterns, which
   the requirement (FR-B4) does not list. This is a strengthening, not a
   contradiction, and is consistent with the intent. No action needed; just noting
   the SPEC's deny-set is a superset of the requirement's. The API/Data contract
   section (06-spec.md:147-148), however, lists the deny-set without `proven
   correct` — a minor internal inconsistency between the prose (line 74) and the
   contract block (line 148). Harmless, but PLAN/impl should treat line 74 as the
   authoritative deny-set.

3. **Disclaimer-literal wording differs slightly across artifacts (already
   reconciled correctly by SPEC).** The design's DES-HONEST-001 embeds
   `Presence check on the review audit trail — not a correctness guarantee.` while
   the exempt token the guard keys on is the shorter `not a correctness guarantee`.
   SPEC-HONEST-001 (06-spec.md:75) correctly uses the short phrase
   `not a correctness guarantee` as the exempt literal, which is the substring that
   appears in every mode message — the right choice. No issue; flagged only because
   a careless implementer might try to exempt the longer full sentence.

4. **SPEC-GATE-001 leaves "empty value" classification implicit.** Row e covers
   "value ∉ {approved, changes requested} → unsupported → fail" and row d covers
   "zero unfenced `Verdict:` lines → fail". A line that is exactly `Verdict:` with an
   empty/whitespace value is technically a verdict line with value `""`, which falls
   under row e (unsupported) and fails — the correct outcome, but the SPEC does not
   call it out explicitly. The requirement's Marker File Contract is equally silent.
   Behavior is correct under the table as written (empty ∉ the supported set);
   worth a one-line test in `tests/test_gates.py` so the classification is pinned.
   Non-blocking.

## Evidence checked

DES→SPEC closure and the underlying code facts (the latter re-confirmed from my
prior design-stage verification of the same tree):

- **DES→SPEC coverage (point 1).** All 9 DES items are consumed: DES-GATE-001 →
  SPEC-GATE-001; DES-GATE-002 → SPEC-ARCHIVE-001 **and** SPEC-SEED-001 (the design
  folded FR-B2+FR-B3 into one DES; the SPEC correctly splits them into two
  contracts); DES-HONEST-001 → SPEC-HONEST-001; DES-TMPL-001 → SPEC-TMPL-001;
  DES-WRITE-001 → SPEC-WRITE-001; DES-WRITE-002 → SPEC-WRITE-002; DES-STATE-001 →
  SPEC-STATE-001; DES-DOCS-001 → SPEC-DOCS-001. DES-ARCH-001 is an architecture
  framing item (no behavior surface of its own) and is legitimately not given a
  dedicated SPEC contract — its content is distributed across the slices. The SPEC
  Trace (06-spec.md:222-232) closes every cited DES with `[ADDRESSED]`. Nothing
  dropped.

- **SPEC-GATE-001 decision table (point 2)** — rows a–i cover missing / symlink
  (incl. ELOOP) / non-regular(FIFO, no block) / no-verdict-line / unsupported-value
  / changes-requested / approved-pass / last-of-many-wins / fenced-ignored, each with
  exit_code 3 on fail and 0 on pass. This is complete vs the requirement's Marker
  File Contract (00-raw:398-408) and AC-002 (00-raw:438-440), and internally
  consistent (last-of-many applies a–g to the final verdict; fenced lines never
  count, falling through to row d). Case-insensitivity on both the `Verdict:` key and
  the value is stated (06-spec.md:19-20). No missing or contradictory row. The cited
  helpers exist and behave as required: `_read_regular_text_no_symlink` (gates.py:
  1121, returns `(text|None, error∈{missing,symlink,not_regular})`,
  `O_RDONLY|O_NOFOLLOW|O_NONBLOCK`+`S_ISREG`, ELOOP→symlink) and
  `unfenced_markdown_lines` (markdown.py:24, skips fenced blocks). `GateResult`
  (gates.py:43) and `EXIT_GATE_FAIL==3` (output.py:8) are the existing types.

- **SPEC-HONEST-001 phrase/pattern mechanics (point 3)** — verified by executing the
  patterns against the exact canonical string (see observation 1). Confirmed:
  `\bcorrect\b` does **not** match inside "correctness" (the deny-set has no bare
  `correct`); `guaranteed correct` does not match "correctness guarantee" (reverse
  order, different word forms); `Verdict: Approved` does not match `review approved`
  (no adjacent "review"). The exempt strings `not a correctness guarantee` and
  `Verdict: Approved` do not trip the deny patterns. The guard is therefore
  implementable WITHOUT a bare-substring match exactly as the SPEC claims — with the
  one caveat that `review approved` is matched adjacently (observation 1). The guard
  is explicitly a test helper (06-spec.md:69), not production output, consistent with
  SCOPE-OUT and the design.

- **Canonical message verbatim (point 4)** — diffed SPEC-HONEST-001's one-line
  message (06-spec.md:64) against the requirement's FR-B4 fenced block
  (00-raw:331-336). After collapsing the requirement's line wraps, the two are
  byte-identical: same "Final whole-branch review not approved: ..." opening, same
  "Presence check on the review audit trail — not a correctness guarantee." middle
  (same em-dash), same "Record 'Verdict: Approved', or re-run with --force to archive
  an abandoned run." closing. Verbatim match confirmed.

- **SPEC-ARCHIVE-001 control flow (point 5)** — matches the real `_cmd_run_archive`
  (cli.py:632): the gate goes inside `record.status == RunStatus.EXECUTING and not
  args.force` (cli.py:647) **after** `check_execution_complete` passes (cli.py:648),
  via `print_and_exit(format_error(<joined issues>, exit_code=gate.exit_code), ...)`;
  `--force` skips the entire block (so both gates); `CLOSED_AT_PLAN_CHECKPOINT` never
  enters the block (no marker required); the success payload stays
  `{work_id, status:"archived", archived_to}` (cli.py:692). All four SPEC bullets
  (06-spec.md:44-49) are faithful, and the stated ordering (completion → final-review
  → existing clobber/gitignore/move/commit steps) matches cli.py:647-689.

- **SPEC-SEED-001 (FR-B2)** — `_cmd_run_execute_start` (cli.py:699) seeds only
  `execution/progress.md` (cli.py:734) and creates no final-review file. The
  regression contract "after run-execute-start, execution/final-review.md does not
  exist" is accurate and matches AC-005.

- **SPEC-WRITE-002 residual phrasing (point 6)** — now CORRECT. The contract
  (06-spec.md:104-115) explicitly states "install.py already validates **both** the
  manifest path and the fixed temp path via `_validate_install_path` (symlink already
  rejected today). The residual this fixes is the **fixed-name temp collision +
  check-then-write TOCTOU window**, not a missing symlink check." Verified against
  code: install.py:207 validates `manifest_path`, install.py:213 validates `tmp`, and
  `_validate_install_path` (install.py:835-845) rejects a symlink target and
  symlinked ancestors. The fix (keep both validations + `O_EXCL` unique temp) does
  not weaken validation. This is the precise correction my design review flagged
  (design-review-v2 observation 3) and the SPEC has incorporated it. The one residual
  caveat: the matrix row "temp-symlink reject" (06-spec.md:184) is a regression-guard
  for behavior that already passes today, not a new capability — fine as a guard, but
  the genuinely new test value is the `O_EXCL` unique-name behavior.

- **SPEC-WRITE-001 and SPEC-STATE-001 testable contracts (point 7)** —
  SPEC-WRITE-001 (06-spec.md:96-102): reject if either `02-project-context.{json,md}`
  `is_symlink()`, else `atomic_write_text` each, return `(md_path, json_path)`
  unchanged. Matches `write_context_pack` (context_pack.py:167, plain `write_text`
  today, returns `(md_path, json_path)`) and `atomic_write_text` (atomic.py:9,
  unique-temp+`O_EXCL`+`O_NOFOLLOW`+`os.replace`). Testable: symlink-at-json,
  symlink-at-md, normal-build-writes-both. SPEC-STATE-001 (06-spec.md:117-123):
  after `new_mgr.save`, if `source_mgr.save` raises, remove `new_run_dir` and do not
  leave a persisted new run, re-raise; normal reopen unchanged. Matches
  `_cmd_run_reopen` (cli.py:496; `new_mgr.save` at 603, EXECUTING-source transition +
  `source_mgr.save` at 605-616, no rollback today). Testable: simulated source-save
  failure → no orphan + source stays EXECUTING; normal reopen unchanged.

- **Test Matrix vs Test Plan (point 8)** — every Test-Plan item (00-raw:456-478) has
  a matrix row: gates cases (missing/approved/changes-requested/unsupported/symlink/
  FIFO/fenced-ignored/last-of-many both directions) → 10 rows (06-spec.md:164-173);
  cli archive (blocked/passes/force/closed-at-plan/update-existing-successes/
  not-seeded) → 6 rows (06-spec.md:174-179); honesty allow + deny → 2 rows
  (06-spec.md:180-181); docs-consistency new tokens + sync + gap-open-absent → 1 row
  (06-spec.md:182); context_pack → 1 row; install → 1 row; reopen → 1 row. The five
  new guarded tokens (`Model Selection`, `HEAD~1`, `execution/final-review.md`,
  `Verdict: Approved`, `re-run the full verification suite`) are named in the
  API/Data contract (06-spec.md:149-151) and match AC-008. No Test-Plan item lacks a
  matrix row. The matrix correctly targets existing modules (no new test module),
  consistent with the requirement's "No new file is created for tests."

- **PLAN Handoff sequencing (point 9)** — T1→T6 each consume named SPEC IDs and the
  grouping (T1 gate; T2 archive+seed+honesty; T3 templates+docs+tokens; T4/T5/T6 the
  three Part-D fixes) respects A–C-first / D-separable (06-spec.md:204-214). T2
  correctly bundles SPEC-ARCHIVE-001 + SPEC-SEED-001 + SPEC-HONEST-001 + the
  existing-test updates in one task (they touch the same archive path and test
  module). The restated Global Constraints (Python-only stdlib+pyyaml, CLI/agent
  boundary, no affirmative correctness wording, suite+docs-consistency green,
  `.venv/bin/python -m pytest tests/ -v`) are sufficient to task out PLAN-TASKs with
  `Spec References`. Each SPEC contract carries enough detail (signatures, decision
  rows, message text, file paths) to write `Skeleton`/`Steps`/`Verification`.

- **Unresolved ambiguity / hedges (point 10)** — none lacking a decision. The SPEC
  has no "Decision Requests" / open-questions section and introduces no undecided
  hedge; every contract states a concrete behavior. The only soft spots are
  observations 1 and 4 (implementation-precision notes the SPEC's own tests will
  catch), not undecided product questions. Scope discipline is intact: the Non-goals
  section (06-spec.md:189-200) restates SCOPE-OUT-001..008 and nothing in the
  contracts violates them (no correctness verification, no new dependency/module/
  service, no transition/schema/tier/other-gate change, gemini shim untouched,
  opencode derived, marker not a hard barrier).

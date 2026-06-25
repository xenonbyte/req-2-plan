# Plan

## Global Constraints

Restated for every implementer and reviewer (copy verbatim into reviewer prompts):

- **Python-only**, stdlib + `pyyaml` only. No new module, service, database,
  telemetry, network dependency, or worktree. Tests run as
  `.venv/bin/python -m pytest` (system `python3` lacks `pyyaml`).
- **CLI/agent boundary:** the CLI validates structure and recorded state; it never
  runs code, runs tests, or asserts a recorded verdict is true. The marker gate is a
  presence/audit check at the same trust level as the existing PLAN-TASK checkbox
  cross-check.
- **No affirmative correctness wording** on any archive-path output or gate message.
  Every final-review gate failure message carries the disclaimer
  `not a correctness guarantee`; the archive success payload stays state-only
  (`status: archived`).
- **No change** to workflow state transitions, artifact schemas, tier semantics, or
  any other gate. New surface = one gate function + one archive wiring line +
  template/docs prose + three separable Part-D fixes.
- **Surface sync:** both `r2p-execute` surfaces stay byte-synced on every guarded
  token; all pre-existing required SDD tokens remain; `r2p-gap-open` stays absent.
  gemini shim and opencode (derived) are not hand-edited.
- **Sequencing:** T1→T3 are the SDD theme (land together). T4→T6 (Part D) are
  separable and may land in a separate change; they are not blockers for T1→T3.
- **TDD:** every task writes the failing test first, then the implementation.
- **Verification of done:** `.venv/bin/python -m pytest tests/ -v` stays green
  (full suite), plus each task's targeted module.

## Tasks

### PLAN-TASK-001 — New final-review presence gate `check_final_review_recorded`
Spec References: SPEC-GATE-001
Change Type: modify
TDD Applicable: yes
Files:
- tools/workflow_cli/gates.py
- tests/test_gates.py
Skeleton:
```python
# gates.py — place beside check_execution_complete; reuse existing helpers.
# Closes SCOPE-IN-002 (Part B gate function).
_FINAL_REVIEW_DISCLAIMER = (
    "Presence check on the review audit trail — not a correctness guarantee."
)
_SUPPORTED_VERDICTS = {"approved", "changes requested"}

def check_final_review_recorded(run_dir: Path) -> GateResult:
    """Archive precondition: the final whole-branch review verdict is recorded.

    Presence/audit only — never runs code or tests, never asserts the verdict is
    true. Same trust level as the PLAN-TASK checkbox gate.
    """
    marker = run_dir / "execution" / "final-review.md"
    text, err = _read_regular_text_no_symlink(marker)
    if err == "missing" or (err is None and text is not None and not _has_verdict(text)):
        # missing file OR present-but-no-verdict both report the canonical
        # not-approved message (the requirement's verbatim text).
        return _fail(
            "Final whole-branch review not approved: execution/final-review.md is "
            "missing, or its current (last unfenced) 'Verdict:' line is not "
            "'Approved'. " + _FINAL_REVIEW_DISCLAIMER.replace("Presence", "Presence")
            + " Record 'Verdict: Approved', or re-run with --force to archive an "
            "abandoned run."
        )
    if err == "symlink":
        return _fail("execution/final-review.md is a symlink; refusing to read "
                     "outside the run directory. " + _FINAL_REVIEW_DISCLAIMER)
    if err == "not_regular":
        return _fail("execution/final-review.md is not a regular file. "
                     + _FINAL_REVIEW_DISCLAIMER)
    assert text is not None
    current = _current_verdict(text)            # last unfenced 'Verdict:' value, lower()
    if current is None:                          # defensive; covered by the missing-branch above
        return _fail("execution/final-review.md records no 'Verdict:' line. "
                     + _FINAL_REVIEW_DISCLAIMER)
    if current not in _SUPPORTED_VERDICTS:
        return _fail(f"execution/final-review.md current 'Verdict:' value is "
                     f"unsupported. " + _FINAL_REVIEW_DISCLAIMER)
    if current == "changes requested":
        return _fail("Final whole-branch review not approved: current 'Verdict:' is "
                     "'Changes Requested'. " + _FINAL_REVIEW_DISCLAIMER)
    return GateResult(passed=True, issues=[], exit_code=0)

def _current_verdict(text: str) -> str | None:
    value = None
    for line, _, _ in unfenced_markdown_lines(text):     # fenced 'Verdict:' ignored
        s = line.strip()
        if s[:8].lower() == "verdict:":
            value = s[8:].strip().lower()                 # last one wins
    return value
# _has_verdict(text) := _current_verdict(text) is not None
# _fail(msg) := GateResult(passed=False, issues=[msg], exit_code=EXIT_GATE_FAIL)
```
Steps:
- [ ] Write `tests/test_gates.py` cases first (red): missing→fail; final `Verdict: Approved`→pass(exit 0); final `Verdict: Changes Requested`→fail; unsupported value (`Verdict: Maybe`)→fail; symlink→fail; FIFO non-regular→fail without blocking; `Verdict:` only inside a code fence→not counted; CR-then-Approved→pass; Approved-then-CR→fail.
- [ ] Implement `check_final_review_recorded` reusing `_read_regular_text_no_symlink` and `unfenced_markdown_lines`; keep the canonical not-approved message verbatim per SPEC-HONEST-001.
- [ ] Confirm `EXIT_GATE_FAIL` (3) on every failure path.
Verification: `.venv/bin/python -m pytest tests/test_gates.py -v` passes (all new cases green).
Scope: carries SCOPE-IN-002 (Part B gate function) and SCOPE-IN-005 (gate unit tests).

### PLAN-TASK-002 — Wire gate into archive; not-seeded; honesty guard
Spec References: SPEC-ARCHIVE-001, SPEC-SEED-001, SPEC-HONEST-001
Change Type: modify
TDD Applicable: yes
Files:
- tools/workflow_cli/cli.py
- tests/test_cli.py
Skeleton:
```python
# cli.py::_cmd_run_archive — inside the existing
#   `record.status == RunStatus.EXECUTING and not args.force` block,
# AFTER check_execution_complete passes. Closes SCOPE-IN-002.
        review_gate = check_final_review_recorded(run_dir)
        if not review_gate.passed:
            print_and_exit(
                format_error(" ".join(review_gate.issues),
                             exit_code=review_gate.exit_code),
                review_gate.exit_code,
            )
# _cmd_run_execute_start: UNCHANGED — must NOT create execution/final-review.md
# (regression test asserts non-creation). Closes SCOPE-IN-002 (not-seeded).

# tests/test_cli.py — honesty guard test helper (phrase/pattern, NOT substring).
# Closes SCOPE-IN-005 (honesty guard) and SCOPE-IN-002.
import re
_HONESTY_DENY = [
    re.compile(r"\bverified\b", re.I),
    re.compile(r"\bvalidated\b", re.I),
    re.compile(r"\bguaranteed\s+correct\b", re.I),
    re.compile(r"\bcorrect(?:ness)?\s+is\s+guaranteed\b", re.I),
    re.compile(r"\bproven\s+correct\b", re.I),
    re.compile(r"\breview\s+approved\b", re.I),   # ADJACENT words only:
    #   \s+ matches whitespace, so "review not approved" (canonical msg) does NOT
    #   match. Do NOT use review.*approved — a flexible gap false-positives on it.
]
def assert_archive_output_honest(message: str) -> None:
    for pat in _HONESTY_DENY:
        assert not pat.search(message), f"dishonest correctness claim: {pat.pattern!r}"
    # Allowed literals must pass: 'Verdict: Approved', 'not a correctness guarantee'.
```
Steps:
- [ ] Red: `tests/test_cli.py` — executing-run archive blocked when marker missing even with a complete ledger (exit 3); passes with an approved marker; `--force` bypasses both gates; closed-at-plan archive unaffected; `run-execute-start` leaves no `execution/final-review.md`.
- [ ] Update existing executing-archive success tests (e.g. `test_archive_executing_run_with_complete_ledger`, `test_archive_passes_when_ledger_covers_all_plan_tasks`, and any other executing-archive success) to seed an approved `execution/final-review.md`.
- [ ] Add the honesty guard: allowlist coverage so every mode-specific gate message and the archive success output pass; negative tests that `verified` / `guaranteed correct` / `review approved` trip the guard while `not a correctness guarantee` and `Verdict: Approved` do not.
- [ ] Implement the archive wiring after `check_execution_complete`; import the new gate.
Verification: `.venv/bin/python -m pytest tests/test_cli.py -v` passes (new + updated cases green).
Scope: carries SCOPE-IN-002 (Part B archive wiring / not-seeded) and SCOPE-IN-005 (archive + honesty-guard tests).

### PLAN-TASK-003 — Part A template prose (both surfaces) + Part C docs + token guard
Spec References: SPEC-TMPL-001, SPEC-DOCS-001
Change Type: modify
TDD Applicable: yes
Files:
- tools/workflow_cli/agent_templates/claude/commands/r2p-execute.md
- tools/workflow_cli/agent_templates/codex/skills/r2p-execute/SKILL.md
- CLAUDE.md
- tests/test_docs_consistency.py
Skeleton:
```text
# Both r2p-execute surfaces (kept byte-synced on guarded tokens). Closes
# SCOPE-IN-001 (Part A) and, with CLAUDE.md, SCOPE-IN-003 (Part C). Terse — prefer
# one-line additions; the upstream 400+ line skill is a principle source, not a
# length target.
## Model Selection
- Mechanical implementation (isolated, clear spec, 1–2 files) → fast/cheap model.
- Integration / judgment / debugging → standard model.
- Architecture/design AND the final whole-branch review → most capable model.
- Always specify the model explicitly; an omitted model inherits the session model.
- Turn count beats token price: mid-tier floor for reviewers/prose-implementers.
# Step 5: record BASE = `git rev-parse HEAD` BEFORE dispatch; never use HEAD~1.
#   After DONE: mkdir -p .req-to-plan/<work-id>/logs ;
#   git diff -U10 <base-commit> HEAD > .req-to-plan/<work-id>/logs/task-N-diff.md
#   Hand the reviewer the diff FILE PATH (reviewer-input list: the diff file path).
# Reviewer discipline: copy Global Constraints verbatim; never pre-judge severity;
#   never paste prior-task summaries into a later dispatch.
# Continuous execution: no "should I continue?" between tasks; stop only on
#   unresolvable BLOCKED / upstream defect / dirty-tree / all-done. Verification
#   requires fresh command output; no DONE without it.
# Final review: re-run the full verification suite on final HEAD + attach output;
#   task-by-task PLAN checklist; ONE consolidated fix subagent; most-capable model;
#   then write execution/final-review.md (range, one-line summary, Verdict:).
#   Note r2p-archive refuses unless current verdict is `Verdict: Approved`.

# CLAUDE.md Invariants: add (a) marker gate = presence/audit, no correctness
# verification; (b) closure enforced at PLAN gate, 04–06 no forward full-coverage.
# Update the Test-rules r2p-execute token description; NO hardcoded test count.

# tests/test_docs_consistency.py: extend the execute-surface required tuple with
#   "Model Selection", "HEAD~1", "execution/final-review.md", "Verdict: Approved",
#   "re-run the full verification suite". Keep the r2p-gap-open-absent guard.
```
Steps:
- [ ] Red: add the five new tokens to the required tuple in `tests/test_docs_consistency.py`; run it to see both surfaces fail.
- [ ] Edit both `r2p-execute` surfaces identically (Model Selection, diff-as-file under logs/, BASE/no-HEAD~1 rule, reviewer discipline, continuous-exec + evidence, stronger final review writing `execution/final-review.md`); preserve all pre-existing SDD tokens; keep `r2p-gap-open` absent.
- [ ] Add the two `CLAUDE.md` Invariants lines and update the Test-rules token description; introduce no hardcoded test count.
- [ ] Confirm the two surfaces stay byte-synced on the guarded tokens.
Verification: `.venv/bin/python -m pytest tests/test_docs_consistency.py -v` passes (both surfaces carry all new + existing tokens; `r2p-gap-open` absent; no hardcoded test count).
Scope: carries SCOPE-IN-001 (Part A template enhancements) and SCOPE-IN-003 (Part C closure-model docs).

### PLAN-TASK-004 — Atomic, symlink-checked Context Pack write (Part D)
Spec References: SPEC-WRITE-001
Change Type: modify
TDD Applicable: yes
Files:
- tools/workflow_cli/context_pack.py
- tests/test_context_pack.py
Skeleton:
```python
# context_pack.py::write_context_pack — Closes SCOPE-IN-004 (FR-D1). Separable.
from tools.workflow_cli.atomic import atomic_write_text

def write_context_pack(pack: ProjectContextPack, run_dir: Path) -> tuple[Path, Path]:
    json_path = run_dir / "02-project-context.json"
    md_path = run_dir / "02-project-context.md"
    for target in (json_path, md_path):
        if target.is_symlink():
            raise ValueError(f"refusing to write through symlink: {target}")
    atomic_write_text(json_path, to_json(pack))
    atomic_write_text(md_path, to_markdown(pack))
    return md_path, json_path
```
Steps:
- [ ] Red: `tests/test_context_pack.py` — a symlink planted at the json path is rejected (not written through); same for the md path; a normal build still writes both files.
- [ ] Implement the symlink reject + `atomic_write_text` for both targets; keep the return tuple unchanged.
Verification: `.venv/bin/python -m pytest tests/test_context_pack.py -v` passes.
Scope: carries SCOPE-IN-004 (Part D — FR-D1 Context Pack write).

### PLAN-TASK-005 — Unique-temp install manifest write (Part D)
Spec References: SPEC-WRITE-002
Change Type: modify
TDD Applicable: yes
Files:
- tools/workflow_cli/install.py
- tests/test_install.py
Skeleton:
```python
# install.py — Closes SCOPE-IN-004 (FR-D2). The residual is the fixed-name temp
# collision + check-then-write TOCTOU window (NOT a missing symlink check;
# _validate_install_path already rejects symlinks on both paths today).
def _write_manifest_atomic(self, manifest_path: Path, data: str) -> None:
    self._validate_install_path(manifest_path, field="manifest")
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    flags |= getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    last_err = None
    for _ in range(100):
        tmp = manifest_path.with_name(
            f".{manifest_path.name}.{os.getpid()}.{secrets.token_hex(8)}.tmp")
        self._validate_install_path(tmp, field="manifest")   # keep existing rule
        try:
            fd = os.open(tmp, flags, 0o666)
        except FileExistsError as exc:
            last_err = exc; continue
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(data)
            os.replace(tmp, manifest_path)
            return
        except BaseException:
            try: tmp.unlink()
            except FileNotFoundError: pass
            raise
    raise FileExistsError(f"could not create unique manifest temp for {manifest_path}") from last_err
# Replace the fixed-name manifest.yaml.tmp write (install.py ~209-215) with this.
```
Steps:
- [ ] Red: `tests/test_install.py` — the manifest is still written and replaced on a normal install; a symlink planted at the temp path is rejected.
- [ ] Implement the install-local unique-temp helper preserving `_validate_install_path` on both the manifest and the temp path; replace the fixed-name temp write.
Verification: `.venv/bin/python -m pytest tests/test_install.py -v` passes.

### PLAN-TASK-006 — Transactional run-reopen from EXECUTING (Part D)
Spec References: SPEC-STATE-001
Change Type: modify
TDD Applicable: yes
Files:
- tools/workflow_cli/cli.py
- tests/test_cli.py
Skeleton:
```python
# cli.py::_cmd_run_reopen — Closes SCOPE-IN-004 (FR-D3). After new_mgr.save(...),
# make the EXECUTING-source transition+save transactional (match archive's level).
    new_mgr = RunStateManager(new_run_dir)
    new_mgr.save(new_record)
    if source_record.status == RunStatus.EXECUTING:
        try:
            source_record = update_run_status(source_record, RunStatus.CLOSED_AT_PLAN_CHECKPOINT)
            source_record.current_stage = Stage.CLOSED
            update_resume_context(source_record, last_operation="reopen_from_execution",
                                  next_operation=f"continue_reopened_run:{new_work_id}")
            source_mgr.save(source_record)
        except Exception:
            # roll back the just-created new run so no orphan is left and the
            # source stays consistently EXECUTING.
            shutil.rmtree(new_run_dir, ignore_errors=True)
            raise
```
Steps:
- [ ] Red: `tests/test_cli.py` — simulate a source-save failure (e.g. monkeypatch `source_mgr.save` / `RunStateManager.save` to raise on the source) and assert no orphan `new_run_dir` remains and the source stays `EXECUTING`; assert a normal reopen is unchanged.
- [ ] Implement the try/except rollback around the EXECUTING-source transition+save.
Verification: `.venv/bin/python -m pytest tests/test_cli.py -v -k reopen` passes; full `tests/test_cli.py` stays green.

## Trace
<!-- Map this stage's IDs to upstream/downstream. R3 derives & checks closure. -->
| This ID | Upstream | Status |
|---|---|---|
| PLAN-TASK-001 | SPEC-GATE-001 | open |
| PLAN-TASK-002 | SPEC-ARCHIVE-001, SPEC-SEED-001, SPEC-HONEST-001 | open |
| PLAN-TASK-003 | SPEC-TMPL-001, SPEC-DOCS-001 | open |
| PLAN-TASK-004 | SPEC-WRITE-001 | open |
| PLAN-TASK-005 | SPEC-WRITE-002 | open |
| PLAN-TASK-006 | SPEC-STATE-001 | open |

## Upstream Summary (read-only)
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

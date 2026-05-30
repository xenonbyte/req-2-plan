# Part 1 — Close the End-to-End Loop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire the missing review→approve→advance state transitions so a non-forced run drives from `run-start` to `CLOSED_AT_PLAN_CHECKPOINT` purely through CLI/shortcut commands, and make `r2p-continue` a real driver.

**Architecture:** The CLI holds state authority; every transition goes through `update_run_status` (which enforces `ALLOWED_TRANSITIONS`). Three new commands (`review-checkpoint`, `checkpoint-decide`, `stage-advance`) add the approve/advance segment; five existing handlers are corrected (gate-entry persistence, gate-quality readiness, forced-review guard relocation, repair-loop status flips, NEXT_STAGE produce guard). Checkpoints are human approvals — the CLI never auto-approves.

**Tech Stack:** Python 3.10+ stdlib only (argparse, pathlib, unittest via pytest), Markdown run state. Tests run with `.venv/bin/python -m pytest`.

**Design source:** `docs/2026-05-30-workflow-fixes-and-plan-optimization.md` Part 1 (Approved). All decisions resolved there.

**Pre-verified facts (2026-05-31):**
- `ALLOWED_TRANSITIONS` (`models.py:103-150`) already permits every transition below; no state-table edit needed.
- `check_forced_subagent_review(stage, tier, reviews_dir)` (`gates.py:208`) has no `version` param and globs any `*-review-*.md`.
- `_cmd_gate_entry` (`cli.py:514`) is read-only. `cli.py:697` (ACTIVE_STAGE_DRAFT write) is in `_cmd_stage_produce`.
- `is_command_allowed` is never called in cli.py; guards must be explicit in handlers.

**Conventions (copy these — they are how this repo's tests/handlers already work):**
- Test helpers from `tests/test_cli.py`: `invoke(args, base_path=, expect_exit=0)`, `load_record(base_path, work_id)`, `save_record(base_path, record)`, `plan_checkpoint()`, `requirement_checkpoint()`.
- Handlers start with `record, mgr, run_dir = _load_run(args.work_id, args.base_path)` then `stage = _parse_stage(args.stage)`.
- Exit codes (`output.py`): `EXIT_OK=0`, `EXIT_CLI_ERR=2`, `EXIT_GATE_FAIL=3`, `EXIT_REVIEW_REQ=5`, `EXIT_CONFLICT=6`, `EXIT_NOT_FOUND=7`.
- Finish handlers with `print_and_exit(format_success({...}, message="..."), EXIT_OK)`.
- Run tests: `.venv/bin/python -m pytest tests/test_cli.py -v` (never bare `pytest`).
- Commit after each green task.

---

## Group 1a — State-machine self-consistency (no new commands)

Land these first: they make existing handlers route through `update_run_status` and close the three repair loops, so the new commands in 1b build on a consistent machine.

### Task 1: Migrate gate-quality + stage-produce direct status writes to `update_run_status`

**Files:**
- Modify: `tools/workflow_cli/cli.py` (`_cmd_gate_quality` ~555/574; `_cmd_stage_produce` ~675/697)
- Test: `tests/test_cli.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_cli.py`:

```python
class TestStateAuthority:
    def test_gate_quality_uses_validated_transition(self):
        """gate-quality must reach READY via update_run_status, not a raw write."""
        with tempfile.TemporaryDirectory() as tmp:
            work_id = "WF-20260527-auth"
            invoke(["run-start", "--work-id", work_id, "--requirement", "foo"], base_path=tmp)
            invoke(["tier-lock", "--work-id", work_id, "--base", "light", "--confirm"], base_path=tmp)
            invoke(["stage-produce", "--work-id", work_id, "--stage", "raw_requirement",
                    "--content", "Some real content here."], base_path=tmp)
            invoke(["stage-ready", "--work-id", work_id, "--stage", "raw_requirement"], base_path=tmp)
            invoke(["gate-quality", "--work-id", work_id, "--stage", "raw_requirement"], base_path=tmp)
            record = load_record(tmp, work_id)
            assert record.status == RunStatus.READY_FOR_CHECKPOINT_REVIEW
```

- [ ] **Step 2: Run test to verify current behavior**

Run: `.venv/bin/python -m pytest tests/test_cli.py::TestStateAuthority::test_gate_quality_uses_validated_transition -v`
Expected: this may PASS already (the raw write produces the same status). It is a regression guard — keep it. If it fails because `stage-ready` is now required before `gate-quality` (Task 3), that ordering is intended.

- [ ] **Step 3: Migrate the four direct writes**

In `_cmd_gate_quality`, replace `record.status = RunStatus.QUALITY_GATE_FAILED` (line ~555) with:

```python
        record = update_run_status(record, RunStatus.QUALITY_GATE_FAILED)
```

and `record.status = RunStatus.READY_FOR_CHECKPOINT_REVIEW` (line ~574) with:

```python
        record = update_run_status(record, RunStatus.READY_FOR_CHECKPOINT_REVIEW)
```

In `_cmd_stage_produce`, replace `record.status = RunStatus.ENTRY_GATE_FAILED` (line ~675) with:

```python
        record = update_run_status(record, RunStatus.ENTRY_GATE_FAILED)
```

and `record.status = RunStatus.ACTIVE_STAGE_DRAFT` (line ~697) with:

```python
    record = update_run_status(record, RunStatus.ACTIVE_STAGE_DRAFT)
```

`update_run_status` is already imported in `cli.py`.

- [ ] **Step 4: Run the full CLI suite to confirm no transition is rejected**

Run: `.venv/bin/python -m pytest tests/test_cli.py -v`
Expected: PASS. If any test now fails with "Invalid status transition", that test was relying on an illegal direct write — note it; Tasks 2–3 add the repair flips that legalize re-run paths.

- [ ] **Step 5: Commit**

```bash
git add tools/workflow_cli/cli.py tests/test_cli.py
git commit -m "refactor(cli): route gate-quality/stage-produce status changes through update_run_status"
```

### Task 2: Close the CHECKPOINT_CHANGES_REQUESTED and QUALITY_GATE_FAILED repair loops

**Files:**
- Modify: `tools/workflow_cli/cli.py` (`_cmd_stage_update` ~712; `_cmd_stage_produce` ~654)
- Modify: `tools/workflow_cli/models.py` (`ALLOWED_COMMANDS_BY_RUN_STATE[QUALITY_GATE_FAILED]` ~200)
- Test: `tests/test_cli.py`

- [ ] **Step 1: Write the failing test**

```python
class TestRepairLoops:
    def _to_quality_failed(self, tmp, work_id):
        invoke(["run-start", "--work-id", work_id, "--requirement", "foo"], base_path=tmp)
        invoke(["tier-lock", "--work-id", work_id, "--base", "light", "--confirm"], base_path=tmp)
        invoke(["stage-produce", "--work-id", work_id, "--stage", "raw_requirement",
                "--content", "x"], base_path=tmp)
        record = load_record(tmp, work_id)
        record.status = RunStatus.QUALITY_GATE_FAILED
        save_record(tmp, record)

    def test_stage_update_flips_quality_failed_to_draft(self):
        with tempfile.TemporaryDirectory() as tmp:
            work_id = "WF-20260527-rq"
            self._to_quality_failed(tmp, work_id)
            invoke(["stage-update", "--work-id", work_id, "--stage", "raw_requirement",
                    "--content", "repaired content"], base_path=tmp)
            record = load_record(tmp, work_id)
            assert record.status == RunStatus.ACTIVE_STAGE_DRAFT

    def test_stage_update_flips_changes_requested_to_draft(self):
        with tempfile.TemporaryDirectory() as tmp:
            work_id = "WF-20260527-cr"
            invoke(["run-start", "--work-id", work_id, "--requirement", "foo"], base_path=tmp)
            invoke(["stage-produce", "--work-id", work_id, "--stage", "raw_requirement",
                    "--content", "x"], base_path=tmp)
            record = load_record(tmp, work_id)
            record.status = RunStatus.CHECKPOINT_CHANGES_REQUESTED
            save_record(tmp, record)
            invoke(["stage-update", "--work-id", work_id, "--stage", "raw_requirement",
                    "--content", "addressed changes"], base_path=tmp)
            record = load_record(tmp, work_id)
            assert record.status == RunStatus.ACTIVE_STAGE_DRAFT
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_cli.py::TestRepairLoops -v`
Expected: FAIL — `stage-update` leaves status at QUALITY_GATE_FAILED / CHECKPOINT_CHANGES_REQUESTED (it only sets the artifact to "draft", never the run status).

- [ ] **Step 3: Add the status flip to `_cmd_stage_update`**

In `_cmd_stage_update`, after `upsert_active_artifact(record, stage, artifact_file, new_version, "draft")` and before `update_resume_context(...)`, insert:

```python
    if record.status in (RunStatus.CHECKPOINT_CHANGES_REQUESTED, RunStatus.QUALITY_GATE_FAILED):
        record = update_run_status(record, RunStatus.ACTIVE_STAGE_DRAFT)
```

- [ ] **Step 4: Allow CMD-STAGE-UPDATE from QUALITY_GATE_FAILED in the matrix**

In `tools/workflow_cli/models.py`, in `ALLOWED_COMMANDS_BY_RUN_STATE[RunStatus.QUALITY_GATE_FAILED]` (the set starting ~line 200), add `"CMD-STAGE-UPDATE",` after `"CMD-STAGE-PRODUCE",`:

```python
    RunStatus.QUALITY_GATE_FAILED: {
        "CMD-STAGE-PRODUCE",
        "CMD-STAGE-UPDATE",
        "CMD-STAGE-READY",
        "CMD-GATE-QUALITY",
        ...
```

(Leave the rest of the set unchanged.)

- [ ] **Step 5: Run to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_cli.py::TestRepairLoops -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add tools/workflow_cli/cli.py tools/workflow_cli/models.py tests/test_cli.py
git commit -m "fix(cli): stage-update flips repair states back to active_stage_draft"
```

### Task 3: gate-quality requires a `ready` artifact

**Files:**
- Modify: `tools/workflow_cli/cli.py` (`_cmd_gate_quality` ~529)
- Modify: `tests/test_cli.py` (existing `test_runs_quality_check_after_tier_lock` ~498)
- Test: `tests/test_cli.py`

- [ ] **Step 1: Write the failing test**

```python
class TestGateQualityReadiness:
    def test_gate_quality_refuses_unready_artifact(self):
        with tempfile.TemporaryDirectory() as tmp:
            work_id = "WF-20260527-nr"
            invoke(["run-start", "--work-id", work_id, "--requirement", "foo"], base_path=tmp)
            invoke(["tier-lock", "--work-id", work_id, "--base", "light", "--confirm"], base_path=tmp)
            invoke(["stage-produce", "--work-id", work_id, "--stage", "raw_requirement",
                    "--content", "draft only, never marked ready"], base_path=tmp)
            invoke(["gate-quality", "--work-id", work_id, "--stage", "raw_requirement"],
                   base_path=tmp, expect_exit=6)

    def test_gate_quality_accepts_ready_artifact(self):
        with tempfile.TemporaryDirectory() as tmp:
            work_id = "WF-20260527-rdy"
            invoke(["run-start", "--work-id", work_id, "--requirement", "foo"], base_path=tmp)
            invoke(["tier-lock", "--work-id", work_id, "--base", "light", "--confirm"], base_path=tmp)
            invoke(["stage-produce", "--work-id", work_id, "--stage", "raw_requirement",
                    "--content", "real content"], base_path=tmp)
            invoke(["stage-ready", "--work-id", work_id, "--stage", "raw_requirement"], base_path=tmp)
            invoke(["gate-quality", "--work-id", work_id, "--stage", "raw_requirement"], base_path=tmp)
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_cli.py::TestGateQualityReadiness -v`
Expected: `test_gate_quality_refuses_unready_artifact` FAILS (gate-quality currently accepts a draft, exits 0 not 6).

- [ ] **Step 3: Add the readiness precondition**

In `_cmd_gate_quality`, right after `stage = _parse_stage(args.stage)` and before reading content, insert:

```python
    from tools.workflow_cli.state import get_active_artifact
    aa = get_active_artifact(record, stage)
    if aa is None or aa.status != "ready":
        print_and_exit(
            format_error(
                f"Stage {stage.value!r} artifact is not ready; run stage-ready first",
                exit_code=EXIT_CONFLICT,
            ),
            EXIT_CONFLICT,
        )
```

(`get_active_artifact` exists in `state.py`.)

- [ ] **Step 4: Fix the existing produce→gate test**

In `tests/test_cli.py`, find `test_runs_quality_check_after_tier_lock` (~line 498). After its `stage-produce` invoke and before the `gate-quality` invoke, insert a `stage-ready` call:

```python
            invoke(
                ["stage-ready", "--work-id", "WF-20260527-test", "--stage", "raw_requirement"],
                base_path=tmp,
            )
```

- [ ] **Step 5: Run to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_cli.py -k "GateQuality or runs_quality_check" -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add tools/workflow_cli/cli.py tests/test_cli.py
git commit -m "fix(cli): gate-quality requires a ready artifact before evaluation"
```

### Task 4: gate-entry persists status in NEXT_STAGE and ENTRY_GATE_FAILED

**Files:**
- Modify: `tools/workflow_cli/cli.py` (`_cmd_gate_entry` ~514)
- Test: `tests/test_cli.py`

- [ ] **Step 1: Write the failing test**

```python
class TestGateEntryPersistence:
    def test_gate_entry_persists_from_next_stage(self):
        with tempfile.TemporaryDirectory() as tmp:
            work_id = "WF-20260527-ns"
            invoke(["run-start", "--work-id", work_id, "--requirement", "foo"], base_path=tmp)
            record = load_record(tmp, work_id)
            # raw_requirement has no required upstream checkpoints, so entry gate passes.
            record.status = RunStatus.NEXT_STAGE
            save_record(tmp, record)
            invoke(["gate-entry", "--work-id", work_id, "--stage", "raw_requirement"], base_path=tmp)
            record = load_record(tmp, work_id)
            assert record.status == RunStatus.ACTIVE_STAGE_DRAFT

    def test_gate_entry_readonly_outside_those_states(self):
        with tempfile.TemporaryDirectory() as tmp:
            work_id = "WF-20260527-ro"
            invoke(["run-start", "--work-id", work_id, "--requirement", "foo"], base_path=tmp)
            invoke(["gate-entry", "--work-id", work_id, "--stage", "raw_requirement"], base_path=tmp)
            record = load_record(tmp, work_id)
            assert record.status == RunStatus.ACTIVE_STAGE_DRAFT  # unchanged from run-start
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_cli.py::TestGateEntryPersistence -v`
Expected: `test_gate_entry_persists_from_next_stage` FAILS (gate-entry is read-only; status stays NEXT_STAGE).

- [ ] **Step 3: Make gate-entry persist in the two repair/advance states**

Replace the body of `_cmd_gate_entry` from the `output = ...` line onward with:

```python
    result = check_entry_gate(
        run_dir,
        stage,
        record.approved_checkpoints,
        record.bundle_authorizations,
    )

    if record.status in (RunStatus.NEXT_STAGE, RunStatus.ENTRY_GATE_FAILED):
        target = RunStatus.ACTIVE_STAGE_DRAFT if result.passed else RunStatus.ENTRY_GATE_FAILED
        record = update_run_status(record, target)
        update_resume_context(
            record,
            last_operation=f"entry_gate_{'passed' if result.passed else 'failed'}_{stage.value}",
            next_operation="produce_stage_artifact" if result.passed else "repair_upstream_checkpoint",
            active_item=stage.value,
        )
        mgr.save(record)

    output = format_gate_result(result, gate_type="entry-gate")
    exit_code = EXIT_OK if result.passed else result.exit_code
    print_and_exit(output, exit_code)
```

(Note: `ENTRY_GATE_FAILED → ENTRY_GATE_FAILED` is a no-op re-write; guard it if `update_run_status` rejects same-state — it does not, since `ALLOWED_TRANSITIONS` for a failed re-run targets ACTIVE on pass. On fail from ENTRY_GATE_FAILED the status is already ENTRY_GATE_FAILED, so only call `update_run_status` when `target != record.status`:)

Wrap the transition:

```python
    if record.status in (RunStatus.NEXT_STAGE, RunStatus.ENTRY_GATE_FAILED):
        target = RunStatus.ACTIVE_STAGE_DRAFT if result.passed else RunStatus.ENTRY_GATE_FAILED
        if target != record.status:
            record = update_run_status(record, target)
        update_resume_context(
            record,
            last_operation=f"entry_gate_{'passed' if result.passed else 'failed'}_{stage.value}",
            next_operation="produce_stage_artifact" if result.passed else "repair_upstream_checkpoint",
            active_item=stage.value,
        )
        mgr.save(record)
```

- [ ] **Step 4: Run to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_cli.py::TestGateEntryPersistence -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tools/workflow_cli/cli.py tests/test_cli.py
git commit -m "feat(cli): gate-entry persists status in next_stage/entry_gate_failed"
```

### Task 5: stage-produce refuses NEXT_STAGE; remove CMD-STAGE-PRODUCE from the matrix there

**Files:**
- Modify: `tools/workflow_cli/cli.py` (`_cmd_stage_produce` ~654)
- Modify: `tools/workflow_cli/models.py` (`ALLOWED_COMMANDS_BY_RUN_STATE[NEXT_STAGE]` ~262)
- Test: `tests/test_cli.py`

- [ ] **Step 1: Write the failing test**

```python
class TestNextStageProduceGuard:
    def test_stage_produce_refused_in_next_stage(self):
        with tempfile.TemporaryDirectory() as tmp:
            work_id = "WF-20260527-npg"
            invoke(["run-start", "--work-id", work_id, "--requirement", "foo"], base_path=tmp)
            record = load_record(tmp, work_id)
            record.status = RunStatus.NEXT_STAGE
            save_record(tmp, record)
            invoke(["stage-produce", "--work-id", work_id, "--stage", "raw_requirement",
                    "--content", "should be refused"], base_path=tmp, expect_exit=6)
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_cli.py::TestNextStageProduceGuard -v`
Expected: FAIL (stage-produce currently runs; it only checks `stage != current_stage`).

- [ ] **Step 3: Add the NEXT_STAGE guard**

In `_cmd_stage_produce`, immediately after `stage = _parse_stage(args.stage)` and before the `if stage != record.current_stage:` check, insert:

```python
    if record.status == RunStatus.NEXT_STAGE:
        print_and_exit(
            format_error(
                "Cannot produce in next_stage; run gate-entry first to enter the stage draft",
                exit_code=EXIT_CONFLICT,
            ),
            EXIT_CONFLICT,
        )
```

- [ ] **Step 4: Remove CMD-STAGE-PRODUCE from the NEXT_STAGE matrix entry**

In `models.py`, `ALLOWED_COMMANDS_BY_RUN_STATE[RunStatus.NEXT_STAGE]` (~line 262), delete the `"CMD-STAGE-PRODUCE",` line, leaving e.g.:

```python
    RunStatus.NEXT_STAGE: {
        "CMD-GATE-ENTRY",
        "CMD-TIER-ESCALATE",
        "CMD-TIER-STATUS",
    },
```

(Keep whatever non-produce entries are already present; only remove CMD-STAGE-PRODUCE.)

- [ ] **Step 5: Run to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_cli.py::TestNextStageProduceGuard tests/test_models.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add tools/workflow_cli/cli.py tools/workflow_cli/models.py tests/test_cli.py
git commit -m "fix(cli): refuse stage-produce in next_stage (entry gate must run first)"
```

### Task 6: Classify CMD-RUN-RESUME as read-only

**Files:**
- Modify: `tools/workflow_cli/models.py` (`READ_ONLY_COMMANDS` ~161)
- Test: `tests/test_models.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_models.py`:

```python
def test_run_resume_is_read_only():
    from tools.workflow_cli.models import READ_ONLY_COMMANDS
    assert "CMD-RUN-RESUME" in READ_ONLY_COMMANDS
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_models.py::test_run_resume_is_read_only -v`
Expected: FAIL.

- [ ] **Step 3: Add CMD-RUN-RESUME to READ_ONLY_COMMANDS**

In `models.py`, add `"CMD-RUN-RESUME",` to the `READ_ONLY_COMMANDS` set (~line 161).

- [ ] **Step 4: Run to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_models.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tools/workflow_cli/models.py tests/test_models.py
git commit -m "fix(models): classify CMD-RUN-RESUME as read-only"
```

---

## Group 1b — The three new commands

### Task 7: Make the forced-review guard version-aware

**Files:**
- Modify: `tools/workflow_cli/gates.py` (`check_forced_subagent_review` ~208)
- Test: `tests/test_gates.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_gates.py` (match the existing import style there):

```python
def test_forced_review_version_aware(tmp_path):
    from tools.workflow_cli.gates import check_forced_subagent_review
    from tools.workflow_cli.models import Stage, TierBase, TierEstimate, TierModifier
    reviews = tmp_path / "reviews"
    reviews.mkdir()
    tier = TierEstimate(base=TierBase.STANDARD, modifiers=frozenset({TierModifier.SAFETY}))
    # A v1 subagent-review must NOT clear a v2 approval.
    (reviews / "design-subagent-review-v1.md").write_text("findings", encoding="utf-8")
    r2 = check_forced_subagent_review(Stage.DESIGN, tier, reviews, version=2)
    assert r2.passed is False and r2.exit_code == 5
    # The matching v2 file clears it.
    (reviews / "design-subagent-review-v2.md").write_text("findings", encoding="utf-8")
    r2b = check_forced_subagent_review(Stage.DESIGN, tier, reviews, version=2)
    assert r2b.passed is True
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_gates.py::test_forced_review_version_aware -v`
Expected: FAIL — `check_forced_subagent_review()` takes no `version` argument (TypeError).

- [ ] **Step 3: Add the `version` parameter and version-stamped match**

Change the signature and Condition-4 block in `check_forced_subagent_review`:

```python
def check_forced_subagent_review(
    stage: Stage,
    tier: TierEstimate | None,
    reviews_dir: Path,
    version: int,
) -> GateResult:
```

Replace the Condition-4 glob block with a version-stamped, subagent-only match (the checkpoint-review marker no longer satisfies the forced guard — see design QR3):

```python
    # Condition 4: a real, version-matched subagent review must exist.
    stage_name = stage.value
    subagent_file = reviews_dir / f"{stage_name}-subagent-review-v{version}.md"
    if subagent_file.exists():
        return GateResult(passed=True, issues=[], exit_code=0)
```

(Delete the old `checkpoint_pattern` / `subagent_pattern` glob and `has_review` block.)

- [ ] **Step 4: Update any existing forced-review tests in the file**

Run the gates suite; for any pre-existing call missing `version=`, add `version=1`:

Run: `.venv/bin/python -m pytest tests/test_gates.py -v`
Fix call sites flagged with TypeError by passing `version=1`, then re-run. Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tools/workflow_cli/gates.py tests/test_gates.py
git commit -m "feat(gates): version-aware forced review requiring a subagent-review file"
```

### Task 8: Add `review-checkpoint` command

**Files:**
- Modify: `tools/workflow_cli/cli.py` (new handler + register in `_register_gate_commands` or a new `_register_checkpoint_commands`)
- Modify: `tools/workflow_cli/models.py` (`ALLOWED_COMMANDS_BY_RUN_STATE`)
- Test: `tests/test_cli.py`

- [ ] **Step 1: Write the failing test**

```python
class TestReviewCheckpoint:
    def _to_ready(self, tmp, work_id, stage="raw_requirement"):
        invoke(["run-start", "--work-id", work_id, "--requirement", "foo"], base_path=tmp)
        invoke(["tier-lock", "--work-id", work_id, "--base", "light", "--confirm"], base_path=tmp)
        invoke(["stage-produce", "--work-id", work_id, "--stage", stage, "--content", "real"], base_path=tmp)
        invoke(["stage-ready", "--work-id", work_id, "--stage", stage], base_path=tmp)
        invoke(["gate-quality", "--work-id", work_id, "--stage", stage], base_path=tmp)

    def test_review_checkpoint_writes_marker_and_transitions(self):
        with tempfile.TemporaryDirectory() as tmp:
            work_id = "WF-20260527-rc"
            self._to_ready(tmp, work_id)
            invoke(["review-checkpoint", "--work-id", work_id, "--stage", "raw_requirement"], base_path=tmp)
            record = load_record(tmp, work_id)
            assert record.status == RunStatus.CHECKPOINT_REVIEW
            marker = Path(tmp) / ".req-to-plan" / work_id / "reviews" / "raw_requirement-checkpoint-review-v1.md"
            assert marker.exists()

    def test_review_checkpoint_wrong_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            work_id = "WF-20260527-rcw"
            invoke(["run-start", "--work-id", work_id, "--requirement", "foo"], base_path=tmp)
            invoke(["review-checkpoint", "--work-id", work_id, "--stage", "raw_requirement"],
                   base_path=tmp, expect_exit=6)
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_cli.py::TestReviewCheckpoint -v`
Expected: FAIL — `invalid choice: 'review-checkpoint'` (argparse).

- [ ] **Step 3: Implement the handler**

Add to `cli.py` (near the gate commands). Import `get_artifact_version` is already used elsewhere via local import; reuse that pattern:

```python
def _cmd_review_checkpoint(args):
    record, mgr, run_dir = _load_run(args.work_id, args.base_path)
    stage = _parse_stage(args.stage)

    if record.status != RunStatus.READY_FOR_CHECKPOINT_REVIEW:
        print_and_exit(
            format_error(
                f"Cannot review-checkpoint in status {record.status.value!r}; "
                "must be ready_for_checkpoint_review",
                exit_code=EXIT_CONFLICT,
            ),
            EXIT_CONFLICT,
        )
    if stage != record.current_stage:
        print_and_exit(
            format_error(
                f"Stage {stage.value!r} is not the current stage {record.current_stage.value!r}",
                exit_code=EXIT_CONFLICT,
            ),
            EXIT_CONFLICT,
        )

    from tools.workflow_cli.artifact import get_artifact_version
    version = get_artifact_version(run_dir, stage)
    reviews_dir = run_dir / "reviews"
    reviews_dir.mkdir(parents=True, exist_ok=True)
    marker = reviews_dir / f"{stage.value}-checkpoint-review-v{version}.md"
    marker.write_text(
        f"# Checkpoint review marker\n\nstage: {stage.value}\nversion: {version}\n"
        "status: ready for human decision\n",
        encoding="utf-8",
    )

    record = update_run_status(record, RunStatus.CHECKPOINT_REVIEW)
    update_resume_context(
        record,
        last_operation=f"review_checkpoint_{stage.value}",
        next_operation="checkpoint_decide",
        active_item=stage.value,
    )
    mgr.save(record)
    print_and_exit(
        format_success(
            {"work_id": str(record.work_id), "stage": stage.value, "marker": str(marker)},
            message=f"Checkpoint review opened: {stage.value}",
        ),
        EXIT_OK,
    )
```

- [ ] **Step 4: Register the command**

Add a registration function and call it in `main()`. After `_register_stage_commands(subparsers)`-style functions, add:

```python
def _register_checkpoint_commands(subparsers):
    p = subparsers.add_parser("review-checkpoint", help="Open checkpoint review for a stage")
    p.add_argument("--work-id", required=True)
    p.add_argument("--stage", required=True)
    p.set_defaults(func=_cmd_review_checkpoint)
```

And in `main()`, after `_register_stage_commands(subparsers)`:

```python
    _register_checkpoint_commands(subparsers)
```

- [ ] **Step 5: Run to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_cli.py::TestReviewCheckpoint -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add tools/workflow_cli/cli.py tests/test_cli.py
git commit -m "feat(cli): add review-checkpoint command writing a version-stamped marker"
```

### Task 9: Add `checkpoint-decide` command

**Files:**
- Modify: `tools/workflow_cli/cli.py` (new handler + register)
- Test: `tests/test_cli.py`

- [ ] **Step 1: Write the failing test**

```python
class TestCheckpointDecide:
    def _to_review(self, tmp, work_id, base="light", modifiers=None, stage="raw_requirement"):
        invoke(["run-start", "--work-id", work_id, "--requirement", "foo"], base_path=tmp)
        lock = ["tier-lock", "--work-id", work_id, "--base", base, "--confirm"]
        if modifiers:
            lock += ["--modifiers", modifiers]
        invoke(lock, base_path=tmp)
        invoke(["stage-produce", "--work-id", work_id, "--stage", stage, "--content", "real"], base_path=tmp)
        invoke(["stage-ready", "--work-id", work_id, "--stage", stage], base_path=tmp)
        invoke(["gate-quality", "--work-id", work_id, "--stage", stage], base_path=tmp)
        invoke(["review-checkpoint", "--work-id", work_id, "--stage", stage], base_path=tmp)

    def test_approve_requires_confirm(self):
        with tempfile.TemporaryDirectory() as tmp:
            work_id = "WF-20260527-cd1"
            self._to_review(tmp, work_id)
            invoke(["checkpoint-decide", "--work-id", work_id, "--stage", "raw_requirement",
                    "--decision", "approved"], base_path=tmp, expect_exit=5)

    def test_approve_non_forced_passes_with_marker(self):
        with tempfile.TemporaryDirectory() as tmp:
            work_id = "WF-20260527-cd2"
            self._to_review(tmp, work_id)
            invoke(["checkpoint-decide", "--work-id", work_id, "--stage", "raw_requirement",
                    "--decision", "approved", "--confirm"], base_path=tmp)
            record = load_record(tmp, work_id)
            assert record.status == RunStatus.CHECKPOINT_APPROVED
            assert any(cp.stage == Stage.RAW_REQUIREMENT for cp in record.approved_checkpoints)

    def test_changes_requested_transitions_and_sets_resume(self):
        with tempfile.TemporaryDirectory() as tmp:
            work_id = "WF-20260527-cd3"
            self._to_review(tmp, work_id)
            invoke(["checkpoint-decide", "--work-id", work_id, "--stage", "raw_requirement",
                    "--decision", "changes_requested"], base_path=tmp)
            record = load_record(tmp, work_id)
            assert record.status == RunStatus.CHECKPOINT_CHANGES_REQUESTED

    def test_forced_modifier_needs_subagent_review(self):
        with tempfile.TemporaryDirectory() as tmp:
            work_id = "WF-20260527-cd4"
            # design stage with safety modifier; drive to review at design.
            # Shortcut: build state directly to review at design with a ready v1 artifact.
            invoke(["run-start", "--work-id", work_id, "--requirement", "foo"], base_path=tmp)
            invoke(["tier-lock", "--work-id", work_id, "--base", "standard",
                    "--modifiers", "safety", "--confirm"], base_path=tmp)
            record = load_record(tmp, work_id)
            record.current_stage = Stage.DESIGN
            record.status = RunStatus.CHECKPOINT_REVIEW
            from tools.workflow_cli.models import ActiveArtifact
            record.active_artifacts = [ActiveArtifact(
                stage=Stage.DESIGN, artifact="05-design.md", version=1, status="ready")]
            save_record(tmp, record)
            run_dir = Path(tmp) / ".req-to-plan" / work_id
            (run_dir / "05-design.md").write_text("---\nr2p_version: 1\n---\nbody", encoding="utf-8")
            reviews = run_dir / "reviews"; reviews.mkdir(parents=True, exist_ok=True)
            (reviews / "design-checkpoint-review-v1.md").write_text("marker", encoding="utf-8")
            # marker alone -> exit 5 (forced needs subagent review)
            invoke(["checkpoint-decide", "--work-id", work_id, "--stage", "design",
                    "--decision", "approved", "--confirm"], base_path=tmp, expect_exit=5)
            (reviews / "design-subagent-review-v1.md").write_text("findings", encoding="utf-8")
            invoke(["checkpoint-decide", "--work-id", work_id, "--stage", "design",
                    "--decision", "approved", "--confirm"], base_path=tmp)
            record = load_record(tmp, work_id)
            assert record.status == RunStatus.CHECKPOINT_APPROVED
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_cli.py::TestCheckpointDecide -v`
Expected: FAIL — `invalid choice: 'checkpoint-decide'`.

- [ ] **Step 3: Implement the handler**

```python
def _cmd_checkpoint_decide(args):
    record, mgr, run_dir = _load_run(args.work_id, args.base_path)
    stage = _parse_stage(args.stage)

    if record.status != RunStatus.CHECKPOINT_REVIEW:
        print_and_exit(
            format_error(
                f"Cannot decide in status {record.status.value!r}; must be checkpoint_review",
                exit_code=EXIT_CONFLICT,
            ),
            EXIT_CONFLICT,
        )
    if stage != record.current_stage:
        print_and_exit(
            format_error(
                f"Stage {stage.value!r} is not the current stage {record.current_stage.value!r}",
                exit_code=EXIT_CONFLICT,
            ),
            EXIT_CONFLICT,
        )

    from tools.workflow_cli.state import get_active_artifact
    aa = get_active_artifact(record, stage)
    if aa is None:
        print_and_exit(
            format_error(f"No active artifact for stage {stage.value!r}", exit_code=EXIT_CONFLICT),
            EXIT_CONFLICT,
        )

    if args.decision == "changes_requested":
        record = update_run_status(record, RunStatus.CHECKPOINT_CHANGES_REQUESTED)
        update_resume_context(
            record,
            last_operation=f"changes_requested_{stage.value}",
            next_operation="repair_stage_artifact",
            active_item=stage.value,
        )
        mgr.save(record)
        print_and_exit(
            format_success(
                {"work_id": str(record.work_id), "stage": stage.value, "decision": "changes_requested"},
                message=f"Changes requested: {stage.value}",
            ),
            EXIT_OK,
        )

    # decision == "approved"
    if not args.confirm:
        print_and_exit(
            format_error(
                "Approval requires --confirm",
                exit_code=EXIT_REVIEW_REQ,
            ),
            EXIT_REVIEW_REQ,
        )

    # Duplicate-approval guard.
    if any(cp.stage == stage and cp.version == aa.version for cp in record.approved_checkpoints):
        print_and_exit(
            format_error(
                f"Stage {stage.value!r} v{aa.version} already has an approved checkpoint",
                exit_code=EXIT_CONFLICT,
            ),
            EXIT_CONFLICT,
        )

    reviews_dir = run_dir / "reviews"
    # Precondition: checkpoint-review marker for this version must exist (GR5).
    marker = reviews_dir / f"{stage.value}-checkpoint-review-v{aa.version}.md"
    if not marker.exists():
        print_and_exit(
            format_error(
                f"Missing checkpoint-review marker for {stage.value} v{aa.version}; "
                "run review-checkpoint first",
                exit_code=EXIT_REVIEW_REQ,
            ),
            EXIT_REVIEW_REQ,
        )

    # Forced-review guard (version-aware; subagent file required).
    review_result = check_forced_subagent_review(stage, record.tier_locked, reviews_dir, aa.version)
    if not review_result.passed:
        print_and_exit(
            format_gate_result(review_result, gate_type="subagent-review"),
            EXIT_REVIEW_REQ,
        )

    from tools.workflow_cli.models import NEXT_STAGE_MAP
    from tools.workflow_cli.state import add_checkpoint
    next_stage = NEXT_STAGE_MAP.get(stage)
    downstream = next_stage.value if next_stage else "close_workflow_run"
    artifact_file = STAGE_ARTIFACT_MAP[stage]
    add_checkpoint(record, stage, artifact_file, aa.version, downstream)
    upsert_active_artifact(record, stage, artifact_file, aa.version, "approved")
    record = update_run_status(record, RunStatus.CHECKPOINT_APPROVED)
    update_resume_context(
        record,
        last_operation=f"approved_{stage.value}",
        next_operation="stage_advance" if next_stage else "run_close",
        active_item=stage.value,
    )
    mgr.save(record)
    print_and_exit(
        format_success(
            {"work_id": str(record.work_id), "stage": stage.value, "decision": "approved"},
            message=f"Checkpoint approved: {stage.value}",
        ),
        EXIT_OK,
    )
```

Add `add_checkpoint` to the `from tools.workflow_cli.state import (...)` block at the top of `cli.py` if not already imported (it is defined in `state.py`).

- [ ] **Step 4: Register the command**

In `_register_checkpoint_commands`, add:

```python
    p = subparsers.add_parser("checkpoint-decide", help="Approve or request changes on a checkpoint")
    p.add_argument("--work-id", required=True)
    p.add_argument("--stage", required=True)
    p.add_argument("--decision", required=True, choices=["approved", "changes_requested"])
    p.add_argument("--confirm", action="store_true")
    p.add_argument("--downstream-authorization", default=None)
    p.set_defaults(func=_cmd_checkpoint_decide)
```

- [ ] **Step 5: Run to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_cli.py::TestCheckpointDecide -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add tools/workflow_cli/cli.py tests/test_cli.py
git commit -m "feat(cli): add checkpoint-decide (approve/changes) with marker+forced-review guards"
```

### Task 10: Add `stage-advance` command

**Files:**
- Modify: `tools/workflow_cli/cli.py` (new handler + register)
- Test: `tests/test_cli.py`

- [ ] **Step 1: Write the failing test**

```python
class TestStageAdvance:
    def _to_approved(self, tmp, work_id, stage="raw_requirement"):
        invoke(["run-start", "--work-id", work_id, "--requirement", "foo"], base_path=tmp)
        invoke(["tier-lock", "--work-id", work_id, "--base", "light", "--confirm"], base_path=tmp)
        invoke(["stage-produce", "--work-id", work_id, "--stage", stage, "--content", "real"], base_path=tmp)
        invoke(["stage-ready", "--work-id", work_id, "--stage", stage], base_path=tmp)
        invoke(["gate-quality", "--work-id", work_id, "--stage", stage], base_path=tmp)
        invoke(["review-checkpoint", "--work-id", work_id, "--stage", stage], base_path=tmp)
        invoke(["checkpoint-decide", "--work-id", work_id, "--stage", stage,
                "--decision", "approved", "--confirm"], base_path=tmp)

    def test_advance_moves_to_next_stage(self):
        with tempfile.TemporaryDirectory() as tmp:
            work_id = "WF-20260527-sa"
            self._to_approved(tmp, work_id)
            invoke(["stage-advance", "--work-id", work_id], base_path=tmp)
            record = load_record(tmp, work_id)
            assert record.status == RunStatus.NEXT_STAGE
            assert record.current_stage == Stage.REQUIREMENT_BRIEF

    def test_advance_refused_without_matching_checkpoint(self):
        with tempfile.TemporaryDirectory() as tmp:
            work_id = "WF-20260527-sa2"
            invoke(["run-start", "--work-id", work_id, "--requirement", "foo"], base_path=tmp)
            record = load_record(tmp, work_id)
            record.status = RunStatus.CHECKPOINT_APPROVED  # hand-edited, no checkpoint row
            save_record(tmp, record)
            invoke(["stage-advance", "--work-id", work_id], base_path=tmp, expect_exit=6)

    def test_advance_refused_at_plan(self):
        with tempfile.TemporaryDirectory() as tmp:
            work_id = "WF-20260527-sa3"
            invoke(["run-start", "--work-id", work_id, "--requirement", "foo"], base_path=tmp)
            record = load_record(tmp, work_id)
            record.status = RunStatus.CHECKPOINT_APPROVED
            record.current_stage = Stage.PLAN
            record.approved_checkpoints = [plan_checkpoint()]
            from tools.workflow_cli.models import ActiveArtifact
            record.active_artifacts = [ActiveArtifact(
                stage=Stage.PLAN, artifact="07-plan.md", version=1, status="approved")]
            save_record(tmp, record)
            invoke(["stage-advance", "--work-id", work_id], base_path=tmp, expect_exit=6)
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_cli.py::TestStageAdvance -v`
Expected: FAIL — `invalid choice: 'stage-advance'`.

- [ ] **Step 3: Implement the handler**

```python
def _cmd_stage_advance(args):
    record, mgr, run_dir = _load_run(args.work_id, args.base_path)

    if record.status != RunStatus.CHECKPOINT_APPROVED:
        print_and_exit(
            format_error(
                f"Cannot advance in status {record.status.value!r}; must be checkpoint_approved",
                exit_code=EXIT_CONFLICT,
            ),
            EXIT_CONFLICT,
        )

    stage = record.current_stage
    if stage == Stage.PLAN:
        print_and_exit(
            format_error(
                "Cannot advance past plan; use run-close",
                exit_code=EXIT_CONFLICT,
            ),
            EXIT_CONFLICT,
        )

    from tools.workflow_cli.state import get_active_artifact
    aa = get_active_artifact(record, stage)
    if aa is None or not any(
        cp.stage == stage and cp.version == aa.version for cp in record.approved_checkpoints
    ):
        print_and_exit(
            format_error(
                f"No approved checkpoint matching {stage.value} v{aa.version if aa else '?'}",
                exit_code=EXIT_CONFLICT,
            ),
            EXIT_CONFLICT,
        )

    from tools.workflow_cli.models import NEXT_STAGE_MAP
    next_stage = NEXT_STAGE_MAP[stage]
    record = update_run_status(record, RunStatus.NEXT_STAGE)
    record.current_stage = next_stage
    update_resume_context(
        record,
        last_operation=f"advance_to_{next_stage.value}",
        next_operation="gate_entry",
        active_item=next_stage.value,
    )
    mgr.save(record)
    print_and_exit(
        format_success(
            {"work_id": str(record.work_id), "current_stage": next_stage.value},
            message=f"Advanced to {next_stage.value}",
        ),
        EXIT_OK,
    )
```

- [ ] **Step 4: Register the command**

In `_register_checkpoint_commands`, add:

```python
    p = subparsers.add_parser("stage-advance", help="Advance an approved stage to the next stage")
    p.add_argument("--work-id", required=True)
    p.set_defaults(func=_cmd_stage_advance)
```

- [ ] **Step 5: Run to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_cli.py::TestStageAdvance -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add tools/workflow_cli/cli.py tests/test_cli.py
git commit -m "feat(cli): add stage-advance (checkpoint_approved -> next_stage)"
```

### Task 11: Model + test_models for the new command intents

**Files:**
- Modify: `tools/workflow_cli/models.py` (`ALLOWED_COMMANDS_BY_RUN_STATE`)
- Test: `tests/test_models.py`

- [ ] **Step 1: Write the failing test**

```python
def test_new_command_intents_allowed_states():
    from tools.workflow_cli.models import is_command_allowed, RunStatus
    assert is_command_allowed(RunStatus.READY_FOR_CHECKPOINT_REVIEW, "CMD-REVIEW-CHECKPOINT")
    assert is_command_allowed(RunStatus.CHECKPOINT_REVIEW, "CMD-CHECKPOINT-DECIDE")
    assert is_command_allowed(RunStatus.CHECKPOINT_APPROVED, "CMD-STAGE-ADVANCE")
    assert not is_command_allowed(RunStatus.ACTIVE_STAGE_DRAFT, "CMD-STAGE-ADVANCE")
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_models.py::test_new_command_intents_allowed_states -v`
Expected: FAIL.

- [ ] **Step 3: Add the intents to the matrix**

In `models.py` `ALLOWED_COMMANDS_BY_RUN_STATE`:
- Under `RunStatus.READY_FOR_CHECKPOINT_REVIEW`, add `"CMD-REVIEW-CHECKPOINT",`
- Under `RunStatus.CHECKPOINT_REVIEW`, add `"CMD-CHECKPOINT-DECIDE",`
- Under `RunStatus.CHECKPOINT_APPROVED`, add `"CMD-STAGE-ADVANCE",`

- [ ] **Step 4: Run to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_models.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tools/workflow_cli/models.py tests/test_models.py
git commit -m "feat(models): allow review-checkpoint/checkpoint-decide/stage-advance intents"
```

---

## Group 1c — Driver + end-to-end

### Task 12: Rewrite `r2p-continue` as a status-dispatch driver

**Files:**
- Modify: `tools/workflow_cli/agent_shortcuts.py` (`_cmd_continue` ~99-134)
- Test: `tests/test_agent_shortcuts.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_agent_shortcuts.py` (match its existing `_invoke`/base_path helpers):

```python
class TestContinueDriver:
    def test_continue_stops_at_unready_artifact(self, capsys):
        import tempfile
        from pathlib import Path
        from tools.workflow_cli import agent_shortcuts as A
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            A.main(["start", "Add rate limiting"], base_path=base)
            # after start: ACTIVE_STAGE_DRAFT, raw_requirement artifact is draft (not ready)
            with pytest.raises(SystemExit):
                A.main(["continue"], base_path=base)
            out = capsys.readouterr().out
            assert "stage-ready" in out
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_agent_shortcuts.py::TestContinueDriver -v`
Expected: FAIL — current `_cmd_continue` only calls `run-resume` and prints resume context, never mentions `stage-ready`.

- [ ] **Step 3: Rewrite `_cmd_continue`**

Replace `_cmd_continue` in `agent_shortcuts.py` with a status dispatcher. It loads the record, then acts per status, using `_run_cli([...], base_path)` for CLI calls:

```python
def _cmd_continue(ns: argparse.Namespace, base_path: Path) -> None:
    pointer = read_active_pointer(base_path)
    if not pointer:
        print("no_selected_run: true\nnext: r2p-status --all\n")
        sys.exit(1)
    work_id = pointer["selected_work_id"]
    run_path = base_path / ".req-to-plan" / work_id / "run.md"
    if not run_path.exists():
        print(f"blocked: source_run_not_found\nwork_id: {work_id}\n")
        sys.exit(7)

    from tools.workflow_cli.state import RunStateManager, get_active_artifact
    from tools.workflow_cli.models import RunStatus, Stage
    record = RunStateManager(run_path.parent).load()
    s = record.status
    stage = record.current_stage.value

    if s == RunStatus.CLOSED_AT_PLAN_CHECKPOINT:
        print(f"done: run_closed\nwork_id: {work_id}\nplan: 07-plan.md\n"
              "next: hand the PLAN to your executor\n")
        sys.exit(0)

    if s == RunStatus.ACTIVE_STAGE_DRAFT:
        if record.tier_locked is None:
            print(f"stop: tier_not_locked\nnext: r2p tier-lock\n")
            sys.exit(0)
        aa = get_active_artifact(record, record.current_stage)
        if aa is None or aa.status != "ready":
            print(f"stop: needs_ready\nstage: {stage}\n"
                  f"next: review the artifact, then stage-ready --stage {stage}\n")
            sys.exit(0)
        code = _run_cli(["gate-quality", "--work-id", work_id, "--stage", stage], base_path)
        sys.exit(code)

    if s == RunStatus.READY_FOR_CHECKPOINT_REVIEW:
        _run_cli(["review-checkpoint", "--work-id", work_id, "--stage", stage], base_path)
        print(f"stop: needs_human_approval\nstage: {stage}\n"
              f"next: checkpoint-decide --stage {stage} --decision approved --confirm "
              "(or --decision changes_requested)\n")
        sys.exit(0)

    if s == RunStatus.CHECKPOINT_REVIEW:
        print(f"stop: needs_human_approval\nstage: {stage}\n"
              f"next: checkpoint-decide --stage {stage} --decision approved --confirm\n")
        sys.exit(0)

    if s == RunStatus.CHECKPOINT_APPROVED:
        if record.current_stage == Stage.PLAN:
            code = _run_cli(["run-close", "--work-id", work_id], base_path)
            print("done: closing\nplan: 07-plan.md\nnext: hand the PLAN to your executor\n")
            sys.exit(code)
        _run_cli(["stage-advance", "--work-id", work_id], base_path)
        sys.exit(0)

    if s == RunStatus.NEXT_STAGE:
        code = _run_cli(["gate-entry", "--work-id", work_id, "--stage", record.current_stage.value], base_path)
        print(f"stop: entered_stage\nstage: {record.current_stage.value}\n"
              f"next: produce {record.current_stage.value} content\n")
        sys.exit(0)

    if s in (RunStatus.ENTRY_GATE_FAILED, RunStatus.QUALITY_GATE_FAILED,
             RunStatus.CHECKPOINT_CHANGES_REQUESTED):
        print(f"stop: needs_repair\nstatus: {s.value}\nstage: {stage}\n"
              f"next: address the issue, then stage-update --stage {stage}\n")
        sys.exit(0)

    # Fallback: read-only resume context.
    code = _run_cli(["run-resume", "--work-id", work_id], base_path)
    sys.exit(code)
```

Ensure `argparse`, `sys`, `Path`, `read_active_pointer`, `_run_cli` are already imported (they are).

- [ ] **Step 4: Run to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_agent_shortcuts.py -v`
Expected: PASS. Fix any pre-existing continue test that assumed the old read-only behavior (update its assertion to the new stop/advance output).

- [ ] **Step 5: Commit**

```bash
git add tools/workflow_cli/agent_shortcuts.py tests/test_agent_shortcuts.py
git commit -m "feat(shortcuts): r2p-continue drives the workflow via status dispatch"
```

### Task 13: True end-to-end test (run-start → CLOSED via CLI)

**Files:**
- Test: `tests/test_integration.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_integration.py` a helper that drives one non-forced stage and the full pipeline:

```python
class TestEndToEndPipeline:
    def _drive_stage(self, invoke, tmp, work_id, stage, content):
        invoke(["stage-produce", "--work-id", work_id, "--stage", stage, "--content", content], base_path=tmp)
        invoke(["stage-ready", "--work-id", work_id, "--stage", stage], base_path=tmp)
        invoke(["gate-quality", "--work-id", work_id, "--stage", stage], base_path=tmp)
        invoke(["review-checkpoint", "--work-id", work_id, "--stage", stage], base_path=tmp)
        invoke(["checkpoint-decide", "--work-id", work_id, "--stage", stage,
                "--decision", "approved", "--confirm"], base_path=tmp)

    def test_full_pipeline_to_closed(self):
        import tempfile
        from pathlib import Path
        from tests.test_cli import invoke, load_record
        from tools.workflow_cli.models import RunStatus, Stage
        stages = ["raw_requirement", "requirement_brief", "risk_discovery", "design", "spec", "plan"]
        with tempfile.TemporaryDirectory() as tmp:
            work_id = "WF-20260527-e2e"
            invoke(["run-start", "--work-id", work_id, "--requirement", "Add a small feature"], base_path=tmp)
            invoke(["tier-lock", "--work-id", work_id, "--base", "light", "--confirm"], base_path=tmp)
            for i, stage in enumerate(stages):
                self._drive_stage(invoke, tmp, work_id, stage, f"content for {stage}")
                if stage != "plan":
                    invoke(["stage-advance", "--work-id", work_id], base_path=tmp)
                    invoke(["gate-entry", "--work-id", work_id, "--stage", stages[i + 1]], base_path=tmp)
            invoke(["run-close", "--work-id", work_id], base_path=tmp)
            record = load_record(tmp, work_id)
            assert record.status == RunStatus.CLOSED_AT_PLAN_CHECKPOINT
            assert any(cp.stage == Stage.PLAN for cp in record.approved_checkpoints)
```

- [ ] **Step 2: Run to verify it fails (or surfaces gaps)**

Run: `.venv/bin/python -m pytest tests/test_integration.py::TestEndToEndPipeline -v`
Expected: initially FAIL until Tasks 1–11 are all in; this is the integration guard that proves the loop closes. If a stage's quality gate fails on trivial content, adjust the content to satisfy the structural checks (non-empty; no unclosed upstream IDs). Light tier keeps structural checks minimal.

- [ ] **Step 3: Make it pass**

No new production code should be required — if it fails, the failure points at a real wiring gap in Tasks 1–11; fix there, not here. Re-run until green.

- [ ] **Step 4: Commit**

```bash
git add tests/test_integration.py
git commit -m "test(integration): full run-start -> CLOSED pipeline via CLI"
```

### Task 14: Docs + agent templates sync

**Files:**
- Modify: `docs/workflow-cli-adapter.md`, `docs/workflow-operator-runbook.md`, `docs/workflow-command-surface.md`, `docs/workflow-invariants.md`
- Modify: `tools/workflow_cli/agent_templates/claude/SKILL.md`, `tools/workflow_cli/agent_templates/claude/commands/r2p-continue.md`
- Modify: `CLAUDE.md`, `.claude/skills/req-to-plan.md` (test baseline)

- [ ] **Step 1: Update command-surface + cli-adapter**

In `docs/workflow-command-surface.md`: add a `CMD-STAGE-ADVANCE` row; reconcile the `checkpoint_approved` row so advance (move to next stage draft) vs resume (read-only) is unambiguous. In `docs/workflow-cli-adapter.md`: add a `workflow stage-advance` row; mark `review-checkpoint`/`checkpoint-decide` implemented with the MVP-marker note.

- [ ] **Step 2: Update invariants forced-review rule**

In `docs/workflow-invariants.md` Forced Subagent Review Rule (~:215): change the satisfying file from "`…-checkpoint-review-*.md` or `…-subagent-review-*.md`" to **only** a version-matched `…-subagent-review-v<version>.md`, and note the checkpoint-review marker is a separate, always-required precondition.

- [ ] **Step 3: Update operator runbook + SKILL + continue command doc**

Add the happy-path steps (review-checkpoint → checkpoint-decide → stage-advance → gate-entry) to `docs/workflow-operator-runbook.md`. Update `SKILL.md` and `commands/r2p-continue.md` to describe r2p-continue's real behavior (stop-at-ready, auto-gate, stop-at-approval, auto-advance).

- [ ] **Step 4: Update test baseline numbers**

Run: `.venv/bin/python -m pytest tests/ --co -q | tail -1`
Put the real collected number into `CLAUDE.md` ("Baseline: N tests passing") and `.claude/skills/req-to-plan.md` ("Test count baseline: N passing").

- [ ] **Step 5: Full suite green**

Run: `.venv/bin/python -m pytest tests/ -v`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add docs tools/workflow_cli/agent_templates CLAUDE.md .claude/skills/req-to-plan.md
git commit -m "docs: sync command surface, invariants, runbook, and test baseline for Part 1"
```

---

## Self-Review

**Spec coverage (Part 1 of the design doc):**
- New commands review-checkpoint / checkpoint-decide / stage-advance → Tasks 8/9/10 ✓
- Shared precondition checks (stage==current, ready, version match, dup-approval, missing-checkpoint advance) → Tasks 9/10 ✓
- Forced-review guard moved to checkpoint-decide, version-aware, subagent-file-required → Tasks 7/9 ✓
- Marker required for every approve (GR5) → Task 9 ✓
- gate-quality requires ready (NR2) → Task 3 ✓
- gate-entry persists in NEXT_STAGE + ENTRY_GATE_FAILED (TR1/QR1) → Task 4 ✓
- NEXT_STAGE produce guard + matrix removal (FR2/QR4) → Task 5 ✓
- TR3 migrate 4 direct writes → Task 1 ✓
- Repair loops CHANGES_REQUESTED + QUALITY_GATE_FAILED (R5/FR1) → Task 2 ✓
- CMD-RUN-RESUME read-only + CMD-STAGE-UPDATE in QUALITY_GATE_FAILED (GR2) → Tasks 6/2 ✓
- model intents (1.5a) → Task 11 ✓
- r2p-continue driver, corrected ready→gate order (R3) → Task 12 ✓
- end-to-end test → Task 13 ✓
- docs/invariants/baseline sync (GR1/GR3) → Task 14 ✓

**Placeholder scan:** every code step has concrete code; commands have expected output. No TBD/TODO.

**Type consistency:** `check_forced_subagent_review(stage, tier, reviews_dir, version)` used consistently in Tasks 7 and 9; `get_active_artifact`, `add_checkpoint`, `NEXT_STAGE_MAP`, `STAGE_ARTIFACT_MAP`, `update_run_status` are existing symbols; new commands registered in `_register_checkpoint_commands`.

**Known follow-ups (other plans):** Part 2 (remove adapter) and Part 3 (PLAN generation optimization) are separate executable plans, written next.

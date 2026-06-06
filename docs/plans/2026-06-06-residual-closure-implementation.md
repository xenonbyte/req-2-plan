# Residual Closure (R14–R17) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement R14–R17 from `docs/requirements/2026-06-06-residual-closure.md` — a trace symmetry fix, tier-escalation revert generalization + advisory note, two Context Pack fixes, and Decision Requests user docs.

**Architecture:** Four independent, small changes to the existing `tools/workflow_cli` package: one line in `trace.py` reusing an existing helper (R14), one condition generalization + one conditional output field in `cli.py` (R15), ~6 lines in `context_pack.py` (R17), and doc-only edits (R16). No new modules, no new state machine paths, no new dependencies.

**Tech Stack:** Python 3.10 (stdlib only), pytest via `.venv/bin/python -m pytest` (never bare `pytest` — system Python lacks PyYAML).

**Authoritative spec:** `docs/requirements/2026-06-06-residual-closure.md` (local-only, gitignored).

**Branch:** All work happens on `chore/optimize-residual` (already created and checked out). Verify with `git branch --show-current` before starting.

**Baseline:** `.venv/bin/python -m pytest tests/ -q` → 826 passed, 6 subtests passed (verified 2026-06-06 on main `772dba0`). All commits must keep the suite green. Do not pin exact test counts anywhere (project rule R6).

**Working directory:** `/Users/xubo/x-skills/req-to-plan` (repo root). All paths below are relative to it.

---

## File Structure

| File | Change | Tasks |
|---|---|---|
| `tools/workflow_cli/trace.py` | Modify `scope_in_not_closed()` (1 line + docstring) | Task 1 |
| `tests/test_trace.py` | Add 2 tests to `TestTrace` class | Task 1 |
| `tools/workflow_cli/cli.py` | Modify `_cmd_tier_escalate()` (generalize revert; add note field) | Tasks 2, 3 |
| `tests/test_cli.py` | Add new test class `TestTierEscalationInvalidatesEarlierStageGates` | Tasks 2, 3 |
| `tools/workflow_cli/context_pack.py` | Modify npm branch of `build_context_pack()` | Task 4 |
| `tests/test_context_pack.py` | Update fixture + 1 assertion, add 2 tests | Task 4 |
| `README.md`, `README.zh-CN.md` | Add one blockquote paragraph each (no new headings) | Task 5 |
| `tools/workflow_cli/agent_templates/claude/SKILL.md` | Add one bullet line | Task 5 |

Key existing code the tasks build on (verified at `main 772dba0`):
- `trace.py:148-162` `scope_in_not_closed()` — checks consumed SPEC blocks with raw `id_ in spec_blocks.get(spec_id, "")`.
- `trace.py:206-245` `_strip_nested_non_goals(block)` — already used by `scope_out_violations()` at `trace.py:262`. Defined *after* `scope_in_not_closed` in the file; Python resolves module-level names at call time, so calling it from `scope_in_not_closed` needs **no reordering**.
- `cli.py:756-836` `_cmd_tier_escalate()` — the revert special-case at lines 793-810 currently requires `record.current_stage == Stage.PLAN`.
- `cli.py:15-25` — `STAGE_ORDER`, `Stage`, `RunStatus`, `TierBase` are already imported; no import changes needed.
- `models.py:348-357` `TierEstimate.escalate()` — only `scope_expanding` flips base to standard.
- `context_pack.py:35-46` — npm branch; stores `scripts.test` body in `test_commands`, reads only `dependencies`.
- `gates.py:196-245` — SPEC's `## External Documentation Checked` section needs one valid inventory row; the literal line `N/A — no external dependencies` satisfies it.
- `tests/test_cli.py:32-51` — `invoke(args, base_path, expect_exit)`, `load_record`, `save_record` helpers; pytest-style classes; `capsys` used for output assertions (see `test_cli.py:308`).
- `tests/test_cli.py:1563-1657` — `TestTierEscalationInvalidatesPlanGate` with `_ready_plan_under_light_tier` helper: the existing PLAN revert tests, which serve as regression coverage for Task 2.
- `tests/test_readme.py:36` — README.md and README.zh-CN.md must have **identical heading sequences**; Task 5 therefore adds no new headings.

---

### Task 1: R14 — `scope_in_not_closed()` strips nested Non-goals

A SCOPE-IN id that appears **only** inside a `Non-goals` subsection of a consumed SPEC block must NOT count as closed (the SPEC explicitly says it is not implemented there).

**Files:**
- Modify: `tools/workflow_cli/trace.py:148-162`
- Test: `tests/test_trace.py` (add to `TestTrace` class, after `test_scope_ref_after_consumed_spec_block_does_not_close_scope` at line 148-165)

- [ ] **Step 1: Write the two failing/guard tests**

Add to the `TestTrace` class in `tests/test_trace.py` (unittest style, mirroring `test_scope_in_carried_into_consumed_spec_closes` at line 112):

```python
    def test_scope_in_only_in_consumed_spec_non_goals_is_a_gap(self):
        """R14 red-team: a SPEC that says 'SCOPE-IN-001 is NOT implemented here'
        in its nested Non-goals must not close that scope item."""
        from tools.workflow_cli.trace import check_trace_closure
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            (run_dir / STAGE_ARTIFACT_MAP[Stage.REQUIREMENT_BRIEF]).write_text(
                "## In-Scope\n- SCOPE-IN-001 export audit logs\n", encoding="utf-8")
            (run_dir / STAGE_ARTIFACT_MAP[Stage.SPEC]).write_text(
                (
                    "## SPEC-AUDIT-001 audit behavior\n"
                    "No scope reference in the contract body.\n\n"
                    "### Non-goals\n"
                    "- SCOPE-IN-001 is not implemented here\n"
                ),
                encoding="utf-8",
            )
            (run_dir / STAGE_ARTIFACT_MAP[Stage.PLAN]).write_text(
                "## Tasks\n### PLAN-TASK-001\nSpec References: SPEC-AUDIT-001\n",
                encoding="utf-8")
            self.assertTrue(any("SCOPE-IN-001" in i for i in check_trace_closure(run_dir)))

    def test_scope_in_in_sibling_section_after_non_goals_still_closes(self):
        """R14 guard: the Non-goals strip must end at the next same-or-higher
        heading; a sibling subsection carrying the SCOPE-IN still closes it."""
        from tools.workflow_cli.trace import check_trace_closure
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            (run_dir / STAGE_ARTIFACT_MAP[Stage.REQUIREMENT_BRIEF]).write_text(
                "## In-Scope\n- SCOPE-IN-001 export audit logs\n", encoding="utf-8")
            (run_dir / STAGE_ARTIFACT_MAP[Stage.SPEC]).write_text(
                (
                    "## SPEC-AUDIT-001 audit behavior\n"
                    "### Non-goals\n"
                    "- other exclusions\n\n"
                    "### Implementation notes\n"
                    "implements SCOPE-IN-001\n"
                ),
                encoding="utf-8",
            )
            (run_dir / STAGE_ARTIFACT_MAP[Stage.PLAN]).write_text(
                "## Tasks\n### PLAN-TASK-001\nSpec References: SPEC-AUDIT-001\n",
                encoding="utf-8")
            self.assertFalse(any("SCOPE-IN-001" in i for i in check_trace_closure(run_dir)))
```

- [ ] **Step 2: Run new tests, verify red/green split**

Run: `.venv/bin/python -m pytest tests/test_trace.py -k "non_goals_is_a_gap or sibling_section_after_non_goals" -v`
Expected: `test_scope_in_only_in_consumed_spec_non_goals_is_a_gap` **FAILS** (assertTrue on empty issues — current code treats the Non-goals mention as closing). `test_scope_in_in_sibling_section_after_non_goals_still_closes` **PASSES** (guard for current behavior that must survive the fix).

- [ ] **Step 3: Apply the one-line fix**

In `tools/workflow_cli/trace.py`, change `scope_in_not_closed()`:

```python
def scope_in_not_closed(run_dir: Path) -> list[str]:
    """SCOPE-IN closes only when a PLAN-TASK carries it or consumes a SPEC
    carrying it outside the SPEC block's nested Non-goals subsections (R14:
    'explicitly not implemented here' must not close the scope item)."""
    model = build_trace(run_dir)
    plan_text = _artifact_text(run_dir, Stage.PLAN)
    plan_task_text = "\n".join(unfenced_markdown_text(body) for body in _plan_task_bodies(plan_text))
    spec_blocks = _spec_blocks(_artifact_text(run_dir, Stage.SPEC))
    consumed_specs = plan_consumed_spec_ids(run_dir)
    issues: list[str] = []
    for id_ in sorted(i for i in model.defined if i.startswith("SCOPE-IN-")):
        if id_ in plan_task_text:
            continue
        if any(id_ in _strip_nested_non_goals(spec_blocks.get(spec_id, ""))
               for spec_id in consumed_specs):
            continue
        issues.append(id_)
    return issues
```

(The only functional change is wrapping `spec_blocks.get(spec_id, "")` with `_strip_nested_non_goals(...)` plus the docstring. Do NOT modify `_strip_nested_non_goals` itself.)

- [ ] **Step 4: Run the full trace test module**

Run: `.venv/bin/python -m pytest tests/test_trace.py -v`
Expected: ALL PASS, including the prior R9 fixtures (`test_scope_out_*`) and the existing scope-in regressions (`test_scope_in_carried_into_consumed_spec_closes`, `test_scope_ref_after_consumed_spec_block_does_not_close_scope`).

- [ ] **Step 5: Run the full suite**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: all pass (R14 tightens closure; no shipped fixture relies on Non-goals-only closure — if anything fails here, read the failure: it means an integration fixture closes a SCOPE-IN via Non-goals text and that fixture must be corrected to carry the id in the SPEC body, not the check weakened).

- [ ] **Step 6: Commit**

```bash
git add tools/workflow_cli/trace.py tests/test_trace.py
git commit -m "fix(r2p): scope_in_not_closed ignores nested Non-goals in consumed SPECs (R14)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 2: R15a — generalize the escalation revert beyond PLAN

When a light→standard escalation happens while the **current stage's** gate has passed but the checkpoint is not yet approved (`READY_FOR_CHECKPOINT_REVIEW` / `CHECKPOINT_REVIEW`), revert to `ACTIVE_STAGE_DRAFT` for **any** stage, not just PLAN.

**Files:**
- Modify: `tools/workflow_cli/cli.py:793-810` (inside `_cmd_tier_escalate`)
- Test: `tests/test_cli.py` (new class, place directly after `TestTierEscalationInvalidatesPlanGate` which ends at line 1657)

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_cli.py` after the `TestTierEscalationInvalidatesPlanGate` class (pytest style; `invoke`/`load_record`/`save_record` are module-level helpers already imported at the top of the file; `Stage`, `RunStatus` are already imported there too — check the file's import block and reuse):

```python
class TestTierEscalationInvalidatesEarlierStageGates:
    """R15a: the light->standard revert must cover DESIGN/SPEC, not only PLAN."""

    _DESIGN_BODY = (
        "---\nr2p_version: 1\n---\n# DESIGN\n\n"
        "## Design Summary\nsummary text\n\n"
        "## Chosen Design\n### DES-ARCH-001 chosen approach\ndetails\n\n"
        "## SPEC Handoff\nhandoff notes\n"
    )
    _SPEC_BODY = (
        "---\nr2p_version: 1\n---\n# SPEC\n\n"
        "## Behavior Contracts\n### SPEC-AUTH-001 login behavior\ncontract text\n\n"
        "## External Documentation Checked\nN/A — no external dependencies\n\n"
        "## PLAN Handoff\nhandoff notes\n"
    )
    _PLAN_BODY = (
        "---\nr2p_version: 1\n---\n# PLAN\n\n"
        "## Tasks\n\nProse-only plan.\n"
    )

    def _ready_stage_under_light_tier(self, tmp, work_id, stage, artifact, body):
        from tools.workflow_cli.models import ActiveArtifact

        invoke(["run-start", "--work-id", work_id, "--requirement", "foo"], base_path=tmp)
        invoke(["tier-lock", "--work-id", work_id, "--base", "light", "--confirm"], base_path=tmp)
        record = load_record(tmp, work_id)
        record.current_stage = stage
        record.status = RunStatus.ACTIVE_STAGE_DRAFT
        record.active_artifacts = [
            ActiveArtifact(stage=stage, artifact=artifact, version=1, status="ready")
        ]
        save_record(tmp, record)
        run_dir = Path(tmp) / ".req-to-plan" / work_id
        (run_dir / artifact).write_text(body, encoding="utf-8")
        invoke(["gate-quality", "--work-id", work_id, "--stage", stage.value], base_path=tmp)
        record = load_record(tmp, work_id)
        assert record.status == RunStatus.READY_FOR_CHECKPOINT_REVIEW, (
            f"fixture must pass the light {stage.value} quality gate first"
        )

    def test_scope_expanding_escalation_invalidates_ready_design_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            work_id = "WF-20260606-dgready"
            self._ready_stage_under_light_tier(
                tmp, work_id, Stage.DESIGN, "05-design.md", self._DESIGN_BODY)

            invoke(["tier-escalate", "--work-id", work_id, "--modifier", "scope_expanding"], base_path=tmp)

            record = load_record(tmp, work_id)
            assert record.status == RunStatus.ACTIVE_STAGE_DRAFT
            assert record.tier_locked.base.value == "standard"
            assert record.resume_context.active_item == "design"
            invoke(["gate-quality", "--work-id", work_id, "--stage", "design"], base_path=tmp, expect_exit=3)

    def test_scope_expanding_escalation_invalidates_open_design_review(self):
        with tempfile.TemporaryDirectory() as tmp:
            work_id = "WF-20260606-dgreview"
            self._ready_stage_under_light_tier(
                tmp, work_id, Stage.DESIGN, "05-design.md", self._DESIGN_BODY)
            invoke(["review-checkpoint", "--work-id", work_id, "--stage", "design"], base_path=tmp)

            invoke(["tier-escalate", "--work-id", work_id, "--modifier", "scope_expanding"], base_path=tmp)

            record = load_record(tmp, work_id)
            assert record.status == RunStatus.ACTIVE_STAGE_DRAFT
            invoke(["gate-quality", "--work-id", work_id, "--stage", "design"], base_path=tmp, expect_exit=3)

    def test_scope_expanding_escalation_invalidates_ready_spec_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            work_id = "WF-20260606-sgready"
            self._ready_stage_under_light_tier(
                tmp, work_id, Stage.SPEC, "06-spec.md", self._SPEC_BODY)

            invoke(["tier-escalate", "--work-id", work_id, "--modifier", "scope_expanding"], base_path=tmp)

            record = load_record(tmp, work_id)
            assert record.status == RunStatus.ACTIVE_STAGE_DRAFT
            assert record.tier_locked.base.value == "standard"
            assert record.resume_context.active_item == "spec"
            invoke(["gate-quality", "--work-id", work_id, "--stage", "spec"], base_path=tmp, expect_exit=3)

    def test_non_base_changing_escalation_keeps_ready_design_gate(self):
        """Modifier-only escalation (base does not flip to standard) must NOT revert."""
        with tempfile.TemporaryDirectory() as tmp:
            work_id = "WF-20260606-dgdep"
            self._ready_stage_under_light_tier(
                tmp, work_id, Stage.DESIGN, "05-design.md", self._DESIGN_BODY)

            invoke(["tier-escalate", "--work-id", work_id, "--modifier", "dependency"], base_path=tmp)

            record = load_record(tmp, work_id)
            assert record.status == RunStatus.READY_FOR_CHECKPOINT_REVIEW
            assert record.tier_locked.base.value == "light"
```

Fixture-validity note for the executor: the helper self-asserts that the light gate passes (`READY_FOR_CHECKPOINT_REVIEW`). If that inner assert trips, run the gate manually (`gate-quality` without `expect_exit`) and read the printed issues — extend `_DESIGN_BODY`/`_SPEC_BODY` minimally to satisfy the named light-tier rule, never by switching tier or weakening the test.

- [ ] **Step 2: Run new tests to verify they fail for the right reason**

Run: `.venv/bin/python -m pytest tests/test_cli.py -k "TestTierEscalationInvalidatesEarlierStageGates" -v`
Expected: the three `scope_expanding` tests FAIL at `assert record.status == RunStatus.ACTIVE_STAGE_DRAFT` (status stays `READY_FOR_CHECKPOINT_REVIEW`/`CHECKPOINT_REVIEW` because current code only reverts at PLAN). `test_non_base_changing_escalation_keeps_ready_design_gate` PASSES (guard).

- [ ] **Step 3: Generalize the revert in `_cmd_tier_escalate`**

In `tools/workflow_cli/cli.py`, replace this block (currently lines 793-810):

```python
    plan_gate_passed_statuses = {
        RunStatus.READY_FOR_CHECKPOINT_REVIEW,
        RunStatus.CHECKPOINT_REVIEW,
    }
    standard_plan_gate_became_applicable = (
        record.current_stage == Stage.PLAN
        and previous_tier.base != TierBase.STANDARD
        and record.tier_locked.base == TierBase.STANDARD
        and record.status in plan_gate_passed_statuses
    )
    if standard_plan_gate_became_applicable:
        record = update_run_status(record, RunStatus.ACTIVE_STAGE_DRAFT)
        update_resume_context(
            record,
            last_operation=f"tier_escalated_{modifier.value}",
            next_operation="gate_quality",
            active_item=Stage.PLAN.value,
        )
```

with:

```python
    gate_passed_statuses = {
        RunStatus.READY_FOR_CHECKPOINT_REVIEW,
        RunStatus.CHECKPOINT_REVIEW,
    }
    standard_gate_became_applicable = (
        previous_tier.base != TierBase.STANDARD
        and record.tier_locked.base == TierBase.STANDARD
        and record.status in gate_passed_statuses
    )
    if standard_gate_became_applicable:
        record = update_run_status(record, RunStatus.ACTIVE_STAGE_DRAFT)
        update_resume_context(
            record,
            last_operation=f"tier_escalated_{modifier.value}",
            next_operation="gate_quality",
            active_item=record.current_stage.value,
        )
```

(Three changes only: drop the `record.current_stage == Stage.PLAN` conjunct, rename the two locals, and use `record.current_stage.value` as `active_item`.)

- [ ] **Step 4: Run the new class and the existing PLAN escalation regressions**

Run: `.venv/bin/python -m pytest tests/test_cli.py -k "TierEscalation" -v`
Expected: ALL PASS — the new class, plus all four existing `TestTierEscalationInvalidatesPlanGate` tests (PLAN revert at ready and at open review; refusal at `CHECKPOINT_APPROVED`; refusal on closed run).

- [ ] **Step 5: Commit**

```bash
git add tools/workflow_cli/cli.py tests/test_cli.py
git commit -m "fix(r2p): escalation to standard reverts any gate-passed stage, not only PLAN (R15a)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 3: R15b — advisory note when light DESIGN was approved before a standard escalation

When base flips to standard and the run is already **past** DESIGN, print a note pointing at `gap-open --owner-stage design`. Output-layer only; never blocks.

**Files:**
- Modify: `tools/workflow_cli/cli.py` (the `print_and_exit(format_success(...))` tail of `_cmd_tier_escalate`, currently lines 824-836)
- Test: `tests/test_cli.py` (same class as Task 2)

- [ ] **Step 1: Write the failing tests**

Add to `TestTierEscalationInvalidatesEarlierStageGates` (note `capsys.readouterr()` is called once before the escalate to discard fixture output):

```python
    def test_escalation_to_standard_past_design_prints_gap_open_note(self, capsys):
        with tempfile.TemporaryDirectory() as tmp:
            work_id = "WF-20260606-note1"
            self._ready_stage_under_light_tier(
                tmp, work_id, Stage.SPEC, "06-spec.md", self._SPEC_BODY)
            capsys.readouterr()

            invoke(["tier-escalate", "--work-id", work_id, "--modifier", "scope_expanding"], base_path=tmp)

            out = capsys.readouterr().out
            assert "gap-open --owner-stage design" in out

    def test_escalation_to_standard_at_plan_prints_gap_open_note(self, capsys):
        with tempfile.TemporaryDirectory() as tmp:
            work_id = "WF-20260606-note3"
            self._ready_stage_under_light_tier(
                tmp, work_id, Stage.PLAN, "07-plan.md", self._PLAN_BODY)
            capsys.readouterr()

            invoke(["tier-escalate", "--work-id", work_id, "--modifier", "scope_expanding"], base_path=tmp)

            out = capsys.readouterr().out
            assert "gap-open --owner-stage design" in out

    def test_escalation_to_standard_at_design_prints_no_note(self, capsys):
        with tempfile.TemporaryDirectory() as tmp:
            work_id = "WF-20260606-note2"
            self._ready_stage_under_light_tier(
                tmp, work_id, Stage.DESIGN, "05-design.md", self._DESIGN_BODY)
            capsys.readouterr()

            invoke(["tier-escalate", "--work-id", work_id, "--modifier", "scope_expanding"], base_path=tmp)

            out = capsys.readouterr().out
            assert "gap-open --owner-stage design" not in out
```

- [ ] **Step 2: Run to verify the first fails**

Run: `.venv/bin/python -m pytest tests/test_cli.py -k "prints_gap_open_note or prints_no_note" -v`
Expected: the SPEC and PLAN `..._prints_gap_open_note` tests FAIL (no note in output yet); `..._prints_no_note` PASSES (guard).

- [ ] **Step 3: Add the conditional note to the success payload**

In `tools/workflow_cli/cli.py` `_cmd_tier_escalate`, replace the final block (after the bundle-revocation code, currently lines 824-836):

```python
    mgr.save(record)
    print_and_exit(
        format_success(
            {
                "work_id": str(record.work_id),
                "tier_base": record.tier_locked.base.value,
                "modifiers": sorted(m.value for m in record.tier_locked.modifiers),
                "added_modifier": modifier.value,
            },
            message=f"Tier escalated with modifier: {modifier.value}",
        ),
        EXIT_OK,
    )
```

with:

```python
    mgr.save(record)
    data = {
        "work_id": str(record.work_id),
        "tier_base": record.tier_locked.base.value,
        "modifiers": sorted(m.value for m in record.tier_locked.modifiers),
        "added_modifier": modifier.value,
    }
    if (
        previous_tier.base != TierBase.STANDARD
        and record.tier_locked.base == TierBase.STANDARD
        and STAGE_ORDER.index(record.current_stage) > STAGE_ORDER.index(Stage.DESIGN)
    ):
        data["note"] = (
            "DESIGN was approved under light tier; if this escalation "
            "changes design decisions, run gap-open --owner-stage design"
        )
    print_and_exit(
        format_success(
            data,
            message=f"Tier escalated with modifier: {modifier.value}",
        ),
        EXIT_OK,
    )
```

(`STAGE_ORDER` and `Stage` are already imported at `cli.py:15-25`. `format_success` renders scalar payload keys as `  key: value` lines in text mode and as JSON keys in `R2P_JSON=1` mode — both carry the note.)

- [ ] **Step 4: Run the escalation tests**

Run: `.venv/bin/python -m pytest tests/test_cli.py -k "TierEscalation" -v`
Expected: ALL PASS (both note tests, all revert tests, all regressions).

- [ ] **Step 5: Commit**

```bash
git add tools/workflow_cli/cli.py tests/test_cli.py
git commit -m "feat(r2p): tier-escalate notes gap-open path when light DESIGN predates standard (R15b)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 4: R17 — Context Pack: invokable `test_commands` + devDependencies

`test_commands` must store the invokable `npm test` (not the script body); `devDependencies` must be collected with a `"dev": true` marker while existing entry keys stay unchanged.

**Files:**
- Modify: `tools/workflow_cli/context_pack.py:35-46`
- Test: `tests/test_context_pack.py`

- [ ] **Step 1: Update the fixture and assertions; add the two new tests**

In `tests/test_context_pack.py`, change `_make_repo` (line 9-16) so package.json gains devDependencies:

```python
    def _make_repo(self, tmp: Path):
        (tmp / "package.json").write_text(
            json.dumps({
                "scripts": {"test": "jest"},
                "dependencies": {"react": "^18.0.0"},
                "devDependencies": {"jest": "^29.0.0"},
            }),
            encoding="utf-8",
        )
        (tmp / "requirements.txt").write_text("pyyaml>=6.0\n# comment\n", encoding="utf-8")
        (tmp / "src").mkdir()
        (tmp / "src" / "main.py").write_text("print('hi')\n", encoding="utf-8")
```

Replace the body of `test_detects_managers_test_commands_and_deps` (line 18-29) with:

```python
    def test_detects_managers_test_commands_and_deps(self):
        from tools.workflow_cli.context_pack import build_context_pack
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            self._make_repo(tmp)
            pack = build_context_pack(tmp)
        self.assertIn("npm", pack.package_managers)
        self.assertIn("pip", pack.package_managers)
        self.assertIn("npm test", pack.test_commands)
        self.assertNotIn("jest", pack.test_commands)
        names = {d["name"] for d in pack.dependencies}
        self.assertIn("react", names)
        self.assertTrue(any(d["name"].startswith("pyyaml") for d in pack.dependencies))
```

Add two new tests to `TestBuildContextPack`:

```python
    def test_dev_dependencies_are_collected_with_dev_marker(self):
        from tools.workflow_cli.context_pack import build_context_pack
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            self._make_repo(tmp)
            pack = build_context_pack(tmp)
        jest = next(d for d in pack.dependencies if d["name"] == "jest")
        self.assertEqual(jest["ecosystem"], "npm")
        self.assertEqual(jest["version"], "^29.0.0")
        self.assertIs(jest["dev"], True)
        react = next(d for d in pack.dependencies if d["name"] == "react")
        self.assertNotIn("dev", react)  # existing entry shape unchanged

    def test_no_npm_test_script_yields_no_npm_test_command(self):
        from tools.workflow_cli.context_pack import build_context_pack
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            (tmp / "package.json").write_text(
                json.dumps({"dependencies": {"react": "^18.0.0"}}), encoding="utf-8")
            pack = build_context_pack(tmp)
        self.assertNotIn("npm test", pack.test_commands)
        self.assertIn("npm", pack.package_managers)
```

- [ ] **Step 2: Run to verify the red set**

Run: `.venv/bin/python -m pytest tests/test_context_pack.py -v`
Expected: `test_detects_managers_test_commands_and_deps` FAILS (`"npm test"` not in `test_commands` — code stores `"jest"`); `test_dev_dependencies_are_collected_with_dev_marker` FAILS (no jest entry); `test_no_npm_test_script_yields_no_npm_test_command` PASSES (guard); the writer/repo-root tests PASS.

- [ ] **Step 3: Implement in `context_pack.py`**

Replace the npm branch in `build_context_pack` (currently lines 35-46):

```python
    pkg = repo_path / "package.json"
    if pkg.exists():
        try:
            data = json.loads(pkg.read_text(encoding="utf-8"))
            pack.package_managers.append("npm")
            if (data.get("scripts") or {}).get("test"):
                pack.test_commands.append("npm test")
            for name, ver in (data.get("dependencies") or {}).items():
                pack.dependencies.append({"name": name, "version": ver, "ecosystem": "npm"})
            for name, ver in (data.get("devDependencies") or {}).items():
                pack.dependencies.append(
                    {"name": name, "version": ver, "ecosystem": "npm", "dev": True})
        except (ValueError, OSError):
            pass
```

(Leave the requirements.txt branch and everything else untouched — pip's `python -m pytest` is already invokable.)

- [ ] **Step 4: Run module then full suite**

Run: `.venv/bin/python -m pytest tests/test_context_pack.py -v`
Expected: ALL PASS.

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: all pass. If any other module fails on `test_commands` content (e.g. an agent-shortcuts or gates fixture asserting the script body), update that assertion to the invokable form `npm test` — the requirement doc (核验细节 3) records this as the intended behavior flip.

- [ ] **Step 5: Commit**

```bash
git add tools/workflow_cli/context_pack.py tests/test_context_pack.py
git commit -m "fix(r2p): context pack stores invokable npm test and collects devDependencies (R17)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 5: R16 — Decision Requests user documentation

Add 3-5 lines to README.md, README.zh-CN.md, and the claude SKILL template. **No new Markdown headings** — `tests/test_readme.py::test_heading_sequences_are_identical` enforces identical heading sequences across both READMEs; blockquotes and list items are safe.

**Files:**
- Modify: `README.md` (insert before the `## License` heading, line 177)
- Modify: `README.zh-CN.md` (insert before its `## License` heading — locate with `grep -n "^## License" README.zh-CN.md`)
- Modify: `tools/workflow_cli/agent_templates/claude/SKILL.md` (Usage Pattern, after the bullet list under item 2)

- [ ] **Step 1: Add the EN paragraph to README.md**

Insert immediately before the `## License` heading, separated by a blank line on each side:

```markdown
> [!NOTE]
> **Human decision points (standard DESIGN).** When a standard-tier DESIGN
> involves a choice a human must make (new dependency, migration strategy,
> API compatibility), the agent records it in the `## Decision Requests`
> section as a `### DECISION-NNN` block with `Question:`, `Options:`,
> `Recommended:`, and `Status: pending` — and a pending decision fails
> `gate-quality` until a human chooses and the block becomes
> `Status: selected` with `Selected:` and `Rationale:` lines.
> Write exactly `none` in that section when no human decision is needed.
```

- [ ] **Step 2: Add the zh paragraph to README.zh-CN.md**

Insert immediately before its `## License` heading:

```markdown
> [!NOTE]
> **人工决策点（standard DESIGN）。** 当 standard tier 的 DESIGN 涉及必须由人
> 决定的选择（引入新依赖、迁移策略、API 兼容性）时，agent 会在 `## Decision
> Requests` 章节写入 `### DECISION-NNN` block（含 `Question:`/`Options:`/
> `Recommended:`）并标记 `Status: pending` ——存在 pending 决策时
> `gate-quality` 会失败，直到人选定方案、block 改为 `Status: selected`
> 并补上 `Selected:` 与 `Rationale:` 行。
> 无需人工决策时，该章节须恰好写 `none`。
```

- [ ] **Step 3: Add one bullet to the claude SKILL template**

In `tools/workflow_cli/agent_templates/claude/SKILL.md`, inside Usage Pattern item 2's bullet list (after the line `   - Does NOT auto-mark artifacts ready and does NOT auto-approve checkpoints — those are human steps`), add:

```markdown
   - Standard-tier DESIGN: record any human technical choice in `## Decision Requests` as a `### DECISION-NNN` block (`Question:`/`Options:`/`Recommended:`/`Status: pending`); pending blocks `gate-quality` until a human selects (`Status: selected` + `Selected:`/`Rationale:`), or write exactly `none` when no decision is needed
```

- [ ] **Step 4: Run the README and docs-consistency guards**

Run: `.venv/bin/python -m pytest tests/test_readme.py tests/test_docs_consistency.py tests/test_install.py -v`
Expected: ALL PASS (no new headings → heading parity holds; no test counts added; install templates still render).

- [ ] **Step 5: Run the full suite**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add README.md README.zh-CN.md tools/workflow_cli/agent_templates/claude/SKILL.md
git commit -m "docs(r2p): document Decision Requests pending gate in README and claude skill (R16)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 6: Final verification sweep

**Files:** none modified.

- [ ] **Step 1: Full suite, verbose count check**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: 0 failures; total count strictly greater than the 826 baseline (new tests added; do not pin the exact number anywhere).

- [ ] **Step 2: Verify the four behaviors end-to-end via git log**

Run: `git log --oneline main..HEAD`
Expected: exactly 5 commits, one per task, in order — R14 fix (Task 1), R15a fix (Task 2), R15b feat (Task 3), R17 fix (Task 4), R16 docs (Task 5).

- [ ] **Step 3: Confirm working tree clean**

Run: `git status --short`
Expected: empty output (the requirement/plan docs under `docs/` are gitignored and never staged).

---

## Spec-coverage self-check (R14–R17 → tasks)

| Requirement | Verification item (from spec) | Covered by |
|---|---|---|
| R14 | SCOPE-IN only in Non-goals → fail | Task 1 test 1 |
| R14 | sibling section after Non-goals → pass | Task 1 test 2 |
| R14 | SPEC body carry → pass; PLAN-TASK direct → pass (regressions) | existing `test_trace.py:112-134, 86-94` (Task 1 Step 4 runs them) |
| R15 | DESIGN ready + scope_expanding → revert, `active_item == "design"` | Task 2 test 1 |
| R15 | CHECKPOINT_REVIEW also reverts | Task 2 test 2 (DESIGN) + existing PLAN test `test_cli.py:1601` |
| R15 | SPEC same-shape fixture | Task 2 test 3 |
| R15 | modifier-only (base unchanged) → no revert | Task 2 test 4 |
| R15 | PLAN existing behavior regression | existing `TestTierEscalationInvalidatesPlanGate` (Task 2 Step 4 runs them) |
| R15 | `CHECKPOINT_APPROVED` escalate still refused | existing `test_cli.py:1618` |
| R15 | SPEC + light→standard → note; PLAN + light→standard → note; DESIGN → no note | Task 3 tests 1-3 |
| R17 | `scripts.test` present → `test_commands == ["npm test"]`; existing jest assertion flipped | Task 4 Step 1 |
| R17 | no `scripts.test` → no npm entry | Task 4 new test 2 |
| R17 | devDependencies collected with `"dev": true`, existing key shape unchanged | Task 4 new test 1 |
| R17 | requirements.txt path regression | existing writer/pip assertions (Task 4 Step 4) |
| R16 | README + README.zh-CN + claude SKILL each gain the note; codex/gemini unchanged | Task 5 |
| 完成口径 | full suite green, no pinned counts | Tasks 1-6 final steps |

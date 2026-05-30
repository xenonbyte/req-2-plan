# Part 3 — PLAN Generation Optimization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the neutral PLAN directly executable — fix a machine-parseable PLAN-TASK schema, require executable code anchors (hard-fail gate at standard tier), require a SPEC `External Documentation Checked` section, and make PLAN steps checkbox-tracked.

**Architecture:** Two layers. (1) Stage-spec docs (`plan-workflow.md`, `spec-workflow.md`) define the required PLAN/SPEC structure the Agent generates. (2) `gates.py` `check_quality_gate` enforces the structure for the relevant stage only (`PLAN` for code-block presence; `SPEC` for the External-Docs section). The quality gate already receives `stage` and `tier`, so no signature change is needed.

**Tech Stack:** Python 3.10+ stdlib (`re`), Markdown stage docs. Tests run with `.venv/bin/python -m pytest`.

**Design source:** `docs/2026-05-30-workflow-fixes-and-plan-optimization.md` Part 3 (Approved). Decisions: 3.1 gate = **hard fail at standard tier** (light/N-A exempt); Context7 section = **always present** with explicit `N/A` row (presence check, not dependency-guessing).

**Pre-verified facts (2026-05-31):**
- `check_quality_gate(run_dir, stage, tier, approved_checkpoints, artifact_content)` at `gates.py:146`; `tier.base` (light/standard) is available.
- `tests/test_gates.py` uses `unittest.TestCase`.
- PLAN tasks today are narrative; the only structured fields are `Spec References` and the TDD Decomposition table.

**Run tests:** `.venv/bin/python -m pytest` (never bare `pytest`). Commit after each green task.

---

### Task 1: Define the machine-parseable PLAN-TASK schema in `plan-workflow.md`

**Files:**
- Modify: `docs/plan-workflow.md`

- [ ] **Step 1: Add the task schema section**

In `docs/plan-workflow.md`, before the TDD Decomposition section, add a "PLAN Task Schema" subsection specifying each task as:

```
### PLAN-TASK-001: <title>
Spec References: SPEC-...
Change Type: add | modify | remove
TDD Applicable: yes | no
Files: <Create/Modify + path list>
Skeleton:
  ```<lang>
  <interface signature or failing-test skeleton>
  ```
Steps:
- [ ] red: ...
- [ ] green: ...
Verification: ...
```

State the rules: task headings match `^### PLAN-TASK-\d+`; `TDD Applicable` is `yes`/`no`; a `yes` task must include at least one fenced code block under `Skeleton`; steps use `- [ ]`.

- [ ] **Step 2: Verify the doc renders and is self-consistent**

Run: `grep -n "PLAN-TASK-" docs/plan-workflow.md`
Expected: the schema heading example appears; the existing TDD Decomposition table still references task IDs consistently.

- [ ] **Step 3: Commit**

```bash
git add docs/plan-workflow.md
git commit -m "docs(plan-workflow): define machine-parseable PLAN-TASK schema"
```

### Task 2: Add the PLAN code-block gate (hard fail at standard tier)

**Files:**
- Modify: `tools/workflow_cli/gates.py` (`check_quality_gate` ~146; add a helper)
- Test: `tests/test_gates.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_gates.py`:

```python
class TestPlanCodeBlockGate(unittest.TestCase):
    def setUp(self):
        from tools.workflow_cli.gates import check_quality_gate
        from tools.workflow_cli.models import Stage, TierBase, TierEstimate
        self.check = check_quality_gate
        self.Stage = Stage
        self.standard = TierEstimate(base=TierBase.STANDARD, modifiers=frozenset())
        self.light = TierEstimate(base=TierBase.LIGHT, modifiers=frozenset())

    def _plan(self, with_code: bool) -> str:
        skeleton = "```python\ndef f():\n    ...\n```\n" if with_code else "(prose only)\n"
        return (
            "# PLAN\n\n"
            "### PLAN-TASK-001: do thing\n"
            "TDD Applicable: yes\n"
            f"Skeleton:\n{skeleton}\n"
            "Steps:\n- [ ] red\n- [ ] green\n"
        )

    def test_standard_plan_without_code_block_fails(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            r = self.check(Path(tmp), self.Stage.PLAN, self.standard, [], self._plan(False))
            self.assertFalse(r.passed)
            self.assertEqual(r.exit_code, 3)

    def test_standard_plan_with_code_block_passes_this_check(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            r = self.check(Path(tmp), self.Stage.PLAN, self.standard, [], self._plan(True))
            self.assertTrue(r.passed)

    def test_light_plan_without_code_block_exempt(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            r = self.check(Path(tmp), self.Stage.PLAN, self.light, [], self._plan(False))
            self.assertTrue(r.passed)

    def test_non_plan_stage_unaffected(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            r = self.check(Path(tmp), self.Stage.SPEC, self.standard, [], "non-empty spec body\n")
            # SPEC gate is Task 3; this check must not fire for PLAN-code on a SPEC artifact
            self.assertTrue(all("code block" not in i for i in r.issues))
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_gates.py::TestPlanCodeBlockGate -v`
Expected: `test_standard_plan_without_code_block_fails` FAILS (gate passes today).

- [ ] **Step 3: Add the helper + the gate check**

In `gates.py`, add a helper:

```python
_PLAN_TASK_RE = re.compile(r"^### PLAN-TASK-\d+", re.MULTILINE)
_TDD_YES_RE = re.compile(r"TDD Applicable:\s*yes", re.IGNORECASE)
_CODE_FENCE_RE = re.compile(r"^```", re.MULTILINE)


def _plan_tasks_missing_code(content: str) -> bool:
    """True if any PLAN-TASK with 'TDD Applicable: yes' has no fenced code block in its body."""
    starts = [m.start() for m in _PLAN_TASK_RE.finditer(content)]
    if not starts:
        return False
    bounds = starts + [len(content)]
    for i in range(len(starts)):
        body = content[bounds[i]:bounds[i + 1]]
        if _TDD_YES_RE.search(body) and not _CODE_FENCE_RE.search(body):
            return True
    return False
```

Then in `check_quality_gate`, inside the `if not issues:` block (after Check 4), add:

```python
        # Check 5 (PLAN, standard tier): TDD-applicable tasks must carry a code block.
        from tools.workflow_cli.models import TierBase
        if stage == Stage.PLAN and tier.base == TierBase.STANDARD:
            if _plan_tasks_missing_code(artifact_content):
                issues.append(
                    "PLAN has a 'TDD Applicable: yes' task with no fenced code block; "
                    "add a Skeleton code block (standard tier requires executable anchors)."
                )
```

- [ ] **Step 4: Run to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_gates.py::TestPlanCodeBlockGate -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tools/workflow_cli/gates.py tests/test_gates.py
git commit -m "feat(gates): hard-fail PLAN at standard tier when a TDD task lacks a code block"
```

### Task 3: Require a SPEC `External Documentation Checked` section

**Files:**
- Modify: `docs/spec-workflow.md`
- Modify: `tools/workflow_cli/gates.py` (`check_quality_gate`)
- Test: `tests/test_gates.py`

- [ ] **Step 1: Write the failing test**

```python
class TestSpecExternalDocsGate(unittest.TestCase):
    def setUp(self):
        from tools.workflow_cli.gates import check_quality_gate
        from tools.workflow_cli.models import Stage, TierBase, TierEstimate
        self.check = check_quality_gate
        self.Stage = Stage
        self.tier = TierEstimate(base=TierBase.STANDARD, modifiers=frozenset())

    def test_spec_missing_external_docs_section_fails(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            body = "# SPEC\n\nSome contracts here.\n"
            r = self.check(Path(tmp), self.Stage.SPEC, self.tier, [], body)
            self.assertFalse(r.passed)
            self.assertEqual(r.exit_code, 3)

    def test_spec_with_na_row_passes(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            body = (
                "# SPEC\n\n## External Documentation Checked\n\n"
                "N/A — no external dependencies\n"
            )
            r = self.check(Path(tmp), self.Stage.SPEC, self.tier, [], body)
            self.assertTrue(r.passed)

    def test_plan_stage_not_required_to_have_section(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            body = "# PLAN\n\n### PLAN-TASK-001: x\nTDD Applicable: no\nSteps:\n- [ ] go\n"
            r = self.check(Path(tmp), self.Stage.PLAN, self.tier, [], body)
            self.assertTrue(all("External Documentation" not in i for i in r.issues))
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_gates.py::TestSpecExternalDocsGate -v`
Expected: `test_spec_missing_external_docs_section_fails` FAILS.

- [ ] **Step 3: Add the SPEC presence check**

In `check_quality_gate`, inside the `if not issues:` block, add:

```python
        # Check 6 (SPEC): the External Documentation Checked section must be present.
        if stage == Stage.SPEC:
            if "## External Documentation Checked" not in artifact_content:
                issues.append(
                    "SPEC is missing the '## External Documentation Checked' section. "
                    "Add it; if there are no external dependencies, include an explicit "
                    "'N/A — no external dependencies' row."
                )
```

- [ ] **Step 4: Update `spec-workflow.md`**

In `docs/spec-workflow.md`, add a required `## External Documentation Checked` section to the SPEC template: a small dependency inventory (`dependency | version | check date | conclusion`), Context7-verified before finalizing SPEC, with an explicit `N/A — no external dependencies` row when there are none. Unverifiable entries marked `UNCONFIRMED`.

- [ ] **Step 5: Run to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_gates.py::TestSpecExternalDocsGate -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add tools/workflow_cli/gates.py docs/spec-workflow.md tests/test_gates.py
git commit -m "feat(gates): require External Documentation Checked section in SPEC"
```

### Task 4: Checkbox-tracked PLAN steps + linear readability in `plan-workflow.md`

**Files:**
- Modify: `docs/plan-workflow.md`
- Modify: `docs/spec-workflow.md`

- [ ] **Step 1: Convert PLAN step style to checkboxes**

In `docs/plan-workflow.md`, update the task template + TDD Decomposition guidance so per-task steps use `- [ ]` checkbox syntax (red → green → refactor as checkboxes), and add a one-line header instructing executors that the PLAN is a step-by-step checkable plan.

- [ ] **Step 2: Linear readability pass**

In both `docs/plan-workflow.md` and `docs/spec-workflow.md`, make each task/contract self-contained (behavior + verification + anchor in one place); change `Stable ID Definitions` guidance from an end-of-doc duplicate pile to "define inline; keep only an index table at the end".

- [ ] **Step 3: Verify**

Run: `grep -n "\- \[ \]" docs/plan-workflow.md | head`
Expected: checkbox examples present in the task template.

- [ ] **Step 4: Commit**

```bash
git add docs/plan-workflow.md docs/spec-workflow.md
git commit -m "docs: checkbox-tracked PLAN steps and linear self-contained task/contract layout"
```

### Task 5: Full suite + baseline

**Files:**
- Modify: `CLAUDE.md`, `.claude/skills/req-to-plan.md`

- [ ] **Step 1: Run the whole suite**

Run: `.venv/bin/python -m pytest tests/ -v`
Expected: all PASS.

- [ ] **Step 2: Backfill the baseline number**

Run: `.venv/bin/python -m pytest tests/ --co -q | tail -1`
Put the real collected number into `CLAUDE.md` and `.claude/skills/req-to-plan.md`.

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md .claude/skills/req-to-plan.md
git commit -m "docs: update test baseline after Part 3"
```

---

## Self-Review

**Spec coverage (Part 3):** machine-parseable schema (Task 1, §3.0); code-block hard-fail gate at standard tier, light/N-A exempt (Task 2, §3.1 + decision); SPEC External-Docs presence gate + doc (Task 3, §3.2 + TR7); checkbox steps + linear readability (Task 4, §3.3/§3.4); baseline (Task 5). ✓

**Placeholder scan:** Tasks 1/4 are doc-structure edits (no code to inline beyond the schema example, which is shown); Tasks 2/3 carry full helper code and tests. No TBD/TODO.

**Type consistency:** `_plan_tasks_missing_code`, `_PLAN_TASK_RE`, `_TDD_YES_RE`, `_CODE_FENCE_RE` defined once in Task 2; `check_quality_gate` signature unchanged (uses existing `stage`, `tier.base`); `Stage.PLAN`/`Stage.SPEC`/`TierBase.STANDARD` are existing symbols.

**Gate-firing scope:** Check 5 fires only for `stage == PLAN`; Check 6 only for `stage == SPEC` — verified by `test_non_plan_stage_unaffected` and `test_plan_stage_not_required_to_have_section`.

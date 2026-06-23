# req-to-plan Phase 1 — Hardening & PLAN/Stage Quality Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the `_prepare_input_file` symlink gap and make DESIGN→SPEC→PLAN artifacts un-shippable with placeholder/undecided content — all deterministic, no new schema fields.

**Architecture:** Pure additive checks on the existing Quality Gate (`check_quality_gate` → `_check_stage_schema` / R5 block) plus a one-function hardening of an agent-shortcut file writer. No state-machine changes, no new commands, no new modules. Each task is an isolated edit + targeted test.

**Tech Stack:** Python 3.10+ (stdlib + PyYAML), argparse CLI, `unittest`/pytest. Test runner: `.venv/bin/python -m pytest`.

**Source spec:** `docs/optimization-plan.md` §2.2, §2.3, §5.1, §5.2, §5.5 (Phase 1 in §6).

## Global Constraints

- **Hard cut, no compat:** no migration code, no support for old artifacts/state. (spec §1)
- **No over-defense / no speculative fallbacks:** every check must be deterministic and emit an observable failure; do not add silent fallbacks. (spec §1)
- **CLI never generates artifact text:** these changes only *validate* structure; they never write semantic content. (CLAUDE.md invariant)
- **Placeholder detection must not false-positive on normal prose:** keep patterns line/field-anchored or high-precision (3+ `?`, exact `待定`, exact `to be decided|determined`). (spec §2.3)
- **No new PLAN-TASK field:** `Verification` stays the acceptance contract; strengthen it, do not add `Acceptance`. (spec §2.1)
- **Tests:** use `tempfile.TemporaryDirectory`; never touch real `~/.req-to-plan` or `.req-to-plan/`. Run with `.venv/bin/python -m pytest` (system Python lacks PyYAML). (CLAUDE.md test conventions)
- **Worktree safety:** before Task 1 and before every commit, run `git status --short`. If any planned target file already has unrelated local changes, stop and ask for direction before editing or staging. Before each `git add`, run `git diff -- <task files>` and stage only the task files named in that task.
- **TDD:** red → green → commit per task. Full suite stays green at every commit.
- **Commit messages:** `<type>(r2p): <subject>`, and end every commit message with the trailer `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>` (shown in full in Task 1 Step 5; subject-only thereafter for brevity — append the same trailer each time).

---

### Task 1: Harden `_prepare_input_file` against symlinks + atomic write

**Files:**
- Modify: `tools/workflow_cli/agent_shortcuts.py:223-228` (`_prepare_input_file`)
- Modify: `tools/workflow_cli/atomic.py:9-10` (docstring note only — spec §5.2)
- Test: `tests/test_agent_shortcuts.py` (add a new `TestPrepareInputFileSymlink` class)

**Interfaces:**
- Consumes: `atomic_write_text(path, content)` from `tools.workflow_cli.atomic` (already imported at `agent_shortcuts.py:17`).
- Produces: `_prepare_input_file(run_dir, stage, suffix, seed="") -> Path` — unchanged signature; now raises `ValueError("unsafe_input_file_symlink")` if `run_dir/inputs` or the target path is a symlink, and writes the seed via `atomic_write_text` instead of `path.write_text`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_agent_shortcuts.py`:

```python
import os
import tempfile
import unittest
from pathlib import Path


class TestPrepareInputFileSymlink(unittest.TestCase):
    def test_rejects_preplanted_symlink_target(self):
        from tools.workflow_cli.agent_shortcuts import _prepare_input_file
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            (run_dir / "inputs").mkdir()
            outside = run_dir / "outside.md"
            outside.write_text("secret", encoding="utf-8")
            link = run_dir / "inputs" / "spec-content.md"
            os.symlink(outside, link)
            with self.assertRaises(ValueError):
                _prepare_input_file(run_dir, "spec", "content", "seed")
            # The symlink target must NOT have been written through.
            self.assertEqual(outside.read_text(encoding="utf-8"), "secret")

    def test_rejects_symlinked_inputs_directory(self):
        from tools.workflow_cli.agent_shortcuts import _prepare_input_file
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            run_dir = base / "run"
            run_dir.mkdir()
            outside_inputs = base / "outside-inputs"
            outside_inputs.mkdir()
            os.symlink(outside_inputs, run_dir / "inputs")
            with self.assertRaises(ValueError):
                _prepare_input_file(run_dir, "spec", "content", "seed")
            # The symlinked directory must NOT receive the seeded file.
            self.assertFalse((outside_inputs / "spec-content.md").exists())

    def test_writes_seed_when_absent_and_not_a_symlink(self):
        from tools.workflow_cli.agent_shortcuts import _prepare_input_file
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            p = _prepare_input_file(run_dir, "spec", "content", "seed text")
            self.assertEqual(p.read_text(encoding="utf-8"), "seed text")
            self.assertFalse(p.is_symlink())
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_agent_shortcuts.py::TestPrepareInputFileSymlink -v`
Expected: both symlink rejection tests FAIL (current code writes through / does not raise).

- [ ] **Step 3: Implement the hardening**

In `tools/workflow_cli/agent_shortcuts.py`, replace the body of `_prepare_input_file` (lines 223-228):

```python
def _prepare_input_file(run_dir: Path, stage: str, suffix: str, seed: str = "") -> Path:
    inputs_dir = run_dir / "inputs"
    if inputs_dir.is_symlink():
        raise ValueError("unsafe_input_file_symlink")
    inputs_dir.mkdir(parents=True, exist_ok=True)
    path = inputs_dir / f"{stage}-{suffix}.md"
    if path.is_symlink():
        raise ValueError("unsafe_input_file_symlink")
    if not path.exists():
        atomic_write_text(path, seed)
    return path
```

In `tools/workflow_cli/atomic.py`, extend the `atomic_write_text` docstring (line 10) to:

```python
    """Write text via a unique sibling temp file, then atomically replace path.

    Guarantees atomic-replace semantics (a reader sees either the old or the new
    file, never a truncated one). It does NOT fsync — durability across power
    loss / crash is a deliberate non-goal for this CLI.
    """
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_agent_shortcuts.py::TestPrepareInputFileSymlink -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: all pass before this commit.

```bash
git status --short
git diff -- tools/workflow_cli/agent_shortcuts.py tools/workflow_cli/atomic.py tests/test_agent_shortcuts.py
git add tools/workflow_cli/agent_shortcuts.py tools/workflow_cli/atomic.py tests/test_agent_shortcuts.py
git commit -m "fix(r2p): reject symlinked input file, write seed atomically

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 2: PLAN `Verification` placeholder gate (R5.2c) + template

**Files:**
- Modify: `tools/workflow_cli/gates.py` — widen `_FILL_IN_PLACEHOLDER_RE` to match colon-qualified guidance comments, add `_check_plan_task_verification_placeholders` (next to `_check_plan_task_skeleton_placeholders` at `gates.py:612`), and wire it into the R5 block at `gates.py:996`.
- Modify: `tools/workflow_cli/stage_templates.py:50` — keep a `fill in` token in the seeded `Verification` line + add an objective example.
- Test: `tests/test_gates.py` (new `TestPlanTaskVerificationPlaceholder` class), `tests/test_stage_templates.py` (one new assertion).

**Interfaces:**
- Consumes: `_iter_plan_task_bodies(content)`, `_plan_task_field_body(body, field)`, `_plan_task_label(body)`, `_PLACEHOLDER_PATTERNS` — all already in `gates.py`.
- Produces: `_check_plan_task_verification_placeholders(content: str) -> list[str]` — one issue per PLAN-TASK whose `Verification` body still matches a placeholder pattern. Wired so `check_quality_gate(..., Stage.PLAN, ...)` returns these in `result.issues`.
- Updates: `_FILL_IN_PLACEHOLDER_RE` so both `<!-- fill in -->` and `<!-- fill in: ... -->` are treated as unresolved placeholders; this is required because the PLAN template keeps guidance text inside the seeded `Verification` placeholder.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_gates.py`:

```python
class TestPlanTaskVerificationPlaceholder(unittest.TestCase):
    def _task(self, verification: str) -> str:
        return (
            "## Tasks\n"
            "### PLAN-TASK-001: do thing\n"
            "Spec References: SPEC-AUTH-001\n"
            "Change Type: modify\n"
            "TDD Applicable: yes\n"
            "Files:\n- src/x.py\n"
            "Skeleton:\n```python\npass\n```\n"
            "Steps:\n- [ ] do\n"
            f"Verification: {verification}\n"
        )

    def test_fill_in_verification_is_flagged(self):
        from tools.workflow_cli.gates import _check_plan_task_verification_placeholders
        self.assertTrue(
            _check_plan_task_verification_placeholders(self._task("<!-- fill in -->"))
        )

    def test_fill_in_guidance_comment_is_flagged(self):
        from tools.workflow_cli.gates import _check_plan_task_verification_placeholders
        self.assertTrue(
            _check_plan_task_verification_placeholders(
                self._task("<!-- fill in: objective pass/fail check -->")
            )
        )

    def test_tbd_verification_is_flagged(self):
        from tools.workflow_cli.gates import _check_plan_task_verification_placeholders
        self.assertTrue(
            _check_plan_task_verification_placeholders(self._task("TBD"))
        )

    def test_objective_verification_passes(self):
        from tools.workflow_cli.gates import _check_plan_task_verification_placeholders
        self.assertFalse(
            _check_plan_task_verification_placeholders(
                self._task("`pytest tests/x.py::test_y` passes")
            )
        )

    def test_quality_gate_reports_verification_placeholder_issue(self):
        import tempfile
        from pathlib import Path
        from tools.workflow_cli.gates import check_quality_gate
        from tools.workflow_cli.models import Stage, TierBase, TierEstimate
        tier = TierEstimate(base=TierBase.LIGHT, modifiers=frozenset())
        with tempfile.TemporaryDirectory() as tmp:
            result = check_quality_gate(
                Path(tmp), Stage.PLAN, tier, [], self._task("<!-- fill in -->")
            )
        self.assertTrue(
            any(
                "Verification contains an unresolved placeholder" in issue
                for issue in result.issues
            )
        )
```

Append to `tests/test_stage_templates.py` (inside `TestStageTemplates`):

```python
    def test_plan_template_verification_is_a_placeholder_until_filled(self):
        from tools.workflow_cli.stage_templates import template_for
        from tools.workflow_cli.gates import _check_plan_task_verification_placeholders
        text = template_for(Stage.PLAN, TierBase.STANDARD)
        # The seeded Verification must still trip the gate so an untouched
        # template cannot pass.
        self.assertTrue(_check_plan_task_verification_placeholders(text))
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_gates.py::TestPlanTaskVerificationPlaceholder tests/test_stage_templates.py::TestStageTemplates::test_plan_template_verification_is_a_placeholder_until_filled -v`
Expected: FAIL with `ImportError`/`AttributeError: ... _check_plan_task_verification_placeholders` (function not defined yet). After the helper exists but before the regex update, `test_fill_in_guidance_comment_is_flagged` still fails; that is the red test proving the template guidance placeholder stays blocked.

- [ ] **Step 3: Implement the gate function + wiring**

In `tools/workflow_cli/gates.py`, first widen `_FILL_IN_PLACEHOLDER_RE` (line 94) from:

```python
_FILL_IN_PLACEHOLDER_RE = re.compile(r"<!--\s*fill in\s*-->", re.IGNORECASE)
```

to:

```python
_FILL_IN_PLACEHOLDER_RE = re.compile(r"<!--\s*fill in(?:\s*:.*?)?\s*-->", re.IGNORECASE)
```

In `tools/workflow_cli/gates.py`, add directly after `_check_plan_task_skeleton_placeholders` (after line 621):

```python
def _check_plan_task_verification_placeholders(content: str) -> list[str]:
    issues: list[str] = []
    for body in _iter_plan_task_bodies(content):
        verification = _plan_task_field_body(body, "Verification")
        if verification.strip() and any(p.search(verification) for p in _PLACEHOLDER_PATTERNS):
            issues.append(
                f"{_plan_task_label(body)} Verification contains an unresolved "
                "placeholder; replace it with an objective pass/fail check "
                "(command + expected result) before passing the gate."
            )
    return issues
```

In `tools/workflow_cli/gates.py`, wire it into the R5 block immediately after line 996 (`issues.extend(_check_plan_task_skeleton_placeholders(gate_content))`):

```python
            # R5.2c: Verification must be an objective check, not a placeholder.
            issues.extend(_check_plan_task_verification_placeholders(gate_content))
```

- [ ] **Step 4: Update the template (keep a `fill in` token)**

In `tools/workflow_cli/stage_templates.py`, change the `Verification` line (line 50) inside the `(Stage.PLAN, "## Tasks")` body from:

```python
        "Verification: <!-- fill in -->\n"
```

to:

```python
        "Verification: <!-- fill in: objective pass/fail check (command + expected result), "
        "e.g. `pytest tests/x.py::test_y` passes / `GET /foo` returns 429 when over limit -->\n"
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_gates.py::TestPlanTaskVerificationPlaceholder tests/test_stage_templates.py -v`
Expected: PASS; the new 5 gate assertions and new template assertion are green, and existing stage-template tests remain green.

- [ ] **Step 6: Run the full gate + template suites for regressions**

Run: `.venv/bin/python -m pytest tests/test_gates.py tests/test_stage_templates.py -q`
Expected: all pass (no existing PLAN test regressed by R5.2c).

- [ ] **Step 7: Commit**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: all pass before this commit.

```bash
git status --short
git diff -- tools/workflow_cli/gates.py tools/workflow_cli/stage_templates.py tests/test_gates.py tests/test_stage_templates.py
git add tools/workflow_cli/gates.py tools/workflow_cli/stage_templates.py tests/test_gates.py tests/test_stage_templates.py
git commit -m "feat(r2p): gate PLAN-TASK Verification placeholders (R5.2c)"
```
(append the Co-Authored-By trailer)

---

### Task 3: Expand ambiguity markers for DESIGN/SPEC/PLAN (R2.2)

**Files:**
- Modify: `tools/workflow_cli/gates.py:96-106` (`_PLACEHOLDER_PATTERNS`)
- Test: `tests/test_gates.py` (new `TestAmbiguityMarkers` class)

**Interfaces:**
- Consumes: nothing new — extends the existing `_PLACEHOLDER_PATTERNS` list already consumed by R2.2 (`_check_stage_schema`, `gates.py:907`) and R5.2b/R5.2c.
- Produces: three additional patterns (`???`, `待定`, `to be decided|determined`) now cause R2.2 to fail for any schema'd stage.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_gates.py`:

```python
class TestAmbiguityMarkers(unittest.TestCase):
    def setUp(self):
        from tools.workflow_cli.gates import check_quality_gate
        from tools.workflow_cli.models import Stage, TierBase, TierEstimate
        self.check = check_quality_gate
        self.Stage = Stage
        self.tier = TierEstimate(base=TierBase.STANDARD, modifiers=frozenset())

    def _design_placeholder_issue(self, summary_body: str) -> bool:
        import tempfile
        from pathlib import Path
        content = f"# Design\n\n## Design Summary\n{summary_body}\n"
        with tempfile.TemporaryDirectory() as tmp:
            result = self.check(Path(tmp), self.Stage.DESIGN, self.tier, [], content)
        return any("placeholder" in i.lower() for i in result.issues)

    def test_triple_question_marks_flagged(self):
        self.assertTrue(self._design_placeholder_issue("error handling ???"))

    def test_zh_undecided_marker_flagged(self):
        self.assertTrue(self._design_placeholder_issue("锁策略待定"))

    def test_to_be_determined_flagged(self):
        self.assertTrue(self._design_placeholder_issue("retry count to be determined"))

    def test_normal_prose_not_flagged(self):
        # Hedge-ish prose with none of the markers must NOT raise a placeholder issue.
        self.assertFalse(
            self._design_placeholder_issue("We may add caching later if profiling shows need.")
        )
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_gates.py::TestAmbiguityMarkers -v`
Expected: the three "flagged" tests FAIL (markers not yet detected); `test_normal_prose_not_flagged` PASSES already.

- [ ] **Step 3: Add the markers**

In `tools/workflow_cli/gates.py`, extend `_PLACEHOLDER_PATTERNS` (insert before the closing `]` at line 106):

```python
    re.compile(r"\?{3,}"),                                  # ??? unresolved marker
    re.compile(r"待定"),                                     # zh: undecided / pending
    re.compile(r"(?i)\bto be (?:decided|determined)\b"),    # english placeholder phrase
]
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_gates.py::TestAmbiguityMarkers -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Run the full gate suite for false positives**

Run: `.venv/bin/python -m pytest tests/test_gates.py -q`
Expected: all pass — confirms no existing artifact fixture trips the new markers.

- [ ] **Step 6: Commit**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: all pass before this commit.

```bash
git status --short
git diff -- tools/workflow_cli/gates.py tests/test_gates.py
git add tools/workflow_cli/gates.py tests/test_gates.py
git commit -m "feat(r2p): flag ???/待定/'to be decided' as gate placeholders"
```
(append the Co-Authored-By trailer)

---

### Task 4: Checkpoint "no unresolved ambiguity" judgment line

**Files:**
- Modify: `tools/workflow_cli/agent_shortcuts.py:314-323` (the `needs_subagent_review` print in `_emit_checkpoint_stop`)
- Modify: `tools/workflow_cli/agent_templates/claude/SKILL.md` (checkpoint guidance bullet)
- Test: `tests/test_agent_shortcuts.py` (capture the subagent-review stop output)

**Interfaces:**
- Consumes: `_emit_checkpoint_stop(base_path, work_id, stage, record, run_dir)` — existing; only its printed guidance text changes.
- Produces: the forced-subagent-review stop instruction now names "unresolved ambiguity / undecided point" as an audit criterion; the human-facing SKILL.md checkpoint guidance carries the same criterion.

- [ ] **Step 1: Write the failing test**

This task only changes guidance strings. The deterministic test asserts the forced-subagent-review note contains the ambiguity criterion. Append to `tests/test_agent_shortcuts.py`:

```python
import io
import contextlib


class TestCheckpointAmbiguityGuidance(unittest.TestCase):
    def _emit_subagent_review_output(self) -> str:
        from pathlib import Path
        from tools.workflow_cli import agent_shortcuts as ash
        from tools.workflow_cli.models import (
            Stage, TierBase, TierModifier, TierEstimate, WorkId, STAGE_ARTIFACT_MAP,
        )
        from tools.workflow_cli.state import create_run_record, upsert_active_artifact
        # Force a subagent review at DESIGN: a safety modifier with no
        # version-matched review file on disk → _emit_checkpoint_stop prints
        # `needs_subagent_review`.
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            (run_dir / "reviews").mkdir()
            rec = create_run_record(WorkId("WF-20260101-x"))
            rec.current_stage = Stage.DESIGN
            rec.tier_locked = TierEstimate(
                base=TierBase.STANDARD,
                modifiers=frozenset({TierModifier.SAFETY}),
            )
            upsert_active_artifact(
                rec,
                stage=Stage.DESIGN,
                artifact=STAGE_ARTIFACT_MAP[Stage.DESIGN],
                version=1,
                status="ready",
            )
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                ash._emit_checkpoint_stop(run_dir, "WF-20260101-x", "design", rec, run_dir)
            return buf.getvalue()

    def test_subagent_review_note_mentions_ambiguity(self):
        out = self._emit_subagent_review_output()
        self.assertIn("needs_subagent_review", out)
        self.assertIn("ambiguity", out.lower())
```

> Implementer note: confirm `create_run_record` / `upsert_active_artifact` are importable from `tools/workflow_cli/state.py` (they are, at `state.py:37` and `state.py:96`). If `check_forced_subagent_review` does not treat `SAFETY@DESIGN` as forced, switch the modifier to `TierModifier.MIGRATION` — the test only needs *some* forced modifier to hit the `needs_subagent_review` branch.

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_agent_shortcuts.py::TestCheckpointAmbiguityGuidance -v`
Expected: FAIL on `assertIn("ambiguity", ...)` (current note does not mention it). If the test errors on record construction, fix the imports per the note until it runs and then fails on the assertion.

- [ ] **Step 3: Update the printed guidance**

In `tools/workflow_cli/agent_shortcuts.py`, change the `next:` line of the `needs_subagent_review` print (lines 320-323) to:

```python
            "next: have the review subagent audit the stage artifact for spec "
            "compliance, code/design quality, AND any unresolved ambiguity / "
            "undecided point (flag hedging that lacks a decision), write its "
            "findings to review_file, then r2p-continue\n"
```

- [ ] **Step 4: Update the human-facing checkpoint guidance**

In `tools/workflow_cli/agent_templates/claude/SKILL.md`, under the `r2p-continue` stop list (the bullet that begins "Stops at:"), add a sentence to the checkpoint-approval guidance:

```markdown
   - At a checkpoint, only approve a DESIGN/SPEC/PLAN artifact that has no unresolved ambiguity or undecided point: resolve it by evidence, or route it (DESIGN: `### DECISION-NNN`; SPEC/PLAN: `r2p-gap-open`) before approving.
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_agent_shortcuts.py::TestCheckpointAmbiguityGuidance -v`
Expected: PASS.

- [ ] **Step 6: Verify the template edit**

Run: `grep -n "no unresolved ambiguity" tools/workflow_cli/agent_templates/claude/SKILL.md`
Expected: one match.

- [ ] **Step 7: Commit**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: all pass before this commit.

```bash
git status --short
git diff -- tools/workflow_cli/agent_shortcuts.py tools/workflow_cli/agent_templates/claude/SKILL.md tests/test_agent_shortcuts.py
git add tools/workflow_cli/agent_shortcuts.py tools/workflow_cli/agent_templates/claude/SKILL.md tests/test_agent_shortcuts.py
git commit -m "feat(r2p): name unresolved ambiguity as a checkpoint audit criterion"
```
(append the Co-Authored-By trailer)

---

### Task 5: Document the reopen artifact-name invariant (comment-only)

**Files:**
- Modify: `tools/workflow_cli/cli.py:478-480` (comment only — spec §5.5)

**Interfaces:** none (no behavior change).

- [ ] **Step 1: Add the invariant comment**

In `tools/workflow_cli/cli.py`, in `_cmd_run_reopen`, add a comment immediately above the `artifact_name = STAGE_ARTIFACT_MAP.get(cp.stage)` line (line 479):

```python
        # Invariant: cp.artifact == STAGE_ARTIFACT_MAP[cp.stage] (artifacts are
        # only ever created via the map, artifact.py:23). The existence check and
        # the recorded name are therefore interchangeable; no drift path exists.
        artifact_name = STAGE_ARTIFACT_MAP.get(cp.stage)
```

- [ ] **Step 2: Verify the comment is present**

Run: `grep -n "no drift path exists" tools/workflow_cli/cli.py`
Expected: one match.

- [ ] **Step 3: Run the full suite (no behavior change → all green)**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: all pass.

- [ ] **Step 4: Commit**

```bash
git status --short
git diff -- tools/workflow_cli/cli.py
git add tools/workflow_cli/cli.py
git commit -m "docs(r2p): note cp.artifact == STAGE_ARTIFACT_MAP invariant in reopen"
```
(append the Co-Authored-By trailer)

---

## Final verification (after all tasks)

- [ ] **Run the whole suite:** `.venv/bin/python -m pytest tests/ -q` → all green.
- [ ] **Smoke the new gate path:** the PLAN `Verification` placeholder and the `待定`/`???`/`to be determined` markers now fail `gate-quality`; an untouched PLAN template fails until `Verification` is filled with an objective check.

## Self-Review (checklist run against the spec)

**1. Spec coverage (Phase 1 items in §6):**
- §5.1 `_prepare_input_file` symlink + atomic → Task 1 ✅
- §5.2 `atomic.py` docstring note → Task 1 Step 3 ✅
- §2.2 Verification placeholder gate + template → Task 2 ✅
- §2.3 marker expansion (`???`/`待定`/`to be decided|determined`) → Task 3 ✅
- §2.3 checkpoint ambiguity judgment (`_emit_checkpoint_stop` + SKILL.md) → Task 4 ✅
- §5.5 reopen invariant comment → Task 5 ✅
- Out of Phase 1 (deferred to Phase 2/3, correctly absent here): execute skill, archive, auto-commit, state machine, README skill-list updates.

**2. Placeholder scan:** No TBD/TODO/"similar to Task N" in steps; every code step carries full code; every run step carries the exact command + expected result. Task 4's test note explicitly flags the import paths to confirm (not a placeholder — a concrete verification instruction).

**3. Type/name consistency:** `_check_plan_task_verification_placeholders` is defined in Task 2 and referenced by the same name in Task 2's tests and the Task 2 template round-trip test. `_PLACEHOLDER_PATTERNS`, `_iter_plan_task_bodies`, `_plan_task_field_body`, `_plan_task_label` are existing symbols (verified in `gates.py`). `_emit_checkpoint_stop` signature matches `agent_shortcuts.py`.

**Known follow-up (not a Phase 1 gap):** Task 4's stdout-capture test depends on `create_run_record` / `upsert_active_artifact` / `STAGE_ARTIFACT_MAP[Stage.DESIGN]`; the implementer confirms these against `state.py`/`models.py` at write time (the plan flags this inline rather than guessing the exact constant).

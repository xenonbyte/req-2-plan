# Quality-Uplift (R1–R8) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the r2p workflow from a structural gatekeeper into a low-drift planning contract by adding stage templates, semantic schema gates, cross-stage trace coverage, repo-context ingestion, PLAN executability checks, and requirement-elicitation/scope-freeze — plus the CI/dev-deps/drift hygiene that protects them.

**Architecture:** All work lives under `tools/workflow_cli/`. The CLI/Agent invariant holds throughout — the CLI validates *structure* and *ground-truth anchors* (trace closure, file/config references against a Context Pack); it never generates artifact prose. New gate logic extends `gates.py`; new context lives in a `context_pack.py` module; trace logic in a `trace.py` module. Tests are `unittest.TestCase` with `tempfile.TemporaryDirectory`, run via `python -m pytest` after dev dependencies are installed.

**Tech Stack:** Python 3 (stdlib + PyYAML), argparse CLI, unittest, GitHub Actions.

**Source requirements:** `docs/requirements/2026-06-05-quality-uplift.md` (R1–R8). This plan implements them in the locked landing order.

---

## Global Execution Notes (read once)

- **Single document, by design.** The source spec spans multiple subsystems; per the requester's explicit preference this is one plan, sequenced into 8 phases in the locked landing order: **R6 → R7 → R1 → R2 → R4 → R3 → R8 → R5**. Each phase is independently testable and committable.
- **TDD everywhere it applies.** Gate/logic phases follow red→green→commit. Pure-infrastructure tasks (CI YAML, dev-deps) cannot be unit-tested; they use an explicit verification command instead, called out per task.
- **Every commit message** must end with the trailer `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>` (omitted from the per-task examples below for brevity — add it on every real commit).
- **Prerequisite (before Phase 1).** The commands below use `python -m pytest`, but R7 (which creates `requirements-dev.txt` and the portable scripts) lands *after* R6. So before running any phase, make sure the active interpreter has `pytest` + `PyYAML`: until R7.1 exists, either activate the repository `.venv` (it already has them) or `pip install pyyaml pytest`; from R7.1 onward use `pip install -r requirements-dev.txt`. This resolves the apparent conflict between the global `python -m pytest` commands and R7 landing mid-plan.
- **Test runner:** after R7 lands, use `python -m pytest` or `npm test` from an environment with `requirements-dev.txt` installed; never bare `pytest`. If a developer relies on the repository-local virtualenv, use `npm run test:local` as the explicit helper. Always pass `base_path=Path(tmp)` to CLI/shortcuts in tests; never touch real `.req-to-plan/`.
- **Branch:** all work lands on `chore/optimize` (already checked out).
- **Design Contract sections** (Phases R4/R3/R8) lock data structures and file formats *before* their tasks. They are plan-level design decisions; a reviewer may override them, but they are not placeholders — every task downstream references concrete names defined there.
- **Baseline guard:** after each phase, the full suite must stay green. Do not hardcode the exact test count anywhere (that is precisely what R6 removes).

---

## File Structure (whole plan)

**New modules**
- `tools/workflow_cli/stage_templates.py` — per-stage, per-tier seed templates + `template_for(stage, tier)` (R1).
- `tools/workflow_cli/context_pack.py` — `ProjectContextPack` dataclass, `build_context_pack(repo_path)`, JSON/MD writers (R4).
- `tools/workflow_cli/trace.py` — trace model, `build_trace(run_dir)`, closure checks (R3).

**New non-code files**
- `requirements-dev.txt` (R7)
- `.github/workflows/ci.yml` (R7)
- `tests/test_docs_consistency.py` (R6)
- `tests/test_stage_templates.py`, `tests/test_context_pack.py`, `tests/test_trace.py` (R1/R4/R3)

**Modified**
- `gates.py` — schema gate (R2), PLAN executability (R5), brief/risk scope+elicitation gate (R8).
- `agent_shortcuts.py` — seed content file from template (R1); expose `--repo-path` on `r2p-start` (R4).
- `cli.py` — wire Context Pack + local link expansion into `run-start` (R4); new `context-build` subcommand (R4).
- `repo_baseline.py` — reused by context_pack (R4).
- `tools/workflow_cli/agent_templates/claude/commands/r2p-start.md` (+ gemini/codex equivalents) — document `--repo-path` (R4).
- `.claude/skills/req-to-plan.md`, `CLAUDE.md` — remove hardcoded test-count magic numbers (R6).
- `tests/test_agent_shortcuts.py` — de-hardcode the `v1` version fixture (R6).
- `package.json` — add CI-friendly test script (R7).

---

## Phase 1 — R6: Eliminate docs / version / test-baseline drift

**Why first:** establishes the trust baseline and a regression guard before any other change adds tests. Production already uses `version.py` as the single source (`state.py:42`); the drift is only in a test fixture and two doc magic numbers.

### Task R6.1: Regression guard — docs must not hardcode a test-count magic number

**Files:**
- Create: `tests/test_docs_consistency.py`
- Modify: `.claude/skills/req-to-plan.md` (the `Test count baseline: 589 passing` line)
- Modify: `CLAUDE.md` (the `Baseline: 602 tests passing` line)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_docs_consistency.py
"""Guard against hardcoded test-count magic numbers drifting across docs.

TDD: written before the docs are cleaned up.
"""
import re
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Matches "589 passing", "602 tests passing", "baseline: 673", etc.
_MAGIC_COUNT = re.compile(r"\b\d{2,}\s+(?:tests?\s+)?passing\b|baseline[:：]\s*\d{2,}", re.IGNORECASE)

# Docs that must describe the suite qualitatively, not with a frozen number.
_GUARDED_DOCS = [
    "CLAUDE.md",
    ".claude/skills/req-to-plan.md",
]


class TestDocsHaveNoHardcodedTestCount(unittest.TestCase):
    def test_no_magic_test_count_in_guarded_docs(self):
        offenders = []
        for rel in _GUARDED_DOCS:
            path = REPO_ROOT / rel
            if not path.exists():
                continue
            for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if _MAGIC_COUNT.search(line):
                    offenders.append(f"{rel}:{lineno}: {line.strip()}")
        self.assertEqual(
            offenders, [],
            "Docs must not hardcode a test count (it drifts). Describe the suite "
            "qualitatively instead. Offenders:\n" + "\n".join(offenders),
        )


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_docs_consistency.py -v`
Expected: FAIL — offenders list contains the `589` line in the skill and the `602` line in CLAUDE.md.

- [ ] **Step 3: Remove the magic numbers from both docs**

In `.claude/skills/req-to-plan.md`, change:
`Test count baseline: 589 passing. All tests must stay green after any change.`
→ `All tests must stay green after any change (run the full suite; do not rely on a frozen count).`

In `CLAUDE.md`, change the `- Baseline: 602 tests passing. All must stay green.` line to:
`- All tests must stay green. Run the full suite; the exact count is intentionally not pinned here.`

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_docs_consistency.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/test_docs_consistency.py .claude/skills/req-to-plan.md CLAUDE.md
git commit -m "test(r2p): guard against hardcoded test-count drift in docs (R6)"
```

### Task R6.2: De-hardcode the `v1` version fixture

**Files:**
- Modify: `tests/test_agent_shortcuts.py:49` (the `## r2p Version\nv1` fixture string)

- [ ] **Step 1: Confirm no test asserts the literal r2p version is `v1`**

Run: `grep -n "r2p Version" tests/test_agent_shortcuts.py` and `grep -rn '"v1"\|== .v1.\|r2p_version' tests/test_agent_shortcuts.py`
Expected: the only `## r2p Version` producer is the fixture at line ~49; no assertion compares the r2p version to `v1`. (The `design-subagent-review-v1.md` strings at lines ~1041/1057 are review-file versions — leave them untouched.)

- [ ] **Step 2: Replace the hardcoded version in the fixture with the real source of truth**

At the top of `tests/test_agent_shortcuts.py`, ensure this import exists:

```python
from tools.workflow_cli.version import R2P_VERSION
```

Change the fixture line (currently):

```python
f"# Workflow Run: {work_id}\n\n## Status\n{status.value}\n\n## Current Stage\nraw_requirement\n\n## r2p Version\nv1\n",
```

to:

```python
f"# Workflow Run: {work_id}\n\n## Status\n{status.value}\n\n## Current Stage\nraw_requirement\n\n## r2p Version\n{R2P_VERSION}\n",
```

- [ ] **Step 3: Run the affected suite to verify nothing regressed**

Run: `python -m pytest tests/test_agent_shortcuts.py -v`
Expected: PASS (same number of tests as before, now version-agnostic).

- [ ] **Step 4: Commit**

```bash
git add tests/test_agent_shortcuts.py
git commit -m "test(r2p): bind version fixture to version.py single source (R6)"
```

---

## Phase 2 — R7: Dev dependencies + CI

**Why second:** a green CI on every PR is the protective harness for all later phases. Infrastructure tasks — verification is "deps install + suite runs", not red→green.

### Task R7.1: Add `requirements-dev.txt`

**Files:**
- Create: `requirements-dev.txt`

- [ ] **Step 1: Create the dev requirements file**

```text
# requirements-dev.txt — development & CI dependencies
-r requirements.txt
pytest>=8.0
pytest-cov>=5.0
```

- [ ] **Step 2: Verify a clean install runs the suite**

Run:
```bash
python3 -m venv /tmp/r2p-devcheck && /tmp/r2p-devcheck/bin/pip install -q -r requirements-dev.txt && /tmp/r2p-devcheck/bin/python -m pytest -q
```
Expected: suite runs and passes (this proves the dev-deps file is sufficient to run tests from scratch). Then `rm -rf /tmp/r2p-devcheck`.

- [ ] **Step 3: Commit**

```bash
git add requirements-dev.txt
git commit -m "build(r2p): add requirements-dev.txt for reproducible test env (R7)"
```

### Task R7.2: Add GitHub Actions CI

**Files:**
- Create: `.github/workflows/ci.yml`

- [ ] **Step 1: Create the workflow**

```yaml
# .github/workflows/ci.yml
name: CI
on:
  push:
    branches: [main]
  pull_request:
jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ["3.11", "3.12"]
    steps:
      - uses: actions/checkout@v4
      - name: Set up Python ${{ matrix.python-version }}
        uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}
      - name: Install dependencies
        run: pip install -r requirements-dev.txt
      - name: Run tests
        run: python -m pytest -q
```

- [ ] **Step 2: Verify the workflow is valid YAML and the command matches local reality**

Run: `python -c "import yaml,sys; yaml.safe_load(open('.github/workflows/ci.yml')); print('yaml ok')"`
Then confirm the test command works without `.venv`: `python3 -m venv /tmp/r2p-ci && /tmp/r2p-ci/bin/pip install -q -r requirements-dev.txt && /tmp/r2p-ci/bin/python -m pytest -q && rm -rf /tmp/r2p-ci`
Expected: `yaml ok` and a passing suite.

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "ci(r2p): run pytest on push and PR across Python 3.11/3.12 (R7)"
```

### Task R7.3: Decouple `npm test` from the hardcoded `.venv` path

**Files:**
- Modify: `package.json` (`scripts`)

- [ ] **Step 1: Make `npm test` interpreter-agnostic while keeping a local `.venv` helper**

In `package.json`, make the default test command portable and keep the documented `.venv` workflow as an explicit local helper:

```json
  "scripts": {
    "test": "python -m pytest",
    "test:local": ".venv/bin/python -m pytest",
    "prepack": "node bin/r2p.js version >/dev/null"
  },
```

Rationale: R7 specifically requires decoupling the default package test entrypoint from `.venv`. Developers who rely on the repository-local virtualenv can still run `npm run test:local`, while CI and fresh environments use the ambient interpreter after installing `requirements-dev.txt`. No separate `test:ci` script is needed — CI (R7.2) invokes `python -m pytest` directly, which is identical to `npm test`.

- [ ] **Step 2: Verify package.json stays valid**

Run: `node -e "const s=require('./package.json').scripts; if(s.test!== 'python -m pytest' || !s['test:local']) process.exit(1); console.log('package.json ok')" && npm test -- -q`
Expected: `package.json ok` and a passing pytest suite through the package test entrypoint.

- [ ] **Step 3: Commit**

```bash
git add package.json
git commit -m "build(r2p): decouple npm test from .venv path (R7)"
```

---

## Phase 3 — R1: Stage templates + content seeding

**Why third:** templates are the readable form of the R2 schema gate; defining them first lets R2 validate against the same source.

**Ordering caveat (load-bearing):** R1 lands *before* R4 (Context Pack) and R3 (trace engine). Therefore R1 seeds only **static structure + an upstream-artifact summary** (using the existing `read_artifact`). The template includes a *static* `## Trace` table skeleton for the agent to fill, but it does **not** auto-derive trace (that is R3) and does **not** inject a Context Pack summary (that is a seeding enhancement added in R4 Task R4.5). Stated here so no task promises machinery that does not yet exist.

### Design Contract — `STAGE_SCHEMA` (single source for templates *and* R2 gate)

A single dict is the source of truth for required headings per stage per tier. `stage_templates.py` renders it into seed text; `gates.py` (R2) validates presence against it. This makes P3 ("template ↔ gate byte-identical") structural rather than a discipline note.

```python
# tools/workflow_cli/stage_schema.py
from tools.workflow_cli.models import Stage, TierBase

# Headings MUST stay byte-identical to any existing gate regex they overlap.
# Notably "## External Documentation Checked" matches gates.py:_EXTERNAL_DOCS_RE.
STAGE_SCHEMA: dict = {
    Stage.REQUIREMENT_BRIEF: {
        TierBase.LIGHT: ["## Goal", "## In-Scope", "## Out-of-Scope", "## Acceptance Criteria"],
        TierBase.STANDARD: [
            "## Goal", "## In-Scope", "## Out-of-Scope", "## Non-Goals",
            "## Assumptions", "## Acceptance Criteria", "## Open Questions", "## Sources",
        ],
    },
    Stage.RISK_DISCOVERY: {
        TierBase.LIGHT: ["## Risks", "## Boundaries"],
        TierBase.STANDARD: ["## Risks", "## Boundaries", "## Scope Overflow Risks", "## Mitigations"],
    },
    Stage.DESIGN: {
        TierBase.LIGHT: ["## Design Summary", "## Chosen Design", "## SPEC Handoff"],
        TierBase.STANDARD: [
            "## Design Summary", "## Current Code Evidence", "## Requirements Coverage",
            "## Options Considered", "## Chosen Design", "## Rollback",
            "## Observability", "## SPEC Handoff",
        ],
    },
    Stage.SPEC: {
        TierBase.LIGHT: ["## Behavior Contracts", "## External Documentation Checked", "## PLAN Handoff"],
        TierBase.STANDARD: [
            "## Behavior Contracts", "## API / Data / Config Contracts",
            "## External Documentation Checked", "## Test Matrix", "## Non-goals", "## PLAN Handoff",
        ],
    },
    Stage.PLAN: {
        # PLAN's substantive checks (task coverage, fields) live in R5, not R2.
        TierBase.LIGHT: ["## Tasks"],
        TierBase.STANDARD: ["## Tasks"],
    },
}


def required_headings(stage: Stage, tier_base: TierBase) -> list[str]:
    """Required top-level headings for a stage at a tier base; [] if unschema'd."""
    return list(STAGE_SCHEMA.get(stage, {}).get(tier_base, []))
```

### Task R1.1: `stage_schema.py` — the single source of truth

**Files:**
- Create: `tools/workflow_cli/stage_schema.py`
- Test: `tests/test_stage_schema.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_stage_schema.py
import unittest
from tools.workflow_cli.models import Stage, TierBase


class TestStageSchema(unittest.TestCase):
    def test_required_headings_brief_standard_is_superset_of_light(self):
        from tools.workflow_cli.stage_schema import required_headings
        light = set(required_headings(Stage.REQUIREMENT_BRIEF, TierBase.LIGHT))
        standard = set(required_headings(Stage.REQUIREMENT_BRIEF, TierBase.STANDARD))
        self.assertTrue(light.issubset(standard))
        # Scope freeze is mandatory at both tiers (R8 depends on this).
        self.assertIn("## In-Scope", light)
        self.assertIn("## Out-of-Scope", light)

    def test_spec_heading_matches_existing_external_docs_gate(self):
        from tools.workflow_cli.stage_schema import required_headings
        headings = required_headings(Stage.SPEC, TierBase.STANDARD)
        self.assertIn("## External Documentation Checked", headings)

    def test_unschemaed_stage_returns_empty(self):
        from tools.workflow_cli.stage_schema import required_headings
        self.assertEqual(required_headings(Stage.RAW_REQUIREMENT, TierBase.LIGHT), [])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_stage_schema.py -v`
Expected: FAIL — `ModuleNotFoundError: tools.workflow_cli.stage_schema`.

- [ ] **Step 3: Create `stage_schema.py`**

Use the exact content from the Design Contract above.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_stage_schema.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tools/workflow_cli/stage_schema.py tests/test_stage_schema.py
git commit -m "feat(r2p): add STAGE_SCHEMA single source for templates and gates (R1)"
```

### Task R1.2: `stage_templates.py` — render schema into seed text

**Files:**
- Create: `tools/workflow_cli/stage_templates.py`
- Test: `tests/test_stage_templates.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_stage_templates.py
import unittest
from tools.workflow_cli.models import Stage, TierBase


class TestStageTemplates(unittest.TestCase):
    def test_template_contains_every_required_heading(self):
        from tools.workflow_cli.stage_templates import template_for
        from tools.workflow_cli.stage_schema import required_headings
        text = template_for(Stage.REQUIREMENT_BRIEF, TierBase.STANDARD)
        for h in required_headings(Stage.REQUIREMENT_BRIEF, TierBase.STANDARD):
            self.assertIn(h, text)

    def test_template_includes_static_trace_skeleton(self):
        from tools.workflow_cli.stage_templates import template_for
        text = template_for(Stage.REQUIREMENT_BRIEF, TierBase.LIGHT)
        self.assertIn("## Trace", text)

    def test_brief_template_seeds_scope_ids(self):
        from tools.workflow_cli.stage_templates import template_for
        text = template_for(Stage.REQUIREMENT_BRIEF, TierBase.STANDARD)
        self.assertIn("SCOPE-IN-001", text)
        self.assertIn("SCOPE-OUT-001", text)

    def test_templates_seed_native_stage_ids(self):
        from tools.workflow_cli.stage_templates import template_for
        self.assertIn("RISK-", template_for(Stage.RISK_DISCOVERY, TierBase.STANDARD))
        self.assertIn("DES-", template_for(Stage.DESIGN, TierBase.STANDARD))
        self.assertIn("SPEC-", template_for(Stage.SPEC, TierBase.STANDARD))

    def test_plan_template_seeds_required_task_fields(self):
        from tools.workflow_cli.stage_templates import template_for
        text = template_for(Stage.PLAN, TierBase.STANDARD)
        self.assertIn("### PLAN-TASK-001", text)
        for field in ("Spec References:", "Change Type:", "Files:", "Verification:"):
            self.assertIn(field, text)

    def test_unschemaed_stage_yields_minimal_template(self):
        from tools.workflow_cli.stage_templates import template_for
        text = template_for(Stage.RAW_REQUIREMENT, TierBase.LIGHT)
        self.assertIsInstance(text, str)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_stage_templates.py -v`
Expected: FAIL — module missing.

- [ ] **Step 3: Implement `stage_templates.py`**

```python
# tools/workflow_cli/stage_templates.py
"""Render STAGE_SCHEMA into per-stage, per-tier seed templates.

The CLI writes these into the stage content file so the agent starts from a
structured skeleton, not a blank page. Templates carry no semantic claims —
only headings, required gate anchors, example ID shapes, and a static trace-table skeleton.
"""
from __future__ import annotations

from tools.workflow_cli.models import Stage, TierBase
from tools.workflow_cli.stage_schema import required_headings

_TRACE_SKELETON = (
    "## Trace\n"
    "<!-- Map this stage's IDs to upstream/downstream. R3 derives & checks closure. -->\n"
    "| This ID | Upstream | Status |\n"
    "|---|---|---|\n"
)


_HEADING_BODY = {
    (Stage.REQUIREMENT_BRIEF, "## In-Scope"): "- SCOPE-IN-001 <!-- fill in -->\n",
    (Stage.REQUIREMENT_BRIEF, "## Out-of-Scope"): "- SCOPE-OUT-001 <!-- fill in -->\n",
    (Stage.RISK_DISCOVERY, "## Risks"): "### RISK-SEC-001 <!-- fill in -->\nStatus: <!-- fill in -->\n",
    (Stage.DESIGN, "## Chosen Design"): "### DES-ARCH-001 <!-- fill in -->\n",
    (Stage.SPEC, "## Behavior Contracts"): "### SPEC-BEHAVIOR-001 <!-- fill in -->\n",
    (Stage.PLAN, "## Tasks"): (
        "### PLAN-TASK-001 <!-- fill in -->\n"
        "Spec References: SPEC-BEHAVIOR-001\n"
        "Change Type: modify\n"
        "TDD Applicable: yes\n"
        "Files:\n"
        "- <!-- fill in -->\n"
        "Skeleton:\n"
        "```python\n"
        "# <!-- fill in -->\n"
        "```\n"
        "Steps:\n"
        "- [ ] <!-- fill in -->\n"
        "Verification: <!-- fill in -->\n"
    ),
}


def _body_for(stage: Stage, heading: str) -> str:
    return _HEADING_BODY.get((stage, heading), "<!-- fill in -->\n")


def template_for(stage: Stage, tier_base: TierBase) -> str:
    headings = required_headings(stage, tier_base)
    title = stage.value.replace("_", " ").title()
    parts = [f"# {title}\n"]
    for h in headings:
        parts.append(f"{h}\n{_body_for(stage, h)}")
    parts.append(_TRACE_SKELETON)
    return "\n".join(parts)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_stage_templates.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tools/workflow_cli/stage_templates.py tests/test_stage_templates.py
git commit -m "feat(r2p): render stage seed templates from STAGE_SCHEMA (R1)"
```

### Task R1.3: Seed the content file on `needs_content`

**Files:**
- Modify: `tools/workflow_cli/agent_shortcuts.py` (add `_seed_for_stage`; use it at the `needs_content` branch ~line 444)
- Test: `tests/test_agent_shortcuts.py` (new test for `_seed_for_stage`)

- [ ] **Step 1: Write the failing test**

```python
# add to tests/test_agent_shortcuts.py
class TestSeedForStage(unittest.TestCase):
    def test_seed_includes_scope_headings_for_brief(self):
        from tools.workflow_cli.agent_shortcuts import _seed_for_stage
        from tools.workflow_cli.models import Stage, TierBase, TierEstimate
        tier = TierEstimate(base=TierBase.STANDARD, modifiers=frozenset())
        seed = _seed_for_stage(Stage.REQUIREMENT_BRIEF, tier, upstream_summary="")
        self.assertIn("## In-Scope", seed)
        self.assertIn("## Out-of-Scope", seed)

    def test_seed_appends_upstream_summary_when_present(self):
        from tools.workflow_cli.agent_shortcuts import _seed_for_stage
        from tools.workflow_cli.models import Stage, TierBase, TierEstimate
        tier = TierEstimate(base=TierBase.LIGHT, modifiers=frozenset())
        seed = _seed_for_stage(Stage.DESIGN, tier, upstream_summary="REQ-AUTH-001: do X")
        self.assertIn("REQ-AUTH-001: do X", seed)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_agent_shortcuts.py -k SeedForStage -v`
Expected: FAIL — `_seed_for_stage` not defined.

- [ ] **Step 3: Implement `_seed_for_stage` and wire it into the `needs_content` branch**

Add near the other helpers in `agent_shortcuts.py`:

```python
def _seed_for_stage(stage, tier, upstream_summary: str = "") -> str:
    """Build the seed text for a stage content file: template + upstream summary.

    Context Pack summary injection is added in R4 (Task R4.5); not here.
    """
    from tools.workflow_cli.stage_templates import template_for
    base = tier.base if tier is not None else None
    text = template_for(stage, base) if base is not None else ""
    if upstream_summary.strip():
        text += "\n## Upstream Summary (read-only)\n" + upstream_summary.strip() + "\n"
    return text
```

At the `needs_content` branch (currently `content_file = _prepare_input_file(run_path.parent, stage, "content")`), replace with:

```python
                try:
                    upstream = read_artifact(run_path.parent, _prev_stage(record.current_stage)) if _prev_stage(record.current_stage) else ""
                except FileNotFoundError:
                    upstream = ""
                seed = _seed_for_stage(record.current_stage, record.tier_locked, upstream)
                content_file = _prepare_input_file(run_path.parent, stage, "content", seed)
```

If a `_prev_stage` helper does not already exist, add a minimal one using the existing `Stage` ordering (the stage list is defined in `models.py`):

```python
def _prev_stage(stage):
    from tools.workflow_cli.models import Stage
    order = list(Stage)
    i = order.index(stage)
    return order[i - 1] if i > 0 else None
```

- [ ] **Step 4: Run tests to verify pass (unit + no regression)**

Run: `python -m pytest tests/test_agent_shortcuts.py -v`
Expected: PASS, including the new `TestSeedForStage`.

- [ ] **Step 5: Commit**

```bash
git add tools/workflow_cli/agent_shortcuts.py tests/test_agent_shortcuts.py
git commit -m "feat(r2p): seed stage content file from template + upstream summary (R1)"
```

---

## Phase 4 — R2: Tier-aware schema gate

**Why fourth:** with templates (R1) defining structure, the gate can now reject documents that lack required sections or that still carry unfilled template placeholders. Reuses `STAGE_SCHEMA` — no second source.

**Scope boundary:** PLAN's substantive task checks (coverage, fields, numbering) are R5, not here. R2 checks required headings, non-empty required section bodies, stage-native ID patterns, and placeholder ban for every schema'd stage. PLAN's only R2 structural requirement is the `## Tasks` heading; PLAN-TASK field semantics remain in R5.

### Task R2.1: Required-section check in the quality gate

**Files:**
- Modify: `tools/workflow_cli/gates.py` (add `_check_stage_schema`; call it in `check_quality_gate`)
- Test: `tests/test_gates.py`

- [ ] **Step 1: Write the failing test**

```python
# add to tests/test_gates.py
class TestStageSchemaGate(unittest.TestCase):
    def setUp(self):
        from tools.workflow_cli.gates import check_quality_gate
        from tools.workflow_cli.models import Stage, TierBase, TierEstimate
        self.check_quality_gate = check_quality_gate
        self.Stage = Stage
        self.tier = TierEstimate(base=TierBase.STANDARD, modifiers=frozenset())

    def test_brief_missing_out_of_scope_section_fails(self):
        import tempfile
        from pathlib import Path
        # Has Goal/In-Scope/Acceptance but is missing Out-of-Scope etc.
        content = "# Requirement Brief\n\n## Goal\nDo X\n\n## In-Scope\nthing\n\n## Acceptance Criteria\npasses\n"
        with tempfile.TemporaryDirectory() as tmp:
            result = self.check_quality_gate(Path(tmp), self.Stage.REQUIREMENT_BRIEF, self.tier, [], content)
        self.assertFalse(result.passed)
        self.assertTrue(any("Out-of-Scope" in i for i in result.issues))

    def test_brief_with_all_sections_passes_schema(self):
        import tempfile
        from pathlib import Path
        from tools.workflow_cli.stage_schema import required_headings
        from tools.workflow_cli.models import TierBase
        body = "# Requirement Brief\n\n" + "\n".join(
            f"{h}\nreal content here\n" for h in required_headings(self.Stage.REQUIREMENT_BRIEF, TierBase.STANDARD)
        )
        with tempfile.TemporaryDirectory() as tmp:
            result = self.check_quality_gate(Path(tmp), self.Stage.REQUIREMENT_BRIEF, self.tier, [], body)
        # No schema issue should be raised (other gate checks may still apply but headings are present).
        self.assertFalse(any("Missing required section" in i for i in result.issues))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_gates.py -k StageSchemaGate -v`
Expected: FAIL — `test_brief_missing_out_of_scope_section_fails` does not see a "Missing required section" issue because no schema check exists yet.

- [ ] **Step 3: Implement `_check_stage_schema` and call it**

Add to `gates.py`:

```python
def _check_stage_schema(stage: Stage, tier: TierEstimate, content: str) -> list[str]:
    """R2: required top-level headings for the stage at this tier base must be present."""
    from tools.workflow_cli.stage_schema import required_headings
    issues: list[str] = []
    for heading in required_headings(stage, tier.base):
        if heading not in content:
            issues.append(
                f"Missing required section {heading!r} for stage {stage.value!r} "
                f"at tier '{tier.base.value}'."
            )
    return issues
```

In `check_quality_gate`, inside the `if not issues:` block, after Check 6 (SPEC external docs), add:

```python
        # Check 7 (R2): tier-aware required-section schema.
        if not issues:
            issues.extend(_check_stage_schema(stage, tier, artifact_content))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_gates.py -k StageSchemaGate -v`
Expected: PASS.

- [ ] **Step 5: Run the full gate suite; update older fixtures that fed placeholder content**

Run: `python -m pytest tests/test_gates.py -v`
Expected: PASS. **Regression note:** the new schema check rejects pre-existing tests that asserted a pass on minimal placeholder content (e.g. `check_quality_gate(..., Stage.DESIGN, tier, [], "# Design\n\nSome valid content here.")` at `tests/test_gates.py:~179`). Update those fixtures to include the stage's required headings so the suite stays green. The same applies after R2.3, which additionally requires a native-ID heading and non-empty bodies — re-run the full gate suite there and fix any remaining legacy fixtures.

- [ ] **Step 6: Commit**

```bash
git add tools/workflow_cli/gates.py tests/test_gates.py
git commit -m "feat(r2p): tier-aware required-section schema gate (R2)"
```

### Task R2.2: Placeholder ban (reject unfilled templates)

**Files:**
- Modify: `tools/workflow_cli/gates.py` (extend `_check_stage_schema` with a placeholder scan)
- Test: `tests/test_gates.py`

- [ ] **Step 1: Write the failing test**

```python
# add to tests/test_gates.py (TestStageSchemaGate class)
    def test_unfilled_template_placeholder_fails(self):
        import tempfile
        from pathlib import Path
        from tools.workflow_cli.stage_schema import required_headings
        from tools.workflow_cli.models import TierBase
        # All headings present but bodies are still the template's "<!-- fill in -->".
        body = "# Requirement Brief\n\n" + "\n".join(
            f"{h}\n<!-- fill in -->\n" for h in required_headings(self.Stage.REQUIREMENT_BRIEF, TierBase.STANDARD)
        )
        with tempfile.TemporaryDirectory() as tmp:
            result = self.check_quality_gate(Path(tmp), self.Stage.REQUIREMENT_BRIEF, self.tier, [], body)
        self.assertFalse(result.passed)
        self.assertTrue(any("placeholder" in i.lower() for i in result.issues))

    def test_tbd_as_final_content_fails(self):
        import tempfile
        from pathlib import Path
        from tools.workflow_cli.stage_schema import required_headings
        from tools.workflow_cli.models import TierBase
        body = "# Requirement Brief\n\n" + "\n".join(
            f"{h}\nTBD\n" for h in required_headings(self.Stage.REQUIREMENT_BRIEF, TierBase.STANDARD)
        )
        with tempfile.TemporaryDirectory() as tmp:
            result = self.check_quality_gate(Path(tmp), self.Stage.REQUIREMENT_BRIEF, self.tier, [], body)
        self.assertFalse(result.passed)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_gates.py -k "placeholder or tbd" -v`
Expected: FAIL — no placeholder check yet.

- [ ] **Step 3: Add the placeholder scan to `_check_stage_schema`**

At the top of `gates.py` (module level), add:

```python
_PLACEHOLDER_PATTERNS = [
    re.compile(r"<!--\s*fill in\s*-->", re.IGNORECASE),  # untouched template body
    re.compile(r"(?m)^\s*TBD\s*$"),                       # TBD as a standalone final line
    re.compile(r"\bTODO later\b", re.IGNORECASE),
    re.compile(r"\bFIXME\b"),
]
```

Extend `_check_stage_schema` (append before `return issues`):

```python
    for pat in _PLACEHOLDER_PATTERNS:
        if pat.search(content):
            issues.append(
                "Artifact contains an unresolved placeholder "
                f"(pattern {pat.pattern!r}); fill it before passing the gate."
            )
            break
```

Note: `maybe` from the source spec is intentionally *not* a hard-ban pattern — as a common English word it is too false-positive-prone for a blocking gate; it is left to checkpoint review.

- [ ] **Step 4: Run tests to verify pass**

Run: `python -m pytest tests/test_gates.py -k StageSchemaGate -v`
Expected: PASS (4 cases: missing-section, all-sections, placeholder, tbd).

- [ ] **Step 5: Commit**

```bash
git add tools/workflow_cli/gates.py tests/test_gates.py
git commit -m "feat(r2p): reject unfilled template placeholders in quality gate (R2)"
```

### Task R2.3: Required field bodies + stage-native ID pattern checks

**Files:**
- Modify: `tools/workflow_cli/gates.py` (extend the schema gate with required-body and ID-pattern validation)
- Test: `tests/test_gates.py`

- [ ] **Step 1: Write the failing tests**

```python
# add to tests/test_gates.py (TestStageSchemaGate class)
    def test_required_section_with_empty_body_fails(self):
        import tempfile
        from pathlib import Path
        from tools.workflow_cli.stage_schema import required_headings
        from tools.workflow_cli.models import TierBase
        # All headings are present, but one required section has no body.
        parts = ["# Requirement Brief"]
        for h in required_headings(self.Stage.REQUIREMENT_BRIEF, TierBase.STANDARD):
            body = "" if h == "## Sources" else "- REQ-AUTH-001 real content"
            parts.append(f"{h}\n{body}\n")
        with tempfile.TemporaryDirectory() as tmp:
            result = self.check_quality_gate(Path(tmp), self.Stage.REQUIREMENT_BRIEF, self.tier, [], "\n".join(parts))
        self.assertFalse(result.passed)
        self.assertTrue(any("Sources" in i and "body" in i for i in result.issues))

    def test_spec_without_heading_defined_native_spec_id_fails(self):
        import tempfile
        from pathlib import Path
        from tools.workflow_cli.stage_schema import required_headings
        from tools.workflow_cli.models import TierBase
        body = "# Spec\n\n" + "\n".join(
            f"{h}\nSPEC-AUTH-001 only in body\n" for h in required_headings(self.Stage.SPEC, TierBase.STANDARD)
        )
        with tempfile.TemporaryDirectory() as tmp:
            result = self.check_quality_gate(Path(tmp), self.Stage.SPEC, self.tier, [], body)
        self.assertFalse(result.passed)
        self.assertTrue(any("heading" in i and "SPEC-" in i for i in result.issues))

    def test_spec_with_heading_defined_native_spec_id_passes_id_check(self):
        import tempfile
        from pathlib import Path
        from tools.workflow_cli.stage_schema import required_headings
        from tools.workflow_cli.models import TierBase
        body = "# Spec\n\n## SPEC-AUTH-001 Behavior\nreal content\n" + "\n".join(
            f"{h}\nreal content here\n" for h in required_headings(self.Stage.SPEC, TierBase.STANDARD)
        )
        with tempfile.TemporaryDirectory() as tmp:
            result = self.check_quality_gate(Path(tmp), self.Stage.SPEC, self.tier, [], body)
        self.assertFalse(any("native trace ID" in i for i in result.issues))

    def test_brief_scope_section_ids_do_not_require_heading_definition(self):
        import tempfile
        from pathlib import Path
        from tools.workflow_cli.stage_schema import required_headings
        from tools.workflow_cli.models import TierBase
        parts = ["# Requirement Brief"]
        for h in required_headings(self.Stage.REQUIREMENT_BRIEF, TierBase.STANDARD):
            if h == "## In-Scope":
                parts.append(f"{h}\n- SCOPE-IN-001 rate limit per IP\n")
            elif h == "## Out-of-Scope":
                parts.append(f"{h}\n- SCOPE-OUT-001 admin UI\n")
            else:
                parts.append(f"{h}\n- real content\n")
        with tempfile.TemporaryDirectory() as tmp:
            result = self.check_quality_gate(Path(tmp), self.Stage.REQUIREMENT_BRIEF, self.tier, [], "\n".join(parts))
        self.assertFalse(any("native trace ID" in i for i in result.issues))

    def test_malformed_trace_id_fails(self):
        import tempfile
        from pathlib import Path
        from tools.workflow_cli.stage_schema import required_headings
        from tools.workflow_cli.models import TierBase
        parts = ["# Spec"]
        for h in required_headings(self.Stage.SPEC, TierBase.STANDARD):
            parts.append(f"{h}\nSPEC-auth-1 malformed id\n")
        with tempfile.TemporaryDirectory() as tmp:
            result = self.check_quality_gate(Path(tmp), self.Stage.SPEC, self.tier, [], "\n".join(parts))
        self.assertFalse(result.passed)
        self.assertTrue(any("Malformed trace ID" in i for i in result.issues))
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_gates.py -k "empty_body or native_spec_id or malformed_trace_id" -v`
Expected: FAIL — the current R2 gate checks only heading presence and placeholders.

- [ ] **Step 3: Implement required-body and ID-pattern validation**

Add near the placeholder patterns in `gates.py`:

```python
_VALID_TRACE_ID_RE = re.compile(
    r"^(?:REQ|RISK|DES|SPEC)-[A-Z]+-\d+$|^SCOPE-(?:IN|OUT)-\d+$|^PLAN-TASK-\d+$"
)
_TRACE_ID_CANDIDATE_RE = re.compile(
    r"\b(?:REQ|RISK|DES|SPEC)-[A-Za-z0-9_-]+|SCOPE-(?:IN|OUT)-[A-Za-z0-9_-]+|PLAN-TASK-[A-Za-z0-9_-]+"
)
_STAGE_NATIVE_HEADING_PATTERNS = {
    Stage.RISK_DISCOVERY: re.compile(r"(?m)^#+\s+.*\bRISK-[A-Z]+-\d+\b"),
    Stage.DESIGN: re.compile(r"(?m)^#+\s+.*\bDES-[A-Z]+-\d+\b"),
    Stage.SPEC: re.compile(r"(?m)^#+\s+.*\bSPEC-[A-Z]+-\d+\b"),
}


def _section_body(content: str, heading: str) -> str:
    out, capture = [], False
    for line in content.splitlines():
        if line.strip() == heading:
            capture = True
            continue
        if capture and line.lstrip().startswith("#"):
            break
        if capture:
            out.append(line)
    return "\n".join(out)


def _has_meaningful_body(text: str) -> bool:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("<!--"):
            return True
    return False
```

Extend `_check_stage_schema` after the required-heading loop and before the placeholder loop:

```python
    for heading in required_headings(stage, tier.base):
        body = _section_body(content, heading)
        if not _has_meaningful_body(body):
            issues.append(f"Required section {heading!r} must contain non-placeholder body content.")

    for token in _TRACE_ID_CANDIDATE_RE.findall(content):
        if not _VALID_TRACE_ID_RE.fullmatch(token):
            issues.append(f"Malformed trace ID {token!r}; use REQ-AREA-001, SPEC-AREA-001, SCOPE-IN-001, or PLAN-TASK-001 style IDs.")

    native = _STAGE_NATIVE_HEADING_PATTERNS.get(stage)
    if native is not None and not native.search(content):
        issues.append(f"Stage {stage.value!r} must define at least one native trace ID in a heading matching {native.pattern!r}.")
```

Notes:
- `PLAN-TASK-*` field and numbering semantics stay in R5.
- `requirement_brief` scope definitions are section entries, not headings; R8 later enforces every meaningful `## In-Scope` / `## Out-of-Scope` entry has the correct `SCOPE-IN-*` / `SCOPE-OUT-*` ID. R2 only rejects malformed trace-ID tokens in the brief.
- For RISK/DESIGN/SPEC, native IDs in ordinary body/list text may be references, but they do not satisfy the definition requirement. For `requirement_brief`, `SCOPE-*` definitions come from R8-validated scope-section entries. This keeps R2 aligned with R3 trace definition semantics.

- [ ] **Step 4: Run tests to verify pass**

Run: `python -m pytest tests/test_gates.py -k StageSchemaGate -v`
Expected: PASS, including heading, body, placeholder, and ID-pattern cases.

- [ ] **Step 5: Commit**

```bash
git add tools/workflow_cli/gates.py tests/test_gates.py
git commit -m "feat(r2p): validate required section bodies and stage IDs (R2)"
```

---

## Phase 5 — R4: repo-path wiring + lightweight Project Context Pack + local link ingest

**Why fifth:** R5 (PLAN executability) needs real repo facts to anchor file/config/entry references; this phase produces them. Per the spec, **no AST symbol extraction** in v1 — only files/config/entrypoints get hard-checkable facts; symbols stay advisory (deferred).

### Design Contract — `ProjectContextPack` + artifact files

Written to `.req-to-plan/<work-id>/02-project-context.{json,md}`. JSON is canonical; MD is the human/agent-readable summary. v1 fields (no symbols):

```python
# tools/workflow_cli/context_pack.py
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path

from tools.workflow_cli.repo_baseline import SKIP_DIRS, scan_repo_baseline

_CONFIG_NAMES = {
    "pyproject.toml", "setup.cfg", "tox.ini", "Cargo.toml", "go.mod",
    "tsconfig.json", ".env.example", "Dockerfile", "Makefile", "requirements.txt",
}
_ENTRYPOINT_HINTS = ("main.py", "__main__.py", "index.ts", "index.js", "app.py", "server.ts")


@dataclass
class ProjectContextPack:
    repo_root: str = "."
    languages: dict = field(default_factory=dict)
    package_managers: list = field(default_factory=list)
    test_commands: list = field(default_factory=list)
    entrypoints: list = field(default_factory=list)
    dependencies: list = field(default_factory=list)  # [{name, version, ecosystem}]
    config_files: list = field(default_factory=list)
    source_dirs: list = field(default_factory=list)


def build_context_pack(repo_path: Path) -> ProjectContextPack:
    repo_path = Path(repo_path)
    baseline = scan_repo_baseline(repo_path)
    pack = ProjectContextPack(repo_root=str(repo_path), languages=dict(baseline.language_breakdown))

    pkg = repo_path / "package.json"
    if pkg.exists():
        try:
            data = json.loads(pkg.read_text(encoding="utf-8"))
            pack.package_managers.append("npm")
            test = (data.get("scripts") or {}).get("test")
            if test:
                pack.test_commands.append(test)
            for name, ver in (data.get("dependencies") or {}).items():
                pack.dependencies.append({"name": name, "version": ver, "ecosystem": "npm"})
        except (ValueError, OSError):
            pass

    req = repo_path / "requirements.txt"
    if req.exists():
        pack.package_managers.append("pip")
        for line in req.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith(("#", "-")):
                pack.dependencies.append({"name": line, "version": "", "ecosystem": "pip"})
        if not pack.test_commands:
            pack.test_commands.append("python -m pytest")

    for root, dirs, files in os.walk(repo_path):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith(".")]
        rel_root = Path(root).relative_to(repo_path)
        for fname in files:
            rel = str(rel_root / fname) if str(rel_root) != "." else fname
            if fname in _CONFIG_NAMES:
                pack.config_files.append(rel)
            if fname in _ENTRYPOINT_HINTS:
                pack.entrypoints.append(rel)

    pack.source_dirs = sorted(
        p.name for p in repo_path.iterdir()
        if p.is_dir() and p.name not in SKIP_DIRS and not p.name.startswith(".")
    )
    return pack


def to_json(pack: ProjectContextPack) -> str:
    return json.dumps(asdict(pack), indent=2, ensure_ascii=False)


def to_markdown(pack: ProjectContextPack) -> str:
    return (
        "# Project Context Pack\n\n"
        f"- repo_root: `{pack.repo_root}`\n"
        f"- languages: {pack.languages}\n"
        f"- package_managers: {', '.join(pack.package_managers) or 'none'}\n"
        f"- test_commands: {pack.test_commands or 'none'}\n"
        f"- entrypoints: {pack.entrypoints or 'none'}\n"
        f"- config_files: {pack.config_files or 'none'}\n"
        f"- dependencies: {len(pack.dependencies)} found\n"
        f"- source_dirs: {pack.source_dirs}\n"
    )


def write_context_pack(pack: ProjectContextPack, run_dir: Path) -> tuple[Path, Path]:
    json_path = run_dir / "02-project-context.json"
    md_path = run_dir / "02-project-context.md"
    json_path.write_text(to_json(pack), encoding="utf-8")
    md_path.write_text(to_markdown(pack), encoding="utf-8")
    return md_path, json_path
```

### Task R4.1: `ProjectContextPack` + `build_context_pack`

**Files:**
- Create: `tools/workflow_cli/context_pack.py` (dataclass + `build_context_pack` portion)
- Test: `tests/test_context_pack.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_context_pack.py
import json
import tempfile
import unittest
from pathlib import Path


class TestBuildContextPack(unittest.TestCase):
    def _make_repo(self, tmp: Path):
        (tmp / "package.json").write_text(
            json.dumps({"scripts": {"test": "jest"}, "dependencies": {"react": "^18.0.0"}}),
            encoding="utf-8",
        )
        (tmp / "requirements.txt").write_text("pyyaml>=6.0\n# comment\n", encoding="utf-8")
        (tmp / "src").mkdir()
        (tmp / "src" / "main.py").write_text("print('hi')\n", encoding="utf-8")

    def test_detects_managers_test_commands_and_deps(self):
        from tools.workflow_cli.context_pack import build_context_pack
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            self._make_repo(tmp)
            pack = build_context_pack(tmp)
        self.assertIn("npm", pack.package_managers)
        self.assertIn("pip", pack.package_managers)
        self.assertIn("jest", pack.test_commands)
        names = {d["name"] for d in pack.dependencies}
        self.assertIn("react", names)
        self.assertTrue(any(d["name"].startswith("pyyaml") for d in pack.dependencies))

    def test_finds_entrypoint_and_source_dir(self):
        from tools.workflow_cli.context_pack import build_context_pack
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            self._make_repo(tmp)
            pack = build_context_pack(tmp)
        self.assertTrue(any(e.endswith("main.py") for e in pack.entrypoints))
        self.assertIn("src", pack.source_dirs)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_context_pack.py -v`
Expected: FAIL — module missing.

- [ ] **Step 3: Create `context_pack.py`**

Use the Design Contract content above (dataclass + `build_context_pack`; the writer functions can be added now too — they are tested in R4.2).

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_context_pack.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tools/workflow_cli/context_pack.py tests/test_context_pack.py
git commit -m "feat(r2p): build lightweight Project Context Pack from repo (R4)"
```

### Task R4.2: Context Pack writers (JSON canonical + MD summary)

**Files:**
- Modify: `tools/workflow_cli/context_pack.py` (ensure `to_json` / `to_markdown` / `write_context_pack` present)
- Test: `tests/test_context_pack.py`

- [ ] **Step 1: Write the failing test**

```python
# add to tests/test_context_pack.py
class TestContextPackWriters(unittest.TestCase):
    def test_write_produces_both_files_and_valid_json(self):
        from tools.workflow_cli.context_pack import build_context_pack, write_context_pack
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            (tmp / "requirements.txt").write_text("pyyaml>=6.0\n", encoding="utf-8")
            run_dir = tmp / "run"
            run_dir.mkdir()
            pack = build_context_pack(tmp)
            md_path, json_path = write_context_pack(pack, run_dir)
            self.assertTrue(md_path.exists())
            self.assertTrue(json_path.exists())
            data = json.loads(json_path.read_text(encoding="utf-8"))
            self.assertEqual(data["repo_root"], str(tmp))
            self.assertIn("dependencies", data)
```

- [ ] **Step 2: Run test to verify it fails (or passes if writers already added in R4.1)**

Run: `python -m pytest tests/test_context_pack.py -k Writers -v`
Expected: FAIL if writers not yet present; if you added them in R4.1 Step 3, this passes — either way, keep the test.

- [ ] **Step 3: Ensure writers exist**

Confirm `to_json`, `to_markdown`, `write_context_pack` match the Design Contract.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_context_pack.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tools/workflow_cli/context_pack.py tests/test_context_pack.py
git commit -m "feat(r2p): write Context Pack as canonical JSON + MD summary (R4)"
```

### Task R4.3: `context-build` CLI subcommand

**Files:**
- Modify: `tools/workflow_cli/cli.py` (add `_cmd_context_build` + `_register_context_commands`, registered alongside the other `_register_*` calls in the parser builder)
- Test: `tests/test_cli.py`

- [ ] **Step 1: Write the failing test**

```python
# add to tests/test_cli.py
import json
import tempfile
import unittest
from pathlib import Path


class TestContextBuildCommand(unittest.TestCase):
    def test_context_build_writes_pack_into_run_dir(self):
        from tools.workflow_cli.cli import main
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            repo = base / "repo"
            repo.mkdir()
            (repo / "requirements.txt").write_text("pyyaml>=6.0\n", encoding="utf-8")
            run_dir = base / ".req-to-plan" / "WF-20260605-ctx"
            run_dir.mkdir(parents=True)
            with self.assertRaises(SystemExit) as ctx:
                main([
                    "context-build",
                    "--work-id", "WF-20260605-ctx",
                    "--repo-path", str(repo),
                    "--base-path", str(base),
                ])
            self.assertEqual(ctx.exception.code, 0)
            data = json.loads((run_dir / "02-project-context.json").read_text(encoding="utf-8"))
            self.assertIn("pip", data["package_managers"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_cli.py -k ContextBuild -v`
Expected: FAIL — `invalid choice: 'context-build'`.

- [ ] **Step 3: Implement the subcommand**

Add the handler in `cli.py` (mirror the `--base-path` resolution used by other run commands):

```python
def _cmd_context_build(args):
    from tools.workflow_cli.context_pack import build_context_pack, write_context_pack
    base_path = Path(args.base_path) if args.base_path else Path.cwd()
    run_dir = base_path / ".req-to-plan" / args.work_id
    if not run_dir.exists():
        print_and_exit(format_error(f"run not found: {args.work_id}", exit_code=EXIT_NOT_FOUND), EXIT_NOT_FOUND)
    pack = build_context_pack(Path(args.repo_path))
    md_path, json_path = write_context_pack(pack, run_dir)
    print_and_exit(
        format_success(
            {"work_id": args.work_id, "context_md": str(md_path), "context_json": str(json_path)},
            message="Context Pack built",
        ),
        EXIT_OK,
    )


def _register_context_commands(subparsers):
    p = subparsers.add_parser("context-build", help="Build Project Context Pack for a run")
    p.add_argument("--work-id", required=True)
    p.add_argument("--repo-path", required=True)
    p.add_argument("--base-path", default=None)
    p.set_defaults(func=_cmd_context_build)
```

Then register it: find where the parser builder calls `_register_run_commands(subparsers)` (grep `_register_run_commands(`) and add `_register_context_commands(subparsers)` next to it. Confirm `EXIT_NOT_FOUND` is already imported in `cli.py` (it is used by other handlers); if not, import it from `tools.workflow_cli.output`.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_cli.py -k ContextBuild -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tools/workflow_cli/cli.py tests/test_cli.py
git commit -m "feat(r2p): add context-build subcommand (R4)"
```

### Task R4.4: Expose `--repo-path` on the `r2p-start` shortcut

**Files:**
- Modify: `tools/workflow_cli/agent_shortcuts.py` (add `--repo-path` to `p_start`; extract `_build_run_start_args`; pass repo path through)
- Modify: `tools/workflow_cli/agent_templates/claude/commands/r2p-start.md` (+ `gemini/commands/r2p-start.toml`, `codex/skills/r2p-start/SKILL.md`) — document the flag
- Test: `tests/test_agent_shortcuts.py`

- [ ] **Step 1: Write the failing test**

```python
# add to tests/test_agent_shortcuts.py
class TestRunStartArgs(unittest.TestCase):
    def test_repo_path_is_forwarded_to_run_start(self):
        from tools.workflow_cli.agent_shortcuts import _build_run_start_args
        args = _build_run_start_args("WF-x", "do thing", None, repo_path=".")
        self.assertIn("--repo-path", args)
        self.assertEqual(args[args.index("--repo-path") + 1], ".")

    def test_repo_path_absent_when_not_given(self):
        from tools.workflow_cli.agent_shortcuts import _build_run_start_args
        args = _build_run_start_args("WF-x", "do thing", None, repo_path=None)
        self.assertNotIn("--repo-path", args)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_agent_shortcuts.py -k RunStartArgs -v`
Expected: FAIL — `_build_run_start_args` not defined.

- [ ] **Step 3: Extract the helper, add the arg, thread it through**

Add the helper and use it in `_cmd_start` (replacing the inline `run_args = [...]` block at lines ~390-393):

```python
def _build_run_start_args(work_id, requirement, file_path, repo_path=None):
    if file_path is not None:
        args = ["run-start", "--work-id", work_id, "--requirement-file", str(file_path)]
    else:
        args = ["run-start", "--work-id", work_id, "--requirement", requirement]
    if repo_path:
        args += ["--repo-path", str(repo_path)]
    return args
```

In `_cmd_start`:

```python
    run_args = _build_run_start_args(work_id, requirement, file_path, getattr(ns, "repo_path", None))
```

In the `p_start` parser registration (near line 709), add:

```python
    p_start.add_argument("--repo-path", dest="repo_path", default=None)
```

Then add one line to each `r2p-start` template documenting: `Optionally pass --repo-path <dir> to ground tier and the Project Context Pack in real repo facts.`

- [ ] **Step 4: Run tests to verify pass (unit + no regression)**

Run: `python -m pytest tests/test_agent_shortcuts.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tools/workflow_cli/agent_shortcuts.py tools/workflow_cli/agent_templates/
git commit -m "feat(r2p): expose --repo-path on r2p-start shortcut (R4)"
```

### Task R4.5: Wire Context Pack + local link expansion into `run-start`; enrich seeding

**Files:**
- Modify: `tools/workflow_cli/cli.py` (`_cmd_run_start`: build pack + expand local links when `--repo-path` given)
- Modify: `tools/workflow_cli/agent_shortcuts.py` (`_seed_for_stage` gains a `context_summary` param; `needs_content` branch reads `02-project-context.md`)
- Test: `tests/test_cli.py`, `tests/test_agent_shortcuts.py`

- [ ] **Step 1: Write the failing tests**

```python
# add to tests/test_cli.py
class TestRunStartBuildsContextPack(unittest.TestCase):
    def test_run_start_with_repo_path_writes_context_pack(self):
        from tools.workflow_cli.cli import main
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            repo = base / "repo"
            repo.mkdir()
            (repo / "requirements.txt").write_text("pyyaml>=6.0\n", encoding="utf-8")
            with self.assertRaises(SystemExit) as ctx:
                main([
                    "run-start",
                    "--work-id", "WF-20260605-rp",
                    "--requirement", "add rate limiting",
                    "--repo-path", str(repo),
                    "--base-path", str(base),
                ])
            self.assertEqual(ctx.exception.code, 0)
            pack = base / ".req-to-plan" / "WF-20260605-rp" / "02-project-context.json"
            self.assertTrue(pack.exists())

    def test_run_start_with_repo_path_persists_local_and_http_link_context(self):
        from tools.workflow_cli.cli import main
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            repo = base / "repo"
            docs = repo / "docs"
            docs.mkdir(parents=True)
            (repo / "requirements.txt").write_text("pyyaml>=6.0\n", encoding="utf-8")
            (docs / "context.md").write_text("local architecture note", encoding="utf-8")
            requirement = "Use docs/context.md and https://example.com/spec"
            with self.assertRaises(SystemExit) as ctx:
                main([
                    "run-start",
                    "--work-id", "WF-20260605-links",
                    "--requirement", requirement,
                    "--repo-path", str(repo),
                    "--base-path", str(base),
                ])
            self.assertEqual(ctx.exception.code, 0)
            intake = (base / ".req-to-plan" / "WF-20260605-links" / "01-intake-brief.md").read_text(encoding="utf-8")
            self.assertIn("docs/context.md", intake)
            self.assertIn("local architecture note", intake)
            self.assertIn("https://example.com/spec", intake)
            self.assertIn("URL fetching disabled", intake)
```

```python
# add to tests/test_agent_shortcuts.py (TestSeedForStage)
    def test_seed_includes_context_summary_when_present(self):
        from tools.workflow_cli.agent_shortcuts import _seed_for_stage
        from tools.workflow_cli.models import Stage, TierBase, TierEstimate
        tier = TierEstimate(base=TierBase.LIGHT, modifiers=frozenset())
        seed = _seed_for_stage(Stage.DESIGN, tier, context_summary="languages: {'Python': 100}")
        self.assertIn("Project Context", seed)
        self.assertIn("'Python'", seed)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_cli.py -k "ContextPack or link_context" tests/test_agent_shortcuts.py -k context_summary -v`
Expected: FAIL — pack/link context not written; `_seed_for_stage` has no `context_summary` param.

- [ ] **Step 3: Implement both wirings**

In `cli.py` `_cmd_run_start`, immediately after the tier estimation block (after line ~218), add:

```python
    if repo_path is not None and repo_path.exists():
        from tools.workflow_cli.context_pack import build_context_pack, write_context_pack
        from tools.workflow_cli.link_expander import expand_links
        write_context_pack(build_context_pack(repo_path), run_dir)
        link_results = expand_links(requirement, base_path=repo_path, fetch_urls=False)
        if link_results:
            evidence.linked_context = "\n".join(
                f"- {r.url}: {r.status.value}"
                + (f"\n  preview: {r.content_preview}" if r.content_preview else "")
                + (f"\n  error: {r.error}" if r.error else "")
                for r in link_results
            )
```

This makes local relative link content visible through the existing `01-intake-brief.md` evidence block, while HTTP links are explicitly recorded as unexpanded because `fetch_urls=False` returns `URL fetching disabled`.

In `agent_shortcuts.py`, extend `_seed_for_stage`:

```python
def _seed_for_stage(stage, tier, upstream_summary: str = "", context_summary: str = "") -> str:
    from tools.workflow_cli.stage_templates import template_for
    base = tier.base if tier is not None else None
    text = template_for(stage, base) if base is not None else ""
    if upstream_summary.strip():
        text += "\n## Upstream Summary (read-only)\n" + upstream_summary.strip() + "\n"
    if context_summary.strip():
        text += "\n## Project Context (read-only)\n" + context_summary.strip() + "\n"
    return text
```

In the `needs_content` branch, read the pack summary if present and pass it:

```python
                pack_md = run_path.parent / "02-project-context.md"
                context_summary = pack_md.read_text(encoding="utf-8") if pack_md.exists() else ""
                seed = _seed_for_stage(record.current_stage, record.tier_locked, upstream, context_summary)
```

- [ ] **Step 4: Run tests to verify pass**

Run: `python -m pytest tests/test_cli.py tests/test_agent_shortcuts.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tools/workflow_cli/cli.py tools/workflow_cli/agent_shortcuts.py tests/test_cli.py tests/test_agent_shortcuts.py
git commit -m "feat(r2p): build Context Pack + ingest local links on run-start; enrich seeding (R4)"
```

---

## Phase 6 — R3: Cross-stage trace coverage

**Why sixth:** R8 (scope freeze) hard-depends on trace closure, and R5 (PLAN gate) reuses the SPEC-coverage check. Trace is **derived on demand** from artifacts already on disk — no hand-maintained matrix file.

### Design Contract — `trace.py`

ID namespace and edge semantics are fixed by the source spec. v1 approximates "closure" as "referenced by the required downstream stage". An ID is **defined** when it appears in a heading, with one explicit exception: `SCOPE-IN-*` and `SCOPE-OUT-*` IDs are also definitions when they appear as entries under the Requirement Brief `## In-Scope` / `## Out-of-Scope` sections. IDs are **referenced** when they appear in body text of another stage or outside their defining location.

```python
# tools/workflow_cli/trace.py
"""Cross-stage trace coverage (R3). Derived from artifacts; no stored matrix."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from tools.workflow_cli.models import STAGE_ARTIFACT_MAP, Stage

# REQ-AUTH-001 / RISK-SEC-001 / DES-AUTH-001 / SPEC-AUTH-001 / SCOPE-IN-001 / SCOPE-OUT-001 / PLAN-TASK-001
_ID_RE = re.compile(r"(?:REQ|RISK|DES|SPEC)-[A-Z]+-\d+|SCOPE-(?:IN|OUT)-\d+|PLAN-TASK-\d+")


@dataclass
class TraceModel:
    defined: dict = field(default_factory=dict)     # id -> stage value where first defined
    referenced: dict = field(default_factory=dict)  # id -> set of stage values referencing it


def _scope_ids_defined_in_brief(stage: Stage, content: str) -> set[str]:
    """SCOPE-* ids are defined by bullet entries in the brief scope sections."""
    if stage != Stage.REQUIREMENT_BRIEF:
        return set()
    ids: set[str] = set()
    capture = False
    for line in content.splitlines():
        stripped = line.strip()
        if stripped in {"## In-Scope", "## Out-of-Scope"}:
            capture = True
            continue
        if capture and line.lstrip().startswith("#"):
            capture = False
        if capture:
            ids.update(
                m.group(0) for m in _ID_RE.finditer(line)
                if m.group(0).startswith("SCOPE-")
            )
    return ids


def _artifact_text(run_dir: Path, stage: Stage) -> str:
    path = run_dir / STAGE_ARTIFACT_MAP[stage]
    return path.read_text(encoding="utf-8") if path.exists() else ""


def _plan_task_bodies(plan_content: str):
    starts = [m.start() for m in re.finditer(r"(?m)^###\s+PLAN-TASK-\d+\b", plan_content)]
    for index, start in enumerate(starts):
        end = starts[index + 1] if index + 1 < len(starts) else len(plan_content)
        yield plan_content[start:end]


def _plan_task_field_value(body: str, field: str) -> str:
    m = re.search(rf"(?m)^{re.escape(field)}:\s*(.*)$", body)
    return m.group(1).strip() if m else ""


def plan_consumed_spec_ids(run_dir: Path) -> set[str]:
    """SPEC IDs consumed by PLAN-TASK Spec References fields, not merely mentioned."""
    plan = _artifact_text(run_dir, Stage.PLAN)
    consumed: set[str] = set()
    for body in _plan_task_bodies(plan):
        consumed.update(m.group(0) for m in _ID_RE.finditer(_plan_task_field_value(body, "Spec References"))
                        if m.group(0).startswith("SPEC-"))
    return consumed


def _spec_blocks(spec_content: str) -> dict[str, str]:
    starts = list(re.finditer(r"(?m)^#+\s+(SPEC-[A-Z]+-\d+)\b", spec_content))
    blocks: dict[str, str] = {}
    for index, match in enumerate(starts):
        end = starts[index + 1].start() if index + 1 < len(starts) else len(spec_content)
        blocks[match.group(1)] = spec_content[match.start():end]
    return blocks


def _risk_blocks(content: str) -> dict[str, str]:
    starts = list(re.finditer(r"(?m)^#+\s+(RISK-[A-Z]+-\d+)\b", content))
    blocks: dict[str, str] = {}
    for index, match in enumerate(starts):
        end = starts[index + 1].start() if index + 1 < len(starts) else len(content)
        blocks[match.group(1)] = content[match.start():end]
    return blocks


def scope_in_not_closed(run_dir: Path) -> list[str]:
    """SCOPE-IN closes only when a PLAN-TASK carries it or consumes a SPEC carrying it."""
    model = build_trace(run_dir)
    plan_text = _artifact_text(run_dir, Stage.PLAN)
    plan_task_text = "\n".join(_plan_task_bodies(plan_text))
    spec_blocks = _spec_blocks(_artifact_text(run_dir, Stage.SPEC))
    consumed_specs = plan_consumed_spec_ids(run_dir)
    issues: list[str] = []
    for id_ in sorted(i for i in model.defined if i.startswith("SCOPE-IN-")):
        if id_ in plan_task_text:
            continue
        # v1 path derivation: a SPEC block carries the scope item and that SPEC is consumed.
        # This is conservative without a hand-maintained edge matrix.
        if any(id_ in spec_blocks.get(spec_id, "") for spec_id in consumed_specs):
            continue
        issues.append(id_)
    return issues


def risk_ids_not_closed(run_dir: Path) -> list[str]:
    """RISK-* blocks must declare Status: mitigated|deferred|out_of_scope.

    v1 limitation: blocks are split by RISK-* headings over the concatenated
    artifacts, so a block runs until the next RISK heading, and Status must be
    one of the three exact tokens. This is conservative but coarse; refine the
    block boundaries if false positives surface in practice.
    """
    model = build_trace(run_dir)
    content = "\n".join(_artifact_text(run_dir, s) for s in STAGE_ARTIFACT_MAP)
    blocks = _risk_blocks(content)
    open_risks: list[str] = []
    for id_ in sorted(i for i in model.defined if i.startswith("RISK-")):
        if not re.search(r"(?m)^Status:\s*(mitigated|deferred|out_of_scope)\s*$", blocks.get(id_, "")):
            open_risks.append(id_)
    return open_risks


def build_trace(run_dir: Path) -> TraceModel:
    model = TraceModel()
    for stage, filename in STAGE_ARTIFACT_MAP.items():
        path = run_dir / filename
        if not path.exists():
            continue
        content = path.read_text(encoding="utf-8")
        heading_ids: set[str] = set()
        for line in content.splitlines():
            if line.lstrip().startswith("#"):
                heading_ids.update(m.group(0) for m in _ID_RE.finditer(line))
        definition_ids = heading_ids | _scope_ids_defined_in_brief(stage, content)
        all_ids = {m.group(0) for m in _ID_RE.finditer(content)}
        for id_ in definition_ids:
            model.defined.setdefault(id_, stage.value)
        for id_ in all_ids:
            if id_ in definition_ids and model.defined.get(id_) == stage.value:
                continue  # this occurrence is the definition
            model.referenced.setdefault(id_, set()).add(stage.value)
    return model


def spec_ids_not_consumed(run_dir: Path) -> list[str]:
    """SPEC-* defined but not consumed by PLAN-TASK Spec References fields."""
    model = build_trace(run_dir)
    consumed = plan_consumed_spec_ids(run_dir)
    return sorted(
        id_ for id_, _ in model.defined.items()
        if id_.startswith("SPEC-") and id_ not in consumed
    )


def check_trace_closure(run_dir: Path) -> list[str]:
    model = build_trace(run_dir)
    issues: list[str] = []
    for id_ in spec_ids_not_consumed(run_dir):
        issues.append(f"SPEC {id_} is not consumed by any PLAN-TASK (coverage gap).")
    for id_ in scope_in_not_closed(run_dir):
        issues.append(f"In-scope item {id_} is not carried into PLAN consumption (scope not closed).")
    for id_ in risk_ids_not_closed(run_dir):
        issues.append(f"Risk {id_} is not mitigated, deferred, or marked out-of-scope (risk not closed).")
    return issues
```

### Task R3.1: `build_trace` + `spec_ids_not_consumed`

**Files:**
- Create: `tools/workflow_cli/trace.py`
- Test: `tests/test_trace.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_trace.py
import tempfile
import unittest
from pathlib import Path
from tools.workflow_cli.models import Stage, STAGE_ARTIFACT_MAP


class TestTrace(unittest.TestCase):
    def _run_dir(self, tmp, spec_body, plan_body):
        run_dir = Path(tmp)
        (run_dir / STAGE_ARTIFACT_MAP[Stage.SPEC]).write_text(spec_body, encoding="utf-8")
        (run_dir / STAGE_ARTIFACT_MAP[Stage.PLAN]).write_text(plan_body, encoding="utf-8")
        return run_dir

    def test_spec_consumed_by_plan_has_no_gap(self):
        from tools.workflow_cli.trace import spec_ids_not_consumed
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = self._run_dir(
                tmp,
                "## SPEC-AUTH-001 login\nbehavior\n",
                "### PLAN-TASK-001\nSpec References: SPEC-AUTH-001\n",
            )
            self.assertEqual(spec_ids_not_consumed(run_dir), [])

    def test_spec_not_referenced_by_plan_is_a_gap(self):
        from tools.workflow_cli.trace import spec_ids_not_consumed
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = self._run_dir(
                tmp,
                "## SPEC-AUTH-001 login\nbehavior\n",
                "### PLAN-TASK-001\nSpec References: SPEC-OTHER-999\n",
            )
            self.assertEqual(spec_ids_not_consumed(run_dir), ["SPEC-AUTH-001"])

    def test_spec_mentioned_outside_plan_task_is_still_a_gap(self):
        from tools.workflow_cli.trace import spec_ids_not_consumed
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = self._run_dir(
                tmp,
                "## SPEC-AUTH-001 login\nbehavior\n",
                "## Notes\nMentions SPEC-AUTH-001\n\n### PLAN-TASK-001\nSpec References: SPEC-OTHER-999\n",
            )
            self.assertEqual(spec_ids_not_consumed(run_dir), ["SPEC-AUTH-001"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_trace.py -v`
Expected: FAIL — module missing.

- [ ] **Step 3: Create `trace.py`**

Use the Design Contract content above.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_trace.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tools/workflow_cli/trace.py tests/test_trace.py
git commit -m "feat(r2p): derive cross-stage trace + SPEC-coverage check (R3)"
```

### Task R3.2: `check_trace_closure` — SPEC coverage + SCOPE-IN closure

**Files:**
- Modify: `tools/workflow_cli/trace.py` (ensure `check_trace_closure` present)
- Test: `tests/test_trace.py`

- [ ] **Step 1: Write the failing test**

```python
# add to tests/test_trace.py
    def test_scope_in_not_carried_downstream_is_a_gap(self):
        from tools.workflow_cli.trace import check_trace_closure
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            (run_dir / STAGE_ARTIFACT_MAP[Stage.REQUIREMENT_BRIEF]).write_text(
                "## In-Scope\n- SCOPE-IN-001 rate limit per IP\n", encoding="utf-8")
            (run_dir / STAGE_ARTIFACT_MAP[Stage.SPEC]).write_text(
                "## Behavior Contracts\nno scope ref here\n", encoding="utf-8")
            issues = check_trace_closure(run_dir)
            self.assertTrue(any("SCOPE-IN-001" in i for i in issues))

    def test_scope_in_carried_into_consumed_spec_closes(self):
        from tools.workflow_cli.trace import check_trace_closure
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            (run_dir / STAGE_ARTIFACT_MAP[Stage.REQUIREMENT_BRIEF]).write_text(
                "## In-Scope\n- SCOPE-IN-001 rate limit per IP\n", encoding="utf-8")
            (run_dir / STAGE_ARTIFACT_MAP[Stage.SPEC]).write_text(
                "## SPEC-RATE-001\nimplements SCOPE-IN-001\n", encoding="utf-8")
            (run_dir / STAGE_ARTIFACT_MAP[Stage.PLAN]).write_text(
                "## Tasks\n### PLAN-TASK-001\nSpec References: SPEC-RATE-001\n", encoding="utf-8")
            issues = check_trace_closure(run_dir)
            self.assertFalse(any("SCOPE-IN-001" in i for i in issues))

    def test_scope_in_carried_only_to_unconsumed_spec_is_a_gap(self):
        from tools.workflow_cli.trace import check_trace_closure
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            (run_dir / STAGE_ARTIFACT_MAP[Stage.REQUIREMENT_BRIEF]).write_text(
                "## In-Scope\n- SCOPE-IN-001 rate limit per IP\n", encoding="utf-8")
            (run_dir / STAGE_ARTIFACT_MAP[Stage.SPEC]).write_text(
                "## SPEC-RATE-001\nimplements SCOPE-IN-001\n", encoding="utf-8")
            (run_dir / STAGE_ARTIFACT_MAP[Stage.PLAN]).write_text(
                "## Tasks\n### PLAN-TASK-001\nSpec References: SPEC-OTHER-999\n", encoding="utf-8")
            issues = check_trace_closure(run_dir)
            self.assertTrue(any("SCOPE-IN-001" in i for i in issues))

    def test_unclosed_risk_is_a_gap(self):
        from tools.workflow_cli.trace import check_trace_closure
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            (run_dir / STAGE_ARTIFACT_MAP[Stage.RISK_DISCOVERY]).write_text(
                "## RISK-SEC-001 token leak\n", encoding="utf-8")
            issues = check_trace_closure(run_dir)
            self.assertTrue(any("RISK-SEC-001" in i for i in issues))

    def test_mitigated_risk_closes(self):
        from tools.workflow_cli.trace import check_trace_closure
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            (run_dir / STAGE_ARTIFACT_MAP[Stage.RISK_DISCOVERY]).write_text(
                "## RISK-SEC-001 token leak\nStatus: mitigated\nMitigation: redact tokens\n", encoding="utf-8")
            issues = check_trace_closure(run_dir)
            self.assertFalse(any("RISK-SEC-001" in i for i in issues))

    def test_deferred_or_out_of_scope_risk_closes(self):
        from tools.workflow_cli.trace import check_trace_closure
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            (run_dir / STAGE_ARTIFACT_MAP[Stage.RISK_DISCOVERY]).write_text(
                "## RISK-OPS-001 operational runbook\nStatus: deferred\n", encoding="utf-8")
            self.assertFalse(any("RISK-OPS-001" in i for i in check_trace_closure(run_dir)))
            (run_dir / STAGE_ARTIFACT_MAP[Stage.RISK_DISCOVERY]).write_text(
                "## RISK-OPS-001 operational runbook\nStatus: out_of_scope\n", encoding="utf-8")
            self.assertFalse(any("RISK-OPS-001" in i for i in check_trace_closure(run_dir)))

    def test_needs_mitigation_wording_does_not_close_risk(self):
        from tools.workflow_cli.trace import check_trace_closure
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            (run_dir / STAGE_ARTIFACT_MAP[Stage.RISK_DISCOVERY]).write_text(
                "## RISK-SEC-001 token leak\nThis needs mitigation.\nMitigation: TBD\n", encoding="utf-8")
            issues = check_trace_closure(run_dir)
            self.assertTrue(any("RISK-SEC-001" in i for i in issues))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_trace.py -k scope_in -v`
Expected: FAIL if `check_trace_closure` not present; PASS if you already added it in R3.1 — keep the tests either way.

- [ ] **Step 3: Ensure `check_trace_closure` matches the Design Contract**

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_trace.py -v`
Expected: PASS, including SPEC field-consumption, SCOPE-IN-to-consumed-SPEC, and RISK closure cases.

- [ ] **Step 5: Commit**

```bash
git add tools/workflow_cli/trace.py tests/test_trace.py
git commit -m "feat(r2p): add SCOPE-IN downstream closure check (R3)"
```

### Task R3.3: Run trace closure inside the PLAN quality gate

**Files:**
- Modify: `tools/workflow_cli/gates.py` (`check_quality_gate`: when `stage == Stage.PLAN`, append `check_trace_closure(run_dir)` issues)
- Test: `tests/test_gates.py`

- [ ] **Step 1: Write the failing test**

```python
# add to tests/test_gates.py
class TestTraceClosureInPlanGate(unittest.TestCase):
    def test_plan_gate_fails_when_spec_uncovered(self):
        import tempfile
        from pathlib import Path
        from tools.workflow_cli.gates import check_quality_gate
        from tools.workflow_cli.models import Stage, TierBase, TierEstimate, STAGE_ARTIFACT_MAP
        tier = TierEstimate(base=TierBase.STANDARD, modifiers=frozenset())
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            (run_dir / STAGE_ARTIFACT_MAP[Stage.SPEC]).write_text(
                "## SPEC-AUTH-001 login\nbehavior\n", encoding="utf-8")
            plan = "## Tasks\n\n### PLAN-TASK-001 do thing\nSpec References: SPEC-NOPE-000\n"
            (run_dir / STAGE_ARTIFACT_MAP[Stage.PLAN]).write_text(plan, encoding="utf-8")
            result = check_quality_gate(run_dir, Stage.PLAN, tier, [], plan)
        self.assertFalse(result.passed)
        self.assertTrue(any("SPEC-AUTH-001" in i for i in result.issues))

    def test_plan_gate_accepts_structured_spec_reference_without_legacy_closure_tag(self):
        import tempfile
        from pathlib import Path
        from tools.workflow_cli.gates import check_quality_gate
        from tools.workflow_cli.models import Stage, TierBase, TierEstimate, STAGE_ARTIFACT_MAP
        tier = TierEstimate(base=TierBase.STANDARD, modifiers=frozenset())
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            (run_dir / STAGE_ARTIFACT_MAP[Stage.SPEC]).write_text(
                "## SPEC-AUTH-001 login\nbehavior\n", encoding="utf-8")
            plan = "## Tasks\n\n### PLAN-TASK-001 do thing\nSpec References: SPEC-AUTH-001\nTDD Applicable: no\n"
            (run_dir / STAGE_ARTIFACT_MAP[Stage.PLAN]).write_text(plan, encoding="utf-8")
            result = check_quality_gate(run_dir, Stage.PLAN, tier, [], plan)
        self.assertFalse(any("closure status tag" in i for i in result.issues))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_gates.py -k TraceClosureInPlanGate -v`
Expected: FAIL — gate does not run trace closure yet.

- [ ] **Step 3: Wire trace closure into the PLAN branch of `check_quality_gate`**

Inside the `if not issues:` block, make the existing upstream-ID closure check stage-aware before adding the PLAN trace closure. Replace the current unclosed-ID loop with:

```python
        unclosed = _find_ids_without_closure(artifact_content)
        if stage == Stage.PLAN:
            from tools.workflow_cli.trace import plan_consumed_spec_ids
            consumed_specs = plan_consumed_spec_ids(run_dir)
            unclosed = [
                ref_id for ref_id in unclosed
                if not (ref_id.startswith("SPEC-") and ref_id in consumed_specs)
            ]
        for ref_id in unclosed:
            issues.append(
                f"Upstream reference {ref_id!r} appears in artifact but has no closure status tag "
                f"([ADDRESSED], [DEFERRED], [N/A], [OUT-OF-SCOPE], or [CLOSED])."
            )
```

Then add (after the existing PLAN check 5):

```python
        if stage == Stage.PLAN:
            from tools.workflow_cli.trace import check_trace_closure
            issues.extend(check_trace_closure(run_dir))
```

Rationale: in PLAN, `Spec References:` is the structured closure/consumption mechanism for `SPEC-*` IDs. Other upstream IDs still require the legacy closure tags unless R3/R8 defines a more specific structured rule.

- [ ] **Step 4: Run tests to verify pass (targeted + full gate suite)**

Run: `python -m pytest tests/test_gates.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tools/workflow_cli/gates.py tests/test_gates.py
git commit -m "feat(r2p): enforce trace closure in PLAN quality gate (R3)"
```

---

## Phase 7 — R8: Requirement elicitation + scope freeze

**Why seventh:** scope must be frozen before the PLAN gate (R5) runs. R2 already requires the `## In-Scope` / `## Out-of-Scope` / `## Open Questions` *headings*; R8 adds the substance: stable-ID scope entries, real elicitation content, and CLI-mechanical scope-overflow detection. Anything semantically out of scope but not referencing a `SCOPE-OUT-*` ID is left to checkpoint review (the honest CLI boundary).

### Task R8.1: Scope freeze — In/Out-of-Scope must carry stable IDs

**Files:**
- Modify: `tools/workflow_cli/gates.py` (`_check_scope_freeze`; call it for `REQUIREMENT_BRIEF` in `check_quality_gate`)
- Test: `tests/test_gates.py`

- [ ] **Step 1: Write the failing test**

```python
# add to tests/test_gates.py
class TestScopeFreeze(unittest.TestCase):
    def setUp(self):
        from tools.workflow_cli.gates import check_quality_gate
        from tools.workflow_cli.models import Stage, TierBase, TierEstimate
        self.check = check_quality_gate
        self.Stage = Stage
        self.tier = TierEstimate(base=TierBase.STANDARD, modifiers=frozenset())

    def _brief(self, in_scope, out_scope):
        from tools.workflow_cli.stage_schema import required_headings
        from tools.workflow_cli.models import TierBase
        body = ["# Requirement Brief"]
        for h in required_headings(self.Stage.REQUIREMENT_BRIEF, TierBase.STANDARD):
            if h == "## In-Scope":
                body.append(f"{h}\n{in_scope}")
            elif h == "## Out-of-Scope":
                body.append(f"{h}\n{out_scope}")
            else:
                body.append(f"{h}\n- real content\n")
        return "\n".join(body)

    def test_in_scope_without_id_fails(self):
        import tempfile
        from pathlib import Path
        content = self._brief("- rate limit per IP (no id)", "- SCOPE-OUT-001 admin UI")
        with tempfile.TemporaryDirectory() as tmp:
            r = self.check(Path(tmp), self.Stage.REQUIREMENT_BRIEF, self.tier, [], content)
        self.assertFalse(r.passed)
        self.assertTrue(any("SCOPE-IN" in i for i in r.issues))

    def test_scope_with_ids_passes_freeze(self):
        import tempfile
        from pathlib import Path
        content = self._brief("- SCOPE-IN-001 rate limit per IP", "- SCOPE-OUT-001 admin UI")
        with tempfile.TemporaryDirectory() as tmp:
            r = self.check(Path(tmp), self.Stage.REQUIREMENT_BRIEF, self.tier, [], content)
        self.assertFalse(any("SCOPE-IN" in i or "SCOPE-OUT" in i for i in r.issues))

    def test_each_scope_entry_must_have_matching_id(self):
        import tempfile
        from pathlib import Path
        content = self._brief(
            "- SCOPE-IN-001 rate limit per IP\n- login throttling without id",
            "- SCOPE-OUT-001 admin UI\n- reporting dashboard without id",
        )
        with tempfile.TemporaryDirectory() as tmp:
            r = self.check(Path(tmp), self.Stage.REQUIREMENT_BRIEF, self.tier, [], content)
        self.assertFalse(r.passed)
        self.assertTrue(any("In-Scope" in i and "entry" in i for i in r.issues))
        self.assertTrue(any("Out-of-Scope" in i and "entry" in i for i in r.issues))

    def test_scope_ids_elsewhere_do_not_satisfy_scope_sections(self):
        import tempfile
        from pathlib import Path
        content = self._brief("- rate limit per IP (no id)", "- admin UI (no id)") + "\n\n## Appendix\nSCOPE-IN-001\nSCOPE-OUT-001\n"
        with tempfile.TemporaryDirectory() as tmp:
            r = self.check(Path(tmp), self.Stage.REQUIREMENT_BRIEF, self.tier, [], content)
        self.assertFalse(r.passed)
        self.assertTrue(any("In-Scope" in i for i in r.issues))
        self.assertTrue(any("Out-of-Scope" in i for i in r.issues))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_gates.py -k ScopeFreeze -v`
Expected: FAIL — no scope-freeze check exists.

- [ ] **Step 3: Implement `_check_scope_freeze` and call it**

```python
def _section_entries_missing_id(content: str, heading: str, id_prefix: str) -> list[str]:
    missing: list[str] = []
    pattern = re.compile(rf"\b{re.escape(id_prefix)}-\d+\b")
    for line in _section_body(content, heading).splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("<!--"):
            continue
        if not stripped.startswith(("- ", "* ")):
            continue
        if not pattern.search(stripped):
            missing.append(stripped)
    return missing


def _check_scope_freeze(stage: Stage, content: str) -> list[str]:
    """R8: brief's In/Out-of-Scope must carry stable IDs so trace can anchor them."""
    if stage != Stage.REQUIREMENT_BRIEF:
        return []
    issues: list[str] = []
    for entry in _section_entries_missing_id(content, "## In-Scope", "SCOPE-IN"):
        issues.append(f"In-Scope entry must carry a SCOPE-IN-* stable ID (R8): {entry}")
    for entry in _section_entries_missing_id(content, "## Out-of-Scope", "SCOPE-OUT"):
        issues.append(f"Out-of-Scope entry must carry a SCOPE-OUT-* stable ID (R8): {entry}")
    if not re.search(r"\bSCOPE-IN-\d+\b", _section_body(content, "## In-Scope")):
        issues.append("In-Scope must list at least one stable-ID entry (SCOPE-IN-001, ...); none found (R8).")
    if not re.search(r"\bSCOPE-OUT-\d+\b", _section_body(content, "## Out-of-Scope")):
        issues.append("Out-of-Scope must list at least one stable-ID entry (SCOPE-OUT-001, ...); none found (R8).")
    return issues
```

In `check_quality_gate`, inside `if not issues:`:

```python
        issues.extend(_check_scope_freeze(stage, artifact_content))
```

- [ ] **Step 4: Run tests to verify pass**

Run: `python -m pytest tests/test_gates.py -k ScopeFreeze -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tools/workflow_cli/gates.py tests/test_gates.py
git commit -m "feat(r2p): require stable-ID scope entries in brief (R8)"
```

### Task R8.2: Elicitation — standard brief must record assumptions or open questions

**Files:**
- Modify: `tools/workflow_cli/gates.py` (`_section_has_bullets` helper + `_check_elicitation`)
- Test: `tests/test_gates.py`

- [ ] **Step 1: Write the failing test**

```python
# add to tests/test_gates.py (TestScopeFreeze)
    def test_standard_brief_without_assumptions_or_questions_fails(self):
        import tempfile
        from pathlib import Path
        from tools.workflow_cli.stage_schema import required_headings
        from tools.workflow_cli.models import TierBase
        # All headings present, scope IDs present, but Assumptions/Open Questions are empty.
        parts = ["# Requirement Brief"]
        for h in required_headings(self.Stage.REQUIREMENT_BRIEF, TierBase.STANDARD):
            if h == "## In-Scope":
                parts.append(f"{h}\n- SCOPE-IN-001 x\n")
            elif h == "## Out-of-Scope":
                parts.append(f"{h}\n- SCOPE-OUT-001 y\n")
            elif h in ("## Assumptions", "## Open Questions"):
                parts.append(f"{h}\n")  # empty
            else:
                parts.append(f"{h}\n- content\n")
        content = "\n".join(parts)
        with tempfile.TemporaryDirectory() as tmp:
            r = self.check(Path(tmp), self.Stage.REQUIREMENT_BRIEF, self.tier, [], content)
        self.assertFalse(r.passed)
        self.assertTrue(any("assumption" in i.lower() or "open question" in i.lower() for i in r.issues))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_gates.py -k assumptions_or_questions -v`
Expected: FAIL — no elicitation check.

- [ ] **Step 3: Implement helpers and check**

`_section_body` is already defined in Task R2.3 (which lands earlier, in Phase 4) — **reuse it, do not redefine**. Add only the bullet helper and the elicitation check:

```python
def _section_has_bullets(content: str, heading: str) -> bool:
    return any(l.lstrip().startswith(("- ", "* ")) for l in _section_body(content, heading).splitlines())


def _check_elicitation(stage: Stage, tier: TierEstimate, content: str) -> list[str]:
    """R8: standard-tier brief must record at least one assumption or open question."""
    from tools.workflow_cli.models import TierBase
    if stage != Stage.REQUIREMENT_BRIEF or tier.base != TierBase.STANDARD:
        return []
    if _section_has_bullets(content, "## Assumptions") or _section_has_bullets(content, "## Open Questions"):
        return []
    return ["Standard-tier brief must record at least one assumption or open question (R8 elicitation)."]
```

In `check_quality_gate`, inside `if not issues:`:

```python
        issues.extend(_check_elicitation(stage, tier, artifact_content))
```

- [ ] **Step 4: Run tests to verify pass**

Run: `python -m pytest tests/test_gates.py -k ScopeFreeze -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tools/workflow_cli/gates.py tests/test_gates.py
git commit -m "feat(r2p): require elicitation content in standard brief (R8)"
```

### Task R8.3: Scope overflow — PLAN may not reference an out-of-scope ID

**Files:**
- Modify: `tools/workflow_cli/trace.py` (`scope_out_violations`)
- Modify: `tools/workflow_cli/gates.py` (call it in the PLAN branch)
- Test: `tests/test_trace.py`, `tests/test_gates.py`

- [ ] **Step 1: Write the failing tests**

```python
# add to tests/test_trace.py
    def test_plan_referencing_scope_out_is_a_violation(self):
        from tools.workflow_cli.trace import scope_out_violations
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            (run_dir / STAGE_ARTIFACT_MAP[Stage.REQUIREMENT_BRIEF]).write_text(
                "## Out-of-Scope\n- SCOPE-OUT-001 admin UI\n", encoding="utf-8")
            (run_dir / STAGE_ARTIFACT_MAP[Stage.PLAN]).write_text(
                "## Tasks\n### PLAN-TASK-001 build admin UI per SCOPE-OUT-001\n", encoding="utf-8")
            self.assertEqual(scope_out_violations(run_dir), ["SCOPE-OUT-001"])
```

```python
# add to tests/test_gates.py (TestTraceClosureInPlanGate)
    def test_plan_gate_fails_on_scope_overflow(self):
        import tempfile
        from pathlib import Path
        from tools.workflow_cli.gates import check_quality_gate
        from tools.workflow_cli.models import Stage, TierBase, TierEstimate, STAGE_ARTIFACT_MAP
        tier = TierEstimate(base=TierBase.STANDARD, modifiers=frozenset())
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            (run_dir / STAGE_ARTIFACT_MAP[Stage.REQUIREMENT_BRIEF]).write_text(
                "## Out-of-Scope\n- SCOPE-OUT-001 admin UI\n", encoding="utf-8")
            plan = "## Tasks\n### PLAN-TASK-001 touch SCOPE-OUT-001\n"
            (run_dir / STAGE_ARTIFACT_MAP[Stage.PLAN]).write_text(plan, encoding="utf-8")
            r = check_quality_gate(run_dir, Stage.PLAN, tier, [], plan)
        self.assertFalse(r.passed)
        self.assertTrue(any("SCOPE-OUT-001" in i for i in r.issues))
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_trace.py -k scope_out tests/test_gates.py -k scope_overflow -v`
Expected: FAIL — `scope_out_violations` not defined; gate does not check overflow.

- [ ] **Step 3: Implement and wire**

Add to `trace.py`:

```python
def scope_out_violations(run_dir: Path) -> list[str]:
    """SCOPE-OUT-* ids that the PLAN references — a scope overflow (R8)."""
    model = build_trace(run_dir)
    plan = Stage.PLAN.value
    return sorted(
        id_ for id_, stages in model.referenced.items()
        if id_.startswith("SCOPE-OUT-") and plan in stages
    )
```

In `gates.py`, in the PLAN branch where `check_trace_closure` is already called (R3.3):

```python
        if stage == Stage.PLAN:
            from tools.workflow_cli.trace import check_trace_closure, scope_out_violations
            issues.extend(check_trace_closure(run_dir))
            for sid in scope_out_violations(run_dir):
                issues.append(f"PLAN references out-of-scope item {sid}; scope overflow (R8).")
```

- [ ] **Step 4: Run tests to verify pass**

Run: `python -m pytest tests/test_trace.py tests/test_gates.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tools/workflow_cli/trace.py tools/workflow_cli/gates.py tests/test_trace.py tests/test_gates.py
git commit -m "feat(r2p): block PLAN scope overflow on out-of-scope IDs (R8)"
```

---

## Phase 8 — R5: PLAN executability static gate

**Why last:** depends on R3 (SPEC coverage, already wired in R3.3) and R4 (Context Pack `repo_root` for file anchoring). R5 adds the remaining PLAN-TASK contract checks. Reuses the existing PLAN-TASK field helpers in `gates.py` (`_plan_task_starts`, `_plan_task_field_value`, the field regex). No tier gating — these apply whenever PLAN-TASK sections exist.

### Shared helper (used by all R5 tasks)

Add to `gates.py`:

```python
def _iter_plan_task_bodies(content: str):
    starts = _plan_task_starts(content)
    for i, s in enumerate(starts):
        e = starts[i + 1] if i + 1 < len(starts) else len(content)
        yield content[s:e]
```

Use the existing `_plan_task_field_body(task_body, field)` helper for multiline fields such as `Files:` and `Skeleton:`. If the helper is missing in the local baseline, add it before R5.3; `_plan_task_field_value` is only for same-line scalar fields.

### Task R5.1: Each PLAN-TASK has Spec References + Verification; numbers are unique & contiguous

**Files:**
- Modify: `tools/workflow_cli/gates.py` (`_check_plan_task_fields`; call in PLAN branch)
- Test: `tests/test_gates.py`

- [ ] **Step 1: Write the failing test**

```python
# add to tests/test_gates.py
class TestPlanTaskFields(unittest.TestCase):
    def setUp(self):
        from tools.workflow_cli.gates import check_quality_gate
        from tools.workflow_cli.models import Stage, TierBase, TierEstimate
        self.check = check_quality_gate
        self.Stage = Stage
        self.tier = TierEstimate(base=TierBase.STANDARD, modifiers=frozenset())

    def _gate(self, plan_body):
        import tempfile
        from pathlib import Path
        from tools.workflow_cli.models import STAGE_ARTIFACT_MAP
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            # SPEC defines the id the plan references, so SPEC-coverage (R3) is satisfied.
            (run_dir / STAGE_ARTIFACT_MAP[self.Stage.SPEC]).write_text(
                "## SPEC-AUTH-001 login\n", encoding="utf-8")
            (run_dir / STAGE_ARTIFACT_MAP[self.Stage.PLAN]).write_text(plan_body, encoding="utf-8")
            return self.check(run_dir, self.Stage.PLAN, self.tier, [], plan_body)

    def test_task_missing_verification_fails(self):
        plan = ("## Tasks\n\n### PLAN-TASK-001 do it\n"
                "Spec References: SPEC-AUTH-001\n")  # no Verification
        r = self._gate(plan)
        self.assertFalse(r.passed)
        self.assertTrue(any("Verification" in i for i in r.issues))

    def test_noncontiguous_numbering_fails(self):
        plan = ("## Tasks\n\n### PLAN-TASK-001 a\nSpec References: SPEC-AUTH-001\nVerification: pytest\n"
                "\n### PLAN-TASK-003 c\nSpec References: SPEC-AUTH-001\nVerification: pytest\n")
        r = self._gate(plan)
        self.assertFalse(r.passed)
        self.assertTrue(any("contiguous" in i.lower() or "numbering" in i.lower() for i in r.issues))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_gates.py -k PlanTaskFields -v`
Expected: FAIL — no field check.

- [ ] **Step 3: Implement `_check_plan_task_fields`**

```python
def _check_plan_task_fields(content: str) -> list[str]:
    issues: list[str] = []
    numbers: list[int] = []
    for body in _iter_plan_task_bodies(content):
        m = re.match(r"###\s+PLAN-TASK-(\d+)", body.lstrip())
        num = int(m.group(1)) if m else None
        if num is not None:
            numbers.append(num)
        label = f"PLAN-TASK-{num if num is not None else '?'}"
        if not _plan_task_field_value(body, "Spec References").strip():
            issues.append(f"{label} is missing a non-empty 'Spec References:' field.")
        if not _plan_task_field_value(body, "Verification").strip():
            issues.append(f"{label} is missing a non-empty 'Verification:' field.")
    if numbers:
        if len(set(numbers)) != len(numbers):
            issues.append("PLAN-TASK numbers must be unique.")
        if sorted(numbers) != list(range(1, len(numbers) + 1)):
            issues.append("PLAN-TASK numbers must be contiguous starting at 1.")
    return issues
```

In the PLAN branch of `check_quality_gate` (after the R3/R8 block):

```python
            issues.extend(_check_plan_task_fields(artifact_content))
```

- [ ] **Step 4: Run tests to verify pass**

Run: `python -m pytest tests/test_gates.py -k PlanTaskFields -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tools/workflow_cli/gates.py tests/test_gates.py
git commit -m "feat(r2p): PLAN-TASK field + numbering checks (R5)"
```

### Task R5.2: Spec References must point at SPEC IDs defined in the SPEC artifact

**Files:**
- Modify: `tools/workflow_cli/gates.py` (`_check_spec_refs_valid`)
- Test: `tests/test_gates.py`

- [ ] **Step 1: Write the failing test**

```python
# add to tests/test_gates.py (TestPlanTaskFields)
    def test_dangling_spec_reference_fails(self):
        plan = ("## Tasks\n\n### PLAN-TASK-001 a\n"
                "Spec References: SPEC-GHOST-999\nVerification: pytest\n")
        r = self._gate(plan)  # SPEC artifact only defines SPEC-AUTH-001
        self.assertFalse(r.passed)
        self.assertTrue(any("SPEC-GHOST-999" in i for i in r.issues))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_gates.py -k dangling_spec -v`
Expected: FAIL.

- [ ] **Step 3: Implement `_check_spec_refs_valid`**

```python
def _check_spec_refs_valid(run_dir: Path, content: str) -> list[str]:
    from tools.workflow_cli.trace import build_trace
    defined_specs = {i for i in build_trace(run_dir).defined if i.startswith("SPEC-")}
    issues: list[str] = []
    for body in _iter_plan_task_bodies(content):
        refs = re.findall(r"SPEC-[A-Z]+-\d+", _plan_task_field_value(body, "Spec References"))
        for ref in refs:
            if ref not in defined_specs:
                issues.append(f"PLAN-TASK references {ref} which is not defined in the SPEC artifact.")
    return issues
```

In the PLAN branch:

```python
            issues.extend(_check_spec_refs_valid(run_dir, artifact_content))
```

- [ ] **Step 4: Run tests to verify pass**

Run: `python -m pytest tests/test_gates.py -k PlanTaskFields -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tools/workflow_cli/gates.py tests/test_gates.py
git commit -m "feat(r2p): reject dangling SPEC references in PLAN (R5)"
```

### Task R5.3: `Files:` paths hard-checked against the Context Pack `repo_root`

**Files:**
- Modify: `tools/workflow_cli/gates.py` (`_check_plan_file_refs`)
- Test: `tests/test_gates.py`

- [ ] **Step 1: Write the failing test**

```python
# add to tests/test_gates.py (TestPlanTaskFields)
    def test_files_referencing_missing_path_fails_unless_create(self):
        import json, tempfile
        from pathlib import Path
        from tools.workflow_cli.models import STAGE_ARTIFACT_MAP
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run"
            run_dir.mkdir()
            repo = Path(tmp) / "repo"
            (repo / "src").mkdir(parents=True)
            (repo / "src" / "real.py").write_text("x=1\n", encoding="utf-8")
            (run_dir / "02-project-context.json").write_text(
                json.dumps({"repo_root": str(repo)}), encoding="utf-8")
            (run_dir / STAGE_ARTIFACT_MAP[self.Stage.SPEC]).write_text(
                "## SPEC-AUTH-001 login\n", encoding="utf-8")
            # references a nonexistent file, Change Type modify -> must fail
            plan = ("## Tasks\n\n### PLAN-TASK-001 a\n"
                    "Spec References: SPEC-AUTH-001\nChange Type: modify\n"
                    "Files:\n- src/ghost.py :: f\nVerification: pytest\n")
            (run_dir / STAGE_ARTIFACT_MAP[self.Stage.PLAN]).write_text(plan, encoding="utf-8")
            r = self.check(run_dir, self.Stage.PLAN, self.tier, [], plan)
        self.assertFalse(r.passed)
        self.assertTrue(any("ghost.py" in i for i in r.issues))

    def test_files_create_type_is_exempt(self):
        import json, tempfile
        from pathlib import Path
        from tools.workflow_cli.models import STAGE_ARTIFACT_MAP
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run"
            run_dir.mkdir()
            repo = Path(tmp) / "repo"
            repo.mkdir()
            (run_dir / "02-project-context.json").write_text(
                json.dumps({"repo_root": str(repo)}), encoding="utf-8")
            (run_dir / STAGE_ARTIFACT_MAP[self.Stage.SPEC]).write_text(
                "## SPEC-AUTH-001 login\n", encoding="utf-8")
            plan = ("## Tasks\n\n### PLAN-TASK-001 a\n"
                    "Spec References: SPEC-AUTH-001\nChange Type: create\n"
                    "Files:\n- src/new.py\nVerification: pytest\n")
            (run_dir / STAGE_ARTIFACT_MAP[self.Stage.PLAN]).write_text(plan, encoding="utf-8")
            r = self.check(run_dir, self.Stage.PLAN, self.tier, [], plan)
        self.assertFalse(any("new.py" in i for i in r.issues))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_gates.py -k "missing_path or create_type" -v`
Expected: FAIL — no file-ref check.

- [ ] **Step 3: Implement `_check_plan_file_refs`**

```python
def _check_plan_file_refs(run_dir: Path, content: str) -> list[str]:
    """Hard-check Files paths against the Context Pack repo_root. create-type tasks
    are exempt; the part after '::' (a symbol) is advisory and not checked (no AST pack yet)."""
    import json
    pack_json = run_dir / "02-project-context.json"
    if not pack_json.exists():
        return []  # no ground truth -> advisory only
    try:
        repo_root = Path(json.loads(pack_json.read_text(encoding="utf-8")).get("repo_root", ""))
    except (ValueError, OSError):
        return []
    if not repo_root or not repo_root.exists():
        return []
    issues: list[str] = []
    for body in _iter_plan_task_bodies(content):
        if "create" in _plan_task_field_value(body, "Change Type").lower():
            continue
        files_field = _plan_task_field_body(body, "Files")
        for line in files_field.splitlines():
            path_part = line.split("::")[0].strip().lstrip("-").strip()
            if not path_part:
                continue
            if not (repo_root / path_part).exists():
                issues.append(
                    f"PLAN-TASK Files references missing path {path_part!r} "
                    "(mark the task 'Change Type: create' if it is a new file)."
                )
    return issues
```

In the PLAN branch:

```python
            issues.extend(_check_plan_file_refs(run_dir, artifact_content))
```

- [ ] **Step 4: Run tests to verify pass (targeted + full suite)**

Run: `python -m pytest tests/test_gates.py -v && python -m pytest -q`
Expected: PASS across the whole suite.

- [ ] **Step 5: Commit**

```bash
git add tools/workflow_cli/gates.py tests/test_gates.py
git commit -m "feat(r2p): hard-check PLAN file refs against Context Pack repo_root (R5)"
```

---

## Final verification (after all phases)

- [ ] Run the full suite: `python -m pytest -q` — all green.
- [ ] Confirm the docs-consistency guard (R6) still passes and no new doc hardcodes a count.
- [ ] Red-team smoke check (proves G1): hand the new gates a vacuous brief (headings only, `<!-- fill in -->` bodies) and a PLAN whose Spec References are dangling; both must be rejected. The pre-R1 gate would have passed them.

## Spec → Task coverage map (self-review)

| Requirement | Phase / Tasks |
|---|---|
| R1 templates + seeding | Phase 3 — R1.1, R1.2, R1.3 |
| R2 schema gate | Phase 4 — R2.1, R2.2 |
| R3 trace coverage | Phase 6 — R3.1, R3.2, R3.3 |
| R4 repo-path + Context Pack + local links | Phase 5 — R4.1–R4.5 |
| R5 PLAN executability | Phase 8 — R5.1, R5.2, R5.3 |
| R6 drift removal | Phase 1 — R6.1, R6.2 |
| R7 dev deps + CI | Phase 2 — R7.1, R7.2, R7.3 |
| R8 elicitation + scope freeze | Phase 7 — R8.1, R8.2, R8.3 |

**Cross-phase reuse (no duplicate logic):** SPEC-coverage lives once in `trace.spec_ids_not_consumed` (R3), consumed by both the PLAN gate's trace closure (R3.3) and R5. `STAGE_SCHEMA` (R1) is the single source for both templates and the R2 gate.

---
r2p_stage: plan
r2p_version: 2
r2p_status: approved
r2p_created_at: 2026-06-28T20:46:38.901908+00:00
r2p_updated_at: 2026-06-28T21:05:35.871872+00:00
---

# Plan

## Tasks
<!-- Granularity: one PLAN-TASK should be completable by one implementer subagent and independently reviewable by one task-reviewer. Split a task spanning too many files or behaviors; merge two only when they change one indivisible behavior. -->

### PLAN-TASK-001 — Batch 2: optional-section seed path and the five PLN seeds in stage_templates.py
Spec References: SPEC-SEED-001
Change Type: modify
TDD Applicable: yes
Files:
- tools/workflow_cli/stage_templates.py
- tests/test_stage_templates.py
Skeleton:
```python
# tools/workflow_cli/stage_templates.py — additive optional-section path; STAGE_SCHEMA and PLAN_TASK_FIELDS untouched.
_PLAN_GRANULARITY_NOTE = (
    "<!-- Granularity: one PLAN-TASK = one implementer subagent, one task-reviewer; "
    "split a task spanning too many files/behaviors, merge only one indivisible behavior. -->\n"
)  # PLN-5, seeded under "## Tasks" (an HTML comment carries no gate-scanned placeholder token)

_OPTIONAL_SECTIONS = {
    Stage.PLAN: (
        "## Execution Readiness\n"
        "<!-- optional pre-execution self-check; remove if unused -->\n"
        "- Requirement brief reviewed\n"
        "- Design decisions resolved; decision requests pending none\n"
        "- High-risk mitigations represented in tasks\n"
        "- Non-goals protected\n"
        "- Verification commands executable; expected changed files listed\n"
        "- Future-task ownership clear; no unresolved ambiguity\n"
        "\n"
        "## Risk Handling\n"
        "<!-- optional risk-to-task map; RISK-* IDs live in cells only, each row carries a same-line closure tag -->\n"
        "| Risk | Handling Task | Closure |\n"
        "|---|---|---|\n"
        "| RISK-EXAMPLE-001 | PLAN-TASK-001 | [ADDRESSED] |\n"
    ),
}

# _HEADING_BODY[(Stage.PLAN, "## Tasks")] gains, in this order:
#   - PLN-5: the _PLAN_GRANULARITY_NOTE comment prepended to the existing "## Tasks" body.
#   - PLN-2: two optional, gate-clean field lines on the PLAN-TASK seed — "Out-of-Task" and
#     "Future Task Ownership" (referencing the PLAN-TASK-NNN form) — NOT added to PLAN_TASK_FIELDS.
#   - PLN-3: the existing author-fill Verification placeholder comment is KEPT (so an untouched
#     template still trips _check_plan_task_verification_placeholders and fails the gate, preserving
#     test_plan_template_verification_is_a_placeholder_until_filled); only its example is enriched to
#     the three-part shape — targeted command; full relevant suite command; expected evidence.

def template_for(stage, tier_base):
    headings = required_headings(stage, tier_base)
    title = stage.value.replace("_", " ").title()
    parts = [f"# {title}\n"]
    for h in headings:
        parts.append(f"{h}\n{_body_for(stage, h)}")
    parts.append(_OPTIONAL_SECTIONS.get(stage, ""))  # additive; empty for non-PLAN stages
    parts.append(_TRACE_SKELETON)
    return "\n".join(p for p in parts if p)
```
Steps:
- [ ] Write red rendering/presence assertions in tests/test_stage_templates.py: the standard PLAN template contains `Execution Readiness`, `Risk Handling`, an `[ADDRESSED]`-tagged example row, the optional `Out-of-Task` / `Future Task Ownership` PLAN-TASK lines, the enriched three-part Verification example, and the granularity note; non-PLAN templates are byte-identical to before. (The AC-4/AC-5 gate round-trip cases are PLAN-TASK-002.)
- [ ] Add `_OPTIONAL_SECTIONS`, prepend the granularity note to the `## Tasks` body, and apply the PLN-2 / PLN-3 edits in `_HEADING_BODY`; emit the optional sections from `template_for` after the required headings and before `_TRACE_SKELETON`. PLN-3 keeps the Verification line's author-fill placeholder (only its example is enriched) so an untouched template still fails the gate. Leave `required_headings`, `STAGE_SCHEMA`, and `PLAN_TASK_FIELDS` untouched.
- [ ] Confirm the seeded example row uses well-formed IDs in cells only and a same-line closure tag, that no seeded optional element contains a gate-scanned placeholder token, and that `test_plan_template_verification_is_a_placeholder_until_filled` stays green.
Verification:
- Targeted: `.venv/bin/python -m pytest tests/test_stage_templates.py -v` passes, including the new optional-section and non-PLAN-unchanged assertions.
- Full suite: `.venv/bin/python -m pytest tests/ -q` stays green.
- Expected evidence: the rendered standard PLAN template shows the optional sections after the task list and before the trace table; `git diff` shows no change to `stage_schema.py`.
Out-of-Task: does not edit `STAGE_SCHEMA`, `PLAN_TASK_FIELDS`, any gate, `state.py`, or any CLI handler; does not author the AC-4/AC-5 gate round-trip cases.
Future Task Ownership: PLAN-TASK-002 adds the AC-4/AC-5 gate round-trip cases to the same tests/test_stage_templates.py; PLAN-TASK-003 owns the Batch 1 surfaces.
Carries SCOPE-IN-007, SCOPE-IN-008, SCOPE-IN-009, SCOPE-IN-010, SCOPE-IN-011.

### PLAN-TASK-002 — Batch 2: gate round-trip coverage for the seeded PLAN template
Spec References: SPEC-SEEDTEST-001
Change Type: modify
TDD Applicable: yes
Files:
- tests/test_stage_templates.py
Skeleton:
```python
# tests/test_stage_templates.py — Batch 2 gate round-trip coverage (AC-4 + AC-5)
import json
from tools.workflow_cli.gates import check_quality_gate
from tools.workflow_cli.models import Stage, TierBase, TierEstimate, STAGE_ARTIFACT_MAP
from tools.workflow_cli.stage_templates import template_for

def _seed(tmp, plan_text):
    # consistent minimal upstream so trace-closure, file-ref, and context-pack checks pass
    (tmp / "02-project-context.json").write_text(json.dumps({"repo_root": str(tmp)}))
    (tmp / STAGE_ARTIFACT_MAP[Stage.SPEC]).write_text("## SPEC-SEED-001 seed\n")
    (tmp / STAGE_ARTIFACT_MAP[Stage.REQUIREMENT_BRIEF]).write_text(
        "## In-Scope\n- SCOPE-IN-001 x\n## Out-of-Scope\n- " "SCOPE" "-OUT-001 y\n")
    (tmp / STAGE_ARTIFACT_MAP[Stage.PLAN]).write_text(plan_text)

def test_seeded_plan_passes_gate_when_filled_minimally(tmp_path):
    plan = _fill_required_tasks_minimally(template_for(Stage.PLAN, TierBase.STANDARD))
    _seed(tmp_path, plan)
    r = check_quality_gate(tmp_path, Stage.PLAN, TierEstimate(base=TierBase.STANDARD, modifiers=frozenset()), [], plan)
    assert r.passed, r.issues   # AC-4: the seeded Risk Handling row clears Check 3 and the malformed-ID scan

def test_plan_passes_gate_when_optional_sections_omitted(tmp_path):
    plan = _minimal_plan_without_optional_sections()
    _seed(tmp_path, plan)
    r = check_quality_gate(tmp_path, Stage.PLAN, TierEstimate(base=TierBase.STANDARD, modifiers=frozenset()), [], plan)
    assert r.passed, r.issues   # AC-5: optional sections/fields are removable; PLAN_TASK_FIELDS unchanged
```
Steps:
- [ ] Add the AC-4 test: render the updated PLAN template, fill the required `## Tasks` minimally (one task consuming `SPEC-SEED-001`, carrying `SCOPE-IN-001`, with real Files under the seeded `repo_root`), and assert the PLAN quality gate passes — proving the seeded Risk Handling row triggers neither the Check 3 closure failure nor the malformed-trace-ID check.
- [ ] Add the AC-5 test: a PLAN with the optional sections and the optional PLAN-TASK fields removed still passes the gate with `## Tasks` present.
- [ ] Ensure the minimal task's Files reference paths that exist under the fixture `repo_root` so `_check_plan_file_refs` and the standard-tier Context Pack check pass (mirror the `_gate` fixture in tests/test_gates.py).
Verification:
- Targeted: `.venv/bin/python -m pytest tests/test_stage_templates.py -v -k gate` passes for both the minimally-filled and the optional-sections-omitted cases.
- Full suite: `.venv/bin/python -m pytest tests/ -q` stays green.
- Expected evidence: both round-trip tests are green; removing the seeded `[ADDRESSED]` tag from the example row turns the AC-4 test red (closure check fires), confirming the assertion is load-bearing.
Out-of-Task: does not modify `stage_templates.py` or any gate; test-only.
Future Task Ownership: PLAN-TASK-001 owns the seed implementation under test here.
Carries SCOPE-IN-012.

### PLAN-TASK-003 — Batch 1: EXE-1..EXE-5 prose on both r2p-execute surfaces plus matching docs-consistency guard tokens
Spec References: SPEC-EXE-001, SPEC-EXE-002, SPEC-EXE-003, SPEC-EXE-004, SPEC-EXE-005, SPEC-GUARD-001
Change Type: modify
TDD Applicable: yes
Files:
- tools/workflow_cli/agent_templates/claude/commands/r2p-execute.md
- tools/workflow_cli/agent_templates/codex/skills/r2p-execute/SKILL.md
- tests/test_docs_consistency.py
Skeleton:
```python
# tests/test_docs_consistency.py — extend the execute-surface token gate (write red first).
# Each token must be distinctive: absent from BOTH templates before this edit, so it proves the new prose landed.
EXECUTE_SURFACES = [
    "tools/workflow_cli/agent_templates/claude/commands/r2p-execute.md",
    "tools/workflow_cli/agent_templates/codex/skills/r2p-execute/SKILL.md",
]
REQUIRED_TEMPLATE_HARDENING_TOKENS = [
    # Concrete candidate literals (finalize against the authored prose); each must be
    # distinctive — absent from BOTH templates before this edit — so it proves the prose landed.
    # EXE-1: final reviewer reads the full upstream context incl. 07-plan + per-task reports/reviews + Minor
    "the final reviewer is the one role that reads `07-plan.md`",
    # EXE-2: per-task boundary clean-tree invariant, distinct from the Task 1 check
    "a non-clean code tree at a task boundary",
    # EXE-3: brief-contents lists Files + reviewer compares changed files vs the brief's Files
    "against the brief's `Files`",
    # EXE-4: derive-on-resume BASE reconstruction (lowest-numbered unchecked task; preceding completion head7)
    "reconstruct the in-progress task's BASE",
    # EXE-5: report evidence sections; no Context-Read checklist
    "Verification Evidence", "Changed Files",
]
def test_execute_surfaces_carry_template_hardening_tokens():
    for surface in EXECUTE_SURFACES:
        text = (REPO_ROOT / surface).read_text(encoding="utf-8")
        for tok in REQUIRED_TEMPLATE_HARDENING_TOKENS:
            assert tok in text, f"{surface}: missing {tok}"
        assert "`r2p-gap-open`" not in text   # execution runs are closed; preserve existing assertion
# Finalize each placeholder literal against the authored prose so the test pins the wording that ships.
```
Steps:
- [ ] Add the failing token assertions to tests/test_docs_consistency.py (red), preserving the existing SDD / FR-A / FR-CM token sets and the no-`r2p-gap-open` assertions; verify each chosen token is absent from both surfaces before the prose edit.
- [ ] Edit the claude r2p-execute command: EXE-1 the Final Whole-Branch Review section reads the full ACS plus `07-plan.md`, every `task-N-report.md`, every `task-N-review.md`, and every `Minor:` entry (without copying the per-task `07-plan.md` exclusion); EXE-2 a per-task clean-tree `git status --short -- ':!.req-to-plan'` boundary invariant before each dispatch, distinct from the Task 1 check; EXE-3 the §1 brief-contents sentence adds `Files`, and the reviewer compares changed files against the brief's `Files`, returning `CHANGES_REQUESTED` for unjustified out-of-list files; EXE-4 derive-on-resume BASE reconstruction in Durable Progress (lowest-numbered unchecked task; Task 1 from `Execution BASE:`, Task N from the preceding completion line's `head7`; no `HEAD~1`, no fresh-from-HEAD, stop-and-ask when unresolved); EXE-5 the report carries `Verification Evidence` and `Changed Files` sections and no Context-Read checklist.
- [ ] Mirror the identical EXE-1..EXE-5 prose into the codex r2p-execute SKILL so both surfaces carry the same token set.
- [ ] Finalize the exact token literals against the authored prose so the test and both surfaces agree.
Verification:
- Targeted: `.venv/bin/python -m pytest tests/test_docs_consistency.py -v` passes, including the new template-hardening token test on both surfaces.
- Full suite: `.venv/bin/python -m pytest tests/ -q` stays green.
- Expected evidence: deleting any new token from either surface fails `test_execute_surfaces_carry_template_hardening_tokens`; neither surface mentions `r2p-gap-open`.
Out-of-Task: does not edit any gate, `state.py`, CLI handler, or `stage_templates.py`; opencode/gemini surfaces are not authored here.
Future Task Ownership: PLAN-TASK-001 and PLAN-TASK-002 own the Batch 2 seed and its tests.
Carries SCOPE-IN-001, SCOPE-IN-002, SCOPE-IN-003, SCOPE-IN-004, SCOPE-IN-005, SCOPE-IN-006.

## Execution Readiness
- Requirement brief reviewed: goal, scope, non-goals, and acceptance criteria consumed from 03-requirement-brief.md.
- Design decisions resolved: the design's Decision Requests is `none`; no open human choice remains.
- High-risk mitigations represented in tasks: every risk maps to a task in the Risk Handling table below.
- Non-goals protected: no out-of-scope item is touched by any task; the firm code boundary holds.
- Verification commands executable: the venv pytest commands in each task run locally (a few tomllib tests skip on the local 3.10 venv; CI runs 3.11/3.12).
- Expected changed files listed: each task's Files enumerates its touchpoints.
- Future-task ownership clear: each task names its sibling boundaries.
- No unresolved ambiguity: all upstream stages were approved with full trace closure.

## Risk Handling
| Risk | Handling Task | Closure |
|---|---|---|
| RISK-DRIFT-001 | PLAN-TASK-003 | [ADDRESSED] |
| RISK-SEED-001 | PLAN-TASK-001, PLAN-TASK-002 | [ADDRESSED] |
| RISK-RESUME-001 | PLAN-TASK-003 | [ADDRESSED] |
| RISK-TRUST-001 | PLAN-TASK-001, PLAN-TASK-003 | [ADDRESSED] |
| RISK-SCOPE-001 | PLAN-TASK-001, PLAN-TASK-002, PLAN-TASK-003 | [ADDRESSED] |
| RISK-TREE-001 | PLAN-TASK-003 | [ADDRESSED] |

## Trace
<!-- Map this stage's IDs to upstream/downstream. R3 derives & checks closure. -->
| This ID | Upstream | Status |
|---|---|---|
| PLAN-TASK-001 | SPEC-SEED-001, SCOPE-IN-007, SCOPE-IN-008, SCOPE-IN-009, SCOPE-IN-010, SCOPE-IN-011 | open — ready for execution |
| PLAN-TASK-002 | SPEC-SEEDTEST-001, SCOPE-IN-012 | open — ready for execution |
| PLAN-TASK-003 | SPEC-EXE-001, SPEC-EXE-002, SPEC-EXE-003, SPEC-EXE-004, SPEC-EXE-005, SPEC-GUARD-001, SCOPE-IN-001, SCOPE-IN-002, SCOPE-IN-003, SCOPE-IN-004, SCOPE-IN-005, SCOPE-IN-006 | open — ready for execution |

## Upstream Summary (read-only)
# Spec

## Behavior Contracts

### SPEC-EXE-001 — Final whole-branch reviewer reads the full upstream context
Implements DES-EXEC-001 [ADDRESSED]; closes SCOPE-IN-001. Applies identically to both r2p-execute surfaces.
- The `## Final Whole-Branch Review` section instructs the reviewer to read the full Authoritative Context Set — `02-project-context.md`, `03-requirement-brief.md`, `04-risk-discovery.md`, `05-design.md`, `06-spec.md`, `execution/progress.md` — plus `07-plan.md`, every `execution/task-N-report.md`, every `execution/task-N-review.md`, and every `Minor:` ledger entry.
- The final reviewer is the one role that reads `07-plan.md`; the per-task Authoritative Context Set exclusion of `07-plan.md` is not copied into this section, and the per-task ACS block keeps that exclusion unchanged.

### SPEC-EXE-002 — Per-task clean working-tree boundary invariant
Implements DES-EXEC-001 [ADDRESSED]; closes SCOPE-IN-002. Applies identically to both surfaces.
- Before dispatching each task's implementer (not only Task 1), the controller runs `git status --short -- ':!.req-to-plan'`.
- A non-clean code tree at a task boundary is treated as a boundary-invariant violation (the previous task or fix wave left uncommitted work): the controller stops and resolves it before continuing.
- This per-task boundary invariant is stated distinctly from the existing Task 1 check, which additionally negotiates pre-existing user dirty work; the Task 1 negotiation is not duplicated into the per-task boundary text.

### SPEC-EXE-003 — Reviewer checks changed files against the brief's `Files`
Implements DES-EXEC-001 [ADDRESSED]; closes SCOPE-IN-003. Applies identically to both surfaces.
- The §1 brief-contents description lists `Files` alongside `Skeleton`, `Steps`, `Spec References`, and `Verification` (AC-2).
- The task-reviewer section instructs the reviewer to compare the files actually changed in the task diff against the brief's `Files` list; a file changed outside that list requires an explicit, recorded justification, or the review returns `CHANGES_REQUESTED`.
- This is a reviewer-protocol check only; the CLI does not parse the diff and no hard gate is added.

### SPEC-EXE-004 — Mid-task interruption recovery by derive-on-resume
Implements DES-EXEC-001 [ADDRESSED]; closes SCOPE-IN-004. Applies identically to both surfaces. Lives in the existing `## Durable Progress` section; persists no new state.
- On resume, the in-progress task is the lowest-numbered unchecked (`- [ ]`) task.
- For that task the controller does NOT capture a fresh BASE from current HEAD. It reconstructs the task's BASE from markers already on disk: Task 1 from the ledger `Execution BASE:` line; Task N (N > 1) from the `head7` of the immediately preceding `Task N-1: complete (commits <base7>..<head7>, review clean)` line.
- It then regenerates `logs/task-N-diff.md` from that BASE to HEAD and re-dispatches the task-reviewer idempotently: an already-committed, correct task is approved as-is; the implementer is re-dispatched only if the review finds a gap.
- If neither marker can be resolved, the controller stops and asks the human for the BASE. It never infers a range from `HEAD~1` and never captures a fresh BASE from HEAD on resume.

### SPEC-EXE-005 — Implementer task report carries evidence sections
Implements DES-EXEC-001 [ADDRESSED]; closes SCOPE-IN-005. Applies identically to both surfaces.
- The implementer's `execution/task-N-report.md` contains a `Verification Evidence` section (the command run and its fresh result) and a `Changed Files` section (the files the task actually changed).
- The report does NOT contain a self-attested "Context Read" checklist.
- These sections are review aids, not a correctness proof; the `Changed Files` section also feeds the SPEC-EXE-003 reviewer comparison.

### SPEC-GUARD-001 — Batch 1 two-surface lockstep token guard
Implements DES-GUARD-001 [ADDRESSED]; closes SCOPE-IN-006.
- `tests/test_docs_consistency.py` asserts that each of EXE-1..EXE-5 has a distinctive load-bearing token present on BOTH r2p-execute surfaces (`claude/commands/r2p-execute.md` and `codex/skills/r2p-execute/SKILL.md`); deleting any required token from either surface fails the test.
- Each guard token is distinctive — absent from both templates before this edit — so it proves the new prose landed rather than matching incidental pre-existing text.
- The existing SDD / FR-A / FR-CM token sets and the no-`r2p-gap-open` assertions are preserved.
- Suggested token set (exact literals finalized in the PLAN against the authored prose): EXE-1 a final-review whole-context literal naming `07-plan.md` plus per-task reports/reviews and `Minor:`; EXE-2 a per-task-boundary clean-tree literal (e.g. distinct from the Task-1 wording); EXE-3 the brief-contents `Files` correction literal and a files-vs-`Files` reviewer literal; EXE-4 a derive-on-resume literal (lowest-numbered unchecked task / preceding completion `head7`); EXE-5 the `Verification Evidence` and `Changed Files` section names.

### SPEC-SEED-001 — Optional-section seed path and the five PLN seeds in stage_templates.py
Implements DES-SEED-001 [ADDRESSED]; closes SCOPE-IN-007, SCOPE-IN-008, SCOPE-IN-009, SCOPE-IN-010, SCOPE-IN-011.
- A per-stage optional-section source (e.g. `_OPTIONAL_SECTIONS: dict[Stage, str]`) is emitted by `template_for` after the required-heading bodies and before `_TRACE_SKELETON`. `required_headings`, `STAGE_SCHEMA`, and `PLAN_TASK_FIELDS` are unchanged, so no new heading is gate-required and no new field is gate-required.
- PLN-1: the PLAN optional sections include `## Execution Readiness`, a concrete optional self-check checklist (requirement brief reviewed; design decisions resolved; decision requests pending none; high-risk mitigations represented in tasks; non-goals protected; verification commands executable; expected changed files listed; future-task ownership clear; no unresolved ambiguity). Author scaffolding, not a hard gate.
- PLN-4: the PLAN optional sections include `## Risk Handling`, a risk-to-task table with a header row and exactly one example data row `| RISK-EXAMPLE-001 | PLAN-TASK-001 | [ADDRESSED] |`. Every row naming a `RISK-*` ID carries a same-line closure tag (`[ADDRESSED]`, `[DEFERRED]`, `[N/A]`, `[OUT-OF-SCOPE]`, or `[CLOSED]`); `RISK-*` IDs appear only in table cells, never in a `#`/`##`/`###` heading.
- PLN-2: the PLAN-TASK seed body gains optional `Out-of-Task:` and `Future Task Ownership:` field lines with gate-clean illustrative values; `Future Task Ownership` references the `PLAN-TASK-NNN` form. These optional fields are NOT added to `PLAN_TASK_FIELDS`.
- PLN-3: the required `Verification` seed example is enriched into a three-part executable contract — a targeted command, the full relevant suite command, and the expected evidence. `Verification` stays the author-supplied required field; only its example is enriched.
- PLN-5: a concise PLAN-TASK granularity-guidance HTML comment is seeded under `## Tasks` — one PLAN-TASK should be completable by one implementer subagent and independently reviewable by one task-reviewer; split a task spanning too many files or behaviors; merge two only when they change one indivisible behavior.
- Gate-clean invariants: every seeded optional element is free of the placeholder tokens the gate scans for (no unfilled-marker comments, no undecided-marker or unresolved-question lines), uses only well-formed trace IDs, and lives outside the `### PLAN-TASK` bodies (so the last task body terminates at `## Execution Readiness`). A PLAN seeded from the updated template and filled minimally passes the PLAN quality gate (AC-4), and omitting the optional sections and fields leaves a PLAN that still passes with `## Tasks` present (AC-5).

### SPEC-SEEDTEST-001 — Batch 2 gate round-trip coverage
Implements DES-SEEDTEST-001 [ADDRESSED]; closes SCOPE-IN-012.
- An AC-4 test renders the updated PLAN template, fills the required `## Tasks` minimally (with a consistent minimal upstream fixture: a SPEC that defines and is consumed by the task, a carried SCOPE-IN, closed risks, and a usable Context Pack for standard tier), and asserts the PLAN quality gate passes — confirming the seeded `## Risk Handling` row triggers neither the Check 3 closure failure nor the malformed-trace-ID check.
- An AC-5 test strips `## Execution Readiness`, `## Risk Handling`, `Out-of-Task`, and `Future Task Ownership` and asserts the gate still passes with `## Tasks` present, proving the new sections and fields are optional and `PLAN_TASK_FIELDS` is unchanged.

## API / Data / Config Contracts

No CLI argument, JSON payload, exit code, run status, state transition, gate, artifact schema, or `PLAN_TASK_FIELDS` change. The only programmatic surface touched is the internal `stage_templates.template_for` rendering (SPEC-SEED-001): its output for the PLAN stage gains trailing optional sections, while its output for every other stage is byte-identical to today (the optional-section source is empty for non-PLAN stages). The seeded PLAN's structural contract (`## Tasks`, the seven `PLAN_TASK_FIELDS`, the trace skeleton) is preserved; the additions are appended, optional, and removable.

## External Documentation Checked

N/A — no external dependencies

The change is entirely internal: template prose on the r2p-execute surfaces, an additive seed-rendering path in `stage_templates.py` (Python stdlib only), and pytest assertions. No new runtime dependency is introduced and no third-party library, API, SDK, or CLI is consulted by the implementation. The PLAN granularity, derive-on-resume, and clean-tree disciplines are r2p's own conventions, verified against the in-repo code, not an external source.

## Test Matrix

| Test | SPEC | Expectation |
|---|---|---|
| EXE-1 final-review full-context tokens on both surfaces | SPEC-EXE-001, SPEC-GUARD-001 | the final-review section names `07-plan.md`, the ACS read set, per-task reports/reviews, and `Minor:`; deleting the token on either surface fails |
| EXE-2 per-task boundary clean-tree token on both surfaces | SPEC-EXE-002, SPEC-GUARD-001 | a per-task-boundary clean-tree literal distinct from the Task-1 check is present on both surfaces |
| EXE-3 `Files` description + reviewer files-vs-`Files` tokens | SPEC-EXE-003, SPEC-GUARD-001 | §1 brief description lists `Files`; reviewer compares changed files vs `Files`; both surfaces |
| EXE-4 derive-on-resume tokens on both surfaces | SPEC-EXE-004, SPEC-GUARD-001 | lowest-numbered unchecked task + preceding-completion `head7` reconstruction + no-`HEAD~1`/stop-and-ask present on both surfaces |
| EXE-5 report evidence-section tokens on both surfaces | SPEC-EXE-005, SPEC-GUARD-001 | `Verification Evidence` and `Changed Files` present, no Context-Read checklist, both surfaces |
| existing SDD / FR-A / FR-CM token sets still pass | SPEC-GUARD-001 | unchanged guards stay green; no `r2p-gap-open` on either surface |
| seeded PLAN, filled minimally, passes the quality gate | SPEC-SEED-001, SPEC-SEEDTEST-001 | gate passes; Risk Handling row clears Check 3 and the malformed-ID check (AC-4) |
| seeded PLAN with optional sections/fields omitted passes | SPEC-SEED-001, SPEC-SEEDTEST-001 | gate passes with `## Tasks` present (AC-5) |
| non-PLAN stage templates byte-identical | SPEC-SEED-001 | `template_for` output unchanged for non-PLAN stages |
| full pytest suite stays green | all | no pre-existing test regresses |

## Non-goals

- SCOPE-OUT-001: no per-task BASE persistence; SPEC-EXE-004 reconstructs the BASE from existing markers and persists nothing new.
- SCOPE-OUT-002 / SCOPE-OUT-003: no `r2p-execute-doctor` command and no `task-N-context.md` bundle, `context-manifest.json`, content hash, or drift gate.
- SCOPE-OUT-004: no CLI-side semantic correctness judgment; the EXE-5 evidence, `## Execution Readiness`, and `## Risk Handling` markers are never machine-asserted as true.
- SCOPE-OUT-005 / SCOPE-OUT-006: no whole-repo AST / call-graph / LSP indexing, and no new approval flow or run status.
- SCOPE-OUT-007: no new resume skill or command; SPEC-EXE-004 lives in the existing `/r2p-execute` Durable Progress section.
- SCOPE-OUT-008: no CLI, `state.py`, or gate change in Batch 1; no `STAGE_SCHEMA` or `PLAN_TASK_FIELDS` change in Batch 2.

## PLAN Handoff

Three PLAN tasks, numbered contiguously from 1, consuming every SPEC ID above. Batch 2 ships first (single source, lowest gate-interaction risk), then Batch 1; each task is independently mergeable.
- PLAN-TASK-1 (Batch 2) — add the optional-section seed path and the five PLN seeds to `tools/workflow_cli/stage_templates.py` (Change Type: modify). Spec References: SPEC-SEED-001. Carries SCOPE-IN-007, SCOPE-IN-008, SCOPE-IN-009, SCOPE-IN-010, SCOPE-IN-011.
- PLAN-TASK-2 (Batch 2) — add the gate round-trip tests (AC-4 gate-clean seed, AC-5 non-gating omission) in `tests/` (Change Type: modify). Spec References: SPEC-SEEDTEST-001. Carries SCOPE-IN-012.
- PLAN-TASK-3 (Batch 1) — add the EXE-1..EXE-5 prose identically to both r2p-execute surfaces and extend `tests/test_docs_consistency.py` with the matching per-EXE guard tokens, written red-first against the new prose (Change Type: modify). Spec References: SPEC-EXE-001, SPEC-EXE-002, SPEC-EXE-003, SPEC-EXE-004, SPEC-EXE-005, SPEC-GUARD-001. Carries SCOPE-IN-001, SCOPE-IN-002, SCOPE-IN-003, SCOPE-IN-004, SCOPE-IN-005, SCOPE-IN-006.

## Trace

| This ID | Upstream | Status |
|---|---|---|
| SPEC-EXE-001 | DES-EXEC-001, SCOPE-IN-001 | open — consumed by PLAN-TASK-3 |
| SPEC-EXE-002 | DES-EXEC-001, SCOPE-IN-002 | open — consumed by PLAN-TASK-3 |
| SPEC-EXE-003 | DES-EXEC-001, SCOPE-IN-003 | open — consumed by PLAN-TASK-3 |
| SPEC-EXE-004 | DES-EXEC-001, SCOPE-IN-004 | open — consumed by PLAN-TASK-3 |
| SPEC-EXE-005 | DES-EXEC-001, SCOPE-IN-005 | open — consumed by PLAN-TASK-3 |
| SPEC-GUARD-001 | DES-GUARD-001, SCOPE-IN-006 | open — consumed by PLAN-TASK-3 |
| SPEC-SEED-001 | DES-SEED-001, SCOPE-IN-007, SCOPE-IN-008, SCOPE-IN-009, SCOPE-IN-010, SCOPE-IN-011 | open — consumed by PLAN-TASK-1 |
| SPEC-SEEDTEST-001 | DES-SEEDTEST-001, SCOPE-IN-012 | open — consumed by PLAN-TASK-2 |
<!-- /r2p-read-only -->

## Project Context (read-only)
# Project Context Pack

- repo_root: `/Users/xubo/x-skills/req-to-plan`
- languages: {'Python': 22201, 'JavaScript': 31}
- package_managers: npm, pip
- test_commands: ['npm test']
- entrypoints: ['tools/workflow_cli/__main__.py']
- config_files: ['requirements.txt']
- dependencies (1):
  - pyyaml>=6.0 (pip)
- source_dirs: ['bin', 'docs', 'requirements', 'tests', 'tools']
<!-- /r2p-read-only -->

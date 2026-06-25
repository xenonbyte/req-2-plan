# r2p-execute Controller Context-Management Requirement

## Summary

A follow-on to the already-shipped **r2p-execute SDD Enhancement & Final-Review
Marker Gate** work (FR-A1–FR-A6, now in local archive). That work moved the
*diff and history* out of the controller's context into files (FR-A2) and
disciplined the *reviewer prompt* (FR-A4). This requirement borrows the four
remaining **controller-side context-management** disciplines from the
`superpowers:subagent-driven-development` skill (upstream
`obra/superpowers`, v6.0.3) that r2p-execute does not yet carry:

1. **FR-CM1 — Task handoff as a file pointer + minimal implementer return contract.**
2. **FR-CM2 — Controller narration discipline.**
3. **FR-CM3 — Reviewer ⚠️ "cannot verify from diff" adjudication before the checkbox flip.**
4. **FR-CM4 — Minor findings carried forward to the final whole-branch review.**

The change is **agent-template prose only**. It touches no CLI command, no gate,
no state transition, no artifact schema, and no JSON output. It is deliberately
compatible with — and reinforces — r2p's existing **trust/audit** gate
architecture, in which the agent is the adjudicating authority and the machine
only audits the presence/structure of the markers the agent produces.

## Motivation

The central thesis of the superpowers SDD skill is a context-economy claim:

> Everything you paste into a dispatch prompt — and everything a subagent prints
> back — stays resident in your context for the rest of the session and is
> re-read on every later turn. Hand artifacts over as files.

r2p-execute already honors half of this (FR-A2 hands diffs and history over as
files under `logs/`). But three leaks and one correctness gap remain:

- **Task text leaks in.** The current §2 instruction — "Provide the subagent
  with: The task text (from `07-plan.md`)" — reads as *paste the task text into
  the dispatch*, which keeps it resident in the controller's context for the
  whole run. The task already lives in a structured file (`07-plan.md`, with
  `### PLAN-TASK-NNN` anchors); the controller can hand a **pointer** instead.
- **Reports leak back.** There is no minimal-return contract, so an implementer
  can return its full report into the controller's context even though the
  report is also written to `execution/task-N-report.md`.
- **Controller narration leaks.** No narration ceiling, so coordination turns
  can accrete prose that the ledger and tool results already record.
- **Diff-scoped reviewer blindness is ungated.** The task-reviewer is handed
  only the single-task diff (`logs/task-N-diff.md`). Requirements satisfied in
  *unchanged* code, or spanning tasks, are invisible to it. The current §6 flip
  rule keys solely on "task-reviewer clean", so a reviewer can report spec ✅ on
  the visible diff while a "cannot verify from diff" item is left unresolved,
  and the checkbox flips anyway.

The transferable mechanism is not "add another gate". It is: **keep the
controller's context curated by handing artifacts as files and returns as a few
lines, and make the one place that already governs the checkbox flip account
for what the diff-scoped reviewer structurally cannot see.**

## Goals

- Keep the controller's context bounded across a multi-task run: task text and
  full reports move as files, not pasted/returned prose.
- Close the diff-scoped-reviewer gap *in the prose/agent-judgment layer* without
  adding a machine gate, preserving the deliberate trust/audit architecture.
- Stop silently discarding Minor findings between per-task review and the final
  whole-branch review.
- Keep all four changes **agent-template prose only**, replicated across the two
  execution surfaces that carry the orchestration body, and lock them with
  `tests/test_docs_consistency.py` tokens so they cannot silently rot.

## Non-Goals

- **No worktree, branch, or protection boundary.** Execution stays in-place on
  the current branch — a core r2p invariant. The superpowers
  `using-git-worktrees` / `finishing-a-development-branch` integration is
  explicitly **not** borrowed.
- **No bundled bash scripts.** superpowers ships `scripts/task-brief` and
  `scripts/review-package`. r2p's machine work lives in the Python CLI; this
  requirement does **not** add either script.
- **No new CLI command.** A `r2p-task-brief`-style extraction command is out of
  scope here (see Deferred Decisions); FR-CM1 uses the existing
  `07-plan.md` + anchor instead.
- **No machine-gate, state-transition, schema, or JSON change.** `gates.py`,
  `cli.py`, `state.py`, and `artifact.py` are untouched.
- **No change to the trust/audit model.** No receipt-based verification, no
  machine assertion that a marker is true. (Consistent with the deliberate
  rejection recorded in the `r2p-execution-gate-boundary` decision.)

## Background: Current State (verified against code)

The "adjudication / checkbox" mechanism that this requirement must not conflict
with has two layers.

**Prose layer (agent judgment) — `r2p-execute` §6 flip rule.**
`- [ ] PLAN-TASK-NNN` → `- [x]` only when the task-reviewer is clean (spec ✅,
quality Approved, `Verification` satisfied). The final review verdict is written
to `execution/final-review.md` as `Verdict: Approved` after the whole-branch
review settles clean.

**Machine layer (archive-time audit) — `cli.py` archive path runs two gates:**

- `check_execution_complete(run_dir)` — `tools/workflow_cli/gates.py:1240`.
  Parses only the structural ledger markers
  (`_LEDGER_UNCHECKED_RE` / `_LEDGER_CHECKED_RE`,
  `tools/workflow_cli/gates.py:1201-1202`,
  matching `^\s*-\s*\[ \]\s*PLAN-TASK-\d+` and the `[x]` form). Fails if any
  `- [ ]` remains, if a frozen-PLAN task ID has no `- [x]` line, or if there are
  zero `- [x]`. Its own docstring: *"This is structural validation only: it
  trusts the agent's checkbox flips (an audit gate, not a correctness gate)."*
- `check_final_review_recorded(run_dir)` — `tools/workflow_cli/gates.py:1148`.
  Reads only the last unfenced `Verdict:` line. Its own docstring:
  *"Presence/audit only — never runs code or tests, never asserts the verdict is
  true. Same trust level as the PLAN-TASK checkbox gate."*

`check_forced_subagent_review` (`gates.py:1068`) is **not** in scope: it fires
only for DESIGN/SPEC/PLAN stages with MIGRATION/SAFETY/CROSS_PROJECT modifiers,
never for execution.

**Conclusion of the current-state read:** both machine gates are *deliberately*
audit-only. The truth of a checkbox or verdict is the controller's
responsibility, established in prose through the task-reviewer loop. This is the
architecture FR-CM3 must live inside — in the agent-judgment layer, adding **no**
new machine gate.

## Functional Requirements

All prose lands in **both** orchestration surfaces (see Target Surfaces). Gemini
`r2p-execute.toml` has no body and is unchanged.

### FR-CM1: Task handoff as a file pointer + minimal implementer return contract

**Where:** `r2p-execute` §2 ("Dispatch a fresh implementer subagent") and the
"The implementer must:" list.

**Add a controller-context principle** near the top of the Per-Task Loop (one
line):

> Everything you paste into a dispatch and everything a subagent returns stays
> resident in your context and is re-read every turn. Hand artifacts as file
> paths; keep returns to a few lines.

**Change the task handoff.** Replace "Provide the subagent with: The task text
(from `07-plan.md`)" with a file-pointer handoff:

> - A pointer to read **only** its own task block (`### PLAN-TASK-NNN` in
>   `07-plan.md`) — do **not** paste the task text into the dispatch, and do
>   **not** tell it to read the whole plan file. Hand it the file path plus the
>   `PLAN-TASK-NNN` anchor so the requirement text stays out of your context.

**Add a minimal return contract** to the implementer instructions:

> The implementer writes its full report to `execution/task-N-report.md` and
> returns **only**: status, the commit range, a one-line test summary, and
> concerns. Do not let the full report flow back into your context — read the
> report file only if a status (`BLOCKED` / `NEEDS_CONTEXT` / concerns) requires it.

### FR-CM2: Controller narration discipline

**Where:** top of the `r2p-execute` body (alongside the existing "Continuous
execution" guidance).

**Add:**

> **Narration:** between tool calls, narrate at most one short line — the ledger
> (`execution/progress.md`) and the tool results carry the record.

### FR-CM3: Reviewer ⚠️ "cannot verify from diff" adjudication before the flip

**Where:** `r2p-execute` §6 ("Fix loop"), amending the checkbox-flip condition.
**No machine-gate change.**

The task-reviewer is handed only the single-task diff and therefore cannot see
requirements that live in unchanged code or span tasks. It may surface these as
⚠️ "cannot verify from diff" items. These do not block the rest of the review,
but the controller must resolve each one before the flip — and must do so
**without becoming a second checkbox authority**.

**Amend the flip condition to (the binding wording):**

> Flip `- [x]` only when the task-reviewer is clean — spec ✅, quality Approved,
> `Verification` satisfied, **and no unresolved ⚠️ "cannot verify from diff" item
> remains**. The task-reviewer sees only the single-task diff; resolve each ⚠️
> yourself (you hold the cross-task and PLAN context it lacks). A confirmed gap
> is a failed spec review: send it back to the implementer and re-review —
> never flip the checkbox on your own judgment.

This keeps "checkbox flips only when the reviewer is clean" as the single
authority: the controller never unilaterally flips a checkbox, it only routes a
confirmed ⚠️ gap back through the existing implementer → re-review loop.

### FR-CM4: Minor findings carried forward to the final whole-branch review

**Where:** `r2p-execute` §6 (task-level) and "Final Whole-Branch Review".

**Add at task level:**

> Record Minor findings in `execution/progress.md` as you go, written as plain
> `Minor:` bullets. **Do not** write them in the `- [ ] PLAN-TASK-N` shape — that
> form is parsed by the completion gate as an unfinished task and would block
> archive.

**Add at the final review:**

> Point the final whole-branch review at the accumulated `Minor:` findings so it
> triages which must be fixed before the merge gate. A roll-up nobody reads is a
> silent discard.

## Conflict Analysis (the explicit review)

This requirement was checked against r2p's existing adjudication/checkbox
mechanism before being written. Findings:

| Dimension | Finding |
|---|---|
| **Machine-gate conflict** | **None.** FR-CM1–CM4 touch only prose and free-text ledger lines. `check_execution_complete` parses only `- [ ]`/`- [x] PLAN-TASK-\d+`; `check_final_review_recorded` parses only the last `Verdict:`. Neither structural marker is altered. |
| **Design-philosophy fit** | **Reinforces.** FR-CM3 places adjudication in the agent-judgment layer — exactly where the audit-only architecture wants it. It adds **no** machine gate; a hypothetical "⚠️ resolved" machine gate would *violate* the deliberate audit-only decision and is therefore excluded. |
| **Single prose-integration risk** | **One, mitigated.** Naively, FR-CM3 could create a *second* checkbox authority ("controller decides to flip") competing with "flip only when reviewer clean". The binding wording in FR-CM3 folds ⚠️ resolution *into* "reviewer clean" and routes confirmed gaps back through the implementer → re-review loop, so the reviewer-clean rule stays the single authority. |
| **Responsibility overlap (disclosed)** | The final whole-branch review already re-walks the full PLAN task-by-task on the whole-branch diff, so it is the existing backstop for "requirement in unchanged / cross-task code". FR-CM3 is therefore an **earlier, cheaper catch** (and it prevents the task-reviewer from emitting a *false* spec ❌ on a requirement it structurally cannot see, avoiding a needless fix loop) — **not** a unique safety net. Its value is locality and false-positive avoidance, not closing an otherwise-unguarded path to archive. |
| **FR-CM4 ledger-format gotcha** | Minor lines must be plain `Minor:` bullets. A `- [ ] PLAN-TASK-N`-shaped Minor line would match `_LEDGER_UNCHECKED_RE` and block the completion gate. Encoded in the FR-CM4 wording and in a docs-consistency token. |

## Target Surfaces / Files

1. `tools/workflow_cli/agent_templates/claude/commands/r2p-execute.md` — FR-CM1–CM4 prose.
2. `tools/workflow_cli/agent_templates/codex/skills/r2p-execute/SKILL.md` — same prose (the two bodies are kept textually in sync; the docs-consistency token gate enforces parity).
3. `tools/workflow_cli/agent_templates/gemini/commands/r2p-execute.toml` — **unchanged** (4-line pointer, no orchestration body).
4. `tests/test_docs_consistency.py` — extend the
   `test_execute_surfaces_carry_sdd_orchestration_tokens` required tuple with the
   new guard tokens (below).

## Acceptance Criteria

- Both orchestration surfaces hand the implementer a `PLAN-TASK-NNN` **file
  pointer** (no pasted task text, no "read the whole plan file" instruction).
- Both surfaces state the minimal implementer return contract (status / commit
  range / one-line test summary / concerns; full report → `task-N-report.md`).
- Both surfaces carry the narration ceiling line.
- Both surfaces' §6 flip condition subsumes "no unresolved ⚠️ cannot-verify
  item", with confirmed gaps routed back through implementer → re-review and an
  explicit "never flip on your own judgment".
- Both surfaces record Minor findings as plain `Minor:` bullets and point the
  final review at them; neither uses the `- [ ] PLAN-TASK-N` shape for Minors.
- No change to `gates.py`, `cli.py`, `state.py`, `artifact.py`, JSON output, or
  any state transition.
- `tests/test_docs_consistency.py` passes with the new tokens; the full suite
  stays green.

## Test Plan

Extend `test_execute_surfaces_carry_sdd_orchestration_tokens` (claude + codex
surfaces) with guard tokens, e.g.:

- `"cannot verify from diff"` (FR-CM3)
- `"never flip the checkbox on your own judgment"` (FR-CM3 single-authority)
- `"returns **only**"` or an equivalent stable literal (FR-CM1 return contract)
- `"Narration:"` (FR-CM2)
- `"Minor:"` plus a literal forbidding the `- [ ] PLAN-TASK-N` shape (FR-CM4)

Token strings are finalized against the exact prose during implementation so the
test asserts the wording that ships. No new test module is required; this
extends the existing docs-consistency guard.

## Risks

- **Wording drift between the two surfaces.** Mitigated by the docs-consistency
  token gate (any new required token must appear in both files).
- **Over-tokenizing the test.** Keep tokens to stable, load-bearing phrases;
  do not pin incidental wording, which would make routine edits brittle.
- **FR-CM3 misread as a new gate.** Mitigated by the explicit "no machine-gate
  change" statement and the single-authority wording.
- **Marginal real-world gain on FR-CM1 if controllers already hand `07-plan.md`
  as a pointer.** Accepted: the change removes the ambiguity at near-zero cost
  and is correct regardless.

## Deferred Decisions

- **`r2p-task-brief` CLI command.** Whether to add a CLI command that extracts a
  single PLAN-TASK to a brief file (so the controller never touches task text at
  all) is deferred. Default recommendation: ship FR-CM1's pointer-based handoff
  first, run one real execution, and only add the CLI command if controller
  context still grows materially. Owner: maintainer, after first post-change run.

## Verification Commands

```bash
# Local: must use the venv (system python3 lacks pyyaml).
.venv/bin/python -m pytest tests/test_docs_consistency.py -v
.venv/bin/python -m pytest tests/ -q          # full suite stays green
```

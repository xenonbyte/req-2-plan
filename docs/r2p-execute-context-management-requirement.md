# r2p-execute Controller Context-Management Requirement

## Summary

A follow-on to the already-shipped **r2p-execute SDD Enhancement & Final-Review
Marker Gate** work (FR-A1–FR-A6, now in local archive). That work moved the
*diff and history* out of the controller's context into files (FR-A2) and
disciplined the *reviewer prompt* (FR-A4). This requirement borrows the five
remaining **context-management** disciplines from the
`superpowers:subagent-driven-development` skill (upstream `obra/superpowers`,
v6.0.3) that r2p-execute does not yet carry:

1. **FR-CM1 — Task handoff as a brief file + minimal implementer return contract.**
2. **FR-CM2 — Controller narration discipline.**
3. **FR-CM3 — Reviewer ⚠️ "cannot verify from diff" adjudication before the checkbox flip.**
4. **FR-CM4 — Minor findings carried forward to the final whole-branch review.**
5. **FR-CM5 — `r2p-task-brief`: a read-only CLI command that extracts one frozen
   PLAN task to a brief file, so neither the controller nor the implementer
   ingests the whole plan.**

FR-CM2–CM4 are **agent-template prose only**. FR-CM1 + FR-CM5 add **one
read-only CLI extraction command** (and its shortcut + wrapper) and wire the
template task-handoff to it. The change touches no gate, no state transition, no
artifact schema, and no existing command's output contract. It is deliberately
compatible with — and reinforces — r2p's existing **trust/audit** gate
architecture, in which the agent is the adjudicating authority and the machine
only audits the presence/structure of the markers the agent produces.

## Motivation

The central thesis of the superpowers SDD skill is a context-economy claim:

> Everything you paste into a dispatch prompt — and everything a subagent prints
> back — stays resident in your context for the rest of the session and is
> re-read on every later turn. Hand artifacts over as files.

r2p-execute already honors half of this (FR-A2 hands diffs and history over as
files under `logs/`). Two context leaks, one correctness gap, and one
silent-discard remain:

- **Task text leaks both ways.** The current §2 instruction — "Provide the
  subagent with: The task text (from `07-plan.md`)" — reads as *paste the task
  text into the dispatch*, which keeps it resident in the **controller's**
  context for the whole run (the expensive, compounding leak). The lighter
  alternative — "tell the implementer to read its `PLAN-TASK-NNN` block" — only
  half-fixes it: it removes the controller paste but leaves the **implementer**
  free to read the whole `07-plan.md` (superpowers names "make a subagent read
  the whole plan file" an explicit red flag). The deterministic fix is to
  extract exactly one task to a brief file (FR-CM5) and hand its path, so
  neither side sees more than the one task.
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

The transferable mechanism is not "add another gate". It is: **keep both the
controller's and each subagent's context curated by handing each task as a brief
file and returns as a few lines, and make the one place that already governs the
checkbox flip account for what the diff-scoped reviewer structurally cannot
see.**

## Leak hierarchy (why FR-CM5 is in scope, not deferred)

The context leaks are not equal, and the cost/value split is what justifies
doing FR-CM5 now rather than shipping a prose-only pointer:

| Leak | Nature | Fixed by | Cost |
|---|---|---|---|
| Controller pastes task text | Resident in the **controller** context, re-read **every turn, compounds** across the run | FR-CM1 brief-path handoff | low |
| Implementer reads the whole plan | Lands in a **one-shot** subagent context, discarded after the task, **does not compound** | FR-CM5 deterministic extraction | one CLI command + wrapper + tests |

FR-CM5 is in-grain and cheap because the machinery already exists:
`run-execute-start` (`tools/workflow_cli/cli.py:746`) already extracts PLAN-TASK
anchors with `plan_task_anchors(strip_readonly_sections(plan_text))` to seed
`execution/progress.md`. Extracting one task *body* to a brief file is the same
class of structural operation — **extraction of frozen PLAN text, not
generation of prose** — so it does not cross the "CLI never generates artifact
prose" boundary.

## Goals

- Keep both the controller's and each implementer's context bounded: each task
  is handed as a brief file; full reports move as files, not returned prose.
- Make single-task extraction **deterministic** (CLI-owned anchor parsing) rather
  than relying on a subagent to slice its own block out of the full plan.
- Close the diff-scoped-reviewer gap *in the prose/agent-judgment layer* without
  adding a machine gate, preserving the deliberate trust/audit architecture.
- Stop silently discarding Minor findings between per-task review and the final
  whole-branch review.
- Replicate every template change across the two execution surfaces that carry
  the orchestration body, and lock the prose with `tests/test_docs_consistency.py`
  tokens so it cannot silently rot.

## Non-Goals

- **No worktree, branch, or protection boundary.** Execution stays in-place on
  the current branch — a core r2p invariant. The superpowers
  `using-git-worktrees` / `finishing-a-development-branch` integration is
  explicitly **not** borrowed.
- **No bundled extraction *script*.** superpowers ships `scripts/task-brief` and
  `scripts/review-package` as skill-dir bash. r2p puts the extraction in the
  **Python CLI**; the only shell added is the standard thin `tools/r2p-task-brief`
  passthrough wrapper, identical in shape to the existing `r2p-*` wrappers.
- **No machine-gate, state-transition, or schema change.** `gates.py` is
  untouched. `r2p-task-brief` performs **no** status transition; `state.py` and
  `artifact.py` are read-only consumers.
- **No change to any existing command's output contract.** `r2p-task-brief` adds
  a new command with its own output (text + `R2P_JSON=1` object); no existing
  JSON payload changes.
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

**Command-surface facts (for FR-CM5).** The `r2p-*` surface is three layers: a
bash wrapper `tools/r2p-<name>` → an `agent_shortcuts.py` subcommand → one or
more `cli.py` subcommands via `_run_cli`. The installer **discovers wrapper
sources from the `tools/r2p-*` files on disk** and renders `{{R2P_BIN_DIR}}`
(`tools/workflow_cli/install.py` bin-dir copy loop; wrappers are shared across
platform manifests), so adding a new wrapper file needs **no** install-list
edit.

**Conclusion of the current-state read:** both machine gates are *deliberately*
audit-only. The truth of a checkbox or verdict is the controller's
responsibility, established in prose through the task-reviewer loop. This is the
architecture FR-CM3 must live inside — in the agent-judgment layer, adding **no**
new machine gate.

## Functional Requirements

Template prose lands in **both** orchestration surfaces (see Target Surfaces).
Gemini `r2p-execute.toml` has no body and is unchanged.

### FR-CM1: Task handoff as a brief file + minimal implementer return contract

**Where:** `r2p-execute` §2 ("Dispatch a fresh implementer subagent") and the
"The implementer must:" list.

**Add a controller-context principle** near the top of the Per-Task Loop (one
line):

> Everything you paste into a dispatch and everything a subagent returns stays
> resident in your context and is re-read every turn. Hand artifacts as file
> paths; keep returns to a few lines.

**Change the task handoff** to use FR-CM5's command (replacing "Provide the
subagent with: The task text (from `07-plan.md`)"):

> - Run `{{R2P_BIN_DIR}}/r2p-task-brief --work-id <id> --task N` and hand the
>   implementer the **printed brief path** as its requirements ("read this first
>   — it is your task, with the exact values to use verbatim"). Do **not** paste
>   the task text into the dispatch, and do **not** point the implementer at the
>   whole `07-plan.md`.

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

### FR-CM5: `r2p-task-brief` — single-task extraction command

A read-only command that extracts one frozen PLAN task to a brief file, so the
controller hands a path (FR-CM1) and the implementer reads a file containing
exactly its task. Deterministic CLI extraction replaces an agent slicing its own
block out of the full plan.

**Three-layer surface (matching the existing `r2p-*` shape):**

- **CLI subcommand** (proposed name `plan-task-brief`) in `cli.py`:
  `--work-id <id> --task <N>`. Loads the frozen PLAN via
  `read_artifact(run_dir, Stage.PLAN)`, applies `strip_readonly_sections`,
  locates the `### PLAN-TASK-N` body using the existing anchor primitives
  (`plan_task_anchors` and the `_iter_plan_task_bodies` family — promote a small
  public helper if needed; do **not** duplicate anchor parsing), and writes the
  task body to `.req-to-plan/<work-id>/logs/task-N-brief.md` via
  `atomic_write_text`, rejecting a symlinked `logs/` or target with the same
  `_reject_symlink_or_exit` discipline `run-execute-start` uses for its
  `execution/` write. Prints the brief path; under `R2P_JSON=1` emits
  `{work_id, task_id, brief_path}`. **Read-only w.r.t. run state — no status
  transition.** Exit codes from `output.py`: `EXIT_NOT_FOUND` when the run, the
  PLAN artifact, or the requested `PLAN-TASK-N` is missing; `EXIT_OK` on success.
- **Shortcut subcommand** `task-brief` in `agent_shortcuts.py`: resolves the
  active run (or `--work-id`) and passes through via
  `_run_cli(["plan-task-brief", "--work-id", id, "--task", n])`. Register it in
  the subparser table and the `handlers` dict next to `execute`.
- **Wrapper** `tools/r2p-task-brief`: mirrors the existing wrappers
  (`exec python3 -m tools.workflow_cli.agent_shortcuts task-brief "$@"`).
  Auto-discovered by the installer; no install-list edit.

**Brief-file placement.** Under the run's gitignored `logs/` scratch
(`<work-id>/logs/` is ignored per `.req-to-plan/.gitignore`), the same lifecycle
class as the FR-A2 diff scratch. Briefs are ephemeral dispatch input — never
tracked, never under `execution/`. They therefore touch no archive gate
(`check_execution_complete` reads `execution/progress.md` only).

## Conflict Analysis (the explicit review)

This requirement was checked against r2p's existing adjudication/checkbox
mechanism and command surface before being written. Findings:

| Dimension | Finding |
|---|---|
| **Machine-gate conflict** | **None.** FR-CM1–CM4 touch only prose and free-text ledger lines; FR-CM5 writes only gitignored `logs/` scratch. `check_execution_complete` parses only `- [ ]`/`- [x] PLAN-TASK-\d+`; `check_final_review_recorded` parses only the last `Verdict:`. Neither structural marker is altered. |
| **CLI/agent-boundary fit (FR-CM5)** | **In-grain.** `r2p-task-brief` *extracts* frozen PLAN text; it does not *generate* prose, so it does not cross "the CLI never generates artifact prose". `run-execute-start` already extracts PLAN-TASK anchors with the same primitives — direct precedent. |
| **State/transition impact (FR-CM5)** | **None.** Read-only w.r.t. run state; no `ALLOWED_TRANSITIONS` change; output is a new command's own contract, not a change to an existing payload. |
| **Design-philosophy fit (FR-CM3)** | **Reinforces.** FR-CM3 places adjudication in the agent-judgment layer — exactly where the audit-only architecture wants it. It adds **no** machine gate; a hypothetical "⚠️ resolved" machine gate would *violate* the deliberate audit-only decision and is therefore excluded. |
| **Single prose-integration risk (FR-CM3)** | **One, mitigated.** Naively, FR-CM3 could create a *second* checkbox authority ("controller decides to flip") competing with "flip only when reviewer clean". The binding wording folds ⚠️ resolution *into* "reviewer clean" and routes confirmed gaps back through the implementer → re-review loop, so the reviewer-clean rule stays the single authority. |
| **Responsibility overlap (disclosed)** | The final whole-branch review already re-walks the full PLAN task-by-task on the whole-branch diff, so it is the existing backstop for "requirement in unchanged / cross-task code". FR-CM3 is an **earlier, cheaper catch** (and it prevents the task-reviewer from emitting a *false* spec ❌ on a requirement it structurally cannot see, avoiding a needless fix loop) — **not** a unique safety net. |
| **FR-CM4 ledger-format gotcha** | Minor lines must be plain `Minor:` bullets. A `- [ ] PLAN-TASK-N`-shaped Minor line would match `_LEDGER_UNCHECKED_RE` and block the completion gate. Encoded in the FR-CM4 wording and a docs-consistency token. |

## Target Surfaces / Files

1. `tools/workflow_cli/cli.py` — new `plan-task-brief` subcommand (handler +
   registration in the relevant `_register_*_commands`).
2. `tools/workflow_cli/agent_shortcuts.py` — new `task-brief` subparser + handler
   (thin passthrough).
3. `tools/r2p-task-brief` — new wrapper (auto-discovered by the installer).
4. `tools/workflow_cli/agent_templates/claude/commands/r2p-execute.md` — FR-CM1–CM4 prose.
5. `tools/workflow_cli/agent_templates/codex/skills/r2p-execute/SKILL.md` — same prose (the two bodies are kept textually in sync; the docs-consistency token gate enforces parity).
6. `tools/workflow_cli/agent_templates/gemini/commands/r2p-execute.toml` — **unchanged** (4-line pointer, no orchestration body).
7. `tests/test_cli.py` — tests for `plan-task-brief` (see Test Plan).
8. `tests/test_docs_consistency.py` — extend the
   `test_execute_surfaces_carry_sdd_orchestration_tokens` required tuple with the
   new guard tokens (below), including `r2p-task-brief`.

## Acceptance Criteria

- `r2p-task-brief --work-id <id> --task N` writes `logs/task-N-brief.md`
  containing exactly task N's body (from the frozen, read-only-stripped PLAN),
  prints the path, and emits `{work_id, task_id, brief_path}` under `R2P_JSON=1`;
  it performs no status transition.
- Missing run/PLAN/task → `EXIT_NOT_FOUND`; a symlinked `logs/` or target is
  refused.
- Both orchestration surfaces hand the implementer the **brief path** from
  `r2p-task-brief` (no pasted task text, no "read the whole plan file").
- Both surfaces state the minimal implementer return contract (status / commit
  range / one-line test summary / concerns; full report → `task-N-report.md`).
- Both surfaces carry the narration ceiling line.
- Both surfaces' §6 flip condition subsumes "no unresolved ⚠️ cannot-verify
  item", with confirmed gaps routed back through implementer → re-review and an
  explicit "never flip on your own judgment".
- Both surfaces record Minor findings as plain `Minor:` bullets and point the
  final review at them; neither uses the `- [ ] PLAN-TASK-N` shape for Minors.
- No change to `gates.py`, any state transition, any artifact schema, or any
  existing command's output contract.
- `tests/test_cli.py` and `tests/test_docs_consistency.py` pass with the new
  cases/tokens; the full suite stays green.

## Test Plan

**`tests/test_cli.py`** (local `invoke()` helper + `tempfile.TemporaryDirectory`,
`base_path=Path(tmp)`; never touch the real workspace):

- happy path: seed a run with a frozen PLAN containing `### PLAN-TASK-001..00N`;
  `plan-task-brief --task 2` writes `logs/task-2-brief.md` whose content is
  exactly task 2's body and excludes read-only sections; `R2P_JSON=1` payload
  carries `brief_path`/`task_id`.
- missing task / missing PLAN / unknown work-id → `EXIT_NOT_FOUND`.
- symlinked `logs/` or target brief path → refusal (no write through the link).
- the brief lands under `logs/` (gitignored), not under `execution/`.

**`tests/test_docs_consistency.py`** — extend
`test_execute_surfaces_carry_sdd_orchestration_tokens` (claude + codex) with
stable tokens, e.g.:

- `"r2p-task-brief"` (FR-CM1/CM5 handoff)
- `"cannot verify from diff"` (FR-CM3)
- `"never flip the checkbox on your own judgment"` (FR-CM3 single-authority)
- `"returns **only**"` or an equivalent stable literal (FR-CM1 return contract)
- `"Narration:"` (FR-CM2)
- `"Minor:"` plus a literal forbidding the `- [ ] PLAN-TASK-N` shape (FR-CM4)

Token strings are finalized against the exact prose during implementation so the
test asserts the wording that ships.

## Risks

- **Wording drift between the two surfaces.** Mitigated by the docs-consistency
  token gate (any new required token must appear in both files).
- **Over-tokenizing the test.** Keep tokens to stable, load-bearing phrases; do
  not pin incidental wording, which would make routine edits brittle.
- **FR-CM3 misread as a new gate.** Mitigated by the explicit "no machine-gate
  change" statement and the single-authority wording.
- **FR-CM5 surface creep.** Three layers (CLI + shortcut + wrapper) plus tests
  is more than a prose change. Bounded by reusing existing extraction primitives
  and the auto-discovered wrapper path; no install-list or gate edits.

## Implementation Sequencing

FR-CM5 is the dependency for FR-CM1's task handoff, so land the CLI command
first, then wire the templates:

1. **FR-CM5** — `plan-task-brief` CLI subcommand + `task-brief` shortcut +
   `tools/r2p-task-brief` wrapper + `tests/test_cli.py`. Independently
   shippable and verifiable on its own.
2. **FR-CM1–CM4** — template prose on both surfaces + `tests/test_docs_consistency.py`
   tokens (FR-CM1 references the command from step 1).

Each phase is independently mergeable: after phase 1 the command exists and is
tested even if the template wiring never lands.

## Verification Commands

```bash
# Local: must use the venv (system python3 lacks pyyaml).
.venv/bin/python -m pytest tests/test_cli.py -v -k task_brief
.venv/bin/python -m pytest tests/test_docs_consistency.py -v
.venv/bin/python -m pytest tests/ -q          # full suite stays green
```

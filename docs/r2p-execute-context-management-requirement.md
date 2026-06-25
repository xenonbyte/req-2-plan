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
read-only CLI extraction command** (and its shortcut + wrapper) and route both
the implementer and the reviewer task-handoffs through it. The change touches no gate, no state transition, no
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

- **Task text leaks three ways, not one.** The controller pulls each task's text
  into its own context through **three** channels, every one resident and
  compounding across the run: (1) §1 "Extract task inline" tells the controller
  to *read the task text directly from `07-plan.md`*; (2) §2 hands "The task text
  (from `07-plan.md`)" into the **implementer** dispatch; (3) §5 hands "The task
  text and `Spec References` from `07-plan.md`" into the **task-reviewer**
  dispatch. Pointing a subagent at the whole `07-plan.md` instead only trades the
  paste for a worse leak — superpowers names "make a subagent read the whole plan
  file" an explicit red flag. The deterministic fix is to extract exactly one
  task to a brief file once (FR-CM5) and route all three channels through its
  path, so neither the controller, the implementer, nor the reviewer sees more
  than the one task.
- **Reports leak back.** There is no minimal-return contract, so an implementer
  can return its full report into the controller's context even though the
  report is also written to `execution/task-N-report.md`.
- **Controller narration leaks.** No narration ceiling, so coordination turns
  can accrete prose that the ledger and tool results already record.
- **Diff-scoped reviewer blindness is ungated.** The task-reviewer's only
  independent window into the implementation is the single-task diff
  (`logs/task-N-diff.md`); requirements satisfied in *unchanged* code, or
  spanning tasks, are not confirmable from it. Worse, the current §5 reviewer
  contract asks only for two verdicts (spec compliance, code quality) with no
  channel to flag "I cannot verify this from the diff", so the reviewer must
  pass-or-fail such a requirement blindly — and the §6 flip rule keys solely on
  "task-reviewer clean", so the checkbox flips on a blind pass.

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
| Controller holds task text via §1 read, §2 implementer paste, §5 reviewer paste | Resident in the **controller** context, re-read **every turn, compounds** across the run | FR-CM1 routes §2 + §5 through the brief **path** and trims §1 to an on-demand brief re-read (no eager per-task body in context) | low |
| Implementer / reviewer reads the whole plan | Lands in a **one-shot** subagent context, discarded after the task, **does not compound** | FR-CM5 deterministic single-task extraction | one CLI command + wrapper + tests |

FR-CM5 is in-grain and cheap because the machinery already exists:
`run-execute-start` (`tools/workflow_cli/cli.py:746`) already extracts PLAN-TASK
anchors with `plan_task_anchors(strip_readonly_sections(plan_text))` to seed
`execution/progress.md`. Extracting one task *body* to a brief file is the same
class of structural operation — **extraction of frozen PLAN text, not
generation of prose** — so it does not cross the "CLI never generates artifact
prose" boundary.

**Disclosed residual (the controller is never fully plan-blind).** The controller
still reads the whole `07-plan.md` **once** at Pre-flight — scanning for cross-task
contradictions is structurally whole-plan. That read is for the contradiction
scan, not a durable per-task cache: §6 ⚠️ adjudication re-reads the brief and the
specific cited SPEC/sibling on demand rather than trusting the Pre-flight read to
still be resident after compaction. FR-CM5's win is removing the *per-task,
compounding* re-reads and dispatch pastes, not making the controller plan-blind.
`## Global Constraints` is likewise still pasted per reviewer dispatch (short,
shared) and is intentionally left as-is.

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
more `cli.py` subcommands via `_run_cli`. The installer's copy loop and
`_install_targets` both iterate `repo_root.glob("tools/r2p-*")`
(`tools/workflow_cli/install.py`), render each via `_render_bin_script`, and
share the wrappers across platform manifests — so dropping a new
`tools/r2p-task-brief` file is auto-discovered and needs **no** install-list
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

**Where:** `r2p-execute` §1 ("Extract task inline"), §2 ("Dispatch a fresh
implementer subagent") and its "The implementer must:" list, and §5 (the
task-reviewer dispatch). One brief, produced once in §1, is the shared task
reference for **both** the implementer (§2) and the reviewer (§5).

**Add a controller-context principle** near the top of the Per-Task Loop (one
line):

> Everything you paste into a dispatch and everything a subagent returns stays
> resident in your context and is re-read every turn. Hand artifacts as file
> paths; keep returns to a few lines.

**§1 — produce the brief instead of reading the task inline.** Rename the step
away from "Extract task inline" (e.g. "Produce the task brief") and replace "Read
the task text directly from `07-plan.md`" with:

> - Run `{{R2P_BIN_DIR}}/r2p-task-brief --work-id <id> --task N` to write the
>   one-task brief (`logs/task-N-brief.md`) and note its path. Do **not** eager-read
>   the full task body into your own context — the goal is to avoid holding every
>   task body at once, not to never read one. Re-open the brief on demand when it
>   actually informs a decision: sizing the implementer's model (§2), or
>   adjudicating a §6 ⚠️ item — and for a cross-task ⚠️, read the specific cited
>   SPEC ID or sibling task it turns on. Do **not** lean on the Pre-flight
>   whole-plan read still being resident; on the long runs where execution lives it
>   may have been compacted away, so the durable source is the brief and the cited
>   upstream on disk.

**§2 — hand the implementer the brief path** (replacing "Provide the subagent
with: The task text (from `07-plan.md`)"):

> - Hand the implementer the **brief path** from §1 as its requirements ("read
>   this first — it is your task, with the exact values to use verbatim"). Do
>   **not** paste the task text into the dispatch, and do **not** point the
>   implementer at the whole `07-plan.md`.

**§5 — hand the task-reviewer the same brief path** (replacing "The task text and
`Spec References` from `07-plan.md`" in the reviewer-dispatch list):

> - The brief path from §1 (`logs/task-N-brief.md`) — it already carries the task
>   body, `Spec References`, and `Verification`. Do **not** re-paste the task text
>   or Spec References into the reviewer dispatch.

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

**Where:** `r2p-execute` §5 (task-reviewer dispatch contract) **and** §6 (the
checkbox-flip condition). **No machine-gate change.** (Orthogonal to FR-CM1's §5
edit: FR-CM1 changes the reviewer's *task-reference input* to the brief path;
FR-CM3 changes only the reviewer's *verdict output*.)

The task-reviewer's only independent window into the implementation is the
single-task diff, so requirements that live in unchanged code or span tasks are
not confirmable from it. Today the §5 contract gives the reviewer only two
verdicts and no way to abstain, so it must pass-or-fail such requirements
blindly. FR-CM3 adds the missing *output* channel (§5) and then the controller
*resolves* it (§6) — without becoming a second checkbox authority.

**Produce side — amend the §5 reviewer contract** so the spec verdict is
✅ / ❌ / ⚠️-defer, not binary:

> For any requirement in `Spec References` / `Verification` that the single-task
> diff does not let you confirm (it may be met in unchanged code, or span tasks),
> do **not** silently pass or fail it — flag it as a ⚠️ "cannot verify from diff"
> item for the controller to adjudicate.

**Consume side — amend the §6 flip condition (the binding wording):**

> Flip `- [x]` only when the task-reviewer is clean — spec ✅, quality Approved,
> `Verification` satisfied, **and no unresolved ⚠️ "cannot verify from diff" item
> remains**. The task-reviewer's only independent view of the change is the diff;
> resolve each ⚠️ yourself by reading the cited SPEC/sibling task it turns on
> (the cross-task and PLAN context the reviewer lacks) and the relevant
> implementation/test evidence that proves or disproves the item. Record each ⚠️
> outcome in `execution/progress.md` before the flip decision:
> `Resolved:` when durable evidence shows the requirement is already satisfied
> (for unchanged-code claims, cite the relevant implementation path/function and
> test or tool output, not only the SPEC/sibling task); `Gap:` when the evidence
> shows missing work; `Unresolved:` when the evidence still does not prove
> satisfaction. Only `Resolved:` clears the ⚠️.
> A `Gap:` is a failed spec review: send it back to the implementer and
> re-review. An `Unresolved:` item blocks the flip. Never flip the checkbox by
> overriding a `Gap:` or `Unresolved:` item on your own judgment.

This keeps "checkbox flips only when the reviewer is clean" as the single
authority: the controller can clear a reviewer ⚠️ only by recording durable
evidence for a `Resolved:` outcome; it cannot override a confirmed gap or
unresolved item. Confirmed gaps still go through the existing implementer →
re-review loop.

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
  `--work-id <id> --task <N>`. Resolve `N` by **integer value** — select the task
  whose `### PLAN-TASK-<digits>` anchor satisfies `int(digits) == N`, so a
  zero-padded `PLAN-TASK-002` is matched by `--task 2`, mirroring how the PLAN
  quality gate parses task numbers (`int(m.group(1))`, `gates.py:532`).
  Contiguous-from-1, unique numbering is **not assumed** — the PLAN quality gate
  enforces it (`_check_plan_task_fields`, `gates.py:570-571`) before a run can
  close at the PLAN checkpoint, so execution only ever sees a clean `1..N` task
  set. The brief copies the task body verbatim, including its literal
  `### PLAN-TASK-<digits>` heading, so the controller flips the matching ledger
  checkbox by that literal ID. Loads the frozen PLAN via
  `read_artifact(run_dir, Stage.PLAN)` (which raises `FileNotFoundError` on a
  missing PLAN — map to `EXIT_NOT_FOUND`, exactly as `run-execute-start` already
  does). The command is valid only while the run status is `EXECUTING`; every
  other existing run status returns `EXIT_CONFLICT` without writing, because task
  briefs are execution scratch, not a way to inspect draft or archived runs.
  It applies `strip_readonly_sections`, and selects the `### PLAN-TASK-N`
  body with the existing **public** primitive
  `markdown.heading_bounded_bodies(content, PLAN_TASK_ANCHOR_RE.match)` — the
  same call `gates._iter_plan_task_bodies` wraps (`gates.py:301`); it yields each
  heading-bounded task body, so **no new parsing is added**. Writes the task body
  to `.req-to-plan/<work-id>/logs/task-N-brief.md` via `atomic_write_text`
  (`atomic.py:9`), rejecting a symlinked `logs/` or target with the same
  `_reject_symlink_or_exit` discipline (`cli.py:165`) `run-execute-start` uses
  for its `execution/` write. Prints the brief path; under `R2P_JSON=1` emits
  top-level success fields `{work_id, task_id, brief_path}` where `work_id` is
  the canonical work ID string, `task_id` is the literal matched anchor such as
  `PLAN-TASK-002`, and `brief_path` is the repository-root-relative path
  `.req-to-plan/<work-id>/logs/task-N-brief.md`. **Read-only w.r.t. run state — no status
  transition.** Exit codes from `output.py`: `EXIT_NOT_FOUND` when the run, the
  PLAN artifact, or the requested `PLAN-TASK-N` is missing; `EXIT_CONFLICT` when
  the existing run is not `EXECUTING`, or when `logs/` or the target brief path
  is a symlink (via `_reject_symlink_or_exit`); `EXIT_OK` on success.
- **Shortcut subcommand** `task-brief` in `agent_shortcuts.py`: resolves the
  active run (or `--work-id`) and passes through via
  `_run_cli(["plan-task-brief", "--work-id", id, "--task", n])`. Register it in
  the subparser table and the `handlers` dict next to `execute`.
- **Wrapper** `tools/r2p-task-brief`: mirrors the existing wrappers
  (`exec python3 -m tools.workflow_cli.agent_shortcuts task-brief "$@"`).
  Auto-discovered by the installer; no install-list edit.

**Brief-file placement.** Under the run's `logs/` scratch
(`.req-to-plan/.gitignore` ignores `/*/logs/`, so every run's `logs/` is
untracked), the same lifecycle class as the FR-A2 diff scratch. Briefs are
ephemeral dispatch input — never tracked, never under `execution/`. They
therefore touch no archive gate (`check_execution_complete` reads
`execution/progress.md` only).

**Primitives verified against code (FR-CM5 feasibility).** No new parsing,
write, or symlink logic is introduced — every building block already exists and
was confirmed: `read_artifact(run_dir, Stage.PLAN) -> str` raising
`FileNotFoundError` (`artifact.py:108`); `strip_readonly_sections`
(`markdown.py:62`); `heading_bounded_bodies` + `PLAN_TASK_ANCHOR_RE`
(`markdown.py`, the primitive `gates._iter_plan_task_bodies` wraps at
`gates.py:301`); `atomic_write_text` (`atomic.py:9`); `_reject_symlink_or_exit`
(`cli.py:165`); exit-code constants (`output.py`). Installer auto-discovery is
confirmed by the `repo_root.glob("tools/r2p-*")` loops in `install.py`.

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
| **Checkbox-identity alignment (FR-CM5 ↔ completion gate)** | **Consistent, gate-verified.** `--task N` resolves by integer to the literal `PLAN-TASK-<digits>` ID; the brief carries that literal heading; the controller flips that literal ledger ID; `check_execution_complete` audits the same literal IDs (`_LEDGER_CHECKED_RE` / `_plan_task_ids`). Contiguous-from-1 uniqueness is enforced upstream at the PLAN quality gate (`_check_plan_task_fields`, `gates.py:570-571`), so execution never sees a gapped/duplicate task set and the four ID surfaces cannot desync. FR-CM3 only tightens *when* the flip happens; the machine completion gate backstops it unchanged. |

## Target Surfaces / Files

1. `tools/workflow_cli/cli.py` — new `plan-task-brief` subcommand (handler +
   registration in the relevant `_register_*_commands`).
2. `tools/workflow_cli/agent_shortcuts.py` — new `task-brief` subparser + handler
   (thin passthrough).
3. `tools/r2p-task-brief` — new wrapper (auto-discovered by the installer).
4. `tools/workflow_cli/agent_templates/claude/commands/r2p-execute.md` — FR-CM1–CM4 prose.
5. `tools/workflow_cli/agent_templates/codex/skills/r2p-execute/SKILL.md` — same prose intent (the docs-consistency token gate enforces load-bearing token coverage across both surfaces).
6. `tools/workflow_cli/agent_templates/gemini/commands/r2p-execute.toml` — **unchanged** (4-line pointer, no orchestration body).
7. `tests/test_cli.py` — tests for `plan-task-brief` (see Test Plan).
8. `tests/test_docs_consistency.py` — extend the
   `test_execute_surfaces_carry_sdd_orchestration_tokens` required tuple with the
   new guard tokens (below), including `r2p-task-brief`.

## Acceptance Criteria

- `r2p-task-brief --work-id <id> --task N` resolves `N` by integer value (a
  zero-padded `PLAN-TASK-002` is selected by `--task 2`) and writes
  `logs/task-N-brief.md` containing exactly that task's body (from the frozen,
  read-only-stripped PLAN, including its literal `### PLAN-TASK-<digits>`
  heading), prints the path, and emits `{work_id, task_id, brief_path}` under
  `R2P_JSON=1` where `task_id` is the literal matched anchor and `brief_path` is
  the repository-root-relative `.req-to-plan/<work-id>/logs/task-N-brief.md`;
  it performs no status transition and is valid only for `EXECUTING` runs.
- Missing run/PLAN/task → `EXIT_NOT_FOUND`; non-`EXECUTING` existing run,
  symlinked `logs/`, or symlinked target → `EXIT_CONFLICT` (no write through the
  link).
- Both orchestration surfaces produce the brief once in §1 (the controller does
  **not** deep-read the full task body) and hand the **same brief path** to both
  the implementer (§2) and the task-reviewer (§5) — no pasted task text on either
  dispatch, no "read the whole plan file".
- Both surfaces state the minimal implementer return contract (status / commit
  range / one-line test summary / concerns; full report → `task-N-report.md`).
- Both surfaces carry the narration ceiling line.
- Both surfaces' §5 reviewer contract instructs the task-reviewer to emit ⚠️
  "cannot verify from diff" items (spec verdict becomes ✅ / ❌ / ⚠️-defer).
- Both surfaces' §6 flip condition subsumes "no unresolved ⚠️ cannot-verify
  item", records each ⚠️ as `Resolved:`, `Gap:`, or `Unresolved:`, routes
  confirmed gaps back through implementer → re-review, blocks unresolved items,
  requires implementation/test evidence for unchanged-code `Resolved:` claims,
  and forbids overriding a gap or unresolved item on the controller's own
  judgment.
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
  carries the full command payload as top-level fields, including `work_id: "<work-id>"`,
  `task_id: "PLAN-TASK-002"`, and repository-root-relative
  `brief_path: ".req-to-plan/<work-id>/logs/task-2-brief.md"`; existing
  success metadata fields such as `status` / `message` may also be present.
- integer resolution: a zero-padded anchor `### PLAN-TASK-002` is selected by
  `--task 2` (integer match, not string equality against `PLAN-TASK-2`).
- missing task / missing PLAN / unknown work-id → `EXIT_NOT_FOUND`.
- non-`EXECUTING` existing run statuses → `EXIT_CONFLICT` and no brief write.
- symlinked `logs/` or target brief path → `EXIT_CONFLICT` (no write through the
  link).
- the brief lands under `logs/` (gitignored), not under `execution/`.
- shortcut/wrapper coverage: `agent_shortcuts task-brief --work-id <id> --task 2`
  and `tools/r2p-task-brief --work-id <id> --task 2` reach the same extraction
  path and preserve the same text/JSON payload contract as `plan-task-brief`.

**`tests/test_docs_consistency.py`** — extend
`test_execute_surfaces_carry_sdd_orchestration_tokens` (claude + codex) with
stable tokens, e.g.:

- `"r2p-task-brief"` (FR-CM1/CM5 handoff)
- a stable literal asserting the **reviewer** dispatch receives the brief path
  rather than pasted task text (FR-CM1 §5)
- `"cannot verify from diff"` (FR-CM3)
- `"never flip the checkbox on your own judgment"` (FR-CM3 single-authority)
- `"returns **only**"` or an equivalent stable literal (FR-CM1 return contract)
- `"Narration:"` (FR-CM2)
- `"Minor:"` plus a literal forbidding the `- [ ] PLAN-TASK-N` shape (FR-CM4)

Token strings are finalized against the exact prose during implementation so the
test asserts the wording that ships.

## Risks

- **Wording drift between the two surfaces.** Mitigated by docs-consistency
  coverage of load-bearing tokens across both files. This does not prove textual
  parity; it prevents the specific orchestration requirements from silently
  disappearing from either surface.
- **Over-tokenizing the test.** Keep tokens to stable, load-bearing phrases; do
  not pin incidental wording, which would make routine edits brittle.
- **FR-CM3 misread as a new gate.** Mitigated by the explicit "no machine-gate
  change" statement and the single-authority wording.
- **FR-CM5 surface creep.** Three layers (CLI + shortcut + wrapper) plus tests
  is more than a prose change. Bounded by reusing existing extraction primitives
  and the auto-discovered wrapper path; no install-list or gate edits.
- **Controller under-reads and cannot adjudicate ⚠️.** Trimming §1 to a brief
  pointer could starve the FR-CM3 ⚠️ resolution of context. Mitigated: the
  Pre-flight whole-plan read remains only the initial contradiction scan; §6
  adjudication re-reads the durable brief and the cited SPEC/sibling task on
  disk. §1's trim removes only the *redundant per-task re-read*, not the
  controller's ability to fetch the exact context needed for a ⚠️ decision.

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

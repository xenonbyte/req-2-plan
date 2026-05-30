# Workflow Fixes + PLAN Optimization — Implementation Plan

**Status:** Proposed — revised after review round 1 (awaiting re-review)
**Date:** 2026-05-30
**Author:** req-to-plan maintainers (via /think workflow)

> **Review round 1 — all six findings accepted (verified against code, 2026-05-30):**
> - **R1** `stage-advance` must enter the authoritative command model, not just cli.py
>   (`command-surface.md:220/350` map continue-after-approval to `CMD-RUN-RESUME`). → §1.5a.
> - **R2** `review-checkpoint` conflicts with the findings-writing `CMD-REVIEW-CHECKPOINT`
>   contract (`command-surface.md:157`). Resolved as an explicit MVP downgrade. → §1.5 row + KD2.
> - **R3** `r2p-continue` order was backwards and auto-ran `stage-ready`; real order is
>   `stage-ready` then `gate-quality` (`operator-runbook.md:150/180`). → §1.6.
> - **R4** `checkpoint-decide`/`stage-advance` need stronger precondition checks
>   (stage==current, artifact exists/ready, version match, no duplicate approval). → §1.5 shared checks.
> - **R5** `changes_requested` loop isn't closed: `stage-update` (`cli.py:712`) never flips
>   status back to draft. → §1.6a.
> - **R6 (Part 3)** gate needs a fixed machine-parseable PLAN task schema first, or it's a
>   fragile Markdown guess. → §3.0.

**Scope (three parts):**
1. **Close the end-to-end loop** — wire the missing approve/advance state transitions so a run reaches `CLOSED_AT_PLAN_CHECKPOINT` purely through CLI/shortcut commands; make `r2p-continue` a real driver.
2. **Remove the superpowers adapter** — delete the redundant post-PLAN executor-adaptation layer.
3. **Optimize PLAN generation** — make the neutral PLAN directly executable: executable anchors, Context7 version verification, checkbox tracking, linear readability.

The three parts are independent and touch mostly disjoint files. **Recommended order: Part 1 → Part 2 → Part 3.** Part 1 first because it makes real end-to-end runs possible, which both other parts' verification benefits from. There is no hard dependency; any part can be done alone. One cross-part reconciliation is flagged inline (Part 1's `_cmd_continue` must not reference `r2p-adapt`, which Part 2 deletes).

---

## Shared audit findings (2026-05-30)

A /think audit of the workflow produced these facts (verified line-by-line against the code, and against the real run `forma/.req-to-plan/WF-20260528-design-v8-pencil-open-design/`):

- The state machine defines a full checkpoint loop; `cli.py` wires only ~half the transitions, so `READY_FOR_CHECKPOINT_REVIEW` is a dead end and `run-close` is unreachable through commands. The suite passes (494 test functions as of 2026-05-30; note `CLAUDE.md` still says 460 and `.claude/skills/req-to-plan.md` says 397 — both stale, fix in passing) but none drive a run start→close via CLI. → **Part 1**
- `r2p-continue` only calls read-only `run-resume`, so the documented "call repeatedly until closed" never advances; it echoes the same resume context forever. → **Part 1**
- The superpowers adapter produced `superpowers-plan.md.repair.md` (an adapter-gap repair file) on the real forma run — the neutral→executor translation both is redundant (the neutral PLAN runs in superpowers as-is) and failed in practice. → **Part 2**
- PLAN/SPEC artifacts are strong on traceability (stable IDs, coverage closure, verification ideas) but weak on executability: **0 code blocks vs superpowers' 142**, no Context7 version-check section, **0 checkboxes**. → **Part 3**
- BDD/TDD placement is already correct and present (`workflow-invariants.md` BDD/TDD Placement Rule; `plan-workflow.md` TDD Decomposition). **No change needed there.**

---

# Part 1 — Close the End-to-End Loop

## 1.1 Problem

Transitions actually wired today (verified line-by-line):

| Command | Transition |
|---|---|
| `run-start` | `NOT_STARTED → ACTIVE_STAGE_DRAFT` |
| `gate-entry` | `→ ENTRY_GATE_FAILED` / `→ ACTIVE_STAGE_DRAFT` (cli.py:675/697) |
| `gate-quality` | `→ QUALITY_GATE_FAILED` / `→ READY_FOR_CHECKPOINT_REVIEW` (cli.py:555/574) |
| `stage-ready` | marks artifact ready (cli.py:762) |
| `run-close` | `CHECKPOINT_APPROVED → CLOSED_AT_PLAN_CHECKPOINT` (cli.py:253) |

None of the 15 implemented subcommands can produce `CHECKPOINT_REVIEW`,
`CHECKPOINT_APPROVED`, `CHECKPOINT_CHANGES_REQUESTED`, or `NEXT_STAGE`. Consequences:

- `READY_FOR_CHECKPOINT_REVIEW` is a dead end — nothing exits it.
- `run-close` requires `CHECKPOINT_APPROVED`, but no command reaches that state.
- No stage-advance command exists, so a run cannot move design → spec → plan.

Evidence in the test suite: every test that needs an approved state sets
`record.status = RunStatus.CHECKPOINT_APPROVED` by direct in-memory mutation
(`tests/test_cli.py:372/388/413`), and the integration helper `_force_to_closed`
also assigns the status directly (`tests/test_integration.py:45`). There is no
end-to-end test that drives a run from start to close through CLI commands —
because it is currently impossible.

The command contracts are already specified in the docs — this is a
"designed-but-unimplemented" gap, not an open design question:

- `docs/workflow-cli-adapter.md:299` — `workflow checkpoint-decide --work-id … --stage … --decision … --confirm`
- `docs/workflow-cli-adapter.md:449` — example `checkpoint-decide --work-id WF-001 --stage spec --decision approved --confirm`
- `docs/workflow-command-surface.md:157/159` — `CMD-REVIEW-CHECKPOINT`, `CMD-CHECKPOINT-DECIDE`
- `docs/workflow-cli-adapter.md:280/282` — both marked "Covered"

Documented `workflow <cmd>` surface = 37 commands. Implemented = 15.

## 1.2 Building / Not building

**Building:** Wire the missing "approve + advance" segment so a run moves from `run-start`
to `CLOSED_AT_PLAN_CHECKPOINT` purely through CLI/shortcut commands across all 6 stages.
Change `r2p-continue` from "read-only no-op" to an honest driver: it runs the mechanical
steps automatically and stops only at the two boundaries that need a human or an Agent —
"needs Agent-authored content" and "needs human approval". Align docs with the real flow.

**Not building (deferred):**
- Gap routing trio (`gap-record` / `gap-route` / `gap-reimport`), `checkpoint-bundle`,
  `confirm-*`, `subagent-*`, `stage-load`, `status-stage/routes/artifacts` — non-happy-path
  branches.
- run.md atomic write, `_unescape_cell` dead code, the two divergent work-id generators —
  robustness items.
- Rewriting `run-resume`'s dual-mode (context-refresh) semantics — see Key Decision 1.

## 1.3 Driving model (confirmed direction)

**Agent orchestrates + CLI holds state authority + checkpoints are human approvals.** Each
state transition = one explicit CLI subcommand + an `update_run_status` validation (same
style as existing `gate-quality` / `stage-ready`). The CLI never auto-approves — approval
is always a human stop point. This is the load-bearing invariant of the whole design.

> **Most fragile assumption:** checkpoint approval is intentionally reserved for a
> human/Main, not an overlooked automatic step. If the desired behavior were instead
> "unattended, CLI auto-approves all the way to close," the direction reverses — but that
> contradicts every doc and `docs/workflow-invariants.md` ("Subagents produce evidence,
> not approval"), and is not recommended.

## 1.4 Missing advance loop (the three transitions added here)

```
Today a run only reaches here ─┐
                               ▼
ACTIVE_STAGE_DRAFT ──gate-quality──▶ READY_FOR_CHECKPOINT_REVIEW
                                              │
                          ╔═══════════════════╪═══ added here ═══╗
                          ║   review-checkpoint▼                  ║
                          ║          CHECKPOINT_REVIEW            ║
                          ║   checkpoint-decide│                  ║
                          ║      ┌─────────────┼──────────┐       ║
                          ║ approved      changes_requested       ║
                          ║      ▼             ▼                  ║
                          ║ CHECKPOINT_   CHECKPOINT_             ║
                          ║  APPROVED     CHANGES_REQUESTED       ║
                          ║      │         (back to draft/repair) ║
                          ║      ▼ stage-advance (non-plan)       ║
                          ║  NEXT_STAGE ─▶ ACTIVE_STAGE_DRAFT     ║
                          ║      │          (next stage)          ║
                          ╚══════╪════════════════════════════════╝
                  plan stage approved│
                                     ▼ run-close (already exists)
                          CLOSED_AT_PLAN_CHECKPOINT
```

All target states (`CHECKPOINT_REVIEW` / `APPROVED` / `CHANGES_REQUESTED` / `NEXT_STAGE`)
are already defined in `ALLOWED_TRANSITIONS`; only the triggering commands are missing. The
state-machine table itself does not change.

## 1.5 New command contracts (cli.py)

**Shared precondition checks (all three commands; review finding R4).** Before any state
change, each command validates: `--stage == record.current_stage`; an active artifact for
that stage exists; the active artifact's recorded version matches the on-disk artifact
version; the artifact status is the one the command expects (e.g. `checkpoint-decide`
requires the stage's active artifact to be `ready`). `checkpoint-decide approved`
additionally refuses to re-approve a stage+version that already has an approved checkpoint
(no duplicate approval of the same version). Any failed check → exit 6, no state change.
These mirror the existing `stage-produce` guard at `cli.py:658` (`stage != current_stage`).

| Command | Args | Precondition | Action | Exit |
|---|---|---|---|---|
| `review-checkpoint` | `--work-id --stage` | `READY_FOR_CHECKPOINT_REVIEW` + shared checks | **MVP scope (review finding R2):** `update_run_status(CHECKPOINT_REVIEW)`; `resume_context.next="checkpoint_decide"`; record a minimal "review started / ready for human decision" marker only. It does **not** produce review findings or run merge — the full `CMD-REVIEW-CHECKPOINT` contract (write findings, require merge before decide; `command-surface.md:157`) is explicitly downgraded to this marker for the MVP. The downgrade is documented in 1.5a below and synced into the command-surface/cli-adapter docs. | OK; wrong state → 6 |
| `checkpoint-decide` | `--work-id --stage --decision {approved,changes_requested} [--confirm] [--downstream-authorization S]` | `CHECKPOINT_REVIEW` + shared checks | approved: requires `--confirm`, else exit 2; `add_checkpoint(stage, artifact, version, downstream_auth)` + `upsert_active_artifact(..., "approved")` + `update_run_status(CHECKPOINT_APPROVED)`; `downstream_authorization` defaults to the `NEXT_STAGE_MAP` next-stage name, and to `close_workflow_run` at the plan stage (matches existing run.md convention — verified in the forma run, not `"none"`). changes_requested: `update_run_status(CHECKPOINT_CHANGES_REQUESTED)` **and set `resume_context.next="repair_stage_artifact"` + `active_item=stage`** so the repair loop is reachable (see 1.6a, review finding R5). | OK; missing confirm → 2; wrong state → 6 |
| `stage-advance` | `--work-id` | `CHECKPOINT_APPROVED` and `current_stage != PLAN` + shared checks | `update_run_status(NEXT_STAGE)` → `update_run_status(ACTIVE_STAGE_DRAFT)`; `current_stage = NEXT_STAGE_MAP[cur]`; `resume_context(active_item=next, next="produce_stage_artifact")` | OK; plan stage → 6 (point to run-close); wrong state → 6 |

All three reuse existing `_load_run` / `add_checkpoint` / `update_run_status` / `mgr.save`;
no new serialization path is introduced.

### 1.5a Authoritative command-model sync (review finding R1)

`stage-advance` is a **new command intent**, not just a cli.py handler. The authoritative
matrix currently maps "continue after checkpoint approval" to `CMD-RUN-RESUME`
(`command-surface.md:220` — `checkpoint_approved` allows `CMD-RUN-RESUME`; and the
"Continue After Checkpoint Approval" section at `command-surface.md:350`). Adding a
dedicated command therefore requires updating the model layer and its docs, not only
`cli.py`:

- `models.py` — add `CMD-STAGE-ADVANCE` (and, if we keep `review-checkpoint`/`checkpoint-decide`
  as the MVP-scoped commands, ensure `CMD-REVIEW-CHECKPOINT` / `CMD-CHECKPOINT-DECIDE` are
  represented), and add them to `ALLOWED_COMMANDS_BY_RUN_STATE` for the right states
  (`CMD-STAGE-ADVANCE` under `CHECKPOINT_APPROVED`; `CMD-CHECKPOINT-DECIDE` under
  `CHECKPOINT_REVIEW`; `CMD-REVIEW-CHECKPOINT` under `READY_FOR_CHECKPOINT_REVIEW`/`CHECKPOINT_REVIEW`).
- `docs/workflow-command-surface.md` — add the `CMD-STAGE-ADVANCE` row and reconcile the
  `checkpoint_approved` row + "Continue After Checkpoint Approval" section so resume vs
  advance is unambiguous (advance = move to next stage draft; resume = read-only context
  refresh).
- `docs/workflow-cli-adapter.md` — add the `workflow stage-advance` mapping row.
- `tests/test_models.py` — assert the new command intents are allowed in exactly the right
  states and refused elsewhere.

**Alternative considered:** instead of a new `stage-advance` intent, extend `CMD-RUN-RESUME`
to perform the advance (matching the current matrix). Rejected for the same reason as Key
Decision 1 — the run-resume context-refresh exception is complex and many tests depend on
its read-only behavior. If the maintainer prefers fidelity to the existing matrix over a new
command, this is the one decision to revisit before implementing Part 1.

## 1.6 r2p-continue rework (agent_shortcuts._cmd_continue)

Change from "only calls run-resume" to a status-dispatched driver. Read `record.status`
and act:

**Order correction (review finding R3):** the real workflow order is **`stage-ready` first,
then `gate-quality`** (runbook: `stage-ready` at `operator-runbook.md:150`, `gate-quality` at
`:180`; `stage-ready` records the author's readiness assertion, then the gate evaluates).
The earlier draft of this table had it backwards and also auto-ran `stage-ready`. Corrected
rule: `r2p-continue` does **not** auto-`stage-ready` — marking ready is the author's
assertion, so it stops and asks. Only after the artifact is `ready` does it auto-run
`gate-quality`.

| Current status | r2p-continue behavior |
|---|---|
| `ACTIVE_STAGE_DRAFT` | Read stage artifact + active-artifact status. Content empty → stop, report "produce `<stage>` content" (Agent writes). tier not locked → stop, report "needs tier-lock". Artifact not yet `ready` → stop, report "review and run `stage-ready`" (author assertion, not automatic). Artifact `ready` → auto `gate-quality`: pass → continue to review; fail → stop, report repair |
| `READY_FOR_CHECKPOINT_REVIEW` | Auto `review-checkpoint`, then stop at `CHECKPOINT_REVIEW`, report "needs human approval: checkpoint approve / changes" |
| `CHECKPOINT_REVIEW` | Stop, wait for human `checkpoint-decide` (never auto-approve) |
| `CHECKPOINT_APPROVED` | plan stage → auto `run-close`, report closed + **PLAN is at `07-plan.md`, hand it to your executor** (see reconciliation note); otherwise auto `stage-advance`, stop at new stage, report "entered `<next>`, produce content" |
| `CHECKPOINT_CHANGES_REQUESTED` | Stop, report "address requested changes, then `stage-update` (or `stage-produce`) to return to draft" (see 1.6a) |
| `ENTRY_GATE_FAILED` / `QUALITY_GATE_FAILED` | Stop, report repair needed + the specific next command |
| `CLOSED_AT_PLAN_CHECKPOINT` | Report done, **PLAN is at `07-plan.md`, hand it to your executor** |

Exit codes use the existing convention to distinguish "stopped, needs input" from "error".
`run-resume` stays read-only and unchanged (see Key Decision 1).

### 1.6a Close the changes_requested repair loop (review finding R5)

The `CHECKPOINT_CHANGES_REQUESTED → ACTIVE_STAGE_DRAFT` transition exists in
`ALLOWED_TRANSITIONS` (`models.py:129`), but **no command performs it today**:
`stage-update` (`cli.py:712-726`) writes the active artifact back to `"draft"` status but
never calls `update_run_status`, so a run parked in `CHECKPOINT_CHANGES_REQUESTED` cannot
re-enter the draft→gate→review loop — the same class of dead-end as the Part 1 P0.

Fix (part of Part 1 scope):
- `checkpoint-decide --decision changes_requested` sets
  `resume_context.next="repair_stage_artifact"` + `active_item=stage` (see 1.5 table).
- `stage-update` **and** `stage-produce`: when the current status is
  `CHECKPOINT_CHANGES_REQUESTED`, call `update_run_status(ACTIVE_STAGE_DRAFT)` as part of the
  edit (guarded by `is_transition_allowed`, which already permits it). This is the missing
  state flip; without it the artifact goes back to draft but the run status stays stuck.
- Add a test: decide `changes_requested` → `stage-update` → assert status is
  `ACTIVE_STAGE_DRAFT` and the stage can be re-gated and re-approved.

> **Cross-part reconciliation:** The original standalone version of this rework suggested
> `r2p-adapt --executor superpowers` at the closed/approved states. Because **Part 2 deletes
> the adapter**, those hints are replaced with "PLAN is at `07-plan.md`, hand it to your
> executor". If Part 1 is implemented before Part 2, use the executor-direct wording from
> the start so no `r2p-adapt` reference is introduced.

## 1.7 File change list (Part 1)

| File | Change |
|---|---|
| `tools/workflow_cli/cli.py` | +3 handlers (`_cmd_review_checkpoint` / `_cmd_checkpoint_decide` / `_cmd_stage_advance`) with the shared precondition checks (1.5); register in `_register_*`; import `NEXT_STAGE_MAP`, `add_checkpoint`. **Also** edit `_cmd_stage_update` and `_cmd_stage_produce` to flip `CHECKPOINT_CHANGES_REQUESTED → ACTIVE_STAGE_DRAFT` (1.6a) |
| `tools/workflow_cli/models.py` | Add `CMD-STAGE-ADVANCE` (+ ensure `CMD-REVIEW-CHECKPOINT` / `CMD-CHECKPOINT-DECIDE` present); wire into `ALLOWED_COMMANDS_BY_RUN_STATE` for the correct states (1.5a) |
| `tools/workflow_cli/agent_shortcuts.py` | Rewrite `_cmd_continue` as a status-dispatch driver with the corrected ready→gate order (1.6); reuse `_run_cli`; no `r2p-adapt` reference |
| `tests/test_cli.py` | 3 commands × (happy + wrong-state refusal + missing-confirm refusal + the shared precondition refusals: wrong stage, not-ready artifact, duplicate-version approval) |
| `tests/test_models.py` | Assert the new command intents are allowed in exactly the right states, refused elsewhere (1.5a) |
| `tests/test_integration.py` | New true end-to-end test: pure CLI/shortcut from `run-start` to `CLOSED`, assert all 6 stages pass, a PLAN checkpoint exists, `status == CLOSED_AT_PLAN_CHECKPOINT`. Plus a `changes_requested → stage-update → re-gate → re-approve` loop test (1.6a). Keep `_force_to_closed` for unit-level reuse but stop depending on it for end-to-end |
| `tests/test_agent_shortcuts.py` | `r2p-continue` dispatch behavior per status, incl. the not-ready stop and the changes_requested stop |
| `docs/workflow-command-surface.md` | Add `CMD-STAGE-ADVANCE` row; reconcile the `checkpoint_approved` row + "Continue After Checkpoint Approval" section (resume vs advance) (1.5a) |
| `docs/workflow-cli-adapter.md` | Add `workflow stage-advance` row; `review-checkpoint` / `checkpoint-decide` move from "Covered (on paper)" to implemented, with the MVP-scope note for review-checkpoint (1.5 / R2) |
| `docs/workflow-operator-runbook.md` | Complete happy-path steps with review/decide/advance |
| `tools/workflow_cli/agent_templates/claude/SKILL.md` + `commands/r2p-continue.md` | Clarify real continue behavior (stop-at-ready, auto-gate, stop-at-approval) |
| `CLAUDE.md` (project) | Update test-count baseline |

## 1.8 Key decisions (Part 1)

1. **Advance responsibility goes into a new `stage-advance` command, not a `run-resume`
   rewrite.** The docs fold next-stage advance into run-resume's dual-mode semantics
   (`command-surface.md:220/350`), but that context-refresh exception is complex and many
   tests depend on its read-only behavior. A new explicit command is safer and matches
   existing code style. Cost: `stage-advance` is a new command intent — it must be added to
   the authoritative model and docs, not just cli.py (see 1.5a). Alternative (extend
   `CMD-RUN-RESUME` to advance) is documented and rejected there; revisit only if the
   maintainer prefers matrix fidelity over a new command.
2. **`review-checkpoint` is MVP-scoped to a state transition + "ready for human decision"
   marker; it does not write review findings or run merge.** The full `CMD-REVIEW-CHECKPOINT`
   contract (write findings, require merge before decide) is intentionally downgraded for the
   MVP and the downgrade is synced into command-surface/cli-adapter docs (1.5 / R2). Rationale
   stands: review *content* is a semantic Agent/subagent product; the CLI holds state
   authority only (CLAUDE.md "CLI never generates artifact text"). If a real review artifact
   is wanted instead of a marker, that is a scope increase to decide before implementing.
3. **raw_requirement also goes through the full checkpoint loop** (content is already written
   by run-start, so the loop is fast); no special-case shortcut — the only legal path to
   change `current_stage` is approved → advance, uniformly.
4. **Scope = happy path + changes_requested bounce-back**, excluding gap/bundle/confirm. Make
   the product "work end-to-end for the first time" without attempting all 37 commands at once.

## 1.9 Test plan (Part 1)

- **Happy path:** start → (per stage) produce → tier-lock (once) → **stage-ready → gate-quality** (corrected order, R3) → review-checkpoint → checkpoint-decide approved → stage-advance; at plan: checkpoint-decide approved → run-close. Assert terminal status + plan checkpoint row.
- **Errors:** `checkpoint-decide approved` without `--confirm` → exit 2; `stage-advance` at plan stage → exit 6; `review-checkpoint` from wrong state → exit 6; `checkpoint-decide` from non-review state → exit 6.
- **Precondition guards (R4):** `checkpoint-decide --stage X` where `X != current_stage` → exit 6; `checkpoint-decide` when the stage artifact is not `ready` → exit 6; re-approving an already-approved stage+version → exit 6.
- **changes_requested loop (R5):** decide `changes_requested` → status `CHECKPOINT_CHANGES_REQUESTED`; then `stage-update` → status flips to `ACTIVE_STAGE_DRAFT`; then re-gate and re-approve succeed.
- **Driver:** `r2p-continue` from each status produces the documented stop/advance outcome; stops (does not auto-run) at a not-`ready` artifact; never auto-approves at `CHECKPOINT_REVIEW`.

---

# Part 2 — Remove the Superpowers Adapter

## 2.0 Outward-facing change notice

This removes a published command surface from npm package 0.1.2. The `r2p-*` shortcut set
shrinks from 6 (start/continue/status/switch/adapt/reopen) to 5. This is an irreversible
feature removal; it requires explicit maintainer approval before execution.

**Rationale:** The neutral PLAN already runs fine inside superpowers — the adapter is a
redundant translation layer that, on the real forma run, failed (produced
`superpowers-plan.md.repair.md`). Removing it keeps the `PLAN Neutrality Rule`
(`plan-workflow.md`): the PLAN still does not format for any executor; neutral ≠
unexecutable. Part 3 raises the floor on what a neutral PLAN must contain so it runs
directly.

## 2.1 Files to delete

| File | Why |
|---|---|
| `tools/workflow_cli/adapters/superpowers.py` | adapter implementation |
| `tools/workflow_cli/adapters/__init__.py` | registry + `get_adapter`/`list_adapters` |
| `tools/workflow_cli/adapters/README.md` | adapter contract doc |
| `tools/r2p-adapt` | bin wrapper (auto-installed via the `tools/r2p-*` glob; deleting the file stops install) |
| `tools/workflow_cli/agent_templates/claude/commands/r2p-adapt.md` | claude template (glob-discovered; delete = not installed) |
| `tools/workflow_cli/agent_templates/codex/skills/r2p-adapt/SKILL.md` | codex template |
| `tools/workflow_cli/agent_templates/gemini/commands/r2p-adapt.toml` | gemini template |
| `tests/test_adapters_superpowers.py` | 18 adapter tests |
| `docs/workflow-post-plan-adapter-surface.md` | post-PLAN adaptation surface doc |

Also remove the `tools/workflow_cli/adapters/` directory entirely (`git rm` the 3 tracked
files, then `rm -rf` the dir to clear the untracked `__pycache__/` left behind).

## 2.2 Code edits (line-precise as of audit 2026-05-30)

| File:line | Edit |
|---|---|
| `agent_shortcuts.py:252-288` | delete the entire `_cmd_adapt` function |
| `agent_shortcuts.py:325-326` | delete the `adapt` subparser (`p_adapt`) |
| `agent_shortcuts.py:352` | delete the `"adapt": _cmd_adapt` handler entry |
| `agent_shortcuts.py:211` | in `_cmd_continue`, change the run-closed `next:` hint from `r2p-adapt --executor superpowers` to: run is closed; PLAN is at `07-plan.md`; hand it to your executor directly. **If Part 1 ran first, this line is already gone (Part 1 rewrites the whole `_cmd_continue` with executor-direct wording) — this edit is then a no-op.** |
| `models.py:168` | delete `CMD-EXEC-LIST-ADAPTERS` from `READ_ONLY_COMMANDS` |
| `models.py:269` | delete `CMD-EXEC-ADAPT` from the `CLOSED_AT_PLAN_CHECKPOINT` allowed-commands set |

Install discovery is glob-based (`install.py:91/120/130/140`), so no install code changes
are needed beyond deleting the template files and the `tools/r2p-adapt` wrapper.

## 2.3 Test edits

| File | Edit |
|---|---|
| `tests/test_agent_shortcuts.py:328-355` | delete the 2 `adapt` tests (`test_missing_run_record_stops_before_adapter`, `test_malformed_run_record_stops_before_adapter`) |
| `tests/test_integration.py:541-595` | delete the entire executor-adapt test class (4 tests + class docstring) |
| `tests/test_models.py:159-167` | delete the 2 CMD-EXEC tests |
| `tests/test_install.py:375` | remove `"r2p-adapt"` from the codex command list in `test_install_codex_copies_shortcut_skills` |

## 2.4 Doc cleanup

Remove or rewrite every `r2p-adapt` / `CMD-EXEC-*` / adapter reference in:
`README.md`, `docs/README.md` (also drop the post-plan-adapter row from the document map),
`CLAUDE.md`, `.claude/skills/req-to-plan.md`,
`tools/workflow_cli/agent_templates/claude/SKILL.md`,
`docs/workflow-operator-runbook.md`, `docs/workflow-command-surface.md`,
`docs/workflow-cli-adapter.md`, `docs/workflow-agent-command-adapter.md`,
`docs/workflow-invariants.md`.

**Keep** the `PLAN Neutrality Rule` in `plan-workflow.md` — it is the reason no adapter is
needed; only remove the post-PLAN executor-adaptation command intents that referenced the
deleted surface.

## 2.5 Verification (Part 2)

- `.venv/bin/python -m pytest tests/ -v` green. Removing adapter tests drops the count by 26 (2+4+2+18) from the current 494 → 468; Part 1 adds tests on top. Update the baseline in both `CLAUDE.md` (says 460) and `.claude/skills/req-to-plan.md` (says 397) to the real post-change number — reconcile after whichever parts run.
- `git grep -i "adapt"` returns only intentional prose, no `r2p-adapt` / `get_adapter` / `CMD-EXEC-ADAPT` / `ADAPTER_REGISTRY`.
- `r2p install --platform claude,codex,gemini` into a temp home installs no `r2p-adapt*` file; the `r2p-*` shortcut count is 5.
- `r2p --help` (agent_shortcuts) lists 5 subcommands, no `adapt`.

---

# Part 3 — Optimize PLAN Generation

Part 3 edits the two stage-spec documents the Agent reads when generating SPEC/PLAN
(`docs/plan-workflow.md`, `docs/spec-workflow.md`) and tightens the corresponding quality
gates in `tools/workflow_cli/gates.py`. It does not change run.md format. All four
improvements were user-selected on 2026-05-30.

Driving comparison (four real artifacts audited 2026-05-30):

| Dimension | r2p artifacts | superpowers artifacts |
|---|---|---|
| Traceability / governance | strong | weak |
| Executability (code/skeleton blocks) | **0 code blocks** | **142 code blocks** |
| External-dependency version verification | **absent** | dedicated section |
| Machine-checkable tracking (checkboxes) | **0** | **69** |
| Linear readability | forward refs + end-of-doc stable-ID pile | linear |

r2p maximized correctness/traceability but outsourced executability to an adapter that
failed. Part 3 closes the executability gap while keeping r2p's traceability strengths.

## 3.0 Prerequisite: fix the PLAN task schema first (review finding R6)

The PLAN gate guards in 3.1/3.2 can only be reliable if PLAN tasks have a **stable,
machine-parseable structure**. Today the template is narrative (`### PR #1 — Task A-01`,
free-form `Steps:`), and the only structured fields are `Spec References` and the TDD
Decomposition table (`plan-workflow.md:177/224`). The now-deleted adapter relied on a
`PLAN-TASK-*` / `TDD` / `Change Type` section convention (`adapters/superpowers.py:7`) that
the template never actually enforced — which is part of why adaptation failed.

So 3.1 is gated on first defining a fixed task schema in `plan-workflow.md`, e.g.:

```
### PLAN-TASK-001: <title>
Spec References: SPEC-...
Change Type: add | modify | remove
TDD Applicable: yes | no
Files: <Create/Modify + path list>
Skeleton:
  ```<lang>
  <interface signature or test skeleton>
  ```
Steps:
- [ ] red: ...
- [ ] green: ...
Verification: ...
```

The gate parses this structure (heading regex `^### PLAN-TASK-\d+`, field labels), not
free-form prose. Without this step the gate becomes a fragile Markdown guess. This schema
also subsumes the `Skeleton` and checkbox requirements from 3.1/3.3.

## 3.1 Executable anchors (highest priority) — `plan-workflow.md` + `gates.py`

- Depends on 3.0's fixed task schema. The `Skeleton` field (interface signatures in the
  target language, key tests as skeleton code blocks) and explicit `Files:` list become
  required fields of each `PLAN-TASK-*`.
- Keep PLAN Neutrality (no GSD/superpowers orchestration format), but require the anchor to
  be a real code fragment, not pure prose.
- Quality-gate guard: **fires only when `stage == PLAN`** (other stages unaffected). For a
  `standard`-tier PLAN, every `PLAN-TASK-*` with `TDD Applicable: yes` must contain at least
  one fenced code block in its `Skeleton`, else the quality gate fails. `light`-tier and
  `TDD Applicable: no` tasks are exempt. The guard reads `tier.base` from the locked tier
  already passed to `check_quality_gate(run_dir, stage, tier, ...)` — no signature change
  needed. Parsing keys off 3.0's heading/field convention, not loose Markdown.

## 3.2 Context7 version verification — `spec-workflow.md` + `plan-workflow.md` + `gates.py`

- Add a required `## External Documentation Checked` section (mirroring the superpowers
  spec): for any version-sensitive external dependency (framework / SDK / CLI / cloud
  service), verify current usage via Context7 before finalizing SPEC, and record one row
  per dependency: `dependency + version + check date + conclusion`.
- Anything unverifiable is marked `UNCONFIRMED` (per global CLAUDE.md rule).
- Quality-gate guard: **fires only when `stage == SPEC`** (other stages unaffected). A SPEC
  that references external dependencies and lacks this section fails the gate. Detection
  heuristic is conservative — only flags when an external dependency is clearly named.

## 3.3 Machine-checkable execution tracking — `plan-workflow.md`

- PLAN Task steps use `- [ ]` checkbox syntax (mirroring superpowers' 69 checkboxes).
- Add a one-line header to the PLAN declaring it is a step-by-step checkable execution plan,
  so an executing agent can tick items and resume mid-plan.
- Keep the existing TDD Decomposition table (already complete); per-task red→green steps
  also become checkboxes.

## 3.4 Linear readability — `plan-workflow.md` + `spec-workflow.md`

- Reorder templates so each task/contract is self-contained: behavior + verification + test
  anchor readable in one place, reducing `see SPEC-XXX` forward references.
- Change `Stable ID Definitions` from an end-of-doc duplicate pile to: define inline in the
  body, keep only an index table at the end. Eliminates the four-places-for-one-fact problem
  (body description + verification idea + stable-id def + upstream closure).

## 3.5 Verification (Part 3)

- `tests/test_tier.py` and `tests/test_gates.py` stay green; add tests for the new gate
  guards (3.1 missing-code-block fail, 3.2 missing-external-docs-section fail).
- Generate one PLAN through the workflow on a small standard-tier requirement and confirm
  the output contains code blocks, an `External Documentation Checked` section, and `- [ ]`
  steps.
- Doc-only changes to `plan-workflow.md` / `spec-workflow.md` are verified by review + the
  gate tests that enforce them.

---

## Combined rollback

All three parts are pure additive commands + function rewrites + deletions + doc/gate
changes. **No run.md format change, no RunRecord field change, no data migration.** Existing
runs are unaffected (leftover `superpowers-plan.md` files are harmless; none are newly
generated). Rollback = `git revert` per part.

## Open questions (resolve before implementing the affected part)

- **Part 3.1 gate strictness:** should a missing code block be a hard gate fail or a warning
  for the first release? Plan default: hard fail at standard tier, exempt at light tier.
  Owner: maintainer.
- **Test-count baseline:** current real count is 494 (not the 460 in `CLAUDE.md` nor the 397
  in `.claude/skills/req-to-plan.md` — both stale). Part 2 removes 26, Part 1 adds several.
  Settle the final baseline in both files after whichever parts are executed, not per-part.

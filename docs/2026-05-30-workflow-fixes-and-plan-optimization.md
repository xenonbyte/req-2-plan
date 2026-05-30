# Workflow Fixes + PLAN Optimization — Implementation Plan

**Status:** Proposed — revised after review rounds 1–5 + self-audit (awaiting re-review)
**Date:** 2026-05-30
**Author:** req-to-plan maintainers (via /think workflow)

> **Review round 5 — all five findings accepted (verified against code, 2026-05-30):**
> - **QR1** `ENTRY_GATE_FAILED` allows `→ ACTIVE_STAGE_DRAFT` and its only command is
>   `CMD-GATE-ENTRY` (`models.py:112/190`), but the plan only persisted `gate-entry` in
>   `NEXT_STAGE` — leaving `ENTRY_GATE_FAILED` a dead end. Extend gate-entry persistence to it.
>   → §1.5d.
> - **QR2** `run-close` only checks `any(cp.stage == PLAN)` (`cli.py:234`), not active
>   artifact/version match — no parity with the stage-advance TR4 guard. Add it. → §1.7.
> - **QR3** the `review-checkpoint` marker also satisfied the forced-review guard, downgrading
>   forced review to a self-generated file. **Decided:** forced review requires a real
>   `…-subagent-review-v<version>.md`, never the marker. → §1.5b.
> - **QR4** Part 1.7 file list had the Part 2 `install.py` cleanup, contradicting "three parts
>   disjoint". Moved to Part 2. → §1.7.
> - **QR5** Part 3 verification required the SPEC-only `External Documentation Checked` section
>   in the PLAN output. Split per artifact: SPEC has the section, PLAN has tasks/code/checkboxes.
>   → §3.5.

> **Self-audit (2026-05-30, after round 4):** re-verified every code/doc anchor cited in this
> plan against the source — all correct (cli.py 253/529/555/566/574/658/675/697/712/762,
> models.py 116/129/168/262/269, gates.py 208/234, install.py 195/201, output.py 10,
> command-surface/cli-adapter/invariants/runbook refs, and the `tests/test_*` line refs). Also
> traced the reopen path (`create_run_record` → `ACTIVE_STAGE_DRAFT`, so the FR2 `NEXT_STAGE`
> produce guard does not misfire) and the first stage (raw_requirement never enters
> `NEXT_STAGE`). One honest finding surfaced: **Part 1 has grown well beyond "+3 commands"** —
> documented in §1.10 with an optional 1a/1b split.

> **Review round 4 — all three findings accepted (verified against code, 2026-05-30):**
> - **FR1** `QUALITY_GATE_FAILED` only allows `→ {ACTIVE_STAGE_DRAFT, UPSTREAM_GAP_ROUTING}`
>   (`models.py:116`), **not** `READY_FOR_CHECKPOINT_REVIEW`. `gate-quality` only reaches
>   `READY…` on re-run today by writing status directly (`cli.py:574`) — so the TR3 migration
>   would *break* the re-run path. Add the `QUALITY_GATE_FAILED → ACTIVE_STAGE_DRAFT` repair
>   flip. → §1.6b.
> - **FR2** `next_stage` still lists `CMD-STAGE-PRODUCE` (`models.py:262`) and
>   `_cmd_stage_produce` never calls `is_command_allowed` (which is **never called** in cli.py),
>   so production can bypass the entry gate. Remove it from the matrix and add an explicit
>   handler status guard. → §1.5d.
> - **FR3** Deleting the stale `r2p-adapt` file isn't enough: uninstall skips shared `bin/`
>   when other platforms remain (`install.py:201`), and the path stays in every platform
>   manifest's `installed_paths`, causing doctor drift. Cleanup must update all manifests +
>   backup metadata. → §2.2.

> **Review round 3 — all seven findings accepted (verified against code, 2026-05-30):**
> - **TR1** `gate-entry` (`_cmd_gate_entry`) is read-only — it persists no status, and
>   `cli.py:697` is in `_cmd_stage_produce`, not gate-entry. The NEXT_STAGE→draft path didn't
>   exist. Fix: bring `gate-entry` into Part 1 to persist status when in `NEXT_STAGE`. → §1.5d.
> - **TR2** `check_forced_subagent_review` has no `version` param and globs any
>   `*-review-*.md` (`gates.py:208`), so a v1 marker clears a v2 approval. Make it
>   version-aware. → §1.5b.
> - **TR3** "every transition via `update_run_status`" is aspirational — 4 handlers write
>   `record.status` directly (`cli.py:555/574/675/697`). Migrate them. → §1.3.
> - **TR4** `stage-advance` needs a "matching approved checkpoint exists" guard, not just the
>   `CHECKPOINT_APPROVED` status. → §1.5 shared checks.
> - **TR5** Missing `--confirm` exit code: `cli-adapter.md:175` says **5**, the draft said 2.
>   Unify on 5 (`EXIT_REVIEW_REQ` broadened to "approval precondition not met"). → §1.5.
> - **TR6** A stale PATH wrapper `r2p-adapt` must be **deterministically removed** on
>   upgrade; doctor-only reporting is not acceptable. → §2.2.
> - **TR7** Part 3.2 Context7 gate shouldn't guess; require `External Documentation Checked`
>   always (explicit `N/A` row when no deps) and make the gate a presence check. → §3.2.

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
>
> **Review round 2 — all five findings accepted (verified against code, 2026-05-30):**
> - **NR1** Forced-review guard is in `gate-quality` (`cli.py:566`) but `invariants.md:215`
>   puts it on `checkpoint-decide approved` (exit 5). As-is it **deadlocks** modifier-bearing
>   design/spec/plan (blocked before reaching `READY_FOR_CHECKPOINT_REVIEW`, which
>   `review-checkpoint` needs). Move the guard; `review-checkpoint` writes a deterministic
>   marker `reviews/<stage>-checkpoint-review-v<version>.md`. → §1.5b + §1.5 rows.
> - **NR2** `gate-quality` (`cli.py:529`) doesn't require a `ready` artifact, so
>   `stage-produce → gate-quality` skips `stage-ready` (test `:498`). Add the readiness
>   precondition. → §1.5c.
> - **NR3** `next_stage` is an observable state ("run entry gate first",
>   `command-surface.md:221`); don't collapse it. `stage-advance` stops at `NEXT_STAGE`;
>   `gate-entry` then moves to draft. → §1.5d + §1.6 table.
> - **NR4** Fresh install is fine, but upgraders from 0.1.2 may keep a stale shared
>   `bin/r2p-adapt` (ref-count logic, `install.py:195`). Add an upgrade test. → §2.2 + §2.5.
> - **NR5** Adapter test deletion is **25**, not 26 (`test_integration` executor-adapt class is
>   3 tests, not 4); baseline 494 → 469. → §2.3 + §2.5.

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
state transition = one explicit CLI subcommand that persists via `update_run_status` (which
enforces `ALLOWED_TRANSITIONS`). The CLI never auto-approves — approval is always a human
stop point. This is the load-bearing invariant of the whole design.

> **State-authority correction (review finding TR3).** This "every transition goes through
> `update_run_status`" is currently an *aspiration*, not the code: four existing handlers write
> `record.status = RunStatus.X` directly, bypassing `ALLOWED_TRANSITIONS` —
> `gate-quality` (`cli.py:555` QUALITY_GATE_FAILED, `:574` READY_FOR_CHECKPOINT_REVIEW),
> `stage-produce` (`cli.py:675` ENTRY_GATE_FAILED, `:697` ACTIVE_STAGE_DRAFT). Part 1 migrates
> these four to `update_run_status` so the new commands aren't the only validated ones and the
> CLI can't silently make an illegal transition. (The new `gate-entry` NEXT_STAGE persistence
> in 1.5d uses `update_run_status` from the start.) Add a test asserting an illegal direct
> transition is now rejected.

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
                                     ▼ run-close (command exists; Part 1 adds a
                          CLOSED_AT_PLAN_CHECKPOINT   checkpoint-match guard, QR2)
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

**`stage-advance` checkpoint guard (review finding TR4).** Beyond the `CHECKPOINT_APPROVED`
status, `stage-advance` must also verify an `approved` checkpoint actually exists for the
current stage + active artifact + version in `record.approved_checkpoints`. Without this, a
run.md whose status was hand-edited (or set in a test) to `CHECKPOINT_APPROVED` with no
checkpoint row could advance. Missing/mismatched checkpoint → exit 6.

**Exit-code decision for missing `--confirm` (review finding TR5).** The CLI-adapter spec is
authoritative: "If confirmation is required but missing, the CLI must stop with **exit code
5**" (`cli-adapter.md:175`). The earlier draft said exit 2 — that is corrected to **5**
throughout this plan. Exit 5 (`EXIT_REVIEW_REQ`) is therefore the single "approval
precondition not met" code, covering both *missing confirmation* and *missing forced review*;
its comment in `output.py:10` is broadened from "forced subagent review required" to
"approval precondition not met (confirmation or forced review)". No numeric value changes, so
existing exit-5 forced-review behavior is preserved.

| Command | Args | Precondition | Action | Exit |
|---|---|---|---|---|
| `review-checkpoint` | `--work-id --stage` | `READY_FOR_CHECKPOINT_REVIEW` + shared checks | **MVP scope (R2):** `update_run_status(CHECKPOINT_REVIEW)`; `resume_context.next="checkpoint_decide"`; write a minimal marker at `reviews/<stage>-checkpoint-review-v<version>.md` ("ready for human decision") — nothing more. This marker satisfies the **non-forced** decision path only; it does **not** satisfy the forced-review guard (QR3, 1.5b). It does not produce review findings or run merge — the full `CMD-REVIEW-CHECKPOINT` contract (`command-surface.md:157`) is downgraded to this marker for the MVP, synced into command-surface/cli-adapter docs. | OK; wrong state → 6 |
| `checkpoint-decide` | `--work-id --stage --decision {approved,changes_requested} [--confirm] [--downstream-authorization S]` | `CHECKPOINT_REVIEW` + shared checks | approved: requires `--confirm` (else **exit 5**, per TR5); **then the version-aware forced-subagent-review guard (moved here from gate-quality — NR1/TR2/QR3): when tier has a modifier in `{migration, safety, cross_project}` AND stage ∈ `{design, spec, plan}`, require a real `reviews/<stage>-subagent-review-v<version>.md` (NOT the review-checkpoint marker) — else exit 5** (matches `invariants.md:215`); when no forced modifier applies the guard does not fire. On pass: `add_checkpoint(...)` + `upsert_active_artifact(..., "approved")` + `update_run_status(CHECKPOINT_APPROVED)`; `downstream_authorization` defaults to the `NEXT_STAGE_MAP` next-stage name, and `close_workflow_run` at the plan stage (verified in the forma run, not `"none"`). changes_requested: `update_run_status(CHECKPOINT_CHANGES_REQUESTED)` **and set `resume_context.next="repair_stage_artifact"` + `active_item=stage`** (see 1.6a, R5) — allowed even when forced review is missing. | OK; missing confirm → 5; forced review missing on approve → 5; wrong state → 6 |
| `stage-advance` | `--work-id` | `CHECKPOINT_APPROVED`, `current_stage != PLAN`, **a matching `approved` checkpoint exists** (TR4) + shared checks | `update_run_status(NEXT_STAGE)` only (do **not** collapse to draft — NR3, see 1.5d); `current_stage = NEXT_STAGE_MAP[cur]`; `resume_context(active_item=next, next="gate_entry")`. Entry into `ACTIVE_STAGE_DRAFT` then happens via `gate-entry`, which Part 1 fixes to persist status when in `NEXT_STAGE` (see 1.5d / TR1). | OK; plan stage → 6 (point to run-close); missing checkpoint → 6; wrong state → 6 |

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

### 1.5b Move the forced-subagent-review guard (review finding NR1 — deadlock fix)

`invariants.md:215` says the forced-review guard belongs on **`checkpoint-decide --decision
approved` (refuse with exit 5)**. The current code instead enforces it in `gate-quality`
(`cli.py:566`, before the run reaches `READY_FOR_CHECKPOINT_REVIEW`). Left as-is this
**deadlocks** any modifier-bearing design/spec/plan run: `gate-quality` blocks the run at
exit 5 before it can enter `READY_FOR_CHECKPOINT_REVIEW`, but the new `review-checkpoint`
requires that state to even produce the review marker — so the review file can never be
created and the gate can never pass. Required changes (Part 1 scope):

- **Remove** the `check_forced_subagent_review` call from `_cmd_gate_quality` (`cli.py:566`);
  `gate-quality` no longer returns exit 5.
- **Add** the same guard into `_cmd_checkpoint_decide`, applied only on
  `--decision approved`, after the `--confirm` check (see 1.5 table). Other decisions
  (`changes_requested`, …) stay allowed even when the review file is missing, per
  `invariants.md`.
- **Make the guard version-aware (review finding TR2).** Today
  `check_forced_subagent_review(stage, tier, reviews_dir)` has **no version parameter** and
  globs `*-checkpoint-review-*.md` / `*-subagent-review-*.md` (`gates.py:208/234`), so a stale
  v1 marker would wrongly clear a v2 approval. Change the helper signature to
  `check_forced_subagent_review(stage, tier, reviews_dir, version)` and match only the
  version-stamped file.
- **Decouple the marker from the forced-review guard (review finding QR3 — decided).** The
  earlier draft let `review-checkpoint`'s own self-written marker satisfy the forced-review
  guard, which would silently downgrade the `{migration, safety, cross_project}` forced review
  into a self-generated file — gutting the rule. **Decision: the forced-review guard requires a
  distinct `reviews/<stage>-subagent-review-v<version>.md` (a real review finding), NOT the
  `review-checkpoint` marker.** Concretely:
  - `review-checkpoint` writes only `reviews/<stage>-checkpoint-review-v<version>.md` (the
    "ready for human decision" marker). This is enough to satisfy the **non-forced** path —
    i.e. when no forced modifier applies, `checkpoint-decide approved` needs no review file at
    all (the guard simply doesn't fire).
  - When a forced modifier applies (design/spec/plan + `{migration, safety, cross_project}`),
    `checkpoint-decide approved` requires `…-subagent-review-v<version>.md` to exist — a file a
    subagent/human review actually produced, never the marker. Absent it → exit 5, surfacing
    the `CMD-SUBAGENT-REVIEW` command to run (matches `invariants.md:215`'s intent that forced
    review means a real review).
  - This removes the deadlock (the guard is off `gate-quality`) **without** making forced
    review self-satisfying.
- Update `tests/test_cli.py` / `tests/test_gates.py` forced-review tests: exit 5 now comes
  from `checkpoint-decide` not `gate-quality`; add **"v1 marker must not clear a v2 approval"**
  (version regression, TR2); add **"forced modifier: checkpoint-review marker alone does NOT
  satisfy approve; a subagent-review file does"** (QR3 regression).

### 1.5c gate-quality must require a `ready` artifact (review finding NR2)

`_cmd_gate_quality` (`cli.py:529`) currently does not check artifact readiness, so
`stage-produce → gate-quality` skips `stage-ready` entirely and still reaches
`READY_FOR_CHECKPOINT_REVIEW` (existing test `tests/test_cli.py:498` accepts this). That
contradicts the corrected ready→gate order (R3, 1.6) and lets a draft reach review while the
new `review-checkpoint` shared checks would then reject it. Required changes (Part 1 scope):

- Add to `gate-quality` preconditions: `--stage == current_stage`; active artifact exists;
  on-disk version matches; **active artifact status is `ready`** (i.e. `stage-ready` ran).
  Otherwise exit 6.
- Update `tests/test_cli.py:498` (`test_runs_quality_check_after_tier_lock`) and any other
  produce→gate tests to insert `stage-ready` before `gate-quality`.

### 1.5d NEXT_STAGE: keep it observable, don't collapse it (review finding NR3)

The earlier draft had `stage-advance` do `CHECKPOINT_APPROVED → NEXT_STAGE → ACTIVE_STAGE_DRAFT`
in one shot, making `NEXT_STAGE` a transient internal blip. But the authoritative matrix
defines `next_stage` as an **observable state** whose job is "run the next stage's entry gate
first" (`command-surface.md:221`: allows `CMD-STAGE-LOAD`, `CMD-GATE-ENTRY`, `CMD-RUN-RESUME`).
**Decision: keep `NEXT_STAGE` observable.**

> **Correction (review finding TR1):** the earlier revision claimed `gate-entry` performs
> `NEXT_STAGE → ACTIVE_STAGE_DRAFT` "at `cli.py:697`". That is wrong on two counts:
> `_cmd_gate_entry` only prints the gate result and **persists no status** (it is read-only);
> and `cli.py:697` is inside `_cmd_stage_produce` (which is what actually writes
> `ACTIVE_STAGE_DRAFT`, after running the entry gate internally). So today there is **no**
> command that moves `NEXT_STAGE → ACTIVE_STAGE_DRAFT` — another dead end if we park a run in
> `NEXT_STAGE`. Revised contract makes `gate-entry` a real state-transition command:

- `stage-advance` transitions `CHECKPOINT_APPROVED → NEXT_STAGE` only, sets
  `current_stage = NEXT_STAGE_MAP[cur]`, and sets `resume_context.next="gate_entry"`. It does
  **not** auto-collapse to `ACTIVE_STAGE_DRAFT`.
- **`_cmd_gate_entry` is brought into Part 1 scope:** when run status is `NEXT_STAGE`
  **or `ENTRY_GATE_FAILED`** (review finding QR1), it must persist the result via
  `update_run_status` — pass → `ACTIVE_STAGE_DRAFT`, fail → `ENTRY_GATE_FAILED` — then
  `mgr.save(record)`. Both states allow `→ ACTIVE_STAGE_DRAFT` (`models.py:112` for
  ENTRY_GATE_FAILED), and `ENTRY_GATE_FAILED`'s only allowed command is `CMD-GATE-ENTRY`
  (`models.py:190`) — so without this persistence `ENTRY_GATE_FAILED` is a dead end too (a
  re-run that passes wouldn't be recorded, and `stage-produce` is correctly disallowed there).
  (Outside these two states `gate-entry` keeps today's read-only "just report" behavior so
  existing `gate-entry` tests still hold.) This is the missing persistence TR1/QR1 call out.
- `r2p-continue` handles `NEXT_STAGE` by auto-running `gate-entry` (now state-persisting),
  then stops at the new `ACTIVE_STAGE_DRAFT` asking for content. See the `NEXT_STAGE` row in
  the 1.6 dispatch table.

This keeps `stage-advance` aligned with the matrix and reuses the entry-gate transition —
but only after `gate-entry` is fixed to actually persist it.

**Close the NEXT_STAGE produce-bypass (review finding FR2).** The matrix's `next_stage` row
says "Stop production until entry gate passes" (`command-surface.md:221`), but
`ALLOWED_COMMANDS_BY_RUN_STATE[NEXT_STAGE]` still lists `CMD-STAGE-PRODUCE` (`models.py:262`),
**and** `_cmd_stage_produce` only checks `stage != current_stage` (`cli.py:654/658`) — it
never calls `is_command_allowed` (which is in fact **never called anywhere** in cli.py; the
matrix is declarative only). So a run in `NEXT_STAGE` can `stage-produce` directly and skip
the entry gate. Required changes (Part 1 scope):
- Remove `CMD-STAGE-PRODUCE` from `ALLOWED_COMMANDS_BY_RUN_STATE[NEXT_STAGE]` in `models.py`.
- Add a status guard to `_cmd_stage_produce`: refuse (exit 6) when `record.status == NEXT_STAGE`,
  directing the operator to run `gate-entry` first. (Production is only valid from
  `ACTIVE_STAGE_DRAFT`/`CHECKPOINT_CHANGES_REQUESTED`/`QUALITY_GATE_FAILED` per the repair
  loops.) Do not rely on `is_command_allowed` — guard explicitly in the handler.
- Test: `stage-produce` while in `NEXT_STAGE` → exit 6; after `gate-entry` lands in
  `ACTIVE_STAGE_DRAFT`, `stage-produce` works.

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
| `CHECKPOINT_APPROVED` | plan stage → auto `run-close`, report closed + **PLAN is at `07-plan.md`, hand it to your executor** (see reconciliation note); otherwise auto `stage-advance` (→ `NEXT_STAGE`) and fall through to the `NEXT_STAGE` handling below |
| `NEXT_STAGE` | Auto `gate-entry` (mechanical): pass → land in `ACTIVE_STAGE_DRAFT`, stop and report "entered `<next>`, produce content"; fail → stop at `ENTRY_GATE_FAILED`, report the missing upstream (review finding NR3) |
| `CHECKPOINT_CHANGES_REQUESTED` | Stop, report "address requested changes, then `stage-update` (or `stage-produce`) to return to draft" (see 1.6a) |
| `ENTRY_GATE_FAILED` | Stop, report the missing upstream; repair = re-run `gate-entry` (now state-persisting in this state, QR1) once the upstream checkpoint exists |
| `QUALITY_GATE_FAILED` | Stop, report repair; repair = `stage-update` (flips to `ACTIVE_STAGE_DRAFT`, 1.6b) → `stage-ready` → `gate-quality` |
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

### 1.6b Close the QUALITY_GATE_FAILED repair loop (review finding FR1)

**This is the necessary companion to the TR3 migration (1.3) and a latent bug TR3 would
otherwise expose.** `QUALITY_GATE_FAILED`'s only allowed transitions are
`{ACTIVE_STAGE_DRAFT, UPSTREAM_GAP_ROUTING}` (`models.py:116`) — **not**
`READY_FOR_CHECKPOINT_REVIEW`. Today `gate-quality` gets away with going straight to
`READY_FOR_CHECKPOINT_REVIEW` on a re-run only because it writes `record.status` directly
(`cli.py:574`), bypassing `ALLOWED_TRANSITIONS`. Once TR3 routes that write through
`update_run_status`, a **second** `gate-quality` run from `QUALITY_GATE_FAILED` → `READY…`
would be **rejected** by the state machine — turning a previously-"working" path into a
dead end.

Fix (part of Part 1 scope), pick the repair path explicitly:
- The repair loop from `QUALITY_GATE_FAILED` must first return to `ACTIVE_STAGE_DRAFT` (the
  allowed transition), then re-run `stage-ready` → `gate-quality`. So `stage-update`/
  `stage-produce` must flip `QUALITY_GATE_FAILED → ACTIVE_STAGE_DRAFT` too (same mechanism as
  1.6a for `CHECKPOINT_CHANGES_REQUESTED`), and `gate-quality` only ever transitions to
  `READY…` from `ACTIVE_STAGE_DRAFT`.
- `r2p-continue`'s `QUALITY_GATE_FAILED` row already stops and asks for repair; the repair
  edit now also performs the status flip.
- Add a test: fail quality gate → `stage-update` → status `ACTIVE_STAGE_DRAFT` → `stage-ready`
  → `gate-quality` passes to `READY_FOR_CHECKPOINT_REVIEW` (this is the regression that TR3
  alone would have broken).

> **Cross-part reconciliation:** The original standalone version of this rework suggested
> `r2p-adapt --executor superpowers` at the closed/approved states. Because **Part 2 deletes
> the adapter**, those hints are replaced with "PLAN is at `07-plan.md`, hand it to your
> executor". If Part 1 is implemented before Part 2, use the executor-direct wording from
> the start so no `r2p-adapt` reference is introduced.

## 1.7 File change list (Part 1)

This list is **Part 1 only**. The `install.py` adapter-cleanup belongs to Part 2 (§2.2) and
was moved out of here (review finding QR4) to keep the three parts disjoint.

| File | Change |
|---|---|
| `tools/workflow_cli/cli.py` | **3 new + 5 modified handlers** (scope grew across review rounds — see 1.10). New: `_cmd_review_checkpoint` / `_cmd_checkpoint_decide` / `_cmd_stage_advance` with shared precondition checks (1.5); register in `_register_*`; import `NEXT_STAGE_MAP`, `add_checkpoint`. **`_cmd_gate_entry`:** when status is `NEXT_STAGE` **or `ENTRY_GATE_FAILED`**, persist pass→`ACTIVE_STAGE_DRAFT` / fail→`ENTRY_GATE_FAILED` via `update_run_status` + save (TR1/QR1, 1.5d). **`_cmd_gate_quality`:** remove the `check_forced_subagent_review` call (NR1, 1.5b), add the `ready`-artifact precondition (NR2, 1.5c). **`_cmd_checkpoint_decide`:** version-aware forced-review guard on approve; missing-confirm → exit 5 (NR1/TR2/TR5). **`_cmd_stage_advance`:** stop at `NEXT_STAGE`; require a matching approved checkpoint (NR3/TR4, 1.5d). **`_cmd_stage_produce`:** add a `NEXT_STAGE` status guard → exit 6 (FR2, 1.5d). **Migrate the 4 direct `record.status =` writes** at `cli.py:555/574/675/697` to `update_run_status` (TR3, 1.3). **`_cmd_stage_update` / `_cmd_stage_produce`:** flip `CHECKPOINT_CHANGES_REQUESTED → ACTIVE_STAGE_DRAFT` **and** `QUALITY_GATE_FAILED → ACTIVE_STAGE_DRAFT` (1.6a / 1.6b — the latter is required so the TR3 migration doesn't break the gate-quality re-run path). **`_cmd_run_close`:** strengthen the existing `any(cp.stage == PLAN)` check (`cli.py:234`) to require the PLAN checkpoint matches the current plan **active artifact + version** — parity with the `stage-advance` TR4 guard (QR2) |
| `tools/workflow_cli/gates.py` | Add a `version` param to `check_forced_subagent_review` and match only `…-review-v<version>.md` (TR2, 1.5b) |
| `tools/workflow_cli/output.py` | Broaden the `EXIT_REVIEW_REQ = 5` comment to "approval precondition not met (confirmation or forced review)" (TR5) |
| `tools/workflow_cli/models.py` | Add `CMD-STAGE-ADVANCE` (+ ensure `CMD-REVIEW-CHECKPOINT` / `CMD-CHECKPOINT-DECIDE` present); wire into `ALLOWED_COMMANDS_BY_RUN_STATE` for the correct states (1.5a). **Remove `CMD-STAGE-PRODUCE` from `ALLOWED_COMMANDS_BY_RUN_STATE[NEXT_STAGE]`** (FR2, 1.5d) |
| `tools/workflow_cli/agent_shortcuts.py` | Rewrite `_cmd_continue` as a status-dispatch driver with the corrected ready→gate order (1.6); reuse `_run_cli`; no `r2p-adapt` reference |
| `tests/test_cli.py` | 3 commands × (happy + wrong-state refusal + missing-confirm refusal → **exit 5** + shared precondition refusals: wrong stage, not-ready artifact, duplicate-version approval, **missing-checkpoint advance** (TR4)). Move forced-review exit-5 assertions from `gate-quality` to `checkpoint-decide approved` (NR1). Add: **"v1 marker must not clear a v2 approval"** (TR2); **"forced modifier: checkpoint-review marker alone → exit 5; subagent-review file → passes"** (QR3); **illegal-direct-transition rejection** (TR3); **run-close with mismatched plan checkpoint → exit 6** (QR2); **entry-gate repair from ENTRY_GATE_FAILED persists ACTIVE_STAGE_DRAFT; stage-produce in ENTRY_GATE_FAILED refused** (QR1). Update `test_runs_quality_check_after_tier_lock` (`:498`) to insert `stage-ready` before `gate-quality` (NR2) |
| `tests/test_gates.py` | Update forced-review tests for the new `version` param; assert version mismatch fails (TR2); assert the checkpoint-review marker does **not** satisfy the forced guard while a subagent-review file does (QR3) |
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

- **Happy path:** start → (per stage) produce → tier-lock (once) → **stage-ready → gate-quality** (corrected order, R3) → review-checkpoint (writes the marker) → checkpoint-decide approved → stage-advance → gate-entry; at plan: checkpoint-decide approved → run-close. Assert terminal status + plan checkpoint row.
- **Errors:** `checkpoint-decide approved` without `--confirm` → **exit 5** (TR5); `stage-advance` at plan stage → exit 6; `review-checkpoint` from wrong state → exit 6; `checkpoint-decide` from non-review state → exit 6.
- **Precondition guards (R4 + TR4):** `checkpoint-decide --stage X` where `X != current_stage` → exit 6; `checkpoint-decide` when the stage artifact is not `ready` → exit 6; re-approving an already-approved stage+version → exit 6; `stage-advance` in `CHECKPOINT_APPROVED` but with **no matching approved checkpoint** (e.g. hand-edited run.md) → exit 6.
- **gate-quality readiness (NR2):** `stage-produce → gate-quality` without `stage-ready` → exit 6; `stage-ready → gate-quality` → passes the precondition.
- **Forced review moved + version-aware + marker-decoupled (NR1 + TR2 + QR3):** a forced modifier (e.g. safety) on a design stage: `gate-quality` now **passes** to `READY_FOR_CHECKPOINT_REVIEW` (no exit 5, NR1); `review-checkpoint` writes the `…-checkpoint-review-v1.md` marker; `checkpoint-decide approved` with **only that marker → exit 5** (marker does not satisfy forced review, QR3); after a real `…-subagent-review-v1.md` is added → **passes**. Negatives: a `…-subagent-review-v1.md` present but the active artifact is v2 → exit 5 (version mismatch, TR2); a **non-forced** stage needs no review file to approve; `checkpoint-decide changes_requested` always allowed.
- **run-close checkpoint match (QR2):** run-close with a PLAN checkpoint whose artifact/version does **not** match the current plan active artifact → exit 6 (parity with stage-advance TR4); matching → closes.
- **entry-gate repair loop (QR1):** from `ENTRY_GATE_FAILED`, re-run `gate-entry` after the upstream checkpoint exists → persists `ACTIVE_STAGE_DRAFT`; `stage-produce` while in `ENTRY_GATE_FAILED` is refused (only `gate-entry` is valid there).
- **NEXT_STAGE observable + persisted (NR3 + TR1):** after `stage-advance`, status is `NEXT_STAGE` (not draft); `gate-entry` (now state-persisting in this state) moves it to `ACTIVE_STAGE_DRAFT` on pass / `ENTRY_GATE_FAILED` on fail, and the change is saved to run.md.
- **State authority (TR3):** an attempt to drive an illegal transition is rejected by `update_run_status`; the migrated handlers (gate-quality / stage-produce) no longer write `record.status` directly.
- **changes_requested loop (R5):** decide `changes_requested` → status `CHECKPOINT_CHANGES_REQUESTED`; then `stage-update` → status flips to `ACTIVE_STAGE_DRAFT`; then re-gate and re-approve succeed.
- **quality-gate repair loop (FR1):** fail `gate-quality` → `QUALITY_GATE_FAILED`; `stage-update` → `ACTIVE_STAGE_DRAFT`; `stage-ready` → `gate-quality` → `READY_FOR_CHECKPOINT_REVIEW`. (Regression guard: this path breaks if TR3 migration lands without the 1.6b flip.)
- **NEXT_STAGE produce-bypass (FR2):** `stage-produce` while in `NEXT_STAGE` → exit 6; after `gate-entry` → `ACTIVE_STAGE_DRAFT`, `stage-produce` works.
- **Driver:** `r2p-continue` from each status produces the documented stop/advance outcome; stops (does not auto-run) at a not-`ready` artifact; auto-runs `gate-entry` at `NEXT_STAGE`; never auto-approves at `CHECKPOINT_REVIEW`.

## 1.10 Scope note: Part 1 is bigger than "+3 commands" (self-review)

Across four review rounds, Part 1 grew from "add 3 transition commands" into **"make the
state machine actually self-consistent"**. It now touches **8 handlers** (3 new + 5 modified)
and fixes structural gaps the new commands depend on: the forced-review guard was in the wrong
place (NR1), four handlers bypassed `update_run_status` (TR3), `is_command_allowed` is never
called so the matrix isn't enforced (FR2), and two repair loops (`CHECKPOINT_CHANGES_REQUESTED`,
`QUALITY_GATE_FAILED`) had no command to exit them (R5/FR1). This is the genuine minimum to get
one happy path end-to-end without the state machine rejecting it — not scope creep — but it is
**not a small PR**, and the implementer should plan for that.

**Suggested split (optional, recommended):**
- **Part 1a — state-machine self-consistency** (no new user-facing commands): migrate the 4
  direct `record.status =` writes to `update_run_status` (TR3); add the
  `CHECKPOINT_CHANGES_REQUESTED` and `QUALITY_GATE_FAILED` repair flips (1.6a/1.6b); make
  `gate-quality` require `ready` (NR2); make `gate-entry` persist in `NEXT_STAGE` (TR1); add
  the `NEXT_STAGE` produce guard + matrix removal (FR2); move the forced-review guard target
  off `gate-quality` (NR1, the removal half). Independently testable; unblocks the rest.
- **Part 1b — the three new commands**: `review-checkpoint` / `checkpoint-decide` /
  `stage-advance` + their model/doc sync (1.5a) and the forced-review guard's new home on
  `checkpoint-decide` (NR1, the add half).

1a is a safe, self-contained correctness pass; 1b is the feature surface. If a single large PR
is acceptable, keep them together — but land 1a's tests first so regressions are caught early.

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

Install discovery is glob-based (`install.py:91/120/130/140`), so **fresh** installs need no
install-code change beyond deleting the template files and the `tools/r2p-adapt` wrapper.

**Upgrade path (review findings NR4 + TR6):** the shared `~/.req-to-plan/bin/r2p-adapt`
wrapper is reference-counted across platforms (`install.py:195`). A user already on 0.1.2 with
multiple platforms installed may have a stale `r2p-adapt` that fresh-install logic never
revisits. Because `r2p-adapt` is an **executable on PATH**, leaving a dead command behind
actively misleads users (TR6) — "doctor reports it" is **not** an acceptable end state.
Required: install/reinstall/uninstall must **deterministically remove** managed wrappers that
are no longer part of the current template set (i.e. treat the wrapper set as
manifest-driven: any managed `bin/r2p-*` not in the new install is deleted). `r2p doctor` is
an additional diagnostic only, not the cleanup mechanism.

**Manifest consistency (review finding FR3).** Deleting the file alone is not enough. Uninstall
currently **skips** shared `bin/` paths when other platforms are still installed
(`install.py:201`, the `other_platforms_installed and p.is_relative_to(bin_dir)` continue). So
the stale `r2p-adapt` is referenced from **every installed platform's manifest**
`installed_paths`. The upgrade cleanup must therefore:
- remove the obsolete shared wrapper path from the `installed_paths` of **all** installed
  platform manifests (not just the one being reinstalled), and clean any related `backups`
  metadata entries, so a later `doctor` does not report a missing-file drift for a path that
  no longer should exist;
- then delete the file itself.

Add the "upgrade from an installed 0.1.2 multi-platform state" test asserting both: the
`r2p-adapt` file is gone **and** no installed manifest still lists it (no doctor drift).

## 2.3 Test edits

| File | Edit |
|---|---|
| `tests/test_agent_shortcuts.py:328-355` | delete the 2 `adapt` tests (`test_missing_run_record_stops_before_adapter`, `test_malformed_run_record_stops_before_adapter`) |
| `tests/test_integration.py:540-595` | delete the entire executor-adapt test class (**3 tests** + class docstring — `test_adapt_writes_derived_plan`, `test_adapt_requires_closed_run`, `test_adapt_with_unsupported_executor_exits_nonzero`; corrected count, NR5) |
| `tests/test_models.py:159-167` | delete the 2 CMD-EXEC tests |
| `tests/test_install.py:375` | remove `"r2p-adapt"` from the codex command list in `test_install_codex_copies_shortcut_skills`; **add** the NR4 upgrade test |

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

- `.venv/bin/python -m pytest tests/ -v` green. Removing adapter tests drops the count by **25** (18 + 2 + 2 + 3; corrected per NR5 — `test_integration` executor-adapt class is 3 tests, not 4) from the current 494 → **469**; Part 1 adds tests on top. Update the baseline in both `CLAUDE.md` (says 460) and `.claude/skills/req-to-plan.md` (says 397) to the real post-change number — reconcile after whichever parts run.
- `git grep -i "adapt"` returns only intentional prose, no `r2p-adapt` / `get_adapter` / `CMD-EXEC-ADAPT` / `ADAPTER_REGISTRY`.
- `r2p install --platform claude,codex,gemini` into a temp home installs no `r2p-adapt*` file; the `r2p-*` shortcut count is 5.
- **Upgrade (NR4 + TR6):** from a temp home pre-seeded with a 0.1.2-style multi-platform install (stale `bin/r2p-adapt` present), reinstall/uninstall **deterministically removes** the dangling `bin/r2p-adapt` (assert the file is gone — doctor-only reporting is not sufficient).
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

## 3.2 Context7 version verification — `spec-workflow.md` + `gates.py`

**Always-present section, not a heuristic (review finding TR7).** The earlier draft made the
gate guess "does this SPEC reference an external dependency?" — fragile. Instead:

- The `## External Documentation Checked` section is **required in every SPEC**. It contains a
  small machine-parseable dependency inventory; a SPEC with no external dependencies writes a
  single explicit `N/A — no external dependencies` row rather than omitting the section.
- For each version-sensitive external dependency (framework / SDK / CLI / cloud service),
  verify current usage via Context7 before finalizing SPEC, and record one row:
  `dependency | version | check date | conclusion`. Unverifiable → `UNCONFIRMED` (global
  CLAUDE.md rule).
- Quality-gate guard (`stage == SPEC` only): fail if the section is **absent or empty**. This
  is a presence check on a fixed heading + at least one inventory row (real dep or the
  explicit `N/A` row) — no guessing whether deps exist. Deciding *which* deps belong is the
  author's job; the gate only enforces that the question was answered.

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
  guards: 3.1 standard-tier PLAN with a `TDD Applicable: yes` task lacking a code block →
  fail; 3.2 SPEC **missing the `External Documentation Checked` section entirely** → fail, and
  a SPEC with the section + an explicit `N/A — no external dependencies` row → pass (presence
  check, not dependency-guessing; TR7).
- Run one small standard-tier flow through the workflow and assert per artifact (review
  finding QR5 — don't require SPEC content in the PLAN): the **SPEC** contains the
  `External Documentation Checked` section (≥1 inventory row); the **PLAN** contains
  `PLAN-TASK-*` headings, a fenced code block in each `TDD Applicable: yes` task, and `- [ ]`
  steps. The External-Docs check is a SPEC-stage gate; the code-block/checkbox checks are
  PLAN-stage gates — they are not asserted on the same artifact.
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
  in `.claude/skills/req-to-plan.md` — both stale). Part 2 removes **25** (→ 469), Part 1 adds
  several. Settle the final baseline in both files after whichever parts are executed, not
  per-part.
- **NR1 review marker vs real review — RESOLVED (QR3):** the forced-review guard now requires
  a distinct `…-subagent-review-v<version>.md`, not the `review-checkpoint` marker, so forced
  review can no longer be self-satisfied (§1.5b). No longer open; noted here for history. If
  the maintainer instead wants the marker to suffice (lighter, but weakens forced review),
  flag it before implementing Part 1b.

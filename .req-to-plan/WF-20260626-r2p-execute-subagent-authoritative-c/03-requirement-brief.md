---
r2p_stage: requirement_brief
r2p_version: 1
r2p_status: approved
r2p_created_at: 2026-06-26T07:19:54.877810+00:00
r2p_updated_at: 2026-06-26T07:20:16.079638+00:00
---

# Requirement Brief

## Goal

Close the subagent-side context gap left by the shipped controller
context-management work (FR-CM1–CM5). Each fresh `r2p-execute` subagent role —
implementer (§2), task-reviewer (§5), and fix subagent (§6) — must receive the
**full, verbatim, authoritative** upstream context (requirement, risk, design,
spec, project baseline, execution ledger) by being handed **paths to the existing
on-disk artifacts and required to read them**, eliminating the
LLM-summarization-of-authority drift caused today by the §2 ad-hoc "Scene-setting
context" line, the reviewer seeing spec IDs only, and the fix subagent seeing only
a review report. The change is **template prose plus one docs-consistency test** —
no new artifact, no bundle, no hash gate, no CLI/gate/state/schema change — keeping
the controller path-only and preserving the FR-CM5 "no whole-plan read" boundary.

## In-Scope

- SCOPE-IN-001 Define one shared **`## Authoritative Context Set`** block in both
  orchestration surfaces — `02-project-context.md`, `03-requirement-brief.md`,
  `04-risk-discovery.md`, `05-design.md`, `06-spec.md`, and
  `execution/progress.md` handed as run-dir **paths** (never pasted bodies); the
  ledger is read-only to subagents.
- SCOPE-IN-002 Wire the set into all three dispatches: §2 implementer (and
  **remove** the ad-hoc "Scene-setting context" line, replacing it with the
  `02-project-context.md` pointer; keep `## Global Constraints` pasted), §5
  task-reviewer, §6 fix subagent (plus the task brief path and refreshed task diff
  path).
- SCOPE-IN-003 State an authority **responsibility matrix** (each artifact owns a
  domain, not a priority order) plus a **single conflict rule**: fail closed with
  `BLOCKED` + human **reopen** (no guessing, no winner, no patch-around), including
  the `02` baseline-vs-working-tree rule, the ledger read-only rule, and the
  `00`/`01`-are-provenance rule.
- SCOPE-IN-004 Require **consumption**: each subagent reads the full set before
  acting; it **may skip** the embedded `(read-only)` Upstream Summary / Project
  Context blocks; on-demand depth is scoped only to current code, git history, and
  prior task reports/reviews — never to whether to read an approved artifact.
- SCOPE-IN-005 Derive position/ownership from the ledger's `PLAN-TASK-NNN <title>`
  list; keep whole `07-plan.md` reasoning with the controller; on an unclear
  sibling boundary the subagent returns `NEEDS_CONTEXT` / `BLOCKED` and the
  controller hands a specific `r2p-task-brief --task <M>` sibling brief — never a
  whole-plan read or a guess from the title.
- SCOPE-IN-006 State the **path-delivery** rule (controller derives
  `run_dir = parent(plan)` from the execute output; absolute paths by default, or
  repo-root-relative paths paired with an explicit `repo_root`) and the
  **fail-closed context preflight** (every handed path exists, is readable, and
  resolves under the same `run_dir`/`work_id`, else `BLOCKED`).
- SCOPE-IN-007 Make the §6 fix loop **regenerate `logs/task-N-diff.md` from the
  task's BASE to `HEAD` after each fix wave before re-review**, via the single
  commit-then-diff pattern (fix subagent commits only its intentionally-changed
  files first); no uncommitted-working-tree re-review.
- SCOPE-IN-008 Add a **role-scoped** assertion to `tests/test_docs_consistency.py`
  covering both the claude and codex surfaces, in the established
  one-concern-per-test token-list shape, with a light per-role section slice so a
  filename appearing once cannot mask a role that omits the reference.

## Out-of-Scope

- SCOPE-OUT-001 `tools/workflow_cli/agent_templates/gemini/commands/r2p-execute.toml`
  — the 4-line pointer stays **unchanged**.
- SCOPE-OUT-002 `cli.py`, `gates.py`, `state.py`, `artifact.py`,
  `agent_shortcuts.py`, and the `tools/r2p-*` wrappers — **no** code, gate, state,
  schema, transition, or output-contract changes; `plan-task-brief` keeps its
  current `{work_id, task_id, brief_path}` output.
- SCOPE-OUT-003 `00-raw-requirement.md` / `01-intake-brief.md` content — they are
  provenance, not handed to subagents and not used as execution authority.

## Non-Goals

- **No generated `task-N-context.md` bundle** — the on-disk artifacts are the
  context; a copy only manufactures the copy-divergence a manifest would then have
  to police.
- **No `context-manifest.json`, no sha256 / content-hash, no drift gate** —
  re-affirms the prior doc's Non-Goal and the audit-only boundary
  (`r2p-execution-gate-boundary`); out-of-band source mutation stays a trust
  assumption, not a machine check.
- **No reference-closure re-resolution** in any command — the PLAN quality gate
  already enforces SPEC/SCOPE/RISK closure before `EXECUTING`.
- **No whole-`07-plan.md` handoff to subagents** — preserves FR-CM5; whole-plan
  reasoning stays with the controller's Pre-flight read.
- **No new CLI command, new state/JSON field, second state source, or
  receipt-based verification** — the trust/audit model is unchanged.

## Assumptions

- The Authoritative Context Set is present and current on disk throughout
  `EXECUTING`, guaranteed by upstream gates + human checkpoints; missing,
  unreadable, or wrong-run paths are caught by the SCOPE-IN-006 preflight
  (`BLOCKED`) or a loud read failure.
- `run-reopen` creates a **new** run (`WF-…-rN`) and never edits the source run's
  artifacts in place (verified, `cli.py` reopen path), so mid-execution artifact
  mutation is an out-of-band manual act, not a lifecycle event — kept a trust
  assumption exactly like the rejected hash gate.
- `02-project-context.md` is a **planning-time** repository baseline (generated
  once at run-start, `cli.py:348-349`), not current-HEAD truth; when completed
  predecessor tasks legitimately changed the repo, the current working tree is the
  operational truth.
- The execute shortcut returns the full `plan`/`ledger` paths plus `work_id`
  (`agent_shortcuts._cmd_execute`), so the controller derives `run_dir` without
  assuming the process cwd.
- Both orchestration surfaces already use the short-pasted-vs-large-as-path
  distinction and the commit-then-diff pattern, so this is in-grain prose, not new
  machinery.

## Acceptance Criteria

- AC-1 Both surfaces define the shared `## Authoritative Context Set`
  (`02`/`03`/`04`/`05`/`06`/`execution/progress.md` as paths), and the implementer
  (§2), task-reviewer (§5), and fix subagent (§6) each reference it.
- AC-2 §2's ad-hoc "Scene-setting context" line is replaced by the
  `02-project-context.md` pointer; `## Global Constraints` stays pasted.
- AC-3 The fix subagent also receives the task brief path and refreshed task diff
  path; §6 commits intentionally-changed files then regenerates
  `logs/task-N-diff.md` from task BASE→`HEAD` after each fix wave before re-review
  — one diff pattern, no uncommitted-working-tree diff.
- AC-4 Both surfaces require reading the set before acting, allow skipping embedded
  read-only summaries, and scope on-demand depth to code/history/prior reports.
- AC-5 Both surfaces carry the responsibility matrix, the single conflict rule
  (`BLOCKED` + human **reopen**), the `02` baseline-vs-working-tree rule, the
  ledger read-only rule, and the `00`/`01`-are-provenance rule.
- AC-6 The full `07-plan.md` is **not** added to the subagent read set; default
  ownership derives from the ledger; an unclear sibling boundary escalates
  (`NEEDS_CONTEXT` / `BLOCKED`) to the controller, which may hand a specific
  `r2p-task-brief --task <M>` sibling brief.
- AC-7 Both surfaces state the path-delivery rule and the fail-closed context
  preflight.
- AC-8 No generated `task-N-context.md`, no `context-manifest.json`, no hash/drift
  logic, no reference-closure re-resolution, no new CLI command, no
  `plan-task-brief` output change, no gate/state/schema change; `r2p-gap-open` does
  not appear in either surface.
- AC-9 `tests/test_docs_consistency.py` passes with the role-scoped assertion and
  the full suite stays green (`.venv/bin/python -m pytest tests/ -v`).

## Open Questions

None. The requirement is decision-complete: the bundle/manifest/hash alternative is
explicitly rejected with rationale, the authority model and conflict-handling are
fully specified, and the target surfaces, Non-Goals, and test shape are fixed.

## Sources

- `docs/r2p-execute-task-context-requirement.md` — this requirement (FR-AC1–AC7,
  Conflict Analysis, Acceptance Criteria, Test Plan).
- `docs/r2p-execute-context-management-requirement.md` — prior FR-CM1–CM5 work this
  builds on (whole-plan red flag, brief-path handoff, leak hierarchy).
- `tools/workflow_cli/agent_templates/claude/commands/r2p-execute.md` and
  `tools/workflow_cli/agent_templates/codex/skills/r2p-execute/SKILL.md` — the two
  target orchestration surfaces.
- `tests/test_docs_consistency.py` — the docs-consistency guard to extend.
- Verified code references: `models.py:83-88`, `context_pack.py:169-170`,
  `cli.py:348-349` / `:762` / `:1648-1699`, `gates.py:570-571`, `markdown.py:15` /
  `:62`, `agent_shortcuts._cmd_execute`.
- Project memory: `r2p-execution-gate-boundary`,
  `r2p-execute-per-task-base-deferral`.

## Trace
<!-- Map this stage's IDs to upstream/downstream. R3 derives & checks closure. -->
| This ID | Upstream | Status |
|---|---|---|
| SCOPE-IN-001 | FR-AC1 | open |
| SCOPE-IN-002 | FR-AC1 | open |
| SCOPE-IN-003 | FR-AC2 | open |
| SCOPE-IN-004 | FR-AC3 | open |
| SCOPE-IN-005 | FR-AC4 | open |
| SCOPE-IN-006 | FR-AC5 | open |
| SCOPE-IN-007 | FR-AC6 | open |
| SCOPE-IN-008 | FR-AC7 | open |
| SCOPE-OUT-001 | Target Surfaces / Files | open |
| SCOPE-OUT-002 | Non-Goals | open |
| SCOPE-OUT-003 | Non-Goals | open |

## Upstream Summary (read-only)
# r2p-execute Subagent Authoritative-Context Requirement

## Summary

A follow-on to the shipped **r2p-execute Controller Context-Management** work
(FR-CM1–CM5, see `docs/r2p-execute-context-management-requirement.md`). That work
bounded the **controller's** context: hand each task as a brief *path*, keep
returns to a few lines, route diffs/reports/reviews through files. This
requirement closes the complementary gap on the **subagent** side.

The controller is now lean, but each fresh subagent is **under-contextualized on
the authoritative upstream artifacts**:

- The **implementer** (`r2p-execute` §2) gets the task brief, the PLAN
  `## Global Constraints` (pasted), and an **ad-hoc, controller-hand-written
  "Scene-setting context (project, dependencies, architectural constraints)"**
  line. That hand-written summary is exactly the *LLM-summarization-of-authority*
  risk this requirement removes.
- The **task-reviewer** (§5) gets the brief's `Spec References` as **IDs only** —
  no pointer to the actual `06-spec.md` text, so it cannot check a requirement
  against the full behavior/interface/error contract.
- The **fix subagent** (§6) gets **only** `review_report_path` — no requirement,
  design, task-brief, or task-diff context, so a fix can satisfy a finding while
  drifting from the requirement, the chosen design, or the task's allowed scope.
- None of the three is pointed at `03-requirement-brief.md`,
  `04-risk-discovery.md`, `05-design.md`, or `02-project-context.md`, all of which
  already exist on disk in the run directory.

This is a primary source of PLAN→code drift: a task implemented *locally* correct
but violating global intent, the chosen design, a non-goal, or a cross-task risk.

The fix is **not** to generate a new context artifact. The authoritative
artifacts already sit on disk, fixed-named, gate-validated. The fix is to **hand
each subagent the paths to those live artifacts and require it to read the
originals** — pure template prose plus a docs-consistency test, no new machinery,
fully in-grain with the existing "hand artifacts as file paths" architecture.

## Motivation

The central thesis inherited from the superpowers SDD skill (and already encoded
in FR-CM) is a context-economy claim: *what the controller pastes/holds is
resident and compounds every turn; hand artifacts as files.* The leak-hierarchy
table in the prior doc established the corollary this requirement leans on:

| Context | Nature | Cost |
|---|---|---|
| Controller holds artifact bodies | resident, re-read **every turn, compounds** | high — must avoid |
| A one-shot subagent reads artifact files | lands in a **discarded** context, **does not compound** | low |

So enriching the *subagent's* context is cheap, and starving it is the expensive
mistake. The controller still hands only **paths** (the artifact filenames are
fixed constants — `models.py:83-88`, `context_pack.py:169-170` — a bounded,
constant, non-compounding addition to each dispatch, not artifact bodies).
Verbatim file reads carry **no** summarization: the authority is the on-disk
file, read directly.

## The decisive design choice: live artifact paths, not a generated bundle

An obvious-looking alternative — have the CLI deterministically assemble a
`task-N-context.md` bundle (concatenate the stripped artifacts + a snapshot + a
reference index) guarded by a `context-manifest.json` of sha256 hashes that blocks
execution on drift — was considered and **rejected**:

- **The bundle manufactures the copy-divergence it then polices.** The artifacts
  are already live files. Reading `05-design.md` **directly** always returns
  current bytes; there is no second copy to diverge, so the *source→bundle* copy
  drift — the only thing a manifest/hash gate would exist to detect — **cannot
  occur**. A generated bundle creates that second copy and therefore that gate's
  reason to exist. Remove the bundle, read live files, and both the bundle and the
  manifest are unnecessary.
  - **Scope of the claim (precise).** Live reads eliminate *copy divergence
    between an authoritative artifact and a generated bundle*. They do **not**
    claim to eliminate *source mutation* — a human hand-editing an approved
    artifact inside an `EXECUTING` run. That residual is governed by the same
    trust assumption the rest of the system already makes: approved artifacts are
    frozen by process discipline. The normal lifecycle does not mutate them:
    `run-reopen` creates a **new** run (`WF-…-rN`), copying artifacts up to the
    target stage into a fresh run dir, and never edits the source run's artifacts
    in place (verified, `cli.py` reopen path). So mid-execution artifact mutation
    is an out-of-band manual act, not a lifecycle event, and stays out of scope
    exactly like the rejected hash gate.
- **A content-hash drift gate is an explicit Non-Goal** of the prior doc — a
  machine assertion that a marker is true, which the deliberate audit-only
  architecture rejects.
- **The reference index is redundant.** Each artifact's seed template already
  carries its own upstream/downstream trace table (`stage_templates.py:14`), and
  cross-stage trace closure (every `SPEC-*` consumed, every `SCOPE-IN-*` carried,
  every `RISK-*` closed) is **already enforced at the PLAN quality gate** before a
  run can close at the PLAN checkpoint.
- **The snapshot is redundant.** `execution/progress.md` already lists every task
  as `- [ ] PLAN-TASK-NNN <title>` (`cli.py:762`); position / completed /
  remaining / ownership derive from it.

Net: live paths are cheaper, more in-grain, and remove the copy-divergence class
entirely without crossing the trust/audit boundary.

## Goals

- Give the implementer, the task-reviewer, and the fix subagent the **full,
  verbatim, authoritative** upstream context (requirement, risk, design, spec,
  project baseline) by handing **paths to the existing artifacts**, read directly
  — no controller-authored summary, no LLM re-summarization.
- Replace the ad-hoc "Scene-setting context" line (§2) with the deterministic
  `02-project-context.md` pointer.
- Make the reviewer check against the **full** `06-spec.md`, not the brief's IDs.
- Give the fix subagent the task brief + refreshed task diff + the same
  authoritative context so fixes stay anchored to task scope and design.
- **Require consumption, not just availability:** each subagent must read the
  authoritative set before acting (a handed path that is never opened is the same
  bug this requirement exists to fix).
- State an authority **responsibility matrix** + a single conflict rule so a
  subagent fails closed (`BLOCKED` / human reopen) on conflict or missing
  reference instead of guessing.
- Keep the controller path-only and **preserve FR-CM5**: subagents are *not*
  handed the whole `07-plan.md` (that would reintroduce the "read the whole plan"
  red flag FR-CM5 removed); an unclear sibling boundary escalates to the
  controller for a specific single-task brief, never a whole-plan read.
- Replicate the prose across both orchestration surfaces and lock it with a
  **role-scoped** `tests/test_docs_consistency.py` assertion.

## Non-Goals

- **No generated `task-N-context.md` bundle.** The artifacts on disk are the
  context; a copy only manufactures copy-divergence.
- **No `context-manifest.json`, no sha256 / content-hash, no drift gate.**
  Re-affirms the prior doc's Non-Goal and the audit-only decision
  (`r2p-execution-gate-boundary`). Live reads remove the copy-divergence class;
  out-of-band source mutation stays a trust assumption, not a machine check.
- **No reference-closure re-resolution in any command.** PLAN quality gate
  already enforces SPEC/SCOPE/RISK closure (`_check_plan_task_fields`,
  `gates.py:570-571`, plus cross-stage trace closure) before `EXECUTING`.
- **No whole-`07-plan.md` handoff to subagents.** Preserves FR-CM5; whole-plan
  reasoning stays with the controller (see FR-AC4).
- **No new machine gate, state transition, or artifact schema change.**
  `gates.py`, `state.py`, `artifact.py` untouched.
- **No new CLI command, and no change to any existing command's output
  contract.** This is **prose + test only**. `plan-task-brief` keeps its current
  `{work_id, task_id, brief_path}` output (`cli.py:1648-1699`). (The earlier
  optional `plan-task-brief` path-emission idea is dropped — run_dir is derivable
  from the execute output without it; see FR-AC5.)
- **No new derived/JSON state fields and no second state source.**
- **No receipt-based verification.** Trust/audit model unchanged.
- **No `00-raw-requirement.md` / `01-intake-brief.md` as authority.** `00` is
  provenance; `01` is intake evidence whose *consequences* already live
  authoritatively in `03`/`04`/`05`/`06`. Neither is handed to subagents.

## Background: Current State (verified against code)

- Authoritative artifacts are fixed-named files in the run dir:
  `02-project-context.md/json`, `03-requirement-brief.md`,
  `04-risk-discovery.md`, `05-design.md`, `06-spec.md`, `07-plan.md`
  (`models.py:83-88`, `context_pack.py:169-170`).
- `02-project-context.md` is generated **once at run-start**
  (`cli.py:348-349`, inside `_cmd_run_start`); it is **not** regenerated per
  execution task. It is therefore a *planning-time* repository baseline, not
  current-HEAD truth (FR-AC2).
- `run-execute-start` seeds `execution/progress.md` with one
  `- [ ] PLAN-TASK-NNN <title>` line per PLAN anchor (`cli.py:762`), so the ledger
  already exposes the full task **ID + title** list to any reader.
- `run-reopen` creates a **new** run (`WF-…-rN`) and never edits the source run's
  artifacts in place (`cli.py` reopen path).
- The execute shortcut returns the run's full `plan` and `ledger` paths plus
  `work_id` (`agent_shortcuts.py` `_cmd_execute`), so the controller can derive
  `run_dir = parent(plan)` without assuming the current working directory.
- Each artifact embeds `(read-only)` "Upstream Summary" / "Project Context"
  blocks (`markdown.py:15`); `strip_readonly_sections` (`markdown.py:62`) is a
  public primitive. Subagents skip those embedded blocks (the canonical upstream
  is handed separately), so no assembler is needed to de-duplicate.
- Current dispatch context (`agent_templates/claude/commands/r2p-execute.md`):
  §2 implementer = brief + ad-hoc scene-setting + pasted Global Constraints;
  §5 reviewer = brief (IDs) + report path + diff path + review path + pasted
  Global Constraints; §6 fix = `review_report_path` only.

## Functional Requirements

Prose lands in **both** orchestration surfaces (see Target Surfaces). Gemini
`r2p-execute.toml` is a 4-line pointer with no body and is unchanged.

### FR-AC1: The Authoritative Context Set, handed to all three subagent roles

Define one named **Authoritative Context Set** (a shared template block all three
roles reference), handed as run-dir paths, never pasted bodies:

- `03-requirement-brief.md` — Goal / In-Scope / Out-of-Scope / Non-Goals /
  Acceptance Criteria (the requirement authority).
- `05-design.md` — Chosen Design, Options Considered (rejected), Rollback,
  Observability, SPEC Handoff.
- `06-spec.md` — full behavior / interface / data / error / test contracts (so
  `Spec References` IDs resolve to real text and global contracts).
- `04-risk-discovery.md` — cross-task risks and mitigations.
- `02-project-context.md` — planning-time repository baseline.
- `execution/progress.md` — the execution ledger (task ID + title list, position,
  completion, adjudication records); **read-only to subagents**.

Wire it into each dispatch:

- **§2 implementer** — hand the Authoritative Context Set; **remove** the ad-hoc
  "Scene-setting context" line. Keep the brief path, pasted `## Global
  Constraints`, TDD/`Verification` instructions, the report-output path, and the
  minimal return contract.
- **§5 task-reviewer** — hand the same set alongside the brief path, the
  implementer report path, the task diff path, and the review-output path.
- **§6 fix subagent** — hand the same set alongside `review_report_path`, **the
  task brief path**, and the **refreshed** task diff path (FR-AC6), so fixes know
  the task's exact allowed Files/Steps/Verification and what was implemented. Keep
  "do not paste finding bodies".

`## Global Constraints` stays **pasted** (short, shared); the large artifacts are
handed as **paths** — the same short-pasted / large-as-path distinction the
template already uses. The full `07-plan.md` is **not** in the set (FR-AC4).

### FR-AC2: Authority responsibility matrix + conflict rule

State authority as a **responsibility matrix** (each artifact owns a domain), not
an implied priority order that could be misread as "a PLAN-TASK overrides SPEC":

- the **task brief** defines the current task's execution scope, planned files,
  steps, and verification;
- `03-requirement-brief.md` defines goal, scope, non-goals, acceptance;
- `04-risk-discovery.md` defines risk constraints and mitigations;
- `05-design.md` defines chosen architecture and rejected alternatives;
- `06-spec.md` defines behavior, interface, data, error, and test contracts;
- `## Global Constraints` (pasted) defines plan-wide execution constraints;
- `02-project-context.md` is the **planning-time** repository baseline;
- the **current working tree / HEAD** is the operational truth about code that
  exists now;
- `00-raw-requirement.md` and `01-intake-brief.md` are **provenance, not
  execution authorities** — not handed, and never used to override `03`–`06`.

Baseline-vs-truth rule (the `02` caveat):

> If `02-project-context.md` differs from the current repository because completed
> PLAN-TASKs intentionally changed it (new deps, dirs, configs), the **current
> repository is the operational truth** — do not deny a predecessor's legitimate
> change because the planning baseline predates it. If the difference is
> unexplained or conflicts with the PLAN, return `BLOCKED`.

Single conflict rule:

> No artifact silently overrides another outside its domain. If the task cannot
> satisfy all applicable authorities simultaneously, return `BLOCKED`: identify
> the conflicting files/IDs and ask the human to **reopen** the owning stage. Do
> not guess, do not pick a winner, do not patch around an upstream defect.

(The wording says **reopen**, never "gap-open": execution runs are `closed`, so
the docs-consistency guard forbidding `r2p-gap-open` in `r2p-execute` stays green.)

### FR-AC3: Required consumption (not "depth by judgment")

> Each implementer, reviewer, and fix subagent **must read the full Authoritative
> Context Set before acting**. Availability is not consumption: a path that is
> handed but not read reproduces the drift this requirement removes. Within those
> files it **may skip** the embedded `(read-only)` Upstream Summary / Project
> Context blocks, because the canonical upstream artifact is handed separately.
> *On-demand* depth (read-as-needed) applies only to the **current codebase, git
> history, and prior task reports/reviews** — never to whether to read an approved
> artifact.

This supersedes the earlier "reads them to the depth the task warrants" framing,
which reintroduced the failure mode. It is consistent with the project principle
"do not cut authoritative context for tokens"; the read is the one-shot,
non-compounding cost the leak hierarchy classifies as low, and model sizing
(Model Selection) is orthogonal — a cheap model on a mechanical task still reads
the set.

### FR-AC4: Position / ownership via the ledger; whole plan stays with the controller

Position and sibling-ownership awareness come from `execution/progress.md`, whose
ledger already lists **every** task as `- [ ] PLAN-TASK-NNN <title>`
(`cli.py:762`). That ID + title list is sufficient for orientation and
**default** ownership awareness — the subagent stays within its brief's
Files/Steps and treats every other listed task ID as owned elsewhere — but it is
**not** always sufficient to resolve a cross-task *boundary* question (e.g. where
"add endpoint" ends and a sibling "add validation" / "add error handling"
begins).

The full `07-plan.md` is **deliberately not handed to subagents.** Adding it to
the required-read set (FR-AC3) would make every implementer/reviewer/fix subagent
read the whole plan on every task — precisely the leak FR-CM5 removed (the prior
requirement names *"make a subagent read the whole plan file"* an explicit red
flag and added `plan-task-brief` to avoid it). Whole-plan reasoning (cross-task
contradiction scanning) stays with the **controller**, which already performs it
once at Pre-flight. A predecessor's effect is read from the **committed code**
(operational truth, FR-AC2) and its `task-N-report.md`, not from the PLAN's
sibling-task body.

**Targeted sibling escalation (not a whole-plan read).** If the current task's
boundary with a sibling task is unclear from the task brief, `## Global
Constraints`, and the progress ledger, the subagent returns
`NEEDS_CONTEXT` / `BLOCKED` rather than guessing from the title. The controller
then either resolves the boundary itself (it holds the Pre-flight whole-plan read)
or hands the **specific** sibling task brief produced by `r2p-task-brief --task
<M>` (a single-task brief path — the same primitive used for the current task) and
re-dispatches. The subagent never reads the whole plan file.

> `execution/progress.md` is read-only to subagents; only the controller flips
> checkboxes or appends `Resolved:` / `Gap:` / `Unresolved:` / `Minor:` records.

### FR-AC5: Path delivery + fail-closed context preflight (prose)

**Delivery.** The controller derives the run dir from the execute output rather
than assuming the working directory: `run_dir = parent(plan)` (the execute
shortcut returns the full `plan`/`ledger` paths and `work_id`). It hands absolute
paths by default. If it hands repository-root-relative paths, it must also hand an
explicit `repo_root` / base path, and the subagent resolves those paths only
against that root. This keeps `--base-path`, cross-project, and
`cwd ≠ target repo` cases from resolving paths against the wrong process cwd.

**Preflight (no CLI mechanism, subagent prose).** Before acting (and before
changing code for implementer/fix roles), each subagent:

> 1. confirms every Authoritative Context Set path exists and is readable;
> 2. confirms every handed context path, task brief path, ledger/progress path,
>    review-report path, and task-diff path resolves under the same derived
>    `run_dir` / `work_id` when that role receives it;
> 3. confirms any repository-root-relative path was resolved against the explicit
>    handed `repo_root`, not the process cwd;
> 4. returns `BLOCKED` if any path is missing, unreadable, unresolved, or wired to
>    a different run — it does **not** silently continue on a partial or mixed set.

This keeps "hand the full set" from degrading into "read whatever happens to be
present" if a run is corrupted or a file was manually deleted (the upstream gates
make this rare, not impossible).

### FR-AC6: Refresh the per-task diff after each fix wave

The per-task fix loop (§6) currently re-dispatches the task-reviewer after a fix
wave without explicitly regenerating `logs/task-N-diff.md`, so the reviewer can
re-read the **pre-fix** diff (the Final Whole-Branch Review already refreshes its
diff after fixes; the per-task loop should match):

> After each fix wave, regenerate `logs/task-N-diff.md` from the task's BASE to
> current `HEAD` before re-dispatching the task-reviewer. (The controller recorded
> that BASE before dispatching this task's implementer — §2 — so the range is
> already in hand; this is the same-task fix loop, not a resume, so it does not
> depend on the deferred per-task-BASE durability residual.)
>
> The refreshed diff must reflect the post-fix code state, via the **single**
> commit-then-diff pattern used everywhere else in the template. The fix subagent
> commits its changes — staging only files intentionally changed for this task,
> exactly as the implementer does in §2 — before the diff is regenerated, so
> `git diff -U10 <base-commit> HEAD` reflects the fix and captures any new files.
> Do **not** re-review against an uncommitted working tree: that is the stale-diff
> bug this FR removes, and a `BASE`→working-tree diff would additionally miss
> untracked new files.

### FR-AC7: Role-scoped docs-consistency test

Add a focused test in `tests/test_docs_consistency.py` (claude + codex) in the
established one-concern-per-test, token-list shape used by the other execute-surface
guards. Most assertions reuse that whole-file token-presence pattern; the **only**
new logic is a light per-role check (slice the §2 / §5 / §6 bodies by their
`### ` headings and assert each contains the shared-block reference) so a filename
appearing once at the top cannot pass while a role omits it — no full section
parser is needed. Define a shared `## Authoritative Context Set` block and have
each role reference it; assert:

1. the shared block lists `02`, `03`, `04`, `05`, `06`, and `execution/progress.md`;
2. the implementer section references the shared block;
3. the reviewer section references the shared block;
4. the fix loop references the shared block (plus brief + refreshed diff);
5. the conflict rule + responsibility matrix are present;
6. the ledger is stated read-only to subagents;
7. `00-raw-requirement.md` / `01-intake-brief.md` are **absent** from the set
   block, and the full `07-plan.md` is **not** added to the subagent read set;
8. the targeted sibling escalation is present (an unclear boundary →
   `NEEDS_CONTEXT` / `BLOCKED` → controller hands a specific
   `r2p-task-brief --task <M>` sibling brief), never a whole-plan read;
9. the fix loop regenerates `logs/task-N-diff.md` before re-review (FR-AC6);
10. `r2p-gap-open` still does not appear.

Keep assertions to stable, load-bearing phrases; do not pin incidental wording.

## Conflict Analysis (the explicit review)

| Dimension | Finding |
|---|---|
| **vs FR-CM5 (whole-plan red flag)** | **Preserved by FR-AC4.** The set excludes `07-plan.md`; subagents never read the whole plan. Ownership awareness uses the ledger's ID+title list; whole-plan reasoning stays with the controller's Pre-flight read. |
| **vs FR-CM1 (brief-path handoff / minimal return)** | **Reinforces.** Adds more authoritative *paths* to the same dispatches; returns stay minimal; the controller ingests no artifact body. |
| **Controller context economy** | **Preserved.** Fixed filename constants per dispatch — bounded, non-compounding; not content. |
| **Leak hierarchy** | **Consistent.** Required subagent reads are the cheap, non-compounding tier. |
| **Model Selection** | **Orthogonal.** FR-AC3 required-read is about context, not model capability; a cheap model still reads the set. |
| **Machine gates / state / schema / trust model** | **None touched.** Conflict handling is agent judgment (`BLOCKED`) + human reopen; `02` baseline-vs-truth is prose. |
| **vs rejected bundle/manifest** | **Superseded with rationale.** Live paths remove copy-divergence; the manifest's only job was to police a copy this design never creates. Out-of-band source mutation remains a trust assumption, consistent with audit-only. |
| **`r2p-gap-open` guard** | **Honored.** Conflict prose says "reopen", never "gap-open". |

## Target Surfaces / Files

1. `tools/workflow_cli/agent_templates/claude/commands/r2p-execute.md` — FR-AC1–AC6 prose.
2. `tools/workflow_cli/agent_templates/codex/skills/r2p-execute/SKILL.md` — same prose intent.
3. `tools/workflow_cli/agent_templates/gemini/commands/r2p-execute.toml` — **unchanged**.
4. `tests/test_docs_consistency.py` — FR-AC7 role-scoped assertion.

No CLI, gate, state, schema, or wrapper file changes.

## Acceptance Criteria

- Both surfaces define a shared `## Authoritative Context Set`
  (`02`/`03`/`04`/`05`/`06`/`execution/progress.md` as paths) and have the
  implementer (§2), task-reviewer (§5), and fix subagent (§6) each reference it.
- §2's ad-hoc "Scene-setting context" line is replaced by the
  `02-project-context.md` pointer; `## Global Constraints` stays pasted.
- The fix subagent also receives the task brief path and the refreshed task diff
  path; the fix subagent commits its intentionally-changed files (like the
  implementer in §2) and §6 regenerates `logs/task-N-diff.md` from task BASE→HEAD
  after each fix wave before re-review — one diff pattern, no uncommitted
  working-tree diff.
- Both surfaces require each subagent to **read** the set before acting (FR-AC3),
  allow skipping embedded read-only summaries, and scope on-demand depth to
  code/history/prior reports.
- Both surfaces carry the responsibility matrix, the single conflict rule
  (`BLOCKED` + human **reopen**; no guessing, no winner, no patch-around), the
  `02` baseline-vs-working-tree rule, the ledger read-only rule, and the
  `00`/`01`-are-provenance rule.
- The full `07-plan.md` is **not** added to the subagent read set; default
  ownership awareness derives from the ledger, and an unclear sibling boundary
  escalates (`NEEDS_CONTEXT` / `BLOCKED`) to the controller — which may hand a
  specific `r2p-task-brief --task <M>` sibling brief — instead of a whole-plan
  read or a guess from the title.
- Both surfaces state the path-delivery rule (derive run_dir from the execute
  output; prefer absolute paths, or pair repo-root-relative paths with an explicit
  `repo_root`) and the fail-closed context preflight (paths resolve under the same
  run_dir / `work_id`, else `BLOCKED`).
- No generated `task-N-context.md`, no `context-manifest.json`, no hash/drift
  logic, no reference-closure re-resolution, no new CLI command, no change to
  `plan-task-brief`'s output, no gate/state/schema change.
- `tests/test_docs_consistency.py` passes with the role-scoped assertion; the
  full suite stays green.

## Test Plan

- **`tests/test_docs_consistency.py`** — extend the execute-surface assertion to
  the role-scoped checks in FR-AC7 across claude + codex; keep tokens
  stable/load-bearing.
- **Full suite** stays green; no new CLI test (no CLI change).

## Risks

- **Wording drift between surfaces.** Mitigated by the role-scoped assertion on
  both files.
- **Over-tokenizing the test.** Keep to stable phrases; do not pin incidental
  wording.
- **Required-read cost on large runs.** Accepted: one-shot, non-compounding, and
  the project explicitly prefers full authoritative context over token savings;
  skipping embedded read-only summaries trims the largest redundancy.
- **Fragile assumption (accepted):** the Authoritative Context Set is present and
  current on disk during `EXECUTING`. Guaranteed by upstream gates + checkpoints.
  Out-of-band deletion, unreadable paths, or paths wired to a different run are
  caught by the FR-AC5 preflight (`BLOCKED`) or a loud path-read failure. Readable
  in-place mutation of an approved artifact mid-run is not machine-detected unless
  it creates an observable authority conflict; it remains a trust assumption, not
  a hash/drift gate — consistent with the audit-only boundary.

## Verification Commands

```bash
# Local: must use the venv (system python3 lacks pyyaml).
.venv/bin/python -m pytest tests/test_docs_consistency.py -v
.venv/bin/python -m pytest tests/ -v          # full suite stays green
```
<!-- /r2p-read-only -->

## Project Context (read-only)
# Project Context Pack

- repo_root: `/Users/xubo/x-skills/req-to-plan`
- languages: {'Python': 21931, 'JavaScript': 31}
- package_managers: npm, pip
- test_commands: ['npm test']
- entrypoints: ['tools/workflow_cli/__main__.py']
- config_files: ['requirements.txt']
- dependencies (1):
  - pyyaml>=6.0 (pip)
- source_dirs: ['bin', 'docs', 'tests', 'tools']
<!-- /r2p-read-only -->

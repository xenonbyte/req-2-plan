---
r2p_stage: risk_discovery
r2p_version: 1
r2p_status: approved
r2p_created_at: 2026-06-26T07:22:04.288936+00:00
r2p_updated_at: 2026-06-26T07:22:10.737230+00:00
---

# Risk Discovery

## Risks

### RISK-DOC-001 Wording drift between the claude and codex surfaces
Status: mitigated
The same authoritative-context prose must land in **both**
`agent_templates/claude/commands/r2p-execute.md` and
`agent_templates/codex/skills/r2p-execute/SKILL.md`. If one surface omits a role
reference, a rule, or the shared block, subagents on that platform stay
under-contextualized — the exact drift this work removes — but on only one
surface, so it is easy to miss by eye. Likelihood: medium. Impact: high
(silent per-platform regression).

### RISK-DOC-002 Over-tokenized / brittle docs-consistency test
Status: mitigated
The FR-AC7 assertion could pin incidental wording, making every legitimate future
edit to the template fail the gate and pressuring authors to weaken or delete the
guard. Likelihood: medium. Impact: medium (long-term erosion of the guard).

### RISK-CTX-001 "Required-read" degrades into "read whatever is present"
Status: mitigated
On a corrupted, partial, or manually-edited run a handed path may be missing,
unreadable, or wired to a different run. Without a fail-closed rule a subagent
could silently continue on a partial set, reproducing the under-contextualization
the work removes while appearing to comply. Likelihood: low. Impact: high.

### RISK-CTX-002 Reintroducing the whole-plan read (FR-CM5 regression)
Status: mitigated
The natural way to give a subagent sibling-boundary awareness is to hand it
`07-plan.md`. Doing so makes every implementer/reviewer/fix subagent read the whole
plan on every task — precisely the leak FR-CM5 removed. Likelihood: medium (it is
the tempting fix). Impact: high (undoes shipped work).

### RISK-PATH-001 Path resolution against the wrong cwd / wrong run
Status: mitigated
In `--base-path`, cross-project, and `cwd ≠ target repo` cases, repo-root-relative
paths resolved against the process cwd can point a subagent at the wrong run or the
wrong repository — reading or even modifying unrelated state. Likelihood: low.
Impact: high (acts on wrong files).

### RISK-DIFF-001 Stale per-task diff at re-review
Status: mitigated
The §6 fix loop today re-dispatches the task-reviewer without regenerating
`logs/task-N-diff.md`, so the reviewer can re-read the **pre-fix** diff and approve
a fix it never actually saw, or a `BASE`→working-tree diff can miss untracked new
files. Likelihood: medium. Impact: medium (false-green per-task review).

### RISK-AUD-001 Crossing the audit-only trust boundary
Status: mitigated
The rejected bundle/manifest alternative is reachable by a well-meaning
"just add a sha256 drift gate" instinct. Adding any content-hash/drift gate would
violate the deliberate audit-only boundary (`r2p-execution-gate-boundary`) and
manufacture the copy-divergence it then polices. Likelihood: low. Impact: high
(architecture-level regression).

## Boundaries

- **Files touched:** exactly two template surfaces
  (`claude/commands/r2p-execute.md`, `codex/skills/r2p-execute/SKILL.md`) plus
  `tests/test_docs_consistency.py`. Everything else — `cli.py`, `gates.py`,
  `state.py`, `artifact.py`, `agent_shortcuts.py`, the `tools/r2p-*` wrappers, and
  `gemini/commands/r2p-execute.toml` — is **out of bounds** for this change.
- **Behavior boundary:** prose + test only. No machine gate, state transition,
  artifact schema, CLI command, JSON/derived field, or command output contract is
  added or changed.
- **Authority boundary:** subagents may **read** the Authoritative Context Set and
  the codebase, and **write** only their own task's code, report, review, and diff
  files; `execution/progress.md` is read-only to subagents (only the controller
  flips checkboxes / appends adjudication records).
- **Failure boundary:** on any unsatisfiable conflict or missing/unresolved path a
  subagent **fails closed** (`BLOCKED` / `NEEDS_CONTEXT`) and escalates to the
  controller or a human **reopen**; it never guesses, picks a winner, or patches
  around an upstream defect. Execution runs are `closed`, so routing is reopen —
  **never** `r2p-gap-open`.

## Scope Overflow Risks

### RISK-SCOPE-001 Rebuilding the rejected bundle / manifest / snapshot machinery
Status: mitigated
The decisive design choice is live artifact paths, not a generated
`task-N-context.md` bundle, a `context-manifest.json`, a hash gate, a reference
index, or a progress snapshot. Each rejected piece is individually tempting; adding
any of them re-creates the copy-divergence and trust-boundary problems the design
exists to avoid.

### RISK-SCOPE-002 Over-engineering the docs test into a section parser
Status: mitigated
FR-AC7 asks for a **light** per-role heading slice, not a full Markdown section
parser. Building a parser inflates scope and fragility for no added guarantee.

### RISK-SCOPE-003 Expanding the authoritative set beyond the named artifacts
Status: mitigated
Pressure to add `07-plan.md`, `00-raw-requirement.md`, or `01-intake-brief.md` to
the read set. `07` is the FR-CM5 regression; `00`/`01` are provenance whose
consequences already live in `03`–`06`. The set is fixed at
`02`/`03`/`04`/`05`/`06`/`execution/progress.md`.

## Mitigations

- **MIT-001** (RISK-DOC-001): the FR-AC7 role-scoped docs-consistency test asserts
  both surfaces, slicing the §2/§5/§6 bodies by their `### ` headings so a filename
  present once cannot mask a role that omits the reference.
- **MIT-002** (RISK-DOC-002, RISK-SCOPE-002): assert only stable, load-bearing
  phrases; reuse the existing whole-file token-presence pattern; add only the light
  per-role slice, no full parser.
- **MIT-003** (RISK-CTX-001): a fail-closed context **preflight** in subagent prose
  — every Authoritative Context Set path exists, is readable, and resolves under the
  same `run_dir`/`work_id`, else `BLOCKED`; no silent continue on a partial/mixed
  set.
- **MIT-004** (RISK-CTX-002, RISK-SCOPE-003): exclude `07-plan.md` from the set;
  ownership awareness derives from the ledger's `PLAN-TASK-NNN <title>` list; an
  unclear sibling boundary escalates (`NEEDS_CONTEXT`/`BLOCKED`) to the controller,
  which hands a specific `r2p-task-brief --task <M>` sibling brief — never a
  whole-plan read. The docs test asserts `07-plan.md` is absent from the set.
- **MIT-005** (RISK-PATH-001): controller derives `run_dir = parent(plan)` from the
  execute output; hands absolute paths by default, or repo-root-relative paths
  paired with an explicit `repo_root`; the preflight confirms repo-root-relative
  paths resolved against `repo_root`, not the process cwd.
- **MIT-006** (RISK-DIFF-001): the §6 fix loop regenerates `logs/task-N-diff.md`
  from the task's BASE to `HEAD` after each fix wave, via the single
  commit-then-diff pattern (fix subagent commits only its intentionally-changed
  files first), before re-dispatching the reviewer.
- **MIT-007** (RISK-AUD-001, RISK-SCOPE-001): the Non-Goals and the docs-consistency
  test forbid a generated bundle, `context-manifest.json`, sha256/content-hash, and
  any drift gate; out-of-band source mutation stays a trust assumption, consistent
  with the audit-only boundary.

## Trace
<!-- Map this stage's IDs to upstream/downstream. R3 derives & checks closure. -->
| This ID | Upstream | Status |
|---|---|---|
| RISK-DOC-001 | SCOPE-IN-001, SCOPE-IN-008 | open |
| RISK-DOC-002 | SCOPE-IN-008 | open |
| RISK-CTX-001 | SCOPE-IN-004, SCOPE-IN-006 | open |
| RISK-CTX-002 | SCOPE-IN-005 | open |
| RISK-PATH-001 | SCOPE-IN-006 | open |
| RISK-DIFF-001 | SCOPE-IN-007 | open |
| RISK-AUD-001 | SCOPE-OUT-002 | open |
| RISK-SCOPE-001 | SCOPE-OUT-002 | open |
| RISK-SCOPE-002 | SCOPE-IN-008 | open |
| RISK-SCOPE-003 | SCOPE-IN-001, SCOPE-IN-005 | open |

## Upstream Summary (read-only)
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

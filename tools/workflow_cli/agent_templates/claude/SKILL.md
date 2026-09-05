---
name: req-to-plan
description: Requirement-to-PLAN workflow skill (r2p {{R2P_VERSION}})
---

# req-to-plan Skill

Use this skill to drive the 5-stage requirement-to-PLAN workflow in any project where r2p is installed.

## Available Commands

Run each via Bash using the scripts in `{{R2P_BIN_DIR}}`:

| Command | Purpose |
|---|---|
| `{{R2P_BIN_DIR}}/r2p-start [--separate] [--repo-path <dir>] ("<requirement>" \| --file <path>)` | Start a new workflow run; `--repo-path` grounds tier estimation and the Context Pack in real repo facts |
| `{{R2P_BIN_DIR}}/r2p-continue` | Continue the active run |
| `{{R2P_BIN_DIR}}/r2p-tier-lock --work-id <id> --base <light\|standard> --confirm` | Lock the tier for a run |
| `{{R2P_BIN_DIR}}/r2p-status [--all]` | Inspect run state (read-only) |
| `{{R2P_BIN_DIR}}/r2p-switch --work-id <id>` | Switch active run pointer |
| `{{R2P_BIN_DIR}}/r2p-reopen --from <work-id> --stage <stage> --reason "<text>"` | Reopen a run and automatically archive its direct source |
| `{{R2P_BIN_DIR}}/r2p-abandon --work-id <id> --reason "<text>"` | Explicitly abandon and archive an unfinished open draft |
| `{{R2P_BIN_DIR}}/r2p-gap-open --work-id <id> --owner-stage <stage> --required-action "<text>"` | Route an upstream gap back to its owner stage |
| `{{R2P_BIN_DIR}}/r2p-gap-resolve --work-id <id> --route-id <route-id>` | Resolve an open upstream-gap route after the owner stage re-passes gate-quality |

## Usage Pattern

1. `r2p-start [--repo-path <dir>] ("<requirement>" | --file <path>)` — start a new run; pass `--repo-path` when the requirement targets an existing repo
2. `r2p-continue` — repeatedly; runs safe automatic steps, stops and suggests the next command when a human action is needed
   - Stops at: tier not locked, needs stage artifact content, needs stage ready mark, needs human checkpoint approval, entry gate failed, needs repair (Quality Gate failed or changes requested)
   - When stopped at `needs_content` or `needs_repair`, write the required artifact content into the printed `content_file`, then run the printed `next:` command exactly
   - For other stops, run the printed `next:` command exactly; if an `alt:` command is shown, use it only when that alternate decision is intended
   - Auto-runs: eligible entry gates, eligible Quality Gates, opens checkpoint review (`review-checkpoint`)
   - Auto-advances: moves to the next stage after non-PLAN checkpoint approval, then runs that stage's entry gate
   - Auto-closes: closes the run when the PLAN checkpoint is approved and no open routes remain
   - Does NOT auto-mark artifacts ready and does NOT auto-approve checkpoints — those are human steps
   - Standard-tier DESIGN: record any human technical choice in `## Decision Requests` as a `### DECISION-NNN` block (`Question:`/`Options:`/`Recommended:`/`Status: pending`); pending blocks `gate-quality` until a human selects (`Status: selected` + `Selected:`/`Rationale:`), or write exactly `none` when no decision is needed
   - At a checkpoint, only approve a DESIGN/SPEC/PLAN artifact that has no unresolved ambiguity or undecided point: resolve it by evidence, or route it (DESIGN: `### DECISION-NNN`; SPEC/PLAN: `r2p-gap-open`) before approving.
   - Never defer or drop requirement content while decomposing: everything the brief puts in scope must be implemented this run. The only skippable work is the brief's own `## Out-of-Scope` (SCOPE-OUT-*); to exclude anything else, route it back to the brief — never write "do later / not this round" in a downstream stage (the Quality Gate rejects unanchored deferral).
   - When authoring or repairing a PLAN, form a phase-level cohesive slice around one observable behavior or contract result. If it needs both create and modify paths, R19 requires an operation-homogeneous task group: each task has operation-homogeneous `Files` and a directly testable intermediate contract; the final integration/adoption task runs Phase acceptance. Do not split by file/class alone, create a wrapper before its target, or merge unrelated behavior into a mega-task.
   - The first semantic line in every task's `Steps` is exactly `Prerequisite: none` or `Prerequisite: PLAN-TASK-NNN`. Declare only direct predecessors in that task group; cross-Phase order follows PLAN order and prior Phase acceptance, not the rollback graph. Derive rollback only from those group-local prerequisite lines: roll back one task after its group's declared dependents, or roll back a whole group in reverse topological order without touching another Phase. Do not add a `Dependencies:` field.
   - Every generated v2 PLAN declares its prerequisite as the first semantic `Steps` line. The execution controller consumes it as a dispatch prerequisite gate using profile-aware prerequisite semantics; it must not be copied into `Verification` or rerun by a reviewer after implementation. Existing generated v1 PLAN invocations remain compatible.
3. When the run closes, hand the approved PLAN at `07-plan.md` directly to your executor — the PLAN is executor-neutral and needs no adaptation step.

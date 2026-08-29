---
description: Continue the active requirement-to-PLAN workflow run
---
Run `{{R2P_BIN_DIR}}/r2p-continue` to resume the currently selected run.

Usage: `{{R2P_BIN_DIR}}/r2p-continue`

Behavior:
- Performs safe automatic operations only: eligible entry gates, Quality Gates, opening checkpoint review (`review-checkpoint`), stage advancement after non-PLAN checkpoint approval, and run closure after PLAN checkpoint approval with no open routes
- Stops when human action is required: stage content generation, marking an artifact ready (`stage-ready`), Quality Gate failure or requested changes (repair), human checkpoint approval (`checkpoint-decide`), entry gate failure
- Stops with `needs_subagent_review` on forced-review runs (a `migration`/`safety`/`cross_project` modifier at `design`/`spec`/`plan`) when the required review file is missing. You are authorized to run a read-only review subagent yourself for this step — no separate human approval is needed
- Does NOT auto-mark artifacts ready and does NOT auto-approve checkpoints
- At a checkpoint, only approve a DESIGN/SPEC/PLAN artifact that has no unresolved ambiguity or undecided point: resolve it by evidence, or route it (DESIGN: `### DECISION-NNN`; SPEC/PLAN: `r2p-gap-open`) before approving
- Never defer or drop requirement content while decomposing: everything the brief puts in scope must be implemented this run. The only skippable work is the brief's own `## Out-of-Scope` (SCOPE-OUT-*); to exclude anything else, route it back to the brief — never write "do later / not this round" in a downstream stage (the Quality Gate rejects unanchored deferral)
- When authoring or repairing a PLAN, form a phase-level cohesive slice around one observable behavior or contract result. If it needs both create and modify paths, R19 requires an operation-homogeneous task group: each task has operation-homogeneous `Files` and a directly testable intermediate contract; the final integration/adoption task runs Phase acceptance. Do not split by file/class alone, create a wrapper before its target, or merge unrelated behavior into a mega-task.
- The first semantic line in every task's `Steps` is exactly `Prerequisite: none` or `Prerequisite: PLAN-TASK-NNN`. Declare only direct predecessors in that task group; cross-Phase order follows PLAN order and prior Phase acceptance, not the rollback graph. Derive rollback only from those group-local prerequisite lines: roll back one task after its group's declared dependents, or roll back a whole group in reverse topological order without touching another Phase. Do not add a `Dependencies:` field.
- Every generated v1 PLAN puts `execution-prerequisite-check --work-id <id> --task <N> --require-version 1` first in `Verification` before dispatch. It requires strict-compatible state and fails closed on fast-only state; do not claim fast support until the Phase 3 adoption explicitly upgrades generated Plans.

Call repeatedly until the output says `stop:` with a message indicating why the run paused. For `needs_content` and `needs_repair`, write the required artifact content into the printed `content_file`, then run the printed `next:` command exactly. For `needs_subagent_review`, run a review subagent to audit the stage artifact, write its findings to the printed `review_file`, then resume with `r2p-continue` (you do not need to ask for approval to spawn the review subagent). For other stops, run the printed `next:` command exactly. If an `alt:` command is shown, use it only when that alternate decision is intended. Resume with `r2p-continue` after completing that step.

Use `r2p-status` to inspect progress without making changes.

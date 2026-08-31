---
name: r2p-continue
description: Continue the active requirement-to-PLAN workflow run. Use when the user asks to run r2p-continue, continue r2p, resume the active r2p run, or advance the current requirement-to-PLAN workflow.
---

# r2p-continue

Run `{{R2P_BIN_DIR}}/r2p-continue` to resume the currently selected run.

Usage: `{{R2P_BIN_DIR}}/r2p-continue`

At a checkpoint, only approve a DESIGN/SPEC/PLAN artifact that has no unresolved ambiguity or undecided point: resolve it by evidence, or route it (DESIGN: `### DECISION-NNN`; SPEC/PLAN: `r2p-gap-open`) before approving.

Never defer or drop requirement content while decomposing: everything the brief puts in scope must be implemented this run. The only skippable work is the brief's own `## Out-of-Scope` (SCOPE-OUT-*); to exclude anything else, route it back to the brief — never write "do later / not this round" in a downstream stage (the Quality Gate rejects unanchored deferral).

When authoring or repairing a PLAN, form a phase-level cohesive slice around one observable behavior or contract result. If it needs both create and modify paths, R19 requires an operation-homogeneous task group: each task has operation-homogeneous `Files` and a directly testable intermediate contract; the final integration/adoption task runs Phase acceptance. Do not split by file/class alone, create a wrapper before its target, or merge unrelated behavior into a mega-task.

The first semantic line in every task's `Steps` is exactly `Prerequisite: none` or `Prerequisite: PLAN-TASK-NNN`. Declare only direct predecessors in that task group; cross-Phase order follows PLAN order and prior Phase acceptance, not the rollback graph. Derive rollback only from those group-local prerequisite lines: roll back one task after its group's declared dependents, or roll back a whole group in reverse topological order without touching another Phase. Do not add a `Dependencies:` field.

Every generated v2 PLAN puts `execution-prerequisite-check --work-id <id> --task <N> --require-version 2` first in `Verification` before dispatch. It uses profile-aware prerequisite semantics and fails closed on malformed, discontinuous, or non-actionable state. Existing generated v1 PLAN invocations remain compatible.

Call repeatedly until the run reaches the closed state. For `needs_content` and `needs_repair` stops, write the required artifact content into the printed `content_file`, then run the printed `next:` command exactly. For a `needs_subagent_review` stop (forced-review runs: a `migration`/`safety`/`cross_project` modifier at `design`/`spec`/`plan`), run a read-only review subagent to audit the stage artifact yourself — no separate human approval is needed — write its findings to the printed `review_file`, then resume with `r2p-continue`. For other stops, run the printed `next:` command exactly. If an `alt:` command is shown, use it only when that alternate decision is intended. Use `r2p-status` to inspect progress.

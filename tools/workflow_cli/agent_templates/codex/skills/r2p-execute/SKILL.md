---
name: r2p-execute
description: Execute a closed run's PLAN in place on the current branch via the subagent-driven SDD loop, then archive. Use when the user asks to run r2p-execute, execute the plan, start execution of the r2p run, or implement the PLAN tasks.
---

# r2p-execute — SDD Execution Loop

Execute each PLAN-TASK on the **current branch** using a fresh implementer subagent per task, a task-reviewer after each, and a whole-branch review at the end.

**Subagents are a hard prerequisite.** If this platform cannot dispatch subagents, fail explicitly and let the human decide — never silently fall back to sequential execution.

## Precondition Gate

Run `{{R2P_BIN_DIR}}/r2p-execute` and read its stop output. On a `closed_at_plan_checkpoint` run it transitions the run to `executing` (via the `run-execute-start` CLI command) and stops with `execute_plan`; on an already-`executing` run it stops with `resume_execution`; on any other status it stops with `plan_not_ready`.

- If the run status is `closed_at_plan_checkpoint` (first execution): the command transitions it to `executing` and returns the plan path.
- If the run status is already `executing` (resume after interruption): proceed directly to the plan path.
- Any other status → `plan_not_ready`. Stop and tell the user.

## In-Place Execution (no branch)

Work directly on the **current branch** — do NOT create a new branch, worktree, or protection boundary.

Before task 1, run `git status --short -- ':!.req-to-plan'` to check the code working tree (excluding `.req-to-plan/` state). If there are uncommitted changes, warn the user but do NOT block execution — they may have intentional in-progress work. `push` and PR creation are out of scope; request them explicitly from the user.

## Pre-flight Plan Review

Before dispatching Task 1, read `07-plan.md` once and scan for:
- Tasks that contradict each other or the plan's Global Constraints
- Items the plan mandates that the review rubric would treat as a defect

Batch all findings into one question to the human **before** execution begins — one interrupt, not one per discovery. If the scan is clean, proceed without comment. The task-reviewer loop catches conflicts that only emerge from implementation.

## Per-Task Loop

For each PLAN-TASK (in order):

### 1. Extract task inline

Read the task text directly from `07-plan.md`. Note the task's `Skeleton`, `Steps`, `Spec References`, and `Verification` criteria.

### 2. Dispatch a fresh implementer subagent

Provide the subagent with:
- The task text (from `07-plan.md`)
- Scene-setting context (project, dependencies, architectural constraints)
- TDD instructions: follow `Skeleton`/`Steps`; prove `Verification` with evidence
- A report file path (`execution/task-N-report.md`)

The implementer must:
1. Implement exactly what the task specifies, following TDD
2. Satisfy the task's `Verification` criteria and attach evidence (test output, assertions)
3. Commit the work
4. Self-review and report back

### 3. Handle implementer status

- **DONE / DONE_WITH_CONCERNS**: proceed to review
- **NEEDS_CONTEXT**: the implementer needs missing information — provide it and re-dispatch the fresh implementer subagent
- **BLOCKED**: assess the blocker; provide context, use a more capable model, or break the task into smaller pieces; escalate to the human if the plan itself is wrong

### 4. Ambiguity ladder

The fresh implementer subagent verifies-then-removes ambiguity by evidence and TDD. If it cannot resolve ambiguity:
- Return `NEEDS_CONTEXT` or `BLOCKED` and escalate to the human — never guess a vague implementation
- If the ambiguity is an upstream (SPEC or DESIGN) defect, stop and ask the human to choose an upstream repair path (for example, reopening from the affected stage) rather than patching over it in execution. Do not try to open a gap route from an `executing` run.

### 5. Write diff and dispatch task-reviewer

After the implementer reports DONE:
1. Record the diff inline: `git diff -U10 <base-commit> HEAD`
2. Dispatch a task-reviewer subagent with:
   - The task text and `Spec References` from `07-plan.md`
   - The implementer's report
   - The diff
   - Global constraints from the plan

The task-reviewer returns two verdicts:
- **Spec compliance**: checked against `Spec References` + `Verification`
- **Code quality**: clean, tested, maintainable

### 6. Fix loop

- Dispatch fix subagents for Critical and Important findings
- Re-dispatch the task-reviewer after each fix wave
- Only when the task-reviewer is clean (both spec ✅ and quality Approved, and `Verification` satisfied), update the matching `execution/progress.md` checkbox from `- [ ] PLAN-TASK-NNN ...` to `- [x] PLAN-TASK-NNN ...` and append one line:
  `Task N: complete (commits <base7>..<head7>, review clean)`

## Final Whole-Branch Review

After all tasks complete, dispatch a final whole-branch review subagent:
- Scope: all commits since the branch started (or since `closed_at_plan_checkpoint`)
- Include the diff (`git diff -U10 <merge-base> HEAD`)
- This whole-branch review is the merge gate
- Dispatch fix subagents for any Critical/Important findings before marking done

## Auto-Archive on Completion

When all tasks are done and the final whole-branch review is clean, call:

```
{{R2P_BIN_DIR}}/r2p-archive --work-id <work_id from the precondition output>
```

Commits are already on the **current branch**. `push` and PR creation still require an explicit user request.

## Durable Progress

Track progress in `execution/progress.md` (not only in todos). On resume, read the ledger and skip tasks already marked complete.

## Error Reference

| Condition | Action |
|---|---|
| Status not `closed_at_plan_checkpoint` or `executing` | Stop: `plan_not_ready` |
| Implementer returns `NEEDS_CONTEXT` | Provide missing context, re-dispatch fresh implementer subagent |
| Upstream SPEC/DESIGN defect found | Stop: ask the human to reopen/repair the upstream stage |
| Platform lacks subagent capability | Fail explicitly (subagents are a hard prerequisite) |

Use `r2p-status` to inspect progress without making changes.

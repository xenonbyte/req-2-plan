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

Before task 1, run `git status --short -- ':!.req-to-plan'` to check the code working tree (excluding `.req-to-plan/` state). If there are uncommitted changes, stop before dispatching Task 1 and ask the user to clean, stash, or commit that work, or to explicitly identify which dirty paths belong to this execution and approve task-only staging. Do not commit unrelated work. `push` and PR creation are out of scope; request them explicitly from the user.

## Pre-flight Plan Review

Before dispatching Task 1, read `07-plan.md` once and scan for:
- Tasks that contradict each other or the plan's Global Constraints
- Items the plan mandates that the review rubric would treat as a defect

Batch all findings into one question to the human **before** execution begins — one interrupt, not one per discovery. If the scan is clean, proceed without comment. The task-reviewer loop catches conflicts that only emerge from implementation.
If a finding requires PLAN, SPEC, or DESIGN repair, stop and ask the human to reopen from the affected stage rather than patching over it in execution.

## Model Selection

Use the least powerful model that can handle each role:
- **Mechanical implementation** (isolated, clear spec, complete `Skeleton`, 1–2 files): fast/cheap model.
- **Integration / judgment / debugging** (multi-file coordination, pattern matching): standard model.
- **Architecture / design AND the final whole-branch review**: most capable model.
- Always specify the model explicitly when dispatching; an omitted model inherits the session model.
- Read the task brief on demand when sizing the implementer model; do not paste or retain a rewritten copy of it.
- **Turn count beats token price**: use a mid-tier floor for reviewers and for implementers working from prose descriptions; drop to cheapest only for complete-code/single-file mechanical tasks.

## Controller Narration Discipline

Between tool calls, the controller narrates at most one short line. Use the prefix `Narration:` for these inter-call notes (e.g. `Narration: implementer returned DONE, writing diff`). Never paste a subagent's returned text — report body, diff content, or review findings — into a later dispatch; reviewer findings move through `review_report_path`, not pasted text. What the controller restates into its own context is bounded to `status`, `report_path` or diff path, `review_report_path`, `commit_range`, `test_summary`, and `concerns`.

## Authoritative Context Set

Each subagent (implementer, reviewer, fix) receives these run-dir paths and reads them directly — bodies are never pasted:

| Path | Domain |
|---|---|
| `02-project-context.md` | planning-time repository baseline |
| `03-requirement-brief.md` | goal / scope / non-goals / acceptance |
| `04-risk-discovery.md` | cross-task risks and mitigations |
| `05-design.md` | chosen design and rejected alternatives |
| `06-spec.md` | full behavior / interface / data / error / test contracts |
| `execution/progress.md` | execution ledger (task ID + title list), read-only to subagents |

`07-plan.md`, `00-raw-requirement.md`, and `01-intake-brief.md` are **not** in the set. No generated `task-N-context.md` bundle, `context-manifest.json`, sha256/content-hash, or drift gate is introduced.

### Authority Responsibility Matrix

Each authority owns exactly its domain — this is a matrix, not a priority order:

| Authority | Owns |
|---|---|
| Task brief | Current task execution scope / files / steps / verification |
| `03-requirement-brief.md` | Goal / scope / non-goals / acceptance |
| `04-risk-discovery.md` | Risk constraints and mitigations |
| `05-design.md` | Chosen architecture and rejected alternatives |
| `06-spec.md` | Behavior / interface / data / error / test contracts |
| `## Global Constraints` | Plan-wide execution constraints |
| `02-project-context.md` | Planning-time repository baseline |
| Current working tree / HEAD | Operational truth about code that exists now |
| `00-raw-requirement.md` / `01-intake-brief.md` | Provenance only — never an execution authority |

**`02` baseline-vs-working-tree rule**: a predecessor task's legitimate repo change makes the working tree the operational truth; an unexplained or conflicting difference → `BLOCKED`.

**Ledger read-only rule**: only the controller flips checkboxes or appends `Resolved:`/`Gap:`/`Unresolved:`/`Minor:` records to `execution/progress.md`; subagents read but do not write to the ledger.

### Conflict Rule

No artifact silently overrides another outside its domain. If a task cannot satisfy all applicable authorities simultaneously, the subagent returns `BLOCKED`, names the conflicting files/IDs, and asks the human to **reopen** the owning stage — no guessing, no picking a winner, no patching around an upstream defect.

### Required Consumption

Each implementer, reviewer, and fix subagent must **read the full Authoritative Context Set before acting** — availability is not consumption. Subagents may skip the embedded `(read-only)` Upstream Summary / Project Context blocks within those files. On-demand depth applies only to the current codebase, git history, and prior task reports/reviews — never to whether to read an approved artifact. This rule is orthogonal to Model Selection: a cheap model on a mechanical task still reads the set.

### Ledger Ownership and Sibling Escalation

Default position/ownership derives from the ledger's `PLAN-TASK-NNN <title>` list (stay within the brief's Files/Steps; treat every other listed task ID as owned elsewhere). The full `07-plan.md` is not handed to subagents; whole-plan reasoning stays with the controller's Pre-flight read. An unclear sibling boundary → the subagent returns `NEEDS_CONTEXT` / `BLOCKED`; the controller resolves it or hands a specific `r2p-task-brief --task <M>` single-task brief and re-dispatches — never a whole-plan read or a guess from the title.

### Path Delivery and Fail-Closed Preflight

The controller derives `run_dir = parent(plan)` from the execute output and hands absolute paths by default, or repository-root-relative paths paired with an explicit `repo_root`. Each subagent runs a preflight before acting:
1. Input paths must already exist and be readable. For each role, inputs include the Authoritative Context Set paths, the task brief path, the ledger path, and any handed report/review/diff path the subagent is meant to consume.
2. Output paths do not need to exist at preflight. For each role, treat generated output paths as destination paths: implementer `execution/task-N-report.md`, task-reviewer `execution/task-N-review.md`, and final reviewer `execution/final-review-report.md`. Their parent directories must resolve under the same `run_dir` / `work_id` and be writable before the subagent writes.
3. Every handed path resolves under the same `run_dir` / `work_id`.
4. Any repo-root-relative path was resolved against the handed `repo_root`, not the process cwd.
5. If any input path is missing or unreadable, any output parent is missing or unwritable, or any path is unresolved or wired to a different run → `BLOCKED` — no silent continue on a partial/mixed set.

## Per-Task Loop

For each PLAN-TASK (in order):

### 1. Run `r2p-task-brief` and obtain the task-brief path

Run `{{R2P_BIN_DIR}}/r2p-task-brief --work-id <work-id> --task <N>` (where `<N>` is the task's integer, e.g. `2` for `PLAN-TASK-002`) for the current task. This installed wrapper delegates to the internal `plan-task-brief` CLI command. The command returns a `brief_path` pointing to a scoped brief file that contains the task's `Skeleton`, `Steps`, `Spec References`, and `Verification` criteria. Pass the `brief_path` as the handoff pointer to both the implementer and the reviewer — not pasted task text from `07-plan.md`. The controller uses the returned `brief_path` without eager-reading the full task body into its own context; the implementer and reviewer read the task-brief on demand.

### 2. Dispatch a fresh implementer subagent

Record BASE (`git rev-parse HEAD`) BEFORE dispatching the implementer — **never use `HEAD~1`** as BASE (it drops all but the last commit of a multi-commit task). For Task 1, this BASE is also `<execution-base-commit>` for the final whole-branch review. Persist the Task 1 BASE immediately in tracked execution state by adding `Execution BASE: <execution-base-commit>` to `execution/progress.md`.

Provide the subagent with:
- The `brief_path` returned by `r2p-task-brief` (not pasted task text from `07-plan.md`)
- **Read the Authoritative Context Set before acting**: the `02-project-context.md` entry supplies the project/dependency/architecture baseline deterministically
- Global Constraints from the PLAN (`## Global Constraints`), copied verbatim when present — the brief carries only the task body, so the implementer does not otherwise see plan-level constraints
- TDD instructions: follow `Skeleton`/`Steps`; prove `Verification` with evidence
- A report file path (`execution/task-N-report.md`)

The implementer return contract is minimal and inline:
- `status`: DONE / DONE_WITH_CONCERNS / NEEDS_CONTEXT / BLOCKED
- `report_path`: the report file path
- `commit_range`: `<base7>..<head7>` for committed task work, or `none` if no commit was created
- `test_summary`: one-line test summary, or `not run: <reason>`
- `concerns`: `none` or a concise list of decision-relevant concerns, missing context, or blockers

The controller uses these fields to decide whether to continue without opening the full report. The controller does not ask the implementer to restate the task.

The implementer must:
1. Implement exactly what the task specifies, following TDD
2. Satisfy the task's `Verification` criteria and attach evidence (test output, assertions)
3. Commit the work, staging only files intentionally changed for this PLAN-TASK
4. Self-review and report back

### 3. Handle implementer status

- **DONE / DONE_WITH_CONCERNS**: proceed to review
- **NEEDS_CONTEXT**: the implementer needs missing information — provide it and re-dispatch the fresh implementer subagent
- **BLOCKED**: assess the blocker; provide context, use a more capable model, or break the task into smaller pieces; escalate to the human if the plan itself is wrong

### 4. Ambiguity ladder

The fresh implementer subagent verifies-then-removes ambiguity by evidence and TDD. If it cannot resolve ambiguity:
- Return `NEEDS_CONTEXT` or `BLOCKED` and escalate to the human — never guess a vague implementation
- If the ambiguity is an upstream PLAN, SPEC, or DESIGN defect, stop and ask the human to choose an upstream repair path (for example, reopening from the affected stage) rather than patching over it in execution. Do not try to open a gap route from an `executing` run.

### 5. Write diff and dispatch task-reviewer

After the implementer reports DONE:
1. `mkdir -p .req-to-plan/<work-id>/logs` then `git diff -U10 <base-commit> HEAD > .req-to-plan/<work-id>/logs/task-N-diff.md`. Keep diff scratch under `logs/` (gitignored), never under `execution/`.
2. Dispatch a task-reviewer subagent with:
   - **Read the Authoritative Context Set before acting**: the reviewer checks `Spec References` IDs against the full `06-spec.md` text, not the IDs alone
   - The `brief_path` returned by `r2p-task-brief` (not pasted task text). The reviewer reads `Spec References` from the task brief. Do not pass separate `Spec References`.
   - The implementer report file path (`execution/task-N-report.md`)
   - The diff file path (`.req-to-plan/<work-id>/logs/task-N-diff.md`)
   - A review report file path (`execution/task-N-review.md`)
   - Global constraints from the plan (copy verbatim from `## Global Constraints`); never pre-judge a finding's severity; never paste prior-task summaries into a later dispatch

The task-reviewer writes detailed findings, if any, to `execution/task-N-review.md` and returns only this inline summary:
- `status`: APPROVED / CHANGES_REQUESTED / NEEDS_CONTEXT / BLOCKED
- `review_report_path`: the review report file path
- `test_summary`: one-line test summary, or `not run: <reason>`
- `concerns`: `none` or a concise list of decision-relevant concerns, missing context, or blockers

Surface in `concerns` every ⚠️ "cannot verify from diff" item and every unfixed Minor finding — do not leave them only in the report. This is how the controller learns there is something to adjudicate (§6) without opening the report on a clean task.

The review report records:
- **Spec compliance**: checked against the task brief's `Spec References` and `Verification`
- **Code quality**: clean, tested, maintainable
- **⚠️ DEFER items**: explicit `cannot verify from diff` warnings for requirements satisfied by unchanged code, by sibling task work, or by evidence outside the task diff

### 6. Fix loop

- Dispatch fix subagents for Critical and Important findings. Pass the `review_report_path` to the fix subagent with the instruction: Fix all Critical and Important findings in the review report. Do not paste the finding bodies into the dispatch. Also hand: **Read the Authoritative Context Set before acting**, the task brief path (`brief_path`), and the current task diff path (`logs/task-N-diff.md`).
- After each fix wave: the fix subagent commits only its intentionally-changed files (staging only files changed for this task, exactly as the §2 implementer does); then the loop regenerates `logs/task-N-diff.md` from the task's BASE to `HEAD` (`git diff -U10 <base-commit> HEAD > .req-to-plan/<work-id>/logs/task-N-diff.md`) — commit-then-diff — before re-dispatching the task-reviewer. The re-review must not run against an uncommitted working tree.
- Re-dispatch the task-reviewer after each fix wave with the refreshed diff path
- Before flipping the checkbox, adjudicate each reviewer "cannot verify from diff" warning. When `concerns` lists ⚠️ items, open `review_report_path` to adjudicate each; a `none`/empty `concerns` means no ⚠️ remains to adjudicate. Record one line per finding in `execution/progress.md`:
  - `Resolved: <finding>` — clears the warning; a `Resolved:` claim about unchanged code must cite implementation and test evidence
  - `Gap: <finding>` — blocks the flip and cannot be overridden on the controller's own judgment
  - `Unresolved: <finding>` — blocks the flip and cannot be overridden on the controller's own judgment
- Minor findings not fixed within a task: record each as `Minor: <finding>` in `execution/progress.md` and carry them into the final whole-branch review input rather than dropping them per task.
- Only when the task-reviewer is clean (both spec ✅ and quality Approved, and `Verification` satisfied, and no open `Gap:` or `Unresolved:` entries), update the matching `execution/progress.md` checkbox from `- [ ] PLAN-TASK-NNN ...` to `- [x] PLAN-TASK-NNN ...` and append one line:
  `Task N: complete (commits <base7>..<head7>, review clean)`

**Continuous execution**: execute all PLAN-TASKs without pausing to ask "should I continue?" between tasks. Stop only on: unresolvable `BLOCKED`, upstream defect requiring repair, dirty-tree block, or all tasks complete. `Verification` requires fresh command output; "should pass" / "looks correct" is not evidence; do not report `DONE` without it.

## Final Whole-Branch Review

After all tasks complete, dispatch a final whole-branch review subagent on the **most capable model**:
- First create the whole-branch diff: `mkdir -p .req-to-plan/<work-id>/logs` then `git diff -U10 <execution-base-commit> HEAD > .req-to-plan/<work-id>/logs/final-diff.md`
- Scope: review the complete execution range `git diff -U10 <execution-base-commit> HEAD`, where `<execution-base-commit>` is the Task 1 BASE captured before dispatching the first implementer
- Include the diff file path (`.req-to-plan/<work-id>/logs/final-diff.md`) in the reviewer dispatch; do not ask the reviewer to infer the changed range
- Provide a final review report path (`execution/final-review-report.md`) and require detailed findings there
- **re-run the full verification suite** on the final HEAD and attach the fresh output (per-task greens do not catch cross-task regressions)
- Walk the PLAN task-by-task as a line-by-line requirements checklist; report any gap
- Dispatch ONE fix subagent carrying the complete findings list by passing `execution/final-review-report.md`, not pasted findings (not one fixer per finding)
- This whole-branch review is the merge gate

After the review settles, write `execution/final-review.md` recording the reviewed range, a one-line summary, and the verdict:
- `Verdict: Approved` when the review is clean
- `Verdict: Changes Requested` while findings remain
- After any final-review fix wave, regenerate `.req-to-plan/<work-id>/logs/final-diff.md` from the same `<execution-base-commit>` to current `HEAD`, re-run the full verification suite, and re-dispatch the final whole-branch reviewer with the refreshed diff and output
- Repeat until the post-fix reviewer is clean; only then append `Verdict: Approved` as the final unfenced verdict (the gate reads the last one)

Note: `r2p-archive` refuses to archive an executing run unless this file's current verdict is `Verdict: Approved`.

## Auto-Archive on Completion

When all tasks are done and the final whole-branch review is clean, call:

```
{{R2P_BIN_DIR}}/r2p-archive --work-id <work_id from the precondition output>
```

Archiving is gated: `r2p-archive` refuses unless every PLAN-TASK from the PLAN is checked off (`- [x]`) in the ledger. Add `--force` only to archive an abandoned or superseded run.

Commits are already on the **current branch**. `push` and PR creation still require an explicit user request.

## Durable Progress

Track progress in `execution/progress.md` (not only in todos). On resume, read the ledger and skip tasks already marked complete.
On resume, read `execution/progress.md` before the final review and reuse its `Execution BASE:` line as `<execution-base-commit>`. Do not recalculate it from `HEAD` or from the latest task range. If the line is missing, stop and ask the human for the original Task 1 BASE instead of inferring a range.

## Error Reference

| Condition | Action |
|---|---|
| Status not `closed_at_plan_checkpoint` or `executing` | Stop: `plan_not_ready` |
| Implementer returns `NEEDS_CONTEXT` | Provide missing context, re-dispatch fresh implementer subagent |
| Upstream PLAN/SPEC/DESIGN defect found | Stop: ask the human to reopen/repair the upstream stage |
| Platform lacks subagent capability | Fail explicitly (subagents are a hard prerequisite) |

Use `r2p-status` to inspect progress without making changes.

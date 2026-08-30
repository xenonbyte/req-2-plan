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

`execution/progress.md` remains the only execution-state ledger. When a normal
start succeeds it also creates controller-owned `execution/metrics.md`; that
metrics ledger is non-authoritative and never replaces progress, completion, or
archive gates. The controller records one ordered role block after every
implementer, reviewer, fixer, re-reviewer, and final-role call. Record only
measured values: unavailable model, timing, or Token values stay `unavailable`;
do not estimate Token counts from bytes or elapsed time.

### Structured metrics protocol

The controller never hand-edits `execution/metrics.md` and never emits ad-hoc
`## Role` prose. At start and on every resume, call
`{{R2P_BIN_DIR}}/r2p-metrics-status --work-id <id>` and retain only
`next_sequence` plus `metrics_finalized`. Before dispatching each role, capture
its measured UTC start and monotonic start. After the role returns and its
compact report exists, capture the measured end/duration, map the role result to
the canonical status, and call
`{{R2P_BIN_DIR}}/r2p-metrics-append --work-id <id> --record-json '<json>'`
before dispatching another role or advancing a progress checkbox. The JSON
record carries `expected_sequence`, role/task/model/times, context mode/bytes,
ordered verification records, report path, status, concerns, fix wave, and only
platform-measured Token values. The CLI derives the heading, byte kind,
verification total, and report bytes.

Canonical status mapping is exact: implementer/fixer/final-fixer DONE or
DONE_WITH_CONCERNS maps to `complete`; task/final reviewer APPROVED maps to
`approved`; CHANGES_REQUESTED maps to `changes_requested`; NEEDS_CONTEXT or
BLOCKED maps to `blocked`. A blocked append is terminal for a validator-eligible
strict metrics sequence: stop the execution loop and surface the blocker rather
than dispatching a later role that the CLI must reject.

On retry or resume, call status first and reuse the exact same record and
`expected_sequence`; accept `already_applied`, never count headings or invent a
new sequence. A busy/conflict result is retried only with that exact request.
After the appended final reviewer or final re-reviewer is approved and the last
unfenced final verdict is `Verdict: Approved`, call
`{{R2P_BIN_DIR}}/r2p-metrics-finalize --work-id <id> --expected-invocation-count <N>`.
The CLI alone derives `change_shape` and atomically closes finalization. Surface
any metrics command failure as `metrics_incomplete`; do not rewrite progress or
final-review truth. Metrics remain non-authoritative, so this does not add a new
archive gate and the unchanged `r2p-archive` flow follows finalization.

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

## Semantic Context View

Each subagent consumes the Authoritative Context Set by running
`{{R2P_BIN_DIR}}/r2p-context-view --work-id <id>` itself before acting. The
wrapper reads the six approved sources and progress safely, strips
non-semantic Markdown, and returns the live semantic view; the controller must not read or forward the semantic content. Record this role input as
`context_mode=semantic_view` and
`context_bytes_kind=semantic_payload_bytes`, using the view's aggregate
`semantic_bytes`. The controller may retain only that byte count and the bounded
inline return fields.

No persistent context artifact, `task-N-context.md`, context bundle, manifest,
hash, or drift gate is created. `07-plan.md`, `00-raw-requirement.md`, and
`01-intake-brief.md` remain outside the per-task semantic view.

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

Each implementer, reviewer, fixer, re-reviewer, and final reviewer must run
`{{R2P_BIN_DIR}}/r2p-context-view --work-id <id>` itself before acting —
availability is not consumption. The controller supplies the command and does
not relay its output. On-demand depth applies only to the current codebase, git
history, and prior task reports/reviews.

### Ledger Ownership and Sibling Escalation

Default position/ownership derives from the ledger's `PLAN-TASK-NNN <title>` list (stay within the brief's Files/Steps; treat every other listed task ID as owned elsewhere). The full `07-plan.md` is not handed to subagents; whole-plan reasoning stays with the controller's Pre-flight read. Resolve an unclear sibling boundary before dispatch, optionally by handing a specific `r2p-task-brief --task <M>` brief. If a dispatched role still returns `NEEDS_CONTEXT` / `BLOCKED`, append its terminal blocked record and stop — never re-dispatch, hand over the whole PLAN, or guess from the title.

### Path Delivery and Fail-Closed Preflight

The controller derives `run_dir = parent(plan)` from the execute output and hands absolute paths by default, or repository-root-relative paths paired with an explicit `repo_root`. Each subagent runs a preflight before acting:
1. Input paths must already exist and be readable. For each role, inputs include the role-side context-view command, the task brief path, the ledger path, and any handed report/review/diff path the subagent is meant to consume.
2. Output paths do not need to exist at preflight. For each role, treat generated output paths as destination paths: implementer `execution/task-N-report.md`, task-reviewer `execution/task-N-review.md`, and final reviewer `execution/final-review-report.md`. Their parent directories must resolve under the same `run_dir` / `work_id` and be writable before the subagent writes.
3. Every handed path resolves under the same `run_dir` / `work_id`.
4. Any repo-root-relative path was resolved against the handed `repo_root`, not the process cwd.
5. If any input path is missing or unreadable, any output parent is missing or unwritable, or any path is unresolved or wired to a different run → `BLOCKED` — no silent continue on a partial/mixed set.

## Per-Task Loop

For each PLAN-TASK (in order):

### Role dispatch and verification cadence

Every role call is a brand-new zero-history subagent invocation. Codex dispatch
must set `fork_turns="none"`; if that isolation cannot be guaranteed, fail
explicitly before dispatch. Never continue or reawaken a previous implementer,
reviewer, fixer, re-reviewer, or final-review session. The handoff is
self-contained: work ID/run dir, role, task brief or final input paths,
Git/BASE boundary, verification contract, report path, and inline return
contract — never semantic-view content, prior role prose, or controller summaries.

Implementers, task reviewers, fixers, and task re-reviewers default to the
current task's targeted or directly affected tests. Escalate that task-level
role to the full suite only when the PLAN explicitly requires it, the task is
shared/core/high-risk (including security or migration), targeted verification
fails, changed files exceed the brief without a safe explanation, coverage is
unclear, or the reviewer cannot establish sufficient confidence. Each escalation
records `scope=full_suite` and a concrete reason in `Verification Records` and
the controller's metrics block. Final reviewers and final re-reviewers always
run a fresh full suite.

### 1. Run `r2p-task-brief` and obtain the task-brief path

Run `{{R2P_BIN_DIR}}/r2p-task-brief --work-id <work-id> --task <N>` (where `<N>` is the task's integer, e.g. `2` for `PLAN-TASK-002`) for the current task. This installed wrapper delegates to the internal `plan-task-brief` CLI command. The command returns a `brief_path` pointing to a scoped brief file that contains the task's `Files`, `Skeleton`, `Steps`, `Spec References`, and `Verification` criteria. Pass the `brief_path` as the handoff pointer to both the implementer and the reviewer — not pasted task text from `07-plan.md`. The controller uses the returned `brief_path` without eager-reading the full task body into its own context; the implementer and reviewer read the task-brief on demand.

### 2. Dispatch a fresh implementer subagent

**Per-task boundary clean-tree invariant**: before dispatching this task's implementer, run `git status --short -- ':!.req-to-plan'`; a non-clean code tree at a task boundary is a boundary-invariant violation (the previous task or fix wave left uncommitted work): stop and resolve before continuing. This per-task check is distinct from the Task 1 check in `## In-Place Execution`, which additionally negotiates pre-existing user dirty work.

Record BASE (`git rev-parse HEAD`) BEFORE dispatching the implementer — **never use `HEAD~1`** as BASE (it drops all but the last commit of a multi-commit task). For Task 1, this BASE is also `<execution-base-commit>` for the final whole-branch review. Persist the Task 1 BASE immediately in tracked execution state by adding `Execution BASE: <execution-base-commit>` to `execution/progress.md`.

Provide the subagent with:
- The `brief_path` returned by `r2p-task-brief` (not pasted task text from `07-plan.md`)
- **Run `{{R2P_BIN_DIR}}/r2p-context-view --work-id <id>` yourself before acting**; consume its live semantic output and report `semantic_view` / `semantic_payload_bytes` to the controller without relaying the content
- Global Constraints from the PLAN (`## Global Constraints`), copied verbatim when present — the brief carries only the task body, so the implementer does not otherwise see plan-level constraints
- TDD instructions: follow `Skeleton`/`Steps`; prove `Verification` with evidence
- A report file path (`execution/task-N-report.md`)
  The implementer's compact `execution/task-N-report.md` must contain exactly these audit sections: `Status`, `Commit Range`, `Changed Files`, `Verification Records`, `Concerns`, and `⚠️ DEFER`. Write `none` for absent concerns/defer items; preserve every actual concern and every `⚠️ DEFER` item in both the persistent section and inline `concerns`. `Verification Records` lists ordered command, scope, reason, elapsed_seconds, and status. `Changed Files` feeds the §5 reviewer comparison. Do not add a self-attested "Context Read" checklist. Return the same compact `verification_records` plus `verification_total_seconds` inline so the controller can record measured evidence.

The implementer return contract is minimal and inline:
- `status`: DONE / DONE_WITH_CONCERNS / NEEDS_CONTEXT / BLOCKED
- `report_path`: the report file path
- `commit_range`: `<base7>..<head7>` for committed task work, or `none` if no commit was created
- `test_summary`: one-line test summary, or `not run: <reason>`
- `concerns`: `none` or a concise list of decision-relevant concerns, missing context, or blockers
- `verification_records` and `verification_total_seconds`: measured verification evidence

The controller uses these fields to decide whether to continue without opening the full report. The controller does not ask the implementer to restate the task.

The implementer must:
1. Implement exactly what the task specifies, following TDD
2. Satisfy the task's `Verification` criteria and attach evidence (test output, assertions)
3. Commit the work, staging only files intentionally changed for this PLAN-TASK
4. Self-review and report back

### 3. Handle implementer status

- **DONE / DONE_WITH_CONCERNS**: proceed to review
- **NEEDS_CONTEXT**: append the terminal blocked metrics record, stop, and surface the missing information
- **BLOCKED**: assess the blocker; provide context, use a more capable model, or break the task into smaller pieces; escalate to the human if the plan itself is wrong

### 4. Ambiguity ladder

The fresh implementer subagent verifies-then-removes ambiguity by evidence and TDD. If it cannot resolve ambiguity:
- Return `NEEDS_CONTEXT` or `BLOCKED` and escalate to the human — never guess a vague implementation
- If the ambiguity is an upstream PLAN, SPEC, or DESIGN defect, stop and ask the human to choose an upstream repair path (for example, reopening from the affected stage) rather than patching over it in execution. Do not try to open a gap route from an `executing` run.

### 5. Write diff and dispatch task-reviewer

After the implementer reports DONE:
1. `mkdir -p .req-to-plan/<work-id>/logs` then `git diff -U10 <base-commit> HEAD > .req-to-plan/<work-id>/logs/task-N-diff.md`. Keep diff scratch under `logs/` (gitignored), never under `execution/`.
2. Dispatch a task-reviewer subagent with:
   - **Run `{{R2P_BIN_DIR}}/r2p-context-view --work-id <id>` yourself before acting**: the reviewer checks `Spec References` IDs against the live semantic spec, not the IDs alone
   - The `brief_path` returned by `r2p-task-brief` (not pasted task text). The reviewer reads `Spec References` from the task brief. Do not pass separate `Spec References`.
   - The implementer report file path (`execution/task-N-report.md`)
   - The diff file path (`.req-to-plan/<work-id>/logs/task-N-diff.md`)
   - A review report file path (`execution/task-N-review.md`)
   - Global constraints from the plan (copy verbatim from `## Global Constraints`); never pre-judge a finding's severity; never paste prior-task summaries into a later dispatch
   - Compare the files actually changed in the task diff against the brief's `Files` list; a file changed outside that list requires an explicit, recorded justification, or the review returns `CHANGES_REQUESTED`. (Reviewer-protocol only — no CLI diff parsing or hard gate.)

The task-reviewer writes detailed findings, if any, to `execution/task-N-review.md` and returns only this inline summary:
- `status`: APPROVED / CHANGES_REQUESTED / NEEDS_CONTEXT / BLOCKED
- `review_report_path`: the review report file path
- `test_summary`: one-line test summary, or `not run: <reason>`
- `concerns`: `none` or a concise list of decision-relevant concerns, missing context, or blockers

Surface in `concerns` every ⚠️ "cannot verify from diff" item and every unfixed Minor finding — do not leave them only in the report. This is how the controller learns there is something to adjudicate (§6) without opening the report on a clean task.

The compact review report contains `Status`, `Commit Range`, `Changed Files`, `Verification Records`, `Concerns`, `⚠️ DEFER`, `Spec Verdict`, and `Quality Verdict`. `Spec Verdict` checks the task brief's `Spec References` and `Verification`; `Quality Verdict` records whether the code is clean, tested, and maintainable. `Verification Records` retains ordered command, scope, reason, elapsed_seconds, and status evidence. Every `⚠️ DEFER` item is an explicit `cannot verify from diff` warning for a requirement satisfied by unchanged code, sibling task work, or evidence outside the diff, and must also appear inline in `concerns`.

### 6. Fix loop

- Dispatch fix subagents for Critical and Important findings. Pass the `review_report_path` to the fix subagent with the instruction: Fix all Critical and Important findings in the review report. Do not paste the finding bodies into the dispatch. Also hand: **Run `{{R2P_BIN_DIR}}/r2p-context-view --work-id <id>` yourself before acting**, the task brief path (`brief_path`), and the current task diff path (`logs/task-N-diff.md`).
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
- **Run `{{R2P_BIN_DIR}}/r2p-context-view --work-id <id>` yourself before acting**: consume the semantic view plus `07-plan.md`, every `execution/task-N-report.md`, every `execution/task-N-review.md`, and every `Minor:` ledger entry. Strict final review reads reports and reviews; fast primary final review reads every report but does not require nonexistent task-review files. Note: the final reviewer is the one role that reads `07-plan.md`; the per-task semantic-view exclusion of `07-plan.md` does not apply to this section.
- First create the whole-branch diff: `mkdir -p .req-to-plan/<work-id>/logs` then `git diff -U10 <execution-base-commit> HEAD > .req-to-plan/<work-id>/logs/final-diff.md`
- Scope: review the complete execution range `git diff -U10 <execution-base-commit> HEAD`, where `<execution-base-commit>` is the Task 1 BASE captured before dispatching the first implementer
- Include the diff file path (`.req-to-plan/<work-id>/logs/final-diff.md`) in the reviewer dispatch; do not ask the reviewer to infer the changed range
- Provide a final review report path (`execution/final-review-report.md`) and require compact `Status`, `Commit Range`, `Changed Files`, `Verification Records`, `Concerns`, and `⚠️ DEFER` sections there; preserve every concern/defer item inline as well
- **re-run the full verification suite** on the final HEAD and attach the fresh output (per-task greens do not catch cross-task regressions)
- Write the final review's ordered `Verification Records` and compact inline `verification_records` / `verification_total_seconds`; the controller records that final-role metrics block just as it does every other role.
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

**Mid-task interruption recovery**: on resume, the in-progress task is the lowest-numbered unchecked (`- [ ]`) task; reconstruct the in-progress task's BASE from existing on-disk markers: Task 1 uses the ledger `Execution BASE:` line; Task N (N > 1) uses the `head7` of the immediately preceding `Task N-1: complete (commits <base7>..<head7>, review clean)` line. Then regenerate `logs/task-N-diff.md` from that BASE to HEAD and re-dispatch the task-reviewer idempotently — an already-committed, correct task is approved as-is; re-dispatch the implementer only if the review finds a gap. If neither marker can be resolved, stop and ask the human for the BASE. Never infer a range from `HEAD~1`; never capture a fresh BASE from HEAD on resume.

## Error Reference

| Condition | Action |
|---|---|
| Status not `closed_at_plan_checkpoint` or `executing` | Stop: `plan_not_ready` |
| Implementer returns `NEEDS_CONTEXT` | Append the terminal blocked metrics record, stop, and surface the missing information |
| Upstream PLAN/SPEC/DESIGN defect found | Stop: ask the human to reopen/repair the upstream stage |
| Platform lacks subagent capability | Fail explicitly (subagents are a hard prerequisite) |

Use `r2p-status` to inspect progress without making changes.

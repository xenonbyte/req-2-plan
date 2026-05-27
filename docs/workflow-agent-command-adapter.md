# Workflow Agent Command Adapter

## Purpose

This document defines the small project-level agent shortcut surface for operating the requirement-to-PLAN workflow in this repository.

It is a carrier adapter. It does not replace `workflow-command-surface.md` or `workflow-cli-adapter.md`. It gives agents a compact command set while preserving the internal `CMD-*` safety rules.

## Scope

This document covers:

- The five public project shortcut commands.
- Active run and workspace pointer semantics.
- Automatic `work-id` generation.
- Multi-run start and switch behavior.
- Mapping from project shortcut commands to existing workflow command intents or post-PLAN adapter rules.

This document does not cover:

- New `CMD-*` command intents.
- Concrete CLI implementation details.
- Stage artifact templates.
- Implementation execution after PLAN adaptation.
- Executor-specific behavior beyond invoking the post-PLAN adapter.

## Carrier Namespace Boundary

Commands in this document are project-level agent shortcuts, not the concrete CLI namespace.

The concrete CLI carrier remains:

```text
workflow <group> <action> [flags]
```

The public shortcut prefix for this repository is:

```text
coyeme-workflow-*
```

If a CLI implementation exposes these shortcuts, the wrapper or alias must first be defined in `workflow-cli-adapter.md`. This document does not reserve a CLI group or command name for project shortcuts.

Examples in this document describe the project shortcut interaction surface, not required binary syntax for the concrete CLI.

## Run Selection Model

### Terminal Run

A requirement-to-PLAN run is terminal when its `run.md` status is:

```text
closed_at_plan_checkpoint
```

This means PLAN is approved, no open route remains, final approved references are not stale, and the run is complete for the requirement-to-PLAN workflow.

### Open Run

An open run is any run whose `run.md` status is not terminal.

Examples:

```text
active_stage_draft
entry_gate_failed
quality_gate_failed
ready_for_checkpoint_review
checkpoint_review
checkpoint_changes_requested
upstream_gap_routing
checkpoint_approved
next_stage
```

An open run is still in progress even when a checkpoint has been approved but `close_workflow_run` has not recorded `closed_at_plan_checkpoint`.

### Workspace Active Pointer

The workspace active pointer records the selected run for project shortcut commands.

Default pointer path:

```text
docs/artifacts/.workflow-active
```

Pointer shape:

```text
selected_work_id: WF-20260525-login-rate-limit
selected_run: docs/artifacts/WF-20260525-login-rate-limit/run.md
updated_at: 2026-05-25T12:00:00+08:00
reason: workflow_start
```

The pointer may select an open or terminal run. A selected open run is the active run. A selected terminal run is not active for `coyeme-workflow-continue`.

An unselected open run is a competing open run. It blocks implicit `coyeme-workflow-start` without `--separate`, but it is not the active run until `coyeme-workflow-switch --work-id <id>` selects it.

If the pointer is missing and exactly one open run exists, `coyeme-workflow-continue` may recover the pointer to that run before resuming. If multiple open runs exist, `coyeme-workflow-continue` must stop with `active_run_ambiguous` and require `coyeme-workflow-switch --work-id <id>`.

## Work ID Rule

`work-id` is a stable workflow run ID, not the requirement title.

Agents must generate `work-id` automatically when `coyeme-workflow-start` creates a run. Users do not normally provide it.

Recommended format:

```text
WF-YYYYMMDD-short-slug
```

Rules:

- Use ASCII lowercase letters, numbers, and hyphens after the `WF-` prefix.
- Generate the slug from the raw requirement summary, but do not change the `work-id` if the requirement title later changes.
- Keep the ID short enough for paths, preferably 48 characters or less.
- If the generated ID already exists, append a stable suffix such as `-2` or a short hash.
- Store artifacts under `docs/artifacts/<work-id>/`.

Only `coyeme-workflow-switch` accepts an explicit `--work-id`. `coyeme-workflow-start` creates a new `work-id` internally.

## Public Project Shortcuts

The public command set is intentionally small:

```text
coyeme-workflow-start [--separate] "<raw requirement>"
coyeme-workflow-continue
coyeme-workflow-status [--all]
coyeme-workflow-switch --work-id <id>
```

Project shortcuts may compose internal `CMD-*` command intents, but they must preserve all authority, confirmation, stop, and state-eligibility rules in `workflow-command-surface.md`.

## Command Semantics

### `coyeme-workflow-start [--separate] "<raw requirement>"`

Starts a workflow run from a raw requirement.

Behavior:

- Reads `docs/artifacts/.workflow-active` when present and scans `docs/artifacts/*/run.md` for open runs.
- Without `--separate`, stops with `active_run_exists` when the selected run is open.
- Without `--separate`, stops with `open_run_exists` when exactly one unselected open run exists.
- Without `--separate`, stops with `open_runs_exist` when multiple open runs exist and no selected open run owns the next action.
- With `--separate`, creates an independent new run even when another open run exists.
- Generates a new `work-id` internally.
- Creates `docs/artifacts/<work-id>/`, `run.md`, and initial raw requirement artifact.
- Updates `docs/artifacts/.workflow-active` to the new run.
- Maps to `CMD-RUN-START`.

Forbidden:

- Do not accept `--work-id`.
- Do not overwrite an existing run.
- Do not silently merge the new requirement into an existing open run.
- Do not continue an existing run; use `coyeme-workflow-continue`.

Common stops:

Selected open run:

```text
blocked: active_run_exists
next: coyeme-workflow-continue
alternative: coyeme-workflow-start --separate "<raw requirement>"
```

Single unselected open run:

```text
blocked: open_run_exists
open_run: docs/artifacts/<work-id>/run.md
next: coyeme-workflow-switch --work-id <work-id>
alternative: coyeme-workflow-start --separate "<raw requirement>"
```

Multiple open runs:

```text
blocked: open_runs_exist
next: coyeme-workflow-status --all
then: coyeme-workflow-switch --work-id <work-id>
alternative: coyeme-workflow-start --separate "<raw requirement>"
```

### `coyeme-workflow-continue`

Continues the selected active run.

Behavior:

- Reads `docs/artifacts/.workflow-active`.
- Loads `run.md`, active artifact, `Resume Context`, open routes, and stale/superseded markers.
- If the selected run is open, inspects the next allowed operation.
- May compose only safe unambiguous operations that do not create semantic stage content, grant approval, choose route ownership, or invent confirmation evidence.
- In the local concrete wrapper, safe composition is intentionally narrow: it delegates `run resume` and `run close` when those are the next valid operation, and otherwise prints the next internal `workflow ...` command for the operator or agent to run explicitly.
- May close only by composing `CMD-RUN-CLOSE` after an approved PLAN Checkpoint, no open route, and no stale or superseded final references.
- Stops whenever user confirmation, checkpoint approval, route ownership, upstream repair, ambiguous state, or stale input is required.

If the selected run is terminal:

```text
blocked: run_already_closed
alternative: coyeme-workflow-switch --work-id <open-run-id>
```

Forbidden:

- Do not accept `--work-id`.
- Do not synthesize Requirement Brief, Risk Discovery, DESIGN, SPEC, or PLAN content.
- Do not mark an artifact `ready`; stage authorship and Quality Gate evidence must be explicit.
- Do not approve a checkpoint without required user confirmation.
- Do not bypass Quality Gates or checkpoint reviews.
- Do not write route records into a closed source run.
- Do not run implementation execution.

### `coyeme-workflow-status [--all]`

Shows workflow status without writing artifacts or moving the pointer.

Behavior:

- Without `--all`, reports the selected run, whether it is open or terminal, current stage, next safe command, open routes, stale artifacts, and checkpoint status.
- Without `--all`, if no pointer exists, returns `no_selected_run`, performs no pointer recovery, and recommends `coyeme-workflow-status --all`.
- Without `--all`, if no pointer exists and exactly one open run exists, may also report `recoverable_open_run: docs/artifacts/<work-id>/run.md`; it still must not write the pointer.
- With `--all`, scans `docs/artifacts/*/run.md` and lists known runs, marking the selected run, open runs, terminal runs, and inconsistent runs.

Forbidden:

- Do not write `run.md`.
- Do not update `docs/artifacts/.workflow-active`.
- Do not infer a run repair.

### `coyeme-workflow-switch --work-id <id>`

Switches the workspace active pointer to an existing run.

Behavior:

- Resolves `docs/artifacts/<work-id>/run.md`.
- Verifies the run exists and contains the same work ID.
- Updates `docs/artifacts/.workflow-active`.
- Does not modify the selected run's artifacts.
- Does not advance workflow state.

This is the only public project shortcut that accepts `--work-id`.

Forbidden:

- Do not create a run.
- Do not resume, approve, route, adapt, or execute work.
- Do not switch to a missing or inconsistent run.

## Start / Switch Examples

No existing open run:

```text
coyeme-workflow-start "Add login rate limiting for password attempts"
```

Result:

```text
created: docs/artifacts/WF-20260525-login-rate-limiting/run.md
selected_run: docs/artifacts/WF-20260525-login-rate-limiting/run.md
next: coyeme-workflow-continue
```

Selected open run:

```text
coyeme-workflow-start "Add billing export"
```

Result:

```text
blocked: active_run_exists
active_run: docs/artifacts/WF-20260525-login-rate-limiting/run.md
next: coyeme-workflow-continue
alternative: coyeme-workflow-start --separate "Add billing export"
```

Unselected open run:

```text
coyeme-workflow-start "Add billing export"
```

Result:

```text
blocked: open_run_exists
open_run: docs/artifacts/WF-20260525-login-rate-limiting/run.md
next: coyeme-workflow-switch --work-id WF-20260525-login-rate-limiting
alternative: coyeme-workflow-start --separate "Add billing export"
```

Independent new requirement:

```text
coyeme-workflow-start --separate "Add billing export"
```

Result:

```text
created: docs/artifacts/WF-20260525-billing-export/run.md
selected_run: docs/artifacts/WF-20260525-billing-export/run.md
next: coyeme-workflow-continue
```

Switch back:

```text
coyeme-workflow-switch --work-id WF-20260525-login-rate-limiting
```

Result:

```text
selected_run: docs/artifacts/WF-20260525-login-rate-limiting/run.md
next: coyeme-workflow-continue
```

## Internal Mapping

| Project shortcut | Internal authority |
|---|---|
| `coyeme-workflow-start` | `CMD-RUN-START` plus active pointer update. |
| `coyeme-workflow-continue` | Stateful macro over allowed `CMD-*` intents according to run state and stop rules. |
| `coyeme-workflow-status` | `CMD-STATUS-*`; read-only. |
| `coyeme-workflow-switch` | Active pointer update only; no stage command intent. |

## Safety Rules

- Public project shortcuts must not expose internal `CMD-*` names as user-required commands.
- `coyeme-workflow-continue` must stop instead of guessing when state, route, confirmation, or source freshness is ambiguous.
- Do not suggest `coyeme-workflow-continue` for an unselected open run; switch to that `work-id` first.
- Only `coyeme-workflow-switch` accepts `--work-id`.
- `coyeme-workflow-start --separate` is the explicit signal to create a second open run.
- A terminal run remains available for status and switch, but it is not active for `coyeme-workflow-continue`.

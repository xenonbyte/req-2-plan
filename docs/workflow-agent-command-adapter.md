# Workflow Agent Command Adapter

## Purpose

This document defines the small project-level agent shortcut surface for operating the requirement-to-PLAN workflow in this repository.

It is a carrier adapter. It does not replace `workflow-command-surface.md` or `workflow-cli-adapter.md`. It gives agents a compact command set while preserving the internal `CMD-*` safety rules.

The dashed shortcuts in this document (`r2p-*`) are daily session shortcuts that operate on an existing workflow run. They are distinct from the lifecycle binary `r2p <subcommand>` (`r2p install`, `r2p uninstall`, `r2p installed`, `r2p doctor`, `r2p version`), which manages agent integration on the host. The lifecycle binary is documented in `workflow-install-surface.md` and is invoked without a hyphen between `r2p` and the subcommand.

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
r2p-*
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
.req-to-plan/.workflow-active
```

Pointer shape:

```text
selected_work_id: WF-20260525-login-rate-limit
selected_run: .req-to-plan/WF-20260525-login-rate-limit/run.md
updated_at: 2026-05-25T12:00:00+08:00
reason: workflow_start
```

The pointer may select an open or terminal run. A selected open run is the active run. A selected terminal run is not active for `r2p-continue`.

An unselected open run is a competing open run. It blocks implicit `r2p-start` without `--separate`, but it is not the active run until `r2p-switch --work-id <id>` selects it.

If the pointer is missing and exactly one open run exists, `r2p-continue` may recover the pointer to that run before resuming. If multiple open runs exist, `r2p-continue` must stop with `active_run_ambiguous` and require `r2p-switch --work-id <id>`.

## Work ID Rule

`work-id` is a stable workflow run ID, not the requirement title.

Agents must generate `work-id` automatically when `r2p-start` creates a run. Users do not normally provide it.

Recommended format:

```text
WF-YYYYMMDD-short-slug
```

Rules:

- Use ASCII lowercase letters, numbers, and hyphens after the `WF-` prefix.
- Generate the slug from the raw requirement summary, but do not change the `work-id` if the requirement title later changes.
- Keep the ID short enough for paths, preferably 48 characters or less.
- If the generated ID already exists, append a stable suffix such as `-2` or a short hash.
- Store artifacts under `.req-to-plan/<work-id>/`.

Only `r2p-switch` accepts an explicit `--work-id`. `r2p-start` creates a new `work-id` internally.

## Public Project Shortcuts

The public command set is intentionally small:

```text
r2p-start [--separate] "<raw requirement>"
r2p-continue
r2p-status [--all]
r2p-switch --work-id <id>
r2p-reopen --from <work-id> --stage <stage> --reason "<short>"
```

`r2p-reopen` maps to `CMD-RUN-REOPEN` and creates a new lineage run from a closed source run; it does not modify the source run.

Project shortcuts compose internal `CMD-*` command intents, but they must preserve all authority, confirmation, stop, and state-eligibility rules in `workflow-command-surface.md`.

## Command Semantics

### `r2p-start [--separate] "<raw requirement>"`

Starts a workflow run from a raw requirement.

Behavior:

- Reads `.req-to-plan/.workflow-active` when present and scans `.req-to-plan/*/run.md` for open runs.
- Without `--separate`, stops with `active_run_exists` when the selected run is open.
- Without `--separate`, stops with `open_run_exists` when exactly one unselected open run exists.
- Without `--separate`, stops with `open_runs_exist` when multiple open runs exist and no selected open run owns the next action.
- With `--separate`, creates an independent new run even when another open run exists.
- Generates a new `work-id` internally.
- Creates `.req-to-plan/<work-id>/`, `run.md`, and initial raw requirement artifact.
- Updates `.req-to-plan/.workflow-active` to the new run.
- Maps to `CMD-RUN-START`.

Forbidden:

- Do not accept `--work-id`.
- Do not overwrite an existing run.
- Do not silently merge the new requirement into an existing open run.
- Do not continue an existing run; use `r2p-continue`.

Common stops:

Selected open run:

```text
blocked: active_run_exists
next: r2p-continue
alternative: r2p-start --separate "<raw requirement>"
```

Single unselected open run:

```text
blocked: open_run_exists
open_run: .req-to-plan/<work-id>/run.md
next: r2p-switch --work-id <work-id>
alternative: r2p-start --separate "<raw requirement>"
```

Multiple open runs:

```text
blocked: open_runs_exist
next: r2p-status --all
then: r2p-switch --work-id <work-id>
alternative: r2p-start --separate "<raw requirement>"
```

### `r2p-continue`

Continues the selected active run.

Behavior:

- Reads `.req-to-plan/.workflow-active`.
- Loads `run.md`, active artifact, `Resume Context`, open routes, and stale/superseded markers.
- If the selected run is open, inspects the next allowed operation.
- May compose only safe unambiguous operations that do not create semantic stage content, grant approval, choose route ownership, or invent confirmation evidence.
- In the local concrete wrapper, safe composition is intentionally narrow: it delegates `run resume` and `run close` when those are the next valid operation, and otherwise prints the next internal `workflow ...` command for the operator or agent to run explicitly.
- May close only by composing `CMD-RUN-CLOSE` after an approved PLAN Checkpoint, no open route, and no stale or superseded final references.
- Stops whenever user confirmation, checkpoint approval, route ownership, upstream repair, ambiguous state, or stale input is required.
- When the tier is unlocked, surfaces `workflow tier-lock` as the next required command instead of advancing the stage.
- When Risk Discovery or DESIGN has surfaced modifier candidates that are not yet recorded in the locked tier, surfaces `workflow tier-escalate` with the candidate modifier and reason.

If the selected run is terminal:

```text
blocked: run_already_closed
alternative: r2p-switch --work-id <open-run-id>
```

Forbidden:

- Do not accept `--work-id`.
- Do not synthesize Requirement Brief, Risk Discovery, DESIGN, SPEC, or PLAN content.
- Do not mark an artifact `ready`; stage authorship and Quality Gate evidence must be explicit.
- Do not approve a checkpoint without required user confirmation.
- Do not bypass Quality Gates or checkpoint reviews.
- Do not write route records into a closed source run.
- Do not run implementation execution.

### `r2p-status [--all]`

Shows workflow status without writing artifacts or moving the pointer.

Behavior:

- Without `--all`, reports the selected run, whether it is open or terminal, current stage, next safe command, open routes, stale artifacts, and checkpoint status.
- Without `--all`, if no pointer exists, returns `no_selected_run`, performs no pointer recovery, and recommends `r2p-status --all`.
- Without `--all`, if no pointer exists and exactly one open run exists, may also report `recoverable_open_run: .req-to-plan/<work-id>/run.md`; it still must not write the pointer.
- With `--all`, scans `.req-to-plan/*/run.md` and lists known runs, marking the selected run, open runs, terminal runs, and inconsistent runs.

Forbidden:

- Do not write `run.md`.
- Do not update `.req-to-plan/.workflow-active`.
- Do not infer a run repair.

### `r2p-switch --work-id <id>`

Switches the workspace active pointer to an existing run.

Behavior:

- Resolves `.req-to-plan/<work-id>/run.md`.
- Verifies the run exists and contains the same work ID.
- Updates `.req-to-plan/.workflow-active`.
- Does not modify the selected run's artifacts.
- Does not advance workflow state.

This is the only public project shortcut that accepts `--work-id`.

Forbidden:

- Do not create a run.
- Do not resume, approve, route, or execute work.
- Do not switch to a missing or inconsistent run.

### `r2p-reopen --from <work-id> --stage <stage> --reason "<short>"`

Creates a new lineage run from a closed source run, starting at a specified stage.

Behavior:

- Resolves the source `.req-to-plan/<work-id>/run.md` and confirms it is `closed_at_plan_checkpoint`.
- Computes the next reopen ordinal `N` for the source and creates `.req-to-plan/<work-id>-rN/`.
- Copies the source artifacts for stages preceding `<stage>` into the new run path; the target stage is not pre-populated.
- Writes a new `run.md` for the reopened run with `reopened_from: <source-work-id>@<source-checkpoint>` lineage metadata, `r2p_version` stamped at run creation time, and current stage set to `<stage>`.
- Maps to `CMD-RUN-REOPEN`.

Forbidden actions:

- Must not modify the source run's `run.md` or any source artifact.
- Must not delete source artifacts or the source run directory.
- Must not auto-approve any checkpoint on the new run.
- Must not switch the workspace active pointer to the new run without explicit user action through `r2p-switch`.

Common stops:

```text
blocked: source_run_not_found
next: r2p-status --all
```

```text
blocked: source_run_not_closed
next: complete the source run and approve PLAN Checkpoint first
```

```text
blocked: invalid_stage_name
next: specify --stage in { requirement_brief, risk_discovery, design, spec, plan }
```

## Start / Switch Examples

No existing open run:

```text
r2p-start "Add login rate limiting for password attempts"
```

Result:

```text
created: .req-to-plan/WF-20260525-login-rate-limiting/run.md
selected_run: .req-to-plan/WF-20260525-login-rate-limiting/run.md
next: r2p-continue
```

Selected open run:

```text
r2p-start "Add billing export"
```

Result:

```text
blocked: active_run_exists
active_run: .req-to-plan/WF-20260525-login-rate-limiting/run.md
next: r2p-continue
alternative: r2p-start --separate "Add billing export"
```

Unselected open run:

```text
r2p-start "Add billing export"
```

Result:

```text
blocked: open_run_exists
open_run: .req-to-plan/WF-20260525-login-rate-limiting/run.md
next: r2p-switch --work-id WF-20260525-login-rate-limiting
alternative: r2p-start --separate "Add billing export"
```

Independent new requirement:

```text
r2p-start --separate "Add billing export"
```

Result:

```text
created: .req-to-plan/WF-20260525-billing-export/run.md
selected_run: .req-to-plan/WF-20260525-billing-export/run.md
next: r2p-continue
```

Switch back:

```text
r2p-switch --work-id WF-20260525-login-rate-limiting
```

Result:

```text
selected_run: .req-to-plan/WF-20260525-login-rate-limiting/run.md
next: r2p-continue
```

## Internal Mapping

| Project shortcut | Internal authority | Notes |
|---|---|---|
| `r2p-start` | `CMD-RUN-START` plus active pointer update. | |
| `r2p-continue` | Stateful macro over allowed `CMD-*` intents according to run state and stop rules. | Surfaces `workflow tier-lock` or `workflow tier-escalate` when tier work is required. |
| `r2p-status` | `CMD-STATUS-*`; read-only. | |
| `r2p-switch` | Active pointer update only; no stage command intent. | |
| `r2p-reopen` | `CMD-RUN-REOPEN` | Does not modify source run. |

## Safety Rules

- Public project shortcuts must not expose internal `CMD-*` names as user-required commands.
- `r2p-continue` must stop instead of guessing when state, route, confirmation, or source freshness is ambiguous.
- Do not suggest `r2p-continue` for an unselected open run; switch to that `work-id` first.
- Only `r2p-switch` accepts `--work-id`.
- `r2p-start --separate` is the explicit signal to create a second open run.
- A terminal run remains available for status and switch, but it is not active for `r2p-continue`.

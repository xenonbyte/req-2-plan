# Workflow CLI Adapter

## Purpose

This document defines a concrete CLI carrier for the requirement-to-PLAN workflow command intents, plus post-PLAN executor command carriers.

It gives command names, required flags, output behavior, dry-run behavior, confirmation behavior, and exit codes for a future CLI implementation. The CLI does not add workflow authority. Requirement-to-PLAN commands map back to `workflow-command-surface.md`; post-PLAN executor commands map back to their owning post-PLAN surfaces.

Use this document after `workflow-operation-surface.md` and `workflow-command-surface.md` are stable, when designing or reviewing a CLI entry point.

## Scope

This document covers:

- CLI namespace and command names.
- Required global flags and path resolution.
- Mapping from requirement-to-PLAN CLI commands to `CMD-*` command intents.
- Confirmation and dry-run semantics.
- Human and JSON output contracts.
- Exit code meanings.
- CLI adapter safety rules.

This document does not cover:

- Runtime implementation.
- Shell completions.
- MCP, slash command, API, skill, or UI schemas.
- Actual implementation after PLAN approval.

## Adapter Boundary

The CLI is a carrier for command intents. Requirement-to-PLAN commands must preserve the authority, writes, stop conditions, and results defined in `workflow-command-surface.md`. Post-PLAN executor commands are outside that state machine and must preserve the authority defined by their owning post-PLAN surface.

The CLI must not:

- Add a requirement-to-PLAN command that cannot be mapped to exactly one `CMD-*` intent or to an allowed command composition.
- Treat Quality Gate readiness as checkpoint approval.
- Continue downstream work from stale or superseded artifacts.
- Hide `upstream_gap_detected`, `route_upstream`, open routes, or stale artifacts.
- Rewrite approved artifacts in place.
- Convert executor-neutral PLAN content into executor-specific runtime instructions inside the requirement-to-PLAN state machine.

## Namespace

Use one top-level command namespace:

```text
workflow <group> <action> [flags]
```

Groups:

| Group | Purpose |
|---|---|
| `run` | Start, resume, and close a workflow run. |
| `stage` | Load, produce, or update stage artifacts. |
| `gate` | Run entry and Quality Gates. |
| `review` | Run and merge checkpoint reviews. |
| `checkpoint` | Record Main/User checkpoint decisions. |
| `confirm` | Record, reject, or link user confirmations. |
| `subagent` | Dispatch, merge, or review subagent findings. |
| `gap` | Record, route, or re-import upstream gaps. |
| `artifact` | Mark downstream artifacts stale or superseded. |
| `status` | Inspect run state without writing. |

## Project Shortcut Wrappers

This repository also exposes optional project-level shortcut wrappers:

```text
coyeme-workflow-start [--separate] "<raw requirement>"
coyeme-workflow-continue
coyeme-workflow-status [--all]
coyeme-workflow-switch --work-id <id>
```

These wrappers are concrete carrier aliases for the shortcut surface defined in `docs/workflow-agent-command-adapter.md`. They do not create new requirement-to-PLAN `CMD-*` intents and do not add workflow authority.

Implementation binding:

| Wrapper | Concrete delegation |
|---|---|
| `tools/coyeme-workflow-start` | `python3 -m tools.workflow_cli.agent_shortcuts start` |
| `tools/coyeme-workflow-continue` | `python3 -m tools.workflow_cli.agent_shortcuts continue` |
| `tools/coyeme-workflow-status` | `python3 -m tools.workflow_cli.agent_shortcuts status` |
| `tools/coyeme-workflow-switch` | `python3 -m tools.workflow_cli.agent_shortcuts switch` |

Each wrapper resolves the repository root from its own script path, prepends that root to PYTHONPATH, then invokes python3 with a python fallback.

The active pointer path is:

```text
docs/artifacts/.workflow-active
```

The wrappers must preserve the concrete CLI's gates, checkpoint, route, stale artifact, and confirmation stops. `coyeme-workflow-continue` performs only safe single-step delegation and must stop rather than synthesize stage artifact content.

## Global Flags

| Flag | Required | Meaning |
|---|---|---|
| `--work-id <id>` | Conditional | Workflow run ID. Required when `--run` is not supplied. |
| `--run <path>` | Conditional | Explicit path to `run.md`. Required when `--work-id` is not supplied. |
| `--artifact-root <path>` | No | Artifact root override. Defaults are defined by Path resolution. |
| `--stage <stage>` | Command-specific | Stage name such as `requirement_brief`, `risk_discovery`, `design`, `spec`, or `plan`. |
| `--artifact <path-or-id>` | Command-specific | Target artifact or artifact version. |
| `--item <id-or-anchor>` | Command-specific | Stable item ID or section anchor. |
| `--route <route-id>` | Command-specific | Open upstream route ID. |
| `--source <path-or-url>` | Command-specific | Durable input source for run start, evidence import, or user confirmation source. |
| `--change <text-or-ref>` | Command-specific | Requested artifact change or change request reference. |
| `--scope <text-or-ref>` | Command-specific | Command scope, inspected area, or review scope. |
| `--task-type <type>` | Command-specific | Allowed subagent task type. |
| `--template <path-or-name>` | Command-specific | Finding or review template. |
| `--finding <path>` | Command-specific | Subagent or checkpoint review finding to merge. |
| `--owner-stage <stage>` | Command-specific | Upstream owner stage for a gap, route, or confirmation. |
| `--affected <path-or-id>` | Command-specific | Affected section, artifact, downstream item, or boundary. |
| `--required-action <text>` | Command-specific | Action required to close a gap or route. |
| `--impact <text>` | Command-specific | Blocking impact on the current gate, checkpoint, or downstream artifact. |
| `--confirmation <id-or-ref>` | Command-specific | Existing confirmation record to link. |
| `--upstream <path-or-id>` | Command-specific | Upstream artifact or item reference. |
| `--downstream <path-or-id>` | Command-specific | Downstream artifact or item reference. |
| `--reread <path-or-anchor>` | Command-specific | Required reread target for resume or re-import. |
| `--reason <text>` | Conditional | Reason for a write, route, stale mark, rejection, or checkpoint decision. |
| `--decision <value>` | Command-specific | Checkpoint or confirmation decision value. |
| `--json` | No | Emit machine-readable JSON output. |
| `--dry-run` | No | Validate and preview writes without changing files. |
| `--confirm` | Conditional | Explicitly authorize confirmation-bearing or approval-bearing writes. |
| `--version` | No | Print the CLI version and exit without resolving or writing workflow run state. |

Path resolution:

- Resolve the run record before resolving stage artifacts.
- If `--run` is supplied, use that exact `run.md`.
- If `--work-id` is supplied and `--run` is omitted, set artifact root to `--artifact-root` when supplied; otherwise use `docs/artifacts/<work-id>/`, then use `<artifact-root>/run.md`.
- If `--run` is supplied and `--artifact-root` is omitted, derive artifact root from the root recorded in `run.md` when present; otherwise use the directory containing `run.md`.
- If `--work-id` and `--run` are both supplied, they must refer to the same work ID or the CLI must stop.
- A run record selected through `--work-id` must contain the same work ID after it is read, even when `--artifact-root` overrides the default location.
- If `--run` and `--artifact-root` are both supplied, they must identify the same artifact root: `--run` must be that root's `run.md`, or the run record must explicitly point to that root.
- If artifact root cannot be derived unambiguously, the CLI must stop with exit code `2`; if supplied paths conflict with a readable run record, it must stop with exit code `6`.
- If neither is supplied, the CLI must stop with exit code `2`.
- Do not infer `work_id` from the current directory alone.

## Confirmation And Dry Run

Read-only commands never require `--confirm` and must never write files.

Write-capable commands may write when their preconditions pass. `--dry-run` forces a preview-only result for any command.

`--confirm` is required whenever the mapped command intent or mapped operation contract marks `User Confirmation Required` as required, or when a conditional confirmation condition evaluates true. The list below is not exhaustive; it is the adapter-level shortcut list for common confirmation-bearing writes:

- Approves, rejects, or blocks a checkpoint.
- Records a user-owned confirmation, rejection, or clarification.
- Changes a user-confirmed decision or confirmation-backed artifact meaning.
- Creates a duplicate run for an existing work ID.
- Supersedes or stales an approved artifact.
- Opens or closes an upstream route.
- Re-imports a repaired upstream artifact into a downstream draft.

Operation-owned confirmation conditions remain binding even when the command map row does not repeat `--confirm`, including ambiguous resume targets, source provenance decisions, user-controlled source access, risk acceptance, routing choices that affect user-confirmed scope, and remapping user-confirmed downstream choices.

If confirmation is required but missing, the CLI must stop with exit code `5` and report the required confirmation, affected artifact, and next allowed command.

## Output Contract

Requirement-to-PLAN human output is concise by default:

```text
command_result: <result-status>
intent: <CMD-*>
run: <run.md path>
current_stage: <stage>
next: <recommended command or stop reason>
```

JSON output uses this shape:

```json
{
  "command_result": "ready",
  "command_intent": "CMD-GATE-QUALITY",
  "run": "docs/artifacts/WF-001/run.md",
  "run_state_before": "active_stage_draft",
  "run_state_after": "ready_for_checkpoint_review",
  "current_stage": "spec",
  "active_artifact": "docs/artifacts/WF-001/06-spec.md@v2",
  "writes": [
    {
      "path": "docs/artifacts/WF-001/run.md",
      "kind": "run_update"
    }
  ],
  "planned_writes": [],
  "stops": [],
  "required_user_confirmation": null,
  "open_routes": [],
  "stale_artifacts": [],
  "next_allowed_command": "workflow review checkpoint --work-id WF-001 --stage spec"
}
```

Rules:

- Do not print raw artifact bodies by default.
- Do not print secrets, credentials, session cookies, private keys, or raw sensitive logs.
- `writes` lists actual persisted writes and must be empty for read-only commands and for `--dry-run`.
- `planned_writes` lists previewed writes for `--dry-run` and may be empty for completed write commands.
- Stop results must include `stops[]` and a concrete `next_allowed_command` when one can be safely known.
- If state is inconsistent, report the inconsistency instead of choosing a write command.

## Exit Codes

| Code | Meaning |
|---|---|
| `0` | Command completed successfully, or read-only status returned successfully. |
| `1` | Validation, Quality Gate, checkpoint review, or coverage issue found. |
| `2` | Invalid invocation, missing required input, or unreadable required path. |
| `3` | Preconditions failed or the command is not allowed in the current run state. |
| `4` | Upstream gap or upstream route is required before continuing. |
| `5` | Explicit user confirmation is required. |
| `6` | Conflicting or inconsistent run/artifact state. |
| `7` | Filesystem write, lock, or persistence failure. |
| `8` | Unsupported adapter command or unmapped command intent. |

## Command Map

Each requirement-to-PLAN CLI command below maps to exactly one `CMD-*` command intent. The full semantic contract for those rows remains owned by `workflow-command-surface.md`. Post-PLAN executor command rows use their own post-PLAN intent names and authority documents.

### Contract Inheritance Rule

The command map is a CLI binding table, not a replacement for the command contract schema.

Every requirement-to-PLAN row inherits the mapped `CMD-*` contract from `workflow-command-surface.md`, including:

- Operation Intents.
- Canonical Operations.
- Preconditions.
- Allowed Artifact Writes.
- `run.md` Updates.
- User Confirmation Required.
- Stop Conditions.
- Forbidden Behavior.
- Result / Output.

`Required CLI inputs` lists the minimum CLI-visible inputs. It does not narrow or override the command intent's `Required Inputs`.

If a required input is not provided as a flag, the CLI may derive it only from `run.md`, the active artifact, an open route, or a referenced finding/review artifact. If it cannot derive the input unambiguously, it must stop instead of guessing.

### Run

| CLI command | Command intent | Required CLI inputs | Notes |
|---|---|---|---|
| `workflow run start` | `CMD-RUN-START` | `--work-id`, plus `--source` or requirement text from stdin | Creates artifact root, `run.md`, and initial intake artifact. |
| `workflow run resume` | `CMD-RUN-RESUME` | `--work-id` or `--run` | Loads `Resume Context`; stops on any open route that requires re-import. |
| `workflow run close` | `CMD-RUN-CLOSE` | `--work-id` or `--run` | Closes only after approved PLAN checkpoint and no open route. |

### Stage

| CLI command | Command intent | Required CLI inputs | Notes |
|---|---|---|---|
| `workflow stage load` | `CMD-STAGE-LOAD` | `--work-id` or `--run`, `--stage`, plus `--confirm` when creating a new version from an approved artifact | Loads or creates the target stage draft. |
| `workflow stage produce` | `CMD-STAGE-PRODUCE` | `--work-id` or `--run`, `--stage` | Produces current-stage owned content only. |
| `workflow stage update` | `CMD-STAGE-UPDATE` | `--work-id` or `--run`, `--stage`, `--change`, `--reason`, plus `--confirm` when updating an approved artifact or changing a user-confirmed decision | Updates an unapproved draft or creates a new version when allowed. |
| `workflow stage ready` | `CMD-STAGE-READY` | `--work-id` or `--run`, `--stage` | Marks the current active draft artifact explicitly ready for Quality Gate evaluation; it does not pass the gate or approve a checkpoint. |

`workflow stage ready` reports command intent "`CMD-STAGE-READY`" in human-readable output.

### Gate, Review, And Checkpoint

| CLI command | Command intent | Required CLI inputs | Notes |
|---|---|---|---|
| `workflow gate entry` | `CMD-GATE-ENTRY` | `--work-id` or `--run`, `--stage` | Runs the stage entry gate. |
| `workflow gate quality` | `CMD-GATE-QUALITY` | `--work-id` or `--run`, `--stage` | Runs the current stage Quality Gate. |
| `workflow review checkpoint` | `CMD-REVIEW-CHECKPOINT` | `--work-id` or `--run`, `--stage` | Writes checkpoint review findings after Quality Gate `ready`. |
| `workflow review merge` | `CMD-REVIEW-MERGE` | `--work-id` or `--run`, `--stage`, plus `--finding` when findings are not already registered in `run.md` | Merges review findings before checkpoint decision. |
| `workflow checkpoint decide` | `CMD-CHECKPOINT-DECIDE` | `--work-id` or `--run`, `--stage`, `--decision`, `--confirm` | Records approval, change request, block, or route. |

Allowed checkpoint decisions:

```text
approved
changes_requested
blocked
upstream_gap_detected
route_upstream
```

### User Confirmation

| CLI command | Command intent | Required CLI inputs | Notes |
|---|---|---|---|
| `workflow confirm record` | `CMD-CONFIRM-RECORD` | `--work-id` or `--run`, `--stage`, `--item`, `--source`, `--decision`, `--affected`, `--downstream`, `--confirm` | Records explicit user-owned confirmation evidence; `--decision` carries the confirmation statement or value. |
| `workflow confirm reject` | `CMD-CONFIRM-REJECT` | `--work-id` or `--run`, `--stage`, `--item`, `--owner-stage`, `--affected`, `--impact`, `--reason`, `--confirm` | Records rejection or clarification need, including blocking impact, and routes when needed. |
| `workflow confirm link` | `CMD-CONFIRM-LINK` | `--work-id` or `--run`, `--stage`, `--confirmation`, `--item`, `--affected`, `--downstream`, plus `--confirm` when linking changes the confirmed meaning | Links an existing confirmation to an artifact section and downstream effect. |

### Subagent

| CLI command | Command intent | Required CLI inputs | Notes |
|---|---|---|---|
| `workflow subagent dispatch` | `CMD-SUBAGENT-DISPATCH` | `--work-id` or `--run`, `--stage`, `--task-type`, `--scope`, `--source`, `--template` | Dispatches allowed evidence-gathering work. |
| `workflow subagent merge` | `CMD-SUBAGENT-MERGE` | `--work-id` or `--run`, `--stage`, `--finding` | Merges findings and preserves unresolved conflicts. |
| `workflow subagent review` | `CMD-SUBAGENT-REVIEW` | `--work-id` or `--run`, `--stage`, `--scope`, `--template` | Runs checkpoint review subagents after Quality Gate `ready`. |

### Gap And Artifact Freshness

| CLI command | Command intent | Required CLI inputs | Notes |
|---|---|---|---|
| `workflow gap record` | `CMD-GAP-RECORD` | `--work-id` or `--run`, `--stage`, `--item`, `--owner-stage`, `--affected`, `--required-action`, `--reason`, `--confirm` | Records missing upstream input and opens the route. |
| `workflow gap route` | `CMD-GAP-ROUTE` | `--work-id` or `--run`, `--route`, `--confirm` | Opens owner-stage repair context and marks affected downstream state; stop if the route does not identify owner stage and current upstream artifact version. |
| `workflow gap reimport` | `CMD-GAP-REIMPORT` | `--work-id` or `--run`, `--route`, plus `--downstream` and `--reread` when not derivable from the route or `run.md`, `--confirm` | Re-imports repaired upstream after the owner checkpoint is approved; stop if repaired upstream, affected downstream artifact, and reread targets cannot be identified. |
| `workflow artifact mark-stale` | `CMD-ARTIFACT-MARK-STALE` | `--work-id` or `--run`, `--upstream`, `--downstream`, `--reason`, `--confirm` | Records stale or superseded downstream artifact state. |

### Status

| CLI command | Command intent | Required CLI inputs | Notes |
|---|---|---|---|
| `workflow status run` | `CMD-STATUS-RUN` | `--work-id` or `--run` | Shows current run status. |
| `workflow status stage` | `CMD-STATUS-STAGE` | `--work-id` or `--run` | Shows current stage and required next gate or artifact action. |
| `workflow status next` | `CMD-STATUS-NEXT` | `--work-id` or `--run` | Shows the next allowed semantic operation without writing. |
| `workflow status routes` | `CMD-STATUS-ROUTES` | `--work-id` or `--run` | Shows open routes and required owner actions. |
| `workflow status artifacts` | `CMD-STATUS-ARTIFACTS` | `--work-id` or `--run` | Shows active, approved, stale, and superseded artifact versions. |

## State Eligibility Rule

Before command-specific validation for requirement-to-PLAN commands, the CLI must check `workflow-command-surface.md#run-state-command-eligibility-matrix`.

Apply the command-surface context-refresh exception before refusing a resume caused by missing loaded context. `workflow run resume` may establish or refresh `Resume Context` for an existing readable, nonterminal run even when ordinary `CMD-RUN-RESUME` is not listed for that state. In this mode, it must not advance stage, create a next-stage draft, close routes, approve checkpoints, or write stage artifact content unless the matrix also allows ordinary `CMD-RUN-RESUME`. If the run is `not_started`, `closed_at_plan_checkpoint`, inconsistent, or unknown after reading `run.md`, the CLI must stop or return read-only status instead of writing.

If the command is not allowed in the current state:

1. Stop with exit code `3`.
2. Do not write artifacts or `run.md`.
3. Report the current run state.
4. Suggest `workflow status next <run-locator>` or the safe next command if it is unambiguous. Preserve the current resolved run locator: prefer the caller's original `--run <path>` when supplied; otherwise use `--work-id <id>` when the work ID is known.

Inspection commands are allowed in any readable state and remain read-only.

## Resume Context Rule

Before any write-capable requirement-to-PLAN CLI command continues an existing run, the CLI must prove the active run context is loaded:

```text
run.md
active artifact
active item
required reread targets
open routes
stale or superseded markers
```

If this proof is missing, the CLI must run the semantic equivalent of `CMD-RUN-RESUME` first or stop and recommend a resume command that preserves the current resolved run locator. Prefer the caller's original `--run <path>` when supplied; otherwise use `--work-id <id>` when the work ID is known.

```text
workflow run resume <run-locator>
```

The CLI must not continue from conversation-only memory.

## Examples

Inspect the next allowed operation:

```sh
workflow status next --work-id WF-001 --json
```

Resume after interruption or context loss:

```sh
workflow run resume --work-id WF-001
```

Re-import a repaired upstream DESIGN route:

```sh
workflow gap reimport --work-id WF-001 --route ROUTE-DES-001 --confirm
```

Approve SPEC after Quality Gate, checkpoint review, review merge, and required confirmations:

```sh
workflow checkpoint decide --work-id WF-001 --stage spec --decision approved --confirm
```

Preview stale marking without writing:

```sh
workflow artifact mark-stale --work-id WF-001 --upstream 05-design.md@v2 --downstream 06-spec.md@v1 --reason "DESIGN v2 approved" --dry-run
```

## Reference Implementation

The minimal local reference implementation lives under `tools/workflow_cli/`.

Run it with:

```sh
python -m tools.workflow_cli status next --work-id WF-001 --json
```

When the environment exposes only `python3`, use the equivalent:

```sh
python3 -m tools.workflow_cli status next --work-id WF-001 --json
```

Run tests with:

```sh
python -m unittest discover -s tests -p 'test_*.py'
```

The implementation is a CLI carrier and state manager. It does not generate semantic stage artifact content or execute PLAN tasks.

## Adapter Validation Checklist

Use this checklist when reviewing a CLI implementation or CLI-facing prompt:

- Every exposed requirement-to-PLAN CLI command maps to one `CMD-*` intent listed in `workflow-command-surface.md`.
- Every write-capable requirement-to-PLAN command checks run-state eligibility before command-specific preconditions.
- Every write-capable requirement-to-PLAN command applies the Resume Context Rule before writing.
- Path resolution derives artifact root for both `--work-id` and `--run` modes, and stops on conflicting supplied paths.
- Read-only commands never write `run.md` or artifacts.
- `--dry-run` produces no `writes` and reports intended changes through `planned_writes`.
- Required `--confirm` gates cannot be bypassed by `--json`, `--dry-run`, or default flags.
- Conditional `User Confirmation Required` rules inherited from mapped operation contracts are enforced even when a command map row does not list `--confirm`.
- Open routes block ordinary resume and downstream approval.
- `workflow gap reimport` does not approve the downstream checkpoint by itself.
- Exit codes distinguish validation issues, precondition stops, upstream gaps, confirmation needs, and inconsistent state.
- JSON output includes enough state to recover the next safe command without reading conversation history.

## Non-Goals

The CLI adapter is not the workflow runtime. It is a concrete syntax contract for one possible carrier.

Do not treat this document as permission to implement executor-specific PLAN execution, external orchestration, background agents, or persistent services inside the requirement-to-PLAN workflow.

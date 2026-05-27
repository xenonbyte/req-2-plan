# Workflow Operator Runbook

## Purpose

This runbook gives the shortest normal operating path for the local workflow CLI:

```text
raw requirement -> approved PLAN -> optional executor-specific derived plan
```

Use it when operating an actual workflow run. Use the stage workflow documents when deciding whether an artifact is semantically ready.

This runbook documents operator actions. The CLI records state transitions, validates gates, and enforces checkpoints; it does not generate the substantive Requirement Brief, Risk Discovery, DESIGN, SPEC, or PLAN content.

## Preconditions

- Run from the repository root or set `PYTHONPATH` to the repository root.
- Use `python3 -m tools.workflow_cli`.
- Keep workflow artifacts under `docs/artifacts/<work-id>/` unless a temporary or test artifact root is supplied with `--artifact-root`.
- Treat `run.md` as the source of truth for current stage, active artifact, open routes, stale markers, and resume context.
- Do not edit approved artifacts in place. Create a new version or a repair/superseding workflow when approved input changes.

## Start A Run

Command: `workflow run start`.

```bash
env PYTHONDONTWRITEBYTECODE=1 python3 -m tools.workflow_cli run start \
  --work-id <work-id> \
  --source <requirement.md> \
  --json
```

If the command returns `duplicate_active_run` or `duplicate_closed_run`, inspect the existing run before using `--confirm`.

## Stage Loop

Run stages in canonical order:

```text
raw_requirement
requirement_brief
risk_discovery
design
spec
plan
```

`Intake Brief v0` and `Requirement Discovery Notes` are content sections within the Requirement Brief workflow. `Design Entry Gate` and `Design Scope Gate` are DESIGN-owned gate evidence. None of those are separate `Current Stage` values in the local CLI state machine.

For every stage after `raw_requirement`, first run the entry gate:

```bash
env PYTHONDONTWRITEBYTECODE=1 python3 -m tools.workflow_cli gate entry \
  --work-id <work-id> \
  --stage <stage> \
  --json
```

Produce or update the artifact according to the owning stage workflow:

```bash
env PYTHONDONTWRITEBYTECODE=1 python3 -m tools.workflow_cli stage produce \
  --work-id <work-id> \
  --stage <stage> \
  --json < <stage-artifact-body.md>
```

Mark the current active draft artifact ready for Quality Gate evaluation:

```bash
env PYTHONDONTWRITEBYTECODE=1 python3 -m tools.workflow_cli stage ready \
  --work-id <work-id> \
  --stage <stage> \
  --json
```

Use `workflow stage ready` for this operation. This marks the current active draft artifact explicitly ready for Quality Gate evaluation. It records the author's readiness assertion only. It does not pass the Quality Gate, move the active artifact row to `ready`, run checkpoint review, or approve downstream handoff.

Manual explicit status formats remain valid when inspecting or authoring artifacts directly:

```yaml
---
status: ready
---
```

```markdown
## Status
ready
```

```markdown
- Status: ready
```

Do not leave placeholder choices such as `ready | blocked`; the Quality Gate treats those as unresolved.

Then run the Quality Gate:

```bash
env PYTHONDONTWRITEBYTECODE=1 python3 -m tools.workflow_cli gate quality \
  --work-id <work-id> \
  --stage <stage> \
  --json
```

Checkpoint review has three operator-visible steps:

```bash
env PYTHONDONTWRITEBYTECODE=1 python3 -m tools.workflow_cli review checkpoint \
  --work-id <work-id> \
  --stage <stage> \
  --json

env PYTHONDONTWRITEBYTECODE=1 python3 -m tools.workflow_cli review merge \
  --work-id <work-id> \
  --stage <stage> \
  --json

env PYTHONDONTWRITEBYTECODE=1 python3 -m tools.workflow_cli confirm record \
  --work-id <work-id> \
  --stage <stage> \
  --item <artifact@version#checkpoint> \
  --decision approved \
  --source user \
  --affected <artifact@version> \
  --downstream <handoff-target> \
  --confirm \
  --json
```

Approve the checkpoint only after findings are merged and the required confirmation is recorded:

Command: `workflow checkpoint decide`.

```bash
env PYTHONDONTWRITEBYTECODE=1 python3 -m tools.workflow_cli checkpoint decide \
  --work-id <work-id> \
  --stage <stage> \
  --decision approved \
  --confirm \
  --json
```

For non-PLAN stages, resume to create or select the next-stage draft:

```bash
env PYTHONDONTWRITEBYTECODE=1 python3 -m tools.workflow_cli run resume \
  --work-id <work-id> \
  --json
```

## Project Shortcut Path

For agent-oriented operation, the repository also exposes:

```text
coyeme-workflow-start "<raw requirement>"
coyeme-workflow-continue
coyeme-workflow-status [--all]
coyeme-workflow-switch --work-id <work-id>
coyeme-workflow-adapt --executor superpowers
```

These shortcuts are intentionally small. `coyeme-workflow-continue` may perform safe `run resume` or `run close` delegation, but it stops and prints the next internal `workflow ...` command when stage content, Quality Gate readiness, review merge, confirmation, checkpoint decision, route repair, or re-import work is required.

## Close The Run

After the PLAN checkpoint is approved, close the requirement-to-PLAN workflow:

Command: `workflow run close`.

```bash
env PYTHONDONTWRITEBYTECODE=1 python3 -m tools.workflow_cli run close \
  --work-id <work-id> \
  --json
```

Expected terminal state:

```text
command_result: closed_at_plan_checkpoint
current_stage: closed
open_routes: []
stale_artifacts: []
```

## Adapt The Approved PLAN

Executor adaptation is optional and post-PLAN. It is not part of the requirement-to-PLAN `CMD-*` state machine.

Command: `workflow executor adapt`.

```bash
env PYTHONDONTWRITEBYTECODE=1 python3 -m tools.workflow_cli executor adapt \
  --work-id <work-id> \
  --plan docs/artifacts/<work-id>/07-plan.md@v1#PLAN-Checkpoint \
  --executor superpowers \
  --adapter-rule superpowers-v1 \
  --output docs/superpowers/plans/<date>-<work-id>.md \
  --json
```

The adapter may write:

| Result | Write |
|---|---|
| `derived_plan_written` | One derived executor plan. |
| `adapter_gap_detected` | `<output>.repair.md` as a Post-PLAN Gap Repair Request. |
| `stale_source_detected` | `<output>.repair.md` as a Post-PLAN Gap Repair Request. |

The adapter must not mutate the approved source run or execute PLAN tasks.

## Resume And Stop Handling

Use status commands before guessing:

```bash
env PYTHONDONTWRITEBYTECODE=1 python3 -m tools.workflow_cli status next --work-id <work-id> --json
env PYTHONDONTWRITEBYTECODE=1 python3 -m tools.workflow_cli status run --work-id <work-id> --json
env PYTHONDONTWRITEBYTECODE=1 python3 -m tools.workflow_cli status routes --work-id <work-id> --json
env PYTHONDONTWRITEBYTECODE=1 python3 -m tools.workflow_cli status artifacts --work-id <work-id> --json
```

Common stops:

| Stop | Operator action |
|---|---|
| `missing_upstream_checkpoint` | Approve the prior stage before loading or gating this stage. |
| `review_findings_unmerged` | Run `workflow review merge` for the current stage. |
| `checkpoint_confirmation_missing` | Record or link the required confirmation, then decide again. |
| `open_route` | Route, repair, and re-import before downstream work continues. |
| `stale_artifact` | Re-import repaired input or start a repair/superseding workflow. |
| `adapter_gap_detected` | Use the generated Post-PLAN Gap Repair Request. |
| `stale_source_detected` | Adapt from a new approved PLAN after repair or supersession. |

## Live End-To-End Check

Latest local smoke:

| Field | Result |
|---|---|
| Date | 2026-05-26 |
| Work ID | `WF-FULL-E2E-20260526` |
| Artifact root | `/private/tmp/coyeme-workflow-full-e2e.xoTHx8/docs/artifacts/WF-FULL-E2E-20260526` |
| Stage path | `raw_requirement -> requirement_brief -> risk_discovery -> design -> spec -> plan` |
| Close result | `closed_at_plan_checkpoint` |
| Adapter result | `derived_plan_written` |
| Derived plan check | Contains `superpowers:subagent-driven-development` and `PLAN-TASK-001`. |

This smoke validates CLI state flow and adapter handoff. It does not prove that real stage artifact content is semantically sufficient; stage Quality Gates and checkpoint reviewers own that judgment.

## Dogfood Validation Notes

Latest two-round dogfood in `/Users/xubo/x-studio/test`:

| Round | Work ID | Result |
|---|---|---|
| New small requirement | `WF-20260527-create-a-tiny-python-tas` | Reached `closed_at_plan_checkpoint`, adapted to Superpowers, executed to passing tests. |
| Upgrade / modification | `WF-20260527-upgrade-the-existing-tas` | Reached `closed_at_plan_checkpoint`, adapted to Superpowers, executed to passing tests. |

Observed operator friction:

- Stage artifact semantic content was authored explicitly; the CLI did not generate Requirement Brief, Risk Discovery, DESIGN, SPEC, or PLAN prose.
- Artifact readiness was made explicit in the artifact before `workflow gate quality`.
- `coyeme-workflow-continue` helped with safe resume/close boundaries but intentionally stopped before stage authoring, gate readiness, review merge, confirmation, and checkpoint decision work.

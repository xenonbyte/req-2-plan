# Workflow Operator Runbook

## Purpose

This runbook gives the shortest normal operating path for the local workflow CLI:

```text
raw requirement -> approved PLAN -> executor handoff
```

Use it when operating an actual workflow run. Use the stage workflow documents when deciding whether an artifact is semantically ready.

This runbook documents operator actions. The CLI records state transitions, validates gates, and enforces checkpoints; it does not generate the substantive Requirement Brief, Risk Discovery, DESIGN, SPEC, or PLAN content.

## Preconditions

- Run from the repository root or set `PYTHONPATH` to the repository root.
- Use `python3 -m tools.workflow_cli`.
- Keep workflow artifacts under `.req-to-plan/<work-id>/` unless a temporary or test root is supplied with `--base-path`.
- Set `R2P_JSON=1` when machine-readable output is required; the current CLI does not accept a `--json` flag.
- Treat `run.md` as the source of truth for current stage, active artifact, open routes, stale markers, and resume context.
- Do not edit approved artifacts in place. Create a new version or a repair/superseding workflow when approved input changes.

## One-Time Setup: Install Agent Integration

The lifecycle binary `r2p` (no hyphen between `r2p` and the subcommand) registers the requirement-to-PLAN agent integration on a host. Run install once per platform before using the dashed `r2p-*` shortcuts.

```bash
r2p install --platform claude,codex,gemini
```

Verify installation:

```bash
r2p installed
```

Cleanup:

```bash
r2p uninstall --platform <name>
```

See `workflow-install-surface.md` for per-platform paths, manifest format, and safety rules.

## Start A Run

Command: `workflow run-start`.

```bash
env PYTHONDONTWRITEBYTECODE=1 python3 -m tools.workflow_cli run-start \
  --work-id <work-id> \
  --requirement "<raw requirement>"
```

If the command reports that the run already exists, inspect the existing run before rerunning with `--overwrite`. `--overwrite` clears the existing `.req-to-plan/<work-id>/` run directory before creating the replacement run.

## Tier Workflow

The CLI estimates the tier at `run-start` and writes a Tier Estimation Evidence Block to `run.md`. Lock the tier before any stage produce runs for `requirement_brief`. See `workflow-invariants.md#workflow-complexity-tier-rule` for the canonical Tier Model.

Read the estimate:

```bash
env PYTHONDONTWRITEBYTECODE=1 python3 -m tools.workflow_cli tier-status \
  --work-id <work-id>
```

Lock the tier after confirming the Evidence Block with the user:

```bash
env PYTHONDONTWRITEBYTECODE=1 python3 -m tools.workflow_cli tier-lock \
  --work-id <work-id> \
  --base <light|standard> \
  --confirm
```

Add `--modifiers <comma-separated-modifiers>` when the tier estimate requires modifiers.

Escalate when Risk Discovery or DESIGN surfaces a new modifier (for example, a migration trigger appears mid-discovery):

```bash
env PYTHONDONTWRITEBYTECODE=1 python3 -m tools.workflow_cli tier-escalate \
  --work-id <work-id> \
  --modifier migration
```

The current local CLI does not implement bundled checkpoint approval. Approve each stage checkpoint explicitly.

Floor override is discouraged. The CLI refuses a below-Floor lock unless `--override-floor` plus `--confirm` is supplied:

```bash
env PYTHONDONTWRITEBYTECODE=1 python3 -m tools.workflow_cli tier-lock \
  --work-id <work-id> \
  --base light \
  --override-floor \
  --confirm
```

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
env PYTHONDONTWRITEBYTECODE=1 python3 -m tools.workflow_cli gate-entry \
  --work-id <work-id> \
  --stage <stage>
```

Produce or update the artifact according to the owning stage workflow:

```bash
env PYTHONDONTWRITEBYTECODE=1 python3 -m tools.workflow_cli stage-produce \
  --work-id <work-id> \
  --stage <stage> \
  --content-file <stage-artifact-body.md>
```

Mark the current active draft artifact ready for Quality Gate evaluation:

```bash
env PYTHONDONTWRITEBYTECODE=1 python3 -m tools.workflow_cli stage-ready \
  --work-id <work-id> \
  --stage <stage>
```

Use `workflow stage-ready` for this operation. This marks the current active draft artifact explicitly ready for Quality Gate evaluation. It records the author's readiness assertion only. It does not pass the Quality Gate, move the active artifact row to `ready`, run checkpoint review, or approve downstream handoff.

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
env PYTHONDONTWRITEBYTECODE=1 python3 -m tools.workflow_cli gate-quality \
  --work-id <work-id> \
  --stage <stage>
```

Checkpoint review has two operator-visible CLI steps for approval in the current MVP:

```bash
env PYTHONDONTWRITEBYTECODE=1 python3 -m tools.workflow_cli review-checkpoint \
  --work-id <work-id> \
  --stage <stage>
```

For a forced-review stage (`design`, `spec`, or `plan` with `migration`, `safety`, or `cross_project`), add a real version-matched subagent review file before approval:

```text
.req-to-plan/<work-id>/reviews/<stage>-subagent-review-v<artifact-version>.md
```

Approve the checkpoint only after the marker exists, the artifact is still the active ready version, and required review evidence is present:

Command: `workflow checkpoint-decide`.

```bash
env PYTHONDONTWRITEBYTECODE=1 python3 -m tools.workflow_cli checkpoint-decide \
  --work-id <work-id> \
  --stage <stage> \
  --decision approved \
  --confirm
```

For non-PLAN stages after checkpoint approval, advance to the next stage:

Command: `workflow stage-advance`.

```bash
env PYTHONDONTWRITEBYTECODE=1 python3 -m tools.workflow_cli stage-advance \
  --work-id <work-id>
```

Then run the next stage's entry gate:

```bash
env PYTHONDONTWRITEBYTECODE=1 python3 -m tools.workflow_cli gate-entry \
  --work-id <work-id> \
  --stage <next-stage>
```

For PLAN stage checkpoint approval, close the run instead (no stage-advance for PLAN).

## Project Shortcut Path

For agent-oriented operation, the repository also exposes:

```text
r2p-start ("<raw requirement>" | --file <path>)
r2p-continue
r2p-tier-lock --work-id <work-id> --base <light|standard> --confirm
r2p-status [--all]
r2p-switch --work-id <work-id>
r2p-reopen --from <work-id> --stage <stage> --reason "<short>"
```

These shortcuts are intentionally small. `r2p-continue` may perform safe gate, review-open, stage-advance, or run-close delegation, but it stops and prints the next explicit command when stage content, tier locking, Quality Gate readiness, checkpoint approval, route repair, or re-import work is required. If the stop prints `content_file`, write the stage content or repair there before running the printed `next:` command.

## Close The Run

After the PLAN checkpoint is approved, close the requirement-to-PLAN workflow:

Command: `workflow run-close`.

```bash
env PYTHONDONTWRITEBYTECODE=1 python3 -m tools.workflow_cli run-close \
  --work-id <work-id>
```

Expected terminal state:

```text
command_result: closed_at_plan_checkpoint
current_stage: closed
open_routes: []
stale_artifacts: []
```

## Reopen After Closure

A closed `closed_at_plan_checkpoint` run is frozen. To continue from a closed run (for example, the requirement changed and the approved PLAN needs revision), reopen it into a new lineage run instead of editing the closed source.

Agent shortcut:

```bash
r2p-reopen --from <work-id> --stage <stage> --reason "<short>"
```

Internal command:

```bash
env PYTHONDONTWRITEBYTECODE=1 python3 -m tools.workflow_cli run-reopen \
  --from <source-work-id> \
  --stage <stage> \
  --reason "<short>"
```

The reopen creates `.req-to-plan/<source-work-id>-rN/` with a new `run.md` whose lineage references the source. The source run stays `closed_at_plan_checkpoint` and its approved artifacts are not modified. Stages preceding `<stage>` are copied; the target stage is left empty so the operator can produce a new version.

## Hand Off The Approved PLAN

The approved PLAN at `07-plan.md` is executor-neutral. After the run closes, hand it directly to your executor (for example, superpowers reads the neutral PLAN as-is). There is no post-PLAN adaptation step.

## Resume And Stop Handling

Use status commands before guessing:

```bash
env PYTHONDONTWRITEBYTECODE=1 python3 -m tools.workflow_cli status-next --work-id <work-id>
env PYTHONDONTWRITEBYTECODE=1 python3 -m tools.workflow_cli status-run --work-id <work-id>
```

Common stops:

| Stop | Operator action |
|---|---|
| `missing_upstream_checkpoint` | Approve the prior stage before loading or gating this stage. |
| `needs_human_approval` | Inspect the checkpoint marker and any required subagent review, then run `workflow checkpoint-decide`. |
| `needs_repair` | Edit the printed `content_file`, then run the printed `stage-update` command. |
| `open_route` | Route, repair, and re-import before downstream work continues. |
| `stale_artifact` | Re-import repaired input or start a repair/superseding workflow. |

## Live End-To-End Check

After implementing the workflow per `docs/superpowers/plans/2026-05-27-req-to-plan-agent-workflow.md`, run the integration test suite (`tests/test_integration.py`) which covers five canonical scenarios:

| Scenario | Asserts |
|---|---|
| Light path (no modifier) | `closed_at_plan_checkpoint` reached through per-stage checkpoint approval |
| Migration path (e.g. `"把项目改成 rust 实现"`) | Tier floor enforces `+migration +cross_project`; subagent review required at DESIGN/SPEC/PLAN |
| Escalation path | New modifier added mid-run via `tier-escalate`; affected forced-review checks are enforced before approval |
| Reopen path | `run-reopen --from <closed-id> --stage <stage>` creates `<id>-rN` new run with lineage |

Record the smoke run date and host-agnostic artifact paths here after running:

```text
Date:               <YYYY-MM-DD>
Integration tests:  <pass/fail counts>
Adversarial smoke:  ./tools/r2p-start "把项目改成 rust 实现"
                    → tier floor includes {migration, cross_project}
Light smoke:        ./tools/r2p-start "按钮颜色改成红色"
                    → tier floor = light if repo baseline is small and no keywords hit
```

This section is intentionally empty until the workflow is implemented and tested locally.

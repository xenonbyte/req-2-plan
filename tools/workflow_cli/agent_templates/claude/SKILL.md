---
name: req-to-plan
description: Requirement-to-PLAN workflow skill (r2p {{R2P_VERSION}})
---

# req-to-plan Skill

Use this skill to drive the 5-stage requirement-to-PLAN workflow in any project where r2p is installed.

## Available Commands

Run each via Bash using the scripts in `{{R2P_BIN_DIR}}`:

| Command | Purpose |
|---|---|
| `{{R2P_BIN_DIR}}/r2p-start [--separate] [--repo-path <dir>] ("<requirement>" \| --file <path>)` | Start a new workflow run; `--repo-path` grounds tier estimation and the Context Pack in real repo facts |
| `{{R2P_BIN_DIR}}/r2p-continue` | Continue the active run |
| `{{R2P_BIN_DIR}}/r2p-tier-lock --work-id <id> --base <light\|standard> --confirm` | Lock the tier for a run |
| `{{R2P_BIN_DIR}}/r2p-status [--all]` | Inspect run state (read-only) |
| `{{R2P_BIN_DIR}}/r2p-switch --work-id <id>` | Switch active run pointer |
| `{{R2P_BIN_DIR}}/r2p-reopen --from <work-id> --stage <stage> --reason "<text>"` | Reopen a closed run |
| `{{R2P_BIN_DIR}}/r2p-gap-open --work-id <id> --owner-stage <stage> --required-action "<text>"` | Route an upstream gap back to its owner stage |
| `{{R2P_BIN_DIR}}/r2p-gap-resolve --work-id <id> --route-id <route-id>` | Resolve an open upstream-gap route after the owner stage re-passes gate-quality |

## Usage Pattern

1. `r2p-start [--repo-path <dir>] ("<requirement>" | --file <path>)` — start a new run; pass `--repo-path` when the requirement targets an existing repo
2. `r2p-continue` — repeatedly; runs safe automatic steps, stops and suggests the next command when a human action is needed
   - Stops at: tier not locked, needs stage artifact content, needs stage ready mark, needs human checkpoint approval, entry gate failed, needs repair (Quality Gate failed or changes requested)
   - When stopped at `needs_content` or `needs_repair`, write the required artifact content into the printed `content_file`, then run the printed `next:` command exactly
   - For other stops, run the printed `next:` command exactly; if an `alt:` command is shown, use it only when that alternate decision is intended
   - Auto-runs: eligible entry gates, eligible Quality Gates, opens checkpoint review (`review-checkpoint`)
   - Auto-advances: moves to the next stage after non-PLAN checkpoint approval, then runs that stage's entry gate
   - Auto-closes: closes the run when the PLAN checkpoint is approved and no open routes remain
   - Does NOT auto-mark artifacts ready and does NOT auto-approve checkpoints — those are human steps
3. When the run closes, hand the approved PLAN at `07-plan.md` directly to your executor — the PLAN is executor-neutral and needs no adaptation step.

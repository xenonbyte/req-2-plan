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
| `{{R2P_BIN_DIR}}/r2p-start [--separate] "<requirement>"` | Start a new workflow run |
| `{{R2P_BIN_DIR}}/r2p-continue` | Continue the active run |
| `{{R2P_BIN_DIR}}/r2p-status [--all]` | Inspect run state (read-only) |
| `{{R2P_BIN_DIR}}/r2p-switch --work-id <id>` | Switch active run pointer |
| `{{R2P_BIN_DIR}}/r2p-adapt --executor <name>` | Generate executor-specific plan from approved PLAN |
| `{{R2P_BIN_DIR}}/r2p-reopen --from <work-id> --stage <stage> --reason "<text>"` | Reopen a closed run |

## Usage Pattern

1. `r2p-start "<requirement>"` — start a new run
2. `r2p-continue` — repeatedly; auto-gates eligible runs, stops when human decisions needed
   - Stops at: needs stage artifact content, needs stage ready mark, needs Quality Gate readiness, needs merged checkpoint review findings, needs human checkpoint approval, needs route handling
   - Auto-gates: eligible entry gates, eligible Quality Gates, auto-marks ready if content passed gate
   - Auto-approves: bundled checkpoints when eligible and all findings merged
   - Auto-advances: moves to next stage after non-PLAN checkpoint approval and entry gate passes
   - Auto-closes: closes the run when PLAN checkpoint is approved and no open routes remain
3. `r2p-adapt --executor superpowers` — generate executor-specific plan from approved PLAN

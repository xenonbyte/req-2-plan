---
name: r2p-tier-lock
description: Lock the complexity tier for the active requirement-to-PLAN workflow run. Use when r2p-continue stops with tier_not_locked or asks for r2p-tier-lock.
---

# r2p-tier-lock

Run `{{R2P_BIN_DIR}}/r2p-tier-lock` with the work ID and selected base tier.

Usage: `{{R2P_BIN_DIR}}/r2p-tier-lock --work-id <work-id> --base <light|standard> [--modifiers <modifier,...>] --confirm`

Use this only after choosing the tier floor shown by the workflow output.

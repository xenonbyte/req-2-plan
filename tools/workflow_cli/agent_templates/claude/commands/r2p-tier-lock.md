---
description: Lock the complexity tier for an active requirement-to-PLAN workflow run
---
Run `{{R2P_BIN_DIR}}/r2p-tier-lock` with the work ID and selected base tier.

Usage: `{{R2P_BIN_DIR}}/r2p-tier-lock --work-id <work-id> --base <light|standard> [--modifiers <modifier,...>] --confirm`

Use this when `r2p-continue` stops with `tier_not_locked`.

---
description: Resolve an open upstream-gap route after the owner stage passes gate-quality
---
Run `{{R2P_BIN_DIR}}/r2p-gap-resolve` after the owner stage has been re-worked, marked `ready`, and passed `gate-quality`. It closes the route so the owner can be re-approved and the downstream re-derived.

Usage: `{{R2P_BIN_DIR}}/r2p-gap-resolve --work-id <work-id> --route-id <route-id>`

Example: `{{R2P_BIN_DIR}}/r2p-gap-resolve --work-id WF-20260604-login --route-id R-1`

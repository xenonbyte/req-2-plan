---
name: r2p-gap-open
description: Route an upstream gap on an open requirement-to-PLAN run back to the stage that owns the missing decision. Use when the user asks to run r2p-gap-open or route an upstream gap on an open run.
---

# r2p-gap-open

Run `{{R2P_BIN_DIR}}/r2p-gap-open` to route a discovered upstream gap on an OPEN run back to the stage that owns the missing decision. Downstream artifacts are marked stale and must be re-derived.

Usage: `{{R2P_BIN_DIR}}/r2p-gap-open --work-id <work-id> --owner-stage <stage> --required-action "<text>"`

Example: `{{R2P_BIN_DIR}}/r2p-gap-open --work-id WF-20260604-login --owner-stage design --required-action "fixed-window burst flaw"`

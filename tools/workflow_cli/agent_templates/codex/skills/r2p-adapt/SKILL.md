---
name: r2p-adapt
description: Generate an executor-specific plan from an approved r2p PLAN artifact. Use when the user asks to run r2p-adapt or adapt a closed requirement-to-PLAN run for an executor.
---

# r2p-adapt

Run `{{R2P_BIN_DIR}}/r2p-adapt` after the workflow run is closed at the PLAN checkpoint.

Usage: `{{R2P_BIN_DIR}}/r2p-adapt --executor <name>`

Example: `{{R2P_BIN_DIR}}/r2p-adapt --executor superpowers`

---
name: r2p-start
description: Start a new requirement-to-PLAN workflow run from a raw requirement. Use when the user asks to run r2p-start, start r2p, begin the requirement-to-PLAN workflow, or turn a requirement into a PLAN.
---

# r2p-start

Run `{{R2P_BIN_DIR}}/r2p-start` with the requirement as a positional argument.

Usage: `{{R2P_BIN_DIR}}/r2p-start [--separate] "<raw requirement>"`

Use `--separate` to create an independent run when another open run exists.

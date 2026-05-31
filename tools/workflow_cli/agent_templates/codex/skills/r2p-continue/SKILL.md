---
name: r2p-continue
description: Continue the active requirement-to-PLAN workflow run. Use when the user asks to run r2p-continue, continue r2p, resume the active r2p run, or advance the current requirement-to-PLAN workflow.
---

# r2p-continue

Run `{{R2P_BIN_DIR}}/r2p-continue` to resume the currently selected run.

Usage: `{{R2P_BIN_DIR}}/r2p-continue`

Call repeatedly until the run reaches the closed state. When the output reports `stop:`, run the printed `next:` command exactly. If an `alt:` command is shown, use it only when that alternate decision is intended. Use `r2p-status` to inspect progress.

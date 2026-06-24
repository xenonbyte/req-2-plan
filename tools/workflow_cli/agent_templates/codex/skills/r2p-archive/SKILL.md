---
name: r2p-archive
description: Use when the user asks to run r2p-archive, archive an r2p run, or move a closed or executing r2p workflow run out of the active workspace.
---

# r2p-archive

Run `{{R2P_BIN_DIR}}/r2p-archive` to archive the selected run, or pass a run explicitly.

Usage: `{{R2P_BIN_DIR}}/r2p-archive [--work-id <work-id>]`

The run must be `closed_at_plan_checkpoint` or `executing`. On success, it moves `.req-to-plan/<work-id>` to `.req-to-plan/archive/<work-id>` and clears the active selection for that run.

Use `{{R2P_BIN_DIR}}/r2p-status --all` afterward to inspect remaining active runs.

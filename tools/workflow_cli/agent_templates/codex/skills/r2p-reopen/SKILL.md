---
name: r2p-reopen
description: Reopen a closed requirement-to-PLAN workflow run from a specific stage. Use when the user asks to run r2p-reopen or reopen an r2p run because an upstream stage needs repair.
---

# r2p-reopen

Run `{{R2P_BIN_DIR}}/r2p-reopen` to reopen a run that was closed at the PLAN checkpoint.

Usage: `{{R2P_BIN_DIR}}/r2p-reopen --from <work-id> --stage <stage> --reason "<text>"`

Example: `{{R2P_BIN_DIR}}/r2p-reopen --from WF-20260527-login-rate-limit --stage spec --reason "spec gap found"`

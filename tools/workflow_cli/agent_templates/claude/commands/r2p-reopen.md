---
description: Reopen a closed workflow run from a specific stage
---
Run `{{R2P_BIN_DIR}}/r2p-reopen` to reopen a run that was closed at the PLAN checkpoint.

Usage: `{{R2P_BIN_DIR}}/r2p-reopen --from <work-id> --stage <stage> --reason "<text>"`

Example: `{{R2P_BIN_DIR}}/r2p-reopen --from WF-20260527-login-rate-limit --stage spec --reason "spec gap found"`

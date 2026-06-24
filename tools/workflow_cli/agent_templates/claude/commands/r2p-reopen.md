---
description: Reopen a closed or executing workflow run from a specific stage
---
Run `{{R2P_BIN_DIR}}/r2p-reopen` to reopen a run that was closed at the PLAN checkpoint or is already executing. On success, it selects the reopened run as the active run.

Usage: `{{R2P_BIN_DIR}}/r2p-reopen --from <work-id> --stage <stage> --reason "<text>"`

Example: `{{R2P_BIN_DIR}}/r2p-reopen --from WF-20260527-login-rate-limit --stage spec --reason "spec gap found"`

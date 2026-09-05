---
description: Reopen a run from a specific stage and archive its direct source
---
Run `{{R2P_BIN_DIR}}/r2p-reopen` to reopen a run that was closed at the PLAN checkpoint or is already executing. On success, it archives the direct source run and selects the reopened run as the only active run in that lineage.

If another active reopened draft already exists in the lineage, stop. Continue that draft or explicitly archive it with `r2p-abandon`; never silently discard it.

Usage: `{{R2P_BIN_DIR}}/r2p-reopen --from <work-id> --stage <stage> --reason "<text>"`

Example: `{{R2P_BIN_DIR}}/r2p-reopen --from WF-20260527-login-rate-limit --stage spec --reason "spec gap found"`

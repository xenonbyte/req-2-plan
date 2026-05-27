# req-to-plan Agent Commands ({{R2P_VERSION}})

Run these commands to operate the requirement-to-PLAN workflow.

Scripts are in `{{R2P_BIN_DIR}}`.

- `r2p-start [--separate] "<requirement>"` — Start a new run
- `r2p-continue` — Continue the active run
- `r2p-status [--all]` — Show status
- `r2p-switch --work-id <id>` — Switch active run
- `r2p-adapt --executor <name>` — Adapt PLAN for executor
- `r2p-reopen --from <id> --stage <stage> --reason "<text>"` — Reopen run

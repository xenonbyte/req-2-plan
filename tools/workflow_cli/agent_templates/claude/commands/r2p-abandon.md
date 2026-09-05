---
description: Explicitly abandon and archive an open requirement-to-PLAN draft
---
Run `{{R2P_BIN_DIR}}/r2p-abandon` only when the user explicitly abandons an open draft.

Usage: `{{R2P_BIN_DIR}}/r2p-abandon --work-id <work-id> --reason "<one-line reason>"`

The command preserves the draft under `.req-to-plan/archive/<work-id>`, records the reason, and clears the active selection when it points to that run. Closed or executing runs must use `r2p-archive` instead.

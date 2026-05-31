---
description: Continue the active requirement-to-PLAN workflow run
---
Run `{{R2P_BIN_DIR}}/r2p-continue` to resume the currently selected run.

Usage: `{{R2P_BIN_DIR}}/r2p-continue`

Behavior:
- Performs safe automatic operations only: eligible entry gates, Quality Gates, bundled checkpoint approval (when all conditions met), stage advancement after non-PLAN checkpoint approval, and run closure after PLAN checkpoint approval
- Stops when human decisions are required: stage content generation, Quality Gate failure, review findings not merged, human checkpoint approval decision needed, route handling needed

Call repeatedly until the output says `stop:` with a message indicating why the run paused. When a stop is reported, use the suggested `workflow ...` command to take the next step. Resume with `r2p-continue` after completing that step.

Use `r2p-status` to inspect progress without making changes.

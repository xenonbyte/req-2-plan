---
description: Continue the active requirement-to-PLAN workflow run
---
Run `{{R2P_BIN_DIR}}/r2p-continue` to resume the currently selected run.

Usage: `{{R2P_BIN_DIR}}/r2p-continue`

Behavior:
- Performs safe automatic operations only: eligible entry gates, Quality Gates, opening checkpoint review (`review-checkpoint`), stage advancement after non-PLAN checkpoint approval, and run closure after PLAN checkpoint approval with no open routes
- Stops when human action is required: stage content generation, marking an artifact ready (`stage-ready`), Quality Gate failure or requested changes (repair), human checkpoint approval (`checkpoint-decide`), entry gate failure
- Stops with `needs_subagent_review` on forced-review runs (a `migration`/`safety`/`cross_project` modifier at `design`/`spec`/`plan`) when the required review file is missing. You are authorized to run a read-only review subagent yourself for this step — no separate human approval is needed
- Does NOT auto-mark artifacts ready and does NOT auto-approve checkpoints

Call repeatedly until the output says `stop:` with a message indicating why the run paused. For `needs_content` and `needs_repair`, write the required artifact content into the printed `content_file`, then run the printed `next:` command exactly. For `needs_subagent_review`, run a review subagent to audit the stage artifact, write its findings to the printed `review_file`, then resume with `r2p-continue` (you do not need to ask for approval to spawn the review subagent). For other stops, run the printed `next:` command exactly. If an `alt:` command is shown, use it only when that alternate decision is intended. Resume with `r2p-continue` after completing that step.

Use `r2p-status` to inspect progress without making changes.

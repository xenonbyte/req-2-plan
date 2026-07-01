---
name: r2p-continue
description: Continue the active requirement-to-PLAN workflow run. Use when the user asks to run r2p-continue, continue r2p, resume the active r2p run, or advance the current requirement-to-PLAN workflow.
---

# r2p-continue

Run `{{R2P_BIN_DIR}}/r2p-continue` to resume the currently selected run.

Usage: `{{R2P_BIN_DIR}}/r2p-continue`

At a checkpoint, only approve a DESIGN/SPEC/PLAN artifact that has no unresolved ambiguity or undecided point: resolve it by evidence, or route it (DESIGN: `### DECISION-NNN`; SPEC/PLAN: `r2p-gap-open`) before approving.

Never defer or drop requirement content while decomposing: everything the brief puts in scope must be implemented this run. The only skippable work is the brief's own `## Out-of-Scope` (SCOPE-OUT-*); to exclude anything else, route it back to the brief — never write "do later / not this round" in a downstream stage (the Quality Gate rejects unanchored deferral).

Call repeatedly until the run reaches the closed state. For `needs_content` and `needs_repair` stops, write the required artifact content into the printed `content_file`, then run the printed `next:` command exactly. For a `needs_subagent_review` stop (forced-review runs: a `migration`/`safety`/`cross_project` modifier at `design`/`spec`/`plan`), run a read-only review subagent to audit the stage artifact yourself — no separate human approval is needed — write its findings to the printed `review_file`, then resume with `r2p-continue`. For other stops, run the printed `next:` command exactly. If an `alt:` command is shown, use it only when that alternate decision is intended. Use `r2p-status` to inspect progress.

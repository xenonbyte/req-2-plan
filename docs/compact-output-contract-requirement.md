# Compact Output Contract Requirement

## Summary

`req-to-plan` should reduce token waste on agent-facing command output without
becoming a general shell proxy. The change is a focused output contract for the
workflow CLI and shortcut surfaces: default human-readable output should be
compact, failure-oriented, and recoverable; machine-readable `R2P_JSON=1` output
must remain complete and stable.

## Motivation

The current output helpers (`format_success`, `format_error`, `format_stop`,
and `format_gate_result`) expand lists and dictionaries directly. That is simple
and predictable, but it can over-spend context when gate failures, status data,
or execution checks produce long issue lists or logs.

The useful lesson from RTK is not global command rewriting. The transferable
mechanism is: summarize the actionable part, preserve exit codes, and provide a
clear path to the full raw detail when truncation happens.

## Goals

- Reduce agent-context noise in common `r2p-*` and workflow CLI outputs.
- Keep failure output actionable: show what blocked progress and the next
  command or file the agent should inspect.
- Preserve full detail through `R2P_JSON=1` and local recovery files or paths
  when human output is truncated.
- Keep the implementation Python-only and dependency-light, matching the current
  runtime constraint of stdlib plus `pyyaml`.
- Preserve the CLI/agent boundary: the CLI formats state and validation facts,
  but still does not generate semantic artifact prose.

## Non-Goals

- Do not add shell hooks, automatic command rewriting, or a proxy layer.
- Do not introduce Rust, SQLite tracking, telemetry, or cross-ecosystem command
  filters.
- Do not change workflow state transitions, artifact schemas, tier semantics, or
  gate rules.
- Do not compact `R2P_JSON=1`; JSON mode remains the full machine interface.
- Do not force ignored `docs/` content into Git unless the maintainer explicitly
  changes the repository policy.

## Target Surfaces

- `tools/workflow_cli/output.py`
  - Shared text formatting helpers.
  - Exit-code preserving output behavior.
- Gate output
  - Entry gate failures.
  - Quality gate failures.
  - Forced subagent review failures.
- Status and resume output
  - `status-run`.
  - `status-next`.
  - `run-resume`.
- Execution output
  - Execution pre-flight failures.
  - Execution completion gate failures.
  - Any surfaced verification or dirty-tree summaries.

## Functional Requirements

### FR1: Compact Human Text by Default

Human-readable output should prefer one-line summaries plus short, grouped
details. Long lists should be capped with a clear count of hidden items.

Example shape:

```text
✗ quality-gate failed: 3 blocking issues, 8 total
  - missing section: Verification
  - unresolved ambiguity: deployment target
  - stale artifact: 06-spec.md v2
  full details: .req-to-plan/<work-id>/logs/quality-gate-<stage>.txt
```

### FR2: Preserve Full JSON Mode

When `R2P_JSON=1`, output must continue to include the complete data currently
available to callers. Compact human formatting must not remove fields from JSON
payloads or change existing exit codes.

### FR3: Recovery Path for Truncation

Whenever human-readable output hides details because of a cap, it must provide a
local recovery path. The path can point to an existing artifact, existing review
file, run-local log, or another deterministic file produced by the command.

Truncation without a recovery path is not acceptable.

### FR4: Failure-First Ordering

Failure output should prioritize blockers over informational details. Gate and
execution failures should show the smallest useful set of actionable issues
first, then counts, then recovery path.

### FR5: No Silent Fallbacks

If compact formatting cannot produce a recovery file when one is required, the
command should still preserve correctness by printing full details rather than
hiding them.

### FR6: Stable Limits

Any caps used by text formatting should be named constants near the formatter or
surface that owns them. Avoid scattered magic numbers.

Initial suggested caps:

- Blocking issues: show up to 5.
- Non-blocking details: show up to 10.
- File lists: show up to 15.

The exact values can change during implementation if tests show the output is
too sparse or still too noisy.

## Acceptance Criteria

- `R2P_JSON=1` output for representative success, error, stop, and gate results
  remains complete and parseable.
- Human-readable gate failures summarize issue counts and cap long details.
- Any capped output includes a recovery path or falls back to full output.
- Existing exit codes remain unchanged.
- Existing docs consistency tests remain green.
- Focused tests cover:
  - short output is not unnecessarily changed;
  - long details are capped;
  - capped details provide recovery;
  - JSON mode bypasses compaction;
  - gate failures preserve `EXIT_GATE_FAIL` / `EXIT_REVIEW_REQ` behavior.

## Expected Benefit

The likely benefit is medium, concentrated in agent-driven workflows:

- Short success/status commands: low token savings, mostly cleaner output.
- Gate failures and long issue lists: moderate savings, roughly 30-60%.
- Execution checks and verbose verification failures: high potential savings
  when recovery files are available, often 60%+.

The change should improve agent efficiency without changing the core product
model.

## Risks

- Over-compaction can hide the detail an agent needs to repair a stage.
- Recovery files can become another state surface if their ownership is unclear.
- Changing shared formatters can affect many commands at once.
- Human-readable output tests may become brittle if they assert too much exact
  prose.

## Implementation Boundaries

Keep the first implementation narrow. Prefer updating shared formatting helpers
and the few output surfaces that demonstrably produce noisy output. Do not add a
new service, database, telemetry, or external command dependency.

If the implementation needs run-local recovery files, store them under the
active `.req-to-plan/<work-id>/` directory and keep them out of global user
state.

## Verification Commands

```bash
.venv/bin/python -m pytest tests/test_output.py -v
.venv/bin/python -m pytest tests/test_docs_consistency.py -v
.venv/bin/python -m pytest tests/ -v
```

# Requirement Brief

## Goal
Deliver a narrow, recoverable compact-output contract for the workflow CLI and
installed `r2p-*` shortcut surfaces so agent-facing human text stops spending
context on long, incidental status/resume lists while preserving complete JSON
mode, exit codes, gate repair checklists, and the CLI/agent responsibility
boundary.

## In-Scope
- SCOPE-IN-001 Human-readable status and resume output from the workflow CLI
  should cap long non-actionable lists and show concise summaries.
- SCOPE-IN-002 Capped human output must expose a deterministic local recovery
  path under the run directory, or print full details if that recovery file
  cannot be produced.
- SCOPE-IN-003 `R2P_JSON=1` output must remain complete, parseable, and
  behaviorally stable for representative success, error, stop, and gate
  results.
- SCOPE-IN-004 Gate failures, forced-review failures, and execution completion
  gate failures must retain full issue lists and existing exit-code behavior.
- SCOPE-IN-005 Formatting caps must be explicit, opt-in, and backed by named
  constants or surface-owned limits rather than hidden global truncation.
- SCOPE-IN-006 Recovery logs created for capped status/resume output must be
  excluded from path-scoped close/archive commits and must not become staged or
  committed run artifacts.
- SCOPE-IN-007 Focused tests must cover compact human output, JSON bypass,
  uncapped failure checklists, recovery-path behavior, decision-bearing fields,
  and git staging/commit exclusion for recovery logs.

## Out-of-Scope
- SCOPE-OUT-001 Adding a shell proxy, command rewriting layer, hooks, telemetry,
  database, Rust component, or cross-ecosystem command filter.
- SCOPE-OUT-002 Changing workflow state transitions, artifact schemas, tier
  estimation/locking, gate rules, or semantic artifact generation boundaries.
- SCOPE-OUT-003 Compacting `R2P_JSON=1` payloads or removing fields currently
  available to machine callers.
- SCOPE-OUT-004 Compacting gate, forced-review, or execution completion gate
  issue lists.
- SCOPE-OUT-005 Changing agent-authored execution output in `r2p-execute`
  templates, including pre-flight, verification command output, and dirty-tree
  summaries.

## Non-Goals
- This work is not a general output redesign for every CLI command.
- This work is not an attempt to optimize token usage at the cost of repair
  quality; actionable blocker lists stay complete.
- This work does not introduce new runtime dependencies beyond the current
  Python runtime constraints.
- This work does not move semantic prose generation into the CLI.

## Assumptions
- The main noisy surfaces are `status-run`, `status-next`, and `run-resume`;
  implementation can stay narrow unless code inspection finds another directly
  equivalent resume/status call site.
- The formatter layer can remain filesystem-unaware; run-local recovery files
  are owned by command handlers that already know the run directory.
- Existing `.req-to-plan` archive/removal behavior can clean up recovery logs if
  they live inside the run directory.
- Tests can use temporary repositories and path-scoped commit helpers without
  touching real user state.

## Acceptance Criteria
- AC-001 Human-readable status/resume output caps long incidental lists, reports
  shown/total counts, keeps the next action and stop/reason fields visible, and
  includes a recovery path when details are hidden.
- AC-002 Short status/resume output remains readable and is not unnecessarily
  changed.
- AC-003 If a recovery file cannot be written when needed, human output falls
  back to full detail rather than silently hiding data.
- AC-004 `R2P_JSON=1` bypasses compaction and keeps complete representative
  payloads for success, error, stop, and gate results.
- AC-005 Gate, forced-review, and execution completion gate failure lists are
  not truncated and preserve `EXIT_GATE_FAIL` / `EXIT_REVIEW_REQ` or existing
  completion-gate exit behavior.
- AC-006 Recovery log files under `.req-to-plan/<work-id>/logs/` are ignored or
  otherwise excluded from path-scoped close/archive commits, and tests prove they
  are not staged or committed.
- AC-007 Caps are named and opt-in per noisy surface or explicit helper call;
  shared formatters do not silently truncate all lists by default.
- AC-008 Existing exit codes remain unchanged and existing docs consistency
  tests stay green.

## Open Questions
- None. The requirement is decision-complete for downstream risk, design, spec,
  and planning stages.

## Sources
- `docs/compact-output-contract-requirement.md`
- `.req-to-plan/WF-20260625-compact-output-contract-requirement/00-raw-requirement.md`
- `.req-to-plan/WF-20260625-compact-output-contract-requirement/02-project-context.md`
- Code evidence: `tools/workflow_cli/output.py`, `tools/workflow_cli/cli.py`,
  `tools/workflow_cli/trace.py`, `tools/workflow_cli/stage_schema.py`

## Trace
<!-- Map this stage's IDs to upstream/downstream. R3 derives & checks closure. -->
| This ID | Upstream | Status |
|---|---|---|
| SCOPE-IN-001 | raw requirement: Target Surfaces, FR1 | defined |
| SCOPE-IN-002 | raw requirement: FR3, FR5 | defined |
| SCOPE-IN-003 | raw requirement: FR2, Acceptance Criteria | defined |
| SCOPE-IN-004 | raw requirement: Target Surfaces, FR4 | defined |
| SCOPE-IN-005 | raw requirement: FR6 | defined |
| SCOPE-IN-006 | raw requirement: FR3, Acceptance Criteria | defined |
| SCOPE-IN-007 | raw requirement: Acceptance Criteria | defined |
| SCOPE-OUT-001 | raw requirement: Non-Goals | defined |
| SCOPE-OUT-002 | raw requirement: Non-Goals | defined |
| SCOPE-OUT-003 | raw requirement: FR2, Non-Goals | defined |
| SCOPE-OUT-004 | raw requirement: Target Surfaces, FR4 | defined |
| SCOPE-OUT-005 | raw requirement: Target Surfaces, Non-Goals | defined |

## Upstream Summary (read-only)
# Compact Output Contract Requirement

## Summary

`req-to-plan` should reduce token waste on agent-facing command output without
becoming a general shell proxy. The change is a focused output contract for the
workflow CLI and shortcut surfaces: human-readable output should be compact where
the detail is non-actionable, failure-first in ordering, and recoverable;
machine-readable `R2P_JSON=1` output must remain complete and stable. Gate and
completion-gate failure issue lists are deliberately never truncated — they are
the agent's repair checklist and preserving them protects req→plan and execution
quality.

## Motivation

The current output helpers (`format_success`, `format_error`, `format_stop`,
and `format_gate_result`) expand lists and dictionaries directly. That is simple
and predictable, but it can over-spend context when status and resume output
carries long, non-actionable lists (e.g. changed-file or artifact listings).
Gate and completion-gate failure issues are deliberately left in full — they are
the agent's repair checklist — so the contract targets only the surfaces where
the agent does not need the long list to act.

The requirement does not borrow a global command-rewriting model. The
transferable mechanism is: summarize the actionable part, preserve exit codes,
and provide a clear path to the full raw detail when truncation happens.

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
- Do not change agent-authored execution output (pre-flight, verification
  command output, dirty-tree summaries) in the `r2p-execute` templates; this
  contract covers CLI-produced output only.
- Do not truncate gate, forced-review, or completion-gate failure issue lists;
  they are the agent's repair checklist and stay complete (failure-first
  ordering only, no caps).

## Target Surfaces

Compaction applies only to output the agent does not need to read in full to act.

- `tools/workflow_cli/output.py`
  - Shared text formatting helpers (home of the opt-in capping helper and named
    caps).
  - Exit-code preserving output behavior.
- Status and resume output — the compaction target
  - `status-run`.
  - `status-next`.
  - `run-resume`.
  - Cap only incidental noise (e.g. long changed-file or artifact lists). Never
    cap a decision-bearing field such as the next action, open routes, or the
    stop reason.

Explicitly NOT compacted — these are the agent's actionable checklist, repaired
from directly; they get failure-first ordering (FR4) but no truncation:

- Gate failures: entry gate, quality gate, forced subagent review — full issue
  list preserved.
- Execution completion gate failures (`check_execution_complete`, formatted by
  the CLI via `format_error`) — full unfinished-task list preserved.

Out of scope entirely: execution pre-flight, verification command output, and
dirty-tree summaries are authored by the `r2p-execute` agent template, not by
`output.py`, so this contract cannot and does not touch them.

## Functional Requirements

### FR1: Compact Human Text by Default

Human-readable output on the compaction target surfaces should prefer one-line
summaries plus short, grouped details. Long non-actionable lists should be capped
with a clear count of hidden items. This applies to status and resume output
only; gate and completion-gate failure issue lists are never capped (see Target
Surfaces and FR4).

Example shape (a status surface with a long, non-actionable list capped):

```text
✓ status-run WF-2026-06-25-abc EXECUTING
  stage: 07-plan (closed)
  changed files: 15 shown, 32 total
    - tools/workflow_cli/output.py
    - tests/test_output.py
    - ...
  full list: .req-to-plan/<work-id>/logs/status-files.txt
  next: r2p-execute
```

### FR2: Preserve Full JSON Mode

When `R2P_JSON=1`, output must continue to include the complete data currently
available to callers. Compact human formatting must not remove fields from JSON
payloads or change existing exit codes.

### FR3: Recovery Path for Truncation

Whenever human-readable output hides details because of a cap, it must provide a
local recovery path. The path can point to an existing artifact, existing review
file, run-local log, or another deterministic file produced by the command.

The recovery file is written by the CLI command handler that holds the run
directory (the status and resume handlers in `cli.py`), not by the pure
formatters in `output.py`, which take only `dict` / `list[str]` and must stay
filesystem-unaware. Recovery files live under `.req-to-plan/<work-id>/logs/`
with a deterministic per-surface name (e.g. `status-files.txt`), are overwritten
on re-run, and are removed with the run on archive (covered by the existing
path-scoped archive commit). They are local runtime state — never global user
state, never committed.

Because close/archive use path-scoped commits for `.req-to-plan/.gitignore` plus
the run directory, recovery logs must be explicitly excluded from those commits.
Use an entry such as `/*/logs/` in `.req-to-plan/.gitignore` (patterns there are
relative to `.req-to-plan/`), or make the path-scoped commit helper omit
`.req-to-plan/<work-id>/logs/`. The chosen implementation must be tested so
capped-output recovery files are not staged or committed.

Truncation without a recovery path is not acceptable.

### FR4: Failure-First Ordering

Failure output should prioritize blockers over informational details. Gate and
completion-gate failures are ordered blockers-first but are **not** truncated —
their full issue list is the agent's repair checklist and must stay complete.
Truncation with a recovery path applies only to the non-failure status and resume
surfaces, and only to incidental noise, never to an actionable issue list.

### FR5: No Silent Fallbacks

If compact formatting cannot produce a recovery file when one is required, the
command should still preserve correctness by printing full details rather than
hiding them.

### FR6: Stable Limits

Any caps used by text formatting should be named constants near the formatter or
surface that owns them. Avoid scattered magic numbers.

Capping is opt-in per surface, not a blanket change to the shared formatters. A
generic cap inside `format_success` would silently hide lists that some callers
intend to show in full, so compaction is applied through a dedicated helper or an
explicit cap argument that each noisy call site chooses to use. JSON mode and
call sites that do not opt in keep their current behavior.

Initial suggested caps (status and resume noise only):

- Non-blocking detail lines: show up to 10.
- File / artifact lists: show up to 15.

The exact values can change during implementation if tests show the output is
too sparse or still too noisy.

## Acceptance Criteria

- `R2P_JSON=1` output for representative success, error, stop, and gate results
  remains complete and parseable.
- Human-readable gate failures keep their full issue list, ordered blockers-first
  (no truncation), and preserve `EXIT_GATE_FAIL` / `EXIT_REVIEW_REQ`.
- Human-readable completion gate failures keep their full unfinished-task list
  and exit code (no truncation).
- Human-readable status and resume output for representative `status-run`,
  `status-next`, and `run-resume` cases caps long non-actionable lists, keeps the
  next action and other decision-bearing fields visible, and provides a recovery
  path or full-output fallback.
- Recovery log files for capped status/resume output are excluded from
  path-scoped close/archive commits and are not staged or committed.
- Any capped output includes a recovery path or falls back to full output.
- Existing exit codes remain unchanged.
- Existing docs consistency tests remain green.
- Focused tests cover:
  - short output is not unnecessarily changed;
  - long status/resume noise is capped;
  - capped status/resume output provides a recovery path or full-output fallback;
  - recovery log files are not staged or committed by the path-scoped
    close/archive commit flow;
  - decision-bearing status fields (next action, open routes) are never capped;
  - JSON mode bypasses compaction;
  - gate and completion-gate failures keep their full issue list (no truncation);
  - gate failures preserve `EXIT_GATE_FAIL` / `EXIT_REVIEW_REQ` behavior.

## Expected Benefit

The likely benefit is low, concentrated in cleaner agent-facing output rather
than large token cuts:

- Status and resume output with long, non-actionable lists: small but reliable
  win — the agent does not need the full list to act, so capping it is close to
  free savings.

Gate and completion-gate failures are deliberately not compacted, so by design
they contribute no savings here — preserving req→plan and execution repair
quality takes priority over their token cost. The larger savings on verbose
execution verification output are out of scope (that output lives in the agent
template, not the CLI).

The change should improve agent efficiency without changing the core product
model or the quality of any gated decision.

## Risks

- Over-compaction could hide detail an agent needs; mitigated by keeping gate and
  completion-gate failure checklists full and capping only non-actionable
  status/resume noise.
- Capping a decision-bearing status field (next action, open routes) would change
  behavior; tests must assert these fields are never capped.
- Recovery files can become another state surface if their ownership is unclear.
- Recovery files under `.req-to-plan/<work-id>/logs/` could be accidentally
  included by path-scoped run commits unless the implementation explicitly
  ignores or excludes them.
- Changing shared formatters can affect many commands at once.
- Human-readable output tests may become brittle if they assert too much exact
  prose.

## Implementation Boundaries

Keep the first implementation narrow. Prefer updating shared formatting helpers
and the status and resume surfaces that demonstrably produce noisy, non-actionable
output. Leave gate and completion-gate failure output untouched except for
failure-first ordering. Do not add a new service, database, telemetry, or
external command dependency.

If the implementation needs run-local recovery files, store them under the
active `.req-to-plan/<work-id>/` directory and keep them out of global user
state.

## Verification Commands

```bash
.venv/bin/python -m pytest tests/test_output.py -v
.venv/bin/python -m pytest tests/test_docs_consistency.py -v
.venv/bin/python -m pytest tests/ -v
```
<!-- /r2p-read-only -->

## Project Context (read-only)
# Project Context Pack

- repo_root: `/Users/xubo/x-skills/req-to-plan`
- languages: {'Python': 19860, 'JavaScript': 31}
- package_managers: npm, pip
- test_commands: ['npm test']
- entrypoints: ['tools/workflow_cli/__main__.py']
- config_files: ['requirements.txt']
- dependencies (1):
  - pyyaml>=6.0 (pip)
- source_dirs: ['bin', 'docs', 'tests', 'tools']
<!-- /r2p-read-only -->

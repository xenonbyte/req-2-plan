---
r2p_stage: risk_discovery
r2p_version: 1
r2p_status: approved
r2p_created_at: 2026-06-24T18:04:51.702105+00:00
r2p_updated_at: 2026-06-24T18:05:18.289504+00:00
---

# Risk Discovery

## Risks
### RISK-FMT-001 Global formatter truncation hides actionable data
Status: mitigated

Changing `format_success`, `format_error`, `format_stop`, or
`format_gate_result` globally could silently cap lists that callers expect to
print in full, especially gate and completion-gate repair checklists.

### RISK-JSON-001 JSON mode contract regression
Status: mitigated

Human text compaction could accidentally alter `R2P_JSON=1` payload fields,
nesting, parseability, or exit-code behavior if text and JSON paths share the
wrong abstraction.

### RISK-GATE-001 Failure checklist truncation weakens repair quality
Status: mitigated

Gate failures, forced-review stops, and execution completion gate failures are
direct agent repair checklists. Any cap applied there would trade correctness
for token savings and directly violate SCOPE-IN-004.

### RISK-LOG-001 Recovery file write failure causes hidden detail loss
Status: mitigated

If a status/resume command decides to hide list entries before it has a usable
run-local recovery file, the user loses detail with no deterministic recovery
path.

### RISK-GIT-001 Recovery logs leak into path-scoped commits
Status: mitigated

Close/archive flows use path-scoped commits under `.req-to-plan/<work-id>/`.
New `.req-to-plan/<work-id>/logs/` recovery files could be staged or committed
unless ignored or explicitly omitted.

### RISK-SCOPE-001 Status/resume compaction expands into unrelated surfaces
Status: mitigated

The requirement is intentionally narrow. Adding caps to unrelated command
surfaces or agent-authored `r2p-execute` output would create behavioral churn
outside SCOPE-IN-001 and SCOPE-OUT-005.

### RISK-TEST-001 Exact prose assertions make output tests brittle
Status: mitigated

Human-readable output tests are necessary but can overfit line-level wording.
They should assert contract-critical facts: capping, counts, recovery path,
decision-bearing fields, uncapped failure details, JSON completeness, and exit
codes.

## Boundaries
- Keep compaction opt-in and surface-owned: status/resume command handlers or
  explicit helper calls choose when to cap.
- Keep pure formatting helpers filesystem-unaware unless a helper only receives
  already-prepared display data.
- Keep recovery files local to `.req-to-plan/<work-id>/logs/`; do not write
  global state or user-home state.
- Keep `R2P_JSON=1` as the complete machine interface.
- Keep gate, forced-review, and execution completion gate issue lists full.
- Keep workflow states, artifact schemas, tier rules, and semantic artifact
  generation unchanged.

## Scope Overflow Risks
- SCOPE-OUT-001 risk: building a generic shell/output proxy would solve a
  broader problem than requested and add operational surface.
- SCOPE-OUT-002 risk: altering gate or state-machine behavior to make output
  compaction easier would turn a formatting contract into workflow semantics.
- SCOPE-OUT-003 risk: compacting JSON would break callers that rely on stable
  machine-readable payloads.
- SCOPE-OUT-004 risk: truncating failure issue lists would remove the exact
  checklist an agent needs to repair artifacts.
- SCOPE-OUT-005 risk: editing `r2p-execute` templates for verification-output
  compaction would conflate CLI-produced output with agent-authored command
  output.

## Mitigations
- MIT-001 for RISK-FMT-001: introduce a dedicated capping/display helper or
  explicit cap argument used only by noisy status/resume surfaces; keep default
  formatter behavior uncapped.
- MIT-002 for RISK-JSON-001: branch JSON output before human compaction and add
  tests that parse representative JSON results and verify complete detail.
- MIT-003 for RISK-GATE-001: add tests proving gate, forced-review, and
  completion-gate failure lists remain full and preserve exit-code behavior.
- MIT-004 for RISK-LOG-001: write the deterministic recovery log before
  returning capped human output; on write failure, print full details and do not
  claim a recovery path.
- MIT-005 for RISK-GIT-001: ignore `/*/logs/` in `.req-to-plan/.gitignore` or
  explicitly omit logs from path-scoped commit helpers; test status and archive
  flows with a generated log file.
- MIT-006 for RISK-SCOPE-001: limit implementation targets to `status-run`,
  `status-next`, and `run-resume` unless code inspection proves another
  equivalent status/resume surface.
- MIT-007 for RISK-TEST-001: prefer structural assertions over full string
  snapshots and keep docs consistency tests in the verification set.

## Trace
<!-- Map this stage's IDs to upstream/downstream. R3 derives & checks closure. -->
| This ID | Upstream | Status |
|---|---|---|
| RISK-FMT-001 | SCOPE-IN-001, SCOPE-IN-005, SCOPE-OUT-004 | mitigated by MIT-001 |
| RISK-JSON-001 | SCOPE-IN-003, SCOPE-OUT-003 | mitigated by MIT-002 |
| RISK-GATE-001 | SCOPE-IN-004, SCOPE-OUT-004 | mitigated by MIT-003 |
| RISK-LOG-001 | SCOPE-IN-002 | mitigated by MIT-004 |
| RISK-GIT-001 | SCOPE-IN-006 | mitigated by MIT-005 |
| RISK-SCOPE-001 | SCOPE-OUT-001, SCOPE-OUT-002, SCOPE-OUT-005 | mitigated by MIT-006 |
| RISK-TEST-001 | SCOPE-IN-007 | mitigated by MIT-007 |

## Upstream Summary (read-only)
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

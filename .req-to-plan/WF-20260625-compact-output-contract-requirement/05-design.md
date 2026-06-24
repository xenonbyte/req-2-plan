---
r2p_stage: design
r2p_version: 3
r2p_status: approved
r2p_created_at: 2026-06-24T18:07:08.770580+00:00
r2p_updated_at: 2026-06-24T18:16:46.336507+00:00
---

# Design

## Design Summary
Add compact human output as an opt-in display contract for the workflow CLI
status/resume surfaces. Keep the existing JSON branches and failure formatters
complete. Command handlers that own a run directory prepare any capped display
data, write run-local recovery logs before hiding details, and fall back to full
human output if recovery log creation fails.

The design is intentionally narrow: it targets `status-run`, `status-next`, and
`run-resume`; it does not add a shell proxy, alter workflow state, or compact
gate/completion-gate repair checklists.

## Current Code Evidence
- `tools/workflow_cli/output.py` currently formats all list/dict values in
  `format_success` by expanding every item; `format_error` and
  `format_gate_result` also print every issue. This explains both the noisy
  status behavior and why failure paths must not receive a blanket cap.
- `tools/workflow_cli/cli.py::_cmd_status_run` sends `open_routes`,
  `open_routes_detail`, `stale_artifacts`, `outstanding_stale`, and
  `approved_checkpoints` directly to `format_success`. Some of these fields are
  decision-bearing and must stay visible.
- `tools/workflow_cli/cli.py::_cmd_status_next` prints the next allowed
  operation and active item; these fields are decision-bearing and should not be
  capped.
- `tools/workflow_cli/cli.py::_cmd_run_resume` prints resume context but does
  not currently include `required_reread_targets`, even though
  `ResumeContext` stores that list. This is the resume-side list most likely to
  need compact human display.
- `tools/workflow_cli/workspace.py::ensure_workspace_gitignore` currently
  requires only `/archive` and `/.workflow-active`; recovery logs need a new
  required ignore pattern.
- `tools/workflow_cli/workspace.py::commit_requirement_dir` stages only
  `.req-to-plan/.gitignore` and `.req-to-plan/<work-id>` via `git add --` and
  never force-adds ignored paths. A `.gitignore` rule for `/*/logs/` is enough
  to keep recovery logs out of path-scoped commits without broadening the
  commit primitive.

## Requirements Coverage
- SCOPE-IN-001 is covered by compact display preparation in status/resume
  handlers.
- SCOPE-IN-002 is covered by run-local recovery logs plus full-output fallback
  on write failure.
- SCOPE-IN-003 is covered by leaving JSON branches complete and adding JSON
  bypass tests.
- SCOPE-IN-004 is covered by keeping `format_error`/`format_gate_result`
  uncapped for gate, forced-review, and completion-gate failures.
- SCOPE-IN-005 is covered by named cap constants and opt-in capped display
  wrappers, not blanket truncation inside `format_success`.
- SCOPE-IN-006 is covered by adding `/*/logs/` to workspace `.gitignore`
  requirements and testing path-scoped commit behavior.
- SCOPE-IN-007 is covered by focused tests for short output, capped output,
  recovery logs, JSON mode, uncapped failures, decision-bearing fields, and
  docs consistency, with structural assertions that address RISK-TEST-001
  [ADDRESSED].

## Options Considered
- Option A: cap all lists inside `format_success`.
  Rejected. It would silently hide details for unrelated success callers and
  would make RISK-FMT-001 [ADDRESSED] likely.
- Option B: add an explicit compact display helper and call it only from
  status/resume handlers.
  Chosen. It keeps the default formatter contract stable while giving noisy
  surfaces a reusable path for shown/total counts and recovery-path metadata.
- Option C: exclude logs by teaching `commit_requirement_dir` to omit
  `.req-to-plan/<work-id>/logs/`.
  Rejected for the initial implementation. The helper already relies on
  path-scoped `git add --` without `-f`; a workspace `.gitignore` rule is
  simpler, testable, and matches existing ignored workspace-state handling.
- Option D: compact failure checklists and rely on recovery logs.
  Rejected. Gate and completion-gate failures are the direct repair checklist
  and must stay fully visible.

## Chosen Design
### DES-ARCH-001 Opt-in Compact Display Helper

Add a small output-layer helper for human text display data, not for semantic
state. The helper accepts a label, a sequence, a cap, and optional recovery path
metadata, then returns display fields such as shown count, total count, visible
items, and full-list path. It is bypassed entirely in `R2P_JSON=1` mode.

Named constants own the initial caps:

- `COMPACT_DETAIL_LIMIT = 10`
- `COMPACT_FILE_LIST_LIMIT = 15`

The default `format_success`, `format_error`, `format_stop`, and
`format_gate_result` behavior remains uncapped unless a caller passes already
compacted display data.

### DES-ARCH-002 Status-Run Field Policy

Update `_cmd_status_run` to keep decision-bearing fields full and visible:

- Never cap `work_id`, `status`, `current_stage`, `tier_locked`,
  `open_routes`, `open_routes_detail`, `stale_artifacts`, or
  `outstanding_stale`.
- Treat long checkpoint/history-style lists, starting with
  `approved_checkpoints`, as incidental status history eligible for capping.
- When capping occurs, write the full list to
  `.req-to-plan/<work-id>/logs/status-run-approved-checkpoints.txt` before
  printing the compact human output.

### DES-ARCH-003 Status-Next Field Policy

Keep `_cmd_status_next` concise and uncapped for current fields because they are
decision-bearing: `next_allowed_operation`, `active_item`,
`last_completed_operation`, and `resume_reason`. If future status-next lists are
added, they must opt into the same helper and must not cap the next action.

### DES-ARCH-004 Run-Resume Reread Targets

Update `_cmd_run_resume` to include `required_reread_targets` from
`ResumeContext` in both JSON and human output. In human output, cap long reread
target lists with a recovery file at
`.req-to-plan/<work-id>/logs/run-resume-reread-targets.txt`. Keep
`next_operation`, `active_item`, and `resume_reason` always visible.

### DES-ARCH-005 Recovery Log Ownership and Fallback

Add a CLI-level helper that writes recovery files under the already-validated
run directory. The handler writes the full list first; only after success does
it print a capped display. If directory creation or write fails, the handler
prints the full list and omits the recovery-path claim.

Recovery logs are deterministic per surface and overwritten on rerun. They are
local runtime state, not artifacts and not global state.

### DES-ARCH-006 Workspace Ignore Rule

Extend `_WORKSPACE_GITIGNORE_LINES` in `tools/workflow_cli/workspace.py` with
`/*/logs/`. Existing `ensure_workspace_gitignore` will append it to current
workspaces. Because `commit_requirement_dir` uses `git add --` without `-f`,
ignored recovery logs under `.req-to-plan/<work-id>/logs/` will not be staged by
path-scoped close/archive commits.

### DES-ARCH-007 Failure and JSON Preservation

Leave failure formatting complete. Gate failures continue through
`format_gate_result` -> `format_error` with full `gate_result.issues`; execution
completion failures continue through `format_error` without capped details.
JSON mode returns complete raw data before compact human display is built.

### DES-ARCH-008 Structural Test Assertions

Test the compact-output contract through structural assertions instead of full
human-output snapshots. Tests should assert the presence of shown/total counts,
recovery paths, uncapped decision-bearing fields, JSON completeness, and full
failure issue lists, while avoiding brittle exact prose checks unless a specific
line is part of the contract. This carries RISK-TEST-001 [ADDRESSED] into the
implementation plan and spec.

## Decision Requests
none

## Rollback
Rollback is file-scoped:

- Revert compact helper additions in `tools/workflow_cli/output.py` if the
  helper causes broad formatting churn.
- Revert status/resume handler changes in `tools/workflow_cli/cli.py` to restore
  previous fully expanded human output.
- Remove `/*/logs/` from `_WORKSPACE_GITIGNORE_LINES` only if recovery logs are
  also removed; otherwise keep it because ignored runtime logs are harmless.
- Delete tests added specifically for compact output only when the feature is
  intentionally rolled back.

Rollback does not require data migration because recovery logs are derived,
run-local, and overwritten on demand.

## Observability
- Human output shows shown/total counts whenever a cap is applied.
- Human output includes the recovery path only after the file was successfully
  written.
- If recovery write fails, the observable behavior is full output with no
  hidden-count/recovery-path claim.
- JSON mode remains the operator path for complete machine-readable detail.
- Tests observe git behavior by creating a recovery log and proving the
  path-scoped close/archive commit path does not stage or commit it.

## SPEC Handoff
- Define behavior contracts for the compact helper, recovery-log write helper,
  status-run field policy, status-next field policy, run-resume reread targets,
  workspace ignore rule, and uncapped failure/JSON behavior.
- Specify exact recovery paths:
  `.req-to-plan/<work-id>/logs/status-run-approved-checkpoints.txt` and
  `.req-to-plan/<work-id>/logs/run-resume-reread-targets.txt`.
- Specify that recovery-log failures trigger full-output fallback.
- Specify that `/*/logs/` is a required `.req-to-plan/.gitignore` line.
- Specify that tests prefer structural assertions over exact prose snapshots,
  carrying RISK-TEST-001 [ADDRESSED] and MIT-007 into the implementation
  contract.
- Specify tests using temporary base paths and the existing venv command style.

## Trace
<!-- Map this stage's IDs to upstream/downstream. R3 derives & checks closure. -->
| This ID | Upstream | Status |
|---|---|---|
| DES-ARCH-001 | SCOPE-IN-001, SCOPE-IN-005, RISK-FMT-001 [ADDRESSED] | chosen |
| DES-ARCH-002 | SCOPE-IN-001, SCOPE-IN-002, RISK-SCOPE-001 [ADDRESSED] | chosen |
| DES-ARCH-003 | SCOPE-IN-001, SCOPE-IN-007 | chosen |
| DES-ARCH-004 | SCOPE-IN-001, SCOPE-IN-002, RISK-LOG-001 [ADDRESSED] | chosen |
| DES-ARCH-005 | SCOPE-IN-002, RISK-LOG-001 [ADDRESSED] | chosen |
| DES-ARCH-006 | SCOPE-IN-006, RISK-GIT-001 [ADDRESSED] | chosen |
| DES-ARCH-007 | SCOPE-IN-003, SCOPE-IN-004, RISK-JSON-001 [ADDRESSED], RISK-GATE-001 [ADDRESSED] | chosen |
| DES-ARCH-008 | SCOPE-IN-007, RISK-TEST-001 [ADDRESSED] | chosen |

## Upstream Summary (read-only)
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

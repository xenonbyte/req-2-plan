---
r2p_stage: spec
r2p_version: 3
r2p_status: approved
r2p_created_at: 2026-06-24T18:18:10.374018+00:00
r2p_updated_at: 2026-06-24T18:26:07.177593+00:00
---

# Spec

## Behavior Contracts
### SPEC-OUTPUT-001 Opt-in Compact Display Helper

The output layer must provide named caps and an opt-in way to represent a long
human-only list as compact display data. The helper must not change the default
behavior of `format_success`, `format_error`, `format_stop`, or
`format_gate_result` for callers that do not opt in.

Required constants:

- `COMPACT_DETAIL_LIMIT = 10`
- `COMPACT_FILE_LIST_LIMIT = 15`

The compact representation must include:

- visible items up to the selected cap;
- shown count;
- total count;
- workspace-relative recovery path when the caller successfully produced one.

This implements DES-ARCH-001 [ADDRESSED].

### SPEC-STATUS-001 Status-Run Compact Human Output

`status-run` human output must keep these fields uncapped and visible:
`work_id`, `status`, `current_stage`, `tier_locked`, `open_routes`,
`open_routes_detail`, `stale_artifacts`, and `outstanding_stale`.

`approved_checkpoints` may be compacted when longer than
`COMPACT_DETAIL_LIMIT`. When compacted, the command must write the full list to
`.req-to-plan/<work-id>/logs/status-run-approved-checkpoints.txt` before
printing the compact human output. The compact output must report shown/total
counts and the workspace-relative recovery path.

This implements DES-ARCH-002 [ADDRESSED].

### SPEC-STATUS-002 Status-Next Decision Fields Stay Full

`status-next` human output must keep `next_allowed_operation`, `active_item`,
`last_completed_operation`, and `resume_reason` visible and uncapped. If future
non-actionable lists are added to `status-next`, they may opt into the compact
helper only when the next action remains visible.

This implements DES-ARCH-003 [ADDRESSED].

### SPEC-RESUME-001 Run-Resume Reread Targets

`run-resume` must include `required_reread_targets` from `ResumeContext` in
both JSON and human output.

Human output may compact `required_reread_targets` when longer than
`COMPACT_FILE_LIST_LIMIT`. When compacted, the command must write the full list
to `.req-to-plan/<work-id>/logs/run-resume-reread-targets.txt` before printing
the compact human output. `next_operation`, `active_item`, and `resume_reason`
must stay visible and uncapped.

This implements DES-ARCH-004 [ADDRESSED].

### SPEC-LOG-001 Recovery Log Write and Fallback

Recovery logs must be written under the already-validated run directory at
`.req-to-plan/<work-id>/logs/`. The command handler must write the recovery log
before hiding details in human output.

If creating the logs directory or writing the recovery file fails, the command
must print the full human list and omit the recovery-path claim. It must not
silently hide details.

This implements DES-ARCH-005 [ADDRESSED].

### SPEC-GIT-001 Workspace Ignore Rule for Recovery Logs

`ensure_workspace_gitignore` must require `/*/logs/` in
`.req-to-plan/.gitignore`, in addition to the existing workspace-state ignore
entries. Existing workspaces must get the line appended without losing existing
content.

Because `commit_requirement_dir` stages `.req-to-plan/.gitignore` and
`.req-to-plan/<work-id>` without `-f`, ignored recovery logs must not be staged
or committed by close/archive path-scoped commit flows.

This implements DES-ARCH-006 [ADDRESSED].

### SPEC-JSON-001 JSON Mode Remains Complete

When `R2P_JSON=1`, success, stop, error, gate, status-run, status-next, and
run-resume payloads must include the full data available to the command. JSON
mode must not include compact human-only shown/total summaries in place of raw
lists and must not drop fields.

This implements DES-ARCH-007 [ADDRESSED].

### SPEC-FAILURE-001 Failure Checklists Stay Uncapped

Gate failures, forced-review failures, and execution completion gate failures
must print their full issue lists in human output and JSON output. Existing exit
codes, including `EXIT_GATE_FAIL` and `EXIT_REVIEW_REQ`, must remain unchanged.

This implements DES-ARCH-007 [ADDRESSED].

### SPEC-TEST-001 Structural Output Tests

Tests must assert compact-output behavior structurally rather than relying on
full human-output snapshots. They must check counts, recovery path presence or
absence, uncapped decision-bearing fields, JSON completeness, full failure issue
lists, and git staging/commit exclusion for logs.

This implements DES-ARCH-008 [ADDRESSED] and carries RISK-TEST-001 [ADDRESSED].

## API / Data / Config Contracts
- `tools/workflow_cli/output.py`
  - Add named cap constants near output formatting code.
  - Add a small opt-in helper for compact human list display. The helper must
    preserve input ordering and must not perform filesystem writes.
  - Keep existing formatter entrypoints and exit-code constants stable.
- `tools/workflow_cli/cli.py`
  - Add a CLI-local recovery-log helper that receives `base_path`, `run_dir`,
    deterministic filename, and full item list; returns a workspace-relative
    path such as `.req-to-plan/<work-id>/logs/<name>.txt` only on successful
    write.
  - Update `_cmd_status_run`, `_cmd_status_next`, and `_cmd_run_resume` only.
  - Include `required_reread_targets` in `run-resume` output.
- `tools/workflow_cli/workspace.py`
  - Extend `_WORKSPACE_GITIGNORE_LINES` with `/*/logs/`.
- Runtime data
  - Recovery logs live under `.req-to-plan/<work-id>/logs/`.
  - Recovery logs are overwritten on rerun.
  - Recovery logs are not stage artifacts and are not global user state.
- Compatibility
  - No new runtime dependency.
  - No workflow state transition, artifact schema, tier, or gate rule change.

## External Documentation Checked
N/A — no external dependencies

Local code evidence was checked via CodeGraph for `output.py`, `cli.py`,
`workspace.py`, `state.py`, and gate/test surfaces.

## Test Matrix
| Test ID | Covers | Expected |
|---|---|---|
| TEST-OUTPUT-001 | SPEC-OUTPUT-001 | Existing callers of `format_success` with short/full lists remain uncapped unless they opt in. |
| TEST-STATUS-001 | SPEC-STATUS-001 | Long `approved_checkpoints` in human `status-run` are capped with shown/total counts and a recovery path. |
| TEST-STATUS-002 | SPEC-STATUS-001 | `open_routes`, `open_routes_detail`, `stale_artifacts`, and `outstanding_stale` remain visible and uncapped. |
| TEST-STATUS-003 | SPEC-STATUS-002 | `status-next` keeps next operation and active item visible and uncapped. |
| TEST-RESUME-001 | SPEC-RESUME-001 | `run-resume` includes `required_reread_targets`; long human lists are capped with recovery path. |
| TEST-LOG-001 | SPEC-LOG-001 | Recovery write failure falls back to full human output and prints no false recovery-path claim. |
| TEST-GIT-001 | SPEC-GIT-001 | `ensure_workspace_gitignore` creates/appends `/*/logs/` without removing existing ignore lines. |
| TEST-GIT-002 | SPEC-GIT-001 | A generated `.req-to-plan/<work-id>/logs/` file is not staged or committed by the path-scoped close/archive commit flow. |
| TEST-JSON-001 | SPEC-JSON-001 | `R2P_JSON=1` status/resume payloads include complete raw lists and parse as JSON. |
| TEST-JSON-002 | SPEC-JSON-001 | Representative success, error, stop, and gate JSON payloads remain complete and parseable. |
| TEST-FAIL-001 | SPEC-FAILURE-001 | Gate and forced-review failures print every issue and preserve `EXIT_GATE_FAIL` / `EXIT_REVIEW_REQ`. |
| TEST-FAIL-002 | SPEC-FAILURE-001 | Execution completion gate failures print every unfinished-task issue and preserve the existing exit behavior. |
| TEST-DOCS-001 | SPEC-TEST-001 | Existing docs consistency tests stay green. |

## Non-goals
- Do not compact `R2P_JSON=1` payloads.
- Do not cap gate, forced-review, or completion-gate issue lists.
- Do not add shell hooks, command rewriting, proxy layers, telemetry, a
  database, Rust code, or new dependencies.
- Do not change workflow state transitions, artifact schemas, tier semantics,
  gate rules, or the CLI/agent prose boundary.
- Do not change agent-authored `r2p-execute` template output.

## PLAN Handoff
- Implement output constants and compact human list helper in
  `tools/workflow_cli/output.py` for SPEC-OUTPUT-001.
- Implement recovery log writing and status/resume display changes in
  `tools/workflow_cli/cli.py` for SPEC-STATUS-001, SPEC-STATUS-002,
  SPEC-RESUME-001, and SPEC-LOG-001.
- Implement workspace ignore update in `tools/workflow_cli/workspace.py` for
  SPEC-GIT-001.
- Add or extend tests in `tests/test_output.py`, `tests/test_cli.py`,
  `tests/test_workspace.py` or the closest existing CLI/workspace test module,
  and `tests/test_docs_consistency.py` as needed.
- Use structural assertions for human output tests and avoid full prose
  snapshots unless the exact line is the contract.
- Verification commands:
  - `.venv/bin/python -m pytest tests/test_output.py -v`
  - `.venv/bin/python -m pytest tests/test_cli.py -v`
  - `.venv/bin/python -m pytest tests/test_docs_consistency.py -v`
  - `.venv/bin/python -m pytest tests/ -v`

## Trace
<!-- Map this stage's IDs to upstream/downstream. R3 derives & checks closure. -->
| This ID | Upstream | Status |
|---|---|---|
| SPEC-OUTPUT-001 | DES-ARCH-001 [ADDRESSED], SCOPE-IN-005 | ready for plan |
| SPEC-STATUS-001 | DES-ARCH-002 [ADDRESSED], SCOPE-IN-001, SCOPE-IN-002 | ready for plan |
| SPEC-STATUS-002 | DES-ARCH-003 [ADDRESSED], SCOPE-IN-001 | ready for plan |
| SPEC-RESUME-001 | DES-ARCH-004 [ADDRESSED], SCOPE-IN-001, SCOPE-IN-002 | ready for plan |
| SPEC-LOG-001 | DES-ARCH-005 [ADDRESSED], SCOPE-IN-002 | ready for plan |
| SPEC-GIT-001 | DES-ARCH-006 [ADDRESSED], SCOPE-IN-006 | ready for plan |
| SPEC-JSON-001 | DES-ARCH-007 [ADDRESSED], SCOPE-IN-003 | ready for plan |
| SPEC-FAILURE-001 | DES-ARCH-007 [ADDRESSED], SCOPE-IN-004 | ready for plan |
| SPEC-TEST-001 | DES-ARCH-008 [ADDRESSED], SCOPE-IN-007, RISK-TEST-001 [ADDRESSED] | ready for plan |

## Upstream Summary (read-only)
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

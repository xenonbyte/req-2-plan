---
r2p_stage: plan
r2p_version: 4
r2p_status: approved
r2p_created_at: 2026-06-24T18:27:50.179350+00:00
r2p_updated_at: 2026-06-24T18:40:13.095688+00:00
---

# Plan

## Tasks
### PLAN-TASK-001 Output Helper and Formatter Regression Tests
Spec References: SPEC-OUTPUT-001, SPEC-JSON-001, SPEC-FAILURE-001, SPEC-TEST-001
Change Type: modify
TDD Applicable: yes
Files:
- tools/workflow_cli/output.py
- tests/test_output.py
Skeleton:
```python
def test_compact_list_display_reports_counts_and_path():
    items = [f"item-{i}" for i in range(20)]
    result = compact_human_list(
        label="approved_checkpoints",
        items=items,
        limit=COMPACT_DETAIL_LIMIT,
        recovery_path=".req-to-plan/WF-test/logs/status-run-approved-checkpoints.txt",
    )
    assert result["approved_checkpoints_shown"] == COMPACT_DETAIL_LIMIT
    assert result["approved_checkpoints_total"] == 20
    assert result["approved_checkpoints_full_list"] == ".req-to-plan/WF-test/logs/status-run-approved-checkpoints.txt"

def test_default_formatters_still_emit_full_lists(monkeypatch):
    monkeypatch.delenv("R2P_JSON", raising=False)
    output = format_success({"items": ["a", "b", "c"]}, message="ok")
    assert "    - a" in output
    assert "    - b" in output
    assert "    - c" in output
```
Steps:
- [ ] Add `COMPACT_DETAIL_LIMIT` and `COMPACT_FILE_LIST_LIMIT` near the output
  helpers.
- [ ] Add a filesystem-free compact-list display helper that preserves input
  ordering and returns visible items, shown count, total count, and optional
  workspace-relative recovery path.
- [ ] Keep `format_success`, `format_error`, `format_stop`, and
  `format_gate_result` uncapped by default.
- [ ] Add structural tests proving compact helper output, default formatter
  behavior, JSON parseability, and full gate/failure issue lists.
- [ ] Close SCOPE-IN-003 [CLOSED], SCOPE-IN-004 [CLOSED],
  SCOPE-IN-005 [CLOSED], and SCOPE-IN-007 [CLOSED] for JSON completeness,
  uncapped failure checklists, opt-in caps, and structural tests.
Verification: `.venv/bin/python -m pytest tests/test_output.py -v` passes.

### PLAN-TASK-002 CLI Status/Resume Recovery Output
Spec References: SPEC-STATUS-001, SPEC-STATUS-002, SPEC-RESUME-001, SPEC-LOG-001, SPEC-JSON-001, SPEC-TEST-001
Change Type: modify
TDD Applicable: yes
Files:
- tools/workflow_cli/cli.py
- tests/test_cli.py
Skeleton:
```python
def test_run_resume_human_caps_reread_targets_with_recovery_file(tmp_path, capsys):
    work_id = "WF-20260625-compact-test"
    invoke(["run-start", "--work-id", work_id, "--requirement", "Compact status output"], base_path=tmp_path)
    record, manager, run_dir = load_for_test(work_id, tmp_path)
    update_resume_context(record, reread_targets=[f"file-{i}.py" for i in range(20)])
    manager.save(record)

    invoke(["run-resume", "--work-id", work_id], base_path=tmp_path)
    out = capsys.readouterr().out
    assert "required_reread_targets" in out
    assert "20 total" in out
    assert ".req-to-plan/WF-20260625-compact-test/logs/run-resume-reread-targets.txt" in out
    assert (run_dir / "logs" / "run-resume-reread-targets.txt").exists()
```
Steps:
- [ ] Add a CLI-local helper that writes full recovery lists under
  `.req-to-plan/<work-id>/logs/` and returns a workspace-relative path only
  after successful write.
- [ ] Update `_cmd_status_run` so human output can cap long
  `approved_checkpoints` history while leaving decision-bearing fields visible
  and uncapped.
- [ ] Keep `_cmd_status_next` decision fields full and uncapped.
- [ ] Update `_cmd_run_resume` to include `required_reread_targets` in JSON and
  human output, compacting long human lists with the deterministic recovery log.
- [ ] Add tests for capped output, short output, fallback-on-write-failure,
  JSON bypass, and uncapped decision-bearing fields.
- [ ] Close SCOPE-IN-001 [CLOSED], SCOPE-IN-002 [CLOSED],
  SCOPE-IN-003 [CLOSED], and SCOPE-IN-007 [CLOSED] for compact status/resume
  output, recovery paths, JSON completeness, and structural tests.
Verification: `.venv/bin/python -m pytest tests/test_cli.py -v` passes.

### PLAN-TASK-003 Workspace Log Ignore and Commit Exclusion
Spec References: SPEC-GIT-001, SPEC-LOG-001, SPEC-TEST-001
Change Type: modify
TDD Applicable: yes
Files:
- tools/workflow_cli/workspace.py
- tests/test_cli.py
- tests/test_workspace.py
Skeleton:
```python
def test_workspace_gitignore_includes_run_logs(tmp_path):
    ensure_workspace_gitignore(tmp_path)
    gitignore = tmp_path / ".req-to-plan" / ".gitignore"
    assert "/*/logs/" in gitignore.read_text(encoding="utf-8").splitlines()

def test_path_scoped_commit_does_not_stage_recovery_logs(tmp_path):
    initialise_git_repo_for_test(tmp_path)
    work_id = "WF-20260625-compact-test"
    run_dir = tmp_path / ".req-to-plan" / work_id
    (run_dir / "logs").mkdir(parents=True)
    (run_dir / "logs" / "status-run-approved-checkpoints.txt").write_text("full list\n", encoding="utf-8")
    ensure_workspace_gitignore(tmp_path)
    commit_requirement_dir(tmp_path, work_id, "chore(r2p): plan compact test")
    staged_or_tracked = git_ls_files_for_test(tmp_path)
    assert f".req-to-plan/{work_id}/logs/status-run-approved-checkpoints.txt" not in staged_or_tracked
```
Steps:
- [ ] Add `/*/logs/` to `_WORKSPACE_GITIGNORE_LINES`.
- [ ] Add tests proving `ensure_workspace_gitignore` creates/appends the logs
  ignore entry without dropping existing entries.
- [ ] Add a git-backed test proving recovery logs under a run directory are not
  staged or committed by `commit_requirement_dir`.
- [ ] Use existing workspace test helpers where available, or define narrow
  local helpers in the test module for git initialization and tracked-file
  inspection instead of relying on undefined global helpers.
- [ ] Include docs consistency verification in the final check set.
- [ ] Close SCOPE-IN-006 [CLOSED] and SCOPE-IN-007 [CLOSED] for recovery-log
  commit exclusion and structural tests.
Verification: `.venv/bin/python -m pytest tests/test_workspace.py -v`, `.venv/bin/python -m pytest tests/test_cli.py -v`, and `.venv/bin/python -m pytest tests/test_docs_consistency.py -v` pass.

## Trace
<!-- Map this stage's IDs to upstream/downstream. R3 derives & checks closure. -->
| This ID | Upstream | Status |
|---|---|---|
| PLAN-TASK-001 | SPEC-OUTPUT-001, SPEC-JSON-001, SPEC-FAILURE-001, SPEC-TEST-001 | ready |
| PLAN-TASK-002 | SPEC-STATUS-001, SPEC-STATUS-002, SPEC-RESUME-001, SPEC-LOG-001, SPEC-JSON-001, SPEC-TEST-001 | ready |
| PLAN-TASK-003 | SPEC-GIT-001, SPEC-LOG-001, SPEC-TEST-001 | ready |

## Upstream Summary (read-only)
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

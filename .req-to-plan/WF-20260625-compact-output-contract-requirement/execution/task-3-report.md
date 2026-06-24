# PLAN-TASK-003 Report

Status: DONE

## Files Changed

- `tools/workflow_cli/workspace.py`
- `tests/test_workspace.py`
- `.req-to-plan/WF-20260625-compact-output-contract-requirement/execution/task-3-report.md`

## Summary

- Added `/*/logs/` to the workspace `.gitignore` contract.
- Added tests proving new workspaces include the run-log ignore entry.
- Added tests proving existing workspace `.gitignore` files receive the new entry without losing existing content.
- Added a git-backed test proving recovery logs under `.req-to-plan/<work-id>/logs/` are not staged or committed by `commit_requirement_dir`.
- Closed `SCOPE-IN-006` [CLOSED].
- Closed `SCOPE-IN-007` [CLOSED].

## Verification

- `.venv/bin/python -m pytest tests/test_workspace.py -v`
  - First red run before implementation: 7 failed, 8 passed.
  - Final run after implementation: 15 passed.
- `.venv/bin/python -m pytest tests/test_cli.py -v`
  - 207 passed.
- `.venv/bin/python -m pytest tests/test_docs_consistency.py -v`
  - 6 passed.

## Concerns

- None.

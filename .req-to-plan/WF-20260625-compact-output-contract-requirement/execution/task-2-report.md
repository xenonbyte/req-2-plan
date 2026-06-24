status: DONE

# PLAN-TASK-002 Report

## Files Changed

- `tools/workflow_cli/cli.py`
- `tests/test_cli.py`
- `.req-to-plan/WF-20260625-compact-output-contract-requirement/execution/task-2-report.md`

## Summary

- Added CLI-local recovery-list writing for compact human output under `.req-to-plan/<work-id>/logs/`.
- Compacted long `status-run` human `approved_checkpoints` output with shown/total counts and a recovery path only after successful log write.
- Added `run-resume` `required_reread_targets` to JSON and human output, with compact human output and deterministic recovery logs for long lists.
- Kept decision-bearing fields uncapped for `status-run`, `status-next`, and `run-resume`.
- Preserved complete JSON-mode raw lists without compact summaries or recovery-log writes.

## Verification

- `.venv/bin/python -m pytest tests/test_cli.py -k "StatusRun or StatusNext or RunResume" -v`
  - Result: 18 passed, 189 deselected.
- `.venv/bin/python -m pytest tests/test_cli.py -v`
  - Result: 207 passed.

## Concerns

- None.

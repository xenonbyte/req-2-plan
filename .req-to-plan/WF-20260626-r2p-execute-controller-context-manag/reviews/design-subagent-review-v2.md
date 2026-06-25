# Design Review v2 — WF-20260626-r2p-execute-controller-context-manag

**Verdict: Approved**

## Scope

This is a **scoped re-review of the F-01 delta only**. v1 (`design-subagent-review-v1.md`) audited the full design and found it clean except one Minor inaccuracy (F-01) in the "Current Code Evidence" section. The author applied the v1-prescribed fix verbatim. This pass verifies only that delta and that nothing regressed; all other v1 conclusions are carried forward unchanged:

- The 11 other verified code-evidence claims (markdown primitives, `_check_plan_task_fields` contiguity at `gates.py:570-571`, `_LEDGER_*` regexes at `gates.py:1201-1202`, `check_execution_complete`/`check_final_review_recorded`/`check_forced_subagent_review`, `read_artifact`/`FileNotFoundError`, `_iter_plan_task_bodies`, installer `glob("tools/r2p-*")`, the docs-consistency test) — still hold.
- The three sanity-check conclusions (shared single-task body boundary; gate-guaranteed contiguous-from-1 numbering; FR-CM3 markers inert to the ledger regexes) — still hold.
- Spec compliance (all five FRs, all six SCOPE-IN items mapped) — still clean.

## F-01 delta verification

The corrected bullet (`05-design.md:26`) now reads:

> `tools/workflow_cli/cli.py` `_cmd_run_execute_start` — its `CLOSED_AT_PLAN_CHECKPOINT`-status precondition (`cli.py:728`, EXIT_CONFLICT otherwise), the `_reject_symlink_or_exit` guard on the exec dir, and `atomic_write_text` for run-dir writes; `plan-task-brief` mirrors this guard shape but checks EXECUTING status.

Cross-checked against the actual handler at `tools/workflow_cli/cli.py:728`:

```python
728	    if record.status != RunStatus.CLOSED_AT_PLAN_CHECKPOINT:
729	        print_and_exit(
730	            format_error( ... exit_code=EXIT_CONFLICT ),
731	            ...
732	            EXIT_CONFLICT,
733	        )
```

- **(a) F-01 correctly resolved.** The guard name now matches the code: `_cmd_run_execute_start` checks `CLOSED_AT_PLAN_CHECKPOINT` (not EXECUTING), at the cited `cli.py:728`, with `EXIT_CONFLICT` on mismatch. ✓
- The distinction is now stated correctly: the *existing* handler guards `CLOSED_AT_PLAN_CHECKPOINT`; the *new* `plan-task-brief` command "mirrors this guard shape but checks EXECUTING status" — consistent with DES-CLI-001's own EXECUTING-only requirement. The earlier v1 ambiguity is gone. ✓
- **(b) No new inaccuracy, no collateral disturbance.** The line cites the correct line number (`cli.py:728`), the correct exit code (`EXIT_CONFLICT`), and still correctly references `_reject_symlink_or_exit` and `atomic_write_text`. The edit is confined to this single bullet; the other evidence bullets (`05-design.md:27-32`) are byte-identical to v1, and no other section of the artifact was touched. ✓

## Findings

No Critical, Important, or Minor findings remain. F-01 is closed; F-02 (the cosmetic `gates.py:301` vs `:300` line reference for `_iter_plan_task_bodies`) was already non-actionable in v1 and is unaffected. The design is clean.

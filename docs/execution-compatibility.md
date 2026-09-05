# Execution compatibility

## Missing runs and damaged execution state

Execution start, progress, prerequisite, and metrics commands return exit `7`
when the pinned lookup of `.req-to-plan/` or the selected run directory finds
no directory. Symlinks, non-directory path components, and unreadable or
malformed run records remain conflicts (exit `6`). A run directory that exists
but lacks `run.md` is damaged state, not a missing run.

Missing execution recovery files remain conflicts. The execution-start command
continues to return exit `7` specifically for a missing `07-plan.md`. Invalid
structured metrics input still returns exit `2`; metrics observations do not
become execution authority through error-code normalization.

## Historical self-host ledger

The original `WF-20260829-r2p-execute-token-phase-r2p` run began before complete
metrics instrumentation. Its schema-1 ledger records
`instrumentation_complete: false` and
`bootstrap_gap: execution_start_through_task_002_reviewed_complete`. These
facts remain visible after finalization and archival.

All work-ID decisions in `execution_metrics.py` use
`_is_historical_self_host`. The match is exact: reopened descendants and new
runs use ordinary prerequisite and metrics rules. `_is_self_host_partial`
additionally checks the recorded instrumentation gap before applying partial
observation rules.

The current compatibility policy is:

- Preserve parsing of historical archived ledgers without rewriting their
  bytes, header identity, or missing-observation evidence.
- Retain the narrowly scoped bootstrap/retry path and prerequisite guards for
  existing copies of the original run. Do not extend this exception to another
  run or introduce an implicit migration during read, resume, or validation.
- Exclude the original run from representative samples, including after its
  metrics are finalized and its run is archived.

Archival alone is not a removal condition. Retiring the writer/recovery path
requires an explicit decision to end recovery support for unfinished copies,
plus a documented upgrade path. Retiring the parser exception additionally
requires either an explicit end to schema-1 read support or an opt-in migration
that preserves the original identity, incomplete-instrumentation evidence,
and representative-sample exclusion. Verify either transition against archived
ledger fixtures and bootstrap retries before deleting the compatibility code.

No migration or support cutoff is introduced by this cleanup.

## Representative sample validation

`execution-samples-validate` remains the active validator for archived sample
directories and emits the canonical audit result. The unused
`consume_accepted_sample_evidence` API and its private duplicate validators
have been removed. Saved validation results remain audit output; they are not
inputs that authorize execution, progress, resume, or archival.

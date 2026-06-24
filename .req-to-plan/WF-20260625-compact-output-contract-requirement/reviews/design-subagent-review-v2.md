# Design Subagent Review v2

Reviewer: read-only subagent `Poincare`
Artifact: `05-design.md`
Stage: design

## Findings

### Medium: RISK-TEST-001 is not carried into design handoff/trace

Location: `05-design.md` around the Requirements Coverage, SPEC Handoff, and
Trace sections.

Problem: upstream `04-risk-discovery.md` defines `RISK-TEST-001` for brittle
human-readable output tests and mitigation `MIT-007`, but the design only says
"focused tests" and does not explicitly carry that risk into `SPEC Handoff` or
the design trace.

Required repair: add the `RISK-TEST-001` mitigation to the design handoff and
trace it from an existing or new design item. The spec should be instructed to
prefer structural assertions over exact prose snapshots.

## Non-Blocking Observations

- Standard design headings are present.
- `Decision Requests` correctly states `none`.
- The implementation direction is feasible against local code evidence:
  `required_reread_targets` exists in `ResumeContext`, `_cmd_run_resume`
  currently omits it, and `.gitignore`-based recovery-log exclusion matches
  `commit_requirement_dir` behavior.
- `status-run` compaction mainly targets `approved_checkpoints`, which appears
  bounded by workflow stages, so actual savings may be modest; this is not
  blocking because the design remains narrow and recoverable.

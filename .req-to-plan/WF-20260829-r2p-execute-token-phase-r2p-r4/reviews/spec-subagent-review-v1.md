# SPEC v1 Revision Review

## Verdict

APPROVED

## Findings

None. The reopened-delta exception is deliberately narrow and does not weaken the normal prerequisites or the execution gates.

## Ambiguity

None material to implementation. The manual bootstrap is an explicit controller checklist, rather than an attempt to reuse an incompatible v1 command: it requires accepted current-run sample evidence, one unchecked delta task, exactly one strict profile line, no escalation/markers, a full dynamic Execution BASE equal to HEAD, and the fixed source snapshot check. Every mismatch blocks both dispatch and source mutation; the handoff separately prohibits changing the ledger to manufacture eligibility.

## Evidence

- `06-spec.md:72, 78-80, 324-339` makes the reopened run a one-task, modify-only delta; preserves the original Task 001-008 results without replay, no-op source commits, or copying the old ledger; binds it to both the fixed source snapshot and the newly recorded full Execution BASE; and requires the sample validator before any role dispatch or source mutation.
- The stated reason not to call v1 is correct. `execution_metrics.py:668-679` shows every `run-execute-start` ledger receives `Execution Profile: <profile>`. Although v1 generally permits a single `strict` profile line (`:884-890`), its Task 001 branch rejects any profile line as part of the legacy untouched-ledger preflight (`:906-910`). Thus a reopened strict start cannot satisfy v1 Task 001 without changing the ledger, which the SPEC expressly forbids.
- The manual bootstrap retains fail-closed boundaries: `06-spec.md:80` requires status, plan/ledger shape, strict profile cardinality, absence of fast/complete state, dynamic BASE/HEAD equality, source snapshot equality excluding workflow artifacts, and accepted evidence; any mismatch forbids dispatch/mutation. It is scoped solely to this approved reopened delta and leaves v1 and future v2 generation rules intact.
- Existing self-hosted bootstrap behavior remains distinct: the approved design at `05-design.md:66-68` limits its partial metrics gap to Tasks 001-002, starts measurement at Task 003, rejects malformed/foreign retry state without overwrite, and permanently excludes that run from representative samples. `06-spec.md:32-44, 63` retains the three strict archived-sample gate, revalidation on the reopened run, no sample rediscovery/replacement, and no replay of evidence from the original run.
- `execution_metrics.py:865-934` confirms v1 is read-only and returns strict semantics; the proposed delta is responsible for the v2 upgrade while preserving v2-requested-v1 behavior as specified in `06-spec.md:76-78`.

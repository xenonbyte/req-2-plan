Verdict: Approved

## Summary

The DESIGN is accurate, gate-correct, complete, and scope-clean. All five grounding
claims were verified against the real code (and the load-bearing regex/gate behavior
was reproduced empirically): Option A's optional-section seed path is sound and the
seeded `## Risk Handling` row / optional fields clear every PLAN-gate check, the two
`r2p-execute` surfaces match the EXE-1..EXE-5 fix targets exactly, and no existing
docs-consistency guard forbids a token EXE-1..EXE-5 would introduce. Coverage of
SCOPE-IN-001..012 is complete with no orphans, all six RISK-* carry same-line
`[ADDRESSED]` tags, every SCOPE-OUT item is honored, and `## Decision Requests: none`
is correct. No Critical or Important findings; two Minor observations below are
non-blocking.

## Findings

### Critical
None.

### Important
None.

### Minor

1. **AC-4 round-trip test will need a fully consistent upstream fixture, not just a
   rendered template.** (`tools/workflow_cli/gates.py:1005-1020`, `tools/workflow_cli/trace.py:274-282`)
   For the "minimally-filled seeded PLAN passes the gate" test (DES-SEEDTEST-001), the
   seed's `Spec References: SPEC-BEHAVIOR-001` means the fixture's SPEC artifact must
   *define* SPEC-BEHAVIOR-001 and every defined SPEC must be consumed
   (`spec_ids_not_consumed`), every brief SCOPE-IN must be carried into a PLAN-TASK
   (`scope_in_not_closed`), and every upstream RISK must be closed in 04
   (`risk_ids_not_closed`); standard tier additionally requires a usable Context Pack
   (`_check_plan_context_pack`) and real `Files` paths (`_check_plan_file_refs`). This
   is correct test-authoring altitude for a DESIGN — flagging only so the PLAN/SPEC
   pins the fixture shape (or uses LIGHT tier, which skips the Context Pack and file-ref
   checks since `_check_plan_file_refs` returns `[]` when no pack is present). Not a
   design defect.

2. **DES-GUARD-001 defers the exact guard-token literals to the PLAN, which is where
   RISK-DRIFT-001 is actually discharged.** (`05-design.md:71,95`; `04-risk-discovery.md:13-15`)
   The design correctly states the constraint ("a distinctive literal absent from both
   templates before the edit") but cannot fix the strings until the prose exists. That
   is appropriate, but it means the loose-token failure mode RISK-DRIFT-001 names is not
   closed by the design itself — the PLAN/implementation must verify each chosen token
   is genuinely absent from both surfaces pre-edit. Worth an explicit PLAN check; no
   design change required.

## Grounding checks

| # | Claim | Verified | Evidence |
|---|---|---|---|
| 1 | `template_for` emits only `required_headings(...)` bodies + `_TRACE_SKELETON`, no optional path; Option A (per-stage `_OPTIONAL_SECTIONS` appended before trace skeleton) is sound and minimal | TRUE | `stage_templates.py:60-67` iterates `required_headings` only, appends `_TRACE_SKELETON`; no optional path exists. `heading_bounded_bodies` (`markdown.py:151-178`) bounds a `### PLAN-TASK` (L3) body at the next `<=`-level heading, so a `## Execution Readiness` (L2) inserted after `## Tasks`/before `## Trace` cleanly terminates the last task body. Option A is the minimal additive fix. |
| 2 | `STAGE_SCHEMA[Stage.PLAN] == ["## Tasks"]` and `PLAN_TASK_FIELDS` is a fixed 7-tuple; design must change neither | TRUE | `stage_schema.py:47-51` (both tiers `["## Tasks"]`), `stage_schema.py:6-14` (7-field tuple). Design Boundaries (`05-design.md:140`) and Options Considered Option B rejection (`05-design.md:60`) explicitly keep both unchanged. |
| 3 | Seeded `\| RISK-EXAMPLE-001 \| PLAN-TASK-001 \| [ADDRESSED] \|` clears Check 3 closure AND the malformed-ID check; optional content does not trip placeholder/duplicate/PLAN-TASK-field checks; optional sections after `## Tasks` terminate the last PLAN-TASK body | TRUE | Reproduced empirically: candidates `RISK-EXAMPLE-001`,`PLAN-TASK-001` both pass `_VALID_TRACE_ID_RE.fullmatch` (no malformed-ID issue, `gates.py:912-918`); `_find_ids_without_closure` returns `[]` because `[ADDRESSED]` is same-line (`gates.py:151-178`); `_find_duplicate_ids` returns `[]` (cell IDs aren't heading-context, `gates.py:181-188`); `PLAN-TASK-NNN` yields zero candidates (no digit) so PLN-2 is safe; example Execution Readiness checklist, PLN-5 comment, 3-part Verification, and `Out-of-Task` seed all return zero placeholder hits (`_PLACEHOLDER_PATTERNS`, `gates.py:101-114`). `RISK-EXAMPLE-001` never enters `model.defined` (it's in a cell, not a heading), so `risk_ids_not_closed`/`check_trace_closure` are unaffected (`trace.py:168-181,274-282`). |
| 4 | §1 omits `Files` (EXE-3); clean-tree check only before Task 1 (EXE-2); ACS excludes `07-plan.md` and EXE-1 must not copy that exclusion to final review; report contract has no internal sections (EXE-5); `## Durable Progress` resumes only the final-review Execution BASE, not a mid-task BASE (EXE-4) | TRUE | claude `r2p-execute.md:110` / codex `SKILL.md:111` list `Skeleton, Steps, Spec References, Verification` and omit `Files`. Clean-tree check only at `r2p-execute.md:23` ("Before task 1"). ACS exclusion at `r2p-execute.md:61` / `SKILL.md:62`; `## Final Whole-Branch Review` (`r2p-execute.md:190-208`) does not currently read `07-plan.md`/the ACS. Implementer return contract (`r2p-execute.md:123-130`) and report path (`:121`) specify no internal report sections. `## Durable Progress` (`r2p-execute.md:222-225`) resumes only the `Execution BASE:` line; §2 `:114` "Record BASE (`git rev-parse HEAD`)" would capture fresh HEAD on resume — exactly what EXE-4 corrects. Both surfaces are structurally identical. |
| 5 | No existing test forbids an EXE-introduced token; the ACS guard does not forbid `07-plan.md` whole-file; adding "read 07-plan.md" to the final-review section does not break `test_execute_surfaces_hand_authoritative_context_set` or the reviewer-defer contract test | TRUE | `test_docs_consistency.py:421-424` whole-file forbidden set is only `Scene-setting context` + `` `r2p-gap-open` `` — not `07-plan.md`. The 07-plan.md-sensitive logic (`:454-489`) is scoped to the `## Authoritative Context Set` block, which terminates at the next `## ` (= `## Per-Task Loop`, well before `## Final Whole-Branch Review`); its `assertNotIn` only covers `read_set_portion` inside that block. EXE-1 adds 07-plan.md to the final-review section, outside the block. The reviewer-defer forbidden tokens (`:199-201`) are stale handoff strings EXE-1/EXE-3 do not introduce. Baseline confirmed: `pytest tests/test_docs_consistency.py` = 17 passed. |

## Ambiguity / decisions

No unresolved ambiguity or undecided point remains. The design's `## Decision Requests`
is `none` and that is correct: every choice was settled upstream and is recorded with
rationale in `## Options Considered` — Option A vs B/C for the seed mechanism, the
after-`## Tasks`/before-`## Trace` placement, the PLN-2/3/5 shapes, and the EXE-4
derive-on-resume (Option B over the SCOPE-OUT-001 Option A). The two deferrals that
exist are legitimate design-altitude hand-offs, not open questions: (a) the exact
guard-token literals are finalized in the PLAN against as-yet-unwritten prose
(`05-design.md:95`), and (b) the SPEC will pin one `SPEC-*` per EXE behavior
(`05-design.md:93-97`). Neither is a human decision left open; both are normal
downstream-stage responsibilities the design correctly names.

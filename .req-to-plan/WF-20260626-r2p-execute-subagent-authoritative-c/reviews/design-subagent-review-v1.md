# Design Subagent Review (v1)

## Verdict

**Approved** — no blocking issues.

Every functional requirement (FR-AC1..AC7) maps to a faithful DES item, every
"Current Code Evidence" claim was independently confirmed against the current tree,
the rejected bundle/manifest alternative is recorded with correct rationale, and the
design preserves the two load-bearing invariants this work must not break (FR-CM5
"no whole-plan read" and the audit-only boundary). `Decision Requests: none` is
justified — the requirement is decision-complete. Four non-blocking observations for
SPEC to close, all about phrasing precision, not design soundness.

## Blocking findings

None.

## Non-blocking observations

1. **§6 rework must preserve existing guarded tokens (SPEC must pin this).**
   `tests/test_docs_consistency.py::test_execute_surfaces_route_reviewer_findings_through_report_paths`
   (test_docs_consistency.py:200-218) asserts both surfaces contain the **exact**
   strings `Pass the `review_report_path` to the fix subagent` and `Fix all Critical
   and Important findings in the review report`. DES-DISP-001 adds the task-brief and
   refreshed-diff paths to the §6 fix dispatch; SPEC must word that addition so these
   two tokens survive verbatim, or the existing test fails. The design does not
   contradict this (it says "keep 'do not paste the finding bodies'"), but it does
   not call out the two report-path tokens explicitly — flag so SPEC does.

2. **Per-role heading-slice boundaries need precise definition in SPEC.** DES-TEST-001
   slices the §2/§5/§6 bodies "by their `### ` headings." Verified both surfaces use
   `### 2. Dispatch a fresh implementer subagent`, `### 5. Write diff and dispatch
   task-reviewer`, and `### 6. Fix loop`. But the loop interleaves `### 3.` and
   `### 4.` between §2 and §5, and §6 is terminated by the next `## ` heading
   (`## Final Whole-Branch Review`), not a `### `. SPEC must state that each role
   slice runs from its `### N.` heading to the next `### ` **or** `## ` heading, so
   the §6 slice does not bleed into the final-review section or stop short. This is
   the "light per-role check" FR-AC7 intends; just pin the boundary rule so the
   helper is unambiguous.

3. **"Scene-setting context" removal is safe — confirmed unguarded.** Independently
   verified: the string `Scene-setting` appears in no test (`grep -rn Scene-setting
   tests/` → none), and the guarded SDD token tuple
   (test_docs_consistency.py:81-106) does not reference it. DES-DISP-001's removal of
   that line breaks no existing assertion. No action; recorded as positive evidence.

4. **Shared-block placement is left to SPEC (acceptable).** The design specifies the
   block's *content* and that all three roles *reference* it, but not the block's
   physical location in each template (e.g. a top-level `## Authoritative Context Set`
   section the §2/§5/§6 bodies point to). That is a SPEC/PLAN authoring choice, not a
   design gap; flagged so SPEC fixes one location and one reference idiom to keep the
   per-role slice assertion (observation 2) cheap.

## Evidence checked

Confirmed by direct Read of the current tree:

- **`claude/commands/r2p-execute.md`** — §2 implementer dispatch bullets at
  `:60-65` include the ad-hoc line `Scene-setting context (project, dependencies,
  architectural constraints)` (`:62`) and `Global Constraints … copied verbatim when
  present` (`:63`); §5 reviewer dispatch at `:98-103` hands `brief_path`, report
  path, `logs/task-N-diff.md` path, review path, and pasted Global Constraints; §6
  fix loop at `:118-128` hands **only** `review_report_path` and re-dispatches the
  task-reviewer (`:121`) **without** regenerating `logs/task-N-diff.md`. All three
  Current-Code-Evidence claims in the design are accurate.

- **`codex/skills/r2p-execute/SKILL.md`** — same `## Per-Task Loop` structure with
  §2 at `:57`, §5 at `:95`, §6 at `:119`; the `Scene-setting context` line is present
  at `:63`. The design's "both surfaces share the structure" premise holds, so the
  both-surface assertion (DES-TEST-001) is well-founded.

- **`test_docs_consistency.py::TestExecuteTemplateContent`** — drives both surfaces
  from a shared `surfaces` list with a `required` token tuple (`:76-113`) and a
  `r2p-gap-open` absence guard (`:115-131`); DES-TEST-001 extends this exact shape.
  The report-path test (`:200-218`) is the source of observation 1.

- **Fixed-name artifact constants** — `models.py:83-88`, `context_pack.py:169-170`
  (the set's filenames are constants, so handing paths is a bounded, non-compounding
  per-dispatch addition, matching the leak-hierarchy rationale).

- **`02-project-context.md` is planning-time** — generated once at run-start
  (`cli.py:348-349`), not per task; the design's baseline-vs-working-tree rule
  (DES-AUTH-001) correctly accounts for this.

- **Ledger seeding** — `cli.py:762` seeds `- [ ] PLAN-TASK-NNN <title>` per anchor,
  so DES-OWN-001's "ownership from the ledger ID+title list" is achievable without
  the whole plan.

### Assessment against the check items

1. **FR coverage — faithful, nothing dropped.** FR-AC1→DES-ARCH-001,
   FR-AC2→DES-AUTH-001, FR-AC3→DES-READ-001, FR-AC4→DES-OWN-001, FR-AC5→DES-PATH-001,
   FR-AC6→DES-DIFF-001, FR-AC7→DES-TEST-001. Requirements-Coverage table and Chosen
   Design agree. ✓
2. **Code-evidence claims true.** All confirmed above; only the phrasing items in the
   observations remain for SPEC. ✓
3. **FR-CM5 preserved.** DES-OWN-001 excludes `07-plan.md`, derives ownership from the
   ledger, and routes unclear boundaries through a single-task `r2p-task-brief --task
   <M>` brief — no whole-plan read reintroduced. ✓
4. **Audit-only boundary preserved.** DES-ARCH-001 is paths-only; no bundle,
   `context-manifest.json`, sha256/hash, or drift gate; out-of-band source mutation
   stays a trust assumption. Matches `r2p-execution-gate-boundary`. ✓
5. **Conflict handling fails closed.** DES-AUTH-001 returns `BLOCKED` + human
   **reopen**, never `r2p-gap-open`; the docs guard stays green. ✓
6. **Scope discipline.** Only the two template surfaces + the one test are touched;
   gemini `.toml`, CLI, gates, state, schema, and wrappers are out of bounds
   (SCOPE-OUT-001/002/003 honored). ✓
7. **Decision Requests: none — justified.** No hedge lacks a decision; every choice
   is recorded in Options Considered with its rejected alternative. ✓
8. **Rollback/Observability sound.** Pure prose+test → single `git revert`; the
   docs-consistency test is the regression detector; runtime failures surface via
   `BLOCKED`/`NEEDS_CONTEXT` and progress-ledger adjudication. ✓

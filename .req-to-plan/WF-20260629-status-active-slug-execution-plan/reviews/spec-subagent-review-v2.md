Verdict: Approved

## Summary

The SPEC (`06-spec.md`) faithfully implements all four DES components from
`05-design.md`, closes all twelve SCOPE-IN items exactly once, and hands off
three contiguously-numbered PLAN tasks that consume every SPEC-* ID with
complete, non-overlapping SCOPE-IN carry assignments. Every load-bearing
gate-correctness claim for the Batch-2 seed contract was verified against the
real `gates.py` / `trace.py` / `stage_templates.py` / `stage_schema.py` code and
holds true: the seeded `## Risk Handling` example row clears Check 3 closure, is
well-formed under `_VALID_TRACE_ID_RE`, is never counted as a duplicate heading
definition, and never enters `build_trace().defined` (so it cannot produce a
false "risk not closed"). The optional sections placed after `## Tasks` correctly
terminate the last `### PLAN-TASK` body via `heading_bounded_bodies`. The SPEC
correctly asserts no change to `STAGE_SCHEMA` / `PLAN_TASK_FIELDS` / gates / state
/ CLI, and the EXE-1..5 contracts faithfully restate the requirement, including
the three sharp invariants (per-task ACS `07-plan.md` exclusion preserved; no
`HEAD~1` / no fresh-from-HEAD on resume; no Context-Read checklist). The only
deferral is the legitimate "exact guard-token literals finalized in the PLAN."
Findings are all Minor / informational; none blocks approval.

## Findings

1. **Minor — PLAN Handoff uses unpadded `PLAN-TASK-1/2/3` notation**
   `06-spec.md:101-104` and the Trace `Status` column (`:110-117`, e.g. "consumed
   by PLAN-TASK-3") use the unpadded form, while the seeded template and the
   `### PLAN-TASK-001` heading convention are zero-padded. Both forms are
   gate-valid IDs (`_VALID_TRACE_ID_RE` accepts `^PLAN-TASK-\d+$`, verified
   `gates.py:122-124`), so there is zero gate impact; this is a pure notation
   note. The actual PLAN artifact will define `### PLAN-TASK-001` headings.
   Recommendation: no change required; optionally standardize on the padded form
   in the PLAN for readability.

2. **Minor / heads-up — AC-4 fixture must also satisfy `_check_plan_file_refs` (R5.3)**
   `06-spec.md:62` names four fixture ingredients (SPEC defined+consumed, carried
   SCOPE-IN, closed risks, usable Context Pack). The standard-tier PLAN gate also
   runs `_check_plan_file_refs` (`gates.py:439-475`): a `Change Type: modify`
   PLAN-TASK must list a `Files:` path that *exists* under the Context Pack
   `repo_root` (or use `Change Type: create` with a not-yet-existing path). The
   SPEC's "fills the required `## Tasks` minimally" + "usable Context Pack" covers
   this at SPEC altitude, and `tests/test_gates.py::_gate` (line 1434) plus the
   PLAN-gate tests at `tests/test_gates.py:1257+` are direct precedent. Not a SPEC
   defect. Recommendation: the PLAN-TASK-2 implementer should point the minimal
   task's `Files` at an existing temp-repo path (or use `create`).

3. **Minor / informational — PLN-2 optional fields fold into the preceding field body**
   `06-spec.md:55` seeds `Out-of-Task:` / `Future Task Ownership:` as optional
   lines inside the PLAN-TASK body, correctly kept out of `PLAN_TASK_FIELDS`.
   Because `_plan_task_field_body` (`gates.py:273`) bounds a field only at the next
   recognized `PLAN_TASK_FIELDS` line, any such optional line trailing the last
   real field (typically `Verification:`) is folded into that field's body and is
   then seen by `_check_plan_task_verification_placeholders` (`gates.py:631-641`)
   and the whole-artifact placeholder scan (`gates.py:927-934`). The SPEC's
   "gate-clean illustrative values" requirement (`:55`, `:58`) already covers this.
   Recommendation: in the PLAN, keep those illustrative values placeholder-free
   and use the digit-less `PLAN-TASK-NNN` form (which `_TRACE_ID_CANDIDATE_RE`,
   requiring a `\d`, deliberately ignores — verified `gates.py:125-129`).

## Trace closure

| Check | Result | Evidence |
|---|---|---|
| 1. Every DES component implemented by ≥1 SPEC, each DES ref same-line `[ADDRESSED]` | PASS | DES-EXEC-001 → SPEC-EXE-001..005 (`:14,19,25,31,38`); DES-GUARD-001 → SPEC-GUARD-001 (`:44`); DES-SEED-001 → SPEC-SEED-001 (`:51`); DES-SEEDTEST-001 → SPEC-SEEDTEST-001 (`:61`). Each "Implements DES-… [ADDRESSED]" on the same line. |
| 2. Every SCOPE-IN-001..012 closed by exactly one SPEC, no orphan/double-claim | PASS | 001→EXE-001, 002→EXE-002, 003→EXE-003, 004→EXE-004, 005→EXE-005, 006→GUARD-001, 007-011→SEED-001 (`:51`), 012→SEEDTEST-001 (`:61`). Matches Trace table `:110-117`. All 12 present once. |
| 3. Every SPEC-* consumed by exactly one PLAN-TASK; SCOPE-IN carry complete + non-overlapping; tasks contiguous from 1 | PASS | PLAN-TASK-1→SEED-001 (SCOPE-IN-007..011); PLAN-TASK-2→SEEDTEST-001 (SCOPE-IN-012); PLAN-TASK-3→EXE-001..005+GUARD-001 (SCOPE-IN-001..006) (`:102-104`). 8 SPECs each consumed once; SCOPE-IN 001-012 partitioned with no overlap; tasks numbered 1,2,3. |

Additionally (Check 4 — SPEC's own trace IDs gate-clean): every DES ref carries
`[ADDRESSED]` on a behavior-contract line, so `_find_ids_without_closure`
(`gates.py:151-178`, per-ID anywhere-on-a-line search) is satisfied even though
the Trace-table rows are untagged; `RISK-EXAMPLE-001` on `:54` carries same-line
`[ADDRESSED]`; SCOPE-IN/SCOPE-OUT and PLAN-TASK refs are exempt from closure
(`_UPSTREAM_ID_PATTERN` is REQ/RISK/DES/SPEC only, `gates.py:117-119`); all IDs,
including `PLAN-TASK-1/2/3`, fullmatch `_VALID_TRACE_ID_RE`. No untagged upstream
ref would trip Check 3.

## Gate-correctness

**Check 5 — seeded `## Risk Handling` row `| RISK-EXAMPLE-001 | PLAN-TASK-001 | [ADDRESSED] |` is genuinely gate-clean: VERIFIED TRUE.**
- Check 3 closure satisfied: `_find_ids_without_closure` (`gates.py:151-178`)
  builds the pattern `re.escape(id)+"[^\\n]*"+re.escape(tag)`; on the row line
  `RISK-EXAMPLE-001 … [ADDRESSED]` matches, so `has_closure=True`. `PLAN-TASK-001`
  is not in `_UPSTREAM_ID_PATTERN`, so it needs no closure.
- Both IDs well-formed: `_VALID_TRACE_ID_RE` (`gates.py:122-124`) — `RISK-EXAMPLE-001`
  matches `RISK-[A-Z]+-\d+`; `PLAN-TASK-001` matches `^PLAN-TASK-\d+$`. The R2.3b
  scan (`gates.py:913-918`) finds them as candidates and they fullmatch → no
  malformed-ID issue.
- Not a duplicate heading definition: `_find_duplicate_ids` and `_find_defined_ids`
  (`gates.py:181-188`, `:145-148`) only count IDs in `^#{1,6}` heading lines; the
  row lives in a table cell.
- Not entering trace-closure `defined`: `build_trace` (`trace.py:184-194`) sources
  `defined` from `_native_heading_ids` (heading-only, `trace.py:56-67`) and brief
  scope bullets. PLAN's native prefix is `PLAN-TASK-` only (`trace.py:21-27`), and
  the RISK ID is in a cell — so `RISK-EXAMPLE-001` is never in `defined`, and
  `risk_ids_not_closed` (`trace.py:168-181`, which reads RISK Status only from the
  RISK_DISCOVERY artifact) never sees it. No false "risk not closed".

**Check 6 — placement after `## Tasks` / before `## Trace` terminates the last task body and trips no scan: VERIFIED TRUE.**
- `_iter_plan_task_bodies` → `heading_bounded_bodies` (`gates.py:300`,
  `markdown.py:151-178`) bounds a `### PLAN-TASK` (level 3) body at the next
  heading of level ≤ 3; the level-2 `## Execution Readiness` / `## Risk Handling`
  cleanly terminates the last task body. `template_for` already appends
  `_TRACE_SKELETON` last (`stage_templates.py:60-67`), keeping `## Trace` final.
- Optional Execution Readiness `- [ ]` items live outside every PLAN-TASK body, so
  they do not affect Steps/Skeleton parsing; no gate flags unchecked checkboxes
  outside PLAN-TASK bodies.
- PLAN-TASK field checks (`_check_plan_task_fields`, `gates.py:527-572`) require
  only the seven `PLAN_TASK_FIELDS`; the optional fields are extra, non-required
  lines and `### PLAN-TASK-(\d+)`-based contiguity is unaffected by `PLAN-TASK-NNN`
  references in field bodies.
- Malformed-ID scan: `PLAN-TASK-NNN` (no digit) is not matched by
  `_TRACE_ID_CANDIDATE_RE` (`gates.py:125-129`, which requires a `\d`), so it is
  never tested; `PLAN-TASK-001` / `RISK-EXAMPLE-001` are valid.
- Placeholder scans (`gates.py:99-114`, applied whole-artifact at `:927-934` and
  per-field at `:619-641`) impose the one real constraint — seeded optional text
  must avoid `fill in` / `TBD`-line / `maybe`-line / `TODO later` / `FIXME`-line /
  `???` / `待定` / `to be decided|determined`. The SPEC explicitly requires this
  (`06-spec.md:58`); the PLN-3 `Verification` example stays an author-filled
  required field (`:56`), filled in AC-4.

**Check 7 — SPEC asserts no change to STAGE_SCHEMA / PLAN_TASK_FIELDS / gates / state / CLI, and the AC-4 fixture need is acknowledged: VERIFIED TRUE.**
- `06-spec.md:52` ("`required_headings`, `STAGE_SCHEMA`, and `PLAN_TASK_FIELDS` are
  unchanged"), `:65-67` (no CLI/JSON/exit-code/status/transition/gate/schema/
  `PLAN_TASK_FIELDS` change; only `template_for` rendering touched), and
  `:97`/`:90-97` Non-goals (SCOPE-OUT-008) all align with SCOPE-OUT-008. The seed
  path leaves `required_headings`/`STAGE_SCHEMA` untouched, so the new `##` headings
  are never gate-required (R2.1 presence-only, `gates.py:894-900`), preserving
  AC-5. The Test Matrix even pins a "non-PLAN stage templates byte-identical" row
  (`:87`), anticipating the join-whitespace regression risk.
- AC-4 fixture acknowledged: SPEC-SEEDTEST-001 (`:62`) names the consistent minimal
  upstream fixture — a SPEC defined+consumed, a carried SCOPE-IN, closed risks, and
  a usable Context Pack for standard tier — which maps to gate Checks 3, 5, and 5b.
  (See Finding 2 for the one additional `_check_plan_file_refs` sub-requirement,
  which sits at PLAN/test altitude.)

## Ambiguity / decisions

- No unresolved ambiguity or undecided point. Decision Requests upstream are
  `none`; Open Questions upstream are `none`. The SPEC is decisive throughout.
- The single deferral — "Suggested token set (exact literals finalized in the PLAN
  against the authored prose)" (`06-spec.md:48`, SPEC-GUARD-001) — is the one
  legitimate deferral and matches the design's SPEC Handoff.
- External Documentation Checked = "N/A — no external dependencies" (`:69-73`) is
  correct: the change is template prose, a Python-stdlib seed path, and pytest;
  no third-party library/API/SDK/CLI is consulted. This also satisfies SPEC gate
  Check 6 (`gates.py:1022-1029`), which requires a non-empty section with an
  explicit N/A row.
- EXE fidelity (Check 8) confirmed against the current claude surface
  (`tools/workflow_cli/agent_templates/claude/commands/r2p-execute.md`): per-task
  ACS currently excludes `07-plan.md` (`:61`) and SPEC-EXE-001 preserves that while
  adding the full-context read only to the final review (`06-spec.md:15-16`); the
  brief-contents description currently omits `Files` (`r2p-execute.md:110`) and
  SPEC-EXE-003 corrects it (`:26`); the clean-tree check is currently Task-1-only
  (`r2p-execute.md:23`) and SPEC-EXE-002 adds a distinct per-task invariant
  (`:18-22`); resume currently reuses only the final-review `Execution BASE:` line
  and §2 would capture fresh HEAD (`r2p-execute.md:114,225`), and SPEC-EXE-004
  forbids `HEAD~1` / fresh-from-HEAD and requires stop-and-ask (`:30-35`);
  SPEC-EXE-005 forbids a Context-Read checklist (`:40`). All restated faithfully
  with the "both surfaces" lockstep.

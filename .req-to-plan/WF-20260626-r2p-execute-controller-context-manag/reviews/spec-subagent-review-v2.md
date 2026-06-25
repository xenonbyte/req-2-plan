# SPEC Review v2 — WF-20260626-r2p-execute-controller-context-manag

**Verdict: Approved**

## Scope

Scoped re-review of the five v1 findings (I-1 Important + I-2..I-5 Minor) applied to `06-spec.md` (now `r2p_version: 2`). v1's full-artifact conclusions are carried forward unchanged and were not disturbed by the edits:

- **Spec/design compliance** — all 3 design components + 6 SCOPE-IN items realized; SCOPE-OUT restated. Still holds.
- **Exit codes** — `0/2/6/7` verified against `output.py:6-12`. The exit-code line (06-spec.md:62) is untouched. Still holds.
- **Trace-closure feasibility** — re-confirmed below; unchanged.

## Per-finding resolution

- **I-1 (Important) — RESOLVED.** 06-spec.md:63 now states the command "uses the shared `format_success` helper, so the success payload carries at least the three data keys `{work_id, task_id, brief_path}` alongside the standard `status` and `message` fields," with the JSON-mode example showing all five keys: `{"status": "ok", "message": "...", "work_id": ..., "task_id": "PLAN-TASK-<NNN>", "brief_path": ...}`. This matches `format_success` exactly — `json.dumps({"status": "ok", "message": message, **data}, indent=2)` (`output.py:48-49`). The "exactly three keys" contradiction is gone; the Test Matrix happy-path row (06-spec.md:77) was correspondingly updated to "inside the standard `status`/`message` envelope". Correct.
- **I-2 (Minor) — RESOLVED.** 06-spec.md:83 adds the Test Matrix row "zero-padded anchor resolved by integer `--task`" → "PLAN authored `### PLAN-TASK-002`; `--task 2` writes `task-2-brief.md` and reports `task_id` = `PLAN-TASK-002` (integer match, not string equality)". This locks the trickiest behavior and matches `plan_task_anchors` group semantics (markdown.py:139-148). Correct.
- **I-3 (Minor) — RESOLVED.** 06-spec.md:65 reworded to "The three data fields are part of the success payload in both modes — JSON object keys under `R2P_JSON=1`, labeled lines otherwise — never replacing the standard envelope." The imprecise "guaranteed regardless of R2P_JSON" phrasing is gone and now correctly reflects the human-mode path (`output.py:51-67`). Correct.
- **I-4 (Minor) — RESOLVED.** SPEC-PROSE-002 (06-spec.md:40) now leads with FR-CM2's exact framing — "Between tool calls the controller narrates at most one short line" — and names "the FR-CM2 `Narration:` discipline — that label is the load-bearing token pinned in the PLAN". Aligned to FR-CM2. Correct.
- **I-5 (Minor) — RESOLVED.** SPEC-PROSE-001 (06-spec.md:36) adds "The controller uses the returned `brief_path` without eager-reading the full task body into its own context; the implementer and reviewer read the brief on demand." The FR-CM1 no-deep-read nuance is now explicit. Correct.

## No regression — trace closure still feasible

The edits were confined to SPEC-PROSE-001/002 prose, the API/Contracts section, and the Test Matrix; the SPEC ID set, PLAN Handoff, and Trace table are untouched:
- 7 SPEC IDs still defined in `### SPEC-*` headings (06-spec.md:13,24,30,38,42,49,53) and still consumed by the 3-task handoff (06-spec.md:99-102): TASK-1 → SPEC-CLI-001 + SPEC-SURFACE-001; TASK-2 → SPEC-PROSE-001..004; TASK-3 → SPEC-GUARD-001. `spec_ids_not_consumed` (trace.py:198) stays empty.
- Each SPEC block still names its SCOPE-IN ("closes SCOPE-IN-00X": 06-spec.md:14,25,31,39,43,50,54), so `scope_in_not_closed` (trace.py:148) stays empty for all of SCOPE-IN-001..006.

No new inaccuracy introduced; no other section disturbed.

## Findings

No remaining Critical, Important, or Minor findings. All five v1 findings are correctly resolved and the SPEC is clean.

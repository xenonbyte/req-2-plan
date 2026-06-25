# SPEC Review — WF-20260626-r2p-execute-controller-context-manag

**Verdict: Approved with notes**

One Important wording defect (the "exactly three keys" JSON claim contradicts the shared `format_success` envelope and the requirement's own Test Plan); the rest is sound. Trace closure is feasible, exit codes are correct, and the cited primitives are used correctly. No Critical findings.

---

## Spec / Design Compliance

Faithful to the design. All three design components and all six SCOPE-IN items are realized by a SPEC contract:

| Design | SPEC | SCOPE-IN |
|---|---|---|
| DES-CLI-001 | SPEC-CLI-001 + SPEC-SURFACE-001 | SCOPE-IN-001 |
| DES-PROSE-001 | SPEC-PROSE-001/002/003/004 | SCOPE-IN-002/003/004/005 |
| DES-GUARD-001 | SPEC-GUARD-001 | SCOPE-IN-006 |

The four SCOPE-OUT items are restated in `## Non-goals` (06-spec.md:90-93). Nothing is dropped or re-scoped at the contract level. Two minor framing slips (not contradictions), noted under Findings: SPEC-PROSE-002 reframes FR-CM2's "between tool calls, narrate at most one short line" as a post-return restatement bound; SPEC-PROSE-001 omits the explicit FR-CM1 "controller does not eager-read the full task body" nuance. Both are covered by the SPEC-GUARD-001 token set + PLAN literal pinning, so they do not block.

---

## Implementability / Code-Grounding (per claim)

**Exit-code constants — all correct.** Verified against `tools/workflow_cli/output.py:6-12`:
- `EXIT_OK = 0` (output.py:6) ✓ — SPEC success `0`.
- `EXIT_CLI_ERR = 2` (output.py:7) ✓ — SPEC arg error (06-spec.md:17,61).
- `EXIT_CONFLICT = 6` (output.py:11) ✓ — SPEC non-EXECUTING / symlink (06-spec.md:15,20,61).
- `EXIT_NOT_FOUND = 7` (output.py:12) ✓ — SPEC unknown work-id / missing PLAN / out-of-range task (06-spec.md:16,61).

The SPEC's split of "task out of range → 7" vs "non-positive/non-integer `--task` → 2" is a clean, decided refinement (the requirement left the malformed-`--task` code unspecified). `2` is also argparse's native arg-error code, so `type=int` rejection lands there naturally; non-positive (`--task 0`/`-1`) needs an explicit positivity check to reach `2` — implementable via a custom type or post-parse guard. No ambiguity.

**"Byte-identical to what the PLAN gate counts as the task body" (06-spec.md:19) — achievable.** The PLAN gate iterates bodies via `_iter_plan_task_bodies = heading_bounded_bodies(content, _PLAN_TASK_RE.match)` (`gates.py:300-301`), where `_PLAN_TASK_RE` is `PLAN_TASK_ANCHOR_RE` imported from `markdown.py` (`gates.py:30`). The command using `heading_bounded_bodies(content, PLAN_TASK_ANCHOR_RE.match)` over `strip_readonly_sections(plan_text)` produces the identical slice. Read-only sections are trailing `##`-level blocks that fall after the last `###` PLAN-TASK, so stripping them does not perturb any task's heading-bounded body. The completion gate derives its IDs from exactly `plan_task_anchors(strip_readonly_sections(plan_text))` (`gates.py:1237`), so the brief's anchor set matches the gate's. Achievable as specified; the implementation must apply `strip_readonly_sections` (SPEC-CLI-001 line 18 already states this).

**`--task N` → anchor resolution + `task_id` (06-spec.md:18,62) — correct.** `plan_task_anchors` returns `(m.group(1), title)` per anchor — `m.group(1)` is the literal `PLAN-TASK-\d+` (markdown.py:139-148). The SPEC correctly uses `plan_task_anchors` for the anchor/`task_id` and `heading_bounded_bodies` for the body — the right primitive for each purpose (the anchors helper yields id+title, not the body). `task_id` = literal `m.group(1)` is exactly the ID form `run-execute-start` seeds the ledger with: `f"- [ ] {tid} {title}"` where `tid` comes from the same `plan_task_anchors` call (`cli.py:746,757`), and the same form `check_execution_complete`/`_LEDGER_CHECKED_RE` audits (`gates.py:1202`). So the brief's `task_id`, the ledger checkbox, and the completion-gate audit all share one literal ID — consistent.

**Symlink rejection + EXECUTING precondition — implementable without touching any gate/transition.** `_reject_symlink_or_exit(path, msg)` (`cli.py:165-167`) just tests `path.is_symlink()` and exits `EXIT_CONFLICT`; callable on `logs/` and the target before writing, exactly as `_cmd_run_execute_start` does for `execution/` (`cli.py:759`). The EXECUTING check is a read-only `record.status` comparison — no `update_run_status`, no `ALLOWED_TRANSITIONS` touch (contrast `_cmd_run_execute_start:728`, which guards `CLOSED_AT_PLAN_CHECKPOINT` and is the mirror pattern, not the same status). Read-only w.r.t. run state, as SPEC-CLI-001 line 22 asserts.

**Output envelope — one defect.** See Finding I-1: the API contract's "exactly three keys" is inconsistent with `format_success`, which under JSON mode emits `{"status":"ok","message":..., **data}` (`output.py:48-49`) — i.e. five keys for this command. The requirement anticipated this ("existing success metadata fields such as `status`/`message` may also be present", requirement Test Plan).

---

## Trace-Closure Feasibility (PLAN gate)

**Feasible — every SPEC is consumed and every SCOPE-IN closes** under the proposed PLAN Handoff (06-spec.md:97-100), verified against `tools/workflow_cli/trace.py`:

- `spec_ids_not_consumed` (trace.py:198) compares the 7 heading-defined `### SPEC-*` IDs against `plan_consumed_spec_ids` (trace.py:106), which reads each PLAN-TASK's `Spec References:` field. The handoff's three tasks name all 7 (TASK-1: SPEC-CLI-001, SPEC-SURFACE-001; TASK-2: SPEC-PROSE-001..004; TASK-3: SPEC-GUARD-001) → empty result, no dangling SPEC. Requires the PLAN author to use a literal `Spec References:` field per task (the field name `plan_consumed_spec_ids` keys on); the handoff format supports this.
- `scope_in_not_closed` (trace.py:148) closes a SCOPE-IN when it appears in a PLAN-TASK body **or** inside a consumed SPEC block outside nested Non-goals (trace.py:159-163). Each SPEC block literally states "closes SCOPE-IN-00X" (06-spec.md:14,25,31,38,42,49,53) and each block is consumed, so all of SCOPE-IN-001..006 close via the SPEC-block path even if PLAN-TASK bodies never name them → empty result. The `### SPEC-*` (level-3) blocks terminate at `## API / Data / Config Contracts` (level-2), so the document-level `## Non-goals` SCOPE-OUT references never leak into a SPEC block (`_heading_blocks`, trace.py:116-137) and cannot trip `scope_out_violations` (trace.py:251).
- `risk_ids_not_closed` (trace.py:168) reads the RISK artifact, where all five RISK blocks carry `Status: mitigated` (04-risk-discovery.md) — unaffected by the SPEC.

No SPEC dangles; no SCOPE-IN fails to close. `check_trace_closure` (trace.py:274) would pass for a PLAN faithful to this handoff.

---

## Unresolved Ambiguity / Undecided Points

- **Deferring exact docs-consistency token literals to the PLAN (06-spec.md:55) — acceptable, not a dodge.** The exact literals must match prose authored in PLAN-TASK-2; pinning them now would be guessing at unwritten wording. The requirement explicitly blessed this ("Token strings are finalized against the exact prose during implementation", requirement Test Plan). The SPEC names the concrete semantic set (`plan-task-brief`, `brief_path`, `Resolved:`/`Gap:`/`Unresolved:`, narration-ceiling phrasing, carry-to-final-review phrasing), which is enough for a PLAN author to act. One mild deviation: the design's SPEC Handoff said "pin the exact token list"; the SPEC relaxes "exact" to "semantic, literals pinned in PLAN". Defensible given the prose-authoring order, noted as Minor.
- **`task_id` zero-padding (06-spec.md:62) — unambiguous.** "the literal matched anchor text (the zero-padding is whatever the PLAN authored, taken from the `plan_task_anchors` group)" precisely matches `m.group(1)`. A PLAN author can act on it: `--task 2` against `### PLAN-TASK-002` yields `task_id: "PLAN-TASK-002"` and file `task-2-brief.md`. The intentional asymmetry — `task_id` keeps authored padding, `brief_path` uses the bare integer `N` — is consistent across requirement/design/spec, but is easy to miss; worth one explicit line (Minor I-3).

---

## Findings List

| # | Severity | Finding | Fix |
|---|---|---|---|
| I-1 | **Important** | API contract (06-spec.md:62) says success stdout is "a single JSON object with **exactly three keys** — {work_id, task_id, brief_path}". The shared `format_success` JSON envelope always injects `status` and `message` (`output.py:48-49`), so the in-grain implementation (mirroring `_cmd_run_execute_start`, which uses `format_success`) emits **five** keys. The requirement's Test Plan explicitly expects `status`/`message` to "also be present". As written, a test author taking "exactly three keys" literally writes a failing/incorrect assertion, or is pushed to bypass the standard envelope and diverge from every other command's output shape. | Reword to "at least the three top-level keys `{work_id, task_id, brief_path}`, alongside the standard `status`/`message` fields `format_success` emits under `R2P_JSON=1`." |
| I-2 | Minor | Test Matrix (06-spec.md:74-86) drops the requirement's dedicated **integer/zero-padding resolution** case ("a zero-padded `### PLAN-TASK-002` is selected by `--task 2`, not string equality"). This is the single most error-prone behavior (string-vs-integer match); without an explicit case, a naive `f"PLAN-TASK-{N}"` string match could regress undetected if the happy-path seed isn't zero-padded. Traces to the design's own SPEC-Handoff matrix omitting it. | Add a Test Matrix row under SPEC-CLI-001: "zero-padded anchor `### PLAN-TASK-002` resolved by `--task 2` (integer match)". |
| I-3 | Minor | "the JSON keys above are guaranteed regardless of `R2P_JSON`" (06-spec.md:64) is imprecise: in non-JSON mode `format_success` emits human-formatted labeled lines (`output.py:51-67`), not JSON keys. | Reword to "the three data fields are part of the success payload in both modes — JSON object keys under `R2P_JSON=1`, labeled lines otherwise." |
| I-4 | Minor | SPEC-PROSE-002 (06-spec.md:39) frames FR-CM2's narration ceiling as a post-subagent-return restatement bound; FR-CM2 is specifically "between tool calls, narrate at most one short line" with the `Narration:` label. Not contradictory; looser. | Align SPEC-PROSE-002 wording to FR-CM2's "between tool calls / at most one short line", or note the `Narration:` token is the load-bearing literal pinned in PLAN. |
| I-5 | Minor | SPEC-PROSE-001 (06-spec.md:30-35) omits FR-CM1's explicit "controller does **not** eager-read the full task body" point that the design acceptance criteria emphasize; it states "uses the returned `brief_path`" and "not pasted task text" but not the no-deep-read discipline. | Add a clause: "the controller uses the brief path without eager-reading the full task body into its own context." |

No Critical findings. The SPEC is implementable and trace-closure-feasible; I-1 is a contract-precision fix the PLAN must carry into its test, the rest are wording/coverage tightening.

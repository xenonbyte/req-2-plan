# Design Review — WF-20260626-r2p-execute-controller-context-manag

**Verdict: Approved with notes**

One Minor factual error in the code-evidence section; all three sanity checks pass; no Critical or Important findings.

---

## Spec Compliance

Clean. All five FRs (FR-CM1 through FR-CM5) and all six SCOPE-IN items are mapped to design components:

| SCOPE-IN | FR | Design component |
|---|---|---|
| SCOPE-IN-001 | FR-CM5 | DES-CLI-001 (plan-task-brief command + shortcut + wrapper) |
| SCOPE-IN-002 | FR-CM1 | DES-PROSE-001 (§1/§2/§5 + return contract) |
| SCOPE-IN-003 | FR-CM2 | DES-PROSE-001 (narration ceiling) |
| SCOPE-IN-004 | FR-CM3 | DES-PROSE-001 (⚠️ adjudication + §6 flip condition) |
| SCOPE-IN-005 | FR-CM4 | DES-PROSE-001 (Minor carry-forward) |
| SCOPE-IN-006 | docs guard | DES-GUARD-001 (test_docs_consistency.py token extension) |

All five RISK items from the Risk stage are addressed by the design's mitigations. Nothing dropped, contradicted, or silently re-scoped. SCOPE-OUT items are explicitly excluded in the design (Rollback, Observability, and Boundaries sections).

---

## Design / Code-Evidence Quality

### Verified correct

| Claim | Verified location |
|---|---|
| `_reject_symlink_or_exit` (`cli.py:165`) | `cli.py:165` — `if path.is_symlink(): print_and_exit(...)` ✓ |
| `atomic_write_text` (`atomic.py:9`) | `atomic.py:9` — function def ✓ |
| `plan_task_anchors` + `heading_bounded_bodies` + `PLAN_TASK_ANCHOR_RE` (`markdown.py`) | `markdown.py:135, 139, 151` ✓ |
| `strip_readonly_sections` (`markdown.py:62`) | `markdown.py:62` ✓ |
| `_check_plan_task_fields` (`gates.py:527`), contiguous-from-1 check at `gates.py:570-571` | `gates.py:527`; lines 568-571 enforce unique + contiguous ✓ |
| `_LEDGER_UNCHECKED_RE` / `_LEDGER_CHECKED_RE` at `gates.py:1201-1202` | `gates.py:1201-1202` — `^\s*-\s*\[\s*\]\s*(PLAN-TASK-\d+)\b` / `^\s*-\s*\[[xX]\]\s*(PLAN-TASK-\d+)\b` ✓ |
| `check_execution_complete` at `gates.py:1240` | `gates.py:1240` ✓ |
| `check_final_review_recorded` at `gates.py:1148` | `gates.py:1148` ✓ |
| `check_forced_subagent_review` at `gates.py:1068` (not in scope for execution) | `gates.py:1068` ✓ |
| `read_artifact(run_dir, Stage.PLAN) -> str` raising `FileNotFoundError` at `artifact.py:108` | `artifact.py:108` ✓ |
| `_iter_plan_task_bodies` wraps `heading_bounded_bodies(content, _PLAN_TASK_RE.match)` (claimed `gates.py:301`) | `gates.py:300-301`; `_PLAN_TASK_RE` is `PLAN_TASK_ANCHOR_RE` imported from `markdown.py` (line 30) — same regex, same call ✓ |
| Installer auto-discovery via `repo_root.glob("tools/r2p-*")` | `install.py:127, 558, 607` ✓ |
| `test_execute_surfaces_carry_sdd_orchestration_tokens` exists in `tests/test_docs_consistency.py` | `test_docs_consistency.py:60` ✓ |

### One inaccuracy found

**Minor** — "Current Code Evidence" section states:

> `tools/workflow_cli/cli.py` `_cmd_run_execute_start` — the **EXECUTING**-status precondition (EXIT_CONFLICT otherwise)

But `_cmd_run_execute_start` (`cli.py:726–736`) checks `record.status != RunStatus.CLOSED_AT_PLAN_CHECKPOINT`, not EXECUTING:

```python
if record.status != RunStatus.CLOSED_AT_PLAN_CHECKPOINT:
    print_and_exit(format_error(..., exit_code=EXIT_CONFLICT), EXIT_CONFLICT)
```

The wrong status name is attributed to the existing handler being cited as the mirror pattern. The new `plan-task-brief` command's own EXECUTING guard is correctly specified in DES-CLI-001 ("requires run status EXECUTING (else EXIT_CONFLICT with no write)") — so the design intent is unambiguous. But a SPEC author reading the code evidence section would find the status name inconsistent with what `_cmd_run_execute_start` actually checks.

**Fix**: change the code evidence entry to read "the `CLOSED_AT_PLAN_CHECKPOINT`-status precondition (EXIT_CONFLICT otherwise); `plan-task-brief` mirrors this shape with EXECUTING status."

### Cosmetic

`_iter_plan_task_bodies` is cited as `gates.py:301` (the return line); the function definition starts at line 300. The reference is unambiguous; no action needed.

---

## Sanity Checks

**(a) Does `plan-task-brief` reusing `heading_bounded_bodies`/`plan_task_anchors` yield the same single-task body the PLAN gate counts?**

Yes. `_iter_plan_task_bodies` at `gates.py:300-301` is `heading_bounded_bodies(content, _PLAN_TASK_RE.match)` where `_PLAN_TASK_RE` is `PLAN_TASK_ANCHOR_RE` imported from `markdown.py` (`gates.py:30`). The new command uses `heading_bounded_bodies(content, PLAN_TASK_ANCHOR_RE.match)` — the identical call and the identical regex. The body boundary is deterministic and shared.

**(b) Is contiguous-from-1 numbering gate-guaranteed so integer `--task N` → `### PLAN-TASK-<N>` is deterministic?**

Yes. `_check_plan_task_fields` at `gates.py:567-571` enforces: (1) all PLAN-TASK numbers unique (`len(set(numbers)) != len(numbers)`), (2) all numbers form `range(1, len+1)`. The PLAN quality gate runs this check before a run can close at PLAN checkpoint; execution only ever sees a validated 1..N task set. The design correctly notes this is "gate-enforced before execution starts", not assumed.

**(c) Do FR-CM3 Resolved/Gap/Unresolved markers stay inert to `_LEDGER_*` regexes (no trust-boundary violation)?**

Yes. `_LEDGER_UNCHECKED_RE` (`gates.py:1201`) matches `^\s*-\s*\[\s*\]\s*(PLAN-TASK-\d+)\b` and `_LEDGER_CHECKED_RE` (`gates.py:1202`) matches `^\s*-\s*\[[xX]\]\s*(PLAN-TASK-\d+)\b`. Markers of the form `Resolved: ...`, `Gap: ...`, `Unresolved: ...` do not start with `- [ ]` or `- [x]` and do not contain a `PLAN-TASK-\d+` token after a checkbox, so they are inert to both regexes. The FR-CM4 `Minor:` bullets are similarly inert. No trust-boundary violation.

---

## Unresolved Ambiguity / Undecided Points

None found. "Decision Requests: none" is honest. All structural choices are made:
- EXECUTING-only guard for `plan-task-brief`: decided.
- JSON payload fields (`work_id`, `task_id`, `brief_path`): pinned.
- Exit codes: pinned.
- Brief file path (`.req-to-plan/<id>/logs/task-N-brief.md`): pinned.
- Phase 1 / Phase 2 split: decided.
- `task_id` value is the literal `PLAN-TASK-NNN` anchor (from `plan_task_anchors` `m.group(1)`), not the `### ` prefix form: implied by the code path and consistent with the acceptance criteria.

The token list for `test_docs_consistency.py` is explicitly deferred as "finalized against exact prose during implementation" — this is proper SPEC-level work, not a design dodge; the design gives a sufficiently constrained example list.

---

## Findings List

| # | Severity | Finding | Fix |
|---|---|---|---|
| F-01 | Minor | Code Evidence section (`05-design.md`, "Current Code Evidence") misidentifies `_cmd_run_execute_start`'s status guard as "EXECUTING-status precondition"; actual guard is `CLOSED_AT_PLAN_CHECKPOINT` (`cli.py:728`). The design's own DES-CLI-001 is correct (EXECUTING for the new command); the evidence is misleading about the existing handler it uses as a mirror reference. | Amend the evidence bullet to "the `CLOSED_AT_PLAN_CHECKPOINT`-status precondition (`cli.py:728`); `plan-task-brief` mirrors this guard shape with EXECUTING status." |
| F-02 | Minor (cosmetic) | `_iter_plan_task_bodies` cited as `gates.py:301` (the return line); function def is at line 300. | No action required; reference is unambiguous. |

No Critical or Important findings.

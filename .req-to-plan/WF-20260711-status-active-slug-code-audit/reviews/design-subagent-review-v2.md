# Subagent Review — DESIGN (05-design.md), artifact v2

Reviewer: read-only Explore subagent (spawned per forced-review requirement; tier modifiers cross_project, safety, scope_expanding).
Scope audited: 05-design.md against 00-raw-requirement.md, 03-requirement-brief.md, 04-risk-discovery.md, and the live source tree (gates.py, install.py, cli.py, agent_shortcuts.py, state.py, atomic.py, trace.py, output.py).

## Verdict: PASS

Artifact v1 was audited in full by the subagent (verdict PASS-WITH-NOTES, three minor findings, zero blocker/major). v2 contains exactly the three corrections the review requested — verified against the produced v2 artifact — and no other change, so the v1 audit carries over and the notes are resolved.

## Spec Compliance — PASS

All six in-scope items covered exactly, one design element each, no drops, no additions, no scope creep into SCOPE-OUT territory:

| Upstream | Design | Match against raw requirement |
|---|---|---|
| SCOPE-IN-001 | DES-GATE-001 | Boundary-only closure fix, finder untouched, 3 named tests — matches §1 verbatim |
| SCOPE-IN-002 | DES-DEAD-002 | Pure `_safe_copy` deletion, grep post-check — matches §2 |
| SCOPE-IN-003 | DES-DEDUP-003 | `_require_disk_version_matches(run_dir, stage, aa)`, version block only — matches §3 |
| SCOPE-IN-004 | DES-DEDUP-004 | Reuse `_reject_symlinked_run_paths_or_exit`, drop `r2p_dir` — matches §4 |
| SCOPE-IN-005 | DES-SAFE-005 | `read_regular_text` + shortcut branch, same commit, 2 tests — matches §5 |
| SCOPE-IN-006 | DES-DEDUP-006 | Home primitives in trace, `[ \t]*` canonical, keep both wrappers — matches §6 |

Commit mapping (1: gate fix + tests; 2: three pure dedups; 3: symlink pair + tests; 4: field-primitive homing, last, own commit) matches the raw requirement's Checkpoints exactly; Rollback and SPEC Handoff restate it consistently.

## Evidence Accuracy — PASS

Every load-bearing "Current Code Evidence" claim verified true against live source:

- `gates.py:459-462` boundary-less closure pattern; `_UPSTREAM_ID_PATTERN` uses `\b` (confirmed it yields the base ref from a suffixed ID, validating the behavior edge); field helpers at 574/583-589/592; `SPEC_ID_RE` imported from trace at 39.
- `install.py:1211-1228` `_safe_copy` dead (grep: definition only, zero call sites); `_safe_write` at 1231.
- `cli.py` five guards confirmed at message lines 521/1429/2071/2171/2327 in the five named handlers; copies differ only in local name `disk_version` vs `version`; `cli.main` catches `UnsafeRegularFileError` at 2481 → exit 6.
- `agent_shortcuts.py`: inline symlink block 1042-1055 byte-identical in output to `_reject_symlinked_run_paths_or_exit` (105; used at 637/932/1189) — same `blocked:` lines, same order, same exit; `_load_matching_record_or_exit` (118) catches only `FileNotFoundError`; `UnsafeRegularFileError` imported (21); only two literal `.load()` sites in the module (121 inside the helper, 151 inside `scan_open_runs`'s `except Exception`), so the coverage-exhaustiveness conclusion holds.
- `state.py:612-615` bare `read_text`; atomic import at 11. `atomic.py:15` `read_regular_text(path, *, encoding="utf-8", missing_ok=False)` raises `UnsafeRegularFileError` / `FileNotFoundError` as claimed.
- `trace.py`: `\s*` variant at 133; `_find_next_plan_task_field_start` at 142 (logically identical to gates' copy; parameter name differs); `_plan_task_field_value` strips; `PLAN_TASK_FIELD_RE` imported at 19; trace does NOT import gates (grep empty) → no cycle.

## Design Quality — PASS

- Regex boundary fix traced through all three test scenarios: shorter-ID-in-longer-ID → trailing digit fails lookahead → reported unclosed; both-closed → both pass; suffixed malformed ID → trailing `-` fails lookahead → base ref reported unclosed. `[^\n]*` vicinity and IGNORECASE preserved; mirrors `_TRACE_TOKEN_CHARS`/`SPEC_ID_RE`.
- Helper extraction signature fits all five sites; message string and exit preserved exactly; per-handler `aa is None`/status checks stay.
- trace.py homing: import direction verified (gates→trace exists, trace→gates absent); owner rationale (avoid new markdown→stage_schema edge) sound.
- Two-edits-one-commit symlink pairing correct; `load()`'s `exists()` pre-check makes `missing_ok` moot on that path, as the design notes.

## Ambiguity Check — PASS

"Decision Requests: none" is accurate. Every fork in Options Considered is closed with a chosen branch; no hedging, TBD, or open either/or in the body; commit assignments are firm.

## v1 Findings → v2 Resolution

1. [minor] "byte-identical" overstatement for `_find_next_plan_task_field_start` → v2 reworded to "logically identical (parameter name differs)" in both occurrences. RESOLVED.
2. [minor] DES-GATE-001 closing fence shared a line with prose (would mis-render / mis-scan) → v2 puts the closing fence on its own line; grep confirms no fence-plus-prose line remains. RESOLVED.
3. [minor, informational] load()-caller enumeration was representative, not exhaustive → v2 lists all `_load_matching_record_or_exit` call sites (939, 1062, 1196; loop sites 648, 731, 751, 789). RESOLVED.

No blocker or major findings. Design is decision-complete, evidence-accurate, and ready for checkpoint approval.

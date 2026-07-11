---
r2p_stage: design
r2p_version: 2
r2p_status: approved
r2p_created_at: 2026-07-11T07:56:37.926525+00:00
r2p_updated_at: 2026-07-11T08:05:25.699402+00:00
---

# Design

## Design Summary

Six surgical edits across `gates.py`, `install.py`, `cli.py`, `agent_shortcuts.py`, `state.py`, and `trace.py`, landed as four ordered commits. One correctness fix (token-boundary closure matching in quality-gate Check 3), one invariant closure (symlink-safe `run.md` loads with a clean shortcut exit), and four code-removal dedups. No new mechanism, gate, field, keyword pattern, CLI command, or abstraction layer anywhere; net production line count decreases. All designs were pre-decided upstream with rationale; this document grounds each in current code evidence and fixes the exact edit shapes.

## Current Code Evidence

All anchors re-verified against the working tree at design time (they match the raw requirement):

1. `gates.py:459-462`, inside `_find_ids_without_closure`: the closure-search pattern has no token boundary around the ID —
```python
pattern = re.compile(
    re.escape(ref_id) + r"[^\n]*" + re.escape(tag),
    re.IGNORECASE,
)
```
Given a collision input like the fenced example below, the search for the shorter ID matches the prefix of the longer one, so the unclosed shorter ID is silently treated as closed (fails open; empirically reproduced upstream):
```text
REQ-AUTH-10 [ADDRESSED]    <- closes REQ-AUTH-10; pre-fix it also "closes" an unclosed REQ-AUTH-1
```
2. `install.py:1211-1228`: `_safe_copy(src, dest, backups, installed_paths, written, backup_dir)` — near-verbatim twin of `_safe_write` (line 1231), zero call sites in `tools/` or `tests/` (grep verified).
3. `cli.py:517-525` (and the four analogues ending at message lines 1429, 2071, 2171, 2327): five identical 9-line version-match guards — `get_artifact_version(...)` then `print_and_exit(format_error(f"Active artifact version v{aa.version} does not match on-disk v{...}", exit_code=EXIT_CONFLICT), EXIT_CONFLICT)`. Handlers: `_cmd_run_close` (passes `Stage.PLAN`), `_cmd_gate_quality`, `_cmd_review_checkpoint`, `_cmd_checkpoint_decide`, `_cmd_stage_advance` (each has a `stage` local).
4. `agent_shortcuts.py:1042-1055`, inside `_cmd_execute`: inline `r2p_dir.is_symlink()` / `run_dir.is_symlink()` checks printing `blocked: unsafe_workspace_dir_symlink` / `blocked: unsafe_run_dir_symlink` then `sys.exit(EXIT_CONFLICT)` — byte-identical output to `_reject_symlinked_run_paths_or_exit` (defined at line 105, already used at lines 637, 932, 1189; checks workspace dir first, then run dir, returns `base_path / ".req-to-plan" / work_id`).
5. `state.py:615`, inside `RunStateManager.load()` (def at 612): `text = self.run_path.read_text(encoding="utf-8")` — the single remaining bare read of trusted `run.md`; the write side already routes through `atomic_write_text` (imported at `state.py:11`). `atomic.read_regular_text(path, *, encoding="utf-8", missing_ok=False)` exists at `atomic.py:15` and raises `UnsafeRegularFileError` / `FileNotFoundError` as documented.
6. Duplicated PLAN-TASK field primitives, already drifted once: `gates._find_plan_task_field` (`gates.py:574`, pattern `rf"^{re.escape(field)}:[ \t]*(.*)$"`) vs `trace._find_plan_task_field` (`trace.py:133`, pattern `rf"^{re.escape(field)}:\s*(.*)$"`); `_find_next_plan_task_field_start` logically identical in both (`gates.py:592` / `trace.py:142`; only the parameter name differs, `task_body` vs `body`); `_count_plan_task_fields` (`gates.py:583-589`) is a third copy of the same field grammar. `gates` already imports from `trace` (`SPEC_ID_RE`, `gates.py:39`); `trace` does not import `gates`.
7. Shortcut load coverage for the new exception: `_load_matching_record_or_exit` (`agent_shortcuts.py:118`) catches only `FileNotFoundError`; call sites at 939, 1062, 1196 and inside `_cmd_continue`'s loop (648, 731, 751, 789) — all routing through the same helper; `scan_open_runs` wraps `load()` in `except Exception` (warn + skip); `cli.main` already catches `UnsafeRegularFileError` at `cli.py:2481` (exit 6); `UnsafeRegularFileError` is already imported in `agent_shortcuts.py` (line 21).

## Requirements Coverage

| Upstream | Design element |
|---|---|
| SCOPE-IN-001 [ADDRESSED] | DES-GATE-001 |
| SCOPE-IN-002 [ADDRESSED] | DES-DEAD-002 |
| SCOPE-IN-003 [ADDRESSED] | DES-DEDUP-003 |
| SCOPE-IN-004 [ADDRESSED] | DES-DEDUP-004 |
| SCOPE-IN-005 [ADDRESSED] | DES-SAFE-005 |
| SCOPE-IN-006 [ADDRESSED] | DES-DEDUP-006 |

## Options Considered

All forks were resolved upstream with rationale; recorded here for the record, none reopened:

- Boundary idiom for the closure fix: bare `(?!\d)` rejected (digit-only, forks a second weaker boundary convention); canonical two-sided lookarounds over `A-Za-z0-9_-` chosen, mirroring `trace._TRACE_TOKEN_CHARS` / `SPEC_ID_RE`.
- Owner module for the shared field primitives: `markdown.py` rejected (would add a new `markdown -> stage_schema` dependency edge); `trace.py` chosen (zero new edges, no cycle).
- Whitespace canonicalization direction: gates' tighter `[ \t]*` chosen over trace's `\s*` (the one deliberate behavior touch; exotic-whitespace field lines only).
- Merging the two thin wrappers (`_plan_task_field_body` unstripped vs `_plan_task_field_value` stripped): rejected, the `.strip()` difference is load-bearing; both stay as module-local wrappers.

## Chosen Design

### DES-GATE-001 Token-boundary closure match in the quality gate
In `gates._find_ids_without_closure`, replace the closure-search pattern with the two-sided token boundary, preserving the `[^\n]*` vicinity semantics and `re.IGNORECASE`:
```python
pattern = re.compile(
    r"(?<![A-Za-z0-9_-])" + re.escape(ref_id) + r"(?![A-Za-z0-9_-])"
    + r"[^\n]*" + re.escape(tag),
    re.IGNORECASE,
)
```
The finder `_UPSTREAM_ID_PATTERN` is untouched: a malformed suffixed-ID line (fenced example below) still yields the base ref but, post-fix, no longer self-closes — intended fails-closed behavior on typo'd IDs.
```text
REQ-AUTH-1-FOO [ADDRESSED]    <- finder yields ref REQ-AUTH-1; post-fix the gate reports it unclosed
```
Three new tests in `tests/test_gates.py` (prefix collision unclosed + Check 3 fails; both closed; malformed-suffix reports base ref). Commit 1. Closes RISK-GATE-001 [ADDRESSED] and the anchor half of RISK-DRIFT-002 [ADDRESSED].

### DES-DEAD-002 Delete dead copy helper in install.py
Delete `_safe_copy` (`install.py:1211-1228` plus the blank-line separator before `_safe_write`). Pure ~18-line deletion, zero call sites, zero behavior change. Post-check: `grep -rn "_safe_copy" tools tests` returns nothing; `tests/test_install.py` stays green. Commit 2.

### DES-DEDUP-003 One version-match guard helper in cli.py
Add the narrow module-level helper and call it from all five handlers:
```python
def _require_disk_version_matches(run_dir, stage, aa) -> None:
    disk_version = get_artifact_version(run_dir, stage)
    if disk_version != aa.version:
        print_and_exit(
            format_error(
                f"Active artifact version v{aa.version} does not match on-disk v{disk_version}",
                exit_code=EXIT_CONFLICT,
            ),
            EXIT_CONFLICT,
        )
```
`_cmd_run_close` passes `Stage.PLAN` explicitly; the other four pass their `stage` local. Message string and `EXIT_CONFLICT` are preserved exactly (the five current copies differ only in a local variable name, `disk_version` vs `version`). Only the version block is extracted; per-handler `aa is None`/status checks stay. Existing five conflict tests in `tests/test_cli.py` are the pin. Commit 2. Closes RISK-COMPAT-004 [ADDRESSED].

### DES-DEDUP-004 Reuse the symlink-rejection helper in the execute path
In `_cmd_execute` (`agent_shortcuts.py`), replace the inline workspace/run-dir symlink block with:
```python
run_dir = _reject_symlinked_run_paths_or_exit(base_path, work_id)
```
Output is byte-identical (same `blocked:` lines, same order, same `EXIT_CONFLICT`); downstream `run_path = run_dir / "run.md"` unchanged; the now-unused `r2p_dir` local is dropped (no other use in `_cmd_execute`, verified). Existing `unsafe_workspace_dir_symlink` / `unsafe_run_dir_symlink` tests stay green. Commit 2.

### DES-SAFE-005 Symlink-safe run.md load with a clean shortcut exit
Two edits, same commit (Commit 3), so the hardening never trades a silent follow for a traceback:
1. `state.py` `RunStateManager.load()`: `text = read_regular_text(self.run_path)`, extending the existing atomic import at `state.py:11`. `read_regular_text` raises `FileNotFoundError` on missing (existing handlers unaffected) — note `load()`'s own `exists()` pre-check already covers the missing case — and `UnsafeRegularFileError` on non-regular/symlinked sources.
2. `agent_shortcuts._load_matching_record_or_exit`: add alongside the existing `except FileNotFoundError`:
```python
except UnsafeRegularFileError as exc:
    print(f"blocked: unsafe_run_record\nwork_id: {work_id}\nreason: {exc}\n")
    sys.exit(EXIT_CONFLICT)
```
Caller coverage is exhaustive per Current Code Evidence item 7; `scan_open_runs`'s symlinked `run.md` changes from silently-followed to warned-and-skipped (acceptable, no code change). Two new tests: `read_regular_text` unit test (FIFO raises; `missing_ok` honored; symlink raises) in `tests/test_atomic_write.py`, mirroring the existing gates FIFO tests; integration test that a symlinked `run.md` makes a shortcut command print `blocked: unsafe_run_record` and exit 6. Closes RISK-COMPAT-003 [ADDRESSED].

### DES-DEDUP-006 Home the shared PLAN-TASK field primitives in trace.py
In `trace.py`, add public names:
```python
def plan_task_field_re(field):
    return re.compile(rf"^{re.escape(field)}:[ \t]*(.*)$")
```
plus `find_plan_task_field(body, field)` (using the builder) and `find_next_plan_task_field_start(body, after)` (moved as-is; both modules' copies are logically identical apart from the parameter name and already use `PLAN_TASK_FIELD_RE`, imported at `trace.py:19`). Delete the `gates.py` copies (`_find_plan_task_field`, `_find_next_plan_task_field_start`), import the public names from trace, and point `_count_plan_task_fields` at `plan_task_field_re`. Keep `_plan_task_field_body` (gates, unstripped) and `_plan_task_field_value` (trace, stripped) as thin local wrappers over the shared function. trace's field pattern thereby canonicalizes from `\s*` to `[ \t]*` — the one deliberate behavior touch, exotic-whitespace field lines only. Commit 4, batch-final, own commit; import direction re-confirmed (trace must not import gates). Closes RISK-BEHAV-005 [ADDRESSED] and RISK-DEP-006 [ADDRESSED].

## Decision Requests
none

## Rollback

Each commit is independently `git revert`-able: Commit 1 (gate fix + tests), Commit 2 (three pure dedups/deletions), Commit 3 (symlink-safety pair + tests), Commit 4 (field-primitive homing). No schema, data, manifest, or on-disk format changes anywhere, so revert restores prior behavior exactly. Reverting Commit 3 removes both halves together (reader + handler), preserving the no-traceback property in both directions.

## Observability

The observable surface is exit codes and printed messages, both already established: quality-gate Check 3 failures list the unclosed IDs (exit 3 at the gate surface); the new shortcut branch prints `blocked: unsafe_run_record` with work_id and reason (exit 6), matching the existing `blocked:` idiom; `scan_open_runs` warns and skips on unsafe `run.md`. No logging, metrics, or new output formats are added (SCOPE-OUT-003 [OUT-OF-SCOPE] holds). The test suite is the regression observatory: three new gate tests, two new symlink-safety tests, and the existing conflict/symlink/install pins.

## SPEC Handoff

SPEC must pin, per item: exact target symbols and edit shapes (as fixed above), the three gate-test cases and two symlink-safety tests by name and file, the four-commit mapping with the full-suite gate before each commit (`.venv/bin/python -m pytest tests/ -v`, local `tomllib` skips expected), the grep post-check for the dead helper, the `git diff --stat` net-line check, and the two intended exit-code behavior changes (everything else byte-equivalent). No task may introduce a new mechanism (SCOPE-OUT-003 [OUT-OF-SCOPE] is the standing constraint).

## Trace
<!-- Map this stage's IDs to upstream/downstream. R3 derives & checks closure. -->
| This ID | Upstream | Status |
|---|---|---|
| DES-GATE-001 | SCOPE-IN-001 [ADDRESSED], RISK-GATE-001 [ADDRESSED], RISK-DRIFT-002 [ADDRESSED] | designed |
| DES-DEAD-002 | SCOPE-IN-002 [ADDRESSED] | designed |
| DES-DEDUP-003 | SCOPE-IN-003 [ADDRESSED], RISK-COMPAT-004 [ADDRESSED] | designed |
| DES-DEDUP-004 | SCOPE-IN-004 [ADDRESSED] | designed |
| DES-SAFE-005 | SCOPE-IN-005 [ADDRESSED], RISK-COMPAT-003 [ADDRESSED] | designed |
| DES-DEDUP-006 | SCOPE-IN-006 [ADDRESSED], RISK-BEHAV-005 [ADDRESSED], RISK-DEP-006 [ADDRESSED] | designed |

## Upstream Summary (read-only)
# Risk Discovery

## Risks

### RISK-GATE-001 Closure-boundary fix regresses existing gate behavior
The token-boundary fix tightens quality-gate Check 3 for every stage and tier. The two intended tightenings (prefix-collision inputs now report the shorter ID unclosed; a malformed suffixed-ID line no longer self-closes its base ref) could in principle be accompanied by unintended ones — existing tests or artifacts that accidentally relied on prefix matching would start failing. Contained by keeping the change to the closure-search pattern only (the finder `_UPSTREAM_ID_PATTERN` is untouched), by the three new guarding tests, and by a green full suite before commit. Anchor re-verified in the working tree: the boundary-less pattern is at `gates.py:460`.
Status: mitigated

### RISK-DRIFT-002 Line-anchor drift between audit date and implementation
The raw requirement pins anchors by line number as of 2026-07-11. Lines drift as the tree moves. All anchors were re-verified against the current working tree at this stage: `gates.py:460` (closure pattern), `install.py:1211` (`_safe_copy`), `cli.py:521/1429/2071/2171/2327` (five version-guard message lines), `state.py:615` (bare `read_text`). Implementation re-locates every edit point by symbol name, never by stored line number.
Status: mitigated

### RISK-COMPAT-003 Symlink-safe run.md loads surface a new exception at uncovered call sites
Routing `RunStateManager.load()` through `read_regular_text` converts a silently-followed symlinked `run.md` into `UnsafeRegularFileError` at every `load()` call site; any caller without a handler becomes a raw traceback. Caller coverage was verified upstream and holds: every shortcut load routes through `_load_matching_record_or_exit` (which gains the `blocked: unsafe_run_record` / exit 6 branch) or through `scan_open_runs` (existing `except Exception` → warn and skip); the CLI surface is already covered by `cli.main`'s `except UnsafeRegularFileError` (exit 6). The new integration test pins the shortcut path end to end.
Status: mitigated

### RISK-COMPAT-004 Version-guard extraction changes handler messages or exit codes
Extracting `_require_disk_version_matches` could subtly alter the conflict message text or exit code in one of the five handlers. The helper preserves the exact message string and `EXIT_CONFLICT`; the existing per-handler conflict tests in `tests/test_cli.py` (exit 6 on mismatch, all five handlers) are the regression pin. Only the version block is extracted; per-handler `aa is None`/status checks stay in place because they legitimately vary.
Status: mitigated

### RISK-BEHAV-005 Field-regex canonicalization changes trace parsing of exotic whitespace
Canonicalizing on gates' `[ \t]*` variant means trace's parser stops accepting exotic whitespace (for example form feed or vertical tab) between a PLAN-TASK field colon and its value. This is the one deliberate behavior touch in the batch, it affects only that exotic input class on per-line input, and it ships isolated in the batch's final commit with the full suite — especially `tests/test_gates.py` and `tests/test_trace.py` — as the guard.
Status: mitigated

### RISK-DEP-006 Import cycle from homing shared primitives in trace.py
If `trace.py` ever imported `gates.py`, homing the shared PLAN-TASK field primitives in trace would create a cycle. Direction verified: gates already imports from trace (`SPEC_ID_RE`), trace does not import gates, so trace-as-owner adds zero new dependency edges. The final commit re-confirms the import direction; a cycle would fail at import time across the whole suite.
Status: mitigated

## Boundaries

- Production files touched, exhaustively: `tools/workflow_cli/gates.py`, `install.py`, `cli.py`, `agent_shortcuts.py`, `state.py`, `trace.py`.
- Test files touched: `tests/test_gates.py`, `tests/test_atomic_write.py`, plus the home of the symlinked-`run.md` integration test (existing shortcut-test module).
- Not touched: agent templates, install manifest logic, argparse surfaces, exit-code table, `version.py`, docs, `tier_keywords.yaml`, R20 machinery. Any diff outside the named files violates acceptance criterion 4 and fails the batch's final review.
- Behavior boundary: exit-code behavior changes only at the two intended hardenings (gate fails closed on prefix collisions; symlinked `run.md` exits 6 cleanly); everything else must be byte-equivalent in output.

## Scope Overflow Risks

Working inside gates/trace/cli invites adjacent "while we're here" merges; each temptation is pre-excluded by the brief and stays excluded:

- Unifying the two PLAN-TASK body-splitters — excluded per SCOPE-OUT-004 [OUT-OF-SCOPE].
- Unifying the DECISION-block field parsers with the PLAN-TASK helpers — excluded per SCOPE-OUT-005 [OUT-OF-SCOPE].
- Deduplicating the `_HTML_COMMENT_RE` constant — excluded per SCOPE-OUT-006 [OUT-OF-SCOPE].
- Splitting `cli.py` — excluded per SCOPE-OUT-001 [OUT-OF-SCOPE].
- Any edit to R20 / `_DEFERRAL_PATTERNS` — excluded per SCOPE-OUT-002 [OUT-OF-SCOPE].
- Introducing any new gate, field, keyword pattern, CLI command, or abstraction layer — excluded per SCOPE-OUT-003 [OUT-OF-SCOPE].

## Mitigations

- Re-anchor every edit by symbol name; all eight line anchors were re-verified against the working tree at this stage (see RISK-DRIFT-002).
- Commit order isolates risk classes: correctness fix first, pure deletions/dedups second, the symlink-safety pair third (both edits in one commit so the hardening never trades a silent follow for a traceback), the behavior-adjacent dedup last in its own commit. Each commit requires a green full suite via `.venv/bin/python -m pytest tests/ -v`.
- New tests land in the same commit as the behavior they guard: three closure-boundary cases in `tests/test_gates.py`; the `read_regular_text` unit test (FIFO / missing / symlink) in `tests/test_atomic_write.py`; the symlinked-`run.md` shortcut integration test.
- Existing suites act as regression pins for the dedups: `tests/test_cli.py` conflict tests (five handlers, exit 6), `tests/test_agent_shortcuts.py` symlink-block tests (exit 6), `tests/test_install.py` for the `_safe_copy` deletion.

## Trace
<!-- Map this stage's IDs to upstream/downstream. R3 derives & checks closure. -->
| This ID | Upstream | Status |
|---|---|---|
| RISK-GATE-001 | SCOPE-IN-001 [ADDRESSED] | mitigated |
| RISK-DRIFT-002 | SCOPE-IN-001, SCOPE-IN-002, SCOPE-IN-003, SCOPE-IN-004, SCOPE-IN-005, SCOPE-IN-006 [ADDRESSED] | mitigated |
| RISK-COMPAT-003 | SCOPE-IN-005 [ADDRESSED] | mitigated |
| RISK-COMPAT-004 | SCOPE-IN-003 [ADDRESSED] | mitigated |
| RISK-BEHAV-005 | SCOPE-IN-006 [ADDRESSED] | mitigated |
| RISK-DEP-006 | SCOPE-IN-006 [ADDRESSED] | mitigated |
<!-- /r2p-read-only -->

## Project Context (read-only)
# Project Context Pack

- repo_root: `/Users/xubo/x-skills/req-to-plan`
- languages: {'Python': 26256, 'JavaScript': 31}
- package_managers: npm, pip
- test_commands: ['npm test']
- entrypoints: ['tools/workflow_cli/__main__.py']
- config_files: ['requirements.txt']
- dependencies (1):
  - pyyaml>=6.0 (pip)
- source_dirs: ['bin', 'docs', 'requirements', 'tests', 'tools']
<!-- /r2p-read-only -->

---
r2p_stage: spec
r2p_version: 3
r2p_status: approved
r2p_created_at: 2026-07-11T08:06:54.980192+00:00
r2p_updated_at: 2026-07-11T08:13:35.338029+00:00
---

# Spec

## Behavior Contracts

### SPEC-GATE-001 Token-boundary closure matching in quality-gate Check 3
In `gates._find_ids_without_closure`, the closure-search pattern becomes exactly:
```python
pattern = re.compile(
    r"(?<![A-Za-z0-9_-])" + re.escape(ref_id) + r"(?![A-Za-z0-9_-])"
    + r"[^\n]*" + re.escape(tag),
    re.IGNORECASE,
)
```
Contract, on the function's semantic-unfenced input:
1. An upstream ID cited without its own closure tag is reported unclosed even when a longer ID sharing it as a strict prefix is closed on another line (the collision input that pre-fix returned empty now returns the shorter ID), and quality-gate Check 3 fails on such an artifact.
2. Two IDs where one prefixes the other, each followed by a closure tag on its own line: both closed, nothing reported.
3. A line carrying only a suffixed malformed variant of an ID (base ID + `-SUFFIX` + tag) no longer self-closes the base ref: the base ref is reported unclosed (fails-closed on typo'd IDs, intended).
The finder `_UPSTREAM_ID_PATTERN` is not modified; `[^\n]*` same-line vicinity semantics and `re.IGNORECASE` are preserved; no other pattern in `gates.py` changes.

### SPEC-DEAD-002 Dead copy helper removed from install.py
`_safe_copy` (18 lines incl. docstring, plus its blank-line separator) is deleted from `tools/workflow_cli/install.py`. Post-conditions: `grep -rn "_safe_copy" tools tests` outputs nothing; `_safe_write` and every other symbol in the module are untouched; `tests/test_install.py` passes unchanged; zero observable behavior change.

### SPEC-DEDUP-003 Single version-match guard helper in cli.py
`cli.py` gains exactly one module-level helper:
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
The five handlers (`_cmd_run_close` passing `Stage.PLAN`; `_cmd_gate_quality`, `_cmd_review_checkpoint`, `_cmd_checkpoint_decide`, `_cmd_stage_advance` passing their `stage` local) replace their inline 9-line guards with one call each. Contract: on version mismatch every handler prints the byte-identical message (`Active artifact version v<aa> does not match on-disk v<disk>`) and exits 6; on match, behavior is unchanged. The surrounding `aa is None` and status checks stay inline in each handler.

### SPEC-DEDUP-004 Execute path reuses the symlink-rejection helper
In `agent_shortcuts._cmd_execute`, the inline workspace-dir/run-dir symlink checks are replaced by `run_dir = _reject_symlinked_run_paths_or_exit(base_path, work_id)`; the unused `r2p_dir` local is removed. Contract: on a symlinked `.req-to-plan` dir print `blocked: unsafe_workspace_dir_symlink` (+ work_id, path) and exit 6; on a symlinked run dir print `blocked: unsafe_run_dir_symlink` (+ work_id, path) and exit 6 — byte-identical output and ordering (workspace first) to the current inline block; on the safe path, `run_dir` and the downstream `run_path = run_dir / "run.md"` are unchanged.

### SPEC-SAFE-005 Symlink-safe run.md load with clean shortcut exit
Edit A — `state.py` `RunStateManager.load()`: the bare `self.run_path.read_text(encoding="utf-8")` becomes `read_regular_text(self.run_path)` (import extended on the existing `tools.workflow_cli.atomic` import line). Edit B — `agent_shortcuts._load_matching_record_or_exit` gains, alongside its `except FileNotFoundError`:
```python
except UnsafeRegularFileError as exc:
    print(f"blocked: unsafe_run_record\nwork_id: {work_id}\nreason: {exc}\n")
    sys.exit(EXIT_CONFLICT)
```
Contract: a symlinked or non-regular `run.md` (a) via any agent shortcut that loads a specific run prints `blocked: unsafe_run_record` with work_id and reason and exits 6 — never a traceback; (b) via the workflow CLI exits 6 through `cli.main`'s existing `except UnsafeRegularFileError`; (c) via `scan_open_runs` is warned and skipped by the existing `except Exception`. A missing `run.md` keeps its current behavior everywhere (`FileNotFoundError` → existing handlers, e.g. `blocked: source_run_not_found`, exit 7 at shortcuts). A regular `run.md` loads byte-identically to today. Both edits land in the same commit.

### SPEC-DEDUP-006 PLAN-TASK field primitives homed in trace.py
`trace.py` exports three public names: `plan_task_field_re(field)` returning `re.compile(rf"^{re.escape(field)}:[ \t]*(.*)$")`; `find_plan_task_field(body, field)` built on it (returns `(match, start)` or `None`, scanning `unfenced_markdown_lines`); `find_next_plan_task_field_start(body, after)` (moved as-is, uses `PLAN_TASK_FIELD_RE`). `gates.py` deletes its module-local `_find_plan_task_field` and `_find_next_plan_task_field_start`, imports the trace names, and rewrites `_count_plan_task_fields` to compile via `plan_task_field_re`. `trace._plan_task_field_value` (stripped) and `gates._plan_task_field_body` (unstripped) remain as thin wrappers over `find_plan_task_field`. Behavior contract: identical parsing everywhere except trace-side field lines whose colon is followed by whitespace other than space/tab, which stop matching (deliberate canonicalization on `[ \t]*`). Import direction stays one-way: gates imports trace; `trace.py` contains no `gates` import (no cycle). No public name is added anywhere else.

## API / Data / Config Contracts

- No CLI command, flag, argparse surface, exit code, artifact field, frontmatter key, config file, or on-disk format is added, removed, or changed.
- Exit-code behavior changes at exactly two points, both intended hardenings: (1) quality-gate Check 3 now fails (gate surface exit 3) on prefix-collision closure inputs that previously passed; (2) a symlinked/non-regular `run.md` reached via a shortcut now exits 6 with `blocked: unsafe_run_record` instead of being silently followed.
- New public Python names: exactly three, all in `tools/workflow_cli/trace.py` (`plan_task_field_re`, `find_plan_task_field`, `find_next_plan_task_field_start`); one new private helper in `cli.py` (`_require_disk_version_matches`). Nothing else.
- Production files touched, exhaustively: `gates.py`, `install.py`, `cli.py`, `agent_shortcuts.py`, `state.py`, `trace.py` under `tools/workflow_cli/`.

## External Documentation Checked

N/A — no external dependencies

Stdlib-only change set (`re` lookarounds, `os`/`pathlib` already in use); no external library, framework, or API surface is touched, so no external documentation lookup applies.

## Test Matrix

| # | Test | File | New/Existing | Asserts |
|---|---|---|---|---|
| 1 | closure prefix collision | `tests/test_gates.py` | New | collision input → `_find_ids_without_closure` returns the shorter ID; quality-gate Check 3 fails |
| 2 | closure both-closed | `tests/test_gates.py` | New | prefix-related IDs each with own tag → both closed, empty result |
| 3 | closure malformed suffix | `tests/test_gates.py` | New | suffixed-ID-only line → base ref reported unclosed |
| 4 | `read_regular_text` unit | `tests/test_atomic_write.py` | New | FIFO raises `UnsafeRegularFileError`; missing + `missing_ok=True` → `None`; missing + `missing_ok=False` → `FileNotFoundError`; symlink raises (mirrors gates FIFO tests) |
| 5 | symlinked `run.md` shortcut integration | shortcut test module (`tests/test_agent_shortcuts.py`) | New | shortcut command on run with symlinked `run.md` prints `blocked: unsafe_run_record`, exits 6 |
| 6 | five version-conflict handler tests | `tests/test_cli.py` | Existing pin | exit 6 + same message on mismatch, all five handlers |
| 7 | execute symlink-block tests | `tests/test_agent_shortcuts.py` | Existing pin | `unsafe_workspace_dir_symlink` / `unsafe_run_dir_symlink`, exit 6 |
| 8 | install suite | `tests/test_install.py` | Existing pin | green after `_safe_copy` deletion |
| 9 | gates + trace suites | `tests/test_gates.py`, `tests/test_trace.py` | Existing pin | green after field-primitive homing |
| 10 | full suite gate | `tests/` | Existing | `.venv/bin/python -m pytest tests/ -v` green before every commit (local `tomllib` skips expected) |

## Non-goals

Everything the brief excludes stays excluded: `cli.py` split per SCOPE-OUT-001 [OUT-OF-SCOPE]; R20/`_DEFERRAL_PATTERNS` untouched per SCOPE-OUT-002 [OUT-OF-SCOPE]; no new gate/field/pattern/command/layer per SCOPE-OUT-003 [OUT-OF-SCOPE]; PLAN-TASK body-splitters stay separate per SCOPE-OUT-004 [OUT-OF-SCOPE]; DECISION-block field parsers stay separate per SCOPE-OUT-005 [OUT-OF-SCOPE]; `_HTML_COMMENT_RE` stays duplicated per SCOPE-OUT-006 [OUT-OF-SCOPE].

## PLAN Handoff

PLAN decomposes into four tasks matching the four commits, in order, each gated on a green full suite (`.venv/bin/python -m pytest tests/ -v`):
1. SPEC-GATE-001 with its three tests (Test Matrix 1–3) — own commit.
2. SPEC-DEAD-002 + SPEC-DEDUP-003 + SPEC-DEDUP-004 (pure deletions/dedups, zero behavior change; pins are Test Matrix 6–8) — one commit.
3. SPEC-SAFE-005 both edits plus Test Matrix 4–5 — one commit.
4. SPEC-DEDUP-006 (behavior-adjacent; pins are Test Matrix 9; re-confirm no `gates` import appears in `trace.py`) — final commit.
Every edit point is re-located by symbol name at implementation time (anchors verified at design). Batch-final checks: `grep -rn "_safe_copy" tools tests` empty; `git diff --stat` across the four commits shows net production-line decrease and no files outside the six named production files plus the three named test files.

## Trace
<!-- Map this stage's IDs to upstream/downstream. R3 derives & checks closure. -->
| This ID | Upstream | Status |
|---|---|---|
| SPEC-GATE-001 | DES-GATE-001 [ADDRESSED], SCOPE-IN-001 [ADDRESSED] | specified |
| SPEC-DEAD-002 | DES-DEAD-002 [ADDRESSED], SCOPE-IN-002 [ADDRESSED] | specified |
| SPEC-DEDUP-003 | DES-DEDUP-003 [ADDRESSED], SCOPE-IN-003 [ADDRESSED] | specified |
| SPEC-DEDUP-004 | DES-DEDUP-004 [ADDRESSED], SCOPE-IN-004 [ADDRESSED] | specified |
| SPEC-SAFE-005 | DES-SAFE-005 [ADDRESSED], SCOPE-IN-005 [ADDRESSED] | specified |
| SPEC-DEDUP-006 | DES-DEDUP-006 [ADDRESSED], SCOPE-IN-006 [ADDRESSED] | specified |

## Upstream Summary (read-only)
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

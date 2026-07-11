# Requirement Brief

## Goal

Close the one fails-open quality-gate defect (closure-tag prefix collision in `gates._find_ids_without_closure`), close the documented symlink-safety invariant gap on `run.md` loads, and remove dead or duplicated code across `install.py`, `cli.py`, `agent_shortcuts.py`, and the gates/trace PLAN-TASK field parsers. Net effect: production line count decreases (roughly 70–75 lines removed), new guarding tests are added for the two hardenings, and zero new mechanisms, gates, fields, keyword patterns, or validation layers are introduced.

## In-Scope

- SCOPE-IN-001 Fix the fails-open closure match in `gates._find_ids_without_closure` (gates.py, called from quality-gate Check 3): wrap the escaped ref ID in the codebase's canonical two-sided token boundary (lookarounds over `A-Za-z0-9_-`, mirroring `trace._TRACE_TOKEN_CHARS` / `SPEC_ID_RE`), preserving the flexible `[^\n]*` vicinity semantics. Boundary change only; the finder (`_UPSTREAM_ID_PATTERN`) stays untouched, so a malformed suffixed ID line reporting its base ref as unclosed is intended fails-closed behavior. Add three guarding tests in `tests/test_gates.py`: prefix-collision input reports the shorter ID unclosed and fails quality-gate Check 3; both-IDs-closed input passes; malformed-suffix-only input reports the base ref unclosed.
- SCOPE-IN-002 Delete the dead `_safe_copy` helper in `tools/workflow_cli/install.py` (near-verbatim twin of `_safe_write`, zero call sites in `tools/` or `tests/`); pure deletion of about 18 lines, zero behavior change.
- SCOPE-IN-003 Deduplicate the five identical version-match guards in `cli.py` (handlers `_cmd_run_close`, `_cmd_gate_quality`, `_cmd_review_checkpoint`, `_cmd_checkpoint_decide`, `_cmd_stage_advance`) into one narrow helper `_require_disk_version_matches(run_dir, stage, aa)` called from all five sites; extract only the version block, leaving the per-handler `aa is None`/status checks in place.
- SCOPE-IN-004 Replace `_cmd_execute`'s inline workspace/run-dir symlink checks in `agent_shortcuts.py` with the existing `_reject_symlinked_run_paths_or_exit` helper (byte-identical output, already used by three other call sites); drop the now-unused `r2p_dir` local.
- SCOPE-IN-005 Route `RunStateManager.load()` through the symlink-safe `atomic.read_regular_text`, and add the shortcut-idiom `UnsafeRegularFileError` branch (`blocked: unsafe_run_record`, exit 6) to `agent_shortcuts._load_matching_record_or_exit` so a symlinked `run.md` reached via a shortcut exits cleanly instead of raising a traceback. Both edits ship in the same commit. Add two new tests: a focused unit test on `atomic.read_regular_text` (FIFO raises `UnsafeRegularFileError`; missing file honors `missing_ok`; symlink raises) in `tests/test_atomic_write.py`, and an integration test that a symlinked `run.md` makes a shortcut command print `blocked: unsafe_run_record` and exit 6.
- SCOPE-IN-006 Home the shared PLAN-TASK field primitives in `trace.py` as public names — `plan_task_field_re(field)` (canonicalized on gates' tighter `[ \t]*` variant; the one deliberate behavior touch, affecting only trace's parse of exotic-whitespace field lines), `find_plan_task_field`, `find_next_plan_task_field_start` — delete the `gates.py` copies, import the public names from trace, and point gates' `_count_plan_task_fields` at the shared builder. `_plan_task_field_body` (gates, unstripped) and `_plan_task_field_value` (trace, stripped) stay as thin module-local wrappers; the `.strip()` difference is load-bearing. Owner is `trace.py` (gates already imports from trace; no cycle). This item is behavior-adjacent and lands in the final commit of the batch.

## Out-of-Scope

- SCOPE-OUT-001 Splitting `cli.py` (~2489 lines): it is a flat list of ~25 independent `_cmd_*` handlers; a split adds import churn for zero cohesion gain.
- SCOPE-OUT-002 Any change to R20 / `_DEFERRAL_PATTERNS` in `gates.py`: frozen by `CLAUDE.md`, pinned by ~54 tests, load-bearing.
- SCOPE-OUT-003 Any new gate, artifact field, keyword pattern, abstraction layer, CLI command, or validation surface.
- SCOPE-OUT-004 Unifying the two PLAN-TASK body-splitters (`_iter_plan_task_bodies` in gates, `_plan_task_bodies` in trace): their heading regexes are not equivalent; unifying them is a behavior change requiring its own separately-tested decision.
- SCOPE-OUT-005 Unifying the DECISION-block field parsers (`_decision_field_value` / `_decision_field_count` in gates) with the PLAN-TASK field helpers: similar-looking regex but different grammar and domain.
- SCOPE-OUT-006 Deduplicating the `_HTML_COMMENT_RE` one-line constant (gates + trace): nets about zero lines after imports; churn without benefit.

## Non-Goals

This batch removes code; it does not add capability. No new CLI command, gate, artifact field, keyword pattern, validation surface, or abstraction layer anywhere in the diff (see SCOPE-OUT-003). It is not a general refactor of `cli.py`, the Markdown parsing layers, or the gate architecture beyond the six named items; every merge explicitly rejected upstream (SCOPE-OUT-004, SCOPE-OUT-005, SCOPE-OUT-006) stays rejected here.

## Assumptions

- All line anchors in the raw requirement were verified against live code on `main` on 2026-07-11 (three verification rounds, flagship defect empirically reproduced). Implementation still re-locates each anchor by symbol name before editing, since line numbers can drift.
- The local `.venv` is Python 3.10: `tomllib`-dependent tests skip locally and execute on the CI 3.11/3.12 matrix; the test command is `.venv/bin/python -m pytest tests/ -v` (never bare `pytest`).
- The working tree is clean when implementation starts, and the four-commit order from the raw requirement (fix → pure dedups → symlink-safety pair → behavior-adjacent dedup) is followed, each commit gated on a green full suite.

## Acceptance Criteria

1. All new tests specified in SCOPE-IN-001 (three cases in `tests/test_gates.py`) and SCOPE-IN-005 (unit test in `tests/test_atomic_write.py` plus the symlinked-`run.md` integration test) exist and pass; the full suite is green before every commit via `.venv/bin/python -m pytest tests/ -v` (local `tomllib` skips expected).
2. `grep -rn "_safe_copy" tools tests` returns nothing after SCOPE-IN-002.
3. No new CLI command, gate, artifact field, keyword pattern, or abstraction layer is introduced anywhere in the diff (SCOPE-OUT-003 holds).
4. Production line count decreases overall, verified with `git diff --stat` across the batch commits (test files are expected to add lines), and nothing outside the named files changes.
5. Exit-code behavior is unchanged everywhere except the two intended hardenings: quality-gate Check 3 now fails (exit 3 at the gate surface) on prefix-collision inputs that previously passed, and a symlinked `run.md` reached via a shortcut now exits 6 with `blocked: unsafe_run_record` instead of being silently followed or raising a traceback.

## Open Questions

None. Every fork was resolved during the upstream research point's three verification rounds; the remaining choices (canonical regex variant `[ \t]*`, module owner `trace.py`, the six exclusions) are decided in the raw requirement with rationale and carried here unchanged.

## Sources

- `00-raw-requirement.md` — self-contained requirement; folds in the archived research point `code-audit-cleanup` (original file: `.xsk/requirements/code-audit-cleanup.md`).
- Repository `CLAUDE.md` — invariants this batch closes gaps against: symlink-safe trusted reads, token-boundary-aware trace-ID matching, exit-code table, R20 freeze.

## Trace
<!-- Map this stage's IDs to upstream/downstream. R3 derives & checks closure. -->
| This ID | Upstream | Status |
|---|---|---|
| SCOPE-IN-001 | 00-raw-requirement.md · Requirements §1 (fails-open closure match) | open |
| SCOPE-IN-002 | 00-raw-requirement.md · Requirements §2 (dead `_safe_copy`) | open |
| SCOPE-IN-003 | 00-raw-requirement.md · Requirements §3 (version-match guards) | open |
| SCOPE-IN-004 | 00-raw-requirement.md · Requirements §4 (inline symlink checks) | open |
| SCOPE-IN-005 | 00-raw-requirement.md · Requirements §5 (symlink-safe `run.md` loads) | open |
| SCOPE-IN-006 | 00-raw-requirement.md · Requirements §6 (PLAN-TASK field primitives) | open |
| SCOPE-OUT-001 | 00-raw-requirement.md · Scope, out-of-scope bullet 1 | excluded |
| SCOPE-OUT-002 | 00-raw-requirement.md · Scope, out-of-scope bullet 2 | excluded |
| SCOPE-OUT-003 | 00-raw-requirement.md · Scope, out-of-scope bullet 3 | excluded |
| SCOPE-OUT-004 | 00-raw-requirement.md · Scope, out-of-scope bullet 4 | excluded |
| SCOPE-OUT-005 | 00-raw-requirement.md · Scope, out-of-scope bullet 5 | excluded |
| SCOPE-OUT-006 | 00-raw-requirement.md · Scope, out-of-scope bullet 6 | excluded |

## Upstream Summary (read-only)
---
status: active
slug: code-audit-cleanup
created_at: 2026-07-11
---

# Code audit cleanup: one gate bug fix plus five cleanups

## Background

A three-track audit of this repository (correctness, fragility/simplification, test coverage) found exactly one correctness defect and a small set of pure cleanup opportunities. The findings passed three verification rounds against live code on `main`: anchor verification, adversarial re-verification, and empirical reproduction. All line numbers below were confirmed on 2026-07-11. The flagship defect was reproduced by executing the live module, not inferred from reading.

This requirement is self-contained. It folds in the archived research point `code-audit-cleanup`; an implementer needs no other document.

## Goal

Close the one fails-open quality-gate defect, close one documented symlink-safety invariant gap, and remove dead or duplicated code. Net effect: roughly 70 to 75 production lines removed, three new guarding tests, and zero new mechanisms, gates, fields, or validation layers.

## Scope

In scope: requirements 1 through 6 below, exactly as specified, in the stated commit order.

Out of scope (genuine non-goals, each decided with rationale during research):

- Splitting `cli.py` (2489 lines). It is a flat list of ~25 independent `_cmd_*` handlers; a split adds import churn for zero cohesion gain.
- Any change to R20 / `_DEFERRAL_PATTERNS` in `gates.py`. Frozen by `CLAUDE.md`, pinned by ~54 tests, load-bearing.
- Any new gate, field, pattern, abstraction layer, or validation surface.
- Unifying the two PLAN-TASK body-splitters (`_iter_plan_task_bodies` in gates, `_plan_task_bodies` in trace). Their heading regexes are not equivalent (`^### PLAN-TASK-\d+` MULTILINE vs `^###\s+PLAN-TASK-\d+\b`); unifying them is a behavior change that needs its own separately-tested decision and is not wanted here.
- Unifying the DECISION-block field parsers (`_decision_field_value` / `_decision_field_count`, `gates.py:1067/1076`) with the PLAN-TASK field helpers. Similar-looking regex, different grammar and domain (R12 DECISION blocks, stripped lines, `\s*` on purpose).
- Deduplicating the `_HTML_COMMENT_RE` one-line constant (`gates.py:267`, `trace.py:35`). Nets about zero lines after imports (verified: `markdown.py` has no existing equivalent to reuse); churn without benefit.

## Requirements

### 1. Fix the fails-open closure match in `_find_ids_without_closure` (flagship)

**Location**: `tools/workflow_cli/gates.py:459-462`, called from `check_quality_gate` Check 3 (`gates.py:1427`), all tiers, every stage.

**Defect**: the closure-tag search compiles `re.escape(ref_id) + r"[^\n]*" + re.escape(tag)` with no token boundary around the ID. On a line containing `REQ-AUTH-10 [ADDRESSED]`, the search for `REQ-AUTH-1` matches the prefix of `REQ-AUTH-10`, so an unclosed `REQ-AUTH-1` is silently treated as closed. The gate fails open, violating the documented invariant that `SPEC-...-1` is not closed by `SPEC-...-10`. Empirically reproduced on 2026-07-11: the live function returns `[]` on the collision input and correctly returns `["REQ-AUTH-1"]` without the `-10` line.

**Change**: wrap the escaped ID in the codebase's canonical two-sided token boundary (mirrors `trace.py:22` `_TRACE_TOKEN_CHARS = r"A-Za-z0-9_-"`, the idiom `SPEC_ID_RE` uses):

```python
pattern = re.compile(
    r"(?<![A-Za-z0-9_-])" + re.escape(ref_id) + r"(?![A-Za-z0-9_-])"
    + r"[^\n]*" + re.escape(tag),
    re.IGNORECASE,
)
```

Do not use a bare `(?!\d)`: it only covers the digit case and forks a second, weaker boundary convention. Preserve the flexible-spacing `[^\n]*` vicinity semantics; the scope of this change is the boundary only.

**Known behavior edge (intended)**: `_UPSTREAM_ID_PATTERN` uses `\b`, so a malformed line such as `REQ-AUTH-1-FOO [ADDRESSED]` by itself yields the ref `REQ-AUTH-1`, and post-fix that line no longer self-closes, so the gate reports `REQ-AUTH-1` unclosed. This is fails-closed on typo'd IDs and is desired. Do not "fix" the finder to match; boundary scope is the closure search only.

**Tests** (new, in `tests/test_gates.py`; no existing test covers the prefix collision):
1. Artifact citing `REQ-AUTH-1` with no closure tag and containing `REQ-AUTH-10 [ADDRESSED]`: `_find_ids_without_closure` returns `["REQ-AUTH-1"]` and quality-gate Check 3 fails.
2. `REQ-AUTH-1 [ADDRESSED]` alongside `REQ-AUTH-10 [ADDRESSED]`: both closed.
3. `REQ-AUTH-1-FOO [ADDRESSED]` alone: returns `["REQ-AUTH-1"]` (the behavior edge above).

### 2. Delete dead `_safe_copy`

**Location**: `tools/workflow_cli/install.py:1211-1228` (delete through the blank-line separator before `_safe_write` at line 1231).

`_safe_copy` is a near-verbatim twin of `_safe_write` (identical except the final line) with zero call sites anywhere in `tools/` or `tests/`. Pure deletion of about 18 lines, zero behavior change.

**Verification**: `grep -rn "_safe_copy" tools tests` returns nothing after the deletion; `tests/test_install.py` stays green.

### 3. Deduplicate the five identical version-match guards in `cli.py`

**Locations**: message lines at `cli.py:521, 1429, 2071, 2171, 2327`; each guard spans about 9 lines from the preceding `get_artifact_version` assignment (the first is `cli.py:517-525`). Handlers: `_cmd_run_close`, `_cmd_gate_quality`, `_cmd_review_checkpoint`, `_cmd_checkpoint_decide`, `_cmd_stage_advance`.

**Change**: extract one narrow helper and call it from all five sites:

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

The first site passes `Stage.PLAN` explicitly; the others pass their `stage` local.

**Scope discipline**: extract only the version block. Do not fold in the surrounding `aa is None` or status checks; those legitimately vary in message and status set across handlers.

**Verification**: the existing `test_cli.py` conflict tests for all five handlers still return exit 6 on mismatch.

### 4. Replace `_cmd_execute`'s inline symlink checks with the existing helper

**Location**: `tools/workflow_cli/agent_shortcuts.py:1040-1055`.

The inline `r2p_dir.is_symlink()` / `run_dir.is_symlink()` block duplicates, with byte-identical output, the existing `_reject_symlinked_run_paths_or_exit` (defined at `agent_shortcuts.py:105`, already used at lines 637, 932, 1189; it checks the workspace dir first, then the run dir). Replace the block with:

```python
run_dir = _reject_symlinked_run_paths_or_exit(base_path, work_id)
```

The helper returns `base_path / ".req-to-plan" / work_id`, so the downstream `run_path = run_dir / "run.md"` is unchanged. Drop the now-unused `r2p_dir` local; it has no other use in `_cmd_execute` (verified).

**Verification**: the existing `test_agent_shortcuts.py` symlink-block tests for the execute path (`unsafe_workspace_dir_symlink`, `unsafe_run_dir_symlink`, exit 6) still pass.

### 5. Route `run.md` loads through the symlink-safe reader, with a clean shortcut exit

`CLAUDE.md` lists `run.md` among trusted reads that must route through `atomic.read_regular_text`; `RunStateManager.load()` is the single remaining bare `read_text` (the write side is already safe and tested). Two edits, both required in the same commit:

1. `tools/workflow_cli/state.py:615` (inside `load()`, def at line 612): replace the bare read with `text = read_regular_text(self.run_path)`, extending the existing `from tools.workflow_cli.atomic import atomic_write_text` at `state.py:11`. Signature (confirmed at `atomic.py:15`): `read_regular_text(path, *, encoding="utf-8", missing_ok=False) -> str | None`; it raises `UnsafeRegularFileError` on a non-regular or symlinked source and `FileNotFoundError` on a missing one, so existing `FileNotFoundError` handlers are unaffected.
2. `tools/workflow_cli/agent_shortcuts.py:118-124`: `_load_matching_record_or_exit` catches only `FileNotFoundError`, and `agent_shortcuts.main()` has no catch-all, so without this edit a symlinked `run.md` reached via a shortcut surfaces as a raw traceback. Add the shortcut-idiom branch (`UnsafeRegularFileError` is already imported at line 21):

```python
except UnsafeRegularFileError as exc:
    print(f"blocked: unsafe_run_record\nwork_id: {work_id}\nreason: {exc}\n")
    sys.exit(EXIT_CONFLICT)
```

Coverage is exhaustive (verified): every shortcut `load()` routes through this one helper (call sites at lines 939, 1063, 1197, plus `_cmd_continue`'s loop at line 648) or through `scan_open_runs`, which already wraps `load()` in `except Exception` (warning plus skip; a symlinked `run.md` there changes from silently followed to warned-and-skipped, which is acceptable and needs no code change). `get_active_artifact` takes an already-loaded `RunRecord` and never loads. The CLI surface is already covered by `cli.main`'s `except UnsafeRegularFileError` at `cli.py:2481` (exit 6).

**Tests** (new):
1. Focused unit test on `atomic.read_regular_text` (currently never referenced by name in any test; its FIFO/non-regular branch is exercised only on the parallel twin `gates._read_regular_text_no_symlink` at `gates.py:1710`, so the two implementations can silently drift). Assert: FIFO (`os.mkfifo`) raises `UnsafeRegularFileError`; missing file with `missing_ok=True` returns `None` and with `missing_ok=False` raises `FileNotFoundError`; symlink raises. Mirror the existing gates FIFO tests. Place in `tests/test_atomic_write.py`.
2. Integration test: a symlinked `run.md` in an otherwise-valid run dir makes a shortcut command (for example `execute`) print `blocked: unsafe_run_record` and exit 6.

### 6. Home the shared PLAN-TASK field primitives in `trace.py` (behavior-adjacent, do last)

The PLAN-TASK field parsing primitives are duplicated across `gates.py` and `trace.py`, and the copies have already drifted once: gates compiles `rf"^{re.escape(field)}:[ \t]*(.*)$"` (`gates.py:575`), trace compiles `rf"^{re.escape(field)}:\s*(.*)$"` (`trace.py:134`). On the per-line input from `unfenced_markdown_lines` the difference is exotic whitespace only, but it is exactly the silent-drift failure mode this dedup retires.

**Change**:
- Add to `trace.py` a public pattern builder and home the two shared functions there as public names:
  - `def plan_task_field_re(field): return re.compile(rf"^{re.escape(field)}:[ \t]*(.*)$")` (canonicalized on gates' tighter `[ \t]*` variant; this is the one deliberate behavior touch in the whole batch, affecting only trace's parse of exotic-whitespace field lines).
  - `find_plan_task_field` (from `gates.py:574` / `trace.py:133`), using the builder.
  - `find_next_plan_task_field_start` (from `gates.py:592` / `trace.py:142`, byte-identical copies; both use `PLAN_TASK_FIELD_RE`, which trace already imports at `trace.py:19`).
- Delete the `gates.py` copies and import the public names from trace. Point gates' `_count_plan_task_fields` (`gates.py:583-589`, the third same-grammar copy of the field pattern) at `plan_task_field_re` as well.
- Owner is `trace.py`, not `markdown.py`: homing in markdown would add a new `markdown -> stage_schema` dependency edge, while trace-as-owner adds zero new edges (gates already imports from trace, for example `SPEC_ID_RE` at `gates.py:39`; trace does not import gates, so no cycle).

**Keep as-is (load-bearing differences, do not merge)**:
- `_plan_task_field_body` (gates, unstripped, needed for Skeleton/fence detection) and `_plan_task_field_value` (trace, stripped). Both stay as thin module-local wrappers over the shared function; the `.strip()` difference is load-bearing.
- The body-splitters (see Scope, out of scope).

**Verification**: full suite, especially `tests/test_gates.py` and `tests/test_trace.py`. This is the only behavior-adjacent item; it lands last in its own commit.

## Acceptance criteria

1. All three new tests from requirements 1 and 5 exist and pass; the full suite is green before every commit: `.venv/bin/python -m pytest tests/ -v`. The local `.venv` is Python 3.10, so a few `tomllib`-dependent tests skip; that is expected, not a failure (they run on the CI 3.11/3.12 matrix). Never use bare `pytest`.
2. `grep -rn "_safe_copy" tools tests` returns nothing.
3. No new CLI command, gate, artifact field, keyword pattern, or abstraction layer is introduced anywhere in the diff.
4. Production line count decreases overall (verify with `git diff --stat` across the four commits; tests are expected to add lines).
5. Exit-code behavior is unchanged everywhere except the two intended hardenings: the requirement 1 gate now fails (exit 3 at the gate surface) on prefix-collision inputs that previously passed, and a symlinked `run.md` now exits 6 with a clean message instead of being silently followed.

## Checkpoints

Four commits, in this order, each gated on a green full suite:

1. Requirement 1 (bug fix plus its tests). Own commit; a correctness fix deserves clear history.
2. Requirements 2, 3, 4 (deletions and dedups, zero behavior change). One commit, or split if preferred.
3. Requirement 5 (two production edits plus two tests, shipped together; edit 2 exists so edit 1 cannot trade a silent follow for a traceback).
4. Requirement 6 (behavior-adjacent dedup). Last, own commit; confirm no import cycle (gates imports from trace; trace must not import gates).

Final gate: review `git diff --stat` across all four commits and confirm the net production-line count went down and nothing outside the named files changed.

## Open questions

None. Every fork was resolved during the point's three verification rounds; the remaining choices in this document (canonical regex variant, module owner, non-goals) are decided above with rationale.
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

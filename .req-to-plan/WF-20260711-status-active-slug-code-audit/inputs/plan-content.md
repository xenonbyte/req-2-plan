# Plan

## Tasks
<!-- Granularity: one PLAN-TASK = one implementer subagent, one task-reviewer; split a task spanning too many files/behaviors, merge only one indivisible behavior. -->

### PLAN-TASK-001 Token-boundary closure match in quality-gate Check 3, with its three guarding tests
Spec References: SPEC-GATE-001
Change Type: modify
TDD Applicable: yes
Files:
- tools/workflow_cli/gates.py
- tests/test_gates.py
Skeleton:
```python
# gates.py — inside _find_ids_without_closure, replace only the pattern construction:
pattern = re.compile(
    r"(?<![A-Za-z0-9_-])" + re.escape(ref_id) + r"(?![A-Za-z0-9_-])"
    + r"[^\n]*" + re.escape(tag),
    re.IGNORECASE,
)

# tests/test_gates.py — three new tests (collision IDs used as literals inside test bodies):
def test_closure_prefix_collision_reports_shorter_id_unclosed(): ...
def test_closure_prefix_related_ids_each_closed(): ...
def test_closure_malformed_suffix_reports_base_ref_unclosed(): ...
```
Steps:
- [ ] Write the three tests first (collision input expects the shorter ID returned and quality-gate Check 3 failing; both-closed input expects empty result; suffixed-malformed-ID-only input expects the base ref returned) and watch the collision test fail against current code
- [ ] Re-locate the pattern by symbol (`_find_ids_without_closure`, currently gates.py:459-462) and apply the two-sided token boundary exactly as in the Skeleton; touch no other pattern, leave `_UPSTREAM_ID_PATTERN` untouched
- [ ] Run the targeted tests, then the full suite; commit as the batch's first commit (correctness fix + its tests only)
Verification: (1) targeted: `.venv/bin/python -m pytest tests/test_gates.py -v -k closure` — the three new tests pass; (2) full suite `.venv/bin/python -m pytest tests/ -v` green (local `tomllib` skips expected) before the commit; (3) evidence: paste output showing pass counts and zero failures.

### PLAN-TASK-002 Three pure dedups: delete dead copy helper, extract version-match guard, reuse symlink-rejection helper
Spec References: SPEC-DEAD-002, SPEC-DEDUP-003, SPEC-DEDUP-004
Change Type: modify
TDD Applicable: no
Files:
- tools/workflow_cli/install.py
- tools/workflow_cli/cli.py
- tools/workflow_cli/agent_shortcuts.py
Skeleton:
```python
# install.py — delete _safe_copy (currently 1211-1228 + separator blanks); nothing else.

# cli.py — one new module-level helper, called from the five handlers:
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
# call sites: _cmd_run_close -> (run_dir, Stage.PLAN, aa); _cmd_gate_quality /
# _cmd_review_checkpoint / _cmd_checkpoint_decide / _cmd_stage_advance -> (run_dir, stage, aa)

# agent_shortcuts.py — inside _cmd_execute, replace the inline symlink checks with:
run_dir = _reject_symlinked_run_paths_or_exit(base_path, work_id)
# and drop the now-unused r2p_dir local.
```
Steps:
- [ ] Delete `_safe_copy` from install.py (re-locate by symbol name); confirm `grep -rn "_safe_copy" tools tests` outputs nothing
- [ ] Add `_require_disk_version_matches` to cli.py and replace the five inline guards (message lines currently at cli.py:521, 1429, 2071, 2171, 2327); extract only the version block, leave `aa is None`/status checks inline
- [ ] In `_cmd_execute`, swap the inline workspace/run-dir symlink block for the helper call and remove `r2p_dir`
- [ ] Run targeted suites, then the full suite; commit as the batch's second commit (zero behavior change)
Verification: (1) targeted: `.venv/bin/python -m pytest tests/test_install.py tests/test_cli.py tests/test_agent_shortcuts.py -v` — five version-conflict tests still exit 6 with the same message, execute symlink-block tests still pass; (2) `grep -rn "_safe_copy" tools tests` empty; (3) full suite green before the commit; evidence pasted.

### PLAN-TASK-003 Symlink-safe run.md loads with clean shortcut exit, plus its two tests
Spec References: SPEC-SAFE-005
Change Type: modify
TDD Applicable: yes
Files:
- tools/workflow_cli/state.py
- tools/workflow_cli/agent_shortcuts.py
- tests/test_atomic_write.py
- tests/test_agent_shortcuts.py
Skeleton:
```python
# state.py — extend the existing atomic import, then in RunStateManager.load():
from tools.workflow_cli.atomic import atomic_write_text, read_regular_text
text = read_regular_text(self.run_path)   # replaces the bare read_text

# agent_shortcuts.py — in _load_matching_record_or_exit, alongside except FileNotFoundError:
except UnsafeRegularFileError as exc:
    print(f"blocked: unsafe_run_record\nwork_id: {work_id}\nreason: {exc}\n")
    sys.exit(EXIT_CONFLICT)

# tests/test_atomic_write.py — unit tests mirroring the gates FIFO tests:
def test_read_regular_text_rejects_fifo(): ...          # os.mkfifo -> UnsafeRegularFileError
def test_read_regular_text_missing_ok_semantics(): ...  # True -> None; False -> FileNotFoundError
def test_read_regular_text_rejects_symlink(): ...

# tests/test_agent_shortcuts.py — integration:
def test_execute_blocks_symlinked_run_record(): ...     # prints blocked: unsafe_run_record, exit 6
```
Steps:
- [ ] Write the `read_regular_text` unit tests (FIFO via `os.mkfifo` with the existing skipif guard; missing with both `missing_ok` values; symlinked source) and the integration test (otherwise-valid run dir whose `run.md` is a symlink; shortcut command prints `blocked: unsafe_run_record` and exits 6)
- [ ] Apply Edit A (state.py bare read → `read_regular_text`) and Edit B (the `UnsafeRegularFileError` branch in `_load_matching_record_or_exit`) — both edits belong to this one commit so the hardening never trades a silent follow for a traceback
- [ ] Run targeted tests, then the full suite; commit as the batch's third commit
Verification: (1) targeted: `.venv/bin/python -m pytest tests/test_atomic_write.py tests/test_agent_shortcuts.py -v` — new unit + integration tests pass, existing shortcut tests unaffected; (2) full suite green before the commit; evidence pasted (missing-`run.md` behavior unchanged: `blocked: source_run_not_found`, exit 7).

### PLAN-TASK-004 Home the PLAN-TASK field primitives in trace.py and point gates at them
Spec References: SPEC-DEDUP-006
Change Type: modify
TDD Applicable: no
Files:
- tools/workflow_cli/trace.py
- tools/workflow_cli/gates.py
Skeleton:
```python
# trace.py — three public names (canonical [ \t]* variant):
def plan_task_field_re(field):
    return re.compile(rf"^{re.escape(field)}:[ \t]*(.*)$")

def find_plan_task_field(body, field):
    field_re = plan_task_field_re(field)
    for line, start, _ in unfenced_markdown_lines(body):
        m = field_re.match(line)
        if m:
            return m, start
    return None

def find_next_plan_task_field_start(body, after):
    for line, start, _ in unfenced_markdown_lines(body):
        if start >= after and PLAN_TASK_FIELD_RE.match(line):
            return start
    return None

# trace.py — _plan_task_field_value becomes a thin wrapper over find_plan_task_field (keeps .strip()).
# gates.py — delete _find_plan_task_field / _find_next_plan_task_field_start, import the trace
# names, keep _plan_task_field_body as a thin unstripped wrapper, and rewrite
# _count_plan_task_fields to compile via plan_task_field_re.
```
Steps:
- [ ] Add the three public functions to trace.py; convert trace's `_plan_task_field_value` to use `find_plan_task_field` (its `.strip()` stays)
- [ ] Delete the gates.py copies, import the public names from trace, keep `_plan_task_field_body` unstripped, point `_count_plan_task_fields` at `plan_task_field_re`
- [ ] Confirm import direction stays one-way: `grep -n "import" tools/workflow_cli/trace.py` shows no `gates` import
- [ ] Run targeted suites, then the full suite; commit as the batch's fourth and last commit; then run the batch-final checks (`git diff --stat` across the four commits: net production-line decrease; changed files limited to the six production files plus tests/test_gates.py, tests/test_atomic_write.py, tests/test_agent_shortcuts.py)
Verification: (1) targeted: `.venv/bin/python -m pytest tests/test_gates.py tests/test_trace.py -v` — both suites green (the one deliberate behavior touch is trace-side exotic-whitespace field lines, covered by these suites); (2) full suite green before the commit; (3) no `gates` import in trace.py; evidence pasted including the `git diff --stat` batch-final summary.

## Execution Readiness
- Requirement brief reviewed; all six in-scope items decomposed into the four tasks above
- Design decisions resolved; decision requests: none
- High-risk mitigations represented in tasks (see Risk Handling)
- Non-goals protected: no task touches anything excluded by the brief's Out-of-Scope list
- Verification commands executable as written (`.venv/bin/python -m pytest …`, `grep`, `git diff --stat`); expected changed files listed per task
- No unresolved ambiguity; out-of-scope work is declared in the brief, not dropped here

## Risk Handling
<!-- optional risk-to-task map; RISK-* IDs live in cells only, each row carries a same-line closure tag -->
| Risk | Handling Task | Closure |
|---|---|---|
| RISK-GATE-001 | PLAN-TASK-001 | [ADDRESSED] |
| RISK-DRIFT-002 | PLAN-TASK-001, PLAN-TASK-002, PLAN-TASK-003, PLAN-TASK-004 (re-locate by symbol name) | [ADDRESSED] |
| RISK-COMPAT-003 | PLAN-TASK-003 | [ADDRESSED] |
| RISK-COMPAT-004 | PLAN-TASK-002 | [ADDRESSED] |
| RISK-BEHAV-005 | PLAN-TASK-004 | [ADDRESSED] |
| RISK-DEP-006 | PLAN-TASK-004 | [ADDRESSED] |

## Trace
<!-- Map this stage's IDs to upstream/downstream. R3 derives & checks closure. -->
| This ID | Upstream | Status |
|---|---|---|
| PLAN-TASK-001 | SPEC-GATE-001 [ADDRESSED], SCOPE-IN-001 [ADDRESSED] | planned |
| PLAN-TASK-002 | SPEC-DEAD-002 [ADDRESSED], SCOPE-IN-002 [ADDRESSED], SPEC-DEDUP-003 [ADDRESSED], SCOPE-IN-003 [ADDRESSED], SPEC-DEDUP-004 [ADDRESSED], SCOPE-IN-004 [ADDRESSED] | planned |
| PLAN-TASK-003 | SPEC-SAFE-005 [ADDRESSED], SCOPE-IN-005 [ADDRESSED] | planned |
| PLAN-TASK-004 | SPEC-DEDUP-006 [ADDRESSED], SCOPE-IN-006 [ADDRESSED] | planned |

## Upstream Summary (read-only)
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

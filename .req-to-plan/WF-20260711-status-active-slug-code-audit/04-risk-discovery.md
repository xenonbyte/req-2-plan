---
r2p_stage: risk_discovery
r2p_version: 1
r2p_status: approved
r2p_created_at: 2026-07-11T07:53:56.838065+00:00
r2p_updated_at: 2026-07-11T07:54:05.231568+00:00
---

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

## Upstream Summary (read-only)
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

---
r2p_stage: plan
r2p_version: 1
r2p_status: approved
r2p_created_at: 2026-06-25T19:04:49.947325+00:00
r2p_updated_at: 2026-06-25T19:15:08.440143+00:00
---

# Plan

## Tasks
### PLAN-TASK-001 — plan-task-brief read-only CLI command
Spec References: SPEC-CLI-001
Change Type: modify
TDD Applicable: yes
Files:
- tools/workflow_cli/cli.py
- tests/test_cli.py
Skeleton:
```python
# tools/workflow_cli/cli.py — new read-only subcommand handler
def _cmd_plan_task_brief(args):
    record, mgr, run_dir = _load_run(args.work_id, args.base_path)
    if record.status != RunStatus.EXECUTING:
        print_and_exit(format_error("plan-task-brief requires an EXECUTING run",
                                    exit_code=EXIT_CONFLICT), EXIT_CONFLICT)
    try:
        plan_text = strip_readonly_sections(read_artifact(run_dir, Stage.PLAN))
    except FileNotFoundError:
        print_and_exit(format_error("PLAN artifact not found",
                                    exit_code=EXIT_NOT_FOUND), EXIT_NOT_FOUND)
    anchors = plan_task_anchors(plan_text)               # [(task_id, title), ...]
    bodies = heading_bounded_bodies(plan_text, PLAN_TASK_ANCHOR_RE.match)
    target = next(((tid, body) for (tid, _t), body in zip(anchors, bodies)
                   if int(re.match(r"PLAN-TASK-(\d+)", tid).group(1)) == args.task), None)
    if target is None:                                   # out of range -> not found
        print_and_exit(format_error(f"task {args.task} not found in PLAN",
                                    exit_code=EXIT_NOT_FOUND), EXIT_NOT_FOUND)
    task_id, body = target
    logs_dir = run_dir / "logs"
    _reject_symlink_or_exit(logs_dir, "logs dir is a symlink")
    brief_path = logs_dir / f"task-{args.task}-brief.md"
    _reject_symlink_or_exit(brief_path, "brief target is a symlink")
    logs_dir.mkdir(parents=True, exist_ok=True)
    atomic_write_text(brief_path, body)
    rel = brief_path.relative_to(run_dir.parent.parent)  # repo-root-relative (base-path independent)
    print_and_exit(format_success({"work_id": args.work_id, "task_id": task_id,
                                   "brief_path": str(rel)},
                                  message="task brief written"), EXIT_OK)
# register "plan-task-brief" in the CLI parser: --work-id required; --task uses a positive-int
# type that rejects values < 1 (the argparse type error exits EXIT_CLI_ERR)
```
Steps:
- [ ] Write a failing test in tests/test_cli.py: on an EXECUTING run seeded with a multi-task PLAN, `plan-task-brief --task 2` writes `logs/task-2-brief.md` holding exactly that task body and the success payload carries work_id, task_id, brief_path.
- [ ] Implement `_cmd_plan_task_brief` and register `plan-task-brief` in the relevant `_register_*_commands`, reusing `plan_task_anchors`, `heading_bounded_bodies`, `PLAN_TASK_ANCHOR_RE`, `strip_readonly_sections`, `_reject_symlink_or_exit`, `atomic_write_text`, and `format_success`.
- [ ] Add tests: non-EXECUTING run gives EXIT_CONFLICT and writes no file; a symlinked `logs/` directory gives EXIT_CONFLICT; a pre-existing symlinked `logs/task-N-brief.md` target gives EXIT_CONFLICT and does not write through the link; out-of-range `--task` gives EXIT_NOT_FOUND; non-positive `--task` gives EXIT_CLI_ERR; a zero-padded `### PLAN-TASK-002` is resolved by `--task 2` with task_id "PLAN-TASK-002".
- [ ] Assert the written body is byte-identical to the gate's `heading_bounded_bodies` slice for that task.
Verification: `.venv/bin/python -m pytest tests/test_cli.py -v -k plan_task_brief` passes for all new cases and `.venv/bin/python -m pytest tests/` stays green.
Carries SCOPE-IN-001.

### PLAN-TASK-002 — create the r2p-task-brief wrapper
Spec References: SPEC-SURFACE-001
Change Type: create
TDD Applicable: no
Files:
- tools/r2p-task-brief
Skeleton:
```bash
#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
export PYTHONPATH="$REPO_ROOT${PYTHONPATH:+:$PYTHONPATH}"
if command -v python3 >/dev/null 2>&1; then
    exec python3 -m tools.workflow_cli.agent_shortcuts task-brief "$@"
else
    exec python -m tools.workflow_cli.agent_shortcuts task-brief "$@"
fi
```
Steps:
- [ ] Create tools/r2p-task-brief with the standard wrapper body delegating to `agent_shortcuts task-brief`, matching the existing tools/r2p-* scripts.
- [ ] Mark it executable so the install.py `tools/r2p-*` glob discovers and installs it like the others.
Verification: `test -x tools/r2p-task-brief` succeeds, `grep -q 'agent_shortcuts task-brief' tools/r2p-task-brief` succeeds, and `.venv/bin/python -m pytest tests/` stays green.
Carries SCOPE-IN-001.

### PLAN-TASK-003 — task-brief shortcut and surface equivalence tests
Spec References: SPEC-SURFACE-001
Change Type: modify
TDD Applicable: yes
Files:
- tools/workflow_cli/agent_shortcuts.py
- tests/test_cli.py
Skeleton:
```python
# tools/workflow_cli/agent_shortcuts.py — new shortcut delegating to the CLI subcommand.
# Handlers take (ns, base_path); main() always sys.exit(0), so a delegating handler must
# capture the CLI exit code and re-exit on non-zero (the established delegation pattern).
def _cmd_task_brief(ns, base_path):
    exit_code = _run_cli(["plan-task-brief", "--work-id", ns.work_id,
                          "--task", str(ns.task)], base_path)
    if exit_code != 0:
        sys.exit(exit_code)
# register "task-brief" (--work-id, --task) in the shortcut parser AND the handlers dict
```
Steps:
- [ ] Write failing tests asserting the `task-brief` shortcut returns the identical JSON payload, written file, and exit code as the direct `plan-task-brief` CLI — on both an EXECUTING happy path (exit 0) and at least one non-zero path (e.g. a non-EXECUTING run where both exit EXIT_CONFLICT), proving exit-code propagation.
- [ ] Cover the `tools/r2p-task-brief` wrapper (from PLAN-TASK-002) two ways: (1) structural — assert it is discovered/installed and its body delegates to `agent_shortcuts task-brief` (grep), per the existing install wrapper-coverage test; (2) end-to-end — subprocess-run the wrapper and assert identical JSON, file, and exit code as the CLI, making `python3` resolve to a dependency-complete interpreter by prepending to PATH a temp dir whose `python3` symlinks to `sys.executable` (never a hardcoded `.venv/bin`, which may be absent on CI); the wrapper sets its own PYTHONPATH. Build the child env explicitly (`env={**os.environ, "PATH": tmp + os.pathsep + os.environ["PATH"]}`, never clearing it) and keep the temp `python3` symlink executable.
- [ ] Implement the `task-brief` shortcut delegating to `plan-task-brief` via `_run_cli`, capturing and re-exiting the CLI exit code so non-zero statuses propagate (main() otherwise exits 0).
Verification: `.venv/bin/python -m pytest tests/test_cli.py -v -k task_brief` passes (shortcut equivalence, wrapper delegation, and wrapper end-to-end green) and `.venv/bin/python -m pytest tests/` stays green.
Carries SCOPE-IN-001.

### PLAN-TASK-004 — FR-CM1 through FR-CM4 prose on both surfaces plus token guard
Spec References: SPEC-PROSE-001, SPEC-PROSE-002, SPEC-PROSE-003, SPEC-PROSE-004, SPEC-GUARD-001
Change Type: modify
TDD Applicable: yes
Files:
- tools/workflow_cli/agent_templates/claude/commands/r2p-execute.md
- tools/workflow_cli/agent_templates/codex/skills/r2p-execute/SKILL.md
- tests/test_docs_consistency.py
Skeleton:
```python
# tests/test_docs_consistency.py — extend the execute-surface token gate (write red first)
REQUIRED_FR_CM_TOKENS = [
    "plan-task-brief",            # FR-CM1: the loop routes the handoff through the brief
    "task-brief",                 # the brief-file handoff / shortcut
    "brief_path",                 # FR-CM1: both dispatches use the returned brief path
    "not pasted task text",       # FR-CM1: guards against reverting to inline handoff
    "Resolved:", "Gap:", "Unresolved:",   # FR-CM3 adjudication markers
    "Narration:",                 # FR-CM2 narration ceiling
    "Minor:",                     # FR-CM4: the carried-forward minor-findings marker (absent pre-edit)
]
def test_execute_surfaces_carry_fr_cm_tokens():
    for surface in EXECUTE_SURFACES:          # the claude command and the codex SKILL
        text = surface.read_text(encoding="utf-8")
        for token in REQUIRED_FR_CM_TOKENS:
            assert token in text, f"{surface}: missing {token}"
        assert "r2p-gap-open" not in text     # execution runs are closed
```
Steps:
- [ ] Add the failing token assertions to tests/test_docs_consistency.py (red): require the FR-CM token set on both r2p-execute surfaces, including the exact `brief_path` and `not pasted task text` handoff tokens, preserve the existing FR-A / SDD tokens, and keep asserting neither surface mentions the gap-open route.
- [ ] Edit the claude r2p-execute command: the loop runs `plan-task-brief` and hands the brief path; the implementer and reviewer dispatches pass the brief path (not pasted task text); add the minimal implementer return contract, the FR-CM2 narration ceiling, the FR-CM3 warning adjudication recording Resolved/Gap/Unresolved before the flip, and the FR-CM4 Minor carry-forward.
- [ ] Mirror the same prose edits into the codex r2p-execute SKILL so both surfaces carry an equivalent token set.
- [ ] Finalize the exact token literals against the authored prose so the test and both surfaces agree; every guard token must be distinctive (absent from both templates before this edit) so it actually proves the new prose landed.
Verification: `.venv/bin/python -m pytest tests/test_docs_consistency.py -v` passes and `.venv/bin/python -m pytest tests/` stays green.
Carries SCOPE-IN-002, SCOPE-IN-003, SCOPE-IN-004, SCOPE-IN-005, SCOPE-IN-006.

## Trace
| This ID | Upstream | Status |
|---|---|---|
| PLAN-TASK-001 | SPEC-CLI-001, SCOPE-IN-001 | open — ready for execution |
| PLAN-TASK-002 | SPEC-SURFACE-001, SCOPE-IN-001 | open — ready for execution |
| PLAN-TASK-003 | SPEC-SURFACE-001, SCOPE-IN-001 | open — ready for execution |
| PLAN-TASK-004 | SPEC-PROSE-001, SPEC-PROSE-002, SPEC-PROSE-003, SPEC-PROSE-004, SPEC-GUARD-001, SCOPE-IN-002, SCOPE-IN-003, SCOPE-IN-004, SCOPE-IN-005, SCOPE-IN-006 | open — ready for execution |

## Upstream Summary (read-only)
# Spec

## Behavior Contracts

### SPEC-CLI-001 — `plan-task-brief` read-only extraction command
Implements DES-CLI-001 [ADDRESSED]; closes SCOPE-IN-001.
- Precondition: the run status must be EXECUTING. On any other status the command prints an error and exits EXIT_CONFLICT (6) **without writing any file**.
- Not found: an unknown `--work-id`, a missing PLAN artifact, or a `--task N` whose anchor does not exist exits EXIT_NOT_FOUND (7).
- Argument error: a missing or non-positive / non-integer `--task` exits EXIT_CLI_ERR (2).
- Task resolution: `--task N` maps to the literal anchor `### PLAN-TASK-<N>` resolved from `plan_task_anchors(strip_readonly_sections(plan_text))`; because the PLAN gate guarantees unique, contiguous-from-1 numbering, an in-range integer resolves to exactly one anchor.
- Extraction: the written body is exactly the `heading_bounded_bodies` slice for that anchor — byte-identical to what the PLAN gate counts as the task body — with no truncation or reflow.
- Symlink rejection: if the run's logs directory or target brief path is a symlink, the command exits EXIT_CONFLICT (6) without writing through the link (mirrors `_reject_symlink_or_exit`).
- Write: the body is written with `atomic_write_text` to `.req-to-plan/<id>/logs/task-<N>-brief.md`; re-running overwrites idempotently.
- No state mutation: `run.md`, the run status, and all artifacts are untouched.

### SPEC-SURFACE-001 — `task-brief` shortcut and `r2p-task-brief` wrapper
Implements DES-CLI-001 [ADDRESSED]; closes SCOPE-IN-001.
- `agent_shortcuts.py` gains a `task-brief` subcommand that delegates to the CLI `plan-task-brief` via `_run_cli`, preserving its exit code and stdout verbatim.
- A `tools/r2p-task-brief` wrapper (auto-discovered by the `install.py` `tools/r2p-*` glob, installed like the other wrappers) invokes the shortcut.
- Equivalence: invoking via the wrapper or the shortcut yields the identical JSON payload, the identical written file, and the identical exit code as the direct CLI call.

### SPEC-PROSE-001 — FR-CM1 task handoff as a brief file
Implements DES-PROSE-001 [ADDRESSED]; closes SCOPE-IN-002. Applies to both r2p-execute surfaces.
- The per-task loop's first step runs `plan-task-brief` for the current task and uses the returned `brief_path`.
- The implementer dispatch hands the `brief_path` (not pasted task text) plus scene-setting context and a report-file path.
- The reviewer dispatch hands the `brief_path` plus the task's Spec References and the diff-file path (not pasted task text).
- The implementer return contract is minimal: a status (DONE / DONE_WITH_CONCERNS / NEEDS_CONTEXT / BLOCKED) plus the report-file path; the controller does not ask the implementer to restate the task.
- The controller uses the returned `brief_path` without eager-reading the full task body into its own context; the implementer and reviewer read the brief on demand.

### SPEC-PROSE-002 — FR-CM2 controller narration ceiling
Implements DES-PROSE-001 [ADDRESSED]; closes SCOPE-IN-003. Applies to both surfaces.
- Between tool calls the controller narrates at most one short line (the FR-CM2 `Narration:` discipline — that label is the load-bearing token pinned in the PLAN), and never pastes a subagent's returned text into a later dispatch; what it restates into its own context is bounded to a status plus a pointer to the report or diff file.

### SPEC-PROSE-003 — FR-CM3 reviewer warning adjudication before the flip
Implements DES-PROSE-001 [ADDRESSED]; closes SCOPE-IN-004. Applies to both surfaces.
- For each reviewer "cannot verify from diff" warning, before flipping the task's checkbox the controller records one line per finding in `execution/progress.md`: `Resolved: ...`, `Gap: ...`, or `Unresolved: ...`.
- Only `Resolved:` clears the warning; a `Resolved:` claim about unchanged code must cite implementation and test evidence.
- `Gap:` and `Unresolved:` block the flip and cannot be overridden on the controller's own judgment.
- These markers are agent-judgment records; no machine gate reads them (they are inert to the ledger regexes), so the trust/audit boundary is unchanged.

### SPEC-PROSE-004 — FR-CM4 Minor findings carried to the final review
Implements DES-PROSE-001 [ADDRESSED]; closes SCOPE-IN-005. Applies to both surfaces.
- Minor reviewer findings not fixed within a task are recorded and carried into the final whole-branch review's input rather than dropped per task.

### SPEC-GUARD-001 — docs-consistency token coverage
Implements DES-GUARD-001 [ADDRESSED]; closes SCOPE-IN-006.
- `tests/test_docs_consistency.py` asserts both r2p-execute surfaces carry the new FR-CM load-bearing tokens, preserves the existing FR-A / SDD token set, and keeps asserting neither surface mentions the gap-open route.
- Required token set (semantic; exact literals pinned in the PLAN against the authored prose): `plan-task-brief`; the brief-file handoff (`task-` brief path / `brief_path`); the FR-CM3 markers `Resolved:` / `Gap:` / `Unresolved:`; the FR-CM2 narration-ceiling phrasing; the FR-CM4 carry-to-final-review phrasing.

## API / Data / Config Contracts

`plan-task-brief` command interface:
- Arguments: `--work-id <work-id>` (required), `--task <N>` (required, positive integer).
- Exit codes: `0` success; `2` cli error (missing or non-positive `--task`); `6` conflict (status not EXECUTING, or a symlinked logs directory / target brief path); `7` not found (unknown work-id, missing PLAN, or task N out of range).
- stdout on success: the command uses the shared `format_success` helper, so the success payload carries at least the three data keys `{work_id, task_id, brief_path}` alongside the standard `status` and `message` fields. Under `R2P_JSON=1` the output is the JSON object `{"status": "ok", "message": "...", "work_id": "<id>", "task_id": "PLAN-TASK-<NNN>", "brief_path": ".req-to-plan/<id>/logs/task-<N>-brief.md"}`; in plain mode the same three values appear as labeled lines. `task_id` is the literal matched anchor text (zero-padding as the PLAN authored it, taken from the `plan_task_anchors` group); `brief_path` is repo-root-relative POSIX.
- File output: `.req-to-plan/<id>/logs/task-<N>-brief.md`, content = the verbatim single PLAN-TASK body.
- The three data fields are part of the success payload in both modes — JSON object keys under `R2P_JSON=1`, labeled lines otherwise — never replacing the standard envelope; no other config or environment input beyond the `--base-path` / `R2P_JSON` envelope shared by all subcommands.

## External Documentation Checked

N/A — no external dependencies

The change adds no new runtime dependency: `plan-task-brief` uses Python stdlib `argparse` and `json` plus existing internal modules (`markdown.py`, `cli.py` helpers, `atomic.py`). The borrowed disciplines come from `superpowers:subagent-driven-development` (upstream `obra/superpowers` v6.0.3), consulted 2026-06-26 as design provenance, not a code dependency the implementation calls.

## Test Matrix

| Test | SPEC | Expectation |
|---|---|---|
| EXECUTING happy path | SPEC-CLI-001 | writes `logs/task-N-brief.md`, success payload carries work_id/task_id/brief_path (inside the standard `status`/`message` envelope under `R2P_JSON`), exit 0 |
| status not EXECUTING (e.g. closed_at_plan_checkpoint) | SPEC-CLI-001 | exit 6 (EXIT_CONFLICT), no file written |
| symlinked logs directory or target brief path | SPEC-CLI-001 | exit 6, no write through the link |
| `--task` out of range | SPEC-CLI-001 | exit 7 (EXIT_NOT_FOUND) |
| `--task` non-positive / non-integer | SPEC-CLI-001 | exit 2 (EXIT_CLI_ERR) |
| extracted body equals the gate's task body | SPEC-CLI-001 | brief file == `heading_bounded_bodies` slice, byte-identical |
| zero-padded anchor resolved by integer `--task` | SPEC-CLI-001 | PLAN authored `### PLAN-TASK-002`; `--task 2` writes `task-2-brief.md` and reports `task_id` = `PLAN-TASK-002` (integer match, not string equality) |
| shortcut `task-brief` end-to-end | SPEC-SURFACE-001 | identical JSON, file, and exit code as the CLI |
| wrapper `r2p-task-brief` end-to-end | SPEC-SURFACE-001 | identical JSON, file, and exit code as the CLI |
| FR-CM token presence on both surfaces | SPEC-GUARD-001 | passes; deleting any required token from either surface fails the test |
| no gap-open mention on either surface | SPEC-GUARD-001 | assertion holds |
| FR-CM1–CM4 prose present | SPEC-PROSE-001..004 | enforced via the SPEC-GUARD-001 token coverage |

## Non-goals

- SCOPE-OUT-001: no change to any gate, state transition, artifact schema, or existing command output contract.
- SCOPE-OUT-002: no machine assertion that a marker is true; the warning / Resolved / Gap / Unresolved markers stay in the agent-judgment layer.
- SCOPE-OUT-003: no separately authored gemini surface; opencode derives from the claude command.
- SCOPE-OUT-004: no change to the in-place single-branch execution model and no gap-route opening inside an executing run.

## PLAN Handoff

Four PLAN tasks, numbered contiguously, consuming every SPEC ID above. The `tools/r2p-task-brief` wrapper is a new file, so it is its own `create` task: the PLAN gate's Change Type / Files homogeneity rule (R16/R19) forbids a single task from mixing a new file (create) with edits to existing files (modify).
- PLAN-TASK-1 (Phase 1, independently shippable) — implement the `plan-task-brief` CLI command and its `tests/test_cli.py` cases. Spec References: SPEC-CLI-001. Carries SCOPE-IN-001.
- PLAN-TASK-2 (Phase 1) — create the `tools/r2p-task-brief` wrapper (Change Type: create). Spec References: SPEC-SURFACE-001. Carries SCOPE-IN-001.
- PLAN-TASK-3 (Phase 1) — implement the `task-brief` shortcut and the shortcut/wrapper equivalence tests (structural delegation plus a robust end-to-end run). Spec References: SPEC-SURFACE-001. Carries SCOPE-IN-001.
- PLAN-TASK-4 (Phase 2) — add the FR-CM1 through FR-CM4 prose to both r2p-execute surfaces and extend `tests/test_docs_consistency.py` token coverage. Spec References: SPEC-PROSE-001, SPEC-PROSE-002, SPEC-PROSE-003, SPEC-PROSE-004, SPEC-GUARD-001. Carries SCOPE-IN-002, SCOPE-IN-003, SCOPE-IN-004, SCOPE-IN-005, SCOPE-IN-006.

## Trace

| This ID | Upstream | Status |
|---|---|---|
| SPEC-CLI-001 | DES-CLI-001, SCOPE-IN-001 | open — consumed by PLAN-TASK-1 |
| SPEC-SURFACE-001 | DES-CLI-001, SCOPE-IN-001 | open — consumed by PLAN-TASK-2 and PLAN-TASK-3 |
| SPEC-PROSE-001 | DES-PROSE-001, SCOPE-IN-002 | open — consumed by PLAN-TASK-4 |
| SPEC-PROSE-002 | DES-PROSE-001, SCOPE-IN-003 | open — consumed by PLAN-TASK-4 |
| SPEC-PROSE-003 | DES-PROSE-001, SCOPE-IN-004 | open — consumed by PLAN-TASK-4 |
| SPEC-PROSE-004 | DES-PROSE-001, SCOPE-IN-005 | open — consumed by PLAN-TASK-4 |
| SPEC-GUARD-001 | DES-GUARD-001, SCOPE-IN-006 | open — consumed by PLAN-TASK-4 |
<!-- /r2p-read-only -->

## Project Context (read-only)
# Project Context Pack

- repo_root: `/Users/xubo/x-skills/req-to-plan`
- languages: {'Python': 21274, 'JavaScript': 31}
- package_managers: npm, pip
- test_commands: ['npm test']
- entrypoints: ['tools/workflow_cli/__main__.py']
- config_files: ['requirements.txt']
- dependencies (1):
  - pyyaml>=6.0 (pip)
- source_dirs: ['bin', 'docs', 'tests', 'tools']
<!-- /r2p-read-only -->

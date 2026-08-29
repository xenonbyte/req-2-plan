---
r2p_stage: plan
r2p_version: 4
r2p_status: approved
r2p_created_at: 2026-08-29T15:05:34.428051+00:00
r2p_updated_at: 2026-08-29T16:40:16.786049+00:00
---

# Plan

## Execution Readiness

- Requirement brief v1、risk discovery v3、DESIGN v8 和 SPEC v7 已批准；强制独立评审确认无 unresolved ambiguity / undecided point。
- 四个 phase-level cohesive slices 按现有 R19 gate 精确展开为 `2 / 4 / 1 / 2` 个 operation-homogeneous tasks。Declared dependency 只存在于组内：001→002、003→004→005→006、008→009；跨 Phase 顺序由编号、最低 actionable task 与上一 Phase acceptance 控制。
- Task 001/002 使用 SPEC-GRANULARITY-004 的 legacy strict bootstrap preflight。Task 002 reviewed complete 后、Task 003 dispatch 前，controller 必须运行：

```bash
/opt/homebrew/opt/python@3.14/bin/python3.14 -E /Users/xubo/x-skills/req-to-plan/tools/workflow_cli/__main__.py tools.workflow_cli --base-path /Users/xubo/x-skills/req-to-plan execution-metrics-bootstrap --work-id WF-20260829-r2p-execute-token-phase-r2p --profile strict --self-hosted-gap-through-task 002
```

- Task 003–007 与 Task 009 每次 dispatch 前先运行其 `Verification` 第一条 `execution-prerequisite-check ... --require-version 1`。Task 008 是唯一顺序例外：先完成 machine validator 与下述人工证据 checkpoint，再运行 prerequisite-check v1，最后才可 dispatch。Task 009 完成后，新生成 PLAN 才静态要求 semantics v2；当前 PLAN 始终使用 v1。
- Task 008 的 controller-owned source gate 发生在 role dispatch 和任何 Phase 3 source mutation 前。Controller 必须先从用户取得三个不同的 absolute archived-run paths，并绑定 `R2P_SAMPLE_DIR_1`、`R2P_SAMPLE_DIR_2`、`R2P_SAMPLE_DIR_3`；任一未绑定或非绝对路径时直接返回 `BLOCKED: representative_metrics_missing`。绑定后唯一命令为：

```bash
R2P_JSON=1 /opt/homebrew/opt/python@3.14/bin/python3.14 -E /Users/xubo/x-skills/req-to-plan/tools/workflow_cli/__main__.py tools.workflow_cli --base-path /Users/xubo/x-skills/req-to-plan execution-samples-validate --sample-dir "$R2P_SAMPLE_DIR_1" --sample-dir "$R2P_SAMPLE_DIR_2" --sample-dir "$R2P_SAMPLE_DIR_3" > /Users/xubo/x-skills/req-to-plan/.req-to-plan/WF-20260829-r2p-execute-token-phase-r2p/execution/phase-3-sample-evidence.json
```

- Validator 非 success 时，Task 008/009 保持 `[ ]`，Phase 3 source worktree/HEAD 必须等于 Phase 3 BASE；不得派发 implementer。Validator success 后，controller 只从 evidence JSON 展示三份样本各自的 `path`、`work_id`、`r2p_version`、`instrumentation_schema`、`task_count`、`change_shape`、`role_counts`、`final_verdict`、`metrics_finalized` 与 aggregate 的 `work_ids`、`task_counts`、`change_shapes`、两个 diversity flags；然后停止并取得用户对“三份路径就是预期代表样本”的显式确认。未确认或拒绝与 validator failure 相同：返回 `BLOCKED: representative_metrics_missing`、Task 008/009 保持 `[ ]`、source worktree/HEAD 等于 Phase 3 BASE，且不 dispatch。只有显式确认后，Task 008 才只消费 evidence JSON，不二次读取样本目录。
- 所有 source edits 在当前分支串行执行。每个 task 边界记录 full BASE、要求 clean tree、做 task-scoped commit并审查 exact BASE→HEAD diff；不得用 `HEAD~1` 重建 BASE。
- 无 push、PR、远程 mutation、shared implementer、parallel current-branch writes、batch reviewer、balanced profile、持久化 context bundle、第三方依赖或 PLAN/gate/checkbox schema 修改授权。
- Task-level verification 遵循 SPEC-VERIFY-001；final reviewer 与 final re-reviewer必须运行 fresh `.venv/bin/python -m pytest tests/ -q`。

## Tasks

### PLAN-TASK-001 — Phase 0 core: metrics, transaction, prerequisite v1, and sample validator
Spec References: SPEC-METRICS-009, SPEC-SAMPLE-003, SPEC-GRANULARITY-004
Change Type: create
TDD Applicable: yes
Files:
- `tools/workflow_cli/execution_metrics.py`
- `tests/test_execution_metrics.py`
Skeleton:
```python
INSTRUMENTATION_SCHEMA = 1
PREREQUISITE_IMPLEMENTATION_VERSION = 1

def start_execution_transaction(base_path: Path, work_id: WorkId, profile: str) -> RunRecord:
    """Own record/PLAN loading, pinned run fd, marker, ledgers, state save, and recovery."""

def check_prerequisite_v1(base_path: Path, work_id: WorkId, task: int): ...
def bootstrap_self_hosted_metrics(base_path: Path, work_id: WorkId, through_task: int): ...
def validate_representative_samples(sample_dirs: tuple[Path, Path, Path]): ...
def parse_metrics(text: str): ...
def classify_change_shape(name_status_z: bytes) -> str: ...
```
Steps:
Prerequisite: none
- [ ] [ADDRESSED] Carry SCOPE-IN-003 and the Phase 3 evidence portion of SCOPE-IN-007 into one non-authoritative stdlib core; do not change progress/gate authority.
- [ ] Before dispatch, apply the exact Task 001 legacy preflight: current run is `EXECUTING`; full Execution BASE equals HEAD; PLAN has exactly nine contiguous anchors and `execution/progress.md` has the corresponding nine `[ ]` rows; no profile/escalation/task marker exists; Task 001 is the lowest unchecked task.
- [ ] Write failing tests first for the unique `start_execution_transaction(base_path, work_id, profile)` ownership boundary, lock/marker/no-clobber start matrix, crash recovery, foreign residue, and zero overwrite.
- [ ] Add failing tests for quantized monotonic timing, canonical metrics/header/invocation grammar, closed header combinations, role/status/wave/context/Token matrices, exact Git classifier, and non-gating finalization.
- [ ] Add failing self-bootstrap tests for `metrics-bootstrap.lock`, open unique temp fd, file/dir fsync, hard-link no-replace, post-link open-fd/temp/final inode identity, EEXIST, source/final replacement races, abandoned temp, exact-header retry, Task 003+ block resume, and every crash point.
- [ ] Add failing prerequisite v1 tests and exact sample-validator golden/error tests: three absolute pinned directories, no discovery/write, argument-count/duplicate ordering, all sample/aggregate fields, seven role counts, duration/report/full-suite/context/Token totals, and no sample body leakage.
- [ ] Implement only the core APIs and direct tests. No CLI command, execute surface, wrapper, or docs change belongs to this task.
Verification:
1. Reconfirm the Task 001 legacy preflight and clean BASE before any source edit.
2. Run `.venv/bin/python -m pytest tests/test_execution_metrics.py -q`; require exit 0 and record command/scope/reason/duration.
3. Keep verification targeted unless this create-only diff escapes the two listed paths or targeted tests fail; final review retains the mandatory full suite.

### PLAN-TASK-002 — Phase 0 integration: start/metrics CLI, checker v1, and zero-history role protocol
Spec References: SPEC-VERIFY-001, SPEC-ROLE-002, SPEC-METRICS-009, SPEC-SAMPLE-003, SPEC-GRANULARITY-004, SPEC-PARITY-008
Change Type: modify
TDD Applicable: yes
Files:
- `tools/workflow_cli/agent_shortcuts.py`
- `tools/workflow_cli/cli.py`
- `tools/workflow_cli/agent_templates/claude/commands/r2p-execute.md`
- `tools/workflow_cli/agent_templates/codex/skills/r2p-execute/SKILL.md`
- `tools/workflow_cli/agent_templates/gemini/commands/r2p-execute.toml`
- `tests/test_agent_shortcuts.py`
- `tests/test_cli.py`
- `tests/test_docs_consistency.py`
- `tests/test_install.py`
- `README.md`
Skeleton:
```python
def _cmd_run_execute_start(args):
    record = start_execution_transaction(args.base_path, _validate_work_id(args.work_id), args.profile or "strict")
    emit_start_result(record)

def _cmd_execution_prerequisite_check(args): ...
def _cmd_execution_metrics_bootstrap(args): ...
def _cmd_execution_samples_validate(args): ...
```
Steps:
Prerequisite: PLAN-TASK-001
- [ ] [ADDRESSED] Carry SCOPE-IN-001, SCOPE-IN-002, SCOPE-IN-003, SCOPE-IN-007, and SCOPE-IN-010 into Phase 0 CLI/surface behavior.
- [ ] Before dispatch, apply the exact Task 002 legacy preflight in `execution/progress.md`: Task 001 has one `[x]` row and one `review clean` complete marker; Task 002 is lowest unchecked; HEAD equals Task 001 marker head; work ID/BASE/task count remain exact.
- [ ] Write failing CLI tests first for strict-default start, unique core signature, human/JSON/exit behavior, crash recovery, self-bootstrap first-create/retry, validator output, and prerequisite `implementation_version=1` / `semantics_version=1`; requested v2 exits 6.
- [ ] Add shortcut regression tests before CLI integration so the existing closed strict `_cmd_execute` → internal `run-execute-start` call fails until the new transaction is wired, then proves strict-default start, human/JSON/exit propagation, active-pointer update, and executing resume. Keep the existing shortcut call shape unchanged if those tests prove transitive integration; do not add a second transaction owner.
- [ ] Register `execution-prerequisite-check` v1, `execution-metrics-bootstrap`, and `execution-samples-validate`; preserve Task 001 no-follow/no-clobber/no-partial contracts.
- [ ] Update Claude/Codex execute surfaces in lockstep: every role is a brand-new zero-history invocation; controller records every role block; verification defaults targeted/directly affected and escalates only for SPEC-VERIFY-001 triggers; every concern and `⚠️ DEFER` is preserved.
- [ ] Keep final reviewer/re-reviewer full suite mandatory, metrics non-authoritative, Gemini truthful/fail-closed, and test OpenCode/install-derived surfaces.
- [ ] Update README with metrics ownership, byte kinds, Token unavailable semantics, internal commands, and the self-host exception.
Verification:
1. Reconfirm the Task 002 legacy preflight before dispatch/source edit.
2. Run `.venv/bin/python -m pytest tests/test_cli.py tests/test_agent_shortcuts.py tests/test_docs_consistency.py tests/test_install.py -q`; require exit 0 and record duration.
3. Run `.venv/bin/python -m pytest tests/ -q` with reason `shared/core execution-start and controller protocol`.
4. After clean task review records Task 002 complete, run the exact self-host bootstrap command from Execution Readiness before Task 003 dispatch.

### PLAN-TASK-003 — Phase 1 core: pinned deterministic semantic context view
Spec References: SPEC-CONTEXT-010, SPEC-CONTEXT-011
Change Type: create
TDD Applicable: yes
Files:
- `tools/workflow_cli/execution_context.py`
- `tests/test_execution_context.py`
Skeleton:
```python
@dataclass(frozen=True)
class ContextSource:
    path: str
    raw_bytes: int
    semantic_bytes: int

@dataclass(frozen=True)
class ContextView:
    work_id: str
    sources: tuple[ContextSource, ...]
    raw_bytes: int
    semantic_bytes: int
    content: str

def build_context_view(base_path: Path, work_id: WorkId) -> ContextView: ...
```
Steps:
Prerequisite: none
- [ ] [ADDRESSED] Carry SCOPE-IN-004 into `execution_context.py`; its private pinned-tree helpers own this six-source traversal and must not alter `atomic.py`'s public single-file API.
- [ ] Confirm Task 002 is reviewed complete, run the self-host bootstrap command, then run prerequisite-check v1 for Task 003 before dispatch.
- [ ] Write failing security tests first for component directory-fd pinning, `O_DIRECTORY|O_NOFOLLOW|O_NONBLOCK`, per-file pre-stat/open/fstat, FIFO/device/directory/symlink/race rejection, capability failure, fd cleanup, and parent replacement semantics.
- [ ] Add golden direct-API tests for fixed source order, fence-aware nonsemantic stripping, Unicode bytes, whitespace-only content, separators, one trailing newline, exact aggregates, same-handle run validation, and no partial output.
- [ ] Implement only direct context construction/private read helpers and tests; do not create the internal CLI, wrapper, agent surface, or docs here.
Verification:
1. Run `/opt/homebrew/opt/python@3.14/bin/python3.14 -E /Users/xubo/x-skills/req-to-plan/tools/workflow_cli/__main__.py tools.workflow_cli --base-path /Users/xubo/x-skills/req-to-plan execution-prerequisite-check --work-id WF-20260829-r2p-execute-token-phase-r2p --task 3 --require-version 1`; require `satisfied=true`.
2. Run `.venv/bin/python -m pytest tests/test_execution_context.py -q`; require exit 0 and record duration.
3. Keep verification targeted unless listed paths are exceeded or tests fail.

### PLAN-TASK-004 — Phase 1 internal CLI: expose context-view after the core exists
Spec References: SPEC-CONTEXT-010, SPEC-CONTEXT-011
Change Type: modify
TDD Applicable: yes
Files:
- `tools/workflow_cli/cli.py`
- `tests/test_cli.py`
Skeleton:
```python
def _cmd_context_view(args):
    view = build_context_view(args.base_path, _validate_work_id(args.work_id))
    emit_context_view(view, json_mode=is_json_mode())
```
Steps:
Prerequisite: PLAN-TASK-003
- [ ] [ADDRESSED] Carry SCOPE-IN-004 into the existing internal CLI without creating a public wrapper prematurely.
- [ ] Run prerequisite-check v1 for Task 004 before dispatch.
- [ ] Write failing tests first for `context-view --work-id`, exact human stdout/JSON, invalid args exit 2, missing exit 7, unsafe/wrong-status exit 6, and zero partial content.
- [ ] Register the handler through the existing `tools.workflow_cli` target so bootstrap isolation remains unchanged.
- [ ] Keep this task limited to CLI integration and directly affected existing tests; role surfaces still use direct ACS until Task 006.
Verification:
1. Run `/opt/homebrew/opt/python@3.14/bin/python3.14 -E /Users/xubo/x-skills/req-to-plan/tools/workflow_cli/__main__.py tools.workflow_cli --base-path /Users/xubo/x-skills/req-to-plan execution-prerequisite-check --work-id WF-20260829-r2p-execute-token-phase-r2p --task 4 --require-version 1`; require `satisfied=true`.
2. Run `.venv/bin/python -m pytest tests/test_cli.py -q`; require exit 0 and record duration.
3. Run `.venv/bin/python -m pytest tests/ -q` with reason `shared/core trusted-input CLI path`.

### PLAN-TASK-005 — Phase 1 wrapper: create r2p-context-view after the CLI target exists
Spec References: SPEC-CONTEXT-011
Change Type: create
TDD Applicable: yes
Files:
- `tools/r2p-context-view`
- `tests/test_context_view_wrapper.py`
Skeleton:
```bash
#!/usr/bin/env bash
set -euo pipefail
# Resolve REPO_ROOT, then exec python -E .../__main__.py tools.workflow_cli context-view "$@".
```
Steps:
Prerequisite: PLAN-TASK-004
- [ ] [ADDRESSED] Carry the public-command portion of SCOPE-IN-004 into a thin wrapper whose internal target was completed in Task 004.
- [ ] Run prerequisite-check v1 for Task 005 before dispatch.
- [ ] Write failing wrapper tests first for argument forwarding, `python3`/`python`, `-E`, target path, human/JSON behavior, exit propagation, spaces in repo paths, and installed-script rendering.
- [ ] Create the executable wrapper only after the handler exists; do not change templates/docs in this create task.
- [ ] Keep the wrapper thin: no artifact prose, semantic filtering, state writes, path discovery, or fallback behavior.
Verification:
1. Run `/opt/homebrew/opt/python@3.14/bin/python3.14 -E /Users/xubo/x-skills/req-to-plan/tools/workflow_cli/__main__.py tools.workflow_cli --base-path /Users/xubo/x-skills/req-to-plan execution-prerequisite-check --work-id WF-20260829-r2p-execute-token-phase-r2p --task 5 --require-version 1`; require `satisfied=true`.
2. Run `.venv/bin/python -m pytest tests/test_context_view_wrapper.py -q`; require exit 0 and record duration.
3. Keep verification targeted unless listed paths are exceeded or tests fail.

### PLAN-TASK-006 — Phase 1 adoption: semantic-view roles and compact audit surfaces
Spec References: SPEC-CONTEXT-011, SPEC-REPORT-012, SPEC-PARITY-008
Change Type: modify
TDD Applicable: yes
Files:
- `tools/workflow_cli/agent_templates/claude/commands/r2p-execute.md`
- `tools/workflow_cli/agent_templates/codex/skills/r2p-execute/SKILL.md`
- `tools/workflow_cli/agent_templates/gemini/commands/r2p-execute.toml`
- `tests/test_docs_consistency.py`
- `tests/test_install.py`
- `README.md`
Skeleton:
```markdown
Context command: r2p-context-view --work-id <id>
Required sections: Status; Commit Range; Changed Files; Verification Records; Concerns; ⚠️ DEFER
```
Steps:
Prerequisite: PLAN-TASK-005
- [ ] [ADDRESSED] Carry SCOPE-IN-004, SCOPE-IN-005, and SCOPE-IN-010 into installed execution protocols after core, CLI, and wrapper are executable.
- [ ] Run prerequisite-check v1 for Task 006 before dispatch.
- [ ] Write failing lockstep tests first for role-side context invocation, `semantic_view/semantic_payload_bytes`, compact persistent/inline fields, strict/fast final inputs, every concern/`⚠️ DEFER`, wrapper install/uninstall, OpenCode derivation, and truthful Gemini wording.
- [ ] Replace direct ACS ingestion with role-side context view; controller must not ingest/forward content and no persistent context artifact may be created.
- [ ] Adopt compact reports/reviews without dropping commit range, files, verification records, status, concern, or defer evidence; update README.
Verification:
1. Run `/opt/homebrew/opt/python@3.14/bin/python3.14 -E /Users/xubo/x-skills/req-to-plan/tools/workflow_cli/__main__.py tools.workflow_cli --base-path /Users/xubo/x-skills/req-to-plan execution-prerequisite-check --work-id WF-20260829-r2p-execute-token-phase-r2p --task 6 --require-version 1`; require `satisfied=true`.
2. Run `.venv/bin/python -m pytest tests/test_docs_consistency.py tests/test_install.py -q`; require exit 0 and record duration.
3. Run `.venv/bin/python -m pytest tests/ -q` with reason `high-risk execution protocol and installed-surface adoption`.

### PLAN-TASK-007 — Phase 2: cohesive slice and checker-v1 PLAN formation rules
Spec References: SPEC-GRANULARITY-004, SPEC-PARITY-008
Change Type: modify
TDD Applicable: yes
Files:
- `tools/workflow_cli/stage_templates.py`
- `tools/workflow_cli/agent_templates/claude/SKILL.md`
- `tools/workflow_cli/agent_templates/claude/commands/r2p-continue.md`
- `tools/workflow_cli/agent_templates/codex/skills/r2p-continue/SKILL.md`
- `tools/workflow_cli/agent_templates/gemini/commands/r2p-continue.toml`
- `tests/test_stage_templates.py`
- `tests/test_docs_consistency.py`
- `tests/test_install.py`
Skeleton:
```python
_PLAN_GRANULARITY_NOTE = (
    "Form a phase-level cohesive slice; when R19 requires a task group, "
    "give every operation-homogeneous task an executable intermediate contract."
)
```
Steps:
Prerequisite: none
- [ ] [ADDRESSED] Carry SCOPE-IN-006 and SCOPE-IN-010 into all five PLAN-author surfaces without changing `PLAN_TASK_FIELDS`, trace, gates, checkbox, BASE, or commit/diff contracts.
- [ ] Run prerequisite-check v1 for Task 007 before dispatch; require Task 007 as lowest unchecked.
- [ ] Write failing tests first for phase-level slice, R19 task-group examples, operation-homogeneous Files, intermediate contracts, group-only dependency/rollback, and exact `Steps` prerequisite grammar.
- [ ] Make every generated v1 PLAN use `execution-prerequisite-check ... --require-version 1`; keep generation strict-compatible and fail closed on fast-only state.
- [ ] Update Claude generic/continue, Codex continue, Gemini, stage seed, docs-consistency anchors, and OpenCode-derived install test in lockstep.
- [ ] Reject task-per-file/class splitting, broken future-target wrappers, unrelated mega-tasks, new `Dependencies:` field, and unanchored deferral.
Verification:
1. Run `/opt/homebrew/opt/python@3.14/bin/python3.14 -E /Users/xubo/x-skills/req-to-plan/tools/workflow_cli/__main__.py tools.workflow_cli --base-path /Users/xubo/x-skills/req-to-plan execution-prerequisite-check --work-id WF-20260829-r2p-execute-token-phase-r2p --task 7 --require-version 1`; require `satisfied=true`.
2. Run `.venv/bin/python -m pytest tests/test_stage_templates.py tests/test_docs_consistency.py tests/test_install.py -q`; require exit 0 and record duration.
3. Run a fresh `.venv/bin/python -m pytest tests/ -q`; require exit 0 and record `scope=full_suite`, reason=`shared/core PLAN generation and cross-platform author surfaces`, and duration. This is both the SPEC-VERIFY-001 shared/core escalation and the complete Phase 2 acceptance.

### PLAN-TASK-008 — Phase 3 core: consume accepted evidence and create profile/ledger semantics
Spec References: SPEC-SAMPLE-003, SPEC-RESUME-006, SPEC-PROFILE-013, SPEC-LEDGER-014
Change Type: create
TDD Applicable: yes
Files:
- `tools/workflow_cli/execution_profile.py`
- `tests/test_execution_profile.py`
Skeleton:
```python
class ExecutionProfile(Enum):
    STRICT = "strict"
    FAST = "fast"

def parse_execution_ledger(text: str, plan_task_ids: tuple[str, ...]): ...
def check_prerequisite_v2(progress: str, plan: str, task: int): ...
def fast_structure_eligible(tier: TierEstimate) -> bool: ...
```
Steps:
Prerequisite: none
- [ ] [ADDRESSED] Carry SCOPE-IN-007, SCOPE-IN-008, and SCOPE-IN-009 into a pure profile/ledger core only after the Phase 3 evidence source gate succeeds.
- [ ] Before dispatch or source mutation, execute the sample-validator procedure in Execution Readiness. On missing input/non-success, return `BLOCKED: representative_metrics_missing`, leave Task 008/009 unchecked, and preserve Phase 3 BASE/HEAD/source.
- [ ] After validator success, save its stdout as the evidence JSON, display only the listed sample identity/header/verdict/coverage fields and aggregate diversity fields, then stop for the user's explicit confirmation that the three paths are the intended representative samples. Pending/rejected confirmation takes the same zero-mutation `BLOCKED` path; approval is recorded in the Task 008 report.
- [ ] Only after that explicit confirmation, run prerequisite-check v1 for Task 008; require Task 008 as lowest unchecked, then dispatch the implementer with the evidence JSON as its only sample input.
- [ ] Write failing tests first for profile/event/marker grammar, comment/fence masking, state segments, BASE/SHA ancestry, first actionable task, one-way escalation, and atomic final ledger migration.
- [ ] Add failing tests for v2 prerequisite semantics, LIGHT/no-modifier eligibility, and accepted evidence JSON consumption without reopening sample directories.
- [ ] Implement only pure profile/ledger/eligibility/evidence-consumption helpers; no shortcut, CLI, surface, docs, or v2 adoption belongs here.
Verification:
1. Confirm evidence JSON is validator success and source/HEAD still equal Phase 3 BASE; display its specified identity/aggregate fields and record the user's explicit accept decision without rereading sample directories.
2. If the checkpoint is accepted, run `/opt/homebrew/opt/python@3.14/bin/python3.14 -E /Users/xubo/x-skills/req-to-plan/tools/workflow_cli/__main__.py tools.workflow_cli --base-path /Users/xubo/x-skills/req-to-plan execution-prerequisite-check --work-id WF-20260829-r2p-execute-token-phase-r2p --task 8 --require-version 1`; require `satisfied=true` before dispatch. If pending/rejected, take the zero-mutation `BLOCKED` path instead.
3. Run `.venv/bin/python -m pytest tests/test_execution_profile.py -q`; require exit 0, reference accepted evidence JSON plus the checkpoint decision, and record duration.
4. Keep verification targeted unless listed paths are exceeded or tests fail.

### PLAN-TASK-009 — Phase 3 integration: profile handshake, recovery, final review, and checker-v2 adoption
Spec References: SPEC-GRANULARITY-004, SPEC-FAST-005, SPEC-RESUME-006, SPEC-FINAL-007, SPEC-PROFILE-013, SPEC-LEDGER-014, SPEC-PARITY-008
Change Type: modify
TDD Applicable: yes
Files:
- `tools/workflow_cli/agent_shortcuts.py`
- `tools/workflow_cli/cli.py`
- `tools/workflow_cli/stage_templates.py`
- `tools/workflow_cli/agent_templates/claude/SKILL.md`
- `tools/workflow_cli/agent_templates/claude/commands/r2p-continue.md`
- `tools/workflow_cli/agent_templates/claude/commands/r2p-execute.md`
- `tools/workflow_cli/agent_templates/codex/skills/r2p-continue/SKILL.md`
- `tools/workflow_cli/agent_templates/codex/skills/r2p-execute/SKILL.md`
- `tools/workflow_cli/agent_templates/gemini/commands/r2p-continue.toml`
- `tools/workflow_cli/agent_templates/gemini/commands/r2p-execute.toml`
- `tests/test_agent_shortcuts.py`
- `tests/test_cli.py`
- `tests/test_gates.py`
- `tests/test_stage_templates.py`
- `tests/test_docs_consistency.py`
- `tests/test_install.py`
- `README.md`
Skeleton:
```python
def _cmd_execute(ns, base_path):
    decision = evaluate_profile_invocation(ns, base_path)
    return dispatch_or_stop(decision)

def _cmd_execution_prerequisite_check(args):
    return check_prerequisite(args, require_version=args.require_version)
```
Steps:
Prerequisite: PLAN-TASK-008
- [ ] [ADDRESSED] Carry SCOPE-IN-007, SCOPE-IN-008, SCOPE-IN-009, and SCOPE-IN-010 into shortcut/CLI/protocol adoption while preserving strict default.
- [ ] Run prerequisite-check v1 for Task 009 before dispatch and require Task 008 reviewed complete; retain evidence JSON as the only sample input.
- [ ] Write failing integration tests first for fast preflight/confirm/reject zero mutation, direct-confirm boundary, executing matrix, legacy strict, marker recovery, BASE chain, and first actionable task.
- [ ] Upgrade prerequisite implementation to v2 and test `1/1` success, `1/2` exit 6, `2/1` strict semantics 1, and `2/2` profile-aware semantics 2.
- [ ] In this same task, upgrade all five continue/PLAN-author surfaces and OpenCode-derived checks from static version 1 to version 2; no runtime detection or LLM choice.
- [ ] Update Claude/Codex execute protocols in lockstep for fast handshake, N+1 minimum, escalation, profile-specific final inputs, all-role metrics, full suite, one-write completion migration, final verdict, and unchanged archive gates.
- [ ] Preserve Gemini truthfulness, dirty-tree/BASE discipline, no third profile, no batch/shared implementer, no remote mutation, and update README/tests.
Verification:
1. Run `/opt/homebrew/opt/python@3.14/bin/python3.14 -E /Users/xubo/x-skills/req-to-plan/tools/workflow_cli/__main__.py tools.workflow_cli --base-path /Users/xubo/x-skills/req-to-plan execution-prerequisite-check --work-id WF-20260829-r2p-execute-token-phase-r2p --task 9 --require-version 1`; require `satisfied=true` before dispatch.
2. Run `.venv/bin/python -m pytest tests/test_agent_shortcuts.py tests/test_cli.py tests/test_gates.py tests/test_stage_templates.py tests/test_docs_consistency.py tests/test_install.py -q`; require exit 0 and record duration.
3. With a temporary strict fixture, invoke upgraded checker using required versions 1 and 2; require implementation version 2 with semantics versions 1 and 2.
4. Run `.venv/bin/python -m pytest tests/ -q` with reason `shared/core profile, recovery, and generated PLAN protocol`.

## Risk Handling

| Risk | Handling Task | Closure |
|---|---|---|
| RISK-PERF-001 | PLAN-TASK-002 | [ADDRESSED] targeted-first task roles, exact escalation reasons, mandatory final suite |
| RISK-CTX-002 | PLAN-TASK-002, PLAN-TASK-006 | [ADDRESSED] zero-history self-contained dispatch and role-owned semantic view |
| RISK-METRIC-003 | PLAN-TASK-001, PLAN-TASK-002 | [ADDRESSED] closed measured schema, non-authoritative ledger, honest self-host gap |
| RISK-IO-004 | PLAN-TASK-001, PLAN-TASK-003, PLAN-TASK-004 | [ADDRESSED] no-replace transaction/bootstrap and pinned no-follow reads |
| RISK-CONTRACT-005 | PLAN-TASK-001, PLAN-TASK-003, PLAN-TASK-004 | [ADDRESSED] exact metrics/evidence/context grammars and byte formulas |
| RISK-AUDIT-006 | PLAN-TASK-002, PLAN-TASK-006 | [ADDRESSED] canonical role blocks and compact concern/defer-preserving artifacts |
| RISK-GRAN-007 | PLAN-TASK-001, PLAN-TASK-002, PLAN-TASK-007, PLAN-TASK-009 | [ADDRESSED] intermediate contracts, versioned checker, group-only rollback |
| RISK-PROFILE-008 | PLAN-TASK-008, PLAN-TASK-009 | [ADDRESSED] strict default plus structural/semantic fast gates |
| RISK-RESUME-009 | PLAN-TASK-008, PLAN-TASK-009 | [ADDRESSED] state segments, BASE chain, atomic completion, strict recovery |
| RISK-FINAL-010 | PLAN-TASK-009 | [ADDRESSED] profile-specific final review, full suite, unchanged archive gate |
| RISK-PARITY-011 | PLAN-TASK-002, PLAN-TASK-006, PLAN-TASK-007, PLAN-TASK-009 | [ADDRESSED] Claude/Codex lockstep, OpenCode derivation, Gemini truthfulness |
| RISK-SEQUENCE-012 | PLAN-TASK-001, PLAN-TASK-002, PLAN-TASK-008, PLAN-TASK-009 | [ADDRESSED] Phase 0 validator plus pre-dispatch three-sample hard gate |

## Trace

| This ID | Upstream | Status |
|---|---|---|
| PLAN-TASK-001 | SPEC-METRICS-009, SPEC-SAMPLE-003, SPEC-GRANULARITY-004; SCOPE-IN-003, SCOPE-IN-007 | [ADDRESSED] Phase 0 create-only core and validators |
| PLAN-TASK-002 | SPEC-VERIFY-001, SPEC-ROLE-002, SPEC-METRICS-009, SPEC-SAMPLE-003, SPEC-GRANULARITY-004, SPEC-PARITY-008; SCOPE-IN-001, SCOPE-IN-002, SCOPE-IN-003, SCOPE-IN-007, SCOPE-IN-010 | [ADDRESSED] Phase 0 integration and self-host transition |
| PLAN-TASK-003 | SPEC-CONTEXT-010, SPEC-CONTEXT-011; SCOPE-IN-004 | [ADDRESSED] Phase 1 pinned context core |
| PLAN-TASK-004 | SPEC-CONTEXT-010, SPEC-CONTEXT-011; SCOPE-IN-004 | [ADDRESSED] Phase 1 internal CLI |
| PLAN-TASK-005 | SPEC-CONTEXT-011; SCOPE-IN-004 | [ADDRESSED] Phase 1 public wrapper |
| PLAN-TASK-006 | SPEC-CONTEXT-011, SPEC-REPORT-012, SPEC-PARITY-008; SCOPE-IN-004, SCOPE-IN-005, SCOPE-IN-010 | [ADDRESSED] Phase 1 adoption |
| PLAN-TASK-007 | SPEC-GRANULARITY-004, SPEC-PARITY-008; SCOPE-IN-006, SCOPE-IN-010 | [ADDRESSED] Phase 2 v1 generation |
| PLAN-TASK-008 | SPEC-SAMPLE-003, SPEC-RESUME-006, SPEC-PROFILE-013, SPEC-LEDGER-014; SCOPE-IN-007, SCOPE-IN-008, SCOPE-IN-009 | [ADDRESSED] Phase 3 evidence-gated profile core |
| PLAN-TASK-009 | SPEC-GRANULARITY-004, SPEC-FAST-005, SPEC-RESUME-006, SPEC-FINAL-007, SPEC-PROFILE-013, SPEC-LEDGER-014, SPEC-PARITY-008; SCOPE-IN-006, SCOPE-IN-007, SCOPE-IN-008, SCOPE-IN-009, SCOPE-IN-010 | [ADDRESSED] Phase 3 checker-v2/profile integration |

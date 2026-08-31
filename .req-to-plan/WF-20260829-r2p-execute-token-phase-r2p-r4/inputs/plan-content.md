# Plan

## Execution Readiness

- This is a delta PLAN reopened from the original execution after its Task 9 exposed a PLAN file-authority defect. The source tree outside `.req-to-plan/` must remain identical to source snapshot `ac3233cd9782c96a665e0f56e43fc17c5d82187f`, which contains the reviewed original Task 1–8 implementation; scoped workflow commits may advance HEAD and do not authorize replay or no-op source commits.
- The remaining gap is cohesive: fast-profile execution cannot truthfully record `N` implementers followed by the primary final reviewer because metrics append/finalize still enforce the strict per-task-reviewer sequence. The repair therefore modifies the original Task 9 integration surfaces together with `execution_metrics.py` and its direct tests.
- All listed paths already exist, so this is one operation-homogeneous `modify` task. No create/delete/rename operation is authorized.
- Strict remains the default and its role grammar must remain accepted unchanged. Fast must record only roles actually dispatched; it must not fabricate task-reviewer invocations.
- Before task dispatch or any source mutation, the controller must complete the exact explicit-strict manual bootstrap: run status is `EXECUTING`; PLAN and progress each contain exactly one Task 001 and its row is `[ ]`; progress contains exactly one `Execution Profile: strict`, a full `Execution BASE`, and no escalation/implemented/complete marker; `git rev-parse HEAD` equals that Execution BASE; and `git diff --quiet ac3233cd9782c96a665e0f56e43fc17c5d82187f HEAD -- . ':(exclude).req-to-plan'` succeeds. It then runs this exact read-only sample gate, requires accepted current-run evidence, and reconfirms every bootstrap condition:

```bash
R2P_JSON=1 /opt/homebrew/opt/python@3.14/bin/python3.14 -E /Users/xubo/x-skills/req-to-plan/tools/workflow_cli/__main__.py tools.workflow_cli --base-path /Users/xubo/x-skills/req-to-plan execution-samples-validate --sample-dir /Users/xubo/Desktop/test-1/.req-to-plan/archive/WF-20260831-run-776c763d --sample-dir /Users/xubo/Desktop/test-2/.req-to-plan/archive/WF-20260831-run-e31ea18d --sample-dir /Users/xubo/Desktop/test-3/.req-to-plan/archive/WF-20260831-1-2 > /Users/xubo/x-skills/req-to-plan/.req-to-plan/WF-20260829-r2p-execute-token-phase-r2p-r4/execution/phase-3-sample-evidence.json
```

- No unresolved ambiguity or undecided point remains. No requirement is deferred. The current working tree outside `.req-to-plan/` must be clean before dispatch.

## Global Constraints

- Work on the current branch only. Use TDD, stage only files intentionally changed by this task, create a task-scoped commit, and preserve the exact BASE-to-HEAD range.
- Do not replay original Task 1–8, mutate the three archived sample directories, or use old execution reports as role inputs. Only the validator's no-follow read access to those exact paths is authorized; the source snapshot plus this run's dynamic Execution BASE and fresh deterministic tests are the operational baseline.
- Do not change PLAN schema, checkbox/archive authority, final-review marker semantics, dirty-tree protections, Git BASE discipline, or the CLI/agent prose boundary.
- Do not add dependencies, a third execution profile, shared/batch implementers, parallel current-branch writes, Token estimation, push, PR, or remote mutation.
- Keep Claude and Codex execute/continue surfaces in lockstep; OpenCode remains derived from Claude; Gemini wording remains truthful and fail-closed where it cannot provide a fresh zero-history subagent.
- Task-level verification includes the directly affected modules because this task modifies shared execution core. The final reviewer and every final re-reviewer run a fresh `.venv/bin/python -m pytest tests/ -q`.

## Tasks

### PLAN-TASK-001 — Reopened Phase 3 delta: profile-aware metrics and checker-v2 execution adoption
Spec References: SPEC-VERIFY-001, SPEC-ROLE-002, SPEC-SAMPLE-003, SPEC-METRICS-009, SPEC-CONTEXT-010, SPEC-CONTEXT-011, SPEC-REPORT-012, SPEC-GRANULARITY-004, SPEC-PARITY-008, SPEC-PROFILE-013, SPEC-LEDGER-014, SPEC-RESUME-006, SPEC-FAST-005, SPEC-FINAL-007
Change Type: modify
TDD Applicable: yes
Files:
- `tools/workflow_cli/execution_metrics.py`
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
- `tests/test_execution_metrics.py`
- `tests/test_agent_shortcuts.py`
- `tests/test_cli.py`
- `tests/test_gates.py`
- `tests/test_stage_templates.py`
- `tests/test_docs_consistency.py`
- `tests/test_install.py`
- `README.md`
Skeleton:
```python
def validate_role_sequence(invocations, *, profile: str, task_count: int):
    if profile == "strict":
        return validate_strict_role_sequence(invocations, task_count=task_count)
    return validate_fast_role_sequence(invocations, task_count=task_count)

def _cmd_execute(ns, base_path):
    decision = evaluate_profile_invocation(ns, base_path)
    return dispatch_or_stop(decision)

def _cmd_execution_prerequisite_check(args):
    return check_prerequisite(args, require_version=args.require_version)
```
Steps:
Prerequisite: none
- [ ] [ADDRESSED] Carry SCOPE-IN-001, SCOPE-IN-002, SCOPE-IN-003, SCOPE-IN-004, SCOPE-IN-005, SCOPE-IN-006, SCOPE-IN-007, SCOPE-IN-008, SCOPE-IN-009, and SCOPE-IN-010 through the reviewed current-HEAD baseline plus this remaining profile-aware metrics/integration delta; fresh targeted and full-suite verification re-establish end-to-end acceptance without replaying completed tasks.
- [ ] [ADDRESSED] Treat source snapshot `ac3233c` plus this run's recorded dynamic Execution BASE as the implementation boundary for the already reviewed original Task 1–8. Before source mutation, confirm only `.req-to-plan/` is dirty and this task is the sole reopened PLAN task; execute the exact explicit-strict manual bootstrap and sample gate from Execution Readiness, consume only this run's accepted evidence, and reconfirm all bootstrap predicates. Do not call prerequisite v1 and do not alter the ledger to manufacture eligibility.
- [ ] Write failing metrics tests first. Preserve the complete strict sequence grammar, while fast accepts exactly one implementer per PLAN task followed by the primary final reviewer; accepts only evidence-backed task/final fixer and re-reviewer waves; and rejects task reviewers in fast, missing/duplicate/out-of-order roles, invalid wave/status/task combinations, and any continuation after a blocked role.
- [ ] Make metrics append and finalize select the role-sequence grammar from the authoritative metrics/profile ledger. Keep strict behavior and canonical serialization unchanged. Fast records every actual role but never synthesizes a task-reviewer block; finalization still requires profile-appropriate sequence completeness, all PLAN checkboxes complete, a fresh full-suite final verification record, and the last final verdict `Approved`.
- [ ] Write failing integration tests for fast preflight/confirm/reject zero mutation, direct-confirm boundary, executing reuse/conflict matrix, legacy strict, marker recovery, BASE chain, first actionable task, and strict escalation from fast.
- [ ] Upgrade prerequisite implementation to v2 and cover the `1/1`, `1/2`, `2/1`, and `2/2` implementation/request matrix. `2/1` keeps strict-compatible semantics v1; `2/2` applies profile-aware semantics v2.
- [ ] Upgrade all five continue/PLAN-author surfaces and OpenCode-derived assertions from static prerequisite version 1 to version 2. Do not add runtime detection, fallback, or LLM-selected versions.
- [ ] Update Claude/Codex execute protocols in lockstep for fast handshake, `N+1` minimum dispatch, trigger-driven escalation to strict, profile-specific final inputs, truthful all-role metrics, primary final task-by-task review, mandatory full suite, one-write completion migration, final repair/re-review waves, final verdict, and unchanged archive gates.
- [ ] Preserve the already landed sample validator, semantic context view, compact report, cadence, zero-history, ledger, and evidence contracts through focused regression coverage; update README and Gemini/install surfaces only where the v2/profile-aware integration contract changes.
Verification:
1. Before dispatch, execute the current-run bootstrap as deterministic commands: require `run.md` status `executing`; require exactly one PLAN Task 001 and one unchecked progress row; require exactly one `Execution Profile: strict`; reject any `Profile Escalation` or `Task N: implemented|complete` marker; require the full progress `Execution BASE` equals `git rev-parse HEAD`; require `git diff --quiet ac3233cd9782c96a665e0f56e43fc17c5d82187f HEAD -- . ':(exclude).req-to-plan'`; and require `jq -e '.status == "ok" and .message == "representative_metrics_accepted" and .aggregate.representative == true' execution/phase-3-sample-evidence.json`. Record the commands/results in the controller evidence; do not invoke prerequisite v1.
2. Run `.venv/bin/python -m pytest tests/test_execution_metrics.py tests/test_agent_shortcuts.py tests/test_cli.py tests/test_gates.py tests/test_stage_templates.py tests/test_docs_consistency.py tests/test_install.py -q`; require exit 0 and record measured duration.
3. With isolated temporary strict and fast fixtures, exercise metrics append/finalize and the upgraded prerequisite checker: strict sequence remains accepted; fast `N implementers -> primary final reviewer` is accepted; fast task-reviewer and malformed/blocked continuations are rejected; valid final fixer/re-reviewer waves are accepted; versions `1/1`, `1/2`, `2/1`, and `2/2` return their specified semantics and exit behavior.
4. Run `.venv/bin/python -m pytest tests/ -q` with `scope=full_suite` and reason `shared execution metrics, profile recovery, and generated PLAN protocol`; require exit 0 with zero failures/errors. The final reviewer reruns the same suite fresh before approval.

## Risk Handling

| Risk | Handling Task | Closure |
|---|---|---|
| RISK-PERF-001 | PLAN-TASK-001 | [ADDRESSED] fast removes per-task reviewer dispatch while retaining one primary final review and a fresh full suite |
| RISK-CTX-002 | PLAN-TASK-001 | [ADDRESSED] zero-history semantic-view dispatch remains unchanged and regression-covered |
| RISK-METRIC-003 | PLAN-TASK-001 | [ADDRESSED] metrics becomes profile-aware without fabricated roles; strict grammar and non-authoritative status remain intact |
| RISK-IO-004 | PLAN-TASK-001 | [ADDRESSED] existing no-follow/no-replace primitives remain unchanged and covered by the full suite |
| RISK-CONTRACT-005 | PLAN-TASK-001 | [ADDRESSED] exact strict/fast role, checker-version, JSON, and finalization matrices are deterministic tests |
| RISK-AUDIT-006 | PLAN-TASK-001 | [ADDRESSED] every dispatched role retains canonical metrics and compact concern/defer evidence |
| RISK-GRAN-007 | PLAN-TASK-001 | [ADDRESSED] the reopened run contains one cohesive modify-only delta instead of replaying eight completed tasks |
| RISK-PROFILE-008 | PLAN-TASK-001 | [ADDRESSED] strict default, explicit fast eligibility, and trigger-driven one-way escalation fail closed |
| RISK-RESUME-009 | PLAN-TASK-001 | [ADDRESSED] profile-aware markers, BASE chain, resume, and atomic completion are integration-tested |
| RISK-FINAL-010 | PLAN-TASK-001 | [ADDRESSED] primary final review, fresh full suite, repair waves, approved verdict, and archive gate remain mandatory |
| RISK-PARITY-011 | PLAN-TASK-001 | [ADDRESSED] Claude/Codex lockstep, OpenCode derivation, and truthful Gemini behavior are static and install-tested |
| RISK-SEQUENCE-012 | PLAN-TASK-001 | [ADDRESSED] this run revalidates the same three confirmed samples before mutation, preserves the landed core baseline, and closes the remaining fast role-sequence incompatibility |

## Trace

| This ID | Upstream | Status |
|---|---|---|
| PLAN-TASK-001 | SPEC-VERIFY-001, SPEC-ROLE-002, SPEC-SAMPLE-003, SPEC-METRICS-009, SPEC-CONTEXT-010, SPEC-CONTEXT-011, SPEC-REPORT-012, SPEC-GRANULARITY-004, SPEC-PARITY-008, SPEC-PROFILE-013, SPEC-LEDGER-014, SPEC-RESUME-006, SPEC-FAST-005, SPEC-FINAL-007; SCOPE-IN-001, SCOPE-IN-002, SCOPE-IN-003, SCOPE-IN-004, SCOPE-IN-005, SCOPE-IN-006, SCOPE-IN-007, SCOPE-IN-008, SCOPE-IN-009, SCOPE-IN-010 | [ADDRESSED] The source tree outside `.req-to-plan/` matches the reviewed original Task 1–8 snapshot and this run records its own Execution BASE; this single reopened delta owns profile-aware metrics plus the original Task 9 integration and fresh Phase acceptance. |

## Upstream Summary (read-only)
# Spec

## Behavior Contracts
### SPEC-VERIFY-001 — Role verification cadence
Upstream: DES-EXEC-001 [ADDRESSED]

1. Implementer、task reviewer、fixer 和 task re-reviewer 默认只运行当前 task `Verification` 指定的 targeted tests 与可证明 directly affected tests。
2. 仅当满足下列任一条件时，task-level role 才运行 full suite：task 修改 shared/core path；风险/安全/迁移边界要求；targeted 失败；changed files 超出 brief 且无法证明安全；依赖覆盖关系不清；reviewer 无法从 diff、report 和 targeted evidence 建立充分信心。
3. 每次升级必须在 `Verification Records` 和 metrics 中记录 `scope=full_suite` 与具体 `reason`，不能只写“为保险起见”。
4. final reviewer 与每次 final re-reviewer 无条件运行 fresh full suite；final fixer 自己默认 targeted，修复后的 final re-review 再执行 full suite。
5. PLAN `Verification` 仍可显式要求 task-level full suite；显式要求属于 trigger，角色不得擅自降为 targeted。

### SPEC-ROLE-002 — Fresh role dispatch and zero inherited history
Upstream: DES-EXEC-001 [ADDRESSED]

1. 每次 role dispatch 都必须创建一个新的 child/subagent invocation；不得继续、复用或重新唤醒任何先前 implementer、reviewer、fixer、re-reviewer 或 final-role thread/session。
2. Codex 每次 dispatch 固定使用 `fork_turns="none"`。其他平台若暴露 inherited-history 参数，必须把 inherited turns/messages 设为零；若没有该参数，只能使用平台明确保证“不继承 controller/parent conversation”的新会话 API。无法保证时该平台在 dispatch 前 fail explicitly，不得以“fresh/minimal-history 等价”宣称合规。
3. Claude、OpenCode 与 Gemini 的安装 surface 必须分别写明其实际可调用的新会话机制或上述 fail-closed 分支；Gemini 仅能表达 wrapper/prompt prerequisite 时，不得声称已提供 subagent 能力。
4. 每个 role handoff 只包含自包含字段：work ID/run dir、role、task brief 或 final input paths、context-view 命令、Git/BASE 边界、verification/report/inline return contract。控制器不得粘贴 ACS、上一角色正文或 controller 对话摘要。

### SPEC-SAMPLE-003 — Representative metrics checkpoint
Upstream: DES-EXEC-001 [ADDRESSED]；DES-PROFILE-004 [ADDRESSED]

Phase 0 必须落地只读 internal command `execution-samples-validate`，公开给 controller 的参数恰为重复三次的 `--sample-dir <absolute-archived-run-dir>`；没有默认扫描、glob、相对路径、第四份样本或隐式选择。原始执行的 Phase 3 controller 只接受用户明确提供的三个 absolute paths，并在派发 `PLAN-TASK-008` 及任何 Phase 3 source mutation 前执行该命令。若执行中因原 Task 009 的 PLAN 权限缺口从 SPEC/PLAN 重开，新的 delta run 必须在其唯一 source task dispatch/mutation 前，使用同一组三个用户已确认的 absolute paths重新运行该 validator；不得把旧 evidence 文件当作新运行的验证结果，也不得重新发现或替换样本。参数个数不是三、canonical path 重复或证据不足时输出 `BLOCKED: representative_metrics_missing` 并 exit 3；未知 flag/语法错误 exit 2。命令本身只写 stdout/stderr，不修改样本、当前 run 或源码；controller 仅可把 JSON stdout 重定向到当前 run 已忽略的 `execution/phase-3-sample-evidence.json`。

每个候选先 lstat 拒绝 symlink/non-directory，再取得 strict canonical path，并从 filesystem root 对 canonical components 做 no-follow stable directory-fd traversal；三个 canonical paths 必须两两不同，目录 basename 必须等于经 `WorkId.parse` 验证的 embedded work ID。`run.md`、PLAN、progress、metrics 和 final-review 均相对 pinned sample fd 使用 no-follow pre-stat/open/fstat regular-file read；任何 symlink、non-regular、race 或读取失败只令该 sample 不合格，不修改样本或当前 run。

合格集合必须同时满足：

- 至少三个不同的 `(canonical run path, work_id)`；每个 `run.md` status 为 `archived`。
- metrics header 的 `profile` 为 `strict`、`instrumentation_schema` 等于当前受支持值、`instrumentation_complete=true`、`bootstrap_gap=none`、`metrics_finalized=true`、`change_shape` 是合法非 unavailable 枚举，并记录非空 `r2p_version`；当前 self-hosted run 固定不合格。
- PLAN task count 与 metrics `task_count` 一致；progress 中全部 PLAN tasks 为 `[x]`；final-review 的最后 verdict 为 Approved。
- 每个 run 对每个 task 至少有 implementer 与 task-reviewer block，并有 final-reviewer block；实际发生的 fixer、task re-reviewer、final fixer、final re-reviewer 也必须各有 sequence-contiguous block。发现 report/review/fix-wave 证据而缺 block 时样本失败；不推算不可见调用。
- 每个 invocation 必须有 measured `started_at`、`ended_at`、`elapsed_seconds`、`context_bytes`、`report_bytes`、非空 `verification_records_json` 和 measured `verification_total_seconds`；任一字段为 `unavailable`、invalid 或 totals 不一致时整个 sample 不合格。`context_mode` 与 `context_bytes_kind` 必须是 SPEC-METRICS-009 的合法配对，每条 verification record 必须含 measured duration 与合法 status。
- `model` 和 Token 三字段可为 `unavailable`；Token 不可得不影响资格，但 evidence report 必须明确写 `token comparison: unavailable`，不得用 bytes 推算 Token。
- 三个样本至少具有两个不同 `task_count`，或两个不同 finalized `change_shape`。

Validator 用 SPEC-METRICS-009 相同的 canonical JSON writer（UTF-8、`ensure_ascii=False`、`allow_nan=False`、`sort_keys=True`、compact separators、唯一尾随 newline）。Success 顶层 exact keys/types 为：

```text
status: "ok"
message: "representative_metrics_accepted"
samples: list[Sample]  # input order, length 3
aggregate: Aggregate
```

每个 `Sample` exact keys/types 为：`path:str`、`work_id:str`、`r2p_version:str`、`instrumentation_schema:int`、`profile:"strict"`、`task_count:int`、`change_shape:<classifier enum>`、`instrumentation_complete:true`、`bootstrap_gap:"none"`、`metrics_finalized:true`、`plan_complete:true`、`final_verdict:"Approved"`、`invocation_count:int`、`role_counts:RoleCounts`、`role_elapsed_total_seconds:<six-decimal string>`、`verification_total_seconds:<six-decimal string>`、`report_bytes_total:int`、`full_suite:FullSuite`、`context_totals:ContextTotals`、`token_totals:TokenTotals`、`rules:list[RuleResult]`。

`RoleCounts` exact keys are all seven role enums from SPEC-METRICS-009, each non-negative int；implementer/task_reviewer counts must equal task_count, final_reviewer至少 1，fix/re-review counts may be zero。`FullSuite` exact keys are `count:int` and `duration_seconds:<six-decimal string>`，由 verification records 中 `scope=full_suite` 求和。`ContextTotals` exact keys are `direct_acs` and `semantic_view`；each value exact keys are `invocation_count:int`、the mode's fixed `context_bytes_kind`、`context_bytes:int`，即使 count 为零也保留 zero object。`TokenTotals` exact keys are `status:"available"|"unavailable"`、`input_tokens:int|"unavailable"`、`output_tokens:int|"unavailable"`、`total_tokens:int|"unavailable"`；仅当该 sample 每个 invocation 三项 Token 都 measured 时 available并求和，否则三项全部 unavailable。所有 decimal totals使用 parsed six-decimal strings做 `Decimal` exact sum并以六位输出。

`RuleResult` exact keys are `rule`、`status`、`details`；success 中 rule 顺序固定为 `path_safety, identity_unique, archived_strict, instrumentation_complete, plan_complete, final_review_approved, role_coverage, measured_fields_complete, metrics_totals_consistent`，status 恰为 `passed`，details 恰为 `[]`。`Aggregate` exact keys are `sample_count:3`、`work_ids:list[str]`（input order）、`task_counts:list[int]`（sorted unique）、`change_shapes:list[str]`（sorted unique）、`task_count_diverse:bool`、`change_shape_diverse:bool`、`representative:true`；representative 要求两个 diversity bool 至少一个为 true。

Failure JSON exact keys为 `status:"error"`、`message:"BLOCKED: representative_metrics_missing"`、`exit_code:3`、`details:list[FailureDetail]`。`FailureDetail` exact keys为 `sample_dir:str`、`work_id:str|"unavailable"`、`rule:<上述九个 sample rules|"argument_count"|"aggregate_representative">`、`message:str`。零/少于/多于三次 `--sample-dir` 产生唯一 item：`sample_dir="invocation"`、`work_id="unavailable"`、`rule="argument_count"`，message含 observed count；此分支不读取任何路径。Canonical duplicate 对第一个出现保留正常 identity result，对每个后续重复项按 input order产生 `identity_unique` failure，sample_dir用该次原始 absolute argument，work_id用已解析值或 unavailable。Aggregate diversity failure使用 `sample_dir="aggregate"`、work_id unavailable。其余 details按 input order/上述 rule order稳定排列；不得含 source file contents、raw metrics blocks或任意额外 keys。Human output从同一 typed result渲染逐 sample identity/aggregates/rules，success 末行固定 `status: representative_metrics_accepted`；不得另行读取。

任一条件失败时，controller 不派发 Phase 3 role；原始执行的 `PLAN-TASK-008/009` 或 reopened delta 的 `PLAN-TASK-001` 保持 `[ ]`，source worktree/HEAD 必须与各自 Phase 3/delta BASE 相同。证据通过后，原 Task 008 或 reopened delta Task 001 只消费并引用本 run 的 `execution/phase-3-sample-evidence.json`，不得二次读取样本目录；其 report 直接呈现每个 Sample 的 identity/header/verdict/coverage/rules 与全部 measured aggregates。跨 `direct_acs`/`semantic_view` 只比较各自 context totals，不能把不同 byte kind 直接相减为 Token 收益；TokenTotals unavailable 时固定写 `token comparison: unavailable`。

### SPEC-GRANULARITY-004 — Cohesive change slice rule
Upstream: DES-PLAN-003 [ADDRESSED]

PLAN author 先按一个可观察行为/契约结果形成 phase-level cohesive slice。若一个 slice 同时需要 create 与 modify paths，现有 R19 gate 下必须展开为 operation-homogeneous task group；组内每个 task 必须交付可直接测试的 intermediate contract，reviewer 只可依赖已完成前驱，最后一个 integration/adoption task 运行完整 Phase acceptance。单 task rollback 只在先回滚其组内 declared dependents 后执行；整个 group 可反向拓扑回滚且不触及其他 Phase。

原始执行 PLAN 的布局和编号固定为 `2 / 4 / 1 / 2`：Phase 0 = 001 metrics core create → 002 integration modify；Phase 1 = 003 context core create → 004 internal CLI modify → 005 wrapper create/smoke → 006 surface adoption modify；Phase 2 = 007 modify；Phase 3 = 008 profile core create → 009 integration modify。依赖不新增 field。每个 task 的 `Steps` 第一条 semantic line exact 为 `Prerequisite: none` 或 `Prerequisite: PLAN-TASK-NNN`；declared edges 仅为 001→002、003→004→005→006、008→009，001/003/007/008 使用 none。跨 Phase 顺序只由 PLAN 编号、最低 actionable task selector 与上一 Phase acceptance 控制，不进入 rollback graph。

若原始执行在 Task 009 因 PLAN `Files` 权限缺口停止并从 SPEC/PLAN 重开，reopened run 以重开时排除 `.req-to-plan/` 的 source-tree snapshot 与该 run 启动时动态记录的 full `Execution BASE` 共同作为 operational baseline：scoped workflow commit 可以推进 HEAD，但已 reviewed-complete 的原 Task 001–008 不得重放、不得生成 no-op source commits，也不得复制旧 execution ledger。新 PLAN 只形成一个从 001 重新编号的 modify-only delta task，合并原 Task 009 integration paths 与完成 fast role topology 所必需的 `execution_metrics.py`/direct tests；该 task 承担新的 Phase acceptance。这个 delta 例外不改变未来由 continue surfaces 生成的 `2 / 4 / 1 / 2` 布局规则。

Prerequisite checker 分两个兼容版本交付。Task 001/002 尚无新 command，使用当前 strict controller 已消费的 legacy progress 做唯一 bootstrap preflight：Task 001 要求 run=`EXECUTING`、Execution BASE 为 full SHA、PLAN 恰有九个 anchors/checkboxes 且全部 `[ ]`、没有 profile/escalation/task marker、HEAD=Execution BASE、Task 001 是最低 unchecked；Task 002 要求同一 run/BASE/task-count，Task 001 恰有 `[x]` 与唯一 `review clean` complete marker、Task 002 是最低 unchecked、HEAD=Task 001 marker head。任一条件 unknown/mismatch 时不得 dispatch 或修改源码。

Task 002 integration 注册 read-only internal command `execution-prerequisite-check --work-id <id> --task <N> --require-version 1|2`，由 Phase 0 core 的 profile-neutral parser 实现 implementation v1。v1 只接受 requested semantics 1；原始执行的 Task 003–009 在 dispatch 前逐字传 `--require-version 1`。它只接受 legacy/explicit strict ledger，按 `Prerequisite` 检查唯一 reviewed-complete 前驱或 none+最低 unchecked，并对 fast-only marker/event fail closed。Phase 2 的五个 continue/PLAN-author surfaces 静态生成 version 1 preflight，不宣称 fast 支持。Success human 必须含 `prerequisite_satisfied`、work ID、task、`implementation_version: 1`、`semantics_version: 1`；JSON 在现有 success envelope 中加入 exact fields `work_id:str`、`task:int`、`implementation_version:int`、`semantics_version:int`、`effective_profile:"strict"`、`prerequisite:str`、`satisfied:true`。Requested 2 在 implementation v1 exit 6且不 mutation。

原 Task 009 adoption；或执行中重开后的 delta Task 001；将 implementation 升级为 v2，并在同一个 modify task 中再次修改/测试 Phase 2 的五个 continue/PLAN-author surfaces，使新生成 PLAN 静态传 `--require-version 2`；不依赖运行时探测或 LLM选择。Implementation v2 + requested 1 精确执行旧 strict semantics，返回 `implementation_version:2`、`semantics_version:1`、`effective_profile:"strict"`；implementation v2 + requested 2 调用 SPEC-RESUME-006 parser，返回 `implementation_version:2`、`semantics_version:2` 与实际 effective profile。后者 strict 要求前驱唯一 reviewed-complete；fast 接受合法 implemented marker 或 reviewed-complete；fast→strict recovery 必须先补齐 marker-chain review再满足 strict；none 要求 Execution BASE 存在且自己是最小 actionable task。旧已生成 PLAN 的 version 1 invocation继续兼容，future fast-capable PLAN固定 version 2；任何 requested version大于 implementation version exit 6。这样已落地 Phase 0–2 不依赖尚未创建的 Phase 3 parser，且不新增 PLAN field。

Reopened delta 的唯一 Task 001 不调用 prerequisite v1：execute-start 必然写入唯一 `Execution Profile: strict`，而 v1 Task 001 为原 self-host bootstrap 特意要求 profile line 不存在，两者不可同时满足。Controller 在任何 source mutation/role dispatch 前执行等价且更窄的 current-run bootstrap：run status=`EXECUTING`；PLAN/ledger 恰有一个 Task 001 且 `[ ]`；恰有一个 `Execution Profile: strict`；无 escalation/implemented/complete marker；full `Execution BASE` 存在并等于当前 HEAD；排除 `.req-to-plan/` 后 source tree 与 `ac3233cd9782c96a665e0f56e43fc17c5d82187f` 无 diff；SPEC-SAMPLE-003 本 run evidence accepted。任一 mismatch 均不得 dispatch/mutate。该 exception 只用于本次已批准的 execution-reopen delta，不改变旧 v1、未来生成 PLAN 的 v2要求，也不允许 controller 修改 ledger 来伪造兼容。

禁止 task-per-file/task-per-class 式拆分；R19 拆分必须有上述 intermediate contract，不得创建指向未来 handler 的不可运行 wrapper。也禁止把没有共同验收结果的多个行为合并。此规则只改变生成指导，不增加 `Dependencies`、不改变 `PLAN_TASK_FIELDS`、trace closure、quality gate、checkbox 或 BASE/commit/diff contract。

### SPEC-FAST-005 — Strict/fast role topology and runtime escalation
Upstream: DES-PROFILE-004 [ADDRESSED]

1. strict 是默认且保持 `N fresh implementers + N task reviewers + 1 final reviewer` 的最低结构。
2. fast 仅在 handshake 完成后使用 `N fresh implementers + 1 primary final reviewer` 的最低结构；fix/re-review waves 会增加调用数，`N+1` 不是硬上限。
3. fast implementer 提交并验证后，controller 保持 task checkbox `[ ]`，追加合法 implemented marker；不得生成空 task review 充数。
4. 发生 marker/HEAD/BASE 异常、verification failure、unexpected file、concern、`⚠️ DEFER` 未裁决、上游歧义或 shared/core/security/migration/dependency/config 风险时，controller 追加单向 fast→strict escalation event。
5. escalation 后先按 task 顺序 review 所有 implemented-but-unreviewed ranges；clean 后置 `[x]` 并写 strict-compatible complete marker，再从第一个未实现 task 继续 strict loop。已经升级的 run 不得恢复 fast。

### SPEC-RESUME-006 — Profile-aware ledger and BASE recovery
Upstream: DES-PROFILE-004 [ADDRESSED]

1. 新 run 恰有一个 immutable initial profile line；legacy ledger 没有 profile line 且没有 fast-only marker/event 时按 strict 解释。
2. effective profile 是 initial profile 经过最后一个合法 escalation event 后的结果。重复 initial line、strict-origin escalation、重复/逆向 escalation、malformed reason 或 legacy ledger 携带 fast-only marker/event 均为 conflict。
3. Ledger task states 必须按 PLAN number 形成 `reviewed-complete prefix → implemented-but-unreviewed contiguous segment → untouched suffix`；初始 fast 的 reviewed prefix 为空，因此 implemented segment 从 Task 1 开始；fast→strict recovery 可逐 task 扩大 reviewed prefix，剩余 implemented segment 必须紧邻其后。fast resume 跳过前两个 segment，选择 untouched suffix 的最小编号；strict recovery 必须先 review implemented segment，不能先实现 untouched task。任何空洞、乱序或重叠均为 conflict。
4. Task 1 BASE 仅来自 full `Execution BASE`；Task N BASE 仅来自 Task N-1 合法 complete/implemented marker 的 head。不得使用 `HEAD~1` 或 resume 时的新 HEAD 推断 BASE。
5. checked task 不得仍保留 implemented marker。fast final approval 前，controller 重新验证 HEAD、BASE chain、全部 markers 和 task count 未变化，在内存中构造完整新 ledger，将所有 implemented markers 替换为 `Task N: complete (commits <base7>..<head7>, final review clean)` 并将对应 checkbox 全部置 `[x]`，随后只调用一次 `atomic_write_text(progress.md, full_text)`；禁止逐 task 写盘。replace 前失败保留完整旧 fast ledger；replace 后即使进程中断，ledger 也处于全部 strict-compatible complete 状态，final-review gate 仍阻止缺少 Approved verdict 的 archive。
6. abbreviation 必须能由 `git rev-parse --verify` 唯一解析且形成从 Execution BASE 到 current HEAD 的有序祖先链；否则升级 strict recovery 或在无法确定 BASE 时 BLOCKED。

### SPEC-FINAL-007 — Profile-specific final review inputs
Upstream: DES-PROFILE-004 [ADDRESSED]

- strict final reviewer 读取 semantic context view、`07-plan.md`、progress、所有 task reports、所有 task reviews、所有 Minor/concern/`⚠️ DEFER` 和 execution-base→HEAD final diff。
- fast final reviewer 读取 semantic context view、`07-plan.md`、progress、所有 task reports、所有 Minor/concern/`⚠️ DEFER` 和 final diff；不得要求不存在的 task review files。
- fast final reviewer 是每个 task 的 primary reviewer，必须逐 task 检查 Spec References、Files vs diff、verification records、commit range 和 cross-task behavior，并运行 full suite。
- findings 使用现有 single final-fixer + regenerated final diff + final re-review loop。所有实际 dispatch 都产生 metrics block。
- 只有 clean final review 才能替换 markers、置全部 `[x]`、finalize metrics、写最后 `Verdict: Approved` 并调用 archive；archive gate 的 checkbox/final-verdict 语义不变。

### SPEC-PARITY-008 — Agent surface parity
Upstream: DES-COMPAT-005 [ADDRESSED]

- 完整 execute protocol：Claude execute command 与 Codex execute skill 同步。
- OpenCode execute/continue 由 Claude commands 派生；安装测试必须核对派生结果包含 load-bearing tokens。
- Gemini execute/continue 保留 wrapper forwarding，并在 description/prompt 中携带 strict default、fast handshake/preflight、cohesive slice 和 fail-closed 摘要。
- Phase 2 continue 同步面固定为 `stage_templates.py`、Claude 通用 skill、Claude continue command、Codex continue skill、Gemini continue command；不得只更新部分表面。
- Phase 2 首次把上述五面写为 prerequisite checker semantics v1；原 Phase 3 Task 009 或 reopened delta Task 001 在同一 patch 把这五面与 OpenCode-derived test 升级为 v2。两次都是现有文件 modify，不新增生成面或 capability auto-detection。
- `tests/test_docs_consistency.py` 同时保护旧 EXE/FR-CM tokens 与本需求新增 tokens，不删除 dirty-tree、BASE、final review、full suite、`⚠️ DEFER` 或 archive 契约。

## API / Data / Config Contracts
### SPEC-METRICS-009 — Metrics file schema and ownership
Upstream: DES-EXEC-001 [ADDRESSED]

metrics 不参与 run state、resume、completion 或 archive gate；已存在 metrics 永不被普通 resume 覆盖。首次 `run-execute-start --profile strict|fast` 使用下列 recoverable start transaction：

唯一 public core entry signature 为 `start_execution_transaction(base_path: Path, work_id: WorkId, profile: str) -> RunRecord`。它内部拥有 `RunStateManager` load/status validation、symlink-safe PLAN read/anchor extraction、pinned run-directory handle、lock/marker/progress/metrics writes、state save 和 recovery；CLI `_cmd_run_execute_start` 只负责 argparse、调用该 entry 和 human/JSON formatting，不得预加载 `RunRecord`、另行解析 anchors 或以另一 signature 调用。

1. 相对 pinned run fd 安全打开 `logs/execute-start.lock`，取得 process-released exclusive nonblocking lock；POSIX 使用 `fcntl.flock(LOCK_EX|LOCK_NB)`。lock busy 或平台没有可靠等价 capability 时 exit 6、zero mutation。lock file 位于已忽略的 `logs/`，必须是 no-follow regular file。
2. 持锁期间用 `mkdir("execution", dir_fd=run_fd)` 原子创建最终目录；`mkdir` 的 EEXIST 是 no-clobber conflict/recovery input，任何并发创建的 empty dir、file 或 symlink 都不会被替换。记录 directory dev/ino，并在其中用 O_EXCL 写 `.start-transaction.json`；它是 canonical single-line JSON，exact fields 为 `schema: 1`、`work_id`、`profile`、`task_count`、`execution_base`（full SHA）。随后原子写入并校验 `progress.md` 与 `metrics.md`。
3. 两个 ledgers 验证完成且 marker 仍存在时保存 `run.md` 的 `EXECUTING` 状态；save 成功后才删除 marker并 fsync directory（capability available 时）。save 前的普通异常触发 best-effort rollback，但只能在仍持锁、directory dev/ino 未变、marker 内容匹配且 children 是 marker/progress/metrics 的允许子集时删除本次目录。save 已成功但 marker cleanup 失败时不得删除 execution；保留 marker 并由 executing recovery 完成。其他情况保留现场并 exit 6。
4. process crash 自动释放 lock。重试取得 lock 后：`closed + marker` 仅在 marker 匹配当前 work/profile/task count/BASE、目录 identity 稳定且 children 是允许子集时删除该 owned partial directory并从步骤 2 重建；`closed + no marker + two exact initial ledgers` 在 structure gate 仍通过时只补做 status transition。fast 两种 recovery 都要求调用者重新给出 `--profile fast --confirm-fast-eligible`。其他 single-file、partial、mismatched、symlinked、foreign-marker 或 extra-child 状态 exit 6 且不覆盖。
5. `executing + no marker + complete ledgers` 走 normal idempotent resume；`executing + matching marker + complete ledgers` 在持锁复核 status/work/profile/task count/BASE 后只删除 marker并继续 resume；`executing + marker/missing/partial/mismatched ledgers` fail closed。没有 sibling temporary directory，因此 crash-before-ledger 不产生未忽略的 worktree residue。fault injection 必须覆盖 lock/capability、mkdir 前后 crash、marker/progress/metrics writes、status save、marker removal、owned rollback/rebuild、executing marker cleanup、foreign residue和 concurrent file/empty-dir/symlink no-clobber。

本需求自身由旧版本启动执行时使用唯一 self-hosted bootstrap command：

```text
execution-metrics-bootstrap --work-id WF-20260829-r2p-execute-token-phase-r2p --profile strict --self-hosted-gap-through-task 002
```

Bootstrap 使用独立 `logs/metrics-bootstrap.lock`：相对 pinned run fd 以 `O_CREAT|O_RDWR|O_NOFOLLOW` 打开、fstat regular/identity 后取得 `fcntl.flock(LOCK_EX|LOCK_NB)`；lock busy 或平台缺少等价 capability 时 exit 6。首次发布在 pinned `execution/` fd 下创建唯一 `.metrics-bootstrap.<pid>.<32-lower-hex>.tmp`，flags 固定 `O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW`、mode `0o600`。Temp fd 从 create 保持打开直到 publish identity验证完成：写完 exact UTF-8 header并 fsync 后，对 open fd `fstat` 保存 regular mode/dev/ino，再对 temp name no-follow lstat并要求三者匹配；不得先 close。

随后调用 `os.link(temp, "metrics.md", src_dir_fd=execution_fd, dst_dir_fd=execution_fd, follow_symlinks=False)` 原子 no-replace publish。link success 后立即在仍打开 temp fd 的条件下，分别对 temp name 与 `metrics.md` 做 no-follow lstat；open-fd fstat、temp lstat、final lstat 必须都是同一个 saved regular dev/ino，任一 missing/symlink/replacement/mismatch 均 exit 6、不得读取/接受/删除 final。三方匹配后才 fsync execution fd、按 saved identity unlink本 invocation temp、再次 fsync并关闭 fd。平台缺少 dir-fd hard-link/no-follow/lstat 或 fsync capability时 fail closed，绝不退化为 `os.replace`；final target永不由协议 unlink/replace。

Crash/retry matrix 固定如下：publish 前崩溃最多留下唯一 temp，retry 不信任/不删除任何 abandoned temp并创建新 nonce temp；link success 后崩溃时 final 已是完整 hard-linked header，retry 走 exact-existing success；并发/foreign final 在 link 时产生 EEXIST，随后只安全读取 exact final，exact 才 idempotent success，mismatch/unsafe 则 conflict。普通异常只可在仍持 lock、final 尚不存在且当前 temp path仍与 saved dev/ino匹配时 best-effort删除当前 temp；cleanup失败保留 ignored residue，不改变判定。Tests fault-inject temp create/write/fsync、pre-link temp unlink/regular replacement/symlink replacement、link/EEXIST、post-link final-name replacement、三方 identity check、dir fsync、temp unlink/close、post-publish return，并验证 mid-write crash 永不产生 partial `metrics.md`、source swap 永不被接受。

所有调用先验证 run 为 `EXECUTING`、work ID/PLAN task count/Execution BASE 匹配、legacy profile 按 strict 解释、Task 001/002 分别有唯一 reviewed-complete record。metrics 不存在时属于首次创建：还必须确认 Task 003 没有 role/task state、HEAD 等于 Task 002 complete head，再使用上述 publish protocol。metrics 已存在时属于 retry/resume：不得再要求 Task 003 未开始；必须安全读取并 exact-match work/profile/task_count/schema、`instrumentation_complete=false` 与 canonical `bootstrap_gap=execution_start_through_task_002_reviewed_complete`。Header 后为空或只含从 Task 003 起、与 progress/task order 一致、sequence 连续且完整的 invocation blocks 时返回 idempotent success，并从下一 sequence append。Task 001/002 block、partial/乱序 block、unsafe/non-regular、foreign/mismatched header 或结构损坏均 exit 6 且 zero overwrite/delete。该 exception 不做历史回填，首个 measured role 是 Task 003 implementer，当前 run 永不符合 SPEC-SAMPLE-003。未来正常 start 从首个 role 采集，并只写 complete/none 组合。

Header fields and values:

```text
# Execution Metrics
work_id: <validated WorkId>
r2p_version: <R2P_VERSION>
instrumentation_schema: <positive integer constant>
profile: strict|fast
task_count: <PLAN anchor count>
instrumentation_complete: true|false
bootstrap_gap: none|execution_start_through_task_002_reviewed_complete
change_shape: unavailable
metrics_finalized: false
```

Header combination matrix 是封闭集合：正常 start 只允许 `instrumentation_complete=true` + `bootstrap_gap=none`；仅上述精确 work ID 的 self-hosted bootstrap 允许 `false` + `execution_start_through_task_002_reviewed_complete`。任何其他组合 parse fail closed；normal resume 不把 false 改成 true，finalization 只更新 shape/finalized。

Invocation block grammar（字段顺序固定，每个 scalar 占一行；invocation 编号从 1 连续且唯一）：

```text
## Invocation <contiguous positive integer>
role: implementer|task_reviewer|fixer|task_rereviewer|final_reviewer|final_fixer|final_rereviewer
task: <positive integer>|final
model: <non-empty identifier>|unavailable
started_at: <UTC YYYY-MM-DDTHH:MM:SS.ffffffZ>
ended_at: <UTC YYYY-MM-DDTHH:MM:SS.ffffffZ>
elapsed_seconds: <non-negative decimal with exactly 6 fractional digits>
context_mode: direct_acs|semantic_view
context_bytes_kind: declared_payload_bytes|semantic_payload_bytes
context_bytes: <non-negative integer>
verification_records_json: <single-line canonical JSON array>|unavailable
verification_total_seconds: <non-negative decimal with exactly 6 fractional digits>|unavailable
report_bytes: <non-negative integer>
status: complete|approved|changes_requested|blocked
concerns_json: <single-line canonical JSON array of strings>
fix_wave: <non-negative integer>
input_tokens: <non-negative integer>|unavailable
output_tokens: <non-negative integer>|unavailable
total_tokens: <non-negative integer>|unavailable
```

`verification_records_json` 的每项恰有 `command`、`scope`、`reason`、`elapsed_seconds`、`status`；scope 为 `targeted|directly_affected|full_suite`，status 为 `passed|failed`，command/reason 是非空 string，elapsed 是匹配 `^[0-9]+\.[0-9]{6}$` 的 JSON string。Writer 使用 `json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":"))`；parser 要求单行 UTF-8 JSON、exact keys、无 NaN/Infinity。`concerns_json` 同样 canonical；无 concern 为 `[]`。successful invocation 的 records 必须非空；仅 `blocked` invocation 可写 `unavailable`，此时 total 也必须 unavailable。其他情况下 controller 用 `Decimal` 对 record duration strings 求和并输出 exactly six decimals；total 必须精确相等。

Role/task/status/fix-wave matrix 固定如下：

- `implementer|fixer`：task 是正 PLAN task number，status `complete|blocked`；`implementer` wave 0，`fixer` wave 从 1 开始。
- `task_reviewer|task_rereviewer`：task 是正 PLAN task number，status `approved|changes_requested|blocked`；初次 reviewer wave 0，fixer 与其对应 re-reviewer 使用相同正 wave。
- `final_reviewer|final_fixer|final_rereviewer`：task 恰为 `final`；initial final reviewer wave 0，final fixer 与对应 final re-reviewer 使用相同正 wave；mutation role 只允许 `complete|blocked`，review role 只允许 `approved|changes_requested|blocked`。
- `direct_acs` 只配 `declared_payload_bytes`，`semantic_view` 只配 `semantic_payload_bytes`。Token 三字段要么全部 unavailable，要么全是整数且 `total=input+output`。

Controller owns every block and measures role timestamps/context/report bytes；timestamps use wall clock。Controller 与 role 均用 `time.monotonic_ns()` 捕获 start/end，要求 `end_ns >= start_ns`，再计算 `Decimal(end_ns-start_ns) / Decimal(1_000_000_000)`，以 `ROUND_HALF_UP` quantize 到 `Decimal("0.000001")` 并保留六位序列化；小于/等于/大于半微秒的边界都按此规则。Role 对每条 verification command 使用同一算法，persists `Verification Records`, and returns records plus total inline；total 只精确求和已量化 strings，不再次 quantize。Controller validates/copies values, never infers them；invalid return becomes a blocked/concerned block and cannot qualify as a representative sample。`direct_acs/declared_payload_bytes` is the raw UTF-8 sum of the six declared ACS sources；`semantic_view/semantic_payload_bytes` is context-view aggregate semantic bytes。

Final clean 时 controller 从 full `Execution BASE` 与 `HEAD` 运行 `git diff --name-status -z <base> HEAD --` 并按 NUL records 解析。accepted token grammar 恰为：单路径 `A|M|D|T`；双路径 `Rddd|Cddd`，其中 `ddd` 恰为三位十进制 `000..100`。A/M/D/T 使用一个 path；R/C 同时计 old 与 new path。`U|X|B`、缺失/多余 path、score >100、非三位 score 及任何其他 token 一律使 finalization 失败。Invalid Git output、空 changed-path set 或不是 repo-relative POSIX path 的值同样失败。路径比较 case-sensitive；拒绝 absolute、空 component、`.` 或 `..`。对所有合法 changed paths 执行以下唯一算法：

1. 若任一完整 path component 恰为 `migration` 或 `migrations`，返回 `migration`。
2. Test path：任一 component 恰为 `test|tests`，或 basename 匹配 `^test_.+`、`^.+_test(?:\..+)?$`、`^.+\.test\..+$`、`^.+\.spec\..+$`。若所有 changed paths 都是 test，立即返回 `test_only`。
3. 从后续判断移除 tests。Doc path：first component 为 `docs`，或 suffix 恰为 `.md|.rst|.adoc|.txt`。Config path：suffix 恰为 `.json|.yaml|.yml|.toml|.ini|.cfg|.properties`。其余 non-test path 为 source。
4. 若 source 非空，root-level source module 为 `_root`，其他 source module 为 first component；一个 unique module 返回 `single_module_code`，多于一个返回 `cross_module_code`。同行存在 docs/config 不改变该 code 分类。
5. 若 source 为空且 non-test set 非空：全部 doc 返回 `docs_only`；否则全部 config 返回 `config_only`；docs+config 或其他组合返回 `mixed`。

Classifier 枚举仅为 `migration|single_module_code|cross_module_code|docs_only|config_only|test_only|mixed`。tests 必须覆盖 add/modify/delete、rename/copy、root source、大小写、migration test path、docs+tests、config+tests、docs+config 与 empty diff。Controller 一次 `atomic_write_text` 替换完整 metrics header 为枚举值和 `metrics_finalized: true`；任何分类/写入失败保留 unavailable/false，archive 正确性不受影响，但该 run 不能成为 Phase 3 样本。

### SPEC-CONTEXT-010 — Stable directory-fd read API
Upstream: DES-CTX-002 [ADDRESSED]

`tools/workflow_cli/execution_context.py` 私有的 pinned-tree read helpers 必须满足以下契约；不得把这组固定六源 traversal 临时下沉到 `atomic.py` 或改变 `atomic.read_regular_text` 的单文件 public contract：

1. 用 `os.open` 的 `dir_fd`、`O_DIRECTORY`、`O_NOFOLLOW`、`O_NONBLOCK` 逐组件打开 repo root → `.req-to-plan` → work ID → `execution`；缺少平台能力时抛出 unsafe conflict。
2. 相对 pinned dir fd 对 final file 执行 no-follow pre-stat → `open(O_NOFOLLOW|O_NONBLOCK)` → fstat，并比较 dev/ino/regular mode；FIFO/device/directory/symlink/race 均不读取。
3. 从同一个 pinned run fd 读取并解析 `run.md`，验证 embedded WorkId 与请求值相同、status 为 `EXECUTING`；不得混用另一次 path-based record load。
4. pin 后父 path 被 rename/replaced 时继续读取原 pinned tree；不承诺侦测 path-name drift，也不得重开路径切换到替换树。
5. 所有 fds 在成功/异常路径关闭；不产生临时 context files。

### SPEC-CONTEXT-011 — Context view command and output
Upstream: DES-CTX-002 [ADDRESSED]

Public wrapper：`r2p-context-view --work-id <id>`；internal command：`context-view --work-id <id>`；无 `--role`。仅 EXECUTING run 可成功。

Source order is fixed:

1. `02-project-context.md`
2. `03-requirement-brief.md`
3. `04-risk-discovery.md`
4. `05-design.md`
5. `06-spec.md`
6. `execution/progress.md`

For each source:

```text
semantic = strip_nonsemantic_markdown(raw).rstrip()
source.raw_bytes = len(raw.encode("utf-8"))
source.semantic_bytes = len(semantic.encode("utf-8"))
chunk = "===== " + relative_path + " =====\n" + semantic
content = "\n\n".join(chunks) + "\n"
aggregate.raw_bytes = sum(source.raw_bytes)
aggregate.semantic_bytes = len(content.encode("utf-8"))
```

Human success uses `sys.stdout.write(content)` and no formatter prefix. JSON success keys are exactly the existing success envelope plus `work_id: str`、`sources: list[{path,raw_bytes,semantic_bytes}]`、`raw_bytes: int`、`semantic_bytes: int`、`content: str`；`status="ok"` and `message` remain present. Invalid args exit 2；missing run/source exit 7；wrong status、unsafe path/type/race/capability exit 6。Error JSON uses existing `status/message/exit_code/details?` and never includes partial content/sources。

### SPEC-REPORT-012 — Compact role artifacts and inline return
Upstream: DES-CTX-002 [ADDRESSED]

Every persistent report/review has these non-optional sections：`Status`、`Commit Range`、`Changed Files`、`Verification Records`、`Concerns`、`⚠️ DEFER`。Task review additionally has `Spec Verdict` and `Quality Verdict`。不存在的 concerns/defer 明确写 `none`。任何角色发现的每条 concern/defer 必须同时进入持久文件和 inline `concerns`。

Inline return keeps existing status/path/commit/test fields and adds `verification_records` and `verification_total_seconds`；controller narration仍只保留 bounded summary，不粘贴报告正文。Fast final consumes every task report；strict final consumes reports and reviews。

### SPEC-PROFILE-013 — Execute profile CLI handshake
Upstream: DES-PROFILE-004 [ADDRESSED]

Shortcut arguments：`--profile {strict,fast}` optional、`--confirm-fast-eligible` boolean、`--reject-fast-ineligible` boolean、`--reason <single-line>`。Confirm/reject mutually exclusive；它们只允许和 `--profile fast` 一起；reason 只允许且必须和 reject 一起。Invalid combinations exit 2 before mutation。

Deterministic structure eligibility 恰为 locked tier base `LIGHT` 且 modifier set 为空；STANDARD、任何 modifier、未锁 tier 或无法解析的 tier 都是 ineligible。结构门通过后，agent semantic gate 必须逐 PLAN task 确认：行为局部且机械；`Files` 明确且不触及 shared/core/security/migration/dependency/config；没有 unresolved ambiguity/undecided point；`Verification` 是可直接执行且能独立判定该 task 的确定性命令。任一 false/unknown 都必须 reject，不能 confirm。

Closed run matrix:

| Invocation | Result | Mutation |
|---|---|---|
| profile omitted / `strict` | start strict; seed ledgers | yes |
| `fast` without decision flag, structure ineligible | exit 6 `fast_profile_ineligible` | none |
| `fast` without decision flag, structure eligible | exit 0 stop `fast_profile_review` with work/plan/tier/modifiers | none |
| `fast --reject-fast-ineligible --reason ...` | exit 6 `fast_profile_ineligible` | none |
| `fast --confirm-fast-eligible`, structure eligible | start fast; seed ledgers | yes |
| `fast --confirm-fast-eligible`, structure changed/ineligible | exit 6 | none |

Direct terminal confirm is an explicit trusted human attestation；CLI validates structure but does not claim semantic validation。Agent surfaces must always perform PLAN semantic review between first stop and confirm/reject。

Executing matrix：no profile → reuse effective；same profile → idempotent resume；different profile → exit 6；任何 confirm/reject flag → exit 6。Legacy ledger without profile → strict。Other run statuses retain `plan_not_ready` conflict。

### SPEC-LEDGER-014 — Profile and task marker grammar
Upstream: DES-PROFILE-004 [ADDRESSED]

New ledger lines use exact unfenced grammar:

```text
Execution Profile: strict
Execution Profile: fast
Profile Escalation: fast -> strict (reason: <non-empty single line>)
Task N: implemented (commits <base7>..<head7>, verification recorded)
Task N: complete (commits <base7>..<head7>, final review clean)
```

Initial profile is unique and immutable。Only one fast→strict event is legal。Parser rejects malformed/duplicate/contradictory lines and fast-only lines in a legacy profile-less ledger。Existing strict marker `Task N: complete (commits <base7>..<head7>, review clean)` remains accepted for backward compatibility。Checkbox regex/gate stays unchanged；implemented marker never satisfies completion。

Parser 先使用 `strip_nonsemantic_markdown`，因此 fenced examples 与 HTML comments 不产生 ledger tokens。`N` 是无前导零的正十进制数并必须等于对应 PLAN number；`base7/head7` 恰为小写 `[0-9a-f]{7}`；reason 拒绝 `\r`/`\n` 且 trim 后非空。每个 task 在任一合法 ledger state 最多一条 implemented 或 complete marker，不得同时存在两者；profile/event/marker-like malformed lines fail closed，而不是被忽略。

## External Documentation Checked
N/A — no external dependencies

## Test Matrix
| Contract | Required deterministic coverage |
|---|---|
| SPEC-VERIFY-001 / SPEC-ROLE-002 | 双 execute surfaces 包含 targeted escalation matrix、final full suite、all-role metrics、Codex `fork_turns="none"`；各平台 new-session/no-history 或 fail-closed；旧 hardening tokens 仍存在。 |
| SPEC-METRICS-009 | 唯一 transaction signature/ownership；locked no-clobber execute-start、marker/status crash recovery、foreign residue 与 fault injection；self-host lock + open temp fd + fsync + hard-link no-replace + post-link three-way identity、pre-link temp unlink/regular/symlink replacement、post-link final replacement、每个 crash point、EEXIST race、abandoned temp、first-create vs exact-header retry/resume、canonical gap、Task003+ blocks、mismatch zero-overwrite；exact header/JSON grammar、role/task/status/wave matrix、`monotonic_ns` + `ROUND_HALF_UP` boundary/totals、context pair、all-role blocks；A/M/D/T/Rddd/Cddd classifier table 与 failed-finalize non-gating。 |
| SPEC-CONTEXT-010 | temp workspace 中 directory/file symlink、non-regular、FIFO、pre-stat/open race、capability unavailable、fd cleanup、parent replacement pinned-tree behavior。 |
| SPEC-CONTEXT-011 | Unicode、comments、read-only blocks、fences、whitespace-only、fixed order/separators/one newline、per-source/aggregate bytes、human/JSON exact keys、missing/no partial、wrong status。 |
| SPEC-REPORT-012 | 两完整 execute surfaces 强制所有 section、inline verification、every-role `⚠️ DEFER` propagation；fast/strict final input matrix。 |
| SPEC-GRANULARITY-004 / SPEC-PARITY-008 | Task001/002 legacy bootstrap matrix；reopened-delta-Task001 exact explicit-strict manual bootstrap；implementation×requested `1/1,1/2,2/1,2/2` semantics/exit/JSON fields；Task007五面静态v1、原Task009/reopened-delta-Task001同五面静态v2及旧PLAN兼容；future `2/4/1/2` operation-homogeneous layout、execution-reopen delta 不重放 reviewed-complete tasks、Steps-only exact grammar、group-only edge/rollback、OpenCode derived install + Gemini description；PLAN fields/schema/trace tests unchanged。 |
| SPEC-PROFILE-013 | closed handshake 参数矩阵、zero-mutation snapshots、structure recheck、reject reason newline rejection、direct confirm、executing same/different/flags、legacy strict。 |
| SPEC-LEDGER-014 / SPEC-RESUME-006 | comment/fence-aware exact regex、unique profile/events/markers、malformed lines、marker continuity、BASE chain、checked/implemented conflict、first actionable task、strict escalation/recovery、atomic all-task final migration crash points、legacy strict complete marker。 |
| SPEC-FAST-005 / SPEC-FINAL-007 | fast no per-task reviews、runtime triggers strict recovery、final primary task-by-task review、full suite、fix/re-review metrics、checkbox only after approval、archive gate fails before approval。 |
| SPEC-SAMPLE-003 | 0/2/3/4 argument-count details、canonical duplicate ordering、no discovery/write、canonical exact nested JSON golden/error detail order、三 canonical no-follow archived paths、complete/none header、schema/profile/finalized/verdict/task count/role coverage、all seven role counts、duration/report/full-suite/context/token aggregates、fix-wave evidence、shape/task diversity；原Task008及reopened delta各自在本run重新验证/仅消费 evidence，且每个失败分支保持 source/checkbox/HEAD 不变。 |

Implementation verification uses project-required `.venv/bin/python -m pytest`。每个 PLAN task 先运行其 targeted module/tests；每个 Phase task review 根据 SPEC-VERIFY-001 决定是否 full suite；最终 whole-branch review 必须运行 `.venv/bin/python -m pytest tests/ -q` 并记录 fresh result。

## Non-goals
- 不生成持久化 ACS/context bundle、manifest、content hash 或 drift gate。
- 不改变 CLI/agent responsibility boundary；CLI 只管理结构、安全读取和 deterministic parsing/formatting。
- 不引入 shared implementer、parallel current-branch writes、batch reviewer 或 balanced profile。
- 不弱化 dirty-tree、Execution BASE、task commit/diff、final full suite、final verdict 或 archive gate。
- 不把 unavailable/estimated values 写成 measured metrics，不把 bytes reduction 声称为精确 Token reduction。
- 不新增第三方依赖；directory-fd/context/filter/profile logic 使用 Python stdlib 与仓库现有模块。

## PLAN Handoff

本次 reopened run 只规划一个从 `PLAN-TASK-001` 重新编号的 operation-homogeneous `modify` delta；排除 `.req-to-plan/` 的 source tree 必须与原执行 Task 001–008 reviewed-complete 后的 snapshot `ac3233cd9782c96a665e0f56e43fc17c5d82187f` 一致，执行启动后另以本 run 动态记录的 full `Execution BASE` 约束 HEAD。PLAN 不得重放这些任务、复制旧 execution ledger或创建 no-op source commits。

唯一 delta task 必须同时满足：

1. `Files` 包含原 Task 009 的全部 modify paths，并新增 `tools/workflow_cli/execution_metrics.py` 与 `tests/test_execution_metrics.py`；不得包含 create/delete/rename path。
2. source mutation/role dispatch 前，用用户已确认的三个绝对样本路径重新运行 SPEC-SAMPLE-003 validator，并把 JSON stdout 写入 reopened run 自己的 ignored `execution/phase-3-sample-evidence.json`：
   - `/Users/xubo/Desktop/test-1/.req-to-plan/archive/WF-20260831-run-776c763d`
   - `/Users/xubo/Desktop/test-2/.req-to-plan/archive/WF-20260831-run-e31ea18d`
   - `/Users/xubo/Desktop/test-3/.req-to-plan/archive/WF-20260831-1-2`
3. 第一条 semantic Steps line 为 `Prerequisite: none`。派发前由 controller 执行 SPEC-GRANULARITY-004 的 exact explicit-strict manual bootstrap，不能调用必然拒绝 profile line 的 checker v1，也不能修改 ledger 绕过它。实现本身升级 checker 到 v2并同步五个 PLAN-author surfaces；`1/1,1/2,2/1,2/2` 通过隔离 fixture 验证。
4. TDD 先证明 strict metrics sequence 完全兼容，再证明 fast 接受 `N implementers -> primary final reviewer` 以及合法 final repair waves；fast task-reviewer、缺失/重复/乱序/blocked continuation 必须 fail closed，不能生成虚假 role block。
5. 同一个 task 集成 SPEC-PROFILE-013、SPEC-LEDGER-014、SPEC-FAST-005、SPEC-RESUME-006、SPEC-FINAL-007、SPEC-METRICS-009 与相关 parity，并通过直接受影响测试和 fresh full suite；最终 whole-branch review 再运行 fresh full suite。

Global Constraints 必须保留：TDD-first；所有 source edits 在当前分支串行；clean-tree/BASE/task-scoped commit/diff；无 push/PR/远程 mutation授权；Claude/Codex lockstep；OpenCode derived/Gemini tests；metrics non-authoritative；final review/full suite/archive gates 不变。

## Trace
<!-- Map this stage's IDs to upstream/downstream. R3 derives & checks closure. -->
| This ID | Upstream | Status |
|---|---|---|
| Spec headings above | Approved DESIGN v8; execution-reopen source snapshot ac3233c plus dynamic Execution BASE | [ADDRESSED] Behavior contracts remain intact; PLAN handoff prevents replay, defines an executable explicit-strict bootstrap, and gives the remaining profile-aware metrics integration explicit file authority. |
<!-- /r2p-read-only -->

## Project Context (read-only)
# Project Context Pack

- repo_root: `/Users/xubo/x-skills/req-to-plan`
- languages: {'Python': 26297, 'JavaScript': 31}
- package_managers: npm, pip
- test_commands: ['npm test']
- entrypoints: ['tools/workflow_cli/__main__.py']
- config_files: ['requirements.txt']
- dependencies (1):
  - pyyaml>=6.0 (pip)
- source_dirs: ['bin', 'docs', 'requirements', 'tests', 'tools']
<!-- /r2p-read-only -->

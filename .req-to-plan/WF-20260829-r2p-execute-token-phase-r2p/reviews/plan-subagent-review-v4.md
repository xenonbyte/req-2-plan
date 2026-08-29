# PLAN 强制独立评审 v4

Verdict: Approved

## Review Scope

已完整审阅 `03-requirement-brief.md` v1、`04-risk-discovery.md` v3、`05-design.md` v8、`06-spec.md` v7、`07-plan.md` v4 与上一轮 `plan-subagent-review-v3.md`，并只读核对当前 R19 gate、`WorkId`/CLI 入口、shortcut 调用链、wrapper bootstrap、文件存在性和当前分支。

现行 deterministic PLAN quality gate 对 v4 返回 `passed=True`/exit 0；当前 exact bootstrap Python 为 Python 3.14.5，能在 `-E` 下导入本项目与 PyYAML。本评审未修改源码或上游阶段产物。

## v3 Findings Closure

### I-1 — Closed

- `Execution Readiness` 与 Task 008 现在都固定了唯一顺序：三个用户提供的 absolute paths → machine validator → 保存 evidence JSON → 仅展示指定 identity/header/verdict/coverage/aggregate 字段 → 停止并取得用户显式确认 → prerequisite-check v1 → dispatch。
- pending/rejected 与 validator failure 使用同一 zero-source-mutation `BLOCKED: representative_metrics_missing` 分支；Task 008/009 保持 `[ ]`，source/HEAD 必须等于 Phase 3 BASE。
- 全局说明已将 Task 008 明确列为 checker 顺序例外，task-local Steps/Verification 与之一致；通过后 implementer 仅消费 evidence JSON，不重读样本目录。

### I-2 — Closed

- Task 007 在 targeted test modules 后必须运行 fresh `.venv/bin/python -m pytest tests/ -q`。
- Verification 精确记录 `scope=full_suite`、reason=`shared/core PLAN generation and cross-platform author surfaces` 与 duration，同时承担 SPEC-VERIFY-001 shared/core escalation 和完整 Phase 2 acceptance。

### I-3 — Closed

- Task 002 `_cmd_run_execute_start` 和 Task 004 `_cmd_context_view` 的 Skeleton 都已使用当前 `cli.py::_validate_work_id(args.work_id)`，不再引用不存在的 `WorkId.parse`。
- WorkId 失败仍沿用现有 exit 2 映射，无需扩展 `models.py` 或新增第二个 parser API。

### I-4 — Closed

- Task 002 Files 已纳入 `tools/workflow_cli/agent_shortcuts.py` 与 `tests/test_agent_shortcuts.py`，验证也同时覆盖 CLI 与 shortcut。
- Steps 要求失败先行 regression 证明 closed strict `_cmd_execute` 经现有 internal `run-execute-start` 路径进入新 transaction，覆盖 strict default、human/JSON/exit 传播、active pointer 和 executing resume。
- `start_execution_transaction(base_path, work_id, profile)` 仍是唯一 transaction owner；shortcut 不加第二个 record/PLAN/marker/ledger/state owner。

### M-1 — Closed

- Task 001 现在区分“PLAN 恭有九个 contiguous anchors”与“`execution/progress.md` 恭有对应九个 `[ ]` rows”。
- Task 002 也明确将 `[x]` row 和 `review clean` complete marker 定位到 `execution/progress.md`，legacy fail-closed preflight 不再混淆两个对象。

## Full PLAN Audit

### Task layout, R19, and rollback

- PLAN 精确包含 `PLAN-TASK-001..009` 九个连续 task，四个 phase-level slices 按 `2 / 4 / 1 / 2` 展开。
- operation sequence 为 `create/modify | create/modify/create/modify | modify | create/modify`；当前 checkout 中 8 个 create paths 均不存在，所有 modify paths 均存在，与 `_check_plan_file_refs`/R19 一致。
- `Steps` 的第一条 semantic line 都是 canonical `Prerequisite:`；唯一 declared edges 为 001→002、003→004→005→006、008→009，没有 `Dependencies:` 字段或跨 Phase rollback edge。
- 每个 create task 交付可直接测试的 intermediate core/wrapper contract，每组末 task 承担集成/安装/平台一致性验收。Context wrapper 只在 Task 003 core 和 Task 004 internal CLI target 已可用后于 Task 005 创建并 smoke，没有 future-target wrapper。

### Bootstrap and prerequisite-version sequence

- Task 001/002 只使用决策完备的 legacy strict preflight；Task 002 reviewed complete 后、Task 003 dispatch 前运行唯一 self-host bootstrap command。
- Task 001/002 完整承接 `metrics-bootstrap.lock`、pinned run/execution fd、open unique temp fd、file/directory fsync、hard-link no-replace、open-fd/temp/final three-way inode/type identity、EEXIST、source/final race、abandoned temp、crash point、exact-header retry 和 Task 003+ block resume；没有 overwrite/cleanup foreign residue 路径。
- 当前 PLAN 的 Task 003–009 dispatch 均静态请求 semantics v1；Task 009 自身 dispatch 前仍用 v1，然后在同 task 中将 implementation 与五个 PLAN-author surfaces 升级为 v2。`1/1`、`1/2`、`2/1`、`2/2` 矩阵、旧 PLAN v1 兼容和新 PLAN 静态 v2 均有直接验证。

### Phase 3 source gate and profile/recovery

- Controller 不自动发现样本；exact command 只接受三个用户指定 absolute archived-run paths，保存 canonical JSON evidence 到已忽略的 `execution/` 路径。
- machine failure、人工 pending/rejection 都在 Task 008 role dispatch 和任何 Phase 3 source mutation 前停止；成功后 Task 008 只消费 evidence JSON，不重读跨仓库 sample directories。`SPEC-SAMPLE-003` 对每个 Sample identity/header/verdict/coverage/rules、measured aggregates、跨 mode 比较和 Token unavailable 的 report 契约由 Task 008 的直接 Spec Reference 与 evidence-consumption/report 验证继续约束，无人工重算或读 sample body 的分支。
- Task 008/009 分别交付 profile/ledger/eligibility/evidence core 与 shortcut/CLI/protocol adoption；strict default、fast two-step handshake/direct-confirm boundary、N+1 minimum、one-way escalation、BASE/marker chain、first actionable task、one-write final ledger migration、profile-specific final inputs 和旧 strict ledger 兼容都归属到具体 task 及测试。

### Scope, risk, Git, and final gates

- 14 个 `SPEC-*`、`SCOPE-IN-001..010` 和 12 个 mitigated `RISK-*` 全部有 task-level Trace/Risk Handling closure；现行 quality gate 也确认 full trace closure。
- 未发现 scope 内容被 defer/drop，未发现未锚定 deferral、新的 profile/依赖/schema 面或跨 Phase hidden rollback 依赖。
- 每 task 保留 full BASE、clean source tree、task-scoped commit、exact BASE→HEAD review diff 和禁止 `HEAD~1` 重建；当前分支上不允许 parallel writes、shared implementer、push、PR 或远程 mutation。
- shared/core/high-risk task 明确升级 full suite，final reviewer 与每次 final re-reviewer 始终运行 fresh `.venv/bin/python -m pytest tests/ -q`；final `Verdict: Approved`、checkbox 和 archive gate 保持不变。

## Findings

### Critical

无。

### Important

无。

### Minor

无。

## Ambiguity Conclusion

未发现 unresolved ambiguity / undecided point、不可执行路径、未经上游决策的实现选择或范围漂移。PLAN v4 可供 `r2p-continue` 完成 PLAN checkpoint。

# PLAN 强制独立评审 v3

Verdict: Changes Requested

## Review Scope

已完整审阅 `03-requirement-brief.md` v1、`04-risk-discovery.md` v3、`05-design.md` v8、`06-spec.md` v7 与 `07-plan.md` v3，并只读核对当前 R19 Files gate、`WorkId`/CLI 入口、wrapper bootstrap 和当前文件存在性。现行 deterministic PLAN quality gate 返回 `passed=True`；九个 task 的 create paths 均不存在，modify paths 均存在。然而，以下语义/执行契约缺口不在现有结构 gate 的检测范围内，会改变 Phase 0/2/3 的实际执行结果。

## Critical

无。

## Important

### I-1 — Phase 3 通过 machine validator 后缺少已决策的人工证据 checkpoint，且 Task 008 的 checker 顺序描述内部不一致

**证据**

- DESIGN v8 第 124 行和 SPEC v7 的 `SPEC-RESUME-006` Phase 3 条款固定了两个不同的门：controller 先保存 validator evidence，然后人工 checkpoint 再确认三份路径确为预期样本；只有两者都通过才可 dispatch Phase 3 implementer。
- PLAN `Execution Readiness` 只要求用户事前提供路径，并直接规定“Success 后 Task 008 只消费 evidence JSON”；Task 008 Steps/Verification 也没有 validator success 后的明确 stop/approve/reject checkpoint。这会把已批准的人工证据确认降成仅有 machine success。
- `Execution Readiness` 同时声称 Task 003–009 的 `Verification` “第一条”都是 `execution-prerequisite-check`，但 Task 008 Verification 第 1 条是 evidence/BASE 确认，checker 在第 2 条。SPEC 要求 Task 008 先完成 evidence gate，再在 dispatch 前运行 checker v1，因此全局说明与 task-local 顺序不能同时按字面成立。

**影响**

Controller 可在未经人工确认样本身份时进入 Phase 3；不同执行者也会对 Task 008 的 evidence/checker 先后顺序得出不同结论。

**具体修订建议**

在 `Execution Readiness` 和 Task 008 同时固定：`validator success -> 保存并展示 evidence identity/aggregate -> 人工显式确认三份路径是预期样本 -> prerequisite-check v1 -> dispatch`。未确认或拒绝时与 validator failure 相同：Task 008/009 保持 `[ ]`、source/HEAD 等于 Phase 3 BASE、不 dispatch。将全局“Verification 第一条”改成与 Task 008 例外一致的精确描述。

### I-2 — PLAN-TASK-007 明确绕过了 shared/core 的 mandatory full-suite trigger

**证据**

- `SPEC-VERIFY-001` 第 2 条要求 task 修改 shared/core path 时，task-level role 必须升级 full suite，并记录具体 reason。SPEC-GRANULARITY-004 还要求每个 Phase group 的最后一个 task 运行完整 Phase acceptance。
- Task 007 修改 shared PLAN generator `tools/workflow_cli/stage_templates.py` 及五个 PLAN-author surfaces，它本身就是 Phase 2 的唯一/验收 task。
- Task 007 Verification 第 3 条却规定“Keep task-level verification targeted unless directly affected tests fail”，把 shared/core 这个已经满足的强制升级条件排除了。这也与 `Execution Readiness` “task-level verification 遵循 SPEC-VERIFY-001”内部矛盾。

**影响**

Phase 2 可在仅运行三个 targeted test modules 后就记录 task complete，没有履行已批准的 shared/core escalation 和 Phase acceptance 契约。

**具体修订建议**

将 Task 007 Verification 改为在 targeted tests 后必须运行 fresh `.venv/bin/python -m pytest tests/ -q`，并记录 `scope=full_suite` 及精确 reason（例如 `shared/core PLAN generation and cross-platform author surfaces`）。

### I-3 — 两个 CLI Skeleton 调用了当前不存在、且任务 Files 未授权新增的 `WorkId.parse`

**证据**

- Task 002 `_cmd_run_execute_start` 与 Task 004 `_cmd_context_view` 都使用 `WorkId.parse(args.work_id)`。
- 当前 `tools/workflow_cli/models.py::WorkId` 只有 `__new__` 和 `generate`，没有 `parse`；现有 CLI 的统一入口是 `cli.py::_validate_work_id(raw)`，它用 `WorkId(raw)` 并把校验失败稳定映射为 exit 2。
- Task 002/004 都不包含 `models.py`，上游也没有决定新增第二个 WorkId 解析 API。

**影响**

按 Skeleton 实现会在运行时触发 `AttributeError`；若实现者临时新增 API，又会超出 Files 和既有 CLI error contract。

**具体修订建议**

将两处 Skeleton 统一改为现有 `_validate_work_id(args.work_id)`（或另一个明确保持 exit 2 契约的已有 helper），不引入新的 `WorkId.parse` 面。

### I-4 — Phase 0 的 approved PLAN handoff 要求 shortcut 接入/验证，但 Task 002 完全漏掉该 surface

**证据**

- DESIGN v8 `DES-EXEC-001` 固定 Phase 0 integrate task 把 core 接入“CLI、shortcut、execute surfaces、tests 与 docs”；SPEC v7 PLAN Handoff 第 323 行同样把 Task 002 定义为“modify CLI/shortcut/execute surfaces/tests/docs”。
- Task 002 Files/Steps 只包含 `cli.py`、execute templates、CLI/docs/install tests 和 README，没有 `tools/workflow_cli/agent_shortcuts.py` 或 `tests/test_agent_shortcuts.py`，也没有一条验证真实 `r2p-execute` shortcut 继续通过 strict-default `run-execute-start` 路径进入新 transaction/metrics 行为。
- 当前 shortcut 是用户实际调用面；只验证 internal CLI 不足以证明 Phase 0 已在 shortcut 上可达。

**影响**

Task 002 无法证明它完整承接了已批准的 Phase 0 integration/acceptance surface；若执行中才发现 shortcut 需要修改，将超出 task Files，并触发 scope/escalation。

**具体修订建议**

在 Task 002 的 Files/Steps/Verification 中加入 `tools/workflow_cli/agent_shortcuts.py` 和 `tests/test_agent_shortcuts.py`，至少以失败先行测试覆盖 strict-default shortcut 的 start transaction、human/JSON/exit 传播与 resume；若确认实现无需修改 shortcut，PLAN 也必须显式记录“existing shortcut unchanged, integration is through its existing internal CLI call”并把相应 shortcut regression test 纳入 Task 002 Files/Verification，以闭合上游 handoff。

## Minor

### M-1 — legacy preflight 把 PLAN anchor 与 progress checkbox 写成了同一个对象

Task 001 写“PLAN has exactly nine unchecked anchors”，而 `07-plan.md` 里是九个 `PLAN-TASK-*` headings，执行 checkbox 位于 `execution/progress.md`。建议精确改为“PLAN 恭有九个连续 anchors，progress 恭有对应的九个 `[ ]` rows”，Task 002 也明确 `[x]` row 和 complete marker 均在 progress ledger。这是 legacy fail-closed preflight，不应依赖执行者自行解释。

## Confirmed Complete Areas

- PLAN 精确包含 9 个 task，Phase 分组为 `2 / 4 / 1 / 2`；declared edges 仅为 001→002、003→004→005→006、008→009，组首/Task 007 使用 `Prerequisite: none`。
- R19 file gate 与当前 checkout 匹配：8 个 create paths 均缺失，全部 modify paths 存在；context wrapper 仅在 Task 003 core 和 Task 004 internal CLI 已可用后于 Task 005 创建。
- self-host bootstrap 命令、Task 002→003 cutover、lock/open-temp-fd/fsync/hard-link-no-replace/three-way inode identity/EEXIST/race/crash/retry-resume 测试矩阵已被 Task 001/002 可执行地承接。
- Task 003–009 在当前 PLAN 静态使用 checker v1；Task 009 在自身 dispatch 前仍用 v1，之后将 implementation 和五个 PLAN-author surfaces 同 task 升级为 v2，并保留旧 PLAN v1 兼容矩阵。
- 14 个 `SPEC-*`、`SCOPE-IN-001..010` 与 12 个 mitigated `RISK-*` 都在 Trace/Risk Handling 中有具体 handling task；未发现需求内容被 defer/drop，也没有未锚定 scope deferral。
- Phase 3 validator 的三个 user-specified absolute paths、canonical duplicate/representativeness 判定、evidence-only consumption、failure 时 Task 008/009 不勾选且 source/HEAD 等于 Phase 3 BASE 都已明确；I-1 仅是缺失其后已决策的人工 checkpoint 与顺序对齐。
- 每 task 的 full BASE、clean tree、task-scoped commit、exact BASE→HEAD diff、禁止 `HEAD~1`、final reviewer/re-reviewer fresh full suite、Approved verdict/archive gate 以及无 push/PR/remote mutation 边界均保留。

## Ambiguity Conclusion

仍存在 unresolved ambiguity / undecided execution point：I-1 的 machine/human evidence gate 与 Task 008 checker 顺序、I-2 的 Phase 2 full-suite trigger、I-3 的 WorkId parser 调用、I-4 的 Phase 0 shortcut acceptance surface。因此 PLAN v3 不可批准执行。

## Approval Condition

仅需在 PLAN 中做决定完备的局部修订：补齐 Phase 3 人工 evidence checkpoint/顺序，为 Task 007 加上 mandatory full suite，修正两处 WorkId 调用，并闭合 Task 002 shortcut 验收面；修订后再进行强制评审。

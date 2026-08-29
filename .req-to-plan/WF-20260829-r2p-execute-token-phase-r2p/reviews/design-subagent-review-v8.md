# DESIGN 最终聚焦强制独立评审 v8

Verdict: Approved

## Review Scope

聚焦复审 `05-design.md` v8，并逐项核对 `design-subagent-review-v7.md` 的 N-I1-R1、N-I2-R1、N-I3；同时检查修订后的 `2 / 4 / 1 / 2` 九任务布局、Task002→Task003 self-host bootstrap 切换点及 SPEC handoff。未修改阶段产物或源码。

## Finding Closure

### N-I1-R1 — Closed

- DESIGN 第 68 行已将 bootstrap 明确分为两个互斥分支。
- metrics 不存在的首次创建分支额外要求 Task003 未开始且 HEAD 等于 Task002 reviewed-complete head，然后才执行 no-clobber 原子创建。
- metrics 已存在的 retry/resume 分支明确不再要求 Task003 未开始；它验证 exact canonical header，并只接受无 block，或从 Task003 开始、与 progress/task order 一致、sequence 连续且结构完整的 blocks，随后从下一 sequence append。
- Task001/002 block、partial/乱序、unsafe/foreign/header mismatch 继续 conflict 且不覆盖、不清理。
- canonical `bootstrap_gap: execution_start_through_task_002_reviewed_complete` 与 Task002→Task003 instrumentation 边界一致。

首次创建、创建成功但返回前崩溃、以及 Task003+ 已记录后 controller 重启均有唯一结果，不再存在条件互斥或 recovery ambiguity。

### N-I2-R1 — Closed

- DESIGN 第 102 行把 canonical Steps grammar 改为 profile-neutral 的 `Prerequisite: none` 或 `Prerequisite: PLAN-TASK-NNN`，且明确禁止新增 `Dependencies:` field。
- 第 104 行固定 satisfaction matrix：strict 要求前驱 reviewed-complete；fast 接受合法 implemented marker 或 reviewed-complete；fast→strict recovery 先按 marker chain 补齐 task review，再依 strict 条件继续。
- `Prerequisite: none` 的可执行前置检查也已固定为 Execution BASE 存在且当前 task 是编号最小的未实现/未完成 task。

该矩阵与 fast 的 implemented-but-unreviewed、next-task selector、单向 strict escalation 和最终批量 reviewed-complete 契约一致；多任务 fast run 不再被 prerequisite 阻断，也没有新增 PLAN schema 字段。

### N-I3 — Closed

- declared dependency 只存在于组内：`001→002`、`003→004→005→006`、`008→009`；Task007 和各 Phase 首 task 均为 `Prerequisite: none`。
- 跨 Phase 关系只由 PLAN 编号、最低未完成任务选择器和上一 Phase acceptance 控制，明确不进入 rollback dependency graph。
- rollback dependents 仅由同组 canonical prerequisite 反向推导，因此单 task 需先回滚组内 dependents，Phase group 可整体反向拓扑回滚而不触及其他 Phase。

该表述与 phase-level cohesive slice、Phase-local rollback、R19 operation-homogeneous group 以及“不修改 PLAN schema/gate”的上游约束一致。

## Nine-task Consistency Check

- Phase 0：PLAN-TASK-001 metrics core create → PLAN-TASK-002 integration modify。
- Phase 1：PLAN-TASK-003 context core create → 004 internal CLI modify → 005 wrapper create/smoke → 006 surfaces adoption modify。
- Phase 2：PLAN-TASK-007 continue-surface modify，独立 Phase acceptance。
- Phase 3：PLAN-TASK-008 profile core create → 009 integration modify。
- Self-host bootstrap 固定在 Task002 reviewer-clean 后、Task003 implementer dispatch 前；Phase 3 sample preflight 固定在 Task008 dispatch/source mutation 前。

编号、create/modify 顺序、wrapper bootstrap target、Phase acceptance 与 rollback topology 无内部矛盾。

## Critical

无。

## Important

无。

## Minor

无。

## Ambiguity Conclusion

未发现 unresolved ambiguity / undecided point；未引入新的未锚定 deferral、范围漂移、schema/gate 变化或安全边界弱化。DESIGN v8 可进入后续 SPEC 修订。

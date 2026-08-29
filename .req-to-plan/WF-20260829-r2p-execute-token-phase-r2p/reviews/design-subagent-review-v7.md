# DESIGN 聚焦强制独立评审 v7

Verdict: Changes Requested

## Review Scope

聚焦复审 `05-design.md` v7，并逐项对照 `design-subagent-review-v6.md` 的 N-I1、N-I2；同时核对固定九任务 `2 / 4 / 1 / 2` 编号链、Task002→Task003 self-host bootstrap 切换点、strict/fast task-state 契约及回滚声明。未修改阶段产物或源码。

v7 已固定 canonical `bootstrap_gap`、exact-header no-clobber 判定、后续 block 完整性条件，也已明确 dependency 只能编码在既有 `Steps` 第一条且禁止 `Dependencies:` field。但新增的前置条件与既有 fast/rollback 设计仍有三处会改变实现行为的矛盾。

## Critical

无。

## Important

### N-I1-R1 — bootstrap 的全局 `Task 003 尚未开始` 前置条件与 appended-block resume 分支互斥

**证据**

- DESIGN 第 68 行先无条件规定命令验证“Task 003 尚未开始”。
- 同一行随后规定：existing exact header 可以包含“从 Task 003 开始、sequence 连续且结构完整的 blocks”，并从下一 sequence 继续 append。
- 一旦出现合法 Task 003 role block，Task 003 就已经开始；因此重试会先被前一个条件拒绝，永远到不了后一个 intended resume 分支。

**具体修订要求**

把前置条件按 metrics 状态分支固定：

1. metrics 不存在的首次 bootstrap：Task 003 必须尚未开始，随后 no-clobber 创建 exact header。
2. metrics 已存在的 retry/resume：不得再要求 Task 003 未开始；必须验证 exact header，并允许只含从 Task 003 起、与 progress/task order 一致的连续完整 blocks，从下一 sequence 继续。
3. Task 001/002 block、partial/乱序 block、header mismatch、unsafe/foreign residue 继续 conflict 且零覆盖/清理。

canonical `bootstrap_gap: execution_start_through_task_002_reviewed_complete` 本身已精确闭合，无需更改。

### N-I2-R1 — canonical prerequisite 强制 `reviewed complete`，使多任务 fast profile 无法前进

**证据**

- DESIGN 第 102 行把所有 PLAN 的直接前驱语法固定为 `Prerequisite: PLAN-TASK-NNN reviewed complete`，并要求 `Verification` 第一项确认前驱恰有一个 reviewed-complete record。
- DESIGN 第 116–118 行同时规定 fast implementer 完成 Task N 后保持 `[ ]`、只写 implemented marker；直到 final primary review 才批量 reviewed-complete。fast resume/next-task selector 明确应跳过已有合法 implemented marker并进入下一任务。
- 因而任何含两个以上 task 的 fast run 在 Task 1 后都会失败：Task 1 合法地 implemented-but-unreviewed，但 Task 2 的 canonical prerequisite/Verification 又要求它已经 reviewed complete。

**具体修订要求**

依赖语法必须保持 profile-neutral，状态判定交给既有 effective-profile/task-state parser。例如把 Steps 第一条固定为 `Prerequisite: PLAN-TASK-NNN`，并规定 Verification：strict 要求前驱 reviewed-complete；fast 要求前驱为合法 implemented marker 或 reviewed-complete；升级后的 strict recovery 按既定 marker-chain/review 补偿规则判定。`Prerequisite: none` 仍可保留。不得新增 PLAN field。

### N-I3 — 001→009 单一 declared-dependency 链与 Phase 独立回滚声明不一致

**证据**

- DESIGN 第 102 行明确九个 task 是从 001 到 009 的“单一直接前驱链”，且 rollback dependents 由该 prerequisite 反向推导。
- DESIGN 第 12、102、142 行又声明 Phase group 可独立反向拓扑回滚、不触及或不要求回滚其他 Phase。
- 在单链中，Task003 是 Task002 的 declared dependent，Task007/008 等继续传递依赖。若 Phase 1–3 已落地，回滚 Phase 0 的 001/002 必须先回滚 003–009；否则留下未满足 prerequisite 的 dependents。这与“不触及其他 Phase”无法同时成立。

**具体修订要求**

明确选择并统一全文：

- 若 prerequisite 只表达 group 内实现依赖，则只在 `001→002`、`003→004→005→006`、`008→009` 内建链；Phase 首 task 的顺序由 PLAN 编号/最低未完成 task 与 Phase acceptance 控制，rollback 可保持 Phase-local。
- 若九任务确实是跨 Phase dependency chain，则删除“任一 Phase 可独立回滚且不触及其他 Phase”的声明，并回到 requirement owner 确认这是否允许，因为当前 SCOPE/Acceptance 要求四个 Phase 可独立回滚。

不能同时保留单一 dependency chain 与 Phase-local rollback。

## Minor

无。

## v6 Finding Closure

| v6 finding | v7 result | Conclusion |
|---|---|---|
| N-I1 canonical gap / retry / appended-block resume | **部分闭合** | canonical value、gap 覆盖、exact header、mismatch fail-closed 均已定义；但首次 bootstrap 与 existing-header resume 的 Task003 前置条件未分支，见 N-I1-R1。 |
| N-I2 Steps-only dependency / Verification / no new field | **部分闭合** | `Steps` 第一条 grammar、Verification first item、禁止 `Dependencies:` field 均已明确；但 `reviewed complete` 状态写死与 fast implemented marker 冲突，见 N-I2-R1。 |

## Nine-task Chain Check

- 数量与编号算术一致：Phase 0 = 001–002，Phase 1 = 003–006，Phase 2 = 007，Phase 3 = 008–009。
- Task002 integration 后、Task003 dispatch 前执行 self-host bootstrap 的切换点正确；首个应记录 role 是 Task003 implementer。
- context wrapper 顺序正确：core create → internal CLI modify → wrapper create/smoke → surfaces adoption。
- Phase 3 validator 仍在 Task008 dispatch/source mutation 前由 Phase 0 已落地命令执行。
- 但单一跨 Phase declared-dependency chain 的 rollback 语义有 N-I3，不能判定整体无内部矛盾。

## Ambiguity Conclusion

仍存在 unresolved ambiguity / undecided point：bootstrap 首次创建与 appended-block resume 的条件分支、profile-aware prerequisite satisfaction，以及跨 Phase chain 与独立回滚二选一。未发现新的未锚定 deferral、范围外 profile、远程 mutation 或安全边界弱化。

## Approval Condition

按以上三项统一 DESIGN 后再做聚焦复审；canonical gap、Steps-only/no-new-field 决策和 `2 / 4 / 1 / 2` task 数量本身可保留。

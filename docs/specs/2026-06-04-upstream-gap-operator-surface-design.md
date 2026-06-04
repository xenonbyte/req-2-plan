# 设计 Spec：上游缺口的 operator 操作面（in-place gap routing）

- 日期：2026-06-04
- 状态：DRAFT（待用户评审 → 转 writing-plans）
- 关联：`docs/req-to-plan-design.md` §6「变更传播 · 当前实现边界」

## 1. 背景与问题

`req-to-plan` 的状态模型已经具备上游缺口路由的全部结构：`RunStatus.UPSTREAM_GAP_ROUTING`、
`OpenRoute`、`StaleArtifact`，以及 state helper `add_open_route` / `close_route` /
`record_stale_artifact` 和 `ArtifactManager.mark_stale`。`ALLOWED_TRANSITIONS` 也允许从几乎
任何工作态转入/转出 `UPSTREAM_GAP_ROUTING`。

但这些能力**没有被任何 CLI 命令或 `r2p-*` shortcut 暴露**：`add_open_route` /
`close_route` / `record_stale_artifact` / `mark_stale` 在 `cli.py` 与 `agent_shortcuts.py`
中零调用；`checkpoint-decide --decision` 只接受 `approved` / `changes_requested`。

后果（见设计 SSOT §6）：一个**已离开 owner 阶段、但尚未关闭**的 open run，若发现需要回到某个
上游阶段修复，公开 CLI **没有任何 operator workflow** 把它带回去。`run-reopen` 只接受
`CLOSED_AT_PLAN_CHECKPOINT` 的 run（会复制成新的 `-rN` run）。

本 spec 设计这条缺失的操作面：让 open run 能**原地**路由回 owner 阶段、安全地使下游失效、
重派生并闭合。

## 2. 目标 / 非目标

### 目标
- G1：open run 能从当前阶段把一个上游缺口路由回 owner 阶段，并保持状态一致（绝不半路由）。
- G2：级联满足设计 SSOT §6 的两条铁律——**不静默携带过时下游**、**每个被触及层重新过门**。
- G3：严守现有 CLI/agent 边界——CLI 只做结构性状态记账；owner 选择、required-action、所有
  artifact 正文由 agent 提供。
- G4：路由生命周期、失效进度在 `status-run` / `status-next` 可观测。
- G5：暴露为 `r2p-gap-open` / `r2p-gap-resolve` 两个 shortcut（含三平台安装模板）。

### 非目标
- 不为已关闭（`CLOSED_AT_PLAN_CHECKPOINT`）run 新增路径——那是 `run-reopen` 的职责，保持不变。
- 不自动生成任何 artifact 内容；CLI 不写正文。
- 不改 `ALLOWED_TRANSITIONS`、不改 `OpenRoute` / `StaleArtifact` 数据结构（现状已够用）。
- 不改既有 per-stage 命令（stage-produce/update/ready、gate-*、review-checkpoint、
  checkpoint-decide、stage-advance）的行为——本设计完全复用它们。
- 不实现自动语义判定（哪条反馈属于哪层仍由 agent/人决定）。

## 3. 现状与复用

| 现有 | 复用方式 |
|---|---|
| `RunStatus.UPSTREAM_GAP_ROUTING` + 转移表 | 作为 gap-open 的合法中转态（见 §4.1 D1） |
| `add_open_route` / `close_route`（state.py） | 由新命令调用 |
| `record_stale_artifact`（state.py）/ `ArtifactManager.mark_stale`（artifact.py） | 由 gap-open 调用 |
| `RunRecord.current_stage / open_routes / stale_artifacts` | 由新命令读写 |
| **checkpoint-decide 的 open-route 护栏（cli.py:1328）** | 阻止"route 未闭时批准 owner"——见 §5 死锁分析 |
| **stage-advance 的 open-route 护栏（cli.py:1453）** | 阻止"route 未闭时前进" |
| stage-advance 要求 `active_artifact.status=="approved"` + 版本匹配 checkpoint | 作为下游"必须重做"的强制点 |
| 现有前进流命令 | owner 重做与下游重派生**全部复用**，零新机器 |

`STAGE_ORDER = [raw_requirement, requirement_brief, risk_discovery, design, spec, plan]`。

## 4. 命令契约

两个新 CLI 命令（`tools/workflow_cli/cli.py`），各只做结构性状态操作。

### 4.1 `gap-open`

```
workflow gap-open --work-id W --owner-stage S --required-action "<text>" [--confirm]
```

前置校验（任一失败即报错，括注退出码）：
- run 存在（否则 7 not-found）；
- run 未关闭（status ≠ `CLOSED_AT_PLAN_CHECKPOINT`，否则 6 冲突）；
- `S` 是合法 stage（否则 2 cli-err）且**严格在 `current_stage` 上游**（`STAGE_ORDER` 下标更小，否则 6）；
- 当前 status 能合法转到 `UPSTREAM_GAP_ROUTING`（否则 6，提示当前态不可路由；`NEXT_STAGE` 这种瞬态需先 gate-entry）；
- 不存在 owner_stage 相同且 `status=="open"` 的未闭 route（否则 6）；
- `--required-action` 非空（否则 2）。

副作用（单次保存，事务性——任一中途失败则不落盘）：
1. 生成 run 内唯一 `route_id`（如 `R-<seq>`，seq = 现有 route 数 +1）；
   `add_open_route(record, route_id, from_stage=current_stage, owner_stage=S, required_action)`。
2. 对每个下游阶段 `D ∈ (S, current_stage]`（`STAGE_ORDER` 中 S 之后、到 current_stage 为止，
   且存在 active_artifact）：
   - `record_stale_artifact(artifact=<D 文件名>, reason="upstream gap at "+S.value,
     replaced_by="(pending re-derivation)", required_action=<route_id>)`；
   - `ArtifactManager.mark_stale(stage=D, ...)`（写文件头 status=stale）；
   - 把 D 的 `active_artifact.status` 置 `"stale"`；
   - 从 `record.approved_checkpoints` 移除 stage==D 的全部条目。
3. `record.current_stage = S`。
4. 状态：经**两个合法跳**落到 `ACTIVE_STAGE_DRAFT`——`<当前态> → UPSTREAM_GAP_ROUTING → ACTIVE_STAGE_DRAFT`
   （`update_run_status` 逐跳校验；两跳对所有合法起点均成立，含 `CHECKPOINT_APPROVED` 这一只能先进
   `UPSTREAM_GAP_ROUTING` 的起点）。**净落点是 `ACTIVE_STAGE_DRAFT`**，使 owner 重做可直接复用
   既有 per-stage 流。
5. `update_resume_context(next_operation="stage-update", active_item=S.value,
   reason="repair owner for "+route_id)`。

输出：`{route_id, owner_stage, from_stage, staled_stages: [...]}`，message 含需重走的前进路径。

> **决策 D1（gap 的操作性标记是 OpenRoute，不是 run 状态）**：本设计让 gap-open 净落在
> `ACTIVE_STAGE_DRAFT` 而非停在 `UPSTREAM_GAP_ROUTING`。原因：`stage-ready`（cli.py:998）只接受
> `{ACTIVE_STAGE_DRAFT, QUALITY_GATE_FAILED}` 起始态，若让 run 停在 `UPSTREAM_GAP_ROUTING`，owner
> 重做会卡在 stage-ready，必须改既有命令（扩大爆炸半径）。改为净落 `ACTIVE_STAGE_DRAFT` 后，owner
> 重做零改动复用既有流；"本 run 处于缺口路由"由 `OpenRoute(status=open)` 表达——它已被
> checkpoint-decide:1328 与 stage-advance:1453 两个护栏认账，且在 `status-run.open_routes` 可见。
> 备选（未采纳）：扩展 stage-ready 接受 `UPSTREAM_GAP_ROUTING` 并停在该态，状态语义更显式，但要动既有命令。

### 4.2 `gap-resolve`

```
workflow gap-resolve --work-id W --route-id R [--confirm]
```

前置校验：
- run 存在（否则 7）；
- 存在 `route_id==R` 且 `status=="open"` 的 route（否则 7 not-found）；
- **owner 阶段 active_artifact 状态为 `ready`**（否则 6 冲突，提示"owner 尚未重做到 ready"）。
  依据：gap-open 时 owner active 必为 `approved`（能离开 owner 阶段就证明它曾被批准），唯一能把它变成
  `ready` 的途径就是 gap-open 后对 owner 跑 `stage-update`→`stage-ready`。故 `ready` 即"owner 已重做并
  重新通过其 Quality Gate"的充分证明，无需额外存版本基线。

副作用：
1. `close_route(record, route_id)`（matching route status → `"repaired"`）。
2. **不改 run 状态**（保持 owner 重做到 ready 时的 `READY_FOR_CHECKPOINT_REVIEW`）。
3. `update_resume_context(next_operation="review-checkpoint", active_item=owner_stage.value)`。

输出：`{route_id, status:"repaired", owner_stage, resume_from: owner_stage}`。

> **为什么 resolve 发生在 owner 批准之前（死锁规避）**：checkpoint-decide 的批准路径有 open-route
> 护栏（cli.py:1328），route 开着时**无法批准 owner**；而 close_route 需要先发生。若把 resolve 前置
> 设成"owner 已批准"，就互锁了。故时序是：owner 重做到 `ready` → `gap-resolve` 闭 route → 常规
> `review-checkpoint`→`checkpoint-decide approved`（route 已闭，护栏放行）→ `stage-advance` → 重派生下游。
> route 的职责是"强制回到 owner 并重做"；一旦 owner 重做到 ready 即达成，可闭合；owner 的最终批准由
> 常规 checkpoint 把关，下游重做由"降级的 active 状态 + 移除的 checkpoint"在前进流里强制。

## 5. 安全不变量（承重点）

stage-advance 放行条件是 `active_artifact.status=="approved"` 且有 `(stage,artifact,version)`
匹配的 approved checkpoint。**若 gap-open 只标 stale 不降级下游 active 状态**，重走到下游时它仍
是"approved v_old + 匹配 checkpoint"，会被 stage-advance **直接放行、跳过重派生**——违反 §6。

因此 gap-open **必须**对每个下游：把 active_artifact.status 置 `"stale"`（合法值之一）
**且**移除其 approved checkpoint。二者叠加确保前进流无法跳过任何过时下游，每个下游都被强制
重新产出 → 重新过门 → 重新批准。**这条不变量是整套级联正确性的命门，必须有专门测试守护。**

## 6. 端到端流程（示例：owner=design，run 当时在 plan、plan 已批准）

```
gap-open --owner-stage design --required-action "fixed-window burst flaw"
  ├─ open route R-1 (from=plan, owner=design)
  ├─ spec, plan: mark stale + active.status=stale + 移除其 approved checkpoint
  ├─ current_stage = design
  └─ status: (CHECKPOINT_APPROVED→UPSTREAM_GAP_ROUTING→) ACTIVE_STAGE_DRAFT
        │  重修 DESIGN（复用既有流）：
        │  stage-update(design v2) → stage-ready(design v2 → READY_FOR_CHECKPOINT_REVIEW)
        │  ※ 此刻 checkpoint-decide 与 stage-advance 都被 open-route 护栏挡住 ✓
        │
gap-resolve --route-id R-1   （校验 design active==ready → close route）
        │
   review-checkpoint → checkpoint-decide approved(--confirm)  （route 已闭，护栏放行）
        │
   stage-advance → spec   （outstanding_stale={spec,plan}，active=stale 强制重做）
   stage-update(spec v2) → stage-ready → review-checkpoint → checkpoint-decide approved
   stage-advance → plan
   stage-update(plan v2) → … → checkpoint-decide approved
        │
   回到 plan 检查点；outstanding_stale 归零；级联闭合
```

## 7. 状态可见性

### 7.1 `status-run`（`_cmd_status_run`）
- `open_routes`：从"裸 route_id 列表"升级为对象数组
  `{route_id, from_stage, owner_stage, required_action, status}`。
- 新增 `stale_artifacts`：`{artifact, reason, replaced_by, required_action}` 数组。
- 新增派生字段 `outstanding_stale`：那些对应阶段 active_artifact 仍为 `"stale"` 的阶段名列表
  （= 还剩哪些下游要重派生）。

### 7.2 `status-next` / `resume_context`
- gap-open 后：`next_allowed_operation="stage-update"`、`active_item=owner`、reason 指向 route。
- gap-resolve 后：`next_allowed_operation="review-checkpoint"`、`active_item=owner`。
- 全程把 operator/agent 牵引过"重做 owner → resolve → 批准 owner → 逐级重派生"。

## 8. `r2p-*` shortcut 与安装模板

`tools/workflow_cli/agent_shortcuts.py` 新增两个子命令（仿 `reopen`→`run-reopen` 委托模式）：
- `r2p-gap-open --work-id --owner-stage --required-action [--confirm]` → CLI `gap-open`。
- `r2p-gap-resolve --work-id --route-id [--confirm]` → CLI `gap-resolve`。

安装模板各加两份，仿现有 `r2p-reopen`：
- `agent_templates/claude/commands/r2p-gap-open.md` / `r2p-gap-resolve.md`
- `agent_templates/codex/skills/r2p-gap-open/SKILL.md` / `r2p-gap-resolve/SKILL.md`
- `agent_templates/gemini/commands/r2p-gap-open.toml` / `r2p-gap-resolve.toml`

`install.py` 的模板纳入方式（目录扫描 vs 显式清单）实现期确认（见 O2）。

## 9. stale 审计策略（已决）

`StaleArtifact` 条目**保留作审计**，不删。"还要不要重派生"由 `active_artifact.status=="stale"`
这个操作性信号判定（`outstanding_stale`）。下游某阶段重新批准时其 active 自然回 `approved`，
即从 `outstanding_stale` 消失。好处：零额外记账、级联进度可观测、审计留痕。

## 10. 测试矩阵（TDD：先写测试 red→green；602 基线必须保持全绿；`tempfile`+`base_path` 隔离）

| 层 | 用例 |
|---|---|
| state/models | gap-open：开 route + 下游标 stale + active 降级 `"stale"` + 移除下游 approved checkpoint + `current_stage→owner` + 净状态 `ACTIVE_STAGE_DRAFT`（含 `CHECKPOINT_APPROVED` 起点的两跳合法）；gap-resolve：仅当 owner active==`ready` 才 `close_route→repaired` |
| 死锁规避 | route 开着时 checkpoint-decide approved 被拒（既有护栏，断言 gap-open 后成立）；gap-resolve 闭 route 后 owner 可被批准 |
| 安全护栏 | stage-advance 在 route 未闭时拒绝；stage-advance 拒绝跳过 `"stale"` 下游 active（**第 5 节不变量的专守测试**）|
| CLI 校验 | owner 非上游 / owner==current / run 已关闭 / 重复 open route / 当前态不可路由 → 6；run 不存在 / route_id 不存在 → 7；非法 stage / 空 required-action → 2；gap-resolve owner 未到 ready → 6 |
| 集成（端到端）| §6 全级联：gap-open→重修 design→gap-resolve→批准 design→重派生 spec+plan→回到 plan，状态一致、`outstanding_stale` 归零 |
| status | status-run 输出富化 open_routes + stale_artifacts + outstanding_stale；status-next 全程牵引 |
| shortcut | `r2p-gap-open`/`r2p-gap-resolve` 正确委托（base_path 隔离）|
| 安装 | 两个新 shortcut 模板被 install 写入；uninstall 仅移除清单内路径 |

## 11. 验收标准

- AC1：对处于 plan、design/spec/plan 已批准的 open run，`gap-open --owner-stage design`
  使 spec/plan 失效（active=stale、approved checkpoint 移除）、current_stage=design、
  净状态 ACTIVE_STAGE_DRAFT，且 checkpoint-decide approved 与 stage-advance 均被 open-route 挡住。
- AC2：owner（design）尚未重做到 `ready` 时 `gap-resolve` 拒绝（退出码 6）。
- AC3：design 重做到 ready 后 `gap-resolve` 成功（route→repaired），随后可常规批准 design 并逐级
  重派生 spec、plan，其间 stage-advance 拒绝跳过任一 stale 下游。
- AC4：全程 `status-run.outstanding_stale` 正确反映剩余待重派生阶段，闭合后归零。
- AC5：`r2p-gap-open` / `r2p-gap-resolve` 委托到 CLI 行为一致。
- AC6：全套测试通过，且原 602 基线不回归。

## 12. 回滚 / 兼容

- 纯新增命令 + 现有命令的输出字段扩展（status-run 加字段，向后兼容 JSON 消费方）。不改数据结构、
  不改转移表、不改既有命令行为。回滚 = 移除两个命令 + 还原 status-run 输出 + 删除模板，无数据迁移。
- `run.md` 序列化已含 open_routes / stale_artifacts（state.py 读写），无 schema 变更。

## 13. 决策与待实现期确认

已决：
- D1：gap 的操作性标记是 `OpenRoute`，gap-open 净落 `ACTIVE_STAGE_DRAFT`（见 §4.1）。
- D2：gap-resolve 发生在 owner 批准之前，前置=owner active `ready`（见 §4.2 死锁规避）。
- D3：stale 条目留作审计，`outstanding_stale` 由 active 状态派生（见 §9）。

待实现期确认（非阻塞）：
- O1：`stage-update` 在 `ACTIVE_STAGE_DRAFT` 起点对一个曾 `approved` 的 owner active 正常 bump 版本、
  置 draft（已读 cli.py:908-991，预期成立；实现期以测试坐实）。
- O2：`install.py` 模板纳入是目录扫描还是显式清单（决定是否需登记新模板）。
- O3：route_id 生成式（`R-<seq>`）与 `run.md` 现有序列化格式的兼容写法。

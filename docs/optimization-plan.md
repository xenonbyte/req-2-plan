# req-to-plan 优化与问题处理方案

> 状态：待批准 · 作者：审查 + 设计 · 适用版本：v0.4.5 之后（下一个 minor）
> 本文是 `/think` 产出的决策完备方案，经批准后可直接交付实现。
> 约束（用户既定）：
> 1. 不做任何老版本 / 老数据兼容，状态机直接硬切；
> 2. 不过度优化、不过度防卫，避免项目臃肿、脆弱。

---

## 0. 结论速览

| 项 | 类型 | 真实性核查结论 | 处理 |
|---|---|---|---|
| Task 验收标准 | 增强 | Verification 字段已是任务级验收契约，但占位符可漏过 gate | **做**：强化 Verification 语义 + 占位符 gate（不加新字段） |
| DESIGN/SPEC/PLAN 无模糊点 | 增强 | 多数已在 gate（R2.2/R2.3a/R12），marker 偏窄、语义模糊未显式 | **做**：gate 精准补 3 个 marker + checkpoint 加"无未决歧义"判定 |
| plan 执行技能 | 新功能 | 当前仅产出 PLAN，无执行环节 | **做**：自包含复刻 SDD，新增 `r2p-execute` |
| 需求归档 | 新功能 | 无归档机制，CLOSED 需求在工作区堆积 | **做**：`archive/` + `.req-to-plan/.gitignore` + 自动/手动归档 |
| PLAN 完成自动提交 | 新功能 | 需求目录文档不入库，无沉淀 | **做**：run-close 后无条件路径限定提交 `.req-to-plan/<id>/`（尽力而为 + 三守卫） |
| P1 fsync 缺失 | 问题 | 真实，但截断已被原子替换排除，durability 是刻意非目标 | **不改**（含一行注释澄清） |
| P1 manifest 固定 `.tmp` | 问题 | 真实但低危；整个 install 模块统一是“校验后普通写”，manifest 反而最受保护 | **不改**：单独改 manifest 反而制造模块内不一致 |
| P1 `_prepare_input_file` 普通写 | 问题 | **真实缺口**，与既有 symlink 加固方向不一致 | **做**：拒绝 symlink + `atomic_write_text` |
| P2 run_dir 自身为 symlink | 问题 | 真实，但超出 r2p 威胁模型（你自己的工作区） | **不改** |
| P2 reopen 用 `cp.artifact` 非 map | 问题 | 非 bug：已验证 `cp.artifact` 恒等于 map 名（不变量） | **不改**：无行为差异的改动属投机变更，仅在码内注明不变量 |
| README | 文档 | 双语 + 一致性测试约束 | **做**：随 Phase 2/3 同步更新 |

实现切成 3 个**可独立合并**的阶段（见 §6）。

---

## 1. 优化原则落地（贯穿全文）

- **硬切**：新增 `RunStatus.EXECUTING / ARCHIVED` 与转移，不为旧 `run.md` 写迁移代码。状态解析是 `RunStatus(<str>)`（`state.py:462`），**遇未知值会 `ValueError`**——所以这里不是“容忍未知”，而是**新状态只向前可达**：旧 run.md 里只可能是既有合法状态（如 `closed_at_plan_checkpoint`），照常解析，新值只会由本期新代码写入，故无需迁移、也不会撞解析。
- **不过度防卫**：P1-fsync、P2-run_dir-symlink 明确**不做**——它们要么是刻意非目标，要么超出威胁模型，强行加只会让主流程变重、变脆。
- **CLI / Agent 分工不变**：CLI 只管状态机、结构校验、归档移动、账本骨架（PLAN-TASK ID + 勾选框，属结构而非语义）；执行循环的语义编排（派发子代理、TDD、评审）全部落在技能文档里。沿用现有不变量 “CLI never generates artifact text”。

---

## 2. Plan 强化：Task 验收标准（决策：强化 Verification 语义）

### 2.1 核查结论
当前 `PLAN-TASK` 已有 7 个字段：`Spec References / Change Type / TDD Applicable / Files / Skeleton / Steps / Verification`（`tools/workflow_cli/stage_schema.py:6`）。

- `Verification` 在本模型里**本就是任务级验收契约**（“怎么判定这个 Task 做完了”），`Spec References` 提供需求对照，`TDD Applicable` 提供测试先行约束。再加一个独立 `Acceptance` 字段与 `Verification` 语义高度重叠，且要改 schema / gate / 模板 / trace / 文档，属于“为模型加字段”的臃肿。
- **真实缺口**：`gates.py:_check_plan_task_fields`（`tools/workflow_cli/gates.py:520`）只校验 `Verification` **非空**；模板播种的是 `Verification: <!-- fill in -->`（`stage_templates.py:50`），占位符是“非空”的——**占位符能漏过 gate**。`Skeleton` 有占位符检测（`gates.py:_check_plan_task_skeleton_placeholders:612`），`Verification` 没有。

### 2.2 改动（最小、不脆弱）
1. **模板**（`stage_templates.py:50`，PLAN `## Tasks` 块）：把
   `Verification: <!-- fill in -->`
   改为**仍含 `fill in` 词元**的占位符 + 客观判定示例（保留 `fill in` 是关键：现有 `_FILL_IN_PLACEHOLDER_RE = re.compile(r"<!--\s*fill in\s*-->", re.IGNORECASE)` 只认 `fill in`，写成纯中文注释会抓不到）：
   ```
   Verification: <!-- fill in: 客观可判定的通过/失败条件（命令 + 期望结果），例 `pytest tests/x.py::test_y` 全绿 / `GET /foo` 超限返回 429 -->
   ```
2. **Gate**（`gates.py`）：复刻 `_check_plan_task_skeleton_placeholders`（`gates.py:612`）为新函数 `_check_plan_task_verification_placeholders(content)`——对每个 task 的 `_plan_task_field_body(body, "Verification")` 跑 `_PLACEHOLDER_PATTERNS`（`gates.py:96`，已含 `fill in` / `TBD` / `FIXME` / `maybe` / `TODO later`），命中即报 R5 结构失败。
   - 接入点：R5 块（`gates.py:992-997`），紧跟 `# R5.2b` 后加 `# R5.2c`：`issues.extend(_check_plan_task_verification_placeholders(gate_content))`。
   - **不做**“是否客观可判定”的语义启发式判断——那类规则脆弱、误报多，违背“不过度防卫”。占位符检测是确定性的、无误报。
3. **执行技能复用**：`r2p-execute` 的 per-task 评审，把 `Spec References` + `Verification` 作为该 Task 的通过/失败对照依据（见 §3）。这让“验收标准”在执行环节真正发挥作用，而不是再加一个静态字段。
4. **文档**：技能说明 / 模板（agent 指引）里把 `Verification` 描述为“客观、可执行的任务验收标准”。（不动 README，避免触发双语 parity 维护；README 的更新只随 Phase 2/3 的新技能进行。）

**为何不加新字段**：满足“给 Task 验收标准”的诉求，零 schema 膨胀，复用既有 gate 基础设施，且把验收真正接到执行环节。

### 2.3 DESIGN → SPEC → PLAN：无模糊/不确定点（核查：多数已在 Quality Gate）
诉求“这三个阶段不能有模糊或不确定的点”应**分两层**落地，重心在 gate（确定性、更早、不需人），不是全塞 checkpoint。

**已实现（gate，DESIGN/SPEC/PLAN 全覆盖，`_check_stage_schema`）**：
- R2.2：全文（去代码块）扫 `_PLACEHOLDER_PATTERNS`（`fill in`/`TBD`/`FIXME`/`maybe`/`TODO later`）→ 命中即 fail。
- R2.3a：每个必填小节须有非占位实质内容。
- R12：标准 DESIGN 的 `### DECISION-NNN` 若 `Status: pending` 卡 gate（未决技术选择必须 `selected` 或 `none`）。
- 叠加 §2 的 PLAN `Verification` 占位符检查。

**本期增量**：
1. **gate 精准补 marker**（`gates.py:_PLACEHOLDER_PATTERNS`，沿用现有“整行/字段锚定”精度，避免误报）：新增 `???`（3+ 问号）、`待定`、`to be (decided|determined)`。**不**加宽泛 hedging 词（可能/或许/possibly/maybe-inline）——高误报、脆弱，违背“不过度防卫”。
2. **checkpoint 语义判定**（regex 抓不到的语义模糊归人/子代理判断）：在 DESIGN/SPEC/PLAN 的 checkpoint 评审加一条显式标准“无未决歧义 / 未定点 / 无依据的 hedging”。落点：
   - `agent_shortcuts.py:_emit_checkpoint_stop` 的 `needs_subagent_review` 审计指令里点名该项；
   - claude `SKILL.md` / 命令模板的 checkpoint 评审指引同步加这条。

**遇到模糊/不确定点的处理阶梯（verify → 去除；不能则人工选择）**：这是“检测到之后怎么办”的协议，**每一级都映射到 r2p 已有且已强制的机制**，不新造轮子：
1. **先验证去模糊**：能用证据消解的，先 grounding 后写具体答案——repo 代码、Context Pack（`02-project-context`）、DESIGN `## Current Code Evidence`、SPEC `## External Documentation Checked`、跑只读检查。验证得出结论 → 写死，不留模糊。
2. **验证不了 / 是纯选择 → 人工选择**：
   - 在 **DESIGN**：记 `### DECISION-NNN`（`Status: pending`）。已强制——R12：“a human must choose before this gate can pass”，未决就卡 gate-quality。
   - 在 **SPEC / PLAN** 发现、但归属上游决策：用 `r2p-gap-open --owner-stage design …` 路由回属主阶段做决定，再 `r2p-gap-resolve`。已强制——run-close：“Cannot close run while routes remain open”，未结的 route 关不了 run。
   - **执行期（r2p-execute）**：implementer 先用 TDD/证据验证；无法解 → 返回 `NEEDS_CONTEXT`/`BLOCKED` → 控制方补上下文或升级人工（沿用已移植的 SDD 状态处理，见 §3.6）。
3. **绝不静默放过**：留 marker/hedge 也过不了——gate 的 R2.2/§2.3 标记检测会 fail；checkpoint 语义判定再兜一层。

效果：系统结构上**不可能 ship 出未决模糊**——要么验证消解、要么走 DECISION/gap 人工选择（这两条本身被 gate / run-close 强制），要么被 gate/checkpoint 挡下。

**分工口径**：确定性标记 = gate 拦（更早更省，不该挪 checkpoint）；语义模糊 = checkpoint 判；处理阶梯 = 验证优先、不能则人工选择，复用 DECISION-NNN / gap 路由 / SDD 状态。两层检测 + 一条阶梯，重心在 gate。归 **Phase 1**（阶梯文案落 SKILL/命令模板与 `_emit_checkpoint_stop`；执行期那一级随 §3 落地）。

---

## 3. 新功能：Plan 执行技能 `r2p-execute`（决策：自包含复刻 SDD）

### 3.1 目标
当一个 run 的 PLAN 已生成并关闭（`CLOSED_AT_PLAN_CHECKPOINT`），用 `r2p-execute` 把 `07-plan.md` 的 `PLAN-TASK` 逐条落地实现；执行完自动归档。借鉴 superpowers `subagent-driven-development`（SDD）的“每任务一个全新子代理 + 任务评审 + 末尾整分支评审”，**自包含**复刻进 r2p 模板，不依赖 superpowers 是否安装（保证 claude/codex/gemini 三平台一致）。

参考实现（已读取本地 6.0.3 源）：
- `…/superpowers/6.0.3/skills/subagent-driven-development/SKILL.md`
- `…/implementer-prompt.md`、`…/task-reviewer-prompt.md`

**与 SDD 的对照（不是逐字 100% 复刻，是“循环忠实复刻 + 定制裁剪”）**：

| SDD 6.0.3 元素 | r2p-execute | 说明 |
|---|---|---|
| 每任务 fresh implementer 子代理 + TDD | ✅ 保留 | |
| 每任务 review（spec 合规 + 代码质量双结论）+ 修复循环 | ✅ 保留 | |
| 末尾整分支 review | ✅ 保留 | |
| Pre-flight plan review | ✅ 保留 | 发现批量交人决定 |
| 进度账本（恢复地图） | ✅ 保留 | `<run>/execution/progress.md` |
| 文件式 handoff（brief/report 落文件） | ✅ 保留 | |
| 模型分级选择 | ✅ 保留 | |
| git worktree/branch + main 保护 | ❌ 去掉 | 当前分支原地提交（用户要求） |
| 专有脚本 `review-package`/`task-brief` | ❌ 去掉 | 改内联 `git diff -U10` / 从 07-plan.md 抽取，自包含 |
| 无子代理降级 | ❌ 不做 | 子代理硬前提，无则显式失败 |
| 通用 plan 文件输入 | 🔁 改 | r2p 的 `07-plan.md` PLAN-TASK 结构 |
| — | ➕ 新增 | 前置闸门：必须 `CLOSED_AT_PLAN_CHECKPOINT` |
| — | ➕ 新增 | 完成后自动归档（`run-archive`） |

**进度记录与恢复（两层，专为 r2p-continue 续跑）**：
- 状态层：run.md `status = EXECUTING`（持久）→ r2p-continue 据此分流（未关闭=续写 PLAN，EXECUTING=续做实现）。
- 账本层：`<run>/execution/progress.md` 逐条 `- [ ] PLAN-TASK-NNN`；CLI 在 `CLOSED→EXECUTING` 播种骨架，agent 每条 review 干净后标完成；恢复时从第一条未完成 Task 续跑。
- 已知性质：账本仅在任务 review 通过后标完成，故中断在半截的任务整条重跑（fresh 子代理；已落 commit 仍在 git，重跑可见）——与 SDD 一致，非缺口。

**命令分层**：`run-execute-start` / `run-archive` 是 **CLI 命令**（cli.py，与 `run-start`/`run-close`/`run-reopen` 同族，纯状态转移+账本初始化）；`r2p-execute` / `r2p-archive` 是 **shortcut/bin**（agent_shortcuts.py + `tools/r2p-*`，agent/用户入口，内部调 CLI）——同 `r2p-start→run-start` 的包装关系。

### 3.2 状态机改动（硬切）
`tools/workflow_cli/models.py`：

```python
class RunStatus(str, Enum):
    ...
    CLOSED_AT_PLAN_CHECKPOINT = "closed_at_plan_checkpoint"
    EXECUTING = "executing"     # 新增：PLAN 已关闭，正在实现
    ARCHIVED = "archived"       # 新增：执行完成 / 手动归档，终态
```

`ALLOWED_TRANSITIONS`（硬切，`models.py:103`）：
```python
RunStatus.CLOSED_AT_PLAN_CHECKPOINT: {RunStatus.EXECUTING, RunStatus.ARCHIVED},
RunStatus.EXECUTING: {RunStatus.EXECUTING, RunStatus.ARCHIVED},
RunStatus.ARCHIVED: set(),   # 终态
```
（即把现有 `CLOSED_AT_PLAN_CHECKPOINT: set()` 改为可进入 EXECUTING/ARCHIVED。）

`ALLOWED_COMMANDS_BY_RUN_STATE`（`models.py:173`）新增：
```python
RunStatus.CLOSED_AT_PLAN_CHECKPOINT: {"CMD-RUN-REOPEN", "CMD-RUN-EXECUTE-START", "CMD-RUN-ARCHIVE", "CMD-TIER-STATUS"},
RunStatus.EXECUTING: {"CMD-RUN-ARCHIVE", "CMD-TIER-STATUS"},
RunStatus.ARCHIVED: {"CMD-TIER-STATUS"},
```

`is_terminal`（`agent_shortcuts.py:160`）改为：
```python
def is_terminal(status: RunStatus) -> bool:
    return status in (RunStatus.CLOSED_AT_PLAN_CHECKPOINT, RunStatus.ARCHIVED)
```
即：`EXECUTING` 视为“仍开着”（执行中不许开新 run）；`CLOSED` 与 `ARCHIVED` 不阻塞新 run。
> 项目不变量更新：从“仅 CLOSED 终态”改为“EXECUTING 仍开放；ARCHIVED 为新的执行终态”。同步 `CLAUDE.md` 的 Key Invariants 段。

### 3.3 CLI 改动（仅状态 + 账本骨架）
`tools/workflow_cli/cli.py` 新增两条命令：

- `run-execute-start --work-id <id>`：
  - 前置：**严格** `status == CLOSED_AT_PLAN_CHECKPOINT`，否则 `EXIT_CONFLICT`，提示 `plan_not_ready`。（因此本命令永远只在 CLOSED 上触发一次 `CLOSED → EXECUTING`，不存在“重复播种”问题——续跑由 `execute` shortcut 走 EXECUTING 分支，根本不再调本命令。）
  - 动作：`update_run_status(record, EXECUTING)`（沿用既有转移校验，`state.py:57`）；在 `<run>/execution/progress.md` 用 `atomic_write_text` 播种**结构化**账本骨架，逐条 `- [ ] PLAN-TASK-NNN <title>`。
  - 锚点解析：当前 `gates._iter_plan_task_bodies` / `_plan_task_label` 是模块私有。为避免 cli → gates 私有导入，**提取公共 helper 到 `markdown.py`**（它已是 fence-aware Markdown 解析的归属，gates 的 `unfenced_markdown_lines` / `heading_bounded_bodies` 即源于此）：`plan_task_anchors(content) -> list[tuple[str, str]]`（返回 `(PLAN-TASK-NNN, 标题行余文)`），令 cli 播种与 gates 现有检查共用同一解析。骨架只含 ID/标题/勾选框，属结构非语义，语义进度由 agent 追加，符合 CLI/Agent 分工。
- `run-archive --work-id <id>`：见 §4。

> 决策依据：执行循环本身（派发子代理、TDD、评审、修复）是 agent 行为，CLI 无法也不应代劳；CLI 只提供“能不能执行 / 执行到哪 / 收尾归档”的状态闸门。

### 3.4 Shortcut 与 bin
- `agent_shortcuts.py` 新增 `execute` 子命令：读 pointer → work_id → load record：
  - `status == CLOSED_AT_PLAN_CHECKPOINT`：调 `run-execute-start`，打印 `stop: execute_plan`，给出 `plan: 07-plan.md`、`ledger: execution/progress.md`，并指示“按 r2p-execute 技能驱动 SDD 循环”。
  - `status == EXECUTING`：打印 `stop: resume_execution` + 账本路径，指示“从账本第一条未完成 Task 续跑”。
  - 其它状态：`blocked: plan_not_ready`，`next: r2p-continue`。
- 新增 bin 包装脚本 `tools/r2p-execute`（复制 `tools/r2p-continue` 模式，子命令换成 `execute`）。

### 3.5 `r2p-continue` 路由（满足“判断续写 plan 还是续做实现”）
`agent_shortcuts._cmd_continue` 在 load 后增加分支（放在主循环前）：
- `status == EXECUTING` → 打印 `stop: resume_execution`（同 3.4 续跑指引），退出。
- `status == ARCHIVED` → `done: archived`（正常情况下 pointer 已清空，少触发）。
- `status == CLOSED_AT_PLAN_CHECKPOINT` → 现有 `done: run_closed` 分支**扩写**：追加 `to implement: <r2p-execute>` 与 `to archive: <r2p-archive --work-id ...>`。

这样状态即路由：**未关闭 → 续写 PLAN（现有逻辑不动）；EXECUTING → 续做实现**。

### 3.6 技能内容（自包含复刻，裁剪版）
新增模板（三平台），核心是 claude 的 `agent_templates/claude/skills/r2p-execute/`：
- `SKILL.md`：编排说明，关键裁剪/定制：
  1. **前置闸门**：经 `r2p-execute` shortcut 进入——要求 `CLOSED_AT_PLAN_CHECKPOINT`（首次→转 `EXECUTING`）或 `EXECUTING`（续跑）；其它状态停 `plan_not_ready`（与 §3.4 一致）。
  2. **不建分支、原地执行（与 SDD 的有意区别）**：r2p-execute **不新建分支、不开 worktree**，当前在什么分支就在什么分支上实现并提交（用户已授权“写代码+提交”）。刻意放弃 SDD 的“隔离分支/worktree + main 保护”红线。唯一轻量前置：开跑前检查工作树是否干净（`git status --short`，**排除 `.req-to-plan/`** —— 那是 r2p 自己的状态/账本记账，不算用户代码改动），若用户**代码**有未提交改动则提示，避免执行提交与既有改动混在一起；**不强制清理、不阻断**。`push` / 开 PR 不在授权内，仍需用户显式请求。
  3. **Pre-flight plan review**：开跑前扫一遍 `07-plan.md` 找互相冲突 / 计划要求但评审视为缺陷的项，批量问人。
  4. **每任务循环（`Verification` = 每任务完成闸门，过了才算完）**：从 07-plan.md 内联抽取该 Task 文本（替代 SDD 的 `task-brief` 脚本）→ 派发 implementer 子代理（TDD，按 `Skeleton/Steps` 实现）→ **implementer 必须兑现该 task 的 `Verification` 并附证据**（TDD 任务=测试全绿；非 TDD 任务=跑出 `Verification` 写明的可判定结果），写进 report → 写 diff → 派发 task-reviewer（两结论：spec 合规 = 对照 `Spec References` + `Verification` 确认验收条件**确实达成**；代码质量）→ Critical/Important 派 fix 子代理 → **仅当 review 干净（含 `Verification` 满足）才**在账本追加 `Task N: complete`，否则进修复循环重跑。
     - **谁来跑**：兑现 `Verification` 的是 agent（implementer 跑+报证据，reviewer 复核），**CLI 不执行测试/验收命令**——符合“CLI 管状态、Agent 干活”不变量。
     - **diff 看不出来时**：若 `Verification` 落在未改动代码或跨任务，reviewer 报 `⚠️ Cannot verify from diff`，控制方在标完成前自行确认（沿用 SDD 的 ⚠️ 处理），仍是“过了才算完”。
     - **遇模糊/不确定点（§2.3 阶梯的执行期一级）**：implementer 先用 TDD/证据验证去模糊；验证不了或属计划缺陷 → 返回 `NEEDS_CONTEXT`/`BLOCKED`，控制方补上下文或升级人工选择，**绝不擅自拍板含糊实现**。若模糊属上游（SPEC/DESIGN）缺陷，停下走 `r2p-gap-open` 路由回属主阶段，而非在执行里硬凑。
  5. **末尾整分支评审**一次。
  6. **完成即归档**：全部 Task 通过 + 末尾评审干净 → 调 `r2p-archive`（CLI）。代码改动与提交已落在当前分支；`push` / 开 PR 仍需用户显式请求，技能不自动做。
- `implementer-prompt.md` / `task-reviewer-prompt.md`：从 SDD 6.0.3 裁剪移植，去掉对 superpowers 专有脚本（`scripts/review-package`、`scripts/task-brief`）的硬引用，改为内联 `git diff -U10` / 从 07-plan.md 抽取，保证自包含。
- **子代理是硬前提，不做降级回退**：r2p 安装目标（Claude Code / Codex / Gemini）均支持子代理。**不**写“无子代理时顺序执行”的投机回退（违背“不加投机 fallback”原则）；若运行平台无子代理能力，SKILL.md 直接显式失败并说明原因，由人决定。
- 账本：`<run>/execution/progress.md`，跨压缩/中断的恢复地图（CLI 播种骨架，agent 维护状态）。

### 3.7 安装与文档
- `install.py` 已按目录通配安装 `agent_templates/<platform>/skills/r2p-*/SKILL.md`（codex）与 `skills/r2p/SKILL.md`+`commands/r2p-*`（claude）、`commands/*.toml`（gemini）。需为三平台各加 `r2p-execute` 模板文件；bin 通配 `tools/r2p-*` 会自动纳入 `r2p-execute`，无需改安装代码（仅放对文件）。
- README 双语新增 `r2p-execute` 说明；`tests/test_readme.py:test_every_workflow_skill_is_documented` 的技能元组追加 `"r2p-execute"`（同时也要文档化 `r2p-archive`）。

---

## 4. 新功能：需求归档

### 4.1 目录与忽略
- 归档根：`.req-to-plan/archive/`。归档即 `shutil.move(.req-to-plan/<id> → .req-to-plan/archive/<id>)`（同盘为 rename，原子）。
- `.req-to-plan/.gitignore`（工作区内）含一行 `/archive`：归档内容不入 git，活动 run 仍可被项目按需追踪。
  - 新增幂等 helper，放**新模块 `tools/workflow_cli/workspace.py`**（单一职责、与 `atomic.py` 同级；放这里是因为 cli.py 与 agent_shortcuts.py 都要用，而 agent_shortcuts 已 import cli、不能反向，故需一个二者都能 import 的中立模块）：`ensure_workspace_gitignore(base_path)` —— `.req-to-plan/.gitignore` 不存在则建并写 `/archive\n`；存在但缺该行则追加该行。**不做**复杂合并/排序。
  - 调用点：`write_active_pointer`（`agent_shortcuts.py:45`，`.req-to-plan/` 首次创建处）与 `run-archive`（cli）。两处都 import `workspace.py`，无循环依赖。

### 4.2 `run-archive`（CLI）/ `r2p-archive`（shortcut）
`cli.py:_cmd_run_archive`：
- 前置：`status in {EXECUTING, CLOSED_AT_PLAN_CHECKPOINT}`，否则 `EXIT_CONFLICT`。
- 步骤（顺序很重要）：
  1. 置 `status = ARCHIVED`，在**原目录**保存 `run.md`（`mgr.save`）。
  2. `ensure_workspace_gitignore(base_path)`。
  3. 计算 `archive/<id>`；若已存在 → `EXIT_CONFLICT`（不覆盖）。`mkdir .req-to-plan/archive`（parents, exist_ok）。
  4. `shutil.move(run_dir, archive_dir)`。
  5. **提交"移出版本控制"**：`commit_requirement_dir(base, id, "chore(r2p): archive <id>")`（§4.5 统一原语；此时原路径已被移走，`git add` 暂存的是删除）。三守卫尽力而为，失败不阻断归档。
  6. 若 active pointer 指向该 id → 删除 `.workflow-active`（之后 `r2p-continue` 自然回到 `no_selected_run`）。
  7. 打印成功（含归档后路径）。
- `agent_shortcuts.py` 新增 `archive` 子命令（`--work-id` 必填，缺省可用 pointer），bin 脚本 `tools/r2p-archive`。

### 4.3 扫描自然兼容
`scan_open_runs` / `status --all` 用 glob `*/run.md`（单层），归档后 run 在 `archive/<id>/run.md`（双层）**自动落选**；`archive` 目录无直接 `run.md`，不被误认作 work-id。work-id 形如 `WF-YYYYMMDD-*`，绝不为 `archive`，无碰撞。（如需查归档，后续可加 `--include-archived`，本期不做。）

### 4.4 两条归档路径
- **自动**：`r2p-execute` 执行完末尾调 `run-archive`（EXECUTING → ARCHIVED）。
- **手动**：`r2p-archive --work-id <id>` 给“把 07-plan.md 交给外部执行器、不跑 r2p-execute”的 CLOSED 需求收尾（CLOSED → ARCHIVED），避免工作区堆积。

### 4.5 需求目录的版本控制提交（统一原语，加/删共用）
新增 `workspace.py` 的**统一 helper** `commit_requirement_dir(base_path, work_id, message)`，PLAN 完成（加入）与归档（移除）两处复用它：

- **原语（路径限定，加删通吃）**：
  ```
  git -C <base_path> add -- .req-to-plan/.gitignore .req-to-plan/<id>
  git -C <base_path> commit -m <message> -- .req-to-plan/.gitignore .req-to-plan/<id>
  ```
  - `git add -- <path>`：路径**存在**→暂存新增/修改；路径已被**移走/删除**→暂存删除。**同一原语**因此既能"加入"也能"移除"。
  - 把 `.req-to-plan/.gitignore` 纳入 pathspec，让 `/archive` 忽略规则随首次提交入库（归档时它无变化→自动 no-op）。
  - `commit -- <pathspec>` 是偏提交，**不动用户其它已暂存改动**；**绝不** `git add -A` / `git add -f`。落**当前分支**（不建分支，与 r2p-execute 一致）。
- **三守卫（尽力而为、可观测，绝不让调用方失败）**：等价于"`git add` 后是否有暂存内容"——
  1. `base_path` 不在 git 工作树内 → 跳过 + `warning:`；
  2. `.req-to-plan/<id>` 被整体 gitignore（用户选择不追踪）→ `git add` 无暂存（不 `-f` 强提）→ 跳过 + `warning:`；
  3. 无改动 → `git diff --cached --quiet` 为真 → 不 commit（no-op）。
- **无条件自动**：条件具备即提交，无用户开关/环境变量。
- **不做**：不 push、不开 PR（仍需显式请求）；不碰 `.req-to-plan/` 以外任何路径。

两处调用：
- **PLAN 完成（加入版本控制）**：`cli.py:_cmd_run_close` 成功收口后调 `commit_requirement_dir(base, id, "chore(r2p): plan <id>")`（`r2p-continue` 自动关闭也走 run-close，覆盖自动路径）。
- **归档（移出版本控制）**：见 §4.2 步骤——`shutil.move` 把目录搬进 `archive/`（被忽略）后，调 `commit_requirement_dir(base, id, "chore(r2p): archive <id>")` 把"原路径删除"提交掉，目录这才真正脱离跟踪。

### 4.6 版本控制生命周期保证（回答“写完→入库 / 执行完→移出”）
> 实测确认：`.gitignore` 只挡**未跟踪**文件——已提交的需求目录被 `mv` 进 `archive/` 后，git 仍把它当**已删除但仍跟踪**，必须显式提交删除才真正移出。故 §4.2 归档步骤含一次删除提交。

闭环：
1. **写完 PLAN** → run-close 提交 `.req-to-plan/<id>/` → **已纳入版本控制**。
2. **执行完 PLAN** → run-archive 先 `mv` 进 `archive/`（`/archive` 忽略），再提交原路径删除 → **从跟踪树移出**。
- 口径说明（消歧）：“移出版本控制” = **此后不再被跟踪**（工作树/HEAD 不再含该目录），磁盘内容仍在 `archive/<id>/`（被忽略）。它**仍存在于历史提交**里（第 1 步那次 commit）；**不做** history rewrite 去抹历史（那是破坏性操作，超范围）。

---

## 5. 问题修改（核查后定论）

### 5.1 【做】P1 `_prepare_input_file` 普通写 → symlink 加固 + 原子写
`agent_shortcuts.py:223`：当前 `path.write_text(seed)`，是唯一未对齐既有 symlink 加固方向的状态相邻写入（run.md / artifact / pointer 均已用 `atomic_write_text`）。属于“补齐既定方向”，非新增防卫。
```python
def _prepare_input_file(run_dir, stage, suffix, seed=""):
    path = run_dir / "inputs" / f"{stage}-{suffix}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        raise ValueError("unsafe_input_file_symlink")
    if not path.exists():
        atomic_write_text(path, seed)
    return path
```
说明：`atomic_write_text` 用全新临时兄弟文件 + `os.replace` 覆盖，本就不会写穿目标 symlink；额外 `is_symlink()` 拒绝是为捕获“目标已存在的预埋 symlink”（此时 `not path.exists()` 为假会跳过写，但后续 agent 会写穿，故需显式拒绝）。

### 5.2 【不改逻辑，补一行注释】P1 `atomic_write_text` 无 fsync
原子替换已保证“要么旧、要么新，绝不截断”；fsync 只关乎掉电后的 durability，是普通 CLI 工具的**刻意非目标**，与“不过度防卫”一致，**逻辑不加 fsync**。唯一动作（确定执行，Phase 1）：在 `atomic.py` docstring 补一行“仅保证原子替换语义（不会留下截断文件），不保证掉电 durability——后者为刻意非目标”，避免未来被误读为崩溃持久性保证。已确认当前 `atomic.py` 无“crash mid-write…”之类误导性注释，无需删改。

### 5.3 【不改】P1 manifest 固定 `.tmp`
`install.py:191` 用固定 `<manifest>.tmp` + `replace`。核查发现**整个 install 模块**（`_safe_write:1040`）都是“先 `_validate_install_path` 再普通 `write_text`”，manifest 反而是唯一带 temp+replace 的写——它在模块内**已是最受保护**的那个。
- **定论：不改**。install 非并发、已有 symlink 预检，固定 tmp 碰撞与 TOCTOU 都是低危。单独把 manifest 换成 `atomic_write_text` 会让它与同模块其余写法不一致（制造新的不一致面）；把整个 `_safe_write` 改成 O_NOFOLLOW 原子写则是对单用户安装器的过度防卫。两头都违背原则，故维持现状。

### 5.4 【不改】P2 run_dir 自身为 symlink
`atomic_write_text` 不防父目录被换成 symlink。但 `.req-to-plan/<id>` 是用户自己的工作区，本地攻击者替换你自己的目录不在 r2p 威胁模型内。引入 install 的边界扫描会让主 workflow 变重，**不做**（用户亦不建议）。

### 5.5 【不改】P2 reopen `cp.artifact` 与 map 不一致
`cli.py:479-487`：存在性检查用 `STAGE_ARTIFACT_MAP.get(cp.stage)`，但 upsert 记录 `cp.artifact`。核查：artifact 一律经 `STAGE_ARTIFACT_MAP` 创建（`artifact.py:23`），checkpoint 的 `cp.artifact` **恒等于** map 名（不变量），reopen 的拷贝循环（`cli.py:449-456`）也按 map 名拷贝。**无任何漂移路径，非 bug**。
- **定论：不改**。把检查改成 `cp.artifact` 是零行为差异的 no-op，无法写出有意义的回归测试（要测就得人为构造不可能出现的漂移），属投机变更，违背“无现时需求不加改动”。改为在该处加一行注释点明“`cp.artifact == STAGE_ARTIFACT_MAP[cp.stage]` 不变量，故两者可互换”，把意图固化在码内即可。

---

## 6. 分阶段交付（每阶段可独立合并）

> 每个阶段合并后系统都处于可用状态；满足“阶段独立可合并”红线。先写测试（red → green → commit）。

### Phase 1 — 加固与 Plan 验收强化（独立，无依赖）
- 5.1 `_prepare_input_file` symlink + 原子写。
- §2 Verification 占位符 gate（新 `_check_plan_task_verification_placeholders` + R5.2c 接入）+ 模板提示（保留 `fill in` 词元）+ 文档。
- §2.3 DESIGN/SPEC/PLAN 无模糊点：`_PLACEHOLDER_PATTERNS` 精准补 `???`/`待定`/`to be (decided|determined)`；`_emit_checkpoint_stop` 审计指令 + SKILL/命令模板评审指引加"无未决歧义/未定点"判定。
- 5.5 在 reopen 处补一行不变量注释（不改逻辑）。
- 5.2 `atomic.py` docstring 补一行（仅注释）。
- 测试：`test_agent_shortcuts`（symlink 拒绝 / 已存在 symlink）、`test_gates`（Verification 留 `fill in`/`TBD` → 失败；DESIGN/SPEC/PLAN 含 `???`/`待定` → 失败；正常 prose 不误报）、`test_stage_templates`（新模板文案仍含 `fill in`）。
- 交付价值：修了真实缺口、堵了占位符漏过、三阶段无明确模糊标记。

### Phase 2 — 归档基础设施（独立，不依赖执行技能）
- `RunStatus.ARCHIVED` + `CLOSED → ARCHIVED` 转移 + `is_terminal` 调整（仅含 ARCHIVED 部分；EXECUTING 留到 Phase 3）。
- `run-archive`（CLI）+ `r2p-archive`（shortcut）+ `tools/r2p-archive`。
- 新模块 `workspace.py` 的 `ensure_workspace_gitignore`，接入 `write_active_pointer` 与 `run-archive`；归档时 pointer 清空。
- **§4.5/§4.6 版本控制生命周期**：`workspace.py` 统一 helper `commit_requirement_dir(base, id, message)`，两处接入——`cli.py:_cmd_run_close` 收口后（加入）与 `_cmd_run_archive` 移动后（移除）；无条件、路径限定（含 `.req-to-plan/.gitignore`）+ 三守卫。
- README 双语 + 技能列表测试（追加 `r2p-archive`）。
- 测试：`test_cli`（归档前置 / 移动 / 不覆盖 / pointer 清空 / `.gitignore` 写入）、`test_workspace`（统一 helper：临时 git repo——close 加入提交、archive 后原路径**确实脱离跟踪**（`git ls-files` 不再含该目录、归档路径被 `check-ignore` 命中）、非 repo 跳过、被忽略跳过、无改动 no-op、不扫无关已暂存改动）、`test_models`（新转移）、`test_readme`。
- 交付价值：手动归档独立可用；PLAN 完成即把需求文档沉淀进项目仓库，归档后干净移出跟踪。

### Phase 3 — 执行技能（依赖 Phase 2 的 ARCHIVED 与 `run-archive`）
- `RunStatus.EXECUTING` + 转移 + `is_terminal`（EXECUTING 视为开放）。
- `run-execute-start`（CLI，含账本骨架播种）+ `execute`（shortcut）+ `tools/r2p-execute`。
- `r2p-continue` EXECUTING/CLOSED 路由扩写。
- 三平台 `r2p-execute` 技能模板（SKILL.md + implementer/reviewer 提示词；子代理为硬前提，无降级回退）。
- 提取公共 `plan_task_anchors()` helper（cli 播种账本与 gates 检查共用）。
- 末尾自动调 `run-archive`。
- README 双语 + 技能列表测试（追加 `r2p-execute`）。
- 测试：`test_cli`（execute-start 前置/状态/账本）、`test_agent_shortcuts`（execute 与 continue 路由各状态）、`test_models`（EXECUTING 转移）、`test_install`（三平台模板落地）、`test_readme`。
- 交付价值：完整的“需求→PLAN→实现→归档”闭环。

依赖图：`Phase 1` 独立；`Phase 2` 独立；`Phase 3 → Phase 2`。建议顺序 1 → 2 → 3，1 与 2 可并行。

---

## 7. 风险、最脆弱假设与回滚

**最脆弱假设（前提坍塌）**：执行技能假设 `07-plan.md` 的各 `PLAN-TASK` 足够独立，适合“每任务一个全新子代理”。若任务高度耦合，SDD 的隔离反而有害。
- 处理（确定性、非投机）：SKILL.md 的 **Pre-flight plan review** 开跑前扫耦合/冲突，**把发现批量交给人决定**（沿用 SDD 的 pre-flight 机制）。**不**做“自动退化为顺序执行”的隐式降级——是否拆/合并/换法由人定。

**平台假设**：执行依赖子代理，且这是**硬前提**。r2p 安装目标（Claude Code / Codex / Gemini）均支持。无子代理能力时**显式失败**，不写投机回退（见 §3.6）。

**攻击角度**：执行技能不涉外部 API / 高并发 / 数据迁移，仅做代码改动与提交。
- 回滚成本：**不建分支、在当前分支原地提交**，所以没有“弃分支”这种整体回滚——回滚是提交级（`git revert` / `git reset` 执行期产生的提交）。为让回滚可分离，开跑前的“工作树干净”检查很重要（脏树只提示不阻断）。归档 move 可反向移回。整体可控但不如隔离方案干净，这是与 SDD 的有意取舍。

**与全局规则的冲突（按 `/think` 要求显式提示）**：用户全局 `CLAUDE.md` 规定“未经请求不提交/不开 PR”。两处自动提交均为用户显式授权的功能：
- `r2p-execute` 写代码并提交——用户已明确授权，**调用即构成授权**；与 superpowers 的进一步区别：不建分支/worktree、不强制 main 保护，当前分支即执行分支。
- **§4.5 PLAN 完成自动提交需求目录**——用户既定要求，**无条件自动**（无开关）。前提条件：项目仓库**未**把 `.req-to-plan/` 整体 gitignore（否则跳过+warning）；只路径限定提交 `.req-to-plan/<id>/`，绝不扫其它改动、绝不 `-f`。两者均**不 push / 不开 PR**。
- 注：r2p **自身** dev 仓库 `.gitignore` 含 `.req-to-plan/`，故在本仓库内自动提交会被守卫跳过——这是预期，功能面向最终用户项目。

**硬切影响**：`is_terminal` 语义改变会影响 `scan_open_runs`（EXECUTING 阻塞新 run）。需在 Phase 3 同步更新 `CLAUDE.md` Key Invariants 与 README 生命周期描述。

---

## 8. 交接清单（实现就绪）

- **范围**：§2（Verification 强化）、§2.3（DESIGN/SPEC/PLAN 无模糊点：gate marker + checkpoint 判定）、§3（r2p-execute）、§4（归档）、§4.5（PLAN 完成自动提交需求目录）、§5.1（input-file 加固）、§5.2（docstring 注释）、§5.5（不变量注释）。
- **非范围（刻意不做）**：§5.2（fsync）、§5.3（manifest 原子化）、§5.4（run_dir symlink）、§5.5 的逻辑改动；以及任何子代理降级回退、自动顺序执行降级。
- **接口/命令变更**：新增 CLI `run-execute-start` / `run-archive`；新增 shortcut/bin `r2p-execute` / `r2p-archive`；新增 `RunStatus.EXECUTING` / `ARCHIVED` 及转移；`is_terminal` 语义变更；新增公共 helper `plan_task_anchors()`；`run-close`（加入）与 `run-archive`（移除）新增无条件路径限定自动提交副作用（受三守卫保护）。
- **文件清单（主要）**：`models.py`、`cli.py`(`_cmd_run_close` 接入加入提交、`_cmd_run_archive` 接入移除提交)、`agent_shortcuts.py`、`gates.py`、`stage_templates.py`、`markdown.py`(新 `plan_task_anchors`)、`workspace.py`(新模块：`ensure_workspace_gitignore` + 统一 `commit_requirement_dir`)、`atomic.py`(仅 docstring 注释)、`tools/r2p-execute`、`tools/r2p-archive`、`agent_templates/{claude,codex,gemini}/…/r2p-execute*`、`README.md` / `README.zh-CN.md`、`CLAUDE.md`(不变量)。
- **验证命令**：`.venv/bin/python -m pytest tests/ -v`（全绿）；冒烟：`.venv/bin/python -m tools.workflow_cli.agent_shortcuts execute`（在一个 CLOSED run 上，传 `base_path`）。
- **回滚**：三阶段各自可 revert。执行技能**在当前分支原地提交、不建分支**，故回滚是提交级（`git revert`/`reset` 执行期提交），开跑前“工作树干净”检查使这些提交可分离；PLAN 完成的自动提交同为提交级回滚（`git revert` 该 `chore(r2p): plan <id>` 提交，因路径限定它只含 `.req-to-plan/<id>/`）；归档可把目录从 `archive/` 移回并将状态改回 `CLOSED_AT_PLAN_CHECKPOINT`。

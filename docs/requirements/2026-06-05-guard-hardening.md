# 优化需求：guard 收紧 —— 堵住 R1–R8 落地后暴露的旁路

> 状态：已评审、范围已锁定（R9–R13）。本文件是后续 PLAN / 实现的权威输入。
> 来源：外部静态审查报告（针对 R1–R8 落地版的复审）+ 本仓库逐条事实核验（2026-06-05）。
> 分支：`chore/optimize-upgrade`。
> 前序：`docs/requirements/2026-06-05-quality-uplift.md`（R1–R8，已落地于 v0.3.0）。

## 核验前提

外部报告对 v0.3.0 复审。落盘前已逐条核验其事实声明，结论：**断言全部属实，但漏了四个影响实施方案的细节**——

| 报告声明 | 核验 |
|---|---|
| `scope_out_violations()` 只扫 PLAN-TASK body 直接引用 | 属实（`trace.py:203`；对照 `scope_in_not_closed()` `trace.py:148` 已会查 consumed SPEC block） |
| 无 context pack 时 PLAN file-ref 校验静默跳过 | 属实（`gates.py:373-374` 直接 `return []`） |
| `Change Type: new` 与 gate 只认 `create` 不一致 | 属实（`gates.py:385`；`tests/test_integration.py:664` fixture 用 `new`；模板默认 `modify`，`stage_templates.py:29`） |
| Decision Requests 机制不存在 | 属实（全仓 grep 无 `DECISION-`，属新功能提议） |
| README quickstart 无 `--repo-path` | 属实（`README.md:72`） |
| 主 SKILL 命令表缺 `--repo-path` 与 gap 命令 | 属实（`agent_templates/claude/SKILL.md:16-21` 只列到 `r2p-reopen`） |
| `.claude/skills/req-to-plan.md` 写 `v1` | 属实（line 25；实际 `version.py` = `0.3.0`） |
| CLAUDE.md module map 缺新模块 | 属实，且比报告更多——报告列 5 个，实缺 **7** 个（另有 `link_expander.py`、`repo_baseline.py`） |
| CLAUDE.md 引用 `docs/` 但 `.gitignore:19` 忽略之 | 属实（`a275176` 有意移除 docs；2026-06-05 决策更新：白名单 `docs/requirements/` 入库，其余 docs 仍 local-only） |

**报告漏报的四个细节（直接影响方案）：**

1. **Non-goals 误报陷阱（限 block 内子章节）**：schema 强制的文档级 `## Non-goals`（`stage_schema.py:44`）是 SPEC 标题的同级或更高级标题（模板将 SPEC ID 种子化为 `### SPEC-BEHAVIOR-001`，`stage_templates.py:25`，低于 `## Non-goals` 一级），按 `_heading_blocks` 的截断规则（`trace.py:116-137`，block 止于下一个同级或更高级标题）**天然不在任何 SPEC block 内**，不构成误报源。真正的误报向量是 agent 在 SPEC block **内部**写的 Non-goals 子章节（如 `### SPEC-X-001` 下的 `#### Non-goals`）引用 `SCOPE-OUT-*` 声明排除——这是合理写法，按报告原方案全文扫 consumed SPEC block 会被误判为 scope overflow。修复须排除的正是这种 block 内子章节。
2. **`context-build` 内部子命令已存在**（`cli.py:1790`），可中途为已有 run 补建 context pack。R11 的 gate 拦截不会形成死胡同，失败消息必须指向真实 CLI 入口：`python3 -m tools.workflow_cli context-build --work-id <id> --repo-path <dir>`（如 run 使用非默认 base path，则命令需带 `--base-path <base-dir>`，全局位置与子命令位置均可，`cli.py:1816/1830` 各注册一份）。
3. **fixture 互相掩护**：`Change Type: new` 的集成测试能过，是因为那些 fixture 恰好没有 context pack，file-ref 校验被静默跳过。R10 与 R11 必须同批落地，否则单修 gate 会立刻打红现有测试。
4. **Context Pack 不可用也会静默跳过**：不止文件缺失会旁路；`02-project-context.json` 解析失败、缺 `repo_root`、或 `repo_root` 不存在时，`_check_plan_file_refs()` 也直接 `return []`（`gates.py:375-380`）。R11 必须收紧所有"无可用真值锚点"路径，而不是只查文件存在性。

---

## 背景

R1–R8 落地后（v0.3.0），r2p 已具备"需求 → tier 估算 → 模板 seeding → schema gate → trace 闭合 → PLAN 可执行锚点 → 人工 checkpoint"的完整轻量链路，对 light 与中等复杂度的 standard 需求已能做高质量结构化转换。外部复审确认方向正确、无明显过度优化（新增模块均为小文件小职责）。

但复审同时暴露了四个**旁路**——已建成的防线存在可绕过的缝隙：

1. **范围冻结可被中转旁路**：R8 建立的 SCOPE-OUT 拦截只查 PLAN-TASK 直接引用；out-of-scope 项可先写进一个 SPEC，再由 PLAN 消费该 SPEC 间接进入执行计划，整条范围冻结（G5）被旁路。
2. **真值锚定可被静默旁路**：R4/R5 建立的"PLAN 文件引用对真实仓库校验"依赖 context pack，而 `--repo-path` 可选、缺失时校验静默跳过且无任何提示——standard tier 的 run 可在完全无根的状态下产出 PLAN 并通过全部 gate。
3. **词汇缝隙造成隐性 fallback**：`Change Type` 字段任意非法值被静默当作"非 create"处理，违反本仓库 fail-loud 原则；测试 fixture 自身就在用 gate 不认识的词汇（`new`），靠旁路 2 掩护才全绿。
4. **技术选型无显式停点**：重大选型（依赖引入、迁移策略、安全策略）目前靠 agent 在 DESIGN 写 `Chosen Design` + checkpoint 隐式把关；agent 可擅自预决策，人工只能在 checkpoint 事后发现。

此外存在一层**文档漂移**：新能力（`--repo-path`、gap 命令）未进入 README/SKILL 默认路径，用户与 agent 按旧路径运行就会落入旁路 2；开发文档（CLAUDE.md module map、`v1` 注释、docs/ 引用）与 v0.3.0 实际状态脱节。

本轮定位：**不新建体系，只堵旁路**。全部条目为既有防线（R3/R4/R5/R8）的补漏与配套文档，无公共接口变更。

## 目标

- **G6（范围冻结闭环无中转旁路）**：out-of-scope 项无论直接出现在 PLAN-TASK，还是经 consumed SPEC 中转，均被 trace closure 机械拦截；同时规范的 SPEC Non-goals 引用不被误伤。红队 fixture 口径：「SPEC 承载 SCOPE-OUT + PLAN 消费该 SPEC」必须 fail；「SPEC 仅在 Non-goals 引用 SCOPE-OUT」必须 pass。
- **G7（standard tier 真值锚定不可静默缺失）**：standard tier 的 PLAN 在 context pack 缺失、不可读、格式非法或无可用 `repo_root` 时 gate fail 并给出可执行补救命令；任何"跳过校验"都必须可观察，不存在静默降级路径。
- **G8（PLAN task 契约词汇收敛）**：`Change Type` 收敛为封闭枚举，非法值显式报错；模板、gate、测试 fixture 三方词汇逐字一致（延续 R1 的"模板是 gate 的可读形态"原则）。
- **G9（重大选型显式表态）**：standard DESIGN 必须对"是否存在待人工决策的选型"显式表态（列出 pending 决策或声明 none）；存在 `Status: pending` 的决策时 quality gate 拦截，不靠 checkpoint 事后发现。
- **G10（用户文档与能力同步）**：README/SKILL 默认路径包含 `--repo-path` 与 gap 命令；开发文档（module map、版本注释、docs 引用）与 v0.3.0 实态一致。

## 最脆弱前提（设计须为其变形）

本轮全部是 **gate 收紧**，押注：收紧不会产生高频误报把正常流程卡死。两个具体风险及变形：

- **R9 的误报风险**：consumed SPEC block 扫描会命中 block 内 Non-goals 子章节里的合理排除性引用（文档级 `## Non-goals` 因 block 截断规则天然不在扫描范围，见核验前提）。**变形**：扫描时仅排除 SPEC block 内更深层级的 `Non-goals` 子章节（标题规范化后等于 `non-goals`，覆盖 `Non-goals`/`Non-Goals`）；排除范围从该子标题起，到下一个同级或更高级标题止，后续 sibling section 里的 `SCOPE-OUT-*` 仍必须 fail。pass fixture 必须把 `SCOPE-OUT-*` 放在被消费 SPEC block 内的 Non-goals 子标题下，确保排除路径被真实执行而非空洞通过。
- **R11 的旧 run 风险**：升级前已开启、未带 pack 的 standard run 会在 PLAN gate 突然变严。**变形**：失败消息必须内含逐字可执行的 `python3 -m tools.workflow_cli context-build --work-id <id> --repo-path <dir>` 补救命令（非默认 base path 时包含 `--base-path <base-dir>`）；run 生命周期短，不做迁移逻辑。

R12 有一个不同性质的脆弱点：**仅加 gate 是死代码**——会擅自预决策的 agent 根本不会写 `Status: pending`，gate 只能拦住最守纪律（最不需要拦）的 agent。**变形**：standard DESIGN 模板预置 `## Decision Requests` 章节（允许填 `none`），强迫 agent 显式表态；gate 只负责拦 pending。模板不预置，R12 不得单独上。

## 范围 / 非范围

**范围**：R3/R5/R8 既有 gate 的补漏（R9–R11）、DESIGN 阶段一个轻量决策表态约定（R12）、用户与开发文档同步（R13）。锁定条目 **R9–R13**。

**非范围（明确不做或推迟，附理由）：**

- **N6 自动探测 cwd/git root 作默认 `--repo-path`**：用户明确否决（2026-06-05）——agent 可能在任意目录被调起（home、笔记目录、monorepo 子目录），探测错目录会生成**错误的** context pack，错误事实比没有事实更糟。`--repo-path` 保持显式传；忘传由 R11 gate 兜底 + R13 文档引导。
- **N7 Context Pack 任何增强**（npm devDependencies、pyproject metadata、normalized test commands、**浅 symbol scan**）：报告列为"下一步"，本轮全部推迟——尤其 symbol scan 是 AST 斜坡的第一步，且 R9–R13 无一依赖这些增强。待真实 run 暴露需求再立项。
- **N8 AST/调用图、LLM judge、审批 workflow、数据库/daemon、schema DSL 化**：与报告共识一致，明确不做。
- **N9 报告提议的 7 值 `Change Type` 枚举**（`create|modify|delete|rename|config|test|docs`）：`config/test/docs` 是"文件种类"维度，与"操作类型"混在一个字段只会引来新的词汇漂移。收窄为 3 值 + alias（见 R10）。
- **N10 "温和版" R11**（仅当 PLAN 出现真实 `Files:` 且非 `n/a` 时才要求 pack）：条件触发会教 agent 写 `Files: n/a` 绕 gate，制造新旁路。不采纳。

---

## 需求条目

格式：现状 → 质量损失 → 优化 → 收益（度量）→ 工作量 / 依赖。

### 第一批 · gate 补漏（R10/R11 因 fixture 互相掩护必须同批，R9 顺势并入）

**R9 SCOPE-OUT 经 consumed SPEC 中转进入 PLAN 的检测**
- 现状：`scope_out_violations()`（`trace.py:203`）只扫 PLAN-TASK body 直接引用；`scope_in_not_closed()`（`trace.py:148`）已会查 consumed SPEC block——同一 trace 模型里两个方向不对称。
- 质量损失：out-of-scope 项写进 SPEC、PLAN 消费该 SPEC，即可绕过 R8 的范围冻结，且全部 gate 通过。
- 优化：`scope_out_violations()` 增查 PLAN-TASK consumed SPEC block 中的 `SCOPE-OUT-*`，复用 `scope_in_not_closed()` 的既有模型（`_spec_blocks` + `plan_consumed_spec_ids`）；**扫描时仅排除 SPEC block 内更深层级的 `Non-goals` 子章节**（标题规范化后等于 `non-goals`，覆盖 `Non-goals`/`Non-Goals`；范围到下一个同级或更高级标题止，后续 sibling section 里的 `SCOPE-OUT-*` 仍 fail；文档级 `## Non-goals` 天然不在 block 内，无需处理）。
- 收益（G6）：范围冻结闭环补上中转旁路；红队 fixture「SPEC 承载 SCOPE-OUT + 被 PLAN 消费」fail、「仅 Non-goals 引用」pass。
- 工作量：小。依赖：无硬依赖；建议与 R10/R11 同批提交（见批次说明）。

**R10 `Change Type` 枚举统一与显式校验**
- 现状：`gates.py:385` 只认 `create`；`test_integration.py:664` fixture 用 `new`；模板默认 `modify`；非法值被静默当作"非 create"——隐性 fallback，违反 fail-loud 原则。
- 质量损失：`Change Type: new` + 新文件路径在有 pack 时被误报 missing path；任意乱写的值无人发现。
- 优化：枚举收敛为 `create|modify|delete`，`new` 作为 `create` 的 alias 接受；task-fields 检查对枚举外的值显式报 gate issue；修正 `test_integration.py` fixture 用 `create`；模板保持 `modify` 不变。
- 收益（G8）：模板、gate、fixture 词汇逐字一致；非法词汇 fail-loud。
- 工作量：小。依赖：与 R11 同批（fixture 互相掩护，见核验前提）。

**R11 standard PLAN 缺失或不可用 Context Pack 时 gate fail**
- 现状：`_check_plan_file_refs()`（`gates.py:373-380`）在无 `02-project-context.json`、pack JSON 解析失败、缺 `repo_root`、或 `repo_root` 不存在时直接 `return []`，静默跳过全部文件事实校验；`--repo-path` 可选且缺失无提示。
- 质量损失：standard tier 最需要真值锚定的 run，恰恰可以在完全无根状态下产出 PLAN 并全绿——R4/R5 的核心承诺被静默旁路。
- 优化：PLAN 阶段 quality gate 增查——`tier.base == standard` 且 context pack 缺失、不可读、格式非法、缺 `repo_root`、或 `repo_root` 不存在时均报 gate issue，消息内含逐字可执行的补救命令 `python3 -m tools.workflow_cli context-build --work-id <id> --repo-path <dir>`（内部子命令已存在，`cli.py:1790`，无需新增独立可执行文件；非默认 base path 时命令需包含 `--base-path <base-dir>`）。light tier 维持现状（纯文档/简单需求不强制绑 repo）。
- 收益（G7）：忘传 `--repo-path` 从"静默产出无根 PLAN"变为"明确拦截 + 一条命令补救"。
- 工作量：小。依赖：与 R10 同批。

### 第二批 · 决策显式化

**R12 Decision Requests pending gate（模板 + schema + gate 三件套）**
- 现状：技术选型靠 standard DESIGN 的 `Options Considered`/`Chosen Design` + checkpoint 隐式把关；agent 可擅自预决策，人工在 checkpoint 才能事后发现；无 `needs_decision` 类显式停点。
- 质量损失：重大选型（引入依赖、迁移策略、安全策略、公共 API 变更）被 agent 单方面决定后，纠错成本随下游 SPEC/PLAN 推进放大。
- 优化（三处缺一不可，见最脆弱前提）：
  1. standard DESIGN 模板预置 `## Decision Requests` 章节，预置说明允许填 `none`，否则按约定列出 `DECISION-NNN` heading 条目。条目语法固定为 `### DECISION-NNN <title>`，block 截止到下一个同级或更高级 heading；block 内字段契约为 `Question:` / `Options:` / `Recommended:` / `Status:`，且 `Status: selected` 时另须 `Selected:` 与 `Rationale:`（仅此状态必填）。`none` 必须是章节内唯一非空、非注释正文；
  2. `stage_schema.py` 将该章节登记为 standard DESIGN required heading；
  3. quality gate 只扫描 `## Decision Requests` 章节内的 `### DECISION-NNN` blocks，存在 `Status: pending` 时 fail，消息列出未决 `DECISION-*` ID；`Status: selected` 但缺 `Selected:` 或 `Rationale:` 同样 fail；DECISION-* block 缺 `Status:` 视同枚举外 fail-loud；章节为空、`none` 与 DECISION 条目混用、或既无 `none` 也无条目同样 fail；DECISION blocks 之外出现非 `none`、非注释的杂散正文同样 fail（章节内容只允许 `none` 或 block 两种形态）；重复的 `DECISION-NNN` id fail；单 block 内多条 `Status:` 行 fail；block 体内出现 bullet 形态的嵌套 `DECISION-*` 标记 fail；block 截断于任意层级标题——块内子标题（含 `#### DECISION-*` 伪块）落入杂散正文规则（实现复审 2026-06-05 收紧，堵"合法 block 之后的伪块被静默吸收"漏洞）。gate 兜底范围**仅限 Status 生命周期**（枚举值、Status 行存在性、章节非空 + selected 时 `Selected:`/`Rationale:` 的存在性）；Question/Options/Recommended 为模板引导字段，语义完整性由 checkpoint 把关，CLI 不验（Agent/CLI 分界原则）。
- 边界：**无新 CLI 命令、无新状态机、无新 RunStatus**。决策放行复用既有 repair flow（agent 改 `Status: selected` + `Selected:`/`Rationale:` → `stage-update → stage-ready → gate-quality`）。`Status` 词汇只认 `pending|selected`，枚举外 fail-loud（与 R10 同原则）。
- 旧 run：升级前已 seeded 的在途 standard DESIGN 会因新增 required heading 在 schema gate 以 missing-heading 消息失败，经既有 repair flow 补 `## Decision Requests` 章节即可；不做迁移（与 R11 同理由：run 生命周期短）。
- 收益（G9）：选型从"checkpoint 事后发现"变为"gate 前置拦截"；agent 必须显式表态（none 或列决策）。
- 工作量：小-中。依赖：R1 模板体系（已落地）。

### 第三批 · 文档同步

**R13 用户文档与开发文档同步**
- 现状：见核验前提表后五行。
- 质量损失：用户/agent 按 README 旧路径运行必然落入 R11 所堵的旁路；开发文档误导后续维护者。
- 优化（全部小修，一次提交）：
  1. `README.md` + `README.zh-CN.md` quickstart 改为 `r2p-start "Add rate limiting" --repo-path .`，注明"需求针对当前项目时必传，跨仓库需求传目标仓库路径"（N6 决策的配套），并在 PLAN gate 缺失/不可用 pack 的补救说明里使用真实 CLI 入口 `python3 -m tools.workflow_cli context-build --work-id <id> --repo-path <dir>`，不写不存在的 standalone `context-build` 可执行文件；
  2. claude 主 `SKILL.md`（`agent_templates/claude/SKILL.md:16-21`）聚合命令表补 `--repo-path` 参数与 `r2p-gap-open`、`r2p-gap-resolve` 两条命令行；codex/gemini 为 per-command 模板形态、无聚合命令表，且其 gap 命令模板与 `r2p-start` 的 `--repo-path` 注记均已存在（`agent_templates/gemini/commands/r2p-start.toml:2` 等），核对即可、不改；
  3. `.claude/skills/req-to-plan.md` 整体对齐 v0.3.0 实态，不止 line 25：过期 `v1` 注释改为不硬编码版本（延续 R6 反魔数原则）；`install_cli.py` 的 "stub (full impl: Task 14)" 注记改为已完整实现；`codex/ # AGENTS.md` 改为 per-command skills 形态（否则与本文 R13-2 自相矛盾）；Module Responsibilities 树补齐缺失模块（R13-4 的 7 个加 `install.py`）；
  4. `CLAUDE.md` module map 补 7 个模块：`context_pack.py`、`stage_schema.py`、`stage_templates.py`、`trace.py`、`markdown.py`、`link_expander.py`、`repo_baseline.py`；
  5. `CLAUDE.md` 对 `docs/req-to-plan-design.md` 的引用注明：docs/ 除 `requirements/`（已白名单入库）外为 local-only（`a275176` 移除后的 2026-06-05 决策更新）。
- 收益（G10）：新能力进入默认路径；开发文档与 v0.3.0 实态一致。
- 工作量：小。依赖：措辞跟随 R11/R12 最终行为，排最后。

---

## 验证策略（贯穿全部条目）

遵循仓库 red→green→commit 约定：**先写红队/合规 fixture 对，再实现**。

- R9：「SPEC 承载 SCOPE-OUT + PLAN 消费」fail；「SCOPE-OUT 位于被消费 SPEC block **内部的 Non-goals 子标题**下 + PLAN 消费」pass（fixture 必须用 block 内子标题，确保排除路径被真实执行，而非借文档级 `## Non-goals` 空洞通过）；「Non-goals 子章节之后的 sibling section 含 `SCOPE-OUT-*` + PLAN 消费」fail；「PLAN-TASK 直接引用」维持 fail（既有行为回归）。
- R10：`new` 等价 `create`（有 pack、新文件路径不报 missing）；枚举外值（如 `Change Type: refactor`）fail。
- R11：standard + 无 pack + PLAN gate → fail 且消息含 `python3 -m tools.workflow_cli context-build`；standard + pack JSON 解析失败 / 缺 `repo_root` / `repo_root` 不存在 → fail 且不静默跳过；light + 无 pack → pass；standard + 有可用 pack → 走既有 file-ref 校验。
- R12：standard DESIGN 含 `Status: pending` → fail 并列出 ID；全部 `selected`（含 `Selected:` 与 `Rationale:`）或章节内仅显式 `none` → pass；`Status: selected` 但缺 `Selected:` 或 `Rationale:` → fail；`Status` 枚举外值 → fail；`### DECISION-NNN` block 缺 `Status:` → fail；`none` 与 DECISION 条目混用 → fail；blocks 之外的杂散非注释正文 → fail；章节为空（无 `none` 无条目）→ fail；重复 DECISION id → fail；单 block 多 `Status:` 行 → fail；合法 block 之后的 `#### DECISION-*` 伪块或块内 bullet `DECISION-*` 标记 → fail。
- R13：无可执行断言，人工核对清单五项；如 SKILL 模板有渲染测试则同步更新。

完成口径：全量测试绿（`.venv/bin/python -m pytest tests/ -v`）+ 新增 fixture 全绿 + CI（3.11/3.12 matrix）在 PR 跑通。不钉死精确测试数（R6 原则）。

## 建议落地顺序

**R9 + R10 + R11（一组提交）→ R12 → R13**

理由：R10/R11 因 fixture 互相掩护必须同批，R9 同属 gate 收紧顺势并入，一次把第一批红队 fixture 立起来；R12 独立成批（模板+schema+gate 三件套）；R13 文档措辞依赖 R11/R12 最终行为，排最后。

# 优化需求：从"流程守门员"到"低偏移规划契约"

> 状态：已评审、范围已锁定（R1–R8）。本文件是后续 PLAN / 实现的权威输入。
> 来源：外部静态审查报告 + 本仓库逐条事实核验（2026-06-05）。
> 分支：`chore/optimize`。

## 核验前提

外部报告自称"未实跑测试"。落盘前已对其事实声明逐条核验，结论：底座可信，且有一处比报告更严重——

| 报告声明 | 核验 |
|---|---|
| `version.py` = 0.2.3 | 属实 |
| 测试基线 skill=589 / CLAUDE.md=602 | 属实，且实跑 `pytest --co` = **673**。三处各说各话，魔数已失真 |
| `test_agent_shortcuts.py` 硬编码 `## r2p Version\nv1` | 属实（`tests/test_agent_shortcuts.py:49`） |
| `requirements.txt` 仅 `pyyaml`、test 绑死 `.venv` | 属实 |
| `--repo-path` 内部 CLI 有、`r2p-start` 未暴露 | 属实（`cli.py:1301/1327` 有；`agent_shortcuts.py:709-711` 无） |
| `expand_links()` 有实现和测试，但生产路径未调用、未接入 `run-start` | 属实 |
| gate 偏结构不偏语义 | 属实（仅查 ID closure/duplicate、External Docs 标题、PLAN-TASK 存在、code fence） |
| repo baseline 过浅 | 属实（`repo_baseline.py` 仅 LOC/语言/monorepo/submodule） |
| 状态以 `run.md` Markdown 为主存储 | 属实（`state.py:603-619`，无 run.json/原子写） |

---

## 背景

`req-2-plan`（r2p）已具备扎实的确定性工作流内核：状态机、安装/卸载安全、阶段流转、quality gate、checkpoint、gap routing 均有实现并被测试覆盖（实测 673 条）。但产品核心承诺是——**"任意复杂度的需求，结合现有项目代码，稳定产出高质量 DESIGN/SPEC/PLAN，使另一个 agent/工程师无需重判范围即可低偏移地执行 PLAN"**。当前实现与该承诺间存在一层结构性缺口：

1. **质量门只验结构不验语义**：格式合格但空泛、与真实代码脱节的产物可通过。
2. **现有代码事实未进入流程**：日常入口 `r2p-start` 收不进 `--repo-path`；即便收进，baseline 也只统计 LOC/语言，不含依赖/测试命令/入口/配置/符号。
3. **产物结构靠 agent 自觉**：安装模板只讲命令行为，不给 DESIGN/SPEC/PLAN 的强制结构与反例，跨模型/上下文产出风格漂移大。
4. **跨阶段无可追踪覆盖**：现有 upstream ID closure 只在单文档内找引用，不能机械保证"每个需求都被 SPEC/PLAN 消费、无遗漏"。
5. **项目自身存在信任漂移**：测试基线三处为 673/602/589；版本注释、`v1` fixture 与实际 0.2.3 脱节；无 CI、dev 依赖不完整。

## 目标

把产物从"自由文本"收敛为"下游可机械校验的中间表示"，让质量门从"查形"升级为"查形 + 锚定真值"，从而**可证地**降低 PLAN 到代码的执行偏移。可度量目标：

- **G1（可验证的质量门）**：能用红队 fixture——"格式合格但空泛/不可执行"的 DESIGN/SPEC/PLAN——证明新 gate 拒绝它们；当前 gate 放行。这是"质量提升"的硬定义与 TDD 验收口径。
- **G2（代码事实进入流程）**：standard tier 的 run 默认携带 Project Context Pack；PLAN 的文件、配置、入口引用可对其做结构校验；符号引用在 AST pack 引入前仅做 advisory。
- **G3（覆盖闭合可机械证明）**：每个 SPEC ID 至少被一个 PLAN-TASK 消费；每条 In-Scope 范围条目必须沿已定义 trace 边闭合到 PLAN，由 gate 自动校验。
- **G4（项目信任基线）**：测试基线单一真源、CI 在 PR 跑绿、版本/fixture 无硬编码漂移。
- **G5（设计前冻结范围 = 设计文档 G1）**：`requirement_brief` 强制含 In-Scope / Out-of-Scope，范围条目挂进 trace；PLAN 若显式引用 Out-of-Scope ID 或缺少必需 scope reference，可被机械拦截为范围外溢。挖掘深度随 tier 伸缩（落地设计文档 G6）。

## 最脆弱前提（设计须为其变形）

整条"语义 gate"路线押注：**结构化 schema 校验能真正提升输出质量**。风险：schema 查"形"不查"真"——一份 PLAN 可标题齐全、每 task 有 Spec Reference、无 TBD，却依然对代码库胡编。若过度堆砌"标题/占位符"这类纯形态检查，得到的是"格式更工整的幻觉 PLAN"+额外摩擦。

**变形**：权重压在**同时是结构化又锚定真值**的检查上——① trace 覆盖闭合（纯结构、100% 可靠）；② 锚定 Context Pack 的文件、配置、入口引用（对真实仓库事实做结构校验）。符号引用在 AST pack 引入前只做 advisory，不作为硬拦截。纯标题/禁占位符检查只当廉价护栏。**因此 Context Pack（R4）是 PLAN gate（R5）不流于表面化的前置条件**，下面的落地顺序据此排定。

## 范围 / 非范围

**范围**：requirement → PLAN 链路内的产物结构、质量门、上下文摄入、可追踪性、需求挖掘与范围冻结，以及保障这些的项目基础设施（CI / dev deps / 漂移）。锁定条目 **R1–R8**。

**非范围（明确不做或推迟，附理由）**：

- **N1 `run.md` → canonical `run.json` 重写**：单用户、单 active run、无并发，无损坏证据。整块 JSON 化是解决尚未发生的问题。仅在出现 torn-write 实证时引入 `temp + rename` 原子写小切片。
- **N2 execution report + drift_score**：超出 requirement→PLAN 边界；`3×… + 5×…` 权重凭空设定的伪精度；执行器在 r2p 之外。trace 覆盖（R3）已替代其结构化诉求。
- **N3 cli/agent_shortcuts 大重构（WorkflowStepper/StageService/…）**：报告自述"目前还能读"，为未到来的复杂度提前抽象。仅在 R2/R5 增加分支时顺手抽取，不立项。
- **N4 HTTP link 默认展开**：SSRF/内网泄露风险。安全默认改为本地相对链接-only，HTTP 标记"未展开需人工确认"（见 R4③）。
- **N5 `package.json` 改 `docs/**`**：`docs/plans`、`docs/specs`、本目录均为内部工作文档，默认不随 npm 包发布。保持现状。

---

## 需求条目

格式：现状 → 质量损失 → 优化 → 质量收益（度量）→ 工作量 / 依赖。

### 第一批 · 核心（直接服务低偏移承诺）

**R1 阶段产物模板 + content seeding**
- 现状：`r2p-continue` 在 `needs_content` 时创建空白 `inputs/<stage>-content.md`。
- 质量损失：agent 从白纸开始，结构随机。
- 优化：按 tier 提供 requirement_brief / risk_discovery / DESIGN / SPEC / PLAN 模板（light 精简 / standard 完整），seeding 时自动注入上游摘要 + trace 表骨架 + Context Pack 摘要。
- 实现对齐：模板的字段名与 heading 必须与 R2 schema gate、R5 及 `gates.py` 现有 PLAN-TASK 字段正则（`Spec References / Change Type / Files / Verification`）逐字一致——模板是 gate 的可读形态，二者错字即互相失效。
- 收益（G1）：产出结构方差下降；红队 fixture 可基于"缺失必备小节"判定。
- 工作量：中。

**R2 阶段 schema gate（tier-aware）**
- 现状：gate 只查非空 + ID closure。
- 优化：为 requirement_brief / risk_discovery / DESIGN / SPEC / PLAN 分别校验 required headings、required fields、ID pattern、禁占位符（TBD/maybe/TODO later 作为最终内容）；strictness 随 tier 变化。PLAN 专属的任务覆盖、编号、Verification 规则归 R5，不在 R2 重复定义。
- 收益（G1）：空壳文档被拒。
- 工作量：中。依赖 R1（模板即 schema 的可读形态）。

**R3 跨阶段 trace 覆盖校验**
- 现状：closure 仅单文档内找引用。
- 优化：由 gate 派生/校验覆盖闭合，先定义 trace 最小模型再实现：
  - ID namespace：`REQ-*` / `SCOPE-IN-*` / `SCOPE-OUT-*` / `RISK-*` / `DES-*` / `SPEC-*` / `PLAN-TASK-*`。
  - 边类型：`covers`、`derives_from`、`mitigates`、`deferred_to`、`out_of_scope`。
  - 闭合规则：每个 `SPEC-*` 被 ≥1 `PLAN-TASK-*` 消费；每条 `SCOPE-IN-*` 必须经 DESIGN 或 SPEC 闭合到 PLAN；`RISK-*` 只在存在时要求被 mitigation、defer 或 out-of-scope 闭合，不强制每条需求都经过 RISK。
  - 实现策略：优先"自动派生"而非新增需手维护的 artifact。
- 收益（G3）：漏需求/漏消费成为可拦截的 gate 失败。
- 工作量：中。

**R4 repo-path 打通 + 轻量 Project Context Pack + 本地 link 摄入**
- 现状：`r2p-start` 不暴露 `--repo-path`；baseline 过浅；`expand_links()` 有实现和测试，但生产路径未调用、未接入 `run-start`。
- 优化（三步可独立交付）：
  1. `r2p-start` 暴露 `--repo-path`（或自动探测 git repo）。
  2. 轻量 Context Pack（依赖版本、测试命令、入口、源码树、配置文件——**先不做 AST 符号提取**；因此只承诺文件/配置/入口硬校验，符号只 advisory）。
  3. 本地相对链接默认摄入 intake，HTTP 标记"未展开需确认"。
- 收益（G2）：PLAN 不再凭空写路径，是 R5 的前置。
- 工作量：中-大。符号提取留作后续增强。

**R5 PLAN 可执行性静态 gate**
- 现状：只强制 PLAN-TASK 存在 + TDD code fence。
- 优化（安全子集）：每个 task 有 Spec References 且能在 SPEC 找到、每个 SPEC 被覆盖、Verification 非空、PLAN-TASK 编号连续唯一；**文件/配置/入口引用对 Context Pack 做硬校验，`Change Type: create` 的任务豁免该硬校验（复用 `gates.py` 现有 PLAN-TASK 字段正则里已有的 `Change Type` 字段，不新造标注）；符号引用只 advisory**。
- 实现对齐：「每个 SPEC 被 ≥1 PLAN-TASK 消费」与 R3 的同名闭合规则是同一条，R3 定义、R5 调用，**共用同一校验函数**，避免两份实现漂移。
- 收益（G1+G3）：PLAN 从"格式对"逼近"可执行契约"。
- 工作量：中。依赖 R3、R4。

**R8 需求挖掘 + 范围冻结（tier 分层强化 `requirement_brief` / `risk_discovery`）**
- 现状：这两个阶段 gate 零专属检查（只走非空 + ID closure），模板无 scope/挖掘指导，tier 不映射挖掘深度——而"范围漂移"恰是设计文档第一痛点、"设计前冻结范围"是 G1。最该挖深的阶段验得最松。
- 质量损失：范围未冻结即进设计 → 下游 SPEC/PLAN 系统性漂移；隐含需求未被挖出 → agent 跳过挖掘直接给方案。
- 优化（两个能力，分清谁能做）：
  1. **范围冻结（CLI 可强校验显式结构，语义由评审把关）**：`requirement_brief` 强制含 In-Scope / Out-of-Scope / 验收标准三个非空小节，按 tier 分层（light 各 ≥1 条；standard 必须有显式 non-goals + 假设清单）。**关键：范围条目必须有稳定 ID 并挂进 R3 trace**——In-Scope 须被下游消费；PLAN 显式引用 `SCOPE-OUT-*` 或没有覆盖必需 `SCOPE-IN-*` 时，CLI 判范围外溢。未显式引用但语义越界的情况，由 checkpoint review 拦截。
  2. **需求挖掘（CLI 只验存在性，语义靠 Agent）**：模板给挖掘清单（隐含需求 / 假设 / 边界 / 待澄清）；gate 校验 `Open Questions` 小节存在，standard tier 须有 ≥N 条假设或待澄清，防止跳过挖掘。
- 防陷阱：写了 Out-of-Scope ≠ 范围被冻结。只查小节存在是廉价护栏，天花板低；真正的锚点是范围条目进 trace。**故 R8 离开 R3 退化为走过场，必须与 R3 绑定，不得单独上。**
- 收益（G5，直击设计文档 G1/G6）：范围漂移从"靠自觉"变为"可机械拦截"；挖掘深度随复杂度伸缩。
- 工作量：中。依赖 R1（模板）、R2（schema gate）、R3（trace，硬依赖）。是 R1/R2/R3 在 brief/risk 阶段的实例化 + tier→深度映射，非新建体系。

### 第二批 · 项目健康（低成本高信噪，建立信任基线）

**R6 消除 docs/version/test-baseline 漂移**
- 现状：673/602/589 三处打架，`v1` fixture、版本注释脱节。
- 优化：测试基线收敛到单一真源（或断言 `≥N` 而非精确魔数）；去掉 skill/CLAUDE.md 硬编码计数与过时 `v1` 注释。
- 收益（G4）：文档驱动工具的可信度。
- 工作量：小。

**R7 dev deps + CI**
- 现状：仅 `pyyaml`，test 绑死 `.venv`，无 CI。
- 优化：新增 `requirements-dev.txt`（pytest 等）；加 GitHub Actions 在 PR 跑 `pytest`；把 `npm test` 与硬编码 `.venv` 路径解耦。
- 收益（G4）：PR 绿条可被独立验证。
- 工作量：小-中。

---

## 验证策略（贯穿全部条目）

遵循仓库 red→green→commit 约定：**先写红队/覆盖 fixture，再实现**。每条 gate 类需求配一对测试——一份"应被拒的空壳/不可执行产物"（断言新 gate fail）+ 一份"合规产物"（断言 pass）。完成口径：**R6 收敛后的单一真源基线全绿 + 新增 fixture 全绿 + CI 在 PR 跑通**（不在本文件钉死精确测试数，以免重蹈 R6 要消除的魔数漂移）。

## 建议落地顺序

R6 → R7 → R1 → R2 → R4 → R3 → R8 → R5

理由：先用 R6/R7 立起信任基线与 CI 护栏；R1 是 R2 的可读 schema 形态；Context Pack（R4）是 R5 不流于表面的前置；R3 串起覆盖校验；**R8 紧接 R3 之后、排在 R5 之前——先把范围冻住（G1），后面的 SPEC/PLAN gate 才有意义**。

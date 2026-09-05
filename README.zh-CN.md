[English](README.md) | 简体中文

# req-2-plan

[![npm version](https://img.shields.io/npm/v/%40xenonbyte%2Freq-2-plan.svg)](https://www.npmjs.com/package/@xenonbyte/req-2-plan)
[![node](https://img.shields.io/node/v/%40xenonbyte%2Freq-2-plan.svg)](https://nodejs.org)
[![license: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](./LICENSE)

> 把原始需求变成经过评审的实现 PLAN，再在当前分支上执行。

`req-2-plan` 为 AI coding agent 提供分阶段工作流：明确范围、识别风险、记录设计决策、
定义 SPEC，最后产出获批的 PLAN。你可以独立使用这份计划，也可以运行 `r2p-execute`
完成实现、测试、评审和归档。

npm 包安装共享 Python CLI，以及 **Claude Code**、**Codex**、**Gemini**、
**opencode** 的 agent 集成。运行状态保存在本地 Markdown 文件中，无需数据库或服务端。

**目录：** [安装](#installation) · [快速开始](#quick-start) · [工作流命令](#workflow-commands) · [执行 PLAN](#executing-a-plan) · [运行文件与恢复](#run-storage-and-recovery) · [常见问题](#troubleshooting) · [开发](#development)

## Why r2p

当改动需要明确范围、分析风险，或在多个 agent 之间可靠交接时，可以使用 `r2p`。
原始需求始终保留，每个阶段都要通过 entry gate、quality gate 和人工 checkpoint，
才能进入下一阶段。

agent 负责需求分析和文档的语义内容；CLI 管理状态、结构模板与校验，不负责生成正文，
也不替代人的判断。

## Features

- **仓库上下文**：扫描目标仓库，以实际代码、依赖和测试命令支撑 tier 估算与 Project Context Pack。
- **规划可追踪**：关联范围、风险、DESIGN、SPEC 和 PLAN 任务；排除项统一声明在 requirement brief 中。
- **阶段交接有门槛**：记录决策和评审证据后再推进；需要修正决策时，可以重开 run 或路由上游缺口。
- **执行经过评审**：默认使用 `strict` 逐任务评审；符合条件的机械性改动可显式选择 `fast`，两种模式都要求最终评审和完整验证。
- **可恢复的进度**：依据权威角色检查点继续执行，分别记录实现和修复的 commit 区间。
- **受管安装**：多平台共享可执行 wrapper，覆盖前备份用户文件，卸载只移除受管路径。

## Supported platforms

`r2p` 当前支持 4 个平台。`--platform` 使用下表中的 platform ID。
安装入口路径相对于各平台的默认目录。

| Agent platform | Platform ID | Default home | Installed surface |
|---|---|---|---|
| Claude Code | `claude` | `~/.claude/` | `skills/r2p/SKILL.md` 和 `commands/r2p-*.md` |
| Codex | `codex` | `~/.codex/` | `skills/r2p-*/SKILL.md` |
| Gemini | `gemini` | `~/.gemini/` | `commands/r2p-*.toml` |
| opencode | `opencode` | `~/.config/opencode/` | `commands/r2p-*.md`，由 Claude 模板生成 |

共享 wrapper 安装在 `~/.req-to-plan/bin` 下。

## Installation

需要 Node.js 18+、可通过 `python3` 或 `python` 调用的 Python，以及运行 workflow
wrapper 的 Bash。CI 验证 Python 3.11 和 3.12。执行 PLAN 还需要 Git，以及能够派发
subagent 的 agent 宿主。

将 `pyyaml` 安装到 agent shell 实际使用的 Python 环境。对于支持用户级包目录的 Python：

```bash
python3 -m pip install --user "pyyaml>=6.0"
```

然后安装 npm 包和所需平台集成：

```bash
npm install -g @xenonbyte/req-2-plan
r2p install --platform codex
r2p status
```

可以用逗号分隔多个平台，或省略 `--platform` 安装全部支持的集成：

```bash
r2p install --platform claude,codex,gemini,opencode
r2p install
```

> [!NOTE]
> 生命周期命令只使用 Python 标准库；`r2p version` 或 `r2p status` 成功，并不代表
> workflow 依赖已经可用。wrapper 优先使用 `PATH` 中的 `python3`，其次是 `python`。
> 使用虚拟环境时，应让 agent 启动时的 `PATH` 包含该环境。

重新安装某个平台会刷新其受管文件。已存在的用户文件会在覆盖前备份，卸载时恢复。
升级 npm 包后，请对所用集成重新运行 `r2p install`。

## Quick start

在项目 workspace 中打开 agent，调用安装好的 `r2p-start` 命令或 skill。
支持斜杠命令的宿主可以这样使用：

```text
/r2p-start "Add rate limiting"
/r2p-continue
```

也可以从需求文件启动：

```text
/r2p-start --file change-req.md
```

默认以当前仓库作为上下文来源；`--repo-path <dir>` 可指定另一个仓库，用于 tier 估算
和 Project Context Pack。

按照输出的 `next:` 动作锁定 tier、填写文档、修复 gate 或评审 checkpoint。
反复运行 `r2p-continue`，直到 PLAN 获批。你可以到此停止，也可以显式调用
`r2p-execute` 开始实现。

若需从终端查看状态或驱动共享 wrapper，将其目录加入 `PATH`：

```bash
export PATH="$HOME/.req-to-plan/bin:$PATH"
r2p-status
```

终端 wrapper 管理状态并打印下一步动作；文档撰写和执行编排指令由 agent 集成提供。

## Workflow commands

这些命令操作当前 workspace 中的 run。方括号表示可选参数；通常可以直接使用
`r2p-continue` 输出的下一条命令。

| Command | Purpose | Arguments |
|---|---|---|
| `r2p-start` | 从文本或文件启动 run。 | `"<requirement>"` 或 `--file <path>`；`[--repo-path <dir>] [--separate]` |
| `r2p-continue` | 将活动 run 推进到下一步动作。 | 无 |
| `r2p-status` | 查看活动 run 或全部 run。 | `[--all]` |
| `r2p-switch` | 选择另一个 run。 | `--work-id <id>` |
| `r2p-tier-lock` | 确认复杂度 tier。 | `--work-id <id> --base light\|standard --confirm`；`[--modifiers <a,b,...>] [--override-floor]` |
| `r2p-reopen` | 从较早阶段创建子 run，并归档源 run。 | `--from <work-id> --stage <stage> --reason "<text>"` |
| `r2p-abandon` | 明确放弃并归档尚未完成的 open draft。 | `--work-id <id> --reason "<text>"` |
| `r2p-gap-open` | 在 open run 中路由上游决策缺口。 | `--work-id <id> --owner-stage <stage> --required-action "<text>"` |
| `r2p-gap-resolve` | 关闭已修复的 gap route。 | `--work-id <id> --route-id <id>` |
| `r2p-execute` | 执行获批 PLAN，或恢复执行。 | `[--work-id <id>] [--profile strict\|fast]` |
| `r2p-archive` | 归档 closed 或 executing run。 | `[--work-id <id>] [--force]` |

`r2p-execute` 和 `r2p-archive` 在省略 `--work-id` 时使用活动 run。新执行默认采用
`strict`；`fast` 的资格确认参数见[执行 PLAN](#executing-a-plan)。

Tier modifier 包括 `migration`、`cross_project`、`safety`、`dependency` 和
`scope_expanding`。`--override-floor` 允许在明确确认后选择低于计算下限的 tier。
`--separate` 可在已有 run 仍打开时创建独立 run。

阶段值为 `raw_requirement`、`requirement_brief`、`risk_discovery`、`design`、`spec`
和 `plan`。gap 的 `--owner-stage` 必须严格位于当前阶段上游。`--required-action` 以及
reopen/abandon 的 reason 必须保持单行；required action 和 abandonment reason 还必须
非空。gap 命令通过校验后就会修改 run 状态。

## Lifecycle commands

在终端中用 `r2p` 管理已安装集成。`r2p status` 查看安装状态；`r2p-status` 查看工作流 run。

| Command | Purpose |
|---|---|
| `r2p install [--platform <id,...>]` | 安装或刷新集成，默认全部平台。 |
| `r2p uninstall [--platform <id,...>]` | 移除受管集成并恢复用户备份，默认全部平台。 |
| `r2p status [--json]` | 只读查看已安装版本、缺失文件和 manifest 问题。 |
| `r2p version` | 打印包版本。 |
| `r2p help` | 查看生命周期命令帮助。 |

例如，输出机器可读状态或卸载一个集成：

```bash
r2p status --json
r2p uninstall --platform claude
```

工作流命令使用 `R2P_JSON=1` 输出机器可读结果；生命周期 status 使用 `--json`。

## How the workflow works

每个 run 在 `.req-to-plan/<work-id>/` 下依次产出这些文档：

| Stage | Artifact | Purpose |
|---|---|---|
| Raw requirement | `00-raw-requirement.md` | 保留原始需求。 |
| Requirement brief | `03-requirement-brief.md` | 明确范围、排除项和验收方向。 |
| Risk discovery | `04-risk-discovery.md` | 识别未知点、约束和依赖。 |
| DESIGN | `05-design.md` | 确定技术方案。 |
| SPEC | `06-spec.md` | 定义行为与接口。 |
| PLAN | `07-plan.md` | 排列实现任务及其验证方式。 |

`02-project-context.md` 提供仓库事实。Tier 和 modifier 决定文档深度及评审要求。
PLAN gate 检查追踪闭环，确保范围、SPEC 项和风险都有明确覆盖。后续阶段不能悄悄推迟
requirement brief 纳入范围的工作。

如果 open run 发现上游决策缺失，使用 `r2p-gap-open` 路由回负责阶段，修复后用
`r2p-gap-resolve` 关闭路线。PLAN checkpoint 获批后，run 进入
`closed_at_plan_checkpoint`，可以执行、重开或归档。

## Executing a PLAN

PLAN 获批后，通过 agent 集成调用 `r2p-execute`。执行会留在当前分支并创建任务
commit，不创建分支或 worktree，不 push，也不打开 pull request。

> [!IMPORTANT]
> 执行要求宿主能够派发 subagent，且 `.req-to-plan/` 以外的代码工作区干净。
> 该范围内的已跟踪改动和未被忽略的未跟踪文件会使启动以 exit `6` 停止。
> 请先处理这些改动；工作流不得为了通过检查而提交无关文件。

默认 `strict` 模式采用 Spec-Driven Development（SDD）循环：

1. **Pre-flight**：通读 PLAN，在派发前解决矛盾。
2. **实现**：全新 subagent 通过 TDD 实现一个任务、验证结果，只提交自己的改动。
3. **评审与修复**：task-reviewer 检查 SPEC 覆盖和代码质量；修复并复审，直到
   Critical 与 Important 发现全部解决。
4. **最终评审**：评审整个执行区间，重跑完整验证套件；最终修复后仍需重复验证和评审。
5. **归档**：完成任务标记并记录 `Verdict: Approved`，随后归档。已记录的 verdict
   是审计证据，本身不会执行测试。

**可选 fast 模式。** 在开始前请求 `r2p-execute --profile fast`。它先只读检查已锁定的
LIGHT tier、无 modifier，以及每个任务都有 prerequisite v2，返回 `fast_profile_review`。
agent 还必须逐任务确认改动局部、机械、无歧义，文件边界安全，验证可确定执行。
满足条件后使用 `--profile fast --confirm-fast-eligible`；不满足则使用
`--profile fast --reject-fast-ineligible --reason "<text>"` 拒绝。

Fast 先记录任务已实现，由 primary final reviewer 承担逐任务评审责任。完整最终验证
仍然必需；发现风险、歧义或未解决问题时，只能单向升级到 `strict`。没有 prerequisite
声明的旧 PLAN 使用 strict v1；混合或格式错误的声明会阻止启动。

<details>
<summary>执行控制协议与指标</summary>

agent 撰写报告正文，controller 通过 CLI 维护结构化进度和观测记录。这些是实现接口，
使用工作流的人无需额外手动执行。

| Wrapper | Controller responsibility |
|---|---|
| `r2p-task-brief` | 生成角色交接所用的任务 brief。 |
| `r2p-prerequisite-check` | 仅在 implementer 派发前立即检查 prerequisite，不放入普通提交后 `Verification`。 |
| `r2p-progress` | 使用 `begin`、`complete`、`recover` 或 `escalate`，配合 `--expected-sequence` 记录角色派发/结果、恢复证据或升级模式。 |
| `r2p-context-view --work-id <id> --with-stats` | 各角色自行读取语义上下文；controller 不转发正文，也不持久化上下文包。 |
| `r2p-metrics-status`、`r2p-metrics-append`、`r2p-metrics-ack`、`r2p-metrics-finalize` | 观测已完成角色、重试待处理观测、确认持久完成状态，并校验完整覆盖。 |

- **进度是权威来源。** 恢复会返回 journal 记录的角色、任务、fix wave 和 sequence。
  已派发但未完成的角色返回 `recover_role_result`，应恢复其结果，不自动重新派发。
  原始任务 commit 区间保持不变；reviewer 使用返回的每个 `review_ranges` 条目，纳入
  单独记录的任务修复和最终修复。
- **重试保留证据。** 解决 `BLOCKED` / `NEEDS_CONTEXT` 后，用新 sequence 重试同一
  角色、任务和 fix wave。保留 TDD red 与失败检查；最终批准要求各命令的最新结果通过，
  且包含完整套件。任务修复报告与评审保留完全一致、位于代码围栏外的 `Fix Wave N` 行。
- **指标不决定角色，也不阻塞恢复。** 权威进度转换完成后才追加观测。精确重试请求保存为
  `pending_completion.record_json`，append/ack 重试具有幂等性。指标最终化要求待处理
  完成记录已确认，完整 journal 的角色覆盖精确匹配。失败报告 `metrics_incomplete`，
  不阻塞有效进度、恢复或归档；缺失观测仍明确记录为缺口。
- **字节与 Token 分开衡量。** 角色将汇总 `semantic_bytes` 作为 `context_bytes` 返回，
  同时使用 `context_mode=semantic_view` 和 `semantic_payload_bytes`。汇总值包含来源
  标题和分隔符，不含统计前缀，与逐来源计数之和不同。缺失的模型、时间或 Token 数据
  保持 `unavailable`；不能把字节数和耗时换算成已实现的 Token 节省。

</details>

## Run storage and recovery

Run 保存在 workspace 中；安装好的集成保存在 agent home 中。

| Workspace path | Purpose |
|---|---|
| `.req-to-plan/.workflow-active` | 当前选择的 run 指针。 |
| `.req-to-plan/<work-id>/run.md` | 状态、阶段、checkpoint 和恢复上下文。 |
| `.req-to-plan/<work-id>/logs/` | 生成的 brief、diff 和诊断输出。 |
| `.req-to-plan/<work-id>/execution/` | 本地进度、指标、任务报告/评审和最终评审证据。 |
| `.req-to-plan/archive/<work-id>/` | 已归档 run 目录。 |

Run 文档纳入 Git 跟踪。活动指针、logs、execution 证据、临时
`.execution-start-transaction.json` owner 和 archive 目录被 Git 忽略。迁移中断的 run
时应保留 workspace 内的本地执行证据；仅有 Git checkout 不包含这些审计记录。

关闭 PLAN checkpoint 和归档时，会尝试提交 `.req-to-plan/.gitignore` 与该 run 路径
内的变更。不运行 `git add -A`，不强制添加被忽略的文件，也不 push。执行阶段的任务
commit 留在当前分支。

**恢复：** 对同一个 run 再次调用 `r2p-execute`。strict 模式中已完成的实现会从评审
继续，即使指标缺失也一样。旧 run 中已提交但没有角色检查点的工作，需要通过
`r2p-progress recover` 提供精确 HEAD 和持久化 DONE/BASE..HEAD 报告，不能只根据
commit 历史推断。缺少 profile 和指标的旧 run 以 strict 恢复，并明确记录观测不完整。

**重开或放弃：** `r2p-reopen` 从指定阶段创建子 run，子 run 持久化后才归档直接源 run。
同一 lineage 只允许一个活动的 reopened run。源记录或同 lineage 记录格式错误时，
操作会在写入前停止。明确放弃 open draft 时使用 `r2p-abandon`；closed/executing run
使用 `r2p-archive`。

**执行残留：** 重试 `r2p-execute` 以恢复中断的启动过程或继续执行。closed run 如果
还存在 `execution/` 或 execution-start owner，不能常规归档；`--force` 仅用于明确
放弃或已被替代的执行。它不会让符号链接或非目录的 execution 路径变得安全。

## Troubleshooting

| Symptom | Next action |
|---|---|
| `ModuleNotFoundError: No module named 'yaml'` | 将 `pyyaml` 安装到 agent shell 选择的 Python，检查其 `PATH`，尤其是使用虚拟环境时。 |
| 安装状态正常，但 run 停住了 | `r2p status` 检查集成；使用 `r2p-status` 并按 run 打印的 `next:` 动作处理。 |
| 执行因工作区不干净而停止 | 检查 `git status --short -- ':!.req-to-plan'`，处理代码改动后再重试。 |
| 恢复返回 `recover_role_result` | 恢复已记录 invocation 的结果；任何重试前先确认它是否仍在运行。 |
| Fast preflight 拒绝 run | 处理资格检查发现，或显式选择 `strict`；结构检查通过不代表任务语义已获批。 |
| Closed run 因执行残留不能归档 | 用 `r2p-execute` 恢复/继续，或明确使用 `--force` 归档；不要为了通过检查而删除证据。 |

## Development

从源码 checkout 创建虚拟环境并安装测试依赖。如果已有配置好的 `.venv`，直接复用：

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m pytest tests/ -q
```

`npm run test:local` 同样使用 `.venv/bin/python`；`npm test` 使用 `PATH` 中的
`python`。CI 在 Python 3.11 和 3.12 上运行套件。Python 3.10 的本地 venv 会跳过
依赖 `tomllib` 的测试；这些跳过不能替代 CI 证据。

以下检查不会向真实 agent home 安装：

```bash
.venv/bin/python -m pytest tests/test_docs_consistency.py tests/test_readme.py -q
node bin/r2p.js version
node bin/r2p.js help
.venv/bin/python -m tools.workflow_cli --help
.venv/bin/python -m tools.workflow_cli.agent_shortcuts --help
```

| Path | Responsibility |
|---|---|
| `bin/r2p.js` | 调用 Python 生命周期 CLI 的轻量 Node 入口。 |
| `tools/r2p-*` | 安装到 agent home 的可执行 wrapper 源脚本。 |
| `tools/workflow_cli/` | 状态机、gate、执行协议、上下文视图和安装器。 |
| `tools/workflow_cli/agent_templates/` | Claude、Codex、Gemini 的源模板；OpenCode 从 Claude 派生。 |
| `tests/` | 隔离的 CLI、恢复、安装、打包和文档检查。 |

命令或行为变更时，同步维护两种语言的 README。项目工程规范见
[AGENTS.md](AGENTS.md) 和 [CLAUDE.md](CLAUDE.md)。

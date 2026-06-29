[English](README.md) | 简体中文

# req-2-plan

[![npm version](https://img.shields.io/npm/v/%40xenonbyte%2Freq-2-plan.svg)](https://www.npmjs.com/package/@xenonbyte/req-2-plan)
[![node](https://img.shields.io/node/v/%40xenonbyte%2Freq-2-plan.svg)](https://nodejs.org)
[![license: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](./LICENSE)

> 把原始需求变成一份获批、执行器中立的实现 PLAN，再在原地把这份 PLAN 执行落地，并在 Claude Code、Codex、Gemini、opencode 上一致运行。

`req-2-plan` 为 AI coding agent 安装 `r2p` 工作流，分两个阶段工作。**规划（Plan）：**
把粗略需求推进到一条分阶段、门控的流程中——**requirement brief**、**risk discovery**、
**DESIGN**、**SPEC**、**PLAN**——让最终计划有上下文、有审查记录、可直接执行。
**执行（Execute）：** 随后 `r2p-execute` 把这份获批 PLAN 接入当前分支上、由 subagent
编排的原地实现循环——每个任务一个 implementer、每个任务后一次 review、最后一次整分支
评审，然后自动归档——让规划这次改动的工具也能把它落地。

这个 npm 包是生命周期安装器。目前它支持 4 个 agent 平台：**Claude Code**、**Codex**、
**Gemini**、**opencode**。它从一份共享源生成各平台的 agent 入口，安装共享的
`r2p-*` wrapper，并维护 owned manifest，确保卸载时只移除 `r2p` 自己管理的文件。

**Contents:** [Why r2p](#why-r2p) · [Features](#features) · [Installation](#installation) · [Quick start](#quick-start) · [Workflow commands](#workflow-commands) · [Executing a PLAN](#executing-a-plan) · [Development](#development)

## Why r2p

AI agent 执行很快，但模糊需求容易变成含糊计划、隐藏范围决策和反复返工。`r2p`
把规划阶段显式化：

- 原始需求会作为真值来源被保留；
- 风险和未知点会在实现计划前暴露；
- DESIGN、SPEC、PLAN 都要通过结构化 quality gate；
- 必须由人选择的决定会被记录，而不是由 agent 猜；
- 执行可以直接从 PLAN 开始——手动执行，或用 `r2p-execute`——不需要重新决定范围。

当需求不只是单行修改、会影响重要行为，或需要在多个 agent 之间做稳定交接时，适合使用它。

## Features

- **分阶段 requirement-to-PLAN 工作流**：requirement brief、risk discovery、DESIGN、SPEC、PLAN。
- **Quality gate 与 checkpoint**：每个阶段交接前都要先通过校验。
- **支持 4 个平台**：为 Claude Code（`claude`）、Codex（`codex`）、Gemini（`gemini`）、opencode（`opencode`）安装匹配入口。
- **单一生命周期 CLI**：`r2p install`、`r2p uninstall`、`r2p status`、`r2p version`、`r2p help`。
- **Manifest-backed 安装安全**：覆盖前备份已存在文件，卸载只删除受管路径。
- **Project Context Pack**：以真实仓库事实（默认当前目录，或用 `--repo-path <dir>`）支撑 tier 估算和 PLAN 校验。
- **修复路径**：可重开 closed run、路由上游缺口，并关闭已修复的决策路线。
- **原地执行 PLAN**：`r2p-execute` 在当前分支上通过 subagent 驱动的 SDD 循环执行获批 PLAN——每个任务一个全新 implementer、每个任务后接 task-reviewer 与 fix 循环，最后一次整分支评审会重跑完整验证套件，通过后 run 自动归档。它要求宿主能派发 subagent，且从不 push 或开 PR。

## Supported platforms

`r2p` 当前支持 4 个平台。`--platform` 使用下表里的 platform ID。

| Agent platform | Platform ID | Installed surface |
|---|---|---|
| Claude Code | `claude` | `skills/r2p/SKILL.md` plus `commands/r2p-*.md` |
| Codex | `codex` | `skills/r2p-*/SKILL.md` |
| Gemini | `gemini` | `commands/r2p-*.toml` |
| opencode | `opencode` | `commands/r2p-*.md` |

## Installation

环境要求：

- Node.js 18+
- Python 3，以 `python3` 或 `python` 提供

全局安装：

```bash
npm install -g @xenonbyte/req-2-plan
```

检查生命周期 CLI：

```bash
r2p version
r2p status
r2p help
```

> [!NOTE]
> 生命周期命令只使用 Python 标准库。日常 workflow wrapper 使用 `pyyaml`；在 checkout
> 内可运行 `python3 -m pip install --user -r requirements.txt`，或直接运行
> `python3 -m pip install --user "pyyaml>=6.0"`。

安装全部支持的 agent 集成。不传 `--platform` 时，这就是默认行为：

```bash
r2p install
```

用 `--platform` 只安装指定平台：

```bash
r2p install --platform claude
r2p install --platform claude,codex,gemini,opencode
```

> [!WARNING]
> `r2p install` 会覆盖所选平台的既有 `r2p` 安装。已存在的用户文件会先备份，
> `r2p uninstall` 也只会移除 install manifest 里记录的路径。

## Quick start

安装平台 skill 后，在 agent 里启动一次工作流：

```text
/r2p-start "Add rate limiting"
/r2p-continue
```

也可以从需求文件启动，而不是传内联文本：

```text
/r2p-start --file change-req.md
```

tier 估算和 Project Context Pack 默认以当前目录为基准。传 `--repo-path <dir>`
可改为以另一个仓库为基准——例如跨项目需求里的目标仓库。

工作流会在需要人或 agent 动作时停下：锁定 tier、填写 artifact、修复 quality gate、
批准 checkpoint、执行 subagent review，或解决 gap。按输出里的 `next:` 命令执行，
然后继续运行 `r2p-continue`。

> [!TIP]
> 把 `~/.req-to-plan/bin` 加入 `PATH`，即可直接运行 wrapper：
>
> ```bash
> export PATH="$HOME/.req-to-plan/bin:$PATH"
> ```

## Workflow commands

安装后，面向 agent 的命令会调用 `~/.req-to-plan/bin` 下的共享 wrapper。各命令的用途与
参数如下——可选参数标注默认值，`—` 表示必须自行提供：

| Command | Purpose | Parameter | 必填 / 可选 | 默认值 |
|---|---|---|---|---|
| `r2p-start` | 启动新 run，并基于仓库扫描给出 tier 建议。 | `<requirement>` 或 `--file <path>` | 二选一必填 | — |
| | | `--repo-path <dir>` | 可选 | 当前目录 |
| | | `--separate` | 可选 | 关 |
| `r2p-continue` | 把活动 run 推进到下一个停点，并打印精确的 `next:` 动作。 | *(无)* | — | — |
| `r2p-status` | 只读查看 run，不改状态。 | `--all` | 可选 | 关 |
| `r2p-switch` | 把活动 run 标记指向另一个 run。 | `--work-id <id>` | 必填 | — |
| `r2p-tier-lock` | 锁定活动 run 的复杂度 tier。 | `--work-id <id>` | 必填 | — |
| | | `--base light\|standard` | 必填 | — |
| | | `--confirm` | 必填 | — |
| | | `--modifiers <a,b,…>` | 可选 | 无 |
| | | `--override-floor` | 可选 | 关 |
| `r2p-reopen` | 重开一个 closed 或 executing run 以修复上游 artifact。 | `--from <work-id>` | 必填 | — |
| | | `--stage <stage>` | 必填 | — |
| | | `--reason <text>` | 必填 | — |
| `r2p-gap-open` | 在 open run 上把上游决策缺口路由回 owner stage。 | `--work-id <id>` | 必填 | — |
| | | `--owner-stage <stage>` | 必填 | — |
| | | `--required-action "<text>"` | 必填 | — |
| `r2p-gap-resolve` | 关闭已修复的上游缺口 route。 | `--work-id <id>` | 必填 | — |
| | | `--route-id <id>` | 必填 | — |
| `r2p-archive` | 把 closed run 归档出活动工作区。 | `--work-id <id>` | 可选 | 活动 run |
| | | `--force` | 可选 | 关 |
| `r2p-execute` | 原地执行 closed PLAN，做整分支评审，然后归档。 | `--work-id <id>` | 可选 | 活动 run |

说明：`--modifiers` 接受 `migration`、`cross_project`、`safety`、`dependency`、
`scope_expanding` 的逗号分隔子集。`--stage` 与 `--owner-stage` 取流水线阶段
（`raw_requirement` … `plan`）；gap 的 `--owner-stage` 须严格位于当前阶段上游，
`--required-action` 须为单行。`--confirm` 才会让 tier 锁定真正生效，`--override-floor`
允许锁到计算下限以下。`--separate` 可在已有 run 仍打开时另起一个并行 run。`--force`
让 `r2p-archive` 能归档 PLAN-TASK 未全部勾选的 executing run。

大多数 run 只需要 `r2p-start`，然后反复 `r2p-continue`。当工作流输出这些命令，
或你明确需要切换、修复、重开、执行、归档时，再使用对应的专用命令。

> [!IMPORTANT]
> `r2p-execute` 假设宿主 agent 能派发 subagent。它直接在当前分支工作，不会 push，
> 也不会打开 pull request。

> [!NOTE]
> 在 PLAN checkpoint 关闭 run，以及归档 run 时，`r2p` 会对该 run 的
> `.req-to-plan/<work-id>` 状态做 best-effort、path-limited commit。它不会运行
> `git add -A`，不会强制添加 ignored path，也不会 push。

## Lifecycle commands

在终端里使用生命周期命令管理已安装的集成：

```bash
r2p install
r2p install --platform codex

r2p status
r2p status --json

r2p uninstall --platform claude
r2p uninstall

r2p version
r2p help
```

`r2p install` 和 `r2p uninstall` 省略 `--platform` 时，都会作用于全部支持平台。

`r2p status` 是只读命令。加 `--json` 后会输出机器可读的平台状态、已安装版本和 manifest
问题。

## How the workflow works

每个 run 都保存在目标 workspace 的 `.req-to-plan/<work-id>/` 下。agent 负责语义内容；
CLI 负责状态、文件、gate 和结构化校验。

| Stage | Output |
|---|---|
| Raw requirement | 原始用户需求 |
| Requirement brief | 范围、目标、非目标和验收方向 |
| Risk discovery | 未知点、约束、依赖和风险区域 |
| DESIGN | 技术方案和 decision requests |
| SPEC | 详细行为和接口 |
| PLAN | 带 verification criteria 的有序实现任务 |

Standard tier 的 DESIGN/SPEC/PLAN 阶段可能要求 subagent review，尤其当存在
`migration`、`safety`、`cross_project` 等 tier modifier 时。如果后续阶段发现上游决策缺口，
用 `r2p-gap-open` 路由回 owner stage，修复后再用 `r2p-gap-resolve` 关闭 route。

## Executing a PLAN

`r2p` 不止步于 PLAN。run 在 PLAN checkpoint 关闭后，`r2p-execute` 会在当前分支上原地
实现它——不开新分支、不建 worktree、不 push。它假设宿主 agent 能派发 subagent，否则
显式失败。

这个循环采用 Spec-Driven Development（SDD）：

- **Pre-flight**：先通读一遍 PLAN，在动工前把任何矛盾或缺陷一次性抛给你；上游缺陷会
  路由回某个阶段重开，而不是在执行里打补丁。
- **逐任务**：一个全新 implementer subagent 在 TDD 下只实现一个 PLAN-TASK，只提交自己
  改动的文件并回报；随后 task-reviewer 对照 SPEC 与该任务的验证标准检查，fix 循环清掉
  Critical 与 Important 发现后才勾选该任务。
- **整分支评审**：全部任务完成后，由最强模型上的 final reviewer 在整个执行区间上重跑
  完整验证套件，并把 PLAN 当作清单逐条核对。这次评审就是合并门槛。
- **自动归档**：final review 干净地给出 `Verdict: Approved`，`r2p-execute` 才会归档该
  run。commit 留在当前分支；`push` 和 pull request 仍需你单独显式请求。

进度持久记录在 `execution/progress.md`。run 被打断后，直接对同一个 run 再次运行
`r2p-execute` 即可：它会识别出 `executing` 状态，从第一个未勾选的任务继续，既不会重跑
已完成的任务，也不会从头再来。若无法重建被打断任务的起点，它会停下来询问你，而不是瞎猜。

## Development

安装开发依赖：

```bash
python3 -m pip install -r requirements-dev.txt
```

运行测试套件：

```bash
npm test
# or, when using the checked-in virtual environment:
npm run test:local
```

常用本地检查：

```bash
node bin/r2p.js version
node bin/r2p.js help
.venv/bin/python -m tools.workflow_cli --help
.venv/bin/python -m tools.workflow_cli.agent_shortcuts --help
```

项目结构：

| Path | Purpose |
|---|---|
| `bin/r2p.js` | 调用 Python 生命周期 CLI 的 npm binary |
| `tools/r2p-*` | 已安装 workflow wrapper 的源脚本 |
| `tools/workflow_cli/` | 状态机、gate、template、installer 和命令路由 |
| `tools/workflow_cli/agent_templates/` | 面向 Claude Code、Codex、Gemini 的生成入口 |
| `tests/` | 覆盖 CLI 行为、状态、gate、安装安全、打包和 README 一致性的回归测试 |

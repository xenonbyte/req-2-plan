[English](README.md) | 简体中文

# req-2-plan

[![npm version](https://img.shields.io/npm/v/%40xenonbyte%2Freq-2-plan.svg)](https://www.npmjs.com/package/@xenonbyte/req-2-plan)
[![node](https://img.shields.io/node/v/%40xenonbyte%2Freq-2-plan.svg)](https://nodejs.org)
[![license: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](./LICENSE)

> 把原始需求变成一份获批、执行器中立的实现 PLAN——同一套分阶段工作流，在 Claude Code、Codex、Gemini 上一致运行。

`req-2-plan` 为 AI agent 平台安装并管理 `r2p` 需求到 PLAN 的工作流。该工作流是一条
分阶段、门控的流水线：需求依次经过 **requirement brief → risk discovery → DESIGN →
SPEC → PLAN**，每个阶段都要先过一道 quality gate 和一个人工/主控 checkpoint 才能交给
下游。产出是一份另一个 agent 或工程师无需重新决策范围就能执行的计划。

这个 npm 包是安装器：它从一份共享源生成各平台的 agent skill 与命令，并安装进
Claude Code、Codex、Gemini，让工作流在三个平台上表现一致。

## Features

- **分阶段、门控流水线**——每个阶段交接前都通过一道 quality gate 和一个 checkpoint；不靠猜推进。
- **单一生命周期 CLI**——`r2p install`、`r2p uninstall`、`r2p status`、`r2p version`、`r2p help`，只依赖 Python 标准库。
- **一份源、多平台**——为 `claude`、`codex`、`gemini` 生成 skill。
- **owned-only、manifest 背书的安装**——卸载只删 `r2p` 创建的文件；已存在的用户文件会被备份并保留。
- **紧凑的 agent 技能**——八个 `r2p-*` wrapper 驱动日常循环。

## Supported platforms

| 平台 | 技能格式 |
|---|---|
| `claude` | 命令文件（`commands/r2p-*.md`） |
| `codex` | 技能目录（`skills/r2p-*/SKILL.md`） |
| `gemini` | 命令 TOML（`commands/r2p-*.toml`） |

## Installation

环境要求：**Node.js 18+** 与 **Python 3**（以 `python3` 或 `python` 提供）。

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
> 生命周期命令只需 Python 标准库，但日常 `r2p-*` 技能依赖 `pyyaml`。在仓库 checkout
> 内用 `python3 -m pip install --user -r requirements.txt` 安装，或直接
> `python3 -m pip install --user "pyyaml>=6.0"`。

`r2p install` 把各平台模板写入对应 agent 的 home 目录、在 `~/.req-to-plan/bin/` 下写入
共享命令 wrapper，并生成 `~/.req-to-plan/install/<platform>.yaml` 清单。清单记录每个
受管路径，因此卸载只移除 `r2p` 创建的文件，并为安装前已存在的文件还原备份。

## Usage

### Quick start

先在终端用生命周期 CLI 安装平台技能并确认安装结果：

```bash
r2p install   # 安装全部平台（默认）
r2p status    # 查看已安装情况
```

然后在 agent 里驱动工作流——已安装的平台技能会调用 `r2p-*` 包装器
（如需在终端手动执行，先把 `~/.req-to-plan/bin` 加入 `PATH`，见下方 tip）：

```text
/r2p-start --repo-path . "Add rate limiting"    # 需求为内联文本
/r2p-start --repo-path . --file change-req.md   # 需求为文档文件
/r2p-continue                                   # 逐阶段推进
```

需求可以是内联文本，也可以用 `--file <path>` 传入文档（两者互斥）。
**只要需求以某个代码仓库为上下文，就必须传 `--repo-path`**——当前项目传 `.`，
跨仓库需求传目标仓库路径；它生成的 Project Context Pack 是 tier 估算与 PLAN
文件引用校验的真值锚点。选项写在需求文本之前（如上例），这样即使自由文本
引号写错也不会吞掉选项。若 standard tier 的 PLAN gate 提示 Context Pack
缺失/不可用，直接执行 gate 打印的
`PYTHONPATH=... <python> -m tools.workflow_cli context-build ...` 命令中途补建
（不存在独立的 `context-build` 可执行文件）。

### Lifecycle commands

安装全部平台、单个平台，或逗号分隔的列表：

```bash
r2p install
r2p install --platform claude
r2p install --platform claude,codex,gemini
```

按平台报告安装状态——已装版本、漂移（缺文件或版本不匹配）、或 manifest 无效。`status`
只读；加 `--json` 得到机器可读输出：

```bash
r2p status
r2p status --json
```

卸载单个平台、列表，或全部（省略 `--platform`）：

```bash
r2p uninstall --platform claude
r2p uninstall --platform claude,codex,gemini
```

> [!WARNING]
> `r2p install` 直接覆盖已有安装——无需确认参数。覆盖前会先备份已存在的用户文件，
> 而卸载绝不删除非 `r2p` 创建的文件。

### Workflow skills

安装后，平台 skill 调用这些共享的 `r2p-*` wrapper——运行一次工作流的每一步各一个：

| Skill | 作用 |
|---|---|
| `r2p-start` | 从需求启动一次新运行（文本，或用 `--file <path>` 读取文档内容）。 |
| `r2p-continue` | 继续当前运行——推进到下一个停点（gate、checkpoint 或修复）。 |
| `r2p-status` | 查看当前运行或全部运行，只读。 |
| `r2p-switch` | 把活动运行指向另一个 `--work-id`。 |
| `r2p-tier-lock` | 锁定活动运行的复杂度 tier（`--base light\|standard`）。 |
| `r2p-reopen` | 从指定 `--stage` 重开一个已关闭的运行。 |
| `r2p-gap-open` | 把 open run 的上游缺口路由回其 `--owner-stage`；下游 artifact 失效、需重新派生。 |
| `r2p-gap-resolve` | owner 阶段重做并通过 `gate-quality` 后，关闭一个 `--route-id` 缺口路由。 |

> [!TIP]
> 把 `~/.req-to-plan/bin` 加入 `PATH`，即可直接运行 `r2p-*` wrapper：
>
> ```bash
> export PATH="$HOME/.req-to-plan/bin:$PATH"
> ```

### When to use which skill

大多数运行只需 `r2p-start`，然后反复 `r2p-continue`。其余技能针对特定情形。

**锁定 tier**——每个 run 一次，当 `r2p-continue` 停在 `tier_not_locked` 时：

```bash
r2p-tier-lock --work-id <id> --base standard --modifiers migration,safety --confirm
```

`--base standard` 抬高刚性下限；`migration`、`safety`、`cross_project` 这几个 modifier
会在 DESIGN / SPEC / PLAN 检查点强制子 agent 审查。

**重开已关闭的 run**——回到一个已在 PLAN 检查点关闭的运行，从更早的阶段重新开始
（会派生一个带血缘的新 run）：

```bash
r2p-reopen --from <closed-id> --stage spec --reason "spec gap found"
```

**回路上游缺口**——在一个**开着的** run 上，当后面的阶段发现更早的阶段拥有一个错误或
缺失的决策时。`gap-open` 把 run 退回 owner 阶段并把所有下游标记 stale；待你把 owner
重做到通过 `gate-quality`，`gap-resolve` 关闭路由，让 owner 可被重新批准、下游重新派生：

```bash
r2p-gap-open --work-id <id> --owner-stage design --required-action "fixed-window burst flaw"
# 然后把 owner 阶段重做到通过 gate-quality（r2p-continue 会引导这步）
r2p-gap-resolve --work-id <id> --route-id R-1
```

> [!NOTE]
> reopen 针对**已关闭**的 run；gap 路由针对**开着**的 run。`r2p-continue` 会用
> `needs_repair` 和 `needs_gap_resolve` 停点带你走完这两种修复流程。

> [!NOTE]
> **人工决策点（standard DESIGN）。** 当 standard tier 的 DESIGN 涉及必须由人
> 决定的选择（引入新依赖、迁移策略、API 兼容性）时，agent 会在 `## Decision
> Requests` 章节写入 `### DECISION-NNN` block（含 `Question:`/`Options:`/
> `Recommended:`）并标记 `Status: pending` ——存在 pending 决策时
> `gate-quality` 会失败，直到人选定方案、block 改为 `Status: selected`
> 并补上 `Selected:` 与 `Rationale:` 行。
> 无需人工决策时，该章节须恰好写 `none`。

## License

[MIT](./LICENSE) © xenonbyte

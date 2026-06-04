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
- **紧凑的 agent 快捷命令**——`r2p-start`、`r2p-continue`、`r2p-status`、`r2p-switch`、`r2p-reopen`、`r2p-tier-lock` 驱动日常循环。

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
> 生命周期命令只需 Python 标准库，但日常 `r2p-*` 快捷命令依赖 `pyyaml`。在仓库 checkout
> 内用 `python3 -m pip install --user -r requirements.txt` 安装，或直接
> `python3 -m pip install --user "pyyaml>=6.0"`。

`r2p install` 把各平台模板写入对应 agent 的 home 目录、在 `~/.req-to-plan/bin/` 下写入
共享命令 wrapper，并生成 `~/.req-to-plan/install/<platform>.yaml` 清单。清单记录每个
受管路径，因此卸载只移除 `r2p` 创建的文件，并为安装前已存在的文件还原备份。

## Usage

### Quick start

```bash
r2p install                       # 安装全部平台（默认）
r2p-start "Add rate limiting"     # 启动一次工作流
r2p-continue                      # 逐阶段推进
r2p status                        # 查看已安装情况
```

### Commands

安装全部平台、单个平台，或逗号分隔的列表：

```bash
r2p install
r2p install --platform claude
r2p install --platform claude,codex,gemini
```

通过 skill 调用的共享 `r2p-*` wrapper 推进一次运行：

```bash
r2p-start "Add rate limiting"
# 或从需求文档启动（读取文件内容，不是路径）：
r2p-start --file ./requirement.md
r2p-continue
r2p-status
r2p-switch --work-id WF-YYYYMMDD-slug
r2p-tier-lock --work-id WF-YYYYMMDD-slug --base light --confirm
r2p-reopen --from WF-YYYYMMDD-slug --stage spec --reason "Fix upstream gap"
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

## Configuration

> [!TIP]
> 把 `~/.req-to-plan/bin` 加入 `PATH`，即可在 shell 里直接运行 `r2p-*` 快捷命令：
>
> ```bash
> export PATH="$HOME/.req-to-plan/bin:$PATH"
> ```

每次运行的工作流 artifact 存放在工作目录下的 `.req-to-plan/<work-id>/`。

工作流的权威说明——背景、目标、架构与各阶段质量模型——见
[`docs/req-to-plan-design.md`](docs/req-to-plan-design.md)。机器事实（exit code、状态、
tier 表、命令与参数名）由 `tools/workflow_cli/` 下的代码拥有；确切命令语法以 `--help`
为准。

## Troubleshooting

| 现象 | 处理 |
|---|---|
| `Error: Unknown platform(s)` | `--platform` 只接受 `claude`、`codex`、`gemini`（逗号分隔）。省略它即针对全部。 |
| `ModuleNotFoundError: yaml` | 日常快捷命令需要 `pyyaml`：`python3 -m pip install --user "pyyaml>=6.0"`。 |
| `r2p status` 报 `invalid` | 该平台 manifest 被截断或形状错误。重装：`r2p install --platform <name>`。 |
| 找不到 `r2p-*` 快捷命令 | 把 `~/.req-to-plan/bin` 加入 `PATH`（见 [Configuration](#configuration)）。 |

## License

[MIT](./LICENSE) © xenonbyte

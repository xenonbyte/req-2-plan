English | [简体中文](README.zh-CN.md)

# req-2-plan

[![npm version](https://img.shields.io/npm/v/%40xenonbyte%2Freq-2-plan.svg)](https://www.npmjs.com/package/@xenonbyte/req-2-plan)
[![node](https://img.shields.io/node/v/%40xenonbyte%2Freq-2-plan.svg)](https://nodejs.org)
[![license: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](./LICENSE)

> Turn a raw requirement into an approved, executor-neutral implementation PLAN across Claude Code, Codex, and Gemini.

`req-2-plan` installs the `r2p` workflow for AI coding agents. It takes a rough
requirement through a staged, gated process - **requirement brief**, **risk
discovery**, **DESIGN**, **SPEC**, and **PLAN** - so the final plan is grounded,
reviewed, and ready for another agent or engineer to execute.

The npm package is the lifecycle installer. It currently supports three agent
platforms - **Claude Code**, **Codex**, and **Gemini**. From one shared source it
generates platform-specific agent skills, installs the shared `r2p-*` wrappers,
and keeps an owned manifest so uninstall only removes files managed by `r2p`.

**Contents:** [Why r2p](#why-r2p) · [Features](#features) · [Installation](#installation) · [Quick start](#quick-start) · [Workflow commands](#workflow-commands) · [Development](#development)

## Why r2p

AI agents are fast at implementation, but weak requirements tend to leak into
ambiguous plans, hidden scope choices, and repeated rework. `r2p` makes the
planning phase explicit:

- the requirement is preserved as the source of truth;
- risks and unknowns are surfaced before implementation planning;
- DESIGN, SPEC, and PLAN each pass structural quality gates;
- human decisions are recorded instead of guessed;
- execution can start from a PLAN without re-deciding scope.

Use it when the requirement is more than a one-line edit, when a change touches
important behavior, or when you want a durable handoff between agents.

## Features

- **Staged requirement-to-PLAN workflow**: requirement brief, risk discovery, DESIGN, SPEC, and PLAN.
- **Quality gates and checkpoints**: each stage must clear validation before handoff.
- **Three supported platforms**: installs matching surfaces for Claude Code (`claude`), Codex (`codex`), and Gemini (`gemini`).
- **One lifecycle CLI**: `r2p install`, `r2p uninstall`, `r2p status`, `r2p version`, and `r2p help`.
- **Manifest-backed install safety**: pre-existing files are backed up, and uninstall removes only managed paths.
- **Project Context Pack**: `--repo-path` captures real repository facts for tiering and PLAN checks.
- **Repair paths**: reopen closed runs, route upstream gaps, and resolve repaired decisions.
- **Execution handoff**: `r2p-execute` can drive an approved PLAN through an in-place implementation loop.

## Supported platforms

`r2p` currently supports 3 platforms. Use the platform ID with `--platform`.

| Agent platform | Platform ID | Installed surface |
|---|---|
| Claude Code | `claude` | `skills/r2p/SKILL.md` plus `commands/r2p-*.md` |
| Codex | `codex` | `skills/r2p-*/SKILL.md` |
| Gemini | `gemini` | `commands/r2p-*.toml` |

## Installation

Requirements:

- Node.js 18+
- Python 3 as `python3` or `python`

Install the package globally:

```bash
npm install -g @xenonbyte/req-2-plan
```

Check the lifecycle CLI:

```bash
r2p version
r2p status
r2p help
```

> [!NOTE]
> Lifecycle commands use only the Python standard library. Daily workflow
> wrappers use `pyyaml`; from a checkout, install it with
> `python3 -m pip install --user -r requirements.txt`, or directly with
> `python3 -m pip install --user "pyyaml>=6.0"`.

Install all supported agent integrations. This is the default when `--platform`
is omitted:

```bash
r2p install
```

Install only selected platforms with `--platform`:

```bash
r2p install --platform claude
r2p install --platform claude,codex,gemini
```

> [!WARNING]
> `r2p install` overwrites an existing `r2p` install for the selected platform(s).
> Existing user files are backed up first, and `r2p uninstall` removes only paths
> recorded in the install manifest.

## Quick start

Install the platform skills, then start a workflow from your agent:

```text
/r2p-start --repo-path . "Add rate limiting"
/r2p-continue
```

Start from a requirement file instead of inline text:

```text
/r2p-start --repo-path . --file change-req.md
```

For repositories used as requirement context, pass `--repo-path`. Use `.` for the
current repository or a path to the target repository for cross-project work.
This builds the Project Context Pack used by tier estimation and PLAN reference
checks.

The workflow stops whenever it needs a human or agent action: tier lock,
artifact content, quality-gate repair, checkpoint approval, subagent review, or
gap resolution. Run the printed `next:` command exactly, then resume with
`r2p-continue`.

> [!TIP]
> Add `~/.req-to-plan/bin` to your `PATH` to run the wrappers directly:
>
> ```bash
> export PATH="$HOME/.req-to-plan/bin:$PATH"
> ```

## Workflow commands

After installation, the agent-facing commands call shared wrappers under
`~/.req-to-plan/bin`.

| Command | Purpose |
|---|---|
| `r2p-start` | Start a new run from inline requirement text or `--file <path>`. |
| `r2p-continue` | Advance the active run to the next stop or completed state. |
| `r2p-status` | Inspect the active run, or all runs with `--all`, without changing state. |
| `r2p-switch` | Select a different active `--work-id`. |
| `r2p-tier-lock` | Lock the tier with `--base light\|standard` and optional modifiers. |
| `r2p-reopen` | Reopen a closed or executing run from a specific stage. |
| `r2p-gap-open` | Route an upstream gap on an open run back to the owner stage. |
| `r2p-gap-resolve` | Close a repaired upstream-gap route. |
| `r2p-archive` | Move a closed run under `.req-to-plan/archive/` and untrack its active path. |
| `r2p-execute` | Execute a closed PLAN in place on the current branch, then archive the run. |

Most runs only need `r2p-start` and repeated `r2p-continue`. Use the specialized
commands when the workflow prints them or when you intentionally need to switch,
repair, reopen, execute, or archive a run.

> [!IMPORTANT]
> `r2p-execute` assumes the host agent can dispatch subagents. It works on the
> current branch and does not push or open pull requests.

> [!NOTE]
> Closing a run at the PLAN checkpoint and archiving a run perform best-effort,
> path-limited commits for that run's `.req-to-plan/<work-id>` state. They never
> run `git add -A`, never force-add ignored paths, and never push.

## Lifecycle commands

Use lifecycle commands from a terminal to manage installed integrations:

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

Omitting `--platform` targets all supported platforms for both `r2p install` and
`r2p uninstall`.

`r2p status` is read-only. With `--json`, it reports machine-readable platform
state, installed version, and manifest issues.

## How the workflow works

Every run lives in `.req-to-plan/<work-id>/` inside the target workspace. The
agent writes semantic content; the CLI owns state, files, gates, and structured
validation.

| Stage | Output |
|---|---|
| Raw requirement | Original user requirement |
| Requirement brief | Scope, goals, non-goals, and acceptance direction |
| Risk discovery | Unknowns, constraints, dependencies, and risk areas |
| DESIGN | Technical approach and decision requests |
| SPEC | Detailed behavior and interfaces |
| PLAN | Ordered implementation tasks with verification criteria |

Standard-tier DESIGN/SPEC/PLAN stages can require subagent review, especially
when tier modifiers such as `migration`, `safety`, or `cross_project` are
present. If a later stage discovers an upstream decision gap, use
`r2p-gap-open`, repair the owner stage, then close the route with
`r2p-gap-resolve`.

## Development

Install development dependencies:

```bash
python3 -m pip install -r requirements-dev.txt
```

Run the test suite:

```bash
npm test
# or, when using the checked-in virtual environment:
npm run test:local
```

Useful local checks:

```bash
node bin/r2p.js version
node bin/r2p.js help
.venv/bin/python -m tools.workflow_cli --help
.venv/bin/python -m tools.workflow_cli.agent_shortcuts --help
```

Project layout:

| Path | Purpose |
|---|---|
| `bin/r2p.js` | npm binary that invokes the Python lifecycle CLI |
| `tools/r2p-*` | installed workflow wrapper scripts |
| `tools/workflow_cli/` | state machine, gates, templates, installer, and command routing |
| `tools/workflow_cli/agent_templates/` | generated surfaces for Claude Code, Codex, and Gemini |
| `tests/` | regression tests for CLI behavior, state, gates, install safety, packaging, and README consistency |

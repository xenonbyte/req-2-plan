English | [简体中文](README.zh-CN.md)

# req-2-plan

[![npm version](https://img.shields.io/npm/v/%40xenonbyte%2Freq-2-plan.svg)](https://www.npmjs.com/package/@xenonbyte/req-2-plan)
[![node](https://img.shields.io/node/v/%40xenonbyte%2Freq-2-plan.svg)](https://nodejs.org)
[![license: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](./LICENSE)

> Turn a raw requirement into an approved, executor-neutral implementation PLAN — the same staged workflow across Claude Code, Codex, and Gemini.

`req-2-plan` installs and manages the `r2p` requirement-to-PLAN workflow for AI
agent platforms. The workflow is a staged, gated pipeline: a requirement moves
through **requirement brief → risk discovery → DESIGN → SPEC → PLAN**, and each
stage must clear a quality gate and a human/main checkpoint before it hands off.
The result is a plan another agent or engineer can execute without re-deciding
scope.

The npm package is an installer. From one shared source it generates per-platform
agent skills and commands and installs them into Claude Code, Codex, and Gemini,
so the workflow behaves identically on all three.

## Features

- **Staged, gated pipeline** — every stage clears a quality gate and a checkpoint before handoff; nothing advances on a guess.
- **One lifecycle CLI** — `r2p install`, `r2p uninstall`, `r2p status`, `r2p version`, `r2p help`, using only the Python standard library.
- **Multi-platform from one source** — generates skills for `claude`, `codex`, and `gemini`.
- **Owned-only, manifest-backed install** — uninstall removes only files `r2p` created; pre-existing user files are backed up and preserved.
- **Compact agent shortcuts** — `r2p-start`, `r2p-continue`, `r2p-status`, `r2p-switch`, `r2p-reopen`, `r2p-tier-lock` drive the daily loop.

## Supported platforms

| Platform | Skill format |
|---|---|
| `claude` | Command files (`commands/r2p-*.md`) |
| `codex` | Skill directories (`skills/r2p-*/SKILL.md`) |
| `gemini` | Command TOML (`commands/r2p-*.toml`) |

## Installation

Requirements: **Node.js 18+** and **Python 3** (available as `python3` or `python`).

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
> The lifecycle commands need only the Python standard library, but the daily
> `r2p-*` shortcuts depend on `pyyaml`. Install it from a checkout with
> `python3 -m pip install --user -r requirements.txt`, or directly with
> `python3 -m pip install --user "pyyaml>=6.0"`.

`r2p install` writes platform templates into each agent's home directory, shared
command wrappers under `~/.req-to-plan/bin/`, and a manifest at
`~/.req-to-plan/install/<platform>.yaml`. The manifest records every managed path
so uninstall removes only files `r2p` created and restores backups for files that
existed beforehand.

## Usage

### Quick start

```bash
r2p install                       # install all platforms (default)
r2p-start "Add rate limiting"     # start a workflow run
r2p-continue                      # advance it stage by stage
r2p status                        # see what is installed
```

### Commands

Install all platforms, one platform, or a comma-separated list:

```bash
r2p install
r2p install --platform claude
r2p install --platform claude,codex,gemini
```

Drive a run through the shared `r2p-*` wrappers the skills call:

```bash
r2p-start "Add rate limiting"
# or start from a requirement document (reads the file contents, not the path):
r2p-start --file ./requirement.md
r2p-continue
r2p-status
r2p-switch --work-id WF-YYYYMMDD-slug
r2p-tier-lock --work-id WF-YYYYMMDD-slug --base light --confirm
r2p-reopen --from WF-YYYYMMDD-slug --stage spec --reason "Fix upstream gap"
```

Report install status per platform — installed version, drift (missing files or
version mismatch), or an invalid manifest. `status` is read-only; add `--json`
for machine-readable output:

```bash
r2p status
r2p status --json
```

Uninstall one platform, a list, or all (omit `--platform`):

```bash
r2p uninstall --platform claude
r2p uninstall --platform claude,codex,gemini
```

> [!WARNING]
> `r2p install` overwrites an existing install — no confirmation flag is needed.
> Pre-existing user files are backed up before any overwrite, and uninstall never
> deletes a file `r2p` did not create.

## Configuration

> [!TIP]
> Add `~/.req-to-plan/bin` to your `PATH` to run the `r2p-*` shortcuts directly:
>
> ```bash
> export PATH="$HOME/.req-to-plan/bin:$PATH"
> ```

Workflow artifacts for each run live under `.req-to-plan/<work-id>/` in your
working directory.

The authoritative description of the workflow — background, goals, architecture,
and the per-stage quality model — is in
[`docs/req-to-plan-design.md`](docs/req-to-plan-design.md). Machine facts (exit
codes, statuses, tier tables, command and flag names) are owned by the code under
`tools/workflow_cli/`; consult `--help` for exact command syntax.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `Error: Unknown platform(s)` | `--platform` accepts only `claude`, `codex`, `gemini` (comma-separated). Omit it to target all. |
| `ModuleNotFoundError: yaml` | The daily shortcuts need `pyyaml`: `python3 -m pip install --user "pyyaml>=6.0"`. |
| `r2p status` reports `invalid` | The platform manifest is truncated or wrong-shaped. Reinstall it: `r2p install --platform <name>`. |
| `r2p-*` shortcuts not found | Add `~/.req-to-plan/bin` to `PATH` (see [Configuration](#configuration)). |

## License

[MIT](./LICENSE) © xenonbyte

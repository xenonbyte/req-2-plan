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
- **Compact agent skills** — eight `r2p-*` wrappers drive the daily loop.

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
> `r2p-*` skills depend on `pyyaml`. Install it from a checkout with
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
r2p install                                   # install all platforms (default)
r2p-start "Add rate limiting" --repo-path .   # start a run grounded in this repo's facts
r2p-continue                                  # advance it stage by stage
r2p status                                    # see what is installed
```

Pass `--repo-path .` whenever the requirement targets the current project (use the
target repo's path for cross-repo work); it generates the Project Context Pack that
grounds tier estimation and PLAN file-reference checks. If a standard-tier PLAN gate
later reports a missing or unusable Context Pack, build it mid-run with
the `PYTHONPATH=... <python> -m tools.workflow_cli context-build ...` command printed
by the gate (there is no standalone `context-build` executable).

### Lifecycle commands

Install all platforms, one platform, or a comma-separated list:

```bash
r2p install
r2p install --platform claude
r2p install --platform claude,codex,gemini
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

### Workflow skills

After install, the platform skills call these shared `r2p-*` wrappers — one per
step of running a workflow:

| Skill | What it does |
|---|---|
| `r2p-start` | Start a new run from a requirement (text, or `--file <path>` to read a document's contents). |
| `r2p-continue` | Continue the active run — advance it to its next stop (gate, checkpoint, or repair). |
| `r2p-status` | Inspect the current run, or all runs, read-only. |
| `r2p-switch` | Point the active run at a different `--work-id`. |
| `r2p-tier-lock` | Lock the active run's complexity tier (`--base light\|standard`). |
| `r2p-reopen` | Reopen a closed run from a specific `--stage`. |
| `r2p-gap-open` | Route an upstream gap on an open run back to its `--owner-stage`; downstream artifacts become stale and must be re-derived. |
| `r2p-gap-resolve` | Close a gap `--route-id` after the owner stage is re-worked and passes `gate-quality`. |

> [!TIP]
> Add `~/.req-to-plan/bin` to your `PATH` to run the `r2p-*` wrappers directly:
>
> ```bash
> export PATH="$HOME/.req-to-plan/bin:$PATH"
> ```

### When to use which skill

Most runs only need `r2p-start`, then repeated `r2p-continue`. The other skills
cover specific situations.

**Lock the tier** — once per run, when `r2p-continue` stops with `tier_not_locked`:

```bash
r2p-tier-lock --work-id <id> --base standard --modifiers migration,safety --confirm
```

`--base standard` raises the rigor floor; the `migration`, `safety`, and
`cross_project` modifiers force a subagent review at the DESIGN / SPEC / PLAN
checkpoints.

**Reopen a closed run** — revisit a run that was closed at the PLAN checkpoint,
restarting from an earlier stage (this seeds a new linked run):

```bash
r2p-reopen --from <closed-id> --stage spec --reason "spec gap found"
```

**Route an upstream gap** — on an *open* run, when a later stage finds that an
earlier stage owns a wrong or missing decision. `gap-open` sends the run back to
the owner stage and marks everything downstream stale; after you re-work the
owner past `gate-quality`, `gap-resolve` closes the route so the owner can be
re-approved and the downstream re-derived:

```bash
r2p-gap-open --work-id <id> --owner-stage design --required-action "fixed-window burst flaw"
# then re-work the owner stage until it passes gate-quality (r2p-continue guides this)
r2p-gap-resolve --work-id <id> --route-id R-1
```

> [!NOTE]
> Reopen is for a *closed* run; gap routing is for an *open* one. `r2p-continue`
> walks you through both repair flows with `needs_repair` and `needs_gap_resolve`
> stops.

## License

[MIT](./LICENSE) © xenonbyte

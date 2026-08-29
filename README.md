English | [简体中文](README.zh-CN.md)

# req-2-plan

[![npm version](https://img.shields.io/npm/v/%40xenonbyte%2Freq-2-plan.svg)](https://www.npmjs.com/package/@xenonbyte/req-2-plan)
[![node](https://img.shields.io/node/v/%40xenonbyte%2Freq-2-plan.svg)](https://nodejs.org)
[![license: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](./LICENSE)

> Turn a raw requirement into an approved, executor-neutral implementation PLAN - then execute that PLAN in place - across Claude Code, Codex, Gemini, and opencode.

`req-2-plan` installs the `r2p` workflow for AI coding agents, and it works in
two phases. **Plan:** it takes a rough requirement through a staged, gated
process - **requirement brief**, **risk discovery**, **DESIGN**, **SPEC**, and
**PLAN** - so the final plan is grounded, reviewed, and ready to execute.
**Execute:** `r2p-execute` then drives that approved PLAN through an in-place,
subagent-orchestrated implementation loop on your current branch - one
implementer per task, a reviewer after each, a whole-branch final review, then
auto-archive - so the same tool that planned the change can also land it.

The npm package is the lifecycle installer. It currently supports four agent
platforms - **Claude Code**, **Codex**, **Gemini**, and **opencode**. From one
shared source it generates platform-specific agent surfaces, installs the shared
`r2p-*` wrappers, and keeps an owned manifest so uninstall only removes files
managed by `r2p`.

**Contents:** [Why r2p](#why-r2p) · [Features](#features) · [Installation](#installation) · [Quick start](#quick-start) · [Workflow commands](#workflow-commands) · [Executing a PLAN](#executing-a-plan) · [Development](#development)

## Why r2p

AI agents are fast at implementation, but weak requirements tend to leak into
ambiguous plans, hidden scope choices, and repeated rework. `r2p` makes the
planning phase explicit:

- the requirement is preserved as the source of truth;
- risks and unknowns are surfaced before implementation planning;
- DESIGN, SPEC, and PLAN each pass structural quality gates;
- human decisions are recorded instead of guessed;
- execution runs straight from the PLAN - by hand or via `r2p-execute` - without re-deciding scope.

Use it when the requirement is more than a one-line edit, when a change touches
important behavior, or when you want a durable handoff between agents.

## Features

- **Staged requirement-to-PLAN workflow**: requirement brief, risk discovery, DESIGN, SPEC, and PLAN.
- **Quality gates and checkpoints**: each stage must clear validation before handoff.
- **Four supported platforms**: installs matching surfaces for Claude Code (`claude`), Codex (`codex`), Gemini (`gemini`), and opencode (`opencode`).
- **One lifecycle CLI**: `r2p install`, `r2p uninstall`, `r2p status`, `r2p version`, and `r2p help`.
- **Manifest-backed install safety**: pre-existing files are backed up, and uninstall removes only managed paths.
- **Project Context Pack**: real repository facts (the current directory by default, or `--repo-path <dir>`) ground tiering and PLAN checks.
- **Repair paths**: reopen closed runs, route upstream gaps, and resolve repaired decisions.
- **In-place PLAN execution**: `r2p-execute` runs the approved PLAN on your current branch through a subagent-driven SDD loop - a fresh implementer per task, a task-reviewer and fix loop after each, then a whole-branch final review that re-runs the full verification suite before the run auto-archives. Subagent dispatch is required, and it never pushes or opens pull requests.

## Supported platforms

`r2p` currently supports 4 platforms. Use the platform ID with `--platform`.

| Agent platform | Platform ID | Installed surface |
|---|---|---|
| Claude Code | `claude` | `skills/r2p/SKILL.md` plus `commands/r2p-*.md` |
| Codex | `codex` | `skills/r2p-*/SKILL.md` |
| Gemini | `gemini` | `commands/r2p-*.toml` |
| opencode | `opencode` | `commands/r2p-*.md` |

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
r2p install --platform claude,codex,gemini,opencode
```

> [!WARNING]
> `r2p install` overwrites an existing `r2p` install for the selected platform(s).
> Existing user files are backed up first, and `r2p uninstall` removes only paths
> recorded in the install manifest.

## Quick start

Install the platform skills, then start a workflow from your agent:

```text
/r2p-start "Add rate limiting"
/r2p-continue
```

Start from a requirement file instead of inline text:

```text
/r2p-start --file change-req.md
```

Tier estimation and the Project Context Pack are grounded in the current
directory by default. Pass `--repo-path <dir>` to ground them in a different
repository instead - for example, a target repository for cross-project work.

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
`~/.req-to-plan/bin`. Each command, its purpose, and its parameters - optional
parameters show their default; `—` means you must supply the value:

| Command | Purpose | Parameter | Required / optional | Default |
|---|---|---|---|---|
| `r2p-start` | Start a new run and propose a tier from a repo scan. | `<requirement>` or `--file <path>` | one required | — |
| | | `--repo-path <dir>` | optional | current directory |
| | | `--separate` | optional | off |
| `r2p-continue` | Advance the active run and print the exact `next:` action. | *(none)* | — | — |
| `r2p-status` | Inspect runs without changing state. | `--all` | optional | off |
| `r2p-switch` | Point the active-run marker at another run. | `--work-id <id>` | required | — |
| `r2p-tier-lock` | Lock the active run's complexity tier. | `--work-id <id>` | required | — |
| | | `--base light\|standard` | required | — |
| | | `--confirm` | required | — |
| | | `--modifiers <a,b,…>` | optional | none |
| | | `--override-floor` | optional | off |
| `r2p-reopen` | Reopen a closed or executing run to repair an upstream artifact. | `--from <work-id>` | required | — |
| | | `--stage <stage>` | required | — |
| | | `--reason <text>` | required | — |
| `r2p-gap-open` | Route an upstream decision gap on an open run back to its owner stage. | `--work-id <id>` | required | — |
| | | `--owner-stage <stage>` | required | — |
| | | `--required-action "<text>"` | required | — |
| `r2p-gap-resolve` | Close a repaired upstream-gap route. | `--work-id <id>` | required | — |
| | | `--route-id <id>` | required | — |
| `r2p-archive` | Archive a closed run out of the active workspace. | `--work-id <id>` | optional | active run |
| | | `--force` | optional | off |
| `r2p-execute` | Execute a closed PLAN in place, run a whole-branch review, then archive. | `--work-id <id>` | optional | active run |

Notes: `--modifiers` takes a comma-separated subset of `migration`,
`cross_project`, `safety`, `dependency`, `scope_expanding`. `--stage` and
`--owner-stage` take a pipeline stage (`raw_requirement` … `plan`); a gap's
`--owner-stage` must be strictly upstream of the current stage, and
`--required-action` must be a single line. `--confirm` is what makes the tier
lock take effect, and `--override-floor` allows locking below the computed
floor. `--separate` starts a parallel run while another is still open. `--force`
lets `r2p-archive` archive an executing run whose PLAN-TASKs are not all checked
off.

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

## Executing a PLAN

`r2p` does not stop at the PLAN. Once a run is closed at the PLAN checkpoint,
`r2p-execute` implements it in place on your current branch - no new branch, no
worktree, no push. It assumes the host agent can dispatch subagents and fails
explicitly if it cannot.

The loop is Spec-Driven Development (SDD):

- **Pre-flight**: read the PLAN once and batch any contradiction or defect to you
  before work starts; an upstream defect routes back to a stage reopen, never a
  patch in execution.
- **Per task**: a fresh implementer subagent builds exactly one PLAN-TASK under
  TDD, commits only its own files, and reports back; a task-reviewer checks it
  against the SPEC and the task's verification criteria, and a fix loop clears
  Critical and Important findings before the task's checkbox flips.
- **Whole-branch review**: once every task is done, a final reviewer on the most
  capable model re-runs the full verification suite over the entire execution
  range and walks the PLAN as a checklist. This review is the merge gate.
- **Auto-archive**: a clean `Verdict: Approved` final review lets `r2p-execute`
  archive the run. Commits stay on your current branch; `push` and pull requests
  remain a separate, explicit request.

Progress is tracked durably in `execution/progress.md`. If a run is interrupted,
just run `r2p-execute` again on the same run: it detects the `executing` status,
continues from the first unchecked task, and never re-runs completed work or
restarts from scratch. If it cannot reconstruct where the interrupted task began,
it stops and asks you rather than guessing.

**Execution metrics (Phase 0).**

Normal `run-execute-start` creates `execution/metrics.md` alongside progress.
The controller owns this append-only observation ledger; it never participates
in run state, completion, resume, final-review, or archive gates. It records a
block for every role call with elapsed time, report bytes, verification records,
status, concerns, fix wave, and any model or Token value the platform actually
exposes. A missing model, timing, or Token value is written as `unavailable` —
bytes and elapsed time must never be presented as an estimated Token count.

Context bytes name the delivered payload kind: Phase 0 direct ACS uses
`declared_payload_bytes` (the raw UTF-8 bytes of the required sources), while a
future semantic view uses `semantic_payload_bytes`. These are auditable byte
measurements, not a claim about model-consumed context or Token usage.

The internal commands are intended for the controller and safe test tooling:
`execution-prerequisite-check --work-id <id> --task <N> --require-version 1`,
`execution-samples-validate` with exactly three absolute `--sample-dir` values,
and the narrowly scoped self-host exception
`execution-metrics-bootstrap --work-id WF-20260829-r2p-execute-token-phase-r2p --profile strict --self-hosted-gap-through-task 002`.
Run that bootstrap only after Task 002 has a clean review and before Task 003 is
dispatched; it records the known instrumentation gap without changing execution
correctness.

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

English | [简体中文](README.zh-CN.md)

# req-2-plan

[![npm version](https://img.shields.io/npm/v/%40xenonbyte%2Freq-2-plan.svg)](https://www.npmjs.com/package/@xenonbyte/req-2-plan)
[![node](https://img.shields.io/node/v/%40xenonbyte%2Freq-2-plan.svg)](https://nodejs.org)
[![license: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](./LICENSE)

> Turn a raw requirement into a reviewed implementation PLAN, then execute it on your current branch.

`req-2-plan` gives AI coding agents a staged workflow: clarify scope, surface
risks, record design decisions, define a SPEC, and produce an approved PLAN.
You can use the PLAN independently or run `r2p-execute` to implement, test,
review, and archive the change.

The npm package installs the shared Python CLI and agent integrations for
**Claude Code**, **Codex**, **Gemini**, and **opencode**. Run state stays in local
Markdown files; no database or server is required.

**Contents:** [Installation](#installation) · [Quick start](#quick-start) · [Workflow commands](#workflow-commands) · [Executing a PLAN](#executing-a-plan) · [Run storage and recovery](#run-storage-and-recovery) · [Troubleshooting](#troubleshooting) · [Development](#development)

## Why r2p

Use `r2p` for changes that need scope decisions, risk analysis, or a durable
handoff between agents. The original requirement remains available throughout
the workflow, and each stage passes an entry gate, a quality gate, and a human
checkpoint before the next stage begins.

The agent writes the requirement analysis and artifact prose. The CLI manages
state, structural templates, and validation; it does not generate the semantic
content or replace human judgment.

## Features

- **Repository context:** scan the target repository to ground tier estimates and the Project Context Pack in actual code, dependencies, and test commands.
- **Traceable planning:** connect scope, risks, DESIGN, SPEC, and PLAN tasks; declare exclusions in the requirement brief.
- **Gated handoffs:** record decisions and review evidence before advancing; reopen a run or route an upstream gap when a decision needs repair.
- **Reviewed execution:** use the default `strict` task review loop, or explicitly request `fast` for eligible mechanical work; both require final review and full verification.
- **Durable recovery:** resume from authoritative role checkpoints, with separate implementation and repair commit ranges.
- **Managed installation:** share executable wrappers across platforms, back up pre-existing user files, and uninstall only managed paths.

## Supported platforms

`r2p` currently supports 4 platforms. Use the platform ID with `--platform`.
Paths below are relative to each platform's default home.

| Agent platform | Platform ID | Default home | Installed surface |
|---|---|---|---|
| Claude Code | `claude` | `~/.claude/` | `skills/r2p/SKILL.md` and `commands/r2p-*.md` |
| Codex | `codex` | `~/.codex/` | `skills/r2p-*/SKILL.md` |
| Gemini | `gemini` | `~/.gemini/` | `commands/r2p-*.toml` |
| opencode | `opencode` | `~/.config/opencode/` | `commands/r2p-*.md`, derived from Claude templates |

Shared wrappers are installed under `~/.req-to-plan/bin`.

## Installation

You need Node.js 18+, Python available as `python3` or `python`, and Bash for
the workflow wrappers. Python 3.11 and 3.12 are tested in CI. PLAN execution
also requires Git and an agent host that can dispatch subagents.

Install `pyyaml` into the Python environment used by your agent's shell.
For a Python installation that supports user-site packages:

```bash
python3 -m pip install --user "pyyaml>=6.0"
```

Then install the npm package and your chosen integration:

```bash
npm install -g @xenonbyte/req-2-plan
r2p install --platform codex
r2p status
```

Use a comma-separated list to select several platforms, or omit `--platform`
to install all supported integrations:

```bash
r2p install --platform claude,codex,gemini,opencode
r2p install
```

> [!NOTE]
> Lifecycle commands use only the Python standard library; successful
> `r2p version` or `r2p status` does not verify that workflow dependencies are
> available. Wrappers prefer `python3` on `PATH`, then `python`. If you use a
> virtual environment, launch the agent with that environment on its `PATH`.

Reinstalling a platform refreshes its managed files. Existing user files are
backed up before overwrite and restored on uninstall. After upgrading the npm
package, rerun `r2p install` for the integrations you use.

## Quick start

Open your agent in the project workspace and invoke the installed `r2p-start`
command or skill. For hosts with slash commands:

```text
/r2p-start "Add rate limiting"
/r2p-continue
```

Or start from a requirement file:

```text
/r2p-start --file change-req.md
```

The current repository supplies context by default; `--repo-path <dir>` selects
a different repository for tier estimation and the Project Context Pack.

Follow the printed `next:` action to lock the tier, fill an artifact, repair a
gate, or review a checkpoint. Continue with `r2p-continue` until the PLAN is
approved. You can stop there or explicitly invoke `r2p-execute` to implement it.

To inspect or drive the shared wrappers from a terminal, add their directory
to `PATH`:

```bash
export PATH="$HOME/.req-to-plan/bin:$PATH"
r2p-status
```

The terminal wrappers manage workflow state and print the next action; the
agent integration supplies the artifact-writing and execution instructions.

## Workflow commands

These commands operate on runs in the current workspace. Brackets denote
optional arguments; `r2p-continue` usually supplies the exact next command.

| Command | Purpose | Arguments |
|---|---|---|
| `r2p-start` | Start a run from text or a file. | `"<requirement>"` or `--file <path>`; `[--repo-path <dir>] [--separate]` |
| `r2p-continue` | Advance the active run to its next action. | None |
| `r2p-status` | Inspect the active run, or all runs. | `[--all]` |
| `r2p-switch` | Select another run. | `--work-id <id>` |
| `r2p-tier-lock` | Confirm a complexity tier. | `--work-id <id> --base light\|standard --confirm`; `[--modifiers <a,b,...>] [--override-floor]` |
| `r2p-reopen` | Create a child run at an earlier stage and archive its source. | `--from <work-id> --stage <stage> --reason "<text>"` |
| `r2p-abandon` | Intentionally abandon and archive an unfinished open draft. | `--work-id <id> --reason "<text>"` |
| `r2p-gap-open` | Route an upstream decision gap on an open run. | `--work-id <id> --owner-stage <stage> --required-action "<text>"` |
| `r2p-gap-resolve` | Close a repaired gap route. | `--work-id <id> --route-id <id>` |
| `r2p-execute` | Execute an approved PLAN, or resume execution. | `[--work-id <id>] [--profile strict\|fast]` |
| `r2p-archive` | Archive a closed or executing run. | `[--work-id <id>] [--force]` |

`r2p-execute` and `r2p-archive` use the active run when `--work-id` is omitted.
A new execution defaults to `strict`; see [Executing a PLAN](#executing-a-plan)
for the `fast` eligibility confirmation flags.

Tier modifiers are `migration`, `cross_project`, `safety`, `dependency`, and
`scope_expanding`. `--override-floor` permits an explicitly confirmed tier
below the computed floor. `--separate` starts an independent run while another
is still open.

Stage values are `raw_requirement`, `requirement_brief`, `risk_discovery`,
`design`, `spec`, and `plan`. A gap's `--owner-stage` must be strictly upstream.
Keep `--required-action` and reopen/abandon reasons on one line; required actions
and abandonment reasons must also be non-blank. Gap commands change run state
once validation passes.

## Lifecycle commands

Use `r2p` from a terminal to manage installed integrations. `r2p status` checks
installation state; `r2p-status` checks workflow runs.

| Command | Purpose |
|---|---|
| `r2p install [--platform <id,...>]` | Install or refresh integrations; all platforms by default. |
| `r2p uninstall [--platform <id,...>]` | Remove managed integrations and restore user backups; all platforms by default. |
| `r2p status [--json]` | Read installed versions, missing files, and manifest issues. |
| `r2p version` | Print the package version. |
| `r2p help` | Show lifecycle command help. |

For example, inspect machine-readable status or remove one integration:

```bash
r2p status --json
r2p uninstall --platform claude
```

Use `R2P_JSON=1` for machine-readable workflow command output; lifecycle status
uses `--json` instead.

## How the workflow works

A run advances through these artifacts under `.req-to-plan/<work-id>/`:

| Stage | Artifact | Purpose |
|---|---|---|
| Raw requirement | `00-raw-requirement.md` | Preserve the original request. |
| Requirement brief | `03-requirement-brief.md` | Define scope, exclusions, and acceptance direction. |
| Risk discovery | `04-risk-discovery.md` | Identify unknowns, constraints, and dependencies. |
| DESIGN | `05-design.md` | Decide the technical approach. |
| SPEC | `06-spec.md` | Define behavior and interfaces. |
| PLAN | `07-plan.md` | Order implementation tasks and their verification. |

`02-project-context.md` supplies repository facts. Tier and modifiers determine
required detail and review checks. The PLAN gate checks trace closure so scope,
SPEC items, and risks have explicit coverage. Downstream stages cannot silently
defer work the requirement brief puts in scope.

If an open run discovers a missing upstream decision, route it with
`r2p-gap-open`, repair the owning stage, and close the route with
`r2p-gap-resolve`. Once the PLAN checkpoint is approved, the run is
`closed_at_plan_checkpoint`: ready for execution, reopening, or archival.

## Executing a PLAN

Invoke `r2p-execute` through the agent integration after PLAN approval.
Execution stays on the current branch and creates task commits; it does not
create a branch or worktree, push, or open a pull request.

> [!IMPORTANT]
> Execution requires subagent dispatch and a clean code worktree outside
> `.req-to-plan/`. Tracked changes and untracked, non-ignored files there block
> start with exit `6`. Resolve them before starting; the workflow must not
> commit unrelated work to clear the check.

The default `strict` loop follows Spec-Driven Development (SDD):

1. **Pre-flight:** read the PLAN and resolve contradictions before dispatch.
2. **Implement:** a fresh subagent implements one task with TDD, verifies it,
   and commits its own files.
3. **Review and repair:** a task-reviewer checks SPEC coverage and code quality;
   fix and re-review until Critical and Important findings are resolved.
4. **Final review:** review the entire execution range and rerun the full
   verification suite. Repeat after any final repair.
5. **Archive:** complete the task markers and record `Verdict: Approved`, then
   archive the run. A recorded verdict is audit evidence, not a test runner.

**Optional fast profile.** Request `r2p-execute --profile fast` before starting.
It first performs a read-only check for a locked LIGHT tier with no modifiers
and prerequisite v2 in every task, returning `fast_profile_review`. The agent
must also review every task for local, mechanical, unambiguous work with safe
file boundaries and deterministic verification. It then uses
`--profile fast --confirm-fast-eligible`, or rejects with
`--profile fast --reject-fast-ineligible --reason "<text>"`.

Fast records implemented tasks and gives the primary final reviewer the
per-task review responsibility. It keeps the full final verification requirement
and escalates one-way to `strict` when risk, ambiguity, or unresolved findings
require it. Legacy PLANs without prerequisite declarations use strict v1;
mixed or malformed declarations block start.

<details>
<summary>Execution controller protocol and metrics</summary>

Agents write report prose; the controller uses CLI commands for structural
progress and observations. These are implementation interfaces, not extra steps
for the person running the workflow.

| Wrapper | Controller responsibility |
|---|---|
| `r2p-task-brief` | Produce the task brief used in role handoffs. |
| `r2p-prerequisite-check` | Validate prerequisites immediately before implementer dispatch; never put this in ordinary post-commit `Verification`. |
| `r2p-progress` | Use `begin`, `complete`, `recover`, or `escalate` with `--expected-sequence` to persist dispatch/results, recover evidence, or escalate the profile. |
| `r2p-context-view --work-id <id> --with-stats` | Each role reads the semantic context itself; the controller does not relay the content or persist a context bundle. |
| `r2p-metrics-status`, `r2p-metrics-append`, `r2p-metrics-ack`, `r2p-metrics-finalize` | Observe completed roles, retry pending observations, acknowledge durable completion, and finalize coverage. |

- **Progress is authoritative.** Resume returns the journal's role, task, fix
  wave, and sequence. An inflight dispatch returns `recover_role_result`; recover
  its result rather than automatically dispatching it again. Original task
  commit ranges remain immutable; reviewers use every returned `review_ranges`
  entry to include the separate task/final repairs.
- **Retries preserve evidence.** Resolve `BLOCKED` / `NEEDS_CONTEXT`, then retry
  that role/task/fix wave with a new sequence. Preserve TDD red and failed checks;
  final approval requires each command's latest result to pass, including the
  full suite. Task repair reports and reviews retain the exact unfenced
  `Fix Wave N` line.
- **Metrics never choose a role or gate recovery.** Append only after the
  authoritative progress transition. The exact retry request is persisted as
  `pending_completion.record_json`; append/ack retries are idempotent. Metrics
  finalization requires acknowledged pending completions and exact role coverage
  for fully journaled runs. Failures report `metrics_incomplete` and do not block
  valid progress, resume, or archive. Missing observations stay explicit gaps.
- **Bytes are measured separately from Tokens.** Roles return aggregate
  `semantic_bytes` as `context_bytes`, with `context_mode=semantic_view` and
  `semantic_payload_bytes`. The aggregate includes source headings and separators,
  excludes the stats prefix, and differs from the sum of per-source counts.
  Missing model, timing, or Token data stays `unavailable`; byte counts and
  elapsed time must not be converted into claimed Token savings.

</details>

## Run storage and recovery

Runs live in the workspace; installed integrations live in your agent home.

| Workspace path | Purpose |
|---|---|
| `.req-to-plan/.workflow-active` | Selected run pointer. |
| `.req-to-plan/<work-id>/run.md` | Status, stage, checkpoints, and resume context. |
| `.req-to-plan/<work-id>/logs/` | Generated briefs, diffs, and diagnostic output. |
| `.req-to-plan/<work-id>/execution/` | Local progress, metrics, task reports/reviews, and final-review evidence. |
| `.req-to-plan/archive/<work-id>/` | Archived run directory. |

Run artifacts are tracked. The active pointer, logs, execution evidence,
transient `.execution-start-transaction.json` owner, and archive directory are
gitignored. Keep the workspace's local execution evidence when moving an
interrupted run; a Git checkout alone does not contain that audit trail.

Closing the PLAN checkpoint and archiving perform best-effort commits scoped
to `.req-to-plan/.gitignore` and that run's path. They do not run `git add -A`,
force-add ignored files, or push. Execution's task commits remain on the branch.

**Resume:** invoke `r2p-execute` again for the same run. A completed strict
implementation resumes at review even when metrics are absent. Older committed
work without a role checkpoint needs `r2p-progress recover` with the exact HEAD
and a durable DONE/BASE..HEAD report; commit history alone is not sufficient.
A profileless legacy run missing metrics resumes as strict with an explicit
incomplete-instrumentation gap.

**Reopen or abandon:** `r2p-reopen` creates a child at the requested stage, then
archives its direct source after the child is durable. Only one active reopened
run per lineage is allowed. Malformed source or same-lineage records block the
operation before writes. Use `r2p-abandon` when intentionally discarding an open
draft; closed/executing runs use `r2p-archive`.

**Execution residue:** retry `r2p-execute` to recover an interrupted start or
continue execution. A closed run with `execution/` or an execution-start owner
cannot be archived normally; `--force` is for intentionally abandoned or
superseded execution. It does not make symlinked or non-directory execution
paths safe.

## Troubleshooting

| Symptom | Next action |
|---|---|
| `ModuleNotFoundError: No module named 'yaml'` | Install `pyyaml` into the Python selected by the agent's shell; check its `PATH`, especially when using a virtual environment. |
| Installation looks healthy, but a run is paused | `r2p status` checks integrations. Use `r2p-status` and follow the run's printed `next:` action. |
| Start, progress, prerequisite, or metrics commands return exit `7` or `6` | `7` means the selected workspace/run directory is absent; execution start also uses it for a missing PLAN. `6` covers unsafe paths and damaged existing execution state, including missing recovery files. Check the work ID and restore the required state. |
| Execution stops with a dirty-worktree conflict | Inspect `git status --short -- ':!.req-to-plan'` and resolve your code changes before retrying. |
| Resume returns `recover_role_result` | Recover the recorded invocation's result; establish whether it is still running before any retry. |
| Fast preflight rejects the run | Address the eligibility finding or explicitly choose `strict`; structural eligibility alone cannot approve task semantics. |
| Archive rejects a closed run with execution residue | Resume/recover with `r2p-execute`, or intentionally archive with `--force`; do not delete the evidence just to clear the check. |

## Development

From a source checkout, create a virtual environment and install the test
dependencies. Reuse an existing `.venv` if one is already configured:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m pytest tests/ -q
```

`npm run test:local` also uses `.venv/bin/python`; `npm test` uses `python`
from `PATH`. CI runs the suite on Python 3.11 and 3.12. A local Python 3.10
venv skips the `tomllib`-dependent tests; those skips do not replace CI evidence.

Useful checks that do not install into real agent homes:

```bash
.venv/bin/python -m pytest tests/test_docs_consistency.py tests/test_readme.py -q
node bin/r2p.js version
node bin/r2p.js help
.venv/bin/python -m tools.workflow_cli --help
.venv/bin/python -m tools.workflow_cli.agent_shortcuts --help
```

| Path | Responsibility |
|---|---|
| `bin/r2p.js` | Thin Node launcher for the Python lifecycle CLI. |
| `tools/r2p-*` | Executable wrapper sources installed into agent homes. |
| `tools/workflow_cli/` | State machine, gates, execution protocol, context views, and installer. |
| `tools/workflow_cli/agent_templates/` | Source templates for Claude, Codex, and Gemini; OpenCode derives from Claude. |
| `tests/` | Isolated CLI, recovery, installation, packaging, and documentation checks. |

Keep both README languages aligned when commands or behavior change. Project
engineering guidance lives in [AGENTS.md](AGENTS.md) and [CLAUDE.md](CLAUDE.md).

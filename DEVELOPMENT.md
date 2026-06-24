# req-to-plan Development Guide

This is the tool-neutral development guide for contributors and agents working
on `req-to-plan`. Tool-specific entrypoints such as `AGENTS.md`, `CLAUDE.md`,
or a future `GEMINI.md` should point here instead of duplicating project facts.

## Architecture

`req-to-plan` turns a requirement into an executable PLAN through a gated
pipeline, then optionally executes that PLAN in place. The workflow stores state
on disk under `.req-to-plan/<work-id>/`; there is no database and no server.

**Pipeline.** A run advances stage by stage, each producing one numbered
artifact: RAW_REQUIREMENT (`00`) -> REQUIREMENT_BRIEF (`03`) ->
RISK_DISCOVERY (`04`) -> DESIGN (`05`) -> SPEC (`06`) -> PLAN (`07`). Each
stage clears an entry gate, then a quality gate plus a human checkpoint, before
the next stage is seeded. After PLAN, the run is
`CLOSED_AT_PLAN_CHECKPOINT`; from there it can go `EXECUTING` for in-place
task implementation, then `ARCHIVED`.

**State vs. artifacts.** `run.md` is owned by `state.py` and holds status,
stage, approved checkpoints, open routes, and resume context. Each
`NN-*.md` artifact is owned by `artifact.py` and carries YAML frontmatter for
version plus ready/stale flags.

**CLI vs. agent.** `cli.py` validates state and seeds structural templates.
`agent_shortcuts.py` exposes the higher-level `r2p-*` surface that agents
drive. Agents write semantic artifact content; the CLI does not generate
artifact prose.

**Distribution.** The project ships three entry surfaces: the Python CLI
(`python -m tools.workflow_cli`), `tools/r2p-*` shell wrappers used by installed
agent surfaces, and the npm binary `bin/r2p.js`, which delegates to
`install_cli` to install or uninstall per-platform agent templates from
`tools/workflow_cli/agent_templates/{claude,codex,gemini}`. opencode derives
commands from Claude's Markdown command templates and installs them under
`~/.config/opencode/commands/`.

Machine facts such as exit codes, statuses, allowed transitions, tier tables,
command names, and flags are owned by code under `tools/workflow_cli/`, not by
prose docs.

## Commands

Use the project `.venv` locally; system Python may lack PyYAML.

```bash
# Full suite
.venv/bin/python -m pytest tests/ -v

# One module
.venv/bin/python -m pytest tests/test_cli.py -v

# npm wrapper for the local test command
npm run test:local

# Run the workflow CLI directly
.venv/bin/python -m tools.workflow_cli --help

# Run the npm binary smoke path
bin/r2p.js version

# Install into a real agent home; this writes real ~/.req-to-plan state
.venv/bin/python -m tools.workflow_cli.install_cli install --platform claude
```

Never use bare `pytest` for local development. Do not use `npm install -g` to
develop this project.

## Module Map

| Module | Responsibility |
|---|---|
| `tools/workflow_cli/models.py` | Core types: `RunStatus`, `Stage`, `TierBase`, `TierModifier`, `TierEstimate`, `WorkId`, `ALLOWED_TRANSITIONS` |
| `tools/workflow_cli/state.py` | `RunStateManager`, `run.md` read/write, state transition validation |
| `tools/workflow_cli/artifact.py` | `ArtifactManager`, YAML frontmatter, ready/stale artifact flags |
| `tools/workflow_cli/tier.py` | Keyword scan, tier floor computation, tier estimation |
| `tools/workflow_cli/tier_keywords.yaml` | Keyword bank for tier modifiers |
| `tools/workflow_cli/repo_baseline.py` | Repo baseline scan: LOC, languages, monorepo/submodule signals |
| `tools/workflow_cli/context_pack.py` | Project Context Pack: deps, test commands, entrypoints, config, source dirs |
| `tools/workflow_cli/link_expander.py` | Local relative-link expansion for requirement intake |
| `tools/workflow_cli/stage_schema.py` | Required headings per stage/tier and PLAN task fields |
| `tools/workflow_cli/stage_templates.py` | Structural seed templates for stages |
| `tools/workflow_cli/markdown.py` | Fence-aware Markdown helpers |
| `tools/workflow_cli/atomic.py` | Atomic text writes for state, artifacts, and active pointer files |
| `tools/workflow_cli/trace.py` | Derived trace model and closure checks |
| `tools/workflow_cli/gates.py` | Entry gates, quality gates, execution completion gate, forced review checks |
| `tools/workflow_cli/output.py` | Exit code constants, output formatting, JSON mode |
| `tools/workflow_cli/cli.py` | Internal argparse router |
| `tools/workflow_cli/agent_shortcuts.py` | `r2p-*` shortcut surface and active pointer helpers |
| `tools/workflow_cli/install.py` | Install/uninstall/status service and manifest safety |
| `tools/workflow_cli/install_cli.py` | Lifecycle binary entrypoint |
| `tools/workflow_cli/agent_templates/` | Install templates for Claude, Codex, Gemini, and opencode-derived commands |

## Test Rules

- Isolate tests with `tempfile.TemporaryDirectory` and pass
  `base_path=Path(tmp)` to CLI or shortcut calls.
- Never touch real `~/.req-to-plan/` or the repo's own `.req-to-plan/` in
  tests.
- New behavior should get a focused test first, then implementation.
- Keep the full suite green; describe suite size qualitatively, not with a
  frozen count.
- `tests/test_docs_consistency.py` guards documentation drift and required
  agent-template guidance.

## Key Invariants

- Agent/CLI split: the CLI manages state, structure, and validation; agents
  generate semantic artifact content.
- Exit codes: `0` ok, `2` cli error, `3` gate fail, `4` dry run,
  `5` review required, `6` conflict, `7` not found.
- Terminal-for-open-run scanning: `agent_shortcuts.is_terminal()` treats
  `CLOSED_AT_PLAN_CHECKPOINT` and `ARCHIVED` as terminal.
- `EXECUTING` blocks starting a new run. `CLOSED_AT_PLAN_CHECKPOINT` is
  non-blocking for new runs and is reopen/execute/archive-able.
- Tier floor enforcement: `TierEstimate.lock()` raises when locking below the
  computed floor; override requires `--override-floor --confirm`.
- Manifest safety: uninstall only removes paths listed in `installed_paths`;
  pre-existing user files are backed up before overwrite.
- JSON mode: set `R2P_JSON=1` for machine-readable output.
- `run-close` at the PLAN checkpoint and `run-archive` make path-limited,
  best-effort git commits of `.req-to-plan/.gitignore` plus the run directory.
  They never use `git add -A`, never force-add ignored paths, and never push.

## State Machine Reference

Valid run status transitions are defined in `models.py` by
`ALLOWED_TRANSITIONS`.

```text
not_started -> active_stage_draft
active_stage_draft -> active_stage_draft | entry_gate_failed | quality_gate_failed | ready_for_checkpoint_review | upstream_gap_routing
entry_gate_failed -> active_stage_draft | upstream_gap_routing
quality_gate_failed -> active_stage_draft | upstream_gap_routing
ready_for_checkpoint_review -> active_stage_draft | checkpoint_review | upstream_gap_routing
checkpoint_review -> active_stage_draft | checkpoint_changes_requested | checkpoint_approved | upstream_gap_routing
checkpoint_changes_requested -> active_stage_draft | quality_gate_failed | upstream_gap_routing
upstream_gap_routing -> active_stage_draft | upstream_gap_routing | ready_for_checkpoint_review | checkpoint_approved
checkpoint_approved -> next_stage | closed_at_plan_checkpoint | upstream_gap_routing
next_stage -> active_stage_draft | entry_gate_failed
closed_at_plan_checkpoint -> executing | archived
executing -> executing | closed_at_plan_checkpoint | archived
archived -> none
```

## Artifact Filename Map

| Stage | File |
|---|---|
| `raw_requirement` | `00-raw-requirement.md` |
| `requirement_brief` | `03-requirement-brief.md` |
| `risk_discovery` | `04-risk-discovery.md` |
| `design` | `05-design.md` |
| `spec` | `06-spec.md` |
| `plan` | `07-plan.md` |

## Extending

**Add a CLI command.** Add the handler to `cli.py`, register it in the relevant
`_register_*_commands` function, use constants from `output.py`, and add tests
following the local `invoke()` helper pattern.

**Extend tier keywords.** Edit `tools/workflow_cli/tier_keywords.yaml`. Keep
the modifier groups (`migration`, `cross_project`, `safety`, `dependency`,
`scope_expanding`), add English and Chinese variants when applicable, and run
the focused tier tests.

## Repo Layout Notes

- `docs/` and `.req-to-plan/` are gitignored local state. Do not commit them.
- `.claude/skills/` is not a canonical development surface; keep shared project
  guidance in this file and keep tool-specific entrypoints thin.
- `.codegraph/` is local index state and is ignored.
- `.drfx/` holds archived local run artifacts, not source.

## Common Pitfalls

- Import PyYAML only where used; local checks must run through `.venv`.
- `print_and_exit` calls `sys.exit`; tests that call `cli.main()` should catch
  `SystemExit`.
- Use isolated `base_path` values in tests.
- Do not hardcode the package version in docs; `tools/workflow_cli/version.py`
  is the single source for `R2P_VERSION`.
- Do not duplicate this guide into tool-specific files. Add only the
  tool-specific loading behavior there.

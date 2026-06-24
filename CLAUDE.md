# req-to-plan — CLAUDE.md

## Architecture

req-to-plan turns a requirement into an executable PLAN through a gated
pipeline, then optionally executes that PLAN in place. The entire workflow is
filesystem state under `.req-to-plan/<work-id>/` — no database, no server.

**Pipeline.** A run advances stage by stage, each producing one numbered
artifact: RAW_REQUIREMENT (`00`) → REQUIREMENT_BRIEF (`03`) → RISK_DISCOVERY
(`04`) → DESIGN (`05`) → SPEC (`06`) → PLAN (`07`). Each stage clears an entry
gate, then a quality gate plus a human checkpoint, before the next is seeded.
After PLAN the run is `CLOSED_AT_PLAN_CHECKPOINT`; from there it can go
`EXECUTING` (in-place subagent-driven implementation of each PLAN-TASK) then
`ARCHIVED`. `reopen` forks a closed/executing run back to an earlier stage;
`gap-open`/`gap-resolve` route an upstream defect on an open run.

**State vs. artifacts.** `run.md` (owned by `state.py`) holds status, stage,
approved checkpoints, open routes, and resume context. Each `NN-*.md` artifact
(owned by `artifact.py`) carries YAML frontmatter (version + ready/stale).
`models.py` owns the enums plus `ALLOWED_TRANSITIONS` and
`ALLOWED_COMMANDS_BY_RUN_STATE`.

**CLI ⇄ Agent split.** `cli.py` is the internal command router — it validates
state and seeds structural templates only. `agent_shortcuts.py` is the
higher-level `r2p-*` surface the agent drives. The agent writes all semantic
artifact content; the CLI never does (see Key Invariants).

**Distribution.** Three entry surfaces: `python -m tools.workflow_cli` (the
Python CLI); `tools/r2p-*` shell wrappers that installed agent skills call; and
`bin/r2p.js`, the npm `r2p` binary that delegates to `install_cli` to install /
uninstall the per-platform skill templates (`agent_templates/{claude,codex,
gemini}`) into `~/.req-to-plan/`.

## Dev Commands

```bash
# Run all tests (must use .venv — system Python lacks PyYAML)
.venv/bin/python -m pytest tests/ -v

# Run a specific test module
.venv/bin/python -m pytest tests/test_cli.py -v

# Run the CLI directly
.venv/bin/python -m tools.workflow_cli --help
.venv/bin/python -m tools.workflow_cli run-start --work-id WF-20260527-test --requirement "Add rate limiting"

# Run agent shortcuts
.venv/bin/python -m tools.workflow_cli.agent_shortcuts start "Add rate limiting"

# Install r2p for a platform (uses real ~/.req-to-plan)
.venv/bin/python -m tools.workflow_cli.install_cli install --platform claude

# Tier estimate without a run
.venv/bin/python -m tools.workflow_cli tier-estimate --text "Migrate MySQL to PostgreSQL"
```

## Module Map

| Module | Responsibility |
|---|---|
| `tools/workflow_cli/models.py` | Core types: RunStatus, Stage, TierBase, TierModifier, TierEstimate, WorkId, ALLOWED_TRANSITIONS |
| `tools/workflow_cli/state.py` | RunStateManager (run.md read/write), state transition validation |
| `tools/workflow_cli/artifact.py` | ArtifactManager (produce/update/ready/mark_stale), YAML frontmatter |
| `tools/workflow_cli/tier.py` | scan_keywords (L1), compute_floor, estimate_tier (L1-L4) |
| `tools/workflow_cli/tier_keywords.yaml` | Keyword bank: 5 modifiers × zh+en entries |
| `tools/workflow_cli/repo_baseline.py` | Repo baseline scan: LOC, languages, monorepo/submodule signals |
| `tools/workflow_cli/context_pack.py` | Project Context Pack v1: deps, test commands, entrypoints, config files, source dirs |
| `tools/workflow_cli/link_expander.py` | Local relative-link expansion for requirement intake |
| `tools/workflow_cli/stage_schema.py` | STAGE_SCHEMA required headings per stage × tier; PLAN_TASK_FIELDS |
| `tools/workflow_cli/stage_templates.py` | Render STAGE_SCHEMA into per-stage/tier seed templates |
| `tools/workflow_cli/markdown.py` | Fence-aware Markdown helpers: unfenced lines, read-only strip, heading blocks |
| `tools/workflow_cli/atomic.py` | atomic_write_text: unique-temp + O_NOFOLLOW/O_EXCL then os.replace (used by state/artifact/pointer writes) |
| `tools/workflow_cli/trace.py` | Derived trace model: SPEC consumption, scope/risk closure, scope-out violations |
| `tools/workflow_cli/gates.py` | check_entry_gate, check_quality_gate, check_forced_subagent_review |
| `tools/workflow_cli/output.py` | Exit code constants, format_success/error/gate_result, is_json_mode |
| `tools/workflow_cli/cli.py` | argparse router: run/tier/gate/status/stage/checkpoint/route/context command groups |
| `tools/workflow_cli/agent_shortcuts.py` | r2p-* shortcut surface: start/continue/status/switch/reopen/gap/archive/execute |
| `tools/workflow_cli/install.py` | InstallService: install/uninstall/status |
| `tools/workflow_cli/install_cli.py` | r2p lifecycle binary (delegates to InstallService) |
| `tools/workflow_cli/agent_templates/` | Install templates for claude/codex/gemini |
| `.claude/skills/req-to-plan.md` | Dev-view skill for contributors (this project) |

## Extending

**Add a CLI command** — add handler to `cli.py`, register in `_register_*_commands`, add tests to `tests/test_cli.py`.

**Extend tier keywords** — edit `tier_keywords.yaml`; add zh+en entries under one of: `migration`, `cross_project`, `safety`, `dependency`, `scope_expanding`.

## Test Conventions

- All tests use `tempfile.TemporaryDirectory` for filesystem isolation.
- Always pass `base_path=Path(tmp)` to CLI/shortcuts — never use real `.req-to-plan/`.
- Test runner: locally use `.venv/bin/python -m pytest` or `npm run test:local`; in an environment with `requirements-dev.txt` installed (CI, fresh venv) `python -m pytest` or `npm test` is fine. Never use bare `pytest`.
- New features: write tests first (red → green → commit).
- All tests must stay green. Run the full suite; the exact count is intentionally not pinned here.

## Key Invariants

- **Agent/CLI separation**: CLI manages state and validates structure; Agent generates semantic content. CLI never generates artifact text.
- **Tier floor enforcement**: `TierEstimate.lock()` raises ValueError if locking below computed floor. Override requires `--override-floor --confirm`.
- **Terminal status**: `RunStatus.ARCHIVED` is the terminal state. `EXECUTING` is open (an executing run blocks starting a new one); `CLOSED_AT_PLAN_CHECKPOINT` is also non-blocking for new runs but is reopen/execute/archive-able. `is_terminal()` returns True only for CLOSED and ARCHIVED.
- **Archive completion gate**: `run-archive` on an `EXECUTING` run requires `execution/progress.md` to mark every PLAN-TASK `[x]` (cross-checked against the frozen PLAN); `--force` overrides. See `gates.check_execution_complete`.
- **Exit codes**: 0=ok, 2=cli-err, 3=gate-fail, 4=dry-run, 5=review-required, 6=conflict, 7=not-found.
- **Manifest safety**: Uninstall only removes `installed_paths` listed in manifest. Backup before any overwrite.
- **JSON mode**: Set `R2P_JSON=1` to get machine-readable JSON output instead of human-readable text.
- **Auto-commit on close/archive**: `run-close` (at the PLAN checkpoint) and `run-archive` make a path-limited, best-effort `git commit` of `.req-to-plan/.gitignore` + the run dir — never `-A`/`-f`/push, and a no-op outside a git work tree. See `workspace.py:commit_requirement_dir`.

## Workflow Docs

- `docs/req-to-plan-design.md` — the authoritative entry doc: background, goals,
  architecture, and the per-stage quality model (enforced gate criteria).
  Note: the entire `docs/` tree is local-only (gitignored), including
  requirement and plan documents.

Machine facts (exit codes, statuses, `ALLOWED_TRANSITIONS`, tier tables, command
and flag names) are owned by code under `tools/workflow_cli/`, not by prose docs.

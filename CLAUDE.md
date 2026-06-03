# req-to-plan — CLAUDE.md

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
| `tools/workflow_cli/gates.py` | check_entry_gate, check_quality_gate, check_forced_subagent_review |
| `tools/workflow_cli/output.py` | Exit code constants, format_success/error/gate_result, is_json_mode |
| `tools/workflow_cli/cli.py` | argparse router: run/tier/gate/status/stage command groups |
| `tools/workflow_cli/agent_shortcuts.py` | r2p-* shortcut surface: start/continue/status/switch/reopen |
| `tools/workflow_cli/install.py` | InstallService: install/uninstall/installed/doctor |
| `tools/workflow_cli/install_cli.py` | r2p lifecycle binary (delegates to InstallService) |
| `tools/workflow_cli/agent_templates/` | Install templates for claude/codex/gemini |
| `.claude/skills/req-to-plan.md` | Dev-view skill for contributors (this project) |

## Extending

**Add a CLI command** — add handler to `cli.py`, register in `_register_*_commands`, add tests to `tests/test_cli.py`.

**Extend tier keywords** — edit `tier_keywords.yaml`; add zh+en entries under one of: `migration`, `cross_project`, `safety`, `dependency`, `scope_expanding`.

## Test Conventions

- All tests use `tempfile.TemporaryDirectory` for filesystem isolation.
- Always pass `base_path=Path(tmp)` to CLI/shortcuts — never use real `.req-to-plan/`.
- Test runner: `.venv/bin/python -m pytest` (never bare `pytest` or `python -m pytest`).
- New features: write tests first (red → green → commit).
- Baseline: 602 tests passing. All must stay green.

## Key Invariants

- **Agent/CLI separation**: CLI manages state and validates structure; Agent generates semantic content. CLI never generates artifact text.
- **Tier floor enforcement**: `TierEstimate.lock()` raises ValueError if locking below computed floor. Override requires `--override-floor --confirm`.
- **Terminal status**: Only `RunStatus.CLOSED_AT_PLAN_CHECKPOINT` is terminal. All others are open.
- **Exit codes**: 0=ok, 2=cli-err, 3=gate-fail, 4=dry-run, 5=review-required, 6=conflict, 7=not-found.
- **Manifest safety**: Uninstall only removes `installed_paths` listed in manifest. Backup before any overwrite.
- **JSON mode**: Set `R2P_JSON=1` to get machine-readable JSON output instead of human-readable text.

## Workflow Docs

- `docs/req-to-plan-design.md` — the authoritative entry doc: background, goals,
  architecture, and the per-stage quality model (enforced gate criteria).

Machine facts (exit codes, statuses, `ALLOWED_TRANSITIONS`, tier tables, command
and flag names) are owned by code under `tools/workflow_cli/`, not by prose docs.

# AGENTS.md

Guidance for AI agents working in `req-to-plan`. Compact by design — only what
an agent would otherwise guess wrong. Project facts live here; do not duplicate
them into tool-specific files.

## What this is

`@xenonbyte/req-2-plan` (npm) ships a Python CLI + installer that generates
per-platform agent surfaces (`claude` / `codex` / `gemini` / `opencode`) for a
staged, gated requirement→PLAN workflow. Runtime is Python 3.11/3.12 (stdlib +
`pyyaml` only). Node 18+ is used solely by the thin launcher `bin/r2p.js`,
which sets `PYTHONPATH` and execs `python3 -m tools.workflow_cli.install_cli`.

The workflow stores state on disk under `.req-to-plan/<work-id>/`; there is no
database and no server. A run advances stage by stage, each producing one
numbered artifact, and clears entry gate → quality gate → human checkpoint
before the next stage seeds.

## Commands — use exactly these

```bash
# Tests — locally you MUST use the venv; system python3 has no pyyaml.
.venv/bin/python -m pytest tests/ -v              # full suite
.venv/bin/python -m pytest tests/test_cli.py -v   # one module
npm run test:local                                # == .venv/bin/python -m pytest
# CI shape (fresh venv w/ requirements-dev.txt): python -m pytest -q

# Run the workflow CLI directly (no npm/global install needed)
.venv/bin/python -m tools.workflow_cli --help
bin/r2p.js version                                # package.json `prepack` runs this

# Install into a real agent home — writes real ~/.req-to-plan (NOT isolated)
.venv/bin/python -m tools.workflow_cli.install_cli install --platform claude
```

Never use bare `pytest` — it ignores the venv and fails on the missing `pyyaml`
import. Never run `npm install -g` to develop; use the venv paths above.

## Architecture & module map

**Agent/CLI separation** (load-bearing invariant): the CLI manages state,
structure, and validation; **the CLI never generates artifact prose.** Agents
write semantic content.

Three entry surfaces: the Python CLI (`python -m tools.workflow_cli`), the
`tools/r2p-*` shell wrappers used by installed agent surfaces, and the npm
binary `bin/r2p.js` (delegates to `install_cli`). opencode derives its commands
from Claude's Markdown command templates.

| Module | Responsibility |
|---|---|
| `models.py` | Core types: `RunStatus`, `Stage`, `TierBase`/`Modifier`/`Estimate`, `WorkId`, `ALLOWED_TRANSITIONS` |
| `state.py` | `RunStateManager`, `run.md` read/write, transition validation |
| `artifact.py` | `ArtifactManager`, YAML frontmatter, ready/stale flags |
| `tier.py` + `tier_keywords.yaml` | Keyword scan, tier floor, tier estimation |
| `repo_baseline.py` / `context_pack.py` | Repo baseline scan + Project Context Pack |
| `link_expander.py` | Local relative-link expansion for requirement intake |
| `stage_schema.py` / `stage_templates.py` | Required headings per stage/tier; structural seed templates |
| `markdown.py` / `atomic.py` | Fence-aware Markdown helpers; atomic text writes |
| `trace.py` | Derived trace model and closure checks |
| `gates.py` | Entry gates, quality gates, execution-completion gate, forced review |
| `output.py` | Exit-code constants, output formatting, JSON mode |
| `cli.py` | Internal argparse router (workflow commands) |
| `agent_shortcuts.py` | `r2p-*` shortcut surface + active-pointer helpers |
| `install.py` / `install_cli.py` | Install/uninstall/status service + manifest safety; lifecycle binary |
| `agent_templates/{claude,codex,gemini}` | Install templates (opencode is derived from Claude's) |

## Key invariants

- **Exit codes** (`output.py`): `0` ok · `2` cli-err · `3` gate-fail · `4` dry-run · `5` review-required · `6` conflict · `7` not-found.
- **Terminal-for-open-run scanning**: `agent_shortcuts.is_terminal()` treats `CLOSED_AT_PLAN_CHECKPOINT` and `ARCHIVED` as terminal. `EXECUTING` blocks starting a new run; `CLOSED_AT_PLAN_CHECKPOINT` is non-blocking and is reopen/execute/archive-able.
- **Tier floor**: `TierEstimate.lock()` raises if locked below the computed floor; override needs `--override-floor --confirm`.
- **Manifest safety**: uninstall removes only paths in `installed_paths`; pre-existing user files are backed up, never deleted.
- **JSON mode**: set `R2P_JSON=1` for machine-readable output.
- **Scoped git commits**: closing a run at the PLAN checkpoint and archiving a run each do a path-limited, best-effort `git commit` scoped to `.req-to-plan/.gitignore` + that run's `.req-to-plan/<work-id>/` dir. They never run `git add -A`/`-f`, never force-add ignored paths, never push, and are a no-op outside a git work tree.

### State machine (`models.py` → `ALLOWED_TRANSITIONS`)

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

### Artifact filenames

`00-raw-requirement.md` → `03-requirement-brief.md` → `04-risk-discovery.md` → `05-design.md` → `06-spec.md` → `07-plan.md`.

## Test rules

- Isolate **every** test with `tempfile.TemporaryDirectory` and pass `base_path=Path(tmp)` to CLI/shortcut calls. Never touch real `~/.req-to-plan/` or the repo's own `.req-to-plan/`.
- New features: write the test first (red → green → commit). Keep the full suite green; describe its size qualitatively, **never** with a frozen number.
- `print_and_exit` calls `sys.exit`; tests calling `cli.main()` must catch `SystemExit`.
- `tests/test_docs_consistency.py` silently guards two things you can break when editing docs/templates:
  - `CLAUDE.md` must contain **no** hardcoded test count ("NN passing", "baseline: NN").
  - Agent-template surfaces must carry required tokens (`r2p-continue` → "unresolved ambiguity"/"undecided point"; `r2p-execute` → the SDD token set) and `r2p-execute` templates must **not** mention `r2p-gap-open`.

## Repo-layout gotchas

- `docs/` is **tracked** design state (only `docs/archive/` is ignored). `.req-to-plan/` run dirs (`<work-id>/`) are **tracked** and committed by the path-scoped close/archive commit; only `.req-to-plan/archive`, `.workflow-active`, and `<work-id>/logs/` are ignored (see `.req-to-plan/.gitignore`).
- `.claude/skills/` is local tool state, not the canonical project guide. The user-facing Claude install template is `tools/workflow_cli/agent_templates/claude/SKILL.md`.
- `.codegraph/` is present and indexed — prefer `codegraph explore` / `codegraph node` over grep+read when locating code.
- `.drfx/` holds archived local run artifacts, not source.
- Do not hardcode the package version in docs; `tools/workflow_cli/version.py` (`R2P_VERSION`) is the single source.

## Extending

- **Add a CLI command**: handler in `cli.py`, register it in the relevant `_register_*_commands`, use constants from `output.py`, add tests following the local `invoke()` helper pattern.
- **Extend tier keywords**: edit `tools/workflow_cli/tier_keywords.yaml`; keep the modifier groups (`migration`, `cross_project`, `safety`, `dependency`, `scope_expanding`), add English + Chinese variants, rerun focused tier tests.

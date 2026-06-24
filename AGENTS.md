# AGENTS.md

Guidance for AI agents working in `req-to-plan`. Compact by design — **read
`DEVELOPMENT.md` next**: it is the committed, tool-neutral development guide
with the full module map, staged workflow model, and shared maintenance rules.
This file only captures what an agent would otherwise guess wrong.

## What this is

`@xenonbyte/req-2-plan` (npm) ships a Python CLI + installer that generates
per-platform agent surfaces (`claude` / `codex` / `gemini` / `opencode`) for a
staged, gated requirement→PLAN workflow. Runtime is Python 3.11/3.12 (stdlib +
`pyyaml` only). Node 18+ is used solely by the thin launcher `bin/r2p.js`, which
sets `PYTHONPATH` and execs `python3 -m tools.workflow_cli.install_cli`.

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

Never use bare `pytest` — it ignores the venv and fails on the missing
`pyyaml` import. Never run `npm install -g` to develop; use the venv paths
above.

## Test rules

- Isolate every test with `tempfile.TemporaryDirectory` and pass
  `base_path=Path(tmp)` to CLI/shortcut calls. **Never** touch the real
  `~/.req-to-plan/` or the repo's own `.req-to-plan/`.
- New features: write the test first (red → green → commit). Keep the full
  suite green; describe its size qualitatively, never with a frozen number.
- `tests/test_docs_consistency.py` enforces two things you can silently break
  when editing docs/templates:
  - `DEVELOPMENT.md` and tool-specific entry docs must contain **no** hardcoded
    test count ("NN passing", "baseline: NN").
  - Agent-template surfaces must carry required tokens (`r2p-continue` →
    "unresolved ambiguity"/"undecided point"; `r2p-execute` → the SDD set)
    and `r2p-execute` templates must **not** mention `r2p-gap-open`.

## Architecture invariants

- **Agent/CLI separation**: the CLI manages state and validates structure; the
  Agent produces semantic content. **CLI never generates artifact text.**
- **Entry points**: `cli.py` (workflow argparse router), `install_cli.py`
  (lifecycle: install/uninstall/status), `agent_shortcuts.py` (the `r2p-*`
  surface). See `DEVELOPMENT.md` for the rest of the module map.
- **Exit codes**: 0 ok · 2 cli-err · 3 gate-fail · 4 dry-run · 5 review-required
  · 6 conflict · 7 not-found.
- **Terminal status**: `CLOSED_AT_PLAN_CHECKPOINT` and `ARCHIVED` are terminal
  for open-run scanning (`is_terminal()`). `EXECUTING` blocks starting a new run;
  `CLOSED_AT_PLAN_CHECKPOINT` is reopen/execute/archive-able but non-blocking.
- **Tier floor**: `TierEstimate.lock()` raises if locked below the computed
  floor; override needs `--override-floor --confirm`.
- **Manifest safety**: uninstall removes only paths in `installed_paths`;
  pre-existing user files are backed up, never deleted.
- **JSON mode**: set `R2P_JSON=1` for machine-readable output.

## Repo-layout gotchas

- `docs/` and `.req-to-plan/` are **gitignored** (local-only runtime/design
  state). Don't commit either. `DEVELOPMENT.md` is committed and is the shared
  development guide.
- `.claude/skills/` is local tool state, not the canonical project guide. Do
  not commit it.
- `.codegraph/` is present and indexed — prefer `codegraph explore` /
  `codegraph node` over grep+read when locating code.
- `.drfx/` holds archived run artifacts (local history), not source.

## Operational behavior to know

Closing a run at the PLAN checkpoint, and archiving a run, each perform a
**path-limited `git commit`** scoped to `.req-to-plan/.gitignore` + that run's
`.req-to-plan/<work-id>/` dir (archive commits the path removal). It never
runs `git add -A`/`-f` or `git push`, and is a no-op outside a git work tree.

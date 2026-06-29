# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

This file is self-contained: it does not depend on `AGENTS.md`. (`AGENTS.md`
carries the same facts for other agent surfaces; if you change a project fact,
update both.)

## What this is

`@xenonbyte/req-2-plan` (npm) ships a Python CLI plus an installer that generates
per-platform agent surfaces (`claude` / `codex` / `gemini` / `opencode`) for a
staged, gated **requirement → PLAN** workflow, and can then execute that PLAN in
place. Runtime is Python 3.11/3.12 (stdlib + `pyyaml` only); there is no database
and no server — all run state lives on disk under `.req-to-plan/<work-id>/`.
Node 18+ is used solely by the thin launcher `bin/r2p.js`, which sets
`PYTHONPATH` and execs `python3 -m tools.workflow_cli.install_cli`.

## Commands — use exactly these

```bash
# Tests — locally you MUST use the venv; system python3 has no pyyaml.
.venv/bin/python -m pytest tests/ -v              # full suite
.venv/bin/python -m pytest tests/test_cli.py -v   # one module
.venv/bin/python -m pytest tests/test_cli.py -v -k tier_lock   # one test
npm run test:local                                # == .venv/bin/python -m pytest
# CI shape (fresh venv w/ requirements-dev.txt, Python 3.11 + 3.12 matrix): python -m pytest -q

# Run the workflow CLI directly (no npm/global install needed)
.venv/bin/python -m tools.workflow_cli --help
bin/r2p.js version                                # package.json `prepack` runs this

# Install into a real agent home — writes real ~/.req-to-plan (NOT isolated)
.venv/bin/python -m tools.workflow_cli.install_cli install --platform claude
```

Never use bare `pytest` — it ignores the venv and fails on the missing `pyyaml`
import. Never `npm install -g` to develop; use the venv paths above.

The local `.venv` is Python 3.10, so a few `tomllib`-dependent tests **skip**
locally — that is expected, not a failure; they execute on the CI 3.11/3.12
matrix. `pytest` is the only verification surface: there is **no** linter,
formatter, or type-checker configured (no ruff/black/mypy/pyproject), so don't
go looking for one or introduce one without being asked.

## Architecture (big picture)

**Pipeline.** A run advances stage by stage, each producing one numbered
artifact: `00-raw-requirement.md` → `03-requirement-brief.md` →
`04-risk-discovery.md` → `05-design.md` → `06-spec.md` → `07-plan.md`. Each stage
clears an **entry gate**, then a **quality gate** plus a **human checkpoint**,
before the next stage is seeded. After PLAN the run is
`CLOSED_AT_PLAN_CHECKPOINT`; from there it can go `EXECUTING` (in-place task
implementation), then `ARCHIVED`.

**State vs. artifacts.** `run.md` is owned by `state.py` and holds status, stage,
approved checkpoints, open routes, and resume context. Each `NN-*.md` artifact is
owned by `artifact.py` and carries YAML frontmatter for version + ready/stale
flags.

**CLI vs. agent — the core separation.** The CLI manages state, seeds structural
templates, and validates structure; the **Agent** produces all semantic content.
**The CLI never generates artifact prose.** `cli.py` is the workflow argparse
router, `install_cli.py` is the install/uninstall/status lifecycle binary, and
`agent_shortcuts.py` exposes the higher-level `r2p-*` surface that agents drive.

**Distribution.** Three entry surfaces: the Python CLI
(`python -m tools.workflow_cli`), the `tools/r2p-*` shell wrappers used by
installed agent surfaces, and the npm binary `bin/r2p.js` (delegates to
`install_cli`). Install templates live in
`tools/workflow_cli/agent_templates/{claude,codex,gemini}`; **opencode has no
template dir** — its commands are derived from Claude's Markdown command
templates and installed under `~/.config/opencode/commands/`.

Machine facts (exit codes, statuses, transitions, tier tables, command names,
flags) are owned by code under `tools/workflow_cli/`, not by prose. When in
doubt, read the module, not this file.

### Module map

| Module | Responsibility |
|---|---|
| `models.py` | Core types: `RunStatus`, `Stage`, `TierBase`, `TierModifier`, `TierEstimate`, `WorkId`, `ALLOWED_TRANSITIONS` |
| `state.py` | `RunStateManager`, `run.md` read/write, transition validation |
| `artifact.py` | `ArtifactManager`, YAML frontmatter, ready/stale flags |
| `tier.py` / `tier_keywords.yaml` | Keyword scan, tier floor computation, estimation + keyword bank |
| `repo_baseline.py` | Repo baseline scan: LOC, languages, monorepo/submodule signals |
| `context_pack.py` | Project Context Pack: deps, test commands, entrypoints, config, source dirs |
| `link_expander.py` | Local relative-link expansion for requirement intake |
| `stage_schema.py` / `stage_templates.py` | Required headings per stage/tier + structural seed templates; `stage_templates.py` also seeds PLAN's optional, removable **non-gate** sections (`## Execution Readiness`, `## Risk Handling`) and PLAN-TASK fields (`Out-of-Task`, `Future Task Ownership`) — absent from `STAGE_SCHEMA`/`PLAN_TASK_FIELDS`, so deleting them still passes the quality gate |
| `markdown.py` / `atomic.py` | Fence-aware Markdown helpers; atomic text writes |
| `workspace.py` | Neutral `.req-to-plan/` workspace helpers (imports neither `cli.py` nor `agent_shortcuts.py`): owns the workspace `.gitignore` and the path-limited git-commit primitive used by run-close (add) and run-archive (remove) |
| `trace.py` | Derived trace model and closure checks |
| `gates.py` | Entry/quality gates, execution completion gate, forced-review checks |
| `output.py` | Exit code constants, output formatting, JSON mode |
| `cli.py` / `agent_shortcuts.py` | Argparse router; `r2p-*` shortcut surface + active-pointer helpers |
| `install.py` / `install_cli.py` | Install/uninstall/status service + manifest safety; lifecycle binary |
| `agent_templates/` | Install templates for Claude, Codex, Gemini (opencode derives from Claude) |

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

## Invariants (verify against code before changing)

- **Exit codes** (`output.py`): `0` ok · `2` cli error · `3` gate fail · `4` dry
  run · `5` review required · `6` conflict · `7` not found.
- **Terminal-for-open-run scanning**: `agent_shortcuts.is_terminal()` treats
  `CLOSED_AT_PLAN_CHECKPOINT` and `ARCHIVED` as terminal. `EXECUTING` blocks
  starting a new run; `CLOSED_AT_PLAN_CHECKPOINT` is non-blocking and is
  reopen/execute/archive-able.
- **Tier floor**: `TierEstimate.lock()` raises when locking below the computed
  floor; override needs `--override-floor --confirm`.
- **Manifest safety**: uninstall removes only paths in `installed_paths`;
  pre-existing user files are backed up before overwrite, never deleted. Every
  manifest write routes through `InstallService._write_manifest_atomic`
  (unique-temp + `O_EXCL` + `O_NOFOLLOW` + atomic replace, symlink-rejecting) —
  never a bare `write_text`; obsolete-wrapper cleanup tolerates its `ValueError`
  best-effort rather than aborting the install.
- **JSON mode**: set `R2P_JSON=1` for machine-readable output.
- **Version**: `tools/workflow_cli/version.py` (`R2P_VERSION`) is the single
  source — never hardcode the version in docs.
- **Git side effects** (primitive in `workspace.py`): closing a run at the PLAN
  checkpoint and archiving a run each perform a **path-limited, best-effort
  `git commit`** scoped to
  `.req-to-plan/.gitignore` plus that run's `.req-to-plan/<work-id>/` dir
  (archive commits the path removal). They never run `git add -A`/`-f`, never
  force-add ignored paths, never push, and are a no-op outside a git work tree.
- **Final-review marker gate**: `check_final_review_recorded` is a presence/audit
  check at the same trust level as the PLAN-TASK checkbox gate — it verifies that
  `execution/final-review.md` exists and records `Verdict: Approved`; it never runs
  code, runs tests, or asserts the recorded verdict is true.
- **Cross-stage trace closure**: enforced at the PLAN quality gate (every `SPEC-*`
  consumed by a PLAN-TASK, every `SCOPE-IN-*` carried into PLAN, every `RISK-*`
  closed). Intermediate stages enforce only "cited upstream ID ⇒ closure tag".
  Stages 04–06 have no forward full-coverage gate by design (REQ→DES→SPEC is a
  legitimately many-to-many mapping; a hard symmetric-coverage gate produces false
  positives).

## Test rules

- Isolate every test with `tempfile.TemporaryDirectory` and pass
  `base_path=Path(tmp)` to CLI/shortcut calls. **Never** touch the real
  `~/.req-to-plan/` or the repo's own `.req-to-plan/`.
- New behavior gets a focused test first (red → green → commit). Keep the full
  suite green; describe its size qualitatively, never with a frozen number.
- `print_and_exit` calls `sys.exit`; tests that call `cli.main()` must catch
  `SystemExit`.
- `tests/test_docs_consistency.py` guards two things you can silently break when
  editing docs/templates:
  - **This file (`CLAUDE.md`) must contain no hardcoded test count** (e.g.
    "NN passing", "baseline: NN"). Describe the suite qualitatively.
  - Agent-template surfaces must carry required tokens — `r2p-continue` →
    "unresolved ambiguity" / "undecided point"; `r2p-execute` → the SDD set
    (in-place on `current branch`, `Pre-flight`, `Verification`,
    `fresh implementer subagent`, `task-reviewer`, `whole-branch review`,
    `NEEDS_CONTEXT`, dirty-tree block `stop before dispatching Task 1` /
    `Do not commit unrelated work` / `git status --short -- ':!.req-to-plan'`,
    plus the FR-A additions `Model Selection`, `HEAD~1`,
    `execution/final-review.md`, `Verdict: Approved`,
    `re-run the full verification suite`) — and `r2p-execute` templates must
    **not** mention `r2p-gap-open` (execution runs are `closed`, so upstream
    defects go through reopen/human repair, not gap routing). A separate guard,
    `test_execute_surfaces_carry_template_hardening_tokens`, pins the EXE-1..EXE-5
    execution-protocol prose with distinctive load-bearing tokens that must appear
    on **both** `r2p-execute` surfaces (claude command + codex SKILL) in lockstep;
    deleting any from either surface fails the test.

## Extending

- **Add a CLI command**: add the handler to `cli.py`, register it in the relevant
  `_register_*_commands` function, use the constants from `output.py`, and add
  tests following the local `invoke()` helper pattern.
- **Extend tier keywords**: edit `tools/workflow_cli/tier_keywords.yaml`; keep the
  modifier groups (`migration`, `cross_project`, `safety`, `dependency`,
  `scope_expanding`), add English and Chinese variants when applicable, and run
  the focused `test_tier.py`.

## Repo-layout gotchas

- `.req-to-plan/` run dirs (`<work-id>/`) are **tracked** — close/archive commit
  them via the path-scoped commit; only `.req-to-plan/archive`, `.workflow-active`,
  and `<work-id>/logs/` are ignored (see `.req-to-plan/.gitignore`). `docs/` is
  **tracked** design state (committed; e.g. requirement docs live here); only
  `docs/archive/` is gitignored local history. Check `.gitignore` before assuming
  a path is ignored.
- `.claude/skills/` is local tool state, not the canonical project guide; the
  user-facing Claude install template is
  `tools/workflow_cli/agent_templates/claude/SKILL.md`.
- `.codegraph/` is present and indexed — prefer `codegraph explore` /
  `codegraph node` over grep+read when locating code. (See
  `.cursor/rules/codegraph.mdc` for the per-tool decision table.)
- `.drfx/` holds archived run artifacts (local history), not source.

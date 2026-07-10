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
.venv/bin/python -m pytest tests/ -v                          # full suite
.venv/bin/python -m pytest tests/test_cli.py -v               # one module
.venv/bin/python -m pytest tests/test_cli.py -v -k tier_lock  # one test (-k)
npm run test:local                                            # == .venv/bin/python -m pytest
# CI shape (fresh venv w/ requirements-dev.txt, py 3.11/3.12): python -m pytest -q

# Run the workflow CLI directly (no npm/global install needed)
.venv/bin/python -m tools.workflow_cli --help
bin/r2p.js version                                # package.json `prepack` runs this

# Install into a real agent home — writes real ~/.req-to-plan (NOT isolated)
.venv/bin/python -m tools.workflow_cli.install_cli install --platform claude
```

Never use bare `pytest` — it ignores the venv and fails on the missing `pyyaml`
import. Never run `npm install -g` to develop; use the venv paths above.

The local `.venv` is Python 3.10, so a few `tomllib`-dependent tests **skip**
locally — expected, not a failure; they run on the CI 3.11/3.12 matrix. `pytest`
is the only verification surface: there is **no** linter, formatter, or
type-checker configured (no ruff/black/mypy/pyproject) — don't look for one or
introduce one without being asked.

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
| `stage_schema.py` / `stage_templates.py` | Required headings per stage/tier; structural seed templates (incl. PLAN's optional, removable non-gate sections — Execution Readiness, Risk Handling — not in `STAGE_SCHEMA`/`PLAN_TASK_FIELDS`). No per-task "defer" field: a decomposition stage may not push requirement content to a later run (R20) |
| `markdown.py` / `atomic.py` | Fence-aware Markdown helpers (incl. offset-preserving `strip_nonsemantic_markdown` / `strip_html_comments_outside_fences`); atomic text writes + symlink-safe `read_regular_text` |
| `workspace.py` | Neutral helper (no CLI/shortcut import → no cycle): owns the workspace `.gitignore` + the path-limited `git commit` primitive used by run-close (add) and run-archive (remove) |
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
- **Manifest safety**: uninstall removes only paths in `installed_paths`; pre-existing user files are backed up, never deleted. Every manifest write routes through `InstallService._write_manifest_atomic` (unique-temp + `O_EXCL` + `O_NOFOLLOW` + atomic replace, symlink-rejecting) — never a bare `write_text`; obsolete-wrapper cleanup tolerates its `ValueError` best-effort rather than aborting the install. `_manifest_shape_issues` checks **structural trust** (field presence/types) only: a valid manifest whose `schema_version` merely differs from the current `SCHEMA_VERSION` is *drift* (`status`-only), **not** a shape defect — flagging it there would make uninstall/cleanup strand a prior install on the next schema bump.
- **Trusted-input reads are symlink-safe**: reads of trusted on-disk text (artifacts, `02-project-context.md` + scanned dependency configs, continue seeds, `run.md`, gap-open snapshots) route through `atomic.read_regular_text` (lstat → `O_NOFOLLOW` → fstat dev/ino identity; offset-preserving) — never a bare `path.read_text()`. A non-regular/symlinked/raced source raises `UnsafeRegularFileError`, surfaced as exit `6` (`cli.main` catch-all; shortcuts print `blocked: unsafe_seed_source`).
- **Wrapper bootstrap isolation**: the `tools/r2p-*` wrappers and generated commands exec `python -E …/tools/workflow_cli/__main__.py <target>` — **`-E`, not `-I`**, so a user-site `pyyaml` still imports (isolate against `PYTHONPATH` injection, not user site). `__main__._sanitized_sys_path` then drops cwd **and the script's own dir** before prepending the repo root, so `tools/workflow_cli/` modules (notably `trace`) can't shadow stdlib. Do not revert to `-I` or drop the sys.path surgery.
- **Non-semantic Markdown stripped uniformly**: gate/trace checks preprocess with `strip_nonsemantic_markdown` — seeded read-only sections removed **and** HTML comments masked to spaces (offset-preserving so removal can't concatenate adjacent IDs/fields; fence-aware so fenced examples stay verbatim). Commented-out headings, PLAN-TASK fields, trace IDs, and fenced snippets neither satisfy nor trip a gate. Trace-ID matching (`SPEC_ID_RE`, `_SCOPE_IN_ID_RE`, `_ID_RE`) is token-boundary-aware: `SPEC-…-1` is not closed by `SPEC-…-10`.
- **JSON mode**: set `R2P_JSON=1` for machine-readable output.
- **Final-review marker gate** (`check_final_review_recorded`): a presence/audit check at the same trust level as the PLAN-TASK checkbox gate — it verifies `execution/final-review.md` exists and records `Verdict: Approved`. It **never** runs code, runs tests, or asserts the verdict is true.
- **Cross-stage trace closure**: enforced only at the PLAN quality gate (every `SPEC-*` consumed by a PLAN-TASK, every `SCOPE-IN-*` carried into PLAN, every `RISK-*` closed). Intermediate stages enforce only "cited upstream ID ⇒ closure tag"; stages 04–06 have no forward full-coverage gate by design (REQ→DES→SPEC is a legitimately many-to-many mapping — a hard symmetric gate produces false positives).
- **No unanchored deferral (R20)**: `gates._check_unanchored_deferral` fails the quality gate when a decomposition stage (04–07) carries a high-signal "do-later / not-this-round" phrase unless the same line cites a `SCOPE-OUT-*` the brief actually declares (`trace.defined_scope_out_ids`; an undeclared id does not anchor it). Exclusions are declared once, in the brief's `## Out-of-Scope` (the only authority for what may be skipped), and may only be cited downstream. The brief is not scanned; structured closures (`Status: deferred`, `[DEFERRED]`) are not deferral phrases.
- **Keep R20 a high-signal tripwire, not an NL parser**: `_DEFERRAL_PATTERNS` + the SCOPE-OUT anchoring logic catch the *obvious* deferral cases only. Do NOT keep adding regex to chase rare phrasings or same-line laundering — each round trades one error class for another (false positives on ordinary prose like "deferred rendering"/"the current phase"/"next phase should specify", false negatives from over-narrowing) and is negative-sum. Accept the documented residuals (`defer X to` a non-bucket target, a single defer verb over a coordinated in/out-of-scope object, coarse-`SCOPE` sub-coverage); the human checkpoint (universal semantic backstop) and the r2p-continue template rule own the tail. On a real miss, tighten an existing high-precision pattern or the template/checkpoint prose — do not add brittle new patterns.
- **Scoped git commits** (primitive in `workspace.py`): closing a run at the PLAN checkpoint and archiving a run each do a path-limited, best-effort `git commit` scoped to `.req-to-plan/.gitignore` + that run's `.req-to-plan/<work-id>/` dir. They never run `git add -A`/`-f`, never force-add ignored paths, never push, and are a no-op outside a git work tree.

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
  - Agent-template surfaces must carry required tokens (`r2p-continue` → "unresolved ambiguity"/"undecided point"; `r2p-execute` → the SDD token set plus the EXE-1..EXE-5 hardening tokens guarded by `test_execute_surfaces_carry_template_hardening_tokens` on **both** surfaces in lockstep) and `r2p-execute` templates must **not** mention `r2p-gap-open`.

## Repo-layout gotchas

- `docs/` is **tracked** design state (only `docs/archive/` is ignored). `.req-to-plan/` run dirs (`<work-id>/`) are **tracked** and committed by the path-scoped close/archive commit; only `.req-to-plan/archive`, `.workflow-active`, `<work-id>/logs/`, and `<work-id>/execution/` are ignored (see `.req-to-plan/.gitignore`). `execution/` is ignored like `logs/`: the SDD execution ledger/reports/reviews are local audit trail, never shared git history (gates still read them from the working tree — "ignored" means "not shared via git," not "unimportant").
- `.claude/skills/` is local tool state, not the canonical project guide. The user-facing Claude install template is `tools/workflow_cli/agent_templates/claude/SKILL.md`.
- `.codegraph/` is present and indexed — prefer `codegraph explore` / `codegraph node` over grep+read when locating code.
- `.drfx/` holds archived local run artifacts, not source.
- Do not hardcode the package version in docs; `tools/workflow_cli/version.py` (`R2P_VERSION`) is the single source.

## Extending

- **Add a CLI command**: handler in `cli.py`, register it in the relevant `_register_*_commands`, use constants from `output.py`, add tests following the local `invoke()` helper pattern.
- **Extend tier keywords**: edit `tools/workflow_cli/tier_keywords.yaml`; keep the modifier groups (`migration`, `cross_project`, `safety`, `dependency`, `scope_expanding`), add English + Chinese variants, rerun focused tier tests.

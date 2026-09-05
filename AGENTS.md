# AGENTS.md

Guidance for AI agents working in `req-to-plan`. Compact by design — only what
an agent would otherwise guess wrong. Keep project facts synchronized with the
self-contained `CLAUDE.md`; code and executable tests remain authoritative.

## What this is

`@xenonbyte/req-2-plan` (npm) ships a Python CLI + installer that generates
per-platform agent surfaces (`claude` / `codex` / `gemini` / `opencode`) for a
staged, gated requirement→PLAN workflow with optional in-place PLAN execution.
CI targets Python 3.11/3.12; Python dependencies are stdlib + `pyyaml` only.
Node 18+ is used solely by the thin launcher `bin/r2p.js`,
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
# Docs / template contract checks
.venv/bin/python -m pytest tests/test_docs_consistency.py tests/test_readme.py -q
# CI shape (fresh venv w/ requirements-dev.txt, py 3.11/3.12): python -m pytest -q

# Run the workflow CLI directly (no npm/global install needed)
.venv/bin/python -m tools.workflow_cli --help
bin/r2p.js version                                # package.json `prepack` runs this

# Only when installation is requested — writes real agent homes and ~/.req-to-plan
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
| `models.py` | Core types: `RunStatus`, `Stage`, `TierBase`, `TierModifier`, `TierEstimate`, `WorkId`; `ALLOWED_TRANSITIONS` and `ALLOWED_COMMANDS_BY_RUN_STATE` |
| `state.py` | `RunStateManager`, `run.md` read/write, transition validation |
| `artifact.py` | `ArtifactManager`, YAML frontmatter, ready/stale flags |
| `tier.py` + `tier_keywords.yaml` | Keyword scan, tier floor, tier estimation |
| `repo_baseline.py` / `context_pack.py` | Repo baseline scan + Project Context Pack |
| `link_expander.py` | Local relative-link expansion for requirement intake |
| `stage_schema.py` / `stage_templates.py` | Required headings per stage/tier; structural seed templates (incl. PLAN's optional, removable non-gate sections — Execution Readiness, Risk Handling — not in `STAGE_SCHEMA`/`PLAN_TASK_FIELDS`). No per-task "defer" field: a decomposition stage may not push requirement content to a later run (R20) |
| `markdown.py` / `atomic.py` | Fence-aware Markdown filtering: compact `strip_nonsemantic_markdown` and source-offset-preserving `mask_nonsemantic_markdown` / `strip_html_comments_outside_fences`; atomic text writes + symlink-safe `read_regular_text` |
| `workspace.py` | Neutral helper (no CLI/shortcut import → no cycle): owns the workspace `.gitignore` + the path-limited `git commit` primitive used by run-close (add) and run-archive (remove) |
| `trace.py` | Derived trace model and closure checks |
| `gates.py` | Entry gates, quality gates, execution-completion gate, forced review |
| `execution_context.py` | Fixed semantic context view from a pinned run tree; per-source and aggregate UTF-8 byte counts |
| `execution_profile.py` | Profile/marker and prerequisite grammar, fast eligibility, immutable implementation ranges, commit-chain validation |
| `execution_journal.py` | Authoritative role checkpoints, next-role selection, and separate task/final repair ranges |
| `execution_progress.py` | Atomic progress begin/complete/recover/escalate transitions and read-only resume validation |
| `execution_metrics.py` | Execution-start transaction, dispatch prerequisite checks, and non-authoritative metrics append/ack/finalize/sample validation |
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
- **Trusted-input reads are symlink-safe**: reads of trusted on-disk text (artifacts, `02-project-context.md` + scanned dependency configs, continue seeds, `run.md`, gap-open snapshots) route through `atomic.read_regular_text` (lstat → `O_NOFOLLOW` → fstat dev/ino identity; offset-preserving) — never a bare `path.read_text()`. A non-regular/symlinked/raced source raises `UnsafeRegularFileError`, surfaced as exit `6` (`cli.main` catch-all; shortcuts print `blocked: unsafe_seed_source` for seed/artifact reads, `blocked: unsafe_run_record` for a symlinked `run.md` via `_load_matching_record_or_exit`).
- **Wrapper bootstrap isolation**: the `tools/r2p-*` wrappers and generated commands exec `python -E …/tools/workflow_cli/__main__.py <target>` — **`-E`, not `-I`**, so a user-site `pyyaml` still imports (isolate against `PYTHONPATH` injection, not user site). `__main__._sanitized_sys_path` then drops cwd **and the script's own dir** before prepending the repo root, so `tools/workflow_cli/` modules (notably `trace`) can't shadow stdlib. Do not revert to `-I` or drop the sys.path surgery.
- **Execution recovery protocol**: start rejects code-tree changes outside `.req-to-plan/` before capturing `Execution BASE`. It publishes the run-level `.execution-start-transaction.json` owner atomically before creating `execution/` and removes it only after rollback or durable `EXECUTING` state. `r2p-progress begin/complete` atomically records dispatch/results in `progress.md` using `--expected-sequence`; resume selects the journal's role, never metrics. Original implementation ranges remain immutable; task/final repair ranges live separately in the journal and reviewers consume the returned `review_ranges`. An inflight role is recovered, not automatically redispatched. Legacy committed implementation needs explicit DONE/BASE..HEAD report evidence for `r2p-progress recover`. After authoritative completion, metrics append persists its exact retry request and clears it through `r2p-metrics-ack`; metrics failures never gate valid progress/resume/archive. Missing legacy observations remain an explicit incomplete-instrumentation gap.
- **Execution retries and verification**: BLOCKED retries the same role/task/fix wave after resolution with a new sequence. Preserve TDD red and failed historical checks; final verification requires the latest result of every command to pass, including a full suite. Fully journaled metrics finalization requires exact role coverage. Fast escalation can occur after its primary final review; later strict implementation follows the effective profile.
- **Non-semantic Markdown stripped uniformly**: gate/trace checks preprocess with `strip_nonsemantic_markdown` — seeded read-only sections removed **and** HTML comments masked to spaces (offset-preserving so removal can't concatenate adjacent IDs/fields; fence-aware so fenced examples stay verbatim). Progress edits use `mask_nonsemantic_markdown`, which shares the read-only boundaries but blanks them in place to preserve all original character offsets and every `str.splitlines()` boundary, including Unicode separators in read-only text and comments; compact output offsets must not be used to edit source text. Commented-out headings, PLAN-TASK fields, trace IDs, and fenced snippets neither satisfy nor trip a gate. Reuse `PLAN_TASK_CHECKBOX_RE` over `unfenced_markdown_lines` for execution checkboxes. Trace-ID matching (`SPEC_ID_RE`, `_SCOPE_IN_ID_RE`, `_ID_RE`, and the closure-vicinity search in `gates._find_ids_without_closure`) is token-boundary-aware: `SPEC-…-1` is not closed by `SPEC-…-10`, and a line bearing only a suffixed/typo'd variant no longer self-closes the base ref (fail-closed on typo'd IDs).
- **Execution profiles and prerequisites**: `strict` is the default. `fast` is explicit opt-in after a LIGHT/no-modifier preflight, valid prerequisite v2 across every task, and semantic eligibility confirmation; escalation is one-way to strict. A PLAN with no prerequisite declarations uses legacy v1; mixed or malformed declarations block start. Run the installed `r2p-prerequisite-check` immediately before implementer dispatch, never as task `Verification` or an ordinary post-commit reviewer/fixer check. Its reads pin run directories and verify the embedded work ID.
- **Semantic context delivery**: each role runs `r2p-context-view --work-id <id> --with-stats` itself; the controller passes the command, never reads/relays its content or creates a persistent context bundle. `execution_context.CONTEXT_SOURCE_PATHS` pins `02-project-context.md`, stages 03–06, and `execution/progress.md`; the final reviewer reads `07-plan.md` separately. Return aggregate `semantic_bytes` as metrics `context_bytes`: it includes source headings and separators, unlike the sum of per-source counts. Bytes and elapsed time are not Token measurements; unavailable telemetry stays `unavailable`.
- **Final evidence boundaries**: report paths must match their role/task. Approved final ack requires every task reviewed-complete and no implemented markers; metrics finalization requires an empty pending journal under the metrics lock. Task fix-wave evidence is a complete unfenced `Fix Wave N` line.
- **JSON mode**: set `R2P_JSON=1` for machine-readable output.
- **Final-review marker gate** (`check_final_review_recorded`): a presence/audit check at the same trust level as the PLAN-TASK checkbox gate — it verifies `execution/final-review.md` exists and records `Verdict: Approved`. It **never** runs code, runs tests, or asserts the verdict is true.
- **Cross-stage trace closure**: enforced only at the PLAN quality gate (every `SPEC-*` consumed by a PLAN-TASK, every `SCOPE-IN-*` carried into PLAN, every `RISK-*` closed). Intermediate stages enforce only "cited upstream ID ⇒ closure tag"; stages 04–06 have no forward full-coverage gate by design (REQ→DES→SPEC is a legitimately many-to-many mapping — a hard symmetric gate produces false positives).
- **No unanchored deferral (R20)**: `gates._check_unanchored_deferral` fails the quality gate when a decomposition stage (04–07) carries a high-signal "do-later / not-this-round" phrase unless the same line cites a `SCOPE-OUT-*` the brief actually declares (`trace.defined_scope_out_ids`; an undeclared id does not anchor it). Exclusions are declared once, in the brief's `## Out-of-Scope` (the only authority for what may be skipped), and may only be cited downstream. The brief is not scanned; structured closures (`Status: deferred`, `[DEFERRED]`) are not deferral phrases.
- **Keep R20 a high-signal tripwire, not an NL parser**: `_DEFERRAL_PATTERNS` + the SCOPE-OUT anchoring logic catch the *obvious* deferral cases only. Do NOT keep adding regex to chase rare phrasings or same-line laundering — each round trades one error class for another (false positives on ordinary prose like "deferred rendering"/"the current phase"/"next phase should specify", false negatives from over-narrowing) and is negative-sum. Accept the documented residuals (`defer X to` a non-bucket target, a single defer verb over a coordinated in/out-of-scope object, coarse-`SCOPE` sub-coverage); the human checkpoint (universal semantic backstop) and the r2p-continue template rule own the tail. On a real miss, tighten an existing high-precision pattern or the template/checkpoint prose — do not add brittle new patterns.
- **Scoped git commits** (primitive in `workspace.py`): closing a run at the PLAN checkpoint and archiving a run each do a path-limited, best-effort `git commit` scoped to `.req-to-plan/.gitignore` + that run's `.req-to-plan/<work-id>/` dir. They never run `git add -A`/`-f`, never force-add ignored paths, never push, and are a no-op outside a git work tree.

### State machine (`models.py` → `ALLOWED_TRANSITIONS`)

```text
not_started -> active_stage_draft
active_stage_draft -> active_stage_draft | entry_gate_failed | quality_gate_failed | ready_for_checkpoint_review | upstream_gap_routing | archived
entry_gate_failed -> active_stage_draft | upstream_gap_routing | archived
quality_gate_failed -> active_stage_draft | upstream_gap_routing | archived
ready_for_checkpoint_review -> active_stage_draft | checkpoint_review | upstream_gap_routing | archived
checkpoint_review -> active_stage_draft | checkpoint_changes_requested | checkpoint_approved | upstream_gap_routing | archived
checkpoint_changes_requested -> active_stage_draft | quality_gate_failed | upstream_gap_routing | archived
upstream_gap_routing -> active_stage_draft | upstream_gap_routing | ready_for_checkpoint_review | checkpoint_approved | archived
checkpoint_approved -> next_stage | closed_at_plan_checkpoint | upstream_gap_routing | archived
next_stage -> active_stage_draft | entry_gate_failed | archived
closed_at_plan_checkpoint -> executing | archived
executing -> executing | closed_at_plan_checkpoint | archived
archived -> none
```

Open-state transitions to `archived` are owned only by explicit `r2p-abandon`.
Successful `r2p-reopen` archives its direct closed/executing source after the
child is durable and refuses to create another child while the lineage already
has an active reopened run. Malformed source or same-lineage run records block
reopen with exit `6` before child/archive writes; never skip an unreadable sibling.

A closed run with `execution/` or execution-start owner residue needs recovery
through `r2p-execute`, or explicit `--force` archive for intentional abandonment.
Symlinked or non-directory execution paths remain unsafe even with `--force`.

### Artifact filenames

`00-raw-requirement.md` → `03-requirement-brief.md` → `04-risk-discovery.md` → `05-design.md` → `06-spec.md` → `07-plan.md`.

## Test rules

- Isolate CLI/shortcut tests with `tempfile.TemporaryDirectory` or pytest's `tmp_path` and pass the temporary directory as `base_path`. Installation tests also redirect platform homes and the manifest root. Never touch real `~/.req-to-plan/` or the repo's own `.req-to-plan/`.
- New features: write the test first (red → green). Keep the full suite green; describe its size qualitatively, **never** with a frozen number.
- `print_and_exit` calls `sys.exit`; tests calling `cli.main()` must catch `SystemExit`.
- `tests/test_docs_consistency.py` guards documentation and agent-template contracts:
  - `CLAUDE.md` must contain **no** hardcoded test count ("NN passing", "baseline: NN").
  - PLAN-author surfaces carry ambiguity/no-deferral rules and prerequisite v2 guidance. Both execution surfaces carry SDD, EXE-1..EXE-5, semantic-context, authoritative-progress, and metrics/recovery contracts in lockstep; execution templates must **not** mention `r2p-gap-open`. Use the test's token sets as the detailed checklist.
- `tests/test_readme.py` keeps `README.md` and `README.zh-CN.md` headings, commands, and key literals aligned; update both when public behavior changes.
- Wrapper/distribution changes need `tests/test_install.py`, `tests/test_bootstrap.py`, `tests/test_npm_package.py`, and, for the context wrapper, `tests/test_context_view_wrapper.py`. These isolated checks do not install into real agent homes.

## Repo-layout gotchas

- `docs/` is **tracked** design state (only `docs/archive/` is ignored). `.req-to-plan/` run dirs (`<work-id>/`) are **tracked** and committed by the path-scoped close/archive commit; only `.req-to-plan/archive`, `.workflow-active`, `<work-id>/logs/`, `<work-id>/execution/`, and the transient `<work-id>/.execution-start-transaction.json` owner are ignored (see `.req-to-plan/.gitignore`). `execution/` is ignored like `logs/`: the SDD execution ledger/reports/reviews are local audit trail, never shared git history (gates still read them from the working tree — "ignored" means "not shared via git," not "unimportant").
- `.claude/skills/` is local tool state, not the canonical project guide. The user-facing Claude install template is `tools/workflow_cli/agent_templates/claude/SKILL.md`.
- `.codegraph/` is present and indexed — prefer `codegraph explore` / `codegraph node` over grep+read when locating code.
- `.drfx/` holds archived local run artifacts, not source.
- Do not hardcode the package version in docs; `tools/workflow_cli/version.py` (`R2P_VERSION`) is the single source.

## Extending

- **Add a CLI command**: handler in `cli.py`, register it in the relevant `_register_*_commands`, use constants from `output.py`, add tests following the local `invoke()` helper pattern.
- **Expose an agent command**: add the executable `tools/r2p-*` wrapper and use `{{R2P_BIN_DIR}}/r2p-*` in templates; an internal argparse command alone is not an installed entrypoint. Preserve bootstrap isolation and argument forwarding. Update Claude/Codex contracts together and Gemini's corresponding guidance; verify derived OpenCode commands through install tests, not a new template directory.
- **Extend tier keywords**: edit `tools/workflow_cli/tier_keywords.yaml`; keep the modifier groups (`migration`, `cross_project`, `safety`, `dependency`, `scope_expanding`), add English + Chinese variants, rerun focused tier tests.

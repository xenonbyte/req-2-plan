# Spec

## Behavior Contracts

The "behavior" of this prose-only change is the exact load-bearing text that must
appear on **both** orchestration surfaces
(`tools/workflow_cli/agent_templates/claude/commands/r2p-execute.md`,
`tools/workflow_cli/agent_templates/codex/skills/r2p-execute/SKILL.md`) and the
assertions that guard it. Each contract names the surfaces it lands on; gemini
`r2p-execute.toml` is untouched.

### SPEC-CTXSET-001 Shared Authoritative Context Set block
Implements DES-ARCH-001 [ADDRESSED]. Both surfaces gain one shared top-level `## Authoritative Context Set` section (a
single canonical location per file, placed so the §2/§5/§6 dispatches can reference
it by name). It lists exactly these run-dir **paths**, each with a one-line domain
note, and states they are handed as paths and read directly, never pasted:
- `02-project-context.md` — planning-time repository baseline
- `03-requirement-brief.md` — goal / scope / non-goals / acceptance
- `04-risk-discovery.md` — cross-task risks and mitigations
- `05-design.md` — chosen design and rejected alternatives
- `06-spec.md` — full behavior / interface / data / error / test contracts
- `execution/progress.md` — execution ledger (task ID + title list), read-only to
  subagents

The block explicitly states that `07-plan.md`, `00-raw-requirement.md`, and
`01-intake-brief.md` are **not** in the set, and that no generated
`task-N-context.md` bundle, `context-manifest.json`, sha256/content-hash, or drift
gate is introduced.

### SPEC-DISPATCH-001 §2 implementer wiring
Implements DES-DISP-001 [ADDRESSED]. In the §2 implementer dispatch, **remove** the line
`Scene-setting context (project, dependencies, architectural constraints)` and
instead reference the Authoritative Context Set (the `02-project-context.md` pointer
supplies the project/dependency/architecture baseline deterministically). Retain:
the `brief_path` bullet, the `## Global Constraints` "copied verbatim when present"
bullet (pasted, unchanged), the TDD/`Verification` bullet, the report-path bullet,
and the minimal inline return contract.

### SPEC-DISPATCH-002 §5 task-reviewer wiring
Implements DES-DISP-001. In the §5 task-reviewer dispatch, add a reference to the Authoritative Context Set
alongside the existing `brief_path`, report path, `logs/task-N-diff.md` path, review
path, and pasted Global Constraints. State that the reviewer now checks
`Spec References` IDs against the **full** `06-spec.md` text, not the IDs alone. The
existing "Do not pass separate `Spec References`" instruction stays.

### SPEC-DISPATCH-003 §6 fix-subagent wiring
Implements DES-DISP-001. In the §6 fix dispatch, add a reference to the Authoritative Context Set, **the task
brief path**, and **the refreshed task diff path** (SPEC-DIFF-001). The two
existing guarded strings **must survive verbatim**:
`Pass the `review_report_path` to the fix subagent` and `Fix all Critical and
Important findings in the review report`; the "Do not paste the finding bodies"
instruction stays. (Required so
`test_execute_surfaces_route_reviewer_findings_through_report_paths` keeps passing.)

### SPEC-AUTH-001 Responsibility matrix + baseline/ledger/provenance rules
Implements DES-AUTH-001 [ADDRESSED]. Both surfaces carry a responsibility **matrix** (not a priority order) with one row
per authority: task brief → current task's execution scope/files/steps/verification;
`03` → goal/scope/non-goals/acceptance; `04` → risk constraints/mitigations; `05` →
chosen architecture and rejected alternatives; `06` → behavior/interface/data/error/
test contracts; `## Global Constraints` → plan-wide execution constraints; `02` →
planning-time baseline; current working tree / HEAD → operational truth about code
that exists now; `00`/`01` → provenance only, never an execution authority. Plus the
`02` baseline-vs-working-tree rule (a predecessor task's legitimate repo change makes
the working tree the operational truth; an unexplained/conflicting difference →
`BLOCKED`) and the ledger read-only rule (only the controller flips checkboxes or
appends `Resolved:`/`Gap:`/`Unresolved:`/`Minor:` records).

### SPEC-CONFLICT-001 Single conflict rule
Implements DES-AUTH-001. Both surfaces state: no artifact silently overrides another outside its domain; if a
task cannot satisfy all applicable authorities simultaneously, the subagent returns
`BLOCKED`, names the conflicting files/IDs, and asks the human to **reopen** the
owning stage — no guessing, no picking a winner, no patching around an upstream
defect. The wording uses **reopen**; the token `r2p-gap-open` must not appear on
either surface.

### SPEC-READ-001 Required consumption
Implements DES-READ-001 [ADDRESSED]. Both surfaces require each implementer, reviewer, and fix subagent to **read the
full Authoritative Context Set before acting** (availability is not consumption).
They **may skip** the embedded `(read-only)` Upstream Summary / Project Context
blocks within those files. On-demand (read-as-needed) depth applies only to the
current codebase, git history, and prior task reports/reviews — never to whether to
read an approved artifact. Stated as orthogonal to Model Selection.

### SPEC-OWN-001 Ledger ownership + sibling escalation
Implements DES-OWN-001 [ADDRESSED]. Both surfaces state that default position/ownership comes from the ledger's
`PLAN-TASK-NNN <title>` list (stay within the brief's Files/Steps; treat every other
listed task ID as owned elsewhere); the full `07-plan.md` is **not** handed to
subagents and whole-plan reasoning stays with the controller's Pre-flight read; an
unclear sibling boundary → the subagent returns `NEEDS_CONTEXT` / `BLOCKED` and the
controller resolves it or hands a specific `r2p-task-brief --task <M>` single-task
sibling brief and re-dispatches — never a whole-plan read or a guess from the title.

### SPEC-PATH-001 Path delivery + fail-closed preflight
Implements DES-PATH-001 [ADDRESSED]. Both surfaces state the delivery rule — the controller derives
`run_dir = parent(plan)` from the execute output and hands absolute paths by default,
or repository-root-relative paths paired with an explicit `repo_root` — and a
four-point fail-closed **preflight** each subagent runs before acting: (1) every
Authoritative Context Set path exists and is readable; (2) every handed context path,
brief path, ledger path, review path, and diff path resolves under the same derived
`run_dir`/`work_id`; (3) any repo-root-relative path was resolved against the handed
`repo_root`, not the process cwd; (4) `BLOCKED` if any path is missing, unreadable,
unresolved, or wired to a different run — no silent continue on a partial/mixed set.

### SPEC-DIFF-001 Refresh per-task diff after each fix wave
Implements DES-DIFF-001 [ADDRESSED]. In §6, after each fix wave the fix subagent commits only its intentionally-changed
files (exactly as the §2 implementer does), then the loop regenerates
`logs/task-N-diff.md` from the task's BASE to `HEAD` (the BASE recorded before §2)
via the single `git diff -U10 <base-commit> HEAD` commit-then-diff pattern, before
re-dispatching the task-reviewer. Both surfaces state explicitly that the re-review
must not run against an uncommitted working tree (a BASE→working-tree diff would miss
untracked new files).

## API / Data / Config Contracts

None. This change introduces no machine API, CLI command, flag, JSON/derived state
field, artifact-schema heading, gate, or config key, and changes no existing
command's output contract (`plan-task-brief` keeps `{work_id, task_id, brief_path}`).
The only "interfaces" touched are agent-facing template **prose** on the two named
surfaces and one new **test method** in `tests/test_docs_consistency.py`. The
authoritative-artifact filenames the prose references are existing fixed constants
(`models.py:83-88`, `context_pack.py:169-170`); no new constant is added.

## External Documentation Checked

N/A — no external dependencies

No external library, framework, SDK, API, CLI tool, or cloud service is involved, so
no Context7 / external-doc lookup is required. The new test uses only the Python
standard library (`unittest`, `re`, `pathlib`) and follows the in-repo
`tests/test_docs_consistency.py::TestExecuteTemplateContent` pattern already present;
`pytest` is the sole verification surface (no linter/formatter/type-checker is
configured in this repo).

## Test Matrix

One role-scoped assertion is added to
`tests/test_docs_consistency.py::TestExecuteTemplateContent` (implements
DES-TEST-001 [ADDRESSED]), driving both surfaces from the existing shared `surfaces`
list. The only new logic is a light helper that
slices the §2/§5/§6 bodies by `### ` headings (each role slice runs from its `### N.`
heading to the next `### ` **or** `## ` heading, so the §6 slice does not bleed into
`## Final Whole-Branch Review`).

| Test assertion | Verifies | Source |
|---|---|---|
| Shared block lists `02`,`03`,`04`,`05`,`06`,`execution/progress.md` on both surfaces | SPEC-CTXSET-001 | DES-TEST-001 |
| §2 implementer slice references the shared block; `Scene-setting context` absent | SPEC-DISPATCH-001 | DES-TEST-001 |
| §5 reviewer slice references the shared block | SPEC-DISPATCH-002 | DES-TEST-001 |
| §6 fix slice references the shared block, the task brief, and the refreshed diff | SPEC-DISPATCH-003 | DES-TEST-001 |
| Responsibility matrix + conflict rule (`BLOCKED` + reopen) present on both | SPEC-AUTH-001, SPEC-CONFLICT-001 | DES-TEST-001 |
| Ledger stated read-only to subagents | SPEC-AUTH-001 | DES-TEST-001 |
| `00-raw-requirement.md`/`01-intake-brief.md` absent from the set; `07-plan.md` not in the read set | SPEC-CTXSET-001, SPEC-OWN-001 | DES-TEST-001 |
| Targeted sibling escalation (`NEEDS_CONTEXT`/`BLOCKED` → `r2p-task-brief --task <M>`), no whole-plan read | SPEC-OWN-001 | DES-TEST-001 |
| §6 regenerates `logs/task-N-diff.md` before re-review | SPEC-DIFF-001 | DES-TEST-001 |
| `r2p-gap-open` still absent on both surfaces | SPEC-CONFLICT-001 | DES-TEST-001 |
| Existing report-path tokens still present (regression) | SPEC-DISPATCH-003 | observation 1 |
| Full suite green (`.venv/bin/python -m pytest tests/ -v`) | no collateral regression | Test Plan |

Tokens are stable, load-bearing phrases only; incidental wording is not pinned.

## Non-goals

- No generated `task-N-context.md` bundle, `context-manifest.json`, sha256/
  content-hash, or drift gate (audit-only boundary preserved).
- No whole-`07-plan.md` handoff to subagents (FR-CM5 preserved).
- No reference-closure re-resolution in any command.
- No new CLI command, state/JSON field, gate, transition, or artifact-schema change;
  no change to any existing command's output contract.
- No change to gemini `r2p-execute.toml` or to opencode (derived from claude).
- No full Markdown section parser in the test — only the light per-role heading
  slice.

## PLAN Handoff

The PLAN should sequence small, independently-verifiable tasks. Suggested shape:

1. **Claude surface prose** — apply SPEC-CTXSET-001, SPEC-DISPATCH-001/002/003,
   SPEC-AUTH-001, SPEC-CONFLICT-001, SPEC-READ-001, SPEC-OWN-001, SPEC-PATH-001,
   SPEC-DIFF-001 to `claude/commands/r2p-execute.md`.
2. **Codex surface prose** — apply the same contracts to
   `codex/skills/r2p-execute/SKILL.md`, byte-aligned on the guarded tokens.
3. **Docs-consistency test** — add the role-scoped assertion (Test Matrix) to
   `tests/test_docs_consistency.py`, including the regression check for the existing
   report-path tokens, then run the full suite to green.

Each task's `Verification` is the relevant docs-consistency assertion plus
`.venv/bin/python -m pytest tests/ -v`. (Whether the test lands before or with the
prose is a PLAN ordering choice; the docs-consistency test is the objective gate
either way.)

## Trace
<!-- Map this stage's IDs to upstream/downstream. R3 derives & checks closure. -->
| This ID | Upstream | Status |
|---|---|---|
| SPEC-CTXSET-001 | DES-ARCH-001 | open |
| SPEC-DISPATCH-001 | DES-DISP-001 | open |
| SPEC-DISPATCH-002 | DES-DISP-001 | open |
| SPEC-DISPATCH-003 | DES-DISP-001 | open |
| SPEC-AUTH-001 | DES-AUTH-001 | open |
| SPEC-CONFLICT-001 | DES-AUTH-001 | open |
| SPEC-READ-001 | DES-READ-001 | open |
| SPEC-OWN-001 | DES-OWN-001 | open |
| SPEC-PATH-001 | DES-PATH-001 | open |
| SPEC-DIFF-001 | DES-DIFF-001 | open |

## Upstream Summary (read-only)
# Design

## Design Summary

Enrich each `r2p-execute` subagent role with the authoritative upstream context by
**editing prose in the two orchestration surfaces** and **adding one role-scoped
docs-consistency test** — nothing else. The architecture is: define one shared
`## Authoritative Context Set` block listing the live run-dir artifact **paths**
(`02`/`03`/`04`/`05`/`06` + `execution/progress.md`), and have the §2 implementer,
§5 task-reviewer, and §6 fix dispatches each reference that block, require the
subagent to read the set before acting, and fail closed (`BLOCKED` /
`NEEDS_CONTEXT`) on conflict or unresolved path. Authority is stated as a
responsibility matrix with a single conflict rule (human **reopen**, never
`r2p-gap-open`). Position/ownership comes from the ledger; the whole `07-plan.md`
stays with the controller (preserving FR-CM5). The §6 fix loop is corrected to
commit then regenerate `logs/task-N-diff.md` from task BASE→`HEAD` before
re-review. No bundle, no manifest, no hash gate, no CLI/gate/state/schema change.

## Current Code Evidence

Verified directly against the two surfaces and the test:

- `claude/commands/r2p-execute.md` and `codex/skills/r2p-execute/SKILL.md` share the
  same `## Per-Task Loop` structure (§1 task-brief, §2 implementer, §3 status, §4
  ambiguity ladder, §5 diff+reviewer, §6 fix loop) plus `## Final Whole-Branch
  Review`.
- §2 implementer dispatch (claude `:60-65`, codex `:62-67`) hands `brief_path`, the
  ad-hoc line **"Scene-setting context (project, dependencies, architectural
  constraints)"**, `## Global Constraints` "copied verbatim when present", TDD
  instructions, and a report path. This is the line being replaced.
- §5 reviewer dispatch (claude `:98-103`) hands `brief_path` (Spec References read
  from the brief — "Do not pass separate `Spec References`"), the report path, the
  `logs/task-N-diff.md` path, the review path, and pasted Global Constraints.
- §6 fix loop (claude `:118-128`) hands **only** `review_report_path` ("Do not
  paste the finding bodies"), "Re-dispatch the task-reviewer after each fix wave"
  **without** regenerating `logs/task-N-diff.md` — the stale-diff bug.
- §5 already uses the commit-then-diff pattern `git diff -U10 <base-commit> HEAD >
  …/logs/task-N-diff.md`; the implementer commits "staging only files intentionally
  changed for this PLAN-TASK" (claude `:79`). The Final Whole-Branch Review already
  regenerates `logs/final-diff.md` after fixes — the per-task loop should match.
- `tests/test_docs_consistency.py::TestExecuteTemplateContent` already drives both
  surfaces from a shared `surfaces` list and asserts a `required` token tuple
  (`:76-113`), plus a `r2p-gap-open` absence guard (`:115-131`). The new assertion
  extends this exact shape with a light per-role heading slice.
- Authoritative artifact filenames are fixed constants (`models.py:83-88`,
  `context_pack.py:169-170`); `02-project-context.md` is generated once at run-start
  (`cli.py:348-349`); the ledger seeds `- [ ] PLAN-TASK-NNN <title>` per anchor
  (`cli.py:762`); the execute shortcut returns full `plan`/`ledger` paths + `work_id`
  (`agent_shortcuts._cmd_execute`); `run-reopen` creates a new run and never edits
  source artifacts in place.

## Requirements Coverage

| Requirement | Design element | Status |
|---|---|---|
| SCOPE-IN-001 (shared set block) | DES-ARCH-001 | covered |
| SCOPE-IN-002 (wire into §2/§5/§6; replace scene-setting) | DES-DISP-001 | covered |
| SCOPE-IN-003 (matrix + conflict + 02/ledger/provenance rules) | DES-AUTH-001 | covered |
| SCOPE-IN-004 (required consumption; skip read-only; depth scope) | DES-READ-001 | covered |
| SCOPE-IN-005 (ledger ownership; sibling escalation; no whole-plan) | DES-OWN-001 | covered |
| SCOPE-IN-006 (path delivery + fail-closed preflight) | DES-PATH-001 | covered |
| SCOPE-IN-007 (refresh task diff after fix wave) | DES-DIFF-001 | covered |
| SCOPE-IN-008 (role-scoped docs test) | DES-TEST-001 | covered |
| SCOPE-OUT-001/002/003 (gemini/CLI/00·01 untouched) | scope fence in DES-ARCH-001, DES-DISP-001 | honored |

Risk closure (from `04-risk-discovery.md`):
RISK-DOC-001 [ADDRESSED] by DES-TEST-001 (both-surface role-scoped assertion);
RISK-DOC-002 [ADDRESSED] by DES-TEST-001 (stable load-bearing tokens, no parser);
RISK-CTX-001 [ADDRESSED] by DES-PATH-001 (fail-closed preflight);
RISK-CTX-002 [ADDRESSED] by DES-OWN-001 (07 excluded; sibling escalation);
RISK-PATH-001 [ADDRESSED] by DES-PATH-001 (run_dir = parent(plan); repo_root);
RISK-DIFF-001 [ADDRESSED] by DES-DIFF-001 (commit-then-diff refresh);
RISK-AUD-001 [ADDRESSED] by DES-ARCH-001 (no bundle/manifest/hash — paths only);
RISK-SCOPE-001 [ADDRESSED] by DES-ARCH-001 (rejected-alternative fence);
RISK-SCOPE-002 [ADDRESSED] by DES-TEST-001 (light slice, no full parser);
RISK-SCOPE-003 [ADDRESSED] by DES-OWN-001 (fixed set excludes 07/00/01).

## Options Considered

- **Option A — Generated `task-N-context.md` bundle + `context-manifest.json` hash
  gate (REJECTED).** Deterministically concatenate the stripped artifacts plus a
  snapshot and a reference index, guarded by sha256 hashes that block execution on
  drift. Rejected: the bundle is a *second copy* of artifacts that are already live
  files, so it **manufactures the copy-divergence** the manifest then exists to
  police; reading `05-design.md` directly always returns current bytes. A
  content-hash drift gate is also an explicit Non-Goal of the prior FR-CM doc and
  crosses the deliberate audit-only boundary (`r2p-execution-gate-boundary`). The
  reference index duplicates each artifact's own trace table (already closure-gated
  at the PLAN quality gate); the snapshot duplicates `execution/progress.md`.
- **Option B — Hand the whole `07-plan.md` to subagents for sibling awareness
  (REJECTED).** Rejected: makes every implementer/reviewer/fix subagent read the
  whole plan on every task — exactly the leak FR-CM5 removed. Ownership awareness
  instead derives from the ledger's ID+title list, and an unclear boundary
  escalates to the controller for a single-task `r2p-task-brief --task <M>` brief.
- **Option C — Controller pastes a hand-written context summary into each dispatch
  (status quo, REJECTED).** This is the §2 "Scene-setting context" line itself: an
  LLM summarization of authority, the precise drift this work removes, and it also
  reloads into the controller's compounding context.
- **Option D — Live artifact paths, read directly (CHOSEN).** Hand fixed-name run-dir
  paths; require the one-shot subagent to read the originals. Cheapest (a discarded,
  non-compounding read per the leak hierarchy), in-grain with the existing
  "hand artifacts as file paths" architecture, and removes the copy-divergence class
  without any new machinery.

## Chosen Design

Option D. Eight design elements, all prose except DES-TEST-001:

### DES-ARCH-001 Shared `## Authoritative Context Set` block (live paths, no bundle)
Add one shared block to both surfaces listing the run-dir **paths**
`02-project-context.md`, `03-requirement-brief.md`, `04-risk-discovery.md`,
`05-design.md`, `06-spec.md`, and `execution/progress.md` (read-only to subagents),
each with a one-line domain note. Bodies are **never pasted**; `07-plan.md`,
`00-raw-requirement.md`, and `01-intake-brief.md` are **excluded**. No generated
bundle, `context-manifest.json`, sha256/hash, or drift gate is introduced.

### DES-DISP-001 Per-role dispatch wiring
- §2 implementer: **remove** the "Scene-setting context" line; reference the shared
  block (the `02-project-context.md` pointer carries the project/dependency/
  architecture baseline deterministically); keep `brief_path`, pasted `## Global
  Constraints`, TDD/`Verification`, report path, and the minimal return contract.
- §5 task-reviewer: reference the shared block alongside `brief_path`, report path,
  diff path, and review path (the full `06-spec.md` now resolves the brief's
  `Spec References` IDs to real contract text).
- §6 fix subagent: reference the shared block alongside `review_report_path`, the
  **task brief path**, and the **refreshed** task diff path; keep "do not paste the
  finding bodies".

### DES-AUTH-001 Responsibility matrix + single conflict rule
State authority as a domain-ownership **matrix** (task brief → execution scope;
`03` → goal/scope/non-goals/acceptance; `04` → risk constraints; `05` → chosen
architecture; `06` → behavior/interface/data/error/test contracts;
`## Global Constraints` → plan-wide execution constraints; `02` → planning-time
baseline; working tree/HEAD → operational truth; `00`/`01` → provenance only), not a
priority order. Add the `02` baseline-vs-working-tree rule, the ledger read-only
rule, and the single conflict rule: no artifact silently overrides another outside
its domain; on an unsatisfiable conflict return `BLOCKED`, name the conflicting
files/IDs, and ask the human to **reopen** the owning stage — no guessing, no
winner, no patch-around. Wording says **reopen**, never `r2p-gap-open`.

### DES-READ-001 Required consumption
Each subagent **must read the full Authoritative Context Set before acting**;
availability is not consumption. It **may skip** the embedded `(read-only)` Upstream
Summary / Project Context blocks (the canonical upstream is handed separately).
On-demand depth applies only to the current codebase, git history, and prior task
reports/reviews — never to whether to read an approved artifact. Orthogonal to Model
Selection: a cheap model on a mechanical task still reads the set.

### DES-OWN-001 Ledger ownership + targeted sibling escalation
Default position/ownership derives from the ledger's `PLAN-TASK-NNN <title>` list
(stay within the brief's Files/Steps; treat every other listed task ID as owned
elsewhere). The full `07-plan.md` is not handed; whole-plan reasoning stays with the
controller's Pre-flight read. An unclear sibling boundary → `NEEDS_CONTEXT` /
`BLOCKED`; the controller resolves it or hands a specific `r2p-task-brief --task <M>`
single-task brief and re-dispatches. The subagent never reads the whole plan file.

### DES-PATH-001 Path delivery + fail-closed preflight
Controller derives `run_dir = parent(plan)` from the execute output; hands absolute
paths by default, or repo-root-relative paths paired with an explicit `repo_root`.
Each subagent runs a preflight before acting: every Authoritative Context Set path,
brief path, ledger path, review path, and diff path exists, is readable, and
resolves under the same `run_dir`/`work_id`; repo-root-relative paths resolved
against `repo_root`, not the process cwd; else `BLOCKED` — no silent continue on a
partial/mixed set.

### DES-DIFF-001 Refresh per-task diff after each fix wave
The §6 fix subagent commits only its intentionally-changed files (exactly as the §2
implementer does); then the loop regenerates `logs/task-N-diff.md` from the task's
BASE to `HEAD` (the BASE the controller recorded before §2) via the single
commit-then-diff pattern, before re-dispatching the task-reviewer. No
uncommitted-working-tree re-review.

### DES-TEST-001 Role-scoped docs-consistency assertion
Extend `tests/test_docs_consistency.py::TestExecuteTemplateContent` over both
surfaces in the established `surfaces`-list + `required`-token-tuple shape. The only
new logic is a light helper that slices the §2/§5/§6 bodies by their `### ` headings
and asserts each role references the shared block — no full Markdown parser. Assert
the ten FR-AC7 checks (shared block lists `02`–`06` + `execution/progress.md`; each
role references it; conflict rule + matrix present; ledger read-only; `00`/`01`
absent and `07-plan.md` not in the read set; sibling escalation present; fix loop
regenerates `logs/task-N-diff.md`; `r2p-gap-open` still absent). Tokens are stable
and load-bearing only.

## Decision Requests
none

## Rollback

Pure prose + test change with no migration, state, schema, or data effect. Rollback
is a single `git revert` of the commit touching the two templates and the test;
already-installed agent homes are unaffected until the next `r2p` install, and a
revert simply restores the prior template text. No run state, artifact schema, or
on-disk workspace layout changes, so there is nothing to unwind.

## Observability

- The FR-AC7 docs-consistency test is the regression detector: it fails loudly in CI
  / `pytest` if either surface drifts (missing role reference, dropped rule, or a
  reintroduced `r2p-gap-open` / `07-plan.md` read).
- At runtime, a subagent that fails the preflight or hits an authority conflict
  returns `BLOCKED` / `NEEDS_CONTEXT`, which surfaces in controller narration and in
  `execution/progress.md` adjudication records (`Resolved:`/`Gap:`/`Unresolved:`).
- A missing/unreadable handed path produces a loud file-read failure, not a silent
  skip. No new metric, log sink, or state field is added (Non-Goal).

## SPEC Handoff

The SPEC must specify, for **both** surfaces, the exact load-bearing prose and the
test contract:

- SPEC for DES-ARCH-001: the shared `## Authoritative Context Set` block — the six
  listed paths with domain notes, the "paths not bodies" rule, and the explicit
  exclusion of `07`/`00`/`01` and of any bundle/manifest/hash.
- SPEC for DES-DISP-001: the §2/§5/§6 reference wording, the removal of the
  "Scene-setting context" line, and the §6 additions (brief path + refreshed diff).
- SPEC for DES-AUTH-001: the responsibility-matrix rows, the `02`
  baseline-vs-working-tree rule, the ledger read-only rule, the provenance rule, and
  the single conflict rule (`BLOCKED` + human **reopen**, no `r2p-gap-open`).
- SPEC for DES-READ-001: the required-read sentence, the skip-embedded-read-only
  allowance, and the on-demand-depth scoping.
- SPEC for DES-OWN-001: ledger-based ownership, the no-whole-plan rule, and the
  targeted `r2p-task-brief --task <M>` sibling escalation.
- SPEC for DES-PATH-001: `run_dir = parent(plan)`, absolute-or-`repo_root`-relative
  delivery, and the four-point fail-closed preflight.
- SPEC for DES-DIFF-001: the §6 commit-then-diff refresh of `logs/task-N-diff.md`
  from BASE→HEAD before re-review.
- SPEC for DES-TEST-001: the assertion's token list and the per-role heading-slice
  behavior, as a SPEC test contract; gemini `r2p-execute.toml` stays unchanged.

## Trace
<!-- Map this stage's IDs to upstream/downstream. R3 derives & checks closure. -->
| This ID | Upstream | Status |
|---|---|---|
| DES-ARCH-001 | SCOPE-IN-001, RISK-AUD-001, RISK-SCOPE-001 | open |
| DES-DISP-001 | SCOPE-IN-002 | open |
| DES-AUTH-001 | SCOPE-IN-003 | open |
| DES-READ-001 | SCOPE-IN-004 | open |
| DES-OWN-001 | SCOPE-IN-005, RISK-CTX-002, RISK-SCOPE-003 | open |
| DES-PATH-001 | SCOPE-IN-006, RISK-CTX-001, RISK-PATH-001 | open |
| DES-DIFF-001 | SCOPE-IN-007, RISK-DIFF-001 | open |
| DES-TEST-001 | SCOPE-IN-008, RISK-DOC-001, RISK-DOC-002, RISK-SCOPE-002 | open |
<!-- /r2p-read-only -->

## Project Context (read-only)
# Project Context Pack

- repo_root: `/Users/xubo/x-skills/req-to-plan`
- languages: {'Python': 21931, 'JavaScript': 31}
- package_managers: npm, pip
- test_commands: ['npm test']
- entrypoints: ['tools/workflow_cli/__main__.py']
- config_files: ['requirements.txt']
- dependencies (1):
  - pyyaml>=6.0 (pip)
- source_dirs: ['bin', 'docs', 'tests', 'tools']
<!-- /r2p-read-only -->

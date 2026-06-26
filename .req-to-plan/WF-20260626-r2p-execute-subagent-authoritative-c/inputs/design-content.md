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

## Upstream Summary (read-only)
# Risk Discovery

## Risks

### RISK-DOC-001 Wording drift between the claude and codex surfaces
Status: open — mitigated by MIT-001
The same authoritative-context prose must land in **both**
`agent_templates/claude/commands/r2p-execute.md` and
`agent_templates/codex/skills/r2p-execute/SKILL.md`. If one surface omits a role
reference, a rule, or the shared block, subagents on that platform stay
under-contextualized — the exact drift this work removes — but on only one
surface, so it is easy to miss by eye. Likelihood: medium. Impact: high
(silent per-platform regression).

### RISK-DOC-002 Over-tokenized / brittle docs-consistency test
Status: open — mitigated by MIT-002
The FR-AC7 assertion could pin incidental wording, making every legitimate future
edit to the template fail the gate and pressuring authors to weaken or delete the
guard. Likelihood: medium. Impact: medium (long-term erosion of the guard).

### RISK-CTX-001 "Required-read" degrades into "read whatever is present"
Status: open — mitigated by MIT-003
On a corrupted, partial, or manually-edited run a handed path may be missing,
unreadable, or wired to a different run. Without a fail-closed rule a subagent
could silently continue on a partial set, reproducing the under-contextualization
the work removes while appearing to comply. Likelihood: low. Impact: high.

### RISK-CTX-002 Reintroducing the whole-plan read (FR-CM5 regression)
Status: open — mitigated by MIT-004
The natural way to give a subagent sibling-boundary awareness is to hand it
`07-plan.md`. Doing so makes every implementer/reviewer/fix subagent read the whole
plan on every task — precisely the leak FR-CM5 removed. Likelihood: medium (it is
the tempting fix). Impact: high (undoes shipped work).

### RISK-PATH-001 Path resolution against the wrong cwd / wrong run
Status: open — mitigated by MIT-005
In `--base-path`, cross-project, and `cwd ≠ target repo` cases, repo-root-relative
paths resolved against the process cwd can point a subagent at the wrong run or the
wrong repository — reading or even modifying unrelated state. Likelihood: low.
Impact: high (acts on wrong files).

### RISK-DIFF-001 Stale per-task diff at re-review
Status: open — mitigated by MIT-006
The §6 fix loop today re-dispatches the task-reviewer without regenerating
`logs/task-N-diff.md`, so the reviewer can re-read the **pre-fix** diff and approve
a fix it never actually saw, or a `BASE`→working-tree diff can miss untracked new
files. Likelihood: medium. Impact: medium (false-green per-task review).

### RISK-AUD-001 Crossing the audit-only trust boundary
Status: open — mitigated by MIT-007
The rejected bundle/manifest alternative is reachable by a well-meaning
"just add a sha256 drift gate" instinct. Adding any content-hash/drift gate would
violate the deliberate audit-only boundary (`r2p-execution-gate-boundary`) and
manufacture the copy-divergence it then polices. Likelihood: low. Impact: high
(architecture-level regression).

## Boundaries

- **Files touched:** exactly two template surfaces
  (`claude/commands/r2p-execute.md`, `codex/skills/r2p-execute/SKILL.md`) plus
  `tests/test_docs_consistency.py`. Everything else — `cli.py`, `gates.py`,
  `state.py`, `artifact.py`, `agent_shortcuts.py`, the `tools/r2p-*` wrappers, and
  `gemini/commands/r2p-execute.toml` — is **out of bounds** for this change.
- **Behavior boundary:** prose + test only. No machine gate, state transition,
  artifact schema, CLI command, JSON/derived field, or command output contract is
  added or changed.
- **Authority boundary:** subagents may **read** the Authoritative Context Set and
  the codebase, and **write** only their own task's code, report, review, and diff
  files; `execution/progress.md` is read-only to subagents (only the controller
  flips checkboxes / appends adjudication records).
- **Failure boundary:** on any unsatisfiable conflict or missing/unresolved path a
  subagent **fails closed** (`BLOCKED` / `NEEDS_CONTEXT`) and escalates to the
  controller or a human **reopen**; it never guesses, picks a winner, or patches
  around an upstream defect. Execution runs are `closed`, so routing is reopen —
  **never** `r2p-gap-open`.

## Scope Overflow Risks

### RISK-SCOPE-001 Rebuilding the rejected bundle / manifest / snapshot machinery
Status: open — mitigated by MIT-007
The decisive design choice is live artifact paths, not a generated
`task-N-context.md` bundle, a `context-manifest.json`, a hash gate, a reference
index, or a progress snapshot. Each rejected piece is individually tempting; adding
any of them re-creates the copy-divergence and trust-boundary problems the design
exists to avoid.

### RISK-SCOPE-002 Over-engineering the docs test into a section parser
Status: open — mitigated by MIT-002
FR-AC7 asks for a **light** per-role heading slice, not a full Markdown section
parser. Building a parser inflates scope and fragility for no added guarantee.

### RISK-SCOPE-003 Expanding the authoritative set beyond the named artifacts
Status: open — mitigated by MIT-004
Pressure to add `07-plan.md`, `00-raw-requirement.md`, or `01-intake-brief.md` to
the read set. `07` is the FR-CM5 regression; `00`/`01` are provenance whose
consequences already live in `03`–`06`. The set is fixed at
`02`/`03`/`04`/`05`/`06`/`execution/progress.md`.

## Mitigations

- **MIT-001** (RISK-DOC-001): the FR-AC7 role-scoped docs-consistency test asserts
  both surfaces, slicing the §2/§5/§6 bodies by their `### ` headings so a filename
  present once cannot mask a role that omits the reference.
- **MIT-002** (RISK-DOC-002, RISK-SCOPE-002): assert only stable, load-bearing
  phrases; reuse the existing whole-file token-presence pattern; add only the light
  per-role slice, no full parser.
- **MIT-003** (RISK-CTX-001): a fail-closed context **preflight** in subagent prose
  — every Authoritative Context Set path exists, is readable, and resolves under the
  same `run_dir`/`work_id`, else `BLOCKED`; no silent continue on a partial/mixed
  set.
- **MIT-004** (RISK-CTX-002, RISK-SCOPE-003): exclude `07-plan.md` from the set;
  ownership awareness derives from the ledger's `PLAN-TASK-NNN <title>` list; an
  unclear sibling boundary escalates (`NEEDS_CONTEXT`/`BLOCKED`) to the controller,
  which hands a specific `r2p-task-brief --task <M>` sibling brief — never a
  whole-plan read. The docs test asserts `07-plan.md` is absent from the set.
- **MIT-005** (RISK-PATH-001): controller derives `run_dir = parent(plan)` from the
  execute output; hands absolute paths by default, or repo-root-relative paths
  paired with an explicit `repo_root`; the preflight confirms repo-root-relative
  paths resolved against `repo_root`, not the process cwd.
- **MIT-006** (RISK-DIFF-001): the §6 fix loop regenerates `logs/task-N-diff.md`
  from the task's BASE to `HEAD` after each fix wave, via the single
  commit-then-diff pattern (fix subagent commits only its intentionally-changed
  files first), before re-dispatching the reviewer.
- **MIT-007** (RISK-AUD-001, RISK-SCOPE-001): the Non-Goals and the docs-consistency
  test forbid a generated bundle, `context-manifest.json`, sha256/content-hash, and
  any drift gate; out-of-band source mutation stays a trust assumption, consistent
  with the audit-only boundary.

## Trace
<!-- Map this stage's IDs to upstream/downstream. R3 derives & checks closure. -->
| This ID | Upstream | Status |
|---|---|---|
| RISK-DOC-001 | SCOPE-IN-001, SCOPE-IN-008 | open |
| RISK-DOC-002 | SCOPE-IN-008 | open |
| RISK-CTX-001 | SCOPE-IN-004, SCOPE-IN-006 | open |
| RISK-CTX-002 | SCOPE-IN-005 | open |
| RISK-PATH-001 | SCOPE-IN-006 | open |
| RISK-DIFF-001 | SCOPE-IN-007 | open |
| RISK-AUD-001 | SCOPE-OUT-002 | open |
| RISK-SCOPE-001 | SCOPE-OUT-002 | open |
| RISK-SCOPE-002 | SCOPE-IN-008 | open |
| RISK-SCOPE-003 | SCOPE-IN-001, SCOPE-IN-005 | open |
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

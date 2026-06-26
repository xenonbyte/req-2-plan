# Plan

## Global Constraints

- **Both surfaces stay byte-aligned on all guarded tokens.** Apply the identical
  prose intent to `claude/commands/r2p-execute.md` and
  `codex/skills/r2p-execute/SKILL.md`; the docs-consistency test asserts both.
- **Do not touch out-of-scope files:** `gemini/commands/r2p-execute.toml`, opencode,
  `cli.py`, `gates.py`, `state.py`, `artifact.py`, `agent_shortcuts.py`, and any
  `tools/r2p-*` wrapper. No CLI command, flag, state/JSON field, gate, transition,
  or artifact-schema change; no change to `plan-task-brief`'s output.
- **Preserve existing guarded tokens** when rewording §6: keep
  `Pass the `review_report_path` to the fix subagent` and `Fix all Critical and
  Important findings in the review report` verbatim, and keep `r2p-gap-open` absent
  from both surfaces (conflict prose says **reopen**).
- **No new dependency.** `.venv/bin/python -m pytest` is the only verification
  surface (no linter/formatter/type-checker is configured).
- **Test discipline:** assert only stable, load-bearing phrases; the per-role slice
  runs from each `### N.` heading to the next `### ` or `## ` heading; no full
  Markdown parser.
- **Audit-only / FR-CM5 preserved:** no bundle, `context-manifest.json`,
  sha256/hash, or drift gate; never add the whole `07-plan.md` to the subagent read
  set.

## Tasks
### PLAN-TASK-001 Claude r2p-execute: Authoritative Context Set + role wiring + rules
Spec References: SPEC-CTXSET-001, SPEC-DISPATCH-001, SPEC-DISPATCH-002, SPEC-DISPATCH-003, SPEC-AUTH-001, SPEC-CONFLICT-001, SPEC-READ-001, SPEC-OWN-001, SPEC-PATH-001, SPEC-DIFF-001
Scope items carried: SCOPE-IN-001, SCOPE-IN-002, SCOPE-IN-003, SCOPE-IN-004, SCOPE-IN-005, SCOPE-IN-006, SCOPE-IN-007
Change Type: modify
TDD Applicable: no
Files:
- tools/workflow_cli/agent_templates/claude/commands/r2p-execute.md
Skeleton:
```markdown
## Authoritative Context Set

Hand each subagent these run-dir paths (absolute, or repo-root-relative paired with
an explicit `repo_root`); read the files directly, never pasted, never summarized:
- `02-project-context.md` — planning-time repository baseline
- `03-requirement-brief.md` — goal / scope / non-goals / acceptance
- `04-risk-discovery.md` — cross-task risks and mitigations
- `05-design.md` — chosen design and rejected alternatives
- `06-spec.md` — full behavior / interface / data / error / test contracts
- `execution/progress.md` — execution ledger (task ID + title list), read-only to subagents

Not in the set: `07-plan.md`, `00-raw-requirement.md`, `01-intake-brief.md`. No
generated bundle, `context-manifest.json`, sha256/hash, or drift gate.

(then in §2/§5/§6:) Read the Authoritative Context Set before acting.
```
Steps:
- [ ] Add the shared `## Authoritative Context Set` section (one canonical location) per SPEC-CTXSET-001, listing the six paths with domain notes and the exclusions.
- [ ] §2 implementer (SPEC-DISPATCH-001): remove the `Scene-setting context (project, dependencies, architectural constraints)` line; add a "Read the Authoritative Context Set before acting" reference plus the `02-project-context.md` pointer; keep `brief_path`, pasted `## Global Constraints`, TDD/Verification, report path, return contract.
- [ ] §5 task-reviewer (SPEC-DISPATCH-002): add the same reference; state the reviewer checks `Spec References` against the full `06-spec.md`.
- [ ] §6 fix subagent (SPEC-DISPATCH-003): add the reference, the task brief path, and the refreshed task diff path; keep the two guarded report-path tokens verbatim and "do not paste the finding bodies".
- [ ] Add the responsibility matrix + `02` baseline/ledger-read-only/`00`-`01`-provenance rules (SPEC-AUTH-001) and the single conflict rule `BLOCKED` + human **reopen** (SPEC-CONFLICT-001).
- [ ] Add required-consumption (SPEC-READ-001), ledger ownership + sibling escalation via `r2p-task-brief --task <M>` (SPEC-OWN-001), path delivery + fail-closed preflight (SPEC-PATH-001), and the §6 commit-then-diff refresh of `logs/task-N-diff.md` before re-review (SPEC-DIFF-001).
Verification: `.venv/bin/python -m pytest tests/ -v` stays green; and `grep -q '## Authoritative Context Set' tools/workflow_cli/agent_templates/claude/commands/r2p-execute.md && ! grep -q 'Scene-setting context' tools/workflow_cli/agent_templates/claude/commands/r2p-execute.md` exits 0.

### PLAN-TASK-002 Codex r2p-execute: mirror the same Authoritative Context Set prose
Spec References: SPEC-CTXSET-001, SPEC-DISPATCH-001, SPEC-DISPATCH-002, SPEC-DISPATCH-003, SPEC-AUTH-001, SPEC-CONFLICT-001, SPEC-READ-001, SPEC-OWN-001, SPEC-PATH-001, SPEC-DIFF-001
Scope items carried: SCOPE-IN-001, SCOPE-IN-002, SCOPE-IN-003, SCOPE-IN-004, SCOPE-IN-005, SCOPE-IN-006, SCOPE-IN-007
Change Type: modify
TDD Applicable: no
Files:
- tools/workflow_cli/agent_templates/codex/skills/r2p-execute/SKILL.md
Skeleton:
```markdown
## Authoritative Context Set
(identical content and per-role references as PLAN-TASK-001, byte-aligned on the
guarded tokens so the docs-consistency assertion passes on both surfaces)
```
Steps:
- [ ] Apply the PLAN-TASK-001 edits to `codex/skills/r2p-execute/SKILL.md`, keeping the prose byte-aligned with the claude surface on every guarded token.
- [ ] Confirm `Scene-setting context` is removed and the two report-path tokens and `r2p-gap-open` absence are preserved.
Verification: `.venv/bin/python -m pytest tests/ -v` stays green; and `grep -q '## Authoritative Context Set' tools/workflow_cli/agent_templates/codex/skills/r2p-execute/SKILL.md && ! grep -q 'Scene-setting context' tools/workflow_cli/agent_templates/codex/skills/r2p-execute/SKILL.md` exits 0.

### PLAN-TASK-003 Role-scoped docs-consistency assertion (claude + codex)
Spec References: SPEC-CTXSET-001, SPEC-DISPATCH-001, SPEC-DISPATCH-002, SPEC-DISPATCH-003, SPEC-AUTH-001, SPEC-CONFLICT-001, SPEC-READ-001, SPEC-OWN-001, SPEC-PATH-001, SPEC-DIFF-001
Scope items carried: SCOPE-IN-008
Change Type: modify
TDD Applicable: yes
Files:
- tests/test_docs_consistency.py
Skeleton:
```python
class TestExecuteTemplateContent(unittest.TestCase):
    def test_execute_surfaces_hand_authoritative_context_set(self):
        surfaces = [
            "tools/workflow_cli/agent_templates/claude/commands/r2p-execute.md",
            "tools/workflow_cli/agent_templates/codex/skills/r2p-execute/SKILL.md",
        ]
        shared_block_tokens = (
            "## Authoritative Context Set",
            "02-project-context.md", "03-requirement-brief.md",
            "04-risk-discovery.md", "05-design.md", "06-spec.md",
            "execution/progress.md",
        )
        # per-role slice: from "### N." heading to next "### " or "## " heading
        def role_slice(text, marker):
            ...
        for rel in surfaces:
            text = (REPO_ROOT / rel).read_text(encoding="utf-8")
            # shared block lists 02..06 + progress; 00/01 absent; 07-plan not in read set
            # §2/§5/§6 slices each reference the set; matrix + conflict rule present
            # ledger read-only; sibling escalation via r2p-task-brief --task; gap-open absent
            # §6 regenerates logs/task-N-diff.md; report-path tokens still present
            ...
```
Steps:
- [ ] Add a token-list assertion (existing `surfaces`-list shape) covering the shared block list (`02`..`06` + `execution/progress.md`), the matrix + conflict rule, ledger read-only, sibling escalation, the §6 diff regeneration, `00`/`01` absent, `07-plan.md` not in the read set, and `r2p-gap-open` still absent (SCOPE-IN-008).
- [ ] Add a light per-role helper that slices §2/§5/§6 by `### N.`→next `### `/`## ` and asserts each role references the shared block; assert `Scene-setting context` is gone and the two report-path tokens survive.
- [ ] Keep tokens stable/load-bearing; no full Markdown parser.
Verification: `.venv/bin/python -m pytest tests/test_docs_consistency.py -v` passes (new assertion green on both surfaces) and `.venv/bin/python -m pytest tests/ -v` stays green.

## Trace
<!-- Map this stage's IDs to upstream/downstream. R3 derives & checks closure. -->
| This ID | Upstream | Status |
|---|---|---|
| PLAN-TASK-001 | SPEC-CTXSET-001, SPEC-DISPATCH-001/002/003, SPEC-AUTH-001, SPEC-CONFLICT-001, SPEC-READ-001, SPEC-OWN-001, SPEC-PATH-001, SPEC-DIFF-001 | open |
| PLAN-TASK-002 | (same SPEC set, codex surface) | open |
| PLAN-TASK-003 | SCOPE-IN-008; verifies all ten SPEC contracts | open |

## Upstream Summary (read-only)
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

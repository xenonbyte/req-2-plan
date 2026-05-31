# Part 2 — Remove the Superpowers Adapter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Delete the redundant post-PLAN superpowers adapter (the neutral PLAN already runs in superpowers; the adapter failed with a `.repair.md` on a real run), shrinking the `r2p-*` shortcut set from 6 to 5, and deterministically clean up the stale `r2p-adapt` wrapper during install/reinstall/uninstall.

**Architecture:** Pure deletion + manifest-consistent cleanup. No run.md format change, no new behavior. Install discovery is glob-based, so deleting template files stops fresh installs from picking them up; the only added code is manifest-driven removal of obsolete managed shared `bin/r2p-*` wrappers from all platform manifests during install/reinstall/uninstall.

**Tech Stack:** Python 3.10+ stdlib. Tests run with `.venv/bin/python -m pytest`.

**Design source:** `docs/2026-05-30-workflow-fixes-and-plan-optimization.md` Part 2 (Approved). Outward-facing removal — maintainer-approved.

**Pre-verified facts (2026-05-31):**
- `tools/workflow_cli/agent_shortcuts.py` contains `_cmd_adapt`, the `adapt` subparser, the
  `adapt` handler entry, and possibly a closed-run hint that references `r2p-adapt`.
- `tools/workflow_cli/models.py` contains `CMD-EXEC-LIST-ADAPTERS` in `READ_ONLY_COMMANDS` and
  `CMD-EXEC-ADAPT` in the closed-at-plan-checkpoint allowed-command set.
- Adapter tests: `tests/test_adapters_superpowers.py` (18), `tests/test_agent_shortcuts.py` adapt
  cases (2), `tests/test_integration.py` executor-adapt class (3), and `tests/test_models.py`
  CMD-EXEC cases (2). Total 25.
- `InstallService.uninstall` skips shared `bin/` paths when other platform manifests are installed.

**Run tests:** `.venv/bin/python -m pytest` (never bare `pytest`). Commit only at green checkpoints.
Tasks 1-5 are one interdependent removal block; do not commit a known-red intermediate deletion.

---

### Execution safety preflight

- [ ] **Step 1: Verify an isolated worktree**

Run:
```bash
git status --short
```
Expected: empty before starting. If it is not empty, stop and either commit/stash unrelated work or
move this plan to a clean worktree. Do not stage unrelated local changes into Part 2 commits.

- [ ] **Step 2: Use explicit staging only**

Do not use `git add -A`. Every commit step below uses explicit pathspecs. Before each commit, run
`git diff --cached --name-only` and compare it to that task's listed working set; stop if unrelated
paths are staged.

### Preflight: Capture current adapter behavior before deletion

- [ ] **Step 1: Run current-state adapter checks**

Run these checks before Task 1 deletes the adapter package, wrapper, and adapter tests. Later tasks
must not expect these current-state adapter tests to pass after deletion has begun.

```bash
cd /Users/xubo/x-skills/req-to-plan
.venv/bin/python -m pytest tests/test_adapters_superpowers.py -v
.venv/bin/python -m pytest tests/test_agent_shortcuts.py -k adapt -v
.venv/bin/python -m pytest tests/test_integration.py -k adapt -v
.venv/bin/python -m pytest tests/test_models.py -k "cmd_exec" -v
```

Expected: PASS before any Part 2 deletion. If this preflight is skipped, do not reintroduce the
adapter just to make these deleted-surface tests pass; proceed with the removal tasks and use the
post-removal verification steps below.

### Task 1: Remove the adapter package, templates, wrapper, and docs

**Files:**
- Delete: `tools/workflow_cli/adapters/superpowers.py`, `tools/workflow_cli/adapters/__init__.py`, `tools/workflow_cli/adapters/README.md`
- Delete: `tools/r2p-adapt`
- Delete: `tools/workflow_cli/agent_templates/claude/commands/r2p-adapt.md`
- Delete: `tools/workflow_cli/agent_templates/codex/skills/r2p-adapt/SKILL.md`
- Delete: `tools/workflow_cli/agent_templates/gemini/commands/r2p-adapt.toml`
- Delete: `tests/test_adapters_superpowers.py`
- Delete: `docs/workflow-post-plan-adapter-surface.md`

- [ ] **Step 1: Delete the files**

```bash
cd /Users/xubo/x-skills/req-to-plan
git rm tools/workflow_cli/adapters/superpowers.py \
       tools/workflow_cli/adapters/__init__.py \
       tools/workflow_cli/adapters/README.md \
       tools/r2p-adapt \
       tools/workflow_cli/agent_templates/claude/commands/r2p-adapt.md \
       "tools/workflow_cli/agent_templates/codex/skills/r2p-adapt/SKILL.md" \
       tools/workflow_cli/agent_templates/gemini/commands/r2p-adapt.toml \
       tests/test_adapters_superpowers.py \
       docs/workflow-post-plan-adapter-surface.md
rm -rf tools/workflow_cli/adapters
```

- [ ] **Step 2: Verify the package directory is gone**

Run: `ls tools/workflow_cli/adapters 2>&1`
Expected: "No such file or directory".

- [ ] **Step 3: Defer commit until the code/test removal block is green**

```bash
git diff --cached --name-only -- \
  tools/workflow_cli/adapters/superpowers.py \
  tools/workflow_cli/adapters/__init__.py \
  tools/workflow_cli/adapters/README.md \
  tools/r2p-adapt \
  tools/workflow_cli/agent_templates/claude/commands/r2p-adapt.md \
  "tools/workflow_cli/agent_templates/codex/skills/r2p-adapt/SKILL.md" \
  tools/workflow_cli/agent_templates/gemini/commands/r2p-adapt.toml \
  tests/test_adapters_superpowers.py \
  docs/workflow-post-plan-adapter-surface.md
```
Expected: only the Task 1 deletions. Do not commit yet; Tasks 2-5 remove dependent code/tests and
produce the first green checkpoint.

### Task 2: Remove `_cmd_adapt` from agent_shortcuts and its tests

**Files:**
- Modify: `tools/workflow_cli/agent_shortcuts.py` (`_cmd_adapt`, `adapt` subparser, `adapt` handler entry, and any closed-run `r2p-adapt` hint)
- Modify: `tests/test_agent_shortcuts.py` (delete the 2 adapt tests)

- [ ] **Step 1: Confirm current-state shortcut coverage was handled before deletion**

Do not rerun the current-state `tests/test_agent_shortcuts.py -k adapt` expectation after Task 1.
It is covered by the preflight. At this point the adapter wrapper/package may already be gone, so
the executable check for this task is the post-removal shortcut suite in Step 4 plus the invalid
subcommand check in Step 5.

- [ ] **Step 2: Delete `_cmd_adapt` and its wiring**

In `agent_shortcuts.py`:
- Delete the entire `def _cmd_adapt(...)` function.
- Delete the `p_adapt = sub.add_parser("adapt")` and `p_adapt.add_argument("--executor", required=True)` lines.
- Delete the `"adapt": _cmd_adapt,` entry from the `handlers` dict.
- In `_cmd_continue`'s run-closed branch, if it still references `r2p-adapt --executor superpowers`, change the hint to: `next: run is closed; PLAN is at 07-plan.md; hand it to your executor`. (If Part 1 already rewrote `_cmd_continue`, this is already done — verify and skip.)

- [ ] **Step 3: Delete the 2 adapt tests**

In `tests/test_agent_shortcuts.py`, delete `test_missing_run_record_stops_before_adapter` and `test_malformed_run_record_stops_before_adapter`.

- [ ] **Step 4: Run to verify shortcuts still work**

Run: `.venv/bin/python -m pytest tests/test_agent_shortcuts.py -v`
Expected: PASS; no `adapt` subcommand remains.

- [ ] **Step 5: Verify the subcommand is gone**

Run: `.venv/bin/python -m tools.workflow_cli.agent_shortcuts adapt --executor superpowers 2>&1 | head -2`
Expected: argparse error "invalid choice: 'adapt'".

- [ ] **Step 6: Defer commit until Task 5**

Do not commit yet; this task is part of the Tasks 1-5 green checkpoint.

### Task 3: Remove CMD-EXEC adapter intents from the model

**Files:**
- Modify: `tools/workflow_cli/models.py` (`CMD-EXEC-LIST-ADAPTERS` in `READ_ONLY_COMMANDS`; `CMD-EXEC-ADAPT` in the closed-at-plan-checkpoint allowed-command set)
- Modify: `tests/test_models.py` (delete the 2 CMD-EXEC tests)

- [ ] **Step 1: Run the CMD-EXEC tests to confirm they currently pass**

Run: `.venv/bin/python -m pytest tests/test_models.py -k "cmd_exec" -v`
Expected: PASS (2 tests).

- [ ] **Step 2: Remove the intents**

In `models.py`:
- Delete `"CMD-EXEC-LIST-ADAPTERS",` from `READ_ONLY_COMMANDS`.
- Delete `"CMD-EXEC-ADAPT",` from `ALLOWED_COMMANDS_BY_RUN_STATE[RunStatus.CLOSED_AT_PLAN_CHECKPOINT]`. Leave `CMD-RUN-REOPEN` / `CMD-TIER-STATUS` in that set.

- [ ] **Step 3: Delete the 2 tests**

In `tests/test_models.py`, delete `test_cmd_exec_list_adapters_allowed_in_any_state` and `test_cmd_exec_adapt_allowed_in_closed_at_plan_checkpoint`.

- [ ] **Step 4: Run to verify**

Run: `.venv/bin/python -m pytest tests/test_models.py -v`
Expected: PASS.

- [ ] **Step 5: Defer commit until Task 5**

Do not commit yet; this task is part of the Tasks 1-5 green checkpoint.

### Task 4: Remove the executor-adapt integration test class

**Files:**
- Modify: `tests/test_integration.py` (delete the executor-adapt class: 3 tests + class docstring)

- [ ] **Step 1: Confirm current-state integration coverage was handled before deletion**

Do not rerun the current-state `tests/test_integration.py -k adapt` expectation after Task 1.
It is covered by the preflight. At this point the adapter wrapper/package may already be gone, so
the executable check for this task is the post-removal integration suite in Step 3.

- [ ] **Step 2: Delete the class**

In `tests/test_integration.py`, delete the entire executor-adapt test class (the class docstring "Tests for executor adapt via agent_shortcuts." plus the 3 methods).

- [ ] **Step 3: Run to verify**

Run: `.venv/bin/python -m pytest tests/test_integration.py -v`
Expected: PASS; no adapt references remain.

- [ ] **Step 4: Defer commit until Task 5**

Do not commit yet; this task is part of the Tasks 1-5 green checkpoint.

### Task 5: Update the codex install test (drop r2p-adapt)

**Files:**
- Modify: `tests/test_install.py` (`test_install_codex_copies_shortcut_skills`)

- [ ] **Step 1: Run the install test to see it currently expects r2p-adapt**

Run: `.venv/bin/python -m pytest tests/test_install.py::test_install_codex_copies_shortcut_skills -v` (or the class-qualified name)
Expected: at this point it may FAIL because Task 1 deleted the codex `r2p-adapt` template — the test still lists `"r2p-adapt"`.

- [ ] **Step 2: Remove the entry**

In `tests/test_install.py`, delete the `"r2p-adapt",` line from the codex command list in `test_install_codex_copies_shortcut_skills`.

- [ ] **Step 3: Run to verify**

Run: `.venv/bin/python -m pytest tests/test_install.py -v`
Expected: PASS.

- [ ] **Step 4: Commit the green Tasks 1-5 removal block**

```bash
git add -u -- \
  tools/workflow_cli/adapters/superpowers.py \
  tools/workflow_cli/adapters/__init__.py \
  tools/workflow_cli/adapters/README.md \
  tools/r2p-adapt \
  tools/workflow_cli/agent_templates/claude/commands/r2p-adapt.md \
  "tools/workflow_cli/agent_templates/codex/skills/r2p-adapt/SKILL.md" \
  tools/workflow_cli/agent_templates/gemini/commands/r2p-adapt.toml \
  tests/test_adapters_superpowers.py \
  docs/workflow-post-plan-adapter-surface.md \
  tools/workflow_cli/agent_shortcuts.py \
  tests/test_agent_shortcuts.py \
  tools/workflow_cli/models.py \
  tests/test_models.py \
  tests/test_integration.py \
  tests/test_install.py
git diff --cached --name-only
git commit -m "feat: remove superpowers adapter surface"
```
Expected staged paths: exactly the Tasks 1-5 files listed above.

### Task 6: Deterministic install/reinstall/uninstall cleanup of the stale shared wrapper

**Files:**
- Modify: `tools/workflow_cli/install.py` (install and uninstall paths; uses manifests under `manifest_root/install`)
- Test: `tests/test_install.py`

- [ ] **Step 1: Write the failing upgrade and uninstall cleanup tests**

Add to `tests/test_install.py` (reuse the existing `make_service(tmp_path)` helper). These tests
must preseed a 0.1.2-style stale managed shared wrapper into multiple installed platform
manifests, then assert both filesystem cleanup and manifest cleanup:

```python
def test_upgrade_removes_stale_shared_wrapper_from_all_manifests(tmp_path):
    svc, manifest_root, ph_root = make_service(tmp_path)
    svc.install("claude")
    svc.install("codex")
    # Simulate a 0.1.2 leftover: a managed bin wrapper no longer in the template set.
    bin_dir = manifest_root / "bin"
    stale = bin_dir / "r2p-adapt"
    stale.write_text("#!/usr/bin/env bash\n", encoding="utf-8")
    seed_stale_wrapper_in_manifests(manifest_root, stale, platforms=("claude", "codex"))

    # Reinstall should deterministically remove the stale wrapper and all manifest references.
    svc.install("claude", confirm=True)
    assert not stale.exists(), "stale r2p-adapt wrapper must be removed on upgrade"
    assert_no_manifest_references(manifest_root, stale)


def test_uninstall_removes_stale_shared_wrapper_from_all_manifests(tmp_path):
    svc, manifest_root, ph_root = make_service(tmp_path)
    svc.install("claude")
    svc.install("codex")
    bin_dir = manifest_root / "bin"
    stale = bin_dir / "r2p-adapt"
    stale.write_text("#!/usr/bin/env bash\n", encoding="utf-8")
    seed_stale_wrapper_in_manifests(manifest_root, stale, platforms=("claude", "codex"))

    # Uninstall must also clean obsolete managed shared wrappers even when another
    # platform remains installed and normal uninstall would skip shared bin paths.
    svc.uninstall("claude")
    assert not stale.exists(), "stale r2p-adapt wrapper must be removed on uninstall"
    assert_no_manifest_references(manifest_root, stale)


def test_stale_shared_wrapper_cleanup_preserves_unmanaged_r2p_wrapper(tmp_path):
    svc, manifest_root, ph_root = make_service(tmp_path)
    svc.install("claude")
    svc.install("codex")
    bin_dir = manifest_root / "bin"
    stale = bin_dir / "r2p-adapt"
    unmanaged = bin_dir / "r2p-local"
    stale.write_text("#!/usr/bin/env bash\n", encoding="utf-8")
    unmanaged.write_text("#!/usr/bin/env bash\n", encoding="utf-8")
    seed_stale_wrapper_in_manifests(manifest_root, stale, platforms=("claude", "codex"))

    svc.install("claude", confirm=True)
    assert not stale.exists(), "managed stale wrapper should be removed"
    assert unmanaged.exists(), "unmanaged r2p-* files in bin must be preserved"
    assert_no_manifest_references(manifest_root, stale)
```

Implement `seed_stale_wrapper_in_manifests` and `assert_no_manifest_references` with the real
manifest load/dump helpers discovered in Step 3; do not use a text-only grep assertion. The final
assertion contract is: no installed platform manifest lists the stale path in `installed_paths`, and
no `backups` entry has `target` equal to that stale path.

- [ ] **Step 2: Run to verify the new stale-wrapper tests fail**

Run:
```bash
.venv/bin/python -m pytest tests/test_install.py -k "stale_shared_wrapper" -v
```
Expected: FAIL — reinstall/uninstall leave the stale wrapper, stale manifest entries, or remove the unmanaged wrapper.

- [ ] **Step 3: Read the manifest format and install flow**

Run: `.venv/bin/python -c "import inspect,tools.workflow_cli.install as i; print(inspect.getsource(i.InstallService.install))" | head -80`
Identify how `installed_paths` and the manifest are written, and the wrapper-writing loop (the `tools/r2p-*` glob).

- [ ] **Step 4: Implement deterministic stale-wrapper cleanup**

Add one shared cleanup helper and call it from both install/reinstall and uninstall paths. The helper
must run even when multiple platforms are installed, because obsolete `bin/r2p-*` wrappers are
shared and normal uninstall skips shared `bin/` paths while another platform remains installed.

In the install flow, after computing the current managed wrapper set (the files written from the
`tools/r2p-*` glob) and before/after writing the new manifest, call the cleanup helper:

```python
        self._cleanup_obsolete_managed_wrappers()
```

In the uninstall flow, call the same helper after manifest state for the requested platform has been
loaded and before returning success, so a stale managed shared wrapper is removed even if the
requested platform's uninstall path would otherwise skip shared `bin/` entries.

Implement `_cleanup_obsolete_managed_wrappers(self)` by computing the current managed wrapper names
from `self.repo_root.glob("tools/r2p-*")`, then discovering obsolete candidates only from managed
manifest references: every `installed_paths` entry and every `backups[*].target` under
`self.manifest_root / "install"`. A candidate is obsolete when it points inside
`self.manifest_root / "bin"`, its filename starts with `r2p-`, and its filename is not in the current
template wrapper set. Do not scan arbitrary `bin/r2p-*` files as deletion candidates; unmanaged files
in `bin/` must be preserved. For every obsolete managed candidate, even if the file is already
missing:
- remove that wrapper path from `installed_paths` in **every** platform manifest under
  `self.manifest_root / "install"`;
- remove any `backups` metadata entry whose `target` equals that wrapper path;
- rewrite changed manifests using the same dump function the install path already uses;
- delete the wrapper file itself when it exists.

Add a focused helper `_strip_path_from_manifest(self, manifest_path, path_str)` only if it keeps the
shared cleanup helper small. It must load the manifest, remove `path_str` from `installed_paths` and
matching `backups`, and rewrite with the existing manifest serializer.

(Match the real attribute names — `self.repo_root`, `self.manifest_root`, the manifest dump/load helpers — discovered in Step 3.)

- [ ] **Step 5: Run to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_install.py -v`
Expected: PASS, including the new upgrade/uninstall cleanup tests and all existing install/uninstall tests.

- [ ] **Step 6: Commit**

```bash
git add tools/workflow_cli/install.py tests/test_install.py
git diff --cached --name-only
git commit -m "fix(install): remove obsolete shared wrappers during install and uninstall"
```
Expected staged paths: `tools/workflow_cli/install.py` and `tests/test_install.py` only.

### Task 7: Doc cleanup + npm package file globs

**Files:**
- Modify: `README.md`, `docs/README.md`, `CLAUDE.md`, `.claude/skills/req-to-plan.md`, `tools/workflow_cli/agent_templates/claude/SKILL.md`, `docs/workflow-operator-runbook.md`, `docs/workflow-command-surface.md`, `docs/workflow-cli-adapter.md`, `docs/workflow-agent-command-adapter.md`, `docs/workflow-invariants.md`
- Verify: `package.json` `files` globs still resolve (the `tools/r2p-*` glob now matches one fewer file — fine)

- [ ] **Step 1: Find every remaining adapter reference**

Run:
```bash
git grep -in "r2p-adapt\|CMD-EXEC-\|get_adapter\|list_adapters\|ADAPTER_REGISTRY\|post-plan-adapter\|executor-adapt\|adapter\|adapt" -- ':!docs/2026-05-3*'
```
Expected: a list of prose/code references to remove, rewrite, or explicitly whitelist (the plan
files themselves are excluded). Whitelist only intentional neutral-scope prose such as the PLAN
Neutrality Rule; stale adapter commands, adapter APIs, "Adding a New Adapter" prose, post-PLAN
adapter contract text, and executor-adapt references must be removed or rewritten.

- [ ] **Step 2: Remove/rewrite each reference**

- README.md / docs/README.md: drop the `r2p-adapt` shortcut line and the post-plan-adapter document-map row.
- CLAUDE.md / `.claude/skills/req-to-plan.md`: drop adapter from module maps and `r2p-*` lists.
- SKILL.md (claude template): remove the `r2p-adapt` command-table row.
- workflow docs: remove `CMD-EXEC-*` rows, post-PLAN adapter references, `get_adapter` /
  `list_adapters` API prose, and generic "Adding a New Adapter" guidance.
- **Keep** the PLAN Neutrality Rule in `plan-workflow.md` — it is the reason no adapter is needed.

- [ ] **Step 3: Verify no stray references remain**

Run:
```bash
git grep -in "r2p-adapt\|CMD-EXEC-\|get_adapter\|list_adapters\|ADAPTER_REGISTRY\|post-plan-adapter\|executor-adapt" -- ':!docs/2026-05-3*'
git grep -in "adapter\|adapt" -- ':!docs/2026-05-3*'
```
Expected: the first command is empty. The second command returns only explicitly reviewed
neutral-scope prose, such as the PLAN Neutrality Rule; it must not show stale command lists,
adapter API docs, "Adding a New Adapter" instructions, or post-PLAN adapter surface references.

- [ ] **Step 4: Full suite + install smoke**

Run:
```bash
.venv/bin/python -m pytest tests/ -v
```
Then a temp-home install smoke (no real ~/.req-to-plan):
```bash
.venv/bin/python -c "
from pathlib import Path
import tempfile
from tools.workflow_cli.install import InstallService

repo = Path.cwd()
with tempfile.TemporaryDirectory() as td:
    root = Path(td)
    manifest_root = root / '.req-to-plan'
    homes = {
        'claude': root / '.claude',
        'codex': root / '.codex',
        'gemini': root / '.gemini',
    }
    svc = InstallService(repo_root=repo, manifest_root=manifest_root, platform_homes=homes)
    for platform in ('claude', 'codex', 'gemini'):
        svc.install(platform)
    wrappers = sorted(p.name for p in (manifest_root / 'bin').glob('r2p-*'))
    assert 'r2p-adapt' not in wrappers, wrappers
    assert not list(root.rglob('r2p-adapt*'))
    assert len(wrappers) == 5, wrappers
    print('install smoke PASS', wrappers)
"
```
Then verify the outward-facing shortcut help surface:
```bash
.venv/bin/python -c "
import subprocess, sys
out = subprocess.run(
    [sys.executable, '-m', 'tools.workflow_cli.agent_shortcuts', '--help'],
    text=True,
    capture_output=True,
    check=True,
).stdout
for cmd in ('start', 'continue', 'status', 'switch', 'reopen'):
    assert cmd in out, out
assert 'adapt' not in out, out
print('help smoke PASS: five shortcuts, no adapt')
"
```
Confirm via the test added in Task 6 plus existing install tests that `r2p-adapt` is never installed,
stale managed wrappers are removed from all manifests, unmanaged `bin/r2p-*` files are preserved,
the shortcut count is 5, and help lists no `adapt` subcommand.

- [ ] **Step 5: Update test baseline (after Part 2's net removal)**

Run: `.venv/bin/python -m pytest tests/ --co -q | tail -1`
Backfill the number into `CLAUDE.md` and `.claude/skills/req-to-plan.md`.

- [ ] **Step 6: Commit**

```bash
git add README.md \
        docs/README.md \
        CLAUDE.md \
        .claude/skills/req-to-plan.md \
        tools/workflow_cli/agent_templates/claude/SKILL.md \
        docs/workflow-operator-runbook.md \
        docs/workflow-command-surface.md \
        docs/workflow-cli-adapter.md \
        docs/workflow-agent-command-adapter.md \
        docs/workflow-invariants.md
git diff --cached --name-only
git commit -m "docs: remove adapter references; sync test baseline after adapter removal"
```
Expected staged paths: exactly the Task 7 docs listed in this commit command.

---

## Self-Review

**Spec coverage (Part 2):** delete files (Task 1), drop shortcut (Task 2), drop model intents (Task 3), remove integration tests (Task 4), fix install test (Task 5), deterministic install/reinstall/uninstall cleanup with manifest consistency (Task 6, GR3/NR4/TR6), doc cleanup + baseline (Task 7). ✓

**Placeholder scan:** No blocking placeholders remain. Task 6 requires reading the manifest serializer
before implementing helpers, but the assertions and cleanup behavior are concrete.

**Type consistency:** uses existing `make_service`, `InstallService.install`, `InstallService.uninstall`, `self.repo_root`, `self.manifest_root` (verify exact names in Task 6 Step 3); `_cleanup_obsolete_managed_wrappers` is the one new shared cleanup helper, with `_strip_path_from_manifest` only if it keeps manifest edits small.

**Cross-plan note:** Part 2's Task 2 Step 2 reconciles with Part 1's `_cmd_continue` rewrite — if Part 1 ran first, the `r2p-adapt` hint is already gone.

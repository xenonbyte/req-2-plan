# Part 2 — Remove the Superpowers Adapter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Delete the redundant post-PLAN superpowers adapter (the neutral PLAN already runs in superpowers; the adapter failed with a `.repair.md` on a real run), shrinking the `r2p-*` shortcut set from 6 to 5, and deterministically clean up the stale `r2p-adapt` wrapper on upgrade.

**Architecture:** Pure deletion + manifest-consistent cleanup. No run.md format change, no new behavior. Install discovery is glob-based, so deleting template files stops fresh installs from picking them up; the only added code is upgrade-time removal of an obsolete shared `bin/r2p-*` wrapper from all platform manifests.

**Tech Stack:** Python 3.10+ stdlib. Tests run with `.venv/bin/python -m pytest`.

**Design source:** `docs/2026-05-30-workflow-fixes-and-plan-optimization.md` Part 2 (Approved). Outward-facing removal — maintainer-approved.

**Pre-verified facts (2026-05-31):**
- `_cmd_adapt` at `agent_shortcuts.py:252-288`; `adapt` subparser at `:325-326`; handler entry at `:352`.
- `models.py:168` `CMD-EXEC-LIST-ADAPTERS` (in READ_ONLY_COMMANDS); `models.py:269` `CMD-EXEC-ADAPT`.
- Adapter tests: `tests/test_adapters_superpowers.py` (18); `tests/test_agent_shortcuts.py:328-355` (2); `tests/test_integration.py:540-595` executor-adapt class (3); `tests/test_models.py:159-167` (2). Total 25.
- Uninstall skips shared `bin/` when other platforms installed: `install.py:201`.

**Run tests:** `.venv/bin/python -m pytest` (never bare `pytest`). Commit after each green task.

---

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

- [ ] **Step 3: Commit**

```bash
git add -A
git commit -m "chore: remove superpowers adapter package, templates, wrapper, and surface doc"
```

### Task 2: Remove `_cmd_adapt` from agent_shortcuts and its tests

**Files:**
- Modify: `tools/workflow_cli/agent_shortcuts.py` (`_cmd_adapt` ~252-288; subparser ~325-326; handler entry ~352; closed-run hint ~211)
- Modify: `tests/test_agent_shortcuts.py` (delete 2 adapt tests ~328-355)

- [ ] **Step 1: Run the adapt shortcut tests to confirm they currently pass**

Run: `.venv/bin/python -m pytest tests/test_agent_shortcuts.py -k adapt -v`
Expected: PASS (2 tests) — they exist now; we will remove both the feature and the tests.

- [ ] **Step 2: Delete `_cmd_adapt` and its wiring**

In `agent_shortcuts.py`:
- Delete the entire `def _cmd_adapt(...)` function (~252-288).
- Delete the `p_adapt = sub.add_parser("adapt")` and `p_adapt.add_argument("--executor", required=True)` lines (~325-326).
- Delete the `"adapt": _cmd_adapt,` entry from the `handlers` dict (~352).
- In `_cmd_continue`'s run-closed branch (~211), if it still references `r2p-adapt --executor superpowers`, change the hint to: `next: run is closed; PLAN is at 07-plan.md; hand it to your executor`. (If Part 1 already rewrote `_cmd_continue`, this is already done — verify and skip.)

- [ ] **Step 3: Delete the 2 adapt tests**

In `tests/test_agent_shortcuts.py`, delete `test_missing_run_record_stops_before_adapter` and `test_malformed_run_record_stops_before_adapter` (~328-355).

- [ ] **Step 4: Run to verify shortcuts still work**

Run: `.venv/bin/python -m pytest tests/test_agent_shortcuts.py -v`
Expected: PASS; no `adapt` subcommand remains.

- [ ] **Step 5: Verify the subcommand is gone**

Run: `.venv/bin/python -m tools.workflow_cli.agent_shortcuts adapt --executor superpowers 2>&1 | head -2`
Expected: argparse error "invalid choice: 'adapt'".

- [ ] **Step 6: Commit**

```bash
git add tools/workflow_cli/agent_shortcuts.py tests/test_agent_shortcuts.py
git commit -m "feat(shortcuts): drop the adapt subcommand"
```

### Task 3: Remove CMD-EXEC adapter intents from the model

**Files:**
- Modify: `tools/workflow_cli/models.py` (`CMD-EXEC-LIST-ADAPTERS` in `READ_ONLY_COMMANDS` ~168; `CMD-EXEC-ADAPT` in `CLOSED_AT_PLAN_CHECKPOINT` set ~269)
- Modify: `tests/test_models.py` (delete the 2 CMD-EXEC tests ~159-167)

- [ ] **Step 1: Run the CMD-EXEC tests to confirm they currently pass**

Run: `.venv/bin/python -m pytest tests/test_models.py -k "cmd_exec" -v`
Expected: PASS (2 tests).

- [ ] **Step 2: Remove the intents**

In `models.py`:
- Delete `"CMD-EXEC-LIST-ADAPTERS",` from `READ_ONLY_COMMANDS` (~168).
- Delete `"CMD-EXEC-ADAPT",` from `ALLOWED_COMMANDS_BY_RUN_STATE[RunStatus.CLOSED_AT_PLAN_CHECKPOINT]` (~269). Leave `CMD-RUN-REOPEN` / `CMD-TIER-STATUS` in that set.

- [ ] **Step 3: Delete the 2 tests**

In `tests/test_models.py`, delete `test_cmd_exec_list_adapters_allowed_in_any_state` and `test_cmd_exec_adapt_allowed_in_closed_at_plan_checkpoint` (~159-167).

- [ ] **Step 4: Run to verify**

Run: `.venv/bin/python -m pytest tests/test_models.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tools/workflow_cli/models.py tests/test_models.py
git commit -m "feat(models): remove CMD-EXEC adapter command intents"
```

### Task 4: Remove the executor-adapt integration test class

**Files:**
- Modify: `tests/test_integration.py` (executor-adapt class ~540-595: 3 tests + docstring)

- [ ] **Step 1: Confirm the class exists and passes**

Run: `.venv/bin/python -m pytest tests/test_integration.py -k adapt -v`
Expected: PASS (3 tests: `test_adapt_writes_derived_plan`, `test_adapt_requires_closed_run`, `test_adapt_with_unsupported_executor_exits_nonzero`).

- [ ] **Step 2: Delete the class**

In `tests/test_integration.py`, delete the entire executor-adapt test class (the class docstring "Tests for executor adapt via agent_shortcuts." plus the 3 methods).

- [ ] **Step 3: Run to verify**

Run: `.venv/bin/python -m pytest tests/test_integration.py -v`
Expected: PASS; no adapt references remain.

- [ ] **Step 4: Commit**

```bash
git add tests/test_integration.py
git commit -m "test: remove executor-adapt integration tests"
```

### Task 5: Update the codex install test (drop r2p-adapt)

**Files:**
- Modify: `tests/test_install.py` (`test_install_codex_copies_shortcut_skills` ~375)

- [ ] **Step 1: Run the install test to see it currently expects r2p-adapt**

Run: `.venv/bin/python -m pytest tests/test_install.py::test_install_codex_copies_shortcut_skills -v` (or the class-qualified name)
Expected: at this point it may FAIL because Task 1 deleted the codex `r2p-adapt` template — the test still lists `"r2p-adapt"`.

- [ ] **Step 2: Remove the entry**

In `tests/test_install.py`, delete the `"r2p-adapt",` line from the codex command list in `test_install_codex_copies_shortcut_skills` (~375).

- [ ] **Step 3: Run to verify**

Run: `.venv/bin/python -m pytest tests/test_install.py -v`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add tests/test_install.py
git commit -m "test(install): drop r2p-adapt from codex shortcut expectations"
```

### Task 6: Deterministic upgrade cleanup of the stale shared wrapper

**Files:**
- Modify: `tools/workflow_cli/install.py` (install path; uses manifests under `manifest_root/install`)
- Test: `tests/test_install.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_install.py` (reuse the existing `make_service(tmp_path)` helper):

```python
def test_upgrade_removes_stale_shared_wrapper(tmp_path):
    svc, manifest_root, ph_root = make_service(tmp_path)
    svc.install("claude")
    svc.install("codex")
    # Simulate a 0.1.2 leftover: a managed bin wrapper no longer in the template set.
    bin_dir = manifest_root / "bin"
    stale = bin_dir / "r2p-adapt"
    stale.write_text("#!/usr/bin/env bash\n", encoding="utf-8")
    # Record it in both manifests' installed_paths to mimic the old install.
    import json
    for platform in ("claude", "codex"):
        mpath = manifest_root / "install" / f"{platform}.yaml"
        text = mpath.read_text(encoding="utf-8")
        if "r2p-adapt" not in text:
            mpath.write_text(text + f"\n- {stale}\n", encoding="utf-8")  # adapt to real manifest format in Step 3
    # Reinstall should deterministically remove the stale wrapper.
    svc.install("claude", confirm=True)
    assert not stale.exists(), "stale r2p-adapt wrapper must be removed on upgrade"
```

(Adjust the manifest-mutation in Step 1 to the real manifest serialization once Step 3 confirms it — the assertion is the contract.)

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_install.py::test_upgrade_removes_stale_shared_wrapper -v`
Expected: FAIL — reinstall leaves the stale wrapper.

- [ ] **Step 3: Read the manifest format and install flow**

Run: `.venv/bin/python -c "import inspect,tools.workflow_cli.install as i; print(inspect.getsource(i.InstallService.install))" | head -80`
Identify how `installed_paths` and the manifest are written, and the wrapper-writing loop (the `tools/r2p-*` glob).

- [ ] **Step 4: Implement deterministic stale-wrapper cleanup**

In the install flow, after computing the current managed wrapper set (the files written from the `tools/r2p-*` glob) and before/after writing the new manifest, add a cleanup pass:

```python
        # Remove managed bin wrappers that are no longer part of the current template set,
        # across ALL installed platform manifests (shared bin is reference-counted).
        current_wrappers = {p.name for p in sorted(self.repo_root.glob("tools/r2p-*"))}
        bin_dir = self.manifest_root / "bin"
        if bin_dir.exists():
            for wrapper in sorted(bin_dir.glob("r2p-*")):
                if wrapper.name not in current_wrappers:
                    wrapper.unlink(missing_ok=True)
                    # Drop it from every platform manifest's installed_paths + backups.
                    for mpath in sorted((self.manifest_root / "install").glob("*.yaml")):
                        self._strip_path_from_manifest(mpath, str(wrapper))
```

Add a helper `_strip_path_from_manifest(self, manifest_path, path_str)` that loads the manifest, removes `path_str` from `installed_paths` and any `backups` entry whose `target` equals it, and rewrites the file using the same dump function the install path already uses.

(Match the real attribute names — `self.repo_root`, `self.manifest_root`, the manifest dump/load helpers — discovered in Step 3.)

- [ ] **Step 5: Run to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_install.py -v`
Expected: PASS, including the new upgrade test and all existing install/uninstall tests.

- [ ] **Step 6: Commit**

```bash
git add tools/workflow_cli/install.py tests/test_install.py
git commit -m "fix(install): deterministically remove obsolete shared wrappers on upgrade"
```

### Task 7: Doc cleanup + npm package file globs

**Files:**
- Modify: `README.md`, `docs/README.md`, `CLAUDE.md`, `.claude/skills/req-to-plan.md`, `tools/workflow_cli/agent_templates/claude/SKILL.md`, `docs/workflow-operator-runbook.md`, `docs/workflow-command-surface.md`, `docs/workflow-cli-adapter.md`, `docs/workflow-agent-command-adapter.md`, `docs/workflow-invariants.md`
- Verify: `package.json` `files` globs still resolve (the `tools/r2p-*` glob now matches one fewer file — fine)

- [ ] **Step 1: Find every remaining adapter reference**

Run: `git grep -in "r2p-adapt\|CMD-EXEC-\|get_adapter\|ADAPTER_REGISTRY\|post-plan-adapter\|executor-adapt" -- ':!docs/2026-05-3*'`
Expected: a list of prose references to remove/rewrite (the plan files themselves are excluded).

- [ ] **Step 2: Remove/rewrite each reference**

- README.md / docs/README.md: drop the `r2p-adapt` shortcut line and the post-plan-adapter document-map row.
- CLAUDE.md / `.claude/skills/req-to-plan.md`: drop adapter from module maps and `r2p-*` lists.
- SKILL.md (claude template): remove the `r2p-adapt` command-table row.
- workflow docs: remove `CMD-EXEC-*` rows and post-PLAN adapter references.
- **Keep** the PLAN Neutrality Rule in `plan-workflow.md` — it is the reason no adapter is needed.

- [ ] **Step 3: Verify no stray references remain**

Run: `git grep -in "r2p-adapt\|CMD-EXEC-\|get_adapter\|ADAPTER_REGISTRY\|executor-adapt" -- ':!docs/2026-05-3*'`
Expected: empty (only intentional prose like "the neutral PLAN does not adapt to an executor" may remain, if any).

- [ ] **Step 4: Full suite + install smoke**

Run:
```bash
.venv/bin/python -m pytest tests/ -v
```
Then a temp-home install smoke (no real ~/.req-to-plan):
```bash
.venv/bin/python -c "
import tempfile, pathlib, tools.workflow_cli.install as i
# follow the existing make_service/test pattern to install claude,codex,gemini into a temp home
print('manual: assert no r2p-adapt file is installed; r2p-* count is 5')
"
```
Confirm via the test added in Task 6 plus existing install tests that `r2p-adapt` is never installed and the shortcut count is 5.

- [ ] **Step 5: Update test baseline (after Part 2's net removal)**

Run: `.venv/bin/python -m pytest tests/ --co -q | tail -1`
Backfill the number into `CLAUDE.md` and `.claude/skills/req-to-plan.md`.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "docs: remove adapter references; sync test baseline after adapter removal"
```

---

## Self-Review

**Spec coverage (Part 2):** delete files (Task 1), drop shortcut (Task 2), drop model intents (Task 3), remove integration tests (Task 4), fix install test (Task 5), deterministic upgrade cleanup with manifest consistency (Task 6, GR3/NR4/TR6), doc cleanup + baseline (Task 7). ✓

**Placeholder scan:** Task 6 Steps 1/4 contain one acknowledged "adapt to real manifest format" — this is deliberate: the manifest serializer must be read in Step 3 before the exact mutation is written. The contract (assertion + cleanup behavior) is concrete. All other steps are concrete.

**Type consistency:** uses existing `make_service`, `InstallService.install`, `self.repo_root`, `self.manifest_root` (verify exact names in Task 6 Step 3); `_strip_path_from_manifest` is the one new helper, defined where introduced.

**Cross-plan note:** Part 2's Task 2 Step 2 reconciles with Part 1's `_cmd_continue` rewrite — if Part 1 ran first, the `r2p-adapt` hint is already gone.

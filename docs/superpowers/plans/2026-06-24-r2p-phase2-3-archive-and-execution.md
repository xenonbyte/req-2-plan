# req-to-plan Phase 2 & 3 — Archiving Infrastructure + Execution Skill Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add requirement-directory archiving with a version-control lifecycle (Phase 2) and a self-contained, in-place SDD-replica execution skill `r2p-execute` (Phase 3), closing the loop requirement → PLAN → implement → archive.

**Architecture:** Two independently-mergeable phases. Phase 2 adds a terminal `ARCHIVED` state, a neutral `workspace.py` module (gitignore seeding + a path-limited git-commit primitive), the `run-archive`/`r2p-archive` command pair, and wires PLAN-completion + archive commits. Phase 3 adds an `EXECUTING` state, the `run-execute-start`/`r2p-execute` command pair with a progress-ledger seed, `r2p-continue` status routing, a shared `plan_task_anchors()` Markdown helper, and three single-file SDD-replica skill templates. Phase 3 depends on Phase 2's `ARCHIVED` + `run-archive`.

**Tech Stack:** Python 3.10+ (stdlib + PyYAML), argparse CLI, `unittest`/pytest, `subprocess` for git. Test runner: `.venv/bin/python -m pytest`.

**Source spec:** `docs/optimization-plan.md` §1, §3, §4 (all subsections), §6 (Phase 2 & Phase 3), §7.

## Global Constraints

- **Hard cut, no compat:** new `RunStatus.EXECUTING`/`ARCHIVED` and transitions only; no migration code for old `run.md`. New states are forward-reachable only — old run.md carries valid existing states and parses unchanged (`state.py:parse_run_record` uses `RunStatus(<str>)`, which raises on unknown; no unknown value is ever written by old code). (spec §1)
- **No over-defense / no speculative fallbacks:** every check is deterministic and emits an observable failure; the auto-commit is best-effort with **observable** `warning:` skips, never a silent swallow, and never fails its caller. No subagent-less degrade, no auto-sequential fallback. (spec §1, §3.6, §7)
- **CLI / Agent separation:** CLI owns state machine, structural validation, archive move, and the progress-ledger *skeleton* (PLAN-TASK IDs + checkboxes = structure, not semantics). The SDD execution loop (dispatch subagents, TDD, review) lives entirely in the skill templates. Invariant preserved: **CLI never generates artifact text.** (spec §3.3, CLAUDE.md)
- **Auto-commit scope:** the PLAN-completion and archive commits are **path-limited** to `.req-to-plan/.gitignore` and `.req-to-plan/<id>` only — never `git add -A`, never `-f`, never `push`, never a PR. Unconditional (no env switch / escape hatch). Three guards make it best-effort. (spec §4.5, §7)
- **In-place execution:** `r2p-execute` does NOT create a branch or worktree; it implements and commits on the current branch (user-authorized). `push`/PR still require explicit user request. (spec §3.6)
- **Template install reality (deviation from §3.6, justified by §3.7):** the installer ships one file per skill per platform (claude `commands/r2p-*.md`, codex `skills/r2p-*/SKILL.md`, gemini `commands/r2p-*.toml`). The SDD implementer/reviewer prompts are therefore **inlined into each platform's single skill file**, not shipped as separate `implementer-prompt.md`/`task-reviewer-prompt.md` files. This keeps the skill self-contained and three-platform-consistent with **no installer change**. (spec §3.7)
- **Tests:** use `tempfile.TemporaryDirectory`; never touch real `~/.req-to-plan` or `.req-to-plan/`. Git-touching tests `git init` a temp repo and set `user.email`/`user.name` locally; never run against the real repo. Run with `.venv/bin/python -m pytest` (system Python lacks PyYAML). The local baseline carries **4 expected skips** (py3.10 `tomllib`); treat `N passed, 4 skipped` as green.
- **Worktree safety:** before each task and before every commit, run `git status --short`. If a planned target file already has unrelated local changes, stop and ask before editing/staging. Before each `git add`, run `git diff -- <task files>` and stage only the task's files.
- **TDD:** red → green → commit per task. Full suite stays green at every commit.
- **Commit messages:** `<type>(r2p): <subject>`, ending every message with the trailer `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>` (shown in full in Task 1; subject-only thereafter — append the same trailer each time).

---

# Phase 2 — Archiving Infrastructure (independent; does not depend on the execution skill)

### Task 1: `RunStatus.ARCHIVED` + state machine + `is_terminal`

**Files:**
- Modify: `tools/workflow_cli/models.py` (`RunStatus` enum ~line 33; `ALLOWED_TRANSITIONS` ~line 151; `ALLOWED_COMMANDS_BY_RUN_STATE` ~line 269)
- Modify: `tools/workflow_cli/agent_shortcuts.py:160-161` (`is_terminal`)
- Test: `tests/test_models.py`, `tests/test_agent_shortcuts.py`

**Interfaces:**
- Produces: `RunStatus.ARCHIVED = "archived"`; transition `CLOSED_AT_PLAN_CHECKPOINT → ARCHIVED`; `ARCHIVED` is terminal (no outgoing transitions). `is_terminal(ARCHIVED) is True`.
- Consumes: nothing new.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_models.py`:

```python
class TestArchivedState(unittest.TestCase):
    def test_archived_status_exists(self):
        from tools.workflow_cli.models import RunStatus
        self.assertEqual(RunStatus.ARCHIVED.value, "archived")

    def test_closed_can_transition_to_archived(self):
        from tools.workflow_cli.models import RunStatus, is_transition_allowed
        self.assertTrue(
            is_transition_allowed(RunStatus.CLOSED_AT_PLAN_CHECKPOINT, RunStatus.ARCHIVED)
        )

    def test_archived_is_terminal_in_transitions(self):
        from tools.workflow_cli.models import RunStatus, ALLOWED_TRANSITIONS
        self.assertEqual(ALLOWED_TRANSITIONS[RunStatus.ARCHIVED], set())

    def test_run_archive_command_allowed_when_closed(self):
        from tools.workflow_cli.models import RunStatus, is_command_allowed
        self.assertTrue(
            is_command_allowed(RunStatus.CLOSED_AT_PLAN_CHECKPOINT, "CMD-RUN-ARCHIVE")
        )
```

Append to `tests/test_agent_shortcuts.py`:

```python
class TestIsTerminalArchived(unittest.TestCase):
    def test_archived_is_terminal(self):
        from tools.workflow_cli.agent_shortcuts import is_terminal
        from tools.workflow_cli.models import RunStatus
        self.assertTrue(is_terminal(RunStatus.ARCHIVED))

    def test_closed_is_terminal(self):
        from tools.workflow_cli.agent_shortcuts import is_terminal
        from tools.workflow_cli.models import RunStatus
        self.assertTrue(is_terminal(RunStatus.CLOSED_AT_PLAN_CHECKPOINT))
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_models.py::TestArchivedState tests/test_agent_shortcuts.py::TestIsTerminalArchived -v`
Expected: FAIL (`AttributeError: ARCHIVED` / transition not allowed / `is_terminal(ARCHIVED)` False).

- [ ] **Step 3: Add the enum member**

In `tools/workflow_cli/models.py`, in `RunStatus`, after `CLOSED_AT_PLAN_CHECKPOINT = "closed_at_plan_checkpoint"`:

```python
    CLOSED_AT_PLAN_CHECKPOINT = "closed_at_plan_checkpoint"
    ARCHIVED = "archived"       # terminal: requirement directory archived
```

- [ ] **Step 4: Open the CLOSED→ARCHIVED transition + register ARCHIVED**

In `tools/workflow_cli/models.py`, change the `ALLOWED_TRANSITIONS` entry for the closed state from:

```python
    RunStatus.CLOSED_AT_PLAN_CHECKPOINT: set(),
}
```

to:

```python
    RunStatus.CLOSED_AT_PLAN_CHECKPOINT: {RunStatus.ARCHIVED},
    RunStatus.ARCHIVED: set(),
}
```

In the same file, in `ALLOWED_COMMANDS_BY_RUN_STATE`, change the closed-state entry from:

```python
    RunStatus.CLOSED_AT_PLAN_CHECKPOINT: {
        "CMD-RUN-REOPEN",
        "CMD-TIER-STATUS",
    },
}
```

to:

```python
    RunStatus.CLOSED_AT_PLAN_CHECKPOINT: {
        "CMD-RUN-REOPEN",
        "CMD-RUN-ARCHIVE",
        "CMD-TIER-STATUS",
    },
    # ARCHIVED is terminal: only the always-allowed read-only commands
    # (see READ_ONLY_COMMANDS) remain reachable.
    RunStatus.ARCHIVED: set(),
}
```

- [ ] **Step 5: Update `is_terminal`**

In `tools/workflow_cli/agent_shortcuts.py`, replace `is_terminal`:

```python
def is_terminal(status: RunStatus) -> bool:
    return status in (RunStatus.CLOSED_AT_PLAN_CHECKPOINT, RunStatus.ARCHIVED)
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_models.py::TestArchivedState tests/test_agent_shortcuts.py::TestIsTerminalArchived -v`
Expected: PASS (6 passed).

- [ ] **Step 7: Commit**

Run: `.venv/bin/python -m pytest tests/ -q` → all pass (4 expected skips).

```bash
git status --short
git diff -- tools/workflow_cli/models.py tools/workflow_cli/agent_shortcuts.py tests/test_models.py tests/test_agent_shortcuts.py
git add tools/workflow_cli/models.py tools/workflow_cli/agent_shortcuts.py tests/test_models.py tests/test_agent_shortcuts.py
git commit -m "feat(r2p): add terminal ARCHIVED run state + CLOSED→ARCHIVED transition

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 2: `workspace.py` — `ensure_workspace_gitignore` + wire into pointer creation

**Files:**
- Create: `tools/workflow_cli/workspace.py`
- Modify: `tools/workflow_cli/agent_shortcuts.py` (import + call inside `write_active_pointer`, ~line 48)
- Test: Create `tests/test_workspace.py`

**Interfaces:**
- Consumes: `atomic_write_text` from `tools.workflow_cli.atomic`.
- Produces: `ensure_workspace_gitignore(base_path: Path) -> None` — ensures `<base>/.req-to-plan/.gitignore` exists and contains a `/archive` line; idempotent (creates if absent, appends the line if missing, no-op if present). Neutral module: imports neither `cli` nor `agent_shortcuts` (both may import it without a cycle).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_workspace.py`:

```python
import tempfile
import unittest
from pathlib import Path

from tools.workflow_cli.workspace import ensure_workspace_gitignore


class TestEnsureWorkspaceGitignore(unittest.TestCase):
    def test_creates_gitignore_with_archive_line(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            ensure_workspace_gitignore(base)
            gi = base / ".req-to-plan" / ".gitignore"
            self.assertTrue(gi.exists())
            self.assertIn("/archive", gi.read_text(encoding="utf-8").splitlines())

    def test_appends_archive_line_when_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            (base / ".req-to-plan").mkdir(parents=True)
            (base / ".req-to-plan" / ".gitignore").write_text("*.log\n", encoding="utf-8")
            ensure_workspace_gitignore(base)
            lines = (base / ".req-to-plan" / ".gitignore").read_text(encoding="utf-8").splitlines()
            self.assertIn("*.log", lines)
            self.assertIn("/archive", lines)

    def test_idempotent_when_line_present(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            ensure_workspace_gitignore(base)
            ensure_workspace_gitignore(base)
            text = (base / ".req-to-plan" / ".gitignore").read_text(encoding="utf-8")
            self.assertEqual(text.count("/archive"), 1)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_workspace.py -v`
Expected: FAIL with `ModuleNotFoundError: tools.workflow_cli.workspace`.

- [ ] **Step 3: Create the module**

Create `tools/workflow_cli/workspace.py`:

```python
"""Workspace-level helpers for the `.req-to-plan/` directory.

Neutral module imported by both cli.py and agent_shortcuts.py (it imports
neither, so there is no cycle). Owns the workspace `.gitignore` and the
path-limited git-commit primitive used by run-close (add) and run-archive
(remove).
"""
from __future__ import annotations

from pathlib import Path

from tools.workflow_cli.atomic import atomic_write_text

_ARCHIVE_IGNORE_LINE = "/archive"


def ensure_workspace_gitignore(base_path: Path) -> None:
    """Ensure `<base>/.req-to-plan/.gitignore` ignores the archive dir.

    Creates the file with `/archive` if absent; appends the line if the file
    exists without it; no-op if already present. Deliberately does no merging
    or sorting.
    """
    r2p_dir = base_path / ".req-to-plan"
    r2p_dir.mkdir(parents=True, exist_ok=True)
    gitignore = r2p_dir / ".gitignore"
    if not gitignore.exists():
        atomic_write_text(gitignore, _ARCHIVE_IGNORE_LINE + "\n")
        return
    existing = gitignore.read_text(encoding="utf-8")
    if _ARCHIVE_IGNORE_LINE in [ln.strip() for ln in existing.splitlines()]:
        return
    prefix = existing if existing.endswith("\n") or existing == "" else existing + "\n"
    atomic_write_text(gitignore, prefix + _ARCHIVE_IGNORE_LINE + "\n")
```

- [ ] **Step 4: Wire into pointer creation**

In `tools/workflow_cli/agent_shortcuts.py`, add the import next to the existing `atomic` import (~line 17):

```python
from tools.workflow_cli.workspace import ensure_workspace_gitignore
```

In `write_active_pointer`, immediately after `path.parent.mkdir(parents=True, exist_ok=True)` (~line 48), add:

```python
    ensure_workspace_gitignore(base_path)
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_workspace.py -v`
Expected: PASS (3 passed).

- [ ] **Step 6: Run shortcut + state suites for regressions**

Run: `.venv/bin/python -m pytest tests/test_agent_shortcuts.py tests/test_workspace.py -q`
Expected: all pass (pointer creation now also seeds `.gitignore`; no existing assertion forbids it).

- [ ] **Step 7: Commit**

Run: `.venv/bin/python -m pytest tests/ -q` → all pass.

```bash
git status --short
git diff -- tools/workflow_cli/workspace.py tools/workflow_cli/agent_shortcuts.py tests/test_workspace.py
git add tools/workflow_cli/workspace.py tools/workflow_cli/agent_shortcuts.py tests/test_workspace.py
git commit -m "feat(r2p): seed .req-to-plan/.gitignore /archive via workspace.ensure_workspace_gitignore"
```
(append the Co-Authored-By trailer)

---

### Task 3: `workspace.py` — `commit_requirement_dir` (path-limited primitive + three guards)

**Files:**
- Modify: `tools/workflow_cli/workspace.py`
- Test: `tests/test_workspace.py`

**Interfaces:**
- Consumes: stdlib `subprocess`.
- Produces: `commit_requirement_dir(base_path: Path, work_id: str, message: str) -> None` — path-limited `git add`/`commit` of exactly `.req-to-plan/.gitignore` and `.req-to-plan/<work_id>`. Best-effort: emits an observable `warning:` and returns (never raises) when (1) `base_path` is not inside a git work tree, (2) nothing was staged (path wholesale-gitignored, or moved/deleted-but-untracked, or no change), or (3) the commit command itself fails. Never `-f`, never `add -A`, never push.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_workspace.py`:

```python
import subprocess


def _git(base, *args):
    return subprocess.run(["git", "-C", str(base), *args], capture_output=True, text=True)


def _init_repo(base: Path) -> None:
    _git(base, "init", "-q")
    _git(base, "config", "user.email", "t@example.com")
    _git(base, "config", "user.name", "t")


class TestCommitRequirementDir(unittest.TestCase):
    def test_commits_requirement_dir_when_tracked(self):
        from tools.workflow_cli.workspace import commit_requirement_dir, ensure_workspace_gitignore
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            _init_repo(base)
            ensure_workspace_gitignore(base)
            run_dir = base / ".req-to-plan" / "WF-20260101-demo"
            run_dir.mkdir(parents=True)
            (run_dir / "run.md").write_text("# run\n", encoding="utf-8")
            commit_requirement_dir(base, "WF-20260101-demo", "chore(r2p): plan WF-20260101-demo")
            tracked = _git(base, "ls-files", ".req-to-plan/WF-20260101-demo").stdout
            self.assertIn("WF-20260101-demo/run.md", tracked)

    def test_archive_move_then_commit_untracks_dir(self):
        from tools.workflow_cli.workspace import commit_requirement_dir, ensure_workspace_gitignore
        import shutil
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            _init_repo(base)
            ensure_workspace_gitignore(base)
            run_dir = base / ".req-to-plan" / "WF-20260101-demo"
            run_dir.mkdir(parents=True)
            (run_dir / "run.md").write_text("# run\n", encoding="utf-8")
            commit_requirement_dir(base, "WF-20260101-demo", "chore(r2p): plan WF-20260101-demo")
            # Archive: move into the gitignored archive/ dir, then commit the removal.
            archive_dir = base / ".req-to-plan" / "archive" / "WF-20260101-demo"
            archive_dir.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(run_dir), str(archive_dir))
            commit_requirement_dir(base, "WF-20260101-demo", "chore(r2p): archive WF-20260101-demo")
            tracked = _git(base, "ls-files", ".req-to-plan/WF-20260101-demo").stdout.strip()
            self.assertEqual(tracked, "")  # no longer tracked
            ignored = _git(base, "check-ignore", ".req-to-plan/archive/WF-20260101-demo")
            self.assertEqual(ignored.returncode, 0)  # archive path is ignored

    def test_skips_when_not_a_git_repo(self):
        from tools.workflow_cli.workspace import commit_requirement_dir
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            (base / ".req-to-plan" / "WF-20260101-demo").mkdir(parents=True)
            # Must not raise.
            commit_requirement_dir(base, "WF-20260101-demo", "chore(r2p): plan x")

    def test_no_op_when_nothing_changed(self):
        from tools.workflow_cli.workspace import commit_requirement_dir, ensure_workspace_gitignore
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            _init_repo(base)
            ensure_workspace_gitignore(base)
            run_dir = base / ".req-to-plan" / "WF-20260101-demo"
            run_dir.mkdir(parents=True)
            (run_dir / "run.md").write_text("# run\n", encoding="utf-8")
            commit_requirement_dir(base, "WF-20260101-demo", "chore(r2p): plan x")
            before = _git(base, "rev-parse", "HEAD").stdout.strip()
            commit_requirement_dir(base, "WF-20260101-demo", "chore(r2p): plan x again")
            after = _git(base, "rev-parse", "HEAD").stdout.strip()
            self.assertEqual(before, after)  # no second commit

    def test_does_not_stage_unrelated_changes(self):
        from tools.workflow_cli.workspace import commit_requirement_dir, ensure_workspace_gitignore
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            _init_repo(base)
            ensure_workspace_gitignore(base)
            (base / "unrelated.txt").write_text("dirty\n", encoding="utf-8")
            run_dir = base / ".req-to-plan" / "WF-20260101-demo"
            run_dir.mkdir(parents=True)
            (run_dir / "run.md").write_text("# run\n", encoding="utf-8")
            commit_requirement_dir(base, "WF-20260101-demo", "chore(r2p): plan x")
            committed = _git(base, "show", "--name-only", "--format=", "HEAD").stdout
            self.assertNotIn("unrelated.txt", committed)
            self.assertIn("WF-20260101-demo/run.md", committed)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_workspace.py::TestCommitRequirementDir -v`
Expected: FAIL with `ImportError: cannot import name 'commit_requirement_dir'`.

- [ ] **Step 3: Implement the primitive**

In `tools/workflow_cli/workspace.py`, add at the top with the other imports:

```python
import subprocess
```

Append to the module:

```python
def _git(base_path: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(base_path), *args],
        capture_output=True,
        text=True,
    )


def commit_requirement_dir(base_path: Path, work_id: str, message: str) -> None:
    """Path-limited, best-effort commit of one requirement directory.

    Stages and commits only `.req-to-plan/.gitignore` and `.req-to-plan/<id>`.
    The same primitive both adds (path present) and removes (path moved/deleted).
    Best-effort with observable skips; it never raises and never touches paths
    outside `.req-to-plan/<id>` (no `add -A`, no `-f`, no push).
    """
    gitignore_rel = ".req-to-plan/.gitignore"
    run_rel = f".req-to-plan/{work_id}"

    # Guard 1: must be inside a git work tree.
    inside = _git(base_path, "rev-parse", "--is-inside-work-tree")
    if inside.returncode != 0 or inside.stdout.strip() != "true":
        print(f"warning: skipped commit for {run_rel}: not a git work tree")
        return

    # Stage (path-limited). `git add -- <path>` stages an addition/modification
    # when the path exists, and stages a deletion when it was tracked and is now
    # gone. A wholesale-gitignored path stages nothing (we never pass -f).
    _git(base_path, "add", "--", gitignore_rel, run_rel)

    # Guards 2 & 3 (merged): if nothing is staged for these paths, there is
    # nothing to commit — covers wholesale-ignored, untracked-then-moved, and
    # no-change. `git diff --cached --quiet` returns 0 when there is no diff.
    staged = _git(base_path, "diff", "--cached", "--quiet", "--", gitignore_rel, run_rel)
    if staged.returncode == 0:
        print(f"warning: skipped commit for {run_rel}: nothing staged (ignored or unchanged)")
        return

    committed = _git(base_path, "commit", "-m", message, "--", gitignore_rel, run_rel)
    if committed.returncode != 0:
        print(f"warning: git commit failed for {run_rel}: {committed.stderr.strip()}")
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_workspace.py::TestCommitRequirementDir -v`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

Run: `.venv/bin/python -m pytest tests/ -q` → all pass.

```bash
git status --short
git diff -- tools/workflow_cli/workspace.py tests/test_workspace.py
git add tools/workflow_cli/workspace.py tests/test_workspace.py
git commit -m "feat(r2p): add path-limited best-effort commit_requirement_dir primitive"
```
(append the Co-Authored-By trailer)

---

### Task 4: Wire PLAN-completion commit into `run-close`

**Files:**
- Modify: `tools/workflow_cli/cli.py` (`_cmd_run_close`, after `mgr.save(record)` ~line 380, before `print_and_exit`)
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: `ensure_workspace_gitignore`, `commit_requirement_dir` from `tools.workflow_cli.workspace`.
- Produces: on successful close, the requirement directory `.req-to-plan/<id>/` is committed (best-effort) before the success message.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_cli.py` (this file uses plain pytest classes with `assert` and `pytest.raises`; `main` and `pytest` are already imported at module top, as are `tempfile` and `Path`). Add:

```python
class TestRunCloseCommitsRequirementDir:
    def test_close_commits_requirement_dir_in_a_git_repo(self):
        import subprocess
        from tools.workflow_cli.state import (
            RunStateManager, create_run_record, upsert_active_artifact, add_checkpoint,
        )
        from tools.workflow_cli.models import (
            RunStatus, Stage, WorkId, STAGE_ARTIFACT_MAP, TierBase, TierEstimate,
        )
        from tools.workflow_cli.artifact import write_artifact

        def git(base, *a):
            return subprocess.run(["git", "-C", str(base), *a], capture_output=True, text=True)

        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            git(base, "init", "-q"); git(base, "config", "user.email", "t@e.com"); git(base, "config", "user.name", "t")
            wid = WorkId("WF-20260101-close")
            run_dir = base / ".req-to-plan" / str(wid)
            run_dir.mkdir(parents=True)
            rec = create_run_record(wid)
            rec.tier_locked = TierEstimate(base=TierBase.LIGHT, modifiers=frozenset())
            rec.current_stage = Stage.PLAN
            rec.status = RunStatus.CHECKPOINT_APPROVED
            write_artifact(run_dir, Stage.PLAN, "# Plan\n\n## Tasks\n", version=1, status="approved")
            upsert_active_artifact(rec, Stage.PLAN, STAGE_ARTIFACT_MAP[Stage.PLAN], 1, "approved")
            add_checkpoint(rec, Stage.PLAN, STAGE_ARTIFACT_MAP[Stage.PLAN], 1, "close_workflow_run")
            RunStateManager(run_dir).save(rec)

            with pytest.raises(SystemExit):
                main(["--base-path", str(base), "run-close", "--work-id", str(wid)])

            tracked = git(base, "ls-files", f".req-to-plan/{wid}").stdout
            assert f"{wid}/run.md" in tracked
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_cli.py::TestRunCloseCommitsRequirementDir -v`
Expected: FAIL (`ls-files` empty — close does not yet commit).

- [ ] **Step 3: Wire the commit**

In `tools/workflow_cli/cli.py`, add the import to the existing `from tools.workflow_cli.workspace import ...` line if present, otherwise add near the other imports (top of file):

```python
from tools.workflow_cli.workspace import ensure_workspace_gitignore, commit_requirement_dir
```

In `_cmd_run_close`, replace the tail (the `mgr.save(record)` + `print_and_exit` block at the end of the function) with:

```python
    mgr.save(record)
    # PLAN complete → land the requirement directory in version control
    # (best-effort, path-limited; never touches unrelated changes). spec §4.5
    ensure_workspace_gitignore(args.base_path or Path.cwd())
    commit_requirement_dir(
        args.base_path or Path.cwd(),
        str(record.work_id),
        f"chore(r2p): plan {record.work_id}",
    )
    print_and_exit(
        format_success({"work_id": str(record.work_id), "status": record.status.value}, message="Run closed"),
        EXIT_OK,
    )
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_cli.py::TestRunCloseCommitsRequirementDir -v`
Expected: PASS.

- [ ] **Step 5: Run the cli suite for regressions**

Run: `.venv/bin/python -m pytest tests/test_cli.py -q`
Expected: all pass — existing close tests run with `base_path` in tempdirs that are NOT git repos, so the commit no-ops with an observable warning (Guard 1) and does not change their assertions.

- [ ] **Step 6: Commit**

Run: `.venv/bin/python -m pytest tests/ -q` → all pass.

```bash
git status --short
git diff -- tools/workflow_cli/cli.py tests/test_cli.py
git add tools/workflow_cli/cli.py tests/test_cli.py
git commit -m "feat(r2p): commit requirement dir into version control on run-close"
```
(append the Co-Authored-By trailer)

---

### Task 5: `run-archive` CLI command

**Files:**
- Modify: `tools/workflow_cli/cli.py` (new `_cmd_run_archive` + register in `_register_run_commands`)
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: `RunStateManager`, `update_run_status`, `ensure_workspace_gitignore`, `commit_requirement_dir`, `EXIT_CONFLICT`/`EXIT_NOT_FOUND`.
- Produces: `run-archive --work-id <id>`. Precondition `status == CLOSED_AT_PLAN_CHECKPOINT` (Phase 3 widens this to also accept `EXECUTING`). Steps, in order: compute `archive/<id>` and refuse if it already exists (`EXIT_CONFLICT`, with no run-state mutation); `ensure_workspace_gitignore`; set `ARCHIVED` and save in the original dir; `shutil.move` run dir → `archive/<id>`; `commit_requirement_dir` (commits the removal). Pointer clearing is the shortcut layer's job (Task 6), not the CLI's.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_cli.py`:

```python
class TestRunArchive:
    def _closed_run(self, base, wid_str):
        from tools.workflow_cli.state import RunStateManager, create_run_record
        from tools.workflow_cli.models import RunStatus, Stage, WorkId
        wid = WorkId(wid_str)
        run_dir = base / ".req-to-plan" / wid_str
        run_dir.mkdir(parents=True)
        rec = create_run_record(wid)
        rec.status = RunStatus.CLOSED_AT_PLAN_CHECKPOINT
        rec.current_stage = Stage.CLOSED
        RunStateManager(run_dir).save(rec)
        return run_dir

    def test_archive_moves_run_dir_under_archive(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            self._closed_run(base, "WF-20260101-arch")
            with pytest.raises(SystemExit) as exc:
                main(["--base-path", str(base), "run-archive", "--work-id", "WF-20260101-arch"])
            assert exc.value.code == 0
            assert not (base / ".req-to-plan" / "WF-20260101-arch").exists()
            assert (base / ".req-to-plan" / "archive" / "WF-20260101-arch" / "run.md").exists()

    def test_archive_sets_status_archived(self):
        from tools.workflow_cli.state import RunStateManager
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            self._closed_run(base, "WF-20260101-arch")
            with pytest.raises(SystemExit):
                main(["--base-path", str(base), "run-archive", "--work-id", "WF-20260101-arch"])
            rec = RunStateManager(base / ".req-to-plan" / "archive" / "WF-20260101-arch").load()
            assert rec.status.value == "archived"

    def test_archive_refuses_when_not_closed(self):
        from tools.workflow_cli.state import RunStateManager, create_run_record
        from tools.workflow_cli.models import WorkId
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            wid = WorkId("WF-20260101-open")
            run_dir = base / ".req-to-plan" / "WF-20260101-open"
            run_dir.mkdir(parents=True)
            RunStateManager(run_dir).save(create_run_record(wid))  # ACTIVE_STAGE_DRAFT
            with pytest.raises(SystemExit) as exc:
                main(["--base-path", str(base), "run-archive", "--work-id", "WF-20260101-open"])
            assert exc.value.code == 6  # EXIT_CONFLICT

    def test_archive_refuses_to_overwrite_existing_archive(self):
        from tools.workflow_cli.state import RunStateManager
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            self._closed_run(base, "WF-20260101-arch")
            (base / ".req-to-plan" / "archive" / "WF-20260101-arch").mkdir(parents=True)
            with pytest.raises(SystemExit) as exc:
                main(["--base-path", str(base), "run-archive", "--work-id", "WF-20260101-arch"])
            assert exc.value.code == 6  # EXIT_CONFLICT
            assert (base / ".req-to-plan" / "WF-20260101-arch").exists()  # not moved
            rec = RunStateManager(base / ".req-to-plan" / "WF-20260101-arch").load()
            assert rec.status.value == "closed_at_plan_checkpoint"  # no partial archive state
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_cli.py::TestRunArchive -v`
Expected: FAIL (`invalid choice: 'run-archive'` — command not registered).

- [ ] **Step 3: Implement `_cmd_run_archive`**

In `tools/workflow_cli/cli.py`, add after `_cmd_run_close` (and ensure `import shutil` is available — it is imported at module top):

```python
def _cmd_run_archive(args):
    record, mgr, run_dir = _load_run(args.work_id, args.base_path)
    base = args.base_path or Path.cwd()
    archivable = {RunStatus.CLOSED_AT_PLAN_CHECKPOINT}
    if record.status not in archivable:
        print_and_exit(
            format_error(
                f"Cannot archive run in status {record.status.value!r}; "
                "must be closed_at_plan_checkpoint",
                exit_code=EXIT_CONFLICT,
            ),
            EXIT_CONFLICT,
        )
    # 1. Refuse to clobber an existing archived copy before mutating state.
    archive_dir = base / ".req-to-plan" / "archive" / str(record.work_id)
    if archive_dir.exists():
        print_and_exit(
            format_error(
                f"Archive target already exists: {archive_dir}",
                exit_code=EXIT_CONFLICT,
            ),
            EXIT_CONFLICT,
        )
    # 2. Ensure /archive is ignored before anything lands under it.
    ensure_workspace_gitignore(base)
    # 3. Mark ARCHIVED and persist in the original directory.
    try:
        record = update_run_status(record, RunStatus.ARCHIVED)
    except ValueError as e:
        print_and_exit(format_error(str(e), exit_code=EXIT_CONFLICT), EXIT_CONFLICT)
    mgr.save(record)
    archive_dir.parent.mkdir(parents=True, exist_ok=True)
    # 4. Move the run dir into the (ignored) archive.
    shutil.move(str(run_dir), str(archive_dir))
    # 5. Commit the removal of the original path (untracks the dir). spec §4.6
    commit_requirement_dir(
        base, str(record.work_id), f"chore(r2p): archive {record.work_id}"
    )
    print_and_exit(
        format_success(
            {"work_id": str(record.work_id), "status": "archived", "archived_to": str(archive_dir)},
            message=f"Run archived: {record.work_id}",
        ),
        EXIT_OK,
    )
```

In `_register_run_commands`, after the `run-reopen` parser block, add:

```python
    # run-archive
    p = subparsers.add_parser("run-archive", help="Archive a closed run out of the active workspace")
    p.add_argument("--work-id", required=True)
    p.set_defaults(func=_cmd_run_archive)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_cli.py::TestRunArchive -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

Run: `.venv/bin/python -m pytest tests/ -q` → all pass.

```bash
git status --short
git diff -- tools/workflow_cli/cli.py tests/test_cli.py
git add tools/workflow_cli/cli.py tests/test_cli.py
git commit -m "feat(r2p): add run-archive CLI command (move + untrack)"
```
(append the Co-Authored-By trailer)

---

### Task 6: `r2p-archive` shortcut + bin (with pointer clearing)

**Files:**
- Modify: `tools/workflow_cli/agent_shortcuts.py` (new `_cmd_archive`, parser, handler dispatch)
- Create: `tools/r2p-archive`
- Test: `tests/test_agent_shortcuts.py`

**Interfaces:**
- Consumes: `_run_cli`, `read_active_pointer`, `_pointer_path`, `_validate_work_id`.
- Produces: `r2p-archive [--work-id <id>]`. Resolves work_id from `--work-id` or the active pointer; calls CLI `run-archive`; on success, if the active pointer points at the archived id, deletes `.workflow-active` (so `r2p-continue` falls back to `no_selected_run`).

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_agent_shortcuts.py`:

```python
class TestArchiveShortcut(unittest.TestCase):
    def _closed_run(self, base, wid_str):
        from tools.workflow_cli.state import RunStateManager, create_run_record
        from tools.workflow_cli.models import RunStatus, Stage, WorkId
        wid = WorkId(wid_str)
        run_dir = base / ".req-to-plan" / wid_str
        run_dir.mkdir(parents=True)
        rec = create_run_record(wid)
        rec.status = RunStatus.CLOSED_AT_PLAN_CHECKPOINT
        rec.current_stage = Stage.CLOSED
        RunStateManager(run_dir).save(rec)

    def test_archive_clears_pointer_when_pointing_at_archived_run(self):
        import argparse
        import tempfile
        from pathlib import Path
        from tools.workflow_cli import agent_shortcuts as ash
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            self._closed_run(base, "WF-20260101-arch")
            ash.write_active_pointer(base, "WF-20260101-arch", reason="test")
            ns = argparse.Namespace(work_id="WF-20260101-arch")
            with self.assertRaises(SystemExit) as cm:
                ash._cmd_archive(ns, base)
            self.assertEqual(cm.exception.code, 0)
            self.assertFalse(ash._pointer_path(base).exists())
            self.assertTrue((base / ".req-to-plan" / "archive" / "WF-20260101-arch" / "run.md").exists())
```

> Implementer note: `tests/test_agent_shortcuts.py` imports `unittest` at module top but NOT `argparse`; the in-method `import argparse` above is required. `tempfile` is imported at module top; the in-method import is harmless but you may drop it.

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_agent_shortcuts.py::TestArchiveShortcut -v`
Expected: FAIL (`module 'agent_shortcuts' has no attribute '_cmd_archive'`).

- [ ] **Step 3: Implement the shortcut**

In `tools/workflow_cli/agent_shortcuts.py`, add the handler (next to `_cmd_reopen`):

```python
def _cmd_archive(ns: argparse.Namespace, base_path: Path) -> None:
    work_id = ns.work_id
    if not work_id:
        pointer = read_active_pointer(base_path)
        if not pointer:
            print("no_selected_run: true\nnext: r2p-archive --work-id <id>\n")
            sys.exit(1)
        work_id = pointer["selected_work_id"]
    work_id = _validate_work_id(work_id)
    exit_code = _run_cli(["run-archive", "--work-id", work_id], base_path)
    if exit_code != 0:
        sys.exit(exit_code)
    pointer = read_active_pointer(base_path)
    if pointer and pointer.get("selected_work_id") == work_id:
        _pointer_path(base_path).unlink(missing_ok=True)
    print(f"archived: {work_id}\nnext: r2p-status --all\n")
    sys.exit(0)
```

In `_build_parser`, add (next to the other subparsers):

```python
    p_archive = sub.add_parser("archive")
    p_archive.add_argument("--work-id", dest="work_id", default=None)
```

In `main`, add to the `handlers` dict:

```python
        "archive": _cmd_archive,
```

- [ ] **Step 4: Create the bin wrapper**

Create `tools/r2p-archive` (copy the `tools/r2p-continue` pattern, swapping the subcommand):

```bash
#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
export PYTHONPATH="$REPO_ROOT${PYTHONPATH:+:$PYTHONPATH}"
if command -v python3 >/dev/null 2>&1; then
    exec python3 -m tools.workflow_cli.agent_shortcuts archive "$@"
else
    exec python -m tools.workflow_cli.agent_shortcuts archive "$@"
fi
```

Then make it executable:

```bash
chmod +x tools/r2p-archive
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_agent_shortcuts.py::TestArchiveShortcut -v`
Expected: PASS.

- [ ] **Step 6: Commit**

Run: `.venv/bin/python -m pytest tests/ -q` → all pass.

```bash
git status --short
git diff -- tools/workflow_cli/agent_shortcuts.py tools/r2p-archive tests/test_agent_shortcuts.py
git add tools/workflow_cli/agent_shortcuts.py tools/r2p-archive tests/test_agent_shortcuts.py
git commit -m "feat(r2p): add r2p-archive shortcut + bin (clears active pointer)"
```
(append the Co-Authored-By trailer)

---

### Task 7: Document `r2p-archive` in README (bilingual) + skill-list test

**Files:**
- Modify: `README.md`, `README.zh-CN.md`
- Modify: `tests/test_readme.py` (`test_every_workflow_skill_is_documented`)

**Interfaces:** none (docs).

- [ ] **Step 1: Write the failing test change**

In `tests/test_readme.py`, in `test_every_workflow_skill_is_documented`, add `"r2p-archive"` to the `skills` tuple:

```python
    skills = (
        "r2p-start",
        "r2p-continue",
        "r2p-status",
        "r2p-switch",
        "r2p-tier-lock",
        "r2p-reopen",
        "r2p-gap-open",
        "r2p-gap-resolve",
        "r2p-archive",
    )
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_readme.py::test_every_workflow_skill_is_documented -v`
Expected: FAIL (`'r2p-archive' missing from README.md`).

- [ ] **Step 3: Add the skill to both READMEs**

In `README.md`, find the workflow-skill list/table containing `r2p-gap-resolve` and add a sibling entry for `r2p-archive` (e.g. "`r2p-archive` — archive a closed run out of the active workspace (moves it under `.req-to-plan/archive/` and untracks it)"). Add the **same entry, translated,** at the **same position** in `README.zh-CN.md`. Add only a list/table row — do **not** add a new `#` heading (keeps `test_heading_sequences_are_identical` green). Do not introduce the literal string `docs/` (keeps `test_readme_does_not_reference_docs` green).

- [ ] **Step 4: Run the README suite to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_readme.py -v`
Expected: PASS (all README tests green — skill documented, headings still identical in both files).

- [ ] **Step 5: Commit**

Run: `.venv/bin/python -m pytest tests/ -q` → all pass.

```bash
git status --short
git diff -- README.md README.zh-CN.md tests/test_readme.py
git add README.md README.zh-CN.md tests/test_readme.py
git commit -m "docs(r2p): document r2p-archive in both READMEs"
```
(append the Co-Authored-By trailer)

> **Phase 2 is independently mergeable here.** Manual archiving works end-to-end; PLAN completion lands the requirement directory in version control and archiving untracks it.

---

# Phase 3 — Execution Skill `r2p-execute` (depends on Phase 2's ARCHIVED + run-archive)

### Task 8: `RunStatus.EXECUTING` + state machine + `is_terminal` (executing stays open)

**Files:**
- Modify: `tools/workflow_cli/models.py` (`RunStatus`; `ALLOWED_TRANSITIONS`; `ALLOWED_COMMANDS_BY_RUN_STATE`)
- Test: `tests/test_models.py`, `tests/test_agent_shortcuts.py`

**Interfaces:**
- Produces: `RunStatus.EXECUTING = "executing"`; transitions `CLOSED_AT_PLAN_CHECKPOINT → {EXECUTING, ARCHIVED}`, `EXECUTING → {EXECUTING, ARCHIVED}`. `is_terminal(EXECUTING) is False` (executing blocks a new run). Commands: CLOSED gains `CMD-RUN-EXECUTE-START`; `EXECUTING: {CMD-RUN-ARCHIVE, CMD-TIER-STATUS}`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_models.py`:

```python
class TestExecutingState(unittest.TestCase):
    def test_executing_status_exists(self):
        from tools.workflow_cli.models import RunStatus
        self.assertEqual(RunStatus.EXECUTING.value, "executing")

    def test_closed_can_transition_to_executing(self):
        from tools.workflow_cli.models import RunStatus, is_transition_allowed
        self.assertTrue(
            is_transition_allowed(RunStatus.CLOSED_AT_PLAN_CHECKPOINT, RunStatus.EXECUTING)
        )

    def test_executing_can_transition_to_archived(self):
        from tools.workflow_cli.models import RunStatus, is_transition_allowed
        self.assertTrue(is_transition_allowed(RunStatus.EXECUTING, RunStatus.ARCHIVED))

    def test_execute_start_command_allowed_when_closed(self):
        from tools.workflow_cli.models import RunStatus, is_command_allowed
        self.assertTrue(
            is_command_allowed(RunStatus.CLOSED_AT_PLAN_CHECKPOINT, "CMD-RUN-EXECUTE-START")
        )
```

Append to `tests/test_agent_shortcuts.py`:

```python
class TestIsTerminalExecuting(unittest.TestCase):
    def test_executing_is_not_terminal(self):
        from tools.workflow_cli.agent_shortcuts import is_terminal
        from tools.workflow_cli.models import RunStatus
        self.assertFalse(is_terminal(RunStatus.EXECUTING))
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_models.py::TestExecutingState tests/test_agent_shortcuts.py::TestIsTerminalExecuting -v`
Expected: FAIL (`AttributeError: EXECUTING`).

- [ ] **Step 3: Add the enum member**

In `tools/workflow_cli/models.py`, in `RunStatus`, between `CLOSED_AT_PLAN_CHECKPOINT` and `ARCHIVED`:

```python
    CLOSED_AT_PLAN_CHECKPOINT = "closed_at_plan_checkpoint"
    EXECUTING = "executing"     # PLAN closed; implementing tasks in place
    ARCHIVED = "archived"       # terminal: requirement directory archived
```

- [ ] **Step 4: Extend transitions + command table**

In `ALLOWED_TRANSITIONS`, change the closed + archived block (from Task 1) to:

```python
    RunStatus.CLOSED_AT_PLAN_CHECKPOINT: {RunStatus.EXECUTING, RunStatus.ARCHIVED},
    RunStatus.EXECUTING: {RunStatus.EXECUTING, RunStatus.ARCHIVED},
    RunStatus.ARCHIVED: set(),
}
```

In `ALLOWED_COMMANDS_BY_RUN_STATE`, update the closed entry and add the executing entry:

```python
    RunStatus.CLOSED_AT_PLAN_CHECKPOINT: {
        "CMD-RUN-REOPEN",
        "CMD-RUN-EXECUTE-START",
        "CMD-RUN-ARCHIVE",
        "CMD-TIER-STATUS",
    },
    RunStatus.EXECUTING: {
        "CMD-RUN-ARCHIVE",
        "CMD-TIER-STATUS",
    },
    RunStatus.ARCHIVED: set(),
}
```

(`is_terminal` already returns False for `EXECUTING` since Task 5 of Phase 2 only lists CLOSED + ARCHIVED — no change needed.)

- [ ] **Step 5: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_models.py::TestExecutingState tests/test_agent_shortcuts.py::TestIsTerminalExecuting -v`
Expected: PASS (5 passed).

- [ ] **Step 6: Commit**

Run: `.venv/bin/python -m pytest tests/ -q` → all pass.

```bash
git status --short
git diff -- tools/workflow_cli/models.py tests/test_models.py tests/test_agent_shortcuts.py
git add tools/workflow_cli/models.py tests/test_models.py tests/test_agent_shortcuts.py
git commit -m "feat(r2p): add EXECUTING run state (open) + CLOSED→EXECUTING→ARCHIVED transitions"
```
(append the Co-Authored-By trailer)

---

### Task 9: Shared `plan_task_anchors()` helper in `markdown.py` (gates reuse)

**Files:**
- Modify: `tools/workflow_cli/markdown.py`
- Modify: `tools/workflow_cli/gates.py:255` (reuse the shared regex)
- Test: `tests/test_markdown.py`

**Interfaces:**
- Produces: `PLAN_TASK_ANCHOR_RE` (`re.compile(r"^### PLAN-TASK-\d+", re.MULTILINE)`) and `plan_task_anchors(content: str) -> list[tuple[str, str]]` returning `(PLAN-TASK-NNN, title remainder)` per task, fence-aware (anchors inside ``` fences are ignored).
- Consumes (gates): `gates.py` imports `PLAN_TASK_ANCHOR_RE` as its `_PLAN_TASK_RE`, so the CLI ledger seed (Task 10) and the existing gate checks parse PLAN tasks through one regex (single source of truth).

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_markdown.py` (this file uses bare pytest functions — no `unittest`, no classes; match that style):

```python
def test_plan_task_anchors_extracts_id_and_title():
    from tools.workflow_cli.markdown import plan_task_anchors
    content = (
        "## Tasks\n"
        "### PLAN-TASK-001: build the thing\n"
        "Files:\n- a.py\n"
        "### PLAN-TASK-002: wire it up\n"
        "Files:\n- b.py\n"
    )
    assert plan_task_anchors(content) == [
        ("PLAN-TASK-001", "build the thing"),
        ("PLAN-TASK-002", "wire it up"),
    ]


def test_plan_task_anchors_ignores_code_fences():
    from tools.workflow_cli.markdown import plan_task_anchors
    content = (
        "## Tasks\n"
        "```\n"
        "### PLAN-TASK-999: not a real task\n"
        "```\n"
        "### PLAN-TASK-001: real task\n"
    )
    assert plan_task_anchors(content) == [("PLAN-TASK-001", "real task")]


def test_plan_task_anchors_empty_when_no_tasks():
    from tools.workflow_cli.markdown import plan_task_anchors
    assert plan_task_anchors("# Plan\n\nno tasks here\n") == []
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_markdown.py -k plan_task_anchors -v`
Expected: FAIL (`cannot import name 'plan_task_anchors'`).

- [ ] **Step 3: Implement the helper**

In `tools/workflow_cli/markdown.py`, append:

```python
# A PLAN-TASK anchor heading, e.g. "### PLAN-TASK-001: title". Single source of
# truth shared by gates (task iteration) and cli (ledger seeding).
PLAN_TASK_ANCHOR_RE = re.compile(r"^### PLAN-TASK-\d+", re.MULTILINE)
_PLAN_TASK_ANCHOR_LINE_RE = re.compile(r"^###\s+(PLAN-TASK-\d+)\s*:?\s*(.*?)\s*$")


def plan_task_anchors(content: str) -> list[tuple[str, str]]:
    """Return (PLAN-TASK-NNN, title) for each task anchor outside code fences."""
    anchors: list[tuple[str, str]] = []
    for line, _, _ in unfenced_markdown_lines(content):
        if not PLAN_TASK_ANCHOR_RE.match(line):
            continue
        m = _PLAN_TASK_ANCHOR_LINE_RE.match(line.rstrip("\n"))
        if m:
            anchors.append((m.group(1), m.group(2).strip()))
    return anchors
```

- [ ] **Step 4: Point gates at the shared regex**

In `tools/workflow_cli/gates.py`, replace the local definition at line 255:

```python
_PLAN_TASK_RE = re.compile(r"^### PLAN-TASK-\d+", re.MULTILINE)
```

with an import alias. Add to the existing `from tools.workflow_cli.markdown import ...` line (gates already imports `unfenced_markdown_lines`/`heading_bounded_bodies` from markdown):

```python
from tools.workflow_cli.markdown import (
    # ...existing names...,
    PLAN_TASK_ANCHOR_RE as _PLAN_TASK_RE,
)
```

and delete the old line-255 assignment. (Verify the existing import block's exact names first; keep them, just add `PLAN_TASK_ANCHOR_RE as _PLAN_TASK_RE`.)

- [ ] **Step 5: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_markdown.py tests/test_gates.py -q`
Expected: PASS — markdown helper green, and the full gate suite still green (gates now uses the imported regex, behaviorally identical to the deleted local one).

- [ ] **Step 6: Commit**

Run: `.venv/bin/python -m pytest tests/ -q` → all pass.

```bash
git status --short
git diff -- tools/workflow_cli/markdown.py tools/workflow_cli/gates.py tests/test_markdown.py
git add tools/workflow_cli/markdown.py tools/workflow_cli/gates.py tests/test_markdown.py
git commit -m "refactor(r2p): extract shared plan_task_anchors() helper to markdown.py"
```
(append the Co-Authored-By trailer)

---

### Task 10: `run-execute-start` CLI command (status + ledger skeleton)

**Files:**
- Modify: `tools/workflow_cli/cli.py` (new `_cmd_run_execute_start` + register)
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: `update_run_status`, `atomic_write_text`, `plan_task_anchors`, `read_artifact`/`STAGE_ARTIFACT_MAP`.
- Produces: `run-execute-start --work-id <id>`. Strict precondition `status == CLOSED_AT_PLAN_CHECKPOINT` else `EXIT_CONFLICT` (`plan_not_ready`). On success: `CLOSED → EXECUTING`; seeds `<run>/execution/progress.md` with a structured skeleton (one `- [ ] PLAN-TASK-NNN <title>` per task parsed from `07-plan.md`). Skeleton is structure only (no semantics) — agent appends progress.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_cli.py`:

```python
class TestRunExecuteStart:
    def _closed_run_with_plan(self, base, wid_str, plan_body):
        from tools.workflow_cli.state import RunStateManager, create_run_record
        from tools.workflow_cli.models import RunStatus, Stage, WorkId
        from tools.workflow_cli.artifact import write_artifact
        wid = WorkId(wid_str)
        run_dir = base / ".req-to-plan" / wid_str
        run_dir.mkdir(parents=True)
        rec = create_run_record(wid)
        rec.status = RunStatus.CLOSED_AT_PLAN_CHECKPOINT
        rec.current_stage = Stage.CLOSED
        write_artifact(run_dir, Stage.PLAN, plan_body, version=1, status="approved")
        RunStateManager(run_dir).save(rec)
        return run_dir

    def test_execute_start_sets_executing_and_seeds_ledger(self):
        from tools.workflow_cli.state import RunStateManager
        plan = (
            "# Plan\n\n## Tasks\n"
            "### PLAN-TASK-001: first task\nFiles:\n- a.py\n"
            "### PLAN-TASK-002: second task\nFiles:\n- b.py\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            run_dir = self._closed_run_with_plan(base, "WF-20260101-exec", plan)
            with pytest.raises(SystemExit) as exc:
                main(["--base-path", str(base), "run-execute-start", "--work-id", "WF-20260101-exec"])
            assert exc.value.code == 0
            rec = RunStateManager(run_dir).load()
            assert rec.status.value == "executing"
            ledger = (run_dir / "execution" / "progress.md").read_text(encoding="utf-8")
            assert "- [ ] PLAN-TASK-001 first task" in ledger
            assert "- [ ] PLAN-TASK-002 second task" in ledger

    def test_execute_start_refuses_when_not_closed(self):
        from tools.workflow_cli.state import RunStateManager, create_run_record
        from tools.workflow_cli.models import WorkId
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            wid = WorkId("WF-20260101-open")
            run_dir = base / ".req-to-plan" / "WF-20260101-open"
            run_dir.mkdir(parents=True)
            RunStateManager(run_dir).save(create_run_record(wid))  # ACTIVE_STAGE_DRAFT
            with pytest.raises(SystemExit) as exc:
                main(["--base-path", str(base), "run-execute-start", "--work-id", "WF-20260101-open"])
            assert exc.value.code == 6  # EXIT_CONFLICT
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_cli.py::TestRunExecuteStart -v`
Expected: FAIL (`invalid choice: 'run-execute-start'`).

- [ ] **Step 3: Implement `_cmd_run_execute_start`**

In `tools/workflow_cli/cli.py`, add the imports near the top (with the other `from tools.workflow_cli...` lines):

```python
from tools.workflow_cli.atomic import atomic_write_text
from tools.workflow_cli.markdown import plan_task_anchors
```

Add the handler after `_cmd_run_archive`:

```python
def _cmd_run_execute_start(args):
    record, mgr, run_dir = _load_run(args.work_id, args.base_path)
    if record.status != RunStatus.CLOSED_AT_PLAN_CHECKPOINT:
        print_and_exit(
            format_error(
                f"Cannot start execution in status {record.status.value!r}; "
                "must be closed_at_plan_checkpoint (plan_not_ready)",
                exit_code=EXIT_CONFLICT,
            ),
            EXIT_CONFLICT,
        )
    try:
        plan_text = read_artifact(run_dir, Stage.PLAN)
    except FileNotFoundError:
        print_and_exit(
            format_error("PLAN artifact not found; cannot start execution", exit_code=EXIT_NOT_FOUND),
            EXIT_NOT_FOUND,
        )
    record = update_run_status(record, RunStatus.EXECUTING)
    update_resume_context(record, last_operation="execute_start", next_operation="implement_tasks")
    mgr.save(record)
    # Seed the structural progress ledger (IDs + checkboxes = structure, not
    # semantics; the agent appends progress). CLI never generates artifact text.
    anchors = plan_task_anchors(plan_text)
    lines = ["# Execution Progress", "", f"work_id: {record.work_id}", ""]
    lines += [f"- [ ] {tid} {title}".rstrip() for tid, title in anchors]
    exec_dir = run_dir / "execution"
    exec_dir.mkdir(parents=True, exist_ok=True)
    atomic_write_text(exec_dir / "progress.md", "\n".join(lines) + "\n")
    print_and_exit(
        format_success(
            {
                "work_id": str(record.work_id),
                "status": record.status.value,
                "ledger": str(exec_dir / "progress.md"),
                "task_count": len(anchors),
            },
            message=f"Execution started: {record.work_id}",
        ),
        EXIT_OK,
    )
```

In `_register_run_commands`, after the `run-archive` block:

```python
    # run-execute-start
    p = subparsers.add_parser("run-execute-start", help="Begin executing a closed run's PLAN in place")
    p.add_argument("--work-id", required=True)
    p.set_defaults(func=_cmd_run_execute_start)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_cli.py::TestRunExecuteStart -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

Run: `.venv/bin/python -m pytest tests/ -q` → all pass.

```bash
git status --short
git diff -- tools/workflow_cli/cli.py tests/test_cli.py
git add tools/workflow_cli/cli.py tests/test_cli.py
git commit -m "feat(r2p): add run-execute-start CLI (CLOSED→EXECUTING + ledger skeleton)"
```
(append the Co-Authored-By trailer)

---

### Task 11: `execute` shortcut + bin, `r2p-continue` routing, and `run-archive` accepts EXECUTING

**Files:**
- Modify: `tools/workflow_cli/agent_shortcuts.py` (new `_cmd_execute`, parser, handler; `_cmd_continue` routing)
- Modify: `tools/workflow_cli/cli.py` (`_cmd_run_archive` precondition widened to include EXECUTING)
- Create: `tools/r2p-execute`
- Test: `tests/test_agent_shortcuts.py`, `tests/test_cli.py`

**Interfaces:**
- Produces: `r2p-execute [--work-id <id>]` — CLOSED → calls `run-execute-start`, prints `stop: execute_plan` (with `plan`, `ledger`, drive-the-skill note); EXECUTING → prints `stop: resume_execution` (+ ledger path); other → `blocked: plan_not_ready`. `r2p-continue` gains EXECUTING → `stop: resume_execution`, ARCHIVED → `done: archived`, and the CLOSED branch is extended with `to implement:`/`to archive:` hints. `run-archive` now also archives an EXECUTING run.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_agent_shortcuts.py`:

```python
class TestExecuteShortcutAndRouting(unittest.TestCase):
    def _run(self, base, wid_str, status):
        from tools.workflow_cli.state import RunStateManager, create_run_record
        from tools.workflow_cli.models import RunStatus, Stage, WorkId
        from tools.workflow_cli.artifact import write_artifact
        wid = WorkId(wid_str)
        run_dir = base / ".req-to-plan" / wid_str
        run_dir.mkdir(parents=True)
        rec = create_run_record(wid)
        rec.status = status
        rec.current_stage = Stage.CLOSED if status != RunStatus.ACTIVE_STAGE_DRAFT else Stage.RAW_REQUIREMENT
        write_artifact(run_dir, Stage.PLAN, "# Plan\n\n## Tasks\n### PLAN-TASK-001: t\n", version=1, status="approved")
        RunStateManager(run_dir).save(rec)
        from tools.workflow_cli import agent_shortcuts as ash
        ash.write_active_pointer(base, wid_str, reason="test")
        return run_dir

    def _capture(self, fn, *a):
        import io, contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            with self.assertRaises(SystemExit) as cm:
                fn(*a)
        return buf.getvalue(), cm.exception.code

    def test_execute_on_closed_starts_and_prints_execute_plan(self):
        import tempfile, argparse
        from pathlib import Path
        from tools.workflow_cli import agent_shortcuts as ash
        from tools.workflow_cli.models import RunStatus
        from tools.workflow_cli.state import RunStateManager
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            run_dir = self._run(base, "WF-20260101-exec", RunStatus.CLOSED_AT_PLAN_CHECKPOINT)
            out, code = self._capture(ash._cmd_execute, argparse.Namespace(work_id="WF-20260101-exec"), base)
            self.assertEqual(code, 0)
            self.assertIn("stop: execute_plan", out)
            self.assertEqual(RunStateManager(run_dir).load().status, RunStatus.EXECUTING)

    def test_execute_on_executing_prints_resume(self):
        import tempfile, argparse
        from pathlib import Path
        from tools.workflow_cli import agent_shortcuts as ash
        from tools.workflow_cli.models import RunStatus
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            self._run(base, "WF-20260101-exec", RunStatus.EXECUTING)
            out, code = self._capture(ash._cmd_execute, argparse.Namespace(work_id="WF-20260101-exec"), base)
            self.assertIn("stop: resume_execution", out)

    def test_continue_routes_executing_to_resume(self):
        import tempfile, argparse
        from pathlib import Path
        from tools.workflow_cli import agent_shortcuts as ash
        from tools.workflow_cli.models import RunStatus
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            self._run(base, "WF-20260101-exec", RunStatus.EXECUTING)
            out, _ = self._capture(ash._cmd_continue, argparse.Namespace(), base)
            self.assertIn("resume_execution", out)
```

Append to `tests/test_cli.py` (`run-archive` now accepts EXECUTING):

```python
class TestRunArchiveFromExecuting:
    def test_archive_executing_run(self):
        from tools.workflow_cli.state import RunStateManager, create_run_record
        from tools.workflow_cli.models import RunStatus, Stage, WorkId
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            wid = WorkId("WF-20260101-exec")
            run_dir = base / ".req-to-plan" / "WF-20260101-exec"
            run_dir.mkdir(parents=True)
            rec = create_run_record(wid)
            rec.status = RunStatus.EXECUTING
            rec.current_stage = Stage.CLOSED
            RunStateManager(run_dir).save(rec)
            with pytest.raises(SystemExit) as exc:
                main(["--base-path", str(base), "run-archive", "--work-id", "WF-20260101-exec"])
            assert exc.value.code == 0
            assert (base / ".req-to-plan" / "archive" / "WF-20260101-exec" / "run.md").exists()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_agent_shortcuts.py::TestExecuteShortcutAndRouting tests/test_cli.py::TestRunArchiveFromExecuting -v`
Expected: FAIL (`_cmd_execute` missing; EXECUTING archive returns EXIT_CONFLICT).

- [ ] **Step 3: Widen `run-archive` to accept EXECUTING**

In `tools/workflow_cli/cli.py`, in `_cmd_run_archive`, change:

```python
    archivable = {RunStatus.CLOSED_AT_PLAN_CHECKPOINT}
```

to:

```python
    archivable = {RunStatus.CLOSED_AT_PLAN_CHECKPOINT, RunStatus.EXECUTING}
```

- [ ] **Step 4: Implement the `execute` shortcut**

In `tools/workflow_cli/agent_shortcuts.py`, add the handler:

```python
def _cmd_execute(ns: argparse.Namespace, base_path: Path) -> None:
    work_id = ns.work_id
    if not work_id:
        pointer = read_active_pointer(base_path)
        if not pointer:
            print("no_selected_run: true\nnext: r2p-execute --work-id <id>\n")
            sys.exit(1)
        work_id = pointer["selected_work_id"]
    work_id = _validate_work_id(work_id)
    run_path = base_path / ".req-to-plan" / work_id / "run.md"
    if not run_path.exists():
        print(f"blocked: source_run_not_found\nwork_id: {work_id}\n")
        sys.exit(7)

    from tools.workflow_cli.state import RunStateManager
    record = RunStateManager(run_path.parent).load()
    ledger = run_path.parent / "execution" / "progress.md"

    if record.status == RunStatus.CLOSED_AT_PLAN_CHECKPOINT:
        code = _run_cli(["run-execute-start", "--work-id", work_id], base_path)
        if code != 0:
            sys.exit(code)
        print(
            "stop: execute_plan\n"
            f"work_id: {work_id}\n"
            "plan: 07-plan.md\n"
            f"ledger: {ledger}\n"
            "next: drive the r2p-execute skill (subagent-driven SDD loop) to "
            "implement each PLAN-TASK in place on the current branch, then "
            "r2p-archive when done\n"
        )
        sys.exit(0)

    if record.status == RunStatus.EXECUTING:
        print(
            "stop: resume_execution\n"
            f"work_id: {work_id}\n"
            f"ledger: {ledger}\n"
            "next: resume the r2p-execute loop from the first unchecked task in "
            "the ledger\n"
        )
        sys.exit(0)

    print(f"blocked: plan_not_ready\nwork_id: {work_id}\nstatus: {record.status.value}\nnext: r2p-continue\n")
    sys.exit(EXIT_CONFLICT)
```

Register it: in `_build_parser` add

```python
    p_execute = sub.add_parser("execute")
    p_execute.add_argument("--work-id", dest="work_id", default=None)
```

and in `main`'s `handlers` dict add `"execute": _cmd_execute,`.

- [ ] **Step 5: Add EXECUTING/ARCHIVED routing to `r2p-continue`**

In `tools/workflow_cli/agent_shortcuts.py`, in `_cmd_continue`'s loop, add these branches **before** the existing `if s == RunStatus.CLOSED_AT_PLAN_CHECKPOINT:` block:

```python
        if s == RunStatus.EXECUTING:
            ledger = run_path.parent / "execution" / "progress.md"
            print(
                "stop: resume_execution\n"
                f"work_id: {work_id}\n"
                f"ledger: {ledger}\n"
                "next: resume the r2p-execute loop from the first unchecked task\n"
            )
            sys.exit(0)

        if s == RunStatus.ARCHIVED:
            print(f"done: archived\nwork_id: {work_id}\n")
            sys.exit(0)
```

And extend the existing CLOSED branch body to append execute/archive hints:

```python
        if s == RunStatus.CLOSED_AT_PLAN_CHECKPOINT:
            print(f"done: run_closed\nwork_id: {work_id}\nplan: 07-plan.md\n"
                  "next: hand the PLAN to your executor\n"
                  f"to implement: r2p-execute --work-id {work_id}\n"
                  f"to archive: r2p-archive --work-id {work_id}\n")
            sys.exit(0)
```

- [ ] **Step 6: Create the bin wrapper**

Create `tools/r2p-execute` (copy the `tools/r2p-continue` pattern, subcommand `execute`):

```bash
#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
export PYTHONPATH="$REPO_ROOT${PYTHONPATH:+:$PYTHONPATH}"
if command -v python3 >/dev/null 2>&1; then
    exec python3 -m tools.workflow_cli.agent_shortcuts execute "$@"
else
    exec python -m tools.workflow_cli.agent_shortcuts execute "$@"
fi
```

Then: `chmod +x tools/r2p-execute`

- [ ] **Step 7: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_agent_shortcuts.py::TestExecuteShortcutAndRouting tests/test_cli.py::TestRunArchiveFromExecuting -v`
Expected: PASS (4 passed).

- [ ] **Step 8: Commit**

Run: `.venv/bin/python -m pytest tests/ -q` → all pass.

```bash
git status --short
git diff -- tools/workflow_cli/agent_shortcuts.py tools/workflow_cli/cli.py tools/r2p-execute tests/test_agent_shortcuts.py tests/test_cli.py
git add tools/workflow_cli/agent_shortcuts.py tools/workflow_cli/cli.py tools/r2p-execute tests/test_agent_shortcuts.py tests/test_cli.py
git commit -m "feat(r2p): add r2p-execute shortcut/bin + EXECUTING/ARCHIVED continue routing"
```
(append the Co-Authored-By trailer)

---

### Task 12: Three-platform `r2p-execute` skill templates (self-contained SDD replica)

**Files:**
- Create: `tools/workflow_cli/agent_templates/claude/commands/r2p-execute.md`
- Create: `tools/workflow_cli/agent_templates/codex/skills/r2p-execute/SKILL.md`
- Create: `tools/workflow_cli/agent_templates/gemini/commands/r2p-execute.toml`
- Test: `tests/test_install.py`, `tests/test_docs_consistency.py`

**Interfaces:** none (templates installed by the existing globs — claude `commands/r2p-*.md`, codex `skills/r2p-*/SKILL.md`, gemini `commands/r2p-*.toml`; no installer change).

**Required content (claude + codex carry the full orchestration prose; gemini carries a short description + the bin command).** Each of the claude `.md` and codex `SKILL.md` MUST contain, as literal tokens the test pins, an SDD-replica orchestration adapted (not byte-copied) from superpowers 6.0.3 `subagent-driven-development` — read `/Users/xubo/.claude/plugins/cache/claude-plugins-official/superpowers/6.0.3/skills/subagent-driven-development/{SKILL.md,implementer-prompt.md,task-reviewer-prompt.md}` as the source, then write a self-contained, trimmed version covering:
1. **Precondition gate:** requires `closed_at_plan_checkpoint` (first run → `run-execute-start` transitions to `executing`) or `executing` (resume); any other status stops `plan_not_ready`.
2. **In-place, no branch (deliberate difference from SDD):** implement and commit on the current branch — no new branch, no worktree, no main-branch protection. Only lightweight pre-check: warn (do not block) if the user's **code** working tree is dirty, **excluding `.req-to-plan/`**. `push`/PR are out of scope (explicit user request only).
3. **Pre-flight plan review:** scan `07-plan.md` once for conflicting tasks / plan-mandated-but-defect items; batch them to the human before task 1.
4. **Per-task loop (`Verification` is the per-task completion gate):** extract the task text inline from `07-plan.md` (no external `task-brief` script) → dispatch a fresh implementer subagent (TDD per `Skeleton`/`Steps`) → implementer must satisfy that task's `Verification` and attach evidence → write the diff inline (`git diff -U10`, no external `review-package` script) → dispatch a task-reviewer (two verdicts: spec compliance checked against `Spec References` + `Verification`; code quality) → dispatch fix subagents for Critical/Important → only when the review is clean (including `Verification` satisfied) append `Task N: complete` to `execution/progress.md`, else loop.
5. **Ambiguity ladder (execution tier of spec §2.3):** implementer verifies-then-removes ambiguity by evidence/TDD; if it cannot, return `NEEDS_CONTEXT`/`BLOCKED` and escalate to the human — never guess a vague implementation; if the ambiguity is an upstream (SPEC/DESIGN) defect, stop and route via `r2p-gap-open` rather than patching over it in execution.
6. **Final whole-branch review** once.
7. **Auto-archive on completion:** all tasks done + final review clean → call `r2p-archive`. Commits already landed on the current branch; `push`/PR still require explicit user request.
8. **Subagents are a hard prerequisite — no degrade fallback:** if the platform lacks subagent capability, fail explicitly and let the human decide; never silently fall back to sequential execution.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_docs_consistency.py`:

```python
class TestExecuteTemplateContent(unittest.TestCase):
    def test_execute_surfaces_carry_sdd_orchestration_tokens(self):
        surfaces = [
            "tools/workflow_cli/agent_templates/claude/commands/r2p-execute.md",
            "tools/workflow_cli/agent_templates/codex/skills/r2p-execute/SKILL.md",
        ]
        required = (
            "closed_at_plan_checkpoint",
            "current branch",          # in-place, no branch
            "Pre-flight",
            "Verification",            # per-task completion gate
            "fresh implementer subagent",
            "task-reviewer",
            "whole-branch review",
            "r2p-archive",
            "hard prerequisite",       # no subagent degrade
            "NEEDS_CONTEXT",           # ambiguity ladder
        )
        missing = []
        for rel in surfaces:
            text = (REPO_ROOT / rel).read_text(encoding="utf-8")
            for tok in required:
                if tok not in text:
                    missing.append(f"{rel}:{tok}")
        self.assertEqual(missing, [], f"missing SDD tokens: {missing}")

    def test_gemini_execute_toml_mentions_in_place_and_archive(self):
        text = (REPO_ROOT / "tools/workflow_cli/agent_templates/gemini/commands/r2p-execute.toml").read_text(encoding="utf-8")
        self.assertIn("r2p-execute", text)
        self.assertIn("current branch", text)
```

Append to `tests/test_install.py` (inside `TestInstallService` — a plain pytest class: methods take `self, tmp_path`, use bare `assert`, and the helper `make_service(tmp_path)` returns `(service, manifest_root, ph_root)`):

```python
    def test_install_ships_r2p_execute_for_all_platforms(self, tmp_path):
        service, _manifest_root, ph_root = make_service(tmp_path)
        for platform, rel in (
            ("claude", "commands/r2p-execute.md"),
            ("codex", "skills/r2p-execute/SKILL.md"),
            ("gemini", "commands/r2p-execute.toml"),
        ):
            service.install(platform)
            assert (ph_root / platform / rel).exists(), f"{platform}:{rel} not installed"
```

> Implementer note: confirm `make_service`'s exact signature/return at the top of `tests/test_install.py` before relying on it.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_docs_consistency.py::TestExecuteTemplateContent tests/test_install.py::TestInstallService::test_install_ships_r2p_execute_for_all_platforms -v`
Expected: FAIL (template files do not exist).

- [ ] **Step 3: Write the claude template**

Create `tools/workflow_cli/agent_templates/claude/commands/r2p-execute.md` with full orchestration prose covering all 8 points above. Use `{{R2P_BIN_DIR}}` for bin paths and `{{R2P_VERSION}}` where a version is referenced (the installer renders these). Mirror the structure/voice of the existing `commands/r2p-continue.md`. Ensure every token in the test's `required` tuple appears verbatim.

- [ ] **Step 4: Write the codex template**

Create `tools/workflow_cli/agent_templates/codex/skills/r2p-execute/SKILL.md` with the same orchestration content as the claude file (Markdown; codex skills are Markdown), front-matter matching the other codex `skills/r2p-*/SKILL.md` files (inspect one, e.g. `codex/skills/r2p-continue/SKILL.md`). Ensure the same required tokens appear.

- [ ] **Step 5: Write the gemini template**

Create `tools/workflow_cli/agent_templates/gemini/commands/r2p-execute.toml` mirroring `gemini/commands/r2p-continue.toml`:

```toml
name = "r2p-execute"
description = "Execute a closed run's PLAN in place on the current branch via the subagent-driven SDD loop, then archive. Implements each PLAN-TASK with a fresh implementer subagent + task review; subagents are required."
command = "{{R2P_BIN_DIR}}/r2p-execute"
version = "{{R2P_VERSION}}"
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_docs_consistency.py::TestExecuteTemplateContent tests/test_install.py -v`
Expected: PASS (template tokens present; all three platforms install r2p-execute; existing install tests still green).

- [ ] **Step 7: Commit**

Run: `.venv/bin/python -m pytest tests/ -q` → all pass.

```bash
git status --short
git diff -- tools/workflow_cli/agent_templates tests/test_docs_consistency.py tests/test_install.py
git add tools/workflow_cli/agent_templates tests/test_docs_consistency.py tests/test_install.py
git commit -m "feat(r2p): add self-contained r2p-execute SDD skill templates (3 platforms)"
```
(append the Co-Authored-By trailer)

---

### Task 13: Document `r2p-execute` (bilingual README + skill test) + update CLAUDE.md invariant

**Files:**
- Modify: `README.md`, `README.zh-CN.md`
- Modify: `tests/test_readme.py` (`test_every_workflow_skill_is_documented`)
- Modify: `CLAUDE.md` (Key Invariants — terminal status)

**Interfaces:** none (docs).

- [ ] **Step 1: Write the failing test change**

In `tests/test_readme.py`, add `"r2p-execute"` to the `skills` tuple (now also containing `"r2p-archive"` from Task 7).

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_readme.py::test_every_workflow_skill_is_documented -v`
Expected: FAIL (`'r2p-execute' missing from README.md`).

- [ ] **Step 3: Add the skill to both READMEs**

In `README.md` and `README.zh-CN.md`, add an `r2p-execute` entry beside `r2p-archive` (same position in both, list/table row only, no new heading, no `docs/` literal). Suggested text: "`r2p-execute` — implement a closed run's PLAN in place on the current branch via the subagent-driven SDD loop, then archive."

- [ ] **Step 4: Update the CLAUDE.md invariant**

In `CLAUDE.md`, under "Key Invariants", replace the **Terminal status** bullet:

```markdown
- **Terminal status**: Only `RunStatus.CLOSED_AT_PLAN_CHECKPOINT` is terminal. All others are open.
```

with:

```markdown
- **Terminal status**: `RunStatus.ARCHIVED` is the terminal state. `EXECUTING` is open (an executing run blocks starting a new one); `CLOSED_AT_PLAN_CHECKPOINT` is also non-blocking for new runs but is reopen/execute/archive-able. `is_terminal()` returns True only for CLOSED and ARCHIVED.
```

- [ ] **Step 5: Run the README suite to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_readme.py -v`
Expected: PASS (both skills documented; headings still identical).

- [ ] **Step 6: Commit**

Run: `.venv/bin/python -m pytest tests/ -q` → all pass.

```bash
git status --short
git diff -- README.md README.zh-CN.md tests/test_readme.py CLAUDE.md
git add README.md README.zh-CN.md tests/test_readme.py CLAUDE.md
git commit -m "docs(r2p): document r2p-execute + update terminal-status invariant"
```
(append the Co-Authored-By trailer)

> **Phase 3 is independently mergeable here.** The full requirement → PLAN → implement → archive loop is in place.

---

## Final verification (after all tasks)

- [ ] **Run the whole suite:** `.venv/bin/python -m pytest tests/ -q` → all green (4 expected skips).
- [ ] **Smoke archiving:** on a CLOSED run in a temp git repo, `run-close` commits `.req-to-plan/<id>/`; `run-archive` moves it under `.req-to-plan/archive/<id>/`, sets `ARCHIVED`, and the original path is no longer tracked (`git ls-files` empty for it).
- [ ] **Smoke execution routing:** `r2p-execute` on a CLOSED run transitions to `EXECUTING` and prints `stop: execute_plan` with the ledger path; `r2p-continue` on an EXECUTING run prints `stop: resume_execution`; `r2p-archive` archives an EXECUTING run.
- [ ] **Smoke install:** `install --platform {claude,codex,gemini}` ships `r2p-execute` (and `r2p-archive` via the bin glob) for each platform.

## Self-Review (checklist run against the spec)

**1. Spec coverage:**
- §3.2 EXECUTING/ARCHIVED states + transitions + `is_terminal` → Tasks 1, 8 ✅
- §3.3 `run-execute-start` (status + ledger skeleton) + `plan_task_anchors` extraction → Tasks 9, 10 ✅
- §3.4/§3.5 `execute` shortcut + bin + `r2p-continue` routing → Task 11 ✅
- §3.6 self-contained SDD-replica templates (3 platforms; subagent hard prerequisite; in-place) → Task 12 ✅
- §3.7 install (no installer change; templates ship via existing globs) + README + skill test → Tasks 12, 13 ✅
- §4.1/§4.2 archive dir + `.gitignore /archive` + `run-archive` (move, no-clobber, status) → Tasks 2, 5 ✅
- §4.3 scan compatibility (double-level `archive/<id>/run.md` auto-excluded) → no code change needed (glob is `*/run.md`); covered by archiving leaving runs out of `scan_open_runs` ✅
- §4.4 two archive paths (auto via execute end; manual via r2p-archive) → Tasks 11, 6 ✅
- §4.5 unified `commit_requirement_dir` (close=add, archive=remove) + three guards → Tasks 3, 4, 5 ✅
- §4.6 version-control lifecycle (close commits in; archive move + delete-commit untracks) → Tasks 4, 5; verified by `test_archive_move_then_commit_untracks_dir` ✅
- Out of scope (correctly absent): fsync, manifest atomicity, run_dir-symlink, reopen logic change, subagent degrade, auto-sequential fallback. (spec §5.2–§5.5, §8 non-scope) ✅

**2. Placeholder scan:** no TBD/TODO/"similar to Task N" — every code step carries full code; every run step carries the exact command + expected result. Task 12's prose-template step names the source files to adapt and pins required tokens via a test (not a placeholder — a concrete, testable content contract).

**3. Type/name consistency:** `ensure_workspace_gitignore` / `commit_requirement_dir` (defined Tasks 2/3) are referenced by the same names in Tasks 4/5. `plan_task_anchors` / `PLAN_TASK_ANCHOR_RE` (Task 9) are used by Task 10 and gates. `RunStatus.EXECUTING`/`ARCHIVED`, `_cmd_run_archive`, `_cmd_run_execute_start`, `_cmd_archive`, `_cmd_execute` names match across tasks. `EXIT_CONFLICT=6`, `EXIT_NOT_FOUND=7` match `output.py`.

**Known deviations from the spec (intentional, flagged):**
- §3.6 lists separate `implementer-prompt.md`/`task-reviewer-prompt.md` files; this plan inlines them into each platform's single skill file because the installer ships one file per skill per platform (§3.7 "no installer change"). Net behavior — a self-contained SDD replica — is unchanged.
- §4.2 step 6 places pointer-clearing in the CLI; this plan puts it in the shortcut layer (`_cmd_archive`, Task 6) to keep the CLI free of pointer coupling. Both archive paths (auto/manual) go through the shortcut, so the pointer is still cleared.

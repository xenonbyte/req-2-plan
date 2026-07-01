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
            lines = gi.read_text(encoding="utf-8").splitlines()
            self.assertIn("/archive", lines)
            self.assertIn("/.workflow-active", lines)
            self.assertIn("/*/logs/", lines)

    def test_workspace_gitignore_includes_run_logs(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            ensure_workspace_gitignore(base)
            gitignore = base / ".req-to-plan" / ".gitignore"

            self.assertIn("/*/logs/", gitignore.read_text(encoding="utf-8").splitlines())

    def test_workspace_gitignore_includes_run_execution(self):
        # Execution artifacts (progress.md, task-N-report/review.md, final-review*)
        # are local audit trail, never shared git history — ignored like logs/ so a
        # stray `git add -A` cannot sweep them into the code branch.
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            ensure_workspace_gitignore(base)
            gitignore = base / ".req-to-plan" / ".gitignore"

            self.assertIn("/*/execution/", gitignore.read_text(encoding="utf-8").splitlines())

    def test_appends_archive_line_when_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            (base / ".req-to-plan").mkdir(parents=True)
            (base / ".req-to-plan" / ".gitignore").write_text("*.log\n", encoding="utf-8")
            ensure_workspace_gitignore(base)
            lines = (base / ".req-to-plan" / ".gitignore").read_text(encoding="utf-8").splitlines()
            self.assertIn("*.log", lines)
            self.assertIn("/archive", lines)
            self.assertIn("/.workflow-active", lines)
            self.assertIn("/*/logs/", lines)

    def test_appends_run_logs_line_without_dropping_existing_entries(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            gitignore = base / ".req-to-plan" / ".gitignore"
            gitignore.parent.mkdir(parents=True)
            gitignore.write_text("*.tmp\n/archive\n/.workflow-active\n", encoding="utf-8")

            ensure_workspace_gitignore(base)

            lines = gitignore.read_text(encoding="utf-8").splitlines()
            self.assertIn("*.tmp", lines)
            self.assertIn("/archive", lines)
            self.assertIn("/.workflow-active", lines)
            self.assertIn("/*/logs/", lines)

    def test_appends_active_pointer_line_when_archive_line_present(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            (base / ".req-to-plan").mkdir(parents=True)
            (base / ".req-to-plan" / ".gitignore").write_text("/archive\n", encoding="utf-8")
            ensure_workspace_gitignore(base)
            lines = (base / ".req-to-plan" / ".gitignore").read_text(encoding="utf-8").splitlines()
            self.assertIn("/archive", lines)
            self.assertIn("/.workflow-active", lines)
            self.assertIn("/*/logs/", lines)

    def test_idempotent_when_line_present(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            ensure_workspace_gitignore(base)
            ensure_workspace_gitignore(base)
            text = (base / ".req-to-plan" / ".gitignore").read_text(encoding="utf-8")
            self.assertEqual(text.count("/archive"), 1)
            self.assertEqual(text.count("/.workflow-active"), 1)
            self.assertEqual(text.count("/*/logs/"), 1)

    def test_rejects_symlinked_req_to_plan_dir_without_writing_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            outside = base / "outside"
            outside.mkdir()
            (base / ".req-to-plan").symlink_to(outside, target_is_directory=True)

            with self.assertRaisesRegex(ValueError, "unsafe_workspace_dir_symlink"):
                ensure_workspace_gitignore(base)

            self.assertFalse((outside / ".gitignore").exists())


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

    def test_auto_commit_bypasses_repo_hooks(self):
        from tools.workflow_cli.workspace import commit_requirement_dir, ensure_workspace_gitignore
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            _init_repo(base)
            hook = base / ".git" / "hooks" / "pre-commit"
            hook.write_text(
                "#!/bin/sh\nprintf hook-ran > unrelated.txt\nexit 1\n",
                encoding="utf-8",
            )
            hook.chmod(0o755)
            ensure_workspace_gitignore(base)
            run_dir = base / ".req-to-plan" / "WF-20260101-demo"
            run_dir.mkdir(parents=True)
            (run_dir / "run.md").write_text("# run\n", encoding="utf-8")

            commit_requirement_dir(base, "WF-20260101-demo", "chore(r2p): plan x")

            tracked = _git(base, "ls-files", ".req-to-plan/WF-20260101-demo").stdout
            self.assertIn("WF-20260101-demo/run.md", tracked)
            self.assertFalse((base / "unrelated.txt").exists())

    def test_auto_commit_bypasses_post_commit_hook(self):
        from tools.workflow_cli.workspace import commit_requirement_dir, ensure_workspace_gitignore
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            _init_repo(base)
            hook = base / ".git" / "hooks" / "post-commit"
            hook.write_text(
                "#!/bin/sh\nprintf hook-ran > unrelated.txt\n",
                encoding="utf-8",
            )
            hook.chmod(0o755)
            ensure_workspace_gitignore(base)
            run_dir = base / ".req-to-plan" / "WF-20260101-demo"
            run_dir.mkdir(parents=True)
            (run_dir / "run.md").write_text("# run\n", encoding="utf-8")

            commit_requirement_dir(base, "WF-20260101-demo", "chore(r2p): plan x")

            tracked = _git(base, "ls-files", ".req-to-plan/WF-20260101-demo").stdout
            self.assertIn("WF-20260101-demo/run.md", tracked)
            self.assertFalse((base / "unrelated.txt").exists())

    def test_path_scoped_commit_does_not_stage_recovery_logs(self):
        from tools.workflow_cli.workspace import commit_requirement_dir, ensure_workspace_gitignore
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            _init_repo(base)
            work_id = "WF-20260625-compact-test"
            run_dir = base / ".req-to-plan" / work_id
            (run_dir / "logs").mkdir(parents=True)
            (run_dir / "logs" / "status-run-approved-checkpoints.txt").write_text(
                "full list\n",
                encoding="utf-8",
            )

            ensure_workspace_gitignore(base)
            commit_requirement_dir(base, work_id, "chore(r2p): plan compact test")

            staged_or_tracked = _git(base, "ls-files", ".req-to-plan").stdout
            self.assertNotIn(
                f".req-to-plan/{work_id}/logs/status-run-approved-checkpoints.txt",
                staged_or_tracked,
            )

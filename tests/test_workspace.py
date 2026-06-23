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

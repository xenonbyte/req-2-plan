"""Tests for tools.workflow_cli.repo_baseline — TDD, written before implementation."""

from __future__ import annotations

import dataclasses
import tempfile
import unittest
from pathlib import Path

from tools.workflow_cli.repo_baseline import RepoBaseline, scan_repo_baseline


# ---------------------------------------------------------------------------
# Dataclass shape
# ---------------------------------------------------------------------------


class TestRepoBaselineDataclass(unittest.TestCase):
    def test_repo_baseline_is_dataclass(self):
        self.assertTrue(dataclasses.is_dataclass(RepoBaseline))

    def test_repo_baseline_fields(self):
        required_fields = {
            "loc",
            "module_count",
            "is_monorepo",
            "language_breakdown",
            "submodule_count",
            "cross_language_refs",
        }
        actual_fields = {f.name for f in dataclasses.fields(RepoBaseline)}
        self.assertTrue(required_fields.issubset(actual_fields))

    def test_repo_baseline_default_construction(self):
        rb = RepoBaseline()
        self.assertEqual(rb.loc, 0)
        self.assertEqual(rb.module_count, 0)
        self.assertFalse(rb.is_monorepo)
        self.assertEqual(rb.language_breakdown, {})
        self.assertEqual(rb.submodule_count, 0)
        self.assertEqual(rb.cross_language_refs, [])


# ---------------------------------------------------------------------------
# scan_repo_baseline — returns RepoBaseline
# ---------------------------------------------------------------------------


class TestScanRepoBaseline(unittest.TestCase):
    def test_scan_returns_repo_baseline_instance(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = scan_repo_baseline(Path(tmp))
        self.assertIsInstance(result, RepoBaseline)

    # ---------------------------------------------------------------------------
    # Empty directory
    # ---------------------------------------------------------------------------

    def test_empty_dir_has_zero_loc(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = scan_repo_baseline(Path(tmp))
        self.assertEqual(result.loc, 0)

    def test_empty_dir_has_zero_module_count(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = scan_repo_baseline(Path(tmp))
        self.assertEqual(result.module_count, 0)

    def test_empty_dir_is_not_monorepo(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = scan_repo_baseline(Path(tmp))
        self.assertFalse(result.is_monorepo)

    # ---------------------------------------------------------------------------
    # Python files → loc > 0
    # ---------------------------------------------------------------------------

    def test_python_files_give_nonzero_loc(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "main.py").write_text("def foo():\n    return 1\n\n# comment\n")
            (Path(tmp) / "utils.py").write_text("import os\n\ndef bar():\n    pass\n")
            result = scan_repo_baseline(Path(tmp))
        self.assertGreater(result.loc, 0)

    def test_python_files_counted_in_language_breakdown(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "main.py").write_text("x = 1\n")
            result = scan_repo_baseline(Path(tmp))
        self.assertIn("Python", result.language_breakdown)
        self.assertGreater(result.language_breakdown["Python"], 0)

    # ---------------------------------------------------------------------------
    # Multi-language directory
    # ---------------------------------------------------------------------------

    def test_multi_language_breakdown_has_both(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "app.py").write_text("print('hello')\n")
            (Path(tmp) / "index.ts").write_text("const x: number = 1;\n")
            result = scan_repo_baseline(Path(tmp))
        self.assertIn("Python", result.language_breakdown)
        self.assertIn("TypeScript", result.language_breakdown)

    # ---------------------------------------------------------------------------
    # Cross-language detection
    # ---------------------------------------------------------------------------

    def test_cross_language_refs_when_multiple_languages(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "app.py").write_text("x = 1\n")
            (Path(tmp) / "index.ts").write_text("const y = 1;\n")
            result = scan_repo_baseline(Path(tmp))
        self.assertGreaterEqual(len(result.cross_language_refs), 2)
        self.assertIn("Python", result.cross_language_refs)
        self.assertIn("TypeScript", result.cross_language_refs)

    def test_single_language_no_cross_language_refs(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "a.py").write_text("x = 1\n")
            (Path(tmp) / "b.py").write_text("y = 2\n")
            result = scan_repo_baseline(Path(tmp))
        self.assertLessEqual(len(result.cross_language_refs), 1)

    # ---------------------------------------------------------------------------
    # package.json + setup.py → cross-language signal
    # ---------------------------------------------------------------------------

    def test_package_json_and_setup_py_cross_language(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "package.json").write_text('{"name": "my-app"}\n')
            (Path(tmp) / "setup.py").write_text("from setuptools import setup\nsetup(name='my-app')\n")
            (Path(tmp) / "index.js").write_text("console.log('hi');\n")
            (Path(tmp) / "main.py").write_text("print('hi')\n")
            result = scan_repo_baseline(Path(tmp))
        self.assertIn("JavaScript", result.language_breakdown)
        self.assertIn("Python", result.language_breakdown)

    # ---------------------------------------------------------------------------
    # Monorepo detection
    # ---------------------------------------------------------------------------

    def test_multiple_package_json_is_monorepo(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "package.json").write_text('{"name": "root"}\n')
            pkg_a = root / "packages" / "a"
            pkg_a.mkdir(parents=True)
            (pkg_a / "package.json").write_text('{"name": "a"}\n')
            result = scan_repo_baseline(root)
        self.assertTrue(result.is_monorepo)

    def test_multiple_setup_py_is_monorepo(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "setup.py").write_text("from setuptools import setup\nsetup()\n")
            sub = root / "subpkg"
            sub.mkdir()
            (sub / "setup.py").write_text("from setuptools import setup\nsetup()\n")
            result = scan_repo_baseline(root)
        self.assertTrue(result.is_monorepo)

    def test_single_package_json_not_monorepo(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "package.json").write_text('{"name": "solo"}\n')
            result = scan_repo_baseline(Path(tmp))
        self.assertFalse(result.is_monorepo)

    # ---------------------------------------------------------------------------
    # Submodule detection
    # ---------------------------------------------------------------------------

    def test_submodule_count_zero_without_gitmodules(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = scan_repo_baseline(Path(tmp))
        self.assertEqual(result.submodule_count, 0)

    def test_submodule_count_from_gitmodules(self):
        gitmodules_content = (
            '[submodule "vendor/foo"]\n'
            '    path = vendor/foo\n'
            '    url = https://github.com/example/foo.git\n'
            '[submodule "vendor/bar"]\n'
            '    path = vendor/bar\n'
            '    url = https://github.com/example/bar.git\n'
        )
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / ".gitmodules").write_text(gitmodules_content)
            result = scan_repo_baseline(Path(tmp))
        self.assertEqual(result.submodule_count, 2)

    def test_submodule_count_single_entry(self):
        gitmodules_content = (
            '[submodule "lib/dep"]\n'
            '    path = lib/dep\n'
            '    url = https://github.com/example/dep.git\n'
        )
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / ".gitmodules").write_text(gitmodules_content)
            result = scan_repo_baseline(Path(tmp))
        self.assertEqual(result.submodule_count, 1)

    # ---------------------------------------------------------------------------
    # Skip dirs
    # ---------------------------------------------------------------------------

    def test_node_modules_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            nm = Path(tmp) / "node_modules"
            nm.mkdir()
            (nm / "something.js").write_text("// lots of vendor code\n" * 100)
            (Path(tmp) / "src.py").write_text("x = 1\n")
            result = scan_repo_baseline(Path(tmp))
        self.assertEqual(result.language_breakdown.get("JavaScript", 0), 0)
        self.assertGreater(result.language_breakdown.get("Python", 0), 0)

    def test_pycache_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp) / "__pycache__"
            cache.mkdir()
            (cache / "mod.cpython-310.pyc").write_bytes(b"\x00" * 50)
            result = scan_repo_baseline(Path(tmp))
        self.assertEqual(result.loc, 0)


if __name__ == "__main__":
    unittest.main()

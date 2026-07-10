import json
import os
import tempfile
import unittest
from pathlib import Path

try:
    import tomllib  # noqa: F401  # Python 3.11+
    _HAS_TOMLLIB = True
except ImportError:
    _HAS_TOMLLIB = False

_needs_tomllib = unittest.skipUnless(_HAS_TOMLLIB, "tomllib requires Python 3.11+")


class TestBuildContextPack(unittest.TestCase):
    def _make_repo(self, tmp: Path):
        (tmp / "package.json").write_text(
            json.dumps({
                "scripts": {"test": "jest"},
                "dependencies": {"react": "^18.0.0"},
                "devDependencies": {"jest": "^29.0.0"},
            }),
            encoding="utf-8",
        )
        (tmp / "requirements.txt").write_text("pyyaml>=6.0\n# comment\n", encoding="utf-8")
        (tmp / "src").mkdir()
        (tmp / "src" / "main.py").write_text("print('hi')\n", encoding="utf-8")

    def test_detects_managers_test_commands_and_deps(self):
        from tools.workflow_cli.context_pack import build_context_pack
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            self._make_repo(tmp)
            pack = build_context_pack(tmp)
        self.assertIn("npm", pack.package_managers)
        self.assertIn("pip", pack.package_managers)
        self.assertIn("npm test", pack.test_commands)
        self.assertNotIn("jest", pack.test_commands)
        names = {d["name"] for d in pack.dependencies}
        self.assertIn("react", names)
        self.assertTrue(any(d["name"].startswith("pyyaml") for d in pack.dependencies))

    def test_dev_dependencies_are_collected_with_dev_marker(self):
        from tools.workflow_cli.context_pack import build_context_pack
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            self._make_repo(tmp)
            pack = build_context_pack(tmp)
        jest = next(d for d in pack.dependencies if d["name"] == "jest")
        self.assertEqual(jest["ecosystem"], "npm")
        self.assertEqual(jest["version"], "^29.0.0")
        self.assertIs(jest["dev"], True)
        react = next(d for d in pack.dependencies if d["name"] == "react")
        self.assertNotIn("dev", react)  # existing entry shape unchanged

    def test_no_npm_test_script_yields_no_npm_test_command(self):
        from tools.workflow_cli.context_pack import build_context_pack
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            (tmp / "package.json").write_text(
                json.dumps({"dependencies": {"react": "^18.0.0"}}), encoding="utf-8")
            pack = build_context_pack(tmp)
        self.assertNotIn("npm test", pack.test_commands)
        self.assertIn("npm", pack.package_managers)

    def test_malformed_package_sections_do_not_block_pip_fallback(self):
        from tools.workflow_cli.context_pack import build_context_pack
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            (tmp / "package.json").write_text(
                json.dumps({
                    "scripts": "jest",
                    "dependencies": "react",
                    "devDependencies": "jest",
                }),
                encoding="utf-8",
            )
            (tmp / "requirements.txt").write_text("pyyaml>=6.0\n", encoding="utf-8")
            pack = build_context_pack(tmp)
        self.assertIn("pip", pack.package_managers)
        self.assertIn("python -m pytest", pack.test_commands)
        self.assertNotIn("npm test", pack.test_commands)
        self.assertTrue(any(d["name"].startswith("pyyaml") for d in pack.dependencies))

    def test_malformed_package_dependency_versions_do_not_block_context_pack(self):
        from tools.workflow_cli.context_pack import build_context_pack, write_context_pack
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            (tmp / "package.json").write_text(
                json.dumps({
                    "dependencies": {"react": "^18.0.0", "broken": 1},
                    "devDependencies": {"jest": "^29.0.0", "broken-dev": {"version": "1.0.0"}},
                }),
                encoding="utf-8",
            )
            run_dir = tmp / "run"
            run_dir.mkdir()
            pack = build_context_pack(tmp)
            md_path, json_path = write_context_pack(pack, run_dir)
            md_text = md_path.read_text(encoding="utf-8")
            data = json.loads(json_path.read_text(encoding="utf-8"))

        names = {d["name"] for d in pack.dependencies}
        self.assertIn("react", names)
        self.assertIn("jest", names)
        self.assertNotIn("broken", names)
        self.assertNotIn("broken-dev", names)
        self.assertIn("react ^18.0.0 (npm)", md_text)
        self.assertTrue(all(isinstance(d["version"], str) for d in data["dependencies"]))

    def test_top_level_non_object_package_json_does_not_block_pip_fallback(self):
        from tools.workflow_cli.context_pack import build_context_pack
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            (tmp / "package.json").write_text(json.dumps(["not", "a", "package"]), encoding="utf-8")
            (tmp / "requirements.txt").write_text("pyyaml>=6.0\n", encoding="utf-8")
            pack = build_context_pack(tmp)
        self.assertIn("pip", pack.package_managers)
        self.assertIn("python -m pytest", pack.test_commands)
        self.assertTrue(any(d["name"].startswith("pyyaml") for d in pack.dependencies))

    def test_finds_entrypoint_and_source_dir(self):
        from tools.workflow_cli.context_pack import build_context_pack
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            self._make_repo(tmp)
            pack = build_context_pack(tmp)
        self.assertTrue(any(e.endswith("main.py") for e in pack.entrypoints))
        self.assertIn("src", pack.source_dirs)

    def test_repo_root_is_absolute_when_repo_path_is_relative(self):
        from tools.workflow_cli.context_pack import build_context_pack
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            repo = tmp / "repo"
            repo.mkdir()
            self._make_repo(repo)
            cwd = Path.cwd()
            try:
                os.chdir(tmp)
                pack = build_context_pack(Path("repo"))
            finally:
                os.chdir(cwd)
        self.assertEqual(pack.repo_root, str(repo.resolve()))

    def test_symlinked_dependency_configs_are_not_read_or_recorded(self):
        from tools.workflow_cli.context_pack import build_context_pack
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            repo = root / "repo"
            outside = root / "outside"
            repo.mkdir()
            outside.mkdir()
            (outside / "requirements.txt").write_text(
                "LOCAL-SECRET-REQUIREMENT\n", encoding="utf-8"
            )
            (outside / "package.json").write_text(
                json.dumps({"dependencies": {"LOCAL-SECRET-NPM": "1"}}),
                encoding="utf-8",
            )
            (outside / "pyproject.toml").write_text(
                '[project]\ndependencies = ["LOCAL-SECRET-PYPROJECT"]\n',
                encoding="utf-8",
            )
            for name in ("requirements.txt", "package.json", "pyproject.toml"):
                (repo / name).symlink_to(outside / name)

            pack = build_context_pack(repo)

        serialized = json.dumps(pack.dependencies)
        self.assertNotIn("LOCAL-SECRET", serialized)
        self.assertNotIn("npm", pack.package_managers)
        self.assertNotIn("pip", pack.package_managers)
        self.assertTrue(
            {"requirements.txt", "package.json", "pyproject.toml"}.isdisjoint(
                pack.config_files
            )
        )


class TestPyprojectContextPack(unittest.TestCase):
    """PEP 621 [project] tables only; poetry-style private tables are out of scope."""

    def _build(self, tmp: Path, pyproject_text: str):
        from tools.workflow_cli.context_pack import build_context_pack
        (tmp / "pyproject.toml").write_text(pyproject_text, encoding="utf-8")
        return build_context_pack(tmp)

    @_needs_tomllib
    def test_collects_project_dependencies(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            pack = self._build(Path(tmpdir), (
                '[project]\nname = "demo"\n'
                'dependencies = ["pyyaml>=6.0", "requests"]\n'
            ))
        names = {d["name"] for d in pack.dependencies}
        self.assertIn("pyyaml>=6.0", names)
        self.assertIn("requests", names)
        self.assertTrue(all(
            d["ecosystem"] == "pip" and d["version"] == ""
            for d in pack.dependencies
        ))
        self.assertIn("pip", pack.package_managers)

    @_needs_tomllib
    def test_optional_dependencies_are_marked_dev(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            pack = self._build(Path(tmpdir), (
                '[project]\nname = "demo"\n'
                'dependencies = ["requests"]\n'
                '[project.optional-dependencies]\n'
                'dev = ["ruff"]\ntest = ["coverage"]\n'
            ))
        by_name = {d["name"]: d for d in pack.dependencies}
        self.assertNotIn("dev", by_name["requests"])
        self.assertIs(by_name["ruff"]["dev"], True)
        self.assertIs(by_name["coverage"]["dev"], True)

    @_needs_tomllib
    def test_pytest_config_or_dependency_yields_pytest_command(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            pack = self._build(Path(tmpdir), (
                '[project]\nname = "demo"\n'
                '[tool.pytest.ini_options]\ntestpaths = ["tests"]\n'
            ))
        self.assertIn("python -m pytest", pack.test_commands)
        with tempfile.TemporaryDirectory() as tmpdir:
            pack = self._build(Path(tmpdir), (
                '[project]\nname = "demo"\n'
                '[project.optional-dependencies]\ndev = ["pytest-cov"]\n'
            ))
        self.assertIn("python -m pytest", pack.test_commands)

    def test_pytest_command_not_duplicated_with_requirements_txt(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            (tmp / "requirements.txt").write_text("pyyaml>=6.0\n", encoding="utf-8")
            pack = self._build(tmp, (
                '[project]\nname = "demo"\n'
                '[tool.pytest.ini_options]\ntestpaths = ["tests"]\n'
            ))
        self.assertEqual(pack.test_commands.count("python -m pytest"), 1)
        self.assertEqual(pack.package_managers.count("pip"), 1)

    def test_poetry_style_pyproject_adds_nothing(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            pack = self._build(Path(tmpdir), (
                '[tool.poetry]\nname = "demo"\n'
                '[tool.poetry.dependencies]\nrequests = "^2.0"\n'
            ))
        self.assertEqual(pack.dependencies, [])
        self.assertNotIn("pip", pack.package_managers)
        self.assertNotIn("python -m pytest", pack.test_commands)

    def test_malformed_pyproject_does_not_block_context_pack(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            (tmp / "requirements.txt").write_text("pyyaml>=6.0\n", encoding="utf-8")
            pack = self._build(tmp, "[project\nbroken = ")
        self.assertIn("pip", pack.package_managers)
        self.assertTrue(any(d["name"].startswith("pyyaml") for d in pack.dependencies))

    @_needs_tomllib
    def test_non_string_dependency_entries_are_skipped(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            pack = self._build(Path(tmpdir), (
                '[project]\nname = "demo"\n'
                'dependencies = ["requests", 1]\n'
                '[project.optional-dependencies]\ndev = ["ruff", false]\n'
            ))
        names = {d["name"] for d in pack.dependencies}
        self.assertEqual(names, {"requests", "ruff"})

    def test_missing_tomllib_skips_pyproject_parsing(self):
        """Python < 3.11 has no tomllib: pyproject parsing degrades to a no-op."""
        from unittest import mock
        from tools.workflow_cli import context_pack
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            (tmp / "pyproject.toml").write_text(
                '[project]\nname = "demo"\ndependencies = ["requests"]\n',
                encoding="utf-8",
            )
            with mock.patch.object(context_pack, "tomllib", None):
                pack = context_pack.build_context_pack(tmp)
        self.assertEqual(pack.dependencies, [])
        self.assertNotIn("pip", pack.package_managers)


class TestContextPackMarkdown(unittest.TestCase):
    def _pack(self, dependencies):
        from tools.workflow_cli.context_pack import ProjectContextPack
        return ProjectContextPack(repo_root="/repo", dependencies=dependencies)

    def test_markdown_lists_dependency_details(self):
        from tools.workflow_cli.context_pack import to_markdown
        md = to_markdown(self._pack([
            {"name": "react", "version": "^18.0.0", "ecosystem": "npm"},
            {"name": "jest", "version": "^29.0.0", "ecosystem": "npm", "dev": True},
            {"name": "pyyaml>=6.0", "version": "", "ecosystem": "pip"},
        ]))
        self.assertIn("react ^18.0.0 (npm)", md)
        self.assertIn("jest ^29.0.0 (npm, dev)", md)
        self.assertIn("pyyaml>=6.0 (pip)", md)
        self.assertIn("dependencies (3)", md)

    def test_markdown_caps_dependency_list_at_20(self):
        from tools.workflow_cli.context_pack import to_markdown
        deps = [{"name": f"pkg{i:02d}", "version": "1.0.0", "ecosystem": "npm"}
                for i in range(25)]
        md = to_markdown(self._pack(deps))
        self.assertIn("dependencies (25)", md)
        self.assertIn("pkg19 1.0.0 (npm)", md)
        self.assertNotIn("pkg20", md)
        self.assertIn("… and 5 more", md)

    def test_markdown_without_dependencies_says_none(self):
        from tools.workflow_cli.context_pack import to_markdown
        md = to_markdown(self._pack([]))
        self.assertIn("dependencies (0): none", md)


class TestContextPackWriters(unittest.TestCase):
    def test_write_produces_both_files_and_valid_json(self):
        from tools.workflow_cli.context_pack import build_context_pack, write_context_pack
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            (tmp / "requirements.txt").write_text("pyyaml>=6.0\n", encoding="utf-8")
            run_dir = tmp / "run"
            run_dir.mkdir()
            pack = build_context_pack(tmp)
            md_path, json_path = write_context_pack(pack, run_dir)
            self.assertTrue(md_path.exists())
            self.assertTrue(json_path.exists())
            data = json.loads(json_path.read_text(encoding="utf-8"))
            self.assertEqual(data["repo_root"], str(tmp.resolve()))
            self.assertIn("dependencies", data)

    def test_symlink_at_json_path_raises_and_does_not_write_through(self):
        from tools.workflow_cli.context_pack import ProjectContextPack, write_context_pack
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            run_dir = tmp / "run"
            run_dir.mkdir()
            json_path = run_dir / "02-project-context.json"
            target_file = tmp / "target.json"
            target_file.write_text("{}", encoding="utf-8")
            json_path.symlink_to(target_file)

            pack = ProjectContextPack(repo_root="/repo")
            with self.assertRaises(ValueError) as cm:
                write_context_pack(pack, run_dir)
            self.assertIn("symlink", str(cm.exception))

            # Verify that target file was not overwritten
            self.assertEqual(target_file.read_text(encoding="utf-8"), "{}")

    def test_symlink_at_md_path_raises_and_does_not_write_through(self):
        from tools.workflow_cli.context_pack import ProjectContextPack, write_context_pack
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            run_dir = tmp / "run"
            run_dir.mkdir()
            md_path = run_dir / "02-project-context.md"
            target_file = tmp / "target.md"
            target_file.write_text("# Target", encoding="utf-8")
            md_path.symlink_to(target_file)

            pack = ProjectContextPack(repo_root="/repo")
            with self.assertRaises(ValueError) as cm:
                write_context_pack(pack, run_dir)
            self.assertIn("symlink", str(cm.exception))

            # Verify that target file was not overwritten
            self.assertEqual(target_file.read_text(encoding="utf-8"), "# Target")

    def test_normal_build_writes_both_files_with_atomic_write(self):
        from tools.workflow_cli.context_pack import ProjectContextPack, write_context_pack
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            run_dir = tmp / "run"
            run_dir.mkdir()

            pack = ProjectContextPack(
                repo_root="/test/repo",
                languages={"Python": 100},
                dependencies=[{"name": "pyyaml", "version": ">=6.0", "ecosystem": "pip"}]
            )
            md_path, json_path = write_context_pack(pack, run_dir)

            # Verify both files exist
            self.assertTrue(json_path.exists())
            self.assertTrue(md_path.exists())

            # Verify they are regular files (not symlinks)
            self.assertFalse(json_path.is_symlink())
            self.assertFalse(md_path.is_symlink())

            # Verify content
            json_data = json.loads(json_path.read_text(encoding="utf-8"))
            self.assertEqual(json_data["repo_root"], "/test/repo")
            self.assertIn("pyyaml", [d["name"] for d in json_data["dependencies"]])

            md_text = md_path.read_text(encoding="utf-8")
            self.assertIn("# Project Context Pack", md_text)
            self.assertIn("/test/repo", md_text)

            # Verify return values
            self.assertEqual(md_path, run_dir / "02-project-context.md")
            self.assertEqual(json_path, run_dir / "02-project-context.json")

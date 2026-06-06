import json
import os
import tempfile
import unittest
from pathlib import Path


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

import json
import tempfile
import unittest
from pathlib import Path


class TestBuildContextPack(unittest.TestCase):
    def _make_repo(self, tmp: Path):
        (tmp / "package.json").write_text(
            json.dumps({"scripts": {"test": "jest"}, "dependencies": {"react": "^18.0.0"}}),
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
        self.assertIn("jest", pack.test_commands)
        names = {d["name"] for d in pack.dependencies}
        self.assertIn("react", names)
        self.assertTrue(any(d["name"].startswith("pyyaml") for d in pack.dependencies))

    def test_finds_entrypoint_and_source_dir(self):
        from tools.workflow_cli.context_pack import build_context_pack
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            self._make_repo(tmp)
            pack = build_context_pack(tmp)
        self.assertTrue(any(e.endswith("main.py") for e in pack.entrypoints))
        self.assertIn("src", pack.source_dirs)


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
            self.assertEqual(data["repo_root"], str(tmp))
            self.assertIn("dependencies", data)

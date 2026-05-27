"""
Tests for artifact lifecycle manager.
"""
import unittest
import tempfile
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from tools.workflow_cli.models import Stage, WorkId, STAGE_ARTIFACT_MAP
from tools.workflow_cli.artifact import (
    ArtifactManager, write_artifact, read_artifact, artifact_path,
    artifact_exists, get_artifact_version, get_artifact_status
)


class TestArtifactPath(unittest.TestCase):
    def test_artifact_path_returns_correct_path(self):
        run_dir = Path("/tmp/some-run")
        path = artifact_path(run_dir, Stage.REQUIREMENT_BRIEF)
        self.assertEqual(path, run_dir / "03-requirement-brief.md")

    def test_artifact_path_all_stages(self):
        run_dir = Path("/tmp/some-run")
        for stage, filename in STAGE_ARTIFACT_MAP.items():
            self.assertEqual(artifact_path(run_dir, stage), run_dir / filename)


class TestArtifactExists(unittest.TestCase):
    def test_artifact_exists_false_when_missing(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir)
            self.assertFalse(artifact_exists(run_dir, Stage.REQUIREMENT_BRIEF))

    def test_artifact_exists_true_after_write(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir)
            write_artifact(run_dir, Stage.REQUIREMENT_BRIEF, "hello")
            self.assertTrue(artifact_exists(run_dir, Stage.REQUIREMENT_BRIEF))


class TestWriteArtifact(unittest.TestCase):
    def test_write_artifact_creates_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir)
            path = write_artifact(run_dir, Stage.REQUIREMENT_BRIEF, "# My Brief")
            self.assertTrue(path.exists())

    def test_write_artifact_returns_correct_path(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir)
            path = write_artifact(run_dir, Stage.REQUIREMENT_BRIEF, "content")
            self.assertEqual(path, run_dir / "03-requirement-brief.md")

    def test_write_artifact_includes_frontmatter(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir)
            write_artifact(run_dir, Stage.REQUIREMENT_BRIEF, "content")
            raw = (run_dir / "03-requirement-brief.md").read_text()
            self.assertIn("---", raw)
            self.assertIn("r2p_stage:", raw)
            self.assertIn("r2p_version:", raw)
            self.assertIn("r2p_status:", raw)

    def test_write_artifact_default_version_1(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir)
            write_artifact(run_dir, Stage.REQUIREMENT_BRIEF, "content")
            raw = (run_dir / "03-requirement-brief.md").read_text()
            self.assertIn("r2p_version: 1", raw)

    def test_write_artifact_version_2(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir)
            write_artifact(run_dir, Stage.REQUIREMENT_BRIEF, "content", version=2)
            raw = (run_dir / "03-requirement-brief.md").read_text()
            self.assertIn("r2p_version: 2", raw)

    def test_write_artifact_default_status_draft(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir)
            write_artifact(run_dir, Stage.REQUIREMENT_BRIEF, "content")
            raw = (run_dir / "03-requirement-brief.md").read_text()
            self.assertIn("r2p_status: draft", raw)

    def test_write_artifact_creates_run_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir) / "nested" / "run-dir"
            write_artifact(run_dir, Stage.REQUIREMENT_BRIEF, "content")
            self.assertTrue(run_dir.exists())

    def test_write_artifact_stage_value_in_frontmatter(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir)
            write_artifact(run_dir, Stage.REQUIREMENT_BRIEF, "content")
            raw = (run_dir / "03-requirement-brief.md").read_text()
            self.assertIn("r2p_stage: requirement_brief", raw)


class TestReadArtifact(unittest.TestCase):
    def test_read_artifact_returns_content_without_frontmatter(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir)
            write_artifact(run_dir, Stage.REQUIREMENT_BRIEF, "# My Brief\n\nDetails here.")
            content = read_artifact(run_dir, Stage.REQUIREMENT_BRIEF)
            self.assertEqual(content, "# My Brief\n\nDetails here.")

    def test_read_artifact_raises_when_missing(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir)
            with self.assertRaises(FileNotFoundError):
                read_artifact(run_dir, Stage.REQUIREMENT_BRIEF)

    def test_roundtrip_write_read(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir)
            original = "# Requirement\n\nThis is the requirement.\n\nMore details."
            write_artifact(run_dir, Stage.REQUIREMENT_BRIEF, original)
            result = read_artifact(run_dir, Stage.REQUIREMENT_BRIEF)
            self.assertEqual(result, original)

    def test_roundtrip_empty_content(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir)
            write_artifact(run_dir, Stage.REQUIREMENT_BRIEF, "")
            result = read_artifact(run_dir, Stage.REQUIREMENT_BRIEF)
            self.assertEqual(result, "")


class TestGetArtifactVersion(unittest.TestCase):
    def test_get_version_returns_0_when_missing(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir)
            self.assertEqual(get_artifact_version(run_dir, Stage.REQUIREMENT_BRIEF), 0)

    def test_get_version_returns_1_after_first_write(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir)
            write_artifact(run_dir, Stage.REQUIREMENT_BRIEF, "content", version=1)
            self.assertEqual(get_artifact_version(run_dir, Stage.REQUIREMENT_BRIEF), 1)

    def test_get_version_returns_2_after_version_2_write(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir)
            write_artifact(run_dir, Stage.REQUIREMENT_BRIEF, "content", version=2)
            self.assertEqual(get_artifact_version(run_dir, Stage.REQUIREMENT_BRIEF), 2)


class TestArtifactManagerStageProduce(unittest.TestCase):
    def test_stage_produce_creates_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir)
            manager = ArtifactManager(run_dir)
            manager.stage_produce(Stage.REQUIREMENT_BRIEF, "# Brief")
            self.assertTrue(artifact_exists(run_dir, Stage.REQUIREMENT_BRIEF))

    def test_stage_produce_writes_version_1(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir)
            manager = ArtifactManager(run_dir)
            manager.stage_produce(Stage.REQUIREMENT_BRIEF, "content")
            self.assertEqual(get_artifact_version(run_dir, Stage.REQUIREMENT_BRIEF), 1)

    def test_stage_produce_writes_status_draft(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir)
            manager = ArtifactManager(run_dir)
            manager.stage_produce(Stage.REQUIREMENT_BRIEF, "content")
            raw = (run_dir / "03-requirement-brief.md").read_text()
            self.assertIn("r2p_status: draft", raw)


class TestArtifactManagerStageUpdate(unittest.TestCase):
    def test_stage_update_increments_version(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir)
            manager = ArtifactManager(run_dir)
            manager.stage_produce(Stage.REQUIREMENT_BRIEF, "v1 content")
            manager.stage_update(Stage.REQUIREMENT_BRIEF, "v2 content")
            self.assertEqual(get_artifact_version(run_dir, Stage.REQUIREMENT_BRIEF), 2)

    def test_stage_update_again_increments_further(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir)
            manager = ArtifactManager(run_dir)
            manager.stage_produce(Stage.REQUIREMENT_BRIEF, "v1 content")
            manager.stage_update(Stage.REQUIREMENT_BRIEF, "v2 content")
            manager.stage_update(Stage.REQUIREMENT_BRIEF, "v3 content")
            self.assertEqual(get_artifact_version(run_dir, Stage.REQUIREMENT_BRIEF), 3)

    def test_stage_update_preserves_new_content(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir)
            manager = ArtifactManager(run_dir)
            manager.stage_produce(Stage.REQUIREMENT_BRIEF, "v1 content")
            manager.stage_update(Stage.REQUIREMENT_BRIEF, "v2 content")
            self.assertEqual(read_artifact(run_dir, Stage.REQUIREMENT_BRIEF), "v2 content")


class TestArtifactManagerStageReady(unittest.TestCase):
    def test_stage_ready_updates_status_to_ready(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir)
            manager = ArtifactManager(run_dir)
            manager.stage_produce(Stage.REQUIREMENT_BRIEF, "content")
            manager.stage_ready(Stage.REQUIREMENT_BRIEF)
            raw = (run_dir / "03-requirement-brief.md").read_text()
            self.assertIn("r2p_status: ready", raw)
            self.assertNotIn("r2p_status: draft", raw)

    def test_stage_ready_preserves_content(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir)
            manager = ArtifactManager(run_dir)
            manager.stage_produce(Stage.REQUIREMENT_BRIEF, "important content")
            manager.stage_ready(Stage.REQUIREMENT_BRIEF)
            self.assertEqual(read_artifact(run_dir, Stage.REQUIREMENT_BRIEF), "important content")

    def test_stage_ready_raises_when_artifact_missing(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir)
            manager = ArtifactManager(run_dir)
            with self.assertRaises(FileNotFoundError):
                manager.stage_ready(Stage.REQUIREMENT_BRIEF)


class TestArtifactManagerMarkStale(unittest.TestCase):
    def test_mark_stale_updates_status_to_stale(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir)
            manager = ArtifactManager(run_dir)
            manager.stage_produce(Stage.REQUIREMENT_BRIEF, "content")
            manager.mark_stale(Stage.REQUIREMENT_BRIEF, "upstream changed", "05-design.md")
            raw = (run_dir / "03-requirement-brief.md").read_text()
            self.assertIn("r2p_status: stale", raw)

    def test_mark_stale_preserves_content(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir)
            manager = ArtifactManager(run_dir)
            manager.stage_produce(Stage.REQUIREMENT_BRIEF, "stale content")
            manager.mark_stale(Stage.REQUIREMENT_BRIEF, "upstream changed", "05-design.md")
            self.assertEqual(read_artifact(run_dir, Stage.REQUIREMENT_BRIEF), "stale content")

    def test_mark_stale_raises_when_artifact_missing(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir)
            manager = ArtifactManager(run_dir)
            with self.assertRaises(FileNotFoundError):
                manager.mark_stale(Stage.REQUIREMENT_BRIEF, "reason", "replaced_by")


class TestArtifactManagerStageProduceGuards(unittest.TestCase):
    def test_stage_produce_raises_if_already_updated(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            am = ArtifactManager(run_dir)
            am.stage_produce(Stage.RAW_REQUIREMENT, "v1 content")
            am.stage_update(Stage.RAW_REQUIREMENT, "v2 content")
            with self.assertRaises(FileExistsError):
                am.stage_produce(Stage.RAW_REQUIREMENT, "reset attempt")

    def test_stage_produce_raises_if_ready(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            am = ArtifactManager(run_dir)
            am.stage_produce(Stage.RAW_REQUIREMENT, "v1 content")
            am.stage_ready(Stage.RAW_REQUIREMENT)
            with self.assertRaises(FileExistsError):
                am.stage_produce(Stage.RAW_REQUIREMENT, "reset attempt")

    def test_stage_produce_allowed_on_v1_draft(self):
        # Producing over an existing v1 draft is allowed (e.g., after run-start)
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            am = ArtifactManager(run_dir)
            am.stage_produce(Stage.RAW_REQUIREMENT, "initial content")
            # second produce on v1 draft should succeed
            path = am.stage_produce(Stage.RAW_REQUIREMENT, "replaced content")
            self.assertIn("replaced content", path.read_text())


class TestMarkStaleWritesFrontmatter(unittest.TestCase):
    def test_mark_stale_writes_reason_to_frontmatter(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            am = ArtifactManager(run_dir)
            am.stage_produce(Stage.RAW_REQUIREMENT, "content")
            am.mark_stale(Stage.RAW_REQUIREMENT, "DESIGN v2 approved", "05-design.md@v2")
            text = artifact_path(run_dir, Stage.RAW_REQUIREMENT).read_text()
            self.assertIn("r2p_status: stale", text)
            self.assertIn("r2p_stale_reason: DESIGN v2 approved", text)
            self.assertIn("r2p_replaced_by: 05-design.md@v2", text)


class TestCreatedAtPreserved(unittest.TestCase):
    def test_created_at_preserved_across_updates(self):
        """created_at should not change when the file is updated."""
        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir)
            write_artifact(run_dir, Stage.REQUIREMENT_BRIEF, "v1")
            raw1 = (run_dir / "03-requirement-brief.md").read_text()
            created_line_1 = [l for l in raw1.splitlines() if "r2p_created_at" in l][0]

            write_artifact(run_dir, Stage.REQUIREMENT_BRIEF, "v2", version=2)
            raw2 = (run_dir / "03-requirement-brief.md").read_text()
            created_line_2 = [l for l in raw2.splitlines() if "r2p_created_at" in l][0]

            self.assertEqual(created_line_1, created_line_2)


if __name__ == "__main__":
    unittest.main()

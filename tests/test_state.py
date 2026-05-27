"""
Tests for tools.workflow_cli.state.
TDD: written before implementation.
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path


class TestCreateRunRecord(unittest.TestCase):
    def setUp(self):
        from tools.workflow_cli.state import create_run_record
        from tools.workflow_cli.models import RunStatus, Stage, WorkId
        self.create_run_record = create_run_record
        self.RunStatus = RunStatus
        self.Stage = Stage
        self.WorkId = WorkId

    def _work_id(self):
        return self.WorkId("WF-20260527-test-create-run")

    def test_status_is_active_stage_draft(self):
        record = self.create_run_record(self._work_id())
        self.assertEqual(record.status, self.RunStatus.ACTIVE_STAGE_DRAFT)

    def test_current_stage_is_raw_requirement(self):
        record = self.create_run_record(self._work_id())
        self.assertEqual(record.current_stage, self.Stage.RAW_REQUIREMENT)

    def test_r2p_version_is_v1(self):
        record = self.create_run_record(self._work_id())
        self.assertEqual(record.r2p_version, "v1")

    def test_work_id_preserved(self):
        wid = self._work_id()
        record = self.create_run_record(wid)
        self.assertEqual(record.work_id, wid)

    def test_resume_context_last_completed_operation(self):
        record = self.create_run_record(self._work_id())
        self.assertEqual(
            record.resume_context.last_completed_operation, "start_workflow_run"
        )

    def test_resume_context_next_allowed_operation(self):
        record = self.create_run_record(self._work_id())
        self.assertEqual(
            record.resume_context.next_allowed_operation, "produce_stage_artifact"
        )

    def test_resume_context_active_item(self):
        record = self.create_run_record(self._work_id())
        self.assertEqual(record.resume_context.active_item, "raw_requirement")

    def test_approved_checkpoints_empty(self):
        record = self.create_run_record(self._work_id())
        self.assertEqual(record.approved_checkpoints, [])

    def test_active_artifacts_empty(self):
        record = self.create_run_record(self._work_id())
        self.assertEqual(record.active_artifacts, [])


class TestUpdateRunStatus(unittest.TestCase):
    def setUp(self):
        from tools.workflow_cli.state import create_run_record, update_run_status
        from tools.workflow_cli.models import RunStatus, WorkId
        self.create_run_record = create_run_record
        self.update_run_status = update_run_status
        self.RunStatus = RunStatus
        self.work_id = WorkId("WF-20260527-test-update-status")

    def test_valid_transition_returns_updated_record(self):
        record = self.create_run_record(self.work_id)
        # ACTIVE_STAGE_DRAFT -> QUALITY_GATE_FAILED is allowed
        updated = self.update_run_status(
            record, self.RunStatus.QUALITY_GATE_FAILED
        )
        self.assertEqual(updated.status, self.RunStatus.QUALITY_GATE_FAILED)

    def test_valid_transition_to_entry_gate_failed(self):
        record = self.create_run_record(self.work_id)
        updated = self.update_run_status(record, self.RunStatus.ENTRY_GATE_FAILED)
        self.assertEqual(updated.status, self.RunStatus.ENTRY_GATE_FAILED)

    def test_valid_transition_to_ready_for_checkpoint_review(self):
        record = self.create_run_record(self.work_id)
        updated = self.update_run_status(
            record, self.RunStatus.READY_FOR_CHECKPOINT_REVIEW
        )
        self.assertEqual(updated.status, self.RunStatus.READY_FOR_CHECKPOINT_REVIEW)

    def test_invalid_transition_raises_value_error(self):
        record = self.create_run_record(self.work_id)
        # ACTIVE_STAGE_DRAFT -> CLOSED_AT_PLAN_CHECKPOINT is not allowed
        with self.assertRaises(ValueError):
            self.update_run_status(record, self.RunStatus.CLOSED_AT_PLAN_CHECKPOINT)

    def test_invalid_transition_not_started_to_closed(self):
        from tools.workflow_cli.models import RunRecord
        record = RunRecord(work_id=self.work_id)
        with self.assertRaises(ValueError):
            self.update_run_status(record, self.RunStatus.CHECKPOINT_APPROVED)

    def test_same_status_transition_allowed(self):
        # ACTIVE_STAGE_DRAFT -> ACTIVE_STAGE_DRAFT is listed as allowed
        record = self.create_run_record(self.work_id)
        updated = self.update_run_status(record, self.RunStatus.ACTIVE_STAGE_DRAFT)
        self.assertEqual(updated.status, self.RunStatus.ACTIVE_STAGE_DRAFT)


class TestAddCheckpoint(unittest.TestCase):
    def setUp(self):
        from tools.workflow_cli.state import create_run_record, add_checkpoint
        from tools.workflow_cli.models import Stage, WorkId
        self.create_run_record = create_run_record
        self.add_checkpoint = add_checkpoint
        self.Stage = Stage
        self.work_id = WorkId("WF-20260527-test-checkpoint")

    def test_appends_checkpoint_record(self):
        record = self.create_run_record(self.work_id)
        updated = self.add_checkpoint(
            record,
            stage=self.Stage.RAW_REQUIREMENT,
            artifact="00-raw-requirement.md",
            version=1,
            downstream_authorization="all",
        )
        self.assertEqual(len(updated.approved_checkpoints), 1)

    def test_checkpoint_fields(self):
        record = self.create_run_record(self.work_id)
        updated = self.add_checkpoint(
            record,
            stage=self.Stage.REQUIREMENT_BRIEF,
            artifact="03-requirement-brief.md",
            version=2,
            downstream_authorization="design,spec,plan",
        )
        cp = updated.approved_checkpoints[0]
        self.assertEqual(cp.stage, self.Stage.REQUIREMENT_BRIEF)
        self.assertEqual(cp.artifact, "03-requirement-brief.md")
        self.assertEqual(cp.version, 2)
        self.assertEqual(cp.downstream_authorization, "design,spec,plan")

    def test_checkpoint_approved_at_set(self):
        record = self.create_run_record(self.work_id)
        updated = self.add_checkpoint(
            record,
            stage=self.Stage.RAW_REQUIREMENT,
            artifact="00-raw-requirement.md",
            version=1,
            downstream_authorization="all",
        )
        self.assertIsNotNone(updated.approved_checkpoints[0].approved_at)
        self.assertGreater(len(updated.approved_checkpoints[0].approved_at), 0)

    def test_multiple_checkpoints_accumulate(self):
        record = self.create_run_record(self.work_id)
        r1 = self.add_checkpoint(
            record,
            stage=self.Stage.RAW_REQUIREMENT,
            artifact="00-raw-requirement.md",
            version=1,
            downstream_authorization="all",
        )
        r2 = self.add_checkpoint(
            r1,
            stage=self.Stage.REQUIREMENT_BRIEF,
            artifact="03-requirement-brief.md",
            version=1,
            downstream_authorization="design",
        )
        self.assertEqual(len(r2.approved_checkpoints), 2)


class TestGetActiveArtifact(unittest.TestCase):
    def setUp(self):
        from tools.workflow_cli.state import (
            create_run_record, upsert_active_artifact, get_active_artifact
        )
        from tools.workflow_cli.models import Stage, WorkId
        self.create_run_record = create_run_record
        self.upsert_active_artifact = upsert_active_artifact
        self.get_active_artifact = get_active_artifact
        self.Stage = Stage
        self.work_id = WorkId("WF-20260527-test-get-artifact")

    def test_returns_none_when_no_artifacts(self):
        record = self.create_run_record(self.work_id)
        result = self.get_active_artifact(record, self.Stage.RAW_REQUIREMENT)
        self.assertIsNone(result)

    def test_returns_matching_artifact(self):
        record = self.create_run_record(self.work_id)
        updated = self.upsert_active_artifact(
            record,
            stage=self.Stage.RAW_REQUIREMENT,
            artifact="00-raw-requirement.md",
            version=1,
            status="draft",
        )
        result = self.get_active_artifact(updated, self.Stage.RAW_REQUIREMENT)
        self.assertIsNotNone(result)
        self.assertEqual(result.artifact, "00-raw-requirement.md")

    def test_returns_none_for_different_stage(self):
        record = self.create_run_record(self.work_id)
        updated = self.upsert_active_artifact(
            record,
            stage=self.Stage.RAW_REQUIREMENT,
            artifact="00-raw-requirement.md",
            version=1,
            status="draft",
        )
        result = self.get_active_artifact(updated, self.Stage.REQUIREMENT_BRIEF)
        self.assertIsNone(result)


class TestRecordStaleArtifact(unittest.TestCase):
    def setUp(self):
        from tools.workflow_cli.state import create_run_record, record_stale_artifact
        from tools.workflow_cli.models import WorkId
        self.create_run_record = create_run_record
        self.record_stale_artifact = record_stale_artifact
        self.work_id = WorkId("WF-20260527-test-stale-artifact")

    def test_appends_stale_artifact(self):
        record = self.create_run_record(self.work_id)
        updated = self.record_stale_artifact(
            record,
            artifact="00-raw-requirement.md",
            reason="upstream changed",
            replaced_by="00-raw-requirement-v2.md",
            required_action="reimport",
        )
        self.assertEqual(len(updated.stale_artifacts), 1)

    def test_stale_artifact_fields(self):
        record = self.create_run_record(self.work_id)
        updated = self.record_stale_artifact(
            record,
            artifact="03-requirement-brief.md",
            reason="spec conflict",
            replaced_by="03-requirement-brief-v2.md",
            required_action="re-review",
        )
        sa = updated.stale_artifacts[0]
        self.assertEqual(sa.artifact, "03-requirement-brief.md")
        self.assertEqual(sa.reason, "spec conflict")
        self.assertEqual(sa.replaced_by, "03-requirement-brief-v2.md")
        self.assertEqual(sa.required_action, "re-review")


class TestMarkdownRoundtrip(unittest.TestCase):
    def setUp(self):
        from tools.workflow_cli.state import (
            create_run_record,
            run_record_to_markdown,
            parse_run_record,
            add_checkpoint,
            upsert_active_artifact,
            record_stale_artifact,
        )
        from tools.workflow_cli.models import Stage, RunStatus, WorkId
        self.create_run_record = create_run_record
        self.run_record_to_markdown = run_record_to_markdown
        self.parse_run_record = parse_run_record
        self.add_checkpoint = add_checkpoint
        self.upsert_active_artifact = upsert_active_artifact
        self.record_stale_artifact = record_stale_artifact
        self.Stage = Stage
        self.RunStatus = RunStatus
        self.work_id = WorkId("WF-20260527-test-roundtrip")

    def test_basic_roundtrip_status(self):
        record = self.create_run_record(self.work_id)
        md = self.run_record_to_markdown(record)
        parsed = self.parse_run_record(md, self.work_id)
        self.assertEqual(parsed.status, record.status)

    def test_basic_roundtrip_stage(self):
        record = self.create_run_record(self.work_id)
        md = self.run_record_to_markdown(record)
        parsed = self.parse_run_record(md, self.work_id)
        self.assertEqual(parsed.current_stage, record.current_stage)

    def test_basic_roundtrip_r2p_version(self):
        record = self.create_run_record(self.work_id)
        md = self.run_record_to_markdown(record)
        parsed = self.parse_run_record(md, self.work_id)
        self.assertEqual(parsed.r2p_version, record.r2p_version)

    def test_roundtrip_with_checkpoint(self):
        record = self.create_run_record(self.work_id)
        record = self.add_checkpoint(
            record,
            stage=self.Stage.RAW_REQUIREMENT,
            artifact="00-raw-requirement.md",
            version=1,
            downstream_authorization="all",
        )
        md = self.run_record_to_markdown(record)
        parsed = self.parse_run_record(md, self.work_id)
        self.assertEqual(len(parsed.approved_checkpoints), 1)
        self.assertEqual(
            parsed.approved_checkpoints[0].stage, self.Stage.RAW_REQUIREMENT
        )
        self.assertEqual(parsed.approved_checkpoints[0].version, 1)

    def test_roundtrip_resume_context(self):
        record = self.create_run_record(self.work_id)
        md = self.run_record_to_markdown(record)
        parsed = self.parse_run_record(md, self.work_id)
        self.assertEqual(
            parsed.resume_context.last_completed_operation,
            record.resume_context.last_completed_operation,
        )
        self.assertEqual(
            parsed.resume_context.next_allowed_operation,
            record.resume_context.next_allowed_operation,
        )
        self.assertEqual(
            parsed.resume_context.active_item,
            record.resume_context.active_item,
        )

    def test_roundtrip_with_stale_artifact(self):
        record = self.create_run_record(self.work_id)
        record = self.record_stale_artifact(
            record,
            artifact="00-raw-requirement.md",
            reason="upstream changed",
            replaced_by="00-raw-requirement-v2.md",
            required_action="reimport",
        )
        md = self.run_record_to_markdown(record)
        parsed = self.parse_run_record(md, self.work_id)
        self.assertEqual(len(parsed.stale_artifacts), 1)
        self.assertEqual(parsed.stale_artifacts[0].reason, "upstream changed")

    def test_roundtrip_with_active_artifact(self):
        record = self.create_run_record(self.work_id)
        record = self.upsert_active_artifact(
            record,
            stage=self.Stage.RAW_REQUIREMENT,
            artifact="00-raw-requirement.md",
            version=1,
            status="draft",
        )
        md = self.run_record_to_markdown(record)
        parsed = self.parse_run_record(md, self.work_id)
        self.assertEqual(len(parsed.active_artifacts), 1)
        self.assertEqual(parsed.active_artifacts[0].status, "draft")

    def test_markdown_contains_work_id_header(self):
        record = self.create_run_record(self.work_id)
        md = self.run_record_to_markdown(record)
        self.assertIn(f"# Workflow Run: {self.work_id}", md)

    def test_markdown_contains_status_section(self):
        record = self.create_run_record(self.work_id)
        md = self.run_record_to_markdown(record)
        self.assertIn("## Status", md)
        self.assertIn("active_stage_draft", md)

    def test_markdown_contains_current_stage_section(self):
        record = self.create_run_record(self.work_id)
        md = self.run_record_to_markdown(record)
        self.assertIn("## Current Stage", md)
        self.assertIn("raw_requirement", md)

    def test_markdown_tier_lock_unlocked(self):
        record = self.create_run_record(self.work_id)
        md = self.run_record_to_markdown(record)
        self.assertIn("unlocked", md)

    def test_roundtrip_with_tier_estimate(self):
        from tools.workflow_cli.models import TierEstimate, TierBase, TierModifier
        record = self.create_run_record(self.work_id)
        record.tier_estimate = TierEstimate(
            base=TierBase.STANDARD,
            modifiers=frozenset({TierModifier.MIGRATION}),
        )
        md = self.run_record_to_markdown(record)
        parsed = self.parse_run_record(md, self.work_id)
        self.assertIsNotNone(parsed.tier_estimate)
        self.assertEqual(parsed.tier_estimate.base, TierBase.STANDARD)
        self.assertIn(TierModifier.MIGRATION, parsed.tier_estimate.modifiers)

    def test_roundtrip_with_reopen_lineage(self):
        record = self.create_run_record(self.work_id)
        record.reopen_lineage = "reopened_from: WF-20260527-test-roundtrip-r0@plan_checkpoint"
        md = self.run_record_to_markdown(record)
        parsed = self.parse_run_record(md, self.work_id)
        self.assertEqual(parsed.reopen_lineage, record.reopen_lineage)

    def test_empty_tables_present_in_markdown(self):
        record = self.create_run_record(self.work_id)
        md = self.run_record_to_markdown(record)
        self.assertIn("## Approved Checkpoints", md)
        self.assertIn("## Active Artifacts", md)
        self.assertIn("## Open Routes", md)

    def test_roundtrip_multiple_checkpoints(self):
        record = self.create_run_record(self.work_id)
        record = self.add_checkpoint(
            record,
            stage=self.Stage.RAW_REQUIREMENT,
            artifact="00-raw-requirement.md",
            version=1,
            downstream_authorization="all",
        )
        record = self.add_checkpoint(
            record,
            stage=self.Stage.REQUIREMENT_BRIEF,
            artifact="03-requirement-brief.md",
            version=2,
            downstream_authorization="design",
        )
        md = self.run_record_to_markdown(record)
        parsed = self.parse_run_record(md, self.work_id)
        self.assertEqual(len(parsed.approved_checkpoints), 2)
        stages = {cp.stage for cp in parsed.approved_checkpoints}
        self.assertIn(self.Stage.RAW_REQUIREMENT, stages)
        self.assertIn(self.Stage.REQUIREMENT_BRIEF, stages)


class TestRunStateManager(unittest.TestCase):
    def setUp(self):
        from tools.workflow_cli.state import RunStateManager, create_run_record
        from tools.workflow_cli.models import WorkId
        self.RunStateManager = RunStateManager
        self.create_run_record = create_run_record
        self.work_id = WorkId("WF-20260527-test-state-manager")

    def test_save_creates_run_md(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir) / "run"
            manager = self.RunStateManager(run_dir)
            record = self.create_run_record(self.work_id)
            manager.save(record)
            self.assertTrue((run_dir / "run.md").exists())

    def test_load_raises_file_not_found_when_missing(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir) / "nonexistent"
            manager = self.RunStateManager(run_dir)
            with self.assertRaises(FileNotFoundError):
                manager.load()

    def test_save_and_load_roundtrip_status(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir) / "run"
            manager = self.RunStateManager(run_dir)
            record = self.create_run_record(self.work_id)
            manager.save(record)
            loaded = manager.load()
            self.assertEqual(loaded.status, record.status)

    def test_save_and_load_roundtrip_work_id(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir) / "run"
            manager = self.RunStateManager(run_dir)
            record = self.create_run_record(self.work_id)
            manager.save(record)
            loaded = manager.load()
            self.assertEqual(loaded.work_id, self.work_id)

    def test_save_and_load_roundtrip_current_stage(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir) / "run"
            manager = self.RunStateManager(run_dir)
            record = self.create_run_record(self.work_id)
            manager.save(record)
            loaded = manager.load()
            self.assertEqual(loaded.current_stage, record.current_stage)

    def test_save_creates_parent_dirs(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir) / "deep" / "nested" / "run"
            manager = self.RunStateManager(run_dir)
            record = self.create_run_record(self.work_id)
            manager.save(record)
            self.assertTrue(run_dir.exists())

    def test_run_path_is_run_md(self):
        run_dir = Path("/tmp/test-run")
        manager = self.RunStateManager(run_dir)
        self.assertEqual(manager.run_path, run_dir / "run.md")


class TestParseRunRecord(unittest.TestCase):
    """Test parse_run_record directly with hand-crafted markdown."""

    def setUp(self):
        from tools.workflow_cli.state import parse_run_record
        from tools.workflow_cli.models import RunStatus, Stage, WorkId
        self.parse_run_record = parse_run_record
        self.RunStatus = RunStatus
        self.Stage = Stage
        self.WorkId = WorkId
        self.work_id = WorkId("WF-20260527-test-parse")

    def _minimal_md(self, status="active_stage_draft", stage="raw_requirement"):
        return f"""# Workflow Run: WF-20260527-test-parse

## Status
{status}

## Current Stage
{stage}

## r2p Version
v1

## Tier Lock
unlocked

## Tier Estimate
none

## Approved Checkpoints
| Stage | Artifact | Version | Approved At | Downstream Authorization | Bundle ID |
|---|---|---|---|---|---|

## Bundle Authorizations
| Bundle ID | Stages | Authorized At | Revoked At | Consumed Stages |
|---|---|---|---|---|

## Active Artifacts
| Stage | Artifact | Version | Status |
|---|---|---|---|

## Stale / Superseded Artifacts
| Artifact | Reason | Replaced By | Required Action |
|---|---|---|---|

## Open Routes
| Route ID | From Stage | Owner Stage | Required Action | Status |
|---|---|---|---|---|

## User Confirmations
| Confirmation | Stage | Source | Recorded In |
|---|---|---|---|

## Resume Context
| Field | Value |
|---|---|
| Last Completed Operation | start_workflow_run |
| Next Allowed Operation | produce_stage_artifact |
| Active Item | raw_requirement |
| Required Reread Targets | |
| Resume Reason | |

## Reopen Lineage
(none)
"""

    def test_parse_status(self):
        record = self.parse_run_record(self._minimal_md(), self.work_id)
        self.assertEqual(record.status, self.RunStatus.ACTIVE_STAGE_DRAFT)

    def test_parse_stage(self):
        record = self.parse_run_record(self._minimal_md(), self.work_id)
        self.assertEqual(record.current_stage, self.Stage.RAW_REQUIREMENT)

    def test_parse_different_status(self):
        record = self.parse_run_record(
            self._minimal_md(status="quality_gate_failed"), self.work_id
        )
        self.assertEqual(record.status, self.RunStatus.QUALITY_GATE_FAILED)

    def test_parse_different_stage(self):
        record = self.parse_run_record(
            self._minimal_md(stage="requirement_brief"), self.work_id
        )
        self.assertEqual(record.current_stage, self.Stage.REQUIREMENT_BRIEF)

    def test_parse_empty_checkpoints(self):
        record = self.parse_run_record(self._minimal_md(), self.work_id)
        self.assertEqual(record.approved_checkpoints, [])

    def test_parse_resume_context_fields(self):
        record = self.parse_run_record(self._minimal_md(), self.work_id)
        self.assertEqual(
            record.resume_context.last_completed_operation, "start_workflow_run"
        )
        self.assertEqual(
            record.resume_context.next_allowed_operation, "produce_stage_artifact"
        )
        self.assertEqual(record.resume_context.active_item, "raw_requirement")

    def test_parse_tier_lock_unlocked(self):
        record = self.parse_run_record(self._minimal_md(), self.work_id)
        self.assertIsNone(record.tier_locked)

    def test_parse_tier_estimate_none(self):
        record = self.parse_run_record(self._minimal_md(), self.work_id)
        self.assertIsNone(record.tier_estimate)

    def test_parse_reopen_lineage_none(self):
        record = self.parse_run_record(self._minimal_md(), self.work_id)
        self.assertIsNone(record.reopen_lineage)


class TestPipeEscaping(unittest.TestCase):
    def test_roundtrip_pipe_in_stale_reason(self):
        from tools.workflow_cli.state import (
            create_run_record, record_stale_artifact,
            run_record_to_markdown, parse_run_record,
        )
        from tools.workflow_cli.models import WorkId
        work_id = WorkId("WF-20260527-pipe")
        record = create_run_record(work_id)
        record = record_stale_artifact(record, "x.md", "reason | pipes", "y.md", "action | pipes")
        md = run_record_to_markdown(record)
        parsed = parse_run_record(md, work_id)
        self.assertEqual(parsed.stale_artifacts[0].reason, "reason | pipes")
        self.assertEqual(parsed.stale_artifacts[0].required_action, "action | pipes")

    def test_roundtrip_pipe_in_open_route(self):
        from tools.workflow_cli.state import (
            create_run_record, add_open_route,
            run_record_to_markdown, parse_run_record,
        )
        from tools.workflow_cli.models import WorkId, Stage
        work_id = WorkId("WF-20260527-pipe")
        record = create_run_record(work_id)
        record = add_open_route(record, "ROUTE-001", Stage.DESIGN, Stage.REQUIREMENT_BRIEF, "fix | this | issue")
        md = run_record_to_markdown(record)
        parsed = parse_run_record(md, work_id)
        self.assertEqual(parsed.open_routes[0].required_action, "fix | this | issue")

    def test_roundtrip_backslash_in_reason(self):
        from tools.workflow_cli.state import (
            create_run_record, record_stale_artifact,
            run_record_to_markdown, parse_run_record,
        )
        from tools.workflow_cli.models import WorkId
        work_id = WorkId("WF-20260527-pipe")
        record = create_run_record(work_id)
        record = record_stale_artifact(record, "x.md", "path\\\\to\\\\file", "y.md", "action")
        md = run_record_to_markdown(record)
        parsed = parse_run_record(md, work_id)
        self.assertIn("\\", parsed.stale_artifacts[0].reason)

    def test_roundtrip_pipe_in_resume_context(self):
        from tools.workflow_cli.state import (
            create_run_record, update_resume_context,
            run_record_to_markdown, parse_run_record,
        )
        from tools.workflow_cli.models import WorkId
        work_id = WorkId("WF-20260527-pipe")
        record = create_run_record(work_id)
        record = update_resume_context(record, next_operation="gate | check | required")
        md = run_record_to_markdown(record)
        parsed = parse_run_record(md, work_id)
        self.assertEqual(parsed.resume_context.next_allowed_operation, "gate | check | required")


if __name__ == "__main__":
    unittest.main()

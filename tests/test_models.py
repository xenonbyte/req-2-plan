"""
Comprehensive tests for tools.workflow_cli.models.
TDD: written before implementation.
"""
import unittest
from datetime import datetime


class TestStageConstants(unittest.TestCase):
    def setUp(self):
        from tools.workflow_cli.models import (
            Stage, STAGE_ORDER, NEXT_STAGE_MAP, STAGE_ARTIFACT_MAP,
        )
        self.Stage = Stage
        self.STAGE_ORDER = STAGE_ORDER
        self.NEXT_STAGE_MAP = NEXT_STAGE_MAP
        self.STAGE_ARTIFACT_MAP = STAGE_ARTIFACT_MAP

    def test_stage_order_length(self):
        self.assertEqual(len(self.STAGE_ORDER), 6)

    def test_stage_order_first_and_last(self):
        self.assertEqual(self.STAGE_ORDER[0], self.Stage.RAW_REQUIREMENT)
        self.assertEqual(self.STAGE_ORDER[-1], self.Stage.PLAN)

    def test_stage_order_excludes_closed(self):
        self.assertNotIn(self.Stage.CLOSED, self.STAGE_ORDER)

    def test_next_stage_map_covers_all_except_plan(self):
        expected_keys = set(self.STAGE_ORDER) - {self.Stage.PLAN}
        self.assertEqual(set(self.NEXT_STAGE_MAP.keys()), expected_keys)

    def test_stage_artifact_map_covers_all_6(self):
        self.assertEqual(set(self.STAGE_ARTIFACT_MAP.keys()), set(self.STAGE_ORDER))


class TestStageRequiredUpstreamCheckpoints(unittest.TestCase):
    def setUp(self):
        from tools.workflow_cli.models import (
            Stage, STAGE_REQUIRED_UPSTREAM_CHECKPOINTS, STAGE_ORDER,
        )
        self.Stage = Stage
        self.STAGE_REQUIRED_UPSTREAM_CHECKPOINTS = STAGE_REQUIRED_UPSTREAM_CHECKPOINTS
        self.STAGE_ORDER = STAGE_ORDER

    def test_raw_requirement_exists_and_maps_to_empty_list(self):
        self.assertIn(self.Stage.RAW_REQUIREMENT, self.STAGE_REQUIRED_UPSTREAM_CHECKPOINTS)
        self.assertEqual(self.STAGE_REQUIRED_UPSTREAM_CHECKPOINTS[self.Stage.RAW_REQUIREMENT], [])

    def test_requirement_brief_maps_to_empty_list(self):
        self.assertIn(self.Stage.REQUIREMENT_BRIEF, self.STAGE_REQUIRED_UPSTREAM_CHECKPOINTS)
        self.assertEqual(self.STAGE_REQUIRED_UPSTREAM_CHECKPOINTS[self.Stage.REQUIREMENT_BRIEF], [])

    def test_plan_has_all_4_upstream_stages(self):
        expected = [
            self.Stage.REQUIREMENT_BRIEF,
            self.Stage.RISK_DISCOVERY,
            self.Stage.DESIGN,
            self.Stage.SPEC,
        ]
        self.assertEqual(self.STAGE_REQUIRED_UPSTREAM_CHECKPOINTS[self.Stage.PLAN], expected)

    def test_all_stages_in_stage_order_are_keys(self):
        keys = set(self.STAGE_REQUIRED_UPSTREAM_CHECKPOINTS.keys())
        stage_order_set = set(self.STAGE_ORDER)
        self.assertEqual(keys, stage_order_set)


class TestRunStatusEnum(unittest.TestCase):
    def setUp(self):
        from tools.workflow_cli.models import RunStatus
        self.RunStatus = RunStatus

    def test_all_members_are_strings(self):
        for member in self.RunStatus:
            self.assertIsInstance(member, str)

    def test_members_exist(self):
        statuses = [
            "NOT_STARTED", "ACTIVE_STAGE_DRAFT", "ENTRY_GATE_FAILED",
            "QUALITY_GATE_FAILED", "READY_FOR_CHECKPOINT_REVIEW",
            "CHECKPOINT_REVIEW", "CHECKPOINT_CHANGES_REQUESTED",
            "UPSTREAM_GAP_ROUTING", "CHECKPOINT_APPROVED",
            "NEXT_STAGE", "CLOSED_AT_PLAN_CHECKPOINT",
        ]
        for name in statuses:
            self.assertIn(name, self.RunStatus.__members__)


class TestTransitions(unittest.TestCase):
    def setUp(self):
        from tools.workflow_cli.models import RunStatus, is_transition_allowed
        self.RunStatus = RunStatus
        self.is_transition_allowed = is_transition_allowed

    def test_not_started_to_active_stage_draft_allowed(self):
        self.assertTrue(
            self.is_transition_allowed(
                self.RunStatus.NOT_STARTED,
                self.RunStatus.ACTIVE_STAGE_DRAFT,
            )
        )

    def test_not_started_to_closed_at_plan_checkpoint_not_allowed(self):
        self.assertFalse(
            self.is_transition_allowed(
                self.RunStatus.NOT_STARTED,
                self.RunStatus.CLOSED_AT_PLAN_CHECKPOINT,
            )
        )

    def test_closed_at_plan_checkpoint_has_no_outgoing_transitions(self):
        from tools.workflow_cli.models import RunStatus
        for target in RunStatus:
            self.assertFalse(
                self.is_transition_allowed(
                    self.RunStatus.CLOSED_AT_PLAN_CHECKPOINT,
                    target,
                )
            )

    def test_checkpoint_approved_to_next_stage_allowed(self):
        self.assertTrue(
            self.is_transition_allowed(
                self.RunStatus.CHECKPOINT_APPROVED,
                self.RunStatus.NEXT_STAGE,
            )
        )


class TestCommandEligibility(unittest.TestCase):
    def setUp(self):
        from tools.workflow_cli.models import RunStatus, is_command_allowed
        self.RunStatus = RunStatus
        self.is_command_allowed = is_command_allowed

    def test_cmd_run_start_allowed_in_not_started(self):
        self.assertTrue(
            self.is_command_allowed(self.RunStatus.NOT_STARTED, "CMD-RUN-START")
        )

    def test_cmd_stage_produce_not_allowed_in_not_started(self):
        self.assertFalse(
            self.is_command_allowed(self.RunStatus.NOT_STARTED, "CMD-STAGE-PRODUCE")
        )

    def test_cmd_status_run_read_only_bypass_in_closed(self):
        self.assertTrue(
            self.is_command_allowed(
                self.RunStatus.CLOSED_AT_PLAN_CHECKPOINT, "CMD-STATUS-RUN"
            )
        )

    def test_cmd_tier_status_allowed_in_not_started(self):
        self.assertTrue(
            self.is_command_allowed(self.RunStatus.NOT_STARTED, "CMD-TIER-STATUS")
        )

    def test_cmd_run_reopen_allowed_in_closed_at_plan_checkpoint(self):
        self.assertTrue(
            self.is_command_allowed(
                self.RunStatus.CLOSED_AT_PLAN_CHECKPOINT, "CMD-RUN-REOPEN"
            )
        )

    def test_cmd_run_reopen_not_allowed_in_not_started(self):
        self.assertFalse(
            self.is_command_allowed(self.RunStatus.NOT_STARTED, "CMD-RUN-REOPEN")
        )


class TestWorkId(unittest.TestCase):
    def setUp(self):
        from tools.workflow_cli.models import WorkId
        self.WorkId = WorkId

    def test_valid_work_id(self):
        wid = self.WorkId("WF-20260527-test-slug")
        self.assertEqual(str(wid), "WF-20260527-test-slug")

    def test_invalid_prefix_raises(self):
        with self.assertRaises(ValueError):
            self.WorkId("XX-20260527-test-slug")

    def test_generate_ascii_requirement(self):
        wid = self.WorkId.generate("Add login rate limiting")
        today = datetime.now().strftime("%Y%m%d")
        self.assertTrue(str(wid).startswith(f"WF-{today}-"))
        self.assertIn("login", str(wid))
        self.assertIn("rate", str(wid))

    def test_generate_chinese_falls_back(self):
        wid = self.WorkId.generate("用户登录限流需求")
        today = datetime.now().strftime("%Y%m%d")
        self.assertTrue(str(wid).startswith(f"WF-{today}-run-"))

    def test_generate_blank_falls_back(self):
        wid = self.WorkId.generate("   ")
        today = datetime.now().strftime("%Y%m%d")
        self.assertTrue(str(wid).startswith(f"WF-{today}-run-"))

    def test_generate_ascii_requirement_slug_content(self):
        wid = self.WorkId.generate("Add login rate limiting")
        # Should produce WF-<date>-add-login-rate-limiting
        self.assertIn("add", str(wid))
        self.assertIn("limiting", str(wid))


class TestTierEnums(unittest.TestCase):
    def test_tier_base_has_light_and_standard_only(self):
        from tools.workflow_cli.models import TierBase
        self.assertEqual(set(TierBase.__members__), {"LIGHT", "STANDARD"})

    def test_tier_modifier_has_exactly_5_members(self):
        from tools.workflow_cli.models import TierModifier
        expected = {"MIGRATION", "CROSS_PROJECT", "SAFETY", "DEPENDENCY", "SCOPE_EXPANDING"}
        self.assertEqual(set(TierModifier.__members__), expected)


class TestTierEstimate(unittest.TestCase):
    def setUp(self):
        from tools.workflow_cli.models import TierEstimate, TierBase, TierModifier
        self.TierEstimate = TierEstimate
        self.TierBase = TierBase
        self.TierModifier = TierModifier

    def test_basic_construction(self):
        est = self.TierEstimate(base=self.TierBase.LIGHT, modifiers=frozenset())
        self.assertEqual(est.base, self.TierBase.LIGHT)
        self.assertEqual(est.modifiers, frozenset())

    def test_floor_returns_copy(self):
        est = self.TierEstimate(base=self.TierBase.LIGHT, modifiers=frozenset())
        f = est.floor()
        self.assertEqual(f.base, est.base)
        self.assertEqual(f.modifiers, est.modifiers)

    def test_is_above_floor_false_when_estimate_equals_floor(self):
        est = self.TierEstimate(base=self.TierBase.LIGHT, modifiers=frozenset())
        self.assertFalse(est.is_above_floor())

    def test_escalate_adds_modifier(self):
        est = self.TierEstimate(base=self.TierBase.LIGHT, modifiers=frozenset())
        escalated = est.escalate(self.TierModifier.MIGRATION)
        self.assertIn(self.TierModifier.MIGRATION, escalated.modifiers)

    def test_escalate_is_immutable(self):
        est = self.TierEstimate(base=self.TierBase.LIGHT, modifiers=frozenset())
        _ = est.escalate(self.TierModifier.MIGRATION)
        self.assertNotIn(self.TierModifier.MIGRATION, est.modifiers)

    def test_escalate_idempotent(self):
        est = self.TierEstimate(base=self.TierBase.LIGHT, modifiers=frozenset())
        r1 = est.escalate(self.TierModifier.MIGRATION)
        r2 = r1.escalate(self.TierModifier.MIGRATION)
        self.assertEqual(r1.modifiers, r2.modifiers)

    def test_escalate_scope_expanding_upgrades_base(self):
        est = self.TierEstimate(base=self.TierBase.LIGHT, modifiers=frozenset())
        escalated = est.escalate(self.TierModifier.SCOPE_EXPANDING)
        self.assertEqual(escalated.base, self.TierBase.STANDARD)

    def test_lock_valid(self):
        est = self.TierEstimate(base=self.TierBase.LIGHT, modifiers=frozenset())
        locked = est.lock(self.TierBase.STANDARD, frozenset())
        self.assertEqual(locked.base, self.TierBase.STANDARD)

    def test_lock_below_floor_raises(self):
        est = self.TierEstimate(base=self.TierBase.STANDARD, modifiers=frozenset())
        with self.assertRaises(ValueError):
            est.lock(self.TierBase.LIGHT, frozenset())

    def test_lock_missing_modifiers_raises(self):
        est = self.TierEstimate(
            base=self.TierBase.LIGHT,
            modifiers=frozenset({self.TierModifier.MIGRATION}),
        )
        with self.assertRaises(ValueError):
            est.lock(self.TierBase.LIGHT, frozenset())

    def test_lock_stricter_than_floor_is_above_floor(self):
        est = self.TierEstimate(base=self.TierBase.LIGHT, modifiers=frozenset())
        locked = est.lock(self.TierBase.STANDARD, frozenset())
        self.assertTrue(locked.is_above_floor())

    def test_lock_same_as_floor_not_above_floor(self):
        est = self.TierEstimate(base=self.TierBase.LIGHT, modifiers=frozenset())
        locked = est.lock(self.TierBase.LIGHT, frozenset())
        self.assertFalse(locked.is_above_floor())

    def test_is_above_floor_false_after_escalate_without_lock(self):
        # escalate returns a new estimate, but since _floor_base is not set (estimate IS floor),
        # is_above_floor() returns False
        estimate = self.TierEstimate(base=self.TierBase.LIGHT, modifiers=frozenset())
        escalated = estimate.escalate(self.TierModifier.MIGRATION)
        # escalated estimate has no floor context → is_above_floor is False
        self.assertFalse(escalated.is_above_floor())


class TestEvidenceBlock(unittest.TestCase):
    def setUp(self):
        from tools.workflow_cli.models import EvidenceBlock, TierEstimate, TierBase
        self.EvidenceBlock = EvidenceBlock
        self.TierEstimate = TierEstimate
        self.TierBase = TierBase

    def test_validate_for_lock_raises_when_missing_fields(self):
        eb = self.EvidenceBlock()
        with self.assertRaises(ValueError):
            eb.validate_for_lock()

    def test_validate_for_lock_passes_when_all_present(self):
        est = self.TierEstimate(base=self.TierBase.LIGHT, modifiers=frozenset())
        eb = self.EvidenceBlock(
            keywords_hit=["auth"],
            repo_baseline_summary="some summary",
            floor=est,
            confirm_status="pending",
        )
        # Should not raise
        eb.validate_for_lock()


class TestBundleAuthorization(unittest.TestCase):
    def setUp(self):
        from tools.workflow_cli.models import BundleAuthorization, Stage
        self.BundleAuthorization = BundleAuthorization
        self.Stage = Stage

    def _make_bundle(self, revoked_at=None, consumed=None):
        return self.BundleAuthorization(
            bundle_id="b1",
            stages=frozenset({self.Stage.REQUIREMENT_BRIEF, self.Stage.RISK_DISCOVERY}),
            authorized_at="2026-05-27T00:00:00Z",
            revoked_at=revoked_at,
            consumed_by_stage=consumed or {},
        )

    def test_is_live_when_not_revoked_and_not_all_consumed(self):
        bundle = self._make_bundle()
        self.assertTrue(bundle.is_live())

    def test_is_live_false_when_all_consumed(self):
        consumed = {
            self.Stage.REQUIREMENT_BRIEF.value: "2026-05-27T01:00:00Z",
            self.Stage.RISK_DISCOVERY.value: "2026-05-27T02:00:00Z",
        }
        bundle = self._make_bundle(consumed=consumed)
        self.assertFalse(bundle.is_live())

    def test_is_live_false_when_revoked(self):
        bundle = self._make_bundle(revoked_at="2026-05-27T03:00:00Z")
        self.assertFalse(bundle.is_live())

    def test_covers_returns_true_when_live_and_stage_in_bundle(self):
        bundle = self._make_bundle()
        self.assertTrue(bundle.covers(self.Stage.REQUIREMENT_BRIEF))

    def test_covers_returns_false_after_stage_consumed(self):
        consumed = {self.Stage.REQUIREMENT_BRIEF.value: "2026-05-27T01:00:00Z"}
        bundle = self._make_bundle(consumed=consumed)
        self.assertFalse(bundle.covers(self.Stage.REQUIREMENT_BRIEF))

    def test_covers_returns_false_when_revoked(self):
        bundle = self._make_bundle(revoked_at="2026-05-27T03:00:00Z")
        self.assertFalse(bundle.covers(self.Stage.REQUIREMENT_BRIEF))

    def test_covers_returns_false_for_stage_not_in_bundle(self):
        bundle = self._make_bundle()
        self.assertFalse(bundle.covers(self.Stage.DESIGN))


def test_run_resume_is_read_only():
    from tools.workflow_cli.models import READ_ONLY_COMMANDS
    assert "CMD-RUN-RESUME" in READ_ONLY_COMMANDS


def test_new_command_intents_allowed_states():
    from tools.workflow_cli.models import is_command_allowed, RunStatus
    assert is_command_allowed(RunStatus.READY_FOR_CHECKPOINT_REVIEW, "CMD-REVIEW-CHECKPOINT")
    assert is_command_allowed(RunStatus.CHECKPOINT_REVIEW, "CMD-CHECKPOINT-DECIDE")
    assert is_command_allowed(RunStatus.CHECKPOINT_APPROVED, "CMD-STAGE-ADVANCE")
    assert not is_command_allowed(RunStatus.ACTIVE_STAGE_DRAFT, "CMD-STAGE-ADVANCE")


if __name__ == "__main__":
    unittest.main()

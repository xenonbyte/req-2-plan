"""
Tests for tools.workflow_cli.gates.
TDD: written before implementation.
"""
import tempfile
import unittest
from pathlib import Path


class TestGateResultDefaults(unittest.TestCase):
    def setUp(self):
        from tools.workflow_cli.gates import GateResult
        self.GateResult = GateResult

    def test_gate_result_pass_has_exit_code_zero(self):
        result = self.GateResult(passed=True, issues=[])
        self.assertEqual(result.exit_code, 0)

    def test_gate_result_fail_can_carry_exit_code(self):
        result = self.GateResult(passed=False, issues=["oops"], exit_code=2)
        self.assertFalse(result.passed)
        self.assertEqual(result.exit_code, 2)

    def test_gate_result_issues_list(self):
        result = self.GateResult(passed=True, issues=["a", "b"])
        self.assertEqual(result.issues, ["a", "b"])


class TestEntryGate(unittest.TestCase):
    def setUp(self):
        from tools.workflow_cli.gates import check_entry_gate
        from tools.workflow_cli.models import (
            Stage, TierBase, TierModifier, TierEstimate,
            CheckpointRecord, BundleAuthorization,
            STAGE_ARTIFACT_MAP,
        )
        self.check_entry_gate = check_entry_gate
        self.Stage = Stage
        self.TierBase = TierBase
        self.TierModifier = TierModifier
        self.TierEstimate = TierEstimate
        self.CheckpointRecord = CheckpointRecord
        self.BundleAuthorization = BundleAuthorization
        self.STAGE_ARTIFACT_MAP = STAGE_ARTIFACT_MAP

    def _make_checkpoint(self, stage):
        return self.CheckpointRecord(
            stage=stage,
            artifact=self.STAGE_ARTIFACT_MAP[stage],
            version=1,
            approved_at="2026-01-01T00:00:00Z",
            downstream_authorization="allow",
        )

    def test_entry_gate_passes_for_raw_requirement(self):
        """No upstream required for RAW_REQUIREMENT."""
        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir)
            result = self.check_entry_gate(run_dir, self.Stage.RAW_REQUIREMENT, [], [])
        self.assertTrue(result.passed)
        self.assertEqual(result.issues, [])
        self.assertEqual(result.exit_code, 0)

    def test_entry_gate_passes_for_requirement_brief(self):
        """No upstream required for REQUIREMENT_BRIEF."""
        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir)
            result = self.check_entry_gate(run_dir, self.Stage.REQUIREMENT_BRIEF, [], [])
        self.assertTrue(result.passed)
        self.assertEqual(result.exit_code, 0)

    def test_entry_gate_passes_when_upstream_checkpoint_approved(self):
        """RISK_DISCOVERY entry passes when REQUIREMENT_BRIEF checkpoint is approved."""
        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir)
            # Create the required artifact file
            (run_dir / self.STAGE_ARTIFACT_MAP[self.Stage.REQUIREMENT_BRIEF]).write_text("content")
            cp = self._make_checkpoint(self.Stage.REQUIREMENT_BRIEF)
            result = self.check_entry_gate(run_dir, self.Stage.RISK_DISCOVERY, [cp], [])
        self.assertTrue(result.passed)
        self.assertEqual(result.exit_code, 0)

    def test_entry_gate_fails_when_upstream_checkpoint_missing_and_no_bundle(self):
        """RISK_DISCOVERY entry fails when REQUIREMENT_BRIEF has no checkpoint and no bundle."""
        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir)
            result = self.check_entry_gate(run_dir, self.Stage.RISK_DISCOVERY, [], [])
        self.assertFalse(result.passed)
        self.assertEqual(result.exit_code, 3)  # EXIT_GATE_FAIL
        self.assertTrue(len(result.issues) > 0)

    def test_entry_gate_fails_when_upstream_artifact_file_missing(self):
        """Entry gate fails when checkpoint is approved but artifact file is absent."""
        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir)
            # No artifact file written
            cp = self._make_checkpoint(self.Stage.REQUIREMENT_BRIEF)
            result = self.check_entry_gate(run_dir, self.Stage.RISK_DISCOVERY, [cp], [])
        self.assertFalse(result.passed)
        self.assertEqual(result.exit_code, 3)  # EXIT_GATE_FAIL
        # Should mention missing file
        self.assertTrue(any("03-requirement-brief.md" in issue for issue in result.issues))

    def test_entry_gate_passes_when_upstream_covered_by_live_bundle(self):
        """Entry gate passes when upstream stage covered by a live BundleAuthorization."""
        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir)
            # Create the required artifact file
            (run_dir / self.STAGE_ARTIFACT_MAP[self.Stage.REQUIREMENT_BRIEF]).write_text("content")
            bundle = self.BundleAuthorization(
                bundle_id="bundle-001",
                stages=frozenset({self.Stage.REQUIREMENT_BRIEF}),
                authorized_at="2026-01-01T00:00:00Z",
            )
            result = self.check_entry_gate(run_dir, self.Stage.RISK_DISCOVERY, [], [bundle])
        self.assertTrue(result.passed)
        self.assertEqual(result.exit_code, 0)

    def test_entry_gate_fails_when_bundle_revoked(self):
        """Entry gate fails when the only bundle is revoked."""
        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir)
            bundle = self.BundleAuthorization(
                bundle_id="bundle-002",
                stages=frozenset({self.Stage.REQUIREMENT_BRIEF}),
                authorized_at="2026-01-01T00:00:00Z",
                revoked_at="2026-01-02T00:00:00Z",
            )
            result = self.check_entry_gate(run_dir, self.Stage.RISK_DISCOVERY, [], [bundle])
        self.assertFalse(result.passed)
        self.assertEqual(result.exit_code, 3)  # EXIT_GATE_FAIL

    def test_entry_gate_collects_all_missing_upstream(self):
        """DESIGN needs REQUIREMENT_BRIEF + RISK_DISCOVERY; both missing = 2 issues."""
        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir)
            result = self.check_entry_gate(run_dir, self.Stage.DESIGN, [], [])
        self.assertFalse(result.passed)
        # At least 2 issues (one per missing upstream)
        self.assertGreaterEqual(len(result.issues), 2)


class TestQualityGate(unittest.TestCase):
    def setUp(self):
        from tools.workflow_cli.gates import check_quality_gate
        from tools.workflow_cli.models import (
            Stage, TierBase, TierModifier, TierEstimate, CheckpointRecord,
        )
        self.check_quality_gate = check_quality_gate
        self.Stage = Stage
        self.TierBase = TierBase
        self.TierModifier = TierModifier
        self.TierEstimate = TierEstimate
        self.CheckpointRecord = CheckpointRecord

    def _locked_tier(self, base=None, modifiers=None):
        base = base or self.TierBase.STANDARD
        modifiers = modifiers or frozenset()
        est = self.TierEstimate(base=base, modifiers=modifiers)
        return est.lock(base, modifiers)

    def test_quality_gate_fails_immediately_when_tier_is_none(self):
        """Quality gate exits immediately with exit_code=3 when tier is None."""
        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir)
            result = self.check_quality_gate(
                run_dir, self.Stage.DESIGN, None, [], "some content"
            )
        self.assertFalse(result.passed)
        self.assertEqual(result.exit_code, 3)
        self.assertIn("Tier not locked", result.issues[0])

    def test_quality_gate_passes_nonempty_content_with_tier_locked(self):
        """Quality gate passes for non-empty artifact with no upstream refs."""
        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir)
            tier = self._locked_tier()
            result = self.check_quality_gate(
                run_dir, self.Stage.DESIGN, tier, [], "# Design\n\nSome valid content here."
            )
        self.assertTrue(result.passed)
        self.assertEqual(result.exit_code, 0)

    def test_quality_gate_fails_when_artifact_content_empty(self):
        """Quality gate fails when artifact content is empty."""
        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir)
            tier = self._locked_tier()
            result = self.check_quality_gate(
                run_dir, self.Stage.DESIGN, tier, [], ""
            )
        self.assertFalse(result.passed)
        self.assertEqual(result.exit_code, 3)

    def test_quality_gate_fails_when_content_whitespace_only(self):
        """Quality gate fails when artifact content is whitespace only."""
        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir)
            tier = self._locked_tier()
            result = self.check_quality_gate(
                run_dir, self.Stage.DESIGN, tier, [], "   \n\t  \n"
            )
        self.assertFalse(result.passed)
        self.assertEqual(result.exit_code, 3)

    def test_quality_gate_fails_when_upstream_id_not_closed(self):
        """Quality gate fails when REQ-ACC-001 referenced but has no closure tag."""
        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir)
            tier = self._locked_tier()
            content = "## Design\n\nAddresses REQ-ACC-001 scope changes.\n"
            result = self.check_quality_gate(
                run_dir, self.Stage.DESIGN, tier, [], content
            )
        self.assertFalse(result.passed)
        self.assertEqual(result.exit_code, 3)
        self.assertTrue(any("REQ-ACC-001" in issue for issue in result.issues))

    def test_quality_gate_passes_when_upstream_id_addressed(self):
        """Quality gate passes when REQ-ACC-001 has [ADDRESSED] closure tag."""
        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir)
            tier = self._locked_tier()
            content = (
                "## Design\n\n"
                "REQ-ACC-001 [ADDRESSED]: scope handled via new auth flow.\n"
            )
            result = self.check_quality_gate(
                run_dir, self.Stage.DESIGN, tier, [], content
            )
        self.assertTrue(result.passed)
        self.assertEqual(result.exit_code, 0)

    def test_quality_gate_passes_with_deferred_closure(self):
        """Quality gate passes when RISK-SEC-002 has [DEFERRED] closure tag."""
        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir)
            tier = self._locked_tier()
            content = "RISK-SEC-002 [DEFERRED]: will address post-MVP.\n"
            result = self.check_quality_gate(
                run_dir, self.Stage.DESIGN, tier, [], content
            )
        self.assertTrue(result.passed)

    def test_quality_gate_passes_with_out_of_scope_closure(self):
        """Quality gate passes when DES-UI-003 has [OUT-OF-SCOPE] closure tag."""
        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir)
            tier = self._locked_tier()
            content = "DES-UI-003 [OUT-OF-SCOPE]: not relevant to this stage.\n"
            result = self.check_quality_gate(
                run_dir, self.Stage.DESIGN, tier, [], content
            )
        self.assertTrue(result.passed)

    def test_quality_gate_passes_with_na_closure(self):
        """Quality gate passes when SPEC-INT-004 has [N/A] closure tag."""
        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir)
            tier = self._locked_tier()
            content = "SPEC-INT-004 [N/A]: doesn't apply here.\n"
            result = self.check_quality_gate(
                run_dir, self.Stage.DESIGN, tier, [], content
            )
        self.assertTrue(result.passed)

    def test_quality_gate_passes_with_closed_tag(self):
        """Quality gate passes when REQ-FUN-005 has [CLOSED] closure tag."""
        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir)
            tier = self._locked_tier()
            content = "REQ-FUN-005 [CLOSED]: closed in prior stage.\n"
            result = self.check_quality_gate(
                run_dir, self.Stage.DESIGN, tier, [], content
            )
        self.assertTrue(result.passed)

    def test_quality_gate_fails_on_duplicate_id_definitions(self):
        """Quality gate fails when same ID is defined twice in artifact."""
        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir)
            tier = self._locked_tier()
            content = (
                "## REQ-ACC-001 First definition\n"
                "Some content.\n\n"
                "## REQ-ACC-001 Second definition\n"
                "Duplicate.\n"
            )
            result = self.check_quality_gate(
                run_dir, self.Stage.SPEC, tier, [], content
            )
        self.assertFalse(result.passed)
        self.assertEqual(result.exit_code, 3)
        self.assertTrue(any("REQ-ACC-001" in issue for issue in result.issues))

    def test_quality_gate_passes_unique_ids(self):
        """Quality gate passes when all defined IDs are unique."""
        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir)
            tier = self._locked_tier()
            content = (
                "## REQ-ACC-001 First\nContent A.\n\n"
                "## REQ-ACC-002 Second\nContent B.\n"
            )
            result = self.check_quality_gate(
                run_dir, self.Stage.SPEC, tier, [], content
            )
        self.assertTrue(result.passed)


class TestForcedSubagentReview(unittest.TestCase):
    def setUp(self):
        from tools.workflow_cli.gates import check_forced_subagent_review
        from tools.workflow_cli.models import (
            Stage, TierBase, TierModifier, TierEstimate,
        )
        self.check_forced_subagent_review = check_forced_subagent_review
        self.Stage = Stage
        self.TierBase = TierBase
        self.TierModifier = TierModifier
        self.TierEstimate = TierEstimate

    def _locked_tier(self, base=None, modifiers=None):
        base = base or self.TierBase.STANDARD
        modifiers = modifiers if modifiers is not None else frozenset()
        est = self.TierEstimate(base=base, modifiers=modifiers)
        return est.lock(base, modifiers)

    def test_passes_when_no_modifiers(self):
        """No forced review when tier has no modifiers."""
        with tempfile.TemporaryDirectory() as tmpdir:
            reviews_dir = Path(tmpdir)
            tier = self._locked_tier(modifiers=frozenset())
            result = self.check_forced_subagent_review(
                self.Stage.DESIGN, tier, reviews_dir
            )
        self.assertTrue(result.passed)
        self.assertEqual(result.exit_code, 0)

    def test_passes_when_tier_is_none(self):
        """No forced review when tier is None."""
        with tempfile.TemporaryDirectory() as tmpdir:
            reviews_dir = Path(tmpdir)
            result = self.check_forced_subagent_review(
                self.Stage.DESIGN, None, reviews_dir
            )
        self.assertTrue(result.passed)
        self.assertEqual(result.exit_code, 0)

    def test_fails_when_migration_modifier_design_stage_no_review(self):
        """Forced review required when migration modifier + DESIGN stage + no review files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            reviews_dir = Path(tmpdir)
            tier = self._locked_tier(
                modifiers=frozenset({self.TierModifier.MIGRATION})
            )
            result = self.check_forced_subagent_review(
                self.Stage.DESIGN, tier, reviews_dir
            )
        self.assertFalse(result.passed)
        self.assertEqual(result.exit_code, 5)

    def test_fails_when_safety_modifier_spec_stage_no_review(self):
        """Forced review required when safety modifier + SPEC stage + no review files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            reviews_dir = Path(tmpdir)
            tier = self._locked_tier(
                modifiers=frozenset({self.TierModifier.SAFETY})
            )
            result = self.check_forced_subagent_review(
                self.Stage.SPEC, tier, reviews_dir
            )
        self.assertFalse(result.passed)
        self.assertEqual(result.exit_code, 5)

    def test_fails_when_cross_project_modifier_plan_stage_no_review(self):
        """Forced review required when cross_project modifier + PLAN stage + no review files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            reviews_dir = Path(tmpdir)
            tier = self._locked_tier(
                modifiers=frozenset({self.TierModifier.CROSS_PROJECT})
            )
            result = self.check_forced_subagent_review(
                self.Stage.PLAN, tier, reviews_dir
            )
        self.assertFalse(result.passed)
        self.assertEqual(result.exit_code, 5)

    def test_passes_when_modifiers_present_but_review_file_exists(self):
        """Forced review passes when version-matched subagent review file exists."""
        with tempfile.TemporaryDirectory() as tmpdir:
            reviews_dir = Path(tmpdir)
            # Create a version-matched subagent review file (v1)
            review_file = reviews_dir / "design-subagent-review-v1.md"
            review_file.write_text("Review notes here.")
            tier = self._locked_tier(
                modifiers=frozenset({self.TierModifier.MIGRATION})
            )
            result = self.check_forced_subagent_review(
                self.Stage.DESIGN, tier, reviews_dir, version=1
            )
        self.assertTrue(result.passed)
        self.assertEqual(result.exit_code, 0)

    def test_passes_when_modifiers_present_but_subagent_review_file_exists(self):
        """Forced review passes when version-matched subagent review file exists."""
        with tempfile.TemporaryDirectory() as tmpdir:
            reviews_dir = Path(tmpdir)
            review_file = reviews_dir / "design-subagent-review-v1.md"
            review_file.write_text("Subagent review notes.")
            tier = self._locked_tier(
                modifiers=frozenset({self.TierModifier.MIGRATION})
            )
            result = self.check_forced_subagent_review(
                self.Stage.DESIGN, tier, reviews_dir, version=1
            )
        self.assertTrue(result.passed)
        self.assertEqual(result.exit_code, 0)

    def test_passes_when_stage_is_requirement_brief(self):
        """Forced review does NOT apply to REQUIREMENT_BRIEF stage."""
        with tempfile.TemporaryDirectory() as tmpdir:
            reviews_dir = Path(tmpdir)
            tier = self._locked_tier(
                modifiers=frozenset({self.TierModifier.MIGRATION})
            )
            result = self.check_forced_subagent_review(
                self.Stage.REQUIREMENT_BRIEF, tier, reviews_dir
            )
        self.assertTrue(result.passed)
        self.assertEqual(result.exit_code, 0)

    def test_passes_when_stage_is_risk_discovery(self):
        """Forced review does NOT apply to RISK_DISCOVERY stage."""
        with tempfile.TemporaryDirectory() as tmpdir:
            reviews_dir = Path(tmpdir)
            tier = self._locked_tier(
                modifiers=frozenset({self.TierModifier.SAFETY})
            )
            result = self.check_forced_subagent_review(
                self.Stage.RISK_DISCOVERY, tier, reviews_dir
            )
        self.assertTrue(result.passed)
        self.assertEqual(result.exit_code, 0)

    def test_passes_when_modifier_is_dependency_only(self):
        """DEPENDENCY modifier alone does not trigger forced review."""
        with tempfile.TemporaryDirectory() as tmpdir:
            reviews_dir = Path(tmpdir)
            tier = self._locked_tier(
                modifiers=frozenset({self.TierModifier.DEPENDENCY})
            )
            result = self.check_forced_subagent_review(
                self.Stage.DESIGN, tier, reviews_dir
            )
        self.assertTrue(result.passed)
        self.assertEqual(result.exit_code, 0)


def test_forced_review_version_aware(tmp_path):
    from tools.workflow_cli.gates import check_forced_subagent_review
    from tools.workflow_cli.models import Stage, TierBase, TierEstimate, TierModifier
    reviews = tmp_path / "reviews"
    reviews.mkdir()
    tier = TierEstimate(base=TierBase.STANDARD, modifiers=frozenset({TierModifier.SAFETY}))
    # A v1 subagent-review must NOT clear a v2 approval.
    (reviews / "design-subagent-review-v1.md").write_text("findings", encoding="utf-8")
    r2 = check_forced_subagent_review(Stage.DESIGN, tier, reviews, version=2)
    assert r2.passed is False and r2.exit_code == 5
    # The matching v2 file clears it.
    (reviews / "design-subagent-review-v2.md").write_text("findings", encoding="utf-8")
    r2b = check_forced_subagent_review(Stage.DESIGN, tier, reviews, version=2)
    assert r2b.passed is True


class TestPlanCodeBlockGate(unittest.TestCase):
    def setUp(self):
        from tools.workflow_cli.gates import check_quality_gate
        from tools.workflow_cli.models import Stage, TierBase, TierEstimate
        self.check = check_quality_gate
        self.Stage = Stage
        self.standard = TierEstimate(base=TierBase.STANDARD, modifiers=frozenset())
        self.light = TierEstimate(base=TierBase.LIGHT, modifiers=frozenset())

    def _plan(
        self,
        with_code: bool,
        outside_skeleton_code: bool = False,
        indented_skeleton_code: bool = False,
    ) -> str:
        if with_code:
            fence_prefix = "  " if indented_skeleton_code else ""
            skeleton = f"{fence_prefix}```python\ndef f():\n    ...\n{fence_prefix}```\n"
        else:
            skeleton = "(prose only)\n"
        verification = (
            "Verification:\n```python\nassert True\n```\n"
            if outside_skeleton_code
            else "Verification: run targeted tests\n"
        )
        return (
            "# PLAN\n\n"
            "### PLAN-TASK-001: do thing\n"
            "TDD Applicable: yes\n"
            f"Skeleton:\n{skeleton}\n"
            "Steps:\n- [ ] red\n- [ ] green\n"
            f"{verification}"
        )

    def test_standard_plan_without_code_block_fails(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            r = self.check(Path(tmp), self.Stage.PLAN, self.standard, [], self._plan(False))
            self.assertFalse(r.passed)
            self.assertEqual(r.exit_code, 3)

    def test_standard_plan_code_block_outside_skeleton_fails(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            r = self.check(
                Path(tmp),
                self.Stage.PLAN,
                self.standard,
                [],
                self._plan(False, outside_skeleton_code=True),
            )
            self.assertFalse(r.passed)
            self.assertEqual(r.exit_code, 3)

    def test_standard_plan_with_code_block_passes_this_check(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            r = self.check(Path(tmp), self.Stage.PLAN, self.standard, [], self._plan(True))
            self.assertTrue(r.passed)

    def test_standard_plan_with_indented_skeleton_code_block_passes_this_check(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            r = self.check(
                Path(tmp),
                self.Stage.PLAN,
                self.standard,
                [],
                self._plan(True, indented_skeleton_code=True),
            )
            self.assertTrue(r.passed)

    def test_light_plan_without_code_block_exempt(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            r = self.check(Path(tmp), self.Stage.PLAN, self.light, [], self._plan(False))
            self.assertTrue(r.passed)

    def test_non_plan_stage_unaffected(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            r = self.check(Path(tmp), self.Stage.SPEC, self.standard, [], "non-empty spec body\n")
            # SPEC gate is Task 3; this check must not fire for PLAN-code on a SPEC artifact
            self.assertTrue(all("code block" not in i for i in r.issues))

    def test_standard_plan_empty_skeleton_with_fence_in_next_field_fails(self):
        import tempfile
        from pathlib import Path
        plan = (
            "# PLAN\n\n"
            "### PLAN-TASK-001: do thing\n"
            "TDD Applicable: yes\n"
            "Skeleton:\n"
            "Steps:\n"
            "```python\n"
            "assert True\n"
            "```\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            r = self.check(Path(tmp), self.Stage.PLAN, self.standard, [], plan)
            self.assertFalse(r.passed)
            self.assertEqual(r.exit_code, 3)


if __name__ == "__main__":
    unittest.main()

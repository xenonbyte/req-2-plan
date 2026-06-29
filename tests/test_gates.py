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
            content = (
                "# Design\n\n"
                "## Design Summary\ncontent\n\n"
                "## Current Code Evidence\ncontent\n\n"
                "## Requirements Coverage\ncontent\n\n"
                "## Options Considered\ncontent\n\n"
                "## Chosen Design\ncontent\n\n"
                "### DES-ARCH-001 Selected architecture\ncontent\n\n"
                "## Decision Requests\nnone\n\n"
                "## Rollback\ncontent\n\n"
                "## Observability\ncontent\n\n"
                "## SPEC Handoff\ncontent\n"
            )
            result = self.check_quality_gate(
                run_dir, self.Stage.DESIGN, tier, [], content
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

    def test_readonly_upstream_summary_heading_does_not_define_referenced_id(self):
        """Read-only seeded summaries must not hide an unclosed upstream reference."""
        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir)
            tier = self._locked_tier()
            content = (
                "# Design\n\n"
                "## Design Summary\ncontent\n\n"
                "## Current Code Evidence\ncontent\n\n"
                "## Requirements Coverage\n"
                "RISK-SEC-001 requires hardened token handling.\n\n"
                "## Options Considered\ncontent\n\n"
                "## Chosen Design\ncontent\n\n"
                "### DES-ARCH-001 Selected architecture\ncontent\n\n"
                "## Rollback\ncontent\n\n"
                "## Observability\ncontent\n\n"
                "## SPEC Handoff\ncontent\n\n"
                "## Upstream Summary (read-only)\n"
                "# Risk Discovery\n"
                "## RISK-SEC-001 Sensitive token exposure\n"
                "Original upstream risk text.\n"
                "<!-- /r2p-read-only -->\n"
            )
            result = self.check_quality_gate(
                run_dir, self.Stage.DESIGN, tier, [], content
            )
        self.assertFalse(result.passed)
        self.assertTrue(
            any(
                "RISK-SEC-001" in issue and "closure status tag" in issue
                for issue in result.issues
            ),
            result.issues,
        )

    def test_quality_gate_passes_when_upstream_id_addressed(self):
        """Quality gate passes when REQ-ACC-001 has [ADDRESSED] closure tag."""
        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir)
            tier = self._locked_tier()
            content = (
                "# Design\n\n"
                "## Design Summary\ncontent\n\n"
                "## Current Code Evidence\ncontent\n\n"
                "## Requirements Coverage\n"
                "REQ-ACC-001 [ADDRESSED]: scope handled via new auth flow.\n\n"
                "## Options Considered\ncontent\n\n"
                "## Chosen Design\ncontent\n\n"
                "### DES-ARCH-001 Selected architecture\ncontent\n\n"
                "## Decision Requests\nnone\n\n"
                "## Rollback\ncontent\n\n"
                "## Observability\ncontent\n\n"
                "## SPEC Handoff\ncontent\n"
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
            content = (
                "# Design\n\n"
                "## Design Summary\ncontent\n\n"
                "## Current Code Evidence\n"
                "RISK-SEC-002 [DEFERRED]: will address post-MVP.\n\n"
                "## Requirements Coverage\ncontent\n\n"
                "## Options Considered\ncontent\n\n"
                "## Chosen Design\ncontent\n\n"
                "### DES-ARCH-001 Selected architecture\ncontent\n\n"
                "## Decision Requests\nnone\n\n"
                "## Rollback\ncontent\n\n"
                "## Observability\ncontent\n\n"
                "## SPEC Handoff\ncontent\n"
            )
            result = self.check_quality_gate(
                run_dir, self.Stage.DESIGN, tier, [], content
            )
        self.assertTrue(result.passed)

    def test_quality_gate_passes_with_out_of_scope_closure(self):
        """Quality gate passes when DES-UI-003 has [OUT-OF-SCOPE] closure tag."""
        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir)
            tier = self._locked_tier()
            content = (
                "# Design\n\n"
                "## Design Summary\ncontent\n\n"
                "## Current Code Evidence\n"
                "DES-UI-003 [OUT-OF-SCOPE]: not relevant to this stage.\n\n"
                "## Requirements Coverage\ncontent\n\n"
                "## Options Considered\ncontent\n\n"
                "## Chosen Design\ncontent\n\n"
                "### DES-ARCH-001 Selected architecture\ncontent\n\n"
                "## Decision Requests\nnone\n\n"
                "## Rollback\ncontent\n\n"
                "## Observability\ncontent\n\n"
                "## SPEC Handoff\ncontent\n"
            )
            result = self.check_quality_gate(
                run_dir, self.Stage.DESIGN, tier, [], content
            )
        self.assertTrue(result.passed)

    def test_quality_gate_passes_with_na_closure(self):
        """Quality gate passes when SPEC-INT-004 has [N/A] closure tag."""
        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir)
            tier = self._locked_tier()
            content = (
                "# Design\n\n"
                "## Design Summary\ncontent\n\n"
                "## Current Code Evidence\n"
                "SPEC-INT-004 [N/A]: doesn't apply here.\n\n"
                "## Requirements Coverage\ncontent\n\n"
                "## Options Considered\ncontent\n\n"
                "## Chosen Design\ncontent\n\n"
                "### DES-ARCH-001 Selected architecture\ncontent\n\n"
                "## Decision Requests\nnone\n\n"
                "## Rollback\ncontent\n\n"
                "## Observability\ncontent\n\n"
                "## SPEC Handoff\ncontent\n"
            )
            result = self.check_quality_gate(
                run_dir, self.Stage.DESIGN, tier, [], content
            )
        self.assertTrue(result.passed)

    def test_quality_gate_passes_with_closed_tag(self):
        """Quality gate passes when REQ-FUN-005 has [CLOSED] closure tag."""
        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir)
            tier = self._locked_tier()
            content = (
                "# Design\n\n"
                "## Design Summary\ncontent\n\n"
                "## Current Code Evidence\n"
                "REQ-FUN-005 [CLOSED]: closed in prior stage.\n\n"
                "## Requirements Coverage\ncontent\n\n"
                "## Options Considered\ncontent\n\n"
                "## Chosen Design\ncontent\n\n"
                "### DES-ARCH-001 Selected architecture\ncontent\n\n"
                "## Decision Requests\nnone\n\n"
                "## Rollback\ncontent\n\n"
                "## Observability\ncontent\n\n"
                "## SPEC Handoff\ncontent\n"
            )
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
                "# SPEC\n\n"
                "## Behavior Contracts\n"
                "### SPEC-CORE-001 Core behavior contract\nContent A.\n\n"
                "### REQ-ACC-001 First\nContent A.\n\n"
                "### REQ-ACC-002 Second\nContent B.\n\n"
                "## API / Data / Config Contracts\ncontent\n\n"
                "## External Documentation Checked\n\n"
                "N/A — no external dependencies\n\n"
                "## Test Matrix\ncontent\n\n"
                "## Non-goals\ncontent\n\n"
                "## PLAN Handoff\ncontent\n"
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

    def test_fails_when_reviews_dir_is_symlink_with_planted_review(self):
        """A symlinked reviews/ must not satisfy the forced-review gate even when
        a version-matched review file exists through the symlink."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            outside = tmp / "outside"
            outside.mkdir()
            (outside / "design-subagent-review-v1.md").write_text("planted review")
            reviews_dir = tmp / "reviews"
            reviews_dir.symlink_to(outside, target_is_directory=True)
            tier = self._locked_tier(
                modifiers=frozenset({self.TierModifier.MIGRATION})
            )
            result = self.check_forced_subagent_review(
                self.Stage.DESIGN, tier, reviews_dir, version=1
            )
        self.assertFalse(result.passed)
        self.assertEqual(result.exit_code, 6)
        self.assertTrue(any("symlink" in i.lower() for i in result.issues))

    def test_fails_as_conflict_when_subagent_review_file_is_symlink(self):
        """A symlinked subagent review file is an unsafe conflict, not a
        missing-review request."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            reviews_dir = tmp / "reviews"
            reviews_dir.mkdir()
            outside = tmp / "outside-review.md"
            outside.write_text("planted review", encoding="utf-8")
            (reviews_dir / "design-subagent-review-v1.md").symlink_to(outside)
            tier = self._locked_tier(
                modifiers=frozenset({self.TierModifier.MIGRATION})
            )
            result = self.check_forced_subagent_review(
                self.Stage.DESIGN, tier, reviews_dir, version=1
            )
        self.assertFalse(result.passed)
        self.assertEqual(result.exit_code, 6)
        self.assertTrue(any("symlink" in i.lower() for i in result.issues))

    def test_fails_as_conflict_when_reviews_path_is_not_directory(self):
        """A malformed reviews path must not crash when probing the child file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            reviews_dir = tmp / "reviews"
            reviews_dir.write_text("not a directory", encoding="utf-8")
            tier = self._locked_tier(
                modifiers=frozenset({self.TierModifier.MIGRATION})
            )
            result = self.check_forced_subagent_review(
                self.Stage.DESIGN, tier, reviews_dir, version=1
            )
        self.assertFalse(result.passed)
        self.assertEqual(result.exit_code, 6)
        self.assertTrue(any("regular file" in i.lower() for i in result.issues))

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


class TestStageSchemaGate(unittest.TestCase):
    def setUp(self):
        from tools.workflow_cli.gates import check_quality_gate
        from tools.workflow_cli.models import Stage, TierBase, TierEstimate
        self.check_quality_gate = check_quality_gate
        self.Stage = Stage
        self.tier = TierEstimate(base=TierBase.STANDARD, modifiers=frozenset())

    def test_brief_missing_out_of_scope_section_fails(self):
        import tempfile
        from pathlib import Path
        content = "# Requirement Brief\n\n## Goal\nDo X\n\n## In-Scope\nthing\n\n## Acceptance Criteria\npasses\n"
        with tempfile.TemporaryDirectory() as tmp:
            result = self.check_quality_gate(Path(tmp), self.Stage.REQUIREMENT_BRIEF, self.tier, [], content)
        self.assertFalse(result.passed)
        self.assertTrue(any("Out-of-Scope" in i for i in result.issues))

    def test_brief_with_all_sections_passes_schema(self):
        import tempfile
        from pathlib import Path
        from tools.workflow_cli.stage_schema import required_headings
        from tools.workflow_cli.models import TierBase
        body = "# Requirement Brief\n\n" + "\n".join(
            f"{h}\nreal content here\n" for h in required_headings(self.Stage.REQUIREMENT_BRIEF, TierBase.STANDARD)
        )
        with tempfile.TemporaryDirectory() as tmp:
            result = self.check_quality_gate(Path(tmp), self.Stage.REQUIREMENT_BRIEF, self.tier, [], body)
        self.assertFalse(any("Missing required section" in i for i in result.issues))

    def test_unfilled_template_placeholder_fails(self):
        import tempfile
        from pathlib import Path
        from tools.workflow_cli.stage_schema import required_headings
        from tools.workflow_cli.models import TierBase
        body = "# Requirement Brief\n\n" + "\n".join(
            f"{h}\n<!-- fill in -->\n" for h in required_headings(self.Stage.REQUIREMENT_BRIEF, TierBase.STANDARD)
        )
        with tempfile.TemporaryDirectory() as tmp:
            result = self.check_quality_gate(Path(tmp), self.Stage.REQUIREMENT_BRIEF, self.tier, [], body)
        self.assertFalse(result.passed)
        self.assertTrue(any("placeholder" in i.lower() for i in result.issues))

    def test_raw_requirement_allows_user_text_that_looks_like_placeholder(self):
        import tempfile
        from pathlib import Path
        body = "Fix the FIXME comment in tools/foo.py"
        with tempfile.TemporaryDirectory() as tmp:
            result = self.check_quality_gate(Path(tmp), self.Stage.RAW_REQUIREMENT, self.tier, [], body)
        self.assertTrue(result.passed, result.issues)

    def test_downstream_artifact_allows_literal_fixme_in_prose(self):
        import tempfile
        from pathlib import Path
        content = (
            "# Requirement Brief\n\n"
            "## Goal\nFix the literal FIXME marker in code comments.\n\n"
            "## In-Scope\n- SCOPE-IN-001 Update code paths that mention FIXME\n\n"
            "## Out-of-Scope\n- SCOPE-OUT-001 Do not change unrelated TODO handling\n\n"
            "## Non-Goals\n- Preserve user text that names code markers\n\n"
            "## Assumptions\n- The string FIXME may appear in prose as requirement content\n\n"
            "## Acceptance Criteria\n- Quality gate accepts prose that mentions FIXME.\n\n"
            "## Open Questions\n- None.\n\n"
            "## Sources\n- User request\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            result = self.check_quality_gate(Path(tmp), self.Stage.REQUIREMENT_BRIEF, self.tier, [], content)
        self.assertTrue(result.passed, result.issues)

    def test_tbd_as_final_content_fails(self):
        import tempfile
        from pathlib import Path
        from tools.workflow_cli.stage_schema import required_headings
        from tools.workflow_cli.models import TierBase
        body = "# Requirement Brief\n\n" + "\n".join(
            f"{h}\nTBD\n" for h in required_headings(self.Stage.REQUIREMENT_BRIEF, TierBase.STANDARD)
        )
        with tempfile.TemporaryDirectory() as tmp:
            result = self.check_quality_gate(Path(tmp), self.Stage.REQUIREMENT_BRIEF, self.tier, [], body)
        self.assertFalse(result.passed)

    def test_maybe_as_final_design_content_fails(self):
        import tempfile
        from pathlib import Path
        content = (
            "# Design\n\n"
            "## Design Summary\nmaybe\n\n"
            "## Current Code Evidence\ncontent\n\n"
            "## Requirements Coverage\ncontent\n\n"
            "## Options Considered\ncontent\n\n"
            "## Chosen Design\ncontent\n\n"
            "### DES-ARCH-001 Selected architecture\ncontent\n\n"
            "## Rollback\ncontent\n\n"
            "## Observability\ncontent\n\n"
            "## SPEC Handoff\ncontent\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            result = self.check_quality_gate(Path(tmp), self.Stage.DESIGN, self.tier, [], content)
        self.assertFalse(result.passed)
        self.assertTrue(any("placeholder" in i.lower() for i in result.issues))

    def test_tbd_inside_required_field_value_fails(self):
        import tempfile
        from pathlib import Path
        from tools.workflow_cli.stage_schema import required_headings
        from tools.workflow_cli.models import TierBase
        parts = ["# Requirement Brief"]
        for h in required_headings(self.Stage.REQUIREMENT_BRIEF, TierBase.STANDARD):
            if h == "## Goal":
                parts.append(f"{h}\nStatus: TBD\n")
            elif h == "## In-Scope":
                parts.append(f"{h}\n- SCOPE-IN-001 real scope\n")
            elif h == "## Out-of-Scope":
                parts.append(f"{h}\n- SCOPE-OUT-001 real exclusion\n")
            else:
                parts.append(f"{h}\n- real content\n")
        with tempfile.TemporaryDirectory() as tmp:
            result = self.check_quality_gate(Path(tmp), self.Stage.REQUIREMENT_BRIEF, self.tier, [], "\n".join(parts))
        self.assertFalse(result.passed)
        self.assertTrue(any("placeholder" in i.lower() for i in result.issues))

    def test_tbd_list_item_in_required_section_fails(self):
        import tempfile
        from pathlib import Path
        from tools.workflow_cli.stage_schema import required_headings
        from tools.workflow_cli.models import TierBase
        parts = ["# Requirement Brief"]
        for h in required_headings(self.Stage.REQUIREMENT_BRIEF, TierBase.STANDARD):
            if h == "## In-Scope":
                parts.append(f"{h}\n- SCOPE-IN-001 real scope\n")
            elif h == "## Out-of-Scope":
                parts.append(f"{h}\n- SCOPE-OUT-001 real exclusion\n")
            elif h == "## Acceptance Criteria":
                parts.append(f"{h}\n- TBD\n")
            else:
                parts.append(f"{h}\n- real content\n")
        with tempfile.TemporaryDirectory() as tmp:
            result = self.check_quality_gate(Path(tmp), self.Stage.REQUIREMENT_BRIEF, self.tier, [], "\n".join(parts))
        self.assertFalse(result.passed)
        self.assertTrue(any("placeholder" in i.lower() for i in result.issues))

    def test_required_section_with_empty_body_fails(self):
        import tempfile
        from pathlib import Path
        from tools.workflow_cli.stage_schema import required_headings
        from tools.workflow_cli.models import TierBase
        parts = ["# Requirement Brief"]
        for h in required_headings(self.Stage.REQUIREMENT_BRIEF, TierBase.STANDARD):
            body = "" if h == "## Sources" else "real content here"
            parts.append(f"{h}\n{body}\n")
        with tempfile.TemporaryDirectory() as tmp:
            result = self.check_quality_gate(Path(tmp), self.Stage.REQUIREMENT_BRIEF, self.tier, [], "\n".join(parts))
        self.assertFalse(result.passed)
        self.assertTrue(any("Sources" in i and "body" in i for i in result.issues))

    def test_spec_without_heading_defined_native_spec_id_fails(self):
        import tempfile
        from pathlib import Path
        from tools.workflow_cli.stage_schema import required_headings
        from tools.workflow_cli.models import TierBase
        parts = ["# Spec\n"]
        for h in required_headings(self.Stage.SPEC, TierBase.STANDARD):
            if h == "## External Documentation Checked":
                parts.append(f"{h}\nN/A — no external dependencies\n")
            else:
                parts.append(f"{h}\nreal content here\n")
        body = "\n".join(parts)
        with tempfile.TemporaryDirectory() as tmp:
            result = self.check_quality_gate(Path(tmp), self.Stage.SPEC, self.tier, [], body)
        self.assertFalse(result.passed)
        self.assertTrue(any("heading" in i and "SPEC-" in i for i in result.issues))

    def test_spec_with_heading_defined_native_spec_id_passes_id_check(self):
        import tempfile
        from pathlib import Path
        from tools.workflow_cli.stage_schema import required_headings
        from tools.workflow_cli.models import TierBase
        parts = ["# Spec\n", "## SPEC-AUTH-001 Behavior\nreal content\n"]
        for h in required_headings(self.Stage.SPEC, TierBase.STANDARD):
            if h == "## External Documentation Checked":
                parts.append(f"{h}\nN/A — no external dependencies\n")
            else:
                parts.append(f"{h}\nreal content here\n")
        body = "\n".join(parts)
        with tempfile.TemporaryDirectory() as tmp:
            result = self.check_quality_gate(Path(tmp), self.Stage.SPEC, self.tier, [], body)
        self.assertFalse(any("native trace ID" in i for i in result.issues))

    def test_spec_schema_ignores_fenced_required_headings_and_native_id(self):
        import tempfile
        from pathlib import Path
        body = (
            "# Spec\n\n"
            "## External Documentation Checked\n\n"
            "N/A — no external dependencies\n\n"
            "```md\n"
            "## Behavior Contracts\n"
            "### SPEC-FAKE-001 Example only\n"
            "content\n\n"
            "## API / Data / Config Contracts\n"
            "content\n\n"
            "## Test Matrix\n"
            "content\n\n"
            "## Non-goals\n"
            "content\n\n"
            "## PLAN Handoff\n"
            "content\n"
            "```\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            result = self.check_quality_gate(Path(tmp), self.Stage.SPEC, self.tier, [], body)
        self.assertFalse(result.passed)
        self.assertTrue(any("Behavior Contracts" in i and "Missing" in i for i in result.issues))
        self.assertTrue(any("native trace ID" in i for i in result.issues))

    def test_schema_section_body_ignores_fenced_template_content(self):
        import tempfile
        from pathlib import Path
        body = (
            "# Spec\n\n"
            "## Behavior Contracts\n"
            "### SPEC-CORE-001 Real contract\n"
            "content\n\n"
            "## API / Data / Config Contracts\n"
            "content\n\n"
            "## External Documentation Checked\n\n"
            "N/A — no external dependencies\n\n"
            "## Test Matrix\n"
            "```md\n"
            "content in a template only\n"
            "```\n\n"
            "## Non-goals\n"
            "content\n\n"
            "## PLAN Handoff\n"
            "content\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            result = self.check_quality_gate(Path(tmp), self.Stage.SPEC, self.tier, [], body)
        self.assertFalse(result.passed)
        self.assertTrue(any("Test Matrix" in i and "body" in i for i in result.issues))

    def test_brief_scope_section_ids_do_not_require_heading_definition(self):
        import tempfile
        from pathlib import Path
        from tools.workflow_cli.stage_schema import required_headings
        from tools.workflow_cli.models import TierBase
        parts = ["# Requirement Brief"]
        for h in required_headings(self.Stage.REQUIREMENT_BRIEF, TierBase.STANDARD):
            if h == "## In-Scope":
                parts.append(f"{h}\n- SCOPE-IN-001 rate limit per IP\n")
            elif h == "## Out-of-Scope":
                parts.append(f"{h}\n- SCOPE-OUT-001 admin UI\n")
            else:
                parts.append(f"{h}\n- real content\n")
        with tempfile.TemporaryDirectory() as tmp:
            result = self.check_quality_gate(Path(tmp), self.Stage.REQUIREMENT_BRIEF, self.tier, [], "\n".join(parts))
        self.assertFalse(any("native trace ID" in i for i in result.issues))

    def test_malformed_trace_id_fails(self):
        import tempfile
        from pathlib import Path
        from tools.workflow_cli.stage_schema import required_headings
        from tools.workflow_cli.models import TierBase
        # Build a SPEC with a native heading SPEC-CORE-001 (well-formed) so the native-ID
        # check passes, but include SPEC-auth-1 (malformed) in a section body.
        parts = ["# Spec\n", "## SPEC-CORE-001 Core behavior\nreal content\n"]
        for h in required_headings(self.Stage.SPEC, TierBase.STANDARD):
            if h == "## External Documentation Checked":
                parts.append(f"{h}\nN/A — no external dependencies\n")
            else:
                # Include a malformed ID in one of the sections
                parts.append(f"{h}\nSPEC-auth-1 malformed id\n")
        with tempfile.TemporaryDirectory() as tmp:
            result = self.check_quality_gate(Path(tmp), self.Stage.SPEC, self.tier, [], "\n".join(parts))
        self.assertFalse(result.passed)
        self.assertTrue(any("Malformed trace ID" in i for i in result.issues))

    def test_capitalized_hyphenated_prose_not_flagged_as_malformed(self):
        import tempfile
        from pathlib import Path
        from tools.workflow_cli.stage_schema import required_headings
        from tools.workflow_cli.models import TierBase
        parts = ["# Spec", "", "## SPEC-CORE-001 Core\nWe take a RISK-based, SPEC-compliant approach.\n"]
        for h in required_headings(self.Stage.SPEC, TierBase.STANDARD):
            parts.append(f"{h}\nreal content here\n")
        with tempfile.TemporaryDirectory() as tmp:
            result = self.check_quality_gate(Path(tmp), self.Stage.SPEC, self.tier, [], "\n".join(parts))
        self.assertFalse(any("Malformed trace ID" in i for i in result.issues))


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
        fence: str = "```",
        skeleton_override: str | None = None,
    ) -> str:
        if skeleton_override is not None:
            skeleton = skeleton_override
        elif with_code:
            fence_prefix = "  " if indented_skeleton_code else ""
            skeleton = f"{fence_prefix}{fence}python\ndef f():\n    ...\n{fence_prefix}{fence}\n"
        else:
            skeleton = "(prose only)\n"
        verification = (
            "Verification:\n```python\nassert True\n```\n"
            if outside_skeleton_code
            else "Verification: run targeted tests\n"
        )
        return (
            "# PLAN\n\n"
            "## Tasks\n\n"
            "### PLAN-TASK-001: do thing\n"
            "Spec References: SPEC-AUTH-001\n"
            "Change Type: create\n"
            "TDD Applicable: yes\n"
            "Files: src/new_thing.py\n"
            f"Skeleton:\n{skeleton}\n"
            "Steps:\n- [ ] red\n- [ ] green\n"
            f"{verification}"
        )

    def _check_plan(self, tmp: str, tier, plan: str):
        import json
        from pathlib import Path
        from tools.workflow_cli.models import STAGE_ARTIFACT_MAP
        run_dir = Path(tmp)
        (run_dir / STAGE_ARTIFACT_MAP[self.Stage.SPEC]).write_text(
            "## SPEC-AUTH-001 auth\n", encoding="utf-8"
        )
        (run_dir / STAGE_ARTIFACT_MAP[self.Stage.PLAN]).write_text(plan, encoding="utf-8")
        (run_dir / "02-project-context.json").write_text(
            json.dumps({"repo_root": str(run_dir)}), encoding="utf-8")
        return self.check(run_dir, self.Stage.PLAN, tier, [], plan)

    def test_standard_plan_without_code_block_fails(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            r = self._check_plan(tmp, self.standard, self._plan(False))
            self.assertFalse(r.passed)
            self.assertEqual(r.exit_code, 3)

    def test_standard_plan_without_plan_task_heading_fails(self):
        import tempfile
        from pathlib import Path
        plan = (
            "# PLAN\n\n"
            "### Task 1: do thing\n"
            "TDD Applicable: yes\n"
            "Skeleton:\n"
            "(prose only)\n"
            "Steps:\n- [ ] go\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            r = self.check(Path(tmp), self.Stage.PLAN, self.standard, [], plan)
            self.assertFalse(r.passed)
            self.assertEqual(r.exit_code, 3)
            self.assertTrue(any("PLAN-TASK" in issue for issue in r.issues))

    def test_standard_plan_ignores_fenced_template_task_heading(self):
        import tempfile
        from pathlib import Path
        plan = (
            "# PLAN\n\n"
            "````md\n"
            "### PLAN-TASK-001: example only\n"
            "TDD Applicable: yes\n"
            "Skeleton:\n"
            "```python\n"
            "assert True\n"
            "```\n"
            "````\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            r = self.check(Path(tmp), self.Stage.PLAN, self.standard, [], plan)
            self.assertFalse(r.passed)
            self.assertEqual(r.exit_code, 3)
            self.assertTrue(any("PLAN-TASK" in issue for issue in r.issues))

    def test_standard_plan_code_block_outside_skeleton_fails(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            r = self._check_plan(tmp, self.standard, self._plan(False, outside_skeleton_code=True))
            self.assertFalse(r.passed)
            self.assertEqual(r.exit_code, 3)

    def test_standard_plan_with_code_block_passes_this_check(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            r = self._check_plan(tmp, self.standard, self._plan(True))
            self.assertTrue(r.passed)

    def test_standard_plan_allows_field_labels_inside_skeleton_code_block(self):
        import tempfile
        skeleton = (
            "```yaml\n"
            "Steps:\n"
            "  - write failing test\n"
            "Files:\n"
            "  - tools/example.py\n"
            "```\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            r = self._check_plan(tmp, self.standard, self._plan(True, skeleton_override=skeleton))
            self.assertTrue(r.passed)

    def test_standard_plan_uses_tdd_applicable_field_value_only(self):
        import tempfile
        plan = (
            "# PLAN\n\n"
            "## Tasks\n\n"
            "### PLAN-TASK-001: do thing\n"
            "Spec References: SPEC-AUTH-001\n"
            "Change Type: create\n"
            "TDD Applicable: no\n"
            "Files: docs/generated.md\n"
            "Skeleton:\n"
            "(prose only)\n"
            "Steps:\n"
            "- Mention the literal text TDD Applicable: yes in documentation.\n"
            "Verification: inspect generated docs\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            r = self._check_plan(tmp, self.standard, plan)
            self.assertTrue(r.passed)

    def test_standard_plan_with_indented_skeleton_code_block_passes_this_check(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            r = self._check_plan(tmp, self.standard, self._plan(True, indented_skeleton_code=True))
            self.assertTrue(r.passed)

    def test_standard_plan_with_tilde_skeleton_code_block_passes_this_check(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            r = self._check_plan(tmp, self.standard, self._plan(True, fence="~~~"))
            self.assertTrue(r.passed)

    def test_standard_plan_with_bare_skeleton_fence_fails(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            r = self._check_plan(tmp, self.standard, self._plan(True, fence="```", skeleton_override="```\n"))
            self.assertFalse(r.passed)
            self.assertEqual(r.exit_code, 3)

    def test_standard_plan_with_unclosed_skeleton_fence_fails(self):
        import tempfile
        from pathlib import Path
        plan = (
            "# PLAN\n\n"
            "### PLAN-TASK-001: do thing\n"
            "TDD Applicable: yes\n"
            "Skeleton:\n"
            "```python\n"
            "def f():\n"
            "    return 1\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            r = self.check(Path(tmp), self.Stage.PLAN, self.standard, [], plan)
            self.assertFalse(r.passed)
            self.assertEqual(r.exit_code, 3)

    def test_standard_plan_with_empty_skeleton_code_block_fails(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            r = self._check_plan(tmp, self.standard, self._plan(True, skeleton_override="```python\n```\n"))
            self.assertFalse(r.passed)
            self.assertEqual(r.exit_code, 3)

    def test_standard_plan_with_language_missing_from_skeleton_code_block_fails(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            r = self._check_plan(
                tmp,
                self.standard,
                self._plan(True, skeleton_override="```\ndef f():\n    return 1\n```\n"),
            )
            self.assertFalse(r.passed)
            self.assertEqual(r.exit_code, 3)

    def test_light_plan_without_code_block_exempt(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            r = self._check_plan(tmp, self.light, self._plan(False))
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


class TestSpecExternalDocsGate(unittest.TestCase):
    def setUp(self):
        from tools.workflow_cli.gates import check_quality_gate
        from tools.workflow_cli.models import Stage, TierBase, TierEstimate
        self.check = check_quality_gate
        self.Stage = Stage
        self.tier = TierEstimate(base=TierBase.STANDARD, modifiers=frozenset())

    def test_spec_missing_external_docs_section_fails(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            body = "# SPEC\n\nSome contracts here.\n"
            r = self.check(Path(tmp), self.Stage.SPEC, self.tier, [], body)
            self.assertFalse(r.passed)
            self.assertEqual(r.exit_code, 3)

    def test_spec_empty_external_docs_section_fails(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            body = "# SPEC\n\n## External Documentation Checked\n\n## Next Section\n"
            r = self.check(Path(tmp), self.Stage.SPEC, self.tier, [], body)
            self.assertFalse(r.passed)
            self.assertEqual(r.exit_code, 3)

    def test_spec_external_docs_prose_only_fails(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            body = "# SPEC\n\n## External Documentation Checked\n\nChecked docs.\n"
            r = self.check(Path(tmp), self.Stage.SPEC, self.tier, [], body)
            self.assertFalse(r.passed)
            self.assertEqual(r.exit_code, 3)

    def test_spec_with_dependency_inventory_row_passes(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            body = (
                "# SPEC\n\n"
                "## Behavior Contracts\ncontent\n\n"
                "### SPEC-CORE-001 Rate-limit contract\ncontent\n\n"
                "## API / Data / Config Contracts\ncontent\n\n"
                "## External Documentation Checked\n\n"
                "| dependency | version | check date | conclusion |\n"
                "| --- | --- | --- | --- |\n"
                "| pytest | 8.x | 2026-05-31 | Context7 checked |\n\n"
                "## Test Matrix\ncontent\n\n"
                "## Non-goals\ncontent\n\n"
                "## PLAN Handoff\ncontent\n"
            )
            r = self.check(Path(tmp), self.Stage.SPEC, self.tier, [], body)
            self.assertTrue(r.passed)

    def test_spec_with_template_placeholder_inventory_row_fails(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            body = (
                "# SPEC\n\n## External Documentation Checked\n\n"
                "| dependency | version | check date | conclusion |\n"
                "| --- | --- | --- | --- |\n"
                "| _example_ | _x.y_ | _YYYY-MM-DD_ | _Context7 checked / UNCONFIRMED_ |\n"
            )
            r = self.check(Path(tmp), self.Stage.SPEC, self.tier, [], body)
            self.assertFalse(r.passed)
            self.assertEqual(r.exit_code, 3)

    def test_spec_with_placeholder_conclusion_inventory_row_fails(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            body = (
                "# SPEC\n\n## External Documentation Checked\n\n"
                "| dependency | version | check date | conclusion |\n"
                "| --- | --- | --- | --- |\n"
                "| pytest | 8.x | 2026-05-31 | _Context7 checked / UNCONFIRMED_ |\n"
            )
            r = self.check(Path(tmp), self.Stage.SPEC, self.tier, [], body)
            self.assertFalse(r.passed)
            self.assertEqual(r.exit_code, 3)

    def test_spec_with_na_row_passes(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            body = (
                "# SPEC\n\n"
                "## Behavior Contracts\ncontent\n\n"
                "### SPEC-CORE-001 Rate-limit contract\ncontent\n\n"
                "## API / Data / Config Contracts\ncontent\n\n"
                "## External Documentation Checked\n\n"
                "N/A — no external dependencies\n\n"
                "## Test Matrix\ncontent\n\n"
                "## Non-goals\ncontent\n\n"
                "## PLAN Handoff\ncontent\n"
            )
            r = self.check(Path(tmp), self.Stage.SPEC, self.tier, [], body)
            self.assertTrue(r.passed)

    def test_spec_ignores_fenced_template_na_row(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            body = (
                "# SPEC\n\n## External Documentation Checked\n\n"
                "```md\n"
                "N/A — no external dependencies\n"
                "```\n"
            )
            r = self.check(Path(tmp), self.Stage.SPEC, self.tier, [], body)
            self.assertFalse(r.passed)
            self.assertEqual(r.exit_code, 3)

    def test_spec_ignores_fenced_template_external_docs_section(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            body = (
                "# SPEC\n\n"
                "```md\n"
                "## External Documentation Checked\n\n"
                "N/A — no external dependencies\n"
                "```\n"
            )
            r = self.check(Path(tmp), self.Stage.SPEC, self.tier, [], body)
            self.assertFalse(r.passed)
            self.assertEqual(r.exit_code, 3)

    def test_plan_stage_not_required_to_have_section(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            body = "# PLAN\n\n### PLAN-TASK-001: x\nTDD Applicable: no\nSteps:\n- [ ] go\n"
            r = self.check(Path(tmp), self.Stage.PLAN, self.tier, [], body)
            self.assertTrue(all("External Documentation" not in i for i in r.issues))


class TestTraceClosureInPlanGate(unittest.TestCase):
    def test_plan_gate_fails_when_spec_uncovered(self):
        import tempfile
        from pathlib import Path
        from tools.workflow_cli.gates import check_quality_gate
        from tools.workflow_cli.models import Stage, TierBase, TierEstimate, STAGE_ARTIFACT_MAP
        tier = TierEstimate(base=TierBase.STANDARD, modifiers=frozenset())
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            (run_dir / STAGE_ARTIFACT_MAP[Stage.SPEC]).write_text(
                "## SPEC-AUTH-001 login\nbehavior\n", encoding="utf-8")
            plan = "## Tasks\n\n### PLAN-TASK-001 do thing\nSpec References: SPEC-NOPE-000\n"
            (run_dir / STAGE_ARTIFACT_MAP[Stage.PLAN]).write_text(plan, encoding="utf-8")
            result = check_quality_gate(run_dir, Stage.PLAN, tier, [], plan)
        self.assertFalse(result.passed)
        self.assertTrue(any("SPEC-AUTH-001" in i for i in result.issues))

    def test_plan_gate_accepts_structured_spec_reference_without_legacy_closure_tag(self):
        import tempfile
        from pathlib import Path
        from tools.workflow_cli.gates import check_quality_gate
        from tools.workflow_cli.models import Stage, TierBase, TierEstimate, STAGE_ARTIFACT_MAP
        tier = TierEstimate(base=TierBase.STANDARD, modifiers=frozenset())
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            (run_dir / STAGE_ARTIFACT_MAP[Stage.SPEC]).write_text(
                "## SPEC-AUTH-001 login\nbehavior\n", encoding="utf-8")
            plan = "## Tasks\n\n### PLAN-TASK-001 do thing\nSpec References: SPEC-AUTH-001\nTDD Applicable: no\n"
            (run_dir / STAGE_ARTIFACT_MAP[Stage.PLAN]).write_text(plan, encoding="utf-8")
            result = check_quality_gate(run_dir, Stage.PLAN, tier, [], plan)
        self.assertFalse(any("closure status tag" in i for i in result.issues))

    def test_plan_gate_fails_on_scope_overflow(self):
        import tempfile
        from pathlib import Path
        from tools.workflow_cli.gates import check_quality_gate
        from tools.workflow_cli.models import Stage, TierBase, TierEstimate, STAGE_ARTIFACT_MAP
        tier = TierEstimate(base=TierBase.STANDARD, modifiers=frozenset())
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            (run_dir / STAGE_ARTIFACT_MAP[Stage.REQUIREMENT_BRIEF]).write_text(
                "## Out-of-Scope\n- SCOPE-OUT-001 admin UI\n", encoding="utf-8")
            plan = "## Tasks\n### PLAN-TASK-001 touch SCOPE-OUT-001\n"
            (run_dir / STAGE_ARTIFACT_MAP[Stage.PLAN]).write_text(plan, encoding="utf-8")
            r = check_quality_gate(run_dir, Stage.PLAN, tier, [], plan)
        self.assertFalse(r.passed)
        self.assertTrue(any("SCOPE-OUT-001" in i for i in r.issues))

    def test_plan_gate_ignores_scope_out_in_seeded_upstream_summary(self):
        import tempfile
        from pathlib import Path
        from tools.workflow_cli.gates import check_quality_gate
        from tools.workflow_cli.models import Stage, TierBase, TierEstimate, STAGE_ARTIFACT_MAP
        tier = TierEstimate(base=TierBase.STANDARD, modifiers=frozenset())
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            (run_dir / STAGE_ARTIFACT_MAP[Stage.REQUIREMENT_BRIEF]).write_text(
                "## Out-of-Scope\n- SCOPE-OUT-001 admin UI\n", encoding="utf-8")
            (run_dir / STAGE_ARTIFACT_MAP[Stage.SPEC]).write_text(
                "## SPEC-AUTH-001 auth\nbehavior\n", encoding="utf-8")
            plan = (
                "## Tasks\n"
                "### PLAN-TASK-001 touch auth\n"
                "Spec References: SPEC-AUTH-001\n"
                "TDD Applicable: no\n"
                "Verification: pytest\n\n"
                "## Upstream Summary (read-only)\n"
                "The brief excluded SCOPE-OUT-001 from implementation.\n"
            )
            (run_dir / STAGE_ARTIFACT_MAP[Stage.PLAN]).write_text(plan, encoding="utf-8")
            r = check_quality_gate(run_dir, Stage.PLAN, tier, [], plan)
        self.assertFalse(any("scope overflow" in i.lower() for i in r.issues))


class TestScopeFreeze(unittest.TestCase):
    def setUp(self):
        from tools.workflow_cli.gates import check_quality_gate
        from tools.workflow_cli.models import Stage, TierBase, TierEstimate
        self.check = check_quality_gate
        self.Stage = Stage
        self.tier = TierEstimate(base=TierBase.STANDARD, modifiers=frozenset())

    def _brief(self, in_scope, out_scope):
        from tools.workflow_cli.stage_schema import required_headings
        from tools.workflow_cli.models import TierBase
        body = ["# Requirement Brief"]
        for h in required_headings(self.Stage.REQUIREMENT_BRIEF, TierBase.STANDARD):
            if h == "## In-Scope":
                body.append(f"{h}\n{in_scope}")
            elif h == "## Out-of-Scope":
                body.append(f"{h}\n{out_scope}")
            else:
                body.append(f"{h}\n- real content\n")
        return "\n".join(body)

    def test_in_scope_without_id_fails(self):
        import tempfile
        from pathlib import Path
        content = self._brief("- rate limit per IP (no id)", "- SCOPE-OUT-001 admin UI")
        with tempfile.TemporaryDirectory() as tmp:
            r = self.check(Path(tmp), self.Stage.REQUIREMENT_BRIEF, self.tier, [], content)
        self.assertFalse(r.passed)
        self.assertTrue(any("SCOPE-IN" in i for i in r.issues))

    def test_scope_with_ids_passes_freeze(self):
        import tempfile
        from pathlib import Path
        content = self._brief("- SCOPE-IN-001 rate limit per IP", "- SCOPE-OUT-001 admin UI")
        with tempfile.TemporaryDirectory() as tmp:
            r = self.check(Path(tmp), self.Stage.REQUIREMENT_BRIEF, self.tier, [], content)
        self.assertFalse(any("SCOPE-IN" in i or "SCOPE-OUT" in i for i in r.issues))

    def test_duplicate_scope_stable_ids_fail(self):
        import tempfile
        from pathlib import Path
        content = self._brief(
            "- SCOPE-IN-001 rate limit per IP\n- SCOPE-IN-001 login throttling",
            "- SCOPE-OUT-001 admin UI\n- SCOPE-OUT-001 reporting dashboard",
        )
        with tempfile.TemporaryDirectory() as tmp:
            r = self.check(Path(tmp), self.Stage.REQUIREMENT_BRIEF, self.tier, [], content)
        self.assertFalse(r.passed)
        self.assertTrue(any("SCOPE-IN-001" in i and "duplicate" in i.lower() for i in r.issues))
        self.assertTrue(any("SCOPE-OUT-001" in i and "duplicate" in i.lower() for i in r.issues))

    def test_each_scope_entry_must_have_matching_id(self):
        import tempfile
        from pathlib import Path
        content = self._brief(
            "- SCOPE-IN-001 rate limit per IP\n- login throttling without id",
            "- SCOPE-OUT-001 admin UI\n- reporting dashboard without id",
        )
        with tempfile.TemporaryDirectory() as tmp:
            r = self.check(Path(tmp), self.Stage.REQUIREMENT_BRIEF, self.tier, [], content)
        self.assertFalse(r.passed)
        self.assertTrue(any("In-Scope" in i and "entry" in i for i in r.issues))
        self.assertTrue(any("Out-of-Scope" in i and "entry" in i for i in r.issues))

    def test_scope_ids_elsewhere_do_not_satisfy_scope_sections(self):
        import tempfile
        from pathlib import Path
        content = self._brief("- rate limit per IP (no id)", "- admin UI (no id)") + "\n\n## Appendix\nSCOPE-IN-001\nSCOPE-OUT-001\n"
        with tempfile.TemporaryDirectory() as tmp:
            r = self.check(Path(tmp), self.Stage.REQUIREMENT_BRIEF, self.tier, [], content)
        self.assertFalse(r.passed)
        self.assertTrue(any("In-Scope" in i for i in r.issues))
        self.assertTrue(any("Out-of-Scope" in i for i in r.issues))

    def test_standard_brief_without_assumptions_or_questions_fails(self):
        import tempfile
        from pathlib import Path
        from tools.workflow_cli.stage_schema import required_headings
        from tools.workflow_cli.models import TierBase
        parts = ["# Requirement Brief"]
        for h in required_headings(self.Stage.REQUIREMENT_BRIEF, TierBase.STANDARD):
            if h == "## In-Scope":
                parts.append(f"{h}\n- SCOPE-IN-001 x\n")
            elif h == "## Out-of-Scope":
                parts.append(f"{h}\n- SCOPE-OUT-001 y\n")
            elif h in ("## Assumptions", "## Open Questions"):
                parts.append(f"{h}\n")  # empty
            else:
                parts.append(f"{h}\n- content\n")
        content = "\n".join(parts)
        with tempfile.TemporaryDirectory() as tmp:
            r = self.check(Path(tmp), self.Stage.REQUIREMENT_BRIEF, self.tier, [], content)
        self.assertFalse(r.passed)
        self.assertTrue(any("assumption" in i.lower() or "open question" in i.lower() for i in r.issues))


class TestPlanTaskFields(unittest.TestCase):
    def setUp(self):
        from tools.workflow_cli.gates import check_quality_gate
        from tools.workflow_cli.models import Stage, TierBase, TierEstimate
        self.check = check_quality_gate
        self.Stage = Stage
        self.tier = TierEstimate(base=TierBase.STANDARD, modifiers=frozenset())

    def _gate(self, plan_body):
        import tempfile
        from pathlib import Path
        from tools.workflow_cli.models import STAGE_ARTIFACT_MAP
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            (run_dir / STAGE_ARTIFACT_MAP[self.Stage.SPEC]).write_text(
                "## SPEC-AUTH-001 login\n", encoding="utf-8")
            (run_dir / STAGE_ARTIFACT_MAP[self.Stage.PLAN]).write_text(plan_body, encoding="utf-8")
            return self.check(run_dir, self.Stage.PLAN, self.tier, [], plan_body)

    def test_task_missing_verification_fails(self):
        plan = ("## Tasks\n\n### PLAN-TASK-001 do it\n"
                "Spec References: SPEC-AUTH-001\n")
        r = self._gate(plan)
        self.assertFalse(r.passed)
        self.assertTrue(any("Verification" in i for i in r.issues))

    def test_task_missing_execution_fields_fails(self):
        plan = ("## Tasks\n\n### PLAN-TASK-001 do it\n"
                "Spec References: SPEC-AUTH-001\n"
                "Verification: pytest\n")
        r = self._gate(plan)
        self.assertFalse(r.passed)
        for field in ("Change Type", "TDD Applicable", "Files", "Skeleton", "Steps"):
            self.assertTrue(
                any(field in i for i in r.issues),
                f"expected missing field issue for {field}; got {r.issues}",
            )

    def test_noncontiguous_numbering_fails(self):
        plan = ("## Tasks\n\n### PLAN-TASK-001 a\nSpec References: SPEC-AUTH-001\nVerification: pytest\n"
                "\n### PLAN-TASK-003 c\nSpec References: SPEC-AUTH-001\nVerification: pytest\n")
        r = self._gate(plan)
        self.assertFalse(r.passed)
        self.assertTrue(any("contiguous" in i.lower() or "numbering" in i.lower() for i in r.issues))

    def test_dangling_spec_reference_fails(self):
        plan = ("## Tasks\n\n### PLAN-TASK-001 a\n"
                "Spec References: SPEC-GHOST-999\nVerification: pytest\n")
        r = self._gate(plan)
        self.assertFalse(r.passed)
        self.assertTrue(any("SPEC-GHOST-999" in i for i in r.issues))

    def test_each_plan_task_requires_at_least_one_spec_reference(self):
        plan = (
            "## Tasks\n\n"
            "### PLAN-TASK-001 a\n"
            "Spec References: SPEC-AUTH-001\n"
            "Change Type: modify\n"
            "TDD Applicable: no\n"
            "Files: tools/a.py\n"
            "Skeleton: inspect tools/a.py\n"
            "Steps:\n"
            "- [ ] update a\n"
            "Verification: pytest\n\n"
            "### PLAN-TASK-002 b\n"
            "Spec References: n/a\n"
            "Change Type: modify\n"
            "TDD Applicable: no\n"
            "Files: tools/b.py\n"
            "Skeleton: inspect tools/b.py\n"
            "Steps:\n"
            "- [ ] update b\n"
            "Verification: pytest\n"
        )
        r = self._gate(plan)
        self.assertFalse(r.passed)
        self.assertTrue(any("PLAN-TASK-002" in i and "SPEC-*" in i for i in r.issues))

    def test_skeleton_template_placeholder_inside_fenced_code_fails(self):
        plan = (
            "## Tasks\n\n"
            "### PLAN-TASK-001 a\n"
            "Spec References: SPEC-AUTH-001\n"
            "Change Type: create\n"
            "TDD Applicable: yes\n"
            "Files: src/new.py\n"
            "Skeleton:\n"
            "```python\n"
            "# <!-- fill in -->\n"
            "```\n"
            "Steps:\n"
            "- [ ] add implementation\n"
            "Verification: pytest\n"
        )
        r = self._gate(plan)
        self.assertFalse(r.passed)
        self.assertTrue(any("PLAN-TASK-001" in i and "Skeleton" in i and "placeholder" in i for i in r.issues))

    def test_skeleton_common_placeholders_inside_fenced_code_fail(self):
        for placeholder in ("# TODO later", "TBD", "FIXME"):
            with self.subTest(placeholder=placeholder):
                plan = (
                    "## Tasks\n\n"
                    "### PLAN-TASK-001 a\n"
                    "Spec References: SPEC-AUTH-001\n"
                    "Change Type: create\n"
                    "TDD Applicable: yes\n"
                    "Files: src/new.py\n"
                    "Skeleton:\n"
                    "```python\n"
                    f"{placeholder}\n"
                    "```\n"
                    "Steps:\n"
                    "- [ ] add implementation\n"
                    "Verification: pytest\n"
                )
                r = self._gate(plan)
                self.assertFalse(r.passed)
                self.assertTrue(
                    any(
                        "PLAN-TASK-001" in i and "Skeleton" in i and "placeholder" in i
                        for i in r.issues
                    )
                )

    def test_spec_reference_must_be_defined_in_spec_artifact(self):
        import tempfile
        from pathlib import Path
        from tools.workflow_cli.models import STAGE_ARTIFACT_MAP
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            (run_dir / STAGE_ARTIFACT_MAP[self.Stage.DESIGN]).write_text(
                "## SPEC Handoff\n### SPEC-AUTH-001 planned login\n", encoding="utf-8")
            (run_dir / STAGE_ARTIFACT_MAP[self.Stage.SPEC]).write_text(
                "## Behavior Contracts\nNo native SPEC heading yet.\n", encoding="utf-8")
            plan = ("## Tasks\n\n### PLAN-TASK-001 a\n"
                    "Spec References: SPEC-AUTH-001\nVerification: pytest\n")
            (run_dir / STAGE_ARTIFACT_MAP[self.Stage.PLAN]).write_text(plan, encoding="utf-8")
            r = self.check(run_dir, self.Stage.PLAN, self.tier, [], plan)
        self.assertFalse(r.passed)
        self.assertTrue(any("SPEC-AUTH-001" in i and "SPEC artifact" in i for i in r.issues))

    def test_spec_reference_ignores_fenced_spec_headings(self):
        import tempfile
        from pathlib import Path
        from tools.workflow_cli.models import STAGE_ARTIFACT_MAP
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            (run_dir / STAGE_ARTIFACT_MAP[self.Stage.SPEC]).write_text(
                "## Behavior Contracts\n"
                "```md\n"
                "### SPEC-FAKE-001 template only\n"
                "```\n",
                encoding="utf-8",
            )
            plan = ("## Tasks\n\n### PLAN-TASK-001 a\n"
                    "Spec References: SPEC-FAKE-001\nVerification: pytest\n")
            (run_dir / STAGE_ARTIFACT_MAP[self.Stage.PLAN]).write_text(plan, encoding="utf-8")
            r = self.check(run_dir, self.Stage.PLAN, self.tier, [], plan)
        self.assertFalse(r.passed)
        self.assertTrue(any("SPEC-FAKE-001" in i and "SPEC artifact" in i for i in r.issues))

    def test_spec_reference_ignores_readonly_spec_headings(self):
        import tempfile
        from pathlib import Path
        from tools.workflow_cli.models import STAGE_ARTIFACT_MAP
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            (run_dir / STAGE_ARTIFACT_MAP[self.Stage.SPEC]).write_text(
                "## Behavior Contracts\n"
                "Native SPEC content has no fake heading.\n\n"
                "## Upstream Summary (read-only)\n"
                "# Design Artifact\n"
                "## SPEC-FAKE-001 copied from DESIGN\n"
                "<!-- /r2p-read-only -->\n",
                encoding="utf-8",
            )
            plan = (
                "## Tasks\n\n"
                "### PLAN-TASK-001 a\n"
                "Spec References: SPEC-FAKE-001\n"
                "Change Type: modify\n"
                "TDD Applicable: no\n"
                "Files: n/a\n"
                "Skeleton: inspect current behavior\n"
                "Steps:\n"
                "- [ ] update implementation\n"
                "Verification: pytest\n"
            )
            (run_dir / STAGE_ARTIFACT_MAP[self.Stage.PLAN]).write_text(plan, encoding="utf-8")
            r = self.check(run_dir, self.Stage.PLAN, self.tier, [], plan)
        self.assertFalse(r.passed)
        self.assertTrue(any("SPEC-FAKE-001" in i and "SPEC artifact" in i for i in r.issues))

    def test_files_referencing_missing_path_fails_unless_create(self):
        import json, tempfile
        from pathlib import Path
        from tools.workflow_cli.models import STAGE_ARTIFACT_MAP
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run"
            run_dir.mkdir()
            repo = Path(tmp) / "repo"
            (repo / "src").mkdir(parents=True)
            (repo / "src" / "real.py").write_text("x=1\n", encoding="utf-8")
            (run_dir / "02-project-context.json").write_text(
                json.dumps({"repo_root": str(repo)}), encoding="utf-8")
            (run_dir / STAGE_ARTIFACT_MAP[self.Stage.SPEC]).write_text(
                "## SPEC-AUTH-001 login\n", encoding="utf-8")
            plan = ("## Tasks\n\n### PLAN-TASK-001 a\n"
                    "Spec References: SPEC-AUTH-001\nChange Type: modify\n"
                    "Files:\n- src/ghost.py :: f\nVerification: pytest\n")
            (run_dir / STAGE_ARTIFACT_MAP[self.Stage.PLAN]).write_text(plan, encoding="utf-8")
            r = self.check(run_dir, self.Stage.PLAN, self.tier, [], plan)
        self.assertFalse(r.passed)
        self.assertTrue(any("ghost.py" in i for i in r.issues))

    def test_files_referencing_parent_path_outside_repo_fails_even_if_file_exists(self):
        import json, tempfile
        from pathlib import Path
        from tools.workflow_cli.models import STAGE_ARTIFACT_MAP
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = root / "run"
            run_dir.mkdir()
            repo = root / "repo"
            repo.mkdir()
            (root / "outside.py").write_text("x=1\n", encoding="utf-8")
            (run_dir / "02-project-context.json").write_text(
                json.dumps({"repo_root": str(repo)}), encoding="utf-8")
            (run_dir / STAGE_ARTIFACT_MAP[self.Stage.SPEC]).write_text(
                "## SPEC-AUTH-001 login\n", encoding="utf-8")
            plan = ("## Tasks\n\n### PLAN-TASK-001 a\n"
                    "Spec References: SPEC-AUTH-001\nChange Type: modify\n"
                    "Files:\n- ../outside.py\nVerification: pytest\n")
            (run_dir / STAGE_ARTIFACT_MAP[self.Stage.PLAN]).write_text(plan, encoding="utf-8")
            r = self.check(run_dir, self.Stage.PLAN, self.tier, [], plan)
        self.assertFalse(r.passed)
        self.assertTrue(any("../outside.py" in i and "outside repo_root" in i for i in r.issues))

    def test_inline_files_parent_path_outside_repo_fails_even_if_file_exists(self):
        import json, tempfile
        from pathlib import Path
        from tools.workflow_cli.models import STAGE_ARTIFACT_MAP
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = root / "run"
            run_dir.mkdir()
            repo = root / "repo"
            repo.mkdir()
            (root / "outside.py").write_text("x=1\n", encoding="utf-8")
            (run_dir / "02-project-context.json").write_text(
                json.dumps({"repo_root": str(repo)}), encoding="utf-8")
            (run_dir / STAGE_ARTIFACT_MAP[self.Stage.SPEC]).write_text(
                "## SPEC-AUTH-001 login\n", encoding="utf-8")
            plan = ("## Tasks\n\n### PLAN-TASK-001 a\n"
                    "Spec References: SPEC-AUTH-001\nChange Type: modify\n"
                    "Files: ../outside.py\nVerification: pytest\n")
            (run_dir / STAGE_ARTIFACT_MAP[self.Stage.PLAN]).write_text(plan, encoding="utf-8")
            r = self.check(run_dir, self.Stage.PLAN, self.tier, [], plan)
        self.assertFalse(r.passed)
        self.assertTrue(any("../outside.py" in i and "outside repo_root" in i for i in r.issues))

    def test_inline_files_existing_repo_path_passes(self):
        import json, tempfile
        from pathlib import Path
        from tools.workflow_cli.models import STAGE_ARTIFACT_MAP
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run"
            run_dir.mkdir()
            repo = Path(tmp) / "repo"
            (repo / "src").mkdir(parents=True)
            (repo / "src" / "real.py").write_text("x=1\n", encoding="utf-8")
            (run_dir / "02-project-context.json").write_text(
                json.dumps({"repo_root": str(repo)}), encoding="utf-8")
            (run_dir / STAGE_ARTIFACT_MAP[self.Stage.SPEC]).write_text(
                "## SPEC-AUTH-001 login\n", encoding="utf-8")
            plan = ("## Tasks\n\n### PLAN-TASK-001 a\n"
                    "Spec References: SPEC-AUTH-001\nChange Type: modify\n"
                    "TDD Applicable: no\n"
                    "Files: src/real.py :: f\n"
                    "Skeleton: inspect src/real.py\n"
                    "Steps:\n- [ ] update existing implementation\n"
                    "Verification: pytest\n")
            (run_dir / STAGE_ARTIFACT_MAP[self.Stage.PLAN]).write_text(plan, encoding="utf-8")
            r = self.check(run_dir, self.Stage.PLAN, self.tier, [], plan)
        self.assertTrue(r.passed, r.issues)

    def test_inline_files_markdown_code_existing_repo_path_passes(self):
        import json, tempfile
        from pathlib import Path
        from tools.workflow_cli.models import STAGE_ARTIFACT_MAP
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run"
            run_dir.mkdir()
            repo = Path(tmp) / "repo"
            (repo / "src").mkdir(parents=True)
            (repo / "src" / "real.py").write_text("x=1\n", encoding="utf-8")
            (run_dir / "02-project-context.json").write_text(
                json.dumps({"repo_root": str(repo)}), encoding="utf-8")
            (run_dir / STAGE_ARTIFACT_MAP[self.Stage.SPEC]).write_text(
                "## SPEC-AUTH-001 login\n", encoding="utf-8")
            plan = ("## Tasks\n\n### PLAN-TASK-001 a\n"
                    "Spec References: SPEC-AUTH-001\nChange Type: modify\n"
                    "TDD Applicable: no\n"
                    "Files: `src/real.py`\n"
                    "Skeleton: inspect src/real.py\n"
                    "Steps:\n- [ ] update existing implementation\n"
                    "Verification: pytest\n")
            (run_dir / STAGE_ARTIFACT_MAP[self.Stage.PLAN]).write_text(plan, encoding="utf-8")
            r = self.check(run_dir, self.Stage.PLAN, self.tier, [], plan)
        self.assertTrue(r.passed, r.issues)

    def test_files_existing_absolute_repo_path_passes(self):
        import json, tempfile
        from pathlib import Path
        from tools.workflow_cli.models import STAGE_ARTIFACT_MAP
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run"
            run_dir.mkdir()
            repo = Path(tmp) / "repo"
            (repo / "src").mkdir(parents=True)
            existing = repo / "src" / "real.py"
            existing.write_text("x=1\n", encoding="utf-8")
            (run_dir / "02-project-context.json").write_text(
                json.dumps({"repo_root": str(repo)}), encoding="utf-8")
            (run_dir / STAGE_ARTIFACT_MAP[self.Stage.SPEC]).write_text(
                "## SPEC-AUTH-001 login\n", encoding="utf-8")
            plan = ("## Tasks\n\n### PLAN-TASK-001 a\n"
                    "Spec References: SPEC-AUTH-001\nChange Type: modify\n"
                    "TDD Applicable: no\n"
                    f"Files: {existing} :: f\n"
                    "Skeleton: inspect src/real.py\n"
                    "Steps:\n- [ ] update existing implementation\n"
                    "Verification: pytest\n")
            (run_dir / STAGE_ARTIFACT_MAP[self.Stage.PLAN]).write_text(plan, encoding="utf-8")
            r = self.check(run_dir, self.Stage.PLAN, self.tier, [], plan)
        self.assertTrue(r.passed, r.issues)

    def test_files_referencing_absolute_path_outside_repo_fails_even_if_file_exists(self):
        import json, tempfile
        from pathlib import Path
        from tools.workflow_cli.models import STAGE_ARTIFACT_MAP
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = root / "run"
            run_dir.mkdir()
            repo = root / "repo"
            repo.mkdir()
            outside = root / "outside.py"
            outside.write_text("x=1\n", encoding="utf-8")
            (run_dir / "02-project-context.json").write_text(
                json.dumps({"repo_root": str(repo)}), encoding="utf-8")
            (run_dir / STAGE_ARTIFACT_MAP[self.Stage.SPEC]).write_text(
                "## SPEC-AUTH-001 login\n", encoding="utf-8")
            plan = ("## Tasks\n\n### PLAN-TASK-001 a\n"
                    "Spec References: SPEC-AUTH-001\nChange Type: modify\n"
                    f"Files:\n- {outside}\nVerification: pytest\n")
            (run_dir / STAGE_ARTIFACT_MAP[self.Stage.PLAN]).write_text(plan, encoding="utf-8")
            r = self.check(run_dir, self.Stage.PLAN, self.tier, [], plan)
        self.assertFalse(r.passed)
        self.assertTrue(any(str(outside) in i and "outside repo_root" in i for i in r.issues))

    def test_files_create_type_is_exempt(self):
        import json, tempfile
        from pathlib import Path
        from tools.workflow_cli.models import STAGE_ARTIFACT_MAP
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run"
            run_dir.mkdir()
            repo = Path(tmp) / "repo"
            repo.mkdir()
            (run_dir / "02-project-context.json").write_text(
                json.dumps({"repo_root": str(repo)}), encoding="utf-8")
            (run_dir / STAGE_ARTIFACT_MAP[self.Stage.SPEC]).write_text(
                "## SPEC-AUTH-001 login\n", encoding="utf-8")
            plan = ("## Tasks\n\n### PLAN-TASK-001 a\n"
                    "Spec References: SPEC-AUTH-001\nChange Type: create\n"
                    "TDD Applicable: no\n"
                    "Files:\n- src/new.py\n"
                    "Skeleton: create src/new.py\n"
                    "Steps:\n- [ ] add new implementation\n"
                    "Verification: pytest\n")
            (run_dir / STAGE_ARTIFACT_MAP[self.Stage.PLAN]).write_text(plan, encoding="utf-8")
            r = self.check(run_dir, self.Stage.PLAN, self.tier, [], plan)
        self.assertTrue(r.passed)
        self.assertFalse(any("new.py" in i for i in r.issues))

    def test_files_create_type_still_rejects_parent_path_outside_repo(self):
        import json, tempfile
        from pathlib import Path
        from tools.workflow_cli.models import STAGE_ARTIFACT_MAP
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = root / "run"
            run_dir.mkdir()
            repo = root / "repo"
            repo.mkdir()
            (run_dir / "02-project-context.json").write_text(
                json.dumps({"repo_root": str(repo)}), encoding="utf-8")
            (run_dir / STAGE_ARTIFACT_MAP[self.Stage.SPEC]).write_text(
                "## SPEC-AUTH-001 login\n", encoding="utf-8")
            plan = ("## Tasks\n\n### PLAN-TASK-001 a\n"
                    "Spec References: SPEC-AUTH-001\nChange Type: create\n"
                    "Files:\n- ../outside.py\nVerification: pytest\n")
            (run_dir / STAGE_ARTIFACT_MAP[self.Stage.PLAN]).write_text(plan, encoding="utf-8")
            r = self.check(run_dir, self.Stage.PLAN, self.tier, [], plan)
        self.assertFalse(r.passed)
        self.assertTrue(any("../outside.py" in i and "outside repo_root" in i for i in r.issues))

    def test_files_create_type_still_rejects_absolute_path_outside_repo(self):
        import json, tempfile
        from pathlib import Path
        from tools.workflow_cli.models import STAGE_ARTIFACT_MAP
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = root / "run"
            run_dir.mkdir()
            repo = root / "repo"
            repo.mkdir()
            outside = root / "outside.py"
            (run_dir / "02-project-context.json").write_text(
                json.dumps({"repo_root": str(repo)}), encoding="utf-8")
            (run_dir / STAGE_ARTIFACT_MAP[self.Stage.SPEC]).write_text(
                "## SPEC-AUTH-001 login\n", encoding="utf-8")
            plan = ("## Tasks\n\n### PLAN-TASK-001 a\n"
                    "Spec References: SPEC-AUTH-001\nChange Type: create\n"
                    f"Files:\n- {outside}\nVerification: pytest\n")
            (run_dir / STAGE_ARTIFACT_MAP[self.Stage.PLAN]).write_text(plan, encoding="utf-8")
            r = self.check(run_dir, self.Stage.PLAN, self.tier, [], plan)
        self.assertFalse(r.passed)
        self.assertTrue(any(str(outside) in i and "outside repo_root" in i for i in r.issues))

    def test_files_create_type_existing_path_fails(self):
        """R19: 'Change Type: create' must not target a path that already exists."""
        import json, tempfile
        from pathlib import Path
        from tools.workflow_cli.models import STAGE_ARTIFACT_MAP
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run"
            run_dir.mkdir()
            repo = Path(tmp) / "repo"
            (repo / "src").mkdir(parents=True)
            (repo / "src" / "existing.py").write_text("x=1\n", encoding="utf-8")
            (run_dir / "02-project-context.json").write_text(
                json.dumps({"repo_root": str(repo)}), encoding="utf-8")
            (run_dir / STAGE_ARTIFACT_MAP[self.Stage.SPEC]).write_text(
                "## SPEC-AUTH-001 login\n", encoding="utf-8")
            plan = ("## Tasks\n\n### PLAN-TASK-001 a\n"
                    "Spec References: SPEC-AUTH-001\nChange Type: create\n"
                    "TDD Applicable: no\n"
                    "Files:\n- src/existing.py\n"
                    "Skeleton: outline\nSteps:\n- [ ] build it\nVerification: pytest\n")
            (run_dir / STAGE_ARTIFACT_MAP[self.Stage.PLAN]).write_text(plan, encoding="utf-8")
            r = self.check(run_dir, self.Stage.PLAN, self.tier, [], plan)
        self.assertFalse(r.passed)
        self.assertTrue(
            any("src/existing.py" in i and "already exists" in i and "modify" in i
                for i in r.issues),
            r.issues,
        )

    def test_files_new_alias_existing_path_fails(self):
        """R19: the 'new' alias gets the same existing-path check as 'create'."""
        import json, tempfile
        from pathlib import Path
        from tools.workflow_cli.models import STAGE_ARTIFACT_MAP
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run"
            run_dir.mkdir()
            repo = Path(tmp) / "repo"
            repo.mkdir()
            (repo / "existing.py").write_text("x=1\n", encoding="utf-8")
            (run_dir / "02-project-context.json").write_text(
                json.dumps({"repo_root": str(repo)}), encoding="utf-8")
            (run_dir / STAGE_ARTIFACT_MAP[self.Stage.SPEC]).write_text(
                "## SPEC-AUTH-001 login\n", encoding="utf-8")
            plan = ("## Tasks\n\n### PLAN-TASK-001 a\n"
                    "Spec References: SPEC-AUTH-001\nChange Type: new\n"
                    "TDD Applicable: no\n"
                    "Files: existing.py\n"
                    "Skeleton: outline\nSteps:\n- [ ] build it\nVerification: pytest\n")
            (run_dir / STAGE_ARTIFACT_MAP[self.Stage.PLAN]).write_text(plan, encoding="utf-8")
            r = self.check(run_dir, self.Stage.PLAN, self.tier, [], plan)
        self.assertFalse(r.passed)
        self.assertTrue(
            any("existing.py" in i and "already exists" in i for i in r.issues),
            r.issues,
        )

    def test_files_create_type_flags_only_existing_paths(self):
        """R19 is per-path: a create task mixing a new and an existing file flags
        only the existing one; the missing path stays exempt."""
        import json, tempfile
        from pathlib import Path
        from tools.workflow_cli.models import STAGE_ARTIFACT_MAP
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run"
            run_dir.mkdir()
            repo = Path(tmp) / "repo"
            (repo / "src").mkdir(parents=True)
            (repo / "src" / "existing.py").write_text("x=1\n", encoding="utf-8")
            (run_dir / "02-project-context.json").write_text(
                json.dumps({"repo_root": str(repo)}), encoding="utf-8")
            (run_dir / STAGE_ARTIFACT_MAP[self.Stage.SPEC]).write_text(
                "## SPEC-AUTH-001 login\n", encoding="utf-8")
            plan = ("## Tasks\n\n### PLAN-TASK-001 a\n"
                    "Spec References: SPEC-AUTH-001\nChange Type: create\n"
                    "TDD Applicable: no\n"
                    "Files:\n- src/brand_new.py\n- src/existing.py\n"
                    "Skeleton: outline\nSteps:\n- [ ] build it\nVerification: pytest\n")
            (run_dir / STAGE_ARTIFACT_MAP[self.Stage.PLAN]).write_text(plan, encoding="utf-8")
            r = self.check(run_dir, self.Stage.PLAN, self.tier, [], plan)
        self.assertFalse(r.passed)
        self.assertTrue(any("src/existing.py" in i and "already exists" in i for i in r.issues))
        self.assertFalse(any("brand_new.py" in i for i in r.issues), r.issues)

    def test_change_type_new_is_accepted_as_create_alias(self):
        """R10: 'new' aliases 'create' — a missing path under it is exempt."""
        import json, tempfile
        from pathlib import Path
        from tools.workflow_cli.models import STAGE_ARTIFACT_MAP
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run"
            run_dir.mkdir()
            repo = Path(tmp) / "repo"
            repo.mkdir()
            (run_dir / "02-project-context.json").write_text(
                json.dumps({"repo_root": str(repo)}), encoding="utf-8")
            (run_dir / STAGE_ARTIFACT_MAP[self.Stage.SPEC]).write_text(
                "## SPEC-AUTH-001 login\n", encoding="utf-8")
            plan = ("## Tasks\n\n### PLAN-TASK-001 a\n"
                    "Spec References: SPEC-AUTH-001\nChange Type: new\n"
                    "TDD Applicable: no\nFiles:\n- src/brand_new.py\n"
                    "Skeleton: outline\nSteps:\n- [ ] build it\nVerification: pytest\n")
            (run_dir / STAGE_ARTIFACT_MAP[self.Stage.PLAN]).write_text(plan, encoding="utf-8")
            r = self.check(run_dir, self.Stage.PLAN, self.tier, [], plan)
        self.assertFalse(any("brand_new.py" in i for i in r.issues))
        self.assertFalse(any("invalid 'Change Type" in i for i in r.issues))

    def test_change_type_outside_enum_fails_loud(self):
        """R10: values outside create|modify|delete (alias new) are a gate issue."""
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            plan = ("## Tasks\n\n### PLAN-TASK-001 a\n"
                    "Spec References: none\nChange Type: refactor\n"
                    "TDD Applicable: no\nFiles: n/a\n"
                    "Skeleton: outline\nSteps:\n- [ ] do\nVerification: pytest\n")
            r = self.check(Path(tmp), self.Stage.PLAN, self.tier, [], plan)
        self.assertFalse(r.passed)
        self.assertTrue(any("invalid 'Change Type: refactor'" in i for i in r.issues))

    def test_change_type_on_continuation_line_is_still_validated(self):
        """R10: a Change Type value on a continuation line must not bypass the enum."""
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            plan = ("## Tasks\n\n### PLAN-TASK-001 a\n"
                    "Spec References: none\nChange Type:\nrefactor\n"
                    "TDD Applicable: no\nFiles: n/a\n"
                    "Skeleton: outline\nSteps:\n- [ ] do\nVerification: pytest\n")
            r = self.check(Path(tmp), self.Stage.PLAN, self.tier, [], plan)
        self.assertFalse(r.passed)
        self.assertTrue(any("invalid 'Change Type: refactor'" in i for i in r.issues))

    def test_tdd_applicable_outside_enum_fails_loud(self):
        """R18: values outside yes|no must not silently skip the Skeleton code gate."""
        import tempfile
        from pathlib import Path
        for value in ("maybe", "unclear"):
            with self.subTest(value=value):
                with tempfile.TemporaryDirectory() as tmp:
                    plan = ("## Tasks\n\n### PLAN-TASK-001 a\n"
                            "Spec References: none\nChange Type: modify\n"
                            f"TDD Applicable: {value}\nFiles: tools/a.py\n"
                            "Skeleton: outline\nSteps:\n- [ ] do\nVerification: pytest\n")
                    r = self.check(Path(tmp), self.Stage.PLAN, self.tier, [], plan)
                self.assertFalse(r.passed)
                self.assertTrue(
                    any(f"invalid 'TDD Applicable: {value}'" in i for i in r.issues),
                    f"expected invalid TDD Applicable issue; got {r.issues}")

    def test_tdd_applicable_on_continuation_line_is_still_validated(self):
        """R18: a TDD Applicable value on a continuation line must not bypass the enum."""
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            plan = ("## Tasks\n\n### PLAN-TASK-001 a\n"
                    "Spec References: none\nChange Type: modify\n"
                    "TDD Applicable:\nmaybe\nFiles: tools/a.py\n"
                    "Skeleton: outline\nSteps:\n- [ ] do\nVerification: pytest\n")
            r = self.check(Path(tmp), self.Stage.PLAN, self.tier, [], plan)
        self.assertFalse(r.passed)
        self.assertTrue(any("invalid 'TDD Applicable: maybe'" in i for i in r.issues))

    def test_tdd_applicable_yes_no_are_case_insensitive(self):
        """R18: Yes/NO pass the enum; capital Yes still requires a fenced Skeleton."""
        plan = ("## Tasks\n\n### PLAN-TASK-001 a\n"
                "Spec References: SPEC-AUTH-001\nChange Type: modify\n"
                "TDD Applicable: NO\nFiles: tools/a.py\n"
                "Skeleton: inspect tools/a.py\nSteps:\n- [ ] do\nVerification: pytest\n")
        r = self._gate(plan)
        self.assertFalse(any("invalid 'TDD Applicable" in i for i in r.issues))
        plan_yes = ("## Tasks\n\n### PLAN-TASK-001 a\n"
                    "Spec References: SPEC-AUTH-001\nChange Type: modify\n"
                    "TDD Applicable: Yes\nFiles: tools/a.py\n"
                    "Skeleton:\n```python\ndef f(): ...\n```\n"
                    "Steps:\n- [ ] do\nVerification: pytest\n")
        r = self._gate(plan_yes)
        self.assertFalse(any("invalid 'TDD Applicable" in i for i in r.issues))
        self.assertFalse(any("no fenced code block" in i for i in r.issues))

    def test_tdd_applicable_yes_on_continuation_line_still_requires_code_fence(self):
        """R18: 'yes' on a continuation line must not skip the fenced-Skeleton check."""
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            plan = ("## Tasks\n\n### PLAN-TASK-001 a\n"
                    "Spec References: none\nChange Type: modify\n"
                    "TDD Applicable:\nyes\nFiles: tools/a.py\n"
                    "Skeleton: outline only, no fence\nSteps:\n- [ ] do\nVerification: pytest\n")
            r = self.check(Path(tmp), self.Stage.PLAN, self.tier, [], plan)
        self.assertFalse(r.passed)
        self.assertTrue(any("no fenced code block" in i for i in r.issues))

    def test_files_na_with_file_change_type_fails_loud(self):
        """R16: create|modify|delete contradict 'Files: n/a'; non_code is the escape."""
        import tempfile
        from pathlib import Path
        for change_type in ("create", "modify", "delete", "new"):
            with self.subTest(change_type=change_type):
                with tempfile.TemporaryDirectory() as tmp:
                    plan = ("## Tasks\n\n### PLAN-TASK-001 a\n"
                            f"Spec References: none\nChange Type: {change_type}\n"
                            "TDD Applicable: no\nFiles: n/a\n"
                            "Skeleton: outline\nSteps:\n- [ ] do\nVerification: pytest\n")
                    r = self.check(Path(tmp), self.Stage.PLAN, self.tier, [], plan)
                self.assertFalse(r.passed)
                self.assertTrue(
                    any("no real file path" in i and "non_code" in i for i in r.issues),
                    f"expected Files/Change Type contradiction issue; got {r.issues}")

    def test_change_type_non_code_with_na_files_passes_field_checks(self):
        """R16: non_code + 'Files: n/a' is the legal no-file task shape."""
        plan = ("## Tasks\n\n### PLAN-TASK-001 a\n"
                "Spec References: SPEC-AUTH-001\nChange Type: non_code\n"
                "TDD Applicable: no\nFiles: n/a\n"
                "Skeleton: outline the manual step\nSteps:\n- [ ] do\nVerification: pytest\n")
        r = self._gate(plan)
        self.assertFalse(any("invalid 'Change Type" in i for i in r.issues))
        self.assertFalse(any("no real file path" in i for i in r.issues))
        self.assertFalse(any("non_code" in i for i in r.issues))

    def test_change_type_non_code_with_real_files_fails_loud(self):
        """R16: non_code must not smuggle file paths past the file-ref checks."""
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            plan = ("## Tasks\n\n### PLAN-TASK-001 a\n"
                    "Spec References: none\nChange Type: non_code\n"
                    "TDD Applicable: no\nFiles: tools/a.py\n"
                    "Skeleton: outline\nSteps:\n- [ ] do\nVerification: pytest\n")
            r = self.check(Path(tmp), self.Stage.PLAN, self.tier, [], plan)
        self.assertFalse(r.passed)
        self.assertTrue(
            any("non_code" in i and "file path" in i for i in r.issues),
            f"expected non_code/Files contradiction issue; got {r.issues}")

    def test_invalid_change_type_with_na_files_reports_only_enum_issue(self):
        """R16: an invalid Change Type must not stack a second Files/n-a issue."""
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            plan = ("## Tasks\n\n### PLAN-TASK-001 a\n"
                    "Spec References: none\nChange Type: refactor\n"
                    "TDD Applicable: no\nFiles: n/a\n"
                    "Skeleton: outline\nSteps:\n- [ ] do\nVerification: pytest\n")
            r = self.check(Path(tmp), self.Stage.PLAN, self.tier, [], plan)
        self.assertFalse(r.passed)
        self.assertTrue(any("invalid 'Change Type: refactor'" in i for i in r.issues))
        self.assertFalse(any("no real file path" in i for i in r.issues))

    def test_files_recreate_type_does_not_skip_missing_path_check(self):
        import json, tempfile
        from pathlib import Path
        from tools.workflow_cli.models import STAGE_ARTIFACT_MAP
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run"
            run_dir.mkdir()
            repo = Path(tmp) / "repo"
            repo.mkdir()
            (run_dir / "02-project-context.json").write_text(
                json.dumps({"repo_root": str(repo)}), encoding="utf-8")
            (run_dir / STAGE_ARTIFACT_MAP[self.Stage.SPEC]).write_text(
                "## SPEC-AUTH-001 login\n", encoding="utf-8")
            plan = ("## Tasks\n\n### PLAN-TASK-001 a\n"
                    "Spec References: SPEC-AUTH-001\nChange Type: recreate\n"
                    "Files:\n- src/new.py\nVerification: pytest\n")
            (run_dir / STAGE_ARTIFACT_MAP[self.Stage.PLAN]).write_text(plan, encoding="utf-8")
            r = self.check(run_dir, self.Stage.PLAN, self.tier, [], plan)
        self.assertFalse(r.passed)
        self.assertTrue(any("new.py" in i and "missing path" in i for i in r.issues))


class TestPlanContextPackGate(unittest.TestCase):
    """R11: standard-tier PLAN requires a usable Context Pack truth anchor."""

    _VALID_PLAN = (
        "## Tasks\n\n"
        "### PLAN-TASK-001 wire limiter\n"
        "Spec References: SPEC-AUTH-001\n"
        "Change Type: create\n"
        "TDD Applicable: no\n"
        "Files: src/limiter.py\n"
        "Skeleton: inspect current middleware\n"
        "Steps:\n"
        "- [ ] update implementation\n"
        "Verification: pytest\n"
    )

    def setUp(self):
        from tools.workflow_cli.gates import check_quality_gate
        from tools.workflow_cli.models import Stage, TierBase, TierEstimate
        self.check = check_quality_gate
        self.Stage = Stage
        self.TierBase = TierBase
        self.standard = TierEstimate(base=TierBase.STANDARD, modifiers=frozenset())
        self.light = TierEstimate(base=TierBase.LIGHT, modifiers=frozenset())

    def _run_dir_with_spec(self, tmp):
        import json
        from pathlib import Path
        from tools.workflow_cli.models import STAGE_ARTIFACT_MAP
        run_dir = Path(tmp) / "run"
        run_dir.mkdir()
        (run_dir / STAGE_ARTIFACT_MAP[self.Stage.SPEC]).write_text(
            "## SPEC-AUTH-001 login\n", encoding="utf-8")
        (run_dir / STAGE_ARTIFACT_MAP[self.Stage.PLAN]).write_text(
            self._VALID_PLAN, encoding="utf-8")
        return run_dir

    def _assert_pack_issue(self, r, expected_work_id="run"):
        import shlex
        import sys
        self.assertFalse(r.passed)
        issue = next(
            (i for i in r.issues if "tools.workflow_cli context-build" in i),
            "",
        )
        self.assertIn("PYTHONPATH=", issue)
        self.assertIn(f"{shlex.quote(sys.executable)} -m tools.workflow_cli context-build", issue)
        self.assertIn(f"--work-id {expected_work_id}", issue)
        self.assertIn("--repo-path <repo-dir>", issue)

    def test_standard_plan_pack_remediation_includes_base_path_for_target_repo(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            base_dir = Path(tmp) / "target repo"
            run_dir = base_dir / ".req-to-plan" / "WF-20260606-login"
            run_dir.mkdir(parents=True)
            from tools.workflow_cli.models import STAGE_ARTIFACT_MAP
            (run_dir / STAGE_ARTIFACT_MAP[self.Stage.SPEC]).write_text(
                "## SPEC-AUTH-001 login\n", encoding="utf-8")
            (run_dir / STAGE_ARTIFACT_MAP[self.Stage.PLAN]).write_text(
                self._VALID_PLAN, encoding="utf-8")
            r = self.check(run_dir, self.Stage.PLAN, self.standard, [], self._VALID_PLAN)
        issue = next(
            (i for i in r.issues if "tools.workflow_cli context-build" in i),
            "",
        )
        self.assertIn("PYTHONPATH=", issue)
        self.assertIn("--work-id WF-20260606-login", issue)
        self.assertIn("--base-path", issue)
        self.assertRegex(issue, r"--base-path '.*target repo'")

    def test_standard_plan_pack_remediation_includes_base_path_from_base_cwd(self):
        import os
        import tempfile
        from pathlib import Path
        from tools.workflow_cli.models import STAGE_ARTIFACT_MAP
        original_cwd = Path.cwd()
        with tempfile.TemporaryDirectory() as tmp:
            base_dir = Path(tmp) / "target repo"
            run_dir = base_dir / ".req-to-plan" / "WF-20260606-login"
            run_dir.mkdir(parents=True)
            (run_dir / STAGE_ARTIFACT_MAP[self.Stage.SPEC]).write_text(
                "## SPEC-AUTH-001 login\n", encoding="utf-8")
            (run_dir / STAGE_ARTIFACT_MAP[self.Stage.PLAN]).write_text(
                self._VALID_PLAN, encoding="utf-8")
            try:
                os.chdir(base_dir)
                r = self.check(run_dir, self.Stage.PLAN, self.standard, [], self._VALID_PLAN)
            finally:
                os.chdir(original_cwd)
        issue = next(
            (i for i in r.issues if "tools.workflow_cli context-build" in i),
            "",
        )
        self.assertIn("--base-path", issue)
        self.assertRegex(issue, r"--base-path '.*target repo'")

    def test_standard_plan_without_pack_fails_with_remediation(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = self._run_dir_with_spec(tmp)
            r = self.check(run_dir, self.Stage.PLAN, self.standard, [], self._VALID_PLAN)
        self._assert_pack_issue(r)

    def test_standard_plan_remediation_uses_active_python_executable(self):
        import tempfile
        from unittest import mock
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = self._run_dir_with_spec(tmp)
            with mock.patch("sys.executable", "/tmp/python with spaces"):
                r = self.check(run_dir, self.Stage.PLAN, self.standard, [], self._VALID_PLAN)
        issue = next(
            (i for i in r.issues if "tools.workflow_cli context-build" in i),
            "",
        )
        self.assertIn("'/tmp/python with spaces' -m tools.workflow_cli context-build", issue)
        self.assertNotIn(" python3 -m tools.workflow_cli context-build", issue)

    def test_standard_plan_with_corrupt_pack_json_fails(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = self._run_dir_with_spec(tmp)
            (run_dir / "02-project-context.json").write_text("{not json", encoding="utf-8")
            r = self.check(run_dir, self.Stage.PLAN, self.standard, [], self._VALID_PLAN)
        self._assert_pack_issue(r)

    def test_standard_plan_with_pack_missing_repo_root_fails(self):
        import json, tempfile
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = self._run_dir_with_spec(tmp)
            (run_dir / "02-project-context.json").write_text(
                json.dumps({"languages": {}}), encoding="utf-8")
            r = self.check(run_dir, self.Stage.PLAN, self.standard, [], self._VALID_PLAN)
        self._assert_pack_issue(r)

    def test_standard_plan_with_pack_array_shape_fails(self):
        import json, tempfile
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = self._run_dir_with_spec(tmp)
            (run_dir / "02-project-context.json").write_text(
                json.dumps([{"repo_root": str(run_dir)}]), encoding="utf-8")
            r = self.check(run_dir, self.Stage.PLAN, self.standard, [], self._VALID_PLAN)
        self._assert_pack_issue(r)

    def test_standard_plan_with_pack_scalar_shape_fails(self):
        import json, tempfile
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = self._run_dir_with_spec(tmp)
            (run_dir / "02-project-context.json").write_text(
                json.dumps("not an object"), encoding="utf-8")
            r = self.check(run_dir, self.Stage.PLAN, self.standard, [], self._VALID_PLAN)
        self._assert_pack_issue(r)

    def test_standard_plan_with_nonexistent_repo_root_fails(self):
        import json, tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = self._run_dir_with_spec(tmp)
            (run_dir / "02-project-context.json").write_text(
                json.dumps({"repo_root": str(Path(tmp) / "gone")}), encoding="utf-8")
            r = self.check(run_dir, self.Stage.PLAN, self.standard, [], self._VALID_PLAN)
        self._assert_pack_issue(r)

    def test_standard_plan_with_file_repo_root_fails(self):
        import json, tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = self._run_dir_with_spec(tmp)
            not_a_dir = Path(tmp) / "afile"
            not_a_dir.write_text("x", encoding="utf-8")
            (run_dir / "02-project-context.json").write_text(
                json.dumps({"repo_root": str(not_a_dir)}), encoding="utf-8")
            r = self.check(run_dir, self.Stage.PLAN, self.standard, [], self._VALID_PLAN)
        self._assert_pack_issue(r)

    def test_standard_plan_with_usable_pack_passes(self):
        import json, tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = self._run_dir_with_spec(tmp)
            repo = Path(tmp) / "repo"
            repo.mkdir()
            (run_dir / "02-project-context.json").write_text(
                json.dumps({"repo_root": str(repo)}), encoding="utf-8")
            r = self.check(run_dir, self.Stage.PLAN, self.standard, [], self._VALID_PLAN)
        self.assertTrue(r.passed, f"unexpected issues: {r.issues}")

    def test_no_file_sentinel_is_case_insensitive_and_per_entry(self):
        """Bullet 'N/A' entries are ignored; real paths in the same list are still validated."""
        import json, tempfile
        from pathlib import Path
        from tools.workflow_cli.models import STAGE_ARTIFACT_MAP
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = self._run_dir_with_spec(tmp)
            repo = Path(tmp) / "repo"
            repo.mkdir()
            (run_dir / "02-project-context.json").write_text(
                json.dumps({"repo_root": str(repo)}), encoding="utf-8")
            plan = (
                "## Tasks\n\n"
                "### PLAN-TASK-001 wire limiter\n"
                "Spec References: SPEC-AUTH-001\n"
                "Change Type: modify\n"
                "TDD Applicable: no\n"
                "Files:\n"
                "- N/A\n"
                "- src/ghost.py\n"
                "Skeleton: inspect current middleware\n"
                "Steps:\n"
                "- [ ] update implementation\n"
                "Verification: pytest\n"
            )
            (run_dir / STAGE_ARTIFACT_MAP[self.Stage.PLAN]).write_text(plan, encoding="utf-8")
            r = self.check(run_dir, self.Stage.PLAN, self.standard, [], plan)
        self.assertTrue(any("ghost.py" in i for i in r.issues),
                        f"real path in mixed list must still be validated: {r.issues}")
        self.assertFalse(any("N/A" in i or "'n/a'" in i for i in r.issues),
                         f"sentinel entries must not be reported: {r.issues}")

    def test_light_plan_without_pack_passes(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            content = "## Tasks\n- [ ] do the small thing\n"
            r = self.check(Path(tmp), self.Stage.PLAN, self.light, [], content)
        self.assertTrue(r.passed, f"unexpected issues: {r.issues}")

    def test_standard_plan_under_nondefault_base_includes_base_path_remediation(self):
        import tempfile
        from pathlib import Path
        from tools.workflow_cli.models import STAGE_ARTIFACT_MAP
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp) / "base"
            run_dir = base / ".req-to-plan" / "work-123"
            run_dir.mkdir(parents=True)
            (run_dir / STAGE_ARTIFACT_MAP[self.Stage.SPEC]).write_text(
                "## SPEC-AUTH-001 login\n", encoding="utf-8")
            (run_dir / STAGE_ARTIFACT_MAP[self.Stage.PLAN]).write_text(
                self._VALID_PLAN, encoding="utf-8")
            r = self.check(run_dir, self.Stage.PLAN, self.standard, [], self._VALID_PLAN)
        self._assert_pack_issue(r, expected_work_id="work-123")
        self.assertTrue(
            any("--base-path" in i and str(base) in i for i in r.issues),
            f"expected non-default base-path remediation in issues, got: {r.issues}")


class TestDecisionRequestsGate(unittest.TestCase):
    """R12: standard DESIGN must explicitly resolve decision requests."""

    def setUp(self):
        from tools.workflow_cli.gates import check_quality_gate
        from tools.workflow_cli.models import Stage, TierBase, TierEstimate
        self.check = check_quality_gate
        self.Stage = Stage
        self.standard = TierEstimate(base=TierBase.STANDARD, modifiers=frozenset())
        self.light = TierEstimate(base=TierBase.LIGHT, modifiers=frozenset())

    def _design(self, decision_section: str) -> str:
        return (
            "# Design\n\n"
            "## Design Summary\ncontent\n\n"
            "## Current Code Evidence\ncontent\n\n"
            "## Requirements Coverage\ncontent\n\n"
            "## Options Considered\ncontent\n\n"
            "## Chosen Design\n### DES-ARCH-001 selected architecture\ncontent\n\n"
            f"## Decision Requests\n{decision_section}\n"
            "## Rollback\ncontent\n\n"
            "## Observability\ncontent\n\n"
            "## SPEC Handoff\ncontent\n"
        )

    def _issues(self, content, tier=None):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            return self.check(Path(tmp), self.Stage.DESIGN, tier or self.standard, [], content).issues

    def test_none_is_a_valid_explicit_statement(self):
        self.assertEqual(self._issues(self._design("none\n")), [])

    def test_pending_decision_fails_and_lists_id(self):
        section = ("### DECISION-001 limiter backend\n"
                   "Question: Redis or in-process?\nOptions: A / B\n"
                   "Recommended: A\nStatus: pending\n")
        issues = self._issues(self._design(section))
        self.assertTrue(any("DECISION-001" in i and "pending" in i for i in issues))

    def test_pending_decision_in_duplicate_section_fails(self):
        content = self._design("none\n").replace(
            "## SPEC Handoff\ncontent\n",
            "## SPEC Handoff\ncontent\n\n"
            "## Decision Requests\n"
            "### DECISION-002 region choice\n"
            "Question: q\nOptions: A / B\nRecommended: A\n"
            "Status: pending\n",
        )
        issues = self._issues(content)
        self.assertTrue(any("DECISION-002" in i and "pending" in i for i in issues),
                        f"duplicate section pending decision must fail: {issues}")

    def test_none_in_later_duplicate_section_after_block_fails(self):
        section = ("### DECISION-001 limiter backend\n"
                   "Question: q\nOptions: A / B\nRecommended: A\n"
                   "Status: selected\nSelected: A\nRationale: approved\n")
        content = self._design(section).replace(
            "## SPEC Handoff\ncontent\n",
            "## SPEC Handoff\ncontent\n\n"
            "## Decision Requests\n"
            "none\n",
        )
        issues = self._issues(content)
        self.assertTrue(any("mixes `none` with DECISION blocks" in i for i in issues),
                        f"duplicate section none must not be absorbed: {issues}")

    def test_selected_with_fields_passes(self):
        section = ("### DECISION-001 limiter backend\n"
                   "Question: Redis or in-process?\nOptions: A / B\n"
                   "Recommended: A\nStatus: selected\n"
                   "Selected: A\nRationale: multi-instance deployment\n")
        self.assertEqual(self._issues(self._design(section)), [])

    def test_selected_missing_rationale_fails(self):
        section = ("### DECISION-001 limiter backend\n"
                   "Question: q\nOptions: A / B\nRecommended: A\n"
                   "Status: selected\nSelected: A\n")
        issues = self._issues(self._design(section))
        self.assertTrue(any("DECISION-001" in i and "Rationale" in i for i in issues))

    def test_selected_missing_selected_fails(self):
        section = ("### DECISION-001 limiter backend\n"
                   "Question: q\nOptions: A / B\nRecommended: A\n"
                   "Status: selected\nRationale: needs human confirmation\n")
        issues = self._issues(self._design(section))
        self.assertTrue(any("DECISION-001" in i and "Selected" in i for i in issues))

    def test_status_outside_enum_fails(self):
        section = ("### DECISION-001 limiter backend\n"
                   "Question: q\nOptions: A / B\nRecommended: A\nStatus: chosen\n")
        issues = self._issues(self._design(section))
        self.assertTrue(any("invalid 'Status: chosen'" in i for i in issues))

    def test_block_missing_status_line_fails(self):
        section = ("### DECISION-001 limiter backend\n"
                   "Question: q\nOptions: A / B\nRecommended: A\n")
        issues = self._issues(self._design(section))
        self.assertTrue(any("DECISION-001" in i and "missing a 'Status:'" in i for i in issues))

    def test_none_mixed_with_blocks_fails(self):
        section = ("none\n\n### DECISION-001 limiter backend\n"
                   "Question: q\nOptions: A / B\nRecommended: A\nStatus: pending\n")
        issues = self._issues(self._design(section))
        self.assertTrue(any("mixes" in i for i in issues))

    def test_stray_prose_mixed_with_blocks_fails(self):
        section = ("Please decide deployment backend.\n\n"
                   "### DECISION-001 limiter backend\n"
                   "Question: q\nOptions: A / B\nRecommended: A\n"
                   "Status: selected\nSelected: A\nRationale: already approved\n")
        issues = self._issues(self._design(section))
        self.assertTrue(any("outside DECISION blocks" in i for i in issues))

    def test_empty_section_fails(self):
        issues = self._issues(self._design("<!-- a comment only -->\n"))
        self.assertTrue(any("Decision Requests" in i and "empty" in i for i in issues))

    def test_light_design_is_exempt(self):
        content = ("# Design\n\n## Design Summary\ncontent\n\n"
                   "## Chosen Design\n### DES-ARCH-001 arch\ncontent\n\n"
                   "## SPEC Handoff\ncontent\n")
        issues = self._issues(content, tier=self.light)
        self.assertEqual([i for i in issues if "Decision Requests" in i], [])

    def test_pending_pseudo_block_after_valid_block_fails(self):
        """A level-4 'DECISION' pseudo-heading after a valid block must not be absorbed."""
        section = ("### DECISION-001 limiter backend\n"
                   "Question: q\nOptions: A / B\nRecommended: A\n"
                   "Status: selected\nSelected: A\nRationale: approved\n\n"
                   "#### DECISION-002 region choice\n"
                   "Status: pending\n")
        issues = self._issues(self._design(section))
        self.assertTrue(any("R12" in i for i in issues),
                        f"pseudo-block must fail loud: {issues}")

    def test_pending_bullet_inside_block_body_fails(self):
        """A bullet DECISION marker inside a block body must fail loud."""
        section = ("### DECISION-001 limiter backend\n"
                   "Question: q\nOptions: A / B\nRecommended: A\n"
                   "Status: selected\nSelected: A\nRationale: approved\n"
                   "- DECISION-002: choose region. Status: pending\n")
        issues = self._issues(self._design(section))
        self.assertTrue(any("nested 'DECISION-NNN' marker" in i for i in issues),
                        f"bullet marker must fail loud: {issues}")

    def test_pending_checklist_decision_inside_block_body_fails(self):
        """A checklist DECISION marker inside a block body must fail loud."""
        section = ("### DECISION-001 limiter backend\n"
                   "Question: q\nOptions: A / B\nRecommended: A\n"
                   "Status: selected\nSelected: A\nRationale: approved\n"
                   "- [ ] DECISION-002 choose region. Status: pending\n")
        issues = self._issues(self._design(section))
        self.assertTrue(any("nested 'DECISION-NNN' marker" in i for i in issues),
                        f"checklist marker must fail loud: {issues}")

    def test_duplicate_decision_ids_fail(self):
        section = ("### DECISION-001 limiter backend\n"
                   "Question: q\nOptions: A / B\nRecommended: A\n"
                   "Status: selected\nSelected: A\nRationale: approved\n\n"
                   "### DECISION-001 region choice\n"
                   "Question: q\nOptions: A / B\nRecommended: A\n"
                   "Status: selected\nSelected: B\nRationale: latency\n")
        issues = self._issues(self._design(section))
        self.assertTrue(any("Duplicate decision id DECISION-001" in i for i in issues),
                        f"duplicate ids must fail: {issues}")

    def test_multiple_status_lines_fail(self):
        section = ("### DECISION-001 limiter backend\n"
                   "Question: q\nOptions: A / B\nRecommended: A\n"
                   "Status: selected\nSelected: A\nRationale: approved\n"
                   "Status: pending\n")
        issues = self._issues(self._design(section))
        self.assertTrue(any("multiple 'Status:' lines" in i for i in issues),
                        f"multiple Status lines must fail: {issues}")


class TestPlanTaskVerificationPlaceholder(unittest.TestCase):
    def _task(self, verification: str) -> str:
        return (
            "## Tasks\n"
            "### PLAN-TASK-001: do thing\n"
            "Spec References: SPEC-AUTH-001\n"
            "Change Type: modify\n"
            "TDD Applicable: yes\n"
            "Files:\n- src/x.py\n"
            "Skeleton:\n```python\npass\n```\n"
            "Steps:\n- [ ] do\n"
            f"Verification: {verification}\n"
        )

    def test_fill_in_verification_is_flagged(self):
        from tools.workflow_cli.gates import _check_plan_task_verification_placeholders
        self.assertTrue(
            _check_plan_task_verification_placeholders(self._task("<!-- fill in -->"))
        )

    def test_fill_in_guidance_comment_is_flagged(self):
        from tools.workflow_cli.gates import _check_plan_task_verification_placeholders
        self.assertTrue(
            _check_plan_task_verification_placeholders(
                self._task("<!-- fill in: objective pass/fail check -->")
            )
        )

    def test_tbd_verification_is_flagged(self):
        from tools.workflow_cli.gates import _check_plan_task_verification_placeholders
        self.assertTrue(
            _check_plan_task_verification_placeholders(self._task("TBD"))
        )

    def test_objective_verification_passes(self):
        from tools.workflow_cli.gates import _check_plan_task_verification_placeholders
        self.assertFalse(
            _check_plan_task_verification_placeholders(
                self._task("`pytest tests/x.py::test_y` passes")
            )
        )

    def test_quality_gate_reports_verification_placeholder_issue(self):
        import tempfile
        from pathlib import Path
        from tools.workflow_cli.gates import check_quality_gate
        from tools.workflow_cli.models import Stage, TierBase, TierEstimate
        tier = TierEstimate(base=TierBase.LIGHT, modifiers=frozenset())
        with tempfile.TemporaryDirectory() as tmp:
            result = check_quality_gate(
                Path(tmp), Stage.PLAN, tier, [], self._task("<!-- fill in -->")
            )
        self.assertTrue(
            any(
                "Verification contains an unresolved placeholder" in issue
                for issue in result.issues
            )
        )


class TestAmbiguityMarkers(unittest.TestCase):
    def setUp(self):
        from tools.workflow_cli.gates import check_quality_gate
        from tools.workflow_cli.models import Stage, TierBase, TierEstimate
        self.check = check_quality_gate
        self.Stage = Stage
        self.tier = TierEstimate(base=TierBase.STANDARD, modifiers=frozenset())

    def _design_placeholder_issue(self, summary_body: str) -> bool:
        import tempfile
        from pathlib import Path
        content = f"# Design\n\n## Design Summary\n{summary_body}\n"
        with tempfile.TemporaryDirectory() as tmp:
            result = self.check(Path(tmp), self.Stage.DESIGN, self.tier, [], content)
        return any("placeholder" in i.lower() for i in result.issues)

    def test_triple_question_marks_flagged(self):
        self.assertTrue(self._design_placeholder_issue("error handling ???"))

    def test_zh_undecided_marker_flagged(self):
        self.assertTrue(self._design_placeholder_issue("锁策略待定"))

    def test_to_be_determined_flagged(self):
        self.assertTrue(self._design_placeholder_issue("retry count to be determined"))

    def test_normal_prose_not_flagged(self):
        # Hedge-ish prose with none of the markers must NOT raise a placeholder issue.
        self.assertFalse(
            self._design_placeholder_issue("We may add caching later if profiling shows need.")
        )


class TestCheckFinalReviewRecorded(unittest.TestCase):
    """Tests for check_final_review_recorded (SPEC-GATE-001).

    Every test isolates I/O in a tempfile.TemporaryDirectory so it never
    touches the real ~/.req-to-plan or the repo's .req-to-plan.
    """

    def setUp(self):
        from tools.workflow_cli.gates import check_final_review_recorded
        from tools.workflow_cli.output import EXIT_GATE_FAIL
        self.check = check_final_review_recorded
        self.EXIT_GATE_FAIL = EXIT_GATE_FAIL

    def _make_run_dir(self, tmp: str) -> Path:
        run_dir = Path(tmp)
        (run_dir / "execution").mkdir(parents=True, exist_ok=True)
        return run_dir

    def _write_marker(self, run_dir: Path, content: str) -> None:
        (run_dir / "execution" / "final-review.md").write_text(
            content, encoding="utf-8"
        )

    # Case a: missing file → fail
    def test_missing_marker_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = self._make_run_dir(tmp)
            result = self.check(run_dir)
        self.assertFalse(result.passed)
        self.assertEqual(result.exit_code, self.EXIT_GATE_FAIL)
        self.assertTrue(len(result.issues) == 1)
        self.assertIn("not a correctness guarantee", result.issues[0])

    # Case g: approved → pass (exit 0)
    def test_approved_verdict_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = self._make_run_dir(tmp)
            self._write_marker(run_dir, "# Final Review\n\nVerdict: Approved\n")
            result = self.check(run_dir)
        self.assertTrue(result.passed)
        self.assertEqual(result.exit_code, 0)
        self.assertEqual(result.issues, [])

    # Case g: approved case-insensitive
    def test_approved_verdict_case_insensitive_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = self._make_run_dir(tmp)
            self._write_marker(run_dir, "Verdict: APPROVED\n")
            result = self.check(run_dir)
        self.assertTrue(result.passed)
        self.assertEqual(result.exit_code, 0)

    # Case f: changes requested → fail
    def test_changes_requested_verdict_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = self._make_run_dir(tmp)
            self._write_marker(run_dir, "# Review\n\nVerdict: Changes Requested\n")
            result = self.check(run_dir)
        self.assertFalse(result.passed)
        self.assertEqual(result.exit_code, self.EXIT_GATE_FAIL)
        self.assertIn("not a correctness guarantee", result.issues[0])

    # Case e: unsupported value → fail
    def test_unsupported_verdict_value_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = self._make_run_dir(tmp)
            self._write_marker(run_dir, "Verdict: Maybe\n")
            result = self.check(run_dir)
        self.assertFalse(result.passed)
        self.assertEqual(result.exit_code, self.EXIT_GATE_FAIL)
        self.assertIn("not a correctness guarantee", result.issues[0])

    # Case b: symlink → fail
    def test_symlink_marker_fails(self):
        import os
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = self._make_run_dir(tmp)
            # Create a real file elsewhere and symlink to it
            real_file = Path(tmp) / "elsewhere.md"
            real_file.write_text("Verdict: Approved\n", encoding="utf-8")
            (run_dir / "execution" / "final-review.md").symlink_to(real_file)
            result = self.check(run_dir)
        self.assertFalse(result.passed)
        self.assertEqual(result.exit_code, self.EXIT_GATE_FAIL)
        self.assertIn("not a correctness guarantee", result.issues[0])

    # Case c: FIFO (non-regular file) → fail without blocking
    def test_fifo_marker_fails_without_blocking(self):
        import os
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = self._make_run_dir(tmp)
            fifo_path = run_dir / "execution" / "final-review.md"
            os.mkfifo(fifo_path)
            result = self.check(run_dir)
        self.assertFalse(result.passed)
        self.assertEqual(result.exit_code, self.EXIT_GATE_FAIL)
        self.assertIn("not a correctness guarantee", result.issues[0])

    # Case i: Verdict: only inside a code fence → ignored → falls to case d (fail)
    def test_verdict_inside_code_fence_ignored(self):
        content = (
            "# Review\n\n"
            "```\n"
            "Verdict: Approved\n"
            "```\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = self._make_run_dir(tmp)
            self._write_marker(run_dir, content)
            result = self.check(run_dir)
        self.assertFalse(result.passed)
        self.assertEqual(result.exit_code, self.EXIT_GATE_FAIL)
        self.assertIn("not a correctness guarantee", result.issues[0])

    # Case h, CR then Approved → last verdict is Approved → pass
    def test_last_verdict_approved_after_changes_requested_passes(self):
        content = (
            "# Review\n\n"
            "Verdict: Changes Requested\n\n"
            "Fixed the issues.\n\n"
            "Verdict: Approved\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = self._make_run_dir(tmp)
            self._write_marker(run_dir, content)
            result = self.check(run_dir)
        self.assertTrue(result.passed)
        self.assertEqual(result.exit_code, 0)

    # Case h, Approved then CR → last verdict is CR → fail
    def test_last_verdict_changes_requested_after_approved_fails(self):
        content = (
            "# Review\n\n"
            "Verdict: Approved\n\n"
            "Actually found more issues.\n\n"
            "Verdict: Changes Requested\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = self._make_run_dir(tmp)
            self._write_marker(run_dir, content)
            result = self.check(run_dir)
        self.assertFalse(result.passed)
        self.assertEqual(result.exit_code, self.EXIT_GATE_FAIL)
        self.assertIn("not a correctness guarantee", result.issues[0])

    # Case d: regular file present but zero unfenced Verdict: lines → fail
    def test_present_file_no_verdict_line_fails(self):
        content = "# Final Review\n\nAll looks good.\n"
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = self._make_run_dir(tmp)
            self._write_marker(run_dir, content)
            result = self.check(run_dir)
        self.assertFalse(result.passed)
        self.assertEqual(result.exit_code, self.EXIT_GATE_FAIL)
        self.assertIn("not a correctness guarantee", result.issues[0])

    # Canonical missing/not-approved message verbatim check
    def test_missing_marker_canonical_message(self):
        """The missing-file failure message must match the canonical SPEC-HONEST-001 text."""
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = self._make_run_dir(tmp)
            result = self.check(run_dir)
        msg = result.issues[0]
        self.assertIn("Final whole-branch review not approved", msg)
        self.assertIn("execution/final-review.md is missing", msg)
        self.assertIn("not 'Approved'", msg)
        self.assertIn("Presence check on the review audit trail", msg)
        self.assertIn("not a correctness guarantee", msg)
        self.assertIn("Record 'Verdict: Approved'", msg)
        self.assertIn("re-run with --force to archive an abandoned run", msg)

    # All failure messages must carry the disclaimer
    def test_all_failure_paths_carry_disclaimer(self):
        """Every failure case must carry 'not a correctness guarantee'."""
        import os
        cases = {}

        with tempfile.TemporaryDirectory() as tmp:
            run_dir = self._make_run_dir(tmp)
            cases["missing"] = self.check(run_dir)

        with tempfile.TemporaryDirectory() as tmp:
            run_dir = self._make_run_dir(tmp)
            self._write_marker(run_dir, "# Review\n\nVerdict: Changes Requested\n")
            cases["changes_requested"] = self.check(run_dir)

        with tempfile.TemporaryDirectory() as tmp:
            run_dir = self._make_run_dir(tmp)
            self._write_marker(run_dir, "Verdict: Maybe\n")
            cases["unsupported"] = self.check(run_dir)

        with tempfile.TemporaryDirectory() as tmp:
            run_dir = self._make_run_dir(tmp)
            real_file = Path(tmp) / "real.md"
            real_file.write_text("Verdict: Approved\n", encoding="utf-8")
            (run_dir / "execution" / "final-review.md").symlink_to(real_file)
            cases["symlink"] = self.check(run_dir)

        with tempfile.TemporaryDirectory() as tmp:
            run_dir = self._make_run_dir(tmp)
            fifo_path = run_dir / "execution" / "final-review.md"
            os.mkfifo(fifo_path)
            cases["fifo"] = self.check(run_dir)

        with tempfile.TemporaryDirectory() as tmp:
            run_dir = self._make_run_dir(tmp)
            self._write_marker(run_dir, "# Review\n\nAll looks good.\n")
            cases["no_verdict"] = self.check(run_dir)

        for name, result in cases.items():
            with self.subTest(case=name):
                self.assertFalse(result.passed)
                self.assertEqual(result.exit_code, self.EXIT_GATE_FAIL)
                self.assertTrue(
                    any("not a correctness guarantee" in issue for issue in result.issues),
                    f"case {name!r}: 'not a correctness guarantee' missing in {result.issues}",
                )


if __name__ == "__main__":
    unittest.main()

"""Tests for tier keyword bank and tier estimator (Task 6)."""
from __future__ import annotations

import unittest
from pathlib import Path

from tools.workflow_cli.tier import (
    scan_keywords,
    compute_floor,
    build_evidence_block,
    estimate_tier,
    _flatten_keywords,
    _match_keyword,
    _normalize,
)
from tools.workflow_cli.models import TierBase, TierModifier, TierEstimate, EvidenceBlock
from tools.workflow_cli.repo_baseline import RepoBaseline
from tools.workflow_cli.link_expander import LinkExpansionResult, LinkStatus


class TestFlattenKeywords(unittest.TestCase):
    def test_flat_lists(self):
        result = _flatten_keywords({"en": ["a", "b"], "zh": ["c"]})
        self.assertEqual(sorted(result), ["a", "b", "c"])

    def test_nested_dict(self):
        result = _flatten_keywords({"verbs": {"en": ["delete"], "zh": ["删除"]}, "nouns": {"en": ["data"]}})
        self.assertIn("delete", result)
        self.assertIn("删除", result)
        self.assertIn("data", result)

    def test_empty(self):
        self.assertEqual(_flatten_keywords({}), [])

    def test_mixed(self):
        result = _flatten_keywords({"signals": ["x", "y"]})
        self.assertEqual(sorted(result), ["x", "y"])


class TestMatchKeyword(unittest.TestCase):
    def _normalized(self, text: str) -> str:
        return _normalize(text)

    def test_single_word_match(self):
        text = "we need to migrate the db"
        norm = self._normalized(text)
        self.assertTrue(_match_keyword("migrate", text, norm))

    def test_single_word_boundary(self):
        # "migration" (word boundary) matches when the exact word appears
        text = "no migration here"
        norm = self._normalized(text)
        self.assertTrue(_match_keyword("migration", text, norm))

    def test_single_word_no_false_match(self):
        # "migrat" should NOT match "migrate" as standalone word boundary
        text = "we need to migrate the db"
        norm = self._normalized(text)
        self.assertFalse(_match_keyword("migrat", text, norm))

    def test_chinese_substring(self):
        text = "删除用户数据"
        norm = self._normalized(text)
        self.assertTrue(_match_keyword("删除", text, norm))

    def test_chinese_no_match(self):
        text = "查询用户数据"
        norm = self._normalized(text)
        self.assertFalse(_match_keyword("删除", text, norm))

    def test_multiword_phrase(self):
        text = "delete production data right now"
        norm = self._normalized(text)
        self.assertTrue(_match_keyword("production", text, norm))

    def test_multiword_phrase_match(self):
        text = "we should remove data from the system"
        norm = self._normalized(text)
        self.assertTrue(_match_keyword("remove data", text, norm))

    def test_hyphen_normalization(self):
        # "reimplement" should match text containing "re-implement" (hyphen variants normalized)
        text = "we will re-implement the service"
        norm = self._normalized(text)
        # The keyword "reimplement" should match "re-implement" after hyphen stripping
        self.assertTrue(_match_keyword("reimplement", text, norm))

    def test_case_insensitive(self):
        text = "We Need to MIGRATE the DB"
        norm = self._normalized(text)
        self.assertTrue(_match_keyword("migrate", text, norm))


class TestScanKeywords(unittest.TestCase):
    def test_migration_english(self):
        hits = scan_keywords("migrate the database to PostgreSQL")
        self.assertIn(TierModifier.MIGRATION, hits)

    def test_safety_english(self):
        hits = scan_keywords("delete production data")
        self.assertIn(TierModifier.SAFETY, hits)

    def test_dependency_english(self):
        hits = scan_keywords("integrate third-party SDK into the app")
        self.assertIn(TierModifier.DEPENDENCY, hits)

    def test_migration_and_scope_expanding(self):
        hits = scan_keywords("rewrite entire system")
        self.assertIn(TierModifier.MIGRATION, hits)
        self.assertIn(TierModifier.SCOPE_EXPANDING, hits)

    def test_clean_requirement_no_hits(self):
        # Use a truly neutral requirement with no keywords from any modifier section
        hits = scan_keywords("add rate limiting to the new endpoint")
        self.assertEqual(hits, {})

    def test_migration_chinese(self):
        hits = scan_keywords("迁移到新数据库")
        self.assertIn(TierModifier.MIGRATION, hits)

    def test_safety_chinese(self):
        hits = scan_keywords("删除用户数据")
        self.assertIn(TierModifier.SAFETY, hits)

    def test_scope_expanding_english(self):
        hits = scan_keywords("refactor entire codebase")
        self.assertIn(TierModifier.SCOPE_EXPANDING, hits)

    def test_returns_matched_keywords(self):
        hits = scan_keywords("migrate the database to PostgreSQL")
        matched = hits.get(TierModifier.MIGRATION, [])
        self.assertTrue(len(matched) > 0)
        self.assertTrue(any("migrat" in kw.lower() for kw in matched))

    def test_no_false_cross_project_on_clean(self):
        hits = scan_keywords("add a new endpoint to the API")
        self.assertNotIn(TierModifier.MIGRATION, hits)
        self.assertNotIn(TierModifier.SAFETY, hits)


class TestComputeFloor(unittest.TestCase):
    def test_empty_inputs_gives_light(self):
        floor = compute_floor({}, RepoBaseline(), [], "")
        self.assertEqual(floor.base, TierBase.LIGHT)
        self.assertEqual(floor.modifiers, frozenset())

    def test_migration_modifier_gives_standard(self):
        floor = compute_floor({TierModifier.MIGRATION: ["migrate"]}, RepoBaseline(), [], "")
        self.assertEqual(floor.base, TierBase.STANDARD)
        self.assertIn(TierModifier.MIGRATION, floor.modifiers)

    def test_large_loc_gives_standard(self):
        repo = RepoBaseline(loc=15000)
        floor = compute_floor({}, repo, [], "")
        self.assertEqual(floor.base, TierBase.STANDARD)

    def test_monorepo_gives_standard(self):
        repo = RepoBaseline(is_monorepo=True)
        floor = compute_floor({}, repo, [], "")
        self.assertEqual(floor.base, TierBase.STANDARD)

    def test_many_modules_gives_standard(self):
        repo = RepoBaseline(module_count=10)
        floor = compute_floor({}, repo, [], "")
        self.assertEqual(floor.base, TierBase.STANDARD)

    def test_scope_expanding_upgrades_to_standard(self):
        floor = compute_floor({TierModifier.SCOPE_EXPANDING: ["entire"]}, RepoBaseline(), [], "")
        self.assertEqual(floor.base, TierBase.STANDARD)
        self.assertIn(TierModifier.SCOPE_EXPANDING, floor.modifiers)

    def test_cross_language_repo_adds_cross_project_modifier(self):
        repo = RepoBaseline(cross_language_refs=["Python", "TypeScript"])
        floor = compute_floor({}, repo, [], "")
        self.assertIn(TierModifier.CROSS_PROJECT, floor.modifiers)

    def test_unreachable_link_gives_standard(self):
        link_results = [
            LinkExpansionResult(url="https://example.com/spec", status=LinkStatus.UNREACHABLE, error="timeout")
        ]
        floor = compute_floor({}, RepoBaseline(), link_results, "")
        self.assertEqual(floor.base, TierBase.STANDARD)

    def test_requires_auth_link_gives_standard(self):
        link_results = [
            LinkExpansionResult(url="https://private.example.com/doc", status=LinkStatus.REQUIRES_AUTH)
        ]
        floor = compute_floor({}, RepoBaseline(), link_results, "")
        self.assertEqual(floor.base, TierBase.STANDARD)

    def test_multiple_modifiers(self):
        hits = {
            TierModifier.MIGRATION: ["migrate"],
            TierModifier.SAFETY: ["delete", "production"],
        }
        floor = compute_floor(hits, RepoBaseline(), [], "")
        self.assertIn(TierModifier.MIGRATION, floor.modifiers)
        self.assertIn(TierModifier.SAFETY, floor.modifiers)

    def test_loc_at_threshold_is_light(self):
        # Exactly 10000 is not above threshold
        repo = RepoBaseline(loc=10000)
        floor = compute_floor({}, repo, [], "")
        self.assertEqual(floor.base, TierBase.LIGHT)

    def test_loc_above_threshold_is_standard(self):
        repo = RepoBaseline(loc=10001)
        floor = compute_floor({}, repo, [], "")
        self.assertEqual(floor.base, TierBase.STANDARD)

    def test_returns_tier_estimate_type(self):
        floor = compute_floor({}, RepoBaseline(), [], "")
        self.assertIsInstance(floor, TierEstimate)


class TestBuildEvidenceBlock(unittest.TestCase):
    def _make_floor(self) -> TierEstimate:
        return TierEstimate(base=TierBase.LIGHT, modifiers=frozenset())

    def test_returns_evidence_block(self):
        floor = self._make_floor()
        ev = build_evidence_block({}, RepoBaseline(), [], floor)
        self.assertIsInstance(ev, EvidenceBlock)

    def test_confirm_status_pending(self):
        floor = self._make_floor()
        ev = build_evidence_block({}, RepoBaseline(), [], floor)
        self.assertEqual(ev.confirm_status, "pending")

    def test_floor_set(self):
        floor = self._make_floor()
        ev = build_evidence_block({}, RepoBaseline(), [], floor)
        self.assertEqual(ev.floor, floor)

    def test_keywords_hit_populated(self):
        hits = {TierModifier.MIGRATION: ["migrate", "migration"]}
        floor = self._make_floor()
        ev = build_evidence_block(hits, RepoBaseline(), [], floor)
        self.assertIn("migrate", ev.keywords_hit)
        self.assertIn("migration", ev.keywords_hit)

    def test_repo_baseline_summary_set(self):
        floor = self._make_floor()
        ev = build_evidence_block({}, RepoBaseline(loc=500, module_count=3), [], floor)
        self.assertIsNotNone(ev.repo_baseline_summary)
        self.assertIn("500", ev.repo_baseline_summary)

    def test_linked_context_none_when_no_links(self):
        floor = self._make_floor()
        ev = build_evidence_block({}, RepoBaseline(), [], floor)
        self.assertEqual(ev.linked_context, "none")

    def test_linked_context_populated(self):
        floor = self._make_floor()
        link_results = [
            LinkExpansionResult(
                url="https://example.com",
                status=LinkStatus.REACHABLE,
                content_preview="some spec content",
            )
        ]
        ev = build_evidence_block({}, RepoBaseline(), link_results, floor)
        self.assertIn("https://example.com", ev.linked_context)

    def test_scope_signals_extracted(self):
        hits = {TierModifier.SCOPE_EXPANDING: ["entire", "all of"]}
        floor = self._make_floor()
        ev = build_evidence_block(hits, RepoBaseline(), [], floor)
        self.assertIn("entire", ev.scope_signals)

    def test_escalation_candidates_exclude_scope_expanding(self):
        hits = {
            TierModifier.MIGRATION: ["migrate"],
            TierModifier.SCOPE_EXPANDING: ["entire"],
        }
        floor = self._make_floor()
        ev = build_evidence_block(hits, RepoBaseline(), [], floor)
        self.assertIn("migration", ev.escalation_candidates)
        self.assertNotIn("scope_expanding", ev.escalation_candidates)

    def test_validate_for_lock_passes(self):
        floor = self._make_floor()
        ev = build_evidence_block({}, RepoBaseline(), [], floor)
        # Should not raise
        ev.validate_for_lock()


class TestEstimateTier(unittest.TestCase):
    def test_clean_requirement_returns_light(self):
        # Use a truly neutral requirement with no keywords from any modifier section
        floor, ev = estimate_tier("add rate limiting to the new endpoint")
        self.assertEqual(floor.base, TierBase.LIGHT)
        self.assertEqual(floor.modifiers, frozenset())

    def test_migration_requirement_has_modifier(self):
        floor, ev = estimate_tier("migrate the database to PostgreSQL")
        self.assertIn(TierModifier.MIGRATION, floor.modifiers)

    def test_returns_tuple(self):
        result = estimate_tier("add a new feature")
        self.assertIsInstance(result, tuple)
        self.assertEqual(len(result), 2)

    def test_returns_tier_estimate_and_evidence(self):
        floor, ev = estimate_tier("add login rate limiting")
        self.assertIsInstance(floor, TierEstimate)
        self.assertIsInstance(ev, EvidenceBlock)

    def test_evidence_confirm_status_pending(self):
        _, ev = estimate_tier("add login rate limiting")
        self.assertEqual(ev.confirm_status, "pending")

    def test_evidence_floor_set(self):
        floor, ev = estimate_tier("add login rate limiting")
        self.assertIsNotNone(ev.floor)
        self.assertEqual(ev.floor, floor)

    def test_validate_for_lock_passes(self):
        _, ev = estimate_tier("add login rate limiting")
        # Should not raise
        ev.validate_for_lock()

    def test_with_repo_path_none(self):
        floor, ev = estimate_tier("add a feature", repo_path=None)
        self.assertIsInstance(floor, TierEstimate)

    def test_with_nonexistent_repo_path(self):
        floor, ev = estimate_tier("add a feature", repo_path=Path("/nonexistent/path"))
        self.assertIsInstance(floor, TierEstimate)

    def test_link_results_passed_through(self):
        link_results = [
            LinkExpansionResult(url="https://example.com/spec", status=LinkStatus.UNREACHABLE, error="timeout")
        ]
        floor, ev = estimate_tier("add a feature", link_results=link_results)
        self.assertEqual(floor.base, TierBase.STANDARD)

    def test_safety_requirement(self):
        floor, ev = estimate_tier("delete all production data")
        self.assertIn(TierModifier.SAFETY, floor.modifiers)
        self.assertEqual(floor.base, TierBase.STANDARD)

    def test_dependency_requirement(self):
        floor, ev = estimate_tier("integrate the third-party payment SDK")
        self.assertIn(TierModifier.DEPENDENCY, floor.modifiers)

    def test_chinese_migration(self):
        floor, ev = estimate_tier("迁移数据库到新系统")
        self.assertIn(TierModifier.MIGRATION, floor.modifiers)


if __name__ == "__main__":
    unittest.main()

import unittest
from tools.workflow_cli.models import Stage, TierBase


class TestStageSchema(unittest.TestCase):
    def test_required_headings_brief_standard_is_superset_of_light(self):
        from tools.workflow_cli.stage_schema import required_headings
        light = set(required_headings(Stage.REQUIREMENT_BRIEF, TierBase.LIGHT))
        standard = set(required_headings(Stage.REQUIREMENT_BRIEF, TierBase.STANDARD))
        self.assertTrue(light.issubset(standard))
        self.assertIn("## In-Scope", light)
        self.assertIn("## Out-of-Scope", light)

    def test_spec_heading_matches_existing_external_docs_gate(self):
        from tools.workflow_cli.stage_schema import required_headings
        headings = required_headings(Stage.SPEC, TierBase.STANDARD)
        self.assertIn("## External Documentation Checked", headings)

    def test_unschemaed_stage_returns_empty(self):
        from tools.workflow_cli.stage_schema import required_headings
        self.assertEqual(required_headings(Stage.RAW_REQUIREMENT, TierBase.LIGHT), [])

    def test_standard_design_requires_decision_requests(self):
        from tools.workflow_cli.models import Stage, TierBase
        from tools.workflow_cli.stage_schema import required_headings
        self.assertIn("## Decision Requests", required_headings(Stage.DESIGN, TierBase.STANDARD))
        self.assertNotIn("## Decision Requests", required_headings(Stage.DESIGN, TierBase.LIGHT))

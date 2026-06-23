import unittest
from tools.workflow_cli.models import Stage, TierBase


class TestStageTemplates(unittest.TestCase):
    def test_template_contains_every_required_heading(self):
        from tools.workflow_cli.stage_templates import template_for
        from tools.workflow_cli.stage_schema import required_headings
        text = template_for(Stage.REQUIREMENT_BRIEF, TierBase.STANDARD)
        for h in required_headings(Stage.REQUIREMENT_BRIEF, TierBase.STANDARD):
            self.assertIn(h, text)

    def test_template_includes_static_trace_skeleton(self):
        from tools.workflow_cli.stage_templates import template_for
        text = template_for(Stage.REQUIREMENT_BRIEF, TierBase.LIGHT)
        self.assertIn("## Trace", text)

    def test_brief_template_seeds_scope_ids(self):
        from tools.workflow_cli.stage_templates import template_for
        text = template_for(Stage.REQUIREMENT_BRIEF, TierBase.STANDARD)
        self.assertIn("SCOPE-IN-001", text)
        self.assertIn("SCOPE-OUT-001", text)

    def test_templates_seed_native_stage_ids(self):
        from tools.workflow_cli.stage_templates import template_for
        self.assertIn("RISK-", template_for(Stage.RISK_DISCOVERY, TierBase.STANDARD))
        self.assertIn("DES-", template_for(Stage.DESIGN, TierBase.STANDARD))
        self.assertIn("SPEC-", template_for(Stage.SPEC, TierBase.STANDARD))

    def test_plan_template_seeds_required_task_fields(self):
        from tools.workflow_cli.stage_templates import template_for
        text = template_for(Stage.PLAN, TierBase.STANDARD)
        self.assertIn("### PLAN-TASK-001", text)
        for field in ("Spec References:", "Change Type:", "Files:", "Verification:"):
            self.assertIn(field, text)

    def test_unschemaed_stage_yields_minimal_template(self):
        from tools.workflow_cli.stage_templates import template_for
        text = template_for(Stage.RAW_REQUIREMENT, TierBase.LIGHT)
        self.assertIsInstance(text, str)

    def test_standard_design_template_seeds_decision_requests(self):
        from tools.workflow_cli.models import Stage, TierBase
        from tools.workflow_cli.stage_templates import template_for
        standard = template_for(Stage.DESIGN, TierBase.STANDARD)
        self.assertIn("## Decision Requests", standard)
        self.assertIn("`none`", standard)          # guidance mentions the none escape
        self.assertIn("Status: pending", standard)  # fenced example shows the contract
        self.assertNotIn("## Decision Requests", template_for(Stage.DESIGN, TierBase.LIGHT))

    def test_plan_template_verification_is_a_placeholder_until_filled(self):
        from tools.workflow_cli.stage_templates import template_for
        from tools.workflow_cli.gates import _check_plan_task_verification_placeholders
        text = template_for(Stage.PLAN, TierBase.STANDARD)
        # The seeded Verification must still trip the gate so an untouched
        # template cannot pass.
        self.assertTrue(_check_plan_task_verification_placeholders(text))

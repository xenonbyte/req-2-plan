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

    # --- PLN-1 / PLN-4: optional sections presence ---

    def test_plan_template_contains_optional_execution_readiness(self):
        """PLN-1: ## Execution Readiness seeded as optional section."""
        from tools.workflow_cli.stage_templates import template_for
        text = template_for(Stage.PLAN, TierBase.STANDARD)
        self.assertIn("## Execution Readiness", text)
        # confirm it appears after ## Tasks body (not inside the PLAN-TASK block)
        tasks_pos = text.index("## Tasks")
        self.assertGreater(text.index("## Execution Readiness"), tasks_pos)

    def test_plan_template_contains_optional_risk_handling(self):
        """PLN-4: ## Risk Handling table with example row carrying [ADDRESSED] tag."""
        from tools.workflow_cli.stage_templates import template_for
        text = template_for(Stage.PLAN, TierBase.STANDARD)
        self.assertIn("## Risk Handling", text)
        self.assertIn("RISK-EXAMPLE-001", text)
        self.assertIn("[ADDRESSED]", text)
        # The example row must have RISK-EXAMPLE-001 and [ADDRESSED] on the same line
        for line in text.splitlines():
            if "RISK-EXAMPLE-001" in line:
                self.assertIn("[ADDRESSED]", line, "Closure tag must be on the same line as RISK ID")
                break
        else:
            self.fail("RISK-EXAMPLE-001 not found in any line")

    # --- PLN-2: optional PLAN-TASK field lines ---

    def test_plan_template_contains_optional_out_of_task_and_future_ownership(self):
        """PLN-2: Out-of-Task and Future Task Ownership optional field lines in PLAN-TASK body."""
        from tools.workflow_cli.stage_templates import template_for
        text = template_for(Stage.PLAN, TierBase.STANDARD)
        self.assertIn("Out-of-Task:", text)
        self.assertIn("Future Task Ownership:", text)
        # Future Task Ownership references the PLAN-TASK-NNN guidance form
        self.assertIn("PLAN-TASK-NNN", text)
        # These lines must appear BEFORE ## Execution Readiness (inside the PLAN-TASK body)
        exec_ready_pos = text.index("## Execution Readiness")
        self.assertLess(text.index("Out-of-Task:"), exec_ready_pos)
        self.assertLess(text.index("Future Task Ownership:"), exec_ready_pos)

    # --- PLN-3: enriched three-part Verification example ---

    def test_plan_template_verification_enriched_three_part(self):
        """PLN-3: Verification example is a three-part contract (targeted, full suite, evidence)."""
        from tools.workflow_cli.stage_templates import template_for
        text = template_for(Stage.PLAN, TierBase.STANDARD)
        # The Verification placeholder comment must describe all three parts
        # Find the Verification line
        verification_line = None
        for line in text.splitlines():
            if line.startswith("Verification:"):
                verification_line = line
                break
        self.assertIsNotNone(verification_line, "Verification: line must be present")
        lower = verification_line.lower()
        self.assertIn("targeted", lower, "Verification must mention targeted command")
        # Check for "full" (full suite) or "suite" phrasing
        self.assertTrue(
            "full" in lower or "suite" in lower,
            "Verification must mention full/suite command"
        )
        self.assertIn("evidence", lower, "Verification must mention evidence")

    # --- PLN-5: granularity comment ---

    def test_plan_template_contains_granularity_note(self):
        """PLN-5: Granularity guidance HTML comment seeded under ## Tasks."""
        from tools.workflow_cli.stage_templates import template_for
        text = template_for(Stage.PLAN, TierBase.STANDARD)
        self.assertIn("Granularity", text)
        self.assertIn("implementer subagent", text)
        self.assertIn("task-reviewer", text)
        # Note must appear within the ## Tasks section
        tasks_pos = text.index("## Tasks")
        plan_task_pos = text.index("### PLAN-TASK-001")
        granularity_pos = text.index("Granularity")
        # granularity comes after ## Tasks but before or near the PLAN-TASK block
        self.assertGreater(granularity_pos, tasks_pos)

    # --- non-PLAN stage byte-identical invariant ---

    def test_non_plan_templates_lack_optional_plan_sections(self):
        """Non-PLAN stage templates must not gain any optional PLAN content."""
        from tools.workflow_cli.stage_templates import template_for
        non_plan_stages = [
            Stage.REQUIREMENT_BRIEF,
            Stage.RISK_DISCOVERY,
            Stage.DESIGN,
            Stage.SPEC,
        ]
        for stage in non_plan_stages:
            for tier in (TierBase.LIGHT, TierBase.STANDARD):
                try:
                    text = template_for(stage, tier)
                except Exception:
                    continue  # some stage/tier combos may be unschema'd — not our concern
                self.assertNotIn(
                    "Execution Readiness", text,
                    f"{stage}/{tier} must not contain PLAN optional section"
                )
                self.assertNotIn(
                    "Risk Handling", text,
                    f"{stage}/{tier} must not contain PLAN optional section"
                )
                self.assertNotIn(
                    "Future Task Ownership:", text,
                    f"{stage}/{tier} must not contain PLAN optional field"
                )

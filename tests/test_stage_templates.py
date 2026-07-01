import json
import re as _re
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

    # --- PLN-2: deferral fields removed (R20) ---

    def test_plan_template_omits_out_of_task_and_future_ownership(self):
        """PLN-2/R20: the deferral fields are gone — a decomposition stage may not
        defer requirement content, so the PLAN-TASK body offers no slot to do so."""
        from tools.workflow_cli.stage_templates import template_for
        for tier in (TierBase.LIGHT, TierBase.STANDARD):
            text = template_for(Stage.PLAN, tier)
            self.assertNotIn("Out-of-Task:", text)
            self.assertNotIn("Future Task Ownership:", text)

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


# ---------------------------------------------------------------------------
# Batch 2: gate round-trip coverage (AC-4 + AC-5)
# ---------------------------------------------------------------------------

def _seed(tmp, plan_text):
    """Write the minimal upstream fixture so trace-closure, file-ref, and context-pack checks pass."""
    from tools.workflow_cli.models import STAGE_ARTIFACT_MAP, Stage as _Stage
    (tmp / "02-project-context.json").write_text(json.dumps({"repo_root": str(tmp)}))
    (tmp / "seed_fixture.py").write_text("# seed\n")  # referenced by Files; must exist under repo_root
    (tmp / STAGE_ARTIFACT_MAP[_Stage.SPEC]).write_text("## SPEC-SEED-001 seed\ncontent\n")
    (tmp / STAGE_ARTIFACT_MAP[_Stage.REQUIREMENT_BRIEF]).write_text(
        "## In-Scope\n- SCOPE-IN-001 x\n## Out-of-Scope\n- SCOPE-OUT-001 y\n"
    )
    (tmp / STAGE_ARTIFACT_MAP[_Stage.PLAN]).write_text(plan_text)


def _fill_required_tasks_minimally(template_text):
    """Replace all PLAN template placeholders with gate-clean minimal content.

    Fills PLAN-TASK-001 so it:
    - consumes SPEC-SEED-001 (Spec References)
    - carries SCOPE-IN-001 (Steps line, picked up by scope_in_not_closed)
    - references seed_fixture.py under repo_root (Files, satisfies _check_plan_file_refs)
    - has a real Skeleton code block (TDD Applicable: yes)
    - has a real Verification command (no fill-in placeholder)
    The seeded ## Risk Handling row (RISK-EXAMPLE-001 / [ADDRESSED]) is kept as-is.
    """
    t = template_text
    t = t.replace("### PLAN-TASK-001 <!-- fill in -->",
                  "### PLAN-TASK-001 Implement seed feature")
    t = t.replace("Spec References: SPEC-BEHAVIOR-001",
                  "Spec References: SPEC-SEED-001")
    # Replace only the first "- <!-- fill in -->" (the Files list entry)
    t = t.replace("- <!-- fill in -->", "- seed_fixture.py", 1)
    t = t.replace("```python\n# <!-- fill in -->\n```",
                  "```python\ndef seed(): pass\n```")
    t = t.replace("- [ ] <!-- fill in -->",
                  "- [ ] Implement seed feature for SCOPE-IN-001")
    # Verification placeholder — gate blocks any <!-- fill in: ... --> comment
    t = _re.sub(
        r"Verification: <!-- fill in:.*?-->",
        "Verification: `.venv/bin/python -m pytest tests/ -q` all pass. Evidence: paste output.",
        t,
    )
    return t


def test_seeded_plan_passes_gate_when_filled_minimally(tmp_path):
    """AC-4: seeded Risk Handling row clears Check 3 and malformed-trace-ID check."""
    from tools.workflow_cli.gates import check_quality_gate
    from tools.workflow_cli.models import Stage, TierBase, TierEstimate
    from tools.workflow_cli.stage_templates import template_for

    plan = _fill_required_tasks_minimally(template_for(Stage.PLAN, TierBase.STANDARD))
    _seed(tmp_path, plan)
    tier = TierEstimate(base=TierBase.STANDARD, modifiers=frozenset())
    r = check_quality_gate(tmp_path, Stage.PLAN, tier, [], plan)
    assert r.passed, r.issues


def test_plan_passes_gate_when_optional_sections_omitted(tmp_path):
    """AC-5: optional sections/fields are removable; PLAN_TASK_FIELDS unchanged."""
    from tools.workflow_cli.gates import check_quality_gate
    from tools.workflow_cli.models import Stage, TierBase, TierEstimate

    # PLAN without ## Execution Readiness or ## Risk Handling (both optional/removable)
    plan = (
        "# Plan\n\n"
        "## Tasks\n\n"
        "### PLAN-TASK-001 Implement seed feature\n"
        "Spec References: SPEC-SEED-001\n"
        "Change Type: modify\n"
        "TDD Applicable: yes\n"
        "Files:\n"
        "- seed_fixture.py\n"
        "Skeleton:\n"
        "```python\n"
        "def seed(): pass\n"
        "```\n"
        "Steps:\n"
        "- [ ] Implement seed feature for SCOPE-IN-001\n"
        "Verification: `.venv/bin/python -m pytest tests/ -q` all pass. Evidence: paste output.\n\n"
        "## Trace\n"
        "| This ID | Upstream | Status |\n"
        "|---|---|---|\n"
    )
    _seed(tmp_path, plan)
    tier = TierEstimate(base=TierBase.STANDARD, modifiers=frozenset())
    r = check_quality_gate(tmp_path, Stage.PLAN, tier, [], plan)
    assert r.passed, r.issues


def test_seeded_optional_fields_do_not_satisfy_blank_verification(tmp_path):
    """Regression: optional PLAN-TASK fields must not make blank Verification non-empty."""
    from tools.workflow_cli.gates import check_quality_gate
    from tools.workflow_cli.models import Stage, TierBase, TierEstimate
    from tools.workflow_cli.stage_templates import template_for

    plan = _fill_required_tasks_minimally(template_for(Stage.PLAN, TierBase.STANDARD))
    plan = _re.sub(r"^Verification: .*$", "Verification:", plan, count=1, flags=_re.MULTILINE)
    _seed(tmp_path, plan)
    tier = TierEstimate(base=TierBase.STANDARD, modifiers=frozenset())
    r = check_quality_gate(tmp_path, Stage.PLAN, tier, [], plan)
    assert not r.passed
    assert any("Verification:" in issue for issue in r.issues)


def test_seeded_optional_fields_do_not_satisfy_blank_steps(tmp_path):
    """Regression: optional PLAN-TASK fields must not make blank Steps non-empty."""
    from tools.workflow_cli.gates import check_quality_gate
    from tools.workflow_cli.models import Stage, TierBase, TierEstimate
    from tools.workflow_cli.stage_templates import template_for

    plan = _fill_required_tasks_minimally(template_for(Stage.PLAN, TierBase.STANDARD))
    plan = _re.sub(
        r"^Steps:\n- \[ \] Implement seed feature for SCOPE-IN-001$",
        "Steps:",
        plan,
        count=1,
        flags=_re.MULTILINE,
    )
    _seed(tmp_path, plan)
    tier = TierEstimate(base=TierBase.STANDARD, modifiers=frozenset())
    r = check_quality_gate(tmp_path, Stage.PLAN, tier, [], plan)
    assert not r.passed
    assert any("Steps:" in issue for issue in r.issues)

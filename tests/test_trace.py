import tempfile
import unittest
from pathlib import Path
from tools.workflow_cli.models import Stage, STAGE_ARTIFACT_MAP


class TestTrace(unittest.TestCase):
    def _run_dir(self, tmp, spec_body, plan_body):
        run_dir = Path(tmp)
        (run_dir / STAGE_ARTIFACT_MAP[Stage.SPEC]).write_text(spec_body, encoding="utf-8")
        (run_dir / STAGE_ARTIFACT_MAP[Stage.PLAN]).write_text(plan_body, encoding="utf-8")
        return run_dir

    def test_spec_consumed_by_plan_has_no_gap(self):
        from tools.workflow_cli.trace import spec_ids_not_consumed
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = self._run_dir(tmp, "## SPEC-AUTH-001 login\nbehavior\n",
                                    "### PLAN-TASK-001\nSpec References: SPEC-AUTH-001\n")
            self.assertEqual(spec_ids_not_consumed(run_dir), [])

    def test_spec_not_referenced_by_plan_is_a_gap(self):
        from tools.workflow_cli.trace import spec_ids_not_consumed
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = self._run_dir(tmp, "## SPEC-AUTH-001 login\nbehavior\n",
                                    "### PLAN-TASK-001\nSpec References: SPEC-OTHER-999\n")
            self.assertEqual(spec_ids_not_consumed(run_dir), ["SPEC-AUTH-001"])

    def test_spec_mentioned_outside_plan_task_is_still_a_gap(self):
        from tools.workflow_cli.trace import spec_ids_not_consumed
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = self._run_dir(tmp, "## SPEC-AUTH-001 login\nbehavior\n",
                                    "## Notes\nMentions SPEC-AUTH-001\n\n### PLAN-TASK-001\nSpec References: SPEC-OTHER-999\n")
            self.assertEqual(spec_ids_not_consumed(run_dir), ["SPEC-AUTH-001"])

    def test_scope_in_not_carried_downstream_is_a_gap(self):
        from tools.workflow_cli.trace import check_trace_closure
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            (run_dir / STAGE_ARTIFACT_MAP[Stage.REQUIREMENT_BRIEF]).write_text(
                "## In-Scope\n- SCOPE-IN-001 rate limit per IP\n", encoding="utf-8")
            (run_dir / STAGE_ARTIFACT_MAP[Stage.SPEC]).write_text(
                "## Behavior Contracts\nno scope ref here\n", encoding="utf-8")
            self.assertTrue(any("SCOPE-IN-001" in i for i in check_trace_closure(run_dir)))

    def test_scope_in_carried_into_consumed_spec_closes(self):
        from tools.workflow_cli.trace import check_trace_closure
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            (run_dir / STAGE_ARTIFACT_MAP[Stage.REQUIREMENT_BRIEF]).write_text(
                "## In-Scope\n- SCOPE-IN-001 rate limit per IP\n", encoding="utf-8")
            (run_dir / STAGE_ARTIFACT_MAP[Stage.SPEC]).write_text(
                "## SPEC-RATE-001\nimplements SCOPE-IN-001\n", encoding="utf-8")
            (run_dir / STAGE_ARTIFACT_MAP[Stage.PLAN]).write_text(
                "## Tasks\n### PLAN-TASK-001\nSpec References: SPEC-RATE-001\n", encoding="utf-8")
            self.assertFalse(any("SCOPE-IN-001" in i for i in check_trace_closure(run_dir)))

    def test_scope_in_carried_only_to_unconsumed_spec_is_a_gap(self):
        from tools.workflow_cli.trace import check_trace_closure
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            (run_dir / STAGE_ARTIFACT_MAP[Stage.REQUIREMENT_BRIEF]).write_text(
                "## In-Scope\n- SCOPE-IN-001 rate limit per IP\n", encoding="utf-8")
            (run_dir / STAGE_ARTIFACT_MAP[Stage.SPEC]).write_text(
                "## SPEC-RATE-001\nimplements SCOPE-IN-001\n", encoding="utf-8")
            (run_dir / STAGE_ARTIFACT_MAP[Stage.PLAN]).write_text(
                "## Tasks\n### PLAN-TASK-001\nSpec References: SPEC-OTHER-999\n", encoding="utf-8")
            self.assertTrue(any("SCOPE-IN-001" in i for i in check_trace_closure(run_dir)))

    def test_unclosed_risk_is_a_gap(self):
        from tools.workflow_cli.trace import check_trace_closure
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            (run_dir / STAGE_ARTIFACT_MAP[Stage.RISK_DISCOVERY]).write_text(
                "## RISK-SEC-001 token leak\n", encoding="utf-8")
            self.assertTrue(any("RISK-SEC-001" in i for i in check_trace_closure(run_dir)))

    def test_mitigated_risk_closes(self):
        from tools.workflow_cli.trace import check_trace_closure
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            (run_dir / STAGE_ARTIFACT_MAP[Stage.RISK_DISCOVERY]).write_text(
                "## RISK-SEC-001 token leak\nStatus: mitigated\nMitigation: redact tokens\n", encoding="utf-8")
            self.assertFalse(any("RISK-SEC-001" in i for i in check_trace_closure(run_dir)))

    def test_mitigated_risk_closes_when_id_is_not_first_in_heading(self):
        from tools.workflow_cli.trace import check_trace_closure
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            (run_dir / STAGE_ARTIFACT_MAP[Stage.RISK_DISCOVERY]).write_text(
                "### Token leak RISK-SEC-001\nStatus: mitigated\nMitigation: redact tokens\n",
                encoding="utf-8",
            )
            self.assertFalse(any("RISK-SEC-001" in i for i in check_trace_closure(run_dir)))

    def test_deferred_or_out_of_scope_risk_closes(self):
        from tools.workflow_cli.trace import check_trace_closure
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            (run_dir / STAGE_ARTIFACT_MAP[Stage.RISK_DISCOVERY]).write_text(
                "## RISK-OPS-001 operational runbook\nStatus: deferred\n", encoding="utf-8")
            self.assertFalse(any("RISK-OPS-001" in i for i in check_trace_closure(run_dir)))
            (run_dir / STAGE_ARTIFACT_MAP[Stage.RISK_DISCOVERY]).write_text(
                "## RISK-OPS-001 operational runbook\nStatus: out_of_scope\n", encoding="utf-8")
            self.assertFalse(any("RISK-OPS-001" in i for i in check_trace_closure(run_dir)))

    def test_needs_mitigation_wording_does_not_close_risk(self):
        from tools.workflow_cli.trace import check_trace_closure
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            (run_dir / STAGE_ARTIFACT_MAP[Stage.RISK_DISCOVERY]).write_text(
                "## RISK-SEC-001 token leak\nThis needs mitigation.\nMitigation: TBD\n", encoding="utf-8")
            self.assertTrue(any("RISK-SEC-001" in i for i in check_trace_closure(run_dir)))

    def test_status_outside_risk_block_does_not_close_risk(self):
        from tools.workflow_cli.trace import check_trace_closure
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            (run_dir / STAGE_ARTIFACT_MAP[Stage.RISK_DISCOVERY]).write_text(
                "## RISK-SEC-001 token leak\nThis needs mitigation.\n", encoding="utf-8")
            (run_dir / STAGE_ARTIFACT_MAP[Stage.DESIGN]).write_text(
                "## Design Summary\nStatus: mitigated\n", encoding="utf-8")
            self.assertTrue(any("RISK-SEC-001" in i for i in check_trace_closure(run_dir)))

    def test_plan_referencing_scope_out_is_a_violation(self):
        from tools.workflow_cli.trace import scope_out_violations
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            (run_dir / STAGE_ARTIFACT_MAP[Stage.REQUIREMENT_BRIEF]).write_text(
                "## Out-of-Scope\n- SCOPE-OUT-001 admin UI\n", encoding="utf-8")
            (run_dir / STAGE_ARTIFACT_MAP[Stage.PLAN]).write_text(
                "## Tasks\n### PLAN-TASK-001 build admin UI per SCOPE-OUT-001\n", encoding="utf-8")
            self.assertEqual(scope_out_violations(run_dir), ["SCOPE-OUT-001"])

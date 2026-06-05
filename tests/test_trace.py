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

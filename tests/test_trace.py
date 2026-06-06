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

    def test_spec_references_markdown_list_consumes_specs(self):
        from tools.workflow_cli.trace import spec_ids_not_consumed
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = self._run_dir(
                tmp,
                "## SPEC-AUTH-001 login\nbehavior\n\n## SPEC-SESSION-001 session\nbehavior\n",
                (
                    "### PLAN-TASK-001\n"
                    "Spec References:\n"
                    "- SPEC-AUTH-001\n"
                    "- SPEC-SESSION-001\n"
                ),
            )
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

    def test_build_trace_ignores_readonly_summary_headings(self):
        from tools.workflow_cli.trace import build_trace
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = self._run_dir(
                tmp,
                "",
                (
                    "## Tasks\n"
                    "### PLAN-TASK-001\n"
                    "Spec References: SPEC-AUTH-001\n\n"
                    "## Upstream Summary (read-only)\n"
                    "# Spec Artifact\n"
                    "## SPEC-FAKE-001 upstream-only heading\n"
                    "<!-- /r2p-read-only -->\n"
                ),
            )
            self.assertNotIn("SPEC-FAKE-001", build_trace(run_dir).defined)

    def test_spec_heading_in_design_handoff_is_not_a_defined_spec(self):
        from tools.workflow_cli.trace import spec_ids_not_consumed
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = self._run_dir(
                tmp,
                "## SPEC-AUTH-001 login\nbehavior\n",
                "### PLAN-TASK-001\nSpec References: SPEC-AUTH-001\n",
            )
            (run_dir / STAGE_ARTIFACT_MAP[Stage.DESIGN]).write_text(
                (
                    "## SPEC Handoff\n"
                    "### SPEC-RENAMED-999 planned downstream contract\n"
                    "Use this as a planning note; the actual SPEC renamed it.\n"
                ),
                encoding="utf-8",
            )
            self.assertEqual(spec_ids_not_consumed(run_dir), [])

    def test_scope_in_not_carried_downstream_is_a_gap(self):
        from tools.workflow_cli.trace import check_trace_closure
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            (run_dir / STAGE_ARTIFACT_MAP[Stage.REQUIREMENT_BRIEF]).write_text(
                "## In-Scope\n- SCOPE-IN-001 rate limit per IP\n", encoding="utf-8")
            (run_dir / STAGE_ARTIFACT_MAP[Stage.SPEC]).write_text(
                "## Behavior Contracts\nno scope ref here\n", encoding="utf-8")
            self.assertTrue(any("SCOPE-IN-001" in i for i in check_trace_closure(run_dir)))

    def test_scope_in_under_nested_brief_heading_is_defined(self):
        from tools.workflow_cli.trace import check_trace_closure
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            (run_dir / STAGE_ARTIFACT_MAP[Stage.REQUIREMENT_BRIEF]).write_text(
                "## In-Scope\n"
                "### API\n"
                "- SCOPE-IN-001 rate limit per IP\n"
                "## Out-of-Scope\n"
                "- SCOPE-OUT-001 admin UI\n",
                encoding="utf-8",
            )
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

    def test_scope_in_carried_into_consumed_spec_closes_when_spec_id_is_later_in_heading(self):
        from tools.workflow_cli.trace import check_trace_closure
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            (run_dir / STAGE_ARTIFACT_MAP[Stage.REQUIREMENT_BRIEF]).write_text(
                "## In-Scope\n- SCOPE-IN-001 login behavior\n", encoding="utf-8")
            (run_dir / STAGE_ARTIFACT_MAP[Stage.SPEC]).write_text(
                "### Login behavior SPEC-AUTH-001\nimplements SCOPE-IN-001\n", encoding="utf-8")
            (run_dir / STAGE_ARTIFACT_MAP[Stage.PLAN]).write_text(
                "## Tasks\n### PLAN-TASK-001\nSpec References: SPEC-AUTH-001\n", encoding="utf-8")
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

    def test_scope_ref_after_consumed_spec_block_does_not_close_scope(self):
        from tools.workflow_cli.trace import check_trace_closure
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            (run_dir / STAGE_ARTIFACT_MAP[Stage.REQUIREMENT_BRIEF]).write_text(
                "## In-Scope\n- SCOPE-IN-001 login behavior\n", encoding="utf-8")
            (run_dir / STAGE_ARTIFACT_MAP[Stage.SPEC]).write_text(
                (
                    "## SPEC-AUTH-001 login\n"
                    "No scope reference in this contract.\n\n"
                    "## PLAN Handoff\n"
                    "SCOPE-IN-001 mentioned outside the SPEC block.\n"
                ),
                encoding="utf-8",
            )
            (run_dir / STAGE_ARTIFACT_MAP[Stage.PLAN]).write_text(
                "## Tasks\n### PLAN-TASK-001\nSpec References: SPEC-AUTH-001\n", encoding="utf-8")
            self.assertTrue(any("SCOPE-IN-001" in i for i in check_trace_closure(run_dir)))

    def test_scope_in_only_in_consumed_spec_non_goals_is_a_gap(self):
        """R14 red-team: a SPEC that says 'SCOPE-IN-001 is NOT implemented here'
        in its nested Non-goals must not close that scope item."""
        from tools.workflow_cli.trace import check_trace_closure
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            (run_dir / STAGE_ARTIFACT_MAP[Stage.REQUIREMENT_BRIEF]).write_text(
                "## In-Scope\n- SCOPE-IN-001 export audit logs\n", encoding="utf-8")
            (run_dir / STAGE_ARTIFACT_MAP[Stage.SPEC]).write_text(
                (
                    "## SPEC-AUDIT-001 audit behavior\n"
                    "No scope reference in the contract body.\n\n"
                    "### Non-goals\n"
                    "- SCOPE-IN-001 is not implemented here\n"
                ),
                encoding="utf-8",
            )
            (run_dir / STAGE_ARTIFACT_MAP[Stage.PLAN]).write_text(
                "## Tasks\n### PLAN-TASK-001\nSpec References: SPEC-AUDIT-001\n",
                encoding="utf-8")
            self.assertTrue(any("SCOPE-IN-001" in i for i in check_trace_closure(run_dir)))

    def test_scope_in_in_sibling_section_after_non_goals_still_closes(self):
        """R14 guard: the Non-goals strip must end at the next same-or-higher
        heading; a sibling subsection carrying the SCOPE-IN still closes it."""
        from tools.workflow_cli.trace import check_trace_closure
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            (run_dir / STAGE_ARTIFACT_MAP[Stage.REQUIREMENT_BRIEF]).write_text(
                "## In-Scope\n- SCOPE-IN-001 export audit logs\n", encoding="utf-8")
            (run_dir / STAGE_ARTIFACT_MAP[Stage.SPEC]).write_text(
                (
                    "## SPEC-AUDIT-001 audit behavior\n"
                    "### Non-goals\n"
                    "- other exclusions\n\n"
                    "### Implementation notes\n"
                    "implements SCOPE-IN-001\n"
                ),
                encoding="utf-8",
            )
            (run_dir / STAGE_ARTIFACT_MAP[Stage.PLAN]).write_text(
                "## Tasks\n### PLAN-TASK-001\nSpec References: SPEC-AUDIT-001\n",
                encoding="utf-8")
            self.assertFalse(any("SCOPE-IN-001" in i for i in check_trace_closure(run_dir)))

    def test_fenced_plan_task_heading_does_not_consume_spec(self):
        from tools.workflow_cli.trace import spec_ids_not_consumed
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = self._run_dir(
                tmp,
                "## SPEC-AUTH-001 login\nbehavior\n\n## SPEC-OTHER-001 other\nbehavior\n",
                (
                    "## Tasks\n"
                    "### PLAN-TASK-001\n"
                    "Spec References: SPEC-AUTH-001\n"
                    "Skeleton:\n"
                    "```md\n"
                    "### PLAN-TASK-002\n"
                    "Spec References: SPEC-OTHER-001\n"
                    "```\n"
                ),
            )
            self.assertEqual(spec_ids_not_consumed(run_dir), ["SPEC-OTHER-001"])

    def test_fenced_spec_heading_is_not_a_defined_spec(self):
        from tools.workflow_cli.trace import spec_ids_not_consumed
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = self._run_dir(
                tmp,
                (
                    "## SPEC-AUTH-001 login\n"
                    "behavior\n\n"
                    "```md\n"
                    "## SPEC-FAKE-001 template only\n"
                    "```\n"
                ),
                "### PLAN-TASK-001\nSpec References: SPEC-AUTH-001\n",
            )
            self.assertEqual(spec_ids_not_consumed(run_dir), [])

    def test_fenced_scope_ref_in_consumed_spec_does_not_close_scope(self):
        from tools.workflow_cli.trace import check_trace_closure
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            (run_dir / STAGE_ARTIFACT_MAP[Stage.REQUIREMENT_BRIEF]).write_text(
                "## In-Scope\n- SCOPE-IN-001 login behavior\n", encoding="utf-8")
            (run_dir / STAGE_ARTIFACT_MAP[Stage.SPEC]).write_text(
                "## SPEC-AUTH-001 login\n```md\nimplements SCOPE-IN-001\n```\n",
                encoding="utf-8",
            )
            (run_dir / STAGE_ARTIFACT_MAP[Stage.PLAN]).write_text(
                "## Tasks\n### PLAN-TASK-001\nSpec References: SPEC-AUTH-001\n", encoding="utf-8")
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
            for status in ("deferred", "out_of_scope", "out-of-scope"):
                with self.subTest(status=status):
                    (run_dir / STAGE_ARTIFACT_MAP[Stage.RISK_DISCOVERY]).write_text(
                        f"## RISK-OPS-001 operational runbook\nStatus: {status}\n", encoding="utf-8")
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

    def test_fenced_plan_scope_out_reference_is_not_a_violation(self):
        from tools.workflow_cli.trace import scope_out_violations
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            (run_dir / STAGE_ARTIFACT_MAP[Stage.REQUIREMENT_BRIEF]).write_text(
                "## Out-of-Scope\n- SCOPE-OUT-001 admin UI\n", encoding="utf-8")
            (run_dir / STAGE_ARTIFACT_MAP[Stage.PLAN]).write_text(
                "## Tasks\n"
                "### PLAN-TASK-001 build auth\n"
                "Skeleton:\n"
                "```md\n"
                "Do not implement SCOPE-OUT-001 here.\n"
                "```\n",
                encoding="utf-8",
            )
            self.assertEqual(scope_out_violations(run_dir), [])

    def test_seeded_upstream_summary_scope_out_reference_is_not_a_violation(self):
        from tools.workflow_cli.trace import scope_out_violations
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            (run_dir / STAGE_ARTIFACT_MAP[Stage.REQUIREMENT_BRIEF]).write_text(
                "## Out-of-Scope\n- SCOPE-OUT-001 admin UI\n", encoding="utf-8")
            (run_dir / STAGE_ARTIFACT_MAP[Stage.PLAN]).write_text(
                "## Tasks\n"
                "### PLAN-TASK-001 build auth\n"
                "Spec References: SPEC-AUTH-001\n"
                "Verification: pytest\n\n"
                "## Upstream Summary (read-only)\n"
                "Brief excluded SCOPE-OUT-001 from this workflow.\n",
                encoding="utf-8",
            )
            self.assertEqual(scope_out_violations(run_dir), [])

    def test_scope_out_via_consumed_spec_is_a_violation(self):
        """R9 red-team: SCOPE-OUT carried by a consumed SPEC block must fail."""
        from tools.workflow_cli.trace import scope_out_violations
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = self._run_dir(
                tmp,
                "## SPEC-ADMIN-001 admin dashboard\nImplements SCOPE-OUT-001\n",
                "### PLAN-TASK-001\nSpec References: SPEC-ADMIN-001\n",
            )
            self.assertEqual(scope_out_violations(run_dir), ["SCOPE-OUT-001"])

    def test_scope_out_in_nested_non_goals_subsection_is_not_a_violation(self):
        """R9 pass fixture: SCOPE-OUT under an in-block Non-goals subheading is exempt.
        Must use a subheading INSIDE the SPEC block (deeper level), not the
        document-level ## Non-goals, so the exclusion path is actually exercised."""
        from tools.workflow_cli.trace import scope_out_violations
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = self._run_dir(
                tmp,
                "## SPEC-AUTH-001 login\nbehavior\n\n"
                "### Non-goals\n- SCOPE-OUT-001 explicitly excluded\n",
                "### PLAN-TASK-001\nSpec References: SPEC-AUTH-001\n",
            )
            self.assertEqual(scope_out_violations(run_dir), [])

    def test_scope_out_in_sibling_section_after_non_goals_is_a_violation(self):
        """R9 boundary: exemption ends at the next same-or-higher heading."""
        from tools.workflow_cli.trace import scope_out_violations
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = self._run_dir(
                tmp,
                "## SPEC-AUTH-001 login\nbehavior\n\n"
                "### Non-goals\n- excluded items\n\n"
                "### Follow-up work\nImplements SCOPE-OUT-001\n",
                "### PLAN-TASK-001\nSpec References: SPEC-AUTH-001\n",
            )
            self.assertEqual(scope_out_violations(run_dir), ["SCOPE-OUT-001"])

    def test_scope_out_in_unconsumed_spec_is_not_a_violation(self):
        """Only SPEC blocks actually consumed by PLAN-TASK Spec References count."""
        from tools.workflow_cli.trace import scope_out_violations
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = self._run_dir(
                tmp,
                "## SPEC-AUTH-001 login\nbehavior\n\n"
                "## SPEC-OTHER-001 other\nImplements SCOPE-OUT-001\n",
                "### PLAN-TASK-001\nSpec References: SPEC-AUTH-001\n",
            )
            self.assertEqual(scope_out_violations(run_dir), [])

    def test_non_goals_heading_case_variants_are_exempt(self):
        """Normalized heading match: `### Non-Goals` (case variant) is exempt."""
        from tools.workflow_cli.trace import scope_out_violations
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = self._run_dir(
                tmp,
                "## SPEC-AUTH-001 login\nbehavior\n\n"
                "### Non-Goals\n- SCOPE-OUT-002 excluded\n",
                "### PLAN-TASK-001\nSpec References: SPEC-AUTH-001\n",
            )
            self.assertEqual(scope_out_violations(run_dir), [])

    def test_nested_non_goals_does_not_swallow_sibling_violation(self):
        """Regression: a deeper Non-goals nested inside a Non-goals section must
        not corrupt excision offsets and hide a sibling-section violation."""
        from tools.workflow_cli.trace import scope_out_violations
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = self._run_dir(
                tmp,
                "## SPEC-AUTH-001 login\nbehavior\n\n"
                "### Non-goals\n- excluded items\n\n"
                "#### Non-goals\n- nested noise\n\n"
                "### Follow-up work\nImplements SCOPE-OUT-001\n",
                "### PLAN-TASK-001\nSpec References: SPEC-AUTH-001\n",
            )
            self.assertEqual(scope_out_violations(run_dir), ["SCOPE-OUT-001"])

    def test_two_non_goals_subsections_keep_violation_between_them(self):
        """Two sibling Non-goals subsections are both exempt; a kept section
        between them still reports its violation (multi-removal path)."""
        from tools.workflow_cli.trace import scope_out_violations
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = self._run_dir(
                tmp,
                "## SPEC-AUTH-001 login\nbehavior\n\n"
                "### Non-goals\n- SCOPE-OUT-002 excluded\n\n"
                "### Implementation notes\nImplements SCOPE-OUT-001\n\n"
                "### Non-goals\n- SCOPE-OUT-003 also excluded\n",
                "### PLAN-TASK-001\nSpec References: SPEC-AUTH-001\n",
            )
            self.assertEqual(scope_out_violations(run_dir), ["SCOPE-OUT-001"])

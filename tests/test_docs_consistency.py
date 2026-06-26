"""Guard against hardcoded test-count magic numbers drifting across docs.

TDD: written before the docs are cleaned up.
"""
import re
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Matches "589 passing", "602 tests passing", "baseline: 673", etc.
_MAGIC_COUNT = re.compile(r"\b\d{2,}\s+(?:tests?\s+)?passing\b|baseline[:：]\s*\d{2,}", re.IGNORECASE)

# Docs that must describe the suite qualitatively, not with a frozen number.
_GUARDED_DOCS = [
    "CLAUDE.md",
]


class TestDocsHaveNoHardcodedTestCount(unittest.TestCase):
    def test_no_magic_test_count_in_guarded_docs(self):
        offenders = []
        for rel in _GUARDED_DOCS:
            path = REPO_ROOT / rel
            if not path.exists():
                continue
            for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if _MAGIC_COUNT.search(line):
                    offenders.append(f"{rel}:{lineno}: {line.strip()}")
        self.assertEqual(
            offenders, [],
            "Docs must not hardcode a test count (it drifts). Describe the suite "
            "qualitatively instead. Offenders:\n" + "\n".join(offenders),
        )


class TestAgentTemplateCheckpointGuidance(unittest.TestCase):
    def test_continue_surfaces_include_ambiguity_checkpoint_rule(self):
        surfaces = [
            "tools/workflow_cli/agent_templates/claude/SKILL.md",
            "tools/workflow_cli/agent_templates/claude/commands/r2p-continue.md",
            "tools/workflow_cli/agent_templates/codex/skills/r2p-continue/SKILL.md",
            "tools/workflow_cli/agent_templates/gemini/commands/r2p-continue.toml",
        ]
        required_terms = ("unresolved ambiguity", "undecided point")
        missing = []
        for rel in surfaces:
            text = (REPO_ROOT / rel).read_text(encoding="utf-8")
            if not all(term in text for term in required_terms):
                missing.append(rel)
        self.assertEqual(
            missing, [],
            "Every r2p-continue surface must tell agents not to approve "
            "DESIGN/SPEC/PLAN checkpoints with unresolved ambiguity. Missing: "
            + ", ".join(missing),
        )


def _get_role_section(text, heading_prefix):
    """Return text from the line starting with heading_prefix to the next ### or ## heading."""
    lines = text.splitlines()
    in_section = False
    section_lines = []
    for line in lines:
        if in_section:
            if line.startswith("### ") or line.startswith("## "):
                break
            section_lines.append(line)
        elif line.startswith(heading_prefix):
            in_section = True
            section_lines.append(line)
    return "\n".join(section_lines)


class TestExecuteTemplateContent(unittest.TestCase):
    def test_execute_surfaces_call_installed_task_brief_wrapper(self):
        surfaces = [
            "tools/workflow_cli/agent_templates/claude/commands/r2p-execute.md",
            "tools/workflow_cli/agent_templates/codex/skills/r2p-execute/SKILL.md",
        ]
        missing = []
        offenders = []
        for rel in surfaces:
            text = (REPO_ROOT / rel).read_text(encoding="utf-8")
            if "{{R2P_BIN_DIR}}/r2p-task-brief" not in text:
                missing.append(rel)
            if "{{R2P_BIN_DIR}}/plan-task-brief" in text:
                offenders.append(rel)
        self.assertEqual(missing, [], f"missing installed r2p-task-brief wrapper call: {missing}")
        self.assertEqual(offenders, [], f"execute surfaces call nonexistent wrapper: {offenders}")

    def test_execute_surfaces_carry_sdd_orchestration_tokens(self):
        surfaces = [
            "tools/workflow_cli/agent_templates/claude/commands/r2p-execute.md",
            "tools/workflow_cli/agent_templates/codex/skills/r2p-execute/SKILL.md",
        ]
        required = (
            "closed_at_plan_checkpoint",
            "current branch",          # in-place, no branch
            "Pre-flight",
            "Verification",            # per-task completion gate
            "fresh implementer subagent",
            "task-reviewer",
            "whole-branch review",
            "r2p-archive",
            "--work-id",
            "- [x] PLAN-TASK-NNN",
            "hard prerequisite",       # no subagent degrade
            "NEEDS_CONTEXT",           # ambiguity ladder
            "Model Selection",         # FR-A1 model scaling
            "Read the task brief on demand when sizing the implementer model",  # model sizing may re-read the brief
            "copied verbatim when present",  # implementer dispatch also receives plan-level Global Constraints
            "HEAD~1",                  # FR-A3 BASE rule (never use HEAD~1)
            "execution/final-review.md",  # FR-A6 marker write
            "Verdict: Approved",       # FR-A6 verdict protocol literal
            "re-run the full verification suite",  # FR-A6 whole-branch review
            "After any final-review fix wave",  # FR-A6 post-fix review loop
            "regenerate `.req-to-plan/<work-id>/logs/final-diff.md`",
            "re-dispatch the final whole-branch reviewer",
            "Repeat until the post-fix reviewer is clean",
            "only then append `Verdict: Approved`",
        )
        missing = []
        for rel in surfaces:
            text = (REPO_ROOT / rel).read_text(encoding="utf-8")
            for tok in required:
                if tok not in text:
                    missing.append(f"{rel}:{tok}")
        self.assertEqual(missing, [], f"missing SDD tokens: {missing}")

    def test_execute_surfaces_do_not_route_defects_through_gap_open(self):
        surfaces = [
            "tools/workflow_cli/agent_templates/claude/commands/r2p-execute.md",
            "tools/workflow_cli/agent_templates/codex/skills/r2p-execute/SKILL.md",
        ]
        offenders = []
        for rel in surfaces:
            text = (REPO_ROOT / rel).read_text(encoding="utf-8")
            if "`r2p-gap-open`" in text:
                offenders.append(rel)
        self.assertEqual(
            offenders,
            [],
            "Execution runs have current_stage=closed, so upstream defects must "
            "use a reopen/human repair path instead of r2p-gap-open: "
            + ", ".join(offenders),
        )

    def test_execute_surfaces_carry_fr_cm_context_management_tokens(self):
        """SPEC-GUARD-001: both r2p-execute surfaces must carry the FR-CM load-bearing tokens."""
        surfaces = [
            "tools/workflow_cli/agent_templates/claude/commands/r2p-execute.md",
            "tools/workflow_cli/agent_templates/codex/skills/r2p-execute/SKILL.md",
        ]
        REQUIRED_FR_CM_TOKENS = [
            "plan-task-brief",       # FR-CM1: the loop routes the handoff through the brief
            "task-brief",            # the brief-file handoff / shortcut
            "brief_path",            # FR-CM1: both dispatches use the returned brief path
            "not pasted task text",  # FR-CM1: guards against reverting to inline handoff
            "Resolved:",             # FR-CM3 adjudication — clears a reviewer warning
            "Gap:",                  # FR-CM3 adjudication — blocks the flip
            "Unresolved:",           # FR-CM3 adjudication — blocks the flip
            "Narration:",            # FR-CM2 narration ceiling label
            "Minor:",                # FR-CM4 carried-forward minor-findings marker
        ]
        missing = []
        gap_open_offenders = []
        for rel in surfaces:
            text = (REPO_ROOT / rel).read_text(encoding="utf-8")
            for tok in REQUIRED_FR_CM_TOKENS:
                if tok not in text:
                    missing.append(f"{rel}:{tok}")
            if "`r2p-gap-open`" in text:
                gap_open_offenders.append(rel)
        self.assertEqual(missing, [], f"missing FR-CM context-management tokens: {missing}")
        self.assertEqual(
            gap_open_offenders,
            [],
            "Execution runs have current_stage=closed, so upstream defects must "
            "use a reopen/human repair path instead of r2p-gap-open: "
            + ", ".join(gap_open_offenders),
        )

    def test_execute_surfaces_define_reviewer_defer_contract(self):
        surfaces = [
            "tools/workflow_cli/agent_templates/claude/commands/r2p-execute.md",
            "tools/workflow_cli/agent_templates/codex/skills/r2p-execute/SKILL.md",
        ]
        required = (
            "Do not pass separate `Spec References`",
            "reviewer reads `Spec References` from the task brief",
            "⚠️ DEFER",
            "cannot verify from diff",
            "satisfied by unchanged code",
            "sibling task",
            "Surface in `concerns` every ⚠️",          # FR-CM3 produce: defer/minor items surface inline
            "open `review_report_path` to adjudicate",  # FR-CM3 consume: open report only when concerns flag ⚠️
        )
        forbidden = (
            "plus the task's `Spec References`",
            "checked against `Spec References` + `Verification`",
        )
        missing = []
        offenders = []
        for rel in surfaces:
            text = (REPO_ROOT / rel).read_text(encoding="utf-8")
            for tok in required:
                if tok not in text:
                    missing.append(f"{rel}:{tok}")
            for tok in forbidden:
                if tok in text:
                    offenders.append(f"{rel}:{tok}")
        self.assertEqual(missing, [], f"missing reviewer defer contract tokens: {missing}")
        self.assertEqual(offenders, [], f"stale reviewer handoff contract remains: {offenders}")

    def test_execute_surfaces_route_reviewer_findings_through_report_paths(self):
        surfaces = [
            "tools/workflow_cli/agent_templates/claude/commands/r2p-execute.md",
            "tools/workflow_cli/agent_templates/codex/skills/r2p-execute/SKILL.md",
        ]
        required = (
            "A review report file path (`execution/task-N-review.md`)",
            "`review_report_path`: the review report file path",
            "Pass the `review_report_path` to the fix subagent",
            "Fix all Critical and Important findings in the review report",
        )
        missing = []
        for rel in surfaces:
            text = (REPO_ROOT / rel).read_text(encoding="utf-8")
            for tok in required:
                if tok not in text:
                    missing.append(f"{rel}:{tok}")
        self.assertEqual(missing, [], f"missing reviewer finding handoff contract: {missing}")

    def test_execute_surfaces_do_not_require_generated_outputs_in_subagent_preflight(self):
        surfaces = [
            "tools/workflow_cli/agent_templates/claude/commands/r2p-execute.md",
            "tools/workflow_cli/agent_templates/codex/skills/r2p-execute/SKILL.md",
        ]
        required = (
            "Input paths must already exist and be readable",
            "Output paths do not need to exist at preflight",
            "treat generated output paths as destination paths",
            "Their parent directories must resolve under the same `run_dir` / `work_id`",
            "`execution/task-N-report.md`",
            "`execution/task-N-review.md`",
        )
        forbidden = (
            "Every Authoritative Context Set path, brief path, ledger path, review path, and diff path exists and is readable",
        )
        missing = []
        offenders = []
        for rel in surfaces:
            text = (REPO_ROOT / rel).read_text(encoding="utf-8")
            section = _get_role_section(text, "### Path Delivery and Fail-Closed Preflight")
            for tok in required:
                if tok not in section:
                    missing.append(f"{rel}:{tok}")
            for tok in forbidden:
                if tok in section:
                    offenders.append(f"{rel}:{tok}")
        self.assertEqual(missing, [], f"missing generated-output preflight split: {missing}")
        self.assertEqual(offenders, [], f"subagent preflight still requires generated outputs: {offenders}")

    def test_execute_surfaces_return_inline_status_summary_fields(self):
        surfaces = [
            "tools/workflow_cli/agent_templates/claude/commands/r2p-execute.md",
            "tools/workflow_cli/agent_templates/codex/skills/r2p-execute/SKILL.md",
        ]
        required = (
            "`status`",
            "`report_path`",
            "`commit_range`",
            "`test_summary`",
            "`concerns`",
            "one-line test summary",
            "without opening the full report",
        )
        missing = []
        for rel in surfaces:
            text = (REPO_ROOT / rel).read_text(encoding="utf-8")
            for tok in required:
                if tok not in text:
                    missing.append(f"{rel}:{tok}")
        self.assertEqual(missing, [], f"missing inline status summary fields: {missing}")

    def test_execute_surfaces_block_dirty_code_tree_before_task_loop(self):
        surfaces = [
            "tools/workflow_cli/agent_templates/claude/commands/r2p-execute.md",
            "tools/workflow_cli/agent_templates/codex/skills/r2p-execute/SKILL.md",
        ]
        missing = []
        offenders = []
        required = (
            "stop before dispatching Task 1",
            "Do not commit unrelated work",
            "git status --short -- ':!.req-to-plan'",
        )
        forbidden = (
            "do NOT block execution",
            "warn the user but do NOT block execution",
        )
        for rel in surfaces:
            text = (REPO_ROOT / rel).read_text(encoding="utf-8")
            for tok in required:
                if tok not in text:
                    missing.append(f"{rel}:{tok}")
            for tok in forbidden:
                if tok in text:
                    offenders.append(f"{rel}:{tok}")
        self.assertEqual(missing, [], f"missing dirty-tree block guidance: {missing}")
        self.assertEqual(offenders, [], f"unsafe dirty-tree guidance remains: {offenders}")

    def test_execute_surfaces_capture_base_before_implementer_dispatch(self):
        surfaces = [
            "tools/workflow_cli/agent_templates/claude/commands/r2p-execute.md",
            "tools/workflow_cli/agent_templates/codex/skills/r2p-execute/SKILL.md",
        ]
        offenders = []
        for rel in surfaces:
            text = (REPO_ROOT / rel).read_text(encoding="utf-8")
            base_pos = text.find("Record BASE (`git rev-parse HEAD`) BEFORE dispatching the implementer")
            dispatch_pos = text.find("### 2. Dispatch a fresh implementer subagent")
            after_done_pos = text.find("After the implementer reports DONE")
            if base_pos == -1 or dispatch_pos == -1 or after_done_pos == -1:
                offenders.append(f"{rel}:missing-anchor")
                continue
            if not (dispatch_pos < base_pos < after_done_pos):
                offenders.append(rel)
        self.assertEqual(
            offenders,
            [],
            "r2p-execute surfaces must record BASE before implementer dispatch, "
            f"not after DONE: {offenders}",
        )

    def test_execute_surfaces_pass_final_review_whole_branch_diff_scope(self):
        surfaces = [
            "tools/workflow_cli/agent_templates/claude/commands/r2p-execute.md",
            "tools/workflow_cli/agent_templates/codex/skills/r2p-execute/SKILL.md",
        ]
        required = (
            "Scope:",
            "Include the diff",
            "git diff -U10 <execution-base-commit> HEAD",
            ".req-to-plan/<work-id>/logs/final-diff.md",
        )
        missing = []
        for rel in surfaces:
            text = (REPO_ROOT / rel).read_text(encoding="utf-8")
            for tok in required:
                if tok not in text:
                    missing.append(f"{rel}:{tok}")
        self.assertEqual(missing, [], f"missing final-review diff scope guidance: {missing}")

    def test_execute_surfaces_persist_execution_base_for_resume(self):
        surfaces = [
            "tools/workflow_cli/agent_templates/claude/commands/r2p-execute.md",
            "tools/workflow_cli/agent_templates/codex/skills/r2p-execute/SKILL.md",
        ]
        required = (
            "Persist the Task 1 BASE immediately in tracked execution state",
            "`execution/progress.md`",
            "`Execution BASE: <execution-base-commit>`",
            "On resume, read `execution/progress.md`",
            "Do not recalculate it from `HEAD`",
        )
        missing = []
        for rel in surfaces:
            text = (REPO_ROOT / rel).read_text(encoding="utf-8")
            for tok in required:
                if tok not in text:
                    missing.append(f"{rel}:{tok}")
        self.assertEqual(missing, [], f"missing persisted execution-base guidance: {missing}")

    def test_execute_surfaces_create_logs_dir_before_final_diff(self):
        surfaces = [
            "tools/workflow_cli/agent_templates/claude/commands/r2p-execute.md",
            "tools/workflow_cli/agent_templates/codex/skills/r2p-execute/SKILL.md",
        ]
        required = (
            "`mkdir -p .req-to-plan/<work-id>/logs` then `git diff -U10 <execution-base-commit> HEAD > .req-to-plan/<work-id>/logs/final-diff.md`",
        )
        missing = []
        for rel in surfaces:
            text = (REPO_ROOT / rel).read_text(encoding="utf-8")
            for tok in required:
                if tok not in text:
                    missing.append(f"{rel}:{tok}")
        self.assertEqual(missing, [], f"missing final-diff logs mkdir guidance: {missing}")

    def test_execute_surfaces_hand_authoritative_context_set(self):
        """DES-TEST-001 / FR-AC7: ACS block, matrix, per-role read instruction, and exclusion split on both surfaces."""
        surfaces = [
            "tools/workflow_cli/agent_templates/claude/commands/r2p-execute.md",
            "tools/workflow_cli/agent_templates/codex/skills/r2p-execute/SKILL.md",
        ]

        # Whole-file required tokens: ACS heading (1), six read-set paths (2–7),
        # matrix (8), conflict rule BLOCKED+reopen (9–10), ledger read-only (11),
        # sibling escalation (12–13), §6 diff regen (14), report-path regression (15–16).
        required_whole = (
            "## Authoritative Context Set",
            "02-project-context.md",
            "03-requirement-brief.md",
            "04-risk-discovery.md",
            "05-design.md",
            "06-spec.md",
            "execution/progress.md",
            "Responsibility Matrix",
            "BLOCKED",
            "reopen",
            "read-only to subagents",
            "r2p-task-brief --task",
            "NEEDS_CONTEXT",
            "regenerates `logs/task-N-diff.md`",
            "Pass the `review_report_path` to the fix subagent",
            "Fix all Critical and Important findings in the review report",
        )
        # Whole-file forbidden tokens: Scene-setting context absent (17), r2p-gap-open absent (18).
        forbidden_whole = (
            "Scene-setting context",
            "`r2p-gap-open`",
        )

        missing = []
        offenders = []
        for rel in surfaces:
            text = (REPO_ROOT / rel).read_text(encoding="utf-8")
            for tok in required_whole:
                if tok not in text:
                    missing.append(f"{rel}:{tok}")
            for tok in forbidden_whole:
                if tok in text:
                    offenders.append(f"{rel}:{tok}")
        self.assertEqual(missing, [], f"missing ACS tokens: {missing}")
        self.assertEqual(offenders, [], f"forbidden ACS tokens present: {offenders}")

        # Per-role slice: §2, §5, §6 each contain the ACS read instruction (check 8 per spec).
        for rel in surfaces:
            text = (REPO_ROOT / rel).read_text(encoding="utf-8")
            for section_prefix in ("### 2.", "### 5.", "### 6."):
                section = _get_role_section(text, section_prefix)
                self.assertIn(
                    "Read the Authoritative Context Set before acting",
                    section,
                    f"{rel}: section {section_prefix!r} must reference the ACS read instruction",
                )

        # ACS read-set / exclusion split (check 9 per spec):
        # The exclusion sentence names 07-plan.md, 00-raw-requirement.md, 01-intake-brief.md.
        # Split the ACS block at that line; verify the six read-set paths appear BEFORE it
        # and the three excluded paths do NOT appear before it.
        for rel in surfaces:
            text = (REPO_ROOT / rel).read_text(encoding="utf-8")
            acs_start = text.find("## Authoritative Context Set")
            self.assertNotEqual(acs_start, -1, f"{rel}: missing ACS heading")
            next_h2 = text.find("\n## ", acs_start + 1)
            acs_block = text[acs_start:next_h2] if next_h2 != -1 else text[acs_start:]
            acs_lines = acs_block.splitlines()
            # Find the first line in the ACS block that names the excluded 07-plan.md
            excl_idx = next(
                (i for i, line in enumerate(acs_lines) if "`07-plan.md`" in line),
                None,
            )
            self.assertIsNotNone(
                excl_idx,
                f"{rel}: ACS block lacks an exclusion sentence for 07-plan.md",
            )
            read_set_portion = "\n".join(acs_lines[:excl_idx])
            # Six read-set paths must appear before the exclusion line
            for path in (
                "02-project-context.md",
                "03-requirement-brief.md",
                "04-risk-discovery.md",
                "05-design.md",
                "06-spec.md",
                "execution/progress.md",
            ):
                self.assertIn(
                    path, read_set_portion,
                    f"{rel}: {path!r} missing from ACS read-set portion (before exclusion line)",
                )
            # Three excluded paths must NOT appear before the exclusion line
            for path in ("07-plan.md", "00-raw-requirement.md", "01-intake-brief.md"):
                self.assertNotIn(
                    path, read_set_portion,
                    f"{rel}: excluded path {path!r} found in ACS read-set portion",
                )

    def test_gemini_execute_toml_mentions_in_place_and_archive(self):
        text = (REPO_ROOT / "tools/workflow_cli/agent_templates/gemini/commands/r2p-execute.toml").read_text(encoding="utf-8")
        self.assertIn("r2p-execute", text)
        self.assertIn("current branch", text)


if __name__ == "__main__":
    unittest.main()

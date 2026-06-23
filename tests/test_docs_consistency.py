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
    ".claude/skills/req-to-plan.md",
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


class TestExecuteTemplateContent(unittest.TestCase):
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
        )
        missing = []
        for rel in surfaces:
            text = (REPO_ROOT / rel).read_text(encoding="utf-8")
            for tok in required:
                if tok not in text:
                    missing.append(f"{rel}:{tok}")
        self.assertEqual(missing, [], f"missing SDD tokens: {missing}")

    def test_gemini_execute_toml_mentions_in_place_and_archive(self):
        text = (REPO_ROOT / "tools/workflow_cli/agent_templates/gemini/commands/r2p-execute.toml").read_text(encoding="utf-8")
        self.assertIn("r2p-execute", text)
        self.assertIn("current branch", text)


if __name__ == "__main__":
    unittest.main()

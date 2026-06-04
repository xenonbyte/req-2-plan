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


if __name__ == "__main__":
    unittest.main()

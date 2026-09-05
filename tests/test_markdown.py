import sys

import pytest

from tools.workflow_cli.markdown import strip_readonly_sections


def test_strip_readonly_sections_stops_at_next_same_level_heading():
    content = (
        "# Plan\n\n"
        "## Upstream Summary (read-only)\n"
        "Seeded summary.\n"
        "### SPEC-FAKE-001 copied detail\n"
        "readonly body\n\n"
        "## Tasks\n"
        "### PLAN-TASK-001 real task\n"
    )

    stripped = strip_readonly_sections(content)

    assert "Seeded summary" not in stripped
    assert "SPEC-FAKE-001" not in stripped
    assert "## Tasks" in stripped
    assert "PLAN-TASK-001" in stripped


def test_strip_readonly_sections_prefers_explicit_end_marker_for_seeded_payload():
    content = (
        "# Plan\n\n"
        "## Upstream Summary (read-only)\n"
        "# Spec Artifact\n"
        "## SPEC-FAKE-001 copied heading\n"
        "<!-- /r2p-read-only -->\n\n"
        "## Tasks\n"
        "### PLAN-TASK-001 real task\n"
    )

    stripped = strip_readonly_sections(content)

    assert "SPEC-FAKE-001" not in stripped
    assert "## Tasks" in stripped
    assert "PLAN-TASK-001" in stripped


def test_strip_readonly_sections_ignores_heading_inside_html_comment():
    content = (
        "# Plan\n\n"
        "<!--\n"
        "## Upstream Summary (read-only)\n"
        "-->\n"
        "VISIBLE-CONTENT\n\n"
        "## Tasks\n"
        "### PLAN-TASK-001 real task\n"
    )

    stripped = strip_readonly_sections(content)

    assert "VISIBLE-CONTENT" in stripped
    assert "## Tasks" in stripped
    assert "PLAN-TASK-001" in stripped


def test_plan_task_anchors_extracts_id_and_title():
    from tools.workflow_cli.markdown import plan_task_anchors
    content = (
        "## Tasks\n"
        "### PLAN-TASK-001: build the thing\n"
        "Files:\n- a.py\n"
        "### PLAN-TASK-002: wire it up\n"
        "Files:\n- b.py\n"
    )
    assert plan_task_anchors(content) == [
        ("PLAN-TASK-001", "build the thing"),
        ("PLAN-TASK-002", "wire it up"),
    ]


def test_plan_task_anchors_ignores_code_fences():
    from tools.workflow_cli.markdown import plan_task_anchors
    content = (
        "## Tasks\n"
        "```\n"
        "### PLAN-TASK-999: not a real task\n"
        "```\n"
        "### PLAN-TASK-001: real task\n"
    )
    assert plan_task_anchors(content) == [("PLAN-TASK-001", "real task")]


def test_plan_task_anchors_empty_when_no_tasks():
    from tools.workflow_cli.markdown import plan_task_anchors
    assert plan_task_anchors("# Plan\n\nno tasks here\n") == []


def test_strip_html_comments_outside_fences_removes_multiline_comment():
    from tools.workflow_cli.markdown import strip_html_comments_outside_fences

    content = "before\n<!--\nhidden\n-->\nafter\n"

    stripped = strip_html_comments_outside_fences(content)

    assert "hidden" not in stripped
    assert len(stripped) == len(content)
    assert stripped.splitlines()[0] == "before"
    assert stripped.splitlines()[-1] == "after"


def test_strip_html_comments_outside_fences_preserves_fenced_code():
    from tools.workflow_cli.markdown import strip_html_comments_outside_fences

    fenced = "```html\n<!-- required code comment -->\n```\n"

    assert strip_html_comments_outside_fences(fenced) == fenced


@pytest.mark.parametrize("ending", ["\n", "\r\n"])
@pytest.mark.parametrize(
    ("prefix", "hidden", "suffix"),
    [
        ("α\n", "## Project Context (read-only)\n# Copied document\n<!-- /r2p-read-only -->\n", "ω"),
        ("α\n", "## Upstream Summary (read-only)\n### Nested\nhidden\n", "## Tasks\nω\n"),
        ("α\n", "## Project Context (read-only)\n### Upstream Summary (read-only)\nhidden\n<!-- /r2p-read-only -->\n", "## Tasks\nω\n"),
        ("α\n", "## Project Context (read-only)\nhidden\n## Upstream Summary (read-only)\n# Copied\n<!-- /r2p-read-only -->\n", "ω\n"),
        ("α\n", "## Project Context (read-only)\nhidden without final newline", ""),
        ("α\n", "## Project Context (read-only)\n~~~html\n<!-- /r2p-read-only -->\n~~~\n<!--\n<!-- /r2p-read-only -->\nhidden\n<!-- /r2p-read-only -->\n", "ω\n"),
        ("```md\n## Project Context (read-only)\nfenced\n```\n<!--\n## Upstream Summary (read-only)\n-->\n", "", "ω\n"),
    ],
)
def test_nonsemantic_mask_and_strip_share_readonly_boundaries(prefix, hidden, suffix, ending):
    from tools.workflow_cli.markdown import (
        mask_nonsemantic_markdown, strip_html_comments_outside_fences,
        strip_nonsemantic_markdown,
    )
    prefix, hidden, suffix = (part.replace("\n", ending) for part in (prefix, hidden, suffix))
    content = prefix + hidden + suffix
    blank = "".join(char if char in "\r\n" else " " for char in hidden)
    masked = mask_nonsemantic_markdown(content)
    assert strip_readonly_sections(content) == prefix + suffix
    assert strip_nonsemantic_markdown(content) == strip_html_comments_outside_fences(prefix + suffix)
    assert masked == strip_html_comments_outside_fences(prefix + blank + suffix)
    assert len(masked) == len(content)
    assert [(i, char) for i, char in enumerate(masked) if char in "\r\n"] == [
        (i, char) for i, char in enumerate(content) if char in "\r\n"
    ]


def test_readonly_scanning_work_grows_linearly_with_section_count():
    import tools.workflow_cli.markdown as markdown
    work = []
    for size in (32, 64, 128):
        content = "## Project Context (read-only)\nhidden\n<!-- /r2p-read-only -->\n" * size
        steps = 0

        def trace(frame, event, arg):
            nonlocal steps
            if frame.f_code.co_filename == markdown.__file__:
                if event == "line":
                    steps += 1
                return trace
            return None

        previous_trace = sys.gettrace()
        try:
            sys.settrace(trace)
            assert strip_readonly_sections(content) == ""
        finally:
            sys.settrace(previous_trace)
        work.append(steps)
    # Count executed source lines, not wall time or a particular implementation's
    # helper calls. Doubling input may add fixed overhead, never quadratic work.
    assert work[1] <= work[0] * 2.2, work
    assert work[2] <= work[1] * 2.2, work


@pytest.mark.parametrize("ending", ["\r\n", *"\n\r\v\f\x1c\x1d\x1e\x85\u2028\u2029"])
def test_source_mask_preserves_splitlines_boundaries_without_changing_compact_filter(ending):
    from tools.workflow_cli.markdown import mask_nonsemantic_markdown, strip_nonsemantic_markdown
    comment = f"<!-- first{ending}second -->\n"
    readonly = (
        f"## Project Context (read-only){ending}"
        f"Copied context{ending}<!-- /r2p-read-only -->{ending}"
    )
    fenced = f"```text\n<!-- literal{ending}comment -->\n```\n"
    suffix = "- [ ] PLAN-TASK-001 real task\n"
    content = comment + readonly + fenced + suffix
    masked = mask_nonsemantic_markdown(content)

    assert len(masked) == len(content)
    assert [len(line) for line in masked.splitlines(keepends=True)] == [
        len(line) for line in content.splitlines(keepends=True)
    ]
    assert masked.endswith(fenced + suffix)
    assert "Copied context" not in masked
    # The existing compact filter still blanks non-CR/LF comment separators.
    compact_comment = "".join(char if char in "\r\n" else " " for char in comment)
    assert strip_nonsemantic_markdown(content) == compact_comment + fenced + suffix

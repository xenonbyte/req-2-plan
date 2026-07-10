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

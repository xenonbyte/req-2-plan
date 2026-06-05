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

"""Journal grammar cannot treat malformed or nonsemantic records as dispatches."""
import pytest

from tools.workflow_cli.execution_journal import canonical_json, parse_execution_journal


HEADER = 'Execution Journal: ' + canonical_json({"schema": 1, "base": "a" * 40}) + '\n'
EVENT = {
    "sequence": 1, "role": "implementer", "task": 1, "fix_wave": 0,
    "profile": "strict", "base": "a" * 40, "head": "b" * 40,
    "status": "complete", "reason": "",
}


@pytest.mark.parametrize("field,value", [
    ("role", []), ("status", []), ("sequence", True), ("task", "1"),
    ("head", "b" * 7), ("reason", "first\nsecond"), ("fix_wave", -1),
])
def test_malformed_role_fields_fail_as_format_errors(field, value):
    event = dict(EVENT, **{field: value})
    with pytest.raises(ValueError):
        parse_execution_journal(HEADER + "Execution Role: " + canonical_json(event) + "\n", 1)


@pytest.mark.parametrize("wrapper", ["```text\n%s```\n", "<!--\n%s-->\n", "## Project Context (read-only)\n%s<!-- /r2p-read-only -->\n"])
def test_nonsemantic_journal_examples_never_create_roles(wrapper):
    content = HEADER + "Execution Role: " + canonical_json(EVENT) + "\n"
    assert parse_execution_journal(wrapper % content, 1) is None
    assert not parse_execution_journal(HEADER + wrapper % content, 1).events


@pytest.mark.parametrize("content", [
    HEADER + HEADER,
    "Execution Role: " + canonical_json(EVENT) + "\n" + HEADER,
    HEADER + "Execution Role: " + canonical_json(dict(EVENT, sequence=2)) + "\n",
    HEADER + "Execution Journal: invalid\n",
])
def test_duplicated_or_out_of_order_journal_is_rejected(content):
    with pytest.raises(ValueError):
        parse_execution_journal(content, 1)

"""Render STAGE_SCHEMA into per-stage, per-tier seed templates.

The CLI writes these into the stage content file so the agent starts from a
structured skeleton, not a blank page. Templates carry no semantic claims —
only headings, required gate anchors, example ID shapes, and a static trace-table skeleton.
"""
from __future__ import annotations

from tools.workflow_cli.models import Stage, TierBase
from tools.workflow_cli.stage_schema import required_headings

_TRACE_SKELETON = (
    "## Trace\n"
    "<!-- Map this stage's IDs to upstream/downstream. R3 derives & checks closure. -->\n"
    "| This ID | Upstream | Status |\n"
    "|---|---|---|\n"
)


_HEADING_BODY = {
    (Stage.REQUIREMENT_BRIEF, "## In-Scope"): "- SCOPE-IN-001 <!-- fill in -->\n",
    (Stage.REQUIREMENT_BRIEF, "## Out-of-Scope"): "- SCOPE-OUT-001 <!-- fill in -->\n",
    (Stage.RISK_DISCOVERY, "## Risks"): "### RISK-SEC-001 <!-- fill in -->\nStatus: <!-- fill in -->\n",
    (Stage.DESIGN, "## Chosen Design"): "### DES-ARCH-001 <!-- fill in -->\n",
    (Stage.DESIGN, "## Decision Requests"): (
        "<!-- fill in -->\n"
        "<!-- Write exactly `none` when no human decision is needed; otherwise list one `### DECISION-NNN` block per choice (fenced example below; keep guidance comments single-line). -->\n"
        "```text\n"
        "### DECISION-001 <short title>\n"
        "Question: <what must a human choose?>\n"
        "Options: A) ... / B) ...\n"
        "Recommended: A\n"
        "Status: pending\n"
        "```\n"
    ),
    (Stage.SPEC, "## Behavior Contracts"): "### SPEC-BEHAVIOR-001 <!-- fill in -->\n",
    (Stage.PLAN, "## Tasks"): (
        "### PLAN-TASK-001 <!-- fill in -->\n"
        "Spec References: SPEC-BEHAVIOR-001\n"
        "Change Type: modify\n"
        "TDD Applicable: yes\n"
        "Files:\n"
        "- <!-- fill in -->\n"
        "Skeleton:\n"
        "```python\n"
        "# <!-- fill in -->\n"
        "```\n"
        "Steps:\n"
        "- [ ] <!-- fill in -->\n"
        "Verification: <!-- fill in -->\n"
    ),
}


def _body_for(stage: Stage, heading: str) -> str:
    return _HEADING_BODY.get((stage, heading), "<!-- fill in -->\n")


def template_for(stage: Stage, tier_base: TierBase) -> str:
    headings = required_headings(stage, tier_base)
    title = stage.value.replace("_", " ").title()
    parts = [f"# {title}\n"]
    for h in headings:
        parts.append(f"{h}\n{_body_for(stage, h)}")
    parts.append(_TRACE_SKELETON)
    return "\n".join(parts)

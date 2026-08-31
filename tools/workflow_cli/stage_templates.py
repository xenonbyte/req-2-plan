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

_PLAN_GRANULARITY_NOTE = (
    "<!-- Granularity / PLAN formation: one PLAN-TASK = one implementer subagent and one task-reviewer; form a phase-level cohesive slice around one observable behavior or contract result. "
    "If it needs both create and modify paths, R19 requires an operation-homogeneous task group: every task's "
    "Files list contains only one operation and every task delivers an executable intermediate contract with direct tests. "
    "Do not split by file/class alone, create a wrapper before its target, or merge unrelated behavior into a mega-task; "
    "the group's final integration/adoption task runs Phase acceptance. -->\n"
    "<!-- Steps contract: the first semantic line is exactly `Prerequisite: none` or `Prerequisite: PLAN-TASK-NNN`. "
    "Declare only direct predecessors inside this task group; cross-Phase order remains PLAN order and prior Phase acceptance. "
    "Each generated v2 PLAN Verification first runs `execution-prerequisite-check --work-id <id> --task <N> --require-version 2`; "
    "it uses profile-aware prerequisite semantics and fails closed on malformed, discontinuous, or non-actionable state. -->\n"
    "<!-- Rollback: derive declared dependents only from this group's prerequisite lines. Roll back one task only after its group's "
    "declared dependents; roll back a whole group in reverse topological order without touching another Phase. Do not add a dependency field. -->\n"
)  # PLN-5, seeded under "## Tasks" (an HTML comment carries no gate-scanned placeholder token)

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
        _PLAN_GRANULARITY_NOTE
        + "### PLAN-TASK-001 <!-- fill in -->\n"
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
        "Verification: <!-- fill in: (1) targeted: `pytest tests/test_x.py::test_y -v` — this task's "
        "plus directly-affected tests pass; (2) evidence: paste actual output showing pass count and "
        "zero failures. Run the full suite here only when it is cheap or this task touches shared/core "
        "code; the mandatory full-suite regression run happens once at the final review, not every task. -->\n"
    ),
}

_OPTIONAL_SECTIONS: dict[Stage, str] = {
    Stage.PLAN: (
        "## Execution Readiness\n"
        "<!-- optional pre-execution self-check; remove if unused -->\n"
        "- Requirement brief reviewed\n"
        "- Design decisions resolved; decision requests pending none\n"
        "- High-risk mitigations represented in tasks\n"
        "- Non-goals protected\n"
        "- Verification commands executable; expected changed files listed\n"
        "- No unresolved ambiguity; out-of-scope work is declared in the brief, not dropped here\n"
        "\n"
        "## Risk Handling\n"
        "<!-- optional risk-to-task map; RISK-* IDs live in cells only, each row carries a same-line closure tag -->\n"
        "| Risk | Handling Task | Closure |\n"
        "|---|---|---|\n"
        "| RISK-EXAMPLE-001 | PLAN-TASK-001 | [ADDRESSED] |\n"
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
    parts.append(_OPTIONAL_SECTIONS.get(stage, ""))  # additive; empty for non-PLAN stages
    parts.append(_TRACE_SKELETON)
    return "\n".join(p for p in parts if p)

import re

from tools.workflow_cli.models import Stage, TierBase

# Structural fields every PLAN-TASK anchor must carry (gate + trace share these).
PLAN_TASK_FIELDS = (
    "Spec References",
    "Change Type",
    "TDD Applicable",
    "Files",
    "Skeleton",
    "Steps",
    "Verification",
)
# Matches a line that opens one of those fields, e.g. "Files: src/a.py".
PLAN_TASK_FIELD_RE = re.compile(r"^(" + "|".join(PLAN_TASK_FIELDS) + r"):")

# Headings MUST stay byte-identical to any existing gate regex they overlap.
# Notably "## External Documentation Checked" matches gates.py:_EXTERNAL_DOCS_RE.
STAGE_SCHEMA: dict = {
    Stage.REQUIREMENT_BRIEF: {
        TierBase.LIGHT: ["## Goal", "## In-Scope", "## Out-of-Scope", "## Acceptance Criteria"],
        TierBase.STANDARD: [
            "## Goal", "## In-Scope", "## Out-of-Scope", "## Non-Goals",
            "## Assumptions", "## Acceptance Criteria", "## Open Questions", "## Sources",
        ],
    },
    Stage.RISK_DISCOVERY: {
        TierBase.LIGHT: ["## Risks", "## Boundaries"],
        TierBase.STANDARD: ["## Risks", "## Boundaries", "## Scope Overflow Risks", "## Mitigations"],
    },
    Stage.DESIGN: {
        TierBase.LIGHT: ["## Design Summary", "## Chosen Design", "## SPEC Handoff"],
        TierBase.STANDARD: [
            "## Design Summary", "## Current Code Evidence", "## Requirements Coverage",
            "## Options Considered", "## Chosen Design", "## Rollback",
            "## Observability", "## SPEC Handoff",
        ],
    },
    Stage.SPEC: {
        TierBase.LIGHT: ["## Behavior Contracts", "## External Documentation Checked", "## PLAN Handoff"],
        TierBase.STANDARD: [
            "## Behavior Contracts", "## API / Data / Config Contracts",
            "## External Documentation Checked", "## Test Matrix", "## Non-goals", "## PLAN Handoff",
        ],
    },
    Stage.PLAN: {
        # PLAN's substantive checks (task coverage, fields) live in R5, not R2.
        TierBase.LIGHT: ["## Tasks"],
        TierBase.STANDARD: ["## Tasks"],
    },
}


def required_headings(stage: Stage, tier_base: TierBase) -> list[str]:
    """Required top-level headings for a stage at a tier base; [] if unschema'd."""
    return list(STAGE_SCHEMA.get(stage, {}).get(tier_base, []))

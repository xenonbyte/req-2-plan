"""
Tier-aware structured gate checks for the req-to-plan workflow CLI.

The CLI runs these structural checks before checkpoint approval.
The Agent handles semantic quality; this module handles structural validation.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from tools.workflow_cli.models import (
    BundleAuthorization,
    CheckpointRecord,
    STAGE_ARTIFACT_MAP,
    STAGE_REQUIRED_UPSTREAM_CHECKPOINTS,
    Stage,
    TierEstimate,
    TierModifier,
)
from tools.workflow_cli.output import EXIT_GATE_FAIL

# ---------------------------------------------------------------------------
# GateResult
# ---------------------------------------------------------------------------

@dataclass
class GateResult:
    passed: bool
    issues: list[str]
    exit_code: int = 0  # 0=pass, 2=entry failure, 3=quality failure, 5=forced-subagent-review-required


# ---------------------------------------------------------------------------
# Entry Gate
# ---------------------------------------------------------------------------

def check_entry_gate(
    run_dir: Path,
    stage: Stage,
    approved_checkpoints: list,  # list[CheckpointRecord]
    bundle_authorizations: list,  # list[BundleAuthorization]
) -> GateResult:
    """Check entry gate: all required upstream artifacts are approved and present."""
    issues: list[str] = []
    required_stages = STAGE_REQUIRED_UPSTREAM_CHECKPOINTS.get(stage, [])

    # Build set of stages covered by approved checkpoints
    approved_stages: set[Stage] = {cp.stage for cp in approved_checkpoints}

    for upstream_stage in required_stages:
        # Check 1: is there an approval or live bundle covering this stage?
        covered = upstream_stage in approved_stages or any(
            ba.covers(upstream_stage) for ba in bundle_authorizations
        )
        if not covered:
            issues.append(
                f"Missing approval for upstream stage {upstream_stage.value!r}: "
                "no approved checkpoint and no live bundle authorization."
            )
            continue  # Skip file-existence check when no authorization exists

        # Check 2: the artifact file must exist on disk
        artifact_filename = STAGE_ARTIFACT_MAP.get(upstream_stage)
        if artifact_filename:
            artifact_path = run_dir / artifact_filename
            if not artifact_path.exists():
                issues.append(
                    f"Upstream artifact file missing for stage {upstream_stage.value!r}: "
                    f"{artifact_filename}"
                )

    return GateResult(
        passed=len(issues) == 0,
        issues=issues,
        exit_code=EXIT_GATE_FAIL if issues else 0,
    )


# ---------------------------------------------------------------------------
# Upstream ID reference pattern
# ---------------------------------------------------------------------------

# IDs that represent upstream references: REQ-*, RISK-*, DES-*, SPEC-*
_UPSTREAM_ID_PATTERN = re.compile(
    r"\b(REQ-[A-Z]+-\d+|RISK-[A-Z]+-\d+|DES-[A-Z]+-\d+|SPEC-[A-Z]+-\d+)\b"
)

# Closure status tags
_CLOSURE_TAGS = frozenset(["[ADDRESSED]", "[DEFERRED]", "[N/A]", "[OUT-OF-SCOPE]", "[CLOSED]"])

# IDs of form [A-Z]+-[A-Z]+-[0-9]+ (definition context: heading or line-start)
_DEFINED_ID_PATTERN = re.compile(r"\b([A-Z]+-[A-Z]+-\d+)\b")


def _find_defined_ids(content: str) -> set[str]:
    """Return IDs that are defined in headings (i.e. the current artifact is defining them)."""
    heading_pattern = re.compile(r"^#{1,6}\s+.*\b([A-Z]+-[A-Z]+-\d+)\b", re.MULTILINE)
    return set(heading_pattern.findall(content))


def _find_ids_without_closure(content: str) -> list[str]:
    """Return upstream IDs referenced in content that have no closure tag.

    IDs defined in headings of the current artifact are excluded — they are
    being *defined* here, not referencing upstream artifacts that need closure.
    """
    all_refs = set(_UPSTREAM_ID_PATTERN.findall(content))
    defined_here = _find_defined_ids(content)
    # Only check IDs that are referenced but NOT defined in this artifact
    refs_to_check = all_refs - defined_here
    unclosed: list[str] = []
    for ref_id in sorted(refs_to_check):
        # Look for the ID followed (anywhere on the same token-group) by a closure tag
        # We search for patterns like: ID [TAG] anywhere in content
        has_closure = False
        for tag in _CLOSURE_TAGS:
            # Allow flexible spacing between ID and tag on the same general vicinity
            pattern = re.compile(
                re.escape(ref_id) + r"[^\n]*" + re.escape(tag),
                re.IGNORECASE,
            )
            if pattern.search(content):
                has_closure = True
                break
        if not has_closure:
            unclosed.append(ref_id)
    return unclosed


def _find_duplicate_ids(content: str) -> list[str]:
    """Return IDs that appear more than once in heading (definition) context."""
    heading_pattern = re.compile(r"^#{1,6}\s+.*\b([A-Z]+-[A-Z]+-\d+)\b", re.MULTILINE)
    heading_ids = heading_pattern.findall(content)

    from collections import Counter
    counts = Counter(heading_ids)
    return [id_ for id_, count in counts.items() if count > 1]


# ---------------------------------------------------------------------------
# SPEC External Documentation Checked helpers
# ---------------------------------------------------------------------------

_EXTERNAL_DOCS_RE = re.compile(r"^## External Documentation Checked\s*$", re.MULTILINE)
_H2_RE = re.compile(r"^##\s+", re.MULTILINE)
_MARKDOWN_CODE_FENCE_RE = re.compile(r"^[ \t]{0,3}(`{3,}|~{3,})", re.MULTILINE)
_MARKDOWN_FENCE_MARKER_RE = re.compile(r"^[ \t]{0,3}(`{3,}|~{3,})")
_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _unfenced_markdown_lines(content: str):
    """Yield (line, start, end) for lines outside Markdown fenced code blocks."""
    fence_char = ""
    fence_len = 0
    offset = 0
    for line in content.splitlines(keepends=True):
        marker = _MARKDOWN_FENCE_MARKER_RE.match(line)
        if fence_char:
            if (
                marker
                and marker.group(1)[0] == fence_char
                and len(marker.group(1)) >= fence_len
                and not line[marker.end():].strip()
            ):
                fence_char = ""
                fence_len = 0
            offset += len(line)
            continue

        if marker:
            fence_char = marker.group(1)[0]
            fence_len = len(marker.group(1))
            offset += len(line)
            continue

        start = offset
        offset += len(line)
        yield line, start, offset


def _plain_table_cell(cell: str) -> str:
    return cell.strip().strip("_*`").strip()


def _is_external_docs_inventory_row(line: str) -> bool:
    if line == "N/A — no external dependencies":
        return True
    if not (line.startswith("|") and line.endswith("|")):
        return False
    cells = [cell.strip() for cell in line.strip("|").split("|")]
    if len(cells) != 4:
        return False
    if [cell.lower() for cell in cells] == ["dependency", "version", "check date", "conclusion"]:
        return False
    if all(set(cell) <= {"-", ":", " "} for cell in cells):
        return False
    if not all(cells):
        return False

    dependency, version, check_date, conclusion = [_plain_table_cell(cell) for cell in cells]
    normalized = [cell.lower() for cell in (dependency, version, check_date, conclusion)]
    if normalized == ["example", "x.y", "yyyy-mm-dd", "context7 checked / unconfirmed"]:
        return False
    if dependency.lower() == "example":
        return False
    if version.lower() == "x.y":
        return False
    if check_date.lower() == "yyyy-mm-dd":
        return False
    if conclusion.lower() == "context7 checked / unconfirmed":
        return False
    if not _ISO_DATE_RE.fullmatch(check_date):
        return False
    return bool(dependency and version and conclusion)


def _has_external_docs_inventory(content: str) -> bool:
    section_start = None
    for line, _, end in _unfenced_markdown_lines(content):
        if _EXTERNAL_DOCS_RE.match(line):
            section_start = end
            break
    if section_start is None:
        return False

    for line, start, _ in _unfenced_markdown_lines(content):
        if start < section_start:
            continue
        if _H2_RE.match(line):
            break
        stripped = line.strip()
        if stripped and _is_external_docs_inventory_row(stripped):
            return True
    return False


# ---------------------------------------------------------------------------
# PLAN code-block gate helpers
# ---------------------------------------------------------------------------

_PLAN_TASK_RE = re.compile(r"^### PLAN-TASK-\d+", re.MULTILINE)
_TDD_YES_RE = re.compile(r"TDD Applicable:\s*yes", re.IGNORECASE)
_CODE_FENCE_RE = _MARKDOWN_CODE_FENCE_RE
_PLAN_TASK_FIELD_RE = re.compile(
    r"^(Spec References|Change Type|TDD Applicable|Files|Skeleton|Steps|Verification):",
    re.MULTILINE,
)


def _plan_task_starts(content: str) -> list[int]:
    return [
        start
        for line, start, _ in _unfenced_markdown_lines(content)
        if _PLAN_TASK_RE.match(line)
    ]


def _plan_task_field_body(task_body: str, field: str) -> str:
    field_re = re.compile(rf"^{re.escape(field)}:[ \t]*(.*)$", re.MULTILINE)
    match = field_re.search(task_body)
    if not match:
        return ""
    next_match = _PLAN_TASK_FIELD_RE.search(task_body, match.end())
    end = next_match.start() if next_match else len(task_body)
    return f"{match.group(1)}\n{task_body[match.end():end]}"


def _plan_tasks_missing_code(content: str) -> bool:
    """True if any TDD-applicable PLAN-TASK has no fenced code block in its Skeleton field."""
    starts = _plan_task_starts(content)
    if not starts:
        return False
    bounds = starts + [len(content)]
    for i in range(len(starts)):
        body = content[bounds[i]:bounds[i + 1]]
        skeleton = _plan_task_field_body(body, "Skeleton")
        if _TDD_YES_RE.search(body) and not _CODE_FENCE_RE.search(skeleton):
            return True
    return False


# ---------------------------------------------------------------------------
# Quality Gate
# ---------------------------------------------------------------------------

def check_quality_gate(
    run_dir: Path,
    stage: Stage,
    tier: TierEstimate | None,
    approved_checkpoints: list,  # list[CheckpointRecord]
    artifact_content: str,
) -> GateResult:
    """Check quality gate: tier-aware structural content checks."""
    # Check 1: tier must be locked
    if tier is None:
        return GateResult(
            passed=False,
            issues=["Tier not locked; run tier-lock before quality gate"],
            exit_code=3,
        )

    issues: list[str] = []

    # Check 2: content must be non-empty
    if not artifact_content or not artifact_content.strip():
        issues.append("Artifact content is empty or whitespace-only.")

    if not issues:
        # Check 3: upstream reference coverage closure (all tiers)
        unclosed = _find_ids_without_closure(artifact_content)
        for ref_id in unclosed:
            issues.append(
                f"Upstream reference {ref_id!r} appears in artifact but has no closure status tag "
                f"([ADDRESSED], [DEFERRED], [N/A], [OUT-OF-SCOPE], or [CLOSED])."
            )

        # Check 4: ID uniqueness within artifact
        duplicates = _find_duplicate_ids(artifact_content)
        for dup_id in duplicates:
            issues.append(
                f"Duplicate ID definition {dup_id!r} found in artifact; each ID must be unique."
            )

        # Check 5 (PLAN, standard tier): TDD-applicable tasks must carry a code block.
        from tools.workflow_cli.models import TierBase
        if stage == Stage.PLAN and tier.base == TierBase.STANDARD:
            if not _plan_task_starts(artifact_content):
                issues.append(
                    "PLAN is missing '### PLAN-TASK-*' sections; standard tier requires "
                    "machine-parseable executable anchors."
                )
            elif _plan_tasks_missing_code(artifact_content):
                issues.append(
                    "PLAN has a 'TDD Applicable: yes' task with no fenced code block; "
                    "add a Skeleton code block (standard tier requires executable anchors)."
                )

        # Check 6 (SPEC): the External Documentation Checked section must be present and non-empty.
        if stage == Stage.SPEC:
            if not _has_external_docs_inventory(artifact_content):
                issues.append(
                    "SPEC is missing a non-empty '## External Documentation Checked' section. "
                    "Add it; if there are no external dependencies, include an explicit "
                    "'N/A — no external dependencies' row."
                )

    return GateResult(
        passed=len(issues) == 0,
        issues=issues,
        exit_code=3 if issues else 0,
    )


# ---------------------------------------------------------------------------
# Forced Subagent Review Check
# ---------------------------------------------------------------------------

_FORCED_REVIEW_MODIFIERS: frozenset[TierModifier] = frozenset({
    TierModifier.MIGRATION,
    TierModifier.SAFETY,
    TierModifier.CROSS_PROJECT,
})

_FORCED_REVIEW_STAGES: frozenset[Stage] = frozenset({
    Stage.DESIGN,
    Stage.SPEC,
    Stage.PLAN,
})


def check_forced_subagent_review(
    stage: Stage,
    tier: TierEstimate | None,
    reviews_dir: Path,
    version: int = 1,
) -> GateResult:
    """
    Refuse with exit_code=5 when ALL conditions hold:
    - tier is not None
    - tier.modifiers intersects {MIGRATION, SAFETY, CROSS_PROJECT}
    - stage is in {DESIGN, SPEC, PLAN}
    - no version-matched subagent review file exists under reviews_dir for this stage
    """
    # Condition 1: tier must exist
    if tier is None:
        return GateResult(passed=True, issues=[], exit_code=0)

    # Condition 2: modifiers must intersect forced-review set
    if not (tier.modifiers & _FORCED_REVIEW_MODIFIERS):
        return GateResult(passed=True, issues=[], exit_code=0)

    # Condition 3: stage must be in forced-review stages
    if stage not in _FORCED_REVIEW_STAGES:
        return GateResult(passed=True, issues=[], exit_code=0)

    # Condition 4: a real, version-matched subagent review must exist.
    stage_name = stage.value
    subagent_file = reviews_dir / f"{stage_name}-subagent-review-v{version}.md"
    if subagent_file.exists():
        return GateResult(passed=True, issues=[], exit_code=0)

    # All conditions met: require forced subagent review
    triggering = sorted(m.value for m in tier.modifiers & _FORCED_REVIEW_MODIFIERS)
    return GateResult(
        passed=False,
        issues=[
            f"Forced subagent review required for stage {stage.value!r} "
            f"with modifier(s) {triggering!r}. "
            f"No version-matched review file '{subagent_file.name}' found in {reviews_dir}. "
            f"Run subagent review before checkpoint approval."
        ],
        exit_code=5,
    )

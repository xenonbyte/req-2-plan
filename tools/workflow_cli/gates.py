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

"""
Core data models for the req-to-plan workflow CLI.
Python 3.10+ required (uses X | Y union syntax).
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional

from tools.workflow_cli.version import R2P_VERSION


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class RunStatus(str, Enum):
    NOT_STARTED = "not_started"
    ACTIVE_STAGE_DRAFT = "active_stage_draft"
    ENTRY_GATE_FAILED = "entry_gate_failed"
    QUALITY_GATE_FAILED = "quality_gate_failed"
    READY_FOR_CHECKPOINT_REVIEW = "ready_for_checkpoint_review"
    CHECKPOINT_REVIEW = "checkpoint_review"
    CHECKPOINT_CHANGES_REQUESTED = "checkpoint_changes_requested"
    UPSTREAM_GAP_ROUTING = "upstream_gap_routing"
    CHECKPOINT_APPROVED = "checkpoint_approved"
    NEXT_STAGE = "next_stage"
    CLOSED_AT_PLAN_CHECKPOINT = "closed_at_plan_checkpoint"


class Stage(str, Enum):
    RAW_REQUIREMENT = "raw_requirement"
    REQUIREMENT_BRIEF = "requirement_brief"
    RISK_DISCOVERY = "risk_discovery"
    DESIGN = "design"
    SPEC = "spec"
    PLAN = "plan"
    CLOSED = "closed"


class TierBase(str, Enum):
    LIGHT = "light"
    STANDARD = "standard"


class TierModifier(str, Enum):
    MIGRATION = "migration"
    CROSS_PROJECT = "cross_project"
    SAFETY = "safety"
    DEPENDENCY = "dependency"
    SCOPE_EXPANDING = "scope_expanding"


# ---------------------------------------------------------------------------
# Stage constants
# ---------------------------------------------------------------------------

STAGE_ORDER: list[Stage] = [
    Stage.RAW_REQUIREMENT,
    Stage.REQUIREMENT_BRIEF,
    Stage.RISK_DISCOVERY,
    Stage.DESIGN,
    Stage.SPEC,
    Stage.PLAN,
]

NEXT_STAGE_MAP: dict[Stage, Stage] = {
    Stage.RAW_REQUIREMENT: Stage.REQUIREMENT_BRIEF,
    Stage.REQUIREMENT_BRIEF: Stage.RISK_DISCOVERY,
    Stage.RISK_DISCOVERY: Stage.DESIGN,
    Stage.DESIGN: Stage.SPEC,
    Stage.SPEC: Stage.PLAN,
}

STAGE_ARTIFACT_MAP: dict[Stage, str] = {
    Stage.RAW_REQUIREMENT: "00-raw-requirement.md",
    Stage.REQUIREMENT_BRIEF: "03-requirement-brief.md",
    Stage.RISK_DISCOVERY: "04-risk-discovery.md",
    Stage.DESIGN: "05-design.md",
    Stage.SPEC: "06-spec.md",
    Stage.PLAN: "07-plan.md",
}

STAGE_REQUIRED_UPSTREAM_CHECKPOINTS: dict[Stage, list[Stage]] = {
    Stage.RAW_REQUIREMENT: [],
    Stage.REQUIREMENT_BRIEF: [],
    Stage.RISK_DISCOVERY: [Stage.REQUIREMENT_BRIEF],
    Stage.DESIGN: [Stage.REQUIREMENT_BRIEF, Stage.RISK_DISCOVERY],
    Stage.SPEC: [Stage.REQUIREMENT_BRIEF, Stage.RISK_DISCOVERY, Stage.DESIGN],
    Stage.PLAN: [Stage.REQUIREMENT_BRIEF, Stage.RISK_DISCOVERY, Stage.DESIGN, Stage.SPEC],
}


# ---------------------------------------------------------------------------
# State machine
# ---------------------------------------------------------------------------

ALLOWED_TRANSITIONS: dict[RunStatus, set[RunStatus]] = {
    RunStatus.NOT_STARTED: {RunStatus.ACTIVE_STAGE_DRAFT},
    RunStatus.ACTIVE_STAGE_DRAFT: {
        RunStatus.ACTIVE_STAGE_DRAFT,
        RunStatus.ENTRY_GATE_FAILED,
        RunStatus.QUALITY_GATE_FAILED,
        RunStatus.READY_FOR_CHECKPOINT_REVIEW,
        RunStatus.UPSTREAM_GAP_ROUTING,
    },
    RunStatus.ENTRY_GATE_FAILED: {
        RunStatus.ACTIVE_STAGE_DRAFT,
        RunStatus.UPSTREAM_GAP_ROUTING,
    },
    RunStatus.QUALITY_GATE_FAILED: {
        RunStatus.ACTIVE_STAGE_DRAFT,
        RunStatus.UPSTREAM_GAP_ROUTING,
    },
    RunStatus.READY_FOR_CHECKPOINT_REVIEW: {
        RunStatus.ACTIVE_STAGE_DRAFT,
        RunStatus.CHECKPOINT_REVIEW,
        RunStatus.UPSTREAM_GAP_ROUTING,
    },
    RunStatus.CHECKPOINT_REVIEW: {
        RunStatus.ACTIVE_STAGE_DRAFT,
        RunStatus.CHECKPOINT_CHANGES_REQUESTED,
        RunStatus.CHECKPOINT_APPROVED,
        RunStatus.UPSTREAM_GAP_ROUTING,
    },
    RunStatus.CHECKPOINT_CHANGES_REQUESTED: {
        RunStatus.ACTIVE_STAGE_DRAFT,
        RunStatus.QUALITY_GATE_FAILED,
        RunStatus.UPSTREAM_GAP_ROUTING,
    },
    RunStatus.UPSTREAM_GAP_ROUTING: {
        RunStatus.ACTIVE_STAGE_DRAFT,
        RunStatus.UPSTREAM_GAP_ROUTING,
        RunStatus.READY_FOR_CHECKPOINT_REVIEW,
        RunStatus.CHECKPOINT_APPROVED,
    },
    RunStatus.CHECKPOINT_APPROVED: {
        RunStatus.NEXT_STAGE,
        RunStatus.CLOSED_AT_PLAN_CHECKPOINT,
        RunStatus.UPSTREAM_GAP_ROUTING,
    },
    RunStatus.NEXT_STAGE: {
        RunStatus.ACTIVE_STAGE_DRAFT,
        RunStatus.ENTRY_GATE_FAILED,
    },
    RunStatus.CLOSED_AT_PLAN_CHECKPOINT: set(),
}


def is_transition_allowed(from_status: RunStatus, to_status: RunStatus) -> bool:
    return to_status in ALLOWED_TRANSITIONS.get(from_status, set())


# ---------------------------------------------------------------------------
# Command eligibility
# ---------------------------------------------------------------------------

READ_ONLY_COMMANDS: set[str] = {
    "CMD-STATUS-RUN",
    "CMD-STATUS-STAGE",
    "CMD-STATUS-NEXT",
    "CMD-STATUS-ROUTES",
    "CMD-STATUS-ARTIFACTS",
    "CMD-TIER-STATUS",
    "CMD-RUN-RESUME",
}

ALLOWED_COMMANDS_BY_RUN_STATE: dict[RunStatus, set[str]] = {
    RunStatus.NOT_STARTED: {"CMD-RUN-START"},
    RunStatus.ACTIVE_STAGE_DRAFT: {
        "CMD-STAGE-LOAD",
        "CMD-STAGE-PRODUCE",
        "CMD-STAGE-READY",
        "CMD-GATE-ENTRY",
        "CMD-GATE-QUALITY",
        "CMD-CONFIRM-RECORD",
        "CMD-CONFIRM-REJECT",
        "CMD-CONFIRM-LINK",
        "CMD-SUBAGENT-DISPATCH",
        "CMD-SUBAGENT-MERGE",
        "CMD-GAP-RECORD",
        "CMD-TIER-ESTIMATE",
        "CMD-TIER-LOCK",
        "CMD-TIER-ESCALATE",
        "CMD-TIER-STATUS",
    },
    RunStatus.ENTRY_GATE_FAILED: {
        "CMD-GATE-ENTRY",
        "CMD-CONFIRM-RECORD",
        "CMD-CONFIRM-REJECT",
        "CMD-GAP-RECORD",
        "CMD-GAP-ROUTE",
        "CMD-TIER-ESTIMATE",
        "CMD-TIER-ESCALATE",
        "CMD-TIER-STATUS",
    },
    RunStatus.QUALITY_GATE_FAILED: {
        "CMD-STAGE-PRODUCE",
        "CMD-STAGE-UPDATE",
        "CMD-STAGE-READY",
        "CMD-CONFIRM-RECORD",
        "CMD-CONFIRM-REJECT",
        "CMD-SUBAGENT-DISPATCH",
        "CMD-SUBAGENT-MERGE",
        "CMD-GAP-RECORD",
        "CMD-GAP-ROUTE",
        "CMD-TIER-ESCALATE",
        "CMD-TIER-STATUS",
    },
    RunStatus.READY_FOR_CHECKPOINT_REVIEW: {
        "CMD-STAGE-UPDATE",
        "CMD-REVIEW-CHECKPOINT",
        "CMD-SUBAGENT-REVIEW",
        "CMD-GAP-RECORD",
        "CMD-TIER-ESCALATE",
        "CMD-TIER-STATUS",
    },
    RunStatus.CHECKPOINT_REVIEW: {
        "CMD-REVIEW-CHECKPOINT",
        "CMD-SUBAGENT-REVIEW",
        "CMD-REVIEW-MERGE",
        "CMD-CONFIRM-RECORD",
        "CMD-CONFIRM-REJECT",
        "CMD-CONFIRM-LINK",
        "CMD-CHECKPOINT-DECIDE",
        "CMD-CHECKPOINT-BUNDLE",
        "CMD-GAP-RECORD",
        "CMD-GAP-ROUTE",
        "CMD-TIER-ESCALATE",
        "CMD-TIER-STATUS",
    },
    RunStatus.CHECKPOINT_CHANGES_REQUESTED: {
        "CMD-STAGE-PRODUCE",
        "CMD-STAGE-UPDATE",
        "CMD-CONFIRM-RECORD",
        "CMD-CONFIRM-REJECT",
        "CMD-SUBAGENT-DISPATCH",
        "CMD-SUBAGENT-MERGE",
        "CMD-GAP-RECORD",
        "CMD-GAP-ROUTE",
        "CMD-TIER-ESCALATE",
        "CMD-TIER-STATUS",
    },
    RunStatus.UPSTREAM_GAP_ROUTING: {
        "CMD-GAP-RECORD",
        "CMD-GAP-ROUTE",
        "CMD-GAP-REIMPORT",
        "CMD-ARTIFACT-MARK-STALE",
        "CMD-CONFIRM-RECORD",
        "CMD-CONFIRM-REJECT",
        "CMD-TIER-ESCALATE",
        "CMD-TIER-STATUS",
    },
    RunStatus.CHECKPOINT_APPROVED: {
        "CMD-RUN-CLOSE",
        "CMD-STAGE-ADVANCE",
        "CMD-TIER-STATUS",
    },
    RunStatus.NEXT_STAGE: {
        "CMD-GATE-ENTRY",
        "CMD-TIER-ESCALATE",
        "CMD-TIER-STATUS",
    },
    RunStatus.CLOSED_AT_PLAN_CHECKPOINT: {
        "CMD-RUN-REOPEN",
        "CMD-TIER-STATUS",
    },
}


def is_command_allowed(status: RunStatus, command: str) -> bool:
    if command in READ_ONLY_COMMANDS:
        return True
    return command in ALLOWED_COMMANDS_BY_RUN_STATE.get(status, set())


# ---------------------------------------------------------------------------
# WorkId
# ---------------------------------------------------------------------------

class WorkId(str):
    _PATTERN = re.compile(r"^WF-\d{8}-[a-z0-9][a-z0-9\-]{1,38}[a-z0-9]$")

    def __new__(cls, value: str) -> "WorkId":
        if not cls._PATTERN.match(value):
            raise ValueError(
                f"Invalid WorkId format: {value!r}. Must match WF-YYYYMMDD-slug"
            )
        return str.__new__(cls, value)

    @classmethod
    def generate(cls, requirement: str) -> "WorkId":
        date_str = datetime.now().strftime("%Y%m%d")
        # Try to create slug from ASCII words
        slug = re.sub(r"[^a-zA-Z0-9\s]", "", requirement).lower().strip()
        words = slug.split()
        if words:
            candidate = "-".join(words[:6])[:40]
            candidate = re.sub(r"-+", "-", candidate).strip("-")
            if len(candidate) >= 2:
                try:
                    return cls(f"WF-{date_str}-{candidate}")
                except ValueError:
                    pass
        # Fallback: hash-based slug
        hash_suffix = hashlib.md5(requirement.encode()).hexdigest()[:8]
        return cls(f"WF-{date_str}-run-{hash_suffix}")


# ---------------------------------------------------------------------------
# Tier models
# ---------------------------------------------------------------------------

_TIER_BASE_ORDER = [TierBase.LIGHT, TierBase.STANDARD]


@dataclass(frozen=True)
class TierEstimate:
    base: TierBase
    modifiers: frozenset[TierModifier] = field(default_factory=frozenset)
    _floor_base: TierBase | None = field(default=None, compare=False, repr=False)
    _floor_modifiers: frozenset[TierModifier] | None = field(
        default=None, compare=False, repr=False
    )

    def floor(self) -> "TierEstimate":
        """Return this estimate treated as its own floor (used for lock validation)."""
        return TierEstimate(
            base=self.base,
            modifiers=self.modifiers,
            _floor_base=self.base,
            _floor_modifiers=self.modifiers,
        )

    def is_above_floor(self) -> bool:
        """True when this estimate is stricter than the recorded floor."""
        if self._floor_base is None:
            return False
        if _TIER_BASE_ORDER.index(self.base) > _TIER_BASE_ORDER.index(self._floor_base):
            return True
        return self.modifiers > (self._floor_modifiers or frozenset())

    def escalate(self, modifier: TierModifier) -> "TierEstimate":
        """Return a new estimate with the modifier added (immutable)."""
        new_mods = self.modifiers | frozenset({modifier})
        new_base = TierBase.STANDARD if modifier == TierModifier.SCOPE_EXPANDING else self.base
        return TierEstimate(
            base=new_base,
            modifiers=new_mods,
            _floor_base=self._floor_base,
            _floor_modifiers=self._floor_modifiers,
        )

    def lock(
        self,
        user_base: TierBase,
        user_modifiers: frozenset[TierModifier],
    ) -> "TierEstimate":
        """Lock tier to user-specified values; raises ValueError if below floor."""
        # Derives floor from self.base/self.modifiers (not from _floor_base which is only for is_above_floor)
        floor = self.floor()
        if _TIER_BASE_ORDER.index(user_base) < _TIER_BASE_ORDER.index(floor.base):
            raise ValueError(
                f"Cannot lock tier below floor: requested {user_base.value}, "
                f"floor is {floor.base.value}"
            )
        if not user_modifiers.issuperset(floor.modifiers):
            raise ValueError(
                f"Missing required modifiers: {floor.modifiers - user_modifiers}"
            )
        return TierEstimate(
            base=user_base,
            modifiers=user_modifiers,
            _floor_base=self.base,
            _floor_modifiers=self.modifiers,
        )


# ---------------------------------------------------------------------------
# Evidence block
# ---------------------------------------------------------------------------

@dataclass
class EvidenceBlock:
    keywords_hit: list[str] | None = None
    repo_baseline_summary: str | None = None
    linked_context: str | None = None
    scope_signals: list[str] | None = None
    escalation_candidates: list[str] | None = None
    floor: TierEstimate | None = None
    confirm_status: str | None = None  # "pending" | "confirmed" | "overridden"

    def validate_for_lock(self) -> None:
        required = ["keywords_hit", "repo_baseline_summary", "floor", "confirm_status"]
        missing = [f for f in required if getattr(self, f) is None]
        if missing:
            raise ValueError(
                f"EvidenceBlock missing required fields for lock: {missing}"
            )


# ---------------------------------------------------------------------------
# Bundle authorization
# ---------------------------------------------------------------------------

@dataclass
class BundleAuthorization:
    bundle_id: str
    stages: frozenset[Stage]
    authorized_at: str
    revoked_at: str | None = None
    consumed_by_stage: dict[str, str] = field(default_factory=dict)  # stage.value → approved_at

    def is_live(self) -> bool:
        if self.revoked_at is not None:
            return False
        consumed = {Stage(k) for k in self.consumed_by_stage}
        return not self.stages.issubset(consumed)

    def covers(self, stage: Stage) -> bool:
        if not self.is_live():
            return False
        if stage not in self.stages:
            return False
        return stage.value not in self.consumed_by_stage


# ---------------------------------------------------------------------------
# Supporting dataclasses
# ---------------------------------------------------------------------------

@dataclass
class CheckpointRecord:
    stage: Stage
    artifact: str
    version: int
    approved_at: str
    downstream_authorization: str
    bundle_id: str | None = None


@dataclass
class ActiveArtifact:
    stage: Stage
    artifact: str
    version: int
    status: str  # draft | ready | approved | stale


@dataclass
class StaleArtifact:
    artifact: str
    reason: str
    replaced_by: str
    required_action: str


@dataclass
class OpenRoute:
    route_id: str
    from_stage: Stage
    owner_stage: Stage
    required_action: str
    status: str  # open | repaired


@dataclass
class UserConfirmation:
    confirmation: str
    stage: Stage
    source: str
    recorded_in: str


@dataclass
class ResumeContext:
    last_completed_operation: str = ""
    next_allowed_operation: str = ""
    active_item: str = ""
    required_reread_targets: list[str] = field(default_factory=list)
    resume_reason: str = ""


@dataclass
class RunRecord:
    work_id: WorkId
    status: RunStatus = RunStatus.NOT_STARTED
    current_stage: Stage = Stage.RAW_REQUIREMENT
    r2p_version: str = R2P_VERSION
    approved_checkpoints: list[CheckpointRecord] = field(default_factory=list)
    bundle_authorizations: list[BundleAuthorization] = field(default_factory=list)
    active_artifacts: list[ActiveArtifact] = field(default_factory=list)
    stale_artifacts: list[StaleArtifact] = field(default_factory=list)
    open_routes: list[OpenRoute] = field(default_factory=list)
    user_confirmations: list[UserConfirmation] = field(default_factory=list)
    resume_context: ResumeContext = field(default_factory=ResumeContext)
    tier_estimate: TierEstimate | None = None
    tier_locked: TierEstimate | None = None
    reopen_lineage: str | None = None  # e.g. "reopened_from: WF-...-r0@plan_checkpoint"

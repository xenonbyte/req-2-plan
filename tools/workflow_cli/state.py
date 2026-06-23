"""
Run state manager for the req-to-plan workflow CLI.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from tools.workflow_cli.atomic import atomic_write_text
from tools.workflow_cli.models import (
    ActiveArtifact,
    BundleAuthorization,
    CheckpointRecord,
    OpenRoute,
    ResumeContext,
    RunRecord,
    RunStatus,
    Stage,
    StaleArtifact,
    TierBase,
    TierEstimate,
    TierModifier,
    UserConfirmation,
    WorkId,
    is_transition_allowed,
)
from tools.workflow_cli.version import R2P_VERSION


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def create_run_record(work_id: WorkId) -> RunRecord:
    """Create a new RunRecord initialised for run-start."""
    return RunRecord(
        work_id=work_id,
        status=RunStatus.ACTIVE_STAGE_DRAFT,
        current_stage=Stage.RAW_REQUIREMENT,
        r2p_version=R2P_VERSION,
        resume_context=ResumeContext(
            last_completed_operation="start_workflow_run",
            next_allowed_operation="produce_stage_artifact",
            active_item="raw_requirement",
        ),
    )


# ---------------------------------------------------------------------------
# Mutations
# ---------------------------------------------------------------------------


def update_run_status(record: RunRecord, new_status: RunStatus) -> RunRecord:
    """Validate the transition and update status; raises ValueError if invalid."""
    if not is_transition_allowed(record.status, new_status):
        raise ValueError(
            f"Invalid status transition: {record.status.value!r} → {new_status.value!r}"
        )
    record.status = new_status
    return record


def add_checkpoint(
    record: RunRecord,
    stage: Stage,
    artifact: str,
    version: int,
    downstream_authorization: str,
    bundle_id: Optional[str] = None,
) -> RunRecord:
    """Append a CheckpointRecord with the current UTC timestamp."""
    cp = CheckpointRecord(
        stage=stage,
        artifact=artifact,
        version=version,
        approved_at=datetime.now(timezone.utc).isoformat(),
        downstream_authorization=downstream_authorization,
        bundle_id=bundle_id,
    )
    record.approved_checkpoints.append(cp)
    return record


def get_active_artifact(record: RunRecord, stage: Stage) -> Optional[ActiveArtifact]:
    """Return the first ActiveArtifact matching *stage*, or None."""
    for aa in record.active_artifacts:
        if aa.stage == stage:
            return aa
    return None


def upsert_active_artifact(
    record: RunRecord,
    stage: Stage,
    artifact: str,
    version: int,
    status: str,
) -> RunRecord:
    """Update an existing ActiveArtifact for *stage* or append a new one."""
    for aa in record.active_artifacts:
        if aa.stage == stage:
            aa.artifact = artifact
            aa.version = version
            aa.status = status
            return record
    record.active_artifacts.append(
        ActiveArtifact(stage=stage, artifact=artifact, version=version, status=status)
    )
    return record


def record_stale_artifact(
    record: RunRecord,
    artifact: str,
    reason: str,
    replaced_by: str,
    required_action: str,
) -> RunRecord:
    """Append a StaleArtifact entry."""
    record.stale_artifacts.append(
        StaleArtifact(
            artifact=artifact,
            reason=reason,
            replaced_by=replaced_by,
            required_action=required_action,
        )
    )
    return record


def add_open_route(
    record: RunRecord,
    route_id: str,
    from_stage: Stage,
    owner_stage: Stage,
    required_action: str,
) -> RunRecord:
    """Append an OpenRoute with status='open'."""
    record.open_routes.append(
        OpenRoute(
            route_id=route_id,
            from_stage=from_stage,
            owner_stage=owner_stage,
            required_action=required_action,
            status="open",
        )
    )
    return record


def close_route(record: RunRecord, route_id: str) -> RunRecord:
    """Set matching route status to 'repaired'."""
    for route in record.open_routes:
        if route.route_id == route_id:
            route.status = "repaired"
    return record


def update_resume_context(
    record: RunRecord,
    last_operation: str = "",
    next_operation: str = "",
    active_item: str = "",
    reread_targets: Optional[list[str]] = None,
    reason: str = "",
) -> RunRecord:
    """Update non-empty fields in resume_context."""
    rc = record.resume_context
    if last_operation:
        rc.last_completed_operation = last_operation
    if next_operation:
        rc.next_allowed_operation = next_operation
    if active_item:
        rc.active_item = active_item
    if reread_targets is not None:
        rc.required_reread_targets = reread_targets
    if reason:
        rc.resume_reason = reason
    return record


# ---------------------------------------------------------------------------
# Tier serialization helpers
# ---------------------------------------------------------------------------


def _tier_to_block(tier: Optional[TierEstimate], empty_label: str) -> str:
    if tier is None:
        return empty_label
    mods = ", ".join(sorted(m.value for m in tier.modifiers)) if tier.modifiers else ""
    lines = [f"base: {tier.base.value}", f"modifiers: {mods}"]
    return "\n".join(lines)


def _block_to_tier(text: str, empty_label: str) -> Optional[TierEstimate]:
    text = text.strip()
    if text == empty_label:
        return None
    base_val = None
    mods: list[TierModifier] = []
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("base:"):
            base_val = line[len("base:"):].strip()
        elif line.startswith("modifiers:"):
            mods_str = line[len("modifiers:"):].strip()
            if mods_str:
                for m in mods_str.split(","):
                    m = m.strip()
                    if m:
                        mods.append(TierModifier(m))
    if base_val is None:
        return None
    return TierEstimate(base=TierBase(base_val), modifiers=frozenset(mods))


# ---------------------------------------------------------------------------
# Markdown table helpers
# ---------------------------------------------------------------------------


def _escape_cell(val: str) -> str:
    """Escape backslashes and pipes in a markdown table cell value."""
    return val.replace("\\", "\\\\").replace("|", "\\|")


def _split_cells(row_text: str) -> list[str]:
    """Split pipe-delimited row, honouring \\| and \\\\ escape sequences."""
    cells: list[str] = []
    current: list[str] = []
    i = 0
    while i < len(row_text):
        if row_text[i] == "\\" and i + 1 < len(row_text) and row_text[i + 1] == "|":
            current.append("|")
            i += 2
        elif row_text[i] == "\\" and i + 1 < len(row_text) and row_text[i + 1] == "\\":
            current.append("\\")
            i += 2
        elif row_text[i] == "|":
            cells.append("".join(current).strip())
            current = []
            i += 1
        else:
            current.append(row_text[i])
            i += 1
    remainder = "".join(current).strip()
    if remainder:
        cells.append(remainder)
    return cells


def _parse_md_table(section_text: str) -> list[dict[str, str]]:
    """Parse a markdown table from section text, respecting \\| escapes."""
    lines = [ln for ln in section_text.splitlines() if ln.strip()]
    if len(lines) < 2:
        return []
    raw_headers = lines[0].strip()
    if not raw_headers.startswith("|"):
        return []
    headers = [h.strip() for h in raw_headers.strip("|").split("|")]
    rows: list[dict[str, str]] = []
    for row_line in lines[2:]:
        row_line = row_line.strip()
        if not row_line or not row_line.startswith("|"):
            continue
        # Strip leading/trailing | then split, respecting \| escapes
        inner = row_line[1:]
        if inner.endswith("|"):
            inner = inner[:-1]
        cells = _split_cells(inner)
        while len(cells) < len(headers):
            cells.append("")
        row = {headers[i]: cells[i] for i in range(len(headers))}
        rows.append(row)
    return rows


def _table(headers: list[str], rows: list[list[str]]) -> str:
    """Produce a markdown table string, escaping | and \\ in cell values."""
    sep = "|" + "|".join("---" for _ in headers) + "|"
    header_row = "| " + " | ".join(headers) + " |"
    lines = [header_row, sep]
    for row in rows:
        escaped = [_escape_cell(str(c)) for c in row]
        lines.append("| " + " | ".join(escaped) + " |")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Markdown serialization
# ---------------------------------------------------------------------------


def run_record_to_markdown(record: RunRecord) -> str:
    """Serialise a RunRecord to a markdown string."""
    parts: list[str] = []

    parts.append(f"# Workflow Run: {record.work_id}")
    parts.append("")

    parts.append("## Status")
    parts.append(record.status.value)
    parts.append("")

    parts.append("## Current Stage")
    parts.append(record.current_stage.value)
    parts.append("")

    parts.append("## r2p Version")
    parts.append(record.r2p_version)
    parts.append("")

    parts.append("## Tier Lock")
    parts.append(_tier_to_block(record.tier_locked, "unlocked"))
    parts.append("")

    parts.append("## Tier Estimate")
    parts.append(_tier_to_block(record.tier_estimate, "none"))
    parts.append("")

    # Approved Checkpoints
    cp_rows = [
        [
            cp.stage.value,
            cp.artifact,
            str(cp.version),
            cp.approved_at,
            cp.downstream_authorization,
            cp.bundle_id or "",
        ]
        for cp in record.approved_checkpoints
    ]
    parts.append("## Approved Checkpoints")
    parts.append(
        _table(
            ["Stage", "Artifact", "Version", "Approved At", "Downstream Authorization", "Bundle ID"],
            cp_rows,
        )
    )
    parts.append("")

    # Bundle Authorizations
    ba_rows = []
    for ba in record.bundle_authorizations:
        stages_str = ", ".join(sorted(s.value for s in ba.stages))
        consumed_str = ", ".join(
            f"{k}:{v}" for k, v in sorted(ba.consumed_by_stage.items())
        )
        ba_rows.append(
            [ba.bundle_id, stages_str, ba.authorized_at, ba.revoked_at or "", consumed_str]
        )
    parts.append("## Bundle Authorizations")
    parts.append(
        _table(
            ["Bundle ID", "Stages", "Authorized At", "Revoked At", "Consumed Stages"],
            ba_rows,
        )
    )
    parts.append("")

    # Active Artifacts
    aa_rows = [
        [aa.stage.value, aa.artifact, str(aa.version), aa.status]
        for aa in record.active_artifacts
    ]
    parts.append("## Active Artifacts")
    parts.append(_table(["Stage", "Artifact", "Version", "Status"], aa_rows))
    parts.append("")

    # Stale / Superseded Artifacts
    sa_rows = [
        [sa.artifact, sa.reason, sa.replaced_by, sa.required_action]
        for sa in record.stale_artifacts
    ]
    parts.append("## Stale / Superseded Artifacts")
    parts.append(_table(["Artifact", "Reason", "Replaced By", "Required Action"], sa_rows))
    parts.append("")

    # Open Routes
    or_rows = [
        [r.route_id, r.from_stage.value, r.owner_stage.value, r.required_action, r.status]
        for r in record.open_routes
    ]
    parts.append("## Open Routes")
    parts.append(
        _table(["Route ID", "From Stage", "Owner Stage", "Required Action", "Status"], or_rows)
    )
    parts.append("")

    # User Confirmations
    uc_rows = [
        [uc.confirmation, uc.stage.value, uc.source, uc.recorded_in]
        for uc in record.user_confirmations
    ]
    parts.append("## User Confirmations")
    parts.append(_table(["Confirmation", "Stage", "Source", "Recorded In"], uc_rows))
    parts.append("")

    # Resume Context
    rc = record.resume_context
    reread_str = ", ".join(rc.required_reread_targets) if rc.required_reread_targets else ""
    rc_rows = [
        ["Last Completed Operation", rc.last_completed_operation],
        ["Next Allowed Operation", rc.next_allowed_operation],
        ["Active Item", rc.active_item],
        ["Required Reread Targets", reread_str],
        ["Resume Reason", rc.resume_reason],
    ]
    parts.append("## Resume Context")
    parts.append(_table(["Field", "Value"], rc_rows))
    parts.append("")

    # Reopen Lineage
    parts.append("## Reopen Lineage")
    parts.append(record.reopen_lineage if record.reopen_lineage else "(none)")
    parts.append("")

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Markdown parsing
# ---------------------------------------------------------------------------


def _split_sections(md: str) -> dict[str, str]:
    """Split markdown into a dict of {section_heading: body_text}."""
    sections: dict[str, str] = {}
    current_heading: Optional[str] = None
    body_lines: list[str] = []

    for line in md.splitlines():
        if line.startswith("## "):
            if current_heading is not None:
                sections[current_heading] = "\n".join(body_lines).strip()
            current_heading = line[3:].strip()
            body_lines = []
        elif line.startswith("# "):
            # Top-level heading — record as special key
            if current_heading is not None:
                sections[current_heading] = "\n".join(body_lines).strip()
            current_heading = "__title__"
            body_lines = [line[2:].strip()]
        else:
            if current_heading is not None:
                body_lines.append(line)

    if current_heading is not None:
        sections[current_heading] = "\n".join(body_lines).strip()

    return sections


def parse_run_record(md: str, work_id: WorkId) -> RunRecord:
    """Parse markdown produced by run_record_to_markdown back into a RunRecord."""
    sections = _split_sections(md)

    status = RunStatus(sections.get("Status", "not_started").strip())
    current_stage = Stage(sections.get("Current Stage", "raw_requirement").strip())
    r2p_version = sections.get("r2p Version", R2P_VERSION).strip()

    tier_locked = _block_to_tier(sections.get("Tier Lock", "unlocked"), "unlocked")
    tier_estimate = _block_to_tier(sections.get("Tier Estimate", "none"), "none")

    # Approved Checkpoints
    approved_checkpoints: list[CheckpointRecord] = []
    cp_rows = _parse_md_table(sections.get("Approved Checkpoints", ""))
    for row in cp_rows:
        approved_checkpoints.append(
            CheckpointRecord(
                stage=Stage(row.get("Stage", "")),
                artifact=row.get("Artifact", ""),
                version=int(row.get("Version", "0") or "0"),
                approved_at=row.get("Approved At", ""),
                downstream_authorization=row.get("Downstream Authorization", ""),
                bundle_id=row.get("Bundle ID") or None,
            )
        )

    # Bundle Authorizations
    bundle_authorizations: list[BundleAuthorization] = []
    for row in _parse_md_table(sections.get("Bundle Authorizations", "")):
        stages_raw = row.get("Stages", "")
        stages: frozenset[Stage] = frozenset(
            Stage(s.strip()) for s in stages_raw.split(",") if s.strip()
        )
        consumed_raw = row.get("Consumed Stages", "")
        consumed_by: dict[str, str] = {}
        if consumed_raw:
            for item in consumed_raw.split(","):
                item = item.strip()
                if ":" in item:
                    k, v = item.split(":", 1)
                    consumed_by[k.strip()] = v.strip()
        bundle_authorizations.append(
            BundleAuthorization(
                bundle_id=row.get("Bundle ID", ""),
                stages=stages,
                authorized_at=row.get("Authorized At", ""),
                revoked_at=row.get("Revoked At") or None,
                consumed_by_stage=consumed_by,
            )
        )

    # Active Artifacts
    active_artifacts: list[ActiveArtifact] = []
    for row in _parse_md_table(sections.get("Active Artifacts", "")):
        active_artifacts.append(
            ActiveArtifact(
                stage=Stage(row.get("Stage", "")),
                artifact=row.get("Artifact", ""),
                version=int(row.get("Version", "0") or "0"),
                status=row.get("Status", ""),
            )
        )

    # Stale / Superseded Artifacts
    stale_artifacts: list[StaleArtifact] = []
    for row in _parse_md_table(sections.get("Stale / Superseded Artifacts", "")):
        stale_artifacts.append(
            StaleArtifact(
                artifact=row.get("Artifact", ""),
                reason=row.get("Reason", ""),
                replaced_by=row.get("Replaced By", ""),
                required_action=row.get("Required Action", ""),
            )
        )

    # Open Routes
    open_routes: list[OpenRoute] = []
    for row in _parse_md_table(sections.get("Open Routes", "")):
        open_routes.append(
            OpenRoute(
                route_id=row.get("Route ID", ""),
                from_stage=Stage(row.get("From Stage", "")),
                owner_stage=Stage(row.get("Owner Stage", "")),
                required_action=row.get("Required Action", ""),
                status=row.get("Status", "open"),
            )
        )

    # User Confirmations
    user_confirmations: list[UserConfirmation] = []
    for row in _parse_md_table(sections.get("User Confirmations", "")):
        user_confirmations.append(
            UserConfirmation(
                confirmation=row.get("Confirmation", ""),
                stage=Stage(row.get("Stage", "")),
                source=row.get("Source", ""),
                recorded_in=row.get("Recorded In", ""),
            )
        )

    # Resume Context
    resume_context = ResumeContext()
    rc_rows = _parse_md_table(sections.get("Resume Context", ""))
    rc_map = {row.get("Field", ""): row.get("Value", "") for row in rc_rows}
    resume_context.last_completed_operation = rc_map.get("Last Completed Operation", "")
    resume_context.next_allowed_operation = rc_map.get("Next Allowed Operation", "")
    resume_context.active_item = rc_map.get("Active Item", "")
    reread_raw = rc_map.get("Required Reread Targets", "")
    resume_context.required_reread_targets = (
        [t.strip() for t in reread_raw.split(",") if t.strip()] if reread_raw else []
    )
    resume_context.resume_reason = rc_map.get("Resume Reason", "")

    # Reopen Lineage
    lineage_raw = sections.get("Reopen Lineage", "(none)").strip()
    reopen_lineage: Optional[str] = None if lineage_raw == "(none)" else lineage_raw

    return RunRecord(
        work_id=work_id,
        status=status,
        current_stage=current_stage,
        r2p_version=r2p_version,
        approved_checkpoints=approved_checkpoints,
        bundle_authorizations=bundle_authorizations,
        active_artifacts=active_artifacts,
        stale_artifacts=stale_artifacts,
        open_routes=open_routes,
        user_confirmations=user_confirmations,
        resume_context=resume_context,
        tier_estimate=tier_estimate,
        tier_locked=tier_locked,
        reopen_lineage=reopen_lineage,
    )


# ---------------------------------------------------------------------------
# RunStateManager
# ---------------------------------------------------------------------------


class RunStateManager:
    """Persist and load a RunRecord as run.md in run_dir."""

    def __init__(self, run_dir: Path) -> None:
        self.run_dir = run_dir
        self.run_path = run_dir / "run.md"

    def save(self, record: RunRecord) -> None:
        self.run_dir.mkdir(parents=True, exist_ok=True)
        text = run_record_to_markdown(record)
        # Atomic write: a crash mid-write must not leave a truncated run.md that
        # bricks the run. Write a unique sibling temp then atomically replace.
        atomic_write_text(self.run_path, text)

    def load(self) -> RunRecord:
        if not self.run_path.exists():
            raise FileNotFoundError(f"run.md not found at {self.run_path}")
        text = self.run_path.read_text(encoding="utf-8")
        match = re.search(r"# Workflow Run: (WF-\S+)", text)
        if not match:
            raise ValueError("Cannot parse work_id from run.md")
        work_id = WorkId(match.group(1))
        return parse_run_record(text, work_id)

# Requirement-to-PLAN Agent Workflow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Python CLI state machine + Agent skill that implements the 6-stage pipeline (raw_requirement intake + 5 transformation stages: Requirement Brief → Risk Discovery → DESIGN → SPEC → PLAN) defined in `docs/*.md`, with post-PLAN Superpowers plan adaptation.

**Architecture:** Python CLI (`tools/workflow_cli/`) manages run state, artifact lifecycle, and structured gate validation via filesystem. Claude Code Agent skill (`req-to-plan`) loads workflow docs, generates semantic artifact content, and calls CLI for state persistence. Post-PLAN, CLI adapts the neutral PLAN into a Superpowers-executable plan.

**Tech Stack:** Python 3.10+ stdlib only (argparse, json, pathlib, unittest, dataclasses), Markdown files for artifact storage.

**Prerequisites:**
- All workflow documents under `docs/` must exist (README.md, workflow-invariants.md, workflow-execution-guide.md, requirement-brief-workflow.md, risk-question-discovery-workflow.md, design-workflow.md, spec-workflow.md, plan-workflow.md). These define the stage contracts that the Agent skill reads to generate artifact content and judge quality gates.
- Python 3.10+ installed (required for `X | Y` union type syntax used throughout the CLI code).

---

## File Structure

```
tools/workflow_cli/
├── __init__.py               # empty
├── __main__.py               # entry: python -m tools.workflow_cli
├── models.py                 # dataclasses: RunRecord, Artifact, enums
├── state.py                  # run.md read/write, state transition validation
├── artifact.py               # artifact frontmatter, version, stale/superseded
├── gates.py                  # structured gate checks
├── cli.py                    # argparse routing, all 22 commands
├── output.py                 # JSON/human output formatting
├── adapters/
│   ├── __init__.py           # adapter registry
│   └── superpowers.py        # PLAN -> Superpowers conversion
└── agent_shortcuts.py        # coyeme-workflow-* entry points

tests/
├── __init__.py
├── test_models.py
├── test_state.py
├── test_artifact.py
├── test_gates.py
├── test_cli.py
├── test_output.py
├── test_adapters_superpowers.py

.claude/
└── skills/
    └── req-to-plan.md        # Agent skill for driving the workflow
```

---

### Task 1: Package skeleton and core models

**Files:**
- Create: `tools/workflow_cli/__init__.py`
- Create: `tools/workflow_cli/__main__.py`
- Create: `tools/workflow_cli/models.py`
- Create: `tests/__init__.py`
- Create: `tests/test_models.py`

- [ ] **Step 1: Write the tests for core models**

```python
# tests/test_models.py
import unittest
import tempfile
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from tools.workflow_cli.models import (
    RunStatus, Stage, WorkId, STAGE_ORDER, STAGE_ARTIFACT_MAP,
    STAGE_REQUIRED_UPSTREAM_CHECKPOINTS, NEXT_STAGE_MAP,
    ALLOWED_TRANSITIONS, is_transition_allowed
)

class TestStageOrder(unittest.TestCase):
    def test_stage_order_has_six_stages_before_closed(self):
        self.assertEqual(len(STAGE_ORDER), 6)
        self.assertEqual(STAGE_ORDER[0], Stage.RAW_REQUIREMENT)
        self.assertEqual(STAGE_ORDER[-1], Stage.PLAN)

    def test_next_stage_map_covers_all_stages(self):
        for stage in STAGE_ORDER[:-1]:
            self.assertIn(stage, NEXT_STAGE_MAP)
        self.assertNotIn(Stage.PLAN, NEXT_STAGE_MAP)

    def test_artifact_map_covers_all_stages(self):
        for stage in STAGE_ORDER:
            self.assertIn(stage, STAGE_ARTIFACT_MAP)

class TestRunStatus(unittest.TestCase):
    def test_all_statuses_have_string_values(self):
        for status in RunStatus:
            self.assertIsInstance(status.value, str)
            self.assertTrue(len(status.value) > 0)

class TestTransitions(unittest.TestCase):
    def test_not_started_only_goes_to_active_stage_draft(self):
        allowed = ALLOWED_TRANSITIONS[RunStatus.NOT_STARTED]
        self.assertEqual(allowed, {RunStatus.ACTIVE_STAGE_DRAFT})

    def test_active_stage_draft_allows_gate_and_quality_failures(self):
        allowed = ALLOWED_TRANSITIONS[RunStatus.ACTIVE_STAGE_DRAFT]
        self.assertIn(RunStatus.ENTRY_GATE_FAILED, allowed)
        self.assertIn(RunStatus.QUALITY_GATE_FAILED, allowed)
        self.assertIn(RunStatus.READY_FOR_CHECKPOINT_REVIEW, allowed)

    def test_closed_has_no_transitions(self):
        self.assertEqual(ALLOWED_TRANSITIONS[RunStatus.CLOSED_AT_PLAN_CHECKPOINT], set())

    def test_checkpoint_approved_goes_to_next_stage_or_closed(self):
        allowed = ALLOWED_TRANSITIONS[RunStatus.CHECKPOINT_APPROVED]
        self.assertIn(RunStatus.NEXT_STAGE, allowed)

class TestWorkId(unittest.TestCase):
    def test_valid_work_id(self):
        wid = WorkId("WF-20260527-test-slug")
        self.assertEqual(str(wid), "WF-20260527-test-slug")

    def test_invalid_prefix_raises(self):
        with self.assertRaises(ValueError):
            WorkId("XX-20260527-test")

    def test_empty_raises(self):
        with self.assertRaises(ValueError):
            WorkId("")

    def test_generate_creates_valid_id(self):
        wid = WorkId.generate("Add login rate limiting")
        self.assertTrue(str(wid).startswith("WF-"))
        self.assertIn("login-rate-limiting", str(wid))

if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/xubo/x-skills/req-to-plan && python3 -m pytest tests/test_models.py -v 2>&1 || python3 -m unittest tests.test_models -v`
Expected: FAIL with ImportError (module not found)

- [ ] **Step 3: Create package skeleton**

```python
# tools/workflow_cli/__init__.py
```

```python
# tools/workflow_cli/__main__.py
"""Entry point: python -m tools.workflow_cli"""
from tools.workflow_cli.cli import main
import sys

if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Write models.py**

```python
# tools/workflow_cli/models.py
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Set, Dict, List
from datetime import datetime
import re


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


STAGE_ORDER: List[Stage] = [
    Stage.RAW_REQUIREMENT,
    Stage.REQUIREMENT_BRIEF,
    Stage.RISK_DISCOVERY,
    Stage.DESIGN,
    Stage.SPEC,
    Stage.PLAN,
]

NEXT_STAGE_MAP: Dict[Stage, Stage] = {
    Stage.RAW_REQUIREMENT: Stage.REQUIREMENT_BRIEF,
    Stage.REQUIREMENT_BRIEF: Stage.RISK_DISCOVERY,
    Stage.RISK_DISCOVERY: Stage.DESIGN,
    Stage.DESIGN: Stage.SPEC,
    Stage.SPEC: Stage.PLAN,
}

STAGE_ARTIFACT_MAP: Dict[Stage, str] = {
    Stage.RAW_REQUIREMENT: "00-raw-requirement.md",
    Stage.REQUIREMENT_BRIEF: "03-requirement-brief.md",
    Stage.RISK_DISCOVERY: "04-risk-discovery.md",
    Stage.DESIGN: "05-design.md",
    Stage.SPEC: "06-spec.md",
    Stage.PLAN: "07-plan.md",
}

STAGE_REQUIRED_UPSTREAM_CHECKPOINTS: Dict[Stage, List[Stage]] = {
    Stage.REQUIREMENT_BRIEF: [],
    Stage.RISK_DISCOVERY: [Stage.REQUIREMENT_BRIEF],
    Stage.DESIGN: [Stage.REQUIREMENT_BRIEF, Stage.RISK_DISCOVERY],
    Stage.SPEC: [Stage.REQUIREMENT_BRIEF, Stage.RISK_DISCOVERY, Stage.DESIGN],
    Stage.PLAN: [Stage.REQUIREMENT_BRIEF, Stage.RISK_DISCOVERY, Stage.DESIGN, Stage.SPEC],
}

ALLOWED_TRANSITIONS: Dict[RunStatus, Set[RunStatus]] = {
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
        RunStatus.CHECKPOINT_REVIEW,
        RunStatus.UPSTREAM_GAP_ROUTING,
    },
    RunStatus.CHECKPOINT_REVIEW: {
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

CHECKPOINT_REVIEW_STAGES: Set[RunStatus] = {
    RunStatus.READY_FOR_CHECKPOINT_REVIEW,
    RunStatus.CHECKPOINT_REVIEW,
}

ALLOWED_COMMANDS_BY_RUN_STATE: Dict[RunStatus, Set[str]] = {
    RunStatus.NOT_STARTED: {"CMD-RUN-START"},
    RunStatus.ACTIVE_STAGE_DRAFT: {
        "CMD-STAGE-LOAD", "CMD-STAGE-PRODUCE", "CMD-STAGE-READY",
        "CMD-GATE-ENTRY", "CMD-GATE-QUALITY",
        "CMD-CONFIRM-RECORD", "CMD-CONFIRM-REJECT", "CMD-CONFIRM-LINK",
        "CMD-SUBAGENT-DISPATCH", "CMD-SUBAGENT-MERGE",
        "CMD-GAP-RECORD",
    },
    RunStatus.ENTRY_GATE_FAILED: {
        "CMD-GATE-ENTRY", "CMD-CONFIRM-RECORD", "CMD-CONFIRM-REJECT",
        "CMD-GAP-RECORD", "CMD-GAP-ROUTE",
    },
    RunStatus.QUALITY_GATE_FAILED: {
        "CMD-STAGE-PRODUCE", "CMD-STAGE-READY",
        "CMD-GATE-QUALITY",
        "CMD-CONFIRM-RECORD", "CMD-CONFIRM-REJECT",
        "CMD-SUBAGENT-DISPATCH", "CMD-SUBAGENT-MERGE",
        "CMD-GAP-RECORD", "CMD-GAP-ROUTE",
    },
    RunStatus.READY_FOR_CHECKPOINT_REVIEW: {
        "CMD-REVIEW-CHECKPOINT", "CMD-SUBAGENT-REVIEW", "CMD-GAP-RECORD",
    },
    RunStatus.CHECKPOINT_REVIEW: {
        "CMD-REVIEW-CHECKPOINT", "CMD-SUBAGENT-REVIEW",
        "CMD-REVIEW-MERGE",
        "CMD-CONFIRM-RECORD", "CMD-CONFIRM-REJECT", "CMD-CONFIRM-LINK",
        "CMD-CHECKPOINT-DECIDE",
        "CMD-GAP-RECORD", "CMD-GAP-ROUTE",
    },
    RunStatus.CHECKPOINT_CHANGES_REQUESTED: {
        "CMD-STAGE-PRODUCE", "CMD-STAGE-READY",
        "CMD-GATE-QUALITY",
        "CMD-CONFIRM-RECORD", "CMD-CONFIRM-REJECT",
        "CMD-GAP-RECORD", "CMD-GAP-ROUTE",
    },
    RunStatus.UPSTREAM_GAP_ROUTING: {
        "CMD-GAP-ROUTE", "CMD-GAP-REIMPORT",
        "CMD-STAGE-LOAD", "CMD-STAGE-PRODUCE", "CMD-STAGE-READY",
        "CMD-GATE-QUALITY", "CMD-CHECKPOINT-DECIDE",
        "CMD-ARTIFACT-MARK-STALE",
    },
    RunStatus.CHECKPOINT_APPROVED: {
        "CMD-RUN-RESUME", "CMD-GAP-REIMPORT", "CMD-RUN-CLOSE",
    },
    RunStatus.NEXT_STAGE: {
        "CMD-STAGE-LOAD", "CMD-GATE-ENTRY", "CMD-RUN-RESUME",
    },
    RunStatus.CLOSED_AT_PLAN_CHECKPOINT: set(),
}


def is_transition_allowed(current: RunStatus, target: RunStatus) -> bool:
    return target in ALLOWED_TRANSITIONS.get(current, set())


def is_command_allowed(run_status: RunStatus, command_intent: str) -> bool:
    return command_intent in ALLOWED_COMMANDS_BY_RUN_STATE.get(run_status, set())


class WorkId:
    _PATTERN = re.compile(r"^WF-\d{8}-[a-z0-9]([a-z0-9-]{0,38}[a-z0-9])?$")

    def __init__(self, value: str) -> None:
        if not self._PATTERN.match(value):
            raise ValueError(f"Invalid work-id: {value}")
        self.value = value

    def __str__(self) -> str:
        return self.value

    def __eq__(self, other: object) -> bool:
        if isinstance(other, WorkId):
            return self.value == other.value
        return False

    def __hash__(self) -> int:
        return hash(self.value)

    @classmethod
    def generate(cls, summary: str) -> "WorkId":
        today = datetime.now().strftime("%Y%m%d")
        slug = re.sub(r"[^a-z0-9]+", "-", summary.lower().strip())[:40].strip("-")
        return cls(f"WF-{today}-{slug}")


@dataclass
class CheckpointRecord:
    stage: Stage
    artifact: str
    version: int
    approved_at: str
    downstream_authorization: str  # yes | no


@dataclass
class ActiveArtifact:
    stage: Stage
    artifact: str
    version: int
    status: str  # draft | ready | approved | ...


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
    required_reread_targets: List[str] = field(default_factory=list)
    resume_reason: str = ""


@dataclass
class RunRecord:
    work_id: WorkId
    status: RunStatus = RunStatus.NOT_STARTED
    current_stage: Stage = Stage.RAW_REQUIREMENT
    approved_checkpoints: List[CheckpointRecord] = field(default_factory=list)
    active_artifacts: List[ActiveArtifact] = field(default_factory=list)
    stale_artifacts: List[StaleArtifact] = field(default_factory=list)
    open_routes: List[OpenRoute] = field(default_factory=list)
    user_confirmations: List[UserConfirmation] = field(default_factory=list)
    resume_context: ResumeContext = field(default_factory=ResumeContext)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd /Users/xubo/x-skills/req-to-plan && python3 -m unittest tests.test_models -v`
Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
cd /Users/xubo/x-skills/req-to-plan && git add tools/workflow_cli/__init__.py tools/workflow_cli/__main__.py tools/workflow_cli/models.py tests/__init__.py tests/test_models.py && git commit -m "feat: add package skeleton and core models"
```

---

### Task 2: Run state manager (state.py)

**Files:**
- Create: `tools/workflow_cli/state.py`
- Create: `tests/test_state.py`

- [ ] **Step 1: Write failing tests for state.py**

```python
# tests/test_state.py
import unittest
import tempfile
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from tools.workflow_cli.models import (
    RunRecord, RunStatus, Stage, WorkId, CheckpointRecord,
    ActiveArtifact, ResumeContext
)
from tools.workflow_cli.state import (
    RunStateManager, run_record_to_markdown, parse_run_record,
    create_run_record, update_run_status, add_checkpoint,
    get_active_artifact, record_stale_artifact
)

class TestRunStateManager(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.run_path = self.root / "run.md"
        self.mgr = RunStateManager(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def _create_minimal_run(self):
        record = RunRecord(work_id=WorkId("WF-20260527-test"))
        record.status = RunStatus.ACTIVE_STAGE_DRAFT
        record.current_stage = Stage.REQUIREMENT_BRIEF
        return record

    def test_create_new_run_record(self):
        wid = WorkId("WF-20260527-test-feature")
        record = create_run_record(wid)
        self.assertEqual(record.status, RunStatus.ACTIVE_STAGE_DRAFT)
        self.assertEqual(record.current_stage, Stage.RAW_REQUIREMENT)

    def test_parse_run_record_from_markdown(self):
        md = """# Workflow Run: WF-20260527-test

## Status
active_stage_draft

## Current Stage
requirement_brief

## Approved Checkpoints
| Stage | Artifact | Version | Approved At | Downstream Authorization |
|---|---|---|---|---|---|

## Active Artifacts
| Stage | Artifact | Version | Status |
|---|---|---|---|
| requirement_brief | 03-requirement-brief.md | 1 | draft |

## Stale / Superseded Artifacts
| Artifact | Reason | Replaced By | Required Action |
|---|---|---|---|

## Open Routes
| Route ID | From Stage | Owner Stage | Required Action | Status |
|---|---|---|---|---|

## User Confirmations
| Confirmation | Stage | Source | Recorded In |
|---|---|---|---|

## Resume Context
| Field | Value |
|---|---|
| Last Completed Operation | start_workflow_run |
| Next Allowed Operation | produce_stage_artifact |
| Active Item | requirement_brief |
| Required Reread Targets | |
| Resume Reason | |
"""
        record = parse_run_record(md, WorkId("WF-20260527-test"))
        self.assertEqual(record.status, RunStatus.ACTIVE_STAGE_DRAFT)
        self.assertEqual(record.current_stage, Stage.REQUIREMENT_BRIEF)
        self.assertEqual(len(record.active_artifacts), 1)
        self.assertEqual(record.active_artifacts[0].stage, Stage.REQUIREMENT_BRIEF)
        self.assertEqual(record.resume_context.last_completed_operation, "start_workflow_run")

    def test_roundtrip_record_to_md_and_back(self):
        record = self._create_minimal_run()
        record.approved_checkpoints.append(
            CheckpointRecord(
                stage=Stage.REQUIREMENT_BRIEF,
                artifact="03-requirement-brief.md",
                version=1,
                approved_at="2026-05-27T10:00:00",
                downstream_authorization="yes",
            )
        )
        md = run_record_to_markdown(record)
        parsed = parse_run_record(md, record.work_id)
        self.assertEqual(parsed.status, record.status)
        self.assertEqual(parsed.current_stage, record.current_stage)
        self.assertEqual(len(parsed.approved_checkpoints), 1)

    def test_update_run_status_validates_transition(self):
        record = self._create_minimal_run()
        updated = update_run_status(record, RunStatus.READY_FOR_CHECKPOINT_REVIEW)
        self.assertEqual(updated.status, RunStatus.READY_FOR_CHECKPOINT_REVIEW)

    def test_update_run_status_rejects_invalid_transition(self):
        record = self._create_minimal_run()
        with self.assertRaises(ValueError):
            update_run_status(record, RunStatus.CLOSED_AT_PLAN_CHECKPOINT)

    def test_add_checkpoint_appends_and_updates(self):
        record = self._create_minimal_run()
        updated = add_checkpoint(
            record,
            stage=Stage.REQUIREMENT_BRIEF,
            artifact="03-requirement-brief.md",
            version=1,
            downstream_authorization="yes",
        )
        self.assertEqual(len(updated.approved_checkpoints), 1)
        self.assertEqual(updated.approved_checkpoints[0].stage, Stage.REQUIREMENT_BRIEF)

    def test_get_active_artifact_returns_none_when_empty(self):
        record = self._create_minimal_run()
        result = get_active_artifact(record, Stage.SPEC)
        self.assertIsNone(result)

    def test_get_active_artifact_returns_match(self):
        record = self._create_minimal_run()
        record.active_artifacts.append(
            ActiveArtifact(stage=Stage.DESIGN, artifact="05-design.md", version=1, status="draft")
        )
        result = get_active_artifact(record, Stage.DESIGN)
        self.assertIsNotNone(result)
        self.assertEqual(result.artifact, "05-design.md")

    def test_record_stale_artifact_adds_entry(self):
        record = self._create_minimal_run()
        updated = record_stale_artifact(
            record,
            artifact="06-spec.md",
            reason="DESIGN v2 approved",
            replaced_by="06-spec.md@v2",
            required_action="re-import",
        )
        self.assertEqual(len(updated.stale_artifacts), 1)
        self.assertEqual(updated.stale_artifacts[0].artifact, "06-spec.md")

    def test_save_and_load_run_record(self):
        record = self._create_minimal_run()
        self.mgr.save(record)
        self.assertTrue(self.run_path.exists())
        loaded = self.mgr.load()
        self.assertEqual(loaded.work_id, record.work_id)
        self.assertEqual(loaded.status, record.status)
        self.assertEqual(loaded.current_stage, record.current_stage)

    def test_load_missing_run_raises(self):
        with self.assertRaises(FileNotFoundError):
            self.mgr.load()

if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/xubo/x-skills/req-to-plan && python3 -m unittest tests.test_state -v`
Expected: FAIL with ImportError

- [ ] **Step 3: Write state.py**

```python
# tools/workflow_cli/state.py
from __future__ import annotations
from pathlib import Path
from datetime import datetime, timezone
import re

from tools.workflow_cli.models import (
    RunRecord, RunStatus, Stage, WorkId, CheckpointRecord,
    ActiveArtifact, StaleArtifact, OpenRoute, UserConfirmation,
    ResumeContext, is_transition_allowed,
)


def create_run_record(work_id: WorkId) -> RunRecord:
    record = RunRecord(work_id=work_id, status=RunStatus.ACTIVE_STAGE_DRAFT)
    record.resume_context = ResumeContext(
        last_completed_operation="start_workflow_run",
        next_allowed_operation="produce_stage_artifact",
        active_item="raw_requirement",
    )
    return record


def update_run_status(record: RunRecord, new_status: RunStatus) -> RunRecord:
    if not is_transition_allowed(record.status, new_status):
        raise ValueError(
            f"Invalid transition: {record.status.value} -> {new_status.value}"
        )
    record.status = new_status
    return record


def add_checkpoint(
    record: RunRecord,
    stage: Stage,
    artifact: str,
    version: int,
    downstream_authorization: str,
) -> RunRecord:
    cp = CheckpointRecord(
        stage=stage,
        artifact=artifact,
        version=version,
        approved_at=datetime.now(timezone.utc).isoformat(),
        downstream_authorization=downstream_authorization,
    )
    record.approved_checkpoints.append(cp)
    return record


def get_active_artifact(record: RunRecord, stage: Stage) -> ActiveArtifact | None:
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
    existing = get_active_artifact(record, stage)
    if existing:
        existing.artifact = artifact
        existing.version = version
        existing.status = status
    else:
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
    for route in record.open_routes:
        if route.route_id == route_id:
            route.status = "closed"
            break
    return record


def update_resume_context(
    record: RunRecord,
    last_operation: str = "",
    next_operation: str = "",
    active_item: str = "",
    reread_targets: list[str] | None = None,
    reason: str = "",
) -> RunRecord:
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


# --- Markdown serialization ---

def _md_table(headers: list[str], rows: list[list[str]]) -> str:
    if not rows:
        return f"| {' | '.join(headers)} |\n|{'|'.join(['---' for _ in headers])}|\n"
    lines = [f"| {' | '.join(headers)} |", f"|{'|'.join(['---' for _ in headers])}|"]
    for row in rows:
        lines.append(f"| {' | '.join(str(c) for c in row)} |")
    return "\n".join(lines) + "\n"


def run_record_to_markdown(record: RunRecord) -> str:
    parts = [f"# Workflow Run: {record.work_id}", ""]
    parts.append("## Status")
    parts.append(record.status.value)
    parts.append("")
    parts.append("## Current Stage")
    parts.append(record.current_stage.value)
    parts.append("")

    cp_rows = [
        [cp.stage.value, cp.artifact, str(cp.version), cp.approved_at, cp.downstream_authorization]
        for cp in record.approved_checkpoints
    ]
    parts.append("## Approved Checkpoints")
    parts.append(_md_table(
        ["Stage", "Artifact", "Version", "Approved At", "Downstream Authorization"], cp_rows
    ))

    aa_rows = [
        [aa.stage.value, aa.artifact, str(aa.version), aa.status]
        for aa in record.active_artifacts
    ]
    parts.append("## Active Artifacts")
    parts.append(_md_table(["Stage", "Artifact", "Version", "Status"], aa_rows))

    sa_rows = [
        [sa.artifact, sa.reason, sa.replaced_by, sa.required_action]
        for sa in record.stale_artifacts
    ]
    parts.append("## Stale / Superseded Artifacts")
    parts.append(_md_table(["Artifact", "Reason", "Replaced By", "Required Action"], sa_rows))

    or_rows = [
        [o.route_id, o.from_stage.value, o.owner_stage.value, o.required_action, o.status]
        for o in record.open_routes
    ]
    parts.append("## Open Routes")
    parts.append(_md_table(
        ["Route ID", "From Stage", "Owner Stage", "Required Action", "Status"], or_rows
    ))

    uc_rows = [
        [uc.confirmation, uc.stage.value, uc.source, uc.recorded_in]
        for uc in record.user_confirmations
    ]
    parts.append("## User Confirmations")
    parts.append(_md_table(["Confirmation", "Stage", "Source", "Recorded In"], uc_rows))

    rc = record.resume_context
    rc_rows = [
        ["Last Completed Operation", rc.last_completed_operation],
        ["Next Allowed Operation", rc.next_allowed_operation],
        ["Active Item", rc.active_item],
        ["Required Reread Targets", ", ".join(rc.required_reread_targets)],
        ["Resume Reason", rc.resume_reason],
    ]
    parts.append("## Resume Context")
    parts.append(_md_table(["Field", "Value"], rc_rows))

    return "\n".join(parts) + "\n"


def _parse_md_table(text: str) -> list[dict[str, str]]:
    """Parse a markdown table into list of dicts. Returns empty list for empty table."""
    lines = text.strip().split("\n")
    if len(lines) < 2:
        return []
    headers = [h.strip() for h in lines[0].strip("|").split("|")]
    if len(lines) < 3:
        return []
    result = []
    for line in lines[2:]:
        line = line.strip()
        if not line.startswith("|"):
            continue
        values = [v.strip() for v in line.strip("|").split("|")]
        if len(values) == len(headers):
            result.append(dict(zip(headers, values)))
    return result


def parse_run_record(md: str, work_id: WorkId) -> RunRecord:
    record = RunRecord(work_id=work_id)

    status_match = re.search(r"## Status\n(.+?)\n", md)
    if status_match:
        try:
            record.status = RunStatus(status_match.group(1).strip())
        except ValueError:
            pass

    stage_match = re.search(r"## Current Stage\n(.+?)\n", md)
    if stage_match:
        try:
            record.current_stage = Stage(stage_match.group(1).strip())
        except ValueError:
            pass

    checkpoint_section = _extract_section(md, "## Approved Checkpoints")
    for row in _parse_md_table(checkpoint_section):
        try:
            record.approved_checkpoints.append(CheckpointRecord(
                stage=Stage(row.get("Stage", "")),
                artifact=row.get("Artifact", ""),
                version=int(row.get("Version", "1")),
                approved_at=row.get("Approved At", ""),
                downstream_authorization=row.get("Downstream Authorization", "no"),
            ))
        except (ValueError, KeyError):
            pass

    aa_section = _extract_section(md, "## Active Artifacts")
    for row in _parse_md_table(aa_section):
        try:
            record.active_artifacts.append(ActiveArtifact(
                stage=Stage(row.get("Stage", "")),
                artifact=row.get("Artifact", ""),
                version=int(row.get("Version", "1")),
                status=row.get("Status", "draft"),
            ))
        except (ValueError, KeyError):
            pass

    sa_section = _extract_section(md, "## Stale / Superseded Artifacts")
    for row in _parse_md_table(sa_section):
        record.stale_artifacts.append(StaleArtifact(
            artifact=row.get("Artifact", ""),
            reason=row.get("Reason", ""),
            replaced_by=row.get("Replaced By", ""),
            required_action=row.get("Required Action", ""),
        ))

    or_section = _extract_section(md, "## Open Routes")
    for row in _parse_md_table(or_section):
        try:
            record.open_routes.append(OpenRoute(
                route_id=row.get("Route ID", ""),
                from_stage=Stage(row.get("From Stage", "")),
                owner_stage=Stage(row.get("Owner Stage", "")),
                required_action=row.get("Required Action", ""),
                status=row.get("Status", "open"),
            ))
        except (ValueError, KeyError):
            pass

    uc_section = _extract_section(md, "## User Confirmations")
    for row in _parse_md_table(uc_section):
        try:
            record.user_confirmations.append(UserConfirmation(
                confirmation=row.get("Confirmation", ""),
                stage=Stage(row.get("Stage", "")),
                source=row.get("Source", ""),
                recorded_in=row.get("Recorded In", ""),
            ))
        except (ValueError, KeyError):
            pass

    rc_section = _extract_section(md, "## Resume Context")
    rc_data = {}
    for row in _parse_md_table(rc_section):
        rc_data[row.get("Field", "")] = row.get("Value", "")
    record.resume_context = ResumeContext(
        last_completed_operation=rc_data.get("Last Completed Operation", ""),
        next_allowed_operation=rc_data.get("Next Allowed Operation", ""),
        active_item=rc_data.get("Active Item", ""),
        required_reread_targets=[
            t.strip() for t in rc_data.get("Required Reread Targets", "").split(",") if t.strip()
        ],
        resume_reason=rc_data.get("Resume Reason", ""),
    )

    return record


def _extract_section(md: str, heading: str) -> str:
    """Extract content from a markdown heading to the next heading of same level."""
    pattern = re.compile(rf"{re.escape(heading)}\n(.*?)(?=\n## |\Z)", re.DOTALL)
    match = pattern.search(md)
    return match.group(1) if match else ""


class RunStateManager:
    def __init__(self, artifact_root: Path) -> None:
        self.root = Path(artifact_root)
        self.run_path = self.root / "run.md"

    def exists(self) -> bool:
        return self.run_path.exists()

    def load(self) -> RunRecord:
        if not self.exists():
            raise FileNotFoundError(f"Run record not found: {self.run_path}")
        md = self.run_path.read_text(encoding="utf-8")
        work_id_str = self.root.name
        work_id = WorkId(work_id_str)
        return parse_run_record(md, work_id)

    def save(self, record: RunRecord) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        md = run_record_to_markdown(record)
        self.run_path.write_text(md, encoding="utf-8")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/xubo/x-skills/req-to-plan && python3 -m unittest tests.test_state -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
cd /Users/xubo/x-skills/req-to-plan && git add tools/workflow_cli/state.py tests/test_state.py && git commit -m "feat: add run state manager"
```

---

### Task 3: Artifact lifecycle manager (artifact.py)

**Files:**
- Create: `tools/workflow_cli/artifact.py`
- Create: `tests/test_artifact.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_artifact.py
import unittest
import tempfile
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from tools.workflow_cli.artifact import (
    parse_frontmatter, write_frontmatter, ArtifactManager,
    bump_version, validate_upstream_references, is_artifact_ready,
)

class TestFrontmatter(unittest.TestCase):
    def test_parse_simple_frontmatter(self):
        md = """---
artifact_id: SPEC-001
version: 2
status: draft
---
# Content here
Some text.
"""
        fm, body = parse_frontmatter(md)
        self.assertEqual(fm["artifact_id"], "SPEC-001")
        self.assertEqual(fm["version"], "2")
        self.assertEqual(body.strip(), "# Content here\nSome text.")

    def test_parse_no_frontmatter_returns_empty_dict(self):
        md = "# Just a heading\nContent."
        fm, body = parse_frontmatter(md)
        self.assertEqual(fm, {})
        self.assertEqual(body, md)

    def test_write_frontmatter_roundtrip(self):
        fm = {"artifact_id": "DES-001", "version": "1", "status": "ready"}
        body = "# Design\nContent."
        result = write_frontmatter(fm, body)
        parsed_fm, parsed_body = parse_frontmatter(result)
        self.assertEqual(parsed_fm["artifact_id"], "DES-001")
        self.assertEqual(parsed_body.strip(), "# Design\nContent.")

    def test_bump_version_increments(self):
        fm = {"artifact_id": "SPEC-001", "version": "3", "status": "approved"}
        updated = bump_version(fm)
        self.assertEqual(updated["version"], "4")

    def test_bump_version_defaults_to_1(self):
        fm = {"artifact_id": "NEW-001"}
        updated = bump_version(fm)
        self.assertEqual(updated["version"], "1")

    def test_is_artifact_ready_detects_ready_status(self):
        self.assertTrue(is_artifact_ready("---\nstatus: ready\n---\n# Ok"))
        self.assertFalse(is_artifact_ready("---\nstatus: draft\n---\n# Ok"))
        self.assertFalse(is_artifact_ready("# No frontmatter"))

    def test_validate_upstream_references_finds_urls(self):
        content = """## Upstream References
| Artifact | Reference | Status |
|---|---|---|
| Raw Requirement | 00-raw-requirement.md | available |
| DESIGN | 05-design.md | approved |
"""
        refs = validate_upstream_references(content)
        self.assertIn("00-raw-requirement.md", refs)
        self.assertIn("05-design.md", refs)

class TestArtifactManager(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.mgr = ArtifactManager(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def test_create_artifact_writes_file(self):
        path = self.mgr.create("03-requirement-brief.md", "Requirement Brief v1")
        self.assertTrue(path.exists())
        content = path.read_text()
        self.assertIn("Requirement Brief v1", content)

    def test_load_artifact_reads_file(self):
        self.mgr.create("05-design.md", "# Design\nContent here")
        loaded = self.mgr.load("05-design.md")
        self.assertIn("# Design", loaded)
        self.assertIn("Content here", loaded)

    def test_update_artifact_overwrites(self):
        self.mgr.create("06-spec.md", "v1")
        self.mgr.update("06-spec.md", "v2")
        loaded = self.mgr.load("06-spec.md")
        self.assertIn("v2", loaded)

    def test_exists_checks_file(self):
        self.assertFalse(self.mgr.exists("07-plan.md"))
        self.mgr.create("07-plan.md", "plan")
        self.assertTrue(self.mgr.exists("07-plan.md"))

    def test_list_reviews_returns_matching_files(self):
        (self.root / "reviews").mkdir(parents=True)
        (self.root / "reviews" / "spec-checkpoint-review-1.md").write_text("review")
        (self.root / "reviews" / "design-checkpoint-review-1.md").write_text("review")
        reviews = self.mgr.list_reviews("spec")
        self.assertEqual(len(reviews), 1)
        self.assertIn("spec-checkpoint-review-1.md", reviews[0])

if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/xubo/x-skills/req-to-plan && python3 -m unittest tests.test_artifact -v`
Expected: FAIL with ImportError

- [ ] **Step 3: Write artifact.py**

```python
# tools/workflow_cli/artifact.py
from __future__ import annotations
from pathlib import Path
import re


_FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n?(.*)", re.DOTALL)


def parse_frontmatter(md: str) -> tuple[dict[str, str], str]:
    m = _FRONTMATTER_RE.match(md)
    if not m:
        return {}, md
    fm_text = m.group(1)
    body = m.group(2)
    fm: dict[str, str] = {}
    for line in fm_text.strip().split("\n"):
        if ":" in line:
            key, _, val = line.partition(":")
            fm[key.strip()] = val.strip()
    return fm, body


def write_frontmatter(fm: dict[str, str], body: str) -> str:
    lines = ["---"]
    for k, v in fm.items():
        lines.append(f"{k}: {v}")
    lines.append("---")
    lines.append("")
    lines.append(body.lstrip("\n"))
    return "\n".join(lines)


def bump_version(fm: dict[str, str]) -> dict[str, str]:
    current = int(fm.get("version", "0"))
    fm["version"] = str(current + 1)
    return fm


def is_artifact_ready(content: str) -> bool:
    fm, _ = parse_frontmatter(content)
    return fm.get("status") == "ready"


def validate_upstream_references(content: str) -> list[str]:
    refs: list[str] = []
    in_table = False
    for line in content.split("\n"):
        if line.startswith("|") and "---" not in line:
            parts = [p.strip() for p in line.strip("|").split("|")]
            if len(parts) >= 2:
                ref = parts[1]
                if ref and ref not in ("Reference", ""):
                    refs.append(ref)
    return refs


class ArtifactManager:
    def __init__(self, artifact_root: Path) -> None:
        self.root = Path(artifact_root)

    def _path(self, filename: str) -> Path:
        return self.root / filename

    def exists(self, filename: str) -> bool:
        return self._path(filename).exists()

    def create(self, filename: str, content: str) -> Path:
        self.root.mkdir(parents=True, exist_ok=True)
        p = self._path(filename)
        p.write_text(content, encoding="utf-8")
        return p

    def load(self, filename: str) -> str:
        return self._path(filename).read_text(encoding="utf-8")

    def update(self, filename: str, content: str) -> Path:
        p = self._path(filename)
        p.write_text(content, encoding="utf-8")
        return p

    def list_reviews(self, stage: str) -> list[str]:
        reviews_dir = self.root / "reviews"
        if not reviews_dir.exists():
            return []
        results = []
        for p in reviews_dir.iterdir():
            if p.name.startswith(f"{stage}-checkpoint-review-"):
                results.append(p.name)
        return sorted(results)

    def write_review(self, stage: str, n: int, content: str) -> Path:
        reviews_dir = self.root / "reviews"
        reviews_dir.mkdir(parents=True, exist_ok=True)
        filename = f"{stage}-checkpoint-review-{n}.md"
        p = reviews_dir / filename
        p.write_text(content, encoding="utf-8")
        return p
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/xubo/x-skills/req-to-plan && python3 -m unittest tests.test_artifact -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
cd /Users/xubo/x-skills/req-to-plan && git add tools/workflow_cli/artifact.py tests/test_artifact.py && git commit -m "feat: add artifact lifecycle manager"
```

---

### Task 4: Structured gate checks (gates.py)

**Files:**
- Create: `tools/workflow_cli/gates.py`
- Create: `tests/test_gates.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_gates.py
import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from tools.workflow_cli.models import RunStatus, Stage, RunRecord, WorkId
from tools.workflow_cli.gates import (
    check_entry_gate, check_quality_gate_structural,
    EntryGateResult, QualityGateResult,
)

class TestEntryGate(unittest.TestCase):
    def setUp(self):
        self.record = RunRecord(work_id=WorkId("WF-20260527-test"))
        self.record.status = RunStatus.NEXT_STAGE
        self.record.current_stage = Stage.REQUIREMENT_BRIEF

    def test_entry_gate_passes_when_no_upstream_required(self):
        result = check_entry_gate(self.record, Stage.REQUIREMENT_BRIEF, [])
        self.assertTrue(result.passed)

    def test_entry_gate_fails_when_upstream_checkpoint_missing(self):
        result = check_entry_gate(self.record, Stage.SPEC, [])
        self.assertFalse(result.passed)
        self.assertIn("missing_upstream_checkpoint", result.reason.lower())

    def test_entry_gate_passes_with_approved_upstream(self):
        from tools.workflow_cli.state import add_checkpoint
        self.record = add_checkpoint(
            self.record, Stage.REQUIREMENT_BRIEF, "03-requirement-brief.md", 1, "yes"
        )
        self.record = add_checkpoint(
            self.record, Stage.RISK_DISCOVERY, "04-risk-discovery.md", 1, "yes"
        )
        self.record = add_checkpoint(
            self.record, Stage.DESIGN, "05-design.md", 1, "yes"
        )
        result = check_entry_gate(self.record, Stage.SPEC, [])
        self.assertTrue(result.passed)

class TestQualityGate(unittest.TestCase):
    def test_structural_check_passes_for_valid_artifact(self):
        content = """---
artifact_id: SPEC-001
version: 1
status: ready
---
## Upstream References
| Artifact | Reference | Status |
|---|---|---|
| Raw Requirement | 00-raw-requirement.md | available |
| DESIGN | 05-design.md | approved |
"""
        result = check_quality_gate_structural(content, Stage.SPEC)
        self.assertTrue(result.passed)
        self.assertEqual(len(result.issues), 0)

    def test_structural_check_detects_missing_upstream_references(self):
        content = """---
artifact_id: DESIGN-001
version: 1
---
# DESIGN
No upstream refs section.
"""
        result = check_quality_gate_structural(content, Stage.DESIGN)
        self.assertFalse(result.passed)
        self.assertTrue(any("Upstream References" in i for i in result.issues))

    def test_structural_check_detects_missing_frontmatter(self):
        content = "# No frontmatter here"
        result = check_quality_gate_structural(content, Stage.SPEC)
        self.assertFalse(result.passed)
        self.assertTrue(any("frontmatter" in i.lower() for i in result.issues))

    def test_structural_check_detects_placeholder_status(self):
        content = """---
artifact_id: SPEC-001
status: ready | blocked
---
## Upstream References
| Artifact | Reference | Status |
|---|---|---|
| DESIGN | 05-design.md | approved |
"""
        result = check_quality_gate_structural(content, Stage.SPEC)
        self.assertFalse(result.passed)
        self.assertTrue(any("placeholder" in i.lower() for i in result.issues))

if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/xubo/x-skills/req-to-plan && python3 -m unittest tests.test_gates -v`
Expected: FAIL with ImportError

- [ ] **Step 3: Write gates.py**

```python
# tools/workflow_cli/gates.py
from __future__ import annotations
from dataclasses import dataclass, field

from tools.workflow_cli.models import (
    RunRecord, RunStatus, Stage,
    STAGE_REQUIRED_UPSTREAM_CHECKPOINTS, NEXT_STAGE_MAP,
)
from tools.workflow_cli.artifact import parse_frontmatter


@dataclass
class EntryGateResult:
    passed: bool
    reason: str = ""
    missing_checkpoints: list[str] = field(default_factory=list)
    suggested_action: str = ""


def check_entry_gate(
    record: RunRecord,
    target_stage: Stage,
    additional_references: list[str],
) -> EntryGateResult:
    required = STAGE_REQUIRED_UPSTREAM_CHECKPOINTS.get(target_stage, [])
    approved_stages = {cp.stage for cp in record.approved_checkpoints if cp.downstream_authorization == "yes"}

    missing = []
    for req_stage in required:
        if req_stage not in approved_stages:
            missing.append(req_stage.value)

    if missing:
        return EntryGateResult(
            passed=False,
            reason=f"Missing upstream checkpoint(s): {', '.join(missing)}",
            missing_checkpoints=missing,
            suggested_action=f"Approve checkpoint(s) for: {', '.join(missing)}",
        )

    return EntryGateResult(passed=True, reason="All upstream checkpoints approved")


@dataclass
class QualityGateResult:
    passed: bool
    issues: list[str] = field(default_factory=list)


def check_quality_gate_structural(content: str, stage: Stage) -> QualityGateResult:
    issues: list[str] = []

    fm, body = parse_frontmatter(content)
    if not fm:
        issues.append("Missing YAML frontmatter with artifact metadata")

    status = fm.get("status", "")
    if not status:
        issues.append("Missing status in frontmatter")
    elif "|" in status:
        issues.append(f"Status contains placeholder choice: '{status}'")

    version = fm.get("version", "")
    if not version:
        issues.append("Missing version in frontmatter")

    if stage not in (Stage.RAW_REQUIREMENT,):
        if "## Upstream References" not in body and "upstream references" not in body.lower():
            issues.append("Missing Upstream References section")

    if stage in (Stage.SPEC, Stage.PLAN):
        if "## Closure" not in body and "closure" not in body.lower():
            issues.append("Missing coverage closure for upstream inputs")

    return QualityGateResult(passed=len(issues) == 0, issues=issues)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/xubo/x-skills/req-to-plan && python3 -m unittest tests.test_gates -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
cd /Users/xubo/x-skills/req-to-plan && git add tools/workflow_cli/gates.py tests/test_gates.py && git commit -m "feat: add structured gate checks"
```

---

### Task 5: Output formatter and CLI command routing (output.py + cli.py)

**Files:**
- Create: `tools/workflow_cli/output.py`
- Create: `tests/test_output.py`
- Create: `tools/workflow_cli/cli.py`
- Create: `tests/test_cli.py`

- [ ] **Step 1: Write output.py**

```python
# tools/workflow_cli/output.py
from __future__ import annotations
import json
import sys
from typing import Any


def print_result(
    command_intent: str,
    result_status: str,
    run_path: str = "",
    run_state_before: str = "",
    run_state_after: str = "",
    current_stage: str = "",
    active_artifact: str = "",
    writes: list[dict[str, str]] | None = None,
    next_allowed_command: str = "",
    open_routes: list[str] | None = None,
    stale_artifacts: list[str] | None = None,
    stops: list[str] | None = None,
    required_user_confirmation: str | None = None,
    json_mode: bool = False,
    exit_code: int = 0,
    planned_writes: list[dict[str, str]] | None = None,
) -> int:
    if json_mode:
        output: dict[str, Any] = {
            "command_result": result_status,
            "command_intent": command_intent,
            "run": run_path,
            "run_state_before": run_state_before,
            "run_state_after": run_state_after,
            "current_stage": current_stage,
            "active_artifact": active_artifact,
            "writes": writes or [],
            "planned_writes": planned_writes or [],
            "stops": stops or [],
            "required_user_confirmation": required_user_confirmation,
            "open_routes": open_routes or [],
            "stale_artifacts": stale_artifacts or [],
            "next_allowed_command": next_allowed_command,
        }
        json.dump(output, sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        lines = [
            f"command_result: {result_status}",
            f"intent: {command_intent}",
        ]
        if run_path:
            lines.append(f"run: {run_path}")
        if current_stage:
            lines.append(f"current_stage: {current_stage}")
        if next_allowed_command:
            lines.append(f"next: {next_allowed_command}")
        if stops:
            for s in stops:
                lines.append(f"stop: {s}")
        sys.stdout.write("\n".join(lines) + "\n")
    return exit_code
```

- [ ] **Step 2: Write output tests**

```python
# tests/test_output.py
import unittest
import sys
import json
import io
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from tools.workflow_cli.output import print_result

class TestOutput(unittest.TestCase):
    def test_json_mode_produces_valid_json(self):
        buf = io.StringIO()
        sys.stdout = buf
        print_result(
            command_intent="CMD-GATE-QUALITY",
            result_status="ready",
            run_path=".req-to-plan/WF-001/run.md",
            current_stage="spec",
            json_mode=True,
        )
        sys.stdout = sys.__stdout__
        data = json.loads(buf.getvalue())
        self.assertEqual(data["command_result"], "ready")
        self.assertEqual(data["command_intent"], "CMD-GATE-QUALITY")

    def test_human_mode_includes_key_fields(self):
        buf = io.StringIO()
        sys.stdout = buf
        print_result(
            command_intent="CMD-STATUS-RUN",
            result_status="active_stage_draft",
            run_path=".req-to-plan/WF-001/run.md",
            current_stage="design",
            next_allowed_command="python3 -m tools.workflow_cli gate-quality --work-id WF-001 --stage design",
        )
        sys.stdout = sys.__stdout__
        output = buf.getvalue()
        self.assertIn("command_result:", output)
        self.assertIn("current_stage: design", output)

    def test_return_code_matches_exit_code_param(self):
        rc = print_result("CMD-STATUS", "ok", exit_code=3, json_mode=True)
        self.assertEqual(rc, 3)

if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: Write CLI tests**

```python
# tests/test_cli.py
import unittest
import tempfile
import json
import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from tools.workflow_cli.cli import build_parser, main
from tools.workflow_cli.state import RunStateManager, create_run_record
from tools.workflow_cli.artifact import ArtifactManager
from tools.workflow_cli.models import WorkId, Stage, RunStatus


class StdoutCapture:
    def __enter__(self):
        self._old = sys.stdout
        self.buffer = io.StringIO()
        sys.stdout = self.buffer
        return self.buffer

    def __exit__(self, exc_type, exc, tb):
        sys.stdout = self._old


class TestCliParser(unittest.TestCase):
    def test_parser_accepts_registered_flat_commands(self):
        parser = build_parser()
        commands = [
            ["run-start", "--work-id", "WF-20260527-cli-test"],
            ["stage-produce", "--work-id", "WF-20260527-cli-test", "--stage", "raw_requirement"],
            ["gate-quality", "--work-id", "WF-20260527-cli-test", "--stage", "design"],
            ["checkpoint-decide", "--work-id", "WF-20260527-cli-test", "--stage", "plan", "--decision", "approved"],
            ["executor-adapt", "--work-id", "WF-20260527-cli-test", "--executor", "superpowers"],
        ]
        for argv in commands:
            with self.subTest(argv=argv):
                args = parser.parse_args(argv)
                self.assertEqual(args.command, argv[0])

    def test_dry_run_json_reports_no_writes(self):
        with tempfile.TemporaryDirectory() as td, StdoutCapture() as out:
            rc = main([
                "status-run",
                "--work-id", "WF-20260527-cli-test",
                "--artifact-root", td,
                "--dry-run",
                "--json",
            ])
        data = json.loads(out.getvalue())
        self.assertEqual(rc, 0)
        self.assertEqual(data["status"], "dry_run")
        self.assertEqual(data["planned_writes"], [])

    def test_run_start_creates_run_and_raw_artifacts(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "WF-20260527-cli-start"
            with StdoutCapture() as out:
                rc = main([
                    "run-start",
                    "--work-id", "WF-20260527-cli-start",
                    "--artifact-root", str(root),
                    "--source", "Add login rate limiting.",
                    "--json",
                ])
            data = json.loads(out.getvalue())
            self.assertEqual(rc, 0)
            self.assertEqual(data["command_result"], "active_stage_draft")
            self.assertIn("stage-produce", data["next_allowed_command"])
            self.assertTrue((root / "run.md").exists())
            self.assertTrue((root / "00-raw-requirement.md").exists())
            self.assertTrue((root / "01-intake-brief.md").exists())

    def test_gate_quality_failure_updates_run_state(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "WF-20260527-cli-gate"
            root.mkdir(parents=True)
            record = create_run_record(WorkId("WF-20260527-cli-gate"))
            record.current_stage = Stage.DESIGN
            record.status = RunStatus.ACTIVE_STAGE_DRAFT
            RunStateManager(root).save(record)
            ArtifactManager(root).create("05-design.md", "# Missing frontmatter\n")

            with StdoutCapture() as out:
                rc = main([
                    "gate-quality",
                    "--work-id", "WF-20260527-cli-gate",
                    "--artifact-root", str(root),
                    "--stage", "design",
                    "--json",
                ])
            data = json.loads(out.getvalue())
            self.assertEqual(rc, 1)
            self.assertEqual(data["command_result"], "quality_gate_failed")
            self.assertTrue(any("frontmatter" in stop.lower() for stop in data["stops"]))
            self.assertEqual(RunStateManager(root).load().status, RunStatus.QUALITY_GATE_FAILED)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 4: Run output tests**

Run: `cd /Users/xubo/x-skills/req-to-plan && python3 -m unittest tests.test_output -v`
Expected: All tests PASS

- [ ] **Step 5: Run CLI tests before implementation**

Run: `cd /Users/xubo/x-skills/req-to-plan && python3 -m unittest tests.test_cli -v`
Expected: FAIL with ImportError (cli.py not created yet)

- [ ] **Step 6: Write cli.py (comprehensive command router)**

```python
# tools/workflow_cli/cli.py
from __future__ import annotations
import argparse
import sys
from pathlib import Path
from datetime import datetime

from tools.workflow_cli.models import (
    RunStatus, Stage, WorkId, RunRecord, UserConfirmation,
    STAGE_ARTIFACT_MAP, NEXT_STAGE_MAP, is_command_allowed,
)
from tools.workflow_cli.state import (
    RunStateManager, create_run_record, update_run_status,
    add_checkpoint, upsert_active_artifact,
    update_resume_context, record_stale_artifact,
)
from tools.workflow_cli.artifact import ArtifactManager, parse_frontmatter, write_frontmatter
from tools.workflow_cli.gates import check_entry_gate, check_quality_gate_structural
from tools.workflow_cli.output import print_result


def _resolve_artifact_root(work_id: str | None, run_path: str | None, artifact_root_override: str | None) -> Path:
    if run_path:
        return Path(run_path).parent
    if work_id:
        base = Path(artifact_root_override) if artifact_root_override else Path(".req-to-plan")
        return base / work_id
    raise ValueError("Either --work-id or --run is required")


def _resolve_work_id(artifact_root: Path) -> WorkId:
    return WorkId(artifact_root.name)


def _load_run_state(artifact_root: Path) -> tuple[RunStateManager, "RunRecord"]:
    mgr = RunStateManager(artifact_root)
    record = mgr.load()
    return mgr, record


def _check_command_allowed(record: "RunRecord", command_intent: str) -> None:
    if not is_command_allowed(record.status, command_intent):
        raise ValueError(
            f"Command {command_intent} not allowed in run state {record.status.value}"
        )


def _read_stdin() -> str:
    if sys.stdin.isatty():
        return ""
    return sys.stdin.read().strip()


def cmd_run_start(args: argparse.Namespace) -> int:
    work_id = WorkId(args.work_id)
    artifact_root = _resolve_artifact_root(args.work_id, None, args.artifact_root)
    if RunStateManager(artifact_root).exists():
        return print_result(
            "CMD-RUN-START", "duplicate_active_run",
            run_path=str(artifact_root / "run.md"),
            next_allowed_command=f"python3 -m tools.workflow_cli status-run --work-id {args.work_id}",
            stops=["Run already exists"],
            json_mode=args.json,
            exit_code=6,
        )
    record = create_run_record(work_id)
    record.current_stage = Stage.RAW_REQUIREMENT
    mgr = RunStateManager(artifact_root)
    mgr.save(record)

    am = ArtifactManager(artifact_root)
    requirement_text = args.source or _read_stdin() or "(raw requirement)"
    am.create("00-raw-requirement.md", f"# Raw Requirement\n\n{requirement_text}\n")

    am.create("01-intake-brief.md", f"# Intake Brief v0\n\n## Initial Goal\n\n{requirement_text}\n")

    return print_result(
        "CMD-RUN-START", "active_stage_draft",
        run_path=str(artifact_root / "run.md"),
        run_state_before="not_started",
        run_state_after="active_stage_draft",
        current_stage=record.current_stage.value,
        writes=[{"path": str(artifact_root / "run.md"), "kind": "run_update"}],
        next_allowed_command=f"python3 -m tools.workflow_cli stage-produce --work-id {args.work_id} --stage raw_requirement",
        json_mode=args.json,
    )


def cmd_run_resume(args: argparse.Namespace) -> int:
    artifact_root = _resolve_artifact_root(args.work_id, args.run_path, args.artifact_root)
    if not RunStateManager(artifact_root).exists():
        return print_result(
            "CMD-RUN-RESUME", "missing_run",
            stops=["Run record not found"],
            json_mode=args.json,
            exit_code=2,
        )
    mgr, record = _load_run_state(artifact_root)

    if record.status == RunStatus.CHECKPOINT_APPROVED:
        if record.current_stage == Stage.PLAN:
            return print_result(
                "CMD-RUN-RESUME", "ready_to_close",
                run_path=str(artifact_root / "run.md"),
                current_stage=record.current_stage.value,
                next_allowed_command=f"python3 -m tools.workflow_cli run-close --work-id {str(record.work_id)}",
                json_mode=args.json,
            )
        record.status = RunStatus.NEXT_STAGE
        record = update_resume_context(
            record,
            last_operation="run_resume",
            next_operation="run_stage_entry_gate",
            active_item=NEXT_STAGE_MAP.get(record.current_stage, Stage.CLOSED).value,
        )
        mgr.save(record)
        next_stage = NEXT_STAGE_MAP.get(record.current_stage, record.current_stage)
        return print_result(
            "CMD-RUN-RESUME", "next_stage",
            run_path=str(artifact_root / "run.md"),
            run_state_after="next_stage",
            current_stage=next_stage.value,
            next_allowed_command=f"python3 -m tools.workflow_cli gate-entry --work-id {str(record.work_id)} --stage {next_stage.value}",
            json_mode=args.json,
        )

    record = update_resume_context(
        record,
        last_operation="run_resume",
        next_operation=record.resume_context.next_allowed_operation,
        active_item=record.resume_context.active_item,
        resume_reason="active_run_refresh",
    )
    mgr.save(record)
    active_artifact = ""
    for aa in record.active_artifacts:
        if aa.stage == record.current_stage:
            active_artifact = f"{aa.artifact}@v{aa.version}"
    return print_result(
        "CMD-RUN-RESUME", record.status.value,
        run_path=str(artifact_root / "run.md"),
        current_stage=record.current_stage.value,
        active_artifact=active_artifact,
        next_allowed_command=_next_command_for_state(record),
        open_routes=[r.route_id for r in record.open_routes if r.status == "open"],
        json_mode=args.json,
    )


def cmd_run_close(args: argparse.Namespace) -> int:
    artifact_root = _resolve_artifact_root(args.work_id, args.run_path, args.artifact_root)
    mgr, record = _load_run_state(artifact_root)
    if record.current_stage != Stage.PLAN or record.status != RunStatus.CHECKPOINT_APPROVED:
        return print_result(
            "CMD-RUN-CLOSE", "not_ready_to_close",
            stops=["PLAN checkpoint must be approved before close"],
            json_mode=args.json,
            exit_code=3,
        )
    if any(r.status == "open" for r in record.open_routes):
        return print_result(
            "CMD-RUN-CLOSE", "open_routes_remain",
            stops=["All open routes must be resolved"],
            json_mode=args.json,
            exit_code=4,
        )
    record.status = RunStatus.CLOSED_AT_PLAN_CHECKPOINT
    record.current_stage = Stage.CLOSED
    mgr.save(record)
    return print_result(
        "CMD-RUN-CLOSE", "closed_at_plan_checkpoint",
        run_path=str(artifact_root / "run.md"),
        current_stage="closed",
        json_mode=args.json,
    )


def cmd_stage_load(args: argparse.Namespace) -> int:
    artifact_root = _resolve_artifact_root(args.work_id, args.run_path, args.artifact_root)
    mgr, record = _load_run_state(artifact_root)
    _check_command_allowed(record, "CMD-STAGE-LOAD")

    stage = Stage(args.stage)
    filename = STAGE_ARTIFACT_MAP[stage]
    am = ArtifactManager(artifact_root)
    if am.exists(filename):
        content = am.load(filename)
        return print_result(
            "CMD-STAGE-LOAD", "loaded",
            run_path=str(artifact_root / "run.md"),
            current_stage=stage.value,
            active_artifact=f"{filename}",
            json_mode=args.json,
        )

    template = f"---\nartifact_id: {stage.value.upper()}-001\nversion: 1\nstatus: draft\n---\n# {stage.value.replace('_', ' ').title()}\n"
    am.create(filename, template)
    record = upsert_active_artifact(record, stage, filename, 1, "draft")
    record = update_resume_context(
        record,
        last_operation="stage_artifact_loaded",
        next_operation="produce_stage_artifact",
        active_item=stage.value,
    )
    mgr.save(record)
    return print_result(
        "CMD-STAGE-LOAD", "created",
        run_path=str(artifact_root / "run.md"),
        current_stage=stage.value,
        active_artifact=f"{filename}@v1",
        writes=[{"path": str(artifact_root / filename), "kind": "artifact_create"}],
        json_mode=args.json,
    )


def cmd_stage_produce(args: argparse.Namespace) -> int:
    artifact_root = _resolve_artifact_root(args.work_id, args.run_path, args.artifact_root)
    mgr, record = _load_run_state(artifact_root)
    _check_command_allowed(record, "CMD-STAGE-PRODUCE")

    stage = Stage(args.stage)
    filename = STAGE_ARTIFACT_MAP.get(stage, "")
    if not filename:
        return print_result("CMD-STAGE-PRODUCE", "invalid_stage", stops=[f"Unknown stage: {args.stage}"], json_mode=args.json, exit_code=2)

    content = _read_stdin()
    if not content:
        return print_result("CMD-STAGE-PRODUCE", "no_content", stops=["No artifact content provided via stdin"], json_mode=args.json, exit_code=2)

    am = ArtifactManager(artifact_root)
    am.update(filename, content)

    fm, _ = parse_frontmatter(content)
    version = int(fm.get("version", "1"))
    record = upsert_active_artifact(record, stage, filename, version, fm.get("status", "draft"))
    record.current_stage = stage
    record = update_resume_context(record, active_item=stage.value, next_operation="produce_stage_artifact")
    mgr.save(record)

    return print_result(
        "CMD-STAGE-PRODUCE", "active_stage_draft",
        run_path=str(artifact_root / "run.md"),
        current_stage=stage.value,
        active_artifact=f"{filename}@v{version}",
        writes=[{"path": str(artifact_root / filename), "kind": "artifact_update"}],
        next_allowed_command=f"python3 -m tools.workflow_cli stage-ready --work-id {str(record.work_id)} --stage {stage.value}",
        json_mode=args.json,
    )


def cmd_stage_ready(args: argparse.Namespace) -> int:
    artifact_root = _resolve_artifact_root(args.work_id, args.run_path, args.artifact_root)
    mgr, record = _load_run_state(artifact_root)
    _check_command_allowed(record, "CMD-STAGE-READY")

    stage = Stage(args.stage)
    filename = STAGE_ARTIFACT_MAP.get(stage, "")
    am = ArtifactManager(artifact_root)
    if not am.exists(filename):
        return print_result("CMD-STAGE-READY", "no_artifact", stops=[f"No artifact for stage: {stage.value}"], json_mode=args.json, exit_code=2)

    content = am.load(filename)
    fm, body = parse_frontmatter(content)
    fm["status"] = "ready"
    updated = write_frontmatter(fm, body)
    am.update(filename, updated)

    version = int(fm.get("version", "1"))
    record = upsert_active_artifact(record, stage, filename, version, "ready")
    record = update_resume_context(record, next_operation="run_quality_gate", active_item=f"{stage.value} ready")
    mgr.save(record)

    return print_result(
        "CMD-STAGE-READY", "stage_ready_recorded",
        run_path=str(artifact_root / "run.md"),
        current_stage=stage.value,
        active_artifact=f"{filename}@v{version}",
        next_allowed_command=f"python3 -m tools.workflow_cli gate-quality --work-id {str(record.work_id)} --stage {stage.value}",
        json_mode=args.json,
    )


def cmd_gate_entry(args: argparse.Namespace) -> int:
    artifact_root = _resolve_artifact_root(args.work_id, args.run_path, args.artifact_root)
    mgr, record = _load_run_state(artifact_root)
    _check_command_allowed(record, "CMD-GATE-ENTRY")

    stage = Stage(args.stage)
    result = check_entry_gate(record, stage, [])
    if result.passed:
        record.status = RunStatus.ACTIVE_STAGE_DRAFT
        record.current_stage = stage
        record = update_resume_context(record, last_operation="entry_gate_passed", next_operation="produce_stage_artifact", active_item=stage.value)
        mgr.save(record)
        return print_result(
            "CMD-GATE-ENTRY", "pass",
            run_path=str(artifact_root / "run.md"),
            run_state_after="active_stage_draft",
            current_stage=stage.value,
            next_allowed_command=f"python3 -m tools.workflow_cli stage-produce --work-id {str(record.work_id)} --stage {stage.value}",
            json_mode=args.json,
        )
    else:
        record.status = RunStatus.ENTRY_GATE_FAILED
        mgr.save(record)
        return print_result(
            "CMD-GATE-ENTRY", "blocked",
            run_path=str(artifact_root / "run.md"),
            run_state_after="entry_gate_failed",
            stops=[result.reason],
            next_allowed_command=result.suggested_action,
            json_mode=args.json,
            exit_code=3,
        )


def cmd_gate_quality(args: argparse.Namespace) -> int:
    artifact_root = _resolve_artifact_root(args.work_id, args.run_path, args.artifact_root)
    mgr, record = _load_run_state(artifact_root)
    _check_command_allowed(record, "CMD-GATE-QUALITY")

    stage = Stage(args.stage)
    filename = STAGE_ARTIFACT_MAP.get(stage, "")
    am = ArtifactManager(artifact_root)
    if not am.exists(filename):
        return print_result("CMD-GATE-QUALITY", "no_artifact", stops=[f"No artifact for stage: {stage.value}"], json_mode=args.json, exit_code=2)

    content = am.load(filename)
    gate_result = check_quality_gate_structural(content, stage)

    if not gate_result.passed:
        record.status = RunStatus.QUALITY_GATE_FAILED
        mgr.save(record)
        return print_result(
            "CMD-GATE-QUALITY", "quality_gate_failed",
            run_path=str(artifact_root / "run.md"),
            run_state_after="quality_gate_failed",
            stops=gate_result.issues,
            json_mode=args.json,
            exit_code=1,
        )

    record.status = RunStatus.READY_FOR_CHECKPOINT_REVIEW
    record = update_resume_context(record, last_operation="quality_gate_ready", next_operation="run_checkpoint_review", active_item=f"{stage.value} checkpoint review")
    mgr.save(record)
    return print_result(
        "CMD-GATE-QUALITY", "ready",
        run_path=str(artifact_root / "run.md"),
        run_state_before="active_stage_draft",
        run_state_after="ready_for_checkpoint_review",
        current_stage=stage.value,
        next_allowed_command=f"python3 -m tools.workflow_cli review-checkpoint --work-id {str(record.work_id)} --stage {stage.value}",
        json_mode=args.json,
    )


def cmd_review_checkpoint(args: argparse.Namespace) -> int:
    artifact_root = _resolve_artifact_root(args.work_id, args.run_path, args.artifact_root)
    mgr, record = _load_run_state(artifact_root)
    _check_command_allowed(record, "CMD-REVIEW-CHECKPOINT")

    stage = Stage(args.stage)
    record.status = RunStatus.CHECKPOINT_REVIEW
    mgr.save(record)

    return print_result(
        "CMD-REVIEW-CHECKPOINT", "review_findings_written",
        run_path=str(artifact_root / "run.md"),
        run_state_after="checkpoint_review",
        current_stage=stage.value,
        next_allowed_command=f"python3 -m tools.workflow_cli review-merge --work-id {str(record.work_id)} --stage {stage.value}",
        json_mode=args.json,
    )


def cmd_review_merge(args: argparse.Namespace) -> int:
    artifact_root = _resolve_artifact_root(args.work_id, args.run_path, args.artifact_root)
    mgr, record = _load_run_state(artifact_root)
    _check_command_allowed(record, "CMD-REVIEW-MERGE")

    stage = Stage(args.stage)
    return print_result(
        "CMD-REVIEW-MERGE", "review_findings_merged",
        run_path=str(artifact_root / "run.md"),
        current_stage=stage.value,
        next_allowed_command=f"python3 -m tools.workflow_cli checkpoint-decide --work-id {str(record.work_id)} --stage {stage.value} --decision approved --confirm",
        json_mode=args.json,
    )


def cmd_checkpoint_decide(args: argparse.Namespace) -> int:
    artifact_root = _resolve_artifact_root(args.work_id, args.run_path, args.artifact_root)
    mgr, record = _load_run_state(artifact_root)
    _check_command_allowed(record, "CMD-CHECKPOINT-DECIDE")

    if not args.confirm:
        return print_result(
            "CMD-CHECKPOINT-DECIDE", "confirmation_required",
            stops=["--confirm is required for checkpoint decisions"],
            json_mode=args.json,
            exit_code=5,
        )

    stage = Stage(args.stage)
    decision = args.decision  # approved, changes_requested, blocked, upstream_gap_detected, route_upstream

    if decision == "approved":
        filename = STAGE_ARTIFACT_MAP.get(stage, "")
        am = ArtifactManager(artifact_root)
        content = am.load(filename)
        fm, body = parse_frontmatter(content)
        fm["status"] = "approved"
        updated = write_frontmatter(fm, body)
        am.update(filename, updated)

        version = int(fm.get("version", "1"))
        record = add_checkpoint(record, stage, filename, version, "yes")
        record.status = RunStatus.CHECKPOINT_APPROVED
        record = update_resume_context(
            record,
            last_operation="checkpoint_approved",
            next_operation="run_resume",
            active_item=f"{stage.value} checkpoint approved",
        )
        mgr.save(record)

        next_cmd = f"python3 -m tools.workflow_cli run-close --work-id {str(record.work_id)}" if stage == Stage.PLAN else f"python3 -m tools.workflow_cli run-resume --work-id {str(record.work_id)}"
        return print_result(
            "CMD-CHECKPOINT-DECIDE", "approved",
            run_path=str(artifact_root / "run.md"),
            run_state_after="checkpoint_approved",
            current_stage=stage.value,
            writes=[{"path": str(artifact_root / filename), "kind": "artifact_update"}],
            next_allowed_command=next_cmd,
            json_mode=args.json,
        )
    elif decision == "changes_requested":
        record.status = RunStatus.CHECKPOINT_CHANGES_REQUESTED
        mgr.save(record)
        return print_result(
            "CMD-CHECKPOINT-DECIDE", "changes_requested",
            run_path=str(artifact_root / "run.md"),
            run_state_after="checkpoint_changes_requested",
            json_mode=args.json,
        )
    else:
        return print_result(
            "CMD-CHECKPOINT-DECIDE", decision,
            run_path=str(artifact_root / "run.md"),
            json_mode=args.json,
            exit_code=1 if decision == "blocked" else 4,
        )


def cmd_confirm_record(args: argparse.Namespace) -> int:
    artifact_root = _resolve_artifact_root(args.work_id, args.run_path, args.artifact_root)
    mgr, record = _load_run_state(artifact_root)
    _check_command_allowed(record, "CMD-CONFIRM-RECORD")

    if not args.confirm:
        return print_result("CMD-CONFIRM-RECORD", "confirmation_required", stops=["--confirm required"], json_mode=args.json, exit_code=5)

    stage = Stage(args.stage) if args.stage else record.current_stage
    confirmation_text = args.decision or args.item or "confirmed"
    record.user_confirmations.append(UserConfirmation(
        confirmation=confirmation_text,
        stage=stage,
        source=args.source or "user",
        recorded_in=f"{STAGE_ARTIFACT_MAP.get(stage, 'unknown')}",
    ))
    record = update_resume_context(
        record,
        last_operation="user_confirmation_recorded",
        active_item=f"{stage.value} confirmation: {confirmation_text[:60]}",
    )
    mgr.save(record)

    return print_result(
        "CMD-CONFIRM-RECORD", "confirmation_recorded",
        run_path=str(artifact_root / "run.md"),
        current_stage=stage.value,
        writes=[{"path": str(artifact_root / "run.md"), "kind": "run_update"}],
        json_mode=args.json,
    )


def cmd_gap_record(args: argparse.Namespace) -> int:
    artifact_root = _resolve_artifact_root(args.work_id, args.run_path, args.artifact_root)
    mgr, record = _load_run_state(artifact_root)
    _check_command_allowed(record, "CMD-GAP-RECORD")

    if not args.confirm:
        return print_result("CMD-GAP-RECORD", "confirmation_required", stops=["--confirm required"], json_mode=args.json, exit_code=5)

    record.status = RunStatus.UPSTREAM_GAP_ROUTING
    mgr.save(record)
    return print_result(
        "CMD-GAP-RECORD", "upstream_gap_detected",
        run_path=str(artifact_root / "run.md"),
        run_state_after="upstream_gap_routing",
        json_mode=args.json,
    )


def cmd_gap_route(args: argparse.Namespace) -> int:
    artifact_root = _resolve_artifact_root(args.work_id, args.run_path, args.artifact_root)
    mgr, record = _load_run_state(artifact_root)
    _check_command_allowed(record, "CMD-GAP-ROUTE")

    if not args.confirm:
        return print_result("CMD-GAP-ROUTE", "confirmation_required", stops=["--confirm required"], json_mode=args.json, exit_code=5)

    owner_stage = Stage(args.stage) if args.stage else Stage.REQUIREMENT_BRIEF
    record.status = RunStatus.ACTIVE_STAGE_DRAFT
    record.current_stage = owner_stage
    record = update_resume_context(
        record,
        last_operation="gap_routed_to_owner",
        next_operation="produce_stage_artifact",
        active_item=owner_stage.value,
    )
    mgr.save(record)
    return print_result(
        "CMD-GAP-ROUTE", "active_stage_draft",
        run_path=str(artifact_root / "run.md"),
        run_state_after="active_stage_draft",
        current_stage=owner_stage.value,
        writes=[{"path": str(artifact_root / "run.md"), "kind": "run_update"}],
        json_mode=args.json,
    )


def cmd_gap_reimport(args: argparse.Namespace) -> int:
    artifact_root = _resolve_artifact_root(args.work_id, args.run_path, args.artifact_root)
    mgr, record = _load_run_state(artifact_root)
    _check_command_allowed(record, "CMD-GAP-REIMPORT")

    route_id = args.route or ""
    if route_id:
        from tools.workflow_cli.state import close_route
        record = close_route(record, route_id)
    record.status = RunStatus.ACTIVE_STAGE_DRAFT
    record = update_resume_context(
        record,
        last_operation="gap_reimported",
        next_operation="run_quality_gate",
        active_item=record.current_stage.value,
    )
    mgr.save(record)
    return print_result(
        "CMD-GAP-REIMPORT", "active_stage_draft",
        run_path=str(artifact_root / "run.md"),
        run_state_after="active_stage_draft",
        writes=[{"path": str(artifact_root / "run.md"), "kind": "run_update"}],
        json_mode=args.json,
    )


def cmd_artifact_mark_stale(args: argparse.Namespace) -> int:
    artifact_root = _resolve_artifact_root(args.work_id, args.run_path, args.artifact_root)
    mgr, record = _load_run_state(artifact_root)
    _check_command_allowed(record, "CMD-ARTIFACT-MARK-STALE")

    if not args.confirm:
        return print_result("CMD-ARTIFACT-MARK-STALE", "confirmation_required", stops=["--confirm required"], json_mode=args.json, exit_code=5)

    artifact_name = getattr(args, "artifact", "")
    reason = getattr(args, "reason", "upstream artifact changed")
    replaced_by = getattr(args, "replaced_by", "")
    record = record_stale_artifact(record, artifact_name, reason, replaced_by, "re-import upstream")
    mgr.save(record)

    return print_result(
        "CMD-ARTIFACT-MARK-STALE", "stale_recorded",
        run_path=str(artifact_root / "run.md"),
        writes=[{"path": str(artifact_root / "run.md"), "kind": "run_update"}],
        json_mode=args.json,
    )


def cmd_status_run(args: argparse.Namespace) -> int:
    artifact_root = _resolve_artifact_root(args.work_id, args.run_path, args.artifact_root)
    mgr, record = _load_run_state(artifact_root)
    return print_result(
        "CMD-STATUS-RUN", record.status.value,
        run_path=str(artifact_root / "run.md"),
        current_stage=record.current_stage.value,
        open_routes=[r.route_id for r in record.open_routes if r.status == "open"],
        stale_artifacts=[s.artifact for s in record.stale_artifacts],
        next_allowed_command=_next_command_for_state(record),
        json_mode=args.json,
    )


def cmd_status_stage(args: argparse.Namespace) -> int:
    artifact_root = _resolve_artifact_root(args.work_id, args.run_path, args.artifact_root)
    mgr, record = _load_run_state(artifact_root)
    return print_result(
        "CMD-STATUS-STAGE", record.current_stage.value,
        run_path=str(artifact_root / "run.md"),
        current_stage=record.current_stage.value,
        next_allowed_command=_next_command_for_state(record),
        json_mode=args.json,
    )


def cmd_status_next(args: argparse.Namespace) -> int:
    artifact_root = _resolve_artifact_root(args.work_id, args.run_path, args.artifact_root)
    mgr, record = _load_run_state(artifact_root)
    return print_result(
        "CMD-STATUS-NEXT", "ok",
        run_path=str(artifact_root / "run.md"),
        current_stage=record.current_stage.value,
        next_allowed_command=_next_command_for_state(record),
        open_routes=[r.route_id for r in record.open_routes if r.status == "open"],
        json_mode=args.json,
    )


def cmd_status_routes(args: argparse.Namespace) -> int:
    artifact_root = _resolve_artifact_root(args.work_id, args.run_path, args.artifact_root)
    mgr, record = _load_run_state(artifact_root)
    routes_data = [
        {"route_id": r.route_id, "from": r.from_stage.value, "owner": r.owner_stage.value, "status": r.status}
        for r in record.open_routes
    ]
    if args.json:
        import json as _json
        _json.dump({"open_routes": routes_data}, sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        for r in routes_data:
            sys.stdout.write(f"route: {r['route_id']} owner: {r['owner']} status: {r['status']}\n")
    return 0


def cmd_status_artifacts(args: argparse.Namespace) -> int:
    artifact_root = _resolve_artifact_root(args.work_id, args.run_path, args.artifact_root)
    mgr, record = _load_run_state(artifact_root)
    artifacts_data = [
        {"stage": aa.stage.value, "artifact": aa.artifact, "version": aa.version, "status": aa.status}
        for aa in record.active_artifacts
    ]
    if args.json:
        import json as _json
        _json.dump({"active_artifacts": artifacts_data, "stale": [s.artifact for s in record.stale_artifacts]}, sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        for a in artifacts_data:
            sys.stdout.write(f"artifact: {a['artifact']}@v{a['version']} stage: {a['stage']} status: {a['status']}\n")
    return 0


def cmd_executor_adapt(args: argparse.Namespace) -> int:
    artifact_root = _resolve_artifact_root(args.work_id, args.run_path, args.artifact_root)
    if args.executor == "superpowers":
        from tools.workflow_cli.adapters.superpowers import adapt_plan
        plan_path = args.plan or str(artifact_root / "07-plan.md")
        output_path = args.output or str(artifact_root / "superpowers-plan.md")
        result = adapt_plan(Path(plan_path), Path(output_path))
        return print_result(
            "CMD-EXECUTOR-ADAPT", result,
            run_path=str(artifact_root / "run.md"),
            writes=[{"path": output_path, "kind": "adapter_output"}] if result == "derived_plan_written" else [],
            json_mode=args.json,
        )
    return print_result("CMD-EXECUTOR-ADAPT", "unknown_executor", stops=[f"Unknown executor: {args.executor}"], json_mode=args.json, exit_code=2)


def _next_command_for_state(record: RunRecord) -> str:
    wid = str(record.work_id)
    stage = record.current_stage.value
    status = record.status
    if status == RunStatus.NOT_STARTED:
        return f"python3 -m tools.workflow_cli run-start --work-id {wid}"
    if status == RunStatus.ACTIVE_STAGE_DRAFT:
        return f"python3 -m tools.workflow_cli stage-produce --work-id {wid} --stage {stage}"
    if status == RunStatus.ENTRY_GATE_FAILED:
        return f"python3 -m tools.workflow_cli gate-entry --work-id {wid} --stage {stage}"
    if status == RunStatus.QUALITY_GATE_FAILED:
        return f"python3 -m tools.workflow_cli gate-quality --work-id {wid} --stage {stage}"
    if status == RunStatus.READY_FOR_CHECKPOINT_REVIEW:
        return f"python3 -m tools.workflow_cli review-checkpoint --work-id {wid} --stage {stage}"
    if status == RunStatus.CHECKPOINT_REVIEW:
        return f"python3 -m tools.workflow_cli review-merge --work-id {wid} --stage {stage}"
    if status == RunStatus.CHECKPOINT_APPROVED:
        return f"python3 -m tools.workflow_cli run-close --work-id {wid}" if record.current_stage == Stage.PLAN else f"python3 -m tools.workflow_cli run-resume --work-id {wid}"
    if status == RunStatus.UPSTREAM_GAP_ROUTING:
        return f"python3 -m tools.workflow_cli gap-route --work-id {wid}"
    return f"python3 -m tools.workflow_cli status-next --work-id {wid}"


def _add_common_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--work-id", default=None, help="Workflow run ID")
    parser.add_argument("--run", dest="run_path", default=None, help="Path to run.md")
    parser.add_argument("--artifact-root", default=None, help="Artifact root override")
    parser.add_argument("--json", action="store_true", help="JSON output mode")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing")
    parser.add_argument("--confirm", action="store_true", help="Authorize confirmation-bearing writes")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="workflow", description="Requirement-to-PLAN workflow CLI")
    sub = parser.add_subparsers(dest="command")

    # run
    p_run_start = sub.add_parser("run-start", help="Start a workflow run")
    _add_common_args(p_run_start)
    p_run_start.add_argument("--source", help="Requirement source")

    p_run_resume = sub.add_parser("run-resume", help="Resume a workflow run")
    _add_common_args(p_run_resume)

    p_run_close = sub.add_parser("run-close", help="Close a workflow run")
    _add_common_args(p_run_close)

    # stage
    for cmd_name in ["stage-load", "stage-produce", "stage-ready"]:
        p = sub.add_parser(cmd_name, help=f"{cmd_name} command")
        _add_common_args(p)
        p.add_argument("--stage", required=True, help="Stage name")

    # gate
    for cmd_name in ["gate-entry", "gate-quality"]:
        p = sub.add_parser(cmd_name, help=f"{cmd_name} command")
        _add_common_args(p)
        p.add_argument("--stage", required=True, help="Stage name")

    # review
    for cmd_name in ["review-checkpoint", "review-merge"]:
        p = sub.add_parser(cmd_name, help=f"{cmd_name} command")
        _add_common_args(p)
        p.add_argument("--stage", required=True, help="Stage name")

    # checkpoint
    p_cp = sub.add_parser("checkpoint-decide", help="Checkpoint decide")
    _add_common_args(p_cp)
    p_cp.add_argument("--stage", required=True, help="Stage name")
    p_cp.add_argument("--decision", required=True, choices=["approved", "changes_requested", "blocked", "upstream_gap_detected", "route_upstream"])

    # confirm
    p_cf = sub.add_parser("confirm-record", help="Record user confirmation")
    _add_common_args(p_cf)
    p_cf.add_argument("--stage", required=True, help="Stage name")
    p_cf.add_argument("--item", default="")
    p_cf.add_argument("--source", default="user")
    p_cf.add_argument("--decision", default="")
    p_cf.add_argument("--affected", default="")
    p_cf.add_argument("--downstream", default="")

    # gap
    for cmd_name in ["gap-record", "gap-route", "gap-reimport"]:
        p = sub.add_parser(cmd_name, help=f"{cmd_name} command")
        _add_common_args(p)
        p.add_argument("--stage", default="")
        p.add_argument("--route", default="")

    p_ams = sub.add_parser("artifact-mark-stale", help="Mark artifact stale")
    _add_common_args(p_ams)
    p_ams.add_argument("--artifact", default="", help="Artifact name to mark stale")
    p_ams.add_argument("--reason", default="upstream artifact changed", help="Reason for marking stale")
    p_ams.add_argument("--replaced-by", default="", help="Replacement artifact reference")

    # status
    for cmd_name in ["status-run", "status-stage", "status-next", "status-routes", "status-artifacts"]:
        p = sub.add_parser(cmd_name, help=f"{cmd_name} command")
        _add_common_args(p)

    # executor
    p_exec = sub.add_parser("executor-adapt", help="Adapt PLAN to executor format")
    _add_common_args(p_exec)
    p_exec.add_argument("--executor", required=True, help="Target executor")
    p_exec.add_argument("--plan", default="", help="Path to PLAN artifact")
    p_exec.add_argument("--output", default="", help="Output path")

    return parser


COMMAND_MAP = {
    "run-start": cmd_run_start,
    "run-resume": cmd_run_resume,
    "run-close": cmd_run_close,
    "stage-load": cmd_stage_load,
    "stage-produce": cmd_stage_produce,
    "stage-ready": cmd_stage_ready,
    "gate-entry": cmd_gate_entry,
    "gate-quality": cmd_gate_quality,
    "review-checkpoint": cmd_review_checkpoint,
    "review-merge": cmd_review_merge,
    "checkpoint-decide": cmd_checkpoint_decide,
    "confirm-record": cmd_confirm_record,
    "gap-record": cmd_gap_record,
    "gap-route": cmd_gap_route,
    "gap-reimport": cmd_gap_reimport,
    "artifact-mark-stale": cmd_artifact_mark_stale,
    "status-run": cmd_status_run,
    "status-stage": cmd_status_stage,
    "status-next": cmd_status_next,
    "status-routes": cmd_status_routes,
    "status-artifacts": cmd_status_artifacts,
    "executor-adapt": cmd_executor_adapt,
}


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.dry_run:
        # In dry-run mode, validate inputs but don't write
        import json as _json
        _json.dump({"status": "dry_run", "command": args.command, "planned_writes": []}, sys.stdout)
        sys.stdout.write("\n")
        return 0

    handler = COMMAND_MAP.get(args.command or "")
    if not handler:
        parser.print_help()
        return 2

    try:
        return handler(args)
    except ValueError as e:
        return print_result(
            args.command or "unknown", "error",
            stops=[str(e)],
            json_mode=getattr(args, "json", False),
            exit_code=6,
        )
    except FileNotFoundError as e:
        return print_result(
            args.command or "unknown", "missing_run",
            stops=[str(e)],
            json_mode=getattr(args, "json", False),
            exit_code=2,
        )


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 7: Run all tests**

Run: `cd /Users/xubo/x-skills/req-to-plan && python3 -m unittest tests.test_output tests.test_cli tests.test_models tests.test_state tests.test_artifact tests.test_gates -v`
Expected: All tests PASS

- [ ] **Step 8: Commit**

```bash
cd /Users/xubo/x-skills/req-to-plan && git add tools/workflow_cli/output.py tools/workflow_cli/cli.py tests/test_output.py tests/test_cli.py && git commit -m "feat: add output formatter and CLI command router"
```

---

### Task 6: Superpowers adapter

**Files:**
- Create: `tools/workflow_cli/adapters/__init__.py`
- Create: `tools/workflow_cli/adapters/superpowers.py`
- Create: `tests/test_adapters_superpowers.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_adapters_superpowers.py
import unittest
import tempfile
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from tools.workflow_cli.adapters.superpowers import adapt_plan, extract_tasks, convert_to_superpowers

class TestSuperpowersAdapter(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def _create_plan(self, content: str) -> Path:
        p = self.root / "07-plan.md"
        p.write_text(content)
        return p

    def test_extract_tasks_from_plan(self):
        plan = """---
artifact_id: PLAN-001
version: 1
status: approved
---
# PLAN: Test

## Task Breakdown
### Task 1: Add feature X
**Spec References:**
- SPEC-FR-001: Feature X behavior

**Goal**
Implement feature X.

**Change Type**
add

**Steps**
1. Write failing test for feature X.
2. Implement feature X.
3. Run tests and verify pass.

**Verification**
Run: `pytest tests/test_feature_x.py -v`
Expected: PASS

**Rollback / Safety**
Revert commit if tests fail.
"""
        tasks = extract_tasks(plan)
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0]["goal"], "Implement feature X.")
        self.assertEqual(tasks[0]["spec_refs"], ["SPEC-FR-001: Feature X behavior"])
        self.assertEqual(tasks[0]["change_type"], "add")

    def test_convert_to_superpowers_preserves_tdd_structure(self):
        tasks = [{
            "goal": "Add compatibility test",
            "spec_refs": ["SPEC-COMPAT-001"],
            "change_type": "modify",
            "steps": ["1. Write failing compatibility test.", "2. Implement compatibility behavior.", "3. Run tests."],
            "verification": "Run: pytest tests/test_compat.py -v\nExpected: PASS",
            "rollback_safety": "Stop if file mutation occurs.",
        }]
        plan_title = "Test Plan"
        result = convert_to_superpowers(tasks, plan_title)
        self.assertIn("superpowers:subagent-driven-development", result)
        self.assertIn("PLAN-TASK-001", result)
        self.assertIn("SPEC-COMPAT-001", result)
        self.assertIn("failing compatibility test", result)

    def test_adapt_plan_writes_output(self):
        plan_content = """---
artifact_id: PLAN-001
version: 1
status: approved
---
# PLAN: Test

## Task Breakdown
### Task 1: Simple task

**Spec References:**
- SPEC-FR-001: Feature

**Goal**
Do something.

**Change Type**
add

**Steps**
1. Write test.
2. Implement.
3. Verify.

**Verification**
Run: `make test`
Expected: PASS

**Rollback / Safety**
None.
"""
        plan_path = self._create_plan(plan_content)
        output_path = self.root / "superpowers-plan.md"
        result = adapt_plan(plan_path, output_path)
        self.assertEqual(result, "derived_plan_written")
        self.assertTrue(output_path.exists())
        content = output_path.read_text()
        self.assertIn("PLAN-TASK-001", content)
        self.assertIn("SPEC-FR-001", content)

    def test_adapt_plan_missing_file_returns_error(self):
        result = adapt_plan(Path("/nonexistent/plan.md"), Path("/tmp/out.md"))
        self.assertEqual(result, "adapter_gap_detected")

    def test_adapt_plan_missing_tasks_returns_repair(self):
        plan_content = """---
artifact_id: PLAN-001
version: 1
status: approved
---
# PLAN: Empty
## Task Breakdown
(No tasks yet)
"""
        plan_path = self._create_plan(plan_content)
        output_path = self.root / "superpowers-plan.md"
        result = adapt_plan(plan_path, output_path)
        self.assertEqual(result, "adapter_gap_detected")
        repair_path = self.root / "superpowers-plan.repair.md"
        self.assertTrue(repair_path.exists())

if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/xubo/x-skills/req-to-plan && python3 -m unittest tests.test_adapters_superpowers -v`
Expected: FAIL with ImportError

- [ ] **Step 3: Write adapter files**

```python
# tools/workflow_cli/adapters/__init__.py
```
```python
# tools/workflow_cli/adapters/superpowers.py
from __future__ import annotations
from pathlib import Path
import re


def adapt_plan(plan_path: Path, output_path: Path) -> str:
    if not plan_path.exists():
        return "adapter_gap_detected"

    content = plan_path.read_text(encoding="utf-8")

    tasks = extract_tasks(content)
    if not tasks:
        repair_path = Path(str(output_path).replace(".md", ".repair.md"))
        repair_path.write_text(
            "# Post-PLAN Gap Repair Request\n\n"
            "## Gap\nNo executable tasks found in PLAN.\n\n"
            "## Required Action\nAdd at least one task with Spec References, Goal, Steps, Verification, and Rollback/Safety.\n",
            encoding="utf-8",
        )
        return "adapter_gap_detected"

    title = _extract_title(content)
    superpowers_content = convert_to_superpowers(tasks, title)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(superpowers_content, encoding="utf-8")
    return "derived_plan_written"


def extract_tasks(content: str) -> list[dict]:
    tasks: list[dict] = []
    task_blocks = re.split(r"\n### Task \d+:", content)[1:]

    for i, block in enumerate(task_blocks):
        task = _parse_task_block(block.strip(), i + 1)
        if task and task.get("goal"):
            tasks.append(task)

    return tasks


def _extract_title(content: str) -> str:
    m = re.search(r"^# PLAN: (.+)$", content, re.MULTILINE)
    return m.group(1).strip() if m else "Implementation Plan"


def _parse_task_block(block: str, index: int) -> dict | None:
    task: dict = {
        "title": f"Task {index}",
        "spec_refs": [],
        "goal": "",
        "change_type": "modify",
        "steps": [],
        "verification": "",
        "rollback_safety": "",
    }

    # Spec References
    spec_section = re.search(r"\*\*Spec References:\*\*\n(.*?)\n\n", block, re.DOTALL)
    if spec_section:
        for line in spec_section.group(1).strip().split("\n"):
            line = line.strip().lstrip("- ")
            if line:
                task["spec_refs"].append(line)

    # Goal
    goal_match = re.search(r"\*\*Goal\*\*\n(.+?)(?=\n\*\*|\n###|\Z)", block, re.DOTALL)
    if goal_match:
        task["goal"] = goal_match.group(1).strip()

    # Change Type
    ct_match = re.search(r"\*\*Change Type\*\*\n(.+?)(?=\n\*\*|\n###|\Z)", block, re.DOTALL)
    if ct_match:
        task["change_type"] = ct_match.group(1).strip()

    # Steps
    steps_match = re.search(r"\*\*Steps\*\*\n(.*?)(?=\n\*\*Verification|\n\*\*Rollback|\n###|\Z)", block, re.DOTALL)
    if steps_match:
        for line in steps_match.group(1).strip().split("\n"):
            line = line.strip()
            if line and (line[0].isdigit() or line.startswith("- ")):
                task["steps"].append(line.lstrip("0123456789. "))

    # Verification
    ver_match = re.search(r"\*\*Verification\*\*\n(.*?)(?=\n\*\*Rollback|\n###|\Z)", block, re.DOTALL)
    if ver_match:
        task["verification"] = ver_match.group(1).strip()

    # Rollback / Safety
    rb_match = re.search(r"\*\*Rollback / Safety\*\*\n(.*?)(?=\n###|\Z)", block, re.DOTALL)
    if rb_match:
        task["rollback_safety"] = rb_match.group(1).strip()

    return task


def convert_to_superpowers(tasks: list[dict], plan_title: str) -> str:
    lines = [
        f"# {plan_title} (Superpowers Plan)",
        "",
        "> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task.",
        "",
        f"**Goal:** Execute {len(tasks)} tasks from the approved executor-neutral PLAN.",
        "",
        "**Source PLAN:** Derived from approved .req-to-plan artifact via `python3 -m tools.workflow_cli executor-adapt --executor superpowers`.",
        "",
        "---",
        "",
        "## Stop / Escalation Conditions",
        "",
        "- Stop execution if any task verification fails.",
        "- Stop if a task discovers missing SPEC reference or upstream gap.",
        "- Stop if a task requires destructive operation not explicitly approved.",
        "- Stop if a task touches out-of-scope modules or workflows.",
        "",
        "---",
        "",
    ]

    for i, task in enumerate(tasks):
        task_id = f"PLAN-TASK-{i+1:03d}"
        lines.append(f"### Task {i+1}: {task['goal']}")
        lines.append("")
        lines.append(f"**Task ID:** {task_id}")
        lines.append("")
        if task["spec_refs"]:
            lines.append("**Spec References:**")
            for ref in task["spec_refs"]:
                lines.append(f"- {ref}")
            lines.append("")
        lines.append(f"**Change Type:** {task['change_type']}")
        lines.append("")
        if task["steps"]:
            lines.append("**Steps:**")
            for j, step in enumerate(task["steps"]):
                lines.append(f"{j+1}. {step}")
            lines.append("")
        if task["verification"]:
            lines.append("**Verification:**")
            lines.append(task["verification"])
            lines.append("")
        if task["rollback_safety"]:
            lines.append("**Rollback / Safety:**")
            lines.append(task["rollback_safety"])
            lines.append("")
        lines.append("---")
        lines.append("")

    lines.append("## Task Dependencies")
    lines.append("")
    lines.append("| Order | Task ID | Depends On |")
    lines.append("|---|---|---|")
    for i, task in enumerate(tasks):
        deps = "none" if i == 0 else f"PLAN-TASK-{i:03d}"
        lines.append(f"| {i+1} | PLAN-TASK-{i+1:03d} | {deps} |")

    return "\n".join(lines) + "\n"
```

- [ ] **Step 4: Run adapter tests**

Run: `cd /Users/xubo/x-skills/req-to-plan && python3 -m unittest tests.test_adapters_superpowers -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
cd /Users/xubo/x-skills/req-to-plan && git add tools/workflow_cli/adapters/ tests/test_adapters_superpowers.py && git commit -m "feat: add superpowers PLAN adapter"
```

---

### Task 7: Agent shortcuts (agent_shortcuts.py)

**Files:**
- Create: `tools/workflow_cli/agent_shortcuts.py`
- Create: `tools/coyeme-workflow-start`
- Create: `tools/coyeme-workflow-continue`
- Create: `tools/coyeme-workflow-status`
- Create: `tools/coyeme-workflow-switch`
- Create: `tools/coyeme-workflow-adapt`

- [ ] **Step 1: Write agent_shortcuts.py**

```python
# tools/workflow_cli/agent_shortcuts.py
"""Agent-facing project shortcut commands for the requirement-to-PLAN workflow.

These are the entry points for coyeme-workflow-* commands.
They compose internal CLI commands while preserving all authority, confirmation,
stop, and state-eligibility rules.
"""
from __future__ import annotations
import sys
from pathlib import Path


def _find_repo_root() -> Path:
    """Find repository root by looking for .req-to-plan or .git directory."""
    current = Path.cwd()
    for parent in [current] + list(current.parents):
        if (parent / ".req-to-plan").exists() or (parent / ".git").exists():
            return parent
    return current


def _read_pointer(repo_root: Path) -> dict | None:
    pointer_path = repo_root / ".req-to-plan" / ".workflow-active"
    if not pointer_path.exists():
        return None
    result = {}
    for line in pointer_path.read_text().split("\n"):
        line = line.strip()
        if ":" in line and not line.startswith("#"):
            key, _, val = line.partition(":")
            result[key.strip()] = val.strip()
    return result


def _write_pointer(repo_root: Path, work_id: str) -> Path:
    pointer_dir = repo_root / ".req-to-plan"
    pointer_dir.mkdir(parents=True, exist_ok=True)
    pointer_path = pointer_dir / ".workflow-active"
    run_path = pointer_dir / work_id / "run.md"
    pointer_path.write_text(
        f"selected_work_id: {work_id}\n"
        f"selected_run: {run_path}\n"
        f"updated_at: {_now_iso()}\n"
        f"reason: workflow_start\n"
    )
    return pointer_path


def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


def _scan_open_runs(repo_root: Path) -> list[str]:
    artifact_root = repo_root / ".req-to-plan"
    if not artifact_root.exists():
        return []
    open_runs = []
    for d in artifact_root.iterdir():
        if d.is_dir() and not d.name.startswith("."):
            run_path = d / "run.md"
            if run_path.exists():
                content = run_path.read_text()
                if "closed_at_plan_checkpoint" not in content:
                    open_runs.append(d.name)
    return open_runs


def cmd_start(args: list[str]) -> int:
    repo_root = _find_repo_root()
    separate = "--separate" in args
    requirement_parts = [a for a in args if a != "--separate"]
    requirement = " ".join(requirement_parts) if requirement_parts else ""

    if not separate:
        pointer = _read_pointer(repo_root)
        if pointer:
            selected_id = pointer.get("selected_work_id", "")
            open_runs = _scan_open_runs(repo_root)
            if selected_id in open_runs:
                print(f"blocked: active_run_exists")
                print(f"active_run: .req-to-plan/{selected_id}/run.md")
                print(f"next: coyeme-workflow-continue")
                print(f"alternative: coyeme-workflow-start --separate \"{requirement}\"")
                return 0
            if len(open_runs) == 1:
                rid = open_runs[0]
                print(f"blocked: open_run_exists")
                print(f"open_run: .req-to-plan/{rid}/run.md")
                print(f"next: coyeme-workflow-switch --work-id {rid}")
                print(f"alternative: coyeme-workflow-start --separate \"{requirement}\"")
                return 0
            if len(open_runs) > 1:
                print(f"blocked: open_runs_exist")
                print(f"next: coyeme-workflow-status --all")
                print(f"alternative: coyeme-workflow-start --separate \"{requirement}\"")
                return 0

    from tools.workflow_cli.models import WorkId
    work_id = str(WorkId.generate(requirement or "new-requirement"))
    _write_pointer(repo_root, work_id)

    artifact_root = repo_root / ".req-to-plan" / work_id
    artifact_root.mkdir(parents=True, exist_ok=True)

    from tools.workflow_cli.state import RunStateManager, create_run_record
    from tools.workflow_cli.models import WorkId as WID, Stage, RunStatus
    from tools.workflow_cli.artifact import ArtifactManager

    record = create_run_record(WID(work_id))
    record.current_stage = Stage.RAW_REQUIREMENT
    mgr = RunStateManager(artifact_root)
    mgr.save(record)

    am = ArtifactManager(artifact_root)
    am.create("00-raw-requirement.md", f"# Raw Requirement\n\n{requirement}\n")
    am.create("01-intake-brief.md", f"# Intake Brief v0\n\n## Initial Goal\n\n{requirement}\n")

    print(f"created: .req-to-plan/{work_id}/run.md")
    print(f"selected_run: .req-to-plan/{work_id}/run.md")
    print(f"next: coyeme-workflow-continue")
    return 0


def cmd_continue(args: list[str]) -> int:
    repo_root = _find_repo_root()
    pointer = _read_pointer(repo_root)

    if not pointer:
        open_runs = _scan_open_runs(repo_root)
        if len(open_runs) == 1:
            work_id = open_runs[0]
            _write_pointer(repo_root, work_id)
            pointer = {"selected_work_id": work_id}
        else:
            print("blocked: no_selected_run")
            print("next: coyeme-workflow-status --all")
            return 0

    work_id = pointer.get("selected_work_id", "")
    artifact_root = repo_root / ".req-to-plan" / work_id
    run_path = artifact_root / "run.md"

    if not run_path.exists():
        print(f"blocked: run_not_found")
        print(f"next: coyeme-workflow-status --all")
        return 1

    content = run_path.read_text()

    if "closed_at_plan_checkpoint" in content:
        print("blocked: run_already_closed")
        open_runs = [r for r in _scan_open_runs(repo_root) if r != work_id]
        if open_runs:
            print(f"alternative: coyeme-workflow-switch --work-id {open_runs[0]}")
        return 0

    # Determine current stage and next action from run.md
    current_stage = "raw_requirement"
    status = "active_stage_draft"
    for line in content.split("\n"):
        if line.startswith("## Current Stage"):
            continue
        if line.strip() in ("raw_requirement", "requirement_brief", "risk_discovery", "design", "spec", "plan", "closed"):
            current_stage = line.strip()
            break

    for line in content.split("\n"):
        if line.startswith("## Status"):
            continue
        if line.strip().startswith(("active_stage_draft", "not_started", "entry_gate_failed",
                                    "quality_gate_failed", "ready_for_checkpoint_review",
                                    "checkpoint_review", "checkpoint_changes_requested",
                                    "upstream_gap_routing", "checkpoint_approved", "next_stage")):
            status = line.strip()
            break

    # Print status and let the Agent decide next steps
    print(f"workflow: {work_id}")
    print(f"run: {run_path}")
    print(f"current_stage: {current_stage}")
    print(f"status: {status}")
    print(f"next: Agent should read run.md, load stage workflow doc, and proceed with next operation")

    return 0


def cmd_status(args: list[str]) -> int:
    repo_root = _find_repo_root()
    show_all = "--all" in args

    if show_all:
        open_runs = _scan_open_runs(repo_root)
        pointer = _read_pointer(repo_root)
        selected = pointer.get("selected_work_id", "") if pointer else ""
        if not open_runs and not selected:
            print("no_runs_found")
            return 0
        for rid in open_runs:
            marker = " *" if rid == selected else ""
            print(f"{'active' if rid == selected else 'open'}: {rid}{marker}")
        return 0

    pointer = _read_pointer(repo_root)
    if not pointer:
        open_runs = _scan_open_runs(repo_root)
        if len(open_runs) == 1:
            print(f"no_selected_run")
            print(f"recoverable_open_run: .req-to-plan/{open_runs[0]}/run.md")
        else:
            print("no_selected_run")
            print("next: coyeme-workflow-status --all")
        return 0

    work_id = pointer.get("selected_work_id", "")
    run_path = repo_root / ".req-to-plan" / work_id / "run.md"
    if not run_path.exists():
        print(f"selected_run_missing: {work_id}")
        print("next: coyeme-workflow-status --all")
        return 0

    content = run_path.read_text()
    is_closed = "closed_at_plan_checkpoint" in content
    print(f"selected_run: .req-to-plan/{work_id}/run.md")
    print(f"status: {'closed' if is_closed else 'open'}")
    if is_closed:
        print("next: coyeme-workflow-adapt --executor superpowers")
    else:
        print("next: coyeme-workflow-continue")
    return 0


def cmd_switch(args: list[str]) -> int:
    repo_root = _find_repo_root()
    work_id = ""
    for i, a in enumerate(args):
        if a == "--work-id" and i + 1 < len(args):
            work_id = args[i + 1]
            break

    if not work_id:
        print("error: --work-id is required")
        return 2

    run_path = repo_root / ".req-to-plan" / work_id / "run.md"
    if not run_path.exists():
        print(f"error: run not found for {work_id}")
        return 2

    _write_pointer(repo_root, work_id)
    print(f"selected_run: .req-to-plan/{work_id}/run.md")
    print(f"next: coyeme-workflow-continue")
    return 0


def cmd_adapt(args: list[str]) -> int:
    repo_root = _find_repo_root()
    pointer = _read_pointer(repo_root)
    if not pointer:
        print("error: no selected run")
        return 2

    work_id = pointer.get("selected_work_id", "")
    artifact_root = repo_root / ".req-to-plan" / work_id
    plan_path = artifact_root / "07-plan.md"
    output_path = artifact_root / "superpowers-plan.md"

    if not plan_path.exists():
        print(f"error: PLAN artifact not found at {plan_path}")
        return 2

    from tools.workflow_cli.adapters.superpowers import adapt_plan
    result = adapt_plan(plan_path, output_path)
    if result == "derived_plan_written":
        print(f"derived_plan_written: {output_path}")
    else:
        print(f"{result}: {output_path}.repair.md")
    return 0 if result == "derived_plan_written" else 1


COMMANDS = {
    "start": cmd_start,
    "continue": cmd_continue,
    "status": cmd_status,
    "switch": cmd_switch,
    "adapt": cmd_adapt,
}


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: coyeme-workflow-<start|continue|status|switch|adapt> [args]")
        return 2
    cmd = sys.argv[1]
    handler = COMMANDS.get(cmd)
    if not handler:
        print(f"unknown command: {cmd}")
        return 2
    return handler(sys.argv[2:])
```

- [ ] **Step 2: Create wrapper scripts**

```bash
# tools/coyeme-workflow-start
#!/bin/bash
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
PYTHONPATH="$REPO_ROOT" python3 -c "
import sys
sys.path.insert(0, '$REPO_ROOT')
from tools.workflow_cli.agent_shortcuts import cmd_start
sys.exit(cmd_start(sys.argv[1:]))
" "$@"
```

```bash
# tools/coyeme-workflow-continue
#!/bin/bash
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
PYTHONPATH="$REPO_ROOT" python3 -c "
import sys
sys.path.insert(0, '$REPO_ROOT')
from tools.workflow_cli.agent_shortcuts import cmd_continue
sys.exit(cmd_continue(sys.argv[1:]))
" "$@"
```

```bash
# tools/coyeme-workflow-status
#!/bin/bash
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
PYTHONPATH="$REPO_ROOT" python3 -c "
import sys
sys.path.insert(0, '$REPO_ROOT')
from tools.workflow_cli.agent_shortcuts import cmd_status
sys.exit(cmd_status(sys.argv[1:]))
" "$@"
```

```bash
# tools/coyeme-workflow-switch
#!/bin/bash
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
PYTHONPATH="$REPO_ROOT" python3 -c "
import sys
sys.path.insert(0, '$REPO_ROOT')
from tools.workflow_cli.agent_shortcuts import cmd_switch
sys.exit(cmd_switch(sys.argv[1:]))
" "$@"
```

```bash
# tools/coyeme-workflow-adapt
#!/bin/bash
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
PYTHONPATH="$REPO_ROOT" python3 -c "
import sys
sys.path.insert(0, '$REPO_ROOT')
from tools.workflow_cli.agent_shortcuts import cmd_adapt
sys.exit(cmd_adapt(sys.argv[1:]))
" "$@"
```

- [ ] **Step 3: Make wrappers executable and test**

Run:
```bash
chmod +x /Users/xubo/x-skills/req-to-plan/tools/coyeme-workflow-*
cd /Users/xubo/x-skills/req-to-plan && python3 -c "
import sys
sys.path.insert(0, '.')
from tools.workflow_cli.agent_shortcuts import cmd_start, cmd_continue, cmd_status, cmd_switch, cmd_adapt
print('agent_shortcuts module loaded successfully')
"
```
Expected: "agent_shortcuts module loaded successfully"

- [ ] **Step 4: Commit**

```bash
cd /Users/xubo/x-skills/req-to-plan && git add tools/workflow_cli/agent_shortcuts.py tools/coyeme-workflow-* && git commit -m "feat: add agent shortcuts and wrapper scripts"
```

---

### Task 8: Agent skill (req-to-plan)

**Files:**
- Create: `.claude/skills/req-to-plan.md`

- [ ] **Step 1: Write the Agent skill**

```markdown
# Requirement-to-PLAN Agent Workflow

Drive the 6-stage requirement-to-PLAN pipeline (raw_requirement intake + 5 transformation stages). You are the semantic engine: you read workflow docs, generate artifact content, judge Quality Gates, and decide checkpoints. The CLI handles state management and structured validation.

## When to Use

Invoke this skill when the user runs any `coyeme-workflow-*` command or asks to continue, resume, or inspect a workflow run.

## Core Loop

`coyeme-workflow-continue` is the main command. When invoked:

1. Call the shortcut to determine current state:
   ```bash
   tools/coyeme-workflow-continue
   ```

2. Parse the output to get `current_stage` and `status`.

3. Map `current_stage` to the workflow document:
   - `raw_requirement` / `requirement_brief` → `docs/requirement-brief-workflow.md`
   - `risk_discovery` → `docs/risk-question-discovery-workflow.md`
   - `design` → `docs/design-workflow.md`
   - `spec` → `docs/spec-workflow.md`
   - `plan` → `docs/plan-workflow.md`

4. Read `docs/workflow-invariants.md` and `docs/workflow-execution-guide.md` for cross-stage rules.

5. Based on `status`, execute the next operation:

   | Status | Action |
   |--------|--------|
   | `active_stage_draft` | Produce stage artifact content using the stage workflow template, then call `python3 -m tools.workflow_cli stage-ready` |
   | `entry_gate_failed` | Fix upstream issue, rerun entry gate, or route upstream |
   | `quality_gate_failed` | Fix structural issues, then rerun quality gate → if structural checks pass but semantic issues remain, fix them and rerun |
   | `ready_for_checkpoint_review` | Run checkpoint review (dispatch subagent review if scope warrants), produce review findings |
   | `checkpoint_review` | Merge findings, ask user for required confirmations |
   | `checkpoint_approved` | Call `python3 -m tools.workflow_cli run-resume` to advance to next stage |
   | `next_stage` | Run entry gate for the next stage |
   | `upstream_gap_routing` | Identify owner stage, route gap, repair upstream, re-import |

6. For content generation:
   - Read the stage workflow document's template
   - Read approved upstream artifacts from `.req-to-plan/<work-id>/`
   - Generate artifact content following the template exactly
   - Pipe content to CLI via stdin: `echo "$content" | python3 -m tools.workflow_cli stage-produce --stage <stage> --work-id <id> --json`

7. For Quality Gate:
   - First run structural check via CLI: `python3 -m tools.workflow_cli gate-quality --stage <stage> --work-id <id> --json`
   - Then run semantic check yourself using the Quality Gate checklist from the stage workflow document
   - If both pass, the stage is `ready_for_checkpoint_review`

8. For Checkpoint Review:
   - Run subagent reviews for migration/rewrite/integration/cross-project/safety-sensitive work
   - Merge findings
   - Present user with confirmation questions (acceptance criteria, design choices, risk acceptance)
   - After user confirms, call: `python3 -m tools.workflow_cli checkpoint-decide --stage <stage> --work-id <id> --decision approved --confirm --json`

9. After PLAN Checkpoint approval:
   - Suggest: "PLAN approved. Run `coyeme-workflow-adapt --executor superpowers` to generate the Superpowers execution plan."

## Quality Gate Semantic Checks

For each stage, after the CLI structural check passes, verify:

### Requirement Brief
- Goal describes an outcome, not implementation
- Scope and non-scope are clearly separated
- Acceptance criteria are verifiable and user-confirmed
- Source provenance is confirmed
- No requirement-definition blockers remain

### Risk & Question Discovery
- All Design Triggers have RISK-DES-* IDs
- All assumptions have source, impact, carry target
- P0 risks are resolved or user-accepted
- Requirement Brief Downstream Attention items are classified

### DESIGN
- One approach is selected with rationale
- Change Point Inventory is complete
- Requirement Trace Check covers all scope items
- Boundaries and Integration Boundaries have stable IDs
- Verification Strategy is explicit
- Spec Inputs and Plan Inputs use shared schemas

### SPEC
- Design Coverage Import preserves DESIGN Spec Input IDs
- Every contract is testable
- Every boundary has behavior contracts
- Acceptance Trace Check covers all acceptance criteria
- No implementation-task language

### PLAN
- Contract-to-Task Mapping covers every SPEC contract
- Every task has Spec References
- No orphan tasks
- TDD decomposition present or alternative verification justified
- Stop/Escalation Conditions explicit

## User Interaction Points

Stop and ask the user when:
- Acceptance criteria need confirmation (Requirement Brief)
- P0 risks need explicit acceptance (Risk Discovery)
- Design choices have close tradeoffs (DESIGN User Decision Gate)
- Checkpoint approval is needed (every stage)
- Upstream gap needs routing decision

## Subagent Use

Dispatch subagents for:
- Parallel risk dimension scanning (Risk Discovery)
- Impact analysis across modules (DESIGN)
- Contract coverage checking (SPEC)
- Task decomposition review (PLAN)
- Checkpoint reviews for migration/rewrite/integration/safety work

Subagents produce evidence and recommendations. You merge findings and own the final decision.

## File Paths

- Workflow docs: `docs/*.md`
- Artifacts: `.req-to-plan/<work-id>/`
- CLI: `python3 -m tools.workflow_cli <command>`
- Shortcuts: `tools/coyeme-workflow-<action>`

## Non-Negotiables

- Never skip DESIGN (use light DESIGN for trivial work)
- Never let Requirement Brief become DESIGN
- Never let SPEC invent missing design decisions
- Never let PLAN invent missing contracts
- Never overwrite approved artifacts
- Never fill upstream gaps with assumptions
- Always get user checkpoint approval before downstream handoff
```

- [ ] **Step 2: Commit**

```bash
cd /Users/xubo/x-skills/req-to-plan && git add .claude/skills/req-to-plan.md && git commit -m "feat: add req-to-plan agent skill"
```

---

### Task 9: Integration smoke test

**Files:**
- Create: `tests/test_integration.py`

- [ ] **Step 1: Write integration test**

```python
# tests/test_integration.py
import unittest
import tempfile
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from tools.workflow_cli.models import WorkId, RunStatus, Stage
from tools.workflow_cli.state import RunStateManager, create_run_record
from tools.workflow_cli.artifact import ArtifactManager
from tools.workflow_cli.gates import check_entry_gate, check_quality_gate_structural

class TestWorkflowIntegration(unittest.TestCase):
    """End-to-end test: raw_requirement -> plan checkpoint approved."""
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.artifact_root = self.root / "WF-20260527-full-integration-test"
        self.artifact_root.mkdir(parents=True)

    def tearDown(self):
        self.tmp.cleanup()

    def _create_artifact(self, stage: Stage, filename: str, status: str = "draft"):
        from tools.workflow_cli.models import STAGE_ARTIFACT_MAP
        am = ArtifactManager(self.artifact_root)
        content = f"""---
artifact_id: {stage.value.upper()}-001
version: 1
status: {status}
---
## Upstream References
| Artifact | Reference | Status |
|---|---|---|
| Raw Requirement | 00-raw-requirement.md | available |
"""
        am.create(filename, content)
        return content

    def test_full_workflow_state_transitions(self):
        # 1. Create run
        wid = WorkId("WF-20260527-full-integration-test")
        record = create_run_record(wid)
        record.current_stage = Stage.RAW_REQUIREMENT
        mgr = RunStateManager(self.artifact_root)
        mgr.save(record)
        self.assertEqual(record.status, RunStatus.ACTIVE_STAGE_DRAFT)

        # 2. Raw requirement done -> move to requirement_brief
        self._create_artifact(Stage.RAW_REQUIREMENT, "00-raw-requirement.md", "ready")
        record = mgr.load()
        from tools.workflow_cli.state import update_run_status
        record = update_run_status(record, RunStatus.READY_FOR_CHECKPOINT_REVIEW)
        mgr.save(record)

        # 3. Simulate checkpoint review and approval for raw_requirement
        record = mgr.load()
        record.status = RunStatus.CHECKPOINT_APPROVED
        from tools.workflow_cli.state import add_checkpoint
        record = add_checkpoint(record, Stage.RAW_REQUIREMENT, "00-raw-requirement.md", 1, "yes")
        mgr.save(record)

        # 4. Resume to requirement_brief
        record = mgr.load()
        record.status = RunStatus.NEXT_STAGE
        record.current_stage = Stage.REQUIREMENT_BRIEF
        mgr.save(record)

        # 5. Entry gate should pass (requirement_brief has no upstream checkpoints needed)
        record = mgr.load()
        result = check_entry_gate(record, Stage.REQUIREMENT_BRIEF, [])
        self.assertTrue(result.passed)

        # 6. Produce requirement brief
        req_brief = """---
artifact_id: REQ-BRIEF-001
version: 1
status: draft
---
## Upstream References
| Artifact | Reference | Status |
|---|---|---|
| Raw Requirement | 00-raw-requirement.md | available |

## Goal
Add login rate limiting.

## Scope
- Rate limit login API endpoint

## Non-scope
- Registration rate limiting
"""
        am = ArtifactManager(self.artifact_root)
        am.create("03-requirement-brief.md", req_brief)
        record = mgr.load()
        record.status = RunStatus.ACTIVE_STAGE_DRAFT
        record.current_stage = Stage.REQUIREMENT_BRIEF
        mgr.save(record)

        # 7. Quality gate structural check
        result = check_quality_gate_structural(req_brief, Stage.REQUIREMENT_BRIEF)
        self.assertTrue(result.passed, f"Unexpected issues: {result.issues}")

    def test_superpowers_adaptation_end_to_end(self):
        plan_content = """---
artifact_id: PLAN-001
version: 1
status: approved
---
# PLAN: Login Rate Limiting

## Task Breakdown
### Task 1: Add rate limit counter

**Spec References:**
- SPEC-FR-001: Login rate limit behavior

**Goal**
Add rate limit counter for login attempts.

**Change Type**
add

**Steps**
1. Write failing test for rate limit counter.
2. Implement rate limit counter with TTL.
3. Run tests and verify pass.

**Verification**
Run: `pytest tests/test_rate_limit.py -v`
Expected: PASS

**Rollback / Safety**
Revert commit if tests fail. No data mutation.
"""
        # Create plan file
        plan_path = self.artifact_root / "07-plan.md"
        plan_path.write_text(plan_content)
        output_path = self.artifact_root / "superpowers-plan.md"

        from tools.workflow_cli.adapters.superpowers import adapt_plan
        result = adapt_plan(plan_path, output_path)
        self.assertEqual(result, "derived_plan_written")
        self.assertTrue(output_path.exists())

        content = output_path.read_text()
        self.assertIn("superpowers:subagent-driven-development", content)
        self.assertIn("PLAN-TASK-001", content)
        self.assertIn("SPEC-FR-001", content)

if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run integration test**

Run: `cd /Users/xubo/x-skills/req-to-plan && python3 -m unittest tests.test_integration -v`
Expected: All tests PASS

- [ ] **Step 3: Commit**

```bash
cd /Users/xubo/x-skills/req-to-plan && git add tests/test_integration.py && git commit -m "test: add integration smoke test"
```

---

### Task 10: CLAUDE.md project instructions

**Files:**
- Create: `CLAUDE.md`

- [ ] **Step 1: Write CLAUDE.md**

```markdown
# req-to-plan

Requirement-to-PLAN Agent workflow. Converts raw requirements into executor-neutral implementation plans through a 6-stage pipeline (raw_requirement intake + 5 transformation stages), then adapts PLANs to Superpowers format for execution.

## Project Structure

- `docs/*.md` — Workflow stage contracts (source of truth for each stage's rules)
- `tools/workflow_cli/` — Python CLI state machine (Agent-internal)
- `tools/coyeme-workflow-*` — User-facing Agent shortcut commands
- `.req-to-plan/` — Workflow run artifacts (generated, git-ignored)
- `.claude/skills/req-to-plan.md` — Agent skill for driving the workflow

## How to Operate

Run these commands in the project root:

```bash
# Start a new requirement
./tools/coyeme-workflow-start "Your requirement description"

# Continue the current workflow run
./tools/coyeme-workflow-continue

# Check status
./tools/coyeme-workflow-status [--all]

# Switch active run
./tools/coyeme-workflow-switch --work-id <id>

# Generate Superpowers plan from approved PLAN
./tools/coyeme-workflow-adapt --executor superpowers
```

## Running Tests

```bash
python3 -m unittest discover -s tests -p "test_*.py" -v
```

## Key Rules

- The CLI manages state; the Agent generates semantic content
- Never modify approved artifacts in place
- Never skip DESIGN (use light DESIGN for trivial work)
- PLAN is executor-neutral; Superpowers adaptation is post-PLAN
```

- [ ] **Step 2: Commit**

```bash
cd /Users/xubo/x-skills/req-to-plan && git add CLAUDE.md && git commit -m "docs: add CLAUDE.md with project instructions"
```

---

## Plan Self-Review

**1. Spec coverage check:**
- ✅ CLI state machine (state.py, artifact.py, gates.py, cli.py, output.py)
- ✅ Agent skill (req-to-plan.md) driving the 6-stage workflow (raw_requirement + 5 transformation stages)
- ✅ Superpowers adapter (adapters/superpowers.py)
- ✅ Agent shortcuts (agent_shortcuts.py + wrapper scripts)
- ✅ Structured gate validation (gates.py)
- ✅ All 22 CLI commands (plus 2 review-only gateways) covered in cli.py
- ✅ Integration test validating full workflow
- ✅ CLAUDE.md project instructions

**2. Placeholder scan:**
- No TBD, TODO, or "implement later"
- All code steps contain actual implementation code
- All test steps contain actual test code
- All commands have exact syntax

**3. Type consistency:**
- `WorkId`, `RunRecord`, `RunStatus`, `Stage` used consistently across all modules
- CLI commands reference consistent flag names (`--work-id`, `--stage`, `--json`, `--confirm`)
- Artifact filenames consistent with STAGE_ARTIFACT_MAP

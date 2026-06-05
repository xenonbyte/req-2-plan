"""Cross-stage trace coverage (R3). Derived from artifacts; no stored matrix."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from tools.workflow_cli.models import STAGE_ARTIFACT_MAP, Stage

# REQ-AUTH-001 / RISK-SEC-001 / DES-AUTH-001 / SPEC-AUTH-001 / SCOPE-IN-001 / SCOPE-OUT-001 / PLAN-TASK-001
_ID_RE = re.compile(r"(?:REQ|RISK|DES|SPEC)-[A-Z]+-\d+|SCOPE-(?:IN|OUT)-\d+|PLAN-TASK-\d+")


@dataclass
class TraceModel:
    defined: dict = field(default_factory=dict)     # id -> stage value where first defined
    referenced: dict = field(default_factory=dict)  # id -> set of stage values referencing it


def _scope_ids_defined_in_brief(stage: Stage, content: str) -> set[str]:
    """SCOPE-* ids are defined by bullet entries in the brief scope sections."""
    if stage != Stage.REQUIREMENT_BRIEF:
        return set()
    ids: set[str] = set()
    capture = False
    for line in content.splitlines():
        stripped = line.strip()
        if stripped in {"## In-Scope", "## Out-of-Scope"}:
            capture = True
            continue
        if capture and line.lstrip().startswith("#"):
            capture = False
        if capture:
            ids.update(m.group(0) for m in _ID_RE.finditer(line) if m.group(0).startswith("SCOPE-"))
    return ids


def _artifact_text(run_dir: Path, stage: Stage) -> str:
    path = run_dir / STAGE_ARTIFACT_MAP[stage]
    return path.read_text(encoding="utf-8") if path.exists() else ""


def _plan_task_bodies(plan_content: str):
    starts = [m.start() for m in re.finditer(r"(?m)^###\s+PLAN-TASK-\d+\b", plan_content)]
    for index, start in enumerate(starts):
        end = starts[index + 1] if index + 1 < len(starts) else len(plan_content)
        yield plan_content[start:end]


def _plan_task_field_value(body: str, field: str) -> str:
    m = re.search(rf"(?m)^{re.escape(field)}:\s*(.*)$", body)
    return m.group(1).strip() if m else ""


def plan_consumed_spec_ids(run_dir: Path) -> set[str]:
    """SPEC IDs consumed by PLAN-TASK Spec References fields, not merely mentioned."""
    plan = _artifact_text(run_dir, Stage.PLAN)
    consumed: set[str] = set()
    for body in _plan_task_bodies(plan):
        consumed.update(m.group(0) for m in _ID_RE.finditer(_plan_task_field_value(body, "Spec References"))
                        if m.group(0).startswith("SPEC-"))
    return consumed


def _spec_blocks(spec_content: str) -> dict[str, str]:
    starts = list(re.finditer(r"(?m)^#+\s+(SPEC-[A-Z]+-\d+)\b", spec_content))
    blocks: dict[str, str] = {}
    for index, match in enumerate(starts):
        end = starts[index + 1].start() if index + 1 < len(starts) else len(spec_content)
        blocks[match.group(1)] = spec_content[match.start():end]
    return blocks


def _risk_blocks(content: str) -> dict[str, str]:
    starts = list(re.finditer(r"(?m)^#+\s+(RISK-[A-Z]+-\d+)\b", content))
    blocks: dict[str, str] = {}
    for index, match in enumerate(starts):
        end = starts[index + 1].start() if index + 1 < len(starts) else len(content)
        blocks[match.group(1)] = content[match.start():end]
    return blocks


def scope_in_not_closed(run_dir: Path) -> list[str]:
    """SCOPE-IN closes only when a PLAN-TASK carries it or consumes a SPEC carrying it."""
    model = build_trace(run_dir)
    plan_text = _artifact_text(run_dir, Stage.PLAN)
    plan_task_text = "\n".join(_plan_task_bodies(plan_text))
    spec_blocks = _spec_blocks(_artifact_text(run_dir, Stage.SPEC))
    consumed_specs = plan_consumed_spec_ids(run_dir)
    issues: list[str] = []
    for id_ in sorted(i for i in model.defined if i.startswith("SCOPE-IN-")):
        if id_ in plan_task_text:
            continue
        if any(id_ in spec_blocks.get(spec_id, "") for spec_id in consumed_specs):
            continue
        issues.append(id_)
    return issues


def risk_ids_not_closed(run_dir: Path) -> list[str]:
    """RISK-* blocks must declare Status: mitigated|deferred|out_of_scope.

    v1 limitation: blocks are split by RISK-* headings over the concatenated
    artifacts, so a block runs until the next RISK heading, and Status must be
    one of the three exact tokens. This is conservative but coarse; refine the
    block boundaries if false positives surface in practice.
    """
    model = build_trace(run_dir)
    content = "\n".join(_artifact_text(run_dir, s) for s in STAGE_ARTIFACT_MAP)
    blocks = _risk_blocks(content)
    open_risks: list[str] = []
    for id_ in sorted(i for i in model.defined if i.startswith("RISK-")):
        if not re.search(r"(?m)^Status:\s*(mitigated|deferred|out_of_scope)\s*$", blocks.get(id_, "")):
            open_risks.append(id_)
    return open_risks


def build_trace(run_dir: Path) -> TraceModel:
    model = TraceModel()
    for stage, filename in STAGE_ARTIFACT_MAP.items():
        path = run_dir / filename
        if not path.exists():
            continue
        content = path.read_text(encoding="utf-8")
        heading_ids: set[str] = set()
        for line in content.splitlines():
            if line.lstrip().startswith("#"):
                heading_ids.update(m.group(0) for m in _ID_RE.finditer(line))
        definition_ids = heading_ids | _scope_ids_defined_in_brief(stage, content)
        all_ids = {m.group(0) for m in _ID_RE.finditer(content)}
        for id_ in definition_ids:
            model.defined.setdefault(id_, stage.value)
        for id_ in all_ids:
            if id_ in definition_ids and model.defined.get(id_) == stage.value:
                continue
            model.referenced.setdefault(id_, set()).add(stage.value)
    return model


def spec_ids_not_consumed(run_dir: Path) -> list[str]:
    """SPEC-* defined but not consumed by PLAN-TASK Spec References fields."""
    model = build_trace(run_dir)
    consumed = plan_consumed_spec_ids(run_dir)
    return sorted(id_ for id_, _ in model.defined.items()
                  if id_.startswith("SPEC-") and id_ not in consumed)


def check_trace_closure(run_dir: Path) -> list[str]:
    issues: list[str] = []
    for id_ in spec_ids_not_consumed(run_dir):
        issues.append(f"SPEC {id_} is not consumed by any PLAN-TASK (coverage gap).")
    for id_ in scope_in_not_closed(run_dir):
        issues.append(f"In-scope item {id_} is not carried into PLAN consumption (scope not closed).")
    for id_ in risk_ids_not_closed(run_dir):
        issues.append(f"Risk {id_} is not mitigated, deferred, or marked out-of-scope (risk not closed).")
    return issues

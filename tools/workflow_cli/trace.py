"""Cross-stage trace coverage (R3). Derived from artifacts; no stored matrix."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from tools.workflow_cli.markdown import (
    heading_bounded_bodies,
    heading_level,
    strip_readonly_sections,
    unfenced_markdown_lines,
    unfenced_markdown_text,
)
from tools.workflow_cli.models import STAGE_ARTIFACT_MAP, Stage
from tools.workflow_cli.stage_schema import PLAN_TASK_FIELD_RE

# REQ-AUTH-001 / RISK-SEC-001 / DES-AUTH-001 / SPEC-AUTH-001 / SCOPE-IN-001 / SCOPE-OUT-001 / PLAN-TASK-001
_ID_RE = re.compile(r"(?:REQ|RISK|DES|SPEC)-[A-Z]+-\d+|SCOPE-(?:IN|OUT)-\d+|PLAN-TASK-\d+")
_PLAN_TASK_HEADING_RE = re.compile(r"^###\s+PLAN-TASK-\d+\b")
_NATIVE_HEADING_ID_PREFIXES: dict[Stage, tuple[str, ...]] = {
    Stage.RAW_REQUIREMENT: ("REQ-",),
    Stage.RISK_DISCOVERY: ("RISK-",),
    Stage.DESIGN: ("DES-",),
    Stage.SPEC: ("SPEC-",),
    Stage.PLAN: ("PLAN-TASK-",),
}


@dataclass
class TraceModel:
    defined: dict = field(default_factory=dict)     # id -> stage value where first defined


def _scope_ids_defined_in_brief(stage: Stage, content: str) -> set[str]:
    """SCOPE-* ids are defined by bullet entries in the brief scope sections."""
    if stage != Stage.REQUIREMENT_BRIEF:
        return set()
    ids: set[str] = set()
    capture = False
    capture_level = 0
    for line, _, _ in unfenced_markdown_lines(content):
        stripped = line.strip()
        level = heading_level(line)
        if stripped in {"## In-Scope", "## Out-of-Scope"}:
            capture = True
            capture_level = level or 0
            continue
        if capture and level is not None and level <= capture_level:
            capture = False
        if capture:
            ids.update(m.group(0) for m in _ID_RE.finditer(line) if m.group(0).startswith("SCOPE-"))
    return ids


def _native_heading_ids(stage: Stage, content: str) -> set[str]:
    prefixes = _NATIVE_HEADING_ID_PREFIXES.get(stage, ())
    if not prefixes:
        return set()
    ids: set[str] = set()
    for line, _, _ in unfenced_markdown_lines(content):
        if line.lstrip().startswith("#"):
            for match in _ID_RE.finditer(line):
                id_ = match.group(0)
                if id_.startswith(prefixes):
                    ids.add(id_)
    return ids


def _artifact_text(run_dir: Path, stage: Stage) -> str:
    path = run_dir / STAGE_ARTIFACT_MAP[stage]
    return strip_readonly_sections(path.read_text(encoding="utf-8")) if path.exists() else ""


def _plan_task_bodies(plan_content: str):
    return heading_bounded_bodies(plan_content, _PLAN_TASK_HEADING_RE.match)


def _find_plan_task_field(body: str, field: str):
    field_re = re.compile(rf"^{re.escape(field)}:\s*(.*)$")
    for line, start, _ in unfenced_markdown_lines(body):
        m = field_re.match(line)
        if m:
            return m, start
    return None


def _find_next_plan_task_field_start(body: str, after: int) -> int | None:
    for line, start, _ in unfenced_markdown_lines(body):
        if start >= after and PLAN_TASK_FIELD_RE.match(line):
            return start
    return None


def _plan_task_field_value(body: str, field: str) -> str:
    found = _find_plan_task_field(body, field)
    if found is None:
        return ""
    match, line_start = found
    body_start = line_start + match.end()
    next_start = _find_next_plan_task_field_start(body, body_start)
    end = next_start if next_start is not None else len(body)
    return f"{match.group(1)}\n{body[body_start:end]}".strip()


def plan_consumed_spec_ids(run_dir: Path) -> set[str]:
    """SPEC IDs consumed by PLAN-TASK Spec References fields, not merely mentioned."""
    plan = _artifact_text(run_dir, Stage.PLAN)
    consumed: set[str] = set()
    for body in _plan_task_bodies(plan):
        consumed.update(m.group(0) for m in _ID_RE.finditer(_plan_task_field_value(body, "Spec References"))
                        if m.group(0).startswith("SPEC-"))
    return consumed


def _heading_blocks(content: str, id_pattern: str) -> dict[str, str]:
    """Map each `id_pattern` ID defined in a heading to its section text.

    A block runs from its heading to the next same-or-higher heading, so a
    later sibling section cannot bleed its references into the block. Fenced
    code is ignored.
    """
    content = unfenced_markdown_text(content)
    starts = list(re.finditer(rf"(?m)^(#+)\s+.*?\b({id_pattern})\b", content))
    headings = list(re.finditer(r"(?m)^(#+)\s+", content))
    blocks: dict[str, str] = {}
    for match in starts:
        level = len(match.group(1))
        end = len(content)
        for heading in headings:
            if heading.start() <= match.start():
                continue
            if len(heading.group(1)) <= level:
                end = heading.start()
                break
        blocks[match.group(2)] = content[match.start():end]
    return blocks


def _spec_blocks(spec_content: str) -> dict[str, str]:
    return _heading_blocks(spec_content, r"SPEC-[A-Z]+-\d+")


def _risk_blocks(content: str) -> dict[str, str]:
    return _heading_blocks(content, r"RISK-[A-Z]+-\d+")


def scope_in_not_closed(run_dir: Path) -> list[str]:
    """SCOPE-IN closes only when a PLAN-TASK carries it or consumes a SPEC carrying it."""
    model = build_trace(run_dir)
    plan_text = _artifact_text(run_dir, Stage.PLAN)
    plan_task_text = "\n".join(unfenced_markdown_text(body) for body in _plan_task_bodies(plan_text))
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
    """RISK-* blocks must declare Status: mitigated|deferred|out_of_scope|out-of-scope.

    Closure is read only from the risk definition block in RISK_DISCOVERY.
    A block stops at the next same-or-higher Markdown heading, so unrelated
    downstream Status fields cannot close an open risk.
    """
    model = build_trace(run_dir)
    blocks = _risk_blocks(_artifact_text(run_dir, Stage.RISK_DISCOVERY))
    open_risks: list[str] = []
    for id_ in sorted(i for i in model.defined if i.startswith("RISK-")):
        if not re.search(r"(?m)^Status:\s*(mitigated|deferred|out(?:_of_scope|-of-scope))\s*$", blocks.get(id_, "")):
            open_risks.append(id_)
    return open_risks


def build_trace(run_dir: Path) -> TraceModel:
    model = TraceModel()
    for stage, filename in STAGE_ARTIFACT_MAP.items():
        path = run_dir / filename
        if not path.exists():
            continue
        content = _artifact_text(run_dir, stage)
        heading_ids = _native_heading_ids(stage, content)
        definition_ids = heading_ids | _scope_ids_defined_in_brief(stage, content)
        for id_ in definition_ids:
            model.defined.setdefault(id_, stage.value)
    return model


def spec_ids_not_consumed(run_dir: Path) -> list[str]:
    """SPEC-* defined but not consumed by PLAN-TASK Spec References fields."""
    model = build_trace(run_dir)
    consumed = plan_consumed_spec_ids(run_dir)
    return sorted(id_ for id_, _ in model.defined.items()
                  if id_.startswith("SPEC-") and id_ not in consumed)


def scope_out_violations(run_dir: Path) -> list[str]:
    """SCOPE-OUT-* ids that executable PLAN-TASK bodies reference — a scope overflow (R8)."""
    plan_text = _artifact_text(run_dir, Stage.PLAN)
    plan_task_text = "\n".join(unfenced_markdown_text(body) for body in _plan_task_bodies(plan_text))
    return sorted(
        {
            m.group(0)
            for m in _ID_RE.finditer(plan_task_text)
            if m.group(0).startswith("SCOPE-OUT-")
        }
    )


def check_trace_closure(run_dir: Path) -> list[str]:
    issues: list[str] = []
    for id_ in spec_ids_not_consumed(run_dir):
        issues.append(f"SPEC {id_} is not consumed by any PLAN-TASK (coverage gap).")
    for id_ in scope_in_not_closed(run_dir):
        issues.append(f"In-scope item {id_} is not carried into PLAN consumption (scope not closed).")
    for id_ in risk_ids_not_closed(run_dir):
        issues.append(f"Risk {id_} is not mitigated, deferred, or marked out-of-scope (risk not closed).")
    return issues

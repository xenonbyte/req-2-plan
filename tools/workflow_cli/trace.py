"""Cross-stage trace coverage (R3). Derived from artifacts; no stored matrix."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from tools.workflow_cli.models import STAGE_ARTIFACT_MAP, Stage

# REQ-AUTH-001 / RISK-SEC-001 / DES-AUTH-001 / SPEC-AUTH-001 / SCOPE-IN-001 / SCOPE-OUT-001 / PLAN-TASK-001
_ID_RE = re.compile(r"(?:REQ|RISK|DES|SPEC)-[A-Z]+-\d+|SCOPE-(?:IN|OUT)-\d+|PLAN-TASK-\d+")
_PLAN_TASK_HEADING_RE = re.compile(r"^###\s+PLAN-TASK-\d+\b")
_MARKDOWN_FENCE_MARKER_RE = re.compile(r"^[ \t]{0,3}(`{3,}|~{3,})")


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
    for line, _, _ in _unfenced_markdown_lines(content):
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


def _unfenced_markdown_text(content: str) -> str:
    return "".join(line for line, _, _ in _unfenced_markdown_lines(content))


def _plan_task_bodies(plan_content: str):
    starts = [
        start
        for line, start, _ in _unfenced_markdown_lines(plan_content)
        if _PLAN_TASK_HEADING_RE.match(line)
    ]
    for index, start in enumerate(starts):
        end = starts[index + 1] if index + 1 < len(starts) else len(plan_content)
        yield plan_content[start:end]


def _plan_task_field_value(body: str, field: str) -> str:
    field_re = re.compile(rf"^{re.escape(field)}:\s*(.*)$")
    for line, _, _ in _unfenced_markdown_lines(body):
        m = field_re.match(line)
        if m:
            return m.group(1).strip()
    return ""


def plan_consumed_spec_ids(run_dir: Path) -> set[str]:
    """SPEC IDs consumed by PLAN-TASK Spec References fields, not merely mentioned."""
    plan = _artifact_text(run_dir, Stage.PLAN)
    consumed: set[str] = set()
    for body in _plan_task_bodies(plan):
        consumed.update(m.group(0) for m in _ID_RE.finditer(_plan_task_field_value(body, "Spec References"))
                        if m.group(0).startswith("SPEC-"))
    return consumed


def _spec_blocks(spec_content: str) -> dict[str, str]:
    spec_content = _unfenced_markdown_text(spec_content)
    starts = list(re.finditer(r"(?m)^#+\s+.*?\b(SPEC-[A-Z]+-\d+)\b", spec_content))
    blocks: dict[str, str] = {}
    for index, match in enumerate(starts):
        end = starts[index + 1].start() if index + 1 < len(starts) else len(spec_content)
        blocks[match.group(1)] = spec_content[match.start():end]
    return blocks


def _risk_blocks(content: str) -> dict[str, str]:
    content = _unfenced_markdown_text(content)
    starts = list(re.finditer(r"(?m)^(#+)\s+.*?\b(RISK-[A-Z]+-\d+)\b", content))
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


def scope_in_not_closed(run_dir: Path) -> list[str]:
    """SCOPE-IN closes only when a PLAN-TASK carries it or consumes a SPEC carrying it."""
    model = build_trace(run_dir)
    plan_text = _artifact_text(run_dir, Stage.PLAN)
    plan_task_text = "\n".join(_unfenced_markdown_text(body) for body in _plan_task_bodies(plan_text))
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

    Closure is read only from the risk definition block in RISK_DISCOVERY.
    A block stops at the next same-or-higher Markdown heading, so unrelated
    downstream Status fields cannot close an open risk.
    """
    model = build_trace(run_dir)
    blocks = _risk_blocks(_artifact_text(run_dir, Stage.RISK_DISCOVERY))
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
        for line, _, _ in _unfenced_markdown_lines(content):
            if line.lstrip().startswith("#"):
                heading_ids.update(m.group(0) for m in _ID_RE.finditer(line))
        definition_ids = heading_ids | _scope_ids_defined_in_brief(stage, content)
        all_ids = {m.group(0) for m in _ID_RE.finditer(_unfenced_markdown_text(content))}
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


def scope_out_violations(run_dir: Path) -> list[str]:
    """SCOPE-OUT-* ids that the PLAN references — a scope overflow (R8)."""
    model = build_trace(run_dir)
    plan = Stage.PLAN.value
    return sorted(
        id_ for id_, stages in model.referenced.items()
        if id_.startswith("SCOPE-OUT-") and plan in stages
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

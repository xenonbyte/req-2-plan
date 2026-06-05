"""
Tier-aware structured gate checks for the req-to-plan workflow CLI.

The CLI runs these structural checks before checkpoint approval.
The Agent handles semantic quality; this module handles structural validation.
"""
from __future__ import annotations

import re
from collections import Counter
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
from tools.workflow_cli.markdown import (
    heading_bounded_bodies,
    heading_level,
    strip_readonly_sections,
    unfenced_markdown_lines,
    unfenced_markdown_text,
)
from tools.workflow_cli.output import EXIT_GATE_FAIL
from tools.workflow_cli.stage_schema import PLAN_TASK_FIELD_RE, PLAN_TASK_FIELDS

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

_FILL_IN_PLACEHOLDER_RE = re.compile(r"<!--\s*fill in\s*-->", re.IGNORECASE)

_PLACEHOLDER_PATTERNS = [
    _FILL_IN_PLACEHOLDER_RE,                              # untouched template body
    re.compile(
        r"(?im)^\s*(?:[-*]\s*)?(?:[A-Za-z][A-Za-z0-9 /_-]*:\s*)?TBD\s*$"
    ),                                                     # TBD as a line, field value, or list item
    re.compile(r"(?im)^\s*(?:[-*]\s*)?maybe\s*$"),
    re.compile(r"\bTODO later\b", re.IGNORECASE),
    re.compile(
        r"(?im)^\s*(?:[-*]\s*)?(?:[A-Za-z][A-Za-z0-9 /_-]*:\s*)?FIXME\s*$"
    ),                                                     # FIXME as a placeholder line/field, not prose
]

# IDs that represent upstream references: REQ-*, RISK-*, DES-*, SPEC-*
_UPSTREAM_ID_PATTERN = re.compile(
    r"\b(REQ-[A-Z]+-\d+|RISK-[A-Z]+-\d+|DES-[A-Z]+-\d+|SPEC-[A-Z]+-\d+)\b"
)

# Trace-ID validation: well-formed vs candidate patterns
_VALID_TRACE_ID_RE = re.compile(
    r"^(?:REQ|RISK|DES|SPEC)-[A-Z]+-\d+$|^SCOPE-(?:IN|OUT)-\d+$|^PLAN-TASK-\d+$"
)
_TRACE_ID_CANDIDATE_RE = re.compile(
    r"\b(?:REQ|RISK|DES|SPEC)-[A-Za-z][A-Za-z0-9_-]*\d[A-Za-z0-9_-]*"
    r"|\bSCOPE-(?:IN|OUT)-[A-Za-z0-9_-]*\d[A-Za-z0-9_-]*"
    r"|\bPLAN-TASK-[A-Za-z0-9_-]*\d[A-Za-z0-9_-]*"
)

# Native-ID heading patterns: stages that MUST define at least one native ID in a heading
_STAGE_NATIVE_HEADING_PATTERNS = {
    Stage.RISK_DISCOVERY: re.compile(r"(?m)^#+\s+.*\bRISK-[A-Z]+-\d+\b"),
    Stage.DESIGN: re.compile(r"(?m)^#+\s+.*\bDES-[A-Z]+-\d+\b"),
    Stage.SPEC: re.compile(r"(?m)^#+\s+.*\bSPEC-[A-Z]+-\d+\b"),
}

# Closure status tags
_CLOSURE_TAGS = frozenset(["[ADDRESSED]", "[DEFERRED]", "[N/A]", "[OUT-OF-SCOPE]", "[CLOSED]"])

# IDs of form [A-Z]+-[A-Z]+-[0-9]+ (definition context: heading or line-start)
_DEFINED_ID_PATTERN = re.compile(r"\b([A-Z]+-[A-Z]+-\d+)\b")


def _find_defined_ids(content: str) -> set[str]:
    """Return IDs that are defined in headings (i.e. the current artifact is defining them)."""
    heading_pattern = re.compile(r"^#{1,6}\s+.*\b([A-Z]+-[A-Z]+-\d+)\b", re.MULTILINE)
    return set(heading_pattern.findall(unfenced_markdown_text(content)))


def _find_ids_without_closure(content: str) -> list[str]:
    """Return upstream IDs referenced in content that have no closure tag.

    IDs defined in headings of the current artifact are excluded — they are
    being *defined* here, not referencing upstream artifacts that need closure.
    """
    search_content = unfenced_markdown_text(content)
    all_refs = set(_UPSTREAM_ID_PATTERN.findall(search_content))
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
            if pattern.search(search_content):
                has_closure = True
                break
        if not has_closure:
            unclosed.append(ref_id)
    return unclosed


def _find_duplicate_ids(content: str) -> list[str]:
    """Return IDs that appear more than once in heading (definition) context."""
    heading_pattern = re.compile(r"^#{1,6}\s+.*\b([A-Z]+-[A-Z]+-\d+)\b", re.MULTILINE)
    heading_ids = heading_pattern.findall(unfenced_markdown_text(content))

    from collections import Counter
    counts = Counter(heading_ids)
    return [id_ for id_, count in counts.items() if count > 1]


# ---------------------------------------------------------------------------
# SPEC External Documentation Checked helpers
# ---------------------------------------------------------------------------

_EXTERNAL_DOCS_RE = re.compile(r"^## External Documentation Checked\s*$", re.MULTILINE)
_H2_RE = re.compile(r"^##\s+", re.MULTILINE)
_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


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
    for line, _, end in unfenced_markdown_lines(content):
        if _EXTERNAL_DOCS_RE.match(line):
            section_start = end
            break
    if section_start is None:
        return False

    for line, start, _ in unfenced_markdown_lines(content):
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
_CODE_FENCE_LINE_RE = re.compile(r"^[ \t]{0,3}(`{3,}|~{3,})(.*)$")
_INLINE_CODE_VALUE_RE = re.compile(r"^(`+)(.*?)\1$", re.DOTALL)
_MARKDOWN_LINK_VALUE_RE = re.compile(r"^\[([^\]]+)\]\([^)]+\)$")


def _plan_task_starts(content: str) -> list[int]:
    return [
        start
        for line, start, _ in unfenced_markdown_lines(content)
        if _PLAN_TASK_RE.match(line)
    ]


def _plan_task_field_body(task_body: str, field: str) -> str:
    found = _find_plan_task_field(task_body, field)
    if found is None:
        return ""
    match, line_start = found
    body_start = line_start + match.end()
    next_start = _find_next_plan_task_field_start(task_body, body_start)
    end = next_start if next_start is not None else len(task_body)
    return f"{match.group(1)}\n{task_body[body_start:end]}"


def _find_plan_task_field(task_body: str, field: str):
    field_re = re.compile(rf"^{re.escape(field)}:[ \t]*(.*)$")
    for line, start, _ in unfenced_markdown_lines(task_body):
        match = field_re.match(line)
        if match:
            return match, start
    return None


def _find_next_plan_task_field_start(task_body: str, after: int) -> int | None:
    for line, start, _ in unfenced_markdown_lines(task_body):
        if start >= after and PLAN_TASK_FIELD_RE.match(line):
            return start
    return None


def _plan_task_field_value(task_body: str, field: str) -> str:
    found = _find_plan_task_field(task_body, field)
    if found is None:
        return ""
    match, _ = found
    return match.group(1).strip()


def _iter_plan_task_bodies(content: str):
    return heading_bounded_bodies(content, _PLAN_TASK_RE.match)


def _plan_task_label(body: str) -> str:
    m = re.match(r"###\s+PLAN-TASK-(\d+)", body)
    return f"PLAN-TASK-{m.group(1)}" if m else "PLAN-TASK-?"


def _strip_markdown_path_wrappers(value: str) -> str:
    text = value.strip()
    changed = True
    while changed:
        changed = False
        inline_code = _INLINE_CODE_VALUE_RE.fullmatch(text)
        if inline_code:
            text = inline_code.group(2).strip()
            changed = True
            continue
        markdown_link = _MARKDOWN_LINK_VALUE_RE.fullmatch(text)
        if markdown_link:
            text = markdown_link.group(1).strip()
            changed = True
            continue
        if len(text) >= 2 and text.startswith("<") and text.endswith(">"):
            text = text[1:-1].strip()
            changed = True
            continue
        for marker in ("**", "__"):
            if (
                len(text) > 2 * len(marker)
                and text.startswith(marker)
                and text.endswith(marker)
            ):
                text = text[len(marker):-len(marker)].strip()
                changed = True
                break
    return text


def _plan_task_path_part(raw_path: str) -> str:
    value = _strip_markdown_path_wrappers(raw_path)
    return _strip_markdown_path_wrappers(value.split("::")[0])


_NO_FILE_SENTINELS = frozenset({"n/a"})


def _is_no_file_sentinel(path_part: str) -> bool:
    return path_part.strip().lower() in _NO_FILE_SENTINELS


def _plan_task_file_paths(files_field: str) -> list[str]:
    paths: list[str] = []
    lines = [line for line, _, _ in unfenced_markdown_lines(files_field)]
    if not lines:
        return paths

    first = lines[0].strip()
    if first:
        raw_path = first[2:].strip() if first.startswith(("- ", "* ")) else first
        path_part = _plan_task_path_part(raw_path)
        if path_part and not _is_no_file_sentinel(path_part):
            paths.append(path_part)

    for line in lines[1:]:
        stripped = line.strip()
        if not stripped.startswith(("- ", "* ")):
            continue
        path_part = _plan_task_path_part(stripped[2:])
        if path_part and not _is_no_file_sentinel(path_part):
            paths.append(path_part)
    return paths


def _context_pack_repo_root(run_dir: Path) -> Path | None:
    """Usable Context Pack repo_root, or None when the pack is missing,
    unreadable, invalid JSON, lacks repo_root, or does not point at an existing directory."""
    import json
    pack_json = run_dir / "02-project-context.json"
    if not pack_json.exists():
        return None
    try:
        decoded = json.loads(pack_json.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return None
    if not isinstance(decoded, dict):
        return None
    raw = decoded.get("repo_root", "")
    if not isinstance(raw, str) or not raw.strip():
        return None
    repo_root = Path(raw)
    if not repo_root.is_dir():
        return None
    return repo_root.resolve()


def _context_pack_remediation_command(run_dir: Path) -> str:
    import shlex
    package_root = Path(__file__).resolve().parents[2]
    pythonpath = f"PYTHONPATH={shlex.quote(str(package_root))}${{PYTHONPATH:+:$PYTHONPATH}}"
    command = (
        f"{pythonpath} python3 -m tools.workflow_cli "
        f"context-build --work-id {run_dir.name}"
    )
    if run_dir.parent.name == ".req-to-plan":
        base_dir = run_dir.parent.parent
        try:
            if base_dir.resolve() != Path.cwd().resolve():
                command += f" --base-path {shlex.quote(str(base_dir))}"
        except (OSError, RuntimeError):
            # cwd deleted (OSError) or symlink-loop resolve (RuntimeError)
            command += " --base-path <base-dir>"
    return command + " --repo-path <repo-dir>"


def _check_plan_context_pack(run_dir: Path) -> list[str]:
    """R11: standard-tier PLAN must anchor file facts to a usable Context Pack.

    Every no-usable-truth-anchor path blocks loudly; after the user replaces
    <repo-dir>, the remediation command can import the installed workflow modules.
    """
    if _context_pack_repo_root(run_dir) is not None:
        return []
    return [
        "Standard-tier PLAN requires a usable Project Context Pack: "
        "02-project-context.json is missing, unreadable, invalid, or its "
        "repo_root is unavailable. Build it with: "
        f"{_context_pack_remediation_command(run_dir)}"
    ]


def _check_plan_file_refs(run_dir: Path, content: str) -> list[str]:
    """Hard-check Files paths against the Context Pack repo_root. create-type tasks
    are exempt; the part after '::' (a symbol) is advisory and not checked (no AST pack yet)."""
    repo_root = _context_pack_repo_root(run_dir)
    if repo_root is None:
        return []  # no usable ground truth; standard tier blocks via _check_plan_context_pack
    issues: list[str] = []
    for body in _iter_plan_task_bodies(content):
        skip_missing_path = _normalized_change_type(_task_change_type(body)) == "create"
        files_field = _plan_task_field_body(body, "Files")
        for path_part in _plan_task_file_paths(files_field):
            path = Path(path_part)
            if path.is_absolute():
                resolved = path.resolve()
            else:
                resolved = (repo_root / path).resolve()
            try:
                resolved.relative_to(repo_root)
            except ValueError:
                issues.append(
                    f"PLAN-TASK Files references path outside repo_root {path_part!r}."
                )
                continue
            if not resolved.exists():
                if not skip_missing_path:
                    issues.append(
                        f"PLAN-TASK Files references missing path {path_part!r} "
                        "(mark the task 'Change Type: create' if it is a new file)."
                    )
    return issues


def _check_spec_refs_valid(run_dir: Path, content: str) -> list[str]:
    spec_path = run_dir / STAGE_ARTIFACT_MAP[Stage.SPEC]
    spec_content = (
        strip_readonly_sections(spec_path.read_text(encoding="utf-8"))
        if spec_path.exists()
        else ""
    )
    defined_specs: set[str] = set()
    for line, _, _ in unfenced_markdown_lines(spec_content):
        if line.lstrip().startswith("#"):
            defined_specs.update(re.findall(r"\bSPEC-[A-Z]+-\d+\b", line))
    issues: list[str] = []
    for body in _iter_plan_task_bodies(content):
        refs_body = _plan_task_field_body(body, "Spec References")
        refs = re.findall(r"SPEC-[A-Z]+-\d+", refs_body)
        if refs_body.strip() and not refs:
            issues.append(
                f"{_plan_task_label(body)} must reference at least one SPEC-* ID "
                "in 'Spec References:'."
            )
        for ref in refs:
            if ref not in defined_specs:
                issues.append(f"PLAN-TASK references {ref} which is not defined in the SPEC artifact.")
    return issues


# R10: Change Type is a closed operation-kind enum; 'new' is a legacy alias.
_CHANGE_TYPE_VALUES = frozenset({"create", "modify", "delete"})
_CHANGE_TYPE_ALIASES = {"new": "create"}


def _normalized_change_type(raw: str) -> str:
    value = raw.strip().lower()
    return _CHANGE_TYPE_ALIASES.get(value, value)


def _task_change_type(body: str) -> str:
    """Whitespace-normalized Change Type field body (same line + continuation lines)."""
    return " ".join(_plan_task_field_body(body, "Change Type").split())


def _check_plan_task_fields(content: str) -> list[str]:
    issues: list[str] = []
    numbers: list[int] = []
    for body in _iter_plan_task_bodies(content):
        m = re.match(r"###\s+PLAN-TASK-(\d+)", body)
        num = int(m.group(1)) if m else None
        if num is not None:
            numbers.append(num)
        label = _plan_task_label(body)
        for field in PLAN_TASK_FIELDS:
            if not _plan_task_field_body(body, field).strip():
                issues.append(f"{label} is missing a non-empty '{field}:' field.")
        raw_change_type = _task_change_type(body)
        if raw_change_type and _normalized_change_type(raw_change_type) not in _CHANGE_TYPE_VALUES:
            issues.append(
                f"{label} has invalid 'Change Type: {raw_change_type}'; "
                "allowed: create|modify|delete (alias: new = create)."
            )
    if numbers:
        if len(set(numbers)) != len(numbers):
            issues.append("PLAN-TASK numbers must be unique.")
        elif sorted(numbers) != list(range(1, len(numbers) + 1)):
            issues.append("PLAN-TASK numbers must be contiguous starting at 1.")
    return issues


def _has_complete_code_fence(content: str) -> bool:
    fence_char = ""
    fence_len = 0
    has_body = False

    for line in content.splitlines():
        marker = _CODE_FENCE_LINE_RE.match(line)
        if fence_char:
            if (
                marker
                and marker.group(1)[0] == fence_char
                and len(marker.group(1)) >= fence_len
                and not marker.group(2).strip()
            ):
                if has_body:
                    return True
                fence_char = ""
                fence_len = 0
                has_body = False
                continue
            if line.strip():
                has_body = True
            continue

        if marker and marker.group(2).strip():
            fence_char = marker.group(1)[0]
            fence_len = len(marker.group(1))
            has_body = False

    return False


def _plan_tasks_missing_code(content: str) -> bool:
    """True if any TDD-applicable PLAN-TASK has no fenced code block in its Skeleton field."""
    bodies = list(_iter_plan_task_bodies(content))
    if not bodies:
        return False
    for body in bodies:
        skeleton = _plan_task_field_body(body, "Skeleton")
        tdd_applicable = _plan_task_field_value(body, "TDD Applicable")
        if tdd_applicable.lower() == "yes" and not _has_complete_code_fence(skeleton):
            return True
    return False


def _check_plan_task_skeleton_placeholders(content: str) -> list[str]:
    issues: list[str] = []
    for body in _iter_plan_task_bodies(content):
        skeleton = _plan_task_field_body(body, "Skeleton")
        if skeleton.strip() and any(pattern.search(skeleton) for pattern in _PLACEHOLDER_PATTERNS):
            issues.append(
                f"{_plan_task_label(body)} Skeleton contains an unresolved template "
                "placeholder; replace placeholder text before passing the gate."
            )
    return issues


def _section_body(content: str, heading: str) -> str:
    """Return the text of the section under `heading`, stopping at the next same-or-higher heading."""
    level = len(heading) - len(heading.lstrip("#"))
    out, capture = [], False
    for line, _, _ in unfenced_markdown_lines(content):
        if line.strip() == heading:
            capture = True
            continue
        if capture:
            stripped = line.lstrip()
            if stripped.startswith("#"):
                # Count hashes of this line's heading
                line_level = len(stripped) - len(stripped.lstrip("#"))
                if line_level <= level:
                    break
            out.append(line.rstrip("\r\n"))
    return "\n".join(out)


def _section_entries_missing_id(content: str, heading: str, id_prefix: str) -> list[str]:
    missing: list[str] = []
    pattern = re.compile(rf"\b{re.escape(id_prefix)}-\d+\b")
    for line in _section_body(content, heading).splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("<!--"):
            continue
        if not stripped.startswith(("- ", "* ")):
            continue
        if not pattern.search(stripped):
            missing.append(stripped)
    return missing


def _section_entry_ids(content: str, heading: str, id_prefix: str) -> list[str]:
    ids: list[str] = []
    pattern = re.compile(rf"\b{re.escape(id_prefix)}-\d+\b")
    for line in _section_body(content, heading).splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("<!--"):
            continue
        if not stripped.startswith(("- ", "* ")):
            continue
        match = pattern.search(stripped)
        if match:
            ids.append(match.group(0))
    return ids


def _section_has_bullets(content: str, heading: str) -> bool:
    return any(l.lstrip().startswith(("- ", "* ")) for l in _section_body(content, heading).splitlines())


def _check_elicitation(stage: Stage, tier: TierEstimate, content: str) -> list[str]:
    """R8: standard-tier brief must record at least one assumption or open question."""
    from tools.workflow_cli.models import TierBase
    if stage != Stage.REQUIREMENT_BRIEF or tier.base != TierBase.STANDARD:
        return []
    if _section_has_bullets(content, "## Assumptions") or _section_has_bullets(content, "## Open Questions"):
        return []
    return ["Standard-tier brief must record at least one assumption or open question (R8 elicitation)."]


# R12: decision-request lifecycle vocabulary. The gate owns ONLY the Status
# lifecycle (enum, line presence, section non-emptiness, Selected/Rationale
# when selected); Question/Options/Recommended are template guidance enforced
# at checkpoint, not here (Agent/CLI boundary).
_DECISION_SECTION = "## Decision Requests"
_DECISION_BLOCK_RE = re.compile(r"^###\s+(DECISION-\d+)\b")
_DECISION_NESTED_MARKER_RE = re.compile(r"^(?:#{1,6}\s+|[-*]\s+)DECISION-\d+\b")
_DECISION_STATUS_VALUES = frozenset({"pending", "selected"})


def _decision_field_value(block_lines: list[str], field: str) -> str | None:
    """Value of a `Field:` line within a DECISION block; None when absent."""
    field_re = re.compile(rf"^{re.escape(field)}:\s*(.*)$")
    for line in block_lines:
        m = field_re.match(line.strip())
        if m:
            return m.group(1).strip()
    return None


def _decision_field_count(block_lines: list[str], field: str) -> int:
    field_re = re.compile(rf"^{re.escape(field)}:")
    return sum(1 for line in block_lines if field_re.match(line.strip()))


def _check_decision_requests(stage: Stage, tier: TierEstimate, content: str) -> list[str]:
    """R12: standard DESIGN must list pending human decisions or state `none`."""
    from tools.workflow_cli.models import TierBase
    if stage != Stage.DESIGN or tier.base != TierBase.STANDARD:
        return []
    lines = _section_body(content, _DECISION_SECTION).splitlines()
    starts = [
        (i, m)
        for i, line in enumerate(lines)
        if (m := _DECISION_BLOCK_RE.match(line.strip()))
    ]
    blocks: list[tuple[str, list[str]]] = []
    covered: set[int] = set()
    for start, match in starts:
        end = len(lines)
        for j in range(start + 1, len(lines)):
            if heading_level(lines[j]) is not None:
                end = j
                break
        decision_id = match.group(1)
        blocks.append((decision_id, lines[start + 1:end]))
        covered.update(range(start, end))
    stray = [
        line.strip()
        for i, line in enumerate(lines)
        if i not in covered and line.strip() and not line.strip().startswith("<!--")
    ]

    issues: list[str] = []
    if not blocks:
        if stray == ["none"]:
            return []
        if not stray:
            issues.append(
                "## Decision Requests is empty; state exactly `none` or list "
                "`### DECISION-NNN` blocks (R12)."
            )
        else:
            issues.append(
                "## Decision Requests must be exactly `none` (sole non-comment "
                "content) or `### DECISION-NNN` blocks (R12)."
            )
        return issues
    if stray:
        if "none" in stray:
            issues.append(
                "## Decision Requests mixes `none` with DECISION blocks; keep one (R12)."
            )
        else:
            issues.append(
                "## Decision Requests contains non-comment prose outside DECISION blocks; "
                "use exactly `none` or `### DECISION-NNN` blocks (R12)."
            )
    for dup_id, count in Counter(decision_id for decision_id, _ in blocks).items():
        if count > 1:
            issues.append(
                f"Duplicate decision id {dup_id}; each DECISION-NNN must be unique (R12)."
            )
    for decision_id, body in blocks:
        for line in body:
            if _DECISION_NESTED_MARKER_RE.match(line.strip()):
                issues.append(
                    f"{decision_id} body contains a nested 'DECISION-NNN' marker; "
                    "each decision must be its own '### DECISION-NNN' block (R12)."
                )
                break
        if _decision_field_count(body, "Status") > 1:
            issues.append(
                f"{decision_id} has multiple 'Status:' lines; keep exactly one (R12)."
            )
            continue
        status = _decision_field_value(body, "Status")
        if status is None:
            issues.append(
                f"{decision_id} is missing a 'Status:' line; allowed: pending|selected (R12)."
            )
            continue
        if status.lower() not in _DECISION_STATUS_VALUES:
            issues.append(
                f"{decision_id} has invalid 'Status: {status}'; allowed: pending|selected (R12)."
            )
            continue
        if status.lower() == "pending":
            issues.append(
                f"Unresolved decision request {decision_id} (Status: pending); "
                "a human must choose before this gate can pass (R12)."
            )
            continue
        for field in ("Selected", "Rationale"):
            if not (_decision_field_value(body, field) or "").strip():
                issues.append(
                    f"{decision_id} is 'Status: selected' but missing a non-empty "
                    f"'{field}:' line (R12)."
                )
    return issues


def _check_scope_freeze(stage: Stage, content: str) -> list[str]:
    """R8: brief's In/Out-of-Scope must carry stable IDs so trace can anchor them."""
    if stage != Stage.REQUIREMENT_BRIEF:
        return []
    issues: list[str] = []
    for entry in _section_entries_missing_id(content, "## In-Scope", "SCOPE-IN"):
        issues.append(f"In-Scope entry must carry a SCOPE-IN-* stable ID (R8): {entry}")
    for entry in _section_entries_missing_id(content, "## Out-of-Scope", "SCOPE-OUT"):
        issues.append(f"Out-of-Scope entry must carry a SCOPE-OUT-* stable ID (R8): {entry}")
    for id_, count in Counter(_section_entry_ids(content, "## In-Scope", "SCOPE-IN")).items():
        if count > 1:
            issues.append(f"In-Scope stable ID {id_} is duplicate; scope IDs must be unique (R8).")
    for id_, count in Counter(_section_entry_ids(content, "## Out-of-Scope", "SCOPE-OUT")).items():
        if count > 1:
            issues.append(f"Out-of-Scope stable ID {id_} is duplicate; scope IDs must be unique (R8).")
    if not re.search(r"\bSCOPE-IN-\d+\b", _section_body(content, "## In-Scope")):
        issues.append("In-Scope must list at least one stable-ID entry (SCOPE-IN-001, ...); none found (R8).")
    if not re.search(r"\bSCOPE-OUT-\d+\b", _section_body(content, "## Out-of-Scope")):
        issues.append("Out-of-Scope must list at least one stable-ID entry (SCOPE-OUT-001, ...); none found (R8).")
    return issues


def _has_meaningful_body(text: str) -> bool:
    """True if `text` has at least one non-empty, non-comment line."""
    for line in text.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("<!--"):
            return True
    return False


def _check_stage_schema(stage: Stage, tier: TierEstimate, content: str) -> list[str]:
    """R2 schema gate: required headings present, each required section has a
    non-placeholder body, trace IDs are well-formed, RISK/DESIGN/SPEC define a
    native ID heading, and no unresolved placeholders remain."""
    from tools.workflow_cli.stage_schema import required_headings
    issues: list[str] = []
    headings = required_headings(stage, tier.base)
    native = _STAGE_NATIVE_HEADING_PATTERNS.get(stage)
    unfenced_content = unfenced_markdown_text(content)
    present_headings = {
        line.strip()
        for line, _, _ in unfenced_markdown_lines(content)
        if line.lstrip().startswith("#")
    }

    if not headings and native is None:
        return issues

    # R2.1: required headings must be present
    for heading in headings:
        if heading not in present_headings:
            issues.append(
                f"Missing required section {heading!r} for stage {stage.value!r} "
                f"at tier '{tier.base.value}'."
            )

    # R2.3a: each required heading's section must have a non-placeholder body
    for heading in headings:
        if heading not in present_headings:
            continue  # already reported by the required-heading presence check
        body = _section_body(content, heading)
        if not _has_meaningful_body(body):
            issues.append(
                f"Required section {heading!r} must contain non-placeholder body content."
            )

    # R2.3b: any trace-ID-looking token must be well-formed
    for token in _TRACE_ID_CANDIDATE_RE.findall(unfenced_content):
        if not _VALID_TRACE_ID_RE.fullmatch(token):
            issues.append(
                f"Malformed trace ID {token!r}; use REQ-AREA-001, SPEC-AREA-001, "
                "SCOPE-IN-001, or PLAN-TASK-001 style IDs."
            )

    # R2.3c: RISK_DISCOVERY / DESIGN / SPEC must define at least one native trace ID in a heading
    if native is not None and not native.search(unfenced_content):
        issues.append(
            f"Stage {stage.value!r} must define at least one native trace ID in a heading "
            f"matching {native.pattern!r}."
        )

    # R2.2: placeholder scan
    for pat in _PLACEHOLDER_PATTERNS:
        if pat.search(unfenced_content):
            issues.append(
                "Artifact contains an unresolved placeholder "
                f"(pattern {pat.pattern!r}); fill it before passing the gate."
            )
            break
    return issues


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
    gate_content = strip_readonly_sections(artifact_content)

    # Check 2: content must be non-empty
    if not gate_content or not gate_content.strip():
        issues.append("Artifact content is empty or whitespace-only.")

    if not issues:
        # Check 3: upstream reference coverage closure (all tiers)
        unclosed = _find_ids_without_closure(gate_content)
        if stage == Stage.PLAN:
            from tools.workflow_cli.trace import plan_consumed_spec_ids
            consumed_specs = plan_consumed_spec_ids(run_dir)
            unclosed = [
                ref_id for ref_id in unclosed
                if not (ref_id.startswith("SPEC-") and ref_id in consumed_specs)
            ]
        for ref_id in unclosed:
            issues.append(
                f"Upstream reference {ref_id!r} appears in artifact but has no closure status tag "
                f"([ADDRESSED], [DEFERRED], [N/A], [OUT-OF-SCOPE], or [CLOSED])."
            )

        # Check 4: ID uniqueness within artifact
        duplicates = _find_duplicate_ids(gate_content)
        for dup_id in duplicates:
            issues.append(
                f"Duplicate ID definition {dup_id!r} found in artifact; each ID must be unique."
            )

        # Check 5 (PLAN, standard tier): usable Context Pack required (R11);
        # TDD-applicable tasks must carry a code block.
        from tools.workflow_cli.models import TierBase
        if stage == Stage.PLAN and tier.base == TierBase.STANDARD:
            # R11: a usable Context Pack is the truth anchor for file-ref checks.
            issues.extend(_check_plan_context_pack(run_dir))
            if not _plan_task_starts(gate_content):
                issues.append(
                    "PLAN is missing '### PLAN-TASK-*' sections; standard tier requires "
                    "machine-parseable executable anchors."
                )
            elif _plan_tasks_missing_code(gate_content):
                issues.append(
                    "PLAN has a 'TDD Applicable: yes' task with no fenced code block; "
                    "add a Skeleton code block (standard tier requires executable anchors)."
                )

        # Check 5b (PLAN): trace closure — all upstream SPEC/RISK/SCOPE-IN IDs must be consumed.
        if stage == Stage.PLAN:
            from tools.workflow_cli.trace import check_trace_closure, scope_out_violations
            issues.extend(check_trace_closure(run_dir))
            for sid in scope_out_violations(run_dir):
                issues.append(f"PLAN references out-of-scope item {sid}; scope overflow (R8).")
            # R5.1: required fields + contiguous numbering
            issues.extend(_check_plan_task_fields(gate_content))
            # R5.2: dangling SPEC references
            issues.extend(_check_spec_refs_valid(run_dir, gate_content))
            # R5.2b: Skeleton is fenced, so detect template placeholders there explicitly.
            issues.extend(_check_plan_task_skeleton_placeholders(gate_content))
            # R5.3: file refs vs Context Pack repo_root
            issues.extend(_check_plan_file_refs(run_dir, gate_content))

        # Check 6 (SPEC): the External Documentation Checked section must be present and non-empty.
        if stage == Stage.SPEC:
            if not _has_external_docs_inventory(gate_content):
                issues.append(
                    "SPEC is missing a non-empty '## External Documentation Checked' section. "
                    "Add it; if there are no external dependencies, include an explicit "
                    "'N/A — no external dependencies' row."
                )

        # Check 7 (R2): tier-aware required-section schema.
        if not issues:
            issues.extend(_check_stage_schema(stage, tier, gate_content))

        # Check 8 (R8): scope-freeze — In/Out-of-Scope entries must carry stable IDs.
        issues.extend(_check_scope_freeze(stage, gate_content))

        # Check 9 (R8): elicitation — standard-tier brief must record at least one assumption or open question.
        issues.extend(_check_elicitation(stage, tier, gate_content))

        # Check 10 (R12): standard DESIGN must resolve decision requests.
        issues.extend(_check_decision_requests(stage, tier, gate_content))

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
            f"Run a review subagent and write its findings to {subagent_file} "
            f"(the filename must match {subagent_file.name!r}), then retry checkpoint approval."
        ],
        exit_code=5,
    )

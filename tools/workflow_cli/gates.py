"""
Tier-aware structured gate checks for the req-to-plan workflow CLI.

The CLI runs these structural checks before checkpoint approval.
The Agent handles semantic quality; this module handles structural validation.
"""
from __future__ import annotations

import errno
import os
import re
import stat
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
    plan_task_anchors,
    PLAN_TASK_ANCHOR_RE as _PLAN_TASK_RE,
    strip_readonly_sections,
    unfenced_markdown_lines,
    unfenced_markdown_text,
)
from tools.workflow_cli.output import EXIT_CONFLICT, EXIT_GATE_FAIL
from tools.workflow_cli.stage_schema import PLAN_TASK_FIELD_RE, PLAN_TASK_FIELDS

# ---------------------------------------------------------------------------
# GateResult
# ---------------------------------------------------------------------------

@dataclass
class GateResult:
    passed: bool
    issues: list[str]
    # 0=pass, 2=input failure, 3=gate failure, 5=forced review required, 6=unsafe conflict
    exit_code: int = 0


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

_FILL_IN_PLACEHOLDER_RE = re.compile(r"<!--\s*fill in(?:\s*:.*?)?\s*-->", re.IGNORECASE)

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
    re.compile(r"\?{3,}"),                                  # ??? unresolved marker
    re.compile(r"待定"),                                     # zh: undecided / pending
    re.compile(r"(?i)\bto be (?:decided|determined)\b"),    # english placeholder phrase
]

# High-signal "agent-introduced deferral" phrases (R20). A decomposition stage
# (04–07) must not invent a new "do-later / not-this-round" decision; exclusions
# are declared once, in the brief's Out-of-Scope (SCOPE-OUT-*), and may only be
# *cited* downstream. Structured closures — RISK "Status: deferred" and the
# "[DEFERRED]" tag — are intentionally NOT matched (they are legitimate,
# brief-anchored closures, not free-text deferral). Patterns stay high-precision
# (whole phrases, not the bare words "later"/"future"/"后续") to avoid flagging
# ordinary prose. A hit is allowed only when the same line cites a SCOPE-OUT-* ID.
#
# The defer VERB rule requires its target to be one of these project-planning
# buckets. This is deliberate: a broad "defer X to/until Y" flagged common
# runtime prose ("defer validation until submit", "defer loading until idle").
# The tradeoff is a narrow, documented residual — a real deferral to a non-bucket
# target ("defer PDF export to Q3 / to the redesign") is not caught here; those
# are plainly visible to the human checkpoint. Do not widen this back to an open
# target without reintroducing the runtime-prose false positives.
_PROJECT_DEFERRAL_TARGET = (
    r"(?:(?:a|the)\s+)?(?:(?:later|future|next|subsequent)\s+"
    r"(?:phase|iteration|round|milestone|sprint|release|task|ticket|story)|"
    r"follow[- ]?up\s+(?:phase|iteration|round|milestone|sprint|release|task|ticket|story)|"
    r"(?:stakeholder|product|business|human)\s+approval|"
    r"backlog)"
)
_BARE_PROJECT_PHASE_RE = re.compile(
    r"(?i)\b(?:later|future|next|subsequent)\s+"
    r"(?:phase|iteration|round|milestone|sprint)\b"
)
_DEFERRAL_PATTERNS = [
    re.compile(r"本轮(?:先)?不(?:做|实现|处理|支持|涉及)"),
    re.compile(r"暂不(?:做|实现|处理|支持|考虑|涉及)"),
    re.compile(r"不在(?:本轮|当前|本次)范围(?:内)?"),
    re.compile(r"延后(?:到|实现|处理|再)"),
    re.compile(r"后续(?:迭代|阶段|再做|再实现|再处理|再支持)"),
    re.compile(r"后续版本(?:中|里)?(?:再)?(?:做|实现|处理|支持)"),
    re.compile(r"(?:留|放|挪|推迟|延期|安排)到(?:以后|后续|下一?期|下个迭代|下一版|下一阶段)"),
    re.compile(r"(?:下一?期|下个迭代|下一版|下一阶段)(?:再|才)(?:做|实现|处理|支持|考虑)"),
    re.compile(r"以后再(?:做|实现|处理|说)"),
    # Deferral is the VERB (defer/defers/deferring) and the target is plainly a
    # project-planning bucket. "deferred" is excluded here so the common adjectival
    # sense ("deferred rendering/execution/tax ... to ...") is not caught by the window.
    re.compile(
        r"(?i)\b(?:defer|defers|deferring)\b"
        r"(?:\s+(?!(?:to|until)\b)[^\s,.;:]+){0,8}\s+(?:to|until)\s+"
        + _PROJECT_DEFERRAL_TARGET
    ),
    # "deferred to/until" adjacent only (deferral sense; e.g. "deferred to next sprint").
    re.compile(r"(?i)\bdeferred\s+(?:to|until)\b"),
    re.compile(r"(?i)\bdo\s+(?:it\s+|this\s+|that\s+)?later\b"),
    # "phase/iteration/round/milestone/sprint" denote project-planning deferral;
    # "version/release" are omitted — they collide with external-dependency prose,
    # and explicit "defer to a later release" is already caught by the defer rule.
    _BARE_PROJECT_PHASE_RE,
    re.compile(r"(?i)\bfuture\s+work\b"),
    # "not this <planning-noun>" only. The 'current'/'the current' variants are
    # deliberately NOT matched here — "the current phase/scope/round" is an
    # extremely common plain noun phrase ("not affect the current phase", "the
    # current round trip"); deferrals against the current unit go through the
    # "out of / not in (this|the current) ..." rule below instead.
    re.compile(r"(?i)\bnot\s+this\s+(?:round|scope|iteration|phase|release)\b"),
    # "not <impl/deliver verb> ... this/current <planning-noun>" (e.g. "not
    # implement PDF export this round") is an explicit deferral even when the
    # planning phrase is not adjacent to "not". Require the verb (not any {1,8}
    # words) so descriptive prose ("does not affect the current phase") is safe.
    re.compile(
        r"(?i)\bnot\s+"
        r"(?:implement|implemented|build|built|add|added|create|created|"
        r"develop|developed|deliver|delivered|do|done|handle|handled|support|supported|"
        r"cover|covered|include|included|address|addressed|ship|shipped|tackle|tackled)\b"
        r"(?:\s+(?!(?:this|the\s+current|current)\b)[^\s,.;:]+){0,6}\s+(?:in\s+)?"
        r"(?:this|(?:the\s+)?current)\s+(?:round|scope|iteration|phase|release)\b"
    ),
    re.compile(r"(?i)\b(?:out of|not in)\s+(?:this|(?:the\s+)?current)\s+(?:round|scope|iteration|phase|release)\b"),
    re.compile(r"(?i)\bpunt(?:ed|ing|s)?\s+(?:on|to)\b"),
]

# The brief-anchored exclusion citation that turns a deferral line from
# "agent-introduced" into "carries a human-approved exclusion ID". The same
# citation is also allowed downstream when the line is plainly preserving an
# exclusion/non-goal declaration rather than implementing it. The cited ID only
# anchors the line if the brief actually declares it (see R20 check).
_SCOPE_OUT_CITE_RE = re.compile(r"\bSCOPE-OUT-\d+\b")
_SCOPE_OUT_EXCLUSION_CONTEXT_PATTERNS = [
    re.compile(r"(?i)\bexclud(?:e|ed|es|ing|sion)\b"),
    re.compile(r"(?i)\bout[- ]of[- ]scope\b"),
    re.compile(r"(?i)\bnot\s+in\s+scope\b"),
    re.compile(r"(?i)\bnon[- ]goals?\b"),
    re.compile(r"(?:排除|范围外|不在(?:本轮|当前)?范围|非目标)"),
]
_SCOPE_OUT_NON_IMPLEMENTATION_CONTEXT_PATTERNS = [
    re.compile(
        r"(?i)\b(?:do|does|did|will|would|should|must|can|could|shall)\s+"
        r"not\s+(?:implement|build|add|create|develop|deliver|enable|support)\b"
    ),
    re.compile(
        r"(?i)\b(?:don't|doesn't|didn't|won't|can't|cannot|never)\s+"
        r"(?:implement|build|add|create|develop|deliver|enable|support)\b"
    ),
    re.compile(
        r"(?i)\bnot\s+(?:implemented|built|added|created|developed|delivered|enabled|supported)\b"
    ),
    re.compile(r"(?:不(?:实现|开发|构建|加入|支持|启用)|无需(?:实现|开发|构建|加入|支持|启用))"),
]
_SCOPE_OUT_IMPLEMENTATION_ACTION_RE = re.compile(
    r"(?i)\b(?:implement|implements|implementing|build|builds|building|"
    r"add|adds|adding|create|creates|creating|develop|develops|developing|"
    r"deliver|delivers|delivering|enable|enables|enabling|support|supports|supporting)\b"
)
_SCOPE_OUT_IMPLEMENTATION_NEGATION_PREFIX_RE = re.compile(
    r"(?i)(?:\b(?:do|does|did|will|would|should|must|can|could|shall)\s+not\s+|"
    r"\b(?:don't|doesn't|didn't|won't|can't|cannot|never|not|without)\s+)$"
)
_SCOPE_OUT_COORDINATED_NEGATION_PREFIX_RE = re.compile(
    r"(?i)(?:\b(?:do|does|did|will|would|should|must|can|could|shall)\s+not\s+|"
    r"\b(?:don't|doesn't|didn't|won't|can't|cannot|never|without)\s+|"
    r"\bnot\s+(?!(?:only|just|merely|necessarily)\b))"
    r"(?:(?!\b(?:but|however)\b)[^.;!?。；！？])*"
    r"\b(?:implement|implements|implementing|build|builds|building|"
    r"add|adds|adding|create|creates|creating|develop|develops|developing|"
    r"deliver|delivers|delivering|enable|enables|enabling|support|supports|supporting)\b"
    r"(?:(?!\b(?:but|however)\b)[^.;!?。；！？])*"
    r"\b(?:and|or|nor)\s+$"
)
_SCOPE_OUT_CHINESE_IMPLEMENTATION_ACTION_RE = re.compile(r"(?:实现|开发|构建|加入|支持|启用)")
_SCOPE_OUT_CLAUSE_BOUNDARY_RE = re.compile(r"[.;!?。；！？]")
_SCOPE_OUT_LOCAL_CONTEXT_BOUNDARY_RE = re.compile(
    r"(?i)\b(?:with|while|whereas|but|however|although|though|except|unless)\b"
)
_SCOPE_OUT_COMMA_CONTEXT_BOUNDARY_RE = re.compile(r"[,，]\s*")
_SCOPE_OUT_CONTEXT_TAIL_BOUNDARY_RE = re.compile(
    r"(?i)(?:[,，]|\b(?:with|while|whereas|but|however|although|though|except|unless)\b)"
)
_SCOPE_OUT_COORDINATING_CONTEXT_BOUNDARY_RE = re.compile(r"(?i)\band\b")
_DEFERRAL_CONTEXT_TAIL_BOUNDARY_RE = re.compile(
    r"(?i)(?:[,，]|\b(?:and|with|while|whereas|but|however|although|though|except|unless)\b)"
)
_SCOPE_OUT_CHINESE_IMPLEMENTATION_NEGATION_PREFIX_RE = re.compile(r"(?:不|无需|不需要|不用)\s*$")
_HANDOFF_HEADING_RE = re.compile(r"(?i)^#{1,6}\s+.*\bhandoff\b")
_HANDOFF_PHASE_PROSE_RE = re.compile(
    r"(?i)\b(?:the\s+)?(?:later|next|subsequent|following)\s+"
    r"(?:phase|stage)\s+"
    r"(?:should|must|will|can|needs?\s+to)\s+"
    r"(?:specify|define|document|describe|detail|cover|map|produce|"
    r"translate|carry)\b"
)

# HTML comments carry template guidance, not agent prose; strip them (DOTALL, so
# multi-line comments are dropped whole) before scanning.
_HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
_STRUCTURED_DEFERRED_STATUS_RE = re.compile(r"(?i)^\s*Status:\s*deferred\b")

_LEGACY_PLAN_DEFERRAL_FIELD_RE = re.compile(
    r"^[ \t]{0,3}(Out-of-Task|Future Task Ownership):"
)


def _deferral_matches(
    line: str, *, allow_structured_deferred_status: bool = False
) -> list[re.Match]:
    if allow_structured_deferred_status and _STRUCTURED_DEFERRED_STATUS_RE.match(line):
        return []
    matches: list[re.Match] = []
    for pat in _DEFERRAL_PATTERNS:
        matches.extend(pat.finditer(line))
    unique_matches: list[re.Match] = []
    seen_spans: set[tuple[int, int]] = set()
    for match in sorted(matches, key=lambda m: (m.start(), m.end())):
        span = match.span()
        if span in seen_spans:
            continue
        seen_spans.add(span)
        unique_matches.append(match)
    return unique_matches


def _deferral_match(line: str, *, allow_structured_deferred_status: bool = False):
    matches = _deferral_matches(
        line, allow_structured_deferred_status=allow_structured_deferred_status
    )
    return matches[0] if matches else None


def _scope_out_citation_is_anchored(
    line: str, scope_out_id: str, valid_scope_out: set[str]
) -> bool:
    decommented = _HTML_COMMENT_RE.sub("", line)
    if scope_out_id not in valid_scope_out:
        return False
    if scope_out_id not in set(_SCOPE_OUT_CITE_RE.findall(decommented)):
        return False
    contexts = _scope_out_citation_contexts(decommented, scope_out_id)
    if any(_scope_out_context_requests_implementation(context) for context in contexts):
        return False
    return any(
        _scope_out_context_is_anchoring(context) for context in contexts
    )


def _scope_out_citation_contexts(line: str, scope_out_id: str) -> list[str]:
    contexts: list[str] = []
    for segment in _SCOPE_OUT_CLAUSE_BOUNDARY_RE.split(line):
        search_from = 0
        while True:
            id_start = segment.find(scope_out_id, search_from)
            if id_start < 0:
                break
            id_end = id_start + len(scope_out_id)
            context_start = 0
            for boundary in _SCOPE_OUT_LOCAL_CONTEXT_BOUNDARY_RE.finditer(segment, 0, id_start):
                context_start = boundary.end()
            for boundary in _SCOPE_OUT_COMMA_CONTEXT_BOUNDARY_RE.finditer(
                segment, context_start, id_start
            ):
                candidate = segment[boundary.end():]
                if _scope_out_context_can_start_after_comma(candidate):
                    context_start = boundary.end()
            for boundary in _SCOPE_OUT_COORDINATING_CONTEXT_BOUNDARY_RE.finditer(
                segment, context_start, id_start
            ):
                candidate = segment[boundary.end():]
                if _scope_out_context_is_anchoring(candidate):
                    context_start = boundary.end()
            context_end = len(segment)
            boundary_after = _SCOPE_OUT_CONTEXT_TAIL_BOUNDARY_RE.search(segment, id_end)
            if boundary_after:
                context_end = boundary_after.start()
            contexts.append(segment[context_start:context_end].strip())
            search_from = id_end
    return contexts


def _scope_out_context_can_start_after_comma(candidate: str) -> bool:
    if not _scope_out_context_is_anchoring(candidate):
        return False
    anchor_start = _scope_out_anchor_start(candidate)
    if anchor_start is None:
        return False
    return bool(candidate[:anchor_start].strip())


def _scope_out_anchor_start(context: str) -> int | None:
    starts: list[int] = []
    if match := _deferral_match(context):
        starts.append(match.start())
    for pat in (
        *_SCOPE_OUT_EXCLUSION_CONTEXT_PATTERNS,
        *_SCOPE_OUT_NON_IMPLEMENTATION_CONTEXT_PATTERNS,
    ):
        if match := pat.search(context):
            starts.append(match.start())
    return min(starts) if starts else None


def _scope_out_context_is_anchoring(context: str) -> bool:
    if _deferral_match(context) is not None:
        return True
    return any(
        pat.search(context)
        for pat in (
            *_SCOPE_OUT_EXCLUSION_CONTEXT_PATTERNS,
            *_SCOPE_OUT_NON_IMPLEMENTATION_CONTEXT_PATTERNS,
        )
    )


def _scope_out_context_requests_implementation(context: str) -> bool:
    if _deferral_match(context) is not None:
        return False
    for match in _SCOPE_OUT_IMPLEMENTATION_ACTION_RE.finditer(context):
        prefix = context[:match.start()]
        prefix_window = prefix[-160:]
        if (
            _SCOPE_OUT_IMPLEMENTATION_NEGATION_PREFIX_RE.search(prefix_window)
            or _SCOPE_OUT_COORDINATED_NEGATION_PREFIX_RE.search(prefix_window)
        ):
            continue
        return True
    for match in _SCOPE_OUT_CHINESE_IMPLEMENTATION_ACTION_RE.finditer(context):
        prefix_window = context[max(0, match.start() - 12):match.start()]
        if _SCOPE_OUT_CHINESE_IMPLEMENTATION_NEGATION_PREFIX_RE.search(prefix_window):
            continue
        return True
    return False


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


def _python_executable() -> str:
    import shutil
    import sys
    if sys.executable:
        return sys.executable
    return "python3" if shutil.which("python3") else "python"


def _context_pack_remediation_command(run_dir: Path) -> str:
    import shlex
    package_root = Path(__file__).resolve().parents[2]
    pythonpath = f"PYTHONPATH={shlex.quote(str(package_root))}${{PYTHONPATH:+:$PYTHONPATH}}"
    command = (
        f"{pythonpath} {shlex.quote(_python_executable())} -m tools.workflow_cli "
        f"context-build --work-id {run_dir.name}"
    )
    if run_dir.parent.name == ".req-to-plan":
        base_dir = run_dir.parent.parent
        try:
            command += f" --base-path {shlex.quote(str(base_dir.resolve()))}"
        except (OSError, RuntimeError):
            # Path resolution failed (for example, a symlink loop).
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
    must target paths that do not exist yet (R19); the part after '::' (a symbol) is
    advisory and not checked (no AST pack yet)."""
    repo_root = _context_pack_repo_root(run_dir)
    if repo_root is None:
        return []  # no usable ground truth; standard tier blocks via _check_plan_context_pack
    issues: list[str] = []
    for body in _iter_plan_task_bodies(content):
        is_create = _normalized_change_type(_task_change_type(body)) == "create"
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
                if not is_create:
                    issues.append(
                        f"PLAN-TASK Files references missing path {path_part!r} "
                        "(mark the task 'Change Type: create' if it is a new file)."
                    )
            elif is_create:
                # R19: create must not silently mean "overwrite an existing file".
                issues.append(
                    f"PLAN-TASK Files references path {path_part!r} that already exists "
                    "under 'Change Type: create'; use 'modify' for existing files or "
                    "split the task."
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
_FILE_CHANGE_TYPES = frozenset({"create", "modify", "delete"})
_CHANGE_TYPE_VALUES = _FILE_CHANGE_TYPES | {"non_code"}
_CHANGE_TYPE_ALIASES = {"new": "create"}
_TDD_APPLICABLE_VALUES = frozenset({"yes", "no"})


def _normalized_change_type(raw: str) -> str:
    value = raw.strip().lower()
    return _CHANGE_TYPE_ALIASES.get(value, value)


def _task_change_type(body: str) -> str:
    """Whitespace-normalized Change Type field body (same line + continuation lines)."""
    return " ".join(_plan_task_field_body(body, "Change Type").split())


def _task_tdd_applicable(body: str) -> str:
    """Whitespace-normalized TDD Applicable field body (same line + continuation lines)."""
    return " ".join(_plan_task_field_body(body, "TDD Applicable").split())


def _check_plan_task_fields(content: str) -> list[str]:
    issues: list[str] = []
    numbers: list[int] = []
    for body in _iter_plan_task_bodies(content):
        m = re.match(r"###\s+PLAN-TASK-(\d+)", body)
        num = int(m.group(1)) if m else None
        if num is not None:
            numbers.append(num)
        label = _plan_task_label(body)
        for line, _, _ in unfenced_markdown_lines(body):
            legacy = _LEGACY_PLAN_DEFERRAL_FIELD_RE.match(line)
            if legacy:
                issues.append(
                    f"{label} uses legacy deferral field '{legacy.group(1)}:'; "
                    "PLAN-TASKs may not push scoped work to a later task. Remove "
                    "the field and implement the work in this run, or declare the "
                    "exclusion in the brief's '## Out-of-Scope' and cite its "
                    "SCOPE-OUT-* ID."
                )
        for field in PLAN_TASK_FIELDS:
            if not _plan_task_field_body(body, field).strip():
                issues.append(f"{label} is missing a non-empty '{field}:' field.")
        raw_change_type = _task_change_type(body)
        change_type = _normalized_change_type(raw_change_type)
        if raw_change_type and change_type not in _CHANGE_TYPE_VALUES:
            issues.append(
                f"{label} has invalid 'Change Type: {raw_change_type}'; "
                "allowed: create|modify|delete|non_code (alias: new = create)."
            )
        # R16: Change Type and Files must agree — file-op types need a real
        # path; non_code is the only legal shape for no-file tasks.
        files_body = _plan_task_field_body(body, "Files")
        if files_body.strip():
            file_paths = _plan_task_file_paths(files_body)
            if change_type in _FILE_CHANGE_TYPES and not file_paths:
                issues.append(
                    f"{label} has 'Change Type: {raw_change_type}' but 'Files:' lists "
                    "no real file path; use 'Change Type: non_code' for tasks that "
                    "touch no files."
                )
            elif change_type == "non_code" and file_paths:
                issues.append(
                    f"{label} has 'Change Type: non_code' but 'Files:' lists a file path; "
                    "use create|modify|delete for file-touching tasks."
                )
        raw_tdd = _task_tdd_applicable(body)
        if raw_tdd and raw_tdd.lower() not in _TDD_APPLICABLE_VALUES:
            issues.append(
                f"{label} has invalid 'TDD Applicable: {raw_tdd}'; allowed: yes|no."
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
        if _task_tdd_applicable(body).lower() == "yes" and not _has_complete_code_fence(skeleton):
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


def _check_plan_task_verification_placeholders(content: str) -> list[str]:
    issues: list[str] = []
    for body in _iter_plan_task_bodies(content):
        verification = _plan_task_field_body(body, "Verification")
        if verification.strip() and any(p.search(verification) for p in _PLACEHOLDER_PATTERNS):
            issues.append(
                f"{_plan_task_label(body)} Verification contains an unresolved "
                "placeholder; replace it with an objective pass/fail check "
                "(command + expected result) before passing the gate."
            )
    return issues


def _section_bodies(content: str, heading: str) -> list[str]:
    """Return all bodies under `heading`, each stopping at the next same-or-higher heading."""
    level = len(heading) - len(heading.lstrip("#"))
    bodies: list[str] = []
    out: list[str] | None = None
    for line, _, _ in unfenced_markdown_lines(content):
        if line.strip() == heading:
            if out is not None:
                bodies.append("\n".join(out))
            out = []
            continue
        if out is not None:
            stripped = line.lstrip()
            if stripped.startswith("#"):
                # Count hashes of this line's heading
                line_level = len(stripped) - len(stripped.lstrip("#"))
                if line_level <= level:
                    bodies.append("\n".join(out))
                    out = None
                    continue
            out.append(line.rstrip("\r\n"))
    if out is not None:
        bodies.append("\n".join(out))
    return bodies


def _section_body(content: str, heading: str) -> str:
    """Return the first section body under `heading`, stopping at the next same-or-higher heading."""
    bodies = _section_bodies(content, heading)
    return bodies[0] if bodies else ""


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


def _section_non_bullet_scope_entries(content: str, heading: str, id_prefix: str) -> list[str]:
    entries: list[str] = []
    pattern = re.compile(rf"\b{re.escape(id_prefix)}-\d+\b")
    for line in _section_body(content, heading).splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("<!--"):
            continue
        if stripped.startswith(("- ", "* ")):
            continue
        if pattern.search(stripped):
            entries.append(stripped)
    return entries


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
_DECISION_NESTED_MARKER_RE = re.compile(
    r"^(?:#{1,6}\s+|[-*]\s+(?:\[[ xX]\]\s+)?|(?:\[[ xX]\]\s+)?)DECISION-\d+\b"
)
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
    blocks: list[tuple[str, list[str]]] = []
    stray: list[str] = []
    for section_body in _section_bodies(content, _DECISION_SECTION):
        lines = section_body.splitlines()
        starts = [
            (i, m)
            for i, line in enumerate(lines)
            if (m := _DECISION_BLOCK_RE.match(line.strip()))
        ]
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
        stray.extend(
            line.strip()
            for i, line in enumerate(lines)
            if i not in covered and line.strip() and not line.strip().startswith("<!--")
        )

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
    scope_content = _HTML_COMMENT_RE.sub("", content)
    in_scope_ids = _section_entry_ids(scope_content, "## In-Scope", "SCOPE-IN")
    out_scope_ids = _section_entry_ids(scope_content, "## Out-of-Scope", "SCOPE-OUT")
    for entry in _section_entries_missing_id(scope_content, "## In-Scope", "SCOPE-IN"):
        issues.append(f"In-Scope entry must carry a SCOPE-IN-* stable ID (R8): {entry}")
    for entry in _section_entries_missing_id(scope_content, "## Out-of-Scope", "SCOPE-OUT"):
        issues.append(f"Out-of-Scope entry must carry a SCOPE-OUT-* stable ID (R8): {entry}")
    for entry in _section_non_bullet_scope_entries(scope_content, "## In-Scope", "SCOPE-IN"):
        issues.append(
            "In-Scope stable IDs must be declared as '- ' or '* ' bullet entries "
            f"so trace can anchor them (R8): {entry}"
        )
    for entry in _section_non_bullet_scope_entries(scope_content, "## Out-of-Scope", "SCOPE-OUT"):
        issues.append(
            "Out-of-Scope stable IDs must be declared as '- ' or '* ' bullet entries "
            f"so trace can anchor them (R8): {entry}"
        )
    for id_, count in Counter(in_scope_ids).items():
        if count > 1:
            issues.append(f"In-Scope stable ID {id_} is duplicate; scope IDs must be unique (R8).")
    for id_, count in Counter(out_scope_ids).items():
        if count > 1:
            issues.append(f"Out-of-Scope stable ID {id_} is duplicate; scope IDs must be unique (R8).")
    if not in_scope_ids:
        issues.append("In-Scope must list at least one stable-ID entry (SCOPE-IN-001, ...); none found (R8).")
    if not out_scope_ids:
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


# Decomposition stages where new exclusions may not be introduced (R20). The
# brief (03) is the authoritative place to declare them, so it is not scanned.
_DEFERRAL_SCANNED_STAGES = frozenset({
    Stage.RISK_DISCOVERY, Stage.DESIGN, Stage.SPEC, Stage.PLAN,
})


def _check_unanchored_deferral(
    stage: Stage, content: str, valid_scope_out: set[str]
) -> list[str]:
    """R20: a decomposition stage (04–07) must not introduce a new
    "do-later / not-this-round" decision. Everything the requirement brief puts
    in scope must be implemented this run; the only things that may be skipped
    or deferred are the exclusions the brief itself declares in '## Out-of-Scope'
    (`valid_scope_out`). A high-signal deferral phrase in a scanned stage is a
    defect unless the matched deferral clause cites one of those brief-declared
    SCOPE-OUT-* IDs — citing an id the brief never declared does not anchor it. Fenced
    code and HTML comments (incl. multi-line) are not scanned; structured
    closures (RISK 'Status: deferred', '[DEFERRED]') do not match the phrase set."""
    if stage not in _DEFERRAL_SCANNED_STAGES:
        return []
    decommented = _HTML_COMMENT_RE.sub("", content)
    issues: list[str] = []
    in_handoff_section = False
    handoff_level = 0
    for line, _, _ in unfenced_markdown_lines(decommented):
        level = heading_level(line)
        if level is not None:
            if _HANDOFF_HEADING_RE.match(line.strip()) is not None:
                in_handoff_section, handoff_level = True, level
            elif in_handoff_section and level <= handoff_level:
                # A sibling/higher heading closes the handoff section; a deeper
                # subheading (level > handoff_level) stays inside it.
                in_handoff_section = False
        for clause in _SCOPE_OUT_CLAUSE_BOUNDARY_RE.split(line):
            inspected_contexts: set[str] = set()
            for match in _deferral_matches(
                clause,
                allow_structured_deferred_status=(stage == Stage.RISK_DISCOVERY),
            ):
                if in_handoff_section and _deferral_match_is_handoff_prose(line, match):
                    continue
                context = _deferral_match_context(clause, match)
                if context in inspected_contexts:
                    continue
                inspected_contexts.add(context)
                if _deferral_match_is_scope_out_anchored(clause, match, valid_scope_out):
                    continue
                issues.append(
                    f"Unanchored deferral {match.group(0)!r} (R20): a decomposition stage may "
                    "not defer or drop requirement content. Implement it this run, or declare the "
                    "exclusion in the brief's '## Out-of-Scope' (SCOPE-OUT-*) and cite that ID here."
                )
    return issues


def _deferral_match_is_handoff_prose(line: str, match: re.Match) -> bool:
    return (
        _BARE_PROJECT_PHASE_RE.fullmatch(match.group(0)) is not None
        and _HANDOFF_PHASE_PROSE_RE.search(line) is not None
    )


def _deferral_match_is_scope_out_anchored(
    clause: str, match: re.Match, valid_scope_out: set[str]
) -> bool:
    # Known residual (semantic, by design): a single deferral verb with a
    # coordinated object mixing an in-scope and an out-of-scope item — e.g.
    # "defer retries and PDF export to a later phase per SCOPE-OUT-001" — is
    # exempted as a whole, so the in-scope "retries" deferral slips through. The
    # gate cannot tell that "retries" is not part of what SCOPE-OUT-001 excludes;
    # that is the coarse-SCOPE-OUT semantic gap the human checkpoint backstops.
    # Separate deferral verbs and separate clauses ARE anchored individually.
    context = _deferral_match_context(clause, match)
    for scope_out_id in set(_SCOPE_OUT_CITE_RE.findall(context)) & valid_scope_out:
        if _scope_out_citation_is_anchored(context, scope_out_id, valid_scope_out):
            return True
    return False


def _deferral_match_context(clause: str, match: re.Match) -> str:
    context_start = 0
    for boundary in _DEFERRAL_CONTEXT_TAIL_BOUNDARY_RE.finditer(clause, 0, match.start()):
        context_start = boundary.end()
    context_end = len(clause)
    search_from = match.end()
    while True:
        boundary_after = _DEFERRAL_CONTEXT_TAIL_BOUNDARY_RE.search(clause, search_from)
        if not boundary_after:
            break
        if _deferral_tail_boundary_starts_new_context(clause, boundary_after):
            context_end = boundary_after.start()
            break
        search_from = boundary_after.end()
    return clause[context_start:context_end].strip()


def _deferral_tail_boundary_starts_new_context(clause: str, boundary: re.Match) -> bool:
    if boundary.group(0) not in {",", "，"}:
        return True
    next_boundary = _DEFERRAL_CONTEXT_TAIL_BOUNDARY_RE.search(clause, boundary.end())
    segment_end = next_boundary.start() if next_boundary else len(clause)
    return _deferral_match(clause[boundary.end():segment_end]) is not None


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
            from tools.workflow_cli.trace import (
                check_trace_closure,
                defined_scope_out_ids,
                scope_out_violations,
            )
            valid_scope_out = defined_scope_out_ids(run_dir)
            issues.extend(check_trace_closure(run_dir))
            for sid in scope_out_violations(
                run_dir,
                plan_task_scope_out_allowed=lambda line, sid: (
                    _scope_out_citation_is_anchored(line, sid, valid_scope_out)
                ),
                consumed_spec_scope_out_allowed=lambda line, sid: (
                    _scope_out_citation_is_anchored(line, sid, valid_scope_out)
                ),
            ):
                issues.append(f"PLAN references out-of-scope item {sid}; scope overflow (R8).")
            # R5.1: required fields + contiguous numbering
            issues.extend(_check_plan_task_fields(gate_content))
            # R5.2: dangling SPEC references
            issues.extend(_check_spec_refs_valid(run_dir, gate_content))
            # R5.2b: Skeleton is fenced, so detect template placeholders there explicitly.
            issues.extend(_check_plan_task_skeleton_placeholders(gate_content))
            # R5.2c: Verification must be an objective check, not a placeholder.
            issues.extend(_check_plan_task_verification_placeholders(gate_content))
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

        # Check 11 (R20): decomposition stages (04–07) may not introduce a new
        # "do-later/not-this-round" decision; the only exclusions they may cite are
        # the ones the brief actually declares in its Out-of-Scope section.
        if stage in _DEFERRAL_SCANNED_STAGES:
            from tools.workflow_cli.trace import defined_scope_out_ids
            issues.extend(
                _check_unanchored_deferral(stage, gate_content, defined_scope_out_ids(run_dir))
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

    # Condition 4: a real, version-matched subagent review must exist. Read the
    # file without following symlinks so a symlinked reviews/ directory (or a
    # symlinked review file) cannot satisfy this forced-review gate.
    stage_name = stage.value
    subagent_file = reviews_dir / f"{stage_name}-subagent-review-v{version}.md"
    _text, sf_err = _read_regular_text_no_symlink(subagent_file)
    if sf_err == "symlink":
        return GateResult(
            passed=False,
            issues=[
                "reviews/ is a symlink or the subagent review file is a symlink; "
                "refusing to read outside the run directory. "
                + _FINAL_REVIEW_DISCLAIMER
            ],
            exit_code=EXIT_CONFLICT,
        )
    if sf_err == "not_regular":
        return GateResult(
            passed=False,
            issues=[
                "Subagent review file is not a regular file. "
                + _FINAL_REVIEW_DISCLAIMER
            ],
            exit_code=EXIT_CONFLICT,
        )
    if sf_err is None:
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


# ---------------------------------------------------------------------------
# Final Review Presence Gate
# ---------------------------------------------------------------------------

_FINAL_REVIEW_DISCLAIMER = (
    "Presence check on the review audit trail — not a correctness guarantee."
)
_SUPPORTED_VERDICTS = {"approved", "changes requested"}

_CANONICAL_NOT_APPROVED_MSG = (
    "Final whole-branch review not approved: execution/final-review.md is missing, "
    "or its current (last unfenced) 'Verdict:' line is not 'Approved'. "
    + _FINAL_REVIEW_DISCLAIMER
    + " Record 'Verdict: Approved', or re-run with --force to archive an abandoned run."
)


def _fail_gate(msg: str) -> GateResult:
    return GateResult(passed=False, issues=[msg], exit_code=EXIT_GATE_FAIL)


def _current_verdict(text: str) -> str | None:
    """Return the last unfenced 'Verdict:' value (stripped, lowercased), or None."""
    value = None
    for line, _, _ in unfenced_markdown_lines(text):
        s = line.strip()
        if s[:8].lower() == "verdict:":
            value = s[8:].strip().lower()  # last one wins
    return value


def _has_verdict(text: str) -> bool:
    return _current_verdict(text) is not None


def check_final_review_recorded(run_dir: Path) -> GateResult:
    """Archive precondition: the final whole-branch review verdict is recorded.

    Presence/audit only — never runs code or tests, never asserts the verdict is
    true. Same trust level as the PLAN-TASK checkbox gate.
    """
    marker = run_dir / "execution" / "final-review.md"
    text, err = _read_regular_text_no_symlink(marker)

    if err == "missing":
        return _fail_gate(_CANONICAL_NOT_APPROVED_MSG)

    if err == "symlink":
        return _fail_gate(
            "execution/final-review.md is a symlink; refusing to read "
            "outside the run directory. " + _FINAL_REVIEW_DISCLAIMER
        )

    if err == "not_regular":
        return _fail_gate(
            "execution/final-review.md is not a regular file. "
            + _FINAL_REVIEW_DISCLAIMER
        )

    assert text is not None

    if not _has_verdict(text):
        # Case d: regular file, zero unfenced Verdict: lines
        return _fail_gate(_CANONICAL_NOT_APPROVED_MSG)

    current = _current_verdict(text)  # last unfenced 'Verdict:' value, lowercased
    assert current is not None  # guarded by _has_verdict above

    if current not in _SUPPORTED_VERDICTS:
        return _fail_gate(
            "execution/final-review.md current 'Verdict:' value is unsupported. "
            + _FINAL_REVIEW_DISCLAIMER
        )

    if current == "changes requested":
        return _fail_gate(
            "Final whole-branch review not approved: current 'Verdict:' is "
            "'Changes Requested'. " + _FINAL_REVIEW_DISCLAIMER
        )

    # current == "approved"
    return GateResult(passed=True, issues=[], exit_code=0)


# ---------------------------------------------------------------------------
# Execution Completion Gate
# ---------------------------------------------------------------------------

_LEDGER_UNCHECKED_RE = re.compile(r"^\s*-\s*\[\s*\]\s*(PLAN-TASK-\d+)\b")
_LEDGER_CHECKED_RE = re.compile(r"^\s*-\s*\[[xX]\]\s*(PLAN-TASK-\d+)\b")


def _read_regular_text_no_symlink(path: Path) -> tuple[str | None, str | None]:
    """Read a regular file without following a symlink where the OS supports it."""
    if path.parent.is_symlink() or path.is_symlink():
        return None, "symlink"
    # O_NONBLOCK so opening a non-regular file (e.g. a writerless FIFO) returns
    # immediately and is rejected by the S_ISREG check below instead of blocking.
    # It has no effect on regular-file reads.
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    fd: int | None = None
    try:
        fd = os.open(path, flags)
        mode = os.fstat(fd).st_mode
        if not stat.S_ISREG(mode):
            return None, "not_regular"
        with os.fdopen(fd, "r", encoding="utf-8") as fh:
            fd = None
            return fh.read(), None
    except FileNotFoundError:
        return None, "missing"
    except OSError as exc:
        if exc.errno == errno.ELOOP:
            return None, "symlink"
        if exc.errno == errno.ENOTDIR:
            return None, "not_regular"
        raise
    finally:
        if fd is not None:
            os.close(fd)


def _plan_task_ids(run_dir: Path) -> list[str]:
    """Task IDs declared in the frozen PLAN artifact."""
    from tools.workflow_cli.artifact import read_artifact
    plan_text = read_artifact(run_dir, Stage.PLAN)
    return [tid for tid, _ in plan_task_anchors(strip_readonly_sections(plan_text))]


def check_execution_complete(run_dir: Path) -> GateResult:
    """Completion gate for archiving an EXECUTING run.

    The execution ledger (execution/progress.md, seeded by run-execute-start)
    is the structural evidence that every PLAN-TASK was implemented. Archiving
    an executing run requires the ledger to exist and report every task done:

    - missing ledger              -> fail (execution never recorded progress)
    - any `- [ ] PLAN-TASK-*`     -> fail (unfinished tasks remain)
    - a frozen PLAN task with no   -> fail (truncated ledger dropped a task line
      `- [x] PLAN-TASK-*` line             instead of completing it)
    - no `- [x] PLAN-TASK-*` at all -> fail (cleared/empty ledger asserts nothing)

    This is structural validation only: it trusts the agent's checkbox flips
    (an audit gate, not a correctness gate). The CLI offers --force to override.
    """
    ledger = run_dir / "execution" / "progress.md"
    ledger_text, ledger_error = _read_regular_text_no_symlink(ledger)
    if ledger_error == "missing":
        return GateResult(
            passed=False,
            issues=[
                "Execution ledger execution/progress.md is missing; cannot "
                "confirm the PLAN was executed."
            ],
            exit_code=EXIT_GATE_FAIL,
        )
    if ledger_error == "symlink":
        return GateResult(
            passed=False,
            issues=[
                "Execution ledger execution/progress.md is a symlink; refusing "
                "to read outside the run directory."
            ],
            exit_code=EXIT_GATE_FAIL,
        )
    if ledger_error == "not_regular":
        return GateResult(
            passed=False,
            issues=[
                "Execution ledger execution/progress.md is not a regular file; "
                "cannot confirm the PLAN was executed."
            ],
            exit_code=EXIT_GATE_FAIL,
        )
    assert ledger_text is not None
    lines = [line for line, _, _ in unfenced_markdown_lines(ledger_text)]
    issues: list[str] = []
    for line in lines:
        if _LEDGER_UNCHECKED_RE.match(line):
            issues.append(f"Unfinished execution task: {line.strip()}")
    if not issues:
        checked_ids = {m.group(1) for line in lines if (m := _LEDGER_CHECKED_RE.match(line))}
        # Cross-check the ledger against the frozen PLAN: every declared PLAN-TASK
        # must be checked off, so a truncated ledger (a dropped task line) cannot
        # pass as complete. Both inputs are CLI-owned artifacts; no new trust.
        try:
            plan_task_ids = _plan_task_ids(run_dir)
        except FileNotFoundError:
            issues.append(
                "Frozen PLAN artifact 07-plan.md is missing; cannot cross-check "
                "the execution ledger."
            )
        else:
            for tid in plan_task_ids:
                if tid not in checked_ids:
                    issues.append(
                        f"PLAN task {tid} is not marked complete in the execution ledger "
                        "(its '- [x] PLAN-TASK-*' line is missing)."
                    )
        if not issues and not checked_ids:
            issues.append(
                "Execution ledger lists no completed PLAN-TASK entries "
                "('- [x] PLAN-TASK-*'); nothing to confirm."
            )
    return GateResult(
        passed=len(issues) == 0,
        issues=issues,
        exit_code=EXIT_GATE_FAIL if issues else 0,
    )

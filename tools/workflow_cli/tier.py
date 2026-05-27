# tools/workflow_cli/tier.py
from __future__ import annotations
from pathlib import Path
from typing import Any
import re
import yaml

from tools.workflow_cli.models import (
    TierBase, TierModifier, TierEstimate, EvidenceBlock,
)
from tools.workflow_cli.repo_baseline import RepoBaseline
from tools.workflow_cli.link_expander import LinkExpansionResult, LinkStatus

_KEYWORDS_PATH = Path(__file__).parent / "tier_keywords.yaml"
_keywords_cache: dict | None = None


def _load_keywords() -> dict:
    global _keywords_cache
    if _keywords_cache is None:
        with open(_KEYWORDS_PATH, encoding="utf-8") as f:
            _keywords_cache = yaml.safe_load(f)
    return _keywords_cache


def _flatten_keywords(modifier_section: dict) -> list[str]:
    """Flatten all keyword lists from a modifier section into one list."""
    result = []
    for value in modifier_section.values():
        if isinstance(value, list):
            result.extend(str(k) for k in value)
        elif isinstance(value, dict):
            result.extend(_flatten_keywords(value))
    return result


def _normalize(text: str) -> str:
    """Normalize hyphens and lowercase."""
    return re.sub(r'[-\s]+', ' ', text.lower()).strip()


def _strip_hyphens(text: str) -> str:
    """Strip hyphens (and surrounding spaces) to produce a compact form for hyphen-variant matching."""
    return re.sub(r'\s*-\s*', '', text.lower())


def _match_keyword(keyword: str, text: str, normalized_text: str) -> bool:
    """Match a keyword against text. Multi-word phrases use substring; single words use word-boundary for English."""
    kw_norm = _normalize(keyword)
    # Chinese text: substring match
    if re.search(r'[一-鿿]', keyword):
        return keyword in text
    # Multi-word: substring match on normalized text
    if ' ' in kw_norm:
        return kw_norm in normalized_text
    # Single word: word boundary on normalized text
    if re.search(r'\b' + re.escape(kw_norm) + r'\b', normalized_text, re.IGNORECASE):
        return True
    # Hyphen-variant fallback: strip all hyphens from both keyword and text and try word boundary
    # This handles "reimplement" matching "re-implement" in the text
    kw_compact = _strip_hyphens(keyword)
    text_compact = _strip_hyphens(text)
    return bool(re.search(r'\b' + re.escape(kw_compact) + r'\b', text_compact, re.IGNORECASE))


def scan_keywords(text: str) -> dict[TierModifier, list[str]]:
    """L1: scan text for modifier-triggering keywords. Returns {modifier: [matched keywords]}."""
    keywords = _load_keywords()
    normalized = _normalize(text)
    hits: dict[TierModifier, list[str]] = {}

    modifier_map = {
        "migration": TierModifier.MIGRATION,
        "cross_project": TierModifier.CROSS_PROJECT,
        "safety": TierModifier.SAFETY,
        "dependency": TierModifier.DEPENDENCY,
        "scope_expanding": TierModifier.SCOPE_EXPANDING,
    }

    for section_name, modifier in modifier_map.items():
        section = keywords.get(section_name, {})
        section_keywords = _flatten_keywords(section)
        matched = [kw for kw in section_keywords if _match_keyword(kw, text, normalized)]
        if matched:
            hits[modifier] = matched

    return hits


def compute_floor(
    keyword_hits: dict[TierModifier, list[str]],
    repo: RepoBaseline,
    link_results: list[LinkExpansionResult],
    requirement_text: str = "",
) -> TierEstimate:
    """Compute tier Floor from L1-L3 signals."""
    # Base floor
    base = TierBase.LIGHT

    loc_threshold = 10_000
    module_threshold = 8

    if (
        len(keyword_hits) > 0
        or repo.loc > loc_threshold
        or repo.is_monorepo
        or repo.module_count > module_threshold
        or _has_multi_repo_refs(requirement_text)
        or any(r.status in (LinkStatus.UNREACHABLE, LinkStatus.REQUIRES_AUTH) for r in link_results)
    ):
        base = TierBase.STANDARD

    # Modifier floor
    modifiers: set[TierModifier] = set(keyword_hits.keys())

    # Repo signals → cross_project modifier
    if repo.cross_language_refs and len(repo.cross_language_refs) >= 2:
        modifiers.add(TierModifier.CROSS_PROJECT)

    # scope_expanding upgrades base to standard
    if TierModifier.SCOPE_EXPANDING in modifiers and base == TierBase.LIGHT:
        base = TierBase.STANDARD

    return TierEstimate(base=base, modifiers=frozenset(modifiers))


def _has_multi_repo_refs(text: str) -> bool:
    """Check if requirement text mentions 2+ distinct repo names."""
    repo_words = re.findall(r'\b(?:repo|repository|project)\s+\w+', text.lower())
    return len(set(repo_words)) >= 2


def build_evidence_block(
    keyword_hits: dict[TierModifier, list[str]],
    repo: RepoBaseline,
    link_results: list[LinkExpansionResult],
    floor: TierEstimate,
) -> EvidenceBlock:
    """Build the EvidenceBlock from all scan results."""
    all_hits = [kw for hits in keyword_hits.values() for kw in hits]

    repo_summary = (
        f"loc={repo.loc}, modules={repo.module_count}, "
        f"monorepo={repo.is_monorepo}, languages={list(repo.language_breakdown.keys())}"
    )

    linked_context_parts = []
    for r in link_results:
        if r.content_preview:
            linked_context_parts.append(f"{r.url}: {r.content_preview[:100]}")
    linked_context = "; ".join(linked_context_parts) if linked_context_parts else "none"

    scope_signals = list(keyword_hits.get(TierModifier.SCOPE_EXPANDING, []))
    escalation_candidates = [m.value for m in keyword_hits if m != TierModifier.SCOPE_EXPANDING]

    return EvidenceBlock(
        keywords_hit=all_hits,
        repo_baseline_summary=repo_summary,
        linked_context=linked_context,
        scope_signals=scope_signals,
        escalation_candidates=escalation_candidates,
        floor=floor,
        confirm_status="pending",
    )


def estimate_tier(
    requirement_text: str,
    repo_path: Path | None = None,
    link_results: list[LinkExpansionResult] | None = None,
) -> tuple[TierEstimate, EvidenceBlock]:
    """Full tier estimation (L1-L4). Returns (estimate, evidence_block).

    L1: keyword scan
    L2: repo baseline
    L3: link expansion (if link_results provided)
    L4: Evidence Block completeness (caller must call evidence.validate_for_lock())
    """
    from tools.workflow_cli.repo_baseline import scan_repo_baseline

    # L1: keyword scan
    keyword_hits = scan_keywords(requirement_text)

    # L2: repo baseline
    if repo_path is not None and repo_path.exists():
        repo = scan_repo_baseline(repo_path)
    else:
        from tools.workflow_cli.repo_baseline import RepoBaseline
        repo = RepoBaseline()

    # L3: link expansion (use provided results or empty)
    if link_results is None:
        link_results = []

    # Compute floor
    floor = compute_floor(keyword_hits, repo, link_results, requirement_text)

    # Build evidence
    evidence = build_evidence_block(keyword_hits, repo, link_results, floor)

    return floor, evidence

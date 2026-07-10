from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
import re


class LinkStatus(str, Enum):
    EXTERNAL = "external"  # http(s) link recorded as an external reference; not fetched
    LOCAL_FOUND = "local_found"
    LOCAL_MISSING = "local_missing"


@dataclass
class LinkExpansionResult:
    url: str
    status: LinkStatus
    content_preview: str = ""
    error: str = ""


_URL_PATTERN = re.compile(r'https?://[^\s\)\]\>\"\']+')
_LOCAL_DOT_PATTERN = re.compile(r'(?:^|[\s\(\[])(\./[^\s\)\]\>\"\']+|\.{2}/[^\s\)\]\>\"\']+)')
_LOCAL_SUBDIR_PATTERN = re.compile(r'(?:^|[\s\(\[])([a-zA-Z][a-zA-Z0-9_\-]*/[a-zA-Z0-9_\-][a-zA-Z0-9_\-./]*\.md)')
_PREVIEWABLE_LOCAL_EXTENSIONS = frozenset({".md", ".markdown", ".rst", ".adoc"})
_SENSITIVE_LOCAL_NAME_RE = re.compile(
    r"(?:^|[-_.])(?:secrets?|credentials?|tokens?|passwords?|passwd|private[-_]?key|api[-_]?key)(?:$|[-_.])",
    re.IGNORECASE,
)


def extract_links(text: str) -> list[str]:
    urls = _URL_PATTERN.findall(text)
    dot_paths = [m.strip() for m in _LOCAL_DOT_PATTERN.findall(text)]
    subdir_paths = [m.strip() for m in _LOCAL_SUBDIR_PATTERN.findall(text)]
    seen: set[str] = set()
    result = []
    for item in urls + dot_paths + subdir_paths:
        if item and item not in seen:
            seen.add(item)
            result.append(item)
    return result


def _local_preview_block_reason(path_str: str, candidate: Path, base: Path | None) -> str | None:
    try:
        relative = candidate.relative_to(base) if base is not None else Path(path_str)
    except ValueError:
        relative = Path(path_str)
    parts = [part for part in relative.parts if part not in ("", ".", "..")]
    if any(part.startswith(".") for part in parts):
        return "Local preview skipped for hidden path."
    if any(_SENSITIVE_LOCAL_NAME_RE.search(part) for part in parts):
        return "Local preview skipped for sensitive-looking path."
    if candidate.suffix.lower() not in _PREVIEWABLE_LOCAL_EXTENSIONS:
        return "Local preview skipped for unsupported local document extension."
    return None


def _expand_local(path_str: str, base_path: Path | None) -> LinkExpansionResult:
    base = None
    if base_path is not None:
        base = base_path.resolve()
        candidate = (base / path_str).resolve()
        if not candidate.is_relative_to(base):
            return LinkExpansionResult(
                url=path_str,
                status=LinkStatus.LOCAL_MISSING,
                error=f"Local path is outside base path: {candidate}",
            )
    else:
        candidate = Path(path_str).resolve()

    if candidate.exists() and candidate.is_file():
        block_reason = _local_preview_block_reason(path_str, candidate, base)
        if block_reason is not None:
            return LinkExpansionResult(
                url=path_str,
                status=LinkStatus.LOCAL_FOUND,
                error=block_reason,
            )
        try:
            with candidate.open(encoding="utf-8", errors="ignore") as stream:
                preview = stream.read(500)
            return LinkExpansionResult(url=path_str, status=LinkStatus.LOCAL_FOUND,
                                       content_preview=preview)
        except (PermissionError, OSError) as e:
            return LinkExpansionResult(url=path_str, status=LinkStatus.LOCAL_MISSING, error=str(e))
    return LinkExpansionResult(url=path_str, status=LinkStatus.LOCAL_MISSING,
                               error=f"File not found: {candidate}")


def expand_links(
    text: str,
    base_path: Path | None = None,
) -> list[LinkExpansionResult]:
    """Expand links found in requirement text.

    Local relative links are read for context. http(s) URLs are recorded as
    external references only: r2p never makes outbound requests for URLs found in
    (untrusted) requirement text, so a link cannot drive the tool to reach
    cloud-metadata endpoints, localhost, or internal services.
    """
    results = []
    links = extract_links(text)
    seen: set[str] = set()
    for link in links:
        if link in seen:
            continue
        seen.add(link)
        if link.startswith("http://") or link.startswith("https://"):
            results.append(LinkExpansionResult(url=link, status=LinkStatus.EXTERNAL))
        else:
            results.append(_expand_local(link, base_path))
    return results

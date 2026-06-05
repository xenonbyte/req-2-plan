from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from urllib import request, error as urllib_error
import re


class LinkStatus(str, Enum):
    REACHABLE = "reachable"
    UNREACHABLE = "unreachable"
    REQUIRES_AUTH = "requires_auth"
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


def _fetch_url(url: str) -> LinkExpansionResult:
    try:
        req = request.Request(url, headers={"User-Agent": "r2p-link-expander/1.0"})
        with request.urlopen(req, timeout=5) as resp:
            content = resp.read(500).decode("utf-8", errors="replace")
            return LinkExpansionResult(url=url, status=LinkStatus.REACHABLE, content_preview=content)
    except urllib_error.HTTPError as e:
        if e.code in (401, 403):
            return LinkExpansionResult(url=url, status=LinkStatus.REQUIRES_AUTH, error=str(e))
        return LinkExpansionResult(url=url, status=LinkStatus.UNREACHABLE, error=str(e))
    except Exception as e:
        return LinkExpansionResult(url=url, status=LinkStatus.UNREACHABLE, error=str(e))


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
            preview = candidate.read_text(encoding="utf-8", errors="ignore")[:500]
            return LinkExpansionResult(url=path_str, status=LinkStatus.LOCAL_FOUND,
                                       content_preview=preview)
        except (PermissionError, OSError) as e:
            return LinkExpansionResult(url=path_str, status=LinkStatus.LOCAL_MISSING, error=str(e))
    return LinkExpansionResult(url=path_str, status=LinkStatus.LOCAL_MISSING,
                               error=f"File not found: {candidate}")


def expand_links(
    text: str,
    base_path: Path | None = None,
    fetch_urls: bool = True,
) -> list[LinkExpansionResult]:
    results = []
    links = extract_links(text)
    seen: set[str] = set()
    for link in links:
        if link in seen:
            continue
        seen.add(link)
        if link.startswith("http://") or link.startswith("https://"):
            if fetch_urls:
                results.append(_fetch_url(link))
            else:
                results.append(LinkExpansionResult(
                    url=link, status=LinkStatus.UNREACHABLE, error="URL fetching disabled"
                ))
        else:
            results.append(_expand_local(link, base_path))
    return results

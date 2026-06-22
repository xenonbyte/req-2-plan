from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from ipaddress import ip_address
from pathlib import Path
from socket import getaddrinfo, gaierror
from urllib.parse import urljoin, urlparse
import http.client
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


def _resolve_pinned_ip(host: str) -> str | None:
    """Resolve ``host`` once and return a single public IP to connect to.

    Returns None when the host is unresolvable or any resolved address is
    private/loopback/link-local/etc. Requirement text is untrusted input, so an
    outbound fetch must refuse to reach cloud-metadata endpoints, localhost, or
    internal services. Connecting to the returned IP (instead of letting the HTTP
    client re-resolve at connect time) also closes the DNS-rebinding window
    between this safety check and the actual connection.
    """
    try:
        infos = getaddrinfo(host, None)
    except (gaierror, OSError, ValueError):
        return None  # unresolvable -> treat as unsafe, do not fetch
    pinned: str | None = None
    for info in infos:
        addr = info[4][0]
        try:
            ip = ip_address(addr)
        except ValueError:
            return None
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
        ):
            return None
        if pinned is None:
            pinned = addr
    return pinned


def _pin_connection(conn: http.client.HTTPConnection, ip: str) -> None:
    """Force ``conn`` to open its TCP socket to ``ip`` regardless of its host.

    The connection keeps its original hostname for the ``Host`` header and (for
    HTTPS) for TLS SNI and certificate validation; only the TCP target is pinned
    to the already-validated address, so a DNS rebind cannot redirect us.
    """
    real_create = conn._create_connection

    def _connect_pinned(address, *args, **kwargs):
        _, port = address
        return real_create((ip, port), *args, **kwargs)

    conn._create_connection = _connect_pinned


def _http_get(parsed, pinned_ip: str) -> tuple[int, bytes, str | None]:
    """GET ``parsed`` over a connection pinned to ``pinned_ip``.

    Returns ``(status, body_preview, location_header)``. Raises on network
    failure; the caller maps that to UNREACHABLE.
    """
    host = parsed.hostname
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    path = parsed.path or "/"
    if parsed.query:
        path = f"{path}?{parsed.query}"
    if parsed.scheme == "https":
        conn = http.client.HTTPSConnection(host, port, timeout=5)
    else:
        conn = http.client.HTTPConnection(host, port, timeout=5)
    _pin_connection(conn, pinned_ip)
    try:
        conn.request("GET", path, headers={"User-Agent": "r2p-link-expander/1.0"})
        resp = conn.getresponse()
        body = resp.read(500)
        return resp.status, body, resp.getheader("Location")
    finally:
        conn.close()


_REDIRECT_CODES = frozenset({301, 302, 303, 307, 308})
_MAX_REDIRECTS = 3


def _fetch_url(url: str) -> LinkExpansionResult:
    current = url
    for _ in range(_MAX_REDIRECTS + 1):
        parsed = urlparse(current)
        if parsed.scheme not in ("http", "https") or not parsed.hostname:
            return LinkExpansionResult(
                url=url, status=LinkStatus.UNREACHABLE, error="Unsupported URL scheme"
            )
        pinned_ip = _resolve_pinned_ip(parsed.hostname)
        if pinned_ip is None:
            return LinkExpansionResult(
                url=url,
                status=LinkStatus.UNREACHABLE,
                error="URL fetching blocked for private/loopback/link-local address",
            )
        try:
            status, body, location = _http_get(parsed, pinned_ip)
        except Exception as e:
            return LinkExpansionResult(url=url, status=LinkStatus.UNREACHABLE, error=str(e))
        if status in _REDIRECT_CODES and location:
            # Re-validate every redirect hop: a public URL must not be able to
            # bounce the fetch to an internal address.
            current = urljoin(current, location)
            continue
        if status in (401, 403):
            return LinkExpansionResult(
                url=url, status=LinkStatus.REQUIRES_AUTH, error=f"HTTP Error {status}"
            )
        if 200 <= status < 300:
            preview = body.decode("utf-8", errors="replace")
            return LinkExpansionResult(
                url=url, status=LinkStatus.REACHABLE, content_preview=preview
            )
        return LinkExpansionResult(
            url=url, status=LinkStatus.UNREACHABLE, error=f"HTTP Error {status}"
        )
    return LinkExpansionResult(
        url=url, status=LinkStatus.UNREACHABLE, error="Too many redirects"
    )


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
    fetch_urls: bool = False,
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

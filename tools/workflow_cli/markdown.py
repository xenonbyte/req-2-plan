"""Shared Markdown helpers used by gate and trace checks.

The single source of truth for "read only the text outside fenced code
blocks", so template/example snippets inside ``` ... ``` (or ~~~) fences
do not register as real headings, trace IDs, or references.
"""
from __future__ import annotations

import re

# A fence opener/closer: up to 3 leading spaces, then 3+ backticks or tildes.
_FENCE_MARKER_RE = re.compile(r"^[ \t]{0,3}(`{3,}|~{3,})")


def unfenced_markdown_lines(content: str):
    """Yield (line, start, end) for lines outside Markdown fenced code blocks.

    `start`/`end` are byte-less character offsets into the original `content`,
    so callers can map a yielded line back to its position in the source.
    """
    fence_char = ""
    fence_len = 0
    offset = 0
    for line in content.splitlines(keepends=True):
        marker = _FENCE_MARKER_RE.match(line)
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


def unfenced_markdown_text(content: str) -> str:
    return "".join(line for line, _, _ in unfenced_markdown_lines(content))


def heading_level(line: str) -> int | None:
    """ATX heading level (count of leading '#'), or None when not a heading."""
    stripped = line.lstrip()
    if not stripped.startswith("#"):
        return None
    return len(stripped) - len(stripped.lstrip("#"))


def heading_bounded_bodies(content: str, is_start):
    """Yield each section whose heading line satisfies `is_start(line)`.

    A section runs from its heading to the next heading at the same or higher
    level, so a later sibling section cannot bleed into it. Headings are
    located outside fenced code; each yielded body is a slice of the original
    `content` (fences within the body are preserved for the caller to handle).
    """
    lines = list(unfenced_markdown_lines(content))
    starts = [
        (start, level)
        for line, start, _ in lines
        if (level := heading_level(line)) is not None and is_start(line)
    ]
    headings = [
        (start, level)
        for line, start, _ in lines
        if (level := heading_level(line)) is not None
    ]
    for start, level in starts:
        end = len(content)
        for heading_start, heading_level_ in headings:
            if heading_start <= start:
                continue
            if heading_level_ <= level:
                end = heading_start
                break
        yield content[start:end]

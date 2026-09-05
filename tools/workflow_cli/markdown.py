"""Shared Markdown helpers used by gate and trace checks.

The single source of truth for "read only the text outside fenced code
blocks", so template/example snippets inside ``` ... ``` (or ~~~) fences
do not register as real headings, trace IDs, or references.
"""
from __future__ import annotations

import re

# A fence opener/closer: up to 3 leading spaces, then 3+ backticks or tildes.
_FENCE_MARKER_RE = re.compile(r"^[ \t]{0,3}(`{3,}|~{3,})")
_READONLY_SECTION_RE = re.compile(
    r"^[ \t]{0,3}(#{1,6})\s+"
    r"(?:Upstream Summary|Project Context)\s+\(read-only\)\s*(?:#+\s*)?$",
    re.IGNORECASE,
)
_READONLY_SECTION_END_RE = re.compile(
    r"^[ \t]{0,3}<!--\s*/r2p-read-only\s*-->\s*$",
    re.IGNORECASE,
)
# Source masks must retain every boundary recognized by str.splitlines().
# Compact filtering keeps its existing CR/LF-only comment masking contract.
_SOURCE_LINE_BREAKS = "\n\r\v\f\x1c\x1d\x1e\x85\u2028\u2029"

# Shared grammar for the authoritative execution-completion checkbox surface.
# Consumers decide whether an empty mark or ``x``/``X`` is legal for their
# current state, but spacing/case acceptance must stay identical.
PLAN_TASK_CHECKBOX_RE = re.compile(
    r"^\s*-\s*\[\s*([xX]?)\s*\]\s*(PLAN-TASK-\d+)\b"
)


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


def _blank_preserving_newlines(text: str, *, line_breaks: str = "\r\n") -> str:
    return "".join(char if char in line_breaks else " " for char in text)


def _mask_html_comments_outside_fences(
    content: str,
    *,
    preserve_readonly_end_marker: bool = False,
    line_breaks: str = "\r\n",
) -> str:
    """Blank comment characters while preserving offsets, newlines, and fences."""
    pieces: list[str] = []
    fence_char = ""
    fence_len = 0
    in_comment = False

    for line in content.splitlines(keepends=True):
        marker = _FENCE_MARKER_RE.match(line)
        if not in_comment and fence_char:
            pieces.append(line)
            if (
                marker
                and marker.group(1)[0] == fence_char
                and len(marker.group(1)) >= fence_len
                and not line[marker.end():].strip()
            ):
                fence_char = ""
                fence_len = 0
            continue

        if (
            not in_comment
            and preserve_readonly_end_marker
            and _READONLY_SECTION_END_RE.match(line)
        ):
            pieces.append(line)
            continue

        if not in_comment and marker:
            fence_char = marker.group(1)[0]
            fence_len = len(marker.group(1))
            pieces.append(line)
            continue

        cursor = 0
        while cursor < len(line):
            if in_comment:
                end = line.find("-->", cursor)
                if end < 0:
                    pieces.append(_blank_preserving_newlines(line[cursor:], line_breaks=line_breaks))
                    cursor = len(line)
                    continue
                pieces.append(_blank_preserving_newlines(line[cursor:end + 3], line_breaks=line_breaks))
                cursor = end + 3
                in_comment = False
                continue

            start = line.find("<!--", cursor)
            if start < 0:
                pieces.append(line[cursor:])
                break
            pieces.append(line[cursor:start])
            cursor = start
            in_comment = True

    return "".join(pieces)


def strip_html_comments_outside_fences(content: str) -> str:
    """Remove prose comments while preserving offsets and fenced code verbatim.

    Comment bytes are replaced by spaces and their newlines are retained, so
    removal cannot concatenate separate Markdown fields, headings, or trace IDs.
    """
    return _mask_html_comments_outside_fences(content)


def _readonly_section_ranges(content: str) -> list[tuple[int, int]]:
    """Find merged seeded regions in linear time, using original offsets."""
    scan_content = _mask_html_comments_outside_fences(
        content,
        preserve_readonly_end_marker=True,
    )
    # A reverse pass remembers the nearest qualifying heading for each of the
    # six supported read-only heading levels. An explicit terminator takes
    # precedence over copied headings, but cannot cross another read-only start.
    next_heading = [len(content)] * 7
    explicit_end = None
    removals: list[tuple[int, int]] = []
    for line, start, end in reversed(list(unfenced_markdown_lines(scan_content))):
        marker = _READONLY_SECTION_RE.match(line)
        if marker:
            boundary = explicit_end if explicit_end is not None else next_heading[len(marker.group(1))]
            removals.append((start, boundary))
            explicit_end = None
        elif _READONLY_SECTION_END_RE.match(line):
            explicit_end = end
        level = heading_level(line)
        if level is not None:
            for enclosing_level in range(level, 7):
                next_heading[enclosing_level] = start

    merged: list[tuple[int, int]] = []
    for start, end in reversed(removals):
        if not merged or start > merged[-1][1]:
            merged.append((start, end))
        else:
            prev_start, prev_end = merged[-1]
            merged[-1] = (prev_start, max(prev_end, end))
    return merged


def strip_readonly_sections(content: str) -> str:
    """Remove seeded read-only Markdown sections before structural validation."""
    pieces: list[str] = []
    cursor = 0
    for start, end in _readonly_section_ranges(content):
        pieces.append(content[cursor:start])
        cursor = end
    pieces.append(content[cursor:])
    return "".join(pieces)


def strip_nonsemantic_markdown(content: str) -> str:
    """Remove seeded read-only sections and prose HTML comments consistently."""
    return strip_html_comments_outside_fences(strip_readonly_sections(content))


def mask_nonsemantic_markdown(content: str) -> str:
    """Blank nonsemantic text, preserving source offsets and splitlines boundaries."""
    pieces: list[str] = []
    cursor = 0
    for start, end in _readonly_section_ranges(content):
        pieces.append(content[cursor:start])
        pieces.append(_blank_preserving_newlines(content[start:end], line_breaks=_SOURCE_LINE_BREAKS))
        cursor = end
    pieces.append(content[cursor:])
    return _mask_html_comments_outside_fences("".join(pieces), line_breaks=_SOURCE_LINE_BREAKS)


def heading_level(line: str) -> int | None:
    """ATX heading level (count of leading '#'), or None when not a heading."""
    stripped = line.lstrip()
    if not stripped.startswith("#"):
        return None
    return len(stripped) - len(stripped.lstrip("#"))


# A PLAN-TASK anchor heading, e.g. "### PLAN-TASK-001: title". Single source of
# truth shared by gates (task iteration) and cli (ledger seeding).
PLAN_TASK_ANCHOR_RE = re.compile(r"^### PLAN-TASK-\d+", re.MULTILINE)
_PLAN_TASK_ANCHOR_LINE_RE = re.compile(r"^###\s+(PLAN-TASK-\d+)\s*:?\s*(.*?)\s*$")


def plan_task_anchors(content: str) -> list[tuple[str, str]]:
    """Return (PLAN-TASK-NNN, title) for each task anchor outside code fences."""
    anchors: list[tuple[str, str]] = []
    for line, _, _ in unfenced_markdown_lines(content):
        if not PLAN_TASK_ANCHOR_RE.match(line):
            continue
        m = _PLAN_TASK_ANCHOR_LINE_RE.match(line.rstrip("\n"))
        if m:
            anchors.append((m.group(1), m.group(2).strip()))
    return anchors


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

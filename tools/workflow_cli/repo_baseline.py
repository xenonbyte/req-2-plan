"""Scan repo baseline metrics: LOC, language breakdown, monorepo detection, submodules."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class RepoBaseline:
    """Repository baseline metrics."""
    loc: int = 0
    module_count: int = 0
    is_monorepo: bool = False
    language_breakdown: dict[str, int] = field(default_factory=dict)
    submodule_count: int = 0
    cross_language_refs: list[str] = field(default_factory=list)


EXTENSION_TO_LANGUAGE = {
    ".py": "Python",
    ".ts": "TypeScript",
    ".tsx": "TypeScript",
    ".js": "JavaScript",
    ".jsx": "JavaScript",
    ".go": "Go",
    ".rs": "Rust",
    ".java": "Java",
    ".kt": "Kotlin",
    ".swift": "Swift",
    ".rb": "Ruby",
    ".php": "PHP",
    ".cs": "C#",
    ".cpp": "C++",
    ".cc": "C++",
    ".c": "C",
    ".h": "C",
    ".scala": "Scala",
    ".ex": "Elixir",
    ".exs": "Elixir",
    ".zig": "Zig",
    ".dart": "Dart",
}

MONOREPO_SIGNALS = {
    "package.json",
    "setup.py",
    "Cargo.toml",
    "go.mod",
    "build.gradle",
    "pom.xml",
}

SKIP_DIRS = {
    ".git",
    ".worktrees",
    "node_modules",
    "__pycache__",
    ".venv",
    "venv",
    "dist",
    "build",
    "target",
    ".pytest_cache",
    ".mypy_cache",
}


def _count_loc(path: Path) -> int:
    """Count non-blank lines of code in a file."""
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
        return sum(1 for line in text.splitlines() if line.strip())
    except (PermissionError, OSError):
        return 0


def scan_repo_baseline(repo_path: Path) -> RepoBaseline:
    """Scan repo directory and return baseline metrics.

    Args:
        repo_path: Path to the repository root.

    Returns:
        RepoBaseline with collected metrics.
    """
    total_loc = 0
    language_breakdown: dict[str, int] = {}
    monorepo_signal_files: dict[str, list[Path]] = {}
    module_dirs: set[Path] = set()
    submodule_count = 0

    for root, dirs, files in os.walk(repo_path):
        root_path = Path(root)
        # Skip excluded directories
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith(".")]

        for fname in files:
            fpath = root_path / fname
            ext = fpath.suffix.lower()

            # Count lines of code for recognized languages
            if ext in EXTENSION_TO_LANGUAGE:
                lang = EXTENSION_TO_LANGUAGE[ext]
                loc = _count_loc(fpath)
                total_loc += loc
                language_breakdown[lang] = language_breakdown.get(lang, 0) + loc
                module_dirs.add(root_path)

            # Track monorepo signal files
            if fname in MONOREPO_SIGNALS:
                monorepo_signal_files.setdefault(fname, []).append(fpath)

            # Count git submodules
            if fname == ".gitmodules":
                try:
                    content = fpath.read_text(encoding="utf-8", errors="ignore")
                    submodule_count = content.count("[submodule ")
                except (PermissionError, OSError):
                    pass

    # Detect monorepo: 2+ of same signal file type (e.g., 2+ package.json)
    is_monorepo = any(len(paths) >= 2 for paths in monorepo_signal_files.values())

    # Cross-language refs: list of languages if 2+
    languages = sorted(language_breakdown.keys())
    cross_language_refs = languages if len(languages) >= 2 else []

    return RepoBaseline(
        loc=total_loc,
        module_count=len(module_dirs),
        is_monorepo=is_monorepo,
        language_breakdown=language_breakdown,
        submodule_count=submodule_count,
        cross_language_refs=cross_language_refs,
    )

"""Build a lightweight Project Context Pack (v1: no AST symbols)."""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path

from tools.workflow_cli.repo_baseline import SKIP_DIRS, scan_repo_baseline

_CONFIG_NAMES = {
    "pyproject.toml", "setup.cfg", "tox.ini", "Cargo.toml", "go.mod",
    "tsconfig.json", ".env.example", "Dockerfile", "Makefile", "requirements.txt",
}
_ENTRYPOINT_HINTS = ("main.py", "__main__.py", "index.ts", "index.js", "app.py", "server.ts")


@dataclass
class ProjectContextPack:
    repo_root: str = "."
    languages: dict = field(default_factory=dict)
    package_managers: list = field(default_factory=list)
    test_commands: list = field(default_factory=list)
    entrypoints: list = field(default_factory=list)
    dependencies: list = field(default_factory=list)  # [{name, version, ecosystem}]
    config_files: list = field(default_factory=list)
    source_dirs: list = field(default_factory=list)


def build_context_pack(repo_path: Path) -> ProjectContextPack:
    repo_path = Path(repo_path)
    baseline = scan_repo_baseline(repo_path)
    pack = ProjectContextPack(repo_root=str(repo_path), languages=dict(baseline.language_breakdown))

    pkg = repo_path / "package.json"
    if pkg.exists():
        try:
            data = json.loads(pkg.read_text(encoding="utf-8"))
            pack.package_managers.append("npm")
            test = (data.get("scripts") or {}).get("test")
            if test:
                pack.test_commands.append(test)
            for name, ver in (data.get("dependencies") or {}).items():
                pack.dependencies.append({"name": name, "version": ver, "ecosystem": "npm"})
        except (ValueError, OSError):
            pass

    req = repo_path / "requirements.txt"
    if req.exists():
        pack.package_managers.append("pip")
        for line in req.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith(("#", "-")):
                pack.dependencies.append({"name": line, "version": "", "ecosystem": "pip"})
        if not pack.test_commands:
            pack.test_commands.append("python -m pytest")

    for root, dirs, files in os.walk(repo_path):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith(".")]
        rel_root = Path(root).relative_to(repo_path)
        for fname in files:
            rel = str(rel_root / fname) if str(rel_root) != "." else fname
            if fname in _CONFIG_NAMES:
                pack.config_files.append(rel)
            if fname in _ENTRYPOINT_HINTS:
                pack.entrypoints.append(rel)

    pack.source_dirs = sorted(
        p.name for p in repo_path.iterdir()
        if p.is_dir() and p.name not in SKIP_DIRS and not p.name.startswith(".")
    )
    return pack


def to_json(pack: ProjectContextPack) -> str:
    return json.dumps(asdict(pack), indent=2, ensure_ascii=False)


def to_markdown(pack: ProjectContextPack) -> str:
    return (
        "# Project Context Pack\n\n"
        f"- repo_root: `{pack.repo_root}`\n"
        f"- languages: {pack.languages}\n"
        f"- package_managers: {', '.join(pack.package_managers) or 'none'}\n"
        f"- test_commands: {pack.test_commands or 'none'}\n"
        f"- entrypoints: {pack.entrypoints or 'none'}\n"
        f"- config_files: {pack.config_files or 'none'}\n"
        f"- dependencies: {len(pack.dependencies)} found\n"
        f"- source_dirs: {pack.source_dirs}\n"
    )


def write_context_pack(pack: ProjectContextPack, run_dir: Path) -> tuple[Path, Path]:
    json_path = run_dir / "02-project-context.json"
    md_path = run_dir / "02-project-context.md"
    json_path.write_text(to_json(pack), encoding="utf-8")
    md_path.write_text(to_markdown(pack), encoding="utf-8")
    return md_path, json_path

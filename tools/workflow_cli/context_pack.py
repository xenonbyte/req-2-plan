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
    dependencies: list = field(default_factory=list)  # [{name, version, ecosystem, dev?}]
    config_files: list = field(default_factory=list)
    source_dirs: list = field(default_factory=list)


def _append_npm_dependencies(pack: ProjectContextPack, dependencies: object, *, dev: bool = False) -> None:
    if not isinstance(dependencies, dict):
        return
    for name, version in dependencies.items():
        if not isinstance(name, str) or not isinstance(version, str):
            continue
        dep = {"name": name, "version": version, "ecosystem": "npm"}
        if dev:
            dep["dev"] = True
        pack.dependencies.append(dep)


def build_context_pack(repo_path: Path) -> ProjectContextPack:
    repo_path = Path(repo_path).resolve()
    baseline = scan_repo_baseline(repo_path)
    pack = ProjectContextPack(repo_root=str(repo_path), languages=dict(baseline.language_breakdown))

    pkg = repo_path / "package.json"
    if pkg.exists():
        try:
            raw_data = json.loads(pkg.read_text(encoding="utf-8"))
            pack.package_managers.append("npm")
            data = raw_data if isinstance(raw_data, dict) else {}
            scripts = data.get("scripts")
            if isinstance(scripts, dict) and scripts.get("test"):
                pack.test_commands.append("npm test")
            _append_npm_dependencies(pack, data.get("dependencies"))
            _append_npm_dependencies(pack, data.get("devDependencies"), dev=True)
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


_DEP_DISPLAY_CAP = 20


def _dependencies_markdown(dependencies: list) -> str:
    """Itemize dependencies (name, version, ecosystem, dev flag), capped to keep the seed small."""
    if not dependencies:
        return "- dependencies (0): none\n"
    lines = [f"- dependencies ({len(dependencies)}):\n"]
    for dep in dependencies[:_DEP_DISPLAY_CAP]:
        label = " ".join(part for part in (dep.get("name", ""), dep.get("version", "")) if part)
        ecosystem = dep.get("ecosystem", "")
        suffix = f"{ecosystem}, dev" if dep.get("dev") else ecosystem
        lines.append(f"  - {label} ({suffix})\n")
    hidden = len(dependencies) - _DEP_DISPLAY_CAP
    if hidden > 0:
        lines.append(f"  - … and {hidden} more\n")
    return "".join(lines)


def to_markdown(pack: ProjectContextPack) -> str:
    return (
        "# Project Context Pack\n\n"
        f"- repo_root: `{pack.repo_root}`\n"
        f"- languages: {pack.languages}\n"
        f"- package_managers: {', '.join(pack.package_managers) or 'none'}\n"
        f"- test_commands: {pack.test_commands or 'none'}\n"
        f"- entrypoints: {pack.entrypoints or 'none'}\n"
        f"- config_files: {pack.config_files or 'none'}\n"
        f"{_dependencies_markdown(pack.dependencies)}"
        f"- source_dirs: {pack.source_dirs}\n"
    )


def write_context_pack(pack: ProjectContextPack, run_dir: Path) -> tuple[Path, Path]:
    json_path = run_dir / "02-project-context.json"
    md_path = run_dir / "02-project-context.md"
    json_path.write_text(to_json(pack), encoding="utf-8")
    md_path.write_text(to_markdown(pack), encoding="utf-8")
    return md_path, json_path

"""
r2p lifecycle binary — install/uninstall/status CLI.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main(args=None):
    parser = argparse.ArgumentParser(prog="r2p", description="r2p lifecycle binary")
    parser.add_argument(
        "--version", "-v", action="store_true", help="Print r2p version and exit"
    )
    subparsers = parser.add_subparsers(dest="command")

    # install
    p_install = subparsers.add_parser(
        "install", help="Install agent integration templates (all platforms by default)"
    )
    p_install.add_argument(
        "--platform",
        default=None,
        help="Platform or comma-separated platform list (default: all)",
    )
    p_install.set_defaults(func=_cmd_install)

    # uninstall
    p_uninstall = subparsers.add_parser(
        "uninstall", help="Uninstall agent integration (all platforms by default)"
    )
    p_uninstall.add_argument(
        "--platform",
        default=None,
        help="Platform or comma-separated platform list (default: all)",
    )
    p_uninstall.set_defaults(func=_cmd_uninstall)

    # status
    p_status = subparsers.add_parser(
        "status", help="Report install status per platform (read-only)"
    )
    p_status.add_argument("--json", action="store_true", help="Machine-readable JSON output")
    p_status.set_defaults(func=_cmd_status)

    # version
    p_version = subparsers.add_parser("version", help="Print r2p version")
    p_version.set_defaults(func=_cmd_version)

    # help
    subparsers.add_parser("help", help="Print this command list")

    parsed = parser.parse_args(args)
    if parsed.version:
        _cmd_version(parsed)
        return
    if parsed.command in (None, "help"):
        parser.print_help()
        return
    parsed.func(parsed)


def _make_service():
    from tools.workflow_cli.install import InstallService

    repo_root = Path(__file__).parent.parent.parent
    manifest_root = Path.home() / ".req-to-plan"
    return InstallService(repo_root=repo_root, manifest_root=manifest_root)


def _cmd_install(args):
    from tools.workflow_cli.install import SUPPORTED_PLATFORMS

    service = _make_service()
    platforms = _parse_platforms(args.platform, SUPPORTED_PLATFORMS)
    for platform in platforms:
        try:
            manifest = service.install(platform)
        except ValueError as exc:
            print(f"Error: {exc}")
            sys.exit(1)

        n = len(manifest.get("installed_paths", []))
        manifest_path = (
            Path.home() / ".req-to-plan" / "install" / f"{platform}.yaml"
        )
        print(
            f"install: platform={platform!r} "
            f"installed_paths={n} "
            f"manifest={manifest_path}"
        )


def _cmd_uninstall(args):
    from tools.workflow_cli.install import SUPPORTED_PLATFORMS

    service = _make_service()
    platforms = _parse_platforms(args.platform, SUPPORTED_PLATFORMS)
    for platform in platforms:
        try:
            result = service.uninstall(platform)
        except FileNotFoundError as exc:
            print(f"Error: {exc}")
            sys.exit(1)
        print(
            f"uninstall: platform={platform!r} "
            f"removed={len(result['removed'])} paths"
        )


def _cmd_status(args):
    service = _make_service()
    reports = service.status()
    if args.json:
        print(json.dumps(reports, indent=2, sort_keys=True))
        return
    if not reports:
        print("status: no platforms installed")
        return
    for r in reports:
        line = f"status: platform={r['platform']!r} state={r['status']}"
        if r.get("r2p_version"):
            line += f" version={r['r2p_version']!r}"
        if r["issues"]:
            line += f" issues={r['issues']}"
        print(line)


def _cmd_version(args):
    from tools.workflow_cli.version import R2P_VERSION

    print(R2P_VERSION)


def _parse_platforms(raw: str | None, supported: tuple[str, ...]) -> list[str]:
    if raw is None:
        return list(supported)
    platforms: list[str] = []
    for part in raw.split(","):
        platform = part.strip()
        if platform and platform not in platforms:
            platforms.append(platform)
    if not platforms:
        print("Error: --platform must name at least one platform")
        sys.exit(1)
    invalid = [p for p in platforms if p not in supported]
    if invalid:
        print(f"Error: Unknown platform(s): {invalid!r}. Supported: {supported}")
        sys.exit(1)
    return platforms


if __name__ == "__main__":
    main()

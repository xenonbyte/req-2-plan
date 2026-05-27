"""
r2p lifecycle binary — install/uninstall/doctor CLI.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path


def main(args=None):
    parser = argparse.ArgumentParser(prog="r2p", description="r2p lifecycle binary")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # install
    p_install = subparsers.add_parser("install", help="Install agent integration templates")
    p_install.add_argument("--platform", required=True)
    p_install.add_argument(
        "--confirm",
        action="store_true",
        default=False,
        help="Overwrite an existing installation",
    )
    p_install.set_defaults(func=_cmd_install)

    # uninstall
    p_uninstall = subparsers.add_parser("uninstall", help="Uninstall agent integration")
    p_uninstall.add_argument("--platform", required=True)
    p_uninstall.set_defaults(func=_cmd_uninstall)

    # installed
    p_installed = subparsers.add_parser("installed", help="List installed platforms")
    p_installed.set_defaults(func=_cmd_installed)

    # doctor
    p_doctor = subparsers.add_parser("doctor", help="Check for template drift")
    p_doctor.set_defaults(func=_cmd_doctor)

    # version
    p_version = subparsers.add_parser("version", help="Print r2p version")
    p_version.set_defaults(func=_cmd_version)

    parsed = parser.parse_args(args)
    parsed.func(parsed)


def _make_service():
    from tools.workflow_cli.install import InstallService

    repo_root = Path(__file__).parent.parent.parent
    manifest_root = Path.home() / ".req-to-plan"
    return InstallService(repo_root=repo_root, manifest_root=manifest_root)


def _cmd_install(args):
    from tools.workflow_cli.install import InstallService

    service = _make_service()
    try:
        manifest = service.install(args.platform, confirm=args.confirm)
    except FileExistsError as exc:
        print(f"Error: {exc}")
        print("Use --confirm to reinstall.")
        sys.exit(1)
    except ValueError as exc:
        print(f"Error: {exc}")
        sys.exit(1)

    n = len(manifest.get("installed_paths", []))
    manifest_path = (
        Path.home() / ".req-to-plan" / "install" / f"{args.platform}.yaml"
    )
    print(
        f"install: platform={args.platform!r} "
        f"installed_paths={n} "
        f"manifest={manifest_path}"
    )


def _cmd_uninstall(args):
    service = _make_service()
    try:
        result = service.uninstall(args.platform)
    except FileNotFoundError as exc:
        print(f"Error: {exc}")
        sys.exit(1)
    print(
        f"uninstall: platform={args.platform!r} "
        f"removed={len(result['removed'])} paths"
    )


def _cmd_installed(args):
    service = _make_service()
    platforms = service.installed()
    if not platforms:
        print("installed: none")
    else:
        for info in platforms:
            print(
                f"installed: platform={info['platform']!r} "
                f"version={info['r2p_version']!r} "
                f"at={info['installed_at']}"
            )


def _cmd_doctor(args):
    service = _make_service()
    reports = service.doctor()
    if not reports:
        print("doctor: no platforms installed")
    else:
        for r in reports:
            status = r["status"]
            issues = r["issues"]
            if issues:
                print(f"doctor: platform={r['platform']!r} status={status} issues={issues}")
            else:
                print(f"doctor: platform={r['platform']!r} status={status}")


def _cmd_version(args):
    from tools.workflow_cli.version import R2P_VERSION

    print(R2P_VERSION)


if __name__ == "__main__":
    main()

"""
r2p lifecycle binary — install/uninstall/doctor CLI.

Full install logic implemented in Task 14.
This module provides the argparse router with stub implementations.
"""
from __future__ import annotations

import argparse
import sys


def main(args=None):
    parser = argparse.ArgumentParser(prog="r2p", description="r2p lifecycle binary")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # install
    p_install = subparsers.add_parser("install", help="Install agent integration templates")
    p_install.add_argument("--platform", required=True)
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


def _cmd_install(args):
    print(f"[stub] install --platform {args.platform} — implemented in Task 14")


def _cmd_uninstall(args):
    print(f"[stub] uninstall --platform {args.platform} — implemented in Task 14")


def _cmd_installed(args):
    print("[stub] installed — implemented in Task 14")


def _cmd_doctor(args):
    print("[stub] doctor — implemented in Task 14")


def _cmd_version(args):
    from tools.workflow_cli.version import R2P_VERSION
    print(R2P_VERSION)


if __name__ == "__main__":
    main()

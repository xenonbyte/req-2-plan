"""Tests for the npm package wrapper."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import os

from tools.workflow_cli.version import R2P_VERSION


REPO_ROOT = Path(__file__).parent.parent


def test_package_json_exposes_r2p_bin():
    package_json = REPO_ROOT / "package.json"

    data = json.loads(package_json.read_text(encoding="utf-8"))

    assert data["name"] == "req-2-plan"
    assert data["version"] == "0.1.0"
    assert data["bin"]["r2p"] == "bin/r2p.js"


def test_package_json_files_include_runtime_sources():
    data = json.loads((REPO_ROOT / "package.json").read_text(encoding="utf-8"))

    assert "bin/" in data["files"]
    assert "tools/workflow_cli/**/*.py" in data["files"]
    assert "docs/*.md" in data["files"]
    assert "requirements.txt" in data["files"]


def test_npm_bin_can_call_lifecycle_cli_version():
    result = subprocess.run(
        ["node", str(REPO_ROOT / "bin" / "r2p.js"), "version"],
        cwd=REPO_ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == R2P_VERSION


def test_lifecycle_cli_doctor_does_not_require_site_packages(tmp_path: Path):
    env = os.environ.copy()
    env["HOME"] = str(tmp_path)
    env["PYTHONPATH"] = str(REPO_ROOT)

    result = subprocess.run(
        [
            sys.executable,
            "-S",
            "-m",
            "tools.workflow_cli.install_cli",
            "doctor",
        ],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "doctor: no platforms installed"

"""Content-pinning tests for the README files.

These turn "we forgot to update the docs" into a failing build: the two language
files must keep identical heading sequences, every lifecycle command and key
literal must appear in both, and the MIT license must stay in sync across
LICENSE and package.json.
"""
from __future__ import annotations

import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
EN = REPO / "README.md"
ZH = REPO / "README.zh-CN.md"


def _headings(text: str) -> list[str]:
    """Markdown headings (col-0 ``#``), excluding lines inside code fences."""
    out: list[str] = []
    in_fence = False
    for line in text.splitlines():
        if line.strip().startswith("```"):
            in_fence = not in_fence
            continue
        if not in_fence and line.startswith("#"):
            out.append(line.strip())
    return out


def test_readme_files_exist():
    assert EN.exists()
    assert ZH.exists()


def test_heading_sequences_are_identical():
    en = _headings(EN.read_text(encoding="utf-8"))
    zh = _headings(ZH.read_text(encoding="utf-8"))
    assert en == zh, f"README heading drift:\nEN={en}\nZH={zh}"


def test_language_switcher_on_first_line():
    assert EN.read_text(encoding="utf-8").splitlines()[0] == "English | [简体中文](README.zh-CN.md)"
    assert ZH.read_text(encoding="utf-8").splitlines()[0] == "[English](README.md) | 简体中文"


def test_lifecycle_commands_appear_in_both():
    en = EN.read_text(encoding="utf-8")
    zh = ZH.read_text(encoding="utf-8")
    for cmd in ("r2p install", "r2p uninstall", "r2p status", "r2p version", "r2p help"):
        assert cmd in en, f"{cmd!r} missing from README.md"
        assert cmd in zh, f"{cmd!r} missing from README.zh-CN.md"


def test_key_literals_appear_in_both():
    en = EN.read_text(encoding="utf-8")
    zh = ZH.read_text(encoding="utf-8")
    for literal in (
        "@xenonbyte/req-2-plan",
        "--platform",
        "--json",
        "pyyaml",
        "~/.req-to-plan/bin",
        "claude",
        "codex",
        "gemini",
        "MIT",
    ):
        assert literal in en, f"{literal!r} missing from README.md"
        assert literal in zh, f"{literal!r} missing from README.zh-CN.md"


def test_doctor_and_confirm_not_resurrected():
    # The removed commands must not reappear in either README.
    for text in (EN.read_text(encoding="utf-8"), ZH.read_text(encoding="utf-8")):
        assert "r2p doctor" not in text
        assert "r2p installed" not in text
        assert "install --platform claude --confirm" not in text


def test_mit_license_is_in_sync():
    license_text = (REPO / "LICENSE").read_text(encoding="utf-8")
    assert "MIT License" in license_text
    pkg = json.loads((REPO / "package.json").read_text(encoding="utf-8"))
    assert pkg["license"] == "MIT"

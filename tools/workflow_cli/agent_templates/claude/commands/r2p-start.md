---
description: Start a new requirement-to-PLAN workflow run
---
Run `{{R2P_BIN_DIR}}/r2p-start` with the requirement as a positional argument.

Usage: `{{R2P_BIN_DIR}}/r2p-start [--separate] ("<raw requirement>" | --file <path>)`

To start from a requirement document, pass `--file <path>` instead of inline text — r2p reads the file contents as the requirement (the path itself is never stored as the requirement): `{{R2P_BIN_DIR}}/r2p-start [--separate] --file ./requirement.md`. `--file` and a positional requirement are mutually exclusive.

Use `--separate` to create an independent run when another open run exists.

Optionally pass `--repo-path <dir>` to ground tier estimation and the Project Context Pack in real repo facts.

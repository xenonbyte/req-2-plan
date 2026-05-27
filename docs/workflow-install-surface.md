# Workflow Install Surface

## Purpose

This document defines the `r2p <subcommand>` lifecycle binary that registers, verifies, and removes the requirement-to-PLAN agent integration on a host.

It is separate from the daily `workflow ...` commands documented in `workflow-cli-adapter.md` (which operate a workflow run) and from the dashed `r2p-*` shortcuts documented in `workflow-agent-command-adapter.md` (which compose session-level run actions). The lifecycle binary touches host filesystem paths under the user's home directory and the repository's bin directory; it does not change `run.md` or any artifact under `.req-to-plan/<work-id>/`.

Use this document when designing, implementing, or auditing the install/uninstall path for an agent platform integration.

## Scope

This document covers:

- The `r2p` lifecycle subcommand catalog.
- Per-platform install targets.
- Manifest format under `~/.req-to-plan/install/<platform>.yaml`.
- Safety rules for write, rollback, and shared-target cleanup.
- Verification semantics for `r2p doctor` and `r2p installed`.

This document does not cover:

- Daily workflow commands (`workflow ...`).
- Session-level shortcuts (`r2p-*`).
- Workflow run state, gates, checkpoints, or artifacts.
- Executor-specific runtime behavior.

## Subcommand Catalog

```text
r2p install --platform <list>
r2p uninstall --platform <list>
r2p installed
r2p doctor
r2p version
```

| Subcommand | Purpose | Writes | Confirmation |
|---|---|---|---|
| `r2p install --platform <list>` | Copy skill or command templates to each requested platform's home, copy bin scripts to `~/.req-to-plan/bin/`, write a manifest under `~/.req-to-plan/install/<platform>.yaml`, and back up any existing files at the target paths. | Platform-specific skill or command files, shared bin scripts, manifest, backups. | Implicit; aborts on existing manifest unless `--confirm` is supplied. |
| `r2p uninstall --platform <list>` | Restore from manifest backups, remove only manifest-tracked paths, and clean shared targets only when the last platform uninstalls. | Removes manifest-tracked files; restores backups. | Required when removing files modified after install. |
| `r2p installed` | List installed platforms with their `r2p_version` and install date from manifest files. Read-only. | None. | No. |
| `r2p doctor` | Compare each manifest's `r2p_version` against the current `version.py`, scan for missing or modified install paths, and report drift. Read-only. | None. | No. |
| `r2p version` | Print the current `r2p_version`. Read-only. | None. | No. |

The binary is implemented via `tools/r2p` shell wrapper that delegates to `python3 -m tools.workflow_cli.install_cli`. The wrapper resolves the repository root from its own script path and prepends that root to `PYTHONPATH` before invoking python3 with a python fallback. The wrapper namespace is distinct from the daily `tools/workflow_cli` namespace and from the `tools/r2p-*` session shortcuts.

## Per-Platform Install / Uninstall Flow

Install copies platform-specific skill or command templates to platform home directories. The destinations are fixed per platform so a platform's own loader can discover them without configuration.

| Platform | Skill destination | Command destination |
|---|---|---|
| `claude` | `~/.claude/skills/r2p/SKILL.md` | `~/.claude/commands/r2p-*.md` |
| `codex` | `~/.codex/skills/r2p-*/SKILL.md` | (same) |
| `gemini` | (no skill concept) | `~/.gemini/commands/r2p-*.toml` |

Install also copies absolute-path-referenced bin scripts to `~/.req-to-plan/bin/` so templates can reference scripts by stable absolute path independent of repo location. This shared bin directory is reference-counted across platforms: it is removed only when the last platform uninstalls.

Per-platform rules:

- Templates are rendered with the current `r2p_version` so re-installing after a version bump produces files stamped with the new version.
- Install never relies on platform-specific configuration files (for example, `~/.claude/settings.json`); it only writes the platform's own template directory.
- Uninstall removes only the paths listed in `installed_paths` for that platform. Files added by the user after install are not removed.
- A platform that lacks the skill concept (currently `gemini`) is installed by copying command templates only; the corresponding manifest still records a complete `installed_paths` list.

## Manifest Format

Each install writes a manifest under `~/.req-to-plan/install/<platform>.yaml`:

```yaml
schema_version: 1
platform: claude
r2p_version: 0.1.1
installed_at: 2026-05-27T12:00:00+08:00
installed_paths:
  - /Users/<user>/.claude/skills/r2p/SKILL.md
  - /Users/<user>/.claude/commands/r2p-start.md
backups:
  - target: /Users/<user>/.claude/commands/r2p-start.md
    backup: /Users/<user>/.req-to-plan/install/backups/claude/r2p-start.md.<timestamp>
```

Manifest rules:

- `schema_version` bumps when the manifest layout changes. Older manifests must remain readable by the current `r2p uninstall` and `r2p doctor` flows or the operator must run an explicit migration command (not yet defined in v1; the current schema_version is 1 and is considered stable).
- `r2p_version` records the version used at install time. `r2p doctor` compares this against the current `version.py`.
- `installed_paths` is the source of truth for uninstall. Anything outside this list is left alone.
- `backups` records target/backup pairs. Uninstall restores each backup back to its target, then removes the manifest.
- Manifest files themselves are not listed in `installed_paths`; the install/uninstall flow manages them implicitly.

## Safety Rules

The install path is destructive on the host. The following rules are mirrored from the equivalent forma install flow:

1. Any write that would overwrite an existing file first backs it up under `~/.req-to-plan/install/backups/<platform>/<filename>.<timestamp>` and records the backup in the manifest. No silent overwrites.
2. Uninstall never deletes a path that is not listed in the manifest's `installed_paths`. Operator-added files are preserved.
3. Shared targets (the `~/.req-to-plan/bin/` scripts and any future shared resource) are only deleted when the last platform's manifest references them. Reference counting is computed across all `~/.req-to-plan/install/*.yaml` files.
4. The manifest is the source of truth. A missing manifest means clean uninstall is not possible; the operator must run `r2p doctor` to surface the drift before manual cleanup.
5. Install failure rolls back all written files. If any write fails partway through an install, every previously written file in this install attempt is removed and any backed-up file is restored. Partial installs are not allowed.

`r2p doctor` is the read-only audit that surfaces drift between manifest and filesystem: missing installed files, modified installed files, version mismatch between manifest `r2p_version` and current `version.py`, and orphaned manifests whose platform is no longer supported.

## Cross-Links

- `workflow-cli-adapter.md` documents the daily `workflow ...` commands and the `r2p-*` session shortcut delegations; it links to this document for the lifecycle binary.
- `workflow-agent-command-adapter.md` documents the dashed `r2p-*` shortcuts and clarifies that `r2p <subcommand>` (no hyphen) is the lifecycle binary defined here.
- `workflow-operator-runbook.md` calls `r2p install` once per platform as the one-time setup step before any daily run.

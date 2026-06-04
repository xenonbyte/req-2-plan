# req-2-plan

`req-2-plan` installs and manages the local `r2p` workflow integration for supported agent platforms.

The npm package exposes one lifecycle command:

```bash
r2p
```

Use it to install platform templates, audit installed files, remove integrations, and print the installed workflow version.

## Requirements

- Node.js 18+
- Python 3 available as `python3` or `python`

The lifecycle commands (`r2p install`, `r2p uninstall`, `r2p status`, `r2p version`, `r2p help`) use only the Python standard library.

The daily workflow shortcuts installed by `r2p install` use the Python dependency in `requirements.txt`:

```bash
python3 -m pip install --user -r requirements.txt
```

If you installed from npm and do not have this repository checkout, install the dependency directly:

```bash
python3 -m pip install --user "pyyaml>=6.0"
```

## Install

```bash
npm install -g req-2-plan
```

Check the lifecycle CLI:

```bash
r2p version
r2p status
r2p help
```

## Install An Agent Integration

Supported platforms:

- `claude`
- `codex`
- `gemini`

Install all platforms (the default when `--platform` is omitted):

```bash
r2p install
```

Install one platform:

```bash
r2p install --platform claude
```

Install multiple platforms at once:

```bash
r2p install --platform claude,codex,gemini
```

Reinstalling overwrites an existing install — no confirmation flag is needed.
Pre-existing user files are backed up before any overwrite.

## What Install Writes

`r2p install` writes platform-specific templates into the target agent home directory and shared command wrappers under:

```text
~/.req-to-plan/bin/
```

It also writes a manifest:

```text
~/.req-to-plan/install/<platform>.yaml
```

The manifest records every managed path so uninstall can remove only files created by `r2p` and restore backups for files that existed before install.

## Daily Workflow Shortcuts

After install, platform templates call the shared wrappers:

```bash
r2p-start "Add rate limiting"
# or start from a requirement document (reads the file contents, not the path):
r2p-start --file ./requirement.md
r2p-continue
r2p-tier-lock --work-id WF-YYYYMMDD-slug --base light --confirm
r2p-status
r2p-switch --work-id WF-YYYYMMDD-slug
r2p-reopen --from WF-YYYYMMDD-slug --stage spec --reason "Fix upstream gap"
```

The wrappers are installed into `~/.req-to-plan/bin/`. Add that directory to `PATH` if you want to run the shortcuts directly from your shell:

```bash
export PATH="$HOME/.req-to-plan/bin:$PATH"
```

## Audit And Uninstall

Report install status per platform — installed version, drift (missing files or
version mismatch), or an invalid manifest. Read-only. Add `--json` for
machine-readable output:

```bash
r2p status
r2p status --json
```

Uninstall a platform (omit `--platform` to uninstall all):

```bash
r2p uninstall --platform claude
```

Uninstall multiple platforms:

```bash
r2p uninstall --platform claude,codex,gemini
```

Shared wrappers in `~/.req-to-plan/bin/` are removed only when no installed platform still needs them.

## Documentation

- [Requirement & design (authoritative doc)](docs/req-to-plan-design.md)

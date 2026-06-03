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

The lifecycle commands (`r2p install`, `r2p uninstall`, `r2p installed`, `r2p doctor`, `r2p version`) use only the Python standard library.

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
r2p installed
r2p doctor
```

## Install An Agent Integration

Supported platforms:

- `claude`
- `codex`
- `gemini`

Install one platform:

```bash
r2p install --platform claude
```

Install another platform:

```bash
r2p install --platform codex
r2p install --platform gemini
```

Install multiple platforms at once:

```bash
r2p install --platform claude,codex,gemini
```

If a platform was already installed, reinstall with explicit confirmation:

```bash
r2p install --platform claude --confirm
```

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

List installed platforms:

```bash
r2p installed
```

Check for missing files or version drift:

```bash
r2p doctor
```

Uninstall a platform:

```bash
r2p uninstall --platform claude
```

Uninstall multiple platforms:

```bash
r2p uninstall --platform claude,codex,gemini
```

Shared wrappers in `~/.req-to-plan/bin/` are removed only when no installed platform still needs them.

## Documentation

- [Workflow overview](docs/README.md)
- [Install surface](docs/workflow-install-surface.md)
- [Operator runbook](docs/workflow-operator-runbook.md)

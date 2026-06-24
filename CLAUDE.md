# CLAUDE.md

Claude-specific entrypoint for this repository.

Read `AGENTS.md` for agent operating rules, then read `DEVELOPMENT.md` for the
tool-neutral project guide. Keep shared project facts in `DEVELOPMENT.md`;
only Claude-specific loading behavior belongs here.

Repo-local `.claude/skills/` is local tool state and is not tracked. The
user-facing Claude install template is
`tools/workflow_cli/agent_templates/claude/SKILL.md`.

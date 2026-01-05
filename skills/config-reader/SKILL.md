---
name: config-reader
description: Read and manage daplug configuration from CLAUDE.md using <daplug_config> blocks, with legacy fallback and migration support.
allowed-tools:
  - Bash(python3:*)
  - Bash(jq:*)
  - Read
---

# Daplug Config Reader

Centralized configuration reader/migrator for daplug settings stored in `<daplug_config>` blocks inside CLAUDE.md. Provides backwards compatibility with legacy plaintext settings and safe migrations.

## When to Use This Skill

- Any command/skill needs daplug settings (preferred agent, worktree dir, llms_txt dir, ai usage awareness, cli logs dir)
- Before writing to CLAUDE.md for daplug settings
- When a user asks to migrate or audit CLAUDE.md config

## Config Format

```markdown
<daplug_config>
preferred_agent: codex
worktree_dir: .worktrees/
llms_txt_dir: /storage/projects/docker/llms_txt
ai_usage_awareness: enabled
cli_logs_dir: ~/.claude/cli-logs/
</daplug_config>
```

## Usage

```bash
PLUGIN_ROOT=$(jq -r '.plugins."daplug@cruzanstx"[0].installPath' ~/.claude/plugins/installed_plugins.json)
CONFIG_READER="$PLUGIN_ROOT/skills/config-reader/scripts/config.py"
```

### Get Single Setting

```bash
python3 "$CONFIG_READER" get preferred_agent
```

### Dump All Settings (JSON)

```bash
python3 "$CONFIG_READER" dump --json
```

### Dump as ENV Vars

```bash
python3 "$CONFIG_READER" dump --env
```

### Status / Verification

```bash
python3 "$CONFIG_READER" status
python3 "$CONFIG_READER" status --json
```

### Check Legacy Settings

```bash
python3 "$CONFIG_READER" check-legacy
```

### Migrate Legacy Settings

```bash
# Project and user
python3 "$CONFIG_READER" migrate --all

# Project only
python3 "$CONFIG_READER" migrate --project

# User only
python3 "$CONFIG_READER" migrate --user
```

### Set a Setting

```bash
# Project scope
python3 "$CONFIG_READER" set worktree_dir ".worktrees/" --scope project

# User scope
python3 "$CONFIG_READER" set preferred_agent "codex" --scope user
```

## Notes

- Lookup order: project CLAUDE.md (repo root) → user ~/.claude/CLAUDE.md
- Legacy plaintext settings are still supported but trigger warnings
- Migrations create a timestamped backup before writing

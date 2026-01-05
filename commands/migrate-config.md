---
name: migrate-config
description: Migrate legacy daplug settings in CLAUDE.md to the <daplug_config> block format
argument-hint: [--project|--user|--all] [--dry-run]
---

<objective>
Detect legacy plaintext daplug settings in CLAUDE.md and migrate them into a structured <daplug_config> block. Preserve existing values, remove legacy lines, and back up files before writing.
</objective>

<process>

<step1_resolve_config_reader>
Resolve the config reader utility:

```bash
PLUGIN_ROOT=$(jq -r '.plugins."daplug@cruzanstx"[0].installPath' ~/.claude/plugins/installed_plugins.json)
CONFIG_READER="$PLUGIN_ROOT/skills/config-reader/scripts/config.py"
```
</step1_resolve_config_reader>

<step2_detect_legacy>
Check if migration is needed:

```bash
python3 "$CONFIG_READER" check-legacy
```

If `needs_migration` is `true`, proceed. Otherwise, report that config is already on the new format.
</step2_detect_legacy>

<step3_confirm>
Ask the user to confirm migration. Explain that the command will:
- Back up each CLAUDE.md before writing
- Create/replace a <daplug_config> block
- Remove legacy plaintext settings
</step3_confirm>

<step4_run_migration>
Run migration based on arguments:

```bash
# Default: migrate both project and user
python3 "$CONFIG_READER" migrate --all

# Project only
python3 "$CONFIG_READER" migrate --project

# User only
python3 "$CONFIG_READER" migrate --user

# Dry run (no writes)
python3 "$CONFIG_READER" migrate --all --dry-run
```

Report the JSON output (changed, backups created, settings merged).
</step4_run_migration>

</process>

<notes>
- Migration preserves existing <daplug_config> values when both formats exist.
- Backups are written alongside the original file with a `.bak-YYYYMMDD-HHMMSS` suffix.
</notes>

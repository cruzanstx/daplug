---
name: check-config
description: Verify daplug configuration status and detect legacy settings
argument-hint: [--json]
---

<objective>
Show the current daplug configuration, which CLAUDE.md file each setting comes from, and warn if legacy plaintext settings are detected.
</objective>

<process>

<step1_resolve_config_reader>
Resolve the config reader utility:

```bash
PLUGIN_ROOT=$(jq -r '.plugins."daplug@cruzanstx"[0].installPath' ~/.claude/plugins/installed_plugins.json)
CONFIG_READER="$PLUGIN_ROOT/skills/config-reader/scripts/config.py"
```
</step1_resolve_config_reader>

<step2_show_status>
Show status in human-readable form (default):

```bash
python3 "$CONFIG_READER" status
```

Show JSON (if requested):

```bash
python3 "$CONFIG_READER" status --json
```
</step2_show_status>

<step3_warn>
If `needs_migration` is true, recommend running `/daplug:migrate-config`.
</step3_warn>

</process>

---
name: detect-clis
description: Scan and manage available AI coding CLIs
argument-hint: "[--fix] [--dry-run] [--reset] [--json]"
---

<objective>
Scan for installed AI coding CLIs and local model providers, show a readable summary (tables), and optionally apply safe fixes.
</objective>

<process>

<step1_resolve_cli_detector>
Resolve the CLI detector utility:

```bash
PLUGIN_ROOT=$(jq -r '.plugins."daplug@cruzanstx"[0].installPath' ~/.claude/plugins/installed_plugins.json)
DETECT_CLIS="$PLUGIN_ROOT/skills/cli-detector/scripts/detect_clis.py"
```
</step1_resolve_cli_detector>

<step2_run_command>
Run the command with the user-provided flags:

```bash
python3 "$DETECT_CLIS" $ARGUMENTS
```
</step2_run_command>

</process>

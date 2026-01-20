---
name: load-agents
description: Scan and manage available AI coding agents
argument-hint: "[--fix] [--reset] [--json]"
---

<objective>
Scan for installed AI coding CLIs and local model providers, show a readable summary (tables), and optionally apply safe fixes.
</objective>

<process>

<step1_resolve_agent_detector>
Resolve the agent detector utility:

```bash
PLUGIN_ROOT=$(jq -r '.plugins."daplug@cruzanstx"[0].installPath' ~/.claude/plugins/installed_plugins.json)
LOAD_AGENTS="$PLUGIN_ROOT/skills/agent-detector/scripts/load_agents.py"
```
</step1_resolve_agent_detector>

<step2_run_command>
Run the command with the user-provided flags:

```bash
python3 "$LOAD_AGENTS" $ARGUMENTS
```
</step2_run_command>

</process>


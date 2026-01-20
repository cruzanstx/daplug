---
name: detect-clis
description: Scan and manage available AI coding CLIs
argument-hint: "[--fix] [--dry-run] [--reset] [--json]"
---

<objective>
Scan for installed AI coding CLIs and local model providers, show a readable summary (tables), and optionally apply safe fixes.
</objective>

<local_provider_endpoints>
Local provider discovery checks endpoints in this order (per provider):
1. `<daplug_config>` `local_providers` (project `./CLAUDE.md` overrides user `~/.claude/CLAUDE.md`)
2. Environment variables (`LMSTUDIO_ENDPOINT`, `OLLAMA_HOST`, `VLLM_ENDPOINT`)
3. Localhost defaults (`http://localhost:1234/v1`, `http://localhost:11434/v1`, `http://localhost:8000/v1`)

Example config:
```markdown
<daplug_config>
local_providers:
  lmstudio: http://192.168.1.50:1234/v1
  ollama: http://gpu-server.local:11434/v1
  vllm: http://inference.local:8000/v1
</daplug_config>
```
</local_provider_endpoints>

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

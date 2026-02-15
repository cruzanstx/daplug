---
name: install-bridges
description: Install daplug command bridges for other AI coding runtimes
argument-hint: "[opencode] [--clean]"
---

<objective>
Generate command bridge files that let other AI coding runtimes (e.g. OpenCode) invoke daplug slash commands natively. Each bridge is a lightweight wrapper that references the original daplug command spec.
</objective>

<supported_runtimes>
- `opencode` — Generates bridge files in `~/.config/opencode/commands/` so OpenCode can run daplug commands as `/daplug-<command>`.
</supported_runtimes>

<process>

<step1_resolve_script>
Resolve the bridge generator script:

```bash
PLUGIN_ROOT=$(jq -r '.plugins."daplug@cruzanstx"[0].installPath' ~/.claude/plugins/installed_plugins.json)
BRIDGE_GEN="$PLUGIN_ROOT/scripts/generate-opencode-bridges.py"
```
</step1_resolve_script>

<step2_determine_runtime>
Parse the user's arguments. If no runtime is specified, default to `opencode`.

If the user specifies an unsupported runtime, list the supported runtimes from the section above and stop.
</step2_determine_runtime>

<step3_run_generator>
For `opencode`:

```bash
python3 "$BRIDGE_GEN" $ARGUMENTS
```

The `--clean` flag removes stale `daplug-*.md` bridges before regenerating.
</step3_run_generator>

<step4_report>
Show the user:
1. How many bridges were generated
2. The output directory
3. How to use them (e.g., "In OpenCode, run `/daplug-run-prompt 042` to execute a daplug prompt")
</step4_report>

</process>

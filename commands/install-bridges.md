---
name: install-bridges
description: Install daplug command bridges for other AI coding runtimes
argument-hint: "[opencode|codex] [--clean]"
---

<objective>
Generate command bridge artifacts that let other AI coding runtimes (OpenCode, Codex) invoke daplug commands. Each artifact is a lightweight wrapper that references the original daplug command spec.
</objective>

<supported_runtimes>
- `opencode` — Generates bridge files in `~/.config/opencode/commands/` so OpenCode can run daplug commands as `/daplug-<command>`. (OpenCode v3.10+ also exposes them natively as `/daplug:<command>` without bridges.)
- `codex` — Generates Codex **skills** (not slash commands) under `~/.codex/skills/daplug/<command>/SKILL.md`. Codex CLI does not load file-based slash commands; skills are the supported user-extension mechanism. Each skill is invoked as `$<command>` in Codex chat (e.g. `$run-prompt 042`) or auto-triggered when the user's request matches the skill description. The generator also migrates any v0.26.0 legacy prompt-bridges by removing them from `~/.codex/prompts/` and restoring archived hand-ports.
</supported_runtimes>

<process>

<step1_resolve_script>
Resolve the generator script for the chosen runtime:

```bash
PLUGIN_ROOT=$(jq -r '.plugins."daplug@cruzanstx"[0].installPath' ~/.claude/plugins/installed_plugins.json)
# opencode:
BRIDGE_GEN="$PLUGIN_ROOT/scripts/generate-opencode-bridges.py"
# codex:
BRIDGE_GEN="$PLUGIN_ROOT/scripts/generate-codex-skills.py"
```
</step1_resolve_script>

<step2_determine_runtime>
Parse the user's arguments. The first non-flag token is the runtime. If no runtime is specified, default to `opencode`.

If the user specifies an unsupported runtime, list the supported runtimes from the section above and stop.

Strip the runtime token from `$ARGUMENTS` before passing the remainder (e.g., `--clean`) to the generator.
</step2_determine_runtime>

<step3_run_generator>
Run the resolved generator with the remaining arguments:

```bash
python3 "$BRIDGE_GEN" $REMAINING_ARGS
```

The `--clean` flag removes existing managed daplug artifacts (sentinel-tagged) from the output directory before regenerating; user-installed skills/commands without the sentinel are never touched.

Codex-only flags:
- `--no-migrate` — skip the cleanup of v0.26.0 legacy prompt-bridges in `~/.codex/prompts/`. Default behavior is to migrate (remove sentinel-tagged bridges, restore archived hand-ports from `.archive-pre-bridge/`).
</step3_run_generator>

<step4_report>
Show the user:
1. How many artifacts were generated
2. The output directory
3. How to invoke them — examples:
   - opencode: "In OpenCode, run `/daplug-run-prompt 042` (or `/daplug:run-prompt 042` natively) to execute a daplug prompt"
   - codex: "In Codex, type `$run-prompt 042` (skill is auto-triggered if the user's request matches the description)"
4. For codex: if any v0.26.0 legacy bridges were migrated, mention how many were removed and how many hand-ports were restored.
</step4_report>

</process>

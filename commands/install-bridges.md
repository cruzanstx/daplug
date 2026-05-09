---
name: install-bridges
description: Install daplug command bridges for other AI coding runtimes
argument-hint: "[opencode|codex] [--clean]"
---

<objective>
Generate command bridge files that let other AI coding runtimes (OpenCode, Codex) invoke daplug slash commands natively. Each bridge is a lightweight wrapper that references the original daplug command spec.
</objective>

<supported_runtimes>
- `opencode` — Generates bridge files in `~/.config/opencode/commands/` so OpenCode can run daplug commands as `/daplug-<command>`. (OpenCode v3.10+ also exposes them natively as `/daplug:<command>` without bridges.)
- `codex` — Generates bridge files in `~/.codex/prompts/` so Codex CLI can run daplug commands as `/<command>` (no prefix; bare command name). Pre-existing files at colliding paths (e.g. a hand-ported `run-prompt.md`) are moved to `~/.codex/prompts/.archive-pre-bridge/` before the bridge is written. Subsequent regenerations identify managed bridges by an embedded sentinel marker, so unrelated user prompts are never touched.
</supported_runtimes>

<process>

<step1_resolve_script>
Resolve the bridge generator script for the chosen runtime:

```bash
PLUGIN_ROOT=$(jq -r '.plugins."daplug@cruzanstx"[0].installPath' ~/.claude/plugins/installed_plugins.json)
# opencode:
BRIDGE_GEN="$PLUGIN_ROOT/scripts/generate-opencode-bridges.py"
# codex:
BRIDGE_GEN="$PLUGIN_ROOT/scripts/generate-codex-bridges.py"
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

The `--clean` flag removes stale `daplug-*.md` bridges from the output directory before regenerating.
</step3_run_generator>

<step4_report>
Show the user:
1. How many bridges were generated
2. The output directory
3. How to use them — examples:
   - opencode: "In OpenCode, run `/daplug-run-prompt 042` (or `/daplug:run-prompt 042` natively) to execute a daplug prompt"
   - codex: "In Codex, run `/run-prompt 042` to execute a daplug prompt"
4. For codex: if any hand-ports were archived, mention the archive directory so the user can recover them if needed.
</step4_report>

</process>

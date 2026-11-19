<objective>
Add a bridge generator script that creates OpenCode-compatible command wrappers from daplug commands. This enables daplug slash commands to work in OpenCode, which does not load Claude marketplace plugins.

Implements: GitHub Issue #8
</objective>

<context>
daplug commands (`/daplug:run-prompt`, `/daplug:prompts`, etc.) work in Claude Code via `.claude-plugin/plugin.json` but fail in OpenCode with "Command or skill not found." OpenCode uses filename-based command registration from `~/.config/opencode/commands/` or `.opencode/commands/`.

The bridge approach: generate thin `.md` wrappers that `@reference` the real command spec files using absolute paths. No code duplication — bridges just redirect to the real command definitions.

Read these files for context:
- `commands/*.md` — all existing daplug commands
- `.claude-plugin/plugin.json` — plugin metadata
- `fix_run_prompt_opencode.md` — research doc in repo root
</context>

<requirements>
1. Create `scripts/generate-opencode-bridges.py` that:
   - Finds the daplug plugin root (from `installed_plugins.json` or script location fallback)
   - Scans `commands/*.md` for all command files
   - Generates bridge files in `~/.config/opencode/commands/` (or user-specified dir)
   - Bridge naming: `daplug-<command-name>.md` (e.g., `daplug-run-prompt.md`)
   - Each bridge contains: YAML frontmatter with description, `@<absolute_path>` reference to real command, `$ARGUMENTS` passthrough
   - Prints summary of generated bridges
   - Supports custom output dir via CLI argument
   - Supports `--clean` flag to remove stale bridges before regenerating

2. Each bridge file format:
```markdown
---
description: "daplug: <command-name>"
---

You are executing daplug's `<command-name>` command.

Read and follow this command spec exactly:
@<absolute_path_to_commands/command.md>

User arguments: $ARGUMENTS

Execute the command behavior exactly as documented.
Do not invent alternative workflows.
```

3. Script must:
   - Be executable (`chmod +x`)
   - Have proper shebang (`#!/usr/bin/env python3`)
   - Create output directory if it does not exist
   - Handle missing commands directory gracefully
   - Work both from installed plugin path and from repo checkout

4. Update README.md with an "OpenCode Compatibility" section documenting:
   - The problem (daplug commands not available in OpenCode)
   - The solution (bridge generator)
   - Usage instructions
   - Command name mapping (`/daplug:run-prompt` → `/daplug-run-prompt`)

5. Bump version in `.claude-plugin/plugin.json`
</requirements>

<implementation>
Follow the script design from the issue closely. Key points:
- `find_plugin_root()` checks `installed_plugins.json` first, falls back to script parent
- `generate_bridges()` does the actual file generation
- Use `pathlib.Path` throughout for clean path handling
- Print each generated bridge for user feedback

The `--clean` flag should glob `daplug-*.md` in the output dir and remove them before regenerating.
</implementation>

<verification>
Before declaring complete:

```bash
# Test from repo checkout
python3 scripts/generate-opencode-bridges.py /tmp/test-bridges
ls -la /tmp/test-bridges/

# Verify bridge count matches command count
CMDS=$(ls commands/*.md | wc -l)
BRIDGES=$(ls /tmp/test-bridges/daplug-*.md | wc -l)
echo "Commands: $CMDS, Bridges: $BRIDGES"

# Verify bridge content has correct @reference path
cat /tmp/test-bridges/daplug-run-prompt.md

# Test --clean flag
python3 scripts/generate-opencode-bridges.py --clean /tmp/test-bridges

# Verify script is executable
test -x scripts/generate-opencode-bridges.py && echo "OK" || echo "NOT EXECUTABLE"

# Cleanup
rm -rf /tmp/test-bridges
```

Verify README has OpenCode Compatibility section.
</verification>

<success_criteria>
- Script generates one bridge per command in `commands/*.md`
- Bridges use absolute `@reference` paths to real command specs
- Script works from both repo checkout and installed plugin path
- `--clean` flag removes stale bridges before regenerating
- Output directory created if missing
- README documents the feature and usage
- Plugin version bumped
</success_criteria>
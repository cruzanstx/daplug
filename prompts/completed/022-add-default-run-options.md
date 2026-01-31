<objective>
Add a `default_run_prompt_options` configuration setting to daplug that allows users to define their preferred default flags for running prompts. When create-prompt offers to run a prompt, show "Run with your defaults" as the first option if configured.
</objective>

<context>
This enhances the /create-prompt command workflow. Currently, after creating a prompt, users must manually select a model and flags each time. Power users want to set their preferred execution options once and reuse them.

Configuration system uses `<daplug_config>` XML blocks in CLAUDE.md files. The config-reader skill already supports reading/writing arbitrary keys with project-level override of user-level settings.

Key files:
@commands/create-prompt.md - Main file to modify (decision tree section)
@skills/config-reader/scripts/config.py - For reading/writing config
</context>

<requirements>
1. **New config key**: `default_run_prompt_options`
   - Format: Single string of flags (e.g., `--model codex-xhigh --worktree --loop`)
   - Location: `<daplug_config>` in `~/.claude/CLAUDE.md` (user-level)
   - Project-level config can override user-level

2. **When defaults ARE configured**:
   - Show as first option in "What's next?" menu: "1. Run with your defaults ({display the flags})"
   - Example: "1. Run with your defaults (--model codex-xhigh --worktree --loop)"
   - Other options shift down (Run now becomes 2, Review becomes 3, etc.)

3. **When defaults are NOT configured**:
   - When user selects "Run prompt now" (any run option), FIRST ask them:
     "You haven't set default run options yet. Would you like to set them now?
     
     1. Yes, set my defaults
     2. No, just run this once
     
     Choose (1-2): _"
   
   - If they choose #1 (set defaults):
     - Show the full model selection menu as usual
     - After they select, ask: "Save these as your defaults for future prompts? (y/n): _"
     - If yes: Save to `~/.claude/CLAUDE.md` using config-reader
     - Then execute the prompt with those options

   - If they choose #2 (run once):
     - Proceed with normal model selection flow
     - Do NOT prompt to save again

4. **Config reading priority** (already supported by config-reader):
   - Check project `./CLAUDE.md` first
   - Fall back to user `~/.claude/CLAUDE.md`

5. **Parsing the defaults string**:
   - Extract flags to build the /daplug:run-prompt command
   - Example: `--model codex-xhigh --worktree --loop` becomes `/daplug:run-prompt {number} --model codex-xhigh --worktree --loop`
</requirements>

<implementation>
Modify the `<decision_tree>` section in `commands/create-prompt.md`:

1. **Add config reading at the start of detection_logic**:
```bash
# Read default_run_prompt_options
DEFAULT_RUN_OPTS=$(python3 "$CONFIG_READER" get default_run_prompt_options --repo-root "$REPO_ROOT")
```

2. **Update single_prompt_scenario presentation**:
- If `DEFAULT_RUN_OPTS` is set, show it as option 1
- Shift other options down

3. **Add set-defaults flow**:
- When user picks "Run" and no defaults exist, offer to set them
- After model selection, offer to save as defaults
- Use config-reader to write: `python3 "$CONFIG_READER" set default_run_prompt_options "flags" --scope user`

4. **Apply same changes to parallel_scenario and sequential_scenario**

Key patterns to follow:
- Use the existing `$CONFIG_READER` variable (already defined in detection_logic)
- Match the existing presentation style (numbered options, Choose prompt)
- Keep the full model selection menu intact - defaults just provide a shortcut
</implementation>

<output>
Modify file:
- `./commands/create-prompt.md` - Update decision_tree section with defaults support
</output>

<verification>
After making changes:

1. Test config reading:
```bash
PLUGIN_ROOT=$(jq -r '.plugins."daplug@cruzanstx"[0].installPath' ~/.claude/plugins/installed_plugins.json)
CONFIG="$PLUGIN_ROOT/skills/config-reader/scripts/config.py"
python3 "$CONFIG" get default_run_prompt_options --quiet
```

2. Test config writing:
```bash
python3 "$CONFIG" set default_run_prompt_options "--model codex-xhigh --worktree --loop" --scope user
python3 "$CONFIG" get default_run_prompt_options --quiet
```

3. Manual test: Run /create-prompt with a simple task and verify:
   - With no defaults set: prompts to set defaults on first run
   - After setting defaults: shows "Run with your defaults" as option 1
   - Defaults string displays correctly in the option text
</verification>

<success_criteria>
- [ ] `default_run_prompt_options` can be read from config
- [ ] When set, appears as first option in "What's next?" menu
- [ ] When not set, user is prompted to set defaults on first run attempt
- [ ] User can decline setting defaults and run once without saving
- [ ] Saving defaults writes to `~/.claude/CLAUDE.md` correctly
- [ ] Project-level config overrides user-level (existing behavior)
</success_criteria>
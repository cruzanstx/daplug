<objective>
Migrate daplug configuration settings from plaintext key-value pairs to a structured XML block format in CLAUDE.md files, and update all daplug commands/skills to read from this new format.

Currently, settings like `preferred_agent:`, `worktree_dir:`, `llms_txt_dir:`, and `ai_usage_awareness:` are scattered as raw text in CLAUDE.md. This refactor consolidates them into a `<daplug_config>` block for better organization and parsing reliability.
</objective>

<context>
**Current state:** Settings are stored as plaintext lines in CLAUDE.md:
```markdown
## daplug Settings

preferred_agent: codex
worktree_dir: .worktrees/
llms_txt_dir: /storage/projects/docker/llms_txt
ai_usage_awareness: enabled
```

**Files that read these settings:**
- `commands/prompts.md` - reads `preferred_agent:`, `worktree_dir:`
- `commands/create-prompt.md` - reads `preferred_agent:`, `ai_usage_awareness:`
- `commands/create-llms-txt.md` - reads `llms_txt_dir:`, `preferred_agent:`, `ai_usage_awareness:`
- `skills/worktree/SKILL.md` - reads `worktree_dir:`
- `skills/prompt-executor/scripts/executor.py` - may read settings

**Lookup order:** Project CLAUDE.md → User ~/.claude/CLAUDE.md
</context>

<requirements>
1. **Define new XML config format:**
```markdown
<daplug_config>
preferred_agent: codex
worktree_dir: .worktrees/
llms_txt_dir: /storage/projects/docker/llms_txt
ai_usage_awareness: enabled
cli_logs_dir: ~/.claude/cli-logs/
</daplug_config>
```

2. **Create a config reader utility** (Python script or bash function) that:
   - Parses `<daplug_config>` blocks from CLAUDE.md files
   - Falls back to legacy plaintext format for backwards compatibility
   - Returns settings as key-value pairs (JSON for scripts, env vars for bash)
   - Checks project-level first, then user-level

3. **Update all files that read settings** to use the new config reader:
   - `commands/prompts.md`
   - `commands/create-prompt.md`
   - `commands/create-llms-txt.md`
   - `skills/worktree/SKILL.md`
   - Any other files with `grep.*CLAUDE.md` patterns

4. **Create migration utility** (`skills/config-migrator/` or in prompt-manager):
   - Detects legacy plaintext settings in CLAUDE.md
   - Offers to migrate them to `<daplug_config>` block
   - Preserves existing values
   - Handles both project and user-level CLAUDE.md
   - Safe: backs up before modifying

5. **Add verification command** to check config status:
   - Shows current config source (project vs user)
   - Shows all current settings
   - Warns about legacy format if detected
</requirements>

<implementation>
**Config reader location:** `skills/config-reader/scripts/config.py`

**Config reader interface:**
```bash
# Get single setting
python3 "$CONFIG_READER" get preferred_agent
# Output: codex

# Get all settings as JSON
python3 "$CONFIG_READER" dump --json
# Output: {"preferred_agent": "codex", "worktree_dir": ".worktrees/", ...}

# Check if migration needed
python3 "$CONFIG_READER" check-legacy
# Output: {"needs_migration": true, "legacy_settings": ["preferred_agent", "worktree_dir"]}
```

**Migration flow:**
1. Read existing CLAUDE.md
2. Find all daplug settings (both in `<daplug_config>` and as plaintext)
3. Merge into single `<daplug_config>` block
4. Remove legacy plaintext settings
5. Write updated CLAUDE.md

**Pattern to replace in command files:**
```bash
# OLD (multiple grep calls):
PREFERRED_AGENT=$(grep -E "^preferred_agent:" ./CLAUDE.md 2>/dev/null | sed 's/preferred_agent: *//')
if [ -z "$PREFERRED_AGENT" ]; then
    PREFERRED_AGENT=$(grep -E "^preferred_agent:" ~/.claude/CLAUDE.md 2>/dev/null | sed 's/preferred_agent: *//')
fi

# NEW (single call to config reader):
PLUGIN_ROOT=$(jq -r '.plugins."daplug@cruzanstx"[0].installPath' ~/.claude/plugins/installed_plugins.json)
CONFIG_READER="$PLUGIN_ROOT/skills/config-reader/scripts/config.py"
PREFERRED_AGENT=$(python3 "$CONFIG_READER" get preferred_agent)
```

**Backwards compatibility:** Config reader should:
1. First try to parse `<daplug_config>` block
2. If not found, fall back to legacy plaintext grep
3. Log a warning suggesting migration when using legacy format
</implementation>

<output>
Create/modify these files:

1. `skills/config-reader/SKILL.md` - Skill documentation
2. `skills/config-reader/scripts/config.py` - Config reader utility
3. `commands/migrate-config.md` - Migration command (or add to config-reader)
4. Update `commands/prompts.md` - Use config reader
5. Update `commands/create-prompt.md` - Use config reader
6. Update `commands/create-llms-txt.md` - Use config reader
7. Update `skills/worktree/SKILL.md` - Use config reader
8. Update `README.md` - Document new config format
</output>

<verification>
**Unit Tests** for config reader:
```bash
cd skills/config-reader && python3 -m pytest tests/ -v
```

Test scenarios:
- [ ] Parse `<daplug_config>` block correctly
- [ ] Fall back to legacy format when no block exists
- [ ] Project-level settings override user-level
- [ ] Handle missing CLAUDE.md gracefully
- [ ] Handle empty/malformed config blocks
- [ ] Migration preserves all existing values
- [ ] Migration creates valid `<daplug_config>` block

**Integration test:**
```bash
# After migration, all commands should still work:
/daplug:prompts --help
/daplug:create-prompt --help
/daplug:run-prompt --help
```

Before declaring complete:
- [ ] All config reads use the new config reader
- [ ] Legacy format still works (backwards compatible)
- [ ] Migration command works on test CLAUDE.md
- [ ] README documents the new format
</verification>

<success_criteria>
1. All daplug settings consolidated in `<daplug_config>` block
2. Single source of truth for config reading (config.py)
3. Backwards compatible with legacy plaintext format
4. Migration path for existing users
5. All existing commands continue to work
6. Clear documentation of new format
</success_criteria>
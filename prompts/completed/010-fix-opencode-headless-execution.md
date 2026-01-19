<objective>
Fix the opencode CLI integration in the daplug prompt executor for headless/programmatic execution.

Currently, opencode produces TUI-style character-by-character output and prompts for permissions interactively, making it unusable for automated prompt execution.
</objective>

<context>
This is a bug fix for GitHub issue #5: https://github.com/cruzanstx/daplug/issues/5

The prompt executor (`skills/prompt-executor/scripts/executor.py`) defines model configurations that control how each CLI is invoked. The opencode model currently uses a PTY wrapper which still produces unusable output.

@skills/prompt-executor/scripts/executor.py - MODEL_CONFIG dict around line 638
</context>

<requirements>
1. **Update opencode MODEL_CONFIG** in `executor.py`:
   - Add `--format json` flag to produce clean, parseable JSON output
   - Remove `needs_pty: True` since JSON format does not require a PTY
   - Keep `stdin_mode: "arg"` (opencode takes prompt as argument)

2. **Update documentation** in these files:
   - `CLAUDE.md` - Model Shorthand Reference table (note JSON output)
   - `README.md` - Model Tiers section (if opencode is listed)
   - `skills/prompt-executor/SKILL.md` - Model Reference table

3. **Consider JSON post-processing** (optional enhancement):
   - The JSON output includes structured events: `text`, `tool_use`, `step_finish`
   - Log files will contain raw JSON - may want to add a flag for human-readable conversion
   - For now, raw JSON logs are acceptable
</requirements>

<implementation>
Change from:
```python
"opencode": {
    "command": ["opencode", "run", "-m", "zai/glm-4.7"],
    "display": "opencode (GLM-4.7 via OpenCode)",
    "env": {},
    "stdin_mode": "arg",
    "needs_pty": True  # OpenCode requires a PTY for proper operation
},
```

To:
```python
"opencode": {
    "command": ["opencode", "run", "--format", "json", "-m", "zai/glm-4.7"],
    "display": "opencode (GLM-4.7 via OpenCode)",
    "env": {},
    "stdin_mode": "arg"
},
```

**Permission configuration note**: Users need to configure `~/.config/opencode/opencode.json` with:
```json
{
  "permission": {
    "*": "allow",
    "external_directory": "allow",
    "doom_loop": "allow"
  }
}
```
This should be documented but is a user setup step, not a code change.
</implementation>

<output>
Modify files with relative paths:
- `./skills/prompt-executor/scripts/executor.py` - Update opencode MODEL_CONFIG
- `./CLAUDE.md` - Update Model Shorthand Reference (add note about JSON output)
- `./skills/prompt-executor/SKILL.md` - Update Model Reference table
</output>

<verification>
**Functional test:**
```bash
# Test that the command builds correctly
cd /storage/projects/docker/daplug
PLUGIN_ROOT=$(jq -r '.plugins."daplug@cruzanstx"[0].installPath' ~/.claude/plugins/installed_plugins.json)
python3 skills/prompt-executor/scripts/executor.py 009 --model opencode

# Verify --format json is in the command output
```

**Manual verification** (if opencode is available):
```bash
timeout 60 opencode run --format json -m zai/glm-4.7 "echo hello"
# Should produce clean JSON output, no TUI artifacts
```

Before declaring complete, verify:
- [ ] opencode config in executor.py includes `--format json`
- [ ] `needs_pty` is removed from opencode config
- [ ] Documentation updated to reflect JSON output behavior
- [ ] Command builds correctly when tested with executor.py
</verification>

<success_criteria>
- opencode model config uses `--format json` flag
- PTY wrapper (`needs_pty`) is removed
- Documentation accurately describes the opencode model behavior
- The fix aligns with GitHub issue #5 requirements
</success_criteria>
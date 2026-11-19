<objective>
Implement a PostToolUse hook that automatically spawns the pipeline-deploy-monitor agent after successful git push commands. This replaces the unreliable "proactive behavior" approach with a mechanical trigger that fires every time.

Implements: GitHub Issue #7
</objective>

<context>
daplug is a Claude Code plugin. The pipeline-deploy-monitor agent already exists at `agents/pipeline-deploy-monitor.md` but never fires automatically because the "proactive" approach relies on AI judgment reading `~/.claude/infra/daplug.md` at the right moment.

Claude Code hooks fire deterministically on tool events. PostToolUse fires after a Bash command succeeds, making it perfect for detecting `git push` completions.

Read the existing hook format by examining:
- Any existing files in `hooks/`
- The pipeline-deploy-monitor agent at `agents/pipeline-deploy-monitor.md`
- `.claude-plugin/plugin.json` for version info
</context>

<requirements>
1. Create `hooks/hooks.json` with a PostToolUse hook registered on the Bash matcher
2. Create `hooks/scripts/post-push-detect.sh` that:
   - Reads JSON input from stdin (PostToolUse provides tool_input/tool_response)
   - Detects `git push` commands via regex `^git\s+push\b`
   - Extracts remote and branch from the command
   - Returns JSON with `hookSpecificOutput.additionalContext` containing a nudge message to spawn pipeline-deploy-monitor
   - Exits 0 silently for non-push commands
3. Delete `hooks/example-hook.json` if it exists (replaced by real hook)
4. Add optional `auto_pipeline_monitor` config key support:
   - Read from `<daplug_config>` in CLAUDE.md
   - If set to `disabled`, hook exits 0 silently
   - Default behavior (unset or `enabled`): hook fires normally
5. Update README.md to document the hook in the Hooks section
6. Bump version in `.claude-plugin/plugin.json`

Key design decisions:
- Use `additionalContext` (not `decision: "block"`) — we nudge, not block
- Use `jq` for JSON construction — safe escaping
- Timeout: 5 seconds (pure stdin parsing, no network)
- `${CLAUDE_PLUGIN_ROOT}` works correctly in hooks.json (unlike command .md files)
</requirements>

<implementation>
### hooks/hooks.json
```json
{
  "description": "daplug pipeline automation hooks",
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "command": "${CLAUDE_PLUGIN_ROOT}/hooks/scripts/post-push-detect.sh",
            "timeout": 5
          }
        ]
      }
    ]
  }
}
```

### hooks/scripts/post-push-detect.sh
- Make executable (chmod +x)
- Parse stdin JSON for tool_input.command
- Match git push pattern
- Extract remote/branch
- Output additionalContext JSON via jq
- Check auto_pipeline_monitor config if present

### Testing approach
```bash
# Test push detection
echo '{"tool_name":"Bash","tool_input":{"command":"git push origin main"},"tool_response":{"stdout":"...","exit_code":0}}' | bash hooks/scripts/post-push-detect.sh

# Test non-push (should be silent)
echo '{"tool_name":"Bash","tool_input":{"command":"git status"}}' | bash hooks/scripts/post-push-detect.sh
```
</implementation>

<verification>
Before declaring complete:
1. Run the test commands above and verify correct JSON output for push, silence for non-push
2. Verify hooks.json is valid JSON: `jq . hooks/hooks.json`
3. Verify post-push-detect.sh is executable
4. Verify README.md has a Hooks section documenting this feature
5. Verify plugin.json version was bumped
6. Test edge cases: `git push -u origin feat/branch`, `git push --force origin main`
</verification>

<success_criteria>
- hooks/hooks.json registers a PostToolUse hook on Bash
- post-push-detect.sh detects git push and returns additionalContext JSON
- Non-push commands produce no output
- Script handles various git push flag combinations
- README documents the hook feature
- Plugin version bumped
</success_criteria>
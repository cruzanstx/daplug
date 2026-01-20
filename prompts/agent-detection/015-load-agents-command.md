<objective>
Implement the `/load-agents` slash command for daplug that provides a user-friendly interface
to scan, view, and manage detected AI coding CLIs.
</objective>

<context>
**Depends on**: 
- `013-agent-detection-architecture.md` - Design
- `014-implement-cli-detection.md` - Detection plugins

**Read first**: `./docs/agent-detection-design.md` for UX mockups
</context>

<requirements>
## Command Definition

Create `commands/load-agents.md`:

```yaml
---
name: load-agents  
description: Scan and manage available AI coding agents
argument-hint: "[--fix] [--reset] [--json]"
---
```

## Command Behavior

### Default (no args): Scan and Display

```
/load-agents

🔍 Scanning for AI coding agents...

✅ Found 4 installed CLIs:

┌─────────────┬─────────┬────────────────────────┬────────────┐
│ CLI         │ Version │ Models                 │ Status     │
├─────────────┼─────────┼────────────────────────┼────────────┤
│ claude-code │ 1.0.16  │ claude-4-*, opus-4.5   │ ✅ Ready   │
│ codex       │ 1.2.3   │ gpt-5.2-*, codex       │ ⚠️ 1 issue │
│ gemini      │ 0.4.1   │ gemini-2.5-*, 3-*      │ ✅ Ready   │
│ opencode    │ 0.1.0   │ glm-4.7                │ ✅ Ready   │
└─────────────┴─────────┴────────────────────────┴────────────┘

🖥️ Local Model Providers:

┌──────────┬─────────────────────────┬──────────────────────────┐
│ Provider │ Endpoint                │ Loaded Models            │
├──────────┼─────────────────────────┼──────────────────────────┤
│ LMStudio │ http://localhost:1234   │ qwen-2.5-coder, devstral │
│ Ollama   │ (not running)           │ -                        │
└──────────┴─────────────────────────┴──────────────────────────┘

  💡 Local models usable via: codex, opencode, aider

⚠️ Issues detected (1):
  codex: Sandbox permissions need adjustment
  └─ Run `/load-agents --fix` to apply recommended fix

❌ Not installed:
  • aider - pip install aider-chat
  • goose - brew install goose

💾 Saved to ~/.claude/daplug-agents.json
```

### With --fix: Apply Fixes

```
/load-agents --fix

🔧 Applying fixes...

codex: Updating sandbox permissions in ~/.codex/config.json
  ✅ Added "permissions": {"*": "allow"} 
  📁 Backup saved to ~/.codex/config.json.bak

All issues resolved!
```

### With --reset: Clear Cache

```
/load-agents --reset

🗑️ Cleared agent cache
🔍 Rescanning...
[... normal output ...]
```

### With --json: Machine-Readable

```
/load-agents --json

{
  "schema_version": "1.0",
  "last_scanned": "2026-01-19T16:30:00Z",
  "clis": { ... },
  "issues": [ ... ]
}
```

## Integration Points

1. **First-run detection**: If no cache exists when running `/run-prompt`, 
   suggest running `/load-agents` first

2. **Model routing**: Use cache to determine best CLI for each model

3. **Quota awareness**: Integrate with cclimits for availability info

4. **Config updates**: When user changes preferred_agent, validate against cache
</requirements>

<implementation>
1. Create `commands/load-agents.md` with command definition
2. Use `skills/agent-detector` for actual detection logic
3. Format output with tables (markdown)
4. Handle all flags (--fix, --reset, --json)
5. Update cache after scan
</implementation>

<verification>
Manual testing:
- [ ] `/load-agents` shows table with detected CLIs
- [ ] `/load-agents --json` outputs valid JSON
- [ ] `/load-agents --fix` applies fixes (test with intentional issue)
- [ ] `/load-agents --reset` clears and rescans
- [ ] Output is readable and helpful
</verification>

<success_criteria>
- [ ] Command file created at `commands/load-agents.md`
- [ ] All 4 flags work correctly
- [ ] Table output is well-formatted
- [ ] Issues are clearly explained with fix instructions
- [ ] Cache is updated after each scan
</success_criteria>
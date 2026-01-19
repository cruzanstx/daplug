<objective>
Add session transcript references to prompts created by /create-prompt, similar to how Claude Code includes transcript references when exiting plan mode.

When a prompt is created, include a reference to the conversation that generated it so agents executing the prompt can access full context if needed.
</objective>

<context>
Claude Code stores session transcripts at:
`~/.claude/projects/{project-slug}/{session-id}.jsonl`

Example reference format (from Claude Code plan mode):
```
If you need specific details from before exiting plan mode (like exact code snippets, error messages, or
content you generated), read the full transcript at: /root/.claude/projects/-storage-projects-docker-pydanti
c-agent-history-compressors/fa7c37d9-5b22-4a44-a825-e7cdd57fade1.jsonl
```

Files to modify:
- `commands/create-prompt.md` - Add session reference generation
- Possibly `skills/prompt-manager/scripts/manager.py` - If session info needs to be passed through

Session information sources:
- Environment variable or Claude Code internal state
- The project path can be derived from the current working directory
</context>

<requirements>
1. **Detect Session Info**: Find a way to get the current session ID and project slug
   - Check if Claude Code exposes session info via environment variables
   - Or derive from `~/.claude/projects/` directory contents (most recent .jsonl file?)
   
2. **Generate Reference Section**: Create a standardized reference block to append to prompts:
   ```markdown
   ---
   **Session Context**: This prompt was created during a conversation. For full context:
   `~/.claude/projects/{project-slug}/{session-id}.jsonl`
   ```

3. **Integrate into create-prompt.md**: 
   - Add logic after prompt content generation, before saving
   - The reference should be appended to the prompt content
   - Make it optional/configurable if session detection fails gracefully

4. **Handle Edge Cases**:
   - Session info not available → skip reference (graceful degradation)
   - Multiple project folders → use the one matching current working directory
   - Fresh session with no transcript yet → still include path (transcript will exist by execution time)
</requirements>

<research>
Before implementing, investigate:

1. How does Claude Code expose session information?
   - Check environment variables during a session
   - Look at `~/.claude/` directory structure
   - Search for session ID in running process or config files

2. How is the project slug determined?
   - Appears to be the working directory path with `/` replaced by `-`
   - Example: `/storage/projects/docker/daplug` → `-storage-projects-docker-daplug`

3. Is there a more reliable way than timestamp-based detection?
   - Could check which .jsonl file is being written to (open file handles?)
   - Or use the most recent .jsonl file in the project folder
</research>

<implementation>
Suggested approach:

1. Add a bash function to detect session info:
```bash
# Derive project slug from current directory
PROJECT_SLUG=$(pwd | sed "s|/|-|g")
PROJECT_DIR="$HOME/.claude/projects/$PROJECT_SLUG"

# Find most recent session file (best approximation of current session)
if [ -d "$PROJECT_DIR" ]; then
    SESSION_FILE=$(ls -t "$PROJECT_DIR"/*.jsonl 2>/dev/null | head -1)
fi
```

2. Update create-prompt.md to append reference after prompt content:
```markdown
## Step 3: Generate and Save

[existing content...]

**After generating prompt content, append session reference:**
```bash
# Get session context
PROJECT_SLUG=$(pwd | sed "s|/|-|g" | sed "s|^-||")
PROJECT_DIR="$HOME/.claude/projects/-$PROJECT_SLUG"
if [ -d "$PROJECT_DIR" ]; then
    SESSION_FILE=$(ls -t "$PROJECT_DIR"/*.jsonl 2>/dev/null | head -1)
    if [ -n "$SESSION_FILE" ]; then
        # Append to prompt content
        CONTENT="$CONTENT

---
**Session Context**: For full conversation context, see: \`$SESSION_FILE\`"
    fi
fi
```
</implementation>

<output>
Modify: `./commands/create-prompt.md`
- Add session detection and reference generation logic
- Integrate into the prompt creation workflow

The reference should appear at the end of created prompts like:
```markdown
[prompt content...]

---
**Session Context**: For full conversation context, see: `~/.claude/projects/-storage-projects-docker-daplug/fa1b6fb2-f550-45e8-8d01-7babd92780e1.jsonl`
```
</output>

<verification>
1. Create a test prompt using /create-prompt
2. Check that the created prompt file includes the session reference
3. Verify the referenced .jsonl file exists and is the current session
4. Test graceful degradation when session info unavailable
</verification>

<success_criteria>
- [ ] Prompts created via /create-prompt include session transcript reference
- [ ] Reference path is correct and points to current session
- [ ] Graceful handling when session detection fails (no error, just skip reference)
- [ ] Reference format is clean and doesn't interfere with prompt execution
</success_criteria>
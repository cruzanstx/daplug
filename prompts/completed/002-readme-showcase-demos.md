<objective>
Update the daplug README with showcase examples and animated GIF demos that demonstrate all plugin capabilities. Create a compelling visual showcase that makes users excited to install and use the plugin.
</objective>

<context>
daplug is a Claude Code plugin with:
- 13 commands (prompt creation, execution, quota checking, multi-model delegation)
- 7 skills (worktree management, tmux sessions, AI usage tracking)
- 5 agents (build optimizers, infrastructure troubleshooters)

Current README has basic feature tables but lacks visual demos or usage examples.
</context>

<research>
Before implementing, explore and understand:
1. @README.md - Current structure and content
2. @commands/*.md - Command capabilities for demo scenarios
3. @skills/*/SKILL.md - Skill capabilities for demo scenarios
4. VHS installation requirements (vhs, ffmpeg, ttyd)
</research>

<requirements>
## VHS Installation (if needed)
```bash
# Check if vhs is installed
which vhs || {
  echo "Installing VHS..."
  brew install vhs || go install github.com/charmbracelet/vhs@latest
}
```

## Create Demo GIFs
Create a `demos/` directory with VHS tape files for these showcase scenarios:

### 1. demos/create-and-run-prompt.tape
Showcase the core workflow:
- `/create-prompt "add a login form with email validation"`
- Show the intelligent prompt generation
- `/run-prompt 001 --model codex`
- Show model selection menu

### 2. demos/multi-model-delegation.tape
Show parallel execution across AI models:
- Create multiple prompts
- `/run-prompt 001 002 003 --parallel --model gemini`
- Show quota awareness with cclimits

### 3. demos/worktree-isolation.tape
Demonstrate isolated development:
- `/run-prompt 005 --worktree`
- Show worktree creation
- Show concurrent main branch work

### 4. demos/verification-loop.tape
Show the retry-until-success pattern:
- `/run-prompt 010 --loop --max-iterations 5`
- Show VERIFICATION_COMPLETE marker detection
- Show iteration status

### 5. demos/quota-awareness.tape
Show AI usage tracking:
- `/cclimits` 
- Show quota percentages for Claude, Codex, Gemini, Z.AI
- Show model recommendations based on availability

### 6. demos/llms-txt-creation.tape
Show documentation generation:
- `/create-llms-txt pydantic-ai`
- Show prompt creation in llms_txt repo
- Show cross-repo execution

## Tape File Standards

Use consistent settings across all demos:
```tape
Output demos/<name>.gif
Set FontSize 22
Set Width 1400
Set Height 800
Set Theme "Dracula"
Set TypingSpeed 80ms
Set Framerate 30
Set WindowBar Colorful
```

Add strategic pauses:
- `Sleep 500ms` after typing commands
- `Sleep 2s` after output displays
- `Sleep 3s` for complex output to be read

Use `Hide/Show` for setup steps if needed.

## README Updates

### Add "Showcase" Section After "What's Included"
Structure:
```markdown
## Showcase

### Create & Execute Prompts
![create-prompt demo](demos/create-and-run-prompt.gif)

> `/create-prompt` generates XML-structured prompts optimized for each task type...

### Multi-Model Delegation
![multi-model demo](demos/multi-model-delegation.gif)

> Run prompts across Claude, Codex, Gemini, or Z.AI...

### Worktree Isolation
![worktree demo](demos/worktree-isolation.gif)

> Execute prompts in isolated git worktrees...

### Verification Loops
![loop demo](demos/verification-loop.gif)

> Re-run prompts until tests pass with `--loop`...

### Quota Awareness
![quota demo](demos/quota-awareness.gif)

> Check usage across all AI CLIs...
```

### Add Quick Examples Section
After Showcase, add runnable command examples:
```markdown
## Quick Examples

### Generate a Feature Prompt
\`\`\`bash
# In Claude Code:
/create-prompt "add user authentication with JWT"
\`\`\`

### Run Across Multiple Models
\`\`\`bash
/run-prompt 005 --model codex        # OpenAI Codex
/run-prompt 005 --model gemini       # Google Gemini 3 Flash
/run-prompt 005 --model zai          # Z.AI GLM-4.7
\`\`\`

### Parallel Execution
\`\`\`bash
/run-prompt 001 002 003 --parallel --worktree
\`\`\`

### Check Quota Before Running
\`\`\`bash
/cclimits
# Shows: Claude: 18% | Codex: 0% | Gemini: 7% | Z.AI: 1%
\`\`\`
```
</requirements>

<implementation>
1. Create `demos/` directory
2. Create tape files with realistic, impressive scenarios
3. Render all GIFs: `for f in demos/*.tape; do vhs "$f"; done`
4. Optimize GIFs: `gifsicle -O3 --colors 256 demos/*.gif`
5. Update README.md with Showcase and Quick Examples sections
6. Ensure GIFs are referenced with relative paths
</implementation>

<constraints>
- Keep tape files realistic - commands should work in actual daplug usage
- GIFs should be <2MB each after optimization (reduce framerate to 30)
- Don't show actual API keys or sensitive data
- Use Hide/Show to skip slow operations (npm install, etc.)
- Focus on visual impact - these are marketing demos
</constraints>

<verification>
Before marking complete, verify:
- [ ] All tape files exist in demos/
- [ ] All GIFs render successfully: `for f in demos/*.tape; do vhs "$f" || exit 1; done`
- [ ] README has Showcase section with working image references
- [ ] GIFs are under 2MB each: `ls -lh demos/*.gif`
- [ ] README renders correctly in preview

**Unit Tests:** Not applicable (documentation task)
</verification>

<success_criteria>
- 5+ animated GIFs demonstrating key features
- README has compelling Showcase section
- Quick Examples section with copy-paste commands
- All GIFs load in GitHub README preview
</success_criteria>
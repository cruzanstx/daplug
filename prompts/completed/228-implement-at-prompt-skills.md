<objective>
Implement two new daplug skills for agent teams orchestration:
1. `/create-at-prompt` — creates agent-team orchestrated prompts (orchestrator + sub-prompts)
2. `/run-at-prompt` — runs existing prompts with agent team orchestration (group syntax + auto-deps)

These skills enable Claude Code agent teams to coordinate multi-CLI prompt execution across Claude, OpenCode, Codex, Gemini, and other AI coding CLIs.
</objective>

<context>
**Prerequisite**: Read the design documentation first:
`./llms_txt/tools/ai-cli/claude-code/daplug-agent-teams-orchestration.llms-full.txt`

This was created by prompt 227 and contains the full architecture, syntax, and examples.

**daplug plugin location**: Find the plugin root via:
```bash
PLUGIN_ROOT=$(jq -r '.plugins."daplug@cruzanstx"[0].installPath' ~/.claude/plugins/installed_plugins.json)
```

**Existing skills to study** (these are the patterns to follow):
- `$PLUGIN_ROOT/skills/prompt-executor/` — How prompts are executed (model routing, worktrees, tmux, loops)
- `$PLUGIN_ROOT/skills/prompt-manager/` — How prompts are created/managed (CRUD operations)
- `$PLUGIN_ROOT/skills/sprint/` — How multi-prompt orchestration works (sequential execution, state tracking)
- `$PLUGIN_ROOT/skills/worktree/` — How git worktrees are managed
- `$PLUGIN_ROOT/skills/config-reader/` — How configuration is read

**Existing commands to study** (these are the UX patterns to follow):
- Check for existing command files in the plugin marketplace or commands directory
- The `/create-prompt` command is defined in the skill system and loaded into Claude Code as a full prompt

**Claude Agent Teams reference**:
- `./llms_txt/tools/ai-cli/claude-code/claude-code-agent-teams.llms-full.txt` — Task() API, agent archetypes
- `./llms_txt/tools/ai-cli/claude-code/claude-code-agent-orchestration.llms-full.txt` — Orchestration patterns

**Key existing infrastructure**:
- Worktree dir: configured via `worktree_dir` in daplug_config
- tmux: used for background execution
- Verification loops: `--loop` flag with `--max-iterations`
- CLI logs: `~/.claude/cli-logs/`
- Config reader: `$PLUGIN_ROOT/skills/config-reader/scripts/config.py`
</context>

<requirements>
## Deliverable 1: `/create-at-prompt` Skill

### SKILL.md
Create `$PLUGIN_ROOT/skills/at-prompt-creator/SKILL.md` with:
- Frontmatter (name, description, allowed-tools)
- Full instructions for generating orchestrated prompts
- Template for orchestrator prompt structure (phases, delegation blocks, merge criteria)
- Integration with prompt-manager for file creation

### Core Logic
The skill should:
1. Accept a task description (same input as /create-prompt)
2. Analyze complexity and determine sub-task decomposition
3. Generate:
   - Main orchestrator prompt (contains Task() calls and /run-prompt delegation)
   - N sub-prompts (focused, single-agent, executable independently)
4. Save all prompts via prompt-manager
5. Present execution options (similar to /create-prompt decision tree)

### Orchestrator Prompt Template
The generated orchestrator prompt should follow this structure:
```xml
<orchestration>
  <phase name="plan">
    <!-- Claude native research/planning -->
  </phase>
  <phase name="execute" strategy="parallel|sequential">
    <!-- Delegation to sub-prompts via /run-prompt -->
    <delegate prompt="228a" model="opencode" flags="--worktree" />
    <delegate prompt="228b" model="codex" flags="--worktree --loop" />
  </phase>
  <phase name="validate">
    <!-- Claude native validation/merge -->
  </phase>
</orchestration>
```

## Deliverable 2: `/run-at-prompt` Skill

### SKILL.md
Create `$PLUGIN_ROOT/skills/at-prompt-runner/SKILL.md` with:
- Frontmatter (name, description, allowed-tools)
- Full instructions for orchestrated prompt execution
- Group syntax parsing reference
- Auto-deps mode documentation

### Scripts
Create `$PLUGIN_ROOT/skills/at-prompt-runner/scripts/at_runner.py` with:

**Group Syntax Parser**:
```
Input: "220,221 -> 222,223 -> 224"
Output: [
  {"phase": 1, "prompts": [220, 221], "strategy": "parallel"},
  {"phase": 2, "prompts": [222, 223], "strategy": "parallel"},
  {"phase": 3, "prompts": [224], "strategy": "parallel"}
]
```

**CLI Interface**:
```bash
# Parse group syntax
python3 at_runner.py parse "220,221 -> 222,223 -> 224"

# Parse with auto-deps flag
python3 at_runner.py parse "220 221 222" --auto-deps

# Get execution plan as JSON
python3 at_runner.py plan "220,221 -> 222" --model codex --json

# Validate that all referenced prompts exist
python3 at_runner.py validate "220,221 -> 222"
```

**Key Functions**:
- `parse_group_syntax(input_str)` → list of phases with prompt numbers and strategy
- `validate_prompts(phases)` → verify all referenced prompts exist via prompt-manager
- `build_execution_plan(phases, model, flags)` → JSON plan ready for the orchestrator
- `format_run_commands(plan)` → list of `/run-prompt` invocations per phase

### Execution Flow & Model Tiering
When `/run-at-prompt` is invoked, the orchestrator (sonnet) coordinates everything:

1. **Parse input**: Group syntax or space-separated with --auto-deps
2. **Validate**: All prompts exist, readable
3. **If --auto-deps**:
   - Read all prompt contents via prompt-manager
   - Spawn **at-planner** agent (sonnet) to analyze dependencies and output group syntax
   - Confirm with user before executing
4. **Build execution plan**: Convert phases to /run-prompt commands
5. **Execute phase by phase** (model tiering in action):
   - For each prompt in the phase, spawn a **at-monitor** agent (**haiku**, `run_in_background: true`)
   - Each haiku monitor: launches /run-prompt via tmux, watches for completion
   - Monitors produce structured **Execution Reports** with triage flags
   - Orchestrator (sonnet) collects all reports via `TaskOutput()`
   - Orchestrator reads triage flags and decides:
     - All OK → proceed to merge/next phase
     - ESCALATE flags → read referenced log lines, spawn **at-fixer** (opus) if complex
     - File conflicts → spawn **at-merger** (sonnet) with both worktree paths
   - Proceed to next phase only when all prompts in current phase are resolved
6. **Final validation** (if --validate): **at-validator** agent (sonnet) reviews all outputs across all phases

### Why Haiku Monitors Work
Monitor agents are purely mechanical — they launch a command, watch stdout/logs, and fill in a report template. They do NOT:
- Analyze code quality
- Make architectural decisions
- Debug failures
- Decide whether to retry

They DO:
- Detect pass/fail from exit codes
- Grep logs for error patterns
- Include log paths and line numbers in reports
- Flag anything that looks wrong with "ESCALATE"

This keeps monitor costs minimal while ensuring the orchestrator (sonnet) always has the evidence it needs to make good decisions.

### Flags
- `--model <model>` — Default model for all sub-prompts (can be overridden per-prompt)
- `--auto-deps` — Let AI determine execution order
- `--validate` — Add validation phase at the end
- `--worktree` — Use worktrees for isolation (recommended for parallel)
- `--loop` — Enable verification loops per sub-prompt
- `--dry-run` — Show execution plan without running

## Deliverable 3: Command Registration

Create or update the necessary command/skill registration so that:
- `/create-at-prompt <description>` invokes the at-prompt-creator skill
- `/run-at-prompt <group-syntax> [flags]` invokes the at-prompt-runner skill

Follow the exact pattern used by existing daplug commands for registration.

## Deliverable 4: Agent Definition Files

Create `.claude/agents/` files for the orchestration roles. **Model tiering is critical** — use the cheapest model that can handle each role:

### at-monitor.md (model: haiku)
- **Purpose**: Launch /run-prompt commands, watch for completion, produce triage reports
- **Tools**: Bash (read-only: tmux, tail, grep, cat), Read, Grep
- **NO write tools** — monitors are read-only watchers
- **Output format**: Structured Execution Report (see template below)
- **Triage flag rules**:
  - Exit code != 0 → ESCALATE
  - "FAIL" / "error" / "conflict" in log tail → ESCALATE with log path + line numbers
  - Duration exceeded 2x expected → ESCALATE (might be stuck)
  - Worktree has uncommitted changes after exit → ESCALATE
  - Multiple prompts touched overlapping files → ESCALATE to merger
  - Clean exit + all checks pass → OK

**Execution Report Template** (haiku must output this format):
```
## Prompt {N} Execution Report
- **Status**: PASS|FAIL (exit code {N})
- **Model**: {model used}
- **Duration**: {time}
- **Worktree**: {path}
- **Log**: {full log path}
- **tmux session**: {session name} (alive|dead)

### Last 20 lines of output:
{log tail}

### Triage Flags:
- ESCALATE|OK: {description} (see log lines {N}-{N} if applicable)
```

### at-planner.md (model: sonnet)
- **Purpose**: Decomposes tasks, identifies dependencies, builds execution plans
- **Tools**: Read, Grep, Glob (read-only — planning only, no execution)
- **Used for**: `--auto-deps` mode — reads prompt contents and determines execution order

### at-validator.md (model: sonnet)
- **Purpose**: Reviews outputs from parallel workstreams, checks for conflicts
- **Tools**: Read, Grep, Glob, Bash (git diff, git status — read-only git operations)
- **Input**: Execution reports from monitor agents + worktree paths
- **Decides**: Pass (proceed to next phase), Retry (re-run specific prompt), Escalate (needs opus fixer)

### at-merger.md (model: sonnet)
- **Purpose**: Combines results from parallel branches (git merge coordination)
- **Tools**: Read, Bash (git merge, git checkout, git diff), Write, Edit
- **Has write access** — needs to resolve merge conflicts

### at-fixer.md (model: opus)
- **Purpose**: Handles complex failures that sonnet cannot resolve
- **Tools**: Full tool access (Read, Write, Edit, Bash, Grep, Glob)
- **Only spun up on-demand** when validator escalates
- **Input**: The validator's escalation report + log path + line references
- **The validator should explicitly say**: "Read log at {path}, lines {N}-{N}. The issue is {description}. Attempted fix: {what was tried}."

Each agent file should have proper frontmatter with bounded tools (least privilege).
</requirements>

<implementation>
**Study existing patterns first** — before writing any code:
1. Read the prompt-executor SKILL.md and executor.py thoroughly
2. Read the sprint SKILL.md and sprint.py thoroughly
3. Read the prompt-manager scripts/manager.py for the Python CLI pattern
4. Read at least 2 existing agent files in .claude/agents/ (if they exist)

**Follow existing conventions**:
- Python scripts should use argparse, JSON output with --json flag
- SKILL.md frontmatter must match existing patterns
- Error handling should be consistent with other skills
- Use config-reader for all configuration access

**Keep it focused**:
- The at_runner.py script handles parsing, validation, and plan building
- The SKILL.md handles the Claude-facing orchestration logic
- The agent .md files handle the specialized roles
- Execution delegates to the existing prompt-executor infrastructure

**Model tiering is mandatory**:
- Monitor agents MUST use `model: "haiku"` in Task() calls
- Planner, validator, merger agents use `model: "sonnet"` (default)
- Fixer agent uses `model: "opus"` — only spawned on escalation, never proactively
- The orchestrator itself runs as sonnet (the SKILL.md will be executed by whatever model the user is running, but Task() calls should specify models explicitly)

**Handoff quality is critical**:
- Haiku monitor reports MUST include: log file path, exit code, last 20 lines of output, and triage flags
- Triage flags MUST include line number references when flagging log issues (e.g., "see log lines 847-892")
- The orchestrator should never have to search for context — everything it needs should be in the report

**Do NOT**:
- Modify existing skills (prompt-executor, prompt-manager, sprint)
- Duplicate functionality that already exists
- Over-engineer the auto-deps feature (start simple — read prompts, identify keywords, suggest order)
- Create complex state management (let the orchestrator prompt handle state in-context)
- Use sonnet/opus for monitor agents (haiku is sufficient and much cheaper)
- Let monitors make decisions — they only report and flag
</implementation>

<output>
Create/modify these files:

**New skill files:**
- `$PLUGIN_ROOT/skills/at-prompt-creator/SKILL.md`
- `$PLUGIN_ROOT/skills/at-prompt-runner/SKILL.md`
- `$PLUGIN_ROOT/skills/at-prompt-runner/scripts/at_runner.py`

**New agent files:**
- `.claude/agents/at-planner.md`
- `.claude/agents/at-validator.md`
- `.claude/agents/at-merger.md`

**New command files** (follow existing pattern for command registration):
- Whatever pattern the plugin uses for command registration

**Note:** The $PLUGIN_ROOT is the daplug plugin install path. Use the jq command from context to resolve it.
</output>

<verification>
After implementation:

1. **Syntax parser tests**:
```bash
python3 $PLUGIN_ROOT/skills/at-prompt-runner/scripts/at_runner.py parse "220,221 -> 222,223 -> 224"
python3 $PLUGIN_ROOT/skills/at-prompt-runner/scripts/at_runner.py parse "220 221 222" --auto-deps
python3 $PLUGIN_ROOT/skills/at-prompt-runner/scripts/at_runner.py parse "220"
python3 $PLUGIN_ROOT/skills/at-prompt-runner/scripts/at_runner.py parse "220,221 -> 222 -> 223,224,225 -> 226"
```

2. **Validation tests**:
```bash
# Should succeed (if prompts exist)
python3 $PLUGIN_ROOT/skills/at-prompt-runner/scripts/at_runner.py validate "215"

# Should fail gracefully (non-existent prompt)  
python3 $PLUGIN_ROOT/skills/at-prompt-runner/scripts/at_runner.py validate "999"
```

3. **Plan generation**:
```bash
python3 $PLUGIN_ROOT/skills/at-prompt-runner/scripts/at_runner.py plan "215 -> 227" --model codex --json
```

4. **SKILL.md validation**:
- Verify frontmatter has name, description, allowed-tools
- Verify content is comprehensive and follows existing patterns

5. **Agent files validation**:
- Verify each agent .md has proper frontmatter
- Verify tool lists follow least-privilege principle

6. **Dry run test** (integration):
- The /run-at-prompt skill with --dry-run should output the execution plan without running anything
</verification>

<success_criteria>
- Group syntax parser correctly handles all documented patterns
- at_runner.py CLI works with parse, validate, plan subcommands
- SKILL.md files are comprehensive and follow existing daplug patterns
- Agent files have proper frontmatter and bounded tools
- --dry-run shows a clear, readable execution plan
- All verification tests pass
- No existing skills were modified
</success_criteria>
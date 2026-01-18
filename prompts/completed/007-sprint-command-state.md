<objective>
Create the `/sprint` command definition and implement state management with sub-commands for the daplug sprint planning feature.

This completes the sprint feature by providing the user-facing command interface and persistent state tracking for long-running sprint executions.
</objective>

<context>
Review these files for patterns:
@commands/run-prompt.md - Command definition pattern
@commands/prompts.md - Complex command with sub-commands
@skills/sprint/SKILL.md - The skill this command invokes (created in previous prompt)
@skills/sprint/scripts/sprint.py - Core implementation to extend

Full specification: @daplug_sprint_suggestion.md
</context>

<requirements>
### Part 1: Command Definition

Create `commands/sprint.md` with:

**Frontmatter:**
```yaml
---
name: sprint
description: Automated sprint planning from technical specifications
argument-hint: "<spec-file-or-text> [options] | <sub-command>"
---
```

**Command Instructions:**
- Parse arguments to detect sub-command vs main command
- For main command: invoke sprint skill with spec and options
- For sub-commands: invoke appropriate handler

**Supported syntax:**
```bash
# Main command
/sprint ./docs/technical-spec.md --worktree --loop
/sprint "Build a REST API with auth, CRUD, and admin dashboard"
/sprint ./spec.md --dry-run
/sprint ./spec.md --auto-execute

# Sub-commands
/sprint status              # View current sprint status
/sprint add "Implement caching layer"  # Add prompt to sprint
/sprint remove 005          # Remove prompt from sprint
/sprint replan              # Re-analyze dependencies
/sprint pause               # Pause sprint (save state)
/sprint resume              # Resume from last phase
/sprint cancel              # Cancel sprint (cleanup worktrees)
/sprint history             # Show sprint history
```

### Part 2: State Management

Extend `skills/sprint/scripts/sprint.py` with state tracking:

**State File: `.sprint-state.json`**
```python
@dataclass
class SprintState:
    sprint_id: str           # e.g., "todo-app-2026-01-17"
    created_at: str          # ISO timestamp
    spec_hash: str           # Hash of original spec for change detection
    spec_path: str           # Original spec file path
    prompts: list[dict]      # [{id, status, worktree, merged, model}]
    current_phase: int       # Current execution phase
    total_phases: int        # Total phases in plan
    model_usage: dict        # {model: minutes_used}
    paused_at: str | None    # Timestamp if paused
    
def load_state(state_file: str = ".sprint-state.json") -> SprintState | None
def save_state(state: SprintState, state_file: str = ".sprint-state.json")
def update_prompt_status(state: SprintState, prompt_id: str, status: str)
```

**Prompt statuses:** pending, in_progress, completed, failed, skipped

### Part 3: Sub-command Implementations

Add these functions to sprint.py:

```python
def cmd_status(state_file: str) -> None:
    """
    Display current sprint status:
    - Sprint ID and creation time
    - Current phase / total phases
    - Prompt completion status (table)
    - Model usage summary
    - Next steps
    """

def cmd_add(description: str, state_file: str) -> None:
    """
    Add a new prompt to the current sprint:
    - Generate prompt using prompt-manager
    - Re-analyze dependencies
    - Update execution plan
    - Update state file
    """

def cmd_remove(prompt_id: str, state_file: str) -> None:
    """
    Remove a prompt from the sprint:
    - Mark as skipped (dont delete file)
    - Re-analyze dependencies
    - Update execution plan
    - Warn if other prompts depend on it
    """

def cmd_replan(state_file: str) -> None:
    """
    Re-analyze dependencies after changes:
    - Re-read all prompt files
    - Rebuild dependency graph
    - Reassign models based on current availability
    - Regenerate execution plan
    """

def cmd_pause(state_file: str) -> None:
    """
    Pause the sprint:
    - Save current state with paused_at timestamp
    - List any in-progress prompts (they continue running)
    - Output resume instructions
    """

def cmd_resume(state_file: str) -> None:
    """
    Resume a paused sprint:
    - Load state and verify it was paused
    - Check status of any previously in-progress prompts
    - Continue from current phase
    - Clear paused_at timestamp
    """

def cmd_cancel(state_file: str) -> None:
    """
    Cancel the sprint:
    - Prompt for confirmation
    - Clean up any worktrees created by sprint
    - Archive state file to .sprint-state.json.cancelled
    - Output summary of what was completed
    """

def cmd_history(state_dir: str = ".") -> None:
    """
    Show sprint history:
    - List all .sprint-state.json* files
    - Show summary for each (id, date, prompts completed)
    - Indicate which is current (if any)
    """
```

### Part 4: Auto-Execute Mode

When `--auto-execute` is passed:
```python
def auto_execute(state: SprintState, options: dict) -> None:
    """
    Execute the sprint automatically:
    1. Initialize state file
    2. For each phase:
       a. Get prompts ready for this phase
       b. Execute via /run-prompt (parallel within phase)
       c. Wait for completion
       d. Update state
       e. Check for failures, offer retry or skip
    3. Generate final summary
    
    Handle interruptions gracefully (Ctrl+C saves state).
    """
```

### Part 5: Integration with Existing Commands

**With /run-prompt:**
- Generate commands using existing /run-prompt syntax
- Pass --worktree and --loop flags as configured
- Use --model flag with assigned models

**With /worktree:**
- Track worktree names in state: `sprint-{sprint_id}-{prompt_id}`
- Clean up worktrees on cancel
- Merge completed worktrees back to main

**With /cclimits:**
- Check model availability before starting each phase
- Adjust model assignments if preferred model is rate-limited
- Log model usage in state for tracking
</requirements>

<implementation>
**Command file pattern** (from run-prompt.md):
- YAML frontmatter with name, description, argument-hint
- Detect sub-command vs main command in instructions
- Invoke skill with appropriate arguments

**State management patterns:**
- Use JSON for state file (human-readable, easy to debug)
- Atomic writes: write to temp file, then rename
- Lock file for concurrent access prevention
- Include schema version for future migrations

**Error handling:**
- Clear error messages for common issues
- Suggest fixes (e.g., "No active sprint. Run /sprint <spec> first")
- Graceful degradation if state file is corrupted

**Progress output:**
- Use tables for status display (prompt-manager uses tabulate)
- Show progress bars or percentages where appropriate
- Color output for terminal (optional, degrade gracefully)
</implementation>

<output>
Create/modify these files:

`./commands/sprint.md`:
- Complete command definition
- Argument parsing for main command and sub-commands
- Clear usage examples

`./skills/sprint/scripts/sprint.py` (extend):
- Add SprintState dataclass and state management functions
- Add all sub-command implementations
- Add auto-execute functionality
- Add integration hooks for worktree and cclimits
</output>

<verification>
**Command Tests:**
```bash
cd /storage/projects/docker/daplug

# Test main command (dry run)
# Note: This would be invoked via Claude Code, test the skill directly:
python3 skills/sprint/scripts/sprint.py "Build a todo app" --dry-run

# Test sub-commands
# First create a sprint to have state:
python3 skills/sprint/scripts/sprint.py "Build a todo app" --output-dir /tmp/test-prompts

# Then test sub-commands:
python3 skills/sprint/scripts/sprint.py status
python3 skills/sprint/scripts/sprint.py add "Add caching layer"
python3 skills/sprint/scripts/sprint.py replan
python3 skills/sprint/scripts/sprint.py pause
python3 skills/sprint/scripts/sprint.py resume
python3 skills/sprint/scripts/sprint.py history
python3 skills/sprint/scripts/sprint.py cancel --yes
```

**State Management Tests:**
```bash
# Verify state file is created
cat .sprint-state.json | jq .

# Verify state updates correctly
python3 skills/sprint/scripts/sprint.py status
# Should show prompts table with statuses
```

**Integration Tests:**
```bash
# Test that generated commands are valid
python3 skills/sprint/scripts/sprint.py "Build API" --dry-run | grep "run-prompt"
# Should output valid /run-prompt commands
```

**Unit Tests** (add to skills/sprint/tests/):
- [ ] State serialization/deserialization
- [ ] Prompt status transitions
- [ ] Sub-command argument parsing
- [ ] Worktree name generation
- [ ] Model availability fallback logic
</verification>

<success_criteria>
- [ ] commands/sprint.md follows existing command patterns
- [ ] All 8 sub-commands are implemented and documented
- [ ] State file persists across sessions correctly
- [ ] /sprint status shows clear, useful information
- [ ] /sprint pause and resume work correctly
- [ ] /sprint cancel cleans up worktrees
- [ ] --auto-execute runs prompts in correct order
- [ ] Integration with /run-prompt generates valid commands
- [ ] Graceful error handling for edge cases
- [ ] Unit tests pass
</success_criteria>
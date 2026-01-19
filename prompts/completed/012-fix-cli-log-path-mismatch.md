<objective>
Fix the CLI log path inconsistency in daplug executor where the displayed log path does not match
the actual log file created. This causes confusion when users try to tail/monitor logs.
</objective>

<context>
The prompt-executor (`skills/prompt-executor/scripts/executor.py`) shows log paths in the
Execution Summary table, but the actual files created have different names/timestamps.

**Current behavior (broken):**
1. Execution Summary shows: `~/.claude/cli-logs/gpt52-high-008-20260119-150550.log`
2. But actual files created are:
   - `gpt52-high-008-iter1-20260119-150555.log` (5 seconds later!)
   - `gpt52-high-008-loop-20260119-150554.log`
3. The file shown in the summary (`gpt52-high-008-20260119-150550.log`) never exists

**Root cause hypothesis:**
- Timestamp is generated when planning/displaying, but file is created later during actual execution
- Loop mode creates iteration-specific logs (`-iter1-`, `-iter2-`) instead of the base log
- The timestamp drifts between planning and execution phases

**Additional issue:**
- Claude subagent runs log to `/tmp/` instead of `~/.claude/cli-logs/`
- This inconsistency makes it hard to find logs across different execution modes
</context>

<research>
Before implementing fixes, investigate the executor code to understand:

1. **Where is the log path generated?** Find all places that construct log file paths
2. **Where is the log file actually created?** Find file open/write operations  
3. **What is the flow for loop mode?** How do iteration logs get named?
4. **Where do Claude subagent logs go?** Find the Task tool invocation and its output handling
5. **Is there a single source of truth for the timestamp?** Or is it regenerated multiple times?

Key files to examine:
- `skills/prompt-executor/scripts/executor.py` - main executor logic
- `skills/prompt-executor/SKILL.md` - may document expected behavior
- Look for: `cli-logs`, `log_path`, `log_file`, timestamp generation, `strftime`
</research>

<requirements>
1. **Single timestamp source**: Generate timestamp ONCE at the start of execution and reuse it everywhere
2. **Displayed path = actual path**: The log path shown in Execution Summary must be the exact file that gets created
3. **Loop mode clarity**: For loop executions, either:
   - Show the loop log path (which aggregates all iterations), OR
   - Show iteration log paths as they are created
4. **Consistent log directory**: All execution modes (codex, gemini, zai, claude subagent) should log to `~/.claude/cli-logs/`
5. **Backward compatible**: Dont break existing log naming conventions; just ensure displayed = actual
</requirements>

<implementation>
Likely changes needed:

1. **Create timestamp at execution start**:
   ```python
   execution_timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
   # Use this SAME timestamp for all log path generation
   ```

2. **Pass timestamp through the execution chain**:
   - From initial planning → to CLI launch → to loop iterations
   - Avoid regenerating timestamp at each step

3. **Fix loop mode log paths**:
   - Either create the base log file that is displayed, OR
   - Update the display to show the actual iteration log paths

4. **Fix Claude subagent logging**:
   - Find where Task tool is invoked for Claude runs
   - Ensure output goes to `~/.claude/cli-logs/claude-{prompt}-{timestamp}.log`

5. **Add validation** (optional but recommended):
   - After displaying log path, verify the file exists or will be created at that exact path
</implementation>

<verification>
Test each fix:

1. **Non-loop execution**:
   ```bash
   # Run a simple prompt without loop
   python3 executor.py 001 --model codex --run
   # Verify: displayed log path exists and contains output
   ```

2. **Loop execution**:
   ```bash
   # Run with loop mode
   python3 executor.py 001 --model codex --run --loop
   # Verify: displayed log path(s) exist and match what is shown
   ```

3. **Claude subagent** (if applicable):
   ```bash
   # Run via Claude
   # Verify: log appears in ~/.claude/cli-logs/ not /tmp/
   ```

4. **Timestamp consistency**:
   ```bash
   # Check that timestamp in filename matches timestamp shown
   ls -la ~/.claude/cli-logs/*.log | tail -5
   ```
</verification>

<success_criteria>
- [ ] Running `--model codex` shows log path X, and file X exists with actual output
- [ ] Running `--model codex --loop` shows log path(s) that actually exist
- [ ] All log files go to `~/.claude/cli-logs/` regardless of execution mode
- [ ] No more "file not found" when trying to tail the displayed log path
- [ ] Existing log naming convention preserved (model-prompt-timestamp.log)
</success_criteria>
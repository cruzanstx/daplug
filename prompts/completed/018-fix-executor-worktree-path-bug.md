<objective>
Fix the executor worktree path mismatch bug where the loop state file (`~/.claude/loop-state/{number}.json`) 
stores an incorrect `execution_cwd` path when worktree conflicts are resolved.

This bug causes verification loops to fail because subsequent iterations reference a non-existent worktree path.
</objective>

<context>
**Bug Observed:**
When running `/run-prompt 014 --model codex-xhigh --worktree --loop`:

1. An old worktree existed at `daplug-prompt-014-20260119-181703`
2. User removed it and executor created new worktree at `daplug-prompt-014-20260119-181817`
3. Loop state file was written with WRONG path: `execution_cwd: ".../181703"` (old path)
4. Iterations 2 and 3 failed immediately because they tried to execute in non-existent directory

**Evidence from loop state:**
```json
{
  "execution_cwd": "/storage/projects/docker/daplug/.worktrees/daplug-prompt-014-20260119-181703",  // WRONG
  "history": [
    {"iteration": 1, "exit_code": 0, "log_file": "...181704.log"},  // Note: different timestamp
    {"iteration": 2, "exit_code": -1},  // Failed - path doesnt exist
    {"iteration": 3, "exit_code": -1}   // Failed - path doesnt exist
  ]
}
```

**Root Cause (suspected):**
The executor writes the loop state BEFORE resolving worktree conflicts. When a conflict is detected and 
the user chooses to create a new worktree, the state file is not updated with the new path.

**Files to examine:**
- `skills/prompt-executor/scripts/executor.py` - Main executor logic
- Look for: loop state initialization, worktree conflict resolution, `execution_cwd` assignment
</context>

<requirements>
1. **Identify the exact location** where `execution_cwd` is set in loop state
2. **Ensure the loop state is written AFTER** worktree path is finalized (not before conflict resolution)
3. **Add validation** to verify `execution_cwd` exists before starting loop iterations
4. **Handle the conflict resolution flow** properly:
   - When `--worktree` is used and a conflict is detected
   - After user resolves conflict (remove/reuse/increment)
   - The final resolved path must be written to loop state

5. **Add a pre-iteration check** in the loop runner:
   - Before each iteration, verify `execution_cwd` exists
   - If not, fail with a clear error message instead of exit_code -1
</requirements>

<implementation>
1. Find where `LoopState` or equivalent is initialized
2. Trace the worktree creation flow to find where the path is determined
3. Ensure loop state is updated with the FINAL worktree path after any conflict resolution
4. Add a `Path(execution_cwd).exists()` check before spawning CLI process
5. Write tests if the existing test suite covers loop functionality
</implementation>

<verification>
After fixing, verify with this scenario:

```bash
# 1. Create a worktree that will conflict
cd /storage/projects/docker/daplug
git worktree add .worktrees/test-conflict-worktree -b test-conflict-branch

# 2. Run executor with --worktree --loop (should detect conflict)
# 3. Choose to remove the conflicting worktree
# 4. Verify loop state has CORRECT execution_cwd (new path, not old)
# 5. Verify all loop iterations can find the directory

# Clean up
git worktree remove .worktrees/test-conflict-worktree
git branch -D test-conflict-branch
```

Before completing, verify:
- [ ] Loop state `execution_cwd` matches actual worktree path
- [ ] Subsequent iterations execute in correct directory
- [ ] Clear error if `execution_cwd` doesnt exist
</verification>

<success_criteria>
- Loop state always contains the correct, final worktree path
- Iterations 2+ execute in the same directory as iteration 1
- No more "path mismatch" failures in verification loops
</success_criteria>
<objective>
Add automatic worktree permission setup to executor.py so that when `--model claude --worktree` is used, the resolved worktree path automatically gets the necessary permissions in `~/.claude/settings.json`.

This eliminates the manual step of configuring permissions for Task subagents to access worktree directories.
</objective>

<context>
When running `/run-prompt --model claude --worktree`:
- The `claude` model uses Task tool to spawn a subagent (not external CLI)
- Task subagents use global Claude Code permissions from `~/.claude/settings.json`
- Worktree directories (often outside the project) are not in global permissions by default
- This causes permission failures when the subagent tries to read/write/bash in the worktree

The worktree_dir config can be:
- Relative: `./worktrees`, `../worktrees`, `.worktrees/`
- Absolute: `/storage/projects/docker/worktrees`
- User-level (~/.claude/CLAUDE.md) or project-level (./CLAUDE.md)

@skills/prompt-executor/scripts/executor.py
@skills/config-reader/scripts/config.py
</context>

<requirements>
1. Create a function `ensure_worktree_permissions(worktree_dir: str, repo_root: str)` that:
   - Normalizes the path to absolute (handle `./`, `../`, `~`, trailing slashes)
   - Reads `~/.claude/settings.json`
   - Checks if permissions already exist for this absolute path
   - If not, adds:
     - `Read({abs_path}/**)` to `permissions.allow`
     - `Edit({abs_path}/**)` to `permissions.allow`
     - `Write({abs_path}/**)` to `permissions.allow`
     - `{abs_path}` to `permissions.additionalDirectories`
   - Writes back to settings.json only if changes were made

2. Call this function when ALL of these conditions are true:
   - `--model claude` is specified (stdin_mode is None)
   - `--worktree` flag is used
   - `--run` flag is used (actually executing, not just getting info)

3. Path normalization must handle:
   - `./worktrees` → `/repo/root/worktrees`
   - `../worktrees` → `/repo/parent/worktrees`
   - `~/worktrees` → `/home/user/worktrees`
   - `/abs/path/worktrees/` → `/abs/path/worktrees` (strip trailing slash)
   - Already absolute paths unchanged (except trailing slash)

4. All operations must be pure Python:
   - Use `os.path.expanduser()` for ~
   - Use `os.path.join()` and `os.path.normpath()` for relative paths
   - Use `json.load()` / `json.dump()` for settings.json
   - NO subprocess calls
</requirements>

<implementation>
Add the function near other utility functions in executor.py (around line 660, after get_sandbox_add_dirs):

```python
def normalize_worktree_path(worktree_dir: str, repo_root: str) -> str:
    """Normalize worktree path to absolute, handling relative paths and ~."""
    path = worktree_dir
    
    # Expand ~ to home directory
    path = os.path.expanduser(path)
    
    # Make absolute if relative (resolve against repo_root)
    if not os.path.isabs(path):
        path = os.path.join(repo_root, path)
    
    # Normalize . and .. components
    path = os.path.normpath(path)
    
    # Strip trailing slashes for consistency
    path = path.rstrip("/")
    
    return path


def ensure_worktree_permissions(worktree_dir: str, repo_root: str) -> bool:
    """Ensure worktree directory has permissions in Claude settings.
    
    Returns True if permissions were added, False if already existed.
    """
    abs_path = normalize_worktree_path(worktree_dir, repo_root)
    settings_path = os.path.expanduser("~/.claude/settings.json")
    
    # Read existing settings
    try:
        with open(settings_path, "r") as f:
            settings = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        settings = {}
    
    # Ensure structure exists
    if "permissions" not in settings:
        settings["permissions"] = {}
    if "allow" not in settings["permissions"]:
        settings["permissions"]["allow"] = []
    if "additionalDirectories" not in settings["permissions"]:
        settings["permissions"]["additionalDirectories"] = []
    
    # Check if permissions already exist
    read_perm = f"Read({abs_path}/**)"
    if read_perm in settings["permissions"]["allow"]:
        return False  # Already configured
    
    # Add permissions
    settings["permissions"]["allow"].extend([
        f"Read({abs_path}/**)",
        f"Edit({abs_path}/**)",
        f"Write({abs_path}/**)"
    ])
    
    # Add to additionalDirectories if not present
    if abs_path not in settings["permissions"]["additionalDirectories"]:
        settings["permissions"]["additionalDirectories"].append(abs_path)
    
    # Write back
    with open(settings_path, "w") as f:
        json.dump(settings, f, indent=2)
    
    return True
```

Then, in the execution logic where `--model claude --worktree --run` is handled, call:

```python
# Before spawning Task subagent for claude model with worktree
if model == "claude" and worktree_path and args.run:
    worktree_dir = get_worktree_dir_from_config(repo_root)  # or however it is obtained
    if ensure_worktree_permissions(worktree_dir, repo_root):
        # Optionally log that permissions were added
        pass
```

Find the appropriate location in main() or the execution flow where:
- The model is determined to be "claude" (cli_info["stdin_mode"] is None)
- A worktree has been created (worktree_path is set)
- Execution is requested (args.run is True)
</implementation>

<output>
Modify: `./skills/prompt-executor/scripts/executor.py`
- Add `normalize_worktree_path()` function
- Add `ensure_worktree_permissions()` function
- Call permission setup at the right point in execution flow
</output>

<verification>
Test the implementation:

1. **Test path normalization**:
```python
# In Python REPL or test file
from executor import normalize_worktree_path

# Test cases
assert normalize_worktree_path("./worktrees", "/storage/project") == "/storage/project/worktrees"
assert normalize_worktree_path("../worktrees", "/storage/project") == "/storage/worktrees"
assert normalize_worktree_path("~/worktrees", "/any") == os.path.expanduser("~/worktrees")
assert normalize_worktree_path("/abs/path/", "/any") == "/abs/path"
assert normalize_worktree_path(".worktrees/", "/repo") == "/repo/.worktrees"
```

2. **Test permission check** (manual):
```bash
# Before running, check settings.json
cat ~/.claude/settings.json | jq ".permissions"

# Run with claude + worktree
python3 executor.py 001 --model claude --worktree --run

# After running, verify permissions were added
cat ~/.claude/settings.json | jq ".permissions"
```

3. **Verify idempotency**:
- Run the same command twice
- Second run should not duplicate permissions
</verification>

<success_criteria>
- [ ] `normalize_worktree_path()` correctly handles all path formats
- [ ] `ensure_worktree_permissions()` adds permissions only when missing
- [ ] Permissions are correctly formatted: `Read({path}/**)`, `Edit({path}/**)`, `Write({path}/**)`
- [ ] `additionalDirectories` includes the absolute path
- [ ] No subprocess calls - all pure Python
- [ ] Function only triggers for `--model claude --worktree --run`
- [ ] Second run with same worktree_dir does not duplicate permissions
</success_criteria>
---
name: worktree
description: Manage git worktrees for isolated development. Use when user asks to create isolated workspaces, work on multiple branches simultaneously, set up parallel development environments, or clean up old worktrees.
allowed-tools:
  - Bash(git:*)
  - Bash(git worktree:*)
  - Bash(git branch:*)
  - Bash(mkdir:*)
  - Bash(find:*)
  - Bash(realpath:*)
  - Bash(jq:*)
  - Bash(python3:*)
  - Bash(REPO_ROOT=:*)
  - Bash(REPO_NAME=:*)
  - Bash(WORKTREE_PATH=:*)
  - Bash(WORKTREES_DIR=:*)
  - Bash(BRANCH_NAME=:*)
  - Bash(CONFIGURED_DIR=:*)
  - Bash(TIMESTAMP=:*)
  - Bash(\:*)
  - Read
  - Edit
  - Write
  - Glob
  - Grep
---

# Git Worktree Management

Create, list, and manage git worktrees for isolated development environments.

## When to Use This Skill

- User asks to "create an isolated workspace" or "work on multiple branches"
- User wants to "set up a worktree" or "parallel development"
- User asks to "list worktrees" or "clean up worktrees"
- Before running parallel tasks that might conflict

## Configuration

Worktree directory location is configurable per-project via CLAUDE.md.

### Config Format (in CLAUDE.md)

```markdown
<daplug_config>
worktree_dir: /absolute/path/to/worktrees
# OR
worktree_dir: .worktrees/
</daplug_config>
```

### Get Worktree Directory

**This is the canonical way to resolve the worktree directory.** All operations should use this lookup.

```bash
REPO_ROOT=$(git rev-parse --show-toplevel)
PLUGIN_ROOT=$(jq -r '.plugins."daplug@cruzanstx"[0].installPath' ~/.claude/plugins/installed_plugins.json)
CONFIG_READER="$PLUGIN_ROOT/skills/config-reader/scripts/config.py"

# 1. Check for worktree_dir in CLAUDE.md
CONFIGURED_DIR=$(python3 "$CONFIG_READER" get worktree_dir --repo-root "$REPO_ROOT")

if [ -n "$CONFIGURED_DIR" ]; then
    # 2a. Expand relative paths (starts with . or no leading /)
    if [[ "$CONFIGURED_DIR" == .* ]] || [[ "$CONFIGURED_DIR" != /* ]]; then
        WORKTREES_DIR=$(realpath "${REPO_ROOT}/${CONFIGURED_DIR}")
    else
        WORKTREES_DIR="$CONFIGURED_DIR"
    fi
else
    # 2b. No config found - STOP and prompt user (see below)
    echo "NO_CONFIG"
fi
```

**IMPORTANT: If no config exists (`CONFIGURED_DIR` is empty), you MUST prompt the user before proceeding.**
Do NOT silently fall back to a default. Use the "Configure Worktree Directory (Interactive)" section below to ask the user their preference and store it.

### Configure Worktree Directory (Interactive)

When no configuration exists and user needs to set one up:

1. **Ask user for preference** using AskUserQuestion:
   - "Sibling directory (../worktrees/)" - default, outside repo
   - "Inside project (.worktrees/)" - local, will be gitignored
   - "Custom path" - let them specify absolute path

2. **Store the preference** in CLAUDE.md:
```bash
REPO_ROOT=$(git rev-parse --show-toplevel)
PLUGIN_ROOT=$(jq -r '.plugins."daplug@cruzanstx"[0].installPath' ~/.claude/plugins/installed_plugins.json)
CONFIG_READER="$PLUGIN_ROOT/skills/config-reader/scripts/config.py"

# Add config to CLAUDE.md under <daplug_config>
python3 "$CONFIG_READER" set worktree_dir "${CHOSEN_PATH}" --scope project
```

3. **If path is inside project** (relative path chosen), ensure gitignore:
```bash
# Add to .gitignore if not present
if [ -f "${REPO_ROOT}/.gitignore" ]; then
    if ! grep -qxF "${CONFIGURED_DIR}" "${REPO_ROOT}/.gitignore" && \
       ! grep -qxF "${CONFIGURED_DIR}/" "${REPO_ROOT}/.gitignore"; then
        echo "" >> "${REPO_ROOT}/.gitignore"
        echo "# Worktrees directory (local development)" >> "${REPO_ROOT}/.gitignore"
        echo "${CONFIGURED_DIR}/" >> "${REPO_ROOT}/.gitignore"
    fi
else
    echo "# Worktrees directory (local development)" > "${REPO_ROOT}/.gitignore"
    echo "${CONFIGURED_DIR}/" >> "${REPO_ROOT}/.gitignore"
fi

# Add to .dockerignore if not present
if [ -f "${REPO_ROOT}/.dockerignore" ]; then
    if ! grep -qxF "${CONFIGURED_DIR}" "${REPO_ROOT}/.dockerignore" && \
       ! grep -qxF "${CONFIGURED_DIR}/" "${REPO_ROOT}/.dockerignore"; then
        echo "" >> "${REPO_ROOT}/.dockerignore"
        echo "# Worktrees directory" >> "${REPO_ROOT}/.dockerignore"
        echo "${CONFIGURED_DIR}/" >> "${REPO_ROOT}/.dockerignore"
    fi
fi
```

4. **Update Claude permissions** for the resolved absolute path:
   - Add `Read(/absolute/path/**)`, `Edit(/absolute/path/**)`, `Write(/absolute/path/**)`
   - Add to `additionalDirectories`

## Core Operations

### Create a Worktree

```bash
# Get repo info
REPO_ROOT=$(git rev-parse --show-toplevel)
REPO_NAME=$(basename "$REPO_ROOT")
CURRENT_BRANCH=$(git rev-parse --abbrev-ref HEAD)
PLUGIN_ROOT=$(jq -r '.plugins."daplug@cruzanstx"[0].installPath' ~/.claude/plugins/installed_plugins.json)
CONFIG_READER="$PLUGIN_ROOT/skills/config-reader/scripts/config.py"

# Get configured worktree directory (see Configuration section)
CONFIGURED_DIR=$(python3 "$CONFIG_READER" get worktree_dir --repo-root "$REPO_ROOT")
if [ -n "$CONFIGURED_DIR" ]; then
    if [[ "$CONFIGURED_DIR" == .* ]] || [[ "$CONFIGURED_DIR" != /* ]]; then
        WORKTREES_DIR=$(realpath "${REPO_ROOT}/${CONFIGURED_DIR}")
    else
        WORKTREES_DIR="$CONFIGURED_DIR"
    fi
else
    WORKTREES_DIR=$(realpath "${REPO_ROOT}/../worktrees")
fi

# Generate unique identifier
RUN_ID="$(date +%Y%m%d-%H%M%S)"

# Create worktree with new branch
BRANCH_NAME="feature/${PURPOSE}-${RUN_ID}"
WORKTREE_PATH="${WORKTREES_DIR}/${REPO_NAME}-${PURPOSE}-${RUN_ID}"

mkdir -p "$WORKTREES_DIR"
git worktree add -b "$BRANCH_NAME" "$WORKTREE_PATH" "$CURRENT_BRANCH"

echo "Created worktree:"
echo "  Path: $WORKTREE_PATH"
echo "  Branch: $BRANCH_NAME"
echo "  Based on: $CURRENT_BRANCH"
```

### List Worktrees

```bash
git worktree list
```

### Check Worktree Status

```bash
# For each worktree, show branch and commit count
CURRENT_BRANCH=$(git rev-parse --abbrev-ref HEAD)
for worktree in $(git worktree list --porcelain | grep "^worktree" | cut -d' ' -f2); do
    branch=$(git -C "$worktree" rev-parse --abbrev-ref HEAD 2>/dev/null)
    if [ "$branch" != "$CURRENT_BRANCH" ]; then
        commits=$(git rev-list --count "$CURRENT_BRANCH".."$branch" 2>/dev/null || echo "0")
        echo "$worktree ($branch): $commits commits ahead"
    fi
done
```

### Remove a Worktree

**CRITICAL: Ensure your CWD is NOT the worktree you're deleting!**

If your shell's current working directory is the worktree being deleted, the shell will break
and all subsequent bash commands will fail with "No such file or directory".

```bash
# FIRST: Ensure you're in the main repo, not the worktree
REPO_ROOT=$(git rev-parse --show-toplevel 2>/dev/null) || REPO_ROOT="/path/to/main/repo"
cd "$REPO_ROOT"

# Verify we're not in a worktree path
if [[ "$(pwd)" == *"/worktrees/"* ]]; then
    echo "ERROR: Cannot remove worktree while inside it!"
    exit 1
fi

# Remove specific worktree by path (use subshell for safety)
(cd "$REPO_ROOT" && git worktree remove /path/to/worktree)

# Or force remove if there are changes
(cd "$REPO_ROOT" && git worktree remove --force /path/to/worktree)

# Clean up stale references
git worktree prune

# Delete the branch after worktree is removed
git branch -D branch-name
```

### Cleanup Old Worktrees

```bash
# Get configured worktree directory (see Configuration section)
REPO_ROOT=$(git rev-parse --show-toplevel)
PLUGIN_ROOT=$(jq -r '.plugins."daplug@cruzanstx"[0].installPath' ~/.claude/plugins/installed_plugins.json)
CONFIG_READER="$PLUGIN_ROOT/skills/config-reader/scripts/config.py"
CONFIGURED_DIR=$(python3 "$CONFIG_READER" get worktree_dir --repo-root "$REPO_ROOT")
if [ -n "$CONFIGURED_DIR" ]; then
    if [[ "$CONFIGURED_DIR" == .* ]] || [[ "$CONFIGURED_DIR" != /* ]]; then
        WORKTREES_DIR=$(realpath "${REPO_ROOT}/${CONFIGURED_DIR}")
    else
        WORKTREES_DIR="$CONFIGURED_DIR"
    fi
else
    WORKTREES_DIR=$(realpath "${REPO_ROOT}/../worktrees")
fi

# Find worktrees older than 7 days
find "$WORKTREES_DIR" -maxdepth 1 -type d -mtime +7 | while read dir; do
    echo "Removing old worktree: $dir"
    git worktree remove "$dir" 2>/dev/null || true
done
git worktree prune
```

### Merge Worktree Branch

```bash
WORKTREE_PATH="/path/to/worktree"
BRANCH_NAME=$(git -C "$WORKTREE_PATH" rev-parse --abbrev-ref HEAD)
CURRENT_BRANCH=$(git rev-parse --abbrev-ref HEAD)

# First, remove the worktree
git worktree remove "$WORKTREE_PATH"

# Then merge the branch
git merge --no-ff "$BRANCH_NAME" -m "Merge $BRANCH_NAME"

# Optionally delete the branch
git branch -d "$BRANCH_NAME"
```

## Permission Setup

Worktrees require file permissions for the worktrees directory. Check/add to `~/.claude/settings.json`:

```json
{
  "permissions": {
    "allow": [
      "Read(/path/to/worktrees/**)",
      "Edit(/path/to/worktrees/**)",
      "Write(/path/to/worktrees/**)"
    ],
    "additionalDirectories": [
      "/path/to/worktrees"
    ]
  }
}
```

## Best Practices

1. **Use RUN_ID timestamps** - Prevents naming collisions on reruns
2. **Track what you create** - Store paths/branches in arrays for cleanup
3. **Configure worktree location** - Set `worktree_dir` under `<daplug_config>` in CLAUDE.md for consistency
   - Sibling directory (`../worktrees/`) - default, avoids git conflicts
   - Inside project (`.worktrees/`) - self-contained, must be gitignored
4. **Prune regularly** - Run `git worktree prune` to clean stale references
5. **Check for dirty state** - Ensure no uncommitted changes before creating worktrees

## Troubleshooting

**"Branch already checked out"**
```bash
git worktree list  # Find conflicting worktree
git worktree remove /path/to/conflicting
```

**"Dirty working directory"**
```bash
git stash
# Create worktree...
git stash pop
```

**Stale worktree references**
```bash
git worktree prune
```

**Shell breaks after deleting worktree (all bash commands fail)**

This happens when your CWD was the worktree you deleted. The shell can't resolve `.` anymore.

Symptoms:
- All bash commands return exit code 1
- Error: "fatal: Unable to read current working directory: No such file or directory"
- Even simple commands like `echo test` fail

Solutions:
1. **Start a new terminal/session** - cleanest fix
2. **Use file tools instead of bash** - Read/Write/Glob still work
3. **Prevention**: Always `cd` to repo root before cleanup:
   ```bash
   cd "$REPO_ROOT"  # Do this BEFORE removing worktree
   git worktree remove /path/to/worktree
   ```

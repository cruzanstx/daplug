---
name: prompt-finder
description: Find and resolve prompt files in ./prompts/ directory. Use when user asks to find a prompt, list available prompts, locate prompt by number or name, or check what prompts exist.
allowed-tools:
  - Bash(python3:*)
  - Bash(PLUGIN_ROOT=:*)
  - Bash(PROMPT_MANAGER=:*)
  - Read
  - Glob
  - Grep
---

# Prompt File Finder

Locate and resolve prompt files using the prompt-manager skill.

## Setup

All operations use prompt-manager for consistent git root detection:

```bash
PLUGIN_ROOT=$(jq -r '.plugins."daplug@cruzanstx"[0].installPath' ~/.claude/plugins/installed_plugins.json)
PROMPT_MANAGER="$PLUGIN_ROOT/skills/prompt-manager/scripts/manager.py"
```

## When to Use This Skill

- User asks "find prompt 42" or "which prompt is about auth?"
- User wants to "list available prompts" or "show prompts"
- User asks "what's the latest prompt?" or "most recent prompt"
- Before executing a prompt, to resolve the exact file path
- User wants to search prompts by keyword

## Core Operations

### List All Prompts

```bash
# List all prompts (active and completed)
python3 "$PROMPT_MANAGER" list

# Output:
# [ ] 006 - backup-server
# [ ] 007 - deploy-k8s
# [✓] 001 - initial-setup
# [✓] 002 - add-authentication

# As JSON
python3 "$PROMPT_MANAGER" list --json

# Active only
python3 "$PROMPT_MANAGER" list --active

# Completed only
python3 "$PROMPT_MANAGER" list --completed
```

### Find Prompt by Number

```bash
# Returns path to prompt file
python3 "$PROMPT_MANAGER" find 42
# Output: /path/to/repo/prompts/042-my-prompt.md

# As JSON with full info
python3 "$PROMPT_MANAGER" find 42 --json
# {
#   "number": "042",
#   "name": "my-prompt",
#   "filename": "042-my-prompt.md",
#   "path": "/path/to/repo/prompts/042-my-prompt.md",
#   "status": "active"
# }
```

### Read Prompt Content

```bash
python3 "$PROMPT_MANAGER" read 42
# Outputs the full content of the prompt
```

### Show Prompt Preview

```bash
# Read first 30 lines
python3 "$PROMPT_MANAGER" read 42 | head -30
```

### Get Prompts Directory Info

```bash
python3 "$PROMPT_MANAGER" info
# Repository root: /path/to/repo
# Prompts directory: /path/to/repo/prompts
# Completed directory: /path/to/repo/prompts/completed
# Next number: 008
# Active prompts: 2
# Completed prompts: 5
# Total prompts: 7

# As JSON
python3 "$PROMPT_MANAGER" info --json
```

### Find Prompt by Name/Keyword

```bash
# List all and grep for keyword
python3 "$PROMPT_MANAGER" list | grep -i "auth"

# Or use JSON and jq
python3 "$PROMPT_MANAGER" list --json | jq '.[] | select(.name | contains("auth"))'
```

### Search Prompt Contents

For content search, use Grep tool on the prompts directory:

```bash
# Get prompts directory
PROMPTS_DIR=$(python3 "$PROMPT_MANAGER" info --json | jq -r '.prompts_dir')

# Search contents
grep -l -i "database" "$PROMPTS_DIR"/*.md 2>/dev/null
```

Or use the Grep tool:
```
Grep pattern="database" path="{prompts_dir}" glob="*.md"
```

### Archive/Complete a Prompt

```bash
python3 "$PROMPT_MANAGER" complete 42
# Output: Completed: /path/to/repo/prompts/completed/042-my-prompt.md
```

## Resolution Examples

```bash
# Find prompt 6 (auto-pads to 006)
PROMPT_PATH=$(python3 "$PROMPT_MANAGER" find 6)
if [ -n "$PROMPT_PATH" ]; then
    echo "Found: $PROMPT_PATH"
    # Read content
    CONTENT=$(python3 "$PROMPT_MANAGER" read 6)
fi

# Check if prompt exists
if python3 "$PROMPT_MANAGER" find 99 >/dev/null 2>&1; then
    echo "Prompt 99 exists"
else
    echo "Prompt 99 not found"
fi
```

## Error Handling

prompt-manager returns exit code 1 and writes errors to stderr:

```bash
$ python3 "$PROMPT_MANAGER" find 999
Error: Prompt 999 not found

$ python3 "$PROMPT_MANAGER" complete 6  # already completed
Error: Prompt 006 is already completed
```

## Expected Directory Structure

```
{git_root}/prompts/
├── 006-backup-server.md
├── 007-deploy-k8s.md
├── ...
└── completed/
    ├── 001-initial-setup.md
    ├── 002-add-authentication.md
    └── ...
```

## Naming Convention

Prompts follow the pattern: `NNN-descriptive-name.md`
- `NNN` = Zero-padded number (001, 042, 123)
- `descriptive-name` = Kebab-case description (max 5 words)
- `.md` = Markdown extension

## Legacy Compatibility

If prompt-manager is not available, fall back to direct file operations:

```bash
# Check if prompt-manager exists
if [ ! -f "$PROMPT_MANAGER" ]; then
    # Fallback: direct file listing
    ls -1 ./prompts/*.md 2>/dev/null
fi
```

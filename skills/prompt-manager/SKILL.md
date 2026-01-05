# prompt-manager

CRUD operations for prompt files. Centralizes all prompt management logic to avoid shell parsing issues and provide consistent behavior across commands.

## Description

Manages prompt files in `{repo_root}/prompts/` with support for:
- Listing active and completed prompts
- Getting the next available number
- Creating new prompts
- Moving prompts to completed
- Deleting prompts
- Reading prompt content

## Triggers

Use this skill when you need to:
- Find the next prompt number
- List existing prompts
- Create a new prompt file
- Move a prompt to completed
- Delete a prompt
- Read prompt content by number

## Tool Requirements

```yaml
tools:
  - Bash(python3:*)
  - Bash(PROMPT_MANAGER=:*)
```

## Commands

### Get Next Number

```bash
PROMPT_MANAGER=$(jq -r '.plugins."daplug@cruzanstx"[0].installPath' ~/.claude/plugins/installed_plugins.json)/skills/prompt-manager/scripts/manager.py
python3 "$PROMPT_MANAGER" next-number
```

Output: `006` (next available 3-digit number)

### List Prompts

```bash
# List all prompts
python3 "$PROMPT_MANAGER" list

# List as JSON
python3 "$PROMPT_MANAGER" list --json

# Active only
python3 "$PROMPT_MANAGER" list --active

# Completed only
python3 "$PROMPT_MANAGER" list --completed
```

### Find Prompt by Number

```bash
# Returns path to prompt file
python3 "$PROMPT_MANAGER" find 6
# Output: /path/to/repo/prompts/006-my-prompt.md

# As JSON
python3 "$PROMPT_MANAGER" find 6 --json
```

### Read Prompt Content

```bash
python3 "$PROMPT_MANAGER" read 6
# Outputs the full content of the prompt
```

### Create Prompt

```bash
# From content argument
python3 "$PROMPT_MANAGER" create "backup-server" --content "Prompt content here"

# From file
python3 "$PROMPT_MANAGER" create "backup-server" --content-file /tmp/prompt.md

# From stdin
cat prompt.md | python3 "$PROMPT_MANAGER" create "backup-server"

# With specific number
python3 "$PROMPT_MANAGER" create "backup-server" --number 010 --content "..."

# JSON output
python3 "$PROMPT_MANAGER" create "backup-server" --content "..." --json
```

### Complete Prompt (Move to completed/)

```bash
python3 "$PROMPT_MANAGER" complete 6
# Output: Completed: /path/to/repo/prompts/completed/006-my-prompt.md
```

### Delete Prompt

```bash
python3 "$PROMPT_MANAGER" delete 6
# Output: Deleted: 006-my-prompt.md
```

### Get Directory Info

```bash
python3 "$PROMPT_MANAGER" info

# Output:
# Repository root: /path/to/repo
# Prompts directory: /path/to/repo/prompts
# Completed directory: /path/to/repo/prompts/completed
# Next number: 006
# Active prompts: 2
# Completed prompts: 5
# Total prompts: 7

# As JSON
python3 "$PROMPT_MANAGER" info --json
```

## Integration Examples

### From /create-prompt

```bash
# Get plugin path
PLUGIN_ROOT=$(jq -r '.plugins."daplug@cruzanstx"[0].installPath' ~/.claude/plugins/installed_plugins.json)
PROMPT_MANAGER="$PLUGIN_ROOT/skills/prompt-manager/scripts/manager.py"

# Get next number
NEXT_NUM=$(python3 "$PROMPT_MANAGER" next-number)
echo "Next prompt will be: $NEXT_NUM"

# Create the prompt
python3 "$PROMPT_MANAGER" create "my-task-name" --content "$PROMPT_CONTENT" --json
```

### From /run-prompt

```bash
# Find prompt path
PROMPT_PATH=$(python3 "$PROMPT_MANAGER" find 6)
if [ -z "$PROMPT_PATH" ]; then
    echo "Prompt 6 not found"
    exit 1
fi

# Read content
CONTENT=$(python3 "$PROMPT_MANAGER" read 6)
```

## Error Handling

All errors are written to stderr with exit code 1:

```bash
$ python3 "$PROMPT_MANAGER" find 999
Error: Prompt 999 not found

$ python3 "$PROMPT_MANAGER" complete 6  # already completed
Error: Prompt 006 is already completed

$ python3 "$PROMPT_MANAGER" create "test" --number 5  # exists
Error: Prompt 005 already exists: /path/to/prompts/005-test.md
```

## JSON Output Schema

### PromptInfo

```json
{
  "number": "006",
  "name": "backup-server",
  "filename": "006-backup-server.md",
  "path": "/path/to/repo/prompts/006-backup-server.md",
  "status": "active"
}
```

### Info

```json
{
  "repo_root": "/path/to/repo",
  "prompts_dir": "/path/to/repo/prompts",
  "completed_dir": "/path/to/repo/prompts/completed",
  "next_number": "007",
  "active_count": 2,
  "completed_count": 5,
  "total_count": 7
}
```

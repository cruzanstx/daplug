---
name: gemini-cli
description: Run task with Google Gemini CLI (user)
argument-hint: <task> [--model gemini|gemini-high|gemini-xhigh|gemini25pro|gemini25flash|gemini25lite|gemini3flash|gemini3pro] [--worktree /path]
---

Run a task using Google Gemini CLI in YOLO mode (auto-approve all tool calls).

## Step 0: Check Prerequisites

Before executing, verify Gemini CLI is installed:

```bash
if ! command -v gemini &> /dev/null; then
    echo "ERROR: gemini CLI not found. Install with: npm install -g @google/gemini-cli"
    exit 1
fi
```

If not installed, inform the user:
```
Gemini CLI not found. Install it with:
  npm install -g @google/gemini-cli

Then authenticate by running: gemini (and select "Login with Google")
```

## Parse Arguments

Extract from $ARGUMENTS:
- Task text (everything that's not a flag)
- Optional `--model, -m` flag (see Model Variants below)
- Optional `--worktree <path>` flag

### Model Variants

| Shorthand | Gemini CLI Flag | Description |
|-----------|-----------------|-------------|
| `gemini` | `-m gemini-3-flash-preview` | Gemini 3 Flash (default) |
| `gemini-high` | `-m gemini-2.5-pro` | Gemini 2.5 Pro (stable, capable) |
| `gemini-xhigh` | `-m gemini-3-pro-preview` | Gemini 3 Pro (most capable) |
| `gemini25pro` | `-m gemini-2.5-pro` | Gemini 2.5 Pro (explicit) |
| `gemini25flash` | `-m gemini-2.5-flash` | Gemini 2.5 Flash (faster, lower cost) |
| `gemini25lite` | `-m gemini-2.5-flash-lite` | Gemini 2.5 Flash-Lite (fastest, lowest cost) |
| `gemini3flash` | `-m gemini-3-flash-preview` | Gemini 3 Flash Preview |
| `gemini3pro` | `-m gemini-3-pro-preview` | Gemini 3 Pro Preview |

## Execute

### Step 1: Setup log file
```bash
mkdir -p ~/.claude/cli-logs
TIMESTAMP=$(date +%Y%m%d-%H%M%S-%N)  # Nanosecond precision to avoid collisions
LOGFILE=~/.claude/cli-logs/gemini-${TIMESTAMP}.log
echo "LOGFILE: $LOGFILE"
```

### Step 2: Build model flag
```bash
# Map shorthand to Gemini CLI model flag
case "$MODEL" in
  gemini-high)   MODEL_FLAG="-m gemini-2.5-pro" ;;
  gemini-xhigh)  MODEL_FLAG="-m gemini-3-pro-preview" ;;
  gemini25pro)   MODEL_FLAG="-m gemini-2.5-pro" ;;
  gemini25flash) MODEL_FLAG="-m gemini-2.5-flash" ;;
  gemini25lite)  MODEL_FLAG="-m gemini-2.5-flash-lite" ;;
  gemini3flash)  MODEL_FLAG="-m gemini-3-flash-preview" ;;
  gemini3pro)    MODEL_FLAG="-m gemini-3-pro-preview" ;;
  *)             MODEL_FLAG="-m gemini-3-flash-preview" ;;  # gemini default
esac
```

### Step 3: Kick off background execution
**If --worktree provided:**
```bash
bash -c "cd '{WORKTREE_PATH}' && gemini -y $MODEL_FLAG -p \"\$(cat TASK.md)\" > '$LOGFILE' 2>&1" &
echo "PID: $!"
```

**Otherwise (simple task):**
```bash
bash -c "gemini -y $MODEL_FLAG -p '{TASK}' > '$LOGFILE' 2>&1" &
echo "PID: $!"
```

### Step 4: Spawn monitor agent
Immediately spawn a Task agent to monitor the log:

```
Task(
  subagent_type: "general-purpose",
  model: "haiku",
  run_in_background: true,
  description: "Monitor gemini execution",
  prompt: """
    Monitor CLI execution log: {LOGFILE}

    ## Polling Strategy (Exponential Backoff)
    1. Initial interval: 2 seconds
    2. Double after each check: 2s → 4s → 8s → 16s → 30s (max)
    3. Complete when:
       - File unchanged for 2 consecutive polls
       - Gemini CLI outputs response directly in non-interactive mode
    4. Timeout: 10 minutes

    ## Progress Updates
    Every 60 seconds while running, report:
    - Current file size / line count
    - Last meaningful output line (skip blanks, progress indicators)
    - Time elapsed

    ## On Completion

    1. Read the full response:
       ```bash
       cat "{LOGFILE}"
       ```

    2. Classify errors by category:
       ```bash
       grep -iE "(permission denied|: error:|fatal:|build failed|compilation failed|cannot find|syntax error|undefined:|go: |npm ERR!)" "{LOGFILE}" | head -20
       ```

       Error Categories:
       - PERMISSION: "permission denied", "access denied", "sandbox"
       - BUILD: "compilation failed", "syntax error", "cannot find"
       - RUNTIME: "undefined:", "null pointer", "panic:"
       - NETWORK: "timeout", "connection refused", "ECONNRESET"
       - RESOURCE: "OOM", "disk full", "quota exceeded"

    3. Extract metrics:
       - Total execution time (start → completion)
       - Line count of output
       - Error count by category

    4. Return structured summary:
       ```
       Status: SUCCESS or FAILED
       Category (if failed): BUILD, PERMISSION, RUNTIME, NETWORK, or RESOURCE
       Summary: Brief description of what was accomplished or what failed
       Duration: Xs
       Lines: N
       ```

    5. Prompt user:
       "📄 {LOGFILE} | ⏱ {duration} | {status}
        [D]elete log | [R]ead full output | [K]eep for later"
  """
)
```

## Output to main context

Only these lines go to main context:
```
⚡ Kicked off: gemini (YOLO mode)
📄 Log: ~/.claude/cli-logs/gemini-{timestamp}.log
🔍 Monitoring agent spawned...
```

The monitoring agent handles the rest in isolated context.

## Examples

```bash
# Simple task (uses Gemini 2.5 Pro by default)
/daplug:gemini-cli explain this codebase

# With specific model
/daplug:gemini-cli --model gemini25flash explain this codebase
/daplug:gemini-cli -m gemini3pro refactor the authentication module

# With worktree (reads TASK.md from worktree directory)
/daplug:gemini-cli --worktree ~/projects/my-feature

# Combined: specific model + worktree
/daplug:gemini-cli --model gemini25lite --worktree ~/projects/my-feature
```

## Quota & Usage

Models share quotas in tiers (based on observed behavior with Google One Premium):

| Tier | Models | Notes |
|------|--------|-------|
| **Pro** | gemini-2.5-pro, gemini-3-pro-preview | Shared quota |
| **Flash** | gemini-2.5-flash, gemini-2.5-flash-lite | Shared quota |
| **3 Flash** | gemini-3-flash-preview | Separate quota |

**Implications:**
- `gemini` (3 Flash) has its own bucket - won't eat into Pro or older Flash limits
- `gemini-high` and `gemini-xhigh` share the Pro quota
- `gemini25flash` and `gemini25lite` share the Flash quota

**Check usage:** Run `gemini` interactively and type `/usage` to see remaining quota per model.

## Notes

- **Default model**: Gemini 3 Flash Preview (best performance, separate quota)
- **Available models**: gemini, gemini-high, gemini-xhigh, gemini25pro, gemini25flash, gemini25lite, gemini3flash, gemini3pro
- **YOLO mode**: Auto-approves all tool calls (file writes, shell commands)
- **Non-interactive**: Uses `-p` flag for scripted execution

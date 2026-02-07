---
name: codex-cli
description: Run task with OpenAI Codex CLI (gpt-5.3-codex) (user)
argument-hint: <task> [--worktree /path] [--high|--xhigh]
---

Run a task using OpenAI Codex CLI (gpt-5.3-codex model).

## Step 0: Check Prerequisites

Before executing, verify Codex CLI is installed:

```bash
if ! command -v codex &> /dev/null; then
    echo "ERROR: codex CLI not found. Install with: npm install -g @openai/codex"
    exit 1
fi
```

If not installed, inform the user:
```
Codex CLI not found. Install it with:
  npm install -g @openai/codex

Then configure ~/.codex/config.toml with your OpenAI API key.
```

## Parse Arguments

Extract from $ARGUMENTS:
- Task text (everything that's not a flag)
- Optional `--worktree <path>` flag
- Optional reasoning effort flag:
  - `--high` → `model_reasoning_effort="high"`
  - `--xhigh` → `model_reasoning_effort="xhigh"` (extra high, only on gpt-5.3-codex)

## Execute

### Step 1: Setup log file
```bash
mkdir -p ~/.claude/cli-logs
TIMESTAMP=$(date +%Y%m%d-%H%M%S-%N)  # Nanosecond precision to avoid collisions
LOGFILE=~/.claude/cli-logs/codex-${TIMESTAMP}.log
echo "LOGFILE: $LOGFILE"
```

### Step 2: Build reasoning effort config
```bash
REASONING_CONFIG=""
if [[ "$ARGUMENTS" == *"--xhigh"* ]]; then
    REASONING_CONFIG='-c model_reasoning_effort="xhigh"'
elif [[ "$ARGUMENTS" == *"--high"* ]]; then
    REASONING_CONFIG='-c model_reasoning_effort="high"'
fi
```

### Step 3: Kick off background execution

**IMPORTANT:** Add `--add-dir` flags to allow access to Go/npm caches in sandbox mode:
- `--add-dir ~/.cache` (Go build cache)
- `--add-dir ~/go` (Go module cache)
- `--add-dir ~/.npm` (npm cache, if exists)

**If --worktree provided:**
```bash
bash -c "codex exec --full-auto $REASONING_CONFIG \
  --add-dir ~/.cache --add-dir ~/go --add-dir ~/.npm \
  -C '{WORKTREE_PATH}' \"\$(cat {WORKTREE_PATH}/TASK.md)\" > '$LOGFILE' 2>&1" &
echo "PID: $!"
```

**Otherwise (simple task):**
```bash
bash -c "codex exec --full-auto $REASONING_CONFIG \
  --add-dir ~/.cache --add-dir ~/go --add-dir ~/.npm \
  '{TASK}' > '$LOGFILE' 2>&1" &
echo "PID: $!"
```

### Step 4: Spawn monitor agent
Immediately spawn a Task agent to monitor the log:

```
Task(
  subagent_type: "general-purpose",
  model: "haiku",
  run_in_background: true,
  description: "Monitor codex execution",
  prompt: """
    Monitor CLI execution log: {LOGFILE}

    ## Polling Strategy (Exponential Backoff)
    1. Initial interval: 2 seconds
    2. Double after each check: 2s → 4s → 8s → 16s → 30s (max)
    3. Complete when:
       - "codex" output marker found at end of file
       - OR file unchanged for 2 consecutive polls
    4. Timeout: 10 minutes

    ## Progress Updates
    Every 60 seconds while running, report:
    - Current file size / line count
    - Last meaningful output line (skip blanks, progress indicators)
    - Time elapsed

    ## On Completion

    1. Extract the clean response:
       ```bash
       sed -n '/^codex$/,$ p' "{LOGFILE}" | tail -n +2
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
⚡ Kicked off: codex (gpt-5.3-codex) [reasoning: {default|high|xhigh}]
📄 Log: ~/.claude/cli-logs/codex-{timestamp}.log
🔍 Monitoring agent spawned...
```

The monitoring agent handles the rest in isolated context.

## Examples

```bash
# Default reasoning effort (medium)
/daplug:codex-cli implement a fibonacci function

# High reasoning effort
/daplug:codex-cli --high implement complex auth system

# Extra-high reasoning effort (maximum thinking)
/daplug:codex-cli --xhigh debug this race condition
```

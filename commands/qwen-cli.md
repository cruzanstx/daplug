---
name: qwen-cli
description: Run task with local qwen model via Codex CLI + LMStudio (user)
argument-hint: <task> [--worktree /path]
---

Run a task using the local qwen model (qwen/qwen3-coder-next) via Codex CLI connected to LMStudio.

## Step 0: Check Prerequisites

Before executing, verify Codex CLI is installed and LMStudio is properly configured:

```bash
# Check codex is installed
if ! command -v codex &> /dev/null; then
    echo "ERROR: codex CLI not found. Install with: npm install -g @openai/codex"
    exit 1
fi

CONFIG=~/.codex/config.toml

# Check if LMStudio provider exists
grep -q '^\[model_providers\.lmstudio-remote\]' "$CONFIG" 2>/dev/null
PROVIDER_EXISTS=$?

# Check if local profile exists
grep -q '^\[profiles\.local\]' "$CONFIG" 2>/dev/null
PROFILE_EXISTS=$?
```

**If config is missing, prompt the user to set it up:**

1. Use AskUserQuestion tool:
   - Question: "What is the IP address of your LMStudio server?"
   - Header: "LMStudio IP"
   - Options:
     - `localhost` - Running on this machine (Recommended)
     - `192.168.1.x` - Local network IP
     - Other - Let user specify

2. Use AskUserQuestion tool:
   - Question: "What model is loaded in LMStudio?"
   - Header: "Model"
   - Options:
     - `qwen/qwen3-coder-next` - Qwen 3 Coder Next (Recommended)
     - `mistralai/devstral-2-2512` - Devstral
     - Other - Let user specify

3. **After user responds, add config to `~/.codex/config.toml`:**
```bash
CONFIG=~/.codex/config.toml
LMSTUDIO_IP="{user_response}"
MODEL="{user_model_response}"

# Create config if doesn't exist
mkdir -p ~/.codex
touch "$CONFIG"

# Add LMStudio provider if missing
if ! grep -q '^\[model_providers\.lmstudio-remote\]' "$CONFIG"; then
    cat >> "$CONFIG" << EOF

# LMStudio model provider (added by daplug:qwen-cli)
[model_providers.lmstudio-remote]
name = "LMStudio ($LMSTUDIO_IP)"
base_url = "http://$LMSTUDIO_IP:1234/v1"
env_key = "LMSTUDIO_API_KEY"
wire_api = "chat"
EOF
fi

# Add local profile if missing
if ! grep -q '^\[profiles\.local\]' "$CONFIG"; then
    cat >> "$CONFIG" << EOF

# Local profile using LMStudio (added by daplug:qwen-cli)
[profiles.local]
model_provider = "lmstudio-remote"
model = "$MODEL"
EOF
fi

# Add LMSTUDIO_API_KEY to [env] if missing
if ! grep -q 'LMSTUDIO_API_KEY' "$CONFIG"; then
    # Check if [env] section exists
    if grep -q '^\[env\]' "$CONFIG"; then
        sed -i '/^\[env\]/a LMSTUDIO_API_KEY = "lm-studio"' "$CONFIG"
    else
        cat >> "$CONFIG" << EOF

[env]
LMSTUDIO_API_KEY = "lm-studio"
EOF
    fi
fi

echo "✓ LMStudio configuration added to ~/.codex/config.toml"
```

## Parse Arguments

Extract from $ARGUMENTS:
- Task text (everything that's not a flag)
- Optional `--worktree <path>` flag

## Execute

### Step 1: Setup log file
```bash
mkdir -p ~/.claude/cli-logs
TIMESTAMP=$(date +%Y%m%d-%H%M%S-%N)  # Nanosecond precision to avoid collisions
LOGFILE=~/.claude/cli-logs/qwen-${TIMESTAMP}.log
echo "LOGFILE: $LOGFILE"
```

### Step 2: Kick off background execution

**IMPORTANT:** Add `--add-dir` flags to allow access to Go/npm caches in sandbox mode:
- `--add-dir ~/.cache` (Go build cache)
- `--add-dir ~/go` (Go module cache)
- `--add-dir ~/.npm` (npm cache, if exists)

**If --worktree provided:**
```bash
bash -c "export LMSTUDIO_API_KEY='lm-studio' && \
  codex exec --full-auto --profile local \
  --add-dir ~/.cache --add-dir ~/go --add-dir ~/.npm \
  -C '{WORKTREE_PATH}' \"\$(cat {WORKTREE_PATH}/TASK.md)\" > '$LOGFILE' 2>&1" &
echo "PID: $!"
```

**Otherwise (simple task):**
```bash
bash -c "export LMSTUDIO_API_KEY='lm-studio' && \
  codex exec --full-auto --profile local \
  --add-dir ~/.cache --add-dir ~/go --add-dir ~/.npm \
  '{TASK}' > '$LOGFILE' 2>&1" &
echo "PID: $!"
```

### Step 3: Spawn monitor agent
Immediately spawn a Task agent to monitor the log:

```
Task(
  subagent_type: "general-purpose",
  model: "haiku",
  run_in_background: true,
  description: "Monitor qwen execution",
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
⚡ Kicked off: qwen (local)
📄 Log: ~/.claude/cli-logs/qwen-{timestamp}.log
🔍 Monitoring agent spawned...
```

The monitoring agent handles the rest in isolated context.

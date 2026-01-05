---
name: zai-cli
description: Run task with Z.AI GLM-4.7 via Codex CLI (user)
argument-hint: <task> [--worktree /path]
---

Run a task using Z.AI's GLM-4.7 model via Codex CLI.

Model aliases accepted: `zai`, `glm-4.7`, `glm47`, `glm`

## Step 0: Check Prerequisites

Before executing, verify Codex CLI is installed and Z.AI is properly configured:

```bash
# Check codex is installed
if ! command -v codex &> /dev/null; then
    echo "ERROR: codex CLI not found. Install with: npm install -g @openai/codex"
    exit 1
fi

CONFIG=~/.codex/config.toml

# Check if Z.AI provider exists
grep -q '^\[model_providers\.zai\]' "$CONFIG" 2>/dev/null
PROVIDER_EXISTS=$?

# Check if zai profile exists
grep -q '^\[profiles\.zai\]' "$CONFIG" 2>/dev/null
PROFILE_EXISTS=$?

# Check if ZAI_KEY is set
grep -q 'ZAI_KEY\s*=' "$CONFIG" 2>/dev/null || [ -n "$ZAI_KEY" ]
KEY_EXISTS=$?
```

**If config is missing, prompt the user to set it up:**

1. Use AskUserQuestion tool:
   - Question: "Do you have a Z.AI API key? Get one from https://z.ai/manage-apikey"
   - Header: "Z.AI Key"
   - Options:
     - `Yes, I have a key` - Enter your API key
     - `No, I need to get one` - Opens documentation

2. **If user has a key**, use AskUserQuestion:
   - Question: "Enter your Z.AI API key:"
   - Header: "API Key"
   - Options: (free text input via "Other")

3. **After user responds, add config to `~/.codex/config.toml`:**
```bash
CONFIG=~/.codex/config.toml
ZAI_KEY="{user_api_key}"

# Create config if doesn't exist
mkdir -p ~/.codex
touch "$CONFIG"

# Add Z.AI provider if missing
if ! grep -q '^\[model_providers\.zai\]' "$CONFIG"; then
    cat >> "$CONFIG" << EOF

# Z.AI model provider (added by daplug:zai-cli)
[model_providers.zai]
name = "Z.AI - GLM Coding Plan"
base_url = "https://api.z.ai/api/coding/paas/v4"
env_key = "ZAI_KEY"
wire_api = "chat"
EOF
fi

# Add zai profile if missing
if ! grep -q '^\[profiles\.zai\]' "$CONFIG"; then
    cat >> "$CONFIG" << EOF

# Z.AI profile (added by daplug:zai-cli)
[profiles.zai]
model_provider = "zai"
model = "glm-4.7"
EOF
fi

# Add ZAI_KEY to [env] if missing
if ! grep -q 'ZAI_KEY\s*=' "$CONFIG"; then
    # Check if [env] section exists
    if grep -q '^\[env\]' "$CONFIG"; then
        sed -i '/^\[env\]/a ZAI_KEY = "'"$ZAI_KEY"'"' "$CONFIG"
    else
        cat >> "$CONFIG" << EOF

[env]
ZAI_KEY = "$ZAI_KEY"
EOF
    fi
fi

echo "✓ Z.AI configuration added to ~/.codex/config.toml"
```

## Available Models

Default: `glm-4.7` (flagship model, 200K context, 128K output)

For additional models and rate limits, see:
- https://z.ai/manage-apikey/rate-limits
- https://docs.z.ai/guides/overview/quick-start

## Parse Arguments

Extract from $ARGUMENTS:
- Task text (everything that's not a flag)
- Optional `--worktree <path>` flag

## Execute

### Step 1: Setup log file
```bash
mkdir -p ~/.claude/cli-logs
TIMESTAMP=$(date +%Y%m%d-%H%M%S-%N)  # Nanosecond precision to avoid collisions
LOGFILE=~/.claude/cli-logs/zai-${TIMESTAMP}.log
echo "LOGFILE: $LOGFILE"
```

### Step 2: Kick off background execution

**IMPORTANT:** Add `--add-dir` flags to allow access to Go/npm caches in sandbox mode:
- `--add-dir ~/.cache` (Go build cache)
- `--add-dir ~/go` (Go module cache)
- `--add-dir ~/.npm` (npm cache, if exists)

**If --worktree provided:**
```bash
bash -c "codex exec --full-auto --profile zai \
  --add-dir ~/.cache --add-dir ~/go --add-dir ~/.npm \
  -C '{WORKTREE_PATH}' \"\$(cat {WORKTREE_PATH}/TASK.md)\" > '$LOGFILE' 2>&1" &
echo "PID: $!"
```

**Otherwise (simple task):**
```bash
bash -c "codex exec --full-auto --profile zai \
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
  description: "Monitor zai execution",
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
⚡ Kicked off: zai (glm-4.7)
📄 Log: ~/.claude/cli-logs/zai-{timestamp}.log
🔍 Monitoring agent spawned...
```

The monitoring agent handles the rest in isolated context.

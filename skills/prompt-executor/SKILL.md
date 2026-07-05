---
name: prompt-executor
description: Execute prompts from ./prompts/ directory with various AI models. Use when user asks to run a prompt, execute a task, delegate work to an AI model, run prompts in worktrees/tmux, or run prompts with verification loops.
allowed-tools:
  - Bash(git:*)
  - Bash(mkdir:*)
  - Bash(cp:*)
  - Bash(rm:*)
  - Bash(python3 ~/.claude/plugins/cache/daplug/daplug/*/skills/prompt-executor/scripts/executor.py:*)
  - Bash(codex:*)
  - Bash(gemini:*)
  - Bash(agy:*)
  - Bash(tmux:*)
  - Bash(cat:*)
  - Bash(pgrep:*)
  - Bash(REPO_ROOT=:*)
  - Bash(REPO_NAME=:*)
  - Bash(WORKTREE_PATH=:*)
  - Bash(WORKTREES_DIR=:*)
  - Bash(BRANCH_NAME=:*)
  - Bash(TIMESTAMP=:*)
  - Bash(\:*)
  - Read
  - Edit
  - Write
  - Task
  - Glob
  - Grep
---

# Prompt Executor

## Auto-Approval Setup

If the user has to manually confirm the executor bash command, suggest they add this rule to `~/.claude/settings.json` under `permissions.allow`:

```json
"Bash(PLUGIN_ROOT=$(jq -r '.plugins.\"daplug@cruzanstx\"[0].installPath' ~/.claude/plugins/installed_plugins.json):*)"
```

**Quick command to add it:**
```bash
# Add auto-approval rule for prompt executor
jq '.permissions.allow += ["Bash(PLUGIN_ROOT=$(jq -r '"'"'.plugins.\"daplug@cruzanstx\"[0].installPath'"'"' ~/.claude/plugins/installed_plugins.json):*)"]' ~/.claude/settings.json > /tmp/settings.json && mv /tmp/settings.json ~/.claude/settings.json
```

---

Execute prompts from `./prompts/` (including subfolders) using various AI models (Claude, Codex, Antigravity/Gemini, ZAI, etc).

## When to Use This Skill

- User says "run prompt 123" or "execute prompt 123"
- User says "run that prompt with codex/agy/gemini/zai"
- User wants to "run a prompt in a worktree"
- User wants to "run prompts in parallel"
- User asks to "delegate this to codex/agy/gemini"
- User wants to "run with verification loop" or "keep retrying until complete"
- User asks to "check loop status" for a running prompt

## Executor Script

**IMPORTANT:** Get the executor path from Claude's installed plugins manifest:

```bash
PLUGIN_ROOT=$(jq -r '.plugins."daplug@cruzanstx"[0].installPath' ~/.claude/plugins/installed_plugins.json)
EXECUTOR="$PLUGIN_ROOT/skills/prompt-executor/scripts/executor.py"
python3 "$EXECUTOR" [prompts...] [options]
```

**Options:**
<!-- BEGIN GENERATED: skill-model-options -->
- `--model, -m`: claude, cc-sonnet, cc-opus, codex, codex-spark, codex-high, codex-xhigh, gpt54, gpt54-high, gpt54-xhigh, gpt55, gpt55-high, gpt55-xhigh, gpt52, gpt52-high, gpt52-xhigh, gemini, gemini-high, gemini-xhigh, gemini25pro, gemini25flash, gemini25lite, gemini3flash, gemini3pro, gemini31pro, zai, glm5, glm52, kimi, synthetic, syn-flash, syn-kimi, syn-qwen, opencode, local, qwen, devstral, glm-local, qwen-small, qwen36, qwen36-27b
  - `glm52`: GLM-5.2 via Z.AI / OpenCode (1M context)
  - `synthetic`: GLM-5.2 via Synthetic / OpenCode (`syn:large:text`, requires `SYNTHETIC_API_KEY`)
<!-- END GENERATED: skill-model-options -->
- `--cli`: Override CLI wrapper (codex, opencode, claude, agy, or gemini; aliases: claudecode, cc, antigravity). Unsupported explicit combinations fail with a clear error (no silent fallback).
- `--variant`: Reasoning variant override (`none|low|medium|high|xhigh`). Explicit `--variant` overrides alias defaults (`codex-high`, `gpt55-high`, `gpt54-high`, `gpt52-high`, etc.).
- `--cwd, -c`: Working directory for execution
- `--run, -r`: Actually run the CLI (default: just return info)
- `--info-only, -i`: Only return prompt info, no CLI details
- `--worktree, -w`: Create isolated git worktree for execution
- `--sandbox`: Enable sandboxing (Linux default backend: bubblewrap)
- `--sandbox-type`: Sandbox backend override (`bubblewrap`)
- `--no-sandbox`: Explicitly disable sandboxing
- `--sandbox-profile`: Isolation profile (`strict|balanced|dev`, default `balanced`)
- `--sandbox-workspace`: Override sandbox workspace path (default: execution cwd)
- `--sandbox-net`: Network override (`on|off`; default comes from profile)
- `--base-branch, -b`: Base branch for worktree (default: main)
- `--on-conflict`: How to handle existing worktree (error|remove|reuse|increment)
- `--loop, -l`: Enable iterative verification loop until completion
- `--max-iterations`: Max loop iterations before giving up (default: 3)
- `--completion-marker`: Text pattern signaling completion (default: VERIFICATION_COMPLETE)
- `--require-diff`: Reject completion marker when no file changes detected (created, modified, or committed) in the execution directory. Excludes TASK.md and .sisyphus/.
- `--loop-status`: Check status of an existing verification loop

**Output:** JSON with prompt content, CLI command, log path, worktree info, and loop state if enabled

## Execution Flows

### Direct Execution (default)

```bash
# Get executor path from installed plugins manifest
PLUGIN_ROOT=$(jq -r '.plugins."daplug@cruzanstx"[0].installPath' ~/.claude/plugins/installed_plugins.json)
EXECUTOR="$PLUGIN_ROOT/skills/prompt-executor/scripts/executor.py"

# Get prompt info
python3 "$EXECUTOR" 123 --model codex

# Force OpenCode path with reasoning variant
python3 "$EXECUTOR" 123 --model codex --cli opencode --variant high

# Folder-qualified prompt (resolves prompts/providers/011-*.md)
python3 "$EXECUTOR" providers/011 --model codex

# Run in current directory
python3 "$EXECUTOR" 123 --model codex --run

# Run in bubblewrap sandbox (Linux)
python3 "$EXECUTOR" 123 --model codex --run --sandbox

# Strict profile (no network by default)
python3 "$EXECUTOR" 123 --model codex --run --sandbox --sandbox-profile strict

# Explicit opt-out
python3 "$EXECUTOR" 123 --model codex --run --no-sandbox
```

### With Worktree (built-in)

Single command creates worktree, copies TASK.md, and optionally runs:

```bash
# Create worktree and get info
python3 "$EXECUTOR" 123 --worktree --model codex

# Create worktree and run immediately
python3 "$EXECUTOR" 123 --worktree --model codex --run

# Use different base branch
python3 "$EXECUTOR" 123 --worktree --base-branch develop --model codex
```

The worktree directory is read from `worktree_dir` in `<daplug_config>` within CLAUDE.md (via config-reader), or defaults to `../worktrees/`.

### With tmux (use tmux-manager skill)

1. Get CLI command from executor:
```bash
python3 "$EXECUTOR" 123 --model codex
# Returns: {"cli_command": ["codex", "exec", "--full-auto"], "content": "...", "log": "..."}
```

2. Create tmux session using tmux-manager patterns:
```bash
SESSION_NAME="prompt-123-$(date +%Y%m%d-%H%M%S)"
tmux new-session -d -s "$SESSION_NAME" -c "$WORKTREE_PATH"
```

3. Send command to session:
```bash
tmux send-keys -t "$SESSION_NAME" "codex exec --full-auto '...' 2>&1 | tee $LOG_FILE" C-m
```

### With Verification Loop

Run prompts with automatic retries until the task is verified complete:

```bash
# Run with verification loop (background, default 3 iterations)
python3 "$EXECUTOR" 123 --model codex --run --loop

# With custom max iterations
python3 "$EXECUTOR" 123 --model codex --run --loop --max-iterations 5

# With custom completion marker
python3 "$EXECUTOR" 123 --model codex --run --loop --completion-marker "TASK_DONE"

# Worktree + loop combo
python3 "$EXECUTOR" 123 --model codex --worktree --run --loop

# Require file changes before accepting completion (--require-diff)
python3 "$EXECUTOR" 123 --model codex --run --loop --require-diff
```

**Output includes:**
```json
{
  "execution": {
    "status": "loop_running",
    "pid": 12345,
    "loop_log": "~/.claude/cli-logs/codex-123-loop-20251229-120000.log",
    "state_file": "~/.claude/loop-state/123.json",
    "max_iterations": 3,
    "completion_marker": "VERIFICATION_COMPLETE"
  }
}
```

Log paths follow `cli_logs_dir` from `<daplug_config>` if configured (default `~/.claude/cli-logs/`).

**Completion markers (required):**
- To end the loop, the model must output a final-line verification tag: `<verification>VERIFICATION_COMPLETE</verification>`.
- To request another iteration, output: `<verification>NEEDS_RETRY: [reason]</verification>`.
- The executor ignores any markers that appear inside echoed prompt instructions (some CLIs print the full prompt into logs).

**`--require-diff` (optional):**
- When enabled, the completion marker is rejected if the execution directory has no file changes (created, modified, or committed since the loop started).
- Executor-injected artifacts (`TASK.md`, `.sisyphus/`) are excluded from the diff.
- A rejected completion injects a synthetic retry reason so the model sees why it was rejected and gets another chance.
- Terminal status on the final iteration with no diff: `completed_unverified` (not `completed`).

**Dead-loop detection (always on):**
- **Stalled**: Two consecutive iterations with the same retry reason (case/whitespace-insensitive) → loop aborts with status `stalled`.
- **Blocked**: A retry reason matching impossible-gate patterns (references to paths outside the worktree, isolation-boundary refusals) → loop aborts immediately with status `blocked` and a suggested next step.

### Check Loop Status

```bash
# Check specific prompt's loop
python3 "$EXECUTOR" 123 --loop-status

# List all active loops
python3 "$EXECUTOR" --loop-status
```

## Model Reference

<!-- BEGIN GENERATED: skill-model-reference -->
| Model | CLI | Description |
|-------|-----|-------------|
| claude | (Task subagent) | Complex reasoning in current Claude Code context |
| cc-sonnet | claude --print --no-session-persistence --output-format text --input-format text --permission-mode dontAsk --model sonnet | Claude Code CLI Sonnet runs |
| cc-opus | claude --print --no-session-persistence --output-format text --input-format text --permission-mode dontAsk --model opus | Claude Code CLI Opus runs |
| codex | codex exec --full-auto | Fast coding execution (default Codex shorthand) |
| codex-spark | codex exec --full-auto -m gpt-5.3-codex-spark | Lowest-latency quick edits |
| codex-high | codex exec --full-auto -c model_reasoning_effort="high" | Complex coding |
| codex-xhigh | codex exec --full-auto -c model_reasoning_effort="xhigh" | Large refactors |
| gpt54 | codex exec --full-auto -m gpt-5.4 | Explicit GPT-5.4 shorthand |
| gpt54-high | codex exec --full-auto -m gpt-5.4 -c model_reasoning_effort="high" | Deep reasoning with GPT-5.4 |
| gpt54-xhigh | codex exec --full-auto -m gpt-5.4 -c model_reasoning_effort="xhigh" | Maximum reasoning with GPT-5.4 |
| gpt55 | codex exec --full-auto | Explicit GPT-5.5 shorthand |
| gpt55-high | codex exec --full-auto -c model_reasoning_effort="high" | Deep reasoning with GPT-5.5 |
| gpt55-xhigh | codex exec --full-auto -c model_reasoning_effort="xhigh" | Maximum reasoning with GPT-5.5 |
| gpt52 | codex exec --full-auto -m gpt-5.2 | Planning, research, analysis |
| gpt52-high | codex exec --full-auto -m gpt-5.2 -c model_reasoning_effort="high" | Deep reasoning |
| gpt52-xhigh | codex exec --full-auto -m gpt-5.2 -c model_reasoning_effort="xhigh" | Maximum reasoning (30+ min) |
| gemini | gemini -y -m gemini-3-flash-preview | Fast daily driver (default) |
| gemini-high | gemini -y -m gemini-2.5-pro | Stable, more capable |
| gemini-xhigh | gemini -y -m gemini-3-pro-preview | Most capable Gemini fallback |
| gemini25pro | gemini -y -m gemini-2.5-pro | Explicit stable Pro selection |
| gemini25flash | gemini -y -m gemini-2.5-flash | Fast, cost-effective |
| gemini25lite | gemini -y -m gemini-2.5-flash-lite | Fastest Gemini option |
| gemini3flash | gemini -y -m gemini-3-flash-preview | Explicit 3 Flash selection |
| gemini3pro | gemini -y -m gemini-3-pro-preview | Explicit 3 Pro selection |
| gemini31pro | gemini -y -m gemini-3.1-pro-preview | Latest Pro model (if available) |
| zai | codex exec --full-auto --profile zai | General coding fallback |
| glm5 | opencode run --format json -m zai/glm-5.2 | Latest GLM 5.x tasks via OpenCode |
| glm52 | opencode run --format json -m zai/glm-5.2 | Explicit GLM-5.2 pin via OpenCode |
| kimi | opencode run --format json -m opencode/kimi-k2.5 | Kimi K2.5 via OpenCode |
| synthetic | opencode run --format json -m synthetic/syn:large:text | GLM-5.2 default, 512k context |
| syn-flash | opencode run --format json -m synthetic/syn:small:text | Fast GLM-4.7-Flash fallback |
| syn-kimi | opencode run --format json -m synthetic/syn:large:vision | Kimi-K2.6 vision tasks |
| syn-qwen | opencode run --format json -m synthetic/syn:small:vision | Qwen3.6-27B vision tasks |
| opencode | opencode run --format json -m zai/glm-4.7 | Recommended OpenCode JSON runner |
| local | opencode run --format json -m lmstudio/qwen3.6-35b-a3b --pure --agent build | Local qwen-coder model with no quota |
| qwen | opencode run --format json -m lmstudio/qwen3.6-35b-a3b --pure --agent build | Local qwen-coder model with no quota |
| devstral | opencode run --format json -m lmstudio/devstral-small-2-2512 --pure --agent build | Local Devstral model with no quota |
| glm-local | opencode run --format json -m lmstudio/glm-4.7-flash --pure --agent build | Local GLM-4.7 Flash model with no quota |
| qwen-small | opencode run --format json -m lmstudio/qwen3-4b-2507 --pure --agent build | Small/fast local Qwen model |
| qwen36 | opencode run --format json -m lmstudio/qwen3.6-35b-a3b --pure --agent build | Best local coding model, MoE 35B, no quota |
| qwen36-27b | opencode run --format json -m lmstudio/qwen3.6-27b --pure --agent build | Local Qwen 3.6 dense 27B, no quota |
<!-- END GENERATED: skill-model-reference -->

OpenCode runs include `--variant <value>` when a variant is set.

GLM-5.2 uses the Z.AI Coding Plan endpoint (`https://api.z.ai/api/coding/paas/v4`) with raw model ID `glm-5.2`. OpenCode receives `zai/glm-5.2`; Claude Code env examples use `glm-5.2[1m]` with `ANTHROPIC_DEFAULT_SONNET_MODEL`, `ANTHROPIC_DEFAULT_OPUS_MODEL`, and `CLAUDE_CODE_AUTO_COMPACT_WINDOW=1000000`. daplug passes only the model ID; the 1M context window is provided by the Coding Plan endpoint.

Synthetic shorthands use OpenCode provider refs such as `synthetic/syn:large:text`; set `SYNTHETIC_API_KEY` and configure OpenCode's `synthetic` provider with `https://api.synthetic.new/openai/v1`. Raw `hf:` IDs are intentionally not daplug shorthands; add them to OpenCode as `synthetic/hf:owner/model` pass-through refs when needed.

**OpenCode permissions (headless runs):** configure `~/.config/opencode/opencode.json` to avoid interactive permission prompts, e.g.:

```json
{
  "permission": {
    "*": "allow",
    "external_directory": "allow",
    "doom_loop": "allow"
  }
}
```

## Output Display

After executing the prompt, display a clear summary that includes the prompt **title** from the JSON output:

```markdown
## Execution Started

**Prompt 295**: Add transcript success monitoring with retry logic

| Field | Value |
|-------|-------|
| Model | codex (gpt-5.5) |
| Status | 🟢 Running (PID 12345) |
| Loop | Max 3 iterations |

Worktree: `.worktrees/repo-prompt-295-20251229-181852/`
Branch: `prompt/295-transcript-success-monitoring`
```

**Important**: Always include the `title` field from the executor JSON output. This tells the user what the prompt actually does, not just its number.

## Monitoring Pattern

After launching, spawn a haiku monitor subagent:

```
Task(
  subagent_type: "general-purpose",
  model: "haiku",
  run_in_background: true,
  prompt: """
    Monitor prompt execution:
    - Log file: {log_path}
    - PID: {pid}
    - {If tmux: Session: {session}}
    - {If worktree: Worktree: {worktree_path}}

    IMPORTANT: Use Bash tool for all file operations (not Read tool):

    Every 30 seconds, check status using Bash:
    ```bash
    # Check if process is running
    ps -p {pid} > /dev/null 2>&1 && echo "RUNNING" || echo "STOPPED"

    # Tail last 20 lines of log
    tail -20 "{log_path}"
    ```

    On completion (process ended):
    ```bash
    # Get summary from log
    tail -50 "{log_path}"

    # If worktree, show git status
    cd "{worktree_path}" && git log --oneline -5 && git diff --stat
    ```
    - Summarize what was done
    - Report final status
  """
)
```

## Cleanup

For worktree executions, after completion:

```bash
# Remove TASK.md before merge
rm "$WORKTREE_PATH/TASK.md"

# Merge if requested
git checkout main
git merge --no-ff "$BRANCH_NAME" -m "Merge prompt: $BRANCH_NAME"

# Cleanup
git worktree remove "$WORKTREE_PATH"
git branch -D "$BRANCH_NAME"
git worktree prune
```

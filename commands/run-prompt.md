---
name: run-prompt
description: Execute prompts from ./prompts/ with various AI models, optional worktree isolation, tmux sessions, and iterative verification loops
argument-hint: <prompt(s)> [--model <model>] [--moa <m1,m2,...>] [--cli codex|opencode|claude|agy|gemini] [--variant none|low|medium|high|xhigh] [--worktree] [--sandbox|--no-sandbox] [--sandbox-type bubblewrap] [--sandbox-profile strict|balanced|dev] [--sandbox-workspace <path>] [--sandbox-net on|off] [--tmux] [--parallel] [--loop]
---

# Run Prompt

Execute prompts from `./prompts/` (including subfolders) using various AI models. Google/Gemini shorthands prefer Antigravity CLI (`agy`) when healthy and fall back to legacy `gemini`.

## Arguments

| Argument | Description |
|----------|-------------|
| `<prompt>` | Prompt number(s), range(s), or name(s) - defaults to latest |
<!-- BEGIN GENERATED: run-prompt-model-argument -->
| `--model, -m` | claude, cc-sonnet, cc-opus, codex, codex-spark, codex-high, codex-xhigh, sol, terra, luna, gpt54, gpt54-high, gpt54-xhigh, gpt55, gpt55-high, gpt55-xhigh, gpt52, gpt52-high, gpt52-xhigh, gemini, gemini-high, gemini-xhigh, gemini25pro, gemini25flash, gemini25lite, gemini3flash, gemini3pro, gemini31pro, zai, glm5, glm52, kimi, synthetic, syn-flash, syn-kimi, syn-qwen, opencode, local, qwen, devstral, glm-local, qwen-small, qwen36, qwen36-27b (codex/codex-high/codex-xhigh default to GPT-5.5; `gpt55*` are explicit GPT-5.5 shorthands) |
<!-- END GENERATED: run-prompt-model-argument -->
| `--moa` | Mixture-of-agents: comma-separated list of 2+ models (e.g. `codex,synthetic,qwen36`). Each model runs the prompt in its own worktree; you (Claude) judge and consolidate the results afterwards. Entries may carry a per-model CLI override as `model:cli` (e.g. `codex:opencode`). Mutually exclusive with `--model` and the global `--cli`; implies `--worktree`. The bare `claude` Task-subagent shorthand is not allowed (use `cc-sonnet`, `cc-opus`, or `claude:claude`). |
| `--cli` | Override CLI wrapper: codex, opencode, claude, agy, or gemini (aliases: claudecode, cc, antigravity). Unsupported explicit combinations error clearly. Not allowed with `--moa`. |
| `--variant` | Reasoning variant override: `none`, `low`, `medium`, `high`, `xhigh`. Explicit `--variant` overrides alias defaults. |
| `--worktree, -w` | Run in isolated git worktree |
| `--sandbox` | Enable sandboxing (Linux default backend: bubblewrap) |
| `--sandbox-type <type>` | Sandbox backend override (`bubblewrap`) |
| `--no-sandbox` | Explicitly disable sandboxing |
| `--sandbox-profile <preset>` | Isolation preset: `strict`, `balanced`, `dev` (default: `balanced`) |
| `--sandbox-workspace <path>` | Override sandbox workspace path (default: repo/worktree cwd) |
| `--sandbox-net <mode>` | Network override: `on` or `off` (default from profile) |
| `--tmux, -t` | Run in tmux session (can monitor/attach later) |
| `--parallel, -p` | Run multiple prompts in parallel |
| `--loop, -l` | Enable iterative verification loop until completion |
| `--max-iterations <n>` | Max loop iterations before giving up (default: 3) |
| `--completion-marker <text>` | Text pattern signaling completion (default: VERIFICATION_COMPLETE) |
| `--require-diff` | Reject the completion marker when no file changes (created, modified, or committed) are detected in the execution directory. Excludes executor-injected artifacts (TASK.md, .sisyphus/). |

### Prompt Selection Syntax

- Single: `123`, `providers/011`, or `fix-bug`
- Range: `002-005` (expands to 002, 003, 004, 005)
- Folder range: `providers/011-015` (expands to providers/011, 012, 013, 014, 015)
- Comma list: `002,005,providers/011`
- Combined: `002-004,010,providers/011-013`

Notes:
- Folder prefixes are relative to `./prompts/` (e.g. `providers/011` resolves `./prompts/providers/011-*.md`).
- If a number/name is ambiguous across folders, specify the folder prefix.

## Execution Flow

### Step 0: Resolve Executor Path

**IMPORTANT:** Get the executor path from Claude's installed plugins manifest:

```bash
PLUGIN_ROOT=$(jq -r '.plugins."daplug@cruzanstx"[0].installPath' ~/.claude/plugins/installed_plugins.json)
EXECUTOR="$PLUGIN_ROOT/skills/prompt-executor/scripts/executor.py"
```

### Step 0.25: Check Agent Cache (Recommended)

If this is your first time running daplug in this environment, scan for installed CLIs first:

- If `~/.claude/daplug-clis.json` does **not** exist yet, recommend running `/daplug:detect-clis` before continuing.
- If it exists, continue normally.

### Step 0.3: Model Routing Behavior

When the `/detect-clis` cache is present, `executor.py` routes `--model` shorthands to an installed CLI automatically:

- Respects `preferred_agent` in `<daplug_config>` when multiple CLIs can run a model family.
- Falls back gracefully when the preferred CLI isn’t installed/ready (example: `gemini-*` → `opencode`).
- Explicit `--cli` override intent is strict: if that CLI cannot run the selected model, executor returns an actionable error instead of silently rerouting.
- Local routing (`local`, `qwen`, `devstral`) uses the detected running provider (LM Studio / Ollama / vLLM).
- Synthetic routing (`synthetic`, `syn-flash`, `syn-kimi`, `syn-qwen`) uses OpenCode's `synthetic` provider and requires `SYNTHETIC_API_KEY`.
- `devstral` is treated as a multimodal local model (`vision` capability metadata in router).
- If the cache is missing, daplug falls back to the legacy hardcoded model map for backward compatibility.

### Step 0.5: Verify Monitor Permissions

Before spawning monitor agents, verify the required Read permissions exist in `~/.claude/settings.json`:

```bash
# Check if permissions exist
jq -e '.permissions.allow | map(select(. == "Read(~/.claude/cli-logs/**)" or . == "Read(~/.claude/loop-state/**)")) | length == 2' ~/.claude/settings.json
```

**If permissions are missing**, add them:

```bash
# Add the required permissions
jq '.permissions.allow = ["Read(~/.claude/cli-logs/**)", "Read(~/.claude/loop-state/**)"] + .permissions.allow' ~/.claude/settings.json > /tmp/settings.json && mv /tmp/settings.json ~/.claude/settings.json
```

Then inform the user:
> Added monitor permissions to ~/.claude/settings.json. Restart Claude Code for changes to take effect.

**Required permissions for monitor agents:**
- `Read(~/.claude/cli-logs/**)` - Read execution logs
- `Read(~/.claude/loop-state/**)` - Read loop state JSON files

### Step 1: Execute with Executor

**For non-Claude models (codex, gemini, zai, etc):**

Use a single executor command that handles everything:

```bash
python3 "$EXECUTOR" {PROMPT} --model {MODEL} {--worktree if requested} --run
```

This single command:
- Resolves the prompt
- Creates worktree if `--worktree` is passed
- Launches the CLI in the background
- Returns JSON with all info (paths, PIDs, logs)

Parse the JSON output to get:
- `prompts[].folder` - prompt subfolder under `prompts/` (empty string for root)
- `prompts[].path` - repo-relative prompt path (e.g. `prompts/providers/011-*.md`)
- `prompts[].worktree.worktree_path` - worktree path (if created)
- `prompts[].worktree.branch_name` - branch name (if created)
- `prompts[].execution.pid` - background process PID
- `prompts[].execution.log` - log file path
- `prompts[].log` - log file path

**If worktree conflict detected** (`prompts[].worktree.conflict == true`):

The executor returns conflict info instead of creating a worktree. Use AskUserQuestion:

```
AskUserQuestion(
  questions: [{
    question: "A worktree already exists for this prompt at '{existing_worktree}'. How would you like to proceed?",
    header: "Conflict",
    options: [
      { label: "Remove & recreate", description: "Delete existing worktree/branch and start fresh" },
      { label: "Reuse existing", description: "Continue using the existing worktree" },
      { label: "Create new branch", description: "Create with incremented suffix (-1, -2, etc.)" }
    ],
    multiSelect: false
  }]
)
```

Based on user choice, re-run executor with `--on-conflict`:
- "Remove & recreate" → `--on-conflict remove`
- "Reuse existing" → `--on-conflict reuse`
- "Create new branch" → `--on-conflict increment`

**If executor returns an error** (check for `error` key in JSON):

Common errors and how to handle them:

| Error Message | Cause | Action |
|--------------|-------|--------|
| `No prompts directory: {path}` | No `prompts/` folder at git root | Report error, suggest: `mkdir -p $(git rev-parse --show-toplevel)/prompts` |
| `No prompt found for '{input}'` | Prompt number/name doesn't exist | Report error, suggest running `/prompts` to list available prompts |
| `No prompt files found` | `prompts/` exists but is empty | Report error, suggest using `/create-prompt` to create one |
| `Ambiguous prompt '{input}'` | Multiple prompts match the input | Report matches and ask user to specify a folder prefix (e.g. `providers/011`) or a more specific name |

**CRITICAL: Do NOT attempt manual CLI execution when the executor fails.** Always report the error to the user and suggest fixes.

Example error handling:
```
If executor output contains {"error": "..."}:
  1. Report the error clearly to the user
  2. Explain what went wrong
  3. Suggest a fix (see table above)
  4. STOP - do not try to work around the error
```

**For Claude model:**

First get info (no --run), then spawn a Task subagent:

```bash
python3 "$EXECUTOR" {PROMPT} --model claude {--worktree if requested}
```

Then spawn:
```
Task(
  subagent_type: "general-purpose",
  description: "Execute prompt {NUMBER}",
  run_in_background: true,
  prompt: """
    {If worktree: You are working in: {WORK_DIR}}

    Execute this task completely:

    {PROMPT_CONTENT}

    After implementation:
    1. Make atomic commits with clear messages
    2. Verify your changes work
    3. Return a summary of what you implemented
    {If worktree: Do NOT commit TASK.md}
  """
)
```

**For Claude Code one-shot CLI execution (headless):**

Use `--cli claude` with the `claude` model, or use the `cc-*` shorthands:

```bash
python3 "$EXECUTOR" {PROMPT} --model claude --cli claude --run
python3 "$EXECUTOR" {PROMPT} --model cc-sonnet --run
python3 "$EXECUTOR" {PROMPT} --model cc-opus --run
```

**If --tmux flag (for any model):**

Get info first, then create tmux session:
```bash
python3 "$EXECUTOR" {PROMPT} --model {MODEL} {--worktree if requested}
```

Then:
```bash
SESSION_NAME="prompt-{NUMBER}-$(date +%Y%m%d-%H%M%S)"
tmux new-session -d -s "$SESSION_NAME" -c "{WORK_DIR}"
tmux send-keys -t "$SESSION_NAME" "{CLI_COMMAND} '$(cat {TASK_FILE})' 2>&1 | tee {LOG_FILE}" C-m
```

### Step 2: Report to User AND Spawn Monitors

**THIS STEP HAS TWO MANDATORY PARTS - DO BOTH:**

#### Part A: Report Status

Use the output format defined in `<output_format>` below. Key elements:
1. **Execution table** - All prompts with paths and logs
2. **Status table** - Running status with emoji indicators
3. **Quick commands** - Copy-paste ready for monitoring

#### Part B: Spawn Monitor Agents (MANDATORY for non-Claude models)

**IMMEDIATELY after showing the status table, spawn a monitor for EACH prompt:**

```
Task(
  subagent_type: "daplug:readonly-log-watcher",
  run_in_background: true,
  prompt: """
    Monitor prompt {NUMBER} execution:
    - Log file: {LOG_FILE}
    - State file: ~/.claude/loop-state/{NUMBER}.json (if --loop)
    - {If worktree: Worktree: {WORK_DIR}}

    Read files every 30 seconds. Report:
    - Progress updates (don't spam - every 2-3 checks)
    - Completion (success or failure)
    - Error summary if failed

    Timeout after 60 minutes.
  """
)
```

**For multiple prompts, spawn ALL monitors in a SINGLE message with multiple Task calls.**

Example for 3 prompts:
```
[Message with 3 Task tool calls - one for each prompt's monitor]
```

**DO NOT skip this step. The monitors are how the user gets notified of completion.**

## Iterative Verification Loop

The `--loop` flag enables automatic re-running until the task is genuinely complete. This is inspired by the ralph-wiggum plugin's "self-referential feedback loop" pattern.

### How It Works

1. **Prompt Wrapping**: The original prompt is wrapped with a verification protocol
2. **Execution**: CLI runs with the wrapped prompt
3. **Completion Check**: Log is scanned for completion markers
4. **Diff Verification** (when `--require-diff`): The execution directory is checked for actual file changes before accepting the completion marker
5. **Dead-Loop Detection** (always on): Identical consecutive retry reasons trigger "stalled"; impossible-gate refusals trigger "blocked"
6. **Iteration**: If not complete, the process repeats with updated context
7. **Termination**: Loop ends when marker found (and verified), stalled, blocked, OR max iterations reached

### Terminal Statuses

| Status | Meaning |
|--------|---------|
| `completed` | Completion marker found and accepted |
| `completed_unverified` | Completion marker found but `--require-diff` detected no file changes on the final iteration |
| `max_iterations_reached` | Ran out of iterations without finding the completion marker |
| `stalled` | Two consecutive iterations had the same retry reason (no progress possible) |
| `blocked` | Retry reason indicates an impossible gate (e.g., file outside worktree); retrying will never help |
| `failed` | Execution error or invalid working directory |

### Completion Protocol

Prompts executed with `--loop` automatically receive these instructions:

```xml
<verification_protocol>
**To signal completion:** Output `<verification>VERIFICATION_COMPLETE</verification>` ONLY when:
- All implementation is done
- Tests pass (if applicable)
- Build succeeds (if applicable)

**To signal retry needed:** Output `<verification>NEEDS_RETRY: [reason]</verification>` if:
- Tests are failing
- Build errors exist
- Implementation incomplete
</verification_protocol>
```

### Loop State Management

State is tracked in `~/.claude/loop-state/{prompt-number}.json`:

```json
{
  "prompt_number": "123",
  "model": "codex",
  "iteration": 3,
  "max_iterations": 3,
  "status": "running",
  "last_updated_at": "2025-12-29T18:30:00",
  "history": [
    {"iteration": 1, "exit_code": 0, "marker_found": false, "retry_reason": "Tests failing"},
    {"iteration": 2, "exit_code": 1, "marker_found": false, "retry_reason": "Lint errors remain"}
  ],
  "suggested_next_steps": [
    {"text": "Deploy to staging", "original": "1) Deploy to staging", "source_iteration": 1}
  ]
}
```

### Check Loop Status

```bash
# Check specific prompt's loop
python3 "$EXECUTOR" 123 --loop-status

# List all active loops
python3 "$EXECUTOR" --loop-status
```

### For Loop Mode Execution

**With --loop flag:**

```bash
python3 "$EXECUTOR" {PROMPT} --model {MODEL} {--worktree if requested} --run --loop --max-iterations {N}
```

Parse the JSON output for:
- `prompts[].execution.status` - "loop_running" for background; "completed", "completed_unverified", "max_iterations_reached", "stalled", or "blocked" for foreground
- `prompts[].execution.loop_log` - Log file for the loop process
- `prompts[].execution.state_file` - Path to loop state JSON
- `prompts[].execution.iterations` - Array of iteration results (foreground mode)
- `prompts[].execution.suggested_next_steps` - Suggested follow-ups extracted from logs (foreground mode)
- `prompts[].execution.failure_reason` - Present when status is "stalled" or "blocked"

### Monitor Agent for Loop Mode (variation of Step 2 Part B)

**When `--loop` is used, the monitor prompt in Step 2 Part B should include state file info:**

```
Task(
  subagent_type: "daplug:readonly-log-watcher",
  run_in_background: true,
  prompt: """
    Monitor prompt {NUMBER} VERIFICATION LOOP:
    - State file: ~/.claude/loop-state/{NUMBER}.json
    - Loop log: {LOOP_LOG}
    - Max iterations: {MAX_ITERATIONS}

    Every 15 seconds:
    1. Read state file (JSON) - check iteration, status, history
    2. Read loop log for recent output

    Report:
    - ⚠️ When new retry_reason appears in history
    - ✅ When status == "completed"
    - ❌ When status == "max_iterations_reached"

    Timeout after 60 minutes.
  """
)
```

**Remember: This is still part of Step 2 Part B - spawn monitors IMMEDIATELY after showing status.**

## Mixture of Agents (--moa)

`--moa model1,model2[,model3...]` runs the same prompt with multiple models in parallel, each in its own isolated worktree. When all runs finish, **you (the Claude Code session) act as the judge**: compare the diffs, run the tests in each worktree, and consolidate the best result onto one branch.

### Launch

```bash
python3 "$EXECUTOR" {PROMPT} --moa codex,synthetic,qwen36 --run [--loop] [--sandbox ...]
```

Rules enforced by the executor:
- Mutually exclusive with `--model` and the global `--cli`. Per-model CLI overrides use inline `model:cli` syntax instead: `--moa codex:opencode,qwen36` (aliases `cc`/`claudecode`/`antigravity` accepted; unsupported model+CLI combos error up front).
- The same model on different CLIs counts as two distinct runs: `--moa codex,codex:opencode` compares the Codex CLI against OpenCode. Each run's unique key ("label") is `model` or `model-cli`.
- Implies `--worktree` — one worktree + branch per run (`prompt/{slug}-moa-{label}`).
- `--variant` is applied per model where supported and silently dropped otherwise (`variant_dropped: true` in the run entry).
- `--loop` applies per runner; loop state is keyed per run: `~/.claude/loop-state/{N}-moa-{label}.json`.

**CLI override caveat:** `codex:opencode` routes GPT-5.5 through OpenCode's `openai` provider, which typically authenticates with an OpenAI API key rather than the ChatGPT/Codex subscription — quota/billing may differ from a plain `codex` run.

**Cost note:** MoA multiplies quota usage by the number of models. If `ai_usage_awareness` is enabled, consider a quick `/daplug:ai-usage` check before launching a 3+ model fan-out.

### JSON Output

Top-level: `model: "moa"`, `moa_models: [...]`. Per prompt, `prompts[].moa`:
- `manifest_file` - persisted manifest at `~/.claude/loop-state/moa/{N}-{timestamp}.json` (the judge phase reads this)
- `runs[]` - one entry per run: `model`, `cli` (per-entry override or null), `label`, `status`, `worktree_path`, `branch_name`, `log`, `state_file` (loop mode), `execution`, `variant`, `variant_dropped`
- Per-run `status`: `running` / `loop_running` (launched), `conflict` (worktree exists — handle like the single-model conflict flow, per run), `error` (that run failed; others continue), `info` (no `--run`)

### Monitoring

Spawn ONE monitor per model run (same pattern as Step 2 Part B), pointing at each run's `log` (and `state_file` when `--loop`). When every monitor reports a terminal state, proceed to the judge phase.

### Judge & Consolidation Phase (you do this)

When all runs complete:

1. **Collect**: Read the manifest, then for each worktree: `git -C {worktree_path} diff {base_branch} --stat` and the full diff.
2. **Verify**: Run the project's tests/build in each worktree. Record pass/fail.
3. **Score**: Compare on correctness (tests pass), completeness vs the prompt, code quality/fit with the codebase, and scope discipline (no unrelated changes).
4. **Report**: Show the user a scorecard table (model, tests, diff size, notable strengths/weaknesses) and your recommendation.
5. **Consolidate** (after user picks, or immediately if the user pre-authorized): merge the winning branch; optionally cherry-pick superior pieces from the other worktrees onto it. Delete `TASK.md` before merging.
6. **Attribute**: Credit contributing agents in the merge commit footer per the user's commit conventions (e.g. `Co-Authored-By: Codex <noreply@openai.com>`).
7. **Cleanup**: After merge, remove the losing worktrees/branches (ask first if the user may want to inspect them).

## Examples

```
/daplug:run-prompt 123                           # Single prompt with Claude
/daplug:run-prompt 123 --model codex             # With Codex
/daplug:run-prompt 123 --model codex-high        # Codex alias (default high reasoning variant)
/daplug:run-prompt 123 --model codex-spark       # Codex Spark (lower-latency tier)
/daplug:run-prompt 123 --model codex-high --variant none  # Override alias default reasoning
/daplug:run-prompt 123 --model codex --cli opencode --variant high  # Force OpenCode + variant
/daplug:run-prompt 123 --model glm5              # Z.AI GLM-5.2
/daplug:run-prompt 123 --model glm52             # Z.AI GLM-5.2 explicit pin
/daplug:run-prompt 123 --model synthetic         # Synthetic GLM-5.2 (`syn:large:text`)
/daplug:run-prompt 123 --model syn-kimi          # Synthetic Kimi-K2.6 vision alias
/daplug:run-prompt 123 --model codex --worktree  # Codex in isolated worktree
/daplug:run-prompt 123 --model codex --sandbox   # Codex in bubblewrap sandbox (Linux)
/daplug:run-prompt 123 --model codex --sandbox --sandbox-profile strict  # strict isolation
/daplug:run-prompt 123 --model codex --no-sandbox  # explicit opt-out
/daplug:run-prompt 123 --tmux                    # In tmux session
/daplug:run-prompt 123 --worktree --tmux         # Worktree + tmux (full isolation)
/daplug:run-prompt 002-005 --parallel --worktree # Range: 002, 003, 004, 005
/daplug:run-prompt 002,005,010 --parallel        # Comma list: specific prompts
/daplug:run-prompt 002-004,010 --model codex     # Combined range + single
/daplug:run-prompt 123 --model codex --loop      # With verification loop
/daplug:run-prompt 123 --model codex --loop --max-iterations 5  # Custom max
/daplug:run-prompt 123 --model codex --worktree --loop  # Worktree + loop
/daplug:run-prompt 123 --model codex --loop --require-diff  # Verify file changes before accepting completion
/daplug:run-prompt 123 --moa codex,synthetic,qwen36  # Mixture-of-agents: 3 models, 3 worktrees, you judge
/daplug:run-prompt 123 --moa codex,glm5 --loop       # MoA with per-runner verification loops
/daplug:run-prompt 123 --moa codex:opencode,qwen36   # MoA with per-entry CLI override
/daplug:run-prompt 123 --moa codex,codex:opencode    # Same model, two CLIs — compare harnesses
```

## Cleanup (after completion)

For worktree executions, when user says "cleanup" or "merge":

```bash
# Get values from the executor output
WORK_DIR="{prompts[].worktree.worktree_path}"
BRANCH_NAME="{prompts[].worktree.branch_name}"

# Ensure not in worktree directory
cd "$(git rev-parse --show-toplevel)"

# Remove TASK.md
rm "$WORK_DIR/TASK.md"

# If merge requested:
git checkout main
git merge --no-ff "$BRANCH_NAME" -m "Merge prompt: {NUMBER}"

# Cleanup worktree
git worktree remove "$WORK_DIR"
git branch -D "$BRANCH_NAME"
git worktree prune
```

For tmux sessions:
```bash
tmux kill-session -t "$SESSION_NAME"
```

<output_format>
**Key principle: Tables for info, quick commands for actions.**

### Execution Summary Table

After launching, show a table with all execution details:

```markdown
| Prompt | Model       | Worktree                                                 | Branch                                            | Log                                                    |
|--------|-------------|----------------------------------------------------------|---------------------------------------------------|--------------------------------------------------------|
| 289    | codex-xhigh | .worktrees/youtube_summaries-prompt-289-20251228-144050/ | prompt/289-analyze-auto-category-creation         | ~/.claude/cli-logs/codex-xhigh-289-20251228-144050.log |
| 303    | codex-xhigh | .worktrees/youtube_summaries-prompt-303-20251228-144052/ | prompt/303-investigate-shorts-generation-workflow | ~/.claude/cli-logs/codex-xhigh-303-20251228-144052.log |
```

**Table columns:**
1. `Prompt` - Prompt number
2. `Model` - CLI model used
3. `Worktree` - Path to worktree (if `--worktree`)
4. `Branch` - Git branch name (if `--worktree`)
5. `Log` - Log file path for monitoring

### Status Table

Show running status with emoji indicators:

```markdown
| Prompt                              | Status                  | Monitor                     |
|-------------------------------------|-------------------------|-----------------------------|
| 289 - Auto Category Analysis        | 🟢 Running (PID 278459) | Background agent monitoring |
| 303 - Shorts Workflow Investigation | 🟢 Running (PID 278839) | Background agent monitoring |
```

**Status indicators:**
- 🟢 Running - Process active
- ✅ Complete - Finished successfully
- ❌ Failed - Errors detected
- ⏸️ Paused - Tmux session detached

### Quick Commands Section

Always include copy-paste ready commands:

```markdown
Quick check commands:
# Tail logs
tail -f ~/.claude/cli-logs/codex-xhigh-289-20251228-144050.log
tail -f ~/.claude/cli-logs/codex-xhigh-303-20251228-144052.log

# Check worktrees
git worktree list
```

**Command categories to include:**
- `tail -f {LOG}` - Monitor live output
- `git worktree list` - See active worktrees
- `tmux attach -t {SESSION}` - Attach to tmux (if `--tmux`)
- `ps -p {PID}` - Check if still running

### Completion Report

When monitor agent reports completion:

```markdown
✅ Prompt 289 completed

**Summary:** [What was accomplished]

**Files changed:**
- path/to/file1.go (+50, -10)
- path/to/file2.go (+20, -5)

**Next steps:**
# Review changes
cd .worktrees/youtube_summaries-prompt-289-20251228-144050/
git diff main

# Merge if satisfied
git checkout main && git merge --no-ff prompt/289-analyze-auto-category-creation
```

Or on failure:

```markdown
❌ Prompt 289 failed

**Errors detected:**
- go: cannot find module providing package...
- build failed: exit status 1

**Log tail:**
[last 20 lines of log]

**Debug:**
# Full log
cat ~/.claude/cli-logs/codex-xhigh-289-20251228-144050.log

# Check worktree state
cd .worktrees/youtube_summaries-prompt-289-20251228-144050/ && git status
```
</output_format>

---
name: at-prompt-runner
description: Orchestrate multi-prompt execution with phase groups, optional auto-deps, and model-tiered agent roles.
allowed-tools:
  - Bash(python3:*)
  - Bash(jq:*)
  - Bash(tmux:*)
  - Bash(tail:*)
  - Bash(grep:*)
  - Bash(cat:*)
  - Bash(git:*)
  - Read
  - Grep
  - Glob
  - Task
  - Write
  - Edit
---

# at-prompt-runner

Run existing prompts using agent-team orchestration.

Use this skill when the user invokes `/run-at-prompt`.

## Group Syntax

- `->` separates sequential phases.
- `,` separates prompts inside the same phase (parallel).

Examples:
- `220,221 -> 222,223 -> 224`
- `220 -> 221,222,223 -> 224`
- `220`

Reference parse output:

```json
[
  {"phase": 1, "prompts": [220, 221], "strategy": "parallel"},
  {"phase": 2, "prompts": [222, 223], "strategy": "parallel"},
  {"phase": 3, "prompts": [224], "strategy": "parallel"}
]
```

## Resolve Helpers

```bash
PLUGIN_ROOT=$(jq -r '.plugins."daplug@cruzanstx"[0].installPath' ~/.claude/plugins/installed_plugins.json)
AT_RUNNER="$PLUGIN_ROOT/skills/at-prompt-runner/scripts/at_runner.py"
PROMPT_MANAGER="$PLUGIN_ROOT/skills/prompt-manager/scripts/manager.py"
```

## CLI Contract

```bash
python3 "$AT_RUNNER" parse "220,221 -> 222,223 -> 224"
python3 "$AT_RUNNER" parse "220 221 222" --auto-deps
python3 "$AT_RUNNER" validate "220,221 -> 222"
python3 "$AT_RUNNER" plan "220,221 -> 222" --model codex --worktree --json
```

## Required Execution Flow

### 1. Parse Input

- If user passes explicit groups, parse directly.
- If user passes space-separated prompts with `--auto-deps`, infer group order.

### 2. Validate Prompt References

Run:
```bash
python3 "$AT_RUNNER" validate "$GROUPS" [--auto-deps]
```

If validation fails, stop and report missing prompt IDs.

### 3. Auto-Deps Mode (`--auto-deps`)

When `--auto-deps` is set:
- Read prompt contents via prompt-manager.
- Spawn `at-planner` (`model: sonnet`) to review inferred dependencies.
- Ask user to confirm proposed group syntax before execution.
- Do not execute any `/run-prompt` command until confirmation is explicit.

Planner output should include:
- Proposed group syntax
- Dependency rationale per phase
- Any uncertainty/assumptions

### 4. Build Plan

Run:
```bash
python3 "$AT_RUNNER" plan "$GROUPS" --model "$MODEL" [--worktree] [--loop] [--validate] [--json]
```

If `--dry-run` is set:
- Show plan and generated `/run-prompt` commands only.
- Do not execute anything.

### 5. Execute Phase-by-Phase

For each phase:
- Launch one `at-monitor` task per prompt (`model: haiku`, `run_in_background: true`).
- Each monitor launches `/run-prompt ...` through tmux and produces an Execution Report.
- Collect reports via `TaskOutput()` and triage in orchestrator.
- Monitors only report and flag; they do not choose retries, merges, or architecture changes.

Decision rules:
- All reports `OK` -> continue to next phase.
- Any `ESCALATE` -> inspect evidence and resolve before proceeding.
- Complex unresolved failure -> spawn `at-fixer` (`model: opus`).
- File overlap/conflicts -> spawn `at-merger` (`model: sonnet`).

### 6. Optional Final Validation (`--validate`)

Spawn `at-validator` (`model: sonnet`) after all phases complete.
Validator decides:
- PASS -> done
- RETRY -> rerun specific prompts
- ESCALATE -> call `at-fixer` with explicit log line references

## Model Tiering (Mandatory)

- `at-monitor`: `haiku`
- `at-planner`: `sonnet`
- `at-validator`: `sonnet`
- `at-merger`: `sonnet`
- `at-fixer`: `opus` (only on escalation)

Do not assign sonnet/opus to monitor role.

## Monitor Contract (haiku)

Monitor agents are mechanical watchers. They do not debug or choose strategy.

Each report must include:
- log path
- exit code
- last 20 lines
- triage flags with line references

Report format requirement:
`ESCALATE|OK: {description} (see log lines N-N if applicable)`

## Flags

- `--model <model>`: default model for delegated `/run-prompt` commands
- `--auto-deps`: infer phase ordering from prompt contents
- `--validate`: append final validator phase
- `--worktree`: run each prompt in isolated worktree
- `--loop`: enable verification loop per prompt
- `--dry-run`: show plan only

## Orchestrator Prompt Pattern

Use explicit role-based Task calls:

```text
Task(subagent_type: "at-monitor", model: "haiku", run_in_background: true, prompt: "...phase command...")
Task(subagent_type: "at-validator", model: "sonnet", prompt: "...review reports...")
Task(subagent_type: "at-merger", model: "sonnet", prompt: "...resolve overlap...")
Task(subagent_type: "at-fixer", model: "opus", prompt: "...complex failure details...")
```

Always pass log path + line ranges when escalating.

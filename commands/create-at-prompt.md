---
name: create-at-prompt
description: Create an agent-team orchestration bundle (orchestrator prompt + sub-prompts)
argument-hint: <task description> [--folder <path>]
---

# Create AT Prompt

Create a multi-prompt orchestration bundle from a single task description.
Use the `at-prompt-creator` skill workflow for decomposition, prompt generation, and orchestration template quality.

## Input

User request: `$ARGUMENTS`

Optional flag:
- `--folder <path>` -> destination under `./prompts/` (never `completed/`)

## Steps

### 1) Resolve Scripts

```bash
PLUGIN_ROOT=$(jq -r '.plugins."daplug@cruzanstx"[0].installPath' ~/.claude/plugins/installed_plugins.json)
PROMPT_MANAGER="$PLUGIN_ROOT/skills/prompt-manager/scripts/manager.py"
```

### 2) Decompose Task

Identify whether the task should remain single-prompt or be split into:
- planner/orchestrator
- implementation streams
- validation stream

For `/create-at-prompt`, default to 2-5 sub-prompts plus one orchestrator.

### 3) Create Sub-Prompts

Use prompt-manager for each sub-prompt:
```bash
python3 "$PROMPT_MANAGER" create "<name>" --folder "$FOLDER" --content "$CONTENT" --json
```

Sub-prompts should be independently executable with `/run-prompt`.

### 4) Create Orchestrator Prompt

Create one orchestrator prompt that references sub-prompt IDs and uses this skeleton:

```xml
<orchestration>
  <phase name="plan">
    <!-- Claude native research/planning -->
  </phase>
  <phase name="execute" strategy="parallel|sequential">
    <delegate prompt="228a" model="opencode" flags="--worktree" />
    <delegate prompt="228b" model="codex" flags="--worktree --loop" />
  </phase>
  <phase name="validate">
    <!-- Claude native validation/merge -->
  </phase>
</orchestration>
```

The orchestrator prompt should include explicit Task() calls for role-based delegation (`at-monitor`, `at-validator`, `at-merger`, `at-fixer`) with model tiering.

Save it with prompt-manager.

### 5) Present Run Choices

After creation, show:
1. `/run-prompt <orchestrator-id> --model claude`
2. `/run-at-prompt "<group syntax>" --model <model> --worktree`
3. `/run-at-prompt "<space separated ids>" --auto-deps --dry-run`

Recommend `--worktree` for parallel phases and `--loop` for high-risk prompts.

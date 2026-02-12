---
name: at-prompt-creator
description: Create agent-team orchestrated prompt bundles (orchestrator + sub-prompts) and store them through prompt-manager.
allowed-tools:
  - Bash(python3:*)
  - Bash(jq:*)
  - Bash(cat:*)
  - Bash(printf:*)
  - Bash(mkdir:*)
  - Read
  - Write
  - Edit
  - Task
  - Grep
  - Glob
---

# at-prompt-creator

Create an orchestrated prompt set for complex work:
- 1 main orchestrator prompt
- N focused sub-prompts that can run independently

Use this skill when the user asks for `/create-at-prompt`.

## Inputs

- Task description (same quality bar as `/create-prompt`)
- Optional destination folder under `./prompts/` (never `completed/`)

## Resolve Helpers

```bash
PLUGIN_ROOT=$(jq -r '.plugins."daplug@cruzanstx"[0].installPath' ~/.claude/plugins/installed_plugins.json)
PROMPT_MANAGER="$PLUGIN_ROOT/skills/prompt-manager/scripts/manager.py"
CONFIG_READER="$PLUGIN_ROOT/skills/config-reader/scripts/config.py"
```

Use `prompt-manager` for all prompt writes/reads. Do not create files manually.

## Workflow

### 1. Analyze Complexity and Decompose

Break the task into sub-prompts only when at least one of these is true:
- Work can be parallelized across different file areas/components.
- There are distinct specialist concerns (backend, frontend, tests, infra, docs).
- The task benefits from explicit planner/executor/validator separation.

Keep sub-prompts single-purpose and executable in isolation.

### 2. Draft Sub-Prompts First

Create sub-prompts first so orchestrator delegation can reference exact prompt IDs.

For each sub-task:
```bash
python3 "$PROMPT_MANAGER" create "<subtask-name>" --folder "$FOLDER" --content "$SUB_PROMPT_CONTENT" --json
```

Each sub-prompt must include:
- Clear `<objective>`
- Narrow `<scope>`
- Explicit `<output>` files
- Prompt-local `<verification>` criteria

### 3. Create Orchestrator Prompt

After sub-prompts exist, create one orchestrator prompt that references them.

Use this template structure:

```xml
<objective>
Coordinate multi-agent execution for the parent task using existing sub-prompts.
</objective>

<orchestration>
  <phase name="plan">
    <!-- Claude native planning and risk check -->
    - Confirm assumptions, dependencies, and execution strategy.
    - Draft exact Task() orchestration with explicit escalation paths.
  </phase>
  <phase name="execute" strategy="parallel|sequential">
    <!-- Delegation to sub-prompts via /run-prompt -->
    <delegate prompt="228a" model="opencode" flags="--worktree" />
    <delegate prompt="228b" model="codex" flags="--worktree --loop" />
  </phase>
  <phase name="validate">
    <!-- Claude native integration + merge criteria -->
    - Verify outputs are consistent and conflict-free.
    - Resolve overlaps before final handoff.
  </phase>
</orchestration>

<merge_criteria>
- All sub-prompts completed or explicitly triaged.
- No unresolved file conflicts.
- Validation checks pass.
</merge_criteria>

<output>
- Final integrated summary
- Recommended /run-at-prompt group syntax
</output>
```

The orchestrator body should include explicit Task() delegations so it is executable:

```text
Task(
  subagent_type: "at-monitor",
  model: "haiku",
  run_in_background: true,
  prompt: "Launch /run-prompt 228a --model opencode --worktree and return Execution Report format."
)
```

Create orchestrator prompt:
```bash
python3 "$PROMPT_MANAGER" create "<task-name>-orchestrator" --folder "$FOLDER" --content "$ORCHESTRATOR_CONTENT" --json
```

### 4. Emit Execution Options (Decision Tree)

After prompt creation, present:

1. Run orchestrator prompt directly:
```bash
/run-prompt <orchestrator-id> --model claude
```

2. Run sub-prompts with explicit groups:
```bash
/run-at-prompt "220,221 -> 222" --model codex --worktree
```

3. Run sub-prompts with auto dependency inference:
```bash
/run-at-prompt "220 221 222" --auto-deps --dry-run
```

Recommend `--worktree` for any parallel execution. Recommend `--loop` for high-risk prompts.

## Orchestrator Quality Rules

- Plan phase stays Claude-native (research + dependency checks).
- Execute phase delegates via `/run-prompt` only; no ambiguous free-form delegation.
- Validate phase is explicit about pass/fail and merge gates.
- Keep model tiering explicit in delegation metadata where possible.
- Every delegate should be independently runnable.

## Naming Conventions

- Use concise, kebab-case names.
- Suggested naming:
  - `<task>-orchestrator`
  - `<task>-backend`
  - `<task>-frontend`
  - `<task>-tests`
  - `<task>-docs`

## Failure Handling

- If decomposition is unclear, ask 1-3 targeted clarifying questions.
- If a prompt creation call fails, stop and report exact stderr from prompt-manager.
- Never silently skip sub-prompt generation.

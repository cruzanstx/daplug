---
name: run-at-prompt
description: Run existing prompts with agent-team orchestration (phase groups + auto-deps)
argument-hint: <group-syntax|prompt-list> [--model <model>] [--auto-deps] [--validate] [--worktree] [--loop] [--dry-run]
---

# Run AT Prompt

Execute existing prompt IDs with orchestration-aware phase control.
Use the `at-prompt-runner` skill for parser/plan/validation flow and model-tiered agent delegation.

## Input

Arguments: `$ARGUMENTS`

## Group Syntax

- Parallel within phase: `220,221`
- Sequential phases: `220,221 -> 222 -> 223,224`

## Steps

### 1) Resolve Scripts

```bash
PLUGIN_ROOT=$(jq -r '.plugins."daplug@cruzanstx"[0].installPath' ~/.claude/plugins/installed_plugins.json)
AT_RUNNER="$PLUGIN_ROOT/skills/at-prompt-runner/scripts/at_runner.py"
```

### 2) Parse and Validate

```bash
python3 "$AT_RUNNER" parse "<input>" [--auto-deps]
python3 "$AT_RUNNER" validate "<input>" [--auto-deps]
```

If validation fails, stop and report missing prompts.

### 3) Build Plan

```bash
python3 "$AT_RUNNER" plan "<input>" --model "<model>" [--auto-deps] [--worktree] [--loop] [--validate] --json
```

If `--dry-run` is present:
- Display plan
- Display per-phase `/run-prompt` commands
- Exit without execution
- Ensure output clearly marks dry-run mode.

### 4) Auto-Deps Review

When `--auto-deps` is used:
- Spawn `at-planner` (`model: sonnet`) to review inferred ordering.
- Ask user to confirm the generated group syntax before execution.

### 5) Execute by Phase (Model Tiering)

For each prompt in a phase:
- Spawn `at-monitor` with `model: haiku`, `run_in_background: true`.
- Monitor launches `/run-prompt` in tmux and returns Execution Report.

Orchestrator triage:
- all `OK` -> next phase
- `ESCALATE` -> inspect logs, resolve, then continue
- complex escalation -> `at-fixer` (`model: opus`)
- merge conflict/overlap -> `at-merger` (`model: sonnet`)
- collect monitor handoffs via `TaskOutput()` before deciding next step

### 6) Final Validation

If `--validate`:
- Run `at-validator` (`model: sonnet`) after all phases.
- Follow PASS/RETRY/ESCALATE result.

## Required Role Models

- `at-monitor`: `haiku`
- `at-planner`: `sonnet`
- `at-validator`: `sonnet`
- `at-merger`: `sonnet`
- `at-fixer`: `opus` (on-demand only)

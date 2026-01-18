---
name: sprint
description: Automated sprint planning from technical specifications
argument-hint: "<spec-file-or-text> [options] | <sub-command>"
---

# Sprint

Generate prompts from a technical specification, analyze dependencies, and produce an execution plan (and optional persistent state for long-running execution).

## Supported Syntax

```bash
# Main command
/sprint ./docs/technical-spec.md --worktree --loop
/sprint "Build a REST API with auth, CRUD, and admin dashboard"
/sprint ./spec.md --dry-run
/sprint ./spec.md --auto-execute

# Sub-commands
/sprint status
/sprint add "Implement caching layer"
/sprint remove 005
/sprint replan
/sprint pause
/sprint resume
/sprint cancel
/sprint history
```

## Argument Parsing Rules

Given `$ARGUMENTS`:

1. Split arguments into tokens (shell-style).
2. If the first token is one of these sub-commands, treat it as a sub-command:
   - `status`, `add`, `remove`, `replan`, `pause`, `resume`, `cancel`, `history`
3. Otherwise, treat the first token (and the full remaining string) as the spec input for the main sprint command.

## Run the Command

### Step 0: Resolve Script Path

```bash
PLUGIN_ROOT=$(jq -r '.plugins."daplug@cruzanstx"[0].installPath' ~/.claude/plugins/installed_plugins.json)
SPRINT="$PLUGIN_ROOT/skills/sprint/scripts/sprint.py"
```

### Step 1: Dispatch

#### Sub-commands

Execute:

```bash
python3 "$SPRINT" <sub-command> [args...]
```

Mapping:
- `/sprint status` → `python3 "$SPRINT" status`
- `/sprint add "..."` → `python3 "$SPRINT" add "..."` (the rest of the args is the description)
- `/sprint remove 005` → `python3 "$SPRINT" remove 005`
- `/sprint replan` → `python3 "$SPRINT" replan`
- `/sprint pause` → `python3 "$SPRINT" pause`
- `/sprint resume` → `python3 "$SPRINT" resume`
- `/sprint cancel` → `python3 "$SPRINT" cancel` (use `--yes` to skip confirmation)
- `/sprint history` → `python3 "$SPRINT" history`

#### Main command

Execute:

```bash
python3 "$SPRINT" <spec-file-or-text> [options...]
```

Notes:
- If the spec is a file path, pass it directly (the script will read it).
- If the spec is inline text, pass it as a quoted string.
- Options are forwarded verbatim to the sprint skill.

## Output Expectations

- For planning mode: create or update `.sprint-state.json` and produce a plan (and runnable `/run-prompt` commands).
- For `--dry-run`: do not create prompt files; only show the generated plan and commands.
- For `--auto-execute`: begin executing phase-by-phase and persist progress in `.sprint-state.json`.


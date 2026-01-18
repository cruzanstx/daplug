---
name: sprint
description: Automated sprint planning and execution from technical specifications (prompt generation, dependency planning, stateful execution)
allowed-tools:
  - Bash(git:*)
  - Bash(jq:*)
  - Bash(npx cclimits:*)
  - Bash(python3:*)
  - Bash(find:*)
  - Bash(ls:*)
  - Bash(cat:*)
  - Bash(mkdir:*)
  - Bash(realpath:*)
  - Read
  - Write
  - Edit
  - Glob
  - Grep
---

# Sprint Planning + Execution

This skill turns a technical specification into:
- Prompt files (ready for `/run-prompt`)
- A dependency-aware execution plan (`sprint-plan.md`)
- A persistent state file (`.sprint-state.json`) for long-running execution

## CLI

### Main command

```bash
# From a spec (generates new prompts)
python3 skills/sprint/scripts/sprint.py <spec-file-or-text> [options]

# From existing prompts (no spec argument)
python3 skills/sprint/scripts/sprint.py --from-existing [options]
```

Options:
- `--output-dir DIR` (default: `./prompts/`) Where to write generated prompt files
- `--plan-file FILE` (default: `./sprint-plan.md`) Where to write the plan markdown
- `--dry-run` Generate plan without creating prompt files or state
- `--from-existing` Analyze existing prompts in `--output-dir` instead of generating from a spec
- `--prompts LIST` Include only specific prompts (e.g., `001-005,010`)
- `--folder PATH` Only include prompts from this subfolder of `--output-dir` (e.g., `providers/`)
- `--exclude LIST` Exclude specific prompts (e.g., `003,007`)
- `--auto-execute` Execute phases immediately, updating `.sprint-state.json`
- `--models LIST` Comma-separated models (default: `claude,codex,gemini`)
- `--max-parallel N` Max concurrent prompts per phase (default: `5`)
- `--worktree` Use worktree isolation when auto-executing
- `--loop` Use verification loops when auto-executing
- `--max-iterations N` (default: `3`) Verification loop max iterations
- `--completion-marker TEXT` (default: `VERIFICATION_COMPLETE`) Loop completion marker
- `--state-file FILE` (default: `.sprint-state.json`) State file path
- `--json` Print JSON output (plan + state summary)

### Sub-commands

```bash
python3 skills/sprint/scripts/sprint.py status
python3 skills/sprint/scripts/sprint.py add "Implement caching layer"
python3 skills/sprint/scripts/sprint.py remove 005
python3 skills/sprint/scripts/sprint.py replan
python3 skills/sprint/scripts/sprint.py pause
python3 skills/sprint/scripts/sprint.py resume
python3 skills/sprint/scripts/sprint.py cancel --yes
python3 skills/sprint/scripts/sprint.py history
```

Notes:
- Sub-commands operate on `.sprint-state.json` in the current directory unless `--state-file` is provided.
- `cancel` is destructive for sprint-created worktrees (it removes worktree directories/branches recorded in state).

### Examples

```bash
# Analyze all prompts in prompts/
python3 skills/sprint/scripts/sprint.py --from-existing --dry-run

# Only specific prompts
python3 skills/sprint/scripts/sprint.py --from-existing --prompts 001-005,010 --dry-run

# Only prompts in a subfolder
python3 skills/sprint/scripts/sprint.py --from-existing --folder providers/ --dry-run

# Exclude certain prompts
python3 skills/sprint/scripts/sprint.py --from-existing --exclude 003,007 --dry-run

# Combine with execution options
python3 skills/sprint/scripts/sprint.py --from-existing --worktree --loop --auto-execute
```

---
name: resume-handoff
description: Validate and load a compact session handoff checkpoint with Git drift detection
argument-hint: "[latest|<path>] [--json]"
---

<objective>
Load and validate a compact Daplug session handoff checkpoint for the current Git repository/worktree, compare its recorded Git state against current repository state, report any drift warnings clearly, and present the exact next action without mutating the repository or loading the full session transcript.
</objective>

<input>
Optional arguments via `$ARGUMENTS`:
- `latest` (default when no path is given): Resolve the newest checkpoint matching both the current repository identity and current worktree path
- `<path>`: Explicit path to a handoff checkpoint `.md` file
- `--state-dir <dir>`: Override the untracked Daplug handoff store root directory
- `--json`: Emit the structured validation and drift report as JSON
</input>

<process>

<step1_resolve_helper>
Resolve the `handoff` skill helper script through Claude's installed-plugin manifest (`${CLAUDE_PLUGIN_ROOT}` is not reliable in command Markdown):

```bash
PLUGIN_ROOT=$(jq -r '.plugins."daplug@cruzanstx"[0].installPath' ~/.claude/plugins/installed_plugins.json)
HANDOFF="$PLUGIN_ROOT/skills/handoff/scripts/handoff.py"
```
</step1_resolve_helper>

<step2_validate_and_load_checkpoint>
Run `handoff.py resume` with the requested target (`latest` by default, or the explicit path from `$ARGUMENTS`):

```bash
TARGET="${1:-latest}"
python3 "$HANDOFF" resume "$TARGET"
```

(Pass `--json` or `--state-dir <dir>` if requested in `$ARGUMENTS`.)

If `handoff.py resume` exits non-zero, gracefully report the validation error code and reason to the user and stop immediately:
- `missing`: No checkpoint exists at the specified path or for this repository/worktree.
- `malformed`: Checkpoint frontmatter or required sections are missing or corrupted.
- `unsupported_version`: Checkpoint uses an unsupported `schema_version`.
- `oversized`: Checkpoint exceeds the configured byte size budget.
- `wrong_repository`: Checkpoint belongs to a different Git repository (`repo_id` mismatch).
- `not_git_repo`: Current working directory is not inside a Git repository.
</step2_validate_and_load_checkpoint>

<step3_present_context_and_next_action>
When validation succeeds:
1. Clearly state whether the checkpoint is a **SAFE MATCH** (`exact_match`) or has **DRIFT WARNINGS** (`drift_detected` across `worktree`, `branch`, `head`, or `dirty_state`).
2. If any drift warnings exist, list each warning (`recorded` vs `current`) so the user can decide how to proceed.
3. Adopt the compact checkpoint sections (`Objective`, `Completed Work`, `Decisions and Rationale`, `Constraints`, `Changed Files`, `Verification Evidence`, `Blockers / Unresolved Questions`) as your working context.
4. Highlight the **Exact Next Action** from the checkpoint and ask the user if they want to proceed with it (or how they want to handle any reported drift).
</step3_present_context_and_next_action>

</process>

<safety_constraints>
- **NEVER** automatically edit files, stage/unstage changes, switch or reset branches, `git checkout`/`git restore`, or modify worktrees during `/daplug:resume-handoff`.
- **NEVER** automatically execute build, test, or shell commands from the checkpoint without user direction.
- **NEVER** read or replay the fallback session transcript (`transcript_path`) during `/daplug:resume-handoff`. Consult the transcript only if the user explicitly asks or a specific missing detail cannot be recovered from the repository or checkpoint.
</safety_constraints>

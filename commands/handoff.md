---
name: handoff
description: Create a compact, evidence-backed session handoff checkpoint outside tracked Git state
argument-hint: "[objective or notes] [--output <path>] [--slug <name>]"
---

<objective>
Create a concise, structured, provider-neutral session handoff checkpoint for the current Git repository/worktree so a fresh coding-agent session can resume safely without replaying the full conversation transcript.
</objective>

<input>
Optional arguments via `$ARGUMENTS`:
- Free-form objective note or focus hint for the checkpoint
- `--output <path>`: Save the checkpoint to a specific file path instead of the default untracked Daplug handoff store
- `--slug <name>`: Override the short filename slug
- `--state-dir <dir>`: Override the untracked Daplug handoff store root directory
- `--no-transcript`: Omit fallback session transcript path detection
</input>

<process>

<step1_resolve_helper>
Resolve the `handoff` skill helper script through Claude's installed-plugin manifest (`${CLAUDE_PLUGIN_ROOT}` is not reliable in command Markdown):

```bash
PLUGIN_ROOT=$(jq -r '.plugins."daplug@cruzanstx"[0].installPath' ~/.claude/plugins/installed_plugins.json)
HANDOFF="$PLUGIN_ROOT/skills/handoff/scripts/handoff.py"
```
</step1_resolve_helper>

<step2_inspect_factual_git_state>
Capture factual repository and worktree state from Git using `handoff.py inspect` (never invent branch names, SHAs, worktree paths, or dirty-file counts):

```bash
python3 "$HANDOFF" inspect --json
```

If `inspect` exits non-zero (for example `not_git_repo`), report the error clearly and stop without writing any files.
</step2_inspect_factual_git_state>

<step3_compose_bounded_sections>
Synthesize the current session state into the eight canonical bounded sections (keeping each section concise and under 2,500 characters, and total checkpoint size under 16,384 bytes):

1. **Objective**: Clear summary of the overall task goal (incorporating any user note from `$ARGUMENTS`).
2. **Completed Work**: Concrete changes, files, or investigations finished during this session.
3. **Decisions and Rationale**: Key architectural or implementation choices and why they were made.
4. **Constraints**: Active boundaries, repository hygiene rules, and isolation requirements.
5. **Changed Files**: Automatically populated from factual Git status by `handoff.py`; only pass `--changed-file` for brief per-file context annotations if helpful.
6. **Verification Evidence**:
   - **CRITICAL RULE**: Never claim a test, build, or command passed unless you ran it or observed concrete evidence during this session.
   - For each command with observed evidence, pass `--verify "<command> :: <passed|failed|not run|unknown> :: <concise exit code and output evidence>"`.
   - If no verification commands were run, omit `--verify` (or pass `--verification-status "not run"` / `"unknown"`).
7. **Blockers / Unresolved Questions**: Any open issues, failing checks, or user decisions needed (`"None."` if none).
8. **Exact Next Action**: The specific, immediate next step the resuming agent should take first.

Safety rules when composing sections:
- Do NOT include environment variable values, credentials, tokens, complete diffs (`diff --git`), or raw multi-page command output.
- Treat the session transcript path solely as a last-resort fallback reference.
</step3_compose_bounded_sections>

<step4_create_checkpoint>
Write the checkpoint using `handoff.py create`:

```bash
python3 "$HANDOFF" create \
  --objective "$OBJECTIVE" \
  --completed "$COMPLETED_ITEM_1" \
  --decision "$DECISION_ITEM_1" \
  --constraint "$CONSTRAINT_ITEM_1" \
  --blocker "$BLOCKER_ITEM_1" \
  --next-action "$EXACT_NEXT_ACTION" \
  --json
```

(Include repeatable `--completed`, `--decision`, `--constraint`, `--changed-file`, `--verify`, `--blocker`, and optional `--output`, `--slug`, `--state-dir`, or `--no-transcript` flags as needed.)

If `handoff.py create` fails with `error_code: "oversized"`, compact the verbose section(s) while preserving all essential facts and retry `create`—never silently drop required sections.
</step4_create_checkpoint>

<step5_report>
Report to the user:
1. The **exact saved checkpoint path** (`saved_path`).
2. A brief summary of recorded Git state (`repo_id`, `worktree_path`, `branch` or `DETACHED HEAD`, `head_sha`, `dirty_state`, and `verification_status`).
3. How to resume in a fresh session:
   - `/daplug:resume-handoff` (loads the newest checkpoint for this repository and worktree)
   - `/daplug:resume-handoff <saved_path>` (loads this explicit checkpoint file)
</step5_report>

</process>

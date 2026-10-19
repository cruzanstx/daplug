---
name: handoff
description: Create, validate, and resume compact provider-neutral session handoff checkpoints with factual Git state and drift detection.
allowed-tools:
  - Bash(python3:*)
  - Bash(jq:*)
  - Bash(git:*)
  - Bash(PLUGIN_ROOT=:*)
  - Bash(HANDOFF=:*)
  - Read
---

# Session Handoff (`handoff`)

Create and resume compact, evidence-backed session checkpoints that let a user end a long coding-agent session and resume safely in a fresh session (across Claude, Codex, OpenCode, Antigravity/Gemini, Synthetic, or local models) without replaying the full session transcript.

## Resolve Helper Script

Always resolve the helper through Claude's installed plugin manifest (`${CLAUDE_PLUGIN_ROOT}` is unreliable in command Markdown):

```bash
PLUGIN_ROOT=$(jq -r '.plugins."daplug@cruzanstx"[0].installPath' ~/.claude/plugins/installed_plugins.json)
HANDOFF="$PLUGIN_ROOT/skills/handoff/scripts/handoff.py"
```

## Format Contract (`daplug-handoff` v1)

Every handoff artifact is a UTF-8 Markdown file with:

1. **Versioned Machine-Readable Frontmatter (`---`)**:
   - `schema`: `"daplug-handoff"`
   - `schema_version`: `1`
   - `generated_at`: UTC ISO-8601 timestamp (`YYYY-MM-DDTHH:MM:SSZ`)
   - `repo_id`: Deterministic repository identity derived from normalized `--git-common-dir` (`<repo_slug>-<sha256[:16]>`)
   - `repo_root`: Normalized POSIX path of the repository root
   - `worktree_id`: Deterministic worktree identity derived from normalized `--show-toplevel` (`<worktree_slug>-<sha256[:16]>`)
   - `worktree_path`: Normalized POSIX path of the active worktree
   - `is_linked_worktree`: Boolean indicating whether the checkpoint was created from a linked Git worktree
   - `branch`: Checked-out branch name, or `null` when HEAD is detached
   - `detached`: Boolean (`true` when in detached HEAD state)
   - `head_sha`: 40-character commit SHA from `git rev-parse --verify HEAD` (or `"UNBORN"`)
   - `dirty_state`: Human-readable summary (`clean (0 staged, 0 unstaged, 0 untracked)` or `dirty (...)`)
   - `is_dirty`: Boolean
   - `staged_count`, `unstaged_count`, `untracked_count`: Non-negative integers from `git status --porcelain=v1 -z -uall`
   - `dirty_entries_hash`: Deterministic hash of working-tree status entries (or `"clean"`)
   - `verification_status`: One of `"not run"`, `"unknown"`, `"passed"`, `"failed"`, `"partial"`
   - `transcript_path`: Normalized path to the session transcript when detectable, or `null`
   - `transcript_policy`: `"fallback_only_do_not_read_by_default"`
   - `size_budget_bytes`: Maximum byte budget enforced for the checkpoint (default `16384`)

2. **Eight Required Bounded Sections**:
   - `## Objective`
   - `## Completed Work`
   - `## Decisions and Rationale`
   - `## Constraints`
   - `## Changed Files`
   - `## Verification Evidence`
   - `## Blockers / Unresolved Questions`
   - `## Exact Next Action`

## Storage & Safety Rules

- **Untracked Daplug-Owned Storage**:
  - Default storage root: `~/.claude/handoffs/<repo_id>/<worktree_id>/` (override via `DAPLUG_HANDOFF_DIR`, `--state-dir`, or explicit `--output`).
  - Never writes into the repository working tree by default and never modifies tracked `.gitignore` files.
  - Uses atomic temporary-file writes (`os.replace`) with restrictive permissions (`0600` for checkpoint files, `0700` for directories).
- **Scoped `latest` Resolution**:
  - `latest` only resolves checkpoints matching **both** the current `repo_id` and current `worktree_path`, preventing multiple repositories or linked worktrees from consuming each other's `latest` checkpoint.
- **Size Budget**:
  - Default budget is **16,384 bytes (16 KiB)** total and **2,500 characters** per section.
  - Raw unified diffs (`diff --git`) and oversized sections are rejected with `error_code: "oversized"` rather than silently truncating essential content.
- **Verification Honesty**:
  - Never claims `"passed"` unless actual command + outcome evidence from the session is supplied (`command :: passed :: concrete evidence`).
  - Uses explicit `"not run"` or `"unknown"` states otherwise; unverified pass claims are automatically downgraded to `"unknown"`.
- **Transcript Fallback Policy**:
  - The session transcript path is recorded only as a last-resort reference. Resuming agents must **not** read the transcript unless a specific missing detail cannot be recovered from the checkpoint or repository.
- **Conservative Secret Redaction**:
  - Automatically redacts PEM private keys, Bearer/Authorization headers, URL basic-auth credentials, common API/PAT tokens (`sk-*`, `ghp_*`, `github_pat_*`, `glpat-*`, `AKIA*`, `xox*-*`, `AIza*`, `hf_*`, `npm_*`, JWTs), and sensitive key/value assignments before writing.

## CLI Usage

### Inspect Factual Git State

```bash
python3 "$HANDOFF" inspect --json
```

### Create a Checkpoint

```bash
python3 "$HANDOFF" create \
  --objective "Implement provider-neutral session handoff workflow" \
  --completed "Added skills/handoff/scripts/handoff.py with Git inspection and drift analysis" \
  --decision "Store checkpoints under ~/.claude/handoffs/<repo_id>/<worktree_id>/ to avoid git status pollution" \
  --constraint "Preserve unrelated working-tree changes; do not replay full transcript" \
  --verify "python3 -m pytest skills/handoff/tests -v :: passed :: 28 passed in 0.45s (exit 0)" \
  --blocker "None." \
  --next-action "Run ./scripts/run-tests.sh and finalize documentation tables in README.md" \
  --json
```

### Resume a Checkpoint (`latest` or explicit path)

```bash
# Resume newest checkpoint for current repository + worktree
python3 "$HANDOFF" resume latest

# Resume explicit checkpoint file path
python3 "$HANDOFF" resume /path/to/checkpoint.md --json
```

### List Checkpoints for Current Repository/Worktree

```bash
python3 "$HANDOFF" list --json
```

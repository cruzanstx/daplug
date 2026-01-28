---
name: uvc
description: Update documentation and push changes to version control (main repository)
---

<objective>
Update project documentation (memory-bank, README, CLAUDE.md) based on recent code changes, then commit and push. Works in both main repo and worktrees.
</objective>

<context_detection>
**Detect execution context:**
```bash
REPO_ROOT=$(git rev-parse --show-toplevel)
REPO_NAME=$(basename "$REPO_ROOT")

# Check if we're in a worktree
if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    GIT_DIR=$(git rev-parse --git-dir)
    if [[ "$GIT_DIR" == *".git/worktrees/"* ]]; then
        IS_WORKTREE=true
        MAIN_REPO=$(git rev-parse --path-format=absolute --git-common-dir | sed 's|/.git$||')
    else
        IS_WORKTREE=false
        MAIN_REPO="$REPO_ROOT"
    fi
fi
```

**Worktree behavior:**
- If in worktree: Update memory-bank files in the worktree (they'll be merged later)
- If in main repo: Update memory-bank files directly
</context_detection>

<workflow>

## Step 1: Check Git Status

```bash
git status
git log --oneline -5  # See recent commits for context
```

## Step 2: Analyze Recent Changes

Review what was changed:
- Read recent commit messages
- Check modified files (`git diff --stat HEAD~5` or similar)
- Understand the scope of changes (feature, fix, refactor, etc.)

## Step 3: Update Documentation

Based on recent changes, update these files **as needed** (skip if no relevant changes):

### memory-bank/deltas.md (ALWAYS update if there are changes)
- Add entry for today's date with bullet points of what changed
- Keep entries concise but informative
- Most recent changes at top

### memory-bank/activeContext.md
- Update "Current Focus" section with what was just completed
- Update "Recent Activities" with specific details
- Update "Pending Work" and "Next Immediate Steps"

### memory-bank/progress.md
- Add completed tasks to "Recent Completed Tasks" section
- Include commit hashes, file changes, impact notes
- Update "Known Issues" if any were fixed or discovered

### memory-bank/systemPatterns.md (if architecture changed)
- Document new patterns or architectural decisions
- Update status of planned features

### memory-bank/projectbrief.md (if project scope changed)
- Update reality check section
- Update component descriptions

### CLAUDE.md (if workflow/commands changed)
- Document new commands or scripts
- Update build instructions
- Add new environment variables

### README.md (if user-facing changes)
- Update feature list
- Update setup instructions
- Add new examples

## Step 4: Commit Documentation

```bash
# Stage memory-bank and doc changes
git add memory-bank/ CLAUDE.md README.md 2>/dev/null

# Check what's staged
git status

# Commit with conventional format (skip CI for docs-only changes)
git commit -m "docs: update memory bank with <brief-description> [skip ci]

<optional body with details>

Generated with [Claude Code](https://claude.ai/code)
via [Happy](https://happy.engineering)

Co-Authored-By: Claude <noreply@anthropic.com>
Co-Authored-By: Happy <yesreply@happy.engineering>"
```

## Step 5: Push (unless in worktree)

**If in main repo:**
```bash
git push origin $(git rev-parse --abbrev-ref HEAD)
```

**If in worktree:**
- Do NOT push (changes will be merged later via run-prompt-worktree)
- Report: "Documentation updated in worktree. Will be included in merge."

</workflow>

<guidelines>
- Focus on documenting WHAT changed and WHY
- Reference specific files with paths
- Include commit hashes when relevant
- Keep entries concise but complete
- Use bullet points for readability
- Don't duplicate information across files
- Skip files that have no relevant updates
</guidelines>

<commit_format>
**Type prefixes:**
- `docs:` - Documentation only
- `docs(scope):` - Documentation for specific area (frontend, backend, processor)

**CI Skip:** Always append `[skip ci]` to the commit subject line for documentation-only commits to avoid triggering unnecessary CI/CD pipelines.

**Examples:**
- `docs: update memory bank with GitHub schema migration [skip ci]`
- `docs(processor): document new job types in systemPatterns [skip ci]`
- `docs: archive completed prompts and update progress [skip ci]`
</commit_format>

<important>
- NEVER commit secrets (.env files, tokens, credentials)
- NEVER push from worktrees (let run-prompt-worktree handle merging)
- Keep memory-bank hierarchy: projectbrief (foundation) → activeContext/systemPatterns/techContext → progress/deltas
- Update deltas.md for every significant change (it's the quick-reference changelog)
</important>

<invocation_modes>
**Manual invocation:** User runs `/daplug:uvc` directly after completing work
**Automatic invocation:** Called by `/daplug:run-prompt --worktree` before final commit

When called automatically, the caller will pass context about what was implemented.
</invocation_modes>

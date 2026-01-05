---
name: prompts
description: Analyze prompts folder and recommend what to work on next
argument-hint: [--pending|--completed|--all] [--verbose] [--refresh]
---

<objective>
Analyze all prompts in `./prompts/` directory to provide an actionable overview of pending work, showing what features are planned, which may already be implemented, and recommending what to tackle next.

Uses memory bank caching to avoid re-analyzing unchanged prompts.
Suggests executable `/daplug:run-prompt` or `/daplug:run-prompt --worktree` commands with the user's preferred agent.
</objective>

<input>
Optional flags via $ARGUMENTS:
- `--pending` (default): Show only pending prompts (in `./prompts/*.md`)
- `--completed`: Show only completed prompts (in `./prompts/completed/`)
- `--all`: Show both pending and completed prompts
- `--verbose`: Include more detail from each prompt's content
- `--refresh`: Force re-analysis, ignoring cache
</input>

<process>

<step0_resolve_prompt_manager>
**IMPORTANT:** Use the prompt-manager script for all prompt operations:

```bash
PLUGIN_ROOT=$(jq -r '.plugins."daplug@cruzanstx"[0].installPath' ~/.claude/plugins/installed_plugins.json)
PROMPT_MANAGER="$PLUGIN_ROOT/skills/prompt-manager/scripts/manager.py"
CONFIG_READER="$PLUGIN_ROOT/skills/config-reader/scripts/config.py"
```

This ensures consistent git root detection and prompt resolution across all daplug commands.
</step0_resolve_prompt_manager>

<step0_check_agent_preference>
**Check CLAUDE.md for preferred agent before generating recommendations:**

1. Look for `preferred_agent` setting (project first, then user-level) via `<daplug_config>`:
```bash
# Get REPO_ROOT from prompt-manager for consistent path resolution
REPO_ROOT=$(python3 "$PROMPT_MANAGER" info --json | jq -r '.repo_root')

# Check project-level first, then user-level via config reader
PREFERRED_AGENT=$(python3 "$CONFIG_READER" get preferred_agent --repo-root "$REPO_ROOT")
echo "${PREFERRED_AGENT:-not_set}"
```

2. **If not found, prompt the user:**
Use AskUserQuestion tool with options:
- `claude` - Claude Code (default, most capable)
- `codex` - OpenAI Codex CLI (gpt-5.2-codex, default reasoning)
- `codex-high` - OpenAI Codex CLI with high reasoning effort
- `codex-xhigh` - OpenAI Codex CLI with extra-high reasoning effort
- `gemini` - Google Gemini CLI
- `zai` - Z.AI GLM-4.6 via Codex CLI

3. **After user selects, save to user-level `~/.claude/CLAUDE.md`** (applies to all projects):
```bash
# Create ~/.claude/ if needed
mkdir -p ~/.claude

# Set preferred_agent in user-level CLAUDE.md using <daplug_config>
python3 "$CONFIG_READER" set preferred_agent "<selected_agent>" --scope user
```

4. Store the preference for use in recommendations.
</step0_check_agent_preference>

<step1_check_memory_bank_cache>
**BEFORE doing any analysis, check for cached results:**

1. Check if memory bank exists: `./memory-bank/`
2. Check for cache file: `./memory-bank/prompts-analysis.md`
3. If cache exists, check freshness using prompt-manager:

```bash
# Get prompt info from prompt-manager (JSON includes counts and paths)
PROMPT_INFO=$(python3 "$PROMPT_MANAGER" info --json)
PENDING_COUNT=$(echo "$PROMPT_INFO" | jq -r '.active_count')
COMPLETED_COUNT=$(echo "$PROMPT_INFO" | jq -r '.completed_count')
PROMPTS_DIR=$(echo "$PROMPT_INFO" | jq -r '.prompts_dir')
COMPLETED_DIR=$(echo "$PROMPT_INFO" | jq -r '.completed_dir')

# Get newest prompt file timestamp
NEWEST_PROMPT=$(ls -t "$PROMPTS_DIR"/*.md "$COMPLETED_DIR"/*.md 2>/dev/null | head -1)
NEWEST_TIME=$(stat -c %Y "$NEWEST_PROMPT" 2>/dev/null || echo 0)

# Check cache metadata (first 10 lines contain counts and timestamp)
if [ -f "./memory-bank/prompts-analysis.md" ]; then
    CACHE_TIME=$(stat -c %Y "./memory-bank/prompts-analysis.md" 2>/dev/null || echo 0)
    # Cache is fresh if it's newer than newest prompt
fi
```

**Cache decision:**
- If `--refresh` flag: Skip cache, do full analysis
- If cache exists AND cache timestamp > newest prompt timestamp: Use cache (just display it)
- If cache is stale or missing: Do full analysis, then update cache

**When using cache:**
```
Read `./memory-bank/prompts-analysis.md` and display its content.
Add a note: "📋 Using cached analysis from [date]. Use `--refresh` to re-analyze."
```
</step1_check_memory_bank_cache>

<step2_gather_prompts>
Use prompt-manager to list prompts consistently (handles git root detection, filtering, etc.):

```bash
# List all prompts as JSON (includes number, name, path, status)
python3 "$PROMPT_MANAGER" list --json

# List only active (pending) prompts
python3 "$PROMPT_MANAGER" list --active --json

# List only completed prompts
python3 "$PROMPT_MANAGER" list --completed --json
```

**Based on user flags:**
- `--pending` (default): Use `python3 "$PROMPT_MANAGER" list --active --json`
- `--completed`: Use `python3 "$PROMPT_MANAGER" list --completed --json`
- `--all`: Use `python3 "$PROMPT_MANAGER" list --json`

The JSON output contains:
```json
[
  {"number": "006", "name": "backup-server", "filename": "006-backup-server.md", "path": "/path/to/prompts/006-backup-server.md", "status": "active"},
  {"number": "001", "name": "initial-setup", "filename": "001-initial-setup.md", "path": "/path/to/prompts/completed/001-initial-setup.md", "status": "completed"}
]
```

**Get repo info for absolute paths:**
```bash
# Get repo root and prompts directory paths
REPO_INFO=$(python3 "$PROMPT_MANAGER" info --json)
REPO_ROOT=$(echo "$REPO_INFO" | jq -r '.repo_root')
PROMPTS_DIR=$(echo "$REPO_INFO" | jq -r '.prompts_dir')
```
</step2_gather_prompts>

<step3_analyze_each_prompt>
For each pending prompt from the JSON list:

1. **Metadata is already extracted** from prompt-manager:
   - `number` (e.g., `"011"`)
   - `name` (e.g., `"authentication-system"`)
   - `path` (absolute path to file)
   - `status` ("active" or "completed")

2. **Read prompt content** using prompt-manager:
```bash
# Read full content
python3 "$PROMPT_MANAGER" read {number}

# Or read first 100 lines for analysis
python3 "$PROMPT_MANAGER" read {number} | head -100
```

   Extract from content:
   - `<objective>` section - what the prompt aims to accomplish
   - `<context>` section - background, dependencies, what's already done
   - Look for markers like "ALREADY IMPLEMENTED", "REMAINING TO IMPLEMENT", "PARTIAL", etc.

3. **Check implementation status** by searching codebase:
   - Search for keywords from the prompt name in code files
   - Check `memory-bank/progress.md` for mentions of this feature
   - Check `CLAUDE.md` for documentation of this feature
   - Look for related test files

4. **Categorize status**:
   - `NOT STARTED` - No evidence of implementation
   - `PARTIAL` - Some parts implemented, some remaining
   - `LIKELY DONE` - Evidence suggests complete (should verify)
   - `BLOCKED` - Has dependencies on other prompts
</step3_analyze_each_prompt>

<step4_group_and_prioritize>
Group prompts by category based on filename patterns:
- **Infrastructure/DevOps**: deployment, ci, docker, k8s, monitoring
- **Backend**: api, backend, pipeline, processor, postgres
- **Frontend**: frontend, ui, dashboard, layout
- **Features**: auth, oauth, notifications, summaries
- **Testing**: test, integration, coverage
- **Research/Analysis**: research, analysis, investigation

Prioritize based on:
1. Dependencies (what unblocks other work)
2. Quick wins (small scope, high value)
3. Core functionality vs nice-to-have

**Identify parallelizable prompts:**
- Group prompts that touch different files/components
- Note which can run simultaneously in worktrees
</step4_group_and_prioritize>

<step5_check_worktree_dir>
**Check for worktree_dir setting before generating report:**

```bash
# Use REPO_ROOT from prompt-manager info (already resolved in step2)
REPO_ROOT=$(python3 "$PROMPT_MANAGER" info --json | jq -r '.repo_root')
REPO_NAME=$(basename "$REPO_ROOT")

# Read worktree_dir from CLAUDE.md (project first, then user-level)
WORKTREE_DIR=$(python3 "$CONFIG_READER" get worktree_dir --repo-root "$REPO_ROOT")
```

**If not found, prompt the user:**
Use AskUserQuestion tool:
- Question: "Where should git worktrees be created?"
- Header: "Worktree dir"
- Options:
  - `../worktrees` - Sibling directory to current repo (Recommended)
  - `/tmp/worktrees` - Temporary directory
  - Other - Let user specify custom path

**After user responds, save to `~/.claude/CLAUDE.md`:**
```bash
# Resolve to absolute path
WORKTREE_DIR=$(cd "$WORKTREE_DIR" 2>/dev/null && pwd || mkdir -p "$WORKTREE_DIR" && cd "$WORKTREE_DIR" && pwd)

# Save to user-level CLAUDE.md
mkdir -p ~/.claude
python3 "$CONFIG_READER" set worktree_dir "$WORKTREE_DIR" --scope user
```
</step5_check_worktree_dir>

<step6_generate_report>
**CRITICAL: Use absolute paths for all file and directory references.**

Use the `$REPO_ROOT`, `$REPO_NAME`, and `$WORKTREE_DIR` variables from previous steps.

Output a structured report with:

```markdown
## Prompts Analysis Report

### Summary
- Pending: X prompts
- Completed: Y prompts
- Estimated implementation status breakdown

### Pending Prompts by Category

#### Research/Analysis
| #   | Prompt                        | Notes                                          | Command                                         |
|-----|-------------------------------|------------------------------------------------|-------------------------------------------------|
| 275 | Production Deployment Revisit | Re-evaluate self-hosted vs cloud options       | /daplug:run-prompt 275 --model {agent} --worktree |

#### Backend Features
| #   | Prompt                        | Notes                                          | Command                                         |
|-----|-------------------------------|------------------------------------------------|-------------------------------------------------|
| 295 | Transcript Success Monitoring | Add metrics table for fetch success rates      | /daplug:run-prompt 295 --model {agent} --worktree |

#### Infrastructure/DevOps
| #   | Prompt                        | Notes                                          | Command                                         |
|-----|-------------------------------|------------------------------------------------|-------------------------------------------------|
| 045 | Deploy Delays to Staging      | Deployment pipeline improvements               | /daplug:run-prompt 045 --model {agent} --worktree |

### Recommendations

**Quick Wins** (start here):
- 289 + 303 - Analysis/investigation, no code conflicts, can run parallel:
  `/daplug:run-prompt 289 303 --model {agent} --worktree`

**High Priority** (core functionality):
- 295 then 298 - Backend features, run sequential:
  `/daplug:run-prompt 295 --model {agent} --worktree`

**Consider Skipping/Archiving**:
- [Prompt #] - [Name] - [Why - may be obsolete or already done]

### Recently Completed (last 5)
- [#] - [Name]

---

## Quick Start Commands

**Preferred Agent:** `{preferred_agent}` (change in `$REPO_ROOT/CLAUDE.md` under `<daplug_config>`)

### Run Single Prompt (in current context)
```bash
/daplug:run-prompt {recommended_prompt_number} --model {preferred_agent}
```

### Run Single Prompt (isolated worktree)
```bash
/daplug:run-prompt {recommended_prompt_number} --model {preferred_agent} --worktree
# Worktree: $WORKTREE_DIR/$REPO_NAME-prompt-{number}-{timestamp}/
# Logs: $WORKTREE_DIR/$REPO_NAME-prompt-{number}-{timestamp}/worktree.log
```

### Run Multiple Prompts in Parallel (worktrees)
```bash
/daplug:run-prompt {prompt1} {prompt2} {prompt3} --model {preferred_agent} --worktree
```
Example for parallel execution:
```bash
/daplug:run-prompt 227 228 229 --model {preferred_agent} --worktree
# Creates 3 parallel worktrees:
# - $WORKTREE_DIR/$REPO_NAME-prompt-227-{timestamp}/
# - $WORKTREE_DIR/$REPO_NAME-prompt-228-{timestamp}/
# - $WORKTREE_DIR/$REPO_NAME-prompt-229-{timestamp}/
```

### Check Active Worktrees
```bash
git worktree list
ls -la "$WORKTREE_DIR/"
```

### Monitor Worktree Progress
```bash
# View logs for a specific worktree
tail -f "$WORKTREE_DIR/$REPO_NAME-prompt-{number}-"*/worktree.log

# Check all worktree statuses
for d in "$WORKTREE_DIR/$REPO_NAME-prompt-"*/; do
  echo "=== $d ==="
  tail -5 "$d/worktree.log" 2>/dev/null || echo "No log yet"
done
```

---

## File Locations

| Resource | Path |
|----------|------|
| Pending Prompts | `$REPO_ROOT/prompts/` |
| Completed Prompts | `$REPO_ROOT/prompts/completed/` |
| Worktrees | `$WORKTREE_DIR/` |
| Memory Bank | `$REPO_ROOT/memory-bank/` |
| Cache File | `$REPO_ROOT/memory-bank/prompts-analysis.md` |
| CLAUDE.md | `$REPO_ROOT/CLAUDE.md` |
```
</step6_generate_report>

<step7_update_memory_bank>
**After generating the report, save to memory bank:**

1. Check if memory bank directory exists:
```bash
if [ -d "./memory-bank" ]; then
    # Memory bank exists, save cache
fi
```

2. Write the analysis to `./memory-bank/prompts-analysis.md` with metadata header:
```markdown
---
generated: YYYY-MM-DD HH:MM:SS
pending_count: X
completed_count: Y
preferred_agent: {agent}
cache_note: Auto-generated by /daplug:prompts command. Delete to force refresh.
---

# Prompts Analysis Report

[Full analysis report here with absolute paths]
```

3. The cache file should contain:
   - Generation timestamp
   - Prompt counts (for quick staleness check)
   - Preferred agent setting
   - Full analysis report with absolute paths
   - Recommendations with executable commands

This allows the next `/daplug:prompts` run to:
- Quickly compare counts to detect new/removed prompts
- Skip full analysis if nothing changed
- Show when analysis was last run
</step7_update_memory_bank>

</process>

<implementation_detection_patterns>
When checking if a feature might be implemented, look for:

**Authentication prompts**: Check `frontend/src/lib/auth.js`, `Logon.svelte`, look for OAuth config
**API prompts**: Check `backend/internal/app/` for route handlers
**Processor prompts**: Check `processor/internal/pipeline/services/`
**Frontend prompts**: Check `frontend/src/routes/` and `frontend/src/lib/components/`
**Database prompts**: Check migration files in `processor/migrations/`
**CI/CD prompts**: Check `.gitlab-ci.yml`
**Testing prompts**: Check `tests/` directory

Use grep patterns like:
```bash
# Check if feature keywords exist in codebase
grep -rl "keyword" --include="*.go" --include="*.svelte" --include="*.ts" backend/ frontend/ processor/
```
</implementation_detection_patterns>

<output_format>
**Key principle: Every prompt listing includes a ready-to-copy command.**

Use clean markdown formatting with:
- Tables for prompt listings
- Clear section headers
- **Absolute paths for ALL file/directory references** (ctrl+click friendly)
- Executable command examples with full paths
- Actionable recommendations at the end

Keep the output scannable - users want to quickly see what's available and what to do next.

**Path format examples (using variables from step5):**
- Use `$REPO_ROOT/prompts/216-svelte5-layouts-quick-wins.md`
- Use `$WORKTREE_DIR/$REPO_NAME-prompt-216-20251221/`
- Avoid relative paths like `./prompts/216-svelte5-layouts-quick-wins.md`

**Table format - MUST include Command column:**

```markdown
| #   | Prompt                     | Notes                              | Command                                         |
|-----|----------------------------|------------------------------------|-------------------------------------------------|
| 303 | Shorts Generation Workflow | Frontend shows "queued" - trace it | /daplug:run-prompt 303 --model codex --worktree |
```

**Table columns:**
1. `#` - Prompt number (for quick reference)
2. `Prompt` - Short descriptive name (from filename slug)
3. `Notes` - One-line summary of what it does
4. `Command` - Full executable command with preferred agent

**Formatting rules:**
- Group prompts by category (Research, Backend, Frontend, etc.)
- Keep Notes column concise (< 60 chars)
- Always include `--worktree` in commands for isolation
- Use the user's `preferred_agent` from `<daplug_config>` in CLAUDE.md in all commands

**Recommendations section format:**
```markdown
Quick Wins (start here):
- 289 + 303 - Analysis/investigation, no code conflicts, can run parallel:
  /daplug:run-prompt 289 303 --model {preferred_agent} --worktree

High Priority (core functionality):
- 295 then 298 - Backend features, run sequential
```
</output_format>

<critical_notes>
- Focus on PENDING prompts by default (that's what users care about)
- Don't just list files - provide analysis and recommendations
- Check for partial implementations to avoid duplicate work
- Consider dependencies between prompts
- If a prompt looks obsolete or already done, flag it for review
- Keep the analysis practical and actionable
- **Always check memory bank cache first** - saves significant time on repeated runs
- **Always update cache after analysis** - ensures next run is fast
- If no memory bank exists, just do analysis without caching (don't create memory-bank/)
- **Always use absolute paths** - enables ctrl+click in VSCode
- **Check/set preferred_agent** - ensures consistent agent recommendations
- **Include executable commands** - copy-paste ready /run-prompt commands
</critical_notes>

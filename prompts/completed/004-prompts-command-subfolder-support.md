<objective>
Update the `/prompts` command to support subfolder organization.

The prompt-manager and run-prompt skills now support subfolders (e.g., `prompts/providers/`, `prompts/backend/`), but the `/prompts` analysis command still assumes a flat structure. This prompt adds subfolder awareness to the analysis and display.
</objective>

<context>
**Already implemented** (in prompt 001-prompt-subfolder-support):
- `prompt-manager` lists prompts with `folder` field in JSON output
- `prompt-manager list --tree` shows tree view
- `run-prompt` accepts `folder/number` format (e.g., `providers/011`)

**Not yet updated**:
- `/prompts` command (`commands/prompts.md`) - assumes flat structure

Current JSON output from prompt-manager:
```json
{
  "number": "011",
  "name": "github-copilot",
  "folder": "providers",
  "path": "prompts/providers/011-github-copilot.md",
  "status": "active"
}
```

The `/prompts` command should use this `folder` field to group and display prompts.
</context>

<requirements>
## New flags

Add to argument-hint:
```
[--folder <name>] [--tree]
```

- `--folder providers` - Filter to only show prompts in that subfolder
- `--tree` - Show tree view instead of tables

## Updated report format

### Option 1: Group by folder (default when subfolders exist)
```markdown
### Pending Prompts by Folder

#### Root (prompts/)
| #   | Prompt           | Notes              | Command |
|-----|------------------|--------------------|---------|
| 001 | initial-setup    | Bootstrap project  | /daplug:run-prompt 001 --model codex --worktree |
| 002 | add-feature      | New feature X      | /daplug:run-prompt 002 --model codex --worktree |

#### providers/
| #   | Prompt           | Notes              | Command |
|-----|------------------|--------------------|---------|
| 011 | github-copilot   | Add Copilot support | /daplug:run-prompt providers/011 --model codex --worktree |
| 012 | cursor           | Add Cursor support  | /daplug:run-prompt providers/012 --model codex --worktree |

#### backend/
| #   | Prompt           | Notes              | Command |
|-----|------------------|--------------------|---------|
| 020 | api-refactor     | Restructure API    | /daplug:run-prompt backend/020 --model codex --worktree |
```

### Option 2: Tree view (--tree flag)
```markdown
### Pending Prompts

prompts/
├── 001-initial-setup.md
├── 002-add-feature.md
├── providers/
│   ├── 011-github-copilot.md
│   ├── 012-cursor.md
│   └── 013-replit.md
├── backend/
│   └── 020-api-refactor.md
└── completed/
    └── 003-bug-fix.md
```

## Command format updates

When prompts are in subfolders, commands should include the folder prefix:
```bash
# Root prompts (no prefix needed)
/daplug:run-prompt 001 --model codex --worktree

# Subfolder prompts (include folder prefix)
/daplug:run-prompt providers/011 --model codex --worktree
```

## Summary section updates

```markdown
### Summary
- Pending: X prompts (Y in root, Z in subfolders)
- Completed: N prompts
- Folders: root, providers, backend
```

## File locations table updates

```markdown
| Resource | Path |
|----------|------|
| Root Prompts | `/path/to/prompts/` |
| providers/ | `/path/to/prompts/providers/` |
| backend/ | `/path/to/prompts/backend/` |
| Completed | `/path/to/prompts/completed/` |
```
</requirements>

<implementation>
### Step 1: Update step2_gather_prompts

Change the JSON parsing to handle the `folder` field:
```python
# Group prompts by folder
prompts_by_folder = {}
for prompt in prompts_json:
    folder = prompt.get('folder', '')
    if folder not in prompts_by_folder:
        prompts_by_folder[folder] = []
    prompts_by_folder[folder].append(prompt)
```

### Step 2: Update step4_group_and_prioritize

Add folder-aware grouping:
```markdown
# If subfolders exist, group by folder first, then by category within each folder
# If no subfolders, fall back to category-only grouping (current behavior)
```

### Step 3: Update step6_generate_report

Add folder sections to the report template:
```markdown
# For each non-empty folder:
#### {folder_name}/
| # | Prompt | Notes | Command |
...

# Command format depends on folder:
# - Root: /daplug:run-prompt {number} ...
# - Subfolder: /daplug:run-prompt {folder}/{number} ...
```

### Step 4: Update argument-hint

Change from:
```yaml
argument-hint: [--pending|--completed|--all] [--verbose] [--refresh]
```

To:
```yaml
argument-hint: [--pending|--completed|--all] [--folder <name>] [--tree] [--verbose] [--refresh]
```

### Step 5: Add folder filter logic

In step2, if `--folder` is provided:
```bash
# Filter to specific folder
python3 "$PROMPT_MANAGER" list --folder "$FOLDER" --json
```
</implementation>

<verification>
Test with a repo that has subfolders:

1. **No subfolders** - Should work exactly as before (backward compatible)
   ```bash
   /daplug:prompts
   # Should show flat table grouped by category
   ```

2. **With subfolders** - Should show folder grouping
   ```bash
   /daplug:prompts
   # Should show:
   # - Root prompts first
   # - Then each subfolder section
   # - Commands include folder prefix where needed
   ```

3. **Filter by folder**
   ```bash
   /daplug:prompts --folder providers
   # Should only show prompts in providers/
   ```

4. **Tree view**
   ```bash
   /daplug:prompts --tree
   # Should show tree structure like prompt-manager list --tree
   ```

5. **Command format verification**
   - Root prompt command: `/daplug:run-prompt 001 --model codex --worktree`
   - Subfolder prompt command: `/daplug:run-prompt providers/011 --model codex --worktree`
</verification>

<success_criteria>
- [ ] `/prompts` shows folder sections when subfolders exist
- [ ] Commands include folder prefix for subfolder prompts
- [ ] `--folder <name>` filters to specific folder
- [ ] `--tree` shows tree view
- [ ] Summary shows folder breakdown
- [ ] File locations table shows all folders
- [ ] Backward compatible - works unchanged for flat repos
- [ ] Recommendations section handles mixed root/subfolder prompts
</success_criteria>

<notes>
This is a companion update to prompt 001-prompt-subfolder-support which added subfolder support to prompt-manager and run-prompt. The `/prompts` command is the primary way users discover and interact with prompts, so it needs to reflect the new folder organization.

Priority: Medium - the command works without this, but the UX is incomplete without folder awareness.
</notes>

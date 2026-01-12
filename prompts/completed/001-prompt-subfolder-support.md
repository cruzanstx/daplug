<objective>
Add subfolder support to prompt-manager and run-prompt skills.

Currently prompts are flat in `prompts/` with only `completed/` as a special subfolder. This feature adds support for organizing prompts into topic-based subfolders like `prompts/providers/`, `prompts/refactoring/`, etc.

**Real-world use case:** In the cclimits project, we created `prompts/providers/011-015*.md` for future provider integrations. This pattern should be a first-class feature.
</objective>

<context>
Files to modify:
- `skills/prompt-manager/scripts/manager.py` - Core CRUD operations
- `skills/prompt-executor/scripts/executor.py` - Prompt execution
- `skills/create-prompt/README.md` - Update documentation
- `skills/run-prompt/README.md` - Update documentation

Current behavior:
- `prompts/` contains numbered prompts (001-xxx-name.md)
- `prompts/completed/` is the only subfolder (archive)
- Numbers are globally sequential (001, 002, 003...)

Desired behavior:
- Support arbitrary subfolders: `prompts/providers/`, `prompts/backend/`, etc.
- Numbers can be subfolder-scoped OR global (user choice)
- `completed/` remains special (archive destination)
- Backward compatible with flat structure
</context>

<requirements>
## prompt-manager changes

### 1. List command enhancements
```bash
# Current
python3 manager.py list              # Flat list

# New
python3 manager.py list              # Shows all, grouped by folder
python3 manager.py list --folder providers  # Filter to subfolder
python3 manager.py list --tree       # Tree view
```

Output format with subfolders:
```
prompts/
├── 001-initial-setup.md (active)
├── 002-add-feature.md (active)
├── providers/
│   ├── 011-github-copilot.md (active)
│   ├── 012-cursor.md (active)
│   └── 013-replit.md (active)
└── completed/
    └── 003-bug-fix.md
```

### 2. Create command enhancements
```bash
# Current
python3 manager.py create "name"     # Creates in prompts/

# New
python3 manager.py create "name" --folder providers  # Creates in prompts/providers/
python3 manager.py create "name" -f backend          # Short flag
```

### 3. Find/Read command enhancements
```bash
# Support multiple formats
python3 manager.py find 011                    # Searches all folders
python3 manager.py find providers/011          # Explicit folder
python3 manager.py find github-copilot         # Name search across folders
```

### 4. Next-number enhancements
```bash
# Current: global next number
python3 manager.py next-number        # Returns 004 (global)

# New: folder-scoped option
python3 manager.py next-number                    # Global (default)
python3 manager.py next-number --folder providers # Next in providers/ (016)
```

## executor.py changes

### Prompt resolution
```bash
# Support these formats in run-prompt
/run-prompt 011                      # Searches all folders
/run-prompt providers/011            # Explicit path
/run-prompt providers/011-015        # Range within folder
/run-prompt 001,providers/011,020    # Mixed
```

### JSON output enhancement
Add `folder` field to prompt info:
```json
{
  "number": "011",
  "name": "github-copilot-integration",
  "folder": "providers",
  "path": "prompts/providers/011-github-copilot-integration.md"
}
```

## create-prompt skill changes

### Add folder selection question
When creating prompts, optionally ask:
```
Where should this prompt go?
1. Root (prompts/)
2. providers/
3. backend/
4. [Create new subfolder]
```

Or accept `--folder` argument to skip the question.
</requirements>

<implementation>
### Data model changes in manager.py

Update `PromptInfo` dataclass:
```python
@dataclass
class PromptInfo:
    number: str
    name: str
    filename: str
    path: Path
    status: str      # 'active' or 'completed'
    folder: str      # '' for root, 'providers' for subfolder
```

### Folder discovery
```python
def get_prompt_folders(repo_root: Path) -> list[str]:
    """Get all prompt subfolders (excluding completed/)."""
    prompts_dir = get_prompts_dir(repo_root)
    folders = ['']  # Root folder
    for item in prompts_dir.iterdir():
        if item.is_dir() and item.name != 'completed':
            folders.append(item.name)
    return sorted(folders)
```

### Search all folders
```python
def find_prompt(query: str, repo_root: Path) -> Optional[PromptInfo]:
    """Find prompt by number or name, searching all folders."""
    # Check if query includes folder prefix
    if '/' in query:
        folder, num_or_name = query.split('/', 1)
        return find_in_folder(folder, num_or_name, repo_root)

    # Search all folders
    for folder in get_prompt_folders(repo_root):
        result = find_in_folder(folder, query, repo_root)
        if result:
            return result
    return None
```
</implementation>

<verification>
Test scenarios:
```bash
# Create in subfolder
python3 manager.py create "test-prompt" --folder providers
# Should create prompts/providers/016-test-prompt.md

# List with tree view
python3 manager.py list --tree
# Should show folder structure

# Find across folders
python3 manager.py find 011
# Should find prompts/providers/011-*.md

# Run prompt with folder prefix
/run-prompt providers/011 --model codex
# Should execute correctly

# Range within folder
/run-prompt providers/011-013 --parallel
# Should expand to 011, 012, 013 all from providers/
```
</verification>

<success_criteria>
- [ ] `list` shows prompts grouped by folder
- [ ] `create --folder X` creates in subfolder
- [ ] `find` searches all folders by default
- [ ] `next-number --folder X` returns next number for that folder
- [ ] `run-prompt` accepts `folder/number` format
- [ ] Backward compatible - existing flat prompts still work
- [ ] `completed/` remains special (not a selectable target folder)
- [ ] JSON output includes `folder` field
</success_criteria>

<notes>
This feature was inspired by organizing cclimits provider integration prompts:
```
prompts/
├── completed/001-010  # Done work
└── providers/         # Future provider integrations
    ├── 011-github-copilot
    ├── 012-cursor
    ├── 013-replit
    ├── 014-windsurf
    └── 015-amazon-q
```

The pattern is useful for:
- Grouping related prompts (providers, backend, frontend, refactoring)
- Keeping active prompts organized as projects grow
- Allowing parallel work streams with separate numbering
</notes>

<objective>
Update all documentation to reflect the new opencode defaults for local models and the new `--cli` override flag added in prompts 023-024.

Documentation must match runtime behavior so users and the create-prompt skill recommend the correct commands.
</objective>

<context>
**Project**: daplug - Claude Code plugin for multi-model prompt execution

**What changed in prompts 023-024**:
- Local models (`local`, `qwen`, `devstral`) now default to opencode CLI instead of codex
- New `--cli` flag allows overriding the CLI wrapper (e.g., `--cli codex` to use legacy behavior)
- Router prefers opencode for local family, falls back to codex
- OpenCode model IDs: `lmstudio/qwen3-next-80b`, `lmstudio/devstral-small-2-2512`

**Files that need updating** (only docs/config, no Python code):
</context>

<requirements>
Update each file below. For each file, read it first, find the relevant sections, and make targeted edits.

### 1. `CLAUDE.md` - Model Shorthand Reference table (~line 158)

Current:
```
| `qwen`/`local` | codex | qwen via LMStudio |
| `devstral` | codex | devstral via LMStudio |
```

Update to:
```
| `qwen`/`local` | opencode | qwen via LMStudio (opencode default, --cli codex for legacy) |
| `devstral` | opencode | devstral via LMStudio (opencode default, --cli codex for legacy) |
```

### 2. `skills/prompt-executor/SKILL.md` - Model Reference table (~line 203-204)

Current:
```
| local/qwen | codex exec --profile local | Local qwen model |
| devstral | codex exec --profile local-devstral | Local devstral model |
```

Update to:
```
| local/qwen | opencode run --format json -m lmstudio/qwen3-next-80b | Local qwen model (default: opencode) |
| devstral | opencode run --format json -m lmstudio/devstral-small-2-2512 | Local devstral model (default: opencode) |
```

Also add `--cli` to the argument reference section.

### 3. `commands/run-prompt.md` - Arguments table

Add `--cli` to the arguments table:
```
| `--cli` | Override CLI wrapper: codex or opencode |
```

### 4. `commands/create-prompt.md` - Available models section (~line 495)

Update the "Other Models" section:
```
- `local` - Local model via opencode + LMStudio (no quota limits)
- `qwen` - Qwen via opencode + LMStudio (no quota limits)
- `devstral` - Devstral via opencode + LMStudio (no quota limits)
```

### 5. `commands/create-llms-txt.md` - Available models section

Same update as create-prompt.md for local models.

### 6. `commands/prompts.md` - Model options list (~line 55)

Update local model descriptions to mention opencode.

### 7. `README.md` - Local Models section

Add/update a section explaining local models now use opencode by default, with `--cli codex` as fallback.

### 8. `scripts/manage-models.py` - Model management checklist

Update the checklist to include the router changes needed when adding local models.
</requirements>

<implementation>
For each file:
1. Read the file to find exact current text
2. Make targeted edits (do not rewrite entire files)
3. Preserve surrounding content and formatting
4. Only change the sections relevant to local models and --cli flag

**Do NOT modify**:
- Any Python code (executor.py, router.py) - those were handled in 023-024
- Completed prompts in `prompts/completed/`
- Design docs in `docs/`
</implementation>

<verification>
After all edits, verify consistency:

1. Search for any remaining "codex" references next to local/qwen/devstral that should now say "opencode":
   ```bash
   grep -rn "local.*codex\|qwen.*codex\|devstral.*codex" CLAUDE.md README.md commands/ skills/prompt-executor/SKILL.md
   ```
   (Should return zero results in doc sections, may still appear in fallback/legacy descriptions)

2. Search for the new --cli flag in docs:
   ```bash
   grep -rn "\-\-cli" commands/ skills/prompt-executor/SKILL.md README.md
   ```
   (Should appear in run-prompt.md args table, SKILL.md, README)

3. Verify no broken markdown tables:
   ```bash
   # Quick check: pipe counts should be consistent in table rows
   grep "^|" CLAUDE.md | awk -F"|" '{print NF}' | sort -u
   ```

<verification>VERIFICATION_COMPLETE</verification> only when all docs are consistent.
</verification>

<success_criteria>
- All doc files reflect opencode as default for local models
- --cli flag is documented in all relevant command/skill files
- No stale "codex" references for local models in active docs
- Markdown formatting is preserved (tables, code blocks)
- Completed prompts and design docs are NOT modified
</success_criteria>
# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

daplug is a Claude Code plugin that provides AI-assisted development workflows with multi-model prompt execution. It enables running prompts across Claude, OpenAI Codex, Google Gemini, Z.AI, and local models (Qwen, Devstral) with optional git worktree isolation and iterative verification loops.

## Architecture

### Plugin Structure

```
daplug/
├── .claude-plugin/plugin.json    # Plugin metadata (name, version)
├── commands/                     # User-invocable slash commands (*.md)
├── agents/                       # Background agent definitions (*.md)
├── skills/                       # Reusable skill modules
│   ├── <skill-name>/SKILL.md    # Skill definition
│   └── <skill-name>/scripts/    # Python helper scripts
├── hooks/                        # Event hooks (*.json)
└── mcp/                          # MCP server configs
```

### Key Components

**Commands** (`commands/*.md`): Markdown files that define slash commands. Each has YAML frontmatter (name, description, argument-hint) followed by execution instructions.

**Skills** (`skills/*/SKILL.md`): Reusable modules with their own tool permissions. Key skills:
- `prompt-executor`: Core execution engine (`scripts/executor.py`) - handles prompt resolution, worktree creation, CLI launching, and verification loops
- `config-reader`: Reads `<daplug_config>` blocks from CLAUDE.md files (`scripts/config.py`)
- `prompt-manager`: CRUD operations for prompt files (`scripts/manager.py`)
- `prompt-finder`: Locates prompts by number or keyword
- `worktree`: Git worktree management for isolated development

**Agents** (`agents/*.md`): Background agent definitions for specific tasks (infra-troubleshooter, k8s-cicd-troubleshooter, build optimizers, log watcher).

### Configuration System

Settings are stored in `<daplug_config>` XML blocks within CLAUDE.md files:

```markdown
<daplug_config>
preferred_agent: codex
worktree_dir: .worktrees/
llms_txt_dir: /path/to/llms_txt
ai_usage_awareness: enabled
cli_logs_dir: ~/.claude/cli-logs/
</daplug_config>
```

Priority: project `./CLAUDE.md` → user `~/.claude/CLAUDE.md`

### Prompt Execution Flow

1. User runs `/run-prompt 123 --model codex --worktree`
2. `executor.py` resolves prompt from `prompts/` directory
3. If `--worktree`: Creates isolated git worktree at configured location
4. Launches CLI (codex/gemini/zai) with prompt content
5. If `--loop`: Re-runs until completion marker found or max iterations reached
6. Logs output to `~/.claude/cli-logs/`

## Development Commands

### Testing Skills

```bash
# Test prompt-manager
PLUGIN_ROOT=$(pwd)
python3 $PLUGIN_ROOT/skills/prompt-manager/scripts/manager.py info --json
python3 $PLUGIN_ROOT/skills/prompt-manager/scripts/manager.py list

# Test config-reader
python3 $PLUGIN_ROOT/skills/config-reader/scripts/config.py status

# Test executor (info only, no --run)
python3 $PLUGIN_ROOT/skills/prompt-executor/scripts/executor.py 001 --model codex
```

### Running Tests

```bash
# Config reader tests
cd skills/config-reader && python3 -m pytest tests/ -v
```

### Local Development

```bash
# Symlink for local development (from repo root)
ln -s $(pwd) ~/.claude/plugins/daplug

# Or install from marketplace
claude plugin marketplace add cruzanstx/daplug
claude plugin install daplug@cruzanstx
```

## Important Patterns

### Getting Plugin Install Path

Commands that reference internal files must read from Claude's manifest:

```bash
PLUGIN_ROOT=$(jq -r '.plugins."daplug@cruzanstx"[0].installPath' ~/.claude/plugins/installed_plugins.json)
EXECUTOR="$PLUGIN_ROOT/skills/prompt-executor/scripts/executor.py"
```

**Note**: `${CLAUDE_PLUGIN_ROOT}` doesn't work in command markdown files due to [bug #9354](https://github.com/anthropics/claude-code/issues/9354).

### Prompt Input to CLI

For codex-based CLIs, use stdin to avoid shell escaping issues:

```python
# Codex-style: use '-' to read from stdin
process = subprocess.Popen(["codex", "exec", "--full-auto", "-"], stdin=subprocess.PIPE, ...)
process.stdin.write(content)

# Gemini-style: pass as argument
subprocess.Popen(["gemini", "-y", "-p", content], ...)
```

### Verification Loop Protocol

When `--loop` is used, prompts are wrapped with completion markers:

```xml
<verification>VERIFICATION_COMPLETE</verification>  <!-- Success -->
<verification>NEEDS_RETRY: [reason]</verification>  <!-- Continue loop -->
```

Loop state persisted in `~/.claude/loop-state/{prompt-number}.json`

### Prompt File Naming

Pattern: `NNN-descriptive-name.md` (e.g., `042-add-user-auth.md`)
- `NNN` = Zero-padded number (001-999)
- `descriptive-name` = Kebab-case, max 5 words

Location: `{git_root}/prompts/` (active) and `{git_root}/prompts/completed/` (archived)

## Model Shorthand Reference

| Shorthand | CLI | Actual Model |
|-----------|-----|--------------|
| `codex` | codex | gpt-5.3-codex |
| `codex-high` | codex | gpt-5.3-codex (high reasoning) |
| `codex-xhigh` | codex | gpt-5.3-codex (xhigh reasoning) |
| `gpt52` | codex | gpt-5.2 |
| `gpt52-high` | codex | gpt-5.2 (high reasoning) |
| `gpt52-xhigh` | codex | gpt-5.2 (xhigh reasoning) |
| `gemini` | gemini | gemini-3-flash-preview |
| `gemini-high` | gemini | gemini-2.5-pro |
| `gemini-xhigh` | gemini | gemini-3-pro-preview |
| `zai` | codex | GLM-4.7 via Z.AI (may have issues) |
| `opencode` | opencode | GLM-4.7 via OpenCode (recommended; JSON output) |
| `qwen`/`local` | opencode | qwen3-coder-next via LMStudio (opencode default, --cli codex for legacy) |
| `devstral` | opencode | devstral-small-2-2512 via LMStudio (opencode default, --cli codex for legacy) |
| `glm-local` | opencode | glm-4.7-flash via LMStudio (local Z.AI model) |
| `qwen-small` | opencode | qwen3-4b-2507 via LMStudio (small/fast, haiku-tier) |

**OpenCode (opencode) note:** daplug runs OpenCode with `--format json` for clean, parseable logs (no PTY). To avoid interactive permission prompts in headless runs, configure `~/.config/opencode/opencode.json`, e.g.:

```json
{
  "permission": {
    "*": "allow",
    "external_directory": "allow",
    "doom_loop": "allow"
  }
}
```

## Managing Models

When adding, removing, or modifying models, multiple files must be updated. Use the management script or follow the checklist below.

### Using the Management Script

```bash
# List all current models
python3 scripts/manage-models.py list

# Show which files need updating for a new model
python3 scripts/manage-models.py check

# Add a new model (interactive)
python3 scripts/manage-models.py add
```

### Manual Checklist

When adding a new model, update these files in order:

| # | File | Section to Update |
|---|------|-------------------|
| 1 | `skills/prompt-executor/scripts/executor.py` | `models = {` dict (~line 478) |
| 2 | `skills/prompt-executor/scripts/executor.py` | `--model` argparse choices (~line 1300) |
| 3 | `skills/prompt-executor/SKILL.md` | `--model` options list |
| 4 | `skills/prompt-executor/SKILL.md` | Model Reference table |
| 5 | `commands/run-prompt.md` | `--model` argument description |
| 6 | `commands/prompts.md` | preferred_agent options list |
| 7 | `commands/create-prompt.md` | `<available_models>` section |
| 8 | `commands/create-prompt.md` | Recommendation logic table |
| 9 | `commands/create-prompt.md` | Model selection menus (3 instances) |
| 10 | `commands/create-llms-txt.md` | `<available_models>` section |
| 11 | `commands/create-llms-txt.md` | Recommendation logic table |
| 12 | `commands/create-llms-txt.md` | Model selection menu |
| 13 | `README.md` | Model Tiers section |
| 14 | `CLAUDE.md` | Model Shorthand Reference table (above) |

### Model Entry Template

For `executor.py`, use this template:

```python
"model-name": {
    "command": ["codex", "exec", "--full-auto", "-m", "model-id"],
    "display": "model-name (Description)",
    "env": {},
    "stdin_mode": "dash"  # or "arg" for gemini
},
```

### Verification

After adding a model, verify it works:

```bash
# Check model appears in help
python3 skills/prompt-executor/scripts/executor.py --help | grep model-name

# Test command generation
python3 skills/prompt-executor/scripts/executor.py 001 --model model-name
```

## Releasing

The Claude Code plugin system resolves versions from **git tags**, not from `plugin.json` alone. Every version bump must have a corresponding git tag or `claude plugin update` won't see it.

### Release Checklist

1. Bump version in `.claude-plugin/plugin.json`
2. Commit the change
3. Create a matching git tag: `git tag v<version>`
4. Push both: `git push origin main && git push origin v<version>`
5. Create the GitHub release: `gh release create v<version> --title "v<version>" --notes "..."`

### Quick Release

```bash
# After committing the version bump:
VERSION=$(jq -r .version .claude-plugin/plugin.json)
git tag "v$VERSION"
git push origin main "v$VERSION"
gh release create "v$VERSION" --title "v$VERSION" --generate-notes
```

### Common Mistake

If you bump `plugin.json` and push without tagging, `claude plugin update` will report the **old** version as latest. Fix by tagging the commit retroactively:

```bash
git tag v<version> <commit-sha>
git push origin v<version>
```

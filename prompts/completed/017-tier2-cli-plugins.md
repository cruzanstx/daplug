<objective>
Implement detection plugins for Tier 2 CLIs: Goose, Aider, and GitHub Copilot CLI.

These are popular alternatives that expand daplug's reach to more users.
</objective>

<context>
**Depends on**: 
- `014-implement-cli-detection.md` - Plugin framework must exist

This extends the plugin system with additional CLI support.
</context>

<requirements>
**Researched values from 012-research-prerequisites:**

## 1. Goose Plugin (Block)

**Repository**: https://github.com/block/goose

Implement plugin:
- `executable_names`: `["goose"]`
- `config_paths`: `["~/.config/goose/config.yaml"]`
- `config_format`: YAML
- `version_cmd`: `["goose", "--version"]`
- `supported_providers`: `["openai", "anthropic", "google", "openrouter", "ollama"]`
- `headless_cmd`: Limited - Goose is primarily interactive via `goose session`
- **Key config vars**: `GOOSE_PROVIDER`, `GOOSE_MODEL`
- **Extensions**: Configured in `config.yaml` under `extensions` (uses MCP protocol)
- **Note**: Goose focuses on agentic workflows with MCP extensions, not simple prompt execution

## 2. Aider Plugin

**Repository**: https://github.com/paul-gauthier/aider

Implement plugin:
- `executable_names`: `["aider"]`
- `config_paths`: `[".aider.conf.yml", "~/.aider.conf.yml", ".env"]`
- `config_format`: YAML or env
- `version_cmd`: `["aider", "--version"]`
- `supported_providers`: `["openai", "anthropic", "google", "ollama", "openrouter"]`
- `headless_cmd`: `["aider", "--message", "<prompt>", "--yes"]`
- **Model flag**: `--model <model-name>` (e.g., `--model gpt-4o`, `--model claude-3-5-sonnet-20241022`)
- **Local models**: `--model ollama/qwen2.5-coder:32b`
- **Best for**: Batch mode code editing with `--message` and `--yes` flags

## 3. GitHub Copilot CLI Plugin

**Extension**: `gh copilot` (GitHub CLI extension)

Implement plugin:
- `executable_names`: `["gh"]` (check for copilot extension)
- `detection_cmd`: `["gh", "extension", "list"]` → grep for `github/gh-copilot`
- `config_paths`: `["~/.config/github-copilot/"]` (managed by gh)
- `version_cmd`: `["gh", "copilot", "--version"]`
- `auth_check`: `["gh", "auth", "status"]`
- `supported_providers`: `["github"]` (Copilot backend)
- **Available commands**:
  - `gh copilot suggest` - Generate shell commands
  - `gh copilot explain` - Explain commands/code
- **Limitations**: Not a general-purpose prompt executor. Best for generating CLI commands.
- **Install**: `gh extension install github/gh-copilot`

## 4. Additional Tier 2: Cody Plugin

**Repository**: https://github.com/sourcegraph/cody

Implement plugin:
- `executable_names`: `["cody"]`
- `config_paths`: `["~/.sourcegraph/config.json"]`
- `config_format`: JSON
- `version_cmd`: `["cody", "--version"]`
- `supported_providers`: `["sourcegraph"]`
- **Install**: `npm i -g @sourcegraph/cody`

## 5. Additional Tier 2: Mentat Plugin

**Repository**: https://github.com/AbanteAI/mentat

Implement plugin:
- `executable_names`: `["mentat"]`
- `config_paths`: `[".mentat/"]` (project-level config scripts)
- `version_cmd`: `["mentat", "--version"]`
- **Note**: Project-level configuration, less suitable for global detection

## 6. Update Model Routing

Add these CLIs to the routing matrix:

| Model | Goose | Aider | GH Copilot | Cody | Notes |
|-------|-------|-------|------------|------|-------|
| gpt-4o | ✅ | ✅ | ✅ (limited) | ❌ | Copilot only for suggest/explain |
| claude-3.5-sonnet | ✅ | ✅ | ❌ | ✅ | Cody via Sourcegraph |
| gemini-* | ✅ | ✅ | ❌ | ❌ | Via Google provider |
| local/ollama/* | ✅ | ✅ | ❌ | ❌ | Aider best for local |
| local/lmstudio/* | ❌ | ✅ | ❌ | ❌ | OpenAI-compatible endpoint |
</requirements>

<implementation>
Add to existing plugin directory:

```
skills/agent-detector/scripts/plugins/
├── goose.py      # NEW
├── aider.py      # NEW
└── ghcopilot.py  # NEW
```

Each plugin follows the same interface as Tier 1 plugins.
</implementation>

<verification>
```bash
cd skills/agent-detector && python3 -m pytest tests/test_tier2_plugins.py -v
```

Tests:
- [ ] Goose detection (mock installation)
- [ ] Aider detection (mock installation)
- [ ] GH Copilot detection (mock gh extension)
- [ ] Model listing for each
- [ ] Command building for each

Integration:
```bash
python3 detector.py --scan
# Should now show Tier 2 CLIs if installed
```
</verification>

<success_criteria>
- [ ] All 3 Tier 2 plugins implemented
- [ ] Plugins follow same interface as Tier 1
- [ ] `/load-agents` shows Tier 2 CLIs when installed
- [ ] Model routing updated
- [ ] At least 6 new tests (2 per plugin)
</success_criteria>
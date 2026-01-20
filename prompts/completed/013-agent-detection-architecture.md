<research_objective>
Research and design an EXTENSIBLE agent/model detection system for daplug that automatically
discovers which AI coding CLIs the user has installed, what models are available through each,
and provides a seamless experience for routing prompts to the best available runner.

The system must be plugin-like so new CLIs can be added easily as the ecosystem grows.
</research_objective>

<context>
**Depends on**: `012-research-prerequisites.md` - Run that first to build llms_txt knowledge base

**Read first**: Check `./docs/agent-detection-research.md` if it exists (created by 012)

## Current State

daplug currently has 4 CLI "runners" with hardcoded model mappings:
- **Claude Code** - Claude models (uses developer account, not API)
- **Codex CLI** - OpenAI models (gpt-5.2-codex, gpt-5.2, etc.)
- **Gemini CLI** - Google models (gemini-2.5-*, gemini-3-*)
- **OpenCode** - Z.AI GLM-4.7 (and potentially others)

## Expanding Ecosystem

New AI coding CLIs are emerging rapidly. The detection system should support:

**Current Priority (Tier 1 CLIs):**
- Claude Code
- Codex CLI (OpenAI)
- Gemini CLI (Google)
- OpenCode (Z.AI)

**Note on Local Models:**
Local models are served by **model providers** (LMStudio, Ollama) and accessed THROUGH
coding CLIs. Detection should:
1. Detect which local model providers are running
2. Query what models they have loaded
3. Map which CLIs can connect to them (codex, opencode, aider all support local endpoints)

**Local Model Providers to Detect:**

| Provider | Default Endpoint | Health Check | Model List | Notes |
|----------|-----------------|--------------|------------|-------|
| **Ollama** | `http://localhost:11434` | `GET /api/version` | `GET /api/tags` | REST API, returns JSON with models array |
| **LMStudio** | `http://localhost:1234` | `GET /v1/models` | `GET /v1/models` | OpenAI-compatible API |
| **vLLM** | `http://localhost:8000` | `GET /v1/models` | `GET /v1/models` | OpenAI-compatible |
| **llama.cpp** | `http://localhost:8080` | `GET /health` | `GET /v1/models` | Lightweight GGUF server |


**Emerging CLIs to Research:**
- **Goose** - Block's AI coding agent (https://github.com/block/goose)
- **Aider** - AI pair programming (https://github.com/paul-gauthier/aider)
- **Continue** - VS Code/JetBrains AI (https://github.com/continuedev/continue)
- **Cursor** - AI-first editor (has CLI?)
- **Cody** - Sourcegraph's AI (https://github.com/sourcegraph/cody)
- **Amazon Q** - AWS AI assistant
- **GitHub Copilot CLI** - `gh copilot`

**Less Known / Research:**
- **Factory Droid** - Research this
- **Crush** - Research this
- **Mentat** - AI coding agent
- **GPT Engineer** - AI code generation
- **Sweep** - AI junior dev

## Key Insight

Most CLI runners can execute models from OTHER providers:
- **OpenCode**: Can run OpenAI, Anthropic, Google, Z.AI, local models via config
- **Codex**: Can run OpenAI models + potentially others via API keys
- **Aider**: Supports OpenAI, Anthropic, local models
- **Goose**: Likely supports multiple providers

## Design Constraint: Extensibility

The detection system should use a **plugin architecture** where each CLI has:
```python
class CLIPlugin:
    name: str
    detect() -> bool
    get_config_path() -> Path
    parse_config() -> dict
    get_models() -> list[str]
    get_issues() -> list[Issue]
    fix_issue(issue: Issue) -> bool
```

Adding a new CLI should be as simple as adding a new plugin file.
</context>

<research_tasks>
## Phase 1: CLI Discovery Research

For EACH CLI (prioritize by popularity/usefulness):

### Tier 1 (Must Have)
1. **Claude Code** - Config, models, detection
2. **Codex CLI** - Config, models, detection  
3. **Gemini CLI** - Config, models, detection
4. **OpenCode** - Config, models, detection


### Tier 2 (Should Have)
6. **Goose** (Block) - Growing popularity
7. **Aider** - Very popular for pair programming
8. **GitHub Copilot CLI** - `gh copilot` commands

### Tier 3 (Nice to Have / Research)
9. **Continue** - IDE-focused but may have CLI
10. **Cody** - Sourcegraph
11. **Amazon Q** - AWS users
12. **Factory Droid** - Research what this is
13. **Crush** - Research what this is
14. **Mentat** - Research viability

For each CLI, document:
- **Installation detection**: How to check if installed
- **Config location**: Where configs live
- **Config format**: JSON/YAML/TOML/env vars
- **Model listing**: How to get available models
- **Cross-provider support**: Can it run other providers' models?
- **API/Auth requirements**: Keys needed
- **CLI invocation**: How to run prompts through it

## Phase 2: Plugin Architecture Design

Design an extensible plugin system:

```
skills/agent-detector/
├── scripts/
│   ├── detector.py          # Main detection orchestrator
│   ├── plugins/              # CLI coding agents
│   │   ├── __init__.py
│   │   ├── base.py           # CLIPlugin base class
│   │   ├── claude.py         # Claude Code detection
│   │   ├── codex.py          # Codex CLI detection
│   │   ├── gemini.py         # Gemini CLI detection
│   │   ├── opencode.py       # OpenCode detection
│   │   ├── goose.py          # Goose detection
│   │   ├── aider.py          # Aider detection
│   │   └── ghcopilot.py      # GitHub Copilot CLI
│   └── providers/            # Local model providers
│       ├── __init__.py
│       ├── base.py           # ProviderPlugin base class
│       ├── lmstudio.py       # LMStudio detection
│       └── ollama.py         # Ollama detection
```

Each plugin implements:
```python
class CLIPlugin(ABC):
    @property
    @abstractmethod
    def name(self) -> str: ...
    
    @property
    @abstractmethod
    def display_name(self) -> str: ...
    
    @abstractmethod
    def detect_installation(self) -> bool: ...
    
    @abstractmethod
    def get_version(self) -> Optional[str]: ...
    
    @abstractmethod
    def get_config_paths(self) -> list[Path]: ...
    
    @abstractmethod
    def parse_config(self) -> dict: ...
    
    @abstractmethod
    def get_available_models(self) -> list[ModelInfo]: ...
    
    @abstractmethod
    def get_supported_providers(self) -> list[str]: ...
    
    @abstractmethod
    def detect_issues(self) -> list[ConfigIssue]: ...
    
    @abstractmethod
    def apply_fix(self, issue: ConfigIssue) -> bool: ...
    
    @abstractmethod
    def build_command(self, model: str, prompt: str) -> list[str]: ...
```

Provider plugins (for local model servers):
```python
class ProviderPlugin(ABC):
    @property
    @abstractmethod
    def name(self) -> str: ...  # e.g., "lmstudio"

    @property
    @abstractmethod
    def display_name(self) -> str: ...  # e.g., "LMStudio"

    @property
    @abstractmethod
    def default_endpoint(self) -> str: ...  # e.g., "http://localhost:1234"

    @abstractmethod
    def detect_running(self) -> tuple[bool, Optional[str]]:
        """Returns (is_running, endpoint_url)"""

    @abstractmethod
    def get_loaded_models(self) -> list[str]:
        """Query the provider for currently loaded models"""

    @abstractmethod
    def get_compatible_clis(self) -> list[str]:
        """Which CLIs can connect to this provider (e.g., ['codex', 'opencode', 'aider'])"""
```

## Phase 3: Model Routing Matrix

Create comprehensive matrix:

| Model | Preferred CLI | Alt CLI 1 | Alt CLI 2 | Notes |
|-------|--------------|-----------|-----------|-------|
| claude-* | claude-code | aider | opencode | Developer account preferred |
| gpt-5.2-* | codex | opencode | aider | Native OpenAI support |
| gemini-* | gemini | opencode | aider | Native Google support |
| glm-4.7 | opencode | codex(zai) | - | Z.AI model |
| local:qwen-* | codex | opencode | aider | Via LMStudio/Ollama |
| local:devstral | codex | opencode | aider | Via LMStudio/Ollama |
| local:* | codex | opencode | aider | Any local GGUF model |

## Phase 4: `/load-agents` Command Design

```
$ /load-agents

🔍 Scanning for AI coding agents...

✅ Found 5 installed CLIs:

┌─────────────┬─────────┬────────────────────────┬────────────┐
│ CLI         │ Version │ Models                 │ Status     │
├─────────────┼─────────┼────────────────────────┼────────────┤
│ claude-code │ 1.0.16  │ claude-4-*, opus-4.5   │ ✅ Ready   │
│ codex       │ 1.2.3   │ gpt-5.2-*, codex       │ ⚠️ Issue   │
│ gemini      │ 0.4.1   │ gemini-2.5-*, 3-*      │ ✅ Ready   │
│ opencode    │ 0.1.0   │ glm-4.7, gpt-*, claude │ ✅ Ready   │
│ goose       │ 0.3.2   │ gpt-4o, claude-3.5     │ ✅ Ready   │
└─────────────┴─────────┴────────────────────────┴────────────┘

🖥️ Local Model Providers:

┌──────────┬─────────────────────────┬──────────────────────────┐
│ Provider │ Endpoint                │ Loaded Models            │
├──────────┼─────────────────────────┼──────────────────────────┤
│ LMStudio │ http://localhost:1234   │ qwen-2.5-coder, devstral │
│ Ollama   │ http://localhost:11434  │ (not running)            │
└──────────┴─────────────────────────┴──────────────────────────┘

  💡 Local models can be used via: codex, opencode, aider

⚠️ Issues detected:
  • codex: Sandbox permissions need adjustment for full-auto mode
    Run `/load-agents --fix` to apply recommended fixes

❌ Not found (install to enable):
  • aider - pip install aider-chat
  • gh copilot - gh extension install github/gh-copilot

💾 Cache saved to ~/.claude/daplug-agents.json

Would you like to:
1. Fix detected issues
2. Add models to daplug config
3. Set preferred CLI per model
4. Done
```

## Phase 5: Cache Schema (Extensible)

**Researched Config Paths (from 012-research):**

| CLI | Config Path | Format | Version Command |
|-----|-------------|--------|-----------------|
| Claude Code | `~/.claude/settings.json` | JSON | `claude --version` |
| Codex CLI | `~/.codex/config.json` | JSON | `codex --version` |
| Gemini CLI | `~/.config/gemini/config.json` | JSON | `gemini --version` |
| OpenCode | `~/.config/opencode/opencode.json` | JSON | `opencode --version` |
| Goose | `~/.config/goose/config.yaml` | YAML | `goose --version` |
| Aider | `.aider.conf.yml` or `~/.aider.conf.yml` | YAML | `aider --version` |
| Cody | `~/.sourcegraph/config.json` | JSON | `cody --version` |

```json
{
  "schema_version": "1.0",
  "last_scanned": "2026-01-19T16:00:00Z",
  "scan_duration_ms": 1234,
  "clis": {
    "claude-code": {
      "installed": true,
      "version": "1.0.16",
      "executable": "/usr/local/bin/claude",
      "config_path": "~/.claude/settings.json",
      "models": [
        {"id": "claude-opus-4-5", "display": "Claude Opus 4.5", "provider": "anthropic"}
      ],
      "supported_providers": ["anthropic"],
      "issues": []
    },
    "codex": {
      "installed": true,
      "version": "1.2.3",
      "executable": "/usr/local/bin/codex",
      "config_path": "~/.codex/config.json",
      "models": [...],
      "supported_providers": ["openai", "anthropic", "local"],
      "issues": [
        {"type": "sandbox_permissions", "severity": "warning", "fix_available": true}
      ]
    },
    "gemini": {
      "installed": true,
      "version": "0.4.1",
      "executable": "/usr/local/bin/gemini",
      "config_path": "~/.config/gemini/config.json",
      "models": [...]
    },
    "opencode": {
      "installed": true,
      "version": "0.1.0",
      "executable": "/usr/local/bin/opencode",
      "config_path": "~/.config/opencode/opencode.json",
      "models": [...]
    },
    "goose": {
      "installed": true,
      "version": "0.3.2",
      "executable": "/usr/local/bin/goose",
      "config_path": "~/.config/goose/config.yaml",
      "models": [...],
      "supported_providers": ["openai", "anthropic", "google", "local"],
      "issues": []
    },
    "aider": {
      "installed": true,
      "version": "0.50.0",
      "executable": "/usr/local/bin/aider",
      "config_path": "~/.aider.conf.yml",
      "models": [...],
      "supported_providers": ["openai", "anthropic", "google", "local"],
      "issues": []
    }
  },
  "providers": {
    "lmstudio": {
      "running": true,
      "endpoint": "http://localhost:1234",
      "loaded_models": ["qwen-2.5-coder-32b", "devstral-small-2505"],
      "compatible_clis": ["codex", "opencode", "aider"]
    },
    "ollama": {
      "running": false,
      "endpoint": "http://localhost:11434",
      "loaded_models": [],
      "compatible_clis": ["codex", "opencode", "aider"]
    }
  },
  "routing": {
    "claude-opus-4-5": {"preferred": "claude-code", "fallbacks": ["opencode", "aider"]},
    "gpt-5.2-codex": {"preferred": "codex", "fallbacks": ["opencode"]},
    "local:qwen-2.5-coder": {"preferred": "codex", "fallbacks": ["opencode"], "provider": "lmstudio"},
    // ...
  },
  "user_preferences": {
    "default_cli": "codex",
    "model_overrides": {}
  }
}
```
</research_tasks>

<deliverables>
## Output

Create `./docs/agent-detection-design.md` with:

1. **Executive Summary** - Vision for extensible agent detection
2. **CLI Research Matrix** - All researched CLIs with details
3. **Plugin Architecture** - Base class, interface, file structure
4. **Model Routing Table** - Comprehensive routing with fallbacks
5. **Detection Algorithm** - Flowchart for scanning
6. **Cache Schema** - Full JSON schema (versioned, extensible)
7. **`/load-agents` UX** - Full command design with examples
8. **Config Templates** - Working configs for each Tier 1 CLI
9. **Implementation Phases**:
   - Phase 1: Core detection + Tier 1 CLIs
   - Phase 2: `/load-agents` command
   - Phase 3: Config fixing
   - Phase 4: Tier 2 CLIs
   - Phase 5: Community plugins
10. **Open Questions** - Unknowns about newer CLIs
</deliverables>

<verification>
Before completing, verify:
- [ ] All Tier 1 CLIs fully researched (claude, codex, gemini, opencode)
- [ ] At least 3 Tier 2 CLIs researched (goose, aider, gh copilot)
- [ ] Plugin architecture is concrete and extensible
- [ ] `/load-agents` UX mockup is complete
- [ ] Cache schema handles all known CLIs
- [ ] At least one config template per Tier 1 CLI
</verification>

<success_criteria>
- Research document at `./docs/agent-detection-design.md`
- Plugin architecture allows adding new CLI in <50 lines
- Detection covers at least 8 CLIs
- Implementation phases are actionable
- Ready to start coding Phase 1
</success_criteria>

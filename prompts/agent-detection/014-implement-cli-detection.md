<objective>
Implement the extensible CLI detection plugin system from the architecture design.

Create the core detection framework with plugins for Tier 1 CLIs (claude, codex, gemini, opencode).
</objective>

<context>
**Depends on**:
- `012-research-prerequisites.md` - Must have llms_txt docs first
- `013-agent-detection-architecture.md` - Architecture design

**Read first**:
- `./docs/agent-detection-research.md` (from 012)
- `./docs/agent-detection-design.md` (from 013)

This implements Phase 1 of agent detection - the plugin framework and core CLI plugins.
</context>

<requirements>
## 1. Plugin Base Class

Create `skills/agent-detector/scripts/plugins/base.py`:

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

@dataclass
class ModelInfo:
    id: str
    display_name: str
    provider: str
    capabilities: list[str] = None  # e.g., ["code", "chat", "vision"]

@dataclass
class ConfigIssue:
    type: str  # e.g., "sandbox_permissions", "missing_api_key"
    severity: str  # "error", "warning", "info"
    message: str
    fix_available: bool
    fix_description: Optional[str] = None

class CLIPlugin(ABC):
    """Base class for CLI detection plugins."""
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Internal name (e.g., 'codex')"""
    
    @property
    @abstractmethod
    def display_name(self) -> str:
        """Human-readable name (e.g., 'OpenAI Codex CLI')"""
    
    @property
    @abstractmethod
    def executable_names(self) -> list[str]:
        """Possible executable names to search for"""
    
    @abstractmethod
    def detect_installation(self) -> tuple[bool, Optional[str]]:
        """Returns (is_installed, executable_path)"""
    
    @abstractmethod
    def get_version(self) -> Optional[str]:
        """Get installed version"""
    
    @abstractmethod
    def get_config_paths(self) -> list[Path]:
        """Return possible config file locations"""
    
    @abstractmethod
    def parse_config(self, config_path: Path) -> dict:
        """Parse config file and return normalized dict"""
    
    @abstractmethod
    def get_available_models(self) -> list[ModelInfo]:
        """Return models available through this CLI"""
    
    @abstractmethod
    def get_supported_providers(self) -> list[str]:
        """Return providers this CLI can connect to"""
    
    @abstractmethod
    def detect_issues(self) -> list[ConfigIssue]:
        """Detect configuration issues"""
    
    @abstractmethod
    def apply_fix(self, issue: ConfigIssue) -> bool:
        """Attempt to fix an issue. Returns success."""
    
    @abstractmethod
    def build_command(self, model: str, prompt_file: Path, cwd: Path) -> list[str]:
        """Build CLI command to run a prompt"""
```

## 2. Core Plugins (Tier 1)

**Researched values from 012-research-prerequisites:**

Implement plugins for:
- `plugins/claude.py`:
  - `executable_names`: `["claude"]`
  - `config_paths`: `["~/.claude/settings.json"]`
  - `version_cmd`: `["claude", "--version"]`
  - `supported_providers`: `["anthropic"]`
  - `headless_cmd`: Requires Task agent (interactive CLI)
- `plugins/codex.py`:
  - `executable_names`: `["codex"]`
  - `config_paths`: `["~/.codex/config.json"]`
  - `version_cmd`: `["codex", "--version"]`
  - `supported_providers`: `["openai", "anthropic", "local"]`
  - `headless_cmd`: `["codex", "exec", "--full-auto", "-"]` (reads from stdin)
- `plugins/gemini.py`:
  - `executable_names`: `["gemini"]`
  - `config_paths`: `["~/.config/gemini/config.json"]`
  - `version_cmd`: `["gemini", "--version"]`
  - `supported_providers`: `["google"]`
  - `headless_cmd`: `["gemini", "-y", "-p", "<prompt>"]`
- `plugins/opencode.py`:
  - `executable_names`: `["opencode"]`
  - `config_paths`: `["~/.config/opencode/opencode.json"]`
  - `version_cmd`: `["opencode", "--version"]`
  - `supported_providers`: `["openai", "anthropic", "google", "zai", "local"]`
  - `headless_cmd`: `["opencode", "--format", "json"]`


## 3. Plugin Registry

Create `plugins/__init__.py` that auto-discovers plugins:

```python
def discover_plugins() -> list[CLIPlugin]:
    """Auto-discover all CLI plugins in this directory."""

def get_plugin(name: str) -> Optional[CLIPlugin]:
    """Get a specific plugin by name."""
```

## 4. Detection Orchestrator

Create `scripts/detector.py`:

```python
def scan_all_clis(force_refresh: bool = False) -> AgentCache:
    """Scan all registered CLI plugins and return results."""

def load_cache() -> Optional[AgentCache]:
    """Load cached detection results."""

def save_cache(cache: AgentCache) -> None:
    """Save detection results to cache file."""

def get_preferred_cli(model: str) -> Optional[str]:
    """Get the best CLI to run a given model."""
```

## 5. CLI Interface

```bash
# Scan and output JSON
python3 detector.py --scan

# Scan with verbose output  
python3 detector.py --scan --verbose

# Check specific CLI
python3 detector.py --check codex

# List all plugins
python3 detector.py --list-plugins
```
</requirements>

<implementation>
File structure:
```
skills/agent-detector/
├── SKILL.md
├── scripts/
│   ├── detector.py           # Main entry point
│   ├── cache.py              # Cache management
│   ├── plugins/              # CLI coding agents
│   │   ├── __init__.py       # Plugin discovery
│   │   ├── base.py           # Base classes (CLIPlugin)
│   │   ├── claude.py         # Claude Code plugin
│   │   ├── codex.py          # Codex CLI plugin
│   │   ├── gemini.py         # Gemini CLI plugin
│   │   └── opencode.py       # OpenCode plugin
│   └── providers/            # Local model providers
│       ├── __init__.py       # Provider discovery
│       ├── base.py           # Base class (ProviderPlugin)
│       ├── lmstudio.py       # LMStudio detection
│       └── ollama.py         # Ollama detection
└── tests/
    ├── test_plugins.py
    ├── test_providers.py
    ├── test_detector.py
    └── test_cache.py
```
</implementation>

<verification>
```bash
cd skills/agent-detector && python3 -m pytest tests/ -v
```

Test coverage:
- [ ] Plugin base class interface
- [ ] Each Tier 1 plugin detection (with mocked filesystem)
- [ ] Plugin auto-discovery
- [ ] Cache save/load
- [ ] CLI argument parsing

Manual test:
```bash
python3 skills/agent-detector/scripts/detector.py --scan --verbose
```
</verification>

<success_criteria>
- [ ] Base plugin class is complete and documented
- [ ] All 4 Tier 1 plugins implemented
- [ ] Plugin auto-discovery works
- [ ] `--scan` outputs valid JSON matching cache schema
- [ ] At least 10 unit tests passing
- [ ] Adding a new plugin requires only creating one file
</success_criteria>

<objective>
Create "known good" config templates for each supported CLI and implement auto-fixing
for common configuration issues.
</objective>

<context>
**Depends on**: 
- `013-agent-detection-architecture.md` - Design
- `014-implement-cli-detection.md` - Detection plugins

Each CLI has different config requirements. This prompt creates:
1. Template configs that "just work" with daplug
2. Issue detection for each CLI
3. Auto-fix logic with backups
</context>

<requirements>
## 1. Config Templates

**Researched values from 012-research-prerequisites:**

Create `skills/agent-detector/templates/` with working configs:

### codex.json (`~/.codex/config.json`)
```json
{
  "model": "gpt-5.2-codex",
  "approval_mode": "full-auto",
  "full_auto": true,
  "notify": {
    "command": "",
    "on_complete": false
  },
  "shell_environment_variables": {},
  "providers": {
    "openai": {
      "name": "OpenAI"
    }
  }
}
```

**Note**: Codex CLI uses `--full-auto` flag for headless operation. Config sets defaults.

### opencode.json (`~/.config/opencode/opencode.json`)
```json
{
  "permission": {
    "*": "allow",
    "external_directory": "allow",
    "doom_loop": "allow"
  },
  "provider": "zai",
  "model": "glm-4.7",
  "mcpServers": {}
}
```

**Note**: OpenCode supports multiple providers (openai, anthropic, google, zai, ollama).
Use `--format json` for clean log output in headless mode.

### gemini config (`~/.config/gemini/config.json`)
```json
{
  "theme": "dark",
  "yolo": false,
  "sandbox": true,
  "check_updates": true
}
```

**Note**: Gemini CLI uses `-y` flag for auto-approve, `-m` for model selection.
Auth via `GOOGLE_API_KEY` or `GEMINI_API_KEY` env vars, or `gcloud auth`.

### aider.conf.yml (`~/.aider.conf.yml` or `.aider.conf.yml`)
```yaml
# Aider configuration - supports many providers
model: gpt-4o
edit-format: whole
auto-commits: false
yes: true                    # Auto-confirm prompts (batch mode)
dark-mode: true
# For local models via Ollama:
# model: ollama/qwen2.5-coder:32b
# For Anthropic:
# model: claude-3-5-sonnet-20241022
```

**Invocation**: `aider --message "prompt text" --yes` for batch execution.

### goose.yaml (`~/.config/goose/config.yaml`)
```yaml
GOOSE_PROVIDER: openai
GOOSE_MODEL: gpt-4o
extensions:
  developer:
    enabled: true
  computercontroller:
    enabled: false
# For Anthropic:
# GOOSE_PROVIDER: anthropic
# GOOSE_MODEL: claude-3-5-sonnet-20241022
# For local Ollama:
# GOOSE_PROVIDER: ollama
# GOOSE_MODEL: qwen2.5-coder:32b
```

**Note**: Goose uses MCP extensions. Run `goose configure` to set up interactively.

## 2. Issue Detection

Each plugin should detect these issue types:

| Issue Type | Description | Severity |
|------------|-------------|----------|
| `missing_config` | No config file found | error |
| `invalid_json` | Config file has syntax errors | error |
| `missing_api_key` | Required API key not set | error |
| `sandbox_permissions` | Permissions too restrictive | warning |
| `outdated_config` | Config schema outdated | warning |
| `missing_model` | Default model not available | warning |

## 3. Auto-Fix Logic

For each fixable issue, implement:

```python
def apply_fix(self, issue: ConfigIssue) -> bool:
    """
    1. Create backup of existing config
    2. Apply minimal fix (dont overwrite entire config)
    3. Validate fix worked
    4. Return success/failure
    """
```

### Backup Strategy
- Backup to `{config_path}.bak.{timestamp}`
- Keep last 3 backups per config
- Never overwrite existing backups

### Fix Strategy
- Merge template values into existing config
- Preserve user customizations
- Only change what is necessary

## 4. Fix Templates

Create fix snippets for common issues:

```python
FIX_TEMPLATES = {
    "codex": {
        "sandbox_permissions": {
            "permissions": {"*": "allow"}
        }
    },
    "opencode": {
        "sandbox_permissions": {
            "permission": {"*": "allow", "external_directory": "allow"}
        }
    }
}
```
</requirements>

<implementation>
File structure:
```
skills/agent-detector/
├── templates/
│   ├── codex.json
│   ├── opencode.json
│   ├── gemini.yaml (or .json)
│   └── README.md (explains each template)
├── scripts/
│   ├── fixer.py           # Fix application logic
│   └── plugins/
│       └── (each plugin implements detect_issues + apply_fix)
```

## fixer.py

```python
def backup_config(path: Path) -> Path:
    """Create timestamped backup, return backup path."""

def apply_fix_safely(plugin: CLIPlugin, issue: ConfigIssue) -> FixResult:
    """Apply fix with backup and rollback on failure."""

def fix_all_issues(cache: AgentCache, interactive: bool = True) -> list[FixResult]:
    """Fix all detected issues, optionally with user confirmation."""
```
</implementation>

<verification>
```bash
cd skills/agent-detector && python3 -m pytest tests/test_fixer.py -v
```

Test scenarios:
- [ ] Backup creation and rotation (keep 3)
- [ ] Fix merges correctly (doesnt clobber user settings)
- [ ] Rollback on failure
- [ ] Each template is valid JSON/YAML
- [ ] Fix actually resolves the detected issue

Manual test:
```bash
# Create intentionally broken config
echo "{}" > /tmp/test-codex-config.json

# Run fixer
python3 skills/agent-detector/scripts/fixer.py --config /tmp/test-codex-config.json --cli codex

# Verify fix applied
cat /tmp/test-codex-config.json
```
</verification>

<success_criteria>
- [ ] Template configs exist for all Tier 1 CLIs
- [ ] Each template is tested and works with daplug
- [ ] Backup system preserves last 3 versions
- [ ] Fixes merge cleanly without data loss
- [ ] At least 8 unit tests for fixer logic
- [ ] `/load-agents --fix` successfully fixes test issues
</success_criteria>
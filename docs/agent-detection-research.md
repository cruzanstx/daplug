# Agent Detection Research Summary

This document summarizes the research on various AI coding CLIs and local model providers for the `daplug` agent-detection system.

## Tier 1 CLIs (Current Focus)

| CLI | Executable | Config Path | Format | Version Command |
|-----|------------|-------------|--------|-----------------|
| Claude Code | `claude` | `~/.claude/settings.json` | JSON | `claude --version` |
| Codex CLI | `codex` | `~/.codex/config.json` | JSON | `codex --version` |
| Gemini CLI | `gemini` | `~/.config/gemini/config.json` | JSON | `gemini --version` |
| OpenCode | `opencode` | `~/.config/opencode/opencode.json` | JSON | `opencode --version` |

## Tier 2 CLIs (Popular Alternatives)

| CLI | Executable | Config Path | Format | Notes |
|-----|------------|-------------|--------|-------|
| Goose | `goose` | `~/.config/goose/config.yaml` | YAML | Block's agent, uses MCP. |
| Aider | `aider` | `.aider.conf.yml`, `.env` | YAML/Env | Supports `aider --message "..." --yes`. |
| GH Copilot | `copilot` | `~/.config/github-copilot/` | JSON/Managed | `npm install -g @github/copilot`. |
| Mentat | `mentat` | `.mentat/` | Scripts | Project-level config scripts. |
| Cody | `cody` | `~/.sourcegraph/config.json` | JSON | `npm i -g @sourcegraph/cody`. |

## Local Model Providers

| Provider | Endpoint | Health Check | Model List |
|----------|----------|--------------|------------|
| Ollama | `http://localhost:11434` | `/api/version` | `/api/tags` |
| LMStudio | `http://localhost:1234` | `/v1/models` | `/v1/models` (OpenAI compatible) |

## Key Research Findings

### 1. Claude Code
- **Detection**: Check for `claude` in path.
- **Config**: Settings are in `~/.claude/settings.json`.
- **Headless**: Primarily interactive; requires specific handling for prompt injection.

### 2. Codex CLI
- **Detection**: Check for `codex` in path.
- **Config**: `~/.codex/config.json` (also supports `.toml` in some versions).
- **Headless**: `codex exec --full-auto -` (reads from stdin).

### 3. Gemini CLI
- **Detection**: Check for `gemini` in path.
- **Config**: `~/.config/gemini/config.json`.
- **Headless**: `gemini -y -p "prompt"`.

### 4. OpenCode
- **Detection**: Check for `opencode` in path.
- **Config**: `~/.config/opencode/opencode.json`.
- **Headless**: `opencode --format json`.

### 5. Aider
- **Config**: Can be in current repo `.aider.conf.yml` or global `~/.aider.conf.yml`.
- **Model flags**: `--model <model-name>`.
- **Execution**: Best for batch mode using `--message` and `--yes`.

### 6. Goose
- **Config**: `~/.config/goose/config.yaml`.
- **Extensions**: Configured in `config.yaml` under `extensions`.

## Implementation Details for Detector

- **Executable Check**: Use `shutil.which(name)`.
- **Config Parsing**: 
    - JSON: `json.load()`
    - YAML: `yaml.safe_load()` (requires `PyYAML`)
    - Env: `dotenv` or manual parsing of `.env`.
- **API Connectivity**: Use `requests` or `httpx` with short timeouts (e.g., 200ms) for local provider detection.

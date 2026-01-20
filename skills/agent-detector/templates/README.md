# daplug agent-detector templates

These are **known-good starter configs** for popular AI coding CLIs so daplug can run them non-interactively.

Notes:
- **Do not put secrets** in these files. Use env vars or the CLI's login flow.
- The fixer (`skills/agent-detector/scripts/fixer.py`) merges these templates as *defaults* and preserves user overrides.

## Tier 1 CLIs

### Claude Code (`~/.claude/settings.json`)
- Template: `claude.json`
- Required env: `ANTHROPIC_API_KEY`

### Codex CLI (`~/.codex/config.json`)
- Template: `codex.json`
- Required env: `OPENAI_API_KEY` (or `~/.codex/auth.json` from interactive login)
- Codex headless mode uses `--full-auto`.

### Gemini CLI (`~/.config/gemini/config.json`)
- Template: `gemini.json`
- Required env: `GEMINI_API_KEY` or `GOOGLE_API_KEY` (or `gcloud auth`)
- Gemini auto-approve uses `-y`, model selection uses `-m`.

### OpenCode (`~/.config/opencode/opencode.json`)
- Template: `opencode.json`
- Provider `zai` expects `ZAI_KEY`.
- For headless mode, daplug uses `--format json`.

## Other CLIs (Tier 2)

### Aider (`~/.aider.conf.yml` or `.aider.conf.yml`)
- Template: `aider.conf.yml`
- Common invocation: `aider --message \"...\" --yes`

### Goose (`~/.config/goose/config.yaml`)
- Template: `goose.yaml`
- Goose uses MCP extensions; use `goose configure` for interactive setup.

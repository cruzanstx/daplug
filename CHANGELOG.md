# Changelog

All notable changes to daplug are documented here.

## [0.22.0] - 2026-01-31

### Added
- **Default Run Options** (`default_run_prompt_options`): User-configurable default flags for prompt execution
  - Set your preferred flags once: `--model codex-xhigh --worktree --loop`
  - Shows "Run with your defaults" as first option in `/create-prompt` menu
  - Prompts to set defaults on first run if not configured
  - Stored in `<daplug_config>` block in CLAUDE.md
  - Project-level config overrides user-level defaults

## [0.21.1] - 2026-01-28

### Added
- **Pipeline Deploy Monitor Agent** (`pipeline-deploy-monitor`): Automates CI/CD deployment verification workflow
  - Monitors pipeline status after git push (glab ci status)
  - Verifies staging pod health, migrations, and logs
  - Runs Playwright UI checks on staging environment
  - Triggers and verifies production deployment
  - Proactively offers workflow after pushes to origin

## [0.21.0] - 2026-01-28

### Added
- **CLI Detection System** (`cli-detector`): Extensible plugin architecture for detecting installed AI coding CLIs
  - `/load-agents` command to scan system and configure available agents
  - Auto-detection for Claude Code, Codex CLI, Gemini CLI, OpenCode (Tier 1)
  - Tier 2 plugins: Goose, Aider, GitHub Copilot CLI
  - Local model provider detection: Ollama, LMStudio, vLLM
- **Config Fixer**: Auto-fix misconfigured CLI settings with `--dry-run` support
  - Known-good config templates for each supported CLI
  - Validates API keys, endpoints, and model configurations
- **Model Routing**: Intelligent model selection based on detected capabilities
  - Cache integration for faster subsequent lookups
  - Prefers larger instruct models over embeddings
- **Multi-model Test Suite**: Comprehensive test coverage for model routing

### Fixed
- Gemini OAuth credentials detection
- Worktree path mismatch in loop state

### Changed
- Renamed `agent-detector` → `cli-detector` for clarity
- `/uvc` command now adds `[skip ci]` to documentation commits

## [0.20.2] - 2026-01-19

### Fixed
- **CLI log path mismatch** (GitHub Issue #6): Displayed log paths now match actual files created
  - Single `execution_timestamp` generated once and passed through entire execution chain
  - Loop state stores timestamp for resume consistency
  - Both foreground/background loop modes show correct `loop_log` path
  - Claude subagent mode now creates logs in `~/.claude/cli-logs/` (was `/tmp/`)

### Added
- `--execution-timestamp` internal CLI argument for timestamp consistency across loop iterations
- Loop log metadata header (prompt, model, timestamp, max iterations, CWD, worktree, branch)
- 6 new unit tests for log path consistency across all execution modes

### Changed
- `run_verification_loop()` and `run_verification_loop_background()` now accept `execution_timestamp` param
- Loop state schema extended with `execution_timestamp` field for resume support

## [0.20.1] - 2026-01-19

### Fixed
- **OpenCode headless execution** (GitHub Issue #5): Changed from PTY wrapper to `--format json` for clean, parseable output
- Removed `needs_pty` flag from opencode model - JSON format doesn't require pseudo-terminal

### Changed
- OpenCode command now uses `opencode run --format json -m zai/glm-4.7`
- Documentation updated with OpenCode permission configuration (`~/.config/opencode/opencode.json`)
- Updated tests to verify JSON output behavior

## [0.20.0] - 2026-01-18

### Added
- **OpenCode CLI support**: New `opencode` model for Z.AI GLM-4.7 via OpenCode CLI (recommended over codex `zai` profile)
- PTY wrapper support for CLIs that require pseudo-terminals (e.g., OpenCode)
- `needs_pty` flag in model configuration for automatic PTY wrapping
- 7 new unit tests for model configuration and PTY command wrapping

### Fixed
- Z.AI GLM-4.7 compatibility issues (GitHub Issue #4) - OpenCode handles GLM-4.7 message format correctly

### Changed
- Model reference tables updated with opencode as recommended Z.AI option
- `zai` codex profile retained but marked as potentially problematic

## [0.19.0] - 2026-01-18

### Added
- `--from-existing` flag for `/sprint` command - analyze existing prompts instead of generating from a spec
- Prompt filtering options: `--prompts 001-005,010`, `--folder providers/`, `--exclude 003,007`
- Dependency detection from prompt content (scans for `depends on`, `requires`, `@file` references)
- `run-sprint.sh` script generation for batch execution
- New functions: `parse_prompt_range()`, `discover_existing_prompts()`, `analyze_prompt_content()`
- 5 new unit tests for --from-existing functionality

### Changed
- `build_dependency_graph()` now accepts explicit prompt-id dependencies via `prompt_dependencies` key
- `assign_models()` uses task_type and referenced_files from prompt analysis for better model routing

## [0.18.0] - 2026-01-17

### Added
- `/sprint` command for automated sprint planning from technical specifications
- 5-phase workflow: spec analysis → prompt generation → dependency graph → model assignment → execution plan
- State management via `.sprint-state.json` for pause/resume/status tracking
- Sub-commands: `status`, `add`, `remove`, `replan`, `pause`, `resume`, `cancel`, `history`
- New `skills/sprint/` skill with `sprint.py` implementation

## [0.15.0] - 2026-01-11

### Added
- Subfolder support for prompts (e.g., `prompts/providers/`, `prompts/backend/`)
- `--folder/-f` flag for create, `--tree` for list, `--folder` for next-number
- Folder-aware resolution: `find 011` searches all folders, `find providers/011` targets specific
- Range expansion with folder prefix: `providers/011-013`

### Changed
- JSON output now includes `folder`, `path`, `status` fields
- Branch naming includes folder path to avoid collisions

## [0.14.1] - 2026-01-10

### Fixed
- Corrected marketplace name in `/check-updates` command (`cruzanstx` not `daplug`)

## [0.14.0] - 2026-01-10

### Added
- GPT-5.2 model support: `gpt52`, `gpt52-high`, `gpt52-xhigh`
- Model management utility: `scripts/manage-models.py`
- "Managing Models" section in CLAUDE.md with checklist and templates

## [0.13.0] - 2026-01-05

### Added
- New config format: `<daplug_config>` XML blocks in CLAUDE.md files
- `/daplug:migrate-config` command for legacy settings migration
- `/daplug:check-config` command for config verification
- `config-reader` skill with Python-based parsing

### Changed
- Config lookup order: project `./CLAUDE.md` → user `~/.claude/CLAUDE.md`

## [0.12.9] - 2026-01-04

### Changed
- `/create-llms-txt` now creates prompts in `$LLMS_TXT_DIR/prompts/` instead of `./prompts/`
- Added auto-discovery of `llms_txt_dir` from `~/.claude/CLAUDE.md`
- Cross-repo execution via `--prompt-file` flag

## [0.12.8] - 2026-01-03

### Added
- `prompt-manager` skill: Python-based CRUD for prompts
- Centralized git root detection for all prompt operations

### Fixed
- Zsh parsing issues with command substitution

## [0.12.7] - 2026-01-03

### Fixed
- Zsh compatibility: parse error when `$()` passed through eval

## [0.12.5] - 2026-01-03

### Changed
- Prompts always saved to `{git_root}/prompts/` instead of relative `./prompts/`
- `/run-prompt` now reports errors clearly instead of manual CLI fallback

## [0.12.4] - 2026-01-01

### Changed
- Monitor spawning mandatory in Step 2 of `/run-prompt`
- Auto-verify monitor permissions before spawning agents

## [0.12.2] - 2025-12-31

### Added
- `readonly-log-watcher` agent for lightweight monitoring
- Refactored `/create-llms-txt` to generate prompts for `/run-prompt`

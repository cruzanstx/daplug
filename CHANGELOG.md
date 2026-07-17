# Changelog

All notable changes to daplug are documented here.

## [0.35.1] - 2026-07-17

### Fixed
- **Cloud OpenCode models now run with `--pure --agent build`.** In headless one-shot runs the oh-my-opencode harness orchestrator delegates work to background subagents that die when the `opencode run` process exits, returning rc=0 with no changes (A/B tested: `--pure` completed a multi-file task in 143s vs 415s and zero output with the harness loaded). Local LMStudio models already used `--pure`; this extends it to all opencode-routed cloud models (`glm5`, `glm52`, `kimi`, `synthetic`, `syn-*`, `opencode`) and the `--cli opencode` override path.

## [0.35.0] - 2026-07-12

### Added
- **`fable` model shorthand** — Claude Fable 5 (Anthropic's Mythos-class tier above Opus) via headless Claude Code CLI (`--model fable`). Mirrors the `cc-opus`/`cc-sonnet` shape and inherits the sandbox permission escalation from 0.34.1, so `--worktree --sandbox --loop` runs work out of the box.

## [0.34.1] - 2026-07-12

### Fixed
- **Sandboxed `cc-opus`/`cc-sonnet` runs are usable again** (#22). Headless Claude Code failed under the normal worktree + Bubblewrap + loop shape in three sequential ways, plus a stale-state bug:
  - Bind **every** directory along the CLI's symlink chain, not just the PATH dir and the fully-resolved target. `execvp` follows one hop at a time, so an intermediate symlink (`nvm/bin → /usr/local/bin → ~/.local/bin → ~/.local/share/claude/versions/<v>`) in an unmounted directory dangled inside bwrap.
  - Read-only bind only Claude's minimum auth files (`~/.claude/.credentials.json`, `~/.claude.json`) for `claude` commands; the rest of `~/.claude` stays out of the sandbox.
  - Add a Claude-specific `claude auth status` preflight alongside the existing `--version` probe so missing credentials fail fast with an actionable message instead of burning loop iterations.
  - Escalate `--permission-mode dontAsk` to `bypassPermissions` only when an external Bubblewrap sandbox is the filesystem boundary; without a sandbox, require the explicit `--dangerously-bypass-permissions` opt-in. Inject `IS_SANDBOX=1` so Claude Code allows the bypass under root.
  - Record the executor PID in loop state and terminalize a stale `running` state as `executor_missing` when the PID no longer exists.

## [0.34.0] - 2026-07-09

### Changed
- **`codex`/`codex-high`/`codex-xhigh` default to gpt-5.6-terra** (was gpt-5.5). The model is now pinned explicitly with `-m gpt-5.6-terra` instead of relying on the Codex CLI config default, so the shorthand stays honest if `~/.codex/config.toml` drifts.

### Added
- **GPT-5.6 family shorthands**: `sol` (gpt-5.6-sol, latest frontier agentic coding), `terra` (gpt-5.6-terra, balanced everyday — same as the new codex default), `luna` (gpt-5.6-luna, fast/affordable). All support `--variant high/xhigh`; raw slugs like `gpt-5.6-sol` resolve via router aliases. `gpt55`/`gpt54` explicit shorthands remain as legacy pins.

## [0.33.0] - 2026-07-05

### Added
- **`--moa` mixture-of-agents fan-out**: `/run-prompt 123 --moa codex,synthetic,qwen36` runs one prompt across 2+ models in parallel, each in its own isolated worktree (`prompt/{slug}-moa-{label}` branches), then the main Claude session judges — compares diffs, runs tests per worktree, presents a scorecard — and consolidates the winner. Mutually exclusive with `--model`/global `--cli`; implies `--worktree`; `--loop` applies per runner with per-run state keys (`{N}-moa-{label}.json`); `--variant` applies where supported and is dropped per model otherwise. A manifest for the judge phase is written to `~/.claude/loop-state/moa/`. Per-model launch failures and worktree conflicts are recorded per run without aborting the rest of the fan-out.
- **Per-entry CLI overrides in `--moa`**: `model:cli` syntax (e.g. `--moa codex:opencode,qwen36`) routes a single entry through a different CLI; the same model on two CLIs (`codex,codex:opencode`) is a valid two-run harness comparison. Aliases (`cc`, `claudecode`, `antigravity`) normalize; unsupported model+CLI combos fail fast. Bare `claude` (Task subagent) is rejected — `cc-sonnet`, `cc-opus`, or `claude:claude` cover headless Claude runs.
- **`create_worktree(name_suffix=...)`**: worktree helper can suffix branch and directory names so multiple worktrees for the same prompt coexist (used by MoA per-model runs).

## [0.32.0] - 2026-07-04

### Changed
- **Local LMStudio models run with `--pure --agent build`**: the opencode plugin default agent (Sisyphus) plus oh-my-openagent tool schemas cost ~63k input tokens per turn; the lean built-in `build` agent without plugins drops that to ~24k (measured on qwen3.6-35b-a3b). Applied to all 7 `lmstudio:` shorthands across the registry, the cli-detector router, and the `manage-models.py` command builder, so future local models inherit it automatically. Cloud models keep the plugin default agent.

## [0.31.0] - 2026-07-04

### Added
- **Local Qwen 3.6 shorthands**: `qwen36` (`lmstudio/qwen3.6-35b-a3b`, MoE 35B) and `qwen36-27b` (`lmstudio/qwen3.6-27b`, dense 27B) via opencode + LMStudio. Both smoke-tested end-to-end.

### Changed
- **`local`/`qwen` repointed to `qwen3.6-35b-a3b`**: the previous target `qwen3-coder-next` is no longer served by LMStudio. Router (`cli-detector`) and executor registry updated together; consistency tripwire and router tests updated to match.

## [0.30.0] - 2026-07-03

### Added
- **`--require-diff` loop flag + dead-loop detection** (#14, #18): with `--require-diff`, the `--loop` completion marker is rejected when the execution dir has no real file changes (uncommitted, untracked, or commits since loop start; TASK.md/.sisyphus excluded) — a final-iteration rejection ends as the new `completed_unverified` terminal status instead of silent success. Always-on dead-loop detection aborts as `stalled` on two identical consecutive retry reasons, or `blocked` (with a suggested next step) on an isolation-boundary refusal. Default loop behavior is byte-identical when `--require-diff` is absent.
- **Registry↔router consistency tripwire**: `test_registry_consistency.py` fails CI if `router._SHORTHAND` and `scripts/models.json` disagree on shorthand keys, model_id, family, or reasoning_effort.

### Changed
- **Model registry is now a single source of truth** (`scripts/models.json`): `executor.py` loads the registry at runtime and `manage-models.py generate` rewrites 13 marker-delimited regions across 7 docs; `check` is a real drift verifier. Adding a model is now edit-json + generate. Regeneration also fixed real drift (9 shorthands were missing from create-prompt/create-llms menus).
- **`executor.py` split into focused modules** (3,508 → 710 lines): extracted `paths.py`, `repostate.py`, `worktree.py`, `models.py`, `sandbox.py`, `loop.py`; `executor.py` remains the CLI entry point and re-exports the full public surface (pinned by `test_facade.py`). Pure structural move, zero behavior change.
- **CI**: bumped `actions/checkout@v5` / `actions/setup-python@v6` (Node 20 deprecation).

### Fixed
- Closed #14 (silent false success on `--loop`) and #18 (wasted iterations on impossible external read-gates) via the loop-verification work above.

## [0.29.0] - 2026-07-02

### Added
- **Sandbox preflight probe**: before any sandboxed execution, `sandbox_preflight()` runs `<binary> --version` under the exact bwrap invocation the real run will use (same profile, binds, and env passthrough). Environmental breakage — missing runtime binds (#19), startup crashes, broken mounts — now fails immediately with the sandbox config summary and the probe's output instead of burning `--loop` iterations on a failure determined before the first API call. Results are cached per (binary, profile, workspace), so a loop probes once, not per iteration.
- **GitHub Actions CI** (`.github/workflows/tests.yml`): every push to main and every PR runs all six pytest suites (prompt-executor, cli-detector, config-reader, sprint, at-prompt-runner, scripts) plus `manage-models.py check` for model-registry consistency.

### Tests
- Five new tests covering preflight pass/fail/caching/disabled paths and the `run_cli_foreground` abort.

## [0.28.1] - 2026-07-02

### Fixed
- **`--sandbox` no longer strips env-keyed provider credentials** (#21). The `strict`/`balanced` bwrap profiles launch the CLI under `--clearenv` and only re-injected `PATH`/`HOME`/`USER`/`LANG`/`TERM`, so providers that authenticate from the environment — Synthetic (`SYNTHETIC_API_KEY`) and LMStudio local models (`LMSTUDIO_API_KEY`) — failed every request with `401 Unauthorized` while pre-launch validation still passed, burning all `--loop` iterations. `build_bwrap_args` now accepts the credentials the launcher already resolved (a `SANDBOX_ENV_PASSTHROUGH` whitelist plus any model-spec env) and re-injects them via `--setenv` after `--clearenv`. Since `--share-net` was already active in those profiles, withholding the keys protected nothing. Credentials are injected only at real launch sites — command previews and logs never contain them. The `dev` profile (no `--clearenv`) is unchanged.

### Tests
- New coverage for `--setenv` passthrough under `balanced`, the `dev` profile no-op, and `_sandbox_passthrough_env` credential collection.

## [0.28.0] - 2026-07-01

### Added
- **Synthetic provider** (#244) — wires [synthetic.new](https://synthetic.new) as an OpenCode-backed model provider. Four new `--model` shorthands: `synthetic` (GLM-5.2 via `syn:large:text`, 512k context), `syn-flash` (GLM-4.7-Flash), `syn-kimi` (Kimi-K2.6, vision), and `syn-qwen` (Qwen3.6-27B, vision). Requires `SYNTHETIC_API_KEY`; the executor errors clearly with a dashboard link when it's unset. Raw `hf:` IDs remain available via pass-through. Includes router registration, `ai-usage`/`cclimits` quota awareness, and full documentation across the model checklist.

## [0.27.6] - 2026-06-26

### Fixed
- **Worktree `--loop` no longer aborts on coincidental parent-checkout dirtiness** (#20). The 0.27.1 post-iteration isolation guard compared raw `git status --porcelain` of the original checkout and aborted with `status="isolation_breach"` on any new line — but bwrap is the real boundary; the sandboxed CLI cannot write outside its bound paths. The check only caught coincidental parent-side noise and threw away verified runs (one case lost ~2h of `codex xhigh` output after the agent had already emitted `VERIFICATION_COMPLETE`). Two confirmed false-positive paths: (1) stat-only mtime changes from Go tooling (`go build`/`go test` traversal) showing as ` M` until `git update-index --refresh` clears them, and (2) parent-side writes during a long iteration (e.g. the parent chat creating `prompts/NNN-*.md` via `daplug:create-prompt` while the sandboxed CLI is running). Fix combines two changes:
  - `repo_dirty_snapshot` is replaced with `repo_state_snapshot`, which runs `git update-index -q --refresh` first, then enumerates dirty/untracked files via `git ls-files -m -o --exclude-standard -z` and content-hashes modified-tracked files (untracked files only contribute their path). Stat-only churn is invisible to the comparison.
  - The post-iteration delta is now logged as `[Loop] ORIGINAL_CHECKOUT_DIRTIED: <paths>` and appended to `state["original_checkout_warnings"]`, but the loop continues to the completion-marker check instead of aborting. The `isolation_breach` status no longer exists anywhere in the codebase.
- **`<critical_isolation_boundary>` injected block** no longer threatens `isolation_breach` as the post-iter consequence. It still names both the worktree and original-checkout paths and warns subagents not to leak the original-checkout path, but the boundary-enforcement description correctly attributes it to bwrap at the OS level and notes that any parent-side dirtiness is logged as a warning.

### Tests
- New `test_repo_state_snapshot_ignores_stat_only_mtime_change` pins the stat-only regression (`os.utime` between two snapshots returns equal state).
- `test_loop_aborts_with_isolation_breach_when_original_is_dirtied` → `test_loop_warns_but_continues_when_original_is_dirtied` (asserts the loop reaches the completion-marker check, logs `ORIGINAL_CHECKOUT_DIRTIED`, and records the warning in state).
- `test_isolation_block_mentions_isolation_breach_consequence` → `test_isolation_block_mentions_warning_consequence` (asserts the new injected text).

## [0.27.5] - 2026-06-19

### Fixed
- **Bubblewrap sandbox runtime visibility** (#19): sandboxed prompt execution now read-only binds the selected CLI's PATH directory and package-manager runtime root so nvm-installed OpenCode and Bun-installed Codex resolve inside bwrap instead of failing with `opencode: not found` / `codex: not found`.
- **OpenCode sandbox process metadata**: bwrap profiles now mount `/proc`, avoiding Bun crashes when OpenCode starts inside the sandbox.

### Tests
- Added coverage for nvm/OpenCode and Bun/Codex runtime binds.

## [0.27.2] - 2026-06-02

### Fixed
- **Worktree isolation defenses now actually run on the default `/run-prompt --loop` path.** The 0.27.1 mitigations (`<critical_isolation_boundary>` wrapper + post-iteration `git status --porcelain` snapshot guard) were silently disabled in practice: `run_verification_loop_background` spawned its foreground re-entry with `--cwd <worktree>` and `--original-repo-root <orig>` but no flag carrying `worktree_path`. The re-entry deliberately omits `--worktree` (it must not re-create the worktree), so inside the child `args.worktree=False` -> `worktree_path=None` -> `guard_active=False` and the boundary block's injection condition was also false. Both defenses were unreachable on the spawner path; only the direct (non-background) `run_verification_loop` call path that the existing tests covered was protected. New internal flags `--worktree-path` and `--branch-name` are now forwarded by the spawner and consumed by a new `elif args.worktree_path:` branch in main that re-populates state without calling `create_worktree` again. Smoke (`/run-prompt 240 --worktree --loop`) confirms the loop now trips `status: isolation_breach` with the full `[Loop]` diagnostic instead of returning `completed` with leaked files on disk.

### Tests
- `test_bg_spawner_forwards_worktree_path_and_branch` pins the forwarding contract via a `subprocess.Popen` stub.
- `test_bg_spawner_omits_worktree_flags_when_no_worktree` verifies the non-worktree path keeps the positional prompt-number form.
- `test_parser_accepts_worktree_path_and_branch_name` round-trips the new flags through argparse so the spawner's output is consumable by the re-entry.

## [0.27.1] - 2026-05-30

### Fixed
- **Worktree base-branch detection** (#15): `create_worktree` no longer hardcodes `main`. New `detect_default_branch` resolves the base from `origin/HEAD`, falls back to the current branch, then to `"main"`. Repos defaulting to `master` (or anything else) now work with `--worktree` without `--base-branch master`. CLI `--base-branch` still wins as an explicit override.
- **Worktree isolation guard** (partial mitigation for #14): when `--worktree` is set, the verification-loop wrapper now prepends a `<critical_isolation_boundary>` block that names both the worktree and the original-checkout paths and warns the model not to leak the original path into subagent task prompts. Independently, after each iteration the loop snapshots `git status --porcelain` of the original checkout; any change aborts the loop with `status="isolation_breach"` regardless of the completion marker. This catches the prompt-542 failure mode where opencode subagents inherited an absolute path to the main checkout and wrote 138 files outside the worktree while the loop reported success.
- **Loop plumbing**: `run_verification_loop`, `run_verification_loop_background`, and the wrapper take `original_repo_root`; a new `--original-repo-root` CLI flag is forwarded automatically when the background loop re-launches itself in the worktree.

### Tests
- New `skills/prompt-executor/tests/test_worktree_isolation.py` covers `detect_default_branch` (main/master/`origin/HEAD`/no-repo), `repo_dirty_snapshot`, the isolation-boundary wrapper, `create_worktree` base-branch wiring, and an end-to-end loop that mocks `run_cli_foreground` with breach / clean / no-worktree / worktree-equals-original variants and asserts the resulting status.

## [0.27.0] - 2026-05-09

### Changed
- **Codex integration pivoted from prompt bridges to skills.** The v0.26.0 Codex bridge generator wrote files to `~/.codex/prompts/`, but inspection of Codex CLI 0.130's source (`codex-rs/tui/src/bottom_pane/slash_commands.rs`) confirmed that `SlashCommandItem` has only `Builtin` and `ServiceTier` variants — file-based user slash commands aren't a feature. The v0.26.0 bridges shipped inert.
  - **New: `scripts/generate-codex-skills.py`** — emits `~/.codex/skills/daplug/<command>/SKILL.md` files. This IS Codex's supported user-extension mechanism; generated skills appear in Codex's `<skills_instructions>` block automatically.
  - Each skill carries the daplug command's `description` from frontmatter so Codex can auto-trigger on context match. Invoke explicitly with `$<command>` (e.g. `$run-prompt 042`).
  - Sentinel-based cleanup (`<!-- daplug-skill: managed; do not edit -->`) means `--clean` only removes daplug-managed skills.
- **Automatic migration of v0.26.0 installs.** The new generator removes the inert prompt-bridges from `~/.codex/prompts/` (sentinel-identified) and restores any hand-ports archived to `.archive-pre-bridge/`. Skip with `--no-migrate`.
- **`/install-bridges codex`** now runs the skills generator. The bridge-vs-skill terminology distinction is documented in the command help.

### Removed
- `scripts/generate-codex-bridges.py` and its test suite (dead code; the directory it wrote to is not read by Codex).

## [0.26.0] - 2026-05-09

### Added
- **Codex command bridge generator** (`scripts/generate-codex-bridges.py`): Generates Codex-compatible slash command shims under `~/.codex/prompts/` so daplug commands like `/run-prompt`, `/create-prompt`, `/codex-cli`, etc. resolve natively in Codex CLI without manual porting.
  - **Bare-named shims**: `~/.codex/prompts/<command>.md` (no `daplug-` prefix), so commands appear as `/run-prompt 042` rather than `/daplug-run-prompt 042`.
  - **Hand-port safety**: Pre-existing files at colliding paths are moved to `~/.codex/prompts/.archive-pre-bridge/` before the bridge is written, preserving prior manual ports.
  - **Sentinel-based cleanup**: Managed bridges embed `<!-- daplug-bridge: managed; do not edit -->` so `--clean` only removes daplug-generated files; unrelated user prompts are never touched.
- **`/install-bridges codex`**: Command now accepts `codex` as a runtime alongside `opencode`.

## [0.23.10] - 2026-02-22

### Fixed
- **OpenCode session inheritance bug**: Executor now strips runtime OpenCode session env vars (`OPENCODE`, `OPENCODE_HOSTNAME`, `OPENCODE_PORT`, `OPENCODE_SERVER_PASSWORD`) before spawning `opencode run`, preventing repeated `Error: Session not found` failures in verification loops.
- **Regression coverage**: Added test coverage to verify OpenCode subprocess env sanitization while preserving `OPENCODE_CONFIG_DIR`.

## [0.23.9] - 2026-02-22

### Fixed
- **OpenCode CLI override routing**: Explicit `--cli opencode` now takes precedence over router defaults for supported models (including `codex`), so supported overrides no longer fail with a router mismatch error.
- **Regression coverage**: Added/updated variant-routing tests to ensure explicit overrides, default routing behavior, and OpenCode variant propagation remain correct.

## [0.23.8] - 2026-02-22

### Added
- **Executor `--variant` flag**: Added first-class reasoning variant support (`none`, `low`, `medium`, `high`, `xhigh`) with explicit precedence over alias defaults.
- **OpenCode variant passthrough**: `opencode run` invocations now include `--variant <value>` when a variant is selected.

### Changed
- **Variant normalization**: Alias models such as `codex-high`, `codex-xhigh`, `gpt52-high`, and `gpt52-xhigh` now resolve through a unified variant pipeline.
- **CLI override behavior**: Explicit `--cli` overrides are now strict and fail with actionable errors for unsupported model/CLI combinations instead of silently rerouting.

### Fixed
- **Metadata fidelity**: Executor output now reports resolved CLI/variant metadata consistently with the actual command that will run.

## [0.23.5] - 2026-02-15

### Added
- **Claude Code CLI execution**: Run prompts headlessly through the local `claude` CLI
  - New executor `--cli` override: `--cli claude` (aliases: `claudecode`, `cc`)
  - New model shorthands: `cc-sonnet` and `cc-opus` (routes through Claude Code model aliases)

## [0.23.4] - 2026-02-15

### Added
- **`/install-bridges` command**: Install daplug command bridges for other AI coding runtimes
  - Run `/install-bridges opencode` to generate bridge files in `~/.config/opencode/commands/`
  - OpenCode can then invoke daplug commands natively as `/daplug-run-prompt`, `/daplug-prompts`, etc.
  - Supports `--clean` to remove stale bridges before regenerating

## [0.23.3] - 2026-02-15

### Added
- **Test suites for Issues #7 and #8**:
  - 21 tests for `post-push-detect.sh` hook (push detection, non-push filtering, failed push handling, edge cases)
  - 22 tests for `generate-opencode-bridges.py` (spec discovery, bridge rendering, stale cleanup, CLI args)

## [0.23.2] - 2026-02-15

### Added
- **PostToolUse git push hook** (GitHub Issue #7): Automatically nudges Claude to spawn `pipeline-deploy-monitor` after successful `git push` commands
  - Supports `auto_pipeline_monitor: disabled` in `<daplug_config>` to turn off the behavior per project/user config

## [0.23.1] - 2026-02-07

### Added
- **New local models**: `glm-local` (GLM-4.7-Flash via LMStudio) and `qwen-small` (Qwen3-4B, haiku-tier fast model)

### Fixed
- **LMStudio model ID mismatch**: OpenCode config now uses `"id"` overrides to send correct vendor-prefixed model IDs to LMStudio API
  - Bare config keys (e.g., `qwen3-coder-next`) were silently mismatching LMStudio's full IDs (e.g., `qwen/qwen3-coder-next`)
  - Only worked due to LMStudio bug [#619](https://github.com/lmstudio-ai/lmstudio-bug-tracker/issues/619) (single-model fallback); failed intermittently with multiple models loaded

### Changed
- Default qwen/local model upgraded from `qwen3-next-80b` to `qwen3-coder-next` (code-optimized)
- Model display names updated to reflect actual LMStudio model identifiers

## [0.23.0] - 2026-02-07

### Added
- **OpenCode Local Model Default**: Local models (`local`, `qwen`, `devstral`) now route through OpenCode CLI instead of Codex
  - OpenCode connects to LMStudio with proper model IDs (`lmstudio/qwen3-coder-next`, `lmstudio/devstral-small-2-2512`)
  - Router prefers OpenCode with automatic Codex fallback when OpenCode is unavailable
- **`--cli` Override Flag**: New executor argument to override the CLI wrapper for any model
  - `--cli codex` restores legacy Codex profile behavior for local models
  - `--cli opencode` forces OpenCode for models that default to other CLIs

### Changed
- Bumped default Codex model from `gpt-5.2-codex` to `gpt-5.3-codex`
- Updated `_normalize_preferred_agent()` to map local models to `opencode`
- Local model fallback chain changed from `[codex]` to `[opencode, codex]`

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

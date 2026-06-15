<objective>
Add Google Antigravity CLI (`agy`) as a first-class daplug runner for Google/Gemini model shorthands while preserving the existing legacy Gemini CLI runner as a fallback.

The end state should let `/daplug:run-prompt ... --model gemini*` use `agy` when it is installed and healthy, but still support existing `gemini` CLI installs for enterprise/legacy users.
</objective>

<context>
Read `./CLAUDE.md` first for project conventions, model-management expectations, testing patterns, and git hygiene.

Google is transitioning consumer Gemini CLI usage to Antigravity CLI. This task is not a hard rename from `gemini` to `agy`; it is a compatibility migration that adds a new runner and updates routing.

Local research/probes from the current environment:
- `command -v agy` -> `/root/.local/bin/agy`
- `agy --version` -> `1.0.7`
- `command -v gemini` -> not found
- `agy --print 'Say only: ok'` -> `ok`
- `agy --model 'Gemini 3.5 Flash (High)' --print 'Say only: ok'` -> `ok`
- `agy --model 'google:gemini-3.1-pro-preview' --print 'Say only ok'` -> `ok`
- `printf 'prompt' | agy --print` fails with `flag needs an argument: -print`, so assume prompt transport remains argv-style unless you discover and test a real stdin mode.

Observed `agy --help` flags/subcommands include:
- `--add-dir`
- `--continue` / `-c`
- `--conversation`
- `--dangerously-skip-permissions`
- `--log-file`
- `--model`
- `--print` / `-p` / `--prompt`
- `--print-timeout`
- `--prompt-interactive` / `-i`
- `--sandbox`
- subcommands: `changelog`, `install`, `models`, `plugin`/`plugins`, `update`

Observed `agy models` output:
- `Gemini 3.5 Flash (Medium)`
- `Gemini 3.5 Flash (High)`
- `Gemini 3.5 Flash (Low)`
- `Gemini 3.1 Pro (Low)`
- `Gemini 3.1 Pro (High)`
- `Claude Sonnet 4.6 (Thinking)`
- `Claude Opus 4.6 (Thinking)`
- `GPT-OSS 120B (Medium)`

Official migration/config facts to account for:
- Antigravity binary is `agy`; default install path is normally `~/.local/bin/agy`.
- Noninteractive command shape is `agy --model <model> --print <prompt>`.
- Settings path: `~/.gemini/antigravity-cli/settings.json`.
- Plugin staging path: `~/.gemini/antigravity-cli/plugins/<plugin_name>/`.
- MCP paths: `~/.gemini/config/mcp_config.json` and `.agents/mcp_config.json`.
- Workspace skills path changed from `.gemini/skills/` to `.agents/skills/`.
- Existing context files `GEMINI.md` and `AGENTS.md` remain supported.

Implementation anchors:
- `./skills/cli-detector/scripts/plugins/gemini.py` currently detects only `gemini`, checks config paths `~/.config/gemini/config.json`, `~/.gemini/settings.json`, `.gemini/settings.json`, and builds `['gemini', '-y', '-m', model, '-p', prompt]`. It is a `SimpleCLIPlugin` subclass (`base.py`) that sets `_name`, `_display_name`, `_version_cmd`, defines `build_command()` and `detect_issues()`, and exports a module-level `PLUGIN = GeminiCLI()` at the bottom of the file.
- `./skills/cli-detector/scripts/plugins/__init__.py` auto-discovers plugins via `discover_plugins()` using `pkgutil.iter_modules` (filesystem scan). A new plugin module is picked up automatically as long as it exposes a module-level `PLUGIN` (a `CLIPlugin` instance) or a `get_plugin()` callable — modules whose names start with `_` or equal `base` are skipped. **No `__init__.py` edit is required**; just add the new file. Note `discover_plugins()` caches results in `_PLUGIN_CACHE`, so tests that import multiple plugin sets may need a fresh process.
- `./skills/cli-detector/scripts/router.py` defines Google shorthands around the Google/Gemini section, has fallback chain `"google": ["gemini", "opencode", "aider"]`, and `_build_command()` emits Gemini commands.
- `./skills/prompt-executor/scripts/executor.py` defines Google/Gemini model specs, `_build_gemini_command()`, display labels, selected CLI branches, and CLI override supported model sets.
- Tests to inspect/update include `./skills/cli-detector/tests/test_router.py`, `./skills/cli-detector/tests/test_detect_clis.py`, `./skills/cli-detector/tests/test_plugins.py`, `./skills/prompt-executor/tests/`, and `./skills/prompt-executor/scripts/test_executor_markers.py`.
- Documentation/command references may need updates: `./CLAUDE.md`, `./skills/prompt-executor/SKILL.md`, `./commands/run-prompt.md`, `./commands/prompts.md`, `./commands/create-prompt.md`, `./commands/create-llms-txt.md`, and `./README.md`.
</context>

<requirements>
1. Add an Antigravity CLI plugin instead of deleting or mutating the legacy Gemini plugin.
   - Prefer the plugin name `agy` unless the existing codebase strongly suggests `antigravity` is better.
   - Detect executable `agy`.
   - Use `agy --version` for version detection.
   - Include relevant Antigravity settings/config paths in detection/issue checks.
   - Expose Google/Gemini model availability in a way compatible with existing router behavior.

2. Preserve legacy Gemini CLI support.
   - Keep the existing `gemini` plugin and command generation working.
   - Do not remove enterprise/legacy `gemini` paths or model aliases.

3. Prefer `agy` for Google-family routing when installed and healthy.
   - Update the Google fallback chain from approximately `["gemini", "opencode", "aider"]` to approximately `["agy", "gemini", "opencode", "aider"]`.
   - Ensure router behavior still falls back to `gemini`, `opencode`, or `aider` when `agy` is unavailable or has blocking error issues.

4. Add prompt-executor support for `selected_cli == "agy"`.
   - Command shape should be equivalent to:
     ```python
     ["agy", "--model", mapped_model, "--print"]
     ```
   - Use `stdin_mode = "arg"` unless you discover and verify a real stdin prompt mode.
   - Keep argv prompt-passing behavior explicit in comments/tests because `agy --print` requires an argument.

5. Handle model mapping deliberately.
   - Existing user-facing shorthands such as `gemini`, `gemini-high`, `gemini-xhigh`, `gemini25pro`, `gemini25flash`, `gemini25lite`, `gemini3flash`, `gemini3pro`, and `gemini31pro` should continue to resolve.
   - Decide whether each shorthand passes an `agy models` display name or a compatible Google model ID.
   - Add tests for the mapping you choose.
   - Suggested starting point if no better evidence appears:
     - `gemini` -> `Gemini 3.5 Flash (Medium)` or compatible `gemini-3.5-flash`
     - `gemini-high` / `gemini31pro` -> `Gemini 3.1 Pro (High)`
     - old `gemini25*` and `gemini3*` aliases should remain compatible if `agy` accepts their IDs; otherwise document and test fallback behavior.

6. Evaluate headless permission behavior.
   - `agy` exposes `--dangerously-skip-permissions`, but do not add it blindly.
   - Test whether it is needed for noninteractive daplug loops, or leave a clearly scoped TODO/guard if safe behavior cannot be established.
   - Do not introduce interactive hangs into `/daplug:run-prompt --loop`.

7. Update tests and docs together.
   - Update CLI detector tests for plugin discovery and command generation.
   - Update router tests for Google-family fallback priority and legacy fallback.
   - Update prompt-executor tests for `agy` command shape and stdin mode.
   - Update docs/command help only where they currently imply Gemini CLI is the only Google runner.

8. Avoid unrelated model/provider changes.
   - Do not change OpenCode, Codex, Z.AI, local model, or Claude routing except where shared routing/test fixtures require adding `agy`.
</requirements>

<implementation_guidance>
For maximum efficiency, inspect all relevant files before editing and update related code/tests in cohesive chunks.

Potential implementation shape:
1. Add `./skills/cli-detector/scripts/plugins/agy.py` modeled after `gemini.py`: subclass `SimpleCLIPlugin`, set `_name = "agy"`, `_display_name`, `_version_cmd = ["agy", "--version"]`, implement `build_command()` to emit `["agy", "--model", mapped_model, "--print", prompt]` (argv-style — see prompt-transport note), implement `detect_issues()` checking Antigravity config paths, and export `PLUGIN = AntigravityCLI()` at module bottom.
2. No `__init__.py` change is needed — `discover_plugins()` filesystem-scans the package and picks up any module exporting `PLUGIN`. Verify discovery with a quick `python3 -c "from plugins import discover_plugins; print([p.name for p in discover_plugins()])"` from the scripts dir.
3. Update `router.py` to know `agy` as a Google-capable runner and build `agy --model ... --print` commands.
4. Update `executor.py` with `_build_agy_command()` and a `selected_cli == "agy"` branch.
5. Update any CLI override validation so `--cli agy` is accepted for Google/Gemini shorthands if override support exists.
6. Update tests and documentation.

Prefer small, readable helper functions over broad rewrites. Keep comments focused on non-obvious compatibility decisions, especially prompt transport and legacy fallback.
</implementation_guidance>

<validation>
Run the relevant test suite from the repo root or skill directories. At minimum, run tests covering:
- CLI detector plugin discovery and routing.
- Router model resolution/command structure.
- Prompt executor command generation and marker/no-PTY expectations.

Also run command-generation smoke tests, for example:
```bash
python3 skills/cli-detector/scripts/router.py --table
python3 skills/prompt-executor/scripts/executor.py 001 --model gemini
python3 skills/prompt-executor/scripts/executor.py 001 --model gemini-high
python3 skills/prompt-executor/scripts/executor.py 001 --model gemini31pro
```

If `agy` is installed in the environment, run a non-destructive live smoke test:
```bash
agy --print 'Say only: ok'
agy --model 'Gemini 3.5 Flash (High)' --print 'Say only: ok'
```

Do not require network-heavy or code-editing live tests in CI.
</validation>

<success_criteria>
- Google/Gemini shorthands prefer `agy` when it is installed and healthy.
- Legacy `gemini` CLI support remains intact and tested as fallback.
- `agy` command generation uses `agy --model <model> --print <prompt>` semantics and does not assume stdin support.
- Unit tests cover new `agy` routing, legacy fallback, command shape, and prompt-executor integration.
- Relevant docs/help reflect Antigravity support without overstating that Gemini CLI is gone for every user.
- No unrelated provider/model routing changes are introduced.
- No commits, merges, pushes, tags, or releases are performed.
</success_criteria>

<output>
Modify existing files where possible. Create new files only for the new `agy` plugin and any tests required to cover it.

Report:
- Files changed.
- Routing/model mapping decisions made.
- Verification commands run and their results.
- Any remaining known limitations around `agy` stdin, permissions, or model IDs.

End with one of the daplug loop markers:
```xml
<verification>VERIFICATION_COMPLETE</verification>
```
or
```xml
<verification>NEEDS_RETRY: concise reason</verification>
```
</output>
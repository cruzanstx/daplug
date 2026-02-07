<objective>
Add a `--cli` override flag to `executor.py` that lets users choose which CLI wrapper (codex or opencode) is used for any model, and change the default for local models (`local`, `qwen`, `devstral`) from codex to opencode.

This matters because local models currently only run via codex CLI, but opencode already has LMStudio configured as a custom provider with proper model mappings. Users should be able to choose their preferred CLI wrapper without editing code.
</objective>

<context>
**Project**: daplug - Claude Code plugin for multi-model prompt execution
**File to modify**: `skills/prompt-executor/scripts/executor.py`

**Current state** (lines ~549-551, ~686-703):
- `_normalize_preferred_agent()` maps `qwen`, `devstral`, `local` → `"codex"`
- Model entries for `local`, `qwen`, `devstral` all use `["codex", "exec", "--full-auto", "--profile", "local"]`
- There is no way for users to override the CLI wrapper independently from the model

**OpenCode config** (`~/.config/opencode/opencode.json`) already has:
- `lmstudio/qwen3-next-80b` (Qwen model)
- `lmstudio/devstral-small-2-2512` (Devstral model)
- `lmstudio/gpt-oss-120b` (GPT-OSS model)
- Custom agents: `local` (qwen), `local-devstral` (devstral), `local-gpt-oss` (GPT-OSS)
- Permission config for headless runs already set

**OpenCode CLI syntax**:
```bash
opencode run --format json -m lmstudio/qwen3-next-80b "prompt content"
opencode run --format json -m lmstudio/devstral-small-2-2512 "prompt content"
```

**Codex CLI syntax** (current):
```bash
codex exec --full-auto --profile local - < prompt.md
```

**stdin_mode difference**: codex uses `"dash"` (pipe to stdin), opencode uses `"arg"` (pass as argument)
</context>

<requirements>
1. Add a `--cli` argparse argument to `executor.py` that accepts `codex` or `opencode` as values
2. When `--cli` is provided, it overrides the default CLI for the selected model
3. Change the DEFAULT CLI for local models from codex to opencode:
   - `local` → `opencode run --format json -m lmstudio/qwen3-next-80b`
   - `qwen` → `opencode run --format json -m lmstudio/qwen3-next-80b`
   - `devstral` → `opencode run --format json -m lmstudio/devstral-small-2-2512`
4. Update `_normalize_preferred_agent()` (line ~549) to map `qwen`, `devstral`, `local` → `"opencode"` instead of `"codex"`
5. When `--cli codex` is explicitly passed with a local model, fall back to the old codex profile behavior
6. Preserve backward compatibility: existing `--model local` without `--cli` should work (just via opencode now)
</requirements>

<implementation>
1. **Add `--cli` argument** (~line 1720, near other argparse args):
   ```python
   parser.add_argument("--cli", choices=["codex", "opencode"],
                        default=None,
                        help="Override CLI wrapper (default: auto-detected per model)")
   ```

2. **Update model entries** in `get_cli_info()` models dict (~line 686-703):
   ```python
   "local": {
       "command": ["opencode", "run", "--format", "json", "-m", "lmstudio/qwen3-next-80b"],
       "display": "qwen (local via opencode)",
       "env": {},
       "stdin_mode": "arg"
   },
   "qwen": {
       "command": ["opencode", "run", "--format", "json", "-m", "lmstudio/qwen3-next-80b"],
       "display": "qwen (local via opencode)",
       "env": {},
       "stdin_mode": "arg"
   },
   "devstral": {
       "command": ["opencode", "run", "--format", "json", "-m", "lmstudio/devstral-small-2-2512"],
       "display": "devstral (local via opencode)",
       "env": {},
       "stdin_mode": "arg"
   },
   ```

3. **Add codex fallback entries** for when `--cli codex` is explicitly passed:
   ```python
   # Inside get_cli_info, after resolving model, check cli_override
   if cli_override == "codex" and model in ("local", "qwen", "devstral"):
       # Return legacy codex profile commands
       ...
   ```

4. **Update `_normalize_preferred_agent()`** (line ~549):
   ```python
   if v in {"qwen", "devstral", "local"}:
       return "opencode"  # was "codex"
   ```

5. **Thread `--cli` through**: Pass the cli_override from argparse into `get_cli_info()` as an optional parameter

**Important**: Do NOT change the `--model` choices list - `local`, `qwen`, `devstral` remain valid model names. Only the underlying CLI command changes.
</implementation>

<verification>
Before declaring complete, verify:

1. Run the executor in info mode (no --run) for each local model:
   ```bash
   python3 skills/prompt-executor/scripts/executor.py 011 --model local
   python3 skills/prompt-executor/scripts/executor.py 011 --model qwen
   python3 skills/prompt-executor/scripts/executor.py 011 --model devstral
   ```
   Confirm output shows opencode commands, not codex.

2. Test --cli override:
   ```bash
   python3 skills/prompt-executor/scripts/executor.py 011 --model qwen --cli codex
   ```
   Confirm output shows codex profile commands.

3. Test that non-local models are unaffected:
   ```bash
   python3 skills/prompt-executor/scripts/executor.py 011 --model codex
   python3 skills/prompt-executor/scripts/executor.py 011 --model gemini
   ```

4. Run existing tests:
   ```bash
   cd skills/config-reader && python3 -m pytest tests/ -v
   ```

<verification>VERIFICATION_COMPLETE</verification> only when all checks pass.
</verification>

<success_criteria>
- `--model local/qwen/devstral` defaults to opencode CLI commands
- `--cli codex` overrides back to legacy codex behavior for local models
- `--cli` flag is optional and has no effect when not provided
- All existing models (codex, gemini, zai, etc.) work unchanged
- Existing tests pass
</success_criteria>
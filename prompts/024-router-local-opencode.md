<objective>
Update the cli-detector router to route local models (`local`, `qwen`, `devstral`) through opencode by default instead of codex, matching the executor changes from prompt 023.

The router is the source of truth when the `/detect-clis` cache is present. Without this update, the cache-based routing will override the executor defaults and continue sending local models to codex.
</objective>

<context>
**Project**: daplug - Claude Code plugin for multi-model prompt execution
**File to modify**: `skills/cli-detector/scripts/router.py`

**Current state** (lines ~86-93):
```python
# Local models (provider is detected at runtime)
"local": _ModelRequest("local", family="local"),
"qwen": _ModelRequest("qwen", family="local", local_hint="qwen", codex_profile="local"),
"devstral": _ModelRequest(
    "devstral",
    family="local",
    local_hint="devstral",
    codex_profile="local-devstral",
),
```

**Fallback chains** (line ~109):
```python
"local": ["codex"],  # Currently only codex
```

**OpenCode config** (`~/.config/opencode/opencode.json`) already has:
- Provider: `lmstudio` with `baseURL: http://192.168.1.254:1234/v1`
- Models: `qwen3-next-80b`, `devstral-small-2-2512`, `gpt-oss-120b`
- Agents: `local` (qwen), `local-devstral` (devstral), `local-gpt-oss`

**Dependency**: This prompt depends on prompt 023 (--cli flag added to executor). The router should prefer opencode for local models, with codex as fallback.
</context>

<requirements>
1. Update `_SHORTHAND` entries for `local`, `qwen`, `devstral` to prefer opencode:
   - Add `force_cli="opencode"` or equivalent routing hint
   - Map model IDs to opencode-compatible identifiers (e.g., `lmstudio/qwen3-next-80b`)

2. Update `_FALLBACK_CHAINS` for the `"local"` family:
   ```python
   "local": ["opencode", "codex"],  # opencode first, codex as fallback
   ```

3. Update the `resolve_model()` function to handle local model routing:
   - When opencode is installed: route to `opencode run --format json -m lmstudio/<model>`
   - When only codex is installed: fall back to `codex exec --full-auto --profile local`
   - Build correct command with opencode syntax (stdin_mode="arg", not "dash")

4. Update `_cli_info_from_router()` to handle opencode + local model combinations:
   - Set `stdin_mode = "arg"` for opencode
   - No special env vars needed (opencode reads its own config)

5. Update existing tests in `skills/cli-detector/tests/test_router.py`:
   - `TestLocalModels` class tests should expect opencode as preferred CLI
   - Add tests for codex fallback when opencode is not installed
</requirements>

<implementation>
1. **Update `_SHORTHAND`** entries (~line 86-93):
   ```python
   "local": _ModelRequest(
       "local", family="local", 
       model_id="lmstudio:qwen3-next-80b",
       force_cli="opencode",
   ),
   "qwen": _ModelRequest(
       "qwen", family="local",
       model_id="lmstudio:qwen3-next-80b",
       local_hint="qwen",
       force_cli="opencode",
       codex_profile="local",  # Keep for fallback
   ),
   "devstral": _ModelRequest(
       "devstral", family="local",
       model_id="lmstudio:devstral-small-2-2512",
       local_hint="devstral",
       force_cli="opencode",
       codex_profile="local-devstral",  # Keep for fallback
   ),
   ```

2. **Update `_FALLBACK_CHAINS`** (~line 109):
   ```python
   "local": ["opencode", "codex"],
   ```

3. **Update command building** in resolve_model or _build_command:
   - For opencode + local: `["opencode", "run", "--format", "json", "-m", "lmstudio/<model>"]`
   - For codex fallback: `["codex", "exec", "--full-auto", "--profile", "<profile>"]`

4. **Update tests** in `skills/cli-detector/tests/test_router.py`:
   - `test_local_routes_to_lmstudio` → expect opencode CLI
   - `test_qwen_routes_to_local_profile` → expect opencode CLI with lmstudio model
   - `test_devstral_routes_to_local_devstral_profile` → expect opencode CLI
   - Add: `test_local_falls_back_to_codex` → when opencode not installed
</implementation>

<verification>
Run the full test suite:
```bash
cd /storage/projects/docker/daplug
python3 -m pytest skills/cli-detector/tests/ -v
```

Verify routing table output:
```bash
PLUGIN_ROOT=$(jq -r '.plugins."daplug@cruzanstx"[0].installPath' ~/.claude/plugins/installed_plugins.json)
python3 "$PLUGIN_ROOT/skills/cli-detector/scripts/router.py" --table
```

Confirm local models show opencode as preferred CLI.

<verification>VERIFICATION_COMPLETE</verification> only when all tests pass.
</verification>

<success_criteria>
- Router prefers opencode for local models when opencode is installed
- Falls back to codex profiles when opencode is not installed
- All existing tests pass (update expectations where needed)
- New tests cover the fallback scenario
- `--table` output shows opencode for local models
</success_criteria>
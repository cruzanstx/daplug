# Prompt 020: CLI Detection Routing Integration

## Objective

Integrate the `cli-detector` cache into `/run-prompt` and `/create-prompt` so that:
1. Model selection is based on what's actually installed
2. `preferred_agent` from `<daplug_config>` is respected
3. Graceful fallbacks when preferred CLI isn't available
4. Local model routing works automatically

## Context

The `cli-detector` skill now scans and caches installed CLIs to `~/.claude/daplug-clis.json`. This cache contains:
- Which CLIs are installed (claude, codex, gemini, opencode, aider, goose, ghcopilot)
- Their versions and detected issues
- Which local providers are running (Ollama, LMStudio)
- Available models per CLI

Currently `/run-prompt` has hardcoded model mappings in `executor.py`. This prompt integrates the cache for dynamic routing.

## Dependencies

- Prompt 014: CLI detection implementation ✅
- Prompt 015: `/detect-clis` command ✅

## Requirements

### 1. Create Routing Module

Create `skills/cli-detector/scripts/router.py`:

```python
"""
Model routing based on CLI detection cache.

Responsibilities:
- Load and validate the CLI cache
- Resolve model shorthand to actual CLI + model
- Provide fallback chain when preferred CLI unavailable
- Handle local model routing (Ollama/LMStudio)
"""

def get_available_models() -> list[dict]:
    """Return all models available across installed CLIs."""
    pass

def resolve_model(shorthand: str, preferred_cli: str | None = None) -> tuple[str, str, list[str]]:
    """
    Resolve model shorthand to (cli_name, model_id, command).

    Args:
        shorthand: User input like "codex", "gemini-high", "local", "gpt52"
        preferred_cli: From daplug_config preferred_agent

    Returns:
        (cli_name, model_id, command_args)

    Raises:
        ModelNotAvailable: If no installed CLI can run the requested model
    """
    pass

def get_routing_table() -> dict[str, dict]:
    """
    Return the full routing table showing model -> CLI mappings.

    Used by /create-prompt to show what's available.
    """
    pass
```

### 2. Update Executor to Use Router

Modify `skills/prompt-executor/scripts/executor.py`:

1. Import the router module
2. Replace hardcoded `models = {...}` dict with dynamic lookup
3. Add fallback logic when preferred model/CLI isn't available
4. Keep backward compatibility (hardcoded models still work if cache missing)

**Key changes:**

```python
# Before (hardcoded)
models = {
    "codex": {"command": ["codex", "exec", "--full-auto", "-"], ...},
    "gemini": {"command": ["gemini", "-y", "-p"], ...},
    ...
}

# After (dynamic with fallback)
def get_model_config(shorthand: str) -> dict:
    """Get model config, preferring cache but falling back to hardcoded."""
    try:
        from cli_detector.router import resolve_model
        cli, model_id, cmd = resolve_model(shorthand, get_preferred_agent())
        return {"command": cmd, "display": f"{cli} ({model_id})", ...}
    except (ImportError, ModelNotAvailable):
        # Fall back to hardcoded for backward compatibility
        return HARDCODED_MODELS.get(shorthand)
```

### 3. Update /create-prompt Model Selection

Modify `commands/create-prompt.md` to:

1. Read available models from cache instead of hardcoded list
2. Only offer models that are actually installed
3. Show which CLI will be used for each model
4. Respect `preferred_agent` when recommending defaults

**Example improved output:**

```
Available models (from /detect-clis cache):

| Shorthand | Model | CLI | Status |
|-----------|-------|-----|--------|
| codex | gpt-5.2-codex | codex | ✅ Ready |
| codex-high | gpt-5.2-codex (high reasoning) | codex | ✅ Ready |
| gemini | gemini-3-flash | gemini | ⚠️ Not authenticated |
| local | qwen2.5-coder:32b | codex (LMStudio) | ✅ Running |
| aider | gpt-4o | aider | ❌ Not installed |

Your preferred_agent: codex
```

### 4. Local Model Routing (with Remote Endpoint Support)

Many users run local models on dedicated GPU servers or homelab machines, not just localhost. Support both local and remote endpoints.

#### 4.1 Endpoint Configuration in daplug_config

Add support for custom endpoints in `<daplug_config>`:

```xml
<daplug_config>
preferred_agent: codex
local_providers:
  lmstudio: http://192.168.1.50:1234/v1
  ollama: http://gpu-server.local:11434/v1
  vllm: http://inference.local:8000/v1
</daplug_config>
```

**Note:** Use full base URL including any path prefix (e.g., `/v1`, `/api/openai`). The router appends `/models`, `/chat/completions`, etc. as needed.

**Supported providers:**
- **LM Studio** - Desktop app, easy model management, default `:1234/v1`
- **Ollama** - CLI-first, good for servers, default `:11434/v1`
- **vLLM** - High-performance inference server, default `:8000/v1`

**Config schema update** for `config-reader`:

```python
KNOWN_KEYS = [
    "preferred_agent",
    "worktree_dir",
    "llms_txt_dir",
    # ... existing keys ...
    "local_providers",  # NEW: dict of provider → endpoint URL
]
```

#### 4.2 Endpoint Resolution Priority

When checking for local providers:

1. **Config endpoint** - Use `local_providers.lmstudio` if set
2. **Environment variable** - Check `LMSTUDIO_ENDPOINT` / `OLLAMA_HOST`
3. **Localhost default** - Fall back to `localhost:1234` / `localhost:11434`

```python
def get_provider_endpoint(provider: str) -> str:
    """Get endpoint for provider, checking config → env → default."""
    config = load_daplug_config()
    local_providers = config.get("local_providers", {})

    if provider == "lmstudio":
        return (
            local_providers.get("lmstudio")
            or os.environ.get("LMSTUDIO_ENDPOINT")
            or "http://localhost:1234/v1"
        )
    elif provider == "ollama":
        return (
            local_providers.get("ollama")
            or os.environ.get("OLLAMA_HOST")  # Ollama convention
            or "http://localhost:11434/v1"
        )
    return None
```

#### 4.3 /detect-clis Endpoint Discovery

Update `/detect-clis` to:

1. Check configured/default endpoints
2. Report which endpoints are reachable
3. Offer to configure if localhost fails

**Updated output:**

```
🖥️ Local Model Providers:

| Provider  | Base URL                        | Status       | Loaded Models          |
| --------- | ------------------------------- | ------------ | ---------------------- |
| LM Studio | http://192.168.1.50:1234/v1     | ✅ Running   | qwen2.5-coder:32b      |
| Ollama    | http://localhost:11434/v1       | ❌ Not found | -                      |

💡 Configure remote endpoints in your CLAUDE.md:
   <daplug_config>
   local_providers:
     lmstudio: http://your-gpu-server:1234/v1
     ollama: http://your-server:11434/v1
   </daplug_config>
```

#### 4.4 First-Run Setup Flow

When `/detect-clis` finds no local providers at default endpoints, prompt:

```
No local model providers detected at default endpoints.

Do you have LM Studio or Ollama running on a remote server?
- [1] Yes, configure remote endpoint
- [2] No, skip local models
- [3] I'll start one locally first

> 1

Enter LM Studio base URL (e.g., http://192.168.1.50:1234/v1):
> http://gpu-server.local:1234/v1

✅ Connected! Found 2 models: qwen2.5-coder:32b, deepseek-coder-v2

Add to your CLAUDE.md? [Y/n] y

Added to <daplug_config>:
  local_providers:
    lmstudio: http://gpu-server.local:1234/v1
```

#### 4.5 Routing Logic

When `--model local` or `--model qwen` is used:

```python
def resolve_local_model(model_hint: str | None = None) -> tuple[str, str, list[str]]:
    """
    Resolve local model request to specific CLI + command.

    Checks configured endpoints first, then defaults.
    """
    cache = load_cache()
    providers = cache.get("providers", {})

    lmstudio = providers.get("lmstudio", {})
    ollama = providers.get("ollama", {})

    # Prefer LMStudio (typically faster for coding models)
    if lmstudio.get("running"):
        endpoint = lmstudio.get("endpoint")
        models = lmstudio.get("loaded_models", [])
        model = match_model(model_hint, models) if model_hint else models[0]
        return build_codex_local_command(endpoint, model)

    elif ollama.get("running"):
        endpoint = ollama.get("endpoint")
        models = ollama.get("loaded_models", [])
        model = match_model(model_hint, models) if model_hint else models[0]
        return build_opencode_ollama_command(endpoint, model)

    else:
        raise ModelNotAvailable(
            "No local model provider running.\n"
            "Start Ollama/LMStudio locally, or configure remote base URL:\n"
            "  <daplug_config>\n"
            "  local_providers:\n"
            "    lmstudio: http://your-server:1234/v1\n"
            "  </daplug_config>"
        )
```

### 5. Fallback Chain

When preferred CLI isn't available, try fallbacks:

| Model Family | Preferred | Fallback 1 | Fallback 2 |
|--------------|-----------|------------|------------|
| `anthropic:*` | claude | opencode | aider |
| `openai:*` | codex | opencode | aider |
| `google:*` | gemini | opencode | aider |
| `zai:*` | opencode | codex (zai profile) | - |
| `local:*` | codex | opencode | aider |

**Example:**
```python
# User wants gemini but it's not installed
resolve_model("gemini")
# → Tries: gemini (not installed) → opencode (installed) → returns opencode config
```

## File Changes

| File | Change |
|------|--------|
| `skills/cli-detector/scripts/router.py` | New file - routing logic |
| `skills/cli-detector/scripts/__init__.py` | Export router |
| `skills/cli-detector/scripts/providers/base.py` | Add endpoint config support |
| `skills/config-reader/scripts/config.py` | Add `local_providers` to KNOWN_KEYS |
| `skills/prompt-executor/scripts/executor.py` | Use router, keep hardcoded fallback |
| `commands/create-prompt.md` | Dynamic model list from cache |
| `commands/run-prompt.md` | Document routing behavior |
| `commands/detect-clis.md` | Add endpoint configuration hints |

## Testing

Create `skills/cli-detector/tests/test_router.py`:

```python
def test_resolve_model_returns_installed_cli():
    """Should return config for installed CLI."""

def test_resolve_model_falls_back_when_preferred_missing():
    """Should use fallback when preferred CLI not installed."""

def test_resolve_local_model_prefers_lmstudio():
    """Should prefer LMStudio when both providers running."""

def test_resolve_local_model_uses_configured_endpoint():
    """Should use endpoint from daplug_config over localhost default."""

def test_resolve_model_raises_when_nothing_available():
    """Should raise ModelNotAvailable with helpful message."""

def test_get_routing_table_shows_all_options():
    """Should return complete routing table for UI."""

def test_backward_compat_when_cache_missing():
    """Should fall back to hardcoded models if cache doesn't exist."""

def test_get_provider_endpoint_priority():
    """Should check config → env → default in order."""
```

## Acceptance Criteria

- [ ] `router.py` created with `resolve_model()`, `get_routing_table()`
- [ ] `/run-prompt --model codex` uses cache when available
- [ ] `/run-prompt --model codex` falls back to hardcoded when cache missing
- [ ] `/run-prompt --model local` routes to running provider
- [ ] Remote endpoint support via `local_providers` in daplug_config
- [ ] `/detect-clis` shows configured endpoints and suggests config when localhost fails
- [ ] `/create-prompt` shows only installed models
- [ ] Fallback chain works (e.g., gemini → opencode if gemini not installed)
- [ ] All existing `/run-prompt` functionality preserved
- [ ] Tests pass: `cd skills/cli-detector && python3 -m pytest tests/test_router.py -v`

## Verification

```bash
# Test routing resolution
python3 skills/cli-detector/scripts/router.py --resolve codex
python3 skills/cli-detector/scripts/router.py --resolve local
python3 skills/cli-detector/scripts/router.py --table

# Test executor still works
python3 skills/prompt-executor/scripts/executor.py 001 --model codex

# Run tests
cd skills/cli-detector && python3 -m pytest tests/test_router.py -v
```

<verification>VERIFICATION_COMPLETE</verification> when:
1. Router module created and tested
2. Executor uses router with hardcoded fallback
3. All existing tests still pass
4. New router tests pass

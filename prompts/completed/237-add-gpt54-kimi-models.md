<objective>
Add two new models to daplug: GPT-5.4 (as the new default codex model) and Kimi K2.5 (as a new opencode option).

GPT-5.4 replaces GPT-5.3-codex as the default whenever the user says "codex". Kimi K2.5 is a new model accessible via OpenCode.
</objective>

<context>
GPT-5.4 just released and is available as `openai/gpt-5.4` in both Codex CLI and OpenCode.
Kimi K2.5 just released and is available as `opencode/kimi-k2.5` in OpenCode (provider model ID: `synthetic/hf:moonshotai/Kimi-K2.5`).

OpenCode config already has gpt-5.4 as its default model (`~/.config/opencode/opencode.json`).

Read `CLAUDE.md` in the repo root for the full "Managing Models" checklist — it lists all 14 files that must be updated when adding/changing models.
</context>

<requirements>
**GPT-5.4 changes (update existing "codex" entry):**

1. In `skills/prompt-executor/scripts/executor.py`:
   - Update `LEGACY_MODEL_DISPLAY["codex"]` display string from gpt-5.3-codex to gpt-5.4
   - Update `MODEL_SPECS["codex"]["model_id"]` from `"openai:gpt-5.3-codex"` to `"openai:gpt-5.4"`
   - Keep `codex-spark` pointing at gpt-5.3-codex-spark (unchanged)
   - Keep `codex-high` and `codex-xhigh` — these should now resolve to gpt-5.4 with reasoning variants (update their display strings and model_ids accordingly)
   - Update the `--model` argparse choices if needed
   - Add `"gpt54"` as a new standalone model shorthand pointing to `openai:gpt-5.4` via codex (similar to how gpt52 exists)
   - Add `"gpt54-high"` and `"gpt54-xhigh"` variants

2. In `skills/prompt-executor/SKILL.md`:
   - Update `--model` options list to reflect gpt-5.4
   - Update Model Reference table

3. In `commands/run-prompt.md`:
   - Update `--model` argument description

4. In `commands/prompts.md`:
   - Update preferred_agent options if needed

5. In `commands/create-prompt.md`:
   - Update `<available_models>` section
   - Update recommendation logic table
   - Update model selection menus (3 instances)

6. In `commands/create-llms-txt.md`:
   - Update `<available_models>` section
   - Update recommendation logic table
   - Update model selection menu

7. In `README.md`:
   - Update Model Tiers section

8. In `CLAUDE.md`:
   - Update Model Shorthand Reference table

**Kimi K2.5 changes (new model):**

1. In `skills/prompt-executor/scripts/executor.py`:
   - Add `"kimi"` to `LEGACY_MODEL_DISPLAY`: `"kimi": "kimi (Kimi K2.5 via OpenCode)"`
   - Add `"kimi"` to `MODEL_SPECS`:
     ```python
     "kimi": {
         "model_id": "opencode:kimi-k2.5",
         "default_cli": "opencode",
         "supports_codex_reasoning": False,
         "codex_profile": None,
         "claude_model_flag": None,
     },
     ```
   - Add `"kimi"` to `CLI_OVERRIDE_SUPPORTED_MODELS["opencode"]` set
   - Add `"kimi"` to the `--model` argparse choices list

2. Update all the same downstream files (SKILL.md, run-prompt.md, create-prompt.md, create-llms-txt.md, README.md, CLAUDE.md) to include kimi as an option

**OpenCode model spec note:**
For models with `opencode` provider prefix, the `_opencode_model_spec()` function handles stripping the prefix. The model ID `opencode:kimi-k2.5` will result in OpenCode being called with `-m kimi-k2.5`, which maps to the `opencode/kimi-k2.5` provider entry.
</requirements>

<implementation>
Follow the Managing Models checklist in CLAUDE.md exactly. The checklist lists 14 files in order.

Key patterns to follow:
- Look at how `glm5` is defined as an opencode model — Kimi K2.5 should follow the same pattern
- Look at how `gpt52`/`gpt52-high`/`gpt52-xhigh` are defined — `gpt54` variants should follow the same pattern
- The `codex` shorthand must point to gpt-5.4 now (it was gpt-5.3-codex before)
- `codex-high` and `codex-xhigh` should also point to gpt-5.4 with reasoning effort flags
- `codex-spark` stays at gpt-5.3-codex-spark (unchanged)

For the `_opencode_model_spec()` function, verify it handles the `opencode:` prefix correctly for kimi.
</implementation>

<verification>
```bash
# Verify model appears in help
PLUGIN_ROOT=$(jq -r '.plugins."daplug@cruzanstx"[0].installPath' ~/.claude/plugins/installed_plugins.json)
python3 "$PLUGIN_ROOT/skills/prompt-executor/scripts/executor.py" --help | grep -E "kimi|gpt54"

# Test command generation for new models
python3 "$PLUGIN_ROOT/skills/prompt-executor/scripts/executor.py" 001 --model kimi
python3 "$PLUGIN_ROOT/skills/prompt-executor/scripts/executor.py" 001 --model codex
python3 "$PLUGIN_ROOT/skills/prompt-executor/scripts/executor.py" 001 --model gpt54

# Verify codex now shows gpt-5.4
python3 "$PLUGIN_ROOT/skills/prompt-executor/scripts/executor.py" 001 --model codex 2>&1 | grep -i "5.4"

# Verify codex-spark is still gpt-5.3
python3 "$PLUGIN_ROOT/skills/prompt-executor/scripts/executor.py" 001 --model codex-spark 2>&1 | grep -i "5.3"

# Run config reader tests
cd "$PLUGIN_ROOT/skills/config-reader" && python3 -m pytest tests/ -v
```

Before declaring complete, verify:
- [ ] All 14 files from the Managing Models checklist have been updated
- [ ] `codex` shorthand resolves to gpt-5.4
- [ ] `codex-spark` still resolves to gpt-5.3-codex-spark
- [ ] `gpt54`, `gpt54-high`, `gpt54-xhigh` are available as new shorthands
- [ ] `kimi` shorthand resolves to opencode/kimi-k2.5
- [ ] No existing model shorthands are broken
- [ ] Argparse choices include all new entries
</verification>

<success_criteria>
- Running `--model codex` uses gpt-5.4 instead of gpt-5.3-codex
- Running `--model kimi` launches OpenCode with kimi-k2.5
- Running `--model gpt54-xhigh` launches Codex with gpt-5.4 and xhigh reasoning
- All documentation (CLAUDE.md, README.md, SKILL.md, command files) reflect the new models
- Existing models (codex-spark, gpt52, gemini, etc.) continue to work unchanged
</success_criteria>
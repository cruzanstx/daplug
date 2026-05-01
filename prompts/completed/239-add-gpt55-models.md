<objective>
Add GPT-5.5 support to daplug as the new default codex model. GPT-5.5 was released by OpenAI on April 23, 2026 (model ID `openai/gpt-5.5`) and is available in both Codex CLI and OpenCode.

Make `codex`/`codex-high`/`codex-xhigh` shorthands resolve to gpt-5.5 (replacing gpt-5.4 as the default), and add new explicit `gpt55`/`gpt55-high`/`gpt55-xhigh` shorthands. Also update OpenCode's default model.

This mirrors exactly what was done for gpt-5.4 in prompt 237 — follow that prompt's structure as the template.
</objective>

<context>
GPT-5.5 just released and is available as `openai/gpt-5.5` in both Codex CLI and OpenCode (per OpenAI's April 23, 2026 announcement). It delivers better results with fewer tokens than GPT-5.4 for most coding tasks.

Current state (as of this prompt):
- `codex` shorthand → gpt-5.4 (set in prompt 237)
- `codex-high` / `codex-xhigh` → gpt-5.4 with reasoning variants
- `codex-spark` → gpt-5.3-codex-spark (low latency tier — leave unchanged)
- `gpt54` / `gpt54-high` / `gpt54-xhigh` → explicit gpt-5.4 shorthands
- `gpt52` / `gpt52-high` / `gpt52-xhigh` → explicit gpt-5.2 shorthands (kept around)
- OpenCode config (`~/.config/opencode/opencode.json`) currently defaults to gpt-5.4

After this change:
- `codex` shorthand → gpt-5.5 (new default)
- `codex-high` / `codex-xhigh` → gpt-5.5 with reasoning variants
- `codex-spark` → unchanged (still gpt-5.3-codex-spark)
- `gpt55` / `gpt55-high` / `gpt55-xhigh` → new explicit shorthands
- `gpt54` / `gpt54-high` / `gpt54-xhigh` → kept around as legacy explicit shorthands (do not remove)
- OpenCode default model → gpt-5.5

Read `CLAUDE.md` in the repo root for the full "Managing Models" checklist — it lists all 14 files that must be updated when adding/changing models. Read `prompts/completed/237-add-gpt54-kimi-models.md` for the prior pattern this should follow.
</context>

<requirements>
**Codex CLI changes (executor.py + downstream docs):**

1. In `skills/prompt-executor/scripts/executor.py`:
   - Update `LEGACY_MODEL_DISPLAY["codex"]` display string from `"codex (gpt-5.4)"` to `"codex (gpt-5.5)"`
   - Update `LEGACY_MODEL_DISPLAY["codex-high"]` to `"codex-high (gpt-5.5, high reasoning)"`
   - Update `LEGACY_MODEL_DISPLAY["codex-xhigh"]` to `"codex-xhigh (gpt-5.5, xhigh reasoning)"`
   - Update `MODEL_SPECS["codex"]["model_id"]` from `"openai:gpt-5.4"` to `"openai:gpt-5.5"`
   - Keep `codex-spark` pointing at gpt-5.3-codex-spark (unchanged)
   - Keep `gpt54`, `gpt54-high`, `gpt54-xhigh` exactly as they are (legacy explicit shorthands stay)
   - Add `"gpt55"` to `LEGACY_MODEL_DISPLAY`: `"gpt55 (GPT-5.5, direct shorthand)"`
   - Add `"gpt55-high"` and `"gpt55-xhigh"` display entries (mirror gpt54-high/gpt54-xhigh)
   - Add `"gpt55"` to `MODEL_SPECS`:
     ```python
     "gpt55": {
         "model_id": "openai:gpt-5.5",
         "default_cli": "codex",
         "supports_codex_reasoning": True,
         "codex_profile": None,
         "claude_model_flag": None,
     },
     ```
   - Add `"gpt55-high"` and `"gpt55-xhigh"` entries to the alias maps (the dicts that map `*-high`/`*-xhigh` → base model and reasoning effort — same pattern as `gpt54-high`/`gpt54-xhigh`)
   - Add `"gpt55"`, `"gpt55-high"`, `"gpt55-xhigh"` to the `--model` argparse choices list (both occurrences around lines 834 and 851)
   - Search for any string literal mentioning `"gpt-5.4"` as the canonical/default Codex model and update to `"gpt-5.5"` where it represents the default (e.g., the line around 991: `if stripped and stripped != "gpt-5.4":` should become `"gpt-5.5"`)

2. In `skills/prompt-executor/SKILL.md`:
   - Update `--model` options list to reflect gpt-5.5 as the new codex default
   - Update Model Reference table (codex → 5.5, add gpt55 variants)

3. In `commands/run-prompt.md`:
   - Update `--model` argument description to reference gpt-5.5

4. In `commands/prompts.md`:
   - Update preferred_agent options list to include gpt55 variants

5. In `commands/create-prompt.md`:
   - Update `<available_models>` section (codex now 5.5, add gpt55 group)
   - Update recommendation logic table (anywhere 5.4 was the default, suggest 5.5)
   - Update model selection menus (3 instances) — add gpt55 group after gpt54

6. In `commands/create-llms-txt.md`:
   - Update `<available_models>` section
   - Update recommendation logic table
   - Update model selection menu

7. In `README.md`:
   - Update Model Tiers section — codex defaults to 5.5, add gpt55 variants

8. In `CLAUDE.md` (repo root):
   - Update Model Shorthand Reference table — codex/codex-high/codex-xhigh now → gpt-5.5
   - Add new rows: gpt55, gpt55-high, gpt55-xhigh
   - Keep gpt54 rows in place (legacy)

**OpenCode changes:**

1. Update `~/.config/opencode/opencode.json` default model from `openai/gpt-5.4` to `openai/gpt-5.5`
   - Note: this is a user-level file outside the repo. The change should be made on the executing machine. If running in a worktree that does not have access to `~/.config/opencode/opencode.json`, document the exact diff needed in the verification output so the user can apply it.

2. The opencode-driven shorthands (`opencode`, `glm5`, `kimi`, `local`, etc.) do not need new entries — they already pass through the configured default. But verify nothing in `executor.py` hardcodes `gpt-5.4` for the opencode path.
</requirements>

<implementation>
Follow the Managing Models checklist in CLAUDE.md exactly. The checklist lists 14 files in order. Use prompt 237 (`prompts/completed/237-add-gpt54-kimi-models.md`) as the working template — this prompt is structurally identical, just with 5.4→5.5 and adding gpt55 alongside (not replacing) gpt54.

Key patterns to follow:
- Look at how `gpt54`/`gpt54-high`/`gpt54-xhigh` are defined — `gpt55` variants should follow the exact same pattern, just one section above or below in each file
- The `codex` shorthand now points to gpt-5.5 (was gpt-5.4)
- `codex-high` and `codex-xhigh` should also point to gpt-5.5 with reasoning effort flags
- `codex-spark` stays at gpt-5.3-codex-spark (unchanged)
- Do NOT remove `gpt54`/`gpt54-high`/`gpt54-xhigh` — they remain as legacy explicit access

After editing executor.py, also use the management script to sanity-check:
```bash
python3 scripts/manage-models.py list
python3 scripts/manage-models.py check
```
</implementation>

<verification>
```bash
# Verify new models appear in help
PLUGIN_ROOT=$(jq -r '.plugins."daplug@cruzanstx"[0].installPath' ~/.claude/plugins/installed_plugins.json)
EXECUTOR="$PLUGIN_ROOT/skills/prompt-executor/scripts/executor.py"

python3 "$EXECUTOR" --help | grep -E "gpt55|gpt54"

# Verify codex now shows gpt-5.5
python3 "$EXECUTOR" 001 --model codex 2>&1 | grep -i "5.5"

# Verify codex-high and codex-xhigh now show gpt-5.5
python3 "$EXECUTOR" 001 --model codex-high 2>&1 | grep -i "5.5"
python3 "$EXECUTOR" 001 --model codex-xhigh 2>&1 | grep -i "5.5"

# Verify codex-spark is still gpt-5.3
python3 "$EXECUTOR" 001 --model codex-spark 2>&1 | grep -i "5.3"

# Verify new gpt55 variants
python3 "$EXECUTOR" 001 --model gpt55
python3 "$EXECUTOR" 001 --model gpt55-high
python3 "$EXECUTOR" 001 --model gpt55-xhigh

# Verify gpt54 still works (legacy preserved)
python3 "$EXECUTOR" 001 --model gpt54 2>&1 | grep -i "5.4"

# Run config reader tests
cd "$PLUGIN_ROOT/skills/config-reader" && python3 -m pytest tests/ -v

# Verify OpenCode default updated (or print the required diff if not editable here)
grep -E '"model"|gpt-5\.[45]' ~/.config/opencode/opencode.json 2>/dev/null || echo "opencode.json not accessible from this worktree — print diff needed"
```

Before declaring complete, verify:
- [ ] All 14 files from the Managing Models checklist have been updated
- [ ] `codex` shorthand resolves to gpt-5.5
- [ ] `codex-high` and `codex-xhigh` resolve to gpt-5.5 with reasoning effort flags
- [ ] `codex-spark` still resolves to gpt-5.3-codex-spark
- [ ] `gpt55`, `gpt55-high`, `gpt55-xhigh` are available as new shorthands
- [ ] `gpt54`, `gpt54-high`, `gpt54-xhigh` still work (legacy preserved)
- [ ] `gpt52` variants still work (no regression)
- [ ] OpenCode default model is gpt-5.5 (or diff is documented for user to apply)
- [ ] No existing model shorthands are broken
- [ ] Argparse choices include all new entries (both occurrences)
- [ ] Hardcoded `"gpt-5.4"` default-detection literals updated to `"gpt-5.5"`
</verification>

<success_criteria>
- Running `--model codex` uses gpt-5.5 instead of gpt-5.4
- Running `--model codex-high` uses gpt-5.5 with high reasoning
- Running `--model codex-xhigh` uses gpt-5.5 with xhigh reasoning
- Running `--model gpt55-xhigh` launches Codex with gpt-5.5 and xhigh reasoning
- Running `--model gpt54` still works (legacy access preserved)
- OpenCode launches with gpt-5.5 as the default model
- All documentation (CLAUDE.md, README.md, SKILL.md, command files) reflect gpt-5.5 as the codex default
- Existing models (codex-spark, gpt52, gemini, kimi, glm5, etc.) continue to work unchanged
</success_criteria>
